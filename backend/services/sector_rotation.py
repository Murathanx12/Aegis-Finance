"""
Aegis Finance — Sector Rotation Model
========================================

Tracks sector relative strength across multiple timeframes to detect
rotation patterns. Key questions it answers:
  - Which sectors are gaining momentum? (leaders vs laggards)
  - Is money rotating from growth → value or vice versa?
  - What's the breadth of the rally? (narrow tech vs broad market)

Methodology:
  1. Compute returns for each sector ETF across 1w, 1m, 3m, 6m, 12m
  2. Rank sectors by composite relative strength
  3. Detect rotation patterns (improving/declining/stable)
  4. Classify market breadth (narrow/moderate/broad)
  5. Map to business cycle phases (early/mid/late/recession)

References:
  - Sam Stovall's sector rotation model
  - Fidelity's business cycle framework
  - Relative Rotation Graphs (RRG) methodology

Usage:
    from backend.services.sector_rotation import compute_sector_rotation
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

from backend.config import config

logger = logging.getLogger(__name__)


# Business cycle sector preferences (Sam Stovall framework)
_CYCLE_LEADERS = {
    "early_recovery": ["Consumer Disc.", "Financials", "Technology", "Industrials"],
    "mid_cycle": ["Technology", "Industrials", "Materials", "Energy"],
    "late_cycle": ["Energy", "Materials", "Healthcare", "Consumer Staples"],
    "recession": ["Consumer Staples", "Healthcare", "Utilities", "Real Estate"],
}


def compute_sector_rotation(lookback_days: int = 504) -> dict:
    """Compute sector rotation analysis across multiple timeframes.

    Returns:
        Dict with:
        - sectors: list of sector data with multi-timeframe returns
        - rotation_signal: overall rotation direction
        - breadth: market breadth assessment
        - cycle_phase: estimated business cycle phase
        - leaders/laggards: top/bottom sectors
    """
    sector_etfs = config["data"]["sectors"]

    # Fetch all sector ETF data in one batch
    tickers = list(sector_etfs.values())
    ticker_to_name = {v: k for k, v in sector_etfs.items()}

    try:
        data = yf.download(tickers, period="2y", progress=False)
    except Exception as e:
        logger.error("Sector rotation data fetch failed: %s", e)
        return {"error": str(e), "sectors": []}

    if data is None or data.empty:
        return {"error": "No sector data available", "sectors": []}

    # Get close prices
    if len(tickers) == 1:
        close = data["Close"].to_frame(tickers[0])
    else:
        close = data["Close"]

    # Also get SPY for relative strength
    try:
        spy = yf.Ticker("SPY").history(period="2y")
        spy_close = spy["Close"] if spy is not None else None
    except Exception:
        spy_close = None

    sectors = []
    for etf_ticker, sector_name in ticker_to_name.items():
        if etf_ticker not in close.columns:
            continue

        prices = close[etf_ticker].dropna()
        if len(prices) < 30:
            continue

        # Multi-timeframe returns
        returns = {}
        for label, days in [("1w", 5), ("1m", 21), ("3m", 63), ("6m", 126), ("12m", 252)]:
            if len(prices) > days:
                ret = float((prices.iloc[-1] / prices.iloc[-days] - 1) * 100)
                returns[label] = round(ret, 2)
            else:
                returns[label] = None

        # Relative strength vs SPY
        rel_strength = {}
        if spy_close is not None and len(spy_close) > 0:
            for label, days in [("1m", 21), ("3m", 63), ("6m", 126)]:
                if len(prices) > days and len(spy_close) > days:
                    sector_ret = float(prices.iloc[-1] / prices.iloc[-days] - 1)
                    spy_ret = float(spy_close.iloc[-1] / spy_close.iloc[-days] - 1)
                    rel_strength[label] = round((sector_ret - spy_ret) * 100, 2)

        # Composite score (weighted average of timeframe returns)
        score_components = []
        weights_tf = {"1w": 0.05, "1m": 0.15, "3m": 0.30, "6m": 0.30, "12m": 0.20}
        for tf, w in weights_tf.items():
            if returns.get(tf) is not None:
                score_components.append(returns[tf] * w)
        composite = sum(score_components) if score_components else 0.0

        # Momentum direction (improving/declining/stable)
        direction = "stable"
        r1m = returns.get("1m")
        r3m = returns.get("3m")
        if r1m is not None and r3m is not None:
            if r3m != 0:
                ratio = r1m / (r3m / 3) if r3m != 0 else 1.0
            else:
                ratio = 1.0
            if ratio > 1.3:
                direction = "accelerating"
            elif ratio > 1.05:
                direction = "improving"
            elif ratio < 0.7:
                direction = "decelerating"
            elif ratio < 0.95:
                direction = "declining"

        # 20-day volatility
        daily_returns = prices.pct_change().dropna()
        vol_20d = float(daily_returns.iloc[-20:].std() * np.sqrt(252) * 100) if len(daily_returns) >= 20 else None

        sectors.append({
            "sector": sector_name,
            "etf": etf_ticker,
            "returns": returns,
            "relative_strength": rel_strength,
            "composite_score": round(composite, 2),
            "direction": direction,
            "volatility_20d": round(vol_20d, 1) if vol_20d else None,
        })

    # Sort by composite score
    sectors.sort(key=lambda x: x["composite_score"], reverse=True)

    # Assign ranks
    for i, s in enumerate(sectors):
        s["rank"] = i + 1

    # Market breadth
    n_positive_3m = sum(1 for s in sectors if (s["returns"].get("3m") or 0) > 0)
    n_total = len(sectors)
    breadth_pct = n_positive_3m / n_total if n_total > 0 else 0

    if breadth_pct >= 0.80:
        breadth = "broad_rally"
        breadth_desc = f"{n_positive_3m}/{n_total} sectors positive — broad-based rally"
    elif breadth_pct >= 0.55:
        breadth = "moderate"
        breadth_desc = f"{n_positive_3m}/{n_total} sectors positive — healthy but selective"
    elif breadth_pct >= 0.35:
        breadth = "narrow"
        breadth_desc = f"{n_positive_3m}/{n_total} sectors positive — narrow leadership"
    else:
        breadth = "broad_decline"
        breadth_desc = f"Only {n_positive_3m}/{n_total} sectors positive — broad weakness"

    # Business cycle phase estimation
    leaders = [s["sector"] for s in sectors[:3]]
    cycle_phase = _estimate_cycle_phase(leaders)

    # Rotation signal
    rotation_signal = _compute_rotation_signal(sectors)

    return {
        "sectors": sectors,
        "leaders": [s["sector"] for s in sectors[:3]],
        "laggards": [s["sector"] for s in sectors[-3:]],
        "breadth": {
            "status": breadth,
            "description": breadth_desc,
            "positive_sectors": n_positive_3m,
            "total_sectors": n_total,
            "pct_positive": round(breadth_pct * 100, 0),
        },
        "cycle_phase": cycle_phase,
        "rotation_signal": rotation_signal,
        "n_sectors": n_total,
    }


def _estimate_cycle_phase(leaders: list[str]) -> dict:
    """Estimate business cycle phase from sector leadership."""
    phase_scores = {}
    for phase, expected_leaders in _CYCLE_LEADERS.items():
        overlap = len(set(leaders) & set(expected_leaders))
        phase_scores[phase] = overlap

    best_phase = max(phase_scores, key=phase_scores.get)
    confidence = phase_scores[best_phase] / len(leaders) if leaders else 0

    descriptions = {
        "early_recovery": "Economy emerging from recession — cyclicals leading",
        "mid_cycle": "Sustained growth — technology and industrials leading",
        "late_cycle": "Growth decelerating — commodities and defensives gaining",
        "recession": "Economic contraction — defensive sectors outperforming",
    }

    return {
        "phase": best_phase,
        "confidence": round(confidence, 2),
        "description": descriptions.get(best_phase, ""),
        "scores": phase_scores,
    }


def _compute_rotation_signal(sectors: list[dict]) -> dict:
    """Summarize overall rotation direction."""
    n_accelerating = sum(1 for s in sectors if s["direction"] in ("accelerating", "improving"))
    n_decelerating = sum(1 for s in sectors if s["direction"] in ("decelerating", "declining"))
    n_total = len(sectors)

    if n_accelerating > n_total * 0.6:
        signal = "risk_on"
        description = "Broad momentum improvement — risk-on rotation"
    elif n_decelerating > n_total * 0.6:
        signal = "risk_off"
        description = "Broad momentum deterioration — risk-off rotation"
    elif n_accelerating > n_decelerating:
        signal = "mildly_risk_on"
        description = "Slight momentum improvement across sectors"
    elif n_decelerating > n_accelerating:
        signal = "mildly_risk_off"
        description = "Slight momentum deterioration across sectors"
    else:
        signal = "neutral"
        description = "No clear rotation direction"

    return {
        "signal": signal,
        "description": description,
        "accelerating": n_accelerating,
        "decelerating": n_decelerating,
        "stable": n_total - n_accelerating - n_decelerating,
    }
