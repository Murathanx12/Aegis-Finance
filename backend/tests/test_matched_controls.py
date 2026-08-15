"""T3: the control engine, built before any insider winner is interpreted.

WHY THESE TESTS ARE SHAPED THIS WAY
===================================
The tempting first result from a Teacher Library is a story — *a CEO bought
after a 40% drawdown and the stock doubled* — which contains no comparison, so
it cannot be wrong, so it cannot be evidence. A control built after that story
is found is chosen, however honestly, by someone who already knows which
control lets the story survive.

So every test below starts from a case where the right answer is known in
advance: a market that moved and took everything with it, a control pool that
is not actually comparable, an arm with too few observations to say anything.
The engine has to say so.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.services.teacher_library import matched_controls as MC


def _c(key, ticker, date, ret=None, *, sector="tech", cap=10.0, beta=1.0,
       mom=0.0, vol=20.0, dd=-5.0, dv=18.0, earn=30, event=False,
       actor="", action=""):
    return MC.Candidate(
        key=key, ticker=ticker, date=date, forward_return_pct=ret,
        has_event=event, actor_id=actor, action_type=action,
        covariates={"sector": sector, "log_market_cap": cap, "beta": beta,
                    "momentum_12m": mom, "realised_vol_60d": vol,
                    "drawdown_pct": dd, "log_dollar_volume": dv,
                    "days_to_next_earnings": earn})


# ── matching ────────────────────────────────────────────────────────────────

def test_controls_come_from_the_same_date_as_the_event():
    """A control measured over a different window compares against a different
    market, and the market moves further than any insider signal here."""
    ev = _c("E", "AAA", "2026-01-05", 10.0, event=True)
    pool = [_c("x", "BBB", "2026-01-05", 1.0),
            _c("y", "CCC", "2026-06-05", 50.0)]
    got = MC.match_controls(ev, pool, k=5)
    assert [c.ticker for c in got] == ["BBB"]


def test_sector_is_matched_EXACTLY_not_by_distance():
    ev = _c("E", "AAA", "d", 10.0, sector="energy", event=True)
    pool = [_c("x", "BBB", "d", 1.0, sector="tech", beta=1.0),
            _c("y", "CCC", "d", 2.0, sector="energy", beta=3.0)]
    got = MC.match_controls(ev, pool, k=5)
    # The energy name wins despite being far away on beta. A nearby sector is
    # not a sector.
    assert [c.ticker for c in got] == ["CCC"]


def test_the_event_security_is_never_its_own_control():
    ev = _c("E", "AAA", "d", 10.0, event=True)
    got = MC.match_controls(ev, [_c("x", "AAA", "d", 10.0)], k=5)
    assert got == []


def test_other_event_securities_are_excluded_from_the_control_pool():
    ev = _c("E", "AAA", "d", 10.0, event=True)
    pool = [_c("x", "BBB", "d", 1.0, event=True), _c("y", "CCC", "d", 2.0)]
    assert [c.ticker for c in MC.match_controls(ev, pool, k=5)] == ["CCC"]


def test_a_candidate_missing_a_covariate_is_not_a_CLOSE_match_on_it():
    """Skipping the term would preferentially select candidates with missing
    data — the closer a candidate is to unmeasured, the better it would score."""
    ev = _c("E", "AAA", "d", 10.0, beta=1.0, event=True)
    near_but_incomplete = _c("x", "BBB", "d", 1.0, beta=1.0)
    near_but_incomplete.covariates["beta"] = None
    far_but_complete = _c("y", "CCC", "d", 2.0, beta=2.5)
    got = MC.match_controls(ev, [near_but_incomplete, far_but_complete], k=5)
    assert [c.ticker for c in got] == ["CCC"]


def test_nearest_controls_are_actually_the_nearest():
    ev = _c("E", "AAA", "d", 10.0, beta=1.0, mom=0.0, event=True)
    pool = [_c("far", "F", "d", 1.0, beta=4.0, mom=90.0),
            _c("near", "N", "d", 1.0, beta=1.1, mom=1.0),
            _c("mid", "M", "d", 1.0, beta=2.0, mom=30.0)]
    got = MC.match_controls(ev, pool, k=2)
    assert [c.ticker for c in got] == ["N", "M"]


# ── balance is reported, not assumed ────────────────────────────────────────

def test_balance_is_reported_per_covariate():
    events = [_c(f"e{i}", f"E{i}", "d", 5.0, beta=1.0) for i in range(6)]
    controls = [_c(f"c{i}", f"C{i}", "d", 1.0, beta=1.0) for i in range(6)]
    b = MC.balance_of(events, controls)
    assert b.is_balanced
    assert set(b.smd) <= set(MC.COVARIATES)


def test_an_UNBALANCED_control_set_says_so_and_blocks_interpretation():
    """A mismatched control carries the authority of the word 'matched'."""
    events = [_c(f"e{i}", f"E{i}", "d", 5.0, beta=1.0 + i * 0.01)
              for i in range(8)]
    controls = [_c(f"c{i}", f"C{i}", "d", 1.0, beta=3.0 + i * 0.01)
                for i in range(8)]
    b = MC.balance_of(events, controls)
    assert not b.is_balanced
    assert b.worst[0] == "beta"

    r = MC.compare(events, controls, arm=MC.MATCHED_SECURITY, balance=b)
    assert r.is_interpretable is False
    assert "NOT balanced" in r.reason


def test_a_sector_mismatch_is_reported_as_unmeasurable_not_as_zero():
    events = [_c(f"e{i}", f"E{i}", "d", 5.0, sector="tech") for i in range(4)]
    controls = [_c(f"c{i}", f"C{i}", "d", 1.0, sector="energy")
                for i in range(4)]
    b = MC.balance_of(events, controls)
    assert "sector" in b.unmeasurable
    assert not b.is_balanced


# ── the comparison carries its own SE and MDE ───────────────────────────────

def test_a_difference_is_reported_with_its_SE_and_MDE():
    events = [_c(f"e{i}", f"E{i}", "d", 10.0 + i) for i in range(8)]
    controls = [_c(f"c{i}", f"C{i}", "d", 1.0 + i) for i in range(8)]
    r = MC.compare(events, controls, arm=MC.MATCHED_SECURITY)
    assert r.diff_pct == pytest.approx(9.0)
    assert r.se_pct is not None and r.mde_pct is not None
    assert r.is_detectable is True


def test_too_few_controls_is_UNPOWERED_not_a_null():
    """Absence of evidence sold as evidence of absence is the failure here."""
    events = [_c(f"e{i}", f"E{i}", "d", 10.0 + i) for i in range(6)]
    controls = [_c("c0", "C0", "d", 1.0), _c("c1", "C1", "d", 2.0)]
    r = MC.compare(events, controls, arm=MC.MATCHED_SECURITY)
    assert r.is_interpretable is False
    assert "UNPOWERED" in r.reason
    assert "means nothing" in r.reason


def test_clustered_events_do_not_count_as_independent_ones():
    """Five insiders filing on one issuer in one week are ONE event.

    Counting them as five is the single easiest way to manufacture significance
    in this dataset, because clusters are exactly where the interesting stories
    live.
    """
    events = [_c(f"e{i}", "AAA", "d", 10.0 + i * 0.1) for i in range(10)]
    controls = [_c(f"c{i}", f"C{i}", "d", 1.0 + i * 0.1) for i in range(10)]
    naive = MC.compare(events, controls, arm=MC.MATCHED_SECURITY)
    clustered = MC.compare(events, controls, arm=MC.MATCHED_SECURITY,
                           n_event_clusters=1)
    assert clustered.se_pct > naive.se_pct
    assert abs(clustered.t_stat) < abs(naive.t_stat)


def test_no_outcomes_on_one_side_is_UNMEASURED_not_no_difference():
    events = [_c("e", "E", "d", None)]
    controls = [_c("c", "C", "d", 1.0)]
    r = MC.compare(events, controls, arm=MC.MATCHED_SECURITY)
    assert r.diff_pct is None
    assert "not the same as no difference" in r.reason


# ── the placebo family ──────────────────────────────────────────────────────

def test_the_family_refuses_to_run_without_a_seeded_rng():
    """An unreproducible shuffle placebo is a number, not a control."""
    with pytest.raises(MC.ControlRefused, match="seeded rng"):
        MC.run_control_family([_c("e", "E", "d", 1.0)], [], rng=None)


def test_every_declared_arm_runs_so_the_kind_one_cannot_be_chosen():
    ev = [_c(f"e{i}", f"E{i}", "d", 10.0, event=True, actor=f"a{i}",
             action="BUY" if i % 2 else "SELL") for i in range(6)]
    pool = [_c(f"p{i}", f"P{i}", "d", 1.0) for i in range(10)]
    res = MC.run_control_family(ev, pool, rng=np.random.default_rng(7))
    assert set(res) == set(MC.PLACEBO_FAMILY)


def test_a_market_wide_move_is_NOT_read_as_an_insider_effect():
    """The case the matched arm exists for.

    Every security gained 12% that quarter, insiders or not. A story about the
    event stocks would be true and meaningless; the matched control has to
    remove it.
    """
    rng = np.random.default_rng(11)
    # Same mean, real dispersion. Identical returns everywhere would be a
    # degenerate sample with zero variance, and the engine correctly declines
    # to compute an MDE from that — which is a different answer from "not
    # detectable", and the test should exercise the one that matters.
    ev = [_c(f"e{i}", f"E{i}", "d", 12.0 + float(rng.normal(0, 6)), event=True,
             actor=f"a{i}", action="BUY") for i in range(8)]
    pool = [_c(f"p{i}", f"P{i}", "d", 12.0 + float(rng.normal(0, 6)))
            for i in range(20)]
    res = MC.run_control_family(ev, pool, rng=np.random.default_rng(11))
    m = res[MC.MATCHED_SECURITY]
    assert abs(m.diff_pct) < 5.0            # the market move is removed
    assert m.is_detectable is False         # and what is left is not a finding
    assert m.is_interpretable is True       # this arm DID answer the question


def test_events_that_found_no_control_are_named_not_dropped_quietly():
    """A mean over the events that happened to find controls is a mean over a
    subset chosen by data availability."""
    ev = [_c("e0", "E0", "d", 10.0, sector="tech", event=True),
          _c("e1", "E1", "d", 10.0, sector="obscure", event=True)]
    pool = [_c(f"p{i}", f"P{i}", "d", 1.0, sector="tech") for i in range(6)]
    res = MC.run_control_family(ev, pool, rng=np.random.default_rng(3))
    assert "found NO matched control" in res[MC.MATCHED_SECURITY].reason


def test_the_sign_flip_arm_compares_buys_against_sells():
    ev = ([_c(f"b{i}", f"B{i}", "d", 10.0, event=True, action="BUY")
           for i in range(6)]
          + [_c(f"s{i}", f"S{i}", "d", 2.0, event=True, action="SELL")
             for i in range(6)])
    res = MC.run_control_family(ev, [_c("p", "P", "d", 1.0)],
                                rng=np.random.default_rng(5))
    assert res[MC.SIGN_FLIP].diff_pct == pytest.approx(8.0)


def test_the_summary_distinguishes_UNEVALUABLE_from_NULL():
    """"We cannot evaluate this yet" and "we evaluated it and found nothing"
    are different sentences and must not print as the same one."""
    ev = [_c("e", "E", "d", 10.0, event=True, action="BUY", actor="a")]
    res = MC.run_control_family(ev, [], rng=np.random.default_rng(1))
    s = MC.summarise(res)
    assert s["arms_interpretable"] == []
    assert "NO INTERPRETABLE ARM" in s["verdict"]
    assert "not the same as evaluating to nothing" in s["verdict"]
    assert s["citable"] is False


def test_a_real_difference_survives_the_family_and_is_reported_as_such():
    ev = [_c(f"e{i}", f"E{i}", "d", 20.0 + i * 0.5, event=True,
             actor=f"a{i}", action="BUY") for i in range(10)]
    pool = [_c(f"p{i}", f"P{i}", "d", 1.0 + i * 0.5) for i in range(20)]
    res = MC.run_control_family(ev, pool, rng=np.random.default_rng(13))
    s = MC.summarise(res)
    assert MC.MATCHED_SECURITY in s["arms_detectable"]
    assert res[MC.MATCHED_SECURITY].diff_pct > 15


def test_nothing_the_engine_produces_is_citable():
    ev = [_c(f"e{i}", f"E{i}", "d", 5.0, event=True, action="BUY")
          for i in range(6)]
    pool = [_c(f"p{i}", f"P{i}", "d", 1.0) for i in range(10)]
    res = MC.run_control_family(ev, pool, rng=np.random.default_rng(2))
    assert all(r.as_dict()["citable"] is False for r in res.values())
