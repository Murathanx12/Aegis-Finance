"""RESEARCH-GYM-1 phase 1: the episode, the surface, the taxonomy, the walls.

Offline and deterministic. The price paths are constructed so each test asserts
one property, because a counterfactual engine tested on real data tests the data
as much as the engine.

WHAT THESE ARE PROTECTING
=========================
The Gym licenses deliberate overfitting. That is only safe if the walls hold, so
the walls are tested harder than the arithmetic: a Gym number must refuse to
become a claim, a search must leave a lineage row, and the episode that
generated a hypothesis must be barred from proving it.
"""

from __future__ import annotations

import pytest

from backend.services import research_gym as G


def _ep(action="SELL", after=0.0, p_up=None, realised=None, horizon=63,
        **kw):
    ep = G.DecisionEpisode(
        decision_ts="2020-04-01T00:00:00+00:00", security="SPY",
        action=action, exposure_before=1.0, exposure_after=after,
        stated_reason="extreme stress + bearish regime + volatility spike",
        beliefs=G.Beliefs(p_up=p_up, horizon_days=horizon), **kw)
    if realised is not None:
        ep.outcome = G.Outcome(resolved_at="2020-07-01", horizon_days=horizon,
                               realised_return_pct=realised)
    return ep


def _path(daily: float, n: int = 63):
    return [daily] * n


# ── the record ──────────────────────────────────────────────────────────────

def test_an_exposure_stated_in_percent_is_refused():
    # 50 rather than 0.50. This project has already written a batch of
    # guaranteed-wrong records by taking a percent for a fraction; the record
    # type refuses rather than trusting every future call site.
    with pytest.raises(ValueError, match="percent"):
        G.DecisionEpisode(decision_ts="t", security="SPY", action="SELL",
                          exposure_after=50.0)


def test_the_episode_id_changes_when_the_state_changes():
    a = _ep(); b = _ep()
    assert a.episode_id == b.episode_id
    c = _ep(); c.state = {"vix": 57.0}
    # An edited episode becomes a different episode rather than silently
    # becoming a different decision under the old identity.
    assert c.episode_id != a.episode_id


def test_an_unresolved_episode_is_structurally_unresolved():
    ep = _ep()
    assert ep.is_resolved is False
    assert ep.outcome is None          # not a zero a downstream mean would eat


def test_absent_beliefs_are_unknown_not_a_coin_flip():
    assert G.Beliefs().is_empty()
    assert G.Beliefs().p_up is None    # None, never 0.5


# ── the whole surface, never just the winner ────────────────────────────────

def test_the_surface_contains_every_policy_in_the_menu():
    s = G.replay(_ep(), _path(0.002))
    assert set(s.results) == set(G.POLICY_MENU)
    # Recorded in full. Truncating to a top-N turns the record into a
    # leaderboard, and a maximum over seventeen tries on one sample is not an
    # estimate of anything.
    assert len(s.as_dict()["surface"]) == len(G.POLICY_MENU)


def test_holding_through_a_rally_beats_selling_and_regret_is_positive():
    # +0.2%/day for 63 days: the April-2020 shape.
    s = G.replay(_ep(action="SELL", after=0.0), _path(0.002))

    assert s.taken_policy == "sell_100"
    assert s.best().name in ("buy_50", "buy_25", "hold")
    assert s.regret_pct() > 0
    assert s.results["hold"].net_return_pct > s.results["sell_100"].net_return_pct


def test_selling_into_a_real_decline_shows_no_regret():
    s = G.replay(_ep(action="SELL", after=0.0), _path(-0.003))
    assert s.results["sell_100"].net_return_pct > s.results["hold"].net_return_pct
    assert s.regret_pct() == pytest.approx(0.0, abs=1e-9)


def test_costs_are_charged_and_change_the_ranking():
    flat = _path(0.0)
    cheap = G.replay(_ep(), flat, cost_bps=0.0)
    dear = G.replay(_ep(), flat, cost_bps=200.0)

    # On a flat path every policy earns nothing gross, so the only thing left
    # to rank them by is turnover — which is the point: a menu that ignored
    # cost would rank the busiest policy first every time.
    assert cheap.results["sell_100_scale_in_4x5d"].cost_pct == 0.0
    assert dear.results["sell_100_scale_in_4x5d"].cost_pct > 0.0
    assert dear.results["hold"].net_return_pct >= \
        dear.results["sell_100_scale_in_4x5d"].net_return_pct


def test_an_action_outside_the_menu_is_refused_rather_than_rounded():
    ep = _ep(after=0.37)
    with pytest.raises(ValueError, match="matches no menu policy"):
        G.taken_policy_name(ep)


def test_reentry_policies_actually_re_enter():
    # Down 10% over the first 10 days, then up.
    path = [-0.01] * 10 + [0.004] * 53
    s = G.replay(_ep(), path)

    early = s.results["sell_100_reenter_10d"].exposure_path
    assert early[:10] == (0.0,) * 10
    assert early[10] == 1.0
    # Selling and coming back beats staying out through the recovery.
    assert s.results["sell_100_reenter_10d"].net_return_pct > \
        s.results["sell_100"].net_return_pct


def test_the_drawdown_trigger_waits_for_the_drawdown():
    # Never falls 10%, so the policy never re-enters.
    s = G.replay(_ep(), _path(0.001))
    assert set(s.results["sell_100_reenter_down_10pct"].exposure_path) == {0.0}


# ── R4: the distinction the whole thing exists for ──────────────────────────

def test_a_wrong_view_is_a_forecast_failure():
    ep = _ep(p_up=0.30, realised=13.4)          # believed down, market rose
    s = G.replay(ep, _path(0.002))
    G.attribute_in_place(ep, s)

    assert ep.failure_mode == G.FORECAST_FAILURE
    assert "the other way" in ep.failure_detail


def test_a_right_view_converted_into_the_wrong_action_is_action_mapping():
    # The prize case, and the shape the timing backtest implies: the system
    # thought the market would RISE and de-risked anyway, because "extreme
    # stress" was wired to "reduce exposure" regardless of the forecast.
    ep = _ep(p_up=0.65, realised=13.4)
    s = G.replay(ep, _path(0.002))
    G.attribute_in_place(ep, s)

    assert ep.failure_mode in (G.ACTION_MAPPING_FAILURE, G.SIZING_FAILURE)
    assert "policy layer" in ep.failure_detail or "HOW MUCH" in ep.failure_detail
    # And it is emphatically NOT a forecast failure — the perception was fine,
    # which is exactly what a prediction-scoring framework cannot see.
    assert ep.failure_mode != G.FORECAST_FAILURE


def test_no_beliefs_means_unclassified_not_a_guess():
    ep = _ep(p_up=None, realised=13.4)
    s = G.replay(ep, _path(0.002))
    G.attribute_in_place(ep, s)

    # "We do not know what it believed" and "its belief was wrong" are
    # different facts, and assuming either would invent the finding.
    assert ep.failure_mode == G.UNCLASSIFIED
    assert "cannot be separated" in ep.failure_detail


def test_a_decision_close_to_the_best_alternative_is_not_a_failure():
    ep = _ep(action="HOLD", after=1.0, p_up=0.6, realised=0.1)
    s = G.replay(ep, _path(0.00002))
    G.attribute_in_place(ep, s)

    assert ep.failure_mode == G.NO_FAILURE


def test_an_unresolved_episode_is_never_classified():
    ep = _ep(p_up=0.65)
    G.attribute_in_place(ep, G.replay(ep, _path(0.002)))
    assert ep.failure_mode == G.UNCLASSIFIED
    assert "unresolved" in ep.failure_detail


def test_every_failure_mode_has_a_description():
    # A taxonomy with an unexplained member is a taxonomy people guess at.
    assert set(G.FAILURE_DESCRIPTIONS) == set(G.FAILURE_MODES)


# ── WALL 1: a Gym number refuses to be a claim ──────────────────────────────

def test_a_gym_result_refuses_to_render_as_a_claim():
    r = G.GymResult(name="best_policy_edge_pct", value=14.2)

    with pytest.raises(G.GymOutputIsNotEvidence, match="HYPOTHESIS"):
        r.as_claim()
    # It still carries its number — the Gym must be free to compute.
    assert r.value == 14.2
    assert "not evidence" in str(r)


# ── WALL 2: every search leaves a lineage row ───────────────────────────────

def test_a_lineage_row_records_why_its_parent_failed(tmp_path):
    p = tmp_path / "lineage.jsonl"
    G.record_lineage(G.LineageRow(
        candidate_id="c2", campaign=G.CAMPAIGN,
        hypothesis="re-enter on vol rollover rather than after 10 days",
        parent_id="c1",
        parent_failure="fixed 10-day re-entry beat it, so the exit carried no "
                       "information beyond the calendar"), path=p)

    rows = G.read_lineage(p)
    assert rows[0]["parent_id"] == "c1"
    assert "no information" in rows[0]["parent_failure"]
    # Every row says so, so a row cannot be lifted out of context and quoted.
    assert rows[0]["citable"] is False


def test_an_unledgered_search_is_reported_not_assumed_clean(tmp_path):
    p = tmp_path / "lineage.jsonl"
    G.record_lineage(G.LineageRow(candidate_id="c1", campaign=G.CAMPAIGN,
                                  hypothesis="h"), path=p)

    assert G.unledgered_search_warning(1, path=p) is None
    warn = G.unledgered_search_warning(500, path=p)
    # 499 searches with no lineage row means the campaign's true
    # multiple-comparison count is unknown, and every deflation understates.
    assert warn and "UNKNOWN" in warn


# ── WALL 3: the parent may not prove the rule ───────────────────────────────

def test_export_is_refused_when_the_origin_episode_is_in_the_test_set():
    t = G.TransferTest(mechanism="buy the capitulation",
                       origin_episode_ids=["e_apr2020"],
                       tested_episode_ids=["e_apr2020", "e_2008", "e_2011"],
                       slices=["2008", "2011", "2020"],
                       result_by_slice={"2008": {"passed": True},
                                        "2011": {"passed": True},
                                        "2020": {"passed": True}})

    rep = G.request_export("buy the capitulation", t,
                           preregistration_id="PREREG-X",
                           forward_certification_id="FWD-X")

    assert rep["exportable"] is False
    assert any("GENERATED" in m for m in rep["missing"])


def test_export_is_refused_without_forward_certification():
    t = G.TransferTest(mechanism="m", origin_episode_ids=["a"],
                       tested_episode_ids=["b", "c", "d"],
                       result_by_slice={"s1": {"passed": True},
                                        "s2": {"passed": True},
                                        "s3": {"passed": True}})

    rep = G.request_export("m", t, preregistration_id="PREREG-X")

    # The Gym cannot certify itself: historical data is contaminated by
    # everything we have already learned from it (R8).
    assert rep["exportable"] is False
    assert any("forward certification" in m for m in rep["missing"])


def test_export_is_refused_with_too_few_independent_slices():
    t = G.TransferTest(mechanism="m", origin_episode_ids=["a"],
                       tested_episode_ids=["b"],
                       result_by_slice={"s1": {"passed": True}})

    rep = G.request_export("m", t, preregistration_id="P",
                           forward_certification_id="F")

    assert rep["exportable"] is False
    assert any("needs 3" in m for m in rep["missing"])


def test_a_fully_earned_mechanism_can_leave():
    t = G.TransferTest(mechanism="m", origin_episode_ids=["a"],
                       tested_episode_ids=["b", "c", "d"],
                       result_by_slice={"s1": {"passed": True},
                                        "s2": {"passed": True},
                                        "s3": {"passed": True}})

    rep = G.request_export("m", t, preregistration_id="PREREG-X",
                           forward_certification_id="FWD-X")

    assert rep["exportable"] is True
    assert rep["missing"] == []


# ── unlucky, or wrong in a way the data already knew? ───────────────────────

def _br(p_up, n=1248, key="vix25-35"):
    from backend.services.research_gym.base_rate import BaseRate
    return BaseRate(state_key=key, n=n, p_up=p_up,
                    mean_forward_return_pct=4.6,
                    median_forward_return_pct=4.0, horizon_days=63)


def test_a_view_contradicting_the_states_own_history_is_learnable_not_unlucky():
    """The distinction the first taxonomy could not draw.

    Dataset zero measured P(up | VIX>=35) = 0.731 over n=353 since 1990, with a
    mean 63-day return of +6.97%. An engine that expected DOWN in that state was
    not unlucky — it was on the wrong side of its own data, before the outcome
    was known.
    """
    ep = _ep(p_up=0.35, realised=15.6)
    s = G.replay(ep, _path(0.0023))

    G.attribute_in_place(ep, s, base_rate=_br(0.731, n=353, key="vix>=35"))

    assert ep.failure_mode == G.STATE_TO_FORECAST_FAILURE
    assert "read correctly" in ep.failure_detail
    assert "0.73" in ep.failure_detail


def test_a_view_agreeing_with_the_base_rate_that_still_lost_is_an_unlucky_draw():
    # Believed down in a state that really does go down, and it went up.
    # Nothing to fix here, and "fixing" it is fitting noise.
    ep = _ep(p_up=0.35, realised=15.6)
    s = G.replay(ep, _path(0.0023))

    G.attribute_in_place(ep, s, base_rate=_br(0.30))

    assert ep.failure_mode == G.FORECAST_FAILURE
    assert "unlucky draw" in ep.failure_detail


def test_a_thin_base_rate_declines_to_judge():
    ep = _ep(p_up=0.35, realised=15.6)
    s = G.replay(ep, _path(0.0023))

    G.attribute_in_place(ep, s, base_rate=_br(0.9, n=4))

    # "Too thin to say" is a real answer and must not be read as "no
    # disagreement" — which would quietly clear every forecast in a rare state.
    assert ep.failure_mode == G.FORECAST_FAILURE
    assert "too thin" in ep.failure_detail


def test_with_no_base_rate_the_classifier_says_so_rather_than_assuming():
    ep = _ep(p_up=0.35, realised=15.6)
    s = G.replay(ep, _path(0.0023))

    G.attribute_in_place(ep, s)

    assert ep.failure_mode == G.FORECAST_FAILURE
    assert "UNKNOWN" in ep.failure_detail


def test_a_base_rate_near_a_coin_flip_convicts_nobody():
    from backend.services.research_gym.base_rate import disagrees_with_base_rate
    # 0.52 must not convict a forecast of 0.48. The question is whether the view
    # was on the wrong side of a CLEAR tendency, not whether it differed from a
    # coin flip by a rounding error.
    assert disagrees_with_base_rate(0.48, _br(0.52)) is False
    assert disagrees_with_base_rate(0.48, _br(0.75)) is True
    assert disagrees_with_base_rate(0.60, _br(0.75)) is False


def test_the_vix_buckets_are_fixed_in_advance():
    # Not tuned. A bucketing chosen after seeing which cut makes the finding
    # strongest is an unledgered search wearing the clothes of a definition.
    assert G.vix_bucket(9.0) == "vix<15"
    assert G.vix_bucket(22.0) == "vix20-25"
    assert G.vix_bucket(57.0) == "vix>=35"
