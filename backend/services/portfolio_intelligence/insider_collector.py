"""
TRIAL-INSIDER-IC — forward collector for the opportunistic open-market buy signal.

Starts (and keeps) the forward information-coefficient clock: each run snapshots a
per-ticker opportunistic-buy score (`insider_opp:{ticker}`) into the point-in-time
store, stamped `observed_at`=now. Leak-safe by construction — we only ever record
what is knowable today; forward IC later correlates each snapshot with the return
AFTER it. See `docs/TRIALS/TRIAL-INSIDER-IC.md`.

Descriptive only: writes to `pit_observations`, never arms a lane, never sizes a
position, never enters `paper_nav`. Same envelope as the LPPLS/fragility evals.

v1 universe = the 12-name book (the conviction-comparison cross-section, where
insider buys are strongest). Small-N is honest and reported, not hidden; widening
to a small-cap watchlist is a future step. Cadence is weekly (insider holdings move
slowly), throttled internally so wiring into the daily check is cheap.

Network: `fetch_open_market_buys` hits SEC EDGAR with hard per-request timeouts; a
failed ticker degrades to a zero score (never raises, never hangs). Tests inject a
stub `fetch` so they stay offline.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from backend.config import book_lanes
from backend.db import get_connection, snapshot
from backend.services.insider_form4 import fetch_open_market_buys
from backend.services.insider_trading import compute_opportunistic_buy_score

logger = logging.getLogger(__name__)

KEY_PREFIX = "insider_opp:"
THROTTLE_DAYS = 5  # skip if we already collected within this window (weekly cadence)


def book_universe() -> list[str]:
    """The book holdings — the v1 insider-IC cross-section."""
    return sorted((book_lanes.get("holdings") or {}).keys())


def _last_collection_as_of(conn) -> str | None:
    row = conn.execute(
        "SELECT MAX(as_of) AS d FROM pit_observations WHERE key LIKE ?",
        (KEY_PREFIX + "%",),
    ).fetchone()
    return row["d"] if row and row["d"] else None


def collect_insider_opp_scores(db_path=None, tickers=None, *, fetch=None,
                               as_of=None, throttle_days=THROTTLE_DAYS) -> dict:
    """Snapshot the opportunistic-buy score for each ticker into the PIT store.

    Idempotent (``snapshot`` no-ops on an unchanged value) and throttled (skips if
    the last collection was within ``throttle_days``). Returns a summary dict.
    ``fetch`` defaults to the live SEC Form 4 fetcher; tests inject a stub.
    """
    tickers = tickers if tickers is not None else book_universe()
    fetch = fetch or fetch_open_market_buys
    as_of = as_of or date.today().isoformat()

    conn = get_connection(db_path)
    try:
        last = _last_collection_as_of(conn)
        if last is not None and throttle_days > 0:
            try:
                if date.fromisoformat(as_of) - date.fromisoformat(last) < timedelta(days=throttle_days):
                    return {"status": "throttled", "last_as_of": last, "n": 0}
            except ValueError:
                pass  # malformed stored date — fall through and collect

        # UTC to match the leak-safe read cutoff (get_*_observable use UTC now);
        # a local-time stamp ahead of UTC would make the row unreadable.
        observed = datetime.now(timezone.utc).isoformat()
        scores: dict[str, float] = {}
        written = 0
        for t in tickers:
            try:
                data = fetch(t)
            except Exception as e:  # never let one ticker break the run
                logger.warning("insider fetch failed for %s: %s", t, e)
                data = None
            s = compute_opportunistic_buy_score(data)
            scores[t] = s["opp_score"]
            rid = snapshot(
                conn, KEY_PREFIX + t, as_of, float(s["opp_score"]),
                source="sec_form4", observed_at=observed,
                payload={"n_distinct_buyers": s["n_distinct_buyers"],
                         "buy_value": s["buy_value"], "cluster_buy": s["cluster_buy"]},
            )
            if rid is not None:
                written += 1
        nonzero = sum(1 for v in scores.values() if v > 0)
        logger.info("insider-IC collect: %d tickers, %d written, %d non-zero (as_of %s)",
                    len(tickers), written, nonzero, as_of)
        return {"status": "collected", "as_of": as_of, "n": len(tickers),
                "written": written, "nonzero": nonzero, "scores": scores}
    finally:
        conn.close()
