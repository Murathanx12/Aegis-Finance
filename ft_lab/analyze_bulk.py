"""Grade the bulk student rows: (1) do the student's typed fields add to the SIZE forecast beyond
trailing priors + TF-IDF, and (2) conditional questions a global null does not answer:
which event types carry the largest next-session / 5-session moves, and is there post-event
DRIFT (signed return in the event's direction) after costs, out of sample, in most months?

Time split: FIT on the validation block (2026-01-16..04-30), GRADE on the test block
(2026-05-15..09-28), 10-session embargo between them (dataset.py). The T2 prior was itself
fitted on 2025 only (baselines.py). Standard errors over weekly DATE BLOCKS, MDE = 2.8 x SE.

Returns: x_oc = entry open -> entry close minus SPY (tradable from the first open after
publication); x5 = entry open -> close of the 5th session (entry + 4) minus SPY over the same
window, from prices_deep. Costs: COST_RT round trip on every signed position.

    ft_lab/.venv/Scripts/python.exe -m ft_lab.analyze_bulk
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from ft_lab import config as C
from ft_lab import evaluate as E

COST_RT = 0.0020          # 20 bps round trip (10 bps a side), both horizons
MIN_TYPE_N = 30           # an event type needs this many cells in a block to be graded
ALPHAS = [1.0, 10.0, 100.0, 1000.0, 10000.0]
MAGI = {n: i for i, n in enumerate(C.MAG_NAMES)}


def load_rows() -> pd.DataFrame:
    rows = pd.read_json(C.WORK / "bulk_events.jsonl", lines=True)
    rows = rows[(rows["source"] == "panel_cell_first_doc") & rows["valid"]].copy()
    rows["first_uid"] = rows["key"].str.split("|").str[0]
    return rows[["first_uid", "symbol", "event_type", "direction", "magnitude", "confidence"]]


def five_session(cells: pd.DataFrame) -> pd.Series:
    b = pd.read_parquet(C.BARS, columns=["symbol", "date", "open", "close"],
                        filters=[("date", ">=", pd.Timestamp("2025-12-01"))])
    b = b[b["symbol"].isin(set(cells["symbol"]) | {"SPY"})]
    b = b.sort_values(["symbol", "date"]).reset_index(drop=True)
    b["close_4"] = b.groupby("symbol")["close"].shift(-4)
    b["date_4"] = b.groupby("symbol")["date"].shift(-4)
    b["r5"] = b["close_4"] / b["open"] - 1.0
    spy = b[b["symbol"] == "SPY"].set_index("date")["r5"].rename("spy5")
    b = b.join(spy, on="date")
    # a symbol with a data gap longer than the calendar would make "4 sessions" a month: refuse it
    b.loc[(b["date_4"] - b["date"]).dt.days > 10, "r5"] = np.nan
    b["x5"] = b["r5"] - b["spy5"]
    key = b["symbol"] + "|" + b["date"].dt.strftime("%Y-%m-%d")
    m = pd.Series(b["x5"].values, index=key.values)
    return (cells["symbol"] + "|" + cells["entry_date"]).map(m)


def features(df: pd.DataFrame, types: list[str]) -> np.ndarray:
    ev = df["event_type"].where(df["event_type"].isin(types), "other_event")
    D = pd.get_dummies(ev, dtype=float).reindex(columns=types + ["other_event"], fill_value=0.0)
    D = D.drop(columns=["no_event"], errors="ignore")
    mag = df["magnitude"].map(MAGI).astype(float)
    num = pd.DataFrame({"mag": mag, "absdir": df["direction"].abs().astype(float), "conf": df["confidence"],
                        "is_event": (df["event_type"] != "no_event").astype(float),
                        "mag_x_event": mag * (df["event_type"] != "no_event")})
    return np.hstack([D.values, num.values])


def size_test(df: pd.DataFrame, va, te, base: str, name: str) -> dict:
    types = df.loc[va, "event_type"].value_counts()
    types = [t for t, n in types.items() if n >= MIN_TYPE_N]
    X = features(df, types)
    mu, sd = X[va.values].mean(0), X[va.values].std(0) + 1e-9
    X = (X - mu) / sd
    resid = (df["ly"] - df[base]).values
    # alpha by time inside the fit block: first 70% of val dates fit, last 30% check
    vd = np.sort(df.loc[va, "entry_date"].unique())
    cut = vd[int(len(vd) * 0.7)]
    inner_tr = va & (df["entry_date"] < cut)
    inner_ck = va & (df["entry_date"] >= cut)
    best = None
    for a in ALPHAS:
        m = Ridge(alpha=a).fit(X[inner_tr.values], resid[inner_tr.values])
        df["_p"] = df[base] + m.predict(X)
        v = E.ic(df[inner_ck], "_p", "y")["mean"] or -9
        if best is None or v > best[0]:
            best = (v, a)
    m = Ridge(alpha=best[1]).fit(X[va.values], resid[va.values])
    df[name] = df[base] + m.predict(X)
    t = df[te]
    return {"fit_block": "val", "alpha": best[1], "n_event_types_as_features": len(types),
            "n_fit": int(va.sum()), "n_test": int(te.sum()),
            "ic_test": E.ic(t, name, "y"), "ic_base": E.ic(t, base, "y"),
            "increment": E.ic_increment(t, name, base, "y")}


def per_date_stats(sub: pd.DataFrame, col: str) -> dict:
    per = sub.groupby("entry_date")[col].mean()
    r = E.block_stats(per)
    bm = per.groupby(pd.Index(per.index).str[:7]).mean()
    r["by_month"] = {k: round(float(v), 5) for k, v in bm.items()}
    r["share_months_positive"] = round(float((bm > 0).mean()), 3) if len(bm) else None
    r["n_cells"] = int(sub[col].notna().sum())
    return r


def conditional(df: pd.DataFrame, va, te) -> dict:
    out = {"size_by_type_test": {}, "drift_by_type": {}}
    df["x5abs"] = df["x5"].abs()
    df["rel1"] = df["ly"] - df["l_vol21_absx"]           # log(|move| / trailing typical move)
    df["sgn1"] = df["direction"] * df["x_oc"]
    df["sgn5"] = df["direction"] * df["x5"]
    df["net1"] = df["sgn1"] - COST_RT
    df["net5"] = df["sgn5"] - COST_RT
    t = df[te]
    ne_rel = float(t.loc[t["event_type"] == "no_event", "rel1"].mean())
    for et, g in t.groupby("event_type"):
        if len(g) < MIN_TYPE_N:
            continue
        out["size_by_type_test"][et] = {
            "n": int(len(g)), "median_abs_1d": round(float(g["y"].median()), 5),
            "mean_abs_1d": round(float(g["y"].mean()), 5),
            "median_abs_5d": round(float(g["x5abs"].median()), 5),
            "mean_rel_log_1d": round(float(g["rel1"].mean()), 4),
            # log(|move|/typical) of this type minus the no_event cells' mean, SE over weeks
            "rel_minus_no_event": per_date_stats(g.assign(_d=g["rel1"] - ne_rel), "_d")}
    # DRIFT: select on the FIT block (val), grade on test; directional rows only
    dv = df[va & (df["direction"] != 0)]
    dt = df[te & (df["direction"] != 0)]
    for h in ("1", "5"):
        sel = []
        tab = {}
        for et, g in dv.groupby("event_type"):
            if len(g) < MIN_TYPE_N:
                continue
            v = per_date_stats(g, f"net{h}")
            gt = dt[dt["event_type"] == et]
            tst = per_date_stats(gt, f"net{h}") if len(gt) >= MIN_TYPE_N else None
            gross = per_date_stats(gt, f"sgn{h}") if len(gt) >= MIN_TYPE_N else None
            chosen = bool(v["mean"] is not None and v["mean"] > 0)
            sel += [et] if chosen else []
            verdict = None
            if tst and tst["mean"] is not None:
                if chosen and tst["mean"] > 0 and (tst["t"] or 0) >= 2 and (tst["share_months_positive"] or 0) > 0.5:
                    verdict = "CONDITIONAL_POSITIVE"
                elif chosen:
                    verdict = "FAILED_VARIANT" if tst["mean"] <= 0 else "CANNOT_DISTINGUISH"
                else:
                    verdict = "NOT_SELECTED_ON_VAL"
            tab[et] = {"val_net": {k: v[k] for k in ("mean", "t", "mde", "n_cells", "share_months_positive")},
                       "selected_on_val": chosen,
                       "test_net": tst, "test_gross_mean": None if not gross else gross["mean"],
                       "verdict": verdict}
        pooled = dt[dt["event_type"].isin(sel)]
        out["drift_by_type"][f"h{h}"] = {"selected_on_val": sel, "types": tab,
                                          "pooled_selected_test_net": per_date_stats(pooled, f"net{h}")
                                          if len(pooled) else None}
    return out


def main(debug_split: bool = False) -> dict:
    cells = pd.read_parquet(C.WORK / "cells.parquet")
    cells = cells[cells["split"].isin(["val", "test"])]
    if debug_split:   # code check only, never a result: the test block split in two by date
        cells = cells[cells["split"] == "test"].copy()
        cells.loc[cells["entry_date"] < "2026-07-10", "split"] = "val"
    pb = pd.read_parquet(C.WORK / "preds_baselines.parquet", columns=["symbol", "entry_date", "B0_vol_prior",
                                                                        "B2_trailing_meta", "T2_trailing_meta_tfidf"])
    cells = cells.merge(pb, on=["symbol", "entry_date"], how="left")
    rows = load_rows()
    df = cells.merge(rows, on=["first_uid", "symbol"], how="inner").reset_index(drop=True)
    df["x5"] = five_session(df).values
    va, te = df["split"] == "val", df["split"] == "test"
    cov = {"val_cells": int((cells["split"] == "val").sum()), "val_with_student": int(va.sum()),
           "test_cells": int((cells["split"] == "test").sum()), "test_with_student": int(te.sum())}
    res = {"coverage": cov,
           "event_share_test": df.loc[te, "event_type"].value_counts(normalize=True).round(4).head(15).to_dict()}
    res["size_over_T2_tfidf"] = size_test(df, va, te, "T2_trailing_meta_tfidf", "S_T2_plus_student")
    res["size_over_B2"] = size_test(df, va, te, "B2_trailing_meta", "S_B2_plus_student")
    df["_T2"] = df["T2_trailing_meta_tfidf"]
    res["tfidf_over_B2_same_cells"] = E.ic_increment(df[te], "_T2", "B2_trailing_meta", "y")
    res["student_vs_tfidf_same_cells"] = E.ic_increment(df[te], "S_B2_plus_student", "_T2", "y")
    res["conditional"] = conditional(df, va, te)
    rec = {"job": "ft_lab.analyze_bulk", "licence": C.LICENCE,
           "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "cost_round_trip": COST_RT, "min_type_n": MIN_TYPE_N, **res}
    if debug_split:
        return rec
    (C.RECEIPTS / "bulk_analysis.json").write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    return rec


if __name__ == "__main__":
    r = main()
    print(json.dumps({k: r[k] for k in ("coverage",)}, indent=1))
    for k in ("size_over_T2_tfidf", "size_over_B2"):
        inc = r[k]["increment"]
        print(k, "IC", r[k]["ic_test"]["mean"], "base", r[k]["ic_base"]["mean"], "inc", inc["mean"], "t", inc["t"],
              "MDE", inc["mde"], "months+", inc["share_of_months_positive"])
