"""Tests for systemic risk indicators (turbulence index + absorption ratio)."""

import numpy as np
import pandas as pd
import pytest

from backend.services.systemic_risk import (
    compute_turbulence_index,
    compute_absorption_ratio,
    compute_systemic_risk,
)


def _make_returns(n_days=500, n_assets=6, seed=42):
    """Generate synthetic multi-asset daily returns."""
    rng = np.random.default_rng(seed)
    # Correlated returns with some structure
    cov = np.eye(n_assets) * 0.0004
    for i in range(n_assets):
        for j in range(n_assets):
            if i != j:
                cov[i, j] = 0.0001
    returns = rng.multivariate_normal(np.zeros(n_assets), cov, n_days)
    dates = pd.bdate_range("2020-01-01", periods=n_days)
    cols = ["SP500", "NASDAQ", "Russell", "Gold", "HYG", "LQD"][:n_assets]
    return pd.DataFrame(returns, index=dates, columns=cols)


class TestTurbulenceIndex:
    def test_output_shape(self):
        returns = _make_returns(400)
        turb = compute_turbulence_index(returns, window=252)
        assert len(turb) == len(returns)
        assert turb.name == "turbulence"

    def test_nan_before_window(self):
        returns = _make_returns(400)
        turb = compute_turbulence_index(returns, window=252)
        # First 252 values should be NaN
        assert turb.iloc[:252].isna().all()

    def test_values_non_negative(self):
        returns = _make_returns(400)
        turb = compute_turbulence_index(returns, window=252)
        valid = turb.dropna()
        assert (valid >= 0).all()

    def test_spike_on_extreme_returns(self):
        """Extreme multi-asset moves should produce high turbulence."""
        returns = _make_returns(400)
        # Inject a crisis day
        returns.iloc[350] = 0.05  # 5% move in all assets
        turb = compute_turbulence_index(returns, window=252)
        crisis_turb = turb.iloc[350]
        median_turb = turb.iloc[253:349].median()
        assert crisis_turb > median_turb * 2  # At least 2x median

    def test_minimum_assets(self):
        """Should return zeros with < 2 assets."""
        returns = _make_returns(400, n_assets=1)
        turb = compute_turbulence_index(returns.iloc[:, :1], window=252)
        assert (turb == 0).all()


class TestAbsorptionRatio:
    def test_output_shape(self):
        returns = _make_returns(400)
        ar = compute_absorption_ratio(returns, n_components=3, window=252)
        assert len(ar) == len(returns)
        assert ar.name == "absorption_ratio"

    def test_values_in_01(self):
        returns = _make_returns(400)
        ar = compute_absorption_ratio(returns, n_components=3, window=252)
        valid = ar.dropna()
        assert (valid >= 0).all()
        assert (valid <= 1).all()

    def test_more_components_higher_ratio(self):
        returns = _make_returns(400)
        ar3 = compute_absorption_ratio(returns, n_components=3, window=252)
        ar5 = compute_absorption_ratio(returns, n_components=5, window=252)
        # More components should capture more variance
        valid3 = ar3.dropna()
        valid5 = ar5.dropna()
        assert valid5.mean() >= valid3.mean()

    def test_high_correlation_high_absorption(self):
        """Perfectly correlated assets should have AR near 1.0."""
        rng = np.random.default_rng(42)
        base = rng.normal(0, 0.02, 400)
        # All assets move together
        data = pd.DataFrame({
            f"A{i}": base + rng.normal(0, 0.001, 400) for i in range(6)
        }, index=pd.bdate_range("2020-01-01", periods=400))
        ar = compute_absorption_ratio(data, n_components=1, window=252)
        valid = ar.dropna()
        # First PC should explain nearly all variance
        assert valid.mean() > 0.8


class TestComputeSystemicRisk:
    def test_output_keys(self):
        """Result should have all expected keys."""
        rng = np.random.default_rng(42)
        dates = pd.bdate_range("2020-01-01", periods=500)
        data = pd.DataFrame({
            "SP500": 100 + np.cumsum(rng.normal(0.0003, 0.01, 500)),
            "NASDAQ": 200 + np.cumsum(rng.normal(0.0004, 0.012, 500)),
            "Russell": 50 + np.cumsum(rng.normal(0.0002, 0.011, 500)),
            "Gold": 1800 + np.cumsum(rng.normal(0.0001, 0.008, 500)),
            "HYG": 80 + np.cumsum(rng.normal(0, 0.005, 500)),
            "LQD": 110 + np.cumsum(rng.normal(0, 0.003, 500)),
        }, index=dates)

        result = compute_systemic_risk(data)
        assert "turbulence_current" in result
        assert "turbulence_percentile" in result
        assert "absorption_ratio_current" in result
        assert "absorption_ratio_change_1m" in result
        assert "systemic_stress" in result
        assert isinstance(result["systemic_stress"], bool)

    def test_insufficient_data(self):
        """Short data should return empty result."""
        data = pd.DataFrame({"SP500": [100, 101], "NASDAQ": [200, 202]},
                            index=pd.bdate_range("2024-01-01", periods=2))
        result = compute_systemic_risk(data)
        assert result["turbulence_current"] is None
        assert result["systemic_stress"] is False

    def test_too_few_columns(self):
        """< 3 price columns should return empty result."""
        data = pd.DataFrame({"SP500": range(500), "VIX": range(500)},
                            index=pd.bdate_range("2020-01-01", periods=500))
        result = compute_systemic_risk(data)
        assert result["n_assets_used"] == 0
