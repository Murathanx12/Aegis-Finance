"""
Aegis Finance — Google Trends Sentiment Proxy
================================================

Uses Google Trends search volume as an alternative sentiment/attention indicator.
Research shows retail search interest correlates with:
  - Buying pressure (Da, Engelberg & Gao, 2011 — "In Search of Attention")
  - Volatility spikes (Vlastakis & Markellos, 2012)
  - Retail sentiment extremes (Joseph, Wintoki & Zhang, 2011)

Key indicators:
  - Search Volume Index (SVI): Normalized 0-100 search interest
  - SVI Z-score: How unusual is current search volume vs history?
  - Fear terms: "stock market crash", "recession", "bear market"
  - Greed terms: "buy stocks", "best stocks to buy", "stock tips"
  - Fear-Greed Ratio: Relative attention to fear vs greed terms

Limitations:
  - Google Trends API is rate-limited and sometimes returns partial data
  - Weekly granularity (not daily)
  - Regional bias (US-centric)

Usage:
    from backend.services.trends_sentiment import (
        compute_fear_greed_trends, get_ticker_attention
    )
"""

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


# Fear and greed search terms (Google Trends keywords)
FEAR_TERMS = [
    "stock market crash",
    "recession",
    "bear market",
    "market crash",
    "sell stocks",
]

GREED_TERMS = [
    "buy stocks",
    "best stocks to buy",
    "stock tips",
    "bull market",
    "invest now",
]


# Google blocks datacenter IPs aggressively; from Railway pytrends fails ~always.
# After a failure we COOL DOWN instead of re-hammering every warm cycle: one
# loud warning on entry, then quiet fast-fails until the cooldown expires.
# The signal is disclosed as unavailable (None) downstream — never neutral-faked.
_TRENDS_COOLDOWN_S = 6 * 3600
_TRENDS_COOLDOWN_KEY = "trends:blocked"


def _in_cooldown() -> bool:
    try:
        from backend.cache import cache_get
        return cache_get(_TRENDS_COOLDOWN_KEY, _TRENDS_COOLDOWN_S) is not None
    except Exception:
        return False


def _enter_cooldown(reason: str) -> None:
    try:
        from backend.cache import cache_set
        cache_set(_TRENDS_COOLDOWN_KEY, {"reason": reason})
        logger.warning(
            "Google Trends unavailable (%s) — cooling down %dh; fear/greed "
            "signal disclosed as unavailable until then", reason,
            _TRENDS_COOLDOWN_S // 3600,
        )
    except Exception:
        logger.warning("Google Trends unavailable (%s)", reason)


def _fetch_trends(keywords: list[str], timeframe: str = "today 3-m") -> Optional[dict]:
    """Fetch Google Trends data for keywords.

    Returns dict of {keyword: latest_value} or None on failure.
    """
    if _in_cooldown():
        logger.debug("Google Trends in failure cooldown — skipping fetch")
        return None
    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="en-US", tz=360, timeout=(10, 25))
        pytrends.build_payload(keywords[:5], timeframe=timeframe, geo="US")

        interest = pytrends.interest_over_time()
        if interest.empty:
            return None

        # Get latest values
        result = {}
        for kw in keywords[:5]:
            if kw in interest.columns:
                vals = interest[kw].dropna()
                if len(vals) > 0:
                    result[kw] = {
                        "current": int(vals.iloc[-1]),
                        "mean": round(float(vals.mean()), 1),
                        "max": int(vals.max()),
                        "zscore": round(
                            float(
                                (vals.iloc[-1] - vals.mean())
                                / max(vals.std(), 0.01)
                            ),
                            2,
                        ),
                    }

        return result

    except ImportError:
        _enter_cooldown("pytrends not installed")
        return None
    except Exception as e:
        _enter_cooldown(f"fetch failed: {e}")
        return None


def compute_fear_greed_trends(timeframe: str = "today 3-m") -> Optional[dict]:
    """Compute Fear/Greed ratio from Google Trends search volume.

    Returns:
        Dict with fear_score, greed_score, ratio, and interpretation.
    """
    # Fetch fear terms
    fear_data = _fetch_trends(FEAR_TERMS, timeframe)
    greed_data = _fetch_trends(GREED_TERMS, timeframe)

    if not fear_data and not greed_data:
        return None

    # Need both sides for a meaningful ratio; one-sided data is unreliable
    if not fear_data or not greed_data:
        available = fear_data or greed_data
        return {
            "sentiment": "neutral",
            "signal": 0.0,
            "fear_greed_ratio": 0.0,
            "avg_fear_zscore": 0.0,
            "avg_greed_zscore": 0.0,
            "fear_terms": fear_data or {},
            "greed_terms": greed_data or {},
            "interpretation": "Incomplete data (only fear or greed terms available). Cannot compute ratio.",
        }

    # Compute aggregate scores
    fear_score = 0.0
    fear_count = 0
    if fear_data:
        for kw, data in fear_data.items():
            fear_score += data["zscore"]
            fear_count += 1

    greed_score = 0.0
    greed_count = 0
    if greed_data:
        for kw, data in greed_data.items():
            greed_score += data["zscore"]
            greed_count += 1

    avg_fear = fear_score / max(fear_count, 1)
    avg_greed = greed_score / max(greed_count, 1)

    # Fear-Greed ratio: positive = more fear than greed
    fg_ratio = avg_fear - avg_greed

    # Signal: -1 (extreme fear/bearish attention) to +1 (extreme greed/bullish attention)
    # Contrarian interpretation: high fear = potential buying opportunity
    signal = float(np.clip(-fg_ratio * 0.3, -1, 1))

    # Classification
    if fg_ratio > 1.5:
        sentiment = "extreme_fear"
        interpretation = "Extreme fear in search trends. Historically a contrarian buy signal."
    elif fg_ratio > 0.5:
        sentiment = "fear"
        interpretation = "Elevated fear in search trends. Caution warranted but may present opportunities."
    elif fg_ratio < -1.5:
        sentiment = "extreme_greed"
        interpretation = "Extreme greed/FOMO in search trends. Historically a contrarian sell signal."
    elif fg_ratio < -0.5:
        sentiment = "greed"
        interpretation = "Elevated greed in search trends. Markets may be overextended."
    else:
        sentiment = "neutral"
        interpretation = "Neutral search sentiment. No extreme attention signals."

    return {
        "sentiment": sentiment,
        "signal": round(signal, 3),
        "fear_greed_ratio": round(fg_ratio, 3),
        "avg_fear_zscore": round(avg_fear, 3),
        "avg_greed_zscore": round(avg_greed, 3),
        "fear_terms": fear_data or {},
        "greed_terms": greed_data or {},
        "interpretation": interpretation,
    }


def get_ticker_attention(
    ticker: str,
    company_name: Optional[str] = None,
    timeframe: str = "today 3-m",
) -> Optional[dict]:
    """Get search attention for a specific stock.

    High attention spikes often precede volatility.
    """
    keywords = [f"{ticker} stock"]
    if company_name:
        keywords.append(company_name)

    data = _fetch_trends(keywords, timeframe)
    if not data:
        return None

    # Get the primary keyword's data
    primary = data.get(keywords[0], {})
    zscore = primary.get("zscore", 0)

    # Attention classification
    if zscore > 2.0:
        level = "extreme"
        interpretation = f"{ticker} is getting unusually high search attention. Expect elevated volatility."
    elif zscore > 1.0:
        level = "elevated"
        interpretation = f"{ticker} search interest is above normal. Retail attention is increasing."
    elif zscore < -1.0:
        level = "low"
        interpretation = f"{ticker} search interest is below normal. Low retail attention."
    else:
        level = "normal"
        interpretation = f"{ticker} search interest is within normal range."

    return {
        "ticker": ticker,
        "attention_level": level,
        "attention_zscore": zscore,
        "data": data,
        "interpretation": interpretation,
    }
