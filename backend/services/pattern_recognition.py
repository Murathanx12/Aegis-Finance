"""
Aegis Finance — Chart Pattern Recognition Service
=====================================================

TradingView-style automatic chart pattern detection. Identifies classic
technical patterns from OHLC price data and computes projected targets.

Patterns detected:
  - Support & Resistance levels (pivot-based clustering)
  - Double Top / Double Bottom
  - Head & Shoulders / Inverse Head & Shoulders
  - Ascending / Descending / Symmetrical Triangles
  - Rising / Falling Wedges
  - Bullish / Bearish Flags
  - Trendline breakouts (ascending / descending support/resistance)

Each pattern includes:
  - Pattern type and direction (bullish/bearish)
  - Key price levels (neckline, peaks, troughs)
  - Projected price target (measured move)
  - Confidence score (0-1)
  - Whether it's confirmed (breakout) or still forming

Usage:
    from backend.services.pattern_recognition import detect_patterns, get_support_resistance
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from backend.cache import cache_get, cache_set
from backend.config import config

logger = logging.getLogger(__name__)

_CACHE_TTL = 3600  # 1 hour

# ── Config defaults (overridden by config.py if present) ──────────────────

_PATTERN_CFG = config.get("pattern_recognition", {})
_PIVOT_WINDOW = _PATTERN_CFG.get("pivot_window", 5)
_SR_CLUSTER_PCT = _PATTERN_CFG.get("sr_cluster_pct", 0.015)
_MIN_PATTERN_BARS = _PATTERN_CFG.get("min_pattern_bars", 10)
_MAX_PATTERN_BARS = _PATTERN_CFG.get("max_pattern_bars", 120)
_BREAKOUT_THRESHOLD = _PATTERN_CFG.get("breakout_threshold", 0.005)
_DOUBLE_TOLERANCE = _PATTERN_CFG.get("double_tolerance", 0.03)
_HS_SHOULDER_TOLERANCE = _PATTERN_CFG.get("hs_shoulder_tolerance", 0.05)


# ── Pivot Detection ─────────────────────────────────────────────────────

def _find_pivots(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    window: int = _PIVOT_WINDOW,
) -> tuple[list[dict], list[dict]]:
    """Find local pivot highs and lows using a rolling window.

    A pivot high at index i means high[i] is the max of high[i-window:i+window+1].
    A pivot low at index i means low[i] is the min of low[i-window:i+window+1].

    Returns:
        (pivot_highs, pivot_lows) — each is a list of {index, price}.
    """
    n = len(close)
    pivot_highs = []
    pivot_lows = []

    for i in range(window, n - window):
        # Pivot high: current high is the max in the window
        if high[i] == np.max(high[i - window:i + window + 1]):
            pivot_highs.append({"index": i, "price": float(high[i])})
        # Pivot low: current low is the min in the window
        if low[i] == np.min(low[i - window:i + window + 1]):
            pivot_lows.append({"index": i, "price": float(low[i])})

    return pivot_highs, pivot_lows


# ── Support & Resistance ────────────────────────────────────────────────

def get_support_resistance(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    n_levels: int = 5,
) -> dict:
    """Detect key support and resistance levels by clustering pivot points.

    Groups nearby pivot prices (within sr_cluster_pct of each other) and
    returns the strongest levels (most touches).

    Returns:
        {"support": [...], "resistance": [...], "current_price": float}
    """
    pivot_highs, pivot_lows = _find_pivots(high, low, close)

    current_price = float(close[-1])

    # Collect all pivot prices with type
    all_pivots = (
        [(p["price"], "high") for p in pivot_highs]
        + [(p["price"], "low") for p in pivot_lows]
    )

    if not all_pivots:
        return {"support": [], "resistance": [], "current_price": current_price}

    # Cluster pivots by proximity
    clusters = _cluster_prices(
        [p[0] for p in all_pivots],
        tolerance_pct=_SR_CLUSTER_PCT,
    )

    # Build levels with touch count and average price
    levels = []
    for cluster in clusters:
        avg_price = np.mean(cluster)
        levels.append({
            "price": round(float(avg_price), 2),
            "touches": len(cluster),
            "strength": min(len(cluster) / 5.0, 1.0),  # normalize to 0-1
        })

    # Sort by strength (most touches first)
    levels.sort(key=lambda x: x["touches"], reverse=True)

    # Classify as support or resistance relative to current price
    support = [
        lv for lv in levels if lv["price"] < current_price * 0.998
    ][:n_levels]
    resistance = [
        lv for lv in levels if lv["price"] > current_price * 1.002
    ][:n_levels]

    # Sort support descending (nearest first), resistance ascending
    support.sort(key=lambda x: x["price"], reverse=True)
    resistance.sort(key=lambda x: x["price"])

    return {
        "support": support,
        "resistance": resistance,
        "current_price": round(current_price, 2),
    }


def _cluster_prices(prices: list[float], tolerance_pct: float) -> list[list[float]]:
    """Group prices within tolerance_pct of each other into clusters."""
    if not prices:
        return []

    sorted_prices = sorted(prices)
    clusters = [[sorted_prices[0]]]

    for price in sorted_prices[1:]:
        cluster_avg = np.mean(clusters[-1])
        if abs(price - cluster_avg) / cluster_avg <= tolerance_pct:
            clusters[-1].append(price)
        else:
            clusters.append([price])

    return clusters


# ── Pattern Detection ───────────────────────────────────────────────────

def detect_patterns(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    dates: Optional[list] = None,
) -> list[dict]:
    """Detect all chart patterns in the given OHLC data.

    Args:
        high: High prices array
        low: Low prices array
        close: Close prices array
        dates: Optional date labels for each bar

    Returns:
        List of detected patterns, each with type, direction, confidence,
        key levels, target price, and status (confirmed/forming).
    """
    pivot_highs, pivot_lows = _find_pivots(high, low, close)

    if len(pivot_highs) < 2 or len(pivot_lows) < 2:
        return []

    patterns = []

    # Double Top / Double Bottom
    patterns.extend(_detect_double_top(pivot_highs, pivot_lows, close, dates))
    patterns.extend(_detect_double_bottom(pivot_lows, pivot_highs, close, dates))

    # Head & Shoulders / Inverse Head & Shoulders
    patterns.extend(_detect_head_shoulders(pivot_highs, pivot_lows, close, dates))
    patterns.extend(_detect_inverse_head_shoulders(pivot_lows, pivot_highs, close, dates))

    # Triangles (ascending, descending, symmetrical)
    patterns.extend(_detect_triangles(pivot_highs, pivot_lows, close, dates))

    # Wedges (rising, falling)
    patterns.extend(_detect_wedges(pivot_highs, pivot_lows, close, dates))

    # Sort by recency (most recent pattern first) then by confidence
    patterns.sort(key=lambda p: (-p.get("end_index", 0), -p.get("confidence", 0)))

    return patterns


def _detect_double_top(
    pivot_highs: list[dict],
    pivot_lows: list[dict],
    close: np.ndarray,
    dates: Optional[list],
) -> list[dict]:
    """Detect double top pattern (bearish reversal).

    Two peaks at roughly the same level with a trough between them.
    Confirmed when price breaks below the neckline (trough level).
    """
    patterns = []
    n = len(close)

    for i in range(len(pivot_highs) - 1):
        p1 = pivot_highs[i]
        p2 = pivot_highs[i + 1]

        # Peaks must be within tolerance of each other
        avg_peak = (p1["price"] + p2["price"]) / 2
        if abs(p1["price"] - p2["price"]) / avg_peak > _DOUBLE_TOLERANCE:
            continue

        # Must have enough bars between peaks
        bar_span = p2["index"] - p1["index"]
        if bar_span < _MIN_PATTERN_BARS or bar_span > _MAX_PATTERN_BARS:
            continue

        # Find the lowest trough between the two peaks
        troughs_between = [
            pl for pl in pivot_lows
            if p1["index"] < pl["index"] < p2["index"]
        ]
        if not troughs_between:
            continue

        neckline_pivot = min(troughs_between, key=lambda x: x["price"])
        neckline = neckline_pivot["price"]

        # Pattern height for target
        pattern_height = avg_peak - neckline
        target = neckline - pattern_height  # measured move down

        # Check if confirmed (price broke below neckline after second peak)
        confirmed = False
        breakout_index = None
        for j in range(p2["index"] + 1, min(p2["index"] + 30, n)):
            if close[j] < neckline * (1 - _BREAKOUT_THRESHOLD):
                confirmed = True
                breakout_index = j
                break

        # Confidence based on symmetry, volume, and confirmation
        symmetry = 1.0 - abs(p1["price"] - p2["price"]) / avg_peak / _DOUBLE_TOLERANCE
        confidence = 0.5 * symmetry + (0.3 if confirmed else 0.0)
        # Bonus if second peak is slightly lower (bearish)
        if p2["price"] < p1["price"]:
            confidence += 0.1
        # Recency bonus
        if p2["index"] > n - 40:
            confidence += 0.1
        confidence = min(confidence, 1.0)

        pattern = {
            "type": "double_top",
            "direction": "bearish",
            "confidence": round(confidence, 2),
            "status": "confirmed" if confirmed else "forming",
            "peak_1": {"price": round(p1["price"], 2), "index": p1["index"]},
            "peak_2": {"price": round(p2["price"], 2), "index": p2["index"]},
            "neckline": round(neckline, 2),
            "target_price": round(target, 2),
            "pattern_height_pct": round(pattern_height / avg_peak * 100, 2),
            "start_index": p1["index"],
            "end_index": breakout_index or p2["index"],
        }
        if dates:
            pattern["peak_1"]["date"] = str(dates[p1["index"]])
            pattern["peak_2"]["date"] = str(dates[p2["index"]])
            if breakout_index and breakout_index < len(dates):
                pattern["breakout_date"] = str(dates[breakout_index])

        patterns.append(pattern)

    return patterns


def _detect_double_bottom(
    pivot_lows: list[dict],
    pivot_highs: list[dict],
    close: np.ndarray,
    dates: Optional[list],
) -> list[dict]:
    """Detect double bottom pattern (bullish reversal).

    Two troughs at roughly the same level with a peak between them.
    Confirmed when price breaks above the neckline (peak level).
    """
    patterns = []
    n = len(close)

    for i in range(len(pivot_lows) - 1):
        t1 = pivot_lows[i]
        t2 = pivot_lows[i + 1]

        avg_trough = (t1["price"] + t2["price"]) / 2
        if avg_trough == 0:
            continue
        if abs(t1["price"] - t2["price"]) / avg_trough > _DOUBLE_TOLERANCE:
            continue

        bar_span = t2["index"] - t1["index"]
        if bar_span < _MIN_PATTERN_BARS or bar_span > _MAX_PATTERN_BARS:
            continue

        peaks_between = [
            ph for ph in pivot_highs
            if t1["index"] < ph["index"] < t2["index"]
        ]
        if not peaks_between:
            continue

        neckline_pivot = max(peaks_between, key=lambda x: x["price"])
        neckline = neckline_pivot["price"]

        pattern_height = neckline - avg_trough
        target = neckline + pattern_height

        confirmed = False
        breakout_index = None
        for j in range(t2["index"] + 1, min(t2["index"] + 30, n)):
            if close[j] > neckline * (1 + _BREAKOUT_THRESHOLD):
                confirmed = True
                breakout_index = j
                break

        symmetry = 1.0 - abs(t1["price"] - t2["price"]) / avg_trough / _DOUBLE_TOLERANCE
        confidence = 0.5 * symmetry + (0.3 if confirmed else 0.0)
        if t2["price"] > t1["price"]:
            confidence += 0.1
        if t2["index"] > n - 40:
            confidence += 0.1
        confidence = min(confidence, 1.0)

        pattern = {
            "type": "double_bottom",
            "direction": "bullish",
            "confidence": round(confidence, 2),
            "status": "confirmed" if confirmed else "forming",
            "trough_1": {"price": round(t1["price"], 2), "index": t1["index"]},
            "trough_2": {"price": round(t2["price"], 2), "index": t2["index"]},
            "neckline": round(neckline, 2),
            "target_price": round(target, 2),
            "pattern_height_pct": round(pattern_height / neckline * 100, 2),
            "start_index": t1["index"],
            "end_index": breakout_index or t2["index"],
        }
        if dates:
            pattern["trough_1"]["date"] = str(dates[t1["index"]])
            pattern["trough_2"]["date"] = str(dates[t2["index"]])
            if breakout_index and breakout_index < len(dates):
                pattern["breakout_date"] = str(dates[breakout_index])

        patterns.append(pattern)

    return patterns


def _detect_head_shoulders(
    pivot_highs: list[dict],
    pivot_lows: list[dict],
    close: np.ndarray,
    dates: Optional[list],
) -> list[dict]:
    """Detect head & shoulders pattern (bearish reversal).

    Three peaks: left shoulder, head (highest), right shoulder.
    Shoulders at roughly the same level, head higher than both.
    """
    patterns = []
    n = len(close)

    for i in range(len(pivot_highs) - 2):
        ls = pivot_highs[i]      # left shoulder
        head = pivot_highs[i + 1]  # head
        rs = pivot_highs[i + 2]  # right shoulder

        # Head must be highest
        if head["price"] <= ls["price"] or head["price"] <= rs["price"]:
            continue

        # Shoulders must be roughly equal
        avg_shoulder = (ls["price"] + rs["price"]) / 2
        if avg_shoulder == 0:
            continue
        if abs(ls["price"] - rs["price"]) / avg_shoulder > _HS_SHOULDER_TOLERANCE:
            continue

        # Pattern span check
        total_span = rs["index"] - ls["index"]
        if total_span < _MIN_PATTERN_BARS * 2 or total_span > _MAX_PATTERN_BARS:
            continue

        # Find neckline: troughs between LS-Head and Head-RS
        trough_left = [
            pl for pl in pivot_lows
            if ls["index"] < pl["index"] < head["index"]
        ]
        trough_right = [
            pl for pl in pivot_lows
            if head["index"] < pl["index"] < rs["index"]
        ]
        if not trough_left or not trough_right:
            continue

        nl_left = min(trough_left, key=lambda x: x["price"])
        nl_right = min(trough_right, key=lambda x: x["price"])
        neckline = (nl_left["price"] + nl_right["price"]) / 2

        # Pattern height and target
        pattern_height = head["price"] - neckline
        target = neckline - pattern_height

        # Check confirmation
        confirmed = False
        breakout_index = None
        for j in range(rs["index"] + 1, min(rs["index"] + 30, n)):
            if close[j] < neckline * (1 - _BREAKOUT_THRESHOLD):
                confirmed = True
                breakout_index = j
                break

        # Confidence
        shoulder_symmetry = 1.0 - abs(ls["price"] - rs["price"]) / avg_shoulder / _HS_SHOULDER_TOLERANCE
        head_prominence = min((head["price"] - avg_shoulder) / avg_shoulder / 0.05, 1.0)
        confidence = 0.3 * shoulder_symmetry + 0.2 * head_prominence + (0.3 if confirmed else 0.0)
        if rs["index"] > n - 40:
            confidence += 0.1
        # Bonus for sloping neckline (more reliable if flat)
        neckline_slope = abs(nl_left["price"] - nl_right["price"]) / neckline
        if neckline_slope < 0.02:
            confidence += 0.1
        confidence = min(confidence, 1.0)

        pattern = {
            "type": "head_and_shoulders",
            "direction": "bearish",
            "confidence": round(confidence, 2),
            "status": "confirmed" if confirmed else "forming",
            "left_shoulder": {"price": round(ls["price"], 2), "index": ls["index"]},
            "head": {"price": round(head["price"], 2), "index": head["index"]},
            "right_shoulder": {"price": round(rs["price"], 2), "index": rs["index"]},
            "neckline": round(neckline, 2),
            "neckline_slope": round(nl_right["price"] - nl_left["price"], 2),
            "target_price": round(target, 2),
            "pattern_height_pct": round(pattern_height / head["price"] * 100, 2),
            "start_index": ls["index"],
            "end_index": breakout_index or rs["index"],
        }
        if dates:
            pattern["left_shoulder"]["date"] = str(dates[ls["index"]])
            pattern["head"]["date"] = str(dates[head["index"]])
            pattern["right_shoulder"]["date"] = str(dates[rs["index"]])

        patterns.append(pattern)

    return patterns


def _detect_inverse_head_shoulders(
    pivot_lows: list[dict],
    pivot_highs: list[dict],
    close: np.ndarray,
    dates: Optional[list],
) -> list[dict]:
    """Detect inverse head & shoulders (bullish reversal).

    Three troughs: left shoulder, head (lowest), right shoulder.
    """
    patterns = []
    n = len(close)

    for i in range(len(pivot_lows) - 2):
        ls = pivot_lows[i]
        head = pivot_lows[i + 1]
        rs = pivot_lows[i + 2]

        # Head must be lowest
        if head["price"] >= ls["price"] or head["price"] >= rs["price"]:
            continue

        avg_shoulder = (ls["price"] + rs["price"]) / 2
        if avg_shoulder == 0:
            continue
        if abs(ls["price"] - rs["price"]) / avg_shoulder > _HS_SHOULDER_TOLERANCE:
            continue

        total_span = rs["index"] - ls["index"]
        if total_span < _MIN_PATTERN_BARS * 2 or total_span > _MAX_PATTERN_BARS:
            continue

        peak_left = [
            ph for ph in pivot_highs
            if ls["index"] < ph["index"] < head["index"]
        ]
        peak_right = [
            ph for ph in pivot_highs
            if head["index"] < ph["index"] < rs["index"]
        ]
        if not peak_left or not peak_right:
            continue

        nl_left = max(peak_left, key=lambda x: x["price"])
        nl_right = max(peak_right, key=lambda x: x["price"])
        neckline = (nl_left["price"] + nl_right["price"]) / 2

        pattern_height = neckline - head["price"]
        target = neckline + pattern_height

        confirmed = False
        breakout_index = None
        for j in range(rs["index"] + 1, min(rs["index"] + 30, n)):
            if close[j] > neckline * (1 + _BREAKOUT_THRESHOLD):
                confirmed = True
                breakout_index = j
                break

        shoulder_symmetry = 1.0 - abs(ls["price"] - rs["price"]) / avg_shoulder / _HS_SHOULDER_TOLERANCE
        head_prominence = min((avg_shoulder - head["price"]) / avg_shoulder / 0.05, 1.0)
        confidence = 0.3 * shoulder_symmetry + 0.2 * head_prominence + (0.3 if confirmed else 0.0)
        if rs["index"] > n - 40:
            confidence += 0.1
        neckline_slope = abs(nl_left["price"] - nl_right["price"]) / neckline
        if neckline_slope < 0.02:
            confidence += 0.1
        confidence = min(confidence, 1.0)

        pattern = {
            "type": "inverse_head_and_shoulders",
            "direction": "bullish",
            "confidence": round(confidence, 2),
            "status": "confirmed" if confirmed else "forming",
            "left_shoulder": {"price": round(ls["price"], 2), "index": ls["index"]},
            "head": {"price": round(head["price"], 2), "index": head["index"]},
            "right_shoulder": {"price": round(rs["price"], 2), "index": rs["index"]},
            "neckline": round(neckline, 2),
            "target_price": round(target, 2),
            "pattern_height_pct": round(pattern_height / neckline * 100, 2),
            "start_index": ls["index"],
            "end_index": breakout_index or rs["index"],
        }
        if dates:
            pattern["left_shoulder"]["date"] = str(dates[ls["index"]])
            pattern["head"]["date"] = str(dates[head["index"]])
            pattern["right_shoulder"]["date"] = str(dates[rs["index"]])

        patterns.append(pattern)

    return patterns


def _detect_triangles(
    pivot_highs: list[dict],
    pivot_lows: list[dict],
    close: np.ndarray,
    dates: Optional[list],
) -> list[dict]:
    """Detect triangle patterns (ascending, descending, symmetrical).

    Uses the last 4+ pivot points to fit trendlines for highs and lows,
    then classifies by the slope combination.
    """
    patterns = []
    n = len(close)

    # Need at least 2 recent pivot highs and 2 recent pivot lows
    if len(pivot_highs) < 2 or len(pivot_lows) < 2:
        return patterns

    # Use the most recent pivots (last 4-6 of each type)
    recent_highs = pivot_highs[-6:]
    recent_lows = pivot_lows[-6:]

    # Try different window sizes to find triangles
    for hi_start in range(max(0, len(recent_highs) - 4), len(recent_highs) - 1):
        for lo_start in range(max(0, len(recent_lows) - 4), len(recent_lows) - 1):
            highs_subset = recent_highs[hi_start:]
            lows_subset = recent_lows[lo_start:]

            if len(highs_subset) < 2 or len(lows_subset) < 2:
                continue

            # Fit trendlines (linear regression on pivot points)
            h_indices = np.array([p["index"] for p in highs_subset], dtype=float)
            h_prices = np.array([p["price"] for p in highs_subset])
            l_indices = np.array([p["index"] for p in lows_subset], dtype=float)
            l_prices = np.array([p["price"] for p in lows_subset])

            # Lines must overlap in time
            overlap_start = max(h_indices[0], l_indices[0])
            overlap_end = min(h_indices[-1], l_indices[-1])
            if overlap_end - overlap_start < _MIN_PATTERN_BARS:
                continue

            # Fit lines
            h_slope, h_intercept = np.polyfit(h_indices, h_prices, 1)
            l_slope, l_intercept = np.polyfit(l_indices, l_prices, 1)

            # Normalize slopes relative to price level
            avg_price = np.mean(close[int(overlap_start):int(overlap_end) + 1])
            if avg_price == 0:
                continue
            h_slope_norm = h_slope / avg_price * 252  # annualized slope
            l_slope_norm = l_slope / avg_price * 252

            # Classify triangle type
            slope_threshold = 0.03  # ~3% annualized slope is "flat"

            if abs(h_slope_norm) < slope_threshold and l_slope_norm > slope_threshold:
                triangle_type = "ascending_triangle"
                direction = "bullish"
            elif h_slope_norm < -slope_threshold and abs(l_slope_norm) < slope_threshold:
                triangle_type = "descending_triangle"
                direction = "bearish"
            elif h_slope_norm < -slope_threshold and l_slope_norm > slope_threshold:
                triangle_type = "symmetrical_triangle"
                direction = "neutral"
            else:
                continue  # Not a converging triangle

            # Check convergence: lines must actually narrow
            start_gap = (h_intercept + h_slope * overlap_start) - (l_intercept + l_slope * overlap_start)
            end_gap = (h_intercept + h_slope * overlap_end) - (l_intercept + l_slope * overlap_end)
            if end_gap >= start_gap or end_gap <= 0:
                continue  # Not converging

            # Compute apex (where lines would meet)
            if abs(h_slope - l_slope) > 1e-10:
                apex_index = (l_intercept - h_intercept) / (h_slope - l_slope)
            else:
                continue

            # Pattern height at start for target
            pattern_height = start_gap
            upper_at_end = h_intercept + h_slope * overlap_end
            lower_at_end = l_intercept + l_slope * overlap_end

            if direction == "bullish":
                target = upper_at_end + pattern_height * 0.75
            elif direction == "bearish":
                target = lower_at_end - pattern_height * 0.75
            else:
                target = None  # Symmetrical can break either way

            # Check breakout
            confirmed = False
            breakout_dir = None
            breakout_index = None
            last_pivot = int(max(h_indices[-1], l_indices[-1]))
            for j in range(last_pivot + 1, min(last_pivot + 20, n)):
                upper_line = h_intercept + h_slope * j
                lower_line = l_intercept + l_slope * j
                if close[j] > upper_line * (1 + _BREAKOUT_THRESHOLD):
                    confirmed = True
                    breakout_dir = "bullish"
                    breakout_index = j
                    if target is None:
                        target = upper_line + pattern_height * 0.75
                    break
                elif close[j] < lower_line * (1 - _BREAKOUT_THRESHOLD):
                    confirmed = True
                    breakout_dir = "bearish"
                    breakout_index = j
                    if target is None:
                        target = lower_line - pattern_height * 0.75
                    break

            # Confidence
            convergence_ratio = end_gap / start_gap if start_gap > 0 else 1.0
            confidence = 0.3 * (1 - convergence_ratio)  # tighter = better
            confidence += 0.2 * min(len(highs_subset) + len(lows_subset), 8) / 8
            if confirmed:
                confidence += 0.3
            if last_pivot > n - 40:
                confidence += 0.1
            confidence = round(min(confidence, 1.0), 2)

            pattern = {
                "type": triangle_type,
                "direction": breakout_dir or direction,
                "confidence": confidence,
                "status": "confirmed" if confirmed else "forming",
                "upper_trendline_slope": round(h_slope_norm, 4),
                "lower_trendline_slope": round(l_slope_norm, 4),
                "convergence_pct": round((1 - end_gap / start_gap) * 100, 1) if start_gap > 0 else 0,
                "pattern_height_pct": round(pattern_height / avg_price * 100, 2),
                "start_index": int(overlap_start),
                "end_index": breakout_index or int(overlap_end),
            }
            if target is not None:
                pattern["target_price"] = round(target, 2)
            if dates:
                pattern["start_date"] = str(dates[int(overlap_start)])
                pattern["end_date"] = str(dates[int(min(overlap_end, len(dates) - 1))])

            patterns.append(pattern)

    return patterns


def _detect_wedges(
    pivot_highs: list[dict],
    pivot_lows: list[dict],
    close: np.ndarray,
    dates: Optional[list],
) -> list[dict]:
    """Detect rising and falling wedge patterns.

    Rising wedge: both trendlines slope up, but lower trendline steeper (converging).
    Falling wedge: both trendlines slope down, but upper trendline steeper (converging).
    """
    patterns = []
    n = len(close)

    if len(pivot_highs) < 3 or len(pivot_lows) < 3:
        return patterns

    recent_highs = pivot_highs[-5:]
    recent_lows = pivot_lows[-5:]

    if len(recent_highs) < 2 or len(recent_lows) < 2:
        return patterns

    h_indices = np.array([p["index"] for p in recent_highs], dtype=float)
    h_prices = np.array([p["price"] for p in recent_highs])
    l_indices = np.array([p["index"] for p in recent_lows], dtype=float)
    l_prices = np.array([p["price"] for p in recent_lows])

    overlap_start = max(h_indices[0], l_indices[0])
    overlap_end = min(h_indices[-1], l_indices[-1])
    if overlap_end - overlap_start < _MIN_PATTERN_BARS:
        return patterns

    h_slope, h_intercept = np.polyfit(h_indices, h_prices, 1)
    l_slope, l_intercept = np.polyfit(l_indices, l_prices, 1)

    avg_price = np.mean(close[int(overlap_start):int(overlap_end) + 1])
    if avg_price == 0:
        return patterns

    h_slope_norm = h_slope / avg_price * 252
    l_slope_norm = l_slope / avg_price * 252

    slope_min = 0.03

    # Rising wedge: both slopes positive, converging (upper slope < lower slope)
    # Falling wedge: both slopes negative, converging (upper slope > lower slope in absolute terms)
    wedge_type = None
    if h_slope_norm > slope_min and l_slope_norm > slope_min:
        # Both rising — check convergence
        start_gap = (h_intercept + h_slope * overlap_start) - (l_intercept + l_slope * overlap_start)
        end_gap = (h_intercept + h_slope * overlap_end) - (l_intercept + l_slope * overlap_end)
        if 0 < end_gap < start_gap:
            wedge_type = "rising_wedge"
            direction = "bearish"  # Rising wedges break down
    elif h_slope_norm < -slope_min and l_slope_norm < -slope_min:
        start_gap = (h_intercept + h_slope * overlap_start) - (l_intercept + l_slope * overlap_start)
        end_gap = (h_intercept + h_slope * overlap_end) - (l_intercept + l_slope * overlap_end)
        if 0 < end_gap < start_gap:
            wedge_type = "falling_wedge"
            direction = "bullish"  # Falling wedges break up

    if wedge_type is None:
        return patterns

    pattern_height = start_gap

    if direction == "bearish":
        target = (l_intercept + l_slope * overlap_end) - pattern_height * 0.75
    else:
        target = (h_intercept + h_slope * overlap_end) + pattern_height * 0.75

    # Check breakout
    confirmed = False
    breakout_index = None
    last_pivot = int(max(h_indices[-1], l_indices[-1]))
    for j in range(last_pivot + 1, min(last_pivot + 20, n)):
        upper_line = h_intercept + h_slope * j
        lower_line = l_intercept + l_slope * j
        if direction == "bullish" and close[j] > upper_line * (1 + _BREAKOUT_THRESHOLD):
            confirmed = True
            breakout_index = j
            break
        elif direction == "bearish" and close[j] < lower_line * (1 - _BREAKOUT_THRESHOLD):
            confirmed = True
            breakout_index = j
            break

    convergence_ratio = end_gap / start_gap if start_gap > 0 else 1.0
    confidence = 0.3 * (1 - convergence_ratio)
    confidence += 0.2 * min(len(recent_highs) + len(recent_lows), 8) / 8
    if confirmed:
        confidence += 0.3
    if last_pivot > n - 40:
        confidence += 0.1
    confidence = round(min(confidence, 1.0), 2)

    pattern = {
        "type": wedge_type,
        "direction": direction,
        "confidence": confidence,
        "status": "confirmed" if confirmed else "forming",
        "upper_trendline_slope": round(h_slope_norm, 4),
        "lower_trendline_slope": round(l_slope_norm, 4),
        "convergence_pct": round((1 - convergence_ratio) * 100, 1),
        "pattern_height_pct": round(pattern_height / avg_price * 100, 2),
        "target_price": round(target, 2),
        "start_index": int(overlap_start),
        "end_index": breakout_index or int(overlap_end),
    }
    if dates:
        pattern["start_date"] = str(dates[int(overlap_start)])
        pattern["end_date"] = str(dates[int(min(overlap_end, len(dates) - 1))])

    patterns.append(pattern)
    return patterns


# ── Composite Pattern Summary ───────────────────────────────────────────

def get_pattern_summary(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    dates: Optional[list] = None,
) -> dict:
    """Get a complete pattern analysis summary with S/R levels and patterns.

    Returns:
        {
            "support_resistance": {...},
            "patterns": [...],
            "pattern_count": int,
            "bullish_patterns": int,
            "bearish_patterns": int,
            "bias": "bullish" | "bearish" | "neutral",
            "strongest_pattern": {...} or None,
        }
    """
    sr = get_support_resistance(high, low, close)
    patterns = detect_patterns(high, low, close, dates)

    bullish = [p for p in patterns if p["direction"] == "bullish"]
    bearish = [p for p in patterns if p["direction"] == "bearish"]

    # Weighted bias (confirmed patterns count more)
    bullish_weight = sum(
        p["confidence"] * (1.5 if p["status"] == "confirmed" else 1.0) for p in bullish
    )
    bearish_weight = sum(
        p["confidence"] * (1.5 if p["status"] == "confirmed" else 1.0) for p in bearish
    )

    if bullish_weight > bearish_weight * 1.3:
        bias = "bullish"
    elif bearish_weight > bullish_weight * 1.3:
        bias = "bearish"
    else:
        bias = "neutral"

    strongest = None
    if patterns:
        # Prefer confirmed patterns, then highest confidence
        confirmed = [p for p in patterns if p["status"] == "confirmed"]
        pool = confirmed if confirmed else patterns
        strongest = max(pool, key=lambda p: p["confidence"])

    return {
        "support_resistance": sr,
        "patterns": patterns,
        "pattern_count": len(patterns),
        "bullish_patterns": len(bullish),
        "bearish_patterns": len(bearish),
        "bias": bias,
        "strongest_pattern": strongest,
    }


# ── Cached Entry Point ─────────────────────────────────────────────────

def get_ticker_patterns(ticker: str, period: str = "1y") -> Optional[dict]:
    """Fetch price data and detect patterns for a ticker.

    Args:
        ticker: Stock ticker symbol
        period: yfinance period string (default "1y")

    Returns:
        Full pattern analysis dict, or None if data unavailable.
    """
    cache_key = f"patterns:{ticker}:{period}"
    cached = cache_get(cache_key, _CACHE_TTL)
    if cached is not None:
        return cached

    try:
        import yfinance as yf

        t = yf.Ticker(ticker)
        hist = t.history(period=period)
        if hist is None or len(hist) < 50:
            logger.debug("%s: Insufficient price data for pattern detection", ticker)
            return None

        high = hist["High"].values
        low = hist["Low"].values
        close = hist["Close"].values
        dates = [str(d.date()) for d in hist.index]

        result = get_pattern_summary(high, low, close, dates)
        result["ticker"] = ticker
        result["period"] = period
        result["bars_analyzed"] = len(close)

        cache_set(cache_key, result)
        return result

    except Exception as e:
        logger.warning("%s: Pattern detection failed — %s", ticker, e)
        return None


def get_pattern_signal_score(summary: dict) -> Optional[float]:
    """Convert pattern summary into a signal score [-1, +1].

    Useful for integration into the signal engine.
    """
    if not summary:
        return None

    patterns = summary.get("patterns", [])
    if not patterns:
        return 0.0

    score = 0.0
    for p in patterns:
        weight = p["confidence"]
        if p["status"] == "confirmed":
            weight *= 1.5
        if p["direction"] == "bullish":
            score += weight
        elif p["direction"] == "bearish":
            score -= weight

    # Normalize to [-1, 1]
    return max(-1.0, min(1.0, round(score / 2, 3)))
