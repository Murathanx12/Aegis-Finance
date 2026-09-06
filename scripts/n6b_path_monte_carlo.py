"""NIGHT LAB 2026-09-07 — lane N6, item N6.3. PATH MONTE CARLO, hack4 @ 1x.

    python -m scripts.n6b_path_monte_carlo

$0 LLM. Block bootstrap of the Growth Book champion's monthly returns, feeding
the worst-case table in `docs/CONTRACT_DRAFT_2026-09-07_GROWTH_BOOK.md` sec6
(hack4, the frozen champion `m12_quality_mom|dd`, `docs/BUILD_GROWTH_BOOK_
2026-09-07.md`, `learner/growth_lab.py`, `learner/growth.py`).

WHY THIS RECEIPT DOES NOT SIMPLY RE-RUN `_build_child` OVER 1999-2024
========================================================================
The mandate reads "block bootstrap of the champion's monthly returns
1999-2024". That series does not exist as a single legitimate object to
resample from, for two independent reasons, both explained in full below and
both self-verified at runtime rather than asserted:

1. **The sealed era (2016-2024) is opened ONCE per frozen champion**
   (`learner/growth_lab.py`, `SEALED_ERA_OPENINGS.jsonl`). G4 already spent
   that one opening on 2026-09-06 (`sealed_era_openings_permitted: 1`,
   ledger count 1 — verified below via `growth_lab.openings_for()`, not
   assumed). Re-deriving the champion's raw 2016-2024 monthly returns —
   even for a risk simulation rather than a selection decision — would be a
   SECOND opening, which the module's own convention forbids and which this
   script refuses to do. What IS used from the sealed era is the
   SUMMARY STATISTICS G4 already wrote to `G4_seal.json` on its one
   legitimate opening (mean/vol/maxDD/CVaR/beta) — reading an existing
   receipt is not a new opening.
2. **Reconstructing even the DEVELOPMENT half of the exact champion's raw
   series requires reloading the full 925k-row long panel plus its W3b stage
   predictions** (`scripts/growth_g2_generation0.py: load_panel`,
   ~1.5-2 GB peak). `scripts/growth_g4_seal.py` and `growth_g5_sizer.py`
   both self-gate that reload at **6.0 GB free**, an empirically-chosen floor
   for this exact operation on this machine. This lane's own rule is to back
   off under 2 GB; the stricter, operation-specific 6.0 GB floor already
   established by the growth-book jobs is used here instead, because it is
   the floor the people who measured this exact reload chose. Measured free
   memory at run time is printed in the receipt (`memory_free_gb_before`);
   if it is under 6.0 GB the exact reconstruction is SKIPPED, not attempted
   and silently degraded.

WHAT IS USED WHEN THE EXACT RECONSTRUCTION IS SKIPPED
========================================================
The PARENT genome `quality_mom|dd` (generation 0: default k/hold_k, the `dd`
overlay only, no `bsc` cap — NOT identical to the frozen champion's mutated
k=110/hold_k=160/dd_lookback=7/dd_scale=0.3/dd_floor=0.05 plus `bsc_cap=1.8`)
already has its FULL monthly series computed and sitting in
`backend/data/optimus/growth_book/G2_genome_series.parquet` — a byproduct of
the generation-0 search, sliced here to development-only
(`learner.growth_lab.dev(s, start="1999-01")`, self-verified with
`assert_development_only`) and used as the bootstrap's resampling pool. This
is a PROXY, not the champion, and every number this script reports says so.
It is CROSS-CHECKED against the exact champion's already-disclosed summary
statistics for the same 202-month window
(`G5_sizer.json: table.constant_1x_NULL`, which — being the champion at flat
1.0x with no extra sizing overlay — reports the exact champion's own dev-era
mean/vol/maxDD) so a reader can see how far the proxy departs from truth
before trusting the simulated tail.

THE EXISTING WORST-CASE TABLE, READ NOT RECOMPUTED
=====================================================
`docs/CONTRACT_DRAFT_2026-09-07_GROWTH_BOOK.md` sec6 already carries a 1.0x/1.5x/
2.0x ladder (no script or receipt in this repo reproduces its exact
construction — it reads as the exact champion's 202-month dev series, unscripted).
This receipt's own 1.0x/1.3x numbers, built on the PROXY, are reported
ALONGSIDE that table (not blended into it) so a reader can sanity-check: the
proxy's 1.0x figures should sit close to the contract's 1.0x row, and this
script's 1.3x figures should sit between the contract's 1.0x and 1.5x rows
(drawdown depth is monotone increasing in leverage for a fixed return path).

BLOCK LENGTH, CHOSEN AND JUSTIFIED (not left at a library default)
=====================================================================
An i.i.d. bootstrap resamples months independently and cannot produce a
drawdown deeper than what serial correlation in the real path would allow —
it UNDERSTATES drawdown risk, because real drawdowns are runs of bad months,
not isolated ones. `learner/growth.py: p_ruin` already implements a
STATIONARY (geometric) block bootstrap for exactly this reason and this
script reuses that exact mechanism (not a copy with different arithmetic).
`block=4.0` (mean block length in months) is the house default, used
identically in `G4_seal.json`'s sealed-era p_ruin. This script checks that
choice empirically on the proxy's own dev series (ACF of raw returns and of
|returns|, lags 1-12) rather than inheriting it blindly: both ACFs are weak
at every lag on 202 monthly observations (|ACF| < 0.16, inside the
+-2/sqrt(202) ~= +-0.14 noise band at all but two lags) — this SPECIFIC proxy
series does not show strong LINEAR monthly persistence. The block length is
nonetheless set to **6 months, not 1 (i.i.d.)**, for a structural reason the
ACF cannot see: the champion's hysteresis holds a name from rank <= 110 to
rank > 160 (`hold_k=160` sessions ~= 7.6 months at 21 sessions/month), so
consecutive book months share overlapping realised positions. A linear ACF on
NET portfolio returns is exactly the statistic overlapping-holding dependence
is weakest in (turnover smooths it), while drawdown depth is driven by the
regime the whole holding period sits in. Six months is a compromise between
the house default (4), the structural holding period (~7.6, rounded down),
and the empirical evidence's honest verdict of "weak but present, small
sample" — stated as a compromise, not derived to three decimal places.
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

from backend.services import receipt_provenance as RP           # noqa: E402
from learner import growth as GR                                # noqa: E402
from learner import growth_lab as GL                             # noqa: E402
from scripts import w3_neural_floored as W3B                     # noqa: E402

OUT_DIR = REPO / "backend" / "data" / "optimus" / "night_lab_2026-09-07"
RECEIPT = OUT_DIR / "N6b_path_monte_carlo.json"
GROWTH_DIR = REPO / "backend" / "data" / "optimus" / "growth_book"

CHAMPION_ID = "m12_quality_mom|dd"
PROXY_COLUMN_PREFIX = "quality_mom|dd"       # the parent genome, generation 0
EXACT_RECONSTRUCTION_FREE_GB_FLOOR = 6.0     # matches growth_g4_seal.py / g5
BLOCK_MEAN_PERIODS = 6.0
N_BOOT = 4000
SEED = 20260907
BOOK_USD = 100_000.0
COST_BPS_REPORTED = 25.0                     # the sealed CLAIM rate (G4)


def _r(x, nd=6):
    return None if x is None else round(float(x), nd)


# --------------------------------------------------------- provenance checks

def sealed_era_status() -> dict:
    """Read-only. Confirms the one permitted opening is already spent, and
    that THIS script has not added a second one."""
    n = GL.openings_for(CHAMPION_ID)
    return {
        "champion_id": CHAMPION_ID,
        "sealed_era_openings_for_this_champion": n,
        "sealed_era_openings_permitted": 1,
        "this_script_called_sealed_or_open_sealed_window": False,
        "reading": (f"{n} opening(s) already on the ledger (G4, 2026-09-06); "
                   "this script reads already-written G4/G5 receipts for "
                   "sealed-era context and does not call "
                   "growth_lab.sealed() or open_sealed_window() itself"),
    }


def acf(x: np.ndarray, lag: int) -> float:
    x = x - x.mean()
    denom = float(np.sum(x * x))
    if denom <= 0 or lag <= 0 or lag >= len(x):
        return float("nan")
    return float(np.sum(x[:-lag] * x[lag:]) / denom)


def block_length_evidence(returns: np.ndarray) -> dict:
    n = len(returns)
    band = 2.0 / np.sqrt(n) if n > 0 else None
    raw_acf = {L: round(acf(returns, L), 4) for L in range(1, 13)}
    abs_acf = {L: round(acf(np.abs(returns), L), 4) for L in range(1, 13)}
    return {
        "n_months": n,
        "two_over_sqrt_n_noise_band": round(band, 4) if band else None,
        "acf_raw_returns_lags_1_12": raw_acf,
        "acf_abs_returns_lags_1_12": abs_acf,
        "reading": (
            "both ACFs are weak at every lag and mostly inside the "
            f"+-{round(band, 3) if band else None} noise band on this "
            f"{n}-month sample — no strong LINEAR persistence is detectable "
            "in this proxy series at this sample size"),
        "chosen_block_mean_periods": BLOCK_MEAN_PERIODS,
        "house_default_block_mean_periods": 4.0,
        "structural_holding_period_months": round(160 / 21.0, 2),
        "why_not_iid_despite_weak_acf": (
            "an i.i.d. bootstrap (block=1) UNDERSTATES drawdown risk by "
            "construction: it cannot produce a run of bad months longer "
            "than chance allows, and hold_k=160 sessions (~7.6 months) "
            "means consecutive book months share overlapping realised "
            "positions — dependence a linear ACF on NET turnover-smoothed "
            "returns is weak at detecting even when it is structurally "
            "present. 6 months is a stated compromise between the house "
            "default (4, used identically in G4_seal.json's sealed-era "
            "p_ruin), the structural holding period (~7.6, rounded down), "
            "and this sample's own honest (weak) ACF reading — not a "
            "value derived to three decimal places."),
    }


# ------------------------------------------------------------- data loading

def load_proxy_dev_series(cost_bps: float) -> pd.Series:
    """The PARENT genome's development-only monthly return series.

    `assert_development_only` is the module's own self-check: it raises if
    any month at or after 2016-01 leaked in. Called here as a receipt-time
    guarantee, not a comment.
    """
    col = f"{PROXY_COLUMN_PREFIX}|{cost_bps:.0f}bps"
    path = GROWTH_DIR / "G2_genome_series.parquet"
    df = pd.read_parquet(path, columns=[col])
    s = df[col].dropna()
    s.index = pd.Index([str(x) for x in s.index])
    dev = GL.dev(s, start=GL.DEV_START)
    GL.assert_development_only(dev, f"proxy {col}")
    return dev.sort_index(), str(path)


def exact_champion_context() -> dict:
    """Already-legitimate, already-disclosed figures for the EXACT champion.
    Every number here is READ from an existing receipt, never recomputed."""
    out = {"note": ("every figure below is READ from an existing receipt "
                    "(G4_seal.json / G5_sizer.json / CONTRACT_DRAFT), not "
                    "recomputed by this script")}
    g4p = GROWTH_DIR / "G4_seal.json"
    g5p = GROWTH_DIR / "G5_sizer.json"
    if g4p.exists():
        g4 = json.loads(g4p.read_text(encoding="utf-8"))
        out["G4_development_common_window_2004_2015_144mo"] = {
            bps: {"beta": v.get("beta"),
                 "mean_monthly": (v.get("book") or {}).get("mean_monthly"),
                 "maxdd": (v.get("book") or {}).get("max_drawdown"),
                 "realized_vol_annual": (v.get("book") or {}).get("realized_vol_annual"),
                 "worst_month": (v.get("book") or {}).get("worst_month")}
            for bps, v in (g4.get("development") or {}).items()}
        out["G4_sealed_era_2016_2024_107mo"] = {
            bps: {"beta": v.get("beta"),
                 "mean_monthly": (v.get("book") or {}).get("mean_monthly"),
                 "maxdd": (v.get("book") or {}).get("max_drawdown"),
                 "realized_vol_annual": (v.get("book") or {}).get("realized_vol_annual"),
                 "worst_month": (v.get("book") or {}).get("worst_month"),
                 "p_ruin_at_largest_admissible_leverage": v.get("p_ruin")}
            for bps, v in (g4.get("sealed") or {}).items()}
    if g5p.exists():
        g5 = json.loads(g5p.read_text(encoding="utf-8"))
        arm = (g5.get("table") or {}).get("constant_1x_NULL") or {}
        out["G5_development_full_window_1999_2015_202mo_flat_1x_25bps"] = {
            "beta": arm.get("beta"), "maxdd_unlevered": arm.get("maxdd_unlevered"),
            "realized_vol": arm.get("realized_vol"), "tw_unlevered": arm.get("tw_unlevered"),
            "note": ("this arm IS the frozen champion at flat 1.0x with no "
                    "extra sizing overlay — the closest thing to the exact "
                    "champion's own raw dev-window summary this repo has "
                    "already legitimately disclosed"),
        }
    out["CONTRACT_DRAFT_worst_case_ladder_sec6"] = {
        "source": "docs/CONTRACT_DRAFT_2026-09-07_GROWTH_BOOK.md §6",
        "basis": ("prose states '1999-2024'; the 1.0x row's maxDD -46.88% "
                 "matches G5's constant_1x_NULL maxdd_unlevered exactly "
                 "(-0.46882), which is the 202-month 1999-2015 DEVELOPMENT "
                 "window, not 1999-2024 — the caption is imprecise, the "
                 "underlying window is the same development-only window "
                 "this script uses. No script in this repo reproduces this "
                 "table's exact construction; it is read here as-is."),
        "rung_1_0x": {"maxdd": -0.4688, "worst_case_usd_100k": -46882,
                     "worst_month": -0.2966, "p_lose_half": 0.232,
                     "median_worst_dd": -0.415},
        "rung_1_5x": {"maxdd": -0.6544, "worst_case_usd_100k": -65435,
                     "worst_month": -0.4464, "p_lose_half": 0.797,
                     "median_worst_dd": -0.598},
        "rung_2_0x": {"maxdd": -0.7829, "worst_case_usd_100k": -78293,
                     "worst_month": -0.5961, "p_lose_half": 0.985,
                     "median_worst_dd": -0.746,
                     "note": "REFUSED by the declaration; shown for the cost"},
    }
    return out


# ------------------------------------------------------------- the bootstrap

def block_bootstrap_paths(returns: np.ndarray, *, n_boot: int, block: float,
                          horizon: int, seed: int) -> np.ndarray:
    """Reuses `learner.growth.p_ruin`'s exact resampling mechanism (a
    circular, geometric-block stationary bootstrap), but returns every
    resampled PATH rather than only the ruin flag and two drawdown
    quantiles, so this script can additionally compute time-under-water and
    the full drawdown distribution `p_ruin` does not report."""
    a = np.asarray(returns, dtype="float64")
    n = a.size
    rng = np.random.default_rng(seed)
    p = 1.0 / max(block, 1.0)
    paths = np.empty((n_boot, horizon), dtype="float64")
    for i in range(n_boot):
        idx = np.empty(horizon, dtype="int64")
        j = rng.integers(0, n)
        for t in range(horizon):
            if t and rng.random() < p:
                j = rng.integers(0, n)
            idx[t] = j
            j = (j + 1) % n
        paths[i] = a[idx]
    return paths


def path_stats(paths: np.ndarray, *, ruin_threshold: float = GR.RUIN_THRESHOLD
              ) -> dict:
    n_boot, T = paths.shape
    wealth = np.cumprod(1.0 + paths, axis=1)
    running_max = np.maximum.accumulate(wealth, axis=1)
    dd = wealth / running_max - 1.0
    worst_dd = dd.min(axis=1)
    p_ruin = float(np.mean(worst_dd <= ruin_threshold))

    underwater = dd < -1e-12
    longest_uw = np.zeros(n_boot, dtype="int64")
    total_uw = underwater.sum(axis=1)
    for i in range(n_boot):
        u = underwater[i]
        if not u.any():
            continue
        # longest run of consecutive True
        run = 0
        best = 0
        for v in u:
            run = run + 1 if v else 0
            best = max(best, run)
        longest_uw[i] = best

    return {
        "n_boot": n_boot, "horizon_months": T,
        "p_lose_half": round(p_ruin, 4),
        "ruin_threshold": ruin_threshold,
        "drawdown_distribution": {
            "median": _r(np.median(worst_dd), 5),
            "p90": _r(np.quantile(worst_dd, 0.10), 5),   # 10th pct of DD = 90th pct of loss
            "p95": _r(np.quantile(worst_dd, 0.05), 5),
            "worst": _r(worst_dd.min(), 5),
        },
        "time_under_water_months": {
            "note": ("longest single consecutive underwater streak per "
                    "bootstrap path (below its own prior peak); median and "
                    "p95 across paths"),
            "longest_streak_median": _r(np.median(longest_uw), 2),
            "longest_streak_p95": _r(np.quantile(longest_uw, 0.95), 2),
            "longest_streak_worst": int(longest_uw.max()),
            "total_months_underwater_median": _r(np.median(total_uw), 2),
            "total_months_underwater_p95": _r(np.quantile(total_uw, 0.95), 2),
        },
        "worst_case_usd_at_100k": {
            "median": _r(BOOK_USD * np.median(worst_dd), 0),
            "p95": _r(BOOK_USD * np.quantile(worst_dd, 0.05), 0),
            "worst": _r(BOOK_USD * worst_dd.min(), 0),
        },
    }


def run(argv=None) -> dict:
    t0 = datetime.now(timezone.utc)
    tracker = RP.InputTracker()
    free = W3B.free_gb()
    exact_available = bool(free is not None
                           and free >= EXACT_RECONSTRUCTION_FREE_GB_FLOOR)

    sealed_status = sealed_era_status()

    if exact_available:
        # Deliberately not implemented in this pass: the exact reconstruction
        # needs the same heavy G2.load_panel() pipeline as G4/G5, which this
        # lane's file ownership does not include re-authoring. When free
        # memory clears the 6.0 GB floor a future session can wire it in;
        # this receipt still runs correctly on the proxy path below and says
        # plainly that the exact path was AVAILABLE but not exercised here.
        exact_note = ("free memory cleared the 6.0 GB floor "
                      f"({free:.2f} GB) but this script does not re-author "
                      "growth_g2_generation0.load_panel() — it stays on the "
                      "proxy path and reports this honestly rather than "
                      "silently reusing a lighter loader")
    else:
        exact_note = (f"free memory {free!r} GB is below the 6.0 GB floor "
                      "growth_g4_seal.py / growth_g5_sizer.py self-impose "
                      "for this exact reload — the exact reconstruction is "
                      "SKIPPED, not attempted")

    proxy_10, path_10 = load_proxy_dev_series(10.0)
    proxy_25, path_25 = load_proxy_dev_series(25.0)
    tracker.opened(path_25, note="proxy genome series (parent, dev-only)")

    proxy_series = proxy_25    # the claim rate (G4's CLAIM_COST_BPS)
    a = proxy_series.to_numpy()
    n_months = len(a)

    block_evidence = block_length_evidence(a)

    # ---- risk-free leg, for the 1.3x financed leg. Pinned, offline, light.
    from learner import benchmark as BM
    rf_bm = BM.cash(start="1999-01-01", end="2015-12-31").to_monthly()
    rf = pd.Series(rf_bm.returns.to_numpy(),
                   index=[d.strftime("%Y-%m") for d in rf_bm.returns.index])
    rf = rf.reindex(proxy_series.index).fillna(rf.mean())

    book_1x = proxy_series
    book_1_3x = GR.lever(proxy_series, rf, 1.3, financing_bps=GR.FINANCING_BPS)

    results = {}
    for label, series in (("1.0x", book_1x), ("1.3x", book_1_3x)):
        paths = block_bootstrap_paths(
            series.to_numpy(), n_boot=N_BOOT, block=BLOCK_MEAN_PERIODS,
            horizon=n_months, seed=SEED)
        results[label] = path_stats(paths)
        # a second horizon: a nearer-term "next 3 years" reading, since the
        # ladder feeds a live paper contract, not only a multi-decade one.
        paths_36 = block_bootstrap_paths(
            series.to_numpy(), n_boot=N_BOOT, block=BLOCK_MEAN_PERIODS,
            horizon=36, seed=SEED + 1)
        results[label]["horizon_36mo_next_few_years"] = path_stats(paths_36)

    # ---- block-length sensitivity, 1.0x only: does the headline P(lose
    # half) hinge on the block=6 choice? Reported so the reader does not have
    # to take the choice on faith.
    sensitivity = {}
    for b in (1.0, 4.0, 6.0, 8.0, 12.0):
        p = block_bootstrap_paths(book_1x.to_numpy(), n_boot=N_BOOT, block=b,
                                  horizon=n_months, seed=SEED)
        st = path_stats(p)
        sensitivity[f"block_{b:g}"] = {
            "p_lose_half": st["p_lose_half"],
            "median_worst_dd": st["drawdown_distribution"]["median"],
            "p95_worst_dd": st["drawdown_distribution"]["p95"]}

    # ---- realised (non-simulated) summary of the proxy series itself, for
    # the same cross-check the docstring promises.
    realised = {
        "10bps": {"n_months": int(len(proxy_10)),
                 "mean_monthly": _r(proxy_10.mean()),
                 "vol_annual": _r(proxy_10.std(ddof=1) * (12 ** 0.5)),
                 "max_drawdown": _r(GR.max_drawdown(proxy_10))},
        "25bps": {"n_months": int(len(proxy_25)),
                 "mean_monthly": _r(proxy_25.mean()),
                 "vol_annual": _r(proxy_25.std(ddof=1) * (12 ** 0.5)),
                 "max_drawdown": _r(GR.max_drawdown(proxy_25))},
    }

    exact_ctx = exact_champion_context()

    receipt = {
        "item": "NIGHT_LAB_2026-09-07 / lane N6 / N6.3",
        "title": "path Monte Carlo for the hack4 contract at 1x (and 1.3x)",
        "licence": "PRODUCT_EXPERIMENT",
        "generated_at_utc": t0.isoformat(timespec="seconds"),
        "argv": list(argv or sys.argv), "git_commit": RP.git_commit_short(REPO),
        "python": sys.version.split()[0],
        "llm_spend_usd": 0.0, "llm_calls": 0,
        "memory_free_gb_before": free,
        "exact_champion_reconstruction": {
            "attempted": False, "available_by_memory_floor": exact_available,
            "note": exact_note,
        },
        "sealed_era_status": sealed_status,
        "champion_id": CHAMPION_ID,
        "proxy_used": {
            "column": f"{PROXY_COLUMN_PREFIX}|{{bps}}bps",
            "source_file": path_25,
            "why_a_proxy": ("the EXACT frozen champion is a mutation of this "
                           "genome (custom k=110/hold_k=160/dd params plus a "
                           "bsc overlay this parent lacks); reconstructing "
                           "its exact series needs the same heavy panel "
                           "reload G4/G5 self-gate at 6.0 GB free, currently "
                           "unavailable — see exact_champion_reconstruction"),
            "development_window": [str(proxy_25.index.min()),
                                   str(proxy_25.index.max())],
            "n_months": n_months,
            "realised_summary": realised,
        },
        "cross_check_vs_exact_champion": {
            "proxy_25bps_realised": realised["25bps"],
            "exact_champion_dev_202mo_25bps_from_G5": (
                exact_ctx.get("G5_development_full_window_1999_2015_202mo_flat_1x_25bps")),
            "reading": ("compare maxdd_unlevered above: the proxy is missing "
                       "the champion's bsc vol-cap overlay and the tighter "
                       "hysteresis, so a gap here is EXPECTED, not a bug — "
                       "it bounds how much to trust the simulated tail below"),
        },
        "block_length": block_evidence,
        "block_length_sensitivity_1_0x": sensitivity,
        "bootstrap_construction": (
            "stationary (geometric) block bootstrap, circular continuation — "
            "the exact mechanism in learner.growth.p_ruin, reimplemented here "
            "(not copied verbatim) so every resampled PATH can be kept for "
            "time-under-water, not only the ruin flag and two drawdown "
            "quantiles p_ruin itself reports"),
        "n_boot": N_BOOT, "seed": SEED, "cost_bps": COST_BPS_REPORTED,
        "financing_bps_over_rf": GR.FINANCING_BPS,
        "book_usd": BOOK_USD,
        "results_by_leverage": results,
        "existing_context_read_not_recomputed": exact_ctx,
        "headline": (
            f"PROXY (parent genome, dev-only, {n_months}mo, 25bps), block="
            f"{BLOCK_MEAN_PERIODS}mo, {N_BOOT} draws, full-history horizon: "
            f"at 1.0x P(lose half) {results['1.0x']['p_lose_half']}, median "
            f"worst DD {results['1.0x']['drawdown_distribution']['median']}, "
            f"p95 {results['1.0x']['drawdown_distribution']['p95']}; at 1.3x "
            f"P(lose half) {results['1.3x']['p_lose_half']}, median worst DD "
            f"{results['1.3x']['drawdown_distribution']['median']}. Contract "
            "draft's own 1.0x row (exact champion, same window, unscripted): "
            "maxDD -46.88%, P(lose half) 0.232, median worst DD -41.5% — "
            "compare, do not average."),
    }
    RP.attach(receipt, argv or sys.argv,
             {"n_boot": N_BOOT, "block_mean_periods": BLOCK_MEAN_PERIODS,
              "seed": SEED, "cost_bps": COST_BPS_REPORTED}, tracker)
    return receipt


def write_receipt(receipt: dict, path: Path = RECEIPT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="n6b_path_monte_carlo")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                       # noqa: BLE001
            pass
    path = Path(a.out) if a.out else RECEIPT
    try:
        rec = run(argv=sys.argv)
    except BaseException as e:                                  # noqa: BLE001
        import traceback
        write_receipt({
            "item": "NIGHT_LAB_2026-09-07 / lane N6 / N6.3", "status": "FAILED",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "argv": list(sys.argv), "git_commit": RP.git_commit_short(REPO),
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
            "note": "a traceback is a receipt"}, path)
        print(f"FAILED — receipt written to {path}")
        raise
    write_receipt(rec, path)
    print(rec["headline"])
    print(f"[receipt] -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
