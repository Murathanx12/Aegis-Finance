"""Tests for technical analysis service."""

import numpy as np
import pandas as pd
import pytest

from backend.services.technical_analysis import (
    compute_technical_indicators,
    get_ta_signal,
    get_ta_summary,
)


def _make_prices(n=300, start_price=100, seed=42):
    """Generate synthetic price series with trend and volatility."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0003, 0.015, n)
    prices = start_price * np.exp(np.cumsum(returns))
    dates = pd.bdate_range("2024-01-01", periods=n)
    return pd.Series(prices, index=dates, name="Close")


def _make_ohlcv(n=300, seed=42):
    """Generate OHLCV data."""
    close = _make_prices(n, seed=seed)
    rng = np.random.default_rng(seed + 1)
    high = close * (1 + rng.uniform(0, 0.02, n))
    low = close * (1 - rng.uniform(0, 0.02, n))
    volume = pd.Series(rng.integers(1_000_000, 10_000_000, n), index=close.index)
    return close, high, low, volume


class TestComputeIndicators:
    def test_basic_output_structure(self):
        close = _make_prices()
        result = compute_technical_indicators(close)
        assert "trend" in result
        assert "momentum" in result
        assert "volatility" in result
        assert "patterns" in result

    def test_trend_indicators_present(self):
        close = _make_prices()
        result = compute_technical_indicators(close)
        trend = result["trend"]
        assert "sma_20" in trend
        assert "sma_50" in trend
        assert "sma_200" in trend
        assert "macd" in trend
        assert "trend_direction" in trend

    def test_momentum_indicators_present(self):
        close = _make_prices()
        result = compute_technical_indicators(close)
        mom = result["momentum"]
        assert "rsi_14" in mom
        assert "rsi_interpretation" in mom
        assert "stochastic_k" in mom

    def test_volatility_indicators_present(self):
        close = _make_prices()
        result = compute_technical_indicators(close)
        vol = result["volatility"]
        assert "bollinger_upper" in vol
        assert "bollinger_lower" in vol
        assert "atr_14" in vol

    def test_volume_indicators_with_volume(self):
        close, high, low, volume = _make_ohlcv()
        result = compute_technical_indicators(close, volume, high, low)
        assert "obv" in result["volume"]
        assert "volume_ratio" in result["volume"]

    def test_volume_empty_without_volume(self):
        close = _make_prices()
        result = compute_technical_indicators(close)
        assert result["volume"] == {}

    def test_patterns_detected(self):
        close = _make_prices()
        patterns = compute_technical_indicators(close)["patterns"]
        assert "high_52w" in patterns
        assert "low_52w" in patterns
        assert "golden_death_cross" in patterns

    def test_insufficient_data(self):
        close = pd.Series([100, 101, 102], index=pd.bdate_range("2024-01-01", periods=3))
        result = compute_technical_indicators(close)
        assert "error" in result

    def test_rsi_range(self):
        close = _make_prices()
        rsi = compute_technical_indicators(close)["momentum"]["rsi_14"]
        assert rsi is None or 0 <= rsi <= 100

    def test_bollinger_position_range(self):
        close = _make_prices()
        bp = compute_technical_indicators(close)["volatility"]["bollinger_position"]
        # Bollinger position can be outside [0,1] when price is outside bands
        assert bp is not None

    def test_sma_values_reasonable(self):
        close = _make_prices(start_price=150)
        trend = compute_technical_indicators(close)["trend"]
        for key in ["sma_20", "sma_50", "sma_200"]:
            val = trend[key]
            if val is not None:
                assert 50 < val < 500, f"{key}={val} out of reasonable range"

    def test_with_full_ohlcv(self):
        close, high, low, volume = _make_ohlcv()
        result = compute_technical_indicators(close, volume, high, low)
        assert result["trend"]["adx"] is not None
        assert result["momentum"]["stochastic_k"] is not None
        assert result["volume"]["obv"] is not None


class TestTASignal:
    def test_basic_signal_structure(self):
        close = _make_prices()
        indicators = compute_technical_indicators(close)
        signal = get_ta_signal(indicators)
        assert "score" in signal
        assert "sentiment" in signal
        assert "confidence" in signal
        assert "reasons" in signal
        assert -1 <= signal["score"] <= 1

    def test_bullish_signal_in_uptrend(self):
        """Strongly trending up data should produce bullish signal."""
        rng = np.random.default_rng(42)
        n = 300
        returns = rng.normal(0.002, 0.01, n)  # strong uptrend
        prices = 100 * np.exp(np.cumsum(returns))
        close = pd.Series(prices, index=pd.bdate_range("2024-01-01", periods=n))
        indicators = compute_technical_indicators(close)
        signal = get_ta_signal(indicators)
        assert signal["score"] > 0, "Uptrend should produce positive signal"

    def test_bearish_signal_in_downtrend(self):
        """Strongly trending down data should produce bearish signal."""
        rng = np.random.default_rng(42)
        n = 300
        returns = rng.normal(-0.002, 0.01, n)  # strong downtrend
        prices = 100 * np.exp(np.cumsum(returns))
        close = pd.Series(prices, index=pd.bdate_range("2024-01-01", periods=n))
        indicators = compute_technical_indicators(close)
        signal = get_ta_signal(indicators)
        assert signal["score"] < 0, "Downtrend should produce negative signal"

    def test_error_indicators(self):
        signal = get_ta_signal({"error": "test error"})
        assert signal["score"] == 0
        assert signal["sentiment"] == "neutral"

    def test_confidence_increases_with_ohlcv(self):
        """More data (OHLCV) should give higher confidence than close-only."""
        close, high, low, volume = _make_ohlcv()
        ind_full = compute_technical_indicators(close, volume, high, low)
        ind_close = compute_technical_indicators(close)
        sig_full = get_ta_signal(ind_full)
        sig_close = get_ta_signal(ind_close)
        assert sig_full["confidence"] >= sig_close["confidence"]


class TestTASummary:
    def test_summary_has_both_keys(self):
        close = _make_prices()
        result = get_ta_summary(close)
        assert "indicators" in result
        assert "signal" in result

    def test_summary_with_ohlcv(self):
        close, high, low, volume = _make_ohlcv()
        result = get_ta_summary(close, volume, high, low)
        assert result["signal"]["n_signals"] > 0
