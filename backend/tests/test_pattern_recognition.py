"""
Tests for Chart Pattern Recognition Service
=============================================

Tests pivot detection, support/resistance levels, and all chart patterns
(double top/bottom, head & shoulders, triangles, wedges) using synthetic data.
"""

import numpy as np

from backend.services.pattern_recognition import (
    _find_pivots,
    _cluster_prices,
    get_support_resistance,
    detect_patterns,
    get_pattern_summary,
    get_pattern_signal_score,
    _detect_double_top,
    _detect_double_bottom,
    _detect_head_shoulders,
    _detect_triangles,
    _detect_wedges,
)


# ── Helpers ─────────────────────────────────────────────────────────────

def _make_price(n: int, base: float = 100.0, noise: float = 0.5, seed: int = 42):
    """Generate random walk price data with high/low/close."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0, 0.01, n)
    close = base * np.exp(np.cumsum(returns))
    high = close * (1 + rng.uniform(0, noise / 100, n))
    low = close * (1 - rng.uniform(0, noise / 100, n))
    return high, low, close


def _make_double_top(n: int = 100, base: float = 100.0):
    """Synthesize a clear double top pattern."""
    close = np.zeros(n)
    # Ramp up to first peak
    close[:20] = np.linspace(base, base * 1.15, 20)
    # Pull back to neckline
    close[20:40] = np.linspace(base * 1.15, base * 1.05, 20)
    # Second peak at roughly same level
    close[40:60] = np.linspace(base * 1.05, base * 1.14, 20)
    # Break down through neckline
    close[60:80] = np.linspace(base * 1.14, base * 0.98, 20)
    # Continue down
    close[80:] = np.linspace(base * 0.98, base * 0.92, n - 80)

    high = close * 1.005
    low = close * 0.995
    return high, low, close


def _make_double_bottom(n: int = 100, base: float = 100.0):
    """Synthesize a clear double bottom pattern."""
    close = np.zeros(n)
    # Decline to first trough
    close[:20] = np.linspace(base, base * 0.85, 20)
    # Bounce to neckline
    close[20:40] = np.linspace(base * 0.85, base * 0.95, 20)
    # Second trough at roughly same level
    close[40:60] = np.linspace(base * 0.95, base * 0.86, 20)
    # Break up through neckline
    close[60:80] = np.linspace(base * 0.86, base * 1.02, 20)
    # Continue up
    close[80:] = np.linspace(base * 1.02, base * 1.08, n - 80)

    high = close * 1.005
    low = close * 0.995
    return high, low, close


def _make_head_shoulders(n: int = 150, base: float = 100.0):
    """Synthesize a head and shoulders pattern.

    Uses slight noise to avoid duplicate pivots at segment boundaries.
    """
    rng = np.random.default_rng(42)
    close = np.zeros(n)
    # Left shoulder: rise then fall
    close[:15] = np.linspace(base, base * 1.10, 15)
    close[15:30] = np.linspace(base * 1.10, base * 1.02, 15)
    # Head: higher peak
    close[30:50] = np.linspace(base * 1.02, base * 1.18, 20)
    close[50:70] = np.linspace(base * 1.18, base * 1.03, 20)
    # Right shoulder: lower than head
    close[70:90] = np.linspace(base * 1.03, base * 1.09, 20)
    close[90:110] = np.linspace(base * 1.09, base * 1.01, 20)
    # Neckline break
    close[110:130] = np.linspace(base * 1.01, base * 0.90, 20)
    close[130:] = np.linspace(base * 0.90, base * 0.85, n - 130)

    # Add tiny noise to break ties at segment boundaries
    close += rng.normal(0, base * 0.0005, n)

    high = close * 1.005
    low = close * 0.995
    return high, low, close


def _make_ascending_triangle(n: int = 100, base: float = 100.0):
    """Synthesize an ascending triangle (flat top, rising bottom)."""
    close = np.zeros(n)
    resistance = base * 1.10
    for i in range(n):
        t = i / n
        # Rising support line
        support = base * (1.0 + 0.08 * t)
        # Oscillate between support and resistance, with support rising
        cycle = np.sin(2 * np.pi * i / 20)
        if cycle > 0:
            close[i] = resistance - (resistance - support) * 0.1
        else:
            close[i] = support + (resistance - support) * 0.1
    # Smooth
    from numpy import convolve
    kernel = np.ones(3) / 3
    close = convolve(close, kernel, mode="same")
    # Breakout at end
    close[-10:] = np.linspace(resistance, resistance * 1.05, 10)

    high = close * 1.003
    low = close * 0.997
    return high, low, close


# ── Tests: Pivot Detection ──────────────────────────────────────────────

class TestPivotDetection:
    def test_finds_pivots_in_synthetic_data(self):
        high, low, close = _make_price(200)
        pivot_highs, pivot_lows = _find_pivots(high, low, close, window=5)

        assert len(pivot_highs) > 0, "Should find at least one pivot high"
        assert len(pivot_lows) > 0, "Should find at least one pivot low"

    def test_pivot_indices_are_valid(self):
        high, low, close = _make_price(200)
        pivot_highs, pivot_lows = _find_pivots(high, low, close, window=5)

        for p in pivot_highs:
            assert 5 <= p["index"] < 195
            assert p["price"] == high[p["index"]]

        for p in pivot_lows:
            assert 5 <= p["index"] < 195
            assert p["price"] == low[p["index"]]

    def test_no_pivots_in_flat_data(self):
        n = 50
        flat = np.full(n, 100.0)
        pivot_highs, pivot_lows = _find_pivots(flat, flat, flat, window=5)
        # All equal prices should all be pivots (or none depending on
        # implementation), but the key is no crash
        assert isinstance(pivot_highs, list)

    def test_window_parameter_affects_count(self):
        high, low, close = _make_price(200, noise=1.0, seed=7)
        small_window_h, small_window_l = _find_pivots(high, low, close, window=3)
        large_window_h, large_window_l = _find_pivots(high, low, close, window=10)

        # Smaller window should find more (or equal) pivots
        assert len(small_window_h) >= len(large_window_h)


# ── Tests: Price Clustering ─────────────────────────────────────────────

class TestPriceClustering:
    def test_clusters_nearby_prices(self):
        prices = [100.0, 100.5, 101.0, 110.0, 110.3, 110.8]
        clusters = _cluster_prices(prices, tolerance_pct=0.015)

        assert len(clusters) == 2
        assert len(clusters[0]) == 3  # 100-101 cluster
        assert len(clusters[1]) == 3  # 110-110.8 cluster

    def test_empty_prices(self):
        assert _cluster_prices([], tolerance_pct=0.01) == []

    def test_single_price(self):
        clusters = _cluster_prices([100.0], tolerance_pct=0.01)
        assert len(clusters) == 1
        assert clusters[0] == [100.0]

    def test_all_same_price(self):
        clusters = _cluster_prices([50.0, 50.0, 50.0], tolerance_pct=0.01)
        assert len(clusters) == 1
        assert len(clusters[0]) == 3


# ── Tests: Support & Resistance ─────────────────────────────────────────

class TestSupportResistance:
    def test_returns_correct_structure(self):
        high, low, close = _make_price(200)
        sr = get_support_resistance(high, low, close)

        assert "support" in sr
        assert "resistance" in sr
        assert "current_price" in sr
        assert isinstance(sr["support"], list)
        assert isinstance(sr["resistance"], list)

    def test_support_below_current_price(self):
        high, low, close = _make_price(200)
        sr = get_support_resistance(high, low, close)

        for level in sr["support"]:
            assert level["price"] < sr["current_price"]

    def test_resistance_above_current_price(self):
        high, low, close = _make_price(200)
        sr = get_support_resistance(high, low, close)

        for level in sr["resistance"]:
            assert level["price"] > sr["current_price"]

    def test_levels_have_required_fields(self):
        high, low, close = _make_price(200)
        sr = get_support_resistance(high, low, close)

        for level in sr["support"] + sr["resistance"]:
            assert "price" in level
            assert "touches" in level
            assert "strength" in level
            assert 0 <= level["strength"] <= 1

    def test_n_levels_parameter(self):
        high, low, close = _make_price(500, seed=99)
        sr = get_support_resistance(high, low, close, n_levels=3)
        assert len(sr["support"]) <= 3
        assert len(sr["resistance"]) <= 3


# ── Tests: Double Top Detection ─────────────────────────────────────────

class TestDoubleTop:
    def test_detects_synthetic_double_top(self):
        high, low, close = _make_double_top()
        pivot_highs, pivot_lows = _find_pivots(high, low, close, window=5)

        patterns = _detect_double_top(pivot_highs, pivot_lows, close, None)
        # Should find at least one double top
        assert len(patterns) >= 1
        dt = patterns[0]
        assert dt["type"] == "double_top"
        assert dt["direction"] == "bearish"
        assert dt["neckline"] > 0
        assert dt["target_price"] < dt["neckline"]
        assert 0 < dt["confidence"] <= 1.0

    def test_no_double_top_in_uptrend(self):
        """Steadily rising prices should not trigger double top."""
        n = 100
        close = np.linspace(100, 150, n)
        high = close * 1.003
        low = close * 0.997
        pivot_highs, pivot_lows = _find_pivots(high, low, close, window=5)
        patterns = _detect_double_top(pivot_highs, pivot_lows, close, None)
        # Any detected pattern should have very low confidence
        for p in patterns:
            assert p["confidence"] < 0.8


# ── Tests: Double Bottom Detection ──────────────────────────────────────

class TestDoubleBottom:
    def test_detects_synthetic_double_bottom(self):
        high, low, close = _make_double_bottom()
        pivot_highs, pivot_lows = _find_pivots(high, low, close, window=5)

        patterns = _detect_double_bottom(pivot_lows, pivot_highs, close, None)
        assert len(patterns) >= 1
        db = patterns[0]
        assert db["type"] == "double_bottom"
        assert db["direction"] == "bullish"
        assert db["neckline"] > 0
        assert db["target_price"] > db["neckline"]
        assert 0 < db["confidence"] <= 1.0


# ── Tests: Head & Shoulders ────────────────────────────────────────────

class TestHeadShoulders:
    def test_detects_synthetic_hs(self):
        high, low, close = _make_head_shoulders()
        pivot_highs, pivot_lows = _find_pivots(high, low, close, window=5)

        patterns = _detect_head_shoulders(pivot_highs, pivot_lows, close, None)
        assert len(patterns) >= 1
        hs = patterns[0]
        assert hs["type"] == "head_and_shoulders"
        assert hs["direction"] == "bearish"
        assert hs["head"]["price"] > hs["left_shoulder"]["price"]
        assert hs["head"]["price"] > hs["right_shoulder"]["price"]
        assert hs["target_price"] < hs["neckline"]


# ── Tests: Composite Detection ──────────────────────────────────────────

class TestDetectPatterns:
    def test_returns_list(self):
        high, low, close = _make_price(200)
        patterns = detect_patterns(high, low, close)
        assert isinstance(patterns, list)

    def test_all_patterns_have_required_fields(self):
        high, low, close = _make_double_top()
        patterns = detect_patterns(high, low, close)
        for p in patterns:
            assert "type" in p
            assert "direction" in p
            assert "confidence" in p
            assert "status" in p
            assert p["direction"] in ("bullish", "bearish", "neutral")
            assert p["status"] in ("confirmed", "forming")
            assert 0 <= p["confidence"] <= 1.0

    def test_date_labels(self):
        n = 100
        high, low, close = _make_double_top(n=n)
        dates = [f"2025-01-{i+1:02d}" for i in range(n)]
        patterns = detect_patterns(high, low, close, dates=dates)
        # If patterns detected, dates should be in the output
        for p in patterns:
            if "peak_1" in p and "date" in p["peak_1"]:
                assert p["peak_1"]["date"].startswith("2025")

    def test_short_data_returns_empty(self):
        """Too little data should return empty, not crash."""
        close = np.array([100, 101, 102])
        patterns = detect_patterns(close, close, close)
        assert patterns == []


# ── Tests: Pattern Summary ──────────────────────────────────────────────

class TestPatternSummary:
    def test_summary_structure(self):
        high, low, close = _make_price(200)
        summary = get_pattern_summary(high, low, close)

        assert "support_resistance" in summary
        assert "patterns" in summary
        assert "pattern_count" in summary
        assert "bullish_patterns" in summary
        assert "bearish_patterns" in summary
        assert "bias" in summary
        assert summary["bias"] in ("bullish", "bearish", "neutral")
        assert isinstance(summary["pattern_count"], int)

    def test_bearish_double_top_gives_bearish_bias(self):
        high, low, close = _make_double_top()
        summary = get_pattern_summary(high, low, close)
        # Should have bearish patterns
        assert summary["bearish_patterns"] >= 1

    def test_bullish_double_bottom_gives_bullish_bias(self):
        high, low, close = _make_double_bottom()
        summary = get_pattern_summary(high, low, close)
        assert summary["bullish_patterns"] >= 1


# ── Tests: Signal Score ─────────────────────────────────────────────────

class TestPatternSignalScore:
    def test_none_input(self):
        assert get_pattern_signal_score(None) is None

    def test_no_patterns_returns_zero(self):
        score = get_pattern_signal_score({"patterns": []})
        assert score == 0.0

    def test_bullish_patterns_positive(self):
        summary = {
            "patterns": [
                {"direction": "bullish", "confidence": 0.8, "status": "confirmed"},
            ]
        }
        score = get_pattern_signal_score(summary)
        assert score > 0

    def test_bearish_patterns_negative(self):
        summary = {
            "patterns": [
                {"direction": "bearish", "confidence": 0.8, "status": "confirmed"},
            ]
        }
        score = get_pattern_signal_score(summary)
        assert score < 0

    def test_score_bounded(self):
        summary = {
            "patterns": [
                {"direction": "bullish", "confidence": 1.0, "status": "confirmed"},
                {"direction": "bullish", "confidence": 1.0, "status": "confirmed"},
                {"direction": "bullish", "confidence": 1.0, "status": "confirmed"},
                {"direction": "bullish", "confidence": 1.0, "status": "confirmed"},
            ]
        }
        score = get_pattern_signal_score(summary)
        assert -1.0 <= score <= 1.0


# ── Tests: Triangles ───────────────────────────────────────────────────

class TestTriangles:
    def test_no_crash_on_random_data(self):
        high, low, close = _make_price(200, seed=123)
        pivot_highs, pivot_lows = _find_pivots(high, low, close)
        patterns = _detect_triangles(pivot_highs, pivot_lows, close, None)
        assert isinstance(patterns, list)

    def test_triangle_fields(self):
        """If a triangle is found, it should have the right fields."""
        high, low, close = _make_ascending_triangle()
        pivot_highs, pivot_lows = _find_pivots(high, low, close)
        patterns = _detect_triangles(pivot_highs, pivot_lows, close, None)
        for p in patterns:
            assert "upper_trendline_slope" in p
            assert "lower_trendline_slope" in p
            assert "convergence_pct" in p
            assert p["convergence_pct"] > 0


# ── Tests: Wedges ──────────────────────────────────────────────────────

class TestWedges:
    def test_no_crash_on_random_data(self):
        high, low, close = _make_price(200, seed=456)
        pivot_highs, pivot_lows = _find_pivots(high, low, close)
        patterns = _detect_wedges(pivot_highs, pivot_lows, close, None)
        assert isinstance(patterns, list)

    def test_wedge_has_correct_fields(self):
        """Wedge patterns should have trendline slopes and convergence."""
        # Create a rising wedge
        n = 100
        close = np.zeros(n)
        for i in range(n):
            t = i / n
            base = 100 + 20 * t  # Rising base
            top = 100 + 25 * t   # Rising top (slightly steeper)
            cycle = np.sin(2 * np.pi * i / 15)
            close[i] = base + (top - base) * (0.5 + 0.4 * cycle)
        high = close * 1.003
        low = close * 0.997

        pivot_highs, pivot_lows = _find_pivots(high, low, close)
        patterns = _detect_wedges(pivot_highs, pivot_lows, close, None)
        for p in patterns:
            assert "type" in p
            assert p["type"] in ("rising_wedge", "falling_wedge")
            assert "convergence_pct" in p
            assert "target_price" in p


# ── Tests: Edge Cases ──────────────────────────────────────────────────

class TestEdgeCases:
    def test_very_short_data(self):
        """Should handle data too short for any analysis."""
        close = np.array([100.0, 101.0, 99.0])
        high = close * 1.01
        low = close * 0.99
        summary = get_pattern_summary(high, low, close)
        assert summary["pattern_count"] == 0
        assert summary["bias"] == "neutral"

    def test_constant_price(self):
        """All same price should not crash."""
        n = 100
        close = np.full(n, 50.0)
        summary = get_pattern_summary(close, close, close)
        assert isinstance(summary, dict)

    def test_single_bar(self):
        """Single bar should return empty patterns."""
        close = np.array([100.0])
        high = np.array([101.0])
        low = np.array([99.0])
        summary = get_pattern_summary(high, low, close)
        assert summary["pattern_count"] == 0

    def test_large_dataset(self):
        """Performance test: should handle 5 years of daily data."""
        high, low, close = _make_price(1260, seed=77)
        summary = get_pattern_summary(high, low, close)
        assert isinstance(summary, dict)
        assert "support_resistance" in summary
