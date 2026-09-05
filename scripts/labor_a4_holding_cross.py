"""A4 -- HOLDING PERIOD x SELECTOR. WHERE DOES EACH SELECTOR'S EDGE ACTUALLY LIVE?

THE QUESTION, AND WHAT IS AND IS NOT VARYING
============================================
Both selectors predict a ONE-MONTH forward excess. What varies here is not the
model and not the forecast horizon -- it is how long the book HOLDS what the
one-month forecast selected. AEGIS-HORIZON-1 (S36) recorded that the horizon
belongs to the ADMITTING SIGNAL; this job asks the money version of that for the
two selectors we have: given a 1m ranking, is the edge collected in the first
month, or does it keep paying for three, six, twelve?

That matters because turnover is the largest single cost line in this repo. The
top-50 books run near 1.0 monthly turnover, and at 25 bps a side that is ~6%/yr
-- larger than most edges ever measured here. If the same edge survives a
six-month hold, the cost line falls by most of itself.

TWO CONSTRUCTIONS, BECAUSE THE MANDATE'S RULE ONLY EXISTS IN ONE OF THEM
=======================================================================
The mandate says "hold 1/3/6/12 months with hysteresis (top-50 in, out below
rank 100)". Those are two different levers and `learner/evaluate.py` implements
them in two different functions:

  * **the HOLD BAND** (`book(k=50, hold_k=100)`): rebalance every month, BUY at
    rank <= 50, HOLD until rank > 100. The holding period is not imposed -- it
    is an OUTCOME, and the receipt reports the realised mean holding period
    implied by measured turnover (1 / turnover, in months). This is the
    mandate's rule literally, and the ladder hold_k in {75, 100, 150, 200, 400}
    is swept beside it so the reader sees a curve rather than one point.

  * **the COHORT** (`overlapping_book(horizon=h)`): at every month a new cohort
    of 50 names is formed and held exactly h months; the portfolio is 1/h in
    each live cohort. This is the "hold for h months" reading, and hysteresis is
    NOT available on it -- a cohort held h months by construction IS the
    strongest possible hold band. Saying that out loud is cheaper than a receipt
    in which one of the two levers silently did nothing.

Both are reported. Neither is quietly presented as the other.

THE RULER
=========
PRIMARY is the BETA-MATCHED excess, for the reason C1 established and A1
repeats: these books carry betas of 1.18 and 1.33, and the raw-market excess
counts a fifth to a third of the market's own return as the book's edge. The
raw-market excess is carried as SECONDARY in every cell. Costs at 10 AND 25 bps
everywhere -- the whole question is a cost question, and a horizon table at one
cost rate answers half of it.

$0 LLM spend. Zero network calls. No model is fitted; the predictions are the
frozen W3b stage vintage and this job REFUSES rather than refitting them.

    python -m scripts.labor_a4_holding_cross
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
RECEIPT = OUT_DIR / "A4_holding_cross_run01.json"

SELECTORS = {"lgbm_clf": "lgbm_clf", "nn_pre_causal": "nn_pre_causal_seedmean"}
COSTS: tuple[float, ...] = (10.0, 25.0)
K = 50

#: The mandate's rule is hold_k = 100. The ladder is swept beside it so the
#: answer is a CURVE and not one point that happened to be asked for.
HOLD_BANDS: tuple[int | None, ...] = (None, 75, 100, 150, 200, 400)
MANDATE_HOLD_K = 100

#: Cohort lengths for the overlapping construction.
COHORT_HORIZONS: tuple[int, ...] = (1, 3, 6, 12)

NW_LAG = 4


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


# ------------------------------------------------------------------ one cell

def grade_cell(bk: dict, rf: pd.Series, *, label: str, construction: str,
               horizon_months: int) -> tuple[dict, pd.Series]:
    """One book -> the beta-matched (PRIMARY) and raw-market (SECONDARY) blocks.

    Returns (block, beta_matched_excess_series) so the caller can build the
    family without regrading anything.
    """
    from scripts.weekend_lab_jobs import era_sign_table
    ser = bk.get("_series")
    if ser is None:
        return {"verdict": "CANNOT DETERMINE", "why": "no series"}, pd.Series(dtype=float)
    net = ser["net"].astype("float64")
    mkt = ser["market"].reindex(net.index).astype("float64")
    turn = ser["turnover"].reindex(net.index).astype("float64")
    rfs = rf.reindex(net.index).fillna(0.0)
    reg = ols_market_model(net - rfs, mkt - rfs, lag=NW_LAG)
    beta = reg.get("beta")
    if beta is None:
        return {"verdict": "CANNOT DETERMINE", "regression": reg}, pd.Series(dtype=float)
    bm = float(beta) * mkt + (1.0 - float(beta)) * rfs
    ex_bm = (net - bm).dropna()
    ex_raw = (net - mkt).dropna()
    mean_turn = float(turn.mean())
    blk = {
        "label": label,
        "construction": construction,
        "nominal_horizon_months": int(horizon_months),
        "months": int(len(net)),
        "cost_bps_per_side": bk.get("cost_bps_per_side"),
        "mean_turnover": _r(mean_turn, 4),
        # THE HOLDING PERIOD IS AN OUTCOME, NOT AN INPUT, on the hold-band path.
        # 1/turnover is the standard implied average holding period; it is an
        # approximation and is labelled as one rather than printed as a fact.
        "implied_mean_holding_months": (_r(1.0 / mean_turn, 2)
                                        if mean_turn > 0 else None),
        "implied_holding_note": ("1 / mean monthly weight turnover. An approximation "
                                 "of the average holding period, not a measured one."),
        "annual_cost_line_pct": _r(mean_turn * 2 * (bk.get("cost_bps_per_side") or 0)
                                   / 10_000.0 * 12 * 100, 3),
        "terminal_wealth_net": bk.get("terminal_wealth_net"),
        "terminal_wealth_gross": bk.get("terminal_wealth_gross"),
        "terminal_wealth_market_same_months": bk.get("terminal_wealth_market_same_months"),
        "mean_names_per_month": bk.get("mean_names_per_month"),
        "PRIMARY_beta_matched": {
            "beta": _r(beta, 4),
            "t_beta_minus_1_hac": reg.get("t_beta_minus_1_hac"),
            "annualised_pct": _r(float(ex_bm.mean()) * 12 * 100, 3),
            "t_paired": _r(_t(ex_bm), 3),
            "p_one_sided": (_r(1.0 - _ncdf(float(_t(ex_bm))))
                            if _t(ex_bm) is not None else None),
        },
        "SECONDARY_raw_market": {
            "annualised_pct": _r(float(ex_raw.mean()) * 12 * 100, 3),
            "t_paired": _r(_t(ex_raw), 3),
        },
        "era_table_on_the_beta_matched_excess": era_sign_table(ex_bm),
    }
    return blk, ex_bm


# ------------------------------------------------------------------- the run

def run(*, verbose: bool = True) -> dict:
    from learner import evaluate as E
    from learner import benchmark as BM
    from learner import inference
    from learner import long_panel as LP
    from learner import neural_long as N
    from scripts import w3_neural_floored as W3B

    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    t0 = time.perf_counter()
    out: dict = {
        "job": "A4_holding_cross",
        "lane": "A",
        "question": ("given a ONE-MONTH ranking, how long should the book hold it? "
                     "Two constructions (hold band and cohort) x two selectors x two "
                     "cost rates, graded against the beta-matched benchmark."),
        "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0, "llm_calls": 0, "network_calls": 0,
        "models_fitted": 0,
        "what_varies": ("the HOLDING RULE only. The prediction column is the frozen "
                        "W3b stage vintage in both cases and no model is refitted; the "
                        "signal's own forecast horizon stays 1 month throughout, so "
                        "this is NOT a multi-horizon model comparison (A3 has that)."),
        "memory_free_gb_before": W3B.free_gb(),
    }
    if not LP.LONG_TABLE.exists():
        out["status"] = "SKIPPED"
        out["reasons"] = [f"{LP.LONG_TABLE} is absent"]
        out["headline"] = f"SKIPPED: {LP.LONG_TABLE} is absent"
        return out

    log("  loading the floored universe ...")
    df, uni, fp = W3B.load_universe(verbose=False)
    note_input(LP.LONG_TABLE)
    out["universe_fingerprint_sha256"] = fp
    out["training_universe"] = {k: uni[k] for k in
                                ("dollar_volume_floor_usd_per_day", "min_close_usd",
                                 "rows_after", "months_after")}

    years = list(range(N.FIRST_TEST_YEAR, N.LAST_TEST_YEAR + 1))
    seeds = [N.SEED_BASE + i for i in range(N.N_SEEDS)]
    try:
        for tag, scope in (("incumbents", W3B._scope(years, [])),
                           ("nn_pre_causal", W3B._scope(years, seeds))):
            block, _meta = W3B._read_stage(tag, fp, scope)
            for col in block.columns:
                df[col] = block[col].reindex(df.index).astype("float64")
            note_input(W3B._stage_path(tag))
    except SystemExit as exc:
        out["status"] = "REFUSED"
        out["reasons"] = [str(exc), "refitting the stage predictions would be a "
                                    "different experiment wearing the same name"]
        out["headline"] = "REFUSED: stage predictions unavailable"
        return out
    missing = [c for c in SELECTORS.values() if c not in df.columns]
    if missing:
        out["status"] = "REFUSED"
        out["reasons"] = [f"no column for {missing}"]
        out["headline"] = f"REFUSED: no column for {missing}"
        return out

    # ---- the risk-free leg, over each book month's OWN holding window
    months_all = pd.Index(sorted(df["month"].dropna().unique()))
    win = _month_windows(df)
    try:
        rf_d = BM.cash().returns.dropna().astype("float64")
        rf, rf_note = _window_leg(rf_d, win, months_all)
        rf_note["source"] = "learner.benchmark.cash() -- pinned FF daily RF, OFFLINE"
    except Exception as exc:                                            # noqa: BLE001
        rf = pd.Series(0.0, index=months_all)
        rf_note = {"available": False, "why": f"{type(exc).__name__}: {exc}",
                   "declared": "rf = 0; only the intercept's level moves"}
    out["risk_free_leg"] = rf_note

    cells: dict = {}
    fam_series: dict = {}

    # ---- construction 1: the HOLD BAND (the mandate's rule, plus a ladder)
    log("  construction 1: the hold band ...")
    for name, col in SELECTORS.items():
        for bps in COSTS:
            for hk in HOLD_BANDS:
                key = f"holdband|{name}|hold_k={hk or 'none'}|{int(bps)}bps"
                bk = E.book(df, col, k=K, weight="vw", cost_bps=bps,
                            ret_col="fwd_1m", mkt_col="mkt_vw_1m",
                            tradable_floor=N.TRADABLE_FLOOR_USD,
                            hold_k=hk, return_series=True)
                blk, ex = grade_cell(
                    bk, rf, label=key, horizon_months=1,
                    construction=(f"monthly rebalance, buy at rank <= {K}, "
                                  f"hold until rank > {hk}" if hk else
                                  f"monthly rebalance, top-{K} rebuilt every month "
                                  f"(NO hysteresis -- the control)"))
                cells[key] = blk
                if len(ex):
                    fam_series[key] = ex
        log(f"    {name}: {len(HOLD_BANDS) * len(COSTS)} hold-band cells")

    # ---- construction 2: the COHORT
    log("  construction 2: the cohort ...")
    for name, col in SELECTORS.items():
        for bps in COSTS:
            for h in COHORT_HORIZONS:
                key = f"cohort|{name}|h={h}m|{int(bps)}bps"
                if h == 1:
                    bk = E.book(df, col, k=K, weight="vw", cost_bps=bps,
                                ret_col="fwd_1m", mkt_col="mkt_vw_1m",
                                tradable_floor=N.TRADABLE_FLOOR_USD, return_series=True)
                else:
                    bk = E.overlapping_book(df, col, h, k=K, weight="vw", cost_bps=bps,
                                            ret_col="fwd_1m", mkt_col="mkt_vw_1m",
                                            tradable_floor=N.TRADABLE_FLOOR_USD,
                                            with_risk=False, return_series=True)
                blk, ex = grade_cell(
                    bk, rf, label=key, horizon_months=h,
                    construction=(f"a new cohort of {K} names every month, each held "
                                  f"exactly {h} months, portfolio 1/{h} in each live "
                                  f"cohort. Hysteresis is NOT available on this path: "
                                  f"a cohort held {h} months IS the hold band."
                                  if h > 1 else
                                  f"monthly top-{K}, the h=1 cohort and the "
                                  f"no-hysteresis hold band are the same book"))
                cells[key] = blk
                if len(ex):
                    fam_series[key] = ex
        log(f"    {name}: {len(COHORT_HORIZONS) * len(COSTS)} cohort cells")

    out["cells"] = cells
    out["family_size"] = len(cells)
    out["hysteresis_availability_note"] = (
        "`evaluate.book` takes hold_k; `evaluate.overlapping_book` does not. The "
        "mandate's rule (top-50 in, out below rank 100) therefore exists only on the "
        "hold-band path and is reported there. Presenting a cohort book as 'held with "
        "hysteresis' would be a lever that silently did nothing.")

    # ---- the family: Holm over every cell, DSR/MDE/PBO on the best
    ps = {k: (None if (v.get("PRIMARY_beta_matched") or {}).get("p_one_sided") is None
              else float(v["PRIMARY_beta_matched"]["p_one_sided"]))
          for k, v in cells.items()}
    ordered = sorted([(k, v) for k, v in ps.items() if v is not None], key=lambda kv: kv[1])
    n = len(ordered)
    holm, run_max = {}, 0.0
    for i, (k, p) in enumerate(ordered):
        adj = min(1.0, max(run_max, (n - i) * p))
        run_max = adj
        holm[k] = _r(adj)
    best = ordered[0][0] if ordered else None
    out["family"] = {
        "size": n,
        "definition": (f"{len(SELECTORS)} selectors x "
                       f"({len(HOLD_BANDS)} hold bands + {len(COHORT_HORIZONS)} cohort "
                       f"lengths) x {len(COSTS)} cost rates"),
        "family_min_p_one_sided": _r(ordered[0][1]) if ordered else None,
        "family_max_p_one_sided": _r(ordered[-1][1]) if ordered else None,
        "holm_adjusted": holm,
        "best_cell": best,
        "n_cells_surviving_holm_at_0_05": sum(
            1 for v in holm.values() if v is not None and v <= 0.05),
    }
    if best and best in fam_series:
        aligned = {k: v for k, v in fam_series.items() if len(v) == len(fam_series[best])}
        out["inference_on_the_best_cell"] = inference.full_report(
            fam_series[best].to_numpy(), family=aligned, n_trials=n, seed=20260907)
        pw = (out["inference_on_the_best_cell"].get("power") or {})
        mde = pw.get("mde_annual_excess_at_t_target")
        eff = abs(float(fam_series[best].mean()) * 12.0)
        out["scope_aware_verdict"] = {
            "best_cell": best,
            "observed_effect_annual": _r(eff),
            "mde_annual_at_t_2": _r(mde),
            "verdict": ("UNDERPOWERED, NOT NOISE" if (mde is not None and eff < float(mde))
                        else "SEPARATED FROM ZERO"
                        if (cells[best]["PRIMARY_beta_matched"].get("t_paired") or 0) >= 2
                        else "NOISE (powered for an effect this size and did not see it)"),
            "scope": ("251 months, 2004-01..2024-11, the $3m/day + $5 floored research "
                      "panel, top-50 vw. The BEST cell of a family of "
                      f"{n} -- its unadjusted p is the minimum of {n} draws and the "
                      "Holm column beside it is the number to quote."),
        }

    out["horizon_answer"] = _horizon_answer(cells)
    out["memory_free_gb_after"] = W3B.free_gb()
    out["headline"] = _headline(out)
    out["wall_seconds"] = round(time.perf_counter() - t0, 1)
    del df
    gc.collect()
    return out


def _horizon_answer(cells: dict) -> dict:
    """The one table the job exists to produce: annualised beta-matched excess by
    (selector x holding rule x cost). Derived from `cells`, never retyped."""
    rows: dict = {}
    for key, v in cells.items():
        if "PRIMARY_beta_matched" not in v:
            continue
        rows[key] = {
            "beta_matched_annualised_pct": v["PRIMARY_beta_matched"]["annualised_pct"],
            "t": v["PRIMARY_beta_matched"]["t_paired"],
            "raw_market_annualised_pct": v["SECONDARY_raw_market"]["annualised_pct"],
            "turnover": v["mean_turnover"],
            "implied_holding_months": v["implied_mean_holding_months"],
            "annual_cost_line_pct": v["annual_cost_line_pct"],
            "terminal_wealth_net": v["terminal_wealth_net"],
        }
    best_by_sel: dict = {}
    for sel in SELECTORS:
        sub = {k: v for k, v in rows.items() if f"|{sel}|" in k}
        for bps in COSTS:
            s2 = {k: v for k, v in sub.items() if k.endswith(f"|{int(bps)}bps")}
            if not s2:
                continue
            b = max(s2, key=lambda k: (s2[k]["beta_matched_annualised_pct"] or -9e9))
            best_by_sel[f"{sel}|{int(bps)}bps"] = {
                "best_cell": b, **s2[b],
                "beats_the_no_hysteresis_monthly_control_by_pp": _r(
                    (s2[b]["beta_matched_annualised_pct"] or 0)
                    - (rows.get(f"holdband|{sel}|hold_k=none|{int(bps)}bps", {})
                       .get("beta_matched_annualised_pct") or 0), 3),
            }
    # IS IT A CURVE OR ONE LUCKY CELL? The best cell is the maximum of a family
    # and its unadjusted p is worth nothing on its own. What IS worth something
    # is whether the whole ladder moves the same way, because a ladder that
    # improves at every rung is not a cell that was picked.
    robust: dict = {}
    for sel in SELECTORS:
        for bps in COSTS:
            ctrl = rows.get(f"holdband|{sel}|hold_k=none|{int(bps)}bps")
            if ctrl is None:
                continue
            ladder = {k: v for k, v in rows.items()
                      if k.startswith(f"holdband|{sel}|") and k.endswith(f"|{int(bps)}bps")
                      and "hold_k=none" not in k}
            beats = [k for k, v in ladder.items()
                     if (v["beta_matched_annualised_pct"] or -9e9)
                     > (ctrl["beta_matched_annualised_pct"] or -9e9)]
            robust[f"{sel}|{int(bps)}bps"] = {
                "control_beta_matched_annualised_pct": ctrl["beta_matched_annualised_pct"],
                "control_annual_cost_line_pct": ctrl["annual_cost_line_pct"],
                "rungs": len(ladder),
                "rungs_beating_the_control": len(beats),
                "all_rungs_beat_the_control": len(beats) == len(ladder),
                "by_rung": {k.split("|")[2]: v["beta_matched_annualised_pct"]
                            for k, v in sorted(ladder.items())},
            }
    return {
        "table": rows,
        "best_holding_rule_per_selector_and_cost": best_by_sel,
        "hold_band_ladder_robustness": robust,
        "reading": ("`beats_the_no_hysteresis_monthly_control_by_pp` is the number that "
                    "matters: it is what the holding rule bought over the book this "
                    "repo already trades. A best cell that beats the control by a "
                    "fraction of a point has answered the question NO. "
                    "`hold_band_ladder_robustness` is the guard against the opposite "
                    "error: a single winning rung is the maximum of a sweep, while a "
                    "ladder in which EVERY rung beats the control is a curve."),
    }


def _headline(out: dict) -> str:
    ha = out.get("horizon_answer") or {}
    best = ha.get("best_holding_rule_per_selector_and_cost") or {}
    fam = out.get("family") or {}
    bits = []
    for k in sorted(best):
        v = best[k]
        bits.append(f"{k}: best {v['best_cell'].split('|', 1)[1]} at "
                    f"{v['beta_matched_annualised_pct']}%/yr t {v['t']} "
                    f"(+{v['beats_the_no_hysteresis_monthly_control_by_pp']}pp over the "
                    f"monthly control)")
    return (f"family {fam.get('size')}, family-max p {fam.get('family_max_p_one_sided')}, "
            f"{fam.get('n_cells_surviving_holm_at_0_05')} cells survive Holm. "
            + " | ".join(bits))


def write(rec: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec["_provenance"] = {
        "sys_argv": list(sys.argv),
        "resolved_config": {
            "SELECTORS": SELECTORS, "COSTS": list(COSTS), "K": K,
            "HOLD_BANDS": [str(x) for x in HOLD_BANDS],
            "MANDATE_HOLD_K": MANDATE_HOLD_K,
            "COHORT_HORIZONS": list(COHORT_HORIZONS), "NW_LAG": NW_LAG,
            "receipt": str(RECEIPT),
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
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    try:
        rec = run(verbose=not a.quiet)
    except Exception as exc:                                            # noqa: BLE001
        rec = {"job": "A4_holding_cross", "lane": "A", "status": "CRASHED",
               "llm_spend_usd": 0.0, "llm_calls": 0,
               "error": f"{type(exc).__name__}: {exc}",
               "traceback": traceback.format_exc(),
               "headline": f"CRASHED: {type(exc).__name__}: {exc}"}
    p = write(rec)
    print(f"\n{rec.get('headline')}\n-> {p}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
