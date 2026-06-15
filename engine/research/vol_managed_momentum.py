"""
Aegis Finance — Volatility-Managed Momentum (TRIAL-VMM, strategy improvement 3a)
================================================================================

The deep-research #1-leverage fix for momentum's thin net edge and crash risk
(Barroso & Santa-Clara 2015): scale the WHOLE momentum book's exposure inversely
to its own recent realized volatility, targeting constant vol. When momentum gets
violent (the regime that precedes momentum crashes), leverage falls automatically.

Construction (leakage-safe): leverage_t = clip(target_vol / trailing_realized_vol)
applied with a ONE-DAY LAG (uses only past vol), on the raw broad-universe
momentum return stream. Cash earns 0 (conservative — ignores rf, so results are
if-anything understated).

Compared vs SPY and vs UNMANAGED momentum, then put through the SAME DSR/PBO gate
that rejected thematic. Deflated against ALL configs tried on this data so far
(3 registry + 15 thematic + this sweep) — strict, anti-self-deception.

Run:  python -m engine.research.vol_managed_momentum
"""

from __future__ import annotations

import itertools
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from backend.config import PROJECT_ROOT, config
from engine.research.thematic_backtest import (
    NO_STOP, TRADING_DAYS, broad_universe, fetch_prices, matched_vol_cagr,
    perf_metrics, run_backtest, select_broad_momentum,
)
from engine.validation.overfitting import (
    deflated_sharpe_from_returns, probability_of_backtest_overfitting,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("vmm")


def vol_target_overlay(raw: pd.Series, target_vol: float, lookback: int,
                       cap: float) -> pd.Series:
    """Barroso–Santa-Clara vol-scaling on a return stream. Lagged → no lookahead."""
    r = raw.dropna()
    rv = r.rolling(lookback).std() * np.sqrt(TRADING_DAYS)
    lev = (target_vol / rv).clip(upper=cap).shift(1).fillna(0.0)
    return (lev * r).dropna()


def main() -> dict:
    prices, spy = fetch_prices()
    broad = broad_universe()
    spy_ret = spy.reindex(prices.index).pct_change().dropna()
    spy_ret = spy_ret[spy_ret.index >= prices.index[0]]
    # align SPY to the strategy trade window below
    base = run_backtest(
        prices, atr_multiple=NO_STOP,
        select_fn=lambda d, s: select_broad_momentum(d, s, lookback_months=12, top_k=10, universe=broad),
    )
    spy_ret = spy_ret.reindex(base.index).dropna()
    spy_m = perf_metrics(spy_ret)
    spy_vol = spy_m["vol"]
    base_m = perf_metrics(base)

    # sweep the overlay
    tv_grid, lb_grid, cap = [0.10, 0.15, 0.20], [21, 63], 2.0
    configs = list(itertools.product(tv_grid, lb_grid))
    managed, results = {}, {}
    log.info("Sweeping %d vol-managed configs…", len(configs))
    for tv, lb in configs:
        m = vol_target_overlay(base, tv, lb, cap)
        managed[(tv, lb)] = m
        results[(tv, lb)] = perf_metrics(m)
        log.info("  tv=%.2f lb=%2d → CAGR %+.1f%%  Sharpe %.2f  maxDD %.1f%%",
                 tv, lb, results[(tv, lb)]["cagr"] * 100,
                 results[(tv, lb)]["sharpe"], results[(tv, lb)]["max_dd"] * 100)

    common = None
    for m in managed.values():
        common = m.index if common is None else common.intersection(m.index)
    mat = np.column_stack([managed[c].reindex(common).values for c in managed])
    pbo = probability_of_backtest_overfitting(mat, n_partitions=10)
    best_c = max(results, key=lambda c: results[c]["sharpe"])
    sharpes = np.array([results[c]["sharpe"] for c in results])
    sr_var = float(np.var(sharpes / np.sqrt(TRADING_DAYS), ddof=1))
    n_trials = 3 + 15 + len(configs)   # strict: all configs tried on this data
    dsr = deflated_sharpe_from_returns(managed[best_c].values, n_trials, sr_var)

    table = {
        "SPY_buyhold": {**spy_m, "matched_vol_cagr": spy_m["cagr"]},
        "momentum_unmanaged": {**base_m, "matched_vol_cagr": matched_vol_cagr(base, spy_vol)},
        "vol_managed_best": {**results[best_c], "matched_vol_cagr": matched_vol_cagr(managed[best_c], spy_vol),
                             "config": {"target_vol": best_c[0], "lookback": best_c[1]}},
    }
    gate_pass = dsr["dsr"] >= 0.95 and pbo.get("pbo", 1.0) < 0.5
    beats_spy = results[best_c]["sharpe"] > spy_m["sharpe"]
    verdict = "PASS — register forward lane" if (gate_pass and beats_spy) else "REJECT/publish"

    out = {"window_obs": int(len(base)), "comparison_table": table, "pbo": pbo,
           "dsr": dsr, "n_trials_deflated_against": n_trials,
           "gate": {"dsr_pass": dsr["dsr"] >= 0.95, "pbo_pass": pbo.get("pbo", 1.0) < 0.5,
                    "beats_spy_sharpe": beats_spy}, "verdict": verdict}

    log.info("\n%s", "=" * 66)
    log.info("%-20s %8s %7s %8s %12s", "Strategy", "CAGR", "Sharpe", "maxDD", "@SPY-vol")
    for name, m in table.items():
        log.info("%-20s %+7.1f%% %7.2f %+7.1f%% %+11.1f%%", name, m["cagr"] * 100,
                 m["sharpe"], m["max_dd"] * 100, m["matched_vol_cagr"] * 100)
    log.info("-" * 66)
    log.info("PBO=%.2f (%s)  DSR=%.3f vs %d trials", pbo.get("pbo", float("nan")),
             pbo.get("interpretation", "?"), dsr["dsr"], n_trials)
    log.info("VERDICT: %s", verdict)
    log.info("=" * 66)

    p = Path(PROJECT_ROOT) / "docs" / "research" / "vol_managed_momentum_results.json"
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    log.info("Wrote %s", p)
    return out


if __name__ == "__main__":
    main()
