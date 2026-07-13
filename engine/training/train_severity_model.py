"""
TRIAL-CRASH-2 — Drawdown-severity (exceedance) model trainer + evaluator
==========================================================================

Implements EXACTLY the frozen protocol in
docs/TRIALS/TRIAL-CRASH-2-severity-model.md (pre-registered 2026-07-14,
commit fe6edf3, BEFORE this file first ran). Any change to the protocol
constants below invalidates the trial — see the doc's amendment rules.

    python -m engine.training.train_severity_model

Output: engine/training/output/crash2_eval_<date>.json + console verdict.
The model deploys NOTHING by itself; an ADOPT verdict only earns a
descriptive surface + forward clock (separate, attended step).
"""

import sys
import json
import logging
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("crash2")

# ── Frozen protocol constants (mirror the trial doc; do not tune) ──────────
THRESHOLDS = [0.05, 0.10, 0.15, 0.20]
HORIZONS_TD = {"30d": 21, "60d": 42, "90d": 63}
DENSE_CELLS = [(x, h) for x in (0.05, 0.10) for h in ("30d", "60d", "90d")]
N_FOLDS = 5
VAL_YEARS = 10
PURGE_TD = 63
EMBARGO_TD = 21
STLFSI4_PUB_LAG_DAYS = 7  # conservative publication lag before a reading is usable
LGB_PARAMS = dict(n_estimators=400, learning_rate=0.05, max_depth=4,
                  min_child_samples=100, deterministic=True,
                  force_row_wise=True, random_state=42, verbosity=-1)
MIN_TRAIN_POS = 10  # fewer positives than this → cell-fold recorded insufficient

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def forward_max_drawdown(close: pd.Series, h_td: int) -> pd.Series:
    """maxDD(t,h) = min(close[t+1..t+h]) / close[t] - 1 (trial doc definition)."""
    arr = close.to_numpy(dtype=float)
    n = len(arr)
    out = np.full(n, np.nan)
    for i in range(n - h_td):
        out[i] = arr[i + 1:i + 1 + h_td].min() / arr[i] - 1.0
    return pd.Series(out, index=close.index)


def fetch_inputs():
    from backend.config import config, api_keys
    from backend.services.data_fetcher import DataFetcher, fetch_safe

    fetcher = DataFetcher()
    data, _sectors = fetcher.fetch_market_data()
    fred_data = fetcher.fetch_fred_data()

    from engine.training.features import build_feature_matrix
    features = build_feature_matrix(data, fred_data=fred_data)

    start = config["data"]["training_start"]
    end = (pd.Timestamp.today() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    spy = fetch_safe("SPY", start, end, "SPY")
    if spy is None or spy.empty:
        raise RuntimeError("SPY fetch failed — cannot build labels")
    spy = spy.tz_localize(None) if getattr(spy.index, "tz", None) is not None else spy

    from fredapi import Fred
    stl = Fred(api_key=api_keys.fred).get_series("STLFSI4")
    stl.index = pd.to_datetime(stl.index) + pd.Timedelta(days=STLFSI4_PUB_LAG_DAYS)

    return features, spy, stl


def build_dataset(features: pd.DataFrame, spy: pd.Series, stl: pd.Series):
    idx = features.index.intersection(spy.index)
    features = features.loc[idx]
    spy = spy.loc[idx]

    labels = {}
    for hname, h_td in HORIZONS_TD.items():
        mdd = forward_max_drawdown(spy, h_td)
        for x in THRESHOLDS:
            labels[(x, hname)] = (mdd <= -x).astype(float).where(mdd.notna())

    stl_daily = stl.reindex(idx.union(stl.index)).ffill().reindex(idx)
    return features, spy, labels, stl_daily


def make_folds(idx: pd.DatetimeIndex, max_label_td: int):
    """Expanding walk-forward: 5 contiguous validation blocks over the final
    VAL_YEARS, train = everything before block minus purge+embargo."""
    usable = idx[:len(idx) - max_label_td]  # dates whose labels are defined
    val_start_date = usable[-1] - pd.DateOffset(years=VAL_YEARS)
    val_positions = np.where(usable >= val_start_date)[0]
    blocks = np.array_split(val_positions, N_FOLDS)
    folds = []
    for block in blocks:
        if len(block) == 0:
            continue
        train_end = block[0] - (PURGE_TD + EMBARGO_TD)
        if train_end < 500:
            continue
        folds.append((np.arange(0, train_end), block))
    return usable, folds


def evaluate():
    from lightgbm import LGBMClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score

    logger.info("Fetching inputs (market, FRED, SPY, STLFSI4)...")
    features, spy, labels, stl = build_dataset(*fetch_inputs())
    usable, folds = make_folds(features.index, max(HORIZONS_TD.values()))
    logger.info("Dataset: %d rows (%s to %s), %d features, %d folds",
                len(usable), usable[0].date(), usable[-1].date(),
                features.shape[1], len(folds))

    X = features.loc[usable]
    stl_u = stl.loc[usable]

    # Collect pooled validation predictions per cell.
    pooled = {cell: {"y": [], "p_model": [], "p_clim": [], "p_stl": [],
                     "dates": []} for cell in labels}
    insufficiencies = []

    for k, (train_pos, val_pos) in enumerate(folds, 1):
        tr_idx, va_idx = usable[train_pos], usable[val_pos]
        logger.info("Fold %d: train %s..%s (%d) | val %s..%s (%d)",
                    k, tr_idx[0].date(), tr_idx[-1].date(), len(tr_idx),
                    va_idx[0].date(), va_idx[-1].date(), len(va_idx))

        # Per-date prediction cube for monotonicity enforcement.
        cube = {}
        for cell, y_all in labels.items():
            y_tr = y_all.loc[tr_idx].dropna()
            y_va = y_all.loc[va_idx].dropna()
            if len(y_va) == 0:
                continue
            n_pos = int(y_tr.sum())
            if n_pos < MIN_TRAIN_POS or y_tr.nunique() < 2:
                insufficiencies.append({"fold": k, "cell": str(cell),
                                        "train_pos": n_pos})
                continue

            Xtr, Xva = X.loc[y_tr.index], X.loc[y_va.index]
            model = LGBMClassifier(**LGB_PARAMS)
            model.fit(Xtr, y_tr)
            cube[cell] = pd.Series(model.predict_proba(Xva)[:, 1],
                                   index=y_va.index)

            # Baseline 1: climatology (train base rate, constant).
            p_clim = float(y_tr.mean())
            # Baseline 2: STLFSI4-only logistic (median-fill within train).
            s_tr = stl_u.loc[y_tr.index].astype(float)
            med = float(np.nanmedian(s_tr))
            s_tr = s_tr.fillna(med).to_numpy().reshape(-1, 1)
            s_va = stl_u.loc[y_va.index].astype(float).fillna(med) \
                .to_numpy().reshape(-1, 1)
            lr = LogisticRegression(max_iter=1000)
            lr.fit(s_tr, y_tr)
            p_stl = lr.predict_proba(s_va)[:, 1]

            pooled[cell]["y"].append(y_va.to_numpy())
            pooled[cell]["p_clim"].append(np.full(len(y_va), p_clim))
            pooled[cell]["p_stl"].append(p_stl)
            pooled[cell]["dates"].append(y_va.index)

        # Monotonicity enforcement (part of the model under evaluation):
        # P(>=5) >= P(>=10) >= P(>=15) >= P(>=20), then P(x,30) <= P(x,60) <= P(x,90).
        if cube:
            common = None
            for s in cube.values():
                common = s.index if common is None else common.intersection(s.index)
            for hname in HORIZONS_TD:
                prev = None
                for x in THRESHOLDS:
                    if (x, hname) not in cube:
                        prev = None
                        continue
                    cur = cube[(x, hname)].loc[common]
                    if prev is not None:
                        cur = np.minimum(cur, prev)
                    cube[(x, hname)] = cur
                    prev = cur
            for x in THRESHOLDS:
                prev = None
                for hname in ("30d", "60d", "90d"):
                    if (x, hname) not in cube:
                        prev = None
                        continue
                    cur = cube[(x, hname)]
                    if prev is not None:
                        cur = np.maximum(cur, prev)
                    cube[(x, hname)] = cur
                    prev = cur
            for cell, s in cube.items():
                y_va = labels[cell].loc[s.index].dropna()
                pooled[cell]["p_model"].append(
                    pd.Series(s, index=s.index).loc[y_va.index].to_numpy())

    # ── Pooled metrics per cell ──────────────────────────────────────────
    def brier(p, y):
        return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))

    results = {}
    for cell, d in pooled.items():
        if not d["p_model"]:
            results[str(cell)] = {"status": "insufficient_events"}
            continue
        y = np.concatenate(d["y"])
        pm = np.concatenate(d["p_model"])
        pc = np.concatenate(d["p_clim"])
        ps = np.concatenate(d["p_stl"])
        n = min(len(y), len(pm))  # alignment guard (mono pass intersects dates)
        y, pm, pc, ps = y[:n], pm[:n], pc[:n], ps[:n]
        bm, bc, bs = brier(pm, y), brier(pc, y), brier(ps, y)
        res = {
            "n": int(n), "n_pos": int(y.sum()),
            "prevalence": round(float(y.mean()), 4),
            "brier_model": round(bm, 6), "brier_climatology": round(bc, 6),
            "brier_stlfsi4": round(bs, 6),
            "skill_vs_climatology": round(1 - bm / bc, 4) if bc > 0 else None,
            "skill_vs_stlfsi4": round(1 - bm / bs, 4) if bs > 0 else None,
        }
        if y.sum() > 0 and y.sum() < n:
            res["pr_auc_model"] = round(float(average_precision_score(y, pm)), 4)
            res["pr_auc_stlfsi4"] = round(float(average_precision_score(y, ps)), 4)
        results[str(cell)] = res

    # ── The pre-registered gate ─────────────────────────────────────────
    gate_cells = {}
    for cell in DENSE_CELLS:
        r = results.get(str(cell), {})
        ok = (r.get("skill_vs_climatology") is not None
              and r["skill_vs_climatology"] > 0
              and r.get("skill_vs_stlfsi4") is not None
              and r["skill_vs_stlfsi4"] > 0)
        gate_cells[str(cell)] = bool(ok)
    verdict = "ADOPT" if all(gate_cells.values()) else "REJECT"

    report = {
        "trial": "TRIAL-CRASH-2",
        "protocol_doc": "docs/TRIALS/TRIAL-CRASH-2-severity-model.md",
        "run_date": date.today().isoformat(),
        "n_folds_run": len(folds),
        "cells": results,
        "dense_gate": gate_cells,
        "insufficient_cells": insufficiencies,
        "verdict": verdict,
        "verdict_meaning": ("ADOPT = earns a descriptive UI surface + forward "
                            "clock only; REJECT = stays dark, published in "
                            "NEGATIVE_RESULTS. Never arms a lane either way."),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"crash2_eval_{date.today().isoformat()}.json"
    out_path.write_text(json.dumps(report, indent=2))

    logger.info("=" * 64)
    for cell in labels:
        r = results.get(str(cell), {})
        logger.info("%-18s %s", str(cell), json.dumps(r))
    logger.info("DENSE GATE: %s", gate_cells)
    logger.info("VERDICT: %s  (report: %s)", verdict, out_path)
    logger.info("=" * 64)
    return report


if __name__ == "__main__":
    evaluate()
