"""N23's guard: a universe must state its population where it claims to trade."""

from __future__ import annotations

import pytest

from backend.services.research_gym.population import (HAS_POPULATION,
                                                      MIN_DECILE_MEMBERS,
                                                      NO_POPULATION_IN_SCOPE,
                                                      THIN_POPULATION,
                                                      NoPopulationInScope,
                                                      assert_population_declared,
                                                      assess_population)


# ── the refusals (Order 8's contract: a missing input must refuse) ──────────
def test_no_counts_at_all_refuses_rather_than_assuming_a_population():
    with pytest.raises(NoPopulationInScope, match="honour-system"):
        assess_population("some universe", None)


def test_all_missing_counts_refuse_rather_than_reading_as_zero_or_as_fine():
    with pytest.raises(NoPopulationInScope, match="absent measurement"):
        assess_population("some universe", [float("nan"), None])


def test_there_is_no_argument_that_asserts_the_population_is_adequate():
    """The whole point: the median is DERIVED, never accepted."""
    import inspect
    sig = inspect.signature(assess_population)
    assert "periodic_counts" in sig.parameters
    banned = {"median_names", "declared_median", "population", "assume_ok"}
    assert not (banned & set(sig.parameters))


# ── the verdict, which is arithmetic ───────────────────────────────────────
def test_std_turns_actual_numbers_reproduce_the_verdict_that_was_found_by_luck():
    """Two names a month in the liquid tercile, 167 months, ten deciles."""
    a = assess_population("std_turn @ liquid", [2] * 167, n_deciles=10,
                          min_names=100)
    assert a["verdict"] == NO_POPULATION_IN_SCOPE
    assert a["months_scoreable"] == 0
    with pytest.raises(NoPopulationInScope, match="not a small effect"):
        assert_population_declared("std_turn @ liquid", [2] * 167,
                                   n_deciles=10, min_names=100)


def test_a_real_survivor_passes_so_the_guard_is_not_a_blanket_no():
    a = assess_population("ShareIss5Y @ liquid", [688] * 167, n_deciles=10,
                          min_names=100)
    assert a["verdict"] == HAS_POPULATION
    assert assert_population_declared("ShareIss5Y @ liquid", [688] * 167,
                                      n_deciles=10, min_names=100)


def test_a_universe_that_disappears_in_a_large_minority_of_months_is_THIN():
    """Scoreable in the median month is a different fact from scoreable.

    The band exists because `med >= need` holds exactly when half the periods
    clear it, so the only reachable "thin" case is a comfortable median with an
    uncomfortable share — 100 of 167 months here, not the 90% a design needs.
    """
    counts = [500] * 100 + [3] * 67
    a = assess_population("intermittent @ liquid", counts, n_deciles=10,
                          min_names=100)
    assert a["verdict"] == THIN_POPULATION
    assert a["months_scoreable"] == 100
    # THIN does not raise: it is a warning about scope, not an impossibility.
    assert assert_population_declared("intermittent @ liquid", counts,
                                      n_deciles=10, min_names=100)


def test_the_thin_band_is_reachable_at_all():
    """The branch that the first version of this guard could never enter.

    `MIN_SCOREABLE_SHARE` at one half would have made THIN_POPULATION dead
    code, because the median and the share encode the same fact there. Asserting
    the threshold leaves room is cheaper than rediscovering the dead branch.
    """
    from backend.services.research_gym.population import MIN_SCOREABLE_SHARE
    assert MIN_SCOREABLE_SHARE > 0.5
    seen = {assess_population("x", [200] * k + [1] * (100 - k),
                              n_deciles=10)["verdict"] for k in (40, 70, 99)}
    assert seen == {NO_POPULATION_IN_SCOPE, THIN_POPULATION, HAS_POPULATION}


def test_the_requirement_comes_from_the_DESIGN_not_from_a_constant():
    """A coarser sort needs fewer names, and the guard has to know that."""
    counts = [30] * 100
    assert assess_population("x", counts, n_deciles=10)["verdict"] == \
        NO_POPULATION_IN_SCOPE
    assert assess_population("x", counts, n_deciles=5)["verdict"] == \
        HAS_POPULATION
    assert assess_population("x", counts, n_deciles=5,
                             min_names=100)["verdict"] == NO_POPULATION_IN_SCOPE


def test_the_scope_name_travels_into_the_refusal():
    """A refusal that does not name what was refused is a log line."""
    with pytest.raises(NoPopulationInScope, match="momentum @ microcaps"):
        assert_population_declared("momentum @ microcaps", [1] * 50)


def test_decile_members_is_reported_because_that_is_what_the_sort_uses():
    a = assess_population("x", [500] * 50, n_deciles=10)
    assert a["median_decile_members"] == pytest.approx(50.0)
    assert a["names_required"] == 10 * MIN_DECILE_MEMBERS
