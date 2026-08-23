"""RELATIVE-VALUE-NN-1 — should capital move from A to B, net of costs?

WHY THIS IS A BETTER QUESTION THAN "WILL B GO UP"
=================================================
Roadmap P1.2. Every other selector in this repository asks "is this stock good".
The actual decision a portfolio makes is "is this stock better than the one whose
capital it would take, after paying to switch". `relative_value_labels`
(NEURAL-RELATIVE-VALUE-1, Order 20 §4) already built that label: 72,495 ordered
pairs, each charged BOTH one-way costs at the two names' own measured TAQ rates,
with pairs whose verdict flips inside the cost band excluded and counted.

THE COUNT THAT MATTERS IS 145
=============================
72,495 pairs come from **145 dates**. Under CANON §58 the effective sample is
145, and the corpus's own metadata says so: "a million pairs on 145 dates is
145 — the pair count is a fact about sampling, not about information". Every
split and every interval here is by DATE.

WHAT THIS RUN EXISTS TO SETTLE
==============================
Two separate questions, and the second is the one the roadmap wants closed:

  1. Is pairwise capital substitution predictable at all, out of block?
  2. Does a NEURAL model add anything a tree or a line does not?

The decision rule for (2) is declared below and it is deliberately hostile to
the neural answer: if an MLP cannot beat LightGBM out of block, the neural
question closes with a receipt rather than being retried until it wins. Forcing
a neural network into production because the roadmap has the letters NN in it
would be architecture theatre.

A MULTI-HEAD TORCH MODEL IS NOT BUILT HERE, ON PURPOSE. The roadmap describes
one (P(B beats A), expected improvement, drawdown improvement, tail
probabilities). It is only worth building if the single-head version is
competitive at all, and this run is what decides that.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from backend import config as _config

PAIRS = _config.OPTIMUS_LEDGER_DIR / "relative_value" / "pair_labels_v1.parquet"
PANEL = _config.OPTIMUS_LEDGER_DIR / "net_panel" / "net_panel_v1.parquet"
OUT = _config.OPTIMUS_LEDGER_DIR / "relative_value"

#: Per-name state at the decision date. Everything else in the panel is a
#: FORWARD quantity and would be the answer, not a feature.
NAME_FEATURES = ["mom_21", "mom_63", "mom_252", "mom_12_1",
                 "vol_21", "vol_63", "drawdown_252", "cs_rank"]

SPEC: dict = {
    "trial_id": "RELATIVE-VALUE-NN-1",
    "licence": "PRODUCT_EXPERIMENT (screen — licenses building, never a claim)",
    "questions": [
        "Q1 is pairwise capital substitution predictable out of block at all?",
        "Q2 does a NEURAL model add anything a tree or a line does not?",
    ],
    "corpus": "relative_value/pair_labels_v1 x net_panel/net_panel_v1",
    "n_effective": "145 DATE BLOCKS — never 72,495 pairs (CANON §58)",
    "target": "improvement_net = fwd_B - fwd_A - both one-way switch costs",
    "excluded": "COST_MODEL_SENSITIVE pairs (verdict flips inside the cost band)",
    "features": ("per name: mom_21/63/252, mom_12_1, vol_21/63, drawdown_252, "
                 "cs_rank — taken for A, for B, and as B-A. Nothing forward."),
    "split": "expanding by DATE: train on all dates < d, test on date d",
    "min_train_dates": 40,
    "models": ["ridge", "lightgbm", "mlp"],
    "primary_metric": ("rank IC of predicted vs realised improvement_net, "
                       "computed WITHIN each test date then averaged over dates"),
    "decision_rule_q1": (
        "The pairwise SIGNAL is licensed iff the best model's mean rank IC "
        "survives BH-FDR at q<=0.10 across every arm in this run."),
    "decision_rule_q2": (
        "A NEURAL challenger is licensed iff the MLP beats LightGBM on the SAME "
        "test dates by more than one paired SE. If it does not, "
        "NEURAL-RELATIVE-VALUE closes as a v1 question WITH A RECEIPT and is "
        "not retried with a bigger network — an MLP that cannot beat a tree on "
        "24 tabular features is not going to be rescued by depth."),
    "g5_note": ("Order 20 §4: any registration on these labels must confront G5 "
                "by name. The distinct claim is pairwise capital SUBSTITUTION, "
                "a quantity none of G5's single-name conditional shapes "
                "contained. This screen does not make that claim — it decides "
                "whether one is worth preparing."),
}


def spec_hash() -> str:
    return hashlib.sha256(
        json.dumps(SPEC, sort_keys=True).encode()).hexdigest()[:16]


def build() -> pd.DataFrame:
    if not PAIRS.exists() or not PANEL.exists():
        sys.exit(f"REFUSED: corpus missing ({PAIRS.exists()=}, {PANEL.exists()=})")
    pairs = pd.read_parquet(PAIRS)
    panel = pd.read_parquet(PANEL)

    # The corpus already excluded these from TRAINING and counted them; doing it
    # again here is cheap and keeps this script honest on its own.
    pairs = pairs[~pairs["cost_model_sensitive"].astype(bool)]

    cols = ["date", "ticker"] + NAME_FEATURES
    p = panel[cols].copy()
    a = p.add_suffix("_a").rename(columns={"date_a": "date",
                                           "ticker_a": "incumbent"})
    b = p.add_suffix("_b").rename(columns={"date_b": "date",
                                           "ticker_b": "candidate"})
    d = (pairs.merge(a, on=["date", "incumbent"], how="inner")
              .merge(b, on=["date", "candidate"], how="inner"))
    for f in NAME_FEATURES:
        d[f"{f}_d"] = d[f"{f}_b"] - d[f"{f}_a"]
    return d.dropna(subset=["improvement_net"])


def feature_cols() -> list[str]:
    return ([f"{f}_a" for f in NAME_FEATURES]
            + [f"{f}_b" for f in NAME_FEATURES]
            + [f"{f}_d" for f in NAME_FEATURES])


def _fit_predict(name: str, Xtr, ytr, Xte):
    if name == "ridge":
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import Ridge
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        m = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                          Ridge(alpha=10.0))
        m.fit(Xtr, ytr)
        return m.predict(Xte)
    if name == "lightgbm":
        import lightgbm as lgb
        m = lgb.LGBMRegressor(n_estimators=400, learning_rate=0.05,
                              num_leaves=31, min_child_samples=100,
                              subsample=0.8, colsample_bytree=0.8,
                              random_state=0, verbose=-1)
        m.fit(Xtr, ytr)
        return m.predict(Xte)
    if name == "mlp":
        from sklearn.impute import SimpleImputer
        from sklearn.neural_network import MLPRegressor
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        m = make_pipeline(
            SimpleImputer(strategy="median"), StandardScaler(),
            MLPRegressor(hidden_layer_sizes=(64, 32), alpha=1e-3,
                         learning_rate_init=1e-3, max_iter=300,
                         early_stopping=True, n_iter_no_change=15,
                         random_state=0))
        m.fit(Xtr, ytr)
        return m.predict(Xte)
    raise ValueError(name)


def _rank_ic(pred: np.ndarray, real: np.ndarray) -> float | None:
    ok = np.isfinite(pred) & np.isfinite(real)
    if ok.sum() < 30:
        return None
    a, b = pred[ok], real[ok]
    if np.all(a == a[0]) or np.all(b == b[0]):
        return None
    return float(np.corrcoef(pd.Series(a).rank(), pd.Series(b).rank())[0, 1])


def _bh(pvals: dict, q: float = 0.10) -> dict:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m, thr = len(items), 0.0
    for i, (_k, pv) in enumerate(items, start=1):
        if pv <= i / m * q:
            thr = i / m * q
    return {k: pv <= thr for k, pv in items}


def run() -> dict:
    from scipy import stats

    print(f"spec_hash {spec_hash()}", flush=True)
    d = build()
    dates = sorted(d["date"].unique())
    feats = feature_cols()
    print(f"  {len(d):,} pairs over {len(dates)} date blocks, "
          f"{len(feats)} features", flush=True)

    ics: dict[str, list] = {m: [] for m in SPEC["models"]}
    when: dict[str, list] = {m: [] for m in SPEC["models"]}
    start = SPEC["min_train_dates"]
    for i in range(start, len(dates)):
        te_d = dates[i]
        tr = d[d["date"] < te_d]
        te = d[d["date"] == te_d]
        if len(tr) < 5000 or len(te) < 50:
            continue
        Xtr = tr[feats].to_numpy(dtype="float64")
        ytr = tr["improvement_net"].to_numpy(dtype="float64")
        Xte = te[feats].to_numpy(dtype="float64")
        yte = te["improvement_net"].to_numpy(dtype="float64")
        for m in SPEC["models"]:
            try:
                ic = _rank_ic(_fit_predict(m, Xtr, ytr, Xte), yte)
            except Exception as e:                              # noqa: BLE001
                print(f"    {m} {te_d}: {type(e).__name__}: {e}", flush=True)
                continue
            if ic is not None:
                ics[m].append(ic)
                when[m].append(str(pd.Timestamp(te_d).date()))
    for m in SPEC["models"]:
        print(f"  {m:10s} {len(ics[m])} test dates", flush=True)

    results, pvals = {}, {}
    for m, series in ics.items():
        if len(series) < 12:
            results[m] = {"n_dates": len(series), "status": "TOO_FEW_DATES"}
            continue
        a = np.array(series)
        mean = float(a.mean())
        se = float(a.std(ddof=1) / np.sqrt(len(a)))
        t = mean / se if se else 0.0
        pv = float(2 * (1 - stats.t.cdf(abs(t), df=len(a) - 1)))
        results[m] = {"n_dates": len(a), "mean_ic": round(mean, 5),
                      "se": round(se, 5), "t": round(t, 3),
                      "p_two_sided": round(pv, 5),
                      "mde_80pct_power": round(2.80 * se, 5)}
        pvals[m] = pv
    for m, ok in _bh(pvals).items():
        results[m]["bh_fdr_survives"] = bool(ok)

    def paired(x: str, y: str) -> dict | None:
        mx, my = dict(zip(when[x], ics[x])), dict(zip(when[y], ics[y]))
        common = sorted(set(mx) & set(my))
        if len(common) < 12:
            return None
        v = np.array([mx[k] - my[k] for k in common])
        se = float(v.std(ddof=1) / np.sqrt(len(v)))
        mean = float(v.mean())
        return {"n_dates": len(v), "mean_diff": round(mean, 6),
                "se": round(se, 6), "t": round(mean / se, 3) if se else 0.0,
                "beats_by_more_than_1se": bool(mean > se)}

    comps = {"mlp_vs_lightgbm": paired("mlp", "lightgbm"),
             "mlp_vs_ridge": paired("mlp", "ridge"),
             "lightgbm_vs_ridge": paired("lightgbm", "ridge")}

    q1 = [m for m, r in results.items()
          if r.get("bh_fdr_survives") and r.get("mean_ic", 0) > 0]
    mvl = comps.get("mlp_vs_lightgbm") or {}
    q2 = bool(mvl.get("beats_by_more_than_1se"))

    receipt = {
        "trial_id": SPEC["trial_id"], "spec_hash": spec_hash(), "spec": SPEC,
        "n_pairs": int(len(d)), "n_date_blocks": int(len(dates)),
        "n_effective": int(len(dates)),
        "results": results, "paired_comparisons": comps,
        "q1_signal_licensed": bool(q1), "q1_arms_passing": q1,
        "q2_neural_licensed": q2,
        "verdict": ("NEURAL_LICENSED" if (q1 and q2) else
                    "SIGNAL_ONLY" if q1 else "STOP"),
        "verdict_meaning": {
            "NEURAL_LICENSED": ("the pairwise signal survives AND the MLP beats "
                                "the tree — build the multi-head torch version"),
            "SIGNAL_ONLY": ("the pairwise signal survives but the MLP does not "
                            "beat the tree. NEURAL-RELATIVE-VALUE closes as a "
                            "v1 question; build the TREE selector instead"),
            "STOP": "nothing survived out of block; no selector is licensed",
        }[("NEURAL_LICENSED" if (q1 and q2) else "SIGNAL_ONLY" if q1 else "STOP")],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "relative_value_nn_receipt.json").write_text(
        json.dumps(receipt, indent=2, default=str), encoding="utf-8")
    return receipt


if __name__ == "__main__":
    r = run()
    print(json.dumps({k: v for k, v in r.items() if k != "spec"},
                     indent=2, default=str))
