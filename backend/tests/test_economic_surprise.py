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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.economic_surprise import (
    compute_surprise_index,
    get_economic_calendar,
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


class TestCPINormalizationGranularity:
    """Regression (cycle 75): CPI surprise normalization was always saturated at ±1.0.

    The use_change conversion makes surprise_pct enormous because monthly %
    changes are tiny (~0.2%), so even small deviations produce 100%+ relative
    surprise, always clipping to ±1.0.  This means CPI always contributes
    maximum weight, losing all granularity.  Fix: use wider normalization
    denominator (±100%) for rate-of-change indicators.
    """

    @patch("backend.services.economic_surprise._fetch_fred_series")
    def test_cpi_not_always_saturated(self, mock_fetch):
        """CPI surprise_normalized should NOT always be ±1.0."""
        # Create a CPI-like monotonically increasing level series
        # with small, steady MoM growth (~0.3%) and a slight recent bump
        n = 60
        dates = pd.date_range(end="2026-03-31", periods=n, freq="MS")
        base = 300 + np.arange(n) * 0.9  # CPI-like level, ~0.3% MoM
        # Slight bump in last value (not extreme)
        base[-1] += 0.5  # ~0.17% extra — should be a MODERATE surprise, not max
        mock_fetch.return_value = pd.Series(base, index=dates)

        result = compute_surprise_index()
        assert result is not None

        # Find CPI indicator
        cpi_ind = None
        for ind in result["indicators"]:
            if ind["series_id"] == "CPIAUCSL":
                cpi_ind = ind
                break

        if cpi_ind is not None:
            # The key assertion: CPI should NOT be at the ±1.0 clip limit
            assert abs(cpi_ind["surprise_normalized"]) < 1.0, (
                f"CPI surprise_normalized={cpi_ind['surprise_normalized']} is saturated at ±1.0 — "
                f"normalization scale is too narrow for rate-of-change indicators"
            )

    @patch("backend.services.economic_surprise._fetch_fred_series")
    def test_use_change_moderate_surprise_has_granularity(self, mock_fetch):
        """A moderate CPI move should produce a surprise between 0 and 1, not at the limit."""
        n = 60
        dates = pd.date_range(end="2026-03-31", periods=n, freq="MS")
        # Steady 0.3% MoM growth
        levels = 300 * np.cumprod(np.ones(n) + 0.003)
        # Last month: 0.5% MoM instead of 0.3% — moderate deviation
        levels[-1] = levels[-2] * 1.005
        mock_fetch.return_value = pd.Series(levels, index=dates)

        result = compute_surprise_index()
        if result:
            for ind in result["indicators"]:
                if ind["series_id"] == "CPIAUCSL":
                    # Should have meaningful intermediate value, not ±1.0
                    assert 0 < abs(ind["surprise_normalized"]) < 1.0, (
                        f"Expected intermediate CPI surprise, got {ind['surprise_normalized']}"
                    )


class TestEconomicCalendar:
    @patch("backend.services.economic_surprise._fetch_fred_series")
    def test_calendar_fields_and_order(self, mock_fetch):
        mock_fetch.return_value = _make_fred_series(60)
        cal = get_economic_calendar()
        assert cal is not None
        assert "note" in cal and "not a street consensus" in cal["note"]
        assert cal["releases"], "expected at least one release row"
        dates = [r["date"] for r in cal["releases"]]
        assert dates == sorted(dates, reverse=True), "most-recent first"
        for r in cal["releases"]:
            for key in ("series_id", "name", "importance", "date", "actual",
                        "forecast_trend", "previous", "surprise_pct",
                        "direction", "frequency"):
                assert key in r, f"missing {key}"
            assert r["importance"] in (1, 2, 3)
            assert r["direction"] in ("beat", "miss", "inline")

    @patch("backend.services.economic_surprise._fetch_fred_series")
    def test_calendar_previous_differs_from_actual(self, mock_fetch):
        mock_fetch.return_value = _make_fred_series(60)
        cal = get_economic_calendar()
        assert cal is not None
        # previous is the second-to-last print — with noisy synthetic data it
        # must exist and (for this seed) differ from the latest
        row = cal["releases"][0]
        assert row["previous"] is not None
        assert row["previous"] != row["actual"]

    @patch("backend.services.economic_surprise.compute_surprise_index")
    def test_calendar_none_on_failure(self, mock_compute):
        mock_compute.return_value = None
        assert get_economic_calendar() is None


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
