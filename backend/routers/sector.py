"""
Sector Analysis Router
========================

GET /api/sectors — 11-sector factor model rankings
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from backend.cache import cache_get, cache_set
from backend.config import config

router = APIRouter(prefix="/api", tags=["sectors"])
logger = logging.getLogger(__name__)

_CACHE_TTL = config["cache"]


@router.get("/sectors")
async def get_sectors():
    """11-sector factor model with expected returns, momentum, risk."""
    cached = cache_get("sector_analysis", _CACHE_TTL["ttl_sectors"])
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_analyze_sectors)
        cache_set("sector_analysis", result)
        return result
    except Exception as e:
        logger.error("sector analysis failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _analyze_sectors() -> dict:
    import numpy as np
    from backend.config import get_forecast_days
    from backend.services.data_fetcher import DataFetcher
    from backend.services.sector_analyzer import analyze_sectors
    from backend.services.regime_detector import fit_hmm_for_mc

    fetcher = DataFetcher()
    data, sector_data = fetcher.fetch_market_data()

    # Compute GARCH vol from SP500 for sector MC enrichment
    garch_vol = None
    try:
        from backend.models.garch import fit_garch
        sp_returns = data["SP500"].pct_change().dropna()
        garch_result = fit_garch(sp_returns)
        if garch_result.success:
            garch_vol = garch_result.current_vol
    except (ImportError, ValueError, KeyError) as e:
        logger.debug("GARCH fit unavailable for sectors: %s", e)

    # Get crash probability from the crash model
    ml_crash_prob = None
    try:
        from backend.services.crash_model import CrashPredictor
        from backend.config import MODEL_DIR
        model_path = MODEL_DIR / "crash_model.pkl"
        if model_path.exists():
            from engine.training.features import build_feature_matrix
            predictor = CrashPredictor()
            predictor.load_model(str(model_path))
            fred_data = fetcher.fetch_fred_data()
            features = build_feature_matrix(data, fred_data=fred_data)
            available = [f for f in predictor.feature_names if f in features.columns]
            latest = features[available].iloc[[-1]]
            ml_crash_prob = float(predictor.predict_proba(latest, "3m")[0])
    except (ImportError, FileNotFoundError, ValueError, KeyError) as e:
        logger.debug("Crash model unavailable for sectors: %s", e)

    # Fit HMM for regime-conditioned sector MC simulations
    hmm_data = fit_hmm_for_mc(data)

    results = analyze_sectors(
        data=data,
        sector_data=sector_data,
        forecast_days=get_forecast_days(),
        ml_crash_prob=ml_crash_prob,
        garch_vol=garch_vol,
        hmm_state_means=hmm_data["state_means"],
        hmm_regime_probs=hmm_data["regime_probs"],
        hmm_state_vols=hmm_data["state_vols"],
    )

    # Sort by expected return
    ranked = sorted(results.items(), key=lambda x: x[1]["sim_total_return"], reverse=True)

    return {
        "sectors": [
            {"name": name, "rank": i + 1, **metrics}
            for i, (name, metrics) in enumerate(ranked)
        ],
        "count": len(ranked),
    }
