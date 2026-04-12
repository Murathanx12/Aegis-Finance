"""
Drift Detection Router
========================

GET /api/drift/check — Feature drift report with severity and confidence discount
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from backend.config import config

router = APIRouter(prefix="/api/drift", tags=["drift"])
logger = logging.getLogger(__name__)


@router.get("/check")
async def get_drift_check():
    """Feature drift report: severity, drifted features, confidence discount."""
    try:
        result = await asyncio.to_thread(_drift_check)
        return result
    except Exception as e:
        logger.error("drift check failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _drift_check() -> dict:
    from backend.services.data_fetcher import DataFetcher
    from backend.services.drift_detector import DriftDetector
    from engine.training.features import build_feature_matrix

    fetcher = DataFetcher()
    data, _ = fetcher.fetch_market_data()
    fred_data = fetcher.fetch_fred_data()

    features = build_feature_matrix(data, fred_data=fred_data)

    report = DriftDetector.from_rolling_window(features)

    drift_cfg = config["ml"].get("drift", {})
    confidence_map = drift_cfg.get("confidence_multiplier", {})
    severity = report.get("severity", "none")
    confidence_multiplier = confidence_map.get(severity, 1.0)

    return {
        "drift_detected": report["drift_detected"],
        "severity": severity,
        "drift_pct": report["drift_pct"],
        "n_features_checked": report["n_features_checked"],
        "n_drifted": report["n_drifted"],
        "confidence_multiplier": confidence_multiplier,
        "drifted_features": report["drifted_features"][:10],
        "recommendation": _recommendation(severity),
    }


def _recommendation(severity: str) -> str:
    if severity == "critical":
        return (
            "Critical feature drift: 60%+ features have shifted. "
            "Crash model predictions are unreliable — retrain with recent data "
            "(python -m engine.training.train_crash_model). "
            "Signal engine is auto-discounting crash probability weight."
        )
    if severity == "high":
        return (
            "High feature drift: model predictions may be degraded. "
            "Consider retraining the crash model soon."
        )
    if severity == "moderate":
        return "Moderate feature drift detected. Monitor for further degradation."
    if severity == "low":
        return "Minor feature drift. No action needed."
    return "No feature drift detected. Model is operating on in-distribution data."
