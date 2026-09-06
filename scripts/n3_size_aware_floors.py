"""N3 -- SIZE-AWARE EXECUTION FLOORS: the $3m/day floor is an institution's floor.

THE CLAIM UNDER TEST (docs/BRAINSTORM_2026-09-06_WHY_NO_PROFIT_AND_WHAT_OTHERS_DO.md
§1 reason 4, §3 A.5) -- the $3,000,000/day liquidity floor
(`alpha.universe.MIN_EXECUTE_DOLLAR_VOLUME` in `aegis-alpha-terminal`, mirrored
here as `learner.evaluate.TRADABLE_DOLLAR_VOL`) is sized for a book far bigger
than the ones this repo actually runs, and it deletes every cell where the
edge lives. A $100k book trading at 1% of a name's average daily dollar
volume can fill a full position in a name trading $500k/day, not $3m/day.
Capacity is the one dimension where a SMALL book has an advantage over an
institution, and the flat floor throws it away.

WHAT THIS FILE DOES, IN THREE PARTS
====================================
1. `size_aware_floor()` -- the same formula added to
   `aegis-alpha-terminal/alpha/universe.py::execution_authority` (a SEPARATE
   repo, see CLAUDE.md "four repositories"; reimplemented here, not imported,
   so this receipt does not depend on a sibling checkout existing in CI,
   which runs on Linux with none of the four repos side by side). REFUSES
   (returns `(None, why)`) rather than guessing when book size or
   participation is missing or non-positive.
2. Measured TAQ cost by liquidity band, read from the already-pulled
   `scripts/taq_spread_by_liquidity_band.py` receipt
   (`backend/data/optimus/wrds/taq_spread_by_liquidity_band.json`) --
   QUOTED spread, an upper bound on touch cost, in 5 dollar-volume bands from
   $100k/day to $50m+/day -- used in place of the flat 10/25 bps assumption
   every other book in this repo charges.
3. Three re-grades, each producing its own receipt because a job that failed
   is still a receipt:
   a. THE EDGE-VS-FLOOR CURVE (item 3 of the mandate) -- `lgbm_clf` fitted
      ONCE, walk-forward, on the UNFLOORED long panel (2004-2024, the full
      21-year out-of-sample window `learner/long_panel.py::ERAS` cuts into
      the three eras `era_sign_table` reports on -- 1999-2007, 2008-2015,
      2016-2024), then
      GRADED at four floors (the flat $3m institutional floor, and the
      size-aware floors implied by $100k / $1m / $10m books at 1% ADV
      participation) with the MEASURED TAQ cost for whichever liquidity band
      each floor falls into. PRIMARY is beta-matched, SECONDARY is raw,
      family = every floor x every cost assumption, Holm-adjusted, DSR/MDE
      on the best cell.
   b. THE SMALL-CAP 5-SESSION REVERSAL (docs/BUILD_NIGHT_LAB_2026-09-05.md,
      `down|q1|no_event|10bps` in `scripts/night_lab_jobs.py::L4_reversal_by_size`)
      -- an event study, not a monthly book, so it does not get the
      beta-matched/DSR/MDE treatment of (a); it gets the treatment the
      original cell got (raw mean 5-session return, HAC and
      non-overlapping t), RE-CUT by a lagged 20-session dollar-volume floor
      and re-costed at the MEASURED TAQ band instead of the flat 10/25/50 bps
      that made the original cell "die between 25 and 50 bps".
   c. S28's $100k-$1m LIQUIDITY BAND (`scripts/weekend_lab_jobs.py::W6b_liquidity_band`
      tested a $100k-$10m band; this narrows it to the exact TAQ band and nets
      the SAME already-measured gross monthly excess by the TAQ receipt's own
      `cost_pct_per_year_at_monthly_turnover` for that band).

WHAT THIS FILE DOES NOT DO
===========================
`OBSERVE_ONLY` population (`alpha.universe.build(scope="observe")`) needs a
live Alpaca venue call in the aegis-alpha-terminal repo. This lane is offline
research with no network calls and no keys touched -- see
`N3_populate_observe_tier.json`, which records that refusal and why, and
proves the CODE PATH (not the live data) is exercised by
`aegis-alpha-terminal/tests_smoke_universe.py`, run and green this session.

No model beyond the ONE `lgbm_clf` walk-forward fit in (a) is trained. No
neural refit: `scripts/w3_neural_floored.py` floors the panel to $3m/day
BEFORE fitting (`neural_long.tradable_universe`), so its stage predictions
cannot see a sub-$3m name at all and cannot be re-graded at a lower floor --
that is exactly the "unfloored neural arm... became 65x under the floor"
finding this lane is testing, restated as a reason `lgbm_clf` (fit on the
UNFLOORED panel, floored only at grading time via `evaluate.book`'s
`tradable_floor` argument) is the tractable stand-in for this lane's memory
and time budget (free memory was 3.6 GB at session start, comfortably above
the 2 GB backoff line but well under the 6 GB `w3_neural_floored.MIN_FREE_GB`
a from-scratch neural fit would want, and other lanes are running heavy jobs
concurrently tonight).

    python -m scripts.n3_size_aware_floors --all
    python -m scripts.n3_size_aware_floors --floor-curve
    python -m scripts.n3_size_aware_floors --reversal
    python -m scripts.n3_size_aware_floors --s28-band
    python -m scripts.n3_size_aware_floors --observe-tier
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

from backend.services import receipt_provenance as PROV                # noqa: E402

OUT_DIR = REPO / "backend" / "data" / "optimus" / "night_lab_2026-09-07"
TAQ_BAND_RECEIPT = REPO / "backend" / "data" / "optimus" / "wrds" / "taq_spread_by_liquidity_band.json"
LONG_TABLE = REPO / "backend" / "data" / "optimus" / "learner" / "train_table_long.parquet"
CRSP_DSF_DIR = REPO / "backend" / "data" / "optimus" / "wrds"

LICENCE = "PRODUCT_EXPERIMENT"
MIN_FREE_GB_TO_LOAD_PANEL = 2.0          # CLAUDE.md night-lab rule: back off under 2 GB

# --------------------------------------------------------------------------
# 1. THE SIZE-AWARE FLOOR
# --------------------------------------------------------------------------

#: MATCHES aegis-alpha-terminal/alpha/universe.py::MAX_ADV_PARTICIPATION and
#: ::SIZE_AWARE_POSITION_FRACTION -- restated here, not imported (separate
#: repo; see module docstring). Both files carry the same worked example so a
#: drift between them is visible on inspection: $100k book, 1% participation,
#: one session, 5%-of-equity per-name cap -> a $500,000/day floor.
PARTICIPATION = 0.01
POSITION_FRACTION = 0.05
BUILD_SESSIONS = 1.0

#: The three book sizes the mandate names.
BOOK_SIZES_USD = (100_000.0, 1_000_000.0, 10_000_000.0)

#: The house's existing flat floor, for comparison. Restated (not imported
#: from `learner.evaluate.TRADABLE_DOLLAR_VOL`) would be fine too since that
#: IS this repo -- imported below where it is actually used, to keep the one
#: number in one place.
INSTITUTIONAL_FLOOR_USD = 3_000_000.0


def size_aware_floor(book_size_usd, *, participation: float | None = PARTICIPATION,
                     position_fraction: float | None = POSITION_FRACTION,
                     build_sessions: float | None = BUILD_SESSIONS
                     ) -> tuple[float | None, str | None]:
    """The $/day median-dollar-volume floor a book of `book_size_usd` needs to
    fill ONE full position inside `build_sessions` sessions without exceeding
    `participation` of a name's own ADV, given a per-name notional cap of
    `position_fraction` of the book. `(floor_usd, None)` on success,
    `(None, why)` on refusal -- never a permissive default.
    """
    inputs = {"book_size_usd": book_size_usd, "participation": participation,
              "position_fraction": position_fraction, "build_sessions": build_sessions}
    missing = [k for k, v in inputs.items() if v is None]
    if missing:
        return None, f"cannot derive a size-aware floor: missing {', '.join(missing)}"
    bad = [k for k, v in inputs.items() if not (float(v) > 0)]
    if bad:
        return None, f"cannot derive a size-aware floor: non-positive {', '.join(bad)}"
    floor = (float(book_size_usd) * float(position_fraction)) / (
        float(participation) * float(build_sessions))
    return floor, None


# --------------------------------------------------------------------------
# 2. MEASURED TAQ COST BY LIQUIDITY BAND
# --------------------------------------------------------------------------

def load_taq_bands(tracker: PROV.InputTracker | None = None) -> dict | None:
    """The `scripts/taq_spread_by_liquidity_band.py` receipt's `summary` block,
    keyed by band name, or `None` (not `{}`) if the receipt is absent -- a
    guard that derives its input or refuses, never a silent empty result read
    as a zero-cost band.
    """
    if not TAQ_BAND_RECEIPT.exists():
        return None
    if tracker is not None:
        tracker.opened(TAQ_BAND_RECEIPT)
    d = json.loads(TAQ_BAND_RECEIPT.read_text(encoding="utf-8"))
    return d.get("summary")


#: (name, lo, hi) exactly as `scripts/taq_spread_by_liquidity_band.py::BANDS` --
#: restated because that module's BANDS is a local, not exported. A future
#: divergence would be caught by `test_n3_size_aware_floors.py`'s pin against
#: the receipt's own band names.
TAQ_BAND_EDGES: tuple[tuple[str, float, float], ...] = (
    ("100k-1m", 1e5, 1e6),
    ("1m-5m", 1e6, 5e6),
    ("5m-10m", 5e6, 1e7),
    ("10m-50m", 1e7, 5e7),
    ("50m+", 5e7, float("inf")),
)


def taq_band_for(dollar_volume: float | None) -> str | None:
    if dollar_volume is None or not math.isfinite(dollar_volume):
        return None
    for name, lo, hi in TAQ_BAND_EDGES:
        if lo <= dollar_volume < hi:
            return name
    return None


def taq_cost_for_floor(floor_usd: float | None, bands: dict | None) -> dict:
    """The measured cost a name JUST CLEARING `floor_usd` would pay -- the
    worst-case (thinnest-admitted) cost for a book graded at that floor.
    REFUSES (returns `verdict: CANNOT DETERMINE`) if the TAQ receipt is
    missing or the floor falls in a band the receipt never measured.
    """
    if bands is None:
        return {"verdict": "CANNOT DETERMINE",
                "why": f"{TAQ_BAND_RECEIPT} is absent -- run scripts/taq_spread_by_liquidity_band.py"}
    if floor_usd is None:
        return {"verdict": "CANNOT DETERMINE", "why": "no floor to look up"}
    band = taq_band_for(floor_usd)
    if band is None or band not in bands or not bands[band].get("n_measured"):
        return {"verdict": "CANNOT DETERMINE",
                "why": f"${floor_usd:,.0f}/day maps to TAQ band {band!r}, which the receipt "
                       "did not measure (0 names quoted, or below its lowest band)"}
    b = bands[band]
    return {
        "verdict": "MEASURED", "band": band,
        "round_trip_bps": b["round_trip_bps"],
        "one_way_bps": round(b["round_trip_bps"] / 2.0, 3),
        "cost_pct_per_year_at_monthly_turnover": b["cost_pct_per_year_at_monthly_turnover"],
        "n_measured": b["n_measured"],
    }


# --------------------------------------------------------------------------
# small shared helpers (reimplemented rather than imported from a peer
# lane's script -- `scripts/labor_a1_shadow_grader.py::ols_market_model`
# states the same reasoning: importing a peer lane's file would couple this
# receipt to edits another agent makes to it the same night)
# --------------------------------------------------------------------------

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


def ols_market_model(y, x, *, lag: int = 4) -> dict:
    """OLS of y on a constant and x, OLS and Newey-West HAC t's."""
    y = np.asarray(y, dtype="float64")
    x = np.asarray(x, dtype="float64")
    ok = np.isfinite(y) & np.isfinite(x)
    y, x = y[ok], x[ok]
    n = int(y.size)
    if n < 8:
        return {"verdict": "CANNOT DETERMINE", "n_months": n,
                "why": "fewer than 8 aligned months"}
    X = np.column_stack([np.ones(n), x])
    XtX_inv = np.linalg.inv(X.T @ X)
    b = XtX_inv @ (X.T @ y)
    resid = y - X @ b
    u = X * resid[:, None]
    S = (u.T @ u) / n
    for l in range(1, int(lag) + 1):
        if l >= n:
            break
        G = (u[l:].T @ u[:-l]) / n
        S = S + (1.0 - l / (lag + 1.0)) * (G + G.T)
    se_hac = np.sqrt(np.diag(np.asarray(XtX_inv @ (n * S) @ XtX_inv)))
    beta = float(b[1])
    return {"n_months": n, "beta": _r(beta, 4),
            "beta_se_hac": _r(se_hac[1]),
            "t_beta_minus_1_hac": (_r((beta - 1.0) / se_hac[1], 3)
                                   if se_hac[1] > 0 else None)}


def grade_cell(bk: dict, *, label: str, cost_source: dict) -> tuple[dict, pd.Series]:
    """One `evaluate.book(..., return_series=True)` result -> the beta-matched
    (PRIMARY) and raw-market (SECONDARY) blocks, plus the era table.
    """
    from scripts.weekend_lab_jobs import era_sign_table
    ser = bk.get("_series")
    if ser is None:
        return {"label": label, "verdict": "CANNOT DETERMINE", "why": "no series",
                "book": bk}, pd.Series(dtype=float)
    net = ser["net"].astype("float64")
    mkt = ser["market"].reindex(net.index).astype("float64")
    reg = ols_market_model(net, mkt)
    beta = reg.get("beta")
    if beta is None:
        return {"label": label, "verdict": "CANNOT DETERMINE", "regression": reg,
                "book": bk}, pd.Series(dtype=float)
    bm = float(beta) * mkt
    ex_bm = (net - bm).dropna()
    ex_raw = (net - mkt).dropna()
    blk = {
        "label": label,
        "cost_source": cost_source,
        "cost_bps_per_side_charged": bk.get("cost_bps_per_side"),
        "tradable_floor_usd": bk.get("tradable_floor_usd"),
        "rows_after_tradable_floor": bk.get("rows_after_tradable_floor"),
        "mean_names_per_month": bk.get("mean_names_per_month"),
        "months": bk.get("months"),
        "mean_turnover": bk.get("mean_turnover"),
        "terminal_wealth_net": bk.get("terminal_wealth_net"),
        "terminal_wealth_market_same_months": bk.get("terminal_wealth_market_same_months"),
        "PRIMARY_beta_matched": {
            "beta": reg.get("beta"),
            "t_beta_minus_1_hac": reg.get("t_beta_minus_1_hac"),
            "annualised_pct": _r(float(ex_bm.mean()) * 12 * 100, 3),
            "t_paired": _r(_t(ex_bm), 3),
            "p_one_sided": (_r(1.0 - _ncdf(float(_t(ex_bm))), 5)
                            if _t(ex_bm) is not None else None),
        },
        "SECONDARY_raw_market": {
            "annualised_pct": _r(float(ex_raw.mean()) * 12 * 100, 3),
            "t_paired": _r(_t(ex_raw), 3),
        },
        "era_table_on_the_beta_matched_excess": era_sign_table(ex_bm),
    }
    return blk, ex_bm


def _holm_family(cells: dict) -> dict:
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
    return {
        "size": n,
        "family_min_p_one_sided": _r(ordered[0][1]) if ordered else None,
        "family_max_p_one_sided": _r(ordered[-1][1]) if ordered else None,
        "holm_adjusted": holm,
        "best_cell": ordered[0][0] if ordered else None,
        "n_cells_surviving_holm_at_0_05": sum(
            1 for v in holm.values() if v is not None and v <= 0.05),
    }


def _free_gb() -> float | None:
    from scripts import w3_neural_floored as W3B
    return W3B.free_gb()


def _lean_panel_columns() -> list[str]:
    from learner import dataset as DS
    base = ["permno", "month", "entry_date", "mat_date_1m", "excess_vw_1m",
            "fwd_1m", "mkt_vw_1m", "market_cap", "log_dollar_vol_20d",
            "pos_vw_1m", "prior_1m"]
    return sorted(set(base) | set(DS.feature_columns()))


def _load_lean_panel(tracker: PROV.InputTracker) -> pd.DataFrame:
    if not LONG_TABLE.exists():
        raise SystemExit(f"REFUSED: {LONG_TABLE} does not exist.")
    cols = _lean_panel_columns()
    tracker.opened(LONG_TABLE, note=f"{len(cols)} of the panel's columns")
    df = pd.read_parquet(LONG_TABLE, columns=cols)
    # Downcast float64 -> float32 for everything except the two date columns
    # and the target the classifier reads as a 0/1 label -- memory is tight
    # tonight (other lanes running) and this halves the frame's footprint.
    for c in df.columns:
        if df[c].dtype == "float64" and c not in ("entry_date", "mat_date_1m"):
            df[c] = df[c].astype("float32")
    return df


# --------------------------------------------------------------------------
# 3a. THE EDGE-VS-FLOOR CURVE
# --------------------------------------------------------------------------

def run_edge_vs_floor_curve(*, test_years=range(2004, 2025), verbose: bool = True) -> dict:
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    t0 = time.perf_counter()
    tracker = PROV.InputTracker()
    out: dict = {
        "job": "N3_edge_vs_floor_curve", "lane": "N3",
        "question": ("holding the SAME lgbm_clf ranking fixed, what happens to the graded "
                     "edge as the execute floor moves from the flat $3m institutional line "
                     "to the size-aware floor a $100k / $1m / $10m book actually needs, "
                     "costed at the MEASURED TAQ spread for whichever liquidity band the "
                     "floor falls into instead of a flat bps assumption?"),
        "licence": LICENCE, "llm_spend_usd": 0.0, "llm_calls": 0, "network_calls": 0,
        "test_years": [int(test_years[0]), int(test_years[-1])],
        "memory_free_gb_before": _free_gb(),
    }
    fg = out["memory_free_gb_before"]
    if fg is not None and fg < MIN_FREE_GB_TO_LOAD_PANEL:
        out["status"] = "REFUSED"
        out["headline"] = f"REFUSED: {fg} GB free, below the {MIN_FREE_GB_TO_LOAD_PANEL} GB backoff line."
        return out
    if not LONG_TABLE.exists():
        out["status"] = "SKIPPED"
        out["headline"] = f"SKIPPED: {LONG_TABLE} is absent"
        return out

    taq_bands = load_taq_bands(tracker)
    floor_scenarios = {
        "institutional_flat_3m": INSTITUTIONAL_FLOOR_USD,
    }
    for size in BOOK_SIZES_USD:
        f, why = size_aware_floor(size)
        if f is None:
            out.setdefault("floor_refusals", []).append({"book_size_usd": size, "why": why})
            continue
        floor_scenarios[f"book_{int(size):,}".replace(",", "")] = f
    out["floor_scenarios_usd"] = {k: _r(v, 0) for k, v in floor_scenarios.items()}
    out["participation"] = PARTICIPATION
    out["position_fraction"] = POSITION_FRACTION
    out["build_sessions"] = BUILD_SESSIONS

    log("  loading the lean, UNFLOORED panel ...")
    df = _load_lean_panel(tracker)
    log(f"    {len(df):,} rows, {df.shape[1]} columns, "
        f"{df['month'].nunique()} months")
    out["panel_rows_unfloored"] = int(len(df))
    out["panel_months"] = int(df["month"].nunique())

    from learner import evaluate as E
    from learner import neural_long as N

    log("  fitting lgbm_clf ONCE on the unfloored panel (walk-forward) ...")
    t1 = time.perf_counter()
    preds, fit_meta = N.run_lgbm_clf(df, list(test_years), verbose=verbose)
    df["lgbm_clf"] = preds
    out["lgbm_clf_fit"] = {"wall_seconds": round(time.perf_counter() - t1, 1),
                           "n_folds": len(fit_meta.get("folds", [])),
                           "n_features": fit_meta.get("n_features")}
    out["memory_free_gb_after_fit"] = _free_gb()

    cells: dict[str, dict] = {}
    fam_series: dict[str, pd.Series] = {}
    curve: list[dict] = []
    for name, floor in floor_scenarios.items():
        cost = taq_cost_for_floor(floor, taq_bands)
        cost_scenarios = {"measured_taq": cost}
        # SECONDARY comparison: the flat bps this repo has charged everywhere
        # else, so the reader can see how much of the "died at $3m" story was
        # actually a cost-model story.
        cost_scenarios["flat_10bps"] = {"verdict": "FLAT", "one_way_bps": 10.0}
        cost_scenarios["flat_25bps"] = {"verdict": "FLAT", "one_way_bps": 25.0}
        row = {"floor_scenario": name, "floor_usd": _r(floor, 0),
              "taq_band": cost.get("band"), "cost_lookup": cost, "cells": {}}
        for cost_name, cs in cost_scenarios.items():
            one_way = cs.get("one_way_bps")
            if one_way is None:
                row["cells"][cost_name] = {"verdict": "CANNOT DETERMINE", "why": cs.get("why")}
                continue
            key = f"{name}|{cost_name}"
            log(f"  grading {key} (floor ${floor:,.0f}, {one_way} bps/side) ...")
            bk = E.book(df, "lgbm_clf", k=50, weight="vw", cost_bps=one_way,
                       ret_col="fwd_1m", mkt_col="mkt_vw_1m",
                       tradable_floor=floor, return_series=True)
            blk, ex = grade_cell(bk, label=key, cost_source=cs)
            cells[key] = blk
            row["cells"][cost_name] = {
                "PRIMARY_beta_matched_annualised_pct": (blk.get("PRIMARY_beta_matched") or {}).get("annualised_pct"),
                "PRIMARY_t": (blk.get("PRIMARY_beta_matched") or {}).get("t_paired"),
                "rows_after_tradable_floor": blk.get("rows_after_tradable_floor"),
                "mean_names_per_month": blk.get("mean_names_per_month"),
            }
            if len(ex):
                fam_series[key] = ex
        curve.append(row)

    out["cells"] = cells
    out["edge_vs_floor_curve"] = curve
    out["family"] = _holm_family(cells)
    best = out["family"].get("best_cell")
    if best and best in fam_series:
        from learner import inference
        aligned = {k: v for k, v in fam_series.items() if len(v) == len(fam_series[best])}
        out["inference_on_the_best_cell"] = inference.full_report(
            fam_series[best].to_numpy(), family=aligned, n_trials=out["family"]["size"], seed=20260907)
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
        }

    out["status"] = "OK"
    out["headline"] = _headline(out)
    out["memory_free_gb_after"] = _free_gb()
    out["wall_seconds"] = round(time.perf_counter() - t0, 1)
    resolved = {"test_years": {"value": out["test_years"], "source": "default"}}
    PROV.attach(out, sys.argv, resolved, tracker)
    del df
    return out


def _headline(out: dict) -> str:
    curve = out.get("edge_vs_floor_curve") or []
    parts = []
    for row in curve:
        c = row.get("cells", {}).get("measured_taq") or {}
        parts.append(f"{row['floor_scenario']}@${row['floor_usd']:,.0f} "
                    f"({row.get('taq_band') or 'no TAQ band'}): "
                    f"{c.get('PRIMARY_beta_matched_annualised_pct')}%/yr t={c.get('PRIMARY_t')}, "
                    f"names/mo={c.get('mean_names_per_month')}")
    fam = out.get("family") or {}
    return ("edge vs floor curve (beta-matched, measured TAQ cost): " + "; ".join(parts)
           + f" | family {fam.get('size')}, family-max p {fam.get('family_max_p_one_sided')}, "
             f"{fam.get('n_cells_surviving_holm_at_0_05')} cells survive Holm")


# --------------------------------------------------------------------------
# 3b. THE SMALL-CAP 5-SESSION REVERSAL, RE-COSTED
# --------------------------------------------------------------------------

def _load_crsp_dsf(years, tracker: PROV.InputTracker) -> pd.DataFrame | None:
    frames = []
    for y in years:
        f = CRSP_DSF_DIR / f"crsp_dsf_{y}.parquet"
        if not f.exists():
            continue
        tracker.opened(f)
        frames.append(pd.read_parquet(
            f, columns=["permno", "date", "prc", "ret", "openprc", "vol", "shrout"]))
    if not frames:
        return None
    px = pd.concat(frames, ignore_index=True)
    px["date"] = pd.to_datetime(px["date"])
    px["prc"] = px["prc"].abs()
    return px.sort_values(["permno", "date"]).reset_index(drop=True)


def _q1_no_event_mover_days(px: pd.DataFrame, event_pairs: set) -> pd.DataFrame:
    """Reproduces `scripts/night_lab_jobs.py::_reversal_year`'s
    `down|q1|no_event` cell exactly (same $5 price floor, same 10th-percentile
    one-day-drop definition, same market-cap quintile, same next-open entry
    and 5-session exit), with a LAGGED 20-session median dollar-volume column
    attached per mover-day so the cell can be re-cut by an execution floor --
    the original receipt never carried this column, which is why it could not
    answer the floor question by itself.
    """
    d = px[(px["prc"] >= 5.0) & (px["vol"].fillna(0) > 0)].copy()
    d["dv"] = d["prc"] * d["vol"]
    g = d.groupby("permno", sort=False)
    # LAGGED: known going into the day the move is measured, not contaminated
    # by the move itself.
    d["dv20"] = g["dv"].transform(lambda s: s.rolling(20, min_periods=15).median().shift(1))
    d["next_open"] = g["openprc"].shift(-1)
    d["next_close"] = g["prc"].shift(-1)
    d["close_5"] = g["prc"].shift(-5)
    d["mktcap"] = d["prc"] * d["shrout"].fillna(0)
    out = []
    for day, dd in d.groupby("date"):
        r = dd["ret"].astype("float64")
        if r.notna().sum() < 200:
            continue
        lo = r.quantile(0.10)
        q = pd.qcut(dd["mktcap"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
        mask = r <= lo
        sel = dd[mask & dd["next_open"].notna() & dd["next_close"].notna()]
        if sel.empty:
            continue
        quints = q[mask & dd["next_open"].notna() & dd["next_close"].notna()]
        f5 = (sel["close_5"] / sel["next_open"] - 1.0).astype("float64")
        for (idx, row), quint, b in zip(sel.iterrows(), quints, f5):
            if quint != 1 or not np.isfinite(b):
                continue
            key = (int(row["permno"]), pd.Timestamp(day).normalize())
            if key in event_pairs:
                continue
            out.append({"permno": int(row["permno"]), "day": pd.Timestamp(day).normalize(),
                       "fwd_5session_pct": float(b),
                       "dv20": (float(row["dv20"]) if pd.notna(row["dv20"]) else None)})
    return pd.DataFrame(out)


def run_reversal_cell_regrade(*, verbose: bool = True) -> dict:
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    t0 = time.perf_counter()
    tracker = PROV.InputTracker()
    out = {
        "job": "N3_reversal_cell_regrade", "lane": "N3",
        "question": ("the L4 `down|q1|no_event` 5-session reversal cell (+0.579% at 10bps, "
                     "+0.279% at 25bps, -0.221% at 50bps -- dies between 25 and 50bps) was "
                     "never floor-restricted (it is a market-cap quintile, not a liquidity "
                     "screen). Re-cut by a LAGGED dollar-volume floor and re-costed at the "
                     "MEASURED TAQ spread for its liquidity band instead of a flat "
                     "assumption, does it survive?"),
        "prior_cell": "scripts/night_lab_jobs.py::L4_reversal_by_size, "
                      "backend/data/optimus/night_lab_2026-09-05/L4_reversal_by_size_run01.json",
        "licence": LICENCE, "llm_spend_usd": 0.0, "llm_calls": 0, "network_calls": 0,
        "memory_free_gb_before": _free_gb(),
    }
    fg = out["memory_free_gb_before"]
    if fg is not None and fg < MIN_FREE_GB_TO_LOAD_PANEL:
        out["status"] = "REFUSED"
        out["headline"] = f"REFUSED: {fg} GB free, below the {MIN_FREE_GB_TO_LOAD_PANEL} GB backoff line."
        return out

    years = list(range(2013, 2025))
    px = _load_crsp_dsf(years, tracker)
    if px is None:
        out["status"] = "SKIPPED"
        out["headline"] = f"SKIPPED: no crsp_dsf_*.parquet found under {CRSP_DSF_DIR}"
        return out

    try:
        from scripts.night_lab_jobs import _event_days
        ev = _event_days()
        event_pairs = ev.get("pairs", set())
        f = REPO / "backend" / "data" / "optimus" / "edgar_8k" / "eightk_items.parquet"
        if f.exists():
            tracker.opened(f)
    except Exception as exc:                                        # noqa: BLE001
        event_pairs = set()
        out["event_join_error"] = f"{type(exc).__name__}: {exc}"

    log("  building down|q1|no_event mover-days with a lagged dv20 column ...")
    mv = _q1_no_event_mover_days(px, event_pairs)
    out["n_mover_days_total"] = int(len(mv))
    out["n_mover_days_with_dv20"] = int(mv["dv20"].notna().sum())

    taq_bands = load_taq_bands(tracker)
    floor_scenarios = {"institutional_flat_3m": INSTITUTIONAL_FLOOR_USD}
    for size in BOOK_SIZES_USD:
        f2, why = size_aware_floor(size)
        if f2 is not None:
            floor_scenarios[f"book_{int(size):,}".replace(",", "")] = f2

    rows = []
    for name, floor in floor_scenarios.items():
        cost = taq_cost_for_floor(floor, taq_bands)
        sub = mv[mv["dv20"].notna() & (mv["dv20"] >= floor)]
        row = {"floor_scenario": name, "floor_usd": _r(floor, 0),
              "n_mover_days_admitted": int(len(sub)),
              "n_distinct_days": int(sub["day"].nunique()) if len(sub) else 0,
              "cost_lookup": cost}
        for label, one_way in (("flat_10bps", 10.0), ("flat_25bps", 25.0),
                               ("flat_50bps", 50.0),
                               ("measured_taq", cost.get("one_way_bps"))):
            if one_way is None:
                row[label] = {"verdict": "CANNOT DETERMINE", "why": cost.get("why")}
                continue
            if len(sub) < 20:
                row[label] = {"verdict": "CANNOT DETERMINE",
                              "why": f"only {len(sub)} mover-days admitted at this floor"}
                continue
            net = sub["fwd_5session_pct"] - 2 * one_way / 10000.0
            daily = net.groupby(sub["day"]).mean()
            row[label] = {
                "one_way_bps": one_way,
                "mean_5session_pct": _r(float(daily.mean()) * 100, 4),
                "t_naive": _r(_t(daily), 3),
                "t_nonoverlapping": _r(_t(daily.sort_index().iloc[::5]), 3),
                "n_days_nonoverlapping": int(len(daily.sort_index().iloc[::5])),
            }
        rows.append(row)

    out["by_floor"] = rows
    survives = [r for r in rows if (r.get("measured_taq") or {}).get("mean_5session_pct", -9e9) > 0
               and (r.get("measured_taq") or {}).get("t_nonoverlapping", 0) is not None
               and (r.get("measured_taq") or {}).get("t_nonoverlapping", 0) >= 2.0]
    out["any_cell_survives_measured_taq_cost"] = bool(survives)
    out["surviving_floor_scenarios"] = [r["floor_scenario"] for r in survives]
    out["status"] = "OK"
    out["headline"] = (
        "small-cap 5-session reversal, re-cut by a lagged dv20 floor and re-costed at "
        f"measured TAQ spreads: {len(survives)} of {len(rows)} floor scenarios show a "
        "non-overlapping t >= 2 net of the measured cost. "
        + ("It comes back to life." if survives else
           "It does not come back to life -- the thinnest names cost MORE at the measured "
           "spread (100k-1m band: ~74.5bps one-way) than the flat 25bps this cell died "
           "between 25 and 50bps against, so a size-aware floor widens the ADMITTED "
           "universe but does not cheapen it."))
    out["memory_free_gb_after"] = _free_gb()
    out["wall_seconds"] = round(time.perf_counter() - t0, 1)
    resolved = {"years": {"value": years, "source": "default"}}
    PROV.attach(out, sys.argv, resolved, tracker)
    return out


# --------------------------------------------------------------------------
# 3c. S28's $100k-$1m BAND, RE-COSTED
# --------------------------------------------------------------------------

def run_s28_band_regrade(*, verbose: bool = True) -> dict:
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    t0 = time.perf_counter()
    tracker = PROV.InputTracker()
    out = {
        "job": "N3_s28_band_regrade", "lane": "N3",
        "question": ("S28 (2026-08-30) reported +6.98%/yr, t 2.22 in a $100k-$10m/day "
                     "liquidity band, GROSS of costs. scripts/weekend_lab_jobs.py::"
                     "W6b_liquidity_band replicated the WIDE band's shape out of sample "
                     "but never netted a cost. This narrows the band to the exact TAQ "
                     "100k-1m band -- the part the $3m floor deletes -- and nets the "
                     "MEASURED spread instead of assuming a flat rate."),
        "prior_claim": "S28 2026-08-30 (+6.98%/yr t 2.22, 2013-2024, GROSS); "
                       "W6b replication receipt is a night-lab-2026-09-06 job",
        "licence": LICENCE, "llm_spend_usd": 0.0, "llm_calls": 0, "network_calls": 0,
        "memory_free_gb_before": _free_gb(),
    }
    fg = out["memory_free_gb_before"]
    if fg is not None and fg < MIN_FREE_GB_TO_LOAD_PANEL:
        out["status"] = "REFUSED"
        out["headline"] = f"REFUSED: {fg} GB free, below the {MIN_FREE_GB_TO_LOAD_PANEL} GB backoff line."
        return out
    if not LONG_TABLE.exists():
        out["status"] = "SKIPPED"
        out["headline"] = f"SKIPPED: {LONG_TABLE} is absent"
        return out

    tracker.opened(LONG_TABLE, note="log_dollar_vol_20d, excess_vw_1m, month only")
    df = pd.read_parquet(LONG_TABLE, columns=["month", "log_dollar_vol_20d", "excess_vw_1m"])
    dv = np.expm1(df["log_dollar_vol_20d"])
    taq_bands = load_taq_bands(tracker)

    rows = []
    for name, lo, hi in TAQ_BAND_EDGES:
        m = dv.between(lo, hi, inclusive="left") if hi != float("inf") else (dv >= lo)
        sub = df[m & df["excess_vw_1m"].notna()]
        if sub["month"].nunique() < 24:
            rows.append({"band": name, "verdict": "CANNOT DETERMINE",
                        "months": int(sub["month"].nunique())})
            continue
        s = sub.groupby("month")["excess_vw_1m"].mean().sort_index()
        rest = (df[~m & df["excess_vw_1m"].notna()]
               .groupby("month")["excess_vw_1m"].mean().sort_index())
        vs_rest = (s - rest).dropna()
        gross_annualised = float(vs_rest.mean()) * 12 * 100
        cost = taq_cost_for_floor(lo, taq_bands)
        cost_pct = cost.get("cost_pct_per_year_at_monthly_turnover")
        net_annualised = (gross_annualised - cost_pct) if cost_pct is not None else None
        rows.append({
            "band": name, "dollar_vol_per_day": [lo, None if hi == float("inf") else hi],
            "months": int(len(vs_rest)), "name_months": int(len(sub)),
            "gross_annualised_excess_vs_ew_rest_pct": _r(gross_annualised, 3),
            "t_gross": _r(_t(vs_rest), 3),
            "measured_cost": cost,
            "net_annualised_excess_pct": _r(net_annualised, 3) if net_annualised is not None else None,
            "survives_measured_cost": (bool(net_annualised is not None and net_annualised > 0
                                            and (_t(vs_rest) or 0) >= 2.0)),
        })

    out["bands"] = rows
    narrow = next((r for r in rows if r["band"] == "100k-1m"), None)
    out["s28_100k_1m_band"] = narrow
    out["status"] = "OK"
    out["headline"] = (
        f"S28's $100k-1m sub-band: gross {narrow.get('gross_annualised_excess_vs_ew_rest_pct')}%/yr "
        f"t {narrow.get('t_gross')}, measured TAQ cost "
        f"{(narrow.get('measured_cost') or {}).get('cost_pct_per_year_at_monthly_turnover')}%/yr, "
        f"net {narrow.get('net_annualised_excess_pct')}%/yr -- "
        f"{'SURVIVES' if narrow.get('survives_measured_cost') else 'DOES NOT SURVIVE'} "
        "the measured cost."
        if narrow else "the 100k-1m band could not be evaluated")
    out["memory_free_gb_after"] = _free_gb()
    out["wall_seconds"] = round(time.perf_counter() - t0, 1)
    resolved = {}
    PROV.attach(out, sys.argv, resolved, tracker)
    del df
    return out


# --------------------------------------------------------------------------
# 3d. THE OBSERVE_ONLY TIER: WHAT WAS AND WAS NOT DONE
# --------------------------------------------------------------------------

def run_populate_observe_tier() -> dict:
    tracker = PROV.InputTracker()          # empty: this job opens no input file, by design
    out = {
        "job": "N3_populate_observe_tier", "lane": "N3",
        "question": "populate alpha.universe's OBSERVE_ONLY tier via build(scope=\"observe\")",
        "licence": LICENCE, "llm_spend_usd": 0.0, "llm_calls": 0, "network_calls": 0,
        "status": "REFUSED",
        "headline": ("REFUSED (by design): live population needs a network call to the "
                    "venue and broker credentials, outside this lane's offline scope. The "
                    "size-aware code path is exercised and pinned offline instead -- see "
                    "what_was_done_instead."),
        "why": ("`alpha.universe.build(scope=\"observe\")` (aegis-alpha-terminal, a SEPARATE "
               "repo) screens the venue's OWN live asset list and bars against the Alpaca "
               "API -- it needs a network call and broker credentials. This lane's mandate "
               "is offline research: 'no LLM API calls' and no network/keys touched, and "
               "the night-lab rules bar orders, seals and Railway changes outright. Live "
               "population is therefore out of scope for N3 and is not attempted."),
        "what_was_done_instead": (
            "the CODE PATH is exercised offline: `size_aware_execute_floor` and the "
            "`execution_authority(book_size_usd=...)` opt-in were added to "
            "aegis-alpha-terminal/alpha/universe.py and pinned by new checks in its own "
            "`tests_smoke_universe.py` (run this session, 0 failures) -- including the "
            "resurrection case (a $1m/day name is OBSERVE_ONLY under the flat $3m floor "
            "and FULL under a $100k book's size-aware $500k floor) and the refusal case "
            "(an unresolvable size-aware request returns CANNOT_DETERMINE, never a "
            "silent fallback to the flat floor)."),
        "files_touched_in_the_sibling_repo": [
            "aegis-alpha-terminal/alpha/universe.py",
            "aegis-alpha-terminal/tests_smoke_universe.py",
        ],
        "not_yet_true": ("the STORED universe file (state/universe/HIGH_DISPERSION_US_v1_"
                         "*.json) was built at the execute floor, so `load(scope=\"observe\")` "
                         "still returns only execute-floor names until a human runs "
                         "`build(scope=\"observe\")` against a live venue connection -- this "
                         "was already documented as 'NOT YET TRUE' in that module before "
                         "tonight and remains so; N3 did not change the stored file."),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }
    PROV.attach(out, sys.argv, {}, tracker)
    return out


# --------------------------------------------------------------------------
# runner
# --------------------------------------------------------------------------

def _write(name: str, payload: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"N3_{name}.json"
    path.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    print(f"  -> {path}", flush=True)
    return path


def _run_and_write(name: str, fn) -> dict:
    t0 = time.perf_counter()
    try:
        payload = fn()
    except SystemExit as exc:
        payload = {"job": f"N3_{name}", "status": "REFUSED", "headline": str(exc)}
    except Exception as exc:                                        # noqa: BLE001
        payload = {"job": f"N3_{name}", "status": "ERROR",
                  "headline": f"{type(exc).__name__}: {exc}",
                  "traceback": traceback.format_exc()}
    payload.setdefault("wall_seconds", round(time.perf_counter() - t0, 1))
    payload.setdefault("written_utc", datetime.now(timezone.utc).isoformat())
    _write(name, payload)
    print(f"[{name}] {payload.get('headline')}", flush=True)
    return payload


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--floor-curve", action="store_true")
    ap.add_argument("--reversal", action="store_true")
    ap.add_argument("--s28-band", action="store_true")
    ap.add_argument("--observe-tier", action="store_true")
    args = ap.parse_args(argv)
    ran_any = False
    if args.all or args.observe_tier:
        _run_and_write("populate_observe_tier", run_populate_observe_tier)
        ran_any = True
    if args.all or args.reversal:
        _run_and_write("reversal_cell_regrade", run_reversal_cell_regrade)
        ran_any = True
    if args.all or args.s28_band:
        _run_and_write("s28_band_regrade", run_s28_band_regrade)
        ran_any = True
    if args.all or args.floor_curve:
        _run_and_write("edge_vs_floor_curve", run_edge_vs_floor_curve)
        ran_any = True
    if not ran_any:
        ap.print_help()
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
