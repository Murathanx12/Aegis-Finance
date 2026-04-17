"""
Crypto + DeFi Router
======================

GET /api/crypto/markets             — top-N coin snapshot
GET /api/crypto/{coin_id}/history   — daily price history (1..365d)
GET /api/crypto/defi                — DeFi TVL dashboard (DefiLlama)
GET /api/crypto/defi/protocols      — top DeFi protocols by TVL
"""

from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, HTTPException

from backend.cache import cache_get, cache_set

router = APIRouter(prefix="/api/crypto", tags=["crypto"])
logger = logging.getLogger(__name__)

_COIN_RE = re.compile(r"^[a-z0-9\-]{2,40}$")


@router.get("/markets")
async def get_crypto_markets(top_n: int = 20):
    """Top N coins from CoinGecko."""
    if top_n < 1 or top_n > 50:
        raise HTTPException(status_code=422, detail="top_n must be 1..50")

    cache_key = f"crypto_dashboard:{top_n}"
    cached = cache_get(cache_key, 180)
    if cached is not None:
        return cached

    try:
        from backend.services.crypto_market import crypto_dashboard
        result = await asyncio.to_thread(crypto_dashboard, top_n)
        cache_set(cache_key, result)
        return result
    except Exception as e:
        logger.error("crypto markets failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{coin_id}/history")
async def get_coin_history(coin_id: str, days: int = 30):
    """Daily price + volume history for one coin."""
    coin_id = (coin_id or "").lower().strip()
    if not _COIN_RE.match(coin_id):
        raise HTTPException(status_code=422, detail="invalid coin_id")
    if days < 1 or days > 365:
        raise HTTPException(status_code=422, detail="days must be 1..365")

    cache_key = f"crypto_history_endpoint:{coin_id}:{days}"
    cached = cache_get(cache_key, 1800)
    if cached is not None:
        return cached

    try:
        from backend.services.crypto_market import fetch_history
        series = await asyncio.to_thread(fetch_history, coin_id, days)
        if not series:
            raise HTTPException(status_code=404, detail=f"No history for {coin_id}")
        out = {"coin_id": coin_id, "days": days, "n": len(series), "series": series}
        cache_set(cache_key, out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.error("crypto history %s failed: %s", coin_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/defi")
async def get_defi_dashboard():
    """DeFi TVL dashboard: global trend + top chains + top protocols."""
    cached = cache_get("defi_dashboard", 600)
    if cached is not None:
        return cached

    try:
        from backend.services.defi_metrics import defi_dashboard
        result = await asyncio.to_thread(defi_dashboard)
        cache_set("defi_dashboard", result)
        return result
    except Exception as e:
        logger.error("defi dashboard failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/defi/protocols")
async def get_defi_protocols(top_n: int = 30):
    """Top N DeFi protocols by TVL."""
    if top_n < 1 or top_n > 200:
        raise HTTPException(status_code=422, detail="top_n must be 1..200")

    cache_key = f"defi_protocols_endpoint:{top_n}"
    cached = cache_get(cache_key, 600)
    if cached is not None:
        return cached

    try:
        from backend.services.defi_metrics import fetch_protocols
        rows = await asyncio.to_thread(fetch_protocols, top_n)
        out = {"protocols": rows, "n": len(rows)}
        cache_set(cache_key, out)
        return out
    except Exception as e:
        logger.error("defi protocols failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
