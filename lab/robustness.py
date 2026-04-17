"""
Lab v12 — Robustness probes
=============================

Stresses a handful of core engine paths against edge cases after each
cycle. The idea: a cycle can pass the test suite but silently break
edge-case behaviour (flat vol → MC degenerate, single-asset portfolio →
optimizer NaN, huge drawdown → crash prob clamped to 0). These probes
run in-process (no subprocess overhead), exit quickly, and emit a small
report the rd_loop can inject into the next prompt.

Each probe returns `(name, ok, detail)`. Aggregate into a robustness
sub-score that contributes to the quality composite.
"""

from __future__ import annotations

import logging
from typing import Callable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _probe_flat_vol_mc() -> tuple[str, bool, str]:
    """MC with zero daily returns → should not crash, should produce bounded output."""
    try:
        from backend.services.monte_carlo import simulate_paths

        scenario = {"drift_adj": 0.0, "vol_mult": 1.0, "crash_mult": 1.0, "label": "Flat"}
        paths = simulate_paths(
            start_price=4500.0,
            historical_mu=0.0,
            historical_sigma=0.0001,
            days=60,
            n_sims=200,
            crash_freq=0.0,
            scenario=scenario,
            seed=42,
        )
        if paths is None or paths.size == 0:
            return ("flat_vol_mc", False, "simulate_paths returned empty")
        span = float(paths.max() - paths.min())
        # With near-zero vol and no jumps, span should be tiny
        if span > 4500.0 * 0.5:
            return ("flat_vol_mc", False, f"unexpected span {span:.1f}")
        return ("flat_vol_mc", True, f"span={span:.2f}")
    except Exception as e:
        return ("flat_vol_mc", False, f"{type(e).__name__}: {e}")


def _probe_extreme_drawdown() -> tuple[str, bool, str]:
    """Anomaly detector should treat a -60% price move as anomalous."""
    try:
        from backend.services.anomaly_detector import AnomalyDetector

        rng = np.random.default_rng(42)
        feats = pd.DataFrame(
            {
                "vix": rng.normal(20, 4, 400),
                "return_21d": rng.normal(0, 0.015, 400),
                "spread": rng.normal(0.5, 0.3, 400),
            }
        )
        det = AnomalyDetector(contamination=0.05)
        det.fit(feats)
        stressed = pd.DataFrame(
            {"vix": [95.0], "return_21d": [-0.60], "spread": [-5.0]}
        )
        report = det.anomaly_report(stressed)
        ok = report.get("status") == "ANOMALOUS"
        return ("extreme_drawdown_flag", ok, f"status={report.get('status')}")
    except Exception as e:
        return ("extreme_drawdown_flag", False, f"{type(e).__name__}: {e}")


def _probe_single_asset_optimizer() -> tuple[str, bool, str]:
    """MPC optimizer with a single asset must return weight 1.0 and not crash."""
    try:
        from backend.services.mpc_optimizer import optimize_single_period

        mu = pd.Series([0.08], index=["X"])
        Sigma = pd.DataFrame([[0.04]], index=["X"], columns=["X"])
        res = optimize_single_period(mu, Sigma, max_weight=1.0)
        if "error" in res:
            return ("single_asset_optimizer", False, res["error"])
        w = res["weights"].get("X", 0.0)
        ok = abs(w - 1.0) < 1e-3
        return ("single_asset_optimizer", ok, f"w=X -> {w:.4f}")
    except Exception as e:
        return ("single_asset_optimizer", False, f"{type(e).__name__}: {e}")


def _probe_crash_timeline_monotone() -> tuple[str, bool, str]:
    """Cumulative crash probability must be monotonically non-decreasing."""
    try:
        from backend.services.crash_timeline import estimate_crash_timeline

        result = estimate_crash_timeline(current_level=4500.0, months_ahead=12)
        cum = [m["cumulative"] for m in result["monthly_probabilities"]]
        for a, b in zip(cum, cum[1:]):
            if b < a - 0.5:
                return (
                    "crash_timeline_monotone",
                    False,
                    f"regression at {a:.1f} → {b:.1f}",
                )
        return ("crash_timeline_monotone", True, f"last cumulative={cum[-1]:.1f}")
    except Exception as e:
        return ("crash_timeline_monotone", False, f"{type(e).__name__}: {e}")


def _probe_empty_portfolio_analyze() -> tuple[str, bool, str]:
    """Portfolio analyze on a tiny 2-holding portfolio should not crash."""
    try:
        from backend.services.portfolio_engine import PortfolioEngine

        out = PortfolioEngine.analyze_portfolio(
            [
                {"ticker": "SPY", "shares": 1.0, "current_price": 550.0},
                {"ticker": "AGG", "shares": 1.0, "current_price": 100.0},
            ]
        )
        if not isinstance(out, dict):
            return ("empty_portfolio_analyze", False, "non-dict output")
        return ("empty_portfolio_analyze", True, "")
    except Exception as e:
        return ("empty_portfolio_analyze", False, f"{type(e).__name__}: {e}")


PROBES: list[Callable[[], tuple[str, bool, str]]] = [
    _probe_flat_vol_mc,
    _probe_extreme_drawdown,
    _probe_single_asset_optimizer,
    _probe_crash_timeline_monotone,
    _probe_empty_portfolio_analyze,
]


def run_all() -> dict:
    """Execute every probe. Return aggregate + per-probe detail."""
    results = []
    for probe in PROBES:
        try:
            name, ok, detail = probe()
        except Exception as e:
            name, ok, detail = (probe.__name__, False, f"probe crashed: {e}")
        results.append({"name": name, "ok": ok, "detail": detail})

    total = len(results)
    passed = sum(1 for r in results if r["ok"])
    score = passed / total if total else 1.0
    return {
        "score": round(score, 3),
        "passed": passed,
        "total": total,
        "probes": results,
    }


def summary_line(report: dict) -> str:
    """One-liner for prompt injection."""
    score = report.get("score", 1.0)
    passed = report.get("passed", 0)
    total = report.get("total", 0)
    fails = [r["name"] for r in report.get("probes", []) if not r["ok"]]
    msg = f"Robustness: {passed}/{total} probes passed ({score:.2f})"
    if fails:
        msg += " — failures: " + ", ".join(fails)
    return msg
