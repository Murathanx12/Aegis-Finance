"""
Cross-Asset Tail Dependence Router
=====================================

GET /api/correlation/tail-dependence  — Pairwise tail dependence, contagion clusters, portfolio summary
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.cache import cache_get, cache_set
from backend.config import config

router = APIRouter(prefix="/api/correlation", tags=["correlation"])
logger = logging.getLogger(__name__)

_CACHE_TTL = config["cache"]


@router.get("/tail-dependence")
async def get_tail_dependence(
    tickers: str = Query(
        default="AAPL,MSFT,GOOGL,AMZN,GLD,TLT,VNQ",
        description="Comma-separated ticker symbols (2-20)",
    ),
    lookback: Optional[int] = Query(
        default=None,
        description="Lookback period in trading days (default 756 = 3 years)",
    ),
    include_rolling: bool = Query(
        default=False,
        description="Include rolling tail dependence time series for top pair",
    ),
):
    """Compute cross-asset tail dependence and contagion analysis.

    Returns pairwise tail dependence coefficients, contagion clusters,
    and portfolio-level diversification quality assessment.
    """
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]

    if len(ticker_list) < 2:
        raise HTTPException(
            status_code=422,
            detail="Need at least 2 tickers for tail dependence analysis",
        )
    if len(ticker_list) > 20:
        raise HTTPException(
            status_code=422,
            detail="Maximum 20 tickers supported",
        )

    # Cache key based on sorted tickers + params
    cache_key = f"tail_dep_{'_'.join(sorted(ticker_list))}_{lookback}_{include_rolling}"
    cached = cache_get(cache_key, _CACHE_TTL.get("ttl_market", 3600))
    if cached is not None:
        return cached

    try:
        from backend.services.tail_dependence import analyze_tail_dependence

        result = await asyncio.to_thread(
            analyze_tail_dependence,
            ticker_list,
            lookback=lookback,
            include_rolling=include_rolling,
        )

        if "error" in result:
            raise HTTPException(status_code=422, detail=result["error"])

        cache_set(cache_key, result)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Tail dependence analysis failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
