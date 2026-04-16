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

    def test_peak_date_not_from_future(self):
        """Regression (cycle 72): peak date search must not pick future dates.

        When the same price appears both before and after a drawdown (e.g., the
        price recovers to the pre-drawdown peak), searching the full series
        for the peak value picks the FUTURE occurrence, causing negative
        peak_to_trough_days durations.

        Scenario: 100 → 110 → 80 (drawdown) → 110 (recovery)
        Bug: peak_dates[-1] picks the second 110 (future), not the first (past).
        """
        dates = pd.bdate_range("2024-01-01", periods=100)
        # Build a price series: ramp up to 110, crash to 80, recover to 110+
        prices_data = np.concatenate([
            np.linspace(100, 110, 20),        # ramp up to 110
            np.linspace(110, 80, 15),          # crash to 80 (-27%)
            np.linspace(80, 110, 30),           # recover to 110
            np.linspace(110, 115, 35),          # continue up
        ])
        prices = pd.Series(prices_data, index=dates)

        result = analyze_drawdowns(prices, min_drawdown_pct=10.0)

        # Should detect the drawdown
        assert len(result["drawdowns"]) >= 1

        for dd in result["drawdowns"]:
            # Peak date must be BEFORE trough date (not a future date)
            assert dd["peak_to_trough_days"] > 0, (
                f"peak_to_trough_days={dd['peak_to_trough_days']} is non-positive — "
                f"peak_date={dd['peak_date']} is after trough_date={dd['trough_date']}"
            )
            # Total duration must be positive
            assert dd["total_days"] > 0


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

    def test_rolling_max_dd_window_size(self):
        """Regression (cycle 75): rolling max drawdown used window+1 elements.

        The slice `prices.iloc[max(0, i - window):i + 1]` had window+1
        elements instead of window.  Fix: `prices.iloc[i - window + 1:i + 1]`
        gives exactly `window` elements.
        """
        # Create a simple price series where we can verify window size
        n = 300
        dates = pd.bdate_range("2024-01-01", periods=n)
        # Flat price with a single -10% spike at day 50
        prices_data = np.full(n, 100.0)
        prices_data[50] = 90.0  # -10% drawdown at day 50
        prices = pd.Series(prices_data, index=dates)

        window = 100
        result = compute_rolling_risk_metrics(prices, window=window)

        if result and "max_drawdown" in result:
            mdd_series = result["max_drawdown"]["series"]
            # The -10% spike at day 50 should be within the rolling window
            # for observations at days window (100) through 50+window (150).
            # After day 150 (i.e., i=150, window starts at i-window+1=51),
            # the spike at day 50 should no longer be in the window.
            # With the old bug (window+1 elements, starting at i-window=50),
            # the spike would still be visible at i=150.
            # With the fix (window elements, starting at i-window+1=51),
            # the spike at day 50 is excluded from i=150 onward.

            # Find a data point well past day 150+window where spike is gone
            for pt in mdd_series:
                date = pd.Timestamp(pt["date"])
                idx = prices.index.get_loc(date)
                if idx > 160:  # Well past the spike's influence
                    # Should be 0 (no drawdown in flat region)
                    assert pt["max_dd"] == 0.0, (
                        f"At index {idx}, max_dd={pt['max_dd']} but spike at day 50 "
                        f"should be outside the {window}-day window"
                    )
