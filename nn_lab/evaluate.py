"""Out-of-sample metrics. Every standard error is over DATE BLOCKS, never rows.

A block is `max(h, 21)` sessions wide, so two blocks share almost no forward
window at h <= 21 and at h = 63 a block is one whole horizon (still optimistic
by up to sqrt(2), as xs_ranker.top_k_backtest documents; `n_blocks_strict`
counts the 2h-wide blocks that cannot share a window).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from nn_lab import config as C


def band_cost_bps(med_dv: np.ndarray) -> np.ndarray:
    m = np.asarray(med_dv, dtype="float64")
    out = np.full(m.shape, C.COST_BPS_BY_BAND["small"])
    out[m >= 2e7] = C.COST_BPS_BY_BAND["mid"]
    out[m >= 1e8] = C.COST_BPS_BY_BAND["large"]
    out[m >= 1e9] = C.COST_BPS_BY_BAND["mega"]
    return out


def per_date_ic(df: pd.DataFrame, score: str, label: str) -> pd.Series:
    d = df[["date", score, label]].dropna()
    if d.empty:
        return pd.Series(dtype=float)
    r = d.groupby("date")[[score, label]].rank()
    r["date"] = d["date"].values
    def _c(g):
        if len(g) < 10:
            return np.nan
        return np.corrcoef(g[score], g[label])[0, 1]
    return r.groupby("date").apply(_c, include_groups=False).dropna()


def block_stats(by_date: pd.Series, cal: pd.DatetimeIndex, h: int) -> dict:
    s = by_date.dropna()
    if s.empty:
        return {"mean": None, "se": None, "t": None, "n_dates": 0, "n_blocks": 0}
    pos = np.searchsorted(cal.values, pd.DatetimeIndex(s.index).values)
    width = max(h, 21)
    bm = s.groupby(pos // width).mean()
    n_strict = int(pd.Series(pos // (2 * max(h, 21))).nunique())
    se = float(bm.std(ddof=1) / math.sqrt(len(bm))) if len(bm) > 1 else float("nan")
    mean = float(s.mean())
    return {"mean": round(mean, 5), "se": round(se, 5) if np.isfinite(se) else None,
            "t": round(mean / se, 2) if np.isfinite(se) and se > 0 else None,
            "n_dates": int(len(s)), "n_blocks": int(len(bm)), "n_blocks_strict": n_strict}


def hold_end(dates, cal: pd.DatetimeIndex, h: int) -> pd.DatetimeIndex:
    """Session the h-session hold ENDS on (entry t+1, exit t+1+h); beyond the
    known calendar, business days are used."""
    d = pd.DatetimeIndex(dates)
    pos = np.searchsorted(cal.values, d.values) + 1 + h
    out = np.empty(len(d), dtype="datetime64[ns]")
    inside = pos < len(cal)
    out[inside] = cal.values[pos[inside]]
    if (~inside).any():
        out[~inside] = (d[~inside] + pd.offsets.BDay(1 + h)).values
    return pd.DatetimeIndex(out)


def topk_series(df: pd.DataFrame, score: str, label: str, k: int = C.TOP_K) -> pd.DataFrame:
    """Per date: top-k equal weight minus the panel's random (all-eligible) portfolio,
    both net of the library band round-trip costs (one round trip per hold)."""
    d = df[["date", score, label, "med_dv"]].dropna(subset=[score, label]).copy()
    d["cost"] = band_cost_bps(d["med_dv"].values) / 1e4
    rows = []
    for dt, g in d.groupby("date"):
        if len(g) < 5 * k:
            continue
        top = g.nlargest(k, score)
        net_top = float(top[label].mean() - top["cost"].mean())
        rnd = float(g[label].mean() - g["cost"].mean())
        rows.append((dt, float(top[label].mean()), net_top, rnd, net_top - rnd))
    return pd.DataFrame(rows, columns=["date", "gross_top", "net_top", "net_random", "spread"]).set_index("date")


def year_views(by_date: pd.Series, cal: pd.DatetimeIndex, h: int) -> dict:
    """By HOLD-END year and month, leave-one-year-out, and without the best 5 hold months."""
    s = by_date.dropna()
    if s.empty:
        return {}
    he = hold_end(s.index, cal, h)
    yr = pd.Series(s.values, index=he.year)
    mo = pd.Series(s.values, index=he.to_period("M").astype(str))
    by_year = {int(y): round(float(v), 5) for y, v in yr.groupby(level=0).mean().items()}
    loyo = {int(y): round(float(yr[yr.index != y].mean()), 5) for y in by_year if (yr.index != y).sum() > 0}
    mm = mo.groupby(level=0).mean().sort_values()
    best5 = list(mm.index[-5:])
    wo = float(mo[~mo.index.isin(best5)].mean()) if len(mm) > 5 else None
    return {"by_hold_year": by_year, "leave_one_year_out": loyo,
            "loyo_worst": round(min(loyo.values()), 5) if loyo else None,
            "best_5_hold_months": best5,
            "mean_without_best_5_months": round(wo, 5) if wo is not None else None,
            "share_positive_hold_months": round(float((mm > 0).mean()), 3)}


def reliability(prob: np.ndarray, outcome: np.ndarray, bins: int = 10) -> dict:
    p = np.asarray(prob, dtype="float64")
    o = np.asarray(outcome, dtype="float64")
    m = np.isfinite(p) & np.isfinite(o)
    p, o = p[m], o[m]
    if len(p) == 0:
        return {}
    base = float(o.mean())
    brier = float(np.mean((p - o) ** 2))
    brier_base = float(np.mean((base - o) ** 2))
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    table = []
    for b in range(bins):
        mb = idx == b
        if mb.sum() == 0:
            continue
        table.append({"bin": f"{edges[b]:.1f}-{edges[b+1]:.1f}", "n": int(mb.sum()),
                      "mean_prob": round(float(p[mb].mean()), 4), "hit_rate": round(float(o[mb].mean()), 4)})
    return {"brier": round(brier, 5), "brier_base_rate": round(brier_base, 5),
            "brier_skill": round(1 - brier / brier_base, 5) if brier_base > 0 else None,
            "base_rate": round(base, 4), "n": int(len(p)), "table": table}


def coverage(y: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> float | None:
    y, lo, hi = (np.asarray(a, dtype="float64") for a in (y, lo, hi))
    m = np.isfinite(y) & np.isfinite(lo) & np.isfinite(hi)
    return round(float(((y[m] >= lo[m]) & (y[m] <= hi[m])).mean()), 4) if m.any() else None


def reliability_weight(t_ic: float | None) -> float:
    """How much a component's mean is trusted: t^2 / (t^2 + 4), floored at 0.05.

    A weak model gets a SMALL weight, not no weight; a negative t gets the floor
    (its sign is not trusted, its existence is logged)."""
    if t_ic is None or not np.isfinite(t_ic) or t_ic <= 0:
        return 0.05
    return round(max(0.05, t_ic ** 2 / (t_ic ** 2 + 4.0)), 4)


def verdict(ic: dict, spread: dict, views: dict, resid_ic: dict | None) -> str:
    """ALPHA_DETECTED / CANNOT_DISTINGUISH / BETA_EXPLAINS / FAILED_VARIANT."""
    t = ic.get("t")
    st = spread.get("t")
    if t is None or ic.get("mean") is None:
        return "FAILED_VARIANT"
    if ic["mean"] <= 0 or (spread.get("mean") is not None and spread["mean"] <= 0 and (t or 0) < 2):
        return "FAILED_VARIANT"
    if resid_ic and resid_ic.get("mean") is not None and ic["mean"] > 0 \
            and resid_ic["mean"] < 0.5 * ic["mean"]:
        return "BETA_EXPLAINS"
    if (t >= 3 and (st or 0) >= 2 and (views.get("loyo_worst") or -1) > 0
            and (views.get("mean_without_best_5_months") or -1) > 0):
        return "ALPHA_DETECTED"
    return "CANNOT_DISTINGUISH"
