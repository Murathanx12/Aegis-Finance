"""
Backtest Router
================

GET /api/backtest/signal  — Run signal engine backtest over historical period
"""

import asyncio
import logging
import re

from fastapi import APIRouter, HTTPException, Query

from backend.cache import cache_get, cache_set
from backend.config import config

router = APIRouter(prefix="/api/backtest", tags=["backtest"])
logger = logging.getLogger(__name__)

_CACHE_TTL = config["cache"]

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@router.get("/signal")
async def backtest_signal(
    start: str = Query("2020-01-01", description="Start date YYYY-MM-DD"),
    end: str = Query("2025-06-01", description="End date YYYY-MM-DD"),
):
    """Run signal engine backtest and return evaluation metrics."""
    if not _DATE_RE.match(start):
        raise HTTPException(status_code=422, detail="Invalid start date format, expected YYYY-MM-DD")
    if not _DATE_RE.match(end):
        raise HTTPException(status_code=422, detail="Invalid end date format, expected YYYY-MM-DD")
    if start >= end:
        raise HTTPException(status_code=422, detail="Start date must be before end date")

    cache_key = f"backtest_signal:{start}:{end}"
    cached = cache_get(cache_key, _CACHE_TTL["ttl_backtest"])
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_run_backtest, start, end)
        cache_set(cache_key, result)
        return result
    except ValueError as e:
        logger.error("backtest value error: %s", e)
        raise HTTPException(status_code=422, detail=str(e))
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
