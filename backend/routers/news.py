"""
News Intelligence Router
===========================

GET /api/news/market       — GDELT macro news signals + event score + LLM summary
GET /api/news/{ticker}     — Stock-specific news from yfinance + LLM analysis
"""

import asyncio
import logging
import re

from fastapi import APIRouter, HTTPException

from backend.cache import cache_get, cache_set, cache_swr
from backend.config import config

router = APIRouter(prefix="/api/news", tags=["news"])
logger = logging.getLogger(__name__)

_CACHE_TTL = config["cache"]

_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")


@router.get("/market")
async def get_market_news():
    """GDELT macro news signals + event score + optional LLM summary."""
    try:
        return await cache_swr(
            "news_market", _CACHE_TTL["ttl_news"], _fetch_market_news
        )
    except Exception as e:
        logger.error("market news failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _fetch_market_news() -> dict:
    from backend.services.news_intelligence import (
        fetch_gdelt_signals, compute_event_score, fetch_stock_news,
        map_news_to_sectors,
    )
    from backend.services.llm_analyzer import summarize_market_news, is_available

    gdelt = fetch_gdelt_signals()
    event = compute_event_score(gdelt)

    # Get some market news for LLM summary
    spy_news = fetch_stock_news("SPY", max_items=10)
    qqq_news = fetch_stock_news("QQQ", max_items=5)
    all_news = spy_news + qqq_news

    llm_summary = None
    if is_available() and all_news:
        llm_summary = summarize_market_news(all_news)

    # Map news to sectors
    sector_impact = map_news_to_sectors(all_news)

    return {
        "gdelt": gdelt,
        "event_score": event,
        "news": all_news[:15],
        "sector_impact": sector_impact,
        "llm_summary": llm_summary,
        "llm_available": is_available(),
    }


@router.get("/brief")
async def get_daily_brief(tickers: str = ""):
    """Personalized daily brief: today's tape + geopolitical read + the
    user's tickers with moves and headlines. Registered BEFORE /{ticker}."""
    from functools import partial
    from backend.services.daily_brief import build_daily_brief

    symbols = []
    for raw in tickers.split(","):
        t = raw.strip().upper()
        if t and _TICKER_RE.match(t) and t not in symbols:
            symbols.append(t)
    symbols = symbols[:15]

    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date().isoformat()
    cache_key = f"daily_brief:{today}:{','.join(sorted(symbols))}"
    try:
        return await cache_swr(
            cache_key, 1800, partial(build_daily_brief, symbols)
        )
    except Exception as e:
        logger.error("daily brief failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}")
async def get_stock_news(ticker: str):
    """Stock-specific news + optional LLM analysis."""
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail="Invalid ticker format")

    cache_key = f"news_stock:{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL["ttl_news"])
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_fetch_stock_news, ticker)
        cache_set(cache_key, result)
        return result
    except Exception as e:
        logger.error("stock news for %s failed: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


def _fetch_stock_news(ticker: str) -> dict:
    from backend.services.news_intelligence import fetch_stock_news
    from backend.services.llm_analyzer import analyze_stock_outlook, is_available

    news = fetch_stock_news(ticker, max_items=15)

    llm_outlook = None
    if is_available() and news:
        import yfinance as yf
        try:
            stock = yf.Ticker(ticker)
            info = stock.info or {}
            fundamentals = {
                "current_price": info.get("regularMarketPrice") or info.get("previousClose"),
                "pe_ratio": info.get("trailingPE"),
                "market_cap": info.get("marketCap"),
                "beta": info.get("beta"),
                "analyst_target": info.get("targetMeanPrice"),
            }
        except Exception:
            fundamentals = {}

        llm_outlook = analyze_stock_outlook(ticker, news, fundamentals)

    return {
        "ticker": ticker,
        "news": news,
        "llm_outlook": llm_outlook,
        "llm_available": is_available(),
    }
