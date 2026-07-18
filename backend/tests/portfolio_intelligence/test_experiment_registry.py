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

from datetime import date, timedelta

from backend import db as db_module
from backend.db import get_connection, init_db
from engine.validation.overfitting import deflated_sharpe_from_returns
from backend.services.portfolio_intelligence.experiment_registry import (
    cumulative_trial_count,
    effective_independent_trials,
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


# ── Effective-N: reported, NEVER gating (TRIAL-001 design review, option 2) ──


def _seed_correlated_lanes(db_path, lanes, n_days=60, rho=0.6, seed=5):
    """Seed paper_portfolios + paper_nav for `lanes` with correlated returns."""
    rng = np.random.default_rng(seed)
    conn = get_connection(db_path)
    try:
        for lane in lanes:
            conn.execute(
                "INSERT OR IGNORE INTO paper_portfolios "
                "(id, inception_date, inception_value, config_version) "
                "VALUES (?, '2026-06-08', 100000.0, 'cfg')", (lane,))
        common = rng.normal(0.0005, 0.01, n_days)  # shared market factor
        d0 = date(2026, 6, 8)
        for i, lane in enumerate(lanes):
            idio = rng.normal(0.0, 0.01, n_days)
            r = rho * common + (1.0 - rho) * idio
            nav = 100000.0 * np.cumprod(1.0 + r)
            for j in range(n_days):
                dt = (d0 + timedelta(days=j)).isoformat()
                db_module.insert_nav(conn, lane, dt, float(nav[j]), "cfg",
                                     dt + "T21:00:00")
    finally:
        conn.close()


def test_effective_independent_trials_no_data(tmp_db):
    eff = effective_independent_trials(tmp_db)
    assert eff["status"] == "no_data"
    assert eff["n_eff"] is None
    assert "reported only" in eff["note"]


def test_effective_independent_trials_insufficient_history(tmp_db):
    _seed_correlated_lanes(tmp_db, ["conservative", "balanced"], n_days=5)
    eff = effective_independent_trials(tmp_db, min_obs=30)
    assert eff["status"] == "insufficient_history"
    assert eff["n_eff"] is None


def test_effective_independent_trials_below_raw_for_correlated_lanes(tmp_db):
    lanes = ["conservative", "balanced", "aggressive"]
    _seed_correlated_lanes(tmp_db, lanes, n_days=80, rho=0.6)
    eff = effective_independent_trials(tmp_db, min_obs=30)
    assert eff["status"] == "ok"
    assert eff["n_lanes"] == 3
    # correlated → effective count strictly below the raw lane count
    assert 1.0 <= eff["n_eff"] < 3.0


def test_gate_is_unchanged_by_effective_n(tmp_db):
    """The load-bearing invariant: N_eff is reported but NEVER moves the gate.

    The adoption decision must be byte-identical to a raw-cumulative-count DSR,
    whether or not correlated lane streams exist to compute N_eff from.
    """
    returns = _candidate_returns()
    # No lanes seeded yet.
    bare = evaluate_candidate(returns, 0.02, batch_trials=1, db_path=tmp_db)
    # Now seed correlated lanes so N_eff becomes computable...
    _seed_correlated_lanes(tmp_db, ["conservative", "balanced", "aggressive"],
                           n_days=80)
    withlanes = evaluate_candidate(returns, 0.02, batch_trials=1, db_path=tmp_db)

    # Gate outputs identical regardless of the effective-N view.
    for k in ("n_trials", "dsr", "survives", "expected_max_sharpe_h0", "verdict"):
        assert bare[k] == withlanes[k]

    # And the gate equals the pure raw-count DSR (no effective-N leakage).
    raw = deflated_sharpe_from_returns(returns, n_trials=1, sr_variance=0.02)
    assert withlanes["dsr"] == raw["dsr"]

    # The reported view IS populated once lanes exist, and is labelled non-gating.
    assert bare["effective_independent_trials"]["status"] == "no_data"
    assert withlanes["effective_independent_trials"]["status"] == "ok"
    assert withlanes["effective_independent_trials"]["n_eff"] is not None


def test_near_duplicate_lane_raises_raw_count_but_not_neff(tmp_db):
    """Pinning test: a near-duplicate lane bumps raw N by 1 yet barely moves N_eff.

    Uses the real 4th reference lane (balanced-ew-control) as a ρ≈0.99 clone of
    balanced — the helper only counts streams from REFERENCE_LANES.
    """
    _seed_correlated_lanes(tmp_db, ["conservative", "balanced", "aggressive"],
                           n_days=120, rho=0.5, seed=2)
    before = effective_independent_trials(tmp_db, min_obs=30)
    raw_before = cumulative_trial_count(tmp_db)

    # Add balanced-ew-control as a near-duplicate of balanced (jittered → ρ≈0.99).
    conn = get_connection(tmp_db)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO paper_portfolios "
            "(id, inception_date, inception_value, config_version) "
            "VALUES ('balanced-ew-control', '2026-06-08', 100000.0, 'cfg')")
        rng = np.random.default_rng(99)
        rows = conn.execute(
            "SELECT date, nav FROM paper_nav WHERE portfolio_id='balanced' ORDER BY date"
        ).fetchall()
        for r in rows:
            jittered = float(r["nav"]) * (1.0 + rng.normal(0.0, 1e-4))
            db_module.insert_nav(conn, "balanced-ew-control", r["date"], jittered,
                                 "cfg", r["date"] + "T21:00:00")
    finally:
        conn.close()
    # Registering the lane is itself a trial row in the registry (raw count +1).
    record_trial(
        evaluate_candidate(_candidate_returns(), 0.02, batch_trials=1, db_path=tmp_db),
        param="lane:balanced-ew-control", new_value="registered",
        config_version="cfg", lane_id="balanced-ew-control", db_path=tmp_db)

    after = effective_independent_trials(tmp_db, min_obs=30)

    assert cumulative_trial_count(tmp_db) == raw_before + 1   # raw N jumped by 1
    assert after["n_lanes"] == before["n_lanes"] + 1          # a stream was added
    assert after["n_eff"] - before["n_eff"] < 0.2            # N_eff barely moved


def test_record_trial_persists_effective_trials(tmp_db):
    _seed_correlated_lanes(tmp_db, ["conservative", "balanced", "aggressive"],
                           n_days=80)
    ev = evaluate_candidate(_candidate_returns(), 0.02, batch_trials=1, db_path=tmp_db)
    assert ev["effective_independent_trials"]["status"] == "ok"
    record_trial(ev, param="drift", new_value=0.06, config_version="cfg",
                 db_path=tmp_db)
    conn = get_connection(tmp_db)
    try:
        row = conn.execute(
            "SELECT effective_trials FROM rule_experiments ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    assert row["effective_trials"] is not None
    assert row["effective_trials"] == pytest.approx(
        ev["effective_independent_trials"]["n_eff"])


# ── data_grade stamp on the verdict (B2) ─────────────────────────────────────


def test_verdict_carries_data_grade_default_directional(tmp_db):
    ev = evaluate_candidate(_candidate_returns(), 0.02, batch_trials=1, db_path=tmp_db)
    assert ev["data_grade"] == "directional"


def test_verdict_data_grade_propagates(tmp_db):
    ev = evaluate_candidate(_candidate_returns(), 0.02, batch_trials=1,
                            db_path=tmp_db, data_grade="sizing")
    assert ev["data_grade"] == "sizing"


def test_no_verdict_path_is_unstamped(tmp_db):
    # Every verdict dict that decides graduation must carry data_grade, whatever
    # the inputs (survives or rejected). Nothing un-stamped reaches a lane.
    for bt in (1, 5):
        ev = evaluate_candidate(_candidate_returns(), 0.02, batch_trials=bt, db_path=tmp_db)
        assert ev.get("data_grade"), f"un-stamped verdict for batch_trials={bt}"


class TestMomBacktestTrial:
    """TRIAL-MOM-BACKTEST registers idempotently and counts toward DSR/PBO."""

    def test_registers_once_and_increments_cumulative(self, tmp_path):
        from backend.db import get_connection, init_db
        from backend.services.portfolio_intelligence.trial_registry import (
            MOM_BACKTEST_TRIAL_PARAM,
            ensure_mom_backtest_trial,
        )
        db = tmp_path / "reg.db"
        init_db(db)
        rid1 = ensure_mom_backtest_trial(db_path=db)
        rid2 = ensure_mom_backtest_trial(db_path=db)
        assert rid1 == rid2  # idempotent
        conn = get_connection(db)
        try:
            rows = conn.execute(
                "SELECT param, verdict, notes FROM rule_experiments "
                "WHERE param = ?", (MOM_BACKTEST_TRIAL_PARAM,)).fetchall()
        finally:
            conn.close()
        assert len(rows) == 1
        assert "NOT a forward clock" in rows[0]["notes"]
        assert "docs/TRIALS/TRIAL-MOM-BACKTEST" in rows[0]["notes"]
