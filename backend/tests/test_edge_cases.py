"""
Edge Case Tests
=================

Tests for boundary conditions and unusual inputs:
  - Invalid tickers return None gracefully (no crash)
  - Single-letter tickers work (F, T)
  - Crash probability monotonicity: 3m <= 6m <= 12m
  - Monte Carlo with extreme volatility parameters

Run with:
    python -m pytest backend/tests/test_edge_cases.py -v
"""

import logging
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.stock_analyzer import analyze_stock
from backend.services.monte_carlo import simulate_paths

logger = logging.getLogger(__name__)


class TestInvalidTickers:
    """Test that invalid tickers fail gracefully."""

    @pytest.mark.parametrize("ticker", ["ZZZZZZ", "INVALID123", "!@#$%", ""])
    def test_invalid_ticker_returns_none(self, ticker):
        """analyze_stock should return None for invalid tickers, not raise."""
        result = analyze_stock(ticker)
        assert result is None, (
            f"Expected None for invalid ticker '{ticker}', got {type(result)}"
        )


@pytest.mark.slow
class TestSingleLetterTickers:
    """Test that single-letter and short tickers work (F=Ford, T=AT&T)."""

    @pytest.mark.parametrize("ticker", ["F", "T"])
    def test_single_letter_ticker_returns_result(self, ticker):
        """Single-letter tickers should return valid results."""
        result = analyze_stock(ticker)
        # These are real tickers; they should work if yfinance is available
        if result is None:
            pytest.skip(f"{ticker}: returned None (may be a data availability issue)")
        assert result["ticker"] == ticker
        assert result["current_price"] > 0
        assert np.isfinite(result["expected_return"])


@pytest.mark.slow
class TestCrashProbabilityMonotonicity:
    """Test that longer horizons have equal or higher crash probability.

    This tests the Monte Carlo simulation indirectly: over a longer window
    there are more opportunities for a drawdown to occur, so the probability
    of experiencing a >20% crash should be monotonically non-decreasing.
    """

    def test_crash_prob_monotonic_over_horizons(self):
        """P(crash by 1Y) <= P(crash by 3Y) <= P(crash by 5Y)."""
        S0 = 100.0
        mu = 0.06
        sigma = 0.16
        n_sims = 3000
        base_scenario = {"drift_adj": 0.0, "vol_mult": 1.0, "crash_mult": 1.0}
        crash_threshold = -0.20

        paths_5y = simulate_paths(
            start_price=S0,
            historical_mu=mu,
            historical_sigma=sigma,
            days=1260,
            n_sims=n_sims,
            crash_freq=0.07,
            risk_score=0.0,
            scenario=base_scenario,
            seed=42,
        )

        sim_peak = np.maximum.accumulate(paths_5y, axis=0)
        sim_dd = (paths_5y - sim_peak) / sim_peak

        # Crash probability at different horizons
        crash_1y = float((sim_dd[:253].min(axis=0) <= crash_threshold).mean())
        crash_3y = float((sim_dd[:757].min(axis=0) <= crash_threshold).mean())
        crash_5y = float((sim_dd.min(axis=0) <= crash_threshold).mean())

        logger.info(
            "Crash probs: 1Y=%.1f%%, 3Y=%.1f%%, 5Y=%.1f%%",
            crash_1y * 100, crash_3y * 100, crash_5y * 100,
        )

        assert crash_1y <= crash_3y + 0.01, (
            f"1Y crash ({crash_1y:.3f}) > 3Y crash ({crash_3y:.3f})"
        )
        assert crash_3y <= crash_5y + 0.01, (
            f"3Y crash ({crash_3y:.3f}) > 5Y crash ({crash_5y:.3f})"
        )


class TestMonteCarloExtremeParams:
    """Test Monte Carlo with extreme but valid parameter combinations."""

    def test_very_high_volatility(self):
        """MC should handle high volatility (80%) without crashing."""
        paths = simulate_paths(
            start_price=100.0,
            historical_mu=0.06,
            historical_sigma=0.80,
            days=252,
            n_sims=100,
            crash_freq=0.07,
            risk_score=0.0,
            scenario={"drift_adj": 0.0, "vol_mult": 1.0, "crash_mult": 1.0},
            seed=42,
        )
        assert paths.shape == (253, 100)
        assert (paths > 0).all(), "Prices should remain positive even at high vol"
        assert np.all(np.isfinite(paths)), "All prices should be finite"

    def test_very_low_volatility(self):
        """MC should handle very low volatility (5%) without crashing."""
        paths = simulate_paths(
            start_price=100.0,
            historical_mu=0.06,
            historical_sigma=0.05,
            days=252,
            n_sims=100,
            crash_freq=0.07,
            risk_score=0.0,
            scenario={"drift_adj": 0.0, "vol_mult": 1.0, "crash_mult": 1.0},
            seed=42,
        )
        assert paths.shape == (253, 100)
        assert (paths > 0).all()
        assert np.all(np.isfinite(paths))

        # With very low vol, paths should stay close to the start price
        final = paths[-1]
        # Over 1 year at 5% vol, most should be within 50% of start
        assert np.percentile(final, 5) > 50.0, "Extreme loss at low vol"
        assert np.percentile(final, 95) < 200.0, "Extreme gain at low vol"

    def test_zero_crash_frequency(self):
        """MC should work with crash_freq near zero."""
        paths = simulate_paths(
            start_price=100.0,
            historical_mu=0.06,
            historical_sigma=0.16,
            days=252,
            n_sims=100,
            crash_freq=0.001,
            risk_score=0.0,
            scenario={"drift_adj": 0.0, "vol_mult": 1.0, "crash_mult": 1.0},
            seed=42,
        )
        assert paths.shape == (253, 100)
        assert np.all(np.isfinite(paths))

    def test_high_crash_frequency(self):
        """MC should work with elevated crash frequency."""
        paths = simulate_paths(
            start_price=100.0,
            historical_mu=0.06,
            historical_sigma=0.16,
            days=252,
            n_sims=100,
            crash_freq=0.20,
            risk_score=0.0,
            scenario={"drift_adj": 0.0, "vol_mult": 1.0, "crash_mult": 1.0},
            seed=42,
        )
        assert paths.shape == (253, 100)
        assert (paths > 0).all()
        assert np.all(np.isfinite(paths))

    def test_negative_drift(self):
        """MC should handle negative drift (bear market)."""
        paths = simulate_paths(
            start_price=100.0,
            historical_mu=-0.10,
            historical_sigma=0.25,
            days=252,
            n_sims=200,
            crash_freq=0.07,
            risk_score=2.0,
            scenario={"drift_adj": 0.0, "vol_mult": 1.0, "crash_mult": 1.0},
            seed=42,
        )
        assert paths.shape == (253, 200)
        assert (paths > 0).all()
        # With -10% drift, median terminal should be below start
        median_final = np.median(paths[-1])
        assert median_final < 100.0, (
            f"Negative drift should produce declining median, got {median_final:.1f}"
        )

    def test_very_long_horizon(self):
        """MC should handle a 10-year simulation."""
        days = 2520  # 10 years
        paths = simulate_paths(
            start_price=100.0,
            historical_mu=0.06,
            historical_sigma=0.16,
            days=days,
            n_sims=50,
            crash_freq=0.07,
            risk_score=0.0,
            scenario={"drift_adj": 0.0, "vol_mult": 1.0, "crash_mult": 1.0},
            seed=42,
        )
        assert paths.shape == (days + 1, 50)
        assert (paths > 0).all()
        assert np.all(np.isfinite(paths))

    def test_small_simulation(self):
        """MC should work with n_sims=2 (minimum for antithetic variates)."""
        paths = simulate_paths(
            start_price=100.0,
            historical_mu=0.06,
            historical_sigma=0.16,
            days=252,
            n_sims=2,
            crash_freq=0.07,
            risk_score=0.0,
            scenario={"drift_adj": 0.0, "vol_mult": 1.0, "crash_mult": 1.0},
            seed=42,
        )
        assert paths.shape == (253, 2)
        assert (paths > 0).all()

    def test_scenario_with_vol_multiplier(self):
        """MC should handle scenario vol_mult > 1."""
        paths = simulate_paths(
            start_price=100.0,
            historical_mu=0.06,
            historical_sigma=0.16,
            days=252,
            n_sims=100,
            crash_freq=0.07,
            risk_score=0.0,
            scenario={"drift_adj": -0.05, "vol_mult": 2.0, "crash_mult": 2.0},
            seed=42,
        )
        assert paths.shape == (253, 100)
        assert (paths > 0).all()
        assert np.all(np.isfinite(paths))
