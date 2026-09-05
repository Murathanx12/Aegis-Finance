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

def monthly_ic_series(df: pd.DataFrame, pred_col: str, y_col: str,
                      month_col: str = "month", min_names: int = 20) -> pd.Series:
    """The per-month rank IC series itself -- what `rank_ic` collapses to a t.

    Exposed because the t is only honest once the OVERLAP in the target is
    accounted for, and that correction needs the series, not the summary.
    """
    out = {}
    for m, chunk in df.groupby(month_col, sort=True):
        sub = chunk[[pred_col, y_col]].dropna()
        if len(sub) < min_names or sub[pred_col].nunique() < 2:
            continue
        rho = stats.spearmanr(sub[pred_col], sub[y_col]).statistic
        if np.isfinite(rho):
            out[m] = float(rho)
    return pd.Series(out).sort_index()


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
         tradable_floor: float | None = None, hold_k: int | None = None,
         with_risk: bool = False, return_series: bool = False) -> dict:
    """Monthly top-k book, value- or equal-weighted, net of measured turnover.

    Returns terminal wealth NET and GROSS, the market's terminal wealth over
    exactly the same months, and the PAIRED monthly excess -- because comparing
    two terminal wealths is one draw of a correlated pair, not a test.

    HYSTERESIS (`hold_k`), and why it is the cheapest thing in this file.
    ---------------------------------------------------------------------
    With `hold_k = None` the book is rebuilt from scratch every month: a name
    that slips from rank 50 to rank 51 is sold and a name at rank 50 is bought,
    and BOTH sides pay. Measured turnover on the top-50 books runs near 1.0 a
    month, so at 25 bps a side the cost line alone is ~6%/yr -- which is larger
    than most of the edges this repo has ever measured, and is why several
    "signals" die between 10 and 25 bps.

    `hold_k` makes the rule asymmetric: BUY at rank <= k, HOLD until rank >
    `hold_k`. Nothing about the prediction changes; only the number of times the
    book pays the spread. It is not a way to make a null look positive -- a
    signal with no edge has nothing to hold on to, and its net simply moves
    toward its gross -- but it is the difference between an edge that survives
    costs and one that is eaten by them.

    Requires `hold_k > k`; `hold_k == k` is the no-hysteresis rule written a
    longer way, and a band that is not a band would read as one in the receipt.

    v2 additions, all OFF by default so v1's receipt is reproduced byte for
    byte: `with_risk` appends the drawdown/tail block, `return_series` appends
    the monthly net and market series under `_series` so a caller can run a
    PAIRED difference test between two arms (which is the only honest way to
    ask "did v2 beat v1?" -- two terminal wealths are one draw).
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

    if hold_k is not None and int(hold_k) <= int(k):
        raise SystemExit(
            f"REFUSED: hold_k={hold_k} must be strictly greater than k={k}. A hold band "
            "that is not wider than the buy rank is the no-hysteresis rule written a "
            "longer way, and the receipt would report a band where there is none.")

    rets, mkts, weights_by_month, names_per_month = {}, {}, {}, {}
    held: set[int] = set()
    for m, chunk in d.groupby(month_col, sort=True):
        ranked = chunk.sort_values([pred_col, "_tb"], ascending=[False, True])
        if hold_k is None:
            sel = ranked.head(k)
        else:
            # BUY at rank <= k, HOLD until rank > hold_k. Incumbents inside the
            # band keep their slots (best-ranked first, so the book never holds a
            # worse name in preference to a better incumbent); the remainder is
            # filled from the top of the ranking. Book size stays k, so the only
            # thing hysteresis changes is how often the book pays the spread.
            band = ranked.head(int(hold_k))
            keep = band[band["permno"].astype("int64").isin(held)].head(k)
            fill = ranked[~ranked["permno"].astype("int64").isin(
                set(keep["permno"].astype("int64")))].head(max(0, k - len(keep)))
            sel = pd.concat([keep, fill]) if len(fill) else keep
        if sel.empty:
            continue
        held = set(sel["permno"].astype("int64"))
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
    res = {
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
    if hold_k is not None:
        # ONLY WHEN HYSTERESIS IS ON. Adding these unconditionally changed the
        # DEFAULT key set and broke `test_v1_book_still_returns_exactly_the_keys_
        # v1_recorded`: this function's docstring promises v1's receipt is
        # reproduced byte for byte, and a SCHEMA change breaks that promise even
        # though every v1 NUMBER was identical (verified). A sealed receipt is
        # sealed at its key set too, so the new keys appear only on the path that
        # gives them meaning.
        res["hold_k"] = hold_k
        res["selection_rule"] = f"buy at rank <= {k}, hold until rank > {hold_k}"
    if with_risk:
        res["risk"] = risk_stats(net, market)
    if return_series:
        res["_series"] = {"net": net, "gross": gross, "market": market,
                          "turnover": turnover}
    return res


# --------------------------------------- overlap: the t that counts DATE BLOCKS

def hac_t(series: pd.Series, lag: int) -> float | None:
    """Newey-West t of the mean, with `lag` lags. None when it cannot be formed.

    A monthly series of 12-MONTH forward returns is the same twelve months of
    market history counted twelve times. Its naive t divides by sqrt(143) when
    the independent draws number about twelve, and the result is a t-statistic
    that rises with horizon for a purely mechanical reason.
    """
    s = pd.Series(series).dropna().astype(float)
    n = len(s)
    if n < 5:
        return None
    x = s.to_numpy() - s.mean()
    gamma0 = float(np.dot(x, x) / n)
    var = gamma0
    for k in range(1, min(int(lag), n - 1) + 1):
        gk = float(np.dot(x[k:], x[:-k]) / n)
        var += 2.0 * (1.0 - k / (int(lag) + 1.0)) * gk
    if var <= 0:
        return None
    return float(s.mean() / np.sqrt(var / n))


def block_t(series: pd.Series, block: int) -> dict:
    """Average the series into NON-OVERLAPPING blocks of `block` months, then t.

    The blunt instrument beside `hac_t`, and the one that makes the n visible:
    143 monthly draws of a 12-month target are 11 independent blocks, and
    printing `n_effective = 11` next to `months = 143` is what stops a reader
    treating the second number as the sample size (CANON §58).
    """
    s = pd.Series(series).dropna().astype(float)
    if len(s) < 2 * block:
        return {"n_effective": int(len(s) // max(block, 1)), "t_block": None,
                "note": "fewer than two full blocks"}
    g = np.arange(len(s)) // int(block)
    means = s.groupby(g).mean()
    t = _t_from_series(means)
    return {"n_effective": int(len(means)),
            "mean_of_block_means": round(float(means.mean()), 5),
            "t_block": round(t, 3) if t is not None else None}


def overlap_corrected(series: pd.Series, horizon_months: int) -> dict:
    """Naive t, HAC t and block t side by side, with the n each one uses."""
    s = pd.Series(series).dropna().astype(float)
    t_naive = _t_from_series(s)
    h = int(horizon_months)
    out = {
        "months": int(len(s)),
        "t_naive": round(t_naive, 3) if t_naive is not None else None,
        "t_naive_n": int(len(s)),
        "horizon_months": h,
    }
    if h > 1:
        t_hac = hac_t(s, lag=h - 1)
        out["t_newey_west"] = round(t_hac, 3) if t_hac is not None else None
        out["newey_west_lags"] = h - 1
        out.update({f"block_{k}": v for k, v in block_t(s, h).items()})
        out["read_as"] = (
            f"a {h}-month forward target sampled monthly is the same history counted "
            f"{h} times; `t_naive` divides by sqrt({len(s)}) when the independent draws "
            "number about n_effective. Use t_newey_west or t_block, never t_naive.")
    else:
        out["read_as"] = "a 1-month target sampled monthly does not overlap; t_naive stands."
    return out


# ------------------------------------------------------- risk, drawdown, tail

def max_drawdown(returns: pd.Series) -> float | None:
    """Peak-to-trough of the COMPOUNDED wealth path, not of the return series.

    A drawdown computed on returns rather than on wealth is a worst month with
    a longer name. The house metric is terminal wealth, so the risk that
    belongs beside it is the worst path the wealth actually took.
    """
    r = pd.Series(returns).dropna()
    if len(r) < 2:
        return None
    wealth = (1.0 + r).cumprod()
    peak = wealth.cummax()
    return round(float((wealth / peak - 1.0).min()), 4)


def risk_stats(net: pd.Series, market: pd.Series | None = None) -> dict:
    """Drawdown and tail, on the net monthly series and on the market beside it.

    Reported beside each other on purpose: a -45% drawdown is a different fact
    in a month when the market fell 40% than in a month when it did not, and a
    strategy drawdown quoted alone invites the reader to supply their own
    market path from memory.
    """
    r = pd.Series(net).dropna()
    if len(r) < 3:
        return {"months": int(len(r)), "note": "too few months"}
    q05 = float(r.quantile(0.05))
    tail = r[r <= q05]
    out = {
        "months": int(len(r)),
        "max_drawdown_net": max_drawdown(r),
        "worst_month": round(float(r.min()), 4),
        "cvar_05_monthly": round(float(tail.mean()), 4) if len(tail) else None,
        "monthly_sd": round(float(r.std(ddof=1)), 4),
        "downside_sd": round(float(r[r < 0].std(ddof=1)), 4) if (r < 0).sum() > 2 else None,
        "skew": round(float(r.skew()), 3),
        "kurtosis_excess": round(float(r.kurtosis()), 3),
    }
    if market is not None:
        m = pd.Series(market).reindex(r.index).dropna()
        if len(m) >= 3:
            out["max_drawdown_market_same_months"] = max_drawdown(m)
            out["worst_month_market"] = round(float(m.min()), 4)
            out["monthly_sd_market"] = round(float(m.std(ddof=1)), 4)
    return out


def paired_difference(a: pd.Series, b: pd.Series, label_a: str = "a",
                      label_b: str = "b") -> dict:
    """The ONLY honest "did A beat B?" -- a paired t on the monthly difference.

    Two terminal wealths are ONE draw of a correlated pair. Two monthly series
    over the same months are n paired draws, and the n is MONTHS (CANON §58).
    """
    a = pd.Series(a).dropna()
    b = pd.Series(b).dropna()
    common = a.index.intersection(b.index)
    if len(common) < 2:
        return {"months": int(len(common)), "note": "fewer than 2 shared months"}
    d = (a.loc[common] - b.loc[common]).astype(float)
    t = _t_from_series(d)
    return {
        "months": int(len(d)),
        "compared": f"{label_a} minus {label_b}",
        "mean_monthly_difference": round(float(d.mean()), 5),
        "annualised_difference": round(float(d.mean()) * 12, 4),
        "t_stat_paired": round(t, 3) if t is not None else None,
        "share_months_ahead": round(float((d > 0).mean()), 4),
        "terminal_wealth_a": round(float((1.0 + a.loc[common]).prod()), 4),
        "terminal_wealth_b": round(float((1.0 + b.loc[common]).prod()), 4),
    }


# -------------------------------------------- books at horizons longer than 1m

def overlapping_book(df: pd.DataFrame, pred_col: str, horizon_months: int,
                     k: int = 50, weight: str = "vw",
                     cost_bps: float = COST_BPS_PER_SIDE,
                     month_col: str = "month", ret_col: str = "fwd_1m",
                     mkt_col: str = "mkt_vw_1m",
                     tradable_floor: float | None = None,
                     with_risk: bool = True, return_series: bool = False) -> dict:
    """A monthly-formed book HELD for `horizon_months` -- the overlapping
    construction, because the alternative is a lie in one of two directions.

    v1 graded 3m/6m/12m on rank IC alone and never priced them, so the horizon
    question -- the one the 12m head exists to answer -- had no money number at
    all. The two wrong ways to supply one:

      * rebalance monthly on a 12m forecast: that is a 1m book wearing a 12m
        signal, and it pays 12x the turnover for a view it never holds;
      * hold non-overlapping annual cohorts: 9 draws instead of 107, and the
        answer becomes a statement about which January you started in.

    So: at every month a new cohort of `k` names is formed, each cohort is held
    for `horizon_months`, and the portfolio is 1/h in each live cohort. Weights
    inside a cohort are set at FORMATION and then drift with realised returns
    (no free intra-cohort rebalancing). A name whose monthly return goes
    missing mid-hold is liquidated at its last observed value and the proceeds
    sit in CASH for the rest of that cohort's life -- the same convention
    `learner/dataset.py` uses for delistings, chosen so a dead name is a zero
    from then on rather than silently deleted from the book.

    Turnover is measured on the AGGREGATE weight vector month over month, so
    the cost of rolling one cohort in and one out is paid, and only that.
    """
    h = int(horizon_months)
    cols = [month_col, "permno", pred_col, ret_col, mkt_col, "market_cap",
            "log_dollar_vol_20d", "dollar_vol_20d"]
    d = df[[c for c in cols if c in df.columns]].copy()
    d = d.dropna(subset=[pred_col])
    if tradable_floor is not None:
        if "dollar_vol_20d" in d.columns and d["dollar_vol_20d"].notna().any():
            dv = d["dollar_vol_20d"]
        elif "log_dollar_vol_20d" in d.columns:
            dv = np.expm1(d["log_dollar_vol_20d"])
        else:
            raise SystemExit(
                "REFUSED: a tradable floor was requested and no liquidity column is "
                "present. A liquidity gate with no liquidity column passes everything.")
        d = d[dv.to_numpy() >= tradable_floor]
    if d.empty:
        return {"months": 0, "note": "no rows"}

    months = sorted(df[month_col].dropna().unique())
    pos = {m: i for i, m in enumerate(months)}
    # Monthly realised return per (month, permno), and the market's own month.
    ret_by_month: dict[str, pd.Series] = {}
    mkt_by_month: dict[str, float] = {}
    for m, chunk in df[[month_col, "permno", ret_col, mkt_col]].groupby(month_col, sort=True):
        s = chunk.dropna(subset=[ret_col]).set_index("permno")[ret_col]
        ret_by_month[m] = s[~s.index.duplicated()]
        mk = chunk[mkt_col].dropna()
        if len(mk):
            mkt_by_month[m] = float(mk.iloc[0])

    mo_int = d[month_col].astype(str).str.replace("-", "", regex=False).astype("int64")
    d = d.assign(_tb=(d["permno"].astype("int64") * 2_654_435_761
                      + mo_int * 97 + TIE_SEED) % 1_000_003)

    # 1. form the cohorts
    cohorts: dict[str, dict] = {}
    for m, chunk in d.groupby(month_col, sort=True):
        sel = chunk.sort_values([pred_col, "_tb"], ascending=[False, True]).head(k)
        if sel.empty:
            continue
        if weight == "vw" and "market_cap" in sel.columns and sel["market_cap"].notna().any():
            w = sel["market_cap"].fillna(sel["market_cap"].median()).clip(lower=0)
            w = w / w.sum() if w.sum() > 0 else pd.Series(1.0 / len(sel), index=sel.index)
        else:
            w = pd.Series(1.0 / len(sel), index=sel.index)
        cohorts[m] = {"w": dict(zip(sel["permno"].astype(int), w.to_numpy())),
                      "cash": 0.0}

    # 2. walk the calendar, holding each cohort for h months
    live: dict[str, dict] = {}
    port_ret, port_weights, n_live = {}, {}, {}
    for m in months:
        if m in cohorts:
            live[m] = {"w": dict(cohorts[m]["w"]), "cash": 0.0}
        # drop cohorts that have been held h months
        live = {f: st for f, st in live.items() if pos[m] - pos[f] < h}
        if not live:
            continue
        rets = ret_by_month.get(m)
        if rets is None or m not in mkt_by_month:
            continue
        agg: dict[int, float] = {}
        cohort_rets = []
        for f, st in live.items():
            tot = sum(st["w"].values()) + st["cash"]
            if tot <= 0:
                continue
            r_c, new_w, new_cash = 0.0, {}, st["cash"]
            for p, wt in st["w"].items():
                r = rets.get(p, np.nan)
                if not np.isfinite(r):
                    new_cash += wt                    # liquidated -> cash, 0 from here
                    continue
                r_c += wt * float(r)
                new_w[p] = wt * (1.0 + float(r))
            cohort_rets.append(r_c / tot)
            st["w"], st["cash"] = new_w, new_cash
            scale = 1.0 / (sum(new_w.values()) + new_cash) if (sum(new_w.values()) + new_cash) > 0 else 0.0
            for p, wt in new_w.items():
                agg[p] = agg.get(p, 0.0) + wt * scale / max(len(live), 1)
        if not cohort_rets:
            continue
        port_ret[m] = float(np.mean(cohort_rets))
        port_weights[m] = agg
        n_live[m] = len(live)

    if not port_ret:
        return {"months": 0, "note": "no month produced a book"}
    gross = pd.Series(port_ret).sort_index()
    market = pd.Series({m: mkt_by_month[m] for m in gross.index}).sort_index()

    turn, prev = [], None
    for m in gross.index:
        cur = port_weights[m]
        if prev is None:
            turn.append(1.0)
        else:
            keys = set(cur) | set(prev)
            turn.append(0.5 * sum(abs(cur.get(kk, 0.0) - prev.get(kk, 0.0)) for kk in keys))
        prev = cur
    turnover = pd.Series(turn, index=gross.index)
    cost = turnover * (cost_bps / 10_000.0) * 2.0
    net = gross - cost

    spread = (net - market).dropna()
    t = _t_from_series(spread)
    yrs = len(net) / 12.0
    tw, twg, twm = (float((1.0 + net).prod()), float((1.0 + gross).prod()),
                    float((1.0 + market).prod()))
    res = {
        "months": int(len(net)),
        "horizon_months": h,
        "construction": (f"overlapping: a new top-{k} cohort every month, each held {h} "
                         "months, portfolio = 1/h in each live cohort; cohort weights set "
                         "at formation and left to drift; a name whose monthly return goes "
                         "missing is liquidated into CASH for the rest of that cohort"),
        "k": k, "weight": weight,
        "cost_bps_per_side": cost_bps,
        "tradable_floor_usd": tradable_floor,
        "mean_live_cohorts": round(float(np.mean(list(n_live.values()))), 2),
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
    if with_risk:
        res["risk"] = risk_stats(net, market)
    if return_series:
        res["_series"] = {"net": net, "gross": gross, "market": market,
                          "turnover": turnover}
    return res


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
           "grade_by_band",
           # v2, additive: v1's functions above are untouched.
           "max_drawdown", "risk_stats", "paired_difference", "overlapping_book",
           "hac_t", "block_t", "overlap_corrected", "monthly_ic_series"]
