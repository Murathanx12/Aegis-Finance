"""A published claim must never be able to stand in for an Aegis measurement.

Both look like a float in a column six weeks later. This is the only property
of the library that actually needs defending.
"""

from __future__ import annotations

import pytest

from backend.services.strategy_library import (SEED, ClaimIsNotEvidence,
                                               Performance, Reproduction,
                                               Source, StrategySpec,
                                               status_report)


def spec(**over) -> StrategySpec:
    base = dict(name="X", family="f", source=Source.PUBLISHED_ACADEMIC,
                citation="Someone (2001)",
                claimed=Performance(gross_annual_return=0.12, sharpe=1.4))
    base.update(over)
    return StrategySpec(**base)


# ── the guard ──────────────────────────────────────────────────────────────
def test_asking_for_a_measurement_that_does_not_exist_refuses(spec_=None):
    s = spec()
    with pytest.raises(ClaimIsNotEvidence, match="NOT a substitute"):
        s.measured("post_publication")


def test_it_refuses_even_though_a_claim_is_sitting_right_there():
    """The whole failure mode. `measured()` must contain no fallback."""
    s = spec(claimed=Performance(gross_annual_return=0.99, sharpe=9.9))
    with pytest.raises(ClaimIsNotEvidence):
        s.measured()
    assert s.claimed.gross_annual_return == 0.99, "the claim is still recorded"


def test_a_measurement_is_returned_once_it_exists():
    s = spec(post_publication=Performance(gross_annual_return=0.03))
    assert s.measured().gross_annual_return == 0.03


def test_the_refusal_names_the_reproduction_status():
    """So the reader knows whether it was never attempted or attempted and
    failed — those call for different next actions."""
    s = spec(reproduction_status=Reproduction.FAILED)
    with pytest.raises(ClaimIsNotEvidence, match="FAILED"):
        s.measured()


# ── decay ──────────────────────────────────────────────────────────────────
def test_decay_needs_both_halves_measured_on_our_data():
    s = spec(post_publication=Performance(gross_annual_return=0.02))
    d = s.decay()
    assert d["decay"] is None
    assert "cannot stand in" in d["why"]


def test_decay_compares_our_window_to_our_window_not_to_the_paper():
    """measured/claimed would confound decay with every difference between
    their pipeline and ours — universe, survivorship, costs, weighting."""
    s = spec(claimed=Performance(gross_annual_return=0.99),
             in_sample=Performance(gross_annual_return=0.10),
             post_publication=Performance(gross_annual_return=0.04))
    d = s.decay()
    assert d["decay"] == pytest.approx(0.6)
    assert d["in_sample_gross"] == 0.10, "not the claimed 0.99"


def test_the_mclean_pontiff_prior_travels_with_the_number():
    s = spec(in_sample=Performance(gross_annual_return=0.10),
             post_publication=Performance(gross_annual_return=0.10))
    d = s.decay()
    assert d["decay"] == pytest.approx(0.0)
    assert d["mclean_pontiff_prior"] == 0.58
    assert "PRIOR to compare against, not a target" in d["why"]


def test_a_zero_in_sample_return_does_not_divide_by_zero():
    s = spec(in_sample=Performance(gross_annual_return=0.0),
             post_publication=Performance(gross_annual_return=0.01))
    assert s.decay()["decay"] is None


# ── the seed ───────────────────────────────────────────────────────────────
def test_nothing_in_the_seed_claims_to_be_reproduced():
    for s in SEED:
        assert s.reproduction_status is Reproduction.NOT_ATTEMPTED, (
            f"{s.name} claims a reproduction status nobody has earned")


def test_no_seeded_strategy_carries_an_aegis_measurement():
    for s in SEED:
        assert s.in_sample is None and s.post_sample is None \
            and s.post_publication is None, f"{s.name} carries a measurement"


def test_the_status_report_says_so_out_loud():
    r = status_report()
    assert r["n_with_any_aegis_measurement"] == 0
    assert r["by_reproduction"]["NOT_ATTEMPTED"] == r["n_strategies"]
    assert "never an Aegis result" in r["warning"]


def test_every_seeded_strategy_can_be_reimplemented_from_its_own_record():
    """If the construction cannot be written down, the strategy is not
    specified and can be neither reproduced nor refuted."""
    for s in SEED:
        assert len(s.construction) > 40, f"{s.name} is under-specified"
        assert s.citation, f"{s.name} has no citation"
        assert s.family and s.universe or s.family, s.name


def test_the_high_turnover_strategies_carry_their_cost_warning():
    """Novy-Marx & Velikov: low-turnover anomalies survive costs, high-turnover
    ones mostly do not. A library that ranked purely on gross return would put
    the least implementable strategy first."""
    hot = [s for s in SEED if s.family in ("reversal", "momentum")]
    assert hot
    for s in hot:
        assert "turnover" in s.capacity_note.lower() or "cost" in s.capacity_note.lower()


def test_pead_is_seeded_as_a_conditional_question_not_a_strategy():
    """The modern evidence says the unconditional large-cap drift is attenuated
    or gone, so importing it as a strategy would be importing a dead one."""
    p = next(s for s in SEED if s.name.startswith("PEAD"))
    assert "CONDITIONAL" in p.construction
    assert "conditional" in p.priority.lower()


def test_bab_is_seeded_with_its_critique_rather_than_its_headline():
    b = next(s for s in SEED if s.name.startswith("BAB"))
    assert "betting against betting against beta" in b.citation.lower()
    assert "DECOMPOSITION" in b.construction


def test_volatility_targeting_is_labelled_a_sizing_rule():
    """It is the layer §59 says this slice can actually resolve — a risk effect
    is measurable in ~4 years where a return effect needs ~95."""
    v = next(s for s in SEED if s.name.startswith("Volatility"))
    assert "SIZING" in v.construction
    assert "not a stock picker" in v.priority


def test_sources_are_recorded_but_do_not_rank():
    """Provenance is a label, not a quality score: all three compete under the
    same utility function."""
    r = status_report()
    assert r["by_source"]["PUBLISHED_ACADEMIC"] > 0
    assert r["by_source"]["PUBLIC_PRACTITIONER"] > 0
