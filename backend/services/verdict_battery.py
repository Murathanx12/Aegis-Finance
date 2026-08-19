"""VERDICT-BATTERY-1 — measures whether the referee kills good ideas.

G1's flip condition: the known-answer battery must recover planted truth
at DECLARED false-positive AND false-kill rates. The known-answer worlds
(nonlinear/null/barrier) cover detection of LARGE effects; this module
measures the verdict machinery's operating characteristics at REALISTIC
effect sizes — including the one that matters most and is easiest to get
wrong: a TRUE effect near the economic bar.

THE THREE ERROR RATES, NAMED
============================
- FALSE POSITIVE: COMPLEX_WINS on a world with zero true effect.
- FALSE KILL: LINEAR_NONINFERIOR on a world whose true effect is at or
  above the economic bar — the verdict that closes a door on a live idea.
  (NOT_ESTABLISHED is NOT a kill: it leaves the door open by name.)
- POWER: COMPLEX_WINS on a world whose true effect is at the detectable
  size — should approach the declared 80%.

The battery runs at the STATISTICAL layer: it simulates the per-date ΔIC
series the tournament actually consumes (Gaussian with declared true mean
and the MEASURED per-date dispersion from the first registered run), and
feeds it through the same `block_bootstrap_paired` + `head_verdicts` path
as a real run. Model fitting is covered separately by the known-answer
worlds; this tier isolates the judge.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from backend.services.net_tournament import head_verdicts
from backend.services.world_model import block_bootstrap_paired

#: Measured on the first registered run (tournament_2026-08-19T040624Z):
#: per-date ΔIC dispersion se·√n_dates = 0.0189·√126 ≈ 0.212.
MEASURED_PER_DATE_SD = 0.212


class BatteryRefused(RuntimeError):
    """A required declaration is missing. Refused, not defaulted."""


def simulate_verdicts(*, true_delta: float, n_dates: int = 126,
                      per_date_sd: float = MEASURED_PER_DATE_SD,
                      n_sims: int = 1000, economic_bar: float = 0.01,
                      n_arms: int = 4, seed: int = 20260819,
                      n_boot: int = 400) -> dict:
    """Verdict rates for a declared true effect, through the REAL judge.

    Each simulation draws a per-date ΔIC series for `n_arms` arms sharing
    the same true effect (the Holm step-down sees realistic siblings),
    runs the actual bootstrap + three-way verdict, and tallies the first
    arm's verdict. Refuses non-finite declarations.
    """
    if not np.isfinite(true_delta) or n_sims < 1:
        raise BatteryRefused(f"true_delta={true_delta!r}, n_sims={n_sims!r}"
                             f" — a battery needs a declared world")
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2016-01-29", periods=n_dates,
                           freq="ME").to_numpy(dtype="datetime64[D]")
    tally = {"COMPLEX_WINS": 0, "LINEAR_NONINFERIOR": 0,
             "NOT_ESTABLISHED": 0}
    for s in range(n_sims):
        contrasts = {}
        for a in range(n_arms):
            d = rng.normal(true_delta, per_date_sd, size=n_dates)
            inf = block_bootstrap_paired(d, dates, block_days=1,
                                         n_boot=n_boot, seed=int(
                                             rng.integers(2**31)))
            contrasts[f"arm_{a}"] = inf.as_dict()
        v = head_verdicts(contrasts, economic_bar=economic_bar)
        tally[v["arm_0"]["verdict"]] += 1
    out = {k: v / n_sims for k, v in tally.items()}
    out.update(true_delta=true_delta, n_dates=n_dates,
               per_date_sd=per_date_sd, n_sims=n_sims,
               economic_bar=economic_bar, n_arms=n_arms)
    return out


def decision_mde_80(*, target_power: float = 0.80, n_sims: int = 300,
                    n_dates: int = 126,
                    per_date_sd: float = MEASURED_PER_DATE_SD,
                    economic_bar: float = 0.01, n_arms: int = 4,
                    tol: float = 0.02, seed: int = 20260819,
                    n_boot: int = 400) -> dict:
    """The effect size at which the FULL judge reaches `target_power`.

    The z-based `mde_80pct_power` prices only the bootstrap interval; the
    complete decision procedure also charges Holm across the sibling arms
    and the economic-bar condition, so its true 80%-power point sits
    HIGHER (VERDICT-BATTERY-1 measured ~50% win rate at the nominal MDE).
    This solver bisects true_delta through `simulate_verdicts` until
    P(COMPLEX_WINS) crosses `target_power`. Keep both numbers, named:
    STATISTICAL_MDE_80 (z-based) vs DECISION_MDE_80 (this).
    """
    stat_mde = float(2.8 * per_date_sd / np.sqrt(n_dates))
    lo, hi = stat_mde, 3.0 * stat_mde   # battery: 50% at 1x, ~100% at 2x
    trace = []

    def power(delta: float) -> float:
        r = simulate_verdicts(true_delta=delta, n_sims=n_sims,
                              n_dates=n_dates, per_date_sd=per_date_sd,
                              economic_bar=economic_bar, n_arms=n_arms,
                              seed=seed, n_boot=n_boot)
        trace.append({"true_delta": round(delta, 6),
                      "p_complex_wins": r["COMPLEX_WINS"]})
        return r["COMPLEX_WINS"]

    if power(hi) < target_power:
        return {"decision_mde_80": None, "statistical_mde_80": stat_mde,
                "note": f"not reached below {hi:.4f}", "trace": trace}
    while hi - lo > tol * stat_mde:
        mid = 0.5 * (lo + hi)
        if power(mid) >= target_power:
            hi = mid
        else:
            lo = mid
    return {"decision_mde_80": float(hi),
            "statistical_mde_80": stat_mde,
            "ratio_decision_over_statistical": float(hi / stat_mde),
            "target_power": target_power, "n_sims_per_point": n_sims,
            "n_arms_holm": n_arms, "economic_bar": economic_bar,
            "trace": trace}


def run_battery(n_sims: int = 1000, *, per_date_sd: float =
                MEASURED_PER_DATE_SD, n_dates: int = 126) -> dict:
    """The declared grid, with each cell's PASS criterion beside it."""
    mde = 2.8 * per_date_sd / np.sqrt(n_dates)
    cells = {
        "null_world": dict(true_delta=0.0),
        "at_economic_bar": dict(true_delta=0.01),
        "at_mde": dict(true_delta=float(mde)),
        "twice_mde": dict(true_delta=float(2 * mde)),
    }
    results = {}
    for name, cfg in cells.items():
        results[name] = simulate_verdicts(n_sims=n_sims, n_dates=n_dates,
                                          per_date_sd=per_date_sd, **cfg)
    return {
        "battery": "VERDICT-BATTERY-1",
        "mde_at_this_n": float(mde),
        "cells": results,
        "declared_criteria": {
            "false_positive_rate": ("null_world COMPLEX_WINS ≤ 0.05 — the "
                                    "Holm FWER doing its job"),
            "false_kill_rate": ("at_economic_bar + at_mde LINEAR_NONINFERIOR"
                                " ≈ 0 — a true effect at/above the bar must "
                                "essentially never be declared noninferior; "
                                "NOT_ESTABLISHED is the honest under-powered "
                                "answer and does NOT count as a kill"),
            "power": "twice_mde COMPLEX_WINS ≥ ~0.8 per its construction",
        },
    }
