"""A universe must state its population where it claims to trade.

WHY THIS IS A GUARD AND NOT A NOTE
==================================
`std_turn` cleared the BH-FDR screen at +18.28%/yr and then produced `n/a` in
the liquid dollar-volume tercile. The reason was not a small effect and not a
wide interval: there was a **median of two eligible names per month** in that
tercile. A decile sort of two names has no deciles. The cell was never a
measurement, and it was found by accident during a NaN-formatting repair.

That verdict — `NO_POPULATION_IN_SCOPE` — is categorically different from
`below its own MDE`:

* below MDE  : the effect may be real; this sample cannot separate it from
               zero. More data can change the answer.
* no population: where the effect lives and where we can act do not intersect.
               More data cannot change the answer, because the universe is not
               there to be sampled.

Reporting the second as the first invites a forward test that can only waste a
window. So the population is checked at REGISTRATION, before an outcome exists.

THE INPUT IS COUNTS, NOT A DECLARED MEDIAN
==========================================
A guard whose input is on the honour system is not a guard: it will fool its own
author. `assess_population` therefore takes the **per-period counts** and
derives the median itself. Handed nothing, it refuses. There is no argument a
caller can pass that asserts "the population is fine".
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

#: A decile needs enough members that its mean is not one name's idiosyncrasy.
#: The library's own sorter already refuses below this; stating it here makes it
#: a declared design requirement rather than an implementation detail.
MIN_DECILE_MEMBERS = 5

#: A design scoreable in the median period can still be unscoreable in a large
#: MINORITY of them, and then its table is computed on a different universe from
#: the one it declares. This is the second failure mode and it needs its own
#: threshold, well above one half.
#:
#: It has to be above one half for a structural reason, not a taste one: the
#: median clears the requirement if and only if at least half the periods do, so
#: a "thin" band defined at 0.5 would be unreachable — the two conditions would
#: be the same condition. The first version was written that way and the test
#: that was supposed to exercise the branch fell into the other one instead.
MIN_SCOREABLE_SHARE = 0.90

#: The three verdicts. A caller may not invent a fourth.
HAS_POPULATION = "HAS_POPULATION"
THIN_POPULATION = "THIN_POPULATION"
NO_POPULATION_IN_SCOPE = "NO_POPULATION_IN_SCOPE"


class NoPopulationInScope(RuntimeError):
    """A universe was declared that does not contain enough names to trade."""


def _counts(periodic_counts: Iterable[float] | None) -> list[int]:
    if periodic_counts is None:
        raise NoPopulationInScope(
            "no per-period population counts were supplied. This guard derives "
            "the median from counts it can see and there is deliberately no "
            "argument that asserts the population is adequate — a declared "
            "population is exactly the honour-system input that fooled us once.")
    xs = [int(c) for c in periodic_counts
          if c is not None and math.isfinite(float(c))]
    if not xs:
        raise NoPopulationInScope(
            "the population counts supplied were all missing or non-finite, so "
            "the median cannot be derived. An empty count series is not an "
            "adequate population; it is an absent measurement.")
    return xs


def _median(xs: Sequence[int]) -> float:
    s = sorted(xs)
    n = len(s)
    return float(s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0)


def assess_population(scope: str, periodic_counts: Iterable[float] | None, *,
                      n_deciles: int = 10, min_names: int = 0) -> dict:
    """Median population in `scope`, and whether a sort of this shape fits it.

    `scope` is a human-readable name for the universe being claimed — it is
    carried into the verdict so the refusal names what was refused rather than
    reporting an anonymous count.

    Returns a verdict; it does not raise. `assert_population_declared` is the
    raising wrapper, because a report wants all the rows and a registration
    wants to stop.
    """
    xs = _counts(periodic_counts)
    need = max(int(min_names), int(n_deciles) * MIN_DECILE_MEMBERS)
    med = _median(xs)
    scoreable = sum(1 for c in xs if c >= need)
    share = scoreable / len(xs)
    # The two failure modes are disjoint by construction: `med >= need` holds
    # exactly when at least half the periods are scoreable, so the thin band is
    # the genuinely reachable range 0.5 <= share < MIN_SCOREABLE_SHARE.
    if med < need:
        verdict = NO_POPULATION_IN_SCOPE
    elif share < MIN_SCOREABLE_SHARE:
        verdict = THIN_POPULATION
    else:
        verdict = HAS_POPULATION
    return {
        "scope": scope,
        "verdict": verdict,
        "median_names": med,
        "median_decile_members": med / float(n_deciles) if n_deciles else med,
        "names_required": need,
        "periods": len(xs),
        "months_scoreable": scoreable,
        "share_scoreable": share,
        "reason": (f"median {med:.0f} names against {need} required; "
                   f"{scoreable} of {len(xs)} periods scoreable"),
    }


def assert_population_declared(scope: str,
                               periodic_counts: Iterable[float] | None, *,
                               n_deciles: int = 10, min_names: int = 0) -> dict:
    """Registration gate: state the population where you claim to trade.

    Raises `NoPopulationInScope` when the counts are absent, or when the
    declared universe cannot support the sort being registered. A universe that
    does not exist is not a scope error to be found afterwards.
    """
    a = assess_population(scope, periodic_counts, n_deciles=n_deciles,
                          min_names=min_names)
    if a["verdict"] == NO_POPULATION_IN_SCOPE:
        raise NoPopulationInScope(
            f"{scope}: {a['reason']}. This is NO_POPULATION_IN_SCOPE, not a "
            f"small effect — where the effect lives and where this design can "
            f"act do not intersect, and no additional data changes that.")
    return a
