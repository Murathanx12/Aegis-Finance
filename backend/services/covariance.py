"""
Aegis Finance — Denoised Covariance Matrix Estimation
=======================================================

Institutional-grade covariance estimation methods:

1. Marchenko-Pastur Denoising (Lopez de Prado, 2020):
   Uses Random Matrix Theory to separate signal from noise in the eigenvalue
   spectrum of the correlation matrix. Noise eigenvalues are shrunk to their
   average, preserving only statistically significant structure.

2. Detoning (optional): Removes the market mode (1st eigenvector) to isolate
   idiosyncratic risk structure. Useful for relative-value analysis.

3. Ledoit-Wolf Shrinkage: Optimal linear shrinkage toward a structured target.
   Already in PyPortfolioOpt — this module provides the RMT alternative.

Why this matters:
  - Raw sample covariance from ~252 days and ~50 stocks is dominated by noise
  - Eigenvalues below the Marchenko-Pastur bound carry no information
  - Denoised matrices produce more stable portfolio weights in optimization
  - MSCI Barra and Axioma use similar eigenvalue cleaning approaches

References:
  - Marchenko & Pastur (1967), "Distribution of eigenvalues for some sets of random matrices"
  - Lopez de Prado (2020), "Machine Learning for Asset Managers" (Ch. 2)
  - Bun, Bouchaud & Potters (2017), "Cleaning large correlation matrices" (Physics Reports)
  - Ledoit & Wolf (2004), "A well-conditioned estimator for large-dimensional covariance matrices"

Usage:
    from backend.services.covariance import (
        denoise_covariance, estimate_covariance, marchenko_pastur_bound
    )
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from backend.config import config

logger = logging.getLogger(__name__)


_COV_CFG = config.get("covariance_config", {})


def marchenko_pastur_pdf(var: float, q: float, pts: int = 1000) -> tuple:
    """Marchenko-Pastur probability density function.

    Args:
        var: Variance of the random elements (sigma^2)
        q: Ratio T/N (observations / variables)
        pts: Number of evaluation points

    Returns:
        (eigenvalues, pdf_values) tuple
    """
    lambda_min = var * (1 - 1 / np.sqrt(q)) ** 2
    lambda_max = var * (1 + 1 / np.sqrt(q)) ** 2

    evals = np.linspace(lambda_min, lambda_max, pts)
    evals = np.clip(evals, lambda_min + 1e-10, lambda_max - 1e-10)

    pdf = q / (2 * np.pi * var) * np.sqrt(
        (lambda_max - evals) * (evals - lambda_min)
    ) / evals

    return evals, pdf


def marchenko_pastur_bound(T: int, N: int, var: float = 1.0) -> float:
    """Upper bound of the Marchenko-Pastur distribution.

    Eigenvalues above this bound are signal; below are noise.

    Args:
        T: Number of observations (time periods)
        N: Number of variables (assets)
        var: Noise variance (estimated from bulk of eigenvalues)

    Returns:
        lambda_max — the critical eigenvalue threshold
    """
    q = T / N
    return var * (1 + 1 / np.sqrt(q)) ** 2


def _fit_mp_variance(eigenvalues: np.ndarray, q: float) -> float:
    """Estimate the noise variance by fitting MP distribution to the bulk.

    Uses the KS statistic to find the variance parameter that best fits
    the empirical eigenvalue distribution below the upper bound.
    """
    from scipy.stats import kstest

    def _neg_fit(var):
        """Negative quality of fit (to minimize)."""
        lambda_max = var * (1 + 1 / np.sqrt(q)) ** 2
        noise_evals = eigenvalues[eigenvalues <= lambda_max]
        if len(noise_evals) < 5:
            return 1e10

        # Compare empirical CDF with MP CDF
        evals_mp, pdf_mp = marchenko_pastur_pdf(var, q)
        cdf_mp = np.cumsum(pdf_mp)
        cdf_mp = cdf_mp / cdf_mp[-1]  # Normalize

        # Interpolate for KS test
        from scipy.interpolate import interp1d
        try:
            cdf_fn = interp1d(evals_mp, cdf_mp, bounds_error=False, fill_value=(0, 1))
            empirical_cdf = np.arange(1, len(noise_evals) + 1) / len(noise_evals)
            theoretical_cdf = cdf_fn(np.sort(noise_evals))
            ks = np.max(np.abs(empirical_cdf - theoretical_cdf))
            return ks
        except Exception:
            return 1e10

    result = minimize_scalar(_neg_fit, bounds=(0.01, 5.0), method="bounded")
    return result.x if result.success else 1.0


def denoise_covariance(
    returns: pd.DataFrame,
    detone: bool = True,
    method: str = "constant_residual",
) -> pd.DataFrame:
    """Denoise a covariance matrix using Random Matrix Theory.

    Steps:
    1. Compute correlation matrix from returns
    2. Eigendecompose
    3. Identify signal vs noise eigenvalues using Marchenko-Pastur bound
    4. Shrink noise eigenvalues to their average (constant residual method)
       or set them to zero (targeted shrinkage)
    5. Optionally remove the market mode (detoning)
    6. Reconstruct the denoised correlation matrix
    7. Convert back to covariance

    Args:
        returns: DataFrame of asset returns (T x N)
        detone: If True, remove the market factor (1st eigenvector)
        method: "constant_residual" or "targeted_shrinkage"

    Returns:
        Denoised covariance matrix as DataFrame
    """
    T, N = returns.shape
    if T < N:
        logger.warning("T=%d < N=%d — sample covariance is rank-deficient. "
                        "Using Ledoit-Wolf instead.", T, N)
        return _ledoit_wolf_cov(returns)

    # Compute correlation matrix
    cov = returns.cov()
    std = np.sqrt(np.diag(cov.values))
    std[std == 0] = 1e-10  # Avoid division by zero
    corr = cov.values / np.outer(std, std)

    # Ensure symmetric and positive semi-definite
    corr = (corr + corr.T) / 2
    np.fill_diagonal(corr, 1.0)

    # Eigendecompose
    eigenvalues, eigenvectors = np.linalg.eigh(corr)

    # Sort descending
    idx = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]

    # Find MP bound
    q = T / N
    var_noise = _fit_mp_variance(eigenvalues, q)
    lambda_max = marchenko_pastur_bound(T, N, var_noise)

    # Separate signal and noise
    n_signal = np.sum(eigenvalues > lambda_max)
    if n_signal == 0:
        n_signal = 1  # Keep at least the first eigenvalue
    n_noise = N - n_signal

    logger.info("Marchenko-Pastur: %d signal, %d noise eigenvalues (bound=%.4f)",
                n_signal, n_noise, lambda_max)

    # Denoise: replace noise eigenvalues
    denoised_evals = eigenvalues.copy()
    if method == "constant_residual" and n_noise > 0:
        # Set noise eigenvalues to their average — preserves trace
        noise_avg = denoised_evals[n_signal:].mean()
        denoised_evals[n_signal:] = noise_avg
    elif method == "targeted_shrinkage":
        # Shrink noise eigenvalues toward 0
        denoised_evals[n_signal:] *= 0.1

    # Detone: remove market mode (optional)
    if detone and n_signal >= 2:
        # Zero out the largest eigenvalue (market factor)
        denoised_evals[0] = 0

    # Reconstruct
    denoised_corr = eigenvectors @ np.diag(denoised_evals) @ eigenvectors.T

    # Rescale diagonal to 1.0
    d = np.sqrt(np.diag(denoised_corr))
    d[d == 0] = 1e-10
    denoised_corr = denoised_corr / np.outer(d, d)
    np.fill_diagonal(denoised_corr, 1.0)

    # Convert back to covariance
    denoised_cov = denoised_corr * np.outer(std, std)

    return pd.DataFrame(denoised_cov, index=returns.columns, columns=returns.columns)


def _ledoit_wolf_cov(returns: pd.DataFrame) -> pd.DataFrame:
    """Ledoit-Wolf shrinkage covariance estimator (fallback)."""
    try:
        from sklearn.covariance import LedoitWolf
        lw = LedoitWolf()
        lw.fit(returns.values)
        return pd.DataFrame(lw.covariance_, index=returns.columns, columns=returns.columns)
    except Exception:
        return returns.cov()


def estimate_covariance(
    returns: pd.DataFrame,
    method: Optional[str] = None,
    detone: Optional[bool] = None,
) -> pd.DataFrame:
    """Estimate covariance matrix using configured method.

    Args:
        returns: Asset returns DataFrame
        method: Override config method ("denoised", "ledoit_wolf", "empirical")
        detone: Override config detone setting

    Returns:
        Estimated covariance matrix
    """
    if method is None:
        method = _COV_CFG.get("method", "denoised")
    if detone is None:
        detone = _COV_CFG.get("detone", True)

    if method == "denoised":
        return denoise_covariance(returns, detone=detone)
    elif method == "ledoit_wolf":
        return _ledoit_wolf_cov(returns)
    else:
        return returns.cov()


def covariance_diagnostics(
    returns: pd.DataFrame,
) -> dict:
    """Compare empirical, Ledoit-Wolf, and denoised covariance matrices.

    Returns diagnostic metrics showing how much noise was removed.
    """
    T, N = returns.shape
    q = T / N

    cov_raw = returns.cov()
    cov_lw = _ledoit_wolf_cov(returns)
    cov_dn = denoise_covariance(returns, detone=False)

    # Eigenvalue analysis — use CORRELATION matrix eigenvalues for MP analysis.
    # Marchenko-Pastur theory applies to correlation matrices (trace = N),
    # not covariance matrices whose eigenvalue scale depends on asset volatilities.
    std_raw = np.sqrt(np.diag(cov_raw.values))
    std_raw[std_raw == 0] = 1e-10
    corr_raw = cov_raw.values / np.outer(std_raw, std_raw)
    corr_raw = (corr_raw + corr_raw.T) / 2
    np.fill_diagonal(corr_raw, 1.0)

    evals_raw = np.sort(np.linalg.eigvalsh(corr_raw))[::-1]

    # Denoised eigenvalues from the denoised correlation matrix
    std_dn = np.sqrt(np.diag(cov_dn.values))
    std_dn[std_dn == 0] = 1e-10
    corr_dn = cov_dn.values / np.outer(std_dn, std_dn)
    corr_dn = (corr_dn + corr_dn.T) / 2
    np.fill_diagonal(corr_dn, 1.0)

    evals_dn = np.sort(np.linalg.eigvalsh(corr_dn))[::-1]

    # Fit noise variance from correlation eigenvalues (consistent with denoise_covariance)
    var_noise = _fit_mp_variance(evals_raw, q)
    lambda_max = marchenko_pastur_bound(T, N, var_noise)

    # Condition number: ratio of largest to smallest eigenvalue
    # Lower = more stable for optimization
    cond_raw = evals_raw[0] / max(evals_raw[-1], 1e-10)
    evals_dn_pos = evals_dn[evals_dn > 0]
    cond_dn = evals_dn_pos[0] / max(evals_dn_pos[-1], 1e-10) if len(evals_dn_pos) > 0 else cond_raw

    n_signal = int(np.sum(evals_raw > lambda_max))

    return {
        "dimensions": {"T": T, "N": N, "q": round(q, 2)},
        "marchenko_pastur_bound": round(lambda_max, 4),
        "signal_eigenvalues": n_signal,
        "noise_eigenvalues": N - n_signal,
        "condition_number": {
            "raw": round(float(cond_raw), 1),
            "denoised": round(float(cond_dn), 1),
            "improvement": round(float(cond_raw / max(cond_dn, 1)), 1),
        },
        "top_5_eigenvalues": {
            "raw": [round(float(e), 4) for e in evals_raw[:5]],
            "denoised": [round(float(e), 4) for e in evals_dn[:5]],
        },
    }
