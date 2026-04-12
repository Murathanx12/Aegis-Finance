"""
Options & Earnings Intelligence Router
==========================================

GET /api/options/vix-term       — VIX term structure analysis
GET /api/options/{ticker}       — Options-implied intelligence (IV skew, P/C ratio, max pain)
GET /api/earnings/{ticker}      — Earnings intelligence (surprises, growth, estimates)
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from backend.cache import cache_get, cache_set
from backend.config import config

router = APIRouter(prefix="/api", tags=["options", "earnings"])
logger = logging.getLogger(__name__)

_CACHE_TTL = config["cache"]


# IMPORTANT: vix-term MUST be defined before {ticker} to avoid
# FastAPI matching "vix-term" as a ticker parameter.
@router.get("/options/vix-term")
async def get_vix_term():
    """Get VIX term structure (contango/backwardation analysis)."""
    cache_key = "vix_term_structure"
    cached = cache_get(cache_key, _CACHE_TTL.get("ttl_market", 300))
    if cached is not None:
        return cached

    try:
        from backend.services.options_intelligence import get_vix_term_structure
        result = await asyncio.to_thread(get_vix_term_structure)

        if "error" in result:
            raise HTTPException(status_code=422, detail=result["error"])

        cache_set(cache_key, result)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("VIX term structure failed: %s", e)
        raise HTTPException(status_code=500, detail=f"VIX term failed: {str(e)}")


@router.get("/options/{ticker}")
async def get_options_analysis(ticker: str):
    """Get options-implied intelligence for a stock.

    Returns IV skew, put/call ratios, IV rank, max pain, and composite signal.
    """
    ticker = ticker.upper().strip()
    cache_key = f"options_{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL.get("ttl_stock", 900))
    if cached is not None:
        return cached

    try:
        from backend.services.options_intelligence import get_options_summary
        result = await asyncio.to_thread(get_options_summary, ticker)

        if "error" in result and "signal" not in result:
            raise HTTPException(status_code=422, detail=result["error"])

        cache_set(cache_key, result)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Options analysis failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Options analysis failed: {str(e)}")


@router.get("/earnings/{ticker}")
async def get_earnings_analysis(ticker: str):
    """Get earnings intelligence for a stock.

    Returns earnings surprise history, growth trajectory, analyst estimates,
    and composite earnings signal.
    """
    ticker = ticker.upper().strip()
    cache_key = f"earnings_{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL.get("ttl_stock", 900))
    if cached is not None:
        return cached

    try:
        from backend.services.earnings_intelligence import get_earnings_summary
        result = await asyncio.to_thread(get_earnings_summary, ticker)

        if "error" in result and "signal" not in result:
            raise HTTPException(status_code=422, detail=result["error"])

        cache_set(cache_key, result)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Earnings analysis failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"Earnings analysis failed: {str(e)}")
