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

    # Try to get crash model feature importances for weighted drift
    feat_imp = None
    try:
        from backend.services.crash_model import CrashPredictor
        from backend.config import MODEL_DIR
        model_path = MODEL_DIR / "crash_model.pkl"
        if model_path.exists():
            predictor = CrashPredictor()
            predictor.load_model(str(model_path))
            top = predictor.get_top_features(n=200)
            feat_imp = dict(top) if top else None
    except Exception as e:
        logger.debug("Could not load crash model for drift weighting: %s", e)

    report = DriftDetector.from_rolling_window(
        features, feature_importances=feat_imp,
    )

    drift_cfg = config["ml"].get("drift", {})
    confidence_map = drift_cfg.get("confidence_multiplier", {})
    effective_severity = report.get("effective_severity",
                                    report.get("severity", "none"))
    raw_severity = report.get("severity", "none")
    confidence_multiplier = confidence_map.get(effective_severity, 1.0)

    result = {
        "drift_detected": report["drift_detected"],
        "severity": effective_severity,
        "raw_severity": raw_severity,
        "drift_pct": report["drift_pct"],
        "n_features_checked": report["n_features_checked"],
        "n_drifted": report["n_drifted"],
        "confidence_multiplier": confidence_multiplier,
        "drifted_features": report["drifted_features"][:10],
        "recommendation": _recommendation(effective_severity),
        "reference_window": report.get("reference_window"),
        "inference_window": report.get("inference_window"),
    }

    # Add importance-weighted metrics when available
    if "importance_weighted_drift_pct" in report:
        result["importance_weighted_drift_pct"] = report["importance_weighted_drift_pct"]
        result["importance_weighted_severity"] = report.get("importance_weighted_severity")
        result["stable_important_features"] = report.get("stable_important_features", [])

    # Add per-group drift decomposition when available
    if "group_drift" in report:
        result["group_drift"] = report["group_drift"]
    if "drift_narrative" in report:
        result["drift_narrative"] = report["drift_narrative"]

    return result


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
