"""What a trade costs, and what a verdict is allowed to say when nobody knows.

    from backend.services import cost_model as CM
    cost = CM.cost_for_bars(o, h, l, c)          # OneWayBps or CostBand
    out  = CM.verdict_across_band(reprice, cost) # a verdict, or COST_MODEL_SENSITIVE

ORDER 18 §1 — THE RULING THIS MODULE IMPLEMENTS
================================================
Track R measured AGK's detection floor at ~23-49bp on a FRICTIONLESS tape. That
number is not a bug in the estimator; it is the estimator's resolution. But it
has a consequence the panel had not priced:

    a megacap's true one-way cost is 1-2bp, which is an order of magnitude
    BELOW the floor, so AGK cannot report it — and reading the floor value as
    the cost charges roughly ten times the truth.

That is the flat-10bp error mirrored. Flat 10bp UNDER-charges illiquid names;
raw AGK OVER-charges liquid ones. Both move verdicts for a property of the
instrument rather than a property of the market, and the panel has already had
two verdicts flip on exactly this kind of mistake.

The ruling is therefore segmented, and it is neither of the two obvious
options on their own:

    AGK RESOLVES (illiquid / small)   -> measure it. `MEASURED_AGK`.
    AGK CANNOT RESOLVE (liquid)       -> the estimate is ABSENT, not the floor.
                                         The segment gets a DECLARED band
                                         (1-5bp one-way), and a verdict that
                                         flips inside the band is reported
                                         `COST_MODEL_SENSITIVE` rather than
                                         resolved by picking an end.

THE STANDING RULE, AND WHY IT IS A TYPE HERE
---------------------------------------------
**An instrument's floor is part of the instrument. Below it, refusal — the
floor value is never the estimate.**

A band that a caller can quietly collapse to one number is not a band, so
`CostBand` has no `.value`, no `__float__`, and the function that would pick an
end of it (`resolve_band_by_picking`) exists ONLY as a named refusal. Its
absence would otherwise look like an oversight to the next person, who would
helpfully add it.

Likewise `COST_BPS_ONE_WAY` carries its convention in its NAME and in the
`OneWayBps` type, because Track R found the convention living in a comment while
every estimator returned the other quantity — the same shape as `PathStatistic`
refusing to rescale. A rate whose unit is a comment WILL be plugged in raw.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Sequence

from backend.services import spread_estimators as SE

logger = logging.getLogger(__name__)


class CostRefused(RuntimeError):
    """A cost was requested where the instrument cannot supply one.

    The missing input is USUALLY resolution rather than data: there are bars,
    there is an estimate, and the estimate is below the estimator's own noise
    floor. That failure returns a plausible number by default, which is what
    makes it worth an exception — an over-charged megacap looks exactly like a
    strategy that does not survive costs.
    """


# ── provenance: how a cost came to be, carried with the number ─────────────
#: AGK's estimate, above its own measured detection floor at this name's n and
#: volatility. A measurement.
MEASURED_AGK = "MEASURED_AGK"

#: An EFFECTIVE spread from TAQ — the trade-quote join, Holden-Jacobsen. Still
#: not reachable: the tables are entitled but the join has not been built, so
#: nothing may carry this label yet. It is kept distinct from the quoted
#: provenance below because the two are different quantities and a shared name
#: would erase the difference at the first call site that stores one.
MEASURED_TAQ = "MEASURED_TAQ"

#: A QUOTED NBBO spread from TAQ. Reachable as of 2026-08-18. Quoted is not
#: effective — see `taq_calibration.bias_ledger()` for the three biases and
#: their signs, two of which point DOWN, so this is an anchor and not a
#: conservative bound.
MEASURED_TAQ_QUOTED = "MEASURED_TAQ_QUOTED"

#: No instrument resolved this segment, so the cost is a DECLARED range chosen
#: to bracket the truth conservatively. Never a measurement, and it says so.
DECLARED_CONSERVATIVE = "DECLARED_CONSERVATIVE"

_PROVENANCES = (MEASURED_AGK, MEASURED_TAQ, MEASURED_TAQ_QUOTED,
                DECLARED_CONSERVATIVE)

#: The declared band for the segment AGK cannot resolve, in ONE-WAY basis
#: points. Declared before seeing which verdicts it permits, per the standing
#: rule about factors chosen after the fact. 1bp is roughly the quoted half
#: spread of a megacap in normal conditions; 5bp is deliberately pessimistic and
#: covers a stressed tape. A verdict that survives BOTH is a verdict.
LIQUID_BAND_ONE_WAY_BPS = (1.0, 5.0)

#: TAQ entitlement, CHECKED 2026-08-18 by SELECT probes rather than a catalogue
#: read: `taqm_2003`..`taqm_2026` + `taqmsec` are readable, per-day
#: `complete_nbbo_*` NBBO tables current through T-2. The check was on the
#: standing queue precisely because the WRDS record listed it as absent and the
#: record was wrong — the same shape as the port-filtering lesson, where the
#: route was declared dead for weeks and worked. It resolved the way the lesson
#: says these resolve.
#:
#: This value licenses NOTHING on its own. Entitlement is a fact about a
#: subscription; a retired band is a fact about a NAME. `taq_calibration`
#: retires it one name at a time, against a measurement.
TAQ_ENTITLEMENT = "VERIFIED_2026-08-18"

#: The verdict a repricing returns when the answer depends on where inside the
#: declared band the cost is assumed to sit.
COST_MODEL_SENSITIVE = "COST_MODEL_SENSITIVE"


@dataclass(frozen=True)
class OneWayBps:
    """Basis points charged per unit of notional crossed ONCE.

    The unit is in the type because Track R proved a comment does not hold it:
    `turn = sum(|dw|)` counts both legs, so the rate charged against it is the
    HALF spread, while all three estimators return the FULL spread. Anything
    that reaches Aegis's cost model goes through this class, and the halving
    happens in `SpreadEstimate.as_one_way_bps()` — one place, with a name.
    """

    value: float
    provenance: str
    basis: str = ""

    def __post_init__(self) -> None:
        if self.provenance not in _PROVENANCES:
            raise CostRefused(
                f"unknown cost provenance {self.provenance!r}; expected one of "
                f"{_PROVENANCES}. A cost without a provenance cannot be told "
                f"apart from a measurement, and the whole point of this ruling "
                f"is that some of these numbers are declared.")
        if not (self.value >= 0.0):
            raise CostRefused(
                f"a one-way cost of {self.value} is not a cost. A negative or "
                f"NaN rate pays the book to trade, which no downstream check "
                f"would flag as anything but a good result.")

    @property
    def measured(self) -> bool:
        return self.provenance in (MEASURED_AGK, MEASURED_TAQ,
                                   MEASURED_TAQ_QUOTED)


@dataclass(frozen=True)
class CostBand:
    """A declared range standing in for a cost nobody measured.

    Deliberately NOT a number. It has no `.value` and no `__float__`, so a
    caller cannot use it as one by accident — the only way through is
    `verdict_across_band`, which evaluates both ends and reports disagreement
    rather than resolving it.
    """

    low: OneWayBps
    high: OneWayBps
    reason: str

    def __post_init__(self) -> None:
        if self.low.value > self.high.value:
            raise CostRefused(
                f"band is inverted: low={self.low.value} > high="
                f"{self.high.value}")
        if self.low.provenance != self.high.provenance:
            raise CostRefused(
                "a band whose ends have different provenance is two different "
                "claims wearing one label")

    @property
    def provenance(self) -> str:
        return self.low.provenance

    def ends(self) -> tuple[OneWayBps, OneWayBps]:
        return (self.low, self.high)


def declared_liquid_band(reason: str = "") -> CostBand:
    """The Order 18 band for names AGK cannot resolve."""
    lo, hi = LIQUID_BAND_ONE_WAY_BPS
    basis = "ORDER_18_DECLARED_BAND"
    return CostBand(
        low=OneWayBps(lo, DECLARED_CONSERVATIVE, basis),
        high=OneWayBps(hi, DECLARED_CONSERVATIVE, basis),
        reason=reason or ("AGK cannot resolve this name's spread: the estimate "
                          "is at or below the estimator's own zero-spread "
                          "floor at this n and volatility"))


def cost_for_bars(open_: Sequence[float], high: Sequence[float],
                  low: Sequence[float], close: Sequence[float],
                  *, label: str = "") -> dict:
    """Segment a single name into the measured branch or the declared band.

    Returns a dict carrying EITHER `cost` (an `OneWayBps`) or `band` (a
    `CostBand`) — never both, and never a bare float. The floor diagnostic
    travels with it so a reader can see why the branch was taken rather than
    trusting the label.
    """
    diag = SE.estimate_with_floor(open_, high, low, close, estimator="agk")
    out = {"label": label, "floor_diagnostic": diag,
           "resolvable": diag["resolvable"]}
    if diag["resolvable"]:
        out["cost"] = OneWayBps(
            diag["one_way_bps"], MEASURED_AGK,
            basis=(f"AGK full spread {diag['full_spread_bps']}bps > floor "
                   f"{diag['floor']['floor_full_spread_bps']}bps at n="
                   f"{diag['floor']['n_obs']}"))
        out["branch"] = MEASURED_AGK
    else:
        out["band"] = declared_liquid_band(
            reason=(f"AGK read {diag['full_spread_bps']}bps against its own "
                    f"floor of {diag['floor']['floor_full_spread_bps']}bps — "
                    f"below the floor, so the estimate is absent, not small"))
        out["branch"] = DECLARED_CONSERVATIVE
    return out


def verdict_across_band(verdict_fn: Callable[[float], object],
                        cost: OneWayBps | CostBand) -> dict:
    """Evaluate a verdict at a measured cost, or at BOTH ends of a band.

    `verdict_fn` takes a one-way bps rate and returns whatever a verdict is in
    the caller's world — a string, a boolean, a survivor count. It is compared
    with `==`, so it must be comparable and must not be a fresh object each
    call. Anything that differs between the ends means the answer was never
    about the market.
    """
    if isinstance(cost, OneWayBps):
        return {"verdict": verdict_fn(cost.value),
                "cost_model_sensitive": False,
                "provenance": cost.provenance,
                "evaluated_at_bps": [cost.value]}
    if not isinstance(cost, CostBand):
        raise CostRefused(
            f"expected OneWayBps or CostBand, got {type(cost).__name__}. A raw "
            f"float here is the exact defect this ruling exists to stop: it "
            f"carries no provenance, so a declared number and a measured one "
            f"become indistinguishable one call downstream.")
    lo_v = verdict_fn(cost.low.value)
    hi_v = verdict_fn(cost.high.value)
    agree = bool(lo_v == hi_v)
    return {
        "verdict": lo_v if agree else COST_MODEL_SENSITIVE,
        "cost_model_sensitive": not agree,
        "provenance": cost.provenance,
        "evaluated_at_bps": [cost.low.value, cost.high.value],
        "verdict_at_low": lo_v,
        "verdict_at_high": hi_v,
        "reason": cost.reason,
    }


def resolve_band_by_picking(band: CostBand, end: str = "low"):
    """A NAMED REFUSAL. Kept so its absence cannot be read as an oversight.

    Picking an end of a declared band converts "we do not know what this costs"
    into a verdict, and it will always be tempting to pick the end that makes
    the result reportable. The function exists here, in the obvious place,
    refusing — so that the next person who looks for it finds the reason rather
    than the gap, and writes it at the call site instead.
    """
    raise CostRefused(
        f"refusing to collapse a {band.provenance} band to its {end} end. A "
        f"verdict that depends on which end you pick is COST_MODEL_SENSITIVE, "
        f"which is a REPORTABLE result — it says the data cannot answer the "
        f"question at this cost resolution. Report that instead. The band "
        f"retires when a resolving instrument arrives, not when someone needs "
        f"a number today.")


def calibrate_agk_against_taq(panel, agk_one_way_bps: dict[str, float]) -> dict:
    """The refusal that became a build, which is what a check that runs is for.

    This function spent Order 18 raising `CostRefused` on the ground that the
    entitlement check had not RUN — deliberately a different statement from "we
    do not have TAQ". The check ran on 2026-08-18 and returned entitled, so the
    refusal is discharged and the work happens in `taq_calibration`.

    Imported lazily because `taq_calibration` imports this module for its types;
    the dependency points one way at import time and the other at call time,
    which is the ordinary shape and not worth a third module to avoid.
    """
    from backend.services import taq_calibration as TC
    return TC.calibrate_against_agk(panel, agk_one_way_bps)


def summarise_segmentation(results: Sequence[dict]) -> dict:
    """Count the two branches, because the split IS the reportable fact.

    A repricing that says "we used AGK" while 60% of its names silently fell
    into the declared band has reported a measurement it did not make.
    """
    measured = [r for r in results if r.get("branch") == MEASURED_AGK]
    declared = [r for r in results if r.get("branch") == DECLARED_CONSERVATIVE]
    n = len(results)
    if n == 0:
        raise CostRefused("no names to summarise; an empty segmentation "
                          "reports 0% declared, which reads as full coverage")
    return {
        "n_names": n,
        "n_measured_agk": len(measured),
        "n_declared_band": len(declared),
        "fraction_declared": round(len(declared) / n, 4),
        "band_one_way_bps": list(LIQUID_BAND_ONE_WAY_BPS),
        "taq_entitlement": TAQ_ENTITLEMENT,
        "note": ("names in the declared band carry no measured cost; any "
                 "verdict over them must be reported across the band"),
    }
