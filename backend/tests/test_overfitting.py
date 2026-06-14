"""
Tests for engine/validation/overfitting.py
============================================

Verifies the backtest-overfitting guards behave correctly on cases where
we know the right answer:
  - a long, genuinely-skilled track record → high PSR/DSR
  - the luckiest of many random strategies → DSR deflated below PSR
  - pure-noise strategy matrix → PBO ≈ 0.5 (selection is noise)
  - one dominant strategy → PBO ≈ 0 (robust)
  - CombinatorialPurgedCV produces C(N,k) disjoint, embargoed splits
"""

import math

import numpy as np
import pytest

from engine.validation.overfitting import (
    CombinatorialPurgedCV,
    deflated_sharpe_from_returns,
    deflated_sharpe_ratio,
    effective_number_of_trials,
    expected_max_sharpe,
    min_track_record_length,
    passes_multiple_testing_hurdle,
    probabilistic_sharpe_ratio,
    probability_of_backtest_overfitting,
)


# ── Probabilistic Sharpe Ratio ──────────────────────────────────────────


def test_psr_zero_edge_is_half():
    """A Sharpe of exactly 0 should give PSR ≈ 0.5 vs a zero benchmark."""
    assert probabilistic_sharpe_ratio(0.0, n_obs=100) == pytest.approx(0.5, abs=1e-9)


def test_psr_strong_long_record_is_confident():
    """A solid per-obs Sharpe over a long record should give high PSR."""
    psr = probabilistic_sharpe_ratio(0.20, n_obs=500)
    assert psr > 0.99


def test_psr_monotonic_in_observed_sr():
    a = probabilistic_sharpe_ratio(0.05, n_obs=200)
    b = probabilistic_sharpe_ratio(0.15, n_obs=200)
    assert b > a


def test_psr_more_data_more_confident():
    short = probabilistic_sharpe_ratio(0.10, n_obs=50)
    long = probabilistic_sharpe_ratio(0.10, n_obs=500)
    assert long > short


def test_psr_negative_skew_hurts_confidence():
    """Negative skew inflates the denominator variance → lower PSR."""
    base = probabilistic_sharpe_ratio(0.15, n_obs=250, skew=0.0, kurtosis=3.0)
    neg_skew = probabilistic_sharpe_ratio(0.15, n_obs=250, skew=-1.0, kurtosis=6.0)
    assert neg_skew < base


# ── Expected max Sharpe & Deflated Sharpe Ratio ─────────────────────────


def test_expected_max_sharpe_grows_with_trials():
    v = 0.01
    assert expected_max_sharpe(100, v) > expected_max_sharpe(10, v)


def test_expected_max_sharpe_degenerate_returns_zero():
    assert expected_max_sharpe(1, 0.01) == 0.0
    assert expected_max_sharpe(100, 0.0) == 0.0


def test_dsr_deflates_below_psr_when_many_trials():
    """The luckiest of many random strategies: DSR must sit below PSR."""
    rng = np.random.default_rng(7)
    n_trials = 200
    n_obs = 250
    sharpes = []
    returns_by_trial = []
    for _ in range(n_trials):
        r = rng.normal(0.0, 0.01, n_obs)
        returns_by_trial.append(r)
        sharpes.append(r.mean() / r.std(ddof=1))
    sharpes = np.array(sharpes)
    best = int(np.argmax(sharpes))
    sr_var = float(sharpes.var(ddof=1))

    winner = returns_by_trial[best]
    psr = probabilistic_sharpe_ratio(
        winner.mean() / winner.std(ddof=1), n_obs
    )
    dsr = deflated_sharpe_ratio(
        winner.mean() / winner.std(ddof=1),
        n_obs=n_obs,
        n_trials=n_trials,
        sr_variance=sr_var,
    )
    # The winner looks good on its own (PSR) but is exposed as luck (low DSR).
    assert dsr < psr
    assert dsr < 0.95


def test_dsr_high_for_genuine_skill_few_trials():
    """A real edge found in only a couple of trials should survive deflation."""
    rng = np.random.default_rng(3)
    r = rng.normal(0.002, 0.01, 500)  # per-obs SR ≈ 0.2
    sr = r.mean() / r.std(ddof=1)
    dsr = deflated_sharpe_ratio(sr, n_obs=500, n_trials=2, sr_variance=1e-4)
    assert dsr > 0.95


def test_deflated_sharpe_from_returns_shape():
    rng = np.random.default_rng(1)
    r = rng.normal(0.001, 0.01, 300)
    out = deflated_sharpe_from_returns(r, n_trials=50, sr_variance=0.01)
    for key in ("observed_sharpe", "psr", "dsr", "expected_max_sharpe_h0", "n_obs"):
        assert key in out
    assert out["n_obs"] == 300
    assert 0.0 <= out["dsr"] <= 1.0
    assert out["dsr"] <= out["psr"] + 1e-9  # deflation never increases confidence


# ── Min track record length ─────────────────────────────────────────────


def test_mintrl_infinite_when_no_edge():
    assert math.isinf(min_track_record_length(0.0))
    assert math.isinf(min_track_record_length(-0.1))


def test_mintrl_finite_and_decreasing_in_sr():
    hi_sr = min_track_record_length(0.30)
    lo_sr = min_track_record_length(0.10)
    assert math.isfinite(hi_sr) and math.isfinite(lo_sr)
    assert hi_sr < lo_sr  # a bigger edge needs fewer observations


# ── Harvey/Liu/Zhu hurdle ───────────────────────────────────────────────


def test_tstat_hurdle():
    assert passes_multiple_testing_hurdle(3.5)
    assert passes_multiple_testing_hurdle(-3.1)  # magnitude matters
    assert not passes_multiple_testing_hurdle(2.0)
    assert passes_multiple_testing_hurdle(2.5, hurdle=2.0)


# ── Probability of Backtest Overfitting (CSCV) ──────────────────────────


def test_pbo_pure_noise_near_half():
    """N independent noise strategies: IS-best is random → PBO ≈ 0.5."""
    rng = np.random.default_rng(11)
    T, N = 96, 30
    M = rng.normal(0.0, 0.01, (T, N))
    res = probability_of_backtest_overfitting(M, n_partitions=8)
    assert res["n_splits"] > 0
    assert 0.3 <= res["pbo"] <= 0.7


def test_pbo_dominant_strategy_is_robust():
    """One strategy with a real, persistent edge → PBO ≈ 0 (robust)."""
    rng = np.random.default_rng(13)
    T, N = 96, 30
    M = rng.normal(0.0, 0.01, (T, N))
    M[:, 0] += 0.02  # strategy 0 dominates every period
    res = probability_of_backtest_overfitting(M, n_partitions=8)
    assert res["pbo"] < 0.2
    assert res["interpretation"] == "robust"


def test_pbo_requires_two_configs():
    M = np.random.default_rng(0).normal(size=(50, 1))
    res = probability_of_backtest_overfitting(M)
    assert math.isnan(res["pbo"])


def test_pbo_handles_odd_partitions():
    """Odd n_partitions should be coerced to even without error."""
    rng = np.random.default_rng(5)
    M = rng.normal(0.0, 0.01, (80, 10))
    res = probability_of_backtest_overfitting(M, n_partitions=7)
    assert res["n_partitions"] % 2 == 0
    assert res["n_splits"] > 0


# ── Combinatorial Purged CV ─────────────────────────────────────────────


def test_cpcv_path_count():
    cv = CombinatorialPurgedCV(n_groups=6, n_test_groups=2)
    assert cv.n_paths() == math.comb(6, 2)
    splits = list(cv.split(120))
    assert len(splits) == math.comb(6, 2)


def test_cpcv_train_test_disjoint_and_cover():
    cv = CombinatorialPurgedCV(n_groups=5, n_test_groups=2, embargo_td=0)
    for train_idx, test_idx in cv.split(100):
        assert set(train_idx).isdisjoint(set(test_idx))
        # With no embargo, train ∪ test covers everything.
        assert len(set(train_idx) | set(test_idx)) == 100


def test_cpcv_embargo_shrinks_train():
    n = 120
    no_embargo = CombinatorialPurgedCV(6, 2, embargo_td=0)
    with_embargo = CombinatorialPurgedCV(6, 2, embargo_td=5)
    a = next(no_embargo.split(n))
    b = next(with_embargo.split(n))
    assert len(b[0]) < len(a[0])  # embargo removes neighbouring train rows


def test_cpcv_rejects_bad_config():
    with pytest.raises(ValueError):
        CombinatorialPurgedCV(n_groups=3, n_test_groups=3)


# ── Effective number of trials (participation ratio) ────────────────────────


def _indep_returns(n_streams: int, n_obs: int = 250, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(0.0, 0.01, size=(n_obs, n_streams))


def test_eff_n_orthogonal_streams_approaches_full_count():
    """Independent streams → N_eff ≈ N (no redundancy)."""
    info = effective_number_of_trials(_indep_returns(4))
    assert info["status"] == "ok"
    assert info["n_streams"] == 4
    assert info["n_eff"] > 3.0  # close to 4 for independent noise


def test_eff_n_identical_streams_collapses_to_one():
    """Perfectly collinear streams → N_eff = 1 (one effective bet)."""
    base = _indep_returns(1, n_obs=200)
    M = np.repeat(base, 4, axis=1)  # 4 identical columns
    info = effective_number_of_trials(M)
    assert info["status"] == "ok"
    assert info["n_eff"] == pytest.approx(1.0, abs=1e-6)


def test_eff_n_near_duplicate_barely_moves_while_raw_count_jumps():
    """The pinning test: adding a ρ≈0.99 stream adds <~0.1 to N_eff."""
    rng = np.random.default_rng(11)
    base = _indep_returns(3, n_obs=400, seed=3)  # 3 roughly-independent lanes
    before = effective_number_of_trials(base)["n_eff"]

    # A near-duplicate of column 0 (correlation ≈ 0.99).
    dup = base[:, [0]] + rng.normal(0.0, 0.0014, size=(base.shape[0], 1))
    after_info = effective_number_of_trials(np.hstack([base, dup]))

    assert after_info["n_streams"] == 4          # raw count went 3 -> 4
    assert after_info["n_eff"] - before < 0.1    # N_eff barely budged


def test_eff_n_insufficient_history_falls_back_to_raw_count():
    """Too few aligned obs → status flagged, N_eff cannot loosen anything."""
    info = effective_number_of_trials(_indep_returns(4, n_obs=10), min_obs=30)
    assert info["status"] == "insufficient_history"
    assert info["n_eff"] == 4.0  # == n_streams: never a looser (smaller) value


def test_eff_n_single_stream():
    info = effective_number_of_trials(_indep_returns(1))
    assert info["status"] == "single_stream"
    assert info["n_eff"] == 1.0


def test_eff_n_degenerate_zero_variance_stream():
    M = _indep_returns(3, n_obs=100)
    M[:, 1] = 0.0  # a flat stream → correlation undefined
    info = effective_number_of_trials(M)
    assert info["status"] == "degenerate"
    assert info["n_eff"] == 3.0


def test_eff_n_bounded_between_one_and_n():
    for seed in range(5):
        info = effective_number_of_trials(_indep_returns(5, seed=seed))
        assert 1.0 <= info["n_eff"] <= 5.0
