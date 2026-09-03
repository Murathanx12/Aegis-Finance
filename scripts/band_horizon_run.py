"""BAND HORIZON / SELF-ATTACK -- is BAND_PRIOR v2 a 1-month selector at all?

THE QUESTION, STATED SO IT CAN LOSE
===================================
BAND_PRIOR v2 bands the analyst target/price ratio and hands each band an
ANNUALISED expected excess return. The live books trade it on a 21-session
clock. Two facts collected on 2026-09-02 make that suspicious:

* the prior's monthly rank IC rises MONOTONICALLY with horizon, reaching
  t 34.5 at twelve months (`learner_v1.json`);
* inside the 3-5 band the prior ranks BACKWARDS (IC -0.022, t -2.93).

So the object may be a TWELVE-MONTH expected-return prior being sampled every
month, in which case the right instrument is a twelve-month book and not a
one-month one. Or the 3-5 band may be a beta/size exposure wearing a selection
label. This script runs the decomposition that separates those, per horizon,
on identical vintages.

WHAT IT EXECUTES, AND UNDER WHOSE RULES
=======================================
`PREREG_BAND_IS_BETA_1` (primary) and the random-ordering control arm of
`PREREG_RANK_VS_EXPRETURN_1`, both pre-registered in `Aegis module/TRIALS/`.
Their metrics, band edges, hygiene floors, beta estimator, cost convention and
decision rules are read from those files and are NOT substituted. Where this
script measures something the preregs did not name -- the four-horizon sweep,
because BAND-IS-BETA declares the split at the book level and not per horizon --
the statistic is labelled EXPLORATORY and never resolves a declared rule.

Licence: PRODUCT_EXPERIMENT. Nothing here trades, sizes, seals or orders. The
beta-neutralised series is a MEASUREMENT, not a book.

THE INCUMBENT'S NUMBER IS NOT A VW NUMBER, AND THAT HAD TO BE FOUND FIRST
========================================================================
+16.55%/yr for the 3-5 band is quoted everywhere in this programme. Reproducing
it took three attempts and the recipe turns out to be specific:

  1. the benchmark is the EQUAL-WEIGHTED MEAN OF THE ANALYST-COVERED PANEL
     ITSELF (`scripts/tracker_ibes_backtest.py:564`,
     `market = lab.groupby("month")["fwd_1m"].mean()`) -- roughly 3,000 covered
     names. It is neither the VW market nor the CRSP equal-weighted market;
  2. band membership is measured on rows WITHOUT a split in the prior year
     (S30b: a stale target across a split is not an opinion), while the
     benchmark leg is computed over ALL rows including those;
  3. the annualisation is LINEAR (mean monthly x 12), not compounded.

Run that recipe and the four constants come back +2.36 / +6.62 / +15.86 /
-39.34 against a published +2.41 / +5.74 / +16.55 / -37.77, the residual being
the published series' cost netting and a 0.9% panel difference. Run the SAME
book against the value-weighted market and the 3-5 band's headline is not
+16.55%/yr. That gap is a benchmark, not a discovery, and it is reported at the
top of the receipt rather than buried, because every downstream document quotes
the +16.55 as though it were an excess over the market.

n_effective COUNTS DATE BLOCKS (canon 58)
=========================================
A monthly-formed book held h months produces ~144 overlapping observations
containing about 144/h independent ones. Every t is reported three ways: naive
(printed only so nobody re-derives it and believes it), Newey-West with h-1
lags, and the non-overlapping block t averaged over the h phase offsets. The
block t is the one every decision rule reads.

COSTS ARE NEVER OMITTED
=======================
Turnover is measured between a cohort and the cohort it replaces, with the old
weights DRIFTED by their realised holding-period return. Cost is charged at
10bps per side on the sum of absolute weight changes, and again at 25bps as a
sensitivity. Both appear beside every return.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from learner import beta as B           # noqa: E402
from learner import dataset as D        # noqa: E402
from learner import prior as P          # noqa: E402

RECEIPT = (REPO / "backend" / "data" / "optimus" / "tracker_backtest"
           / "band_horizon_20260903.json")

HORIZONS = (1, 3, 6, 12)
BANDS = ("lt_1_5", "b_1_5_3", "b_3_5", "toxic_ge_5")
COST_BPS_PRIMARY = 10.0
COST_BPS_SENSITIVITY = 25.0
ERAS = {"2013_2019": (2013, 2019), "2020_2021": (2020, 2021), "2022_2024": (2022, 2024)}
#: PREREG_BAND_IS_BETA_1 contamination clause.
MAX_MISSING_BETA_SHARE = 0.05
#: PREREG_RANK_VS_EXPRETURN_1 frozen parameters.
BOOK_K = 50
RANDOM_DRAWS = 100
SEED = 20260903
#: PREREG_BAND_IS_BETA_1 decision rule thresholds, quoted verbatim.
BETA_LEG_THRESHOLD_PP = 6.0
NEUTRAL_REFUTES_PP = 10.0
NEUTRAL_REFUTES_T = 2.0


# ------------------------------------------------------------------ statistics

def nw_se(x: np.ndarray, lags: int) -> float:
    """Newey-West standard error of the mean with `lags` Bartlett lags."""
    x = np.asarray(x, dtype="float64")
    n = len(x)
    if n < 3:
        return float("nan")
    e = x - x.mean()
    var = float(e @ e) / n
    for L in range(1, min(lags, n - 1) + 1):
        var += 2.0 * (1.0 - L / (lags + 1.0)) * (float(e[L:] @ e[:-L]) / n)
    return float(np.sqrt(var / n)) if var > 0 else float("nan")


def block_t(x: pd.Series, h: int) -> dict:
    """Non-overlapping block t: every h-th observation, averaged over the h
    phase offsets. The statistic whose n is a count of DATE BLOCKS."""
    ts, ns = [], []
    for p in range(h):
        s = x.iloc[p::h].dropna()
        if len(s) < 3:
            continue
        se = s.std(ddof=1) / np.sqrt(len(s))
        if se > 0:
            ts.append(float(s.mean() / se))
            ns.append(int(len(s)))
    if not ts:
        return {"t": float("nan"), "n_blocks": 0, "phases": 0}
    return {"t": float(np.mean(ts)), "t_min": float(np.min(ts)),
            "t_max": float(np.max(ts)), "n_blocks": int(np.mean(ns)), "phases": len(ts)}


def annualise(mean_h: float, h: int) -> float:
    if not np.isfinite(mean_h) or mean_h <= -1.0:
        return float("nan")
    return float((1.0 + mean_h) ** (12.0 / h) - 1.0)


def series_stats(x: pd.Series, h: int, label: str) -> dict:
    x = x.dropna()
    n = len(x)
    if n < 3:
        return {"label": label, "n_months": n, "insufficient": True,
                "annualised_pct": None, "t_block": None,
                "n_effective_date_blocks": 0}
    m = float(x.mean())
    naive_se = float(x.std(ddof=1) / np.sqrt(n))
    hac = nw_se(x.to_numpy(), max(h - 1, 0))
    bt = block_t(x, h)
    return {
        "label": label,
        "n_months": n,
        "mean_per_period_pct": round(100.0 * m, 4),
        "annualised_pct": round(100.0 * annualise(m, h), 3),
        "annualised_linear_pct_incumbent_convention": round(100.0 * m * 12.0 / h, 3),
        "t_naive_OVERSTATED": round(m / naive_se, 3) if naive_se > 0 else None,
        "t_newey_west": round(m / hac, 3) if np.isfinite(hac) and hac > 0 else None,
        "t_block": round(bt["t"], 3) if np.isfinite(bt["t"]) else None,
        "t_block_range": ([round(bt.get("t_min", float("nan")), 3),
                          round(bt.get("t_max", float("nan")), 3)] if bt["phases"] else None),
        "n_effective_date_blocks": bt["n_blocks"],
        "share_periods_positive": round(float((x > 0).mean()), 4),
    }


def max_drawdown(wealth: np.ndarray) -> float:
    if len(wealth) == 0:
        return float("nan")
    return float(np.min(wealth / np.maximum.accumulate(wealth)) - 1.0)


# ------------------------------------------------------- book construction

def panel_ew_benchmark(df: pd.DataFrame, h: int) -> pd.Series:
    """The INCUMBENT's benchmark: the equal-weighted mean forward return of the
    whole analyst-covered panel, splits included. Not the market -- the covered
    universe. Reproduced here because the published band constants are quoted
    against it and a reader comparing them to a VW excess is comparing two
    different objects."""
    d = df[df[f"fwd_{h}m"].notna()]
    return d.groupby("month")[f"fwd_{h}m"].mean().rename("mkt_panel")


def cohort_frame(df: pd.DataFrame, h: int, panel_ew: pd.Series) -> pd.DataFrame:
    """One row per (month, permno) INVESTABLE at horizon h.

    Investable means the h-month target matured, the market leg exists and a
    pre-period beta exists. A name lacking a beta is dropped from BOTH arms,
    never from one (PREREG_BAND_IS_BETA_1)."""
    need = [f"fwd_{h}m", f"mkt_vw_{h}m", f"mkt_ew_{h}m", "beta_pre"]
    ok = df[need].notna().all(axis=1)
    c = df.loc[ok, ["month", "permno", "band", "ratio", "consensus", "market_cap",
                    "beta_pre", "in_admissible", "split_prior_year",
                    f"fwd_{h}m", f"mkt_vw_{h}m", f"mkt_ew_{h}m", f"prior_{h}m"]].copy()
    c = c.rename(columns={f"fwd_{h}m": "fwd", f"mkt_vw_{h}m": "mkt_vw",
                          f"mkt_ew_{h}m": "mkt_ew", f"prior_{h}m": "prior"})
    c["mkt_panel"] = c["month"].map(panel_ew)
    c["excess_vw"] = c["fwd"] - c["mkt_vw"]
    c["excess_ew"] = c["fwd"] - c["mkt_ew"]
    c["excess_panel"] = c["fwd"] - c["mkt_panel"]
    # THE DECOMPOSITION, exact by construction:
    #   excess_vw = (beta_pre - 1) * mkt_vw  +  resid
    c["resid"] = c["fwd"] - c["beta_pre"] * c["mkt_vw"]
    c["beta_leg"] = (c["beta_pre"] - 1.0) * c["mkt_vw"]
    return c


def contamination_months(df: pd.DataFrame, band_mask: pd.Series, h: int) -> dict:
    """PREREG_BAND_IS_BETA_1: any month in which more than 5 per cent of
    admitted names lack a usable beta is excluded from BOTH arms."""
    sel = df[band_mask & df[f"fwd_{h}m"].notna()]
    if sel.empty:
        return {"excluded_months": [], "n_excluded": 0}
    share = sel.groupby("month")["beta_pre"].apply(lambda s: float(s.isna().mean()))
    bad = sorted(share[share > MAX_MISSING_BETA_SHARE].index.tolist())
    return {"excluded_months": bad, "n_excluded": len(bad),
            "worst_month_missing_share": round(float(share.max()), 4),
            "median_missing_share": round(float(share.median()), 4)}


def ew_book(c: pd.DataFrame, h: int, cost_bps: float) -> dict:
    """Equal-weighted monthly-formed book held h months.

    EW because that is the construction the band constants were measured under.
    Using anything else would compare a new number to an old one built
    differently."""
    months = sorted(c["month"].unique())
    holdings = {m: g for m, g in c.groupby("month")}
    rows = []
    for i, m in enumerate(months):
        g = holdings[m]
        n = len(g)
        if n == 0:
            continue
        rec = {"month": m, "n_names": n}
        for col in ("fwd", "mkt_vw", "mkt_ew", "mkt_panel", "excess_vw", "excess_ew",
                    "excess_panel", "resid", "beta_leg"):
            rec[col] = float(g[col].mean())
        rec["beta_mean"] = float(g["beta_pre"].mean())
        rec["beta_median"] = float(g["beta_pre"].median())
        rec["log_cap_mean"] = float(np.log(g["market_cap"].clip(lower=1)).mean())
        if i - h >= 0:
            pg = holdings[months[i - h]]
            w_old = pd.Series(1.0 / len(pg), index=pg["permno"].to_numpy())
            w_old = w_old * (1.0 + pd.Series(pg["fwd"].to_numpy(),
                                             index=pg["permno"].to_numpy()))
            w_old = w_old / w_old.sum()
            w_new = pd.Series(1.0 / n, index=g["permno"].to_numpy())
            allp = w_old.index.union(w_new.index)
            rec["turnover_sum_abs_dw"] = float(np.abs(
                w_new.reindex(allp).fillna(0.0) - w_old.reindex(allp).fillna(0.0)).sum())
        else:
            rec["turnover_sum_abs_dw"] = np.nan
        rows.append(rec)
    bk = pd.DataFrame(rows).set_index("month")
    # sum|dw| already counts the sell leg AND the buy leg, so one multiplication
    # by bps-per-side is the whole round trip.
    med = float(np.nanmedian(bk["turnover_sum_abs_dw"])) if len(bk) else 0.0
    bk["cost"] = bk["turnover_sum_abs_dw"].fillna(med) * (cost_bps / 10_000.0)
    for col in ("excess_vw", "excess_panel", "resid", "fwd"):
        bk[f"{col}_net"] = bk[col] - bk["cost"]
    return {"book": bk, "median_turnover": med}


def phase_chains(bk: pd.DataFrame, h: int, col: str) -> dict:
    """Terminal wealth and max drawdown of the NON-OVERLAPPING chain, one chain
    per phase offset. A single-phase chain is a strategy someone could have run;
    the overlapping mean is not."""
    out = []
    for p in range(h):
        s = bk[col].iloc[p::h].dropna()
        if len(s) < 2:
            continue
        w = np.cumprod(1.0 + s.to_numpy())
        out.append({"phase": p, "n_rebalances": int(len(s)),
                    "terminal_wealth": round(float(w[-1]), 4),
                    "max_drawdown": round(max_drawdown(w), 4)})
    if not out:
        return {"phases": []}
    tw = [o["terminal_wealth"] for o in out]
    dd = [o["max_drawdown"] for o in out]
    return {"phases": out,
            "terminal_wealth_median": round(float(np.median(tw)), 4),
            "terminal_wealth_min": round(float(np.min(tw)), 4),
            "terminal_wealth_max": round(float(np.max(tw)), 4),
            "max_drawdown_median": round(float(np.median(dd)), 4),
            "max_drawdown_worst": round(float(np.min(dd)), 4)}


def _years(bk: pd.DataFrame) -> pd.Series:
    return pd.Series([int(m[:4]) for m in bk.index], index=bk.index)


def era_split(bk: pd.DataFrame, h: int, col: str) -> dict:
    yr = _years(bk)
    out = {}
    for name, (lo, hi) in ERAS.items():
        st = series_stats(bk.loc[(yr >= lo) & (yr <= hi), col], h, name)
        out[name] = {"n_months": st.get("n_months"),
                     "annualised_pct": st.get("annualised_pct"),
                     "t_block": st.get("t_block"),
                     "n_effective_date_blocks": st.get("n_effective_date_blocks")}
    return out


def leave_one_year_out(bk: pd.DataFrame, h: int, col: str) -> dict:
    yr = _years(bk)
    out = {}
    for y in sorted(yr.unique()):
        st = series_stats(bk.loc[yr != y, col], h, f"drop_{y}")
        out[str(y)] = {"annualised_pct_without_this_year": st.get("annualised_pct"),
                       "t_block": st.get("t_block")}
    return out


def by_year(bk: pd.DataFrame, h: int, col: str) -> dict:
    yr = _years(bk)
    return {str(y): round(100.0 * annualise(float(bk.loc[yr == y, col].mean()), h), 2)
            for y in sorted(yr.unique())}


# --------------------------------------------------- multiplicity control

def bh_fdr(pvals: dict, q: float = 0.05) -> dict:
    items = sorted(((k, v) for k, v in pvals.items() if np.isfinite(v)), key=lambda kv: kv[1])
    m = len(items)
    passed, thresh = set(), 0.0
    for i, (k, p) in enumerate(items, start=1):
        if p <= i / m * q:
            thresh = i / m * q
            passed = {kk for kk, _ in items[:i]}
    return {"q": q, "m": m, "critical_p": round(thresh, 6), "survivors": sorted(passed)}


def holm(pvals: dict, alpha: float = 0.05) -> dict:
    items = sorted(((k, v) for k, v in pvals.items() if np.isfinite(v)), key=lambda kv: kv[1])
    m = len(items)
    survivors = []
    for i, (k, p) in enumerate(items):
        if p <= alpha / (m - i):
            survivors.append(k)
        else:
            break
    return {"alpha": alpha, "m": m, "survivors": survivors,
            "note": "Holm stops at the first failure; everything after it is NOT exported"}


def two_sided_p(t, dof: int) -> float:
    if t is None or not np.isfinite(t) or dof < 2:
        return float("nan")
    try:
        from scipy import stats
        return float(2.0 * stats.t.sf(abs(t), dof))
    except Exception:
        from math import erfc, sqrt
        return float(erfc(abs(t) / sqrt(2.0)))


# ------------------------------------------------------------------- controls

def beta_matched_control(c: pd.DataFrame, h: int, target_band: str) -> dict:
    """PREREG_BAND_IS_BETA_1's required matched control -- run whether or not
    the primary result is interesting.

    A basket from OUTSIDE the admitted region matched on pre-period beta decile,
    market-capitalisation decile and calendar month, holding ratio below 1.5.
    If it earns the band's return, the ratio screen is decoration on a beta sort.

    Cell-weighted rather than one-draw-per-name: the control return for a month
    is the admitted set's own (beta decile x cap decile) distribution applied to
    the mean return of the ratio<1.5 pool in the same cells. Same joint match,
    far less sampling noise, and every unmatched admitted name is counted."""
    c = c.copy()
    for src, dst in (("beta_pre", "beta_dec"), ("market_cap", "cap_dec")):
        c[dst] = c.groupby("month")[src].transform(
            lambda s: pd.qcut(s.rank(method="first"), 10, labels=False, duplicates="drop"))
    tgt = c[c["band"] == target_band]
    pool = c[c["ratio"] < 1.5]
    rows, unmatched, total = [], 0, 0
    for m, g in tgt.groupby("month"):
        pg = pool[pool["month"] == m]
        if pg.empty:
            continue
        pm = pg.groupby(["beta_dec", "cap_dec"]).agg(
            fwd=("fwd", "mean"), excess_vw=("excess_vw", "mean"),
            excess_panel=("excess_panel", "mean"), resid=("resid", "mean"),
            beta=("beta_pre", "mean"), n=("fwd", "size"))
        cells = g.groupby(["beta_dec", "cap_dec"]).size().rename("w")
        total += int(cells.sum())
        j = pd.concat([cells, pm], axis=1, join="inner")
        unmatched += int(cells.sum() - (int(j["w"].sum()) if len(j) else 0))
        if j.empty or j["w"].sum() == 0:
            continue
        w = j["w"] / j["w"].sum()
        rows.append({"month": m,
                     "fwd": float((w * j["fwd"]).sum()),
                     "excess_vw": float((w * j["excess_vw"]).sum()),
                     "excess_panel": float((w * j["excess_panel"]).sum()),
                     "resid": float((w * j["resid"]).sum()),
                     "beta_mean": float((w * j["beta"]).sum())})
    if not rows:
        return {"status": "NO_MATCHES"}
    bk = pd.DataFrame(rows).set_index("month")
    return {
        "design": "ratio<1.5 pool, matched on (beta decile x cap decile x month), "
                  "cell-weighted by the 3-5 band's own joint distribution",
        "n_months": int(len(bk)),
        "unmatched_admitted_names": unmatched,
        "unmatched_share": round(unmatched / max(total, 1), 4),
        "mean_beta_of_control": round(float(bk["beta_mean"].mean()), 4),
        "excess_vw": series_stats(bk["excess_vw"], h, "control_excess_vw"),
        "excess_panel": series_stats(bk["excess_panel"], h, "control_excess_panel"),
        "resid": series_stats(bk["resid"], h, "control_resid"),
        "_book": bk,
    }


def vw_topk(g: pd.DataFrame, order: np.ndarray, k: int):
    idx = np.argsort(-order, kind="stable")[:k]
    sel = g.iloc[idx]
    w = sel["market_cap"].to_numpy(dtype="float64")
    if not np.isfinite(w).all() or w.sum() <= 0:
        w = np.ones(len(sel))
    w = w / w.sum()
    return float((w * sel["fwd"].to_numpy()).sum()), sel["permno"].to_numpy()


def ordering_arena(c: pd.DataFrame, rng: np.random.Generator) -> dict:
    """PREREG_RANK_VS_EXPRETURN_1, scoped to the horizon-1 admitted set.

    Three arms on the SAME admitted set: score order (ratio x consensus),
    expectation order (the sealed prior field), and RANDOM order averaged over
    100 seeded draws. Nothing here changes admission or trades."""
    adm = c[c["in_admissible"]].copy()
    rows, degenerate = [], 0
    for m in sorted(adm["month"].unique()):
        g = adm[adm["month"] == m].reset_index(drop=True)
        if len(g) < 5:
            continue
        score = (g["ratio"] * g["consensus"]).to_numpy(dtype="float64")
        expv = g["prior"].to_numpy(dtype="float64")
        if len(np.unique(expv[np.isfinite(expv)])) <= 1:
            degenerate += 1
        # The prereg's own words: "plus whatever tie-break the sort happens to
        # apply". Made explicit and seeded rather than left implicit.
        expv_tb = expv + rng.random(len(g)) * 1e-9
        k = min(BOOK_K, len(g))
        r_s, p_s = vw_topk(g, score, k)
        r_e, p_e = vw_topk(g, expv_tb, k)
        rand = [vw_topk(g, rng.random(len(g)), k)[0] for _ in range(RANDOM_DRAWS)]
        rows.append({"month": m, "n_admitted": int(len(g)),
                     "score": r_s, "exp": r_e, "rand": float(np.mean(rand)),
                     "mkt_vw": float(g["mkt_vw"].mean()),
                     "slot_overlap": len(set(p_s) & set(p_e)) / float(k),
                     "rank_corr": float(pd.Series(score).rank().corr(
                         pd.Series(expv).rank(), method="pearson"))})
    bk = pd.DataFrame(rows).set_index("month")
    for a in ("score", "exp", "rand"):
        bk[f"{a}_excess"] = bk[a] - bk["mkt_vw"]
    diff = bk["score_excess"] - bk["exp_excess"]
    st = series_stats(diff, 1, "score_minus_exp")
    tw = {a: round(float(np.prod(1.0 + bk[a].to_numpy())), 4) for a in ("score", "exp", "rand")}
    return {
        "n_months": int(len(bk)),
        "k": BOOK_K, "weighting": "value-weighted inside the admitted set",
        "random_draws_per_month": RANDOM_DRAWS,
        "mean_slot_overlap_score_vs_exp": round(float(bk["slot_overlap"].mean()), 4),
        "mean_rank_corr_between_orderings": round(float(bk["rank_corr"].mean()), 4),
        "degenerate_months_expectation_constant": degenerate,
        "arms_excess_vs_vw": {a: series_stats(bk[f"{a}_excess"], 1, a)
                              for a in ("score", "exp", "rand")},
        "paired_score_minus_exp": st,
        "terminal_wealth_gross": tw,
        "terminal_wealth_market_vw": round(float(np.prod(1.0 + bk["mkt_vw"].to_numpy())), 4),
        "cost_bps_per_side": COST_BPS_PRIMARY,
        "cost_note": ("all three arms rebalance a top-50 book monthly and are charged the "
                      "same convention; the cost DIFFERENCE between arms is bounded by "
                      "(1 - slot_overlap) x 2 x 10bps per month, quoted below"),
        "max_monthly_cost_difference_pct": round(
            100.0 * (1.0 - float(bk["slot_overlap"].mean())) * 2.0 * COST_BPS_PRIMARY / 1e4, 4),
        "decision_rule_PREREG_RANK_VS_EXPRETURN_1": {
            "rule": "adopt one ordering only if its paired advantage is positive with "
                    "t >= 2 AND its terminal wealth is higher AND the advantage exceeds "
                    "the quoted round-trip cost of the slots that differ",
            "paired_t_block": st.get("t_block"),
            "paired_annualised_pct": st.get("annualised_pct"),
            "terminal_wealth_score": tw["score"], "terminal_wealth_exp": tw["exp"],
            "resolved": ("NO-DIFFERENCE" if (st.get("t_block") is None
                                             or abs(st.get("t_block")) < 2.0)
                         else "ONE ORDERING WINS -- see paired_score_minus_exp"),
        },
    }


# ------------------------------------------------------------- reproduction

def reproduce_published(df: pd.DataFrame) -> dict:
    """Pin this pipeline against the published band constants by running the
    INCUMBENT's exact recipe, found by reading
    `scripts/tracker_ibes_backtest.py` rather than by assuming."""
    d = df[df["fwd_1m"].notna()].copy()
    d["sp"] = d["split_prior_year"].astype(bool)
    mkt = d.groupby("month")["fwd_1m"].mean()      # ALL rows, splits included
    sub = d[~d["sp"]]                              # bands: split-free rows only
    pub = {b[2]: b[3] for b in P.BAND_PRIOR_V2}
    out = {}
    for b in BANDS:
        g = sub[sub["band"] == b]
        sp = (g.groupby("month")["fwd_1m"].mean() - mkt).dropna()
        out[b] = {
            "reproduced_annualised_linear_pct": round(100.0 * float(sp.mean()) * 12.0, 2),
            "published_pct": round(100.0 * pub[b], 2),
            "reproduced_t": round(float(sp.mean() / (sp.std(ddof=1) / np.sqrt(len(sp)))), 3),
            "name_months": int(len(g)),
            "months": int(len(sp)),
        }
    return {
        "recipe_as_found_in_code": [
            "benchmark = EW mean of the WHOLE analyst-covered panel, splits included "
            "(scripts/tracker_ibes_backtest.py:564)",
            "band membership measured on rows WITHOUT split_prior_year (S30b)",
            "annualisation LINEAR: mean monthly x 12",
            "published series are NET of 10bps/side on measured turnover; this "
            "reproduction is GROSS, which accounts for most of the residual",
        ],
        "bands": out,
        "why_this_matters": (
            "the +16.55%/yr everyone quotes is an excess over the analyst-covered "
            "panel's own equal-weighted mean -- NOT over the market. The same book "
            "against the value-weighted market is a different and smaller number, "
            "and it is that number, not the quoted one, that a book earns."),
    }


# ------------------------------------------------------------------- the run

def one_variant(df: pd.DataFrame, tag: str, note: str) -> tuple[dict, dict, dict]:
    """The full four-horizon sweep on one universe. Returns
    (block, screen p-values, export p-values)."""
    per_h: dict = {}
    p_screen: dict = {}
    p_export: dict = {}
    for h in HORIZONS:
        pew = panel_ew_benchmark(df, h)
        c = cohort_frame(df, h, pew)
        per_b: dict = {}
        for b in BANDS:
            contam = contamination_months(df, df["band"] == b, h)
            g = c[(c["band"] == b) & (~c["month"].isin(contam["excluded_months"]))]
            if len(g) < 50:
                per_b[b] = {"status": "TOO_FEW_ROWS", "rows": int(len(g))}
                continue
            res = ew_book(g, h, COST_BPS_PRIMARY)
            bk = res["book"]
            bk25 = ew_book(g, h, COST_BPS_SENSITIVITY)["book"]
            ex = series_stats(bk["excess_vw"], h, "excess_vw")
            rs = series_stats(bk["resid"], h, "resid")
            leg = series_stats(bk["beta_leg"], h, "beta_leg")
            entry = {
                "contamination_clause": contam,
                "n_months": int(len(bk)),
                "name_months": int(len(g)),
                "median_names_per_month": int(bk["n_names"].median()),
                "mean_beta_pre": round(float(bk["beta_mean"].mean()), 4),
                "median_beta_pre": round(float(bk["beta_median"].mean()), 4),
                "turnover_sum_abs_dw_median": round(res["median_turnover"], 4),
                "raw_return": series_stats(bk["fwd"], h, "raw"),
                "market_vw_same_months": series_stats(bk["mkt_vw"], h, "mkt_vw"),
                "excess_vw": ex,
                "excess_ew_CRSP_COMPARISON_ONLY": series_stats(bk["excess_ew"], h, "excess_ew"),
                "excess_panel_INCUMBENT_BENCHMARK": series_stats(
                    bk["excess_panel"], h, "excess_panel"),
                "beta_neutral_resid": rs,
                "beta_leg_raw_minus_neutral": leg,
                "beta_leg_pp_per_year": leg.get("annualised_pct"),
                "net_10bps": {"excess_vw": series_stats(bk["excess_vw_net"], h, "ex_net10"),
                              "resid": series_stats(bk["resid_net"], h, "resid_net10")},
                "net_25bps": {"excess_vw": series_stats(bk25["excess_vw_net"], h, "ex_net25"),
                              "resid": series_stats(bk25["resid_net"], h, "resid_net25")},
                "terminal_wealth_gross": phase_chains(bk, h, "fwd"),
                "terminal_wealth_net_10bps": phase_chains(bk, h, "fwd_net"),
                "terminal_wealth_market_vw": phase_chains(bk, h, "mkt_vw"),
                "era_splits_excess_vw": era_split(bk, h, "excess_vw"),
                "era_splits_resid": era_split(bk, h, "resid"),
                "leave_one_year_out_excess_vw": leave_one_year_out(bk, h, "excess_vw"),
                "by_year_excess_vw_annualised_pct": by_year(bk, h, "excess_vw"),
                "by_year_resid_annualised_pct": by_year(bk, h, "resid"),
            }
            per_b[b] = entry
            nb = ex.get("n_effective_date_blocks") or 0
            p_screen[f"{tag}|{b}@{h}m_excess_vw"] = two_sided_p(ex.get("t_block"), max(nb - 1, 2))
            if b == "b_3_5" and tag == "primary":
                p_export[f"b_3_5@{h}m_excess_vw"] = two_sided_p(ex.get("t_block"), max(nb - 1, 2))
                rn = rs.get("n_effective_date_blocks") or 0
                p_export[f"b_3_5@{h}m_beta_neutral_resid"] = two_sided_p(
                    rs.get("t_block"), max(rn - 1, 2))
            print(f"    [{tag}] {h:2d}m {b:12s} vw {ex.get('annualised_pct'):+8.2f}%/yr "
                  f"t_b {ex.get('t_block')}  resid {rs.get('annualised_pct'):+8.2f}%/yr "
                  f"t_b {rs.get('t_block')}  beta_leg {leg.get('annualised_pct'):+6.2f}pp  "
                  f"beta {entry['mean_beta_pre']:.2f}")
        ctrl = beta_matched_control(c, h, "b_3_5")
        ctrl.pop("_book", None)
        per_h[f"{h}m"] = {"bands": per_b, "beta_matched_control_for_b_3_5": ctrl}
    return ({"universe_note": note, "per_horizon": per_h}, p_screen, p_export)


def resolve_band_is_beta(primary: dict) -> dict:
    """PREREG_BAND_IS_BETA_1's decision rule, applied verbatim and per horizon.

    The prereg declares the rule at the BOOK level; the four-horizon sweep is
    this script's extension, so the horizon rows are labelled EXPLORATORY and
    the 1-month row -- the clock the book is actually traded on -- carries the
    declared resolution."""
    out = {}
    for h in HORIZONS:
        e = primary["per_horizon"][f"{h}m"]["bands"].get("b_3_5")
        if not e or e.get("status"):
            continue
        leg = e["beta_leg_pp_per_year"]
        neu = e["beta_neutral_resid"]["annualised_pct"]
        neu_t = e["beta_neutral_resid"]["t_block"]
        ex = e["excess_vw"]["annualised_pct"]
        rule_a = (leg is not None and leg >= BETA_LEG_THRESHOLD_PP)
        rule_b = (neu is not None and neu > NEUTRAL_REFUTES_PP
                  and neu_t is not None and neu_t >= NEUTRAL_REFUTES_T)
        out[f"{h}m"] = {
            "excess_vw_pp_per_year": ex,
            "beta_leg_pp_per_year": leg,
            "beta_leg_share_of_excess": (round(leg / ex, 3)
                                         if (ex not in (None, 0) and leg is not None) else None),
            "beta_neutral_pp_per_year": neu,
            "beta_neutral_t_block": neu_t,
            "rule_beta_leg_ge_6pp_OPPORTUNITY_SET_PLUS_LEVERAGE": bool(rule_a),
            "rule_neutral_gt_10pp_and_t_ge_2_REFUTES_hypothesis": bool(rule_b),
            "status": "DECLARED" if h == 1 else "EXPLORATORY (prereg declares the "
                                                "rule at the book level, not per horizon)",
        }
    return out


def run() -> dict:
    t0 = datetime.now(timezone.utc)
    print("loading the learner's PIT table ...")
    df = pd.read_parquet(D.TRAIN_TABLE)
    print(f"  {len(df):,} rows x {df.shape[1]} cols")
    df["beta_pre"] = B.attach(df, B.load())
    print(f"  beta present on {df['beta_pre'].notna().mean():.4f} of rows")

    receipt: dict = {
        "artefact": "BAND_HORIZON_SELF_ATTACK",
        "written_at_utc": t0.isoformat(),
        "licence": "PRODUCT_EXPERIMENT",
        "executes": ["TRIAL-BAND-IS-BETA-1 (primary)",
                     "TRIAL-RANK-VS-EXPRETURN-1 (random-order control arm, horizon 1m)"],
        "not_executed": {
            "TRIAL-BIAS-CORRECTED-BAND-1":
                "NOT RUN. It needs a per-contributor optimism panel from tr_ibes.ptgdetu "
                "(4.66m analyst-level targets) with a 20-resolved-forecast floor and three "
                "years of burn-in. Running half of it would produce a number its own prereg "
                "would not accept. Declared so the absence is a decision, not an omission."},
        "prior_version": P.PRIOR_VERSION,
        "band_constants_as_published": {b[2]: b[3] for b in P.BAND_PRIOR_V2},
        "dataset": {
            "table": "backend/data/optimus/learner/train_table.parquet",
            "rows": int(len(df)), "months": int(df["month"].nunique()),
            "names": int(df["permno"].nunique()), "window": "2013-2024",
            "benchmark_primary": "value-weighted CRSP common stock (prereg-frozen)",
            "benchmark_also_stored": ["equal-weighted CRSP",
                                      "equal-weighted analyst-covered panel (the "
                                      "incumbent's own, and the one +16.55 is quoted against)"],
        },
        "beta": {"panel": "backend/data/optimus/learner/beta_panel.parquet",
                 "estimator": "OLS of daily return on daily VW market return",
                 "window_sessions": B.BETA_WINDOW, "min_obs": B.BETA_MIN_OBS,
                 "window_ends": "last session STRICTLY BEFORE entry_date -- no beta is "
                                "fitted on a return it is later used to explain",
                 "winsor": [B.WINSOR_LO, B.WINSOR_HI],
                 "risk_free": "0.0, DECLARED -- cancels from a daily slope",
                 "coverage_share_of_rows": round(float(df["beta_pre"].notna().mean()), 4)},
        "costs": {"primary_bps_per_side": COST_BPS_PRIMARY,
                  "sensitivity_bps_per_side": COST_BPS_SENSITIVITY,
                  "convention": "cost = sum|dw| x bps/side, where the old weights are DRIFTED "
                                "by their realised holding-period return before the diff; "
                                "sum|dw| counts the sell leg and the buy leg",
                  "zero_cost_diagnostic": False},
        "seed": SEED,
        "sector_column_NOT_USED": {
            "claim": "no result in this receipt groups, neutralises or matches on `sector`.",
            "why_it_is_stated": (
                "a cross-agent finding on 2026-09-03: CRSP SIC 9000-9999 in this panel is "
                "98.8% code 9999 = NONCLASSIFIABLE, and tracker_ibes_backtest.SIC_DIVISIONS "
                "labels that whole range 'Public Administration' -- about 99,334 of 441,278 "
                "rows (22.5%) carry a sector label that actually means UNKNOWN. Anything "
                "sector-neutral built on that column is contaminated. Nothing here is."),
            "what_the_matched_control_matches_on":
                "pre-period beta decile x market-capitalisation decile x calendar month. "
                "No industry leg, by design -- the prereg names beta, cap and month only.",
            "consequence_if_a_sector_leg_is_added_later":
                "the 9999 block must be its own honest UNCLASSIFIED bucket, never folded "
                "into Public Administration.",
        },
        "statistics_note": (
            "t_naive is printed and is OVERSTATED for h>1 by construction. t_block "
            "(non-overlapping, averaged over the h phase offsets) is what every decision "
            "rule reads; n_effective counts DATE BLOCKS (canon 58)."),
    }

    print("pinning against the published constants ...")
    receipt["reproduction_of_published_constants"] = reproduce_published(df)
    for b, v in receipt["reproduction_of_published_constants"]["bands"].items():
        print(f"    {b:12s} reproduced {v['reproduced_annualised_linear_pct']:+7.2f}%/yr "
              f"(t {v['reproduced_t']:+.2f})  published {v['published_pct']:+7.2f}%/yr")

    # ---- PRIMARY universe: hygiene + split-readable, the object the engine trades.
    split_free = ~df["split_prior_year"].astype(bool)
    primary, ps, pe = one_variant(
        df[split_free].copy(), "primary",
        "hygiene (close>=$2, coverage>=2, applied by the band labeller) AND "
        "split_prior_year == False. S30b: a stale target across a split is not an "
        "opinion, and the incumbent's own published constants are measured this way.")
    sens, ps2, _ = one_variant(
        df.copy(), "with_splits",
        "SENSITIVITY: the same sweep with split_prior_year rows KEPT. The 3-5 band's "
        "headline falls by roughly 3pp/yr when they are kept, which is why they are "
        "excluded rather than a matter of taste.")
    receipt["primary_split_readable"] = primary
    receipt["sensitivity_splits_kept"] = sens

    receipt["decision_rules_PREREG_BAND_IS_BETA_1"] = resolve_band_is_beta(primary)

    # ---- the contamination clause is more binding on a 30-name band than on a
    # 2,000-name one: two missing betas in a 30-name month is 6.7% and trips a
    # 5% rule. It excluded 13 months from b_3_5, almost all of them 2013-2014
    # where the beta panel's own 120-session warm-up bites. Declared in advance,
    # so it stays primary -- but the without-clause number is printed beside it
    # rather than left for a later reader to discover.
    contam_sens = {}
    for h in HORIZONS:
        c = cohort_frame(df[split_free], h, panel_ew_benchmark(df, h))
        g = c[c["band"] == "b_3_5"]
        bk = ew_book(g, h, COST_BPS_PRIMARY)["book"]
        ex = series_stats(bk["excess_vw"], h, "no_clause_excess_vw")
        rs = series_stats(bk["resid"], h, "no_clause_resid")
        wc = primary["per_horizon"][f"{h}m"]["bands"]["b_3_5"]
        contam_sens[f"{h}m"] = {
            "with_clause_months": wc["n_months"],
            "with_clause_excess_vw_pp": wc["excess_vw"]["annualised_pct"],
            "with_clause_t_block": wc["excess_vw"]["t_block"],
            "without_clause_months": ex["n_months"],
            "without_clause_excess_vw_pp": ex["annualised_pct"],
            "without_clause_t_block": ex["t_block"],
            "without_clause_resid_pp": rs["annualised_pct"],
            "without_clause_resid_t_block": rs["t_block"],
        }
    receipt["contamination_clause_sensitivity_b_3_5"] = {
        "why": "the >5%-missing-beta clause is prereg-declared and applies to BOTH arms, "
               "but on a ~30-name band two missing betas trips it. It removed 13 months, "
               "mostly 2013-2014, and it moved the 1m headline by ~5pp. Printed, not buried.",
        "by_horizon": contam_sens,
    }

    receipt["multiplicity"] = {
        "rule": "canon 63: SCREEN = BH-FDR at q=0.05, EXPORT = Holm at alpha=0.05. "
                "p comes from t_block on (n_effective - 1) dof, never from the naive t.",
        "screen_BH_FDR": bh_fdr({**ps, **ps2}, 0.05),
        "screen_family": {k: (round(v, 6) if np.isfinite(v) else None)
                          for k, v in {**ps, **ps2}.items()},
        "export_Holm": holm(pe, 0.05),
        "export_family": {k: (round(v, 6) if np.isfinite(v) else None) for k, v in pe.items()},
    }

    print("ordering arena on the admitted set (h=1m) ...")
    c1 = cohort_frame(df[split_free], 1, panel_ew_benchmark(df, 1))
    receipt["ordering_arena_h1m"] = ordering_arena(c1, np.random.default_rng(SEED + 1))

    print("prior rank IC by horizon ...")
    ic = {}
    for h in HORIZONS:
        c = cohort_frame(df[split_free], h, panel_ew_benchmark(df, h))
        def _ic(frame: pd.DataFrame, xcol: str, minn: int) -> dict:
            vals = [g[xcol].corr(g["excess_vw"], method="spearman")
                    for _, g in frame.groupby("month") if len(g) >= minn]
            s = pd.Series(vals).dropna()
            if len(s) < 3:
                return {"mean_ic": None, "t_block": None, "n_months": int(len(s))}
            return {"mean_ic": round(float(s.mean()), 5),
                    "t_naive_OVERSTATED": round(float(
                        s.mean() / (s.std(ddof=1) / np.sqrt(len(s)))), 3),
                    "t_block": round(block_t(s, h)["t"], 3),
                    "n_effective_date_blocks": block_t(s, h)["n_blocks"],
                    "n_months": int(len(s))}
        ic[f"{h}m"] = {
            "prior_vs_excess_vw_WHOLE_PANEL": _ic(c, "prior", 20),
            "ratio_inside_admissible_1_5_to_5": _ic(c[c["in_admissible"]], "ratio", 20),
            "ratio_inside_b_3_5": _ic(c[c["band"] == "b_3_5"], "ratio", 10),
        }
        print(f"    {h:2d}m prior IC {ic[f'{h}m']['prior_vs_excess_vw_WHOLE_PANEL']['mean_ic']} "
              f"t_block {ic[f'{h}m']['prior_vs_excess_vw_WHOLE_PANEL']['t_block']}  "
              f"inside-3-5 IC {ic[f'{h}m']['ratio_inside_b_3_5']['mean_ic']} "
              f"t_block {ic[f'{h}m']['ratio_inside_b_3_5']['t_block']}")
    receipt["prior_rank_ic_by_horizon"] = ic

    # ---- the four answers the session was asked for, computed rather than argued
    b35 = {h: primary["per_horizon"][f"{h}m"]["bands"]["b_3_5"] for h in HORIZONS}
    receipt["verdict"] = {
        "question": "is the 3-5 band (a) an exclusion rule, (b) a 12-month expected-return "
                    "prior, (c) a beta/size exposure, or (d) a genuine 1-month selector?",
        "money_by_horizon_excess_vw_pp_per_year": {
            f"{h}m": b35[h]["excess_vw"]["annualised_pct"] for h in HORIZONS},
        "money_by_horizon_t_block": {
            f"{h}m": b35[h]["excess_vw"]["t_block"] for h in HORIZONS},
        "beta_neutral_by_horizon_pp_per_year": {
            f"{h}m": b35[h]["beta_neutral_resid"]["annualised_pct"] for h in HORIZONS},
        "ic_is_an_overlap_artefact": {
            f"{h}m": {"mean_ic": ic[f"{h}m"]["prior_vs_excess_vw_WHOLE_PANEL"]["mean_ic"],
                      "t_naive": ic[f"{h}m"]["prior_vs_excess_vw_WHOLE_PANEL"]["t_naive_OVERSTATED"],
                      "t_block": ic[f"{h}m"]["prior_vs_excess_vw_WHOLE_PANEL"]["t_block"],
                      "n_effective": ic[f"{h}m"]["prior_vs_excess_vw_WHOLE_PANEL"]["n_effective_date_blocks"]}
            for h in HORIZONS},
        "ic_root_h_scaling_test": {
            "note": "if the prior were a 12-month object sampled monthly, the 12-month IC "
                    "would be about sqrt(12) x the 1-month IC. Sub-sqrt(h) growth means "
                    "the per-month information DECAYS with horizon.",
            "ic_1m": ic["1m"]["prior_vs_excess_vw_WHOLE_PANEL"]["mean_ic"],
            "ic_12m_observed": ic["12m"]["prior_vs_excess_vw_WHOLE_PANEL"]["mean_ic"],
            "ic_12m_if_sqrt_h": round(
                ic["1m"]["prior_vs_excess_vw_WHOLE_PANEL"]["mean_ic"] * np.sqrt(12.0), 5),
        },
        "screen_survivors_BH_FDR": receipt["multiplicity"]["screen_BH_FDR"]["survivors"],
        "export_survivors_Holm": receipt["multiplicity"]["export_Holm"]["survivors"],
        "matched_control_1m_excess_vw_pp_per_year":
            primary["per_horizon"]["1m"]["beta_matched_control_for_b_3_5"]["excess_vw"]["annualised_pct"],
        "ordering_arena_resolved":
            receipt["ordering_arena_h1m"]["decision_rule_PREREG_RANK_VS_EXPRETURN_1"]["resolved"],
    }
    receipt["runtime_seconds"] = round((datetime.now(timezone.utc) - t0).total_seconds(), 1)
    return receipt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-betas", action="store_true")
    a = ap.parse_args(argv)
    if a.build_betas:
        df = pd.read_parquet(D.TRAIN_TABLE, columns=["permno"])
        panel, rec = B.build(df["permno"].unique(), 2012, 2024)
        B.save(panel)
        print(json.dumps(rec, indent=2))
        return 0
    rep = run()
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    print(f"\nreceipt -> {RECEIPT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
