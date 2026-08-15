"""Market-relative stress, so a precursor can mean the same thing in two markets.

WHY (N2, measured 2026-08-16)
=============================
Every precursor in the mechanism library is written over `vix`, and exactly one
market has a VIX. N2 measured eleven international candidate transfer slices
supplying 152 stress episodes between them, and **not one of those episodes
could be evaluated by a single rule already in the library.** The atlas was
unreachable in principle, not merely uncollected — and it would have stayed
that way however much data was gathered.

The obvious substitute does not work. `realised_vol_20d` is portable as a
NUMBER and meaningless as a THRESHOLD: N2's frequency-matched bars came out at
57.3% annualised for Korea and 27.2% for Australia, so a rule reading
`realised_vol_20d >= 40` selects a country, not a state. That is the same class
of error as a rule written in a vocabulary the corpus does not speak — it
compiles, it runs, and it answers a different question in every slice.

WHAT THIS COMPUTES
==================
`stress_pctile`: where the security's own trailing realised volatility sits
within its OWN history, in [0, 1]. `>= 0.96` means "calmer than this on 96% of
days I have seen", which is the same statement everywhere, and it is the
condition the incumbent's `vix >= 35` picks out in the US (measured: VIX is at
or above 35 on 3.83% of days since 1990).

THE EXPANDING WINDOW IS NOT A DETAIL
====================================
A percentile taken against the whole sample knows the future distribution.
2008 would rank differently depending on whether 2020 had happened yet, and a
precursor built on it would be reading a summary of its own future. The rank is
therefore taken against history ONLY — everything strictly before the day being
labelled — which is also why the first `min_history` days return `None` rather
than a number: an unmeasurable state must never print as a measured one.
"""

from __future__ import annotations

from typing import Sequence

#: Days of history required before a percentile means anything. Two years: long
#: enough to have seen a stress episode, short enough that a young series is
#: not excluded forever.
MIN_HISTORY_DAYS = 504

#: Trailing window for the volatility whose rank is taken. Matches
#: `realised_vol_20d` in the shared vocabulary so the two describe the same
#: quantity at two scales.
VOL_WINDOW = 20


def realised_vol(returns: Sequence[float], window: int = VOL_WINDOW
                 ) -> list[float | None]:
    """Annualised trailing volatility, in percent. `None` before `window`."""
    import numpy as np

    r = [float(x) for x in returns]
    out: list[float | None] = []
    for i in range(len(r)):
        if i + 1 < window:
            out.append(None)
            continue
        w = r[i + 1 - window:i + 1]
        out.append(float(np.std(w, ddof=1) * np.sqrt(252) * 100.0))
    return out


def stress_pctile(vol_series: Sequence[float | None], *,
                  min_history: int = MIN_HISTORY_DAYS
                  ) -> list[float | None]:
    """Expanding-window percentile rank of each value within its own PAST.

    `out[i]` is the fraction of days STRICTLY BEFORE `i` whose volatility was
    below `vol_series[i]`. Never includes `i` itself and never includes the
    future — so a precursor reading this cannot learn the shape of a
    distribution it has not lived through.

    Returns `None` until `min_history` usable observations exist. That is the
    same rule the rest of the Gym follows: an unmeasurable state is `None`, and
    `None` is not zero.
    """
    import bisect

    vals = list(vol_series)
    seen: list[float] = []
    out: list[float | None] = []
    for v in vals:
        if v is None or v != v:
            out.append(None)
            continue
        if len(seen) < min_history:
            out.append(None)
        else:
            # Rank against history only — `seen` does not yet contain `v`.
            out.append(bisect.bisect_left(seen, float(v)) / len(seen))
        bisect.insort(seen, float(v))
    return out


def stress_state(returns: Sequence[float], *, window: int = VOL_WINDOW,
                 min_history: int = MIN_HISTORY_DAYS
                 ) -> list[dict[str, float | None]]:
    """The market-relative half of an episode's state, ready for a precursor.

    Returns one dict per day carrying `realised_vol_20d` and `stress_pctile`,
    with `None` wherever the value is not yet measurable. Callers merge this
    into whatever else the slice can supply.
    """
    vol = realised_vol(returns, window=window)
    pct = stress_pctile(vol, min_history=min_history)
    return [{"realised_vol_20d": v, "stress_pctile": p}
            for v, p in zip(vol, pct)]


#: The incumbent precursor's frequency, measured on VIX 1990-2026 in N2:
#: VIX >= 35 on 3.83% of days. A market-relative rule aiming at the same state
#: uses `stress_pctile >= 1 - 0.0383`.
INCUMBENT_STRESS_FREQUENCY = 0.038274


def frequency_matched_threshold(frequency: float = INCUMBENT_STRESS_FREQUENCY
                                ) -> float:
    """The `stress_pctile` bar that fires at a declared frequency.

    Kept as a function rather than a constant so the frequency is always
    stated at the call site. A threshold chosen to produce episodes is how a
    transfer corpus gets manufactured; a threshold chosen to produce a RATE is
    how it gets compared.
    """
    f = min(max(float(frequency), 0.0), 1.0)
    return 1.0 - f
