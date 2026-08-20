"""RISK-SIZING-VALUE-1 — is the risk head worth anything at BOOK level?

The bridge the programme has never built. OPTION-INCREMENTAL-RISK-1
established that the options-augmented LGBM ranks next-month realized
variance better than trailing realized variance, better than HAR-RV and
better than the options market's own estimate (rank IC ~0.80 vs ~0.75,
MSE(log var) beating IV-scaled in BOTH eras). That is a SECURITY-LEVEL
claim about a number.

INFORMATION-DIMENSION-1 then found that pouring information through a
top-N long-only monthly grammar produces no new portfolio behaviour. So
the obvious question is whether the risk head fares any better when it is
used for the job it is actually good at — SIZING, not selection.

THE CONTRAST
------------
Same signal, same picks, same rebalance dates, same costs, same winner
handling. The ONLY difference is how the chosen names are weighted:

    inverse_vol   w propto 1 / trailing 63-day realized vol   (incumbent)
    model_vol     w propto 1 / sqrt(model predicted variance) (challenger)

Both are inverse-volatility sizing. One uses the past, the other uses a
forecast. If the forecast's superior ranking is real and useful, the
book sized by it should realise LOWER volatility and shallower drawdowns
than the book sized by trailing vol — holding the stock selection fixed.

Declared before running: the challenger should REDUCE realised book
volatility. A null result means the head's ranking advantage does not
survive translation into weights, which would be worth knowing and is a
live possibility — the incumbent is already a strong, nearly free
estimator.

HONESTY OF THE PREDICTIONS
--------------------------
Predictions are strictly walk-forward: for each year Y the model is fit
on rows before Y and predicts Y only. No book ever sees a weight derived
from a model that saw that year. Features are read at the month-end
close of t and the sizing applies to the month beginning t+1.

    python -m scripts.risk_sizing_value_1

SCREEN. A sizing-rule comparison on simulated books; no promotion, no
capital, no track record.
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
from scripts.option_incremental_risk_1 import (              # noqa: E402
    WITH_OPT, build)
from scripts.rule_intervention_1 import (block_boot_stat,    # noqa: E402
                                         _maxdd_of, _vol_of)

OUT = _config.OPTIMUS_LEDGER_DIR / "structure"
PRED = OUT / "risk_sizing_oos_predictions.parquet"
SEED = 20260820

#: a focused signal set spanning the classes, not all 18 — the question
#: is about the SIZING rule, and each extra signal only adds pairs
SIGNALS = ("mom_12_1", "low_vol", "value_bm", "quality_roe",
           "exp_breadth", "opt_iv_low")
HANDLINGS = ("trim", "exempt")
TOP_N = 50
#: concentration cap, as a multiple of equal weight
CAP = 5.0
START, END = "2016-12-31", "2024-11-30"


def walk_forward_predictions(first_test: int = 2017) -> pd.DataFrame:
    """Out-of-sample predicted variance for every permno-month.

    Fit on years strictly before Y, predict Y. A book in year Y is
    therefore never sized by a model that has seen year Y.
    """
    if PRED.exists():
        print(f"reusing {PRED.name}")
        return pd.read_parquet(PRED)
    from lightgbm import LGBMRegressor
    df = build("modern")
    need = list(dict.fromkeys(list(WITH_OPT) + ["fwd_var"]))
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=need)
    feats = list(WITH_OPT)
    out = []
    for y in range(first_test, 2025):
        tr = df[df["date"].dt.year < y]
        te = df[df["date"].dt.year == y]
        if len(tr) < 5000 or not len(te):
            continue
        m = LGBMRegressor(n_estimators=300, num_leaves=31,
                          learning_rate=0.05, random_state=SEED,
                          verbose=-1)
        m.fit(tr[feats].to_numpy(), np.log(tr["fwd_var"].to_numpy()))
        p = te[["permno", "date"]].copy()
        p["pred_var"] = np.exp(m.predict(te[feats].to_numpy()))
        out.append(p)
        print(f"  fold {y}: train {len(tr):,} predict {len(te):,}")
    res = pd.concat(out, ignore_index=True)
    OUT.mkdir(parents=True, exist_ok=True)
    res.to_parquet(PRED, index=False)
    return res


def main() -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-boot", type=int, default=2000)
    a = ap.parse_args()

    print("building out-of-sample predictions...")
    pred = walk_forward_predictions()
    piv = pred.pivot_table(index="date", columns="permno",
                           values="pred_var", aggfunc="last").sort_index()
    piv.index = pd.to_datetime(piv.index)
    print(f"predictions: {piv.shape[0]} dates x {piv.shape[1]} permnos "
          f"({piv.index.min():%Y-%m}..{piv.index.max():%Y-%m})")

    register(LFS.SIGNALS)
    LFS.MODEL_PRED_VAR = piv
    panel = LFS.load_panel()
    extras = build_extras(panel)

    # 2x2: which ESTIMATOR (trailing vs model) x whether the weights are
    # CAPPED. Inverse-vol sizing is unbounded, and a model can output a
    # far smaller variance than any 63-day trailing window, so varying
    # only the estimator confounds "better forecast" with "more extreme
    # concentration". Both knobs move independently here.
    rows, series = [], {}
    for sig in SIGNALS:
        for h in HANDLINGS:
            for w in ("inverse_vol", "model_vol"):
                for cap in (None, CAP):
                    ct = "uncapped" if cap is None else f"cap{cap:g}x"
                    k = f"{sig}|{w}|{ct}|{h}"
                    try:
                        b = LFS.run_book(panel, weighting=w,
                                         winner_handling=h, top_n=TOP_N,
                                         signal=sig, extras=extras,
                                         weight_cap=cap,
                                         start=START, end=END)
                    except Exception as e:                     # noqa: BLE001
                        print(f"  {k}: {type(e).__name__}: {e}")
                        continue
                    series[k] = b["monthly_returns"]
                    rows.append({"key": k, "signal": sig, "weighting": w,
                                 "cap": ct, "handling": h,
                                 **{kk: vv for kk, vv in b.items()
                                    if isinstance(vv, (int, float))}})
                    print(f"  {k:40s} ret {b['total_return']:+.3f} "
                          f"vol {b['ann_vol']:.3f} "
                          f"dd {b['max_drawdown']:.3f}")

    R = pd.DataFrame(series).dropna()
    dates = np.array(R.index.values, dtype="datetime64[D]")
    blk = bootstrap_block_dates(dates, 21)
    ct_cap = f"cap{CAP:g}x"

    def contrast(a_tpl, b_tpl, label):
        prs = [(a_tpl.format(s=s, h=h), b_tpl.format(s=s, h=h))
               for s in SIGNALS for h in HANDLINGS
               if a_tpl.format(s=s, h=h) in R.columns
               and b_tpl.format(s=s, h=h) in R.columns]
        if not prs:
            return None
        A = R[[x for x, _ in prs]]
        B = R[[y for _, y in prs]]
        out = {"label": label, "n_pairs": len(prs),
               "d_ann_vol": block_boot_stat(A, B, _vol_of, blk,
                                            n_boot=a.n_boot),
               "d_max_drawdown": block_boot_stat(A, B, _maxdd_of, blk,
                                                 n_boot=a.n_boot),
               "d_ann_return": block_boot_stat(
                   A, B, lambda x: float(np.nanmean(x) * 12), blk,
                   n_boot=a.n_boot)}
        # heterogeneity: a pooled null can be one pair's blow-up
        out["per_pair_d_ann_vol"] = {
            x.split("|")[0] + "|" + x.split("|")[-1]:
                round(float(R[x].std(ddof=1) * np.sqrt(12)
                            - R[y].std(ddof=1) * np.sqrt(12)), 4)
            for x, y in prs}
        return out

    contrasts = {
        "model_vs_trailing_uncapped": contrast(
            "{s}|model_vol|uncapped|{h}", "{s}|inverse_vol|uncapped|{h}",
            "model_vol - inverse_vol, both UNCAPPED"),
        "model_vs_trailing_capped": contrast(
            "{s}|model_vol|" + ct_cap + "|{h}",
            "{s}|inverse_vol|" + ct_cap + "|{h}",
            f"model_vol - inverse_vol, both capped at {CAP:g}x equal"),
        "cap_effect_on_model": contrast(
            "{s}|model_vol|" + ct_cap + "|{h}",
            "{s}|model_vol|uncapped|{h}",
            "capping the MODEL-sized book"),
        "cap_effect_on_trailing": contrast(
            "{s}|inverse_vol|" + ct_cap + "|{h}",
            "{s}|inverse_vol|uncapped|{h}",
            "capping the TRAILING-sized book"),
    }
    vol = contrasts["model_vs_trailing_uncapped"]["d_ann_vol"]
    dd = contrasts["model_vs_trailing_uncapped"]["d_max_drawdown"]
    ret = contrasts["model_vs_trailing_uncapped"]["d_ann_return"]

    res = {"trial": "RISK-SIZING-VALUE-1", "mode": "SCREEN",
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "question": "does the risk head's PREDICTED vol beat TRAILING "
                       "vol for position sizing, holding selection fixed?",
           "declared_direction": "model_vol should REDUCE realised book "
                                 "volatility vs inverse_vol",
           "n_months": int(len(R)), "weight_cap_multiple": CAP,
           "window": [str(R.index.min())[:10], str(R.index.max())[:10]],
           "predictions": "walk-forward; fit on years < Y, predict Y",
           "contrasts": contrasts,
           "books": rows,
           "label": "SIMULATION — LANE-FACTORY-SIM-1, never a track record"}
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "risk_sizing_value_1_2026-08-20.json"
    p.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")

    def tag(d):
        return ("POWERED" if d["clears_mde"] else
                ("significant" if d["significant_ci_excludes_zero"]
                 else "ns"))
    for key, c in contrasts.items():
        if not c:
            continue
        print(f"\n{c['label']}  ({c['n_pairs']} pairs, {len(R)} months)")
        for m in ("d_ann_vol", "d_max_drawdown", "d_ann_return"):
            d = c[m]
            print(f"  {m:16s} {d['observed']:+.4f}  MDE {d['mde_80']:.4f}"
                  f"  CI [{d['ci'][0]:+.4f}, {d['ci'][1]:+.4f}]  {tag(d)}")
    print("\nper-pair d_ann_vol, model vs trailing (UNCAPPED) — a pooled "
          "null can be one pair's blow-up:")
    for k, v in sorted(contrasts["model_vs_trailing_uncapped"]
                       ["per_pair_d_ann_vol"].items(),
                       key=lambda kv: kv[1]):
        print(f"    {k:28s} {v:+.4f}")
    print(f"\nreceipt -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
