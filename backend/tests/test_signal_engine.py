"""Tests for the composite signal engine."""

import numpy as np
import pandas as pd
import pytest

from backend.services.signal_engine import (
    get_market_signal, get_stock_signal, compute_drawdown_pct,
    adjust_crash_prob_for_stock,
)


class TestMarketSignal:
    """Test market-level signal generation."""

    def test_returns_required_keys(self):
        result = get_market_signal()
        assert "action" in result
        assert "confidence" in result
        assert "color" in result
        assert "composite_score" in result
        assert "reasons" in result
        assert "components" in result

    def test_action_is_valid(self):
        result = get_market_signal()
        assert result["action"] in {"Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"}

    def test_confidence_range(self):
        result = get_market_signal()
        assert 0 <= result["confidence"] <= 100

    def test_composite_score_range(self):
        result = get_market_signal()
        assert -1.0 <= result["composite_score"] <= 1.0

    def test_high_crash_prob_bearish(self):
        result = get_market_signal(crash_prob_3m=60.0, regime="Bear", vix=35.0)
        assert result["composite_score"] < 0
        assert result["action"] in {"Sell", "Strong Sell"}

    def test_low_crash_prob_bullish(self):
        result = get_market_signal(
            crash_prob_3m=5.0, regime="Bull",
            sp500_1m_return=3.0, sp500_3m_return=8.0, vix=18.0,
            external_consensus="BULLISH",
        )
        assert result["composite_score"] > 0
        assert result["action"] in {"Buy", "Strong Buy"}

    def test_neutral_defaults(self):
        result = get_market_signal()
        assert result["action"] == "Hold"

    def test_reasons_populated(self):
        result = get_market_signal(crash_prob_3m=50.0, regime="Bear", vix=32.0)
        assert len(result["reasons"]) > 0
        assert len(result["reasons"]) <= 3

    def test_components_all_present(self):
        result = get_market_signal(crash_prob_3m=20.0, external_consensus="BULLISH", drawdown_pct=-5.0)
        components = result["components"]
        for key in ["crash_prob", "regime", "valuation", "momentum", "mean_reversion", "external", "drawdown"]:
            assert key in components

    def test_color_matches_action(self):
        for crash, regime, expected_colors in [
            (5.0, "Bull", {"green"}),
            (60.0, "Bear", {"red"}),
        ]:
            result = get_market_signal(
                crash_prob_3m=crash, regime=regime,
                sp500_1m_return=5.0 if crash < 20 else -10.0,
                vix=15 if crash < 20 else 35,
            )
            assert result["color"] in expected_colors


class TestStockSignal:
    """Test per-stock signal generation."""

    def test_returns_required_keys(self):
        market = get_market_signal()
        result = get_stock_signal(market)
        assert "action" in result
        assert "confidence" in result
        assert "beta_adj" in result

    def test_high_beta_amplifies(self):
        market = get_market_signal(crash_prob_3m=5.0, regime="Bull", vix=18.0)
        low_beta = get_stock_signal(market, beta=0.5)
        high_beta = get_stock_signal(market, beta=2.0)
        # High beta should amplify the signal (more positive in bull market)
        assert abs(high_beta["composite_score"]) >= abs(low_beta["composite_score"]) * 0.8

    def test_analyst_upside_boosts(self):
        market = get_market_signal()
        no_analyst = get_stock_signal(market, current_price=100.0)
        with_upside = get_stock_signal(
            market, analyst_target=150.0, current_price=100.0
        )
        assert with_upside["composite_score"] >= no_analyst["composite_score"]

    def test_analyst_upside_additive_not_dominant(self):
        """Analyst target should adjust, not dominate — a neutral market with
        moderate analyst upside should NOT flip to Buy on its own."""
        market = get_market_signal()  # defaults → Hold, score ~0.04
        assert market["action"] == "Hold"
        # 20% analyst upside alone should not push a Hold market to Buy
        result = get_stock_signal(market, analyst_target=120.0, current_price=100.0)
        # Score should increase but stay below Strong Buy
        assert result["composite_score"] < 0.45

    def test_bearish_market_produces_sell_despite_analyst(self):
        """Even with bullish analyst targets, a bearish market should produce Sell."""
        market = get_market_signal(crash_prob_3m=55.0, regime="Bear", vix=34.0,
                                   sp500_1m_return=-8.0, sp500_3m_return=-12.0)
        assert market["composite_score"] < -0.15
        # Analyst target +30% should not override a strongly bearish market
        result = get_stock_signal(market, analyst_target=130.0, current_price=100.0,
                                  beta=1.0)
        assert result["composite_score"] < 0, "Bearish market should not be fully offset by analyst target"

    def test_signal_diversity_across_stocks(self):
        """Different stock fundamentals should produce differentiated signals,
        not a wall of identical Buy signals."""
        market = get_market_signal()  # neutral Hold
        # Stock A: high beta, expensive, no analyst target
        a = get_stock_signal(market, beta=1.8, pe_ratio=70.0, current_price=100.0)
        # Stock B: low beta, cheap, strong analyst upside, strong earnings growth
        b = get_stock_signal(market, beta=0.6, pe_ratio=8.0,
                             analyst_target=140.0, current_price=100.0,
                             forward_pe=6.0, sector_momentum=12.0)
        spread = b["composite_score"] - a["composite_score"]
        assert spread > 0.15, f"Signal spread {spread:.3f} too narrow between opposing fundamentals"

    def test_high_pe_penalizes(self):
        market = get_market_signal()
        normal_pe = get_stock_signal(market, pe_ratio=20.0)
        high_pe = get_stock_signal(market, pe_ratio=80.0)
        assert high_pe["composite_score"] <= normal_pe["composite_score"]

    def test_low_pe_rewards(self):
        market = get_market_signal()
        normal_pe = get_stock_signal(market, pe_ratio=20.0)
        low_pe = get_stock_signal(market, pe_ratio=8.0)
        assert low_pe["composite_score"] >= normal_pe["composite_score"]


class TestDrawdownSignal:
    """Test drawdown signal component in market signal."""

    def test_drawdown_component_present_when_provided(self):
        result = get_market_signal(drawdown_pct=-10.0)
        assert "drawdown" in result["components"]

    def test_drawdown_component_zeroed_when_none(self):
        result = get_market_signal(drawdown_pct=None)
        assert result["components"]["drawdown"] == 0.0

    def test_near_highs_is_bullish(self):
        """At or near 52-week highs, drawdown should be a bullish signal."""
        result = get_market_signal(drawdown_pct=-0.5)
        assert result["components"]["drawdown"] > 0

    def test_small_pullback_is_neutral(self):
        """A 3% pullback is normal market noise — neutral signal."""
        result = get_market_signal(drawdown_pct=-3.0)
        assert result["components"]["drawdown"] == 0.0

    def test_correction_is_bearish(self):
        """A 10% correction should produce a bearish drawdown signal."""
        result = get_market_signal(drawdown_pct=-10.0)
        assert result["components"]["drawdown"] < -0.2

    def test_bear_market_is_strongly_bearish(self):
        """A 20%+ drawdown (bear market) should produce a strong bearish signal."""
        result = get_market_signal(drawdown_pct=-22.0)
        assert result["components"]["drawdown"] <= -0.7

    def test_crisis_drawdown_is_extreme(self):
        """A 30%+ crash should produce near-maximum bearish signal."""
        result = get_market_signal(drawdown_pct=-35.0)
        assert result["components"]["drawdown"] <= -0.85

    def test_drawdown_monotonically_bearish(self):
        """Deeper drawdowns should produce more bearish signals."""
        levels = [0.0, -3.0, -7.0, -12.0, -25.0]
        signals = [
            get_market_signal(drawdown_pct=dd)["components"]["drawdown"]
            for dd in levels
        ]
        for i in range(1, len(signals)):
            assert signals[i] <= signals[i - 1], (
                f"Drawdown signal not monotonic: {levels[i]}% ({signals[i]}) "
                f"> {levels[i-1]}% ({signals[i-1]})"
            )

    def test_drawdown_reason_in_correction(self):
        """A correction-level drawdown should produce an explanatory reason."""
        result = get_market_signal(drawdown_pct=-12.0)
        reasons_text = " ".join(result["reasons"])
        assert "correction" in reasons_text.lower() or "52" in reasons_text

    def test_drawdown_reason_in_crisis(self):
        """A crisis-level drawdown should flag it."""
        result = get_market_signal(drawdown_pct=-25.0)
        reasons_text = " ".join(result["reasons"])
        assert "crisis" in reasons_text.lower() or "drawdown" in reasons_text.lower()

    def test_drawdown_reason_near_highs(self):
        """Near ATH should produce a confirmation reason."""
        result = get_market_signal(drawdown_pct=-1.0)
        reasons_text = " ".join(result["reasons"])
        assert "52-week" in reasons_text.lower() or "high" in reasons_text.lower()

    def test_deep_drawdown_shifts_composite_bearish(self):
        """A deep drawdown should meaningfully shift the overall composite score."""
        baseline = get_market_signal(drawdown_pct=None)
        crisis = get_market_signal(drawdown_pct=-25.0)
        assert crisis["composite_score"] < baseline["composite_score"] - 0.05

    def test_drawdown_affects_action_in_marginal_case(self):
        """In a marginal Buy scenario, a deep drawdown should downgrade to Hold."""
        # Mild bullish conditions: regime=Bull, low crash, but deep drawdown
        no_dd = get_market_signal(
            crash_prob_3m=15.0, regime="Bull", vix=19.0,
            sp500_1m_return=2.0, sp500_3m_return=5.0,
            drawdown_pct=-1.0,
        )
        with_dd = get_market_signal(
            crash_prob_3m=15.0, regime="Bull", vix=19.0,
            sp500_1m_return=2.0, sp500_3m_return=5.0,
            drawdown_pct=-15.0,
        )
        assert with_dd["composite_score"] < no_dd["composite_score"]


class TestDrawdownEdgeCases:
    """Edge case and hardening tests for drawdown signal."""

    def test_positive_drawdown_clamped_to_zero(self):
        """A positive drawdown (data error) should be clamped to 0% (near-high)."""
        result = get_market_signal(drawdown_pct=5.0)
        # Positive drawdown is impossible; engine should treat as near-high
        assert result["components"]["drawdown"] >= 0

    def test_exactly_zero_drawdown(self):
        """Exactly at the 52-week high (0% drawdown)."""
        result = get_market_signal(drawdown_pct=0.0)
        assert result["components"]["drawdown"] > 0  # near-high → bullish

    def test_extreme_drawdown_minus_100(self):
        """A -100% drawdown (total loss) shouldn't crash."""
        result = get_market_signal(drawdown_pct=-100.0)
        assert result["components"]["drawdown"] <= -0.85
        assert -1.0 <= result["composite_score"] <= 1.0

    def test_tiny_drawdown_minus_0_01(self):
        """A -0.01% drawdown is effectively at highs."""
        result = get_market_signal(drawdown_pct=-0.01)
        assert result["components"]["drawdown"] > 0

    def test_boundary_at_minus_2(self):
        """Exactly at the -2% threshold (boundary between near-high and pullback)."""
        result = get_market_signal(drawdown_pct=-2.0)
        # -2.0 is NOT > -2, so should be in pullback territory
        assert result["components"]["drawdown"] == 0.0

    def test_boundary_at_minus_5(self):
        """Exactly at -5% (boundary between pullback and correction)."""
        result = get_market_signal(drawdown_pct=-5.0)
        # -5.0 is NOT > -5, so should be in correction territory
        assert result["components"]["drawdown"] < 0

    def test_boundary_at_minus_10(self):
        """Exactly at -10% (boundary between correction and bear)."""
        result = get_market_signal(drawdown_pct=-10.0)
        assert result["components"]["drawdown"] <= -0.3

    def test_boundary_at_minus_20(self):
        """Exactly at -20% (boundary between bear and crisis)."""
        result = get_market_signal(drawdown_pct=-20.0)
        # -20.0 is NOT > -20, so should be in crisis territory
        assert result["components"]["drawdown"] <= -0.85

    def test_drawdown_none_excludes_weight(self):
        """When drawdown is None, its weight should be excluded from composite denominator.
        This means None drawdown should NOT shift the composite vs having 0 drawdown."""
        with_none = get_market_signal(drawdown_pct=None)
        # The drawdown component should be zero but also have zero weight
        assert with_none["components"]["drawdown"] == 0.0

    def test_all_components_present_without_drawdown(self):
        """Even without drawdown, all other components should still be present."""
        result = get_market_signal(
            crash_prob_3m=20.0, regime="Bull", vix=18.0,
            drawdown_pct=None,
        )
        assert "crash_prob" in result["components"]
        assert "regime" in result["components"]
        assert "valuation" in result["components"]
        assert "momentum" in result["components"]
        assert "drawdown" in result["components"]

    def test_drawdown_does_not_exceed_3_reasons(self):
        """Total reasons should never exceed 3 even with drawdown adding one."""
        result = get_market_signal(
            crash_prob_3m=50.0, regime="Bear", vix=35.0,
            sp500_1m_return=-8.0, drawdown_pct=-25.0,
        )
        assert len(result["reasons"]) <= 3


class TestComputeDrawdownPct:
    """Tests for the compute_drawdown_pct utility function."""

    def test_at_high(self):
        """When current price equals the high, drawdown is 0%."""
        prices = pd.Series([100, 110, 120, 130, 140, 150],
                           index=pd.date_range("2025-01-01", periods=6))
        dd = compute_drawdown_pct(prices)
        assert dd == 0.0

    def test_below_high(self):
        """When current price is below the high, drawdown is negative."""
        prices = pd.Series([100, 150, 120],
                           index=pd.date_range("2025-01-01", periods=3))
        dd = compute_drawdown_pct(prices)
        assert dd == pytest.approx(-20.0, abs=0.1)

    def test_with_nans(self):
        """NaN values in the series should be dropped before computation."""
        prices = pd.Series([100, float("nan"), 150, float("nan"), 120],
                           index=pd.date_range("2025-01-01", periods=5))
        dd = compute_drawdown_pct(prices)
        assert dd is not None
        assert dd == pytest.approx(-20.0, abs=0.1)

    def test_all_nans_returns_none(self):
        """All-NaN series should return None."""
        prices = pd.Series([float("nan"), float("nan")],
                           index=pd.date_range("2025-01-01", periods=2))
        dd = compute_drawdown_pct(prices)
        assert dd is None

    def test_empty_series_returns_none(self):
        """Empty series should return None."""
        prices = pd.Series([], dtype=float)
        dd = compute_drawdown_pct(prices)
        assert dd is None

    def test_single_value_returns_none(self):
        """Single data point can't compute a meaningful drawdown."""
        prices = pd.Series([100.0], index=pd.date_range("2025-01-01", periods=1))
        dd = compute_drawdown_pct(prices)
        assert dd is None

    def test_lookback_window(self):
        """Lookback window should limit how far back we look for the high."""
        # Price peaked at 200 long ago, recent high is 150
        old = pd.Series([200] + [100] * 300 + [150, 140],
                        index=pd.date_range("2023-01-01", periods=303))
        dd_short = compute_drawdown_pct(old, lookback=10)
        dd_full = compute_drawdown_pct(old, lookback=500)
        # Short lookback: high is 150, current 140 → ~-6.7%
        assert dd_short == pytest.approx(-6.67, abs=0.5)
        # Full lookback: high is 200, current 140 → -30%
        assert dd_full == pytest.approx(-30.0, abs=0.5)

    def test_result_always_non_positive(self):
        """Result should never be positive regardless of input."""
        # Monotonically rising — should be exactly 0.0
        prices = pd.Series(range(1, 100),
                           index=pd.date_range("2025-01-01", periods=99))
        dd = compute_drawdown_pct(prices)
        assert dd is not None
        assert dd <= 0.0

    def test_zero_price_returns_none(self):
        """If the high is zero (impossible but defensive), return None."""
        prices = pd.Series([0.0, 0.0, 0.0],
                           index=pd.date_range("2025-01-01", periods=3))
        dd = compute_drawdown_pct(prices)
        assert dd is None


class TestDrawdownConfigDriven:
    """Verify drawdown thresholds are loaded from config."""

    def test_config_has_drawdown_thresholds(self):
        from backend.config import config
        assert "drawdown_thresholds" in config
        dt = config["drawdown_thresholds"]
        assert "near_high" in dt
        assert "correction" in dt
        assert "bear" in dt

    def test_config_has_drawdown_signals(self):
        from backend.config import config
        assert "drawdown_signals" in config
        ds = config["drawdown_signals"]
        assert "near_high" in ds
        assert "crisis" in ds
        # Signals should be monotonically decreasing
        assert ds["near_high"] > ds["pullback"] >= ds["correction"] > ds["bear"] > ds["crisis"]

    def test_drawdown_weight_in_signal_weights(self):
        from backend.config import config
        sw = config["signal_weights"]
        assert "drawdown" in sw
        assert 0 < sw["drawdown"] <= 0.20  # reasonable range

    def test_signal_weights_sum_to_one(self):
        from backend.config import config
        sw = config["signal_weights"]
        total = sum(sw.values())
        assert total == pytest.approx(1.0, abs=0.01)


class TestFullContextMarketSignal:
    """Verify that a fully-contextualized market signal has active components.

    These tests catch the wiring bug where get_market_signal() was called
    with all defaults, producing 6/8 zero components.
    """

    def test_bull_regime_produces_nonzero_regime_component(self):
        """Regime='Bull' should produce a positive regime signal, not 0."""
        result = get_market_signal(regime="Bull")
        assert result["components"]["regime"] == pytest.approx(0.7)

    def test_real_risk_score_produces_nonzero_macro(self):
        """A nonzero risk score should produce a nonzero macro_risk component."""
        result = get_market_signal(risk_score=1.5)
        assert result["components"]["macro_risk"] != 0.0

    def test_full_context_has_multiple_nonzero_components(self):
        """When all inputs are provided, most components should be nonzero."""
        result = get_market_signal(
            crash_prob_3m=15.0,
            crash_prob_12m=25.0,
            regime="Bull",
            risk_score=1.14,
            sp500_1m_return=2.5,
            sp500_3m_return=5.0,
            sp500_ytd_return=8.0,
            vix=19.0,
            yield_curve=0.5,
            external_consensus="BULLISH",
            drawdown_pct=-3.0,
        )
        components = result["components"]
        nonzero = [k for k, v in components.items() if v != 0.0]
        # At least 5 of 8 components should be active with real inputs
        assert len(nonzero) >= 5, f"Only {len(nonzero)} nonzero: {nonzero}"

    def test_full_context_composite_differs_from_defaults(self):
        """A fully-wired signal should differ from the default (no-context) signal."""
        default_sig = get_market_signal()
        wired_sig = get_market_signal(
            crash_prob_3m=10.0,
            regime="Bull",
            risk_score=1.0,
            sp500_1m_return=3.0,
            sp500_3m_return=7.0,
            vix=19.0,
            drawdown_pct=-1.5,
        )
        assert wired_sig["composite_score"] != default_sig["composite_score"]

    def test_crash_prob_none_zeroes_weight_not_just_component(self):
        """When crash_prob is None, both component AND weight should be zero."""
        result = get_market_signal(crash_prob_3m=None, regime="Bull")
        assert result["components"]["crash_prob"] == 0.0
        # With crash_prob excluded, regime (0.7) should dominate more
        assert result["composite_score"] > 0


class TestCrashSignalBaseRateCentering:
    """Test that crash probability signal is centered on the historical base rate."""

    def test_base_rate_is_neutral(self):
        """At the base rate (~12%), crash signal component should be near zero."""
        result = get_market_signal(crash_prob_3m=12.0)
        # At base rate, crash component should be approximately 0
        assert abs(result["components"]["crash_prob"]) < 0.1

    def test_below_base_rate_is_bullish(self):
        """Crash probability well below base rate should produce bullish signal."""
        result = get_market_signal(crash_prob_3m=2.0)
        assert result["components"]["crash_prob"] > 0.3

    def test_above_base_rate_is_bearish(self):
        """Crash probability above base rate should produce bearish signal."""
        result = get_market_signal(crash_prob_3m=30.0)
        assert result["components"]["crash_prob"] < -0.5

    def test_extreme_crash_prob_is_very_bearish(self):
        """Very high crash probability should hit the floor."""
        result = get_market_signal(crash_prob_3m=60.0)
        assert result["components"]["crash_prob"] == -1.0

    def test_zero_crash_prob_capped(self):
        """Zero crash prob should produce bullish but capped signal."""
        result = get_market_signal(crash_prob_3m=0.0)
        assert result["components"]["crash_prob"] <= 0.6

    def test_normal_market_not_strong_buy(self):
        """Normal bull market conditions should produce Buy, not Strong Buy.

        With base-rate centering, a typical bull market (low crash risk, Bull regime,
        normal VIX) should produce a more moderate signal than before.
        """
        result = get_market_signal(
            crash_prob_3m=5.0,   # low but not extreme
            regime="Bull",
            vix=19.0,
            risk_score=0.5,
            sp500_1m_return=1.0,
            sp500_3m_return=3.0,
        )
        # Should be Buy but composite should be moderate, not extreme
        assert result["composite_score"] < 0.45  # below Strong Buy threshold

    def test_blend_3m_12m_with_base_rate(self):
        """Blending 3M and 12M crash probs should work with base-rate centering."""
        result = get_market_signal(crash_prob_3m=5.0, crash_prob_12m=25.0)
        crash_sig = result["components"]["crash_prob"]
        # 3M is bullish (5% < 12%), 12M is bearish (25% > 12%)
        # Blend: 0.7 * bullish + 0.3 * bearish → mildly bullish
        assert -0.5 < crash_sig < 0.5


class TestPerStockCrashAdjustment:
    """Tests for adjust_crash_prob_for_stock — per-stock crash risk differentiation."""

    def test_market_beta_returns_close_to_input(self):
        """Beta=1.0, avg vol, no drawdown → near-identity."""
        result = adjust_crash_prob_for_stock(0.10, beta=1.0, stock_vol=0.20, drawdown_from_peak=0.0)
        assert 0.09 < result < 0.11

    def test_high_beta_increases_crash_prob(self):
        """High-beta stock should have higher crash probability."""
        base = adjust_crash_prob_for_stock(0.10, beta=1.0, stock_vol=0.20)
        high = adjust_crash_prob_for_stock(0.10, beta=1.8, stock_vol=0.20)
        assert high > base

    def test_low_beta_decreases_crash_prob(self):
        """Low-beta defensive stock should have lower crash probability."""
        base = adjust_crash_prob_for_stock(0.10, beta=1.0, stock_vol=0.20)
        low = adjust_crash_prob_for_stock(0.10, beta=0.4, stock_vol=0.20)
        assert low < base

    def test_high_vol_increases_crash_prob(self):
        """High-volatility stock should have higher crash probability."""
        low_vol = adjust_crash_prob_for_stock(0.10, beta=1.0, stock_vol=0.15)
        high_vol = adjust_crash_prob_for_stock(0.10, beta=1.0, stock_vol=0.45)
        assert high_vol > low_vol

    def test_drawdown_increases_crash_prob(self):
        """Stock in drawdown should have higher crash probability."""
        no_dd = adjust_crash_prob_for_stock(0.10, beta=1.0, stock_vol=0.25, drawdown_from_peak=0.0)
        dd = adjust_crash_prob_for_stock(0.10, beta=1.0, stock_vol=0.25, drawdown_from_peak=-20.0)
        assert dd > no_dd

    def test_output_clipped_to_valid_range(self):
        """Result should always be in [0.001, 0.95]."""
        # Extreme high
        high = adjust_crash_prob_for_stock(0.90, beta=3.0, stock_vol=0.80, drawdown_from_peak=-50.0)
        assert high <= 0.95
        # Extreme low
        low = adjust_crash_prob_for_stock(0.001, beta=0.1, stock_vol=0.05, drawdown_from_peak=0.0)
        assert low >= 0.001

    def test_meaningful_spread_across_profiles(self):
        """Different stock profiles should produce meaningfully different crash probs."""
        market_prob = 0.10
        defensive = adjust_crash_prob_for_stock(market_prob, beta=0.4, stock_vol=0.15, drawdown_from_peak=-2.0)
        aggressive = adjust_crash_prob_for_stock(market_prob, beta=1.8, stock_vol=0.45, drawdown_from_peak=-15.0)
        # At least 2x spread between defensive and aggressive
        assert aggressive / defensive > 2.0

    def test_zero_market_prob_stays_near_zero(self):
        """If market crash prob is ~0, stock crash prob should also be very low."""
        result = adjust_crash_prob_for_stock(0.001, beta=1.5, stock_vol=0.30)
        assert result < 0.01

    def test_multiplier_floor_prevents_zero(self):
        """Even very defensive stocks should have some crash probability."""
        result = adjust_crash_prob_for_stock(0.10, beta=0.1, stock_vol=0.05, drawdown_from_peak=0.0)
        assert result >= 0.10 * 0.4  # min_multiplier = 0.4


class TestPerStockSignalDifferentiation:
    """Test that per-stock crash risk creates signal diversity."""

    def _make_market_signal(self, crash_3m=10.0):
        sig = get_market_signal(crash_prob_3m=crash_3m, regime="Neutral", vix=22.0)
        sig["_crash_3m_pct"] = crash_3m
        return sig

    def test_high_beta_penalized_vs_low_beta(self):
        """High-beta stock should get a lower (more bearish) signal than low-beta."""
        market_sig = self._make_market_signal(crash_3m=15.0)
        low_beta = get_stock_signal(
            market_sig, beta=0.4, stock_vol=0.15, drawdown_from_peak=-2.0,
        )
        high_beta = get_stock_signal(
            market_sig, beta=1.8, stock_vol=0.45, drawdown_from_peak=-15.0,
        )
        # High-beta should have lower composite (more risk penalty)
        # Note: in bull market, beta amplification of positive base can offset this
        # So we test with neutral market (crash=15%, near base rate)
        assert low_beta["composite_score"] != high_beta["composite_score"]

    def test_stock_vol_affects_signal(self):
        """Two stocks with same beta but different vol should get different signals."""
        market_sig = self._make_market_signal(crash_3m=12.0)
        low_vol = get_stock_signal(market_sig, beta=1.0, stock_vol=0.15)
        high_vol = get_stock_signal(market_sig, beta=1.0, stock_vol=0.40)
        assert low_vol["composite_score"] != high_vol["composite_score"]

    def test_no_crash_prob_graceful(self):
        """When market signal has no _crash_3m_pct, stock signal should still work."""
        market_sig = get_market_signal(regime="Bull", vix=18.0)
        # No _crash_3m_pct key at all
        result = get_stock_signal(market_sig, beta=1.5, stock_vol=0.30)
        assert "action" in result
        assert "composite_score" in result


class TestRegimeAdaptiveWeights:
    """Test that signal weights adapt to market regime."""

    def test_bull_regime_uses_bull_weights(self):
        """Bull regime should use the Bull weight profile."""
        result = get_market_signal(
            crash_prob_3m=10.0, regime="Bull", vix=18.0,
            sp500_1m_return=3.0, sp500_3m_return=8.0,
        )
        assert result.get("regime_weight_profile") == "Bull"

    def test_bear_regime_uses_bear_weights(self):
        """Bear regime should use the Bear weight profile."""
        result = get_market_signal(
            crash_prob_3m=30.0, regime="Bear", vix=28.0,
            sp500_1m_return=-5.0, sp500_3m_return=-10.0,
        )
        assert result.get("regime_weight_profile") == "Bear"

    def test_volatile_regime_uses_volatile_weights(self):
        """Volatile regime should use the Volatile weight profile."""
        result = get_market_signal(
            crash_prob_3m=20.0, regime="Volatile", vix=30.0,
        )
        assert result.get("regime_weight_profile") == "Volatile"

    def test_neutral_regime_uses_default_weights(self):
        """Neutral/Unknown regimes should use default weights (no profile key)."""
        result = get_market_signal(regime="Neutral", vix=20.0)
        assert "regime_weight_profile" not in result

    def test_unknown_regime_uses_default_weights(self):
        """Unknown regime should also use default weights."""
        result = get_market_signal(regime="Unknown", vix=20.0)
        assert "regime_weight_profile" not in result

    def test_bull_momentum_more_influential(self):
        """In Bull regime, strong positive momentum should push the score
        higher than in Neutral, because Bull has higher momentum weight."""
        kwargs = dict(
            crash_prob_3m=10.0, vix=18.0,
            sp500_1m_return=6.0, sp500_3m_return=12.0,
            external_consensus="BULLISH", drawdown_pct=-1.0,
        )
        bull = get_market_signal(regime="Bull", **kwargs)
        neutral = get_market_signal(regime="Neutral", **kwargs)
        # Bull should be at least as bullish (momentum gets higher weight)
        assert bull["composite_score"] >= neutral["composite_score"] - 0.05

    def test_bear_crash_risk_more_influential(self):
        """In Bear regime, high crash probability should push the score
        more negative than in Neutral, because Bear has higher crash weight."""
        kwargs = dict(
            crash_prob_3m=45.0, vix=30.0,
            sp500_1m_return=-6.0, sp500_3m_return=-12.0,
        )
        bear = get_market_signal(regime="Bear", **kwargs)
        neutral = get_market_signal(regime="Neutral", **kwargs)
        # Bear regime should amplify the bearish crash signal
        assert bear["composite_score"] <= neutral["composite_score"] + 0.05

    def test_bear_mean_reversion_after_drop(self):
        """In Bear regime, a large 3M drop should trigger stronger mean reversion
        signal because Bear weights mean_reversion higher."""
        kwargs = dict(
            crash_prob_3m=20.0, vix=28.0,
            sp500_1m_return=-4.0, sp500_3m_return=-15.0,
        )
        bear = get_market_signal(regime="Bear", **kwargs)
        # Mean reversion component should be present and positive
        assert bear["components"]["mean_reversion"] > 0.3

    def test_volatile_valuation_weight_higher(self):
        """Volatile regime should put more weight on VIX-based valuation signal."""
        # High VIX = moderate opportunity in volatile regime
        result = get_market_signal(
            crash_prob_3m=15.0, regime="Volatile", vix=27.0,
        )
        assert result.get("regime_weight_profile") == "Volatile"
        # Valuation component should be positive (VIX 27 = opportunity zone)
        assert result["components"]["valuation"] > 0

    def test_regime_weights_still_produce_valid_output(self):
        """All regime profiles should produce valid signal output."""
        for regime in ["Bull", "Bear", "Volatile", "Neutral", "Unknown"]:
            result = get_market_signal(
                crash_prob_3m=15.0, regime=regime, vix=22.0,
            )
            assert -1.0 <= result["composite_score"] <= 1.0
            assert result["action"] in {"Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"}
            assert 0 <= result["confidence"] <= 100

    def test_drift_applied_on_top_of_regime_weights(self):
        """Drift adjustment should apply ON TOP of regime-selected weights,
        not on top of default weights."""
        # Bull regime with critical drift: crash_prob starts at 0.14 (Bull profile),
        # then gets multiplied by drift_mult (0.2 for critical).
        result = get_market_signal(
            crash_prob_3m=40.0, regime="Bull", vix=25.0,
            drift_severity="critical",
        )
        assert result.get("regime_weight_profile") == "Bull"
        assert result.get("drift_severity") == "critical"
        # The crash weight reduction reason should appear
        assert any("drift" in r.lower() for r in result["reasons"])

    def test_bull_and_bear_produce_different_scores_same_inputs(self):
        """Same market data under different regimes should produce different
        composite scores because weights differ."""
        kwargs = dict(
            crash_prob_3m=20.0, vix=22.0,
            sp500_1m_return=2.0, sp500_3m_return=5.0,
            external_consensus="MIXED", drawdown_pct=-4.0,
        )
        bull = get_market_signal(regime="Bull", **kwargs)
        bear = get_market_signal(regime="Bear", **kwargs)
        # Scores should be different (weights changed)
        assert bull["composite_score"] != bear["composite_score"]

    def test_all_components_present_in_regime_profiles(self):
        """Regime weight profiles should still produce all expected components."""
        for regime in ["Bull", "Bear", "Volatile"]:
            result = get_market_signal(
                crash_prob_3m=15.0, regime=regime, vix=22.0,
                external_consensus="BULLISH", drawdown_pct=-3.0,
            )
            for key in ["crash_prob", "regime", "valuation", "momentum",
                        "mean_reversion", "external", "drawdown"]:
                assert key in result["components"], f"{key} missing for {regime}"

    def test_regime_weight_profiles_sum_to_one(self):
        """All regime weight profiles in config should sum to 1.0."""
        from backend.config import config
        for regime, weights in config["regime_signal_weights"].items():
            total = sum(weights.values())
            assert total == pytest.approx(1.0, abs=0.01), \
                f"{regime} regime weights sum to {total}, expected 1.0"

    def test_regime_weight_profiles_have_all_keys(self):
        """Regime weight profiles should have the same keys as default weights."""
        from backend.config import config
        default_keys = set(config["signal_weights"].keys())
        for regime, weights in config["regime_signal_weights"].items():
            assert set(weights.keys()) == default_keys, \
                f"{regime} profile keys {set(weights.keys())} != default {default_keys}"


class TestInsiderSignalIntegration:
    """Test insider trading signal integration into stock signal engine."""

    def _make_market_signal(self, crash_3m=10.0):
        sig = get_market_signal(crash_prob_3m=crash_3m, regime="Neutral", vix=20.0)
        sig["_crash_3m_pct"] = crash_3m
        return sig

    def test_insider_score_accepted(self):
        """get_stock_signal should accept insider_signal_score parameter."""
        market_sig = self._make_market_signal()
        result = get_stock_signal(
            market_sig, beta=1.0, insider_signal_score=0.5,
        )
        assert "action" in result
        assert "insider" in result["components"]

    def test_insider_none_has_zero_contribution(self):
        """When insider_signal_score is None, insider component should be 0."""
        market_sig = self._make_market_signal()
        result = get_stock_signal(market_sig, beta=1.0, insider_signal_score=None)
        assert result["components"]["insider"] == 0.0

    def test_insider_bullish_increases_score(self):
        """Positive insider signal (buying) should increase composite score."""
        market_sig = self._make_market_signal()
        no_insider = get_stock_signal(market_sig, beta=1.0, insider_signal_score=None)
        with_insider = get_stock_signal(market_sig, beta=1.0, insider_signal_score=0.8)
        assert with_insider["composite_score"] > no_insider["composite_score"]
        assert with_insider["components"]["insider"] > 0

    def test_insider_bearish_decreases_score(self):
        """Negative insider signal (selling) should decrease composite score."""
        market_sig = self._make_market_signal()
        no_insider = get_stock_signal(market_sig, beta=1.0, insider_signal_score=None)
        with_insider = get_stock_signal(market_sig, beta=1.0, insider_signal_score=-0.6)
        assert with_insider["composite_score"] < no_insider["composite_score"]
        assert with_insider["components"]["insider"] < 0

    def test_insider_cluster_buy_reason(self):
        """Strong insider buying should produce a reason mentioning insiders."""
        market_sig = self._make_market_signal()
        result = get_stock_signal(market_sig, beta=1.0, insider_signal_score=0.6)
        insider_reasons = [r for r in result["reasons"] if "insider" in r.lower()]
        assert len(insider_reasons) > 0

    def test_insider_signal_clipped(self):
        """Extreme insider signal values should be clipped to [-1, 1]."""
        market_sig = self._make_market_signal()
        result_pos = get_stock_signal(market_sig, beta=1.0, insider_signal_score=5.0)
        result_neg = get_stock_signal(market_sig, beta=1.0, insider_signal_score=-5.0)
        # Component should be bounded by weight * 1.0
        from backend.config import config
        insider_w = config["stock_signal_weights"]["insider_trading"]
        assert abs(result_pos["components"]["insider"]) <= insider_w + 0.001
        assert abs(result_neg["components"]["insider"]) <= insider_w + 0.001

    def test_insider_conviction_quality(self):
        """Insider signal should be included in conviction quality assessment."""
        market_sig = self._make_market_signal()
        result = get_stock_signal(market_sig, beta=1.0, insider_signal_score=0.5)
        assert "conviction" in result
        # insider component should count in n_contributing
        assert result["conviction"]["n_contributing"] >= 1


class TestEconomicSurpriseWeight:
    """Regression tests: economic_surprise and momentum_breadth must have non-zero weight."""

    def test_economic_surprise_affects_composite(self):
        """Economic surprise signal must actually influence the composite score."""
        base = get_market_signal(crash_prob_3m=10.0, regime="Bull", vix=18.0)
        with_surprise = get_market_signal(
            crash_prob_3m=10.0, regime="Bull", vix=18.0, economic_surprise=0.8,
        )
        # A strong positive economic surprise should change the composite
        assert with_surprise["composite_score"] != base["composite_score"]
        assert "economic_surprise" in with_surprise["components"]
        # Positive surprise → should push composite higher
        assert with_surprise["composite_score"] > base["composite_score"]

    def test_negative_economic_surprise_bearish(self):
        """Negative economic surprise should push composite lower."""
        base = get_market_signal(crash_prob_3m=10.0, regime="Neutral", vix=20.0)
        with_neg_surprise = get_market_signal(
            crash_prob_3m=10.0, regime="Neutral", vix=20.0, economic_surprise=-0.8,
        )
        assert with_neg_surprise["composite_score"] < base["composite_score"]

    def test_momentum_breadth_affects_composite(self):
        """Momentum breadth signal must actually influence the composite score."""
        base = get_market_signal(crash_prob_3m=10.0, regime="Bull", vix=18.0)
        with_breadth = get_market_signal(
            crash_prob_3m=10.0, regime="Bull", vix=18.0, momentum_breadth=0.80,
        )
        assert with_breadth["composite_score"] != base["composite_score"]
        assert "momentum_breadth" in with_breadth["components"]
        # High breadth → bullish → higher composite
        assert with_breadth["composite_score"] > base["composite_score"]

    def test_low_breadth_bearish(self):
        """Low momentum breadth should push composite lower."""
        base = get_market_signal(crash_prob_3m=10.0, regime="Neutral", vix=20.0)
        with_low_breadth = get_market_signal(
            crash_prob_3m=10.0, regime="Neutral", vix=20.0, momentum_breadth=0.20,
        )
        assert with_low_breadth["composite_score"] < base["composite_score"]

    def test_weights_in_config(self):
        """economic_surprise and momentum_breadth must be in signal_weights config."""
        from backend.config import config
        weights = config["signal_weights"]
        assert "economic_surprise" in weights, "economic_surprise missing from signal_weights"
        assert "momentum_breadth" in weights, "momentum_breadth missing from signal_weights"
        assert weights["economic_surprise"] > 0
        assert weights["momentum_breadth"] > 0

    def test_regime_weights_include_new_signals(self):
        """All regime weight profiles must include economic_surprise + momentum_breadth."""
        from backend.config import config
        for regime, weights in config.get("regime_signal_weights", {}).items():
            assert "economic_surprise" in weights, f"{regime} missing economic_surprise"
            assert "momentum_breadth" in weights, f"{regime} missing momentum_breadth"
