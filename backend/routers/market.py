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

    yield_curve = None
    if "T10Y" in data.columns and "T3M" in data.columns:
        yield_curve = float(data["T10Y"].iloc[-1] - data["T3M"].iloc[-1])

    # Try to get crash probs
    crash_3m = None
    crash_12m = None
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
            for h in predictor.lgb_models:
                prob = float(predictor.predict_proba(latest, h)[0]) * 100
                if h == "3m":
                    crash_3m = prob
                elif h == "12m":
                    crash_12m = prob
    except Exception:
        pass

    # External consensus
    external = None
    try:
        from backend.services.external_validator import validate_external
        fred_data = fetcher.fetch_fred_data()
        ext = validate_external(data, fred_data)
        external = ext.get("consensus_direction")
    except Exception:
        pass

    signal = get_market_signal(
        crash_prob_3m=crash_3m,
        crash_prob_12m=crash_12m,
        regime=regime,
        risk_score=risk_score,
        sp500_1m_return=sp500_1m,
        sp500_3m_return=sp500_3m,
        vix=vix,
        yield_curve=yield_curve,
        external_consensus=external,
    )
    signal["sp500"] = sp500
    signal["regime"] = regime
    signal["risk_score"] = round(risk_score, 2)
    signal["vix"] = round(vix, 1)
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
