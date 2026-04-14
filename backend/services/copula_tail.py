"""
Aegis Finance — Copula-Based Tail Dependence & Joint Risk
============================================================

Parametric copula models for proper tail dependence estimation.
This replaces the empirical-only approach in tail_dependence.py with
statistically rigorous parametric models that:

1. Provide consistent tail dependence estimates (empirical is noisy)
2. Enable simulation of joint tail scenarios
3. Support AIC-based model selection across copula families
4. Compute copula-based portfolio VaR and CVaR

Copula families:
  - Clayton: Asymmetric lower tail dependence (co-crashes)
  - Gumbel: Asymmetric upper tail dependence (co-rallies)
  - Frank: Symmetric, no tail dependence (benchmark)
  - Student-t: Symmetric tail dependence controlled by df

References:
  - Nelsen (2006), "An Introduction to Copulas"
  - Joe (2014), "Dependence Modeling with Copulas"
  - Embrechts, McNeil & Straumann (2002)
  - Patton (2006), "Modelling asymmetric exchange rate dependence" (JEL)

Usage:
    from backend.services.copula_tail import (
        fit_best_copula, compute_copula_tail_dependence,
        copula_var_cvar, analyze_pair_copula
    )
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import minimize_scalar, minimize

from backend.config import config

logger = logging.getLogger(__name__)


# ── Copula Config ────────────────────────────────────────────────────────────

_COP_CFG = config.get("copula_config", {})
_LOOKBACK = _COP_CFG.get("lookback_days", 756)
_MIN_OBS = _COP_CFG.get("min_observations", 252)
_CONF_LEVEL = _COP_CFG.get("confidence_level", 0.05)
_N_SIMS = _COP_CFG.get("n_simulations", 10000)


# ══════════════════════════════════════════════════════════════════════════════
# COPULA IMPLEMENTATIONS
# ══════════════════════════════════════════════════════════════════════════════


def _to_pseudo_observations(data: np.ndarray) -> np.ndarray:
    """Convert data to pseudo-observations (uniform marginals via ranks).

    Uses the standard formula: U_i = R_i / (n+1) to avoid boundary issues.
    """
    n = len(data)
    if data.ndim == 1:
        ranks = stats.rankdata(data)
        return ranks / (n + 1)
    else:
        result = np.zeros_like(data, dtype=float)
        for j in range(data.shape[1]):
            result[:, j] = stats.rankdata(data[:, j]) / (n + 1)
        return result


# ── Clayton Copula ──────────────────────────────────────────────────────────


def _clayton_loglik(theta: float, u: np.ndarray, v: np.ndarray) -> float:
    """Negative log-likelihood for Clayton copula. theta > 0."""
    if theta <= 0:
        return 1e10
    n = len(u)
    u = np.clip(u, 1e-10, 1 - 1e-10)
    v = np.clip(v, 1e-10, 1 - 1e-10)

    term = u ** (-theta) + v ** (-theta) - 1
    term = np.clip(term, 1e-10, None)

    loglik = (
        n * np.log(1 + theta)
        - (1 + theta) * np.sum(np.log(u) + np.log(v))
        - (2 + 1.0 / theta) * np.sum(np.log(term))
    )
    return -loglik


def _fit_clayton(u: np.ndarray, v: np.ndarray) -> dict:
    """Fit Clayton copula via MLE."""
    result = minimize_scalar(
        lambda t: _clayton_loglik(t, u, v),
        bounds=(0.01, 50.0), method="bounded"
    )
    theta = result.x
    loglik = -result.fun
    k = 1  # number of parameters
    n = len(u)
    aic = 2 * k - 2 * loglik
    # Lower tail dependence: lambda_L = 2^(-1/theta)
    tail_lower = 2 ** (-1.0 / theta) if theta > 0 else 0.0

    return {
        "family": "clayton",
        "theta": round(float(theta), 4),
        "loglik": round(float(loglik), 2),
        "aic": round(float(aic), 2),
        "tail_lower": round(float(tail_lower), 4),
        "tail_upper": 0.0,  # Clayton has no upper tail dependence
        "n_params": k,
    }


# ── Gumbel Copula ──────────────────────────────────────────────────────────


def _gumbel_loglik(theta: float, u: np.ndarray, v: np.ndarray) -> float:
    """Negative log-likelihood for Gumbel copula. theta >= 1."""
    if theta < 1:
        return 1e10
    u = np.clip(u, 1e-10, 1 - 1e-10)
    v = np.clip(v, 1e-10, 1 - 1e-10)

    lu = -np.log(u)
    lv = -np.log(v)
    A = (lu ** theta + lv ** theta)
    A = np.clip(A, 1e-10, None)
    A_inv = A ** (1.0 / theta)

    C = np.exp(-A_inv)
    C = np.clip(C, 1e-300, None)

    # Log-density (bivariate)
    log_c = (
        np.log(C)
        + (theta - 1) * (np.log(lu) + np.log(lv))
        + np.log(A_inv + theta - 1)
        - np.log(u * v)
        + (1.0 / theta - 2) * np.log(A)
        - A_inv
    )

    # Re-add the exp(-A_inv) that we already accounted for
    loglik = np.sum(
        np.log(C + 1e-300)
        + np.log(np.clip(A_inv + theta - 1, 1e-10, None))
        - np.log(u) - np.log(v)
        + (theta - 1) * np.log(lu * lv)
        + (1.0 / theta - 2) * np.log(A)
    )

    return -loglik if np.isfinite(loglik) else 1e10


def _fit_gumbel(u: np.ndarray, v: np.ndarray) -> dict:
    """Fit Gumbel copula via MLE."""
    result = minimize_scalar(
        lambda t: _gumbel_loglik(t, u, v),
        bounds=(1.001, 50.0), method="bounded"
    )
    theta = result.x
    loglik = -result.fun
    k = 1
    aic = 2 * k - 2 * loglik
    # Upper tail dependence: lambda_U = 2 - 2^(1/theta)
    tail_upper = 2 - 2 ** (1.0 / theta) if theta > 1 else 0.0

    return {
        "family": "gumbel",
        "theta": round(float(theta), 4),
        "loglik": round(float(loglik), 2),
        "aic": round(float(aic), 2),
        "tail_lower": 0.0,  # Gumbel has no lower tail dependence
        "tail_upper": round(float(tail_upper), 4),
        "n_params": k,
    }


# ── Frank Copula ────────────────────────────────────────────────────────────


def _frank_loglik(theta: float, u: np.ndarray, v: np.ndarray) -> float:
    """Negative log-likelihood for Frank copula. theta != 0."""
    if abs(theta) < 0.01:
        return 1e10
    u = np.clip(u, 1e-10, 1 - 1e-10)
    v = np.clip(v, 1e-10, 1 - 1e-10)

    et = np.exp(-theta)
    etu = np.exp(-theta * u)
    etv = np.exp(-theta * v)

    num = -theta * (1 - et) * np.exp(-theta * (u + v))
    denom = ((1 - et) - (1 - etu) * (1 - etv)) ** 2
    denom = np.clip(denom, 1e-300, None)

    density = num / denom
    density = np.clip(np.abs(density), 1e-300, None)
    loglik = np.sum(np.log(density))

    return -loglik if np.isfinite(loglik) else 1e10


def _fit_frank(u: np.ndarray, v: np.ndarray) -> dict:
    """Fit Frank copula via MLE."""
    result = minimize_scalar(
        lambda t: _frank_loglik(t, u, v),
        bounds=(-50.0, 50.0), method="bounded"
    )
    theta = result.x
    loglik = -result.fun
    k = 1
    aic = 2 * k - 2 * loglik

    return {
        "family": "frank",
        "theta": round(float(theta), 4),
        "loglik": round(float(loglik), 2),
        "aic": round(float(aic), 2),
        "tail_lower": 0.0,  # Frank has no tail dependence
        "tail_upper": 0.0,
        "n_params": k,
    }


# ── Student-t Copula ───────────────────────────────────────────────────────


def _fit_student_t(u: np.ndarray, v: np.ndarray) -> dict:
    """Fit Student-t copula via method of moments + profile likelihood.

    Parameters: rho (correlation), nu (degrees of freedom).
    Tail dependence: lambda = 2 * t_{nu+1}(-sqrt((nu+1)(1-rho)/(1+rho)))
    """
    # Transform to t-marginals
    # Start with Kendall's tau to estimate rho
    tau, _ = stats.kendalltau(u, v)
    rho_init = np.sin(np.pi * tau / 2)  # Relationship between tau and rho for elliptical
    rho_init = np.clip(rho_init, -0.99, 0.99)

    # Profile likelihood over nu (degrees of freedom)
    best_loglik = -1e10
    best_nu = 5
    best_rho = rho_init

    for nu in [2, 3, 4, 5, 8, 10, 15, 20, 30]:
        # Transform uniform marginals to t-marginals
        x = stats.t.ppf(np.clip(u, 0.001, 0.999), df=nu)
        y = stats.t.ppf(np.clip(v, 0.001, 0.999), df=nu)

        # MLE for rho given nu
        rho = np.corrcoef(x, y)[0, 1]
        rho = np.clip(rho, -0.99, 0.99)

        # Bivariate t log-likelihood
        n = len(x)
        det = 1 - rho ** 2
        if det <= 0:
            continue

        Q = (x ** 2 - 2 * rho * x * y + y ** 2) / det
        loglik = (
            n * np.log(stats.gamma((nu + 2) / 2).args[0] if hasattr(stats.gamma, 'args') else 1)
            - n * np.log(stats.gamma(nu / 2).args[0] if hasattr(stats.gamma, 'args') else 1)
            - n * np.log(nu * np.pi * np.sqrt(det))
            - ((nu + 2) / 2) * np.sum(np.log(1 + Q / nu))
            + n * (nu / 2) * np.log(nu)
        )

        # Use scipy for proper log-likelihood
        try:
            from scipy.special import gammaln
            loglik = (
                n * gammaln((nu + 2) / 2)
                - n * gammaln(nu / 2)
                - n * np.log(nu * np.pi * np.sqrt(det))
                - ((nu + 2) / 2) * np.sum(np.log(1 + Q / nu))
            )
        except Exception:
            continue

        if np.isfinite(loglik) and loglik > best_loglik:
            best_loglik = loglik
            best_nu = nu
            best_rho = rho

    k = 2  # rho + nu
    aic = 2 * k - 2 * best_loglik

    # Tail dependence for bivariate t-copula
    # lambda = 2 * t_{nu+1}(-sqrt((nu+1)(1-rho)/(1+rho)))
    if best_rho < 1:
        arg = -np.sqrt((best_nu + 1) * (1 - best_rho) / (1 + best_rho))
        tail = 2 * stats.t.cdf(arg, df=best_nu + 1)
    else:
        tail = 1.0

    return {
        "family": "student_t",
        "rho": round(float(best_rho), 4),
        "nu": int(best_nu),
        "loglik": round(float(best_loglik), 2),
        "aic": round(float(aic), 2),
        "tail_lower": round(float(tail), 4),  # Symmetric
        "tail_upper": round(float(tail), 4),
        "n_params": k,
    }


# ══════════════════════════════════════════════════════════════════════════════
# MODEL SELECTION & HIGH-LEVEL API
# ══════════════════════════════════════════════════════════════════════════════


def fit_best_copula(u: np.ndarray, v: np.ndarray) -> dict:
    """Fit all copula families and select the best by AIC.

    Args:
        u, v: Pseudo-observations (uniform marginals) of two assets.

    Returns:
        Dict with best copula parameters, all fits, and model comparison.
    """
    fits = {}

    try:
        fits["clayton"] = _fit_clayton(u, v)
    except Exception as e:
        logger.debug("Clayton fit failed: %s", e)

    try:
        fits["gumbel"] = _fit_gumbel(u, v)
    except Exception as e:
        logger.debug("Gumbel fit failed: %s", e)

    try:
        fits["frank"] = _fit_frank(u, v)
    except Exception as e:
        logger.debug("Frank fit failed: %s", e)

    try:
        fits["student_t"] = _fit_student_t(u, v)
    except Exception as e:
        logger.debug("Student-t fit failed: %s", e)

    if not fits:
        return {"best": None, "all_fits": {}, "selection": "none"}

    # Select by AIC (lower = better)
    best_name = min(fits, key=lambda k: fits[k].get("aic", 1e10))
    best_fit = fits[best_name]

    return {
        "best": best_fit,
        "all_fits": fits,
        "selection": best_name,
        "n_candidates": len(fits),
    }


def analyze_pair_copula(
    ticker_a: str,
    ticker_b: str,
    lookback_days: int = _LOOKBACK,
) -> Optional[dict]:
    """Full copula analysis for a pair of stocks.

    Fetches data, fits all copula families, selects best,
    and reports tail dependence with confidence.
    """
    try:
        import yfinance as yf

        tickers = [ticker_a, ticker_b]
        end = pd.Timestamp.now()
        start = end - pd.Timedelta(days=int(lookback_days * 1.5))

        prices = yf.download(
            tickers, start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"), progress=False, auto_adjust=True,
        )

        if prices.empty:
            return None

        if isinstance(prices.columns, pd.MultiIndex):
            close = prices["Close"]
        else:
            close = prices

        returns = close.pct_change().dropna()
        if len(returns) < _MIN_OBS:
            return None

        # Trim to lookback
        if len(returns) > lookback_days:
            returns = returns.iloc[-lookback_days:]

    except Exception as e:
        logger.warning("Data fetch failed for copula analysis: %s", e)
        return None

    r_a = returns[ticker_a].values
    r_b = returns[ticker_b].values

    # Convert to pseudo-observations
    u = _to_pseudo_observations(r_a)
    v = _to_pseudo_observations(r_b)

    # Fit copulas
    copula_result = fit_best_copula(u, v)

    # Linear correlation for comparison
    pearson = float(np.corrcoef(r_a, r_b)[0, 1])
    tau, _ = stats.kendalltau(r_a, r_b)

    # Empirical tail dependence (for comparison with parametric)
    q = 0.05
    empirical_lower = float(np.mean((u <= q) & (v <= q)) / q) if q > 0 else 0

    best = copula_result.get("best", {})

    return {
        "pair": f"{ticker_a}/{ticker_b}",
        "observations": len(returns),
        "correlation": {
            "pearson": round(float(pearson), 4),
            "kendall_tau": round(float(tau), 4),
        },
        "copula": copula_result,
        "tail_dependence": {
            "lower": best.get("tail_lower", 0.0) if best else 0.0,
            "upper": best.get("tail_upper", 0.0) if best else 0.0,
            "empirical_lower_5pct": round(empirical_lower, 4),
        },
        "interpretation": _interpret_copula(best, pearson) if best else "Copula fitting failed.",
    }


def _interpret_copula(best: dict, pearson: float) -> str:
    """Human-readable copula interpretation."""
    family = best.get("family", "unknown")
    tail_l = best.get("tail_lower", 0)
    tail_u = best.get("tail_upper", 0)

    parts = [f"Best copula: {family}."]

    if family == "clayton":
        parts.append(
            f"Asymmetric lower tail dependence (lambda_L={tail_l:.2f}): "
            "these assets tend to crash together more than they rally together."
        )
    elif family == "gumbel":
        parts.append(
            f"Asymmetric upper tail dependence (lambda_U={tail_u:.2f}): "
            "these assets rally together more than they crash together."
        )
    elif family == "student_t":
        parts.append(
            f"Symmetric tail dependence (lambda={tail_l:.2f}): "
            "co-movement in both tails. Low df = heavy tails."
        )
    elif family == "frank":
        parts.append("No tail dependence — extreme co-movements are rare.")

    # Compare with Pearson
    max_tail = max(tail_l, tail_u)
    if max_tail > 0.3 and abs(pearson) < 0.5:
        parts.append(
            f"WARNING: Pearson correlation ({pearson:.2f}) understates tail risk. "
            f"Copula reveals hidden co-crash probability of {max_tail:.0%}."
        )

    return " ".join(parts)


def compute_copula_portfolio_risk(
    tickers: list[str],
    weights: Optional[list[float]] = None,
    lookback_days: int = _LOOKBACK,
    n_sims: int = _N_SIMS,
) -> Optional[dict]:
    """Compute portfolio VaR/CVaR using copula-based joint simulation.

    This captures tail dependence that standard correlation-based VaR misses.
    """
    try:
        import yfinance as yf

        end = pd.Timestamp.now()
        start = end - pd.Timedelta(days=int(lookback_days * 1.5))

        prices = yf.download(
            tickers, start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"), progress=False, auto_adjust=True,
        )

        if prices.empty:
            return None

        if isinstance(prices.columns, pd.MultiIndex):
            close = prices["Close"]
        else:
            close = prices

        returns = close.pct_change().dropna()
        if len(returns) < _MIN_OBS:
            return None

        if len(returns) > lookback_days:
            returns = returns.iloc[-lookback_days:]

    except Exception as e:
        logger.warning("Data fetch failed for copula portfolio risk: %s", e)
        return None

    if weights is None:
        weights = [1.0 / len(tickers)] * len(tickers)

    weights = np.array(weights)
    n_assets = len(tickers)

    # Fit Student-t copula to capture joint tail behavior
    U = _to_pseudo_observations(returns.values)

    # Estimate correlation matrix from pseudo-observations
    X_norm = stats.norm.ppf(np.clip(U, 0.001, 0.999))
    corr_matrix = np.corrcoef(X_norm.T)

    # Standard (Gaussian) portfolio VaR for comparison
    port_returns = returns.values @ weights
    var_gaussian = float(np.percentile(port_returns, _CONF_LEVEL * 100))
    cvar_gaussian = float(port_returns[port_returns <= var_gaussian].mean()) if np.any(port_returns <= var_gaussian) else var_gaussian

    # Monte Carlo with t-copula for tail-aware VaR
    rng = np.random.default_rng(42)
    try:
        # Generate correlated normal samples
        L = np.linalg.cholesky(corr_matrix)
        Z = rng.standard_normal((n_sims, n_assets))
        corr_Z = Z @ L.T

        # Add tail fatness via chi-squared mixing (t-copula)
        nu = 5  # degrees of freedom
        chi2 = rng.chisquare(nu, size=n_sims) / nu
        T = corr_Z / np.sqrt(chi2[:, np.newaxis])

        # Transform to uniform via t-CDF
        U_sim = stats.t.cdf(T, df=nu)

        # Transform back to returns using empirical marginals
        sim_returns = np.zeros_like(U_sim)
        for j in range(n_assets):
            marginal = np.sort(returns.iloc[:, j].values)
            indices = (U_sim[:, j] * len(marginal)).astype(int)
            indices = np.clip(indices, 0, len(marginal) - 1)
            sim_returns[:, j] = marginal[indices]

        # Portfolio returns
        port_sim = sim_returns @ weights
        var_copula = float(np.percentile(port_sim, _CONF_LEVEL * 100))
        cvar_copula = float(port_sim[port_sim <= var_copula].mean()) if np.any(port_sim <= var_copula) else var_copula

    except np.linalg.LinAlgError:
        logger.warning("Cholesky failed — correlation matrix not positive definite")
        var_copula = var_gaussian
        cvar_copula = cvar_gaussian

    return {
        "tickers": tickers,
        "weights": [round(w, 4) for w in weights],
        "observations": len(returns),
        "gaussian": {
            "var_95": round(var_gaussian * 100, 2),
            "cvar_95": round(cvar_gaussian * 100, 2),
        },
        "copula_t": {
            "var_95": round(var_copula * 100, 2),
            "cvar_95": round(cvar_copula * 100, 2),
            "degrees_of_freedom": 5,
        },
        "tail_risk_underestimate_pct": round(
            (var_copula / var_gaussian - 1) * 100 if var_gaussian != 0 else 0, 1
        ),
        "interpretation": (
            f"Copula VaR ({var_copula*100:.2f}%) is "
            f"{'worse' if var_copula < var_gaussian else 'better'} "
            f"than Gaussian VaR ({var_gaussian*100:.2f}%). "
            f"{'Standard risk models may understate tail risk for this portfolio.' if var_copula < var_gaussian * 1.1 else 'Tail dependence effect is modest.'}"
        ),
    }
