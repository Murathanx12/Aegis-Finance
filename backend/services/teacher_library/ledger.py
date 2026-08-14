"""TEACHER-LIBRARY-1 — the append-only, point-in-time event ledger.

Append-safe, deduplicated, amendment-aware, and — the part that matters —
**incapable of showing a reader a filing that was not public yet**.

WHY `as_of` IS A REQUIRED ARGUMENT AND NOT A CONVENIENCE
========================================================
Every research question this ledger exists to serve is a question about what was
knowable at a moment. If reading the ledger defaulted to "everything", the
default would be the leaking one, and a leak that comes from a default argument
is invisible in review: the call site looks like ordinary code.

So `events_asof(as_of)` takes the timestamp positionally and filters on
`public_at`. There is deliberately no "give me everything" convenience wrapper.
`all_events()` exists for data engineering, is named to be conspicuous in a
diff, and says in its own docstring that it must not feed a backtest.

AMENDMENTS
==========
Filings get corrected. An amendment does not overwrite its parent — the ledger
is append-only and the original was genuinely what the world saw at the time.
`events_asof` returns the newest version that was public by `as_of`, so a reader
standing before the correction sees the original, exactly as a copy strategy
would have. Rewriting history in place would make yesterday's backtest
irreproducible and would quietly delete the disclosure-quality signal that
"this actor amends often" represents.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from backend import config as _config

from .events import (OK_EMPTY, USABLE_STATUSES, TeacherEvent,
                     TeacherEventInvalid, _parse)

logger = logging.getLogger(__name__)

LEDGER_DIR = _config.OPTIMUS_LEDGER_DIR / "teacher_library"
EVENTS_PATH = LEDGER_DIR / "events.jsonl"

_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_raw(path: Path | None = None) -> Iterator[dict]:
    p = path or EVENTS_PATH
    if not p.exists():
        return
    with open(p, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # A corrupt line is disclosed, not skipped in silence: the
                # telemetry ledger already taught this repo that quietly
                # dropping unreadable rows turns a count into a lower bound
                # that nobody knows is a lower bound.
                logger.error("teacher ledger: line %d of %s is unreadable — "
                             "counts from this file are LOWER BOUNDS", i, p)


def existing_ids(path: Path | None = None) -> set[str]:
    return {r.get("event_id", "") for r in _read_raw(path)} - {""}


def append(events: Iterable[TeacherEvent], *,
           path: Path | None = None) -> dict:
    """Append new events. Idempotent on `event_id`; never rewrites a line.

    Returns a summary rather than nothing, because "how many were actually new"
    is the number that tells you whether a collector is working or re-reading
    the same window forever.
    """
    p = path or EVENTS_PATH
    evs = list(events)
    with _LOCK:
        seen = existing_ids(p)
        fresh, dup = [], 0
        for e in evs:
            eid = e.event_id()
            if eid in seen:
                dup += 1
                continue
            seen.add(eid)
            if not e.observed_at:
                e.observed_at = _now()
            fresh.append(e)
        if fresh:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a", encoding="utf-8") as fh:
                for e in fresh:
                    fh.write(e.to_json() + "\n")
    return {"submitted": len(evs), "written": len(fresh), "duplicates": dup,
            "path": str(p)}


def all_events(path: Path | None = None) -> list[TeacherEvent]:
    """EVERY row, with no point-in-time filter.

    For data engineering, counting and integrity checks ONLY. This must never
    feed a backtest, a copy strategy or a feature — it can see filings that had
    not happened yet at the moment being studied. The name is deliberately
    conspicuous so its appearance in a research diff is a question.
    """
    out = []
    for r in _read_raw(path):
        try:
            out.append(TeacherEvent.from_dict(r))
        except TeacherEventInvalid as exc:
            logger.error("teacher ledger: stored row is invalid (%s) — "
                         "excluded from reads", exc)
    return out


def events_asof(as_of: str | datetime, *, path: Path | None = None,
                usable_only: bool = True,
                actor_types: Iterable[str] | None = None,
                tickers: Iterable[str] | None = None) -> list[TeacherEvent]:
    """Everything that was PUBLIC at `as_of`, newest amendment first.

    The point-in-time read. `as_of` is required and positional; filtering is on
    `public_at`, never on `transaction_at`, so an event disclosed after `as_of`
    is invisible here no matter when it was transacted.
    """
    cutoff = _parse(as_of if isinstance(as_of, str) else as_of.isoformat())
    if cutoff is None:
        raise ValueError(f"as_of {as_of!r} is not a timestamp")

    want_actors = set(actor_types) if actor_types else None
    want_tickers = {t.upper() for t in tickers} if tickers else None

    visible: list[TeacherEvent] = []
    for e in all_events(path):
        pub = _parse(e.public_at)
        if pub is None or pub > cutoff:
            continue
        if usable_only and e.status not in USABLE_STATUSES:
            continue
        if want_actors and e.actor_type not in want_actors:
            continue
        if want_tickers and (e.ticker_at_event or "").upper() not in want_tickers:
            continue
        visible.append(e)

    # An amendment supersedes its parent — but only once IT is public. A reader
    # standing before the correction still sees the original, which is what the
    # world saw.
    superseded = {e.amends_event_id for e in visible if e.amends_event_id}
    latest = [e for e in visible if e.event_id() not in superseded]
    latest.sort(key=lambda e: (_parse(e.public_at) or cutoff, e.event_id()),
                reverse=True)
    return latest


def coverage(path: Path | None = None) -> dict:
    """What is in the ledger, by source, actor type and status.

    Deliberately includes the non-usable rows in the counts. A coverage report
    that only counted OK_DATA would make a source that is failing look like a
    source that is quiet, which is the failure this whole track is built to
    avoid.
    """
    by_source: dict[str, int] = {}
    by_actor: dict[str, int] = {}
    by_status: dict[str, int] = {}
    lags: list[float] = []
    n = 0
    for e in all_events(path):
        n += 1
        by_source[e.source] = by_source.get(e.source, 0) + 1
        by_actor[e.actor_type] = by_actor.get(e.actor_type, 0) + 1
        by_status[e.status] = by_status.get(e.status, 0) + 1
        lag = e.disclosure_lag_days()
        if lag is not None:
            lags.append(lag)
    lags.sort()
    return {
        "n_events": n,
        "by_source": by_source,
        "by_actor_type": by_actor,
        "by_status": by_status,
        "n_with_disclosure_lag": len(lags),
        "disclosure_lag_days_median": (lags[len(lags) // 2] if lags else None),
        "disclosure_lag_days_max": (lags[-1] if lags else None),
        "note": ("counts include non-usable rows on purpose: a source that is "
                 "FAILING must not read as a source that is QUIET"),
    }
