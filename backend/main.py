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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.cache import cache_clear, set_cache_status, cache_ready, cache_status
from backend.middleware import add_timing_middleware
from backend.routers import market, crash, simulation, stock, sector, portfolio, news, savings, backtest, correlation, options, drift, analytics, copilot, bond, events, markets, crypto

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    import asyncio

    logger.info("Aegis Finance API starting")
    # Fire-and-forget: prewarm cache in background so the server starts
    # accepting requests (including health checks) immediately.
    asyncio.create_task(_prewarm_cache())
    yield
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
