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


def get_standardized_residuals(garch: GARCHResult, returns: pd.Series) -> np.ndarray | None:
    """Extract GARCH-standardized residuals from a fitted model.

    Standardized residuals = returns / conditional_volatility are approximately
    iid with unit variance and fat tails matching the fitted distribution.
    These are superior to raw returns for block bootstrap because:
      1. Variance is uniform across time (no vol-clustering contamination)
      2. Fat tails come from genuine tail events, not high-vol periods
      3. Block structure captures higher-order dependence (leverage, skew clustering)

    Args:
        garch: Fitted GARCHResult from fit_garch()
        returns: The same daily return series used to fit the model

    Returns:
        np.ndarray of standardized residuals, or None if extraction fails
    """
    if not garch.success or garch.model_fit is None:
        return None

    try:
        res = garch.model_fit
        # Conditional volatility from the fitted model (in percentage scale)
        cond_vol = res.conditional_volatility
        if cond_vol is None or len(cond_vol) == 0:
            return None

        # Align returns with conditional volatility (GARCH drops initial obs)
        clean_returns = returns.dropna()
        # The model was fit on returns * 100, so cond_vol is in percentage scale
        # Convert back: daily_vol_decimal = cond_vol / 100
        cond_vol_decimal = cond_vol.values / 100.0

        # Align lengths (GARCH may have fewer obs due to mean model)
        n = min(len(clean_returns), len(cond_vol_decimal))
        aligned_returns = clean_returns.iloc[-n:].values
        aligned_vol = cond_vol_decimal[-n:]

        # Avoid division by zero
        valid = aligned_vol > 1e-8
        if valid.sum() < 50:
            return None

        std_resid = np.zeros(n)
        std_resid[valid] = aligned_returns[valid] / aligned_vol[valid]
        std_resid[~valid] = 0.0  # Replace near-zero vol points

        logger.info(
            "GARCH residuals: n=%d, mean=%.3f, std=%.3f, kurtosis=%.1f",
            len(std_resid), std_resid.mean(), std_resid.std(),
            float(pd.Series(std_resid).kurtosis()),
        )
        return std_resid

    except Exception as e:
        logger.warning("Failed to extract GARCH residuals: %s", e)
        return None


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
