"""CAPITAL ALLOCATOR / DECISION ENGINE v0 -- SHADOW ONLY.

Licence: PRODUCT_EXPERIMENT (shadow). This module emits DecisionArtifacts and
nothing reads them for execution. It has no broker client, no order path, no
import from the execution repo, and backend/tests/test_allocator.py pins that
boundary as a failing test, not a promise.

WHY THIS MODULE EXISTS (the idle two-thirds, 2026-09-03)
========================================================
The external review (docs/REVIEW_2026-09-03_GPT_VERDICTS_AND_CAPITAL_ALLOCATOR.md
PART B) named the program's largest bottleneck: AEGIS is much better at
research, falsification and post-mortems than at converting an imperfect
belief into a portfolio. The live receipt of the disease: SPY flat over the
competition window while hack3/4/6 sat 60-67% cash with NO OPINION RECORDED
about the idle two-thirds. "17 names failed admission so $70,000 is idle" is
not a decision. The one-line spec this module implements:

    Every unused dollar gets a documented competing allocation, and cash must
    BEAT THE BENCHMARK IN EXPECTATION to be held. The benchmark is the
    parking orbit; cash requires a thesis.

BINDING CONSTRAINTS ARE FIRST-CLASS (the invisible 40% ceiling, 2026-09-04)
===========================================================================
aegis-alpha-terminal/docs/FINDING_2026-09-04_THE_INVISIBLE_40PCT_CEILING.md:
the fleet's real deployment ceiling was a driver-taxonomy gap -- every
whole-market name fell into ONE `UNCLASSIFIED` bucket and a 40% per-driver cap
silently capped three books at ~35-40% deployed while every surface showed
ACTUAL vs INTENT and none showed the BINDING ceiling. A ceiling that cannot be
seen teaches the reader that idle = chosen. So in a DecisionArtifact every
sleeve row carries `binding_constraint` -- the cap or gate that actually bound
it, or the explicit statement that none did -- and the artifact carries a
top-level `binding_constraints` list. There is no path through this code that
produces a weight without naming what bound it.

EVERY NUMBER CITES ITS RECEIPT OR SAYS PRIOR_ONLY
=================================================
`corr = 0.516` once lived in prose only and turned out to be a filtered subset
nobody had named (CLAUDE.md). Here every E[excess], CVaR proxy, cost and
uncertainty input is a COMPONENT dict carrying `basis`:

    cited      -- value read from a receipt at build time; `source` is
                  "<receipt path>#<key.path>" and the extraction REFUSES if
                  the key is absent (a missing receipt is never a zero);
    DEFINITION -- true by construction (the benchmark's own excess is 0);
    PRIOR_ONLY -- a declared prior with no receipt behind it yet; the
                  artifact's `missing_inputs_v1_must_replace` lists every one;
    REFUSED    -- not computable; `reason` names the missing input.

THE OBJECTIVE (PART B, declared not implied)
============================================
    U_i = E[R_i - R_bench] - l1*CVaR_i - l2*Costs_i - l3*Uncertainty_i

per personality, lambdas in PERSONALITIES below (a config block, not prose).
v0 term semantics, named honestly:

* E is the receipt's NET annualised excess vs the VW market. Because it is
  already net of the backtest's trading costs, Costs_i is 0 for backtested
  sleeves (double-counting a cost is as wrong as omitting it) and the
  receipt's measured drag is carried as information.
* CVaR_i is the receipt's |max drawdown| -- a full-window tail-loss PROXY,
  not a per-horizon CVaR. v1 replaces it with states-based tail estimates
  (review Q7: states rank loss/tail, which is what sizing consumes).
* Uncertainty_i sums named sub-components: the standard error implied by the
  receipt's paired t (|E|/t), the era dispersion (pooled minus 2022-24
  excess -- the S36 lesson that pooled numbers flatter), and carries the
  model-null percentile as evidence. Missing sub-components are named, never
  silently zero.

A sleeve is admitted only when U_i > U_bench (it must beat the parking
orbit). Cash is a sleeve like any other EXCEPT that a positive margin alone
never funds it: without an explicit bearish/deleveraging thesis the cash
weight is 0 and the artifact records that cash would have won numerically.
An allocator that drifts into cash by arithmetic is the itsang89 mirror
(knew it was underinvested, wrote about it daily, never deployed).

DELIBERATELY STDLIB-ONLY
========================
This module imports nothing beyond the standard library: it consumes one
PotentialUniverse JSONL vintage and four JSON receipts. Not inheriting the
learner's sklearn/pandas stack keeps the no-broker/no-heavyweight boundary
auditable by reading the import block.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
PU_DIR = REPO / "backend" / "data" / "optimus" / "potential_universe"
OUT_DIR = REPO / "backend" / "data" / "optimus" / "decision_artifacts"

CODE_VERSION = "capital_allocator_v0/2026-09-04"
LICENCE = "PRODUCT_EXPERIMENT (shadow)"
AUTHORITY = ("SHADOW_ONLY — this artifact places nothing and nothing reads "
             "it for execution")

# ----------------------------------------------------------------- receipts
#
# Repo-relative receipt paths, declared once. The values below are NEVER
# retyped into this file: builders extract them at build time and refuse when
# a key is absent.
RECEIPT_PATHS = {
    "revision_6m": "backend/data/optimus/tracker_backtest/revision_6m_cohorts_20260904.json",
    "learner_v2": "backend/data/optimus/tracker_backtest/learner_v2_20260903.json",
    "learner_v1_null": "backend/data/optimus/tracker_backtest/learner_v1_model_null_64_20260904.json",
    "toxic_short": "backend/data/optimus/tracker_backtest/toxic_band_short_20260904.json",
}

#: The revision sleeve's arm: the contract draft's default falsifier variant
#: (toxic + left-band exits, market-park), the measured best on both terminal
#: wealth and drawdown (docs/CONTRACT_DRAFT_2026-09-04_REVISION_6M.md §9).
REV_ARM = "cohort_H6m_falsifier_toxic_leftband_mktpark_25bps"

# ------------------------------------------------------------ personalities
#
# EVERY lambda here is PRIOR_ONLY: declared, uncalibrated, chosen so the
# drawdown penalty is a tail tilt rather than the dominant term (a maxDD of
# ~0.3 against an annual excess of ~0.02-0.18 would otherwise decide
# everything). v1 must derive these from the declared utility functions
# (docs/OPTIMUS_OBJECTIVE.md: four personalities are DECLARED PREFERENCES)
# and calibrate them on the farm's replayed histories. l2 is 1.0 everywhere:
# a dollar of cost is a dollar for every personality.
PERSONALITIES: dict[str, dict[str, float]] = {
    "preservation":   {"l1": 0.50, "l2": 1.0, "l3": 2.00, "max_sleeve_weight": 0.25},
    "balanced":       {"l1": 0.25, "l2": 1.0, "l3": 1.00, "max_sleeve_weight": 0.40},
    "aggressive":     {"l1": 0.10, "l2": 1.0, "l3": 0.50, "max_sleeve_weight": 0.60},
    "extreme_growth": {"l1": 0.05, "l2": 1.0, "l3": 0.25, "max_sleeve_weight": 0.80},
}
LAMBDAS_BASIS = ("PRIOR_ONLY -- declared, uncalibrated; v1 derives them from "
                 "the four declared utility functions and calibrates on "
                 "replayed farm histories")

#: Gross exposure cap. No leverage in v0: the ladder (1x -> 1.5x -> 2x, each
#: rung graded on compound wealth after drawdown) belongs to a later frozen
#: contract, not to a shadow allocator's first artifact.
GROSS_CAP = 1.0

#: Golden keys, pinned like the PotentialUniverse's. Changing either tuple is
#: a schema change and must bump CODE_VERSION.
ARTIFACT_KEYS = (
    "artefact", "version", "licence", "authority", "day", "generated_at_utc",
    "personality", "lambdas", "universe", "allocations", "residual",
    "cash_policy", "binding_constraints", "worst_case",
    "regret_decomposition_spec", "missing_inputs_v1_must_replace", "schema",
)
ALLOCATION_ROW_KEYS = (
    "sleeve", "gate", "u_components", "U", "u_margin_vs_benchmark", "weight",
    "binding_constraint", "notes",
)


def schema_hash() -> str:
    blob = json.dumps({"artifact": list(ARTIFACT_KEYS),
                       "row": list(ALLOCATION_ROW_KEYS),
                       "version": CODE_VERSION}, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


# ------------------------------------------------- component dict helpers
#
# One shape for every number in the artifact. `value` in annualised decimal
# return units unless `unit` says otherwise.

def cited(value, receipt_key: str, keypath: str, *,
          unit: str = "annualised decimal", note: str | None = None) -> dict:
    """Numeric values are rounded; text values (a verdict string, a receipt's
    own caveat prose) are carried verbatim -- a citation is not only a number."""
    try:
        v = round(float(value), 6) if value is not None else None
    except (TypeError, ValueError):
        v = value
    c = {"value": v, "unit": unit, "basis": "cited",
         "source": f"{RECEIPT_PATHS[receipt_key]}#{keypath}"}
    if note:
        c["note"] = note
    return c


def definition(value: float, why: str, *, unit: str = "annualised decimal") -> dict:
    return {"value": round(float(value), 6), "unit": unit,
            "basis": "DEFINITION", "note": why}


def prior_only(value: float, why: str, *, unit: str = "annualised decimal") -> dict:
    return {"value": round(float(value), 6), "unit": unit,
            "basis": "PRIOR_ONLY", "note": why}


def refused(reason: str) -> dict:
    return {"value": None, "unit": None, "basis": "REFUSED", "reason": reason}


def _refusal_gate(*components: dict) -> str:
    """The gate label for a refused sleeve, naming WHY it is unpriceable.

    Two refusals look identical in a weight column and are not the same finding:
    a receipt we cannot READ is an operational problem (wrong path, absent file,
    corrupt JSON), while a receipt that has been SUPERSEDED is an evidence
    problem — the file is fine and the number in it is wrong. Printing
    "RECEIPT_UNREADABLE" for the second sends the reader to look for a missing
    file that is sitting right there.
    """
    reasons = [c.get("reason") or "" for c in components
               if c.get("basis") == "REFUSED"]
    if any("VOID" in r for r in reasons):
        return "NOT_DEPLOYABLE_RECEIPT_VOID_SUPERSEDED"
    if any("key absent" in r for r in reasons):
        return "NOT_DEPLOYABLE_RECEIPT_KEY_ABSENT"
    return "NOT_DEPLOYABLE_RECEIPT_UNREADABLE"

def _dig(obj: Any, keypath: str):
    """(ok, value) down a dotted keypath. ok=False on ANY missing step --
    absence of a key is not a value of zero (the docs-move that disarmed the
    budget gate read absence as $0.00; this function is the antidote shape)."""
    cur = obj
    for part in keypath.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False, None
        cur = cur[part]
    return True, cur


#: Marker `load_receipts` substitutes for a receipt that has been superseded.
#: A dict rather than None so the reason travels to the refusal.
VOID_SENTINEL = "__VOID_SUPERSEDED__"


def _extract(receipts: dict, receipt_key: str, keypath: str, *,
             unit: str = "annualised decimal", note: str | None = None) -> dict:
    """A cited component, or a REFUSED one naming exactly what is missing."""
    if receipt_key not in receipts or receipts[receipt_key] is None:
        return refused(f"receipt unreadable: {RECEIPT_PATHS[receipt_key]}")
    void = receipts[receipt_key].get(VOID_SENTINEL) \
        if isinstance(receipts[receipt_key], dict) else None
    if void:
        # A superseded receipt is not a degraded input, it is a WRONG one. The
        # allocator refuses rather than reading it, and refuses rather than
        # silently following the sidecar to the replacement: which arm to cite
        # from a re-issued receipt is a research decision, and on 2026-09-05 the
        # answer changed sign (REV_ARM went +1.745pp t +0.73 -> -7.71pp t -1.19).
        # Substituting the new number here would have re-derived a sleeve weight
        # from evidence that refutes the sleeve.
        return refused(
            f"receipt VOID -- superseded: {RECEIPT_PATHS[receipt_key]} "
            f"-> {void.get('superseded_by')} ({void.get('reason', 'no reason recorded')}). "
            "Repoint RECEIPT_PATHS and re-choose the arm deliberately; do not "
            "assume the same arm survives.")
    ok, v = _dig(receipts[receipt_key], keypath)
    if not ok or v is None:
        return refused(f"key absent from receipt: "
                       f"{RECEIPT_PATHS[receipt_key]}#{keypath}")
    return cited(v, receipt_key, keypath, unit=unit, note=note)


def load_receipts(repo: Path | None = None) -> dict[str, dict | None]:
    """Read every registered receipt; unreadable -> None (the builders turn
    that into named refusals, never into zeros)."""
    repo = repo or REPO
    out: dict[str, dict | None] = {}
    for key, rel in RECEIPT_PATHS.items():
        p = repo / rel
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            out[key] = None
            continue
        # DERIVE supersession from the filesystem rather than from a hand-kept
        # list here. B1 re-issued four tape receipts on 2026-09-05 and wrote a
        # `<name>.SUPERSEDED_BY.json` sidecar beside each sealed original; two of
        # those four are cited above. A consumer that reads a void receipt and
        # reports a number is worse than one that refuses, because the number
        # looks fresh. Sealed receipts are never edited, so the sidecar is the
        # only place this fact can live.
        sidecar = p.with_name(p.name + ".SUPERSEDED_BY.json")
        if sidecar.exists() and isinstance(payload, dict):
            try:
                meta = json.loads(sidecar.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                meta = {"reason": "sidecar present but unreadable"}
            payload = dict(payload)
            payload[VOID_SENTINEL] = {
                "sidecar": sidecar.name,
                "superseded_by": meta.get("superseded_by"),
                "reason": meta.get("reason"),
                "status": meta.get("status"),
            }
        out[key] = payload
    return out


# --------------------------------------------------- PotentialUniverse input

def read_potential_universe(path: Path) -> dict:
    """Light JSONL reader (header line + scorecard lines). Duplicated from
    learner/potential_universe.py ON PURPOSE: importing that module drags the
    full sklearn/pandas scorer stack into a consumer that only needs to parse
    six lines of JSON, and the stdlib-only boundary here is load-bearing."""
    with Path(path).open("r", encoding="utf-8") as fh:
        header = json.loads(fh.readline())
        cards = [json.loads(line) for line in fh if line.strip()]
    return {"header": header, "scorecards": cards}


def latest_pu_day(pu_dir: Path | None = None) -> str | None:
    d = pu_dir or PU_DIR
    if not d.exists():
        return None
    days = sorted(p.stem for p in d.glob("*.jsonl"))
    return days[-1] if days else None


def _universe_evidence(pu: dict | None) -> dict:
    """What the vintage can tell the allocator, and what it cannot -- the
    starved-seal sensor read at allocation time, not discovered after."""
    if pu is None:
        return {"status": "REFUSED",
                "reason": "no PotentialUniverse vintage supplied; sleeve "
                          "capacity and universe evidence are unknowable, "
                          "not assumed"}
    h = pu["header"]
    counts = h.get("counts", {})
    return {
        "status": h.get("status"),
        "day": h.get("day"),
        "version": h.get("version"),
        "n_scorecards": counts.get("n_scorecards"),
        "by_engine_verdict": counts.get("by_engine_verdict"),
        "by_capacity_tier": counts.get("by_capacity_tier"),
        "d_catalyst_unreadable": counts.get("d_catalyst_unreadable"),
        "whole_universe_refusals": {
            k: {kk: v.get(kk) for kk in ("refused_on", "of")}
            for k, v in (h.get("whole_universe_refusals") or {}).items()
            if isinstance(v, dict)},
        "note": "verdict counts bound sleeve capacity in NAMES; dollar "
                "capacity per sleeve is a v1 gap (listed below)",
    }


# ------------------------------------------------------------ sleeve builders
#
# Each builder returns {name, gate, components, notes}. `gate` is either
# "DEPLOYABLE" or a named refusal; a gated sleeve still appears in the
# artifact with weight 0 -- omitting it would be the invisible-ceiling shape.

def _uncertainty_total(subs: dict[str, dict]) -> dict:
    """Sum the NUMERIC uncertainty sub-components; carry the rest by name.
    A missing sub-component stays visible instead of averaging away."""
    total = 0.0
    used, missing = [], []
    for name, c in subs.items():
        if c.get("value") is not None and c.get("basis") != "REFUSED":
            total += abs(float(c["value"]))
            used.append(name)
        else:
            missing.append(name)
    return {"value": round(total, 6), "unit": "annualised decimal",
            "basis": "derived", "summed": used, "missing": missing,
            "sub_components": subs,
            "note": "sum of |sub-components|; derived from cited/PRIOR_ONLY "
                    "inputs, each carrying its own basis"}


def _sleeve_revision_6m(receipts: dict) -> dict:
    e_pooled = _extract(receipts, "revision_6m", f"arms.{REV_ARM}.excess_cagr",
                        note="NET of 25bps/side; pooled 2015-02..2024-12; the "
                             "contract's §0 forbids quoting this row alone")
    e_adverse = _extract(receipts, "revision_6m",
                         f"subwindow_2022_2024.{REV_ARM}.excess_cagr",
                         note="the ADVERSE era leads (contract §0): 2022-24 the "
                              "book LOSES to the VW market -- the pooled edge is "
                              "concentrated pre-2022")
    t_pooled = _extract(receipts, "revision_6m", f"arms.{REV_ARM}.t_paired_vs_vw",
                        unit="t-stat")
    t_adverse = _extract(receipts, "revision_6m",
                         f"subwindow_2022_2024.{REV_ARM}.t_paired_vs_vw",
                         unit="t-stat")
    cvar = _extract(receipts, "revision_6m", f"arms.{REV_ARM}.max_drawdown",
                    unit="max drawdown, decimal",
                    note="|maxDD| as tail-loss proxy (v0 convention)")
    drag = _extract(receipts, "revision_6m",
                    f"arms.{REV_ARM}.implied_annual_cost_drag_pct",
                    unit="pct/yr",
                    note="measured drag at 25bps/side -- INFORMATION ONLY: "
                         "E is already net of it")

    subs: dict[str, dict] = {}
    if e_pooled["basis"] == "cited" and t_pooled["basis"] == "cited" \
            and t_pooled["value"]:
        subs["stderr_from_paired_t"] = {
            "value": round(abs(e_pooled["value"] / t_pooled["value"]), 6),
            "unit": "annualised decimal", "basis": "derived",
            "note": "|E|/t from the two cited numbers above (t 0.73-shaped: "
                    "the excess does not clear any significance bar and the "
                    "uncertainty term says so)"}
    else:
        subs["stderr_from_paired_t"] = refused(
            "needs cited excess_cagr and nonzero t_paired_vs_vw")
    if e_pooled["basis"] == "cited" and e_adverse["basis"] == "cited":
        subs["era_dispersion"] = {
            "value": round(abs(e_pooled["value"] - e_adverse["value"]), 6),
            "unit": "annualised decimal", "basis": "derived",
            "note": "pooled minus 2022-24 excess: the S36 overlap-flattery "
                    "lesson as a number"}
    else:
        subs["era_dispersion"] = refused("needs both pooled and 2022-24 excess rows")
    null_p = _extract(receipts, "revision_6m",
                      "null_vs_random_from_pool.metrics."
                      "monthly_excess_mean_pct.p_one_sided",
                      unit="p, one-sided",
                      note="ranking-vs-own-pool null (64 draws); the pool-vs-"
                           "market question remains the t above")

    gate = "DEPLOYABLE"
    if e_pooled["basis"] == "REFUSED" or cvar["basis"] == "REFUSED":
        gate = _refusal_gate(e_pooled, cvar)
    return {
        "name": "revision_6m",
        "gate": gate,
        "components": {
            "e_excess": e_pooled,
            "e_excess_2022_2024": e_adverse,
            "t_paired_pooled": t_pooled,
            "t_paired_2022_2024": t_adverse,
            "cvar": cvar,
            "costs": (definition(
                0.0, "E is NET of 25bps/side already; charging the measured "
                     "drag again would double-count. Drag carried beside it.")
                if drag["basis"] == "cited" else refused(
                    "cost drag key unreadable; cannot confirm E is net")),
            "cost_drag_information": drag,
            "uncertainty": _uncertainty_total({
                "stderr_from_paired_t": subs["stderr_from_paired_t"],
                "era_dispersion": subs["era_dispersion"]}),
            "null_evidence": null_p,
        },
        "notes": [
            "contract draft docs/CONTRACT_DRAFT_2026-09-04_REVISION_6M.md, "
            "NOT frozen; arm = " + REV_ARM + " (draft default variant)",
            "this experiment tests whether the pre-2022 revision edge "
            "RETURNS; forward paper is the only admissible evidence either way",
        ],
    }


def _sleeve_learner_v2(receipts: dict, pu: dict | None) -> dict:
    base = "champions.1m.tradable_floor_variant"
    e = _extract(receipts, "learner_v2", f"{base}.annualised_excess",
                 note="frozen champion encoder_clf__residual, 1m, NET of "
                      "10bps/side, $3.0m/day tradable floor applied")
    t = _extract(receipts, "learner_v2", f"{base}.t_stat_paired_vs_market",
                 unit="t-stat")
    cvar = _extract(receipts, "learner_v2", f"{base}.risk.max_drawdown_net",
                    unit="max drawdown, decimal",
                    note="|maxDD| as tail-loss proxy (v0 convention); "
                         "cvar_05_monthly also in receipt")
    cvar_m = _extract(receipts, "learner_v2", f"{base}.risk.cvar_05_monthly",
                      unit="monthly decimal",
                      note="INFORMATION: monthly CVaR(5%), not yet the U term")
    null_p = _extract(receipts, "learner_v2",
                      "model_null_distribution.horizons.1m.arms."
                      "encoder_clf__residual.p_vs_model_null_paired_t",
                      unit="p, one-sided",
                      note="64 fitted-on-shuffled draws; dev bar per review Q1 "
                           "-- capital-authoritative wants >=256 + family-max")
    v1_caveat = _extract(receipts, "learner_v1_null",
                         "model_null_64_20260904.arms.lgbm_clf."
                         "verdict_paired_t.verdict", unit="verdict",
                         note="among v1 arms, on MONEY only lgbm_clf clears "
                              "the model null -- the v1 family's money "
                              "evidence is thinner than its IC evidence")

    subs: dict[str, dict] = {}
    if e["basis"] == "cited" and t["basis"] == "cited" and t["value"]:
        subs["stderr_from_paired_t"] = {
            "value": round(abs(e["value"] / t["value"]), 6),
            "unit": "annualised decimal", "basis": "derived",
            "note": "|E|/t from the two cited numbers above"}
    else:
        subs["stderr_from_paired_t"] = refused(
            "needs cited annualised_excess and nonzero paired t")
    # The v2 receipt carries NO 2022-24 sub-window. Zero would flatter;
    # borrow the revision sleeve's measured era dispersion as a conservative
    # prior and say so. v1 must compute the real one.
    rev_pooled = _extract(receipts, "revision_6m", f"arms.{REV_ARM}.excess_cagr")
    rev_adv = _extract(receipts, "revision_6m",
                       f"subwindow_2022_2024.{REV_ARM}.excess_cagr")
    if rev_pooled["basis"] == "cited" and rev_adv["basis"] == "cited":
        subs["era_dispersion"] = prior_only(
            abs(rev_pooled["value"] - rev_adv["value"]),
            "MISSING from the v2 receipt (no 2022-24 sub-window); borrowed "
            "from the revision sleeve's measured dispersion as a conservative "
            "prior. v1 must compute v2's own era split.")
    else:
        subs["era_dispersion"] = refused(
            "no 2022-24 sub-window in the v2 receipt AND the revision "
            "receipt's rows (the borrow source) are unreadable")

    gate = "DEPLOYABLE"
    if e["basis"] == "REFUSED" or cvar["basis"] == "REFUSED":
        gate = _refusal_gate(e, cvar)
    notes = [
        "frozen champion (review PART A Q3: ONE champion, one metric, "
        "forward shadow accrual only; no re-picking)",
        "historical t 2.64-2.87 earns a serious forward experiment, not "
        "production-alpha status",
    ]
    if pu is not None:
        ok, ref = _dig(pu, "header.whole_universe_refusals.learner_v2")
        if ok and isinstance(ref, dict):
            notes.append(
                f"today's PotentialUniverse REFUSES v2 on {ref.get('refused_on')}"
                f"/{ref.get('of')} names (day-file schema gap): this sleeve "
                "trades MONTHLY panel vintages, not the daily tracker file, "
                "and the refusal is the receipt that says why")
    return {
        "name": "learner_v2_monthly",
        "gate": gate,
        "components": {
            "e_excess": e,
            "e_excess_2022_2024": refused(
                "no 2022-24 sub-window in learner_v2_20260903.json; era "
                "dispersion borrowed as PRIOR_ONLY inside uncertainty"),
            "t_paired_pooled": t,
            "cvar": cvar,
            "cvar_05_monthly_information": cvar_m,
            "costs": (definition(
                0.0, "E is NET of 10bps/side on measured turnover already; "
                     "not charged twice.")
                if e["basis"] == "cited" else refused("E unreadable")),
            "uncertainty": _uncertainty_total(subs),
            "null_evidence": null_p,
            "v1_family_money_caveat": v1_caveat,
        },
        "notes": notes,
    }


def _sleeve_toxic_band_short(receipts: dict) -> dict:
    gross = _extract(receipts, "toxic_short",
                     "verdict_headline_1m.naive_short.gross_annualised_pct",
                     unit="pct/yr, GROSS",
                     note="gross of borrow; the honest headline is the "
                          "breakeven borrow rate, not this")
    brk = _extract(receipts, "toxic_short",
                   "verdict_headline_1m.naive_short.breakeven_borrow_pct_25bps",
                   unit="pct/yr borrow rate")
    borrow_note = _extract(receipts, "toxic_short", "conventions.borrow_note",
                           unit="text")
    return {
        "name": "toxic_band_short",
        "gate": "NOT_DEPLOYABLE_NO_BORROW_DATA",
        "components": {
            "e_excess": refused(
                "NO borrow-rate data exists in this repo (receipt's own "
                "words); net expectancy is a function of an unobserved rate "
                "-- hard-to-borrow small caps live at 20-100%+/yr, "
                "bracketing the ~27-28% breakeven. Not computable, not "
                "guessed."),
            "gross_information": gross,
            "breakeven_borrow_information": brk,
            "borrow_note": borrow_note,
            "cvar": refused("tail of a short book is unbounded above the "
                            "collateral convention; squeeze table in receipt "
                            "(worst name-month +476% in one month)"),
            "costs": refused("borrow IS the cost in question"),
            "uncertainty": refused("not computed for a gated sleeve"),
        },
        "notes": [
            "appears at weight 0 BY DESIGN: a gated sleeve that vanished "
            "from the table would be the invisible-ceiling shape",
            "gate lifts when a borrow-rate feed exists; either monetisable "
            "or already eaten by borrow -- either answer is a finding",
        ],
    }


def _sleeve_benchmark(receipts: dict) -> dict:
    cvar = _extract(receipts, "learner_v2",
                    "champions.1m.tradable_floor_variant.risk."
                    "max_drawdown_market_same_months",
                    unit="max drawdown, decimal",
                    note="VW market maxDD over the same 107 months the "
                         "champion was graded on")
    return {
        "name": "benchmark_SPY",
        "gate": "DEPLOYABLE",
        "components": {
            "e_excess": definition(0.0, "E[R_bench - R_bench] = 0 by definition"),
            "cvar": cvar,
            "costs": prior_only(
                0.0001, "one ETF trade ~1bp; no receipt measures it yet"),
            "uncertainty": definition(
                0.0, "the benchmark is its own reference; excess-vs-self has "
                     "no estimation error"),
        },
        "notes": ["the parking orbit: receives the residual row by default "
                  "(S36 stop-side rule -- proceeds park in SPY, never cash)"],
    }


def _sleeve_cash(receipts: dict) -> dict:
    mkt = _extract(receipts, "revision_6m", f"arms.{REV_ARM}.market_cagr",
                   note="trailing 2015-2024 VW market CAGR -- an ANCHOR, "
                        "not a forecast")
    if mkt["basis"] == "cited":
        e = prior_only(
            -mkt["value"],
            "cash's expected excess is MINUS the expected benchmark return. "
            "No forward nowcast exists; anchored to the trailing CAGR at "
            f"{mkt['source']} and therefore PRIOR_ONLY -- v1 must supply a "
            "real benchmark nowcast.")
    else:
        e = refused("no benchmark return anchor readable; cash's expected "
                    "excess is unknowable, not zero")
    return {
        "name": "cash",
        "gate": "DEPLOYABLE",
        "components": {
            "e_excess": e,
            "cvar": definition(0.0, "nominal cash does not draw down "
                                    "(inflation is outside v0's ledger)"),
            "costs": definition(0.0, "holding cash costs nothing to trade"),
            "uncertainty": definition(
                0.0, "the cash return is known; the uncertainty lives in the "
                     "benchmark leg and is already the E term's burden"),
        },
        "notes": ["cash must EARN its slot: a positive margin alone never "
                  "funds it -- an explicit bearish/deleveraging thesis is "
                  "required (see cash_policy)"],
    }


#: The v0 registry, in the order the artifact prints. Builders that need the
#: PotentialUniverse receive it; the rest take receipts only.
def build_sleeves(receipts: dict, pu: dict | None) -> list[dict]:
    return [
        _sleeve_revision_6m(receipts),
        _sleeve_learner_v2(receipts, pu),
        _sleeve_toxic_band_short(receipts),
        _sleeve_benchmark(receipts),
        _sleeve_cash(receipts),
    ]


# ---------------------------------------------------------------- objective

def utility_of(sleeve: dict, lam: dict[str, float]) -> float | None:
    """U_i = E - l1*|CVaR| - l2*Costs - l3*Uncertainty, or None when E or the
    CVaR proxy is a refusal (an unpriceable sleeve has no utility number --
    it has a gate)."""
    c = sleeve["components"]
    e = c.get("e_excess", {}).get("value")
    cv = c.get("cvar", {}).get("value")
    if e is None or c["e_excess"].get("basis") == "REFUSED":
        return None
    if cv is None or c["cvar"].get("basis") == "REFUSED":
        return None
    costs = c.get("costs", {}).get("value")
    unc = c.get("uncertainty", {}).get("value")
    if costs is None or unc is None:
        return None
    return (float(e) - lam["l1"] * abs(float(cv))
            - lam["l2"] * abs(float(costs)) - lam["l3"] * abs(float(unc)))


# --------------------------------------------------------------- allocation

def _allocate(sleeves: list[dict], personality: str,
              cash_thesis: str | None) -> tuple[list[dict], dict, dict]:
    """Weights + residual + cash policy. Deterministic and documented:

    1. U_i per sleeve; U_bench is the bar every sleeve must clear.
    2. Deployable sleeves with U_i > U_bench split the gross cap in
       proportion to their margin (U_i - U_bench), each clipped at the
       personality's max_sleeve_weight. benchmark and cash never compete
       here: benchmark is the residual's default destination, cash is
       thesis-gated.
    3. Residual = GROSS_CAP - sum(weights) -> benchmark, unless a cash
       thesis exists AND cash's own margin clears the bar.

    Every row leaves with `binding_constraint` filled -- the invisible-40%
    lesson: a weight without its binding reason is a lie of omission.
    """
    lam = PERSONALITIES[personality]
    by_name = {s["name"]: s for s in sleeves}
    bench = by_name["benchmark_SPY"]
    u_bench = utility_of(bench, lam)

    rows: list[dict] = []
    margins: dict[str, float] = {}
    for s in sleeves:
        u = utility_of(s, lam)
        margin = (None if (u is None or u_bench is None) else u - u_bench)
        rows.append({"sleeve": s["name"], "gate": s["gate"],
                     "u_components": s["components"],
                     "U": (round(u, 6) if u is not None else None),
                     "u_margin_vs_benchmark": (round(margin, 6)
                                               if margin is not None else None),
                     "weight": 0.0, "binding_constraint": None,
                     "notes": s["notes"]})
        if margin is not None:
            margins[s["name"]] = margin

    competing = [r for r in rows
                 if r["sleeve"] not in ("benchmark_SPY", "cash")]
    positive = [r for r in competing
                if r["gate"] == "DEPLOYABLE"
                and r["u_margin_vs_benchmark"] is not None
                and r["u_margin_vs_benchmark"] > 0]
    total_margin = sum(r["u_margin_vs_benchmark"] for r in positive)

    for r in competing:
        if r["gate"] != "DEPLOYABLE":
            r["binding_constraint"] = f"GATE:{r['gate']}"
        elif r["u_margin_vs_benchmark"] is None:
            r["binding_constraint"] = ("GATE:UNPRICEABLE -- a U term refused; "
                                       "see u_components")
        elif r["u_margin_vs_benchmark"] <= 0:
            r["binding_constraint"] = (
                "U_BELOW_BENCHMARK: does not beat the parking orbit under "
                f"{personality} lambdas (margin "
                f"{r['u_margin_vs_benchmark']:+.4f})")
        else:
            raw = GROSS_CAP * r["u_margin_vs_benchmark"] / total_margin
            if raw > lam["max_sleeve_weight"]:
                r["weight"] = round(lam["max_sleeve_weight"], 6)
                r["binding_constraint"] = (
                    f"MAX_SLEEVE_WEIGHT_{lam['max_sleeve_weight']:.2f} "
                    f"(uncapped share would be {raw:.4f})")
            else:
                r["weight"] = round(raw, 6)
                r["binding_constraint"] = (
                    "UNCONSTRAINED_BY_CAPS -- weight set by the margin-"
                    "proportional rule itself")

    allocated = sum(r["weight"] for r in rows)
    residual_w = round(GROSS_CAP - allocated, 6)

    cash_margin = margins.get("cash")
    cash_row = next(r for r in rows if r["sleeve"] == "cash")
    bench_row = next(r for r in rows if r["sleeve"] == "benchmark_SPY")
    cash_wins_numerically = cash_margin is not None and cash_margin > 0

    cash_policy = {
        "rule": "cash requires a thesis; the benchmark is the parking orbit. "
                "A positive cash margin WITHOUT a thesis is recorded, not "
                "funded (an allocator that drifts into cash by arithmetic is "
                "the itsang89 mirror).",
        "thesis_supplied": cash_thesis,
        "cash_margin_vs_benchmark": (round(cash_margin, 6)
                                     if cash_margin is not None else None),
        "cash_wins_numerically": cash_wins_numerically,
    }

    # The residual ROW carries the residual weight; the destination sleeve's
    # own row stays at its U-competition weight (0 for benchmark and cash,
    # which never compete). sum(allocation weights) + residual == GROSS_CAP.
    if cash_thesis and cash_wins_numerically:
        cash_row["binding_constraint"] = (
            "RESIDUAL_TO_CASH: explicit thesis supplied AND cash margin "
            f"{cash_margin:+.4f} clears the benchmark")
        bench_row["binding_constraint"] = (
            "PARKING_ORBIT_DISPLACED by the cash thesis this one artifact")
        destination, thesis = "cash", cash_thesis
        cash_policy["outcome"] = "residual routed to cash under the thesis"
    else:
        bench_row["binding_constraint"] = (
            "PARKING_ORBIT_DEFAULT: receives the residual because no sleeve "
            "claim (or thesis-backed cash claim) beat it")
        if cash_thesis and not cash_wins_numerically:
            cash_row["binding_constraint"] = (
                "THESIS_REFUSED: a thesis was supplied but cash does not "
                "beat the benchmark under these lambdas (margin "
                f"{cash_margin if cash_margin is not None else 'unpriceable'})"
                " -- the thesis is recorded, the parking orbit holds")
            cash_policy["outcome"] = "thesis recorded but refused by the numbers"
        else:
            cash_row["binding_constraint"] = (
                "NO_THESIS: cash requires a thesis and none was supplied"
                + (" (cash would have won numerically -- recorded, not funded)"
                   if cash_wins_numerically else ""))
            cash_policy["outcome"] = "no thesis; residual parks in the benchmark"
        destination, thesis = "benchmark_SPY", None

    residual = {
        "sleeve": "__residual__",
        "weight": residual_w,
        "destination": destination,
        "thesis": thesis,
        "rationale": ("every unused dollar gets a documented competing "
                      "allocation; this row IS that documentation. Residual "
                      f"= gross cap {GROSS_CAP:.2f} minus the "
                      f"{allocated:.4f} the sleeves claimed."),
    }
    return rows, residual, cash_policy


# ---------------------------------------------------- regret decomposition

def regret_decomposition_spec() -> dict:
    """The fields a nightly grader needs to split (book - benchmark) into
    named causes. The spec ships INSIDE every artifact so the grader and the
    allocator can never drift apart silently; TheCromazone lesson -- regret
    is an INPUT to the next decision, not a report."""
    return {
        "identity": "total_regret = realised_book_return - realised_benchmark_"
                    "return = selection_alpha + beta_gap + sizing + timing + "
                    "cash_drag + execution + risk_interventions + residual_"
                    "unexplained (grader must print residual_unexplained; a "
                    "decomposition that always sums exactly is fitting, not "
                    "measuring)",
        "inputs_required": {
            "artifact_weights": "this artifact's allocation + residual rows",
            "realised_sleeve_returns": "per sleeve, close-to-close, same day span",
            "realised_benchmark_return": "SPY close-to-close, named span",
            "actual_book_weights": "what the (future, non-shadow) book held",
            "sleeve_betas": "MISSING today -- no per-sleeve beta receipt "
                            "exists; v1 gap",
            "fill_records": "actual fills vs the marks used above",
            "intervention_log": "every stop/gate/cap that fired, with the "
                                "position and dollar delta",
        },
        "components": {
            "selection_alpha": "sum_i w_i * (r_i - beta_i * r_bench): did the "
                               "names chosen beat their market exposure",
            "beta_gap": "(sum_i w_i * beta_i - 1) * r_bench: exposure above/"
                        "below one benchmark unit",
            "sizing": "sum_i (w_actual_i - w_artifact_i) * r_i: the cost of "
                      "not holding the decided weights",
            "timing": "entry/exit price vs the close convention the artifact "
                      "was priced at",
            "cash_drag": "w_cash_actual * (r_bench - r_cash): the disease "
                         "this allocator exists to make visible",
            "execution": "fills vs marks (spread, partial fills, venue "
                         "refusals -- the opg 13/15 shape)",
            "risk_interventions": "dollar delta of stops/gates that fired vs "
                                  "the artifact's intent (S34: stops fired on "
                                  "BETA; this line is where that shows)",
        },
    }


# ------------------------------------------------------------------- build

def build_decision_artifact(day: str, personality: str, *,
                            pu: dict | None = None,
                            receipts: dict | None = None,
                            equity_usd: float = 100_000.0,
                            cash_thesis: str | None = None) -> dict:
    """One DecisionArtifact for (day, personality). Everything injectable so
    the tests run offline on synthetic fixtures; defaults read the real
    substrate. Places NOTHING either way."""
    if personality not in PERSONALITIES:
        raise ValueError(f"unknown personality {personality!r}; "
                         f"declared: {sorted(PERSONALITIES)}")
    receipts = receipts if receipts is not None else load_receipts()
    if pu is None:
        p = PU_DIR / f"{day}.jsonl"
        pu = read_potential_universe(p) if p.exists() else None

    sleeves = build_sleeves(receipts, pu)
    rows, residual, cash_policy = _allocate(sleeves, personality, cash_thesis)
    lam = PERSONALITIES[personality]

    # Worst case in dollars for the largest admissible book (session-start
    # protocol §4): sum of exposure x |maxDD proxy|, with the residual's
    # exposure attributed to its destination sleeve's tail.
    exposures = {r["sleeve"]: r["weight"] for r in rows}
    exposures[residual["destination"]] = round(
        exposures.get(residual["destination"], 0.0) + residual["weight"], 6)
    wc_terms, wc_unpriceable = [], []
    for r in rows:
        w = exposures[r["sleeve"]]
        if w <= 0:
            continue
        cv = r["u_components"].get("cvar", {}).get("value")
        if cv is None:
            wc_unpriceable.append(r["sleeve"])
        else:
            wc_terms.append((r["sleeve"], w, abs(float(cv))))
    wc_frac = sum(w * c for _, w, c in wc_terms)
    worst_case = {
        "equity_usd_assumed": equity_usd,
        "gross": round(sum(r["weight"] for r in rows) + residual["weight"], 6),
        "worst_case_fraction": round(wc_frac, 6),
        "worst_case_usd": round(-equity_usd * wc_frac, 2),
        "terms": [{"sleeve": s, "weight": w, "maxdd_proxy": c}
                  for s, w, c in wc_terms],
        "unpriceable": wc_unpriceable,
        "convention": "sum(weight x |maxDD proxy|); maxDD is a full-window "
                      "proxy, not a same-day bound -- printed anyway because "
                      "an unprinted worst case is how -9% became -24%",
    }

    artifact = {
        "artefact": "AEGIS_DECISION_ARTIFACT",
        "version": CODE_VERSION,
        "licence": LICENCE,
        "authority": AUTHORITY,
        "day": day,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "personality": personality,
        "lambdas": {**lam, "basis": LAMBDAS_BASIS,
                    "objective": "U_i = E[R_i - R_bench] - l1*CVaR_i - "
                                 "l2*Costs_i - l3*Uncertainty_i"},
        "universe": {
            **_universe_evidence(pu),
            "path": (str(PU_DIR / f"{day}.jsonl")
                     if pu is not None else None),
        },
        "allocations": rows,
        "residual": residual,
        "cash_policy": cash_policy,
        "binding_constraints": (
            [{"sleeve": r["sleeve"], "constraint": r["binding_constraint"]}
             for r in rows]
            + [{"sleeve": "__gross__",
                "constraint": f"GROSS_CAP_{GROSS_CAP:.2f} -- no leverage in "
                              "v0; the ladder is a later frozen contract"}]),
        "worst_case": worst_case,
        "regret_decomposition_spec": regret_decomposition_spec(),
        "missing_inputs_v1_must_replace": [
            "lambdas: declared priors, uncalibrated -- derive from the four "
            "declared utility functions and calibrate on farm replays",
            "cash e_excess: anchored to trailing 2015-24 VW CAGR; needs a "
            "real benchmark nowcast",
            "learner_v2 era_dispersion: no 2022-24 sub-window in its receipt; "
            "borrowed from revision_6m as PRIOR_ONLY",
            "benchmark costs: ~1bp PRIOR_ONLY, unmeasured",
            "toxic_band_short: gated entirely on absent borrow-rate data",
            "sleeve_betas: required by the regret spec, no receipt exists",
            "cvar: |maxDD| is a full-window proxy -- v1 wires states-based "
            "tail estimates (review Q7: sizing is the states' first consumer)",
            "sleeve dollar capacity: PU gives per-name max_usd, not yet "
            "aggregated per sleeve",
        ],
        "schema": {"artifact_keys": list(ARTIFACT_KEYS),
                   "row_keys": list(ALLOCATION_ROW_KEYS),
                   "schema_hash": schema_hash()},
    }
    return artifact


def write_decision_artifact(artifact: dict, out_dir: Path | None = None) -> Path:
    """<day>_<personality>.json -- one file per (day, personality) pair; the
    review's `<day>.json` shape is under-keyed once two personalities run."""
    out_dir = out_dir or OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{artifact['day']}_{artifact['personality']}.json"
    path.write_text(json.dumps(artifact, indent=1, default=str),
                    encoding="utf-8")
    return path


def format_table(artifact: dict) -> str:
    """One-screen allocation table for the run script and the handoff."""
    lines = [
        f"DECISION ARTIFACT  day={artifact['day']}  "
        f"personality={artifact['personality']}  ({artifact['licence']})",
        f"authority: {artifact['authority']}",
        f"{'sleeve':<22}{'gate':<38}{'E[exc]':>8}{'CVaR':>8}"
        f"{'Unc':>8}{'U':>9}{'margin':>9}{'weight':>8}",
        "-" * 110,
    ]
    for r in artifact["allocations"]:
        c = r["u_components"]

        def _v(name):
            v = c.get(name, {}).get("value")
            return f"{v:+.4f}" if v is not None else "  --  "
        u = f"{r['U']:+.4f}" if r["U"] is not None else "  --  "
        m = (f"{r['u_margin_vs_benchmark']:+.4f}"
             if r["u_margin_vs_benchmark"] is not None else "  --  ")
        gate = r["gate"] if len(r["gate"]) <= 36 else r["gate"][:33] + "..."
        lines.append(f"{r['sleeve']:<22}{gate:<38}{_v('e_excess'):>8}"
                     f"{_v('cvar'):>8}{_v('uncertainty'):>8}{u:>9}{m:>9}"
                     f"{r['weight']:>8.4f}")
    res = artifact["residual"]
    lines.append("-" * 110)
    lines.append(f"{'__residual__':<22}-> {res['destination']:<35}"
                 f"{'':>33}{res['weight']:>17.4f}")
    if res["thesis"]:
        lines.append(f"  residual thesis: {res['thesis']}")
    wc = artifact["worst_case"]
    lines.append(f"worst case (session protocol 4): {wc['worst_case_usd']:+,.2f} USD "
                 f"on {wc['equity_usd_assumed']:,.0f} equity "
                 f"(fraction {wc['worst_case_fraction']:.4f}, "
                 f"gross {wc['gross']:.2f})")
    for b in artifact["binding_constraints"]:
        lines.append(f"  BINDING  {b['sleeve']:<20} {b['constraint']}")
    return "\n".join(lines)


__all__ = [
    "CODE_VERSION", "LICENCE", "AUTHORITY", "RECEIPT_PATHS", "REV_ARM",
    "PERSONALITIES", "GROSS_CAP", "ARTIFACT_KEYS", "ALLOCATION_ROW_KEYS",
    "schema_hash", "cited", "definition", "prior_only", "refused",
    "load_receipts", "read_potential_universe", "latest_pu_day",
    "build_sleeves", "utility_of", "regret_decomposition_spec",
    "build_decision_artifact", "write_decision_artifact", "format_table",
    "OUT_DIR", "PU_DIR",
]
