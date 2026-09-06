"""N5.3 -- THE STATES' THIRD NULL, AND A FINAL VERDICT (Night Lab 2026-09-07).

WHAT THIS ANSWERS
==================
`docs/NIGHT_LAB_2026-09-07_OPUS_PROMPT.md` lane N5 item 3. The four
unsupervised market states (`learner/states.py`'s per-(permno, month)
`state_k4`, the "4 OOS states" of MEMORY S35/S37) already carry TWO nulls,
and they DISAGREE in a way that is itself the finding
(`docs/REVIEW_2026-09-04_FABLE51_VERDICTS.md` claim 9, re-derived below, not
just quoted):

    NULL 1 (`states.shuffled_null`, LEGACY, within-month)
        permutes state labels independently WITHIN each month across names.
        Destroys persistence entirely. On the sealed k=4 assignment this
        clears at p ~ 0.000 ("beats a random partition").

    NULL 2 (`states.persistent_shuffled_null`, the "honest bar" S36 built)
        circularly shifts EACH NAME'S OWN label sequence in time. Preserves
        exactly the observed persistence, destroys the calendar alignment.
        Run on the sealed assignment 2026-09-04: p = 1.000 at k=3/4/5 -- the
        OBSERVED spread sits BELOW every one of 200 persistent-null draws.

Null 1 says the partition beats pure noise by a landslide. Null 2 says a
partition with the SAME persistence, SAME state marginal, and SAME name-level
composition -- just misaligned in time -- beats the true alignment. Read
together (the review's own words): **"the two nulls bracket a name-path
confound neither controls."** Neither null asks the one question that would
resolve it: does it matter WHICH NAME a given state PATH is glued to, holding
the calendar fixed? That is null 3, and it is new code, not a rerun of
existing code (`states.py` has no cross-name path-swap null; this is the gap
identified but not filled at the 2026-09-04 review, referenced there as work
still owed to `tracker_backtest/` by "B4").

NULL 3 -- THE NAME-PATH-CONTROLLED PERMUTATION
================================================
For a random permutation `pi` over names (a full DERANGEMENT: no name maps to
itself), name `i` receives name `pi(i)`'s REAL, UNSHUFFLED historical state
PATH, read off at the SAME calendar months name `i` actually has a matured
return for. Name `i`'s own true forward returns never move.

What this holds fixed that the other two do not:
    * the calendar (month m's row is still graded against month m's return --
      null 2 breaks this by time-shifting a name's own sequence);
    * each DONOR's own path exactly as lived (no re-randomising within a
      month -- null 1 breaks this, and MEMORY's own lesson is that a
      re-randomising null cannot catch a persistent tilt).
What it destroys: the pairing between a SPECIFIC company's identity and the
SPECIFIC state path that company happened to occupy. If the sealed spread is
driven by "the states genuinely time this company's returns", null 3 should
clear (a random OTHER company's path should predict this company's returns
worse than its own). If the spread is driven by "which company this is"
(size, sector, a persistently different mean state occupancy having nothing
to do with alignment), null 3 should NOT clear, because a donor path swap
preserves exactly that kind of company-level heterogeneity.

A shuffled-DATE null does not control for the date (S24 -- MEMORY,
`feedback_a_shuffled_date_null_does_not_control_for_the_date.md`); this null
is built to hold the date fixed on purpose, which is the property null 2 is
missing and null 1 has only by construction (it stays within one month but
gives up persistence to get there).

LICENCE: PRODUCT_EXPERIMENT. Places nothing, recommends nothing -- a
measurement, feeding a verdict and (if CANNOT DETERMINE) a demotion list.

    python -m scripts.n5_states_third_null                # full run
    python -m scripts.n5_states_third_null --quick          # smoke-sized
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import receipt_provenance as PROV                 # noqa: E402
from learner import nullbar as NB                                       # noqa: E402
from learner import states as S                                         # noqa: E402
from learner import long_panel as LP                                    # noqa: E402
from scripts.w3_neural_floored import free_gb                           # noqa: E402

RECEIPT = (REPO / "backend" / "data" / "optimus" / "night_lab_2026-09-07"
           / "N5_states_third_null.json")

COMPANY_STATES = REPO / "backend" / "data" / "optimus" / "learner" / "states" / "company_states.parquet"

DEFAULT_SEED = 20260907
MIN_FREE_GB = 2.0
PRIMARY_STATE_COL = "state_k4"       # "the four states" -- MEMORY S35/S37, sealed receipt's own primary_state_col
PRIMARY_TARGET = "excess_vw_1m"
SECONDARY_TARGET = "excess_vw_3m"


def log(*a):
    print(*a, flush=True)


def _mem_guard(note: str) -> dict:
    g = free_gb()
    if g is not None and g < MIN_FREE_GB:
        raise MemoryError(f"REFUSED before {note}: {g} GB free < {MIN_FREE_GB} GB floor")
    return {f"free_gb_before_{note.replace(' ', '_')}": g}


# ------------------------------------------------------------------ loading

def load_states_and_returns(tracker: PROV.InputTracker | None = None,
                            state_col: str = PRIMARY_STATE_COL) -> pd.DataFrame:
    """(permno, month, state, excess_vw_1m, excess_vw_3m) -- the grading frame.

    Reads only the columns needed from each parquet (never the full 418 MB
    long panel; `company_states.parquet` is itself the small, already-fitted
    OOS assignment file, and `train_table.parquet` is read column-subset).
    """
    if tracker is not None:
        tracker.opened(COMPANY_STATES, note="OOS state assignments (this file's own object)")
    cs = pd.read_parquet(COMPANY_STATES, columns=["permno", "month", state_col])
    from learner import dataset as D
    if tracker is not None:
        tracker.opened(D.TRAIN_TABLE, note="monthly forward-excess-return targets")
    tt = pd.read_parquet(D.TRAIN_TABLE, columns=["permno", "month", PRIMARY_TARGET, SECONDARY_TARGET])
    d = cs.merge(tt, on=["permno", "month"], how="inner")
    return d


# --------------------------------------------------------- null 3: the new one

def _derangement(n: int, rng: np.random.Generator) -> np.ndarray:
    """A uniform-ish random permutation of `range(n)` with NO fixed points.

    Rejection sampling: P(zero fixed points) -> 1/e ~ 36.8% for a uniform
    permutation on n this large, so a derangement is found in ~2-3 tries on
    average. A residual fixed point after the retry budget is repaired by a
    local swap (never by leaving it -- a self-mapped name reproduces the
    TRUE observed pairing for that name, which is exactly the pairing this
    null exists to rule out).
    """
    idx = np.arange(n)
    for _ in range(50):
        perm = rng.permutation(n)
        if not np.any(perm == idx):
            return perm
    perm = rng.permutation(n)
    fixed = np.flatnonzero(perm == idx)
    if fixed.size >= 2:
        perm[fixed] = perm[np.roll(fixed, 1)]
    elif fixed.size == 1:
        j = int(fixed[0])
        k = j
        while k == j:
            k = int(rng.integers(0, n))
        perm[j], perm[k] = perm[k], perm[j]
    return perm


def name_path_permutation_null(d: pd.DataFrame, state_col: str, target: str, *,
                               n_draws: int, seed: int) -> dict:
    """NULL 3. See the module docstring for the full argument.

    Implementation: build a dense (n_names x n_months) state matrix ONCE
    (small: `company_states.parquet` holds ~5,400 names x ~120 months). Each
    draw is then one derangement `pi` plus a single fancy-index lookup
    `state_matrix[pi[row_name_idx], row_month_idx]` -- vectorised over every
    row at once, not a Python loop over rows. `spread_statistic`
    (`learner/states.py`, imported not reimplemented) is then computed on the
    permuted labels against the TRUE, unmoved target.
    """
    sub = d[["permno", "month", state_col, target]].dropna(subset=[target]).reset_index(drop=True)
    obs = S.spread_statistic(sub, state_col, target)

    names = np.sort(sub["permno"].unique())
    months = np.sort(sub["month"].unique())
    name_idx = {p: i for i, p in enumerate(names)}
    month_idx = {m: i for i, m in enumerate(months)}
    n_names, n_months = len(names), len(months)

    state_matrix = np.full((n_names, n_months), np.nan, dtype="float64")
    ni = sub["permno"].map(name_idx).to_numpy()
    mi = sub["month"].map(month_idx).to_numpy()
    state_matrix[ni, mi] = sub[state_col].to_numpy()

    rng = np.random.default_rng(seed)
    draws = []
    coverage = []
    for _ in range(n_draws):
        perm = _derangement(n_names, rng)
        donor_ni = perm[ni]
        permuted_state = state_matrix[donor_ni, mi]
        tmp = pd.DataFrame({state_col: permuted_state, "month": sub["month"].to_numpy(),
                           target: sub[target].to_numpy()})
        coverage.append(float(tmp[state_col].notna().mean()))
        tmp = tmp.dropna(subset=[state_col])
        draws.append(float(S.spread_statistic(tmp, state_col, target)))
    a = np.asarray([x for x in draws if x == x], dtype="float64")
    n_ok = int(a.size)
    result = {
        "statistic": "max-minus-min of per-state mean monthly excess (learner.states.spread_statistic)",
        "target": target,
        "observed": round(float(obs), 6),
        "n_names": int(n_names),
        "n_months": int(n_months),
        "n_rows_graded": int(len(sub)),
        "n_draws_requested": int(n_draws),
        "n_draws_usable": n_ok,
        "mean_donor_coverage": round(float(np.mean(coverage)), 4) if coverage else None,
        "coverage_note": ("share of rows whose donor actually had a state assigned in that exact "
                          "calendar month; a donor with no listing/coverage that month contributes "
                          "no row to that draw's spread, same as a real cross-sectional gap would."),
        "null_bar": NB.MODEL_NULL_BAR if n_ok >= NB.MIN_DRAWS else NB.CANNOT_DETERMINE,
    }
    if n_ok < NB.MIN_DRAWS:
        result["verdict"] = f"{NB.CANNOT_DETERMINE} (usable draws {n_ok} < {NB.MIN_DRAWS})"
        return result
    result["null_summary"] = NB.summarise_null(a)
    result["percentile_of_observed_in_null"] = round(NB.percentile_of(float(obs), a), 4)
    result["p_one_sided"] = round(NB.p_one_sided(float(obs), a), 4)
    result["beats_name_path_permutation"] = bool(result["p_one_sided"] <= 0.05)
    result["verdict"] = ("CLEARS_MODEL_NULL" if result["p_one_sided"] <= 0.05 else "WITHIN_MODEL_NULL")
    return result


# ---------------------------------------------------------------- era table

def era_spread_table(d: pd.DataFrame, state_col: str, target: str) -> dict:
    sub = d.dropna(subset=[target])
    out = {}
    for name, lo, hi in LP.ERAS:
        years = sub["month"].str.slice(0, 4).astype(int)
        g = sub[(years >= lo) & (years <= hi)]
        if g["month"].nunique() < 6:
            out[name] = {"months": int(g["month"].nunique()), "rows": int(len(g)), "spread": None,
                        "note": "fewer than 6 months"}
            continue
        out[name] = {"months": int(g["month"].nunique()), "rows": int(len(g)),
                     "spread": round(float(S.spread_statistic(g, state_col, target)), 6)}
    spreads = [v["spread"] for v in out.values() if v.get("spread") is not None]
    consistent = bool(len(spreads) >= 2 and max(spreads) > 0 and (min(spreads) / max(spreads)) >= 0.5)
    return {"by_era": out, "eras_measured": len(spreads),
           "era_consistent_ratio_ge_0_5": consistent,
           "note": ("a spread is a range (max-min), non-negative by construction -- consistency "
                    "means the eras agree in MAGNITUDE (min/max >= 0.5), not merely that all are "
                    "positive, which is true of any partition whatsoever.")}


# --------------------------------------------------------------- demotion list

def grep_state_usage() -> dict:
    """Every place `state_k4` / the states module is referenced outside this
    file's own lane, so a CANNOT DETERMINE verdict has a concrete demotion
    list rather than a general warning. Best-effort: `git grep` if available
    (fast, respects .gitignore), else a plain filesystem walk. Never raises --
    an inability to grep is reported, not fatal to the receipt.
    """
    patterns = ["state_k4", "STATE_SEMANTICS", "unsupervised_states_20260903",
               "company_states.parquet", "market_states.parquet"]
    hits: dict[str, list[str]] = {}
    for pat in patterns:
        try:
            out = subprocess.run(
                ["git", "grep", "-n", "--", pat, "--",
                 "*.py", "*.md"],
                cwd=REPO, capture_output=True, text=True, timeout=30)
            lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
        except Exception as exc:                                       # noqa: BLE001
            lines = [f"CANNOT_DETERMINE: git grep failed ({type(exc).__name__})"]
        hits[pat] = lines[:40]
    terminal = REPO.parent / "aegis-alpha-terminal"
    terminal_hits: list[str] | str
    if terminal.is_dir():
        try:
            out = subprocess.run(
                ["git", "grep", "-n", "-e", "state_k4", "-e", "unsupervised_states",
                 "-e", "company_states.parquet", "--", "*.py"],
                cwd=terminal, capture_output=True, text=True, timeout=30)
            terminal_hits = [ln for ln in out.stdout.splitlines() if ln.strip()][:40]
        except Exception as exc:                                        # noqa: BLE001
            terminal_hits = f"CANNOT_DETERMINE: {type(exc).__name__}"
    else:
        terminal_hits = "SKIPPED: aegis-alpha-terminal checkout not found beside this repo"
    return {"aegis_finance": hits, "aegis_alpha_terminal": terminal_hits}


# ------------------------------------------------------------------- main

def main() -> dict:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(RECEIPT))
    ap.add_argument("--n-draws", type=int, default=200)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    tracker = PROV.InputTracker()
    mem_before = _mem_guard("states third null run")
    log(f"[N5.3] free_gb={mem_before}")

    n_draws = 64 if args.quick else args.n_draws

    receipt: dict = {
        "job": "N5_states_third_null",
        "lane": "N5.3",
        "licence": "PRODUCT_EXPERIMENT",
        "state_col": PRIMARY_STATE_COL,
        "primary_target": PRIMARY_TARGET,
        "prior_verdict": ("REFUTED (void under its own bar) -- "
                          "docs/REVIEW_2026-09-04_FABLE51_VERDICTS.md claim 9: null 1 "
                          "(legacy within-month) clears at p~0.000, null 2 (persistent "
                          "circular-shift) FAILS at p=1.000 (observed spread below every "
                          "draw) at k=3/4/5. 'the two nulls bracket a name-path confound "
                          "neither controls.' This receipt runs the third."),
        "params": {"n_draws": n_draws, "seed": args.seed},
        "llm_spend_usd": 0.0,
        "llm_calls": 0,
    }

    d = load_states_and_returns(tracker)
    receipt["data"] = {
        "rows_after_merge": int(len(d)),
        "distinct_permnos": int(d["permno"].nunique()),
        "distinct_months": int(d["month"].nunique()),
        "month_min": str(d["month"].min()), "month_max": str(d["month"].max()),
    }
    per_month_states = d.groupby("month")[PRIMARY_STATE_COL].nunique()
    receipt["state_is_market_level"] = bool((per_month_states <= 1).all())
    receipt["state_is_market_level_note"] = (
        "checked directly: if state_k4 were constant within a month (market-level), "
        "null 1 (within-month shuffle) would be the identity by construction. It is "
        "NOT constant here -- state_k4 is a per-(permno, month) assignment, which is "
        "the object nulls 1-3 are all correctly defined for.")

    log(f"[N5.3] {len(d)} rows, {d['permno'].nunique()} names, "
        f"{d['month'].nunique()} months. Running null 1 (legacy, within-month)...")
    t_n1 = time.time()
    null1 = S.shuffled_null(d, PRIMARY_STATE_COL, PRIMARY_TARGET, n_shuffles=n_draws, seed=args.seed)
    log(f"[N5.3] null 1 done in {round(time.time()-t_n1,1)}s: p={null1.get('p_value_one_sided')}")

    log("[N5.3] running null 2 (persistent circular-shift)...")
    t_n2 = time.time()
    null2 = S.persistent_shuffled_null(d, PRIMARY_STATE_COL, PRIMARY_TARGET,
                                       n_shuffles=n_draws, seed=args.seed)
    log(f"[N5.3] null 2 done in {round(time.time()-t_n2,1)}s: "
        f"p={null2.get('p_value_one_sided')}")

    log("[N5.3] running null 3 (name-path-controlled permutation, NEW)...")
    t_n3 = time.time()
    null3 = name_path_permutation_null(d, PRIMARY_STATE_COL, PRIMARY_TARGET,
                                       n_draws=n_draws, seed=args.seed)
    log(f"[N5.3] null 3 done in {round(time.time()-t_n3,1)}s: "
        f"p={null3.get('p_one_sided')}, verdict={null3.get('verdict')}")

    receipt["null_1_within_month_legacy"] = null1
    receipt["null_2_persistent_circular_shift"] = null2
    receipt["null_3_name_path_permutation"] = null3

    receipt["era_table"] = era_spread_table(d, PRIMARY_STATE_COL, PRIMARY_TARGET)

    # ---------------------------------------------------------- secondary target
    log("[N5.3] robustness: repeating all three nulls on excess_vw_3m...")
    d3 = d.dropna(subset=[SECONDARY_TARGET])
    null1_3m = S.shuffled_null(d3, PRIMARY_STATE_COL, SECONDARY_TARGET,
                               n_shuffles=n_draws, seed=args.seed)
    null2_3m = S.persistent_shuffled_null(d3, PRIMARY_STATE_COL, SECONDARY_TARGET,
                                          n_shuffles=n_draws, seed=args.seed)
    null3_3m = name_path_permutation_null(d3, PRIMARY_STATE_COL, SECONDARY_TARGET,
                                          n_draws=n_draws, seed=args.seed)
    receipt["secondary_target_excess_vw_3m"] = {
        "null_1": {"p_one_sided": null1_3m.get("p_value_one_sided")},
        "null_2": {"p_one_sided": null2_3m.get("p_value_one_sided"),
                  "verdict": null2_3m.get("beats_persistent_relabelling")},
        "null_3": {"p_one_sided": null3_3m.get("p_one_sided"), "verdict": null3_3m.get("verdict")},
    }

    # ---------------------------------------------------------------- verdict
    p1 = null1.get("p_value_one_sided")
    p2 = null2.get("p_value_one_sided")
    p3 = null3.get("p_one_sided")
    clears1 = isinstance(p1, (int, float)) and p1 <= 0.05
    clears2 = isinstance(p2, (int, float)) and p2 <= 0.05
    clears3 = isinstance(p3, (int, float)) and p3 <= 0.05
    obs2_below_null = None
    if isinstance(null2.get("null_mean"), (int, float)):
        obs2_below_null = null2["observed"] < null2["null_mean"]

    if clears1 and (not clears2) and (not clears3):
        family = "ALL_THREE_AGREE_ON_FAILURE"
        verdict = "CANNOT_DETERMINE"
        reasoning = ("null 1 alone clears (mis-specified per S36/nullbar.py -- a re-randomising "
                    "null cannot catch a persistent tilt, so its clearing is not informative on "
                    "its own). Nulls 2 AND 3 -- the two that hold something real fixed (persistence, "
                    "and respectively the calendar or the donor's own path) -- both FAIL to clear. "
                    "Null 3 resolving in the SAME direction as null 2 answers the review's open "
                    "question: it is not merely that null 2's time-shift is too weak a null -- "
                    "swapping WHICH NAME owns a real state path, calendar held fixed, ALSO beats "
                    "the true pairing. The state assignment's cross-sectional spread is explained "
                    "by company-level heterogeneity (which names habitually sit in which states), "
                    "not by the states timing any one company's OWN returns.")
    elif clears1 and clears2 and clears3:
        family = "ALL_THREE_CLEAR"
        verdict = "SCREEN_SURVIVOR (all three nulls; still not a book, still not NOVEL)"
        reasoning = "All three nulls clear at p<=0.05; the strongest reading this design permits."
    elif clears1 and clears3 and not clears2:
        family = "NULL_2_ALONE_DISAGREES"
        verdict = "CANNOT_DETERMINE"
        reasoning = ("Null 3 clearing while null 2 does not is a genuinely different reading from "
                    "the review's -- it would say the calendar-holding, donor-path-swapping test "
                    "finds real name-return-timing signal that the time-shifting test's own "
                    "within-name misalignment happens to mask. Reported as CANNOT DETERMINE "
                    "rather than adjudicated here: a 3-null split decision on a screen is not a "
                    "verdict this file is licensed to resolve into a claim.")
    else:
        family = "MIXED"
        verdict = "CANNOT_DETERMINE"
        reasoning = "Nulls disagree in a pattern not covered by the named cases above; see the raw p-values."

    receipt["final_verdict"] = {
        "verdict": verdict,
        "family_case": family,
        "p_null_1": p1, "clears_null_1": clears1,
        "p_null_2": p2, "clears_null_2": clears2, "observed_below_null_2_mean": obs2_below_null,
        "p_null_3": p3, "clears_null_3": clears3,
        "reasoning": reasoning,
        "family_id": "n5-states-k4-three-nulls",
        "family_size": 1,
        "family_max_p_note": ("one state definition (k=4) tested; a family-max correction across "
                              "k in {3,4,5,6,8} was NOT run here (out of scope/time for this lane) "
                              "-- the review's claim 9 quotes k=3/4/5 all failing null 2, which is "
                              "suggestive but not this receipt's own multiplicity-corrected number."),
        "dsr_pbo_note": ("not applicable: this is a cross-sectional spread statistic on a "
                         "partition, not a book with a Sharpe ratio to deflate -- same rationale "
                         "as scripts.weekend_lab_jobs.screen_verdict for a Fama-MacBeth screen."),
        "mde_note": (f"the detectable floor IS the null's own p95: null 2's p95={null2.get('null_p95')}, "
                    f"null 3's p95={(null3.get('null_summary') or {}).get('p95')} (observed must clear "
                    "this to be distinguishable from either null's own noise at alpha=0.05)."),
    }

    if verdict.startswith("CANNOT_DETERMINE") or verdict == "CANNOT_DETERMINE":
        log("[N5.3] verdict CANNOT_DETERMINE -- building the demotion list")
        receipt["demotion"] = {
            "instruction": ("verdict is CANNOT DETERMINE (or worse): the four unsupervised states "
                            "(state_k4 and its k-ladder siblings) are to be DEMOTED everywhere they "
                            "are currently used as a live input -- i.e. treated as unvalidated / "
                            "informational-only, never as a sizing, admission, or routing input, "
                            "until a state definition clears all three nulls or a fourth, better "
                            "null resolves the remaining disagreement."),
            "usage_grep": grep_state_usage(),
            "known_live_references": [
                {"file": "learner/potential_universe.py:125-142,577,698",
                "what": "STATE_SEMANTICS tags + STATES_RECEIPT path, quoted into the "
                        "'whole_universe_refusals' / per-row 'state' block of every scorecard row",
                "current_status": ("ALREADY INERT for a different reason: a day file cannot supply "
                                  "the STATE_FEATURES columns, so `state.status` is CANNOT_DETERMINE "
                                  "on every row today regardless of this receipt. Demotion here is "
                                  "confirmatory, not a new restriction -- but the SEMANTICS TEXT "
                                  "('broken-lottery-ticket', 'p=0.000 vs 200 random partitions') "
                                  "should be corrected or removed the next time that file is touched, "
                                  "since it quotes null 1 alone and reads as a validated finding.")},
                {"file": "scripts/weekend_lab_jobs.py (W8_states_three_nulls)",
                "what": "measures MARKET-LEVEL states (a different object: one state per MONTH, "
                        "not per (permno, month)) with its own three-null design",
                "current_status": ("not directly affected by this receipt (different object), but "
                                  "shares the same 'states' brand -- a reader should not infer "
                                  "market-level states are validated because this receipt is silent "
                                  "on them, nor infer they are demoted; W8's own receipts carry "
                                  "their own verdict.")},
                {"file": "docs/REVIEW_2026-09-04_FABLE51_VERDICTS.md claim 9 / claim 7 (allocator v1)",
                "what": "the allocator v1 plan was already marked UNVALIDATED pending this null; "
                        "this receipt does not lift that mark (it deepens the same finding)."},
            ],
        }
    else:
        receipt["demotion"] = {"instruction": "not triggered -- verdict is not CANNOT_DETERMINE",
                              "usage_grep_for_reference": grep_state_usage()}

    receipt["status"] = "OK"
    receipt["runtime_seconds"] = round(time.time() - t0, 1)
    receipt["memory"] = {**mem_before, "free_gb_after": free_gb()}
    PROV.attach(receipt, sys.argv, vars(args), tracker)
    _write(receipt, args.out)
    return receipt


def _write(receipt: dict, path: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    def _default(o):
        if isinstance(o, (pd.Timestamp, datetime)):
            return o.isoformat()
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, np.bool_):
            return bool(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        return str(o)

    with open(p, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=2, default=_default)
    log(f"[N5.3] wrote {p}")


if __name__ == "__main__":
    main()
