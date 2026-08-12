"""Investment Committee API — the graceful-degradation book (NIGHT-13 §2).

One endpoint: the composed book (benchmark core + evidence-scaled tilts) at
one or all configured capital levels. Deliberately thin — every decision lives
in `services.investment_committee`, shared with the CLI script and the tests.

The endpoint NEVER returns an empty page for an evidence problem: a missing
funnel, a void ranking gate or a refused archetype all degrade to a pure
benchmark core with the reason printed. 5xx is reserved for actual faults.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from backend import config
from backend.services import investment_committee as IC

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ic", tags=["investment-committee"])


@router.get("/committee")
def get_committee(capital: float | None = Query(
        None, gt=0,
        description="one of the configured IC capital levels; omit for all"),
        refresh: bool = Query(False)) -> dict:
    """Ranking gate, evidence coverage, opportunities, and the composed book.

    Funnel-derived inputs are cached (1h TTL); the composition itself is
    computed per request. `refresh` forces the funnel state to recompute.
    """
    if capital is not None and float(capital) not in {
            float(c) for c in config.IC_CAPITAL_LEVELS}:
        raise HTTPException(
            status_code=422,
            detail=f"capital must be one of "
                   f"{[int(c) for c in config.IC_CAPITAL_LEVELS]}")
    try:
        return IC.committee(capital, use_cache=not refresh)
    except Exception as e:                                    # noqa: BLE001
        logger.exception("investment committee page failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
