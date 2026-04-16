"""Tests for Cycle 48: stock signal component decomposition and conviction quality.

Verifies:
- get_stock_signal returns 'components' dict with all expected keys
- Component values are properly attributed (each adjustment tracked)
- Components sum to approximately the composite score (before clipping)
- _compute_conviction_quality classifies agreement correctly
- Conviction quality varies with component agreement patterns
- Backward compatibility: existing keys still present
"""

import unittest

import numpy as np

from backend.services.signal_engine import (
    get_market_signal,
    get_stock_signal,
    _compute_conviction_quality,
)


def _base_market_signal(**kwargs):
    """Helper: generate a simple market signal for stock signal tests."""
    defaults = dict(
        crash_prob_3m=10.0,
        regime="Bull",
        risk_score=0.5,
        sp500_1m_return=2.0,
        sp500_3m_return=5.0,
        vix=18.0,
    )
    defaults.update(kwargs)
    return get_market_signal(**defaults)


class TestStockSignalComponents(unittest.TestCase):
    """Verify component decomposition is present and correctly structured."""

    def test_components_key_present(self):
        """get_stock_signal must return a 'components' dict."""
        mkt = _base_market_signal()
        result = get_stock_signal(mkt, beta=1.0)
        self.assertIn("components", result)
        self.assertIsInstance(result["components"], dict)

    def test_all_component_keys_present(self):
        """All expected component keys must be in the output."""
        mkt = _base_market_signal()
        result = get_stock_signal(
            mkt, beta=1.2,
            analyst_target=150, current_price=100,
            pe_ratio=25, forward_pe=20,
            stock_vol=0.30, drawdown_from_peak=-5.0,
            stock_momentum_1m=3.0, stock_momentum_3m=8.0,
            options_signal_score=0.2,
            earnings_signal_score=0.3,
        )
        expected_keys = {
            "market_base", "beta_adjustment", "analyst_target",
            "sector_momentum", "valuation", "crash_risk",
            "drawdown", "momentum", "options", "earnings",
            "insider", "technical",
        }
        self.assertEqual(set(result["components"].keys()), expected_keys)

    def test_components_are_numeric(self):
        """All component values must be finite numbers."""
        mkt = _base_market_signal()
        result = get_stock_signal(mkt, beta=1.5, stock_momentum_3m=10.0)
        for key, val in result["components"].items():
            self.assertIsInstance(val, float, f"{key} is not float")
            self.assertTrue(np.isfinite(val), f"{key} is not finite")

    def test_market_base_matches_market_composite(self):
        """market_base component must equal the market signal's composite score."""
        mkt = _base_market_signal()
        result = get_stock_signal(mkt, beta=1.0)
        self.assertAlmostEqual(
            result["components"]["market_base"],
            mkt["composite_score"],
            places=3,
        )

    def test_beta_adjustment_nonzero_for_high_beta(self):
        """High beta must produce a non-zero beta_adjustment component."""
        mkt = _base_market_signal()
        result = get_stock_signal(mkt, beta=1.8)
        self.assertNotAlmostEqual(result["components"]["beta_adjustment"], 0.0, places=3)

    def test_beta_adjustment_zero_for_beta_one(self):
        """Beta = 1.0 must produce zero beta_adjustment."""
        mkt = _base_market_signal()
        result = get_stock_signal(mkt, beta=1.0)
        self.assertAlmostEqual(result["components"]["beta_adjustment"], 0.0, places=4)

    def test_analyst_target_positive_for_upside(self):
        """Analyst target above price must produce positive contribution."""
        mkt = _base_market_signal()
        result = get_stock_signal(mkt, beta=1.0, analyst_target=130, current_price=100)
        self.assertGreater(result["components"]["analyst_target"], 0)

    def test_analyst_target_negative_for_downside(self):
        """Analyst target below price must produce negative contribution."""
        mkt = _base_market_signal()
        result = get_stock_signal(mkt, beta=1.0, analyst_target=70, current_price=100)
        self.assertLess(result["components"]["analyst_target"], 0)

    def test_analyst_target_zero_when_missing(self):
        """No analyst target must produce zero contribution."""
        mkt = _base_market_signal()
        result = get_stock_signal(mkt, beta=1.0)
        self.assertAlmostEqual(result["components"]["analyst_target"], 0.0)

    def test_momentum_positive_for_strong_returns(self):
        """Strong stock momentum must produce positive momentum component."""
        mkt = _base_market_signal()
        result = get_stock_signal(mkt, beta=1.0, stock_momentum_1m=8.0, stock_momentum_3m=15.0)
        self.assertGreater(result["components"]["momentum"], 0)

    def test_momentum_negative_for_weak_returns(self):
        """Weak stock momentum must produce negative momentum component."""
        mkt = _base_market_signal()
        result = get_stock_signal(mkt, beta=1.0, stock_momentum_1m=-10.0, stock_momentum_3m=-18.0)
        self.assertLess(result["components"]["momentum"], 0)

    def test_drawdown_positive_near_highs(self):
        """Stock near 52w high must produce positive drawdown component."""
        mkt = _base_market_signal()
        result = get_stock_signal(mkt, beta=1.0, drawdown_from_peak=-1.0)
        self.assertGreater(result["components"]["drawdown"], 0)

    def test_drawdown_negative_in_correction(self):
        """Stock in correction must produce negative drawdown component."""
        mkt = _base_market_signal()
        result = get_stock_signal(mkt, beta=1.0, drawdown_from_peak=-15.0)
        self.assertLess(result["components"]["drawdown"], 0)

    def test_options_contribution_tracked(self):
        """Options signal must appear in components."""
        mkt = _base_market_signal()
        result = get_stock_signal(mkt, beta=1.0, options_signal_score=-0.5)
        self.assertLess(result["components"]["options"], 0)

    def test_earnings_contribution_tracked(self):
        """Earnings signal must appear in components."""
        mkt = _base_market_signal()
        result = get_stock_signal(mkt, beta=1.0, earnings_signal_score=0.6)
        self.assertGreater(result["components"]["earnings"], 0)

    def test_components_sum_approximates_composite(self):
        """Sum of all components should approximately equal composite_score
        (may differ slightly due to clipping at [-1, 1])."""
        mkt = _base_market_signal()
        result = get_stock_signal(
            mkt, beta=1.1,
            analyst_target=120, current_price=100,
            stock_momentum_1m=3.0, stock_momentum_3m=5.0,
            drawdown_from_peak=-2.0,
            options_signal_score=0.1,
            earnings_signal_score=0.2,
        )
        component_sum = sum(result["components"].values())
        composite = result["composite_score"]
        # Should be close unless clipping occurred
        if -0.9 < composite < 0.9:
            self.assertAlmostEqual(component_sum, composite, delta=0.05)


class TestStockSignalBackwardCompatibility(unittest.TestCase):
    """Existing keys must still be present after adding components."""

    def test_existing_keys_preserved(self):
        mkt = _base_market_signal()
        result = get_stock_signal(mkt, beta=1.0)
        for key in ["action", "confidence", "color", "composite_score", "reasons", "beta_adj"]:
            self.assertIn(key, result, f"Missing existing key: {key}")

    def test_conviction_key_present(self):
        mkt = _base_market_signal()
        result = get_stock_signal(mkt, beta=1.0)
        self.assertIn("conviction", result)
        self.assertIsInstance(result["conviction"], dict)

    def test_conviction_has_required_fields(self):
        mkt = _base_market_signal()
        result = get_stock_signal(mkt, beta=1.0, stock_momentum_3m=5.0)
        conv = result["conviction"]
        for key in ["quality", "agreement_pct", "dominant_driver", "n_contributing"]:
            self.assertIn(key, conv, f"Missing conviction key: {key}")


class TestConvictionQuality(unittest.TestCase):
    """Test _compute_conviction_quality directly."""

    def test_all_positive_components_high_quality(self):
        """When all stock components agree (bullish), quality should be high."""
        components = {
            "market_base": 0.2,
            "beta_adjustment": 0.02,
            "analyst_target": 0.05,
            "momentum": 0.04,
            "drawdown": 0.03,
            "valuation": 0.02,
            "options": 0.01,
            "earnings": 0.01,
            "crash_risk": 0.0,
            "sector_momentum": 0.0,
        }
        result = _compute_conviction_quality(components)
        self.assertEqual(result["quality"], "high")
        self.assertGreaterEqual(result["agreement_pct"], 75)

    def test_mixed_components_low_quality(self):
        """When components are evenly split, quality should be low."""
        components = {
            "market_base": 0.1,
            "beta_adjustment": 0.05,
            "analyst_target": 0.06,
            "momentum": -0.05,
            "drawdown": -0.04,
            "valuation": -0.03,
            "options": -0.02,
            "earnings": 0.0,
            "crash_risk": 0.0,
            "sector_momentum": 0.0,
        }
        result = _compute_conviction_quality(components)
        # Mixed: 2 positive, 3 negative (excluding market_base and zeros)
        self.assertIn(result["quality"], ("low", "moderate"))

    def test_no_stock_components_returns_low(self):
        """When only market_base contributes, quality is low (no stock info)."""
        components = {
            "market_base": 0.3,
            "beta_adjustment": 0.0,
            "analyst_target": 0.0,
            "momentum": 0.0,
            "drawdown": 0.0,
            "valuation": 0.0,
            "options": 0.0,
            "earnings": 0.0,
            "crash_risk": 0.0,
            "sector_momentum": 0.0,
        }
        result = _compute_conviction_quality(components)
        self.assertEqual(result["quality"], "low")
        self.assertEqual(result["n_contributing"], 0)

    def test_dominant_driver_identified(self):
        """Dominant driver should be the largest absolute contributor."""
        components = {
            "market_base": 0.1,
            "beta_adjustment": 0.0,
            "analyst_target": 0.0,
            "momentum": 0.15,
            "drawdown": -0.02,
            "valuation": 0.0,
            "options": 0.0,
            "earnings": 0.0,
            "crash_risk": 0.0,
            "sector_momentum": 0.0,
        }
        result = _compute_conviction_quality(components)
        self.assertEqual(result["dominant_driver"], "momentum")

    def test_n_contributing_counts_nonzero(self):
        """n_contributing should count only non-zero stock components."""
        components = {
            "market_base": 0.2,
            "beta_adjustment": 0.05,
            "analyst_target": 0.03,
            "momentum": 0.0,
            "drawdown": 0.0,
            "valuation": 0.0,
            "options": 0.0,
            "earnings": 0.0,
            "crash_risk": 0.0,
            "sector_momentum": 0.0,
        }
        result = _compute_conviction_quality(components)
        self.assertEqual(result["n_contributing"], 2)  # beta_adjustment + analyst_target

    def test_agreement_pct_is_percentage(self):
        """agreement_pct should be 0-100."""
        components = {
            "market_base": 0.1,
            "beta_adjustment": 0.05,
            "analyst_target": 0.03,
            "momentum": -0.02,
            "drawdown": 0.0,
            "valuation": 0.0,
            "options": 0.0,
            "earnings": 0.0,
            "crash_risk": 0.0,
            "sector_momentum": 0.0,
        }
        result = _compute_conviction_quality(components)
        self.assertGreaterEqual(result["agreement_pct"], 0)
        self.assertLessEqual(result["agreement_pct"], 100)

    def test_quality_values_are_valid(self):
        """Quality must be one of the defined levels."""
        for components in [
            {"market_base": 0.5, "momentum": 0.1, "drawdown": 0.05, "valuation": 0.03, "analyst_target": 0.02},
            {"market_base": 0.1, "momentum": 0.1, "drawdown": -0.1, "analyst_target": 0.0},
            {"market_base": 0.3, "momentum": -0.2, "drawdown": 0.15, "valuation": -0.1, "analyst_target": 0.05},
        ]:
            result = _compute_conviction_quality(components)
            self.assertIn(result["quality"], ("high", "moderate", "low"))


class TestConvictionIntegration(unittest.TestCase):
    """Test conviction quality through the full get_stock_signal flow."""

    def test_all_bullish_inputs_high_conviction(self):
        """Bullish across all dimensions should produce high conviction."""
        mkt = _base_market_signal(
            crash_prob_3m=5.0, regime="Bull", vix=15.0,
            sp500_1m_return=5.0, sp500_3m_return=10.0,
        )
        result = get_stock_signal(
            mkt, beta=1.0,
            analyst_target=140, current_price=100,
            stock_momentum_1m=8.0, stock_momentum_3m=15.0,
            drawdown_from_peak=-1.0,
            options_signal_score=0.5,
            earnings_signal_score=0.6,
        )
        self.assertEqual(result["conviction"]["quality"], "high")

    def test_mixed_inputs_not_high_conviction(self):
        """Conflicting signals (strong momentum but deep drawdown) should
        produce lower conviction."""
        mkt = _base_market_signal()
        result = get_stock_signal(
            mkt, beta=1.0,
            analyst_target=80, current_price=100,  # bearish
            stock_momentum_1m=10.0, stock_momentum_3m=20.0,  # bullish
            drawdown_from_peak=-25.0,  # bearish
            options_signal_score=0.5,  # bullish
            earnings_signal_score=-0.5,  # bearish
        )
        self.assertNotEqual(result["conviction"]["quality"], "high")

    def test_conviction_dominant_driver_meaningful(self):
        """Dominant driver should be a real component name."""
        mkt = _base_market_signal()
        result = get_stock_signal(
            mkt, beta=1.5,
            stock_momentum_3m=-20.0,
            drawdown_from_peak=-30.0,
        )
        valid_drivers = {
            "market_base", "beta_adjustment", "analyst_target",
            "sector_momentum", "valuation", "crash_risk",
            "drawdown", "momentum", "options", "earnings",
        }
        self.assertIn(result["conviction"]["dominant_driver"], valid_drivers)


class TestComponentDifferentiation(unittest.TestCase):
    """Verify that components differentiate across stocks with different profiles."""

    def test_growth_vs_value_stock_components_differ(self):
        """A growth stock (high PE, strong momentum) and value stock (low PE, weak momentum)
        should have visibly different component profiles."""
        mkt = _base_market_signal()

        growth = get_stock_signal(
            mkt, beta=1.5,
            pe_ratio=60, forward_pe=40,
            stock_momentum_1m=8.0, stock_momentum_3m=15.0,
            drawdown_from_peak=-2.0,
        )
        value = get_stock_signal(
            mkt, beta=0.7,
            pe_ratio=8, forward_pe=7,
            stock_momentum_1m=-2.0, stock_momentum_3m=-5.0,
            drawdown_from_peak=-12.0,
        )

        # Growth should have higher momentum, lower valuation
        self.assertGreater(
            growth["components"]["momentum"],
            value["components"]["momentum"],
        )
        # Value should have better valuation component
        self.assertGreater(
            value["components"]["valuation"],
            growth["components"]["valuation"],
        )

    def test_different_betas_different_components(self):
        """Different betas should produce different beta_adjustment components."""
        mkt = _base_market_signal()
        low_beta = get_stock_signal(mkt, beta=0.5)
        high_beta = get_stock_signal(mkt, beta=2.0)
        self.assertNotAlmostEqual(
            low_beta["components"]["beta_adjustment"],
            high_beta["components"]["beta_adjustment"],
            places=2,
        )


if __name__ == "__main__":
    unittest.main()
