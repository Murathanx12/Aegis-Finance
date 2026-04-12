"""
Market Status & Macro Indicators Router
==========================================

GET /api/market-status  — Unified market state (regime, risk score, VIX, etc.)
GET /api/macro          — FRED macro indicators
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from backend.cache import cache_get, cache_set
from backend.config import config

router = APIRouter(prefix="/api", tags=["market"])
logger = logging.getLogger(__name__)

_CACHE_TTL = config["cache"]


@router.get("/market-status")
async def get_market_status():
    """Unified market state: regime, risk score, VIX, yield curve, crash prob."""
    cached = cache_get("market_status", _CACHE_TTL["ttl_market"])
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_compute_market_status)
        cache_set("market_status", result)
        return result
    except Exception as e:
        logger.error("market-status failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _compute_market_status() -> dict:
    from backend.services.data_fetcher import DataFetcher
    from backend.services.risk_scorer import build_risk_score
    from backend.services.regime_detector import detect_regimes

    fetcher = DataFetcher()
    data, _ = fetcher.fetch_market_data()

    # Risk score
    data["Risk_Score"] = build_risk_score(data)
    risk_score = float(data["Risk_Score"].iloc[-1])

    # Regime detection
    _, current_regime = detect_regimes(data)

    # Key indicators
    sp500 = float(data["SP500"].iloc[-1])
    sp500_change_1m = float(data["SP500"].pct_change(21).iloc[-1]) * 100
    current_year = data.index[-1].year
    ytd_data = data["SP500"].loc[data.index.year >= current_year]
    sp500_change_ytd = float(
        (ytd_data.iloc[-1] / ytd_data.iloc[0] - 1) * 100
    ) if len(ytd_data) > 1 else 0.0

    vix = float(data["VIX"].iloc[-1]) if "VIX" in data.columns else None

    yield_curve = None
    if "T10Y" in data.columns and "T3M" in data.columns:
        yield_curve = float(data["T10Y"].iloc[-1] - data["T3M"].iloc[-1])

    # Try crash model if available
    crash_probs = {}
    try:
        from backend.services.crash_model import CrashPredictor
        from backend.config import MODEL_DIR

        model_path = MODEL_DIR / "crash_model.pkl"
        if model_path.exists():
            from engine.training.features import build_feature_matrix
            from engine.training.feature_selection import SELECTED_FEATURES

            predictor = CrashPredictor()
            predictor.load_model(str(model_path))

            fred_data = fetcher.fetch_fred_data()
            features = build_feature_matrix(data, fred_data=fred_data)
            available = [f for f in predictor.feature_names if f in features.columns]
            latest = features[available].iloc[[-1]]

            for horizon in predictor.lgb_models:
                prob = float(predictor.predict_proba(latest, horizon)[0])
                crash_probs[horizon] = round(prob * 100, 1)
    except Exception as e:
        logger.warning("Crash model unavailable: %s", e)

    # Data quality check
    data_quality = None
    try:
        from backend.services.data_quality import DataQualityChecker
        checker = DataQualityChecker()
        data_quality = checker.summary(data)
    except Exception as e:
        logger.warning("Data quality check failed: %s", e)

    # Net liquidity
    net_liq = None
    try:
        from backend.services.net_liquidity import get_net_liquidity
        nl = get_net_liquidity()
        if nl and nl.get("current", {}).get("net_liquidity") is not None:
            net_liq = nl["current"]
    except Exception as e:
        logger.warning("Net liquidity fetch failed: %s", e)

    # Systemic risk (turbulence index + absorption ratio)
    systemic = None
    try:
        from backend.services.systemic_risk import compute_systemic_risk
        systemic = compute_systemic_risk(data)
    except Exception as e:
        logger.warning("Systemic risk computation failed: %s", e)

    # LPPL bubble detection
    bubble = None
    try:
        from backend.services.bubble_detector import get_bubble_status
        bubble = get_bubble_status(data["SP500"], ticker="SP500")
    except Exception as e:
        logger.warning("Bubble detection failed: %s", e)

    return {
        "sp500": sp500,
        "sp500_change_1m": round(sp500_change_1m, 2),
        "sp500_change_ytd": round(sp500_change_ytd, 2),
        "vix": vix,
        "yield_curve": yield_curve,
        "risk_score": round(risk_score, 2),
        "regime": current_regime,
        "crash_probabilities": crash_probs,
        "data_quality": data_quality,
        "net_liquidity": net_liq,
        "systemic_risk": systemic,
        "bubble_indicator": bubble,
        "last_updated": str(data.index[-1].date()),
    }


@router.get("/signal")
async def get_market_signal_endpoint():
    """Composite market buy/sell signal."""
    cached = cache_get("market_signal", _CACHE_TTL["ttl_market"])
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_compute_market_signal)
        cache_set("market_signal", result)
        return result
    except Exception as e:
        logger.error("market signal failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _compute_market_signal() -> dict:
    from backend.services.data_fetcher import DataFetcher
    from backend.services.risk_scorer import build_risk_score
    from backend.services.regime_detector import detect_regimes
    from backend.services.signal_engine import get_market_signal

    fetcher = DataFetcher()
    data, _ = fetcher.fetch_market_data()
    data["Risk_Score"] = build_risk_score(data)

    _, regime = detect_regimes(data)
    risk_score = float(data["Risk_Score"].iloc[-1])
    sp500 = float(data["SP500"].iloc[-1])
    vix = float(data["VIX"].iloc[-1]) if "VIX" in data.columns else 20.0
    sp500_1m = float(data["SP500"].pct_change(21).iloc[-1]) * 100
    sp500_3m = float(data["SP500"].pct_change(63).iloc[-1]) * 100

    # YTD return
    sp500_ytd = 0.0
    try:
        import pandas as pd
        sp500_series = data["SP500"].dropna()
        now = sp500_series.index[-1]
        year_start = pd.Timestamp(year=now.year, month=1, day=1)
        prev_year_prices = sp500_series[sp500_series.index < year_start]
        if len(prev_year_prices) > 0:
            sp500_ytd = float((sp500_series.iloc[-1] / prev_year_prices.iloc[-1] - 1) * 100)
    except Exception:
        pass

    yield_curve = None
    if "T10Y" in data.columns and "T3M" in data.columns:
        yield_curve = float(data["T10Y"].iloc[-1] - data["T3M"].iloc[-1])

    # Drawdown from 52-week high
    sp500_drawdown = None
    if "SP500" in data.columns:
        from backend.services.signal_engine import compute_drawdown_pct
        sp500_drawdown = compute_drawdown_pct(data["SP500"])

    # Try to get crash probs + drift severity (share feature matrix)
    crash_3m = None
    crash_12m = None
    _drift_severity = None
    _feature_matrix = None
    try:
        from backend.services.crash_model import CrashPredictor
        from backend.config import MODEL_DIR
        model_path = MODEL_DIR / "crash_model.pkl"
        if model_path.exists():
            from engine.training.features import build_feature_matrix
            predictor = CrashPredictor()
            predictor.load_model(str(model_path))
            fred_data = fetcher.fetch_fred_data()
            _feature_matrix = build_feature_matrix(data, fred_data=fred_data)
            available = [f for f in predictor.feature_names if _feature_matrix is not None and f in _feature_matrix.columns]
            latest = _feature_matrix[available].iloc[[-1]]
            for h in predictor.lgb_models:
                prob = float(predictor.predict_proba(latest, h)[0]) * 100
                if h == "3m":
                    crash_3m = prob
                elif h == "12m":
                    crash_12m = prob
    except (ImportError, FileNotFoundError, ValueError, KeyError) as e:
        logger.debug("Crash model unavailable in signal: %s", e)

    # Drift severity (reuses feature matrix from crash model block)
    # Pass crash model feature importances so drift detector can compute
    # importance-weighted severity — prevents low-importance features from
    # inflating drift and unnecessarily disabling the crash model.
    if _feature_matrix is not None:
        try:
            from backend.services.drift_detector import DriftDetector
            _feat_imp = None
            if "predictor" in dir() and hasattr(predictor, "get_top_features"):
                try:
                    top = predictor.get_top_features(n=200)
                    _feat_imp = dict(top) if top else None
                except Exception:
                    pass
            _drift_report = DriftDetector.from_multi_scale(
                _feature_matrix, feature_importances=_feat_imp,
            )
            _drift_severity = _drift_report.get("effective_severity",
                                                 _drift_report.get("severity"))
        except Exception as e:
            logger.debug("Drift detection unavailable in signal: %s", e)

    # External consensus
    external = None
    try:
        from backend.services.external_validator import validate_external
        fred_data_ext = fetcher.fetch_fred_data()
        ext = validate_external(fred_data_ext, crash_12m / 100 if crash_12m else None, regime)
        external = ext.consensus_direction
    except (ImportError, KeyError, TypeError, ValueError) as e:
        logger.debug("External validation unavailable: %s", e)

    signal = get_market_signal(
        crash_prob_3m=crash_3m,
        crash_prob_12m=crash_12m,
        regime=regime,
        risk_score=risk_score,
        sp500_1m_return=sp500_1m,
        sp500_3m_return=sp500_3m,
        sp500_ytd_return=sp500_ytd,
        vix=vix,
        yield_curve=yield_curve,
        external_consensus=external,
        drawdown_pct=sp500_drawdown,
        drift_severity=_drift_severity,
    )
    signal["sp500"] = sp500
    signal["regime"] = regime
    signal["risk_score"] = round(risk_score, 2)
    signal["vix"] = round(vix, 1)
    signal["drawdown_pct"] = round(sp500_drawdown, 2) if sp500_drawdown is not None else None
    signal["last_updated"] = str(data.index[-1].date())
    return signal


@router.get("/macro")
async def get_macro_indicators():
    """FRED macro indicators with latest values."""
    cached = cache_get("macro_indicators", _CACHE_TTL["ttl_macro"])
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_compute_macro)
        cache_set("macro_indicators", result)
        return result
    except Exception as e:
        logger.error("macro failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _compute_macro() -> dict:
    from backend.services.data_fetcher import DataFetcher

    fetcher = DataFetcher()
    fred_data = fetcher.fetch_fred_data()

    indicators = {}
    display_names = {
        "T10Y2Y": "10Y-2Y Spread",
        "T10Y3M": "10Y-3M Spread",
        "VIXCLS": "VIX (CBOE)",
        "BAMLH0A0HYM2": "High Yield Spread",
        "ICSA": "Initial Claims",
        "NFCI": "Financial Conditions",
        "UNRATE": "Unemployment Rate",
        "CPIAUCSL": "CPI (All Urban)",
        "FEDFUNDS": "Fed Funds Rate",
        "M2SL": "M2 Money Supply",
        "INDPRO": "Industrial Production",
        "UMCSENT": "Consumer Sentiment",
    }

    for key, series in fred_data.items():
        if series is not None and len(series) > 0:
            latest = float(series.dropna().iloc[-1])
            change_1m = None
            if len(series) > 21:
                prev = float(series.dropna().iloc[-22]) if len(series.dropna()) > 22 else None
                if prev is not None and prev != 0:
                    change_1m = round((latest - prev) / abs(prev) * 100, 2)

            indicators[key] = {
                "name": display_names.get(key, key),
                "value": round(latest, 4),
                "change_1m_pct": change_1m,
                "last_date": str(series.dropna().index[-1].date()),
            }

    return {"indicators": indicators, "count": len(indicators)}


@router.get("/net-liquidity")
async def get_net_liquidity_endpoint():
    """Fed Net Liquidity: WALCL - (TGA + RRP). Weekly data, 24hr cache."""
    cached = cache_get("net_liquidity_endpoint", _CACHE_TTL["ttl_macro"])
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_compute_net_liquidity)
        cache_set("net_liquidity_endpoint", result)
        return result
    except Exception as e:
        logger.error("net-liquidity failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _compute_net_liquidity() -> dict:
    from backend.services.net_liquidity import get_net_liquidity
    return get_net_liquidity()


@router.get("/data-quality")
async def get_data_quality():
    """Run data quality checks on current market data."""
    cached = cache_get("data_quality", _CACHE_TTL["ttl_market"])
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_compute_data_quality)
        cache_set("data_quality", result)
        return result
    except Exception as e:
        logger.error("data-quality failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _compute_data_quality() -> dict:
    from backend.services.data_fetcher import DataFetcher
    from backend.services.data_quality import DataQualityChecker

    fetcher = DataFetcher()
    data, _ = fetcher.fetch_market_data()
    checker = DataQualityChecker()
    return checker.summary(data)
