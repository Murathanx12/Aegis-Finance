"""
Aegis Finance — Volatility Analytics
======================================

Bloomberg-style volatility analysis for individual stocks:
  - Volatility Cone: percentile bands at multiple lookback windows
  - Realized Vol Term Structure: current vol at 10d/30d/60d/90d/180d/252d
  - Vol Regime: high/normal/low classification based on historical percentile
  - Vol Risk Premium: implied vol vs realized vol spread (when options data available)
  - Vol Clustering: ARCH effect detection (autocorrelation of squared returns)
  - Vol-of-Vol: stability of vol itself (second-order metric)
  - Parkinson & Garman-Klass estimators: more efficient OHLC-based vol
  - GARCH Forward Curve: model-based vol forecast out 1/5/10/30/60/90 days

This is the kind of analysis Bloomberg PORT shows on every equity page.
Retail platforms rarely surface this — it's a clear competitive edge.

Data source: yfinance (OHLCV history)

Usage:
    from backend.services.volatility_analytics import get_volatility_analytics
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from backend.config import config

logger = logging.getLogger(__name__)

_VOL_CFG = config.get("volatility_analytics", {})

# Lookback windows for the vol cone (trading days)
_CONE_WINDOWS = _VOL_CFG.get("cone_windows", [10, 30, 60, 90, 180, 252])

# Rolling window for vol-of-vol computation
_VOVOL_WINDOW = _VOL_CFG.get("vovol_window", 60)

# History years for percentile computation
_HISTORY_YEARS = _VOL_CFG.get("history_years", 5)

# Annualization factor
_ANNUALIZE = _VOL_CFG.get("annualization_factor", 252)

# Vol regime percentile thresholds
_REGIME_LOW = _VOL_CFG.get("regime_low_pctl", 25)
_REGIME_HIGH = _VOL_CFG.get("regime_high_pctl", 75)

# ARCH effect lag for Ljung-Box test
_ARCH_LAGS = _VOL_CFG.get("arch_test_lags", 10)


def _annualized_vol(returns: pd.Series) -> float:
    """Annualized standard deviation of returns."""
    return float(np.std(returns, ddof=1) * np.sqrt(_ANNUALIZE)) if len(returns) > 1 else 0.0


def _parkinson_vol(high: pd.Series, low: pd.Series) -> float:
    """Parkinson (1980) range-based volatility estimator.

    More efficient than close-to-close vol as it uses intraday range.
    Var = (1/4ln2) * E[ln(H/L)^2]
    """
    if len(high) < 2 or len(low) < 2:
        return 0.0
    log_hl = np.log(high / low)
    var = (1.0 / (4.0 * np.log(2))) * np.mean(log_hl ** 2)
    return float(np.sqrt(var * _ANNUALIZE))


def _garman_klass_vol(
    open_: pd.Series, high: pd.Series, low: pd.Series, close: pd.Series
) -> float:
    """Garman-Klass (1980) OHLC volatility estimator.

    Uses all four price points for maximum efficiency.
    """
    if len(open_) < 2:
        return 0.0
    log_hl = np.log(high / low)
    log_co = np.log(close / open_)
    var = 0.5 * np.mean(log_hl ** 2) - (2 * np.log(2) - 1) * np.mean(log_co ** 2)
    # Guard against negative variance from numerical issues
    if var <= 0:
        return _annualized_vol(close.pct_change().dropna())
    return float(np.sqrt(var * _ANNUALIZE))


def _compute_vol_cone(returns: pd.Series) -> dict:
    """Compute volatility cone — percentile bands at each lookback window.

    For each window W, we compute rolling W-day annualized vol over the full
    history, then extract percentiles (5th, 25th, 50th, 75th, 95th) and
    the CURRENT W-day vol. This shows where current vol sits vs its
    historical distribution at each horizon.
    """
    cone = {}
    for window in _CONE_WINDOWS:
        if len(returns) < window + 20:
            continue
        rolling_vol = returns.rolling(window).std() * np.sqrt(_ANNUALIZE)
        rolling_vol = rolling_vol.dropna()
        if len(rolling_vol) < 10:
            continue

        current = float(rolling_vol.iloc[-1])
        p5 = float(np.percentile(rolling_vol, 5))
        p25 = float(np.percentile(rolling_vol, 25))
        p50 = float(np.percentile(rolling_vol, 50))
        p75 = float(np.percentile(rolling_vol, 75))
        p95 = float(np.percentile(rolling_vol, 95))
        pctl = float(
            (rolling_vol < current).sum() / len(rolling_vol) * 100
        )

        cone[f"{window}d"] = {
            "window_days": window,
            "current": round(current * 100, 2),
            "p5": round(p5 * 100, 2),
            "p25": round(p25 * 100, 2),
            "median": round(p50 * 100, 2),
            "p75": round(p75 * 100, 2),
            "p95": round(p95 * 100, 2),
            "percentile": round(pctl, 1),
        }
    return cone


def _compute_term_structure(returns: pd.Series) -> list[dict]:
    """Current realized vol at each lookback horizon — the vol term structure."""
    term = []
    for window in _CONE_WINDOWS:
        if len(returns) < window:
            continue
        vol = float(np.std(returns.iloc[-window:], ddof=1) * np.sqrt(_ANNUALIZE))
        term.append({
            "horizon_days": window,
            "realized_vol_pct": round(vol * 100, 2),
        })
    return term


def _detect_vol_regime(returns: pd.Series) -> dict:
    """Classify current vol regime as high/normal/low based on 30d realized vol
    percentile vs 5-year history."""
    window = 30
    if len(returns) < window + 20:
        return {"regime": "unknown", "percentile": None}

    rolling_vol = returns.rolling(window).std() * np.sqrt(_ANNUALIZE)
    rolling_vol = rolling_vol.dropna()
    if len(rolling_vol) < 10:
        return {"regime": "unknown", "percentile": None}

    current = float(rolling_vol.iloc[-1])
    pctl = float((rolling_vol < current).sum() / len(rolling_vol) * 100)

    if pctl >= _REGIME_HIGH:
        regime = "high"
    elif pctl <= _REGIME_LOW:
        regime = "low"
    else:
        regime = "normal"

    return {
        "regime": regime,
        "percentile": round(pctl, 1),
        "current_30d_vol_pct": round(current * 100, 2),
        "interpretation": _regime_interpretation(regime, pctl),
    }


def _regime_interpretation(regime: str, pctl: float) -> str:
    if regime == "high":
        return f"Vol at {pctl:.0f}th percentile — elevated risk, consider hedging or reducing position size"
    elif regime == "low":
        return f"Vol at {pctl:.0f}th percentile — subdued environment, options may be cheap"
    else:
        return f"Vol at {pctl:.0f}th percentile — normal range"


def _compute_vol_risk_premium(ticker: str, realized_30d: float) -> Optional[dict]:
    """Compare implied vol (from options) to realized vol.

    A positive spread (IV > RV) means options are expensive — vol sellers' market.
    A negative spread (IV < RV) means options are cheap — vol buyers' market.
    """
    try:
        from backend.services.options_intelligence import get_iv_signal
        iv_data = get_iv_signal(ticker)
        if not iv_data.get("available"):
            return None

        iv_rank = iv_data.get("iv_rank")
        # IV rank is 0-100, approximate ATM IV from iv_rank and historical context
        # We use the raw IV data if available
        iv_atm = iv_data.get("atm_iv")

        if iv_atm is not None and realized_30d > 0:
            spread = iv_atm - realized_30d
            ratio = iv_atm / realized_30d
            return {
                "implied_vol_pct": round(iv_atm * 100, 2) if iv_atm < 5 else round(iv_atm, 2),
                "realized_vol_pct": round(realized_30d * 100, 2),
                "spread_pct": round(spread * 100, 2) if iv_atm < 5 else round((iv_atm / 100 - realized_30d) * 100, 2),
                "iv_rv_ratio": round(ratio, 3) if iv_atm < 5 else round(iv_atm / 100 / realized_30d, 3),
                "iv_rank": iv_rank,
                "interpretation": _vrp_interpretation(ratio if iv_atm < 5 else iv_atm / 100 / realized_30d),
            }
        elif iv_rank is not None:
            return {
                "iv_rank": iv_rank,
                "realized_vol_pct": round(realized_30d * 100, 2),
                "interpretation": f"IV rank at {iv_rank:.0f}th percentile vs 1-year range",
            }
    except Exception as e:
        logger.debug("Vol risk premium unavailable for %s: %s", ticker, e)
    return None


def _vrp_interpretation(iv_rv_ratio: float) -> str:
    if iv_rv_ratio > 1.3:
        return "Options expensive — implied vol significantly exceeds realized. Vol sellers may find opportunity"
    elif iv_rv_ratio > 1.1:
        return "Slight premium — IV modestly above realized. Normal hedging demand"
    elif iv_rv_ratio > 0.9:
        return "Fair — implied and realized vol roughly aligned"
    else:
        return "Options cheap — implied vol below realized. Good time to buy protection"


def _compute_vol_clustering(returns: pd.Series) -> dict:
    """Detect ARCH effects — autocorrelation of squared returns.

    High vol clustering means vol shocks persist, making recent vol
    a better predictor of near-term vol.
    """
    if len(returns) < 50:
        return {"arch_effect": False, "interpretation": "Insufficient data"}

    squared = (returns ** 2).dropna()
    if len(squared) < 50:
        return {"arch_effect": False, "interpretation": "Insufficient data"}

    # Ljung-Box test on squared returns
    try:
        from statsmodels.stats.diagnostic import acorr_ljungbox
        lb_result = acorr_ljungbox(squared, lags=[_ARCH_LAGS], return_df=True)
        lb_pvalue = float(lb_result["lb_pvalue"].iloc[0])
        arch_detected = lb_pvalue < 0.05

        # Autocorrelation of squared returns at lag 1
        acf1 = float(squared.autocorr(lag=1)) if len(squared) > 1 else 0.0

        return {
            "arch_effect": arch_detected,
            "ljung_box_pvalue": round(lb_pvalue, 4),
            "squared_return_acf1": round(acf1, 4),
            "interpretation": (
                "Strong vol clustering detected — vol shocks tend to persist. GARCH forecasts are informative"
                if arch_detected
                else "Weak vol clustering — vol shocks dissipate quickly. Historical vol is a reasonable forecast"
            ),
        }
    except ImportError:
        # Fallback: simple autocorrelation check without statsmodels
        acf1 = float(squared.autocorr(lag=1)) if len(squared) > 1 else 0.0
        arch_detected = abs(acf1) > 0.1
        return {
            "arch_effect": arch_detected,
            "squared_return_acf1": round(acf1, 4),
            "interpretation": (
                "Vol clustering detected (ACF1 of squared returns > 0.1)"
                if arch_detected
                else "Weak vol clustering"
            ),
        }


def _compute_vol_of_vol(returns: pd.Series) -> Optional[dict]:
    """Vol-of-vol — how stable is volatility itself?

    High vol-of-vol means the stock's risk profile is unstable,
    making position sizing harder.
    """
    window = _VOVOL_WINDOW
    if len(returns) < window * 3:
        return None

    rolling_vol = returns.rolling(window).std() * np.sqrt(_ANNUALIZE)
    rolling_vol = rolling_vol.dropna()
    if len(rolling_vol) < 60:
        return None

    vovol = float(np.std(rolling_vol, ddof=1))
    mean_vol = float(np.mean(rolling_vol))
    cv = vovol / mean_vol if mean_vol > 0 else 0.0

    # Vol trend — is vol rising or falling?
    recent = float(rolling_vol.iloc[-20:].mean())
    older = float(rolling_vol.iloc[-60:-20].mean()) if len(rolling_vol) >= 60 else mean_vol
    vol_trend = "rising" if recent > older * 1.05 else ("falling" if recent < older * 0.95 else "stable")

    return {
        "vol_of_vol_pct": round(vovol * 100, 2),
        "mean_vol_pct": round(mean_vol * 100, 2),
        "coefficient_of_variation": round(cv, 3),
        "vol_trend": vol_trend,
        "interpretation": _vovol_interpretation(cv, vol_trend),
    }


def _vovol_interpretation(cv: float, trend: str) -> str:
    stability = "very unstable" if cv > 0.5 else ("unstable" if cv > 0.3 else "stable")
    return f"Volatility is {stability} (CV={cv:.2f}), currently {trend}"


def _garch_forward_curve(returns: pd.Series) -> Optional[dict]:
    """GARCH(1,1) based forward vol forecast out 1/5/10/30/60/90 days.

    Uses the `arch` package if available, falls back to EWMA otherwise.
    """
    if len(returns) < 100:
        return None

    # Scale returns to percentage for arch library numerical stability
    ret_pct = returns * 100

    try:
        from arch import arch_model
        am = arch_model(ret_pct.dropna(), vol="Garch", p=1, q=1, dist="t", rescale=False)
        res = am.fit(disp="off", show_warning=False)

        # Extract parameters
        omega = float(res.params.get("omega", 0))
        alpha = float(res.params.get("alpha[1]", 0))
        beta = float(res.params.get("beta[1]", 0))
        persistence = alpha + beta

        # Unconditional (long-run) variance
        if persistence < 1.0 and omega > 0:
            uncond_var = omega / (1 - persistence)
        else:
            uncond_var = float(np.var(ret_pct.dropna()))

        # Current conditional variance (last fitted value)
        current_var = float(res.conditional_volatility.iloc[-1] ** 2)

        # Forward curve: E[σ²_t+h] = σ²_∞ + (σ²_t - σ²_∞) * persistence^h
        horizons = [1, 5, 10, 30, 60, 90]
        curve = []
        for h in horizons:
            fwd_var = uncond_var + (current_var - uncond_var) * (persistence ** h)
            # Convert daily pct variance back to annualized vol
            fwd_vol_annual = float(np.sqrt(fwd_var / 10000 * _ANNUALIZE))
            curve.append({
                "horizon_days": h,
                "forecast_vol_pct": round(fwd_vol_annual * 100, 2),
            })

        return {
            "model": "GARCH(1,1) Student-t",
            "persistence": round(persistence, 4),
            "long_run_vol_pct": round(np.sqrt(uncond_var / 10000 * _ANNUALIZE) * 100, 2),
            "current_vol_pct": round(np.sqrt(current_var / 10000 * _ANNUALIZE) * 100, 2),
            "curve": curve,
            "interpretation": _garch_interpretation(persistence, curve),
        }
    except ImportError:
        logger.debug("arch package not available, using EWMA fallback")
    except Exception as e:
        logger.debug("GARCH fit failed: %s, using EWMA fallback", e)

    # EWMA fallback
    try:
        span = 30
        ewma_var = ret_pct.ewm(span=span).var().dropna()
        if len(ewma_var) < 2:
            return None
        current_var = float(ewma_var.iloc[-1])
        long_run_var = float(ewma_var.mean())

        # Simple mean-reversion assumption
        decay = 0.97  # approximate EWMA decay
        horizons = [1, 5, 10, 30, 60, 90]
        curve = []
        for h in horizons:
            fwd_var = long_run_var + (current_var - long_run_var) * (decay ** h)
            fwd_vol = float(np.sqrt(fwd_var / 10000 * _ANNUALIZE))
            curve.append({
                "horizon_days": h,
                "forecast_vol_pct": round(fwd_vol * 100, 2),
            })
        return {
            "model": "EWMA (fallback)",
            "long_run_vol_pct": round(np.sqrt(long_run_var / 10000 * _ANNUALIZE) * 100, 2),
            "current_vol_pct": round(np.sqrt(current_var / 10000 * _ANNUALIZE) * 100, 2),
            "curve": curve,
        }
    except Exception as e:
        logger.debug("EWMA fallback also failed: %s", e)
        return None


def _garch_interpretation(persistence: float, curve: list) -> str:
    if persistence > 0.99:
        persist_str = "near unit-root — vol shocks are extremely persistent"
    elif persistence > 0.95:
        persist_str = "high persistence — vol shocks decay slowly"
    elif persistence > 0.85:
        persist_str = "moderate persistence — normal mean-reversion"
    else:
        persist_str = "low persistence — vol shocks dissipate quickly"

    # Compare short-term vs long-term forecast
    if len(curve) >= 2:
        short = curve[0]["forecast_vol_pct"]
        long = curve[-1]["forecast_vol_pct"]
        if short > long * 1.1:
            term_str = "Term structure inverted (short-term vol elevated)"
        elif long > short * 1.1:
            term_str = "Term structure in contango (vol expected to rise)"
        else:
            term_str = "Flat term structure"
    else:
        term_str = ""

    return f"{persist_str}. {term_str}".strip()


def get_volatility_analytics(ticker: str) -> dict:
    """Comprehensive volatility analysis for a single stock.

    Returns:
        Dict with vol_cone, term_structure, regime, risk_premium,
        clustering, vol_of_vol, estimators, garch_forecast
    """
    try:
        import yfinance as yf
    except ImportError:
        return {"error": "yfinance not installed", "ticker": ticker}

    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=f"{_HISTORY_YEARS}y")
        if hist is None or len(hist) < 60:
            return {"error": f"Insufficient price history for {ticker}", "ticker": ticker}

        result = {"ticker": ticker}

        # Log returns
        close = hist["Close"]
        returns = np.log(close / close.shift(1)).dropna()

        # 1. Volatility Cone — percentile bands at each lookback window
        result["vol_cone"] = _compute_vol_cone(returns)

        # 2. Realized Vol Term Structure — current vol at each horizon
        result["term_structure"] = _compute_term_structure(returns)

        # 3. Vol Regime — high/normal/low
        result["regime"] = _detect_vol_regime(returns)

        # 4. Advanced vol estimators (Parkinson, Garman-Klass)
        recent_252 = hist.tail(252)
        if len(recent_252) >= 30:
            result["estimators"] = {
                "close_to_close_pct": round(
                    _annualized_vol(np.log(recent_252["Close"] / recent_252["Close"].shift(1)).dropna()) * 100, 2
                ),
                "parkinson_pct": round(
                    _parkinson_vol(recent_252["High"], recent_252["Low"]) * 100, 2
                ),
                "garman_klass_pct": round(
                    _garman_klass_vol(
                        recent_252["Open"], recent_252["High"],
                        recent_252["Low"], recent_252["Close"]
                    ) * 100, 2
                ),
                "interpretation": "Parkinson/GK use intraday range — more efficient than close-to-close",
            }

        # 5. Vol Risk Premium (implied vs realized)
        rv_30d = _annualized_vol(returns.iloc[-30:]) if len(returns) >= 30 else None
        if rv_30d is not None:
            vrp = _compute_vol_risk_premium(ticker, rv_30d)
            if vrp:
                result["risk_premium"] = vrp

        # 6. Vol Clustering (ARCH effects)
        result["clustering"] = _compute_vol_clustering(returns)

        # 7. Vol-of-Vol
        vovol = _compute_vol_of_vol(returns)
        if vovol:
            result["vol_of_vol"] = vovol

        # 8. GARCH Forward Curve
        garch = _garch_forward_curve(returns)
        if garch:
            result["garch_forecast"] = garch

        # Summary
        regime_str = result.get("regime", {}).get("regime", "unknown")
        current_30d = result.get("regime", {}).get("current_30d_vol_pct")
        pctl = result.get("regime", {}).get("percentile")
        result["summary"] = {
            "regime": regime_str,
            "current_30d_vol_pct": current_30d,
            "percentile_vs_history": pctl,
            "arch_effect": result.get("clustering", {}).get("arch_effect", False),
            "vol_trend": result.get("vol_of_vol", {}).get("vol_trend"),
        }

        return result

    except Exception as e:
        logger.error("Volatility analytics failed for %s: %s", ticker, e)
        return {"error": str(e), "ticker": ticker}


def get_vol_summary(ticker: str) -> Optional[dict]:
    """Lightweight vol summary for embedding in stock analysis.

    Returns key vol metrics without the full cone/curve detail.
    """
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        hist = stock.history(period="2y")
        if hist is None or len(hist) < 60:
            return None

        close = hist["Close"]
        returns = np.log(close / close.shift(1)).dropna()

        # Current realized vols
        vol_10d = _annualized_vol(returns.iloc[-10:]) if len(returns) >= 10 else None
        vol_30d = _annualized_vol(returns.iloc[-30:]) if len(returns) >= 30 else None
        vol_90d = _annualized_vol(returns.iloc[-90:]) if len(returns) >= 90 else None

        # Percentile of 30d vol vs 2-year history
        pctl = None
        if len(returns) >= 90:
            rolling = returns.rolling(30).std() * np.sqrt(_ANNUALIZE)
            rolling = rolling.dropna()
            if len(rolling) > 10:
                current = float(rolling.iloc[-1])
                pctl = float((rolling < current).sum() / len(rolling) * 100)

        # Regime
        regime = "unknown"
        if pctl is not None:
            if pctl >= _REGIME_HIGH:
                regime = "high"
            elif pctl <= _REGIME_LOW:
                regime = "low"
            else:
                regime = "normal"

        # GK estimator for comparison
        recent = hist.tail(90)
        gk = None
        if len(recent) >= 30:
            gk = _garman_klass_vol(recent["Open"], recent["High"], recent["Low"], recent["Close"])

        return {
            "vol_10d_pct": round(vol_10d * 100, 2) if vol_10d else None,
            "vol_30d_pct": round(vol_30d * 100, 2) if vol_30d else None,
            "vol_90d_pct": round(vol_90d * 100, 2) if vol_90d else None,
            "garman_klass_90d_pct": round(gk * 100, 2) if gk else None,
            "vol_percentile": round(pctl, 1) if pctl is not None else None,
            "vol_regime": regime,
        }
    except Exception as e:
        logger.debug("Vol summary failed for %s: %s", ticker, e)
        return None
