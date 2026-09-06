"""N1.4 -- IS MONTHLY REFIT STILL WORTH +5.7pp ONCE THE BOOK IS BROAD?

WHAT A2 SHOWED, AND THE HOLE IN IT
==================================
A2 (labor-day lane) measured the refit cadence on ONE construction -- the
top-50 value-weighted book -- and found monthly minus frozen-once at **+5.751pp
beta-matched, TW 27.17 vs 6.77.** N1 has since measured why that construction
is the wrong instrument: it has a transfer coefficient near 0.13 and about a
dozen effective names. A +5.7pp gap measured through an instrument that
expresses an eighth of the bet is not obviously the same gap the book we would
actually run would see.

So this job asks A2's question again, in N1's constructions. **Only the refit
clock varies.** Same features, same pipeline (`models.fit_predict_proba`, the
classifier head `run_lgbm_clf` uses), same floored universe, same folds rule.

THE CONTROL IS THE ANNUAL VINTAGE WE ALREADY OWN
================================================
`lgbm_clf` in the frozen W3b stage IS the annual-refit model, and A2's
reproduction gate proved it reproduces to float32 storage precision over
454,708 rows (max deviation 3e-08). Refitting it here would spend 47 seconds to
re-derive a column we can read, and would introduce a second object with the
same name -- so the control is READ, not refitted, and the gate that proves it
is quoted rather than re-run.

MEMORY, AND WHY THE PREDICTIONS ARE CACHED
==========================================
252 boundaries at ~2 s each is nine minutes of fitting that a memory guard can
interrupt at fit 200. The predictions are therefore flushed to a parquet every
`FLUSH_EVERY` fits and re-read on the next run, so an interrupted sweep is
RESUMED and not repeated. The cache is keyed by the universe fingerprint: a
different universe cannot silently reuse another one's predictions.

    python -m scripts.n1d_monthly_refit_books
    python -m scripts.n1d_monthly_refit_books --max-fits 24     # a bounded probe
"""

from __future__ import annotations

import argparse
import gc
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
    _month_windows, _window_leg)

OUT_DIR = REPO / "backend" / "data" / "optimus" / "night_lab_2026-09-07"
RECEIPT = OUT_DIR / "N1d_monthly_refit_books.json"
CACHE = OUT_DIR / "N1d_monthly_refit_predictions.parquet"
CACHE_META = OUT_DIR / "N1d_monthly_refit_predictions.meta.json"

#: This job's OWN memory floor. Lower than A2's 4.0 GB because the cache makes
#: an interruption cost one fit instead of the sweep -- the floor exists to
#: protect the machine, and A2's higher floor existed to protect work that is
#: now protected by the cache instead.
MIN_FREE_GB = 2.0
FLUSH_EVERY = 12


def _r(v, nd: int = 5):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, nd) if math.isfinite(f) else None


def _flush(preds: pd.Series, fingerprint: str) -> None:
    """Write the prediction cache AND the sidecar that makes it checkable."""
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"monthly": preds.to_numpy()}).to_parquet(CACHE, index=False)
    CACHE_META.write_text(json.dumps({
        "universe_fingerprint_sha256": fingerprint,
        "rows": int(len(preds)),
        "rows_predicted": int(preds.notna().sum()),
        "written_utc": datetime.now(timezone.utc).isoformat(),
    }, indent=1), encoding="utf-8")


def run(*, max_fits: int | None = None, verbose: bool = True) -> dict:
    from learner import benchmark as BM
    from learner import dataset as DS
    from learner import evaluate as E
    from learner import long_panel as LP
    from learner import models as M
    from learner import neural_long as N
    from scripts import labor_a2_retrain_cadence as A2
    from scripts import n1_construction_books as N1
    from scripts import w3_neural_floored as W3B

    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    t0 = time.perf_counter()
    tracker = RP.InputTracker()
    out: dict = {
        "job": "N1d_monthly_refit_books",
        "lane": "N1",
        "question": ("A2 measured the refit cadence on the top-50 VW book and found "
                     "+5.751pp for monthly. Does that survive N1's broad "
                     "constructions, where the transfer coefficient is three times "
                     "higher?"),
        "licence": "PRODUCT_EXPERIMENT",
        "what_varies": ("the REFIT CLOCK only. The annual control is the frozen W3b "
                        "stage column, whose equivalence to a re-run annual sweep A2 "
                        "proved over 454,708 rows at max deviation 3e-08."),
        "llm_spend_usd": 0.0, "llm_calls": 0, "network_calls": 0,
        "memory_free_gb_before": W3B.free_gb(),
        "memory_floor_gb": MIN_FREE_GB,
    }
    if not LP.LONG_TABLE.exists():
        out.update(status="SKIPPED", headline=f"SKIPPED: {LP.LONG_TABLE} is absent")
        return out

    log("  loading the floored universe ...")
    df, uni, fp = W3B.load_universe(verbose=False)
    df.attrs["_fingerprint"] = fp
    tracker.opened(LP.LONG_TABLE)
    out["universe_fingerprint_sha256"] = fp
    out["stage_control"] = N1._attach_stage(df, tracker)
    if "lgbm_clf" not in df.columns:
        out.update(status="REFUSED",
                   headline="REFUSED: the annual control column `lgbm_clf` is absent")
        return out

    feature_cols = DS.feature_columns()
    out["n_features"] = len(feature_cols) + 1

    # ---- the monthly predictions, resumed from cache where one exists
    preds = pd.Series(np.nan, index=df.index, dtype="float64")
    cached_rows, cache_note = 0, "no cache"
    if CACHE.exists() and CACHE_META.exists():
        try:
            meta = json.loads(CACHE_META.read_text(encoding="utf-8"))
            c = pd.read_parquet(CACHE)
            # A GATE THAT CANNOT FAIL IS A BROKEN GATE. parquet does not carry
            # `DataFrame.attrs`, so a fingerprint read back from the file would
            # always be None and the check would always pass -- which is how a
            # cache built on one universe gets served to another. The
            # fingerprint lives in a SIDECAR, and a mismatch refuses the cache.
            if meta.get("universe_fingerprint_sha256") != fp:
                cache_note = ("cache REFUSED: it was built on universe "
                              f"{str(meta.get('universe_fingerprint_sha256'))[:16]}, "
                              f"this run is {fp[:16]}")
            elif len(c) != len(df):
                cache_note = (f"cache REFUSED: {len(c):,} rows vs the panel's "
                              f"{len(df):,}")
            else:
                preds = pd.Series(c["monthly"].to_numpy(), index=df.index)
                cached_rows = int(preds.notna().sum())
                cache_note = f"resumed {cached_rows:,} rows from {CACHE.name}"
                tracker.opened(CACHE)
        except Exception as exc:                                    # noqa: BLE001
            cache_note = f"cache unreadable ({type(exc).__name__}); refitting"
    elif CACHE.exists():
        cache_note = "cache present but its sidecar is missing -- REFUSED, refitting"
    out["cache"] = cache_note

    notes, skipped, n_done = [], [], 0
    t_fit = time.perf_counter()
    for c, tr, te in A2.folds(df, "monthly"):
        if preds.loc[te].notna().all():
            continue                                    # already in the cache
        g = W3B.free_gb()
        if g is not None and g < MIN_FREE_GB:
            skipped.append({"cutoff": str(c.date()),
                            "why": f"free memory {g} GB below {MIN_FREE_GB} GB"})
            continue
        t1 = time.perf_counter()
        p, meta = M.fit_predict_proba(df.loc[tr], df.loc[te], feature_cols, 1)
        preds.loc[te] = p
        n_done += 1
        notes.append({"cutoff": str(c.date()), "n_train": int(len(tr)),
                      "n_test": int(len(te)),
                      "seconds": round(time.perf_counter() - t1, 2)})
        if n_done % FLUSH_EVERY == 0:
            _flush(preds, fp)
            log(f"    {n_done} fits, {round(time.perf_counter() - t_fit, 1)}s, "
                f"{int(preds.notna().sum()):,} rows")
        if max_fits is not None and n_done >= max_fits:
            break
        gc.collect()
    _flush(preds, fp)
    df["lgbm_clf_monthly"] = preds.astype("float32")
    out["refit"] = {
        "boundaries": len(A2.cutoffs("monthly")),
        "fits_this_run": n_done,
        "fits_from_cache": cached_rows > 0,
        "fits_skipped_for_memory": len(skipped),
        "skipped": skipped[:20],
        "rows_predicted": int(preds.notna().sum()),
        "coverage_vs_the_annual_control": _r(
            float(preds.notna().sum()) / max(1, int(df["lgbm_clf"].notna().sum())), 4),
        "wall_seconds": round(time.perf_counter() - t_fit, 1),
        "cache_path": str(CACHE),
    }
    # A COVERAGE GAP IS A FINDING, NOT A FOOTNOTE. If the monthly column covers
    # materially fewer rows than the annual one, the two books are not being
    # compared on the same tape and the delta is partly a sample difference.
    cov = out["refit"]["coverage_vs_the_annual_control"] or 0.0
    out["comparability"] = (
        "COMPARABLE" if cov >= 0.98 else
        f"CANNOT DETERMINE -- the monthly column covers {cov:.1%} of the annual "
        "column's rows; the delta below is contaminated by a sample difference")

    # ---- the risk-free leg
    months_all = pd.Index(sorted(df["month"].dropna().unique()))
    try:
        rf_d = BM.cash().returns.dropna().astype("float64")
        rf, rf_note = _window_leg(rf_d, _month_windows(df), months_all)
        rf_note["source"] = "learner.benchmark.cash() -- pinned FF daily RF, OFFLINE"
    except Exception as exc:                                        # noqa: BLE001
        rf = pd.Series(0.0, index=months_all)
        rf_note = {"available": False, "why": f"{type(exc).__name__}: {exc}"}
    out["risk_free_leg"] = rf_note

    # ---- the same six constructions, both cadences
    log("  grading both cadences in every N1 construction ...")
    cells, fam = {}, {}
    for cad, col in (("annual", "lgbm_clf"), ("monthly", "lgbm_clf_monthly")):
        for (k, wgt, hk) in N1.CONSTRUCTIONS:
            for bps in N1.COSTS:
                key = f"{cad}|k={k}|{wgt}|hold={hk or 'none'}|{int(bps)}bps"
                bk = E.book(df, col, k=k, weight=wgt, cost_bps=bps,
                            ret_col="fwd_1m", mkt_col="mkt_vw_1m",
                            tradable_floor=N.TRADABLE_FLOOR_USD, hold_k=hk,
                            return_series=True, return_weights=True)
                blk, ex = N1.grade(bk, rf, label=key, df=df, pred_col=col,
                                   construction=f"top-{k} {wgt}"
                                                + (f", hold until rank > {hk}" if hk
                                                   else ", rebuilt monthly (control)"))
                cells[key] = blk
                if len(ex):
                    fam[key] = ex
        gc.collect()
    out["cells"] = cells

    deltas = {}
    for (k, wgt, hk) in N1.CONSTRUCTIONS:
        for bps in N1.COSTS:
            suffix = f"k={k}|{wgt}|hold={hk or 'none'}|{int(bps)}bps"
            a, b = fam.get(f"monthly|{suffix}"), fam.get(f"annual|{suffix}")
            if a is None or b is None:
                continue
            aa, bb = a.align(b, join="inner")
            d = (aa - bb).dropna()
            if len(d) < 3:
                continue
            t = N1._t(d)
            fl = (cells.get(f"monthly|{suffix}", {}).get("fundamental_law") or {})
            deltas[suffix] = {
                "months_paired": int(len(d)),
                "monthly_minus_annual_pp_per_year": _r(float(d.mean()) * 12 * 100, 3),
                "t_paired": _r(t, 3),
                "p_one_sided": N1._p_one_sided(t),
                "transfer_coefficient": (fl.get("transfer_coefficient") or {}).get("tc"),
                "effective_names": (fl.get("effective_breadth") or {}).get(
                    "mean_effective_names_per_month"),
                "terminal_wealth_monthly": cells[f"monthly|{suffix}"].get("terminal_wealth_net"),
                "terminal_wealth_annual": cells[f"annual|{suffix}"].get("terminal_wealth_net"),
            }
    out["monthly_minus_annual"] = deltas
    dp = {k: v["p_one_sided"] for k, v in deltas.items() if v.get("p_one_sided") is not None}
    adj = N1.holm(dp)
    best = min(dp, key=lambda k: dp[k]) if dp else None
    vals = [v["monthly_minus_annual_pp_per_year"] for v in deltas.values()
            if v.get("monthly_minus_annual_pp_per_year") is not None]
    out["family"] = {
        "size": len(dp),
        "constructions_where_monthly_wins": int(sum(1 for x in vals if x > 0)),
        "constructions_total": len(vals),
        "median_pp_per_year": _r(float(np.median(vals)), 3) if vals else None,
        "family_min_p": _r(min(dp.values()), 6) if dp else None,
        "family_max_p": _r(max(dp.values()), 6) if dp else None,
        "best": best, "best_holm_adjusted_p": adj.get(best) if best else None,
        "surviving_holm_at_0.05": sorted(k for k, v in adj.items() if v <= 0.05),
    }
    ctrl = deltas.get(f"k=50|vw|hold=none|10bps") or {}
    broad = deltas.get(f"k=300|ew|hold=600|10bps") or {}
    out["A2_comparison"] = {
        "A2_reported_on_the_top50_VW_book_pp": 5.751,
        "A2_baseline": "frozen_once (fitted in 2004 and never touched again)",
        "this_job_baseline": "annual refit -- the incumbent's actual clock, NOT frozen",
        "note": ("A2's +5.751pp is monthly MINUS FROZEN. The number below is monthly "
                 "MINUS ANNUAL, which is the decision actually on the table: nobody "
                 "proposes freezing a model for twenty years. The two are not the "
                 "same quantity and must not be quoted as if they were."),
        "top50_vw_10bps": ctrl.get("monthly_minus_annual_pp_per_year"),
        "broad_300_ew_10bps": broad.get("monthly_minus_annual_pp_per_year"),
    }
    out["memory_free_gb_after"] = W3B.free_gb()
    out["wall_seconds"] = round(time.perf_counter() - t0, 1)
    out["headline"] = (
        f"monthly minus ANNUAL refit: wins in "
        f"{out['family']['constructions_where_monthly_wins']} of "
        f"{out['family']['constructions_total']} constructions, median "
        f"{out['family']['median_pp_per_year']}pp/yr, best Holm "
        f"{out['family']['best_holm_adjusted_p']}; top-50 VW "
        f"{ctrl.get('monthly_minus_annual_pp_per_year')}pp vs broad 300 EW "
        f"{broad.get('monthly_minus_annual_pp_per_year')}pp. {out['comparability']}")
    RP.attach(out, sys.argv,
              {"min_free_gb": MIN_FREE_GB, "flush_every": FLUSH_EVERY,
               "max_fits": max_fits}, tracker)
    return out


def write(rec: dict, path: Path = RECEIPT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rec["generated_utc"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-fits", type=int, default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    path = Path(a.out) if a.out else RECEIPT
    try:
        rec = run(max_fits=a.max_fits)
    except Exception:                                               # noqa: BLE001
        rec = {"job": "N1d_monthly_refit_books", "status": "FAILED",
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
