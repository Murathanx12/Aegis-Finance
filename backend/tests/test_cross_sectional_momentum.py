"""
Cross-Sectional Momentum Tests
=================================

Tests for relative strength ranking service.

Run with:
    python -m pytest backend/tests/test_cross_sectional_momentum.py -v
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.cross_sectional_momentum import (
    compute_momentum_rankings,
    get_momentum_score,
)


def _make_mock_download(tickers, n_days=280):
    """Create mock yfinance download data."""
    dates = pd.bdate_range(end="2026-03-31", periods=n_days)
    rng = np.random.default_rng(42)

    data = {}
    for i, ticker in enumerate(tickers):
        # Give different stocks different drift (for differentiation)
        drift = 0.0005 * (i - len(tickers) // 2)
        returns = rng.normal(drift, 0.02, n_days)
        prices = 100 * np.cumprod(1 + returns)
        data[ticker] = prices

    prices_df = pd.DataFrame(data, index=dates)
    # Create MultiIndex columns like yfinance returns
    cols = pd.MultiIndex.from_product([["Close"], tickers])
    multi_df = pd.DataFrame(prices_df.values, index=dates, columns=cols)
    return multi_df


class TestMomentumRankings:
    @patch("yfinance.download")
    def test_basic_rankings(self, mock_yf):
        tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
        mock_yf.return_value = _make_mock_download(tickers)

        result = compute_momentum_rankings(tickers=tickers, include_sector_relative=False)

        assert result is not None
        assert "rankings" in result
        assert "summary" in result
        assert len(result["rankings"]) == 5

    @patch("yfinance.download")
    def test_ranking_order(self, mock_yf):
        tickers = ["A", "B", "C"]
        mock_yf.download.return_value = _make_mock_download(tickers)

        result = compute_momentum_rankings(tickers=tickers, include_sector_relative=False)
        if result and result["rankings"]:
            scores = [r["composite_score"] for r in result["rankings"]]
            # Should be sorted descending
            assert scores == sorted(scores, reverse=True)

    @patch("yfinance.download")
    def test_percentile_range(self, mock_yf):
        tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
        mock_yf.download.return_value = _make_mock_download(tickers)

        result = compute_momentum_rankings(tickers=tickers, include_sector_relative=False)
        if result:
            for r in result["rankings"]:
                assert 0 <= r["percentile"] <= 100
                assert 1 <= r["quintile"] <= 5
                assert 1 <= r["rank"] <= len(result["rankings"])

    @patch("yfinance.download")
    def test_returns_present(self, mock_yf):
        tickers = ["AAPL", "MSFT"]
        mock_yf.download.return_value = _make_mock_download(tickers)

        result = compute_momentum_rankings(tickers=tickers, include_sector_relative=False)
        if result:
            for r in result["rankings"]:
                assert "returns" in r
                assert "1M" in r["returns"]
                assert "3M" in r["returns"]

    @patch("yfinance.download")
    def test_summary_stats(self, mock_yf):
        tickers = ["AAPL", "MSFT", "GOOGL"]
        mock_yf.download.return_value = _make_mock_download(tickers)

        result = compute_momentum_rankings(tickers=tickers, include_sector_relative=False)
        if result:
            summary = result["summary"]
            assert "total_stocks" in summary
            assert "avg_momentum" in summary
            assert "breadth_positive" in summary
            assert "top_5" in summary
            assert "bottom_5" in summary

    @patch("yfinance.download")
    def test_empty_download(self, mock_yf):
        mock_yf.download.return_value = pd.DataFrame()
        result = compute_momentum_rankings(tickers=["FAKE"])
        assert result is None


class TestGetMomentumScore:
    def test_from_precomputed(self):
        rankings = {
            "rankings": [
                {"ticker": "AAPL", "composite_score": 5.0, "rank": 1},
                {"ticker": "MSFT", "composite_score": 3.0, "rank": 2},
            ],
            "summary": {},
        }
        result = get_momentum_score("AAPL", rankings=rankings)
        assert result is not None
        assert result["ticker"] == "AAPL"
        assert result["composite_score"] == 5.0

    def test_ticker_not_found(self):
        rankings = {"rankings": [{"ticker": "MSFT"}], "summary": {}}
        result = get_momentum_score("AAPL", rankings=rankings)
        assert result is None

    def test_none_rankings(self):
        with patch("backend.services.cross_sectional_momentum.compute_momentum_rankings", return_value=None):
            result = get_momentum_score("AAPL")
            assert result is None


class TestPercentileQuintileDistribution:
    """Regression tests for percentile/quintile calculation (cycle_054 fix)."""

    @patch("yfinance.download")
    def test_top_stock_percentile_is_100(self, mock_yf):
        """Top-ranked stock should have percentile = 100."""
        tickers = ["A", "B", "C", "D", "E"]
        mock_yf.return_value = _make_mock_download(tickers, n_days=280)
        result = compute_momentum_rankings(tickers=tickers, include_sector_relative=False)
        if result and len(result["rankings"]) >= 2:
            assert result["rankings"][0]["percentile"] == 100.0

    @patch("yfinance.download")
    def test_bottom_stock_percentile_is_0(self, mock_yf):
        """Bottom-ranked stock should have percentile = 0."""
        tickers = ["A", "B", "C", "D", "E"]
        mock_yf.return_value = _make_mock_download(tickers, n_days=280)
        result = compute_momentum_rankings(tickers=tickers, include_sector_relative=False)
        if result and len(result["rankings"]) >= 2:
            assert result["rankings"][-1]["percentile"] == 0.0

    @patch("yfinance.download")
    def test_quintile_distribution_even(self, mock_yf):
        """Quintiles should distribute roughly evenly across 1-5."""
        tickers = [f"T{i:02d}" for i in range(20)]
        mock_yf.return_value = _make_mock_download(tickers, n_days=280)
        result = compute_momentum_rankings(tickers=tickers, include_sector_relative=False)
        if result:
            quintiles = [r["quintile"] for r in result["rankings"]]
            # Each quintile should have at least 1 stock with 20 stocks total
            for q in range(1, 6):
                assert q in quintiles, f"Quintile {q} missing from distribution"

    @patch("yfinance.download")
    def test_quintile_5_is_best(self, mock_yf):
        """Top-ranked stock should be in quintile 5."""
        tickers = ["A", "B", "C", "D", "E"]
        mock_yf.return_value = _make_mock_download(tickers, n_days=280)
        result = compute_momentum_rankings(tickers=tickers, include_sector_relative=False)
        if result and result["rankings"]:
            assert result["rankings"][0]["quintile"] == 5

    @patch("yfinance.download")
    def test_quintile_1_is_worst(self, mock_yf):
        """Bottom-ranked stock should be in quintile 1."""
        tickers = ["A", "B", "C", "D", "E"]
        mock_yf.return_value = _make_mock_download(tickers, n_days=280)
        result = compute_momentum_rankings(tickers=tickers, include_sector_relative=False)
        if result and result["rankings"]:
            assert result["rankings"][-1]["quintile"] == 1
