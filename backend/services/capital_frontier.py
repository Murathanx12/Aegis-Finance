"""
Capital frontier — the same evidence, sized at $10k and at $250m
================================================================

The product's mandate is not "manage $45k". It is: given ANY capital, what
should be owned? A name that is an obvious buy at $40k can be untradeable at
$50m, and that is a FINDING about the strategy's capacity, not a failure of the
name.

What this module will and will not claim
----------------------------------------

It reports, per name and per capital level: the dollar position implied by a
target weight, that position as a fraction of median daily dollar volume, an
estimated round-trip spread cost, and the number of trading days to enter or
exit at a participation cap.

It does **not** report market impact. G7 was measured at 31.00 bps across ADV
multiples spanning six orders of magnitude (1e6 down to 1), which means the
programme's cost model is insensitive to size and therefore **cannot price
impact at all** (NIGHT-8, CANON §17). Every capacity number here is a
**delay-only lower bound**: it says how long you would be in the market, not
what moving that size would cost you. A real impact model would make every
large-capital number worse, never better, so the direction of the error is
known and stated rather than hidden.

Spread is estimated by Corwin-Schultz from the daily high-low range where a
range is available. The naive `(high-low)/2` is the intraday RANGE, not the
spread, and using it understates costs by roughly an order of magnitude — that
mistake is what CANON §15 exists to prevent, and it is not repeated here.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from backend import config

logger = logging.getLogger(__name__)

#: Capital levels every finalist is evaluated at.
CAPITAL_LEVELS: tuple[float, ...] = (
    10_000.0, 40_000.0, 100_000.0, 1_000_000.0,
    10_000_000.0, 50_000_000.0, 250_000_000.0,
)

#: Share of a day's dollar volume a single order may take. Above this the
#: delay-only model stops being even a lower bound.
MAX_PARTICIPATION = 0.10

#: A position needing more than this many days to unwind is illiquid at that
#: capital, whatever its expected return.
MAX_DAYS_TO_EXIT = 5.0

#: Fallback round-trip cost when no spread can be estimated. Deliberately
#: pessimistic: an unknown spread is not a free one.
FALLBACK_ROUND_TRIP = 0.004


@dataclass
class CapacityRow:
    capital: float
    weight: float
    position_usd: float
    adv_fraction: Optional[float]
    days_to_exit: Optional[float]
    round_trip_cost: Optional[float]
    cost_usd: Optional[float]
    tradeable: bool
    binding_constraint: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def corwin_schultz_spread(high: Iterable[float],
                          low: Iterable[float]) -> Optional[float]:
    """Corwin-Schultz (2012) two-day high-low spread estimator, as a fraction.

    Returns None when the inputs cannot support an estimate. Negative estimates
    are a known artefact of the estimator and are floored at zero rather than
    passed through as a negative cost.
    """
    hs = [float(h) for h in high]
    ls = [float(l) for l in low]
    if len(hs) != len(ls) or len(hs) < 2:
        return None
    spreads: list[float] = []
    for i in range(1, len(hs)):
        h1, l1, h0, l0 = hs[i], ls[i], hs[i - 1], ls[i - 1]
        if min(h1, l1, h0, l0) <= 0:
            continue
        hi2, lo2 = max(h1, h0), min(l1, l0)
        if lo2 <= 0 or l1 <= 0 or l0 <= 0:
            continue
        beta = math.log(h0 / l0) ** 2 + math.log(h1 / l1) ** 2
        gamma = math.log(hi2 / lo2) ** 2
        denom = 3 - 2 * math.sqrt(2)
        alpha = (math.sqrt(2 * beta) - math.sqrt(beta)) / denom - \
            math.sqrt(gamma / denom)
        s = 2 * (math.exp(alpha) - 1) / (1 + math.exp(alpha))
        if math.isfinite(s):
            spreads.append(max(0.0, s))
    if not spreads:
        return None
    spreads.sort()
    mid = len(spreads) // 2
    return (spreads[mid] if len(spreads) % 2
            else 0.5 * (spreads[mid - 1] + spreads[mid]))


def capacity_for(*, weight: float, median_dollar_vol: Optional[float],
                 round_trip_cost: Optional[float] = None,
                 capital_levels: Iterable[float] = CAPITAL_LEVELS,
                 ) -> list[CapacityRow]:
    """One name's capacity profile across capital levels."""
    rows: list[CapacityRow] = []
    rt = round_trip_cost if round_trip_cost is not None else FALLBACK_ROUND_TRIP
    for cap in capital_levels:
        pos = cap * weight
        adv_frac = days = None
        tradeable = True
        binding = ""
        if median_dollar_vol and median_dollar_vol > 0:
            adv_frac = pos / median_dollar_vol
            days = adv_frac / MAX_PARTICIPATION
            if days > MAX_DAYS_TO_EXIT:
                tradeable = False
                binding = (f"{days:.1f} days to exit at {100*MAX_PARTICIPATION:.0f}% "
                           f"participation, over the {MAX_DAYS_TO_EXIT:.0f}-day limit")
        else:
            tradeable = False
            binding = "no median dollar volume — capacity cannot be checked"
        rows.append(CapacityRow(
            capital=cap, weight=weight, position_usd=round(pos, 2),
            adv_fraction=(None if adv_frac is None else round(adv_frac, 6)),
            days_to_exit=(None if days is None else round(days, 3)),
            round_trip_cost=round(rt, 5),
            cost_usd=round(pos * rt, 2),
            tradeable=tradeable, binding_constraint=binding))
    return rows


def frontier(candidates: list[Any], weights: dict[str, float],
             *, capital_levels: Iterable[float] = CAPITAL_LEVELS) -> dict:
    """Portfolio-level capacity: how much of the book survives at each size."""
    levels = list(capital_levels)
    by_name: dict[str, list[CapacityRow]] = {}
    for c in candidates:
        t = c.get("ticker") if isinstance(c, dict) else getattr(c, "ticker", "")
        w = weights.get(t, 0.0)
        if w <= 0:
            continue
        mdv = (c.get("median_dollar_vol") if isinstance(c, dict)
               else getattr(c, "median_dollar_vol", None))
        by_name[t] = capacity_for(weight=w, median_dollar_vol=mdv,
                                  capital_levels=levels)

    summary = []
    for i, cap in enumerate(levels):
        ok = [t for t, rows in by_name.items() if rows[i].tradeable]
        blocked = [t for t, rows in by_name.items() if not rows[i].tradeable]
        w_ok = sum(weights.get(t, 0.0) for t in ok)
        cost = sum(rows[i].cost_usd or 0.0 for rows in by_name.values())
        summary.append({
            "capital": cap,
            "n_names_tradeable": len(ok),
            "n_names_blocked": len(blocked),
            "weight_tradeable": round(w_ok, 4),
            "weight_blocked": round(sum(weights.get(t, 0.0) for t in blocked), 4),
            "round_trip_cost_usd": round(cost, 2),
            "round_trip_cost_pct_of_capital": (round(100 * cost / cap, 4)
                                               if cap else None),
            "blocked_names": sorted(blocked)[:10],
        })
    return {
        "levels": summary,
        "per_name": {t: [r.to_dict() for r in rows] for t, rows in by_name.items()},
        "participation_cap": MAX_PARTICIPATION,
        "max_days_to_exit": MAX_DAYS_TO_EXIT,
        "impact_caveat": (
            "DELAY-ONLY LOWER BOUND. G7 prices the same 31.00 bps at ADV "
            "multiples from 1e6 to 1, so this programme's cost model cannot "
            "price market impact (CANON §17). These numbers say how long you "
            "would be in the market, not what moving the size would cost. A "
            "real impact model makes every large-capital figure worse, never "
            "better."),
    }
