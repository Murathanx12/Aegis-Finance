"""
Aegis Finance — Point-in-time data collectors (V3 data layer)
=============================================================

Collectors fetch external data API-first and persist it into the point-in-time
store (``backend.db.snapshot``) with the correct ``as_of`` vs ``observed_at``, so
every downstream read is leak-free. See ``docs/V3_DATA_LAYER_DESIGN.md``.

First collector — **SEC EDGAR 13F institutional-filing activity** ("track the big
players"). For each tracked institution it records WHEN it filed its latest 13F
and for WHICH reporting period. The legal ~45-day disclosure lag is captured
natively, not approximated:

    as_of       = period of report  (the quarter the holdings refer to)
    observed_at = filing date       (when it became public on EDGAR — the
                                     earliest anyone, including us, could know it)

Using the filing date (not collector-run time) as ``observed_at`` keeps the store
honest even if the collector runs late or backfills. Holdings infotable
extraction is a deliberate follow-on (Chunk 2b); this establishes the cadence
signal and the collector pattern end-to-end.

Honesty note: 13F data is descriptive/positioning context on a long legal lag —
it is NEVER a timing signal and never arms a lane.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

from backend.db import get_connection, snapshot
from backend.services import edgar_events

logger = logging.getLogger(__name__)

# Starter watchlist of notable 13F filers (institution name → SEC CIK).
# Configurable; CIKs are verified against live EDGAR by the slow integration test
# before any live run. Expand via config later (V3).
TRACKED_INSTITUTIONS: dict[str, int] = {
    "Berkshire Hathaway": 1067983,
    "Scion Asset Management": 1649339,
}


def latest_13f_filing(cik: int) -> dict | None:
    """Most recent 13F-HR filing for an institutional filer CIK, or None.

    Returns ``{accession, form, report_date, filing_date, primary_doc_url}``.
    Reuses the rate-limited, cached EDGAR submissions fetch in ``edgar_events``.
    """
    sub = edgar_events._fetch_submissions(cik)
    if not sub:
        return None
    recent = (sub.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    accessions = recent.get("accessionNumber") or []
    filed = recent.get("filingDate") or []
    report = recent.get("reportDate") or []
    primary = recent.get("primaryDocument") or []

    best: dict | None = None
    for i, form in enumerate(forms):
        # 13F-HR (holdings report) and 13F-HR/A (amendment) both qualify.
        if not str(form).startswith("13F-HR"):
            continue
        filing_date = filed[i] if i < len(filed) else ""
        report_date = report[i] if i < len(report) else ""
        if not filing_date or not report_date:
            continue
        cand = {
            "accession": accessions[i] if i < len(accessions) else "",
            "form": str(form),
            "report_date": report_date,
            "filing_date": filing_date,
            "primary_doc_url": edgar_events._doc_url(
                cik,
                accessions[i] if i < len(accessions) else "",
                primary[i] if i < len(primary) else "",
            ),
        }
        if best is None or cand["filing_date"] > best["filing_date"]:
            best = cand
    return best


def _quality_warnings(f: dict) -> list[str]:
    """Lightweight data-quality gate for filing metadata — loud, never silent.

    The DataFrame-shaped DataQualityChecker doesn't fit filing metadata, so this
    applies the same staleness/range spirit: nothing dated in the future, and the
    13F lag (report before filing) must not be inverted."""
    warns: list[str] = []
    today = datetime.now(timezone.utc).date().isoformat()
    if f["report_date"] > today:
        warns.append(f"report_date {f['report_date']} is in the future")
    if f["filing_date"] > today:
        warns.append(f"filing_date {f['filing_date']} is in the future")
    if f["report_date"] > f["filing_date"]:
        warns.append(
            f"report_date {f['report_date']} after filing_date {f['filing_date']} "
            "(13F lag inverted)"
        )
    return warns


def collect_institution_13f(
    conn: sqlite3.Connection, name: str, cik: int
) -> int | None:
    """Fetch the latest 13F filing for one institution and persist it to the PIT
    store. Returns the new row id, or None (no filing found, or unchanged)."""
    f = latest_13f_filing(cik)
    if f is None:
        logger.info("no 13F-HR found for %s (CIK %s)", name, cik)
        return None
    for w in _quality_warnings(f):
        logger.warning("13F quality [%s CIK %s]: %s", name, cik, w)
    return snapshot(
        conn,
        key=f"13f:{cik}:filing",
        as_of=f["report_date"],
        value=None,
        source="edgar",
        payload={"institution": name, **f},
        observed_at=f["filing_date"],
    )


def collect_all_13f(
    conn: sqlite3.Connection | None = None,
    institutions: dict[str, int] | None = None,
) -> dict:
    """Run the 13F collector across the tracked institutions.

    Each institution is isolated: a failure is logged loudly and reported in the
    return value — never silently swallowed, never aborting the batch (the
    silent-fragility class this project guards against)."""
    institutions = institutions or TRACKED_INSTITUTIONS
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    recorded: list[str] = []
    unchanged: list[str] = []
    errors: list[dict] = []
    try:
        for name, cik in institutions.items():
            try:
                rid = collect_institution_13f(conn, name, cik)
                (recorded if rid is not None else unchanged).append(name)
            except Exception as e:  # isolate per-institution; degrade LOUD
                logger.warning("13F collect failed for %s (CIK %s): %s", name, cik, e)
                errors.append({"institution": name, "error": str(e)})
    finally:
        if own_conn:
            conn.close()
    return {"recorded": recorded, "unchanged": unchanged, "errors": errors}
