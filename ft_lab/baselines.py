"""Baselines FIRST, on the same time split the fine-tuned models are graded on.

B0  vol prior           trailing 21-session mean |abnormal open-to-close| (no fit)
B1  trailing ridge      ridge on five trailing priors (vol, sd21, sd63, last move, dollar volume)
B2  + news metadata     B1 + number of documents / sources in the cell, pre-bell flag
B3  at-open ridge       B2 + |overnight gap| (known AT the entry open, not before it)
T1  TF-IDF ridge        text only
T2  B2 + TF-IDF         text fitted on B2's residual
T3  B3 + TF-IDF
E1  B2 + bge-small      frozen sentence embedding (if data/emb_bge.npy exists)
X1  B2 + teacher fields DeepSeek's own typed fields (event, magnitude, confidence), on the
                        cells a teacher row covers -- "do extracted fields predict size?"

Targets: ly = log(|x_oc| + 1e-4). Ridge alpha chosen on the validation block only.
Run:  ft_lab/.venv/Scripts/python.exe -m ft_lab.baselines
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from ft_lab import config as C
from ft_lab import evaluate as E
from ft_lab.dataset import META, PRIOR_AT_OPEN, PRIOR_TRAILING, assert_features_pit

ALPHAS = [0.1, 1.0, 10.0, 100.0, 1000.0]
TOP_EVENTS = 20


def _val_ic(df, col):
    r = E.ic(df, col, "y")
    return r["mean"] if r["mean"] is not None else -9


def fit_dense(cells, feats, name, tr, va, te=None):
    assert_features_pit(cells, feats)
    sc = StandardScaler().fit(cells.loc[tr, feats])
    X = sc.transform(cells[feats])
    best = None
    for a in ALPHAS:
        m = Ridge(alpha=a).fit(X[tr.values], cells.loc[tr, "ly"])
        cells[name] = m.predict(X)
        v = _val_ic(cells[va], name)
        if best is None or v > best[0]:
            best = (v, a, m)
    cells[name] = best[2].predict(X)
    return {"alpha": best[1], "val_ic": round(best[0], 4), "features": feats}


def fit_resid_sparse(cells, Xs, base, name, tr, va, feature_note):
    """Ridge on a sparse/dense text matrix predicting the residual of `base`."""
    resid = (cells["ly"] - cells[base]).values
    best = None
    for a in ALPHAS:
        m = Ridge(alpha=a).fit(Xs[tr.values], resid[tr.values])
        cells[name] = cells[base] + m.predict(Xs)
        v = _val_ic(cells[va], name)
        if best is None or v > best[0]:
            best = (v, a, m)
    cells[name] = cells[base] + best[2].predict(Xs)
    return {"alpha": best[1], "val_ic": round(best[0], 4), "on_residual_of": base,
            "features": feature_note}


def teacher_cell_features(cells: pd.DataFrame) -> pd.DataFrame:
    ext = pd.read_parquet(C.WORK / "extract.parquet")
    top = ext.loc[ext["split"] == "train", "event_type"].value_counts().index[:TOP_EVENTS].tolist()
    mag = {n: i for i, n in enumerate(C.MAG_NAMES)}
    rows = []
    for r in ext.itertuples():
        for sym, day in json.loads(r.panel_cells):
            rows.append({"symbol": sym, "entry_date": day, "t_mag": mag.get(r.magnitude_bucket, 0),
                         "t_conf": float(r.confidence or 0), "t_absdir": abs(int(r.direction or 0)),
                         "t_event": r.event_type if r.event_type in top else "other"})
    t = pd.DataFrame(rows)
    d = pd.get_dummies(t["t_event"], prefix="ev", dtype=float)
    t = pd.concat([t.drop(columns=["t_event"]), d], axis=1)
    agg = t.groupby(["symbol", "entry_date"]).max().reset_index()
    return agg


def run_fold(cells: pd.DataFrame, tr, va, te, tfidf_max=50000, use_emb=True) -> dict:
    info = {}
    cells["B0_vol_prior"] = cells["l_vol21_absx"]
    info["B1_trailing"] = fit_dense(cells, PRIOR_TRAILING, "B1_trailing", tr, va)
    info["B2_trailing_meta"] = fit_dense(cells, PRIOR_TRAILING + META, "B2_trailing_meta", tr, va)
    info["B3_at_open"] = fit_dense(cells, PRIOR_AT_OPEN + META, "B3_at_open", tr, va)
    vec = TfidfVectorizer(max_features=tfidf_max, ngram_range=(1, 2), min_df=5, sublinear_tf=True,
                          dtype=np.float32)
    vec.fit(cells.loc[tr, "text"])
    Xt = vec.transform(cells["text"])
    # T1 text only: ridge on ly directly (base = train mean)
    cells["_mean"] = float(cells.loc[tr, "ly"].mean())
    info["T1_tfidf_only"] = fit_resid_sparse(cells, Xt, "_mean", "T1_tfidf_only", tr, va, "tfidf 1-2gram")
    info["T2_trailing_meta_tfidf"] = fit_resid_sparse(cells, Xt, "B2_trailing_meta", "T2_trailing_meta_tfidf",
                                                      tr, va, "tfidf 1-2gram")
    info["T3_at_open_tfidf"] = fit_resid_sparse(cells, Xt, "B3_at_open", "T3_at_open_tfidf", tr, va,
                                                "tfidf 1-2gram")
    emb_path = C.WORK / "emb_bge.npy"
    if use_emb and emb_path.exists():
        emb = np.load(emb_path)
        keys = pd.read_parquet(C.WORK / "emb_keys.parquet")
        pos = pd.Series(np.arange(len(keys)), index=keys["symbol"] + "|" + keys["entry_date"])
        idx = pos.reindex(cells["symbol"] + "|" + cells["entry_date"]).values
        ok = ~np.isnan(idx)
        Xe = np.zeros((len(cells), emb.shape[1]), dtype=np.float32)
        Xe[ok] = emb[idx[ok].astype(int)]
        info["E1_trailing_meta_bge"] = fit_resid_sparse(cells, Xe, "B2_trailing_meta", "E1_trailing_meta_bge",
                                                        tr, va, "bge-small-en-v1.5 CLS, frozen")
    return info


def main() -> dict:
    cells = pd.read_parquet(C.WORK / "cells.parquet")
    cells = cells[cells["split"] != "embargo"].reset_index(drop=True)
    tr, va, te = (cells["split"] == s for s in ("train", "val", "test"))
    info = run_fold(cells, tr, va, te)
    preds = [c for c in ["B0_vol_prior", "B1_trailing", "B2_trailing_meta", "B3_at_open", "T1_tfidf_only",
                         "T2_trailing_meta_tfidf", "T3_at_open_tfidf", "E1_trailing_meta_bge"] if c in cells]
    test = cells[te].copy()
    res = {"primary_fold": {"fit": info, "test": E.summarize(test, preds, "B0_vol_prior")}}
    # the at-open increment is judged against the at-open prior, not the trailing one
    for p in ("T3_at_open_tfidf",):
        res["primary_fold"]["test"][p]["increment_over_at_open_prior"] = E.ic_increment(test, p, "B3_at_open")
    for p in ("T2_trailing_meta_tfidf", "E1_trailing_meta_bge"):
        if p in test:
            res["primary_fold"]["test"][p]["increment_over_B2"] = E.ic_increment(test, p, "B2_trailing_meta")
    # absolute-bucket accuracy of a regression mapped back through exp()
    for p in preds:
        res["primary_fold"]["test"][p]["abs_bucket"] = E.abs_bucket_accuracy(
            test["mag_bucket"], E.bucket_of(np.exp(test[p].values) - C.EPS) if p != "B0_vol_prior"
            else E.bucket_of(np.exp(test[p].values)))
    cells[["symbol", "entry_date", "split"] + preds].to_parquet(C.WORK / "preds_baselines.parquet", index=False)

    # ---- teacher fields: do DeepSeek's extracted fields predict size beyond the prior? ----
    tf = teacher_cell_features(cells)
    sub = cells.merge(tf, on=["symbol", "entry_date"], how="inner")
    tcols = [c for c in tf.columns if c not in ("symbol", "entry_date")]
    str_, sva, ste = (sub["split"] == s for s in ("train", "val", "test"))
    xinfo = fit_dense(sub, PRIOR_TRAILING + META, "B2_sub", str_, sva)
    xinfo2 = fit_resid_sparse(sub, StandardScaler().fit(sub.loc[str_, tcols]).transform(sub[tcols]),
                              "B2_sub", "X1_B2_teacher_fields", str_, sva, tcols)
    sub["DS_magnitude_bucket"] = sub["t_mag"] + 0.01 * sub["t_conf"]
    stest = sub[ste].copy()
    res["teacher_fields_subset"] = {
        "n_cells": {"train": int(str_.sum()), "val": int(sva.sum()), "test": int(ste.sum())},
        "fit": {"B2_sub": xinfo, "X1_B2_teacher_fields": xinfo2},
        "test": E.summarize(stest, ["B0_vol_prior", "B2_sub", "X1_B2_teacher_fields", "DS_magnitude_bucket"],
                            "B0_vol_prior"),
    }
    res["teacher_fields_subset"]["test"]["X1_B2_teacher_fields"]["increment_over_B2"] = \
        E.ic_increment(stest, "X1_B2_teacher_fields", "B2_sub")
    mag_names = np.array(C.MAG_NAMES)
    res["teacher_fields_subset"]["deepseek_zero_shot_bucket_vs_realised"] = E.abs_bucket_accuracy(
        stest["mag_bucket"], mag_names[stest["t_mag"].astype(int).clip(0, 4)])
    sub[["symbol", "entry_date", "split", "B2_sub", "X1_B2_teacher_fields", "DS_magnitude_bucket"]].to_parquet(
        C.WORK / "preds_teacher_subset.parquet", index=False)

    # ---- a second, earlier fold so there is a 2025 reading (by-year) ----
    c2 = pd.read_parquet(C.WORK / "cells.parquet")
    c2 = c2[c2["entry_date"] <= "2025-12-31"].reset_index(drop=True)
    tr2 = c2["entry_date"] <= "2025-05-31"
    va2 = (c2["entry_date"] >= "2025-06-16") & (c2["entry_date"] <= "2025-08-15")
    te2 = c2["entry_date"] >= "2025-09-02"
    info2 = run_fold(c2, tr2, va2, te2, use_emb=False)
    t2 = c2[te2].copy()
    p2 = ["B0_vol_prior", "B2_trailing_meta", "B3_at_open", "T2_trailing_meta_tfidf", "T3_at_open_tfidf"]
    res["early_fold_2025"] = {"train": "2025-01-02..2025-05-31", "val": "2025-06-16..2025-08-15",
                              "test": "2025-09-02..2025-12-31", "fit": info2,
                              "test_results": E.summarize(t2, p2, "B0_vol_prior")}
    res["early_fold_2025"]["test_results"]["T2_trailing_meta_tfidf"]["increment_over_B2"] = \
        E.ic_increment(t2, "T2_trailing_meta_tfidf", "B2_trailing_meta")

    rec = {"job": "ft_lab.baselines", "licence": C.LICENCE,
           "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "target": "ly = log(|x_oc| + 1e-4); IC = per-date Spearman vs |x_oc|, SE over weekly blocks",
           **res}
    C.RECEIPTS.mkdir(parents=True, exist_ok=True)
    (C.RECEIPTS / "baselines.json").write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    return rec


def headline(rec: dict) -> str:
    lines = []
    t = rec["primary_fold"]["test"]
    for k, v in t.items():
        a = v["ic_abs_move"]
        inc = v.get("increment_over_prior", {})
        lines.append(f"{k:28s} IC {a['mean']:+.4f} (t {a['t']}, MDE {a['mde']}) rel {v['ic_relative_move']['mean']:+.4f}"
                     f"  terc {v['tercile']['accuracy']}  inc {inc.get('mean')} t {inc.get('t')}")
    return "\n".join(lines)


if __name__ == "__main__":
    r = main()
    print(headline(r))
