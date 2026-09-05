"""W3b -- THE NEURAL ARM WITH THE TRADABLE FLOOR ON THE **TRAINING** UNIVERSE.

WHAT W3 ACTUALLY ASKED, AND WHY IT WAS THE WRONG QUESTION
========================================================
`W3_neural_long_run13_v0.json` reported a best cell with terminal wealth
**698.9x** against a market of 14.4x, and then `_neural_floor_check` cut it to
**64.9x** by restricting the BOOK to names trading $3m a day above $5. The
weekend's summary recorded that honestly and concluded "does NOT beat lgbm".

But both numbers came from a model **fitted on all 925,757 panel rows**. The
floor was a grading filter bolted on afterwards. So the question W3 answered was
*"what happens to a microcap-trained ranking when you are forbidden to buy
microcaps?"* -- and the answer to that ("it loses most of its edge") is not the
answer to the question a desk asks, which is *"if I fit on what I can trade,
rank what I can trade and buy what I can trade, do I beat my incumbent?"*

This job asks that one. `neural_long.tradable_universe` applies
`evaluate.TRADABLE_DOLLAR_VOL` ($3m/day) and `neural_long.TRADABLE_MIN_CLOSE`
($5) to the panel BEFORE `walk_forward_splits` sees it, so the same 530k-row
universe is what the impute/scale/clip pipeline is fitted on, what the
self-supervised pass reconstructs, what the inner temporal holdout stops
training against, what the incumbents are fitted on, and what the book is graded
on. Nothing downstream can see a name the desk could not have bought.

The direction of the effect is genuinely unknown in advance: the floored panel
is 57.3% of the rows (less tape, and this repo's binding constraint has been
tape every single time) but every gradient step is spent on the distribution the
book is scored against. That is why it is worth one run and not an argument.

THE INCUMBENT IS NOT OPTIONAL, AND THERE ARE TWO OF THEM
=======================================================
`lgbm_clf` (the classifier head, `models.fit_predict_proba`) is the baseline the
mandate names -- S36 recorded it as the only model left standing on half the
panel. `lgbm` (the regression head) is W3's own incumbent and is kept so this
receipt is comparable with run13. **Both are re-fitted on the floored universe
on the same folds**, and the decision rule below requires beating BOTH: the
challenger does not get to pick whichever incumbent it happens to be ahead of.

WHAT IS DECLARED BEFORE THE RESULT
==================================
`DECISION_RULE` below, and `--declare` writes it to the receipt path with a
sha256 BEFORE the run starts. The full receipt carries the same text and the
same hash, so "we decided the bar after we saw the number" is checkable rather
than promised. The rule is judged on the SEED-MEAN ENSEMBLE, never on the best
cell: the best cell is the maximum of an eight-seed draw and nobody can pick it
in advance.

Run it with the CUDA interpreter (`requirements-gpu.txt`):

    & "$env:LOCALAPPDATA\\Programs\\Python\\Python312\\python.exe" -m scripts.w3_neural_floored --declare
    & "$env:LOCALAPPDATA\\Programs\\Python\\Python312\\python.exe" -m scripts.w3_neural_floored
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:                       # so `python scripts/...` works too
    sys.path.insert(0, str(REPO))

from learner import benchmark as BM                                    # noqa: E402
from learner import evaluate, inference                                # noqa: E402
from learner import long_panel as LP                                   # noqa: E402
from learner import neural_long as N                                   # noqa: E402

OUT_DIR = REPO / "backend" / "data" / "optimus" / "continuation_2026-09-06"
RECEIPT = OUT_DIR / "W3b_neural_floored_run01.json"
DECLARATION = OUT_DIR / "W3b_neural_floored_run01_declaration.json"

#: The two arms. `supervised` is W3's champion architecture; `pretrained` is run
#: at the CAUSAL scope ONLY -- the `all` scope is a named look-ahead in
#: `neural_long`, a claim may not be made from it, and carrying it would add
#: eight untradeable cells to a family the tradeable cells have to pay for.
ARMS: tuple[dict, ...] = (
    {"tag": "nn", "width": "base", "pretrain": None,
     "why": "W3's variant 0 -- the architecture that produced run13's champion"},
    {"tag": "nn_pre_causal", "width": "base", "pretrain": "causal",
     "why": "masked-feature self-supervised pre-training, strictly point-in-time; "
            "the plausible way a smaller floored training set is compensated"},
)

#: MEMORY DISCIPLINE. Five other agents share this laptop. A pass that starts
#: with less than this free is REFUSED rather than allowed to swap the machine
#: to a halt in the middle of a 21-fold loop.
MIN_FREE_GB = 6.0

DECISION_RULE = {
    "declared": "BEFORE the run, by --declare, and hashed",
    "question": "does the neural arm, FITTED on the tradable universe, beat the "
                "LightGBM incumbents fitted on the same universe on the same folds?",
    "the_object_judged": (
        "the SEED-MEAN ENSEMBLE of each arm over the eight declared seeds -- never "
        "the best cell. The best cell is the maximum of an 8-seed draw and is not "
        "choosable in advance; reporting it as the result would publish a number no "
        "desk could have selected."),
    "incumbents": ["lgbm_clf (models.fit_predict_proba -- the baseline the mandate "
                   "names; mandatory)",
                   "lgbm (models.fit_predict regression head -- W3's own incumbent)"],
    "beats_requires_ALL_of": [
        "(a) the paired monthly net-return difference (ensemble minus incumbent) has "
        "a POSITIVE mean against BOTH incumbents at 10 bps AND at 25 bps",
        "(b) the family-corrected inference on the ensemble-minus-lgbm_clf difference "
        "series clears DSR >= 0.95 AND SPA p <= 0.10 AND PBO < 0.5 "
        "(learner.neural_long._beats_incumbent), with the family = every cell this "
        "job looked at across BOTH arms and BOTH cost rates",
        "(c) the ensemble's terminal wealth net exceeds BOTH incumbents' over the "
        "same months at 10 bps",
        "(d) the sign of the ensemble-minus-lgbm_clf monthly difference is positive "
        "in >= 2 of the 3 eras",
    ],
    "evaluated_on": "each arm's ensemble independently; the neural arm 'beats' if at "
                    "least ONE ensemble satisfies all four. Both shots are paid for "
                    "in (b), whose family spans both arms.",
    "if_it_does_NOT_beat": (
        "write B10_not_earned = true into this receipt, say so plainly in the "
        "headline, STOP THE NEURAL LOOP. Do not soften it, do not re-cut the "
        "universe until it passes, do not promote the best cell instead."),
    "if_it_DOES_beat": (
        "freeze ONE champion -- named arm + width + the seed-mean-over-the-eight-"
        "declared-seeds policy, no seed selection -- and set up shadow accrual via "
        "learner/shadow.py. Nothing sealed, ordered, deployed or pushed either way."),
    "not_a_get_out": (
        "an UNDERPOWERED verdict on the market leg does not convert a failure to "
        "beat the incumbent into a pass. The incumbent leg is a PAIRED difference "
        "on the same months and does not depend on the market leg's power."),
}


def _rule_sha() -> str:
    return hashlib.sha256(
        json.dumps(DECISION_RULE, sort_keys=True).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------- memory

def free_gb() -> float | None:
    """Physical memory available, in GB. None off Windows rather than a guess."""
    try:
        class _MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = _MS()
        m.dwLength = ctypes.sizeof(_MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))    # type: ignore[attr-defined]
        return round(m.ullAvailPhys / 2 ** 30, 2)
    except Exception:                                                   # noqa: BLE001
        return None


# ---------------------------------------------------------------- the grading

def grade(df: pd.DataFrame, col: str, bps: float) -> dict:
    """Book the column, WITH the floor passed again at grading.

    The panel is already floored, so `tradable_floor` here must remove nothing.
    That is the point: `rows_after_tradable_floor` in the receipt is the proof
    that the training-universe filter was at least as tight as the grading one,
    and a non-zero difference would say the two disagree.
    """
    return evaluate.book(df, col, k=50, weight="vw", cost_bps=bps,
                         ret_col="fwd_1m", mkt_col="mkt_vw_1m",
                         tradable_floor=N.TRADABLE_FLOOR_USD, return_series=True)


def _t(series: pd.Series) -> float | None:
    s = pd.Series(series).dropna()
    if len(s) < 3 or s.std(ddof=1) <= 0:
        return None
    return round(float(s.mean() / (s.std(ddof=1) / np.sqrt(len(s)))), 3)


def _diff_block(a: pd.Series, b: pd.Series) -> tuple[pd.Series | None, dict]:
    common = a.index.intersection(b.index)
    if len(common) < 12:
        return None, {"months": int(len(common)), "note": "fewer than 12 common months"}
    d = (a.loc[common] - b.loc[common]).astype("float64")
    mu = float(d.mean())
    return d, {"months": int(len(d)),
               "mean_monthly_pct": round(mu * 100, 4),
               "annualised_pct": round(mu * 12 * 100, 3),
               "t_paired": _t(d),
               "months_ahead": round(float((d > 0).mean()), 4)}


# ------------------------------------------------------------------- the run

def run(*, seeds: list[int], test_years: list[int], verbose: bool = True) -> dict:
    from scripts.weekend_lab_jobs import era_sign_table          # READ ONLY import
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    t0 = time.perf_counter()

    out: dict = {
        "job": "W3b_neural_floored",
        "question": ("with the $3m/day + $5 tradable floor applied to the TRAINING "
                     "universe as well as the graded book, does the neural arm beat "
                     "lgbm_clf (and lgbm) on the same walk-forward folds, after the "
                     "multiplicity family?"),
        "decision_rule_declared_before_the_result": DECISION_RULE,
        "decision_rule_sha256": _rule_sha(),
        "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0,
        "llm_calls": 0,
    }
    if DECLARATION.exists():
        try:
            dec = json.loads(DECLARATION.read_text(encoding="utf-8"))
            out["declaration"] = {
                "path": str(DECLARATION.relative_to(REPO)),
                "declared_utc": dec.get("declared_utc"),
                "sha256_in_declaration": dec.get("decision_rule_sha256"),
                "matches_the_rule_in_this_receipt":
                    dec.get("decision_rule_sha256") == out["decision_rule_sha256"],
            }
        except Exception as exc:                                        # noqa: BLE001
            out["declaration"] = {"error": f"{type(exc).__name__}: {exc}"}
    else:
        out["declaration"] = {"verdict": "CANNOT DETERMINE",
                              "why": "no pre-run declaration file was written"}

    fg = free_gb()
    out["memory_before"] = {"free_gb": fg, "floor_gb": MIN_FREE_GB}
    if fg is not None and fg < MIN_FREE_GB:
        out["verdict"] = "REFUSED"
        out["headline"] = (f"REFUSED: {fg} GB free, below the {MIN_FREE_GB} GB floor. "
                           "Five agents share this laptop; a 21-fold loop that swaps "
                           "produces a receipt nobody can time and may take the other "
                           "jobs down with it. Nothing was fitted.")
        return out

    device, dev = N.resolve_device()
    out["device"] = dev
    out["python_executable"] = dev.get("python_executable")
    if dev.get("device_actually_used") != "cuda":
        out["device_headline_warning"] = (
            "THIS RUN WAS NOT ON THE GPU. " + str(dev.get("device_warning")))
    log(f"device: {dev.get('device_actually_used')} ({dev.get('device_name')}) "
        f"torch {dev.get('torch_version')} on {dev.get('python_executable')}")

    # ---- THE UNIVERSE, floored BEFORE anything is fitted
    panel = LP.load_long()
    df, uni = N.tradable_universe(panel)
    del panel
    out["training_universe"] = uni
    log(f"universe: {uni['rows_before']:,} -> {uni['rows_after']:,} rows "
        f"({uni['share_kept']:.1%}), {uni['months_after']} months, "
        f"median {uni['median_names_per_month_after']:.0f} names/month")

    out["benchmark_stamp"] = BM.declare(
        "vw_crsp_common_main",
        construction="value-weighted total-return index of the panel's own CRSP "
                     "common-share universe, carried on every row as `mkt_vw_1m` "
                     "and consumed by learner.evaluate.book as `mkt_col`. The "
                     "benchmark is the FULL universe and is deliberately NOT "
                     "re-cut to the tradable slice: restricting what we may buy "
                     "must not also lower the bar we are measured against.",
        freq="M", span=[str(df["month"].min()), str(df["month"].max())],
        n_periods=int(df["month"].nunique()))
    ok, why = BM.validate_stamp(out["benchmark_stamp"])
    out["benchmark_stamp_valid"] = {"ok": bool(ok), "why": why}

    out["seeds"] = [int(s) for s in seeds]
    out["test_years"] = [int(test_years[0]), int(test_years[-1])]
    out["arms"] = list(ARMS)

    # ---- the neural arms
    runs: dict = {}
    pred_cols: dict[str, str] = {}
    for arm in ARMS:
        log(f"  arm {arm['tag']} (width {arm['width']}, pretrain {arm['pretrain']})")
        preds, rec = N.run_neural(df, test_years, seeds=seeds, width=arm["width"],
                                  pretrain_scope=arm["pretrain"], device=device,
                                  device_info=dev, verbose=verbose)
        runs[arm["tag"]] = rec
        for key, s in preds.items():
            col = f"{arm['tag']}_{key}"
            df[col] = s.to_numpy()
            pred_cols[col] = arm["tag"]
        member = [f"{arm['tag']}_s{int(s)}" for s in seeds]
        member = [c for c in member if c in df.columns]
        if len(member) > 1:
            col = f"{arm['tag']}_seedmean"
            df[col] = df[member].mean(axis=1, skipna=False)
            pred_cols[col] = arm["tag"]
        del preds

    # ---- the incumbents, on the SAME floored folds
    log("  lgbm_clf on the same folds ...")
    clf_pred, clf_rec = N.run_lgbm_clf(df, test_years, verbose=verbose)
    df["lgbm_clf"] = clf_pred.to_numpy()
    log("  lgbm (regression) on the same folds ...")
    reg_pred, reg_rec = N.run_lgbm(df, test_years, verbose=verbose)
    df["lgbm_raw"] = reg_pred.to_numpy()
    runs["lgbm_clf"] = clf_rec
    runs["lgbm_raw"] = reg_rec
    del clf_pred, reg_pred

    INCUMBENTS = ("lgbm_clf", "lgbm_raw")

    # ---- grade every cell at both cost rates
    cells, ex_series, net_series = {}, {}, {}
    for col in list(pred_cols) + list(INCUMBENTS):
        for bps in N.COSTS:
            key = f"{col}|{int(bps)}bps"
            try:
                bk = grade(df, col, bps)
            except Exception as exc:                                    # noqa: BLE001
                cells[key] = {"error": f"{type(exc).__name__}: {exc}"}
                continue
            ser = bk.pop("_series", {}) or {}
            cells[key] = {k: v for k, v in bk.items() if not k.startswith("_")}
            netv, mkt = ser.get("net"), ser.get("market")
            if netv is not None and mkt is not None and len(netv) \
                    and netv.index.equals(mkt.index):
                ex_series[key] = (netv - mkt).astype("float64")
                net_series[key] = netv.astype("float64")
    out["cells"] = cells
    out["cells_looked_at"] = len(cells)

    # the no-op proof: the grading floor removed nothing, because the training
    # universe was already at least as tight.
    any_cell = next((v for v in cells.values() if "rows_after_tradable_floor" in v), {})
    out["floor_at_grading_is_a_noop"] = {
        "rows_after_tradable_floor_at_grading": any_cell.get("rows_after_tradable_floor"),
        "reading": "the panel handed to evaluate.book was already floored, so the "
                   "grading floor can only confirm it. If these ever disagree the "
                   "training universe was NOT the graded universe.",
    }

    neural_keys = [k for k in ex_series if not k.startswith(("lgbm_clf|", "lgbm_raw|"))]
    if not neural_keys or f"lgbm_clf|10bps" not in ex_series:
        out["verdict"] = "CANNOT DETERMINE"
        out["headline"] = "no usable paired series on one of the legs"
        out["runs"] = runs
        return out

    # ---- LEG 1: against the MARKET. Family = every cell, both arms, both rates.
    wide = pd.concat({k: ex_series[k] for k in ex_series}, axis=1).dropna()
    fam = {k: wide[k].tolist() for k in wide.columns}
    best = max(neural_keys, key=lambda k: float(np.mean(fam[k])))
    inf_mkt = inference.full_report(fam[best], family=fam, paired_excess=fam,
                                    n_trials=len(cells), n_boot=500, seed=17)
    out["n_common_months"] = int(len(wide))
    out["common_window"] = [str(wide.index[0]), str(wide.index[-1])]
    out["best_cell"] = best
    out["best_cell_book"] = cells.get(best)
    out["best_mean_monthly_excess_pct"] = round(float(np.mean(fam[best])) * 100, 4)
    out["inference_vs_market"] = inf_mkt
    out["era_sign_table_best_cell"] = era_sign_table(wide[best])

    # ---- LEG 2: against each incumbent, PAIRED month by month at the same rate
    vs: dict = {}
    for inc in INCUMBENTS:
        diff_fam, diff_cells = {}, {}
        for k in neural_keys:
            bps = k.rsplit("|", 1)[-1]
            lk = f"{inc}|{bps}"
            if lk not in net_series:
                continue
            d, blk = _diff_block(net_series[k], net_series[lk])
            diff_cells[k] = blk
            if d is not None:
                diff_fam[k] = d
        inf_inc, best_vs = {}, None
        if diff_fam:
            wd = pd.concat(diff_fam, axis=1).dropna()
            if len(wd) >= 12:
                dfam = {k: wd[k].tolist() for k in wd.columns}
                best_vs = max(dfam, key=lambda k: float(np.mean(dfam[k])))
                inf_inc = inference.full_report(dfam[best_vs], family=dfam,
                                                paired_excess=dfam,
                                                n_trials=len(cells), n_boot=500, seed=23)
        vs[inc] = {
            "incumbent_book_10bps": cells.get(f"{inc}|10bps"),
            "incumbent_book_25bps": cells.get(f"{inc}|25bps"),
            "per_cell": diff_cells,
            "best_cell_vs_incumbent": best_vs,
            "inference_on_the_difference": inf_inc,
            "bar": N._beats_incumbent(inf_inc),
            "note": "paired MONTHLY difference of the two books' NET returns at the "
                    "same cost rate on the months both exist. Two terminal wealths "
                    "are one draw of a correlated pair.",
            "_diff_fam": diff_fam,          # popped before writing
        }
    out["vs_incumbents"] = vs

    # ---- the seed spread and the ensembles
    spread = {}
    for arm in ARMS:
        for bps in N.COSTS:
            keys = [f"{arm['tag']}_s{int(s)}|{int(bps)}bps" for s in seeds]
            ens = f"{arm['tag']}_seedmean|{int(bps)}bps"
            spread[f"{arm['tag']}|{int(bps)}bps"] = {
                "per_seed_cells": keys,
                "annualised_excess_vs_market": N._spread(
                    {k: (cells.get(k) or {}).get("annualised_excess") for k in keys}),
                "terminal_wealth_net": N._spread(
                    {k: (cells.get(k) or {}).get("terminal_wealth_net") for k in keys}),
                "t_paired_vs_market": N._spread(
                    {k: (cells.get(k) or {}).get("t_stat_paired_vs_market") for k in keys}),
                "vs_lgbm_clf_annualised_pct": N._spread(
                    {k: ((vs["lgbm_clf"]["per_cell"].get(k) or {}).get("annualised_pct"))
                     for k in keys}),
                "seed_mean_ensemble": {
                    "cell": ens,
                    "annualised_excess": (cells.get(ens) or {}).get("annualised_excess"),
                    "terminal_wealth_net": (cells.get(ens) or {}).get("terminal_wealth_net"),
                    "t_paired_vs_market": (cells.get(ens) or {}).get("t_stat_paired_vs_market"),
                    "vs_lgbm_clf_annualised_pct": (
                        vs["lgbm_clf"]["per_cell"].get(ens) or {}).get("annualised_pct"),
                    "vs_lgbm_raw_annualised_pct": (
                        vs["lgbm_raw"]["per_cell"].get(ens) or {}).get("annualised_pct"),
                },
            }
    out["seed_spread"] = spread

    # ---- robustness on the cells the receipt names
    rob_cols = {best.rsplit("|", 1)[0], "lgbm_clf", "lgbm_raw"}
    rob_cols |= {f"{a['tag']}_seedmean" for a in ARMS}
    out["robustness"] = {c: N.robustness(df, c) for c in sorted(rob_cols)
                         if c in df.columns}

    # ---- THE DECLARED RULE, applied
    checks: dict = {}
    for arm in ARMS:
        ens_col = f"{arm['tag']}_seedmean"
        ens10, ens25 = f"{ens_col}|10bps", f"{ens_col}|25bps"
        a_pos, a_detail = True, {}
        for inc in INCUMBENTS:
            for cell in (ens10, ens25):
                blk = vs[inc]["per_cell"].get(cell) or {}
                m = blk.get("annualised_pct")
                a_detail[f"{cell}_vs_{inc}"] = m
                if not (isinstance(m, (int, float)) and m > 0):
                    a_pos = False
        b_ok = bool(vs["lgbm_clf"]["bar"].get("clears"))
        tw_ens = (cells.get(ens10) or {}).get("terminal_wealth_net")
        tw_inc = {i: (cells.get(f"{i}|10bps") or {}).get("terminal_wealth_net")
                  for i in INCUMBENTS}
        c_ok = bool(isinstance(tw_ens, (int, float))
                    and all(isinstance(v, (int, float)) and tw_ens > v
                            for v in tw_inc.values()))
        d_series = vs["lgbm_clf"]["_diff_fam"].get(ens10)
        d_eras = era_sign_table(d_series) if d_series is not None else {
            "verdict": "CANNOT DETERMINE", "why": "no paired difference series"}
        d_ok = bool(d_eras.get("holds_in_2_of_3")
                    and d_eras.get("dominant_sign") == 1)
        checks[arm["tag"]] = {
            "a_positive_mean_vs_both_incumbents_at_both_cost_rates": {
                "pass": a_pos, "annualised_pct_by_pair": a_detail},
            "b_family_corrected_vs_lgbm_clf": {
                "pass": b_ok, **{k: v for k, v in vs["lgbm_clf"]["bar"].items()
                                 if k != "clears"}},
            "c_terminal_wealth_ahead_of_both_at_10bps": {
                "pass": c_ok, "ensemble": tw_ens, "incumbents": tw_inc},
            "d_sign_in_2_of_3_eras_vs_lgbm_clf": {
                "pass": d_ok, "era_table": d_eras},
            "ALL_FOUR": bool(a_pos and b_ok and c_ok and d_ok),
        }
    beats = any(v["ALL_FOUR"] for v in checks.values())
    out["decision"] = {
        "rule_sha256": out["decision_rule_sha256"],
        "checks_by_arm": checks,
        "beats_the_incumbent": beats,
        "B10_not_earned": (not beats),
    }
    if not beats:
        out["decision"]["what_happens_now"] = (
            "B10 NOT EARNED. The neural loop stops here. No champion is frozen, no "
            "shadow accrual is started, and the best cell is NOT promoted in the "
            "ensemble's place.")
    else:
        out["decision"]["champion"] = {
            "arm": next(k for k, v in checks.items() if v["ALL_FOUR"]),
            "width": "base",
            "horizon_months": N.HORIZON,
            "seed_policy": f"seed-mean over exactly these eight seeds: {list(seeds)} "
                           "-- NO seed selection, the ensemble is the object",
            "target": f"excess_vw_{N.HORIZON}m, standardised on train, clipped +/-"
                      f"{N.TARGET_CLIP_SD} sd",
            "universe": "tradable_universe($3m/day, close >= $5) applied to fit AND grade",
            "book": "top-50 value-weighted, monthly, 10 bps/side",
            "status": "SHADOW ONLY -- nothing sealed, ordered or deployed",
        }

    # ---- verdict + headline
    from scripts.weekend_lab_jobs import verdict_from
    base = verdict_from(inf_mkt, out["era_sign_table_best_cell"])
    if base == "NOVEL" and not beats:
        verdict = "NOISE (clears the market bar, does NOT beat the incumbents)"
    elif base == "NOVEL":
        verdict = "NOVEL"
    else:
        verdict = base
    out["verdict"] = verdict

    pw = inf_mkt.get("power", {}) or {}
    e10 = {a["tag"]: (cells.get(f"{a['tag']}_seedmean|10bps") or {}) for a in ARMS}
    clf10 = cells.get("lgbm_clf|10bps") or {}
    reg10 = cells.get("lgbm_raw|10bps") or {}
    ens_line = "; ".join(
        f"{t} ensemble TW {v.get('terminal_wealth_net')} "
        f"({v.get('annualised_excess')}/yr vs market, t {v.get('t_stat_paired_vs_market')})"
        for t, v in e10.items())
    out["headline"] = (
        f"[{dev.get('device_actually_used')}] FLOORED TRAINING UNIVERSE "
        f"({uni['rows_after']:,} of {uni['rows_before']:,} rows, "
        f"${N.TRADABLE_FLOOR_USD:,.0f}/day and close >= ${N.TRADABLE_MIN_CLOSE:.0f}): "
        f"{ens_line}. Incumbents on the same folds: lgbm_clf TW "
        f"{clf10.get('terminal_wealth_net')}, lgbm TW {reg10.get('terminal_wealth_net')}, "
        f"market {clf10.get('terminal_wealth_market_same_months')}. Best of "
        f"{len(cells)} cells is {best} ({out['best_mean_monthly_excess_pct']:+.3f}%/mo); "
        f"DSR {(inf_mkt.get('deflated_sharpe') or {}).get('dsr')}, SPA p "
        f"{(inf_mkt.get('spa') or {}).get('p_spa_consistent')}, PBO "
        f"{(inf_mkt.get('pbo') or {}).get('pbo')}, t2 needs "
        f"{pw.get('years_needed_for_t2')}y vs {pw.get('years_observed')}y observed, "
        f"MDE {pw.get('mde_annual_excess_at_t_target')}. "
        + ("B10 NOT EARNED -- the neural loop stops."
           if not beats else "The rule was met; one champion is frozen, shadow only."))

    out["runs"] = runs
    out["memory_after"] = {"free_gb": free_gb()}
    out["wall_seconds"] = round(time.perf_counter() - t0, 1)
    out["generated_utc"] = datetime.now(timezone.utc).isoformat()
    for inc in INCUMBENTS:                       # series are not JSON, and are big
        vs[inc].pop("_diff_fam", None)
    return out


# ------------------------------------------------------------------- the CLI

def declare() -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    body = {
        "job": "W3b_neural_floored",
        "status": "DECLARED -- written BEFORE the run, so the bar cannot be moved after",
        "declared_utc": datetime.now(timezone.utc).isoformat(),
        "decision_rule_declared_before_the_result": DECISION_RULE,
        "decision_rule_sha256": _rule_sha(),
        "arms": list(ARMS),
        "seeds": [N.SEED_BASE + i for i in range(N.N_SEEDS)],
        "receipt_path": str(RECEIPT.relative_to(REPO)),
    }
    DECLARATION.write_text(json.dumps(body, indent=1, default=str), encoding="utf-8")
    return DECLARATION


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--declare", action="store_true",
                    help="write the decision rule to disk BEFORE the run, then exit")
    ap.add_argument("--seeds", type=int, default=N.N_SEEDS)
    ap.add_argument("--first-year", type=int, default=N.FIRST_TEST_YEAR)
    ap.add_argument("--last-year", type=int, default=N.LAST_TEST_YEAR)
    ap.add_argument("--out", default=str(RECEIPT))
    a = ap.parse_args(argv)

    if a.declare:
        p = declare()
        print(f"declared -> {p} (sha {_rule_sha()[:16]})")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    seeds = [N.SEED_BASE + i for i in range(a.seeds)]
    years = list(range(a.first_year, a.last_year + 1))
    try:
        res = run(seeds=seeds, test_years=years)
    except BaseException as exc:                                        # noqa: BLE001
        # A TRACEBACK IS A RECEIPT. A job that dies without one leaves the reader
        # unable to tell a crash from a job that was never started.
        import traceback
        res = {"job": "W3b_neural_floored", "verdict": "FAILED",
               "decision_rule_declared_before_the_result": DECISION_RULE,
               "decision_rule_sha256": _rule_sha(),
               "error": f"{type(exc).__name__}: {exc}",
               "traceback": traceback.format_exc(),
               "python_executable": sys.executable,
               "generated_utc": datetime.now(timezone.utc).isoformat(),
               "headline": f"W3b FAILED: {type(exc).__name__}: {exc}"}
        Path(a.out).write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
        print(res["headline"])
        raise
    Path(a.out).write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(f"\n{res.get('verdict')} -- {res.get('headline')}")
    print(f"receipt -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
