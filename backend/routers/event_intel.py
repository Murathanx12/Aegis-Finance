"""
EVENT-INTEL router — structured descriptive events per ticker.

Descriptive-only surface (ROADMAP 2026-07-29B acceptance spec): typed events
with disclosed per-feed availability, no buy/sell language, no forecasts.
"""

import asyncio
import functools
import logging
import re

from fastapi import APIRouter, HTTPException

from backend.cache import cache_swr
from backend.config import config

router = APIRouter(prefix="/api/event-intel", tags=["event-intel"])
logger = logging.getLogger(__name__)

_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")
_TTL = config["event_intel"]["cache_ttl"]


# Literal path registered before /{ticker} — route order matters.
@router.get("/stats")
async def extraction_stats():
    """Extraction outcomes: events, tier/direction/method mix, feed health."""
    try:
        from backend.observability import event_intel_stats
        return await asyncio.to_thread(event_intel_stats)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("event-intel stats failed: %s", e)
        raise HTTPException(status_code=500, detail="stats unavailable")


@router.get("/{ticker}")
async def ticker_events(ticker: str):
    """Typed events for one ticker with per-feed availability disclosure."""
    symbol = ticker.upper().strip()
    if not _TICKER_RE.match(symbol):
        raise HTTPException(status_code=422, detail=f"Invalid ticker: {ticker}")
    try:
        from backend.services.event_intel import get_ticker_events
        return await cache_swr(
            f"event_intel:{symbol}", _TTL,
            functools.partial(get_ticker_events, symbol),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("event-intel failed for %s: %s", symbol, e)
        raise HTTPException(status_code=500, detail="event extraction failed")
