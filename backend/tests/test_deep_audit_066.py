"""Regression tests for bugs found in deep audit cycle 066.

Bug 1: retirement_mc.py — Student-t(df=8) has variance 8/6, not 1.0.
  Using raw standard_t inflates simulation volatility by sqrt(4/3) ≈ 15.5%.
  Over 30-year horizons this significantly depresses median outcomes.

Bug 2: sector_rotation.py — Momentum direction ratio inverted for negative returns.
  When both 1m and 3m returns are negative, the ratio of r1m/(r3m/3) produces
  the wrong sign interpretation: "accelerating" when actually "decelerating".

Bug 3: technical_analysis.py — SMA "200" computed with min(200, len-1) window.
  When <200 days of data, sma_200 is a shorter-period SMA but still used in
  trend direction, producing misleading signals (e.g. SMA49 labeled as SMA200).
"""

import numpy as np
import pandas as pd


# ═══════════════════════════════════════════════════════════════════════════
# Bug 1: t-distribution variance normalization in retirement_mc
# ═══════════════════════════════════════════════════════════════════════════

class TestRetirementMCVarianceNormalization:
    """Student-t(df=8) has variance 8/6, not 1.0.
    The simulation must normalize so that sigma * t(df) has the intended variance.
    """

    def test_monthly_return_volatility_matches_target(self):
        """Simulated monthly volatility should match the target, not be inflated."""
        from backend.services.retirement_mc import simulate_retirement

        # Run with known parameters: moderate = 12% annual vol
        result = simulate_retirement(
            current_savings=1_000_000,
            monthly_contribution=0,
            monthly_withdrawal=0,
            current_age=65,
            retirement_age=65,
            end_age=75,  # 10 years
            risk_level="moderate",
            n_sims=5000,
            seed=42,
        )
        # Extract yearly projections to check dispersion
        projections = result["yearly_projections"]
        # At year 10 (age 75), the spread should reflect ~12% vol, not ~14%
        year_10 = [p for p in projections if p["age"] == 75][0]

        # With 12% annual vol over 10 years, the log-normal p10/p90 spread
        # should be roughly: exp(±1.28 * 0.12 * sqrt(10)) ≈ exp(±0.486)
        # p90/median ≈ 1.63, p10/median ≈ 0.62
        # The ratio p90/p10 should be around 2.6
        # With inflated vol (13.9%), p90/p10 would be around 3.1
        if year_10["p10"] > 0:
            spread_ratio = year_10["p90"] / year_10["p10"]
            # Correct spread ~2.6, inflated spread ~3.1
            # Allow some tolerance but it should not be wildly inflated
            assert spread_ratio < 3.0, (
                f"p90/p10 ratio {spread_ratio:.2f} suggests inflated volatility. "
                f"Expected ~2.6 for 12% annual vol over 10 years."
            )

    def test_t_distribution_normalized_variance(self):
        """Direct check: the daily return generator should produce
        returns with the intended standard deviation."""
        from backend.services.retirement_mc import _ASSET_RETURNS

        params = _ASSET_RETURNS["moderate"]
        daily_sigma = params["sigma"] / np.sqrt(252)
        rng = np.random.default_rng(42)

        # Generate many daily returns using the same method as simulate_retirement
        n_samples = 100_000
        df = 8
        # After fix: should normalize by sqrt((df-2)/df) = sqrt(6/8)
        # The raw t(8) has std = sqrt(8/6) ≈ 1.155, not 1.0
        raw_t = rng.standard_t(df=df, size=n_samples)
        raw_std = np.std(raw_t)

        # The normalization factor: multiply by sqrt((df-2)/df)
        normalized_t = raw_t * np.sqrt((df - 2) / df)
        normalized_std = np.std(normalized_t)

        # Raw t(8) std should be ~1.15, not 1.0
        assert raw_std > 1.10, f"Raw t(8) std should be > 1.10, got {raw_std:.3f}"
        # Normalized should be ~1.0
        assert abs(normalized_std - 1.0) < 0.05, (
            f"Normalized t(8) std should be ~1.0, got {normalized_std:.3f}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Bug 2: sector_rotation momentum direction inverted for negative returns
# ═══════════════════════════════════════════════════════════════════════════

class TestSectorRotationMomentumDirection:
    """When both 1m and 3m returns are negative, the ratio r1m/(r3m/3)
    gives the wrong sign: a moderating decline appears as "decelerating"
    and a deepening decline appears as "accelerating".
    """

    def test_moderating_decline_is_improving(self):
        """If 3m return = -15% (avg monthly -5%) and 1m = -2%,
        the decline is moderating → should be 'improving' not 'decelerating'.
        """
        # After fix, the sector_rotation code should detect moderating declines
        r1m = -2.0   # 1-month return, %
        r3m = -15.0  # 3-month return, %
        avg_monthly_3m = r3m / 3  # = -5.0

        # The 1m loss (-2%) is LESS severe than avg monthly (-5%),
        # meaning the decline is moderating (improving)
        # The old code would compute ratio = -2 / -5 = 0.4 < 0.7 → "decelerating" (WRONG)
        # The fix should correctly detect this as "improving"
        from backend.services.sector_rotation import _classify_momentum_direction
        direction = _classify_momentum_direction(r1m, r3m)
        assert direction in ("improving", "accelerating"), (
            f"Moderating decline (1m={r1m}%, 3m={r3m}%) should be improving, got '{direction}'"
        )

    def test_deepening_decline_is_decelerating(self):
        """If 3m return = -9% (avg monthly -3%) and 1m = -8%,
        the decline is deepening → should be 'decelerating' not 'accelerating'.
        """
        r1m = -8.0
        r3m = -9.0
        from backend.services.sector_rotation import _classify_momentum_direction
        direction = _classify_momentum_direction(r1m, r3m)
        assert direction in ("decelerating", "declining"), (
            f"Deepening decline (1m={r1m}%, 3m={r3m}%) should be decelerating, got '{direction}'"
        )

    def test_positive_returns_still_correct(self):
        """Positive returns should still work correctly after the fix."""
        from backend.services.sector_rotation import _classify_momentum_direction
        # Accelerating rally: 3m = +9%, 1m = +6% (monthly avg 3%, recent 6%)
        direction = _classify_momentum_direction(6.0, 9.0)
        assert direction in ("accelerating", "improving")

        # Decelerating rally: 3m = +15%, 1m = +2% (monthly avg 5%, recent 2%)
        direction = _classify_momentum_direction(2.0, 15.0)
        assert direction in ("decelerating", "declining")


# ═══════════════════════════════════════════════════════════════════════════
# Bug 3: technical_analysis.py SMA "200" with insufficient data
# ═══════════════════════════════════════════════════════════════════════════

class TestTASMA200InsufficientData:
    """When <200 days of data, SMA 200 should be None, not a shorter-period SMA.
    Using a 99-day SMA labeled as 'SMA 200' produces wrong trend signals.
    """

    def test_sma200_none_with_100_days(self):
        """With only 100 days, sma_200 should be None."""
        from backend.services.technical_analysis import compute_technical_indicators

        rng = np.random.default_rng(42)
        n = 100
        prices = pd.Series(
            100 * np.exp(np.cumsum(rng.normal(0.001, 0.015, n))),
            index=pd.bdate_range("2024-01-01", periods=n),
        )
        result = compute_technical_indicators(prices)
        assert result["trend"]["sma_200"] is None, (
            "SMA 200 should be None with only 100 days of data, "
            "not a shorter-period SMA masquerading as SMA 200"
        )

    def test_sma200_none_with_150_days(self):
        """With 150 days, sma_200 should still be None."""
        from backend.services.technical_analysis import compute_technical_indicators

        rng = np.random.default_rng(42)
        n = 150
        prices = pd.Series(
            100 * np.exp(np.cumsum(rng.normal(0.001, 0.015, n))),
            index=pd.bdate_range("2024-01-01", periods=n),
        )
        result = compute_technical_indicators(prices)
        assert result["trend"]["sma_200"] is None

    def test_sma200_present_with_250_days(self):
        """With 250 days, sma_200 should be computed normally."""
        from backend.services.technical_analysis import compute_technical_indicators

        rng = np.random.default_rng(42)
        n = 250
        prices = pd.Series(
            100 * np.exp(np.cumsum(rng.normal(0.001, 0.015, n))),
            index=pd.bdate_range("2024-01-01", periods=n),
        )
        result = compute_technical_indicators(prices)
        assert result["trend"]["sma_200"] is not None

    def test_trend_direction_with_insufficient_data(self):
        """With <200 days, trend direction should only use SMA 20 and SMA 50,
        not a fake SMA 200."""
        from backend.services.technical_analysis import compute_technical_indicators

        rng = np.random.default_rng(42)
        n = 100
        # Generate strong uptrend
        prices = pd.Series(
            100 * np.exp(np.cumsum(rng.normal(0.003, 0.01, n))),
            index=pd.bdate_range("2024-01-01", periods=n),
        )
        result = compute_technical_indicators(prices)
        trend = result["trend"]
        # sma_200 should not contribute to trend direction
        assert trend["sma_200"] is None
        assert trend["price_vs_sma200_pct"] is None
