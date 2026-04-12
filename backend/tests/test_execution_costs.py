"""Tests for execution cost modeling in backtest."""

import pytest
from backend.services.backtest import estimate_execution_cost


class TestExecutionCost:
    def test_output_keys(self):
        result = estimate_execution_cost()
        assert "slippage_bps" in result
        assert "commission_bps" in result
        assert "market_impact_bps" in result
        assert "total_bps" in result
        assert "total_pct" in result

    def test_round_trip_doubles_cost(self):
        one_way = estimate_execution_cost(is_round_trip=False)
        round_trip = estimate_execution_cost(is_round_trip=True)
        # Slippage + commission should double
        assert round_trip["slippage_bps"] == one_way["slippage_bps"] * 2
        assert round_trip["commission_bps"] == one_way["commission_bps"] * 2

    def test_larger_trade_higher_impact(self):
        small = estimate_execution_cost(trade_value=10000)
        large = estimate_execution_cost(trade_value=10000000)
        assert large["market_impact_bps"] > small["market_impact_bps"]

    def test_higher_volume_lower_impact(self):
        thin = estimate_execution_cost(avg_daily_volume_usd=1e7)
        liquid = estimate_execution_cost(avg_daily_volume_usd=1e10)
        assert thin["market_impact_bps"] > liquid["market_impact_bps"]

    def test_total_positive(self):
        result = estimate_execution_cost()
        assert result["total_bps"] > 0
        assert result["total_pct"] > 0

    def test_typical_spy_trade(self):
        """$100k SPY trade should be < 20 bps round trip."""
        result = estimate_execution_cost(
            trade_value=100000,
            avg_daily_volume_usd=30e9,  # SPY typical ADV
        )
        assert result["total_bps"] < 20

    def test_illiquid_stock_trade(self):
        """$100k in an illiquid stock should be significantly more costly."""
        result = estimate_execution_cost(
            trade_value=100000,
            avg_daily_volume_usd=5e6,  # Illiquid micro-cap
        )
        assert result["total_bps"] > 20
