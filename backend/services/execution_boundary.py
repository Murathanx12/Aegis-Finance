"""A precursor can be observable, correct, and still unreachable.

THE THIRD VERDICT FAMILY
========================
This programme has had two ways for a result to fail. It is REAL, or it is NOT
ESTABLISHED. G4 produced a third:

    real, observable beforehand, and UNREACHABLE — because the execution
    boundary binds rather than the information.

87-95% of the earnings-announcement effect happens between the close and the
next open. The precursor was fine. The market was shut. That is not a power
problem, not a leakage problem, and no amount of better inference recovers it —
which is exactly why it needs its own name and its own guard, or it will be
rediscovered as a positive every time somebody measures an event on
close-to-close returns.

It is the Micron test's mirror. We spend our effort proving precursors were
observable BEFORE the fact; here one was, comfortably, and the answer was still
no.

THE DISCRIMINATING QUESTION IS NOT THE HORIZON
==============================================
The first instinct — "sweep every one-day close-to-close outcome" — is the wrong
axis, and running it that way would have condemned results that are perfectly
sound.

A daily regime signal computed from Monday's close, acted on at Monday's close,
holds through Tuesday's open. The overnight gap belongs to that position: the
decision preceded it. The utility and regret tensors are all of this kind, and
their one-day close-to-close outcomes are legitimate.

What matters is **when the information arrives relative to the last moment you
could act on it**:

    information at/before a close, decision at that close -> gap is EARNED
    information after the close, decision at the next open -> gap is LOST

So the guard asks about the arrival, not the horizon. Getting this wrong in the
strict direction is not free either: a rule that flagged every one-day outcome
would produce 150 false alarms here and then be switched off.
"""

from __future__ import annotations

import math

#: How the information reaches us relative to the session.
DURING_SESSION = "DURING_SESSION"
#: Arrives while the market is open; the gap does not separate it from action.
AT_OR_BEFORE_CLOSE = "AT_OR_BEFORE_CLOSE"
#: Arrives after the close (or before the open) — a window opens between
#: knowing and being able to act, and whatever happens in it is not ours.
OUTSIDE_SESSION = "OUTSIDE_SESSION"

ARRIVALS = (DURING_SESSION, AT_OR_BEFORE_CLOSE, OUTSIDE_SESSION)


class NotReportable(RuntimeError):
    """An event result quoted without saying how much of it was reachable."""


def gap_is_lost(arrival: str) -> bool:
    """Does a non-tradable window separate the information from the action?"""
    if arrival not in ARRIVALS:
        raise NotReportable(
            f"information arrival {arrival!r} is not one of {ARRIVALS}. "
            f"Undeclared is not the same as DURING_SESSION, and defaulting it "
            f"to the harmless case is how an untradable result gets reported "
            f"as an edge.")
    return arrival == OUTSIDE_SESSION


def tradable_fraction(gross: float, tradable: float, *,
                      gross_mde: float | None = None) -> dict:
    """What share of `gross` survived to the first moment anyone could act.

    Refuses to produce a ratio when the DENOMINATOR is below its own MDE. That
    rule was learned on `1 - tradable/gross` printing **253%** for a contrast
    whose gross was -0.05pp — a confident number computed from noise. The same
    refusal now covers every ratio in this programme, lift included.
    """
    if gross_mde is not None and abs(gross) < gross_mde:
        return {"fraction": None, "lost_to_gap": None,
                "why": (f"gross {gross:+.4g} is below its own MDE "
                        f"{gross_mde:.4g}; a share of it would be a ratio to "
                        f"noise, so none is reported")}
    if gross == 0 or not math.isfinite(gross):
        return {"fraction": None, "lost_to_gap": None,
                "why": "gross effect is zero or non-finite"}
    frac = tradable / gross
    return {"fraction": frac, "lost_to_gap": 1.0 - frac,
            "why": (f"{100 * (1 - frac):.0f}% of the gross effect occurred "
                    f"before the first tradable moment")}


def assert_reportable(*, event_family: str, arrival: str,
                      gross: float | None, tradable: float | None,
                      gross_mde: float | None = None) -> dict:
    """An event result must say how much of itself was reachable, or not report.

    The standing rule from Order 7, made mechanical: **every event result
    reports its tradable fraction or is not reportable.** A gross announcement
    effect with no tradable counterpart is a description of the world, not a
    claim about what could have been done in it, and the two have been
    confused in this literature for thirty years.
    """
    if gap_is_lost(arrival):
        if tradable is None:
            raise NotReportable(
                f"{event_family}: information arrives {arrival}, so a "
                f"non-tradable window separates it from any action. This "
                f"result may not be reported without its tradable "
                f"counterpart — measured, not assumed away.")
        if gross is None:
            raise NotReportable(f"{event_family}: no gross effect to compare")
        return {"event_family": event_family, "arrival": arrival,
                "gross": gross, "tradable": tradable, "reportable": True,
                **tradable_fraction(gross, tradable, gross_mde=gross_mde)}
    return {"event_family": event_family, "arrival": arrival,
            "gross": gross, "tradable": tradable, "reportable": True,
            "fraction": 1.0, "lost_to_gap": 0.0,
            "why": ("the decision could be taken at the same close the "
                    "information arrived at, so no window separates them and "
                    "the whole move belongs to the position")}
