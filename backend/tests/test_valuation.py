"""Tests for market valuation metrics (unit tests)."""

import pytest

from backend.services.valuation import _percentile_rank, _CAPE_HISTORY


class TestPercentileRank:
    def test_low_value(self):
        result = _percentile_rank(5, _CAPE_HISTORY)
        assert result is not None
        assert result <= 10

    def test_median_value(self):
        result = _percentile_rank(20, _CAPE_HISTORY)
        assert result is not None
        assert 40 <= result <= 70

    def test_high_value(self):
        result = _percentile_rank(40, _CAPE_HISTORY)
        assert result is not None
        assert result >= 85

    def test_extreme_value(self):
        result = _percentile_rank(50, _CAPE_HISTORY)
        assert result == 100  # above all historical values

    def test_none_value(self):
        result = _percentile_rank(None, _CAPE_HISTORY)
        assert result is None

    def test_empty_history(self):
        result = _percentile_rank(20, [])
        assert result is None
