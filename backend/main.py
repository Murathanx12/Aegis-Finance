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

from backend.cache import cache_clear, set_cache_ready, cache_ready
from backend.routers import market, crash, simulation, stock, sector, portfolio, news, savings, backtest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def _prewarm_cache():
    """Pre-compute expensive data on startup so first requests are fast.

    With disk cache, this may return almost instantly if data is still valid.
    """
    import asyncio
    try:
        from backend.services.data_fetcher import DataFetcher
        fetcher = DataFetcher()

        # Prewarm market data (used by most endpoints)
        await asyncio.to_thread(fetcher.fetch_market_data)
        logger.info("Prewarmed: market data")

        # Prewarm FRED data
        await asyncio.to_thread(fetcher.fetch_fred_data)
        logger.info("Prewarmed: FRED data")

        set_cache_ready(True)
        logger.info("Cache prewarm complete — ready to serve")
    except Exception as e:
        logger.warning("Cache prewarm failed (non-fatal): %s", e)
        set_cache_ready(True)  # Still mark ready so health check passes


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
            "/api/simulation/sp500",
            "/api/stock/{ticker}",
            "/api/sectors",
            "/api/portfolio/build",
            "/api/news/market",
            "/api/crash/prediction",
        ],
    }


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": "0.2.0",
        "cache_ready": cache_ready(),
    }
