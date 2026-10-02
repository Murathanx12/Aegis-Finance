"""SIZE ensemble members (2026-09-30): two things the project has measured to be learnable.

1. EARNINGS-SIZE PRIOR. Earnings is the one event type whose move is larger than its own
   trailing volatility predicts (ft_lab 2026-09-29: +0.24 log ratio, t 3.74, 5/5 months).
   Whether an earnings release falls inside a hold window is KNOWABLE BEFOREHAND from the
   release cadence: SEC 8-K item 2.02 ("Results of Operations") dates filed strictly before
   t, projected forward one year (d + 364) and one quarter (last + 91). The realised 2.02
   date is used only to grade the projection, never as a feature.

2. TF-IDF TEXT SIZE. ft_lab's T2 recipe (ridge on trailing priors, then a TF-IDF 1-2gram
   ridge on its residual) adds +0.0069 rank IC for the NEXT session's |move|. Here the text's
   contribution (T2 minus B2, a log-size residual) is fitted ONLY on news cells before a
   cutoff and averaged over the cells that entered in the 7 calendar days up to t
   (entry_date <= t, so the text was published before t's open); NaN without news.

Coverage (review F2 discipline): the 8-K pull was made in 2026 for names alive then (living
84%, dead 3%), so its coverage is LATER_PULL_SNAPSHOT: an uncovered name reads "no earnings
expected" (0), and no coverage indicator is ever a feature. News is LATER_PULL_ARCHIVAL.

Members enter the nightly ensemble ONLY through the forward-only magnitude trust
(`loop.magnitude_table`), starting at the prior 0; walk-forward numbers are reported and
never seed them (they are absent from `nightly.wf_record`'s name map on purpose).

    python -m nn_lab.size_members build      # sidecar table for every grid row + live rows
    python -m nn_lab.size_members evaluate   # size walk-forward receipt
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from nn_lab import config as C

EIGHTK = C.OPTIMUS / "edgar_8k" / "eightk_items.parquet"
FT_CELLS = C.REPO / "ft_lab" / "data" / "cells.parquet"
SIDECAR = C.TABLE_DIR / "size_members.parquet"
YEAR_DAYS = 364          # same weekday one year on
QUARTER_DAYS = 91
TOL_DAYS = 3
MAX_KNOWN_LAG_DAYS = 30   # an 8-K filed later than this after its event is not used
TEXT_WINDOW_DAYS = 7
TEXT_EMBARGO_DAYS = 15   # between the last fitted cell and the first scored cell
MEMBERS = ("vol_earn", "vol_text", "ridge_abs_plus")
EARN_COLS = tuple(f"earn_exp_{h}" for h in C.MAGNITUDE_HORIZONS)


# ─────────────────────────── earnings cadence ────────────────────────────────

def earnings_dates(eightk: pd.DataFrame | None = None) -> pd.DataFrame:
    """(ticker, event_day, known_day) for every 8-K carrying item 2.02.

    event_day = the acceptance date (the release's day); known_day = the filing date
    (the earliest day the row could be read)."""
    if eightk is None:
        eightk = pd.read_parquet(EIGHTK, columns=["ticker", "filing_date", "acceptance_datetime", "items_joined"])
    e = eightk[eightk["items_joined"].fillna("").str.contains("2.02", regex=False)].copy()
    acc = pd.to_datetime(e["acceptance_datetime"], errors="coerce", utc=True).dt.tz_localize(None)
    e["event_day"] = acc.dt.normalize().fillna(pd.to_datetime(e["filing_date"]))
    e["known_day"] = pd.to_datetime(e["filing_date"]).dt.normalize()
    e["known_day"] = e[["known_day", "event_day"]].max(axis=1)
    return e[["ticker", "event_day", "known_day"]].dropna().sort_values(["ticker", "event_day"]).reset_index(drop=True)


def expected_earnings(rows: pd.DataFrame, cal: pd.DatetimeIndex, ed: pd.DataFrame,
                      horizons=C.MAGNITUDE_HORIZONS) -> pd.DataFrame:
    """For each (symbol, date t) row: earn_exp_h = 1 when a release is EXPECTED inside the
    hold window [session t+1, session t+1+h], from releases KNOWN strictly before t.
    Also returns earn_real_h (the realised release in the window) for grading only."""
    out = {f"earn_exp_{h}": np.zeros(len(rows), dtype="float32") for h in horizons}
    out.update({f"earn_real_{h}": np.zeros(len(rows), dtype="float32") for h in horizons})
    pos_t = np.searchsorted(cal.values, rows["date"].values)
    win = {}
    for h in horizons:
        a = np.clip(pos_t + 1, 0, len(cal) - 1)
        b = pos_t + 1 + h
        lo = cal.values[a]
        hi = np.where(b < len(cal), cal.values[np.clip(b, 0, len(cal) - 1)],
                      (pd.DatetimeIndex(rows["date"].values) + pd.offsets.BDay(1 + h)).values)
        win[h] = (lo.astype("datetime64[D]"), hi.astype("datetime64[D]"))
    ed = ed[(ed["known_day"] - ed["event_day"]) <= pd.Timedelta(days=MAX_KNOWN_LAG_DAYS)]
    groups = ed.groupby("ticker")
    tick = set(ed["ticker"].unique())
    tol = np.timedelta64(TOL_DAYS, "D")
    for sym, idx in rows.groupby("symbol").indices.items():
        base = str(sym).split("#")[0]
        if base != str(sym) or base not in tick:   # a renamed dead segment is not the 2026 filer
            continue
        g = groups.get_group(base)
        kn = g["known_day"].values.astype("datetime64[D]")
        order = np.argsort(kn, kind="stable")
        kn_s = kn[order]
        ev_k = g["event_day"].values.astype("datetime64[D]")[order]
        ev_cummax = np.maximum.accumulate(ev_k.astype("int64")).astype("datetime64[D]")
        ev_sorted = np.sort(g["event_day"].values.astype("datetime64[D]"))
        t = rows["date"].values[idx].astype("datetime64[D]")
        n_known = np.searchsorted(kn_s, t, side="left")          # releases known strictly before t
        last = np.where(n_known > 0, ev_cummax[np.maximum(n_known - 1, 0)], np.datetime64("NaT"))
        yr = np.timedelta64(YEAR_DAYS, "D")
        for h in horizons:
            lo, hi = win[h][0][idx], win[h][1][idx]
            # one year on: a release in [lo-364-tol, hi-364+tol]; it lies >300 days before t
            # and was filed within MAX_KNOWN_LAG_DAYS of its event, so it was known before t
            a = np.searchsorted(ev_sorted, lo - yr - tol, side="left")
            b = np.searchsorted(ev_sorted, hi - yr + tol, side="right")
            yearly = b > a
            q = last + np.timedelta64(QUARTER_DAYS, "D")
            quarterly = (n_known > 0) & (q >= t) & (q >= lo - tol) & (q <= hi + tol)
            out[f"earn_exp_{h}"][idx] = (yearly | quarterly)
            i0 = np.searchsorted(ev_sorted, lo, side="left")
            i1 = np.searchsorted(ev_sorted, hi, side="right")
            out[f"earn_real_{h}"][idx] = (i1 > i0)
    return pd.DataFrame(out, index=rows.index)


# ─────────────────────────── TF-IDF text size ────────────────────────────────

PRIOR_TRAILING = ["l_vol21_absx", "l_sd21_cc", "l_sd63_cc", "l_last_absx", "l_dv21"]
META = ["l_n_docs", "l_n_sources", "pre_bell"]
ALPHAS = (1.0, 10.0, 100.0, 1000.0)


def fit_text_model(cells: pd.DataFrame, fit_mask: np.ndarray, *, max_features: int = 50000):
    """ft_lab T2: B2 ridge on priors, TF-IDF ridge on B2's residual. Alpha chosen on the
    last 20% (by date) of the FIT rows, never on a scored row."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    fit = cells[fit_mask]
    dates = np.sort(fit["entry_date"].unique())
    cut = dates[int(len(dates) * 0.8)]
    inner_tr = (fit["entry_date"] < cut).values
    inner_va = ~inner_tr
    feats = PRIOR_TRAILING + META
    sc = StandardScaler().fit(fit[feats])
    Xb = sc.transform(fit[feats])
    b2 = Ridge(alpha=10.0).fit(Xb, fit["ly"])
    resid = fit["ly"].values - b2.predict(Xb)
    vec = TfidfVectorizer(max_features=max_features, ngram_range=(1, 2), min_df=5, sublinear_tf=True,
                          dtype=np.float32).fit(fit["text"])
    Xt = vec.transform(fit["text"])
    best = None
    for a in ALPHAS:
        m = Ridge(alpha=a).fit(Xt[inner_tr], resid[inner_tr])
        p = m.predict(Xt[inner_va])
        c = np.corrcoef(p, resid[inner_va])[0, 1]
        if best is None or c > best[0]:
            best = (c, a)
    tm = Ridge(alpha=best[1]).fit(Xt, resid)
    return {"vec": vec, "text_ridge": tm, "alpha": best[1], "inner_val_corr": round(float(best[0]), 4),
            "fit_rows": int(len(fit)), "fit_last_entry": str(fit["entry_date"].max())}


def text_resid(model: dict, cells: pd.DataFrame) -> np.ndarray:
    return model["text_ridge"].predict(model["vec"].transform(cells["text"])).astype("float32")


def text_cutoffs(entry_dates: pd.Series, every_months: int = 6, min_months: int = 5) -> list[pd.Timestamp]:
    """Refit points: every `every_months` months after the first `min_months` of news."""
    d = pd.to_datetime(entry_dates)
    start = d.min().to_period("M").to_timestamp() + pd.DateOffset(months=min_months)
    cuts, c = [], start
    while c <= d.max():
        cuts.append(pd.Timestamp(c))
        c = c + pd.DateOffset(months=every_months)
    return cuts


def scored_cells(cells: pd.DataFrame, cutoffs: list[pd.Timestamp]) -> pd.DataFrame:
    """Out-of-sample text residual per cell: each cell is scored by the model fitted on
    cells entered at least TEXT_EMBARGO_DAYS before the cutoff that precedes it."""
    ed = pd.to_datetime(cells["entry_date"])
    out = pd.Series(np.nan, index=cells.index, dtype="float32")
    info = []
    for i, c in enumerate(cutoffs):
        nxt = cutoffs[i + 1] if i + 1 < len(cutoffs) else pd.Timestamp.max
        fit_mask = (ed < c - pd.Timedelta(days=TEXT_EMBARGO_DAYS)).values
        score_mask = ((ed >= c) & (ed < nxt)).values
        if fit_mask.sum() < 5000 or score_mask.sum() == 0:
            continue
        m = text_model_cache(cells, fit_mask)
        out[score_mask] = text_resid(m, cells[score_mask])
        info.append({"cutoff": str(c.date()), "fit_rows": m["fit_rows"], "alpha": m["alpha"],
                     "inner_val_corr": m["inner_val_corr"], "scored": int(score_mask.sum())})
    return pd.DataFrame({"symbol": cells["symbol"].values, "entry_date": ed.values,
                         "text_resid": out.values}), info


def text_model_cache(cells, fit_mask):
    return fit_text_model(cells, fit_mask)


def aggregate_text(rows: pd.DataFrame, scored: pd.DataFrame) -> np.ndarray:
    """Mean scored text residual over cells with entry_date in (t - 7d, t]; NaN when none."""
    s = scored.dropna(subset=["text_resid"])
    s = s.groupby(["symbol", "entry_date"], as_index=False)["text_resid"].mean().sort_values(["symbol", "entry_date"])
    out = np.full(len(rows), np.nan, dtype="float32")
    gs = s.groupby("symbol")
    have = set(s["symbol"].unique())
    for sym, idx in rows.groupby("symbol").indices.items():
        if sym not in have:
            continue
        g = gs.get_group(sym)
        ed = g["entry_date"].values.astype("datetime64[D]")
        cs = np.r_[0.0, np.cumsum(g["text_resid"].values.astype("float64"))]
        t = rows["date"].values[idx].astype("datetime64[D]")
        hi = np.searchsorted(ed, t, side="right")
        lo = np.searchsorted(ed, t - np.timedelta64(TEXT_WINDOW_DAYS, "D"), side="right")
        n = hi - lo
        with np.errstate(invalid="ignore", divide="ignore"):
            v = np.where(n > 0, (cs[hi] - cs[lo]) / np.maximum(n, 1), np.nan)
        out[idx] = v
    return out


# ─────────────────────────── build the sidecar ───────────────────────────────

def build(table_path: Path | None = None, out: Path | None = None) -> dict:
    t0 = time.time()
    tp = Path(table_path or C.TABLE_PATH)
    rows = pd.read_parquet(tp, columns=["date", "symbol", "on_grid"])
    cal = pd.DatetimeIndex(pd.read_parquet(tp.parent / "calendar.parquet")["date"])
    ed = earnings_dates()
    ee = expected_earnings(rows, cal, ed)
    side = pd.concat([rows[["date", "symbol"]], ee], axis=1)
    info: dict = {"earnings_releases": int(len(ed)), "earnings_tickers": int(ed["ticker"].nunique())}
    if FT_CELLS.exists():
        cells = pd.read_parquet(FT_CELLS, columns=["symbol", "entry_date", "text", "ly"] + PRIOR_TRAILING + META)
        cells = cells.dropna(subset=["ly"] + PRIOR_TRAILING).reset_index(drop=True)
        cuts = text_cutoffs(cells["entry_date"])
        sc, tinfo = scored_cells(cells, cuts)
        side["text_resid_7d"] = aggregate_text(rows, sc)
        info["text_folds"] = tinfo
    else:
        side["text_resid_7d"] = np.float32(np.nan)
        info["text_folds"] = "ABSENT: ft_lab/data/cells.parquet not on disk"
    o = Path(out or SIDECAR)
    tmp = o.with_suffix(".tmp.parquet")
    side.to_parquet(tmp, index=False)
    import os
    os.replace(tmp, o)
    info.update({"rows": int(len(side)), "path": str(o), "elapsed_s": round(time.time() - t0, 1),
                 "earn_exp_share": {c: round(float(side[c].mean()), 4) for c in EARN_COLS},
                 "text_coverage": round(float(side["text_resid_7d"].notna().mean()), 4)})
    return info


# ─────────────────────────── members (prediction) ────────────────────────────

def fit_log_member(logvol: np.ndarray, extra: np.ndarray, y_abs: np.ndarray) -> np.ndarray:
    """OLS of log|y| on [1, log vol, extra] -> coefficients (the member is vol x exp(b x extra))."""
    m = np.isfinite(logvol) & np.isfinite(extra) & np.isfinite(y_abs) & (y_abs > 0)
    X = np.c_[np.ones(m.sum()), logvol[m], extra[m]]
    beta, *_ = np.linalg.lstsq(X, np.log(y_abs[m] + 1e-4), rcond=None)
    return beta


def predict_log_member(beta: np.ndarray, logvol: np.ndarray, extra: np.ndarray) -> np.ndarray:
    e = np.nan_to_num(extra, nan=0.0)
    return np.exp(beta[0] + beta[1] * logvol + beta[2] * e)


# ─────────────────────────── size walk-forward ───────────────────────────────

def evaluate(run_id: str | None = None) -> dict:
    from nn_lab import evaluate as E
    from nn_lab import models as M
    from nn_lab.splits import walk_forward_folds
    from nn_lab.table import GROUPS
    t0 = time.time()
    run_id = run_id or f"size_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    feats = [c for g in GROUPS.values() for c in g]
    df = pd.read_parquet(C.TABLE_PATH, columns=["date", "symbol", "on_grid", "dead"] + feats
                         + [f"y_{h}" for h in C.MAGNITUDE_HORIZONS])
    df = df[df["on_grid"]].reset_index(drop=True)
    side = pd.read_parquet(SIDECAR)
    df = df.merge(side, on=["date", "symbol"], how="left")
    df = df.sort_values(["date", "symbol"], kind="mergesort").reset_index(drop=True)
    cal = pd.DatetimeIndex(pd.read_parquet(C.TABLE_PATH.parent / "calendar.parquet")["date"])
    folds = walk_forward_folds(df["date"].unique(), cal)
    groups_all = list(GROUPS)
    Xall, xn = M.design_matrix(df, groups_all)
    logvol = np.log(df["vol_63"].to_numpy(dtype="float64") + 1e-6)
    parts = []
    finfo = []
    for f in folds:
        tr = df["date"].isin(f.train).values
        te = df["date"].isin(f.test).values
        groups = M.active_groups(df.loc[tr])
        cols = [i for i, n in enumerate(xn) if any(n in GROUPS[g] or n == f"missing_{g}" for g in groups)]
        X = Xall[:, cols]
        o = df.loc[te, ["date", "symbol", "dead"] + [f"y_{h}" for h in C.MAGNITUDE_HORIZONS]
                   + list(EARN_COLS) + [f"earn_real_{h}" for h in C.MAGNITUDE_HORIZONS] + ["text_resid_7d"]].copy()
        fi = {"fold": f.name, "coef": {}}
        for h in C.MAGNITUDE_HORIZONS:
            y = df[f"y_{h}"].to_numpy(dtype="float64")
            ya = np.abs(M.winsorize_by_date(df, f"y_{h}")).astype("float64")
            o[f"vol_{h}"] = np.exp(logvol[te])
            ra = M.fit_ridge(X[tr], ya[tr])
            o[f"ridge_abs_{h}"] = ra.predict(X[te])
            ec = df[f"earn_exp_{h}"].to_numpy(dtype="float64")
            b = fit_log_member(logvol[tr], ec[tr], np.abs(y[tr]))
            o[f"vol_earn_{h}"] = predict_log_member(b, logvol[te], ec[te])
            fi["coef"][f"earn_h{h}"] = [round(float(x), 4) for x in b]
            Xp = np.c_[X, ec[:, None]]
            rp = M.fit_ridge(Xp[tr], ya[tr])
            o[f"ridge_abs_plus_{h}"] = rp.predict(Xp[te])
            txt = df["text_resid_7d"].to_numpy(dtype="float64")
            if np.isfinite(txt[tr]).sum() > 2000:
                bt = fit_log_member(logvol[tr], txt[tr], np.abs(y[tr]))
                o[f"vol_text_{h}"] = predict_log_member(bt, logvol[te], txt[te])
                fi["coef"][f"text_h{h}"] = [round(float(x), 4) for x in bt]
            else:
                # not enough news before this fold: the member is the vol baseline itself
                o[f"vol_text_{h}"] = o[f"vol_{h}"]
                fi["coef"][f"text_h{h}"] = "NO_TRAINING_NEWS: equals trailing vol"
        finfo.append(fi)
        parts.append(o)
        print(json.dumps({"fold": f.name, "s": round(time.time() - t0)}), flush=True)
    oos = pd.concat(parts, ignore_index=True)
    res = {"artefact": "NN_LAB_SIZE_WALKFORWARD", "run_id": run_id, "licence": "PRODUCT_EXPERIMENT",
           "target": "|y_h| (excess vs the cross-sectional median), rank IC per date, SE over blocks of max(h,21) sessions",
           "folds": finfo, "by_horizon": {}}
    for h in C.MAGNITUDE_HORIZONS:
        o = oos.copy()
        o["absy"] = o[f"y_{h}"].abs()
        r: dict = {}
        ic = {}
        for m in ("vol", "ridge_abs", "vol_earn", "ridge_abs_plus", "vol_text"):
            ic[m] = E.per_date_ic(o, f"{m}_{h}", "absy")
            r[m] = {"ic": E.block_stats(ic[m], cal, h), "by_year": _by_year(ic[m])}
        for a, b in (("vol_earn", "vol"), ("ridge_abs_plus", "ridge_abs"), ("ridge_abs", "vol"),
                     ("vol_text", "vol")):
            d = (ic[a] - ic[b]).dropna()
            r[f"{a}_minus_{b}"] = {**E.block_stats(d, cal, h), "by_year": _by_year(d)}
        # the text member only where news exists (post-2025 folds): paired on those dates only
        news_rows = o["text_resid_7d"].notna()
        on = o[news_rows]
        if len(on):
            i1 = E.per_date_ic(on, f"vol_text_{h}", "absy")
            i0 = E.per_date_ic(on, f"vol_{h}", "absy")
            d = (i1 - i0).dropna()
            r["vol_text_minus_vol_on_news_rows"] = {**E.block_stats(d, cal, h), "by_year": _by_year(d),
                                                    "rows": int(news_rows.sum())}
        # living names only (the 8-K pull covers survivors)
        lv = o[~o["dead"].astype(bool)]
        i1 = E.per_date_ic(lv, f"vol_earn_{h}", "absy")
        i0 = E.per_date_ic(lv, f"vol_{h}", "absy")
        r["vol_earn_minus_vol_living_only"] = E.block_stats((i1 - i0).dropna(), cal, h)
        # the projection graded against the realised release
        ex, re_ = o[f"earn_exp_{h}"].astype(bool), o[f"earn_real_{h}"].astype(bool)
        r["earnings_projection"] = {
            "share_expected": round(float(ex.mean()), 4), "share_realised": round(float(re_.mean()), 4),
            "precision": round(float(re_[ex].mean()), 4) if ex.any() else None,
            "recall": round(float(ex[re_].mean()), 4) if re_.any() else None,
            "median_abs_move_ratio_expected_vs_not": round(float(
                (o.loc[ex, "absy"] / o.loc[ex, f"vol_{h}"]).median()
                / (o.loc[~ex, "absy"] / o.loc[~ex, f"vol_{h}"]).median()), 4) if ex.any() else None}
        res["by_horizon"][f"h{h}"] = r
    res["text_member_last_year"] = text_member_last_year(df, cal, logvol)
    out_dir = C.OUT / "walkforward"
    out_dir.mkdir(parents=True, exist_ok=True)
    op = out_dir / f"oos_{run_id}.parquet"
    oos.to_parquet(op, index=False)
    res.update({"oos_path": str(op), "elapsed_s": round(time.time() - t0, 1),
                "trust_rule": "reported only; members enter the nightly through FORWARD graded magnitude "
                              "blocks (prior 0), never through this receipt",
                "coverage_caveat": "8-K item 2.02 pull (2026) covers 84% of living and 3% of dead names; "
                                   "uncovered = no earnings expected; no coverage flag is a feature",
                "survivorship_caveat": "PARTIALLY SURVIVOR-SELECTED (table receipt); deaths 2023-26 nearly absent",
                "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    C.RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    (C.RECEIPT_DIR / f"{run_id}.json").write_text(json.dumps(res, indent=1, default=str))
    return res


def text_member_last_year(df: pd.DataFrame, cal: pd.DatetimeIndex, logvol: np.ndarray) -> dict:
    """The text member where news exists: news only starts in 2025, so the calendar-year
    folds above never see a training row with text. Here: the LAST calendar year of the
    table is the test block; the member's one coefficient is fitted on news rows at least
    one embargo (63 sessions) before it; plus the UNFITTED member (k = 1: the text
    residual is already a log-size forecast for the next session)."""
    from nn_lab import evaluate as E
    last_year = int(df["date"].max().year)
    te = (df["date"].dt.year == last_year).values
    p0 = int(np.searchsorted(cal.values, df.loc[te, "date"].min().to_datetime64()))
    cut = cal[max(p0 - C.EMBARGO_SESSIONS, 0)]
    tr = (df["date"] < cut).values
    txt = df["text_resid_7d"].to_numpy(dtype="float64")
    out: dict = {"test_year": last_year, "train_before": str(cut.date()),
                 "train_news_rows": int(np.isfinite(txt[tr]).sum()), "test_news_rows": int(np.isfinite(txt[te]).sum())}
    for h in C.MAGNITUDE_HORIZONS:
        y = np.abs(df[f"y_{h}"].to_numpy(dtype="float64"))
        o = df.loc[te, ["date"]].copy()
        o["absy"] = y[te]
        o["vol"] = np.exp(logvol[te])
        o["k1"] = np.exp(logvol[te] + np.nan_to_num(txt[te], nan=0.0))
        r: dict = {}
        if np.isfinite(txt[tr]).sum() > 500:
            b = fit_log_member(logvol[tr], txt[tr], y[tr])
            o["fit"] = predict_log_member(b, logvol[te], txt[te])
            r["coef"] = [round(float(x), 4) for x in b]
        for sub, mask in (("all_rows", np.ones(len(o), bool)), ("news_rows", np.isfinite(txt[te]))):
            oo = o[mask]
            i0 = E.per_date_ic(oo, "vol", "absy")
            for m in ("k1", "fit"):
                if m in oo:
                    i1 = E.per_date_ic(oo, m, "absy")
                    r[f"{m}_minus_vol_{sub}"] = {**E.block_stats((i1 - i0).dropna(), cal, h),
                                                 "by_month": {str(k): round(float(v), 5) for k, v in
                                                              (i1 - i0).dropna().groupby(
                                                                  pd.DatetimeIndex((i1 - i0).dropna().index)
                                                                  .to_period("M").astype(str)).mean().items()}}
        out[f"h{h}"] = r
    return out


def _by_year(s: pd.Series) -> dict:
    s = s.dropna()
    if s.empty:
        return {}
    return {str(k): round(float(v), 5) for k, v in s.groupby(pd.DatetimeIndex(s.index).year).mean().items()}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "evaluate"])
    a = ap.parse_args()
    r = build() if a.cmd == "build" else evaluate()
    print(json.dumps(r, indent=1, default=str)[:12000])


# ─────────────────────────── the nightly members ─────────────────────────────

def member_roster() -> tuple[str, ...]:
    return tuple(C.SIZE_MEMBER_ROSTER) if C.SIZE_MEMBERS_NIGHTLY else ()


def nightly_member_predictions(live: pd.DataFrame, *, table_path: Path | None = None,
                               sidecar: Path | None = None, horizons=C.MAGNITUDE_HORIZONS) -> dict:
    """{member: {h: pred_abs array aligned with `live`}} for the newest decision date.

    Each member's coefficients are an OLS of log|y_h| on [1, log vol_63, x] over every
    LABELLED grid row (label window elapsed) in the table, where x is the member's input
    (earn_exp_h or text_resid_7d, NaN read as 0 = no view). The live rows' inputs come from
    the sidecar, which `build()` recomputes nightly from releases known strictly before t."""
    tp = Path(table_path or C.TABLE_PATH)
    sc = pd.read_parquet(sidecar or SIDECAR)
    cal = pd.DatetimeIndex(pd.read_parquet(tp.parent / "calendar.parquet")["date"])
    tab = pd.read_parquet(tp, columns=["date", "symbol", "on_grid", "vol_63"] + [f"y_{h}" for h in horizons])
    tab = tab[tab["on_grid"]].merge(sc, on=["date", "symbol"], how="left")
    live = live[["symbol", "date", "vol_63"]].merge(sc, on=["date", "symbol"], how="left")
    lv_live = np.log(live["vol_63"].to_numpy(dtype="float64") + 1e-6)
    out: dict = {"_coef": {}}
    for h in horizons:
        pos = np.searchsorted(cal.values, tab["date"].values)
        done = (pos + 1 + h) < len(cal)
        t = tab[done]
        lv = np.log(t["vol_63"].to_numpy(dtype="float64") + 1e-6)
        y = np.abs(t[f"y_{h}"].to_numpy(dtype="float64"))
        for m, col in (("vol_earn", f"earn_exp_{h}"), ("vol_text", "text_resid_7d")):
            if m not in member_roster():
                continue
            x = t[col].to_numpy(dtype="float64")
            if np.isfinite(x).sum() < 500:
                b = np.array([np.nan, np.nan, np.nan])
                pred = np.full(len(live), np.nan)
            else:
                b = fit_log_member(lv, np.nan_to_num(x, nan=0.0) if m == "vol_earn" else x, y)
                pred = predict_log_member(b, lv_live, live[col].to_numpy(dtype="float64"))
            out.setdefault(m, {})[h] = pred
            out["_coef"][f"{m}_h{h}"] = [round(float(v), 5) for v in b]
    return out
