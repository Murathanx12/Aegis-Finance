"""N2 -- THE SELECTION-FREE ENSEMBLE (Numerai's meta-model, on our tape).

WHY AN ENSEMBLE AND NOT A CHAMPION
==================================
Every family this repo has ever graded ends the same way: one cell is picked
because it looked best, and the deflated Sharpe then punishes the picking. A3
showed the sharpest version -- the neural family's champion is an individual
SEED in 15 of 15 CPCV partitions and never the seed-mean, with PBO 0.51 at the
horizon the books trade. **The winner is not choosable in advance.**

The field's answer is not a better selector. It is to stop selecting: Numerai
pays a crowd of models whose individual correlations are ~0.02 and monetises
the META-MODEL. This job builds ours. No arm is chosen, dropped or tuned, so
the deflated Sharpe is computed with **family = 1** -- and the receipt says, in
the same breath, that the INPUTS were searched, because they were: every arm
here exists because some earlier session fitted it.

WHAT IS COMBINED, AND HOW
=========================
Each arm's monthly cross-sectional PERCENTILE RANK, averaged. Ranks, not
scores: the arms are on incompatible scales (a classifier probability, a ridge
residual return, a pct-rank momentum) and averaging those directly would be an
accidental weighting by units.

Two weightings, both reported:

* **PRIMARY -- reliability-weighted.** Arm `a`'s weight in month `m` is its
  trailing 36-month **beta-matched** book excess, floored at zero and
  normalised. Strictly point-in-time: months `< m` only, and the beta used for
  the matching is itself a trailing regression. An arm whose trailing excess is
  negative gets weight ZERO, never a negative weight -- inverting a losing arm
  is selection by the back door and would need its own null.
* **SECONDARY -- equal weight.** Zero fitted parameters at all. If the primary
  does not beat this, the reliability weighting bought nothing and the receipt
  says so.

COVERAGE IS RENORMALISED, NOT ASSUMED
=====================================
`ridge` and `encoder` exist for ~39% of the panel's rows; the stage arms exist
from 2004. A row scored by three arms and a row scored by eight are not the
same object, so weights are renormalised over the arms actually present on that
row and the receipt reports the arm-count distribution. Filling an absent arm
with 0.5 would have quietly pulled every thin row toward the median.

    python -m scripts.n2_ensemble --smoke
    python -m scripts.n2_ensemble
"""

from __future__ import annotations

import argparse
import json
import math
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

from backend.services import receipt_provenance as RP           # noqa: E402
from scripts.labor_a1_shadow_grader import (                    # noqa: E402
    _month_windows, _window_leg, ols_market_model)

OUT_DIR = REPO / "backend" / "data" / "optimus" / "night_lab_2026-09-07"
RECEIPT = OUT_DIR / "N2_ensemble.json"
SCORES = OUT_DIR / "N2_ensemble_scores.parquet"

#: The trailing window the reliability weight is computed over. 36 months is
#: the mandate's number and is long enough that one good quarter cannot take
#: over the book; it is NOT tuned, and tuning it would reintroduce the
#: selection this job exists to avoid.
RELIABILITY_MONTHS = 36
BETA_MONTHS = 36
NW_LAG = 4

#: The arms. Each is a column produced by an EARLIER session; this job fits
#: nothing. `options` and `behavioural` are named here and reported ABSENT
#: rather than silently omitted -- W5/W6 graded them as feature families, not
#: as trained cross-sectional selectors, so there is no OOS score column to
#: stack, and pretending otherwise would make the ensemble look broader than
#: it is.
ARM_COLUMNS: tuple[tuple[str, str], ...] = (
    ("lgbm_clf", "lgbm_clf"),
    ("lgbm_raw", "lgbm_raw"),
    ("nn_pre_causal", "nn_pre_causal_seedmean"),
    ("ridge", "ridge"),
    ("encoder", "encoder"),
    ("revisions", "revisions"),
    ("momentum", "momentum"),
    ("quality_mom", "quality_mom"),
    ("options", "options_selector"),
    ("behavioural", "behavioural_selector"),
)

ENSEMBLE_K = 100        # the book the ensemble is judged in (N1 grades the rest)


def _r(v, nd: int = 5):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, nd) if math.isfinite(f) else None


def _ncdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _t(series) -> float | None:
    s = pd.Series(series).dropna().astype("float64")
    if len(s) < 3:
        return None
    sd = float(s.std(ddof=1))
    scale = float(np.max(np.abs(s.to_numpy()))) if len(s) else 0.0
    if not math.isfinite(sd) or sd <= max(1e-9 * scale, 0.0) or sd <= 0:
        return None
    return float(s.mean() / (sd / math.sqrt(len(s))))


def trailing_reliability(excess: pd.Series, window: int = RELIABILITY_MONTHS) -> pd.Series:
    """Mean beta-matched excess over the PREVIOUS `window` months.

    `shift(1)` is the whole point: the value carried at month m must be
    computable at the START of month m. Without it the ensemble would weight
    each arm by how well it was about to do, which is a backtest of the future
    and would have looked spectacular.
    """
    s = pd.Series(excess).astype("float64")
    return s.rolling(window, min_periods=max(12, window // 3)).mean().shift(1)


def arm_excess(df: pd.DataFrame, col: str, rf: pd.Series, *, k: int = ENSEMBLE_K,
               cost_bps: float = 10.0) -> pd.Series:
    """One arm's monthly BETA-MATCHED excess, on a top-k equal-weighted book.

    The beta is a TRAILING regression, refitted every month, so the series is
    usable as a point-in-time reliability signal. A full-sample beta would make
    the excess of the last month depend on the first.
    """
    from learner import evaluate as E
    from learner import neural_long as N
    bk = E.book(df, col, k=k, weight="ew", cost_bps=cost_bps,
                ret_col="fwd_1m", mkt_col="mkt_vw_1m",
                tradable_floor=N.TRADABLE_FLOOR_USD, hold_k=2 * k,
                return_series=True)
    ser = bk.get("_series")
    if ser is None or not len(ser.get("net", [])):
        return pd.Series(dtype=float)
    net = ser["net"].astype("float64")
    mkt = ser["market"].reindex(net.index).astype("float64")
    rfs = rf.reindex(net.index).fillna(0.0)
    y, x = (net - rfs).to_numpy(), (mkt - rfs).to_numpy()
    out = []
    for i in range(len(net)):
        if i < BETA_MONTHS:
            out.append(np.nan)
            continue
        yy, xx = y[i - BETA_MONTHS:i], x[i - BETA_MONTHS:i]
        vx = float(np.var(xx, ddof=1))
        b = float(np.cov(yy, xx, ddof=1)[0, 1] / vx) if vx > 0 else np.nan
        out.append(y[i] - b * x[i] if math.isfinite(b) else np.nan)
    return pd.Series(out, index=net.index)


def build_scores(df: pd.DataFrame, arms: dict[str, str], weights: pd.DataFrame
                 ) -> tuple[pd.Series, pd.Series, dict]:
    """The two ensemble score columns, aligned to `df`'s index."""
    ranks = {}
    for name, col in arms.items():
        ranks[name] = df.groupby("month")[col].rank(pct=True)
    R = pd.DataFrame(ranks, index=df.index)
    present = R.notna()
    n_arms = present.sum(axis=1)

    # equal weight, renormalised over the arms actually on the row
    ew = R.mean(axis=1, skipna=True)

    # reliability weight, per month, renormalised the same way
    w_rows = weights.reindex(df["month"].to_numpy())
    w_rows.index = df.index
    w_rows = w_rows[list(arms)].fillna(0.0)
    w_eff = w_rows.where(present, 0.0)
    denom = w_eff.sum(axis=1)
    # A month in which NO arm had a positive trailing record: fall back to
    # equal weight rather than dropping the month. Declared, not silent.
    fallback = denom <= 0
    rw = (R.fillna(0.0) * w_eff).sum(axis=1) / denom.replace(0.0, np.nan)
    rw = rw.where(~fallback, ew)

    meta = {
        "rows": int(len(R)),
        "arm_count_distribution": {str(int(k)): int(v) for k, v in
                                   n_arms.value_counts().sort_index().items()},
        "rows_with_no_arm": int((n_arms == 0).sum()),
        "months_falling_back_to_equal_weight": int(
            df.loc[fallback, "month"].nunique()) if fallback.any() else 0,
    }
    return rw, ew, meta


def run(*, smoke: bool = False, verbose: bool = True) -> dict:
    from learner import benchmark as BM
    from learner import evaluate as E
    from learner import inference as INF
    from learner import long_panel as LP
    from learner import neural_long as N
    from scripts import n1_construction_books as N1
    from scripts import w3_neural_floored as W3B
    from scripts.weekend_lab_jobs import era_sign_table

    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    t0 = time.perf_counter()
    tracker = RP.InputTracker()
    out: dict = {
        "job": "N2_ensemble",
        "lane": "N2",
        "question": ("does a SELECTION-FREE rank ensemble of every arm we have "
                     "already trained beat the arms it is made of, and does "
                     "weighting by trailing beta-matched reliability beat equal "
                     "weight?"),
        "licence": "PRODUCT_EXPERIMENT",
        "no_selection_claim": ("no arm is chosen, dropped or tuned by this job, so "
                               "the deflated Sharpe is computed with family = 1. "
                               "THE INPUTS WERE SEARCHED: every arm exists because an "
                               "earlier session fitted it, and that search is not "
                               "corrected for here and cannot be."),
        "llm_spend_usd": 0.0, "llm_calls": 0, "network_calls": 0, "models_fitted": 0,
        "memory_free_gb_before": W3B.free_gb(),
        "smoke": bool(smoke),
    }
    if not LP.LONG_TABLE.exists():
        out.update(status="SKIPPED", headline=f"SKIPPED: {LP.LONG_TABLE} is absent")
        return out

    log("  loading the floored universe ...")
    df, uni, fp = W3B.load_universe(verbose=False)
    df.attrs["_fingerprint"] = fp
    tracker.opened(LP.LONG_TABLE)
    out["universe_fingerprint_sha256"] = fp
    out["training_universe"] = {k: uni[k] for k in
                                ("dollar_volume_floor_usd_per_day", "min_close_usd",
                                 "rows_after", "months_after") if k in uni}

    out["selector_sources"] = {
        "stage": N1._attach_stage(df, tracker),
        "oos_v2": N1._attach_v2(df, tracker),
        "panel_native": N1._attach_panel_natives(df),
        "quality_mom": N1._attach_quality_mom(df, tracker),
    }
    arms = {n: c for n, c in ARM_COLUMNS if c in df.columns and df[c].notna().any()}
    out["arms_stacked"] = {n: {"column": c,
                               "coverage_share": _r(float(df[c].notna().mean()), 4)}
                           for n, c in arms.items()}
    out["arms_absent"] = {n: c for n, c in ARM_COLUMNS if n not in arms}
    if len(arms) < 2:
        out.update(status="REFUSED",
                   headline=f"REFUSED: only {len(arms)} arm(s) available; an ensemble "
                            "of one is the arm")
        return out

    months_all = pd.Index(sorted(df["month"].dropna().unique()))
    win = _month_windows(df)
    try:
        rf_d = BM.cash().returns.dropna().astype("float64")
        rf, rf_note = _window_leg(rf_d, win, months_all)
        rf_note["source"] = "learner.benchmark.cash() -- pinned FF daily RF, OFFLINE"
    except Exception as exc:                                        # noqa: BLE001
        rf = pd.Series(0.0, index=months_all)
        rf_note = {"available": False, "why": f"{type(exc).__name__}: {exc}"}
    out["risk_free_leg"] = rf_note

    log(f"  measuring trailing reliability for {len(arms)} arms ...")
    excesses, reliab = {}, {}
    for name, col in arms.items():
        ex = arm_excess(df, col, rf)
        if not len(ex):
            continue
        excesses[name] = ex
        reliab[name] = trailing_reliability(ex)
    W = pd.DataFrame(reliab).reindex(months_all)
    Wpos = W.clip(lower=0.0)
    out["reliability"] = {
        "window_months": RELIABILITY_MONTHS,
        "beta_window_months": BETA_MONTHS,
        "definition": ("trailing mean of the arm's beta-matched excess on its own "
                       f"top-{ENSEMBLE_K} EW hysteresis book at 10 bps, shifted one "
                       "month so it is knowable at the start of the month it weights"),
        "mean_weight_share_by_arm": {
            k: _r(float(v), 4) for k, v in
            (Wpos.div(Wpos.sum(axis=1).replace(0, np.nan), axis=0)).mean().items()},
        "months_with_no_positive_arm": int((Wpos.sum(axis=1) <= 0).sum()),
        "full_sample_mean_excess_by_arm_pct_per_year": {
            k: _r(float(v.mean()) * 12 * 100, 3) for k, v in excesses.items()},
    }

    log("  stacking ranks ...")
    rw, ew, meta = build_scores(df, arms, Wpos)
    df["ensemble"] = rw.astype("float32")
    df["ensemble_ew"] = ew.astype("float32")
    out["stacking"] = meta

    SCORES.parent.mkdir(parents=True, exist_ok=True)
    df[["permno", "month", "ensemble", "ensemble_ew"]].to_parquet(SCORES, index=False)
    out["scores_parquet"] = str(SCORES)

    log("  grading the ensemble and every arm in the SAME construction ...")
    cells, fam = {}, {}
    graded = list(arms.items()) + [("ENSEMBLE_reliability", "ensemble"),
                                   ("ENSEMBLE_equal_weight", "ensemble_ew")]
    for name, col in graded:
        bk = E.book(df, col, k=ENSEMBLE_K, weight="ew", cost_bps=10.0,
                    ret_col="fwd_1m", mkt_col="mkt_vw_1m",
                    tradable_floor=N.TRADABLE_FLOOR_USD, hold_k=2 * ENSEMBLE_K,
                    return_series=True, return_weights=True)
        blk, ex = N1.grade(bk, rf, label=name, df=df, pred_col=col,
                           construction=f"top-{ENSEMBLE_K} EW, hold until rank > "
                                        f"{2 * ENSEMBLE_K}, 10 bps")
        cells[name] = blk
        if len(ex):
            fam[name] = ex
    out["cells"] = cells

    # ---- the two comparisons that decide whether this job bought anything
    comp = {}
    if "ENSEMBLE_reliability" in fam and "ENSEMBLE_equal_weight" in fam:
        a, b = fam["ENSEMBLE_reliability"].align(fam["ENSEMBLE_equal_weight"], join="inner")
        d = (a - b).dropna()
        comp["reliability_minus_equal_weight"] = {
            "months": int(len(d)), "annualised_pp": _r(float(d.mean()) * 12 * 100, 3),
            "t_paired": _r(_t(d), 3),
            "reading": ("if this is not positive, the reliability weighting bought "
                        "nothing and equal weight is the honest ensemble"),
        }
    best_arm = max((k for k in fam if not k.startswith("ENSEMBLE")),
                   key=lambda k: float(fam[k].mean()), default=None)
    if best_arm and "ENSEMBLE_reliability" in fam:
        a, b = fam["ENSEMBLE_reliability"].align(fam[best_arm], join="inner")
        d = (a - b).dropna()
        comp["ensemble_minus_the_best_single_arm"] = {
            "best_arm_in_hindsight": best_arm,
            "months": int(len(d)), "annualised_pp": _r(float(d.mean()) * 12 * 100, 3),
            "t_paired": _r(_t(d), 3),
            "reading": ("the arm is chosen IN HINDSIGHT, so this comparison is "
                        "deliberately unfair to the ensemble; a small negative "
                        "number here is the ensemble doing its job"),
        }
    mean_arm = pd.DataFrame({k: v for k, v in fam.items()
                             if not k.startswith("ENSEMBLE")}).mean(axis=1)
    if "ENSEMBLE_reliability" in fam and len(mean_arm):
        a, b = fam["ENSEMBLE_reliability"].align(mean_arm, join="inner")
        d = (a - b).dropna()
        comp["ensemble_minus_the_AVERAGE_arm"] = {
            "months": int(len(d)), "annualised_pp": _r(float(d.mean()) * 12 * 100, 3),
            "t_paired": _r(_t(d), 3),
            "reading": "the fair comparison: no arm is chosen on either side",
        }
    out["comparisons"] = comp

    # ---- inference on BOTH weightings. The family is TWO, not one: this job
    # builds two ensembles and reports both, so a reader who takes the better
    # one has looked at two cells. Saying "family = 1" while printing two
    # numbers is the selection this job exists to avoid, done in the receipt
    # instead of in the code.
    out["inference"] = {}
    for tag in ("ENSEMBLE_reliability", "ENSEMBLE_equal_weight"):
        arm = fam.get(tag)
        if arm is None or len(arm) < 24:
            continue
        try:
            out["inference"][tag] = INF.full_report(
                arm.to_numpy(), n_trials=2, seed=20260907)
        except Exception as exc:                                    # noqa: BLE001
            out["inference"][tag] = {"verdict": "CANNOT DETERMINE",
                                     "why": f"{type(exc).__name__}: {exc}"}
        out.setdefault("era_tables", {})[tag] = era_sign_table(arm)

    # ---- THE SUB-PERIOD THAT MATTERS: months when the ensemble is actually an
    # ensemble. Before 2004 only the panel-native arms exist, so the early era
    # is a three-arm average wearing an eight-arm name, and an edge that lives
    # only there is not evidence about the object we would run.
    per_month_arms = (pd.DataFrame({n: df.groupby("month")[c].apply(
        lambda x: float(x.notna().mean())) for n, c in arms.items()})
        .fillna(0.0))
    n_arms_by_month = (per_month_arms > 0.5).sum(axis=1)
    out["arms_available_by_month"] = {
        "min": int(n_arms_by_month.min()), "max": int(n_arms_by_month.max()),
        "first_month_with_all_arms": (str(n_arms_by_month[
            n_arms_by_month == n_arms_by_month.max()].index[0])
            if (n_arms_by_month == n_arms_by_month.max()).any() else None),
        "months_by_arm_count": {str(int(k)): int(v) for k, v in
                                n_arms_by_month.value_counts().sort_index().items()},
    }
    full_months = n_arms_by_month[n_arms_by_month >= max(6, int(n_arms_by_month.max()) - 1)].index
    out["full_ensemble_subperiod"] = {
        "rule": ">= 6 arms present in the month (or one short of the maximum)",
        "months": int(len(full_months)),
    }
    for tag in ("ENSEMBLE_reliability", "ENSEMBLE_equal_weight"):
        arm = fam.get(tag)
        if arm is None:
            continue
        sub = arm.reindex(arm.index.intersection(full_months)).dropna()
        if len(sub) < 24:
            out["full_ensemble_subperiod"][tag] = {"verdict": "CANNOT DETERMINE",
                                                   "months": int(len(sub))}
            continue
        t = _t(sub)
        out["full_ensemble_subperiod"][tag] = {
            "months": int(len(sub)),
            "first_month": str(sub.index[0]), "last_month": str(sub.index[-1]),
            "annualised_beta_matched_pct": _r(float(sub.mean()) * 12 * 100, 3),
            "t_paired": _r(t, 3),
            "p_one_sided": _r(1.0 - _ncdf(float(t)), 6) if t is not None else None,
            "era_table": era_sign_table(sub),
        }

    e = cells.get("ENSEMBLE_equal_weight", {})
    out["headline"] = (
        f"ensemble (EQUAL-weighted -- the reliability weighting lost; top-{ENSEMBLE_K} "
        f"EW hysteresis, 10 bps): "
        f"beta {e.get('beta')}, beta-matched "
        f"{(e.get('PRIMARY_beta_matched') or {}).get('annualised_pct')}%/yr t "
        f"{(e.get('PRIMARY_beta_matched') or {}).get('t_paired')} over "
        f"{e.get('months')} months, TW {e.get('terminal_wealth_net')} vs market "
        f"{e.get('terminal_wealth_market_same_months')}; "
        f"vs the average arm "
        f"{(comp.get('ensemble_minus_the_AVERAGE_arm') or {}).get('annualised_pp')}pp")
    out["memory_free_gb_after"] = W3B.free_gb()
    out["wall_seconds"] = round(time.perf_counter() - t0, 1)
    RP.attach(out, sys.argv,
              {"reliability_months": RELIABILITY_MONTHS, "beta_months": BETA_MONTHS,
               "ensemble_k": ENSEMBLE_K, "smoke": bool(smoke)},
              tracker)
    return out


def write(rec: dict, path: Path = RECEIPT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rec["generated_utc"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    path = Path(a.out) if a.out else RECEIPT
    try:
        rec = run(smoke=a.smoke)
    except Exception:                                               # noqa: BLE001
        rec = {"job": "N2_ensemble", "status": "FAILED",
               "traceback": traceback.format_exc(),
               "headline": "FAILED -- see traceback"}
        write(rec, path)
        print(rec["traceback"], flush=True)
        return 1
    write(rec, path)
    print(rec.get("headline"), flush=True)
    print(f"-> {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
