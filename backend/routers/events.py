"""
Events Router — SEC EDGAR materiality stream
=============================================

GET /api/events/8k                — universe-wide high-materiality stream
GET /api/events/8k/{ticker}       — per-ticker classified 8-K feed
GET /api/events/taxonomy          — explain the 8-K item → event_type mapping
"""

from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, HTTPException

from backend.cache import cache_get, cache_set
from backend.config import config

router = APIRouter(prefix="/api/events", tags=["events"])
logger = logging.getLogger(__name__)

_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")


@router.get("/taxonomy")
async def get_taxonomy():
    """Explain the 8-K item → event_type / materiality mapping."""
    from backend.services.edgar_events import (
        ITEM_TAXONOMY, HIGH_MATERIALITY_ITEMS,
    )
    return {
        "items": [
            {
                "item": code,
                "event_type": evt,
                "materiality": mat,
                "high_materiality": code in HIGH_MATERIALITY_ITEMS,
            }
            for code, (evt, mat) in sorted(ITEM_TAXONOMY.items())
        ]
    }


@router.get("/8k/{ticker}")
async def get_ticker_events(
    ticker: str,
    days_back: int = 90,
    high_only: bool = False,
):
    """Recent 8-K filings for a single ticker, classified by item."""
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail=f"Invalid ticker: {ticker}")
    if days_back < 1 or days_back > 365 * 3:
        raise HTTPException(status_code=422, detail="days_back must be 1..1095")

    cache_key = f"edgar_events:{ticker}:{days_back}:{int(high_only)}"
    cached = cache_get(cache_key, 600)
    if cached is not None:
        return cached

    try:
        from backend.services.edgar_events import (
            fetch_events_for_ticker, event_summary,
        )
        events = await asyncio.to_thread(
            fetch_events_for_ticker,
            ticker,
            days_back=days_back,
            only_8k=True,
            high_materiality_only=high_only,
        )
        result = {
            "ticker": ticker,
            "days_back": days_back,
            "high_only": high_only,
            "events": [e.to_dict() for e in events],
            "summary": event_summary(events),
        }
        cache_set(cache_key, result)
        return result
    except Exception as e:
        logger.error("EDGAR events for %s failed: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/8k")
async def get_universe_events(days_back: int = 14, high_only: bool = True):
    """Aggregated high-materiality 8-K stream across the default watchlist."""
    if days_back < 1 or days_back > 90:
        raise HTTPException(status_code=422, detail="days_back must be 1..90")

    cache_key = f"edgar_events:universe:{days_back}:{int(high_only)}"
    cached = cache_get(cache_key, 900)
    if cached is not None:
        return cached

    try:
        from backend.services.edgar_events import (
            fetch_events_for_universe, event_summary,
        )
        tickers = (
            config.get("stock_universe", {}).get("default_watchlist")
            or ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]
        )[:30]
        events = await asyncio.to_thread(
            fetch_events_for_universe,
            tickers,
            days_back=days_back,
            high_materiality_only=high_only,
        )
        result = {
            "days_back": days_back,
            "high_only": high_only,
            "n_tickers_scanned": len(tickers),
            "events": [e.to_dict() for e in events[:200]],
            "summary": event_summary(events),
        }
        cache_set(cache_key, result)
        return result
    except Exception as e:
        logger.error("EDGAR universe events failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
