"""
Tests for the rule-evolution experiment registry + cumulative-trials guard.

The load-bearing test (design correction #2): a candidate that PASSES the
deflated-Sharpe guard per-batch must be REJECTED once the cumulative trial
count across all runs is high — proving the guard deflates against the
persistent registry, not just tonight's batch. Without this, the loop is an
overfitting machine over time.
"""

import numpy as np
import pytest

from backend.db import get_connection, init_db
from backend.services.portfolio_intelligence.experiment_registry import (
    cumulative_trial_count,
    evaluate_candidate,
    record_trial,
)


@pytest.fixture
def tmp_db(tmp_path):
    db = tmp_path / "reg.db"
    init_db(db)
    return db


def _seed_trials(db_path, n: int):
    """Bulk-insert n minimal trial rows (fast, single transaction)."""
    conn = get_connection(db_path)
    try:
        conn.executemany(
            """INSERT INTO rule_experiments
               (created_at, config_version, param, batch_trials,
                cumulative_trials, verdict)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [("2026-01-01T00:00:00", "seed", "drift", 1, i + 1, "rejected")
             for i in range(n)],
        )
        conn.commit()
    finally:
        conn.close()


def _candidate_returns():
    """A genuinely strong-looking single strategy (per-obs Sharpe ~0.3)."""
    rng = np.random.default_rng(20260606)
    return rng.normal(0.003, 0.01, 250)


def test_empty_registry_count(tmp_db):
    assert cumulative_trial_count(tmp_db) == 0


def test_cumulative_deflation_rejects_what_batch_would_accept(tmp_db):
    """The core guarantee: same candidate, two cumulative-trial regimes."""
    returns = _candidate_returns()
    sr_variance = 0.02  # variance of Sharpes across mined configs

    # Low cumulative count (fresh registry, small batch) -> should survive.
    low = evaluate_candidate(returns, sr_variance, batch_trials=2, db_path=tmp_db)
    assert low["existing_trials"] == 0
    assert low["dsr"] >= 0.95
    assert low["survives"] is True

    # Now pretend the loop has mined 10,000 configs over its lifetime.
    _seed_trials(tmp_db, 10_000)
    high = evaluate_candidate(returns, sr_variance, batch_trials=2, db_path=tmp_db)
    assert high["existing_trials"] == 10_000
    assert high["n_trials"] == 10_002

    # The bar rose with cumulative trials: the SAME candidate now fails.
    assert high["expected_max_sharpe_h0"] > low["expected_max_sharpe_h0"]
    assert high["dsr"] < low["dsr"]
    assert high["dsr"] < 0.95
    assert high["survives"] is False


def test_dsr_monotonically_non_increasing_in_cumulative_trials(tmp_db):
    returns = _candidate_returns()
    prev = 1.01
    for n in (0, 100, 1_000, 10_000):
        if n:
            _seed_trials(tmp_db, n - cumulative_trial_count(tmp_db))
        dsr = evaluate_candidate(returns, 0.02, batch_trials=1, db_path=tmp_db)["dsr"]
        assert dsr <= prev + 1e-9
        prev = dsr


def test_record_trial_persists_and_increments_count(tmp_db):
    returns = _candidate_returns()
    ev = evaluate_candidate(returns, 0.02, batch_trials=1, db_path=tmp_db)
    rid = record_trial(ev, param="rebalance_trigger_drift", new_value=0.06,
                       config_version="abc123", db_path=tmp_db)
    assert rid > 0
    assert cumulative_trial_count(tmp_db) == 1
