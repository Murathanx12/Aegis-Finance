"""Forecast Lab, Theory Lab, System Health and Brain APIs (chunk C19, 2026-10-07; review
fixes; brain v2 added same day). READ ONLY.

GET /api/legibility/v1/forecast-lab              calibration, magnitude vs direction skill (baselines
                                                  named), sigma prior, trust, regime rows, tournament
GET /api/legibility/v1/theory-lab?board=sticky   theories with states, family posteriors, the board's
                                                  four columns (rows for ONE board), the CRSP sentence
GET /api/legibility/v1/system-health             the newest health probe receipt, grouped
GET /api/legibility/v1/brain                     the belief table, scenarios (display probability
                                                  only), regime rows vs baselines, belief_stability,
                                                  and the newest belief_updates ("what changed")

Every payload leaves through the deny-by-default sanitiser (`legibility_sanitise`). 404 when
none of a page's receipts exists; 422 on a bad `board`; 500 names only the exception type.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.routers.arena_v1 import serve
from backend.services import legibility as L

router = APIRouter(prefix="/api/legibility/v1", tags=["legibility-v1"])


@router.get("/forecast-lab")
def get_forecast_lab() -> dict:
    return serve(L.forecast_lab_payload, "forecast_lab", "forecast lab",
                 "no forecast-lab receipt on disk (reputation/, learning_reports/, night_factory_*/grade_forecasts, "
                 "nn_lab/receipts/, digest/, analyst/reputation_weights_*); this endpoint reads receipts and never "
                 "builds one.", published="forecast_lab")


@router.get("/theory-lab")
def get_theory_lab(board: str = Query(default="sticky")) -> dict:
    if board not in L.BOARD_KINDS:
        raise HTTPException(status_code=422, detail=f"board must be one of {sorted(L.BOARD_KINDS)}")
    return serve(L.theory_lab_payload, "theory_lab", "theory lab",
                 "no hyp_lab/ledger.jsonl and no twin_board_SUMMARY_*.json on disk.",
                 published=f"theory_lab_{board}", board=board)


@router.get("/system-health")
def get_system_health() -> dict:
    return serve(L.system_health_payload, "system_health", "system health",
                 "no health/health_<stamp>.json on disk. It is written by `python -m scripts.health_probe` "
                 "and by the daily pass's last step.", published="system_health")


@router.get("/brain")
def get_brain() -> dict:
    return serve(L.brain_payload, "brain", "brain belief state",
                 "no world_state/beliefs.json on disk. It is written by backend.services.world_state "
                 "(AegisWorldDigest, every ~6h); this endpoint reads it and never builds one.",
                 published="brain")
