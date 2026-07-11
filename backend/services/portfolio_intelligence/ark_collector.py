"""
TRIAL-ARK-IC — daily collector for ARK ETF holdings (raw shares + flow score).
===============================================================================

Phase 1 (immediately): snapshot ``ark_shares:{FUND}:{ticker}`` per fund per
holding, ``as_of`` = the CSV's own file date, deduped on unchanged shares.

Phase 2 (self-arming): once ≥ SCORE_WINDOW_SESSIONS distinct as_of dates have
accrued, also snapshot ``ark_score:{ticker}`` — the frozen 21-session net
share-flow score. Until then the score is UNWRITTEN (an early score would be
false-neutral zeros). See ``docs/TRIALS/TRIAL-ARK-IC.md``. Descriptive only.

One fund failing does not sink the rest, but a run where EVERY fund fails
raises — a dead source must be loud, not a quiet day.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.db import get_connection, snapshot
from backend.services.ark_holdings import (
    FUND_FILES, SCORE_WINDOW_SESSIONS, compute_ark_scores, fetch_fund_holdings,
)

logger = logging.getLogger(__name__)

SHARES_PREFIX = "ark_shares:"
SCORE_PREFIX = "ark_score:"
TRIAL_PARAM = "ark-ic-signal"


def _fund_shares(conn, fund: str, as_of: str) -> dict[str, float]:
    """{ticker: shares} for ONE fund at one as_of date, from the PIT store."""
    rows = conn.execute(
        "SELECT key, value FROM pit_observations "
        "WHERE key LIKE ? AND as_of = ? ORDER BY revision ASC",
        (f"{SHARES_PREFIX}{fund}:%", as_of),
    ).fetchall()  # revisions ascending → the dict keeps the latest
    out: dict[str, float] = {}
    for r in rows:
        _, _, ticker = r["key"].split(":", 2)
        out[ticker] = float(r["value"])
    return out


def _fund_dates(conn, fund: str) -> list[str]:
    """This fund's own distinct as_of dates, newest first."""
    return [row["d"] for row in conn.execute(
        "SELECT DISTINCT as_of AS d FROM pit_observations "
        "WHERE key LIKE ? ORDER BY as_of DESC",
        (f"{SHARES_PREFIX}{fund}:%",),
    ).fetchall()]


def collect_ark_holdings(db_path=None, *, fetch=None) -> dict:
    """Fetch all funds, snapshot raw shares, and (once the baseline exists)
    the flow scores. ``fetch`` defaults to the live CSV fetcher."""
    fetch = fetch or fetch_fund_holdings
    observed = datetime.now(timezone.utc).isoformat()

    all_rows: list[dict] = []
    failures: dict[str, str] = {}
    for fund in FUND_FILES:
        try:
            all_rows.extend(fetch(fund))
        except Exception as e:  # isolate per fund, but never silently
            failures[fund] = str(e)
            logger.error("ARK fetch failed for %s: %s", fund, e)
    if not all_rows:
        raise ValueError(f"ARK collection: ALL funds failed: {failures}")

    conn = get_connection(db_path)
    try:
        written = 0
        for r in all_rows:
            rid = snapshot(
                conn, f"{SHARES_PREFIX}{r['fund']}:{r['ticker']}", r["date"],
                float(r["shares"]), source="ark_funds_csv",
                observed_at=observed, payload={"weight_pct": r["weight_pct"]},
            )
            if rid is not None:
                written += 1

        # Phase 2: flow scores. Baselines are aligned PER FUND — each fund's
        # window is its own 21 published sessions (funds can lag each other a
        # day; a pooled date list would silently vary the frozen window by
        # fund and bias the pre-registered IC). Funds without a full baseline
        # simply don't contribute yet.
        current_map: dict[str, dict[str, float]] = {}
        baseline_map: dict[str, dict[str, float]] = {}
        sessions_by_fund: dict[str, int] = {}
        for fund in FUND_FILES:
            fdates = _fund_dates(conn, fund)
            sessions_by_fund[fund] = len(fdates)
            if len(fdates) > SCORE_WINDOW_SESSIONS:
                current_map[fund] = _fund_shares(conn, fund, fdates[0])
                baseline_map[fund] = _fund_shares(
                    conn, fund, fdates[SCORE_WINDOW_SESSIONS])

        scores_written = 0
        score_status = "accruing_baseline"
        if current_map:
            score_as_of = max(
                _fund_dates(conn, f)[0] for f in current_map)
            scores = compute_ark_scores(current_map, baseline_map)
            for ticker, (value, payload) in scores.items():
                rid = snapshot(
                    conn, SCORE_PREFIX + ticker, score_as_of, value,
                    source="ark_funds_csv", observed_at=observed,
                    payload={**payload,
                             "funds_scored": sorted(current_map)},
                )
                if rid is not None:
                    scores_written += 1
            score_status = "scored"

        summary = {
            "status": "collected", "funds_ok": len(FUND_FILES) - len(failures),
            "funds_failed": failures, "rows": len(all_rows),
            "shares_written": written, "score_status": score_status,
            "scores_written": scores_written,
            "sessions_by_fund": sessions_by_fund,
        }
        logger.info("ARK collect: %s", summary)
        return summary
    finally:
        conn.close()


def ensure_ark_trial(db_path=None) -> int:
    """Idempotently pre-register TRIAL-ARK-IC."""
    from backend.services.portfolio_intelligence.trial_registry import (
        ensure_trial_registered,
    )

    notes = {
            "hypothesis": (
                "ARK's daily share-count flow (21-session net change per "
                "ticker, summed across 6 funds, clipped ±1/fund) has nonzero "
                "forward rank-IC at 21/63/126d — honest prior: weak-to-null, "
                "possibly negative (post-2021 crowding literature)"
            ),
            "purpose": "experimental",
            "canonical_doc": "docs/TRIALS/TRIAL-ARK-IC.md",
            "pre_registered": "2026-07-11",
            "decision_rule": {
                "trial": "TRIAL-ARK-IC",
                "primary_metric": "forward rank-IC (Spearman) at 21/63/126d, "
                                  "block-bootstrap CI",
                "adopt_threshold": "IC != 0 with 95% CI excluding 0 at >=1 "
                                   "horizon over >=6mo, median cross-section "
                                   ">=25; a robust NEGATIVE IC becomes an "
                                   "inverse-reading successor trial, never a "
                                   "silent flip",
                "reject_threshold": "CI covers 0 at all horizons after 12mo "
                                    "of scores",
                "earliest_decision": "6mo after the first ark_score snapshot",
                "params_frozen": "funds ARKK/W/G/Q/F/X, window 21 sessions, "
                                 "clip ±1 per fund, no dollar/fund weighting",
                "crash_event_override": "SPY drawdown >=20% defers decisions "
                                        "until >=6mo past trough",
                "hard_constraint": "descriptive-only; NEVER arms a lane; no "
                                   "buy-sell framing; not in multifactor "
                                   "until adopted",
            },
    }
    return ensure_trial_registered(TRIAL_PARAM, notes, db_path=db_path)
