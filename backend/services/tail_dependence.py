"""
Aegis Finance — Cross-Asset Tail Dependence & Contagion Analysis
=================================================================

Measures how assets co-crash using empirical copula methods. This goes beyond
linear correlation (Pearson) to capture nonlinear dependence in extreme events.

Key concepts:
  - Tail Dependence Coefficient (λ_L): probability that asset B crashes given
    asset A crashes. Estimated via empirical copula (no parametric assumption).
  - Contagion Score: how much diversification benefit disappears during tail events.
    High contagion = portfolio risk is understated by standard correlation.
  - Correlation-Tail Divergence: difference between linear correlation and tail
    dependence. Large divergence = hidden tail risk not visible in normal markets.

Theory:
  Lower tail dependence λ_L = lim(u→0) P(U₁ ≤ u | U₂ ≤ u)
  where U₁, U₂ are probability integral transforms (ranks) of asset returns.

  Empirical estimator (Frahm, Junker & Schmidt, 2005):
    λ̂_L(q) = P(U₁ ≤ q, U₂ ≤ q) / q
  averaged over q ∈ [q_lo, q_hi] for robustness.

References:
  - Frahm, Junker & Schmidt (2005) "Estimating the tail-dependence coefficient"
  - Embrechts, McNeil & Straumann (2002) "Correlation and dependence in risk management"
  - Ang & Chen (2002) "Asymmetric correlations of equity portfolios" (JFE)

Usage:
    from backend.services.tail_dependence import analyze_tail_dependence
    result = analyze_tail_dependence(["AAPL", "MSFT", "GLD", "TLT"])
"""

import logging

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import kendalltau, rankdata

from backend.config import config

logger = logging.getLogger(__name__)

# Config
_TD_CFG = config.get("tail_dependence", {})
_LOOKBACK_DAYS = _TD_CFG.get("lookback_days", 756)  # 3 years
_QUANTILE_LO = _TD_CFG.get("quantile_lo", 0.02)
_QUANTILE_HI = _TD_CFG.get("quantile_hi", 0.10)
_N_QUANTILE_STEPS = _TD_CFG.get("n_quantile_steps", 9)
_ROLLING_WINDOW = _TD_CFG.get("rolling_window", 126)  # 6 months
_MIN_OBS = _TD_CFG.get("min_observations", 120)
_CONTAGION_THRESHOLD = _TD_CFG.get("contagion_threshold", 0.15)


def _fetch_returns(tickers: list[str], lookback: int = _LOOKBACK_DAYS) -> pd.DataFrame:
    """Fetch aligned daily returns for a list of tickers.

    Returns:
        DataFrame with tickers as columns, daily returns as values.
        Only includes dates where ALL tickers have data.
    """
    end = pd.Timestamp.now()
    start = end - pd.Timedelta(days=int(lookback * 1.5))  # buffer for holidays

    try:
        prices = yf.download(
            tickers, start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"), progress=False,
            auto_adjust=True,
        )
    except Exception as e:
        logger.error("Failed to download prices for tail dependence: %s", e)
        return pd.DataFrame()

    if prices.empty:
        return pd.DataFrame()

    # Handle multi-level columns from yfinance
    if isinstance(prices.columns, pd.MultiIndex):
        close = prices["Close"] if "Close" in prices.columns.get_level_values(0) else prices
    else:
        close = prices

    # Compute daily returns, drop NaN rows
    returns = close.pct_change().dropna()

    # Trim to requested lookback
    if len(returns) > lookback:
        returns = returns.iloc[-lookback:]

    # Only keep columns with enough data
    valid_cols = [c for c in returns.columns if returns[c].notna().sum() >= _MIN_OBS]
    returns = returns[valid_cols].dropna()

    return returns


def _empirical_copula_ranks(returns: pd.DataFrame) -> pd.DataFrame:
    """Transform returns to pseudo-observations (rank-based uniform marginals).

    Uses the probability integral transform: U_i = rank(X_i) / (n+1)
    The (n+1) denominator avoids 0 and 1 at boundaries (Genest & Favre, 2007).
    """
    n = len(returns)
    ranks = returns.apply(lambda col: rankdata(col, method="ordinal") / (n + 1))
    return ranks


def _pairwise_tail_dependence(
    u1: np.ndarray,
    u2: np.ndarray,
    q_lo: float = _QUANTILE_LO,
    q_hi: float = _QUANTILE_HI,
    n_steps: int = _N_QUANTILE_STEPS,
) -> dict:
    """Compute lower tail dependence between two uniform marginals.

    Averages λ̂_L(q) over a grid of quantile thresholds for robustness.
    Also computes upper tail dependence for completeness.

    Returns:
        Dict with lower_tail_dep, upper_tail_dep, and per-quantile breakdown.
    """
    n = len(u1)
    quantiles = np.linspace(q_lo, q_hi, n_steps)

    lower_lambdas = []
    upper_lambdas = []

    for q in quantiles:
        # Lower tail: P(U1 <= q, U2 <= q) / q
        joint_lower = np.sum((u1 <= q) & (u2 <= q)) / n
        lambda_l = joint_lower / q if q > 0 else 0.0
        lower_lambdas.append(float(lambda_l))

        # Upper tail: P(U1 > 1-q, U2 > 1-q) / q
        joint_upper = np.sum((u1 > 1 - q) & (u2 > 1 - q)) / n
        lambda_u = joint_upper / q if q > 0 else 0.0
        upper_lambdas.append(float(lambda_u))

    # Average across quantile grid (more robust than single-point estimate)
    lower_td = float(np.mean(lower_lambdas))
    upper_td = float(np.mean(upper_lambdas))

    return {
        "lower_tail_dep": round(lower_td, 4),
        "upper_tail_dep": round(upper_td, 4),
    }


def _compute_all_pairs(
    ranks: pd.DataFrame,
    returns: pd.DataFrame,
) -> list[dict]:
    """Compute tail dependence and correlation for all asset pairs.

    Returns list of dicts, one per pair, sorted by contagion risk (descending).
    """
    tickers = list(ranks.columns)
    n_assets = len(tickers)
    pairs = []

    for i in range(n_assets):
        for j in range(i + 1, n_assets):
            t1, t2 = tickers[i], tickers[j]
            u1 = ranks[t1].values
            u2 = ranks[t2].values

            td = _pairwise_tail_dependence(u1, u2)

            # Pearson correlation on returns
            pearson_corr = float(np.corrcoef(
                returns[t1].values, returns[t2].values
            )[0, 1])

            # Kendall's tau (rank correlation, more robust)
            tau, _ = kendalltau(returns[t1].values, returns[t2].values)

            # Contagion score: how much tail dependence exceeds what
            # Pearson correlation would predict. Under Gaussian copula,
            # tail dependence = 0 for any correlation < 1. So any positive
            # tail dep is "excess" contagion not captured by linear corr.
            # We also compare to Kendall tau to be more conservative.
            expected_from_corr = max(0, pearson_corr * 0.3)  # rough baseline
            contagion = max(0, td["lower_tail_dep"] - expected_from_corr)

            # Asymmetry: difference between lower and upper tail dependence
            # Positive = more co-crashing than co-rallying (common for equities)
            asymmetry = td["lower_tail_dep"] - td["upper_tail_dep"]

            pairs.append({
                "asset_1": t1,
                "asset_2": t2,
                "pearson_correlation": round(pearson_corr, 4),
                "kendall_tau": round(float(tau), 4),
                "lower_tail_dep": td["lower_tail_dep"],
                "upper_tail_dep": td["upper_tail_dep"],
                "tail_asymmetry": round(asymmetry, 4),
                "contagion_score": round(contagion, 4),
            })

    # Sort by contagion score descending (highest risk first)
    pairs.sort(key=lambda p: p["contagion_score"], reverse=True)
    return pairs


def _rolling_tail_dependence(
    returns: pd.DataFrame,
    asset_1: str,
    asset_2: str,
    window: int = _ROLLING_WINDOW,
) -> list[dict]:
    """Compute rolling tail dependence over time for a specific pair.

    Useful for detecting regime shifts in co-crash behavior.
    """
    n = len(returns)
    if n < window + 20:
        return []

    results = []
    step = max(1, window // 4)  # step every quarter-window for efficiency

    for end_idx in range(window, n, step):
        start_idx = end_idx - window
        window_returns = returns.iloc[start_idx:end_idx]

        # Rank within window
        r1 = rankdata(window_returns[asset_1].values, method="ordinal") / (window + 1)
        r2 = rankdata(window_returns[asset_2].values, method="ordinal") / (window + 1)

        td = _pairwise_tail_dependence(r1, r2)
        pearson = float(np.corrcoef(
            window_returns[asset_1].values,
            window_returns[asset_2].values,
        )[0, 1])

        results.append({
            "date": str(window_returns.index[-1].date()),
            "lower_tail_dep": td["lower_tail_dep"],
            "upper_tail_dep": td["upper_tail_dep"],
            "pearson_correlation": round(pearson, 4),
        })

    return results


def _cluster_analysis(pairs: list[dict], tickers: list[str]) -> list[dict]:
    """Identify clusters of assets with high tail dependence.

    Uses a simple threshold-based approach: assets are in the same
    "contagion cluster" if their lower tail dependence exceeds the threshold.

    Returns list of clusters, each with member tickers and avg tail dep.
    """
    from collections import defaultdict, deque

    threshold = _TD_CFG.get("cluster_threshold", 0.20)

    # Build adjacency from high-tail-dep pairs
    adj: dict[str, set[str]] = defaultdict(set)
    for p in pairs:
        if p["lower_tail_dep"] >= threshold:
            adj[p["asset_1"]].add(p["asset_2"])
            adj[p["asset_2"]].add(p["asset_1"])

    # Simple connected components via BFS
    visited: set[str] = set()
    clusters = []

    for ticker in tickers:
        if ticker in visited or ticker not in adj:
            continue

        # BFS using deque for O(1) popleft (list.pop(0) is O(n))
        cluster = set()
        queue = deque([ticker])
        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            cluster.add(node)
            for neighbor in adj.get(node, set()):
                if neighbor not in visited:
                    queue.append(neighbor)

        if len(cluster) >= 2:
            # Compute avg tail dep within cluster
            cluster_pairs = [
                p for p in pairs
                if p["asset_1"] in cluster and p["asset_2"] in cluster
            ]
            avg_td = float(np.mean([p["lower_tail_dep"] for p in cluster_pairs])) if cluster_pairs else 0.0

            clusters.append({
                "members": sorted(cluster),
                "n_members": len(cluster),
                "avg_lower_tail_dep": round(avg_td, 4),
                "interpretation": _interpret_cluster(avg_td, len(cluster)),
            })

    # Sort by size * avg_td (biggest risk clusters first)
    clusters.sort(key=lambda c: c["n_members"] * c["avg_lower_tail_dep"], reverse=True)
    return clusters


def _interpret_cluster(avg_td: float, n_members: int) -> str:
    """Human-readable interpretation of a contagion cluster."""
    if avg_td > 0.40:
        severity = "Very high"
    elif avg_td > 0.25:
        severity = "High"
    else:
        severity = "Moderate"

    return (
        f"{severity} co-crash risk among {n_members} assets. "
        f"In tail events, these assets tend to move together "
        f"(avg tail dep: {avg_td:.0%}), reducing diversification benefit."
    )


def _portfolio_contagion_summary(pairs: list[dict], tickers: list[str]) -> dict:
    """Compute portfolio-level contagion metrics.

    Returns:
        Dict with overall contagion score, diversification quality,
        and risk assessment.
    """
    if not pairs:
        return {"overall_contagion": 0.0, "diversification_quality": "unknown"}

    avg_lower_td = float(np.mean([p["lower_tail_dep"] for p in pairs]))
    avg_pearson = float(np.mean([p["pearson_correlation"] for p in pairs]))
    max_lower_td = float(np.max([p["lower_tail_dep"] for p in pairs]))
    avg_contagion = float(np.mean([p["contagion_score"] for p in pairs]))

    # Hidden risk: tail dep much higher than correlation would suggest
    hidden_risk = max(0, avg_lower_td - max(0, avg_pearson * 0.3))

    # Diversification quality rating
    if avg_lower_td < 0.10:
        div_quality = "excellent"
        div_explanation = "Low tail dependence — diversification holds up well in crashes."
    elif avg_lower_td < 0.20:
        div_quality = "good"
        div_explanation = "Moderate tail dependence — some diversification erosion in crashes."
    elif avg_lower_td < 0.35:
        div_quality = "fair"
        div_explanation = "Elevated tail dependence — significant diversification loss in crashes."
    else:
        div_quality = "poor"
        div_explanation = "High tail dependence — portfolio behaves like a single asset in crashes."

    return {
        "overall_contagion": round(avg_contagion, 4),
        "avg_lower_tail_dep": round(avg_lower_td, 4),
        "avg_pearson_correlation": round(avg_pearson, 4),
        "max_lower_tail_dep": round(max_lower_td, 4),
        "hidden_risk_score": round(hidden_risk, 4),
        "diversification_quality": div_quality,
        "diversification_explanation": div_explanation,
        "n_pairs": len(pairs),
        "n_high_contagion_pairs": sum(
            1 for p in pairs if p["contagion_score"] > _CONTAGION_THRESHOLD
        ),
    }


def analyze_tail_dependence(
    tickers: list[str],
    lookback: int | None = None,
    include_rolling: bool = False,
    rolling_pair: tuple[str, str] | None = None,
) -> dict:
    """Full cross-asset tail dependence analysis.

    Args:
        tickers: List of ticker symbols (2-20 assets).
        lookback: Number of trading days to analyze (default from config).
        include_rolling: Whether to include rolling tail dep for top pair.
        rolling_pair: Specific pair for rolling analysis (asset_1, asset_2).

    Returns:
        Dict with pairwise tail dependence, clusters, portfolio summary,
        and optionally rolling time series.
    """
    if lookback is None:
        lookback = _LOOKBACK_DAYS

    if len(tickers) < 2:
        return {"error": "Need at least 2 tickers for tail dependence analysis"}
    if len(tickers) > 20:
        tickers = tickers[:20]
        logger.warning("Tail dependence: capped at 20 tickers")

    # Fetch and align returns
    returns = _fetch_returns(tickers, lookback)
    if returns.empty or len(returns.columns) < 2:
        return {"error": "Insufficient price data for tail dependence analysis"}

    actual_tickers = list(returns.columns)
    n_obs = len(returns)

    # Compute pseudo-observations (rank transform)
    ranks = _empirical_copula_ranks(returns)

    # Pairwise analysis
    pairs = _compute_all_pairs(ranks, returns)

    # Cluster detection
    clusters = _cluster_analysis(pairs, actual_tickers)

    # Portfolio-level summary
    summary = _portfolio_contagion_summary(pairs, actual_tickers)

    result = {
        "tickers": actual_tickers,
        "n_observations": n_obs,
        "lookback_days": lookback,
        "pairs": pairs,
        "clusters": clusters,
        "portfolio_summary": summary,
    }

    # Rolling analysis
    if include_rolling:
        if rolling_pair and rolling_pair[0] in actual_tickers and rolling_pair[1] in actual_tickers:
            a1, a2 = rolling_pair
        elif pairs:
            # Default to highest-contagion pair
            a1, a2 = pairs[0]["asset_1"], pairs[0]["asset_2"]
        else:
            a1, a2 = actual_tickers[0], actual_tickers[1]

        result["rolling"] = {
            "pair": [a1, a2],
            "series": _rolling_tail_dependence(returns, a1, a2),
        }

    return result
