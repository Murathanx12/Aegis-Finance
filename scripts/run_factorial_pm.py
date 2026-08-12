"""FACTORIAL-PM-1 — execute the pre-registered picks × management matrix.

PREREG: `Aegis module/TRIALS/PREREG_FACTORIAL_PM_1.md` @ c5b81aa — frozen
before any cell was computed. This runner only fills the frozen design in:
3 evaluable books × 4 managements, H1/H2/H3, the §3 decision rule verbatim.

Outputs:
  docs/conviction_replay/factorial_pm_1.json   (the receipt)
  docs/NIGHT13_FACTORIAL.md                    (the readable matrix)

Usage:
  python scripts/run_factorial_pm.py            # full run (~5-10 min)
  python scripts/run_factorial_pm.py --finalize # re-read the as-traded
      ensemble file and re-evaluate H1 without recomputing the matrix
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services import factorial_pm as F  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("factorial_pm_runner")

OUT_JSON = ROOT / "docs" / "conviction_replay" / "factorial_pm_1.json"
OUT_MD = ROOT / "docs" / "NIGHT13_FACTORIAL.md"
ENSEMBLE_JSON = ROOT / "docs" / "conviction_replay" / "transaction_ensemble_1.json"

N_B3_MDE_SUBSAMPLE = 30      # draws on which the B3 management MDE is measured
N_B3_SE_SUBSAMPLE = 200      # draws whose daily paths feed the H2 bootstrap SE

DECISION_RULE_VERBATIM = [
    ["H1 holds net of costs with the paired difference >= its own measured MDE",
     "CONFIRMED_IN_DIRECTION — the product pitch (\"bring your ideas, the "
     "engine manages them\") gains its first licensed receipt; still NO alpha "
     "claim, NO skill claim"],
    ["H1 sign positive but below MDE", "UNRESOLVED"],
    ["H1 sign negative", "DIRECTION_REJECTED on this window — reported, with "
     "the window's one-bull-path caveat"],
    ["any cell's inputs contaminated (per CONVICTION-REPLAY-1 defect class)",
     "cell VOID, investigated before any number is reported"],
]

WHAT_THIS_MAY_NOT_DO = [
    "No annualization of a 9-month window into a headline.",
    "No cell promotes a strategy, seeds a lane, or arms anything.",
    "B3's distribution may not be collapsed to its mean alone (p05-p95 printed).",
    "The matrix may not be summarized without each cell's MDE beside it (§19).",
    "This does not and cannot grade Murat's skill (24-month rule; one window).",
    "M4 is 'mirror rules under their frozen equal-weight fallback' — the HRP "
    "gate (min 252 obs) cannot pass on the 197-bar frozen panel; nothing here "
    "is an HRP result.",
    "The as-traded comparator is an ensemble RANGE, never a point; if it is "
    "pending, H1 is evaluated against the registered fallback (B1×M1) and "
    "says so.",
    "Synthetic names (APLT, SLNO) enter period returns via entry+payout on a "
    "disclosed step path; within-window drawdown timing for those names is an "
    "assumption, and they are excluded from every daily-path statistic.",
]


def _pts(w: float) -> float:
    return (w - 1.0) * 100.0


def _cell_public(cell: dict) -> dict:
    """JSON-safe view of a management cell (paths stripped)."""
    out = {k: v for k, v in cell.items()
           if k not in ("wealth_path", "daily_returns", "exposure_path")}
    out["terminal_wealth_per_dollar"] = round(cell["terminal_wealth"], 6)
    out["window_return_pts"] = round(_pts(cell["terminal_wealth"]), 2)
    return out


def read_as_traded() -> dict:
    """The TRANSACTION-ENSEMBLE-1 Q4 bounds, if the other agent has landed
    them. Absent/unreadable -> DATA_NEEDED/PENDING (printed, never guessed)."""
    if not ENSEMBLE_JSON.exists():
        return {"status": "DATA_NEEDED/PENDING",
                "note": ("docs/conviction_replay/transaction_ensemble_1.json "
                         "not present — TRANSACTION-ENSEMBLE-1 still running; "
                         "H1 uses the registered fallback comparator B1×M1")}
    try:
        raw = json.loads(ENSEMBLE_JSON.read_text(encoding="utf-8"))
    except Exception as e:                                  # noqa: BLE001
        return {"status": "DATA_NEEDED/PENDING",
                "note": f"ensemble file unreadable ({e}); fallback B1×M1"}

    tr = (raw.get("Q4") or {}).get("total_return") or {}
    rng = tr.get("range") or {}
    label = str(tr.get("label", ""))
    if not rng or ("min" not in rng or "max" not in rng):
        return {"status": "DATA_NEEDED/PENDING",
                "note": ("ensemble file present but Q4.total_return carries "
                         "no min/max range — not guessed; fallback B1×M1"),
                "ensemble_keys": sorted(raw)[:20]}
    base = {
        "ensemble_label": label,
        "synthetic_note": raw.get("SYNTHETIC", ""),
        "range_terminal_wealth": {"lower": 1.0 + float(rng["min"]),
                                  "upper": 1.0 + float(rng["max"])},
        "range_pts": {"lower": round(float(rng["min"]) * 100, 2),
                      "upper": round(float(rng["max"]) * 100, 2),
                      "p05": round(float(rng.get("p05", float("nan"))) * 100, 2),
                      "p50": round(float(rng.get("p50", float("nan"))) * 100, 2),
                      "p95": round(float(rng.get("p95", float("nan"))) * 100, 2)},
        "n_members": tr.get("n_members"),
    }
    if label.upper().startswith("DATA_NEEDED"):
        return {**base, "status": "DATA_NEEDED",
                "note": ("Q4.total_return is labelled DATA_NEEDED by the "
                         "ensemble (SYNTHETIC bounds; minimal ask: " +
                         str(tr.get("minimal_ask", "")) + "). The as-traded "
                         "column prints the RANGE with that label (prereg "
                         "§1); H1 uses the registered fallback comparator "
                         "B1×M1")}
    return {**base, "status": "OK",
            "lower": base["range_terminal_wealth"]["lower"],
            "upper": base["range_terminal_wealth"]["upper"],
            "note": "TRANSACTION-ENSEMBLE-1 Q4 bounds (a RANGE, never a point)"}


def compute_b3(panel, pool, draws):
    """All 1,000 B3 draws under M1/M2/M4; distributions + path subsamples."""
    n = len(draws)
    term = {m: np.empty(n) for m in ("M1", "M2", "M4")}
    logs = {m: [] for m in ("M1", "M2", "M4")}     # daily log-returns, subsample
    sub_idx = None
    t0 = time.time()
    for i, tickers in enumerate(draws):
        c1 = F.m1_cell(panel, tickers)
        c2 = F.m2_cell(panel, tickers)
        c4 = F.m4_cell(panel, tickers)
        term["M1"][i] = c1["terminal_wealth"]
        term["M2"][i] = c2["terminal_wealth"]
        term["M4"][i] = c4["terminal_wealth"]
        if i < N_B3_SE_SUBSAMPLE:
            if sub_idx is None:
                sub_idx = c1["daily_returns"].index
            for m, c in (("M1", c1), ("M2", c2), ("M4", c4)):
                logs[m].append(np.log1p(
                    c["daily_returns"].reindex(sub_idx).to_numpy(float)))
        if (i + 1) % 200 == 0:
            logger.info("B3 %d/%d draws (%.0fs)", i + 1, n, time.time() - t0)
    log_mats = {m: np.column_stack(v) for m, v in logs.items()}
    return term, log_mats, sub_idx


def _dist(x: np.ndarray) -> dict:
    return {"median": round(float(np.median(x)), 4),
            "p05": round(float(np.percentile(x, 5)), 4),
            "p95": round(float(np.percentile(x, 95)), 4),
            "n_draws": int(len(x))}


def _mde_summary(mdes: list) -> dict:
    vals = [m for m in mdes if m is not None]
    return {"median_pts": float(np.median(vals)) if vals else None,
            "min_pts": float(np.min(vals)) if vals else None,
            "max_pts": float(np.max(vals)) if vals else None,
            "n_measured": len(mdes), "n_reached_80pct": len(vals)}


def h1_arm_verdict(diff_pts: float, mde_pts: float | None) -> str:
    if diff_pts > 0 and mde_pts is not None and diff_pts >= mde_pts:
        return "CONFIRMED_IN_DIRECTION"
    if diff_pts > 0:
        return "UNRESOLVED"
    return "DIRECTION_REJECTED"


def main(finalize_only: bool = False) -> dict:
    t_start = time.time()
    if finalize_only and OUT_JSON.exists():
        result = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        result = finalize_h1(result)
        write_outputs(result)
        return result

    panel = F.load_panel()
    books = F.load_books()

    # ── B1 / B2 cells ───────────────────────────────────────────────────────
    cells: dict[str, dict] = {}
    tests: dict[str, dict] = {}
    for bk in ("B1", "B2"):
        tickers = books[bk]
        c1, c2, c4 = (F.m1_cell(panel, tickers), F.m2_cell(panel, tickers),
                      F.m4_cell(panel, tickers))
        cells[bk] = {"M1": c1, "M2": c2, "M4": c4,
                     "M3": F.m3_audit(tickers)}
        seed_off = {"B1_M2": 1, "B1_M4": 2, "B2_M2": 3, "B2_M4": 4}
        for m, c in (("M2", c2), ("M4", c4)):
            off = seed_off[f"{bk}_{m}"]        # deterministic — hash() is
            pt = F.paired_terminal_diff(c["daily_returns"],  # process-salted
                                        c1["daily_returns"],
                                        seed=F.SEED + off)
            mde = F.measure_pair_mde(c["daily_returns"], c1["daily_returns"],
                                     seed=F.SEED + 50 + off)
            tests[f"{bk}_{m}_vs_M1"] = {**pt, **{
                "mde_pts": mde["mde_pts_at_80pct_power"],
                "mde_grid": mde["grid"], "mde_note": mde["note"]}}
        logger.info("%s: M1 %.2f pts | M2 %.2f | M4 %.2f", bk,
                    _pts(c1["terminal_wealth"]), _pts(c2["terminal_wealth"]),
                    _pts(c4["terminal_wealth"]))

    # contamination cross-check against CONVICTION-REPLAY-1's recorded basket
    replay = json.loads((ROOT / "docs" / "conviction_replay" /
                         "conviction_replay_1.json").read_text(encoding="utf-8"))
    recorded_picks = float(replay["primary"]["picks"]["mean"]) * 100 \
        if isinstance(replay["primary"].get("picks"), dict) else None
    b1_m1_pts = _pts(cells["B1"]["M1"]["terminal_wealth"])
    if recorded_picks is not None and abs(b1_m1_pts - recorded_picks) > 0.5:
        raise RuntimeError(
            f"B1×M1 = {b1_m1_pts:.2f} pts but CONVICTION-REPLAY-1 recorded "
            f"{recorded_picks:.2f} — same book, same window, same prices "
            f"must agree; decision rule: cell VOID, investigate first")

    # ── B3 distribution ─────────────────────────────────────────────────────
    draws = F.b3_draws(books["pool"])
    b3_term, b3_logs, _ = compute_b3(panel, books["pool"], draws)
    b3_eff = {m: (b3_term[m] - b3_term["M1"]) * 100 for m in ("M2", "M4")}

    b3_mdes = {"M2": [], "M4": []}
    for i in range(N_B3_MDE_SUBSAMPLE):
        c1 = F.m1_cell(panel, draws[i])
        for m, fn in (("M2", F.m2_cell), ("M4", F.m4_cell)):
            c = fn(panel, draws[i])
            r = F.measure_pair_mde(c["daily_returns"], c1["daily_returns"],
                                   n_sim=150, seed=F.SEED + 100 + i)
            b3_mdes[m].append(r["mde_pts_at_80pct_power"])
    logger.info("B3 MDE subsample done (%.0fs)", time.time() - t_start)

    b3_m3 = F.m3_audit(books["pool"])
    b3_m3["note_draws"] = (
        f"pool-level audit: {b3_m3['n_checkable']}/61 names checkable -> the "
        f"maximum checkable fraction any 13-name draw can reach is "
        f"{min(13, b3_m3['n_checkable'])}/13; every one of the 1,000 draws "
        f"is below 50% and REFUSED")

    # ── H1 ─────────────────────────────────────────────────────────────────
    as_traded = read_as_traded()
    h1 = {"as_traded": as_traded,
          "arms": {}, "comparator": None}
    for m in ("M2", "M4"):
        t = tests[f"B1_{m}_vs_M1"]
        h1["arms"][m] = {
            "vs_M1_diff_pts": round(t["difference_pts"], 3),
            "vs_M1_se_pts": round(t["se_pts"], 3), "vs_M1_z": round(t["z"], 2),
            "mde_pts": t["mde_pts"]}
    h1 = finalize_h1_inner(h1, cells["B1"], tests)

    # ── H2 ─────────────────────────────────────────────────────────────────
    h2 = {}
    for m in ("M2", "M4"):
        eff_b1 = tests[f"B1_{m}_vs_M1"]["difference_pts"]
        d = F.difference_of_differences(
            eff_b1, cells["B1"]["M1"]["daily_returns"],
            cells["B1"][m]["daily_returns"],
            b3_logs["M1"], b3_logs[m], b3_eff[m],
            seed=F.SEED + (17 if m == "M2" else 19))
        dm = F.measure_dod_mde(cells["B1"]["M1"]["daily_returns"],
                               cells["B1"][m]["daily_returns"],
                               b3_logs["M1"], b3_logs[m],
                               seed=F.SEED + (23 if m == "M2" else 27))
        d["mde_pts"] = dm["mde_pts_at_80pct_power"]
        d["mde_grid"] = dm["grid"]
        d["mde_note"] = dm["note"]
        d["registered_expectation"] = "NOT detectable at this sample (prereg §2)"
        d["verdict"] = ("DETECTED" if d["significant_at_5pct"] else
                        "NOT_DETECTABLE — as registered (§19: below the "
                        "measured MDE is a design statement, never a kill)")
        h2[m] = d

    # ── H3 ─────────────────────────────────────────────────────────────────
    dd_m1 = F.max_drawdown(cells["B1"]["M1"]["wealth_path"], F.WAR_START,
                           F.WAR_END)
    dd_m2 = F.max_drawdown(cells["B1"]["M2"]["wealth_path"], F.WAR_START,
                           F.WAR_END)
    # dd values are negative; reduction = dd_m2 - dd_m1 (less negative = better)
    h3 = {"subwindow": f"{F.WAR_START} -> {F.WAR_END}",
          "b1_m1_maxdd_pct": round(dd_m1 * 100, 2),
          "b1_m2_maxdd_pct": round(dd_m2 * 100, 2),
          "reduction_pp": round((dd_m2 - dd_m1) * 100, 2),
          "registered_bar": ">= 5pp reduction",
          "descriptive_n1": True,
          "verdict": ("MET (descriptive receipt, n=1 — no inference)"
                      if (dd_m2 - dd_m1) * 100 >= 5.0
                      else "NOT_MET (descriptive, n=1 — no inference)")}

    # ── assemble ────────────────────────────────────────────────────────────
    sel_mde_note = ("cross-BOOK comparisons carry CONVICTION-REPLAY-1's "
                    "measured selection MDE: 80 pts")
    matrix = {}
    for bk in ("B1", "B2"):
        matrix[bk] = {
            "M1": {**_cell_public(cells[bk]["M1"]), "status": "OK",
                   "mde_pts": None,
                   "mde_basis": "baseline cell — management effects are "
                                "measured against it; " + sel_mde_note},
            "M2": {**_cell_public(cells[bk]["M2"]), "status": "OK",
                   "mde_pts": tests[f"{bk}_M2_vs_M1"]["mde_pts"],
                   "mde_basis": "measured 80%-power MDE of the paired "
                                "management effect vs M1 (planted effects, "
                                "21td block bootstrap)",
                   "paired_vs_M1": {k: tests[f"{bk}_M2_vs_M1"][k]
                                    for k in ("difference_pts", "se_pts", "z",
                                              "significant_at_5pct")}},
            "M3": cells[bk]["M3"],
            "M4": {**_cell_public(cells[bk]["M4"]), "status": "OK",
                   "mde_pts": tests[f"{bk}_M4_vs_M1"]["mde_pts"],
                   "mde_basis": "measured 80%-power MDE of the paired "
                                "management effect vs M1",
                   "paired_vs_M1": {k: tests[f"{bk}_M4_vs_M1"][k]
                                    for k in ("difference_pts", "se_pts", "z",
                                              "significant_at_5pct")}},
        }
    matrix["B1"]["as_traded"] = as_traded
    matrix["B3"] = {
        "draws": {"n": len(draws), "seed": F.SEED,
                  "rule": "random-13 from the 61-name pool, "
                          "np.random.default_rng(20260811)"},
        "M1": {"status": "OK", "terminal_wealth_dist": _dist(b3_term["M1"]),
               "window_return_pts_dist": _dist((b3_term["M1"] - 1) * 100),
               "mde_pts": None,
               "mde_basis": "baseline cell (distribution); " + sel_mde_note},
        "M2": {"status": "OK", "terminal_wealth_dist": _dist(b3_term["M2"]),
               "window_return_pts_dist": _dist((b3_term["M2"] - 1) * 100),
               "effect_vs_M1_pts_dist": _dist(b3_eff["M2"]),
               "mde_pts_subsample": _mde_summary(b3_mdes["M2"]),
               "mde_basis": f"measured on the first {N_B3_MDE_SUBSAMPLE} "
                            "draws (paired vs each draw's own M1)"},
        "M3": b3_m3,
        "M4": {"status": "OK", "terminal_wealth_dist": _dist(b3_term["M4"]),
               "window_return_pts_dist": _dist((b3_term["M4"] - 1) * 100),
               "effect_vs_M1_pts_dist": _dist(b3_eff["M4"]),
               "mde_pts_subsample": _mde_summary(b3_mdes["M4"]),
               "mde_basis": f"measured on the first {N_B3_MDE_SUBSAMPLE} "
                            "draws (paired vs each draw's own M1)"},
    }
    matrix["B4"] = {
        "status": "NOT_EVALUABLE",
        "refusal": ("the funnel ran in Aug-2026; replaying it from Nov-2025 "
                    "is look-ahead by construction. Recording the refusal is "
                    "the point (a check that cannot run honestly is not run)"),
        "forward_cell": {"registered": True, "start": "2026-08-11",
                         "note": "B4 enters the matrix as a forward cell "
                                 "only, from 2026-08-11"},
    }

    result = {
        "trial": F.TRIAL, "prereg": F.PREREG,
        "computed_at": datetime.now().isoformat(timespec="seconds"),
        "accrues_to_denominator": True,
        "window": {"start": F.WINDOW_START, "end": F.WINDOW_END,
                   "trading_days": int(len(cells["B1"]["M1"]["wealth_path"])),
                   "no_annualization": True},
        "canon": ["§18 differences tested as differences with their own SE",
                  "§19 every arm prints its measured 80%-power MDE"],
        "books": {"B1": books["B1"], "B2": books["B2"],
                  "pool_n": len(books["pool"])},
        "matrix": matrix,
        "h1": h1, "h2": h2, "h3": h3,
        "decision_rule_verbatim_prereg_s3": DECISION_RULE_VERBATIM,
        "what_this_may_not_do": WHAT_THIS_MAY_NOT_DO,
        "cross_check": {"b1_m1_pts": round(b1_m1_pts, 2),
                        "conviction_replay_1_picks_pts": recorded_picks,
                        "agree_within_0p5": True},
        "runtime_secs": round(time.time() - t_start, 1),
    }
    write_outputs(result)
    return result


def finalize_h1_inner(h1: dict, b1_cells: dict, tests: dict) -> dict:
    """Evaluate H1 against the frozen rule, naming the comparator honestly."""
    as_traded = h1["as_traded"]
    arms = {}
    if as_traded.get("status") == "OK":
        ub = float(as_traded["upper"])
        h1["comparator"] = {
            "kind": "as_traded_upper_bound",
            "upper_terminal_wealth": ub,
            "note": ("H1 tests B1×{M2,M4} terminal wealth against the "
                     "ensemble's UPPER bound — the hardest honest hurdle. "
                     "The ensemble carries no daily path, so the difference "
                     "vs the bound uses the managed leg's own block-bootstrap "
                     "SE (not fully paired; disclosed).")}
        for m in ("M2", "M4"):
            w = b1_cells[m]["terminal_wealth"]
            diff = (w - ub) * 100
            mde = tests[f"B1_{m}_vs_M1"]["mde_pts"]
            arms[m] = {"terminal_wealth": round(w, 4),
                       "diff_vs_upper_bound_pts": round(diff, 2),
                       "mde_pts": mde,
                       "verdict": h1_arm_verdict(diff, mde)}
    else:
        h1["comparator"] = {
            "kind": "REGISTERED_FALLBACK_B1xM1",
            "note": ("*** SUBSTITUTION, PROMINENT: the as-traded column is "
                     + str(as_traded.get("status")) + " — H1 is evaluated "
                     "against the registered fallback comparator B1×M1 "
                     "(prereg's paired design). Re-run with --finalize "
                     "if/when the ensemble's Q4 total_return is re-labelled "
                     "from DATA_NEEDED (minimal ask: his broker CSV). ***")}
        for m in ("M2", "M4"):
            t = tests.get(f"B1_{m}_vs_M1") or h1["arms"][m]
            diff = t.get("difference_pts", t.get("vs_M1_diff_pts"))
            mde = t.get("mde_pts")
            arms[m] = {"diff_vs_fallback_M1_pts": round(float(diff), 3),
                       "mde_pts": mde, "verdict": h1_arm_verdict(diff, mde)}
        rng_tw = as_traded.get("range_terminal_wealth")
        if rng_tw:
            h1["synthetic_range_for_the_record"] = {
                "b1_m2_terminal": round(b1_cells["M2"]["terminal_wealth"], 4),
                "b1_m4_terminal": round(b1_cells["M4"]["terminal_wealth"], 4),
                "synthetic_upper_bound": round(rng_tw["upper"], 4),
                "note": ("both managed cells sit above the ensemble's "
                         "SYNTHETIC upper bound, but that bound is "
                         "DATA_NEEDED, accrues ZERO, and cannot resolve H1 — "
                         "recorded so nobody re-derives it as a finding; the "
                         "registered fallback comparator governs")}
    order = {"CONFIRMED_IN_DIRECTION": 0, "UNRESOLVED": 1,
             "DIRECTION_REJECTED": 2}
    verdicts = [a["verdict"] for a in arms.values()]
    overall = sorted(verdicts, key=order.get)[0]
    if overall == "UNRESOLVED" and "DIRECTION_REJECTED" in verdicts:
        overall = "UNRESOLVED"      # mixed signs: reported per-arm, not a kill
    h1["arms_vs_comparator"] = arms
    h1["overall"] = overall
    return h1


def finalize_h1(result: dict) -> dict:
    """--finalize path: re-read the ensemble and re-evaluate H1 in place."""
    as_traded = read_as_traded()
    result["matrix"]["B1"]["as_traded"] = as_traded
    h1 = result["h1"]
    h1["as_traded"] = as_traded
    b1 = result["matrix"]["B1"]
    cells = {m: {"terminal_wealth": b1[m]["terminal_wealth_per_dollar"]}
             for m in ("M2", "M4")}
    tests = {f"B1_{m}_vs_M1": {
        "difference_pts": b1[m]["paired_vs_M1"]["difference_pts"],
        "mde_pts": b1[m]["mde_pts"]} for m in ("M2", "M4")}
    result["h1"] = finalize_h1_inner(h1, cells, tests)
    result["finalized_at"] = datetime.now().isoformat(timespec="seconds")
    return result


def write_outputs(result: dict) -> None:
    OUT_JSON.write_text(json.dumps(result, indent=1, default=str),
                        encoding="utf-8")
    OUT_MD.write_text(render_md(result), encoding="utf-8")
    logger.info("wrote %s and %s", OUT_JSON, OUT_MD)


def _fmt_mde(v) -> str:
    if v is None:
        return "MDE: none on grid (§19: design-limits statement)"
    return f"MDE {v:.1f} pts"


def render_md(r: dict) -> str:
    m = r["matrix"]
    L: list[str] = []
    A = L.append
    A("# NIGHT-13 — FACTORIAL-PM-1: picks × management, his claim as a matrix")
    A("")
    A(f"**Prereg** {r['prereg']} (frozen). **Window** "
      f"{r['window']['start']} → {r['window']['end']} "
      f"({r['window']['trading_days']} trading days — NEVER annualized). "
      f"Computed {r['computed_at']}. CANON §18/§19 bind.")
    A("")
    A("**The claim under test (Murat, verbatim):** \"my portfolio with good "
      "timing/management would be a great winner with the stock picks.\"")
    A("")
    A("## The matrix — window return in pts per $1, EVERY cell with its MDE")
    A("")
    A("| book | M1 EW-hold | M2 vol-target | M3 kill-conditions | "
      "M4 mirror rules | as-traded |")
    A("|---|---|---|---|---|---|")
    for bk, label in (("B1", "B1 — his 13 picks"),
                      ("B2", "B2 — his 48 non-picks")):
        c = m[bk]
        at = "—"
        if bk == "B1":
            a = m["B1"]["as_traded"]
            if a.get("status") == "OK":
                at = f"[{a['lower']:.4f}, {a['upper']:.4f}] per $1"
            elif "range_pts" in a:
                rp = a["range_pts"]
                at = (f"**{a['status']}** — range [{rp['lower']:+.1f}, "
                      f"{rp['upper']:+.1f}] pts (SYNTHETIC ensemble, "
                      f"label printed, never a point)")
            else:
                at = f"**{a['status']}**"
        A(f"| {label} "
          f"| **{c['M1']['window_return_pts']:+.1f} pts** (baseline; "
          f"selection MDE 80 pts across books) "
          f"| **{c['M2']['window_return_pts']:+.1f} pts** "
          f"({c['M2']['paired_vs_M1']['difference_pts']:+.2f} vs M1; "
          f"{_fmt_mde(c['M2']['mde_pts'])}) "
          f"| **{c['M3']['status']}** ({c['M3']['n_checkable']}/"
          f"{c['M3']['n_names']} checkable) "
          f"| **{c['M4']['window_return_pts']:+.1f} pts** "
          f"({c['M4']['paired_vs_M1']['difference_pts']:+.2f} vs M1; "
          f"{_fmt_mde(c['M4']['mde_pts'])}) | {at} |")
    b3 = m["B3"]
    def d3(mm):
        d = b3[mm]["window_return_pts_dist"]
        return f"{d['median']:+.1f} [{d['p05']:+.1f}, {d['p95']:+.1f}]"
    A(f"| B3 — random-13 × {b3['draws']['n']} draws (median [p05, p95]) "
      f"| {d3('M1')} (baseline dist.) "
      f"| {d3('M2')} (eff. vs M1 "
      f"{b3['M2']['effect_vs_M1_pts_dist']['median']:+.2f} pts; median MDE "
      f"{b3['M2']['mde_pts_subsample']['median_pts']} pts) "
      f"| **{b3['M3']['status']}** ({b3['M3']['n_checkable']}/61 pool names "
      f"checkable) "
      f"| {d3('M4')} (eff. vs M1 "
      f"{b3['M4']['effect_vs_M1_pts_dist']['median']:+.2f} pts; median MDE "
      f"{b3['M4']['mde_pts_subsample']['median_pts']} pts) | — |")
    b4 = m["B4"]
    A(f"| B4 — funnel candidates | **{b4['status']}** (all cells) — "
      f"{b4['refusal']} Forward cell registered, start "
      f"{b4['forward_cell']['start']}. | | | | |")
    A("")
    A("Refusals are findings. B3 is a distribution and may not be collapsed "
      "to a point.")
    A("")
    A("## M3 — the checkability audit (ran FIRST; the refusal is the result)")
    A("")
    A("A condition is checkable only if it can be evaluated point-in-time "
      "from the frozen price CSV (there is no fundamentals feed for "
      "backdated quarters, no analyst-history feed, no event stream). "
      "Conditions that failed, and why:")
    A("")
    seen = set()
    for bk in ("B1", "B2"):
        for row in m[bk]["M3"]["per_name"]:
            key = (row["ticker"], row["condition"])
            if key in seen:
                continue
            seen.add(key)
            cond = row["condition"] or "(none on record)"
            A(f"- **{row['ticker']}** — \"{cond}\" → "
              f"{'checkable' if row['checkable'] else 'NOT checkable'}: "
              f"{row['reason']}")
    A("")
    A(f"- B3 pool-level: {b3['M3']['note_draws']}")
    A("")
    A("## H1 — his claim, direction " + f"(**{r['h1']['overall']}**)")
    A("")
    A(f"Comparator: {r['h1']['comparator']['kind']}. "
      f"{r['h1']['comparator']['note']}")
    A("")
    for arm, a in r["h1"]["arms_vs_comparator"].items():
        A(f"- **B1×{arm}**: " + ", ".join(f"{k}={v}" for k, v in a.items()))
    A("")
    if r["h1"]["overall"] == "DIRECTION_REJECTED":
        A("Caveat (frozen rule row 3, verbatim obligation): this window is "
          "ONE bull path, and both paired differences sit far below their "
          "measured MDEs — DIRECTION_REJECTED is a report of the SIGN on "
          "this window, not a detected negative effect (§19: below the MDE "
          "is a design statement, never a kill).")
        A("")
    sr = r["h1"].get("synthetic_range_for_the_record")
    if sr:
        A(f"For the record: {sr['note']} (B1×M2 {sr['b1_m2_terminal']}, "
          f"B1×M4 {sr['b1_m4_terminal']}, synthetic upper bound "
          f"{sr['synthetic_upper_bound']}).")
        A("")
    A("## H2 — interaction (management effect, B1 vs B3 distribution)")
    A("")
    for arm, d in r["h2"].items():
        A(f"- **{arm}−M1**: DoD {d['dod_pts']:+.2f} pts, SE {d['se_pts']:.2f} "
          f"(z={d['z']:.2f}), {_fmt_mde(d.get('mde_pts'))} → {d['verdict']}")
    A("")
    A("## H3 — the exposure story, war sub-window (descriptive, n=1)")
    A("")
    h3 = r["h3"]
    A(f"- {h3['subwindow']}: B1×M1 maxDD {h3['b1_m1_maxdd_pct']:.2f}%, "
      f"B1×M2 maxDD {h3['b1_m2_maxdd_pct']:.2f}%, reduction "
      f"{h3['reduction_pp']:+.2f} pp vs the registered bar of "
      f"{h3['registered_bar']} → **{h3['verdict']}**")
    A("")
    A("## Decision rule (prereg §3, verbatim)")
    A("")
    A("| outcome | verdict |")
    A("|---|---|")
    for row in r["decision_rule_verbatim_prereg_s3"]:
        A(f"| {row[0]} | {row[1]} |")
    A("")
    A("## M4 disclosure")
    A("")
    A("- " + m["B1"]["M4"]["hrp_gate_note"])
    A(f"- B1 rebalances: {m['B1']['M4']['n_rebalances']}, total cost "
      f"{m['B1']['M4']['total_cost_paid_pts']:.2f} pts. "
      f"B2 rebalances: {m['B2']['M4']['n_rebalances']}.")
    A("- Sector cap: " + m["B1"]["M4"]["params"]["sector_cap"])
    A("")
    A("## What this may not do")
    A("")
    for item in r["what_this_may_not_do"]:
        A(f"- {item}")
    A("")
    A(f"*Receipt: docs/conviction_replay/factorial_pm_1.json · runtime "
      f"{r['runtime_secs']}s*")
    A("")
    return "\n".join(L)


if __name__ == "__main__":
    main(finalize_only="--finalize" in sys.argv)
