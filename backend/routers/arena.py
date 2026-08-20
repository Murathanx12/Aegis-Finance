"""Read-only surface for the ARENA Gen-1 product experiment (ORDER 25).

Every payload carries `validation_status: PRODUCT_EXPERIMENT` and
`simulation: true`. Nothing here is a track record, a recommendation, or
evidence of skill — it is the live view of a forward paper SIMULATION.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backend.services.arena import (
    engine, experience, regret, reliability, store,
)
from backend.services.arena import spec as spec_mod

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/arena", tags=["arena"])

_BANNER = {
    "validation_status": "PRODUCT_EXPERIMENT",
    "simulation": True,
    "note": ("Forward paper simulation in its own namespace. Not a track "
             "record, not validated alpha, never evidence of skill."),
}

#: The two populations are graded on horizons that do NOT line up: rules
#: decisions mature at 1/5/21/63/126 sessions, LLM predictions at the
#: belief_state grid (1/2/5/20/60/120/252). "About a month" is 21 in one and 20
#: in the other. Stated here rather than reconciled silently, because joining
#: them would compare two different windows under one label.
_HORIZON_NOTE = {
    "horizon_alignment": {
        "decision_horizons": list(experience.HORIZONS),
        "forecast_horizons_available": [1, 2, 5, 20, 60, 120, 252],
        "warning": ("decision horizon 21 and forecast horizon 20 are NOT the "
                    "same window; do not join these two blocks on 'a month'"),
    },
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


@router.get("/reliability")
def arena_reliability(leg: str = "forecast", min_n: int = reliability.MIN_CELL_N,
                      live: bool = False) -> dict:
    """What the arena has been right about, per cell — or how far off n is.

    `live=false` serves the last appended daily snapshot (what the scheduler
    computed, immutable). `live=true` recomputes from the ledgers now; use it
    to see today's counts before the 17:45 pass has run.
    """
    if leg not in reliability.LEGS:
        raise HTTPException(
            status_code=422,
            detail=f"leg must be one of {sorted(reliability.LEGS)} — the "
                   f"forecast and execution legs answer different questions "
                   f"and there is no combined view on purpose")
    try:
        if live:
            return {**_BANNER, "source": "recomputed_now", "leg": leg,
                    "decisions": reliability.decision_cells(leg=leg,
                                                            min_n=min_n),
                    "forecasts": reliability.forecast_cells(min_n=min_n),
                    **_HORIZON_NOTE}
        snap = reliability.latest()
        if snap is None:
            return {**_BANNER, "source": "daily_snapshot", "snapshot": None,
                    "note": ("no reliability snapshot has been written yet — "
                             "the arena writes one per daily pass"),
                    **_HORIZON_NOTE}
        return {**_BANNER, "source": "daily_snapshot", "snapshot": snap,
                **_HORIZON_NOTE}
    except Exception as e:  # noqa: BLE001
        logger.error("arena reliability failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/regret")
def arena_regret(leg: str = "forecast", min_n: int = 20,
                 worst_k: int = 10) -> dict:
    """What passing cost — paired REJECT vs chosen legs from one information
    state. Unmatched legs are in `unpaired`, not silently absent."""
    if leg not in reliability.LEGS:
        raise HTTPException(status_code=422,
                            detail=f"leg must be one of {sorted(reliability.LEGS)}")
    try:
        return {**_BANNER, **regret.summary(leg=leg, min_n=min_n,
                                            worst_k=max(0, min(worst_k, 50)))}
    except Exception as e:  # noqa: BLE001
        logger.error("arena regret failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
