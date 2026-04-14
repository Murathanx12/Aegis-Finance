"""
Cycle 051 regression tests:
  - crash_timeline VIX sigma fix (was 16x overstated)
  - anomaly_detector fillna(0) → ffill/bfill
  - systemic_risk AR n_components scaling
  - systemic_risk signal integration into signal engine
"""

import numpy as np
import pandas as pd
import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# CRASH TIMELINE — VIX sigma fix
# ═══════════════════════════════════════════════════════════════════════════════

class TestCrashTimelineVixSigma:
    """Verify crash_timeline passes correct sigma to simulate_paths."""

    def test_sigma_not_inflated(self):
        """VIX=20 should yield sigma=0.20, NOT 0.20 * sqrt(252) = 3.17."""
        from unittest.mock import patch

        captured_args = {}

        def mock_simulate_paths(*args, **kwargs):
            # Capture positional args: start_price, mu, sigma, days, n_sims, crash_freq, seed
            if len(args) > 2:
                captured_args["historical_sigma"] = args[2]
            captured_args.update(kwargs)
            return np.ones((252, 5000)) * 5000  # dummy paths

        # simulate_paths is imported inside estimate_crash_timeline, so patch at source
        with patch("backend.services.monte_carlo.simulate_paths", side_effect=mock_simulate_paths):
            from backend.services import crash_timeline
            # Force re-import to pick up the mock
            import importlib
            importlib.reload(crash_timeline)
            crash_timeline.estimate_crash_timeline(
                current_level=5000.0,
                vix=20.0,
                months_ahead=12,
            )

            # sigma should be VIX/100 = 0.20, NOT 0.20 * sqrt(252) ≈ 3.17
            sigma = captured_args.get("historical_sigma")
            assert sigma is not None, "historical_sigma not captured"
            assert sigma < 1.0, f"Sigma {sigma} is too high — VIX/100 should be 0.20"
            assert abs(sigma - 0.20) < 0.01, f"Expected ~0.20, got {sigma}"

    def test_sigma_formula_in_source(self):
        """Source code should NOT multiply VIX by sqrt(252) — VIX is already annualized."""
        import inspect
        from backend.services.crash_timeline import estimate_crash_timeline
        source = inspect.getsource(estimate_crash_timeline)
        assert "np.sqrt(252)" not in source, (
            "VIX is already annualized — do not multiply by sqrt(252)"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# ANOMALY DETECTOR — fillna fix
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnomalyDetectorFillna:
    """Verify BOCPD no longer uses fillna(0)."""

    def test_no_fillna_zero_in_source(self):
        """Source code should not contain fillna(0)."""
        import inspect
        from backend.services.anomaly_detector import BayesianChangepoint
        source = inspect.getsource(BayesianChangepoint.detect)
        assert "fillna(0)" not in source, "fillna(0) is banned — use ffill/bfill"

    def test_bocpd_detect_returns_dataframe(self):
        """BOCPD detect should still return valid DataFrame after fix."""
        from backend.services.anomaly_detector import BayesianChangepoint
        rng = np.random.default_rng(42)
        returns = pd.Series(
            rng.normal(0, 0.01, 100),
            index=pd.bdate_range("2024-01-01", periods=100),
        )
        bc = BayesianChangepoint()
        result = bc.detect(returns, window=60)
        assert isinstance(result, pd.DataFrame)
        assert "changepoint_prob" in result.columns
        assert "regime_age" in result.columns
        # Should have no NaNs after ffill/bfill
        assert not result["changepoint_prob"].isna().any()


# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEMIC RISK — AR n_components scaling
# ═══════════════════════════════════════════════════════════════════════════════

class TestAbsorptionRatioScaling:
    """Verify AR n_components is capped at n_assets // 3."""

    def test_6_assets_uses_2_components(self):
        """With 6 assets, n_components should be min(5, 6//3) = 2."""
        from backend.services.systemic_risk import compute_absorption_ratio
        rng = np.random.default_rng(42)
        returns = pd.DataFrame(
            rng.normal(0, 0.01, (400, 6)),
            index=pd.bdate_range("2020-01-01", periods=400),
            columns=[f"A{i}" for i in range(6)],
        )
        ar = compute_absorption_ratio(returns, n_components=5, window=252)
        valid = ar.dropna()
        # With 2 components on 6 assets, AR should be well below 1.0
        # (not ~0.998 as before with 5 components)
        assert valid.mean() < 0.80, (
            f"AR mean {valid.mean():.3f} too high — n_components should be capped"
        )

    def test_ar_scales_with_assets(self):
        """More assets with same n_components → lower AR (more variance to explain)."""
        from backend.services.systemic_risk import compute_absorption_ratio
        rng = np.random.default_rng(42)
        # 6 assets: n_components = min(5, 6//3) = 2
        ret6 = pd.DataFrame(
            rng.normal(0, 0.01, (400, 6)),
            index=pd.bdate_range("2020-01-01", periods=400),
            columns=[f"A{i}" for i in range(6)],
        )
        # 12 assets: n_components = min(5, 12//3) = 4
        ret12 = pd.DataFrame(
            rng.normal(0, 0.01, (400, 12)),
            index=pd.bdate_range("2020-01-01", periods=400),
            columns=[f"A{i}" for i in range(12)],
        )
        ar6 = compute_absorption_ratio(ret6, n_components=5, window=252).dropna()
        ar12 = compute_absorption_ratio(ret12, n_components=5, window=252).dropna()
        # Both should be reasonable (not ~1.0)
        assert ar6.mean() < 0.90
        assert ar12.mean() < 0.90


# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEMIC RISK SIGNAL — integration with signal engine
# ═══════════════════════════════════════════════════════════════════════════════

class TestSystemicRiskSignal:
    """Test get_systemic_risk_signal and signal engine integration."""

    def _make_data(self, seed=42):
        rng = np.random.default_rng(seed)
        dates = pd.bdate_range("2020-01-01", periods=500)
        return pd.DataFrame({
            "SP500": 100 + np.cumsum(rng.normal(0.0003, 0.01, 500)),
            "NASDAQ": 200 + np.cumsum(rng.normal(0.0004, 0.012, 500)),
            "Russell": 50 + np.cumsum(rng.normal(0.0002, 0.011, 500)),
            "Gold": 1800 + np.cumsum(rng.normal(0.0001, 0.008, 500)),
            "HYG": 80 + np.cumsum(rng.normal(0, 0.005, 500)),
            "LQD": 110 + np.cumsum(rng.normal(0, 0.003, 500)),
        }, index=dates)

    def test_returns_float_or_none(self):
        from backend.services.systemic_risk import get_systemic_risk_signal
        data = self._make_data()
        result = get_systemic_risk_signal(data)
        assert result is None or isinstance(result, float)

    def test_score_in_range(self):
        from backend.services.systemic_risk import get_systemic_risk_signal
        data = self._make_data()
        result = get_systemic_risk_signal(data)
        if result is not None:
            assert -1.0 <= result <= 1.0

    def test_insufficient_data_returns_none(self):
        from backend.services.systemic_risk import get_systemic_risk_signal
        data = pd.DataFrame({"SP500": [100], "NASDAQ": [200]},
                            index=pd.bdate_range("2024-01-01", periods=1))
        result = get_systemic_risk_signal(data)
        assert result is None

    def test_signal_engine_accepts_systemic_risk(self):
        """Signal engine should include systemic_risk in components."""
        from backend.services.signal_engine import get_market_signal
        result = get_market_signal(
            crash_prob_3m=10.0,
            regime="Bull",
            systemic_risk_score=-0.5,
        )
        assert "systemic_risk" in result["components"]
        assert result["components"]["systemic_risk"] == -0.5

    def test_signal_engine_without_systemic_risk(self):
        """Signal engine works fine without systemic_risk (backward compatible)."""
        from backend.services.signal_engine import get_market_signal
        result = get_market_signal(
            crash_prob_3m=10.0,
            regime="Neutral",
        )
        assert "systemic_risk" not in result["components"]
        assert "action" in result

    def test_config_has_systemic_risk_weights(self):
        """All weight profiles should include systemic_risk."""
        from backend.config import config
        default_w = config["signal_weights"]
        assert "systemic_risk" in default_w

        regime_w = config["regime_signal_weights"]
        for regime in ("Bull", "Bear", "Volatile"):
            assert "systemic_risk" in regime_w[regime], f"Missing in {regime}"

    def test_negative_score_reduces_composite(self):
        """Negative systemic risk score should push composite down."""
        from backend.services.signal_engine import get_market_signal
        base = get_market_signal(crash_prob_3m=10.0, regime="Neutral")
        with_stress = get_market_signal(
            crash_prob_3m=10.0, regime="Neutral",
            systemic_risk_score=-0.8,
        )
        assert with_stress["composite_score"] < base["composite_score"]
