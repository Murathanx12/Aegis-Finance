"""
TRIAL-CONGRESS-IC — forward collector for congressional (STOCK Act) trades.
============================================================================

Snapshots ``congress_score:{ticker}`` (net distinct-member purchases over 90d
of DISCLOSURES — knowledge time, never transaction time) into the PIT store,
weekly-throttled, leak-safe. Universe = the 150 most-active tickers by
in-window trade count (frozen) — this is also the first collector whose
cross-section is not limited to the ~12 book names. Descriptive only.
See ``docs/TRIALS/TRIAL-CONGRESS-IC.md``.

A full source failure RAISES before any PIT write (the scheduler logs it
loudly) — a broken feed must never write a cross-section of false zeros.
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from backend.services.congress_trades import (
    WINDOW_DAYS, active_universe, compute_congress_scores,
    fetch_congress_trades,
)
from backend.services.portfolio_intelligence.pit_score_collector import (
    collect_pit_scores,
)

logger = logging.getLogger(__name__)

KEY_PREFIX = "congress_score:"
TRIAL_PARAM = "congress-ic-signal"


def collect_congress_scores(db_path=None, tickers=None, *, fetch=None,
                            as_of=None, throttle_days=5) -> dict:
    """Snapshot the congressional-trading score into the PIT store.
    ``fetch`` defaults to the live FMP fetcher; tests inject a stub."""
    fetch = fetch or fetch_congress_trades
    aso = as_of or date.today().isoformat()

    trades = fetch(window_days=WINDOW_DAYS, as_of=aso)  # raises on source failure
    scores = compute_congress_scores(trades, as_of=aso, window_days=WINDOW_DAYS)
    universe = tickers if tickers is not None else active_universe(scores)

    def _score_for(ticker: str) -> tuple[float, dict]:
        value, payload = scores.get(ticker, (0.0, {"n_trades": 0}))
        return value, payload

    return collect_pit_scores(
        key_prefix=KEY_PREFIX, source="fmp_congress",
        score_for_ticker=_score_for, tickers=universe,
        db_path=db_path, as_of=aso, throttle_days=throttle_days,
    )


def ensure_congress_trial(db_path=None) -> int:
    """Idempotently pre-register TRIAL-CONGRESS-IC in the experiment registry
    (pattern: ensure_lppls_trial). Entering the cumulative count makes the
    DSR/PBO guards stricter — the conservative direction."""
    import json as _json

    from backend.db import count_cumulative_trials, get_connection, init_db

    init_db(db_path)
    conn = get_connection(db_path)
    try:
        existing = conn.execute(
            "SELECT id FROM rule_experiments WHERE param = ? ORDER BY id LIMIT 1",
            (TRIAL_PARAM,),
        ).fetchone()
        if existing is not None:
            return int(existing["id"])
        cumulative = count_cumulative_trials(conn) + 1
        notes = {
            "hypothesis": (
                "Per-ticker net distinct-member congressional purchase score "
                "(90d of STOCK Act disclosures, by disclosureDate) has positive "
                "forward rank-IC at 21/63/126d — honest prior: weak-to-null, "
                "post-STOCK-Act literature finds the edge largely faded"
            ),
            "purpose": "experimental",
            "canonical_doc": "docs/TRIALS/TRIAL-CONGRESS-IC.md",
            "pre_registered": "2026-07-11",
            "decision_rule": {
                "trial": "TRIAL-CONGRESS-IC",
                "primary_metric": "forward rank-IC (Spearman) at 21/63/126d, "
                                  "block-bootstrap CI",
                "adopt_threshold": "IC > 0 with 95% CI excluding 0 at >=1 "
                                   "horizon over >=6mo, median cross-section "
                                   ">=30 names, then evaluate_candidate",
                "reject_threshold": "CI covers 0 at all horizons after 12mo, "
                                    "or median cross-section <10 for 3mo",
                "earliest_decision": "2027-01-11",
                "evaluation_cadence": "monthly reads, reported only",
                "params_frozen": "window 90d, universe cap 150, distinct-member "
                                 "counting, FMP both chambers, no amount weights",
                "crash_event_override": "SPY drawdown >=20% defers decisions "
                                        "until >=6mo past trough",
                "hard_constraint": "descriptive-only; NEVER arms a lane; no "
                                   "buy-sell framing; not in multifactor until "
                                   "adopted",
            },
        }
        cur = conn.execute(
            "INSERT INTO rule_experiments "
            "(created_at, config_version, lane_id, param, old_value, new_value, "
            " batch_trials, cumulative_trials, verdict, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (datetime.now().isoformat(), "descriptive", None, TRIAL_PARAM,
             None, "registered", 1, cumulative, "adopted", _json.dumps(notes)),
        )
        conn.commit()
        logger.info("Pre-registered TRIAL-CONGRESS-IC (cumulative trials now %d)",
                    cumulative)
        return int(cur.lastrowid)
    finally:
        conn.close()
