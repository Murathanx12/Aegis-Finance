"""
GJR-GARCH Volatility Model
============================

Time-varying conditional volatility with leverage effect.
Negative returns boost volatility more than positive returns.

Usage:
    from backend.models.garch import fit_garch, forecast_volatility
"""

import logging
from typing import NamedTuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class GARCHResult(NamedTuple):
    omega: float
    alpha: float
    gamma: float  # Leverage effect (asymmetry)
    beta: float
    current_vol: float  # Annualized
    nu: float  # Student-t degrees of freedom
    model_fit: object
    success: bool


def fit_garch(returns: pd.Series, min_obs: int = 500) -> GARCHResult:
    """Fit GJR-GARCH(1,1) with skewed Student-t innovations.

    Args:
        returns: Daily return series (decimal, not percentage)
        min_obs: Minimum observations required

    Returns:
        GARCHResult with fitted parameters and current volatility
    """
    try:
        from arch import arch_model
    except ImportError:
        logger.warning("arch library not available, using constant vol")
        return _fallback_result(returns)

    clean = returns.dropna()
    if len(clean) < min_obs:
        logger.warning("Only %d returns, need %d for GARCH", len(clean), min_obs)
        return _fallback_result(returns)

    try:
        scaled = clean * 100  # Percentage for numerical stability

        am = arch_model(
            scaled,
            vol="Garch",
            p=1, o=1, q=1,
            dist="skewt",
            mean="Constant",
        )
        res = am.fit(disp="off", show_warning=False)

        omega = float(res.params.get("omega", 0.01))
        alpha = float(res.params.get("alpha[1]", 0.05))
        gamma = float(res.params.get("gamma[1]", 0.05))
        beta = float(res.params.get("beta[1]", 0.90))
        nu = float(res.params.get("nu", 8.0))

        cond_vol = float(res.conditional_volatility.iloc[-1])
        current_vol_annual = cond_vol / 100 * np.sqrt(252)

        if not (0.05 < current_vol_annual < 1.5):
            logger.warning("GARCH vol %.2f out of range, using fallback", current_vol_annual)
            return _fallback_result(returns)

        logger.info(
            "GARCH: alpha=%.4f, gamma=%.4f, beta=%.4f, vol=%.1f%%, df=%.1f",
            alpha, gamma, beta, current_vol_annual * 100, nu,
        )

        return GARCHResult(
            omega=omega, alpha=alpha, gamma=gamma, beta=beta,
            current_vol=current_vol_annual, nu=nu,
            model_fit=res, success=True,
        )

    except Exception as e:
        logger.warning("GARCH fit failed: %s", e)
        return _fallback_result(returns)


def forecast_volatility(
    garch: GARCHResult,
    horizon: int = 252,
    n_sims: int = 1000,
) -> np.ndarray:
    """Simulate forward volatility paths from fitted GARCH.

    Returns:
        np.ndarray of shape (horizon, n_sims) — daily volatilities (decimal)
    """
    if not garch.success or garch.model_fit is None:
        return np.full((horizon, n_sims), garch.current_vol / np.sqrt(252))

    try:
        res = garch.model_fit
        fcast = res.forecast(
            horizon=min(horizon, 252),
            method="simulation",
            simulations=n_sims,
        )
        var_paths = fcast.simulations.variances.values
        if var_paths.ndim == 3:
            var_paths = var_paths[0]

        vol_paths = np.sqrt(var_paths) / 100

        if horizon > vol_paths.shape[0]:
            extended = np.zeros((horizon, n_sims))
            extended[:vol_paths.shape[0]] = vol_paths
            persistence = garch.alpha + garch.gamma * np.sqrt(2 / np.pi) + garch.beta
            persistence = min(persistence, 0.999)
            lr_var = garch.omega / (1 - persistence)
            lr_vol = np.sqrt(lr_var) / 100
            for t in range(vol_paths.shape[0], horizon):
                extended[t] = extended[t - 1] * persistence + lr_vol * (1 - persistence)
            vol_paths = extended

        return vol_paths

    except Exception:
        return np.full((horizon, n_sims), garch.current_vol / np.sqrt(252))


def _fallback_result(returns: pd.Series) -> GARCHResult:
    vol = float(returns.dropna().std() * np.sqrt(252))
    return GARCHResult(
        omega=0.01, alpha=0.05, gamma=0.05, beta=0.90,
        current_vol=vol, nu=8.0, model_fit=None, success=False,
    )
