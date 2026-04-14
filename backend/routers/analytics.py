"""
Advanced Analytics Router
===========================

GET /api/analytics/factors/{ticker}      — Fama-French 5-factor decomposition
POST /api/analytics/factors/portfolio    — Portfolio factor decomposition
GET /api/analytics/stress-test/{ticker}  — Single stock stress test
POST /api/analytics/stress-test          — Portfolio stress test
GET /api/analytics/momentum              — Cross-sectional momentum rankings
GET /api/analytics/momentum/{ticker}     — Single stock momentum score
GET /api/analytics/economic-surprise     — Economic surprise index
GET /api/analytics/scenarios             — Available stress test scenarios
GET /api/analytics/crash-timeline        — 60-month crash probability curve
GET /api/analytics/changepoint           — Bayesian changepoint detection
GET /api/analytics/liquidity/{ticker}    — Liquidity risk metrics
GET /api/analytics/liquidity             — Liquidity universe analysis
GET /api/analytics/copula/{ticker_a}/{ticker_b} — Copula tail dependence
POST /api/analytics/copula/portfolio     — Copula portfolio risk
GET /api/analytics/covariance-diagnostics — Denoised covariance diagnostics
"""

import asyncio
import logging
import re

import pandas as pd
from fastapi import APIRouter, HTTPException, Body

from backend.cache import cache_get, cache_set
from backend.config import config

router = APIRouter(prefix="/api/analytics", tags=["analytics"])
logger = logging.getLogger(__name__)

_CACHE_TTL = config["cache"]
_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")


# ── Factor Model ──────────────────────────────────────────────────


@router.get("/factors/{ticker}")
async def get_factor_decomposition(ticker: str):
    """Fama-French 5-factor decomposition for a single stock."""
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail=f"Invalid ticker: {ticker}")

    cache_key = f"factors_{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL.get("ttl_stock", 900))
    if cached is not None:
        return cached

    try:
        from backend.services.factor_model import decompose_stock
        result = await asyncio.to_thread(decompose_stock, ticker)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Insufficient data for {ticker}")
        cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("factor decomposition failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/factors-ff6/{ticker}")
async def get_factor_ff6(ticker: str):
    """FF5 + Momentum (6-factor) decomposition for a single stock."""
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail=f"Invalid ticker: {ticker}")

    cache_key = f"factors_ff6_{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL.get("ttl_stock", 900))
    if cached is not None:
        return cached

    try:
        from backend.services.factor_model import decompose_stock_ff6
        result = await asyncio.to_thread(decompose_stock_ff6, ticker)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Insufficient data for {ticker}")
        # Remove raw residuals from API response (large array)
        result.pop("residuals", None)
        cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("FF6 decomposition failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/factors/pca-residuals")
async def get_pca_residuals(tickers: list[str] = Body(...)):
    """PCA on FF6 residuals — Axioma-style hidden factor discovery."""
    if not tickers or len(tickers) < 5:
        raise HTTPException(status_code=422, detail="Provide at least 5 tickers for PCA")

    tickers = [t.upper() for t in tickers[:30]]  # Cap at 30

    try:
        from backend.services.factor_model import pca_residual_factors
        result = await asyncio.to_thread(pca_residual_factors, tickers)
        if result is None:
            raise HTTPException(status_code=404, detail="Insufficient data for PCA analysis")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("PCA residual analysis failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/factors/portfolio")
async def get_portfolio_factors(weights: dict[str, float] = Body(...)):
    """Fama-French 5-factor decomposition for a portfolio."""
    if not weights or len(weights) > 50:
        raise HTTPException(status_code=422, detail="Provide 1-50 ticker weights")

    try:
        from backend.services.factor_model import decompose_portfolio
        result = await asyncio.to_thread(decompose_portfolio, weights)
        if result is None:
            raise HTTPException(status_code=404, detail="Insufficient data for portfolio")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("portfolio factor decomposition failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Stress Testing ────────────────────────────────────────────────


@router.get("/scenarios")
async def get_stress_scenarios():
    """List available historical stress test scenarios."""
    from backend.services.stress_testing import get_scenario_list
    return {"scenarios": get_scenario_list()}


@router.get("/stress-test/{ticker}")
async def stress_test_stock(ticker: str):
    """Stress test a single stock against historical crises."""
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail=f"Invalid ticker: {ticker}")

    cache_key = f"stress_{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL.get("ttl_stock", 900))
    if cached is not None:
        return cached

    try:
        from backend.services.stress_testing import stress_test_single
        result = await asyncio.to_thread(stress_test_single, ticker)
        cache_set(cache_key, result)
        return result
    except Exception as e:
        logger.error("stress test failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stress-test")
async def stress_test_portfolio(
    weights: dict[str, float] = Body(..., embed=True),
):
    """Stress test a portfolio against historical crises."""
    if not weights or len(weights) > 50:
        raise HTTPException(status_code=422, detail="Provide 1-50 ticker weights")

    try:
        from backend.services.stress_testing import stress_test_portfolio
        result = await asyncio.to_thread(stress_test_portfolio, weights)
        return result
    except Exception as e:
        logger.error("portfolio stress test failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stress-test/hypothetical")
async def hypothetical_stress(
    weights: dict[str, float] = Body(...),
    shocks: dict[str, float] = Body(...),
):
    """User-defined hypothetical stress scenario (Bloomberg MARS style).

    Apply custom macro shocks and see estimated portfolio impact.

    Supported shocks:
    - sp500: S&P 500 return (e.g., -0.15 = -15%)
    - rates: Rate change in bps (e.g., 200 = +200bp)
    - vix: VIX level change (e.g., 20 = +20 points)
    - oil: Oil price change (e.g., -0.30 = -30%)
    - credit_spread: HY OAS widening in bps (e.g., 300)
    - gold: Gold price change (e.g., 0.10 = +10%)
    """
    if not weights or len(weights) > 50:
        raise HTTPException(status_code=422, detail="Provide 1-50 ticker weights")
    if not shocks:
        raise HTTPException(status_code=422, detail="Provide at least one shock")

    valid_shocks = {"sp500", "rates", "vix", "oil", "gold", "usd", "credit_spread"}
    invalid = set(shocks.keys()) - valid_shocks
    if invalid:
        raise HTTPException(status_code=422, detail=f"Invalid shocks: {invalid}. Valid: {valid_shocks}")

    try:
        from backend.services.stress_testing import hypothetical_stress_test
        result = await asyncio.to_thread(hypothetical_stress_test, weights, shocks)
        return result
    except Exception as e:
        logger.error("hypothetical stress test failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Cross-Sectional Momentum ─────────────────────────────────────


@router.get("/momentum")
async def get_momentum_rankings():
    """Cross-sectional momentum rankings for entire stock universe."""
    cached = cache_get("momentum_rankings", _CACHE_TTL.get("ttl_stock", 900))
    if cached is not None:
        return cached

    try:
        from backend.services.cross_sectional_momentum import compute_momentum_rankings
        result = await asyncio.to_thread(compute_momentum_rankings)
        if result is None:
            raise HTTPException(status_code=500, detail="Failed to compute momentum rankings")
        cache_set("momentum_rankings", result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("momentum rankings failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/momentum/{ticker}")
async def get_stock_momentum(ticker: str):
    """Get momentum score for a single stock."""
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail=f"Invalid ticker: {ticker}")

    try:
        from backend.services.cross_sectional_momentum import (
            compute_momentum_rankings, get_momentum_score,
        )
        # Try cache first
        cached_rankings = cache_get("momentum_rankings", _CACHE_TTL.get("ttl_stock", 900))
        if cached_rankings:
            result = get_momentum_score(ticker, cached_rankings)
        else:
            rankings = await asyncio.to_thread(compute_momentum_rankings)
            if rankings:
                cache_set("momentum_rankings", rankings)
            result = get_momentum_score(ticker, rankings)

        if result is None:
            raise HTTPException(status_code=404, detail=f"No momentum data for {ticker}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("momentum score failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Economic Surprise Index ──────────────────────────────────────


@router.get("/economic-surprise")
async def get_economic_surprise():
    """Economic surprise index from FRED data releases."""
    cached = cache_get("economic_surprise", _CACHE_TTL.get("ttl_macro", 300))
    if cached is not None:
        return cached

    try:
        from backend.services.economic_surprise import compute_surprise_index
        result = await asyncio.to_thread(compute_surprise_index)
        if result is None:
            raise HTTPException(status_code=500, detail="Failed to compute economic surprise index")
        cache_set("economic_surprise", result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("economic surprise failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Crash Timeline ────────────────────────────────────────────────


@router.get("/crash-timeline")
async def get_crash_timeline():
    """Monthly crash probability over next 60 months from Monte Carlo."""
    cached = cache_get("crash_timeline", _CACHE_TTL.get("ttl_crash", 1800))
    if cached is not None:
        return cached

    try:
        from backend.services.crash_timeline import estimate_crash_timeline
        from backend.services.data_fetcher import DataFetcher
        from backend.services.risk_scorer import build_risk_score
        from backend.services.regime_detector import detect_regimes

        fetcher = DataFetcher()
        data, _ = await asyncio.to_thread(fetcher.fetch_market_data)
        data["Risk_Score"] = build_risk_score(data)
        _, regime = detect_regimes(data)

        sp500_level = float(data["SP500"].iloc[-1])
        vix = float(data["VIX"].iloc[-1]) if "VIX" in data.columns else 20.0
        risk_score = float(data["Risk_Score"].iloc[-1])
        yield_curve = None
        if "T10Y" in data.columns and "T3M" in data.columns:
            yield_curve = float(data["T10Y"].iloc[-1] - data["T3M"].iloc[-1])

        result = await asyncio.to_thread(
            estimate_crash_timeline,
            current_level=sp500_level,
            regime=regime,
            risk_score=risk_score,
            vix=vix,
            yield_curve=yield_curve,
        )
        cache_set("crash_timeline", result)
        return result
    except Exception as e:
        logger.error("crash timeline failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Changepoint Detection ─────────────────────────────────────────


@router.get("/changepoint")
async def get_changepoint_detection():
    """Bayesian changepoint detection on S&P 500 returns."""
    cached = cache_get("changepoint", _CACHE_TTL.get("ttl_market", 300))
    if cached is not None:
        return cached

    try:
        from backend.services.anomaly_detector import BayesianChangepoint
        from backend.services.data_fetcher import DataFetcher

        fetcher = DataFetcher()
        data, _ = await asyncio.to_thread(fetcher.fetch_market_data)

        returns = data["SP500"].pct_change().dropna()
        detector = BayesianChangepoint()

        recent = await asyncio.to_thread(detector.recent_changepoint, returns, 60)
        result = {
            "changepoint_detected": recent["detected"],
            "days_since_changepoint": recent["days_ago"],
            "max_changepoint_prob": recent["max_prob"],
            "interpretation": (
                f"Regime shift detected {recent['days_ago']} days ago (prob={recent['max_prob']:.2f})"
                if recent["detected"]
                else "No recent regime shift detected in last 60 trading days"
            ),
        }
        cache_set("changepoint", result)
        return result
    except Exception as e:
        logger.error("changepoint detection failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Liquidity Risk ──────────────────────────────────────────────────


@router.get("/liquidity/{ticker}")
async def get_liquidity_metrics(ticker: str):
    """Compute liquidity risk metrics for a stock (Amihud, Roll, LVaR)."""
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail=f"Invalid ticker: {ticker}")

    cache_key = f"liquidity_{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL.get("ttl_stock", 900))
    if cached is not None:
        return cached

    try:
        from backend.services.liquidity_risk import compute_liquidity_metrics
        result = await asyncio.to_thread(compute_liquidity_metrics, ticker)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Insufficient data for {ticker}")
        cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("liquidity analysis failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/liquidity")
async def get_liquidity_universe():
    """Analyze liquidity across the default watchlist."""
    cached = cache_get("liquidity_universe", _CACHE_TTL.get("ttl_sectors", 3600))
    if cached is not None:
        return cached

    try:
        from backend.services.liquidity_risk import analyze_liquidity_universe
        result = await asyncio.to_thread(analyze_liquidity_universe)
        cache_set("liquidity_universe", result)
        return result
    except Exception as e:
        logger.error("liquidity universe analysis failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Copula Tail Dependence ──────────────────────────────────────────


@router.get("/copula/{ticker_a}/{ticker_b}")
async def get_copula_pair(ticker_a: str, ticker_b: str):
    """Copula-based tail dependence analysis for a pair of assets."""
    ticker_a = ticker_a.upper()
    ticker_b = ticker_b.upper()
    if not _TICKER_RE.match(ticker_a) or not _TICKER_RE.match(ticker_b):
        raise HTTPException(status_code=422, detail="Invalid ticker(s)")

    cache_key = f"copula_{ticker_a}_{ticker_b}"
    cached = cache_get(cache_key, _CACHE_TTL.get("ttl_stock", 900))
    if cached is not None:
        return cached

    try:
        from backend.services.copula_tail import analyze_pair_copula
        result = await asyncio.to_thread(analyze_pair_copula, ticker_a, ticker_b)
        if result is None:
            raise HTTPException(status_code=404, detail="Insufficient data for copula analysis")
        cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("copula analysis failed for %s/%s: %s", ticker_a, ticker_b, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/copula/portfolio")
async def get_copula_portfolio_risk(
    tickers: list[str] = Body(...),
    weights: list[float] = Body(None),
):
    """Copula-based portfolio VaR/CVaR (captures tail dependence)."""
    if not tickers or len(tickers) > 30:
        raise HTTPException(status_code=422, detail="Provide 1-30 tickers")

    tickers = [t.upper() for t in tickers]

    try:
        from backend.services.copula_tail import compute_copula_portfolio_risk
        result = await asyncio.to_thread(
            compute_copula_portfolio_risk, tickers, weights
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Insufficient data for copula risk")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("copula portfolio risk failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Covariance Diagnostics ─────────────────────────────────────────


@router.get("/covariance-diagnostics")
async def get_covariance_diagnostics():
    """Compare empirical vs denoised covariance matrix (Random Matrix Theory)."""
    cached = cache_get("cov_diagnostics", _CACHE_TTL.get("ttl_sectors", 3600))
    if cached is not None:
        return cached

    try:
        import yfinance as yf
        from backend.services.covariance import covariance_diagnostics

        # Use default watchlist
        tickers = config.get("stock_universe", {}).get("default_watchlist", [])[:18]
        end = pd.Timestamp.now()
        start = end - pd.Timedelta(days=600)

        prices = await asyncio.to_thread(
            yf.download, tickers, start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"), progress=False, auto_adjust=True,
        )
        if isinstance(prices.columns, pd.MultiIndex):
            close = prices["Close"]
        else:
            close = prices
        returns = close.pct_change().dropna()

        result = covariance_diagnostics(returns)
        cache_set("cov_diagnostics", result)
        return result
    except Exception as e:
        logger.error("covariance diagnostics failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
