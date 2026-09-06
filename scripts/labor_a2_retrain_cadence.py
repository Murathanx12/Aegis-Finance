"""A2 -- HOW OFTEN SHOULD THE CHAMPION BE REFITTED? MONTHLY / QUARTERLY / ANNUAL / ONCE.

THE QUESTION
============
`lgbm_clf` is refitted once a year, and nobody in this repo has ever measured
whether that is the right cadence or simply the one `dataset.walk_forward_splits`
happened to implement. Two failure modes sit on either side of the answer:

  * refit too rarely and the model is stale -- its daily shadow is REFUSED today
    on exactly that ground (sealed schema `fd48dbc7`, current `7f01cbe4`);
  * refit too often and every refit is a fresh draw from a noisy objective, the
    book churns for reasons that have nothing to do with the data, and the extra
    turnover is paid at 10 or 25 bps a side.

So: **is the model's information static?** If a model fitted ONCE in 2004 and
never touched again earns what a model refitted every month earns, then the
refit is ceremony, the cadence question is closed, and the engineering budget
belongs elsewhere. If it does not, the gap is the value of freshness and it can
be compared against the cost of the churn it causes.

WHAT IS HELD FIXED
==================
Everything except the refit boundary. Same pipeline (`models.fit_predict_proba`,
the classifier head that IS the champion), same 50 features, same floored panel
($3m/day and >= $5, applied to the TRAINING universe), same expanding-window
train rule -- a row is admissible for training only once its one-month target has
MATURED before the refit cutoff -- same top-50 value-weighted book, same two cost
rates, same grader.

THE REPRODUCTION GATE
=====================
The `annual` cadence is the incumbent, and it must reproduce the `lgbm_clf`
column in W3b's stage parquet. That is checked before any cadence is compared,
and the answer is reported as a number (max absolute deviation and correlation)
rather than a boolean, because a re-derivation that lands *close* to its parent
is a different finding from one that lands *on* it.

THE RULER
=========
PRIMARY is after-cost TERMINAL WEALTH and the BETA-MATCHED excess, at 10 AND 25
bps. The raw-market excess is SECONDARY throughout (C1: the incumbents' excess
is a loading, not an intercept). DSR is quoted over the 4-cell cadence family as
the mandate names, with the 8-cell (cadence x cost) count carried beside it.
Three-era table on every cell.

$0 LLM spend. Zero network calls. This job DOES fit models -- that is the
experiment -- and it fits them ONE AT A TIME with a memory gate in front.

    python -m scripts.labor_a2_retrain_cadence
    python -m scripts.labor_a2_retrain_cadence --cadences annual frozen_once
"""

from __future__ import annotations

import argparse
import gc
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
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.labor_a1_shadow_grader import (            # noqa: E402  our own lane's
    _month_windows, _window_leg, note_input, ols_market_model, _INPUTS)

OUT_DIR = REPO / "backend" / "data" / "optimus" / "labor_day_lab_2026-09-07"
RECEIPT = OUT_DIR / "A2_retrain_cadence_run01.json"

FIRST_TEST_YEAR, LAST_TEST_YEAR = 2004, 2024
COSTS: tuple[float, ...] = (10.0, 25.0)
K, WEIGHT = 50, "vw"
HORIZON = 1
NW_LAG = 4

#: A cadence is a rule for WHERE the refit boundaries fall. Nothing else differs.
CADENCES: tuple[str, ...] = ("monthly", "quarterly", "annual", "frozen_once")

#: The same floor `dataset.walk_forward_splits` applies. A fold whose train side
#: is shorter than this is skipped rather than fitted on a stub.
MIN_TRAIN_MONTHS = 24

#: Refuse to start a fit below this. The machine is shared with three other
#: agents today and an OOM in the middle of a 252-fit sweep loses the sweep.
MIN_FREE_GB = 4.0

#: The mandate names a 4-cell family (the four cadences). The 8-cell count
#: (cadence x cost rate) is carried beside it -- a reader may pick either cost
#: rate, so both counts are declared and neither is the convenient one alone.
FAMILY_CADENCES = 4
FAMILY_CADENCES_X_COSTS = 8


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO),
                              capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception as exc:                                            # noqa: BLE001
        return f"UNKNOWN ({type(exc).__name__})"


def _r(v, nd: int = 5):
    try:
        f = float(v)
        return round(f, nd) if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _ncdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _t(series) -> float | None:
    s = pd.Series(series).dropna().astype("float64")
    if len(s) < 3 or s.std(ddof=1) <= 0:
        return None
    return float(s.mean() / (s.std(ddof=1) / np.sqrt(len(s))))


# ------------------------------------------------------------ the refit clock

def cutoffs(cadence: str) -> list[pd.Timestamp]:
    """The refit boundaries. THE ONLY THING THAT DIFFERS BETWEEN CADENCES."""
    lo, hi = FIRST_TEST_YEAR, LAST_TEST_YEAR
    if cadence == "annual":
        return [pd.Timestamp(f"{y}-01-01") for y in range(lo, hi + 1)]
    if cadence == "quarterly":
        return [pd.Timestamp(f"{y}-{m:02d}-01")
                for y in range(lo, hi + 1) for m in (1, 4, 7, 10)]
    if cadence == "monthly":
        return [pd.Timestamp(f"{y}-{m:02d}-01")
                for y in range(lo, hi + 1) for m in range(1, 13)]
    if cadence == "frozen_once":
        return [pd.Timestamp(f"{lo}-01-01")]
    raise ValueError(f"unknown cadence {cadence!r}")


def folds(df: pd.DataFrame, cadence: str):
    """(cutoff, train_index, test_index) per refit boundary.

    The train rule is `dataset.walk_forward_splits`' rule, generalised from a
    calendar year to an arbitrary cutoff: a row is admissible only once its
    one-month target has MATURED strictly before the cutoff. A row dated
    2015-11 with a 1-month target does not resolve until 2015-12 and would hand
    a 2015-12 test window part of its own future.

    `frozen_once` has ONE fold whose test window runs to the end of the sample:
    that is what "fit it and never touch it again" means, and giving it later
    boundaries would make it a slow refit rather than a frozen model.
    """
    mat, y_col = f"mat_date_{HORIZON}m", f"excess_vw_{HORIZON}m"
    cs = cutoffs(cadence)
    end = pd.Timestamp(f"{LAST_TEST_YEAR + 1}-01-01")
    for i, c in enumerate(cs):
        nxt = cs[i + 1] if i + 1 < len(cs) else end
        tr = df.index[(df[mat].notna()) & (df[mat] < c) & (df[y_col].notna())]
        te = df.index[(df["entry_date"] >= c) & (df["entry_date"] < nxt)
                      & (df[y_col].notna())]
        if len(tr) == 0 or len(te) == 0:
            continue
        if df.loc[tr, "month"].nunique() < MIN_TRAIN_MONTHS:
            continue
        yield c, tr, te


def free_gb() -> float | None:
    from scripts import w3_neural_floored as W3B
    return W3B.free_gb()


def run_cadence(df: pd.DataFrame, cadence: str, feature_cols: list[str],
                log) -> tuple[pd.Series, dict]:
    """Walk the refit clock, fitting ONE model at a time. Returns (preds, meta)."""
    from learner import models as M
    out = pd.Series(np.nan, index=df.index, dtype="float64")
    notes, t0 = [], time.perf_counter()
    for c, tr, te in folds(df, cadence):
        g = free_gb()
        if g is not None and g < MIN_FREE_GB:
            notes.append({"cutoff": str(c.date()), "SKIPPED": True,
                          "why": f"free memory {g} GB below the {MIN_FREE_GB} GB floor"})
            continue
        t1 = time.perf_counter()
        p, meta = M.fit_predict_proba(df.loc[tr], df.loc[te], feature_cols, HORIZON)
        out.loc[te] = p
        notes.append({"cutoff": str(c.date()), "n_train": int(len(tr)),
                      "n_test": int(len(te)),
                      "best_iteration": meta.get("best_iteration"),
                      "seconds": round(time.perf_counter() - t1, 2)})
        if len(notes) % 24 == 0:
            log(f"      {cadence}: {len(notes)} fits, "
                f"{round(time.perf_counter() - t0, 1)}s")
    skipped = [n for n in notes if n.get("SKIPPED")]
    return out, {
        "cadence": cadence,
        "n_refits": len([n for n in notes if not n.get("SKIPPED")]),
        "n_refits_skipped_for_memory": len(skipped),
        "skipped": skipped,
        "rows_predicted": int(out.notna().sum()),
        "wall_seconds": round(time.perf_counter() - t0, 1),
        "first_cutoff": notes[0]["cutoff"] if notes else None,
        "last_cutoff": notes[-1]["cutoff"] if notes else None,
        "mean_seconds_per_fit": _r(float(np.mean([n["seconds"] for n in notes
                                                  if "seconds" in n])), 2) if notes else None,
        "folds": notes if cadence in ("annual", "frozen_once") else notes[:6] + notes[-6:],
        "folds_note": ("every fold for annual/frozen_once; first and last six only for "
                       "the monthly and quarterly sweeps, which have 252 and 84"),
    }


# ------------------------------------------------------------------ the grade

def grade(df: pd.DataFrame, col: str, bps: float, rf: pd.Series) -> tuple[dict, pd.Series]:
    from learner import evaluate as E
    from learner import neural_long as N
    from scripts.weekend_lab_jobs import era_sign_table
    bk = E.book(df, col, k=K, weight=WEIGHT, cost_bps=bps,
                ret_col="fwd_1m", mkt_col="mkt_vw_1m",
                tradable_floor=N.TRADABLE_FLOOR_USD, return_series=True)
    ser = bk.pop("_series", None)
    if ser is None:
        return {"verdict": "CANNOT DETERMINE", "why": "no series"}, pd.Series(dtype=float)
    net = ser["net"].astype("float64")
    mkt = ser["market"].reindex(net.index).astype("float64")
    rfs = rf.reindex(net.index).fillna(0.0)
    reg = ols_market_model(net - rfs, mkt - rfs, lag=NW_LAG)
    beta = reg.get("beta")
    if beta is None:
        return {"verdict": "CANNOT DETERMINE", "regression": reg}, pd.Series(dtype=float)
    bm = float(beta) * mkt + (1.0 - float(beta)) * rfs
    ex_bm = (net - bm).dropna()
    ex_raw = (net - mkt).dropna()
    tb = _t(ex_bm)
    blk = {k: v for k, v in bk.items() if not k.startswith("_")}
    blk["PRIMARY_after_cost_terminal_wealth"] = bk.get("terminal_wealth_net")
    blk["PRIMARY_beta_matched"] = {
        "beta": _r(beta, 4),
        "t_beta_minus_1_hac": reg.get("t_beta_minus_1_hac"),
        "annualised_pct": _r(float(ex_bm.mean()) * 12 * 100, 3),
        "t_paired": _r(tb, 3),
        "p_one_sided": _r(1.0 - _ncdf(float(tb))) if tb is not None else None,
    }
    blk["SECONDARY_raw_market"] = {
        "annualised_pct": _r(float(ex_raw.mean()) * 12 * 100, 3),
        "t_paired": _r(_t(ex_raw), 3),
    }
    blk["era_table_on_the_beta_matched_excess"] = era_sign_table(ex_bm)
    return blk, ex_bm


# ------------------------------------------------------------------- the run

def run(*, cadences: tuple[str, ...] = CADENCES, verbose: bool = True) -> dict:
    from learner import benchmark as BM
    from learner import dataset as DS
    from learner import inference
    from learner import long_panel as LP
    from learner import neural_long as N
    from scripts import w3_neural_floored as W3B

    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    t0 = time.perf_counter()
    out: dict = {
        "job": "A2_retrain_cadence",
        "lane": "A",
        "question": ("does refitting the champion more often buy anything after "
                     "costs, or is the model's information static? Monthly vs "
                     "quarterly vs annual vs frozen-once, walk-forward 2004-2024 on "
                     "the floored long panel."),
        "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0, "llm_calls": 0, "network_calls": 0,
        "pipeline": ("learner.models.fit_predict_proba -- the classifier head that IS "
                     "the champion. Identical features, panel, floor, book and grader "
                     "across all four cadences; ONLY the refit boundary differs."),
        "memory_free_gb_before": W3B.free_gb(),
        "memory_floor_gb": MIN_FREE_GB,
    }
    if not LP.LONG_TABLE.exists():
        out["status"] = "SKIPPED"
        out["reasons"] = [f"{LP.LONG_TABLE} is absent"]
        out["headline"] = "SKIPPED: the long panel is absent"
        return out
    g = W3B.free_gb()
    if g is not None and g < MIN_FREE_GB:
        out["status"] = "REFUSED"
        out["reasons"] = [f"free memory {g} GB is below the {MIN_FREE_GB} GB floor. "
                          f"This job fits up to 252 models; starting it here would OOM "
                          f"mid-sweep and lose the sweep."]
        out["headline"] = f"REFUSED: {g} GB free, floor {MIN_FREE_GB} GB"
        return out

    log("  loading the floored universe ...")
    df, uni, fp = W3B.load_universe(verbose=False)
    note_input(LP.LONG_TABLE)
    out["universe_fingerprint_sha256"] = fp
    out["training_universe"] = {k: uni[k] for k in
                                ("dollar_volume_floor_usd_per_day", "min_close_usd",
                                 "rows_before", "rows_after", "share_kept",
                                 "months_after")}
    feature_cols = DS.feature_columns()
    out["n_features"] = len(feature_cols) + 1
    out["feature_note"] = ("dataset.feature_columns() (49) plus prior_1m, appended by "
                           "fit_predict_proba -- exactly what run_lgbm_clf passes")

    # ---- the refit clocks, declared before anything is fitted
    out["refit_clocks"] = {c: {"n_boundaries": len(cutoffs(c)),
                               "first": str(cutoffs(c)[0].date()),
                               "last": str(cutoffs(c)[-1].date())}
                           for c in CADENCES}

    # ---- the risk-free leg
    months_all = pd.Index(sorted(df["month"].dropna().unique()))
    try:
        rf_d = BM.cash().returns.dropna().astype("float64")
        rf, rf_note = _window_leg(rf_d, _month_windows(df), months_all)
        rf_note["source"] = "learner.benchmark.cash() -- pinned FF daily RF, OFFLINE"
    except Exception as exc:                                            # noqa: BLE001
        rf = pd.Series(0.0, index=months_all)
        rf_note = {"available": False, "why": f"{type(exc).__name__}: {exc}"}
    out["risk_free_leg"] = rf_note

    # ---- fit, ONE CADENCE AT A TIME
    fits: dict = {}
    for cad in cadences:
        log(f"  cadence {cad} ...")
        preds, meta = run_cadence(df, cad, feature_cols, log)
        df[f"cad__{cad}"] = preds
        fits[cad] = meta
        log(f"    {cad}: {meta['n_refits']} refits, {meta['wall_seconds']}s, "
            f"{meta['rows_predicted']:,} rows predicted")
        gc.collect()
    out["fits"] = fits
    out["memory_free_gb_after_fits"] = W3B.free_gb()

    # ---- THE REPRODUCTION GATE: annual must be the incumbent
    if "annual" in cadences:
        out["reproduction_gate"] = _reproduction_gate(df, fp, W3B, N)

    # ---- grade every cadence at every cost rate
    log("  grading ...")
    cells, fam = {}, {}
    for cad in cadences:
        for bps in COSTS:
            key = f"{cad}|{int(bps)}bps"
            blk, ex = grade(df, f"cad__{cad}", bps, rf)
            blk["n_refits"] = fits[cad]["n_refits"]
            cells[key] = blk
            if len(ex):
                fam[key] = ex
    out["cells"] = cells

    # ---- the comparison the job exists for
    out["ANSWER"] = _answer(cells, fits)

    # ---- inference over the cadence family
    ps = {k: (v.get("PRIMARY_beta_matched") or {}).get("p_one_sided") for k, v in cells.items()}
    ordered = sorted([(k, float(v)) for k, v in ps.items() if v is not None],
                     key=lambda kv: kv[1])
    n = len(ordered)
    holm, run_max = {}, 0.0
    for i, (k, p) in enumerate(ordered):
        adj = min(1.0, max(run_max, (n - i) * p))
        run_max = adj
        holm[k] = _r(adj)
    out["family"] = {
        "size_cadences": FAMILY_CADENCES,
        "size_cadences_x_costs": FAMILY_CADENCES_X_COSTS,
        "size_actually_graded": n,
        "family_min_p_one_sided": _r(ordered[0][1]) if ordered else None,
        "family_max_p_one_sided": _r(ordered[-1][1]) if ordered else None,
        "holm_adjusted": holm,
    }
    dsr: dict = {}
    for key, ex in fam.items():
        aligned = {k: v for k, v in fam.items()
                   if k.endswith(key.split("|")[1]) and len(v) == len(ex)}
        rep = inference.full_report(ex.to_numpy(), family=aligned,
                                    n_trials=FAMILY_CADENCES, seed=20260907)
        dsr[key] = {
            "dsr_over_the_4_cell_cadence_family": (rep.get("deflated_sharpe") or {}).get("dsr"),
            "dsr_over_8_cells": (inference.deflated_sharpe(
                ex.to_numpy(), n_trials=FAMILY_CADENCES_X_COSTS) or {}).get("dsr"),
            "mde_annual_excess_at_t_2": (rep.get("power") or {}).get(
                "mde_annual_excess_at_t_target"),
            "power_verdict": (rep.get("power") or {}).get("verdict"),
            "pbo_within_the_cost_rate": (rep.get("pbo") or {}).get("pbo"),
        }
    out["inference_by_cell"] = dsr

    out["memory_free_gb_after"] = W3B.free_gb()
    out["headline"] = _headline(out)
    out["wall_seconds"] = round(time.perf_counter() - t0, 1)
    del df
    gc.collect()
    return out


def _reproduction_gate(df: pd.DataFrame, fp: str, W3B, N) -> dict:
    """The `annual` cadence IS the incumbent. Does it land on it, or near it?

    Reported as numbers, never a boolean: a re-derivation that lands CLOSE to
    its parent is a different finding from one that lands ON it, and a bool
    would erase the difference.
    """
    out: dict = {"claim": ("the annual cadence reproduces the lgbm_clf column in "
                           "W3b's stage parquet -- same pipeline, same folds")}
    years = list(range(N.FIRST_TEST_YEAR, N.LAST_TEST_YEAR + 1))
    try:
        block, meta = W3B._read_stage("incumbents", fp, W3B._scope(years, []))
    except SystemExit as exc:
        return {**out, "verdict": "CANNOT DETERMINE", "why": str(exc)}
    note_input(W3B._stage_path("incumbents"))
    ref = block["lgbm_clf"].reindex(df.index).astype("float64")
    mine = df["cad__annual"].astype("float64")
    both = ref.notna() & mine.notna()
    if not both.any():
        return {**out, "verdict": "CANNOT DETERMINE", "why": "no overlapping rows"}
    d = (mine[both] - ref[both]).abs()
    return {
        **out,
        "rows_compared": int(both.sum()),
        "rows_only_in_the_stage_file": int((ref.notna() & ~mine.notna()).sum()),
        "rows_only_in_this_job": int((mine.notna() & ~ref.notna()).sum()),
        "max_abs_deviation": _r(float(d.max()), 8),
        "mean_abs_deviation": _r(float(d.mean()), 8),
        "pearson_correlation": _r(float(mine[both].corr(ref[both])), 8),
        "spearman_correlation": _r(float(mine[both].corr(ref[both], method="spearman")), 8),
        # THE STAGE PARQUET STORES float32 (`_write_stage` casts). A float64
        # re-derivation therefore cannot land at 0.0 against it and must not be
        # graded as if it could: ~1e-7 is the round-trip precision of float32
        # near 0.5, so a deviation at that scale is a STORAGE artefact and a
        # deviation above it is a real difference in the fit.
        "storage_note": ("W3b's stage parquet stores predictions as float32; the "
                         "round-trip precision near a probability of 0.5 is ~6e-8, so "
                         "a max deviation at that scale is the CAST, not the model."),
        "verdict": ("BIT-EXACT" if float(d.max()) == 0.0 else
                    "EXACT TO FLOAT32 STORAGE PRECISION" if float(d.max()) < 1e-6 else
                    "CLOSE BUT NOT EXACT" if float(d.max()) < 1e-3 else
                    "DIFFERENT"),
        "why_it_matters": ("if annual does NOT reproduce the incumbent, the four "
                           "cadences are still internally comparable (one pipeline, "
                           "four clocks) but no row of this table can be quoted as a "
                           "statement about the book the repo actually trades."),
    }


def _answer(cells: dict, fits: dict) -> dict:
    """The one comparison: does more refitting buy anything after costs?"""
    rows = {}
    for key, v in cells.items():
        if "PRIMARY_beta_matched" not in v:
            continue
        cad, bps = key.split("|")
        rows[key] = {
            "cadence": cad,
            "n_refits": fits.get(cad, {}).get("n_refits"),
            "after_cost_terminal_wealth": v.get("terminal_wealth_net"),
            "market_terminal_wealth_same_months": v.get("terminal_wealth_market_same_months"),
            "beta_matched_annualised_pct": v["PRIMARY_beta_matched"]["annualised_pct"],
            "t": v["PRIMARY_beta_matched"]["t_paired"],
            "raw_market_annualised_pct": v["SECONDARY_raw_market"]["annualised_pct"],
            "mean_turnover": v.get("mean_turnover"),
            "months": v.get("months"),
            "eras_positive": (v.get("era_table_on_the_beta_matched_excess") or {}).get(
                "eras_with_a_positive_mean"),
        }
    verdicts = {}
    for bps in COSTS:
        sub = {k: v for k, v in rows.items() if k.endswith(f"|{int(bps)}bps")}
        if not sub:
            continue
        frozen = sub.get(f"frozen_once|{int(bps)}bps")
        monthly = sub.get(f"monthly|{int(bps)}bps")
        annual = sub.get(f"annual|{int(bps)}bps")
        best = max(sub, key=lambda k: (sub[k]["after_cost_terminal_wealth"] or -9e9))
        blk = {
            "best_cadence_by_after_cost_terminal_wealth": best,
            "terminal_wealth_by_cadence": {
                v["cadence"]: v["after_cost_terminal_wealth"] for v in sub.values()},
            "beta_matched_excess_by_cadence": {
                v["cadence"]: v["beta_matched_annualised_pct"] for v in sub.values()},
            "turnover_by_cadence": {v["cadence"]: v["mean_turnover"] for v in sub.values()},
        }
        if frozen and monthly:
            blk["monthly_minus_frozen_terminal_wealth"] = _r(
                (monthly["after_cost_terminal_wealth"] or 0)
                - (frozen["after_cost_terminal_wealth"] or 0), 3)
            blk["monthly_minus_frozen_beta_matched_pp"] = _r(
                (monthly["beta_matched_annualised_pct"] or 0)
                - (frozen["beta_matched_annualised_pct"] or 0), 3)
            blk["refits_bought"] = (
                f"{monthly['n_refits']} refits against {frozen['n_refits']}")
        if frozen and annual:
            blk["annual_minus_frozen_beta_matched_pp"] = _r(
                (annual["beta_matched_annualised_pct"] or 0)
                - (frozen["beta_matched_annualised_pct"] or 0), 3)
        verdicts[f"{int(bps)}bps"] = blk
    return {
        "table": rows,
        "by_cost_rate": verdicts,
        "reading": ("the question is `monthly_minus_frozen_*`. A model fitted once in "
                    "2004 and never touched is the null; if it earns what the monthly "
                    "refit earns, the refit is ceremony and the model's information is "
                    "STATIC. Note that all four cadences share one pipeline, so this "
                    "compares refit frequency, not model families."),
    }


def _headline(out: dict) -> str:
    a = (out.get("ANSWER") or {}).get("by_cost_rate") or {}
    rg = (out.get("reproduction_gate") or {}).get("verdict")
    bits = []
    for bps in ("10bps", "25bps"):
        b = a.get(bps)
        if not b:
            continue
        bits.append(f"{bps}: TW by cadence {b.get('terminal_wealth_by_cadence')}, "
                    f"monthly-minus-frozen {b.get('monthly_minus_frozen_beta_matched_pp')}pp "
                    f"beta-matched")
    return (f"reproduction gate: {rg}. " + " | ".join(bits)) if bits else \
        f"reproduction gate: {rg}. No graded cell."


def write(rec: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec["_provenance"] = {
        "sys_argv": list(sys.argv),
        "resolved_config": {
            "CADENCES": list(CADENCES), "COSTS": list(COSTS), "K": K, "WEIGHT": WEIGHT,
            "HORIZON": HORIZON, "FIRST_TEST_YEAR": FIRST_TEST_YEAR,
            "LAST_TEST_YEAR": LAST_TEST_YEAR, "MIN_TRAIN_MONTHS": MIN_TRAIN_MONTHS,
            "MIN_FREE_GB": MIN_FREE_GB, "NW_LAG": NW_LAG,
            "FAMILY_CADENCES": FAMILY_CADENCES, "receipt": str(RECEIPT),
        },
        "_inputs_opened": _INPUTS,
        "git_commit": git_commit(),
        "python": sys.version.split()[0],
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    rec["generated_utc"] = rec["_provenance"]["generated_utc"]
    RECEIPT.write_text(json.dumps(rec, indent=1, default=str),
                       encoding="utf-8", newline="\n")
    return RECEIPT


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cadences", nargs="*", default=list(CADENCES),
                    choices=list(CADENCES))
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    try:
        rec = run(cadences=tuple(a.cadences), verbose=not a.quiet)
    except Exception as exc:                                            # noqa: BLE001
        rec = {"job": "A2_retrain_cadence", "lane": "A", "status": "CRASHED",
               "llm_spend_usd": 0.0, "llm_calls": 0,
               "error": f"{type(exc).__name__}: {exc}",
               "traceback": traceback.format_exc(),
               "headline": f"CRASHED: {type(exc).__name__}: {exc}"}
    p = write(rec)
    print(f"\n{rec.get('headline')}\n-> {p}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
