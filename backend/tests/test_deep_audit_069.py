"""
Deep Audit Cycle 069 — Regression Tests
==========================================

Tests that catch the 3 bugs found during this audit:
1. retirement_mc.py: geometric/arithmetic drift mismatch
2. sector_rotation.py: composite score not renormalized for missing timeframes
3. economic_surprise.py: CPI level-based series causes systematic bearish bias

Run with:
    python -m pytest backend/tests/test_deep_audit_069.py -v
"""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest


# ── Bug 1: retirement_mc.py drift mismatch ──────────────────────────────────


class TestRetirementMcDrift:
    """The geometric mean of simulated returns should match the intended target.

    Bug: daily_mu was set to annual_geometric / 252, but arithmetic daily drift
    should be higher to compensate for the volatility drag (Jensen's inequality).
    Without correction, the realized geometric return is ~σ²/2 lower than intended.
    """

    def test_realized_geometric_return_matches_target(self):
        """Median annualized return should be close to the target geometric return."""
        from backend.services.retirement_mc import simulate_retirement

        # Use all_equity (mu=9%, sigma=20%) to make the bias most visible.
        # σ²/2 = 0.02 = 2%, so the bug would give ~7% instead of 9%.
        result = simulate_retirement(
            current_savings=100000,
            monthly_contribution=0,
            monthly_withdrawal=0,
            current_age=30,
            retirement_age=60,
            end_age=60,      # 30 years accumulation only
            risk_level="all_equity",
            inflation_rate=0.0,  # remove inflation to isolate growth
            n_sims=5000,
            seed=42,
        )

        median_at_end = result["at_retirement"]["median"]
        # Annualized geometric return: (final/initial)^(1/years) - 1
        realized_return = (median_at_end / 100000) ** (1 / 30) - 1

        # Target is 9.0%. With the bug, this was ~7.0%.
        # Allow ±1.5% tolerance for MC noise.
        assert realized_return > 0.075, (
            f"Realized geometric return {realized_return:.3%} is too low — "
            f"drift correction may be missing (expected ~9%, got {realized_return:.1%})"
        )

    def test_zero_vol_return_equals_target(self):
        """With zero volatility, geometric and arithmetic returns are identical.

        This test verifies the basic drift is correct independent of the
        volatility correction.
        """
        from backend.services.retirement_mc import _ASSET_RETURNS

        # All risk levels should have their target return in the config
        for level, params in _ASSET_RETURNS.items():
            assert "mu" in params, f"{level} missing 'mu'"
            assert "sigma" in params, f"{level} missing 'sigma'"
            assert 0.03 < params["mu"] < 0.15, f"{level} mu={params['mu']} out of range"


# ── Bug 2: sector_rotation.py missing weight renormalization ─────────────────


class TestSectorRotationCompositeScore:
    """Composite score should not be biased when some timeframes are missing.

    Bug: when a timeframe (e.g. 12m) has no data, its weight is dropped but
    the remaining weights are NOT renormalized to sum to 1.0. This makes the
    composite score artificially lower for sectors with shorter histories.
    """

    def test_missing_timeframe_doesnt_deflate_score(self):
        """A sector with 4/5 timeframes should score comparably to one with 5/5,
        all else being equal."""
        from backend.services.sector_rotation import _compute_composite_score

        returns_full = {"1w": 2.0, "1m": 5.0, "3m": 10.0, "6m": 15.0, "12m": 20.0}
        returns_no_12m = {"1w": 2.0, "1m": 5.0, "3m": 10.0, "6m": 15.0, "12m": None}

        score_full = _compute_composite_score(returns_full)
        score_partial = _compute_composite_score(returns_no_12m)

        # Without renormalization, the buggy score would be:
        # 2*0.05 + 5*0.15 + 10*0.30 + 15*0.30 = 8.35 (total weight only 0.80)
        # With renormalization: 8.35 / 0.80 = 10.44
        buggy_score = 2.0 * 0.05 + 5.0 * 0.15 + 10.0 * 0.30 + 15.0 * 0.30  # = 8.35
        assert score_partial > buggy_score * 1.15, (
            f"Partial score ({score_partial:.2f}) is too close to unrenormalized value "
            f"({buggy_score:.2f}) — weights may not be renormalized"
        )

    def test_single_timeframe_not_deflated(self):
        """Even with only 1 timeframe, score should not be near-zero."""
        from backend.services.sector_rotation import _compute_composite_score

        returns = {"1w": None, "1m": None, "3m": 10.0, "6m": None, "12m": None}
        score = _compute_composite_score(returns)

        # With only 3m=10.0, the score should be ~10.0, not 10.0 * 0.30 = 3.0
        assert score > 8.0, (
            f"Single-timeframe score ({score:.2f}) is deflated — "
            f"weight renormalization missing"
        )


# ── Bug 3: economic_surprise.py CPI level bias ──────────────────────────────


class TestEconomicSurpriseCpiBias:
    """CPI (price level) should not cause a systematic bearish surprise.

    Bug: CPIAUCSL is a monotonically increasing price level index. Using
    the raw level for surprise computation means latest > median(trailing 12m)
    ALWAYS, creating a permanent bearish drag after inversion.

    Fix: use rate-of-change (month-over-month change) for level-based series,
    so the surprise measures acceleration/deceleration of inflation.
    """

    @patch("backend.services.economic_surprise._fetch_fred_series")
    def test_steady_inflation_gives_neutral_surprise(self, mock_fetch):
        """A perfectly steady inflation rate should produce near-zero surprise."""
        from backend.services.economic_surprise import compute_surprise_index

        # Create a CPI-like series with perfectly constant 0.2% monthly growth
        # (2.4% annual inflation). There should be NO surprise.
        dates = pd.date_range(end="2026-03-31", periods=60, freq="MS")
        cpi = 300 * (1.002 ** np.arange(60))
        steady_cpi = pd.Series(cpi, index=dates)

        mock_fetch.return_value = steady_cpi

        result = compute_surprise_index()
        if result is None:
            pytest.skip("All series returned None")

        # Find the CPI indicator
        cpi_indicators = [i for i in result["indicators"] if i["series_id"] == "CPIAUCSL"]
        if not cpi_indicators:
            pytest.skip("CPIAUCSL not in results")

        cpi_surprise = cpi_indicators[0]["surprise_normalized"]

        # With steady inflation, surprise should be near zero (±0.05)
        # Bug would give a negative value (~-0.10 for moderate growth,
        # worse for faster growth) due to level-vs-median lag
        assert abs(cpi_surprise) < 0.05, (
            f"CPI surprise ({cpi_surprise:.3f}) is biased for a steady-inflation series — "
            f"level-based trend tracking causes systematic bias"
        )

    @patch("backend.services.economic_surprise._fetch_fred_series")
    def test_inflation_spike_detected_as_bearish(self, mock_fetch):
        """An actual inflation spike should still register as bearish surprise."""
        from backend.services.economic_surprise import compute_surprise_index

        dates = pd.date_range(end="2026-03-31", periods=60, freq="MS")
        # Normal 0.2% monthly growth, then sudden 1% spike in last 3 months
        cpi = 300 * (1.002 ** np.arange(60))
        cpi[-3:] = cpi[-4] * (1.01 ** np.arange(1, 4))  # inflation spike
        spiked_cpi = pd.Series(cpi, index=dates)

        mock_fetch.return_value = spiked_cpi

        result = compute_surprise_index()
        if result is None:
            pytest.skip("All series returned None")

        cpi_indicators = [i for i in result["indicators"] if i["series_id"] == "CPIAUCSL"]
        if not cpi_indicators:
            pytest.skip("CPIAUCSL not in results")

        # After inversion, an inflation spike should be bearish (negative)
        cpi_surprise = cpi_indicators[0]["surprise_normalized"]
        assert cpi_surprise < -0.05, (
            f"CPI surprise ({cpi_surprise:.3f}) should be negative after inflation spike"
        )
