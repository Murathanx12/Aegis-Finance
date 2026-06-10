"""Tests for fixed income analytics (unit tests, no network)."""

import numpy as np
import pandas as pd

from backend.services.fixed_income import (
    compute_yield_curve_analysis,
    compute_credit_spread_analysis,
)


def _make_fred_data():
    """Create mock FRED data for testing."""
    dates = pd.bdate_range("2023-01-01", periods=300)
    return {
        "DGS3MO": pd.Series(np.random.uniform(4.5, 5.5, 300), index=dates),
        "DGS2": pd.Series(np.random.uniform(4.0, 5.0, 300), index=dates),
        "DGS5": pd.Series(np.random.uniform(3.8, 4.5, 300), index=dates),
        "DGS10": pd.Series(np.random.uniform(3.5, 4.5, 300), index=dates),
        "DGS30": pd.Series(np.random.uniform(3.8, 4.8, 300), index=dates),
        "BAMLH0A0HYM2": pd.Series(np.random.uniform(3.0, 5.0, 300), index=dates),
        "BAMLC0A0CM": pd.Series(np.random.uniform(1.0, 2.0, 300), index=dates),
        "DFII10": pd.Series(np.random.uniform(1.5, 2.5, 300), index=dates),
        "T10YIE": pd.Series(np.random.uniform(2.0, 2.5, 300), index=dates),
    }


class TestYieldCurveAnalysis:
    def test_basic_output_structure(self):
        fred_data = _make_fred_data()
        result = compute_yield_curve_analysis(fred_data)
        assert "yields" in result
        assert "spreads" in result
        assert "shape" in result
        assert "interpretation" in result

    def test_yields_parsed(self):
        fred_data = _make_fred_data()
        result = compute_yield_curve_analysis(fred_data)
        assert "10y" in result["yields"]
        assert "2y" in result["yields"]

    def test_spreads_computed(self):
        fred_data = _make_fred_data()
        result = compute_yield_curve_analysis(fred_data)
        assert result["spreads"]["10y_2y"] is not None
        assert result["spreads"]["10y_3m"] is not None

    def test_inverted_curve_detected(self):
        """When short rates > long rates, should detect inversion."""
        dates = pd.bdate_range("2023-01-01", periods=300)
        fred_data = {
            "DGS3MO": pd.Series(np.full(300, 5.5), index=dates),
            "DGS2": pd.Series(np.full(300, 5.0), index=dates),
            "DGS5": pd.Series(np.full(300, 4.0), index=dates),
            "DGS10": pd.Series(np.full(300, 3.5), index=dates),
            "DGS30": pd.Series(np.full(300, 3.8), index=dates),
        }
        result = compute_yield_curve_analysis(fred_data)
        assert len(result["inversions"]) > 0
        assert result["shape"] in ("deeply_inverted", "partially_inverted")

    def test_normal_curve_detected(self):
        """When long rates > short rates, should detect normal shape."""
        dates = pd.bdate_range("2023-01-01", periods=300)
        fred_data = {
            "DGS3MO": pd.Series(np.full(300, 2.0), index=dates),
            "DGS2": pd.Series(np.full(300, 2.5), index=dates),
            "DGS5": pd.Series(np.full(300, 3.5), index=dates),
            "DGS10": pd.Series(np.full(300, 4.0), index=dates),
            "DGS30": pd.Series(np.full(300, 4.5), index=dates),
        }
        result = compute_yield_curve_analysis(fred_data)
        assert result["shape"] in ("normal", "steep")

    def test_empty_data(self):
        result = compute_yield_curve_analysis({})
        assert "error" in result

    def test_curvature_computed(self):
        fred_data = _make_fred_data()
        result = compute_yield_curve_analysis(fred_data)
        assert result["curvature"] is not None


class TestCreditSpreadAnalysis:
    def test_basic_output_structure(self):
        fred_data = _make_fred_data()
        result = compute_credit_spread_analysis(fred_data)
        assert "spreads" in result
        assert "stress" in result

    def test_spreads_have_context(self):
        fred_data = _make_fred_data()
        result = compute_credit_spread_analysis(fred_data)
        if "hy_oas" in result["spreads"]:
            hy = result["spreads"]["hy_oas"]
            assert "current" in hy
            assert "mean_1y" in hy

    def test_stress_detection(self):
        """High HY spread should trigger stress signal."""
        dates = pd.bdate_range("2023-01-01", periods=300)
        fred_data = {
            "BAMLH0A0HYM2": pd.Series(np.full(300, 6.0), index=dates),
            "BAMLC0A0CM": pd.Series(np.full(300, 1.5), index=dates),
        }
        result = compute_credit_spread_analysis(fred_data)
        assert result["stress"]["level"] == "elevated"

    def test_real_yield_extracted(self):
        fred_data = _make_fred_data()
        result = compute_credit_spread_analysis(fred_data)
        assert result["real_yield_10y"] is not None

    def test_breakeven_extracted(self):
        fred_data = _make_fred_data()
        result = compute_credit_spread_analysis(fred_data)
        assert result["breakeven_inflation_10y"] is not None
