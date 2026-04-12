"""
Aegis Finance — Composite Buy/Sell Signal Engine
===================================================

Generates market-level and per-stock buy/sell signals by compositing:
  - Crash probability (20%)
  - Market regime (16%)
  - Valuation / CAPE (11%)
  - Momentum (12%)
  - Mean reversion (9%)
  - External consensus (12%)
  - Macro risk (10%)
  - Drawdown from 52W high (10%)

Output: action, confidence, top 3 reasons.

Usage:
    from backend.services.signal_engine import get_market_signal, get_stock_signal
    from backend.services.signal_engine import compute_drawdown_pct
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from backend.config import config

logger = logging.getLogger(__name__)


def compute_drawdown_pct(sp500_series: pd.Series, lookback: int = 252) -> Optional[float]:
    """Compute current S&P 500 drawdown from its high over the lookback window.

    Args:
        sp500_series: S&P 500 price series (DatetimeIndex, no NaNs expected)
        lookback: Number of trading days for the high window (default 252 = ~1 year)

    Returns:
        Drawdown as a negative percentage (e.g., -12.5 means 12.5% below peak),
        or None if the series is too short to compute.
    """
    clean = sp500_series.dropna()
    if len(clean) < 2:
        return None
    window = min(lookback, len(clean))
    high = float(clean.iloc[-window:].max())
    current = float(clean.iloc[-1])
    if high <= 0 or np.isnan(high) or np.isnan(current):
        return None
    dd = (current / high - 1) * 100
    return min(dd, 0.0)  # clamp: positive would be a data error


# Signal weights — loaded from config.py for tunability
_DEFAULT_WEIGHTS = config.get("signal_weights", {
    "crash_prob": 0.20,
    "regime": 0.16,
    "valuation": 0.11,
    "momentum": 0.12,
    "mean_reversion": 0.09,
    "external": 0.12,
    "macro_risk": 0.10,
    "drawdown": 0.10,
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
    drawdown_pct: Optional[float] = None,
) -> dict:
    """Generate a composite market-level buy/sell signal.

    Returns:
        Dict with action, confidence, color, reasons, components
    """
    weights = _DEFAULT_WEIGHTS.copy()
    components = {}
    reasons = []

    # 1. Crash probability signal (-1 to +1)
    #    Centered on the historical base rate so that "normal" crash risk → neutral (0).
    #    Below base rate → bullish, above base rate → bearish.
    #    Base rate ~12%: 1% → +0.46, 12% → 0.0, 25% → -0.54, 50% → -1.0
    if crash_prob_3m is not None:
        base_rate = config.get("crash_base_rate_pct", 12.0) / 100.0
        scale = 1.0 / max(base_rate, 0.01)  # steepness of the mapping

        def _crash_to_signal(prob_pct: float) -> float:
            return float(np.clip((base_rate - prob_pct / 100.0) * scale * 0.5, -1, 0.6))

        crash_sig_3m = _crash_to_signal(crash_prob_3m)
        if crash_prob_12m is not None:
            crash_sig_12m = _crash_to_signal(crash_prob_12m)
            # 70% weight on near-term, 30% on structural
            crash_sig = 0.7 * crash_sig_3m + 0.3 * crash_sig_12m
        else:
            crash_sig = crash_sig_3m
        components["crash_prob"] = float(crash_sig)
        if crash_prob_3m > 40:
            reasons.append(f"High 3M crash probability ({crash_prob_3m:.0f}%)")
        elif crash_prob_3m < 15:
            reasons.append(f"Low crash risk ({crash_prob_3m:.0f}% 3M)")
        if crash_prob_12m is not None and crash_prob_12m > 50:
            reasons.append(f"Elevated 12M crash risk ({crash_prob_12m:.0f}%)")
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

    # Yield curve enhancement: inverted curve is a strong recession predictor
    if yield_curve is not None:
        if yield_curve < -0.5:
            val_sig -= 0.3
            reasons.append(f"Yield curve deeply inverted ({yield_curve:+.2f}%) — recession risk")
        elif yield_curve < 0:
            val_sig -= 0.15
            reasons.append(f"Yield curve inverted ({yield_curve:+.2f}%)")
        elif yield_curve > 1.5:
            val_sig += 0.1  # Steep positive curve = expansionary

    val_sig = float(np.clip(val_sig, -1, 1))
    components["valuation"] = val_sig

    if vix > 30:
        reasons.append(f"VIX at {vix:.0f} — extreme volatility")
    elif vix > 25:
        reasons.append(f"Elevated VIX ({vix:.0f}) — fear in market")

    # 4. Momentum signal
    # Combine 1M, 3M, and YTD momentum for multi-timeframe view.
    # YTD captures the longer trend that 1M/3M can miss in choppy markets.
    mom_1m = np.clip(sp500_1m_return / 10, -1, 1)  # ±10% → ±1
    mom_3m = np.clip(sp500_3m_return / 15, -1, 1)  # ±15% → ±1
    mom_ytd = np.clip(sp500_ytd_return / 20, -1, 1)  # ±20% → ±1
    mom_sig = 0.45 * mom_1m + 0.35 * mom_3m + 0.20 * mom_ytd
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

    # 7. Macro risk score — 9-factor composite (risk_scorer output)
    #    risk_score is [-4, +4] z-score; >2.0 = elevated stress
    #    Map to signal: low risk → bullish, high risk → bearish
    # Linear map: risk_score 0 → 0, +2 → -0.6, +4 → -1.0, -2 → +0.4
    macro_sig = float(np.clip(-risk_score * 0.25, -1.0, 0.5))
    components["macro_risk"] = macro_sig
    if risk_score > 2.0:
        reasons.append(f"Macro stress elevated (risk score {risk_score:.1f})")
    elif risk_score < -1.0:
        reasons.append(f"Low macro stress (risk score {risk_score:.1f})")

    # 8. Drawdown signal — current distance from 52-week high
    #    Drawdowns and returns convey different information:
    #      - Return: "where did we end up?" (direction)
    #      - Drawdown: "how far have we fallen from the top?" (pain)
    #    A market up 20% then down 10% shows +10% 3M return (bullish momentum)
    #    but is in a -10% drawdown (caution warranted).
    _dd_thresh = config.get("drawdown_thresholds", {})
    _dd_sigs = config.get("drawdown_signals", {})
    if drawdown_pct is not None:
        dd = min(drawdown_pct, 0.0)  # clamp: positive drawdown is a data error
        if dd > _dd_thresh.get("near_high", -2):
            dd_sig = _dd_sigs.get("near_high", 0.2)
        elif dd > _dd_thresh.get("pullback", -5):
            dd_sig = _dd_sigs.get("pullback", 0.0)
        elif dd > _dd_thresh.get("correction", -10):
            dd_sig = _dd_sigs.get("correction", -0.3)
        elif dd > _dd_thresh.get("bear", -20):
            dd_sig = _dd_sigs.get("bear", -0.7)
        else:
            dd_sig = _dd_sigs.get("crisis", -0.9)
        components["drawdown"] = float(dd_sig)

        if dd < _dd_thresh.get("bear", -20):
            reasons.append(f"Deep drawdown ({dd:.1f}%) from 52W high — crisis risk")
        elif dd < _dd_thresh.get("correction", -10):
            reasons.append(f"In correction ({dd:.1f}%) from 52W high")
        elif dd > _dd_thresh.get("near_high", -2):
            reasons.append("Near 52-week highs — trend confirmation")
    else:
        components["drawdown"] = 0.0
        weights["drawdown"] = 0  # exclude if unavailable

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


def adjust_crash_prob_for_stock(
    market_crash_prob: float,
    beta: float = 1.0,
    stock_vol: float = 0.20,
    drawdown_from_peak: float = 0.0,
) -> float:
    """Scale market-level crash probability by stock-specific risk factors.

    High-beta, high-volatility stocks in drawdown get higher crash probability;
    defensive low-beta stocks get lower. This creates meaningful differentiation
    across the stock universe instead of assigning every stock the same crash risk.

    Args:
        market_crash_prob: Market-level crash probability (0-1 scale)
        beta: Stock beta (1.0 = market, >1 = aggressive, <1 = defensive)
        stock_vol: Annualized volatility (decimal, e.g. 0.30 = 30%)
        drawdown_from_peak: Current drawdown as negative pct (e.g. -15.0 = 15% below peak)

    Returns:
        Adjusted crash probability for this stock (0-1 scale, clipped)
    """
    adj_cfg = config.get("stock_crash_adjustment", {})
    beta_sens = adj_cfg.get("beta_sensitivity", 0.6)
    vol_sens = adj_cfg.get("vol_sensitivity", 0.4)
    dd_sens = adj_cfg.get("drawdown_sensitivity", 0.3)
    vol_baseline = adj_cfg.get("vol_baseline", 0.20)
    min_mult = adj_cfg.get("min_multiplier", 0.4)
    max_mult = adj_cfg.get("max_multiplier", 2.5)

    # Beta factor: beta=1 → 1.0, beta=1.5 → 1.3, beta=0.5 → 0.7
    beta_factor = 1.0 + (beta - 1.0) * beta_sens

    # Vol factor: excess vol above baseline increases crash risk
    # stock_vol=0.30, baseline=0.20 → excess=0.10 → factor=1.04
    vol_excess = max(stock_vol - vol_baseline, 0.0)
    vol_factor = 1.0 + vol_excess * vol_sens / vol_baseline

    # Drawdown factor: stocks already in drawdown are more vulnerable
    # drawdown=-15% → factor=1.045, drawdown=0% → factor=1.0
    dd_factor = 1.0 + abs(min(drawdown_from_peak, 0.0)) / 100.0 * dd_sens

    multiplier = float(np.clip(beta_factor * vol_factor * dd_factor, min_mult, max_mult))
    adjusted = market_crash_prob * multiplier

    return float(np.clip(adjusted, 0.001, 0.95))


def get_stock_signal(
    market_signal: dict,
    beta: float = 1.0,
    analyst_target: Optional[float] = None,
    current_price: float = 0.0,
    sector_momentum: float = 0.0,
    pe_ratio: Optional[float] = None,
    forward_pe: Optional[float] = None,
    stock_vol: Optional[float] = None,
    drawdown_from_peak: Optional[float] = None,
    stock_momentum_1m: Optional[float] = None,
    stock_momentum_3m: Optional[float] = None,
) -> dict:
    """Generate a per-stock signal adjusted by beta and fundamentals.

    Args:
        market_signal: Output from get_market_signal()
        beta: Stock beta (>1 = amplifies market signal)
        analyst_target: Mean analyst price target
        current_price: Current stock price
        sector_momentum: Sector relative strength (pct)
        pe_ratio: Trailing P/E ratio
        forward_pe: Forward P/E ratio (consensus estimates)
        stock_vol: Annualized stock volatility (decimal, e.g. 0.30)
        drawdown_from_peak: Stock drawdown from 52w high (negative pct, e.g. -15.0)
        stock_momentum_1m: Stock's own 1-month return (pct, e.g. -5.0)
        stock_momentum_3m: Stock's own 3-month return (pct, e.g. 12.0)

    Returns:
        Dict with action, confidence, color, reasons
    """
    _sw = config.get("stock_signal_weights", {})
    analyst_w = _sw.get("analyst_target", 0.12)
    sector_w = _sw.get("sector_momentum", 0.012)
    pe_bonus = _sw.get("pe_bonus", 0.10)
    eg_scale = _sw.get("earnings_growth", 0.30)
    crash_risk_w = _sw.get("stock_crash_risk", 0.15)

    base_score = market_signal["composite_score"]
    reasons = list(market_signal["reasons"])

    # Beta adjustment: amplify market signal
    beta_adj = 1.0 + (beta - 1.0) * 0.3  # Dampen extreme betas
    stock_score = base_score * beta_adj

    # Analyst target signal — ADDITIVE (not convex combination)
    # Old: stock_score = 0.7*base + 0.3*analyst (analyst dominated the base)
    # New: stock_score += analyst_w * analyst_sig (analyst adjusts, doesn't replace)
    if analyst_target is not None and analyst_target > 0 and current_price > 0:
        upside = (analyst_target / current_price - 1) * 100
        analyst_sig = np.clip(upside / 30, -0.5, 0.5)  # ±30% → ±0.5
        stock_score += analyst_w * analyst_sig

        if upside > 15:
            reasons.insert(0, f"Analyst target implies +{upside:.0f}% upside")
        elif upside < -10:
            reasons.insert(0, f"Below analyst target by {abs(upside):.0f}%")

    # Sector momentum — graduated, proportional to magnitude
    if abs(sector_momentum) > 3:
        sector_adj = float(np.clip(sector_momentum * sector_w, -0.15, 0.15))
        stock_score += sector_adj
        if sector_momentum > 10:
            reasons.append(f"Strong sector momentum (+{sector_momentum:.0f}%)")
        elif sector_momentum < -10:
            reasons.append(f"Weak sector ({sector_momentum:.0f}%)")

    # PE ratio — graduated valuation signal
    if pe_ratio is not None and pe_ratio > 0:
        if pe_ratio > 50:
            stock_score -= pe_bonus
            reasons.append(f"High P/E ({pe_ratio:.0f}x) — premium valuation")
        elif pe_ratio < 10:
            stock_score += pe_bonus
            reasons.append(f"Low P/E ({pe_ratio:.0f}x) — value opportunity")

    # Forward PE earnings growth signal: when forward_pe << trailing_pe,
    # earnings are expected to grow significantly (bullish). When forward_pe >>
    # trailing_pe, earnings are expected to decline (bearish).
    # Example: NVDA PE=38.5, fwd_PE=17 → ratio=0.44 → strong growth signal +0.15
    #          JNJ  PE=22.8, fwd_PE=15.5 → ratio=0.68 → moderate growth +0.05
    if (
        forward_pe is not None
        and pe_ratio is not None
        and forward_pe > 0
        and pe_ratio > 0
    ):
        pe_compression = forward_pe / pe_ratio  # <1 = earnings growing, >1 = declining
        # Map: ratio 0.5 → +0.15, ratio 0.75 → +0.05, ratio 1.0 → 0, ratio 1.25 → -0.05
        earnings_growth_sig = float(np.clip((1.0 - pe_compression) * eg_scale, -0.15, 0.15))
        stock_score += earnings_growth_sig
        if pe_compression < 0.6:
            reasons.append(f"Strong earnings growth expected (fwd P/E {forward_pe:.0f}x vs {pe_ratio:.0f}x trailing)")
        elif pe_compression > 1.15:
            reasons.append(f"Earnings decline expected (fwd P/E {forward_pe:.0f}x vs {pe_ratio:.0f}x trailing)")

    # Per-stock crash risk adjustment: differentiate crash exposure by stock
    # characteristics. Market crash component is shared; this adds stock-specific
    # risk that the market signal misses (e.g., NVDA beta=1.7 vs JNJ beta=0.5).
    market_crash_3m_pct = market_signal.get("_crash_3m_pct")
    if market_crash_3m_pct is not None and stock_vol is not None:
        market_prob = market_crash_3m_pct / 100.0
        stock_prob = adjust_crash_prob_for_stock(
            market_prob, beta, stock_vol,
            drawdown_from_peak if drawdown_from_peak is not None else 0.0,
        )
        # Signal: deviation from market crash prob → stock-specific risk adjustment
        # Positive delta = stock is riskier than market → bearish adjustment
        # Negative delta = stock is safer than market → bullish adjustment
        crash_delta = stock_prob - market_prob
        base_rate = config.get("crash_base_rate_pct", 12.0) / 100.0
        crash_risk_sig = float(np.clip(-crash_delta / base_rate, -0.5, 0.5))
        stock_score += crash_risk_w * crash_risk_sig

        if stock_prob > market_prob * 1.5:
            reasons.append(f"Elevated stock-specific crash risk ({stock_prob*100:.0f}% vs {market_prob*100:.0f}% market)")
        elif stock_prob < market_prob * 0.7:
            reasons.append(f"Below-market crash risk ({stock_prob*100:.0f}% vs {market_prob*100:.0f}% market)")

    # Stock-specific drawdown signal: penalizes stocks far from their peak,
    # rewards stocks near highs. This is independent of the market-level drawdown
    # component — a stock can be in a -30% drawdown while the market is near ATH.
    dd_w = _sw.get("stock_drawdown", 0.25)
    if drawdown_from_peak is not None:
        dd = min(drawdown_from_peak, 0.0)
        # Graduated: near peak (+0.1), -5% (0), -15% (-0.4), -30% (-0.8), -50%+ (-1.0)
        if dd > -3:
            stock_dd_sig = 0.1
        elif dd > -8:
            stock_dd_sig = 0.0
        elif dd > -20:
            stock_dd_sig = dd / 25.0  # -8% → -0.32, -20% → -0.80
        else:
            stock_dd_sig = float(np.clip(dd / 30.0, -1.0, -0.6))
        stock_score += dd_w * stock_dd_sig

        if dd < -20:
            reasons.append(f"Stock in deep drawdown ({dd:.0f}% from peak)")
        elif dd < -10:
            reasons.append(f"Stock in correction ({dd:.0f}% from peak)")

    # Stock-specific momentum signal: the stock's own recent returns.
    # A stock down 15% in 3 months during a bull market is a red flag;
    # a stock up 20% shows individual strength beyond the market move.
    mom_w = _sw.get("stock_momentum", 0.20)
    if stock_momentum_1m is not None or stock_momentum_3m is not None:
        s_mom_1m = float(np.clip((stock_momentum_1m or 0.0) / 12, -1, 1))  # ±12% → ±1
        s_mom_3m = float(np.clip((stock_momentum_3m or 0.0) / 20, -1, 1))  # ±20% → ±1
        stock_mom_sig = 0.4 * s_mom_1m + 0.6 * s_mom_3m
        stock_score += mom_w * stock_mom_sig

        if (stock_momentum_3m or 0.0) < -15:
            reasons.append(f"Weak stock momentum ({stock_momentum_3m:.0f}% 3M)")
        elif (stock_momentum_3m or 0.0) > 15:
            reasons.append(f"Strong stock momentum (+{stock_momentum_3m:.0f}% 3M)")

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
