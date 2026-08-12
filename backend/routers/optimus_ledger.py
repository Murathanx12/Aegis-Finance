"""
Optimus Prediction-Ledger Router
================================

GET /api/optimus/calibration — specialist × observable × horizon cross-tab
    (honest counts: sparse cells print n and None; pending never scored)
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/optimus", tags=["optimus"])
logger = logging.getLogger(__name__)


@router.get("/calibration")
async def get_calibration():
    """Calibration report for the prediction ledger, with ledger health attached."""
    try:
        from backend.services.ledger_calibration import calibration_report
        return await asyncio.to_thread(calibration_report)
    except Exception as e:
        logger.error("ledger calibration report failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
