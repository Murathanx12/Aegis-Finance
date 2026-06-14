"""
LPPLS bubble-structure flag — DESCRIPTIVE, never a forecaster (T1)
=================================================================

The Log-Periodic Power Law Singularity model captures the *structure* of a
speculative regime (super-exponential price growth + accelerating log-periodic
oscillations). Its predictive skill for crash *timing* was adversarially
**REFUTED twice** in the 2026-06-14 deep research
(`DEEP_RESEARCH_2026-06-14_DECISION.md` §1.1). So it ships here as a descriptive
bubble/regime flag ONLY:

  - It is measured FORWARD against a base-rate climatology baseline (TRIAL-LPPLS,
    forward Brier by horizon) before any skill is ever claimed.
  - It is HARD-WIRED to never arm a lane, never size a position, and never emit
    buy/sell language. There is no code path from this module to a trade.
  - A skill claim is permitted only if a pre-registered forward Brier ever beats
    climatology by horizon — which the literature predicts it will not.

This mirrors the crash-overlay observability template: a scheduled eval persists
an `lppls_eval` audit row each cycle, `scheduler.lppls_status()` reads the latest
and exposes a canary on `/api/health/full`, so a dark/stale flag can never run
unseen.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Surfaced with every reading so the UI/consumer can never mistake it for a call.
LPPLS_LABEL = "descriptive bubble-structure flag — NOT a crash-timing forecaster"

# Sentinel portfolio_id for the market-level (non-lane) audit rows.
MARKET_ID = "_market"

# Forward-Brier harness defaults (pre-registered in TRIAL-LPPLS).
BRIER_HORIZONS_DAYS = (30, 60, 90)
CRASH_DRAWDOWN_THRESHOLD = 0.10  # a "crash" outcome = SPY draws down >=10% within the horizon


# ─────────────────────────────────────────────────────────────────────────
# Evaluation (descriptive reading)
# ─────────────────────────────────────────────────────────────────────────


LPPLS_TRIAL_PARAM = "lppls-fragility-flag"

LPPLS_DECISION_RULE = {
    "trial": "TRIAL-LPPLS",
    "hypothesis": (
        "LPPLS bubble-structure confidence on the S&P 500 has forward skill at "
        "flagging elevated crash risk over 30/60/90-day horizons"
    ),
    "purpose": "experimental",
    "primary_metric": "forward Brier by horizon vs base-rate climatology",
    "horizons_days": list(BRIER_HORIZONS_DAYS),
    "crash_outcome": f"SPY drawdown >= {CRASH_DRAWDOWN_THRESHOLD:.0%} within horizon",
    "baseline": "climatology (predict in-sample base rate every period)",
    "adopt_threshold": "skill_score > 0 (brier_flag < brier_climatology) on a "
                       "pre-registered forward window, all horizons",
    "prior": "predictive skill REFUTED twice in deep research; expected null",
    "hard_constraint": "descriptive-only; NEVER arms a lane / no buy-sell language",
    "pre_registered": "2026-06-14",
    "canonical_doc": "docs/TRIALS/TRIAL-LPPLS-fragility.md",
}


def ensure_lppls_trial(db_path=None) -> int:
    """Idempotently pre-register TRIAL-LPPLS in the experiment registry.

    Returns the row id (existing or new). Registering it as a trial means the
    LPPLS skill test enters the cumulative trial count the DSR/PBO guards deflate
    against — the conservative direction. verdict='adopted' here means we adopt
    SHIPPING the descriptive flag; any future *signal* claim is a separate trial
    gated on the forward Brier in the decision rule.
    """
    import json as _json

    from backend.db import count_cumulative_trials, get_connection, init_db

    init_db(db_path)
    conn = get_connection(db_path)
    try:
        existing = conn.execute(
            "SELECT id FROM rule_experiments WHERE param = ? ORDER BY id LIMIT 1",
            (LPPLS_TRIAL_PARAM,),
        ).fetchone()
        if existing is not None:
            return int(existing["id"])
        cumulative = count_cumulative_trials(conn) + 1
        notes = {"hypothesis": LPPLS_DECISION_RULE["hypothesis"],
                 "purpose": "experimental",
                 "decision_rule": LPPLS_DECISION_RULE}
        cur = conn.execute(
            "INSERT INTO rule_experiments "
            "(created_at, config_version, lane_id, param, old_value, new_value, "
            " batch_trials, cumulative_trials, verdict, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (datetime.now().isoformat(), "descriptive", None, LPPLS_TRIAL_PARAM,
             None, "registered", 1, cumulative, "adopted", _json.dumps(notes)),
        )
        conn.commit()
        logger.info("Pre-registered TRIAL-LPPLS (cumulative trials now %d)", cumulative)
        return int(cur.lastrowid)
    finally:
        conn.close()


def evaluate_lppls(prices: Optional[pd.Series] = None) -> dict:
    """Compute the descriptive LPPLS reading on the S&P 500 (or a supplied series).

    Returns a dict with status ∈ {evaluated, lppls_not_installed,
    data_unavailable, eval_error} and, when evaluated, confidence/is_bubble/
    tc_date/n_valid_fits. NEVER returns an arming or sizing decision.
    """
    if prices is None:
        try:
            from backend.services.data_fetcher import DataFetcher
            data, _ = DataFetcher().fetch_market_data()
            prices = data["SP500"]
        except Exception as e:  # pragma: no cover - network/IO
            logger.warning("LPPLS: market data unavailable: %s", e)
            return {"status": "data_unavailable", "confidence": None,
                    "is_bubble": None, "label": LPPLS_LABEL}

    if prices is None or len(prices) < 120:
        return {"status": "data_unavailable", "confidence": None,
                "is_bubble": None, "label": LPPLS_LABEL}

    try:
        from backend.services.bubble_detector import get_bubble_status
        b = get_bubble_status(prices, ticker="SP500")
    except Exception as e:
        logger.warning("LPPLS eval error: %s", e)
        return {"status": "eval_error", "confidence": None,
                "is_bubble": None, "label": LPPLS_LABEL}

    if b.get("confidence") is None:
        # bubble_detector returns a reason string in `status` when lppls is absent.
        reason = b.get("status", "lppls_not_installed")
        status = "lppls_not_installed" if "not installed" in str(reason) else "eval_error"
        return {"status": status, "confidence": None, "is_bubble": None,
                "label": LPPLS_LABEL}

    return {
        "status": "evaluated",
        "confidence": b.get("confidence"),
        "is_bubble": b.get("is_bubble"),
        "tc_date": b.get("tc_date"),
        "n_valid_fits": b.get("n_valid_fits"),
        "as_of": str(prices.dropna().index[-1].date()),
        "label": LPPLS_LABEL,
        # Explicit, machine-readable guarantee echoed into every persisted row.
        "arms_lane": False,
        "descriptive_only": True,
    }


def persist_lppls_eval(reading: dict, db_path=None) -> None:
    """Append one `lppls_eval` audit row (market-level) — the forward record."""
    from backend.db import get_connection, insert_audit_log

    conn = get_connection(db_path)
    try:
        insert_audit_log(conn, datetime.now().isoformat(), MARKET_ID,
                         "lppls_eval", reading)
    finally:
        conn.close()


def run_lppls_eval(prices: Optional[pd.Series] = None, db_path=None) -> dict:
    """Evaluate + persist the descriptive LPPLS reading. Called by the scheduler.

    Loud, not silent: it always writes a status row (even on error), so a dark
    flag is visible in health rather than hidden behind a swallowed exception.
    """
    reading = evaluate_lppls(prices)
    try:
        persist_lppls_eval(reading, db_path=db_path)
    except Exception as e:  # pragma: no cover
        logger.error("LPPLS persist failed: %s", e, exc_info=True)
    return reading


# ─────────────────────────────────────────────────────────────────────────
# Forward Brier harness (the measurement — accumulates, scored later)
# ─────────────────────────────────────────────────────────────────────────


def brier_skill(forecasts, outcomes) -> dict:
    """Brier score of a probabilistic flag vs its own base-rate climatology.

    A pure, testable scorer. `forecasts` ∈ [0,1] (here: LPPLS confidence used
    as a deliberately conservative pseudo-probability), `outcomes` ∈ {0,1}.
    climatology = predicting the in-sample base rate every time. The flag has
    skill iff brier_flag < brier_climatology (skill_score > 0).

    Returns {n, base_rate, brier_flag, brier_climatology, skill_score, status}.
    """
    f = np.asarray(forecasts, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    if f.shape != y.shape or f.size == 0:
        return {"status": "no_data", "n": int(f.size)}
    base = float(y.mean())
    brier_flag = float(np.mean((f - y) ** 2))
    brier_clim = float(np.mean((base - y) ** 2))
    skill = None if brier_clim <= 1e-12 else 1.0 - brier_flag / brier_clim
    return {
        "status": "ok",
        "n": int(y.size),
        "base_rate": round(base, 4),
        "brier_flag": round(brier_flag, 4),
        "brier_climatology": round(brier_clim, 4),
        "skill_score": None if skill is None else round(skill, 4),
    }


def _realized_drawdown_within(prices: pd.Series, start, horizon_days: int) -> Optional[int]:
    """1 if SPY drew down >= CRASH_DRAWDOWN_THRESHOLD within `horizon_days` of
    `start`, 0 if it did not, None if the window hasn't fully matured yet."""
    start = pd.Timestamp(start)
    window_end = start + timedelta(days=horizon_days)
    if prices.index[-1] < window_end:
        return None  # not matured — cannot be scored without peeking
    window = prices.loc[(prices.index >= start) & (prices.index <= window_end)]
    if len(window) < 2:
        return None
    peak = window.iloc[0]
    trough = window.min()
    return int((trough / peak - 1.0) <= -CRASH_DRAWDOWN_THRESHOLD)


def forward_brier_status(db_path=None, horizons=BRIER_HORIZONS_DAYS) -> dict:
    """Forward-Brier measurement state for TRIAL-LPPLS — accumulates over time.

    Joins persisted `lppls_eval` readings with realized forward SPY drawdowns
    for readings old enough to have matured, and scores Brier vs climatology per
    horizon. Until enough matured observations exist it returns
    `insufficient_forward_data` with the count accumulated — the honest
    "still measuring" state, never a fabricated number.
    """
    import json

    from backend.db import get_connection

    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT timestamp, payload FROM audit_log "
            "WHERE event_type = 'lppls_eval' ORDER BY id",
        ).fetchall()
    finally:
        conn.close()

    readings = []
    for r in rows:
        try:
            p = json.loads(r["payload"])
        except Exception:
            continue
        if p.get("status") == "evaluated" and p.get("confidence") is not None:
            readings.append({"date": p.get("as_of") or r["timestamp"][:10],
                             "confidence": float(p["confidence"])})

    base = {"trial": "TRIAL-LPPLS", "readings_accumulated": len(readings),
            "crash_threshold": CRASH_DRAWDOWN_THRESHOLD, "label": LPPLS_LABEL,
            "note": "descriptive flag measured forward; never arms a lane"}

    if len(readings) < 30:
        return {**base, "status": "insufficient_forward_data",
                "horizons": {str(h): {"status": "insufficient_forward_data"} for h in horizons}}

    # Realized outcomes need SPY history covering the matured windows.
    try:
        from backend.services.data_fetcher import DataFetcher
        data, _ = DataFetcher().fetch_market_data()
        spy = data["SP500"].dropna()
    except Exception:
        return {**base, "status": "data_unavailable"}

    out = {**base, "status": "ok", "horizons": {}}
    for h in horizons:
        fc, yo = [], []
        for rec in readings:
            y = _realized_drawdown_within(spy, rec["date"], h)
            if y is not None:
                fc.append(rec["confidence"])
                yo.append(y)
        out["horizons"][str(h)] = (
            brier_skill(fc, yo) if len(yo) >= 30
            else {"status": "insufficient_forward_data", "matured": len(yo)}
        )
    return out
