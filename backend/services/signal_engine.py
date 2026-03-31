"""
Aegis Finance — Composite Buy/Sell Signal Engine
===================================================

Generates market-level and per-stock buy/sell signals by compositing:
  - Crash probability (25%)
  - Market regime (20%)
  - Valuation / CAPE (15%)
  - Momentum (15%)
  - Mean reversion (10%)
  - External consensus (15%)

Output: action, confidence, top 3 reasons.

Usage:
    from backend.services.signal_engine import get_market_signal, get_stock_signal
"""

import logging
from typing import Optional

import numpy as np

from backend.config import config

logger = logging.getLogger(__name__)

# Signal weights — loaded from config.py for tunability
_DEFAULT_WEIGHTS = config.get("signal_weights", {
    "crash_prob": 0.25,
    "regime": 0.20,
    "valuation": 0.15,
    "momentum": 0.15,
    "mean_reversion": 0.10,
    "external": 0.15,
})

# Action thresholds from config (signal: -1 = very bearish, +1 = very bullish)
_sig_thresholds = config.get("signal_thresholds", {
    "strong_buy": 0.45, "buy": 0.15, "sell": -0.15, "strong_sell": -0.45,
})
_ACTION_THRESHOLDS = [
    (_sig_thresholds["strong_buy"], "Strong Buy"),
    (_sig_thresholds["buy"], "Buy"),
    (_sig_thresholds["sell"], "Hold"),
    (_sig_thresholds["strong_sell"], "Sell"),
    (-1.0, "Strong Sell"),
]

_ACTION_COLORS = {
    "Strong Buy": "green",
    "Buy": "green",
    "Hold": "amber",
    "Sell": "red",
    "Strong Sell": "red",
}


def get_market_signal(
    crash_prob_3m: Optional[float] = None,
    crash_prob_12m: Optional[float] = None,
    regime: str = "Neutral",
    risk_score: float = 0.0,
    sp500_1m_return: float = 0.0,
    sp500_3m_return: float = 0.0,
    sp500_ytd_return: float = 0.0,
    vix: float = 20.0,
    yield_curve: Optional[float] = None,
    external_consensus: Optional[str] = None,
) -> dict:
    """Generate a composite market-level buy/sell signal.

    Returns:
        Dict with action, confidence, color, reasons, components
    """
    weights = _DEFAULT_WEIGHTS.copy()
    components = {}
    reasons = []

    # 1. Crash probability signal (-1 to +1)
    if crash_prob_3m is not None:
        # Lower crash prob = more bullish
        # 5% → +0.8, 20% → 0, 50% → -0.8
        crash_sig = np.clip(0.8 - (crash_prob_3m / 100) * 2.0, -1, 1)
        components["crash_prob"] = crash_sig
        if crash_prob_3m > 40:
            reasons.append(f"High 3M crash probability ({crash_prob_3m:.0f}%)")
        elif crash_prob_3m < 15:
            reasons.append(f"Low crash risk ({crash_prob_3m:.0f}% 3M)")
    else:
        components["crash_prob"] = 0.0
        weights["crash_prob"] = 0  # exclude if unavailable

    # 2. Regime signal
    regime_scores = {"Bull": 0.7, "Neutral": 0.0, "Bear": -0.6, "Volatile": -0.4, "Unknown": 0.0}
    reg_sig = regime_scores.get(regime, 0.0)
    components["regime"] = reg_sig
    if regime in ("Bear", "Volatile"):
        reasons.append(f"Market regime: {regime}")
    elif regime == "Bull":
        reasons.append("Bullish market regime")

    # 3. Valuation signal (VIX as proxy for fear/opportunity)
    # High VIX = potential opportunity (contrarian), very high = danger
    if vix < 15:
        val_sig = -0.2  # complacency
    elif vix < 20:
        val_sig = 0.1
    elif vix < 25:
        val_sig = 0.3  # moderate fear = opportunity
    elif vix < 30:
        val_sig = 0.15  # high fear, mixed
    else:
        val_sig = -0.3  # extreme fear = risk
    components["valuation"] = val_sig

    if vix > 30:
        reasons.append(f"VIX at {vix:.0f} — extreme volatility")
    elif vix > 25:
        reasons.append(f"Elevated VIX ({vix:.0f}) — fear in market")

    # 4. Momentum signal
    # Combine 1M and 3M momentum
    mom_1m = np.clip(sp500_1m_return / 10, -1, 1)  # ±10% → ±1
    mom_3m = np.clip(sp500_3m_return / 15, -1, 1)  # ±15% → ±1
    mom_sig = 0.6 * mom_1m + 0.4 * mom_3m
    components["momentum"] = float(mom_sig)

    if sp500_1m_return < -7:
        reasons.append(f"Sharp 1M decline ({sp500_1m_return:.1f}%) — potential bounce")
        # Mean reversion opportunity if not in crisis
        if vix < 35:
            components["momentum"] = float(mom_sig * 0.5)  # dampen bearish momentum if bounce likely

    # 5. Mean reversion signal
    # After big drops, markets tend to recover (if not in crisis)
    if sp500_3m_return < -8 and vix < 35:
        mr_sig = 0.4 + min(0.3, abs(sp500_3m_return + 8) * 0.05)  # graduated, stronger for bigger drops
        reasons.append(f"3M return {sp500_3m_return:.1f}% — oversold, potential recovery")
    elif sp500_3m_return > 15:
        mr_sig = -0.3  # overbought
    else:
        mr_sig = 0.0
    components["mean_reversion"] = mr_sig

    # 6. External consensus
    ext_scores = {"BULLISH": 0.4, "MIXED": 0.0, "BEARISH": -0.4}
    ext_sig = ext_scores.get(external_consensus or "MIXED", 0.0)
    components["external"] = ext_sig
    if external_consensus and external_consensus != "MIXED":
        reasons.append(f"External consensus: {external_consensus}")

    # Composite signal
    total_w = sum(weights[k] for k in components if k in weights)
    if total_w > 0:
        composite = sum(components[k] * weights.get(k, 0) for k in components) / total_w
    else:
        composite = 0.0

    composite = float(np.clip(composite, -1, 1))

    # Determine action
    action = "Hold"
    for threshold, act in _ACTION_THRESHOLDS:
        if composite >= threshold:
            action = act
            break

    # Confidence: distance from nearest threshold → 0-100%
    confidence = int(min(abs(composite) * 100, 100))

    # Sort reasons by relevance (keep top 3)
    reasons = reasons[:3]
    if not reasons:
        reasons = ["Mixed signals — no strong conviction"]

    return {
        "action": action,
        "confidence": confidence,
        "color": _ACTION_COLORS.get(action, "amber"),
        "composite_score": round(composite, 3),
        "reasons": reasons,
        "components": {k: round(v, 3) for k, v in components.items()},
    }


def get_stock_signal(
    market_signal: dict,
    beta: float = 1.0,
    analyst_target: Optional[float] = None,
    current_price: float = 0.0,
    sector_momentum: float = 0.0,
    pe_ratio: Optional[float] = None,
) -> dict:
    """Generate a per-stock signal adjusted by beta and fundamentals.

    Args:
        market_signal: Output from get_market_signal()
        beta: Stock beta (>1 = amplifies market signal)
        analyst_target: Mean analyst price target
        current_price: Current stock price
        sector_momentum: Sector relative strength (pct)
        pe_ratio: Trailing P/E ratio

    Returns:
        Dict with action, confidence, color, reasons
    """
    base_score = market_signal["composite_score"]
    reasons = list(market_signal["reasons"])

    # Beta adjustment: amplify market signal
    beta_adj = 1.0 + (beta - 1.0) * 0.3  # Dampen extreme betas
    stock_score = base_score * beta_adj

    # Analyst target signal
    if analyst_target is not None and analyst_target > 0 and current_price > 0:
        upside = (analyst_target / current_price - 1) * 100
        analyst_sig = np.clip(upside / 30, -0.5, 0.5)  # ±30% → ±0.5
        stock_score = 0.7 * stock_score + 0.3 * analyst_sig

        if upside > 15:
            reasons.insert(0, f"Analyst target implies +{upside:.0f}% upside")
        elif upside < -10:
            reasons.insert(0, f"Below analyst target by {abs(upside):.0f}%")

    # Sector momentum
    if abs(sector_momentum) > 5:
        sector_adj = np.clip(sector_momentum / 20, -0.2, 0.2)
        stock_score += sector_adj
        if sector_momentum > 10:
            reasons.append(f"Strong sector momentum (+{sector_momentum:.0f}%)")
        elif sector_momentum < -10:
            reasons.append(f"Weak sector ({sector_momentum:.0f}%)")

    # PE ratio — flag extremes
    if pe_ratio is not None:
        if pe_ratio > 50:
            stock_score -= 0.1
            reasons.append(f"High P/E ({pe_ratio:.0f}x) — premium valuation")
        elif pe_ratio < 10 and pe_ratio > 0:
            stock_score += 0.1
            reasons.append(f"Low P/E ({pe_ratio:.0f}x) — value opportunity")

    stock_score = float(np.clip(stock_score, -1, 1))

    # Action
    action = "Hold"
    for threshold, act in _ACTION_THRESHOLDS:
        if stock_score >= threshold:
            action = act
            break

    confidence = int(min(abs(stock_score) * 100, 100))

    return {
        "action": action,
        "confidence": confidence,
        "color": _ACTION_COLORS.get(action, "amber"),
        "composite_score": round(stock_score, 3),
        "reasons": reasons[:3],
        "beta_adj": round(beta_adj, 2),
    }
