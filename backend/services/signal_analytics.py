"""
Aegis Finance — Signal Analytics
==================================

Post-processing layer for screener signals. Adds:
  - Signal consensus scoring (component agreement)
  - Conviction decomposition (per-component contribution breakdown)
  - Risk-reward ratio (MC upside/downside)
  - Relative ranking with percentiles
  - Sector concentration warning for top picks

Usage:
    from backend.services.signal_analytics import enrich_screener_signals
    enriched = enrich_screener_signals(stocks, market_signal)
"""

import logging
from collections import Counter
from typing import Optional

import numpy as np

from backend.config import config

logger = logging.getLogger(__name__)


def compute_signal_consensus(components: dict) -> dict:
    """Measure agreement among signal components.

    A composite score of +0.2 where all components are mildly bullish is
    fundamentally different from +0.2 where half are strongly bullish and
    half are strongly bearish. This function captures that distinction.

    Args:
        components: Dict of {component_name: signal_value} from signal_engine.

    Returns:
        Dict with consensus metrics:
          - agreement_ratio: fraction of components with same sign as composite (0-1)
          - n_bullish / n_bearish / n_neutral: component counts by direction
          - dispersion: std dev of component values (high = conflicting signals)
          - consensus_label: "strong", "moderate", "weak", "conflicted"
    """
    if not components:
        return {
            "agreement_ratio": 0.0,
            "n_bullish": 0,
            "n_bearish": 0,
            "n_neutral": 0,
            "dispersion": 0.0,
            "consensus_label": "no_data",
        }

    values = list(components.values())
    n = len(values)
    composite_sign = np.sign(sum(values))

    neutral_threshold = 0.02
    n_bullish = sum(1 for v in values if v > neutral_threshold)
    n_bearish = sum(1 for v in values if v < -neutral_threshold)
    n_neutral = n - n_bullish - n_bearish

    # Agreement: fraction of non-neutral components that agree with composite direction
    non_neutral = [v for v in values if abs(v) > neutral_threshold]
    if non_neutral and composite_sign != 0:
        same_sign = sum(1 for v in non_neutral if np.sign(v) == composite_sign)
        agreement = same_sign / len(non_neutral)
    elif non_neutral:
        # Composite is ~0 but components exist: check if they cancel out
        agreement = 0.5
    else:
        agreement = 1.0  # all neutral = perfect agreement (on nothing)

    dispersion = float(np.std(values)) if len(values) > 1 else 0.0

    # Label
    if agreement >= 0.85 and dispersion < 0.30:
        label = "strong"
    elif agreement >= 0.65:
        label = "moderate"
    elif agreement >= 0.45:
        label = "weak"
    else:
        label = "conflicted"

    return {
        "agreement_ratio": round(agreement, 3),
        "n_bullish": n_bullish,
        "n_bearish": n_bearish,
        "n_neutral": n_neutral,
        "dispersion": round(dispersion, 3),
        "consensus_label": label,
    }


def compute_conviction_decomposition(
    components: dict,
    weights: Optional[dict] = None,
) -> list[dict]:
    """Break down composite signal into per-component contributions.

    Shows which components drive the signal and by how much, enabling
    users to understand *why* a stock is rated Buy vs Hold.

    Args:
        components: Dict of {component_name: signal_value}
        weights: Optional dict of {component_name: weight}. If None,
            uses default signal_weights from config.

    Returns:
        List of dicts sorted by absolute contribution (descending):
          [{name, value, weight, contribution, contribution_pct, direction}]
    """
    if not components:
        return []

    if weights is None:
        weights = config.get("signal_weights", {})

    total_w = sum(weights.get(k, 0) for k in components)
    if total_w == 0:
        total_w = 1.0

    decomposition = []
    total_abs_contribution = 0.0
    for name, value in components.items():
        w = weights.get(name, 0)
        contribution = value * w / total_w
        total_abs_contribution += abs(contribution)

    for name, value in components.items():
        w = weights.get(name, 0)
        contribution = value * w / total_w
        pct = (abs(contribution) / total_abs_contribution * 100
               if total_abs_contribution > 0 else 0)

        direction = "bullish" if value > 0.02 else ("bearish" if value < -0.02 else "neutral")

        decomposition.append({
            "name": name,
            "value": round(value, 3),
            "weight": round(w, 3),
            "contribution": round(contribution, 4),
            "contribution_pct": round(pct, 1),
            "direction": direction,
        })

    decomposition.sort(key=lambda x: abs(x["contribution"]), reverse=True)
    return decomposition


def compute_risk_reward(stock: dict) -> dict:
    """Compute risk-reward profile from Monte Carlo projections.

    Uses MC p10 (downside) and p90 (upside) 5Y returns to compute
    the upside/downside ratio. A ratio > 1 means more upside than downside.

    Args:
        stock: Stock dict with MC return fields from stock_analyzer.

    Returns:
        Dict with risk_reward_ratio, upside_pct, downside_pct, asymmetry label.
    """
    # Try multiple key patterns (screener vs full analysis format)
    upside = stock.get("mc_p90_5y_return") or stock.get("mc_p90_5y")
    downside = stock.get("mc_p10_5y_return") or stock.get("mc_p10_5y")
    median = stock.get("mc_median_5y_return") or stock.get("mc_median_5y")
    expected = stock.get("expected_return")

    if upside is None or downside is None:
        return {"available": False}

    # Downside is typically negative, upside is positive
    abs_downside = abs(downside) if downside < 0 else 0.01
    abs_upside = abs(upside) if upside > 0 else 0.01

    ratio = abs_upside / abs_downside if abs_downside > 0.01 else 10.0
    ratio = min(ratio, 10.0)  # cap extreme values

    if ratio >= 3.0:
        label = "highly_favorable"
    elif ratio >= 1.5:
        label = "favorable"
    elif ratio >= 0.8:
        label = "balanced"
    elif ratio >= 0.4:
        label = "unfavorable"
    else:
        label = "highly_unfavorable"

    return {
        "available": True,
        "risk_reward_ratio": round(ratio, 2),
        "upside_pct": round(upside, 1),
        "downside_pct": round(downside, 1),
        "median_return_pct": round(median, 1) if median is not None else None,
        "asymmetry": label,
    }


def rank_screener_signals(stocks: list[dict]) -> list[dict]:
    """Add relative ranking and percentile to screener stocks.

    Ranks by signal_score and adds percentile (100 = best, 0 = worst).

    Args:
        stocks: List of stock dicts from screener (must have signal_score).

    Returns:
        Same list with added rank, percentile, and tier fields.
    """
    if not stocks:
        return stocks

    # Sort by signal_score descending for ranking
    scored = [(i, s.get("signal_score", 0)) for i, s in enumerate(stocks)]
    scored.sort(key=lambda x: x[1], reverse=True)

    n = len(scored)
    for rank_idx, (orig_idx, score) in enumerate(scored):
        rank = rank_idx + 1
        # Percentile: 1st out of 30 = 100th percentile, 30th = ~3rd
        percentile = round((1 - rank_idx / max(n - 1, 1)) * 100, 1) if n > 1 else 50.0

        if percentile >= 75:
            tier = "top_quartile"
        elif percentile >= 50:
            tier = "above_median"
        elif percentile >= 25:
            tier = "below_median"
        else:
            tier = "bottom_quartile"

        stocks[orig_idx]["signal_rank"] = rank
        stocks[orig_idx]["signal_percentile"] = percentile
        stocks[orig_idx]["signal_tier"] = tier

    return stocks


def detect_sector_concentration(stocks: list[dict], top_n: int = 5) -> dict:
    """Check if top-ranked stocks are concentrated in few sectors.

    If all top picks are in the same sector, the screener is effectively
    making a sector bet rather than picking diverse opportunities.

    Args:
        stocks: List of stock dicts (must have signal_rank and sector).
        top_n: Number of top stocks to check for concentration.

    Returns:
        Dict with concentration metrics and warning if applicable.
    """
    analytics_cfg = config.get("signal_analytics", {})
    warn_threshold = analytics_cfg.get("concentration_warning_pct", 60)

    ranked = sorted(stocks, key=lambda s: s.get("signal_rank", 999))
    top = ranked[:min(top_n, len(ranked))]

    if not top:
        return {"concentrated": False, "top_n": 0}

    sectors = [s.get("sector", "Unknown") for s in top]
    sector_counts = Counter(sectors)
    dominant_sector, dominant_count = sector_counts.most_common(1)[0]
    concentration_pct = dominant_count / len(top) * 100

    concentrated = concentration_pct >= warn_threshold
    n_sectors = len(sector_counts)

    result = {
        "concentrated": concentrated,
        "top_n": len(top),
        "n_sectors_in_top": n_sectors,
        "sector_distribution": dict(sector_counts),
        "dominant_sector": dominant_sector,
        "dominant_pct": round(concentration_pct, 1),
    }

    if concentrated:
        result["warning"] = (
            f"Top {len(top)} picks are {concentration_pct:.0f}% concentrated in "
            f"{dominant_sector} — consider diversification"
        )

    return result


def enrich_screener_signals(
    stocks: list[dict],
    market_signal: Optional[dict] = None,
) -> dict:
    """Main entry point: enrich screener output with analytics.

    Adds ranking, consensus, risk-reward, and concentration analysis
    to the raw screener stock list.

    Args:
        stocks: List of stock dicts from screener.
        market_signal: Market-level signal dict (with components).

    Returns:
        Dict with enriched stocks list and aggregate analytics.
    """
    if not stocks:
        return {"stocks": [], "analytics": {"n_stocks": 0}}

    # 1. Add relative ranking
    stocks = rank_screener_signals(stocks)

    # 2. Add risk-reward for each stock
    for stock in stocks:
        rr = compute_risk_reward(stock)
        stock["risk_reward"] = rr

    # 3. Market signal consensus
    market_consensus = None
    market_decomposition = None
    if market_signal and "components" in market_signal:
        market_consensus = compute_signal_consensus(market_signal["components"])
        market_decomposition = compute_conviction_decomposition(
            market_signal["components"]
        )

    # 4. Sector concentration
    concentration = detect_sector_concentration(stocks)

    # 5. Aggregate signal diversity metrics
    scores = [s.get("signal_score", 0) for s in stocks]
    actions = [s.get("signal_action", "Hold") for s in stocks]
    action_dist = dict(Counter(actions))

    analytics = {
        "n_stocks": len(stocks),
        "score_mean": round(float(np.mean(scores)), 3),
        "score_std": round(float(np.std(scores)), 3),
        "score_min": round(float(np.min(scores)), 3),
        "score_max": round(float(np.max(scores)), 3),
        "action_distribution": action_dist,
        "n_unique_actions": len(action_dist),
        "concentration": concentration,
    }

    if market_consensus:
        analytics["market_consensus"] = market_consensus
    if market_decomposition:
        analytics["market_decomposition"] = market_decomposition

    return {
        "stocks": stocks,
        "analytics": analytics,
    }
