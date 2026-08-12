"""Why the book moved — attribution always, hypotheses only when gradeable.

GET /api/why-moved/attribution — the deterministic decomposition, no LLM.
GET /api/why-moved/explain     — the same, plus seven independent specialists
                                 whose cross-asset assertions are graded
                                 against that same day immediately.

Neither endpoint ever returns a cause. The second returns competing
hypotheses side by side with their corroboration scores; collapsing them into
a winner is not a feature this router is missing, it is a claim the data
cannot support (see backend/services/why_moved.py).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from backend.services import why_moved as wm

router = APIRouter(prefix="/api/why-moved", tags=["why-moved"])
logger = logging.getLogger(__name__)


def _positions() -> list[tuple[str, float]]:
    return wm.book_positions()


@router.get("/attribution")
async def attribution(as_of: str | None = Query(
        None, description="Trading day to explain (ISO). Walks back to the "
                          "last session at or before it; the date actually "
                          "used is returned as `as_of`.")):
    """Deterministic attribution for one day. No language model is involved."""
    try:
        return await asyncio.to_thread(
            wm.run_why_moved, _positions(), as_of or str(date.today()),
            with_hypotheses=False)
    except wm.PricingError as e:
        # 422, not 500 and not a zero: the request is well formed, the book
        # simply cannot be priced for that day, and a plausible $0.00 would be
        # worse than an error.
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:                            # noqa: BLE001
        logger.error("why-moved attribution failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explain")
async def explain(
        as_of: str | None = Query(None, description="Trading day to explain (ISO)."),
        lenses: str | None = Query(
            None, description="Comma-separated subset of the specialist lenses; "
                              "default is all of them."),
        write_ledger: bool = Query(
            False, description="Append the minted PredictionRecords to the "
                               "Optimus ledger. Off by default: a page refresh "
                               "must not write forecasts.")):
    """Attribution plus graded hypotheses.

    Degrades explicitly: with no DeepSeek key (or an API that will not answer)
    the attribution still returns, `hypotheses` is empty and `status` says so.
    Nothing is invented to fill the gap.
    """
    picked = None
    if lenses:
        picked = [x.strip() for x in lenses.split(",") if x.strip()]
        unknown = [x for x in picked if x not in wm.LENSES]
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"unknown lens(es) {unknown}; available: {sorted(wm.LENSES)}")
    try:
        return await asyncio.to_thread(
            wm.run_why_moved, _positions(), as_of or str(date.today()),
            lenses=picked, write_ledger=write_ledger)
    except wm.PricingError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:                            # noqa: BLE001
        logger.error("why-moved explain failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/lenses")
async def lenses_available():
    """The specialist lenses and the contract they are all bound by."""
    return {"lenses": {k: v for k, v in wm.LENSES.items()},
            "contract": wm.CONTRACT,
            "note": ("each lens is called SEPARATELY — one prompt asked to do "
                     "all seven does none of them, and a panel that agrees is "
                     "one forecaster")}
