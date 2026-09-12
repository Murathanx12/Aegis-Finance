"""E5 -- WHEN TO STOP LOOKING AT A LINEAGE (roadmap section 3, item E5).

A search that runs every night and keeps its best genome is a maximum-of-N
machine. G3 evaluated 595 distinct genomes in 251 lineages over one night; the
top of that pile is the best of 251 draws, and "it beat the random-genome null"
is a statement about the null, not about the search. THE DEFLATION IS THE
MISSING HALF: an observed Sharpe has to clear the Sharpe the best of N trials
reaches by luck alone before it means anything.

E5 IS INTEGRATION, NOT INVENTION
================================
`backend/strategy/multipletesting.py` already ships `deflated_sharpe_ratio`
(Bailey & Lopez de Prado 2014, SSRN 2460551) and
`probability_of_backtest_overfitting` (CSCV). That file is VENDORED VERBATIM
and is not edited here. This module reads `G3_evaluations.jsonl`, builds the
two inputs those functions need, calls them, and writes a verdict plus a
receipt.

THE EFFECTIVE TRIAL COUNT, AND THE GAP THAT IS NAMED RATHER THAN HIDDEN
=======================================================================
DSR needs "how many strategies did you search over". Two numbers are computed
and BOTH travel on every row:

* `n_trials_raw` -- distinct genome keys evaluated. Raw trials only ever
  inflate `expected_maximum_sharpe`, i.e. raise the bar, so this is the
  conservative count.
* `n_trials_effective_proxy` -- distinct lineage roots. The unit the archive
  already de-duplicates on. It is a PROXY for the ONC (Optimal Number of
  Clusters) count of Lopez de Prado & Lewis (2018/2019), which clusters trials
  by the CORRELATION of their return series, because two siblings differing in
  one weight are not two independent draws. ONC needs a per-genome return
  VECTOR; G3 persists only a scalar `fitness` per (genome, bank), so the ONC
  count is `null` in every receipt this module writes and the gap is stated in
  `n_trials_effective_onc_gap`. Closing it means persisting the per-window
  excess vector for finalists -- named in the spec as later work, not done
  here.

WHAT THE OBSERVATION UNIT ACTUALLY IS
=====================================
G3 writes one `fitness` per (genome, window bank): the median, across the ~24
windows of that bank, of the genome's beta-matched annualised excess over the
bank's random-genome null bar. So a lineage representative's observation vector
is its per-BANK fitness values, and `n_observations` is how many banks it met
-- NOT how many windows. A per-bank number is already a median over windows, so
its dispersion is narrower than a per-window series' would be and a Sharpe
computed on it is not comparable to one computed per window. Both facts ride on
every row (`observation_unit`, `n_windows_measured`), because the RW1 null
control below IS measured per window and the two numbers would otherwise be
read as the same kind of thing.

`probabilistic_sharpe_ratio` refuses below `MIN_OBSERVATIONS = 30`, so a
lineage whose representative met fewer than 30 banks gets
`dsr_status = "insufficient_observations"` and NOT a verdict of convenience.
That is a gate that CAN go green -- one representative in the 09-08 log met 342
banks -- so it is a refusal, not a permanent red line.

WHAT THE VERDICT DOES
=====================
`DEPRIORITIZED`, never `deleted` and never a bare `STOP` (CLAUDE.md, "EXPLORE
DIRTY, PROMOTE CLEAN"). A deprioritized lineage keeps every row it ever wrote
in `G3_evaluations.jsonl`, gets a row in `G3_lineage_verdicts.jsonl` saying
why, and is excluded from `SearchState.update_elites` so the next night does
not breed from it. It may be re-tested later under the corpse-check pattern if
a genuinely new instrument appears -- never re-run under the identical
bank/seed regime that produced the verdict, which would only reproduce the
overfitting the deflation caught.

    python -m scripts.night_stopping_rules                 # the real logs
    python -m scripts.night_stopping_rules --smoke
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.strategy import multipletesting as MT           # noqa: E402
from learner import evidence_memory as EM                    # noqa: E402

#: Where the night directories live. One per run date.
NIGHTS = REPO / "backend" / "data" / "optimus"

#: The bars. Imported, never re-declared: `evidence_memory` already owns them
#: and a second copy would drift.
DSR_BAR = EM.DSR_BAR          # 0.95
PBO_BAR = EM.PBO_BAR          # 0.5

#: DERIVED, not chosen. `probabilistic_sharpe_ratio` raises below this, and a
#: local constant would be a second opinion about the same floor.
MIN_DSR_OBSERVATIONS = MT.MIN_OBSERVATIONS

#: CSCV subsets. Must be even and >= 4; 16 is the vendored default.
CSCV_SPLITS = MT.DEFAULT_CSCV_SPLITS

#: A lineage enters the table only if its representative met this many banks --
#: the archive's own admission bar in `night_g3_evolve_v2`.
MIN_BANKS = 2

#: Where the verdicts land. Append-only, like every other JSONL here.
VERDICTS_NAME = "G3_lineage_verdicts.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _r(v, nd=4):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return None
    return round(float(v), nd)


# --------------------------------------------------------------- reading

def read_evaluations(paths) -> list[dict]:
    """Every evaluation row from one or more `G3_evaluations.jsonl` files.

    A malformed line is SKIPPED rather than repaired: a half-written line at
    the tail is what a killed job leaves, and guessing at its contents is how a
    crashed run becomes a fabricated one.
    """
    out: list[dict] = []
    for p in ([paths] if isinstance(paths, (str, Path)) else list(paths)):
        p = Path(p)
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("key"):
                out.append(row)
    return out


def evaluation_logs(base: Path | None = None) -> list[Path]:
    """Every `G3_evaluations.jsonl` under the night directories, name-ordered.

    Never mtime-ordered: a fresh CI checkout rewrites every file, so mtime is
    an order on checkout time (CLAUDE.md session protocol item 7).
    """
    base = Path(base or NIGHTS)
    if not base.is_dir():
        return []
    return sorted(base.glob("night_factory_*/G3_evaluations.jsonl"),
                  key=lambda p: str(p))


# ------------------------------------------------------- the lineage table

def lineage_table(rows, *, min_banks: int = MIN_BANKS) -> dict:
    """One representative per lineage, with its per-bank fitness vector.

    The representative is the lineage's BEST-MEASURED member -- ordered by
    (banks met, then median fitness) -- which is the rule `night_g3_evolve_v2`
    settled on after the 09-10 finding that ranking by fitness first made 248
    of 251 lineages speak through a genome that had met exactly one bank.
    Picking the higher-scoring member would be selection on the outcome inside
    the very test that exists to correct for selection.
    """
    per: dict[str, dict[int, float]] = {}
    windows: dict[str, dict[int, int]] = {}
    lineage_of: dict[str, str] = {}
    for r in rows:
        key = str(r.get("key"))
        res = r.get("result") or {}
        fit = res.get("fitness")
        lineage_of.setdefault(key, str(r.get("lineage") or key))
        if fit is None or not math.isfinite(float(fit)):
            continue
        bank = int(r.get("bank_seed") or 0)
        per.setdefault(key, {})[bank] = float(fit)
        windows.setdefault(key, {})[bank] = int(res.get("n_windows") or 0)

    by_lineage: dict[str, dict] = {}
    for key, banks in per.items():
        lin = lineage_of.get(key, key)
        vec = [banks[b] for b in sorted(banks)]
        cand = {
            "lineage": lin,
            "representative_key": key,
            "banks_met": len(vec),
            "fitness_vector": vec,
            "bank_seeds": sorted(banks),
            "fitness_median": float(statistics.median(vec)),
            "fitness_best_bank": float(max(vec)),
            "n_windows_measured": int(sum(windows.get(key, {}).values())),
        }
        cur = by_lineage.get(lin)
        if cur is None or ((cand["banks_met"], cand["fitness_median"])
                           > (cur["banks_met"], cur["fitness_median"])):
            by_lineage[lin] = cand

    table = {k: v for k, v in by_lineage.items() if v["banks_met"] >= min_banks}
    return {
        "table": table,
        "per_genome": {k: [banks[b] for b in sorted(banks)] for k, banks in per.items()},
        "n_trials_raw": len(per),
        "n_trials_effective_proxy": len(by_lineage),
        "n_lineages_admitted": len(table),
        "min_banks": min_banks,
        "all_lineages": by_lineage,
    }


def performance_matrix(table: dict) -> tuple[pd.DataFrame, str]:
    """(rows = banks, columns = lineage representatives) for CSCV.

    COMPLETE ROWS ONLY. CSCV ranks strategies against each other inside each
    subset, so a bank where only one representative has a number contributes a
    comparison of one, and a matrix stitched from different banks per column
    would have each split's "winner" decided by who happened to be measured
    there. Dropping incomplete rows can leave too few for the procedure -- that
    is `PBO_INSUFFICIENT_WINDOWS`, a refusal with a count, not a silent number.
    """
    if len(table) < 2:
        return pd.DataFrame(), f"{len(table)} finalist(s); CSCV needs at least 2"
    cols = {}
    for lin, row in sorted(table.items()):
        cols[row["representative_key"]] = dict(zip(row["bank_seeds"],
                                                   row["fitness_vector"]))
    frame = pd.DataFrame(cols).sort_index()
    complete = frame.dropna(axis=0, how="any")
    note = (f"{len(frame)} banks touched by {len(cols)} finalists, "
            f"{len(complete)} of them complete (every finalist measured)")
    return complete, note


# ------------------------------------------------------ the trial dispersion

def trial_sharpe_dispersion(built: dict) -> dict:
    """How widely the SEARCH's trial Sharpes were spread -- the DSR's scale.

    `expected_maximum_sharpe` multiplies this by the expected maximum of N
    standard normals, so it must be measured in SHARPE units. Measuring it in
    %/yr sets the bar in the wrong units entirely; that was this module's first
    bug and its known-answer test is what caught it.

    TWO ESTIMATORS, THE STABLE ONE PRIMARY AND THE DIRECT ONE BESIDE IT.

    * `direct` -- the plain standard deviation of the representatives' own
      per-observation Sharpes. Correct in principle and unusable in practice on
      this data: a genome measured on two banks has a Sharpe of
      `mean / sd` over two numbers, which reaches 89 when the two happen to sit
      close together. Measured on the 09-08 log the direct number is 8.77 and
      is dominated by that artefact, so a bar built on it would deflate
      everything by construction -- strict, not discriminating.
    * `ratio` (PRIMARY) -- `std(representative median fitness) /
      pooled_within_genome_sd`. The numerator is the spread of trial OUTCOMES
      across all lineages, which is measured on 251 numbers rather than 4; the
      denominator is the within-trial per-bank volatility pooled over every
      genome that met two or more banks. It assumes one common within-trial
      volatility, which is an assumption and is named as one on the receipt.

    Both travel in the payload. Neither is invented here: they are two ways of
    estimating the same quantity and the receipt says which one set the bar.
    """
    reps = list(built["all_lineages"].values())
    levels = [r["fitness_median"] for r in reps]
    direct = []
    for r in reps:
        vec = [x for x in r["fitness_vector"] if x is not None]
        if len(vec) < 2:
            continue
        sh = MT.sharpe_ratio(vec)
        if math.isfinite(sh):
            direct.append(float(sh))
    ss, dof = 0.0, 0
    for vec in built.get("per_genome", {}).values():
        v = np.asarray([x for x in vec if x is not None], dtype=float)
        if v.size < 2:
            continue
        ss += float(((v - v.mean()) ** 2).sum())
        dof += int(v.size - 1)
    pooled = math.sqrt(ss / dof) if dof > 0 and ss > 0 else None
    spread = float(np.std(levels, ddof=1)) if len(levels) > 1 else None
    value = (spread / pooled) if (pooled and spread is not None) else None
    return {
        "value": value,
        "basis": "ratio" if value is not None else "unavailable",
        "n_lineage_levels": len(levels),
        "pooled_within_genome_sd": pooled,
        "n_genomes_pooled": sum(1 for v in built.get("per_genome", {}).values()
                                if len([x for x in v if x is not None]) >= 2),
        "spread_of_levels": spread,
        "direct": (float(np.std(direct, ddof=1)) if len(direct) > 1 else None),
        "direct_n": len(direct),
        "note": ("PRIMARY = spread of lineage-representative median fitness "
                 "divided by the pooled within-genome per-bank sd, which "
                 "assumes one common within-trial volatility. The DIRECT "
                 "standard deviation of representative Sharpes is reported "
                 "beside it, never instead of it; on thin data the direct "
                 "number is dominated by two-observation Sharpes."),
    }


# ------------------------------------------------------------------ the maths

def dsr_row(vector, *, n_trials: int, trial_sharpe_std: float | None,
            confidence: float = DSR_BAR) -> dict:
    """`deflated_sharpe_ratio` over one observation vector, or a stated refusal.

    The refusal is typed (`dsr_status`) and carries the count that caused it,
    so a thin lineage reads as "not enough observations yet" rather than as a
    failed test -- the two have opposite consequences for whether the search
    should keep breeding from it.
    """
    v = np.asarray([x for x in vector if x is not None], dtype=float)
    v = v[np.isfinite(v)]
    n = int(v.size)
    out = {"n_observations": n, "observed_sharpe": None, "dsr": None,
           "dsr_bar": confidence, "dsr_survives": None,
           "expected_maximum_sharpe": None,
           "skew": None, "kurtosis": None, "dsr_status": "ok"}
    if trial_sharpe_std is None:
        out["dsr_status"] = "trial_dispersion_unavailable"
        out["reason"] = (
            "the deflation needs the SPREAD of Sharpes across the trials the "
            "search ran, and fewer than two lineage representatives have a "
            "Sharpe at all (a Sharpe needs two measured banks). Passing 0.0 "
            "would set `expected_maximum_sharpe` to zero, i.e. deflate by "
            "nothing while looking deflated.")
        return out
    if n < MIN_DSR_OBSERVATIONS:
        out["dsr_status"] = "insufficient_observations"
        out["reason"] = (f"{n} measured observations is below the "
                         f"{MIN_DSR_OBSERVATIONS} the probabilistic Sharpe "
                         f"refuses under; a deflation on {n} numbers would be "
                         f"a decimal point on a coin flip")
        return out
    sharpe = MT.sharpe_ratio(v)
    if not math.isfinite(sharpe):
        out["dsr_status"] = "no_dispersion"
        out["reason"] = "every observation is identical; a Sharpe is undefined"
        return out
    mean, sd = float(v.mean()), float(v.std(ddof=1))
    skew = float(((v - mean) ** 3).mean() / sd ** 3) if sd > 0 else 0.0
    # NON-EXCESS fourth moment. `scipy.stats.kurtosis` returns the excess form
    # and passing it makes the variance term too small and the confidence too
    # high -- the vendored module's own documented gotcha.
    kurt = (float(((v - mean) ** 4).mean() / sd ** 4) if sd > 0
            else MT.GAUSSIAN_KURTOSIS)
    try:
        res = MT.deflated_sharpe_ratio(
            observed_sharpe=sharpe, n_trials=int(n_trials), n_observations=n,
            trial_sharpe_std=float(trial_sharpe_std), skew=skew, kurtosis=kurt,
            confidence=confidence)
    except ValueError as exc:
        out["dsr_status"] = "refused"
        out["reason"] = f"{type(exc).__name__}: {exc}"
        out["observed_sharpe"] = _r(sharpe, 6)
        return out
    out.update({"observed_sharpe": _r(res.observed_sharpe, 6),
                "expected_maximum_sharpe": _r(res.expected_maximum_sharpe, 6),
                "dsr": _r(res.deflated_sharpe_ratio, 6),
                "dsr_survives": bool(res.survives),
                "n_trials": int(res.n_trials),
                "trial_sharpe_std": _r(res.trial_sharpe_std, 6),
                "skew": _r(skew, 4), "kurtosis": _r(kurt, 4)})
    return out


def pbo_row(frame: pd.DataFrame, note: str, *, n_splits: int = CSCV_SPLITS) -> dict:
    """CSCV over the finalist matrix, or `insufficient_windows` with the count.

    The vendored function RAISES on a matrix too small to split. A night job
    that died there would lose every other lineage's verdict, so the refusal is
    caught and reported: a gate that cannot run says CANNOT DETERMINE rather
    than either crashing or quietly passing.
    """
    out = {"pbo": None, "pbo_bar": PBO_BAR, "pbo_status": "insufficient_windows",
           "pbo_note": note, "pbo_n_splits": None, "pbo_n_strategies": None,
           "performance_degradation": None}
    if frame.empty or frame.shape[1] < 2:
        return out
    try:
        res = MT.probability_of_backtest_overfitting(frame, n_splits=n_splits)
    except ValueError as exc:
        out["pbo_reason"] = f"{type(exc).__name__}: {exc}"
        return out
    out.update({"pbo": _r(res.pbo, 4), "pbo_status": "ok",
                "pbo_n_splits": int(res.n_splits),
                "pbo_n_strategies": int(res.n_strategies),
                "pbo_n_observations": int(res.n_observations),
                "performance_degradation": _r(res.performance_degradation, 4)})
    return out


def verdict_for(dsr: dict, pbo: dict) -> tuple[str, str]:
    """(verdict, reason). DSR first, PBO second, CANNOT_DETERMINE when neither ran.

    The order matters: DSR asks "is this Sharpe bigger than the best of N
    draws", PBO asks "does in-sample selection survive out-of-sample at all".
    A lineage can pass the first and fail the second, which is why both run.
    """
    if dsr.get("dsr_status") == "ok" and dsr.get("dsr_survives") is False:
        return "DEPRIORITIZED", (
            f"DSR {dsr['dsr']:.3f} <= {dsr['dsr_bar']} bar at "
            f"n_trials={dsr.get('n_trials')}")
    if pbo.get("pbo_status") == "ok" and pbo["pbo"] > PBO_BAR:
        return "DEPRIORITIZED", f"PBO {pbo['pbo']:.3f} > {PBO_BAR} bar"
    if dsr.get("dsr_status") == "ok":
        return "ACTIVE", (f"DSR {dsr['dsr']:.3f} > {dsr['dsr_bar']} bar"
                          + ("" if pbo.get("pbo_status") == "ok"
                             else "; PBO could not run"))
    return "CANNOT_DETERMINE", (
        f"DSR {dsr.get('dsr_status')} ({dsr.get('reason', '')}); "
        f"PBO {pbo.get('pbo_status')}. A check that did not run is not a check "
        f"that passed -- this lineage is neither cleared nor deprioritized.")


# ------------------------------------------------------------ the RW1 control

def rw1_null_control(parquet: Path | None = None, *, n_trials: int,
                     trial_sharpe_std: float | None) -> dict:
    """The random-genome null, run through the SAME wrapper as the search.

    G3's `fitness` is already an excess over a random-genome null bar drawn on
    the same windows, so within G3 the null's fitness is 0 BY CONSTRUCTION and
    there is nothing left to deflate. RW1 measured five independent random
    genomes per window (`NULL_random_0..4`, 240 windows x 2 constructions) and
    its parquet keeps the per-window `beta_matched_ann_pct`. Those vectors are
    a control this module can actually score: if the wrapper hands a random
    genome a surviving DSR, the wiring is wrong.

    THE UNIT DIFFERS AND SAYING SO IS THE POINT: the null's observations are
    per WINDOW, a lineage's are per BANK (itself a median over ~24 windows).
    Per-bank dispersion is narrower, so the two Sharpes are not comparable
    level-to-level. Only the survives/does-not-survive verdict is.
    """
    p = Path(parquet) if parquet else None
    if p is None:
        cands = sorted(NIGHTS.glob("night_factory_*/RW1_windows.parquet"))
        p = cands[-1] if cands else None
    if p is None or not Path(p).is_file():
        return {"available": False,
                "reason": f"no RW1_windows.parquet under {NIGHTS}"}
    df = pd.read_parquet(p, columns=["strategy", "construction",
                                     "beta_matched_ann_pct", "is_null"])
    nulls = df[df["is_null"].astype(bool)]
    arms = []
    for (strategy, construction), grp in nulls.groupby(["strategy", "construction"]):
        vec = grp["beta_matched_ann_pct"].to_numpy(dtype=float)
        row = dsr_row(vec, n_trials=n_trials, trial_sharpe_std=trial_sharpe_std)
        arms.append({"strategy": str(strategy), "construction": str(construction),
                     "median_excess_pct": _r(float(np.nanmedian(vec))), **row})
    survived = [a for a in arms if a.get("dsr_survives")]
    return {"available": True, "receipt": str(p), "n_arms": len(arms),
            "observation_unit": "one WINDOW (240 windows x 2 constructions)",
            "n_survived_dsr": len(survived),
            "max_dsr": max((a["dsr"] for a in arms if a.get("dsr") is not None),
                           default=None),
            "arms": arms,
            "note": ("the control is scored at the SAME n_trials and "
                     "trial_sharpe_std as the search cohort; its observation "
                     "unit is a window, the cohort's is a bank, so only the "
                     "survives/does-not verdict is comparable, never the level")}


# ------------------------------------------------------------------ the pass

def stopping_verdicts(rows, *, min_banks: int = MIN_BANKS,
                      run: str = "unknown", night_index: int | None = None,
                      evaluations_log: str = "", search_state: str = "",
                      n_splits: int = CSCV_SPLITS) -> dict:
    """Every lineage's verdict plus the receipt block. Writes nothing."""
    built = lineage_table(rows, min_banks=min_banks)
    table = built["table"]
    n_raw = built["n_trials_raw"]
    n_proxy = built["n_trials_effective_proxy"]

    # THE DISPERSION IS OF SHARPES, NOT OF FITNESSES -- see
    # `trial_sharpe_dispersion` for the two estimators and why the stable one
    # is primary. The first version of this function passed the spread of
    # fitness LEVELS straight in, and a planted +6%/yr edge failed its own
    # known-answer test against a bar of 2. That is how the unit error was
    # caught rather than shipped.
    disp = trial_sharpe_dispersion(built)
    trial_sd = disp["value"]

    frame, note = performance_matrix(table)
    pbo = pbo_row(frame, note, n_splits=n_splits)

    verdicts = []
    for lin, row in sorted(table.items()):
        dsr = dsr_row(row["fitness_vector"], n_trials=n_proxy,
                      trial_sharpe_std=trial_sd)
        dsr_raw = dsr_row(row["fitness_vector"], n_trials=n_raw,
                          trial_sharpe_std=trial_sd)
        verdict, reason = verdict_for(dsr, pbo)
        verdicts.append({
            "utc": _now(), "run": run, "night_index": night_index,
            "lineage": lin, "representative_key": row["representative_key"],
            "banks_met": row["banks_met"],
            "n_windows_measured": row["n_windows_measured"],
            "observation_unit": ("one window BANK; a bank's fitness is itself "
                                 "the median over its ~24 windows"),
            "fitness_median": _r(row["fitness_median"]),
            "fitness_best_bank": _r(row["fitness_best_bank"]),
            "n_trials_raw": n_raw,
            "n_trials_effective_proxy": n_proxy,
            "n_trials_effective_onc": None,
            "n_trials_effective_onc_gap": (
                "ONC clusters trials by the correlation of their RETURN "
                "SERIES; G3 persists one scalar fitness per (genome, bank), so "
                "the vector ONC needs does not exist on disk. Until it does, "
                "the lineage count is a proxy that over-counts independent "
                "trials and the raw genome count is reported beside it."),
            "trial_sharpe_std": _r(trial_sd, 6),
            "trial_sharpe_std_basis": disp["basis"],
            "trial_sharpe_std_direct": _r(disp["direct"], 6),
            "trial_sharpe_std_direct_n": disp["direct_n"],
            "trial_sharpe_std_unit": ("a standard deviation of PER-OBSERVATION "
                                      "SHARPES across the search's trials -- "
                                      "not of their fitness levels"),
            **{k: v for k, v in dsr.items() if k != "n_trials"},
            "dsr_at_n_trials_raw": dsr_raw.get("dsr"),
            "dsr_survives_at_n_trials_raw": dsr_raw.get("dsr_survives"),
            **{k: v for k, v in pbo.items() if k != "pbo_note"},
            "null_refused_rate": None,
            "null_refused_rate_status": (
                "CANNOT DETERMINE from the evaluations log: `n_null_refused` "
                "is a run-level counter in the G3 receipt, not a per-bank "
                "field on the row. Reported, never gated on (spec 2.5)."),
            "verdict": verdict, "reason": reason,
            "receipt_evaluations_log": evaluations_log,
            "receipt_search_state": search_state,
        })
    counts: dict[str, int] = {}
    for v in verdicts:
        counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1
    return {"verdicts": verdicts, "counts": counts,
            "n_trials_raw": n_raw, "n_trials_effective_proxy": n_proxy,
            "trial_sharpe_std": _r(trial_sd, 6),
            "trial_sharpe_dispersion": disp,
            "n_lineages_admitted": len(table),
            "min_banks": min_banks,
            "pbo": pbo, "matrix_note": note}


def append_verdicts(path: Path, verdicts: list[dict]) -> Path:
    """Append-only, one line per lineage per pass. Nothing is ever rewritten."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for v in verdicts:
            fh.write(json.dumps(v, default=str) + "\n")
    return path


def deprioritized_lineages(path: Path | None = None) -> set[str]:
    """The lineages the LATEST pass deprioritized, for the next night's resume.

    Latest wins per lineage: the file is append-only, so a lineage that was
    deprioritized in one pass and cleared in a later one (more banks met, a new
    verdict) must not be excluded forever by its own history.
    """
    p = Path(path) if path else None
    if p is None:
        cands = sorted(NIGHTS.glob(f"night_factory_*/{VERDICTS_NAME}"))
        p = cands[-1] if cands else None
    if p is None or not Path(p).is_file():
        return set()
    latest: dict[str, str] = {}
    for line in Path(p).read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        lin = row.get("lineage")
        if lin:
            latest[str(lin)] = str(row.get("verdict") or "")
    return {k for k, v in latest.items() if v == "DEPRIORITIZED"}


def E5_stopping_rules(smoke: bool = False, run: int = 1,
                      logs=None, out_dir: Path | None = None,
                      min_banks: int = MIN_BANKS) -> dict:
    """The night job. Reads the evaluation logs, writes the verdicts receipt."""
    paths = [Path(p) for p in (logs or evaluation_logs())]
    rows = read_evaluations(paths)
    if smoke:
        rows = rows[:1200]
    out = Path(out_dir) if out_dir else (paths[-1].parent if paths
                                         else NIGHTS / "night_factory_stopping")
    state = out / "night_search_state.json"
    res = stopping_verdicts(
        rows, min_banks=min_banks, run=f"{run:02d}",
        evaluations_log=str(paths[-1]) if paths else "",
        search_state=str(state) if state.exists() else "ABSENT")
    written = (append_verdicts(out / VERDICTS_NAME, res["verdicts"])
               if res["verdicts"] else None)
    null = rw1_null_control(n_trials=res["n_trials_effective_proxy"],
                            trial_sharpe_std=res["trial_sharpe_std"])
    counts = res["counts"]
    head = (f"{res['n_lineages_admitted']} lineages admitted at banks_met>="
            f"{min_banks} out of {res['n_trials_effective_proxy']} "
            f"({res['n_trials_raw']} distinct genomes); "
            + ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
            + f"; PBO {res['pbo']['pbo_status']}")
    return {
        "job": "E5_stopping_rules", "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0,
        "question": ("Which G3 lineages survive the deflation for how many "
                     "genomes the search tried, and which should the next "
                     "night stop breeding from?"),
        "inputs": [str(p) for p in paths],
        "n_evaluation_rows": len(rows),
        "bars": {"dsr_bar": DSR_BAR, "pbo_bar": PBO_BAR,
                 "min_dsr_observations": MIN_DSR_OBSERVATIONS,
                 "source": ("learner.evidence_memory / "
                            "multipletesting.MIN_OBSERVATIONS")},
        "counts": counts,
        "n_trials_raw": res["n_trials_raw"],
        "n_trials_effective_proxy": res["n_trials_effective_proxy"],
        "n_trials_effective_onc": None,
        "trial_sharpe_std": res["trial_sharpe_std"],
        "trial_sharpe_dispersion": res["trial_sharpe_dispersion"],
        "pbo": res["pbo"], "matrix_note": res["matrix_note"],
        "rw1_null_control": null,
        "deprioritized": sorted(v["lineage"] for v in res["verdicts"]
                                if v["verdict"] == "DEPRIORITIZED"),
        "verdicts_receipt": str(written) if written else None,
        "verdicts": res["verdicts"][:24],
        "headline": head,
        "verdict": ("STOPPING RULES APPLIED: " + head) if res["verdicts"] else
                   ("NO LINEAGE ADMITTED: every lineage representative met "
                    f"fewer than {min_banks} banks, so nothing is either "
                    "cleared or deprioritized. A refusal, not a pass."),
        "written_utc": _now(),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--min-banks", type=int, default=MIN_BANKS)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    payload = E5_stopping_rules(smoke=a.smoke, run=a.run, min_banks=a.min_banks)
    dest = (Path(a.out) if a.out else
            NIGHTS / f"night_factory_{datetime.now(timezone.utc):%Y-%m-%d}"
            / f"E5_stopping_rules_run{a.run:02d}{'_smoke' if a.smoke else ''}.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    print(f"E5_stopping_rules: {payload['headline']}\n  -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
