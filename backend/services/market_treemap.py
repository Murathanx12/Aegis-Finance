"""
Aegis Finance — Finviz/Bloomberg-style Market Treemap
========================================================

Builds a sector → industry → ticker treemap of the configured stock
universe, with rectangle size ∝ market cap and color ∝ return over the
selected window (1D, 1W, 1M, YTD).

The frontend consumes this directly with Recharts Treemap.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

from backend.cache import cache_get, cache_set
from backend.config import config

logger = logging.getLogger(__name__)

_UNI = config.get("stock_universe", {})
SECTOR_STOCKS: dict = _UNI.get("sector_stocks", {})
_CACHE_TTL = 900  # 15 min

_VALID_WINDOWS = {"1d", "1w", "1m", "ytd"}


def _download_history(tickers: list[str]) -> Optional[pd.DataFrame]:
    """Fetch ~1Y of adjusted closes for the ticker list in one yfinance call."""
    if not tickers:
        return None
    try:
        df = yf.download(
            tickers=" ".join(tickers),
            period="1y",
            interval="1d",
            auto_adjust=True,
            group_by="column",
            threads=True,
            progress=False,
        )
    except Exception as e:
        logger.warning("treemap yfinance download failed: %s", e)
        return None

    if df is None or df.empty:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        if "Close" in df.columns.get_level_values(0):
            closes = df["Close"]
        elif "Adj Close" in df.columns.get_level_values(0):
            closes = df["Adj Close"]
        else:
            return None
    else:
        # Single-ticker download returns flat columns
        if "Close" in df.columns:
            closes = df[["Close"]]
            closes.columns = tickers[:1]
        else:
            return None

    return closes.dropna(how="all")


def _compute_return(prices: pd.Series, window: str) -> Optional[float]:
    s = prices.dropna()
    if len(s) < 2:
        return None
    last = float(s.iloc[-1])
    if window == "1d":
        prior = float(s.iloc[-2])
    elif window == "1w":
        if len(s) < 6:
            return None
        prior = float(s.iloc[-6])
    elif window == "1m":
        if len(s) < 22:
            return None
        prior = float(s.iloc[-22])
    elif window == "ytd":
        year = s.index[-1].year
        ytd = s[s.index.year == year]
        if len(ytd) < 2:
            return None
        prior = float(ytd.iloc[0])
    else:
        return None
    if prior == 0:
        return None
    return round((last / prior - 1.0) * 100.0, 2)


def _fetch_market_cap(ticker: str) -> Optional[float]:
    try:
        info = yf.Ticker(ticker).fast_info
        mc = getattr(info, "market_cap", None)
        if mc is None:
            mc = yf.Ticker(ticker).info.get("marketCap")
        return float(mc) if mc else None
    except Exception:
        return None


def build_treemap(window: str = "1d") -> dict:
    """Build the sector → tickers treemap for the current configured universe.

    Args:
        window: one of {'1d', '1w', '1m', 'ytd'}.
    """
    window = window.lower()
    if window not in _VALID_WINDOWS:
        raise ValueError(f"Unsupported window {window!r}; choose from {sorted(_VALID_WINDOWS)}")

    cache_key = f"market_treemap:{window}"
    cached = cache_get(cache_key, _CACHE_TTL)
    if cached is not None:
        return cached

    # Flatten universe into a single ticker list so we pay for one yfinance call
    all_tickers: list[str] = []
    sector_lookup: dict[str, str] = {}
    for sector, tickers in SECTOR_STOCKS.items():
        for t in tickers:
            all_tickers.append(t)
            sector_lookup[t] = sector
    all_tickers = sorted(set(all_tickers))

    history = _download_history(all_tickers)
    if history is None or history.empty:
        return {
            "window": window,
            "children": [],
            "total_market_cap": 0.0,
            "missing": all_tickers,
            "error": "yfinance returned no history",
        }

    # Fetch market caps in parallel
    caps: dict[str, Optional[float]] = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(_fetch_market_cap, t): t for t in all_tickers}
        for fut in as_completed(futs):
            t = futs[fut]
            caps[t] = fut.result()

    # Build sector → children
    sector_children: dict[str, list[dict]] = {}
    missing: list[str] = []
    total_mc = 0.0

    for t in all_tickers:
        prices = history[t] if t in history.columns else None
        if prices is None or prices.dropna().empty:
            missing.append(t)
            continue
        ret = _compute_return(prices, window)
        mc = caps.get(t)
        if mc is None or ret is None:
            missing.append(t)
            continue
        sector = sector_lookup.get(t, "Unknown")
        sector_children.setdefault(sector, []).append({
            "ticker": t,
            "market_cap": mc,
            "return_pct": ret,
            "size": mc,          # Recharts treemap uses `size`
            "value": ret,        # and `value` or colorValue for shading
        })
        total_mc += mc

    # Sort tickers within each sector descending by market cap; sort sectors likewise
    children = []
    for sector, items in sector_children.items():
        items.sort(key=lambda x: x["market_cap"], reverse=True)
        sector_mc = sum(i["market_cap"] for i in items)
        sector_ret = float(np.average(
            [i["return_pct"] for i in items],
            weights=[i["market_cap"] for i in items],
        ))
        children.append({
            "name": sector,
            "size": sector_mc,
            "value": round(sector_ret, 2),
            "children": items,
        })
    children.sort(key=lambda x: x["size"], reverse=True)

    result = {
        "window": window,
        "children": children,
        "total_market_cap": total_mc,
        "ticker_count": sum(len(c["children"]) for c in children),
        "missing": missing,
    }
    cache_set(cache_key, result)
    return result
