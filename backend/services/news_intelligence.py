"""
Aegis Finance — News Intelligence Service
============================================

GDELT-powered news sentiment analysis + yfinance stock news.
No API key required for GDELT (free, 15-min updates).

Adapted from V7 intelligence/gdelt_fetcher.py + event_scorer.py.

Usage:
    from backend.services.news_intelligence import (
        fetch_gdelt_signals, fetch_stock_news,
        compute_event_score, adjust_crash_probability,
    )
"""

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

_GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"


def fetch_gdelt_signals(query: str = "market OR economy OR financial", days: int = 30) -> dict:
    """Fetch GDELT news sentiment signals.

    Returns:
        Dict with avg_tone, tone_trend, volume_zscore, conflict_score, raw_data
    """
    if not _HAS_REQUESTS:
        return _gdelt_fallback("requests library not available")

    try:
        tone_data = _fetch_tone_timeline(query, days)
        volume_data = _fetch_volume_timeline(query, days)
        conflict_data = _fetch_conflict_timeline(days)

        # Compute summary stats
        avg_tone = 0.0
        tone_trend = 0.0
        if tone_data and len(tone_data) > 0:
            tones = [float(t) for t in tone_data]
            avg_tone = float(np.mean(tones[-7:])) if len(tones) >= 7 else float(np.mean(tones))
            if len(tones) >= 14:
                recent = np.mean(tones[-7:])
                earlier = np.mean(tones[-14:-7])
                tone_trend = float(recent - earlier)

        volume_zscore = 0.0
        if volume_data and len(volume_data) > 7:
            volumes = [float(v) for v in volume_data]
            vol_mean = np.mean(volumes[:-7])
            vol_std = np.std(volumes[:-7])
            if vol_std > 0:
                recent_vol = np.mean(volumes[-7:])
                volume_zscore = float((recent_vol - vol_mean) / vol_std)

        conflict_score = 0.0
        if conflict_data and len(conflict_data) > 0:
            conflicts = [float(c) for c in conflict_data]
            recent_conflict = np.mean(conflicts[-7:]) if len(conflicts) >= 7 else np.mean(conflicts)
            max_conflict = max(conflicts) if conflicts else 1
            conflict_score = float(np.clip(recent_conflict / max(max_conflict, 1), 0, 1))

        return {
            "avg_tone": round(avg_tone, 3),
            "tone_trend": round(tone_trend, 3),
            "volume_zscore": round(volume_zscore, 2),
            "conflict_score": round(conflict_score, 3),
            "raw_data": {
                "tone": tone_data[-30:] if tone_data else [],
                "volume": volume_data[-30:] if volume_data else [],
                "conflict": conflict_data[-30:] if conflict_data else [],
            },
            "success": True,
        }

    except Exception as e:
        logger.warning("GDELT fetch failed: %s", e)
        return _gdelt_fallback(str(e))


def _fetch_tone_timeline(query: str, days: int) -> list:
    """Fetch daily news tone from GDELT DOC API."""
    params = {
        "query": query,
        "mode": "timelinetone",
        "timespan": f"{days}d",
        "format": "json",
    }
    resp = requests.get(_GDELT_DOC_API, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    timeline = data.get("timeline", [])
    if timeline and isinstance(timeline, list):
        series = timeline[0].get("data", [])
        return [entry.get("value", 0) for entry in series]
    return []


def _fetch_volume_timeline(query: str, days: int) -> list:
    """Fetch daily article volume from GDELT DOC API."""
    params = {
        "query": query,
        "mode": "timelinevolraw",
        "timespan": f"{days}d",
        "format": "json",
    }
    resp = requests.get(_GDELT_DOC_API, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    timeline = data.get("timeline", [])
    if timeline and isinstance(timeline, list):
        series = timeline[0].get("data", [])
        return [entry.get("value", 0) for entry in series]
    return []


def _fetch_conflict_timeline(days: int) -> list:
    """Fetch geopolitical conflict article volume."""
    params = {
        "query": "conflict OR war OR sanctions OR military OR geopolitical",
        "mode": "timelinevolraw",
        "timespan": f"{days}d",
        "format": "json",
    }
    resp = requests.get(_GDELT_DOC_API, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    timeline = data.get("timeline", [])
    if timeline and isinstance(timeline, list):
        series = timeline[0].get("data", [])
        return [entry.get("value", 0) for entry in series]
    return []


def _gdelt_fallback(reason: str) -> dict:
    return {
        "avg_tone": 0.0,
        "tone_trend": 0.0,
        "volume_zscore": 0.0,
        "conflict_score": 0.0,
        "raw_data": {"tone": [], "volume": [], "conflict": []},
        "success": False,
        "error": reason,
    }


def fetch_stock_news(ticker: str, max_items: int = 10) -> list[dict]:
    """Fetch recent news for a stock ticker from yfinance.

    Returns:
        List of {title, publisher, link, published, type}
    """
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        raw_news = stock.news or []

        news_items = []
        for item in raw_news[:max_items]:
            content = item.get("content", item)
            news_items.append({
                "title": content.get("title", item.get("title", "")),
                "publisher": content.get("provider", {}).get("displayName", "") if isinstance(content.get("provider"), dict) else item.get("publisher", ""),
                "link": content.get("canonicalUrl", {}).get("url", "") if isinstance(content.get("canonicalUrl"), dict) else item.get("link", ""),
                "published": content.get("pubDate", item.get("providerPublishTime", "")),
                "type": content.get("contentType", item.get("type", "article")),
            })
        return news_items

    except Exception as e:
        logger.warning("Failed to fetch news for %s: %s", ticker, e)
        return []


def compute_event_score(
    gdelt_signals: dict,
    fred_gpr: Optional[float] = None,
) -> dict:
    """Compute composite event risk score from GDELT + FRED GPR.

    Weights:
        - GDELT tone: 40%
        - GDELT volume spike: 30%
        - FRED GPR (geopolitical risk): 30%

    Returns:
        Dict with event_score, components, interpretation
    """
    # Tone score: negative tone = higher risk
    tone = gdelt_signals.get("avg_tone", 0)
    tone_score = float(np.clip(((-tone) + 5) / 10, 0, 1))  # Map [-5,5] -> [0,1]

    # Volume score: higher z-score = more unusual = higher risk
    vol_z = gdelt_signals.get("volume_zscore", 0)
    volume_score = float(np.clip(vol_z / 3, 0, 1))  # Z>3 = max risk

    # GPR score
    gpr_score = 0.3  # neutral default
    if fred_gpr is not None:
        gpr_score = float(np.clip(fred_gpr / 300, 0, 1))  # GPR 0-300 range

    # Weighted composite
    weights = {"tone": 0.40, "volume": 0.30, "gpr": 0.30}
    event_score = (
        weights["tone"] * tone_score
        + weights["volume"] * volume_score
        + weights["gpr"] * gpr_score
    )

    # Convergence bonus: +15% per elevated signal when 2+ fire
    elevated = sum(1 for s in [tone_score, volume_score, gpr_score] if s > 0.5)
    if elevated >= 2:
        event_score = min(1.0, event_score * (1 + 0.15 * (elevated - 1)))

    event_score = float(np.clip(event_score, 0, 1))

    # Interpretation
    if event_score > 0.75:
        interpretation = "Critical — multiple risk signals converging"
    elif event_score > 0.50:
        interpretation = "Elevated — significant event risk detected"
    elif event_score > 0.30:
        interpretation = "Moderate — some risk signals present"
    else:
        interpretation = "Low — no significant event risk"

    return {
        "event_score": round(event_score, 3),
        "components": {
            "tone_score": round(tone_score, 3),
            "volume_score": round(volume_score, 3),
            "gpr_score": round(gpr_score, 3),
        },
        "interpretation": interpretation,
        "regime_override": "Crisis" if event_score > 0.75 else None,
    }


def adjust_crash_probability(base_prob: float, event_score: float) -> float:
    """Adjust ML crash probability with event score.

    Max adjustment: +30% multiplicative boost.
    Only increases crash probability, never decreases.
    """
    if event_score <= 0.3:
        return base_prob

    adjustment = 1.0 + min(event_score * 0.4, 0.30)
    adjusted = base_prob * adjustment
    return float(np.clip(adjusted, base_prob, 0.95))
