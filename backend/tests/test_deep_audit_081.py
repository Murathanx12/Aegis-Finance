"""
Deep Audit Cycle 081 — Regression tests for bugs found during line-by-line audit.

Bug 1: monte_carlo.run_monte_carlo annual_return_pct uses hardcoded forecast_years
        instead of actual simulation days when forecast_days_override is provided.
Bug 2: drawdown_analyzer.compute_rolling_risk_metrics rolling max drawdown has
        off-by-one error — starts at position 1 instead of 0, missing first price.
Bug 3: copula_tail._fit_student_t contains dead code with incorrect stats.gamma
        usage that would produce wrong log-likelihood if gammaln import failed.
Bug 4: retirement_mc.compute_safe_withdrawal_rate doesn't guard against savings=0.
"""

import numpy as np
import pandas as pd


# ═══════════════════════════════════════════════════════════════════════════
# BUG 1: Monte Carlo annual_return_pct annualization with forecast_days_override
# ═══════════════════════════════════════���═══════════════════════════════════


class TestMCannualReturnAnnualization:
    """annual_return_pct must use actual simulation days, not config forecast_years."""

    def test_annual_return_uses_actual_days(self):
        """When forecast_days_override=252 (1 year), annual return should equal total return."""
        from backend.services.monte_carlo import run_monte_carlo

        result = run_monte_carlo(
            current_price=100.0,
            current_regime="Neutral",
            risk_score=0.0,
            crash_freq=0.07,
            current_vix=20.0,
            yield_curve=0.5,
            val_penalty=0.0,
            seed=42,
            n_sims_override=500,
            forecast_days_override=252,  # 1 year
        )

        total_return = result["total_return_pct"]
        annual_return = result["annual_return_pct"]

        # For a 1-year simulation, annual return should be very close to total return
        # (not total_return^(1/5) which would happen if it used forecast_years=5)
        assert abs(annual_return - total_return) < 1.0, (
            f"1-year sim: annual_return={annual_return:.2f}% should ≈ "
            f"total_return={total_return:.2f}%, but they differ by "
            f"{abs(annual_return - total_return):.2f}pp — "
            f"likely using wrong forecast_years for annualization"
        )

    def test_annual_return_2y_override(self):
        """For 2-year sim, annual return should be roughly sqrt(1+total)-1."""
        from backend.services.monte_carlo import run_monte_carlo

        result = run_monte_carlo(
            current_price=100.0,
            current_regime="Neutral",
            risk_score=0.0,
            crash_freq=0.07,
            current_vix=20.0,
            yield_curve=0.5,
            val_penalty=0.0,
            seed=42,
            n_sims_override=500,
            forecast_days_override=504,  # 2 years
        )

        total_return_dec = result["total_return_pct"] / 100
        annual_return_dec = result["annual_return_pct"] / 100
        expected_annual = (1 + total_return_dec) ** (1 / 2) - 1

        assert abs(annual_return_dec - expected_annual) < 0.005, (
            f"2-year sim: annual_return={annual_return_dec:.4f} should ≈ "
            f"expected={expected_annual:.4f}"
        )

    def test_default_5y_still_works(self):
        """Default 5-year simulation should not be affected by the fix."""
        from backend.services.monte_carlo import run_monte_carlo

        result = run_monte_carlo(
            current_price=100.0,
            current_regime="Neutral",
            risk_score=0.0,
            crash_freq=0.07,
            current_vix=20.0,
            yield_curve=0.5,
            val_penalty=0.0,
            seed=42,
            n_sims_override=500,
        )

        total_return_dec = result["total_return_pct"] / 100
        annual_return_dec = result["annual_return_pct"] / 100
        expected_annual = (1 + total_return_dec) ** (1 / 5) - 1

        assert abs(annual_return_dec - expected_annual) < 0.005, (
            f"5-year sim: annual_return={annual_return_dec:.4f} should ≈ "
            f"expected={expected_annual:.4f}"
        )


# ═══════════════════════════���═══════════════════════════════════════════════
# BUG 2: Rolling max drawdown off-by-one
# ══════════════════════��════════════════════════════════════════════════════


class TestRollingMDDOffByOne:
    """Rolling max drawdown should include position 0 in the first window."""

    def test_rolling_mdd_first_window_includes_index_0(self):
        """The first rolling MDD window must include the price at index 0.

        If the loop starts at range(window, ...) instead of range(window-1, ...),
        the slice prices.iloc[1:window+1] skips index 0 entirely.
        We construct a series where the ONLY drawdown occurs from index 0→1,
        so missing index 0 means the rolling MDD never captures it.
        """
        from backend.services.drawdown_analyzer import compute_rolling_risk_metrics

        # Build a price series: peak at index 0, drop at index 1, flat after
        n = 30
        prices = np.ones(n) * 100.0
        prices[0] = 120.0  # Peak only at index 0
        prices[1] = 96.0   # 20% drop from peak (120 → 96)
        # From index 2 onwards, stay at 100 (recovered above day-1 trough)
        idx = pd.date_range("2020-01-01", periods=n, freq="B")
        price_series = pd.Series(prices, index=idx)

        result = compute_rolling_risk_metrics(price_series, window=10)

        # With window=10, the first valid MDD should cover indices [0..9].
        # The drawdown from 120→96 at index 0→1 is -20%.
        # If off-by-one skips index 0, the first window covers [1..10] and
        # sees no drawdown (96, 100, 100, ...) — the peak in that window is 100,
        # and 96 is already below it, so MDD would only be -4%.
        mdd_data = result.get("max_drawdown", {})
        worst_mdd = mdd_data.get("worst")
        assert worst_mdd is not None, "Rolling MDD should produce data"
        assert worst_mdd <= -15.0, (
            f"Rolling MDD worst={worst_mdd:.1f}% — should capture the 20% drop "
            f"from index 0 peak. If > -15%, the first window missed index 0."
        )


# ════════════════════════════════════════════════════════════════���══════════
# BUG 3: Copula Student-t dead code
# ═══��══════════════════════════════��════════════════════════════════════════


class TestCopulaStudentTLoglik:
    """Student-t copula fit should not rely on dead code with wrong gamma function."""

    def test_student_t_loglik_is_finite(self):
        """Student-t copula should produce finite, sensible log-likelihood."""
        from backend.services.copula_tail import _fit_student_t

        rng = np.random.default_rng(42)
        n = 500
        # Generate correlated uniform data (pseudo-observations)
        from scipy import stats
        rho = 0.5
        z1 = rng.standard_normal(n)
        z2 = rho * z1 + np.sqrt(1 - rho**2) * rng.standard_normal(n)
        u = stats.norm.cdf(z1)
        v = stats.norm.cdf(z2)
        # Clip to avoid boundary issues
        u = np.clip(u, 0.001, 0.999)
        v = np.clip(v, 0.001, 0.999)

        result = _fit_student_t(u, v)
        assert np.isfinite(result["loglik"]), f"loglik should be finite, got {result['loglik']}"
        assert np.isfinite(result["aic"]), f"AIC should be finite, got {result['aic']}"
        assert 0 <= result["tail_lower"] <= 1, f"tail_lower out of range: {result['tail_lower']}"
        assert result["rho"] > 0, f"Correlated data should give positive rho, got {result['rho']}"

    def test_student_t_no_dead_code_stats_gamma(self):
        """Ensure the code doesn't use stats.gamma (distribution) as gamma function."""
        import inspect
        from backend.services import copula_tail
        source = inspect.getsource(copula_tail._fit_student_t)
        # After fix, there should be no stats.gamma usage in _fit_student_t
        assert "stats.gamma(" not in source, (
            "_fit_student_t still contains stats.gamma() — dead code with wrong gamma function"
        )


# ════���════════════════════════════════════════════════���═════════════════════
# BUG 4: Safe withdrawal rate with savings=0
# ════════════════════════════════════════════════════���══════════════════════


class TestSafeWithdrawalEdgeCases:
    """compute_safe_withdrawal_rate should handle edge cases gracefully."""

    def test_zero_savings(self):
        """savings=0 should return 0 withdrawal rate without error."""
        from backend.services.retirement_mc import compute_safe_withdrawal_rate

        result = compute_safe_withdrawal_rate(
            savings=0,
            retirement_years=30,
            risk_level="moderate",
            n_sims=100,
        )
        assert result["safe_monthly_withdrawal"] == 0
        assert result["safe_withdrawal_rate_pct"] == 0

    def test_very_small_savings(self):
        """Very small savings should produce proportionally small withdrawal."""
        from backend.services.retirement_mc import compute_safe_withdrawal_rate

        result = compute_safe_withdrawal_rate(
            savings=100,
            retirement_years=30,
            risk_level="moderate",
            n_sims=100,
        )
        assert result["safe_monthly_withdrawal"] >= 0
        assert result["safe_withdrawal_rate_pct"] >= 0
        assert result["safe_withdrawal_rate_pct"] <= 20  # sanity bound
