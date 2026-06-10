"""
Aegis Finance — Signal Engine Weight Optimization (OFFLINE RESEARCH TOOL)
============================================================================

Grid search over signal engine weights using backtest results.
Finds the weight combination that maximizes Sharpe ratio and hit rate.

Intentionally NOT exposed via the API — this is a heavy offline tool meant
to be run from a notebook / script to tune weights in config.py. Results
feed the hardcoded signal weights. See test_signal_optimizer.py for usage.

Usage:
    from backend.services.signal_optimizer import optimize_weights
    winners = optimize_weights("2020-01-01", "2025-06-01")
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
    from backend.services.signal_engine import _DEFAULT_WEIGHTS

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
        per_obs_sharpe = float(np.mean(arr) / max(np.std(arr), 1e-8))
        sharpe = float(per_obs_sharpe * np.sqrt(4))  # annualized (quarterly obs)
        hit_rate = buy_correct / buy_total * 100

        results.append({
            "weights": weights,
            "sharpe": round(sharpe, 4),
            "hit_rate": round(hit_rate, 1),
            "total_return": round(float((1 + arr).prod() - 1) * 100, 1),
            "buy_signals": buy_total,
            # Internal (stripped before return) — used for the overfitting guard.
            "_per_obs_sharpe": per_obs_sharpe,
            "_returns": arr.tolist(),
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

    # Overfitting guard: the winner was selected as best-of-N, so its Sharpe
    # is inflated by the search itself. Deflate it (DSR) and measure how often
    # the in-sample winner survives out-of-sample (PBO) before recommending.
    guard = _overfitting_guard(results)

    def _strip(r: dict | None) -> dict | None:
        if r is None:
            return None
        return {k: v for k, v in r.items() if not k.startswith("_")}

    return {
        "top_3": [_strip(r) for r in results[:3]],
        "current_weights": dict(_DEFAULT_WEIGHTS),
        "current_performance": _strip(current_result),
        "total_combos_tested": len(results),
        "overfitting_guard": guard,
        "recommendation": _make_recommendation(results[:3], current_result, guard),
    }


def _overfitting_guard(results: list[dict]) -> dict:
    """Deflated Sharpe + PBO for the grid-search winner.

    `results` must still carry the internal `_returns` / `_per_obs_sharpe`
    fields (this is called before they are stripped).
    """
    from engine.validation.overfitting import (
        deflated_sharpe_from_returns,
        probability_of_backtest_overfitting,
    )

    n_trials = len(results)
    if n_trials < 2:
        return {"available": False, "reason": "need ≥2 weight combinations"}

    per_obs = np.array([r["_per_obs_sharpe"] for r in results], dtype=float)
    sr_variance = float(per_obs.var(ddof=1)) if n_trials > 1 else 0.0

    best_returns = np.array(results[0]["_returns"], dtype=float)
    dsr = deflated_sharpe_from_returns(best_returns, n_trials=n_trials,
                                       sr_variance=sr_variance)

    # (T observations × N configs) matrix for the combinatorial PBO test.
    matrix = np.column_stack([r["_returns"] for r in results])
    pbo = probability_of_backtest_overfitting(matrix, n_partitions=8)

    survives = dsr["dsr"] >= 0.95 and (pbo.get("pbo") is None or pbo["pbo"] < 0.5)
    return {
        "available": True,
        "n_trials": n_trials,
        "winner_psr": dsr["psr"],
        "winner_dsr": dsr["dsr"],
        "expected_max_sharpe_h0": dsr["expected_max_sharpe_h0"],
        "pbo": pbo.get("pbo"),
        "pbo_interpretation": pbo.get("interpretation"),
        "survives_deflation": bool(survives),
        "note": (
            "Forward returns overlap (quarterly horizon), so PSR/DSR are "
            "approximate; the deflation direction is still informative."
        ),
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


def _make_recommendation(top3: list, current: dict | None,
                         guard: dict | None = None) -> str:
    """Generate recommendation, gated on the overfitting guard.

    Even a big in-sample improvement is NOT recommended unless the winner
    survives deflation (DSR ≥ 0.95) and the in-sample winner generally holds
    up out-of-sample (PBO < 0.5). This is what stops the grid search from
    banking a lucky configuration.
    """
    if not top3:
        return "Insufficient data for recommendation"

    best = top3[0]

    # Hard gate: a winner that doesn't survive deflation is treated as luck.
    if guard and guard.get("available") and not guard.get("survives_deflation"):
        return (
            f"NO CHANGE (likely overfit): best combo's edge does not survive "
            f"deflation: DSR={guard['winner_dsr']:.2f} (need >=0.95), "
            f"PBO={guard['pbo']} across {guard['n_trials']} trials. "
            f"Keep current weights; the apparent improvement is consistent "
            f"with selection bias."
        )

    if current is None:
        return f"Best combo: Sharpe={best['sharpe']}, hit rate={best['hit_rate']}%"

    sharpe_diff = best["sharpe"] - current["sharpe"]
    hit_diff = best["hit_rate"] - current["hit_rate"]

    if hit_diff > 5:
        deflation = ""
        if guard and guard.get("available"):
            deflation = (f" Survives deflation (DSR={guard['winner_dsr']:.2f}, "
                         f"PBO={guard['pbo']}).")
        return (
            f"RECOMMENDED CHANGE: New weights improve hit rate by {hit_diff:.1f}% "
            f"(Sharpe: {current['sharpe']:.3f} -> {best['sharpe']:.3f}).{deflation} "
            f"New weights: {best['weights']}"
        )
    else:
        return (
            f"Current weights are near-optimal (hit rate diff: {hit_diff:.1f}%, "
            f"Sharpe diff: {sharpe_diff:.3f}). No change recommended."
        )
