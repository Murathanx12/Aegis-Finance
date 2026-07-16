"""
Aegis Finance — Analyst Intelligence (Wall Street consensus per ticker)
=======================================================================

The Bloomberg-ANR-shaped view retail apps clone: consensus price targets
(low/mean/median/high + implied upside), the monthly Strong Buy→Strong Sell
recommendation trend, the 1-5 consensus rating, and the firm-attributed
upgrade/downgrade feed (JP Morgan, Goldman Sachs, ... with from→to grades).

Data source: Yahoo Finance via yfinance — consensus/estimates originate from
S&P Global Market Intelligence and the upgrades/downgrades feed from Benzinga
(Yahoo's licensed providers; we attribute "via Yahoo Finance" in responses).
All fields are OPTIONAL: any fetch/parse failure degrades that field to None,
never raises past the public functions.

This is DISPLAY intelligence, not a signal source — nothing here feeds the
paper lanes or the signal engine write-paths.
"""

import logging
from typing import Optional

from backend.cache import cached
from backend.config import config

logger = logging.getLogger(__name__)

# Benzinga "Action" codes → what the UI should say
_ACTION_LABELS = {
    "up": "upgrade",
    "down": "downgrade",
    "init": "initiated",
    "main": "maintained",
    "reit": "reiterated",
}


def _implied_upside(target: Optional[float], current: Optional[float]) -> Optional[float]:
    if not target or not current or current <= 0:
        return None
    return round((target / current - 1) * 100, 2)


def _price_target_block(stock) -> Optional[dict]:
    """analyst_price_targets → {current, low, mean, median, high, upside_pct}."""
    try:
        t = stock.analyst_price_targets
        if not isinstance(t, dict) or not t:
            return None
        current = t.get("current")
        mean = t.get("mean")
        return {
            "current_price": current,
            "low": t.get("low"),
            "mean": mean,
            "median": t.get("median"),
            "high": t.get("high"),
            "upside_pct": _implied_upside(mean, current),
        }
    except Exception as e:
        logger.debug("%s: price-target block failed — %s", getattr(stock, "ticker", "?"), e)
        return None


def _recommendation_trend(stock) -> Optional[list]:
    """recommendations → monthly [{period, strongBuy, buy, hold, sell, strongSell, total}]."""
    try:
        rec = stock.recommendations
        if rec is None or not hasattr(rec, "iterrows") or rec.empty:
            return None
        trend = []
        for _, row in rec.iterrows():
            counts = {k: int(row.get(k, 0) or 0)
                      for k in ("strongBuy", "buy", "hold", "sell", "strongSell")}
            trend.append({
                "period": str(row.get("period", "")),
                **counts,
                "total": sum(counts.values()),
            })
        return trend or None
    except Exception as e:
        logger.debug("%s: recommendation trend failed — %s", getattr(stock, "ticker", "?"), e)
        return None


def _consensus_rating(info: dict) -> Optional[dict]:
    """info → {score (1=Strong Buy … 5=Sell, Yahoo convention), label, n_analysts}."""
    try:
        score = info.get("recommendationMean")
        key = info.get("recommendationKey")
        n = info.get("numberOfAnalystOpinions")
        if score is None and key is None:
            return None
        return {
            "score": round(float(score), 2) if score is not None else None,
            "label": str(key).replace("_", " ") if key else None,
            "n_analysts": int(n) if n is not None else None,
            "scale": "1 = Strong Buy … 5 = Sell (Yahoo convention)",
        }
    except Exception as e:
        logger.debug("consensus rating parse failed — %s", e)
        return None


def _upgrades_downgrades(stock, max_items: int, lookback_days: int) -> Optional[list]:
    """upgrades_downgrades → firm-attributed actions, most recent first."""
    try:
        import pandas as pd
        df = stock.upgrades_downgrades
        if df is None or not hasattr(df, "iterrows") or df.empty:
            return None
        df = df.sort_index(ascending=False)
        cutoff = pd.Timestamp.now(tz=df.index.tz) - pd.Timedelta(days=lookback_days)
        items = []
        for date, row in df.iterrows():
            if date < cutoff or len(items) >= max_items:
                break
            action = str(row.get("Action", "") or "").lower()
            items.append({
                "date": str(date.date()) if hasattr(date, "date") else str(date),
                "firm": str(row.get("Firm", "") or ""),
                "from_grade": str(row.get("FromGrade", "") or "") or None,
                "to_grade": str(row.get("ToGrade", "") or "") or None,
                "action": _ACTION_LABELS.get(action, action or None),
            })
        return items or None
    except Exception as e:
        logger.debug("%s: upgrades/downgrades failed — %s", getattr(stock, "ticker", "?"), e)
        return None


@cached(ttl=config["cache"].get("ttl_sectors", 3600), key_prefix="analyst_intel")
def get_analyst_intelligence(ticker: str) -> Optional[dict]:
    """Full analyst view for one ticker. None only when NO field is available
    (unknown symbol / total fetch failure) — partial data returns with the
    missing fields as None, disclosed by the `available` flags.
    """
    import yfinance as yf
    from backend.services.data_fetcher import fetch_ticker_info

    ticker = ticker.upper()
    stock = yf.Ticker(ticker)  # lazy handle — network happens per property
    try:
        info = fetch_ticker_info(ticker) or {}
    except Exception:
        info = {}

    ai_cfg = config.get("analyst_intelligence", {})
    targets = _price_target_block(stock)
    trend = _recommendation_trend(stock)
    rating = _consensus_rating(info)
    actions = _upgrades_downgrades(
        stock,
        max_items=ai_cfg.get("max_actions", 30),
        lookback_days=ai_cfg.get("actions_lookback_days", 365),
    )

    if targets is None and trend is None and rating is None and actions is None:
        return None

    return {
        "ticker": ticker,
        "price_targets": targets,
        "recommendation_trend": trend,
        "consensus_rating": rating,
        "recent_actions": actions,
        "attribution": (
            "Analyst data via Yahoo Finance (consensus: S&P Global Market "
            "Intelligence; ratings actions: Benzinga). Informational only — "
            "not investment advice."
        ),
    }
