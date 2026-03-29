"""
Sector Analysis Router
========================

GET /api/sectors — 11-sector factor model rankings
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from backend.cache import cache_get, cache_set

router = APIRouter(prefix="/api", tags=["sectors"])
logger = logging.getLogger(__name__)


@router.get("/sectors")
async def get_sectors():
    """11-sector factor model with expected returns, momentum, risk."""
    cached = cache_get("sector_analysis", 21600)  # 6 hours
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_analyze_sectors)
        cache_set("sector_analysis", result)
        return result
    except Exception as e:
        logger.error("sector analysis failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _analyze_sectors() -> dict:
    from backend.config import get_forecast_days
    from backend.services.data_fetcher import DataFetcher
    from backend.services.sector_analyzer import analyze_sectors

    fetcher = DataFetcher()
    data, sector_data = fetcher.fetch_market_data()

    results = analyze_sectors(
        data=data,
        sector_data=sector_data,
        forecast_days=get_forecast_days(),
    )

    # Sort by expected return
    ranked = sorted(results.items(), key=lambda x: x[1]["sim_total_return"], reverse=True)

    return {
        "sectors": [
            {"name": name, "rank": i + 1, **metrics}
            for i, (name, metrics) in enumerate(ranked)
        ],
        "count": len(ranked),
    }
