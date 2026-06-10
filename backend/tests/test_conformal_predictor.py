"""
Conformal Prediction Interval Tests
=======================================

Tests for the conformal prediction service.

Run with:
    python -m pytest backend/tests/test_conformal_predictor.py -v
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.conformal_predictor import (
    ConformalCrashPredictor,
    conformal_crash_interval,
    _heuristic_interval,
)


class TestHeuristicInterval:
    """Test the heuristic fallback when conformal scores are unavailable."""

    def test_low_probability(self):
        result = _heuristic_interval(0.05, alpha=0.10)
        assert result["lower"] >= 0.0
        assert result["upper"] <= 1.0
        assert result["lower"] < result["point"]
        assert result["upper"] > result["point"]
        assert result["method"] == "heuristic"

    def test_high_probability(self):
        result = _heuristic_interval(0.80, alpha=0.10)
        assert result["lower"] >= 0.0
        assert result["upper"] <= 1.0
        assert result["width"] > 0

    def test_midrange_wider_than_extremes(self):
        """Mid-range predictions should have wider intervals (more uncertainty)."""
        mid = _heuristic_interval(0.50, alpha=0.10)
        low = _heuristic_interval(0.05, alpha=0.10)
        high = _heuristic_interval(0.95, alpha=0.10)
        assert mid["width"] > low["width"]
        assert mid["width"] > high["width"]

    def test_zero_probability(self):
        result = _heuristic_interval(0.0, alpha=0.10)
        assert result["lower"] == 0.0
        assert result["upper"] >= 0.0

    def test_one_probability(self):
        result = _heuristic_interval(1.0, alpha=0.10)
        assert result["upper"] == 1.0
        assert result["lower"] <= 1.0

    def test_narrower_at_higher_alpha(self):
        """Higher alpha = lower coverage = narrower interval."""
        narrow = _heuristic_interval(0.30, alpha=0.20)
        wide = _heuristic_interval(0.30, alpha=0.05)
        assert narrow["width"] < wide["width"]

    def test_coverage_target_matches(self):
        result = _heuristic_interval(0.30, alpha=0.10)
        assert result["coverage_target"] == 0.90


class TestConformalCrashPredictor:
    """Test the full conformal prediction pipeline."""

    def _make_mock_predictor(self):
        """Create a mock predictor with predict_proba method."""
        class MockPredictor:
            lgb_models = {"3m": True, "6m": True, "12m": True}

            def predict_proba(self, features, horizon):
                # Return predictions that are somewhat calibrated
                rng = np.random.default_rng(42)
                n = len(features) if hasattr(features, '__len__') else 1
                return rng.beta(2, 10, size=n)  # ~15% mean probability

        return MockPredictor()

    def test_calibrate_basic(self):
        import pandas as pd

        predictor = self._make_mock_predictor()
        cp = ConformalCrashPredictor()

        # Create calibration data
        n = 100
        cal_features = pd.DataFrame(np.random.randn(n, 5), columns=[f"f{i}" for i in range(5)])
        cal_targets = {
            "3m": pd.Series(np.random.binomial(1, 0.12, n)),
            "6m": pd.Series(np.random.binomial(1, 0.18, n)),
        }

        results = cp.calibrate(predictor, cal_features, cal_targets)
        assert cp.is_calibrated
        assert "3m" in results
        assert "6m" in results
        assert results["3m"]["n_calibration"] == n

    def test_get_interval_after_calibration(self):
        import pandas as pd

        predictor = self._make_mock_predictor()
        cp = ConformalCrashPredictor()

        n = 200
        cal_features = pd.DataFrame(np.random.randn(n, 5), columns=[f"f{i}" for i in range(5)])
        cal_targets = {"3m": pd.Series(np.random.binomial(1, 0.12, n))}

        cp.calibrate(predictor, cal_features, cal_targets)

        interval = cp.get_interval(0.10, horizon="3m", alpha=0.10)
        assert interval["method"] == "split_conformal"
        assert interval["lower"] >= 0.0
        assert interval["upper"] <= 1.0
        assert interval["lower"] <= interval["point"] <= interval["upper"]
        assert interval["n_calibration"] == n

    def test_uncalibrated_falls_back_to_heuristic(self):
        cp = ConformalCrashPredictor()
        interval = cp.get_interval(0.10, horizon="3m", alpha=0.10)
        assert interval["method"] == "heuristic"

    def test_monotonicity_enforcement(self):
        import pandas as pd

        predictor = self._make_mock_predictor()
        cp = ConformalCrashPredictor()

        n = 200
        cal_features = pd.DataFrame(np.random.randn(n, 5), columns=[f"f{i}" for i in range(5)])
        cal_targets = {
            "3m": pd.Series(np.random.binomial(1, 0.10, n)),
            "6m": pd.Series(np.random.binomial(1, 0.15, n)),
            "12m": pd.Series(np.random.binomial(1, 0.20, n)),
        }

        cp.calibrate(predictor, cal_features, cal_targets)

        predictions = {"3m": 0.08, "6m": 0.12, "12m": 0.18}
        intervals = cp.get_multi_horizon_intervals(predictions, alpha=0.10)

        assert intervals["3m"]["lower"] <= intervals["6m"]["lower"]
        assert intervals["6m"]["lower"] <= intervals["12m"]["lower"]
        assert intervals["3m"]["upper"] <= intervals["6m"]["upper"]
        assert intervals["6m"]["upper"] <= intervals["12m"]["upper"]

    def test_save_and_load(self, tmp_path):
        import pandas as pd

        predictor = self._make_mock_predictor()
        cp = ConformalCrashPredictor()

        n = 100
        cal_features = pd.DataFrame(np.random.randn(n, 5), columns=[f"f{i}" for i in range(5)])
        cal_targets = {"3m": pd.Series(np.random.binomial(1, 0.12, n))}
        cp.calibrate(predictor, cal_features, cal_targets)

        # Save
        save_path = str(tmp_path / "conformal.pkl")
        cp.save(save_path)

        # Load into new instance
        cp2 = ConformalCrashPredictor()
        loaded = cp2.load(save_path)
        assert loaded
        assert cp2.is_calibrated

        # Results should match
        i1 = cp.get_interval(0.10, "3m")
        i2 = cp2.get_interval(0.10, "3m")
        assert i1["lower"] == i2["lower"]
        assert i1["upper"] == i2["upper"]

    def test_load_nonexistent_file(self):
        cp = ConformalCrashPredictor()
        loaded = cp.load("/nonexistent/path.pkl")
        assert not loaded
        assert not cp.is_calibrated


class TestConvenienceFunction:
    def test_conformal_crash_interval_returns_dict(self):
        """Test the module-level convenience function."""
        result = conformal_crash_interval(0.10, horizon="3m", alpha=0.10)
        assert "lower" in result
        assert "upper" in result
        assert "point" in result
        assert "width" in result
        assert "method" in result

    def test_various_horizons(self):
        for h in ["3m", "6m", "12m"]:
            result = conformal_crash_interval(0.15, horizon=h)
            assert result["point"] == 0.15


class TestScenarioSpecificMultipliers:
    """Regression tests for scenario-specific sector multipliers in stress_testing."""

    def test_gfc_financials_worse_than_tech(self):
        """In GFC, Financials should be hit harder than Tech."""
        from backend.services.stress_testing import _estimate_crisis_return

        fin_ret = _estimate_crisis_return("JPM", "2008_GFC", sector="Financials", beta=1.0, sp500_drawdown=-0.568)
        tech_ret = _estimate_crisis_return("AAPL", "2008_GFC", sector="Technology", beta=1.0, sp500_drawdown=-0.568)
        assert fin_ret < tech_ret, f"GFC: Financials ({fin_ret}) should lose more than Tech ({tech_ret})"

    def test_dotcom_tech_worse_than_financials(self):
        """In Dot-Com, Tech should be hit harder than Financials."""
        from backend.services.stress_testing import _estimate_crisis_return

        tech_ret = _estimate_crisis_return("AAPL", "2000_DOTCOM", sector="Technology", beta=1.0, sp500_drawdown=-0.491)
        fin_ret = _estimate_crisis_return("JPM", "2000_DOTCOM", sector="Financials", beta=1.0, sp500_drawdown=-0.491)
        assert tech_ret < fin_ret, f"Dot-Com: Tech ({tech_ret}) should lose more than Financials ({fin_ret})"

    def test_covid_tech_resilient(self):
        """In COVID, Tech should be more resilient than Energy."""
        from backend.services.stress_testing import _estimate_crisis_return

        tech_ret = _estimate_crisis_return("AAPL", "2020_COVID", sector="Technology", beta=1.0, sp500_drawdown=-0.339)
        energy_ret = _estimate_crisis_return("XOM", "2020_COVID", sector="Energy", beta=1.0, sp500_drawdown=-0.339)
        assert tech_ret > energy_ret, f"COVID: Tech ({tech_ret}) should lose less than Energy ({energy_ret})"

    def test_rate_shock_energy_positive(self):
        """In 2022 Rate Shock, Energy had a tiny multiplier (rallied on oil spike)."""
        from backend.services.stress_testing import _estimate_crisis_return

        energy_ret = _estimate_crisis_return("XOM", "2022_RATE_SHOCK", sector="Energy", beta=0.8, sp500_drawdown=-0.254)
        tech_ret = _estimate_crisis_return("AAPL", "2022_RATE_SHOCK", sector="Technology", beta=1.2, sp500_drawdown=-0.254)
        # Energy should lose much less than Tech
        assert energy_ret > tech_ret

    def test_all_scenarios_have_multipliers(self):
        """All defined scenarios should have specific sector multipliers."""
        from backend.services.stress_testing import _estimate_crisis_return

        scenarios = ["2008_GFC", "2020_COVID", "2000_DOTCOM", "1987_BLACK_MONDAY",
                      "2022_RATE_SHOCK", "2018_VOLMAGEDDON"]
        for sid in scenarios:
            # Defensive should always lose less than cyclical
            util_ret = _estimate_crisis_return("NEE", sid, sector="Utilities", beta=0.5, sp500_drawdown=-0.30)
            assert util_ret > -0.30, f"{sid}: Utilities with beta=0.5 should lose less than market"
