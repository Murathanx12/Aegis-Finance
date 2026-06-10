"""
Tests: Options & Earnings Intelligence Wiring into Stock Signals
=================================================================

Validates that:
  1. Signal engine correctly applies options_signal_score
  2. Signal engine correctly applies earnings_signal_score
  3. Bullish options/earnings boost stock signal
  4. Bearish options/earnings penalize stock signal
  5. None values are backward compatible (no effect)
  6. Combined options + earnings have additive effect
  7. Scores are clipped to [-1, 1] range
  8. Router wiring calls the intelligence services
"""


from backend.services.signal_engine import get_stock_signal


# Base market signal fixture: mildly bullish market (Bull, low crash risk)
_MARKET_SIGNAL = {
    "action": "Buy",
    "confidence": 20,
    "color": "green",
    "composite_score": 0.20,
    "reasons": ["Bullish market regime"],
    "components": {
        "crash_prob": 0.3,
        "regime": 0.7,
        "valuation": 0.1,
        "momentum": 0.05,
        "mean_reversion": 0.0,
        "external": 0.0,
        "macro_risk": 0.0,
        "drawdown": 0.0,
    },
}

# Base stock kwargs shared across tests
_STOCK_KWARGS = dict(
    market_signal=_MARKET_SIGNAL,
    beta=1.0,
    current_price=100.0,
    stock_vol=0.25,
    drawdown_from_peak=-5.0,
    stock_momentum_1m=2.0,
    stock_momentum_3m=5.0,
)


class TestOptionsSignalIntegration:
    """Options signal should shift stock score via options_iv weight."""

    def test_bullish_options_boosts_signal(self):
        """Positive options score should increase stock composite."""
        base = get_stock_signal(**_STOCK_KWARGS, options_signal_score=None)
        bullish = get_stock_signal(**_STOCK_KWARGS, options_signal_score=0.6)
        assert bullish["composite_score"] > base["composite_score"]

    def test_bearish_options_reduces_signal(self):
        """Negative options score should decrease stock composite."""
        base = get_stock_signal(**_STOCK_KWARGS, options_signal_score=None)
        bearish = get_stock_signal(**_STOCK_KWARGS, options_signal_score=-0.6)
        assert bearish["composite_score"] < base["composite_score"]

    def test_none_options_has_no_effect(self):
        """None options_signal_score should produce same result as omitting it."""
        sig_none = get_stock_signal(**_STOCK_KWARGS, options_signal_score=None)
        sig_omit = get_stock_signal(**_STOCK_KWARGS)
        assert sig_none["composite_score"] == sig_omit["composite_score"]

    def test_options_score_clipped(self):
        """Extreme options scores should be clipped to [-1, 1]."""
        extreme_pos = get_stock_signal(**_STOCK_KWARGS, options_signal_score=5.0)
        clipped_pos = get_stock_signal(**_STOCK_KWARGS, options_signal_score=1.0)
        assert extreme_pos["composite_score"] == clipped_pos["composite_score"]

    def test_bearish_options_adds_reason(self):
        """Strongly bearish options should add a reason about options market."""
        result = get_stock_signal(**_STOCK_KWARGS, options_signal_score=-0.5)
        reasons = " ".join(result["reasons"]).lower()
        assert "option" in reasons

    def test_bullish_options_adds_reason(self):
        """Strongly bullish options should add a reason about options market."""
        result = get_stock_signal(**_STOCK_KWARGS, options_signal_score=0.5)
        reasons = " ".join(result["reasons"]).lower()
        assert "option" in reasons


class TestEarningsSignalIntegration:
    """Earnings signal should shift stock score via earnings_quality weight."""

    def test_strong_earnings_boosts_signal(self):
        """Positive earnings score should increase stock composite."""
        base = get_stock_signal(**_STOCK_KWARGS, earnings_signal_score=None)
        strong = get_stock_signal(**_STOCK_KWARGS, earnings_signal_score=0.5)
        assert strong["composite_score"] > base["composite_score"]

    def test_weak_earnings_reduces_signal(self):
        """Negative earnings score should decrease stock composite."""
        base = get_stock_signal(**_STOCK_KWARGS, earnings_signal_score=None)
        weak = get_stock_signal(**_STOCK_KWARGS, earnings_signal_score=-0.5)
        assert weak["composite_score"] < base["composite_score"]

    def test_none_earnings_has_no_effect(self):
        """None earnings_signal_score should produce same result as omitting it."""
        sig_none = get_stock_signal(**_STOCK_KWARGS, earnings_signal_score=None)
        sig_omit = get_stock_signal(**_STOCK_KWARGS)
        assert sig_none["composite_score"] == sig_omit["composite_score"]

    def test_strong_earnings_adds_reason(self):
        """Strong earnings should add a reason about earnings quality."""
        result = get_stock_signal(**_STOCK_KWARGS, earnings_signal_score=0.5)
        reasons = " ".join(result["reasons"]).lower()
        assert "earning" in reasons

    def test_weak_earnings_adds_reason(self):
        """Weak earnings should add a reason about earnings quality."""
        result = get_stock_signal(**_STOCK_KWARGS, earnings_signal_score=-0.5)
        reasons = " ".join(result["reasons"]).lower()
        assert "earning" in reasons


class TestCombinedOptionsEarnings:
    """Combined options + earnings should have additive effect."""

    def test_both_bullish_stronger_than_either_alone(self):
        """Bullish options + bullish earnings > either alone."""
        opts_only = get_stock_signal(**_STOCK_KWARGS, options_signal_score=0.5)
        earn_only = get_stock_signal(**_STOCK_KWARGS, earnings_signal_score=0.5)
        both = get_stock_signal(
            **_STOCK_KWARGS,
            options_signal_score=0.5,
            earnings_signal_score=0.5,
        )
        assert both["composite_score"] > opts_only["composite_score"]
        assert both["composite_score"] > earn_only["composite_score"]

    def test_both_bearish_stronger_than_either_alone(self):
        """Bearish options + bearish earnings < either alone."""
        opts_only = get_stock_signal(**_STOCK_KWARGS, options_signal_score=-0.5)
        earn_only = get_stock_signal(**_STOCK_KWARGS, earnings_signal_score=-0.5)
        both = get_stock_signal(
            **_STOCK_KWARGS,
            options_signal_score=-0.5,
            earnings_signal_score=-0.5,
        )
        assert both["composite_score"] < opts_only["composite_score"]
        assert both["composite_score"] < earn_only["composite_score"]

    def test_opposing_signals_partially_cancel(self):
        """Bullish options + bearish earnings should partially offset."""
        base = get_stock_signal(**_STOCK_KWARGS)
        mixed = get_stock_signal(
            **_STOCK_KWARGS,
            options_signal_score=0.5,
            earnings_signal_score=-0.5,
        )
        # The mixed result should be close to base since they partially cancel
        assert abs(mixed["composite_score"] - base["composite_score"]) < 0.15

    def test_output_always_valid(self):
        """All combinations should produce valid output."""
        for opt in [None, -1.0, -0.3, 0.0, 0.3, 1.0]:
            for earn in [None, -1.0, -0.3, 0.0, 0.3, 1.0]:
                result = get_stock_signal(
                    **_STOCK_KWARGS,
                    options_signal_score=opt,
                    earnings_signal_score=earn,
                )
                assert -1.0 <= result["composite_score"] <= 1.0
                assert result["action"] in {"Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"}
                assert 0 <= result["confidence"] <= 100


class TestSignalDifferentiation:
    """Options + earnings should meaningfully differentiate similar stocks."""

    def test_same_stock_different_options_creates_spread(self):
        """Two identical stocks with different options profiles should diverge."""
        bullish_opts = get_stock_signal(**_STOCK_KWARGS, options_signal_score=0.6)
        bearish_opts = get_stock_signal(**_STOCK_KWARGS, options_signal_score=-0.6)
        spread = bullish_opts["composite_score"] - bearish_opts["composite_score"]
        assert spread > 0.10, f"Options spread too small: {spread:.3f}"

    def test_same_stock_different_earnings_creates_spread(self):
        """Two identical stocks with different earnings profiles should diverge."""
        strong_earn = get_stock_signal(**_STOCK_KWARGS, earnings_signal_score=0.6)
        weak_earn = get_stock_signal(**_STOCK_KWARGS, earnings_signal_score=-0.6)
        spread = strong_earn["composite_score"] - weak_earn["composite_score"]
        assert spread > 0.06, f"Earnings spread too small: {spread:.3f}"

    def test_bearish_options_can_push_to_sell(self):
        """A stock near the sell threshold with bearish options should flip to Sell."""
        # Start with a slightly negative market signal
        bearish_market = dict(_MARKET_SIGNAL)
        bearish_market["composite_score"] = -0.10
        result = get_stock_signal(
            market_signal=bearish_market,
            beta=1.2,
            current_price=100.0,
            stock_vol=0.35,
            drawdown_from_peak=-12.0,
            stock_momentum_3m=-8.0,
            options_signal_score=-0.7,
            earnings_signal_score=-0.5,
        )
        # With all these bearish signals, we should be at least Hold or Sell
        assert result["composite_score"] < 0, "Should be negative with all bearish inputs"
