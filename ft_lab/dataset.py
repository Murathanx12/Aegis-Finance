"""Build ft_lab's two tables from what is already on disk. No network, no LLM.

cells.parquet   one row per (symbol, entry_date) news cell of the E1 text-return panel:
                text (first document + other headlines), PIT numeric priors from the bars
                panel, the target |x_oc| and the split.
extract.parquet one row per DeepSeek-typed document (typed_events/panel_2026-09-13.jsonl),
                with its text and the TEACHER label (event_type, direction,
                magnitude_bucket, confidence). A teacher label is DeepSeek's reading, not
                ground truth.

Run:  ft_lab/.venv/Scripts/python.exe -m ft_lab.dataset
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ft_lab import config as C

#: columns of the panel that are realised ON or AFTER the entry session. None may be a
#: feature. `dollar_vol` is the ENTRY day's dollar volume -- realised during the target
#: session -- so it is barred like the returns.
FORBIDDEN_FEATURES = ("r_oc", "r_oo", "x_oc", "x_oo", "dollar_vol", "y", "ly", "rel",
                      "mag_bucket")

PRIOR_TRAILING = ["l_vol21_absx", "l_sd21_cc", "l_sd63_cc", "l_last_absx", "l_dv21"]
PRIOR_AT_OPEN = PRIOR_TRAILING + ["l_gap_abs"]
META = ["l_n_docs", "l_n_sources", "pre_bell"]


# ------------------------------------------------------------------ split + leakage guard
def assign_split(dates: pd.Series, splits: dict | None = None) -> pd.Series:
    """Label each entry_date train/val/test by the configured inclusive bounds; dates in an
    embargo gap get 'embargo' and are never used."""
    splits = splits or C.SPLITS
    d = pd.to_datetime(dates)
    out = pd.Series("embargo", index=dates.index, dtype=object)
    for name, (lo, hi) in splits.items():
        out[(d >= pd.Timestamp(lo)) & (d <= pd.Timestamp(hi))] = name
    return out


def assert_time_split(df: pd.DataFrame, sessions: pd.DatetimeIndex | None = None,
                      embargo: int = C.EMBARGO_SESSIONS) -> dict:
    """Refuse unless train < val < test in time with >= `embargo` sessions between blocks.

    `sessions` is the trading calendar; without it, business days stand in."""
    order = ["train", "val", "test"]
    d = pd.to_datetime(df["entry_date"])
    spans = {}
    for s in order:
        m = df["split"] == s
        if not m.any():
            raise ValueError(f"split {s!r} is empty")
        spans[s] = (d[m].min(), d[m].max())
    gaps = {}
    for a, b in zip(order, order[1:]):
        end_a, start_b = spans[a][1], spans[b][0]
        if not end_a < start_b:
            raise ValueError(f"LEAK: {a} ends {end_a.date()} on/after {b} starts {start_b.date()}")
        if sessions is not None:
            n_between = int(((sessions > end_a) & (sessions < start_b)).sum())
        else:
            n_between = int(np.busday_count(end_a.date(), start_b.date())) - 1
        if n_between < embargo:
            raise ValueError(f"LEAK: only {n_between} sessions between {a} and {b} "
                             f"(embargo {embargo})")
        gaps[f"{a}->{b}"] = n_between
    return {"spans": {k: [str(v[0].date()), str(v[1].date())] for k, v in spans.items()},
            "sessions_between": gaps}


def assert_features_pit(df: pd.DataFrame, feature_cols: list[str]) -> None:
    """Refuse a feature list that names a realised column, or a row whose trailing
    features were computed on/after its entry session."""
    bad = [c for c in feature_cols if c in FORBIDDEN_FEATURES]
    if bad:
        raise ValueError(f"LEAK: forbidden feature columns {bad}")
    if "asof_date" in df.columns:
        a = pd.to_datetime(df["asof_date"])
        e = pd.to_datetime(df["entry_date"])
        n = int(((a >= e) & a.notna()).sum())
        if n:
            raise ValueError(f"LEAK: {n} rows have trailing features as of >= entry_date")


# ------------------------------------------------------------------ priors from bars
def trailing_priors(symbols: set[str], start: str = "2024-09-01") -> pd.DataFrame:
    """Per (symbol, session) priors known BEFORE that session opens (all shifted by one
    session), plus |gap| known AT its open. `asof_date` is the last session used."""
    b = pd.read_parquet(C.BARS, columns=["symbol", "date", "open", "close", "volume"])
    b = b[(b["date"] >= pd.Timestamp(start)) & (b["symbol"].isin(symbols | {"SPY"}))]
    b = b.sort_values(["symbol", "date"]).reset_index(drop=True)
    b["r_oc"] = b["close"] / b["open"] - 1.0
    spy = b[b["symbol"] == "SPY"].set_index("date")["r_oc"].rename("spy_oc")
    b = b.join(spy, on="date")
    b["x_oc_d"] = b["r_oc"] - b["spy_oc"]
    g = b.groupby("symbol", sort=False)
    prev_close = g["close"].shift(1)
    b["r_cc"] = b["close"] / prev_close - 1.0
    b["gap_abs"] = (b["open"] / prev_close - 1.0).abs()
    b["dv"] = b["close"] * b["volume"]
    b["_absx"] = b["x_oc_d"].abs()
    g = b.groupby("symbol", sort=False)
    sh_absx = g["_absx"].shift(1)
    sh_rcc = g["r_cc"].shift(1)
    sh_dv = g["dv"].shift(1)
    key = b["symbol"]
    feats = pd.DataFrame({
        "symbol": b["symbol"], "entry_date": b["date"],
        "asof_date": g["date"].shift(1),
        "vol21_absx": sh_absx.groupby(key).transform(lambda s: s.rolling(C.VOL_WINDOW, min_periods=10).mean()),
        "sd21_cc": sh_rcc.groupby(key).transform(lambda s: s.rolling(21, min_periods=10).std()),
        "sd63_cc": sh_rcc.groupby(key).transform(lambda s: s.rolling(63, min_periods=30).std()),
        "last_absx": sh_absx,
        "dv21": sh_dv.groupby(key).transform(lambda s: s.rolling(21, min_periods=10).median()),
        "gap_abs": b["gap_abs"],
    })
    for c in ["vol21_absx", "sd21_cc", "sd63_cc", "last_absx", "gap_abs"]:
        feats["l_" + c] = np.log(feats[c] + C.EPS)
    feats["l_dv21"] = np.log1p(feats["dv21"])
    return feats


# ------------------------------------------------------------------ cells
def _norm(s) -> str:
    return " ".join(str(s or "").split())


def build_cells(panel: pd.DataFrame) -> pd.DataFrame:
    p = panel.copy()
    p = p[p["pit_grade"].fillna("") != "archive"]
    p["title"] = p["title"].map(_norm)
    p["body"] = p["body"].map(_norm)
    p["published_utc"] = p["published_utc"].fillna("").astype(str)
    p = p.sort_values(["symbol", "entry_date", "published_utc", "uid"], kind="mergesort")
    rows = []
    for (sym, day), g in p.groupby(["symbol", "entry_date"], sort=False):
        head = g.iloc[0]
        others = [t for t in g["title"].iloc[1:].tolist() if t and t != head["title"]]
        others = list(dict.fromkeys(others))[:C.OTHER_TITLES]
        text = head["title"]
        if head["body"]:
            text += "\n" + head["body"]
        text = text[:C.TEXT_CHARS]
        if others:
            text += "\nOther headlines: " + " | ".join(others)
        rows.append({
            "symbol": sym, "entry_date": day, "text": text,
            "first_uid": head["uid"], "first_source": head["source"],
            "pre_bell": int(head["publish_position"] == "pre_bell"),
            "n_docs": int(len(g)), "n_sources": int(g["source"].nunique()),
            "x_oc": float(head["x_oc"]),
            "title_key": hashlib.sha1(head["title"].lower().encode()).hexdigest()[:16],
        })
    cells = pd.DataFrame(rows)
    cells["l_n_docs"] = np.log1p(cells["n_docs"])
    cells["l_n_sources"] = np.log1p(cells["n_sources"])
    return cells


def mag_bucket(y: pd.Series) -> pd.Series:
    return pd.cut(y, C.MAG_EDGES, right=False, labels=C.MAG_NAMES).astype(str)


def build(save: bool = True) -> dict:
    C.WORK.mkdir(parents=True, exist_ok=True)
    panel = pd.read_parquet(C.PANEL)
    cells = build_cells(panel)
    pri = trailing_priors(set(cells["symbol"]))
    cells["entry_date_ts"] = pd.to_datetime(cells["entry_date"])
    cells = cells.merge(pri.rename(columns={"entry_date": "entry_date_ts"}),
                        on=["symbol", "entry_date_ts"], how="left")
    n0 = len(cells)
    cells = cells[np.isfinite(cells["x_oc"]) & cells["l_vol21_absx"].notna()
                  & cells["l_gap_abs"].notna() & cells["l_sd63_cc"].notna()
                  & cells["l_last_absx"].notna() & cells["l_dv21"].notna()].copy()
    dropped_no_prior = n0 - len(cells)
    cells["y"] = cells["x_oc"].abs()
    cells["ly"] = np.log(cells["y"] + C.EPS)
    cells["rel"] = cells["ly"] - cells["l_vol21_absx"]     # surprise size relative to normal
    cells["mag_bucket"] = mag_bucket(cells["y"])
    cells["split"] = assign_split(cells["entry_date"])
    sessions = pd.DatetimeIndex(sorted(pri["entry_date"].unique()))
    split_check = assert_time_split(cells[cells["split"] != "embargo"], sessions)
    assert_features_pit(cells, PRIOR_AT_OPEN + META)
    cells["week"] = cells["entry_date_ts"].dt.to_period("W-FRI").astype(str)
    cells["month"] = cells["entry_date"].str[:7]
    train_titles = set(cells.loc[cells["split"] == "train", "title_key"])
    cells["title_seen_in_train"] = cells["title_key"].isin(train_titles) & (cells["split"] != "train")

    # ---------------- extraction docs (teacher = DeepSeek, typed 2026-09-13) ----------------
    uid_text = (panel.sort_values(["uid", "symbol"]).drop_duplicates("uid")
                .set_index("uid")[["title", "body", "source", "published_utc"]])
    ext = []
    with open(C.TEACHER, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            ext.append({k: r.get(k) for k in ("panel_uid", "scope", "scope_kind", "document_date",
                                               "panel_entry_date", "panel_cells", "event_type",
                                               "direction", "magnitude_bucket", "confidence",
                                               "model", "text_sha256")})
    ext = pd.DataFrame(ext)
    ext = ext.join(uid_text, on="panel_uid")
    ext = ext[ext["title"].notna()].copy()
    ext["title"] = ext["title"].map(_norm)
    ext["body"] = ext["body"].map(_norm)
    ext["entry_date"] = ext["panel_entry_date"]
    ext["split"] = assign_split(ext["entry_date"])
    ext_check = assert_time_split(ext[ext["split"] != "embargo"], sessions)
    ext["panel_cells"] = ext["panel_cells"].map(json.dumps)

    if save:
        cells.drop(columns=["entry_date_ts"]).to_parquet(C.WORK / "cells.parquet", index=False)
        ext.to_parquet(C.WORK / "extract.parquet", index=False)

    def span(df):
        return [str(df["entry_date"].min()), str(df["entry_date"].max())]

    tr = ext["split"] == "train"
    rec = {
        "job": "ft_lab.dataset", "licence": C.LICENCE,
        "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": {"panel": str(C.PANEL.relative_to(C.REPO)), "panel_rows": int(len(panel)),
                   "bars": str(C.BARS.relative_to(C.REPO)),
                   "teacher": str(C.TEACHER.relative_to(C.REPO))},
        "target": f"|{C.TARGET}|: open-to-close of the first session whose open is after publication, minus SPY's",
        "cells": {
            "n_total": int(len(cells)), "dropped_no_trailing_prior": int(dropped_no_prior),
            "by_split": cells["split"].value_counts().to_dict(),
            "date_range_by_split": {s: span(cells[cells["split"] == s]) for s in ["train", "val", "test"]},
            "symbols": int(cells["symbol"].nunique()),
            "median_abs_move_by_split": {s: round(float(cells.loc[cells["split"] == s, "y"].median()), 5)
                                         for s in ["train", "val", "test"]},
            "mag_bucket_share_by_split": {s: cells.loc[cells["split"] == s, "mag_bucket"]
                                          .value_counts(normalize=True).round(4).to_dict()
                                          for s in ["train", "val", "test"]},
            "title_seen_in_train_share": {s: round(float(cells.loc[cells["split"] == s, "title_seen_in_train"].mean()), 4)
                                          for s in ["val", "test"]},
            "split_check": split_check,
        },
        "extract": {
            "n_total": int(len(ext)), "by_split": ext["split"].value_counts().to_dict(),
            "date_range_by_split": {s: span(ext[ext["split"] == s]) for s in ["train", "val", "test"]},
            "teacher_model": sorted(ext["model"].dropna().unique().tolist()),
            "event_type_share_train": ext.loc[tr, "event_type"].value_counts(normalize=True).round(4).head(15).to_dict(),
            "n_event_types": int(ext["event_type"].nunique()),
            "magnitude_share_train": ext.loc[tr, "magnitude_bucket"].value_counts(normalize=True).round(4).to_dict(),
            "direction_share_train": {str(k): v for k, v in ext.loc[tr, "direction"].value_counts(normalize=True).round(4).to_dict().items()},
            "split_check": ext_check,
            "teacher_is_not_ground_truth": "every extraction label is DeepSeek's reading of the text; agreement with it measures mimicry, not truth",
        },
        "leakage_guards": ["assert_time_split (train < val < test, >= %d sessions between)" % C.EMBARGO_SESSIONS,
                           "assert_features_pit (no realised column; trailing priors as of the session BEFORE entry)",
                           "the panel's dollar_vol is the ENTRY day's and is barred; dv21 is recomputed from bars"],
    }
    if save:
        C.RECEIPTS.mkdir(parents=True, exist_ok=True)
        (C.RECEIPTS / "dataset.json").write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    return rec


if __name__ == "__main__":
    print(json.dumps(build(), indent=1, default=str))
