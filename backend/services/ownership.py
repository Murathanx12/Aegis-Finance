"""
Aegis Finance — Institutional Ownership & ETF Look-through
==============================================================

Two free-data moats that most retail dashboards skip:

1. `get_institutional_ownership(ticker)`: "Who owns this ticker?" —
   top 10 institutional holders with share count, value, QoQ change,
   and a crowding score derived from combined institutional float.
2. `get_etf_lookthrough(ticker)`: "What am I really exposed to?" —
   an ETF's top holdings + sector weights, so a user who owns SPY+QQQ
   can see real single-name concentration.

Data source: yfinance (which aggregates SEC 13F + N-PORT filings via
Yahoo's data pipeline). Free, no extra API key.
"""

from __future__ import annotations

import logging
from typing import Optional

from backend.cache import cache_get, cache_set

logger = logging.getLogger(__name__)


# ── Institutional ownership ──────────────────────────────────────────────────


def get_institutional_ownership(ticker: str) -> Optional[dict]:
    """Top-10 institutional holders + crowding assessment."""
    ticker = ticker.upper()
    cache_key = f"ownership:{ticker}"
    cached = cache_get(cache_key, 86400)  # 24h cache
    if cached is not None:
        return cached

    try:
        import yfinance as yf
    except ImportError:
        return None

    try:
        t = yf.Ticker(ticker)
        inst = t.institutional_holders
        major = t.major_holders
    except Exception as e:
        logger.debug("ownership fetch failed for %s: %s", ticker, e)
        return None

    holders = []
    if inst is not None and len(inst) > 0:
        for _, row in inst.iterrows():
            holders.append(
                {
                    "holder": _safe_str(row.get("Holder")),
                    "shares": _safe_int(row.get("Shares")),
                    "value": _safe_float(row.get("Value")),
                    "pct_held": _safe_float(row.get("pctHeld")),
                    "pct_change": _safe_float(row.get("pctChange")),
                    "date_reported": _safe_str(row.get("Date Reported")),
                }
            )

    ownership_summary: dict = {}
    if major is not None and len(major) > 0:
        try:
            # major_holders is a 2-col frame with breakdown keys
            val_col = major.columns[0]
            for idx, val in major[val_col].items():
                ownership_summary[str(idx)] = _safe_float(val)
        except Exception:
            pass

    # Crowding: combined % held by top 10 institutions vs historical norm.
    # High crowding = crowded trade (potential sell-off cascade risk).
    top_pct_sum = sum(
        (h.get("pct_held") or 0) for h in holders if h.get("pct_held") is not None
    )
    if top_pct_sum >= 0.45:
        crowding = "very_high"
        crowding_note = "Top-10 institutions hold >45% — crowded, higher liquidation risk"
    elif top_pct_sum >= 0.30:
        crowding = "high"
        crowding_note = "Top-10 institutions hold 30-45% — meaningful concentration"
    elif top_pct_sum >= 0.15:
        crowding = "moderate"
        crowding_note = "Top-10 institutions hold 15-30% — typical large-cap concentration"
    else:
        crowding = "low"
        crowding_note = "Top-10 institutions hold <15% — diversified ownership"

    # QoQ-style summary: count net buyers vs sellers in most recent quarter
    recent_buyers = sum(1 for h in holders if (h.get("pct_change") or 0) > 0.01)
    recent_sellers = sum(1 for h in holders if (h.get("pct_change") or 0) < -0.01)

    result = {
        "ticker": ticker,
        "holders": holders[:10],
        "summary": ownership_summary,
        "crowding": {
            "level": crowding,
            "top10_pct_held": round(top_pct_sum, 4),
            "note": crowding_note,
        },
        "recent_activity": {
            "buyers_top10": recent_buyers,
            "sellers_top10": recent_sellers,
            "net_signal": (
                "accumulating" if recent_buyers > recent_sellers
                else "distributing" if recent_sellers > recent_buyers
                else "neutral"
            ),
        },
        "source": "yfinance",
    }
    cache_set(cache_key, result)
    return result


# ── ETF look-through ─────────────────────────────────────────────────────────


def get_etf_lookthrough(ticker: str) -> Optional[dict]:
    """Top holdings + sector weights for an ETF. Returns None for non-ETFs."""
    ticker = ticker.upper()
    cache_key = f"etf_lookthrough:{ticker}"
    cached = cache_get(cache_key, 86400)
    if cached is not None:
        return cached

    try:
        import yfinance as yf
    except ImportError:
        return None

    try:
        t = yf.Ticker(ticker)
        funds = t.funds_data
    except Exception as e:
        logger.debug("etf lookthrough fetch failed for %s: %s", ticker, e)
        return None

    if funds is None:
        return None

    top_holdings = []
    try:
        th = getattr(funds, "top_holdings", None)
        if th is not None and len(th) > 0:
            for symbol, row in th.iterrows():
                top_holdings.append(
                    {
                        "symbol": str(symbol),
                        "name": _safe_str(row.get("Name")),
                        "weight": _safe_float(row.get("Holding Percent")),
                    }
                )
    except Exception as e:
        logger.debug("top_holdings extract failed: %s", e)

    sector_weights = {}
    try:
        sw = getattr(funds, "sector_weightings", None)
        if isinstance(sw, dict):
            sector_weights = {k: _safe_float(v) for k, v in sw.items() if v is not None}
    except Exception:
        pass

    # Not an ETF (or data missing) — bail out clearly
    if not top_holdings and not sector_weights:
        return None

    # Concentration metrics
    top5 = sum((h.get("weight") or 0) for h in top_holdings[:5])
    top10 = sum((h.get("weight") or 0) for h in top_holdings[:10])

    if top10 >= 0.50:
        concentration = "very_high"
    elif top10 >= 0.30:
        concentration = "high"
    elif top10 >= 0.15:
        concentration = "moderate"
    else:
        concentration = "low"

    result = {
        "ticker": ticker,
        "top_holdings": top_holdings,
        "sector_weights": sector_weights,
        "concentration": {
            "top5_pct": round(top5, 4),
            "top10_pct": round(top10, 4),
            "level": concentration,
        },
        "source": "yfinance",
    }
    cache_set(cache_key, result)
    return result


# ── Helpers ──────────────────────────────────────────────────────────────────


def _safe_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        import pandas as pd
        if pd.isna(v):
            return None
    except Exception:
        pass
    try:
        f = float(v)
        if f != f:
            return None
        return f
    except (TypeError, ValueError):
        return None


def _safe_int(v) -> Optional[int]:
    f = _safe_float(v)
    return int(f) if f is not None else None


def _safe_str(v) -> Optional[str]:
    if v is None:
        return None
    try:
        import pandas as pd
        if pd.isna(v):
            return None
    except Exception:
        pass
    s = str(v)
    return s if s and s != "nan" else None
