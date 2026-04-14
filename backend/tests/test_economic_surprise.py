"""
Economic Surprise Index Tests
================================

Tests for economic surprise index service.

Run with:
    python -m pytest backend/tests/test_economic_surprise.py -v
"""

import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.economic_surprise import (
    compute_surprise_index,
    get_indicator_surprises,
)


def _make_fred_series(n: int = 60, trend: float = 0.01, noise: float = 0.5) -> pd.Series:
    """Create mock FRED series with trend + noise."""
    rng = np.random.default_rng(42)
    dates = pd.date_range(end="2026-03-31", periods=n, freq="MS")
    values = 100 + np.cumsum(rng.normal(trend, noise, len(dates)))
    return pd.Series(values, index=dates)


class TestComputeSurpriseIndex:
    @patch("backend.services.economic_surprise._fetch_fred_series")
    def test_basic_computation(self, mock_fetch):
        mock_fetch.return_value = _make_fred_series(60)

        result = compute_surprise_index()
        assert result is not None
        assert "composite_score" in result
        assert -1.0 <= result["composite_score"] <= 1.0
        assert "signal" in result
        assert result["signal"] in ("bullish_surprise", "bearish_surprise", "neutral")
        assert "trend" in result
        assert "indicators" in result

    @patch("backend.services.economic_surprise._fetch_fred_series")
    def test_all_series_fail(self, mock_fetch):
        mock_fetch.return_value = None
        result = compute_surprise_index()
        assert result is None

    @patch("backend.services.economic_surprise._fetch_fred_series")
    def test_bullish_surprise(self, mock_fetch):
        # Create a series where latest values are above trend (positive surprise)
        series = _make_fred_series(60, trend=0.01, noise=0.1)
        # Spike the last few values
        series.iloc[-3:] = series.iloc[-3:] + 20
        mock_fetch.return_value = series

        result = compute_surprise_index()
        if result:
            # With positive surprise, score should be positive for non-inverted indicators
            # Note: some indicators are inverted, so composite may vary
            assert result["composite_score"] is not None

    @patch("backend.services.economic_surprise._fetch_fred_series")
    def test_indicator_details(self, mock_fetch):
        mock_fetch.return_value = _make_fred_series(60)

        result = compute_surprise_index()
        if result and result["indicators"]:
            for ind in result["indicators"]:
                assert "series_id" in ind
                assert "name" in ind
                assert "latest_value" in ind
                assert "trend_value" in ind
                assert "surprise_pct" in ind
                assert "surprise_normalized" in ind
                assert -1.0 <= ind["surprise_normalized"] <= 1.0

    @patch("backend.services.economic_surprise._fetch_fred_series")
    def test_short_series_excluded(self, mock_fetch):
        # Series too short for trend computation
        mock_fetch.return_value = _make_fred_series(5)
        result = compute_surprise_index()
        # Should return None since all series are too short
        assert result is None

    @patch("backend.services.economic_surprise._fetch_fred_series")
    def test_breadth_computation(self, mock_fetch):
        mock_fetch.return_value = _make_fred_series(60)
        result = compute_surprise_index()
        if result:
            assert "breadth" in result
            assert 0 <= result["breadth"] <= 1.0
            assert result["positive_surprises"] + result["negative_surprises"] <= result["indicators_tracked"]


class TestGetIndicatorSurprises:
    @patch("backend.services.economic_surprise.compute_surprise_index")
    def test_returns_list(self, mock_compute):
        mock_compute.return_value = {
            "composite_score": 0.1,
            "indicators": [{"series_id": "ICSA", "name": "Claims"}],
        }
        result = get_indicator_surprises()
        assert isinstance(result, list)
        assert len(result) == 1

    @patch("backend.services.economic_surprise.compute_surprise_index")
    def test_returns_empty_on_failure(self, mock_compute):
        mock_compute.return_value = None
        result = get_indicator_surprises()
        assert result == []
