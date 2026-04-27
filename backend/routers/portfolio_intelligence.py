"""
Portfolio Intelligence Router
================================

POST /api/pi/real-portfolio/analyze    — Full metric pack for user holdings
GET  /api/pi/reference/{lane_id}/state — Current allocation + metrics
GET  /api/pi/reference/{lane_id}/history — Rebalance event history
GET  /api/pi/reference/{lane_id}/explain — Most recent rebalance explanation
GET  /api/pi/compare                   — All lanes side-by-side
POST /api/pi/trigger-check             — Manual rebalance check (Railway cron target)
GET  /api/pi/replay/{lane_id}          — Replay backtest results
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.schemas.portfolio_intelligence import (
    AnalyzePortfolioRequest,
    ReplayResult,
    SnapshotResponse,
)
from backend.services.portfolio_intelligence.real_analyzer import analyze_portfolio

router = APIRouter(prefix="/api/pi", tags=["portfolio-intelligence"])
logger = logging.getLogger(__name__)


@router.post("/real-portfolio/analyze", response_model=SnapshotResponse)
async def analyze_real_portfolio(request: AnalyzePortfolioRequest):
    """Analyze a real portfolio: returns MetricPack + risk flags."""
    try:
        result = await asyncio.to_thread(analyze_portfolio, request.holdings)
        return result
    except Exception as e:
        logger.error("Portfolio analysis failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get("/reference/{lane_id}/state", response_model=SnapshotResponse)
async def get_reference_state(lane_id: str):
    """Get current state of a reference portfolio lane."""
    if lane_id not in ("conservative", "balanced", "aggressive"):
        raise HTTPException(status_code=404, detail=f"Unknown lane: {lane_id}")

    from backend.services.portfolio_intelligence.reference_engine import run_reference_check

    try:
        result = await asyncio.to_thread(run_reference_check, lane_id)
        return result
    except Exception as e:
        logger.error("Reference state failed for %s: %s", lane_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reference/{lane_id}/history")
async def get_reference_history(
    lane_id: str,
    limit: int = Query(default=20, ge=1, le=100),
):
    """Get rebalance event history for a reference lane."""
    if lane_id not in ("conservative", "balanced", "aggressive"):
        raise HTTPException(status_code=404, detail=f"Unknown lane: {lane_id}")

    from backend.db import get_connection

    try:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM rebalance_events WHERE portfolio_id = ? ORDER BY id DESC LIMIT ?",
                (lane_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
    except Exception as e:
        logger.error("History fetch failed for %s: %s", lane_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reference/{lane_id}/explain")
async def get_reference_explain(lane_id: str):
    """Get most recent rebalance explanation for a lane."""
    if lane_id not in ("conservative", "balanced", "aggressive"):
        raise HTTPException(status_code=404, detail=f"Unknown lane: {lane_id}")

    from backend.db import get_connection

    try:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT explanation, trigger_reason, triggered_at FROM rebalance_events "
                "WHERE portfolio_id = ? ORDER BY id DESC LIMIT 1",
                (lane_id,),
            ).fetchone()
            if not row:
                return {"message": f"No rebalance events for {lane_id}"}
            return dict(row)
        finally:
            conn.close()
    except Exception as e:
        logger.error("Explain fetch failed for %s: %s", lane_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/compare")
async def compare_lanes():
    """Get all reference lanes side-by-side."""
    from backend.services.portfolio_intelligence.reference_engine import run_all_lanes

    try:
        results = await asyncio.to_thread(run_all_lanes)
        return {
            lane_id: {
                "portfolio_id": snapshot.portfolio_id,
                "date": snapshot.date,
                "weights": snapshot.weights,
                "metrics": snapshot.metrics.model_dump() if snapshot.metrics else None,
                "rebalanced": snapshot.latest_rebalance is not None,
            }
            for lane_id, snapshot in results.items()
        }
    except Exception as e:
        logger.error("Compare failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trigger-check")
async def trigger_check(lane_id: Optional[str] = None):
    """Manual rebalance check — Railway cron target.

    POST /api/pi/trigger-check          — check all lanes
    POST /api/pi/trigger-check?lane_id=conservative — check one lane
    """
    from backend.services.portfolio_intelligence.scheduler import manual_trigger

    try:
        result = await manual_trigger(lane_id)
        return result
    except Exception as e:
        logger.error("Trigger check failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/replay/{lane_id}", response_model=ReplayResult)
async def get_replay(
    lane_id: str,
    start_date: str = Query(default="2021-01-01"),
    end_date: Optional[str] = Query(default=None),
):
    """Run walk-forward replay backtest for a reference lane.

    WARNING: This is computationally expensive (fetches years of data).
    Cache the result client-side.
    """
    if lane_id not in ("conservative", "balanced", "aggressive"):
        raise HTTPException(status_code=404, detail=f"Unknown lane: {lane_id}")

    from backend.services.portfolio_intelligence.replay import ReplayEngine

    try:
        engine = ReplayEngine()
        result = await asyncio.to_thread(
            engine.run, lane_id, start_date, end_date,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Replay failed for %s: %s", lane_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
