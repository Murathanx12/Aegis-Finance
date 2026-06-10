"""
Tests for the real portfolio analyzer.

Uses synthetic price data — no network calls. Covers metric computation,
concentration flags, correlation clusters, and edge cases.
"""

from datetime import datetime
from unittest.mock import patch

import numpy as np
import pandas as pd

from backend.schemas.portfolio_intelligence import HoldingInput
from backend.services.portfolio_intelligence.real_analyzer import (
    _compute_weights,
    _compute_portfolio_returns,
    _compute_basic_metrics,
    _compute_beta_tracking,
    compute_concentration_flags,
    compute_correlation_clusters,
    analyze_portfolio,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

FIXTURE_TICKERS = [
    "TVTX", "DKNG", "ALMS", "MSTR", "APLT", "FSLR", "AMZN",
    "TTWO", "SLDP", "MRVL", "RGTI", "APMX", "NTLA",
]


def _make_prices(tickers: list[str], n_days: int = 504, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic price data with realistic drift and volatility."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=datetime.now(), periods=n_days)
    data = {}
    for i, ticker in enumerate(tickers):
        drift = 0.0003 + rng.normal(0, 0.0001)
        vol = 0.015 + abs(rng.normal(0, 0.005))
        returns = rng.normal(drift, vol, n_days)
        prices = 50 * np.exp(np.cumsum(returns))
        data[ticker] = prices
    return pd.DataFrame(data, index=dates)


def _make_holdings(tickers: list[str] | None = None) -> list[HoldingInput]:
    """Create test holdings from fixture tickers."""
    if tickers is None:
        tickers = FIXTURE_TICKERS
    return [HoldingInput(ticker=t, shares=100.0) for t in tickers]


SYNTHETIC_PRICES = _make_prices(FIXTURE_TICKERS + ["SPY", "AGG"])


# ── _compute_weights ────────────────────────────────────────────────────────


class TestComputeWeights:
    def test_weights_sum_to_one(self):
        holdings = _make_holdings()
        weights = _compute_weights(holdings, SYNTHETIC_PRICES)
        assert abs(sum(weights.values()) - 1.0) < 1e-6

    def test_all_tickers_present(self):
        holdings = _make_holdings()
        weights = _compute_weights(holdings, SYNTHETIC_PRICES)
        for h in holdings:
            assert h.ticker in weights

    def test_weights_proportional_to_value(self):
        holdings = [
            HoldingInput(ticker="TVTX", shares=200.0),
            HoldingInput(ticker="DKNG", shares=100.0),
        ]
        prices = _make_prices(["TVTX", "DKNG"], n_days=10)
        # Make prices equal so TVTX should be ~2x DKNG weight
        prices["TVTX"] = 100.0
        prices["DKNG"] = 100.0
        weights = _compute_weights(holdings, prices)
        assert abs(weights["TVTX"] - 2 * weights["DKNG"]) < 1e-6

    def test_missing_ticker_excluded(self):
        holdings = [
            HoldingInput(ticker="TVTX", shares=100.0),
            HoldingInput(ticker="ZZZZ", shares=100.0),
        ]
        prices = _make_prices(["TVTX"], n_days=10)
        weights = _compute_weights(holdings, prices)
        assert "TVTX" in weights
        assert "ZZZZ" not in weights
        assert abs(weights["TVTX"] - 1.0) < 1e-6


# ── _compute_portfolio_returns ──────────────────────────────────────────────


class TestPortfolioReturns:
    def test_returns_length(self):
        weights = {"TVTX": 0.5, "DKNG": 0.5}
        returns = _compute_portfolio_returns(weights, SYNTHETIC_PRICES)
        assert len(returns) > 400

    def test_returns_reasonable_range(self):
        weights = {"TVTX": 0.5, "DKNG": 0.5}
        returns = _compute_portfolio_returns(weights, SYNTHETIC_PRICES)
        assert returns.abs().max() < 0.5  # no single-day 50% move
        assert returns.mean() > -0.01  # not catastrophically negative

    def test_single_holding(self):
        weights = {"TVTX": 1.0}
        returns = _compute_portfolio_returns(weights, SYNTHETIC_PRICES)
        expected = SYNTHETIC_PRICES["TVTX"].pct_change().dropna()
        # Should match single-stock returns
        aligned = pd.DataFrame({"port": returns, "exp": expected}).dropna()
        np.testing.assert_allclose(
            aligned["port"].values, aligned["exp"].values, atol=1e-10
        )

    def test_empty_weights(self):
        returns = _compute_portfolio_returns({}, SYNTHETIC_PRICES)
        assert len(returns) == 0


# ── _compute_basic_metrics ──────────────────────────────────────────────────


class TestBasicMetrics:
    def test_positive_returns_positive_sharpe(self):
        rng = np.random.default_rng(42)
        # Strong positive drift
        returns = pd.Series(rng.normal(0.001, 0.01, 252))
        metrics = _compute_basic_metrics(returns)
        assert metrics["total_return"] > 0
        assert metrics["annualized_return"] > 0
        assert metrics["sharpe_ratio"] > 0

    def test_zero_vol_no_sharpe(self):
        returns = pd.Series([0.0] * 100)
        metrics = _compute_basic_metrics(returns)
        assert metrics["sharpe_ratio"] is None

    def test_too_few_observations(self):
        returns = pd.Series([0.01, -0.01, 0.005])
        metrics = _compute_basic_metrics(returns)
        assert metrics["total_return"] == 0.0

    def test_annualized_return_reasonable(self):
        rng = np.random.default_rng(99)
        returns = pd.Series(rng.normal(0.0004, 0.012, 504))
        metrics = _compute_basic_metrics(returns)
        assert -0.5 < metrics["annualized_return"] < 0.5


# ── _compute_beta_tracking ──────────────────────────────────────────────────


class TestBetaTracking:
    def test_spy_beta_near_one_for_spy(self):
        spy_returns = SYNTHETIC_PRICES["SPY"].pct_change().dropna()
        result = _compute_beta_tracking(spy_returns, "SPY", SYNTHETIC_PRICES)
        assert result["beta_vs_spy"] is not None
        assert abs(result["beta_vs_spy"] - 1.0) < 0.05

    def test_tracking_error_zero_for_self(self):
        spy_returns = SYNTHETIC_PRICES["SPY"].pct_change().dropna()
        result = _compute_beta_tracking(spy_returns, "SPY", SYNTHETIC_PRICES)
        assert result["tracking_error_vs_spy"] is not None
        assert abs(result["tracking_error_vs_spy"]) < 0.01

    def test_no_benchmark_returns_none(self):
        port_returns = SYNTHETIC_PRICES["TVTX"].pct_change().dropna()
        result = _compute_beta_tracking(port_returns, "MISSING", SYNTHETIC_PRICES)
        assert result["beta_vs_spy"] is None
        assert result["tracking_error_vs_spy"] is None


# ── compute_concentration_flags ─────────────────────────────────────────────


class TestConcentrationFlags:
    def test_single_name_warning(self):
        weights = {"AAPL": 0.15, "MSFT": 0.05, "GOOGL": 0.80}
        flags = compute_concentration_flags(weights)
        single_name_flags = [f for f in flags if f.flag_type == "single_name"]
        assert len(single_name_flags) >= 2  # AAPL + GOOGL
        critical = [f for f in single_name_flags if f.severity == "critical"]
        assert len(critical) >= 1  # GOOGL at 80%

    def test_no_flags_when_diversified(self):
        weights = {f"STOCK_{i}": 0.05 for i in range(20)}
        flags = compute_concentration_flags(weights, sector_map={})
        single_name_flags = [f for f in flags if f.flag_type == "single_name"]
        assert len(single_name_flags) == 0

    def test_sector_concentration_flag(self):
        sector_map = {"AAPL": "Technology", "MSFT": "Technology", "NVDA": "Technology"}
        weights = {"AAPL": 0.20, "MSFT": 0.15, "NVDA": 0.10}
        flags = compute_concentration_flags(weights, sector_map=sector_map)
        sector_flags = [f for f in flags if f.flag_type == "sector"]
        assert len(sector_flags) >= 1
        assert "Technology" in sector_flags[0].message

    def test_biotech_overconcentration_fixture(self):
        """Murat's portfolio has 4+ biotech names — should flag sector."""
        sector_map = {
            "TVTX": "Healthcare", "ALMS": "Healthcare",
            "APLT": "Healthcare", "NTLA": "Healthcare", "APMX": "Healthcare",
            "DKNG": "Consumer Disc.", "AMZN": "Consumer Disc.",
            "MSTR": "Technology", "MRVL": "Technology", "RGTI": "Technology",
            "FSLR": "Energy", "TTWO": "Communications", "SLDP": "Industrials",
        }
        # Equal weight for 13 tickers → ~7.7% each. 5 healthcare = ~38%
        weights = {t: 1.0 / 13 for t in FIXTURE_TICKERS}
        flags = compute_concentration_flags(weights, sector_map=sector_map)
        # Healthcare at ~38% is below 40% threshold, so no sector flag with equal weight
        # But if we overweight biotech...
        weights["TVTX"] = 0.15
        weights["ALMS"] = 0.12
        weights["APLT"] = 0.10
        weights["NTLA"] = 0.08
        weights["APMX"] = 0.07
        remaining = 1.0 - sum(weights[t] for t in ["TVTX", "ALMS", "APLT", "NTLA", "APMX"])
        other_tickers = [t for t in FIXTURE_TICKERS if t not in ["TVTX", "ALMS", "APLT", "NTLA", "APMX"]]
        for t in other_tickers:
            weights[t] = remaining / len(other_tickers)

        flags = compute_concentration_flags(weights, sector_map=sector_map)
        sector_flags = [f for f in flags if f.flag_type == "sector"]
        assert any("Healthcare" in f.message for f in sector_flags)

    def test_tech_overconcentration_fixture(self):
        """Tech cluster (MSTR, MRVL, RGTI, AMZN) should trigger when overweighted."""
        sector_map = {
            "MSTR": "Technology", "MRVL": "Technology",
            "RGTI": "Technology", "AMZN": "Technology",
        }
        weights = {"MSTR": 0.15, "MRVL": 0.12, "RGTI": 0.10, "AMZN": 0.13}
        flags = compute_concentration_flags(weights, sector_map=sector_map)
        sector_flags = [f for f in flags if f.flag_type == "sector"]
        assert any("Technology" in f.message for f in sector_flags)

    def test_high_beta_flag(self):
        weights = {"MSTR": 0.40, "TVTX": 0.30, "DKNG": 0.30}
        beta_map = {"MSTR": 2.5, "TVTX": 1.8, "DKNG": 1.5}
        flags = compute_concentration_flags(weights, beta_map=beta_map)
        beta_flags = [f for f in flags if f.flag_type == "beta"]
        assert len(beta_flags) == 1
        assert "elevated" in beta_flags[0].message.lower()

    def test_low_beta_flag(self):
        weights = {"AGG": 0.50, "TLT": 0.30, "SHY": 0.20}
        beta_map = {"AGG": 0.05, "TLT": 0.15, "SHY": 0.02}
        flags = compute_concentration_flags(weights, beta_map=beta_map)
        beta_flags = [f for f in flags if f.flag_type == "beta"]
        assert len(beta_flags) == 1
        assert "low" in beta_flags[0].message.lower()

    def test_no_beta_flag_without_map(self):
        weights = {"MSTR": 1.0}
        flags = compute_concentration_flags(weights, beta_map=None)
        beta_flags = [f for f in flags if f.flag_type == "beta"]
        assert len(beta_flags) == 0


# ── compute_correlation_clusters ────────────────────────────────────────────


class TestCorrelationClusters:
    def test_perfect_correlation_detected(self):
        rng = np.random.default_rng(42)
        base = rng.normal(0, 0.01, 200)
        df = pd.DataFrame({
            "A": base + rng.normal(0, 0.001, 200),
            "B": base + rng.normal(0, 0.001, 200),
            "C": base + rng.normal(0, 0.001, 200),
            "D": rng.normal(0, 0.01, 200),  # independent
        })
        clusters = compute_correlation_clusters(df, threshold=0.70)
        assert len(clusters) >= 1
        assert "A" in clusters[0]["tickers"]
        assert "B" in clusters[0]["tickers"]
        assert "C" in clusters[0]["tickers"]

    def test_no_cluster_when_uncorrelated(self):
        rng = np.random.default_rng(42)
        df = pd.DataFrame({
            "A": rng.normal(0, 0.01, 200),
            "B": rng.normal(0, 0.01, 200),
            "C": rng.normal(0, 0.01, 200),
            "D": rng.normal(0, 0.01, 200),
        })
        clusters = compute_correlation_clusters(df, threshold=0.70)
        assert len(clusters) == 0

    def test_too_few_observations(self):
        rng = np.random.default_rng(42)
        df = pd.DataFrame({
            "A": rng.normal(0, 0.01, 30),
            "B": rng.normal(0, 0.01, 30),
            "C": rng.normal(0, 0.01, 30),
        })
        clusters = compute_correlation_clusters(df)
        assert len(clusters) == 0

    def test_too_few_columns(self):
        rng = np.random.default_rng(42)
        df = pd.DataFrame({"A": rng.normal(0, 0.01, 200), "B": rng.normal(0, 0.01, 200)})
        clusters = compute_correlation_clusters(df)
        assert len(clusters) == 0


# ── analyze_portfolio (integration with mocks) ─────────────────────────────


class TestAnalyzePortfolio:
    @patch("backend.services.portfolio_intelligence.real_analyzer._fetch_prices")
    def test_returns_snapshot_response(self, mock_fetch):
        mock_fetch.return_value = SYNTHETIC_PRICES
        holdings = _make_holdings()
        result = analyze_portfolio(holdings)
        assert result.portfolio_id == "real"
        assert result.date is not None
        assert len(result.weights) > 0

    @patch("backend.services.portfolio_intelligence.real_analyzer._fetch_prices")
    def test_metrics_populated(self, mock_fetch):
        mock_fetch.return_value = SYNTHETIC_PRICES
        holdings = _make_holdings()
        result = analyze_portfolio(holdings)
        assert result.metrics is not None
        assert result.metrics.total_return != 0
        assert result.metrics.annualized_volatility > 0
        assert result.metrics.max_drawdown <= 0

    @patch("backend.services.portfolio_intelligence.real_analyzer._fetch_prices")
    def test_sharpe_ratio_reasonable(self, mock_fetch):
        mock_fetch.return_value = SYNTHETIC_PRICES
        holdings = _make_holdings()
        result = analyze_portfolio(holdings)
        assert result.metrics is not None
        if result.metrics.sharpe_ratio is not None:
            assert -5 < result.metrics.sharpe_ratio < 5

    @patch("backend.services.portfolio_intelligence.real_analyzer._fetch_prices")
    def test_weights_sum_to_one(self, mock_fetch):
        mock_fetch.return_value = SYNTHETIC_PRICES
        holdings = _make_holdings()
        result = analyze_portfolio(holdings)
        total = sum(result.weights.values())
        assert abs(total - 1.0) < 0.001

    @patch("backend.services.portfolio_intelligence.real_analyzer._fetch_prices")
    def test_sector_exposure_populated(self, mock_fetch):
        mock_fetch.return_value = SYNTHETIC_PRICES
        holdings = _make_holdings()
        result = analyze_portfolio(holdings)
        assert result.metrics is not None
        assert len(result.metrics.sector_exposure) > 0

    @patch("backend.services.portfolio_intelligence.real_analyzer._fetch_prices")
    def test_no_data_returns_error_flag(self, mock_fetch):
        mock_fetch.return_value = None
        holdings = _make_holdings()
        result = analyze_portfolio(holdings)
        assert result.metrics is None
        assert len(result.flags) > 0
        assert result.flags[0].flag_type == "data"

    @patch("backend.services.portfolio_intelligence.real_analyzer._fetch_prices")
    def test_single_holding(self, mock_fetch):
        mock_fetch.return_value = SYNTHETIC_PRICES
        holdings = [HoldingInput(ticker="TVTX", shares=100.0)]
        result = analyze_portfolio(holdings)
        assert result.metrics is not None
        assert len(result.weights) == 1
        assert abs(result.weights["TVTX"] - 1.0) < 1e-6

    @patch("backend.services.portfolio_intelligence.real_analyzer._fetch_prices")
    def test_flags_include_concentration(self, mock_fetch):
        """Single large holding should generate single-name flag."""
        prices = SYNTHETIC_PRICES.copy()
        # Make one stock much more expensive so it dominates
        prices["AMZN"] = prices["AMZN"] * 100
        mock_fetch.return_value = prices
        holdings = _make_holdings()
        result = analyze_portfolio(holdings)
        single_name_flags = [f for f in result.flags if f.flag_type == "single_name"]
        assert len(single_name_flags) >= 1
        assert any("AMZN" in f.message for f in single_name_flags)

    @patch("backend.services.portfolio_intelligence.real_analyzer._fetch_prices")
    def test_empty_prices_handled(self, mock_fetch):
        mock_fetch.return_value = pd.DataFrame()
        holdings = _make_holdings()
        result = analyze_portfolio(holdings)
        assert result.metrics is None
        assert any(f.flag_type == "data" for f in result.flags)
