"""
Savings/Retirement Projection Router
=======================================

POST /api/savings/project — Retirement/savings projection calculator
"""

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
