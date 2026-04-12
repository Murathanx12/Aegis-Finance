"""
Tests for Earnings Intelligence Service
==========================================

Tests the earnings signal computation, surprise tracking, and growth metrics.
"""

import numpy as np
import pytest


class TestEarningsSignalGeneration:
    """Test the earnings signal generation logic."""

    def test_strong_beat_rate_is_bullish(self):
        """87.5%+ beat rate → bullish signal."""
        from backend.services.earnings_intelligence import _generate_earnings_signal

        data = {
            "beat_rate": 100.0,
            "avg_surprise_pct": 12.0,
            "surprise_trend": "improving",
            "revenue_yoy_growth": 25.0,
            "earnings_yoy_growth": 30.0,
        }
        signal = _generate_earnings_signal(data)
        assert signal["score"] > 0.3
        assert signal["sentiment"] in ("bullish",)

    def test_poor_beat_rate_is_bearish(self):
        """<37.5% beat rate → bearish signal."""
        from backend.services.earnings_intelligence import _generate_earnings_signal

        data = {
            "beat_rate": 25.0,
            "avg_surprise_pct": -8.0,
            "surprise_trend": "declining",
            "revenue_yoy_growth": -10.0,
        }
        signal = _generate_earnings_signal(data)
        assert signal["score"] < -0.2
        assert signal["sentiment"] in ("bearish", "slightly_bearish")

    def test_empty_data_returns_neutral(self):
        """No earnings data → neutral score."""
        from backend.services.earnings_intelligence import _generate_earnings_signal

        signal = _generate_earnings_signal({})
        assert signal["score"] == 0.0
        assert signal["sentiment"] == "neutral"
        assert signal["n_signals"] == 0

    def test_signal_score_bounds(self):
        """Signal score stays within [-1, 1]."""
        from backend.services.earnings_intelligence import _generate_earnings_signal

        # Max bullish
        data = {
            "beat_rate": 100,
            "avg_surprise_pct": 30,
            "surprise_trend": "improving",
            "revenue_yoy_growth": 50,
            "earnings_yoy_growth": 50,
        }
        signal = _generate_earnings_signal(data)
        assert -1.0 <= signal["score"] <= 1.0

        # Max bearish
        data2 = {
            "beat_rate": 0,
            "avg_surprise_pct": -20,
            "surprise_trend": "declining",
            "revenue_yoy_growth": -30,
            "earnings_yoy_growth": -30,
        }
        signal2 = _generate_earnings_signal(data2)
        assert -1.0 <= signal2["score"] <= 1.0

    def test_earnings_imminent_flag(self):
        """Earnings within 14 days adds a reason but doesn't change score."""
        from backend.services.earnings_intelligence import _generate_earnings_signal

        data = {
            "earnings_imminent": True,
            "days_until_earnings": 3,
        }
        signal = _generate_earnings_signal(data)
        assert any("Earnings in" in r for r in signal["reasons"])

    def test_moderate_metrics_are_slightly_bullish(self):
        """Good but not exceptional metrics → slightly bullish."""
        from backend.services.earnings_intelligence import _generate_earnings_signal

        data = {
            "beat_rate": 75.0,
            "avg_surprise_pct": 5.0,
            "revenue_yoy_growth": 8.0,
        }
        signal = _generate_earnings_signal(data)
        assert signal["score"] > 0
        assert signal["sentiment"] in ("slightly_bullish", "bullish")

    def test_confidence_scales_with_signals(self):
        """More data points → higher confidence."""
        from backend.services.earnings_intelligence import _generate_earnings_signal

        few = _generate_earnings_signal({"beat_rate": 75})
        many = _generate_earnings_signal({
            "beat_rate": 75,
            "avg_surprise_pct": 5,
            "surprise_trend": "stable",
            "revenue_yoy_growth": 10,
            "earnings_yoy_growth": 15,
        })
        assert many["confidence"] > few["confidence"]
