"""The library may not state a net figure or a bar without its cost rate.

N25's correction, made structural: "exactly one detectable net in the liquid
tercile" was true at 10bp, quoted for two sessions as a fact about the panel,
and is 4 / 3 / 1 / 0 across 0 / 5 / 10 / 20bp. A scalar net is a property of an
assumption wearing the name of a property of a strategy.
"""

from __future__ import annotations

import pytest

from backend.services.strategy_library import (DEFAULT_GRID_BPS, SEED,
                                               ClaimIsNotEvidence, Performance,
                                               RateNotDeclared, StrategySpec,
                                               Source, factory_bar, rate_table)


#: ANNUAL turnover, matching `load_measured` (12 x monthly). The panel's median
#: monthly turnover is 0.59, so ~7 annual is the realistic scale — the first
#: version of these tests used 1.2 and nothing moved, because at that turnover
#: 20bp costs 24 basis points a year.
def _spec(gross=0.06, turn=7.0, mde=0.05):
    s = StrategySpec(name="X", family="f", source=Source.PUBLISHED_ACADEMIC,
                     citation="c")
    s.post_publication = Performance(gross_annual_return=gross,
                                     annual_turnover=turn, mde_annual=mde)
    return s


# ── the refusals ───────────────────────────────────────────────────────────
def test_a_net_figure_without_a_rate_refuses():
    p = _spec().measured()
    with pytest.raises(RateNotDeclared, match="4/3/1/0"):
        p.net_at(None)


def test_the_factory_bar_without_a_rate_refuses_rather_than_defaulting_to_10():
    """The bar sets the threshold every new mechanism is judged against, so an
    unstated cost assumption in it sets the whole factory's bar by accident."""
    with pytest.raises(RateNotDeclared, match="threshold"):
        factory_bar([_spec()])


def test_net_without_a_measured_turnover_refuses_rather_than_inferring_one():
    s = StrategySpec(name="Y", family="f", source=Source.PUBLISHED_ACADEMIC,
                     citation="c")
    s.post_publication = Performance(gross_annual_return=0.06)
    with pytest.raises(ClaimIsNotEvidence, match="turnover"):
        s.measured().net_at(10.0)


def test_detectability_without_an_MDE_refuses():
    s = _spec(mde=None)
    with pytest.raises(ClaimIsNotEvidence, match="MDE"):
        s.measured().detectable_at(10.0)


# ── the arithmetic ─────────────────────────────────────────────────────────
def test_the_rate_actually_moves_the_verdict():
    """The property the whole change exists for."""
    p = _spec(gross=0.06, turn=7.0, mde=0.05).measured()
    assert p.detectable_at(0.0) is True         # 6.00% vs MDE 5%
    assert p.detectable_at(20.0) is False       # 4.60% vs MDE 5%
    assert p.net_at(0.0) > p.net_at(10.0) > p.net_at(50.0)


def test_zero_cost_is_the_gross_number():
    p = _spec().measured()
    assert p.net_at(0.0) == pytest.approx(p.gross_annual_return)


def test_the_default_emission_is_the_whole_grid_not_one_rate():
    t = rate_table([_spec()])
    assert t["grid_bps"] == list(DEFAULT_GRID_BPS)
    assert set(t["rows"][0]["net"]) == set(DEFAULT_GRID_BPS)
    assert len(t["grid_bps"]) > 1


def test_an_unmeasured_strategy_is_carried_as_unmeasured_not_dropped():
    """A strategy missing from a table reads as 'not run yet'; present and
    unmeasured is the finding."""
    rows = rate_table([_spec(), StrategySpec(name="Z", family="f",
                                             source=Source.PUBLISHED_ACADEMIC,
                                             citation="c")])["rows"]
    assert len(rows) == 2
    assert "unmeasured" in rows[1]


def test_the_bar_moves_with_the_rate():
    specs = [_spec(gross=0.06, turn=7.0), _spec(gross=0.04, turn=0.6)]
    # At zero cost the high-turnover one wins; by 50bp the low-turnover one does.
    assert factory_bar(specs, 0.0) == pytest.approx(0.06)
    assert factory_bar(specs, 50.0) == pytest.approx(0.04 - 0.6 * 50 / 1e4)


# ── the prose the harness is meant to stop drifting ────────────────────────
def test_the_withdrawn_four_year_drawdown_figure_is_gone_from_the_seed():
    """§59's '~4 years' was withdrawn 2026-08-17; it lived on in a seed field.

    A withdrawn number inside a data structure outlives the sentence that
    withdrew it, because nobody re-reads a construction string.
    """
    vt = next(s for s in SEED if s.name == "Volatility targeting")
    # The number may APPEAR — it is named in order to be withdrawn. What must
    # not survive is the claiming form of it.
    assert "measurable in ~4 years" not in vt.construction
    assert "WITHDRAWN" in vt.construction
    assert "30x" in vt.construction          # the ratio, which does reproduce
    assert "screen-grade" in vt.construction  # N22's verdict, carried forward


def test_the_seed_priorities_were_not_re_sorted_on_the_measurement():
    """A priority tuned to a result is a result wearing a plan.

    N25 refuted the folk prior these priorities were assigned under. The
    correction is recorded; the ordering is deliberately untouched.
    """
    assert next(s for s in SEED
                if s.name.startswith("Short-term reversal")).priority == "C"
    assert next(s for s in SEED
                if s.name.startswith("Profitability")).priority == "A"
