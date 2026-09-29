"""Size-of-move metrics, with standard errors over DATE BLOCKS (weeks), never over rows.

Every IC is a per-date cross-sectional Spearman correlation, averaged over dates. Its SE
comes from weekly means (dates inside a week share news cycles, so they are not
independent). MDE = 2.8 x SE (two-sided 5%, 80% power), printed beside every t.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from ft_lab import config as C

MIN_CELLS_PER_DATE = 8


def _per_date_ic(df: pd.DataFrame, pred: str, target: str) -> pd.Series:
    out = {}
    for d, g in df.groupby("entry_date"):
        g = g[[pred, target]].dropna()
        if len(g) < MIN_CELLS_PER_DATE or g[pred].nunique() < 2:
            continue
        out[d] = spearmanr(g[pred], g[target]).statistic
    return pd.Series(out, dtype=float)


def block_stats(per_date: pd.Series, weeks: pd.Series | None = None) -> dict:
    """Mean of a per-date series with SE from weekly block means."""
    s = per_date.dropna()
    if s.empty:
        return {"mean": None, "se": None, "t": None, "mde": None, "n_dates": 0, "n_blocks": 0}
    idx = pd.to_datetime(pd.Index(s.index))
    wk = idx.to_period("W-FRI").astype(str) if weeks is None else weeks
    blocks = s.groupby(np.asarray(wk)).mean()
    nb = len(blocks)
    se = float(blocks.std(ddof=1) / np.sqrt(nb)) if nb > 1 else None
    m = float(s.mean())
    return {"mean": round(m, 4), "se": None if se is None else round(se, 4),
            "t": None if not se else round(m / se, 2),
            "mde": None if se is None else round(2.8 * se, 4),
            "n_dates": int(len(s)), "n_blocks": int(nb)}


def ic(df: pd.DataFrame, pred: str, target: str = "y") -> dict:
    per = _per_date_ic(df, pred, target)
    res = block_stats(per)
    res["pooled_spearman"] = round(float(spearmanr(df[pred], df[target], nan_policy="omit").statistic), 4)
    by_month = per.groupby(pd.Index(per.index).str[:7]).mean()
    res["by_month"] = {k: round(float(v), 4) for k, v in by_month.items()}
    if len(by_month) > 1:
        loo = {m: float(per[~pd.Index(per.index).str.startswith(m)].mean()) for m in by_month.index}
        res["loo_month_worst"] = round(min(loo.values()), 4)
    return res


def ic_increment(df: pd.DataFrame, pred_a: str, pred_b: str, target: str = "y") -> dict:
    """Paired per-date IC(a) - IC(b)."""
    a = _per_date_ic(df, pred_a, target)
    b = _per_date_ic(df, pred_b, target)
    common = a.index.intersection(b.index)
    d = a[common] - b[common]
    res = block_stats(d)
    by_month = d.groupby(pd.Index(d.index).str[:7]).mean()
    res["by_month"] = {k: round(float(v), 4) for k, v in by_month.items()}
    res["share_of_months_positive"] = round(float((by_month > 0).mean()), 3) if len(by_month) else None
    return res


def tercile_accuracy(df: pd.DataFrame, pred: str, target: str = "y") -> dict:
    """Within each date, rank prediction and outcome into terciles; accuracy vs 1/3 chance,
    with the weekly-block SE."""
    per = {}
    for d, g in df.groupby("entry_date"):
        g = g[[pred, target]].dropna()
        if len(g) < MIN_CELLS_PER_DATE:
            continue
        pt = pd.qcut(g[pred].rank(method="first"), 3, labels=False)
        yt = pd.qcut(g[target].rank(method="first"), 3, labels=False)
        per[d] = float((pt == yt).mean())
    s = pd.Series(per, dtype=float)
    r = block_stats(s - 1.0 / 3.0)
    return {"accuracy": None if r["mean"] is None else round(r["mean"] + 1 / 3, 4),
            "minus_chance": r["mean"], "se": r["se"], "t": r["t"], "mde": r["mde"],
            "n_dates": r["n_dates"]}


def bucket_of(y: np.ndarray) -> np.ndarray:
    return np.asarray(pd.cut(pd.Series(y), C.MAG_EDGES, right=False, labels=C.MAG_NAMES).astype(str))


def abs_bucket_accuracy(true_bucket: pd.Series, pred_bucket: pd.Series) -> dict:
    t = np.asarray(true_bucket).astype(str)
    p = np.asarray(pred_bucket).astype(str)
    order = {n: i for i, n in enumerate(C.MAG_NAMES)}
    ti = np.array([order.get(x, -9) for x in t])
    pi = np.array([order.get(x, -9) for x in p])
    ok = (ti >= 0) & (pi >= 0)
    return {"n": int(ok.sum()), "exact": round(float((ti[ok] == pi[ok]).mean()), 4),
            "within_one": round(float((np.abs(ti[ok] - pi[ok]) <= 1).mean()), 4),
            "majority_class_rate": round(float(pd.Series(t[ok]).value_counts(normalize=True).iloc[0]), 4)}


def summarize(df: pd.DataFrame, preds: list[str], prior: str) -> dict:
    """IC vs |move|, IC vs relative move (move / trailing vol), tercile accuracy and the
    paired increment over `prior`, for each prediction column."""
    out = {}
    for p in preds:
        out[p] = {"ic_abs_move": ic(df, p, "y"),
                  "ic_relative_move": ic(df, p, "rel"),
                  "tercile": tercile_accuracy(df, p, "y")}
        if p != prior:
            out[p]["increment_over_prior"] = ic_increment(df, p, prior, "y")
    return out
