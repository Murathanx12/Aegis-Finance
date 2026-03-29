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

from backend.cache import cache_clear
from backend.routers import market, crash, simulation, stock, sector, portfolio, news, savings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def _prewarm_cache():
    """Pre-compute expensive data on startup so first requests are fast."""
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
    except Exception as e:
        logger.warning("Cache prewarm failed (non-fatal): %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    logger.info("Aegis Finance API starting")
    await _prewarm_cache()
    yield
    cache_clear()
    logger.info("Aegis Finance API shutdown")


app = FastAPI(
    title="Aegis Finance",
    version="0.1.0",
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


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
