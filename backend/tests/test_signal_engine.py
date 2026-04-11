"""Tests for the composite signal engine."""

import pytest

from backend.services.signal_engine import get_market_signal, get_stock_signal


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
        result = get_market_signal(crash_prob_3m=20.0, external_consensus="BULLISH")
        components = result["components"]
        for key in ["crash_prob", "regime", "valuation", "momentum", "mean_reversion", "external"]:
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
