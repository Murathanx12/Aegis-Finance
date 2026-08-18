"""INTERNET-INVESTIGATOR-FWD-1 — the grader and pairing harness.

    # what the campaign can detect, computed from forecasts alone. NO OUTCOMES.
    python -m scripts.iif1_grade --power

    # the whole pipeline end to end on synthetic outcomes
    python -m scripts.iif1_grade --synthetic

    # the real read. Refused unless the read gate licenses it.
    python -m scripts.iif1_grade --grade

WHY THIS EXISTS AND WHY IT IS P0
================================
585 records were minted on 2026-08-17. The first 195 resolve on 2026-08-21 and
the remaining 390 on 08-27, and until this file there was **no IIF-1 grader
module at all** — the attended `resolve_campaign_ledger.py` grades the ledger
into outcomes, and nothing turned graded outcomes into the campaign's paired
contrast. Grade-readiness precedes accrual-readiness: buying forty nights
against a statistic nobody has written down is buying receipts, not evidence.

TWO ACCESS MODES, ENFORCED STRUCTURALLY
=======================================
§64 says a power check that consumes no outcome is FREE and therefore
OBLIGATORY before any confirmation. That is only true if "consumes no outcome"
is a property of the code rather than of the analyst's intentions, so the loader
has two modes and the difference is what it is physically able to see:

  `MODE_POWER`  strips `outcome`, `brier`, `resolved_at` and `resolution_detail`
                from every record at load. The power path cannot read an outcome
                because it does not have one. No read licence required — the
                forecasts are already minted and frozen, and asking what they
                could detect is not a look at the answer.

  `MODE_GRADE`  keeps them, and is refused outright unless the read gate
                licenses a look at the derived graded-night count.

A comment saying "this function does not look at outcomes" is the honour system.
Deleting the field is not.

THE DERIVED GRADED-NIGHT COUNT
==============================
`iif1_read_gate.check_read` takes `n_graded_nights` as an INPUT — it is the last
outstanding entry on the canon's honour-system list, and it lives in the Aegis
module sibling where this session cannot change it. What this file can do, and
does, is never supply that number from anywhere but a count of receipts on disk.
The gate is still handed a value; the value is no longer a claim.

If the sibling holding the gate cannot be imported, the read is REFUSED rather
than falling back to a local copy of the schedule. A second implementation of a
read schedule is a second thing that can drift, and the whole point of the gate
is that there is exactly one.

EVERY BRIER PRINTS ITS BASE RATE
================================
Not by convention — `brier_with_base_rate` cannot return one without the other,
because they are the same dict. A rare event shrinks `p(1-p)` and a Brier
without its base rate is a number without its power: at a 4% base rate,
predicting 0.04 everywhere scores 0.038 and knows nothing. The Brier skill score
against a PIT climatology, and Murphy's reliability/resolution/uncertainty
decomposition, are computed for the same reason — resolution is the term that
says whether the forecaster distinguished anything at all.

THE UNIT IS THE NIGHT, NOT THE RECORD
=====================================
585 paired records is not n = 585. Cells within one night share a market, a
snapshot and a model call pattern; `n_effective` counts DATE BLOCKS, never rows.
So every statistic here reduces to one number per night first and then treats
nights as the sample. With one completed night the campaign's n is **1**, and
that is what the power section reports.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from backend.services import investigator_night as N

logger = logging.getLogger(__name__)

TRIAL = N.TRIAL

#: The registered loss target. Order 15 §2, and the Patton question is settled:
#: `abs_move_exceeds` is an EXACT binary target, not a noisy volatility proxy,
#: so Patton's proxy-robustness requirement does not bind and Brier is a proper
#: score on it directly.
FROZEN_LOSS_OBSERVABLE = "abs_move_exceeds"

#: The primary contrast, in the read gate's own direction: `B_tools -
#: A_snapshot`. Sign matters — a negative difference in Brier is B scoring
#: BETTER, and reporting it with the sign flipped is a way to be exactly wrong.
PRIMARY_TREATMENT = "B_tools"
PRIMARY_CONTROL = "A_snapshot"

#: The pairing key, per Order 13 §2. A cell missing from ANY arm is dropped from
#: EVERY arm — that is the matched design working, and it is also why a 0.5%
#: cell failure cost 2.5% of the contrast on Night 1.
PAIRING_FIELDS = ("night", "ticker", "observable", "horizon_days", "threshold")

MODE_POWER = "power"
MODE_GRADE = "grade"

#: What a night whose receipt carries no `implementation_version` is called.
#: A string rather than `None` so it survives a JSON round-trip as itself and
#: cannot be quietly compared equal to a real version by an `or` somewhere.
UNSTAMPED_VERSION = "UNSTAMPED"

#: Fields the power mode is not permitted to see. Removed at load.
OUTCOME_FIELDS = ("outcome", "brier", "resolved_at", "resolution_detail")

CAMPAIGN_POPULATION = "campaign_forward"


class GradeRefused(RuntimeError):
    """The grader was asked for a number it cannot honestly produce.

    Every use is a missing input rather than a bad one:

      * outcomes requested without a licensed read;
      * a Brier over an empty sample, or over one whose base rate is 0 or 1 —
        `p(1-p)` is zero, the MDE is undefined and a score computed anyway is a
        number about the sample's degeneracy, not the forecaster;
      * a forward MDE for a contrast whose arms never disagree, where no n
        makes the difference detectable;
      * a record that cannot be attributed to exactly one night.
    """


# ── loading, with the mode enforced by deletion ────────────────────────────
def load_records(path: Path | str, *, mode: str,
                 population: str | None = CAMPAIGN_POPULATION) -> list[dict]:
    """Read the ledger. In `MODE_POWER` the outcome fields do not survive.

    `population` filters to the campaign's own evidence pool. Pooling two
    populations is separately refused elsewhere in the codebase; here the point
    is narrower — a live-forward record has a different provenance and does not
    belong in this contrast at all.
    """
    if mode not in (MODE_POWER, MODE_GRADE):
        raise GradeRefused(f"unknown mode {mode!r}")
    p = Path(path)
    if not p.exists():
        raise GradeRefused(
            f"ledger {p} does not exist. An empty grade over a missing file "
            f"would report 'no records' identically to a genuinely empty "
            f"campaign, and those need opposite responses.")
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError as e:
            raise GradeRefused(
                f"ledger {p} has an unparseable line ({e}). A grader that "
                f"skips torn rows silently changes its own denominator.") from e
        if population is not None and r.get("evidence_population") != population:
            continue
        if mode == MODE_POWER:
            for f in OUTCOME_FIELDS:
                r.pop(f, None)
        out.append(r)
    return out


# ── night attribution: derived, and refuses when ambiguous ─────────────────
def night_intervals(receipts_dir: Path | None = None) -> list[dict]:
    """Each completed night's MEASURED wall-clock interval, from its receipt.

    Derived from `arm_started_at` / `arm_finished_at` on the per-arm rows rather
    than from the receipt's date field, because the join has to survive a
    post-close night that crosses midnight UTC. A date-string match would look
    right for every pre-open night and mis-file every post-close one, which is
    the sort of defect that is invisible until the schedule changes.
    """
    d = Path(receipts_dir or N.RECEIPTS_DIR)
    out: list[dict] = []
    if not d.exists():
        return out
    for p in sorted(d.glob("*.json")):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            logger.warning("night interval: receipt %s unreadable (%s)",
                           p.name, e)
            continue
        if r.get("sandbox"):
            continue
        starts, ends = [], []
        for blk in (r.get("per_arm") or {}).values():
            for row in (blk.get("rows") or []):
                if isinstance(row.get("arm_started_at"), (int, float)):
                    starts.append(float(row["arm_started_at"]))
                if isinstance(row.get("arm_finished_at"), (int, float)):
                    ends.append(float(row["arm_finished_at"]))
        if not starts or not ends:
            continue
        out.append({
            "night": str(r.get("night") or p.stem),
            "status": str(r.get("status")),
            "started_utc": datetime.fromtimestamp(min(starts), timezone.utc),
            "finished_utc": datetime.fromtimestamp(max(ends), timezone.utc),
            "implementation_version": r.get("implementation_version"),
            "arm_implementation_fingerprint": r.get(
                "arm_implementation_fingerprint"),
        })
    return out


def attach_night(records: Sequence[dict],
                 receipts_dir: Path | None = None) -> list[dict]:
    """Stamp each record with its night and `implementation_version`.

    The records carry neither. The version boundary is stamped on the RECEIPT
    (Night 1 is version 1; Night 2 onward is version 2 after the tool-call parse
    was hardened), and the campaign's analysis has to report the contrast within
    version as well as pooled — which is impossible if the records do not say
    which version produced them.

    A record matching zero nights or more than one is REFUSED, not assigned to
    the nearest. Mis-attributing a record across the version boundary is exactly
    the pooling error the boundary exists to prevent, and a nearest-match rule
    would do it silently.
    """
    intervals = night_intervals(receipts_dir)
    if not intervals:
        raise GradeRefused(
            "no night receipts with measured arm timestamps were found, so no "
            "record can be attributed to a night. Grading without that "
            "attribution would pool across the implementation_version boundary "
            "the receipts exist to mark.")
    # A minting instant lands exactly on the last arm's finish, so the window is
    # closed at both ends and widened by a small tolerance at the top.
    tol = 90.0
    out: list[dict] = []
    for r in records:
        try:
            made = datetime.fromisoformat(str(r["made_at"]))
        except (KeyError, ValueError) as e:
            raise GradeRefused(
                f"record {r.get('prediction_id')} has no usable `made_at` "
                f"({e}); it cannot be attributed to a night.") from e
        if made.tzinfo is None:
            made = made.replace(tzinfo=timezone.utc)
        hits = [iv for iv in intervals
                if iv["started_utc"] <= made
                and (made - iv["finished_utc"]).total_seconds() <= tol]
        if len(hits) != 1:
            raise GradeRefused(
                f"record {r.get('prediction_id')} made at {made.isoformat()} "
                f"matches {len(hits)} night interval(s). Exactly one is "
                f"required: zero means an orphan record, more than one means "
                f"overlapping nights, and assigning it to the nearest would "
                f"cross the implementation_version boundary without saying so.")
        iv = hits[0]
        rr = dict(r)
        rr["night"] = iv["night"]
        # UNSTAMPED, never coerced to 1. Night 1's receipt predates the line
        # that writes `implementation_version`, so the only completed night in
        # the campaign carries no version — a hole exactly at the boundary the
        # field exists to mark. Filling it with the version we *believe* Night 1
        # ran would turn an inference into a record, and the whole reason for a
        # declared version beside a derived fingerprint is that the two can
        # disagree. It is reported as its own bucket instead.
        rr["implementation_version"] = (
            iv["implementation_version"]
            if iv["implementation_version"] is not None else UNSTAMPED_VERSION)
        rr["arm_implementation_fingerprint"] = iv[
            "arm_implementation_fingerprint"]
        out.append(rr)
    return out


# ── pairing ────────────────────────────────────────────────────────────────
def _cell_key(r: dict) -> tuple:
    return tuple(r.get(f) for f in PAIRING_FIELDS)


def pair_cells(records: Sequence[dict], *,
               arms: Sequence[str] | None = None) -> dict:
    """Cells present in EVERY arm, plus the accounting for what was dropped.

    The drop accounting is not decoration. Night 1's single malformed tool call
    killed one cell in 200 and removed 2.5% of the contrast, because the cell
    goes from every arm — and that failure mode is only available to the
    tool-using arms, so it is a bias with a DIRECTION, toward the null, which is
    the direction that looks like a clean negative result. A contrast whose arms
    had different failure rates is reported with that term or it is not reported.
    """
    arms = tuple(arms or N.ARMS)
    by_arm: dict[str, dict[tuple, dict]] = {a: {} for a in arms}
    unknown_arms: set[str] = set()
    for r in records:
        a = r.get("arm")
        if a not in by_arm:
            unknown_arms.add(str(a))
            continue
        by_arm[a][_cell_key(r)] = r

    union: set[tuple] = set()
    for a in arms:
        union |= set(by_arm[a])
    paired = set.intersection(*(set(by_arm[a]) for a in arms)) if union else set()

    per_arm = {a: {"n_cells": len(by_arm[a]),
                   "n_dropped_for_pairing": len(set(by_arm[a]) - paired),
                   "n_missing_from_arm": len(union - set(by_arm[a]))}
               for a in arms}
    return {
        "arms": list(arms),
        "n_cells_union": len(union),
        "n_cells_paired": len(paired),
        "n_cells_dropped_unpaired": len(union - paired),
        "pairing_key": list(PAIRING_FIELDS),
        "per_arm": per_arm,
        "unknown_arms": sorted(unknown_arms),
        "cells": {a: {k: by_arm[a][k] for k in paired} for a in arms},
        "keys": sorted(paired),
    }


# ── Brier, and it cannot be produced without its base rate ─────────────────
def brier_with_base_rate(probabilities: Sequence[float],
                         outcomes: Sequence[int], *,
                         climatology: float | None = None,
                         label: str = "") -> dict:
    """Brier score, base rate, skill vs climatology, Murphy decomposition.

    ONE dict, because the parts are not separable in practice. A Brier reported
    alone invites the rare-event trap: at a 4% base rate, forecasting 0.04
    everywhere scores 0.038 and has learned nothing, and only the base rate
    beside it makes that visible.

      BSS  = 1 - BS / BS_climatology, with the reference computed from the
             HISTORICAL population for this exact observable x horizon x
             threshold — never from the outcomes being scored, which would
             be scoring a forecaster against its own answer key.
      Murphy: BS = reliability - resolution + uncertainty. Resolution is the
             term that says whether the forecaster separated high-risk cases
             from low-risk ones at all; a low Brier with near-zero resolution
             is the base rate wearing a model.
    """
    probs = [float(p) for p in probabilities]
    ys = [int(y) for y in outcomes]
    if len(probs) != len(ys):
        raise GradeRefused(
            f"{label or 'brier'}: {len(probs)} forecasts against {len(ys)} "
            f"outcomes. A score over a mismatched join is arithmetic against "
            f"the wrong world.")
    n = len(ys)
    if n == 0:
        raise GradeRefused(
            f"{label or 'brier'}: no scored records. An empty Brier is not 0.0.")
    base = sum(ys) / n
    if base in (0.0, 1.0):
        raise GradeRefused(
            f"{label or 'brier'}: base rate is {base:.3f} over n={n}. With "
            f"p(1-p) = 0 the uncertainty term vanishes, no skill score is "
            f"defined and the MDE is infinite — this is a fact about the "
            f"sample, and reporting a Brier from it would read as a fact about "
            f"the forecaster.")
    bs = sum((p - y) ** 2 for p, y in zip(probs, ys)) / n

    # Murphy (1973), on a binning of the forecasts. Ten bins unless the sample
    # is too small to fill them, in which case fewer — bins with one member make
    # resolution look perfect.
    n_bins = max(2, min(10, n // 5))
    bins: dict[int, list[int]] = {}
    for p, y in zip(probs, ys):
        b = min(n_bins - 1, int(p * n_bins))
        bins.setdefault(b, []).append(y)
    reliability = resolution = 0.0
    for b, members in bins.items():
        nk = len(members)
        obar_k = sum(members) / nk
        # The bin's representative forecast is its members' mean, not the bin
        # centre: a bin centre would attribute miscalibration to the binning.
        fk = sum(p for p, y in zip(probs, ys)
                 if min(n_bins - 1, int(p * n_bins)) == b) / nk
        reliability += nk * (fk - obar_k) ** 2
        resolution += nk * (obar_k - base) ** 2
    reliability /= n
    resolution /= n
    uncertainty = base * (1.0 - base)

    out = {
        "label": label,
        "n": n,
        "brier": round(bs, 6),
        "base_rate": round(base, 6),
        "uncertainty": round(uncertainty, 6),
        "reliability": round(reliability, 6),
        "resolution": round(resolution, 6),
        # NAMED, not swept up. Murphy's identity BS = REL - RES + UNC closes
        # exactly only when every forecast inside a bin is identical. With
        # continuous forecasts the binning leaves a residual, and calling it
        # "residual" without saying what it is invites someone to read a
        # binning artefact as a decomposition error. It is reported, and
        # `murphy_closes_exactly` says whether the identity actually held.
        "binning_residual": round(bs - (reliability - resolution + uncertainty), 9),
        "murphy_closes_exactly": abs(
            bs - (reliability - resolution + uncertainty)) < 1e-9,
        "n_bins": n_bins,
        "climatology": None,
        "brier_skill_score": None,
        "bss_reference": "NOT SUPPLIED — no skill claim is available",
    }
    if climatology is not None:
        c = float(climatology)
        if not 0.0 < c < 1.0:
            raise GradeRefused(
                f"{label or 'brier'}: climatology {c} is not a probability.")
        bs_clim = sum((c - y) ** 2 for y in ys) / n
        out["climatology"] = round(c, 6)
        out["brier_skill_score"] = round(1.0 - bs / bs_clim, 6) if bs_clim else None
        out["bss_reference"] = ("PIT climatology for this observable x horizon "
                                "x threshold, from the historical population")
    return out


# ── the paired contrast, with the NIGHT as the unit ────────────────────────
def paired_brier_contrast(paired: dict, *, treatment: str = PRIMARY_TREATMENT,
                          control: str = PRIMARY_CONTROL,
                          observable: str | None = FROZEN_LOSS_OBSERVABLE,
                          climatology: float | None = None) -> dict:
    """`treatment - control` in Brier, differenced within cell, averaged by night.

    Direction, stated: a NEGATIVE difference means the treatment arm scored a
    LOWER Brier, i.e. better. The read gate's terminal rule is written on
    `B_tools - A_snapshot`, and reporting this with the sign flipped is a way to
    be exactly wrong while every number looks reasonable.

    THE UNIT IS THE NIGHT. Cells within a night share a market, a snapshot and a
    model; treating 585 records as 585 independent observations would divide the
    SE by roughly 12 and manufacture significance out of clustering. Each night
    contributes one mean paired difference, and the sample is the nights.
    """
    keys = [k for k in paired["keys"]]
    if observable is not None:
        oi = PAIRING_FIELDS.index("observable")
        keys = [k for k in keys if k[oi] == observable]
    if not keys:
        raise GradeRefused(
            f"no paired cells for observable={observable!r}. The frozen loss is "
            f"Brier on {FROZEN_LOSS_OBSERVABLE!r}; a contrast computed over a "
            f"different observable is a different registration.")

    ni = PAIRING_FIELDS.index("night")
    by_night: dict[str, list[float]] = {}
    t_probs, c_probs, ys = [], [], []
    for k in keys:
        rt = paired["cells"][treatment][k]
        rc = paired["cells"][control][k]
        yt, yc = rt.get("outcome"), rc.get("outcome")
        if yt is None or yc is None:
            continue
        if int(yt) != int(yc):
            raise GradeRefused(
                f"cell {k} resolved to {yt} for {treatment} and {yc} for "
                f"{control}. The same cell has one outcome; two means the join "
                f"is wrong, and a paired difference over it is meaningless.")
        y = int(yt)
        pt, pc = float(rt["probability"]), float(rc["probability"])
        by_night.setdefault(k[ni], []).append((pt - y) ** 2 - (pc - y) ** 2)
        t_probs.append(pt)
        c_probs.append(pc)
        ys.append(y)

    if not by_night:
        raise GradeRefused(
            "no paired cell has an outcome on both arms. Nothing has resolved, "
            "so there is no contrast — which is a state, not a null result.")

    nights = sorted(by_night)
    per_night = [sum(by_night[n]) / len(by_night[n]) for n in nights]
    m = len(per_night)
    mean = sum(per_night) / m
    if m > 1:
        var = sum((x - mean) ** 2 for x in per_night) / (m - 1)
        se_iid = math.sqrt(var / m)
        se_hac = _newey_west_se(per_night)
    else:
        se_iid = se_hac = None

    se = (max(se_iid, se_hac) if se_iid is not None and se_hac is not None
          else None)
    return {
        "treatment": treatment,
        "control": control,
        "observable": observable,
        "direction": f"{treatment} - {control}; NEGATIVE means {treatment} "
                     f"scored a LOWER (better) Brier",
        "n_nights": m,
        "n_paired_cells": len(ys),
        "nights": nights,
        "per_night_mean_diff": [round(x, 6) for x in per_night],
        "mean_diff": round(mean, 6),
        "se_iid": round(se_iid, 6) if se_iid is not None else None,
        "se_hac": round(se_hac, 6) if se_hac is not None else None,
        "se_used": round(se, 6) if se is not None else None,
        "t_stat": (round(mean / se, 4) if se else None),
        "t_stat_note": ("None with fewer than two nights: a standard error over "
                        "one date block is not a small number, it is undefined. "
                        "n_effective counts DATE BLOCKS, never rows."),
        treatment: brier_with_base_rate(t_probs, ys, climatology=climatology,
                                        label=treatment),
        control: brier_with_base_rate(c_probs, ys, climatology=climatology,
                                      label=control),
    }


def _newey_west_se(x: Sequence[float]) -> float:
    """Newey-West SE of the mean with the usual n^(1/4) lag rule."""
    n = len(x)
    mean = sum(x) / n
    e = [v - mean for v in x]
    lag = max(0, int(math.floor(4 * (n / 100.0) ** 0.25)))
    lag = min(lag, n - 1)
    gamma0 = sum(v * v for v in e) / n
    s = gamma0
    for L in range(1, lag + 1):
        w = 1.0 - L / (lag + 1.0)
        gl = sum(e[i] * e[i - L] for i in range(L, n)) / n
        s += 2.0 * w * gl
    return math.sqrt(max(s, 0.0) / n)


# ── §64: forward power, computed from forecasts alone ──────────────────────
#: Normal quantiles, hardcoded rather than pulled from scipy: this is a power
#: check that must run in the offline fast suite, and a power gate that silently
#: skips when a dependency is missing is a gate that passes by not running.
_Z = {0.80: 0.8416, 0.90: 1.2816, 0.95: 1.6449, 0.975: 1.9600, 0.99: 2.3263}


def forward_mde_paired(*, deltas_by_night: dict[str, Sequence[float]],
                       base_rate: float, n_nights_target: int,
                       alpha: float = 0.05, power: float = 0.80,
                       outcome_correlation: float = 0.0) -> dict:
    """The smallest paired Brier difference the campaign could detect. NO OUTCOMES.

    This is §64 run forwards: a power check that consumes no outcome is free and
    therefore obligatory before any confirmation. Everything it needs already
    exists — the arms' forecast disagreement is in the ledger the night it was
    minted, and the base rate comes from history rather than from the answer key.

    THE ALGEBRA, so the assumption is visible instead of buried. For a cell with
    forecasts `f_t`, `f_c` and binary outcome `y`:

        d = (f_t - y)^2 - (f_c - y)^2 = (f_t - f_c)(f_t + f_c - 2y)

    With `y ~ Bernoulli(p)` and the forecasts fixed, `Var(d) = 4 d_f^2 p(1-p)`
    where `d_f = f_t - f_c`. So the per-night variance of the mean difference is
    `4 p(1-p) * mean(d_f^2) / m` over m cells, and

        MDE = (z_{1-alpha/2} + z_{power}) * SD_night / sqrt(n_nights)

    WHAT THIS ASSUMPTION COSTS, STATED. Cells within a night share a market, so
    their outcomes are NOT independent, and positive correlation INFLATES the
    real variance. The rho=0 figure is therefore an OPTIMISTIC FLOOR — the best
    case, not the estimate. `outcome_correlation` inflates it by the standard
    design effect `1 + (m-1)*rho`; it is DECLARED, and a declared value of 0 is
    reported under the label that says what it is rather than as a result.

    THE REFUSAL THAT MATTERS: if the arms never disagree, `d_f` is zero, the
    difference is identically zero whatever the world does, and NO n makes it
    detectable. That is a property of the treatment, not of the sample size, and
    it is the single most valuable thing this function can find out for free.
    """
    if not 0.0 < base_rate < 1.0:
        raise GradeRefused(
            f"base rate {base_rate} is not strictly between 0 and 1; p(1-p) is "
            f"zero and the MDE is infinite.")
    if n_nights_target < 1:
        raise GradeRefused("a forward MDE needs at least one night of target n")

    per_night_var, m_per_night, all_sq = [], [], []
    for _night, deltas in sorted(deltas_by_night.items()):
        ds = [float(d) for d in deltas]
        if not ds:
            continue
        m = len(ds)
        mean_sq = sum(d * d for d in ds) / m
        deff = 1.0 + (m - 1) * float(outcome_correlation)
        per_night_var.append(4.0 * base_rate * (1.0 - base_rate)
                             * mean_sq * deff / m)
        m_per_night.append(m)
        all_sq.extend(d * d for d in ds)

    if not per_night_var:
        raise GradeRefused("no forecast differences supplied; nothing to power")

    rms_delta = math.sqrt(sum(all_sq) / len(all_sq))
    if rms_delta == 0.0:
        raise GradeRefused(
            "the arms' forecasts are IDENTICAL on every paired cell, so the "
            "paired difference is exactly zero whatever the outcomes turn out "
            "to be. No n is sufficient — this is a fact about the treatment, "
            "not about the sample size, and it is detectable today for $0.")

    sd_night = math.sqrt(sum(per_night_var) / len(per_night_var))
    z_a = _Z[round(1.0 - alpha / 2.0, 3)] if round(1.0 - alpha / 2.0, 3) in _Z \
        else _Z[0.975]
    z_b = _Z.get(round(power, 2), _Z[0.80])
    mde = (z_a + z_b) * sd_night / math.sqrt(n_nights_target)

    return {
        "mde": round(mde, 6),
        "basis": ("OPTIMISTIC_FLOOR_INDEPENDENT_OUTCOMES"
                  if outcome_correlation == 0.0
                  else "DECLARED_INTRA_NIGHT_CORRELATION"),
        "outcome_correlation": outcome_correlation,
        "outcome_correlation_note": (
            "rho=0 assumes cells within a night resolve independently. They do "
            "not — they share a market. The reported MDE is therefore a FLOOR: "
            "the true detectable difference is larger."
            if outcome_correlation == 0.0 else
            "declared, not measured; measure it once outcomes exist"),
        "base_rate": base_rate,
        "n_nights_target": n_nights_target,
        "n_nights_observed": len(per_night_var),
        "cells_per_night": m_per_night,
        "rms_forecast_difference": round(rms_delta, 6),
        "sd_per_night": round(sd_night, 6),
        "alpha": alpha,
        "power": power,
        "consumed_outcomes": False,
    }


def cell_types(paired: dict) -> list[tuple]:
    """The distinct `(observable, horizon_days, threshold)` triples present.

    These are DIFFERENT REGISTERED CELLS, not one pooled quantity. Night 1
    forecast `abs_move_exceeds` at thresholds 0.05 and 0.03, whose measured
    climatological base rates are 0.196 and 0.402 — a factor of two apart. One
    MDE computed over both with a single `p` would be correct arithmetic
    against the wrong world, which is this project's signature failure. So the
    power is reported per cell type and never pooled across thresholds.
    """
    oi = PAIRING_FIELDS.index("observable")
    hi = PAIRING_FIELDS.index("horizon_days")
    ti = PAIRING_FIELDS.index("threshold")
    return sorted({(k[oi], k[hi], k[ti]) for k in paired["keys"]},
                  key=lambda x: (str(x[0]), str(x[1]), str(x[2])))


def forecast_deltas_by_night(paired: dict, *, treatment: str = PRIMARY_TREATMENT,
                             control: str = PRIMARY_CONTROL,
                             observable: str | None = FROZEN_LOSS_OBSERVABLE,
                             horizon_days: int | None = None,
                             threshold: float | None = None,
                             ) -> dict[str, list[float]]:
    """`f_treatment - f_control` per cell, grouped by night. Reads no outcome."""
    keys = list(paired["keys"])
    oi = PAIRING_FIELDS.index("observable")
    hi = PAIRING_FIELDS.index("horizon_days")
    ti = PAIRING_FIELDS.index("threshold")
    if observable is not None:
        keys = [k for k in keys if k[oi] == observable]
    if horizon_days is not None:
        keys = [k for k in keys if k[hi] == horizon_days]
    if threshold is not None:
        keys = [k for k in keys if k[ti] == threshold]
    ni = PAIRING_FIELDS.index("night")
    out: dict[str, list[float]] = {}
    for k in keys:
        pt = float(paired["cells"][treatment][k]["probability"])
        pc = float(paired["cells"][control][k]["probability"])
        out.setdefault(str(k[ni]), []).append(pt - pc)
    if not out:
        raise GradeRefused(
            f"no paired cells for observable={observable!r} "
            f"horizon={horizon_days!r} threshold={threshold!r} to difference")
    return out


# ── the read gate, handed a DERIVED count ──────────────────────────────────
def derive_n_graded_nights(receipts_dir: Path | None = None) -> int:
    """Counted from receipts on disk. Never accepted from a caller.

    `check_read` takes this as an input and is the last outstanding item on the
    canon's honour-system list. The signature lives in the Aegis module sibling
    and cannot be changed from here — but nothing in THIS repo may supply that
    number from anywhere except a count, so the gate is still handed a value and
    the value is no longer a claim.
    """
    d = Path(receipts_dir or N.RECEIPTS_DIR)
    if not d.exists():
        return 0
    n = 0
    for p in sorted(d.glob("*.json")):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not r.get("sandbox") and str(r.get("status")) == "ok":
            n += 1
    return n


def load_read_gate(module_root: Path | None = None):
    """Import the gate out of the `Aegis module` sibling.

    TWO REPOS BOTH HAVE A TOP-LEVEL `scripts` PACKAGE, and the gate's own
    `from scripts import iif1_config` resolves against whichever one reached
    `sys.modules` first. Importing this from a process that has already touched
    aegis-finance's `scripts` therefore fails with a message about the wrong
    repository entirely — which is how the first run of this function reported
    GATE_UNREADABLE while the gate loaded perfectly in isolation.

    So the name is vacated for the duration of the import and restored
    afterwards. Surgical rather than clever: the alternative is a second copy of
    the read schedule living in this repo, and a schedule with two
    implementations has two things that can drift.
    """
    import importlib
    import sys as _sys

    root = Path(module_root or (Path(N._config.PROJECT_ROOT).parent
                                / "Aegis module"))
    gate = root / "scripts" / "iif1_read_gate.py"
    if not gate.exists():
        raise ImportError(f"no read gate at {gate}")

    saved = {k: v for k, v in _sys.modules.items()
             if k == "scripts" or k.startswith("scripts.")}
    saved_path = list(_sys.path)
    for k in saved:
        del _sys.modules[k]
    try:
        _sys.path.insert(0, str(root))
        return importlib.import_module("scripts.iif1_read_gate")
    finally:
        _sys.path[:] = saved_path
        for k in [k for k in list(_sys.modules)
                  if k == "scripts" or k.startswith("scripts.")]:
            del _sys.modules[k]
        _sys.modules.update(saved)


def check_read_licence(receipts_dir: Path | None = None,
                       module_root: Path | None = None) -> dict:
    """Ask the gate. Reports; does not enforce. Asking is not a read."""
    n = derive_n_graded_nights(receipts_dir)
    try:
        gate = load_read_gate(module_root)
    except Exception as e:                                    # noqa: BLE001
        return {"licensed": False, "n_graded_nights": n,
                "disposition": "GATE_UNREADABLE",
                "reason": (f"the read gate could not be loaded ({e}). The read "
                           f"is refused rather than falling back to a local "
                           f"copy of the schedule: a second implementation is "
                           f"a second thing that can drift, and there is "
                           f"supposed to be exactly one.")}
    d = gate.check_read(n)
    out = d.as_dict() if hasattr(d, "as_dict") else dict(d)
    out["n_graded_nights_basis"] = "COUNTED_FROM_RECEIPTS"
    return out


def assert_read_licensed(receipts_dir: Path | None = None) -> dict:
    lic = check_read_licence(receipts_dir)  # noqa: F841 — reported below
    if not lic.get("licensed"):
        raise GradeRefused(
            f"[{lic.get('disposition')}] {lic.get('reason')} "
            f"(n_graded_nights={lic.get('n_graded_nights')}, derived by "
            f"counting receipts). The campaign_forward outcomes stay unread.")
    return lic


# ── climatology, from data rather than from an assertion ───────────────────
def climatological_base_rate(returns_by_ticker: dict[str, Sequence[float]], *,
                             horizon_days: int, threshold: float) -> dict:
    """P(|cumulative return over `horizon_days`| > `threshold`), from history.

    Takes a RETURNS PANEL, not a number. A function that accepted a base rate
    would be accepting an assertion, and the whole reason the Brier skill score
    needs a climatology is that the alternative — scoring against the sample's
    own outcomes — grades a forecaster against its own answer key.

    Refuses an empty panel rather than returning 0.0.
    """
    if horizon_days < 1:
        raise GradeRefused("horizon_days must be at least 1")
    hits = total = 0
    for _t, series in returns_by_ticker.items():
        r = [float(x) for x in series]
        for i in range(len(r) - horizon_days + 1):
            cum = 1.0
            for x in r[i:i + horizon_days]:
                cum *= (1.0 + x)
            total += 1
            if abs(cum - 1.0) > float(threshold):
                hits += 1
    if total == 0:
        raise GradeRefused(
            f"the returns panel yields no {horizon_days}-day windows, so no "
            f"climatology can be computed. An empty panel is not a base rate "
            f"of zero — and a zero would make every skill score infinite.")
    return {"base_rate": hits / total, "n_windows": total, "n_hits": hits,
            "horizon_days": horizon_days, "threshold": threshold,
            "basis": "MEASURED_FROM_SUPPLIED_RETURNS_PANEL"}


def measure_intra_night_correlation(returns_by_ticker: dict[str, Sequence[float]],
                                    *, horizon_days: int, threshold: float
                                    ) -> dict:
    """Intraclass correlation of exceedance ACROSS NAMES WITHIN A DAY.

    THIS IS THE NUMBER THAT DOMINATES THE CAMPAIGN'S POWER, and it was a
    declared assumption until it was measured. On Night 1's universe the
    forward MDE at 40 nights roughly TRIPLES between rho = 0 and rho = 0.3, so
    "how correlated are 39 names' exceedances on one date" matters more to what
    IIF-1 can detect than anything about the arms.

    The canon's rule is that the dependence unit is measurable, not assumable,
    and that a declared value must be conservative. So this measures it, and
    the caller may still declare a larger one — never a smaller.

    THE ESTIMATOR, so the assumption is visible. If `m` names on one date each
    exceed with probability `p` and share an intraclass correlation `rho`, the
    variance of the daily COUNT is `m*p*(1-p)*(1 + (m-1)*rho)`. Inverting:

        rho_hat = (Var(count) / (m*p*(1-p)) - 1) / (m - 1)

    which is exactly the design effect the forward MDE applies, so the measured
    number and the number it feeds are the same quantity rather than two
    plausible cousins.

    Negative estimates are reported as measured and floored at 0 for USE: a
    negative intraclass correlation would make the MDE smaller, and a
    measurement is only allowed to make this guard more conservative.
    """
    if horizon_days < 1:
        raise GradeRefused("horizon_days must be at least 1")
    names = [t for t, s in returns_by_ticker.items()
             if len(list(s)) >= horizon_days]
    if len(names) < 2:
        raise GradeRefused(
            f"intra-night correlation needs at least two names; got "
            f"{len(names)}. With one name there is no cross-section to "
            f"correlate, and returning 0 would read as 'measured, and they are "
            f"independent'.")
    series = {t: [float(x) for x in returns_by_ticker[t]] for t in names}
    n_obs = min(len(series[t]) for t in names) - horizon_days + 1
    if n_obs < 2:
        raise GradeRefused(
            f"only {n_obs} common {horizon_days}-day window(s); a variance "
            f"over one date is undefined, not zero.")

    counts, hits, total = [], 0, 0
    for i in range(n_obs):
        c = 0
        for t in names:
            cum = 1.0
            for x in series[t][i:i + horizon_days]:
                cum *= (1.0 + x)
            if abs(cum - 1.0) > float(threshold):
                c += 1
        counts.append(c)
        hits += c
        total += len(names)
    p = hits / total
    if p in (0.0, 1.0):
        raise GradeRefused(
            f"exceedance rate is {p}; p(1-p) is zero and the intraclass "
            f"correlation is undefined.")
    m = len(names)
    mean_c = sum(counts) / len(counts)
    var_c = sum((c - mean_c) ** 2 for c in counts) / (len(counts) - 1)
    rho_hat = (var_c / (m * p * (1.0 - p)) - 1.0) / (m - 1)
    # Clamped to [0, 1] FOR USE, and the raw estimate kept beside it. Both ends
    # are real: `p` is estimated from the same data, so the point estimate can
    # land a little above 1 on a perfectly coupled panel (measured 1.0037 on
    # the synthetic check), and an intraclass correlation above 1 would imply a
    # design effect larger than the number of names. The floor at 0 is the
    # asymmetric half — a measurement may only make this guard more
    # conservative, never less.
    rho_use = min(1.0, max(0.0, rho_hat))
    return {
        "rho_measured": round(rho_hat, 6),
        "rho_for_use": round(rho_use, 6),
        "basis": "MEASURED_INTRACLASS_FROM_DAILY_EXCEEDANCE_COUNTS",
        "floored_at_zero": rho_hat < 0.0,
        "capped_at_one": rho_hat > 1.0,
        "n_names": m,
        "n_dates": len(counts),
        "exceedance_rate": round(p, 6),
        "design_effect_at_m": round(1.0 + (m - 1) * rho_use, 4),
        "horizon_days": horizon_days,
        "threshold": threshold,
        "note": ("a caller may DECLARE a larger rho; it may never declare a "
                 "smaller one, because a measurement is only allowed to make "
                 "this guard more conservative"),
    }


# ── the whole thing ────────────────────────────────────────────────────────
def power_report(*, ledger: Path | str, receipts_dir: Path | None = None,
                 base_rates: dict[tuple, float],
                 n_nights_target: int | None = None,
                 alpha: float = 0.05, power: float = 0.80,
                 outcome_correlation: float = 0.0,
                 observable: str | None = FROZEN_LOSS_OBSERVABLE) -> dict:
    """§64 forwards, PER REGISTERED CELL. Loads in POWER mode: no outcomes.

    `base_rates` maps `(observable, horizon_days, threshold)` to a MEASURED
    climatology. A cell present in the ledger with no base rate supplied is
    REFUSED rather than defaulted — a default here would be an assertion about
    how often the world moves, silently deciding the power of the trial.
    """
    recs = attach_night(load_records(ledger, mode=MODE_POWER), receipts_dir)
    paired = pair_cells(recs)
    target = int(n_nights_target or N.GRADED_NIGHTS_TO_FIRST_LOOK)

    types = [t for t in cell_types(paired)
             if observable is None or t[0] == observable]
    if not types:
        raise GradeRefused(
            f"no paired cells for observable={observable!r}")
    missing = [t for t in types if t not in base_rates]
    if missing:
        raise GradeRefused(
            f"no measured base rate supplied for cell type(s) {missing}. A "
            f"default would be an assertion about how often the world moves, "
            f"and it would silently set the power of the trial. Measure it "
            f"with `climatological_base_rate` on a returns panel.")

    per_cell = {}
    for t in types:
        deltas = forecast_deltas_by_night(
            paired, observable=t[0], horizon_days=t[1], threshold=t[2])
        per_cell[f"{t[0]}|h{t[1]}|thr{t[2]}"] = forward_mde_paired(
            deltas_by_night=deltas, base_rate=float(base_rates[t]),
            n_nights_target=target, alpha=alpha, power=power,
            outcome_correlation=outcome_correlation)

    by_version: dict[str, int] = {}
    for r in recs:
        by_version[str(r.get("implementation_version"))] = \
            by_version.get(str(r.get("implementation_version")), 0) + 1
    return {
        "trial": TRIAL,
        "mode": MODE_POWER,
        "read_licence_not_required": (
            "a power check consumes no outcome, so it is free and therefore "
            "obligatory before any confirmation (§64). The loader physically "
            "removed the outcome fields."),
        "pairing": {k: v for k, v in paired.items() if k not in ("cells", "keys")},
        "cell_types": [list(t) for t in types],
        "records_by_implementation_version": by_version,
        "forward_mde_by_cell": per_cell,
        "read_licence": check_read_licence(receipts_dir),
    }


def grade_report(*, ledger: Path | str, receipts_dir: Path | None = None,
                 climatology: float | None = None,
                 require_licence: bool = True) -> dict:
    """The real read. Refused unless the gate licenses a look.

    `require_licence=False` exists for SYNTHETIC outcomes only, and the caller
    that passes it has to have built the records itself — the campaign ledger
    path plus `require_licence=False` is refused, because the one thing this
    harness must never do is grade the real thing early by way of a test flag.
    """
    if require_licence:
        licence = assert_read_licensed(receipts_dir)
    else:
        licence = {"licensed": False, "disposition": "SYNTHETIC_ONLY",
                   "reason": "outcomes were supplied by the caller"}
    recs = attach_night(load_records(ledger, mode=MODE_GRADE), receipts_dir)
    return _grade_records(recs, climatology=climatology, licence=licence)


def _grade_records(recs: Sequence[dict], *, climatology: float | None,
                   licence: dict) -> dict:
    paired_all = pair_cells(recs)
    out: dict[str, Any] = {
        "trial": TRIAL,
        "mode": MODE_GRADE,
        "read_licence": licence,
        "frozen_loss": f"Brier on {FROZEN_LOSS_OBSERVABLE}",
        "pairing": {k: v for k, v in paired_all.items()
                    if k not in ("cells", "keys")},
        "pooled": paired_brier_contrast(paired_all, climatology=climatology),
        "by_implementation_version": {},
    }
    # WITHIN VERSION AS WELL AS POOLED. The tool-call hardening between Night 1
    # and Night 2 made B a better arm AND a different arm; a contrast pooled
    # across that boundary silently mixes two versions of the treatment.
    versions = sorted({str(r.get("implementation_version")) for r in recs})
    for v in versions:
        sub = [r for r in recs if str(r.get("implementation_version")) == v]
        try:
            p = pair_cells(sub)
            out["by_implementation_version"][v] = paired_brier_contrast(
                p, climatology=climatology)
        except GradeRefused as e:
            # A version with nothing resolved is a STATE, and it is reported as
            # one. Dropping it would make the pooled figure look like the whole
            # story.
            out["by_implementation_version"][v] = {
                "refused": str(e), "n_records": len(sub)}
    return out


def grade_synthetic(records: Sequence[dict], *,
                    climatology: float | None = None) -> dict:
    """Grade records the caller built. The end-to-end path, with no real outcome.

    This is what makes the harness testable before 2026-08-21: everything from
    pairing through the Murphy decomposition runs, and the only thing that never
    happens is a look at the campaign.
    """
    for r in records:
        if r.get("evidence_population") == CAMPAIGN_POPULATION:
            raise GradeRefused(
                "a record in the synthetic path declares "
                f"evidence_population={CAMPAIGN_POPULATION!r}. Synthetic "
                "grading is the one path with no read licence, so letting a "
                "real record through it would be an unlicensed read wearing a "
                "test flag.")
    return _grade_records(list(records), climatology=climatology,
                          licence={"licensed": False,
                                   "disposition": "SYNTHETIC_ONLY",
                                   "reason": "outcomes supplied by the caller"})
