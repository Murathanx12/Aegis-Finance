"""
Aegis Finance — FastAPI Application
=====================================

Backend API for market intelligence, crash prediction,
Monte Carlo simulation, and portfolio analytics.

Usage:
    uvicorn backend.main:app --reload --port 8000
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.cache import cache_clear, set_cache_status, cache_ready, cache_status
from backend.middleware import add_timing_middleware
from backend.observability import install_log_buffer
from backend.routers import market, crash, simulation, stock, sector, portfolio, news, savings, backtest, correlation, options, drift, analytics, copilot, bond, events, markets, crypto, portfolio_intelligence

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Recent WARNING+ records exposed at /api/health/full — install before any
# router/service code runs so early warnings are captured too.
install_log_buffer()

_PROCESS_START = datetime.now(timezone.utc)
# Railway injects the deployed commit; locally falls back to "unknown".
_DEPLOY_COMMIT = os.getenv("RAILWAY_GIT_COMMIT_SHA", "unknown")


async def _prewarm_cache():
    """Pre-compute expensive data on startup so first requests are fast.

    Records real lifecycle state ('ready' vs 'failed') so /api/health can
    honestly report degraded mode. Endpoints still work without prewarm —
    they just pay the first-call latency instead.
    """
    import asyncio
    set_cache_status("pending")
    try:
        from backend.services.data_fetcher import DataFetcher
        fetcher = DataFetcher()

        await asyncio.wait_for(asyncio.to_thread(fetcher.fetch_market_data), timeout=60)
        logger.info("Prewarmed: market data")

        await asyncio.wait_for(asyncio.to_thread(fetcher.fetch_fred_data), timeout=60)
        logger.info("Prewarmed: FRED data")

        set_cache_status("ready")
        logger.info("Cache prewarm complete — ready to serve")
    except asyncio.TimeoutError:
        logger.warning("Cache prewarm timeout — running in degraded mode")
        set_cache_status("failed", "timeout")
    except Exception as e:
        logger.warning("Cache prewarm failed (non-fatal): %s", e)
        set_cache_status("failed", str(e))

    # Background warm of PI fast-lane metrics so /compare is instant.
    # Heavy walk-forward replays are NOT prewarmed — they run on-demand from
    # the dedicated /replay page (where users explicitly opt in to the wait).
    asyncio.create_task(_prewarm_pi_fast_lanes())


async def _prewarm_pi_fast_lanes():
    """Warm the static-weight lane metric cache for the periods /compare uses.

    Each call is ~3 yfinance fetches (SPY/AGG/GLD) that the cache then dedupes.
    Total cost is well under 30s and lets /compare return cached on first hit.
    """
    import asyncio
    from datetime import date, timedelta
    try:
        from backend.routers.portfolio_intelligence import _compute_lane_metrics_fast
        end_d = date.today()
        # Cover the most-clicked periods. ALL/3Y/5Y warm on first user request.
        period_days = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365}

        jobs = []
        for days in period_days.values():
            start_d = end_d - timedelta(days=days)
            for lane in ("conservative", "balanced", "aggressive"):
                jobs.append(asyncio.to_thread(_compute_lane_metrics_fast, lane, start_d, end_d))

        results = await asyncio.gather(*jobs, return_exceptions=True)
        ok = sum(1 for r in results if not isinstance(r, Exception) and r is not None)
        logger.info("PI fast-lane prewarm: %d/%d succeeded", ok, len(jobs))
    except Exception as e:
        logger.warning("PI fast-lane prewarm failed (non-fatal): %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    import asyncio

    logger.info("Aegis Finance API starting")
    # Fire-and-forget: prewarm cache in background so the server starts
    # accepting requests (including health checks) immediately.
    asyncio.create_task(_prewarm_cache())

    # Initialize Portfolio Intelligence DB (runs v2→v3 migration on existing
    # volumes, creating paper_nav + rule_experiments) + reference lanes.
    try:
        from backend.db import init_db
        init_db()
        logger.info("Portfolio Intelligence DB initialized")
    except Exception as e:
        logger.warning("PI DB init failed (non-fatal): %s", e)

    # Idempotently initialize the 3 reference lanes ($100k each, anchored to
    # inception date + config hash). A redeploy must NOT reset or double-init:
    # initialize_lane is a no-op when the lane row already exists. Run in a
    # thread so startup (and health checks) aren't blocked by price fetches.
    async def _init_lanes():
        import asyncio
        from backend.services.portfolio_intelligence.reference_engine import initialize_lane
        for lane in ("conservative", "balanced", "aggressive"):
            try:
                await asyncio.to_thread(initialize_lane, lane)
            except Exception as e:
                logger.warning("Lane init failed for %s (non-fatal): %s", lane, e)
    asyncio.create_task(_init_lanes())

    try:
        from backend.services.portfolio_intelligence.scheduler import setup_scheduler
        setup_scheduler()
    except Exception as e:
        logger.warning("PI scheduler setup failed (non-fatal): %s", e)

    yield

    try:
        from backend.services.portfolio_intelligence.scheduler import shutdown_scheduler
        shutdown_scheduler()
    except Exception as e:
        logger.warning("PI scheduler shutdown failed: %s", e)
    cache_clear()
    logger.info("Aegis Finance API shutdown")


app = FastAPI(
    title="Aegis Finance",
    version="0.2.0",
    description="Free, open-source market intelligence API",
    lifespan=lifespan,
)

_env_origins = os.getenv("ALLOWED_ORIGINS", "")
_origins = (
    [o.strip() for o in _env_origins.split(",") if o.strip()]
    if _env_origins
    else ["http://localhost:3000", "http://127.0.0.1:3000"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request timing (must be added after CORS so it wraps the actual handler)
add_timing_middleware(app)


# ── Register routers ──────────────────────────────────────────
app.include_router(market.router)
app.include_router(crash.router)
app.include_router(simulation.router)
app.include_router(stock.router)
app.include_router(sector.router)
app.include_router(portfolio.router)
app.include_router(news.router)
app.include_router(savings.router)
app.include_router(backtest.router)
app.include_router(correlation.router)
app.include_router(options.router)
app.include_router(drift.router)
app.include_router(analytics.router)
app.include_router(copilot.router)
app.include_router(bond.router)
app.include_router(events.router)
app.include_router(markets.router)
app.include_router(crypto.router)
app.include_router(portfolio_intelligence.router)


@app.get("/")
async def root():
    return {
        "name": "Aegis Finance API",
        "version": "0.2.0",
        "docs": "/docs",
        "health": "/api/health",
        "endpoints": [
            "/api/health",
            "/api/market-status",
            "/api/macro",
            "/api/realtime/{ticker}",
            "/api/simulation/sp500",
            "/api/stock/{ticker}",
            "/api/stock/{ticker}/technicals",
            "/api/stock/{ticker}/sentiment",
            "/api/stock/{ticker}/fundamentals",
            "/api/stock/{ticker}/insiders",
            "/api/sectors",
            "/api/portfolio/build",
            "/api/portfolio/analyze",
            "/api/portfolio/optimize",
            "/api/portfolio/attribution",
            "/api/portfolio/risk-contributions",
            "/api/portfolio/factor-exposures",
            "/api/portfolio/copula-risk",
            "/api/portfolio/commentary",
            "/api/news/market",
            "/api/crash/prediction",
            "/api/options/{ticker}",
            "/api/options/vix-term",
            "/api/earnings/{ticker}",
            "/api/correlation/tail-dependence",
            "/api/analytics/factors/{ticker}",
            "/api/analytics/stress-test/{ticker}",
            "/api/analytics/momentum",
            "/api/analytics/economic-surprise",
            "/api/analytics/scenarios",
            "/api/analytics/sector-rotation",
            "/api/analytics/liquidity/{ticker}",
            "/api/analytics/copula/{ticker_a}/{ticker_b}",
            "/api/analytics/covariance-diagnostics",
            "/api/analytics/crash-timeline",
            "/api/analytics/changepoint",
            "/api/analytics/drawdowns/{ticker}",
            "/api/analytics/conformal-interval",
            "/api/analytics/pairs/{ticker_a}/{ticker_b}",
            "/api/analytics/pairs/scan",
            "/api/savings/project",
            "/api/savings/simulate",
            "/api/savings/safe-rate",
        ],
    }


@app.get("/api/health")
async def health():
    cs = cache_status()
    return {
        "status": "ok",
        "version": "0.2.0",
        "cache_ready": cache_ready(),
        "cache_status": cs["status"],
        "cache_error": cs.get("error"),
    }


@app.get("/api/health/full")
async def health_full():
    """One-call session status: everything /go Phase 0 needs.

    Aggregates deploy identity (commit, uptime), scheduler + per-lane NAV
    freshness, track-record state (per-lane latest NAV + since-inception
    delta), data-source health (yfinance batch rate, FRED series by name),
    and the last ≤50 WARNING+ log records. Strictly read-only.
    """
    from backend.db import get_connection
    from backend.observability import recent_warnings, source_health
    from backend.services.portfolio_intelligence.scheduler import scheduler_health

    sched = scheduler_health()

    track_record: dict = {"lanes": {}, "inception_date": None, "age_days": None}
    try:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT p.id, p.inception_date, p.inception_value, "
                "       n.date AS last_date, n.nav AS last_nav "
                "FROM paper_portfolios p "
                "LEFT JOIN paper_nav n ON n.portfolio_id = p.id "
                "AND n.date = (SELECT MAX(date) FROM paper_nav "
                "              WHERE portfolio_id = p.id) "
                "WHERE p.id IN ('conservative','balanced','aggressive')"
            ).fetchall()
        finally:
            conn.close()
        for r in rows:
            nav = r["last_nav"]
            inception_value = r["inception_value"]
            track_record["lanes"][r["id"]] = {
                "last_date": r["last_date"],
                "nav": round(nav, 2) if nav is not None else None,
                "since_inception_pct": (
                    round((nav / inception_value - 1) * 100, 3)
                    if nav is not None and inception_value else None
                ),
            }
        inceptions = [r["inception_date"] for r in rows if r["inception_date"]]
        if inceptions:
            inception = min(inceptions)
            track_record["inception_date"] = inception
            track_record["age_days"] = (
                datetime.now(timezone.utc).date()
                - datetime.fromisoformat(inception).date()
            ).days
    except Exception as e:
        track_record["error"] = str(e)

    cs = cache_status()
    return {
        "status": "ok",
        "deploy": {
            "commit": _DEPLOY_COMMIT,
            "version": "0.2.0",
            "started_at": _PROCESS_START.isoformat(timespec="seconds"),
            "uptime_seconds": int(
                (datetime.now(timezone.utc) - _PROCESS_START).total_seconds()
            ),
            "cache_status": cs["status"],
        },
        "scheduler": sched,
        "track_record": track_record,
        "data_sources": source_health(),
        "recent_warnings": recent_warnings(),
    }


@app.get("/health/scheduler")
async def health_scheduler():
    """Canary for the Portfolio Intelligence scheduler (point UptimeRobot here).

    Returns HTTP 503 when the scheduler is not running or its jobs are missing
    — a silently-dead scheduler flat-lines the track record, so the canary must
    fail loudly rather than return 200 with running=false.
    """
    from fastapi.responses import JSONResponse
    from backend.services.portfolio_intelligence.scheduler import scheduler_health

    h = scheduler_health()
    healthy = h.get("running") and h.get("n_jobs", 0) >= 3 and h.get("persistent")
    return JSONResponse(status_code=200 if healthy else 503, content=h)


@app.get("/api/providers")
async def providers():
    """Data provider inventory + current availability.

    Reports which upstream sources (yfinance/FRED/Polygon/FMP/Finnhub/AV)
    the engine can reach right now. Clients use this to surface a 'data
    source' badge or fall back to degraded views when a provider is down.
    """
    from backend.services.providers import registry

    healths = registry.health()
    return {
        "providers": [
            {
                "name": h.name,
                "available": h.available,
                "reason": h.reason,
                "capabilities": h.capabilities,
            }
            for h in healths
        ],
        "priority": registry._priority,
    }
