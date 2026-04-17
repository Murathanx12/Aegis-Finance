"""
Bond Analytics Router
======================

Per-bond and per-ladder fixed-income analytics (YTM, duration, convexity,
key-rate durations, ladder rollup) plus the live US Treasury par curve.

Endpoints:
    GET  /api/bond/treasury-curve       — current Treasury par curve (FRED)
    POST /api/bond/analytics            — full analytics for one bond
    POST /api/bond/key-rate-durations   — KRDs at 2y/5y/10y/30y
    POST /api/bond/ladder               — portfolio analytics for a ladder
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Body, HTTPException

from backend.cache import cache_get, cache_set

router = APIRouter(prefix="/api/bond", tags=["bond"])
logger = logging.getLogger(__name__)


@router.get("/treasury-curve")
async def get_treasury_curve():
    """Current Treasury par curve and key spreads from FRED."""
    cached = cache_get("bond_treasury_curve", 1800)
    if cached is not None:
        return cached

    try:
        from backend.services.bond_analytics import treasury_curve

        result = await asyncio.to_thread(treasury_curve)
        if "error" in result:
            raise HTTPException(status_code=503, detail=result["error"])
        cache_set("bond_treasury_curve", result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("treasury curve failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analytics")
async def post_bond_analytics(payload: dict = Body(...)):
    """Full analytics block for one fixed-coupon bond.

    Body fields:
        face: float = 100
        coupon_rate: float (decimal, e.g. 0.045)
        maturity_years: float
        freq: int = 2
        price: float = face (clean price)
    """
    from backend.services.bond_analytics import Bond, bond_analytics

    try:
        coupon_rate = float(payload.get("coupon_rate", 0.0))
        maturity = float(payload["maturity_years"])
    except (KeyError, TypeError, ValueError) as e:
        raise HTTPException(status_code=422, detail=f"Invalid input: {e}")

    if maturity <= 0 or maturity > 100:
        raise HTTPException(status_code=422, detail="maturity_years must be in (0, 100]")
    if not -0.5 <= coupon_rate <= 1.0:
        raise HTTPException(status_code=422, detail="coupon_rate out of range [-50%, 100%]")

    bond = Bond(
        face=float(payload.get("face", 100.0)),
        coupon_rate=coupon_rate,
        maturity_years=maturity,
        freq=int(payload.get("freq", 2)),
    )
    price = float(payload.get("price", bond.face))
    if price <= 0:
        raise HTTPException(status_code=422, detail="price must be > 0")

    try:
        result = await asyncio.to_thread(bond_analytics, bond, price)
        if "error" in result:
            raise HTTPException(status_code=422, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("bond analytics failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/key-rate-durations")
async def post_key_rate_durations(payload: dict = Body(...)):
    """Key-rate durations at 2y / 5y / 10y / 30y for a single bond.

    Same input fields as /analytics plus optional ``shock_bp`` (default 25).
    """
    from backend.services.bond_analytics import Bond, key_rate_durations

    try:
        coupon_rate = float(payload.get("coupon_rate", 0.0))
        maturity = float(payload["maturity_years"])
    except (KeyError, TypeError, ValueError) as e:
        raise HTTPException(status_code=422, detail=f"Invalid input: {e}")

    if maturity <= 0 or maturity > 100:
        raise HTTPException(status_code=422, detail="maturity_years must be in (0, 100]")

    bond = Bond(
        face=float(payload.get("face", 100.0)),
        coupon_rate=coupon_rate,
        maturity_years=maturity,
        freq=int(payload.get("freq", 2)),
    )
    price = float(payload.get("price", bond.face))
    if price <= 0:
        raise HTTPException(status_code=422, detail="price must be > 0")
    shock_bp = float(payload.get("shock_bp", 25.0))

    try:
        result = await asyncio.to_thread(
            key_rate_durations, bond, price, shock_bp=shock_bp
        )
        if "error" in result:
            raise HTTPException(status_code=422, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("key-rate durations failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ladder")
async def post_ladder(payload: dict = Body(...)):
    """Portfolio-level analytics for a bond ladder.

    Body field ``positions``: list of bond dicts, each with at minimum
    ``maturity_years`` + ``coupon_rate``. Optional per-position fields:
    face, freq, price, weight.
    """
    from backend.services.bond_analytics import ladder_analytics

    positions = payload.get("positions") or []
    if not positions:
        raise HTTPException(status_code=422, detail="positions list is required")
    if len(positions) > 50:
        raise HTTPException(status_code=422, detail="max 50 positions per ladder")

    try:
        result = await asyncio.to_thread(ladder_analytics, positions)
        if "error" in result:
            raise HTTPException(status_code=422, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("ladder analytics failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
