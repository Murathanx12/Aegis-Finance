"""
Aegis Finance — Rule-Evolution Experiment Registry
====================================================

The Aegis-OWNED persistence + acceptance logic for the guarded rule-evolution
loop. Every candidate rule change the loop tries is a "trial" recorded here.

The load-bearing rule (correction from design review): the Deflated Sharpe /
PBO guards must deflate against the CUMULATIVE number of trials ever run —
read from this registry — NOT just the trials in the current batch. A loop
that re-deflates only per-batch slowly becomes an overfitting machine: run it
1,000 times and you have mined 1,000s of configs, so the bar a winner must
clear is set by 1,000s of trials, not by the handful in tonight's run.

This registry lives in Aegis (public repo, where the loop runs) for
reproducibility. Optimus may ingest it as corpus; it never owns it.

Usage:
    from backend.services.portfolio_intelligence.experiment_registry import (
        cumulative_trial_count, evaluate_candidate, record_trial,
    )
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import numpy as np

from backend.db import (
    count_cumulative_trials,
    get_connection,
    init_db,
    insert_experiment,
)
from engine.validation.overfitting import (
    deflated_sharpe_from_returns,
    effective_number_of_trials,
    expected_max_sharpe,
    probability_of_backtest_overfitting,
)

# Ship bar: a candidate must clear DSR >= this AND PBO < 0.5 to be adopted.
DSR_SHIP_THRESHOLD = 0.95
PBO_REJECT_THRESHOLD = 0.5


def cumulative_trial_count(db_path=None) -> int:
    """Total trials ever recorded in the registry (the multiple-testing count)."""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        return count_cumulative_trials(conn)
    finally:
        conn.close()


def effective_independent_trials(db_path=None, min_obs: int = 30) -> dict:
    """Reported (NON-gating) estimate of independent trials among lanes with
    live return streams — the "estimated independent-trials" view.

    Pulls each reference lane's ``paper_nav`` series, aligns them on common
    dates, converts to daily returns, and returns the participation-ratio
    ``N_eff`` (see :func:`engine.validation.overfitting.effective_number_of_trials`).

    **Guardrail (TRIAL-001 design review, 2026-06-14): reported, never gating.**
    The adoption gate (:func:`evaluate_candidate`) deflates against the *raw*
    cumulative trial count, which acts as a strictness floor — at current
    sample sizes the lane-return correlation matrix is too noisy to be trusted
    to *loosen* the bar, and a too-lenient guard (a false skill claim) is the
    failure mode this project most needs to avoid. The raw count covers all
    registry rows (lanes + rule tweaks); ``N_eff`` is computed only over lanes
    that carry return streams, and is labelled as such. Revisit feeding N_eff
    into the gate only once lane history is long enough to make it stable — and
    record that as its own registered decision.
    """
    _NOTE = ("reported only — the adoption gate deflates against the raw "
             "cumulative trial count (a strictness floor)")
    from backend.db import get_nav_series
    from backend.services.portfolio_intelligence.rules import (
        BOOK_LANES,
        CONSERVATIVE_ATR_LANES,
        REFERENCE_LANES,
    )

    init_db(db_path)
    conn = get_connection(db_path)
    try:
        series = {}
        # Reference lanes + book lanes (P1 #6). Book lanes (mirror/conviction)
        # share the same holdings → highly correlated → N_eff treats them as ~1
        # independent stream, which is exactly why N_eff is reported and the raw
        # cumulative count stays the gate floor.
        for lane_id in (*REFERENCE_LANES, *BOOK_LANES, *CONSERVATIVE_ATR_LANES):
            rows = get_nav_series(conn, lane_id)
            if rows:
                series[lane_id] = {r["date"]: r["nav"] for r in rows}
    finally:
        conn.close()

    lanes = sorted(series)
    if len(lanes) < 2:
        return {"n_eff": None, "n_lanes": len(lanes), "n_obs": 0,
                "status": "single_stream" if lanes else "no_data",
                "lanes": lanes, "note": _NOTE}

    # Dates present for EVERY lane, chronological — so returns are aligned.
    common = sorted(set.intersection(*(set(s) for s in series.values())))
    if len(common) < 2:
        return {"n_eff": None, "n_lanes": len(lanes), "n_obs": len(common),
                "status": "insufficient_history", "lanes": lanes, "note": _NOTE}

    nav = np.array([[series[lid][d] for lid in lanes] for d in common], dtype=float)
    rets = np.diff(nav, axis=0) / nav[:-1]

    info = effective_number_of_trials(rets, min_obs=min_obs)
    return {
        "n_eff": info["n_eff"] if info["status"] == "ok" else None,
        "n_lanes": len(lanes),
        "n_obs": info["n_obs"],
        "status": info["status"],
        "lanes": lanes,
        "note": _NOTE,
    }


def evaluate_candidate(
    returns,
    batch_sr_variance: float,
    batch_trials: int = 1,
    *,
    pbo_matrix=None,
    dsr_ship: float = DSR_SHIP_THRESHOLD,
    data_grade: str | None = None,
    db_path=None,
) -> dict:
    """Evaluate a candidate rule change, deflating against CUMULATIVE trials.

    n_trials = (trials already in the registry) + (candidates in this batch).
    This is what makes the guard tighten over the life of the loop.

    Args:
        returns: forward returns of the candidate strategy (1-D).
        batch_sr_variance: variance of Sharpes across this batch's candidates.
        batch_trials: number of candidates evaluated in this batch.
        pbo_matrix: optional (T × N) per-period returns matrix for the PBO test.

    Returns a verdict dict (does NOT write to the registry — call record_trial).
    """
    existing = cumulative_trial_count(db_path)
    n_trials = existing + max(batch_trials, 1)

    # Stamp the data grade of the backtest that produced these returns. Default
    # to the grade of the live price source (yfinance -> directional), so no
    # verdict that decides graduation is ever un-stamped (B2). A sizing-grade
    # source flips this once one is wired.
    if data_grade is None:
        from backend.services import data_integrity as _di
        data_grade = _di.data_grade(_di.DEFAULT_PRICE_SOURCE).value

    dsr_info = deflated_sharpe_from_returns(
        np.asarray(returns, dtype=float),
        n_trials=n_trials,
        sr_variance=batch_sr_variance,
    )

    pbo = None
    if pbo_matrix is not None:
        pbo = probability_of_backtest_overfitting(np.asarray(pbo_matrix, dtype=float)).get("pbo")

    survives = dsr_info["dsr"] >= dsr_ship and (pbo is None or pbo < PBO_REJECT_THRESHOLD)

    result = {
        "existing_trials": existing,
        "batch_trials": max(batch_trials, 1),
        "n_trials": n_trials,
        "dsr_ship": dsr_ship,
        "pbo": pbo,
        "survives": survives,
        "verdict": "adopted" if survives else "rejected",
        "data_grade": data_grade,
        **dsr_info,
    }

    # Reported-only diagnostic (NEVER gates — see effective_independent_trials).
    # The gate above used the raw-count expected-max-Sharpe bar
    # (dsr_info["expected_max_sharpe_h0"]). Here we surface what the
    # correlation-adjusted effective-N *would* imply, purely for transparency.
    try:
        eff = effective_independent_trials(db_path)
    except Exception:  # never let the reported view break the gate
        eff = {"n_eff": None, "status": "error"}
    result["effective_independent_trials"] = eff
    result["expected_max_sharpe_at_raw_n"] = dsr_info["expected_max_sharpe_h0"]
    if eff.get("status") == "ok" and eff.get("n_eff"):
        result["expected_max_sharpe_at_effective_n"] = round(
            expected_max_sharpe(int(round(eff["n_eff"])), batch_sr_variance), 4)

    return result


def record_trial(
    evaluation: dict,
    *,
    param: str,
    config_version: str = "unknown",
    lane_id: Optional[str] = None,
    old_value=None,
    new_value=None,
    notes: Optional[str] = None,
    created_at: Optional[str] = None,
    db_path=None,
) -> int:
    """Persist a trial (from evaluate_candidate) to the registry. Returns row id."""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        return insert_experiment(
            conn,
            created_at=created_at or datetime.now(timezone.utc).isoformat(),
            config_version=config_version,
            param=param,
            batch_trials=evaluation.get("batch_trials", 1),
            cumulative_trials=evaluation.get("n_trials", 1),
            verdict=evaluation.get("verdict", "rejected"),
            lane_id=lane_id,
            old_value=old_value,
            new_value=new_value,
            observed_sharpe=evaluation.get("observed_sharpe"),
            n_obs=evaluation.get("n_obs"),
            dsr=evaluation.get("dsr"),
            pbo=evaluation.get("pbo"),
            effective_trials=(evaluation.get("effective_independent_trials") or {}).get("n_eff"),
            notes=notes,
        )
    finally:
        conn.close()
