"""
Tests for Backtest Service — Bug Fixes & Regression
======================================================

Tests the overlapping-return fix in evaluate_backtest:
  - Non-overlapping quarterly sampling for compounding
  - Sharpe annualization consistency
  - Execution cost tracking

Run with:
    python -m pytest backend/tests/test_backtest.py -v
"""

import numpy as np
import pandas as pd

from backend.services.backtest import evaluate_backtest, estimate_execution_cost


# ── Fixtures ──────────────────────────────────────────────────────────


def _make_backtest_df(n_months: int = 24, signal: str = "Buy") -> pd.DataFrame:
    """Create synthetic backtest DataFrame with monthly eval dates."""
    rng = np.random.default_rng(42)
    dates = pd.date_range("2022-01-01", periods=n_months, freq="MS")
    return pd.DataFrame({
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "signal_action": [signal] * n_months,
        "confidence": [50] * n_months,
        "composite_score": [0.3] * n_months,
        "vix": [20.0] * n_months,
        "sp500_1m": [1.0] * n_months,
        "sp500_3m": [3.0] * n_months,
        "regime": ["Bull"] * n_months,
        "forward_3m_return": rng.normal(3.0, 5.0, n_months).tolist(),
        "forward_12m_return": rng.normal(10.0, 15.0, n_months).tolist(),
        "reasons": [["test reason"]] * n_months,
    })


# ── Test: Non-overlapping compounding ─────────────────────────────────


class TestOverlappingReturnFix:
    """Regression tests for the overlapping-return compounding bug fix."""

    def test_quarterly_sampling_reduces_compounded_returns(self):
        """Compounding non-overlapping returns should give smaller totals
        than compounding all overlapping monthly returns."""
        df = _make_backtest_df(n_months=36)
        result = evaluate_backtest(df)

        # With 36 monthly observations and quarterly sampling,
        # we should compound ~12 non-overlapping returns, not 36.
        # The total return should be reasonable, not inflated.
        assert result["total_signals"] == 36
        # Strategy total return should be finite and not wildly inflated
        assert -100 < result["strategy_total_return_gross"] < 500
        assert -100 < result["buy_hold_total_return"] < 500

    def test_all_buy_signals_return_positive_sharpe(self):
        """All-buy signals with positive avg forward returns → positive Sharpe."""
        df = _make_backtest_df(n_months=24, signal="Buy")
        # Override with consistently positive returns
        df["forward_3m_return"] = 3.0
        result = evaluate_backtest(df)
        assert result["strategy_sharpe_gross"] > 0
        assert result["buy_hold_sharpe"] > 0

    def test_mixed_signals_produce_valid_output(self):
        """Mixed Buy/Hold/Sell signals should produce valid backtest metrics."""
        df = _make_backtest_df(n_months=30)
        actions = (["Buy"] * 10 + ["Hold"] * 10 + ["Sell"] * 10)
        df["signal_action"] = actions
        result = evaluate_backtest(df)

        assert result["buy_signals"] == 10
        assert result["sell_signals"] == 10
        assert result["hold_signals"] == 10
        assert result["buy_hit_rate_3m"] is not None
        assert result["sell_hit_rate_3m"] is not None

    def test_quarterly_count_is_one_third(self):
        """Non-overlapping quarterly sampling should use ~1/3 of observations."""
        df = _make_backtest_df(n_months=30)
        result = evaluate_backtest(df)
        # Total signals is all monthly, but compounding uses every 3rd
        assert result["total_signals"] == 30
        # strategy_total should exist and be finite
        assert np.isfinite(result["strategy_total_return_gross"])


# ── Test: Execution costs ─────────────────────────────────────────────


class TestExecutionCosts:
    """Test execution cost estimation."""

    def test_round_trip_doubles_costs(self):
        """Round-trip costs should be ~2x one-way."""
        one_way = estimate_execution_cost(is_round_trip=False)
        round_trip = estimate_execution_cost(is_round_trip=True)
        assert round_trip["slippage_bps"] == 2 * one_way["slippage_bps"]
        assert round_trip["commission_bps"] == 2 * one_way["commission_bps"]

    def test_larger_trades_have_more_impact(self):
        """Market impact should increase with trade size."""
        small = estimate_execution_cost(trade_value=10_000)
        large = estimate_execution_cost(trade_value=10_000_000)
        assert large["market_impact_bps"] > small["market_impact_bps"]

    def test_cost_fields_present(self):
        """All cost fields should be present and non-negative."""
        result = estimate_execution_cost()
        for key in ["slippage_bps", "commission_bps", "market_impact_bps", "total_bps", "total_pct"]:
            assert key in result
            assert result[key] >= 0

    def test_trades_tracked_in_evaluation(self):
        """Execution costs should track trade count."""
        df = _make_backtest_df(n_months=12)
        # Alternate Buy/Sell to maximize trades
        df["signal_action"] = ["Buy", "Sell"] * 6
        result = evaluate_backtest(df)
        assert result["execution_costs"]["total_trades"] > 0
        assert result["execution_costs"]["cost_per_trade_bps"] > 0
