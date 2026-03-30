"""
Aegis Finance — Signal Engine Weight Optimization
====================================================

Grid search over signal engine weights using backtest results.
Finds the weight combination that maximizes Sharpe ratio and hit rate.

Usage:
    from backend.services.signal_optimizer import optimize_weights
"""

import logging
from itertools import product

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def optimize_weights(
    start_date: str = "2020-01-01",
    end_date: str = "2025-06-01",
) -> dict:
    """Run grid search over signal engine weights to find optimal combination.

    Tests weight combinations that sum to 1.0 and evaluates each via backtest.

    Returns:
        Dict with top 3 combinations and comparison to current weights.
    """
    import yfinance as yf
    from backend.services.signal_engine import get_market_signal, _DEFAULT_WEIGHTS

    # Download all data once
    buffer_end = (pd.Timestamp(end_date) + pd.DateOffset(months=14)).strftime("%Y-%m-%d")
    data_start = (pd.Timestamp(start_date) - pd.DateOffset(years=2)).strftime("%Y-%m-%d")

    sp500 = yf.download("^GSPC", start=data_start, end=buffer_end, progress=False)["Close"]
    vix = yf.download("^VIX", start=data_start, end=buffer_end, progress=False)["Close"]

    if isinstance(sp500, pd.DataFrame):
        sp500 = sp500.squeeze()
    if isinstance(vix, pd.DataFrame):
        vix = vix.squeeze()

    if sp500.empty:
        return {"error": "Could not download data"}

    # Generate monthly evaluation points
    eval_dates = pd.date_range(start=start_date, end=end_date, freq="MS")

    # Pre-compute inputs for each date
    date_inputs = []
    for eval_date in eval_dates:
        mask = sp500.index <= eval_date
        if mask.sum() < 63:
            continue
        actual_date = sp500.index[mask][-1]
        sp_slice = sp500.loc[:actual_date]
        vix_slice = vix.loc[:actual_date] if not vix.empty else pd.Series(dtype=float)

        current_vix = float(vix_slice.iloc[-1]) if len(vix_slice) > 0 else 20.0
        sp_1m = float(sp_slice.iloc[-1] / sp_slice.iloc[-22] - 1) * 100 if len(sp_slice) > 22 else 0.0
        sp_3m = float(sp_slice.iloc[-1] / sp_slice.iloc[-63] - 1) * 100 if len(sp_slice) > 63 else 0.0

        sp_252d = float(sp_slice.iloc[-1] / sp_slice.iloc[-min(252, len(sp_slice)-1)] - 1) if len(sp_slice) > 1 else 0.0
        if sp_252d > 0.10:
            regime = "Bull"
        elif sp_252d < -0.10:
            regime = "Bear"
        elif current_vix > 25:
            regime = "Volatile"
        else:
            regime = "Neutral"

        if regime == "Bull" and (sp_1m / 100 < -0.05 or sp_3m / 100 < -0.08):
            regime = "Neutral"

        # Forward 3m return
        fwd_3m_date = actual_date + pd.DateOffset(months=3)
        fwd_mask = sp500.index >= fwd_3m_date
        fwd_3m = None
        if fwd_mask.any():
            fwd_3m = (float(sp500.loc[sp500.index[fwd_mask][0]]) / float(sp_slice.iloc[-1]) - 1)

        date_inputs.append({
            "regime": regime,
            "risk_score": current_vix / 30,
            "sp500_1m_return": sp_1m,
            "sp500_3m_return": sp_3m,
            "vix": current_vix,
            "fwd_3m": fwd_3m,
        })

    if not date_inputs:
        return {"error": "No valid evaluation dates"}

    # Weight grid (coarser to keep runtime reasonable)
    crash_w = [0.15, 0.20, 0.25, 0.30]
    regime_w = [0.15, 0.20, 0.25]
    valuation_w = [0.10, 0.15, 0.20]
    momentum_w = [0.10, 0.15, 0.20]
    mean_rev_w = [0.05, 0.10, 0.15]
    external_w = [0.10, 0.15, 0.20]

    combos = []
    for cw, rw, vw, mw, mrw, ew in product(crash_w, regime_w, valuation_w, momentum_w, mean_rev_w, external_w):
        total = cw + rw + vw + mw + mrw + ew
        if abs(total - 1.0) < 0.001:
            combos.append({
                "crash_prob": cw, "regime": rw, "valuation": vw,
                "momentum": mw, "mean_reversion": mrw, "external": ew,
            })

    logger.info("Testing %d weight combinations over %d months", len(combos), len(date_inputs))

    results = []
    for weights in combos:
        strategy_returns = []
        buy_correct = 0
        buy_total = 0

        for inp in date_inputs:
            if inp["fwd_3m"] is None:
                continue

            # Compute signal with custom weights
            signal = _compute_signal_with_weights(inp, weights)
            action = signal["action"]

            if action in ("Buy", "Strong Buy"):
                strategy_returns.append(inp["fwd_3m"])
                buy_total += 1
                if inp["fwd_3m"] > 0:
                    buy_correct += 1
            elif action in ("Sell", "Strong Sell"):
                strategy_returns.append(0.0)
            else:
                strategy_returns.append(inp["fwd_3m"] * 0.5)

        if not strategy_returns or buy_total == 0:
            continue

        arr = np.array(strategy_returns)
        sharpe = float(np.mean(arr) / max(np.std(arr), 1e-8) * np.sqrt(4))
        hit_rate = buy_correct / buy_total * 100

        results.append({
            "weights": weights,
            "sharpe": round(sharpe, 4),
            "hit_rate": round(hit_rate, 1),
            "total_return": round(float((1 + arr).prod() - 1) * 100, 1),
            "buy_signals": buy_total,
        })

    if not results:
        return {"error": "No valid weight combinations found"}

    # Sort by Sharpe
    results.sort(key=lambda x: x["sharpe"], reverse=True)

    # Current weights performance
    current_result = None
    for r in results:
        if r["weights"] == dict(_DEFAULT_WEIGHTS):
            current_result = r
            break

    return {
        "top_3": results[:3],
        "current_weights": dict(_DEFAULT_WEIGHTS),
        "current_performance": current_result,
        "total_combos_tested": len(results),
        "recommendation": _make_recommendation(results[:3], current_result),
    }


def _compute_signal_with_weights(inputs: dict, weights: dict) -> dict:
    """Compute signal score with custom weights (simplified, no numpy clipping)."""
    components = {}

    # Crash prob (not available in backtest, use VIX proxy)
    vix = inputs["vix"]
    crash_sig = max(-1, min(1, 0.8 - (vix / 30) * 0.8))
    components["crash_prob"] = crash_sig

    # Regime
    regime_scores = {"Bull": 0.7, "Neutral": 0.0, "Bear": -0.6, "Volatile": -0.4}
    components["regime"] = regime_scores.get(inputs["regime"], 0.0)

    # Valuation (VIX proxy)
    if vix < 15:
        components["valuation"] = -0.2
    elif vix < 20:
        components["valuation"] = 0.1
    elif vix < 25:
        components["valuation"] = 0.3
    elif vix < 30:
        components["valuation"] = 0.15
    else:
        components["valuation"] = -0.3

    # Momentum
    mom_1m = max(-1, min(1, inputs["sp500_1m_return"] / 10))
    mom_3m = max(-1, min(1, inputs["sp500_3m_return"] / 15))
    components["momentum"] = 0.6 * mom_1m + 0.4 * mom_3m

    # Mean reversion
    if inputs["sp500_3m_return"] < -8 and vix < 35:
        components["mean_reversion"] = 0.4
    elif inputs["sp500_3m_return"] > 15:
        components["mean_reversion"] = -0.3
    else:
        components["mean_reversion"] = 0.0

    # External (not available, neutral)
    components["external"] = 0.0

    # Composite
    total_w = sum(weights[k] for k in components if k in weights)
    if total_w > 0:
        composite = sum(components[k] * weights.get(k, 0) for k in components) / total_w
    else:
        composite = 0.0

    composite = max(-1, min(1, composite))

    # Action
    thresholds = [(0.45, "Strong Buy"), (0.15, "Buy"), (-0.15, "Hold"), (-0.45, "Sell"), (-1.0, "Strong Sell")]
    action = "Hold"
    for threshold, act in thresholds:
        if composite >= threshold:
            action = act
            break

    return {"action": action, "composite_score": composite}


def _make_recommendation(top3: list, current: dict | None) -> str:
    """Generate recommendation based on optimization results."""
    if not top3:
        return "Insufficient data for recommendation"

    best = top3[0]
    if current is None:
        return f"Best combo: Sharpe={best['sharpe']}, hit rate={best['hit_rate']}%"

    sharpe_diff = best["sharpe"] - current["sharpe"]
    hit_diff = best["hit_rate"] - current["hit_rate"]

    if hit_diff > 5:
        return (
            f"RECOMMENDED CHANGE: New weights improve hit rate by {hit_diff:.1f}% "
            f"(Sharpe: {current['sharpe']:.3f} -> {best['sharpe']:.3f}). "
            f"New weights: {best['weights']}"
        )
    else:
        return (
            f"Current weights are near-optimal (hit rate diff: {hit_diff:.1f}%, "
            f"Sharpe diff: {sharpe_diff:.3f}). No change recommended."
        )
