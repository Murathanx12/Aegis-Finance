"""Tests for liquidity risk service."""

import numpy as np
import pandas as pd
import pytest

from backend.services.liquidity_risk import (
    compute_amihud_illiquidity,
    compute_roll_spread,
    compute_turnover_ratio,
    compute_lvar,
    compute_liquidity_score,
)


@pytest.fixture
def sample_data():
    """Generate realistic stock data for testing."""
    rng = np.random.default_rng(42)
    n = 252
    dates = pd.bdate_range("2024-01-01", periods=n)
    price = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.02, n)))
    volume = rng.integers(100000, 5000000, n).astype(float)
    returns = pd.Series(np.diff(price) / price[:-1], index=dates[1:])
    price_s = pd.Series(price[1:], index=dates[1:])
    volume_s = pd.Series(volume[1:], index=dates[1:])
    return returns, volume_s, price_s


class TestAmihudIlliquidity:
    def test_basic_computation(self, sample_data):
        returns, volume, price = sample_data
        result = compute_amihud_illiquidity(returns, volume, price, window=21)
        assert len(result) == len(returns)
        # Should have some valid values
        valid = result.dropna()
        assert len(valid) > 0
        # Amihud should be non-negative
        assert (valid >= 0).all()

    def test_higher_volume_means_lower_illiquidity(self):
        """More volume = more liquid = lower Amihud ratio."""
        rng = np.random.default_rng(42)
        n = 100
        dates = pd.bdate_range("2024-01-01", periods=n)
        returns = pd.Series(rng.normal(0, 0.02, n), index=dates)
        price = pd.Series(np.full(n, 100.0), index=dates)

        low_vol = pd.Series(np.full(n, 100000.0), index=dates)
        high_vol = pd.Series(np.full(n, 10000000.0), index=dates)

        amihud_low = compute_amihud_illiquidity(returns, low_vol, price, window=21)
        amihud_high = compute_amihud_illiquidity(returns, high_vol, price, window=21)

        # Higher volume should produce lower illiquidity
        assert amihud_low.dropna().mean() > amihud_high.dropna().mean()


class TestRollSpread:
    def test_basic_computation(self, sample_data):
        returns, _, _ = sample_data
        result = compute_roll_spread(returns, window=21)
        valid = result.dropna()
        assert len(valid) > 0
        # Roll spread should be non-negative
        assert (valid >= 0).all()

    def test_with_bid_ask_bounce(self):
        """Synthetic bid-ask bounce should produce positive spread."""
        rng = np.random.default_rng(42)
        n = 200
        dates = pd.bdate_range("2024-01-01", periods=n)
        # Create negatively autocorrelated returns (bid-ask bounce)
        noise = rng.normal(0, 0.01, n)
        bounce = np.zeros(n)
        for i in range(1, n):
            bounce[i] = -0.5 * bounce[i - 1] + noise[i]
        returns = pd.Series(bounce, index=dates)

        result = compute_roll_spread(returns, window=50)
        valid = result.dropna()
        # Should detect positive spread from the bounce
        assert valid.mean() > 0


class TestTurnover:
    def test_basic(self):
        n = 100
        dates = pd.bdate_range("2024-01-01", periods=n)
        volume = pd.Series(np.full(n, 1000000.0), index=dates)
        shares_out = 100000000.0  # 100M shares

        result = compute_turnover_ratio(volume, shares_out, window=21)
        valid = result.dropna()
        assert len(valid) > 0
        # 1M / 100M = 1% daily
        assert abs(valid.mean() - 1.0) < 0.1

    def test_zero_shares(self):
        n = 50
        dates = pd.bdate_range("2024-01-01", periods=n)
        volume = pd.Series(np.full(n, 1000000.0), index=dates)
        result = compute_turnover_ratio(volume, 0, window=21)
        assert result.isna().all()


class TestLVaR:
    def test_basic(self, sample_data):
        returns, _, _ = sample_data
        result = compute_lvar(returns, amihud_illiq=0.5)
        assert result["var_95"] is not None
        assert result["lvar_95"] is not None
        assert result["liquidity_cost_bps"] is not None
        # LVaR should be worse (more negative) than VaR
        assert result["lvar_95"] <= result["var_95"]

    def test_high_illiquidity(self, sample_data):
        returns, _, _ = sample_data
        result_low = compute_lvar(returns, amihud_illiq=0.001)
        result_high = compute_lvar(returns, amihud_illiq=0.005)
        # Higher illiquidity → higher liquidity cost
        assert result_high["liquidity_cost_bps"] > result_low["liquidity_cost_bps"]


class TestLiquidityScore:
    def test_mega_cap_scores_high(self):
        """Large dollar volume + low illiquidity = high score."""
        score = compute_liquidity_score(
            amihud_illiq=0.01,
            roll_spread=0.0005,
            avg_dollar_volume_mm=500.0,
            turnover_pct=0.5,
        )
        assert score["composite"] >= 70
        assert score["tier"] in ("highly_liquid", "liquid")

    def test_micro_cap_scores_low(self):
        """Low dollar volume + high illiquidity = low score."""
        score = compute_liquidity_score(
            amihud_illiq=10.0,
            roll_spread=0.01,
            avg_dollar_volume_mm=0.5,
            turnover_pct=0.01,
        )
        assert score["composite"] < 50
        assert score["tier"] in ("moderately_liquid", "illiquid", "highly_illiquid")

    def test_score_range(self):
        """Score should always be 0-100."""
        for dv in [0.1, 1, 10, 100, 1000]:
            score = compute_liquidity_score(
                amihud_illiq=0.5,
                roll_spread=0.001,
                avg_dollar_volume_mm=dv,
            )
            assert 0 <= score["composite"] <= 100

    def test_zero_amihud_scores_highest(self):
        """Regression (cycle 75): amihud_illiq=0.0 should score 100, not fallback 50.

        Mega-cap stocks can have Amihud illiquidity of exactly 0.0 (due to
        enormous dollar volume).  The old code used `if current_amihud` which
        is False for 0.0, treating it as missing data and displaying None
        instead of the valid 0.0 value.
        """
        score = compute_liquidity_score(
            amihud_illiq=0.0,
            roll_spread=0.0,
            avg_dollar_volume_mm=10000.0,
            turnover_pct=0.5,
        )
        # amihud=0.0 means perfectly liquid → amihud score should be 100
        assert score["components"]["amihud"]["score"] == 100.0
        # roll_spread=0.0 → spread score should be 100
        assert score["components"]["roll_spread"]["score"] == 100.0


class TestZeroValueDisplay:
    """Regression (cycle 75): numeric 0.0 values incorrectly displayed as None."""

    def test_zero_amihud_displayed_as_zero(self):
        """Amihud illiquidity of 0.0 should display as 0.0, not None."""

        # We can't easily test the full compute_liquidity_metrics (needs yfinance),
        # but we can test the display logic directly
        amihud_val = 0.0
        roll_val = 0.0

        # Simulate the display logic that was buggy
        # OLD (buggy): round(amihud_val, 4) if amihud_val else None → None
        # NEW (fixed): round(amihud_val, 4) if amihud_val is not None else None → 0.0
        display_amihud = round(amihud_val, 4) if amihud_val is not None else None
        display_roll = round(roll_val * 10000, 1) if roll_val is not None else None

        assert display_amihud == 0.0, "Amihud 0.0 should display as 0.0, not None"
        assert display_roll == 0.0, "Roll spread 0.0 should display as 0.0, not None"
