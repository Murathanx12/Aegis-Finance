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
        if not valid:
            return None
        returns = returns[valid]
        # Forward-fill small gaps then drop only rows where ALL columns are NaN
        # (plain .dropna() loses data when tickers have different start dates)
        returns = returns.ffill(limit=5).dropna(how="all")
        # Drop remaining rows that still have any NaN (incomplete after ffill)
        returns = returns.dropna()
        return returns if not returns.empty else None

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
    returns: Optional[pd.DataFrame] = None,
) -> Optional[dict]:
    """Hierarchical Risk Parity portfolio.

    Uses clustering on correlation structure. No matrix inversion needed,
    so it's more robust than MVO for large asset universes.

    Args:
        returns: Optional pre-built daily-returns DataFrame. When supplied,
            NO data is fetched — the caller owns the as-of bound. This is the
            leakage-safe entry point used by the PI lanes: live passes a panel
            ending at the latest bar, replay passes one truncated at the
            simulated date. When None, fetches the latest lookback_days
            (legitimate only for ad-hoc/spot use, never for backtests).
    """
    try:
        import riskfolio as rp
    except ImportError:
        return _equal_weight_fallback(tickers)

    if returns is None:
        returns = _fetch_returns(tickers, lookback_days)
    if returns is None or len(returns) == 0:
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
    apply_liquidity_adjustment: bool = True,
) -> dict:
    """Run all optimization methods and compare results.

    Returns a comparison table showing how different risk models
    produce different allocations — the kind of analysis Bloomberg PORT provides.

    Args:
        apply_liquidity_adjustment: If True, also shows liquidity-adjusted
            weights alongside raw optimizer output.
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

    # Apply liquidity adjustment to all methods
    liquidity_summary = None
    if apply_liquidity_adjustment and results:
        # Fetch liquidity once, reuse for all methods
        all_tickers = set()
        for r in results.values():
            all_tickers.update(r.get("weights", {}).keys())
        liq_scores = _fetch_liquidity_scores(list(all_tickers))

        if liq_scores:
            for name, r in results.items():
                adj = adjust_weights_for_liquidity(r.get("weights", {}), liq_scores)
                r["liquidity_adjusted"] = adj
            liquidity_summary = {
                "scores_available": len(liq_scores),
                "tickers_checked": list(liq_scores.keys()),
            }

    result = {
        "methods": results,
        "n_methods": len(results),
        "tickers": tickers,
        "recommendation": _recommend_method(results),
    }
    if liquidity_summary:
        result["liquidity_summary"] = liquidity_summary
    return result


def _recommend_method(results: dict) -> str:
    """Recommend best method based on risk-adjusted metrics."""
    if not results:
        return "Insufficient data for optimization."

    # sharpe_ratio can be explicitly None (equal_weight fallback) — a plain
    # `.get(..., -999)` does not protect against that and raised TypeError
    # for every compare_methods call.
    best_sharpe = None
    best_method = "equal_weight"
    for name, r in results.items():
        sharpe = (r.get("metrics") or {}).get("sharpe_ratio")
        if sharpe is not None and (best_sharpe is None or sharpe > best_sharpe):
            best_sharpe = sharpe
            best_method = name

    if best_sharpe is None:
        return "Insufficient data for optimization."

    return (
        f"Best risk-adjusted: {best_method} (Sharpe={best_sharpe:.2f}). "
        "Consider risk_parity for balanced risk budgets, "
        "mean_cvar for tail-risk awareness, "
        "max_diversification for concentrated portfolios."
    )


def adjust_weights_for_liquidity(
    weights: dict[str, float],
    liquidity_scores: Optional[dict[str, dict]] = None,
) -> dict:
    """Adjust portfolio weights based on liquidity constraints.

    Institutional portfolios penalize illiquid positions to avoid:
    - Slippage: large orders move price against you
    - Exit risk: can't sell quickly in a crash
    - Marking risk: illiquid positions have unreliable prices

    Algorithm:
    1. Compute a liquidity penalty factor for each asset (0 to max_reduction)
    2. Reduce illiquid weights by their penalty factor
    3. Redistribute freed weight pro-rata to liquid assets
    4. Hard-floor: zero out positions below minimum dollar volume

    Args:
        weights: Optimized {ticker: weight} dict
        liquidity_scores: {ticker: {"composite": 0-100, "tier": str,
                          "avg_dollar_volume_mm": float}} from liquidity_risk.
                          If None, fetches live from liquidity_risk service.

    Returns:
        Dict with adjusted weights, adjustments made, and liquidity summary.
    """
    _liq_cfg = config.get("liquidity_risk", {}).get("position_sizing", {})
    if not _liq_cfg.get("enabled", True):
        return {
            "weights": weights,
            "adjustments": {},
            "liquidity_adjusted": False,
        }

    # Fetch liquidity scores if not provided
    if liquidity_scores is None:
        liquidity_scores = _fetch_liquidity_scores(list(weights.keys()))

    if not liquidity_scores:
        return {
            "weights": weights,
            "adjustments": {},
            "liquidity_adjusted": False,
            "reason": "No liquidity data available",
        }

    min_dv = _liq_cfg.get("min_dollar_volume_mm", 1.0)
    penalty_exp = _liq_cfg.get("penalty_exponent", 0.5)
    max_reduction = _liq_cfg.get("max_weight_reduction", 0.50)
    score_threshold = _liq_cfg.get("score_threshold", 40)

    adjusted = {}
    adjustments = {}
    freed_weight = 0.0

    for ticker, w in weights.items():
        liq = liquidity_scores.get(ticker)
        if liq is None:
            # No liquidity data — keep original weight
            adjusted[ticker] = w
            continue

        score = liq.get("composite", 50)
        avg_dv = liq.get("avg_dollar_volume_mm", 100)

        # Hard floor: zero out below minimum dollar volume
        if avg_dv < min_dv:
            adjustments[ticker] = {
                "original_weight": round(w, 4),
                "adjusted_weight": 0.0,
                "reason": f"Below ${min_dv}M daily volume (${avg_dv:.1f}M)",
                "liquidity_score": score,
            }
            freed_weight += w
            adjusted[ticker] = 0.0
            continue

        # Penalty for scores below threshold
        if score < score_threshold:
            # Penalty scales with distance below threshold
            # score=40,threshold=40 → penalty=0
            # score=20,threshold=40 → penalty = (20/40)^0.5 * max_reduction
            shortfall = (score_threshold - score) / score_threshold
            penalty = min(shortfall ** penalty_exp * max_reduction, max_reduction)
            new_w = w * (1 - penalty)
            freed = w - new_w
            freed_weight += freed
            adjusted[ticker] = new_w
            adjustments[ticker] = {
                "original_weight": round(w, 4),
                "adjusted_weight": round(new_w, 4),
                "penalty_pct": round(penalty * 100, 1),
                "reason": f"Low liquidity score ({score:.0f}/100)",
                "liquidity_score": score,
            }
        else:
            adjusted[ticker] = w

    # Redistribute freed weight pro-rata to liquid positions (score >= threshold)
    liquid_tickers = [
        t for t, w in adjusted.items()
        if w > 0 and t not in adjustments
    ]
    liquid_total = sum(adjusted[t] for t in liquid_tickers)

    if freed_weight > 0.001 and liquid_total > 0:
        for t in liquid_tickers:
            share = adjusted[t] / liquid_total
            boost = freed_weight * share
            adjusted[t] += boost

    # Remove zero-weight positions
    adjusted = {t: round(w, 4) for t, w in adjusted.items() if w > 0.001}

    # Renormalize to sum to 1
    total = sum(adjusted.values())
    if total > 0 and abs(total - 1.0) > 0.001:
        adjusted = {t: round(w / total, 4) for t, w in adjusted.items()}

    return {
        "weights": adjusted,
        "adjustments": adjustments,
        "liquidity_adjusted": len(adjustments) > 0,
        "freed_weight_pct": round(freed_weight * 100, 2),
        "n_penalized": len(adjustments),
        "n_removed": sum(1 for a in adjustments.values() if a.get("adjusted_weight", 1) == 0),
    }


def _fetch_liquidity_scores(tickers: list[str]) -> dict[str, dict]:
    """Fetch liquidity scores for a list of tickers (uses cached service)."""
    try:
        from backend.services.liquidity_risk import compute_liquidity_metrics
    except ImportError:
        return {}

    scores = {}
    for ticker in tickers:
        try:
            result = compute_liquidity_metrics(ticker)
            if result and "score" in result:
                scores[ticker] = {
                    "composite": result["score"]["composite"],
                    "tier": result["score"]["tier"],
                    "avg_dollar_volume_mm": result["metrics"]["avg_dollar_volume_mm"],
                }
        except Exception:
            pass
    return scores


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
