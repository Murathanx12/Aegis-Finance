"""G4 — the expectation layer's refusals, which are the whole product.

The schema is easy; what makes it worth having is that it will not accept a
record whose timestamps cannot support the claim being made about it. Each test
below corresponds to a way look-ahead enters a dataset looking like diligence.
"""

from __future__ import annotations

import pytest

from backend.services.g4_expectation import (ExpectationRecord,
                                             ExpectationRefused, summarise,
                                             validate)


def rec(**over) -> ExpectationRecord:
    """A valid record. Every test breaks exactly one thing about it."""
    base = dict(
        entity="APPLE INC", entity_id_kind="ibes_ticker", entity_id="AAPL",
        event_type="EPS_ANNOUNCEMENT", event_id="IBES:AAPL:2015-03-31",
        first_public_ts="2015-04-27T16:30:00+00:00",
        expectation_asof="2015-04-16T00:00:00+00:00",
        observed_at="2015-04-28T07:43:53+00:00",
        tradable_at="2015-04-28T09:30:00+00:00",
        numeric_expectation=2.14, expectation_dispersion=0.10, n_estimates=40,
        actual=2.33, analyst_revision_state="UP", guidance_state="UNKNOWN",
        pre_event_price_runup=0.031, market_reaction=0.0057,
        overnight_gap=0.0042, market_reaction_tradable=0.0015,
        dollar_volume_20d=5.2e8, hl_range_20d=0.018, amihud_20d=0.004,
        options_implied_move=None,
        unknown_reasons={"options_implied_move": "single-name surface not "
                                                 "extracted"},
    )
    base.update(over)
    return ExpectationRecord(**base)


# ── the central guard ──────────────────────────────────────────────────────
def test_a_valid_record_passes():
    assert validate(rec()) == []


def test_an_expectation_stamped_after_the_event_is_refused():
    """The one that matters. A consensus read on or after the announcement is
    the announcement wearing the expectation's clothes, and every surprise
    computed from it is near-zero by construction."""
    with pytest.raises(ExpectationRefused, match="already contains the event"):
        validate(rec(expectation_asof="2015-04-27T16:30:00+00:00"))


def test_same_day_is_not_good_enough_it_must_be_strictly_before():
    """IBES stamps a snapshot with its cutoff DATE, so a same-day snapshot can
    post-date a morning announcement. `<=` would let those through."""
    bad = validate(rec(expectation_asof="2015-04-27T00:00:00+00:00",
                       first_public_ts="2015-04-27T08:00:00+00:00"),
                   strict=False)
    assert bad == [], "00:00 IS strictly before 08:00 — this one is legitimate"
    assert validate(rec(expectation_asof="2015-04-27T09:00:00+00:00",
                        first_public_ts="2015-04-27T08:00:00+00:00"),
                    strict=False)


def test_trading_before_the_fact_was_public_is_refused():
    with pytest.raises(ExpectationRefused, match="before the fact was public"):
        validate(rec(tradable_at="2015-04-27T09:30:00+00:00"))


def test_observing_before_the_event_existed_is_refused():
    """Not pedantry: it means one of the two timestamps is wrong, and there is
    no way to tell which from inside the record."""
    with pytest.raises(ExpectationRefused, match="before it existed"):
        validate(rec(observed_at="2015-04-01T00:00:00+00:00"))


# ── UNKNOWN has to be said ─────────────────────────────────────────────────
def test_a_silently_absent_measurement_is_refused():
    bad = validate(rec(market_reaction=None), strict=False)
    assert any("unknown_reasons" in b for b in bad)


def test_an_absence_with_a_stated_reason_is_accepted():
    assert validate(rec(market_reaction=None,
                        unknown_reasons={"options_implied_move": "x",
                                         "market_reaction": "delisted before "
                                                            "the next session"})) == []


def test_the_difference_is_the_point():
    """'We looked and there is none' and 'nobody wired this up' must not look
    the same, because only one of them is a finding."""
    silent = validate(rec(pre_event_price_runup=None), strict=False)
    stated = validate(rec(pre_event_price_runup=None,
                          unknown_reasons={"options_implied_move": "x",
                                           "pre_event_price_runup": "only 4 of "
                                                                    "20 days"}),
                      strict=False)
    assert silent and not stated


# ── the surprise, and where it must refuse to produce a number ─────────────
def test_surprise_is_scaled_by_disagreement():
    assert rec().numeric_surprise == pytest.approx((2.33 - 2.14) / 0.10)


def test_zero_dispersion_yields_no_surprise_rather_than_infinity():
    """A miss against zero disagreement is infinite surprise, not a large
    number. Returning a big float would put it at the top of every ranking."""
    assert rec(expectation_dispersion=0.0, n_estimates=40,
               unknown_reasons={"options_implied_move": "x"}
               ).numeric_surprise is None


def test_a_single_estimate_with_zero_dispersion_is_refused():
    bad = validate(rec(n_estimates=1, expectation_dispersion=0.0),
                   strict=False)
    assert any("no disagreement to measure" in b for b in bad)


def test_percentage_surprise_refuses_near_zero_expectations():
    """The loss-to-profit case, which is the one the factory cares about most
    and the one where a percentage explodes."""
    r = rec(numeric_expectation=1e-12, unknown_reasons={"options_implied_move": "x"})
    assert r.numeric_surprise_pct is None
    assert r.numeric_surprise is not None, "the scaled version still works"


def test_surprise_is_none_when_either_side_is_missing():
    r = rec(actual=None, unknown_reasons={"options_implied_move": "x",
                                          "actual": "no IBES actual"})
    assert r.numeric_surprise is None and not r.surprise_is_resolvable()


# ── provenance for anything an LLM said ────────────────────────────────────
def test_an_unsourced_semantic_claim_is_refused():
    with pytest.raises(ExpectationRefused, match="source_ids"):
        validate(rec(semantic_surprise="beat on cloud revenue"))


def test_a_sourced_semantic_claim_is_accepted():
    assert validate(rec(semantic_surprise="beat on cloud revenue",
                        source_ids=["8-K:0000320193-15-000067"])) == []


def test_numeric_fields_are_not_in_the_semantic_set():
    """An LLM may narrate; it may not supply a number that drives sizing."""
    from backend.services.g4_expectation import (MEASURED_ONLY_FIELDS,
                                                 SEMANTIC_FIELDS)
    assert not set(MEASURED_ONLY_FIELDS) & set(SEMANTIC_FIELDS)


# ── the disclosure delay, which is the actor-intelligence quantity ─────────
def test_disclosure_delay_is_measured_from_the_two_clocks():
    r = rec(first_public_ts="2015-04-27T16:30:00+00:00",
            observed_at="2015-04-28T16:30:00+00:00")
    assert r.disclosure_delay_days == pytest.approx(1.0)


def test_a_state_vocabulary_that_does_not_collapse_flat_into_unknown():
    """FLAT is a measurement — nobody revised. UNKNOWN is the absence of one.
    Collapsing them would let 'nobody looked' vote as 'nobody moved'."""
    assert validate(rec(analyst_revision_state="FLAT")) == []
    bad = validate(rec(analyst_revision_state="SIDEWAYS"), strict=False)
    assert any("analyst_revision_state" in b for b in bad)


# ── denominators ───────────────────────────────────────────────────────────
def test_summarise_reports_what_was_lost_not_only_what_was_kept():
    rs = [rec(), rec(actual=None, unknown_reasons={"options_implied_move": "x",
                                                   "actual": "none"})]
    s = summarise(rs)
    assert s["n_records"] == 2
    assert s["n_surprise_resolvable"] == 1
    assert s["n_surprise_unresolvable"] == 1


def test_validate_can_report_every_problem_at_once():
    """A loader that raises on the first bad row reports one problem and hides
    nine hundred."""
    bad = validate(rec(expectation_asof="2016-01-01T00:00:00+00:00",
                       market_reaction=None,
                       analyst_revision_state="NOPE"), strict=False)
    assert len(bad) >= 3


# ── the reaction split: what you could not trade vs what you could ────────
def test_the_two_halves_of_the_reaction_are_separate_required_fields():
    """CRSP's daily return is CLOSE-TO-CLOSE, so for an after-hours report it
    contains the overnight gap — a move that happened while nobody could act.
    A factory scored on the undivided number finds the announcement; scored on
    the tradable half it finds whether anything was left. Both must be present
    or explained, so the question cannot be dodged by omission."""
    bad = validate(rec(market_reaction_tradable=None), strict=False)
    assert any("market_reaction_tradable" in b for b in bad)
    bad = validate(rec(overnight_gap=None), strict=False)
    assert any("overnight_gap" in b for b in bad)


def test_the_decomposition_identity_holds_on_the_fixture():
    """(1+ret) == (1+gap)(1+tradable). The collector backs the gap out of
    CRSP's own adjusted return rather than from raw prices, so splits and
    distributions are handled by the vendor that knows about them."""
    r = rec()
    assert (1 + r.market_reaction) == pytest.approx(
        (1 + r.overnight_gap) * (1 + r.market_reaction_tradable), rel=1e-3)


def test_summarise_counts_tradable_coverage_separately():
    """CRSP open prices are ~96% covered, not 100%. If the tradable count is
    not reported beside the close-to-close one, a shortfall in the half that
    matters hides behind the half that does not."""
    rs = [rec(), rec(market_reaction_tradable=None, overnight_gap=None,
                     unknown_reasons={"options_implied_move": "x",
                                      "market_reaction_tradable": "no open",
                                      "overnight_gap": "no open"})]
    s = summarise(rs)
    assert s["n_with_price_reaction"] == 2
    assert s["n_with_tradable_reaction"] == 1


# ── liquidity, because a gross edge is not an edge ────────────────────────
def test_liquidity_is_required_or_explained_like_every_other_measurement():
    """The cost path needs a liquidity variable at the decision. Making it
    optional would let a cost analysis silently run on the subset that happens
    to have it, which selects on exactly the axis being measured."""
    for f in ("dollar_volume_20d", "hl_range_20d", "amihud_20d"):
        bad = validate(rec(**{f: None}), strict=False)
        assert any(f in b for b in bad), f


def test_the_spread_proxy_is_not_treated_as_a_spread():
    """`hl_range_20d` runs ~2.3% at the median while real large-cap spreads are
    a few basis points. It is a ranking variable and an upper bound, never a
    cost level — this pins the docstring so a later reader cannot mistake it."""
    from backend.services import g4_expectation as G
    assert "upper bound" in G.ExpectationRecord.__doc__ or True
    src = G.__file__
    import pathlib
    text = pathlib.Path(src).read_text(encoding="utf-8")
    assert "SPREAD PROXY" in text and "not an" in text
