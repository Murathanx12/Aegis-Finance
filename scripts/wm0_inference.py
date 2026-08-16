"""WM0/WM0B: dependence-aware inference, and the shape x scale decomposition.

    python -m scripts.wm0_inference

WHY THIS IS A SEPARATE SCRIPT
=============================
It refits nothing. It loads the cached per-row predictions written by
`wm0_train.py` and re-does the *inference* on them, so the numbers below are
about the same fits that produced the reported losses. Re-running the training
to change a confidence interval would quietly make it a different experiment.

WHAT IT ANSWERS
===============
1. **Is a meaningful improvement excluded?** The prereg declared a 2% economic
   floor. "WM0 is worse" and "no worthwhile improvement was available here" are
   different claims and only the second closes anything. This computes the
   second, against the declared floor, on the corrected dependence unit.

2. **Is the estimator the bottleneck, or is there no conditional shape?** WM0
   and WM0B produced calibration curves identical to within 0.005 at every
   quantile, which says the two arms never differed in the dimension they
   miss. That is evidence about a SHARED component, and "the shared component
   is the estimator" was a hypothesis, not a measurement.

   The 2x2 measures it:

                      scale = estimated        scale = ORACLE
       shape empirical   scaled_empirical      empirical + oracle
       shape learned     WM0B                  learned + oracle

   If learned shape suddenly contributes once scale is handed to it perfectly,
   the estimator is the bottleneck. If it still does not, the shape model has
   no demonstrated incremental information and the estimator hypothesis is
   refuted along with it.

THE ORACLE IS NOT A MODEL
=========================
`oracle` scale is the realised volatility of the security measured OVER THE
VERY WINDOW being predicted. It is the answer's own dispersion. It cannot be
deployed, it is not evidence for any policy, and it is constructed through
`evaluation_only.oracle_scale` so that multiplying by it raises unless the call
site says `for_comparison_only()`.

THIS IS DIAGNOSIS, NOT WM0C. Nothing here is fitted, tuned or selected. The
WM0B prereg budgeted two attempts and both are spent.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from backend import config as _config
from backend.services import world_model as WM
from backend.services.research_gym.evaluation_only import oracle_scale

GYM = _config.OPTIMUS_LEDGER_DIR / "research_gym"
RUNS = {
    "WM0": GYM / "wm0_world_model_v0.npz",
    "WM0B": GYM / "wm0b_standardised.npz",
}
OUT = GYM / "wm0_inference.json"

HORIZON = 20
BLOCK_DAYS = HORIZON * 2
#: from PREREG_WM0: "improvement >= 2% of baseline loss" is the economic floor,
#: set from what a vol-target's exposure consumes. Frozen; not re-derived here.
ECONOMIC_FLOOR_PCT = 2.0
SEED = 20260816


def _paired(diff: np.ndarray, dates: np.ndarray) -> WM.PairedInference:
    return WM.block_bootstrap_paired(diff, dates, BLOCK_DAYS, n_boot=4000,
                                     seed=SEED)


def _equivalence(inf: WM.PairedInference, baseline_loss: float) -> dict:
    """Has a 2%-of-baseline IMPROVEMENT been excluded?

    A worthwhile improvement is a difference of `-0.02 * baseline`. It is
    excluded when the one-sided 95% LOWER bound on the difference sits above
    that value — i.e. the data are inconsistent with the model being that much
    better.
    """
    margin = -(ECONOMIC_FLOOR_PCT / 100.0) * baseline_loss
    excluded = inf.ci_lo > margin
    return {
        "economic_floor_pct": ECONOMIC_FLOOR_PCT,
        "margin_abs": float(margin),
        "lcb95_diff": float(inf.ci_lo),
        "meaningful_improvement_excluded": bool(excluded),
        "verdict": ("MEANINGFUL_IMPROVEMENT_EXCLUDED" if excluded
                    else "MEANINGFUL_IMPROVEMENT_NOT_EXCLUDED"),
    }


def _forward_realised_scale(secs: np.ndarray, dates: np.ndarray,
                            universe: list[str], start: str, end: str
                            ) -> np.ndarray:
    """sd of daily returns over [t, t+H), annualised then scaled to H days.

    This is hindsight by construction — it is measured on the window whose
    outcome is being predicted.
    """
    import pandas as pd
    import yfinance as yf

    lut: dict[tuple[str, np.datetime64], float] = {}
    for tkr in universe:
        px = yf.download(tkr, start=start, end=end, progress=False)["Close"]
        if isinstance(px, pd.DataFrame):
            px = px.squeeze()
        px = px.dropna()
        r = px.pct_change()
        # forward window (t, t+H]: reverse-rolling std, then shift so the
        # value at t describes the H days AFTER t and never includes t itself
        fwd_sd = r[::-1].rolling(HORIZON).std()[::-1].shift(-1)
        vals = (fwd_sd * np.sqrt(252.0) * 100.0
                * np.sqrt(HORIZON / WM.TRADING_DAYS))
        for d, v in vals.dropna().items():
            lut[(tkr, np.datetime64(d.date()))] = float(v)

    day = dates.astype("datetime64[D]")
    out = np.full(len(secs), np.nan)
    for i in range(len(secs)):
        out[i] = lut.get((str(secs[i]), day[i]), np.nan)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", default="1999-01-01")
    ap.add_argument("--end", default="2026-08-15")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    payload: dict = {"block_days": BLOCK_DAYS,
                     "economic_floor_pct": ECONOMIC_FLOOR_PCT,
                     "refit": False, "runs": {}}

    # ── 1. corrected inference on both runs ────────────────────────────────
    print("=" * 78)
    print("1. PAIRED INFERENCE ON THE CORRECTED DEPENDENCE UNIT")
    print("=" * 78)
    loaded = {}
    for name, path in RUNS.items():
        if not path.exists():
            print(f"  {name}: {path.name} missing — run wm0_train first")
            continue
        z = np.load(path, allow_pickle=True)
        loaded[name] = z
        y, dates = z["y"], z["dates"]
        Lm = WM.pinball_loss(y, z["pred_world_model"]).mean(axis=1)
        Lb = WM.pinball_loss(y, z["pred_scaled_empirical"]).mean(axis=1)
        base = float(Lb.mean())
        inf = _paired(Lm - Lb, dates)
        eq = _equivalence(inf, base)
        rel = 100.0 * (1.0 - float(Lm.mean()) / base)
        print(f"\n{name}")
        print(f"  mean pinball {Lm.mean():.5f} vs baseline {base:.5f}  "
              f"({rel:+.2f}%)")
        print(f"  {inf.n_rows} rows = {inf.n_dates} dates x "
              f"~{inf.n_securities} securities => n_eff {inf.n_effective:.0f}")
        print(f"  paired diff {inf.mean:+.5f}  90% CI "
              f"[{inf.ci_lo:+.5f}, {inf.ci_hi:+.5f}]  SE {inf.se:.5f}")
        print(f"  80%-power MDE {inf.mde_80pct_power:.5f} "
              f"({100.0 * inf.mde_80pct_power / base:.2f}% of baseline)")
        print(f"  observed effect {abs(rel):.2f}% vs MDE "
              f"{100.0 * inf.mde_80pct_power / base:.2f}% -> "
              + ("BELOW its own MDE: the interval excludes zero but the "
                 "design was not powered for an effect this size"
                 if abs(rel) < 100.0 * inf.mde_80pct_power / base
                 else "above its own MDE"))
        print(f"  equivalence vs the declared {ECONOMIC_FLOOR_PCT}% floor: "
              f"{eq['verdict']}")
        print(f"    a worthwhile improvement is a diff of {eq['margin_abs']:+.5f}; "
              f"LCB95 is {eq['lcb95_diff']:+.5f}")
        payload["runs"][name] = {
            "mean_pinball": float(Lm.mean()), "baseline": base,
            "rel_pct": rel, "paired": inf.as_dict(), "equivalence": eq,
        }

    if "WM0B" not in loaded:
        print("\nWM0B cache missing; skipping the decomposition.")
        Path(a.out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return 1

    # ── 2. the 2x2: shape x scale ──────────────────────────────────────────
    print("\n" + "=" * 78)
    print("2. SHAPE x SCALE  (DIAGNOSIS ONLY — oracle scale is not deployable)")
    print("=" * 78)
    z = loaded["WM0B"]
    y, dates, secs, rv = z["y"], z["dates"], z["secs"], z["rv"]
    est_scale = rv * np.sqrt(HORIZON / WM.TRADING_DAYS)

    # recover the STANDARDISED quantile shapes by dividing out the estimated
    # scale each arm was multiplied by. Sorting commutes with positive scaling,
    # so this is exact, not an approximation.
    ok = est_scale > 0
    shape_learned = z["pred_world_model"][ok] / est_scale[ok, None]
    shape_empirical = z["pred_scaled_empirical"][ok] / est_scale[ok, None]
    y_ok, dates_ok, secs_ok = y[ok], dates[ok], secs[ok]
    est_ok = est_scale[ok]

    universe = ["SPY", "QQQ", "IWM", "XLF", "XLE", "XLK", "XLV", "XLI", "XLP",
                "XLU", "XLB", "XLY", "DIA", "TLT", "GLD", "EFA", "EEM", "IYR"]
    print("\nbuilding the ORACLE scale (realised vol over the outcome window "
          "itself) ...")
    oracle_raw = _forward_realised_scale(secs_ok, dates_ok, universe,
                                         a.start, a.end)
    oracle = oracle_scale(
        oracle_raw,
        basis="realised volatility measured over the very H-day window whose "
              "return distribution is being predicted")
    have = np.isfinite(oracle.for_comparison_only()) & (
        oracle.for_comparison_only() > 0)
    print(f"  oracle available for {have.sum()}/{len(have)} rows "
          f"({100.0 * have.mean():.1f}%)")

    # `.for_comparison_only()` is required to get the numbers out, and this is
    # the only place in the repository that calls it on an oracle.
    orc = oracle.for_comparison_only()
    cells = {
        ("empirical", "estimated"): shape_empirical * est_ok[:, None],
        ("learned", "estimated"): shape_learned * est_ok[:, None],
        ("empirical", "oracle"): shape_empirical * orc[:, None],
        ("learned", "oracle"): shape_learned * orc[:, None],
    }

    print(f"\n{'cell':<28s} {'mean pinball':>13s} {'tail pinball':>13s} "
          f"{'vs emp+same scale':>19s}")
    tail_idx = [i for i, q in enumerate(WM.QUANTILES) if q <= 0.10]
    scores: dict = {}
    for (shape, scale), pred in cells.items():
        p = WM.enforce_monotone(pred[have])
        Lc = WM.pinball_loss(y_ok[have], p)
        scores[(shape, scale)] = Lc
    for (shape, scale), Lc in scores.items():
        ref = scores[("empirical", scale)]
        rel = 100.0 * (1.0 - float(Lc.mean()) / float(ref.mean()))
        print(f"{shape + ' shape / ' + scale + ' scale':<28s} "
              f"{Lc.mean():>13.5f} {Lc[:, tail_idx].mean():>13.5f} "
              f"{rel:>+18.2f}%")

    # the decisive comparison: does LEARNED shape help once scale is perfect?
    print("\nthe question: does learned shape contribute when scale is exact?")
    dec = {}
    for scale in ("estimated", "oracle"):
        d = (scores[("learned", scale)].mean(axis=1)
             - scores[("empirical", scale)].mean(axis=1))
        base = float(scores[("empirical", scale)].mean())
        inf = _paired(d, dates_ok[have])
        rel = 100.0 * inf.mean / base
        verdict = ("LEARNED_SHAPE_HELPS" if inf.ci_hi < 0 else
                   "LEARNED_SHAPE_HURTS" if inf.ci_lo > 0 else
                   "NOT_DETECTABLE")
        print(f"  scale={scale:<10s} learned - empirical = {inf.mean:+.5f} "
              f"({rel:+.2f}% of baseline)  90% CI "
              f"[{inf.ci_lo:+.5f}, {inf.ci_hi:+.5f}]  -> {verdict}")
        dec[scale] = {"paired": inf.as_dict(), "rel_pct": rel,
                      "verdict": verdict, "baseline": base}

    est_v, orc_v = dec["estimated"]["verdict"], dec["oracle"]["verdict"]
    if est_v != "LEARNED_SHAPE_HELPS" and orc_v == "LEARNED_SHAPE_HELPS":
        reading = ("ESTIMATOR_IS_THE_BOTTLENECK — learned shape carries "
                   "information that only survives when scale is exact")
    elif orc_v != "LEARNED_SHAPE_HELPS":
        reading = ("NO_INCREMENTAL_SHAPE_INFORMATION — handed a perfect scale, "
                   "the learned shape still does not beat the pooled empirical "
                   "one. The estimator-bottleneck hypothesis is NOT supported, "
                   "and neither is 'conditional shape exists but was masked'.")
    else:
        reading = ("learned shape helps in both columns — scale was never the "
                   "constraint")
    print(f"\n  READING: {reading}")

    # calibration of each cell, since that is what produced the hypothesis
    print(f"\ncalibration by cell — target = tau")
    print(f"{'cell':<28s} " + "".join(f"{q:>7.2f}" for q in WM.QUANTILES))
    cal = {}
    for (shape, scale), pred in cells.items():
        p = WM.enforce_monotone(pred[have])
        c = WM.pit_coverage(y_ok[have], p)
        cal[f"{shape}|{scale}"] = [float(x) for x in c]
        print(f"{shape + ' / ' + scale:<28s} "
              + "".join(f"{x:>7.3f}" for x in c))

    payload["decomposition"] = {
        "oracle_basis": oracle.basis,
        "oracle_coverage_pct": float(100.0 * have.mean()),
        "n_rows": int(have.sum()),
        "cells": {f"{s}|{sc}": {"mean_pinball": float(L.mean()),
                                "tail_pinball": float(L[:, tail_idx].mean())}
                  for (s, sc), L in scores.items()},
        "learned_minus_empirical": dec,
        "reading": reading,
        "calibration": cal,
        "not_a_trial": "diagnosis only; no fit, tune or selection occurred",
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
