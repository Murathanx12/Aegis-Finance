"""
Savings/Retirement Projection Router
=======================================

POST /api/savings/project     — Deterministic retirement projection
POST /api/savings/simulate    — Monte Carlo retirement simulation (with withdrawals)
POST /api/savings/safe-rate   — Safe withdrawal rate calculator
"""

import asyncio
import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.services.savings_calculator import project_savings

router = APIRouter(prefix="/api/savings", tags=["savings"])
logger = logging.getLogger(__name__)


class SavingsRequest(BaseModel):
    monthly_contribution: float = Field(500, ge=0, le=1_000_000)
    current_savings: float = Field(0, ge=0, le=100_000_000)
    current_age: int = Field(25, ge=1, le=100)
    target_age: int = Field(65, ge=2, le=120)
    risk_level: str = Field("moderate", pattern="^(conservative|moderate|aggressive)$")
    inflation_rate: float = Field(0.025, ge=0, le=0.20)
    target_amount: float = Field(1_000_000, gt=0, le=1_000_000_000)


@router.post("/project")
async def project(request: SavingsRequest):
    """Calculate retirement/savings projection."""
    if request.target_age <= request.current_age:
        return {"error": "Target age must be greater than current age"}

    return project_savings(
        monthly_contribution=request.monthly_contribution,
        current_savings=request.current_savings,
        current_age=request.current_age,
        target_age=request.target_age,
        risk_level=request.risk_level,
        inflation_rate=request.inflation_rate,
        target_amount=request.target_amount,
    )


class RetirementMCRequest(BaseModel):
    current_savings: float = Field(100000, ge=0, le=100_000_000)
    monthly_contribution: float = Field(1000, ge=0, le=100_000)
    monthly_withdrawal: float = Field(5000, ge=0, le=500_000)
    current_age: int = Field(30, ge=18, le=100)
    retirement_age: int = Field(65, ge=20, le=100)
    end_age: int = Field(95, ge=50, le=120)
    risk_level: str = Field("moderate", pattern="^(conservative|moderate|aggressive|all_equity)$")
    inflation_rate: float = Field(0.025, ge=0, le=0.15)
    social_security_monthly: float = Field(0, ge=0, le=50_000)
    social_security_start_age: int = Field(67, ge=62, le=75)
    n_sims: int = Field(5000, ge=500, le=50000)


@router.post("/simulate")
async def simulate_retirement_endpoint(request: RetirementMCRequest):
    """Monte Carlo retirement simulation with contributions and withdrawals.

    Models real market uncertainty (fat tails, volatility clustering) to answer:
    "What is the probability I run out of money before age X?"
    """
    if request.retirement_age <= request.current_age:
        return {"error": "Retirement age must be greater than current age"}
    if request.end_age <= request.retirement_age:
        return {"error": "End age must be greater than retirement age"}

    from backend.services.retirement_mc import simulate_retirement
    try:
        result = await asyncio.to_thread(
            simulate_retirement,
            current_savings=request.current_savings,
            monthly_contribution=request.monthly_contribution,
            monthly_withdrawal=request.monthly_withdrawal,
            current_age=request.current_age,
            retirement_age=request.retirement_age,
            end_age=request.end_age,
            risk_level=request.risk_level,
            inflation_rate=request.inflation_rate,
            social_security_monthly=request.social_security_monthly,
            social_security_start_age=request.social_security_start_age,
            n_sims=request.n_sims,
        )
        return result
    except Exception as e:
        logger.error("retirement simulation failed: %s", e)
        return {"error": str(e)}


class SafeRateRequest(BaseModel):
    savings: float = Field(1_000_000, gt=0, le=100_000_000)
    retirement_years: int = Field(30, ge=5, le=50)
    risk_level: str = Field("moderate", pattern="^(conservative|moderate|aggressive|all_equity)$")
    target_success_rate: float = Field(95.0, ge=50, le=99.9)


@router.post("/safe-rate")
async def safe_withdrawal_rate(request: SafeRateRequest):
    """Compute the maximum safe withdrawal rate for a given success probability.

    Answers: "How much can I withdraw monthly without running out of money?"
    Compares result to the classic 4% rule (Bengen 1994).
    """
    from backend.services.retirement_mc import compute_safe_withdrawal_rate
    try:
        result = await asyncio.to_thread(
            compute_safe_withdrawal_rate,
            savings=request.savings,
            retirement_years=request.retirement_years,
            risk_level=request.risk_level,
            target_success_rate=request.target_success_rate,
        )
        return result
    except Exception as e:
        logger.error("safe withdrawal rate failed: %s", e)
        return {"error": str(e)}
