"""The forecast ledger as two append-only monthly streams, sealed by a manifest chain.

    python -m backend.services.forecast_ledger --status          # which backend, which files, the chain
    python -m backend.services.forecast_ledger --verify          # re-hash every sealed month
    python -m backend.services.forecast_ledger --seal            # what would be sealed (writes nothing)
    python -m backend.services.forecast_ledger --seal --apply    # seal closed months (attended, then commit)

The migration itself is `python -m scripts.ledger_split --plan` / `--apply`
(`backend/services/forecast_ledger_migration.py`).

WHY THE SINGLE FILE HAD TO GO
=============================
`predictions.jsonl` is tracked, ~54 MB, grows ~25 MB a month, and is rewritten
IN PLACE every time a record resolves (`belief_state.resolve_all`,
`forecast_grader.void_unresolvable`). A rewrite of the whole file per grade is
bad for git (every resolution is a 54 MB diff), bad for crash safety (the
resolver's `write_text` was not atomic), and fatal to any byte-level seal: a
closed month can never be vouched for while a later grade rewrites its bytes.

THE DESIGN
==========
Two LOGICAL streams, one file per month each:

* `forecasts/forecasts_<YYYY-MM>.jsonl` -- the forecast row AS MADE, filed by the
  month of its `made_at`, never touched again;
* `resolutions/resolutions_<YYYY-MM>.jsonl` -- one EVENT per grade or void
  (`{"prediction_id", "event": "resolve"|"void", "set": {...}}`), filed by the
  month the event was RECORDED.

A reader folds events onto rows by `prediction_id`. That is the pattern the LLM
telemetry already uses (immutable call rows + later facts joined by id), and it
means a closed month is closed: a late grade is a new event in the open month,
not an edit of an old one. Folding reproduces the legacy row exactly (dict
equality and canonical hash, verified row by row at migration time).

DUPLICATES ARE A RULE, NOT AN ACCIDENT. The FIRST terminal event for an id wins
and every later one is ignored and counted (`fold_stats`). That is the legacy
semantics made explicit: `resolve_one` never re-grades a graded record and the
void pass never voids a graded one. Writers also refuse to append a second
terminal event under the lock, so a duplicate can only come from a hand edit or
a crashed process -- and then it is visible, not silently applied.

A late FORECAST for a sealed month (a backdated restoration) is filed in the
open month instead; its `made_at` is untouched and `status()` counts it.

THE CHAIN IS MANIFEST-TO-MANIFEST
=================================
A closed month is sealed (attended) by a manifest under
`ledger_manifests/forecast_ledger/<stream>_<YYYY-MM>.json`: rows, bytes, sha256
of the stream file, the previous manifest's hash and its own. Order is
(month, forecasts before resolutions). Per-row chaining in an appended file is
what a concurrent writer tears; one manifest per sealed month cannot be torn by
an append, and git carries the manifests.

The legacy file carried NO row chain at all (verified over every row and every
committed version; `forecast_ledger_migration.legacy_chain_report`). The 25 Aug
2026 chain break the handoffs remember belongs to the terminal repo's
`state/decisions.jsonl`. The genesis manifest says so in its
`legacy_chain_break` record, and tamper evidence for this ledger starts there.

THE COMPATIBILITY SWITCH
========================
`backend_for(path)` picks the backend for a LOGICAL ledger path:

* no marker at `ledger_manifests/forecast_ledger/MIGRATION.json` -> the legacy file;
* a valid marker naming this file -> the streams;
* a marker that is present but unreadable -> REFUSED. Falling back to the legacy
  file after a migration would read a frozen ledger that no longer receives
  writes, and "empty output is not automatically healthy".

Every write takes one cross-process lock (`.forecast_ledger.lock` beside the
legacy file) and re-selects the backend under it, so the migration's switch is
atomic with respect to every writer running this code.

WHAT IS STILL LEGACY
====================
Until an attended `--apply`, everything reads and writes `predictions.jsonl`
exactly as before (the resolver's rewrite is now atomic and keeps rows appended
while it graded). The arena and leakage-probe ledgers are separate logical
ledgers and stay single files.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import logging
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from backend import config as _config

logger = logging.getLogger(__name__)

#: The legacy single-file ledger this module replaces.
LEGACY_NAME = "predictions.jsonl"
FORECAST_DIR = "forecasts"
RESOLUTION_DIR = "resolutions"
#: Chain order within a month.
STREAMS = ("forecasts", "resolutions")
_STREAM_DIRS = {"forecasts": FORECAST_DIR, "resolutions": RESOLUTION_DIR}
#: Manifests and the migration marker, relative to the ledger directory.
MANIFEST_SUBDIR = Path("ledger_manifests") / "forecast_ledger"
MARKER_NAME = "MIGRATION.json"
LOCK_NAME = ".forecast_ledger.lock"
#: Who holds it, for the LedgerBusy message. Ends in `.lock`, so `.gitignore`'s
#: `*.lock` keeps both out of `git status`.
LOCK_HOLDER_NAME = ".forecast_ledger.holder.lock"

MARKER_SCHEMA = "forecast_ledger_migration/1"
MANIFEST_SCHEMA = "forecast_ledger_manifest/1"
EVENT_SCHEMA = "forecast_resolution/1"
EVENT_KINDS = ("resolve", "void")

STREAM_FILE = re.compile(r"^(?P<stream>forecasts|resolutions)_"
                         r"(?P<month>\d{4}-(?:0[1-9]|1[0-2]))\.jsonl$")
_MONTH = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")
#: A row's own id when it is the FIRST key (every writer's layout). Anchored, so
#: a nested `prediction_id` inside `inputs_used` can never be mistaken for it.
_FIRST_ID = re.compile(rb'^\{"prediction_id":\s*"([^"\\]+)"')

#: The fields a grade or a void writes, and the value they hold while a record
#: is open. Everything else on a row is frozen at `made_at`.
RESOLUTION_DEFAULTS: dict[str, Any] = {
    "resolved_at": None, "outcome": None, "brier": None, "resolution_detail": {},
    "void_reason": None, "calibration_bucket": None, "vs_benchmark": None,
    "vs_control": None,
}
RESOLUTION_KEYS = frozenset(RESOLUTION_DEFAULTS) | {"voided_at", "voided_by"}


class ForecastLedgerError(RuntimeError):
    """A refusal. The message says why and what to run; nothing was written."""


class LedgerBusy(ForecastLedgerError):
    """Another process held the ledger lock past the timeout."""


class SealRefused(ForecastLedgerError):
    """A seal (or a write into a sealed month) would make a manifest false."""


class MigrationRefused(ForecastLedgerError):
    """`scripts.ledger_split` refused; nothing was switched."""


# ─────────────────────────────── small helpers ───────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _repo_root() -> Path:
    """The checkout, honouring `AEGIS_REPO_ROOT` (frozen-path family; the same
    rule as `ledger_archive._repo_root`)."""
    env = os.getenv("AEGIS_REPO_ROOT")
    if env and Path(env).is_dir():
        return Path(env).resolve()
    return Path(_config.__file__).resolve().parents[1]


def rel(path: Path) -> str:
    """Repo-relative POSIX path when inside the checkout, else as given."""
    try:
        return Path(path).resolve().relative_to(_repo_root()).as_posix()
    except (ValueError, OSError):
        return Path(path).as_posix()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      default=str)


def canonical_row_hash(row: dict) -> str:
    """Content identity of a row: independent of key order and line endings."""
    return sha256_bytes(canonical_json(row).encode("utf-8"))


def row_line(row: dict) -> bytes:
    """THE serialisation of a stream row: the legacy writer's own `json.dumps`
    (key order kept), UTF-8, LF. Never CRLF, on any platform."""
    return (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")


def month_of(stamp: Any) -> Optional[str]:
    """`YYYY-MM` of an ISO stamp or date, else None (never a guess)."""
    s = str(stamp or "")[:7]
    return s if _MONTH.match(s) else None


def month_floor(dt: datetime) -> str:
    return f"{dt.astimezone(timezone.utc):%Y-%m}"


def _next_month_start(month: str) -> datetime:
    y, m = int(month[:4]), int(month[5:7])
    y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return datetime(y, m, 1, tzinfo=timezone.utc)


def is_sealable_month(month: str, now: datetime) -> bool:
    """Closed AND past the grace period, by the run clock (never a file mtime)."""
    grace = timedelta(days=float(getattr(_config, "FORECAST_LEDGER_SEAL_GRACE_DAYS", 1)))
    return now >= _next_month_start(month) + grace


def _chain_key(stream: str, month: str) -> tuple[str, int]:
    return (month, STREAMS.index(stream))


def _fsync_dir(path: Path) -> None:
    """Best effort: POSIX can fsync a directory entry, Windows cannot."""
    if os.name == "nt":
        return
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """temp file -> flush -> fsync -> `os.replace`. The canonical file is never
    partially overwritten: a crash leaves either the old bytes or the new."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}.{threading.get_ident()}")
    try:
        with tmp.open("wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    _fsync_dir(path.parent)


def atomic_write_text(path: Path, text: str) -> None:
    """The legacy file's write: TEXT mode, so each platform keeps the line
    endings the legacy writers always produced (a migration, not a 54 MB
    line-ending diff), but atomic and fsynced, which `write_text` was not."""
    path = Path(path)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}.{threading.get_ident()}")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    _fsync_dir(path.parent)


# ─────────────────────────────── the lock ────────────────────────────────────

_THREAD_LOCKS: dict[str, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()
_HELD = threading.local()            # .depth: {lock key: re-entry depth} for THIS thread
_LOCK_WARNED = False


def _thread_lock(key: str) -> threading.RLock:
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.RLock())


def _depths() -> dict:
    d = getattr(_HELD, "depth", None)
    if d is None:
        d = _HELD.depth = {}
    return d


def _try_file_lock(fh) -> bool:
    """Non-blocking exclusive lock on byte 0. True when held."""
    if os.name == "nt":
        import msvcrt
        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    import fcntl
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except BlockingIOError:
        return False


def _release_file_lock(fh) -> None:
    try:
        if os.name == "nt":
            import msvcrt
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except OSError:                                                # pragma: no cover
        pass


@contextlib.contextmanager
def ledger_lock(directory: Path, *, timeout_s: Optional[float] = None,
                purpose: str = "write") -> Iterator[None]:
    """One writer at a time per ledger directory, across threads AND processes.

    Re-entrant within a thread. The legacy writers held only a thread lock, so
    two processes could interleave a read-dedupe-append, and a resolver's
    read-grade-rewrite could drop rows appended meanwhile. Under this lock a
    writer re-selects the backend, so the migration's switch is atomic for
    every writer running this code (old code that was not restarted is the one
    thing it cannot see -- `--apply` re-hashes the legacy file for that).
    """
    global _LOCK_WARNED
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    key = str(directory.resolve())
    depths = _depths()
    tl = _thread_lock(key)
    tl.acquire()
    if depths.get(key):
        # Re-entry by the thread that already holds the file lock: an OS lock is
        # not re-entrant, and taking it again would wait on ourselves.
        depths[key] += 1
        try:
            yield
        finally:
            depths[key] -= 1
            tl.release()
        return
    fh = None
    locked = False
    holder_file = directory / LOCK_HOLDER_NAME
    try:
        timeout = float(timeout_s if timeout_s is not None else
                        getattr(_config, "FORECAST_LEDGER_LOCK_TIMEOUT_S", 120.0))
        try:
            fh = (directory / LOCK_NAME).open("a+b")
        except OSError as exc:
            if not _LOCK_WARNED:
                logger.warning("forecast ledger: no cross-process lock in %s (%s); "
                               "this process serialises its own threads only", directory, exc)
                _LOCK_WARNED = True
        if fh is not None:
            deadline = time.monotonic() + timeout
            while not _try_file_lock(fh):
                if time.monotonic() >= deadline:
                    holder = ""
                    with contextlib.suppress(OSError):
                        holder = holder_file.read_text(encoding="utf-8", errors="replace")[:200]
                    raise LedgerBusy(
                        f"the forecast ledger lock {rel(directory / LOCK_NAME)} was held "
                        f"for more than {timeout:.0f}s (last holder: {holder.strip() or 'unknown'}); "
                        f"nothing was written. An OS lock dies with its process, so a "
                        f"lock that never clears names a writer that is still running.")
                time.sleep(0.05)
            locked = True
            with contextlib.suppress(OSError):
                holder_file.write_text(f"pid {os.getpid()} {purpose} since {_iso(_now())}\n",
                                       encoding="utf-8")
        depths[key] = 1
        yield
    finally:
        depths[key] = 0
        if fh is not None:
            if locked:
                _release_file_lock(fh)
            fh.close()
        tl.release()


# ─────────────────────────────── backend selection ───────────────────────────

def default_legacy_path() -> Path:
    return Path(_config.OPTIMUS_LEDGER_DIR) / LEGACY_NAME


def manifest_dir_for(legacy_path: Path) -> Path:
    return Path(legacy_path).parent / MANIFEST_SUBDIR


def marker_path(legacy_path: Path) -> Path:
    return manifest_dir_for(legacy_path) / MARKER_NAME


@dataclass(frozen=True)
class Backend:
    kind: str                       # "legacy" | "streams"
    legacy_path: Path
    reason: str
    marker: Optional[dict] = None

    @property
    def root(self) -> Path:
        return self.legacy_path.parent

    @property
    def manifest_dir(self) -> Path:
        return manifest_dir_for(self.legacy_path)

    def stream_dir(self, stream: str) -> Path:
        return self.root / _STREAM_DIRS[stream]

    def stream_path(self, stream: str, month: str) -> Path:
        return self.stream_dir(stream) / f"{stream}_{month}.jsonl"

    def manifest_path(self, stream: str, month: str) -> Path:
        return self.manifest_dir / f"{stream}_{month}.json"

    def describe(self) -> dict:
        """What a receipt carries: which backend answered, and why."""
        out = {"backend": self.kind, "legacy_path": rel(self.legacy_path),
               "reason": self.reason}
        if self.marker:
            out["migrated_at_utc"] = self.marker.get("applied_at_utc")
            out["legacy_sha256"] = self.marker.get("legacy_sha256")
        return out


_MARKER_CACHE: dict[str, tuple[tuple, dict]] = {}
_MARKER_REQUIRED = ("schema", "legacy_name", "legacy_sha256", "applied_at_utc")


def _read_marker(mp: Path) -> dict:
    st = mp.stat()
    key = str(mp)
    stamp = (st.st_size, st.st_mtime_ns)
    hit = _MARKER_CACHE.get(key)
    if hit and hit[0] == stamp:
        return hit[1]
    try:
        marker = json.loads(mp.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ForecastLedgerError(
            f"the migration marker {rel(mp)} exists but cannot be read ({type(exc).__name__}: "
            f"{exc}). Readers REFUSE rather than fall back to the legacy file, which stopped "
            f"receiving writes at the migration. Restore the marker from git.") from exc
    missing = [k for k in _MARKER_REQUIRED if not (isinstance(marker, dict) and marker.get(k))]
    if missing or marker.get("schema") != MARKER_SCHEMA:
        raise ForecastLedgerError(
            f"the migration marker {rel(mp)} is not a {MARKER_SCHEMA} marker "
            f"(missing {missing or 'nothing'}, schema {marker.get('schema') if isinstance(marker, dict) else None!r}). "
            f"Readers refuse rather than guess which ledger is current.")
    _MARKER_CACHE[key] = (stamp, marker)
    return marker


def backend_for(path: Optional[Path] = None) -> Backend:
    """The backend that answers for the LOGICAL ledger at `path`.

    One `stat` when there is no marker, so it is cheap enough for every call."""
    legacy = Path(path) if path is not None else default_legacy_path()
    mp = marker_path(legacy)
    if not mp.exists():
        return Backend("legacy", legacy,
                       f"no migration marker at {rel(mp)}: the single legacy file is the ledger")
    marker = _read_marker(mp)
    if marker.get("legacy_name") != legacy.name:
        return Backend("legacy", legacy,
                       f"the marker at {rel(mp)} migrated {marker.get('legacy_name')!r}, "
                       f"not {legacy.name!r}")
    return Backend("streams", legacy,
                   f"migrated at {marker.get('applied_at_utc')} from legacy sha256 "
                   f"{str(marker.get('legacy_sha256'))[:12]}; monthly streams are the ledger",
                   marker)


# ─────────────────────────────── reading ─────────────────────────────────────

def stream_files(be: Backend, stream: str) -> list[tuple[str, Path]]:
    """`[(month, path)]` for one stream, oldest month first."""
    d = be.stream_dir(stream)
    if not d.is_dir():
        return []
    out = []
    for p in d.iterdir():
        m = STREAM_FILE.match(p.name)
        if m and m.group("stream") == stream and p.is_file():
            out.append((m.group("month"), p))
    return sorted(out)


def _split_raw_lines(raw: bytes) -> list[bytes]:
    lines = raw.split(b"\n")
    if lines and lines[-1] == b"":
        lines = lines[:-1]
    return lines


def _parse_line(line: bytes, where: str, lineno: int, strict: bool,
                bad: list) -> Optional[dict]:
    """One stream line -> dict. `where` is the file's label; the `file:line`
    string is only built on a failure (it was once built per line, and the
    path resolution behind it made a read ten times slower than the legacy one)."""
    s = line.strip()
    if not s:
        return None
    try:
        row = json.loads(s)
    except json.JSONDecodeError as exc:
        if strict:
            # The legacy read raised JSONDecodeError; callers catch that type.
            raise json.JSONDecodeError(f"{where}:{lineno}: {exc.msg}", exc.doc, exc.pos) from exc
        bad.append(f"{where}:{lineno}")
        return None
    except UnicodeDecodeError as exc:
        if strict:
            raise ValueError(f"{where}:{lineno} is not UTF-8: {exc}") from exc
        bad.append(f"{where}:{lineno}")
        return None
    if not isinstance(row, dict):
        if strict:
            raise ValueError(f"{where}:{lineno} is not a JSON object")
        bad.append(f"{where}:{lineno}")
        return None
    return row


def _read_legacy(path: Path, *, strict: bool, bad: Optional[list] = None) -> list[dict]:
    """Exactly what `belief_state.read_predictions` always did, plus a lenient mode."""
    path = Path(path)
    if not path.exists():
        return []
    bad = [] if bad is None else bad
    out: list[dict] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            if strict:
                raise
            bad.append(f"{rel(path)}:{i}")
    return out


@dataclass
class FoldStats:
    rows: int = 0
    events: int = 0
    applied: int = 0
    duplicate_forecast_ids: list = field(default_factory=list)
    duplicate_terminal_events: list = field(default_factory=list)
    orphan_events: list = field(default_factory=list)
    bad_lines: list = field(default_factory=list)

    def as_dict(self, cap: int = 20) -> dict:
        return {"rows": self.rows, "events": self.events, "applied": self.applied,
                "duplicate_forecast_ids": len(self.duplicate_forecast_ids),
                "duplicate_forecast_ids_sample": self.duplicate_forecast_ids[:cap],
                "duplicate_terminal_events_ignored": len(self.duplicate_terminal_events),
                "duplicate_terminal_events_sample": self.duplicate_terminal_events[:cap],
                "orphan_events_ignored": len(self.orphan_events),
                "orphan_events_sample": self.orphan_events[:cap],
                "bad_lines": len(self.bad_lines), "bad_lines_sample": self.bad_lines[:cap]}


def _read_forecasts(be: Backend, *, strict: bool, stats: FoldStats) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for month, p in stream_files(be, "forecasts"):
        where = rel(p)
        for i, line in enumerate(_split_raw_lines(p.read_bytes()), 1):
            row = _parse_line(line, where, i, strict, stats.bad_lines)
            if row is None:
                continue
            pid = row.get("prediction_id")
            if not isinstance(pid, str) or not pid:
                if strict:
                    raise ValueError(f"{where}:{i} has no prediction_id")
                stats.bad_lines.append(f"{where}:{i}")
                continue
            if pid in rows:
                # Never applied twice and never silently dropped: the first row
                # stands (it is the one every earlier read saw) and the copy is
                # counted on status(). Writers dedupe under the lock, so a copy
                # here is a hand edit or a crashed process.
                stats.duplicate_forecast_ids.append(pid)
                continue
            rows[pid] = row
    stats.rows = len(rows)
    return rows


def _read_events(be: Backend, *, strict: bool, stats: FoldStats) -> list[dict]:
    events: list[dict] = []
    for month, p in stream_files(be, "resolutions"):
        where = rel(p)
        for i, line in enumerate(_split_raw_lines(p.read_bytes()), 1):
            ev = _parse_line(line, where, i, strict, stats.bad_lines)
            if ev is None:
                continue
            problem = event_problem(ev)
            if problem:
                if strict:
                    raise ValueError(f"{where}:{i}: {problem}")
                stats.bad_lines.append(f"{where}:{i}")
                continue
            events.append(ev)
    stats.events = len(events)
    return events


def event_problem(ev: Any) -> Optional[str]:
    """Why `ev` is not a resolution event, or None."""
    if not isinstance(ev, dict):
        return "not a JSON object"
    if not isinstance(ev.get("prediction_id"), str) or not ev.get("prediction_id"):
        return "event without a prediction_id"
    if ev.get("event") not in EVENT_KINDS:
        return f"event kind {ev.get('event')!r} not in {EVENT_KINDS}"
    if not isinstance(ev.get("set"), dict) or not ev["set"]:
        return "event with no fields to set"
    return None


def fold(rows: dict[str, dict], events: list[dict], stats: Optional[FoldStats] = None) -> FoldStats:
    """Apply events to rows IN PLACE, in order. The FIRST terminal event per id
    wins; later ones and events for unknown ids are counted, never applied."""
    stats = stats or FoldStats(rows=len(rows), events=len(events))
    done: set[str] = set()
    for ev in events:
        pid = ev["prediction_id"]
        row = rows.get(pid)
        if row is None:
            stats.orphan_events.append(pid)
            continue
        if pid in done:
            stats.duplicate_terminal_events.append(pid)
            continue
        row.update(ev["set"])
        done.add(pid)
        stats.applied += 1
    return stats


def read_rows(path: Optional[Path] = None, *, strict: bool = True,
              stats: Optional[FoldStats] = None) -> list[dict]:
    """Every logical row, resolution folded in. The one read every caller uses.

    `strict` raises on an unparseable line (the legacy `read_predictions`
    contract); lenient skips it and records it on `stats.bad_lines`."""
    be = backend_for(path)
    stats = stats if stats is not None else FoldStats()
    if be.kind == "legacy":
        rows = _read_legacy(be.legacy_path, strict=strict, bad=stats.bad_lines)
        stats.rows = len(rows)
        return rows
    by_id = _read_forecasts(be, strict=strict, stats=stats)
    events = _read_events(be, strict=strict, stats=stats)
    fold(by_id, events, stats)
    if stats.duplicate_forecast_ids or stats.duplicate_terminal_events or stats.orphan_events:
        logger.warning("forecast ledger fold: %s", {k: v for k, v in stats.as_dict(3).items()
                                                   if k.endswith(("ids", "ignored"))})
    return list(by_id.values())


_TERMINAL_CACHE: dict[str, tuple[tuple, dict]] = {}


def _terminal_sets(be: Backend) -> dict[str, dict]:
    """`{prediction_id: set}` of the first terminal event per id (lenient).

    Cached on the resolution files' (name, size, mtime_ns): an append moves the
    key. Callers only read the sets (they are folded into copies)."""
    key = str(be.root.resolve())
    fp = tuple((p.name, p.stat().st_size, p.stat().st_mtime_ns)
               for _, p in stream_files(be, "resolutions"))
    hit = _TERMINAL_CACHE.get(key)
    if hit and hit[0] == fp:
        return hit[1]
    stats = FoldStats()
    out: dict[str, dict] = {}
    for ev in _read_events(be, strict=False, stats=stats):
        out.setdefault(ev["prediction_id"], ev["set"])
    _TERMINAL_CACHE[key] = (fp, out)
    return out


#: One folded copy of the streams' logical lines, keyed on `fingerprint()`: a
#: full scan (the health probes) re-serialises ~20k graded rows, about a second
#: each time. Any append moves a file's size and so the key. Not kept above
#: LOGICAL_CACHE_MAX_BYTES of text.
LOGICAL_CACHE_MAX_BYTES = 256 * 1024 * 1024
_LOGICAL_CACHE: dict[str, tuple[tuple, tuple]] = {}
_LOGICAL_CACHE_GUARD = threading.Lock()


def _fold_line(line: bytes, terminal: dict) -> str:
    m = _FIRST_ID.match(line)
    pid = m.group(1).decode("utf-8", "replace") if m else None
    if pid is None:
        try:
            pid = json.loads(line).get("prediction_id")
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            pid = None
    if pid is not None and pid in terminal:
        row = json.loads(line)
        row.update(terminal[pid])
        return json.dumps(row, ensure_ascii=False) + "\n"
    return line.decode("utf-8", "replace") + "\n"


def logical_lines(path: Optional[Path] = None, *, contains: Optional[str] = None) -> Iterator[str]:
    """Each logical row as one JSON text line (with its newline).

    For readers that scan text with a regex or a substring before parsing (the
    health probes, the per-ticker lookups). Legacy: the file's own lines. Streams:
    the forecast line verbatim when the record is open, and re-serialised with
    its terminal event folded in when it is graded or void.

    `contains` keeps only rows whose FORECAST text holds that substring, tested
    before any parsing -- so it must name a frozen field (a ticker, a specialist,
    an observable), never a resolution field, which lives in the events."""
    be = backend_for(path)
    if be.kind == "legacy":
        if not be.legacy_path.exists():
            return
        with be.legacy_path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if contains is None or contains in line:
                    yield line
        return
    if contains is None:
        key = str(be.legacy_path.resolve())
        fp = fingerprint(path)
        with _LOGICAL_CACHE_GUARD:
            hit = _LOGICAL_CACHE.get(key)
        if hit and hit[0] == fp:
            yield from hit[1]
            return
        terminal = _terminal_sets(be)
        out: list[str] = []
        size = 0
        for _, p in stream_files(be, "forecasts"):
            for line in _split_raw_lines(p.read_bytes()):
                if line.strip():
                    text = _fold_line(line, terminal)
                    size += len(text)
                    out.append(text)
        if size <= LOGICAL_CACHE_MAX_BYTES:
            with _LOGICAL_CACHE_GUARD:
                _LOGICAL_CACHE[key] = (fp, tuple(out))
        yield from out
        return
    needle = contains.encode("utf-8")
    terminal = _terminal_sets(be)
    for _, p in stream_files(be, "forecasts"):
        for line in _split_raw_lines(p.read_bytes()):
            if needle in line and line.strip():
                yield _fold_line(line, terminal)


def tail_lines(path: Optional[Path] = None, *, tail_bytes: int) -> list[str]:
    """The newest forecast lines AS MADE, oldest first, ~`tail_bytes` of them.

    For the tail readers that only need what a forecast said and when (the
    accrual canary, the daily review's latest forecasts). Resolution is NOT
    folded in; a caller that needs grades uses `read_rows`. The first line of
    a cut is dropped, since it may be partial."""
    be = backend_for(path)
    if be.kind == "legacy":
        p = be.legacy_path
        if not p.exists():
            return []
        with p.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - tail_bytes))
            lines = fh.read().decode("utf-8", errors="replace").splitlines()
        return lines[1:] if size > tail_bytes and lines else lines
    chunks: list[bytes] = []
    need = tail_bytes
    cut = False
    for _, p in reversed(stream_files(be, "forecasts")):
        size = p.stat().st_size
        with p.open("rb") as fh:
            if size > need:
                fh.seek(size - need)
                chunks.append(fh.read())
                cut = True
                need = 0
            else:
                chunks.append(fh.read())
                need -= size
        if need <= 0:
            break
    lines = b"".join(reversed(chunks)).decode("utf-8", errors="replace").splitlines()
    return lines[1:] if cut and lines else lines


def exists(path: Optional[Path] = None) -> bool:
    be = backend_for(path)
    if be.kind == "legacy":
        return be.legacy_path.exists()
    return bool(stream_files(be, "forecasts"))


def row_count(path: Optional[Path] = None) -> int:
    """Non-empty lines of the forecast side (one per record as made); cheap,
    no parse. The legacy file's line count, or the forecast streams' total."""
    be = backend_for(path)
    files = ([be.legacy_path] if be.kind == "legacy"
             else [p for _, p in stream_files(be, "forecasts")])
    n = 0
    for p in files:
        if p.exists():
            with p.open("rb") as fh:
                n += sum(1 for ln in fh if ln.strip())
    return n


def fingerprint(path: Optional[Path] = None) -> tuple:
    """A cache key that changes whenever any backing file changes."""
    be = backend_for(path)
    if be.kind == "legacy":
        try:
            st = be.legacy_path.stat()
            return ("legacy", st.st_size, st.st_mtime_ns)
        except OSError:
            return ("legacy", None)
    parts: list = ["streams", str(be.marker.get("applied_at_utc") if be.marker else "")]
    for stream in STREAMS:
        for month, p in stream_files(be, stream):
            st = p.stat()
            parts.append((p.name, st.st_size, st.st_mtime_ns))
    return tuple(parts)


def content_digest(path: Optional[Path] = None) -> Optional[str]:
    """sha256 over the ledger's bytes: the legacy file, or every stream file in
    chain order (name + sha256 each). None when nothing exists."""
    be = backend_for(path)
    if be.kind == "legacy":
        return sha256_file(be.legacy_path) if be.legacy_path.exists() else None
    h = hashlib.sha256()
    n = 0
    for month, stream in sorted((m, s) for s in STREAMS for m, _ in stream_files(be, s)):
        p = be.stream_path(stream, month)
        h.update(f"{p.name}:{sha256_file(p)}\n".encode())
        n += 1
    return h.hexdigest() if n else None


# ─────────────────────────────── events ──────────────────────────────────────

def make_event(old: dict, new: dict, *, kind: str, writer: str,
               now: Optional[datetime] = None) -> dict:
    """The event that turns `old` into `new`. Refuses to touch a frozen field.

    A grade may set the resolution fields and may ADD fields the forecast never
    had (a resolver's own detail). It may not change or delete anything the
    forecast was made with: that would be rewriting what was believed."""
    if kind not in EVENT_KINDS:
        raise ForecastLedgerError(f"event kind {kind!r} not in {EVENT_KINDS}")
    pid = old.get("prediction_id")
    if not pid or new.get("prediction_id") != pid:
        raise ForecastLedgerError(
            f"a {kind} event needs the same prediction_id on both rows "
            f"({pid!r} vs {new.get('prediction_id')!r})")
    gone = [k for k in old if k not in new]
    if gone:
        raise ForecastLedgerError(f"{kind} of {pid} would delete field(s) {gone}; events only add")
    changed: dict = {}
    for k, v in new.items():
        if k in old and old[k] == v:
            continue
        if k in old and k not in RESOLUTION_KEYS:
            raise ForecastLedgerError(
                f"{kind} of {pid} would change the frozen forecast field {k!r}; a grade "
                f"may set {sorted(RESOLUTION_KEYS)} or add new fields, never rewrite what "
                f"was forecast")
        changed[k] = v
    if not changed:
        raise ForecastLedgerError(f"{kind} of {pid} changes nothing; no event to record")
    return {"schema": EVENT_SCHEMA, "prediction_id": pid, "event": kind, "set": changed,
            "recorded_at": _iso(now or _now()), "writer": writer,
            "month_basis": "recorded_at"}


# ─────────────────────────────── writing ─────────────────────────────────────

_ID_CACHE: dict[str, tuple[tuple, frozenset]] = {}
_ID_CACHE_GUARD = threading.Lock()


def _ids_in(p: Path, *, terminal: bool) -> frozenset:
    """prediction_ids in one stream file, cached on (size, mtime_ns). A sealed
    month never changes, so only the open month is ever re-read."""
    st = p.stat()
    key = f"{p}|{int(terminal)}"
    stamp = (st.st_size, st.st_mtime_ns)
    with _ID_CACHE_GUARD:
        hit = _ID_CACHE.get(key)
        if hit and hit[0] == stamp:
            return hit[1]
    ids = set()
    for line in _split_raw_lines(p.read_bytes()):
        if not line.strip():
            continue
        try:
            obj = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(obj, dict) and obj.get("prediction_id"):
            if not terminal or obj.get("event") in EVENT_KINDS:
                ids.add(obj["prediction_id"])
    out = frozenset(ids)
    with _ID_CACHE_GUARD:
        _ID_CACHE[key] = (stamp, out)
    return out


def _all_ids(be: Backend, stream: str) -> set:
    ids: set = set()
    for _, p in stream_files(be, stream):
        ids |= _ids_in(p, terminal=(stream == "resolutions"))
    return ids


def sealed_months(be: Backend, stream: str) -> set:
    d = be.manifest_dir
    if not d.is_dir():
        return set()
    out = set()
    for p in d.glob(f"{stream}_*.json"):
        m = re.match(rf"^{stream}_(\d{{4}}-\d{{2}})\.json$", p.name)
        if m:
            out.add(m.group(1))
    return out


def _append_bytes(p: Path, blob: bytes) -> None:
    """Append one batch with one write, then fsync. Refuses to glue a row onto
    a torn tail: a crash mid-append leaves a last line without its newline, and
    the next write must not turn two half-rows into one corrupt one."""
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists() and p.stat().st_size:
        with p.open("rb") as fh:
            fh.seek(-1, 2)
            if fh.read(1) != b"\n":
                raise ForecastLedgerError(
                    f"{rel(p)} ends without a newline (a torn append, most likely a crash "
                    f"mid-write). Nothing was written. Inspect the last line; if it is a "
                    f"fragment, move it aside by hand and record that you did.")
    fd = os.open(str(p), os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0),
                 0o644)
    try:
        view = memoryview(blob)
        while view:
            n = os.write(fd, view)
            view = view[n:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _require_streams(be: Backend, what: str) -> None:
    if be.kind != "streams":
        raise ForecastLedgerError(
            f"{what} writes the monthly streams, but {rel(be.legacy_path)} is answered by "
            f"the legacy backend ({be.reason}); legacy writes go through belief_state")


def append_forecasts(rows: list[dict], path: Optional[Path] = None, *,
                     now: Optional[datetime] = None) -> dict:
    """File forecast rows by their `made_at` month. Dedupes on prediction_id
    across every month, under the ledger lock. Returns a count receipt."""
    be = backend_for(path)
    with ledger_lock(be.root, purpose="append_forecasts"):
        be = backend_for(path)
        _require_streams(be, "append_forecasts")
        run = now or _now()
        known = _all_ids(be, "forecasts")
        sealed = sealed_months(be, "forecasts")
        open_month = month_floor(run)
        if open_month in sealed:
            raise SealRefused(
                f"forecasts_{open_month} is sealed although it is the run clock's month; "
                f"the clock or the seal is wrong. Nothing was written.")
        batches: dict[str, list[bytes]] = {}
        written = dup = late = 0
        for row in rows:
            pid = row.get("prediction_id")
            if not isinstance(pid, str) or not pid:
                raise ForecastLedgerError("a forecast row without a prediction_id cannot be filed")
            if pid in known:
                logger.warning("%s already in the ledger — a duplicate record would be "
                               "scored twice", pid)
                dup += 1
                continue
            made = month_of(row.get("made_at"))
            if made is None:
                raise ForecastLedgerError(
                    f"{pid}: made_at {row.get('made_at')!r} has no YYYY-MM; a forecast is "
                    f"filed by the month it was made and this one cannot be placed")
            target = made
            if made in sealed:
                # A backdated row (a restoration) for a closed month. Filed in the
                # open month so the seal stays true; `made_at` is not touched.
                target = open_month
                late += 1
            batches.setdefault(target, []).append(row_line(row))
            known.add(pid)
            written += 1
        for month in sorted(batches):
            _append_bytes(be.stream_path("forecasts", month), b"".join(batches[month]))
    return {"backend": "streams", "written": written, "skipped_duplicates": dup,
            "late_filed": late, "months": sorted(batches)}


def append_events(events: list[dict], path: Optional[Path] = None, *,
                  now: Optional[datetime] = None) -> dict:
    """Append resolution events to the RECORDING month's stream, under the lock.

    An event for an id that already has a terminal event is skipped and counted
    (first grade wins). An event for an id with no forecast is refused: a grade
    of nothing is a bug upstream, not a fact to file."""
    be = backend_for(path)
    with ledger_lock(be.root, purpose="append_events"):
        be = backend_for(path)
        _require_streams(be, "append_events")
        run = now or _now()
        month = month_floor(run)
        if month in sealed_months(be, "resolutions"):
            raise SealRefused(f"resolutions_{month} is sealed although it is the run clock's "
                              f"month; nothing was written")
        known = _all_ids(be, "forecasts")
        terminal = _all_ids(be, "resolutions")
        lines: list[bytes] = []
        skipped = 0
        for ev in events:
            problem = event_problem(ev)
            if problem:
                raise ForecastLedgerError(f"not a resolution event: {problem}")
            pid = ev["prediction_id"]
            if pid not in known:
                raise ForecastLedgerError(
                    f"a {ev['event']} event for {pid}, which no forecast stream holds; "
                    f"nothing was written")
            if pid in terminal:
                skipped += 1
                continue
            lines.append(row_line(ev))
            terminal.add(pid)
        if lines:
            _append_bytes(be.stream_path("resolutions", month), b"".join(lines))
    return {"backend": "streams", "written": len(lines), "skipped_already_terminal": skipped,
            "month": month}


def legacy_rewrite(path: Path, updates: dict[str, dict]) -> int:
    """Apply terminal updates to the LEGACY file: re-read under the lock, keep
    every row appended meanwhile, never re-grade a row that is already terminal,
    write atomically. Returns how many rows changed."""
    path = Path(path)
    with ledger_lock(path.parent, purpose="legacy_rewrite"):
        be = backend_for(path)
        if be.kind != "legacy":
            raise ForecastLedgerError(
                f"{rel(path)} was migrated to monthly streams ({be.reason}); the legacy "
                f"file is frozen and is never rewritten")
        rows = _read_legacy(path, strict=True)
        n = 0
        out = []
        for r in rows:
            u = updates.get(r.get("prediction_id"))
            if u is not None and r.get("outcome") is None and not r.get("void_reason"):
                r = u
                n += 1
            out.append(r)
        if n:
            atomic_write_text(path, "\n".join(json.dumps(r, ensure_ascii=False)
                                              for r in out) + "\n")
        return n


def record_terminal(path: Optional[Path], pairs: list[tuple[dict, dict]], *, kind: str,
                    writer: str, now: Optional[datetime] = None) -> dict:
    """Record grades or voids, whichever backend answers. `pairs` are
    (row as read, row as graded/voided). Returns {backend, written, ...}."""
    path = Path(path) if path is not None else default_legacy_path()
    if not pairs:
        return {"backend": backend_for(path).kind, "written": 0}
    with ledger_lock(path.parent, purpose=f"record_{kind}"):
        be = backend_for(path)
        if be.kind == "legacy":
            n = legacy_rewrite(path, {new["prediction_id"]: new for _, new in pairs})
            return {"backend": "legacy", "written": n}
        events = [make_event(old, new, kind=kind, writer=writer, now=now) for old, new in pairs]
        out = append_events(events, path, now=now)
        return out


# ─────────────────────────────── sealing ─────────────────────────────────────

def manifest_hash(man: dict) -> str:
    body = {k: v for k, v in man.items() if k != "manifest_sha256"}
    return sha256_bytes(canonical_json(body).encode("utf-8"))


def describe_stream_file(p: Path, stream: str, month: str) -> dict:
    """Facts a manifest records about one stream file. Refuses a file that is
    not a clean LF JSONL of the right kind (a seal over a torn file is a lie)."""
    raw = p.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise SealRefused(f"{rel(p)} ends without a newline (torn tail); not sealed")
    if b"\r" in raw:
        raise SealRefused(f"{rel(p)} contains CR bytes; streams are LF-only. Not sealed")
    lines = _split_raw_lines(raw)
    ids: list[str] = []
    kinds: dict[str, int] = {}
    late = 0
    for i, line in enumerate(lines, 1):
        try:
            obj = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SealRefused(f"{rel(p)}:{i} is not valid JSON ({exc}); not sealed") from exc
        if not isinstance(obj, dict) or not obj.get("prediction_id"):
            raise SealRefused(f"{rel(p)}:{i} has no prediction_id; not sealed")
        ids.append(obj["prediction_id"])
        if stream == "resolutions":
            problem = event_problem(obj)
            if problem:
                raise SealRefused(f"{rel(p)}:{i}: {problem}; not sealed")
            kinds[obj["event"]] = kinds.get(obj["event"], 0) + 1
        elif month_of(obj.get("made_at")) != month:
            late += 1
    out = {"rows": len(lines), "bytes": len(raw), "sha256": sha256_bytes(raw),
           "first_id": ids[0] if ids else None, "last_id": ids[-1] if ids else None,
           "line_endings": "LF"}
    if stream == "resolutions":
        out["events_by_kind"] = dict(sorted(kinds.items()))
    else:
        out["rows_made_in_another_month"] = late
    return out


def _load_manifests(be: Backend) -> list[dict]:
    out = []
    d = be.manifest_dir
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.json")):
        m = re.match(r"^(forecasts|resolutions)_(\d{4}-(?:0[1-9]|1[0-2]))\.json$", p.name)
        if not m:
            continue
        try:
            man = json.loads(p.read_bytes().decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            man = {"_unreadable": f"{type(exc).__name__}: {exc}"}
        man["_file"] = p
        man["_stream"], man["_month"] = m.group(1), m.group(2)
        out.append(man)
    return sorted(out, key=lambda x: _chain_key(x["_stream"], x["_month"]))


def verify_chain(path: Optional[Path] = None, *, rehash: bool = True) -> dict:
    """Is every sealed month still what its manifest says, and is the chain whole?

    Checks, per manifest in chain order: it parses; its own hash matches its
    content; it points at the previous manifest's hash (genesis: null, and it
    carries `legacy_chain_break` when the ledger was migrated); its stream file
    exists and (with `rehash`) still has the recorded bytes, sha256 and rows.
    Also: no stream file of a month at or before the chain's tail is unsealed
    (a gap means a month was skipped, and a later seal would hide it)."""
    be = backend_for(path)
    if be.kind != "streams":
        return {"status": "NOT_APPLICABLE", "backend": be.kind, "reason": be.reason,
                "manifests": 0}
    mans = _load_manifests(be)
    problems: list[str] = []
    prev: Optional[dict] = None
    for i, man in enumerate(mans):
        name = man["_file"].name
        if "_unreadable" in man:
            problems.append(f"{name}: unreadable ({man['_unreadable']})")
            prev = None
            continue
        body = {k: v for k, v in man.items() if not k.startswith("_")}
        if body.get("schema") != MANIFEST_SCHEMA:
            problems.append(f"{name}: schema {body.get('schema')!r} is not {MANIFEST_SCHEMA}")
        if body.get("manifest_sha256") != manifest_hash(body):
            problems.append(f"{name}: its content does not hash to its manifest_sha256 "
                            f"(the manifest was edited after sealing)")
        want_prev = prev.get("manifest_sha256") if prev else None
        if body.get("prev_manifest_sha256") != want_prev:
            problems.append(f"{name}: prev_manifest_sha256 {str(body.get('prev_manifest_sha256'))[:12]} "
                            f"does not match the previous manifest "
                            f"({str(want_prev)[:12] if want_prev else 'none: this is genesis'})")
        if i == 0 and (be.marker or {}).get("migrated_from_legacy") and not body.get("legacy_chain_break"):
            problems.append(f"{name}: the genesis manifest of a migrated ledger carries no "
                            f"legacy_chain_break record")
        f = be.stream_path(man["_stream"], man["_month"])
        if not f.exists():
            problems.append(f"{name}: its stream file {rel(f)} is missing")
        elif rehash:
            raw = f.read_bytes()
            if len(raw) != body.get("bytes") or sha256_bytes(raw) != body.get("sha256"):
                problems.append(f"{name}: {rel(f)} no longer hashes to the sealed sha256 "
                                f"{str(body.get('sha256'))[:12]} ({len(raw)} bytes vs "
                                f"{body.get('bytes')}); a SEALED month changed")
            elif len(_split_raw_lines(raw)) != body.get("rows"):
                problems.append(f"{name}: row count changed")
        prev = body
    tail = _chain_key(mans[-1]["_stream"], mans[-1]["_month"]) if mans else None
    sealed = {(m["_stream"], m["_month"]) for m in mans}
    gaps = []
    if tail is not None:
        for stream in STREAMS:
            for month, p in stream_files(be, stream):
                if (stream, month) not in sealed and _chain_key(stream, month) <= tail:
                    gaps.append(p.name)
    if gaps:
        problems.append(f"unsealed stream file(s) at or before the chain tail: {gaps}")
    return {"status": "ok" if not problems else "BROKEN", "backend": "streams",
            "manifests": len(mans), "rehashed": rehash, "problems": problems,
            "tail": (f"{mans[-1]['_stream']}_{mans[-1]['_month']}" if mans else None),
            "tail_manifest_sha256": (mans[-1].get("manifest_sha256") if mans else None)}


def seal_closed(path: Optional[Path] = None, *, now: Optional[datetime] = None,
                apply: bool = False, provenance: Optional[dict] = None) -> dict:
    """Seal every closed (past-grace) month that has a stream file and no
    manifest, in chain order. Refuses -- writing nothing -- when the existing
    chain does not verify or a candidate would land before the chain's tail.

    Attended: run `--seal` to see the plan, `--seal --apply` to write, then
    commit the manifests and the sealed stream files."""
    be = backend_for(path)
    run = now or _now()
    with ledger_lock(be.root, purpose="seal"):
        be = backend_for(path)
        _require_streams(be, "seal_closed")
        chain = verify_chain(path, rehash=True)
        if chain["status"] != "ok":
            raise SealRefused("the existing manifest chain does not verify; nothing sealed:\n  "
                              + "\n  ".join(chain["problems"]))
        mans = _load_manifests(be)
        sealed = {(m["_stream"], m["_month"]) for m in mans}
        tail = _chain_key(mans[-1]["_stream"], mans[-1]["_month"]) if mans else None
        prev_hash = mans[-1].get("manifest_sha256") if mans else None
        cands = sorted(((stream, month, p) for stream in STREAMS
                        for month, p in stream_files(be, stream)
                        if (stream, month) not in sealed and is_sealable_month(month, run)),
                       key=lambda c: _chain_key(c[0], c[1]))
        for stream, month, p in cands:
            if tail is not None and _chain_key(stream, month) <= tail:
                raise SealRefused(f"{p.name} is unsealed but precedes the chain tail; sealing it "
                                  f"now would break chain order. Nothing sealed.")
        planned = []
        marker = be.marker or {}
        for stream, month, p in cands:
            facts = describe_stream_file(p, stream, month)
            man: dict = {"schema": MANIFEST_SCHEMA, "stream": stream, "month": month,
                         "path": rel(p), **facts,
                         "prev_manifest_sha256": prev_hash,
                         "sealed_at_utc": _iso(run),
                         "dated_by": "the run clock and each row's own stamp; never a file mtime",
                         "provenance": {"tool": "backend.services.forecast_ledger.seal_closed",
                                        "migration_version": marker.get("migration_version"),
                                        **(provenance or {})}}
            if prev_hash is None:
                man["genesis"] = True
                if marker.get("legacy_chain_break"):
                    man["legacy_chain_break"] = marker["legacy_chain_break"]
                if marker.get("source"):
                    man["provenance"]["legacy_source"] = marker["source"]
            man["manifest_sha256"] = manifest_hash(man)
            planned.append({"manifest": rel(be.manifest_path(stream, month)), **{
                k: man[k] for k in ("stream", "month", "rows", "bytes", "sha256",
                                    "prev_manifest_sha256", "manifest_sha256")}})
            if apply:
                atomic_write_bytes(be.manifest_path(stream, month),
                                   (json.dumps(man, indent=1, ensure_ascii=False) + "\n")
                                   .encode("utf-8"))
            prev_hash = man["manifest_sha256"]
    return {"apply": apply, "utc": _iso(run), "sealed" if apply else "would_seal": planned,
            "status": "OK", "next": ("git add the manifests and the sealed stream files, then commit"
                                     if apply and planned else None)}


# ─────────────────────────────── status ──────────────────────────────────────

def status(path: Optional[Path] = None, *, rehash: bool = False,
           now: Optional[datetime] = None) -> dict:
    """Which backend answers, what it holds, and whether its seals hold.

    Cheap by default (no full read, no re-hash); `rehash=True` re-hashes every
    sealed file. DEGRADED when the chain is broken, a closed month is past its
    grace and unsealed, or stream files exist beside an unmigrated legacy file
    (an interrupted `--apply`)."""
    be = backend_for(path)
    run = now or _now()
    out: dict = {**be.describe(), "marker": rel(marker_path(be.legacy_path))}
    problems: list[str] = []
    if be.kind == "legacy":
        out["legacy_exists"] = be.legacy_path.exists()
        out["legacy_bytes"] = be.legacy_path.stat().st_size if out["legacy_exists"] else None
        strays = [p.name for s in STREAMS for _, p in stream_files(be, s)]
        if strays:
            problems.append(f"stream files exist but no marker: {strays[:6]} -- an interrupted "
                            f"`scripts.ledger_split --apply`? Readers use the legacy file")
        out["next"] = ("python -m scripts.ledger_split --plan  (attended migration; "
                       "the legacy file stays the ledger until --apply)")
    else:
        files = []
        for stream in STREAMS:
            sealed = sealed_months(be, stream)
            for month, p in stream_files(be, stream):
                st = p.stat()
                files.append({"file": rel(p), "stream": stream, "month": month,
                              "bytes": st.st_size, "sealed": month in sealed})
                if month not in sealed and is_sealable_month(month, run):
                    problems.append(f"{p.name} is closed and past its grace but not sealed "
                                    f"(python -m backend.services.forecast_ledger --seal --apply)")
        out["files"] = files
        chain = verify_chain(path, rehash=rehash)
        out["chain"] = {k: chain[k] for k in ("status", "manifests", "rehashed", "tail",
                                               "problems")}
        if chain["status"] != "ok":
            problems.extend(chain["problems"])
        if be.legacy_path.exists() and rehash:
            same = sha256_file(be.legacy_path) == (be.marker or {}).get("legacy_sha256")
            out["legacy_frozen_intact"] = same
            if not same:
                problems.append(f"{rel(be.legacy_path)} changed after the migration froze it: "
                                f"a writer that bypassed this module (or old code) appended to it")
    out["status"] = "ok" if not problems else "DEGRADED"
    out["problems"] = problems
    return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="forecast_ledger", description=__doc__.split("\n\n")[0])
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--verify", action="store_true", help="re-hash every sealed month")
    ap.add_argument("--seal", action="store_true", help="list closed months to seal")
    ap.add_argument("--apply", action="store_true", help="with --seal: write the manifests")
    ap.add_argument("--ledger", default=None, help="logical ledger path (default: config)")
    a = ap.parse_args(argv)
    path = Path(a.ledger) if a.ledger else None
    try:
        if a.seal:
            print(json.dumps(seal_closed(path, apply=a.apply), indent=1, default=str))
            return 0
        if a.verify:
            res = verify_chain(path, rehash=True)
            print(json.dumps(res, indent=1, default=str))
            return 0 if res["status"] in ("ok", "NOT_APPLICABLE") else 1
        res = status(path, rehash=False)
        print(json.dumps(res, indent=1, default=str))
        return 0 if res["status"] == "ok" else 1
    except ForecastLedgerError as exc:
        print(f"REFUSED: {exc}")
        return 2


if __name__ == "__main__":
    if str(_repo_root()) not in sys.path:
        sys.path.insert(0, str(_repo_root()))
    raise SystemExit(main())
