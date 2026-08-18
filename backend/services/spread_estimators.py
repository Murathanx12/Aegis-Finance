"""Bid-ask spread from daily OHLC — and the convention that decides what it means.

    from backend.services import spread_estimators as SE
    est = SE.estimate(open_, high, low, close, estimator="agk")
    cost_bps = est.as_one_way_bps()      # THE conversion. It refuses if unsure.

WHY THE CONVENTION AUDIT COMES FIRST (Order 16 item 11, Order 17 P0-R2)
=======================================================================
Better spread data pushed through a factor-of-two convention error is the
two-wrong-constants house failure with a citation attached. So this module
answers the convention question before it offers a number, and the answer is
enforced by a type rather than described in a docstring somebody will skim.

THE THREE QUANTITIES, AND THEY ARE NOT INTERCHANGEABLE
------------------------------------------------------
    S            the PROPORTIONAL EFFECTIVE SPREAD. Ask minus bid over the
                 midpoint. This is what all three estimators below return.
    S / 2        the ONE-WAY cost: what it costs to cross once, because a
                 buyer pays half the spread above the mid and a seller pays
                 half below.
    S            the ROUND-TRIP cost — buy then sell — which is numerically
                 S again, and that coincidence is exactly why this is easy to
                 get wrong. `S` is both "the spread" and "the round trip", so a
                 reader who has one in mind will read a number meant as the
                 other and nothing will look strange.

WHAT AEGIS'S COST MODEL ACTUALLY EXPECTS — AUDITED, NOT ASSUMED
---------------------------------------------------------------
`scripts/library_measure_2006_2019.py` is where the 206-predictor panel's cost
is charged, and the two lines that decide it are:

    turn[t] = float(np.abs(w - w_prev).sum())        # line 191
    cost_m  = turn_m * COST_BPS_ONE_WAY / 1e4        # line 206

`sum(|Δw|)` counts BOTH LEGS of a rotation: selling A and buying B on equal
weights contributes 1.0 + 1.0 = 2.0. So the notional in `turn` is total notional
crossed on both sides, and each unit of it is charged `COST_BPS` exactly once.

    ⇒ COST_BPS IS A ONE-WAY RATE. It is the HALF-SPREAD in basis points.

Therefore setting `COST_BPS` to an estimator's output — which is `S`, the full
spread — **charges twice the true cost**. On the panel that is not a rounding
error: the survivor count already moves 4 → 3 → 1 → 0 across 0/5/10/20bp, so a
factor of two moves a verdict by two whole steps of that grid.

This is stated here and PROVEN in `test_spread_estimators.py`, which builds
price paths with a known spread and checks each estimator recovers `S` rather
than `S/2`. A convention claim that is only asserted is the honour system.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Sequence

logger = logging.getLogger(__name__)

#: The proportional effective spread itself: (ask - bid) / mid. What every
#: estimator in this module returns.
CONVENTION_FULL_SPREAD = "proportional_effective_spread"

#: Cost of crossing ONCE = S / 2. What Aegis's turnover-based cost model wants,
#: because its turnover already counts both legs.
CONVENTION_ONE_WAY = "one_way_cost"

#: Cost of a buy followed by a sell = S. Numerically equal to the full spread,
#: which is precisely why it needs its own name.
CONVENTION_ROUND_TRIP = "round_trip_cost"

_CONVENTIONS = (CONVENTION_FULL_SPREAD, CONVENTION_ONE_WAY,
                CONVENTION_ROUND_TRIP)

#: Multiplier from each convention to the ONE-WAY cost.
_TO_ONE_WAY = {
    CONVENTION_FULL_SPREAD: 0.5,
    CONVENTION_ONE_WAY: 1.0,
    CONVENTION_ROUND_TRIP: 0.5,
}


class SpreadConventionError(RuntimeError):
    """A spread was used without a declared, known convention.

    The missing input is the CONVENTION, and it is the one input whose absence
    looks exactly like agreement: every convention is a positive number of
    basis points, so a wrong one produces a plausible cost, a plausible net
    return and a plausible survivor count. Nothing downstream can detect it.

    Also raised when an estimator is handed too few observations to estimate
    anything — a spread computed from four days is a number about the sample.
    """


#: Below this many usable observations an estimate is refused rather than
#: returned noisy. Declared, not tuned: the estimators are moment-based and
#: their sampling error at n < 20 is comparable to the quantity itself.
MIN_OBS = 20


@dataclass(frozen=True)
class SpreadEstimate:
    """A spread that cannot be used without saying what it is.

    `value` is meaningless without `convention`, so they travel together and
    the conversion goes through a method rather than a multiplication somebody
    writes at the call site. That is the whole design: the factor of two is
    applied in ONE place, by code that knows which direction it is going.
    """

    value: float
    convention: str
    estimator: str
    n_obs: int
    note: str = ""

    def __post_init__(self) -> None:
        if self.convention not in _CONVENTIONS:
            raise SpreadConventionError(
                f"unknown convention {self.convention!r}; expected one of "
                f"{_CONVENTIONS}. A spread without a declared convention is a "
                f"number that will be read as whichever one the reader had in "
                f"mind, and every reading produces a plausible cost.")

    def as_one_way_bps(self) -> float:
        """Basis points per unit of notional crossed ONCE.

        This is the number Aegis's cost model wants, because its turnover is
        `sum(|dw|)` and already counts both legs of a rotation.
        """
        return _TO_ONE_WAY[self.convention] * self.value * 1e4

    def as_round_trip_bps(self) -> float:
        return 2.0 * self.as_one_way_bps()

    def as_full_spread_bps(self) -> float:
        return 2.0 * self.as_one_way_bps()


def _clean(*series: Sequence[float]) -> list[list[float]]:
    cols = [list(map(float, s)) for s in series]
    n = min(len(c) for c in cols)
    if n < MIN_OBS:
        raise SpreadConventionError(
            f"{n} observations is below the declared minimum of {MIN_OBS}. A "
            f"moment-based spread estimate from this few days has sampling "
            f"error comparable to the quantity itself — it is a number about "
            f"the sample, not about the security.")
    return [c[:n] for c in cols]


def corwin_schultz(high: Sequence[float], low: Sequence[float]) -> SpreadEstimate:
    """Corwin & Schultz (2012), from consecutive high-low ranges.

    Kept as a COMPARATOR, not as the primary. Its known downward bias under
    infrequent trading is exactly the regime the small/mid-cap panel lives in,
    which is why AGK supersedes it — but a comparator that disagrees is how the
    supersession stops being a citation and becomes a measurement.
    """
    h, lo = _clean(high, low)
    k = 3.0 - 2.0 * math.sqrt(2.0)
    vals = []
    for t in range(len(h) - 1):
        if min(lo[t], lo[t + 1]) <= 0 or min(h[t], h[t + 1]) <= 0:
            continue
        b = (math.log(h[t] / lo[t]) ** 2) + (math.log(h[t + 1] / lo[t + 1]) ** 2)
        g = math.log(max(h[t], h[t + 1]) / min(lo[t], lo[t + 1])) ** 2
        a = (math.sqrt(2.0 * b) - math.sqrt(b)) / k - math.sqrt(g / k)
        s = 2.0 * (math.exp(a) - 1.0) / (1.0 + math.exp(a))
        vals.append(s)
    if not vals:
        raise SpreadConventionError("no usable high/low pairs")
    # Negative daily estimates are set to zero BEFORE averaging, which is the
    # authors' own convention. Averaging the negatives instead would report a
    # spread biased toward zero on exactly the illiquid names where the
    # estimator is already known to be low.
    m = sum(max(0.0, v) for v in vals) / len(vals)
    return SpreadEstimate(value=m, convention=CONVENTION_FULL_SPREAD,
                          estimator="corwin_schultz", n_obs=len(vals),
                          note="negative daily estimates floored at 0 per the "
                               "authors' convention")


def abdi_ranaldo(high: Sequence[float], low: Sequence[float],
                 close: Sequence[float]) -> SpreadEstimate:
    """Abdi & Ranaldo (2017), close vs the high-low midrange."""
    h, lo, c = _clean(high, low, close)
    eta = [(math.log(hi) + math.log(lo_)) / 2.0 for hi, lo_ in zip(h, lo)]
    cl = [math.log(x) for x in c]
    prods = [(cl[t] - eta[t]) * (cl[t] - eta[t + 1]) for t in range(len(cl) - 1)]
    if not prods:
        raise SpreadConventionError("no usable observations")
    mean = sum(prods) / len(prods)
    # A negative mean is a legitimate small-sample outcome and the estimator is
    # undefined there; floored at zero rather than returning a NaN that would
    # propagate into a cost silently.
    return SpreadEstimate(value=2.0 * math.sqrt(max(0.0, mean)),
                          convention=CONVENTION_FULL_SPREAD,
                          estimator="abdi_ranaldo", n_obs=len(prods))


def edge_agk(open_: Sequence[float], high: Sequence[float],
             low: Sequence[float], close: Sequence[float]) -> SpreadEstimate:
    """Ardia, Guidotti & Kroencke (2024) — the EDGE estimator. The PRIMARY.

    Uses the authors' own `bidask` package rather than a reimplementation.
    Order 16 named it, and the reason is the one this module exists for: a
    hand-rolled GMM estimator that is subtly wrong produces a plausible number,
    and there is nothing downstream that would notice.

    Missing package is a REFUSAL, not a silent fallback to Corwin-Schultz. The
    fallback would be the estimator AGK was adopted to replace, quietly
    supplying the numbers the replacement was supposed to correct.
    """
    o, h, lo, c = _clean(open_, high, low, close)
    try:
        from bidask import edge
    except ImportError as e:
        raise SpreadConventionError(
            f"the `bidask` package (Ardia-Guidotti-Kroencke) is not installed "
            f"({e}). This refuses rather than falling back to Corwin-Schultz: "
            f"the fallback is the estimator AGK was adopted to REPLACE, and it "
            f"would quietly supply the numbers the replacement exists to "
            f"correct.") from e
    val = float(edge(o, h, lo, c))
    if not math.isfinite(val):
        raise SpreadConventionError(
            "the AGK estimator returned a non-finite value; a NaN propagated "
            "into a cost model becomes a silently-zero or silently-infinite "
            "trading cost")
    return SpreadEstimate(value=max(0.0, val), convention=CONVENTION_FULL_SPREAD,
                          estimator="agk_edge", n_obs=len(c),
                          note="Ardia-Guidotti-Kroencke (2024), via the "
                               "authors' `bidask` package")


ESTIMATORS = {"agk": edge_agk, "corwin_schultz": corwin_schultz,
              "abdi_ranaldo": abdi_ranaldo}


# ── the estimator's own detection floor, measured rather than assumed ──────
#: Paths per floor simulation. Enough to pin a high quantile without making an
#: estimate expensive; seeded, so the floor is reproducible.
FLOOR_SIMS = 200
FLOOR_QUANTILE = 0.95


def noise_floor_bps(n_obs: int, sigma_daily: float, *, sims: int = FLOOR_SIMS,
                    quantile: float = FLOOR_QUANTILE, seed: int = 20260818,
                    ticks: int = 60) -> dict:
    """What AGK reads on a ZERO-spread tape at this sample size and volatility.

    MEASURED HERE BECAUSE IT IS LARGE AND NOBODY HAD LOOKED. On simulated
    frictionless bars the estimator returns a positive number that rises with
    volatility and falls with sample length — roughly 10-28bp of apparent full
    spread at realistic values. A true 10bp spread reads 15-18bp, i.e. the
    floor dominates the signal.

    The consequence is specific and it points the opposite way from the flat-bp
    problem the panel already knows about:

      * ILLIQUID names: a flat 10bp under-charges, which flatters the
        "larger in the illiquid tercile" verdicts. Known, and why AGK was
        adopted.
      * LIQUID names: AGK OVER-charges. A megacap's true spread is 1-2bp and
        the estimator cannot see below its own floor, so it reports ~15-20bp
        and the cost model would charge roughly ten times the truth.

    So an AGK estimate near the floor is an UPPER BOUND, not a measurement,
    and a panel repriced with it would move the liquid tercile's verdicts for a
    reason that is an artefact of the instrument. That is the same shape as
    charging illiquid names the megacap rate, which flipped two of our own
    verdicts — the instrument correcting one end while breaking the other.

    Derived, not declared: it is simulated at the caller's OWN `n_obs` and
    realized `sigma_daily`, which are both observable from the bars being
    estimated. A constant here would be a number quoted from one afternoon's
    experiment and applied to every security forever.
    """
    import random as _random

    if n_obs < MIN_OBS or not (sigma_daily > 0):
        raise SpreadConventionError(
            f"a detection floor needs n_obs >= {MIN_OBS} and a positive daily "
            f"volatility; got n_obs={n_obs}, sigma={sigma_daily}. Returning a "
            f"floor of zero would license every estimate as resolvable.")
    try:
        from bidask import edge
    except ImportError as e:
        raise SpreadConventionError(
            f"cannot measure the AGK detection floor without `bidask` ({e})"
        ) from e

    rng = _random.Random(seed)
    step = float(sigma_daily) / math.sqrt(ticks)
    reads = []
    for _ in range(sims):
        p, o, h, l_, c = 100.0, [], [], [], []
        for _ in range(int(n_obs)):
            px = []
            for _ in range(ticks):
                p *= math.exp(rng.gauss(0.0, step))
                px.append(p)
            o.append(px[0])
            h.append(max(px))
            l_.append(min(px))
            c.append(px[-1])
        v = float(edge(o, h, l_, c))
        reads.append(v if math.isfinite(v) else 0.0)
    reads.sort()
    idx = min(len(reads) - 1, int(quantile * len(reads)))
    return {"floor_full_spread_bps": round(max(0.0, reads[idx]) * 1e4, 3),
            "median_full_spread_bps": round(
                max(0.0, reads[len(reads) // 2]) * 1e4, 3),
            "quantile": quantile, "sims": sims, "n_obs": int(n_obs),
            "sigma_daily": float(sigma_daily),
            "basis": "SIMULATED_ZERO_SPREAD_AT_THIS_N_AND_VOLATILITY"}


def realized_daily_sigma(close: Sequence[float]) -> float:
    """Close-to-close daily volatility — the floor simulation's other input."""
    c = [float(x) for x in close if float(x) > 0]
    if len(c) < 3:
        raise SpreadConventionError("need at least 3 closes for a volatility")
    r = [math.log(c[i] / c[i - 1]) for i in range(1, len(c))]
    mu = sum(r) / len(r)
    return math.sqrt(sum((x - mu) ** 2 for x in r) / (len(r) - 1))


def estimate_with_floor(open_: Sequence[float], high: Sequence[float],
                        low: Sequence[float], close: Sequence[float], *,
                        estimator: str = "agk", **floor_kw) -> dict:
    """An AGK estimate together with the floor that says whether to believe it.

    `resolvable` is False when the estimate sits at or below the estimator's
    own zero-spread reading. A `False` here does NOT mean the spread is zero —
    it means daily OHLC cannot see it, and the number should be used as an
    upper bound or replaced by a better instrument (TAQ effective spreads).
    """
    est = estimate(open_, high, low, close, estimator=estimator)
    sigma = realized_daily_sigma(close)
    floor = noise_floor_bps(est.n_obs, sigma, **floor_kw)
    val = est.as_full_spread_bps()
    return {
        "estimator": est.estimator,
        "convention": est.convention,
        "full_spread_bps": round(val, 3),
        "one_way_bps": round(est.as_one_way_bps(), 3),
        "floor": floor,
        "resolvable": bool(val > floor["floor_full_spread_bps"]),
        "interpretation": (
            "above the estimator's zero-spread floor — usable as a measurement"
            if val > floor["floor_full_spread_bps"] else
            "AT OR BELOW the estimator's own floor: daily OHLC cannot resolve "
            "this spread. Use it as an UPPER BOUND, not a cost. This is the "
            "expected state for megacaps, whose true spreads are 1-2bp."),
    }


def estimate(open_: Sequence[float], high: Sequence[float],
             low: Sequence[float], close: Sequence[float], *,
             estimator: str = "agk") -> SpreadEstimate:
    if estimator not in ESTIMATORS:
        raise SpreadConventionError(
            f"unknown estimator {estimator!r}; have {sorted(ESTIMATORS)}")
    if estimator == "agk":
        return edge_agk(open_, high, low, close)
    if estimator == "corwin_schultz":
        return corwin_schultz(high, low)
    return abdi_ranaldo(high, low, close)


def compare_all(open_: Sequence[float], high: Sequence[float],
                low: Sequence[float], close: Sequence[float]) -> dict:
    """All three on the same bars. Disagreement is the finding, not a problem.

    Order 16: the winner is frozen by size/liquidity segment BEFORE any
    repricing. This function is what that freezing reads; it does not choose.
    """
    out: dict = {}
    for name in ESTIMATORS:
        try:
            est = estimate(open_, high, low, close, estimator=name)
            out[name] = {"full_spread_bps": round(est.as_full_spread_bps(), 3),
                         "one_way_bps": round(est.as_one_way_bps(), 3),
                         "n_obs": est.n_obs, "convention": est.convention}
        except SpreadConventionError as e:
            # Named, never dropped. An estimator missing from a comparison
            # table reads as "we tried three and they agreed".
            out[name] = {"refused": str(e)}
    return out


def one_way_bps_for_turnover(est: SpreadEstimate) -> float:
    """The single sanctioned bridge into Aegis's turnover-based cost model.

    Exists so the factor of two is applied in ONE place with a name attached,
    rather than at each call site by whoever last read a paper. See the module
    docstring for the audit: `turn = sum(|dw|)` counts both legs, so the rate
    charged against it is the ONE-WAY cost, which is HALF the spread.
    """
    return est.as_one_way_bps()
