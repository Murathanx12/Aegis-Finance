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
GET /api/analytics/trends-sentiment       — Google Trends fear/greed index
GET /api/analytics/trends-sentiment/{ticker} — Ticker-specific search attention
GET /api/analytics/drawdowns/{ticker}     — Drawdown history + rolling returns
GET /api/analytics/sector-rotation        — Sector rotation model + business cycle
GET /api/analytics/technicals/{ticker}    — Technical analysis (RSI, MACD, BB, ADX)
GET /api/analytics/fixed-income           — Yield curve + credit spreads + real yields
GET /api/analytics/valuation              — Market valuation metrics (CAPE, ERP, Buffett)
GET /api/analytics/pairs/{ticker_a}/{ticker_b} — Pair cointegration analysis
GET /api/analytics/pairs/scan             — Scan universe for cointegrated pairs
GET /api/analytics/tail-risk/{ticker}     — Tail risk metrics (Sortino, Omega, Calmar, etc.)
GET /api/analytics/survival-model         — Cox PH crash timing (market-level hazard rates)
GET /api/analytics/cross-asset            — Cross-asset macro intelligence dashboard
GET /api/analytics/macro-regime           — Growth × inflation quadrant classification
GET /api/analytics/prediction-confidence  — Confidence grade + drift-adjusted MC interval
GET /api/analytics/earnings-calendar      — Upcoming earnings (Finnhub, per ticker or all)
GET /api/analytics/analyst-consensus/{ticker} — Unified analyst targets + rating breakdown
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


# ── VIX Term Structure ────────────────────────────────────────────


@router.get("/vix-term-structure")
async def get_vix_term_structure():
    """VIX term structure analysis (contango/backwardation regime signal)."""
    cached = cache_get("vix_term_structure", _CACHE_TTL.get("ttl_market", 300))
    if cached is not None:
        return cached

    try:
        from backend.services.regime_detector import get_vix_term_structure_state
        from backend.services.data_fetcher import DataFetcher

        fetcher = DataFetcher()
        data, _ = await asyncio.to_thread(fetcher.fetch_market_data)

        result = get_vix_term_structure_state(data)
        cache_set("vix_term_structure", result)
        return result
    except Exception as e:
        logger.error("VIX term structure failed: %s", e)
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


# ── Google Trends Sentiment ────────────────────────────────────────


@router.get("/trends-sentiment")
async def get_trends_sentiment():
    """Google Trends fear/greed sentiment index.

    Uses search volume for fear terms (crash, recession, bear market)
    vs greed terms (buy stocks, bull market) as a contrarian indicator.
    """
    cached = cache_get("trends_sentiment", _CACHE_TTL.get("ttl_macro", 300))
    if cached is not None:
        return cached

    try:
        from backend.services.trends_sentiment import compute_fear_greed_trends
        result = await asyncio.to_thread(compute_fear_greed_trends)
        if result is None:
            raise HTTPException(
                status_code=503,
                detail="Google Trends data unavailable (pytrends not installed or rate-limited)",
            )
        cache_set("trends_sentiment", result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("trends sentiment failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trends-sentiment/{ticker}")
async def get_ticker_trends(ticker: str):
    """Search attention for a specific stock ticker (Google Trends)."""
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail=f"Invalid ticker: {ticker}")

    cache_key = f"trends_{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL.get("ttl_stock", 900))
    if cached is not None:
        return cached

    try:
        from backend.services.trends_sentiment import get_ticker_attention
        result = await asyncio.to_thread(get_ticker_attention, ticker)
        if result is None:
            raise HTTPException(
                status_code=503,
                detail=f"Google Trends data unavailable for {ticker}",
            )
        cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("ticker trends failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Drawdown & Rolling Return Analysis ────────────────────────────


@router.get("/drawdowns/{ticker}")
async def get_drawdown_analysis(ticker: str, period: str = "10y"):
    """Full drawdown history, rolling returns, and rolling risk metrics.

    Portfolio Visualizer-style analysis: every drawdown with depth, duration,
    and recovery time, plus rolling 1Y/3Y/5Y returns and Sharpe/Sortino.
    """
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail=f"Invalid ticker: {ticker}")
    if period not in ("1y", "2y", "5y", "10y", "20y", "max"):
        raise HTTPException(status_code=422, detail="period must be 1y/2y/5y/10y/20y/max")

    cache_key = f"drawdowns_{ticker}_{period}"
    cached = cache_get(cache_key, _CACHE_TTL.get("ttl_stock", 900))
    if cached is not None:
        return cached

    try:
        from backend.services.drawdown_analyzer import full_drawdown_analysis
        result = await asyncio.to_thread(full_drawdown_analysis, ticker, period)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Insufficient data for {ticker}")
        cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("drawdown analysis failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Conformal Prediction Intervals ────────────────────────────────


@router.get("/conformal-interval")
async def get_conformal_interval(
    crash_prob: float = 0.10,
    horizon: str = "3m",
    alpha: float = 0.10,
):
    """Conformal prediction interval for a crash probability.

    Returns calibrated uncertainty band with finite-sample coverage guarantee.
    If conformal scores are not pre-computed, returns a heuristic interval.

    Args:
        crash_prob: Crash probability as decimal (0.10 = 10%)
        horizon: Prediction horizon (3m, 6m, 12m)
        alpha: Miscoverage rate (0.10 = 90% coverage)
    """
    if not 0 <= crash_prob <= 1:
        raise HTTPException(status_code=422, detail="crash_prob must be between 0 and 1")
    if horizon not in ("3m", "6m", "12m"):
        raise HTTPException(status_code=422, detail="horizon must be 3m, 6m, or 12m")
    if not 0.01 <= alpha <= 0.50:
        raise HTTPException(status_code=422, detail="alpha must be between 0.01 and 0.50")

    try:
        from backend.services.conformal_predictor import conformal_crash_interval
        result = conformal_crash_interval(crash_prob, horizon=horizon, alpha=alpha)
        return {
            "crash_prob_pct": round(crash_prob * 100, 1),
            "interval": {
                "lower_pct": round(result["lower"] * 100, 1),
                "upper_pct": round(result["upper"] * 100, 1),
                "width_pct": round(result["width"] * 100, 1),
            },
            "coverage": result["coverage_target"],
            "method": result["method"],
            "n_calibration": result["n_calibration"],
            "horizon": horizon,
        }
    except Exception as e:
        logger.error("conformal interval failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Earnings Calendar (Finnhub provider) ──────────────────────────


@router.get("/earnings-calendar")
async def get_earnings_calendar(
    ticker: str | None = None,
    days_ahead: int = 30,
):
    """Upcoming earnings releases. Optional ticker filter; defaults to all.

    Provider: Finnhub (single-provider capability — returns [] when unkeyed).
    """
    if days_ahead < 1 or days_ahead > 180:
        raise HTTPException(status_code=422, detail="days_ahead must be 1..180")

    cache_key = f"earnings_cal:{ticker or 'all'}:{days_ahead}"
    cached = cache_get(cache_key, 1800)  # 30min cache
    if cached is not None:
        return cached

    try:
        from backend.services.providers import registry

        events = await asyncio.to_thread(
            registry.get_earnings_calendar, ticker, days_ahead
        )
        result = {
            "days_ahead": days_ahead,
            "ticker": ticker.upper() if ticker else None,
            "count": len(events),
            "events": [
                {
                    "ticker": e.ticker,
                    "date": e.date,
                    "eps_estimate": e.eps_estimate,
                    "eps_actual": e.eps_actual,
                    "revenue_estimate": e.revenue_estimate,
                    "revenue_actual": e.revenue_actual,
                    "time": e.time,
                    "source": e.source,
                }
                for e in events
            ],
        }
        cache_set(cache_key, result)
        return result
    except Exception as e:
        logger.error("earnings calendar failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Analyst Consensus (multi-provider with fallback) ──────────────


@router.get("/analyst-consensus/{ticker}")
async def get_analyst_consensus(ticker: str):
    """Unified analyst target + rating breakdown.

    Prefers Finnhub for freshness, falls back to FMP, then yfinance. Response
    includes source provenance so callers can tell which vendor served it.
    """
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail=f"Invalid ticker: {ticker}")

    cache_key = f"analyst_consensus:{ticker}"
    cached = cache_get(cache_key, 3600)
    if cached is not None:
        return cached

    try:
        from backend.services.providers import registry

        est = await asyncio.to_thread(registry.get_analyst_estimates, ticker)
        if est is None:
            raise HTTPException(
                status_code=404,
                detail=f"No analyst data for {ticker}",
            )
        result = est.to_dict()
        cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("analyst consensus failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Prediction Confidence ──────────────────────────────────────────


@router.get("/prediction-confidence")
async def get_prediction_confidence(
    mc_p10: float,
    mc_median: float,
    mc_p90: float,
    garch_nu: float | None = None,
    garch_persistence: float | None = None,
    data_years: float = 5.0,
    drift_severity: str | None = None,
    beta: float = 1.0,
):
    """Score the confidence of a Monte Carlo forecast and widen its bands.

    Combines drift severity, MC spread tightness, GARCH tail quality, data
    sufficiency, and beta stability into a single A-F grade plus drift-
    adjusted P10/P90. Useful when an external workflow produced MC outputs
    and wants Aegis's uncertainty view on them.
    """
    from backend.services.prediction_confidence import score_prediction_confidence

    if mc_p10 > mc_median or mc_median > mc_p90:
        raise HTTPException(
            status_code=422,
            detail="Must satisfy mc_p10 <= mc_median <= mc_p90",
        )
    if drift_severity and drift_severity not in (
        "none",
        "low",
        "moderate",
        "high",
        "critical",
    ):
        raise HTTPException(
            status_code=422,
            detail="drift_severity must be one of none/low/moderate/high/critical",
        )

    try:
        return score_prediction_confidence(
            mc_p10_return=mc_p10,
            mc_p90_return=mc_p90,
            mc_median_return=mc_median,
            garch_nu=garch_nu,
            garch_persistence=garch_persistence,
            data_years=data_years,
            drift_severity=drift_severity,
            beta=beta,
        )
    except Exception as e:
        logger.error("prediction confidence failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Sector Rotation ──────────────────────────────────────────────


@router.get("/sector-rotation")
async def get_sector_rotation():
    """Sector rotation analysis: multi-timeframe relative strength, business cycle phase."""
    cached = cache_get("sector_rotation", 3600)  # 1hr cache
    if cached is not None:
        return cached

    try:
        from backend.services.sector_rotation import compute_sector_rotation
        result = await asyncio.to_thread(compute_sector_rotation)
        if "error" not in result:
            cache_set("sector_rotation", result)
        return result
    except Exception as e:
        logger.error("sector rotation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Fixed Income ──────────────────────────────────────────────


@router.get("/fixed-income")
async def get_fixed_income():
    """Yield curve analysis, credit spreads, real yields, and stress detection."""
    cached = cache_get("fixed_income", 1800)  # 30 min cache
    if cached is not None:
        return cached

    try:
        from backend.services.fixed_income import get_fixed_income_dashboard
        result = await asyncio.to_thread(get_fixed_income_dashboard)
        if "error" not in result:
            cache_set("fixed_income", result)
        return result
    except Exception as e:
        logger.error("fixed income failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Market Valuation ──────────────────────────────────────────


@router.get("/valuation")
async def get_market_valuation():
    """Market valuation metrics: CAPE, equity risk premium, Buffett Indicator."""
    cached = cache_get("market_valuation", 3600)  # 1hr cache
    if cached is not None:
        return cached

    try:
        from backend.services.valuation import compute_market_valuation
        result = await asyncio.to_thread(compute_market_valuation)
        if "error" not in result:
            cache_set("market_valuation", result)
        return result
    except Exception as e:
        logger.error("market valuation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Pair Trading & Cointegration ──────────────────────────────


@router.get("/pairs/{ticker_a}/{ticker_b}")
async def get_pair_analysis(ticker_a: str, ticker_b: str):
    """Cointegration analysis for a specific pair.

    Returns hedge ratio, cointegration test results (Engle-Granger + Johansen),
    Ornstein-Uhlenbeck half-life, Hurst exponent, z-score, and trading signal.
    """
    ticker_a = ticker_a.upper()
    ticker_b = ticker_b.upper()
    if not _TICKER_RE.match(ticker_a) or not _TICKER_RE.match(ticker_b):
        raise HTTPException(status_code=422, detail="Invalid ticker format")
    if ticker_a == ticker_b:
        raise HTTPException(status_code=422, detail="Tickers must be different")

    cache_key = f"pair_{ticker_a}_{ticker_b}"
    cached = cache_get(cache_key, _CACHE_TTL.get("ttl_stock", 900))
    if cached is not None:
        return cached

    try:
        from backend.services.pair_trading import get_pair_signal
        result = await asyncio.to_thread(get_pair_signal, ticker_a, ticker_b)
        if "error" not in result:
            cache_set(cache_key, result)
        return result
    except Exception as e:
        logger.error("pair analysis %s/%s failed: %s", ticker_a, ticker_b, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pairs/scan")
async def scan_pairs_endpoint(
    sector: str = None,
    top_n: int = 20,
):
    """Scan the stock universe for cointegrated pairs.

    Optionally filter by sector. Returns top N pairs ranked by quality score.
    """
    if top_n < 1 or top_n > 50:
        top_n = 20

    cache_key = f"pair_scan_{sector or 'all'}_{top_n}"
    cached = cache_get(cache_key, 3600)  # 1hr cache (expensive scan)
    if cached is not None:
        return cached

    try:
        from backend.services.pair_trading import scan_pairs
        tickers = config.get("pair_trading", {}).get("scan_tickers", [])
        if not tickers:
            # Fallback to default watchlist
            tickers = config.get("stock_universe", {}).get("default_watchlist", [])

        result = await asyncio.to_thread(
            scan_pairs, tickers, top_n=top_n, sector_filter=sector
        )
        if "error" not in result:
            cache_set(cache_key, result)
        return result
    except Exception as e:
        logger.error("pair scan failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Tail Risk Analytics ──────────────────────────────────────────


@router.get("/tail-risk/{ticker}")
async def get_tail_risk(ticker: str, period: str = "5y"):
    """Institutional-grade tail risk metrics for a stock.

    Returns Sortino, Omega, Calmar ratios, downside deviation, max drawdown
    duration, tail concentration index, Ulcer Index, win rate, and profit factor.
    """
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail=f"Invalid ticker: {ticker}")
    if period not in ("1y", "2y", "5y", "10y", "max"):
        raise HTTPException(status_code=422, detail="period must be 1y/2y/5y/10y/max")

    cache_key = f"tail_risk_{ticker}_{period}"
    cached = cache_get(cache_key, _CACHE_TTL.get("ttl_stock", 900))
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_compute_tail_risk, ticker, period)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Insufficient data for {ticker}")
        cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("tail risk failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


def _compute_tail_risk(ticker: str, period: str) -> dict | None:
    import numpy as np
    import yfinance as yf
    from backend.services.tail_risk import compute_tail_risk_metrics

    period_map = {"1y": "1y", "2y": "2y", "5y": "5y", "10y": "10y", "max": "max"}
    t = yf.Ticker(ticker)
    hist = t.history(period=period_map[period], auto_adjust=True)
    if hist is None or len(hist) < 60:
        return None

    daily_returns = hist["Close"].pct_change().dropna().values
    metrics = compute_tail_risk_metrics(daily_returns)

    # Add context
    ann_return = float(np.mean(daily_returns) * 252 * 100)
    ann_vol = float(np.std(daily_returns) * np.sqrt(252) * 100)
    sharpe = float((ann_return / 100 - 0.04) / (ann_vol / 100)) if ann_vol > 0.1 else None

    return {
        "ticker": ticker,
        "period": period,
        "annual_return_pct": round(ann_return, 2),
        "annual_volatility_pct": round(ann_vol, 2),
        "sharpe_ratio": round(sharpe, 4) if sharpe else None,
        **metrics,
    }


# ── Survival Model (Cox PH Crash Timing) ─────────────────────────


@router.get("/survival-model")
async def get_survival_model():
    """Cox Proportional Hazards crash timing model.

    Returns market-level crash probabilities at 3m/6m/12m horizons,
    top risk factors by Cox coefficient magnitude, and training diagnostics.
    """
    cached = cache_get("survival_model", _CACHE_TTL.get("ttl_crash", 1800))
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_compute_survival_model)
        if result is None:
            raise HTTPException(
                status_code=503,
                detail="Survival model unavailable (lifelines not installed or insufficient data)",
            )
        cache_set("survival_model", result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("survival model failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _compute_survival_model() -> dict | None:
    from backend.services.data_fetcher import DataFetcher
    from backend.services.survival_model import CrashSurvivalModel

    try:
        from engine.training.features import build_feature_matrix
    except ImportError:
        return None

    fetcher = DataFetcher()
    data, _ = fetcher.fetch_market_data()
    fred_data = fetcher.fetch_fred_data()
    features = build_feature_matrix(data, fred_data=fred_data)

    cox = CrashSurvivalModel()
    train_end = int(len(features) * 0.8)
    train_result = cox.train(features, data, train_end)

    if not train_result.get("success"):
        return None

    probabilities = {}
    for h in ["3m", "6m", "12m"]:
        cox_prob = float(cox.predict_proba(features.iloc[[-1]], h)[0])
        probabilities[h] = round(cox_prob * 100, 1)

    top_features = cox.get_top_features(n=7)

    return {
        "method": "Cox Proportional Hazards (semi-parametric)",
        "probabilities": probabilities,
        "top_risk_factors": [
            {"feature": name, "coefficient": round(coef, 4), "direction": "increases risk" if coef > 0 else "decreases risk"}
            for name, coef in top_features
        ],
        "training": {
            "n_train": train_result.get("n_train"),
            "n_events": train_result.get("n_events"),
            "features_used": len(cox._available_features),
        },
        "interpretation": (
            f"Cox model estimates {probabilities.get('3m', '?')}% crash risk in 3 months, "
            f"{probabilities.get('12m', '?')}% in 12 months"
        ),
        "last_updated": str(data.index[-1].date()),
    }


# ── Cross-Asset Macro Regime Monitor ────────────────────────────────


@router.get("/cross-asset")
async def get_cross_asset_dashboard():
    """Full cross-asset macro intelligence dashboard.

    Returns growth×inflation quadrant, risk-on/off score,
    cross-asset momentum table, correlation matrix, and
    intermarket divergence alerts.
    """
    cached = cache_get("cross_asset_dashboard", _CACHE_TTL["ttl_market"])
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_compute_cross_asset_dashboard)
        cache_set("cross_asset_dashboard", result)
        return result
    except Exception as e:
        logger.error("cross-asset dashboard failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _compute_cross_asset_dashboard() -> dict:
    from backend.services.cross_asset_monitor import compute_cross_asset_dashboard
    return compute_cross_asset_dashboard()


@router.get("/macro-regime")
async def get_macro_regime():
    """Current macro regime (growth × inflation quadrant only).

    Lighter-weight endpoint — returns just the regime classification
    without the full momentum table and correlation matrix.
    """
    cached = cache_get("macro_regime", _CACHE_TTL["ttl_market"])
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_compute_macro_regime)
        cache_set("macro_regime", result)
        return result
    except Exception as e:
        logger.error("macro-regime failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _compute_macro_regime() -> dict:
    from backend.services.cross_asset_monitor import compute_macro_regime
    return compute_macro_regime()


@router.get("/allocation-strategies")
async def list_allocation_strategies():
    """List the pre-defined asset-allocation strategies the backtester knows about."""
    from backend.services.allocation_backtester import NAMED_STRATEGIES
    return {"strategies": [{"name": n, "weights": w} for n, w in NAMED_STRATEGIES.items()]}


@router.get("/allocation-backtest/{name}")
async def backtest_named_allocation(name: str, start: str = "2005-01-01",
                                     rebalance: str = "quarterly"):
    """Backtest a named allocation (60_40, 3_fund, permanent_portfolio, all_weather, ...)."""
    cache_key = f"aa_backtest_named:{name}:{start}:{rebalance}"
    cached = cache_get(cache_key, _CACHE_TTL.get("ttl_market", 3600))
    if cached is not None:
        return cached

    try:
        from backend.services.allocation_backtester import backtest_named
        result = await asyncio.to_thread(backtest_named, name, start=start, rebalance_freq=rebalance)
        if "error" in result:
            raise HTTPException(status_code=422, detail=result["error"])
        cache_set(cache_key, result)
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("allocation backtest (named=%s) failed: %s", name, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/allocation-backtest")
async def backtest_custom_allocation(payload: dict = Body(...)):
    """Backtest a user-defined allocation. JSON body: {weights: {TICKER: weight}, start, rebalance}."""
    weights = payload.get("weights") or {}
    start = payload.get("start", "2005-01-01")
    rebalance = payload.get("rebalance_freq", "quarterly")
    if not weights:
        raise HTTPException(status_code=422, detail="weights dict is required")

    try:
        from backend.services.allocation_backtester import backtest_allocation
        result = await asyncio.to_thread(backtest_allocation, weights=weights,
                                          start=start, rebalance_freq=rebalance)
        if "error" in result:
            raise HTTPException(status_code=422, detail=result["error"])
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("custom allocation backtest failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/treemap")
async def get_market_treemap(window: str = "1d"):
    """Finviz-style sector → ticker treemap (size=market cap, color=return).

    Query params:
      - window: one of 1d | 1w | 1m | ytd
    """
    if window not in {"1d", "1w", "1m", "ytd"}:
        raise HTTPException(status_code=422, detail=f"window must be one of 1d,1w,1m,ytd (got {window!r})")

    cache_key = f"market_treemap:{window}"
    cached = cache_get(cache_key, _CACHE_TTL.get("ttl_stock", 900))
    if cached is not None:
        return cached

    try:
        from backend.services.market_treemap import build_treemap
        result = await asyncio.to_thread(build_treemap, window)
        cache_set(cache_key, result)
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("market treemap failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
