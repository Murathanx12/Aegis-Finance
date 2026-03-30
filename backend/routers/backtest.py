"""
Backtest Router
================

GET /api/backtest/signal  — Run signal engine backtest over historical period
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query

from backend.cache import cache_get, cache_set

router = APIRouter(prefix="/api/backtest", tags=["backtest"])
logger = logging.getLogger(__name__)

_BACKTEST_TTL = 86400  # 24hr cache


@router.get("/signal")
async def backtest_signal(
    start: str = Query("2020-01-01", description="Start date YYYY-MM-DD"),
    end: str = Query("2025-06-01", description="End date YYYY-MM-DD"),
):
    """Run signal engine backtest and return evaluation metrics."""
    cache_key = f"backtest_signal:{start}:{end}"
    cached = cache_get(cache_key, _BACKTEST_TTL)
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_run_backtest, start, end)
        cache_set(cache_key, result)
        return result
    except Exception as e:
        logger.error("backtest failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _run_backtest(start: str, end: str) -> dict:
    from backend.services.backtest import backtest_signal_engine, evaluate_backtest

    df = backtest_signal_engine(start_date=start, end_date=end)
    evaluation = evaluate_backtest(df)

    # Include the raw signal history
    history = df.to_dict(orient="records")

    return {
        "evaluation": evaluation,
        "history": history,
        "start": start,
        "end": end,
    }
