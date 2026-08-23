"""Append-only history of every event Aegis has ever accepted.

WHAT WAS ACTUALLY MISSING
=========================
Measured 2026-08-23, against the assumption that the news engine needed
building: it does not. `event_intel` already classifies news, EDGAR 8-Ks and
earnings into typed events with per-feed canaries, and in production all ten of
`LLM_EVENTS_v1`'s daily beliefs carry `event_coverage: FETCHED` with events
actually shown. The perception layer works end to end.

What it has no trace of is **yesterday**. Events are fetched fresh into each
day's frozen snapshot and then discarded. That makes three things impossible,
and they are exactly the three the learning loop needs:

  NOVELTY      the same headline re-syndicated by four outlets over three days
               reads as four independent events, every day, forever. Novelty is
               not a property of an event -- it is a property of an event
               AGAINST WHAT WAS ALREADY SEEN, so it cannot be computed without
               a history.
  ATTRIBUTION  "which source, event type and horizon actually paid?" needs the
               event to still exist when the outcome matures 20 days later.
  AVAILABILITY the honest question is not "what happened?" but "what could a
               decision at time t have known?" -- which requires the ACCEPTANCE
               timestamp to be recorded separately from the source timestamp
               and never back-dated.

WHY ACCEPTANCE TIME IS SEPARATE FROM SOURCE TIME
================================================
A feed can hand us an item stamped three days ago. Using that stamp to decide
what a decision "knew" would silently backdate information into a past the
model did not have -- lookahead, arriving through the timestamp rather than
through the data. So every record carries BOTH, plus `available_to_decision`,
which is computed from the acceptance clock alone.

WHAT THIS MODULE REFUSES
========================
* back-dating `accepted_at`; it is stamped here, from the wall clock, never
  taken from the payload;
* writing an event with no source and no content hash, because an event that
  cannot be traced or de-duplicated is not evidence;
* answering "is this novel?" against an unwritten history -- an empty store
  returns UNKNOWN, not "novel". The whole novelty concept is meaningless before
  a baseline exists, and reporting everything as novel on day one is how a
  learner concludes its first day was extraordinary.

This is a store, not a signal. Nothing here decides anything.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from backend import config as _config

logger = logging.getLogger(__name__)

ROOT = _config.OPTIMUS_LEDGER_DIR / "events"

_LOCK = threading.Lock()

SCHEMA_VERSION = "event-store-1.0.0"

#: How far back a content hash is remembered for novelty. A month is long
#: enough to catch re-syndication and short enough that an annual filing with
#: the same title is not mistaken for a repeat.
NOVELTY_WINDOW_DAYS = 30


class EventRejected(ValueError):
    """An event that cannot be traced or de-duplicated is not evidence."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _day_path(day: str, root: Path | None = None) -> Path:
    return (root or ROOT) / f"events_{day}.jsonl"


def content_hash(event: dict) -> str:
    """Identity of the CONTENT, deliberately excluding when we saw it.

    Two feeds carrying the same headline about the same company must collide,
    or novelty is meaningless. Acceptance time and feed are therefore NOT in
    the hash -- they are what differs between duplicates.
    """
    src = event.get("source") or {}
    parts = [
        str(event.get("scope") or ""),
        str(event.get("event_type") or ""),
        (str(event.get("title") or "").strip().lower()),
        str(src.get("url") or ""),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _read_day(day: str, root: Path | None = None) -> list[dict]:
    p = _day_path(day, root)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            # One corrupt line must not blind the whole day. Say so loudly.
            logger.error("event_store: unparseable line in %s — skipped", p)
    return out


def recent_hashes(*, days: int = NOVELTY_WINDOW_DAYS,
                  root: Path | None = None,
                  today: date | None = None) -> set[str]:
    """Content hashes seen in the trailing window."""
    today = today or _now().date()
    seen: set[str] = set()
    for i in range(days + 1):
        d = (today - timedelta(days=i)).isoformat()
        for rec in _read_day(d, root):
            h = rec.get("content_hash")
            if h:
                seen.add(h)
    return seen


def novelty_of(event: dict, *, known: set[str] | None = None,
               root: Path | None = None,
               today: date | None = None) -> dict:
    """NEW / REPEAT / UNKNOWN, and why.

    UNKNOWN when the store has no history yet: on an empty store every event
    would otherwise report NEW, which is not a measurement, it is the absence
    of one.
    """
    known = recent_hashes(root=root, today=today) if known is None else known
    h = content_hash(event)
    if not known:
        return {"novelty": "UNKNOWN", "content_hash": h,
                "reason": ("no event history in the novelty window — novelty "
                           "is undefined against an empty baseline")}
    return {"novelty": "REPEAT" if h in known else "NEW",
            "content_hash": h,
            "reason": f"compared against {len(known)} hash(es) in the "
                      f"trailing {NOVELTY_WINDOW_DAYS} days"}


def make_record(event: dict, *, tickers: list[str] | None = None,
                accepted_at: datetime | None = None,
                horizon_days: int | None = None,
                feed_health: str | None = None,
                known: set[str] | None = None,
                root: Path | None = None) -> dict:
    """Turn one `event_intel` event into a durable, traceable record."""
    src = event.get("source") or {}
    title = (event.get("title") or "").strip()
    if not title and not src.get("url"):
        raise EventRejected(
            "event has neither a title nor a URL — nothing to trace it to and "
            "nothing stable to de-duplicate on, so it cannot be evidence")

    # ACCEPTANCE TIME IS OURS. Never taken from the payload: a feed stamp of
    # three days ago would silently backdate information into a decision that
    # did not have it.
    accepted = accepted_at or _now()
    nov = novelty_of(event, known=known, root=root,
                     today=accepted.date())

    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": hashlib.sha256(
            f"{nov['content_hash']}|{accepted.isoformat()}".encode()
        ).hexdigest()[:20],
        "content_hash": nov["content_hash"],
        "entities": sorted(set(tickers or ([event["scope"]]
                                           if event.get("scope") else []))),
        "scope": event.get("scope"),
        "event_type": event.get("event_type"),
        "direction": event.get("direction"),
        "direction_basis": event.get("direction_basis"),
        "source_feed": src.get("feed"),
        "source_url": src.get("url"),
        "source_publisher": src.get("publisher"),
        #: What the SOURCE said about when it happened. May be absent, may be
        #: wrong, may be older than acceptance. Never used for availability.
        "source_timestamp": event.get("timestamp"),
        #: When AEGIS accepted it. The only clock availability is computed on.
        "accepted_at": accepted.isoformat(timespec="seconds"),
        "title": title[:300],
        "extraction_method": (event.get("extraction") or {}).get("method"),
        "extraction_tier": (event.get("extraction") or {}).get("tier"),
        "novelty": nov["novelty"],
        "novelty_reason": nov["reason"],
        "horizon_days": horizon_days,
        "feed_health": feed_health,
        "context": event.get("context") or {},
    }


def append(records: list[dict], *, root: Path | None = None,
           day: str | None = None) -> dict:
    """Append records for one day. Append-only: never rewrites a past day."""
    if not records:
        return {"written": 0, "day": day}
    day = day or records[0]["accepted_at"][:10]
    p = _day_path(day, root)
    with _LOCK:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r, default=str) + "\n")
    return {"written": len(records), "day": day, "path": str(p)}


def ingest_for_tickers(tickers: list[str], *, root: Path | None = None,
                       accepted_at: datetime | None = None) -> dict:
    """Fetch today's events for `tickers` and persist them with provenance.

    Deliberately reuses `event_intel.get_ticker_events` rather than
    reimplementing ingestion: a second event stack is exactly what this
    programme does not need.
    """
    from backend.services.event_intel import get_ticker_events

    accepted = accepted_at or _now()
    known = recent_hashes(root=root, today=accepted.date())
    records, per_ticker, failures = [], {}, {}

    for t in tickers:
        try:
            block = get_ticker_events(t)
        except Exception as e:                                  # noqa: BLE001
            # A dead feed must be VISIBLE, not an empty day. This is the
            # house failure mode: code that runs green and stores nothing.
            logger.error("event_store: ingestion failed for %s: %s", t, e)
            failures[t] = str(e)
            continue
        health = ("degraded" if block.get("unavailable_feeds") else "ok")
        got = 0
        for ev in block.get("events") or []:
            try:
                rec = make_record(ev, tickers=[t], accepted_at=accepted,
                                  feed_health=health, known=known, root=root)
            except EventRejected as e:
                logger.warning("event_store: rejected an event for %s: %s",
                               t, e)
                continue
            records.append(rec)
            known.add(rec["content_hash"])
            got += 1
        per_ticker[t] = got

    written = append(records, root=root,
                     day=accepted.date().isoformat())
    n_new = sum(1 for r in records if r["novelty"] == "NEW")
    return {
        "status": "ok" if not failures else "partial",
        "n_events": len(records),
        "n_new": n_new,
        "n_repeat": sum(1 for r in records if r["novelty"] == "REPEAT"),
        "n_unknown_novelty": sum(1 for r in records
                                 if r["novelty"] == "UNKNOWN"),
        "per_ticker": per_ticker,
        "failures": failures,
        "day": written.get("day"),
        "written": written.get("written", 0),
    }


def available_to_decision(decision_at: str, *, lookback_days: int = 7,
                          root: Path | None = None,
                          entity: str | None = None) -> list[dict]:
    """Every event ACCEPTED strictly before `decision_at`.

    The strictness matters: an event accepted in the same second a decision was
    made was not available to it. Filtering on the acceptance clock -- never
    the source clock -- is what keeps a late-arriving item from backdating
    itself into a decision that never saw it.
    """
    cutoff = datetime.fromisoformat(decision_at)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)
    out = []
    for i in range(lookback_days + 1):
        d = (cutoff.date() - timedelta(days=i)).isoformat()
        for rec in _read_day(d, root):
            try:
                acc = datetime.fromisoformat(rec["accepted_at"])
            except (KeyError, ValueError):
                continue
            if acc.tzinfo is None:
                acc = acc.replace(tzinfo=timezone.utc)
            if acc >= cutoff:
                continue
            if entity and entity not in (rec.get("entities") or []):
                continue
            out.append(rec)
    return sorted(out, key=lambda r: r["accepted_at"], reverse=True)


def health(*, root: Path | None = None, today: date | None = None) -> dict:
    """Is the store accruing, and does it know it?"""
    today = today or _now().date()
    r = root or ROOT
    if not r.exists():
        return {"status": "ABSENT", "n_days": 0, "n_events_window": 0,
                "reason": "no event store on disk — nothing has been ingested"}
    days = sorted(p.stem.replace("events_", "") for p in r.glob("events_*.jsonl"))
    window = [d for d in days
              if (today - date.fromisoformat(d)).days <= NOVELTY_WINDOW_DAYS]
    n = sum(len(_read_day(d, root)) for d in window)
    last = days[-1] if days else None
    quiet = (today - date.fromisoformat(last)).days if last else None
    return {
        "status": "ok" if (quiet is not None and quiet <= 5) else "DEGRADED",
        "n_days": len(days),
        "n_events_window": n,
        "last_day": last,
        "days_quiet": quiet,
        "novelty_window_days": NOVELTY_WINDOW_DAYS,
        "note": ("append-only; accepted_at is stamped on write and never "
                 "back-dated, so availability is computable after the fact"),
    }
