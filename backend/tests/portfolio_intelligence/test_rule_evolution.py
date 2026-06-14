"""
Tests for the guarded rule-evolution orchestrator (rule_evolution.evolve_param).

The two load-bearing guarantees, proven deterministically (backtest monkeypatched
so no network):
  1. The deflation guard BITES — an overfit candidate (best-of-a-searched-grid)
     that would pass at a low trial count is REJECTED once the cumulative trial
     count is high. A guard that bites is the whole point.
  2. NEVER auto-adopt — a candidate that PASSES the guard is a full stop:
     action == "STOP_PROPOSE", and NO trial is recorded / no count change.
"""

import numpy as np
import pandas as pd
import pytest

from backend import db as db_module
from backend.db import get_connection, init_db
from backend.services.portfolio_intelligence import rule_evolution as rev
from backend.services.portfolio_intelligence.experiment_registry import (
    cumulative_trial_count,
)


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db = tmp_path / "evo.db"
    monkeypatch.setattr(db_module, "DB_PATH", db)
    init_db(db)
    return db


def _seed_trials(db_path, n: int):
    conn = get_connection(db_path)
    try:
        conn.executemany(
            "INSERT INTO rule_experiments (created_at, config_version, param, "
            "batch_trials, cumulative_trials, verdict) VALUES (?, ?, ?, ?, ?, ?)",
            [("2026-01-01T00:00:00", "seed", "x", 1, i + 1, "rejected") for i in range(n)],
        )
        conn.commit()
    finally:
        conn.close()


def _spread_grid_backtest(lane_id, override, start_date, end_date, engine=None):
    """Deterministic fake: maps the candidate value to a per-obs mean so the grid
    Sharpes SPREAD (~0.05..0.35) — i.e. searching the grid inflates the best, the
    selection bias the deflation guard exists to catch."""
    v = float(list(override.values())[0])
    rng = np.random.default_rng(int(round(v * 1000)))
    mean = v * 0.05  # grid [0.01..0.07] → per-obs Sharpe ~0.05..0.35
    return pd.Series(rng.normal(mean, 0.01, 250))


def _strong_backtest(lane_id, override, start_date, end_date, engine=None):
    """Deterministic fake: a genuinely strong candidate (per-obs Sharpe ~0.4)."""
    rng = np.random.default_rng(int(round(float(list(override.values())[0]) * 1000)))
    return pd.Series(rng.normal(0.004, 0.01, 250))


# ── The guard bites: overfit best-of-grid rejected at high trial count ─────────


def test_overfit_candidate_rejected_after_many_trials(tmp_db, monkeypatch):
    monkeypatch.setattr(rev, "_backtest_candidate", _spread_grid_backtest)
    grid = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07]

    # Pretend the evolution loop has already mined 10,000 configs over its life.
    _seed_trials(tmp_db, 10_000)
    out = rev.evolve_param("balanced", "rebalance_trigger_drift", grid,
                           dry_run=False, db_path=tmp_db)

    assert out["status"] == "ok"
    assert out["grid_size"] == 7
    assert out["sr_variance"] > 0           # the grid genuinely spread
    assert out["survives"] is False         # deflation killed the best-of-7
    assert out["action"] == "recorded_rejected"
    assert "recorded_trial_id" in out
    # The rejection is recorded — the loop working, count moves by exactly 1.
    assert cumulative_trial_count(tmp_db) == 10_001


# ── Never auto-adopt: a passing candidate is a FULL STOP ──────────────────────


def test_passing_candidate_is_full_stop_not_adopted(tmp_db, monkeypatch):
    monkeypatch.setattr(rev, "_backtest_candidate", _strong_backtest)
    before = cumulative_trial_count(tmp_db)  # 0, fresh db

    out = rev.evolve_param("balanced", "rebalance_trigger_drift", [0.05, 0.06],
                           dry_run=False, db_path=tmp_db)

    assert out["survives"] is True
    assert out["action"] == "STOP_PROPOSE"          # hard stop
    assert "recorded_trial_id" not in out            # NOT recorded
    # Critically: a passing candidate must NOT change the registry unattended.
    assert cumulative_trial_count(tmp_db) == before


# ── dry-run records nothing ───────────────────────────────────────────────────


def test_dry_run_records_nothing(tmp_db, monkeypatch):
    monkeypatch.setattr(rev, "_backtest_candidate", _spread_grid_backtest)
    _seed_trials(tmp_db, 10_000)
    out = rev.evolve_param("balanced", "rebalance_trigger_drift",
                           [0.01, 0.04, 0.07], dry_run=True, db_path=tmp_db)
    assert out["survives"] is False
    assert out["action"] == "dry_run_not_recorded"
    assert "recorded_trial_id" not in out
    assert cumulative_trial_count(tmp_db) == 10_000  # unchanged


# ── guard rails: unknown param, no valid candidates ───────────────────────────


def test_unknown_param_is_skipped(tmp_db):
    out = rev.evolve_param("balanced", "not_a_real_param", [1, 2], db_path=tmp_db)
    assert out["status"] == "skipped"


def test_no_valid_candidates(tmp_db, monkeypatch):
    monkeypatch.setattr(rev, "_backtest_candidate",
                        lambda *a, **k: pd.Series(dtype=float))
    out = rev.evolve_param("balanced", "rebalance_trigger_drift", [0.05, 0.06],
                           db_path=tmp_db)
    assert out["status"] == "no_valid_candidates"


def test_low_trials_would_pass_proving_it_was_deflation_not_weakness(tmp_db, monkeypatch):
    """Same overfit grid that gets REJECTED at 10k trials PASSES at 0 trials —
    proving the rejection above is the deflation biting, not a weak candidate."""
    monkeypatch.setattr(rev, "_backtest_candidate", _spread_grid_backtest)
    out = rev.evolve_param("balanced", "rebalance_trigger_drift",
                           [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07],
                           dry_run=True, db_path=tmp_db)  # fresh db, 0 cumulative
    assert out["survives"] is True
    assert out["action"] == "STOP_PROPOSE"
