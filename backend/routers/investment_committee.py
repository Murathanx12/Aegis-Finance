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


@router.get("/decisions")
def get_decisions(date: str | None = Query(
        None, description="YYYY-MM-DD; omit for today")) -> dict:
    """Today's Decision Contract and the lifecycle states it has reached.

    READ ONLY, and it builds nothing: the contract is written by the morning
    click and by the unattended daily pass, and an endpoint that could build one
    on request would let a page create a decision at a time nobody declared.

    404, not an empty page, when no contract exists for the day. That is the
    opposite of `/committee`'s rule and deliberately so: the committee always
    has an answer (a benchmark core), while "the engine has not said what it
    would buy today" is an absence, and an absence dressed as `{"rows": []}`
    reads identically to a day on which every candidate was refused.
    """
    from backend.services import decision_contract as DC
    from backend.services import decision_ledger as DL

    try:
        blob = DC.latest(date)
    except ValueError as e:
        raise HTTPException(status_code=422,
                            detail=f"date must be YYYY-MM-DD: {e}") from e
    except Exception as e:                                    # noqa: BLE001
        logger.exception("decision contract read failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
    if blob is None:
        raise HTTPException(
            status_code=404,
            detail=(f"no decision contract for "
                    f"{date or 'today'}. It is written by the morning click "
                    f"(/api/control/morning) and by the unattended daily pass; "
                    f"this endpoint reads one and never builds one."))
    try:
        blob["ledger"] = DL.summary(blob.get("date"))
    except Exception as e:                                    # noqa: BLE001
        blob["ledger"] = {"error": f"{type(e).__name__}: {e}"}
    return blob


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
