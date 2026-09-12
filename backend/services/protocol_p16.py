"""P1-P6: the protocol an LLM-in-history receipt carries, or is not quoted.

MUST NOT REGRESS #24 (roadmap 2026-09-11 section 10): *"An LLM read over history
carries P1-P6, its LAP score and its anonymisation gap, or it is not quoted."*
That sentence was a declaration. This module is the enforcement: a schema, a
validator that names the missing field, and a refusal the leaderboard applies
before an X-lane row reaches the board.

The six come from "The Alpha Illusion" (arXiv:2605.16895), adopted verbatim in
`docs/research_notes/2026-09-12/spec_lane_x.md` section 6:

    P1 temporal integrity   anonymised? date-shifted placebo? time-locked model?
                            -- each a named field WITH the path to its evidence
    P2 dynamic universe     the P7 universe-vintage id, and delisting handling
    P3 direction-flip       flip the news sign, the forecast must flip: rate + n
    P4 calibration          the ECE, its bin count, the Brier and Murphy's split
    P5 full frictions       the cost-curve id and the REALISED bps, not a plan
    P6 disaggregation       which agent/prompt produced which field

WHY A CLAIM WITHOUT A PATH IS REFUSED
=====================================
`anonymised: true` with no artefact behind it is the same object as
`monday_gate_check`'s permanent `0/9 stamped [FAIL]`: a line a reader learns to
skim. So a P1 control that is claimed RUN must name the file that proves it ran,
and a control that was NOT run is `false` with a null path, which is honest and
passes. The refusal is for the third case -- claimed true, nothing behind it.

The same reasoning gives `LAP.applies: false` its `reason_if_not_applicable`:
PANEL-B is entirely post-cutoff for Qwen2.5-7B (spec section 1.3), so LAP genuinely
does not bind there -- but the receipt has to SAY that, because a silently
missing key and a reasoned exemption are not the same fact.

Used by `scripts/night_leaderboard_sync.py` (the board refuses an X-lane receipt
without a valid block) and by every X-lane job that writes one:
`scripts/night_l3_lookahead.py`, `scripts/night_x_anonymisation_gap.py`,
`scripts/night_x2_elasticity.py`, `scripts/night_x4_regime_route.py`.
"""

from __future__ import annotations

import re
from typing import Any

#: The six keys, in order. A receipt carrying five of them is refused naming the
#: sixth -- never "invalid P1_P6 block", which sends the reader back to the spec.
P_KEYS: tuple[str, ...] = (
    "P1_temporal_integrity",
    "P2_dynamic_universe",
    "P3_direction_flip",
    "P4_calibration_ece",
    "P5_full_frictions",
    "P6_disaggregation",
)

#: Required sub-fields per protocol item. Presence is the test, not truthiness:
#: `time_locked_control_run: false` is a legitimate state (ChronoGPT is an
#: OPTIONAL deliverable, spec section 1.6) and must not be forced to true by a schema.
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "P1_temporal_integrity": ("anonymised", "date_shifted_placebo_run",
                              "time_locked_control_run", "cutoff_stated",
                              "cutoff_source", "cutoff_confidence", "evidence_paths"),
    "P2_dynamic_universe": ("universe_vintage_id", "delisting_handled", "note"),
    "P3_direction_flip": ("pass_rate", "n", "test"),
    "P4_calibration_ece": ("ece", "n_bins", "brier", "brier_decomposition"),
    "P5_full_frictions": ("cost_curve_id", "cost_bps_per_side", "realised_bps",
                          "costed", "gross_reported_separately"),
    "P6_disaggregation": ("single_agent_baseline_run", "field_provenance"),
}

#: The three P1 controls whose `true` must be backed by a path in `evidence_paths`.
P1_EVIDENCED: tuple[str, ...] = ("anonymised", "date_shifted_placebo_run",
                                 "time_locked_control_run")

#: Murphy's three terms (`calibration.brier_decomposition` returns them).
BRIER_TERMS: tuple[str, ...] = ("reliability", "resolution", "uncertainty")

CUTOFF_CONFIDENCES: tuple[str, ...] = ("HIGH", "MEDIUM", "LOW")

LAP_VERDICTS: tuple[str, ...] = ("CONTAMINATED", "CLEAN",
                                 "INCONCLUSIVE_UNDERPOWERED", "AMBIGUOUS")

#: Job ids this protocol binds. `X` followed by a digit or an underscore, or
#: `L3`. Matched on the job id the leaderboard row is filed under, so a lane-X
#: job cannot escape the check by omitting the `lane` field.
X_JOB_RE = re.compile(r"^(X[0-9_]|L3[_$])")


def is_x_lane(job: str | None, payload: dict | None = None) -> bool:
    """Does the P1-P6 protocol bind this receipt?

    Two independent triggers, deliberately: the declared `lane` and the job id.
    A receipt that declares `lane: "X"` is bound whatever it is called, and a
    job called `X2_elasticity` is bound whether or not it remembered to declare.
    """
    payload = payload or {}
    lane = str(payload.get("lane") or "").strip().upper()
    if lane == "X":
        return True
    name = str(job or payload.get("job") or "")
    return bool(X_JOB_RE.match(name))


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate(payload: dict) -> list[str]:
    """Every reason this receipt's protocol block is not valid, in order.

    An empty list is a pass. Each reason NAMES the field, because the whole
    value of the check is that the reader is told what to add rather than that
    something somewhere is wrong.
    """
    reasons: list[str] = []
    if not isinstance(payload, dict):
        return [f"the receipt is a {type(payload).__name__}, not an object"]

    block = payload.get("P1_P6")
    if block is None:
        reasons.append("P1_P6: the block is missing entirely")
    elif not isinstance(block, dict):
        reasons.append(f"P1_P6: the block is a {type(block).__name__}, not an object")
    else:
        for key in P_KEYS:
            item = block.get(key)
            if item is None:
                reasons.append(f"P1_P6.{key}: missing")
                continue
            if not isinstance(item, dict):
                reasons.append(f"P1_P6.{key}: is a {type(item).__name__}, not an object")
                continue
            for field in REQUIRED_FIELDS[key]:
                if field not in item:
                    reasons.append(f"P1_P6.{key}.{field}: missing")
        reasons += _p1_detail(block.get("P1_temporal_integrity"))
        reasons += _p3_detail(block.get("P3_direction_flip"))
        reasons += _p4_detail(block.get("P4_calibration_ece"))
        reasons += _p5_detail(block.get("P5_full_frictions"))
        reasons += _p6_detail(block.get("P6_disaggregation"))

    reasons += _lap_detail(payload.get("LAP"))
    reasons += _gap_detail(payload.get("anonymisation_gap"))
    return reasons


def _p1_detail(p1: Any) -> list[str]:
    if not isinstance(p1, dict):
        return []
    out: list[str] = []
    ev = p1.get("evidence_paths")
    if "evidence_paths" in p1 and not isinstance(ev, dict):
        out.append("P1_P6.P1_temporal_integrity.evidence_paths: must be an object "
                   "mapping each control to the artefact that proves it ran")
        ev = {}
    ev = ev if isinstance(ev, dict) else {}
    for control in P1_EVIDENCED:
        if p1.get(control) is True and not str(ev.get(control) or "").strip():
            out.append(f"P1_P6.P1_temporal_integrity.evidence_paths.{control}: "
                       f"{control} is claimed true with no artefact path behind it "
                       "(a control claimed and not evidenced is the line a reader skims)")
    conf = p1.get("cutoff_confidence")
    if "cutoff_confidence" in p1 and conf not in CUTOFF_CONFIDENCES and conf is not None:
        out.append(f"P1_P6.P1_temporal_integrity.cutoff_confidence: {conf!r} is not one of "
                   f"{list(CUTOFF_CONFIDENCES)}")
    if p1.get("cutoff_stated") is True and not str(p1.get("cutoff_source") or "").strip():
        out.append("P1_P6.P1_temporal_integrity.cutoff_source: the cutoff is stated with "
                   "no source (a scraped system prompt is a source; nothing is not)")
    return out


def _p3_detail(p3: Any) -> list[str]:
    if not isinstance(p3, dict):
        return []
    out: list[str] = []
    rate, n = p3.get("pass_rate"), p3.get("n")
    if rate is not None:
        if not _is_num(rate) or not (0.0 <= float(rate) <= 1.0):
            out.append(f"P1_P6.P3_direction_flip.pass_rate: {rate!r} is not a rate in [0, 1]")
        if not _is_num(n) or int(n) <= 0:
            out.append("P1_P6.P3_direction_flip.n: a pass rate with n<=0 is a rate over "
                       "nothing; state n, or leave pass_rate null")
    elif "n" in p3 and n not in (0, None) and _is_num(n) and int(n) > 0:
        out.append("P1_P6.P3_direction_flip.pass_rate: n cells were tested and no rate "
                   "was reported")
    return out


def _p4_detail(p4: Any) -> list[str]:
    if not isinstance(p4, dict):
        return []
    out: list[str] = []
    if p4.get("ece") is not None:
        if not _is_num(p4.get("ece")):
            out.append(f"P1_P6.P4_calibration_ece.ece: {p4.get('ece')!r} is not a number")
        nb = p4.get("n_bins")
        if not _is_num(nb) or int(nb) < 1:
            out.append("P1_P6.P4_calibration_ece.n_bins: an ECE without its bin count is "
                       "not reproducible")
    dec = p4.get("brier_decomposition")
    if isinstance(dec, dict) and dec:
        missing = [t for t in BRIER_TERMS if t not in dec]
        if missing and dec.get("decomposition") != "insufficient_n":
            out.append("P1_P6.P4_calibration_ece.brier_decomposition: missing "
                       + ", ".join(missing))
    return out


def _p5_detail(p5: Any) -> list[str]:
    if not isinstance(p5, dict):
        return []
    out: list[str] = []
    if not str(p5.get("cost_curve_id") or "").strip():
        out.append("P1_P6.P5_full_frictions.cost_curve_id: name the cost curve; "
                   "'25 bps' without the curve it came from is a number without a receipt")
    if p5.get("costed") is True and not _is_num(p5.get("cost_bps_per_side")):
        out.append("P1_P6.P5_full_frictions.cost_bps_per_side: costed is true and the rate "
                   "is not a number (quote the cost rate or do not quote the count)")
    return out


def _p6_detail(p6: Any) -> list[str]:
    if not isinstance(p6, dict):
        return []
    prov = p6.get("field_provenance")
    if "field_provenance" in p6 and not isinstance(prov, dict):
        return ["P1_P6.P6_disaggregation.field_provenance: must be an object mapping each "
                "produced field to the agent/prompt that produced it"]
    if isinstance(prov, dict) and not prov:
        return ["P1_P6.P6_disaggregation.field_provenance: empty -- say which agent and "
                "which prompt produced which field, even when there is only one of each"]
    return []


def _lap_detail(lap: Any) -> list[str]:
    """`LAP` is required, and `applies: false` needs its reason.

    Spec section 6: *"silently omitting the key is refused, an explicit
    non-applicability is not."*
    """
    if lap is None:
        return ["LAP: missing -- a pre-cutoff LLM read carries its Lookahead Propensity, "
                "and a post-cutoff one says so explicitly (applies: false + reason)"]
    if not isinstance(lap, dict):
        return [f"LAP: is a {type(lap).__name__}, not an object"]
    out: list[str] = []
    if "applies" not in lap:
        out.append("LAP.applies: missing")
        return out
    if lap.get("applies") is False:
        if not str(lap.get("reason_if_not_applicable") or "").strip():
            out.append("LAP.reason_if_not_applicable: LAP is declared not to apply and no "
                       "reason is given; an exemption without a reason is an omission")
    else:
        if lap.get("score") is None and lap.get("study_verdict") is None:
            out.append("LAP.score: LAP applies and neither a per-cell score nor a study "
                       "verdict is present")
        v = lap.get("study_verdict")
        if v is not None and v not in LAP_VERDICTS:
            out.append(f"LAP.study_verdict: {v!r} is not one of {list(LAP_VERDICTS)}")
    return out


def _gap_detail(gap: Any) -> list[str]:
    if gap is None:
        return ["anonymisation_gap: missing -- a lane that reads free text measures it, and "
                "a lane that reads none states value_pct_pt: null with the reason"]
    if not isinstance(gap, dict):
        return [f"anonymisation_gap: is a {type(gap).__name__}, not an object"]
    out: list[str] = []
    if "value_pct_pt" not in gap:
        out.append("anonymisation_gap.value_pct_pt: missing")
        return out
    if gap.get("value_pct_pt") is None and not str(gap.get("reason") or "").strip():
        out.append("anonymisation_gap.reason: the gap is null and no reason is given "
                   "(e.g. 'no anonymised-text arm in this lane')")
    arm = gap.get("adopted_arm")
    if arm is not None and arm not in ("MASKED", "RAW", "CONDITIONAL_INSUFFICIENT_DATA"):
        out.append(f"anonymisation_gap.adopted_arm: {arm!r} is not MASKED, RAW or "
                   "CONDITIONAL_INSUFFICIENT_DATA")
    return out


def refuse_reasons(job: str | None, payload: dict) -> list[str]:
    """The reasons the leaderboard must refuse this row, or `[]`.

    A receipt that is not lane X is never refused here: this protocol binds LLM
    reads over history, not the whole factory.
    """
    if not is_x_lane(job, payload):
        return []
    return validate(payload)


def assert_valid(job: str | None, payload: dict) -> None:
    """Raise `ProtocolIncomplete` with every missing field named."""
    reasons = refuse_reasons(job, payload)
    if reasons:
        raise ProtocolIncomplete(
            f"{job or payload.get('job')}: X-lane receipt refused -- "
            + "; ".join(reasons))


class ProtocolIncomplete(ValueError):
    """An X-lane receipt that does not carry the protocol is not quoted."""


# ----------------------------------------------------------------- builders

def block(*, anonymised: bool, anonymised_evidence: str | None = None,
          placebo_run: bool = False, placebo_evidence: str | None = None,
          time_locked_run: bool = False, time_locked_evidence: str | None = None,
          time_locked_model: str | None = None,
          cutoff: str | None = None, cutoff_source: str | None = None,
          cutoff_confidence: str | None = None,
          universe_vintage_id: str | None = None, delisting_handled: bool = False,
          universe_note: str = "",
          flip_pass_rate: float | None = None, flip_n: int = 0,
          flip_test: str = "sign_flip counterfactual, spec_lane_x section 3.5",
          ece: float | None = None, n_bins: int = 10, brier: float | None = None,
          brier_decomposition: dict | None = None,
          cost_curve_id: str = "", cost_bps_per_side: float | None = None,
          realised_bps: float | None = None, costed: bool = True,
          gross_reported_separately: bool = True,
          single_agent_baseline_run: bool = False,
          field_provenance: dict | None = None,
          homogeneity_metric: float | None = None) -> dict:
    """Build a valid `P1_P6` block. One constructor, so six writers agree.

    Nothing here invents a value: every argument is passed in by the job that
    measured it, and a control that did not run stays `False` with a null path.
    """
    return {
        "P1_temporal_integrity": {
            "anonymised": bool(anonymised),
            "date_shifted_placebo_run": bool(placebo_run),
            "time_locked_control_run": bool(time_locked_run),
            "time_locked_control_model": time_locked_model,
            "cutoff_stated": cutoff is not None,
            "cutoff_date": cutoff,
            "cutoff_source": cutoff_source,
            "cutoff_confidence": cutoff_confidence,
            "evidence_paths": {
                "anonymised": anonymised_evidence,
                "date_shifted_placebo_run": placebo_evidence,
                "time_locked_control_run": time_locked_evidence,
            },
        },
        "P2_dynamic_universe": {
            "universe_vintage_id": universe_vintage_id,
            "delisting_handled": bool(delisting_handled),
            "note": universe_note,
        },
        "P3_direction_flip": {
            "pass_rate": flip_pass_rate, "n": int(flip_n), "test": flip_test,
        },
        "P4_calibration_ece": {
            "ece": ece, "n_bins": int(n_bins), "brier": brier,
            "brier_decomposition": brier_decomposition or {},
        },
        "P5_full_frictions": {
            "cost_curve_id": cost_curve_id,
            "cost_bps_per_side": cost_bps_per_side,
            "realised_bps": realised_bps,
            "costed": bool(costed),
            "gross_reported_separately": bool(gross_reported_separately),
        },
        "P6_disaggregation": {
            "single_agent_baseline_run": bool(single_agent_baseline_run),
            "field_provenance": field_provenance or {},
            "homogeneity_metric": homogeneity_metric,
        },
    }


def lap(applies: bool, *, score: float | None = None, verdict: str | None = None,
        reason: str | None = None) -> dict:
    """The `LAP` stanza. `applies=False` REQUIRES a reason and says so here."""
    return {"score": score, "study_verdict": verdict, "applies": bool(applies),
            "reason_if_not_applicable": None if applies else (reason or "")}


def anonymisation_gap(value_pct_pt: float | None = None, *, t: float | None = None,
                      adopted_arm: str | None = None, reason: str | None = None) -> dict:
    """The `anonymisation_gap` stanza. A null value carries its reason."""
    return {"value_pct_pt": value_pct_pt, "t": t, "adopted_arm": adopted_arm,
            "reason": reason}


def ece(probabilities, outcomes, n_bins: int = 10) -> dict:
    """Expected Calibration Error beside Murphy's split, from one place.

    `calibration.brier_decomposition` already bins forecasts and returns each
    bin's mean forecast and observed rate; ECE is the |difference| weighted by
    bin mass over exactly those bins, so computing it here rather than
    re-binning keeps P4's two numbers on the same partition. Spec section 0:
    this is *"the ECE/Brier utility X-lane receipts call, not something to
    reimplement."*
    """
    from backend.services.calibration import brier_decomposition

    dec = brier_decomposition(probabilities, outcomes, n_bins=n_bins)
    bins = dec.get("bins") or []
    n = int(dec.get("n") or 0)
    if not bins or n <= 0:
        return {"ece": None, "n_bins": int(n_bins), "brier": dec.get("brier"),
                "brier_decomposition": dec,
                "note": dec.get("reason") or "no bins: ECE is undefined on this sample"}
    total = 0.0
    for b in bins:
        k = float(b.get("n") or 0)
        p_hat = b.get("mean_forecast")
        o_hat = b.get("mean_outcome")
        if p_hat is None or o_hat is None or k <= 0:
            continue
        total += (k / n) * abs(float(p_hat) - float(o_hat))
    return {"ece": round(total, 6), "n_bins": len(bins), "brier": dec.get("brier"),
            "brier_decomposition": {k: dec.get(k) for k in BRIER_TERMS},
            "bins": bins}
