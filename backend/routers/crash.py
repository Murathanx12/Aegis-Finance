"""
Crash Prediction Router
=========================

GET /api/crash/prediction  — Multi-horizon crash probabilities + SHAP
GET /api/crash/{ticker}    — Per-ticker crash assessment
"""

import asyncio
import logging
import re

from fastapi import APIRouter, HTTPException, Query

from backend.cache import cache_get, cache_set
from backend.config import config

router = APIRouter(prefix="/api/crash", tags=["crash"])
logger = logging.getLogger(__name__)

_CACHE_TTL = config["cache"]

_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")


@router.get("/prediction")
async def get_crash_prediction(
    horizon: str = Query("3m", pattern="^(3m|6m|12m)$", description="Prediction horizon: 3m, 6m, 12m"),
    explain: bool = Query(False, description="Include SHAP explanation"),
):
    """Multi-horizon crash probability with optional SHAP explanation."""
    cache_key = f"crash_prediction:{horizon}:{explain}"
    cached = cache_get(cache_key, _CACHE_TTL["ttl_crash"])
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_predict_crash, horizon, explain)
        cache_set(cache_key, result)
        return result
    except Exception as e:
        logger.error("crash prediction failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _predict_crash(horizon: str, explain: bool) -> dict:
    from backend.config import MODEL_DIR
    from backend.services.data_fetcher import DataFetcher
    from backend.services.crash_model import CrashPredictor
    from backend.services.drift_detector import DriftDetector
    from engine.training.features import build_feature_matrix
    from engine.training.feature_selection import SELECTED_FEATURES

    model_path = MODEL_DIR / "crash_model.pkl"
    if not model_path.exists():
        return {
            "status": "model_not_trained",
            "message": "Run 'python -m engine.training.train_crash_model' first",
        }

    predictor = CrashPredictor()
    predictor.load_model(str(model_path))

    fetcher = DataFetcher()
    data, _ = fetcher.fetch_market_data()
    fred_data = fetcher.fetch_fred_data()

    features = build_feature_matrix(data, fred_data=fred_data)
    available = [f for f in predictor.feature_names if f in features.columns]
    latest = features[available].iloc[[-1]]

    # All horizons
    probabilities = {}
    for h in predictor.lgb_models:
        prob = float(predictor.predict_proba(latest, h)[0])
        probabilities[h] = round(prob * 100, 1)

    # Drift-aware confidence (importance-weighted when model importances available)
    drift_cfg = config["ml"].get("drift", {})
    confidence_map = drift_cfg.get("confidence_multiplier", {})
    try:
        feat_imp = dict(predictor.get_top_features(n=200)) if predictor.get_top_features() else None
        drift_report = DriftDetector.from_multi_scale(
            features, feature_importances=feat_imp,
        )
        drift_severity = drift_report.get("effective_severity",
                                          drift_report.get("severity", "none"))
        confidence_multiplier = confidence_map.get(drift_severity, 1.0)
    except Exception as e:
        logger.warning("Drift check failed in crash prediction: %s", e)
        drift_severity = "none"
        confidence_multiplier = 1.0

    # Conformal prediction intervals — calibrated uncertainty bands
    try:
        from backend.services.conformal_predictor import conformal_crash_interval
        prediction_intervals = {}
        for h, prob_pct in probabilities.items():
            interval = conformal_crash_interval(prob_pct / 100.0, horizon=h, alpha=0.10)
            prediction_intervals[h] = {
                "lower_pct": round(interval["lower"] * 100, 1),
                "upper_pct": round(interval["upper"] * 100, 1),
                "width_pct": round(interval["width"] * 100, 1),
                "coverage": interval["coverage_target"],
                "method": interval["method"],
            }
    except Exception as e:
        logger.debug("Conformal intervals unavailable: %s", e)
        prediction_intervals = None

    result = {
        "probabilities": probabilities,
        "prediction_intervals": prediction_intervals,
        "primary_horizon": horizon,
        "primary_prob": probabilities.get(horizon, None),
        "last_updated": str(data.index[-1].date()),
        "drift": {
            "severity": drift_severity,
            "confidence_multiplier": confidence_multiplier,
        },
    }

    # SHAP explanation
    if explain:
        from backend.services.shap_explainer import explain_prediction
        explanation = explain_prediction(predictor, latest, horizon)
        result["explanation"] = explanation

    # External validation (consensus agreement)
    try:
        from backend.services.external_validator import validate_external
        from backend.services.regime_detector import detect_regimes
        from backend.services.regime_validator import validate_regime

        _, current_regime = detect_regimes(data)

        # 12m crash prob for external validation
        crash_12m = probabilities.get("12m", probabilities.get("6m", 0)) / 100.0

        ext = validate_external(fred_data, crash_12m, current_regime)
        result["external_validation"] = {
            "consensus_direction": ext.consensus_direction,
            "engine_agreement": round(ext.engine_agreement * 100, 1),
            "signals": {
                "lei": ext.lei_signal,
                "sloos": ext.sloos_signal,
                "fed": ext.fed_signal,
                "sentiment": ext.sentiment_signal,
            },
            "divergence_alerts": ext.divergence_alerts,
        }

        # Regime confirmation
        regime_val = validate_regime(data, current_regime)
        result["regime_validation"] = {
            "regime": str(regime_val.regime),
            "confirmed": bool(regime_val.confirmed),
            "confidence": str(regime_val.confidence),
            "checks": {
                "price_structure": bool(regime_val.price_confirmed),
                "breadth": bool(regime_val.breadth_confirmed),
                "consensus": bool(regime_val.consensus_aligned),
            },
            "notes": list(regime_val.notes),
        }
    except Exception as e:
        logger.warning("External/regime validation failed: %s", e)

    return result


@router.get("/diagnostics")
async def get_crash_diagnostics():
    """Crash model health diagnostics: calibrator status, floor-pinning, drift."""
    try:
        result = await asyncio.to_thread(_crash_diagnostics)
        return result
    except (FileNotFoundError, OSError) as e:
        logger.error("crash diagnostics I/O error: %s", e)
        raise HTTPException(status_code=500, detail=f"Model file error: {e}")
    except (ValueError, KeyError, TypeError, RuntimeError, ImportError) as e:
        logger.error("crash diagnostics computation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _crash_diagnostics() -> dict:
    from backend.config import MODEL_DIR
    from backend.services.crash_model import CrashPredictor
    from backend.services.data_fetcher import DataFetcher
    from backend.services.drift_detector import DriftDetector
    from engine.training.features import build_feature_matrix

    model_path = MODEL_DIR / "crash_model.pkl"
    if not model_path.exists():
        return {"status": "model_not_trained"}

    predictor = CrashPredictor()
    predictor.load_model(str(model_path))

    fetcher = DataFetcher()
    data, _ = fetcher.fetch_market_data()
    fred_data = fetcher.fetch_fred_data()

    features = build_feature_matrix(data, fred_data=fred_data)
    available = [f for f in predictor.feature_names if f in features.columns]
    latest = features[available].iloc[[-1]]

    diag = predictor.diagnostics(latest)
    any_degenerate = any(h["degenerate"] for h in diag.values())

    # Feature drift check (importance-weighted)
    drift_cfg = config["ml"].get("drift", {})
    confidence_map = drift_cfg.get("confidence_multiplier", {})
    try:
        feat_imp = dict(predictor.get_top_features(n=200)) if predictor.get_top_features() else None
        drift_report = DriftDetector.from_multi_scale(
            features, feature_importances=feat_imp,
        )
        drift_severity = drift_report.get("effective_severity",
                                          drift_report.get("severity", "none"))
        drift_pct = drift_report.get("importance_weighted_drift_pct",
                                     drift_report.get("drift_pct", 0))
        confidence_multiplier = confidence_map.get(drift_severity, 1.0)
    except Exception as e:
        logger.warning("Drift check failed in diagnostics: %s", e)
        drift_severity = "unknown"
        drift_pct = 0
        confidence_multiplier = 1.0

    # Overall status considers both calibrator health and drift
    if any_degenerate or drift_severity == "critical":
        status = "degraded"
    elif drift_severity == "high":
        status = "warning"
    else:
        status = "healthy"

    recommendation_parts = []
    if any_degenerate:
        recommendation_parts.append(
            "Model predictions are degenerate — retrain with recent data "
            "(python -m engine.training.train_crash_model)"
        )
    if drift_severity in ("critical", "high"):
        recommendation_parts.append(
            f"Feature drift is {drift_severity} ({drift_pct:.0f}% drifted) — "
            f"predictions discounted to {confidence_multiplier:.0%} confidence"
        )
    if not recommendation_parts:
        recommendation_parts.append("Model operating normally")

    return {
        "status": status,
        "horizons": diag,
        "drift": {
            "severity": drift_severity,
            "drift_pct": drift_pct,
            "confidence_multiplier": confidence_multiplier,
        },
        "recommendation": "; ".join(recommendation_parts),
    }


@router.get("/{ticker}")
async def get_ticker_crash(ticker: str = "SPY"):
    """Per-ticker crash risk assessment using beta-adjusted market crash probability."""
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail="Invalid ticker format")
    cache_key = f"crash_ticker:{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL["ttl_crash"])
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_ticker_crash, ticker)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Ticker {ticker} not found")
        cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("ticker crash failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _ticker_crash(ticker: str) -> dict:
    import yfinance as yf
    from backend.config import MODEL_DIR
    from backend.services.crash_model import CrashPredictor

    # Get ticker beta
    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}
        beta = info.get("beta", 1.0) or 1.0
        company_name = info.get("shortName", ticker)
        current_price = info.get("regularMarketPrice") or info.get("previousClose", 0)
    except Exception:
        return None

    # Get market crash probabilities
    model_path = MODEL_DIR / "crash_model.pkl"
    market_probs = {}

    if model_path.exists():
        try:
            from backend.services.data_fetcher import DataFetcher
            from engine.training.features import build_feature_matrix

            predictor = CrashPredictor()
            predictor.load_model(str(model_path))

            fetcher = DataFetcher()
            data, _ = fetcher.fetch_market_data()
            fred_data = fetcher.fetch_fred_data()

            features = build_feature_matrix(data, fred_data=fred_data)
            available = [f for f in predictor.feature_names if f in features.columns]
            latest = features[available].iloc[[-1]]

            for h in predictor.lgb_models:
                market_probs[h] = float(predictor.predict_proba(latest, h)[0])
        except Exception as e:
            logger.warning("Could not get market crash probs: %s", e)

    # Beta-adjusted crash probabilities
    ticker_probs = {}
    for h, market_p in market_probs.items():
        adjusted = min(market_p * beta, 0.95)
        ticker_probs[h] = round(adjusted * 100, 1)

    return {
        "ticker": ticker,
        "name": company_name,
        "current_price": current_price,
        "beta": beta,
        "market_crash_probs": {h: round(p * 100, 1) for h, p in market_probs.items()},
        "ticker_crash_probs": ticker_probs,
        "risk_level": "high" if any(p > 30 for p in ticker_probs.values()) else
                      "elevated" if any(p > 20 for p in ticker_probs.values()) else "normal",
    }
