"""
Aegis Finance — Unified Market Dashboard
==========================================

Bloomberg Terminal's main screen equivalent: everything a user needs
to understand the market in a single API call.

This endpoint aggregates:
  1. Market snapshot (S&P 500, VIX, yield curve, regime)
  2. Crash probability with confidence intervals
  3. Sector rotation and business cycle phase
  4. Fixed income (yield curve shape, credit spreads)
  5. Market valuation (CAPE, ERP)
  6. Volatility regime
  7. Economic surprise index
  8. Risk score and systemic risk
  9. Net liquidity (Fed balance sheet)
  10. Sentiment (Google Trends fear/greed)
  11. Market breadth
  12. Crypto/BTC correlation signal

Design: Each section has a try/except so partial failures don't break
the whole dashboard. Sections return None on failure.

Usage:
    from backend.services.market_dashboard import build_market_dashboard
"""

import logging
from typing import Optional

import pandas as pd


logger = logging.getLogger(__name__)


def build_market_dashboard() -> dict:
    """Build the full market dashboard in a single call.

    Returns a dict with all sections. Each section is None if
    that data source failed, so the frontend can degrade gracefully.
    """
    from backend.services.data_fetcher import DataFetcher

    fetcher = DataFetcher()
    data, _ = fetcher.fetch_market_data()
    fred_data = fetcher.fetch_fred_data()

    result = {
        "market": _build_market_section(data),
        "regime": _build_regime_section(data),
        "crash": _build_crash_section(data, fred_data, fetcher),
        "risk": _build_risk_section(data),
        "fixed_income": _build_fixed_income_section(fred_data),
        "valuation": _build_valuation_section(),
        "volatility": _build_vol_section(data),
        "economic": _build_economic_section(),
        "sentiment": _build_sentiment_section(),
        "liquidity": _build_liquidity_section(),
        "crypto": _build_crypto_section(data),
        "breadth": _build_breadth_section(),
    }

    return result


def _build_market_section(data: pd.DataFrame) -> Optional[dict]:
    """Core market snapshot: S&P 500, VIX, yields."""
    try:
        sp500 = float(data["SP500"].iloc[-1])
        sp500_1d = float(data["SP500"].pct_change().iloc[-1]) * 100
        sp500_1m = float(data["SP500"].pct_change(21).iloc[-1]) * 100
        sp500_3m = float(data["SP500"].pct_change(63).iloc[-1]) * 100

        # YTD
        sp500_series = data["SP500"].dropna()
        now = sp500_series.index[-1]
        year_start = pd.Timestamp(year=now.year, month=1, day=1)
        prev_year = sp500_series[sp500_series.index < year_start]
        sp500_ytd = float((sp500_series.iloc[-1] / prev_year.iloc[-1] - 1) * 100) if len(prev_year) > 0 else 0

        vix = float(data["VIX"].iloc[-1]) if "VIX" in data.columns else None

        yield_10y = float(data["T10Y"].iloc[-1]) if "T10Y" in data.columns else None
        yield_3m = float(data["T3M"].iloc[-1]) if "T3M" in data.columns else None
        yield_spread = round(yield_10y - yield_3m, 3) if yield_10y and yield_3m else None

        return {
            "sp500": round(sp500, 2),
            "sp500_1d_pct": round(sp500_1d, 2),
            "sp500_1m_pct": round(sp500_1m, 2),
            "sp500_3m_pct": round(sp500_3m, 2),
            "sp500_ytd_pct": round(sp500_ytd, 2),
            "vix": round(vix, 1) if vix else None,
            "yield_10y": round(yield_10y, 3) if yield_10y else None,
            "yield_3m": round(yield_3m, 3) if yield_3m else None,
            "yield_spread": yield_spread,
            "date": str(data.index[-1].date()),
        }
    except Exception as e:
        logger.warning("Dashboard market section failed: %s", e)
        return None


def _build_regime_section(data: pd.DataFrame) -> Optional[dict]:
    """Market regime detection."""
    try:
        from backend.services.regime_detector import detect_regimes, get_vix_term_structure_state
        from backend.services.risk_scorer import build_risk_score

        data["Risk_Score"] = build_risk_score(data)
        _, regime = detect_regimes(data)
        risk_score = float(data["Risk_Score"].iloc[-1])

        vts = get_vix_term_structure_state(data)

        return {
            "regime": regime,
            "risk_score": round(risk_score, 2),
            "vix_term_structure": vts.get("structure") if vts.get("available") else None,
            "vts_signal": vts.get("signal") if vts.get("available") else None,
        }
    except Exception as e:
        logger.warning("Dashboard regime section failed: %s", e)
        return None


def _build_crash_section(data: pd.DataFrame, fred_data: dict, fetcher) -> Optional[dict]:
    """Crash probabilities with model confidence."""
    try:
        from backend.services.crash_model import CrashPredictor
        from backend.config import MODEL_DIR
        from engine.training.features import build_feature_matrix

        model_path = MODEL_DIR / "crash_model.pkl"
        if not model_path.exists():
            return {"available": False, "reason": "Model not trained"}

        predictor = CrashPredictor()
        predictor.load_model(str(model_path))

        features = build_feature_matrix(data, fred_data=fred_data)
        available = [f for f in predictor.feature_names if f in features.columns]
        latest = features[available].iloc[[-1]]

        probs = {}
        for h in predictor.lgb_models:
            prob = float(predictor.predict_proba(latest, h)[0])
            probs[h] = round(prob * 100, 1)

        # Drift severity
        drift_severity = None
        try:
            from backend.services.drift_detector import DriftDetector
            feat_imp = None
            if hasattr(predictor, "get_top_features"):
                try:
                    top = predictor.get_top_features(n=200)
                    feat_imp = dict(top) if top else None
                except Exception:
                    pass
            drift_report = DriftDetector.from_multi_scale(features, feature_importances=feat_imp)
            drift_severity = drift_report.get("effective_severity", drift_report.get("severity"))
        except Exception:
            pass

        return {
            "available": True,
            "probabilities": probs,
            "drift_severity": drift_severity,
        }
    except Exception as e:
        logger.warning("Dashboard crash section failed: %s", e)
        return None


def _build_risk_section(data: pd.DataFrame) -> Optional[dict]:
    """Systemic risk metrics."""
    try:
        from backend.services.systemic_risk import compute_systemic_risk

        systemic = compute_systemic_risk(data)
        return systemic
    except Exception as e:
        logger.warning("Dashboard risk section failed: %s", e)
        return None


def _build_fixed_income_section(fred_data: dict) -> Optional[dict]:
    """Yield curve and credit spreads."""
    try:
        from backend.services.fixed_income import (
            compute_yield_curve_analysis, compute_credit_spread_analysis,
        )

        yield_curve = compute_yield_curve_analysis(fred_data)
        credit = compute_credit_spread_analysis(fred_data)

        return {
            "curve_shape": yield_curve.get("shape"),
            "curve_interpretation": yield_curve.get("interpretation"),
            "inversions": yield_curve.get("inversions", []),
            "spread_10y_2y": yield_curve.get("spreads", {}).get("10y_2y"),
            "hy_spread": credit.get("spreads", {}).get("hy_oas", {}).get("current"),
            "credit_stress": credit.get("stress", {}).get("level"),
            "breakeven_inflation": credit.get("breakeven_inflation_10y"),
        }
    except Exception as e:
        logger.warning("Dashboard fixed income section failed: %s", e)
        return None


def _build_valuation_section() -> Optional[dict]:
    """Market valuation metrics."""
    try:
        from backend.services.valuation import compute_market_valuation

        val = compute_market_valuation()
        if "error" in val:
            return None

        return {
            "cape": val.get("cape", {}).get("current"),
            "cape_percentile": val.get("cape", {}).get("percentile"),
            "cape_interpretation": val.get("cape", {}).get("interpretation"),
            "forward_pe": val.get("pe", {}).get("forward"),
            "erp_pct": val.get("equity_risk_premium", {}).get("erp_pct"),
            "valuation_score": val.get("composite_valuation_score", {}).get("score"),
            "valuation_level": val.get("composite_valuation_score", {}).get("level"),
        }
    except Exception as e:
        logger.warning("Dashboard valuation section failed: %s", e)
        return None


def _build_vol_section(data: pd.DataFrame) -> Optional[dict]:
    """Volatility regime."""
    try:
        from backend.services.volatility_analytics import get_vol_summary

        vol = get_vol_summary("^GSPC")
        if not vol:
            return None

        return {
            "regime": vol.get("vol_regime"),
            "vol_30d_pct": vol.get("vol_30d_pct"),
            "vol_percentile": vol.get("vol_percentile"),
        }
    except Exception as e:
        logger.warning("Dashboard vol section failed: %s", e)
        return None


def _build_economic_section() -> Optional[dict]:
    """Economic surprise index."""
    try:
        from backend.services.economic_surprise import compute_surprise_index

        eco = compute_surprise_index()
        if not eco:
            return None

        return {
            "composite_score": eco.get("composite_score"),
            "signal": eco.get("signal"),
            "trend": eco.get("trend"),
        }
    except Exception as e:
        logger.warning("Dashboard economic section failed: %s", e)
        return None


def _build_sentiment_section() -> Optional[dict]:
    """Google Trends fear/greed."""
    try:
        from backend.services.trends_sentiment import compute_fear_greed_trends

        trends = compute_fear_greed_trends()
        if not trends:
            return None

        return {
            "sentiment": trends.get("sentiment"),
            "signal": trends.get("signal"),
            "fear_greed_ratio": trends.get("fear_greed_ratio"),
        }
    except Exception as e:
        logger.warning("Dashboard sentiment section failed: %s", e)
        return None


def _build_liquidity_section() -> Optional[dict]:
    """Fed net liquidity."""
    try:
        from backend.services.net_liquidity import get_net_liquidity

        nl = get_net_liquidity()
        if not nl or not nl.get("current"):
            return None

        current = nl["current"]
        return {
            "net_liquidity_t": current.get("net_liquidity"),
            "wow_change_t": current.get("wow_change"),
            "signal": current.get("signal"),
        }
    except Exception as e:
        logger.warning("Dashboard liquidity section failed: %s", e)
        return None


def _build_crypto_section(data: pd.DataFrame) -> Optional[dict]:
    """Bitcoin as a macro signal."""
    try:
        import yfinance as yf

        btc = yf.Ticker("BTC-USD")
        hist = btc.history(period="6mo")
        if hist is None or len(hist) < 30:
            return None

        btc_close = hist["Close"]
        btc_price = float(btc_close.iloc[-1])
        btc_1d = float(btc_close.pct_change().iloc[-1]) * 100
        btc_1m = float((btc_close.iloc[-1] / btc_close.iloc[-21] - 1) * 100) if len(btc_close) > 21 else None
        btc_3m = float((btc_close.iloc[-1] / btc_close.iloc[-63] - 1) * 100) if len(btc_close) > 63 else None

        # BTC/SPX rolling correlation (30-day)
        btc_returns = btc_close.pct_change().dropna()
        sp500_returns = data["SP500"].pct_change().dropna()

        # Align dates
        common = btc_returns.index.intersection(sp500_returns.index)
        corr_30d = None
        if len(common) >= 30:
            b = btc_returns.loc[common].iloc[-30:]
            s = sp500_returns.loc[common].iloc[-30:]
            corr_30d = round(float(b.corr(s)), 3)

        return {
            "btc_price": round(btc_price, 0),
            "btc_1d_pct": round(btc_1d, 2),
            "btc_1m_pct": round(btc_1m, 2) if btc_1m else None,
            "btc_3m_pct": round(btc_3m, 2) if btc_3m else None,
            "btc_sp500_corr_30d": corr_30d,
            "interpretation": (
                "High correlation — BTC moving with risk assets"
                if corr_30d and corr_30d > 0.5
                else "Decorrelated — BTC acting independently"
                if corr_30d and abs(corr_30d) < 0.2
                else "Moderate correlation"
                if corr_30d
                else "Insufficient data"
            ),
        }
    except Exception as e:
        logger.warning("Dashboard crypto section failed: %s", e)
        return None


def _build_breadth_section() -> Optional[dict]:
    """Market breadth from momentum rankings."""
    try:
        from backend.cache import cache_get

        cached_mom = cache_get("momentum_rankings", 3600)
        if not cached_mom or "rankings" not in cached_mom:
            return None

        rankings = cached_mom["rankings"]
        n_total = len(rankings)
        if n_total == 0:
            return None

        n_positive = sum(1 for r in rankings if r.get("composite_score", 0) > 0)
        pct_positive = round(n_positive / n_total * 100, 0)

        # Sector distribution
        sector_counts = {}
        for r in rankings:
            sector = r.get("sector", "Unknown")
            if r.get("composite_score", 0) > 0:
                sector_counts[sector] = sector_counts.get(sector, 0) + 1

        return {
            "stocks_positive_pct": pct_positive,
            "stocks_positive": n_positive,
            "stocks_total": n_total,
            "interpretation": (
                "Broad rally" if pct_positive > 70
                else "Healthy breadth" if pct_positive > 55
                else "Narrow leadership" if pct_positive > 40
                else "Weak breadth" if pct_positive > 25
                else "Broad weakness"
            ),
        }
    except Exception as e:
        logger.warning("Dashboard breadth section failed: %s", e)
        return None
