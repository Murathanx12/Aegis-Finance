"""Tests for short interest / squeeze signal."""

from unittest.mock import patch

import pytest

from backend.services import short_interest as si


def test_classify_short_regime_branches():
    assert si._classify_short_regime(None, None) == "unknown"
    assert si._classify_short_regime(0.02, None) == "low"
    assert si._classify_short_regime(0.07, 3.0) == "moderate"
    assert si._classify_short_regime(0.15, 4.0) == "high"
    assert si._classify_short_regime(0.25, 7.0) == "extreme"
    # High float% but trivial days-to-cover should not be "extreme"
    assert si._classify_short_regime(0.25, 1.0) == "high"


def test_squeeze_score_weighting():
    score = si._squeeze_score(short_pct_float=0.30, days_to_cover=10.0, momentum_3m=0.30)
    assert score == pytest.approx(100.0)
    score_low = si._squeeze_score(short_pct_float=0.0, days_to_cover=0.0, momentum_3m=0.0)
    assert score_low == 0.0


def test_squeeze_score_returns_none_when_no_inputs():
    assert si._squeeze_score(None, None, None) is None


def test_squeeze_score_partial_inputs():
    # Only short % available
    score = si._squeeze_score(short_pct_float=0.15, days_to_cover=None, momentum_3m=None)
    assert score is not None
    assert 0 < score < 100


def test_get_short_interest_end_to_end_with_mock():
    fake_info = {
        "shares_short": 50_000_000,
        "shares_short_prior_month": 40_000_000,
        "short_ratio": 6.5,
        "short_percent_float": 0.18,
        "short_percent_outstanding": 0.15,
        "float_shares": 300_000_000,
        "shares_outstanding": 350_000_000,
        "avg_volume": 10_000_000,
        "last_price": 50.0,
        "name": "MOCK Inc",
    }
    with patch.object(si, "_pull_yf_info", return_value=fake_info), \
         patch.object(si, "_momentum_3m", return_value=0.25):
        result = si.get_short_interest("MOCK")

    assert result is not None
    assert result["ticker"] == "MOCK"
    assert result["month_over_month_change_pct"] == 25.0
    assert result["regime"] == "high"
    assert 0 <= result["squeeze_score_0_100"] <= 100


def test_get_short_interest_returns_none_when_info_missing():
    with patch.object(si, "_pull_yf_info", return_value=None):
        assert si.get_short_interest("GHOST") is None
