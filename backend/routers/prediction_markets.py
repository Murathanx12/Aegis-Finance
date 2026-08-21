"""Prediction-market context surface (TRIAL-PREDMARKET-1).

Read-only view of the newest Kalshi daily snapshot. DESCRIPTIVE CONTEXT —
the banner on every response is part of the contract, not decoration: this
corpus is never a signal, and no scoring path may read it before a successor
trial passes.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backend.services import prediction_markets

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/prediction-markets",
                   tags=["prediction-markets"])


@router.get("")
async def prediction_markets_summary():
    """Newest daily snapshot summary — disk only, no fetch on request."""
    try:
        return prediction_markets.latest_summary()
    except Exception as e:  # noqa: BLE001
        logger.error("prediction-market summary failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500,
                            detail=f"prediction-market summary failed: {e}")


@router.get("/divergence")
async def prediction_markets_divergence():
    """Cross-venue divergence on the newest day both venues snapshotted.

    Same-day measurement only (TRIAL-PREDMARKET-2's deciding metric also
    needs persistence to the next snapshot). Disk only, no fetch.
    """
    from backend.services import prediction_market_matching

    try:
        return prediction_market_matching.latest_divergence()
    except Exception as e:  # noqa: BLE001
        logger.error("divergence report failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500,
                            detail=f"divergence report failed: {e}")
