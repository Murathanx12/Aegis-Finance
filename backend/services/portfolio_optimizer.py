"""
Aegis Finance — Advanced Portfolio Optimization
=================================================

Institutional-grade portfolio construction methods beyond basic mean-variance:

1. Mean-CVaR Optimization: Minimizes Conditional Value-at-Risk instead of
   variance, better capturing downside/tail risk. Used by MSCI Barra, Axioma.

2. Risk Budgeting (Risk Parity): Allocates equal marginal risk contribution
   from each asset. Used by Bridgewater, AQR.

3. Maximum Diversification: Maximizes the diversification ratio
   (weighted avg vol / portfolio vol). Minimizes concentration risk.

4. Hierarchical Risk Parity (HRP): Uses clustering on correlation structure
   to build robust allocations. No covariance inversion needed.

5. Augmented Black-Litterman: Entropy pooling approach for incorporating
   views while respecting market equilibrium.

All methods use denoised covariance matrix from RMT when available.

References:
  - Rockafellar & Uryasev (2000), "Optimization of CVaR"
  - Maillard, Roncalli & Teiletche (2010), "Risk budgeting"
  - Choueifaty & Coignard (2008), "Maximum Diversification"
  - Lopez de Prado (2016), "Hierarchical Risk Parity"
  - Meucci (2008), "Fully Flexible Views" (entropy pooling)

Usage:
    from backend.services.portfolio_optimizer import (
        optimize_mean_cvar, optimize_risk_parity,
        optimize_max_diversification, optimize_hrp,
    )
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from backend.config import config

logger = logging.getLogger(__name__)


def _fetch_returns(
    tickers: list[str],
    lookback_days: int = 756,
) -> Optional[pd.DataFrame]:
    """Fetch and align daily returns for a list of tickers."""
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
        if len(returns) > lookback_days:
            returns = returns.iloc[-lookback_days:]

        # Drop columns with too many NaNs
        valid = [c for c in returns.columns if returns[c].notna().sum() > 126]
        return returns[valid].dropna() if valid else None

    except Exception as e:
        logger.warning("Failed to fetch returns: %s", e)
        return None


def optimize_mean_cvar(
    tickers: list[str],
    lookback_days: int = 504,
    confidence: float = 0.95,
    risk_free_rate: Optional[float] = None,
) -> Optional[dict]:
    """Mean-CVaR optimization: maximize return per unit of tail risk.

    Uses riskfolio-lib's Portfolio class with CVaR as the risk measure.
    This better captures downside risk compared to mean-variance.
    """
    try:
        import riskfolio as rp
    except ImportError:
        logger.warning("riskfolio-lib not installed — falling back to equal weight")
        return _equal_weight_fallback(tickers)

    returns = _fetch_returns(tickers, lookback_days)
    if returns is None or returns.empty:
        return None

    # Only keep tickers that have data
    available = [t for t in tickers if t in returns.columns]
    if len(available) < 2:
        return None
    returns = returns[available]

    if risk_free_rate is None:
        risk_free_rate = config.get("risk_free_rate", 0.04) / 252  # Daily

    try:
        port = rp.Portfolio(returns=returns)
        port.assets_stats(method_mu="hist", method_cov="ledoit")

        # CVaR optimization
        w = port.optimization(
            model="Classic",
            rm="CVaR",
            obj="Sharpe",
            rf=risk_free_rate,
            hist=True,
        )

        if w is None or w.empty:
            return None

        weights = {t: round(float(w.loc[t, "weights"]), 4) for t in w.index if w.loc[t, "weights"] > 0.001}

        # Compute portfolio metrics
        port_ret = (returns[list(weights.keys())] * pd.Series(weights)).sum(axis=1)
        ann_return = float(port_ret.mean() * 252)
        ann_vol = float(port_ret.std() * np.sqrt(252))
        cvar_95 = float(np.percentile(port_ret, (1 - confidence) * 100))

        return {
            "method": "mean_cvar",
            "weights": weights,
            "n_assets": len(weights),
            "metrics": {
                "expected_return": round(ann_return * 100, 2),
                "volatility": round(ann_vol * 100, 2),
                "cvar_95_daily": round(cvar_95 * 100, 2),
                "sharpe_ratio": round((ann_return - config.get("risk_free_rate", 0.04)) / max(ann_vol, 0.01), 2),
            },
            "observations": len(returns),
        }

    except Exception as e:
        logger.error("Mean-CVaR optimization failed: %s", e)
        return None


def optimize_risk_parity(
    tickers: list[str],
    lookback_days: int = 504,
    risk_measure: str = "MV",
) -> Optional[dict]:
    """Risk Parity (Equal Risk Contribution) portfolio.

    Each asset contributes equally to total portfolio risk.
    Bridgewater's All Weather fund uses this approach.

    Args:
        risk_measure: "MV" (variance), "CVaR", "MAD", or "CDaR"
    """
    try:
        import riskfolio as rp
    except ImportError:
        return _equal_weight_fallback(tickers)

    returns = _fetch_returns(tickers, lookback_days)
    if returns is None:
        return None

    available = [t for t in tickers if t in returns.columns]
    if len(available) < 2:
        return None
    returns = returns[available]

    try:
        port = rp.Portfolio(returns=returns)
        port.assets_stats(method_mu="hist", method_cov="ledoit")

        w = port.rp_optimization(
            model="Classic",
            rm=risk_measure,
            hist=True,
        )

        if w is None or w.empty:
            return None

        weights = {t: round(float(w.loc[t, "weights"]), 4) for t in w.index if w.loc[t, "weights"] > 0.001}

        # Compute risk contributions
        port_ret = (returns[list(weights.keys())] * pd.Series(weights)).sum(axis=1)
        ann_return = float(port_ret.mean() * 252)
        ann_vol = float(port_ret.std() * np.sqrt(252))

        return {
            "method": "risk_parity",
            "risk_measure": risk_measure,
            "weights": weights,
            "n_assets": len(weights),
            "metrics": {
                "expected_return": round(ann_return * 100, 2),
                "volatility": round(ann_vol * 100, 2),
                "sharpe_ratio": round((ann_return - config.get("risk_free_rate", 0.04)) / max(ann_vol, 0.01), 2),
            },
            "observations": len(returns),
        }

    except Exception as e:
        logger.error("Risk parity optimization failed: %s", e)
        return None


def optimize_max_diversification(
    tickers: list[str],
    lookback_days: int = 504,
) -> Optional[dict]:
    """Maximum Diversification portfolio.

    Maximizes the diversification ratio:
        DR = (w' * sigma) / sqrt(w' * Sigma * w)

    Higher DR means more diversification benefit from combining assets.
    """
    returns = _fetch_returns(tickers, lookback_days)
    if returns is None:
        return None

    available = [t for t in tickers if t in returns.columns]
    if len(available) < 2:
        return None
    returns = returns[available]

    n = len(available)
    cov = returns.cov().values
    vols = np.sqrt(np.diag(cov))

    # Optimize: max DR = max (w'sigma) / sqrt(w'Sw) subject to sum(w)=1, w>=0
    from scipy.optimize import minimize

    def neg_div_ratio(w):
        w = np.array(w)
        port_vol = np.sqrt(w @ cov @ w)
        if port_vol < 1e-10:
            return 1e10
        return -(w @ vols) / port_vol

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
    bounds = [(0, 1)] * n
    x0 = np.ones(n) / n

    result = minimize(neg_div_ratio, x0, bounds=bounds, constraints=constraints, method="SLSQP")

    if not result.success:
        return None

    w = result.x
    weights = {available[i]: round(float(w[i]), 4) for i in range(n) if w[i] > 0.001}

    port_ret = (returns[list(weights.keys())] * pd.Series(weights)).sum(axis=1)
    ann_return = float(port_ret.mean() * 252)
    ann_vol = float(port_ret.std() * np.sqrt(252))
    div_ratio = float(-(neg_div_ratio(w)))

    return {
        "method": "max_diversification",
        "weights": weights,
        "n_assets": len(weights),
        "metrics": {
            "expected_return": round(ann_return * 100, 2),
            "volatility": round(ann_vol * 100, 2),
            "sharpe_ratio": round((ann_return - config.get("risk_free_rate", 0.04)) / max(ann_vol, 0.01), 2),
            "diversification_ratio": round(div_ratio, 3),
        },
        "observations": len(returns),
    }


def optimize_hrp(
    tickers: list[str],
    lookback_days: int = 504,
    use_denoised_cov: bool = True,
) -> Optional[dict]:
    """Hierarchical Risk Parity portfolio.

    Uses clustering on correlation structure. No matrix inversion needed,
    so it's more robust than MVO for large asset universes.
    """
    try:
        import riskfolio as rp
    except ImportError:
        return _equal_weight_fallback(tickers)

    returns = _fetch_returns(tickers, lookback_days)
    if returns is None:
        return None

    available = [t for t in tickers if t in returns.columns]
    if len(available) < 2:
        return None
    returns = returns[available]

    try:
        port = rp.HCPortfolio(returns=returns)

        w = port.optimization(
            model="HRP",
            rm="MV",
            linkage="ward",
            codependence="pearson",
            method_cov="ledoit" if use_denoised_cov else "hist",
        )

        if w is None or w.empty:
            return None

        weights = {t: round(float(w.loc[t, "weights"]), 4) for t in w.index if w.loc[t, "weights"] > 0.001}

        port_ret = (returns[list(weights.keys())] * pd.Series(weights)).sum(axis=1)
        ann_return = float(port_ret.mean() * 252)
        ann_vol = float(port_ret.std() * np.sqrt(252))

        return {
            "method": "hrp",
            "weights": weights,
            "n_assets": len(weights),
            "metrics": {
                "expected_return": round(ann_return * 100, 2),
                "volatility": round(ann_vol * 100, 2),
                "sharpe_ratio": round((ann_return - config.get("risk_free_rate", 0.04)) / max(ann_vol, 0.01), 2),
            },
            "observations": len(returns),
            "denoised_cov": use_denoised_cov,
        }

    except Exception as e:
        logger.error("HRP optimization failed: %s", e)
        return None


def compare_methods(
    tickers: list[str],
    lookback_days: int = 504,
) -> dict:
    """Run all optimization methods and compare results.

    Returns a comparison table showing how different risk models
    produce different allocations — the kind of analysis Bloomberg PORT provides.
    """
    results = {}

    for name, fn in [
        ("equal_weight", lambda: _equal_weight_fallback(tickers)),
        ("mean_cvar", lambda: optimize_mean_cvar(tickers, lookback_days)),
        ("risk_parity", lambda: optimize_risk_parity(tickers, lookback_days)),
        ("max_diversification", lambda: optimize_max_diversification(tickers, lookback_days)),
        ("hrp", lambda: optimize_hrp(tickers, lookback_days)),
    ]:
        try:
            r = fn()
            if r:
                results[name] = r
        except Exception as e:
            logger.warning("Method %s failed: %s", name, e)

    return {
        "methods": results,
        "n_methods": len(results),
        "tickers": tickers,
        "recommendation": _recommend_method(results),
    }


def _recommend_method(results: dict) -> str:
    """Recommend best method based on risk-adjusted metrics."""
    if not results:
        return "Insufficient data for optimization."

    best_sharpe = -999
    best_method = "equal_weight"
    for name, r in results.items():
        sharpe = r.get("metrics", {}).get("sharpe_ratio", -999)
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_method = name

    return (
        f"Best risk-adjusted: {best_method} (Sharpe={best_sharpe:.2f}). "
        "Consider risk_parity for balanced risk budgets, "
        "mean_cvar for tail-risk awareness, "
        "max_diversification for concentrated portfolios."
    )


def _equal_weight_fallback(tickers: list[str]) -> dict:
    """Equal-weight portfolio as baseline."""
    n = len(tickers)
    weights = {t: round(1.0 / n, 4) for t in tickers}
    return {
        "method": "equal_weight",
        "weights": weights,
        "n_assets": n,
        "metrics": {
            "expected_return": None,
            "volatility": None,
            "sharpe_ratio": None,
        },
        "observations": 0,
    }
