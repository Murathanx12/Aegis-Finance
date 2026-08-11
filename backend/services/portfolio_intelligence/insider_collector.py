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
failed ticker is recorded as UNSCOREABLE and nothing is written for it (never
raises, never hangs, never invents a zero). Tests inject a stub `fetch` so they
stay offline.
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
        scores: dict[str, float | None] = {}
        unscoreable: dict[str, str] = {}
        written = 0
        for t in tickers:
            try:
                data = fetch(t)
            except Exception as e:  # never let one ticker break the run
                logger.warning("insider fetch failed for %s: %s", t, e)
                data = None
            s = compute_opportunistic_buy_score(data)
            scores[t] = s["opp_score"]
            # An unscoreable ticker is NOT a zero. Writing 0.0 for "we could not
            # classify these transactions" would put a fabricated observation
            # into a point-in-time store that later research reads as fact —
            # the same conflation that let an uncoded Finnhub feed report "no
            # open-market purchases" for every ticker on earth (NIGHT-10).
            if s.get("available") is False or s["opp_score"] is None:
                unscoreable[t] = s.get("reason", "unavailable")
                continue
            rid = snapshot(
                conn, KEY_PREFIX + t, as_of, float(s["opp_score"]),
                source="sec_form4", observed_at=observed,
                payload={"n_distinct_buyers": s["n_distinct_buyers"],
                         "buy_value": s["buy_value"], "cluster_buy": s["cluster_buy"]},
            )
            if rid is not None:
                written += 1
        nonzero = sum(1 for v in scores.values() if v)
        if unscoreable:
            logger.warning("insider-IC collect: %d of %d tickers UNSCOREABLE "
                           "(nothing written for them): %s", len(unscoreable),
                           len(tickers), dict(list(unscoreable.items())[:5]))
        logger.info("insider-IC collect: %d tickers, %d written, %d non-zero, "
                    "%d unscoreable (as_of %s)",
                    len(tickers), written, nonzero, len(unscoreable), as_of)
        return {"status": "collected", "as_of": as_of, "n": len(tickers),
                "written": written, "nonzero": nonzero, "scores": scores,
                "unscoreable": unscoreable}
    finally:
        conn.close()
