"""
Aegis Finance — Guarded Rule-Evolution Loop (orchestrator)
==========================================================

The honest form of "learn from history": backtests propose **rule** changes,
deflated against the cumulative trial count, adopted/rejected — never feeding the
LLM (see docs/EVOLUTION_LOOP_PLAN.md and the V2_GOALS A2 firewall).

This module is the ORCHESTRATOR. The two halves it wires already exist:
  - leakage-safe backtest: `ReplayEngine.run(..., lane_config_override=...)`
  - acceptance guard: `experiment_registry.evaluate_candidate` (DSR/PBO deflated
    against cumulative trials) + `record_trial`.

HARD STOPS (enforced here, not just by policy):
  - **Never auto-adopt.** A candidate that PASSES the deflation guard is NOT
    recorded as adopted and NOT applied. `evolve_param` returns it with
    `action="STOP_PROPOSE"` so the caller writes it up for a human. Adopting
    changes the live track record — that is a human decision, never unattended.
  - **Rejected candidates are recorded** (verdict 'rejected') and the loop moves
    on — that is the guard working.
  - This module NEVER writes the paper_nav path and NEVER mutates the YAML. An
    adoption (later, by a human) is a separate config-version bump.

Phase-A scope: survivorship-safe params over a broad-ETF + macro universe
(rebalance drift/frequency, optimizer lookback, sleeve %, crash thresholds).
Individual-stock / smart-money lanes need the as-of-constituents + SEC layer
(Phase B) and are out of scope here.
"""

from __future__ import annotations

import json
import logging
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from backend.config import paper_portfolios
from backend.services.portfolio_intelligence.experiment_registry import (
    cumulative_trial_count,
    evaluate_candidate,
    record_trial,
)
from backend.services.portfolio_intelligence.replay import ReplayEngine

logger = logging.getLogger(__name__)


def _per_obs_sharpe(returns: pd.Series) -> float:
    r = np.asarray(returns, dtype=float)
    r = r[~np.isnan(r)]
    if len(r) < 2:
        return 0.0
    sd = r.std(ddof=1)
    return float(r.mean() / sd) if sd > 1e-12 else 0.0


def _backtest_candidate(
    lane_id: str,
    override: dict,
    start_date: str,
    end_date: Optional[str],
    engine: Optional[ReplayEngine] = None,
) -> pd.Series:
    """Leakage-safe backtest of one candidate config → per-period return series.

    Returns the check-date NAV path's returns (the same NAV the live path marks).
    Reuses an injected engine so a grid shares one data fetch. Isolated here so
    tests can monkeypatch it deterministically (no network).
    """
    eng = engine or ReplayEngine()
    res = eng.run(lane_id, start_date=start_date, end_date=end_date,
                  lane_config_override=override)
    pts = res.equity_curve or []
    if len(pts) < 3:
        return pd.Series(dtype=float)
    vals = pd.Series(
        [p["value"] for p in pts],
        index=pd.to_datetime([p["date"] for p in pts]),
    )
    return vals.pct_change().dropna()


def evolve_param(
    lane_id: str,
    param: str,
    value_grid: Sequence,
    *,
    start_date: str = "2001-01-01",
    end_date: Optional[str] = None,
    dry_run: bool = True,
    db_path=None,
    engine: Optional[ReplayEngine] = None,
) -> dict:
    """Propose → backtest a grid → deflate the best → adopt-proposal / reject.

    Backtests each value in `value_grid` (leakage-safe replay), takes the best by
    per-period Sharpe, and deflates it via `evaluate_candidate` against the
    CUMULATIVE trial count using the GRID as the multiple-testing batch
    (n_trials = cumulative + len(grid), sr_variance = var of grid Sharpes). The
    finer the grid you search, the higher the bar the winner must clear — that is
    the False Strategy Theorem doing its job.

    Outcomes:
      - REJECTED (does not survive): recorded as a 'rejected' trial (unless
        dry_run); `action="recorded_rejected"`. The loop's normal output.
      - PASSES the guard: **full stop**. NOT recorded as adopted, NOT applied;
        `action="STOP_PROPOSE"` — the caller must write it up for a human to
        adopt. Never auto-adopt (changes the live track record).

    Returns a summary dict (always; never raises on a bad candidate — it skips it).
    """
    if param not in (paper_portfolios.get(lane_id) or {}):
        # Top-level lane params only in Phase A (shallow-merge override).
        return {"status": "skipped", "reason": f"unknown/non-top-level param {param!r} for {lane_id}",
                "lane_id": lane_id, "param": param}

    old_value = paper_portfolios[lane_id].get(param)
    eng = engine or ReplayEngine()

    grid_results = []
    for v in value_grid:
        try:
            rets = _backtest_candidate(lane_id, {param: v}, start_date, end_date, engine=eng)
        except Exception as e:  # a bad candidate skips, never crashes the loop
            logger.warning("evolve_param: candidate %s=%s failed: %s", param, v, e)
            continue
        if len(rets) < 2:
            continue
        grid_results.append({"value": v, "sharpe": _per_obs_sharpe(rets),
                             "n_obs": int(len(rets)), "returns": rets})

    if not grid_results:
        return {"status": "no_valid_candidates", "lane_id": lane_id, "param": param}

    sharpes = [g["sharpe"] for g in grid_results]
    sr_variance = float(np.var(sharpes, ddof=1)) if len(sharpes) > 1 else 0.0
    best = max(grid_results, key=lambda g: g["sharpe"])

    existing = cumulative_trial_count(db_path)
    ev = evaluate_candidate(
        best["returns"].to_numpy(),
        batch_sr_variance=sr_variance,
        batch_trials=len(grid_results),
        db_path=db_path,
    )

    summary = {
        "status": "ok",
        "lane_id": lane_id,
        "param": param,
        "old_value": old_value,
        "best_value": best["value"],
        "best_sharpe": round(best["sharpe"], 4),
        "n_obs": best["n_obs"],
        "grid_size": len(grid_results),
        "sr_variance": round(sr_variance, 6),
        "existing_trials": existing,
        "n_trials_deflated_against": ev["n_trials"],
        "dsr": ev["dsr"],
        "pbo": ev["pbo"],
        "survives": ev["survives"],
        "grid": [{"value": g["value"], "sharpe": round(g["sharpe"], 4),
                  "n_obs": g["n_obs"]} for g in grid_results],
        "window": {"start": start_date, "end": end_date},
    }

    if ev["survives"]:
        # HARD STOP — never auto-adopt. Surface for a human; do not record adopted.
        summary["action"] = "STOP_PROPOSE"
        summary["note"] = ("PASSES deflation guard — full stop. Write to PROPOSALS.md "
                           "with the trial record + segment-boundary implications; "
                           "adoption (a config-version bump) is a human decision.")
        logger.warning("evolve_param: %s.%s=%s PASSES guard (DSR=%.3f) — STOP, propose to human.",
                       lane_id, param, best["value"], ev["dsr"])
        return summary

    # Rejected: record the trial (the loop working) and move on.
    summary["action"] = "recorded_rejected" if not dry_run else "dry_run_not_recorded"
    if not dry_run:
        rid = record_trial(
            ev, param=param, old_value=old_value, new_value=best["value"],
            config_version="evolution-candidate", lane_id=lane_id,
            notes=json.dumps({"source": "rule_evolution.evolve_param",
                              "grid": summary["grid"], "window": summary["window"]}),
            db_path=db_path,
        )
        summary["recorded_trial_id"] = rid
        logger.info("evolve_param: %s.%s rejected (DSR=%.3f, n_trials=%d) — recorded #%d.",
                    lane_id, param, ev["dsr"], ev["n_trials"], rid)
    return summary
