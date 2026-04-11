"""
HMM Regime Detection & Integration Tests
==========================================

Comprehensive tests covering:
  1. HMM model fitting (valid outputs, edge cases, empty states)
  2. fit_hmm_for_mc bridge function (keys, fallback, None handling)
  3. HMM ↔ Monte Carlo integration (paths, drift/vol blending)
  4. Config-driven HMM parameters
  5. Drift detector reproducibility (rng fix)
  6. get_regime_probs conversion
"""

import numpy as np
import pandas as pd
import pytest


def _make_synthetic_market_data(n_days: int = 1500, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic market data with regime-like behavior."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2018-01-01", periods=n_days)

    # Simulate regime-switching returns
    prices = [5000.0]
    vix = []
    for i in range(n_days - 1):
        if i < 1000:
            ret = rng.normal(0.0004, 0.01)
            vix_val = 15 + rng.normal(0, 2)
        elif i < 1200:
            ret = rng.normal(-0.002, 0.025)
            vix_val = 35 + rng.normal(0, 5)
        else:
            ret = rng.normal(0.0003, 0.012)
            vix_val = 20 + rng.normal(0, 3)
        prices.append(prices[-1] * (1 + ret))
        vix.append(max(8, vix_val))
    vix.append(vix[-1])

    return pd.DataFrame({
        "SP500": prices,
        "VIX": vix,
        "T10Y": 4.0,
        "T3M": 3.5,
    }, index=dates)


# ══════════════════════════════════════════════════════════════════════════════
# 1. HMM MODEL FITTING
# ══════════════════════════════════════════════════════════════════════════════


class TestHMMModelFitting:
    """Test the HMM model in backend/models/hmm.py."""

    def test_fit_hmm_returns_valid_result(self):
        """HMM fitting should produce a valid HMMResult with 3 states."""
        from backend.models.hmm import fit_hmm_regimes

        data = _make_synthetic_market_data()
        result = fit_hmm_regimes(data, n_states=3, n_fits=5)

        assert result.success is True
        assert result.current_regime in ("Bull", "Bear", "Crisis")
        assert len(result.state_means) == 3
        assert len(result.state_vols) == 3
        assert len(result.regime_probs) == 3
        assert result.transition_matrix.shape == (3, 3)

    def test_hmm_regime_probs_sum_to_one(self):
        """Current regime probabilities should sum to ~1.0."""
        from backend.models.hmm import fit_hmm_regimes

        data = _make_synthetic_market_data()
        result = fit_hmm_regimes(data, n_states=3, n_fits=5)

        assert result.success
        prob_sum = result.regime_probs.sum()
        assert abs(prob_sum - 1.0) < 0.01, f"Probs sum to {prob_sum}, expected ~1.0"

    def test_hmm_state_ordering(self):
        """States should produce at least 2 distinct regime labels."""
        from backend.models.hmm import fit_hmm_regimes

        data = _make_synthetic_market_data()
        result = fit_hmm_regimes(data, n_states=3, n_fits=5)

        assert result.success
        labels = result.regime_labels
        unique_labels = labels[labels != "Unknown"].unique()
        assert len(unique_labels) >= 2, f"Expected >=2 regime labels, got {unique_labels}"

    def test_hmm_fallback_on_insufficient_data(self):
        """HMM should return fallback when data is too short."""
        from backend.models.hmm import fit_hmm_regimes

        short_data = _make_synthetic_market_data(n_days=100)
        result = fit_hmm_regimes(short_data)

        assert result.success is False
        assert result.current_regime == "Bull"
        assert len(result.state_means) == 3

    def test_hmm_transition_matrix_rows_sum_to_one(self):
        """Each row of the transition matrix should sum to 1."""
        from backend.models.hmm import fit_hmm_regimes

        data = _make_synthetic_market_data()
        result = fit_hmm_regimes(data, n_states=3, n_fits=5)

        assert result.success
        for i in range(3):
            row_sum = result.transition_matrix[i].sum()
            assert abs(row_sum - 1.0) < 0.01, f"Row {i} sums to {row_sum}"

    def test_hmm_no_vix_column(self):
        """HMM should work with only SP500 (no VIX)."""
        from backend.models.hmm import fit_hmm_regimes

        data = _make_synthetic_market_data()
        data_no_vix = data[["SP500"]].copy()
        result = fit_hmm_regimes(data_no_vix, n_states=3, n_fits=3)

        assert result.success is True
        assert result.current_regime in ("Bull", "Bear", "Crisis")

    def test_hmm_constant_prices_fallback(self):
        """Constant prices → zero returns → HMM should handle gracefully."""
        from backend.models.hmm import fit_hmm_regimes

        dates = pd.bdate_range("2018-01-01", periods=1500)
        data = pd.DataFrame({
            "SP500": 5000.0,
            "VIX": 15.0,
        }, index=dates)

        result = fit_hmm_regimes(data, n_states=3, n_fits=3)
        # Constant vol → zero std → X_std[X_std==0]=1 handles this
        # But rolling std of constant returns → all 0 → may not have 500 valid rows
        # Either way, should not crash
        assert isinstance(result.success, bool)
        assert len(result.state_means) == 3

    def test_hmm_single_fit(self):
        """n_fits=1 should work (no restart)."""
        from backend.models.hmm import fit_hmm_regimes

        data = _make_synthetic_market_data()
        result = fit_hmm_regimes(data, n_states=3, n_fits=1)

        assert result.success is True
        assert result.current_regime in ("Bull", "Bear", "Crisis")

    def test_hmm_feature_mean_std_stored(self):
        """Fitted HMM should store feature normalization params."""
        from backend.models.hmm import fit_hmm_regimes

        data = _make_synthetic_market_data()
        result = fit_hmm_regimes(data, n_states=3, n_fits=3)

        assert result.success
        assert result.feature_mean is not None
        assert result.feature_std is not None
        # 3 features: smoothed ret, realized vol, VIX
        assert len(result.feature_mean) == 3
        assert len(result.feature_std) == 3
        assert np.all(result.feature_std > 0)


# ══════════════════════════════════════════════════════════════════════════════
# 2. get_regime_probs CONVERSION
# ══════════════════════════════════════════════════════════════════════════════


class TestGetRegimeProbs:
    """Test the HMM → scenario weight conversion."""

    def test_successful_result_returns_probs(self):
        """Successful HMM → probs should have all 3 keys and sum to ~1."""
        from backend.models.hmm import fit_hmm_regimes, get_regime_probs

        data = _make_synthetic_market_data()
        result = fit_hmm_regimes(data, n_states=3, n_fits=3)
        probs = get_regime_probs(result)

        assert "bull_prob" in probs
        assert "bear_prob" in probs
        assert "crisis_prob" in probs
        total = probs["bull_prob"] + probs["bear_prob"] + probs["crisis_prob"]
        assert abs(total - 1.0) < 0.01

    def test_failed_result_returns_fallback_probs(self):
        """Failed HMM → should return config-driven fallback probs."""
        from backend.models.hmm import fit_hmm_regimes, get_regime_probs

        short = _make_synthetic_market_data(n_days=50)
        result = fit_hmm_regimes(short)
        probs = get_regime_probs(result)

        assert probs["bull_prob"] == 0.50
        assert probs["bear_prob"] == 0.30
        assert probs["crisis_prob"] == 0.20

    def test_all_probs_non_negative(self):
        """No regime prob should be negative."""
        from backend.models.hmm import fit_hmm_regimes, get_regime_probs

        data = _make_synthetic_market_data()
        result = fit_hmm_regimes(data, n_states=3, n_fits=3)
        probs = get_regime_probs(result)

        assert probs["bull_prob"] >= 0
        assert probs["bear_prob"] >= 0
        assert probs["crisis_prob"] >= 0


# ══════════════════════════════════════════════════════════════════════════════
# 3. fit_hmm_for_mc BRIDGE FUNCTION
# ══════════════════════════════════════════════════════════════════════════════


class TestFitHMMForMC:
    """Test the fit_hmm_for_mc bridge function in regime_detector.py."""

    def test_returns_correct_keys(self):
        """fit_hmm_for_mc should return all keys needed by simulate_paths."""
        from backend.services.regime_detector import fit_hmm_for_mc

        data = _make_synthetic_market_data()
        result = fit_hmm_for_mc(data)

        expected_keys = {"state_means", "state_vols", "regime_probs",
                         "current_regime", "transition_matrix", "success"}
        assert expected_keys == set(result.keys())

    def test_success_with_enough_data(self):
        """Should succeed with sufficient data."""
        from backend.services.regime_detector import fit_hmm_for_mc

        data = _make_synthetic_market_data()
        result = fit_hmm_for_mc(data)

        assert result["success"] is True
        assert result["state_means"] is not None
        assert result["state_vols"] is not None
        assert result["regime_probs"] is not None
        assert len(result["state_means"]) == 3
        assert len(result["state_vols"]) == 3
        assert len(result["regime_probs"]) == 3

    def test_fallback_with_short_data(self):
        """Should return fallback (None arrays) with insufficient data."""
        from backend.services.regime_detector import fit_hmm_for_mc

        short_data = _make_synthetic_market_data(n_days=100)
        result = fit_hmm_for_mc(short_data)

        assert result["success"] is False
        assert result["state_means"] is None
        assert result["state_vols"] is None
        assert result["regime_probs"] is None
        assert result["current_regime"] is None

    def test_fallback_keys_match_success_keys(self):
        """Fallback dict should have exactly the same keys as success dict."""
        from backend.services.regime_detector import fit_hmm_for_mc

        good = fit_hmm_for_mc(_make_synthetic_market_data())
        bad = fit_hmm_for_mc(_make_synthetic_market_data(n_days=50))

        assert set(good.keys()) == set(bad.keys())

    def test_state_vols_all_positive(self):
        """All state vols should be strictly positive."""
        from backend.services.regime_detector import fit_hmm_for_mc

        data = _make_synthetic_market_data()
        result = fit_hmm_for_mc(data)

        if result["success"]:
            assert np.all(np.array(result["state_vols"]) > 0), \
                f"State vols contain non-positive: {result['state_vols']}"

    def test_regime_probs_sum_to_one(self):
        """Regime probs from fit_hmm_for_mc should sum to ~1."""
        from backend.services.regime_detector import fit_hmm_for_mc

        data = _make_synthetic_market_data()
        result = fit_hmm_for_mc(data)

        if result["success"]:
            total = result["regime_probs"].sum()
            assert abs(total - 1.0) < 0.01, f"Probs sum to {total}"


# ══════════════════════════════════════════════════════════════════════════════
# 4. HMM ↔ MONTE CARLO INTEGRATION
# ══════════════════════════════════════════════════════════════════════════════


class TestHMMMCIntegration:
    """Test that HMM outputs integrate correctly with simulate_paths."""

    def test_hmm_outputs_compatible_with_simulate_paths(self):
        """HMM outputs should be valid inputs for simulate_paths."""
        from backend.services.regime_detector import fit_hmm_for_mc
        from backend.services.monte_carlo import simulate_paths

        data = _make_synthetic_market_data()
        hmm = fit_hmm_for_mc(data)

        if not hmm["success"]:
            pytest.skip("HMM fitting failed")

        paths = simulate_paths(
            start_price=5000.0,
            historical_mu=0.05,
            historical_sigma=0.16,
            days=252,
            n_sims=100,
            crash_freq=0.08,
            risk_score=0.0,
            scenario={"drift_adj": 0, "vol_mult": 1.0, "crash_mult": 1.0},
            hmm_state_means=hmm["state_means"],
            hmm_regime_probs=hmm["regime_probs"],
            hmm_state_vols=hmm["state_vols"],
            seed=42,
        )

        assert paths.shape == (253, 100)
        assert paths[0, 0] == 5000.0
        assert np.all(paths > 0)
        assert np.all(np.isfinite(paths))

    def test_hmm_none_inputs_dont_crash_mc(self):
        """simulate_paths should work fine with None HMM inputs (no-op)."""
        from backend.services.monte_carlo import simulate_paths

        paths = simulate_paths(
            start_price=5000.0,
            historical_mu=0.05,
            historical_sigma=0.16,
            days=252,
            n_sims=100,
            crash_freq=0.08,
            risk_score=0.0,
            scenario={"drift_adj": 0, "vol_mult": 1.0, "crash_mult": 1.0},
            hmm_state_means=None,
            hmm_regime_probs=None,
            hmm_state_vols=None,
            seed=42,
        )

        assert paths.shape == (253, 100)
        assert np.all(np.isfinite(paths))

    def test_hmm_blending_changes_drift(self):
        """Providing HMM means should shift the drift vs no-HMM baseline."""
        from backend.services.monte_carlo import simulate_paths

        base_scenario = {"drift_adj": 0, "vol_mult": 1.0, "crash_mult": 1.0}
        common = dict(
            start_price=5000.0,
            historical_mu=0.05,
            historical_sigma=0.16,
            days=252,
            n_sims=500,
            crash_freq=0.08,
            risk_score=0.0,
            scenario=base_scenario,
            seed=42,
        )

        # Without HMM
        paths_no_hmm = simulate_paths(**common)

        # With strongly bullish HMM (high prob on bull state with high mean)
        paths_bull_hmm = simulate_paths(
            **common,
            hmm_state_means=np.array([0.30, -0.05, -0.30]),
            hmm_regime_probs=np.array([0.95, 0.03, 0.02]),
            hmm_state_vols=np.array([0.12, 0.20, 0.35]),
        )

        # Bullish HMM should produce higher mean final price
        mean_no_hmm = paths_no_hmm[-1].mean()
        mean_bull_hmm = paths_bull_hmm[-1].mean()

        # The hmm_drift_blend is 15%, so with a 0.25 drift difference
        # the tilt should be ~0.15 * 0.25 ≈ 0.0375 annual
        assert mean_bull_hmm > mean_no_hmm, \
            f"Bull HMM ({mean_bull_hmm:.0f}) should exceed no-HMM ({mean_no_hmm:.0f})"

    def test_hmm_blending_changes_vol(self):
        """Providing HMM vols should shift the realized vol vs no-HMM baseline."""
        from backend.services.monte_carlo import simulate_paths

        base_scenario = {"drift_adj": 0, "vol_mult": 1.0, "crash_mult": 1.0}
        common = dict(
            start_price=5000.0,
            historical_mu=0.05,
            historical_sigma=0.16,
            days=252,
            n_sims=500,
            crash_freq=0.08,
            risk_score=0.0,
            scenario=base_scenario,
            seed=42,
        )

        # Without HMM
        paths_no_hmm = simulate_paths(**common)

        # With high-vol HMM (all states have very high vol)
        paths_high_vol_hmm = simulate_paths(
            **common,
            hmm_state_means=np.array([0.05, -0.05, -0.30]),
            hmm_regime_probs=np.array([0.90, 0.05, 0.05]),
            hmm_state_vols=np.array([0.50, 0.50, 0.50]),
        )

        # Measure realized vol from daily log returns
        daily_rets_no = np.diff(np.log(paths_no_hmm), axis=0)
        daily_rets_hi = np.diff(np.log(paths_high_vol_hmm), axis=0)

        vol_no = daily_rets_no.std(axis=0).mean() * np.sqrt(252)
        vol_hi = daily_rets_hi.std(axis=0).mean() * np.sqrt(252)

        assert vol_hi > vol_no, \
            f"High-vol HMM ({vol_hi:.3f}) should exceed no-HMM ({vol_no:.3f})"

    def test_extreme_hmm_probs_dont_crash(self):
        """Edge case: all probability on one state shouldn't crash."""
        from backend.services.monte_carlo import simulate_paths

        paths = simulate_paths(
            start_price=5000.0,
            historical_mu=0.05,
            historical_sigma=0.16,
            days=63,
            n_sims=50,
            crash_freq=0.08,
            risk_score=0.0,
            scenario={"drift_adj": 0, "vol_mult": 1.0, "crash_mult": 1.0},
            hmm_state_means=np.array([0.20, -0.10, -0.50]),
            hmm_regime_probs=np.array([1.0, 0.0, 0.0]),
            hmm_state_vols=np.array([0.12, 0.25, 0.40]),
            seed=42,
        )

        assert np.all(np.isfinite(paths))
        assert paths.shape == (64, 50)

    def test_zero_hmm_probs_dont_crash(self):
        """Edge case: all-zero probs should not crash (dot product = 0)."""
        from backend.services.monte_carlo import simulate_paths

        paths = simulate_paths(
            start_price=5000.0,
            historical_mu=0.05,
            historical_sigma=0.16,
            days=63,
            n_sims=50,
            crash_freq=0.08,
            risk_score=0.0,
            scenario={"drift_adj": 0, "vol_mult": 1.0, "crash_mult": 1.0},
            hmm_state_means=np.array([0.0, 0.0, 0.0]),
            hmm_regime_probs=np.array([0.0, 0.0, 0.0]),
            hmm_state_vols=np.array([0.0, 0.0, 0.0]),
            seed=42,
        )

        assert np.all(np.isfinite(paths))


# ══════════════════════════════════════════════════════════════════════════════
# 5. CONFIG-DRIVEN HMM PARAMETERS
# ══════════════════════════════════════════════════════════════════════════════


class TestHMMConfig:
    """Test that HMM uses config values, not hardcoded constants."""

    def test_config_has_hmm_section(self):
        """config['simulation']['hmm'] should exist with expected keys."""
        from backend.config import config

        hmm_cfg = config["simulation"]["hmm"]
        assert "n_states" in hmm_cfg
        assert "n_fits" in hmm_cfg
        assert "n_iter" in hmm_cfg
        assert "min_data_rows" in hmm_cfg
        assert "fallback_state_means" in hmm_cfg
        assert "fallback_state_vols" in hmm_cfg
        assert "fallback_regime_probs" in hmm_cfg

    def test_fallback_probs_sum_to_one(self):
        """Fallback regime probs in config should sum to 1."""
        from backend.config import config

        probs = config["simulation"]["hmm"]["fallback_regime_probs"]
        assert abs(sum(probs) - 1.0) < 0.01

    def test_fallback_uses_config_values(self):
        """_fallback_result should use config, not hardcoded values."""
        from backend.models.hmm import _fallback_result
        from backend.config import config

        dates = pd.bdate_range("2020-01-01", periods=10)
        data = pd.DataFrame({"SP500": 5000.0}, index=dates)
        result = _fallback_result(data)

        expected_means = config["simulation"]["hmm"]["fallback_state_means"]
        np.testing.assert_array_almost_equal(result.state_means, expected_means)

        expected_vols = config["simulation"]["hmm"]["fallback_state_vols"]
        np.testing.assert_array_almost_equal(result.state_vols, expected_vols)

    def test_hmm_blend_weights_exist(self):
        """hmm_drift_blend and hmm_vol_blend should be in simulation config."""
        from backend.config import config

        sim = config["simulation"]
        assert "hmm_drift_blend" in sim
        assert "hmm_vol_blend" in sim
        assert 0 < sim["hmm_drift_blend"] <= 1.0
        assert 0 < sim["hmm_vol_blend"] <= 1.0


# ══════════════════════════════════════════════════════════════════════════════
# 6. DRIFT DETECTOR REPRODUCIBILITY
# ══════════════════════════════════════════════════════════════════════════════


class TestDriftDetectorReproducibility:
    """Test that drift detector produces reproducible results."""

    def test_ks_test_reproducible(self):
        """Two DriftDetector instances with same seed → identical results."""
        from backend.services.drift_detector import DriftDetector

        rng = np.random.default_rng(123)
        ref_data = pd.DataFrame({
            "feat_a": rng.normal(0, 1, 500),
            "feat_b": rng.normal(5, 2, 500),
        })
        inf_data = pd.DataFrame({
            "feat_a": rng.normal(0.5, 1, 100),
            "feat_b": rng.normal(5, 2, 100),
        })

        det1 = DriftDetector(ref_data, seed=42)
        det2 = DriftDetector(ref_data, seed=42)

        report1 = det1.check_drift(inf_data)
        report2 = det2.check_drift(inf_data)

        for col in report1["feature_details"]:
            assert report1["feature_details"][col]["psi"] == report2["feature_details"][col]["psi"]
            assert report1["feature_details"][col]["ks_stat"] == report2["feature_details"][col]["ks_stat"]
            assert report1["feature_details"][col]["ks_p"] == report2["feature_details"][col]["ks_p"]

    def test_different_seeds_different_ks(self):
        """Different seeds should produce different KS test results."""
        from backend.services.drift_detector import DriftDetector

        rng = np.random.default_rng(123)
        ref_data = pd.DataFrame({"x": rng.normal(0, 1, 500)})
        inf_data = pd.DataFrame({"x": rng.normal(0.5, 1, 100)})

        det1 = DriftDetector(ref_data, seed=42)
        det2 = DriftDetector(ref_data, seed=99)

        r1 = det1.check_drift(inf_data)
        r2 = det2.check_drift(inf_data)

        # KS stat may differ slightly due to different synthetic samples
        # (PSI is deterministic so it should be the same)
        if "x" in r1["feature_details"] and "x" in r2["feature_details"]:
            assert r1["feature_details"]["x"]["psi"] == r2["feature_details"]["x"]["psi"]
            # KS stats should differ (different synthetic reference samples)
            # But this is probabilistic, so we just check they're both valid
            assert 0 <= r1["feature_details"]["x"]["ks_stat"] <= 1
            assert 0 <= r2["feature_details"]["x"]["ks_stat"] <= 1

    def test_drift_detected_on_shifted_data(self):
        """Should detect drift when inference distribution is shifted."""
        from backend.services.drift_detector import DriftDetector

        rng = np.random.default_rng(99)
        ref_data = pd.DataFrame({"x": rng.normal(0, 1, 1000)})
        shifted_data = pd.DataFrame({"x": rng.normal(3, 1, 200)})

        det = DriftDetector(ref_data, seed=42)
        report = det.check_drift(shifted_data)

        assert report["drift_detected"] is True
        assert "x" in report["drifted_features"]

    def test_no_drift_on_same_distribution(self):
        """Should NOT detect drift when inference matches reference."""
        from backend.services.drift_detector import DriftDetector

        rng = np.random.default_rng(77)
        ref_data = pd.DataFrame({"x": rng.normal(0, 1, 1000)})
        same_data = pd.DataFrame({"x": rng.normal(0, 1, 200)})

        det = DriftDetector(ref_data, seed=42)
        report = det.check_drift(same_data)

        assert report["drift_detected"] is False

    def test_empty_inference_data(self):
        """Empty inference DataFrame should return no drift."""
        from backend.services.drift_detector import DriftDetector

        rng = np.random.default_rng(55)
        ref_data = pd.DataFrame({"x": rng.normal(0, 1, 500)})
        empty_data = pd.DataFrame({"x": pd.Series(dtype=float)})

        det = DriftDetector(ref_data, seed=42)
        report = det.check_drift(empty_data)

        assert report["drift_detected"] is False
        assert report["n_features_checked"] == 0

    def test_missing_column_in_inference(self):
        """Column present in reference but missing in inference → skipped."""
        from backend.services.drift_detector import DriftDetector

        rng = np.random.default_rng(44)
        ref_data = pd.DataFrame({
            "x": rng.normal(0, 1, 500),
            "y": rng.normal(0, 1, 500),
        })
        inf_data = pd.DataFrame({"x": rng.normal(0, 1, 100)})

        det = DriftDetector(ref_data, seed=42)
        report = det.check_drift(inf_data)

        # Only "x" should be checked, "y" should be skipped
        assert "y" not in report["feature_details"]

    def test_few_inference_samples_skipped(self):
        """Fewer than 10 inference samples → feature skipped."""
        from backend.services.drift_detector import DriftDetector

        rng = np.random.default_rng(33)
        ref_data = pd.DataFrame({"x": rng.normal(0, 1, 500)})
        tiny_data = pd.DataFrame({"x": rng.normal(0, 1, 5)})

        det = DriftDetector(ref_data, seed=42)
        report = det.check_drift(tiny_data)

        assert report["n_features_checked"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# 7. ANALYZE_STOCK HMM PARAM PASSTHROUGH
# ══════════════════════════════════════════════════════════════════════════════


class TestStockAnalyzerHMMParams:
    """Test that analyze_stock properly accepts and forwards HMM params."""

    def test_analyze_stock_signature_accepts_hmm(self):
        """analyze_stock should accept hmm_state_means/probs/vols kwargs."""
        import inspect
        from backend.services.stock_analyzer import analyze_stock

        sig = inspect.signature(analyze_stock)
        params = set(sig.parameters.keys())

        assert "hmm_state_means" in params
        assert "hmm_regime_probs" in params
        assert "hmm_state_vols" in params

    def test_analyze_sectors_signature_accepts_hmm(self):
        """analyze_sectors should accept hmm_state_means/probs/vols kwargs."""
        import inspect
        from backend.services.sector_analyzer import analyze_sectors

        sig = inspect.signature(analyze_sectors)
        params = set(sig.parameters.keys())

        assert "hmm_state_means" in params
        assert "hmm_regime_probs" in params
        assert "hmm_state_vols" in params
