"""
Tests for Relative Valuation & Peer Comparison Service
========================================================

Tests the percentile ranking, composite scoring, verdict logic,
and peer comparison mechanics without requiring network access.
"""

import pytest
from unittest.mock import patch, MagicMock

from backend.services.relative_valuation import (
    _compute_percentile,
    _interpret_vs_peers,
    _compute_composite_score,
    _compute_verdict,
    _find_sector_peers,
    get_valuation_summary,
)


class TestComputePercentile:
    """Test percentile computation logic."""

    def test_lowest_value(self):
        values = [10, 20, 30, 40, 50]
        pctile = _compute_percentile(10, values)
        assert pctile < 20

    def test_highest_value(self):
        values = [10, 20, 30, 40, 50]
        pctile = _compute_percentile(50, values)
        assert pctile > 80

    def test_median_value(self):
        values = [10, 20, 30, 40, 50]
        pctile = _compute_percentile(30, values)
        assert 40 <= pctile <= 60

    def test_single_value_returns_50(self):
        assert _compute_percentile(10, [10]) == 50.0

    def test_empty_list_returns_50(self):
        assert _compute_percentile(10, []) == 50.0

    def test_all_same_values(self):
        values = [20, 20, 20, 20]
        pctile = _compute_percentile(20, values)
        assert pctile == 50.0

    def test_below_all(self):
        values = [20, 30, 40, 50]
        pctile = _compute_percentile(5, values)
        assert pctile == 0.0

    def test_above_all(self):
        values = [20, 30, 40, 50]
        pctile = _compute_percentile(100, values)
        assert pctile == 100.0


class TestInterpretVsPeers:
    """Test human-readable interpretations."""

    def test_significantly_cheaper_pe(self):
        result = _interpret_vs_peers("pe_trailing", 10.0, 20.0)
        assert "cheaper" in result.lower()

    def test_premium_pe(self):
        result = _interpret_vs_peers("pe_trailing", 30.0, 20.0)
        assert "premium" in result.lower()

    def test_in_line_pe(self):
        result = _interpret_vs_peers("pe_trailing", 20.0, 20.5)
        assert result == "in line"

    def test_above_peers_growth(self):
        result = _interpret_vs_peers("revenue_growth", 0.30, 0.10)
        assert "above" in result.lower()

    def test_below_peers_growth(self):
        result = _interpret_vs_peers("revenue_growth", 0.05, 0.20)
        assert "below" in result.lower()

    def test_no_peer_avg_returns_na(self):
        result = _interpret_vs_peers("pe_trailing", 20.0, None)
        assert result == "N/A"

    def test_zero_peer_avg_returns_na(self):
        result = _interpret_vs_peers("pe_trailing", 20.0, 0)
        assert result == "N/A"


class TestCompositeScore:
    """Test the composite valuation score computation."""

    def test_all_cheap_scores_high(self):
        """When stock is cheaper than peers on all metrics, composite > 60."""
        rankings = {}
        for metric in ["pe_trailing", "pe_forward", "peg_ratio", "ev_ebitda",
                       "price_to_sales", "price_to_book", "dividend_yield",
                       "revenue_growth", "earnings_growth", "profit_margin"]:
            rankings[metric] = {
                "value": 10.0,
                "percentile": 20.0,
                "valuation_percentile": 80.0,  # cheap = high valuation percentile
                "peer_avg": 20.0,
                "peer_count": 5,
                "vs_peers": "cheaper",
            }
        score, components = _compute_composite_score(rankings)
        assert score >= 70

    def test_all_expensive_scores_low(self):
        """When stock is expensive on all metrics, composite < 40."""
        rankings = {}
        for metric in ["pe_trailing", "pe_forward", "peg_ratio", "ev_ebitda",
                       "price_to_sales", "price_to_book", "dividend_yield",
                       "revenue_growth", "earnings_growth", "profit_margin"]:
            rankings[metric] = {
                "value": 50.0,
                "percentile": 90.0,
                "valuation_percentile": 20.0,  # expensive = low valuation percentile
                "peer_avg": 20.0,
                "peer_count": 5,
                "vs_peers": "premium",
            }
        score, components = _compute_composite_score(rankings)
        assert score <= 30

    def test_mixed_scores_near_50(self):
        """Mixed metrics → composite near 50."""
        rankings = {}
        for i, metric in enumerate(["pe_trailing", "pe_forward", "peg_ratio",
                                     "ev_ebitda", "price_to_sales"]):
            rankings[metric] = {
                "value": 20.0,
                "percentile": 50.0,
                "valuation_percentile": 50.0,
                "peer_avg": 20.0,
                "peer_count": 5,
                "vs_peers": "in line",
            }
        score, components = _compute_composite_score(rankings)
        assert 40 <= score <= 60

    def test_insufficient_data_returns_50(self):
        """Too few metrics with data → default to 50."""
        rankings = {
            "pe_trailing": {"valuation_percentile": None},
        }
        score, _ = _compute_composite_score(rankings)
        assert score == 50.0

    def test_components_have_expected_structure(self):
        rankings = {
            "pe_trailing": {
                "value": 20.0,
                "percentile": 30.0,
                "valuation_percentile": 70.0,
                "peer_avg": 25.0,
            },
        }
        _, components = _compute_composite_score(rankings)
        if "pe_trailing" in components:
            assert "percentile" in components["pe_trailing"]
            assert "weight" in components["pe_trailing"]
            assert "contribution" in components["pe_trailing"]


class TestVerdict:
    """Test valuation verdict generation."""

    def test_deep_value(self):
        verdict = _compute_verdict(80.0, None)
        assert verdict["label"] == "Deep Value"
        assert verdict["color"] == "green"

    def test_undervalued(self):
        verdict = _compute_verdict(65.0, None)
        assert verdict["label"] == "Undervalued"
        assert verdict["color"] == "green"

    def test_fair_value(self):
        verdict = _compute_verdict(50.0, None)
        assert verdict["label"] == "Fair Value"
        assert verdict["color"] == "yellow"

    def test_overvalued(self):
        verdict = _compute_verdict(38.0, None)
        assert verdict["label"] == "Overvalued"
        assert verdict["color"] == "orange"

    def test_significantly_overvalued(self):
        verdict = _compute_verdict(20.0, None)
        assert verdict["label"] == "Significantly Overvalued"
        assert verdict["color"] == "red"

    def test_historical_note_expensive(self):
        historical = {"pe_percentile_vs_history": 90.0}
        verdict = _compute_verdict(50.0, historical)
        assert "historical_note" in verdict
        assert "expensive" in verdict["historical_note"].lower() or "high" in verdict["historical_note"].lower()

    def test_historical_note_cheap(self):
        historical = {"pe_percentile_vs_history": 10.0}
        verdict = _compute_verdict(50.0, historical)
        assert "historical_note" in verdict
        assert "cheap" in verdict["historical_note"].lower() or "low" in verdict["historical_note"].lower()


class TestFindSectorPeers:
    """Test sector peer lookup."""

    def test_finds_peers_for_known_ticker(self):
        peers = _find_sector_peers("AAPL", "Technology")
        assert len(peers) > 0
        assert "AAPL" not in peers

    def test_finds_peers_for_sector_name(self):
        # COIN is in Financials
        peers = _find_sector_peers("COIN", "Financial Services")
        assert len(peers) > 0

    def test_unknown_ticker_empty_peers(self):
        peers = _find_sector_peers("ZZZZZ", "Unknown Sector")
        assert peers == []

    def test_target_excluded_from_peers(self):
        peers = _find_sector_peers("MSFT", "Technology")
        assert "MSFT" not in peers


class TestValuationSummary:
    """Test the lightweight summary function used in stock analysis."""

    def test_summary_returns_none_when_no_data(self):
        """With a mocked empty result, summary returns None."""
        with patch("backend.services.relative_valuation.get_relative_valuation", return_value=None):
            result = get_valuation_summary("FAKE")
            assert result is None

    def test_summary_has_expected_keys(self):
        """Summary dict has the right structure."""
        mock_full = {
            "composite_score": 55.0,
            "verdict": {"label": "Fair Value", "color": "yellow"},
            "peer_count": 5,
            "sector": "Technology",
            "rankings": {
                "pe_trailing": {
                    "value": 25.0,
                    "percentile": 40.0,
                    "valuation_percentile": 60.0,
                    "peer_avg": 30.0,
                    "vs_peers": "cheaper",
                },
                "pe_forward": {
                    "value": 22.0,
                    "percentile": 35.0,
                    "valuation_percentile": 65.0,
                    "peer_avg": 28.0,
                    "vs_peers": "cheaper",
                },
            },
            "historical": {"pe_percentile_vs_history": 45.0},
        }
        with patch("backend.services.relative_valuation.get_relative_valuation", return_value=mock_full):
            result = get_valuation_summary("AAPL")
            assert result is not None
            assert "composite_score" in result
            assert "verdict" in result
            assert "verdict_color" in result
            assert "peer_count" in result
            assert "notable_metrics" in result
            assert result["composite_score"] == 55.0
            assert result["verdict"] == "Fair Value"

    def test_notable_metrics_sorted_by_extremity(self):
        """Notable metrics should be sorted by distance from 50th percentile."""
        mock_full = {
            "composite_score": 50.0,
            "verdict": {"label": "Fair Value", "color": "yellow"},
            "peer_count": 5,
            "sector": "Tech",
            "rankings": {
                "pe_trailing": {
                    "value": 10.0,
                    "percentile": 10.0,  # very extreme
                    "valuation_percentile": 90.0,
                    "peer_avg": 25.0,
                    "vs_peers": "significantly cheaper",
                },
                "price_to_sales": {
                    "value": 5.0,
                    "percentile": 45.0,  # near middle
                    "valuation_percentile": 55.0,
                    "peer_avg": 5.5,
                    "vs_peers": "cheaper",
                },
                "ev_ebitda": {
                    "value": 30.0,
                    "percentile": 85.0,  # fairly extreme
                    "valuation_percentile": 15.0,
                    "peer_avg": 20.0,
                    "vs_peers": "premium",
                },
            },
            "historical": None,
        }
        with patch("backend.services.relative_valuation.get_relative_valuation", return_value=mock_full):
            result = get_valuation_summary("TEST")
            metrics = result["notable_metrics"]
            # pe_trailing (pctile 10, distance 40) should come before ev_ebitda (pctile 85, distance 35)
            assert len(metrics) >= 2
            assert metrics[0]["metric"] == "pe_trailing"


class TestFetchTickerMetrics:
    """Test the metric extraction from yfinance data."""

    def test_fetch_returns_dict_structure(self):
        from backend.services.relative_valuation import _fetch_ticker_metrics

        mock_info = {
            "regularMarketPrice": 150.0,
            "trailingPE": 25.0,
            "forwardPE": 22.0,
            "pegRatio": 1.5,
            "enterpriseToEbitda": 18.0,
            "priceToSalesTrailing12Months": 6.0,
            "priceToBook": 35.0,
            "dividendYield": 0.006,
            "revenueGrowth": 0.08,
            "earningsGrowth": 0.15,
            "profitMargins": 0.25,
            "returnOnEquity": 0.40,
            "debtToEquity": 180.0,
            "freeCashflow": 100_000_000_000,
            "marketCap": 2_500_000_000_000,
            "shortName": "Apple Inc.",
            "sector": "Technology",
        }

        mock_ticker = MagicMock()
        mock_ticker.info = mock_info

        with patch("backend.services.relative_valuation.yf.Ticker", return_value=mock_ticker):
            result = _fetch_ticker_metrics("AAPL")

        assert result is not None
        assert result["ticker"] == "AAPL"
        assert result["pe_trailing"] == 25.0
        assert result["pe_forward"] == 22.0
        assert result["peg_ratio"] == 1.5
        assert result["ev_ebitda"] == 18.0
        assert result["price_to_sales"] == 6.0
        assert result["dividend_yield"] == 0.006
        assert result["fcf_yield"] == pytest.approx(0.04, abs=0.001)
        assert result["sector"] == "Technology"

    def test_fetch_handles_missing_fields(self):
        from backend.services.relative_valuation import _fetch_ticker_metrics

        mock_ticker = MagicMock()
        mock_ticker.info = {"regularMarketPrice": 100.0, "shortName": "Test"}

        with patch("backend.services.relative_valuation.yf.Ticker", return_value=mock_ticker):
            result = _fetch_ticker_metrics("TEST")

        assert result is not None
        assert result["pe_trailing"] is None
        assert result["fcf_yield"] is None

    def test_fetch_returns_none_on_failure(self):
        from backend.services.relative_valuation import _fetch_ticker_metrics

        with patch("backend.services.relative_valuation.yf.Ticker", side_effect=Exception("net error")):
            result = _fetch_ticker_metrics("FAIL")
        assert result is None

    def test_fetch_returns_none_when_no_price(self):
        from backend.services.relative_valuation import _fetch_ticker_metrics

        mock_ticker = MagicMock()
        mock_ticker.info = {"shortName": "Empty"}

        with patch("backend.services.relative_valuation.yf.Ticker", return_value=mock_ticker):
            result = _fetch_ticker_metrics("EMPTY")
        assert result is None


class TestGetRelativeValuation:
    """Integration-level tests for get_relative_valuation using mocks."""

    def _make_mock_metrics(self, ticker, pe=20, fwd_pe=18, sector="Technology"):
        return {
            "ticker": ticker,
            "name": f"{ticker} Inc.",
            "sector": sector,
            "pe_trailing": pe,
            "pe_forward": fwd_pe,
            "peg_ratio": 1.5,
            "ev_ebitda": pe * 0.8,
            "price_to_sales": 5.0,
            "price_to_book": 8.0,
            "dividend_yield": 0.005,
            "revenue_growth": 0.10,
            "earnings_growth": 0.15,
            "profit_margin": 0.20,
            "roe": 0.30,
            "debt_to_equity": 150.0,
            "fcf_yield": 0.04,
            "market_cap": 1e12,
        }

    def test_returns_full_structure(self):
        from backend.services.relative_valuation import get_relative_valuation

        target = self._make_mock_metrics("AAPL", pe=25)
        peers = [
            self._make_mock_metrics("MSFT", pe=30),
            self._make_mock_metrics("NVDA", pe=40),
            self._make_mock_metrics("AVGO", pe=15),
            self._make_mock_metrics("CRM", pe=35),
        ]

        def side_effect(ticker):
            if ticker == "AAPL":
                return target
            for p in peers:
                if p["ticker"] == ticker:
                    return p
            return None

        with patch("backend.services.relative_valuation._fetch_ticker_metrics", side_effect=side_effect), \
             patch("backend.services.relative_valuation._compute_historical_valuation", return_value=None):
            result = get_relative_valuation("AAPL")

        assert result is not None
        assert result["ticker"] == "AAPL"
        assert result["sector"] == "Technology"
        assert result["peer_count"] >= 3
        assert "rankings" in result
        assert "composite_score" in result
        assert "verdict" in result
        assert "peer_table" in result
        assert isinstance(result["composite_score"], float)
        assert 0 <= result["composite_score"] <= 100

    def test_cheap_stock_gets_high_score(self):
        """Stock with lowest P/E in group should score higher."""
        from backend.services.relative_valuation import get_relative_valuation

        target = self._make_mock_metrics("CHEAP", pe=10, fwd_pe=8)
        peers = [
            self._make_mock_metrics("EXP1", pe=30, fwd_pe=25),
            self._make_mock_metrics("EXP2", pe=40, fwd_pe=35),
            self._make_mock_metrics("EXP3", pe=50, fwd_pe=45),
        ]

        def side_effect(ticker):
            if ticker == "CHEAP":
                return target
            for p in peers:
                if p["ticker"] == ticker:
                    return p
            return None

        with patch("backend.services.relative_valuation._fetch_ticker_metrics", side_effect=side_effect), \
             patch("backend.services.relative_valuation._compute_historical_valuation", return_value=None), \
             patch("backend.services.relative_valuation._find_sector_peers", return_value=["EXP1", "EXP2", "EXP3"]):
            result = get_relative_valuation("CHEAP")

        assert result is not None
        assert result["composite_score"] >= 60  # Should be undervalued or better

    def test_expensive_stock_gets_low_score(self):
        """Stock with highest P/E in group should score lower."""
        from backend.services.relative_valuation import get_relative_valuation

        target = self._make_mock_metrics("EXPNS", pe=60, fwd_pe=55)
        peers = [
            self._make_mock_metrics("CHE1", pe=12, fwd_pe=10),
            self._make_mock_metrics("CHE2", pe=15, fwd_pe=12),
            self._make_mock_metrics("CHE3", pe=18, fwd_pe=15),
        ]

        def side_effect(ticker):
            if ticker == "EXPNS":
                return target
            for p in peers:
                if p["ticker"] == ticker:
                    return p
            return None

        with patch("backend.services.relative_valuation._fetch_ticker_metrics", side_effect=side_effect), \
             patch("backend.services.relative_valuation._compute_historical_valuation", return_value=None), \
             patch("backend.services.relative_valuation._find_sector_peers", return_value=["CHE1", "CHE2", "CHE3"]):
            result = get_relative_valuation("EXPNS")

        assert result is not None
        assert result["composite_score"] <= 40  # Should be overvalued

    def test_returns_none_for_unknown_ticker(self):
        from backend.services.relative_valuation import get_relative_valuation

        with patch("backend.services.relative_valuation._fetch_ticker_metrics", return_value=None):
            result = get_relative_valuation("FAKEFAKE")
        assert result is None

    def test_returns_none_with_too_few_peers(self):
        from backend.services.relative_valuation import get_relative_valuation

        target = self._make_mock_metrics("ALONE")

        def side_effect(ticker):
            if ticker == "ALONE":
                return target
            return None  # All peers fail

        with patch("backend.services.relative_valuation._fetch_ticker_metrics", side_effect=side_effect), \
             patch("backend.services.relative_valuation._find_sector_peers", return_value=["P1", "P2"]):
            result = get_relative_valuation("ALONE")
        assert result is None

    def test_peer_table_marks_target(self):
        """Peer table should mark the target stock."""
        from backend.services.relative_valuation import get_relative_valuation

        target = self._make_mock_metrics("TGT")
        peers = [
            self._make_mock_metrics("P1", pe=20),
            self._make_mock_metrics("P2", pe=25),
            self._make_mock_metrics("P3", pe=30),
        ]

        def side_effect(ticker):
            if ticker == "TGT":
                return target
            for p in peers:
                if p["ticker"] == ticker:
                    return p
            return None

        with patch("backend.services.relative_valuation._fetch_ticker_metrics", side_effect=side_effect), \
             patch("backend.services.relative_valuation._compute_historical_valuation", return_value=None), \
             patch("backend.services.relative_valuation._find_sector_peers", return_value=["P1", "P2", "P3"]):
            result = get_relative_valuation("TGT")

        assert result is not None
        target_rows = [r for r in result["peer_table"] if r["is_target"]]
        assert len(target_rows) == 1
        assert target_rows[0]["ticker"] == "TGT"
