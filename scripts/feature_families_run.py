"""THE FEATURE-FAMILY ABLATION. Does 13F ownership or analyst identity add
anything the price-and-consensus base model did not already have?

THE QUESTION, AND WHY IT IS AN ABLATION
=======================================
Three separate receipts say the standalone versions of these things are thin:
raw news is a mega-cap filter (T12: 7.7% of corpus news is a new dated fact,
Benzinga 390:1), holder identity is ~5bps per 1sd (t 2.24, under costs), and the
manager's own top-decile stake is ADVERSE (-1.21pp/252s, t -3.95). None of that
answers the question a model actually poses, which is INCREMENTAL: given a
learner that already sees price, consensus, revisions, coverage and the band
prior, does adding a family of ownership features move the OUT-OF-SAMPLE number?

So nothing here is graded on its own. Every family is graded on the DIFFERENCE
between two models that are identical except for that family, on the same rows,
the same months, the same costs, the same seeds.

WHAT IS COMPARED
================
    base                              `learner.dataset.feature_columns()` + the band prior
    base+analyst                      + analyst identity (bias-corrected consensus, ...)
    base+holder                       + 13F ownership
    base+analyst+holder               both
    base+analyst+holder+interaction   + the products

`base+holder` is NOT in the brief's ladder and is here anyway: a purely nested
ladder cannot say which of two families a joint gain came from, and a negative
has to be attributable to be worth recording.

THE STATISTICS, AND THEIR n
===========================
n is MONTHS, never name-months (CANON 58). The primary comparison is the PAIRED
monthly difference -- rank IC of the family model minus rank IC of the base
model, in the same month, on the same rows -- and its t across months. Comparing
two pooled ICs is one draw of a correlated pair, not a test.

At the 12-month horizon a monthly-formed book OVERLAPS. Two things are done
about that rather than one: (a) `n_effective_blocks = months / 12` is reported
beside the naive month count, and (b) terminal wealth is computed on the TWELVE
DISJOINT annual paths (formation months 0, 12, 24, ... then 1, 13, 25, ...) and
geometrically averaged, so the wealth number is a path something could have
held.

THE NULL, AND THE MISSINGNESS CONTROL
=====================================
Two things can manufacture a fake answer here and both are checked:

* a leak in the plumbing -- so the same pipeline is run once with the TRAINING
  target permuted WITHIN each month. Any surviving OOS IC is plumbing.
* missingness -- the ownership panel does not cover every row, and a family that
  is NaN on a third of the table is handicapped for a reason that is not about
  the mechanism. So the 1-month comparison is ALSO run on the COMPLETE-CASE
  subsample where every family is present on every row.

Costs are 10 bps per side on measured weight turnover, both sides, in every
book. `zero_cost_diagnostic` does not exist in this script.

Licence: PRODUCT_EXPERIMENT.

Run:
    python -m scripts.feature_families_run                # full ablation
    python -m scripts.feature_families_run --rebuild      # rebuild both panels
    python -m scripts.feature_families_run --quick        # 1m only, ridge only
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from learner import dataset as D          # noqa: E402  READ-ONLY
from learner import evaluate as E         # noqa: E402  READ-ONLY
from learner import features_ext as F     # noqa: E402
from learner import models as M           # noqa: E402  READ-ONLY

RECEIPT = (REPO / "backend" / "data" / "optimus" / "tracker_backtest"
           / "feature_ablation_20260903.json")

TEST_YEARS = tuple(range(2016, 2025))
HORIZONS = (1, 12)
KINDS = ("ridge", "lgbm")
ARM = "raw"
BOOK_K = 50
COST_BPS = E.COST_BPS_PER_SIDE      # 10.0 per side
MIN_NAMES_PER_MONTH = 20


# --------------------------------------------------------------- statistics

def _t_of(s: pd.Series) -> float | None:
    s = s.dropna()
    if len(s) < 3 or s.std(ddof=1) == 0:
        return None
    return float(s.mean() / (s.std(ddof=1) / np.sqrt(len(s))))


def monthly_ic(df: pd.DataFrame, pred: str, y: str) -> pd.Series:
    """Cross-sectional Spearman per month. The index is the month; the caller
    pairs two of these on that index rather than on a pooled number."""
    out = {}
    for m, chunk in df.groupby("month", sort=True):
        sub = chunk[[pred, y]].dropna()
        if len(sub) < MIN_NAMES_PER_MONTH or sub[pred].nunique() < 2:
            continue
        rho = stats.spearmanr(sub[pred], sub[y]).statistic
        if np.isfinite(rho):
            out[m] = float(rho)
    return pd.Series(out, dtype="float64").sort_index()


def paired_ic_delta(fam_ic: pd.Series, base_ic: pd.Series, horizon: int) -> dict:
    """The PRIMARY comparison. Paired by month, t across months."""
    j = pd.concat([fam_ic.rename("f"), base_ic.rename("b")], axis=1).dropna()
    if len(j) < 3:
        return {"months": int(len(j)), "note": "too few paired months"}
    d = j["f"] - j["b"]
    t = _t_of(d)
    return {
        "months": int(len(j)),
        # OVERLAP. A 12m target observed monthly gives months/12 independent
        # blocks, not `months`. Both are printed; neither is quietly assumed.
        "n_effective_blocks": round(len(j) / horizon, 1),
        "mean_ic_family": round(float(j["f"].mean()), 5),
        "mean_ic_base": round(float(j["b"].mean()), 5),
        "delta_mean_ic": round(float(d.mean()), 5),
        "delta_median_ic": round(float(d.median()), 5),
        "t_paired": round(t, 3) if t is not None else None,
        "t_paired_block_adjusted": (round(t / np.sqrt(horizon), 3)
                                    if t is not None and horizon > 1 else
                                    (round(t, 3) if t is not None else None)),
        "share_months_family_better": round(float((d > 0).mean()), 4),
    }


def book_for_horizon(df: pd.DataFrame, pred: str, horizon: int) -> dict:
    """Monthly-formed top-k value-weighted book, held for `horizon` months.

    For horizon 1 that is one continuous path. For horizon 12 the monthly
    formations OVERLAP, so terminal wealth is computed on each of the twelve
    DISJOINT annual paths and geometrically averaged -- a number a book could
    have held, rather than a compounding of overlapping windows.
    """
    kw = dict(k=BOOK_K, weight="vw", cost_bps=COST_BPS,
              ret_col=f"fwd_{horizon}m", mkt_col=f"mkt_vw_{horizon}m")
    if horizon == 1:
        return E.book(df, pred, **kw)
    months = sorted(df["month"].unique())
    idx = {m: i for i, m in enumerate(months)}
    paths, spreads = [], []
    for off in range(horizon):
        sel = df[df["month"].map(idx) % horizon == off]
        if sel.empty:
            continue
        r = E.book(sel, pred, **kw)
        if r.get("months", 0) >= 3:
            paths.append(r)
    if not paths:
        return {"months": 0, "note": "no disjoint path produced a book"}
    tw = np.array([p["terminal_wealth_net"] for p in paths], dtype="float64")
    twm = np.array([p["terminal_wealth_market_same_months"] for p in paths],
                   dtype="float64")
    spreads = np.array([p["mean_monthly_excess"] for p in paths], dtype="float64")
    geo = float(np.exp(np.mean(np.log(np.clip(tw, 1e-9, None)))))
    geom = float(np.exp(np.mean(np.log(np.clip(twm, 1e-9, None)))))
    return {
        "months": int(sum(p["months"] for p in paths)),
        "disjoint_paths": len(paths),
        "overlapping_formations": True,
        "terminal_wealth_net": round(geo, 4),
        "terminal_wealth_market_same_months": round(geom, 4),
        "terminal_wealth_net_per_path": [round(float(x), 4) for x in tw],
        "mean_period_excess": round(float(spreads.mean()), 5),
        "paths_beating_market": round(float((tw > twm).mean()), 4),
        "cost_bps_per_side": COST_BPS,
        "k": BOOK_K, "weight": "vw",
        "note": ("horizon 12 formations overlap; terminal wealth is the geometric "
                 "mean of the 12 DISJOINT annual paths, not a compounding of "
                 "overlapping windows."),
    }


# ------------------------------------------------------------- the ablation

def walk_forward_preds(df: pd.DataFrame, cols: list[str], kind: str, horizon: int,
                       shuffle: bool = False, verbose: bool = True) -> tuple[pd.Series, dict]:
    """OOS predictions for one (feature set, model, horizon). Every prediction
    was made by a model that saw only rows whose targets had already MATURED
    before its test year opened -- `D.walk_forward_splits` enforces that and is
    imported, not re-implemented."""
    pred = pd.Series(np.nan, index=df.index, dtype="float64")
    meta: dict = {}
    for year, tr, te in D.walk_forward_splits(df, TEST_YEARS, horizon):
        t0 = time.time()
        p, mt = M.fit_predict(kind, ARM, df.loc[tr], df.loc[te], cols, horizon,
                              shuffle_target=shuffle)
        pred.loc[te] = p
        meta[str(year)] = {"n_train": mt["n_train"],
                           "n_train_months": mt["n_train_months"],
                           "n_test": int(len(te)),
                           "n_features": mt["n_features"],
                           "secs": round(time.time() - t0, 1)}
        if verbose:
            print(f"      {year}: train {mt['n_train']:,} / test {len(te):,} "
                  f"({time.time() - t0:.1f}s)", flush=True)
    return pred, meta


def run_horizon(df: pd.DataFrame, horizon: int, kinds: tuple[str, ...],
                tag: str, verbose: bool = True) -> dict:
    y = f"excess_vw_{horizon}m"
    base_cols = D.feature_columns()
    out: dict = {"horizon_months": horizon, "target": y, "tag": tag,
                 "n_rows_with_target": int(df[y].notna().sum()),
                 "sets": {}, "base_absolute": {}}
    ics: dict[tuple[str, str], pd.Series] = {}

    for set_name, fams in F.ABLATION_SETS:
        cols = base_cols + F.columns_for(fams)
        out["sets"][set_name] = {"n_features": len(cols) + 1,   # + the prior column
                                 "added_features": F.columns_for(fams),
                                 "models": {}}
        for kind in kinds:
            if verbose:
                print(f"    [{tag} h={horizon}] {set_name} / {kind}", flush=True)
            pred, meta = walk_forward_preds(df, cols, kind, horizon, verbose=verbose)
            scored = df.assign(_pred=pred)
            scored = scored[scored["_pred"].notna() & scored[y].notna()]
            ic = monthly_ic(scored, "_pred", y)
            ics[(set_name, kind)] = ic
            row = {
                "fits": meta,
                "rank_ic": {"months": int(len(ic)),
                            "mean_ic": round(float(ic.mean()), 5) if len(ic) else None,
                            "t_stat": (round(_t_of(ic), 3)
                                       if _t_of(ic) is not None else None),
                            "share_months_positive": (round(float((ic > 0).mean()), 4)
                                                      if len(ic) else None)},
                "book": book_for_horizon(scored, "_pred", horizon),
                "top_minus_bottom": E.top_minus_bottom(scored, "_pred", y),
            }
            if set_name == "base":
                row["calibration"] = E.calibration_slope(
                    E.decile_table(scored, "_pred", y))
            out["sets"][set_name]["models"][kind] = row

    # ---- the incremental value of each family, paired against `base`
    for set_name, _f in F.ABLATION_SETS:
        if set_name == "base":
            continue
        for kind in kinds:
            b = ics.get(("base", kind))
            f = ics.get((set_name, kind))
            if b is None or f is None:
                continue
            d = paired_ic_delta(f, b, horizon)
            bb = out["sets"]["base"]["models"][kind]["book"]
            fb = out["sets"][set_name]["models"][kind]["book"]
            d["delta_terminal_wealth_net"] = (
                round(float(fb.get("terminal_wealth_net", np.nan)
                            - bb.get("terminal_wealth_net", np.nan)), 4)
                if fb.get("terminal_wealth_net") is not None
                and bb.get("terminal_wealth_net") is not None else None)
            d["terminal_wealth_net_family"] = fb.get("terminal_wealth_net")
            d["terminal_wealth_net_base"] = bb.get("terminal_wealth_net")
            d["terminal_wealth_market"] = bb.get("terminal_wealth_market_same_months")
            out["sets"][set_name]["models"][kind]["vs_base"] = d

    # ---- the strictly INCREMENTAL step, family by family up the ladder
    ladder = []
    order = [s for s, _ in F.ABLATION_SETS if s != "base+holder"]
    for prev_set, next_set in zip(order, order[1:]):
        for kind in kinds:
            a, b = ics.get((prev_set, kind)), ics.get((next_set, kind))
            if a is None or b is None:
                continue
            step = paired_ic_delta(b, a, horizon)
            step.update({"step": f"{prev_set} -> {next_set}", "model": kind})
            ladder.append(step)
    out["nested_ladder_steps"] = ladder
    return out


def univariate_interaction_scan(df: pd.DataFrame, horizons=(1, 12)) -> dict:
    """Every extension feature, on its own, against the forward excess.

    This is a DIAGNOSTIC and not the verdict: a univariate IC says nothing about
    whether a model already had the information. It exists to answer "which
    single interaction feature is the best one" without pretending that answer
    is the ablation's.
    """
    out: dict = {}
    for h in horizons:
        y = f"excess_vw_{h}m"
        sub = df[df[y].notna()]
        rows = []
        for c in F.all_ext_features():
            if c not in sub.columns or sub[c].notna().sum() < 1000:
                continue
            ic = monthly_ic(sub, c, y)
            if len(ic) < 12:
                continue
            t = _t_of(ic)
            rows.append({
                "feature": c, "family": F.family_of(c),
                "months": int(len(ic)),
                "n_effective_blocks": round(len(ic) / h, 1),
                "mean_ic": round(float(ic.mean()), 5),
                "t_stat": round(t, 3) if t is not None else None,
                "t_block_adjusted": (round(t / np.sqrt(h), 3)
                                     if t is not None and h > 1 else
                                     (round(t, 3) if t is not None else None)),
                "share_months_positive": round(float((ic > 0).mean()), 4),
                "coverage": round(float(sub[c].notna().mean()), 4),
            })
        rows.sort(key=lambda r: -abs(r["t_stat"] or 0.0))
        out[f"{h}m"] = rows
    return out


def null_check(df: pd.DataFrame, horizon: int = 1) -> dict:
    """The full feature set with the TRAINING target permuted WITHIN each month.

    Within the date block, never across it: a shuffled DATE null controls for the
    calendar and not for the cross section, which is the error S24 paid for.
    """
    cols = D.feature_columns() + F.columns_for(("analyst", "holder", "interaction"))
    pred, _ = walk_forward_preds(df, cols, "lgbm", horizon, shuffle=True, verbose=False)
    y = f"excess_vw_{horizon}m"
    scored = df.assign(_pred=pred)
    scored = scored[scored["_pred"].notna() & scored[y].notna()]
    ic = monthly_ic(scored, "_pred", y)
    t = _t_of(ic)
    return {"months": int(len(ic)),
            "mean_ic": round(float(ic.mean()), 5) if len(ic) else None,
            "t_stat": round(t, 3) if t is not None else None,
            "book": book_for_horizon(scored, "_pred", horizon),
            "reads": ("the training target was permuted WITHIN each month, so the "
                      "cross-sectional pairing is destroyed while the calendar, the "
                      "market factor and the whole pipeline are untouched. A non-zero "
                      "IC here would be a leak in the plumbing, not a signal.")}


def family_gain_shares(df: pd.DataFrame, horizon: int = 1) -> dict:
    """LightGBM gain, aggregated by family, from the LAST walk-forward fit.

    Descriptive only: gain says what the model USED, never what it EARNED. It is
    reported because "the family added nothing" and "the model never looked at
    the family" are different findings and the receipt should not conflate them.
    """
    cols = D.feature_columns() + F.columns_for(("analyst", "holder", "interaction"))
    splits = list(D.walk_forward_splits(df, TEST_YEARS, horizon))
    if not splits:
        return {"note": "no split"}
    _y, tr, te = splits[-1]
    _p, meta, model = M.fit_predict("lgbm", ARM, df.loc[tr], df.loc[te], cols,
                                    horizon, return_model=True)
    names = meta["feature_cols"]
    gain = np.asarray(model.booster_.feature_importance(importance_type="gain"),
                      dtype="float64")
    tot = float(gain.sum()) or 1.0
    by_fam: dict[str, float] = {"base": 0.0, "analyst": 0.0, "holder": 0.0,
                                "interaction": 0.0}
    per_feature = {}
    for n, gv in zip(names, gain):
        fam = F.family_of(n) or "base"
        by_fam[fam] += float(gv)
        if fam != "base":
            per_feature[n] = round(float(gv) / tot, 5)
    return {
        "test_year": int(splits[-1][0]),
        "gain_share_by_family": {k: round(v / tot, 5) for k, v in by_fam.items()},
        "gain_share_by_ext_feature": dict(
            sorted(per_feature.items(), key=lambda kv: -kv[1])),
        "reads": "gain says what the model USED, never what it EARNED.",
    }


# -------------------------------------------------------------------- main

def prereg_header() -> dict:
    return {
        "written_before_any_result": True,
        "date": "2026-09-03",
        "licence": ("PRODUCT_EXPERIMENT -- exploration. No significance gate, no MDE, "
                    "no multiplicity control, and correspondingly NO claim of alpha. "
                    "PIT discipline, absent target leakage, non-zero costs and frozen "
                    "walk-forward splits do NOT relax."),
        "question": ("Does a family of 13F-ownership or analyst-identity features add "
                     "OUT-OF-SAMPLE value to a learner that already sees price, "
                     "consensus, revisions, coverage and the band prior?"),
        "primary_metric": ("the PAIRED monthly difference in cross-sectional rank IC "
                           "between the family model and the base model, t across "
                           "MONTHS (CANON 58 -- date blocks, never name-months)."),
        "secondary": ("terminal wealth of a monthly top-50 value-weighted book net of "
                      "10 bps/side on measured weight turnover; decile spread."),
        "decision_rule": ("a family that does not raise the paired delta IC above zero "
                          "at BOTH horizons and for BOTH model kinds is recorded as "
                          "adding nothing. A negative is recorded as a negative and "
                          "not smoothed into 'directionally encouraging'."),
        "known_negatives_not_re_run": {
            "sentiment_novelty_attention": ("T12 CLOSED NEGATIVE: only 7.7% of corpus "
                                            "news is a new dated fact; Benzinga 390:1 "
                                            "coverage makes 'requires news' a mega-cap "
                                            "filter. Not rebuilt."),
            "analyst_accuracy_weighting": ("accuracy does not persist (Spearman 0.087) "
                                           "-- the design is dead before it is built."),
        },
        "nulls": {
            "shuffled_target_within_month": "run on the full feature set at h=1",
            "complete_case_subsample": ("the h=1 ablation is re-run on rows where every "
                                        "family is present, so a negative cannot be a "
                                        "missingness artefact"),
        },
        "models": {"kinds": list(KINDS), "arm": ARM,
                   "note": "the raw arm sees the band prior as a COLUMN (models.arm_features)"},
        "splits": {"test_years": list(TEST_YEARS),
                   "rule": "expanding by DATE; a training row's target must have MATURED "
                           "before the test year opened"},
        "horizons_months": list(HORIZONS),
        "costs": {"bps_per_side": COST_BPS, "applied_to": "measured weight turnover, both sides"},
    }


def run(rebuild: bool = False, quick: bool = False, verbose: bool = True,
        horizons: tuple[int, ...] | None = None,
        kinds: tuple[str, ...] | None = None,
        skip_complete_case: bool = False, out: Path | None = None) -> int:
    t_start = time.time()
    global RECEIPT
    if out is not None:
        RECEIPT = out
    kinds = kinds or (("ridge",) if quick else KINDS)
    horizons = horizons or ((1,) if quick else HORIZONS)

    print("loading the training table ...", flush=True)
    df = D.load()
    print(f"  {len(df):,} rows x {len(df.columns)} cols", flush=True)

    print("loading/building the extension panels ...", flush=True)
    holder, analyst, build_diag = F.load_or_build(rebuild=rebuild, verbose=verbose)
    print(f"  holder panel {len(holder):,} rows; analyst panel {len(analyst):,} rows",
          flush=True)

    print("attaching ...", flush=True)
    df, attach_diag = F.attach(df, holder, analyst)
    print(f"  {len(df):,} rows x {len(df.columns)} cols", flush=True)

    receipt: dict = {
        "PRE_REGISTRATION": prereg_header(),
        "run": {
            "built_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(),
            "features_ext": F.describe(),
            "schema_hash_base": D.schema_hash(),
            "model_seed": M.SEED,
            "receipt": str(RECEIPT.relative_to(REPO)).replace("\\", "/"),
        },
        "panels": build_diag,
        "attach": attach_diag,
        "table": {"rows": int(len(df)), "months": int(df["month"].nunique()),
                  "names": int(df["permno"].nunique()),
                  "month_min": str(df["month"].min()), "month_max": str(df["month"].max())},
        "horizons": {},
    }

    for h in horizons:
        print(f"=== horizon {h}m ===", flush=True)
        receipt["horizons"][f"{h}m"] = run_horizon(df, h, kinds, "all_rows",
                                                   verbose=verbose)

    # ---- the missingness control: every family present on every row
    ext = F.all_ext_features()
    core = [c for c in ext if c not in ("h_top_holder_log_chg", "a_bias_disp",
                                        "h_n_holders_chg_pct", "h_inst_own_chg")]
    cc = df.dropna(subset=core)
    receipt["complete_case"] = {
        "rule": ("every extension feature present, except four that are structurally "
                 "null on a name's first observed quarter or with a single covering "
                 "analyst (h_top_holder_log_chg, h_n_holders_chg_pct, h_inst_own_chg, "
                 "a_bias_disp)"),
        "rows": int(len(cc)), "share_of_table": round(float(len(cc) / len(df)), 4),
        "months": int(cc["month"].nunique()), "names": int(cc["permno"].nunique()),
    }
    if skip_complete_case:
        receipt["complete_case"]["horizon_1m"] = {
            "note": "NOT RUN in this invocation (--skip-complete-case)."}
    elif len(cc) > 20_000 and cc["month"].nunique() >= 60:
        print("=== complete-case subsample, horizon 1m ===", flush=True)
        receipt["complete_case"]["horizon_1m"] = run_horizon(
            cc, 1, kinds, "complete_case", verbose=verbose)
    else:
        receipt["complete_case"]["horizon_1m"] = {
            "note": "REFUSED: the complete-case subsample is too small or too short to "
                    "grade. Recorded as CANNOT DETERMINE, not as agreement."}

    print("univariate scan ...", flush=True)
    receipt["univariate_scan"] = univariate_interaction_scan(df, horizons)

    if not quick:
        print("null (shuffled target within month) ...", flush=True)
        receipt["null_shuffled_within_month_1m"] = null_check(df, 1)
        print("gain shares ...", flush=True)
        receipt["lgbm_gain_shares_1m"] = family_gain_shares(df, 1)

    receipt["run"]["seconds"] = round(time.time() - t_start, 1)
    receipt["VERDICT"] = verdict(receipt, horizons, kinds)

    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    print(f"\nreceipt -> {RECEIPT}", flush=True)
    _print_scoreboard(receipt, horizons, kinds)
    return 0


def verdict(receipt: dict, horizons, kinds) -> dict:
    """The mechanical read of the decision rule. No judgement at this step."""
    out: dict = {}
    for fam_set in ("base+analyst", "base+holder", "base+analyst+holder",
                    "base+analyst+holder+interaction"):
        rows = []
        for h in horizons:
            hh = receipt["horizons"].get(f"{h}m", {})
            for kind in kinds:
                v = (hh.get("sets", {}).get(fam_set, {}).get("models", {})
                     .get(kind, {}).get("vs_base"))
                if v:
                    rows.append({"horizon": f"{h}m", "model": kind,
                                 "delta_mean_ic": v.get("delta_mean_ic"),
                                 "t_paired": v.get("t_paired"),
                                 "delta_terminal_wealth_net":
                                     v.get("delta_terminal_wealth_net")})
        pos = [r for r in rows if (r["delta_mean_ic"] or 0) > 0]
        out[fam_set] = {
            "cells": rows,
            "cells_positive_delta_ic": f"{len(pos)}/{len(rows)}",
            "reads": ("ADDS OOS VALUE" if rows and len(pos) == len(rows)
                      else "MIXED" if pos else "ADDS NOTHING (or subtracts)"),
        }
    return out


def _print_scoreboard(r: dict, horizons, kinds) -> None:
    print("\n" + "=" * 74)
    print("RESULTS SCOREBOARD -- feature-family ablation")
    print("=" * 74)
    for h in horizons:
        hh = r["horizons"][f"{h}m"]
        print(f"\nhorizon {h}m   (target {hh['target']}, "
              f"{hh['n_rows_with_target']:,} rows with a matured target)")
        print(f"  {'set':<34}{'model':<7}{'meanIC':>9}{'dIC':>9}"
              f"{'t_pair':>8}{'TW_net':>9}{'dTW':>8}")
        for set_name, _f in F.ABLATION_SETS:
            for kind in kinds:
                m = hh["sets"][set_name]["models"].get(kind)
                if not m:
                    continue
                v = m.get("vs_base", {})
                bk = m.get("book", {})
                print(f"  {set_name:<34}{kind:<7}"
                      f"{_f4(m['rank_ic']['mean_ic']):>9}"
                      f"{_f4(v.get('delta_mean_ic')):>9}"
                      f"{_f2(v.get('t_paired')):>8}"
                      f"{_f2(bk.get('terminal_wealth_net')):>9}"
                      f"{_f2(v.get('delta_terminal_wealth_net')):>8}")
    print("\nVERDICT")
    for k, v in r["VERDICT"].items():
        print(f"  {k:<34}{v['cells_positive_delta_ic']:>8}  {v['reads']}")
    n = r.get("null_shuffled_within_month_1m")
    if n:
        print(f"\nNULL (shuffled target within month, 1m): mean IC {n['mean_ic']}, "
              f"t {n['t_stat']} over {n['months']} months")
    print("\nbest single extension feature by |t| (1m univariate):")
    for row in r["univariate_scan"].get("1m", [])[:5]:
        print(f"  {row['feature']:<32}{row['family']:<12}"
              f"IC {row['mean_ic']:+.5f}  t {row['t_stat']:+.2f}  "
              f"cov {row['coverage']:.2f}")


def _f4(v):
    return "n/a" if v is None else f"{v:+.5f}"


def _f2(v):
    return "n/a" if v is None else f"{v:+.3f}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rebuild", action="store_true",
                    help="rebuild the holder and analyst panels from WRDS parquet")
    ap.add_argument("--quick", action="store_true",
                    help="1-month horizon, ridge only -- a smoke test, not a verdict")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--horizons", default=None,
                    help="comma-separated horizons in months, e.g. '1' or '1,12'")
    ap.add_argument("--kinds", default=None,
                    help="comma-separated model kinds, e.g. 'ridge' or 'ridge,lgbm'")
    ap.add_argument("--skip-complete-case", action="store_true",
                    help="skip the missingness control (it is a control, so the "
                         "receipt records that it did not run)")
    ap.add_argument("--out", default=None, help="receipt path override")
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass
    hz = (tuple(int(x) for x in a.horizons.split(",")) if a.horizons else None)
    kd = (tuple(x.strip() for x in a.kinds.split(",")) if a.kinds else None)
    return run(rebuild=a.rebuild, quick=a.quick, verbose=not a.quiet,
               horizons=hz, kinds=kd, skip_complete_case=a.skip_complete_case,
               out=Path(a.out) if a.out else None)


if __name__ == "__main__":
    raise SystemExit(main())
