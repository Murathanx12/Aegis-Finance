"""
Portfolio Analytics Router
============================

POST /api/portfolio/analyze  — Analyze existing portfolio
POST /api/portfolio/build    — Build goal-based portfolio
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
    """Analyze a portfolio: allocations, correlations, VaR/CVaR, Sharpe."""
    try:
        holdings = [h.model_dump() for h in request.holdings]
        result = await asyncio.to_thread(PortfolioEngine.analyze_portfolio, holdings)
        return result
    except Exception as e:
        logger.error("portfolio analyze failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


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
        )
        return result
    except Exception as e:
        logger.error("portfolio build failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
