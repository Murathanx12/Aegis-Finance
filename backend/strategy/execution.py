"""S5 -- `breakeven_fee_bps` ON EVERY RESULT ROW, and an ADV cap that carries
the shortfall forward.

TWO NUMBERS, ONE PURPOSE
========================
House canon is *"quote the cost rate or don't quote the count"*. The cheapest
possible enforcement is to print, beside every book, the cost rate at which its
edge is exactly zero:

    breakeven_fee_bps = ln(1 + gross_return) / (2 * trades * position_size) * 1e4

THE UNITS ARE PER SIDE, and the `2` in the denominator is why: total cost is
`2 * trades * size * rate`, so the rate this solves for is the one charged on
EACH of the two legs. It must therefore be compared with a PER-SIDE cost
(`COST_BPS_PER_SIDE`, the 10 / 25 bps grid), never with a round trip -- that
mistake is a factor of two and it flatters every book. This module was written
comparing against the round trip and was corrected when the event-family lane
measured PEAD's breakeven at **1.2-14.6 bps a side** against exactly that 10 /
25 grid: the effect is inside the spread, and at the wrong units three of those
cells would have read as survivors.

A book whose breakeven is 6 bps a side and whose venue charges 10 a side is
dead, and that can be read at a glance without re-running anything. Beside it
sits the second
number: how much of the target the tape could actually supply. A backtest that
fills any size at the close has acquired capacity it never had, and the honest
treatment of an unfillable target is neither to fill it nor to drop it, but to
carry the SHORTFALL into the next rebalance as a tracked deficit.

LICENCE
=======
Both implementations are **vendored VERBATIM** from Vibe-Trading (HKUDS),
**MIT**, in `backend/strategy/vendor/` with the project LICENSE prepended to
each file, and are byte-compared against the clone by
`backend/tests/test_strategy_execution.py`. This module is the Aegis side: the
carry-forward loop, the comparison against the strategy's DECLARED cost rate,
and the row that both travel on. No upstream body is edited.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from backend.strategy.vendor import (DEFAULT_MAX_PARTICIPATION, VENDOR,
                                     apply_adv_capacity, breakeven_fee_bps)

CANNOT_DETERMINE = "CANNOT DETERMINE"


class ExecutionRefused(ValueError):
    """An execution number could not be derived from the inputs given."""


# --------------------------------------------------------------------------
# breakeven fee


def breakeven_row(*, gross_return: float | None, trades: int | None,
                  position_size: float | None = None,
                  declared_cost_bps_per_side: float | None = None) -> dict:
    """The breakeven fee PER SIDE, and whether the book's declared cost clears it.

    `declared_cost_bps_per_side` is a PER-SIDE rate -- the same units as
    `learner.evaluate.COST_BPS_PER_SIDE` and as the 10 / 25 bps grid every
    Aegis receipt is computed on. Passing a round trip here overstates the
    book's headroom by exactly a factor of two.

    `CANNOT DETERMINE` rather than a number whenever the identity's inputs are
    not usable -- a book with zero trades has no breakeven fee, and printing
    `inf` would read as "costs can never kill this".
    """
    be = breakeven_fee_bps(gross_return if gross_return is not None else float("nan"),
                           int(trades) if trades is not None else 0,
                           position_size)
    row: dict[str, Any] = {
        "breakeven_fee_bps": be,
        "gross_return": gross_return,
        "trades": trades,
        "position_size": 1.0 if position_size is None else float(position_size),
        "identity": "ln(1+gross)/(2*trades*size)*1e4",
        "units": ("bps PER SIDE -- the 2 in the denominator is the two legs, so "
                  "compare against COST_BPS_PER_SIDE, never against a round trip"),
        # ALWAYS on the row, including on the CANNOT DETERMINE path: the cost
        # rate is half of "quote the cost rate or don't quote the count", and
        # dropping it when the other half is missing loses both.
        "declared_cost_bps_per_side": declared_cost_bps_per_side,
        "declared_round_trip_bps": (None if declared_cost_bps_per_side is None
                                    else 2.0 * float(declared_cost_bps_per_side)),
        "provenance": {"vendored_from": VENDOR["project"],
                       "licence": VENDOR["licence"], "head": VENDOR["head"]},
    }
    if be is None:
        row["verdict"] = (
            f"{CANNOT_DETERMINE}: the identity's inputs are not usable "
            f"(gross {gross_return!r}, trades {trades!r}, size "
            f"{position_size!r}). A book with no round trips has no breakeven "
            f"fee; a number here would read as 'costs cannot kill this'.")
        return row
    if declared_cost_bps_per_side is None:
        row["verdict"] = (
            f"breakeven {be:.2f} bps a side; {CANNOT_DETERMINE} whether it "
            f"survives, because no cost rate was declared. Quote the cost rate "
            f"or do not quote the count.")
        return row
    survives = float(declared_cost_bps_per_side) < be
    row["edge_survives_declared_cost"] = bool(survives)
    row["headroom_bps_per_side"] = be - float(declared_cost_bps_per_side)
    row["verdict"] = (
        f"breakeven {be:.2f} bps a side vs declared "
        f"{float(declared_cost_bps_per_side):.2f} bps a side -> "
        f"{'SURVIVES' if survives else 'DEAD AT ITS OWN COST RATE'}")
    return row


# --------------------------------------------------------------------------
# ADV participation cap, with the shortfall carried forward


@dataclass(frozen=True)
class CapacityPath:
    """One capped rebalance path. Every field is a fraction of capital."""

    achieved: pd.DataFrame           # period x symbol, what was actually held
    requested: pd.DataFrame          # period x symbol, what was asked for
    unfilled: pd.DataFrame           # requested - achieved, the tracked deficit
    executed_turnover: pd.Series     # one-way, per period
    unfilled_turnover: pd.Series     # what the cap prevented, per period
    capped_symbols: Mapping[Any, tuple[str, ...]]
    max_participation: float

    def as_dict(self) -> dict:
        total_req = float(self.executed_turnover.sum() + self.unfilled_turnover.sum())
        fill_ratio = (float(self.executed_turnover.sum()) / total_req
                      if total_req > 0 else None)
        return {
            "max_participation": self.max_participation,
            "n_periods": int(len(self.achieved)),
            "executed_turnover_total": float(self.executed_turnover.sum()),
            "unfilled_turnover_total": float(self.unfilled_turnover.sum()),
            "fill_ratio": fill_ratio,
            "periods_with_a_capped_name": int(
                sum(1 for v in self.capped_symbols.values() if v)),
            "final_unfilled_by_symbol": {
                str(k): float(v) for k, v in self.unfilled.iloc[-1].items()
                if abs(float(v)) > 1e-12} if len(self.unfilled) else {},
            "note": ("the shortfall is CARRIED FORWARD: a target the tape could "
                     "not supply this period is still the target next period, "
                     "so it appears as a tracked deficit rather than as a fill "
                     "that never happened or a position that was silently "
                     "abandoned"),
            "provenance": {"vendored_from": VENDOR["project"],
                           "licence": VENDOR["licence"], "head": VENDOR["head"]},
        }


def adv_capped_path(target_weights: Mapping[Any, Mapping[str, float]] | pd.DataFrame,
                    adv_value: Mapping[Any, Mapping[str, float]] | pd.DataFrame,
                    *,
                    capital: float,
                    max_participation: float = DEFAULT_MAX_PARTICIPATION,
                    initial_weights: Mapping[str, float] | None = None
                    ) -> CapacityPath:
    """Walk a weight path under an ADV participation cap.

    Each period's achieved book becomes the next period's starting book, so an
    unfilled target is automatically still outstanding -- that IS the
    carry-forward, and expressing it as state rather than as a separate ledger
    is what stops the two drifting apart.

    `adv_value` is average daily traded VALUE in the same currency as
    `capital`, never a share count. A symbol with no ADV entry, or a
    non-positive one, is treated as UNTRADEABLE for that period: its weight
    stays where it was and the whole requested change is recorded as unfilled.
    Assuming an unknown volume is infinite liquidity is how a backtest acquires
    capacity it never had.
    """
    tw = pd.DataFrame(target_weights).T if isinstance(target_weights, Mapping) \
        else pd.DataFrame(target_weights)
    av = pd.DataFrame(adv_value).T if isinstance(adv_value, Mapping) \
        else pd.DataFrame(adv_value)
    if tw.empty:
        raise ExecutionRefused(
            "REFUSED: no target weights. An empty capacity path would report "
            "a 100% fill ratio, which reads as 'the tape supplied everything'.")
    tw = tw.sort_index()
    missing = [p for p in tw.index if p not in av.index]
    if missing:
        raise ExecutionRefused(
            f"REFUSED: {len(missing)} period(s) have target weights and no ADV "
            f"({missing[:3]}...). A period priced without volume is a period "
            f"assumed infinitely liquid.")

    cur = pd.Series(dict(initial_weights or {}), dtype=float)
    ach_rows, req_rows, unf_rows = {}, {}, {}
    ex_turn, un_turn, capped = {}, {}, {}
    for period in tw.index:
        target = tw.loc[period].dropna().astype(float)
        adv = av.loc[period].reindex(
            target.index.union(cur.index)).astype(float)
        res = apply_adv_capacity(target, cur, adv, float(capital),
                                 float(max_participation))
        before = cur.reindex(res.achieved_weights.index).fillna(0.0)
        executed = float((res.achieved_weights - before).abs().sum())
        prevented = float(res.unfilled_weights.abs().sum())
        ach_rows[period] = res.achieved_weights
        req_rows[period] = res.requested_weights
        unf_rows[period] = res.unfilled_weights
        ex_turn[period] = executed
        un_turn[period] = prevented
        capped[period] = tuple(res.capped_symbols)
        cur = res.achieved_weights

    return CapacityPath(
        achieved=pd.DataFrame(ach_rows).T.fillna(0.0),
        requested=pd.DataFrame(req_rows).T.fillna(0.0),
        unfilled=pd.DataFrame(unf_rows).T.fillna(0.0),
        executed_turnover=pd.Series(ex_turn),
        unfilled_turnover=pd.Series(un_turn),
        capped_symbols=capped,
        max_participation=float(max_participation),
    )


# --------------------------------------------------------------------------
# the row both numbers travel on


def execution_row(*, gross_return: float | None, trades: int | None,
                  position_size: float | None = None,
                  declared_cost_bps_per_side: float | None = None,
                  capacity: CapacityPath | None = None) -> dict:
    """The block `run_one` attaches to every receipt."""
    out = {"breakeven": breakeven_row(
        gross_return=gross_return, trades=trades, position_size=position_size,
        declared_cost_bps_per_side=declared_cost_bps_per_side)}
    out["capacity"] = capacity.as_dict() if capacity is not None else {
        "verdict": (f"{CANNOT_DETERMINE}: no ADV series was supplied, so the "
                    f"book's capacity is unmeasured. That is not the same as "
                    f"uncapped -- it is unknown.")}
    return out


def trades_from_turnover(turnover_by_period: Sequence[float] | pd.Series,
                         *, n_names: float | None = None) -> int:
    """Round trips implied by a one-way turnover series.

    One-way turnover of 1.0 over the whole book is one full round trip's worth
    of a leg; two legs make a round trip, so `trades = sum(turnover) / 2`
    expressed in book units. `n_names` converts book units into name-level
    round trips when a caller wants the count per position rather than per
    book. Returns at least 0, never a fraction pretending to be a count.
    """
    s = pd.Series(list(turnover_by_period), dtype=float).dropna()
    if s.empty:
        return 0
    book_round_trips = float(s.sum()) / 2.0
    if n_names:
        book_round_trips *= float(n_names)
    return int(max(0, round(book_round_trips)))


__all__ = ["CANNOT_DETERMINE", "CapacityPath", "ExecutionRefused",
           "adv_capped_path", "breakeven_fee_bps", "breakeven_row",
           "execution_row", "trades_from_turnover"]
