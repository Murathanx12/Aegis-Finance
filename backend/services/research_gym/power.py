"""How many independent observations is a row of overlapping windows worth?

WHY THIS MODULE EXISTS (G2, found by running the numbers, 2026-08-15)
=====================================================================
The Gym's base-rate table reported `n=353` for the VIX>=35 bucket and used it
as if it were 353 observations. It is 353 **daily** observations of a **63-day
forward window**. Consecutive rows share 62 of their 63 days. The 353rd row
tells you almost nothing the 352nd did not.

Measured on the real series: 349 daily observations, **17 distinct episodes**
more than 21 days apart, and an overlap-adjusted n of **5.5**. The +6.97% mean
forward return that the whole re-entry hypothesis rests on stands on something
between five and seventeen independent events -- 1998, 2001-02, 2008-09, 2010,
2011, 2015, 2018, 2020, 2022 -- not on 353.

Reporting `n` where `n_effective` is owed is not a rounding problem. It is the
difference between a row that can support an inference and a row that cannot,
and the inflated version always looks like the former.

TWO SHRINKAGES, BOTH REAL, AND THE SMALLER ONE WINS
===================================================
1. **Overlap.** H-day forward windows sampled daily carry roughly `n/H`
   independent windows. This is the standard non-overlapping-equivalent count.
2. **Episode clustering.** Stress states arrive in bursts. Sixty consecutive
   days above VIX 35 in March-May 2020 are one crisis, not sixty draws, and no
   overlap correction that only divides by H can know that.

These measure different dependencies, so `effective_n` takes the **minimum**.
Taking the larger would let whichever correction happened to be gentler set the
sample size, which is choosing the flattering denominator by construction.

AND EVERY ROW OWES AN MDE (SS19)
================================
A row without a minimum detectable effect cannot distinguish "we looked and
there is nothing there" from "we could never have seen it". Both print as a
small number with a wide interval. SS19 is a standing rule in this project
precisely because the second kept being reported as the first.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

#: Two-sided 5% and 80% power. Frozen here rather than passed around so that a
#: session cannot quietly soften the bar by moving alpha, and so the numbers in
#: any report are all the same test.
Z_ALPHA_TWO_SIDED_05 = 1.959963984540054
Z_POWER_80 = 0.8416212335729143

#: Days between two occurrences of a state before they count as separate
#: episodes. 21 trading days ~ one month: long enough that the second is not
#: simply the tail of the first, short enough that 2008 and 2009 are not fused
#: into a single "the GFC" observation.
DEFAULT_EPISODE_GAP_DAYS = 21


def overlap_effective_n(n_obs: int, horizon_days: int) -> float:
    """Non-overlapping-equivalent count for daily-sampled H-day windows."""
    if n_obs <= 0:
        return 0.0
    if horizon_days <= 1:
        return float(n_obs)
    return n_obs / float(horizon_days)


def count_episodes(positions: Sequence[int],
                   gap_days: int = DEFAULT_EPISODE_GAP_DAYS) -> int:
    """Distinct bursts in a sorted sequence of integer day positions.

    `positions` are index offsets into the underlying daily series, not dates,
    so the caller decides what a "day" is (trading days here) and this stays
    calendar-free.
    """
    pos = sorted(int(p) for p in positions)
    if not pos:
        return 0
    episodes, prev = 1, pos[0]
    for p in pos[1:]:
        if p - prev > gap_days:
            episodes += 1
        prev = p
    return episodes


def effective_n(n_obs: int, horizon_days: int, *,
                n_episodes: int | None = None) -> float:
    """The smaller of the two shrinkages, never the kinder one."""
    ov = overlap_effective_n(n_obs, horizon_days)
    if n_episodes is None:
        return ov
    return min(ov, float(n_episodes))


def mde_mean(sd: float, n_effective: float) -> float | None:
    """Smallest mean detectable at 80% power, two-sided 5%.

    Returns None below two effective observations: a "minimum detectable
    effect" computed on 1.2 windows is a number with the shape of a bound and
    none of its meaning.
    """
    if n_effective is None or n_effective < 2.0 or sd is None or sd <= 0:
        return None
    return (Z_ALPHA_TWO_SIDED_05 + Z_POWER_80) * float(sd) / math.sqrt(
        float(n_effective))


def mde_from_se(se: float | None) -> float | None:
    """Smallest effect detectable given an ALREADY-COMPUTED standard error.

    `mde_mean` is this with `se = sd / sqrt(n_effective)` folded in. It is
    separated out for §18: the minimum detectable *difference* between two
    groups is driven by the SE of the difference, `sqrt(se_a**2 + se_b**2)`,
    which no single (sd, n) pair describes.

    §18 exists because "significant in A, not significant in B" was repeatedly
    offered as evidence of conditionality. It is not — two point estimates on
    opposite sides of a threshold can easily have a difference whose interval
    covers zero. The interaction has to be tested as its own quantity, with its
    own SE and its own MDE, and this is the second half of that.
    """
    if se is None or se <= 0:
        return None
    return (Z_ALPHA_TWO_SIDED_05 + Z_POWER_80) * float(se)


def se_proportion(p: float, n_effective: float) -> float | None:
    """Standard error of a proportion at the EFFECTIVE sample size."""
    if n_effective is None or n_effective < 1.0 or p is None:
        return None
    p = min(max(float(p), 0.0), 1.0)
    return math.sqrt(max(p * (1.0 - p), 1e-12) / float(n_effective))


def mde_proportion(n_effective: float, p0: float = 0.5) -> float | None:
    """Smallest departure from `p0` detectable at 80% power, two-sided 5%."""
    se = se_proportion(p0, n_effective)
    if se is None or n_effective < 2.0:
        return None
    return (Z_ALPHA_TWO_SIDED_05 + Z_POWER_80) * se


@dataclass(frozen=True)
class Power:
    """The sample-size facts a row must print before it may be read."""
    n_obs: int
    horizon_days: int
    n_episodes: int | None
    n_effective: float
    mde_mean_pct: float | None
    mde_proportion: float | None

    @property
    def is_reportable(self) -> bool:
        """A row with no MDE is not publishable, including inside the Gym."""
        return self.mde_mean_pct is not None or self.mde_proportion is not None

    def as_dict(self) -> dict:
        return {
            "n_obs": self.n_obs,
            "horizon_days": self.horizon_days,
            "n_episodes": self.n_episodes,
            "n_effective": round(self.n_effective, 3),
            "mde_mean_pct": (None if self.mde_mean_pct is None
                             else round(self.mde_mean_pct, 3)),
            "mde_proportion": (None if self.mde_proportion is None
                               else round(self.mde_proportion, 4)),
            # Carried so a reader never has to reconstruct why n shrank.
            "note": (f"{self.n_obs} daily observations of a "
                     f"{self.horizon_days}-day window"
                     + (f" spanning {self.n_episodes} distinct episodes"
                        if self.n_episodes is not None else "")
                     + f" -> n_effective {self.n_effective:.1f}"),
        }


def power_for(n_obs: int, horizon_days: int, sd: float | None, *,
              n_episodes: int | None = None, p0: float = 0.5) -> Power:
    """Everything a base-rate or null row owes about its own sample size."""
    n_eff = effective_n(n_obs, horizon_days, n_episodes=n_episodes)
    return Power(
        n_obs=int(n_obs),
        horizon_days=int(horizon_days),
        n_episodes=n_episodes,
        n_effective=n_eff,
        mde_mean_pct=(None if sd is None else mde_mean(sd, n_eff)),
        mde_proportion=mde_proportion(n_eff, p0),
    )


def n_required_for(effect: float, sd: float) -> float | None:
    """Independent observations needed to detect `effect` at 80% power.

    The inverse of `mde_mean`, and the quantity that turns "the corpus is too
    small" from a complaint into a specification:

        n = ((Z_alpha + Z_power) * sd / effect)^2

    USE IT WITH A **DECLARED** EFFECT, NOT A MEASURED ONE (N8, 2026-08-16).
    `n` scales with the inverse SQUARE of the effect, so feeding it an effect
    estimated on two observations produces a requirement that inherits the
    effect's entire uncertainty, squared and inverted. Measured on the six
    autopsied mechanisms, the implied requirement ranged from **0.9 to 1,534
    episodes** — the sample could not determine how large a sample it needed.

    Dispersion, unlike the effect, is estimated from all the data and is
    stable. So the honest way to size a corpus is to declare the smallest edge
    worth acting on and read `n` off that. That makes corpus size a DECISION
    with a number attached, rather than a measurement of a thing too small to
    measure.
    """
    if effect is None or sd is None or sd <= 0 or abs(float(effect)) < 1e-12:
        return None
    return ((Z_ALPHA_TWO_SIDED_05 + Z_POWER_80) * float(sd)
            / abs(float(effect))) ** 2


def design_curve(sd: float,
                 effects: Sequence[float] = (1.0, 2.0, 3.0, 5.0, 10.0, 20.0)
                 ) -> dict[float, float | None]:
    """`n_required` across a grid of declared minimum effects of interest.

    Measured 2026-08-16: at the dispersion of the Gym's CRISIS slices
    (~17.7pp over the relevant windows) a 3pp edge needs **273** independent
    episodes and a 10pp edge needs **25**; at the dispersion of the CALM slices
    (~1.5pp) a 1pp edge needs **17**. The scarcity is not in history — it is
    concentrated entirely in the states with the largest dispersion, which are
    exactly the states every mechanism in the library is about.
    """
    return {float(e): n_required_for(e, sd) for e in effects}
