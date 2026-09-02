"""Grading. Rank IC, calibration, spread, and the metric that actually decides.

THE DECISION METRIC IS TERMINAL WEALTH
======================================
Rank IC is diagnostic; a monthly book's terminal wealth is the decision. The
house learned this expensively: a strategy with mean +0.147% per window
compounded to 0.1x, because the mean of a fat-tailed ratio is not the thing you
end up holding. So every arm is graded on all four -- rank IC, calibration,
decile spread, terminal wealth -- and RANKED on terminal wealth.

THE n IS MONTHS, NOT NAME-MONTHS
================================
A cross-sectional IC computed on 441,278 rows has 144 independent draws, not
441,278. Every t-statistic here divides by sqrt(number of MONTHS) -- the DATE
BLOCK count (CANON §58) -- and the month count is printed beside it so nobody
has to trust that it was done.

COSTS ARE NEVER ZERO
====================
10 bps per side on MEASURED turnover, both sides, following the convention in
`scripts/tracker_ibes_backtest.basket` -- generalised from a name-count
turnover to a weight turnover because these books are value-weighted. Gross is
reported beside net; the cost rate is quoted with every count.

TIES ARE BROKEN BY A SEEDED HASH, NOT BY permno
===============================================
The `prior` baseline emits FOUR distinct values and `constant` emits one, so
"top 50 by prediction" is mostly or entirely a tie for them. The obvious
tie-break -- permno ascending -- is NOT neutral: low permnos are the OLDEST
LISTINGS, and the farm's null of the ten oldest listings beat 13 of 15 real
signals. Breaking ties that way would hand every tied baseline a known
survivorship premium and would make the ML arms look worse than they are for a
reason that has nothing to do with either. Ties are broken on a seeded integer
hash of (permno, month): reproducible, and uncorrelated with listing age.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

COST_BPS_PER_SIDE = 10.0
TIE_SEED = 20260902
#: Execution floor from the house's universe rules: below this a name is
#: OBSERVE_ONLY, so a book that holds it is a backtest of something unbuyable.
TRADABLE_DOLLAR_VOL = 3_000_000.0

ERAS: dict[str, tuple[int, int]] = {
    "2016-2018": (2016, 2018),
    "2019-2021": (2019, 2021),
    "2022-2024": (2022, 2024),
}


def _t_from_series(s: pd.Series) -> float | None:
    s = s.dropna()
    if len(s) < 3 or s.std() == 0:
        return None
    return float(s.mean() / (s.std(ddof=1) / np.sqrt(len(s))))


# ------------------------------------------------------------------ rank IC

def rank_ic(df: pd.DataFrame, pred_col: str, y_col: str,
            month_col: str = "month", min_names: int = 20) -> dict:
    """Cross-sectional Spearman per month; t across MONTHS."""
    ics = []
    for m, chunk in df.groupby(month_col, sort=True):
        sub = chunk[[pred_col, y_col]].dropna()
        if len(sub) < min_names or sub[pred_col].nunique() < 2:
            continue
        rho = stats.spearmanr(sub[pred_col], sub[y_col]).statistic
        if np.isfinite(rho):
            ics.append((m, float(rho)))
    if not ics:
        return {"months": 0, "note": "no month had enough names or enough distinct predictions"}
    s = pd.Series({m: v for m, v in ics})
    t = _t_from_series(s)
    return {
        "months": int(len(s)),                    # the n. DATE BLOCKS.
        "mean_ic": round(float(s.mean()), 5),
        "median_ic": round(float(s.median()), 5),
        "t_stat": round(t, 3) if t is not None else None,
        "share_months_positive": round(float((s > 0).mean()), 4),
    }


# -------------------------------------------------------------- calibration

def decile_table(df: pd.DataFrame, pred_col: str, y_col: str,
                 month_col: str = "month", n_bins: int = 10) -> list[dict]:
    """Predicted vs realised, by prediction decile cut WITHIN each month.

    Cut per month, never pooled: a full-sample quantile is lookahead, and a
    pooled cut on a decade of drifting prediction scale is not a decile of
    anything a desk could have formed.
    """
    d = df[[month_col, pred_col, y_col]].dropna().copy()
    if d.empty:
        return []
    d["_bin"] = d.groupby(month_col)[pred_col].transform(
        lambda s: pd.qcut(s.rank(method="first"), min(n_bins, max(2, s.nunique())),
                          labels=False, duplicates="drop") if s.nunique() > 1 else np.nan)
    d = d.dropna(subset=["_bin"])
    rows = []
    for b, chunk in d.groupby("_bin", sort=True):
        rows.append({
            "decile": int(b) + 1,
            "n": int(len(chunk)),
            "mean_predicted": round(float(chunk[pred_col].mean()), 5),
            "mean_realized": round(float(chunk[y_col].mean()), 5),
            "median_realized": round(float(chunk[y_col].median()), 5),
        })
    return rows


def calibration_slope(table: list[dict]) -> dict:
    """Regress realised on predicted across deciles. Slope 1 = calibrated;
    slope < 0 means the model orders the wrong way at the level of magnitude
    even if its rank IC is positive (T13 saw exactly that: 'the model orders
    better than it prices')."""
    if len(table) < 3:
        return {"note": "too few deciles"}
    x = np.array([r["mean_predicted"] for r in table])
    y = np.array([r["mean_realized"] for r in table])
    if np.std(x) == 0:
        return {"note": "prediction is constant across deciles -- not calibratable"}
    res = stats.linregress(x, y)
    return {"slope": round(float(res.slope), 3), "intercept": round(float(res.intercept), 5),
            "r_squared": round(float(res.rvalue ** 2), 3)}


def top_minus_bottom(df: pd.DataFrame, pred_col: str, y_col: str,
                     month_col: str = "month", n_bins: int = 10) -> dict:
    """Monthly (top decile - bottom decile) of REALISED excess, and its t."""
    d = df[[month_col, pred_col, y_col]].dropna().copy()
    if d.empty:
        return {"months": 0}
    per = []
    for m, chunk in d.groupby(month_col, sort=True):
        if len(chunk) < n_bins * 5 or chunk[pred_col].nunique() < 2:
            continue
        q = chunk[pred_col].rank(method="first", pct=True)
        top = chunk.loc[q > 1 - 1.0 / n_bins, y_col].mean()
        bot = chunk.loc[q <= 1.0 / n_bins, y_col].mean()
        if np.isfinite(top) and np.isfinite(bot):
            per.append((m, float(top - bot)))
    if not per:
        return {"months": 0}
    s = pd.Series({m: v for m, v in per})
    t = _t_from_series(s)
    return {"months": int(len(s)),
            "mean_monthly_spread": round(float(s.mean()), 5),
            "annualised_spread": round(float(s.mean()) * 12, 4),
            "t_stat": round(t, 3) if t is not None else None,
            "share_months_positive": round(float((s > 0).mean()), 4)}


# ------------------------------------------------------------------- books

def book(df: pd.DataFrame, pred_col: str, k: int = 50, weight: str = "vw",
         cost_bps: float = COST_BPS_PER_SIDE, ret_col: str = "fwd_1m",
         mkt_col: str = "mkt_vw_1m", month_col: str = "month",
         tradable_floor: float | None = None) -> dict:
    """Monthly top-k book, value- or equal-weighted, net of measured turnover.

    Returns terminal wealth NET and GROSS, the market's terminal wealth over
    exactly the same months, and the PAIRED monthly excess -- because comparing
    two terminal wealths is one draw of a correlated pair, not a test.
    """
    cols = [month_col, "permno", pred_col, ret_col, mkt_col, "market_cap"]
    if tradable_floor is not None:
        cols += ["dollar_vol_20d", "log_dollar_vol_20d"]
    d = df[[c for c in cols if c in df.columns]].dropna(
        subset=[pred_col, ret_col, mkt_col]).copy()
    if tradable_floor is not None:
        # A GATE THAT CANNOT FIRE IS A BROKEN GATE. The first version of this
        # asked for `dollar_vol_20d`, which the training table does not carry
        # (it stores the LOG), found the column absent, and skipped the filter
        # in silence -- so `book_top50_vw_tradable_3m` was byte-identical to the
        # unfiltered book and read as "the floor removed nothing". It DERIVES
        # its input now, or REFUSES.
        if "dollar_vol_20d" in d.columns and d["dollar_vol_20d"].notna().any():
            dv = d["dollar_vol_20d"]
        elif "log_dollar_vol_20d" in d.columns:
            dv = np.expm1(d["log_dollar_vol_20d"])
        else:
            raise SystemExit(
                "REFUSED: a tradable floor was requested and neither `dollar_vol_20d` nor "
                "`log_dollar_vol_20d` is present. A liquidity gate with no liquidity column "
                "silently passes everything.")
        d = d[dv.to_numpy() >= tradable_floor]
    if d.empty:
        return {"months": 0, "note": "no rows"}

    # Seeded tie-break. NOT permno ascending -- that is listing age, and the
    # farm's oldest-listings null beat 13 of 15 real signals.
    mo = d[month_col].astype(str).str.replace("-", "", regex=False).astype("int64")
    d["_tb"] = (d["permno"].astype("int64") * 2_654_435_761 + mo * 97 + TIE_SEED) % 1_000_003

    rets, mkts, weights_by_month, names_per_month = {}, {}, {}, {}
    for m, chunk in d.groupby(month_col, sort=True):
        sel = chunk.sort_values([pred_col, "_tb"], ascending=[False, True]).head(k)
        if sel.empty:
            continue
        if weight == "vw" and "market_cap" in sel.columns and sel["market_cap"].notna().any():
            w = sel["market_cap"].fillna(sel["market_cap"].median()).clip(lower=0)
            w = w / w.sum() if w.sum() > 0 else pd.Series(1.0 / len(sel), index=sel.index)
        else:
            w = pd.Series(1.0 / len(sel), index=sel.index)
        rets[m] = float((w * sel[ret_col]).sum())
        mkts[m] = float(sel[mkt_col].iloc[0])
        weights_by_month[m] = dict(zip(sel["permno"].astype(int), w.to_numpy()))
        names_per_month[m] = int(len(sel))

    if not rets:
        return {"months": 0, "note": "no month produced a book"}
    gross = pd.Series(rets).sort_index()
    market = pd.Series(mkts).sort_index()

    # Weight turnover: the generalisation of the script's name-count turnover.
    turn, prev = [], None
    for m in gross.index:
        cur = weights_by_month[m]
        if prev is None:
            turn.append(1.0)
        else:
            keys = set(cur) | set(prev)
            turn.append(0.5 * sum(abs(cur.get(kk, 0.0) - prev.get(kk, 0.0)) for kk in keys))
        prev = cur
    turnover = pd.Series(turn, index=gross.index)
    cost = turnover * (cost_bps / 10_000.0) * 2.0          # both sides
    net = gross - cost

    spread = (net - market).dropna()
    t = _t_from_series(spread)
    yrs = len(net) / 12.0
    tw = float((1.0 + net).prod())
    twg = float((1.0 + gross).prod())
    twm = float((1.0 + market).prod())
    return {
        "months": int(len(net)),
        "k": k, "weight": weight,
        "cost_bps_per_side": cost_bps,
        "tradable_floor_usd": tradable_floor,
        "rows_after_tradable_floor": int(len(d)),
        "mean_names_per_month": round(float(np.mean(list(names_per_month.values()))), 1),
        "mean_turnover": round(float(turnover.mean()), 3),
        "terminal_wealth_net": round(tw, 4),
        "terminal_wealth_gross": round(twg, 4),
        "terminal_wealth_market_same_months": round(twm, 4),
        "cagr_net": round(tw ** (1 / yrs) - 1.0, 4) if yrs > 0 and tw > 0 else None,
        "cagr_market": round(twm ** (1 / yrs) - 1.0, 4) if yrs > 0 and twm > 0 else None,
        "mean_monthly_excess": round(float(spread.mean()), 5),
        "annualised_excess": round(float(spread.mean()) * 12, 4),
        "t_stat_paired_vs_market": round(t, 3) if t is not None else None,
        "months_beating_market": round(float((spread > 0).mean()), 4),
        "worst_month_net": round(float(net.min()), 4),
        "hit_rate": round(float((net > 0).mean()), 4),
    }


# --------------------------------------------------------------- the grader

def grade(df: pd.DataFrame, pred_col: str, horizon_months: int,
          benchmark: str = "vw", is_calibrated: bool = True,
          with_books: bool = True, k: int = 50) -> dict:
    """Every metric for one arm's predictions over the pooled OOS test rows."""
    h = horizon_months
    y = f"excess_{benchmark}_{h}m"
    out: dict = {"rank_ic": rank_ic(df, pred_col, y)}
    if is_calibrated:
        tab = decile_table(df, pred_col, y)
        out["decile_table"] = tab
        out["calibration"] = calibration_slope(tab)
    else:
        out["calibration"] = {"note": "rank-only ruler -- output is a percentile, not a return"}
    out["top_minus_bottom_decile"] = top_minus_bottom(df, pred_col, y)

    if with_books and h == 1:
        out["book_top50_vw"] = book(df, pred_col, k=k, weight="vw")
        out["book_top50_ew"] = book(df, pred_col, k=k, weight="ew")
        out["book_top50_vw_tradable_3m"] = book(df, pred_col, k=k, weight="vw",
                                                tradable_floor=TRADABLE_DOLLAR_VOL)
    return out


def grade_by_era(df: pd.DataFrame, pred_col: str, horizon_months: int,
                 benchmark: str = "vw") -> dict:
    y = f"excess_{benchmark}_{horizon_months}m"
    out = {}
    for era, (lo, hi) in ERAS.items():
        sub = df[(df["entry_date"].dt.year >= lo) & (df["entry_date"].dt.year <= hi)]
        if sub.empty:
            continue
        row = {"rank_ic": rank_ic(sub, pred_col, y)}
        if horizon_months == 1:
            b = book(sub, pred_col, k=50, weight="vw")
            row["book_top50_vw"] = {kk: b.get(kk) for kk in
                                    ("months", "terminal_wealth_net",
                                     "terminal_wealth_market_same_months",
                                     "annualised_excess", "t_stat_paired_vs_market")}
        out[era] = row
    return out


def grade_by_band(df: pd.DataFrame, pred_col: str, horizon_months: int,
                  benchmark: str = "vw") -> dict:
    """THE HONEST TEST. Inside the admissible region the engine says one
    constant (+5.74%/yr for 1.5-3), and S33 found six simple features EMPTY
    there -- every Fama-MacBeth |t| < 1.5 over 143 months. If the learner's
    richer features add nothing HERE, the constants-per-band stance survives
    and the learner's whole contribution is across bands, which the band prior
    already does."""
    y = f"excess_{benchmark}_{horizon_months}m"
    out: dict = {}
    adm = df[df["in_admissible"].astype(bool)]
    out["ADMISSIBLE_REGION_ratio_1_5_to_5"] = {
        "n_rows": int(len(adm)),
        "rank_ic": rank_ic(adm, pred_col, y),
        "top_minus_bottom_decile": top_minus_bottom(adm, pred_col, y),
    }
    if horizon_months == 1 and len(adm):
        b = book(adm, pred_col, k=50, weight="vw")
        out["ADMISSIBLE_REGION_ratio_1_5_to_5"]["book_top50_vw_within_region"] = {
            kk: b.get(kk) for kk in ("months", "terminal_wealth_net",
                                     "terminal_wealth_market_same_months",
                                     "annualised_excess", "t_stat_paired_vs_market")}
    for band, chunk in df.groupby("band", sort=True):
        out[f"band_{band}"] = {"n_rows": int(len(chunk)),
                               "rank_ic": rank_ic(chunk, pred_col, y)}
    return out


__all__ = ["COST_BPS_PER_SIDE", "TRADABLE_DOLLAR_VOL", "ERAS", "rank_ic", "decile_table",
           "calibration_slope", "top_minus_bottom", "book", "grade", "grade_by_era",
           "grade_by_band"]
