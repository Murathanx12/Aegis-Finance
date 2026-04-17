"""
Aegis Finance — Portfolio Risk Number (1-100)
================================================

Bloomberg PORT's most iconic feature: a single number that tells you
how risky your portfolio is. Risk Number 1 = Treasury bills,
Risk Number 100 = leveraged crypto.

Methodology:
  1. Portfolio volatility (annualized, 40% weight)
  2. Maximum drawdown over lookback (20% weight)
  3. CVaR 95% (tail risk, 15% weight)
  4. Concentration risk (Herfindahl index, 10% weight)
  5. Beta exposure (market sensitivity, 15% weight)

Each component is mapped to a 1-100 scale using percentile ranks
against historical S&P 500 data and reference portfolios.

Usage:
    from backend.services.risk_number import compute_risk_number
    risk = compute_risk_number(returns_df, weights)
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# Reference calibration: maps raw metric values to 1-100 scale
# Based on historical data for portfolios ranging from 100% T-bills to 100% leveraged equities
_CALIBRATION = {
    "volatility": {
        # annualized vol → risk number contribution
        "breakpoints": [0.02, 0.05, 0.08, 0.12, 0.16, 0.20, 0.25, 0.35, 0.50, 0.80],
        "scores":      [5,    15,   25,   35,   45,   55,   65,   75,   85,   95],
    },
    "max_drawdown": {
        # max dd (absolute) → risk number contribution
        "breakpoints": [0.02, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.60, 0.80],
        "scores":      [5,    15,   25,   35,   45,   55,   65,   75,   85,   95],
    },
    "cvar_95": {
        # daily CVaR 95% (absolute) → risk number contribution
        "breakpoints": [0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.07, 0.10],
        "scores":      [5,     15,   25,    35,   45,    55,   65,   75,   85,   95],
    },
    "beta": {
        # portfolio beta → risk number contribution
        "breakpoints": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0],
        "scores":      [5,   15,  25,  35,  45,  55,  65,  75,  85,  95],
    },
    "concentration": {
        # Herfindahl index → risk number contribution
        "breakpoints": [0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.60, 0.80, 1.0],
        "scores":      [5,    15,   25,   35,   45,   55,   65,   75,   85,   95],
    },
}

# Component weights (must sum to 1.0)
_WEIGHTS = {
    "volatility": 0.40,
    "max_drawdown": 0.20,
    "cvar_95": 0.15,
    "concentration": 0.10,
    "beta": 0.15,
}


def _interpolate_score(value: float, breakpoints: list, scores: list) -> float:
    """Linearly interpolate between calibration breakpoints."""
    if value <= breakpoints[0]:
        return float(scores[0])
    if value >= breakpoints[-1]:
        return float(scores[-1])
    for i in range(len(breakpoints) - 1):
        if breakpoints[i] <= value <= breakpoints[i + 1]:
            frac = (value - breakpoints[i]) / (breakpoints[i + 1] - breakpoints[i])
            return float(scores[i] + frac * (scores[i + 1] - scores[i]))
    return 50.0  # fallback


def compute_risk_number(
    returns: pd.DataFrame,
    weights: dict[str, float],
    benchmark_returns: Optional[pd.Series] = None,
    lookback_days: int = 252,
) -> dict:
    """Compute a Bloomberg PORT-style risk number for a portfolio.

    Args:
        returns: DataFrame of daily returns (columns = tickers)
        weights: Dict of {ticker: weight} (must sum to ~1.0)
        benchmark_returns: S&P 500 daily returns for beta calculation
        lookback_days: Lookback window for metrics

    Returns:
        Dict with risk_number (1-100), components, interpretation, and breakdown.
    """
    # Validate inputs
    available = [t for t in weights if t in returns.columns]
    if len(available) < 1:
        return _fallback_result("No valid tickers in returns data")

    # Build portfolio return series
    w = np.array([weights[t] for t in available])
    w = w / w.sum()  # re-normalize
    # Drop rows where any ticker has NaN before computing weighted sum,
    # otherwise sum(axis=1) silently skips NaN and deflates returns
    trimmed = returns[available].iloc[-lookback_days:].dropna()
    port_returns = (trimmed * w).sum(axis=1)

    if len(port_returns) < 30:
        return _fallback_result("Insufficient return history")

    # 1. Volatility
    ann_vol = float(port_returns.std() * np.sqrt(252))
    vol_score = _interpolate_score(ann_vol, **_CALIBRATION["volatility"])

    # 2. Maximum drawdown
    cum_returns = (1 + port_returns).cumprod()
    running_max = cum_returns.cummax()
    drawdowns = (cum_returns - running_max) / running_max
    max_dd = abs(float(drawdowns.min()))
    dd_score = _interpolate_score(max_dd, **_CALIBRATION["max_drawdown"])

    # 3. CVaR 95%
    sorted_returns = np.sort(port_returns.values)
    n_tail = max(1, int(len(sorted_returns) * 0.05))
    cvar_95 = abs(float(sorted_returns[:n_tail].mean()))
    cvar_score = _interpolate_score(cvar_95, **_CALIBRATION["cvar_95"])

    # 4. Concentration (Herfindahl index)
    hhi = float(np.sum(w ** 2))
    conc_score = _interpolate_score(hhi, **_CALIBRATION["concentration"])

    # 5. Beta
    beta = 1.0
    if benchmark_returns is not None:
        aligned = pd.DataFrame({
            "port": port_returns,
            "bench": benchmark_returns,
        }).dropna()
        if len(aligned) > 30:
            cov = np.cov(aligned["port"], aligned["bench"])
            if cov[1, 1] > 0:
                beta = float(cov[0, 1] / cov[1, 1])
    beta_score = _interpolate_score(abs(beta), **_CALIBRATION["beta"])

    # Weighted composite
    risk_number = (
        _WEIGHTS["volatility"] * vol_score
        + _WEIGHTS["max_drawdown"] * dd_score
        + _WEIGHTS["cvar_95"] * cvar_score
        + _WEIGHTS["concentration"] * conc_score
        + _WEIGHTS["beta"] * beta_score
    )
    risk_number = int(round(np.clip(risk_number, 1, 99)))

    # Interpretation
    if risk_number <= 20:
        level = "very_low"
        description = "Very conservative portfolio — minimal market exposure"
    elif risk_number <= 40:
        level = "low"
        description = "Conservative portfolio — moderate income focus"
    elif risk_number <= 60:
        level = "moderate"
        description = "Balanced portfolio — mix of growth and stability"
    elif risk_number <= 80:
        level = "high"
        description = "Aggressive portfolio — significant equity exposure"
    else:
        level = "very_high"
        description = "Very aggressive portfolio — concentrated equity/growth"

    return {
        "risk_number": risk_number,
        "level": level,
        "description": description,
        "components": {
            "volatility": {
                "value": round(ann_vol * 100, 1),
                "unit": "%",
                "score": round(vol_score, 0),
                "weight": _WEIGHTS["volatility"],
            },
            "max_drawdown": {
                "value": round(max_dd * 100, 1),
                "unit": "%",
                "score": round(dd_score, 0),
                "weight": _WEIGHTS["max_drawdown"],
            },
            "cvar_95": {
                "value": round(cvar_95 * 100, 2),
                "unit": "%",
                "score": round(cvar_score, 0),
                "weight": _WEIGHTS["cvar_95"],
            },
            "concentration": {
                "value": round(hhi, 3),
                "unit": "HHI",
                "score": round(conc_score, 0),
                "weight": _WEIGHTS["concentration"],
            },
            "beta": {
                "value": round(beta, 2),
                "unit": "",
                "score": round(beta_score, 0),
                "weight": _WEIGHTS["beta"],
            },
        },
    }


def _fallback_result(reason: str) -> dict:
    return {
        "risk_number": 50,
        "level": "moderate",
        "description": f"Default risk number — {reason}",
        "components": {},
    }
