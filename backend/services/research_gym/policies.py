"""The alternatives. "We sold — but what if we had held?" as executable code.

A policy maps a decision and the price path that followed it to an EXPOSURE
PATH: how much of the position was held on each forward day. The return is then
the exposure path dotted with the daily returns, minus the cost of every change
in exposure.

WHY EXPOSURE PATHS AND NOT "STRATEGY RETURNS"
=============================================
Because the interesting failures live in the path, not the endpoint. "Sold and
re-entered after 10 days" and "sold and re-entered when volatility rolled over"
can produce the same total return by completely different routes, and only one
of them is a rule that could transfer. Keeping the path means the attribution
layer can ask *when* the decision lost its money, which is what separates a
timing failure from a forecast failure.

COSTS ARE NOT OPTIONAL
======================
Every exposure change is charged. A counterfactual menu that quietly ignored
turnover would rank the busiest policy first, every time, and the busiest policy
is the one most likely to be fitting noise. R9 names cost survival as part of
fitness; this is where it is actually paid.

THE MENU IS DECLARED, NOT DISCOVERED
====================================
`POLICY_MENU` is fixed and named. The counterfactual engine records the WHOLE
surface — every policy, every time — rather than reporting the best one. A
surface reported as "the best alternative was X" is a maximum over a search, and
a maximum over a search is not an estimate of anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

#: One-way cost per unit of exposure changed. 10 bps is deliberately not
#: generous: G7 in this project already established that turnover assumptions
#: decide outcomes, and a Gym that flatters its own policies teaches nothing.
DEFAULT_COST_BPS_ONE_WAY = 10.0


@dataclass(frozen=True)
class PolicyResult:
    name: str
    exposure_path: tuple[float, ...]
    gross_return_pct: float
    cost_pct: float
    net_return_pct: float
    turnover: float
    #: Day index at which exposure first differs from the taken action's. Lets
    #: the attribution layer ask when a policy's advantage was actually earned.
    first_divergence_day: int | None
    #: The NET WEALTH PATH, added 2026-08-15 for P0.5.
    #:
    #: Until then this dataclass carried return, cost and turnover and NOTHING
    #: about the route — no drawdown, no minimum wealth, no time under water —
    #: and `ResponseSurface.ranked()` sorted on `net_return_pct` alone. So the
    #: identity of the "best" counterfactual, and every attribution label
    #: derived from it, was computed under an objective nobody had declared:
    #: raw terminal return, out of a menu containing 1.25x and 1.5x levered
    #: arms. The programme's stated objective is terminal wealth under a
    #: DECLARED utility. Those are different objectives and they disagree.
    #:
    #: The path is kept rather than a handful of summary statistics because
    #: which statistics matter depends on the utility function, and the utility
    #: functions are not all declared yet.
    wealth_path: tuple[float, ...] = ()

    @property
    def path_net_return_pct(self) -> float | None:
        """Terminal return of `wealth_path`. NOT identical to `net_return_pct`.

        `net_return_pct` charges turnover as a single subtraction at the end;
        the path charges it multiplicatively as it is incurred, so the two
        differ by a compounding-of-costs term of order (cost x return). Both
        are kept and neither is silently substituted for the other:
        `net_return_pct` is the quantity every existing tensor cell was
        computed with, and rewriting it would change published numbers to fix a
        rounding difference.
        """
        if not self.wealth_path:
            return None
        return (self.wealth_path[-1] - 1.0) * 100.0


def _apply(exposure: Sequence[float], daily_returns: Sequence[float],
           start_exposure: float, cost_bps: float
           ) -> tuple[float, float, float, tuple[float, ...]]:
    """(gross %, cost %, turnover, net wealth path) for one exposure path.

    Compounded, not summed. A 60-day path summed rather than compounded drifts
    enough to reorder policies whose true difference is a few percent, and the
    whole exercise is about small differences between alternatives.

    The wealth path is NET and charges each exposure change on the day it
    happens. The three scalars are unchanged from the version that returned
    only them — deliberately, because every tensor cell already computed was
    computed with them, and a path is being ADDED rather than substituted.
    """
    prev, turnover = float(start_exposure), 0.0
    gross, wealth = 1.0, 1.0
    path: list[float] = []
    for e, r in zip(exposure, daily_returns):
        d = abs(float(e) - prev)
        turnover += d
        prev = float(e)
        gross *= (1.0 + float(e) * float(r))
        wealth *= (1.0 + float(e) * float(r)) * (1.0 - d * cost_bps / 10_000.0)
        path.append(wealth)
    cost = turnover * (cost_bps / 10_000.0)
    return ((gross - 1.0) * 100.0, cost * 100.0, turnover, tuple(path))


# ── the menu ────────────────────────────────────────────────────────────────
# Each builder returns an exposure path of len(daily_returns).

def _flat(level: float):
    def build(daily_returns, ctx):
        return [level] * len(daily_returns)
    return build


def _delayed_reentry(sell_to: float, days: int):
    """Sell now, come back after a fixed number of days.

    The simplest possible answer to "what if we had bought back in later", and
    the one that tests whether the exit had any information at all: if a fixed
    calendar re-entry beats the discretionary one, the exit was noise with a
    story attached.
    """
    def build(daily_returns, ctx):
        n = len(daily_returns)
        return [sell_to] * min(days, n) + [1.0] * max(0, n - days)
    return build


def _drawdown_reentry(sell_to: float, trigger_pct: float):
    """Sell now, re-enter once price has fallen a further `trigger_pct`.

    Murat's question in its literal form: *what if we buy after it dropped to a
    certain percentage?* Note it re-enters from the DECISION price, not from the
    running peak — a trailing trigger is a different rule and gets its own
    entry rather than being folded in here.
    """
    def build(daily_returns, ctx):
        out, cum, re_entered = [], 1.0, False
        for r in daily_returns:
            cum *= (1.0 + r)
            if not re_entered and (cum - 1.0) * 100.0 <= -abs(trigger_pct):
                re_entered = True
            out.append(1.0 if re_entered else sell_to)
        return out
    return build


def _vol_reversal_reentry(sell_to: float, lookback: int = 5):
    """Sell now, re-enter when realised volatility rolls over.

    The mechanism the timing backtest's failure suggests: extreme stress is real
    and is a poor reason to be flat, because it is followed by mean reversion.
    "Volatility has peaked" is the falsifiable version of "the panic is over".
    """
    def build(daily_returns, ctx):
        out, re_entered = [], False
        for i, _ in enumerate(daily_returns):
            if not re_entered and i >= 2 * lookback:
                recent = daily_returns[i - lookback:i]
                prior = daily_returns[i - 2 * lookback:i - lookback]
                rv = sum(x * x for x in recent)
                pv = sum(x * x for x in prior)
                if pv > 0 and rv < pv:
                    re_entered = True
            out.append(1.0 if re_entered else sell_to)
        return out
    return build


def _scale_in(sell_to: float, steps: int, every: int):
    """Sell now, then rebuild the position in equal steps.

    Included because it is the policy most likely to beat both extremes while
    being the least likely to be chosen by a rule that thinks in signals. If
    scale-in wins repeatedly, the finding is about sizing, not timing — and this
    project has now reached that conclusion three separate times by other
    routes.
    """
    def build(daily_returns, ctx):
        out = []
        for i, _ in enumerate(daily_returns):
            done = min(steps, i // every)
            out.append(sell_to + (1.0 - sell_to) * (done / steps))
        return out
    return build


def _hedged(level: float, hedge: float):
    """Stay invested and carry a short hedge. Net exposure, not two books."""
    return _flat(level - hedge)


#: THE DECLARED MENU. Names are stable because they end up in lineage rows.
POLICY_MENU: dict[str, Callable] = {
    "hold": _flat(1.0),
    "sell_25": _flat(0.75),
    "sell_50": _flat(0.50),
    "sell_100": _flat(0.0),
    "buy_25": _flat(1.25),
    "buy_50": _flat(1.50),
    "sell_100_reenter_3d": _delayed_reentry(0.0, 3),
    "sell_100_reenter_10d": _delayed_reentry(0.0, 10),
    "sell_100_reenter_21d": _delayed_reentry(0.0, 21),
    "sell_100_reenter_down_5pct": _drawdown_reentry(0.0, 5.0),
    "sell_100_reenter_down_10pct": _drawdown_reentry(0.0, 10.0),
    "sell_50_reenter_down_10pct": _drawdown_reentry(0.5, 10.0),
    "sell_100_reenter_vol_rollover": _vol_reversal_reentry(0.0),
    "sell_50_reenter_vol_rollover": _vol_reversal_reentry(0.5),
    "sell_100_scale_in_4x5d": _scale_in(0.0, 4, 5),
    "sell_50_scale_in_4x5d": _scale_in(0.5, 4, 5),
    "hold_hedged_25": _hedged(1.0, 0.25),
}


def run_policy(name: str, daily_returns: Sequence[float], *,
               start_exposure: float = 1.0,
               taken_exposure_path: Sequence[float] | None = None,
               cost_bps: float = DEFAULT_COST_BPS_ONE_WAY,
               ctx: dict | None = None) -> PolicyResult:
    """One policy over one forward path."""
    if name not in POLICY_MENU:
        raise KeyError(f"unknown policy {name!r}")
    path = [float(x) for x in
            POLICY_MENU[name](list(daily_returns), ctx or {})]
    gross, cost, turnover, wealth = _apply(path, daily_returns,
                                           start_exposure, cost_bps)
    div = None
    if taken_exposure_path is not None:
        for i, (a, b) in enumerate(zip(path, taken_exposure_path)):
            if abs(a - b) > 1e-9:
                div = i
                break
    return PolicyResult(name=name, exposure_path=tuple(path),
                        gross_return_pct=gross, cost_pct=cost,
                        net_return_pct=gross - cost, turnover=turnover,
                        first_divergence_day=div, wealth_path=wealth)
