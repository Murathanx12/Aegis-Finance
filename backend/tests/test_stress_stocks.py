"""
Stock Analysis Stress Tests
==============================

Tests analyze_stock() across representative tickers from different sectors.
Validates that returned metrics are finite and within reasonable ranges.

Run with:
    python -m pytest backend/tests/test_stress_stocks.py -v
    python -m pytest backend/tests/test_stress_stocks.py -v -m slow  # only slow tests
"""

import logging
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.stock_analyzer import analyze_stock

logger = logging.getLogger(__name__)

# Representative tickers spanning sectors and cap tiers
STRESS_TICKERS = ["AAPL", "JPM", "XOM", "TSLA", "NEE", "PLD", "PLTR", "BRK-B"]


@pytest.mark.slow
class TestStockAnalysis:
    """Stress test analyze_stock() across a diverse set of tickers."""

    @pytest.mark.parametrize("ticker", STRESS_TICKERS)
    def test_analyze_stock_returns_result(self, ticker):
        """analyze_stock() should return a non-None dict for valid tickers."""
        result = analyze_stock(ticker)
        assert result is not None, f"{ticker}: analyze_stock returned None"
        assert isinstance(result, dict)
        assert result["ticker"] == ticker

    @pytest.mark.parametrize("ticker", STRESS_TICKERS)
    def test_expected_return_finite_and_reasonable(self, ticker):
        """5Y expected return should be finite and within -50% to +500%."""
        result = analyze_stock(ticker)
        if result is None:
            pytest.skip(f"{ticker}: analyze_stock returned None (data issue)")

        exp_ret = result["expected_return"]
        assert np.isfinite(exp_ret), f"{ticker}: expected_return is not finite: {exp_ret}"
        # expected_return is in percentage (e.g. 50.0 means 50%)
        assert -50 <= exp_ret <= 500, (
            f"{ticker}: expected_return {exp_ret:.1f}% outside [-50%, +500%]"
        )

    @pytest.mark.parametrize("ticker", STRESS_TICKERS)
    def test_sharpe_ratio_finite(self, ticker):
        """Sharpe ratio should be finite."""
        result = analyze_stock(ticker)
        if result is None:
            pytest.skip(f"{ticker}: analyze_stock returned None (data issue)")

        sharpe = result["sharpe"]
        assert np.isfinite(sharpe), f"{ticker}: Sharpe is not finite: {sharpe}"
        # Sharpe for individual stocks typically -1 to +2
        assert -3.0 <= sharpe <= 5.0, (
            f"{ticker}: Sharpe {sharpe:.2f} outside [-3, +5] range"
        )

    @pytest.mark.parametrize("ticker", STRESS_TICKERS)
    def test_prob_loss_between_0_and_100(self, ticker):
        """P(Loss over 5Y) should be between 0% and 100%."""
        result = analyze_stock(ticker)
        if result is None:
            pytest.skip(f"{ticker}: analyze_stock returned None (data issue)")

        prob_loss = result["prob_loss_5y"]
        assert 0 <= prob_loss <= 100, (
            f"{ticker}: prob_loss_5y {prob_loss:.1f}% outside [0, 100]"
        )

    @pytest.mark.parametrize("ticker", STRESS_TICKERS)
    def test_max_drawdown_in_range(self, ticker):
        """Average max drawdown should be between -100% and 0%."""
        result = analyze_stock(ticker)
        if result is None:
            pytest.skip(f"{ticker}: analyze_stock returned None (data issue)")

        max_dd = result["avg_max_drawdown"]
        assert np.isfinite(max_dd), f"{ticker}: max_drawdown is not finite"
        # avg_max_drawdown is in percentage and negative (e.g. -35.0 means -35%)
        assert -100 <= max_dd <= 0, (
            f"{ticker}: avg_max_drawdown {max_dd:.1f}% outside [-100%, 0%]"
        )

    @pytest.mark.parametrize("ticker", STRESS_TICKERS)
    def test_volatility_reasonable(self, ticker):
        """Annualized volatility should be 15-80% (capped in code)."""
        result = analyze_stock(ticker)
        if result is None:
            pytest.skip(f"{ticker}: analyze_stock returned None (data issue)")

        vol = result["volatility"]
        assert np.isfinite(vol), f"{ticker}: volatility is not finite"
        # volatility is in percentage
        assert 10 <= vol <= 85, (
            f"{ticker}: volatility {vol:.1f}% outside [10%, 85%]"
        )

    @pytest.mark.parametrize("ticker", STRESS_TICKERS)
    def test_current_price_positive(self, ticker):
        """Current price should be positive."""
        result = analyze_stock(ticker)
        if result is None:
            pytest.skip(f"{ticker}: analyze_stock returned None (data issue)")

        assert result["current_price"] > 0, (
            f"{ticker}: current_price is not positive: {result['current_price']}"
        )

    @pytest.mark.parametrize("ticker", STRESS_TICKERS)
    def test_p05_less_than_p95(self, ticker):
        """5th percentile price should be less than 95th percentile."""
        result = analyze_stock(ticker)
        if result is None:
            pytest.skip(f"{ticker}: analyze_stock returned None (data issue)")

        assert result["p05_price"] < result["p95_price"], (
            f"{ticker}: p05 ({result['p05_price']:.2f}) >= p95 ({result['p95_price']:.2f})"
        )
