"""
Portfolio Analytics Router
============================

POST /api/portfolio/analyze           — Analyze existing portfolio
POST /api/portfolio/build             — Build goal-based portfolio
POST /api/portfolio/optimize          — Advanced optimization (CVaR, risk parity, etc.)
POST /api/portfolio/compare           — Compare all optimization methods
POST /api/portfolio/factor-exposures  — Fama-French 5-factor decomposition
POST /api/portfolio/copula-risk       — Copula-based tail risk (joint crash probability)
"""

import asyncio
import logging
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.services.portfolio_engine import PortfolioEngine, score_risk_profile

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])
logger = logging.getLogger(__name__)

_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")


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
    risk_tolerance: str = Field("moderate", pattern="^(conservative|moderate|aggressive)$")
    investment_amount: float = Field(10000, gt=0)
    time_horizon: str = Field("5y", pattern="^(1y|3y|5y|10y)$")
    method: str = Field("template", pattern="^(template|black-litterman|hrp)$")
    goal: str = Field("growth", pattern="^(preservation|income|growth|aggressive_growth|retirement)$")


class QuestionnaireRequest(BaseModel):
    horizon: str = Field("5y", pattern="^(1y|3y|5y|10y|20y)$")
    risk_tolerance: str = Field("moderate", pattern="^(conservative|moderate|aggressive)$")
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


@router.post("/analyze")
async def analyze_portfolio(request: AnalyzeRequest):
    """Analyze a portfolio: allocations, correlations, VaR/CVaR, Sharpe, risk number."""
    try:
        holdings = [h.model_dump() for h in request.holdings]
        result = await asyncio.to_thread(_analyze_with_risk_number, holdings)
        return result
    except Exception as e:
        logger.error("portfolio analyze failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _analyze_with_risk_number(holdings: list[dict]) -> dict:
    """Run portfolio analysis and attach risk number (1-100)."""
    result = PortfolioEngine.analyze_portfolio(holdings)

    # Compute risk number
    try:
        import yfinance as yf
        import pandas as pd
        from backend.services.risk_number import compute_risk_number

        tickers = [h["ticker"] for h in holdings]
        total_value = sum(h["shares"] * h["current_price"] for h in holdings)
        weights = {}
        for h in holdings:
            w = (h["shares"] * h["current_price"]) / total_value if total_value > 0 else 0
            weights[h["ticker"]] = w

        # Fetch returns for all tickers
        data = yf.download(tickers, period="2y", progress=False)
        if data is not None and "Close" in data.columns.get_level_values(0) if hasattr(data.columns, 'get_level_values') else "Close" in data.columns:
            if len(tickers) == 1:
                close = data["Close"].to_frame(tickers[0])
            else:
                close = data["Close"]
            returns = close.pct_change().dropna()

            # Also get S&P 500 for beta calculation
            bench = yf.download("SPY", period="2y", progress=False)
            bench_returns = None
            if bench is not None and len(bench) > 30:
                bench_returns = bench["Close"].pct_change().dropna()

            risk = compute_risk_number(returns, weights, benchmark_returns=bench_returns)
            result["risk_number"] = risk
    except Exception as e:
        logger.warning("Risk number computation failed: %s", e)

    return result


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


# ── Advanced Optimization ──────────────────────────────────────────


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
    """Marginal Contribution to Risk (MCTR) — which holdings drive portfolio risk."""
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
    alpha, R², and style interpretation for each holding and the portfolio overall.
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
                detail="Copula fitting failed — need at least 2 assets with sufficient history",
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("portfolio copula risk failed: %s", e)
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
