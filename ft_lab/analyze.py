"""Grade everything the first run produced; write backend/data/optimus/ft_lab/receipts/first_run.json.

A. SIZE   fine-tuned Qwen-0.5B regression head: test IC of B2 + a*lm (a fitted on val), its
          increment over B2 and over the TF-IDF / bge baselines, by month.
B. EXTRACTION agreement with the DeepSeek teacher on held-out test documents: base zero-shot
          vs student. Agreement measures mimicry, not truth.
C. PSYCH -> SIZE  do news-psychology fields predict size beyond the numeric prior?
          C1 DeepSeek fields: fit on 2,500 train cells, grade on 1,000 test cells
          C2 student fields: fit on the validation sample, grade on the test sample
          plus each model's own expected_move bucket as a zero-shot size forecast
D. SPEED and COST: pages/minute locally vs DeepSeek dollars per 1,000 pages.
With small samples the IC is computed per WEEK (pooled cells) and its SE over weeks.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import cohen_kappa_score
from sklearn.preprocessing import StandardScaler

from ft_lab import config as C
from ft_lab import evaluate as E
from ft_lab import prompts as P

MAG_I = {n: i for i, n in enumerate(C.MAG_NAMES)}


def weekly_ic(df, pred, target="y"):
    per = {}
    for w, g in df.groupby("week"):
        g = g[[pred, target]].dropna()
        if len(g) >= 6 and g[pred].nunique() > 1:
            per[w] = spearmanr(g[pred], g[target]).statistic
    s = pd.Series(per, dtype=float)
    n = len(s)
    se = float(s.std(ddof=1) / np.sqrt(n)) if n > 1 else None
    m = float(s.mean()) if n else None
    return {"mean": None if m is None else round(m, 4), "se": None if se is None else round(se, 4),
            "t": None if not se else round(m / se, 2), "mde": None if se is None else round(2.8 * se, 4),
            "n_weeks": n, "n_cells": int(df[[pred, target]].dropna().shape[0])}


def weekly_increment(df, a, b, target="y"):
    ra, rb = {}, {}
    for w, g in df.groupby("week"):
        g = g[[a, b, target]].dropna()
        if len(g) >= 6 and g[a].nunique() > 1 and g[b].nunique() > 1:
            ra[w] = spearmanr(g[a], g[target]).statistic
            rb[w] = spearmanr(g[b], g[target]).statistic
    d = pd.Series(ra) - pd.Series(rb)
    n = len(d)
    se = float(d.std(ddof=1) / np.sqrt(n)) if n > 1 else None
    m = float(d.mean()) if n else None
    return {"mean": None if m is None else round(m, 4), "se": None if se is None else round(se, 4),
            "t": None if not se else round(m / se, 2), "mde": None if se is None else round(2.8 * se, 4),
            "n_weeks": n}


def base_frame():
    cells = pd.read_parquet(C.WORK / "cells.parquet", columns=["symbol", "entry_date", "split", "y", "ly", "rel",
                                                               "week", "month", "mag_bucket"])
    pb = pd.read_parquet(C.WORK / "preds_baselines.parquet")
    return cells.merge(pb.drop(columns=["split"]), on=["symbol", "entry_date"], how="inner")


# ------------------------------------------------------------------ A. size head
def grade_size(df):
    p = C.WORK / "preds_lm_size.parquet"
    if not p.exists():
        return {"status": "NOT_RUN"}
    lm = pd.read_parquet(p)
    d = df.merge(lm.drop(columns=["split"]), on=["symbol", "entry_date"], how="inner")
    va, te = d[d["split"] == "val"], d[d["split"] == "test"].copy()
    reg = LinearRegression().fit(va[["lm_size"]], va["ly"] - va["B2_trailing_meta"])
    te["LM_B2_plus_qwen05"] = te["B2_trailing_meta"] + reg.coef_[0] * te["lm_size"] + reg.intercept_
    te["LM_alone"] = te["lm_size"]
    out = E.summarize(te, ["B0_vol_prior", "B2_trailing_meta", "T2_trailing_meta_tfidf", "E1_trailing_meta_bge",
                           "LM_alone", "LM_B2_plus_qwen05"], "B0_vol_prior")
    out["LM_B2_plus_qwen05"]["increment_over_B2"] = E.ic_increment(te, "LM_B2_plus_qwen05", "B2_trailing_meta")
    out["LM_B2_plus_qwen05"]["increment_over_T2_tfidf"] = E.ic_increment(te, "LM_B2_plus_qwen05", "T2_trailing_meta_tfidf")
    out["LM_B2_plus_qwen05"]["increment_over_E1_bge"] = E.ic_increment(te, "LM_B2_plus_qwen05", "E1_trailing_meta_bge")
    out["LM_B2_plus_qwen05"]["abs_bucket"] = E.abs_bucket_accuracy(
        te["mag_bucket"], E.bucket_of(np.exp(te["LM_B2_plus_qwen05"].values) - C.EPS))
    out["_val_fit"] = {"coef": round(float(reg.coef_[0]), 4), "intercept": round(float(reg.intercept_), 4),
                       "n_val": int(len(va)), "n_test": int(len(te))}
    log = C.MODELS / "size_qwen05_lora" / "train_log.json"
    if log.exists():
        L = json.loads(log.read_text(encoding="utf-8"))
        out["_train"] = {k: L.get(k) for k in ("n_train", "stopped", "steps", "best", "awake_min", "train_rate_per_s",
                                               "peak_vram_mib", "evals")}
    sl = C.MODELS / "size_qwen05_lora" / "score_log.json"
    if sl.exists():
        out["_score"] = json.loads(sl.read_text(encoding="utf-8"))
    return out


# ------------------------------------------------------------------ B. extraction agreement
def _read_gen(name):
    p = C.WORK / f"gen_{name}.jsonl"
    return pd.read_json(p, lines=True) if p.exists() else None


def grade_events():
    ext = pd.read_parquet(C.WORK / "extract.parquet")
    teach = ext.set_index("panel_uid")
    out = {}
    for model in ("base", "student"):
        g = _read_gen(f"{model}_events_events_test")
        if g is None:
            out[model] = {"status": "NOT_RUN"}
            continue
        g = g.join(teach[["event_type", "direction", "magnitude_bucket"]].rename(
            columns={"event_type": "t_event", "direction": "t_dir", "magnitude_bucket": "t_mag"}), on="key")
        v = g[g["valid"]]
        r = {"n": int(len(g)), "valid_rate": round(float(g["valid"].mean()), 4)}
        if len(v):
            r.update({
                "event_accuracy": round(float((v["event_type"] == v["t_event"]).mean()), 4),
                "event_kappa": round(float(cohen_kappa_score(v["t_event"], v["event_type"])), 4),
                "is_event_accuracy": round(float(((v["event_type"] != "no_event") == (v["t_event"] != "no_event")).mean()), 4),
                "event_accuracy_on_teacher_events": round(float((v.loc[v["t_event"] != "no_event", "event_type"] ==
                                                                 v.loc[v["t_event"] != "no_event", "t_event"]).mean()), 4),
                "direction_kappa": round(float(cohen_kappa_score(v["t_dir"].astype(int), v["direction"].astype(int))), 4),
                "magnitude_weighted_kappa": round(float(cohen_kappa_score(v["t_mag"].map(MAG_I), v["magnitude"].map(MAG_I),
                                                                          weights="linear")), 4),
                "teacher_no_event_rate": round(float((v["t_event"] == "no_event").mean()), 4),
                "always_no_event_accuracy": round(float((v["t_event"] == "no_event").mean()), 4),
            })
        out[model] = r
    return out


def grade_psych_agreement():
    ds = pd.read_json(C.WORK / "deepseek_psych.jsonl", lines=True)
    ds = ds[(ds["split"] == "test") & ds["parsed"]]
    ds["key"] = ds["symbol"] + "|" + ds["entry_date"]
    out = {}
    for model in ("base", "student"):
        g = _read_gen(f"{model}_psych_psych_test")
        if g is None:
            out[model] = {"status": "NOT_RUN"}
            continue
        m = g[g["valid"]].merge(ds, on="key", suffixes=("", "_ds"))
        r = {"n": int(len(g)), "valid_rate": round(float(g["valid"].mean()), 4)}
        for f in ("tone", "uncertainty", "surprise", "novelty", "attention"):
            r[f"spearman_{f}"] = round(float(spearmanr(m[f], m[f + "_ds"]).statistic), 4)
        mc = m.dropna(subset=["mgmt_confidence", "mgmt_confidence_ds"])
        r["spearman_mgmt_confidence"] = round(float(spearmanr(mc["mgmt_confidence"], mc["mgmt_confidence_ds"]).statistic), 4) if len(mc) > 10 else None
        r["mgmt_confidence_null_agreement"] = round(float((m["mgmt_confidence"].isna() == m["mgmt_confidence_ds"].isna()).mean()), 4)
        r["emotion_accuracy"] = round(float((m["emotion"] == m["emotion_ds"]).mean()), 4)
        r["emotion_kappa"] = round(float(cohen_kappa_score(m["emotion_ds"], m["emotion"])), 4)
        r["expected_move_weighted_kappa"] = round(float(cohen_kappa_score(m["expected_move_ds"].map(MAG_I),
                                                                          m["expected_move"].map(MAG_I), weights="linear")), 4)
        out[model] = r
    return out


# ------------------------------------------------------------------ C. psych -> size
PSY_NUM = ["tone", "uncertainty", "surprise", "novelty", "attention"]


def psych_features(g: pd.DataFrame) -> pd.DataFrame:
    f = pd.DataFrame(index=g.index)
    for c in PSY_NUM:
        f[c] = g[c].astype(float)
    f["abs_tone"] = f["tone"].abs()
    f["mgmt_present"] = g["mgmt_confidence"].notna().astype(float)
    f["mgmt_conf"] = g["mgmt_confidence"].fillna(0.5).astype(float)
    f["exp_move"] = g["expected_move"].map(MAG_I).astype(float)
    for e in P.EMOTIONS:
        f[f"emo_{e}"] = (g["emotion"] == e).astype(float)
    return f


def fit_psych_increment(fit_df, test_df, label):
    feats = psych_features(fit_df)
    cols = list(feats.columns)
    sc = StandardScaler().fit(feats)
    m = Ridge(alpha=10.0).fit(sc.transform(feats), fit_df["ly"] - fit_df["B2_trailing_meta"])
    tf = psych_features(test_df)
    test_df = test_df.copy()
    test_df[f"PSY_{label}"] = test_df["B2_trailing_meta"] + m.predict(sc.transform(tf[cols]))
    test_df[f"EXPMOVE_{label}"] = tf["exp_move"] + 0.001 * tf["attention"]
    res = {
        "n_fit": int(len(fit_df)), "n_test": int(len(test_df)),
        "ic_vol_prior": weekly_ic(test_df, "B0_vol_prior"),
        "ic_B2": weekly_ic(test_df, "B2_trailing_meta"),
        f"ic_B2_plus_psych": weekly_ic(test_df, f"PSY_{label}"),
        "increment_psych_over_B2": weekly_increment(test_df, f"PSY_{label}", "B2_trailing_meta"),
        "ic_expected_move_alone": weekly_ic(test_df, f"EXPMOVE_{label}"),
        "ic_expected_move_vs_relative_move": weekly_ic(test_df, f"EXPMOVE_{label}", "rel"),
        "expected_move_bucket_vs_realised": E.abs_bucket_accuracy(test_df["mag_bucket"], test_df["expected_move"]),
        "ridge_coefs_std": {c: round(float(v), 4) for c, v in zip(cols, m.coef_)},
    }
    # each numeric field alone, against the relative move (move / trailing vol): does the
    # field see the SURPRISE part of size the prior cannot?
    res["field_ic_vs_relative_move"] = {}
    for c in PSY_NUM + ["abs_tone"]:
        test_df[f"_f_{c}"] = tf[c].values
        res["field_ic_vs_relative_move"][c] = weekly_ic(test_df, f"_f_{c}", "rel")
    return res


def grade_psych_size(df):
    out = {}
    ds = pd.read_json(C.WORK / "deepseek_psych.jsonl", lines=True)
    ds = ds[ds["parsed"]].merge(df, on=["symbol", "entry_date"], how="inner", suffixes=("_ds", ""))
    ds = ds.rename(columns={"split": "split"})
    fit = ds[ds["split"] == "train"]
    test = ds[ds["split"] == "test"]
    out["C1_deepseek"] = fit_psych_increment(fit, test, "deepseek")
    sv = _read_gen("student_psych_psych_val")
    st = _read_gen("student_psych_psych_testall")
    if sv is not None and st is not None:
        sv = sv[sv["valid"]].merge(df, on=["symbol", "entry_date"], how="inner")
        st = st[st["valid"]].merge(df, on=["symbol", "entry_date"], how="inner")
        out["C2_student"] = fit_psych_increment(sv, st, "student")
    else:
        out["C2_student"] = {"status": "NOT_RUN"}
    bt = _read_gen("base_psych_psych_test")
    if bt is not None:
        bt = bt[bt["valid"]].merge(df, on=["symbol", "entry_date"], how="inner")
        bt["EXP"] = bt["expected_move"].map(MAG_I) + 0.001 * bt["attention"]
        out["C3_base_expected_move_zero_shot"] = {"ic": weekly_ic(bt, "EXP"),
                                                  "ic_vol_prior_same_cells": weekly_ic(bt, "B0_vol_prior"),
                                                  "bucket": E.abs_bucket_accuracy(bt["mag_bucket"], bt["expected_move"])}
    return out


# ------------------------------------------------------------------ D. speed and cost
def speed_cost():
    runs = []
    p = C.RECEIPTS / "infer_runs.jsonl"
    if p.exists():
        runs = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    ds = [json.loads(x) for x in (C.RECEIPTS / "deepseek_arm_runs.jsonl").read_text(encoding="utf-8").splitlines()]
    big = max(ds, key=lambda r: r["calls"])
    return {
        "local_runs": runs,
        "deepseek_psych_prompt": {"calls": big["calls"], "usd_ledger": big["cost_usd_ledger"],
                                  "usd_per_1000_pages_ledger": round(1000 * big["cost_usd_ledger"] / big["calls"], 4),
                                  "usd_per_1000_pages_peak_list": round(1000 * big["cost_usd_own_peak_estimate"] / big["calls"], 4),
                                  "pages_per_min_6_threads": round(big["calls"] / big["wall_s"] * 60, 1),
                                  "tokens_in_per_page": round(big["tokens_in"] / big["calls"], 1)},
        "deepseek_typed_event_prompt_measured_2026_09_13": {
            "usd_per_1000_pages": 0.3152, "tokens_in_per_page": 1482.7, "rows_per_min_serial": 57.4,
            "source": "scripts/night_l2_typed_events.py MEASURED (llm_calls_2026-09.jsonl, 7,565 rows)"},
        "local_7b_llama_server_typed_event_rate": {"rows_per_min_per_worker": 20.0,
                                                   "source": "scripts/night_l2_typed_events.py ROWS_PER_MIN_PER_WORKER (supervised wall clock)"},
    }


def main() -> dict:
    df = base_frame()
    rec = {"job": "ft_lab.first_run", "licence": C.LICENCE,
           "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "A_size_finetune": grade_size(df),
           "B_extraction_events_agreement": grade_events(),
           "B_extraction_psych_agreement": grade_psych_agreement(),
           "C_psych_to_size": grade_psych_size(df),
           "D_speed_cost": speed_cost(),
           "teacher_note": "every extraction agreement is against DeepSeek's labels: it measures mimicry, not truth"}
    (C.RECEIPTS / "first_run.json").write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    return rec


if __name__ == "__main__":
    r = main()
    print(json.dumps(r, indent=1, default=str)[:12000])
