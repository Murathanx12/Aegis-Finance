"""
Multi-Asset Markets Router
============================

GET /api/markets/fx                 — G10 FX dashboard (spot + forwards)
GET /api/markets/fx/{pair}          — single pair forward curve
GET /api/markets/futures            — commodities dashboard
GET /api/markets/futures/{symbol}   — single commodity curve
"""

from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, HTTPException

from backend.cache import cache_get, cache_set

router = APIRouter(prefix="/api/markets", tags=["markets"])
logger = logging.getLogger(__name__)

_PAIR_RE = re.compile(r"^[A-Z]{6}$")
_SYMBOL_RE = re.compile(r"^[A-Z]{2,12}$")


@router.get("/fx")
async def get_fx_dashboard():
    """G10 FX table: spot + 1m/3m/12m forwards + carry."""
    cached = cache_get("fx_dashboard", 300)
    if cached is not None:
        return cached

    try:
        from backend.services.fx_curves import fx_dashboard
        result = await asyncio.to_thread(fx_dashboard)
        cache_set("fx_dashboard", result)
        return result
    except Exception as e:
        logger.error("fx dashboard failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fx/{pair}")
async def get_fx_pair(pair: str, tenors: str = "1,3,6,12"):
    """Forward curve for a single pair (CIP-implied)."""
    pair = pair.upper().strip()
    if not _PAIR_RE.match(pair):
        raise HTTPException(status_code=422, detail="pair must be 6 letters (e.g. EURUSD)")

    try:
        tenor_list = tuple(
            int(t.strip()) for t in tenors.split(",") if t.strip()
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="tenors must be comma-separated ints")
    if not tenor_list or len(tenor_list) > 12 or any(t < 1 or t > 60 for t in tenor_list):
        raise HTTPException(status_code=422, detail="provide 1..12 tenors in months [1..60]")

    cache_key = f"fx_pair:{pair}:{tenors}"
    cached = cache_get(cache_key, 300)
    if cached is not None:
        return cached

    try:
        from backend.services.fx_curves import forward_curve
        result = await asyncio.to_thread(forward_curve, pair, tenor_list)
        if "error" in result:
            raise HTTPException(status_code=503, detail=result["error"])
        cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("fx pair %s failed: %s", pair, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/futures")
async def get_commodities_dashboard(months: int = 6):
    """Commodities dashboard with curve shape per market."""
    if months < 1 or months > 24:
        raise HTTPException(status_code=422, detail="months must be 1..24")

    cache_key = f"commodities_dashboard:{months}"
    cached = cache_get(cache_key, 1800)
    if cached is not None:
        return cached

    try:
        from backend.services.commodity_curves import commodity_dashboard
        result = await asyncio.to_thread(commodity_dashboard, None, months)
        cache_set(cache_key, result)
        return result
    except Exception as e:
        logger.error("commodities dashboard failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/futures/{symbol}")
async def get_commodity_curve(symbol: str, months: int = 12):
    """Front + N-month curve for a single commodity."""
    symbol = symbol.upper().strip()
    if not _SYMBOL_RE.match(symbol):
        raise HTTPException(status_code=422, detail="invalid symbol")
    if months < 1 or months > 24:
        raise HTTPException(status_code=422, detail="months must be 1..24")

    cache_key = f"commodity_curve_endpoint:{symbol}:{months}"
    cached = cache_get(cache_key, 1800)
    if cached is not None:
        return cached

    try:
        from backend.services.commodity_curves import fetch_curve, DEFAULT_COMMODITIES
        if symbol not in DEFAULT_COMMODITIES:
            raise HTTPException(
                status_code=404,
                detail=f"unknown commodity {symbol} (try {list(DEFAULT_COMMODITIES)[:6]})",
            )
        result = await asyncio.to_thread(fetch_curve, symbol, months)
        if "error" in result:
            raise HTTPException(status_code=503, detail=result["error"])
        cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("commodity %s failed: %s", symbol, e)
        raise HTTPException(status_code=500, detail=str(e))
