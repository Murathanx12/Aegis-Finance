"""N1 -- DOES THE IC BECOME MONEY ONCE THE CONSTRUCTION STOPS DESTROYING IT?

THE NIGHT'S ONE QUESTION, AND WHY IT IS A CONSTRUCTION QUESTION
===============================================================
Five months of this programme measured forecasts and concluded that nothing
works. `BRAINSTORM_2026-09-06` §1.2 says the arithmetic differently:

    IR ~= IC x sqrt(BR) x TC

Our IC is real (0.06-0.10 on the clean panel). Our breadth is 7 effective
names, because a top-50 VALUE-weighted US book is three mega-caps and a tail.
Our transfer coefficient is worse, because long-only + top-50 + full monthly
rebalancing expresses a fraction of the bet the ranking implies. 0.08 x sqrt(7
x 12) x 0.3 is an IR of ~0.06 -- invisible at any sample size we will ever
own. The SAME forecast at breadth 300 with hysteresis is an IR near 1.

**Nothing in this job changes a single prediction.** Every selector is a frozen
column. What varies is the construction: k, the weighting, the hold band, and
whether the bottom decile is monetised. If the money moves, it was never the
signal.

WHAT IS COMPARED WITH WHAT
==========================
Every broad book is compared with **its own top-50 value-weighted book over
exactly the same months**. That difference is not a horse race between two
strategies; it is the transfer-coefficient cost, measured in terminal wealth,
of the construction this repo has been using since March. Both books carry a
`learner.fundamental_law` block, so the reader sees WHICH term moved.

THE RULER
=========
PRIMARY is the BETA-MATCHED excess (beta x market + (1 - beta) x rf) and beta
is printed FIRST on every book, per the 2026-09-07 amendment: a broad
equal-weighted book of small names carries more beta than a mega-cap top-50
book, and grading it on the raw market excess would credit that beta as skill.
The raw-market excess is SECONDARY and always present. 10 and 25 bps a side.

THE FAMILY
==========
Every cell this job builds is in one family and the family size is printed
before any cell is quoted. Screens cannot reach NOVEL; the verdict vocabulary
is `scripts.weekend_lab_jobs.verdict_from`.

    python -m scripts.n1_construction_books --smoke     # 3 selectors, 1 cost
    python -m scripts.n1_construction_books             # the full grid
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
    _month_windows, _window_leg, ols_market_model)

OUT_DIR = REPO / "backend" / "data" / "optimus" / "night_lab_2026-09-07"
RECEIPT = OUT_DIR / "N1_construction_books.json"
ENSEMBLE_PARQUET = OUT_DIR / "N2_ensemble_scores.parquet"

NW_LAG = 4
COSTS: tuple[float, ...] = (10.0, 25.0)

#: (k, weight, hold_k). The FIRST row is the incumbent construction this repo
#: has used for six months and is the control every other row is measured
#: against. `hold_k = 2k` is Qlib's TopkDropout band, which A4 found beat the
#: no-hysteresis control in 19 of 20 rungs.
CONSTRUCTIONS: tuple[tuple[int, str, int | None], ...] = (
    (50, "vw", None),          # THE CONTROL -- the incumbent
    (50, "ew", 100),
    (100, "ew", 200),
    (100, "rank", 200),
    (300, "ew", 600),
    (300, "rank", 600),
)
CONTROL_KEY = "k=50|vw|hold=none"

#: Deciles for the long-short and exclusion books.
DECILE = 10


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


def _p_one_sided(t: float | None) -> float | None:
    return None if t is None else _r(1.0 - _ncdf(float(t)), 6)


def holm(pvals: dict[str, float]) -> dict[str, float]:
    """Holm-Bonferroni adjusted p-values. EXPORT standard, CANON §63."""
    items = sorted(((k, v) for k, v in pvals.items() if v is not None),
                   key=lambda kv: kv[1])
    n, out, running = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        adj = min(1.0, (n - i) * p)
        running = max(running, adj)          # monotone, as Holm requires
        out[k] = round(running, 6)
    return out


# ------------------------------------------------------------- the selectors

def _attach_stage(df: pd.DataFrame, tracker: RP.InputTracker) -> dict:
    """The frozen W3b stage vintage. REFUSES rather than refitting."""
    from learner import neural_long as N
    from scripts import w3_neural_floored as W3B
    years = list(range(N.FIRST_TEST_YEAR, N.LAST_TEST_YEAR + 1))
    seeds = [N.SEED_BASE + i for i in range(N.N_SEEDS)]
    fp = df.attrs.get("_fingerprint")
    got: dict = {}
    for tag, scope in (("incumbents", W3B._scope(years, [])),
                       ("nn_pre_causal", W3B._scope(years, seeds))):
        try:
            block, meta = W3B._read_stage(tag, fp, scope)
        except SystemExit as exc:
            got[tag] = {"status": "REFUSED", "why": str(exc)}
            continue
        for col in block.columns:
            df[col] = block[col].reindex(df.index).astype("float32")
        tracker.opened(W3B._stage_path(tag))
        got[tag] = {"status": "ok", "columns": list(block.columns),
                    "written_utc": meta.get("written_utc")}
    return got


def _attach_v2(df: pd.DataFrame, tracker: RP.InputTracker) -> dict:
    """ridge and the v2 encoder, from the SHORT-panel OOS vintage.

    They cover fewer months than the stage arms and that is reported rather
    than hidden: a cell graded on 2013-2024 is not comparable with one graded
    on 2004-2024, and the receipt prints `months` on every cell for exactly
    this reason.
    """
    path = REPO / "backend" / "data" / "optimus" / "learner" / "oos_predictions_v2.parquet"
    if not path.exists():
        return {"status": "ABSENT", "path": str(path)}
    cols = ["permno", "month", "ridge__residual__1m", "encoder__residual__1m"]
    try:
        v2 = pd.read_parquet(path, columns=cols)
    except Exception as exc:                                        # noqa: BLE001
        return {"status": "REFUSED", "why": f"{type(exc).__name__}: {exc}"}
    tracker.opened(path)
    v2["month"] = v2["month"].astype(str)
    v2 = v2.rename(columns={"ridge__residual__1m": "ridge",
                            "encoder__residual__1m": "encoder"})
    key = df[["permno", "month"]].copy()
    key["permno"] = key["permno"].astype("int64")
    v2["permno"] = v2["permno"].astype("int64")
    merged = key.merge(v2, on=["permno", "month"], how="left")
    for c in ("ridge", "encoder"):
        df[c] = merged[c].to_numpy(dtype="float32")
    return {"status": "ok", "rows_matched": int(merged["ridge"].notna().sum()),
            "share_of_panel": _r(float(merged["ridge"].notna().mean()), 4)}


def _attach_panel_natives(df: pd.DataFrame) -> dict:
    """Momentum, the revision family and quality-momentum, from the panel.

    These need no model and no fit, which is the point: if a broad
    construction rescues 12-1 momentum, the finding is about construction and
    cannot be about a learner.
    """
    got: dict = {}
    if "mom_12_1__xs" in df.columns:
        df["momentum"] = df["mom_12_1__xs"].astype("float32")
        got["momentum"] = "mom_12_1__xs (cross-sectional rank)"
    if "net_rev_4w__xs" in df.columns:
        df["revisions"] = df["net_rev_4w__xs"].astype("float32")
        got["revisions"] = "net_rev_4w__xs (cross-sectional rank)"
    if "target_rev_1m__xs" in df.columns:
        df["revisions_target"] = df["target_rev_1m__xs"].astype("float32")
        got["revisions_target"] = "target_rev_1m__xs"
    return got


def _attach_quality_mom(df: pd.DataFrame, tracker: RP.InputTracker) -> dict:
    """The Growth Book champion's signal: pct-rank ROE + pct-rank 12-1, halved.

    Imported from `growth_g2_generation0` rather than re-derived, so the two
    receipts cannot drift into meaning different things by the same name.
    """
    try:
        from scripts.growth_g2_generation0 import _attach_quality, _load_roe
    except Exception as exc:                                        # noqa: BLE001
        return {"status": "UNAVAILABLE", "why": f"{type(exc).__name__}: {exc}"}
    try:
        roe = _load_roe(tracker)
        out = _attach_quality(df, roe)
    except Exception as exc:                                        # noqa: BLE001
        return {"status": "REFUSED", "why": f"{type(exc).__name__}: {exc}"}
    if "roe_pit" not in out.columns or not out["roe_pit"].notna().any():
        return {"status": "REFUSED", "why": "roe_pit is empty after the join"}
    q = out.groupby("month")["roe_pit"].rank(pct=True)
    m = out.groupby("month")["mom_12_1"].rank(pct=True)
    df["quality_mom"] = ((q + m) / 2.0).astype("float32")
    return {"status": "ok",
            "roe_coverage_share": _r(float(out["roe_pit"].notna().mean()), 4),
            "quality_mom_coverage_share": _r(float(df["quality_mom"].notna().mean()), 4)}


def _attach_ensemble(df: pd.DataFrame, tracker: RP.InputTracker) -> dict:
    """N2's selection-free ensemble, if it has been built. Optional by design:
    N1 must be readable on a night when N2 refused."""
    if not ENSEMBLE_PARQUET.exists():
        return {"status": "ABSENT", "path": str(ENSEMBLE_PARQUET),
                "note": "N2 has not run yet; N1 grades without the ensemble"}
    try:
        e = pd.read_parquet(ENSEMBLE_PARQUET,
                            columns=["permno", "month", "ensemble", "ensemble_ew"])
    except Exception as exc:                                        # noqa: BLE001
        return {"status": "REFUSED", "why": f"{type(exc).__name__}: {exc}"}
    tracker.opened(ENSEMBLE_PARQUET)
    e["month"] = e["month"].astype(str)
    e["permno"] = e["permno"].astype("int64")
    key = df[["permno", "month"]].copy()
    key["permno"] = key["permno"].astype("int64")
    merged = key.merge(e, on=["permno", "month"], how="left")
    for c in ("ensemble", "ensemble_ew"):
        df[c] = merged[c].to_numpy(dtype="float32")
    return {"status": "ok", "rows_matched": int(merged["ensemble"].notna().sum()),
            "columns": ["ensemble (reliability-weighted)", "ensemble_ew (equal weight)"]}


# ------------------------------------------------------------------ grading

def grade(bk: dict, rf: pd.Series, *, label: str, construction: str,
          df: pd.DataFrame | None = None, pred_col: str | None = None) -> tuple[dict, pd.Series]:
    """One book -> beta FIRST, then the two rulers, the era table and the law."""
    from learner import fundamental_law as FL
    from scripts.weekend_lab_jobs import era_sign_table
    ser = bk.get("_series")
    if ser is None or not len(ser.get("net", [])):
        return {"label": label, "verdict": "CANNOT DETERMINE",
                "why": "the book produced no month"}, pd.Series(dtype=float)
    net = ser["net"].astype("float64")
    mkt = ser["market"].reindex(net.index).astype("float64")
    turn = ser["turnover"].reindex(net.index).astype("float64")
    rfs = rf.reindex(net.index).fillna(0.0)
    reg = ols_market_model(net - rfs, mkt - rfs, lag=NW_LAG)
    beta = reg.get("beta")
    if beta is None:
        return {"label": label, "verdict": "CANNOT DETERMINE",
                "regression": reg}, pd.Series(dtype=float)
    bm = float(beta) * mkt + (1.0 - float(beta)) * rfs
    ex_bm = (net - bm).dropna()
    ex_raw = (net - mkt).dropna()
    mean_turn = float(turn.mean())
    t_bm = _t(ex_bm)
    blk = {
        "label": label,
        # BETA FIRST. The 2026-09-07 amendment: a book praised for a return it
        # bought with leverage is the error this ordering exists to prevent.
        "beta": _r(beta, 4),
        "t_beta_minus_1_hac": reg.get("t_beta_minus_1_hac"),
        "construction": construction,
        "months": int(len(net)),
        "first_month": str(net.index[0]), "last_month": str(net.index[-1]),
        "cost_bps_per_side": bk.get("cost_bps_per_side"),
        "mean_names_per_month": bk.get("mean_names_per_month"),
        "mean_turnover": _r(mean_turn, 4),
        "implied_mean_holding_months": _r(1.0 / mean_turn, 2) if mean_turn > 0 else None,
        "annual_cost_line_pct": _r(mean_turn * 2 * (bk.get("cost_bps_per_side") or 0)
                                   / 10_000.0 * 12 * 100, 3),
        "terminal_wealth_net": bk.get("terminal_wealth_net"),
        "terminal_wealth_gross": bk.get("terminal_wealth_gross"),
        "terminal_wealth_market_same_months": bk.get("terminal_wealth_market_same_months"),
        "PRIMARY_beta_matched": {
            "annualised_pct": _r(float(ex_bm.mean()) * 12 * 100, 3),
            "t_paired": _r(t_bm, 3),
            "p_one_sided": _p_one_sided(t_bm),
        },
        "SECONDARY_raw_market": {
            "annualised_pct": _r(float(ex_raw.mean()) * 12 * 100, 3),
            "t_paired": _r(_t(ex_raw), 3),
        },
        "era_table_on_the_beta_matched_excess": era_sign_table(ex_bm),
    }
    w = bk.get("_weights")
    if w and df is not None and pred_col:
        blk["fundamental_law"] = FL.receipt(
            df[["month", "permno", pred_col, "fwd_1m"]].dropna(subset=[pred_col]),
            pred_col, w, net=net, benchmark=bm, beta=float(beta))
    return blk, ex_bm


# ------------------------------------------------- the long-short / exclusion

def index_hedged(df: pd.DataFrame, pred_col: str, *, k_share: float = 1.0 / DECILE,
                 cost_bps: float = 10.0, beta_window: int = 60,
                 ret_col: str = "fwd_1m", mkt_col: str = "mkt_vw_1m") -> tuple[pd.Series, dict]:
    """Long the top decile EQUAL-weighted, short the index to beta ~ 0.

    THE HEDGE RATIO IS EX-ANTE OR IT IS A BACKTEST OF THE FUTURE. The hedge
    uses the book's own TRAILING `beta_window`-month regression beta, known at
    the moment the hedge is placed. Using the full-sample beta would set the
    hedge with information from months that had not happened, and would report
    a beta of exactly zero because it was fitted to be.
    """
    d = df[["month", "permno", pred_col, ret_col, mkt_col]].dropna(
        subset=[pred_col, ret_col, mkt_col])
    if d.empty:
        return pd.Series(dtype=float), {"months": 0, "note": "no rows"}
    rows, prev = {}, None
    for m, g in d.groupby("month", sort=True):
        k = max(1, int(round(len(g) * k_share)))
        sel = g.sort_values(pred_col, ascending=False).head(k)
        w = {int(p): 1.0 / len(sel) for p in sel["permno"]}
        turn = 1.0 if prev is None else 0.5 * sum(
            abs(w.get(x, 0.0) - prev.get(x, 0.0)) for x in set(w) | set(prev))
        prev = w
        rows[m] = {"long": float(sel[ret_col].mean()),
                   "mkt": float(sel[mkt_col].iloc[0]),
                   "turn": turn, "names": len(sel)}
    f = pd.DataFrame(rows).T.sort_index()
    long_r = f["long"].astype(float)
    mkt_r = f["mkt"].astype(float)
    hedge = []
    for i in range(len(long_r)):
        if i < beta_window:
            hedge.append(np.nan)                 # not enough trailing tape yet
            continue
        y = long_r.iloc[i - beta_window:i].to_numpy()
        x = mkt_r.iloc[i - beta_window:i].to_numpy()
        vx = float(np.var(x, ddof=1))
        hedge.append(float(np.cov(y, x, ddof=1)[0, 1] / vx) if vx > 0 else np.nan)
    hedge = pd.Series(hedge, index=long_r.index)
    cost = f["turn"].astype(float) * (cost_bps / 10_000.0) * 2.0
    # The short index leg pays its own one-way cost on the CHANGE in hedge ratio.
    hedge_turn = hedge.diff().abs().fillna(hedge.abs())
    cost = cost + hedge_turn * (cost_bps / 10_000.0) * 2.0
    net = (long_r - hedge * mkt_r - cost).dropna()
    return net, {
        "months": int(len(net)),
        "construction": (f"long top decile EW ({int(f['names'].mean())} names/month), "
                         f"short the VW index at the TRAILING {beta_window}-month beta"),
        "mean_hedge_ratio": _r(float(hedge.dropna().mean()), 4),
        "cost_bps_per_side": cost_bps,
        "annual_cost_drag_pct": _r(float(cost.reindex(net.index).mean()) * 12 * 100, 3),
        "benchmark": "CASH -- a hedged book carries no market exposure to beat",
    }


def exclusion_book(df: pd.DataFrame, pred_col: str, *, cost_bps: float = 10.0,
                   drop_share: float = 1.0 / DECILE,
                   ret_col: str = "fwd_1m") -> tuple[pd.Series, pd.Series, dict]:
    """The tradable universe EQUAL-weighted, minus the bottom decile.

    Reported against the EW universe INCLUDING the bottom decile, because the
    only question an exclusion book asks is "is the bottom decile worth not
    owning?" -- and against nothing else, since a book that holds 90% of the
    universe is not a stock-selection claim.
    """
    d = df[["month", "permno", pred_col, ret_col]].dropna(subset=[pred_col, ret_col])
    if d.empty:
        return pd.Series(dtype=float), pd.Series(dtype=float), {"months": 0}
    keep_r, all_r, rows, prev = {}, {}, {}, None
    for m, g in d.groupby("month", sort=True):
        n_drop = int(round(len(g) * drop_share))
        srt = g.sort_values(pred_col, ascending=False)
        kept = srt.head(len(g) - n_drop) if n_drop else srt
        w = {int(p): 1.0 / len(kept) for p in kept["permno"]}
        turn = 1.0 if prev is None else 0.5 * sum(
            abs(w.get(x, 0.0) - prev.get(x, 0.0)) for x in set(w) | set(prev))
        prev = w
        keep_r[m] = float(kept[ret_col].mean()) - turn * (cost_bps / 10_000.0) * 2.0
        all_r[m] = float(g[ret_col].mean())
        rows[m] = {"kept": len(kept), "dropped": n_drop, "turn": turn}
    kept_s = pd.Series(keep_r).sort_index()
    all_s = pd.Series(all_r).sort_index()
    f = pd.DataFrame(rows).T
    return kept_s, all_s, {
        "months": int(len(kept_s)),
        "mean_names_held": _r(float(f["kept"].mean()), 1),
        "mean_names_dropped": _r(float(f["dropped"].mean()), 1),
        "mean_turnover": _r(float(f["turn"].mean()), 4),
        "cost_bps_per_side": cost_bps,
        "terminal_wealth_excluding_bottom_decile": _r(float((1 + kept_s).prod()), 4),
        "terminal_wealth_ew_universe": _r(float((1 + all_s).prod()), 4),
    }


# ----------------------------------------------------------------------- run

def run(*, smoke: bool = False, verbose: bool = True) -> dict:
    from learner import benchmark as BM
    from learner import evaluate as E
    from learner import inference as INF
    from learner import long_panel as LP
    from learner import neural_long as N
    from scripts import w3_neural_floored as W3B
    from scripts.weekend_lab_jobs import verdict_from

    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    t0 = time.perf_counter()
    tracker = RP.InputTracker()
    out: dict = {
        "job": "N1_construction_books",
        "lane": "N1",
        "question": ("does the IC we already have turn into money once the "
                     "construction stops destroying it? Same frozen predictions, "
                     "six constructions, two cost rates, graded beta-matched."),
        "licence": "PRODUCT_EXPERIMENT",
        "what_varies": ("the CONSTRUCTION only -- k, the weighting, the hold band, "
                        "and whether the bottom decile is monetised. No model is "
                        "fitted and no prediction column is recomputed."),
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
                                 "rows_after", "months_after",
                                 "median_names_per_month_after") if k in uni}

    out["selector_sources"] = {
        "stage": _attach_stage(df, tracker),
        "oos_v2": _attach_v2(df, tracker),
        "panel_native": _attach_panel_natives(df),
        "quality_mom": _attach_quality_mom(df, tracker),
        "ensemble": _attach_ensemble(df, tracker),
    }
    candidates = [
        ("lgbm_clf", "lgbm_clf"), ("lgbm_raw", "lgbm_raw"),
        ("nn_pre_causal", "nn_pre_causal_seedmean"),
        ("ridge", "ridge"), ("encoder", "encoder"),
        ("momentum", "momentum"), ("revisions", "revisions"),
        ("quality_mom", "quality_mom"),
        ("ensemble", "ensemble"), ("ensemble_ew", "ensemble_ew"),
    ]
    selectors = {name: col for name, col in candidates
                 if col in df.columns and df[col].notna().any()}
    out["selectors_graded"] = {k: {"column": v,
                                   "coverage_share": _r(float(df[v].notna().mean()), 4)}
                               for k, v in selectors.items()}
    out["selectors_absent"] = [n for n, c in candidates if n not in selectors]
    if not selectors:
        out.update(status="REFUSED", headline="REFUSED: no selector column is available")
        return out
    if smoke:
        selectors = {k: v for k, v in list(selectors.items())[:3]}

    # ---- the risk-free leg over each book month's own holding window
    months_all = pd.Index(sorted(df["month"].dropna().unique()))
    win = _month_windows(df)
    try:
        rf_d = BM.cash().returns.dropna().astype("float64")
        rf, rf_note = _window_leg(rf_d, win, months_all)
        rf_note["source"] = "learner.benchmark.cash() -- pinned FF daily RF, OFFLINE"
    except Exception as exc:                                        # noqa: BLE001
        rf = pd.Series(0.0, index=months_all)
        rf_note = {"available": False, "why": f"{type(exc).__name__}: {exc}",
                   "declared": "rf = 0; only the intercept's level moves"}
    out["risk_free_leg"] = rf_note

    costs = (10.0,) if smoke else COSTS
    constructions = CONSTRUCTIONS[:3] if smoke else CONSTRUCTIONS

    cells: dict = {}
    fam: dict = {}
    log(f"  grading {len(selectors)} selectors x {len(constructions)} constructions "
        f"x {len(costs)} cost rates ...")
    for name, col in selectors.items():
        for (k, wgt, hk) in constructions:
            for bps in costs:
                key = f"{name}|k={k}|{wgt}|hold={hk or 'none'}|{int(bps)}bps"
                try:
                    bk = E.book(df, col, k=k, weight=wgt, cost_bps=bps,
                                ret_col="fwd_1m", mkt_col="mkt_vw_1m",
                                tradable_floor=N.TRADABLE_FLOOR_USD,
                                hold_k=hk, return_series=True, return_weights=True)
                except SystemExit as exc:
                    cells[key] = {"label": key, "verdict": "REFUSED", "why": str(exc)}
                    continue
                blk, ex = grade(bk, rf, label=key, df=df, pred_col=col,
                                construction=(f"top-{k} {wgt}"
                                              + (f", hold until rank > {hk}" if hk
                                                 else ", rebuilt every month (control)")))
                cells[key] = blk
                if len(ex):
                    fam[key] = ex
                del bk
        gc.collect()
        log(f"    {name}: done ({len(cells)} cells so far)")

    # ---- THE TRANSFER-COEFFICIENT COST: broad vs its own top-50 VW control
    deltas = {}
    for name in selectors:
        for bps in costs:
            ctrl_key = f"{name}|{CONTROL_KEY}|{int(bps)}bps"
            ctrl = fam.get(ctrl_key)
            if ctrl is None:
                continue
            for (k, wgt, hk) in constructions:
                key = f"{name}|k={k}|{wgt}|hold={hk or 'none'}|{int(bps)}bps"
                if key == ctrl_key or key not in fam:
                    continue
                from scripts.weekend_lab_jobs import era_sign_table
                a, b = fam[key].align(ctrl, join="inner")
                d = (a - b).dropna()
                if len(d) < 3:
                    continue
                cb = cells.get(ctrl_key, {}).get("fundamental_law", {})
                bb = cells.get(key, {}).get("fundamental_law", {})
                deltas[f"{key}  MINUS  {ctrl_key}"] = {
                    "months_paired": int(len(d)),
                    "annualised_pp": _r(float(d.mean()) * 12 * 100, 3),
                    "t_paired": _r(_t(d), 3),
                    "p_one_sided": _p_one_sided(_t(d)),
                    "transfer_coefficient_control": (cb.get("transfer_coefficient") or {}).get("tc"),
                    "transfer_coefficient_broad": (bb.get("transfer_coefficient") or {}).get("tc"),
                    "effective_names_control": (cb.get("effective_breadth") or {}).get(
                        "mean_effective_names_per_month"),
                    "effective_names_broad": (bb.get("effective_breadth") or {}).get(
                        "mean_effective_names_per_month"),
                    "terminal_wealth_control": cells.get(ctrl_key, {}).get("terminal_wealth_net"),
                    "terminal_wealth_broad": cells.get(key, {}).get("terminal_wealth_net"),
                    "era_table": era_sign_table(d),
                }
    out["transfer_coefficient_cost"] = deltas

    # ---- THE DELTA FAMILY, corrected. Each delta is a paired test of the SAME
    # signal under two constructions, which is a far sharper instrument than
    # either level -- and there are a hundred of them, so quoting the best one
    # without the family is exactly the error the level family is corrected for.
    dp = {k: v["p_one_sided"] for k, v in deltas.items()
          if isinstance(v, dict) and v.get("p_one_sided") is not None}
    dadj = holm(dp)
    dbest = min(dp, key=lambda k: dp[k]) if dp else None
    pos = [v.get("annualised_pp") for v in deltas.values()
           if isinstance(v, dict) and v.get("annualised_pp") is not None]
    out["transfer_coefficient_cost_family"] = {
        "size": len(dp),
        "comparisons_with_a_POSITIVE_delta": int(sum(1 for x in pos if x > 0)),
        "comparisons_total": len(pos),
        "median_delta_pp_per_year": _r(float(np.median(pos)), 3) if pos else None,
        "family_min_p": _r(min(dp.values()), 6) if dp else None,
        "family_max_p": _r(max(dp.values()), 6) if dp else None,
        "best_comparison": dbest,
        "best_comparison_holm_adjusted_p": dadj.get(dbest) if dbest else None,
        "comparisons_surviving_holm_at_0.05": sorted(k for k, v in dadj.items() if v <= 0.05),
        "reading": ("a POSITIVE delta means the broad construction beat the top-50 VW "
                    "control on the same months with the same frozen predictions. The "
                    "count of positives is the honest headline: if broadening were "
                    "free money it would be near 100 of 100."),
    }

    # ---- long-short and exclusion, per selector, at each cost rate
    ls_cells, ex_cells = {}, {}
    for name, col in selectors.items():
        for bps in costs:
            try:
                net, meta = index_hedged(df, col, cost_bps=bps)
            except Exception as exc:                                # noqa: BLE001
                ls_cells[f"{name}|{int(bps)}bps"] = {"verdict": "REFUSED",
                                                     "why": f"{type(exc).__name__}: {exc}"}
                continue
            if len(net) < 12:
                ls_cells[f"{name}|{int(bps)}bps"] = {"verdict": "CANNOT DETERMINE", **meta}
                continue
            rfs = rf.reindex(net.index).fillna(0.0)
            t = _t(net - rfs)
            from scripts.weekend_lab_jobs import era_sign_table
            ls_cells[f"{name}|{int(bps)}bps"] = {
                **meta,
                "annualised_net_pct": _r(float(net.mean()) * 12 * 100, 3),
                "annualised_over_cash_pct": _r(float((net - rfs).mean()) * 12 * 100, 3),
                "t_vs_cash": _r(t, 3), "p_one_sided": _p_one_sided(t),
                "terminal_wealth_net": _r(float((1 + net).prod()), 4),
                "realised_beta_of_the_hedged_book": _r(
                    (ols_market_model(net - rfs,
                                      df.groupby("month")["mkt_vw_1m"].first()
                                      .reindex(net.index) - rfs, lag=NW_LAG) or {}
                     ).get("beta"), 4),
                "era_table": era_sign_table(net - rfs),
            }
            if len(net) >= 24:
                fam[f"LS|{name}|{int(bps)}bps"] = (net - rfs)

            kept, allr, xmeta = exclusion_book(df, col, cost_bps=bps)
            if len(kept) >= 12:
                d = (kept - allr).dropna()
                ex_cells[f"{name}|{int(bps)}bps"] = {
                    **xmeta,
                    "annualised_vs_ew_universe_pp": _r(float(d.mean()) * 12 * 100, 3),
                    "t_paired_vs_ew_universe": _r(_t(d), 3),
                    "p_one_sided": _p_one_sided(_t(d)),
                    "era_table": era_sign_table(d),
                }
                fam[f"EXCL|{name}|{int(bps)}bps"] = d
        gc.collect()
    out["index_hedged_long_short"] = ls_cells
    out["exclusion_books"] = ex_cells

    # ---- the family, in one place, before any cell is quoted
    pvals = {}
    for key, blk in cells.items():
        p = (blk.get("PRIMARY_beta_matched") or {}).get("p_one_sided")
        if p is not None:
            pvals[key] = float(p)
    for key, blk in ls_cells.items():
        if isinstance(blk, dict) and blk.get("p_one_sided") is not None:
            pvals[f"LS|{key}"] = float(blk["p_one_sided"])
    for key, blk in ex_cells.items():
        if isinstance(blk, dict) and blk.get("p_one_sided") is not None:
            pvals[f"EXCL|{key}"] = float(blk["p_one_sided"])
    adj = holm(pvals)
    best = min(pvals, key=lambda k: pvals[k]) if pvals else None
    out["family"] = {
        "size": len(pvals),
        "family_min_p": _r(min(pvals.values()), 6) if pvals else None,
        "family_max_p": _r(max(pvals.values()), 6) if pvals else None,
        "best_cell": best,
        "best_cell_holm_adjusted_p": adj.get(best) if best else None,
        "cells_surviving_holm_at_0.05": sorted(k for k, v in adj.items() if v <= 0.05),
        "note": ("one family for every cell this job built. The Holm column is the "
                 "EXPORT standard (CANON §63); a cell quoted without it is a screen."),
    }

    # ---- inference on the best cell, and the verdict
    if best and best in fam:
        arm = fam[best].to_numpy()
        try:
            inf = INF.full_report(arm, family={k: v.to_numpy() for k, v in fam.items()},
                                  n_trials=len(pvals), seed=20260907)
        except Exception as exc:                                    # noqa: BLE001
            inf = {"verdict": "CANNOT DETERMINE", "why": f"{type(exc).__name__}: {exc}"}
        out["inference_on_the_best_cell"] = inf
        eras = (cells.get(best) or ls_cells.get(best.split("|", 1)[-1])
                or {}).get("era_table_on_the_beta_matched_excess") or {}
        try:
            out["verdict_on_the_best_cell"] = verdict_from(inf, eras)
        except Exception as exc:                                    # noqa: BLE001
            out["verdict_on_the_best_cell"] = f"CANNOT DETERMINE ({type(exc).__name__})"

    out["cells"] = cells
    out["memory_free_gb_after"] = W3B.free_gb()
    out["wall_seconds"] = round(time.perf_counter() - t0, 1)
    out["headline"] = _headline(out)
    RP.attach(out, sys.argv,
              {"smoke": bool(smoke), "costs": list(costs),
               "constructions": [list(c) for c in constructions],
               "tradable_floor_usd": N.TRADABLE_FLOOR_USD,
               "nw_lag": NW_LAG, "decile": DECILE},
              tracker)
    return out


def _headline(out: dict) -> str:
    d = out.get("transfer_coefficient_cost") or {}
    fam = out.get("transfer_coefficient_cost_family") or {}
    if not d:
        return "no paired broad-vs-control comparison was formed"
    best = max(d.items(), key=lambda kv: (kv[1].get("annualised_pp") or -1e9))
    k, v = best
    return (f"{fam.get('comparisons_with_a_POSITIVE_delta')} of "
            f"{fam.get('comparisons_total')} broad-vs-control comparisons are POSITIVE "
            f"(median {fam.get('median_delta_pp_per_year')}pp/yr, best Holm "
            f"{fam.get('best_comparison_holm_adjusted_p')}). "
            f"Broad construction minus the top-50 VW control, best cell: {k} "
            f"{v.get('annualised_pp')}pp/yr t {v.get('t_paired')}; TC "
            f"{v.get('transfer_coefficient_control')} -> {v.get('transfer_coefficient_broad')}, "
            f"effective names {v.get('effective_names_control')} -> "
            f"{v.get('effective_names_broad')}")


def write(rec: dict, path: Path = RECEIPT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rec["generated_utc"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--smoke", action="store_true",
                    help="3 selectors, 3 constructions, one cost rate")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    path = Path(a.out) if a.out else RECEIPT
    try:
        rec = run(smoke=a.smoke)
    except Exception:                                               # noqa: BLE001
        # A TRACEBACK IS A RECEIPT. A job that dies without one is a job the
        # morning cannot tell apart from a job that never ran.
        rec = {"job": "N1_construction_books", "status": "FAILED",
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
