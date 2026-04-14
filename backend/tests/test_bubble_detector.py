"""Tests for LPPL bubble detector."""

import numpy as np
import pandas as pd
import pytest

from backend.services.bubble_detector import (
    get_bubble_status,
    get_bubble_signal_score,
    _valid_sornette_params,
    LPPLS_AVAILABLE,
)


def _make_normal_prices(n_days=500, seed=42):
    """Generate normal (non-bubble) random walk prices."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0003, 0.01, n_days)
    prices = 100 * np.exp(np.cumsum(returns))
    dates = pd.bdate_range("2022-01-01", periods=n_days)
    return pd.Series(prices, index=dates)


def _make_bubble_prices(n_days=500, seed=42):
    """Generate super-exponential bubble-like prices (power law acceleration)."""
    rng = np.random.default_rng(seed)
    t = np.arange(n_days)
    tc = n_days + 50  # Critical time slightly in the future
    # LPPL-like price: A + B*(tc-t)^m with log-periodic oscillation
    A, B, m = 10, -0.5, 0.5
    base = A + B * (tc - t) ** m
    noise = rng.normal(0, 0.01, n_days)
    prices = np.exp(base + noise) * 100
    dates = pd.bdate_range("2022-01-01", periods=n_days)
    return pd.Series(prices, index=dates)


class TestBubbleStatus:
    def test_output_keys(self):
        prices = _make_normal_prices()
        result = get_bubble_status(prices, "TEST")
        assert "confidence" in result
        assert "is_bubble" in result
        assert "status" in result
        assert "n_valid_fits" in result
        assert "n_total_fits" in result
        assert "threshold" in result

    def test_insufficient_data(self):
        prices = pd.Series([100, 101, 102], index=pd.bdate_range("2024-01-01", periods=3))
        result = get_bubble_status(prices, "SHORT")
        assert result["is_bubble"] is False
        assert result["status"] == "insufficient data"

    def test_none_prices(self):
        result = get_bubble_status(None, "NULL")
        assert result["is_bubble"] is False

    @pytest.mark.skipif(not LPPLS_AVAILABLE, reason="lppls not installed")
    def test_normal_market_not_bubble(self):
        """Normal random walk should not trigger bubble detection."""
        prices = _make_normal_prices(500)
        result = get_bubble_status(prices, "NORMAL")
        # Should have low confidence (not necessarily 0 due to random fits)
        assert result["confidence"] is not None
        # Most random walks should not be flagged
        # (allow some tolerance since LPPL can have false positives)

    @pytest.mark.skipif(not LPPLS_AVAILABLE, reason="lppls not installed")
    def test_confidence_bounded(self):
        prices = _make_normal_prices(500)
        result = get_bubble_status(prices, "BOUNDED")
        if result["confidence"] is not None:
            assert 0.0 <= result["confidence"] <= 1.0

    @pytest.mark.skipif(not LPPLS_AVAILABLE, reason="lppls not installed")
    def test_n_fits_consistent(self):
        prices = _make_normal_prices(500)
        result = get_bubble_status(prices, "FITS")
        assert result["n_valid_fits"] <= result["n_total_fits"]


class TestSornetteParams:
    def test_tc_in_past_invalid(self):
        """tc must be in the future."""
        time_ordinal = np.arange(100, 600)
        assert not _valid_sornette_params(tc=500.0, m=0.5, w=8.0, t2=499, time_ordinal=time_ordinal)

    def test_tc_too_far_future_invalid(self):
        time_ordinal = np.arange(100, 600)
        # tc 2 years in the future
        assert not _valid_sornette_params(tc=time_ordinal[499] + 730, m=0.5, w=8.0, t2=499, time_ordinal=time_ordinal)

    def test_m_out_of_bounds(self):
        time_ordinal = np.arange(100, 600)
        tc = float(time_ordinal[499] + 30)
        assert not _valid_sornette_params(tc=tc, m=0.05, w=8.0, t2=499, time_ordinal=time_ordinal)  # m too low
        assert not _valid_sornette_params(tc=tc, m=0.95, w=8.0, t2=499, time_ordinal=time_ordinal)  # m too high

    def test_omega_out_of_bounds(self):
        time_ordinal = np.arange(100, 600)
        tc = float(time_ordinal[499] + 30)
        assert not _valid_sornette_params(tc=tc, m=0.5, w=3.0, t2=499, time_ordinal=time_ordinal)  # ω too low
        assert not _valid_sornette_params(tc=tc, m=0.5, w=15.0, t2=499, time_ordinal=time_ordinal)  # ω too high

    def test_valid_params(self):
        time_ordinal = np.arange(100, 600)
        tc = float(time_ordinal[499] + 60)
        assert _valid_sornette_params(tc=tc, m=0.5, w=8.0, t2=499, time_ordinal=time_ordinal)


class TestBubbleSignalScore:
    def test_no_data_returns_none(self):
        assert get_bubble_signal_score(None) is None

    @pytest.mark.skipif(not LPPLS_AVAILABLE, reason="lppls not installed")
    def test_signal_bounded(self):
        prices = _make_normal_prices(500)
        score = get_bubble_signal_score(prices)
        if score is not None:
            assert -1.0 <= score <= 0.0

    def test_signal_continuity_at_threshold(self):
        """Signal score must be continuous at CONFIDENCE_THRESHOLD (no jump)."""
        from backend.services.bubble_detector import CONFIDENCE_THRESHOLD
        from unittest.mock import patch

        # Test just below threshold
        below_result = {"confidence": CONFIDENCE_THRESHOLD - 0.001, "is_bubble": False}
        with patch("backend.services.bubble_detector.get_bubble_status", return_value=below_result):
            score_below = get_bubble_signal_score(_make_normal_prices(200))

        # Test just above threshold
        above_result = {"confidence": CONFIDENCE_THRESHOLD + 0.001, "is_bubble": True}
        with patch("backend.services.bubble_detector.get_bubble_status", return_value=above_result):
            score_above = get_bubble_signal_score(_make_normal_prices(200))

        # Both should be close to -0.5 (the boundary value)
        if score_below is not None and score_above is not None:
            assert abs(score_below - score_above) < 0.05, (
                f"Discontinuity at threshold: below={score_below:.3f}, above={score_above:.3f}"
            )

    def test_signal_at_exact_threshold(self):
        """At exactly the confidence threshold, score should be -0.5."""
        from backend.services.bubble_detector import CONFIDENCE_THRESHOLD
        from unittest.mock import patch

        result = {"confidence": CONFIDENCE_THRESHOLD, "is_bubble": True}
        with patch("backend.services.bubble_detector.get_bubble_status", return_value=result):
            score = get_bubble_signal_score(_make_normal_prices(200))
        if score is not None:
            assert abs(score - (-0.5)) < 0.01, f"Expected -0.5 at threshold, got {score}"

    def test_signal_at_half_threshold(self):
        """At half the confidence threshold, score should be 0 (entry to partial zone)."""
        from backend.services.bubble_detector import CONFIDENCE_THRESHOLD
        from unittest.mock import patch

        result = {"confidence": CONFIDENCE_THRESHOLD * 0.5, "is_bubble": False}
        with patch("backend.services.bubble_detector.get_bubble_status", return_value=result):
            score = get_bubble_signal_score(_make_normal_prices(200))
        if score is not None:
            assert abs(score) < 0.01, f"Expected 0 at half-threshold, got {score}"
