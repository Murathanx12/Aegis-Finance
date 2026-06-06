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


def evaluate_candidate(
    returns,
    batch_sr_variance: float,
    batch_trials: int = 1,
    *,
    pbo_matrix=None,
    dsr_ship: float = DSR_SHIP_THRESHOLD,
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

    dsr_info = deflated_sharpe_from_returns(
        np.asarray(returns, dtype=float),
        n_trials=n_trials,
        sr_variance=batch_sr_variance,
    )

    pbo = None
    if pbo_matrix is not None:
        pbo = probability_of_backtest_overfitting(np.asarray(pbo_matrix, dtype=float)).get("pbo")

    survives = dsr_info["dsr"] >= dsr_ship and (pbo is None or pbo < PBO_REJECT_THRESHOLD)

    return {
        "existing_trials": existing,
        "batch_trials": max(batch_trials, 1),
        "n_trials": n_trials,
        "dsr_ship": dsr_ship,
        "pbo": pbo,
        "survives": survives,
        "verdict": "adopted" if survives else "rejected",
        **dsr_info,
    }


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
            notes=notes,
        )
    finally:
        conn.close()
