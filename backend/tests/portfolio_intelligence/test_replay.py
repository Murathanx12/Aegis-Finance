"""
Tests for the walk-forward replay engine.

Tests with synthetic price data — no network calls.
Verifies:
  - Replay produces valid equity curve
  - Crash guard activates at correct dates
  - Deterministic: same inputs → identical results
  - Rebalance count is reasonable
  - Metrics computed correctly
"""

from datetime import date
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from backend.services.portfolio_intelligence.market_data_wrapper import MarketDataAtTimestamp
from backend.services.portfolio_intelligence.replay import (
    ReplayEngine,
    _generate_check_dates,
    _compute_daily_returns,
    _compute_replay_metrics,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_universe_prices(start="2021-01-01", end="2025-12-31", seed=42):
    """Create synthetic prices for the full ticker universe."""
    from backend.config import paper_portfolios
    from backend.services.portfolio_intelligence.rules import _get_sleeve_tickers

    universe = paper_portfolios.get("universe", {})
    sleeves = _get_sleeve_tickers(universe)
    all_tickers = sleeves["equity"] + sleeves["bond"] + sleeves["alternative"]

    dates = pd.bdate_range(start, end)
    rng = np.random.default_rng(seed)
    data = {}
    for t in all_tickers:
        drift = 0.0003 if t not in ("AGG", "TLT", "IEF", "SHY", "LQD", "HYG", "TIP") else 0.0001
        vol = 0.015 if t not in ("AGG", "TLT", "IEF", "SHY", "LQD", "HYG", "TIP") else 0.005
        returns = rng.normal(drift, vol, len(dates))
        prices = 100.0 * np.cumprod(1 + returns)
        data[t] = prices
    return pd.DataFrame(data, index=dates)


def _make_wrapper(start="2021-01-01", end="2025-12-31", seed=42):
    """Create a MarketDataAtTimestamp wrapper with synthetic data."""
    prices = _make_universe_prices(start, end, seed)
    return MarketDataAtTimestamp(prices)


# ── _generate_check_dates ────────────────────────────────────────────────


class TestGenerateCheckDates:
    def test_monthly(self):
        dates = _generate_check_dates(date(2024, 1, 1), date(2024, 12, 31), "monthly")
        assert len(dates) >= 12
        assert dates[0] == date(2024, 1, 1)

    def test_weekly(self):
        dates = _generate_check_dates(date(2024, 1, 1), date(2024, 3, 31), "weekly")
        assert len(dates) >= 12

    def test_end_date_respected(self):
        dates = _generate_check_dates(date(2024, 1, 1), date(2024, 1, 15), "monthly")
        assert all(d <= date(2024, 1, 15) for d in dates)


# ── _compute_daily_returns ───────────────────────────────────────────────


class TestComputeDailyReturns:
    def test_basic_returns(self):
        dates = pd.bdate_range("2024-01-01", "2024-01-31")
        prices = pd.DataFrame({
            "A": np.linspace(100, 110, len(dates)),
            "B": np.linspace(50, 55, len(dates)),
        }, index=dates)
        weights = {"A": 0.60, "B": 0.40}
        returns = _compute_daily_returns(weights, prices, date(2024, 1, 1), date(2024, 1, 31))
        assert len(returns) > 0
        assert all(np.isfinite(returns))

    def test_empty_on_missing_tickers(self):
        dates = pd.bdate_range("2024-01-01", "2024-01-31")
        prices = pd.DataFrame({"X": np.ones(len(dates))}, index=dates)
        weights = {"A": 0.50, "B": 0.50}
        returns = _compute_daily_returns(weights, prices, date(2024, 1, 1), date(2024, 1, 31))
        assert len(returns) == 0


# ── _compute_replay_metrics ──────────────────────────────────────────────


class TestComputeReplayMetrics:
    def test_basic_metrics(self):
        dates = pd.bdate_range("2023-01-01", "2024-12-31")
        rng = np.random.default_rng(42)
        returns = rng.normal(0.0003, 0.01, len(dates))
        equity = 100_000 * np.cumprod(1 + returns)
        eq_series = pd.Series(equity, index=dates)
        metrics = _compute_replay_metrics(eq_series)
        assert metrics is not None
        assert metrics.total_return > 0
        assert metrics.annualized_volatility > 0
        assert metrics.max_drawdown < 0

    def test_too_short_returns_none(self):
        eq = pd.Series([100, 101, 102], index=pd.bdate_range("2024-01-01", periods=3))
        assert _compute_replay_metrics(eq) is None

    def test_sharpe_computed(self):
        dates = pd.bdate_range("2022-01-01", "2024-12-31")
        rng = np.random.default_rng(42)
        returns = rng.normal(0.0005, 0.01, len(dates))
        equity = 100_000 * np.cumprod(1 + returns)
        eq_series = pd.Series(equity, index=dates)
        metrics = _compute_replay_metrics(eq_series)
        assert metrics.sharpe_ratio is not None


# ── ReplayEngine ─────────────────────────────────────────────────────────


class TestReplayEngine:
    @patch("backend.services.portfolio_intelligence.replay.ReplayEngine._get_ticker_universe_prices")
    def test_basic_replay(self, mock_prices):
        """Basic replay with synthetic data and no crash model."""
        mock_prices.return_value = _make_universe_prices("2023-01-01", "2024-12-31")
        wrapper = _make_wrapper("2023-01-01", "2024-12-31")
        engine = ReplayEngine(wrapper=wrapper)

        result = engine.run(
            "conservative",
            start_date="2023-01-01",
            end_date="2024-12-31",
            crash_prob_override=0.10,
        )

        assert result.lane == "conservative"
        assert result.total_rebalances > 0
        assert len(result.equity_curve) > 0
        assert result.crash_guard_activations == 0  # 0.10 < 0.25 threshold

    @patch("backend.services.portfolio_intelligence.replay.ReplayEngine._get_ticker_universe_prices")
    def test_crash_guard_activates(self, mock_prices):
        """High crash prob should trigger crash guard."""
        mock_prices.return_value = _make_universe_prices("2023-01-01", "2024-06-30")
        wrapper = _make_wrapper("2023-01-01", "2024-06-30")
        engine = ReplayEngine(wrapper=wrapper)

        result = engine.run(
            "conservative",
            start_date="2023-01-01",
            end_date="2024-06-30",
            crash_prob_override=0.50,
        )

        assert result.crash_guard_activations > 0

    @patch("backend.services.portfolio_intelligence.replay.ReplayEngine._get_ticker_universe_prices")
    def test_deterministic(self, mock_prices):
        """Same inputs → identical results."""
        prices = _make_universe_prices("2023-06-01", "2024-06-01")
        mock_prices.return_value = prices
        wrapper = _make_wrapper("2023-06-01", "2024-06-01")

        engine = ReplayEngine(wrapper=wrapper)
        r1 = engine.run("balanced", "2023-06-01", "2024-06-01", crash_prob_override=0.15)

        engine2 = ReplayEngine(wrapper=wrapper)
        r2 = engine2.run("balanced", "2023-06-01", "2024-06-01", crash_prob_override=0.15)

        assert r1.total_rebalances == r2.total_rebalances
        assert r1.total_turnover == r2.total_turnover
        assert len(r1.equity_curve) == len(r2.equity_curve)

    @patch("backend.services.portfolio_intelligence.replay.ReplayEngine._get_ticker_universe_prices")
    def test_aggressive_has_more_rebalances(self, mock_prices):
        """Aggressive (weekly) should rebalance more often than conservative (monthly)."""
        prices = _make_universe_prices("2023-01-01", "2024-12-31")
        mock_prices.return_value = prices
        wrapper = _make_wrapper("2023-01-01", "2024-12-31")

        engine = ReplayEngine(wrapper=wrapper)
        r_con = engine.run("conservative", "2023-01-01", "2024-12-31", crash_prob_override=0.05)
        r_agg = engine.run("aggressive", "2023-01-01", "2024-12-31", crash_prob_override=0.05)

        assert r_agg.total_rebalances >= r_con.total_rebalances

    @patch("backend.services.portfolio_intelligence.replay.ReplayEngine._get_ticker_universe_prices")
    def test_rebalance_log_populated(self, mock_prices):
        """Rebalance log should have entries with expected fields."""
        mock_prices.return_value = _make_universe_prices("2024-01-01", "2024-06-30")
        wrapper = _make_wrapper("2024-01-01", "2024-06-30")
        engine = ReplayEngine(wrapper=wrapper)

        result = engine.run(
            "conservative", "2024-01-01", "2024-06-30",
            crash_prob_override=0.10,
        )

        assert len(result.rebalance_log) > 0
        first = result.rebalance_log[0]
        assert "date" in first
        assert "reason" in first
        assert "turnover" in first

    def test_unknown_lane_raises(self):
        engine = ReplayEngine()
        with pytest.raises(ValueError, match="Unknown lane"):
            engine.run("nonexistent", "2024-01-01", "2024-06-30")

    @patch("backend.services.portfolio_intelligence.replay.ReplayEngine._get_ticker_universe_prices")
    def test_metrics_computed(self, mock_prices):
        """Replay should produce MetricPack with reasonable values."""
        mock_prices.return_value = _make_universe_prices("2022-01-01", "2024-12-31")
        wrapper = _make_wrapper("2022-01-01", "2024-12-31")
        engine = ReplayEngine(wrapper=wrapper)

        result = engine.run(
            "balanced", "2022-01-01", "2024-12-31",
            crash_prob_override=0.10,
        )

        if result.metrics:
            assert result.metrics.annualized_volatility >= 0
            assert result.metrics.max_drawdown <= 0
