"""The alerts suite must never touch the REAL backend/data tree (lane A review F5).

On 2026-09-28 `test_alerts_replies` wrote seven synthetic rows -- one carrying
"ignore all previous instructions" -- into the real
`news_corpus/dj_digest_inbox/2026-09-28.jsonl`, because `web_reader.store_article`
writes its corpus row under `config.OPTIMUS_LEDGER_DIR` whatever `root=` says.
The row count grew by one on every run.

`guard_real_data` is an autouse fixture in every `test_alerts_*.py` module: it
wraps every way this code opens a file and FAILS the test on

* any write (open for w/a/x/+, `os.open` with a write flag, `os.replace` /
  `os.rename` onto it) to a path under the real `backend/data`, and
* any read of the lane's private or live stores under the real
  `backend/data/optimus` (alerts, telegram, news_corpus, digest_inbox,
  prices_2025_26, paper_accounts, llm_portfolio).

It resolves paths from THIS file's location, not from `backend.config`, so a
test that monkeypatches the config cannot hide from it.
"""

from __future__ import annotations

import builtins
import io
import os
from pathlib import Path

import pytest

REAL_DATA = (Path(__file__).resolve().parents[1] / "data").resolve()
REAL_OPTIMUS = REAL_DATA / "optimus"
PRIVATE_DIRS = tuple(REAL_OPTIMUS / d for d in (
    "alerts", "telegram", "news_corpus", "digest_inbox", "prices_2025_26",
    "paper_accounts", "llm_portfolio", "edgar_8k", "sec_insider", "analyst"))


class RealDataTouched(AssertionError):
    """A test in the alerts suite resolved a path under the real data tree."""


def _resolve(p) -> Path | None:
    if isinstance(p, int):
        return None
    try:
        return Path(os.fsdecode(p)).resolve()
    except (TypeError, ValueError, OSError):
        return None


def _under(p: Path | None, root: Path) -> bool:
    if p is None:
        return False
    try:
        p.relative_to(root)
        return True
    except ValueError:
        return False


def check(path, *, write: bool) -> None:
    p = _resolve(path)
    if write and _under(p, REAL_DATA):
        raise RealDataTouched(f"the alerts suite WROTE to the real data tree: {p}")
    if not write and any(_under(p, d) for d in PRIVATE_DIRS):
        raise RealDataTouched(f"the alerts suite READ a real private store: {p}")


_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC


def install(monkeypatch) -> list[str]:
    """Wrap the file-opening entry points; returns the list of violations seen
    (each also raises inside the test that caused it)."""
    seen: list[str] = []
    real_open = io.open
    real_os_open = os.open
    real_replace = os.replace
    real_rename = os.rename

    def g_open(file, mode="r", *a, **k):
        try:
            check(file, write=any(c in str(mode) for c in "wax+"))
        except RealDataTouched as exc:
            seen.append(str(exc))
            raise
        return real_open(file, mode, *a, **k)

    def g_os_open(path, flags, *a, **k):
        try:
            check(path, write=bool(flags & _WRITE_FLAGS))
        except RealDataTouched as exc:
            seen.append(str(exc))
            raise
        return real_os_open(path, flags, *a, **k)

    def g_move(real):
        def f(src, dst, *a, **k):
            try:
                check(dst, write=True)
            except RealDataTouched as exc:
                seen.append(str(exc))
                raise
            return real(src, dst, *a, **k)
        return f

    monkeypatch.setattr(builtins, "open", g_open)
    monkeypatch.setattr(io, "open", g_open)
    monkeypatch.setattr(os, "open", g_os_open)
    monkeypatch.setattr(os, "replace", g_move(real_replace))
    monkeypatch.setattr(os, "rename", g_move(real_rename))
    from backend.services import disk_guard as DG
    monkeypatch.setattr(DG, "_open", g_open)
    return seen


@pytest.fixture(autouse=True)
def guard_real_data(monkeypatch):
    seen = install(monkeypatch)
    yield seen
    assert not seen, seen
