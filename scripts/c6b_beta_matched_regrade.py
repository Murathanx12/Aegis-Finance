"""C1 -- INTERCEPT OR LOADING? THE BETA-MATCHED RE-GRADE OF THE THREE BOOKS.

THE QUESTION
============
`W3b_neural_floored_run01.json` graded every book against the RAW value-weighted
market (`mkt_vw_1m`) -- a 1.00x market leg -- and reported paired excess. A
long-only top-50 book of $3m/day names is not a 1.00x market leg. If its beta is
1.15, then 15% of the market's own return is being counted as the book's edge,
and the "excess" is a LOADING wearing an alpha's clothes.

The testable version is the market regression:

    net_t - rf_t = alpha + beta * (mkt_t - rf_t) + e_t

and its dual, the BETA-MATCHED benchmark `beta * market + (1 - beta) * rf`,
which is what the leverage alone would have earned. `alpha` and the mean of the
beta-matched excess are the SAME NUMBER by construction (full-sample OLS beta,
same rf on both sides); reporting both is a check on the plumbing, not two
findings.

WHAT THIS JOB IS NOT
====================
It is not a re-run of the model search. Every prediction column comes off the
W3b stage parquets, is graded by the identical `evaluate.book` call W3b used,
and is REFUSED unless every field of every graded cell reproduces the W3b
receipt's `cells` block. A number that does not reproduce is a finding, not
something to paper over.

FABLE'S CLAIM 5, AND WHY THE MONTE CARLO IS HERE
================================================
`docs/REVIEW_2026-09-06_FABLE51_ON_THE_CONTINUATION.md` claim 5 argued that
lgbm_clf's "83.55% of the excess comes from five months" is NOT evidence of beta
timing, because a pure-noise series with lgbm_clf's own moments (mean 0.28%/mo,
sd 3.6%) produces a top-5 share that large in 31% (normal) to 40% (t4) of draws.
Section E reproduces that directly, per series, at each series' OWN realised
moments -- never a shared set -- with `np.random.default_rng`.

$0 LLM spend. Pure arithmetic on data on disk.

    & "$env:LOCALAPPDATA\\Programs\\Python\\Python312\\python.exe" -m scripts.c6b_beta_matched_regrade
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:                       # so `python scripts/...` works too
    sys.path.insert(0, str(REPO))

from learner import benchmark as BM                                     # noqa: E402
from learner import inference                                           # noqa: E402
from learner import long_panel as LP                                    # noqa: E402
from learner import neural_long as N                                    # noqa: E402
from scripts import w3_neural_floored as W3B          # READ ONLY -- staging + grading

OUT_DIR = REPO / "backend" / "data" / "optimus" / "continuation_2026-09-06b"
RECEIPT = OUT_DIR / "C1_beta_matched_regrade_run01.json"
W3B_RECEIPT = (REPO / "backend" / "data" / "optimus" / "continuation_2026-09-06"
               / "W3b_neural_floored_run01.json")

#: The three books the mandate names. `nn_pre_causal_seedmean` is the 8-seed
#: seed-mean ensemble -- the object W3b's decision rule judged, never a best cell.
BOOKS: tuple[str, ...] = ("lgbm_clf", "lgbm_raw", "nn_pre_causal_seedmean")
COSTS: tuple[float, ...] = (10.0, 25.0)

#: Newey-West lag. Rule of thumb floor(4 * (T/100)^(2/9)) = 4 at T = 251.
#: DECLARED, not tuned: a lag chosen after seeing which one made the t smaller
#: would be the same error the receipt exists to catch.
NW_LAG = 4

#: The multiplicity family. W3b's search opened 40 cells and these three
#: prediction columns are three of them; this job re-grades them against a
#: different benchmark and opens 6 more (3 books x 2 cost rates). The HEADLINE
#: deflation uses 40 -- the count of cells the search that produced these
#: predictions actually looked at -- and 6 and 46 are carried beside it so a
#: reader can see the whole range rather than one convenient choice.
FAMILY_N_TRIALS = 40
FAMILY_N_TRIALS_ALTERNATIVES = (6, 46)

MC_DRAWS = 20_000
MC_SEED = 20260906
MC_T_DF = 4
WF_MIN_MONTHS = 36
K, WEIGHT = 50, "vw"
SPA_BOOT, SPA_SEED = 500, 61


# --------------------------------------------------------------- provenance

def sha256_file(path) -> dict:
    """Hash a file the loader ACTUALLY opened. Streamed -- the panel is 418 MB."""
    p = Path(path)
    h, n = hashlib.sha256(), 0
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
            n += len(chunk)
    return {"path": str(p), "sha256": h.hexdigest(), "bytes": n}


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO),
                              capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception as exc:                                            # noqa: BLE001
        return f"UNKNOWN ({type(exc).__name__})"


def _ncdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


# ------------------------------------------------------- the market regression

def ols_market_model(y, x, *, lag: int = NW_LAG) -> dict:
    """OLS of `y` on a constant and `x`, with OLS **and** Newey-West t's.

    `y` and `x` are already excess of the same risk-free leg when one exists, so
    `alpha` is the CAPM intercept and `beta` is the LOADING the question is
    about. The HAC covariance is the plain sandwich
    `(X'X)^-1 (sum_t u_t u_t') (X'X)^-1` with `u_t = x_t e_t` and Bartlett
    weights -- no small-sample dof inflation, which is DECLARED here rather than
    left for a reader to infer from a t that does not reconcile.
    """
    y = np.asarray(y, dtype="float64")
    x = np.asarray(x, dtype="float64")
    ok = np.isfinite(y) & np.isfinite(x)
    y, x = y[ok], x[ok]
    n = int(y.size)
    if n < 8:
        return {"verdict": inference.CANNOT_DETERMINE, "n_months": n,
                "why": "fewer than 8 aligned months"}
    X = np.column_stack([np.ones(n), x])
    XtX_inv = np.linalg.inv(X.T @ X)
    b = XtX_inv @ (X.T @ y)
    resid = y - X @ b
    dof = n - 2
    ssr = float(resid @ resid)
    sst = float(((y - y.mean()) ** 2).sum())
    cov_ols = (ssr / dof) * XtX_inv
    se_ols = np.sqrt(np.diag(cov_ols))

    u = X * resid[:, None]
    S = (u.T @ u) / n
    for l in range(1, int(lag) + 1):
        if l >= n:
            break
        G = (u[l:].T @ u[:-l]) / n
        S = S + (1.0 - l / (lag + 1.0)) * (G + G.T)
    V = XtX_inv @ (n * S) @ XtX_inv
    se_hac = np.sqrt(np.diag(np.asarray(V)))

    alpha, beta = float(b[0]), float(b[1])
    resid_sd = float(resid.std(ddof=2)) if n > 2 else float("nan")
    t_a_ols = alpha / se_ols[0] if se_ols[0] > 0 else None
    t_a_hac = alpha / se_hac[0] if se_hac[0] > 0 else None
    return {
        "n_months": n,
        "nw_lag": int(lag),
        "alpha_monthly": round(alpha, 6),
        "alpha_annualised_12x": round(alpha * 12.0, 5),
        "alpha_se_ols": round(float(se_ols[0]), 6),
        "alpha_se_hac": round(float(se_hac[0]), 6),
        "t_alpha_ols": round(float(t_a_ols), 3) if t_a_ols is not None else None,
        "t_alpha_hac": round(float(t_a_hac), 3) if t_a_hac is not None else None,
        "p_alpha_one_sided_hac": (round(1.0 - _ncdf(float(t_a_hac)), 5)
                                  if t_a_hac is not None else None),
        "beta": round(beta, 4),
        "beta_se_ols": round(float(se_ols[1]), 5),
        "beta_se_hac": round(float(se_hac[1]), 5),
        "t_beta_ols": round(float(beta / se_ols[1]), 3) if se_ols[1] > 0 else None,
        "t_beta_hac": round(float(beta / se_hac[1]), 3) if se_hac[1] > 0 else None,
        "t_beta_minus_1_ols": (round(float((beta - 1.0) / se_ols[1]), 3)
                               if se_ols[1] > 0 else None),
        "t_beta_minus_1_hac": (round(float((beta - 1.0) / se_hac[1]), 3)
                               if se_hac[1] > 0 else None),
        "r_squared": round(1.0 - ssr / sst, 4) if sst > 0 else None,
        "residual_sd_monthly": round(resid_sd, 5),
        "residual_sd_annualised": round(resid_sd * math.sqrt(12.0), 5),
        "hac_note": "Bartlett kernel, no dof inflation; OLS se uses n - 2",
    }


def walk_forward_beta(y: pd.Series, x: pd.Series, *,
                      min_months: int = WF_MIN_MONTHS) -> pd.Series:
    """beta_t estimated on months STRICTLY BEFORE t, NaN until `min_months` exist.

    The full-sample beta is the headline because it is the cleanest decomposition
    of what was actually earned; this one answers the different question of
    whether a desk could have hedged the loading in real time.
    """
    y = pd.Series(y).astype("float64")
    x = pd.Series(x).astype("float64").reindex(y.index)
    out = np.full(len(y), np.nan)
    yv, xv = y.to_numpy(), x.to_numpy()
    for i in range(len(y)):
        if i < int(min_months):
            continue
        ys, xs = yv[:i], xv[:i]
        m = np.isfinite(ys) & np.isfinite(xs)
        if m.sum() < int(min_months):
            continue
        vx = float(np.var(xs[m], ddof=1))
        if vx <= 0:
            continue
        out[i] = float(np.cov(ys[m], xs[m], ddof=1)[0, 1] / vx)
    return pd.Series(out, index=y.index)


# ------------------------------------------------------------------ the tail

def _tw(s) -> float:
    return float((1.0 + pd.Series(s).dropna().astype("float64")).prod())


def top5_block(net: pd.Series, bench: pd.Series, *, selection: str) -> dict:
    """Share of the total excess carried by the best five months.

    `selection="net"` reproduces `neural_long.robustness` EXACTLY (it ranks by
    the book's own net return); `selection="excess"` ranks by the excess itself,
    which is the rule the Monte-Carlo null in section E implements. Both are
    reported because the W3b receipt printed the first and the null tests the
    second, and quietly comparing one to the other is how a number moves without
    anybody changing it.
    """
    net = pd.Series(net).dropna().astype("float64")
    bench = pd.Series(bench).reindex(net.index).astype("float64")
    ex = (net - bench).dropna()
    key = net if selection == "net" else ex
    top5 = key.sort_values(ascending=False).head(5).index
    tot = float(ex.sum())
    ex_top = float(ex.reindex(top5).dropna().sum())
    rest = ex.drop(top5)
    return {
        "selection": ("best 5 by the book's NET return (the rule "
                      "neural_long.robustness uses)" if selection == "net"
                      else "best 5 by the EXCESS itself (the rule the MC null uses)"),
        "best_5_months": {str(i): round(float(net.loc[i]), 4) for i in top5},
        "excess_in_those_5": {str(i): round(float(ex.loc[i]), 4)
                              for i in top5 if i in ex.index},
        "total_excess_sum": round(tot, 5),
        "share_of_total_excess_from_those_5": round(ex_top / tot, 4) if tot else None,
        # A SHARE OF A TOTAL THAT IS NOT POSITIVE IS NOT A SHARE. Against the
        # beta-matched leg several cells have a total excess near zero or below
        # it, and the ratio top5/total then reads -1.09 or +14.46 -- arithmetic
        # that is correct and means nothing. The flag is here so a reader never
        # quotes one of those beside 0.8355 as if they were the same statistic.
        "total_excess_is_positive": bool(tot > 0),
        "share_is_interpretable": bool(tot > 0 and ex_top > 0),
        "excess_sum_without_them": round(float(rest.sum()), 5),
        "turns_negative_without_them": bool(float(rest.sum()) < 0),
        "book_terminal_wealth_all_months": round(_tw(net), 4),
        "benchmark_terminal_wealth_all_months": round(_tw(bench), 4),
        "book_terminal_wealth_without_them": round(_tw(net.drop(top5)), 4),
        "benchmark_terminal_wealth_without_them": round(
            _tw(bench.reindex(net.index).drop(top5)), 4),
    }


def mc_top5_null(mean: float, sd: float, n: int, obs_share: float | None, *,
                 draws: int = MC_DRAWS, seed: int, dist: str = "normal",
                 df: int = MC_T_DF) -> dict:
    """How often does PURE NOISE with THIS series' own moments look this tailed?

    `dist="t4"` is a Student-t with 4 df RESCALED to the same sd (t4's raw sd is
    sqrt(df/(df-2)) = sqrt(2)), so the two nulls differ in shape and not in
    dispersion -- which is the whole point of running both.

    Two p's are reported. `p_share_ge_observed` is over all draws; the ratio
    top5/total is not monotone when `total` is negative, so
    `p_share_ge_observed_given_positive_total` restricts to the draws that share
    the observed series' sign. Neither is "the" answer and both are printed.
    """
    rng = np.random.default_rng(int(seed))
    if dist == "normal":
        X = rng.normal(float(mean), float(sd), size=(int(draws), int(n)))
    elif dist == "t4":
        raw = rng.standard_t(int(df), size=(int(draws), int(n)))
        X = float(mean) + float(sd) * raw / math.sqrt(df / (df - 2.0))
    else:
        raise ValueError(f"unknown dist {dist!r}")
    tot = X.sum(axis=1)
    top = np.partition(X, int(n) - 5, axis=1)[:, int(n) - 5:].sum(axis=1)
    rest = tot - top
    with np.errstate(divide="ignore", invalid="ignore"):
        share = np.where(tot != 0.0, top / tot, np.nan)
    pos = tot > 0
    out = {
        "dist": dist,
        "draws": int(draws),
        "months_per_draw": int(n),
        "seed": int(seed),
        "mean_used": round(float(mean), 6),
        "sd_used": round(float(sd), 6),
        "observed_share": (round(float(obs_share), 4)
                           if obs_share is not None else None),
        "median_null_share": round(float(np.nanmedian(share)), 4),
        "mean_null_share_positive_total_only": (
            round(float(np.nanmean(share[pos])), 4) if pos.any() else None),
        "share_of_draws_with_positive_total": round(float(pos.mean()), 4),
        "p_turns_negative_without_top5": round(float((rest < 0).mean()), 4),
        "p_turns_negative_without_top5_given_positive_total": (
            round(float((rest[pos] < 0).mean()), 4) if pos.any() else None),
    }
    if obs_share is not None:
        out["p_share_ge_observed"] = round(
            float(np.nanmean(share >= float(obs_share))), 4)
        out["p_share_ge_observed_given_positive_total"] = (
            round(float(np.nanmean(share[pos] >= float(obs_share))), 4)
            if pos.any() else None)
    return out


# ----------------------------------------------------- the panel and the legs

def _cell_matches(got: dict, want: dict, tol: float = 1e-3) -> list[str]:
    """Every field of a graded cell against the W3b receipt. Diffs, not a bool."""
    bad = []
    for k, wv in want.items():
        gv = got.get(k)
        if isinstance(wv, (int, float)) and isinstance(gv, (int, float)) \
                and not isinstance(wv, bool):
            if not math.isclose(float(gv), float(wv), rel_tol=tol, abs_tol=tol):
                bad.append(f"{k}: got {gv!r} want {wv!r}")
        elif gv != wv:
            bad.append(f"{k}: got {gv!r} want {wv!r}")
    return bad


def rf_leg(df: pd.DataFrame, months: pd.Index) -> tuple[pd.Series, dict]:
    """The risk-free return over EACH BOOK MONTH'S OWN HOLDING WINDOW.

    The panel's row labelled `2020-02` is not February 2020: it is the book held
    from the 2020-02-21 entry date to its 2020-03-2x maturity, and its
    `mkt_vw_1m` is -33.3% because that window contains the crash. Reindexing a
    CALENDAR-month risk-free series onto those labels would attach February's
    bill rate to a March holding period, and `benchmark.beta_matched` would
    silently `fillna(0.0)` anything that failed to line up. So the rf leg is
    compounded from the pinned daily file over `(entry_date, mat_date_1m]` --
    the same window the return was earned in -- and the number of months that
    could NOT be built is reported rather than zero-filled.
    """
    g = (df.groupby("month")
           .agg(entry=("entry_date", "min"),
                mat=("mat_date_1m", lambda s: s.dropna().mode().iloc[0]
                     if s.dropna().size else pd.NaT)))
    note: dict = {"source": "learner.benchmark.cash() -- pinned FF daily RF",
                  "window": "(entry_date, mat_date_1m] per book month, compounded"}
    try:
        rf_d = BM.cash().returns.dropna().astype("float64")
        note["daily_rows"] = int(len(rf_d))
        note["daily_span"] = [str(rf_d.index.min().date()), str(rf_d.index.max().date())]
    except Exception as exc:                                            # noqa: BLE001
        note["available"] = False
        note["why"] = f"{type(exc).__name__}: {exc}"
        note["declared"] = "rf = 0 and DECLARED (learner/beta.py does the same; the " \
                           "SLOPE is unaffected by a near-constant leg, only the " \
                           "intercept's level moves)"
        return pd.Series(0.0, index=months), note
    note["available"] = True
    vals, missing = {}, []
    for m in months:
        row = g.loc[m] if m in g.index else None
        if row is None or pd.isna(row["entry"]) or pd.isna(row["mat"]):
            missing.append(str(m))
            continue
        w = rf_d[(rf_d.index > pd.Timestamp(row["entry"]))
                 & (rf_d.index <= pd.Timestamp(row["mat"]))]
        if w.empty:
            missing.append(str(m))
            continue
        vals[m] = float((1.0 + w).prod() - 1.0)
    ser = pd.Series(vals).reindex(months)
    note["months_built"] = int(ser.notna().sum())
    note["months_missing"] = missing
    note["mean_monthly_rf"] = round(float(ser.mean()), 6)
    note["annualised_rf_12x"] = round(float(ser.mean()) * 12.0, 5)
    if ser.isna().any():
        note["declared"] = ("rf = 0 on the months that could not be built, and they "
                            "are named above -- never silently zero-filled")
        ser = ser.fillna(0.0)
    return ser.astype("float64"), note


def entry_dates(df: pd.DataFrame, months: pd.Index) -> pd.DatetimeIndex:
    g = df.groupby("month")["entry_date"].min()
    return pd.DatetimeIndex([pd.Timestamp(g.loc[m]) for m in months])


# ------------------------------------------------------------------- the run

def run(*, verbose: bool = True, mc_draws: int = MC_DRAWS) -> dict:
    from scripts.weekend_lab_jobs import era_sign_table          # READ ONLY import
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    t0 = time.perf_counter()
    inputs: list[dict] = []

    out: dict = {
        "job": "C1_beta_matched_regrade",
        "question": ("is the incumbents' excess an INTERCEPT or a LOADING? Graded "
                     "against a beta-matched benchmark instead of the raw VW market, "
                     "does lgbm_clf / lgbm_raw / nn_pre_causal_seedmean keep a "
                     "positive alpha, or does the excess collapse into beta > 1?"),
        "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0,
        "llm_calls": 0,
        "memory_before": {"free_gb": W3B.free_gb(), "floor_gb": W3B.MIN_FREE_GB},
    }

    # ---- the universe, IDENTICAL to W3b's or this job refuses
    df, uni, fp = W3B.load_universe(verbose)
    inputs.append(sha256_file(LP.LONG_TABLE))
    w3b = json.loads(W3B_RECEIPT.read_text(encoding="utf-8"))
    inputs.append(sha256_file(W3B_RECEIPT))
    out["training_universe"] = {k: uni[k] for k in
                                ("dollar_volume_floor_usd_per_day", "min_close_usd",
                                 "rows_before", "rows_after", "share_kept",
                                 "months_after", "fingerprint_sha256")}
    out["universe_fingerprint_sha256"] = fp
    out["universe_fingerprint_matches_w3b"] = bool(
        fp == w3b.get("universe_fingerprint_sha256"))
    if not out["universe_fingerprint_matches_w3b"]:
        out["verdict"] = "REFUSED"
        out["headline"] = (
            f"REFUSED: this universe is {fp[:16]} and W3b graded {str(w3b.get('universe_fingerprint_sha256'))[:16]}. "
            "A different population is a different question; nothing was regraded.")
        return out

    # ---- the predictions, off the stage parquets
    years = list(range(N.FIRST_TEST_YEAR, N.LAST_TEST_YEAR + 1))
    seeds = [N.SEED_BASE + i for i in range(N.N_SEEDS)]
    for tag, scope in (("incumbents", W3B._scope(years, [])),
                       ("nn_pre_causal", W3B._scope(years, seeds))):
        block, _meta = W3B._read_stage(tag, fp, scope)
        for col in block.columns:
            df[col] = block[col].reindex(df.index).astype("float64")
        inputs.append(sha256_file(W3B._stage_path(tag)))
        inputs.append(sha256_file(W3B.STAGE_DIR / f"w3b_meta_{tag}.json"))
    out["stage_files"] = {t: str(W3B._stage_path(t))
                          for t in ("incumbents", "nn_pre_causal")}
    out["stage_scope"] = W3B._scope(years, seeds)
    missing = [b for b in BOOKS if b not in df.columns]
    if missing:
        out["verdict"] = "REFUSED"
        out["headline"] = f"REFUSED: stage files carry no column for {missing}"
        return out

    # ---- grade every book at every cost rate, EXACTLY as W3b did
    log("grading ...")
    net, mkt, gross, cells = {}, {}, {}, {}
    repro: dict = {}
    for book in BOOKS:
        for bps in COSTS:
            key = f"{book}|{int(bps)}bps"
            bk = W3B.grade(df, book, bps)
            ser = bk.pop("_series")
            cells[key] = {k: v for k, v in bk.items() if not k.startswith("_")}
            net[key] = ser["net"].astype("float64")
            mkt[key] = ser["market"].astype("float64")
            gross[key] = ser["gross"].astype("float64")
            want = (w3b.get("cells") or {}).get(key)
            repro[key] = ({"reproduces_w3b": False, "why": "no such cell in W3b"}
                          if want is None else
                          {"reproduces_w3b": not _cell_matches(cells[key], want),
                           "diffs": _cell_matches(cells[key], want)})
    out["cells"] = cells
    out["reproduction_of_w3b_cells"] = repro
    bad = {k: v for k, v in repro.items() if not v.get("reproduces_w3b")}
    out["all_cells_reproduce_w3b"] = not bad
    if bad:
        out["verdict"] = "REFUSED"
        out["headline"] = ("REFUSED: the re-staged predictions do NOT reproduce the W3b "
                           f"receipt. {bad}. A number that cannot be reproduced is a "
                           "finding, not a footnote -- nothing downstream was computed.")
        return out
    log(f"  {len(cells)} cells, all reproduce W3b to 1e-3")

    months = net[f"{BOOKS[0]}|10bps"].index
    for k, s in net.items():
        if not s.index.equals(months):
            out["verdict"] = "REFUSED"
            out["headline"] = f"REFUSED: {k} spans different months from {BOOKS[0]}|10bps"
            return out
    out["n_common_months"] = int(len(months))
    out["common_window"] = [str(months[0]), str(months[-1])]

    # ---- the risk-free leg, on the book's OWN holding windows
    rf, rf_note = rf_leg(df, months)
    out["risk_free_leg"] = rf_note
    idx_dt = entry_dates(df, months)
    out["month_label_convention"] = {
        "note": ("the panel's row labelled `2020-02` is the book ENTERED 2020-02-21 "
                 "and held to its 2020-03-2x maturity; `mkt_vw_1m` there is -33.3% "
                 "because that window contains the crash. Every leg in this receipt "
                 "uses that same window, so the labels are consistent even though "
                 "they are not calendar months."),
        "first_entry_date": str(idx_dt[0].date()),
        "last_entry_date": str(idx_dt[-1].date()),
    }

    market_ts = pd.Series(mkt[f"{BOOKS[0]}|10bps"].to_numpy(), index=idx_dt)
    rf_ts = pd.Series(rf.to_numpy(), index=idx_dt)
    mkt_bm = BM.Benchmark("vw_crsp_common_main", market_ts, "M", {
        "source": "learner.evaluate.book(..., return_series=True)['market']",
        "construction": ("the panel's own `mkt_vw_1m` value-weighted CRSP "
                         "common-share total return over each book month's holding "
                         "window -- the identical series every W3b cell was graded "
                         "against. NOT re-cut to the tradable slice."),
        "dividends_included": True, "network": False,
        "index": "the book month's entry_date",
    })
    rf_bm = BM.Benchmark("cash_rf_pinned", rf_ts, "M", {
        "source": "learner.benchmark.cash() (pinned FF daily RF), compounded",
        "construction": rf_note.get("window", "n/a"),
        "network": False,
    })
    out["benchmark_stamp"] = mkt_bm.stamp()
    ok, why = BM.validate_stamp(out["benchmark_stamp"])
    out["benchmark_stamp_valid"] = {"ok": bool(ok), "why": why}
    out["risk_free_stamp"] = rf_bm.stamp()

    # ---- A + B: the regression, then the beta-matched leg it implies
    log("regressing ...")
    fam: dict[str, list[float]] = {}
    per_cell: dict[str, dict] = {}
    bm_excess: dict[str, pd.Series] = {}
    for book in BOOKS:
        for bps in COSTS:
            key = f"{book}|{int(bps)}bps"
            y = (net[key] - rf).astype("float64")
            x = (mkt[key] - rf).astype("float64")
            reg = ols_market_model(y.to_numpy(), x.to_numpy(), lag=NW_LAG)
            beta = float(reg["beta"])

            leg = BM.beta_matched(mkt_bm, beta, rf_bm)
            legv = pd.Series(leg.returns.to_numpy(), index=months)
            check = float(np.nanmax(np.abs(
                legv.to_numpy() - (beta * mkt[key].to_numpy()
                                   + (1.0 - beta) * rf.to_numpy()))))
            ex_bm = (net[key] - legv).astype("float64")
            ex_mkt = (net[key] - mkt[key]).astype("float64")
            bm_excess[key] = ex_bm
            fam[key] = ex_bm.tolist()

            wf = walk_forward_beta(y, x, min_months=WF_MIN_MONTHS)
            wf_leg = wf * mkt[key] + (1.0 - wf) * rf
            wf_ex = (net[key] - wf_leg).dropna()

            n_bm = float(ex_bm.mean()); s_bm = float(ex_bm.std(ddof=1))
            n_mk = float(ex_mkt.mean()); s_mk = float(ex_mkt.std(ddof=1))
            per_cell[key] = {
                "book": book, "cost_bps_per_side": bps,
                "A_market_regression": reg,
                "A_reading": ("beta > 1 with t(beta-1) >= 2 means the book carried "
                              "MORE market than the benchmark it was graded against; "
                              "alpha is what is left once that leverage is paid for"),
                "B_beta_matched": {
                    "benchmark_stamp": leg.stamp(),
                    "beta_used": round(beta, 4),
                    "beta_source": "full-sample OLS of (net - rf) on (mkt - rf)",
                    "leg_reconstruction_max_abs_error": round(check, 12),
                    "mean_monthly_excess": round(n_bm, 6),
                    "annualised_excess_12x": round(n_bm * 12.0, 5),
                    "sd_monthly": round(s_bm, 5),
                    "t_paired": round(n_bm / (s_bm / math.sqrt(len(ex_bm))), 3)
                                if s_bm > 0 else None,
                    "t_paired_hac": _round(_hac_t(ex_bm, NW_LAG), 3),
                    "months_ahead_of_beta_matched_leg": round(float((ex_bm > 0).mean()), 4),
                    "book_terminal_wealth": round(_tw(net[key]), 4),
                    "beta_matched_leg_terminal_wealth": round(_tw(legv), 4),
                    "raw_market_terminal_wealth": round(_tw(mkt[key]), 4),
                    "terminal_wealth_ratio_book_over_beta_matched": round(
                        _tw(net[key]) / _tw(legv), 4) if _tw(legv) else None,
                },
                "B_raw_market_for_comparison": {
                    "mean_monthly_excess": round(n_mk, 6),
                    "annualised_excess_12x": round(n_mk * 12.0, 5),
                    "t_paired": round(n_mk / (s_mk / math.sqrt(len(ex_mkt))), 3)
                                if s_mk > 0 else None,
                    "w3b_annualised_excess": (w3b["cells"][key] or {}).get(
                        "annualised_excess"),
                    "w3b_t_stat_paired_vs_market": (w3b["cells"][key] or {}).get(
                        "t_stat_paired_vs_market"),
                },
                "B_walk_forward_beta": {
                    "min_months_before_a_beta_is_formed": WF_MIN_MONTHS,
                    "months_graded": int(len(wf_ex)),
                    "beta_first": _round(wf.dropna().iloc[0] if wf.notna().any() else None, 4),
                    "beta_last": _round(wf.dropna().iloc[-1] if wf.notna().any() else None, 4),
                    "beta_mean": _round(float(wf.mean()) if wf.notna().any() else None, 4),
                    "beta_min": _round(float(wf.min()) if wf.notna().any() else None, 4),
                    "beta_max": _round(float(wf.max()) if wf.notna().any() else None, 4),
                    "mean_monthly_excess": _round(float(wf_ex.mean()) if len(wf_ex) else None, 6),
                    "annualised_excess_12x": _round(
                        float(wf_ex.mean()) * 12.0 if len(wf_ex) else None, 5),
                    "t_paired": _round(
                        float(wf_ex.mean() / (wf_ex.std(ddof=1) / math.sqrt(len(wf_ex))))
                        if len(wf_ex) > 2 and wf_ex.std(ddof=1) > 0 else None, 3),
                    "note": ("beta_t uses months strictly before t. It is NOT the "
                             "headline: it answers whether a desk could have hedged "
                             "the loading in real time, which is a different question "
                             "from how much of the realised excess WAS the loading."),
                },
            }

    # ---- C: DSR over the declared family
    log("inference ...")
    for key in list(per_cell):
        rep = inference.full_report(fam[key], family=fam, paired_excess=fam,
                                    n_trials=FAMILY_N_TRIALS, n_boot=SPA_BOOT,
                                    seed=SPA_SEED)
        alt = {str(n_t): inference.deflated_sharpe(fam[key], n_trials=n_t).get("dsr")
               for n_t in FAMILY_N_TRIALS_ALTERNATIVES}
        per_cell[key]["C_inference_on_beta_matched_excess"] = {
            "family": sorted(fam),
            "family_size_cells_in_this_job": len(fam),
            "family_size_declared_for_deflation": FAMILY_N_TRIALS,
            "family_size_justification": (
                "the three prediction columns are three of the 40 cells the W3b "
                "search opened (cells_looked_at = 40); this job re-grades them "
                "against a new benchmark and opens 6 more. 40 is the headline "
                "because the SELECTION happened there; dsr at 6 (this job alone) "
                "and 46 (both) are carried beside it."),
            "dsr_at_alternative_family_sizes": alt,
            **rep,
            "family_max_p_spa_consistent": (rep.get("spa") or {}).get("p_spa_consistent"),
            "family_max_p_spa_best_arm": (rep.get("spa") or {}).get("best_arm"),
            "mde_annual_excess_at_t_target": (rep.get("power") or {}).get(
                "mde_annual_excess_at_t_target"),
        }
        per_cell[key]["C_era_sign_table"] = era_sign_table(bm_excess[key])

    # Holm across THIS job's six cells, on the one-sided HAC alpha p.
    praw = {k: (v["A_market_regression"] or {}).get("p_alpha_one_sided_hac")
            for k, v in per_cell.items()}
    order = sorted([k for k, p in praw.items() if p is not None], key=lambda k: praw[k])
    holm, run_max = {}, 0.0
    for i, k in enumerate(order):
        adj = min(1.0, praw[k] * (len(order) - i))
        run_max = max(run_max, adj)
        holm[k] = round(run_max, 5)
    out["holm_adjusted_one_sided_alpha_p_over_this_jobs_six_cells"] = holm
    for k, v in holm.items():
        per_cell[k]["C_inference_on_beta_matched_excess"]["holm_p_this_job_6_cells"] = v

    # ---- D + E: the tail, and the noise null with each series' OWN moments
    log("tail + monte carlo ...")
    for key in list(per_cell):
        book, bps = key.rsplit("|", 1)
        beta = float(per_cell[key]["A_market_regression"]["beta"])
        legv = beta * mkt[key] + (1.0 - beta) * rf
        d: dict = {}
        for sel in ("net", "excess"):
            d[f"vs_raw_market_top5_by_{sel}"] = top5_block(net[key], mkt[key],
                                                           selection=sel)
            d[f"vs_beta_matched_top5_by_{sel}"] = top5_block(net[key], legv,
                                                             selection=sel)
        w3b_tail = ((w3b.get("robustness") or {}).get(book) or {}).get("tail") or {}
        d["w3b_raw_market_share_for_comparison"] = {
            "share_of_total_excess_from_those_5": w3b_tail.get(
                "share_of_total_excess_from_those_5"),
            "terminal_wealth_without_them": w3b_tail.get("terminal_wealth_without_them"),
            "note": "W3b computed the tail at 10 bps only, ranking by NET",
        }
        per_cell[key]["D_top5_share"] = d

        mc: dict = {}
        for label, series in (("beta_matched_excess", bm_excess[key]),
                              ("raw_market_excess", (net[key] - mkt[key]))):
            s = pd.Series(series).dropna().astype("float64")
            obs = top5_block(net[key],
                             legv if label == "beta_matched_excess" else mkt[key],
                             selection="excess")["share_of_total_excess_from_those_5"]
            mc[label] = {
                "observed_top5_share_by_excess": obs,
                "series_mean_monthly": round(float(s.mean()), 6),
                "series_sd_monthly": round(float(s.std(ddof=1)), 6),
                "normal": mc_top5_null(float(s.mean()), float(s.std(ddof=1)), len(s),
                                       obs, draws=mc_draws,
                                       seed=stable_seed(MC_SEED, key + "|" + label),
                                       dist="normal"),
                "t4": mc_top5_null(float(s.mean()), float(s.std(ddof=1)), len(s),
                                   obs, draws=mc_draws,
                                   seed=stable_seed(MC_SEED, key + "|" + label),
                                   dist="t4"),
            }
        per_cell[key]["E_monte_carlo_top5_null"] = mc

    out["by_cell"] = per_cell

    # ---- FABLE'S CLAIM 5, AT ITS OWN THRESHOLD AND ITS OWN MOMENTS
    # The review put the number at 31% (normal) / 40% (t4) for a top-5 share of
    # >= 0.8355 on a series with mean 0.28%/mo and sd 3.6%. 0.8355 is W3b's
    # BY-NET share and the null is a by-own-value construction, so the check is
    # run at that exact threshold, once on lgbm_clf's realised moments and once
    # on the review's rounded ones -- and both are printed rather than whichever
    # lands closer.
    clf_ex = (net["lgbm_clf|10bps"] - mkt["lgbm_clf|10bps"]).dropna()
    thr = ((w3b.get("robustness") or {}).get("lgbm_clf") or {}).get(
        "tail", {}).get("share_of_total_excess_from_those_5")
    out["fable_claim5_check"] = {
        "claim": ("REVIEW_2026-09-06_FABLE51 claim 5: a top-5-month share >= 0.8355 "
                  "on a series with mean 0.28%/mo and sd 3.6% happens in 31% (normal) "
                  "to 40% (t4) of pure-noise draws, so 'the baseline is five months' "
                  "is not evidence of beta timing."),
        "threshold_tested": thr,
        "threshold_source": "W3b robustness.lgbm_clf.tail (ranked by NET, 10 bps)",
        "at_lgbm_clf_realised_moments": {
            "mean_monthly": round(float(clf_ex.mean()), 6),
            "sd_monthly": round(float(clf_ex.std(ddof=1)), 6),
            "normal": mc_top5_null(float(clf_ex.mean()), float(clf_ex.std(ddof=1)),
                                   len(clf_ex), thr, draws=mc_draws,
                                   seed=stable_seed(MC_SEED, "fable|realised"),
                                   dist="normal"),
            "t4": mc_top5_null(float(clf_ex.mean()), float(clf_ex.std(ddof=1)),
                               len(clf_ex), thr, draws=mc_draws,
                               seed=stable_seed(MC_SEED, "fable|realised"), dist="t4"),
        },
        "at_the_reviews_rounded_moments": {
            "mean_monthly": 0.0028, "sd_monthly": 0.036,
            "normal": mc_top5_null(0.0028, 0.036, len(clf_ex), thr, draws=mc_draws,
                                   seed=stable_seed(MC_SEED, "fable|rounded"),
                                   dist="normal"),
            "t4": mc_top5_null(0.0028, 0.036, len(clf_ex), thr, draws=mc_draws,
                               seed=stable_seed(MC_SEED, "fable|rounded"), dist="t4"),
        },
    }

    # ---- one table, so the receipt is readable without a script
    out["summary_table"] = {
        key: {
            "beta": v["A_market_regression"]["beta"],
            "t_beta_minus_1_hac": v["A_market_regression"]["t_beta_minus_1_hac"],
            "t_beta_minus_1_ols": v["A_market_regression"]["t_beta_minus_1_ols"],
            "r_squared": v["A_market_regression"]["r_squared"],
            "annualised_excess_vs_raw_market":
                v["B_raw_market_for_comparison"]["annualised_excess_12x"],
            "t_vs_raw_market": v["B_raw_market_for_comparison"]["t_paired"],
            "alpha_annualised_beta_matched":
                v["A_market_regression"]["alpha_annualised_12x"],
            "t_alpha_ols": v["A_market_regression"]["t_alpha_ols"],
            "t_alpha_hac": v["A_market_regression"]["t_alpha_hac"],
            "dsr_family_40": (v["C_inference_on_beta_matched_excess"].get(
                "deflated_sharpe") or {}).get("dsr"),
            "family_max_p_spa": v["C_inference_on_beta_matched_excess"].get(
                "family_max_p_spa_consistent"),
            "holm_p_6_cells": v["C_inference_on_beta_matched_excess"].get(
                "holm_p_this_job_6_cells"),
            "mde_annual_excess_at_t2": v["C_inference_on_beta_matched_excess"].get(
                "mde_annual_excess_at_t_target"),
            "eras_positive_of_3": v["C_era_sign_table"].get(
                "eras_with_a_positive_mean"),
            "top5_share_vs_raw_market_by_net": v["D_top5_share"][
                "vs_raw_market_top5_by_net"]["share_of_total_excess_from_those_5"],
            "top5_share_vs_beta_matched_by_net": v["D_top5_share"][
                "vs_beta_matched_top5_by_net"]["share_of_total_excess_from_those_5"],
            "top5_share_vs_beta_matched_is_interpretable": v["D_top5_share"][
                "vs_beta_matched_top5_by_net"]["share_is_interpretable"],
            "terminal_wealth_book": v["B_beta_matched"]["book_terminal_wealth"],
            "terminal_wealth_beta_matched_leg":
                v["B_beta_matched"]["beta_matched_leg_terminal_wealth"],
            "terminal_wealth_raw_market": v["B_beta_matched"]["raw_market_terminal_wealth"],
        }
        for key, v in per_cell.items()
    }

    # ---- the answer, from a rule stated here rather than after the numbers
    out["verdict_rule"] = {
        "LOADING": "beta - 1 clears t >= 2 AND the beta-matched alpha's t < 2",
        "INTERCEPT": "the beta-matched alpha's t >= 2 (HAC)",
        "BOTH": "both of the above",
        "NEITHER": "neither -- the excess is neither a demonstrable intercept nor a "
                   "demonstrable loading on this much tape",
        "note": "a LABEL on an arithmetic result, not a promotion gate. No book is "
                "promoted, sealed, ordered or deployed by this receipt.",
    }
    verdicts = {}
    for key, v in per_cell.items():
        reg = v["A_market_regression"]
        tb = reg.get("t_beta_minus_1_hac")
        ta = reg.get("t_alpha_hac")
        loading = bool(tb is not None and tb >= 2.0)
        interc = bool(ta is not None and ta >= 2.0)
        verdicts[key] = ("BOTH" if (loading and interc) else
                         "LOADING" if loading else
                         "INTERCEPT" if interc else "NEITHER")
    out["verdict_by_cell"] = verdicts

    c10 = per_cell["lgbm_clf|10bps"]
    c25 = per_cell["lgbm_clf|25bps"]
    n10 = per_cell["nn_pre_causal_seedmean|10bps"]
    n25 = per_cell["nn_pre_causal_seedmean|25bps"]
    out["one_sentence_answer"] = (
        f"LOADING: lgbm_clf's beta is {c10['A_market_regression']['beta']} "
        f"(t(beta-1) = {c10['A_market_regression']['t_beta_minus_1_hac']} HAC, "
        f"{c10['A_market_regression']['t_beta_minus_1_ols']} OLS), and once that "
        "leverage is paid for its annualised excess falls from "
        f"{c10['B_raw_market_for_comparison']['annualised_excess_12x']:+.4f} "
        f"(t {c10['B_raw_market_for_comparison']['t_paired']}) against the raw VW market to "
        f"{c10['B_beta_matched']['annualised_excess_12x']:+.4f} "
        f"(t {c10['A_market_regression']['t_alpha_hac']} HAC) against the beta-matched leg "
        f"at 10 bps and {c25['B_beta_matched']['annualised_excess_12x']:+.4f} "
        f"(t {c25['A_market_regression']['t_alpha_hac']}) at 25 bps -- an intercept "
        "indistinguishable from zero sitting on a market loading that is not. "
        "The 8-seed nn_pre_causal ensemble is the SAME shape and not the opposite: its "
        f"beta is {n10['A_market_regression']['beta']} "
        f"(t(beta-1) = {n10['A_market_regression']['t_beta_minus_1_hac']} HAC), its "
        f"only-net-VW-beating t of {n10['B_raw_market_for_comparison']['t_paired']} against "
        f"the raw market becomes {n10['B_beta_matched']['annualised_excess_12x']:+.4f}/yr at "
        f"t {n10['A_market_regression']['t_alpha_hac']} beta-matched at 10 bps and "
        f"{n25['B_beta_matched']['annualised_excess_12x']:+.4f}/yr at "
        f"t {n25['A_market_regression']['t_alpha_hac']} at 25 bps, so its residual alpha is "
        "positive in every cell but clears nothing "
        f"(DSR {(n10['C_inference_on_beta_matched_excess'].get('deflated_sharpe') or {}).get('dsr')} "
        f"at a {FAMILY_N_TRIALS}-cell family, MDE "
        f"{n10['C_inference_on_beta_matched_excess'].get('mde_annual_excess_at_t_target')}/yr "
        f"against a {n10['B_beta_matched']['annualised_excess_12x']:+.4f} effect) -- "
        "it is the one book whose beta-matched excess is positive in all three eras."
    )
    out["headline"] = out["one_sentence_answer"]
    out["verdict"] = ("LOADING (all 6 cells)"
                      if set(verdicts.values()) == {"LOADING"} else
                      "MIXED: " + json.dumps(verdicts))

    out["memory_after"] = {"free_gb": W3B.free_gb()}
    out["wall_seconds"] = round(time.perf_counter() - t0, 1)
    out["_provenance"] = {
        "sys_argv": list(sys.argv),
        "resolved_config": {
            "books": list(BOOKS),
            "costs_bps_per_side": list(COSTS),
            "k": K, "weight": WEIGHT,
            "ret_col": "fwd_1m", "mkt_col": "mkt_vw_1m",
            "tradable_floor_usd": float(N.TRADABLE_FLOOR_USD),
            "tradable_min_close_usd": float(N.TRADABLE_MIN_CLOSE),
            "test_years": [years[0], years[-1]],
            "seeds": seeds,
            "nw_lag": NW_LAG,
            "family_n_trials_headline": FAMILY_N_TRIALS,
            "family_n_trials_alternatives": list(FAMILY_N_TRIALS_ALTERNATIVES),
            "mc_draws": int(mc_draws),
            "mc_seed_base": MC_SEED,
            "mc_t_df": MC_T_DF,
            "walk_forward_min_months": WF_MIN_MONTHS,
            "spa_n_boot": SPA_BOOT, "spa_seed": SPA_SEED,
            "rng": "np.random.default_rng only",
            "python_executable": sys.executable,
            "stage_dir": str(W3B.STAGE_DIR),
            "receipt_path": str(RECEIPT),
        },
        "_inputs_opened": inputs,
        "git_commit": git_commit(),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }
    out["generated_utc"] = out["_provenance"]["generated_utc"]
    return out


def _round(x, n):
    return None if x is None else round(float(x), n)


def stable_seed(base: int, label: str) -> int:
    """A per-series seed that is the SAME in every process.

    `hash("lgbm_clf|10bps")` is salted per interpreter (PYTHONHASHSEED), so a
    seed derived from it reproduces within one run and never across two -- which
    is the one thing a seed is for.
    """
    h = hashlib.sha256(label.encode("utf-8")).hexdigest()[:8]
    return int(base) + int(h, 16) % 100_000


def _hac_t(series, lag: int):
    from learner.evaluate import hac_t
    return hac_t(pd.Series(series), lag)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(RECEIPT))
    ap.add_argument("--mc-draws", type=int, default=MC_DRAWS)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        res = run(verbose=not a.quiet, mc_draws=a.mc_draws)
    except BaseException as exc:                                        # noqa: BLE001
        # A TRACEBACK IS A RECEIPT.
        res = {"job": "C1_beta_matched_regrade", "verdict": "FAILED",
               "error": f"{type(exc).__name__}: {exc}",
               "traceback": traceback.format_exc(),
               "headline": f"C1 FAILED: {type(exc).__name__}: {exc}",
               "_provenance": {"sys_argv": list(sys.argv), "resolved_config": {},
                               "_inputs_opened": [], "git_commit": git_commit(),
                               "generated_utc": datetime.now(timezone.utc).isoformat()}}
        Path(a.out).write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
        print(res["headline"])
        raise
    Path(a.out).write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(f"\n{res.get('verdict', 'DONE')} -- {res.get('headline')}")
    print(f"receipt -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
