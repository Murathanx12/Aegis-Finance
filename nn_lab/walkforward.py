"""Walk-forward evaluation -- the only kind nn_lab reports.

    python -m nn_lab.walkforward [--folds 2020,2021] [--seeds 3] [--no-lgbm]

Expanding train | 63-session embargo | 26-date validation | 63-session embargo |
one calendar test year. Hyperparameters are fixed in code before any fold is
fit; the validation block is used ONLY for early stopping and for the Platt map
from score to probability. Nothing is tuned on a test block.
"""
from __future__ import annotations

import argparse
import json
import secrets
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from nn_lab import config as C
from nn_lab import evaluate as E
from nn_lab import models as M
from nn_lab import seeds as S
from nn_lab.splits import check_fold, walk_forward_folds
from nn_lab.table import GROUPS

H = C.HORIZONS


def _sha(p) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_table(cols_extra=()) -> pd.DataFrame:
    feats = [c for g in GROUPS.values() for c in g]
    cols = ["date", "symbol", "med_dv", "on_grid", "dead"] + feats + [f"y_{h}" for h in H] + list(cols_extra)
    df = pd.read_parquet(C.TABLE_PATH, columns=cols)
    df = df[df["on_grid"]].sort_values(["date", "symbol"], kind="mergesort").reset_index(drop=True)
    return df


def residual_score(df: pd.DataFrame, score: np.ndarray) -> np.ndarray:
    """Score minus its per-date OLS projection on ranked (mom_12_1, beta_63, vol_63, dv_log)."""
    ctrl = ["mom_12_1", "beta_63", "vol_63", "dv_log"]
    R = M.rank_gauss(df, ctrl)
    R = np.where(np.isnan(R), 0.0, R)
    out = np.full(len(df), np.nan)
    codes = df["date"].values
    s = pd.Series(score)
    for d, idx in df.groupby("date").indices.items():
        y = s.values[idx]
        m = np.isfinite(y)
        if m.sum() < 30:
            continue
        X = np.c_[np.ones(m.sum()), R[idx][m]]
        beta, *_ = np.linalg.lstsq(X, y[m], rcond=None)
        r = np.full(len(idx), np.nan)
        r[m] = y[m] - X @ beta
        out[idx] = r
    return out


def run(folds_filter=None, n_seeds: int = 3, do_lgbm: bool = True, do_nn: bool = True,
        run_id: str | None = None) -> dict:
    t0 = time.time()
    run_id = run_id or f"wf_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    df = load_table()
    cal = pd.DatetimeIndex(pd.read_parquet(C.TABLE_PATH.parent / "calendar.parquet")["date"])
    all_groups = list(GROUPS)
    Xall, xnames = M.design_matrix(df, all_groups)
    Yw = np.column_stack([M.winsorize_by_date(df, f"y_{h}") for h in H])
    Yraw = df[[f"y_{h}" for h in H]].values.astype("float32")
    codes = pd.factorize(df["date"])[0]
    folds = walk_forward_folds(df["date"].unique(), cal)
    if folds_filter:
        folds = [f for f in folds if f.name in folds_filter]
    seeds_used = []
    fold_log, oos_parts = [], []
    for f in folds:
        check_fold(f, cal)
        tr = df["date"].isin(f.train).values
        va = df["date"].isin(f.val).values
        te = df["date"].isin(f.test).values
        groups = M.active_groups(df.loc[tr])
        cols = [i for i, n in enumerate(xnames)
                if any(n in GROUPS[g] or n == f"missing_{g}" for g in groups)]
        X = Xall[:, cols]
        feats_raw = M.feature_list(groups)
        o = df.loc[te, ["date", "symbol", "med_dv", "dead", "mom_12_1", "vol_63"] + [f"y_{h}" for h in H]].copy()
        info = {"fold": f.name, "train_dates": [str(f.train[0].date()), str(f.train[-1].date()), len(f.train)],
                "val_dates": [str(f.val[0].date()), str(f.val[-1].date()), len(f.val)],
                "test_dates": [str(f.test[0].date()), str(f.test[-1].date()), len(f.test)],
                "train_rows": int(tr.sum()), "test_rows": int(te.sum()), "groups": groups}
        for j, h in enumerate(H):
            yv = Yraw[va, j]
            # momentum
            mv = df.loc[va, "mom_12_1"].values
            o[f"mom_score_{h}"] = o["mom_12_1"].values
            ok = np.isfinite(mv)
            o[f"mom_prob_{h}"] = M.platt(mv[ok], yv[ok])(np.nan_to_num(o["mom_12_1"].values, nan=np.nanmedian(mv)))
            # ridge
            rg = M.fit_ridge(X[tr], Yw[tr, j])
            o[f"ridge_score_{h}"] = rg.predict(X[te])
            o[f"ridge_prob_{h}"] = M.platt(rg.predict(X[va]), yv)(o[f"ridge_score_{h}"].values)
            # lightgbm
            if do_lgbm:
                sd = 1000 + j
                lg = M.fit_lgbm(df.loc[tr, feats_raw], Yw[tr, j], seed=sd)
                o[f"lgbm_score_{h}"] = lg.predict(df.loc[te, feats_raw])
                o[f"lgbm_prob_{h}"] = M.platt(lg.predict(df.loc[va, feats_raw]), yv)(o[f"lgbm_score_{h}"].values)
            # trailing-vol magnitude baseline (the 'zero' distribution)
            sig = df.loc[te, "vol_63"].values * np.sqrt(h / 252.0)
            o[f"vol_sigma_{h}"] = sig
            # F8: the FAIR magnitude baseline is a fitted linear risk model, not one
            # trailing vol: ridge of |y| on the same ranked features
            ra = M.fit_ridge(X[tr], np.abs(Yw[tr, j]))
            o[f"ridgeabs_score_{h}"] = ra.predict(X[te])
        if do_nn:
            from nn_lab.nn import Trainer, ensemble_predict
            for variant in ("dist", "rank"):
                trs, hist = [], []
                for k in range(n_seeds):
                    sd = S.draw(1)[0]
                    seeds_used.append(sd)
                    t = Trainer(X.shape[1], seed=sd, variant=variant)
                    hist.append(t.fit(X[tr], Yw[tr], codes[tr], X[va], Yraw[va], codes[va]))
                    trs.append(t)
                p = ensemble_predict(trs, X[te])
                for j, h in enumerate(H):
                    o[f"nn{variant}_score_{h}"] = p["mean"][:, j]
                    o[f"nn{variant}_prob_{h}"] = p["prob"][:, j]
                    for qi, tau in enumerate((5, 25, 50, 75, 95)):
                        o[f"nn{variant}_q{tau:02d}_{h}"] = p["q"][:, j, qi]
                info[f"nn_{variant}"] = [{k: v for k, v in r.items() if k != "history"} | {
                    "val_ic_by_epoch": [e["val_ic"] for e in r["history"]]} for r in hist]
                del trs
        info["elapsed_s"] = round(time.time() - t0, 1)
        fold_log.append(info)
        oos_parts.append(o)
        print(json.dumps({"fold": f.name, "elapsed_s": info["elapsed_s"]}), flush=True)
    oos = pd.concat(oos_parts, ignore_index=True)
    out_dir = C.OUT / "walkforward"
    out_dir.mkdir(parents=True, exist_ok=True)
    oos.to_parquet(out_dir / f"oos_{run_id}.parquet", index=False)
    S.record(seeds_used, source=run_id)
    rec = summarise(oos, cal, df_ctrl=df)
    rec.update({"artefact": "NN_LAB_WALKFORWARD", "run_id": run_id, "licence": "PRODUCT_EXPERIMENT",
                "folds": fold_log, "n_seeds_per_variant": n_seeds, "seeds_used": seeds_used,
                "oos_path": str(out_dir / f"oos_{run_id}.parquet"),
                "elapsed_s": round(time.time() - t0, 1),
                "survivorship_caveat": "PARTIALLY SURVIVOR-SELECTED (see table receipt): living names chosen "
                                       "alive 2026-09-01; dead names from the inactive listed list only.",
                "post_review": True,
                "review_fixes": "F1 no market-cap features without an unadjusted close, no adjusted price floor; "
                                "F2 no missing-indicator for later-pull groups, analyst unavailable before its "
                                "first snapshot; F9 latest period end on a shared filing date; F8 ridge |y| baseline",
                "table_sha256": _sha(C.TABLE_PATH),
                "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    C.RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    (C.RECEIPT_DIR / f"{run_id}.json").write_text(json.dumps(rec, indent=1, default=str))
    return rec


def summarise(oos: pd.DataFrame, cal: pd.DatetimeIndex, df_ctrl: pd.DataFrame | None = None) -> dict:
    models = sorted({c.split("_score_")[0] for c in oos.columns if "_score_" in c})
    res = {"models": {}, "magnitude": {}, "intervals": {}}
    if df_ctrl is not None:
        ctrl = df_ctrl.merge(oos[["date", "symbol"]], on=["date", "symbol"], how="right")
    for h in H:
        y = f"y_{h}"
        for m in models:
            sc = f"{m}_score_{h}"
            if sc not in oos:
                continue
            ic = E.per_date_ic(oos, sc, y)
            sp = E.topk_series(oos, sc, y)
            ic_s = E.block_stats(ic, cal, h)
            sp_s = E.block_stats(sp["spread"], cal, h)
            views_sp = E.year_views(sp["spread"], cal, h)
            views_ic = E.year_views(ic, cal, h)
            resid = None
            if df_ctrl is not None and m != "mom":
                o2 = oos[["date", "symbol", y]].copy()
                o2["r"] = residual_score(ctrl, oos[sc].values)
                resid = E.block_stats(E.per_date_ic(o2, "r", y), cal, h)
            pr = f"{m}_prob_{h}"
            rel = {}
            if pr in oos:
                rel = E.reliability(oos[pr].values[np.isfinite(oos[y].values)],
                                    (oos[y].values[np.isfinite(oos[y].values)] > 0).astype(float))
            res["models"].setdefault(m, {})[f"h{h}"] = {
                "rank_ic": ic_s, "rank_ic_by_year": views_ic.get("by_hold_year"),
                "rank_ic_loyo_worst": views_ic.get("loyo_worst"),
                "top20_minus_random_net": sp_s,
                "top20_gross_mean": round(float(sp["gross_top"].mean()), 5) if len(sp) else None,
                "top20_views": views_sp, "residual_ic_vs_mom_beta_vol_size": resid,
                "probability": {k: v for k, v in rel.items() if k != "table"},
                "reliability_table": rel.get("table"),
                "verdict": E.verdict(ic_s, sp_s, views_sp, resid),
                "reliability_weight": E.reliability_weight(ic_s.get("t")),
            }
        # magnitude: does the predicted spread rank |y|?
        absy = oos[y].abs()
        tmp = oos[["date"]].copy()
        tmp["absy"] = absy
        tmp["vol"] = oos[f"vol_sigma_{h}"]
        ic_vol = E.per_date_ic(tmp, "vol", "absy")
        res["magnitude"][f"h{h}"] = {"trailing_vol_ic_with_abs_y": E.block_stats(ic_vol, cal, h)}
        if f"ridgeabs_score_{h}" in oos:
            tmp["ra"] = oos[f"ridgeabs_score_{h}"]
            ic_ra = E.per_date_ic(tmp, "ra", "absy")
            res["magnitude"][f"h{h}"]["ridgeabs_ic_with_abs_y"] = E.block_stats(ic_ra, cal, h)
            res["magnitude"][f"h{h}"]["ridge_abs_minus_vol"] = E.block_stats(
                (ic_ra - ic_vol).dropna(), cal, h)
        z50, z90 = 0.6745, 1.6449
        res["intervals"][f"h{h}"] = {
            "trailing_vol_around_zero": {
                "cov50": E.coverage(oos[y], -z50 * oos[f"vol_sigma_{h}"], z50 * oos[f"vol_sigma_{h}"]),
                "cov90": E.coverage(oos[y], -z90 * oos[f"vol_sigma_{h}"], z90 * oos[f"vol_sigma_{h}"])}}
        for v in ("nndist", "nnrank"):
            if f"{v}_q05_{h}" in oos:
                tmp["nnsig"] = oos[f"{v}_q95_{h}"] - oos[f"{v}_q05_{h}"]
                ic_nn = E.per_date_ic(tmp, "nnsig", "absy")
                res["magnitude"][f"h{h}"][f"{v}_width_ic_with_abs_y"] = E.block_stats(ic_nn, cal, h)
                res["magnitude"][f"h{h}"][f"{v}_width_minus_vol"] = E.block_stats((ic_nn - ic_vol).dropna(), cal, h)
                res["intervals"][f"h{h}"][v] = {
                    "cov50": E.coverage(oos[y], oos[f"{v}_q25_{h}"], oos[f"{v}_q75_{h}"]),
                    "cov90": E.coverage(oos[y], oos[f"{v}_q05_{h}"], oos[f"{v}_q95_{h}"])}
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", default="")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--no-lgbm", action="store_true")
    ap.add_argument("--no-nn", action="store_true")
    ap.add_argument("--run-id", default=None)
    a = ap.parse_args()
    ff = [x for x in a.folds.split(",") if x]
    rec = run(ff or None, n_seeds=a.seeds, do_lgbm=not a.no_lgbm, do_nn=not a.no_nn, run_id=a.run_id)
    brief = {m: {h: {"ic": v["rank_ic"]["mean"], "t": v["rank_ic"]["t"],
                     "spread": v["top20_minus_random_net"]["mean"], "verdict": v["verdict"]}
                 for h, v in d.items()} for m, d in rec["models"].items()}
    print(json.dumps(brief, indent=1))
