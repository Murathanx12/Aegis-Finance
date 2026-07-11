"""
Portfolio Analytics Router
============================

POST /api/portfolio/analyze           â€” Analyze existing portfolio
POST /api/portfolio/build             â€” Build goal-based portfolio
POST /api/portfolio/optimize          â€” Advanced optimization (CVaR, risk parity, etc.)
POST /api/portfolio/compare           â€” Compare all optimization methods
POST /api/portfolio/factor-exposures  â€” Fama-French 5-factor decomposition
POST /api/portfolio/copula-risk       â€” Copula-based tail risk (joint crash probability)
POST /api/portfolio/benchmark         â€” Benchmark analytics (tracking error, IR, active share, capture)
"""

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # annotation-only; pandas is imported lazily at runtime
    import pandas as pd

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field, field_validator

from backend.cache import cache_get, cache_set
from backend.services.portfolio_engine import PortfolioEngine, score_risk_profile

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])
logger = logging.getLogger(__name__)

_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")
_PRICE_CACHE_TTL = 600  # 10 min â€” yfinance is slow + analyze is hot path


def _weights_key(weights: dict) -> str:
    """Stable cache key from a weights dict (rounded to 4 decimals)."""
    items = sorted((t, round(float(w), 4)) for t, w in weights.items())
    return ";".join(f"{t}:{w}" for t, w in items)


def _engine_analyze_cached(holdings: list[dict], weights: dict) -> dict:
    """Cached wrapper around PortfolioEngine.analyze_portfolio.

    The engine output is deterministic in (tickers, weights) given current prices.
    Cache by weights â€” total_value is recomputed by caller for current prices.
    """
    cache_key = f"portfolio:analyze:engine:{_weights_key(weights)}"
    cached = cache_get(cache_key, _PRICE_CACHE_TTL)
    if cached is not None:
        # total_value depends on current prices â€” recompute fresh
        total_value = sum(h["shares"] * h["current_price"] for h in holdings)
        return {**cached, "total_value": total_value}
    result = PortfolioEngine.analyze_portfolio(holdings)
    cache_set(cache_key, result)
    return result


def _prefetch_close_5y(tickers: list[str]) -> Optional["pd.DataFrame"]:
    """Download 5y daily Close for tickers+SPY once, cache for 10min.

    Returns wide DataFrame indexed by date with one column per ticker (incl. SPY).
    The 5y window is a superset of the 2y window used by risk_number, so callers
    can slice instead of re-downloading.
    """
    import yfinance as yf
    universe = sorted(set(tickers) | {"SPY"})
    cache_key = f"portfolio:analyze:close5y:{','.join(universe)}"
    cached = cache_get(cache_key, _PRICE_CACHE_TTL)
    if cached is not None:
        return cached
    try:
        data = yf.download(universe, period="5y", progress=False, auto_adjust=True)
        if data is None or len(data) == 0:
            return None
        if hasattr(data.columns, "get_level_values") and "Close" in data.columns.get_level_values(0):
            close = data["Close"]
        elif "Close" in data.columns:
            close = data[["Close"]]
            close.columns = [universe[0]]
        else:
            return None
        cache_set(cache_key, close)
        return close
    except Exception as e:
        logger.warning("prefetch close 5y failed: %s", e)
        return None


class Holding(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10)
    shares: float = Field(..., gt=0)
    current_price: float = Field(..., gt=0)

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v: str) -> str:
        v = v.upper()
        if not _TICKER_RE.match(v):
            raise ValueError("Ticker must be 1-10 uppercase alphanumeric characters or dots")
        return v


class AnalyzeRequest(BaseModel):
    holdings: list[Holding] = Field(..., min_length=1, max_length=50)


class BuildRequest(BaseModel):
    risk_tolerance: str = Field("moderate", pattern="^(conservative|moderate|aggressive|max_growth)$")
    investment_amount: float = Field(10000, gt=0)
    time_horizon: str = Field("5y", pattern="^(1y|3y|5y|10y)$")
    method: str = Field("template", pattern="^(template|black-litterman|hrp)$")
    goal: str = Field("growth", pattern="^(preservation|income|growth|aggressive_growth|retirement)$")


class QuestionnaireRequest(BaseModel):
    horizon: str = Field("5y", pattern="^(1y|3y|5y|10y|20y)$")
    risk_tolerance: str = Field("moderate", pattern="^(conservative|moderate|aggressive|max_growth)$")
    loss_reaction: str = Field("hold", pattern="^(sell|hold|buy_more)$")
    experience: str = Field("beginner", pattern="^(none|beginner|intermediate|advanced)$")
    income_stability: str = Field("stable", pattern="^(unstable|stable|very_stable)$")
    goal: str = Field("growth", pattern="^(preservation|income|growth|aggressive_growth)$")


@router.post("/questionnaire")
async def portfolio_questionnaire(request: QuestionnaireRequest):
    """Score a risk profile from questionnaire answers and return recommended allocation."""
    try:
        profile = score_risk_profile(request.model_dump())
        # Auto-build a portfolio from the profile
        portfolio = await asyncio.to_thread(
            PortfolioEngine.build_portfolio,
            risk_tolerance=profile["allocation_style"],
            investment_amount=10000,
            time_horizon=request.horizon,
        )
        return {**profile, "recommended_portfolio": portfolio}
    except Exception as e:
        logger.error("portfolio questionnaire failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class GuidanceHolding(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10)
    shares: float = Field(..., gt=0)
    cost_basis: float | None = Field(None, gt=0)


class GuidanceRequest(BaseModel):
    holdings: list[GuidanceHolding] = Field(..., min_length=1, max_length=50)


@router.post("/guidance")
async def get_portfolio_guidance(request: GuidanceRequest):
    """Per-position guidance: P&L, move unusualness, Chandelier trailing-stop
    level + distance, forward-collected signal readings, and behavioral nudges
    (disposition effect). Descriptive levels and context â€” never orders."""
    def _worker():
        from backend.services.portfolio_guidance import portfolio_guidance
        return portfolio_guidance([h.model_dump() for h in request.holdings])

    try:
        return await asyncio.to_thread(_worker)
    except Exception as e:
        logger.error("portfolio guidance failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze")
async def analyze_portfolio(request: AnalyzeRequest):
    """Analyze a portfolio: allocations, correlations, VaR/CVaR, Sharpe, risk number.

    The 6 sub-analyses (risk number, factor exposures, stress test, attribution/MCTR,
    benchmark analytics, drawdowns) run concurrently in the thread pool â€” yfinance
    downloads dominate wall time, so parallel I/O cuts latency by ~5-6x.
    """
    import time
    t0 = time.perf_counter()
    n_holdings = len(request.holdings)
    try:
        holdings = [h.model_dump() for h in request.holdings]

        tickers = [h["ticker"] for h in holdings]
        total_value = sum(h["shares"] * h["current_price"] for h in holdings)
        weights = {
            h["ticker"]: (h["shares"] * h["current_price"]) / total_value if total_value > 0 else 0
            for h in holdings
        }

        # Single I/O wave: engine analyze + prefetch + 4 independent helpers all
        # start at once. The 2 helpers that need prefetched closes wait inline.
        async def _risk_then(close_fut):
            close = await close_fut
            return await asyncio.to_thread(_compute_risk_number, holdings, weights, close)

        async def _drawdowns_then(close_fut):
            close = await close_fut
            return await asyncio.to_thread(_compute_portfolio_drawdowns, holdings, weights, close)

        async def _timed(name, coro):
            ts = time.perf_counter()
            try:
                return name, (await coro), time.perf_counter() - ts
            except Exception as e:
                return name, e, time.perf_counter() - ts

        prefetch_task = asyncio.create_task(asyncio.to_thread(_prefetch_close_5y, tickers))
        all_results = await asyncio.gather(
            _timed("engine", asyncio.to_thread(_engine_analyze_cached, holdings, weights)),
            _timed("factor", asyncio.to_thread(_compute_factor_exposures, weights)),
            _timed("stress", asyncio.to_thread(_compute_stress_test, weights)),
            _timed("attr", asyncio.to_thread(_compute_attribution_mctr, holdings)),
            _timed("bench", asyncio.to_thread(_compute_benchmark_analytics, weights)),
            _timed("risk", _risk_then(asyncio.shield(prefetch_task))),
            _timed("dd", _drawdowns_then(asyncio.shield(prefetch_task))),
        )
        timings = {name: round(dt, 2) for name, _, dt in all_results}
        result = {}
        for name, val, _dt in all_results:
            if isinstance(val, Exception):
                logger.warning("portfolio analyze %s error: %s", name, val)
            elif val:
                result.update(val)

        elapsed = time.perf_counter() - t0
        logger.info("portfolio analyze: %d holdings in %.2fs  per_task=%s", n_holdings, elapsed, timings)
        return result
    except Exception as e:
        elapsed = time.perf_counter() - t0
        logger.error("portfolio analyze failed after %.2fs (%d holdings): %s", elapsed, n_holdings, e)
        raise HTTPException(status_code=500, detail=str(e))


def _analyze_with_risk_number(holdings: list[dict]) -> dict:
    """Synchronous full portfolio analysis for tearsheet rendering.

    Composes the same sub-analyses as the async analyze_portfolio endpoint,
    run sequentially (tearsheets are not latency-sensitive). Returns the merged
    analysis dict (metrics, holdings, risk_number, factor_exposures, stress_test)
    consumed by render_portfolio_tearsheet_html / _xlsx.
    """
    tickers = [h["ticker"] for h in holdings]
    total_value = sum(h["shares"] * h["current_price"] for h in holdings)
    weights = {
        h["ticker"]: (h["shares"] * h["current_price"]) / total_value if total_value > 0 else 0
        for h in holdings
    }

    close_5y = _prefetch_close_5y(tickers)

    result: dict = {}
    for part in (
        _engine_analyze_cached(holdings, weights),
        _compute_factor_exposures(weights),
        _compute_stress_test(weights),
        _compute_risk_number(holdings, weights, close_5y),
    ):
        if part:
            result.update(part)
    return result


def _compute_risk_number(holdings: list[dict], weights: dict, close_5y=None) -> dict:
    """Risk number (1-100) â€” uses prefetched 5y close (slices last ~2y)."""
    try:
        from backend.services.risk_number import compute_risk_number

        tickers = [h["ticker"] for h in holdings]
        if close_5y is None or len(close_5y) == 0:
            return {}
        # Slice ~2y (504 trading days) to match original behavior
        close = close_5y.tail(504)
        ticker_close = close[[t for t in tickers if t in close.columns]]
        if ticker_close.empty:
            return {}
        returns = ticker_close.pct_change().dropna()

        bench_returns = None
        if "SPY" in close.columns:
            bench_returns = close["SPY"].pct_change().dropna()

        return {"risk_number": compute_risk_number(returns, weights, benchmark_returns=bench_returns)}
    except Exception as e:
        logger.warning("Risk number computation failed: %s", e)
        return {}


def _compute_factor_exposures(weights: dict) -> dict:
    """Fama-French 5-factor portfolio decomposition."""
    cache_key = f"portfolio:analyze:factor:{_weights_key(weights)}"
    cached = cache_get(cache_key, _PRICE_CACHE_TTL)
    if cached is not None:
        return cached
    try:
        from backend.services.factor_model import decompose_portfolio
        factor_result = decompose_portfolio(weights)
        if not factor_result:
            cache_set(cache_key, {})  # cache empties too â€” avoids re-failing
            return {}
        out = {
            "factor_exposures": {
                "r_squared": factor_result.get("portfolio", {}).get("r_squared"),
                "alpha_annual": factor_result.get("portfolio", {}).get("alpha_annual"),
                "market_beta": factor_result.get("portfolio", {}).get("market_beta"),
                "style": factor_result.get("portfolio", {}).get("style"),
                "stocks": {
                    t: {"market_beta": s.get("market_beta"), "style": s.get("style")}
                    for t, s in factor_result.get("stocks", {}).items()
                },
            }
        }
        cache_set(cache_key, out)
        return out
    except Exception as e:
        logger.warning("Factor exposure computation failed: %s", e)
        return {}


def _compute_stress_test(weights: dict) -> dict:
    """Historical scenario stress test (GFC, COVID, etc.)."""
    cache_key = f"portfolio:analyze:stress:{_weights_key(weights)}"
    cached = cache_get(cache_key, _PRICE_CACHE_TTL)
    if cached is not None:
        return cached
    try:
        from backend.services.stress_testing import stress_test_portfolio
        stress = stress_test_portfolio(weights)
        if not stress or "scenarios" not in stress:
            return {}
        scenario_summaries = {
            s["name"]: {
                "portfolio_drawdown_pct": round(s.get("portfolio_drawdown", 0) * 100, 2),
                "sp500_drawdown_pct": round(s.get("sp500_drawdown", 0) * 100, 2),
                "relative_to_market": s.get("relative_to_market"),
            }
            for s in stress["scenarios"].values()
        }
        worst = stress.get("worst_case", {})
        out = {
            "stress_test": {
                "scenarios": scenario_summaries,
                "worst_scenario": worst.get("name"),
                "worst_drawdown_pct": round(worst.get("drawdown", 0) * 100, 2) if worst.get("drawdown") is not None else None,
            }
        }
        cache_set(cache_key, out)
        return out
    except Exception as e:
        logger.warning("Stress test computation failed: %s", e)
        return {}


def _compute_attribution_mctr(holdings: list[dict]) -> dict:
    """Brinson-Fachler attribution + MCTR risk decomposition."""
    weights_proxy = {h["ticker"]: h.get("shares", 0) * h.get("current_price", 0) for h in holdings}
    cache_key = f"portfolio:analyze:attr:{_weights_key(weights_proxy)}"
    cached = cache_get(cache_key, _PRICE_CACHE_TTL)
    if cached is not None:
        return cached
    try:
        from backend.services.attribution import full_portfolio_analytics
        attr_result = full_portfolio_analytics(holdings, benchmark_ticker="SPY", period="1mo")
        if not attr_result:
            cache_set(cache_key, {})
            return {}
        out: dict = {}
        attribution = attr_result.get("attribution", {})
        out["attribution_summary"] = {
            "period": attr_result.get("period"),
            "total_allocation_effect": attribution.get("total_allocation_effect"),
            "total_selection_effect": attribution.get("total_selection_effect"),
            "total_interaction_effect": attribution.get("total_interaction_effect"),
            "total_active_return": attribution.get("total_active_return"),
            "portfolio_return": attribution.get("portfolio_return"),
            "benchmark_return": attribution.get("benchmark_return"),
        }
        risk_contrib = attr_result.get("risk_contributions")
        if risk_contrib and "contributions" in risk_contrib:
            out["mctr_summary"] = {
                "portfolio_vol": risk_contrib.get("portfolio_volatility"),
                "top_risk_contributors": [
                    {
                        "ticker": c.get("ticker"),
                        "weight_pct": c.get("weight_pct"),
                        "risk_contrib_pct": c.get("risk_contribution_pct"),
                        "mctr": c.get("mctr"),
                    }
                    for c in sorted(
                        risk_contrib["contributions"],
                        key=lambda x: abs(x.get("risk_contribution_pct", 0)),
                        reverse=True,
                    )[:5]
                ],
            }
        cache_set(cache_key, out)
        return out
    except Exception as e:
        logger.warning("Inline attribution/MCTR failed: %s", e)
        return {}


def _compute_benchmark_analytics(weights: dict) -> dict:
    """Tracking error, IR, active share, capture ratios vs SPY."""
    cache_key = f"portfolio:analyze:bench:{_weights_key(weights)}"
    cached = cache_get(cache_key, _PRICE_CACHE_TTL)
    if cached is not None:
        return cached
    try:
        from backend.services.benchmark_analytics import compute_benchmark_analytics
        bench_result = compute_benchmark_analytics(weights, benchmark="SPY")
        if not bench_result:
            return {}
        out = {
            "benchmark_analytics": {
                "tracking_error_pct": bench_result["tracking_error_pct"],
                "information_ratio": bench_result["information_ratio"],
                "active_return_annual_pct": bench_result["active_return_annual_pct"],
                "active_share": bench_result.get("active_share", {}).get("active_share_pct") if bench_result.get("active_share") else None,
                "active_share_label": bench_result.get("active_share", {}).get("label") if bench_result.get("active_share") else None,
                "up_capture": bench_result["capture_ratios"].get("up_capture"),
                "down_capture": bench_result["capture_ratios"].get("down_capture"),
                "beta_vs_benchmark": bench_result["regression"].get("beta") if bench_result["regression"].get("available") else None,
                "r_squared": bench_result["regression"].get("r_squared") if bench_result["regression"].get("available") else None,
                "management_style": bench_result["interpretation"].get("management_style"),
                "insights": bench_result["interpretation"].get("insights", []),
            }
        }
        cache_set(cache_key, out)
        return out
    except Exception as e:
        logger.warning("Benchmark analytics failed: %s", e)
        return {}


def _compute_portfolio_drawdowns(holdings: list[dict], weights: dict, close_5y=None) -> dict:
    """Portfolio-level drawdown history + rolling returns. Uses prefetched 5y close."""
    try:
        import numpy as np
        from backend.services.drawdown_analyzer import analyze_drawdowns, compute_rolling_returns

        tickers = [h["ticker"] for h in holdings]
        if close_5y is None or len(close_5y) <= 60:
            return {}
        ticker_close = close_5y[[t for t in tickers if t in close_5y.columns]]
        if ticker_close.empty:
            return {}
        returns = ticker_close.pct_change().dropna()

        w = np.array([weights.get(t, 0) for t in returns.columns])
        if w.sum() <= 0:
            return {}
        w = w / w.sum()
        port_returns = (returns * w).sum(axis=1)
        port_prices = (1 + port_returns).cumprod() * 100

        dd_result = analyze_drawdowns(port_prices)
        rolling = compute_rolling_returns(port_prices, windows=[252])
        return {
            "portfolio_drawdowns": {
                "total_drawdowns": dd_result["summary"].get("n_drawdowns", 0),
                "max_drawdown_pct": dd_result["summary"].get("max_depth_pct"),
                "avg_recovery_days": dd_result["summary"].get("avg_recovery_days"),
                "current_drawdown_pct": dd_result["current"]["depth_pct"] if dd_result.get("current") else 0.0,
                "rolling_return_1y": rolling.get(252, {}).get("current"),
            }
        }
    except Exception as e:
        logger.warning("Portfolio drawdown analysis failed: %s", e)
        return {}


class ProjectRequest(BaseModel):
    holdings: list[Holding] = Field(..., min_length=1, max_length=50)
    years: int = Field(1, ge=1, le=30)
    monthly_add: float = Field(0, ge=0, le=1_000_000)


@router.post("/project")
async def project_portfolio(request: ProjectRequest):
    """Project portfolio value forward."""
    try:
        holdings = [h.model_dump() for h in request.holdings]
        result = await asyncio.to_thread(
            PortfolioEngine.project_portfolio,
            holdings,
            years=request.years,
            monthly_add=request.monthly_add,
        )
        return result
    except Exception as e:
        logger.error("portfolio projection failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/build")
async def build_portfolio(request: BuildRequest):
    """Build a goal-based portfolio allocation."""
    try:
        result = await asyncio.to_thread(
            PortfolioEngine.build_portfolio,
            risk_tolerance=request.risk_tolerance,
            investment_amount=request.investment_amount,
            time_horizon=request.time_horizon,
            method=request.method,
            goal=request.goal,
        )
        return result
    except Exception as e:
        logger.error("portfolio build failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# â”€â”€ Advanced Optimization â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class OptimizeRequest(BaseModel):
    tickers: list[str] = Field(..., min_length=2, max_length=50)
    method: str = Field("mean_cvar", pattern="^(mean_cvar|risk_parity|max_diversification|hrp)$")
    lookback_days: int = Field(504, ge=126, le=1260)


@router.post("/optimize")
async def optimize_portfolio(request: OptimizeRequest):
    """Advanced portfolio optimization with institutional methods.

    Methods:
    - mean_cvar: Minimize Conditional VaR (tail risk)
    - risk_parity: Equal risk contribution
    - max_diversification: Maximize diversification ratio
    - hrp: Hierarchical Risk Parity
    """
    from backend.services.portfolio_optimizer import (
        optimize_mean_cvar, optimize_risk_parity,
        optimize_max_diversification, optimize_hrp,
    )

    tickers = [t.upper() for t in request.tickers]
    method_map = {
        "mean_cvar": optimize_mean_cvar,
        "risk_parity": optimize_risk_parity,
        "max_diversification": optimize_max_diversification,
        "hrp": optimize_hrp,
    }

    fn = method_map.get(request.method)
    if not fn:
        raise HTTPException(status_code=422, detail=f"Unknown method: {request.method}")

    try:
        result = await asyncio.to_thread(fn, tickers, request.lookback_days)
        if result is None:
            raise HTTPException(status_code=404, detail="Insufficient data for optimization")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("portfolio optimization failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class AttributionRequest(BaseModel):
    holdings: list[Holding] = Field(..., min_length=1, max_length=50)
    benchmark: str = Field("SPY", min_length=1, max_length=10)
    period: str = Field("1mo", pattern="^(1mo|3mo|1y|ytd)$")


@router.post("/attribution")
async def portfolio_attribution(request: AttributionRequest):
    """Brinson-Fachler performance attribution vs benchmark (Bloomberg PORT style).

    Decomposes active return into: allocation effect, selection effect, interaction effect.
    """
    from backend.services.attribution import full_portfolio_analytics

    holdings_data = [h.model_dump() for h in request.holdings]
    try:
        result = await asyncio.to_thread(
            full_portfolio_analytics, holdings_data, request.benchmark, request.period
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Insufficient data for attribution")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("portfolio attribution failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class RiskContribRequest(BaseModel):
    tickers: list[str] = Field(..., min_length=2, max_length=50)
    weights: list[float] = Field(..., min_length=2, max_length=50)

    @field_validator("weights")
    @classmethod
    def validate_weights(cls, v: list[float], info) -> list[float]:
        tickers = info.data.get("tickers")
        if tickers is not None and len(v) != len(tickers):
            raise ValueError(
                f"weights length ({len(v)}) must match tickers length ({len(tickers)})"
            )
        if any(w < 0 for w in v):
            raise ValueError("weights must be non-negative")
        return v


@router.post("/risk-contributions")
async def risk_contributions(request: RiskContribRequest):
    """Marginal Contribution to Risk (MCTR) â€” which holdings drive portfolio risk."""
    from backend.services.attribution import compute_risk_contributions

    tickers = [t.upper() for t in request.tickers]
    try:
        result = await asyncio.to_thread(
            compute_risk_contributions, tickers, request.weights
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Insufficient data for risk contribution")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("risk contribution failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/commentary")
async def portfolio_commentary(request: AnalyzeRequest):
    """AI-generated portfolio commentary (Bloomberg PORT Enterprise style)."""
    from backend.services.llm_analyzer import generate_portfolio_commentary, is_available

    if not is_available():
        raise HTTPException(status_code=503, detail="No LLM provider configured (set ANTHROPIC_API_KEY or DEEPSEEK_API_KEY)")

    holdings_data = [
        {"ticker": h.ticker, "weight": h.shares * h.current_price, "sector": ""}
        for h in request.holdings
    ]
    # Normalize weights
    total = sum(h["weight"] for h in holdings_data)
    if total > 0:
        for h in holdings_data:
            h["weight"] /= total

    try:
        result = await asyncio.to_thread(
            generate_portfolio_commentary, holdings_data, {}, None, None
        )
        if result is None:
            raise HTTPException(status_code=500, detail="LLM analysis failed")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("portfolio commentary failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class FactorExposureRequest(BaseModel):
    holdings: list[Holding] = Field(..., min_length=1, max_length=50)
    lookback_days: int = Field(756, ge=126, le=1260)


@router.post("/factor-exposures")
async def portfolio_factor_exposures(request: FactorExposureRequest):
    """Fama-French 5-factor decomposition for a portfolio.

    Shows factor loadings (market beta, size, value, profitability, investment),
    alpha, RÂ², and style interpretation for each holding and the portfolio overall.
    """
    from backend.services.factor_model import decompose_portfolio

    # Convert holdings to weights dict
    total_value = sum(h.shares * h.current_price for h in request.holdings)
    if total_value <= 0:
        raise HTTPException(status_code=400, detail="Portfolio has no value")

    weights = {
        h.ticker: (h.shares * h.current_price) / total_value
        for h in request.holdings
    }

    try:
        result = await asyncio.to_thread(
            decompose_portfolio, weights, request.lookback_days
        )
        if result is None:
            raise HTTPException(
                status_code=404,
                detail="Insufficient data for factor decomposition",
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("portfolio factor exposure failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class CopulaRiskRequest(BaseModel):
    holdings: list[Holding] = Field(..., min_length=2, max_length=50)
    lookback_days: int = Field(504, ge=126, le=1260)


@router.post("/copula-risk")
async def portfolio_copula_risk(request: CopulaRiskRequest):
    """Copula-based tail risk analysis for a portfolio.

    Measures joint crash risk using Clayton/Gumbel/Frank/Student-t copulas.
    Returns tail dependence coefficients and copula-based VaR/CVaR.
    """
    from backend.services.copula_tail import compute_copula_risk_from_returns
    import numpy as np
    import yfinance as yf

    tickers = [h.ticker for h in request.holdings]
    total_value = sum(h.shares * h.current_price for h in request.holdings)
    if total_value <= 0:
        raise HTTPException(status_code=400, detail="Portfolio has no value")

    weights_arr = np.array([
        (h.shares * h.current_price) / total_value for h in request.holdings
    ])

    try:
        import pandas as pd
        # Fetch aligned price data for all tickers
        data = yf.download(tickers, period=f"{max(request.lookback_days // 252, 2)}y", progress=False)
        prices = data["Close"] if "Close" in data.columns or len(tickers) > 1 else pd.DataFrame(data["Close"])
        if prices.empty or len(prices) < 60:
            raise HTTPException(
                status_code=404,
                detail="Insufficient price data for copula analysis",
            )

        returns = prices.pct_change().dropna()

        result = await asyncio.to_thread(
            compute_copula_risk_from_returns, returns, weights_arr
        )
        if result is None:
            raise HTTPException(
                status_code=404,
                detail="Copula fitting failed â€” need at least 2 assets with sufficient history",
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("portfolio copula risk failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class BenchmarkRequest(BaseModel):
    holdings: list[Holding] = Field(..., min_length=1, max_length=50)
    benchmark: str = Field("SPY", min_length=1, max_length=10)
    lookback_days: int = Field(504, ge=63, le=1260)


@router.post("/benchmark")
async def portfolio_benchmark_analytics(request: BenchmarkRequest):
    """Bloomberg PORT-style benchmark-relative analytics.

    Tracking error, information ratio, active share (Cremers & Petajisto),
    up/down capture ratios, rolling tracking error, regression stats,
    and period return comparison vs benchmark.
    """
    from backend.services.benchmark_analytics import compute_benchmark_analytics

    total_value = sum(h.shares * h.current_price for h in request.holdings)
    if total_value <= 0:
        raise HTTPException(status_code=400, detail="Portfolio has no value")

    weights = {
        h.ticker: (h.shares * h.current_price) / total_value
        for h in request.holdings
    }

    try:
        result = await asyncio.to_thread(
            compute_benchmark_analytics,
            weights,
            request.benchmark.upper(),
            request.lookback_days,
        )
        if result is None:
            raise HTTPException(
                status_code=404,
                detail="Insufficient data for benchmark analytics",
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("benchmark analytics failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class CompareRequest(BaseModel):
    tickers: list[str] = Field(..., min_length=2, max_length=50)
    lookback_days: int = Field(504, ge=126, le=1260)


@router.post("/compare")
async def compare_portfolios(request: CompareRequest):
    """Compare all optimization methods side-by-side (Bloomberg PORT style)."""
    from backend.services.portfolio_optimizer import compare_methods

    tickers = [t.upper() for t in request.tickers]
    try:
        result = await asyncio.to_thread(compare_methods, tickers, request.lookback_days)
        return result
    except Exception as e:
        logger.error("portfolio comparison failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class MPCRequest(BaseModel):
    tickers: list[str] = Field(..., min_length=2, max_length=30)
    current_weights: dict[str, float] | None = None
    benchmark_weights: dict[str, float] | None = None
    sector_map: dict[str, str] | None = None
    sector_caps: dict[str, float] | None = None
    gamma: float = Field(3.0, gt=0, le=100)
    transaction_cost_bps: float = Field(5.0, ge=0, le=500)
    holding_penalty: float = Field(0.0, ge=0, le=10)
    max_weight: float = Field(0.35, gt=0, le=1.0)
    min_weight: float = Field(0.0, ge=-0.5, le=0.5)
    tracking_error_limit: float | None = Field(None, ge=0.001, le=1.0)
    allow_shorts: bool = False
    horizon: int = Field(1, ge=1, le=12)
    return_decay: float = Field(0.0, ge=0, le=0.95)
    lookback_days: int = Field(504, ge=126, le=1260)

    @field_validator("tickers")
    @classmethod
    def upper_tickers(cls, v: list[str]) -> list[str]:
        out = [t.upper() for t in v]
        for t in out:
            if not _TICKER_RE.match(t):
                raise ValueError(f"Invalid ticker: {t}")
        return out


@router.post("/optimize-mpc")
async def optimize_mpc(request: MPCRequest):
    """Convex single-/multi-period portfolio optimizer.

    Solves mean-variance with explicit transaction costs, tracking error
    constraint, sector caps, and optional short-sale permission. When
    horizon > 1, re-solves each step (rolling MPC) with optional
    alpha-decay across steps.
    """
    import yfinance as yf
    import pandas as pd
    from backend.services.mpc_optimizer import (
        optimize_single_period,
        optimize_multi_period,
    )

    tickers = request.tickers
    try:
        # Fetch price history once, compute returns + Sigma + mu
        period_days = request.lookback_days
        start = (pd.Timestamp.today() - pd.Timedelta(days=int(period_days * 1.6))).strftime(
            "%Y-%m-%d"
        )
        end = pd.Timestamp.today().strftime("%Y-%m-%d")
        frame = await asyncio.to_thread(
            yf.download, tickers, start=start, end=end, progress=False, group_by="ticker"
        )
        if frame is None or frame.empty:
            raise HTTPException(status_code=422, detail="Could not fetch price data")

        closes: dict[str, pd.Series] = {}
        if len(tickers) == 1:
            # Single-ticker shape is different
            if "Close" in frame.columns:
                closes[tickers[0]] = frame["Close"].dropna()
        else:
            for t in tickers:
                try:
                    if t in frame.columns.get_level_values(0):
                        closes[t] = frame[t]["Close"].dropna()
                except Exception:
                    continue

        available = [t for t in tickers if t in closes and len(closes[t]) > 30]
        if len(available) < 2:
            raise HTTPException(
                status_code=422,
                detail="Need â‰¥2 tickers with sufficient history",
            )

        price_df = pd.DataFrame({t: closes[t] for t in available}).dropna()
        if len(price_df) < 30:
            raise HTTPException(status_code=422, detail="Not enough overlapping history")

        rets = price_df.pct_change().dropna()
        mu = rets.mean() * 252  # annualised
        sigma = rets.cov() * 252

        # Restrict weight dictionaries to available tickers
        cw = {k: v for k, v in (request.current_weights or {}).items() if k in available}
        bw = {k: v for k, v in (request.benchmark_weights or {}).items() if k in available}
        sm = {k: v for k, v in (request.sector_map or {}).items() if k in available}

        kwargs = dict(
            gamma=request.gamma,
            transaction_cost_bps=request.transaction_cost_bps,
            holding_penalty=request.holding_penalty,
            max_weight=request.max_weight,
            min_weight=request.min_weight,
            tracking_error_limit=request.tracking_error_limit,
            benchmark_weights=bw if bw else None,
            sector_map=sm if sm else None,
            sector_caps=request.sector_caps,
            allow_shorts=request.allow_shorts,
        )

        if request.horizon == 1:
            result = await asyncio.to_thread(
                optimize_single_period,
                expected_returns=mu,
                cov_matrix=sigma,
                current_weights=cw if cw else None,
                **kwargs,
            )
        else:
            result = await asyncio.to_thread(
                optimize_multi_period,
                expected_returns=mu,
                cov_matrix=sigma,
                current_weights=cw if cw else None,
                horizon=request.horizon,
                return_decay=request.return_decay,
                **kwargs,
            )

        result["tickers"] = available
        result["lookback_days"] = request.lookback_days
        result["mu_annualised"] = {t: float(mu[t]) for t in available}
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("optimize-mpc failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class TearsheetRequest(BaseModel):
    holdings: list[Holding] = Field(..., min_length=1, max_length=50)
    title: str = Field("Portfolio Tearsheet", max_length=80)


@router.post("/tearsheet.html", response_class=HTMLResponse)
async def portfolio_tearsheet_html(request: TearsheetRequest):
    """Return a self-contained HTML tearsheet (print-to-PDF from the browser)."""
    try:
        holdings = [h.model_dump() for h in request.holdings]
        from backend.routers.portfolio import _analyze_with_risk_number
        from backend.services.tearsheet import render_portfolio_tearsheet_html

        analysis = await asyncio.to_thread(_analyze_with_risk_number, holdings)
        html_doc = render_portfolio_tearsheet_html(analysis, title=request.title)
        return HTMLResponse(content=html_doc)
    except Exception as e:
        logger.error("tearsheet HTML failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/currency-exposure")
async def portfolio_currency_exposure(request: dict):
    """Multi-currency portfolio breakdown + recent FX attribution.

    Body:
        positions: list of {ticker, shares, current_price, [currency], [return_local_pct]}
        base: target reporting currency (default USD)

    Returns currency exposure (with HHI), recent 30d return decomposition
    into local vs FX components, and an interpretation string. Bloomberg
    PORT / FactSet style: foreign holdings should never silently roll FX
    P&L into 'stock return'.
    """
    positions = request.get("positions") or request.get("holdings") or []
    base = (request.get("base") or "USD").upper()

    if not positions:
        raise HTTPException(status_code=422, detail="positions list required")
    if len(positions) > 100:
        raise HTTPException(status_code=422, detail="max 100 positions")

    try:
        from backend.services.portfolio_currency import portfolio_currency_report
        result = await asyncio.to_thread(
            portfolio_currency_report, positions, base
        )
        if "error" in result:
            raise HTTPException(status_code=422, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("portfolio currency exposure failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tearsheet.xlsx")
async def portfolio_tearsheet_xlsx(request: TearsheetRequest):
    """Return a multi-sheet .xlsx workbook with tearsheet data."""
    try:
        holdings = [h.model_dump() for h in request.holdings]
        from backend.routers.portfolio import _analyze_with_risk_number
        from backend.services.tearsheet import render_portfolio_tearsheet_xlsx

        analysis = await asyncio.to_thread(_analyze_with_risk_number, holdings)
        blob = await asyncio.to_thread(render_portfolio_tearsheet_xlsx, analysis)
        filename = f"aegis-tearsheet-{request.title.replace(' ', '_')[:40]}.xlsx"
        return Response(
            content=blob,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("tearsheet xlsx failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
