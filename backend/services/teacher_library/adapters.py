"""TEACHER-LIBRARY-1 — source adapters.

One interface, many sources. The point of the interface is that adding the
ninth source is an adapter and not an architecture, and that every source is
forced through the same tri-state honesty on the way in.

An adapter's job is narrow: fetch, parse, and emit `TeacherEvent`s with correct
timestamps and provenance. Adapters do not score, do not join outcomes, and do
not decide what is interesting.

FORM 4 IS FIRST BECAUSE THE INFRASTRUCTURE ALREADY EXISTS
=========================================================
`insider_form4.fetch_open_market_buys` is reused, not reimplemented. It already
handles the SEC rate limiter, the mandatory User-Agent, the 403 retry, the XML
parsing and — since the Track E prerequisite landed — the tri-state contract.
A second insider parser would be a second thing to keep correct, and the first
one has receipts.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Protocol

from . import events as E
from .events import TeacherEvent, sha256_of

logger = logging.getLogger(__name__)

PARSER_VERSION = "form4-adapter-1.0.0"


class SourceAdapter(Protocol):
    """What every teacher source must provide."""

    source_name: str

    def fetch(self, subject: str, **kw) -> dict:
        """Raw payload plus a tri-state `status`. Never raises for data reasons."""

    def to_events(self, payload: dict) -> list[TeacherEvent]:
        """Canonical events. A failed payload yields a status row, not silence."""


def _status_row(source: str, subject: str, status: str, reason: str,
                actor_type: str, fetched_at: str) -> TeacherEvent:
    """A row that records a FAILURE as a fact.

    Emitting nothing on failure is how a broken feed becomes a quiet week. The
    row is not usable (its status keeps it out of `events_asof`) but it is
    counted in `coverage`, so the difference shows up in the one place someone
    looks.
    """
    return TeacherEvent(
        source=source,
        source_event_id=f"{subject}:{status}:{fetched_at}",
        actor_id=f"unresolved:{subject}",
        actor_type=actor_type,
        action_type="OTHER",
        ticker_at_event=subject.upper(),
        status=status,
        reason=reason,
        fetched_at=fetched_at,
        observed_at=fetched_at,
        parser_version=PARSER_VERSION,
    )


class Form4Adapter:
    """SEC Form 4 open-market purchases → `TeacherEvent`.

    `public_at` is the FILING date, not the transaction date. That is the
    earliest moment anyone outside the company could act on it, and Section 16
    allows two business days between the two — the gap is real, routinely
    non-zero, and is exactly the quantity the copyability question turns on.
    """

    source_name = "sec_form4"

    def __init__(self, fetch=None):
        from backend.services.insider_form4 import fetch_open_market_buys
        self._fetch = fetch or fetch_open_market_buys

    def fetch(self, subject: str, **kw) -> dict:
        return self._fetch(subject, **kw)

    def to_events(self, payload: dict) -> list[TeacherEvent]:
        ticker = str(payload.get("ticker", "")).upper()
        fetched = datetime.now(timezone.utc).isoformat(timespec="seconds")
        status = payload.get("status")

        if status == E.UNAVAILABLE:
            return [_status_row(self.source_name, ticker, E.UNAVAILABLE,
                                str(payload.get("reason", "unavailable")),
                                E.ACTOR_CORPORATE_INSIDER, fetched)]
        if status == E.OK_EMPTY:
            return [_status_row(self.source_name, ticker, E.OK_EMPTY,
                                str(payload.get("reason", "empty")),
                                E.ACTOR_CORPORATE_INSIDER, fetched)]

        out: list[TeacherEvent] = []
        for i, b in enumerate(payload.get("buys") or []):
            filed = b.get("filing_date") or ""
            txn = b.get("date") or ""
            owner_cik = str(b.get("cik") or "").strip()
            name = str(b.get("name") or "Unknown").strip()

            # Identity quality is recorded, not assumed. A Form 4 without an
            # owner CIK can only be keyed on a name string, and name strings
            # collide — "SMITH JOHN" is not an identifier. Saying so here is
            # what lets a later actor-history feature refuse to build on it.
            if owner_cik:
                actor_id = f"cik:{owner_cik}"
                identity_quality = "cik"
            else:
                actor_id = f"name:{name.lower()}"
                identity_quality = "name_only"

            flags: list[str] = []
            if not filed:
                flags.append("no_filing_date")
            if payload.get("partial"):
                flags.append("source_partial_lower_bound")

            try:
                ev = TeacherEvent(
                    source=self.source_name,
                    source_event_id=f"{ticker}:{filed}:{owner_cik or name}:{i}",
                    actor_id=actor_id,
                    actor_name=name,
                    actor_type=E.ACTOR_CORPORATE_INSIDER,
                    action_type="BUY",
                    ticker_at_event=ticker,
                    security_id=ticker,
                    # THE SIGNAL TIMESTAMP. Filing, never transaction.
                    public_at=filed or None,
                    filed_at=filed or None,
                    transaction_at=txn or None,
                    shares=float(b.get("shares") or 0) or None,
                    reported_price=(
                        float(b["value"]) / float(b["shares"])
                        if b.get("shares") else None),
                    filing_type="4",
                    status=E.OK_DATA if filed else E.PARSE_ERROR,
                    reason="" if filed else "no_filing_date_on_transaction",
                    source_quality="sec_primary",
                    raw_sha256=sha256_of(b),
                    parser_version=PARSER_VERSION,
                    identity_quality=identity_quality,
                    mapping_quality="ticker_at_event",
                    data_quality_flags=flags,
                    fetched_at=fetched,
                )
            except E.TeacherEventInvalid as exc:
                logger.warning("form4 adapter: refusing a row for %s (%s)",
                               ticker, exc)
                out.append(_status_row(self.source_name, ticker, E.PARSE_ERROR,
                                       str(exc)[:200],
                                       E.ACTOR_CORPORATE_INSIDER, fetched))
                continue
            out.append(ev)

        return out or [_status_row(self.source_name, ticker, E.OK_EMPTY,
                                   "no_open_market_purchases",
                                   E.ACTOR_CORPORATE_INSIDER, fetched)]


def ingest(adapter: Any, subjects: list[str], *, path=None, **kw) -> dict:
    """Run one adapter over subjects and append what it produces.

    Data engineering only. No outcome is joined and nothing is scored here.
    """
    from .ledger import append

    produced: list[TeacherEvent] = []
    per_subject: dict[str, str] = {}
    for s in subjects:
        try:
            payload = adapter.fetch(s, **kw)
        except Exception as exc:                               # noqa: BLE001
            logger.warning("%s: fetch raised for %s: %s",
                           adapter.source_name, s, exc)
            payload = {"ticker": s, "status": E.UNAVAILABLE,
                       "reason": f"fetch_raised:{type(exc).__name__}"}
        evs = adapter.to_events(payload)
        per_subject[s] = payload.get("status", "UNKNOWN")
        produced.extend(evs)

    res = append(produced, path=path)
    res["subjects"] = len(subjects)
    res["usable_events"] = sum(1 for e in produced if e.usable)
    res["status_by_subject"] = per_subject
    return res
