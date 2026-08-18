"""The convention claim, proven on price paths whose spread we chose.

A convention that is only asserted is the honour system: every reading of a
spread produces a positive number of basis points, so a wrong one yields a
plausible cost, a plausible net return and a plausible survivor count, and
nothing downstream can detect it.

So the central test here builds bars from an efficient price plus a KNOWN
bid-ask spread and checks each estimator recovers `S` — the full proportional
spread — and not `S/2`. That is what licenses the halving in `as_one_way_bps`,
and it is the difference between "we read the paper" and "we checked".
"""

from __future__ import annotations

import math
import random

import pytest

from backend.services import spread_estimators as SE


# ── a market whose spread we chose ─────────────────────────────────────────
def _bars(n_days: int = 400, spread: float = 0.01, sigma: float = 0.02,
          ticks: int = 60, seed: int = 11):
    """Daily OHLC from an efficient random walk plus a fixed proportional spread.

    Each observed transaction sits half a spread above or below the efficient
    price with equal probability — the standard Roll setup. So the OBSERVED
    range is inflated by the spread, which is the signal all three estimators
    read, and the ground truth is exactly `spread`.
    """
    rng = random.Random(seed)
    p = 100.0
    o, h, lo, c = [], [], [], []
    step = sigma / math.sqrt(ticks)
    for _ in range(n_days):
        prices = []
        for _ in range(ticks):
            p *= math.exp(rng.gauss(0.0, step))
            q = 1.0 if rng.random() < 0.5 else -1.0
            prices.append(p * (1.0 + q * spread / 2.0))
        o.append(prices[0])
        h.append(max(prices))
        lo.append(min(prices))
        c.append(prices[-1])
    return o, h, lo, c


@pytest.mark.parametrize("true_spread", [0.005, 0.01, 0.02])
def test_agk_recovers_the_full_spread_not_the_half_spread(true_spread):
    """THE TEST THE WHOLE MODULE RESTS ON.

    If the estimator returned the half-spread, `as_one_way_bps` would halve it
    again and every cost in Aegis would be half what it should be. If it
    returns the full spread — as this asserts — the halving is correct.
    """
    o, h, lo, c = _bars(spread=true_spread, seed=hash(true_spread) % 10_000)
    est = SE.edge_agk(o, h, lo, c)
    assert est.convention == SE.CONVENTION_FULL_SPREAD
    # Recovers S, within estimator noise.
    assert est.value == pytest.approx(true_spread, rel=0.35), (
        f"AGK returned {est.value:.5f} for a true spread of {true_spread}")
    # And is emphatically NOT the half-spread — the alternative reading.
    assert abs(est.value - true_spread) < abs(est.value - true_spread / 2.0)


@pytest.mark.parametrize("estimator", ["agk", "corwin_schultz", "abdi_ranaldo"])
def test_every_estimator_declares_the_same_convention(estimator):
    """Three papers, one quantity. If they disagreed on the convention, the
    comparison table would be comparing different things while looking like a
    disagreement about liquidity."""
    o, h, lo, c = _bars(spread=0.01)
    est = SE.estimate(o, h, lo, c, estimator=estimator)
    assert est.convention == SE.CONVENTION_FULL_SPREAD
    assert est.value == pytest.approx(0.01, rel=0.6)


def test_a_zero_spread_market_still_reads_positive_and_that_is_the_floor():
    """THE NEGATIVE CONTROL, AND IT FAILS IN AN INFORMATIVE DIRECTION.

    AGK does not read zero on a frictionless tape — it reads 10-28bp depending
    on sample length and volatility. That is not a bug to threshold away; it is
    the estimator's DETECTION FLOOR, and it decides which securities daily OHLC
    can say anything about at all.

    The consequence points the OPPOSITE way from the flat-bp problem the panel
    already knows about: a flat 10bp under-charges illiquid names, and AGK
    OVER-charges liquid ones, because a megacap's true 1-2bp sits far below
    this floor.
    """
    o, h, lo, c = _bars(spread=0.0, sigma=0.03, seed=5)
    est = SE.edge_agk(o, h, lo, c)
    assert est.value > 0.0, "a zero reading would hide the floor entirely"
    floor = SE.noise_floor_bps(est.n_obs, SE.realized_daily_sigma(c), sims=40)
    assert est.as_full_spread_bps() <= floor["floor_full_spread_bps"] * 1.5, (
        "a zero-spread tape must read at or near the measured floor")


def test_the_floor_falls_with_sample_length():
    """Derived from the caller's own n, so it must actually move with it — a
    'floor' that ignored sample size would be a constant with a function's
    name."""
    hi = SE.noise_floor_bps(250, 0.02, sims=40)["floor_full_spread_bps"]
    lo = SE.noise_floor_bps(1000, 0.02, sims=40)["floor_full_spread_bps"]
    assert lo < hi


def test_the_floor_rises_with_volatility():
    quiet = SE.noise_floor_bps(400, 0.01, sims=40)["floor_full_spread_bps"]
    loud = SE.noise_floor_bps(400, 0.04, sims=40)["floor_full_spread_bps"]
    assert loud > quiet


def test_a_megacap_spread_is_declared_UNRESOLVABLE_not_reported_as_a_cost():
    """The finding that matters for repricing the panel.

    A true 1bp spread is far below the floor, so AGK reports the floor. Using
    that as a cost would charge a megacap roughly ten times the truth — the
    same shape of error as charging illiquid names the megacap rate, which
    already flipped two of our own verdicts, running the other way.
    """
    o, h, lo, c = _bars(spread=0.0001, sigma=0.02, n_days=300, seed=9)
    out = SE.estimate_with_floor(o, h, lo, c, sims=40)
    assert out["resolvable"] is False
    assert "UPPER BOUND" in out["interpretation"]
    assert out["full_spread_bps"] > 1.0, (
        "the estimator reads its floor, far above the true 1bp")


def test_a_wide_spread_is_resolvable():
    o, h, lo, c = _bars(spread=0.02, sigma=0.02, n_days=300, seed=9)
    out = SE.estimate_with_floor(o, h, lo, c, sims=40)
    assert out["resolvable"] is True
    assert out["one_way_bps"] == pytest.approx(out["full_spread_bps"] / 2)


def test_a_floor_cannot_be_computed_from_nothing():
    with pytest.raises(SE.SpreadConventionError, match="detection floor needs"):
        SE.noise_floor_bps(5, 0.02, sims=5)
    with pytest.raises(SE.SpreadConventionError, match="detection floor needs"):
        SE.noise_floor_bps(400, 0.0, sims=5)


def test_the_estimate_scales_with_the_true_spread():
    """Not just close on one value — MONOTONE, so it is measuring the spread
    rather than happening to land near a constant."""
    vals = [SE.edge_agk(*_bars(spread=s, seed=3)).value
            for s in (0.002, 0.008, 0.02)]
    assert vals[0] < vals[1] < vals[2]


# ── the conversion, which is the whole point ───────────────────────────────
def test_one_way_is_half_the_spread_and_round_trip_is_the_whole_one():
    est = SE.SpreadEstimate(value=0.0020, convention=SE.CONVENTION_FULL_SPREAD,
                            estimator="t", n_obs=100)
    assert est.as_full_spread_bps() == pytest.approx(20.0)
    assert est.as_one_way_bps() == pytest.approx(10.0)
    assert est.as_round_trip_bps() == pytest.approx(20.0)


def test_the_round_trip_and_the_full_spread_coincide_and_that_is_the_trap():
    """They are numerically equal, which is exactly why each needs its own
    name: a reader with one in mind will read a number meant as the other and
    nothing will look strange."""
    est = SE.SpreadEstimate(value=0.003, convention=SE.CONVENTION_FULL_SPREAD,
                            estimator="t", n_obs=100)
    assert est.as_round_trip_bps() == est.as_full_spread_bps()
    assert est.as_one_way_bps() * 2 == pytest.approx(est.as_round_trip_bps())


def test_a_one_way_estimate_is_not_halved_again():
    """The bug this design prevents: applying the factor of two twice because
    two different call sites each 'knew' the convention."""
    est = SE.SpreadEstimate(value=0.0010, convention=SE.CONVENTION_ONE_WAY,
                            estimator="t", n_obs=100)
    assert est.as_one_way_bps() == pytest.approx(10.0)
    assert est.as_full_spread_bps() == pytest.approx(20.0)


def test_an_undeclared_convention_is_refused():
    """The missing input whose absence looks exactly like agreement."""
    with pytest.raises(SE.SpreadConventionError, match="unknown convention"):
        SE.SpreadEstimate(value=0.001, convention="whatever", estimator="t",
                          n_obs=100)
    with pytest.raises(SE.SpreadConventionError, match="unknown convention"):
        SE.SpreadEstimate(value=0.001, convention="", estimator="t", n_obs=100)


def test_too_few_observations_is_refused_not_returned_noisy():
    o, h, lo, c = _bars(n_days=8, spread=0.01)
    with pytest.raises(SE.SpreadConventionError, match="below the declared"):
        SE.edge_agk(o, h, lo, c)


def test_a_missing_bidask_package_refuses_rather_than_falling_back(monkeypatch):
    """A fallback to Corwin-Schultz would be the estimator AGK was adopted to
    REPLACE, quietly supplying the numbers the replacement exists to correct."""
    import builtins
    real_import = builtins.__import__

    def _no_bidask(name, *a, **k):
        if name == "bidask":
            raise ImportError("simulated absence")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _no_bidask)
    o, h, lo, c = _bars(spread=0.01)
    with pytest.raises(SE.SpreadConventionError, match="adopted to REPLACE"):
        SE.edge_agk(o, h, lo, c)


# ── the comparison table ───────────────────────────────────────────────────
def test_compare_all_names_a_refusal_instead_of_dropping_it():
    """An estimator missing from a comparison table reads as 'we tried three
    and they agreed'."""
    o, h, lo, c = _bars(spread=0.01)
    out = SE.compare_all(o[:5], h[:5], lo[:5], c[:5])
    assert set(out) == set(SE.ESTIMATORS)
    assert all("refused" in v for v in out.values())


def test_compare_all_reports_all_three_on_good_data():
    o, h, lo, c = _bars(spread=0.01)
    out = SE.compare_all(o, h, lo, c)
    assert set(out) == set(SE.ESTIMATORS)
    for name, v in out.items():
        assert "refused" not in v, f"{name}: {v}"
        assert v["convention"] == SE.CONVENTION_FULL_SPREAD
        assert v["one_way_bps"] == pytest.approx(v["full_spread_bps"] / 2)


def test_corwin_schultz_reads_lower_than_agk_on_an_illiquid_tape():
    """The documented CS downward bias under infrequent trading, reproduced.

    This is why AGK supersedes it and why the panel's illiquid tercile is the
    cell most exposed to the old estimator: a tape with long flat stretches is
    exactly where CS under-reads, and under-reading cost in the illiquid tercile
    flatters precisely the 'larger in the illiquid tercile' claim the panel
    made.
    """
    rng = random.Random(7)
    o, h, lo, c = _bars(spread=0.02, ticks=60, seed=7)
    # Freeze most days to one print: infrequent trading, so H == L == O == C.
    for i in range(len(c)):
        if rng.random() < 0.6:
            o[i] = h[i] = lo[i] = c[i] = c[i]
    cs = SE.corwin_schultz(h, lo).value
    agk = SE.edge_agk(o, h, lo, c).value
    assert cs < agk, f"CS {cs:.5f} was not below AGK {agk:.5f}"
