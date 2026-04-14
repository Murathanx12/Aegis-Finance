"""
Aegis Finance — Systemic Risk Monitor
=======================================

Institutional-grade systemic risk indicators:

1. **Turbulence Index** (Kritzman & Li, 2010)
   Mahalanobis distance of current multi-asset returns from their historical
   distribution. When returns are jointly unusual, the index spikes. Values
   above the 90th percentile historically preceded major drawdowns.

2. **Absorption Ratio** (Kritzman et al., 2011)
   Fraction of total variance explained by top principal components. When
   absorption rises, markets are tightly coupled and diversification benefits
   evaporate — systemic risk is elevated.

Both are computationally cheap (covariance inverse + PCA) and complement the
existing 9-factor risk score by measuring multivariate structure rather than
univariate z-scores.

Usage:
    from backend.services.systemic_risk import compute_systemic_risk
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
from scipy import linalg

from backend.config import config

logger = logging.getLogger(__name__)

# Config defaults
SYSTEMIC_CFG = config.get("systemic_risk", {})
TURBULENCE_WINDOW = SYSTEMIC_CFG.get("turbulence_window", 252)
ABSORPTION_N_COMPONENTS = SYSTEMIC_CFG.get("absorption_n_components", 5)
ABSORPTION_WINDOW = SYSTEMIC_CFG.get("absorption_window", 252)
TURBULENCE_THRESHOLD_PCTL = SYSTEMIC_CFG.get("turbulence_threshold_pctl", 90)


def compute_turbulence_index(
    returns: pd.DataFrame,
    window: int = TURBULENCE_WINDOW,
) -> pd.Series:
    """Compute Kritzman's turbulence index (Mahalanobis distance).

    For each day t, measures how unusual the multi-asset return vector r_t is
    relative to the trailing covariance structure:
        turbulence_t = (r_t - μ)' Σ⁻¹ (r_t - μ)

    Args:
        returns: DataFrame of daily returns, one column per asset.
        window: Lookback for rolling covariance estimation.

    Returns:
        pd.Series of turbulence values (higher = more unusual).
    """
    n_assets = returns.shape[1]
    if n_assets < 2:
        logger.warning("Turbulence requires ≥2 assets, got %d", n_assets)
        return pd.Series(0.0, index=returns.index)

    turbulence = pd.Series(np.nan, index=returns.index, name="turbulence")

    for i in range(window, len(returns)):
        hist = returns.iloc[i - window:i].dropna()
        if len(hist) < window * 0.8:
            continue

        r_t = returns.iloc[i].values
        mu = hist.mean().values
        cov = hist.cov().values

        try:
            # Use pseudo-inverse for numerical stability with near-singular cov
            cov_inv = linalg.pinvh(cov)
            diff = r_t - mu
            mahal = float(diff @ cov_inv @ diff)
            turbulence.iloc[i] = mahal
        except (linalg.LinAlgError, ValueError):
            continue

    return turbulence


def compute_absorption_ratio(
    returns: pd.DataFrame,
    n_components: int = ABSORPTION_N_COMPONENTS,
    window: int = ABSORPTION_WINDOW,
) -> pd.Series:
    """Compute PCA absorption ratio (fraction of variance in top eigenvectors).

    AR = sum(λ₁..λₖ) / sum(λ₁..λₙ)

    High AR means markets are tightly coupled (herding behavior, contagion).
    Rising AR is a leading indicator of systemic stress.

    Args:
        returns: DataFrame of daily returns, one column per asset.
        n_components: Number of top eigenvalues to sum.
        window: Rolling lookback for covariance estimation.

    Returns:
        pd.Series of absorption ratios in [0, 1].
    """
    n_assets = returns.shape[1]
    # Cap at n_assets // 3 so the ratio is meaningful (not ~1.0 by construction)
    n_components = min(n_components, max(1, n_assets // 3))

    ar = pd.Series(np.nan, index=returns.index, name="absorption_ratio")

    for i in range(window, len(returns)):
        hist = returns.iloc[i - window:i].dropna()
        if len(hist) < window * 0.8:
            continue

        try:
            cov = hist.cov().values
            eigenvalues = np.linalg.eigvalsh(cov)
            # eigvalsh returns ascending order; take the largest k
            top_k = eigenvalues[-n_components:]
            total = eigenvalues.sum()
            if total > 0:
                ar.iloc[i] = float(top_k.sum() / total)
        except (np.linalg.LinAlgError, ValueError):
            continue

    return ar


def compute_systemic_risk(data: pd.DataFrame) -> dict:
    """Compute all systemic risk indicators from market data.

    Args:
        data: DataFrame with SP500, VIX, T10Y, T3M, HYG, LQD, Gold, NASDAQ,
              Russell columns (same as risk_scorer input).

    Returns:
        dict with turbulence_current, turbulence_percentile,
        absorption_ratio_current, absorption_ratio_change,
        systemic_stress (bool), and historical series.
    """
    # Build multi-asset return matrix from available columns
    price_cols = [c for c in ["SP500", "NASDAQ", "Russell", "Gold", "HYG", "LQD"] if c in data.columns]
    if len(price_cols) < 3:
        logger.warning("Systemic risk needs ≥3 price series, got %d", len(price_cols))
        return _empty_result()

    returns = data[price_cols].pct_change().dropna()
    if len(returns) < TURBULENCE_WINDOW + 10:
        logger.warning("Insufficient data for systemic risk (%d rows)", len(returns))
        return _empty_result()

    # Compute indicators
    turb = compute_turbulence_index(returns)
    ar = compute_absorption_ratio(returns)

    # Current values
    turb_current = float(turb.iloc[-1]) if pd.notna(turb.iloc[-1]) else None
    ar_current = float(ar.iloc[-1]) if pd.notna(ar.iloc[-1]) else None

    # Turbulence percentile (relative to full history)
    turb_valid = turb.dropna()
    turb_pctl = None
    if turb_current is not None and len(turb_valid) > 20:
        turb_pctl = float((turb_valid < turb_current).mean() * 100)

    # AR change over last month
    ar_valid = ar.dropna()
    ar_change = None
    if ar_current is not None and len(ar_valid) > 22:
        ar_1m_ago = float(ar_valid.iloc[-22]) if pd.notna(ar_valid.iloc[-22]) else None
        if ar_1m_ago is not None:
            ar_change = ar_current - ar_1m_ago

    # Systemic stress flag
    systemic_stress = False
    if turb_pctl is not None and turb_pctl > TURBULENCE_THRESHOLD_PCTL:
        systemic_stress = True
    if ar_current is not None and ar_current > 0.85:
        systemic_stress = True

    result = {
        "turbulence_current": round(turb_current, 4) if turb_current is not None else None,
        "turbulence_percentile": round(turb_pctl, 1) if turb_pctl is not None else None,
        "turbulence_threshold_pctl": TURBULENCE_THRESHOLD_PCTL,
        "absorption_ratio_current": round(ar_current, 4) if ar_current is not None else None,
        "absorption_ratio_change_1m": round(ar_change, 4) if ar_change is not None else None,
        "systemic_stress": systemic_stress,
        "n_assets_used": len(price_cols),
        "assets_used": price_cols,
    }

    logger.info(
        "Systemic risk: turbulence=%.2f (p%.0f), AR=%.3f, stress=%s",
        turb_current or 0, turb_pctl or 0, ar_current or 0, systemic_stress,
    )

    return result


def get_systemic_risk_signal(data: pd.DataFrame) -> Optional[float]:
    """Compute a signal score in [-1, +1] from systemic risk indicators.

    Combines turbulence percentile and absorption ratio into a single
    score suitable for the signal engine. Negative = elevated systemic risk.

    Returns None if data is insufficient.
    """
    result = compute_systemic_risk(data)
    if result.get("turbulence_current") is None:
        return None

    score = 0.0

    # Turbulence: percentile > 80 = warning, > 90 = danger
    turb_pctl = result.get("turbulence_percentile")
    if turb_pctl is not None:
        if turb_pctl > 90:
            score -= 0.5
        elif turb_pctl > 80:
            score -= 0.25
        elif turb_pctl < 30:
            score += 0.15  # calm markets

    # Absorption ratio: high = tightly coupled = fragile
    ar = result.get("absorption_ratio_current")
    if ar is not None:
        if ar > 0.85:
            score -= 0.3
        elif ar > 0.75:
            score -= 0.1
        elif ar < 0.50:
            score += 0.1  # diversified, healthy

    # Rising AR is a leading indicator of stress
    ar_change = result.get("absorption_ratio_change_1m")
    if ar_change is not None:
        if ar_change > 0.03:
            score -= 0.2  # rapid coupling increase
        elif ar_change < -0.03:
            score += 0.1  # decoupling, stress easing

    return float(np.clip(score, -1.0, 1.0))


def _empty_result() -> dict:
    """Return empty systemic risk dict when data is insufficient."""
    return {
        "turbulence_current": None,
        "turbulence_percentile": None,
        "turbulence_threshold_pctl": TURBULENCE_THRESHOLD_PCTL,
        "absorption_ratio_current": None,
        "absorption_ratio_change_1m": None,
        "systemic_stress": False,
        "n_assets_used": 0,
        "assets_used": [],
    }
