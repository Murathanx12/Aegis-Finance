"""
Aegis Finance — World Markets Tile (WEI-style)
================================================

Bloomberg WEI-equivalent: a single request that returns live snapshots of
~30 global indices, major FX pairs, commodities, and sovereign yields in a
normalised shape suitable for a heat grid.

Sources: yfinance for indices/FX/commodities (wrapped in provider registry
for future fallback), FRED for international bond yields, Polygon/Finnhub
for real-time deltas when available.

Output shape (per row):
    {
        "ticker": "^GSPC", "name": "S&P 500", "region": "Americas",
        "category": "index",
        "price": 5843.2, "change": -12.4, "change_pct": -0.21,
        "is_open": true, "source": "yfinance",
    }
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from backend.cache import cached
from backend.services.providers import registry

logger = logging.getLogger(__name__)


# ── Universe ─────────────────────────────────────────────────────────────────


INDICES = [
    # Americas
    ("^GSPC", "S&P 500", "Americas"),
    ("^IXIC", "NASDAQ Composite", "Americas"),
    ("^DJI", "Dow Jones", "Americas"),
    ("^RUT", "Russell 2000", "Americas"),
    ("^GSPTSE", "S&P/TSX", "Americas"),
    ("^BVSP", "Bovespa", "Americas"),
    ("^MXX", "IPC Mexico", "Americas"),
    # Europe
    ("^FTSE", "FTSE 100", "Europe"),
    ("^GDAXI", "DAX", "Europe"),
    ("^FCHI", "CAC 40", "Europe"),
    ("^STOXX50E", "Euro Stoxx 50", "Europe"),
    ("^IBEX", "IBEX 35", "Europe"),
    ("FTSEMIB.MI", "FTSE MIB", "Europe"),
    ("^SSMI", "SMI (Swiss)", "Europe"),
    # Asia-Pacific
    ("^N225", "Nikkei 225", "Asia"),
    ("^HSI", "Hang Seng", "Asia"),
    ("000001.SS", "Shanghai Composite", "Asia"),
    ("^KS11", "KOSPI", "Asia"),
    ("^AXJO", "ASX 200", "Asia"),
    ("^TWII", "Taiwan Weighted", "Asia"),
    ("^NSEI", "Nifty 50", "Asia"),
]

FX_PAIRS = [
    ("EURUSD=X", "EUR/USD", "Major"),
    ("GBPUSD=X", "GBP/USD", "Major"),
    ("USDJPY=X", "USD/JPY", "Major"),
    ("USDCHF=X", "USD/CHF", "Major"),
    ("AUDUSD=X", "AUD/USD", "Major"),
    ("USDCAD=X", "USD/CAD", "Major"),
    ("NZDUSD=X", "NZD/USD", "Major"),
    ("USDCNY=X", "USD/CNY", "EM"),
    ("USDINR=X", "USD/INR", "EM"),
    ("USDBRL=X", "USD/BRL", "EM"),
]

COMMODITIES = [
    ("GC=F", "Gold", "Metals"),
    ("SI=F", "Silver", "Metals"),
    ("HG=F", "Copper", "Metals"),
    ("PL=F", "Platinum", "Metals"),
    ("CL=F", "WTI Crude", "Energy"),
    ("BZ=F", "Brent Crude", "Energy"),
    ("NG=F", "Natural Gas", "Energy"),
    ("RB=F", "Gasoline", "Energy"),
    ("ZC=F", "Corn", "Agriculture"),
    ("ZS=F", "Soybeans", "Agriculture"),
    ("ZW=F", "Wheat", "Agriculture"),
]

SOVEREIGN_YIELDS = [
    ("^TNX", "US 10Y", "Americas"),
    ("^FVX", "US 5Y", "Americas"),
    ("^TYX", "US 30Y", "Americas"),
    ("^IRX", "US 13-Week", "Americas"),
]


# ── Fetcher ──────────────────────────────────────────────────────────────────


def _snapshot_one(ticker: str) -> Optional[dict]:
    """Fetch one snapshot through the provider registry."""
    try:
        snap = registry.get_equity_snapshot(ticker)
        if snap is None or snap.price is None:
            return None
        return {
            "price": float(snap.price),
            "change": _safe_float(snap.change),
            "change_pct": _safe_float(snap.change_pct),
            "prev_close": _safe_float(snap.prev_close),
            "source": snap.source,
        }
    except Exception as e:
        logger.debug("world-markets snapshot failed for %s: %s", ticker, e)
        return None


def _safe_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        if f != f:
            return None
        return round(f, 6)
    except (TypeError, ValueError):
        return None


def _fetch_group(entries: list[tuple[str, str, str]], category: str) -> list[dict]:
    """Parallel-fetch snapshots for a category. Missing entries dropped."""
    out: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        future_to_meta = {
            ex.submit(_snapshot_one, t): (t, name, region)
            for t, name, region in entries
        }
        for fut in as_completed(future_to_meta):
            ticker, name, region = future_to_meta[fut]
            try:
                snap = fut.result()
            except Exception:
                snap = None
            if snap is None:
                continue
            out.append(
                {
                    "ticker": ticker,
                    "name": name,
                    "region": region,
                    "category": category,
                    **snap,
                }
            )
    # Sort within group by region then name so UI gets deterministic order
    out.sort(key=lambda r: (r["region"], r["name"]))
    return out


@cached(ttl=300)  # 5-min cache — WEI doesn't need tick-by-tick
def get_world_markets_snapshot() -> dict:
    """Return a WEI-style snapshot of indices / FX / commodities / yields."""
    indices = _fetch_group(INDICES, "index")
    fx = _fetch_group(FX_PAIRS, "fx")
    commodities = _fetch_group(COMMODITIES, "commodity")
    yields = _fetch_group(SOVEREIGN_YIELDS, "yield")

    # Derive top movers across everything
    all_rows = indices + fx + commodities + yields
    with_moves = [r for r in all_rows if r.get("change_pct") is not None]
    gainers = sorted(with_moves, key=lambda r: r["change_pct"], reverse=True)[:5]
    losers = sorted(with_moves, key=lambda r: r["change_pct"])[:5]

    return {
        "counts": {
            "indices": len(indices),
            "fx": len(fx),
            "commodities": len(commodities),
            "yields": len(yields),
            "total_attempted": len(INDICES) + len(FX_PAIRS) + len(COMMODITIES) + len(SOVEREIGN_YIELDS),
            "total_fetched": len(all_rows),
        },
        "indices": indices,
        "fx": fx,
        "commodities": commodities,
        "yields": yields,
        "top_gainers": gainers,
        "top_losers": losers,
    }


# ── Economic calendar (macro releases, not earnings) ─────────────────────────


def get_economic_calendar(days_ahead: int = 14) -> dict:
    """Fetch upcoming economic releases from Finnhub (US-focused, free tier).

    Returns a shape the frontend can render as a day-grouped calendar.
    """
    import requests
    import pandas as pd
    from backend.config import api_keys

    if not api_keys.has("finnhub"):
        return {
            "days_ahead": days_ahead,
            "count": 0,
            "events": [],
            "note": "Finnhub key not set — calendar empty",
        }

    start = pd.Timestamp.today().strftime("%Y-%m-%d")
    end = (pd.Timestamp.today() + pd.Timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/calendar/economic",
            params={"from": start, "to": end, "token": api_keys.finnhub},
            timeout=10,
        )
        if r.status_code in (401, 403):
            return {"days_ahead": days_ahead, "count": 0, "events": [], "note": "auth failed"}
        r.raise_for_status()
        payload = r.json()
    except Exception as e:
        logger.warning("economic calendar fetch failed: %s", e)
        return {"days_ahead": days_ahead, "count": 0, "events": [], "error": str(e)}

    rows = payload.get("economicCalendar", []) or []
    events = []
    for row in rows:
        events.append(
            {
                "date": row.get("time", "")[:10],
                "time": row.get("time", ""),
                "country": row.get("country"),
                "event": row.get("event"),
                "actual": _safe_float(row.get("actual")),
                "estimate": _safe_float(row.get("estimate")),
                "prior": _safe_float(row.get("prev")),
                "impact": row.get("impact"),
                "unit": row.get("unit"),
            }
        )
    events.sort(key=lambda e: e.get("time") or "")
    return {
        "days_ahead": days_ahead,
        "count": len(events),
        "events": events,
    }
