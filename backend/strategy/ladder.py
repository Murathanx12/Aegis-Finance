"""S6 -- THE EXIT LADDER AS ITS OWN TESTED MODEL.

Entry alpha and exit alpha are different problems. Aegis has spent five months
improving selection and grading books on it, while the fleet's own measurement
says the exits destroy most of what selection produces -- turnover fell
0.90 -> 0.53 by changing the HOLDING rule alone, nothing about which names were
picked. So the sell gets its own object, its own ranking, its own known-answer
tests and its own meta-label.

WHAT IS HERE
============
1.  `ExitLadder` -- the ranked resolution. Every reason is evaluated on every
    bar and a LIST is returned; the winner is the first entry of the
    contract's declared `exit_priority`. Two reasons firing on one bar must
    resolve identically in paper and in replay, and the only way to guarantee
    that is to make the order data on the contract instead of a property of
    which `if` a programmer wrote first.
2.  `stop_vs_volatility` -- THE EXPLICIT INPUT. On 2026-09-08 one book's stop
    width was measured at 0.98 of the name's daily standard deviation, so the
    stop was inside a single ordinary session's noise and the declared minimum
    hold could never bind: the position was always stopped out before the hold
    rule had anything to say. That relationship is now a computed, testable
    number on the ladder rather than an accident discovered afterwards.
3.  `simulate_ladder` -- run one position through a price path and get back the
    typed reason, the bar and the P&L. Deterministic, no randomness, no costs
    invented (costs belong to `CostModel`).
4.  `meta_label_exits` -- META-LABEL THE SELL. For each realised exit, look at
    what the position would have done had it been held: an exit is CORRECT when
    the forward return after it was worse than holding. Aggregated by typed
    reason, this is a scoreboard for the exit RULE, not for the book.

PROVENANCE AND LICENCE
======================
The `minimal_roi` time-decayed curve and the four-step exit ordering are
freqtrade's DESIGN (`freqtrade/strategy/interface.py`, GPL-3.0). No freqtrade
code is copied, imported or adapted; the spec was written in English first and
is reproduced in `docs/BUILD_2026-09-08_R5_STRATEGY_PORTS.md` section S6. The
typed reason vocabulary and the ranking are Aegis's own
(`backend/strategy/contract.DEFAULT_EXIT_PRIORITY`, mirroring the terminal
repo's `alpha/contract.EXIT_REASONS`). The meta-labelling framing is
Akepanidtaworn et al. 2023, "Selling Fast and Buying Slow".

FILL CONVENTIONS, WRITTEN DOWN
==============================
Stated so a reader can attack them, which is the transferable half of
freqtrade's backtest documentation:
  * one price per bar; there is no intrabar path, so a bar that touches both
    the stop and an ROI rung resolves by the declared RANKING, not by which
    the price reached first;
  * a stop fills AT the stop level, not at the bar's price -- optimistic, and
    named as such;
  * the ROI rung fills at the bar's price when the bar's return is at or above
    the rung, so a 6% rung can exit at 9%;
  * `min_hold_periods` SUPPRESSES the normal exits (ROI, deadline, rebalance)
    and never the emergency ones (stop, thesis invalidated). A minimum hold
    that could hold through a stop would be a risk limit that a calendar
    overrides.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from backend.strategy.contract import DEFAULT_EXIT_PRIORITY, HoldRule

CANNOT_DETERMINE = "CANNOT DETERMINE"

#: Reasons a minimum hold may NOT suppress. A hold rule that held through a
#: stop would be a calendar overriding a risk limit.
EMERGENCY_REASONS: frozenset[str] = frozenset(
    {"THESIS_INVALIDATED", "EXPLICIT_EVENT_STRATEGY_EXIT", "STOP",
     "TRAILING_STOP"})


class LadderRefused(ValueError):
    """The ladder could not be evaluated from the inputs given."""


@dataclass(frozen=True)
class ExitCheck:
    """One reason, and whether it fired on this bar."""

    reason: str
    fired: bool
    detail: str = ""
    level: float | None = None

    def as_dict(self) -> dict:
        return {"reason": self.reason, "fired": self.fired,
                "detail": self.detail, "level": self.level}


@dataclass(frozen=True)
class LadderDecision:
    """Every reason evaluated, and the one the ranking selected."""

    winner: str | None
    checks: tuple[ExitCheck, ...]
    periods_held: int
    unrealised_return: float
    suppressed_by_min_hold: tuple[str, ...] = ()
    priority: tuple[str, ...] = DEFAULT_EXIT_PRIORITY

    @property
    def fired(self) -> tuple[str, ...]:
        return tuple(c.reason for c in self.checks if c.fired)

    def as_dict(self) -> dict:
        return {"winner": self.winner, "fired": list(self.fired),
                "periods_held": self.periods_held,
                "unrealised_return": self.unrealised_return,
                "suppressed_by_min_hold": list(self.suppressed_by_min_hold),
                "priority": list(self.priority),
                "checks": [c.as_dict() for c in self.checks]}


@dataclass(frozen=True)
class ExitLadder:
    """The exit model. Built from a `HoldRule`; holds no state of its own."""

    hold: HoldRule
    signal_says_exit: bool = False

    # --------------------------------------------------------------- decision

    def evaluate(self, *, periods_held: int, unrealised_return: float,
                 peak_return: float | None = None,
                 signal_says_exit: bool | None = None,
                 event_exit: bool = False,
                 scheduled_review: bool = False) -> LadderDecision:
        """Evaluate EVERY reason, then resolve by the declared ranking."""
        if periods_held < 0:
            raise LadderRefused("periods_held must be >= 0")
        h = self.hold
        sig = self.signal_says_exit if signal_says_exit is None else signal_says_exit
        peak = unrealised_return if peak_return is None else float(peak_return)

        checks: list[ExitCheck] = []
        checks.append(ExitCheck(
            "THESIS_INVALIDATED", bool(sig),
            "the signal said sell" if sig else "the signal still says hold"))
        checks.append(ExitCheck(
            "EXPLICIT_EVENT_STRATEGY_EXIT", bool(event_exit),
            "the contract's declared event window closed" if event_exit else ""))

        stop = h.stop_loss
        checks.append(ExitCheck(
            "STOP", stop is not None and unrealised_return <= float(stop),
            f"unrealised {unrealised_return:+.4f} vs stop {stop}"
            if stop is not None else "no stop declared", stop))

        roi = h.roi_floor_at(periods_held)
        checks.append(ExitCheck(
            "ROI_LADDER", roi is not None and unrealised_return >= float(roi),
            (f"rung at {periods_held} periods is {roi}"
             if roi is not None else
             f"{CANNOT_DETERMINE}: no rung has matured at {periods_held} "
             f"periods, which is NOT the same as a rung of 0.0"), roi))

        trail = h.trailing_stop
        trail_hit = (trail is not None and peak > 0
                     and (unrealised_return - peak) <= -abs(float(trail)))
        checks.append(ExitCheck(
            "TRAILING_STOP", bool(trail_hit),
            f"gave back {peak - unrealised_return:+.4f} from a peak of {peak:+.4f}"
            if trail is not None else "no trailing stop declared", trail))

        checks.append(ExitCheck(
            "DEADLINE", periods_held >= int(h.horizon_periods),
            f"{periods_held} of {h.horizon_periods} periods",
            float(h.horizon_periods)))

        rebal = bool(scheduled_review) and h.scheduled_review_periods is not None
        checks.append(ExitCheck("REBALANCE", rebal,
                                "dropped out on a scheduled pass" if rebal else ""))

        by_reason = {c.reason: c for c in checks}
        suppressed: list[str] = []
        winner: str | None = None
        for reason in h.exit_priority:
            c = by_reason.get(reason)
            if c is None or not c.fired:
                continue
            if (periods_held < int(h.min_hold_periods)
                    and reason not in EMERGENCY_REASONS):
                suppressed.append(reason)
                continue
            winner = reason
            break

        return LadderDecision(
            winner=winner, checks=tuple(checks), periods_held=int(periods_held),
            unrealised_return=float(unrealised_return),
            suppressed_by_min_hold=tuple(suppressed),
            priority=tuple(h.exit_priority))

    # ------------------------------------------------------------- simulation

    def simulate(self, prices: Sequence[float],
                 *, signal_exit_at: int | None = None,
                 event_exit_at: int | None = None) -> dict:
        """Run one long position from `prices[0]` and report the typed exit."""
        px = [float(p) for p in prices]
        if len(px) < 2 or px[0] <= 0:
            raise LadderRefused(
                "REFUSED: a ladder simulation needs at least two positive "
                "prices; one bar cannot produce a hold or an exit.")
        entry = px[0]
        peak = 0.0
        for i in range(1, len(px)):
            r = px[i] / entry - 1.0
            peak = max(peak, r)
            d = self.evaluate(
                periods_held=i, unrealised_return=r, peak_return=peak,
                signal_says_exit=(signal_exit_at is not None and i >= signal_exit_at),
                event_exit=(event_exit_at is not None and i >= event_exit_at))
            if d.winner:
                fill = r
                if d.winner == "STOP" and self.hold.stop_loss is not None:
                    # optimistic and named as such: the stop fills AT its level
                    fill = float(self.hold.stop_loss)
                return {"exit_reason": d.winner, "exit_bar": i,
                        "periods_held": i, "return_at_bar": r,
                        "fill_return": fill, "decision": d.as_dict(),
                        "fill_convention": (
                            "one price per bar, no intrabar path; a stop fills "
                            "AT its level (optimistic); an ROI rung fills at "
                            "the bar's price, so a 6% rung can exit at 9%")}
        last = px[-1] / entry - 1.0
        return {"exit_reason": None, "exit_bar": None,
                "periods_held": len(px) - 1, "return_at_bar": last,
                "fill_return": last,
                "note": "still open at the end of the path (a censored spell)"}


# --------------------------------------------------------------------------
# the stop-width / holding-period-volatility relationship, as an INPUT


def stop_vs_volatility(hold: HoldRule, *, per_period_sd: float,
                       noise_multiple: float = 1.0) -> dict:
    """Is the declared stop inside the noise of the declared holding period?

    A stop of 3% on a name whose daily sd is 3.06% is 0.98 sd wide: it is
    inside a single ordinary session, so the position is stopped out by noise
    before the declared minimum hold has anything to say, and the hold rule can
    never bind. That was measured on a live book on 2026-09-08. It is now a
    number the ladder computes and a test asserts, not an accident.

    The holding-period sd is the per-period sd scaled by sqrt(min_hold), which
    assumes independent increments -- stated because it is the assumption that
    could be wrong, and a serially correlated name needs a larger multiple.
    """
    if per_period_sd is None or not np.isfinite(per_period_sd) or per_period_sd <= 0:
        return {"verdict": (f"{CANNOT_DETERMINE}: per_period_sd is "
                            f"{per_period_sd!r}. A stop cannot be compared to a "
                            f"volatility that was not measured, and assuming "
                            f"one would be inventing the answer."),
                "stop_in_sd": None, "min_hold_can_bind": None}
    if hold.stop_loss is None:
        return {"verdict": ("no stop declared, so the worst case is the whole "
                            "position, not a stop-bounded loss"),
                "stop_in_sd": None, "min_hold_can_bind": True}

    stop = abs(float(hold.stop_loss))
    one_period_sd = float(per_period_sd)
    n = max(1, int(hold.min_hold_periods))
    hold_sd = one_period_sd * float(np.sqrt(n))
    stop_in_sd = stop / one_period_sd
    stop_in_hold_sd = stop / hold_sd
    binds = stop_in_hold_sd > float(noise_multiple)
    return {
        "stop_pct": stop,
        "per_period_sd": one_period_sd,
        "min_hold_periods": int(hold.min_hold_periods),
        "holding_period_sd": hold_sd,
        "stop_in_sd": stop_in_sd,
        "stop_in_holding_period_sd": stop_in_hold_sd,
        "noise_multiple": float(noise_multiple),
        "min_hold_can_bind": bool(binds),
        "verdict": (
            f"stop {stop:.2%} is {stop_in_sd:.2f} per-period sd and "
            f"{stop_in_hold_sd:.2f} holding-period sd over {n} period(s) -> "
            + ("the declared minimum hold CAN bind"
               if binds else
               "STOP INSIDE THE NOISE: the position is stopped out by ordinary "
               "movement before the minimum hold has anything to say, so the "
               "declared hold rule can never bind")),
    }


# --------------------------------------------------------------------------
# META-LABEL THE SELL


def meta_label_exits(exits: Sequence[Mapping[str, Any]],
                     *, forward_return_key: str = "forward_return_if_held",
                     realised_key: str = "realised_return",
                     reason_key: str = "exit_reason") -> dict:
    """Score the EXIT RULE, by typed reason. Positive = the exit saved money.

    Each record needs what the position DID (`realised_return`) and what it
    WOULD have done had the exit not fired (`forward_return_if_held`), measured
    over the same forward window. The label is `realised - would_have_been`; an
    exit is CORRECT when that is positive.

    A record missing either field is counted as `unlabelled` and named -- never
    dropped, and never imputed as a zero, which would drag every reason's mean
    toward "the exit did nothing".
    """
    rows = list(exits)
    if not rows:
        return {"verdict": f"{CANNOT_DETERMINE}: no exits to label.",
                "n": 0, "by_reason": {}}

    labelled: list[tuple[str, float]] = []
    unlabelled = 0
    untyped = 0
    for r in rows:
        reason = r.get(reason_key)
        if not reason:
            reason = "UNTYPED"
            untyped += 1
        a, b = r.get(realised_key), r.get(forward_return_key)
        if a is None or b is None or not np.isfinite(float(a)) or not np.isfinite(float(b)):
            unlabelled += 1
            continue
        labelled.append((str(reason), float(a) - float(b)))

    by_reason: dict[str, dict] = {}
    for reason in sorted({r for r, _ in labelled}):
        vals = np.array([v for r, v in labelled if r == reason], dtype=float)
        n = int(len(vals))
        mean = float(vals.mean())
        sd = float(vals.std(ddof=1)) if n > 1 else float("nan")
        t = (mean / (sd / np.sqrt(n))) if n > 1 and sd > 0 else None
        by_reason[reason] = {
            "n": n,
            "mean_saved": mean,
            "share_correct": float((vals > 0).mean()),
            "t": None if t is None else float(t),
            "verdict": ("this exit reason SAVED money on average"
                        if mean > 0 else
                        "this exit reason COST money on average -- the position "
                        "would have done better held"),
        }

    total = np.array([v for _, v in labelled], dtype=float)
    return {
        "n": len(rows),
        "n_labelled": int(len(labelled)),
        "n_unlabelled": unlabelled,
        "n_untyped": untyped,
        "mean_saved_overall": float(total.mean()) if len(total) else None,
        "by_reason": by_reason,
        "label": "realised_return - forward_return_if_held, over one window",
        "note": ("an exit with no typed reason is counted as UNTYPED, never "
                 "dropped; a record missing either leg is counted as "
                 "unlabelled, never imputed as zero"),
    }


__all__ = ["CANNOT_DETERMINE", "EMERGENCY_REASONS", "ExitCheck", "ExitLadder",
           "LadderDecision", "LadderRefused", "meta_label_exits",
           "stop_vs_volatility"]
