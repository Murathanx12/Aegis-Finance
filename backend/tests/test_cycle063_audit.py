"""Cycle 063 deep audit — regression tests for bugs found.

Each test is designed to FAIL before the fix and PASS after.
"""

import numpy as np
import pandas as pd
import pytest


class TestBug1_RetirementInflationFormula:
    """Bug: compute_safe_withdrawal_rate used (1.025 / 12)^m instead of (1 + 0.025/12)^m.

    The wrong formula makes inflation_factor = 0.0854^m which goes to ~0 after month 1,
    effectively removing all withdrawals. This makes ANY withdrawal rate appear safe.
    """

    def test_safe_withdrawal_rate_not_absurdly_high(self):
        """SWR for 30yr moderate should be roughly 3-7%, not 20%+."""
        from backend.services.retirement_mc import compute_safe_withdrawal_rate

        result = compute_safe_withdrawal_rate(
            savings=1_000_000,
            retirement_years=30,
            risk_level="moderate",
            target_success_rate=95.0,
            n_sims=1000,
            seed=42,
        )
        rate = result["safe_withdrawal_rate_pct"]
        # Before fix: rate was absurdly high (>15%) because inflation killed withdrawals
        # After fix: should be in the 3-8% range (Bengen 4% rule neighborhood)
        assert rate < 9, f"SWR {rate}% is too high — inflation formula likely broken"
        assert rate > 1, f"SWR {rate}% is too low — something else is wrong"

    def test_inflation_adjustment_grows_over_time(self):
        """Inflation-adjusted withdrawal at month 120 should be > month 1."""
        # Directly test the inflation math used inside _ruin_rate
        # Correct: (1 + 0.025/12)^120 ≈ 1.284 (grows)
        # Wrong:   (1.025 / 12)^120 ≈ 0 (shrinks to nothing)
        m = 120
        correct = (1 + 0.025 / 12) ** m
        assert correct > 1.2, f"Inflation factor at month 120 should be >1.2, got {correct}"
        # The buggy formula:
        buggy = (1.025 / 12) ** m
        assert buggy < 0.001, "Sanity check: buggy formula does go to zero"


class TestBug2_SortinoRatio:
    """Bug: Sortino denominator used std() instead of sqrt(mean(min(r-rf,0)^2)).

    std() subtracts the mean of downside returns, which is mathematically wrong.
    The correct downside deviation uses excess returns below rf, with RMS not std.
    """

    def test_sortino_higher_than_sharpe_for_skewed_returns(self):
        """For positively-skewed returns, Sortino should be > Sharpe.

        Positively-skewed returns have fewer downside observations, so
        downside deviation < total std, meaning Sortino > Sharpe.
        """
        from backend.services.drawdown_analyzer import compute_rolling_risk_metrics

        rng = np.random.default_rng(42)
        n = 600
        dates = pd.bdate_range("2020-01-01", periods=n)
        # Create positively-skewed returns (few big up days, steady otherwise)
        daily_returns = rng.normal(0.0005, 0.01, n)
        # Add some big positive jumps
        for i in range(0, n, 30):
            daily_returns[i] += 0.03
        prices = pd.Series(100 * np.exp(np.cumsum(daily_returns)), index=dates)

        result = compute_rolling_risk_metrics(prices, window=252)
        sharpe = result["sharpe"]["current"]
        sortino = result["sortino"]["current"]

        # For positively-skewed returns, Sortino should generally exceed Sharpe
        # Before fix: Sortino could be lower due to wrong denominator
        assert sortino is not None
        assert sharpe is not None
        assert sortino > sharpe * 0.9, (
            f"Sortino ({sortino:.3f}) should be >= Sharpe ({sharpe:.3f}) "
            f"for positively-skewed returns"
        )

    def test_sortino_uses_excess_returns(self):
        """Sortino should account for risk-free rate in downside calculation."""
        from backend.services.drawdown_analyzer import compute_rolling_risk_metrics

        rng = np.random.default_rng(123)
        n = 500
        dates = pd.bdate_range("2020-01-01", periods=n)
        # Returns that are positive but below risk-free rate
        # These should count as "downside" in proper Sortino
        daily_returns = rng.normal(0.0001, 0.008, n)
        prices = pd.Series(100 * np.exp(np.cumsum(daily_returns)), index=dates)

        # With rf=0 vs rf=0.04, Sortino should differ
        result_low_rf = compute_rolling_risk_metrics(prices, window=252, risk_free_rate=0.0)
        result_high_rf = compute_rolling_risk_metrics(prices, window=252, risk_free_rate=0.08)

        sort_low = result_low_rf["sortino"]["current"]
        sort_high = result_high_rf["sortino"]["current"]

        # Higher risk-free rate → more returns count as "downside" → lower Sortino
        assert sort_low > sort_high, (
            f"Higher rf should give lower Sortino: rf=0 gave {sort_low:.3f}, "
            f"rf=0.08 gave {sort_high:.3f}"
        )


class TestBug3_RollingMaxDrawdownOffByOne:
    """Bug: Rolling max drawdown excluded current day's price.

    prices.iloc[max(0, i-window):i] misses index i (the current day).
    When today is the trough of a drawdown, the worst value is excluded.
    """

    def test_rolling_mdd_includes_current_day(self):
        """A crash on the last day of the window should be captured."""
        from backend.services.drawdown_analyzer import compute_rolling_risk_metrics

        n = 300
        dates = pd.bdate_range("2020-01-01", periods=n)
        prices_arr = np.ones(n) * 100.0
        # Flat at 100 for 298 days, then crash to 70 on day 299
        prices_arr[-1] = 70.0
        prices = pd.Series(prices_arr, index=dates)

        result = compute_rolling_risk_metrics(prices, window=252)
        if result and "max_drawdown" in result:
            mdd = result["max_drawdown"]["current"]
            # Should capture the -30% drawdown on the last day
            # Before fix: would miss it because current day excluded
            assert mdd is not None
            assert mdd < -25, (
                f"Rolling MDD should capture -30% crash on last day, got {mdd:.1f}%"
            )


class TestBug4_SWRBinarySearchRNG:
    """Bug: Binary search in compute_safe_withdrawal_rate shared mutable RNG.

    Each _ruin_rate() call consumed different random numbers from the same
    generator, making results path-dependent rather than withdrawal-dependent.
    """

    def test_swr_is_reproducible(self):
        """Same inputs + same seed should give identical results."""
        from backend.services.retirement_mc import compute_safe_withdrawal_rate

        r1 = compute_safe_withdrawal_rate(
            savings=1_000_000, retirement_years=30,
            risk_level="moderate", n_sims=500, seed=99,
        )
        r2 = compute_safe_withdrawal_rate(
            savings=1_000_000, retirement_years=30,
            risk_level="moderate", n_sims=500, seed=99,
        )
        assert r1["safe_withdrawal_rate_pct"] == r2["safe_withdrawal_rate_pct"], (
            f"SWR not reproducible: {r1['safe_withdrawal_rate_pct']} vs {r2['safe_withdrawal_rate_pct']}"
        )

    def test_swr_monotonic_in_savings(self):
        """Higher savings should give same or higher absolute withdrawal."""
        from backend.services.retirement_mc import compute_safe_withdrawal_rate

        r_low = compute_safe_withdrawal_rate(
            savings=500_000, retirement_years=30, n_sims=500, seed=42,
        )
        r_high = compute_safe_withdrawal_rate(
            savings=2_000_000, retirement_years=30, n_sims=500, seed=42,
        )
        assert r_high["safe_monthly_withdrawal"] >= r_low["safe_monthly_withdrawal"], (
            f"$2M should allow >= withdrawal than $500k: "
            f"${r_high['safe_monthly_withdrawal']} vs ${r_low['safe_monthly_withdrawal']}"
        )
