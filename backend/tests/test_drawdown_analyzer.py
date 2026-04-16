"""Tests for drawdown and rolling return analysis."""

import numpy as np
import pandas as pd
import pytest

from backend.services.drawdown_analyzer import (
    analyze_drawdowns,
    compute_rolling_returns,
    compute_rolling_risk_metrics,
)


@pytest.fixture
def trending_up():
    """Price series that trends up with occasional drawdowns."""
    rng = np.random.default_rng(42)
    n = 1260  # 5 years
    dates = pd.bdate_range("2020-01-01", periods=n)
    # Trending up with noise + two deliberate drawdowns
    base = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.015, n)))
    # Insert a -15% drawdown at day 300
    base[300:340] *= np.linspace(1.0, 0.85, 40)
    base[340:400] *= np.linspace(0.85, 1.0, 60)
    # Insert a -25% drawdown at day 700
    base[700:750] *= np.linspace(1.0, 0.75, 50)
    base[750:900] *= np.linspace(0.75, 1.0, 150)
    return pd.Series(base, index=dates)


@pytest.fixture
def short_series():
    """Very short price series."""
    dates = pd.bdate_range("2024-01-01", periods=10)
    return pd.Series(np.linspace(100, 105, 10), index=dates)


class TestAnalyzeDrawdowns:
    def test_detects_drawdowns(self, trending_up):
        result = analyze_drawdowns(trending_up, min_drawdown_pct=10.0)
        assert len(result["drawdowns"]) >= 1
        # Should find the -25% drawdown
        depths = [d["depth_pct"] for d in result["drawdowns"]]
        assert any(d < -20 for d in depths)

    def test_drawdown_has_required_fields(self, trending_up):
        result = analyze_drawdowns(trending_up, min_drawdown_pct=5.0)
        if result["drawdowns"]:
            dd = result["drawdowns"][0]
            assert "peak_date" in dd
            assert "trough_date" in dd
            assert "depth_pct" in dd
            assert "peak_to_trough_days" in dd
            assert "trough_to_recovery_days" in dd
            assert "total_days" in dd
            assert "recovered" in dd
            assert dd["depth_pct"] < 0  # Drawdowns are negative

    def test_recovery_time_positive(self, trending_up):
        result = analyze_drawdowns(trending_up, min_drawdown_pct=5.0)
        for dd in result["drawdowns"]:
            if dd["recovered"]:
                assert dd["trough_to_recovery_days"] >= 0
                assert dd["total_days"] > 0

    def test_summary_stats(self, trending_up):
        result = analyze_drawdowns(trending_up, min_drawdown_pct=5.0)
        summary = result["summary"]
        assert "n_drawdowns" in summary
        if summary["n_drawdowns"] > 0:
            assert "avg_depth_pct" in summary
            assert "max_depth_pct" in summary
            assert summary["max_depth_pct"] <= summary["avg_depth_pct"]  # max is more negative

    def test_short_series(self, short_series):
        result = analyze_drawdowns(short_series)
        assert result["drawdowns"] == []
        assert result["current"] is None

    def test_monotonic_up_no_drawdowns(self):
        """Pure uptrend should have no drawdowns above threshold."""
        dates = pd.bdate_range("2024-01-01", periods=252)
        prices = pd.Series(np.linspace(100, 150, 252), index=dates)
        result = analyze_drawdowns(prices, min_drawdown_pct=5.0)
        assert len(result["drawdowns"]) == 0


class TestRollingReturns:
    def test_basic_output(self, trending_up):
        result = compute_rolling_returns(trending_up, windows=[252])
        assert "1Y" in result
        r = result["1Y"]
        assert "current" in r
        assert "mean" in r
        assert "pct_positive" in r
        assert "series" in r
        assert len(r["series"]) > 0

    def test_multiple_windows(self, trending_up):
        result = compute_rolling_returns(trending_up, windows=[252, 756])
        assert "1Y" in result
        assert "3Y" in result

    def test_skips_insufficient_data(self, short_series):
        result = compute_rolling_returns(short_series, windows=[252])
        assert len(result) == 0

    def test_pct_positive_in_range(self, trending_up):
        result = compute_rolling_returns(trending_up, windows=[252])
        assert 0 <= result["1Y"]["pct_positive"] <= 100

    def test_percentiles_ordered(self, trending_up):
        result = compute_rolling_returns(trending_up, windows=[252])
        pctls = result["1Y"]["percentiles"]
        assert pctls["p5"] <= pctls["p25"] <= pctls["p75"] <= pctls["p95"]


class TestRollingRiskMetrics:
    def test_basic_output(self, trending_up):
        result = compute_rolling_risk_metrics(trending_up, window=252)
        assert "sharpe" in result
        assert "sortino" in result
        assert "max_drawdown" in result
        assert result["sharpe"]["current"] is not None
        assert result["sortino"]["current"] is not None

    def test_sharpe_has_series(self, trending_up):
        result = compute_rolling_risk_metrics(trending_up, window=252)
        assert len(result["sharpe"]["series"]) > 0

    def test_insufficient_data(self, short_series):
        result = compute_rolling_risk_metrics(short_series, window=252)
        assert result == {}

    def test_max_drawdown_negative(self, trending_up):
        result = compute_rolling_risk_metrics(trending_up, window=252)
        assert result["max_drawdown"]["worst"] < 0
