"""
Tests for signal_analytics.py — consensus, decomposition, risk-reward, ranking, concentration.
"""

import pytest
import numpy as np

from backend.services.signal_analytics import (
    compute_signal_consensus,
    compute_conviction_decomposition,
    compute_risk_reward,
    rank_screener_signals,
    detect_sector_concentration,
    enrich_screener_signals,
)


# ── compute_signal_consensus ─────────────────────────────────────────────


class TestSignalConsensus:
    """Test consensus scoring for signal components."""

    def test_all_bullish_components(self):
        """All components positive → strong consensus."""
        components = {
            "crash_prob": 0.4,
            "regime": 0.7,
            "valuation": 0.3,
            "momentum": 0.2,
        }
        result = compute_signal_consensus(components)
        assert result["agreement_ratio"] == 1.0
        assert result["n_bullish"] == 4
        assert result["n_bearish"] == 0
        assert result["consensus_label"] == "strong"

    def test_all_bearish_components(self):
        """All components negative → strong consensus."""
        components = {
            "crash_prob": -0.5,
            "regime": -0.6,
            "valuation": -0.3,
            "momentum": -0.2,
        }
        result = compute_signal_consensus(components)
        assert result["agreement_ratio"] == 1.0
        assert result["n_bearish"] == 4
        assert result["consensus_label"] == "strong"

    def test_mixed_components_conflicted(self):
        """Half bullish, half bearish → conflicted."""
        components = {
            "crash_prob": 0.8,
            "regime": 0.7,
            "valuation": -0.6,
            "momentum": -0.9,
        }
        result = compute_signal_consensus(components)
        assert result["n_bullish"] == 2
        assert result["n_bearish"] == 2
        assert result["consensus_label"] in ("weak", "conflicted")

    def test_mostly_bullish_moderate_consensus(self):
        """Most bullish with one bearish → moderate consensus."""
        components = {
            "crash_prob": 0.3,
            "regime": 0.5,
            "valuation": 0.2,
            "momentum": 0.4,
            "external": -0.1,
        }
        result = compute_signal_consensus(components)
        assert result["agreement_ratio"] >= 0.65
        assert result["consensus_label"] in ("strong", "moderate")

    def test_empty_components(self):
        """Empty components dict → no_data label."""
        result = compute_signal_consensus({})
        assert result["consensus_label"] == "no_data"
        assert result["agreement_ratio"] == 0.0

    def test_all_neutral_components(self):
        """All near-zero components → perfect agreement on nothing."""
        components = {"a": 0.01, "b": -0.01, "c": 0.0}
        result = compute_signal_consensus(components)
        assert result["n_neutral"] == 3
        assert result["agreement_ratio"] == 1.0

    def test_dispersion_high_for_conflicting(self):
        """Conflicting signals should have high dispersion."""
        conflicting = {"a": 0.9, "b": -0.8, "c": 0.7, "d": -0.6}
        unanimous = {"a": 0.3, "b": 0.35, "c": 0.25, "d": 0.3}

        r_conflict = compute_signal_consensus(conflicting)
        r_unanimous = compute_signal_consensus(unanimous)
        assert r_conflict["dispersion"] > r_unanimous["dispersion"]

    def test_single_component(self):
        """Single component → trivially strong consensus."""
        result = compute_signal_consensus({"crash_prob": 0.5})
        assert result["agreement_ratio"] == 1.0
        assert result["n_bullish"] == 1


# ── compute_conviction_decomposition ─────────────────────────────────────


class TestConvictionDecomposition:
    """Test per-component contribution breakdown."""

    def test_basic_decomposition(self):
        """Components decompose into weighted contributions."""
        components = {"crash_prob": 0.4, "regime": 0.7, "valuation": 0.1}
        weights = {"crash_prob": 0.20, "regime": 0.16, "valuation": 0.11}

        result = compute_conviction_decomposition(components, weights)
        assert len(result) == 3
        # Sorted by absolute contribution descending
        assert abs(result[0]["contribution"]) >= abs(result[1]["contribution"])
        # All have contribution_pct
        total_pct = sum(r["contribution_pct"] for r in result)
        assert abs(total_pct - 100.0) < 1.0

    def test_contributions_sum_to_composite(self):
        """Sum of contributions should approximately equal composite score."""
        components = {
            "crash_prob": 0.3,
            "regime": 0.5,
            "valuation": -0.2,
            "momentum": 0.1,
        }
        weights = {"crash_prob": 0.20, "regime": 0.16, "valuation": 0.11, "momentum": 0.12}

        result = compute_conviction_decomposition(components, weights)
        total_contribution = sum(r["contribution"] for r in result)

        # Manual calculation
        total_w = sum(weights.values())
        expected = sum(components[k] * weights[k] / total_w for k in components)
        assert abs(total_contribution - expected) < 0.001

    def test_direction_labels(self):
        """Components should be labeled bullish/bearish/neutral."""
        components = {"a": 0.5, "b": -0.3, "c": 0.01}
        result = compute_conviction_decomposition(components, {"a": 0.5, "b": 0.3, "c": 0.2})
        directions = {r["name"]: r["direction"] for r in result}
        assert directions["a"] == "bullish"
        assert directions["b"] == "bearish"
        assert directions["c"] == "neutral"

    def test_empty_components(self):
        """Empty components → empty decomposition."""
        assert compute_conviction_decomposition({}) == []

    def test_uses_default_config_weights(self):
        """When weights=None, uses config signal_weights."""
        components = {"crash_prob": 0.3, "regime": 0.5}
        result = compute_conviction_decomposition(components)
        assert len(result) == 2
        # Should use config weights (crash_prob=0.20, regime=0.16)
        for r in result:
            assert r["weight"] > 0

    def test_zero_weight_component(self):
        """Component with zero weight contributes nothing."""
        components = {"a": 0.9, "b": 0.5}
        weights = {"a": 0.5, "b": 0.0}
        result = compute_conviction_decomposition(components, weights)
        b_entry = next(r for r in result if r["name"] == "b")
        assert b_entry["contribution"] == 0.0


# ── compute_risk_reward ──────────────────────────────────────────────────


class TestRiskReward:
    """Test risk-reward ratio computation."""

    def test_favorable_risk_reward(self):
        """High upside, small downside → favorable."""
        stock = {"mc_p90_5y": 120.0, "mc_p10_5y": -15.0, "mc_median_5y": 50.0}
        result = compute_risk_reward(stock)
        assert result["available"] is True
        assert result["risk_reward_ratio"] == 8.0  # 120/15
        assert result["asymmetry"] == "highly_favorable"

    def test_unfavorable_risk_reward(self):
        """Small upside, big downside → unfavorable."""
        stock = {"mc_p90_5y": 20.0, "mc_p10_5y": -50.0, "mc_median_5y": -10.0}
        result = compute_risk_reward(stock)
        assert result["available"] is True
        assert result["risk_reward_ratio"] == 0.4  # 20/50
        assert result["asymmetry"] == "unfavorable"

    def test_balanced_risk_reward(self):
        """Symmetric upside/downside → balanced."""
        stock = {"mc_p90_5y": 40.0, "mc_p10_5y": -35.0, "mc_median_5y": 5.0}
        result = compute_risk_reward(stock)
        assert result["available"] is True
        assert 0.8 <= result["risk_reward_ratio"] <= 1.5
        assert result["asymmetry"] in ("balanced", "favorable")

    def test_missing_mc_data(self):
        """No MC data → unavailable."""
        result = compute_risk_reward({"ticker": "XYZ"})
        assert result["available"] is False

    def test_alternative_key_format(self):
        """Works with mc_p90_5y_return format too."""
        stock = {"mc_p90_5y_return": 100.0, "mc_p10_5y_return": -20.0, "mc_median_5y_return": 40.0}
        result = compute_risk_reward(stock)
        assert result["available"] is True
        assert result["risk_reward_ratio"] == 5.0

    def test_ratio_capped_at_10(self):
        """Extreme ratios are capped at 10."""
        stock = {"mc_p90_5y": 200.0, "mc_p10_5y": -0.5}
        result = compute_risk_reward(stock)
        assert result["risk_reward_ratio"] <= 10.0

    def test_both_positive(self):
        """When downside is also positive (rare), handle gracefully."""
        stock = {"mc_p90_5y": 150.0, "mc_p10_5y": 5.0, "mc_median_5y": 70.0}
        result = compute_risk_reward(stock)
        assert result["available"] is True
        # Downside is positive, so abs_downside = 0.01 (floor), ratio = capped
        assert result["risk_reward_ratio"] == 10.0


# ── rank_screener_signals ────────────────────────────────────────────────


class TestRankSignals:
    """Test relative signal ranking."""

    def test_basic_ranking(self):
        """Stocks ranked by signal_score, highest = rank 1."""
        stocks = [
            {"ticker": "A", "signal_score": 0.1},
            {"ticker": "B", "signal_score": 0.5},
            {"ticker": "C", "signal_score": -0.2},
            {"ticker": "D", "signal_score": 0.3},
        ]
        result = rank_screener_signals(stocks)
        ranks = {s["ticker"]: s["signal_rank"] for s in result}
        assert ranks["B"] == 1
        assert ranks["D"] == 2
        assert ranks["A"] == 3
        assert ranks["C"] == 4

    def test_percentile_distribution(self):
        """Top stock gets 100th percentile, bottom gets 0th."""
        stocks = [{"ticker": f"S{i}", "signal_score": i * 0.1} for i in range(10)]
        result = rank_screener_signals(stocks)
        best = next(s for s in result if s["signal_rank"] == 1)
        worst = next(s for s in result if s["signal_rank"] == 10)
        assert best["signal_percentile"] == 100.0
        assert worst["signal_percentile"] == 0.0

    def test_tier_assignment(self):
        """Percentile maps to correct tier."""
        stocks = [{"ticker": f"S{i}", "signal_score": i * 0.1} for i in range(20)]
        result = rank_screener_signals(stocks)
        tiers = {s["signal_rank"]: s["signal_tier"] for s in result}
        assert tiers[1] == "top_quartile"
        assert tiers[20] == "bottom_quartile"

    def test_empty_list(self):
        """Empty list returns empty."""
        assert rank_screener_signals([]) == []

    def test_single_stock(self):
        """Single stock gets rank 1, 50th percentile."""
        stocks = [{"ticker": "A", "signal_score": 0.3}]
        result = rank_screener_signals(stocks)
        assert result[0]["signal_rank"] == 1
        assert result[0]["signal_percentile"] == 50.0

    def test_original_order_preserved(self):
        """Original list order is preserved (ranking is added in-place)."""
        stocks = [
            {"ticker": "A", "signal_score": 0.1},
            {"ticker": "B", "signal_score": 0.5},
        ]
        result = rank_screener_signals(stocks)
        assert result[0]["ticker"] == "A"
        assert result[1]["ticker"] == "B"


# ── detect_sector_concentration ──────────────────────────────────────────


class TestSectorConcentration:
    """Test sector concentration detection."""

    def test_concentrated_sector(self):
        """All top picks in one sector → warning."""
        stocks = [
            {"ticker": "AAPL", "sector": "Technology", "signal_rank": 1},
            {"ticker": "MSFT", "sector": "Technology", "signal_rank": 2},
            {"ticker": "NVDA", "sector": "Technology", "signal_rank": 3},
            {"ticker": "GOOG", "sector": "Technology", "signal_rank": 4},
            {"ticker": "JNJ", "sector": "Healthcare", "signal_rank": 5},
        ]
        result = detect_sector_concentration(stocks)
        assert result["concentrated"] is True
        assert result["dominant_sector"] == "Technology"
        assert result["dominant_pct"] == 80.0
        assert "warning" in result

    def test_diversified_picks(self):
        """Top picks spread across sectors → no warning."""
        stocks = [
            {"ticker": "AAPL", "sector": "Technology", "signal_rank": 1},
            {"ticker": "JNJ", "sector": "Healthcare", "signal_rank": 2},
            {"ticker": "JPM", "sector": "Financials", "signal_rank": 3},
            {"ticker": "XOM", "sector": "Energy", "signal_rank": 4},
            {"ticker": "PG", "sector": "Consumer Staples", "signal_rank": 5},
        ]
        result = detect_sector_concentration(stocks)
        assert result["concentrated"] is False
        assert result["n_sectors_in_top"] == 5

    def test_empty_stocks(self):
        """Empty list → no concentration."""
        result = detect_sector_concentration([])
        assert result["concentrated"] is False

    def test_custom_top_n(self):
        """Concentration checked on custom top_n."""
        stocks = [
            {"ticker": "A", "sector": "Tech", "signal_rank": 1},
            {"ticker": "B", "sector": "Tech", "signal_rank": 2},
            {"ticker": "C", "sector": "Health", "signal_rank": 3},
        ]
        result = detect_sector_concentration(stocks, top_n=2)
        assert result["concentrated"] is True  # 100% Tech in top 2
        assert result["top_n"] == 2


# ── enrich_screener_signals (integration) ────────────────────────────────


class TestEnrichScreenerSignals:
    """Test the main enrichment pipeline."""

    def _make_stocks(self, n: int = 5) -> list[dict]:
        """Helper to create mock stock dicts."""
        sectors = ["Technology", "Healthcare", "Financials", "Energy", "Consumer"]
        return [
            {
                "ticker": f"STOCK{i}",
                "sector": sectors[i % len(sectors)],
                "signal_score": 0.1 * (i - n // 2),
                "signal_action": "Buy" if i > n // 2 else "Hold",
                "mc_p90_5y": 80 + i * 10,
                "mc_p10_5y": -20 + i * 3,
                "mc_median_5y": 30 + i * 5,
                "sharpe": 0.5 + i * 0.1,
            }
            for i in range(n)
        ]

    def _make_market_signal(self) -> dict:
        return {
            "action": "Buy",
            "confidence": 25,
            "composite_score": 0.25,
            "components": {
                "crash_prob": 0.3,
                "regime": 0.5,
                "valuation": 0.1,
                "momentum": -0.05,
                "mean_reversion": 0.0,
                "external": 0.2,
                "macro_risk": -0.1,
                "drawdown": 0.15,
            },
        }

    def test_enrichment_adds_ranking(self):
        """All stocks get rank and percentile."""
        stocks = self._make_stocks(10)
        result = enrich_screener_signals(stocks)
        for s in result["stocks"]:
            assert "signal_rank" in s
            assert "signal_percentile" in s
            assert "signal_tier" in s

    def test_enrichment_adds_risk_reward(self):
        """All stocks get risk_reward dict."""
        stocks = self._make_stocks(5)
        result = enrich_screener_signals(stocks)
        for s in result["stocks"]:
            assert "risk_reward" in s
            assert "available" in s["risk_reward"]

    def test_enrichment_has_analytics(self):
        """Result includes aggregate analytics."""
        stocks = self._make_stocks(10)
        market = self._make_market_signal()
        result = enrich_screener_signals(stocks, market)
        analytics = result["analytics"]
        assert "n_stocks" in analytics
        assert analytics["n_stocks"] == 10
        assert "score_mean" in analytics
        assert "score_std" in analytics
        assert "action_distribution" in analytics
        assert "concentration" in analytics

    def test_enrichment_has_market_consensus(self):
        """Market signal consensus is included when market_signal provided."""
        stocks = self._make_stocks(3)
        market = self._make_market_signal()
        result = enrich_screener_signals(stocks, market)
        assert "market_consensus" in result["analytics"]
        assert "market_decomposition" in result["analytics"]

    def test_enrichment_no_market_signal(self):
        """Works without market signal (no consensus/decomposition)."""
        stocks = self._make_stocks(3)
        result = enrich_screener_signals(stocks, market_signal=None)
        assert "market_consensus" not in result["analytics"]

    def test_empty_stocks(self):
        """Empty stocks → empty result."""
        result = enrich_screener_signals([])
        assert result["stocks"] == []
        assert result["analytics"]["n_stocks"] == 0

    def test_stocks_without_mc_data(self):
        """Stocks missing MC data get unavailable risk_reward."""
        stocks = [{"ticker": "X", "signal_score": 0.1, "signal_action": "Hold", "sector": "Tech"}]
        result = enrich_screener_signals(stocks)
        assert result["stocks"][0]["risk_reward"]["available"] is False

    def test_concentration_detection_in_enrichment(self):
        """Concentration warning appears in analytics."""
        stocks = [
            {"ticker": f"T{i}", "sector": "Technology", "signal_score": 0.5 - i * 0.05,
             "signal_action": "Buy"}
            for i in range(5)
        ]
        result = enrich_screener_signals(stocks)
        assert result["analytics"]["concentration"]["concentrated"] is True

    def test_score_statistics_correct(self):
        """Score statistics match input data."""
        stocks = self._make_stocks(5)
        result = enrich_screener_signals(stocks)
        scores = [s["signal_score"] for s in stocks]
        analytics = result["analytics"]
        assert abs(analytics["score_mean"] - float(np.mean(scores))) < 0.01
        assert abs(analytics["score_std"] - float(np.std(scores))) < 0.01
        assert analytics["score_min"] == round(min(scores), 3)
        assert analytics["score_max"] == round(max(scores), 3)
