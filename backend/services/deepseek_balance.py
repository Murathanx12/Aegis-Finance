"""The provider's own balance — the ONLY economic truth about LLM spend.

WHY THIS EXISTS
===============
On 2026-08-24 the IIF-1 night receipt reported `$0.941` for the night while the
DeepSeek account was observed losing roughly `$3/day`. Both numbers were
defended and neither could be checked, because the repository had no way to ask
the provider what it had actually charged. It had:

  * `llm_telemetry.price_call` — correct arithmetic over the tokens WE saw;
  * `investigator_night.DEFAULT_BALANCE_USD` — a hand-typed constant, dated
    2026-08-15, updated by a human editing a source file.

A hand-typed balance cannot detect the failure it exists to detect. If a call
never reaches the telemetry ledger — a module that does not record, a process
on another host, a retry counted once — then telemetry and the constant agree
with each other and both are wrong, and nothing anywhere raises. That is the
house failure mode (silent fragility) applied to money.

DeepSeek exposes `GET /user/balance`. That figure is the vendor's, it includes
every call from every host on the key, and it is not derived from anything this
repository believes. Snapshotting it turns "what did the night cost?" from a
model into a MEASUREMENT:

    unaccounted = (balance_before - balance_after) - telemetry_total

FIRST MEASUREMENT, 2026-08-24 19:xx HKT
---------------------------------------
Live balance `$23.99`. The last recorded figure was `$57.12` as of 2026-08-15
(`investigator_night.DEFAULT_BALANCE_USD`). That is **$33.13 across 9 days,
~$3.68/day** — so Murat's ~$3/day observation is the real number and the
$0.941 IIF receipt is real too: they are measuring different populations. IIF-1
is one of several DeepSeek consumers on one key (the arena's nightly beliefs,
why_moved, the specialists, prediction markets, copy_lab, plus attended local
research runs), and no surface had ever summed them.

WHAT THIS MODULE IS NOT
=======================
It is not a budget guard — `research_budget` is. It does not decide anything and
nothing blocks on it. A failed read is recorded as an ERROR IN THE RECEIPT and
never as a zero, because a zero balance delta would read as "the night was
free", which is the exact misreport this module exists to end.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.config import DATA_DIR

logger = logging.getLogger(__name__)

BALANCE_URL = "https://api.deepseek.com/user/balance"
TIMEOUT_S = 20.0

#: Append-only. One line per read, so a delta between any two moments is a
#: subtraction rather than an archaeology exercise. Lives under DATA_DIR so it
#: is on the persistent volume in production (see belief_state's ledger note —
#: a spend history destroyed by every deploy is not a history).
SNAPSHOT_PATH = DATA_DIR / "optimus" / "deepseek_balance.jsonl"


#: Strictly-increasing wall-clock stamp, and the reason it cannot just be
#: `datetime.now()`.
#:
#: `read_at` is the KEY `spend_between` looks a snapshot up by. Two reads that
#: share a stamp collapse to one row and the delta between them computes as
#: $0.00 — exactly the "the night was free" misreport this module exists to
#: end, produced by the module built to end it.
#:
#: `llm_telemetry._now` hit the same class of bug at SECOND resolution and
#: moved to microseconds. Microseconds are not enough here: on this Windows
#: host `datetime.now()` advances in ~15.6 ms ticks, so two reads inside one
#: tick return byte-identical microsecond stamps. Measured, not assumed — the
#: test below failed against the microsecond version on the first run.
#:
#: So the stamp is monotonic BY CONSTRUCTION: never less than or equal to the
#: last one this process emitted. The nudge is one microsecond, which is
#: smaller than any real interval anybody will ever measure with it, and the
#: ordering it guarantees is what the file's `sorted(...)` depends on.
_LAST_STAMP = ""
_STAMP_LOCK = threading.Lock()


def _now() -> str:
    global _LAST_STAMP
    with _STAMP_LOCK:
        t = datetime.now(timezone.utc)
        stamp = t.isoformat(timespec="microseconds")
        if stamp <= _LAST_STAMP:
            t = datetime.fromisoformat(_LAST_STAMP) + timedelta(microseconds=1)
            stamp = t.isoformat(timespec="microseconds")
        _LAST_STAMP = stamp
        return stamp


class BalanceUnavailable(RuntimeError):
    """The provider could not be asked. NOT a zero, NOT a stale number."""


def read_balance(*, api_key: str | None = None, url: str = BALANCE_URL,
                 opener=None) -> dict:
    """Live USD balance from DeepSeek. Raises `BalanceUnavailable`.

    Returns the raw vendor payload plus a parsed `total_usd`, so a caller that
    wants the arithmetic gets a float and a caller writing a receipt keeps the
    bytes the vendor actually sent.
    """
    key = api_key if api_key is not None else os.getenv("DEEPSEEK_API_KEY", "")
    if not key:
        raise BalanceUnavailable("DEEPSEEK_API_KEY is not set — the balance "
                                 "cannot be read, and no default stands in")
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {key}",
                      "Accept": "application/json"})
    try:
        _open = opener or urllib.request.urlopen
        with _open(req, timeout=TIMEOUT_S) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        raise BalanceUnavailable(f"{type(exc).__name__}: {exc}") from exc

    infos = payload.get("balance_infos") or []
    usd = [i for i in infos if str(i.get("currency", "")).upper() == "USD"]
    if not usd:
        raise BalanceUnavailable(
            f"no USD row in balance_infos (currencies: "
            f"{[i.get('currency') for i in infos]}) — the account may be "
            f"denominated in another currency and this reader must be told, "
            f"not silently return the first row")
    try:
        total = float(usd[0]["total_balance"])
    except (KeyError, TypeError, ValueError) as exc:
        raise BalanceUnavailable(f"USD row has no readable total_balance: "
                                 f"{usd[0]!r}") from exc
    return {
        "total_usd": total,
        "granted_usd": _f(usd[0].get("granted_balance")),
        "topped_up_usd": _f(usd[0].get("topped_up_balance")),
        "is_available": bool(payload.get("is_available", True)),
        "read_at": _now(),
        "raw": payload,
    }


def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def snapshot(label: str, *, path: Path | None = None, **kw) -> dict:
    """Read the balance and APPEND it to the snapshot ledger.

    `label` says what moment this is ("iif1_night_start", "manual_audit", ...)
    so a delta can be taken between the two ends of one run rather than between
    two unrelated reads. Never raises on a write failure — but never silently
    succeeds either: a read that could not be persisted returns
    `persisted: False` and logs, so a receipt built from it says so.
    """
    row = read_balance(**kw)
    row["label"] = str(label)
    p = path or SNAPSHOT_PATH
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({k: v for k, v in row.items() if k != "raw"},
                                sort_keys=True) + "\n")
        row["persisted"] = True
    except OSError as exc:                                     # noqa: BLE001
        logger.warning("deepseek_balance: read %.4f but could NOT persist to "
                       "%s (%s) — the delta against this point will not be "
                       "computable later", row["total_usd"], p, exc)
        row["persisted"] = False
    return row


def snapshots(path: Path | None = None) -> list[dict]:
    """Every persisted read, oldest first. Torn lines are SKIPPED AND COUNTED
    by the caller's own reading of the file length — this returns only what
    parsed, and never invents a row."""
    p = path or SNAPSHOT_PATH
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            logger.warning("deepseek_balance: unreadable snapshot line skipped")
            continue
        if isinstance(row, dict) and "total_usd" in row:
            out.append(row)
    return sorted(out, key=lambda r: str(r.get("read_at") or ""))


def spend_between(start_read_at: str, end_read_at: str,
                  path: Path | None = None) -> float | None:
    """USD the PROVIDER says left the account between two snapshots.

    None when either endpoint is missing — never 0.0, which would read as "no
    spend" when it means "no measurement". A NEGATIVE result is returned as-is
    and means a top-up happened inside the window; the caller must say so
    rather than clamp it, because a clamped top-up hides real spend.
    """
    rows = {str(r.get("read_at")): r for r in snapshots(path)}
    a, b = rows.get(start_read_at), rows.get(end_read_at)
    if not a or not b:
        return None
    return round(float(a["total_usd"]) - float(b["total_usd"]), 6)
