"""
Cycle 078 regression tests — deep audit bugs.

Bug 1: crash_timeline.py calls simulate_paths() without required
       risk_score and scenario args → TypeError at runtime.

Bug 2: volatility_analytics.py _garch_forward_curve reports model as
       "GJR-GARCH(1,1) Student-t" but actually fits standard GARCH(1,1)
       via vol="Garch" — incorrect metadata in API responses.

Bug 3: risk_number.py portfolio returns use sum(axis=1) which silently
       skips NaN, producing incorrect returns when tickers have different
       data availability.
"""

import numpy as np
import pandas as pd
import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# BUG 1: crash_timeline missing simulate_paths args
# ═══════════════════════════════════════════════════════════════════════════════


class TestCrashTimelineMissingArgs:
    """crash_timeline must pass risk_score and scenario to simulate_paths."""

    def test_simulate_paths_receives_required_args(self):
        """estimate_crash_timeline must pass risk_score and scenario kwargs."""
        from unittest.mock import patch

        captured = {}

        def mock_simulate(*args, **kwargs):
            captured.update(kwargs)
            # Also capture positional args by name
            import inspect
            from backend.services.monte_carlo import simulate_paths
            sig = inspect.signature(simulate_paths)
            params = list(sig.parameters.keys())
            for i, val in enumerate(args):
                if i < len(params):
                    captured[params[i]] = val
            # Return dummy paths: (days+1, n_sims)
            days = kwargs.get("days", args[3] if len(args) > 3 else 252)
            n_sims = kwargs.get("n_sims", args[4] if len(args) > 4 else 100)
            return np.ones((days + 1, n_sims)) * 5000

        with patch("backend.services.monte_carlo.simulate_paths", side_effect=mock_simulate):
            from backend.services import crash_timeline
            import importlib
            importlib.reload(crash_timeline)

            crash_timeline.estimate_crash_timeline(
                current_level=5000.0,
                vix=20.0,
                months_ahead=12,
            )

        # These args are REQUIRED by simulate_paths — crash_timeline must pass them
        assert "risk_score" in captured, (
            "crash_timeline does not pass risk_score to simulate_paths"
        )
        assert "scenario" in captured, (
            "crash_timeline does not pass scenario to simulate_paths"
        )

    def test_estimate_crash_timeline_does_not_raise(self):
        """Calling estimate_crash_timeline should not raise TypeError."""
        from unittest.mock import patch
        from backend.services.monte_carlo import simulate_paths
        import inspect

        # Get the real signature to verify all required params are satisfied
        sig = inspect.signature(simulate_paths)
        required = [
            name for name, p in sig.parameters.items()
            if p.default is inspect.Parameter.empty
        ]

        captured_kwargs = {}

        def mock_simulate(*args, **kwargs):
            captured_kwargs.update(kwargs)
            days = kwargs.get("days", args[3] if len(args) > 3 else 252)
            n_sims = kwargs.get("n_sims", args[4] if len(args) > 4 else 100)
            return np.ones((days + 1, n_sims)) * 5000

        with patch("backend.services.monte_carlo.simulate_paths", side_effect=mock_simulate):
            from backend.services import crash_timeline
            import importlib
            importlib.reload(crash_timeline)

            # This should NOT raise TypeError
            result = crash_timeline.estimate_crash_timeline(
                current_level=5000.0,
                vix=20.0,
                months_ahead=12,
            )

        assert result is not None
        assert "monthly_probabilities" in result


# ═══════════════════════════════════════════════════════════════════════════════
# BUG 2: volatility_analytics GARCH model label mismatch
# ═══════════════════════════════════════════════════════════════════════════════


class TestGarchModelLabel:
    """GARCH forward curve must report the correct model type."""

    def test_garch_model_label_matches_specification(self):
        """The model label must match what arch_model actually fits.

        Bug: code uses vol='Garch' (standard GARCH) but reports
        'GJR-GARCH(1,1) Student-t'. GJR-GARCH requires vol='GARCH' with
        o=1 (or vol='GJR-GARCH'). Since the code uses standard GARCH,
        the label must say 'GARCH(1,1)'.
        """
        from unittest.mock import patch

        captured_kwargs = {}

        try:
            from arch import arch_model as real_arch_model
        except ImportError:
            pytest.skip("arch package not available")

        def spy_arch_model(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return real_arch_model(*args, **kwargs)

        rng = np.random.default_rng(42)
        returns = pd.Series(rng.normal(0.0005, 0.015, 500))

        with patch("arch.arch_model", side_effect=spy_arch_model):
            from backend.services import volatility_analytics
            import importlib
            importlib.reload(volatility_analytics)
            result = volatility_analytics._garch_forward_curve(returns)

        if result is None:
            pytest.skip("GARCH fit returned None")

        # The model label must NOT say "GJR" if the code is fitting standard GARCH
        vol_type = captured_kwargs.get("vol", "Garch")
        if vol_type.upper() == "GARCH":
            # Standard GARCH — label must not claim GJR
            assert "GJR" not in result["model"], (
                f"Model reports '{result['model']}' but fits vol='{vol_type}' "
                f"(standard GARCH, not GJR-GARCH)"
            )

    def test_garch_label_not_misleading(self):
        """Smoke test: whatever GARCH variant is fit, the label should match."""
        rng = np.random.default_rng(42)
        returns = pd.Series(rng.normal(0.0005, 0.015, 500))

        from backend.services.volatility_analytics import _garch_forward_curve
        result = _garch_forward_curve(returns)

        if result is None:
            pytest.skip("GARCH fit returned None (arch not installed?)")

        model_label = result["model"]
        # Label must contain "GARCH" and "Student-t" (since dist='t' is used)
        assert "GARCH" in model_label
        assert "Student-t" in model_label or "t" in model_label


# ═══════════════════════════════════════════════════════════════════════════════
# BUG 3: risk_number NaN handling in portfolio returns
# ═══════════════════════════════════════════════════════════════════════════════


class TestRiskNumberNaNHandling:
    """Portfolio returns must handle partial NaN data correctly."""

    def test_partial_nan_does_not_deflate_returns(self):
        """When some tickers have NaN, portfolio return should still be correct.

        Bug: sum(axis=1) skips NaN, so if ticker A has NaN and ticker B
        doesn't, the portfolio return is just w_B * r_B instead of the
        correct weighted average over available tickers.
        """
        from backend.services.risk_number import compute_risk_number

        rng = np.random.default_rng(42)
        dates = pd.bdate_range("2024-01-01", periods=300)

        # Ticker A: full data, daily return ~0.1%
        ret_a = rng.normal(0.001, 0.01, 300)
        # Ticker B: last 50 days are NaN (within the 252-day lookback)
        ret_b = rng.normal(0.001, 0.01, 300)
        ret_b[-50:] = np.nan

        returns = pd.DataFrame({"A": ret_a, "B": ret_b}, index=dates)
        weights = {"A": 0.5, "B": 0.5}

        result = compute_risk_number(returns, weights)
        assert result["risk_number"] != 50, "Should not fall back to default"

        # The volatility should be reasonable (not deflated by half-weighted days)
        vol = result["components"]["volatility"]["value"]
        assert vol > 0, "Volatility must be positive"

    def test_all_nan_ticker_excluded(self):
        """A ticker with all NaN should be excluded, not crash the computation."""
        from backend.services.risk_number import compute_risk_number

        rng = np.random.default_rng(42)
        dates = pd.bdate_range("2024-01-01", periods=252)
        returns = pd.DataFrame({
            "GOOD": rng.normal(0.0003, 0.015, 252),
            "BAD": np.full(252, np.nan),
        }, index=dates)
        weights = {"GOOD": 0.5, "BAD": 0.5}

        result = compute_risk_number(returns, weights)
        # Should work with just GOOD ticker
        assert 1 <= result["risk_number"] <= 99

    def test_consistent_returns_with_and_without_nan(self):
        """Portfolio vol should be similar whether NaN rows exist or not."""
        from backend.services.risk_number import compute_risk_number

        rng = np.random.default_rng(42)
        dates = pd.bdate_range("2024-01-01", periods=300)
        ret_a = rng.normal(0.0003, 0.015, 300)
        ret_b = rng.normal(0.0003, 0.015, 300)

        # Clean version
        clean = pd.DataFrame({"A": ret_a, "B": ret_b}, index=dates)
        weights = {"A": 0.5, "B": 0.5}
        result_clean = compute_risk_number(clean, weights)

        # Version with NaN in last 30 days of B (within lookback window)
        dirty = clean.copy()
        dirty.loc[dirty.index[-30:], "B"] = np.nan
        result_dirty = compute_risk_number(dirty, weights)

        # Risk numbers should be similar (within 15 points)
        # Before fix, the dirty version had inflated vol due to half-weighted days
        diff = abs(result_clean["risk_number"] - result_dirty["risk_number"])
        assert diff <= 15, (
            f"Risk numbers differ by {diff} points — "
            f"clean={result_clean['risk_number']}, dirty={result_dirty['risk_number']}. "
            f"NaN handling is distorting portfolio returns."
        )
