"""
Aegis Finance — Economic Surprise Index
==========================================

Computes an economic surprise index measuring how actual FRED data releases
compare to their recent trend (rolling median as consensus proxy).

When macro data consistently beats trend → bullish surprise → positive signal.
When macro data consistently misses trend → bearish surprise → negative signal.

Indicators tracked:
  - Employment: Initial claims (ICSA), unemployment (UNRATE)
  - Activity: Industrial production (INDPRO), manufacturing employment (MANEMP)
  - Inflation: CPI (CPIAUCSL)
  - Financial: NFCI, credit spreads (BAMLH0A0HYM2)
  - Sentiment: Consumer sentiment (UMCSENT)

Usage:
    from backend.services.economic_surprise import (
        compute_surprise_index, get_indicator_surprises
    )
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from backend.config import config, api_keys

logger = logging.getLogger(__name__)

# Indicators and whether higher is "good" (positive surprise = bullish)
# For inverted indicators (like unemployment, claims), higher = bearish
_INDICATORS = {
    "ICSA": {"name": "Initial Jobless Claims", "inverted": True, "weight": 1.5},
    "UNRATE": {"name": "Unemployment Rate", "inverted": True, "weight": 1.0},
    "INDPRO": {"name": "Industrial Production", "inverted": False, "weight": 1.2},
    "MANEMP": {"name": "Manufacturing Employment", "inverted": False, "weight": 0.8},
    "CPIAUCSL": {"name": "Consumer Price Index", "inverted": True, "weight": 0.8},
    "NFCI": {"name": "Chicago Fed NFCI", "inverted": True, "weight": 1.3},
    "BAMLH0A0HYM2": {"name": "High Yield Spread", "inverted": True, "weight": 1.2},
    "UMCSENT": {"name": "Consumer Sentiment", "inverted": False, "weight": 1.0},
}

# Rolling window for trend estimation (consensus proxy)
_TREND_WINDOW = 12  # 12 periods (months for monthly, weeks for weekly)
_LOOKBACK_YEARS = 3


def _fetch_fred_series(series_id: str) -> Optional[pd.Series]:
    """Fetch a FRED series. Returns None on failure."""
    try:
        from fredapi import Fred
        fred_key = api_keys.fred
        if not fred_key:
            return None
        fred = Fred(api_key=fred_key)
        # Dynamic start date based on lookback config (was hardcoded to "2020-01-01",
        # which caused the trend window to include increasingly stale data over time)
        start_date = (pd.Timestamp.now() - pd.DateOffset(years=_LOOKBACK_YEARS + 1)).strftime("%Y-%m-%d")
        data = fred.get_series(series_id, observation_start=start_date)
        if data is not None and not data.empty:
            return data.dropna()
        return None
    except Exception as e:
        logger.warning("Failed to fetch FRED series %s: %s", series_id, e)
        return None


def compute_surprise_index() -> Optional[dict]:
    """Compute composite economic surprise index from FRED data.

    Returns:
        Dictionary with:
          - composite_score: -1.0 (bearish surprises) to +1.0 (bullish surprises)
          - signal: "bullish_surprise" / "bearish_surprise" / "neutral"
          - indicators: per-indicator surprise details
          - trend: "improving" / "deteriorating" / "stable"
    """
    indicator_surprises = []

    for series_id, meta in _INDICATORS.items():
        data = _fetch_fred_series(series_id)
        if data is None or len(data) < _TREND_WINDOW + 2:
            continue

        # Compute trend (rolling median as consensus proxy)
        trend = data.rolling(_TREND_WINDOW, min_periods=max(3, _TREND_WINDOW // 2)).median()

        # Latest value vs trend
        latest = float(data.iloc[-1])
        trend_val = float(trend.iloc[-1]) if not np.isnan(trend.iloc[-1]) else float(trend.dropna().iloc[-1])

        if trend_val == 0:
            surprise_pct = 0.0
        else:
            surprise_pct = (latest - trend_val) / abs(trend_val) * 100

        # For inverted indicators, flip the sign
        if meta["inverted"]:
            surprise_pct = -surprise_pct

        # Normalize to [-1, 1] range (±10% surprise maps to ±1)
        surprise_normalized = float(np.clip(surprise_pct / 10.0, -1.0, 1.0))

        # 3-month surprise trend (are surprises getting better or worse?)
        if len(data) >= _TREND_WINDOW + 6:
            recent_surprises = []
            for i in range(-6, 0):
                if i + len(data) >= _TREND_WINDOW:
                    val = float(data.iloc[i])
                    tr = float(trend.iloc[i]) if not np.isnan(trend.iloc[i]) else np.nan
                    if not np.isnan(tr) and tr != 0:
                        s = (val - tr) / abs(tr) * 100
                        if meta["inverted"]:
                            s = -s
                        recent_surprises.append(s)
            surprise_trend = np.mean(recent_surprises) if recent_surprises else 0.0
        else:
            surprise_trend = 0.0

        indicator_surprises.append({
            "series_id": series_id,
            "name": meta["name"],
            "latest_value": round(latest, 2),
            "trend_value": round(trend_val, 2),
            "surprise_pct": round(surprise_pct, 2),
            "surprise_normalized": round(surprise_normalized, 3),
            "weight": meta["weight"],
            "weighted_surprise": round(surprise_normalized * meta["weight"], 3),
            "surprise_trend": round(surprise_trend, 2),
        })

    if not indicator_surprises:
        return None

    # Composite weighted surprise score
    total_weight = sum(i["weight"] for i in indicator_surprises)
    if total_weight > 0:
        composite = sum(i["weighted_surprise"] for i in indicator_surprises) / total_weight
    else:
        composite = 0.0

    composite = float(np.clip(composite, -1.0, 1.0))

    # Determine signal
    if composite > 0.15:
        signal = "bullish_surprise"
    elif composite < -0.15:
        signal = "bearish_surprise"
    else:
        signal = "neutral"

    # Trend: are surprises improving or deteriorating over last 3 months?
    avg_trend = np.mean([i["surprise_trend"] for i in indicator_surprises])
    if avg_trend > 1.0:
        trend = "improving"
    elif avg_trend < -1.0:
        trend = "deteriorating"
    else:
        trend = "stable"

    # Count positive vs negative surprises
    n_positive = sum(1 for i in indicator_surprises if i["surprise_normalized"] > 0.05)
    n_negative = sum(1 for i in indicator_surprises if i["surprise_normalized"] < -0.05)

    return {
        "composite_score": round(composite, 3),
        "signal": signal,
        "trend": trend,
        "indicators_tracked": len(indicator_surprises),
        "positive_surprises": n_positive,
        "negative_surprises": n_negative,
        "breadth": round(n_positive / len(indicator_surprises), 2) if indicator_surprises else 0,
        "indicators": sorted(indicator_surprises, key=lambda x: abs(x["weighted_surprise"]), reverse=True),
    }


def get_indicator_surprises() -> list[dict]:
    """Get individual indicator surprises for dashboard display."""
    result = compute_surprise_index()
    if result is None:
        return []
    return result.get("indicators", [])
