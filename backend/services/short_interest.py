"""
Aegis Finance — Short Interest & Squeeze Signal
==================================================

Surface short-side positioning that retail tools usually bury:
  - Shares short, float shorted %, days to cover (shares short / avg daily volume)
  - Short squeeze score (composite of high short %, low days to cover, high momentum)
  - Regime label (low/moderate/high/extreme)

Primary source: yfinance `.info` (free). Finnhub short-interest bulk data
is available when FINNHUB_API_KEY is set but is not required — yfinance
alone gives the latest bi-monthly FINRA snapshot.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


def _classify_short_regime(short_pct_float: Optional[float], days_to_cover: Optional[float]) -> str:
    """Classify short interest intensity using float% and cover days.

    Combines both because either alone is misleading:
      - 30% shorted but 1 day to cover → easy to unwind, not a squeeze setup
      - 2% shorted but 20 days to cover → thin liquidity, can still move violently
    """
    if short_pct_float is None:
        return "unknown"
    pct = float(short_pct_float)
    if pct >= 0.20 and (days_to_cover is None or days_to_cover >= 5):
        return "extreme"
    if pct >= 0.10:
        return "high"
    if pct >= 0.05:
        return "moderate"
    return "low"


def _squeeze_score(short_pct_float: Optional[float],
                   days_to_cover: Optional[float],
                   momentum_3m: Optional[float]) -> Optional[float]:
    """Composite 0-100 squeeze risk.

    Weighting: 50% float shorted, 30% days to cover, 20% positive momentum.
    Positive momentum matters because shorts covering amplifies rallies.
    """
    parts: list[tuple[float, float]] = []
    if short_pct_float is not None:
        parts.append((0.5, float(np.clip(short_pct_float / 0.30, 0.0, 1.0))))
    if days_to_cover is not None:
        parts.append((0.3, float(np.clip(days_to_cover / 10.0, 0.0, 1.0))))
    if momentum_3m is not None:
        parts.append((0.2, float(np.clip(momentum_3m / 0.30, 0.0, 1.0))))
    if not parts:
        return None
    total_weight = sum(w for w, _ in parts)
    if total_weight <= 0:
        return None
    score = sum(w * v for w, v in parts) / total_weight * 100.0
    return round(float(score), 1)


def _pull_yf_info(ticker: str) -> Optional[dict]:
    """Read short-related fields from yfinance. Returns None if unavailable."""
    try:
        import yfinance as yf
    except ImportError:
        return None

    try:
        info = yf.Ticker(ticker).info or {}
    except Exception as e:
        logger.debug("yfinance .info failed for %s: %s", ticker, e)
        return None

    if not info:
        return None

    return {
        "shares_short": info.get("sharesShort"),
        "shares_short_prior_month": info.get("sharesShortPriorMonth"),
        "short_ratio": info.get("shortRatio"),             # days-to-cover per Yahoo
        "short_percent_float": info.get("shortPercentOfFloat"),
        "short_percent_outstanding": info.get("shortPercentOfSharesOutstanding"),
        "float_shares": info.get("floatShares"),
        "shares_outstanding": info.get("sharesOutstanding"),
        "avg_volume": info.get("averageDailyVolume10Day") or info.get("averageVolume"),
        "last_price": info.get("regularMarketPrice") or info.get("currentPrice"),
        "name": info.get("shortName", ticker),
    }


def _momentum_3m(ticker: str) -> Optional[float]:
    """Fetch a rough 3-month total return for squeeze scoring. Tolerates network failure."""
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        hist = yf.Ticker(ticker).history(period="3mo", auto_adjust=True)
    except Exception:
        return None
    if hist is None or hist.empty or "Close" not in hist.columns:
        return None
    closes = hist["Close"].dropna()
    if len(closes) < 2:
        return None
    return float(closes.iloc[-1] / closes.iloc[0] - 1.0)


def get_short_interest(ticker: str) -> Optional[dict]:
    """Return short interest snapshot + squeeze diagnostics for a ticker."""
    info = _pull_yf_info(ticker)
    if info is None:
        return None

    short_pct = info.get("short_percent_float") or info.get("short_percent_outstanding")
    days_to_cover = info.get("short_ratio")
    # yfinance already expresses dollar ratio; nothing to recompute there

    # Month-over-month short change, if we have the prior snapshot
    mom_change = None
    if info.get("shares_short") and info.get("shares_short_prior_month"):
        try:
            prior = float(info["shares_short_prior_month"])
            current = float(info["shares_short"])
            if prior > 0:
                mom_change = round((current / prior - 1.0) * 100.0, 2)
        except (TypeError, ValueError):
            pass

    momentum = _momentum_3m(ticker)
    squeeze = _squeeze_score(short_pct, days_to_cover, momentum)
    regime = _classify_short_regime(short_pct, days_to_cover)

    return {
        "ticker": ticker,
        "name": info.get("name"),
        "shares_short": info.get("shares_short"),
        "shares_short_prior_month": info.get("shares_short_prior_month"),
        "short_percent_float": short_pct,
        "days_to_cover": days_to_cover,
        "float_shares": info.get("float_shares"),
        "avg_daily_volume_10d": info.get("avg_volume"),
        "month_over_month_change_pct": mom_change,
        "momentum_3m": momentum,
        "squeeze_score_0_100": squeeze,
        "regime": regime,
        "source": "yfinance (FINRA bi-monthly)",
    }
