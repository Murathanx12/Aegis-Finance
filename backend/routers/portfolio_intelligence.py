"""
Portfolio Intelligence Router
================================

POST /api/pi/real-portfolio/analyze    — Full metric pack for user holdings
GET  /api/pi/reference/{lane_id}/state — Current allocation + metrics
GET  /api/pi/reference/{lane_id}/history?period= — Equity curve + rebalance log
GET  /api/pi/reference/{lane_id}/explain — Most recent rebalance explanation
GET  /api/pi/compare?ids=&period=      — All lanes + benchmarks side-by-side
POST /api/pi/trigger-check             — Manual rebalance check (Railway cron target)
GET  /api/pi/replay/{lane_id}          — Replay backtest results
"""

import asyncio
import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.schemas.portfolio_intelligence import (
    AnalyzePortfolioRequest,
    ComparisonResponse,
    ExplainResponse,
    HistoryEquityPoint,
    HistoryRebalanceEntry,
    HistoryResponse,
    MetricPack,
    ReplayResult,
    SnapshotResponse,
)
from backend.services.portfolio_intelligence.real_analyzer import analyze_portfolio

router = APIRouter(prefix="/api/pi", tags=["portfolio-intelligence"])
logger = logging.getLogger(__name__)

_VALID_LANES = ("conservative", "balanced", "aggressive")
_VALID_PERIODS = ("1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y", "ALL")


def _period_to_days(period: str) -> Optional[int]:
    """Convert period string to lookback days. Returns None for ALL."""
    period = period.upper()
    if period == "ALL":
        return None
    if period == "YTD":
        today = date.today()
        return (today - date(today.year, 1, 1)).days
    mapping = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365, "3Y": 1095, "5Y": 1825}
    return mapping.get(period, 365)


@router.post("/real-portfolio/analyze", response_model=SnapshotResponse)
async def analyze_real_portfolio(request: AnalyzePortfolioRequest):
    """Analyze a real portfolio: returns SnapshotResponse with MetricPack + risk flags."""
    try:
        result = await asyncio.to_thread(analyze_portfolio, request.holdings)
        return result
    except Exception as e:
        logger.error("Portfolio analysis failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get("/reference/{lane_id}/state", response_model=SnapshotResponse)
async def get_reference_state(lane_id: str):
    """Get current state of a reference portfolio lane."""
    if lane_id not in _VALID_LANES:
        raise HTTPException(status_code=404, detail=f"Unknown lane: {lane_id}")

    from backend.services.portfolio_intelligence.reference_engine import run_reference_check

    try:
        result = await asyncio.to_thread(run_reference_check, lane_id)
        return result
    except Exception as e:
        logger.error("Reference state failed for %s: %s", lane_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reference/{lane_id}/history", response_model=HistoryResponse)
async def get_reference_history(
    lane_id: str,
    period: str = Query(default="1Y", pattern="^(1M|3M|6M|YTD|1Y|3Y|5Y|ALL)$"),
):
    """Equity curve + rebalance log for a reference lane.

    Equity curve is derived from rebalance event timestamps + portfolio values.
    For lanes without rebalance history yet, returns empty arrays plus
    has_rebalance_events=false so the frontend can show an empty state.
    """
    if lane_id not in _VALID_LANES:
        raise HTTPException(status_code=404, detail=f"Unknown lane: {lane_id}")

    from backend.db import get_connection
    from backend.services.portfolio_intelligence.reference_engine import (
        _ensure_lane_initialized,
    )

    try:
        # Make sure parent row exists; otherwise queries return zero events for
        # a different reason than the user expects.
        await asyncio.to_thread(_ensure_lane_initialized, lane_id)

        cutoff_days = _period_to_days(period)
        cutoff_iso: Optional[str] = None
        if cutoff_days is not None:
            cutoff_iso = (datetime.now() - timedelta(days=cutoff_days)).isoformat()

        conn = get_connection()
        try:
            if cutoff_iso:
                rows = conn.execute(
                    "SELECT triggered_at, trigger_reason, crash_prob_3m, explanation, post_weights "
                    "FROM rebalance_events WHERE portfolio_id = ? AND triggered_at >= ? "
                    "ORDER BY id ASC",
                    (lane_id, cutoff_iso),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT triggered_at, trigger_reason, crash_prob_3m, explanation, post_weights "
                    "FROM rebalance_events WHERE portfolio_id = ? "
                    "ORDER BY id ASC",
                    (lane_id,),
                ).fetchall()

            inception = conn.execute(
                "SELECT inception_value FROM paper_portfolios WHERE id = ?",
                (lane_id,),
            ).fetchone()
            inception_value = inception["inception_value"] if inception else 100_000.0
        finally:
            conn.close()

        rebalance_log: list[HistoryRebalanceEntry] = []
        equity_curve: list[HistoryEquityPoint] = []

        for row in rows:
            event_date = row["triggered_at"][:10]
            reason = row["trigger_reason"]
            crash_prob = row["crash_prob_3m"]
            overlay_armed = (reason == "crash_overlay")
            rebalance_log.append(HistoryRebalanceEntry(
                date=event_date,
                reason=reason,
                crash_prob=crash_prob,
                overlay_armed=overlay_armed,
                explanation=row["explanation"],
            ))
            # Live equity curve isn't computed yet (Phase 7 will mark-to-market hourly).
            # For now seed the curve with inception value at each rebalance date so
            # the frontend has a non-empty series to render. Replay endpoint exposes
            # the backtested curve.
            equity_curve.append(HistoryEquityPoint(
                date=event_date,
                value=inception_value,
            ))

        return HistoryResponse(
            portfolio_id=lane_id,
            period=period.upper(),
            equity_curve=equity_curve,
            rebalance_log=rebalance_log,
            has_rebalance_events=len(rebalance_log) > 0,
        )
    except Exception as e:
        logger.error("History fetch failed for %s: %s", lane_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reference/{lane_id}/explain", response_model=ExplainResponse)
async def get_reference_explain(lane_id: str):
    """Most recent rebalance explanation. Shape consistent whether events exist or not."""
    if lane_id not in _VALID_LANES:
        raise HTTPException(status_code=404, detail=f"Unknown lane: {lane_id}")

    from backend.db import get_connection
    from backend.services.portfolio_intelligence.reference_engine import (
        _ensure_lane_initialized,
    )

    try:
        await asyncio.to_thread(_ensure_lane_initialized, lane_id)

        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT explanation, trigger_reason, triggered_at FROM rebalance_events "
                "WHERE portfolio_id = ? ORDER BY id DESC LIMIT 1",
                (lane_id,),
            ).fetchone()
        finally:
            conn.close()

        if not row:
            return ExplainResponse(
                portfolio_id=lane_id,
                explanation=f"No rebalance events yet for {lane_id}.",
                last_rebalance_date=None,
                has_rebalance_events=False,
            )

        return ExplainResponse(
            portfolio_id=lane_id,
            explanation=row["explanation"],
            last_rebalance_date=row["triggered_at"][:10] if row["triggered_at"] else None,
            has_rebalance_events=True,
        )
    except Exception as e:
        logger.error("Explain fetch failed for %s: %s", lane_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/compare", response_model=ComparisonResponse)
async def compare_lanes(
    ids: str = Query(default="conservative,balanced,aggressive"),
    period: str = Query(default="1Y", pattern="^(1M|3M|6M|YTD|1Y|3Y|5Y|ALL)$"),
):
    """Side-by-side comparison of lanes + standard benchmarks.

    Lane MetricPacks come from the replay endpoint (backtested numbers).
    Benchmark MetricPacks (SPY, AGG, 60-40) are computed inline from price data
    over the same period for honest comparison.
    """
    requested_ids = [s.strip() for s in ids.split(",") if s.strip()]
    lane_ids = [i for i in requested_ids if i in _VALID_LANES]
    if not lane_ids:
        lane_ids = list(_VALID_LANES)

    cutoff_days = _period_to_days(period)
    end_d = date.today()
    if cutoff_days is None:
        start_d = date(2021, 1, 4)
    else:
        start_d = end_d - timedelta(days=cutoff_days)

    from backend.services.portfolio_intelligence.replay import ReplayEngine

    engine = ReplayEngine()
    lanes_metrics: dict[str, Optional[MetricPack]] = {}

    for lane_id in lane_ids:
        try:
            result = await asyncio.to_thread(
                engine.run, lane_id, start_d.isoformat(), end_d.isoformat(),
            )
            lanes_metrics[lane_id] = result.metrics
        except Exception as e:
            logger.warning("Compare: replay failed for %s: %s", lane_id, e)
            lanes_metrics[lane_id] = None

    # Benchmarks
    benchmarks_metrics: dict[str, Optional[MetricPack]] = {}
    for bench in ("SPY", "AGG", "60-40"):
        try:
            metrics = await asyncio.to_thread(
                _compute_benchmark_metrics, bench, start_d, end_d,
            )
            benchmarks_metrics[bench] = metrics
        except Exception as e:
            logger.warning("Compare: benchmark %s failed: %s", bench, e)
            benchmarks_metrics[bench] = None

    return ComparisonResponse(
        lanes=lanes_metrics,
        benchmarks=benchmarks_metrics,
        period=period.upper(),
        start_date=start_d.isoformat(),
        end_date=end_d.isoformat(),
    )


def _compute_benchmark_metrics(name: str, start_d: date, end_d: date) -> Optional[MetricPack]:
    """Compute a MetricPack for a single benchmark by name."""
    import numpy as np
    import pandas as pd
    from backend.services.data_fetcher import fetch_safe

    start_s = start_d.isoformat()
    end_s = end_d.isoformat()

    if name in ("SPY", "AGG"):
        series = fetch_safe(name, start_s, end_s, name=name)
        if series is None or len(series) < 20:
            return None
        returns = series.pct_change().dropna()
    elif name == "60-40":
        spy = fetch_safe("SPY", start_s, end_s, name="SPY")
        agg = fetch_safe("AGG", start_s, end_s, name="AGG")
        if spy is None or agg is None or len(spy) < 20 or len(agg) < 20:
            return None
        df = pd.DataFrame({"SPY": spy, "AGG": agg}).dropna()
        rets = df.pct_change().dropna()
        returns = rets["SPY"] * 0.6 + rets["AGG"] * 0.4
    else:
        return None

    if returns.empty:
        return None

    total_return = float((1 + returns).prod() - 1)
    n_years = len(returns) / 252.0
    ann_return = float((1 + total_return) ** (1 / n_years) - 1) if n_years > 0 else 0.0
    ann_vol = float(returns.std() * np.sqrt(252))
    sharpe = float((ann_return - 0.04) / ann_vol) if ann_vol > 1e-10 else None

    cum = (1 + returns).cumprod()
    peak = cum.cummax()
    max_dd = float((cum / peak - 1).min())

    return MetricPack(
        total_return=round(total_return, 6),
        annualized_return=round(ann_return, 6),
        annualized_volatility=round(ann_vol, 6),
        sharpe_ratio=round(sharpe, 4) if sharpe is not None else None,
        max_drawdown=round(max_dd, 6),
    )


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
    if lane_id not in _VALID_LANES:
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
