"""The factory's refusals: look-ahead in the covariates, and controls in name only.

Rule 4 says the informative unit is winner vs MATCHED loser. These tests are
about the word "matched" — a nearest neighbour is always available, and one
that is nothing like the treated unit is a control in name only.
"""

from __future__ import annotations

import math

from backend.services.winner_loser_factory import (CALIPER_SD,
                                                   MATCH_DIMENSIONS, Episode,
                                                   assert_pit, balance_report,
                                                   match_pairs,
                                                   standardised_differences)


def ep(eid: str, outcome: float, *, ts="2015-04-27T16:30:00+00:00",
       asof="2015-04-24T00:00:00+00:00", **chars) -> Episode:
    c = {"industry": "3570", "log_size": 10.0, "momentum_12_1": 0.10,
         "volatility_60d": 0.20, "max_drawdown_1y": -0.15,
         "log_dollar_volume": 18.0, "book_to_market": 0.3,
         "revision_state": "UP", "expectation_state": "HIGH",
         "calendar_block": "2015Q2"}
    c.update(chars)
    return Episode(entity_id=eid, decision_ts=ts, characteristics=c,
                   characteristics_asof={k: asof for k in c},
                   outcome=outcome, outcome_horizon_days=20)


def blk(e: Episode) -> str:
    return str(e.characteristics["calendar_block"])


#: Realistic population scales, supplied explicitly so these tests exercise the
#: MATCHER rather than the scale estimator. Estimating a spread from two points
#: is meaningless and `match_pairs` refuses to; that refusal has its own test.
SDS = {"log_size": 1.5, "momentum_12_1": 0.25, "volatility_60d": 0.10,
       "max_drawdown_1y": 0.12, "log_dollar_volume": 2.0,
       "book_to_market": 0.4, "industry": 0.0, "revision_state": 0.0,
       "expectation_state": 0.0, "calendar_block": 0.0}


def match(eps, **kw):
    kw.setdefault("covariate_sds", SDS)
    kw.setdefault("block_of", blk)
    return match_pairs(eps, **kw)


# ── look-ahead in the covariates ───────────────────────────────────────────
def test_a_covariate_computed_after_the_decision_is_refused():
    """The most common way a matched study becomes a look-ahead study: a
    window that closes after the event it is supposed to predate."""
    e = ep("A", 0.05)
    e.characteristics_asof["momentum_12_1"] = "2015-05-01T00:00:00+00:00"
    bad = assert_pit(e)
    assert len(bad) == 1 and "not before the decision" in bad[0]


def test_a_covariate_dated_exactly_at_the_decision_is_refused():
    """Same instant is not before. A characteristic stamped at the decision
    time may have been computed from a window that includes it."""
    e = ep("A", 0.05)
    e.characteristics_asof["log_size"] = e.decision_ts
    assert assert_pit(e)


def test_a_covariate_with_no_date_is_refused_not_assumed_fine():
    e = ep("A", 0.05)
    del e.characteristics_asof["volatility_60d"]
    bad = assert_pit(e)
    assert len(bad) == 1 and "no `characteristics_asof`" in bad[0]


def test_pit_violations_are_counted_and_named_not_silently_dropped():
    good = [ep(f"G{i}", 0.10 - i * 0.01) for i in range(6)]
    bad = ep("B", 0.99)
    bad.characteristics_asof["log_size"] = "2016-01-01T00:00:00+00:00"
    _, counts = match(good + [bad])
    assert counts["pit_violations"] == 1
    assert counts["pit_violation_kinds"]


# ── a control in name only ─────────────────────────────────────────────────
def test_a_far_neighbour_is_dropped_rather_than_kept_with_a_footnote():
    """Two episodes, wildly different size. A nearest-neighbour matcher always
    finds a partner; the caliper is what makes it a control."""
    a, b = ep("A", 0.20, log_size=10.0), ep("B", -0.20, log_size=25.0)
    pairs, counts = match([a, b], winner_quantile=0.5)
    assert pairs == []
    assert counts["unmatched_winners_outside_caliper"] == 1


def test_a_close_neighbour_is_matched():
    a, b = ep("A", 0.20, log_size=10.0), ep("B", -0.20, log_size=10.05)
    pairs, _ = match([a, b], winner_quantile=0.5)
    assert len(pairs) == 1
    assert pairs[0].winner.entity_id == "A" and pairs[0].loser.entity_id == "B"


def test_exact_dimensions_are_exact():
    """A 'close' industry is a different industry."""
    a, b = ep("A", 0.20, industry="3570"), ep("B", -0.20, industry="2834")
    pairs, _ = match([a, b], winner_quantile=0.5)
    assert pairs == []


def test_a_missing_characteristic_cannot_be_matched_on():
    a, b = ep("A", 0.20), ep("B", -0.20, book_to_market=None)
    sd = standardised_differences(a, b, {d: 1.0 for d in MATCH_DIMENSIONS})
    assert sd["book_to_market"] == float("inf")
    pairs, _ = match([a, b], winner_quantile=0.5)
    assert pairs == [], "unknown is not a match, it is an absence of one"


def test_zero_variation_makes_any_difference_infinite_not_small():
    """With no spread, a difference cannot be expressed in standard deviations.
    Returning a small number there would silently admit the pair."""
    a, b = ep("A", 0.2, log_size=10.0), ep("B", -0.2, log_size=11.0)
    sd = standardised_differences(a, b, {d: 0.0 for d in MATCH_DIMENSIONS})
    assert sd["log_size"] == float("inf")
    same = standardised_differences(a, ep("C", 0.0, log_size=10.0),
                                    {d: 0.0 for d in MATCH_DIMENSIONS})
    assert same["log_size"] == 0.0


# ── the market must not be the difference ──────────────────────────────────
def test_matching_never_crosses_a_calendar_block():
    a = ep("A", 0.20, calendar_block="2015Q2")
    b = ep("B", -0.20, calendar_block="2015Q3")
    pairs, counts = match([a, b], winner_quantile=1.0)
    assert pairs == []
    assert counts["blocks"] == 2


def test_the_label_is_a_within_block_rank_so_a_rising_market_cancels():
    """Every episode in this block has a POSITIVE outcome. A raw-return
    threshold would call them all winners and leave nothing to compare."""
    eps = [ep(f"E{i}", 0.01 + i * 0.01, log_size=10.0 + (i % 3) * 0.05)
           for i in range(10)]
    pairs, counts = match(eps, winner_quantile=0.3)
    assert counts["candidate_winners"] == 3 and counts["candidate_losers"] == 3
    assert pairs, "a uniformly rising block still yields winner/loser pairs"
    for p in pairs:
        assert p.winner.outcome > p.loser.outcome


# ── denominators ───────────────────────────────────────────────────────────
def test_the_two_kinds_of_unmatched_winner_are_distinguished():
    """'No partner existed' and 'partners existed and were all too different'
    call for opposite fixes; one number for both hides which you have."""
    lone = [ep("W", 0.5)]
    _, c1 = match(lone, winner_quantile=1.0)
    assert c1["pairs"] == 0

    far = [ep("W", 0.5, log_size=10.0), ep("L", -0.5, log_size=40.0)]
    _, c2 = match(far, winner_quantile=0.5)
    assert c2["unmatched_winners_outside_caliper"] == 1
    assert c2["unmatched_winners_no_partner"] == 0


def test_episodes_without_an_outcome_are_counted_not_dropped_quietly():
    eps = [ep("A", 0.2), ep("B", -0.2)]
    eps[1].outcome = None
    _, counts = match(eps)
    assert counts["no_outcome"] == 1


def test_every_result_carries_what_was_held_fixed():
    """A reader who does not know what was matched cannot evaluate what was
    found, so the list travels with the result rather than with the docs."""
    a, b = ep("A", 0.2, log_size=10.0), ep("B", -0.2, log_size=10.01)
    pairs, counts = match([a, b], winner_quantile=0.5)
    assert counts["matched_on"] == list(MATCH_DIMENSIONS)
    assert pairs[0].as_dict()["matched_on"] == list(MATCH_DIMENSIONS)
    assert counts["caliper_sd"] == CALIPER_SD


def test_balance_is_reported_per_dimension_not_as_one_average():
    """A mean of 0.1 can hide one dimension at 0.24, and that dimension is the
    one a reader will propose as the explanation."""
    eps = [ep(f"E{i}", 0.5 - i * 0.1, log_size=10.0 + (i % 2) * 0.05,
              momentum_12_1=0.10 + (i % 2) * 0.01) for i in range(8)]
    pairs, _ = match(eps, winner_quantile=0.5)
    rep = balance_report(pairs)
    assert rep["n_pairs"] == len(pairs)
    assert set(rep["per_dimension"]) == set(MATCH_DIMENSIONS)
    assert rep["worst_dimension"] in MATCH_DIMENSIONS
    for d, s in rep["per_dimension"].items():
        if s["max_sd"] is not None:
            assert s["max_sd"] <= CALIPER_SD + 1e-9, (
                f"{d} exceeds the caliper inside an accepted pair")


def test_one_loser_is_used_at_most_once():
    """Reusing a control inflates the effective sample: the same loser voting
    in three pairs is one observation counted three times."""
    eps = ([ep(f"W{i}", 0.5 - i * 0.01, log_size=10.0) for i in range(3)]
           + [ep("L", -0.5, log_size=10.0)])
    pairs, _ = match(eps, winner_quantile=0.25)
    assert len({id(p.loser) for p in pairs}) == len(pairs)


def test_balance_report_on_no_pairs_says_so_rather_than_dividing_by_zero():
    assert balance_report([]) == {"n_pairs": 0}


# ── the covariate scale is a property of the population, not of the block ──
def test_a_scale_estimated_from_too_few_episodes_is_refused():
    """The bug this refusal exists for: with the spread computed inside a block
    of two, the sd IS the difference, so every possible pair sits 1.41 sd apart
    and nothing ever matches — while the report happily says 'no pairs found',
    which reads as a fact about the world rather than about the estimator."""
    eps = [ep("A", 0.2, log_size=10.0), ep("B", -0.2, log_size=10.01)]
    pairs, counts = match_pairs(eps, block_of=blk, winner_quantile=0.5)
    assert pairs == []
    assert counts["covariate_scale_source"] == "REFUSED"
    assert "standardise" in counts["refusal"]


def test_with_enough_episodes_the_scale_is_estimated_and_recorded():
    eps = [ep(f"E{i}", (i % 7) / 10.0, log_size=10.0 + (i % 5) * 0.4)
           for i in range(40)]
    pairs, counts = match_pairs(eps, block_of=blk, winner_quantile=0.3)
    assert counts["covariate_scale_source"].startswith("population n=")
    assert pairs, "40 episodes with overlapping sizes should pair"


def test_the_same_caliper_means_the_same_thing_in_every_block():
    """Block-local scaling would make 0.25 sd a tighter requirement in a quiet
    quarter than in a volatile one, silently admitting different pairs
    depending on when they happened."""
    quiet = [ep(f"Q{i}", (i % 5) / 10.0, log_size=10.0 + (i % 3) * 0.02,
                calendar_block="2015Q1") for i in range(20)]
    # In the wild block size moves WITH the outcome, so a winner's nearest
    # admissible loser is genuinely far away — there is no close partner to
    # find, which is the situation the caliper exists to report rather than
    # paper over.
    wild = [ep(f"W{i}", (i % 5) / 10.0, log_size=10.0 + (i % 5) * 2.0,
               calendar_block="2015Q2") for i in range(20)]
    _, counts = match_pairs(quiet + wild, block_of=blk, winner_quantile=0.3,
                            covariate_sds=SDS)
    assert counts["covariate_scale_source"] == "supplied"
    # The quiet block's pairs are all well inside the caliper; the wild block's
    # are mostly outside it. Under block-local scaling both would look alike.
    assert counts["unmatched_winners_outside_caliper"] > 0
    assert counts["pairs"] > 0
