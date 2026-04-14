"""
Aegis Finance — Cross-Sectional Momentum (Relative Strength)
==============================================================

Ranks all stocks in the universe by relative strength across multiple
timeframes. Used by every institutional quant shop (Jegadeesh & Titman 1993,
Asness et al. 2013).

Computes:
  - 1M, 3M, 6M, 12M total returns for each stock
  - Composite momentum score (weighted average of timeframes)
  - Percentile rank within the universe
  - Momentum quintile (1=weakest, 5=strongest)
  - Sector-relative momentum (vs sector peers)

Usage:
    from backend.services.cross_sectional_momentum import (
        compute_momentum_rankings, get_momentum_score
    )
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from backend.config import config

logger = logging.getLogger(__name__)


def compute_momentum_rankings(
    tickers: Optional[list[str]] = None,
    include_sector_relative: bool = True,
) -> Optional[dict]:
    """Compute cross-sectional momentum rankings for all stocks in universe.

    Returns ranked list of stocks with momentum scores and percentiles.
    """
    import yfinance as yf

    # Default to full universe
    if tickers is None:
        universe = config.get("stock_universe", {})
        sector_stocks = universe.get("sector_stocks", {})
        all_tickers = set(universe.get("default_watchlist", []))
        for sector_tickers in sector_stocks.values():
            all_tickers.update(sector_tickers)
        tickers = sorted(all_tickers)

    if not tickers:
        return None

    # Fetch 13 months of data (need 12M return + 1M buffer)
    try:
        data = yf.download(
            tickers, period="13mo",
            auto_adjust=True, progress=False, threads=True,
        )
        if data.empty:
            return None

        if isinstance(data.columns, pd.MultiIndex):
            prices = data["Close"]
        else:
            prices = pd.DataFrame({tickers[0]: data["Close"]})
    except Exception as e:
        logger.warning("Failed to fetch momentum data: %s", e)
        return None

    # Build sector map for sector-relative momentum
    sector_map = {}
    if include_sector_relative:
        sector_stocks = config.get("stock_universe", {}).get("sector_stocks", {})
        for sector, stickers in sector_stocks.items():
            for t in stickers:
                sector_map[t] = sector

    # Compute returns over different lookback windows
    trading_days = {"1M": 21, "3M": 63, "6M": 126, "12M": 252}
    weights = {"1M": 0.10, "3M": 0.25, "6M": 0.35, "12M": 0.30}

    results = []
    for ticker in tickers:
        if ticker not in prices.columns:
            continue

        series = prices[ticker].dropna()
        if len(series) < 22:  # Need at least 1 month
            continue

        current_price = float(series.iloc[-1])
        returns = {}

        for period, days in trading_days.items():
            if len(series) >= days + 1:
                past_price = float(series.iloc[-(days + 1)])
                if past_price > 0:
                    returns[period] = (current_price / past_price - 1) * 100
                else:
                    returns[period] = None
            else:
                returns[period] = None

        # Composite momentum score (weighted average of available timeframes)
        composite = 0.0
        total_w = 0.0
        for period, w in weights.items():
            if returns.get(period) is not None:
                composite += w * returns[period]
                total_w += w

        if total_w > 0:
            composite /= total_w
        else:
            continue

        results.append({
            "ticker": ticker,
            "returns": returns,
            "composite_score": round(composite, 2),
            "sector": sector_map.get(ticker, "Unknown"),
        })

    if not results:
        return None

    # Sort by composite score descending
    results.sort(key=lambda x: x["composite_score"], reverse=True)

    # Assign percentile ranks and quintiles
    n = len(results)
    for i, r in enumerate(results):
        rank = i + 1
        # Percentile: top stock = 100, bottom stock = 0
        percentile = round((n - rank) / max(n - 1, 1) * 100, 1) if n > 1 else 50.0
        r["rank"] = rank
        r["percentile"] = percentile
        # Quintile: evenly distributed 5=best, 1=worst
        r["quintile"] = max(1, min(5, 5 - int(i * 5 / n))) if n > 0 else 3

    # Sector-relative momentum
    if include_sector_relative:
        sector_groups: dict[str, list] = {}
        for r in results:
            sector = r["sector"]
            if sector not in sector_groups:
                sector_groups[sector] = []
            sector_groups[sector].append(r)

        for sector, stocks in sector_groups.items():
            sector_n = len(stocks)
            stocks_sorted = sorted(stocks, key=lambda x: x["composite_score"], reverse=True)
            sector_avg = np.mean([s["composite_score"] for s in stocks_sorted])
            for i, s in enumerate(stocks_sorted):
                s["sector_rank"] = i + 1
                s["sector_percentile"] = round((1 - (i + 1) / sector_n) * 100, 1) if sector_n > 1 else 50.0
                s["sector_relative"] = round(s["composite_score"] - sector_avg, 2)

    # Summary statistics
    scores = [r["composite_score"] for r in results]
    summary = {
        "total_stocks": n,
        "avg_momentum": round(float(np.mean(scores)), 2),
        "median_momentum": round(float(np.median(scores)), 2),
        "breadth_positive": sum(1 for s in scores if s > 0),
        "breadth_negative": sum(1 for s in scores if s < 0),
        "breadth_ratio": round(sum(1 for s in scores if s > 0) / n, 2) if n > 0 else 0,
        "top_5": [{"ticker": r["ticker"], "score": r["composite_score"]} for r in results[:5]],
        "bottom_5": [{"ticker": r["ticker"], "score": r["composite_score"]} for r in results[-5:]],
    }

    return {
        "rankings": results,
        "summary": summary,
    }


def get_momentum_score(
    ticker: str,
    rankings: Optional[dict] = None,
) -> Optional[dict]:
    """Get momentum score for a single stock from precomputed rankings.

    If rankings not provided, computes fresh (slower).
    """
    if rankings is None:
        rankings = compute_momentum_rankings()

    if rankings is None:
        return None

    for r in rankings["rankings"]:
        if r["ticker"] == ticker:
            return r

    return None
