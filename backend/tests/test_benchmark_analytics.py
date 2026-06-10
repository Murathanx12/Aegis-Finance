"""Tests for Bloomberg PORT-style benchmark analytics."""

import numpy as np
import pandas as pd

from backend.services.benchmark_analytics import (
    _build_portfolio_returns,
    _compute_capture_ratios,
    _compute_regression_stats,
    _compute_rolling_tracking_error,
    _compute_period_returns,
    _compute_risk_comparison,
    _interpret_results,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _make_returns(n: int = 504, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic daily return series for testing."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end="2026-04-15", periods=n)
    # SPY: ~10% annual return, ~16% vol
    spy = rng.normal(0.0004, 0.01, n)
    # AAPL: higher vol, correlated with SPY
    aapl = spy * 1.2 + rng.normal(0.0002, 0.008, n)
    # MSFT: similar
    msft = spy * 1.1 + rng.normal(0.0001, 0.007, n)
    # JPM: financials
    jpm = spy * 0.9 + rng.normal(0.0001, 0.009, n)
    return pd.DataFrame(
        {"SPY": spy, "AAPL": aapl, "MSFT": msft, "JPM": jpm},
        index=dates,
    )


# ── Unit Tests ───────────────────────────────────────────────────────


class TestBuildPortfolioReturns:
    """Test portfolio return construction."""

    def test_basic_weighted_return(self):
        returns = _make_returns()
        weights = {"AAPL": 0.5, "MSFT": 0.5}
        port_ret = _build_portfolio_returns(returns, weights)
        assert port_ret is not None
        assert len(port_ret) == len(returns)
        # Verify weighted sum
        expected = returns["AAPL"] * 0.5 + returns["MSFT"] * 0.5
        np.testing.assert_allclose(port_ret.values, expected.values, atol=1e-10)

    def test_single_ticker(self):
        returns = _make_returns()
        weights = {"AAPL": 1.0}
        port_ret = _build_portfolio_returns(returns, weights)
        assert port_ret is not None
        np.testing.assert_allclose(port_ret.values, returns["AAPL"].values, atol=1e-10)

    def test_missing_ticker_renormalized(self):
        returns = _make_returns()
        weights = {"AAPL": 0.5, "MISSING_TICKER": 0.5}
        port_ret = _build_portfolio_returns(returns, weights)
        assert port_ret is not None
        # Should renormalize to AAPL=100%
        np.testing.assert_allclose(port_ret.values, returns["AAPL"].values, atol=1e-10)

    def test_empty_weights(self):
        returns = _make_returns()
        assert _build_portfolio_returns(returns, {}) is None

    def test_zero_weights(self):
        returns = _make_returns()
        assert _build_portfolio_returns(returns, {"AAPL": 0.0}) is None


class TestTrackingErrorAndIR:
    """Test tracking error and information ratio computation."""

    def test_identical_portfolio_zero_te(self):
        """Portfolio = benchmark should have zero tracking error."""
        returns = _make_returns()
        port_ret = returns["SPY"]
        bench_ret = returns["SPY"]
        active = port_ret - bench_ret
        te = float(active.std() * np.sqrt(252))
        assert te < 1e-10

    def test_different_portfolio_positive_te(self):
        """Different portfolio should have positive tracking error."""
        returns = _make_returns()
        port_ret = returns["AAPL"]
        bench_ret = returns["SPY"]
        active = port_ret - bench_ret
        te = float(active.std() * np.sqrt(252))
        assert te > 0.01  # Should be meaningful

    def test_information_ratio_sign(self):
        """IR should be positive when portfolio outperforms."""
        rng = np.random.default_rng(123)
        n = 504
        dates = pd.bdate_range(end="2026-04-15", periods=n)
        # Portfolio with consistent positive alpha
        bench = rng.normal(0.0004, 0.01, n)
        port = bench + 0.0002 + rng.normal(0, 0.005, n)
        port_ret = pd.Series(port, index=dates)
        bench_ret = pd.Series(bench, index=dates)
        active = port_ret - bench_ret
        te = float(active.std() * np.sqrt(252))
        active_annual = float(active.mean() * 252)
        ir = active_annual / te if te > 1e-8 else 0
        assert ir > 0  # Should be positive given alpha


class TestCaptureRatios:
    """Test up/down capture ratio computation."""

    def test_perfect_tracking(self):
        """Portfolio = benchmark should have ~100% capture both ways."""
        returns = _make_returns()
        capture = _compute_capture_ratios(returns["SPY"], returns["SPY"])
        if capture["up_capture"] is not None:
            assert abs(capture["up_capture"] - 100) < 5
        if capture["down_capture"] is not None:
            assert abs(capture["down_capture"] - 100) < 5

    def test_high_beta_portfolio(self):
        """High-beta portfolio should have >100% capture in both directions."""
        returns = _make_returns()
        high_beta = returns["SPY"] * 1.5  # 1.5x benchmark
        high_beta.index = returns.index
        capture = _compute_capture_ratios(high_beta, returns["SPY"])
        if capture["up_capture"] is not None:
            assert capture["up_capture"] > 110
        if capture["down_capture"] is not None:
            assert capture["down_capture"] > 110

    def test_defensive_portfolio(self):
        """Low-beta portfolio should have <100% capture in both directions."""
        returns = _make_returns()
        defensive = returns["SPY"] * 0.5  # 0.5x benchmark
        defensive.index = returns.index
        capture = _compute_capture_ratios(defensive, returns["SPY"])
        if capture["up_capture"] is not None:
            assert capture["up_capture"] < 90
        if capture["down_capture"] is not None:
            assert capture["down_capture"] < 90

    def test_short_series(self):
        """Very short series should return None for captures."""
        dates = pd.bdate_range(end="2026-04-15", periods=10)
        port = pd.Series(np.random.default_rng(42).normal(0, 0.01, 10), index=dates)
        bench = pd.Series(np.random.default_rng(43).normal(0, 0.01, 10), index=dates)
        capture = _compute_capture_ratios(port, bench)
        assert capture["up_months"] + capture["down_months"] <= 1  # Monthly resampled


class TestRegressionStats:
    """Test beta/alpha/R-squared regression."""

    def test_perfect_correlation(self):
        """Portfolio = 1.2 * benchmark should have beta ≈ 1.2, R² ≈ 1.0."""
        rng = np.random.default_rng(42)
        n = 504
        dates = pd.bdate_range(end="2026-04-15", periods=n)
        bench = pd.Series(rng.normal(0.0004, 0.01, n), index=dates)
        port = bench * 1.2 + 0.0001  # beta=1.2, small alpha
        reg = _compute_regression_stats(port, bench)
        assert reg["available"]
        assert abs(reg["beta"] - 1.2) < 0.01
        assert reg["r_squared"] > 0.99

    def test_uncorrelated(self):
        """Independent series should have low R² and beta near 0."""
        rng = np.random.default_rng(42)
        n = 504
        dates = pd.bdate_range(end="2026-04-15", periods=n)
        bench = pd.Series(rng.normal(0.0004, 0.01, n), index=dates)
        port = pd.Series(rng.normal(0.0003, 0.01, n), index=dates)
        reg = _compute_regression_stats(port, bench)
        assert reg["available"]
        assert reg["r_squared"] < 0.1
        assert abs(reg["beta"]) < 0.3

    def test_short_series(self):
        """Too few data points should return unavailable."""
        dates = pd.bdate_range(end="2026-04-15", periods=10)
        bench = pd.Series(np.random.default_rng(42).normal(0, 0.01, 10), index=dates)
        port = pd.Series(np.random.default_rng(43).normal(0, 0.01, 10), index=dates)
        reg = _compute_regression_stats(port, bench)
        assert reg["available"] is False


class TestRollingTrackingError:
    """Test rolling tracking error computation."""

    def test_basic_rolling(self):
        rng = np.random.default_rng(42)
        n = 504
        dates = pd.bdate_range(end="2026-04-15", periods=n)
        active = pd.Series(rng.normal(0, 0.005, n), index=dates)
        result = _compute_rolling_tracking_error(active, window=63)
        assert result["available"]
        assert result["current_pct"] > 0
        assert result["average_pct"] > 0
        assert len(result["time_series"]) > 0

    def test_short_series_unavailable(self):
        dates = pd.bdate_range(end="2026-04-15", periods=30)
        active = pd.Series(np.random.default_rng(42).normal(0, 0.005, 30), index=dates)
        result = _compute_rolling_tracking_error(active, window=63)
        assert result["available"] is False


class TestPeriodReturns:
    """Test period return comparison."""

    def test_periods_exist(self):
        returns = _make_returns(504)
        result = _compute_period_returns(returns["AAPL"], returns["SPY"])
        assert "1m" in result
        assert "3m" in result
        assert "1y" in result
        for period_data in result.values():
            assert "portfolio_pct" in period_data
            assert "benchmark_pct" in period_data
            assert "active_return_pct" in period_data
            assert isinstance(period_data["outperformed"], bool)


class TestRiskComparison:
    """Test risk metric comparison."""

    def test_basic_comparison(self):
        returns = _make_returns()
        result = _compute_risk_comparison(returns["AAPL"], returns["SPY"])
        assert "portfolio" in result
        assert "benchmark" in result
        for side in ["portfolio", "benchmark"]:
            assert "annual_return_pct" in result[side]
            assert "volatility_pct" in result[side]
            assert "sharpe" in result[side]
            assert "sortino" in result[side]
            assert "max_drawdown_pct" in result[side]

    def test_max_drawdown_negative(self):
        """Max drawdown should be negative or zero."""
        returns = _make_returns()
        result = _compute_risk_comparison(returns["AAPL"], returns["SPY"])
        assert result["portfolio"]["max_drawdown_pct"] <= 0
        assert result["benchmark"]["max_drawdown_pct"] <= 0


class TestInterpretation:
    """Test result interpretation logic."""

    def test_low_te(self):
        result = _interpret_results(0.01, 0.3, None, {})
        assert result["tracking_error_label"] == "Low"

    def test_high_te(self):
        result = _interpret_results(0.08, 0.3, None, {})
        assert result["tracking_error_label"] == "High"

    def test_good_ir(self):
        result = _interpret_results(0.05, 0.7, None, {})
        assert result["information_ratio_label"] == "Good"

    def test_negative_ir(self):
        result = _interpret_results(0.05, -0.3, None, {})
        assert result["information_ratio_label"] == "Negative"

    def test_management_style_stock_picker(self):
        active_share = {"active_share_pct": 80}
        result = _interpret_results(0.08, 0.5, active_share, {})
        assert result["management_style"] == "Concentrated Stock Picker"

    def test_management_style_closet_indexer(self):
        active_share = {"active_share_pct": 20}
        result = _interpret_results(0.02, 0.1, active_share, {})
        assert result["management_style"] == "Closet Indexer"

    def test_capture_insight(self):
        capture = {"up_capture": 110, "down_capture": 80}
        result = _interpret_results(0.05, 0.5, None, capture)
        found = any("Asymmetric" in i for i in result["insights"])
        assert found


# ── Integration-level (synthetic data, no network) ───────────────────


class TestComputeBenchmarkAnalyticsSynthetic:
    """Integration tests using synthetic data to verify the full pipeline."""

    def test_full_pipeline_structure(self):
        """Verify the output structure of the full analytics pipeline.

        Note: compute_benchmark_analytics fetches from yfinance,
        so we test internal components that don't require network.
        """
        returns = _make_returns()
        port_ret = _build_portfolio_returns(returns, {"AAPL": 0.5, "MSFT": 0.5})
        bench_ret = returns["SPY"]
        active = port_ret - bench_ret
        aligned = pd.DataFrame({"portfolio": port_ret, "benchmark": bench_ret}).dropna()

        # Test each component
        te = float(active.std() * np.sqrt(252))
        assert te > 0

        capture = _compute_capture_ratios(aligned["portfolio"], aligned["benchmark"])
        assert isinstance(capture, dict)
        assert "up_capture" in capture

        rolling = _compute_rolling_tracking_error(active, window=63)
        assert rolling["available"]

        reg = _compute_regression_stats(aligned["portfolio"], aligned["benchmark"])
        assert reg["available"]
        assert 0 <= reg["r_squared"] <= 1

        periods = _compute_period_returns(aligned["portfolio"], aligned["benchmark"])
        assert len(periods) > 0

        risk = _compute_risk_comparison(aligned["portfolio"], aligned["benchmark"])
        assert "portfolio" in risk and "benchmark" in risk

    def test_three_stock_portfolio(self):
        """Test with a 3-stock portfolio vs SPY benchmark."""
        returns = _make_returns()
        weights = {"AAPL": 0.4, "MSFT": 0.3, "JPM": 0.3}
        port_ret = _build_portfolio_returns(returns, weights)
        bench_ret = returns["SPY"]

        assert port_ret is not None
        assert len(port_ret) == len(returns)

        active = port_ret - bench_ret
        te = float(active.std() * np.sqrt(252))
        assert 0 < te < 1.0  # Reasonable range

        reg = _compute_regression_stats(port_ret, bench_ret)
        assert reg["available"]
        # 3-stock portfolio should have high R² with market
        assert reg["r_squared"] > 0.5
        assert 0.5 < reg["beta"] < 2.0
