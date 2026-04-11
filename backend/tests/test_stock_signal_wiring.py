"""Tests that stock analysis endpoints include signal and crash fields.

Validates the wiring between stock_analyzer, signal_engine, and the
stock router — ensuring single-stock analysis returns the same signal
fields as the screener.
"""

import pytest
from unittest.mock import patch


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _make_market_signal(action="Hold", score=0.0, crash_pct=None):
    """Build a minimal market signal dict for mocking."""
    return {
        "action": action,
        "confidence": int(min(abs(score) * 100, 100)),
        "color": {"Buy": "green", "Sell": "red", "Strong Sell": "red"}.get(action, "amber"),
        "composite_score": score,
        "reasons": ["Test reason"],
        "components": {"crash_prob": 0.0, "regime": 0.0},
        "_crash_3m_pct": crash_pct,
    }


def _make_stock_result(ticker="TEST", sector="Technology", beta=1.0,
                       price=100.0, pe=20.0, analyst_target=None,
                       key_stats=None):
    """Build a minimal analyze_stock return dict for mocking."""
    return {
        "ticker": ticker,
        "name": f"{ticker} Corp",
        "sector": sector,
        "current_price": price,
        "beta": beta,
        "pe_ratio": pe,
        "analyst_target": analyst_target,
        "key_stats": key_stats,
    }


VALID_ACTIONS = {"Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"}


# ═══════════════════════════════════════════════════════════════════════════
# _analyze_stock signal wiring
# ═══════════════════════════════════════════════════════════════════════════


class TestAnalyzeStockSignalFields:
    """Verify _analyze_stock attaches signal + crash fields."""

    @patch("backend.routers.stock._compute_sector_momentum")
    @patch("backend.routers.stock._compute_market_signal")
    @patch("backend.services.stock_analyzer.analyze_stock")
    def test_signal_fields_attached(self, mock_analyze, mock_market, mock_momentum):
        """Single-stock analysis must include signal_action, signal_score, crash_prob_3m."""
        from backend.routers.stock import _analyze_stock

        mock_market.return_value = _make_market_signal(crash_pct=12.5)
        mock_momentum.return_value = {"Technology": 3.2}
        mock_analyze.return_value = _make_stock_result(
            "AAPL", beta=1.1, pe=28.0, analyst_target=280.0,
            key_stats={"pe_forward": 25.0},
        )

        result = _analyze_stock("AAPL")

        assert result is not None
        assert result["signal_action"] in VALID_ACTIONS
        assert isinstance(result["signal_confidence"], (int, float))
        assert isinstance(result["signal_score"], float)
        assert result["crash_prob_3m"] == 12.5
        assert result["market_signal"] == "Hold"

    @patch("backend.routers.stock._compute_sector_momentum")
    @patch("backend.routers.stock._compute_market_signal")
    @patch("backend.services.stock_analyzer.analyze_stock")
    def test_none_crash_prob_handled(self, mock_analyze, mock_market, mock_momentum):
        """Signal fields work when crash model is unavailable (crash_prob=None)."""
        from backend.routers.stock import _analyze_stock

        mock_market.return_value = _make_market_signal(crash_pct=None)
        mock_momentum.return_value = {}
        mock_analyze.return_value = _make_stock_result(pe=None, analyst_target=None)

        result = _analyze_stock("TEST")

        assert result is not None
        assert result["signal_action"] in VALID_ACTIONS
        assert result["crash_prob_3m"] is None

    @patch("backend.routers.stock._compute_sector_momentum")
    @patch("backend.routers.stock._compute_market_signal")
    @patch("backend.services.stock_analyzer.analyze_stock")
    def test_analyze_stock_returns_none(self, mock_analyze, mock_market, mock_momentum):
        """When analyze_stock returns None, _analyze_stock should also return None."""
        from backend.routers.stock import _analyze_stock

        mock_market.return_value = _make_market_signal()
        mock_analyze.return_value = None

        result = _analyze_stock("FAKE")
        assert result is None

    @patch("backend.routers.stock._compute_sector_momentum")
    @patch("backend.routers.stock._compute_market_signal")
    @patch("backend.services.stock_analyzer.analyze_stock")
    def test_signal_components_included(self, mock_analyze, mock_market, mock_momentum):
        """Signal components and reasons should be included for transparency."""
        from backend.routers.stock import _analyze_stock

        mock_market.return_value = _make_market_signal("Buy", 0.3, crash_pct=8.0)
        mock_momentum.return_value = {"Technology": 5.0}
        mock_analyze.return_value = _make_stock_result(
            "NVDA", beta=2.3, pe=55.0, analyst_target=220.0,
            key_stats={"pe_forward": 40.0},
        )

        result = _analyze_stock("NVDA")

        assert isinstance(result["signal_components"], dict)
        assert isinstance(result["signal_reasons"], list)


# ═══════════════════════════════════════════════════════════════════════════
# Edge cases: extreme / missing values flowing through _analyze_stock
# ═══════════════════════════════════════════════════════════════════════════


class TestAnalyzeStockEdgeCases:
    """Edge cases for the stock → signal wiring path."""

    @patch("backend.routers.stock._compute_sector_momentum")
    @patch("backend.routers.stock._compute_market_signal")
    @patch("backend.services.stock_analyzer.analyze_stock")
    def test_zero_beta_does_not_crash(self, mock_analyze, mock_market, mock_momentum):
        """Beta=0 should not divide-by-zero or produce NaN."""
        from backend.routers.stock import _analyze_stock

        mock_market.return_value = _make_market_signal(crash_pct=10.0)
        mock_momentum.return_value = {}
        mock_analyze.return_value = _make_stock_result(beta=0.0)

        result = _analyze_stock("ZB")

        assert result is not None
        assert result["signal_action"] in VALID_ACTIONS
        # score should be finite
        assert result["signal_score"] == result["signal_score"]  # NaN != NaN

    @patch("backend.routers.stock._compute_sector_momentum")
    @patch("backend.routers.stock._compute_market_signal")
    @patch("backend.services.stock_analyzer.analyze_stock")
    def test_extreme_beta_clamped(self, mock_analyze, mock_market, mock_momentum):
        """Extreme beta (10x) should produce signal within [-1, 1] range."""
        from backend.routers.stock import _analyze_stock

        mock_market.return_value = _make_market_signal("Sell", -0.4, crash_pct=50.0)
        mock_momentum.return_value = {}
        mock_analyze.return_value = _make_stock_result(beta=10.0)

        result = _analyze_stock("XBETA")

        assert -1.0 <= result["signal_score"] <= 1.0

    @patch("backend.routers.stock._compute_sector_momentum")
    @patch("backend.routers.stock._compute_market_signal")
    @patch("backend.services.stock_analyzer.analyze_stock")
    def test_negative_pe_ignored(self, mock_analyze, mock_market, mock_momentum):
        """Negative P/E (losses) should not trigger valuation penalty/reward."""
        from backend.routers.stock import _analyze_stock

        mock_market.return_value = _make_market_signal()
        mock_momentum.return_value = {}
        mock_analyze.return_value = _make_stock_result(pe=-15.0)

        result = _analyze_stock("LOSS")

        assert result is not None
        assert result["signal_action"] in VALID_ACTIONS

    @patch("backend.routers.stock._compute_sector_momentum")
    @patch("backend.routers.stock._compute_market_signal")
    @patch("backend.services.stock_analyzer.analyze_stock")
    def test_missing_key_stats_no_forward_pe(self, mock_analyze, mock_market, mock_momentum):
        """key_stats=None should skip forward PE without error."""
        from backend.routers.stock import _analyze_stock

        mock_market.return_value = _make_market_signal()
        mock_momentum.return_value = {}
        mock_analyze.return_value = _make_stock_result(key_stats=None)

        result = _analyze_stock("NOFWD")
        assert result is not None
        assert result["signal_action"] in VALID_ACTIONS

    @patch("backend.routers.stock._compute_sector_momentum")
    @patch("backend.routers.stock._compute_market_signal")
    @patch("backend.services.stock_analyzer.analyze_stock")
    def test_empty_key_stats_dict(self, mock_analyze, mock_market, mock_momentum):
        """key_stats={} (no pe_forward key) should skip forward PE."""
        from backend.routers.stock import _analyze_stock

        mock_market.return_value = _make_market_signal()
        mock_momentum.return_value = {}
        mock_analyze.return_value = _make_stock_result(key_stats={})

        result = _analyze_stock("EMPTY")
        assert result is not None
        assert result["signal_action"] in VALID_ACTIONS

    @patch("backend.routers.stock._compute_sector_momentum")
    @patch("backend.routers.stock._compute_market_signal")
    @patch("backend.services.stock_analyzer.analyze_stock")
    def test_unknown_sector_no_momentum(self, mock_analyze, mock_market, mock_momentum):
        """Unknown sector should get 0 momentum, not crash."""
        from backend.routers.stock import _analyze_stock

        mock_market.return_value = _make_market_signal()
        mock_momentum.return_value = {"Technology": 5.0}
        mock_analyze.return_value = _make_stock_result(sector="Alien Tech")

        result = _analyze_stock("ALIEN")
        assert result is not None
        assert result["signal_action"] in VALID_ACTIONS

    @patch("backend.routers.stock._compute_sector_momentum")
    @patch("backend.routers.stock._compute_market_signal")
    @patch("backend.services.stock_analyzer.analyze_stock")
    def test_zero_price_no_division_error(self, mock_analyze, mock_market, mock_momentum):
        """current_price=0 should not cause division by zero in analyst upside."""
        from backend.routers.stock import _analyze_stock

        mock_market.return_value = _make_market_signal()
        mock_momentum.return_value = {}
        mock_analyze.return_value = _make_stock_result(price=0.0, analyst_target=50.0)

        result = _analyze_stock("ZERO")
        assert result is not None
        assert result["signal_action"] in VALID_ACTIONS

    @patch("backend.routers.stock._compute_sector_momentum")
    @patch("backend.routers.stock._compute_market_signal")
    @patch("backend.services.stock_analyzer.analyze_stock")
    def test_crash_prob_flows_to_mc(self, mock_analyze, mock_market, mock_momentum):
        """crash_3m_pct should be divided by 100 before passing to analyze_stock."""
        from backend.routers.stock import _analyze_stock

        mock_market.return_value = _make_market_signal(crash_pct=25.0)
        mock_momentum.return_value = {}
        mock_analyze.return_value = _make_stock_result()

        _analyze_stock("MC")

        # analyze_stock called with ml_crash_prob = 25.0/100 = 0.25
        call_kwargs = mock_analyze.call_args
        assert call_kwargs[1]["ml_crash_prob"] == pytest.approx(0.25)


# ═══════════════════════════════════════════════════════════════════════════
# _stock_signal refactored function
# ═══════════════════════════════════════════════════════════════════════════


class TestStockSignalEndpoint:
    """Verify _stock_signal reuses _compute_market_signal correctly."""

    @patch("backend.routers.stock._compute_sector_momentum")
    @patch("backend.routers.stock._compute_market_signal")
    @patch("backend.services.stock_analyzer.analyze_stock")
    def test_returns_required_keys(self, mock_analyze, mock_market, mock_momentum):
        from backend.routers.stock import _stock_signal

        mock_market.return_value = _make_market_signal(crash_pct=10.0)
        mock_momentum.return_value = {}
        mock_analyze.return_value = _make_stock_result("AAPL")

        result = _stock_signal("AAPL")

        assert result["ticker"] == "AAPL"
        assert result["action"] in VALID_ACTIONS
        assert "confidence" in result
        assert "composite_score" in result
        assert result["market_action"] == "Hold"

    @patch("backend.routers.stock._compute_sector_momentum")
    @patch("backend.routers.stock._compute_market_signal")
    @patch("backend.services.stock_analyzer.analyze_stock")
    def test_stock_none_returns_fallback(self, mock_analyze, mock_market, mock_momentum):
        """When analyze_stock returns None, signal endpoint returns Hold fallback."""
        from backend.routers.stock import _stock_signal

        mock_market.return_value = _make_market_signal()
        mock_analyze.return_value = None

        result = _stock_signal("BAD")

        assert result["ticker"] == "BAD"
        assert result["action"] == "Hold"
        assert result["confidence"] == 0
        assert "error" in result

    @patch("backend.routers.stock._compute_sector_momentum")
    @patch("backend.routers.stock._compute_market_signal")
    @patch("backend.services.stock_analyzer.analyze_stock")
    def test_bearish_market_propagates(self, mock_analyze, mock_market, mock_momentum):
        """Strong sell market signal should produce bearish stock signal."""
        from backend.routers.stock import _stock_signal

        mock_market.return_value = _make_market_signal("Strong Sell", -0.6, crash_pct=60.0)
        mock_momentum.return_value = {}
        mock_analyze.return_value = _make_stock_result(beta=1.5)

        result = _stock_signal("BEAR")

        assert result["composite_score"] < 0
        assert result["action"] in {"Hold", "Sell", "Strong Sell"}


# ═══════════════════════════════════════════════════════════════════════════
# Sentiment analyzer consistency & edge cases
# ═══════════════════════════════════════════════════════════════════════════


class TestSentimentAnalyzerConsistency:
    """Verify sentiment analyzer always returns a dict, never None."""

    def test_no_titles_returns_dict(self):
        """When news items have no 'title' field, should return dict not None."""
        from backend.services.sentiment_analyzer import analyze_sentiment

        with patch("backend.services.news_intelligence.fetch_stock_news") as mock_news:
            mock_news.return_value = [
                {"url": "https://example.com", "source": "Test"},
                {"url": "https://example.com/2", "description": "No title here"},
            ]
            result = analyze_sentiment("AAPL")

        assert result is not None
        assert isinstance(result, dict)
        assert result["sentiment"] == "neutral"
        assert result["headline_count"] == 0
        assert result["method"] == "none"

    def test_no_news_returns_dict(self):
        """When no news at all, should return dict not None."""
        from backend.services.sentiment_analyzer import analyze_sentiment

        with patch("backend.services.news_intelligence.fetch_stock_news") as mock_news:
            mock_news.return_value = []
            result = analyze_sentiment("AAPL")

        assert result is not None
        assert isinstance(result, dict)
        assert result["sentiment"] == "neutral"

    def test_none_news_returns_dict(self):
        """When fetch_stock_news returns None, should return dict."""
        from backend.services.sentiment_analyzer import analyze_sentiment

        with patch("backend.services.news_intelligence.fetch_stock_news") as mock_news:
            mock_news.return_value = None
            result = analyze_sentiment("AAPL")

        assert result is not None
        assert result["sentiment"] == "neutral"
        assert result["ticker"] == "AAPL"


class TestSentimentKeywordScoring:
    """Verify keyword fallback produces correct sentiment labels."""

    def test_bullish_headlines(self):
        """Headlines with strong positive keywords → bullish."""
        from backend.services.sentiment_analyzer import _score_with_keywords

        headlines = [
            "Stock beats earnings surge profits record high",
            "Company gains growth upgrade rally",
        ]
        scores = _score_with_keywords(headlines)
        assert len(scores) == 2
        assert all(s["numeric"] > 0 for s in scores)

    def test_bearish_headlines(self):
        """Headlines with strong negative keywords → bearish."""
        from backend.services.sentiment_analyzer import _score_with_keywords

        headlines = [
            "Crash losses recession layoff bankruptcy",
            "Stock drop decline slump plunge",
        ]
        scores = _score_with_keywords(headlines)
        assert len(scores) == 2
        assert all(s["numeric"] < 0 for s in scores)

    def test_neutral_headline(self):
        """Headlines with no sentiment keywords → neutral."""
        from backend.services.sentiment_analyzer import _score_with_keywords

        scores = _score_with_keywords(["The company released quarterly report today"])
        assert len(scores) == 1
        assert scores[0]["numeric"] == 0.0
        assert scores[0]["label"] == "neutral"

    def test_empty_headlines_list(self):
        """Empty list should return empty list, not crash."""
        from backend.services.sentiment_analyzer import _score_with_keywords

        assert _score_with_keywords([]) == []

    def test_mixed_sentiment_headline(self):
        """Equal positive and negative keywords → neutral."""
        from backend.services.sentiment_analyzer import _score_with_keywords

        scores = _score_with_keywords(["Stock gains despite crash fears"])
        # "gains" = positive, "crash" = negative → balanced → neutral
        assert len(scores) == 1
        assert scores[0]["label"] == "neutral"


class TestSentimentConfigThresholds:
    """Verify sentiment thresholds are read from config."""

    def test_thresholds_exist_in_config(self):
        """Config must have sentiment section with all threshold keys."""
        from backend.config import config
        sent = config["sentiment"]
        assert "bullish_threshold" in sent
        assert "slightly_bullish_threshold" in sent
        assert "bearish_threshold" in sent
        assert "slightly_bearish_threshold" in sent

    def test_threshold_ordering(self):
        """Thresholds must be ordered: bearish < sl_bearish < sl_bullish < bullish."""
        from backend.config import config
        sent = config["sentiment"]
        assert sent["bearish_threshold"] < sent["slightly_bearish_threshold"]
        assert sent["slightly_bearish_threshold"] < sent["slightly_bullish_threshold"]
        assert sent["slightly_bullish_threshold"] < sent["bullish_threshold"]

    def test_sentiment_labels_from_config(self):
        """analyze_sentiment should use config thresholds for label mapping."""
        from backend.services.sentiment_analyzer import analyze_sentiment

        with patch("backend.services.news_intelligence.fetch_stock_news") as mock_news:
            # All strongly positive headlines
            mock_news.return_value = [
                {"title": "Stock surge rally gains profit record boom"},
                {"title": "Massive beat upgrade outperform bullish soar"},
            ]
            # Patch FinBERT to unavailable so keyword fallback is used
            with patch("backend.services.sentiment_analyzer._get_finbert", return_value=None):
                result = analyze_sentiment("BULL")

        assert result["sentiment"] in ("bullish", "slightly_bullish")
        assert result["score"] > 0
        assert result["method"] == "keyword"


# ═══════════════════════════════════════════════════════════════════════════
# Screener consistency: stock signal fields match _analyze_stock fields
# ═══════════════════════════════════════════════════════════════════════════


class TestScreenerSignalConsistency:
    """Verify the screener and single-stock endpoint produce compatible signals."""

    def test_signal_engine_returns_all_expected_keys(self):
        """get_stock_signal must return action, confidence, composite_score."""
        from backend.services.signal_engine import get_stock_signal, get_market_signal

        market = get_market_signal()
        result = get_stock_signal(market_signal=market, beta=1.0)

        assert "action" in result
        assert "confidence" in result
        assert "composite_score" in result
        assert result["action"] in VALID_ACTIONS
        assert 0 <= result["confidence"] <= 100
        assert -1.0 <= result["composite_score"] <= 1.0

    def test_extreme_bullish_inputs(self):
        """All bullish inputs → Buy or Strong Buy signal."""
        from backend.services.signal_engine import get_stock_signal, get_market_signal

        market = get_market_signal(
            crash_prob_3m=2.0, regime="Bull",
            sp500_1m_return=5.0, sp500_3m_return=12.0,
            vix=14.0, external_consensus="BULLISH",
        )
        result = get_stock_signal(
            market_signal=market, beta=0.8,
            analyst_target=150.0, current_price=100.0,
            sector_momentum=15.0, pe_ratio=12.0,
        )

        assert result["action"] in {"Buy", "Strong Buy"}
        assert result["composite_score"] > 0.1

    def test_extreme_bearish_inputs(self):
        """All bearish inputs → Sell or Strong Sell signal."""
        from backend.services.signal_engine import get_stock_signal, get_market_signal

        market = get_market_signal(
            crash_prob_3m=70.0, regime="Bear",
            sp500_1m_return=-8.0, sp500_3m_return=-15.0,
            vix=40.0, external_consensus="BEARISH",
        )
        result = get_stock_signal(
            market_signal=market, beta=2.0,
            analyst_target=80.0, current_price=120.0,
            sector_momentum=-12.0, pe_ratio=60.0,
        )

        assert result["action"] in {"Sell", "Strong Sell"}
        assert result["composite_score"] < -0.1
