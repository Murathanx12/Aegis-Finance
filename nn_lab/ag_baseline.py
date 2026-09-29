"""AutoGluon-Tabular as a second strong baseline (coordinator request, 2026-09-28).

    python -m nn_lab.ag_baseline [--time-limit 600] [--max-train-rows 400000]

Same walk-forward folds, embargo and raw features as LightGBM in walkforward.py.
h = 21 only (the budget: 7 folds x 10 minutes). Training rows are subsampled to
`max_train_rows` (seeded, recorded) to stay inside the ~3 GB memory budget; the
validation block is passed as AutoGluon's tuning data (strictly earlier than
test, as for every other model). KNN is excluded (memory). The probability comes
from the same validation-block Platt map as the other baselines.
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from nn_lab import config as C
from nn_lab import evaluate as E
from nn_lab import models as M
from nn_lab import seeds as S
from nn_lab.splits import check_fold, walk_forward_folds
from nn_lab.walkforward import load_table, residual_score

H = 21


def run(time_limit: int, max_train_rows: int, run_id: str) -> dict:
    from autogluon.tabular import TabularPredictor
    t0 = time.time()
    df = load_table()
    cal = pd.DatetimeIndex(pd.read_parquet(C.TABLE_PATH.parent / "calendar.parquet")["date"])
    y = f"y_{H}"
    df["yw"] = M.winsorize_by_date(df, y)
    folds = walk_forward_folds(df["date"].unique(), cal)
    seed = S.draw(1)[0]
    S.record([seed], source=run_id)
    rng = np.random.default_rng(seed)
    parts, log = [], []
    for f in folds:
        check_fold(f, cal)
        tr = df["date"].isin(f.train).values & df["yw"].notna().values
        va = df["date"].isin(f.val).values & df["yw"].notna().values
        te = df["date"].isin(f.test).values
        groups = M.active_groups(df.loc[df["date"].isin(f.train)])
        feats = M.feature_list(groups)
        idx = np.flatnonzero(tr)
        if len(idx) > max_train_rows:
            idx = np.sort(rng.choice(idx, size=max_train_rows, replace=False))
        path = C.LOCAL_PC / f"ag_{run_id}_{f.name}"
        pred = TabularPredictor(label="yw", problem_type="regression", eval_metric="root_mean_squared_error",
                                path=str(path), verbosity=0)
        pred.fit(df.iloc[idx][feats + ["yw"]], tuning_data=df.loc[va, feats + ["yw"]],
                 time_limit=time_limit, presets="medium_quality",
                 excluded_model_types=["KNN"], use_bag_holdout=False)
        o = df.loc[te, ["date", "symbol", "med_dv", y, "mom_12_1", "beta_63", "vol_63", "dv_log"]].copy()
        o["ag_score"] = pred.predict(df.loc[te, feats]).values
        sv = pred.predict(df.loc[va, feats]).values
        o["ag_prob"] = M.platt(sv, df.loc[va, y].values)(o["ag_score"].values)
        lb = pred.leaderboard(silent=True)
        log.append({"fold": f.name, "train_rows_used": int(len(idx)), "groups": groups,
                    "best_model": str(pred.model_best),
                    "models": lb[["model", "score_val"]].head(6).to_dict("records"),
                    "elapsed_s": round(time.time() - t0, 1)})
        parts.append(o)
        shutil.rmtree(path, ignore_errors=True)
        print(json.dumps(log[-1], default=str), flush=True)
    oos = pd.concat(parts, ignore_index=True)
    ic = E.per_date_ic(oos, "ag_score", y)
    sp = E.topk_series(oos, "ag_score", y)
    o2 = oos[["date", "symbol", y]].copy()
    o2["r"] = residual_score(oos, oos["ag_score"].values)
    resid = E.block_stats(E.per_date_ic(o2, "r", y), cal, H)
    ic_s, sp_s = E.block_stats(ic, cal, H), E.block_stats(sp["spread"], cal, H)
    views = E.year_views(sp["spread"], cal, H)
    m = np.isfinite(oos[y].values)
    rel = E.reliability(oos["ag_prob"].values[m], (oos[y].values[m] > 0).astype(float))
    rec = {"artefact": "NN_LAB_AUTOGLUON_BASELINE", "run_id": run_id, "horizon": H,
           "time_limit_s_per_fold": time_limit, "max_train_rows": max_train_rows, "subsample_seed": seed,
           "rank_ic": ic_s, "rank_ic_by_year": E.year_views(ic, cal, H).get("by_hold_year"),
           "top20_minus_random_net": sp_s, "top20_views": views,
           "residual_ic_vs_mom_beta_vol_size": resid,
           "probability": {k: v for k, v in rel.items() if k != "table"},
           "verdict": E.verdict(ic_s, sp_s, views, resid), "folds": log,
           "elapsed_s": round(time.time() - t0, 1),
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (C.RECEIPT_DIR / f"{run_id}.json").write_text(json.dumps(rec, indent=1, default=str))
    return rec


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--time-limit", type=int, default=600)
    ap.add_argument("--max-train-rows", type=int, default=400_000)
    ap.add_argument("--run-id", default=f"ag_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}")
    a = ap.parse_args()
    r = run(a.time_limit, a.max_train_rows, a.run_id)
    print(json.dumps({k: r[k] for k in ("rank_ic", "top20_minus_random_net", "verdict")}, indent=1))
