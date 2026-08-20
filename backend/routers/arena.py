"""Read-only surface for the ARENA Gen-1 product experiment (ORDER 25).

Every payload carries `validation_status: PRODUCT_EXPERIMENT` and
`simulation: true`. Nothing here is a track record, a recommendation, or
evidence of skill — it is the live view of a forward paper SIMULATION.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backend.services.arena import engine, store
from backend.services.arena import spec as spec_mod

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/arena", tags=["arena"])

_BANNER = {
    "validation_status": "PRODUCT_EXPERIMENT",
    "simulation": True,
    "note": ("Forward paper simulation in its own namespace. Not a track "
             "record, not validated alpha, never evidence of skill."),
}


@router.get("/status")
def arena_status() -> dict:
    try:
        return {**_BANNER, **engine.status()}
    except Exception as e:  # noqa: BLE001
        logger.error("arena status failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/books/{book_id}/nav")
def book_nav(book_id: str) -> dict:
    if book_id not in spec_mod.AUTHORISED_ACTIVE:
        raise HTTPException(status_code=404,
                            detail=f"unknown arena book {book_id!r}")
    return {**_BANNER, "book_id": book_id,
            "seed": store.read_seed(book_id),
            "nav": store.read_nav(book_id)}


@router.get("/books/{book_id}/decisions")
def book_decisions(book_id: str, limit: int = 100) -> dict:
    if book_id not in spec_mod.AUTHORISED_ACTIVE:
        raise HTTPException(status_code=404,
                            detail=f"unknown arena book {book_id!r}")
    rows = store.read_decisions(book_id)
    return {**_BANNER, "book_id": book_id, "n_total": len(rows),
            "decisions": rows[-max(0, min(limit, 500)):]}


@router.get("/experiences/summary")
def experiences_summary() -> dict:
    exps = store.read_experiences()
    outs = store.read_outcomes()
    by_action: dict[str, int] = {}
    for e in exps:
        by_action[e.get("action", "?")] = by_action.get(e.get("action", "?"), 0) + 1
    by_class: dict[str, int] = {}
    for o in outs:
        by_class[o.get("outcome_class", "?")] = (
            by_class.get(o.get("outcome_class", "?"), 0) + 1)
    return {**_BANNER, "experiences": len(exps), "outcomes": len(outs),
            "by_action": by_action, "by_outcome_class": by_class}
