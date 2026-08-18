"""INSTRUMENT-FLOOR-SWEEP-1 — what each estimator can and cannot see.

    from backend.services import instrument_floor as IF
    prof = IF.profile_instrument(IF.INSTRUMENTS["roll_spread"])
    IF.guard_reading(prof, reading, n_obs=250)   # refuses below the floor

WHERE THIS CAME FROM
====================
Track R handed AGK a FRICTIONLESS synthetic tape — a tape whose true spread is
exactly zero — and the estimator read 23-49bp. That is not a bug. It is the
estimator's resolution, and it had never been measured, so a megacap's true 1-2bp
was being reported as ~15-20bp and would have moved the liquid tercile's verdicts
for a property of the instrument.

**Nothing about that method is specific to AGK.** Every estimator on the shelf
is a function from noisy data to a number, and every one of them returns
SOMETHING when handed data containing none of the quantity it measures. None of
them had been asked what that something is. So this module runs the same
procedure over the whole shelf: synthetic data with a DECLARED truth, then four
questions per instrument.

    1. THE NULL BAND      What does it read when the quantity is ABSENT?
                          Measured as a two-sided interval, not a single floor,
                          because not every instrument reads zero on null data —
                          an absorption ratio over independent assets reads
                          k/n, and calling that "zero" would license every
                          reading above it as a detection.

    2. THE RESOLVABLE     The smallest truth whose typical reading escapes the
       RANGE              null band. Below it the instrument is not wrong, it is
                          BLIND, and the two look identical in a report.

    3. BIAS IN RANGE      Inside the resolvable range, does the reading track
                          the truth or sit at a multiple of it?

    4. STABILISATION      How much data before the reading stops being about the
                          sample? Reported as the n at which the relative spread
                          of readings falls under a declared tolerance.

THE RULE THIS ENFORCES (Order 18 §4)
------------------------------------
**An instrument's floor is part of the instrument. Below it, refusal — the floor
value is never the estimate.**

`guard_reading` is that rule as code. It refuses with `UNRESOLVABLE_FOR_INPUT`
rather than returning the floor, because a floor returned as an estimate is
indistinguishable downstream from a measurement, and it is systematically WRONG
in one direction: it over-states small quantities. That is how AGK came to
over-charge megacaps tenfold while looking like an improvement.

WHAT A PROFILE IS AND IS NOT
-----------------------------
A profile is a property of THE INSTRUMENT AT A SAMPLE SIZE AND A DECLARED
MICROSTRUCTURE. It is not a property of the market. The existence of a floor and
the direction it scales are robust; the MAGNITUDE depends on the simulation, and
every profile carries `basis` saying so. `guard_reading` refuses a profile
measured at a different `n` rather than interpolating, because the floor moves
with sample length and interpolating it would be the same "correct arithmetic
against the wrong world" this whole exercise exists to catch.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import numpy as np

logger = logging.getLogger(__name__)


class InstrumentUnresolvable(RuntimeError):
    """A reading was used where the instrument cannot resolve the quantity.

    The missing input is RESOLUTION. There is data, there is a number, and the
    number is inside the range the instrument produces on data containing none
    of what it measures. Nothing downstream can tell the difference — which is
    why this is an exception rather than a warning.
    """


#: The verdict attached to a reading inside the null band.
UNRESOLVABLE_FOR_INPUT = "UNRESOLVABLE_FOR_INPUT"

#: Paths per simulated point. Enough to pin a two-sided 90% band without making
#: a profile expensive.
DEFAULT_SIMS = 200

#: The null band's coverage. A reading outside it is at least distinguishable
#: from "the quantity is absent"; it is NOT thereby accurate.
DEFAULT_NULL_QUANTILE = 0.95

#: Relative interquartile spread under which a reading is called stable.
#: DECLARED, not tuned: 0.5 means the middle half of readings spans less than
#: half the truth. Chosen before running the sweep.
DEFAULT_STABILITY_TOLERANCE = 0.5

DEFAULT_SEED = 20260818


@dataclass(frozen=True)
class Instrument:
    """An estimator, plus the synthetic world in which its answer is known.

    `generate(truth, n, rng)` must produce data in which the quantity really
    IS `truth` — that is the whole contract, and an instrument whose generator
    is wrong produces a confident profile of nothing. Each generator below says
    in its docstring what it holds fixed and what it omits, because a dimension
    a simulator does not model looks exactly like a passing test.
    """

    name: str
    read: Callable[[Any], float]
    generate: Callable[[float, int, np.random.Generator], Any]
    null_truth: float
    units: str
    truths: tuple[float, ...]
    n_default: int = 250
    higher_means_more: bool = True
    basis: str = ""
    consumers: tuple[str, ...] = ()
    #: Units of the TRUTH being injected. When these differ from `units`, the
    #: instrument is answering a different question from the one being asked of
    #: it — Amihud reads |r|/$vol while the truth injected is an impact
    #: coefficient — and a "bias" computed across that gap would be a made-up
    #: number. Resolvability still means something; the ratio does not.
    truth_units: str = ""

    @property
    def bias_comparable(self) -> bool:
        return not self.truth_units or self.truth_units == self.units


@dataclass
class FloorProfile:
    """What an instrument can see, measured rather than assumed."""

    instrument: str
    units: str
    n_obs: int
    sims: int
    null_truth: float
    null_median: float
    null_low: float
    null_high: float
    ladder: list[dict] = field(default_factory=list)
    smallest_resolvable_truth: float | None = None
    bias_at_smallest_resolvable: float | None = None
    stabilisation_n: int | None = None
    basis: str = ""
    consumers: tuple[str, ...] = ()
    notes: str = ""

    @property
    def detection_floor(self) -> float:
        """The reading below which nothing is distinguishable from absence.

        For a one-sided-up instrument this is the null band's upper edge — the
        number Track R called AGK's floor.
        """
        return self.null_high

    def resolves(self, reading: float) -> bool:
        return bool(reading > self.null_high or reading < self.null_low)

    def to_row(self) -> dict:
        return {
            "instrument": self.instrument,
            "units": self.units,
            "n_obs": self.n_obs,
            "null_truth": self.null_truth,
            "null_median": round(self.null_median, 6),
            "detection_floor": round(self.null_high, 6),
            "null_band": [round(self.null_low, 6), round(self.null_high, 6)],
            "smallest_resolvable_truth": self.smallest_resolvable_truth,
            "bias_at_smallest_resolvable": self.bias_at_smallest_resolvable,
            "stabilisation_n": self.stabilisation_n,
            "consumers": list(self.consumers),
            "basis": self.basis,
            "notes": self.notes,
        }


def _reads(inst: Instrument, truth: float, n: int, sims: int,
           seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(sims):
        try:
            v = float(inst.read(inst.generate(truth, n, rng)))
        except Exception as e:                    # noqa: BLE001
            # A refusal at the null is INFORMATION — an instrument that declines
            # to report on empty data is behaving correctly — so it is counted,
            # not dropped. Dropping would make a refusing instrument look like a
            # confident one with fewer samples.
            logger.debug("%s refused at truth=%s: %s", inst.name, truth, e)
            v = math.nan
        out.append(v)
    arr = np.asarray(out, dtype=float)
    return arr[np.isfinite(arr)]


def measure_null_band(inst: Instrument, *, n: int | None = None,
                      sims: int = DEFAULT_SIMS,
                      quantile: float = DEFAULT_NULL_QUANTILE,
                      seed: int = DEFAULT_SEED) -> dict:
    """What the instrument reads when the quantity it measures is absent."""
    n = int(n or inst.n_default)
    reads = _reads(inst, inst.null_truth, n, sims, seed)
    if reads.size < max(10, sims // 10):
        raise InstrumentUnresolvable(
            f"{inst.name}: only {reads.size}/{sims} null simulations produced a "
            f"finite reading. A null band from this few is a statement about "
            f"the simulator, and a floor derived from it would license "
            f"everything above it as a detection.")
    lo = float(np.quantile(reads, 1.0 - quantile))
    hi = float(np.quantile(reads, quantile))
    return {"median": float(np.median(reads)), "low": lo, "high": hi,
            "n_finite": int(reads.size), "quantile": quantile}


def stabilisation_n(inst: Instrument, truth: float, *,
                    candidate_ns: Sequence[int] = (60, 125, 250, 500, 1000),
                    tolerance: float = DEFAULT_STABILITY_TOLERANCE,
                    sims: int = DEFAULT_SIMS,
                    seed: int = DEFAULT_SEED) -> int | None:
    """Smallest n at which the middle half of readings spans < `tolerance`x truth.

    Returns None when no candidate qualifies — which is itself a finding, and a
    more useful one than the largest candidate would be: it says the instrument
    does not stabilise within any sample this project actually has.
    """
    scale = abs(truth - inst.null_truth) or abs(truth) or 1.0
    for n in candidate_ns:
        reads = _reads(inst, truth, int(n), sims, seed + n)
        if reads.size < max(10, sims // 10):
            continue
        iqr = float(np.quantile(reads, 0.75) - np.quantile(reads, 0.25))
        if iqr / scale < tolerance:
            return int(n)
    return None


def profile_instrument(inst: Instrument, *, n: int | None = None,
                       sims: int = DEFAULT_SIMS,
                       quantile: float = DEFAULT_NULL_QUANTILE,
                       tolerance: float = DEFAULT_STABILITY_TOLERANCE,
                       seed: int = DEFAULT_SEED,
                       measure_stability: bool = True) -> FloorProfile:
    """The four questions, answered for one instrument."""
    n = int(n or inst.n_default)
    null = measure_null_band(inst, n=n, sims=sims, quantile=quantile, seed=seed)
    prof = FloorProfile(
        instrument=inst.name, units=inst.units, n_obs=n, sims=sims,
        null_truth=inst.null_truth, null_median=null["median"],
        null_low=null["low"], null_high=null["high"],
        basis=inst.basis, consumers=inst.consumers)

    for i, truth in enumerate(inst.truths):
        reads = _reads(inst, truth, n, sims, seed + 1000 + i)
        if reads.size == 0:
            prof.ladder.append({"truth": truth, "median_read": None,
                                "resolved": False, "note": "no finite reading"})
            continue
        med = float(np.median(reads))
        resolved = prof.resolves(med)
        excess_truth = truth - inst.null_truth
        row = {
            "truth": truth,
            "median_read": round(med, 6),
            "p05": round(float(np.quantile(reads, 0.05)), 6),
            "p95": round(float(np.quantile(reads, 0.95)), 6),
            "read_over_truth": (round(med / truth, 4)
                                if truth and inst.bias_comparable else None),
            # Bias measured on the EXCESS over the null reading, which is the
            # only version that means anything when the null is not zero.
            "excess_ratio": (round((med - prof.null_median) / excess_truth, 4)
                             if excess_truth else None),
            "resolved": resolved,
        }
        prof.ladder.append(row)
        if resolved and prof.smallest_resolvable_truth is None:
            prof.smallest_resolvable_truth = truth
            prof.bias_at_smallest_resolvable = row["read_over_truth"]

    if measure_stability and prof.smallest_resolvable_truth is not None:
        # Stability is asked at the smallest RESOLVABLE truth, not the largest
        # available one: an instrument is easy to stabilise where the signal is
        # huge, and that number would flatter every instrument equally.
        prof.stabilisation_n = stabilisation_n(
            inst, prof.smallest_resolvable_truth, tolerance=tolerance,
            sims=sims, seed=seed)

    if prof.smallest_resolvable_truth is None:
        prof.notes = ("NOTHING ON THE DECLARED LADDER RESOLVED. Either the "
                      "ladder does not reach far enough or the instrument "
                      "cannot see this quantity at this n — and those are "
                      "different findings, so the ladder is printed with the "
                      "profile rather than summarised away.")
    return prof


def guard_reading(profile: FloorProfile, reading: float, *,
                  n_obs: int, label: str = "") -> float:
    """Return the reading, or REFUSE — never the floor.

    Refuses on a sample-size mismatch rather than interpolating: the floor moves
    with n, and a floor quoted at the wrong n is correct arithmetic against the
    wrong world.
    """
    if int(n_obs) != int(profile.n_obs):
        raise InstrumentUnresolvable(
            f"{profile.instrument}: profile was measured at n={profile.n_obs} "
            f"and this reading has n={n_obs}. The floor moves with sample "
            f"length, so reusing it here would be a floor quoted against the "
            f"wrong world. Re-profile at this n.")
    if not math.isfinite(reading):
        raise InstrumentUnresolvable(
            f"{profile.instrument}: non-finite reading{' for ' + label if label else ''}")
    if not profile.resolves(reading):
        raise InstrumentUnresolvable(
            f"{UNRESOLVABLE_FOR_INPUT}: {profile.instrument} read "
            f"{reading:.6g} {profile.units}{' for ' + label if label else ''}, "
            f"inside its own null band [{profile.null_low:.6g}, "
            f"{profile.null_high:.6g}] at n={profile.n_obs}. This does NOT mean "
            f"the quantity is small — it means this instrument cannot see it. "
            f"Use an upper bound or a declared band; the floor value is never "
            f"the estimate.")
    return float(reading)


# ═══════════════════════════════════════════════════════════════════════════
# The synthetic worlds. Each says what it models and what it omits.
# ═══════════════════════════════════════════════════════════════════════════

def _bounce_path(spread: float, n: int, rng: np.random.Generator,
                 sigma: float = 0.02, ticks: int = 60) -> dict:
    """Intraday random walk whose prints alternate bid/ask around the mid.

    MODELS: a known proportional spread, bid/ask bounce, realistic daily vol.
    OMITS: volume clustering, overnight gaps, time-varying spreads, informed
    flow. Each omission makes the instruments look BETTER than they are, so a
    floor measured here is a LOWER bound on the real one.
    """
    step = sigma / math.sqrt(ticks)
    p = 100.0
    o, h, lo, c = [], [], [], []
    for _ in range(n):
        inc = rng.normal(0.0, step, ticks)
        mids = p * np.exp(np.cumsum(inc))
        p = float(mids[-1])
        signs = rng.choice((-1.0, 1.0), size=ticks)
        px = mids * (1.0 + (spread / 2.0) * signs)
        o.append(float(px[0]))
        h.append(float(px.max()))
        lo.append(float(px.min()))
        c.append(float(px[-1]))
    return {"open": o, "high": h, "low": lo, "close": c}


def _returns_with_impact(lam: float, n: int, rng: np.random.Generator,
                         sigma: float = 0.02) -> dict:
    """Returns whose magnitude carries a known price-impact coefficient.

    |r_t| = sigma*|z| + lam * sqrt(v_t), with volume drawn independently of the
    noise. MODELS: a linear impact channel with a declared coefficient.
    OMITS: the endogeneity that makes real impact estimation hard — real volume
    and real volatility are jointly determined, so this generator is KINDER
    than the world.
    """
    vol = rng.lognormal(mean=math.log(1e6), sigma=0.5, size=n)
    base = np.abs(rng.normal(0.0, sigma, n))
    mag = base + lam * np.sqrt(vol)
    signs = rng.choice((-1.0, 1.0), size=n)
    r = mag * signs
    price = 100.0 * np.exp(np.cumsum(r))
    return {"returns": r, "volume": vol, "price": price}


def _roll_returns(spread: float, n: int, rng: np.random.Generator,
                  sigma: float = 0.02) -> np.ndarray:
    """Returns with bid-ask bounce of a KNOWN spread.

    Roll's estimator recovers `2*sqrt(-cov(r_t, r_{t-1}))`, and under this
    construction that quantity is exactly `spread` in expectation. MODELS: the
    bounce and an efficient-price innovation. OMITS: serial correlation in the
    efficient price itself, which biases Roll toward zero in real data.
    """
    eff = rng.normal(0.0, sigma, n + 1)
    q = rng.choice((-0.5, 0.5), size=n + 1)
    logp = np.cumsum(eff) + spread * q
    return np.diff(logp)


def _factor_returns(share: float, n: int, rng: np.random.Generator,
                    n_assets: int = 12) -> np.ndarray:
    """A panel where a known FRACTION of variance is a single common factor.

    MODELS: one factor plus idiosyncratic noise, with the factor's variance
    share declared. OMITS: multiple factors, time-varying loadings and the fat
    tails that make absorption spike in a crisis.
    """
    share = min(max(share, 0.0), 0.999)
    f = rng.normal(0.0, 1.0, n)
    loads = np.sqrt(share)
    idio = rng.normal(0.0, math.sqrt(1.0 - share), (n, n_assets))
    return (loads * f[:, None] + idio) * 0.01


def _correlated_pair(rho: float, n: int, rng: np.random.Generator) -> np.ndarray:
    """A bivariate normal pair with a KNOWN linear correlation.

    Used for the covariance/denoising instruments, where the truth is the
    correlation itself. OMITS tail dependence entirely — a Gaussian pair has
    zero asymptotic tail dependence by construction, which is exactly why it is
    the right NULL for a tail-dependence estimator.
    """
    cov = np.array([[1.0, rho], [rho, 1.0]])
    return rng.multivariate_normal([0.0, 0.0], cov, size=n) * 0.01


def _clayton_pair(lam_lower: float, n: int, rng: np.random.Generator):
    """A Clayton pair with a KNOWN lower-tail dependence coefficient.

    Clayton's lower tail dependence is `2**(-1/theta)`, so a target lambda
    inverts to `theta = -1/log2(lambda)`. lambda -> 0 means theta -> 0, which is
    the independence limit and the correct null. MODELS: asymmetric lower-tail
    dependence with an analytic truth. OMITS: upper-tail dependence and any
    time-series structure.
    """
    if lam_lower <= 0.0:
        u = rng.random(n)
        v = rng.random(n)
    else:
        theta = -1.0 / math.log2(min(lam_lower, 0.999))
        u = rng.random(n)
        w = rng.random(n)
        # Conditional inverse (Marshall-Olkin style) sampling for Clayton.
        v = ((w ** (-theta / (1.0 + theta)) - 1.0) * u ** (-theta) + 1.0
             ) ** (-1.0 / theta)
    # Map to returns through a normal quantile so downstream estimators that
    # expect returns are not handed uniforms.
    from scipy.stats import norm
    return np.column_stack([norm.ppf(np.clip(u, 1e-6, 1 - 1e-6)) * 0.01,
                            norm.ppf(np.clip(v, 1e-6, 1 - 1e-6)) * 0.01])


def _vol_path(sigma_ann: float, n: int, rng: np.random.Generator) -> np.ndarray:
    """iid returns at a KNOWN annualised volatility.

    OMITS volatility clustering, which is the whole reason GARCH exists — so a
    GARCH forecast profiled here is being asked only whether it can recover a
    CONSTANT vol, which is the easiest case it will ever see.
    """
    return rng.normal(0.0, sigma_ann / math.sqrt(252.0), n)


# ═══════════════════════════════════════════════════════════════════════════
# The shelf. Every instrument whose number feeds a gate or a report.
# ═══════════════════════════════════════════════════════════════════════════

def _read_spread(estimator: str):
    def _read(d) -> float:
        from backend.services import spread_estimators as SE
        est = SE.estimate(d["open"], d["high"], d["low"], d["close"],
                          estimator=estimator)
        return est.as_full_spread_bps()
    return _read


def _read_roll(r) -> float:
    import pandas as pd
    from backend.services.liquidity_risk import compute_roll_spread
    s = compute_roll_spread(pd.Series(r)).dropna()
    if s.empty:
        return math.nan
    return float(s.iloc[-1]) * 1e4


def _read_amihud(d) -> float:
    import pandas as pd
    from backend.services.liquidity_risk import compute_amihud_illiquidity
    s = compute_amihud_illiquidity(pd.Series(d["returns"]),
                                   pd.Series(d["volume"]),
                                   pd.Series(d["price"])).dropna()
    return float(s.iloc[-1]) if not s.empty else math.nan


def _read_kyle(d) -> float:
    import pandas as pd
    from backend.services.liquidity_risk import compute_kyle_lambda
    s = compute_kyle_lambda(pd.Series(d["returns"]),
                            pd.Series(d["volume"])).dropna()
    return float(s.iloc[-1]) if not s.empty else math.nan


def _read_absorption(panel) -> float:
    import pandas as pd
    from backend.services.systemic_risk import compute_absorption_ratio
    s = compute_absorption_ratio(pd.DataFrame(panel)).dropna()
    return float(s.iloc[-1]) if not s.empty else math.nan


def _read_mp_factor_count(panel) -> float:
    """How many eigenvalues clear the Marchenko-Pastur bound."""
    from backend.services.covariance import marchenko_pastur_bound
    x = np.asarray(panel, dtype=float)
    T, N = x.shape
    corr = np.corrcoef(x, rowvar=False)
    ev = np.linalg.eigvalsh(corr)
    return float((ev > marchenko_pastur_bound(T, N, var=1.0)).sum())


def _read_copula_lower_tail(pair) -> float:
    from backend.services.copula_tail import _to_pseudo_observations, fit_best_copula
    pseudo = _to_pseudo_observations(np.asarray(pair, dtype=float))
    fit = fit_best_copula(pseudo[:, 0], pseudo[:, 1])
    best = fit.get("best")
    return float(best.get("tail_lower", math.nan)) if best else math.nan


def _read_realized_vol(r) -> float:
    return float(np.std(np.asarray(r, dtype=float), ddof=1) * math.sqrt(252.0))


def _mp_panel(n_factors: float, n: int, rng: np.random.Generator,
              n_assets: int = 30, share_each: float = 0.15) -> np.ndarray:
    """A panel with a KNOWN number of common factors, each of declared size."""
    k = int(round(n_factors))
    out = rng.normal(0.0, 1.0, (n, n_assets))
    for _ in range(k):
        f = rng.normal(0.0, 1.0, n)
        out = out * math.sqrt(1.0 - share_each) + math.sqrt(share_each) * f[:, None]
    return out * 0.01


_SPREAD_LADDER = (1.0, 2.0, 5.0, 10.0, 25.0, 50.0, 100.0, 200.0, 400.0)

INSTRUMENTS: dict[str, Instrument] = {
    "agk_edge_spread": Instrument(
        name="agk_edge_spread", read=_read_spread("agk"),
        generate=lambda t, n, rng: _bounce_path(t / 1e4, n, rng),
        null_truth=0.0, units="bps (full spread)", truths=_SPREAD_LADDER,
        basis="bid/ask bounce, 60 prints/day, sigma=2%/day, no gaps",
        consumers=("library panel repricing", "NEURAL-RELATIVE-VALUE-1 labels",
                   "cost_model.cost_for_bars")),
    "corwin_schultz_spread": Instrument(
        name="corwin_schultz_spread", read=_read_spread("corwin_schultz"),
        generate=lambda t, n, rng: _bounce_path(t / 1e4, n, rng),
        null_truth=0.0, units="bps (full spread)", truths=_SPREAD_LADDER,
        basis="same tape as AGK — the comparator, so disagreement is measured",
        consumers=("spread comparator",)),
    "abdi_ranaldo_spread": Instrument(
        name="abdi_ranaldo_spread", read=_read_spread("abdi_ranaldo"),
        generate=lambda t, n, rng: _bounce_path(t / 1e4, n, rng),
        null_truth=0.0, units="bps (full spread)", truths=_SPREAD_LADDER,
        basis="same tape as AGK", consumers=("spread comparator",)),
    "roll_spread": Instrument(
        name="roll_spread", read=_read_roll,
        generate=lambda t, n, rng: _roll_returns(t / 1e4, n, rng),
        null_truth=0.0, units="bps (full spread)", truths=_SPREAD_LADDER,
        n_default=250,
        basis="pure bounce + efficient-price innovations, sigma=2%/day",
        consumers=("liquidity_risk.compute_liquidity_metrics",
                   "liquidity score")),
    "amihud_illiquidity": Instrument(
        name="amihud_illiquidity", read=_read_amihud,
        generate=lambda t, n, rng: _returns_with_impact(t, n, rng),
        null_truth=0.0, units="|r|/$vol x1e6", truth_units="impact coef",
        truths=(1e-9, 1e-8, 1e-7, 1e-6, 1e-5, 1e-4),
        basis="linear impact channel, lognormal volume, sigma=2%/day baseline",
        consumers=("liquidity score", "LVaR")),
    "kyle_lambda": Instrument(
        name="kyle_lambda", read=_read_kyle,
        generate=lambda t, n, rng: _returns_with_impact(t, n, rng),
        null_truth=0.0, units="return per sqrt(share)",
        truths=(1e-9, 1e-8, 1e-7, 1e-6, 1e-5, 1e-4),
        basis="the estimator's OWN specification is the generator — the "
              "kindest possible test, and it still has a floor",
        consumers=("liquidity score",)),
    "absorption_ratio": Instrument(
        name="absorption_ratio", read=_read_absorption,
        generate=lambda t, n, rng: _factor_returns(t, n, rng),
        null_truth=0.0, units="variance share in top-k",
        truth_units="true common-factor share",
        truths=(0.05, 0.10, 0.20, 0.35, 0.50, 0.70),
        n_default=300,
        basis="12 assets, one common factor of declared variance share",
        consumers=("systemic risk composite", "regime detection")),
    "mp_factor_count": Instrument(
        name="mp_factor_count", read=_read_mp_factor_count,
        generate=_mp_panel, null_truth=0.0, units="eigenvalues above MP bound",
        truth_units="true factors injected",
        truths=(1.0, 2.0, 3.0, 5.0), n_default=250,
        basis="30 assets, each injected factor carrying 15% of variance",
        consumers=("denoised covariance", "portfolio optimiser inputs")),
    "copula_lower_tail": Instrument(
        name="copula_lower_tail", read=_read_copula_lower_tail,
        generate=_clayton_pair, null_truth=0.0,
        units="lambda_lower", truths=(0.05, 0.10, 0.20, 0.35, 0.50),
        n_default=500,
        basis="Clayton with analytic lambda_L = 2^(-1/theta); null is "
              "independence, which has zero asymptotic tail dependence",
        consumers=("tail dependence report", "contagion analysis")),
    "realized_vol": Instrument(
        name="realized_vol", read=_read_realized_vol, generate=_vol_path,
        null_truth=0.02, units="annualised vol",
        truths=(0.05, 0.10, 0.15, 0.25, 0.40), n_default=250,
        basis="iid normal returns at a constant annualised vol — INCLUDED AS "
              "THE CONTROL: an instrument with no floor problem, so the table "
              "reports a shelf rather than an indictment",
        consumers=("vol cone", "GARCH forecast baseline", "risk number")),
}
