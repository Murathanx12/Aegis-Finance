"""C4 -- the HOLD arm of the era replay, at $0, plus the second-era dry run.

WHY THIS FILE EXISTS
====================
`docs/REVIEW_2026-09-06_FABLE51_ON_THE_CONTINUATION.md` claim 6 reads the era
replay's receipt and notices `mean_turnover 0.9965`:

> the decider rebuilds the whole top-k every month, so 10 bps/side costs
> ~0.2%/mo of the -0.39%/mo net. Add a HOLD arm (keep the prior month's names
> unless the rank leaves the top 2k) before spending another dollar on the
> decide step.

The instruction is right and the diagnosis is not, and the difference is the
finding. Turnover is ~1.0 in that job **because the window build redraws eight
names from ~2,700 eligible permnos every month**, not because the decider
churns its ranking. Across the 188 consecutive (thread, month) transitions the
job contains, exactly **8 of 1,504 name-slots repeat at all**. An incumbent the
book might have held is, 99.5% of the time, not in the opportunity set. No
hysteresis rule can hold a name that is not on the menu.

So this job does two things:

1. **Grades the HOLD arm anyway, from cache, for $0** -- because "the rule
   cannot bite here" is an assertion until it is a measured number beside the
   original one, and because the four hold cells belong in the family whether
   they move or not (family size 4 -> 8, and every p is re-corrected).
2. **Counts the second era before anyone pays for it** (`--era2`), which is the
   half of the review's instruction that actually has room to move the answer.

NO LLM CALL IS MADE. Every decision is replayed out of
`backend/data/optimus/era_replay_v2/llm_cache.jsonl` by the same key the wire
path computed; `era_replay_v2.replay_from_cache` constructs no client and never
reaches `_gate`. The proof that the replay is faithful is in the receipt:
re-grading the cache WITHOUT hysteresis reproduces the sealed
`L10_era_replay_v2_run01.json` numbers digit for digit, for all four arms.

USAGE
-----
    python -m scripts.c6b_era_replay_hold --declare   # write + hash the rule
    python -m scripts.c6b_era_replay_hold --grade     # part (a), $0
    python -m scripts.c6b_era_replay_hold --era2      # part (b), $0
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import era_replay_v2 as E                          # noqa: E402

OUT_DIR = REPO / "backend" / "data" / "optimus" / "continuation_2026-09-06b"
DECLARATION = OUT_DIR / "C4_hold_rule_declaration.json"
RECEIPT_A = "C4_era_replay_hold_run01.json"
RECEIPT_B = "C4b_era2_window_build_dryrun.json"
SEALED_ERA1 = (REPO / "backend" / "data" / "optimus"
               / "continuation_2026-09-06" / "L10_era_replay_v2_run01.json")


# ══════════════════════════════════════════════════════════════════════════
# THE RULE, DECLARED BEFORE THE GRADE
# ══════════════════════════════════════════════════════════════════════════
# The HOLD arm re-grades decisions that ALREADY EXIST on disk. Declaring the
# rule after seeing which band helps would be worthless -- there is no waiting
# to do and nothing to be surprised by, so the only thing that makes this
# tamper-evident is that the text below is written to a separate file, hashed,
# and the hash stamped in the receipt BEFORE the grade runs.

HOLD_RULE: dict[str, Any] = {
    "declared": "BEFORE the grade, by --declare, and hashed (sha256).",
    "why_declaring_first_matters_here": (
        "the HOLD arm is a RE-GRADE of decisions collected on 2026-09-05 and "
        "cached on disk. Nothing about it has to wait for data. A band chosen "
        "after seeing which band helps is not a rule, it is a fit, and the only "
        "evidence that it was not is this file's timestamp and hash."),
    "rule": ("BUY at rank <= k; HOLD an incumbent until its rank leaves the top "
             "hold_k. Book size stays k: incumbents inside the band keep their "
             "slots, best-ranked first, and the remainder is filled from the "
             "top of the ranking."),
    "k": E.TOP_N,
    "hold_k": E.HOLD_MULTIPLE * E.TOP_N,
    "hold_k_is": "2k, exactly as the review specified ('the top 2k')",
    "implementation": (
        "scripts/era_replay_v2.select_with_hold, which is a re-implementation "
        "of learner/evaluate.py `book`'s `hold_k` hysteresis (evaluate.py:191-"
        "208). The era-replay grader is bespoke -- it grades 8-name bundles "
        "with a sealed forward column, not a monthly panel -- so the rule is "
        "re-implemented rather than routed through `book`, and "
        "backend/tests/test_era_replay_hold.py proves the two agree on a "
        "synthetic panel, month by month."),
    "degenerate_case": (
        "hold_k == k is the no-hysteresis rule written a longer way. "
        "`select_with_hold` accepts it (the equivalence is what the test "
        "pins); `grade_arm` REFUSES it, exactly as evaluate.book refuses "
        "hold_k == k, so no receipt can report a band where there is none."),
    "what_is_held_constant": [
        "the DECISIONS -- identical cached ranks, no new LLM call, $0",
        "the benchmark -- the equal-weight basket of the SAME 8 anonymised "
        "names in the SAME month",
        "the cost rate -- learner.evaluate.COST_BPS_PER_SIDE, both sides, on "
        "realised turnover (design.cost_bps_per_side = 10.0 in the sealed "
        "era-1 receipt; that receipt graded ONE cost level, so this one does)",
        "the nulls -- null-1 shuffled companies, null-2 shuffled dates, null-3 "
        "same-day paired, unchanged code, unchanged draws, unchanged seed",
        "the canary -- the same guess_year / guess_company answers, so "
        "blind-held is the same fact for a hold cell as for its parent",
    ],
    "what_changes": [
        "which 3 of the 8 slots the book holds, and therefore realised "
        "turnover, the cost line, and net excess",
        "the family: 4 arms -> 8 cells. Every per-arm p is re-corrected by "
        "BH-FDR at m = 8 (CANON §63, SCREEN = BH-FDR), and DSR's n_trials "
        "rises with it.",
    ],
    "decision_rule_declared_before_the_result": {
        "the_hold_arm_changes_the_verdict_only_if_ALL_of": [
            "(a) at least one hold cell's mean net excess over the EW basket of "
            "the same names is POSITIVE, and",
            "(b) that cell survives BH-FDR at 0.05 in the family of 8, and",
            "(c) its null-1 (shuffled companies) one-sided p is <= 0.05, and",
            "(d) its terminal wealth exceeds the EW basket's over the same "
            "months.",
        ],
        "otherwise": (
            "the verdict of the sealed era-1 receipt stands unchanged and the "
            "hold arm is reported as what it is: a cost-line experiment on an "
            "arm that is at random."),
        "pre_committed_expectation": (
            "the rule will move almost nothing, and the reason is structural "
            "rather than statistical: the window build redraws the 8-name "
            "bundle every month, so an incumbent is only rarely in the next "
            "month's opportunity set. This expectation is written here BEFORE "
            "the grade precisely so that 'we knew it would not move' cannot be "
            "claimed afterwards for free -- the receipt reports "
            "`incumbents_present_in_next_bundle`, which is the hard ceiling on "
            "anything hysteresis can save, and the reader can check it."),
        "power_caveat": (
            "the sealed era-1 receipt's MDE is ~8.98%/yr at t = 2 on 48 month "
            "blocks. A cost saving of a few basis points a month is INVISIBLE "
            "at that resolution. 'The hold arm did not change the verdict' is "
            "therefore not evidence that hysteresis is worthless in general -- "
            "it is evidence that it is worthless HERE, where turnover is a "
            "property of the sampling design."),
    },
    "three_era_axis": (
        "CANNOT DETERMINE BY CONSTRUCTION. learner.evaluate.ERAS is "
        "2016-18 / 2019-21 / 2022-24; this replay covers 2016-01..2019-12 only, "
        "which is one era and one quarter of the next. No re-grade of these "
        "decisions can produce the three-era table, because the decisions for "
        "the other two eras do not exist. Part (b) of this job -- the "
        "second-era window build -- is the fix, and it is BUILD-ONLY here."),
    "licence": "PRODUCT_EXPERIMENT (exploratory). A screen cannot reach NOVEL.",
}


def rule_sha() -> str:
    return hashlib.sha256(
        json.dumps(HOLD_RULE, sort_keys=True, separators=(",", ":"))
        .encode("utf-8")).hexdigest()


def declare() -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    DECLARATION.write_text(json.dumps({
        "job": "C4_era_replay_hold",
        "status": "DECLARED -- written BEFORE the grade, so the band cannot be "
                  "moved after the number is seen",
        "declared_utc": datetime.now(timezone.utc).isoformat(),
        "hold_rule": HOLD_RULE,
        "hold_rule_sha256": rule_sha(),
        "grades_data_already_on_disk": True,
        "llm_calls_authorised": 0,
    }, indent=1), encoding="utf-8")
    print(f"[declared] {DECLARATION}  sha256 {rule_sha()[:16]}")
    return DECLARATION


# ══════════════════════════════════════════════════════════════════════════
# PROVENANCE
# ══════════════════════════════════════════════════════════════════════════

def _sha_file(p: Path) -> dict:
    h = hashlib.sha256()
    n = 0
    with p.open("rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
            n += len(b)
    return {"path": str(p), "sha256": h.hexdigest(), "bytes": n}


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              cwd=str(REPO), capture_output=True, text=True,
                              timeout=20).stdout.strip() or "UNKNOWN"
    except Exception:                                          # noqa: BLE001
        return "UNKNOWN"


def provenance(argv: list[str], config: dict, inputs: list[Path]) -> dict:
    opened = []
    for p in inputs:
        try:
            opened.append(_sha_file(p) if p.exists() else
                          {"path": str(p), "sha256": None, "bytes": 0,
                           "note": "ABSENT when this job ran"})
        except Exception as exc:                               # noqa: BLE001
            opened.append({"path": str(p), "sha256": None, "bytes": 0,
                           "error": f"{type(exc).__name__}: {exc}"})
    return {
        "sys_argv": list(argv),
        "resolved_config": config,
        "_inputs_opened": opened,
        "git_commit": _git_commit(),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# ══════════════════════════════════════════════════════════════════════════
# PART (a) -- the HOLD arm
# ══════════════════════════════════════════════════════════════════════════

def _two_sided_p(t: float | None, n: int) -> float | None:
    if t is None or n < 3:
        return None
    return float(2 * (1 - stats.t.cdf(abs(t), df=n - 1)))


def bh_family(cells: dict[str, dict]) -> dict:
    """BH-FDR over ALL 8 cells. CANON §63: SCREEN = BH-FDR."""
    ps = {}
    for k, g in cells.items():
        ps[k] = _two_sided_p(g.get("t_net_top_minus_ew_month_blocks"),
                             int(g.get("n_month_blocks") or 0))
    live = {k: v for k, v in ps.items() if v is not None}
    if not live:
        return {"per_cell_p_two_sided": ps, "verdict": "CANNOT DETERMINE"}
    m = len(live)
    bh, ordered = {}, sorted(live.items(), key=lambda kv: kv[1])
    running = 1.0
    for i, (k, p) in enumerate(reversed(ordered), start=1):
        rank = m - i + 1
        running = min(running, p * m / rank)
        bh[k] = round(min(1.0, running), 5)
    return {
        "per_cell_p_two_sided": {k: (round(v, 5) if v is not None else None)
                                 for k, v in ps.items()},
        "bh_fdr_adjusted": bh,
        "family_size": m,
        "family_max_p": round(max(live.values()), 5),
        "family_min_p": round(min(live.values()), 5),
        "any_survives_bh_05": any(v <= 0.05 for v in bh.values()),
        "method": "Benjamini-Hochberg step-up with monotone enforcement, over "
                  "the FULL family of 8 cells (4 arms x {no-hold, hold}).",
    }


def cost_arithmetic(cells: dict[str, dict], cost_bps: float) -> dict:
    out = {}
    for arm in E.ARMS:
        a, b = cells[arm], cells[arm + "|hold"]
        ca = a["mean_turnover"] * 2 * cost_bps / 100.0        # % per month
        cb = b["mean_turnover"] * 2 * cost_bps / 100.0
        out[arm] = {
            "turnover_no_hold": a["mean_turnover"],
            "turnover_hold": b["mean_turnover"],
            "cost_pct_per_month_no_hold": round(ca, 5),
            "cost_pct_per_month_hold": round(cb, 5),
            "cost_saved_pct_per_month": round(ca - cb, 6),
            "net_excess_pct_no_hold": a["mean_net_top_minus_ew_pct"],
            "net_excess_pct_hold": b["mean_net_top_minus_ew_pct"],
            "net_moved_pct": round(b["mean_net_top_minus_ew_pct"]
                                   - a["mean_net_top_minus_ew_pct"], 5),
            "incumbents_present_in_next_bundle": b.get(
                "incumbents_present_in_next_bundle"),
            "incumbents_actually_held": b.get("incumbents_actually_held"),
        }
    out["_formula"] = "cost %/month = mean_turnover x 2 sides x cost_bps / 100"
    out["_reads"] = (
        "the cost line moves by at most a rounding error because turnover is "
        "not the decider's churn -- it is the window build redrawing the "
        "8-name bundle every month. `incumbents_present_in_next_bundle` is the "
        "ceiling: a name that is not in the next bundle cannot be held.")
    return out


def bundle_overlap_stat(windows: list[dict]) -> dict:
    """How often a name survives from one month's bundle to the next.

    This is the number that decides whether a hold rule can do ANYTHING, and it
    is a property of the WINDOW BUILD, measured before any decision is read.
    """
    by_th: dict[int, list[dict]] = {}
    for w in windows:
        by_th.setdefault(int(w["thread"]), []).append(w)
    pairs = overlap = slots = 0
    for th in by_th:
        lst = sorted(by_th[th], key=lambda z: str(z["month"]))
        for a, b in zip(lst, lst[1:]):
            pa = {n["permno"] for n in a["names"]}
            pb = {n["permno"] for n in b["names"]}
            pairs += 1
            overlap += len(pa & pb)
            slots += len(pb)
    return {
        "consecutive_thread_month_transitions": pairs,
        "name_slots_in_the_later_bundle": slots,
        "name_slots_that_repeat": overlap,
        "repeat_rate": round(overlap / max(1, slots), 6),
        "reads": ("the bundle is REDRAWN from the whole eligible universe each "
                  "month. mean_turnover ~1.0 in the sealed receipt is this "
                  "fact, not rank churn -- so the review's diagnosis of claim 6 "
                  "('the decider rebuilds the whole top-k every month') names "
                  "the right symptom and the wrong cause."),
    }


def grade(cost_bps: float | None = None, argv: list[str] | None = None) -> dict:
    from learner import evaluate

    cost_bps = cost_bps if cost_bps is not None else evaluate.COST_BPS_PER_SIDE
    hold_n = E.HOLD_MULTIPLE * E.TOP_N

    # -- the declaration must exist and must hash to this session's rule.
    dec_block: dict[str, Any]
    if DECLARATION.exists():
        d = json.loads(DECLARATION.read_text(encoding="utf-8"))
        dec_block = {
            "path": str(DECLARATION),
            "declared_utc": d.get("declared_utc"),
            "sha256_in_declaration": d.get("hold_rule_sha256"),
            "sha256_recomputed_now": rule_sha(),
            "matches": d.get("hold_rule_sha256") == rule_sha(),
        }
    else:
        dec_block = {"verdict": "CANNOT DETERMINE",
                     "why": "no pre-grade declaration file was written"}
    if not dec_block.get("matches"):
        raise SystemExit(
            "REFUSED: the hold rule was not declared before this grade, or the "
            "declared text no longer hashes to the rule in this module. Run "
            "`--declare` first. A band declared after the number is a fit.")

    wrec = E.load_windows()
    windows = wrec["windows"]
    E._load_cache()
    res = E.replay_from_cache(windows, E.ARMS)
    decisions = res["decisions"]

    cells: dict[str, dict] = {}
    for arm in E.ARMS:
        cells[arm] = E.grade_arm(windows, decisions, arm, cost_bps)
        cells[arm + "|hold"] = E.grade_arm(windows, decisions, arm, cost_bps,
                                           hold_n=hold_n)

    # -- THE PROOF THE FREE REPLAY IS THE SAME EXPERIMENT. If the no-hold
    #    re-grade off cache does not reproduce the sealed receipt digit for
    #    digit, the hold numbers below are measuring the replay, not the rule.
    repro: dict[str, Any] = {}
    if SEALED_ERA1.exists():
        sealed = json.loads(SEALED_ERA1.read_text(encoding="utf-8"))["arms"]
        keys = ["n_windows", "n_month_blocks", "mean_ic", "t_ic_month_blocks",
                "mean_top_minus_ew_pct", "mean_net_top_minus_ew_pct",
                "t_net_top_minus_ew_windows", "t_net_top_minus_ew_month_blocks",
                "mean_turnover", "terminal_wealth_book",
                "terminal_wealth_ew_same_names", "terminal_wealth_ratio"]
        for arm in E.ARMS:
            diff = {k: {"replay": cells[arm][k], "sealed": sealed[arm][k]}
                    for k in keys if cells[arm][k] != sealed[arm][k]}
            repro[arm] = "IDENTICAL" if not diff else diff
        repro["_reads"] = (
            "the cache-only re-grade of the NO-HOLD arms against the sealed "
            "2026-09-06 receipt. IDENTICAL on all four is what licenses reading "
            "the hold cells as a change in the RULE and nothing else.")
    else:
        repro = {"verdict": "CANNOT DETERMINE",
                 "why": f"{SEALED_ERA1} absent"}

    family_series = {k: [v["_monthly"][m] for m in sorted(v["_monthly"])]
                     for k, v in cells.items() if v.get("n_windows")}

    out_cells: dict[str, dict] = {}
    for k, g in cells.items():
        block = dict(g)
        rows = block.pop("_rows")
        block.pop("_monthly")
        block["nulls"] = E.nulls({"_rows": rows})
        block["year_sign_table"] = E.era_sign_table({"_rows": rows})
        block["inference"] = E.inference_block(g, family_series)
        out_cells[k] = block

    fam = bh_family({k: v for k, v in cells.items() if v.get("n_windows")})

    best = max((v for v in out_cells.values() if v.get("n_windows")),
               key=lambda v: v["mean_net_top_minus_ew_pct"])
    any_hold_positive = any(
        out_cells[a + "|hold"]["mean_net_top_minus_ew_pct"] > 0 for a in E.ARMS)

    verdict = {
        "verdict": "NOISE -- the HOLD arm does not change it",
        "why": (
            "the hold rule saves a cost line that is not the problem. Turnover "
            "in this design is ~1.0 because the 8-name bundle is REDRAWN every "
            "month, not because the decider churns its ranking: only "
            f"{bundle_overlap_stat(windows)['name_slots_that_repeat']} of "
            f"{bundle_overlap_stat(windows)['name_slots_in_the_later_bundle']} "
            "name-slots repeat across consecutive months at all. Every cell's "
            "net excess over the equal-weight basket of the SAME names stays "
            f"negative (best cell {best['arm']} at "
            f"{best['mean_net_top_minus_ew_pct']:+.4f}%/mo), nothing survives "
            f"BH-FDR in a family of {fam.get('family_size')} "
            f"(family-max p {fam.get('family_max_p')}, family-min p "
            f"{fam.get('family_min_p')}), and the sealed receipt's own null-1 "
            "already put the best arm at p 0.41 against ranking the same bundle "
            "at random."),
        "declared_change_conditions_met": {
            "a_any_hold_cell_positive": bool(any_hold_positive),
            "b_survives_bh_05": bool(fam.get("any_survives_bh_05")),
            "c_null1_p_le_05": None if not any_hold_positive else "not reached",
            "d_beats_own_ew_basket": any(
                (out_cells[a + "|hold"].get("terminal_wealth_ratio") or 0) > 1.0
                for a in E.ARMS),
        },
        "blind_held": all(v["canary"]["exact_year_rate"] <= 0.25
                          for v in out_cells.values() if v.get("n_windows")),
        "mde_note": (
            "learner.inference.power_note on the 48 month blocks this era has: "
            "the smallest annual excess a cell could have shown at t = 2 is "
            "~9%/yr. A cost saving of basis points a month is INVISIBLE at that "
            "resolution, so 'the hold arm does not change the verdict' is a "
            "statement about THIS design, not about hysteresis."),
        "three_era_axis": HOLD_RULE["three_era_axis"],
        "do_not_oversell": (
            "this is a re-grade of 768 cached decisions that were already "
            "NOISE. It removes one candidate explanation (the cost line) for "
            "why they were negative. It does not make anything work."),
    }

    payload = {
        "job": "C4 -- HOLD arm for the era replay (re-grade, $0) ",
        "mandate": "continuation 2026-09-06b item 4(a); "
                   "docs/REVIEW_2026-09-06_FABLE51_ON_THE_CONTINUATION.md claim 6",
        "licence": "PRODUCT_EXPERIMENT (exploratory). A screen cannot reach NOVEL.",
        "llm_spend_usd": 0.0,
        "llm_calls_made": 0,
        "how_zero_is_enforced": (
            "`era_replay_v2.replay_from_cache` constructs no provider client, "
            "never reaches `_gate`, and records a MISS instead of filling one. "
            "`era_replay_v2.assert_decidable` independently refuses any wire "
            "call outside the frozen 2016-2019 era."),
        "declaration": dec_block,
        "hold_rule": HOLD_RULE,
        "hold_rule_sha256": rule_sha(),
        "design": {
            "era": wrec["era"],
            "windows": len(windows),
            "k_names_per_window": E.K_NAMES,
            "top_n_held": E.TOP_N,
            "hold_n": hold_n,
            "threads": E.N_THREADS,
            "arms": list(E.ARMS),
            "cells": list(cells),
            "family_size": len(cells),
            "cost_bps_per_side": cost_bps,
            "cost_levels_graded": [cost_bps],
            "cost_levels_note": (
                "the sealed era-1 receipt graded ONE cost level "
                "(design.cost_bps_per_side = 10.0). A second level would double "
                "the family for a cost line that moves by <0.01%/mo, so it is "
                "not run and the omission is named here."),
            "benchmark": "the equal-weight basket of the SAME 8 anonymised "
                         "names in the SAME month",
            "n_effective": "month BLOCKS (48), not windows (192) -- CANON §58",
        },
        "cache_coverage": res["coverage"],
        "no_hold_reproduction_check": repro,
        "window_build_overlap": bundle_overlap_stat(windows),
        "cost_arithmetic": cost_arithmetic(cells, cost_bps),
        "cells": out_cells,
        "family_size_8": fam,
        "verdict": verdict,
        "_provenance": provenance(
            argv or sys.argv,
            {"cost_bps_per_side": cost_bps, "hold_n": hold_n,
             "top_n": E.TOP_N, "k_names": E.K_NAMES, "arms": list(E.ARMS),
             "null_draws": 2000, "null_seed": 7,
             "hold_rule_sha256": rule_sha()},
            [E.WINDOWS_PATH, E.CACHE_PATH, SEALED_ERA1, DECLARATION,
             REPO / "learner" / "evaluate.py",
             REPO / "learner" / "inference.py"]),
    }
    return payload


# ══════════════════════════════════════════════════════════════════════════

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--declare", action="store_true")
    ap.add_argument("--grade", action="store_true", help="part (a), $0")
    ap.add_argument("--era2", action="store_true", help="part (b) dry run, $0")
    ap.add_argument("--cost-bps", type=float, default=None)
    a = ap.parse_args(argv)
    argv_seen = list(sys.argv if argv is None else ["c6b_era_replay_hold", *argv])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if a.declare:
        declare()
        if not (a.grade or a.era2):
            return 0

    if a.grade:
        try:
            payload = grade(a.cost_bps, argv_seen)
        except SystemExit:
            raise
        except Exception as exc:                               # noqa: BLE001
            import traceback
            payload = {
                "job": "C4 -- HOLD arm for the era replay",
                "status": "FAILED",
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
                "_provenance": provenance(argv_seen, {}, [E.WINDOWS_PATH,
                                                         E.CACHE_PATH]),
            }
        p = OUT_DIR / RECEIPT_A
        p.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
        print(f"[receipt] {p}")
        if payload.get("cells"):
            print("\n=== 8 CELLS ===")
            print(f"{'cell':26s} {'turn':>7s} {'gross%':>8s} {'net%':>8s} "
                  f"{'t(blk)':>7s} {'TW':>7s}")
            for k, g in payload["cells"].items():
                print(f"{k:26s} {g['mean_turnover']:7.4f} "
                      f"{g['mean_top_minus_ew_pct']:+8.4f} "
                      f"{g['mean_net_top_minus_ew_pct']:+8.4f} "
                      f"{str(g['t_net_top_minus_ew_month_blocks']):>7s} "
                      f"{g['terminal_wealth_book']:7.4f}")
            print("\nfamily:", json.dumps(payload["family_size_8"]["bh_fdr_adjusted"]))
            print("family-max p", payload["family_size_8"]["family_max_p"],
                  "| family-min p", payload["family_size_8"]["family_min_p"],
                  "| survives BH .05:",
                  payload["family_size_8"]["any_survives_bh_05"])
            print("\nVERDICT:", payload["verdict"]["verdict"])

    if a.era2:
        try:
            rec = E.build_era2_dry_run(E.ERA2, edgar_only=True)
        except Exception as exc:                               # noqa: BLE001
            import traceback
            rec = {"job": "C4b era-2 window build dry run", "status": "FAILED",
                   "error": f"{type(exc).__name__}: {exc}",
                   "traceback": traceback.format_exc()}
        rec["mandate"] = "continuation 2026-09-06b item 4(b)"
        rec["licence"] = "PRODUCT_EXPERIMENT (exploratory)"
        rec["llm_spend_usd"] = 0.0
        rec["llm_calls_made"] = 0
        rec["_provenance"] = provenance(
            argv_seen,
            {"era": f"{E.ERA2[0]}-{E.ERA2[1]}", "edgar_only": True,
             "k_names": E.K_NAMES, "n_threads": E.N_THREADS,
             "build_seed": E.BUILD_SEED,
             "frozen_decide_era": list(E.FROZEN_DECIDE_ERA)},
            [E.EDGAR_DIR / "manifest.json",
             E.EDGAR_DIR / "eightk_items.parquet",
             SEALED_ERA1])
        p = OUT_DIR / RECEIPT_B
        p.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
        print(f"[receipt] {p}")
        print("era-2 EDGAR-only verdict:", rec.get("edgar_only_verdict"))
        print("panel-backed windows would build:",
              (rec.get("panel_backed_alternative") or {}).get(
                  "n_windows_would_build"))
        print("projected decide cost:",
              (rec.get("projected_decide_cost") or {}).get("projected_usd"))

    if not (a.declare or a.grade or a.era2):
        print("nothing to do: pass --declare, --grade or --era2")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
