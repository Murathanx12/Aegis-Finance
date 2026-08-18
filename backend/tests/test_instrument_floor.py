"""The sweep's contract: it must not manufacture floors, and must not miss them.

Every test here builds its OWN instrument out of arithmetic rather than
capturing one off the shelf. Two reasons, both paid for already: a test that
imports `bidask` measures a different world in CI than locally, and a harness
validated only against instruments that have floors would never reveal that it
puts a floor on everything.

So the suite is built around three constructed instruments whose answers are
known in advance:

    PERFECT   reads the truth exactly         -> must show NO floor
    NOISY     reads pure noise, ignores truth -> must show BLIND on every rung
    OFFSET    reads truth + 3, tiny noise     -> BIASED, but still resolves small
                                                 truths, because a deterministic
                                                 offset can be subtracted
    NOISY_NULL reads truth + |N(0,3)|         -> genuinely BLIND under ~6

The third and fourth are the pair that matters, and the harness had to earn the
distinction: **a detection floor comes from the VARIANCE of the null reading,
not from its level.** An instrument that always reads 3 too high is wrong in a
way you can correct; one whose null reading wanders over [0, 6] cannot tell 2
from nothing no matter how carefully you read it. AGK's floor is the second
kind, which is why it cannot be calibrated away with a constant.

If the harness gets any of these wrong, nothing it says about AGK or Roll is
worth reading.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from backend.services import instrument_floor as IF


def _inst(read, *, truths=(1.0, 2.0, 5.0, 10.0), null_truth=0.0, name="t",
          units="u", **kw):
    return IF.Instrument(
        name=name, read=read,
        generate=lambda truth, n, rng: (truth, n, rng),
        null_truth=null_truth, units=units, truths=truths, n_default=50, **kw)


PERFECT = _inst(lambda d: d[0], name="perfect")
NOISY = _inst(lambda d: float(d[2].normal(0.0, 1.0)), name="noisy",
              truths=(0.01, 0.02, 0.05))
OFFSET = _inst(lambda d: d[0] + 3.0 + float(d[2].normal(0.0, 0.1)),
               name="offset", truths=(0.5, 1.0, 2.0, 5.0, 10.0))
NOISY_NULL = _inst(lambda d: d[0] + abs(float(d[2].normal(0.0, 3.0))),
                   name="noisy_null", truths=(0.5, 1.0, 2.0, 5.0, 20.0, 50.0))


# ── the three controls ─────────────────────────────────────────────────────
def test_an_exact_instrument_shows_NO_floor():
    """The control that proves the harness is not manufacturing floors. If a
    perfect reader came back with a detection floor, every number in
    INSTRUMENT_FLOORS.md would be an artefact of this module."""
    prof = IF.profile_instrument(PERFECT, sims=50, measure_stability=False)
    assert prof.detection_floor == pytest.approx(0.0)
    assert prof.smallest_resolvable_truth == 1.0
    assert prof.bias_at_smallest_resolvable == pytest.approx(1.0)


def test_a_pure_noise_instrument_resolves_NOTHING_and_says_so():
    """The mirror control. An instrument that ignores its input must come back
    BLIND rather than with a plausible-looking small floor."""
    prof = IF.profile_instrument(NOISY, sims=100, measure_stability=False)
    assert prof.smallest_resolvable_truth is None
    assert "BLIND" in prof.notes or "NOTHING ON THE DECLARED LADDER" in prof.notes


def test_a_deterministic_offset_is_BIAS_and_does_not_blind_the_instrument():
    """The distinction the harness had to earn, and it corrected me on it.

    An instrument reading `truth + 3` with tiny noise still separates 0.5 from
    0.0 perfectly well — the offset is subtractable. Reporting it as a
    detection floor would condemn a merely-biased instrument as a blind one,
    and those need opposite remedies: recalibrate versus replace.
    """
    prof = IF.profile_instrument(OFFSET, sims=100, measure_stability=False)
    assert prof.null_median == pytest.approx(3.0, abs=0.3)
    resolved = [r["truth"] for r in prof.ladder if r["resolved"]]
    assert 0.5 in resolved, "a subtractable offset must not read as blindness"
    # ...and the bias IS caught, in the column that exists for it.
    row = next(r for r in prof.ladder if r["truth"] == 0.5)
    assert row["read_over_truth"] > 5.0


def test_a_NOISY_null_is_what_actually_blinds_an_instrument():
    """The mirror, and the shape AGK really has: a null reading that WANDERS.

    No constant correction recovers 2.0 from a null that ranges over [0, 6],
    which is exactly why AGK's floor cannot be calibrated away and the liquid
    segment needs a declared band instead.
    """
    prof = IF.profile_instrument(NOISY_NULL, sims=200, measure_stability=False)
    assert prof.detection_floor > 3.0
    resolved = [r["truth"] for r in prof.ladder if r["resolved"]]
    assert 0.5 not in resolved and 1.0 not in resolved
    assert 50.0 in resolved


# ── the null band is two-sided ─────────────────────────────────────────────
def test_the_null_band_is_two_sided_not_a_single_floor():
    """An absorption ratio over independent assets reads ~k/n, not zero.
    Calling that "the floor" and testing only upward would license every
    reading above it as a detection — and would miss an instrument whose
    failure is reading LOW."""
    band = IF.measure_null_band(OFFSET, sims=100)
    assert band["low"] < band["median"] < band["high"]
    assert band["low"] > 0.0, "a two-sided band around a non-zero null"


def test_a_reading_BELOW_a_non_zero_null_also_fails_to_resolve():
    prof = IF.profile_instrument(OFFSET, sims=100, measure_stability=False)
    assert prof.resolves(0.0) is True          # far below the null band
    assert prof.resolves(3.0) is False         # sitting in it


# ── the guard ──────────────────────────────────────────────────────────────
def test_a_reading_inside_the_band_is_refused_and_the_floor_is_NOT_returned():
    """The rule as code. Returning the floor here is the AGK defect: a number
    indistinguishable downstream from a measurement, systematically over-stating
    small quantities."""
    prof = IF.profile_instrument(OFFSET, sims=100, measure_stability=False)
    with pytest.raises(IF.InstrumentUnresolvable, match="UNRESOLVABLE_FOR_INPUT"):
        IF.guard_reading(prof, 3.0, n_obs=prof.n_obs)


def test_the_refusal_says_BLIND_not_SMALL():
    """The distinction the report has to carry: 'this instrument cannot see it'
    is a different claim from 'the quantity is small', and only one of them
    licenses a conclusion."""
    prof = IF.profile_instrument(OFFSET, sims=100, measure_stability=False)
    with pytest.raises(IF.InstrumentUnresolvable) as e:
        IF.guard_reading(prof, 3.0, n_obs=prof.n_obs)
    assert "does NOT mean the quantity is small" in str(e.value)


def test_a_resolvable_reading_passes_through_unchanged():
    prof = IF.profile_instrument(OFFSET, sims=100, measure_stability=False)
    assert IF.guard_reading(prof, 50.0, n_obs=prof.n_obs) == 50.0


def test_a_profile_from_a_DIFFERENT_n_is_refused_rather_than_interpolated():
    """The floor moves with sample length. Reusing one across n is correct
    arithmetic against the wrong world — the house failure mode."""
    prof = IF.profile_instrument(OFFSET, sims=50, measure_stability=False)
    with pytest.raises(IF.InstrumentUnresolvable, match="wrong world"):
        IF.guard_reading(prof, 50.0, n_obs=prof.n_obs + 1)


def test_a_non_finite_reading_is_refused():
    prof = IF.profile_instrument(PERFECT, sims=50, measure_stability=False)
    with pytest.raises(IF.InstrumentUnresolvable):
        IF.guard_reading(prof, float("nan"), n_obs=prof.n_obs)


# ── refusals at the null are counted, never dropped ────────────────────────
def test_an_instrument_that_mostly_refuses_at_the_null_is_itself_refused():
    """Dropping the failures would make a refusing instrument look like a
    confident one measured on fewer samples."""
    def _mostly_broken(d):
        raise ValueError("no")
    inst = _inst(_mostly_broken, name="broken")
    with pytest.raises(IF.InstrumentUnresolvable, match="finite reading"):
        IF.profile_instrument(inst, sims=50)


def test_a_partially_refusing_instrument_still_profiles_on_what_survived():
    calls = {"n": 0}

    def _flaky(d):
        calls["n"] += 1
        if calls["n"] % 3 == 0:
            raise ValueError("intermittent")
        return d[0]
    prof = IF.profile_instrument(_inst(_flaky, name="flaky"), sims=90,
                                 measure_stability=False)
    assert prof.smallest_resolvable_truth is not None


# ── bias is not reported across a units gap ────────────────────────────────
def test_bias_is_suppressed_when_truth_and_reading_are_different_quantities():
    """Amihud reads |r|/$vol while the truth injected is an impact coefficient.
    A ratio across that gap is a made-up number, so it is not printed."""
    inst = _inst(lambda d: d[0] * 1000.0, name="mismatched",
                 truth_units="impact coef", units="|r|/$vol")
    assert inst.bias_comparable is False
    prof = IF.profile_instrument(inst, sims=50, measure_stability=False)
    assert all(r["read_over_truth"] is None for r in prof.ladder)


def test_bias_IS_reported_when_the_units_match():
    prof = IF.profile_instrument(OFFSET, sims=100, measure_stability=False)
    assert any(r["read_over_truth"] is not None for r in prof.ladder)


# ── stabilisation ──────────────────────────────────────────────────────────
def test_an_instrument_that_never_stabilises_returns_None_not_the_largest_n():
    """None says 'not within any sample this project has'. The largest
    candidate would read as an answer."""
    got = IF.stabilisation_n(NOISY, 0.05, candidate_ns=(20, 40),
                             sims=60, tolerance=0.01)
    assert got is None


def test_a_clean_instrument_stabilises_at_the_smallest_candidate():
    got = IF.stabilisation_n(PERFECT, 5.0, candidate_ns=(20, 40), sims=40)
    assert got == 20


# ── determinism ────────────────────────────────────────────────────────────
def test_the_profile_is_reproducible_at_a_fixed_seed():
    """A floor that moves between runs is a floor nobody can cite."""
    a = IF.profile_instrument(OFFSET, sims=60, seed=99, measure_stability=False)
    b = IF.profile_instrument(OFFSET, sims=60, seed=99, measure_stability=False)
    assert a.detection_floor == b.detection_floor
    assert [r["median_read"] for r in a.ladder] == [
        r["median_read"] for r in b.ladder]


# ── the registry itself ────────────────────────────────────────────────────
def test_every_registered_instrument_declares_what_consumes_it():
    """An instrument with no named consumer is either dead code or an
    unaudited input to something, and the two need opposite remedies."""
    for name, inst in IF.INSTRUMENTS.items():
        assert inst.consumers, f"{name} names no consumer"
        assert inst.basis, f"{name} declares no simulated basis"


def test_every_registered_instrument_has_a_ladder_that_brackets_its_null():
    for name, inst in IF.INSTRUMENTS.items():
        assert inst.truths, f"{name} has no ladder"
        assert all(t != inst.null_truth for t in inst.truths), (
            f"{name} has its null value on the ladder, so one rung is asking "
            f"whether the instrument can resolve nothing from nothing")


def test_the_generators_actually_vary_with_the_truth_they_are_handed():
    """A generator that ignores its `truth` argument produces a confident
    profile of nothing, and every downstream number would be an artefact."""
    rng = np.random.default_rng(0)
    for name, inst in IF.INSTRUMENTS.items():
        lo = inst.generate(inst.truths[0], 60, np.random.default_rng(1))
        hi = inst.generate(inst.truths[-1], 60, np.random.default_rng(1))
        assert not _same(lo, hi), f"{name}'s generator ignores its truth"
    assert rng is not None


def _same(a, b) -> bool:
    if isinstance(a, dict):
        return all(_same(a[k], b[k]) for k in a)
    arr_a, arr_b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if arr_a.shape != arr_b.shape:
        return False
    return bool(np.allclose(arr_a, arr_b, equal_nan=True))


def test_the_agk_floor_reproduces_the_track_R_finding():
    """The one test that pins the harness to the result it generalises from.

    Track R measured 23-49bp on a frictionless tape by hand. If this harness
    disagrees, one of the two is wrong and the whole sweep is suspect. Skipped
    rather than faked when `bidask` is absent, because the alternative is
    asserting against a fallback estimator AGK was adopted to replace.
    """
    pytest.importorskip("bidask")
    prof = IF.profile_instrument(IF.INSTRUMENTS["agk_edge_spread"], sims=60,
                                 measure_stability=False)
    assert 15.0 < prof.detection_floor < 60.0, (
        f"harness says {prof.detection_floor:.1f}bp, Track R measured 23-49bp "
        f"by hand; a disagreement here invalidates the sweep")
    assert math.isfinite(prof.null_median)
