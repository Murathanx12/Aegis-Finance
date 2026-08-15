"""G1 + G2: the regret denominator has a non-zero null, and `n` is not `n`.

WHAT WENT WRONG, AND WHY TESTS DID NOT CATCH IT
===============================================
`RESEARCH-GYM-1` shipped with thirty passing tests. All thirty were about
whether the machinery computed what it said it computed, and it did. None asked
the only question that mattered: **what does this number read for a decision
nobody could fault?**

Measured afterwards on real index history:

  * regret vs the ex-post best of 17 policies is ~+5pp for always-HOLD and
    ~+17pp for a full sell after VIX>=35 — for a decision-maker with no skill
    at all, because a maximum over seventeen noisy draws is biased upward;
  * `MATERIAL_EDGE_PCT = 1.0` was cleared by a blameless hold **93%** of the
    time, so 27 of dataset zero's 28 HOLDs were labelled failures by the
    threshold rather than by the evidence;
  * `n=353` for the VIX>=35 bucket is 353 daily observations of a 63-day window
    covering 19 episodes — an effective sample of **5.6**.

So these tests are written the other way round: each one starts from a decision
that is knowably blameless, or a sample that is knowably thin, and asserts the
machinery says so.
"""

from __future__ import annotations

import math

import pytest

from backend.services import research_gym as G
from backend.services.research_gym import power as PW
from backend.services.research_gym import regret as RG


# ── G2: what a row of overlapping windows is actually worth ─────────────────

def test_sixty_consecutive_stress_days_are_one_episode_not_sixty():
    # March-May 2020 above VIX 35 is one crisis. An overlap correction that
    # only divides by the horizon cannot know that, which is why episodes are
    # counted separately.
    assert PW.count_episodes(list(range(60))) == 1
    assert PW.count_episodes(list(range(60)) + list(range(500, 520))) == 2


def test_two_stress_windows_a_month_apart_are_still_one_episode():
    # 21 trading days is the declared gap: long enough that the second burst is
    # not the tail of the first, short enough that 2008 and 2009 do not fuse.
    assert PW.count_episodes([0, 1, 2, 20]) == 1
    assert PW.count_episodes([0, 1, 2, 30]) == 2


def test_the_vix35_row_is_worth_about_five_observations_not_353():
    n_eff = PW.overlap_effective_n(353, 63)
    assert 5.0 < n_eff < 6.0
    # And the value actually used takes the smaller of the two shrinkages.
    assert PW.effective_n(353, 63, n_episodes=19) == pytest.approx(n_eff, 0.01)


def test_effective_n_takes_the_harsher_correction_never_the_kinder():
    # 2,947 calm days over 31 episodes: overlap says 46.8, clustering says 31.
    # Picking the larger would let whichever correction happened to be gentler
    # set the sample size — choosing the flattering denominator by construction.
    assert PW.effective_n(2947, 63, n_episodes=31) == 31.0


def test_an_mde_is_refused_below_two_effective_observations():
    # A "minimum detectable effect" computed on 1.2 windows has the shape of a
    # bound and none of the meaning.
    assert PW.mde_mean(10.0, 1.5) is None
    assert PW.mde_mean(10.0, 5.6) is not None


def test_the_mde_is_the_declared_80_percent_power_two_sided_5_percent():
    got = PW.mde_mean(sd=20.0, n_effective=5.6)
    assert got == pytest.approx(2.8016 * 20.0 / math.sqrt(5.6), rel=1e-3)


def test_every_power_row_states_why_its_n_shrank():
    p = PW.power_for(n_obs=353, horizon_days=63, sd=20.0, n_episodes=19)
    d = p.as_dict()
    assert d["n_obs"] == 353 and d["n_effective"] == pytest.approx(5.603, 0.01)
    assert "353 daily observations" in d["note"]
    assert "19 distinct episodes" in d["note"]
    assert p.is_reportable          # SS19: a row with no MDE is not publishable


# ── G2: a disagreement is graded, not asserted ──────────────────────────────

def _br(p_up, n=353, n_episodes=19, horizon=63, sd=20.0, key="vix>=35"):
    from backend.services.research_gym.base_rate import BaseRate
    return BaseRate(state_key=key, n=n, p_up=p_up,
                    mean_forward_return_pct=6.97, median_forward_return_pct=5.0,
                    horizon_days=horizon, sd_forward_return_pct=sd,
                    power=PW.power_for(n, horizon, sd, n_episodes=n_episodes))


def test_the_vix35_disagreement_is_suggestive_and_says_so():
    # P(up | VIX>=35) = 0.73 against a believed 0.35 IS a disagreement, and at
    # n_effective 5.6 it cannot be established. Both facts are reported; the
    # old bare `True` reported only the first and read like a measurement.
    a = G.assess(0.35, _br(0.731))
    assert a.disagrees is True
    assert a.strength == G.SUGGESTIVE
    assert "BELOW the 80%-power MDE" in a.detail
    assert "n_effective 5.6" in a.detail


def test_a_disagreement_on_a_thick_bucket_is_established():
    # 2,785 days over 72 episodes -> n_effective 44.2; the same 0.73 clears it.
    a = G.assess(0.35, _br(0.731, n=2785, n_episodes=72, key="vix15-20"))
    assert a.disagrees is True
    assert a.strength == G.ESTABLISHED


def test_a_base_rate_near_a_coin_flip_still_convicts_nobody():
    a = G.assess(0.48, _br(0.52))
    assert a.disagrees is False and a.strength == G.ESTABLISHED


def test_too_thin_is_not_agreement():
    a = G.assess(0.35, _br(0.9, n=4, n_episodes=1))
    assert a.disagrees is None
    assert a.strength == G.TOO_THIN
    assert "NOT the same as agreement" in a.detail


# ── G2 / SS18: the U-shape is a difference and must be tested as one ─────────

def test_the_u_shape_is_measured_as_a_difference_not_read_off_a_column():
    """Five means in a column let the eye supply a curve. SS18 says otherwise.

    The real numbers: trough at VIX 20-25 (+1.56%) and right arm at VIX>=35
    (+6.97%). The gap looks large. At the EFFECTIVE sample sizes it is not
    distinguishable from flat, and this is the test that says so.
    """
    from backend.services.research_gym.base_rate import bucket_difference
    trough = _br(0.643, n=1824, n_episodes=68, sd=8.61, key="vix20-25")
    trough = type(trough)(**{**trough.__dict__,
                             "mean_forward_return_pct": 1.56})
    right = _br(0.731, n=353, n_episodes=19, sd=12.90, key="vix>=35")

    d = bucket_difference(right, trough)
    assert d.diff_pct == pytest.approx(6.97 - 1.56, abs=1e-6)
    # The SE is dominated by the thin arm: 5.6 effective observations, not 353.
    assert d.se_pct == pytest.approx(5.68, abs=0.15)
    assert abs(d.t_stat) < 1.5
    assert d.is_detectable is False


def test_the_difference_uses_effective_n_not_the_daily_count():
    """Using `n` here would shrink the SE by ~sqrt(63) and manufacture a shape."""
    from backend.services.research_gym.base_rate import bucket_difference
    a = _br(0.731, n=353, n_episodes=19, sd=12.90, key="vix>=35")
    d = bucket_difference(a, _br(0.643, n=1824, n_episodes=68, sd=8.61,
                                 key="vix20-25"))
    naive_se = math.sqrt(12.90 ** 2 / 353 + 8.61 ** 2 / 1824)
    assert d.se_pct > 5 * naive_se


def test_a_difference_without_dispersion_declines_to_report_a_t():
    from backend.services.research_gym.base_rate import BaseRate, \
        bucket_difference
    bare = BaseRate("a", 100, 0.6, 5.0, 4.0, 63)
    d = bucket_difference(bare, bare)
    assert d.se_pct is None and d.t_stat is None and d.is_detectable is None


# ── G1: the null, and the three denominators ────────────────────────────────

def _null(cost_bps=10.0, horizon=63, universe="^GSPC", mean=17.31, p90=35.16,
          menu=("hold", "sell_100", "buy_25")):
    cell = RG.NullCell(
        state_key="vix>=35", policy="sell_100", mean_regret_pct=mean,
        percentiles={10: 2.0, 25: 6.0, 50: 12.0, 75: 24.0, 90: p90, 95: 41.0},
        power=PW.power_for(353, horizon, 20.0, n_episodes=19))
    mn = RG.MatchedNull(universe=universe, horizon_days=horizon,
                        cost_bps=cost_bps, menu_hash=RG.menu_hash(menu),
                        sample_start="1990-01-04", sample_end="2026-08-14")
    mn.cells[("vix>=35", "sell_100")] = cell
    mn.pooled["sell_100"] = cell
    return mn


class _R:
    def __init__(self, name, net):
        self.name, self.net_return_pct = name, net
        self.gross_return_pct, self.cost_pct, self.turnover = net, 0.0, 0.0
        self.first_divergence_day = None


class _S:
    """A minimal surface. The real one is exercised elsewhere; here the point
    is the arithmetic of the denominators, not the replay."""
    def __init__(self, taken="sell_100", cost_bps=10.0, horizon=63, **nets):
        self.taken_policy, self.cost_bps, self.horizon_days = (taken, cost_bps,
                                                               horizon)
        self.results = {k: _R(k, v) for k, v in nets.items()}

    @property
    def taken(self):
        return self.results.get(self.taken_policy)

    def best(self):
        return max(self.results.values(), key=lambda r: r.net_return_pct)


def test_the_headline_denominator_is_reported_as_an_upper_bound():
    t = RG.regret_triple(_S(hold=20.0, sell_100=0.0, buy_25=25.0),
                         state_key="vix>=35", matched_null=_null())
    assert t.vs_ex_post_best == pytest.approx(25.0)
    assert "UPPER BOUND" in t.as_dict()["vs_ex_post_best_note"]


def test_a_good_decision_can_score_NEGATIVE_regret_against_the_fixed_default():
    # The property the ex-post-best denominator structurally cannot have. A
    # denominator that can never exonerate is not a measurement of skill.
    t = RG.regret_triple(_S(taken="sell_100", hold=-30.0, sell_100=0.0),
                         state_key="vix>=35",
                         matched_null=_null(menu=("hold", "sell_100")))
    assert t.vs_fixed_default == pytest.approx(-30.0)
    assert t.vs_ex_post_best >= 0.0


def test_excess_over_the_null_is_the_headline_minus_what_a_blameless_actor_scores():
    # Dataset zero in miniature: 26.5pp of raw regret against a null of 17.31pp
    # for exactly this state and action is +9.2pp of excess, not +26.5pp.
    t = RG.regret_triple(_S(hold=26.5, sell_100=0.0), state_key="vix>=35",
                         matched_null=_null(menu=("hold", "sell_100")))
    assert t.vs_ex_post_best == pytest.approx(26.5)
    assert t.excess_vs_matched_null == pytest.approx(26.5 - 17.31, abs=1e-9)
    assert t.match_quality == "state_and_action"
    assert t.is_interpretable


def test_without_a_null_the_triple_says_it_is_not_interpretable():
    t = RG.regret_triple(_S(hold=26.5, sell_100=0.0))
    assert t.excess_vs_matched_null is None
    assert t.is_interpretable is False
    assert t.match_quality == "no_null_supplied"


def test_a_missing_state_cell_falls_back_to_pooled_and_SAYS_it_did():
    t = RG.regret_triple(_S(hold=26.5, sell_100=0.0), state_key="vix<15",
                         matched_null=_null(menu=("hold", "sell_100")))
    assert t.match_quality == "action_only_pooled_over_states"


# ── G1: matchedness is enforced, because it was got wrong once ──────────────

def test_a_null_measured_at_a_different_cost_is_REFUSED_not_subtracted():
    # The first measurement of this null ran on SPY at 5bps while dataset zero
    # ran on ^GSPC at 10bps — three mismatches inside a comparison whose only
    # purpose is to be matched.
    with pytest.raises(RG.NullMismatch, match="5.0bps"):
        RG.regret_triple(_S(hold=26.5, sell_100=0.0, cost_bps=10.0),
                         state_key="vix>=35",
                         matched_null=_null(cost_bps=5.0,
                                            menu=("hold", "sell_100")))


def test_a_null_measured_over_a_different_horizon_is_REFUSED():
    with pytest.raises(RG.NullMismatch, match="horizon"):
        RG.regret_triple(_S(hold=26.5, sell_100=0.0, horizon=63),
                         state_key="vix>=35",
                         matched_null=_null(horizon=21,
                                            menu=("hold", "sell_100")))


def test_a_null_measured_on_a_different_universe_is_REFUSED():
    with pytest.raises(RG.NullMismatch, match="universe"):
        RG.regret_triple(_S(hold=26.5, sell_100=0.0), state_key="vix>=35",
                         matched_null=_null(universe="SPY",
                                            menu=("hold", "sell_100")),
                         universe="^GSPC")


def test_a_null_measured_against_a_DIFFERENT_MENU_is_refused():
    """The gap this closes was found by auditing the file, not by it failing.

    `menu_hash` was introduced in this module precisely because regret against
    the best of 17 and against the best of 25 are different quantities — and
    then nothing compared it. Adding one policy to `POLICY_MENU` would have
    silently raised every historical regret figure against an unchanged null,
    in the direction that makes the engine look worse, with no error anywhere.
    """
    with pytest.raises(RG.NullMismatch, match="menu"):
        RG.regret_triple(_S(hold=26.5, sell_100=0.0), state_key="vix>=35",
                         matched_null=_null(menu=("hold", "sell_100",
                                                  "a_new_policy")))


def test_the_real_menu_and_the_real_null_agree():
    """The check must not fire on the pipeline it is meant to protect."""
    from backend.services.research_gym.policies import POLICY_MENU
    assert RG.menu_hash(POLICY_MENU.keys()) == RG.menu_hash(list(POLICY_MENU))


def test_the_menu_is_part_of_the_number_identity():
    # Regret vs the best of 17 and vs the best of 25 are different quantities.
    # Without this, adding a policy silently worsens every historical number.
    assert RG.menu_hash(["a", "b"]) != RG.menu_hash(["a", "b", "c"])
    assert RG.menu_hash(["b", "a"]) == RG.menu_hash(["a", "b"])


# ── G1: the gate that replaced the round number ─────────────────────────────

def test_the_gate_is_a_percentile_of_the_matched_null_and_names_its_source():
    thr, why = RG.failure_threshold_pct(_null().cells[("vix>=35", "sell_100")])
    assert thr == pytest.approx(35.16)
    assert "p90 of the matched null" in why
    assert "n_effective 5.6" in why


def test_the_uncalibrated_fallback_announces_that_it_is_uncalibrated():
    thr, why = RG.failure_threshold_pct(None, fallback_pct=1.0)
    assert thr == 1.0
    assert why.startswith("UNCALIBRATED")
    assert "has not been shown to exceed what a blameless decision scores" in why


def test_the_old_gate_convicts_and_the_calibrated_gate_does_not():
    """The defect, as one assertion.

    A 26.5pp regret on a full sell after VIX>=35 clears the old 1.0pp gate by a
    factor of twenty-six and reads as an enormous failure. Against what a
    blameless sell in that same state actually scores, it does not even reach
    the 90th percentile.
    """
    cell = _null().cells[("vix>=35", "sell_100")]
    raw = 26.5
    assert raw > G.MATERIAL_EDGE_PCT                     # old gate: FAILURE
    thr, _ = RG.failure_threshold_pct(cell)
    assert raw < thr                                     # new gate: NO FAILURE


# ── G1: the artifact survives the round trip ────────────────────────────────

def test_a_written_null_reads_back_with_its_power_intact(tmp_path):
    p = _null().write(tmp_path / "n.json")
    back = RG.MatchedNull.read(p)
    assert back.universe == "^GSPC" and back.cost_bps == 10.0
    c = back.cells[("vix>=35", "sell_100")]
    assert c.mean_regret_pct == pytest.approx(17.31)
    assert c.percentile(90) == pytest.approx(35.16)
    # The power block is the part a reader needs and the easiest to drop.
    assert c.power.n_obs == 353
    assert c.power.n_effective == pytest.approx(5.603, 0.01)


# ── the null is real, not an artifact of my arithmetic ──────────────────────

def test_a_blameless_actor_scores_large_positive_regret_on_random_walks():
    """The claim underneath everything above, measured rather than asserted.

    Returns here have zero drift and no predictability, so no policy on the
    menu has any edge and every decision is blameless by construction. If the
    denominator were unbiased, mean regret would be ~0. It is not.
    """
    import numpy as np
    rng = np.random.default_rng(20260815)
    rets = list(rng.normal(0.0, 0.01, 3000))
    mn = RG.build_matched_null(rets, ["flat"] * len(rets), universe="synthetic",
                               horizon_days=63, cost_bps=10.0,
                               sample_start="x", sample_end="y")
    hold = mn.cells[("flat", "hold")]
    assert hold.mean_regret_pct > 3.0, (
        "a zero-edge market must still show large positive regret under the "
        "ex-post-best denominator; if this ever fails, the bias G1 describes "
        "has gone away and the three-denominator machinery can be simplified")
    # And the old gate would have convicted the overwhelming majority of them.
    assert hold.percentile(10) > G.MATERIAL_EDGE_PCT


def test_the_null_builder_refuses_states_that_do_not_line_up_with_returns():
    with pytest.raises(ValueError, match="aligned index-for-index"):
        RG.build_matched_null([0.01] * 100, ["a"] * 99, universe="x",
                              horizon_days=10, cost_bps=10.0,
                              sample_start="x", sample_end="y")


# ── N8: sizing a corpus (added 2026-08-16) ──────────────────────────────────

def test_n_required_is_the_exact_inverse_of_the_MDE():
    """If a corpus of n can just detect d, then d needs exactly n."""
    from backend.services.research_gym import power as P

    sd, n = 12.0, 40.0
    d = P.mde_mean(sd, n)
    assert P.n_required_for(d, sd) == pytest.approx(n, rel=1e-9)


def test_n_required_scales_with_the_INVERSE_SQUARE_of_the_effect():
    """The property that makes N8's headline unusable and its curve usable.

    Halving the effect of interest quadruples the corpus. So a requirement
    computed from an effect measured on two observations inherits that
    effect's whole uncertainty, squared and inverted — measured across the six
    autopsied mechanisms, the implied requirement spanned 0.9 to 1,534
    episodes.
    """
    from backend.services.research_gym import power as P

    a = P.n_required_for(4.0, 20.0)
    b = P.n_required_for(2.0, 20.0)
    assert b == pytest.approx(4.0 * a)


def test_the_design_curve_reproduces_the_numbers_the_atlas_is_sized_from():
    """Crisis dispersion is ~12x calm dispersion, and n goes as sd^2, so the
    scarcity is concentrated entirely in the states every mechanism is about."""
    from backend.services.research_gym import power as P

    crisis = P.design_curve(17.69)
    calm = P.design_curve(1.48)
    assert round(crisis[3.0]) == 273
    assert round(crisis[10.0]) == 25
    assert round(calm[1.0]) == 17
    # 144x more episodes for the same edge, purely from dispersion.
    assert crisis[3.0] / calm[3.0] == pytest.approx((17.69 / 1.48) ** 2,
                                                    rel=1e-6)


def test_the_GYMS_OWN_recalibrated_bar_needs_the_corpus_it_already_has():
    """An internal-consistency check worth keeping.

    G1 recalibrated the failure threshold at VIX>=35 from 1.0pp to 35.16pp,
    because that is the percentile of the state-and-action-matched null. At the
    crisis dispersion, an effect that large needs about TWO independent
    episodes — and the affected cells carry about two. The corpus is adequate
    for the bar the Gym actually applies and hopeless for a 1-3pp bar, and
    those two facts have always been the same fact.
    """
    from backend.services.research_gym import power as P

    assert round(P.n_required_for(35.16, 17.69)) == 2


def test_a_zero_effect_has_no_finite_requirement():
    from backend.services.research_gym import power as P

    assert P.n_required_for(0.0, 10.0) is None
    assert P.n_required_for(5.0, 0.0) is None
    assert P.n_required_for(None, 10.0) is None
