"""What we actually know about a name, and how much of it to believe.

BUILD-1.1. Two bugs in PM v1 shared one root cause: the engine could not
distinguish *absent* evidence from *unfavourable* evidence.

  * A name with a live price but no consensus target got `available: True`, a
    target weight of zero, and therefore a SELL. A feed outage read as a
    negative view.
  * A name that no analyst had touched in years got `freshness = 1.0` — the
    maximum — because `days_since_last_action` was `None`. Unknown was scored
    as perfect.

This module fixes both by making the state of the evidence a first-class
object rather than an implicit consequence of a missing dict key.

Two outputs, deliberately separate:

**Completeness** — which facts do we possess? Purely descriptive, no view.

**Reliability** — a bounded multiplier applied to the expected return before
it reaches a position size. It is a DISCOUNT and only a discount: it lives in
`[RELIABILITY_FLOOR, 1.0]` and can never inflate a signal. This is how the
analyst evidence finally reaches sizing — v1 computed breadth, freshness and
coverage, used them to rank, and then sized on a number that ignored them all.

It is `calibrated: False` and will stay that way until the journal has enough
resolved decisions to fit it. An uncalibrated discount is still better than an
implicit one of 1.0, which is what the code was doing before.
"""
from __future__ import annotations

import math
from typing import Any, Optional

#: Reliability never falls below this — a floor keeps a thin-evidence name
#: small rather than making it vanish, which would be a disguised SELL.
RELIABILITY_FLOOR = 0.35
#: Analyst coverage this old is still usable, but is marked `stale` and is
#: discounted hard. It is NOT treated as missing: the target still exists.
STALE_COVERAGE_DAYS = 365
#: What an unknown value scores on a 0-1 axis. NOT 1.0. That is the whole
#: point of this module.
UNKNOWN = 0.5

#: The facts a decision would like to have. Presence of each is reported.
EVIDENCE_FIELDS = (
    "target_present",
    "target_range_known",
    "target_timestamp_known",
    "n_analysts_known",
    "rating_present",
    "rating_history_present",
    "target_history_present",
    "firm_actions_present",
    "dispersion_known",
    "price_fresh",
)


def completeness(e: dict) -> dict:
    """Which decision-relevant facts exist for this name. Descriptive only."""
    pt_ok = e.get("target_median") is not None
    have = {
        "target_present": pt_ok,
        "target_range_known": (e.get("target_low") is not None
                               and e.get("target_high") is not None),
        # Yahoo gives a consensus target with NO timestamp. Until the snapshot
        # ledger has observed the same ticker twice we genuinely do not know
        # when this number was set.
        "target_timestamp_known": bool(e.get("target_observed_at")),
        "n_analysts_known": e.get("n_analysts") is not None,
        "rating_present": e.get("consensus_score") is not None,
        "rating_history_present": bool(e.get("rating_history_present")),
        "target_history_present": bool(e.get("target_history_present")),
        "firm_actions_present": e.get("days_since_last_action") is not None,
        "dispersion_known": e.get("dispersion") is not None,
        "price_fresh": e.get("market_data_status") == "ok",
    }
    known = sum(1 for f in EVIDENCE_FIELDS if have[f])
    frac = known / len(EVIDENCE_FIELDS)
    return {
        **have,
        "known_fields": known,
        "total_fields": len(EVIDENCE_FIELDS),
        "known_fraction": round(frac, 3),
        "missing": [f for f in EVIDENCE_FIELDS if not have[f]],
        "grade": ("thin" if frac < 0.5 else "partial" if frac < 0.8 else "full"),
        "source_count": int(e.get("source_count") or 0),
    }


def _breadth(n: Optional[int]) -> tuple[float, bool]:
    """Analyst count on a 0-1 axis. Unknown is NOT full breadth."""
    if n is None:
        return UNKNOWN, False
    return min(1.0, math.log1p(max(0, int(n))) / math.log1p(15)), True


def _freshness(days: Optional[int]) -> tuple[float, bool]:
    """Decay on the last rating action. Unknown is NOT maximum freshness.

    The v1 bug in one line: `1.0 if days is None else exp(-days/180)`. A name
    with no ratings tape at all scored above a name upgraded yesterday.
    """
    if days is None:
        return UNKNOWN, False
    return max(0.05, math.exp(-(max(0, days) / 365.0))), True


def reliability(e: dict, comp: Optional[dict] = None) -> dict:
    """A bounded DISCOUNT on the expected return. Never an amplifier.

    Multiplicative in the things that independently degrade a consensus
    number: how many analysts stand behind it, how long ago anyone looked, how
    far apart they are, and how much of the record we hold at all.
    """
    comp = comp or completeness(e)
    breadth, breadth_known = _breadth(e.get("n_analysts"))
    fresh, fresh_known = _freshness(e.get("days_since_last_action"))

    # Each factor maps a 0-1 axis onto a discount band. The bands are chosen so
    # that a fully-covered, fresh, tight, complete name scores ~1.0 and a name
    # we know almost nothing about lands near the floor — and neither of those
    # is a measurement.
    f_breadth = 0.55 + 0.45 * breadth
    f_fresh = 0.60 + 0.40 * fresh
    f_complete = 0.70 + 0.30 * comp["known_fraction"]

    disp = e.get("dispersion")
    if disp is None:
        f_disp = 0.85          # unknown dispersion is penalised, not ignored
        disp_known = False
    else:
        # dispersion = (high - low) / median. Above 1.0 the street does not
        # agree on the order of magnitude.
        f_disp = max(0.60, 1.0 - 0.20 * max(0.0, float(disp) - 1.0))
        disp_known = True

    f_stale = 0.75 if e.get("analyst_data_status") == "stale" else 1.0

    mult = f_breadth * f_fresh * f_complete * f_disp * f_stale
    mult = max(RELIABILITY_FLOOR, min(1.0, mult))
    return {
        "multiplier": round(mult, 4),
        "calibrated": False,
        "components": {
            "breadth": round(f_breadth, 3),
            "freshness": round(f_fresh, 3),
            "completeness": round(f_complete, 3),
            "dispersion": round(f_disp, 3),
            "staleness": round(f_stale, 3),
        },
        "unknowns_penalised": [k for k, known in
                               (("n_analysts", breadth_known),
                                ("days_since_last_action", fresh_known),
                                ("dispersion", disp_known)) if not known],
        "floor": RELIABILITY_FLOOR,
        "grade": "OBSERVATIONAL — heuristic prior, fitted to nothing",
        "note": ("a discount only: bounded to [floor, 1.0] so no combination of "
                 "evidence can raise an expected return above the haircut "
                 "analyst number"),
    }


#: Rating momentum is allowed to tilt a size, within a narrow band, because it
#: is the part of the analyst tape that is closest to news. It is NOT
#: reliability — a name can be perfectly covered and getting downgraded — so it
#: is a separate, separately-bounded, separately-labelled multiplier.
REVISION_TILT_BAND = 0.20


def revision_tilt(e: dict) -> dict:
    """Rating drift and the 90-day upgrade tape as a bounded tilt on mu.

    Bounded to +-20%. A momentum signal that can double a position is not a
    tilt, it is the thesis, and this one has never been validated.
    """
    drift = e.get("rating_drift_3m")
    net = e.get("net_90d")
    known = drift is not None or net is not None
    d = 0.0 if drift is None else max(-0.5, min(0.5, float(drift)))
    n = 0 if net is None else max(-5, min(5, int(net)))
    raw = 0.5 * d + 0.03 * n
    tilt = 1.0 + max(-REVISION_TILT_BAND, min(REVISION_TILT_BAND, raw))
    return {
        "multiplier": round(tilt, 4),
        "known": known,
        "rating_drift_3m": drift,
        "net_90d": net,
        "band": REVISION_TILT_BAND,
        "grade": "OBSERVATIONAL, unvalidated",
        "note": ("rating-count momentum, NOT a target revision. Real "
                 "delta-target needs the analyst snapshot ledger to have "
                 "observed this ticker on two different days."),
    }


def evidence_summary(e: dict) -> dict:
    """One object carrying everything the sizing path is allowed to consult."""
    comp = completeness(e)
    rel = reliability(e, comp)
    tilt = revision_tilt(e)
    return {"completeness": comp, "reliability": rel, "revision_tilt": tilt,
            "usable_multiplier": round(rel["multiplier"] * tilt["multiplier"], 4)}


def is_finite(x: Any) -> bool:
    """NaN and inf are missing data wearing a number's clothes."""
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False
