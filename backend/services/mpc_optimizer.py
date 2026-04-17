"""
Aegis Finance — Convex Portfolio Optimizer (Cvxportfolio-lite)
==================================================================

A single-period mean-variance optimizer that explicitly models:

  - Quadratic risk penalty (covariance-based)
  - L1 transaction costs (proportional spread / commission)
  - L2 holding penalty (quadratic concentration penalty)
  - Absolute weight bounds (long-only by default)
  - Tracking-error constraint vs a benchmark
  - Sector-exposure caps

And a rolling-horizon multi-step wrapper that re-solves each period, so
the MPC behaviour is visible even though we don't solve the joint
multi-period problem (which needs a return *process*, not a single
vector of expected returns — outside the scope of a one-shot API call).

Dependencies: cvxpy (already pulled in by riskfolio-lib).

Usage:
    from backend.services.mpc_optimizer import optimize_single_period

    result = optimize_single_period(
        expected_returns=mu,       # pd.Series, annualised
        cov_matrix=Sigma,          # pd.DataFrame, annualised
        current_weights={"AAPL": 0.6, "MSFT": 0.4},
        gamma=3.0,                 # risk aversion
        transaction_cost_bps=5,    # round-trip cost in basis points
        max_weight=0.35,
        tracking_error_limit=0.05, # annualised, vs benchmark_weights
        benchmark_weights={...},
    )
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


try:
    import cvxpy as cp

    _HAS_CVXPY = True
except ImportError:
    _HAS_CVXPY = False


# ── Single-period solver ─────────────────────────────────────────────────────


def optimize_single_period(
    expected_returns: pd.Series,
    cov_matrix: pd.DataFrame,
    current_weights: Optional[dict[str, float]] = None,
    *,
    gamma: float = 3.0,
    transaction_cost_bps: float = 5.0,
    holding_penalty: float = 0.0,
    max_weight: float = 0.35,
    min_weight: float = 0.0,
    tracking_error_limit: Optional[float] = None,
    benchmark_weights: Optional[dict[str, float]] = None,
    sector_map: Optional[dict[str, str]] = None,
    sector_caps: Optional[dict[str, float]] = None,
    allow_shorts: bool = False,
) -> dict:
    """Single-period mean-variance optimization with TX costs + constraints.

    Returns a dict with:
      - weights: {ticker: weight}
      - trades: {ticker: delta} — change vs current_weights
      - metrics: expected_return, volatility, sharpe, turnover, tx_cost
      - tracking_error: if benchmark provided
      - sector_exposures: if sector_map provided
      - status: cvxpy solver status
    """
    if not _HAS_CVXPY:
        return {"error": "cvxpy not installed"}

    tickers = list(expected_returns.index)
    n = len(tickers)
    if n == 0:
        return {"error": "no assets"}

    mu = expected_returns.reindex(tickers).to_numpy()
    Sigma = cov_matrix.reindex(index=tickers, columns=tickers).to_numpy()
    Sigma = _psd_wrap(Sigma)

    w_prev = np.array(
        [(current_weights or {}).get(t, 0.0) for t in tickers], dtype=float
    )
    # If no current weights provided, start from equal weight so the TX-cost
    # term still penalises huge concentration swings in the first step.
    if w_prev.sum() == 0:
        w_prev = np.full(n, 1.0 / n)

    # Decision variable
    w = cp.Variable(n)
    delta = w - w_prev

    # Objective pieces
    expected_ret = mu @ w
    risk = cp.quad_form(w, cp.psd_wrap(Sigma))
    tx_cost = (transaction_cost_bps / 10000.0) * cp.norm(delta, 1)
    holding_cost = holding_penalty * cp.sum_squares(w) if holding_penalty > 0 else 0

    objective = cp.Maximize(expected_ret - gamma * risk - tx_cost - holding_cost)

    constraints = [cp.sum(w) == 1.0]

    if not allow_shorts:
        constraints.append(w >= max(0.0, min_weight))
    else:
        constraints.append(w >= min_weight)
    constraints.append(w <= max_weight)

    # Tracking-error constraint: Var(w - w_b)ᵀΣ(w - w_b) ≤ TE²
    if tracking_error_limit and benchmark_weights:
        w_b = np.array([(benchmark_weights or {}).get(t, 0.0) for t in tickers])
        if abs(w_b.sum()) > 0:
            w_b = w_b / w_b.sum()  # renormalise if benchmark doesn't sum to 1
        te_sq = tracking_error_limit ** 2
        constraints.append(
            cp.quad_form(w - w_b, cp.psd_wrap(Sigma)) <= te_sq
        )

    # Sector caps: sum of weights in each sector ≤ cap
    if sector_map and sector_caps:
        for sector, cap in sector_caps.items():
            indicator = np.array(
                [1.0 if sector_map.get(t) == sector else 0.0 for t in tickers]
            )
            if indicator.sum() > 0:
                constraints.append(indicator @ w <= cap)

    prob = cp.Problem(objective, constraints)
    try:
        prob.solve(solver=cp.CLARABEL)
    except Exception as e:
        logger.warning("CLARABEL failed, falling back to SCS: %s", e)
        try:
            prob.solve(solver=cp.SCS)
        except Exception as e2:
            return {"error": f"solver failed: {e2}", "status": "failed"}

    if w.value is None:
        return {"error": "optimizer did not converge", "status": prob.status}

    w_opt = np.asarray(w.value).flatten()
    # Clip tiny negatives from numerical noise
    w_opt = np.where((w_opt < 0) & (w_opt > -1e-6), 0.0, w_opt)
    # Renormalise so sum is exactly 1 (tiny floating-point drift)
    if w_opt.sum() > 0:
        w_opt = w_opt / w_opt.sum()

    trades = w_opt - w_prev
    turnover = float(np.abs(trades).sum())
    realised_tx_cost = turnover * (transaction_cost_bps / 10000.0)
    expected_return = float(mu @ w_opt)
    vol = float(np.sqrt(max(w_opt @ Sigma @ w_opt, 0.0)))
    sharpe = expected_return / vol if vol > 0 else None

    result: dict = {
        "status": prob.status,
        "weights": {t: round(float(v), 6) for t, v in zip(tickers, w_opt)},
        "trades": {t: round(float(d), 6) for t, d in zip(tickers, trades)},
        "metrics": {
            "expected_return": round(expected_return, 6),
            "volatility": round(vol, 6),
            "sharpe": round(sharpe, 4) if sharpe is not None else None,
            "turnover": round(turnover, 6),
            "tx_cost": round(realised_tx_cost, 6),
        },
    }

    if tracking_error_limit and benchmark_weights:
        w_b = np.array([(benchmark_weights or {}).get(t, 0.0) for t in tickers])
        if w_b.sum() > 0:
            w_b = w_b / w_b.sum()
        te = float(np.sqrt(max((w_opt - w_b) @ Sigma @ (w_opt - w_b), 0.0)))
        result["tracking_error"] = {
            "annualised": round(te, 6),
            "limit": tracking_error_limit,
            "active_share": round(float(0.5 * np.abs(w_opt - w_b).sum()), 4),
        }

    if sector_map:
        sector_exposures: dict[str, float] = {}
        for t, weight in zip(tickers, w_opt):
            sec = sector_map.get(t, "Unknown")
            sector_exposures[sec] = sector_exposures.get(sec, 0.0) + float(weight)
        result["sector_exposures"] = {k: round(v, 4) for k, v in sector_exposures.items()}

    return result


# ── Rolling-horizon wrapper ──────────────────────────────────────────────────


def optimize_multi_period(
    expected_returns: pd.Series,
    cov_matrix: pd.DataFrame,
    current_weights: Optional[dict[str, float]] = None,
    *,
    horizon: int = 4,
    return_decay: float = 0.0,
    **kwargs,
) -> dict:
    """Rolling-horizon MPC: at each of `horizon` steps solve the single-period
    problem, apply, advance. Simulates re-optimisation over time.

    `return_decay` lets the user fade expected returns toward zero across the
    horizon (captures alpha-decay realism — most forecasts don't hold for long).
    """
    steps = []
    weights_state = dict(current_weights) if current_weights else None
    total_turnover = 0.0
    total_tx_cost = 0.0

    for t in range(horizon):
        # Apply return decay for this step
        decay = (1.0 - return_decay) ** t
        mu_t = expected_returns * decay
        step = optimize_single_period(
            expected_returns=mu_t,
            cov_matrix=cov_matrix,
            current_weights=weights_state,
            **kwargs,
        )
        if "error" in step:
            step["step"] = t
            steps.append(step)
            break
        steps.append(
            {
                "step": t,
                "weights": step["weights"],
                "trades": step["trades"],
                "metrics": step["metrics"],
            }
        )
        weights_state = step["weights"]
        total_turnover += step["metrics"]["turnover"]
        total_tx_cost += step["metrics"]["tx_cost"]

    return {
        "horizon": horizon,
        "steps": steps,
        "cumulative": {
            "turnover": round(total_turnover, 4),
            "tx_cost": round(total_tx_cost, 4),
        },
        "final_weights": weights_state,
    }


# ── Helpers ──────────────────────────────────────────────────────────────────


def _psd_wrap(Sigma: np.ndarray, eps: float = 1e-8) -> np.ndarray:
    """Symmetrise + project to positive semi-definite via eigenvalue clipping."""
    S = 0.5 * (Sigma + Sigma.T)
    try:
        w_eig, V = np.linalg.eigh(S)
        w_eig = np.maximum(w_eig, eps)
        return V @ np.diag(w_eig) @ V.T
    except np.linalg.LinAlgError:
        # Fall back: add tiny diagonal
        return S + eps * np.eye(S.shape[0])
