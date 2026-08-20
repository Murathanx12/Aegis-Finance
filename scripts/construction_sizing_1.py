"""CONSTRUCTION-SIZING-1 — is the missing ingredient covariance?

The sizing half of CONSTRUCTION-BOTTLENECK-1, and the test of the one
loose end RISK-SIZING-DISPERSION-1 refused to hand-wave.

That trial left a named anomaly. On the deep-value book, realised
volatility was 0.331 under trailing inverse-vol, 0.596 under the model,
0.589 after the dispersion correction and 0.608 under plain equal
weight. The model's ordering was good there (rank IC 0.764 on those
picks), its coverage was high (93.3%), a concentration cap did not bind,
and the dispersion correction was verified rank-preserving. Every
property of the *estimator* checked out, so the remaining suspect was
never the estimator at all:

    every inverse-volatility rule optimises each name's MARGINAL
    variance and is blind to how the names CO-MOVE.

A book can therefore be assembled entirely out of individually quiet
names that all fall together. Nothing in a per-name variance forecast,
however good, can see that.

ARMS (same signal, same picks, same dates, same costs):

    equal        no sizing at all — the floor
    inverse_vol  1/sqrt(trailing 63d var)        — the incumbent
    model_vol_ds dispersion-corrected model      — the best per-name arm
    min_var      long-only minimum variance on a DENOISED covariance

Declared before running: if covariance-blindness is the missing
ingredient, `min_var` should reduce realised book volatility relative to
every per-name arm, and the improvement should be LARGEST where the
per-name arms disagreed most with each other — the value book.

    python -m scripts.construction_sizing_1

SCREEN. A construction comparison on simulated books; no promotion.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                        # noqa: E402
from backend.services import lane_factory_sim as LFS         # noqa: E402
from backend.services.information_classes import (           # noqa: E402
    build_extras, register)
from backend.services.net_tournament import (                # noqa: E402
    bootstrap_block_dates)
from scripts.risk_sizing_dispersion_1 import (                # noqa: E402
    dispersion_correct, trailing_var_panel)
from scripts.risk_sizing_value_1 import (HANDLINGS, SIGNALS,  # noqa: E402
                                         START, END, TOP_N,
                                         walk_forward_predictions)
from scripts.rule_intervention_1 import (block_boot_stat,    # noqa: E402
                                         _maxdd_of, _vol_of)

OUT = _config.OPTIMUS_LEDGER_DIR / "structure"
ARMS = ("equal", "inverse_vol", "model_vol_ds", "min_var")


def main() -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-boot", type=int, default=2000)
    a = ap.parse_args()

    pred = walk_forward_predictions()
    piv = pred.pivot_table(index="date", columns="permno",
                           values="pred_var", aggfunc="last").sort_index()
    piv.index = pd.to_datetime(piv.index)

    register(LFS.SIGNALS)
    panel = LFS.load_panel()
    extras = build_extras(panel)
    trail = trailing_var_panel(panel, list(piv.index))
    LFS.MODEL_PRED_VAR = dispersion_correct(piv, trail)

    series, rows = {}, []
    for sig in SIGNALS:
        for h in HANDLINGS:
            for arm in ARMS:
                w = "model_vol" if arm == "model_vol_ds" else arm
                k = f"{sig}|{arm}|{h}"
                try:
                    b = LFS.run_book(panel, weighting=w, winner_handling=h,
                                     top_n=TOP_N, signal=sig,
                                     extras=extras, start=START, end=END)
                except Exception as e:                         # noqa: BLE001
                    print(f"  {k}: {type(e).__name__}: {e}")
                    continue
                series[k] = b["monthly_returns"]
                rows.append({"key": k, "signal": sig, "arm": arm,
                             "handling": h,
                             **{kk: vv for kk, vv in b.items()
                                if isinstance(vv, (int, float))}})
                print(f"  {k:34s} vol {b['ann_vol']:.3f} "
                      f"dd {b['max_drawdown']:+.3f} "
                      f"ret {b['total_return']:+.3f} "
                      f"turn {b['turnover_oneway_total']:.0f}")

    R = pd.DataFrame(series).dropna()
    dates = np.array(R.index.values, dtype="datetime64[D]")
    blk = bootstrap_block_dates(dates, 21)

    def contrast(an, bn):
        prs = [(f"{s}|{an}|{h}", f"{s}|{bn}|{h}")
               for s in SIGNALS for h in HANDLINGS
               if f"{s}|{an}|{h}" in R.columns
               and f"{s}|{bn}|{h}" in R.columns]
        if not prs:
            return None
        A, B = R[[x for x, _ in prs]], R[[y for _, y in prs]]
        return {"n_pairs": len(prs),
                "d_ann_vol": block_boot_stat(A, B, _vol_of, blk,
                                             n_boot=a.n_boot),
                "d_max_drawdown": block_boot_stat(A, B, _maxdd_of, blk,
                                                  n_boot=a.n_boot),
                "d_ann_return": block_boot_stat(
                    A, B, lambda x: float(np.nanmean(x) * 12), blk,
                    n_boot=a.n_boot),
                "per_pair_d_ann_vol": {
                    x.split("|")[0] + "|" + x.split("|")[-1]: round(
                        float(R[x].std(ddof=1) * np.sqrt(12)
                              - R[y].std(ddof=1) * np.sqrt(12)), 4)
                    for x, y in prs}}

    contrasts = {f"min_var_vs_{b}": contrast("min_var", b)
                 for b in ("equal", "inverse_vol", "model_vol_ds")}
    contrasts["inverse_vol_vs_equal"] = contrast("inverse_vol", "equal")

    res = {"trial": "CONSTRUCTION-SIZING-1", "mode": "SCREEN",
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "question": "is covariance-blindness the missing ingredient in "
                       "risk sizing?",
           "declared_direction": "min_var should reduce realised book vol "
                                 "vs every per-name arm, most where the "
                                 "per-name arms disagreed most",
           "min_var_note": "long-only imposed by clipping the analytic "
                           "solution and renormalising, not by a QP — an "
                           "approximation, declared as one",
           "n_months": int(len(R)), "arms": list(ARMS),
           "window": [str(R.index.min())[:10], str(R.index.max())[:10]],
           "contrasts": contrasts, "books": rows,
           "label": "SIMULATION — LANE-FACTORY-SIM-1, never a track record"}
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "construction_sizing_1_2026-08-20.json"
    p.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")

    def tag(d):
        return ("POWERED" if d["clears_mde"] else
                ("significant" if d["significant_ci_excludes_zero"]
                 else "ns"))
    for name, c in contrasts.items():
        if not c:
            continue
        print(f"\n{name}  ({c['n_pairs']} pairs, {len(R)} months)")
        for m in ("d_ann_vol", "d_max_drawdown", "d_ann_return"):
            d = c[m]
            print(f"  {m:16s} {d['observed']:+.4f}  MDE {d['mde_80']:.4f}"
                  f"  CI [{d['ci'][0]:+.4f}, {d['ci'][1]:+.4f}]  {tag(d)}")

    print(f"\n{'signal':13s} " + " ".join(f"{x:>13s}" for x in ARMS))
    bs = {b["key"]: b for b in rows}
    for s in SIGNALS:
        vals = [bs.get(f"{s}|{x}|trim", {}).get("ann_vol", float("nan"))
                for x in ARMS]
        best = ARMS[int(np.nanargmin(vals))]
        print(f"{s:13s} " + " ".join(f"{v:>13.3f}" for v in vals)
              + f"   best={best}")
    print(f"\nreceipt -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
