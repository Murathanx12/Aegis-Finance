"""P0.5 — the objective was never declared, and the obvious fix changes nothing.

WHAT WAS WRONG
==============
`ResponseSurface.ranked()` sorted on `net_return_pct`, and `PolicyResult`
carried no path risk at all. So "the best counterfactual" meant "the highest
raw terminal return" out of a menu containing 1.25x and 1.5x levered arms, and
nothing on the record named the objective.

WHAT THIS FILE PINS HARDEST
===========================
Not the new machinery — the TRAP. A `utility_score = log(final_wealth)`
property would have shipped, changed no ranking anywhere (log is monotonic in
terminal wealth), and been reported as "the objective does not change the
answer". `test_a_PER_PATH_log_utility_would_have_reordered_NOTHING` is that
non-result, measured, so nobody has to rediscover it; and `score_one` raises
for distribution objectives so the tautology cannot be computed by accident.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from backend.services.research_gym import counterfactual as CF
from backend.services.research_gym import policies as PL
from backend.services.research_gym import utility as U
from backend.services.research_gym import utility_tensor as UT


# ── path statistics ─────────────────────────────────────────────────────────

def test_a_policy_result_now_carries_the_route_not_only_the_endpoint():
    r = PL.run_policy("hold", [0.01, -0.02, 0.03], cost_bps=0.0)
    assert len(r.wealth_path) == 3
    s = U.stats_of(r)
    assert s is not None and s.n_days == 3
    assert s.max_drawdown_pct > 0            # it fell on day 2
    assert s.terminal_wealth == pytest.approx(1.01 * 0.98 * 1.03)


def test_two_paths_with_the_SAME_endpoint_have_different_risk():
    """The entire argument for keeping the path.

    Same terminal wealth by construction; one gets there smoothly and one
    through a 30% hole. Raw return cannot tell them apart and every ranked
    comparison in the Gym was raw return.
    """
    smooth = [0.01] * 30
    # Same terminal wealth to within a fraction of a percent, by construction:
    # 1.01**30 == (0.95**7) * (x**20)  =>  x = 1.033434
    rough = [-0.05] * 7 + [0.0] * 3 + [0.033434] * 20
    a = U.path_stats(_wealth(smooth))
    b = U.path_stats(_wealth(rough))
    assert abs(a.terminal_wealth - b.terminal_wealth) < 0.02
    assert a.max_drawdown_pct < 1.0
    assert b.max_drawdown_pct > 25.0
    assert b.time_under_water_frac > a.time_under_water_frac
    assert U.score_one(U.TOTAL_RETURN, a) == pytest.approx(
        U.score_one(U.TOTAL_RETURN, b), abs=2.0)
    assert U.score_one(U.SORTINO, a) > U.score_one(U.SORTINO, b)


def test_unmeasurable_path_quantities_are_None_and_never_zero():
    s = U.path_stats([1.01])
    assert s.n_days == 1
    assert s.realised_vol_pct is None            # not 0.0
    assert s.downside_deviation_pct is None
    assert s.expected_shortfall_5_pct is None    # needs 20 days
    assert U.path_stats([]) is None


def test_a_drawdown_that_never_recovers_reports_None_not_a_big_number():
    s = U.path_stats(_wealth([-0.10] * 5 + [0.001] * 5))
    assert s.max_drawdown_pct > 9.0
    assert s.recovery_days is None, (
        "'had not recovered by the end of the window' is an unknown, not a "
        "large number")


def test_ruin_is_a_breach_of_the_PATH_not_of_the_endpoint():
    """A path that went through the floor and came back is still ruin. It is
    the difference between a drawdown you sat through and one you could not."""
    down = _wealth([-0.20] * 5 + [0.60] * 4)
    s = U.path_stats(down)
    assert s.min_wealth < U.RUIN_FLOOR
    assert s.terminal_wealth > 1.0
    assert s.ruin is True


# ── the trap ────────────────────────────────────────────────────────────────

def _wealth(daily):
    w, out = 1.0, []
    for r in daily:
        w *= (1.0 + r)
        out.append(w)
    return out


def test_a_PER_PATH_log_utility_would_have_reordered_NOTHING():
    """The measured non-result, kept so it is never rediscovered as a finding.

    This is what shipping `utility_score = log(final_wealth)` would have
    produced: perfect agreement with raw return on every episode, reported as
    evidence that the objective does not matter.
    """
    rng = np.random.default_rng(20260815)
    rets = list(rng.normal(0.0004, 0.02, 90))
    surface = {n: PL.run_policy(n, rets) for n in PL.POLICY_MENU}
    by_return = sorted(surface, key=lambda n: -surface[n].net_return_pct)
    by_log = sorted(surface,
                    key=lambda n: -math.log(max(
                        U.stats_of(surface[n]).terminal_wealth, 1e-9)))
    assert by_return == by_log, (
        "the fixture is broken — per-path log utility MUST agree with raw "
        "return, that is the whole point of the test")

    # And a path objective, on the identical episode, does not.
    by_sortino = sorted(surface,
                        key=lambda n: -U.score_one(U.SORTINO,
                                                   U.stats_of(surface[n])))
    assert by_sortino != by_return


def test_scoring_one_episode_under_a_DISTRIBUTION_objective_RAISES():
    s = U.path_stats(_wealth([0.01] * 10))
    with pytest.raises(U.ObjectiveMisuse, match="monotonic"):
        U.score_one(U.EXPECTED_LOG_GROWTH, s)
    with pytest.raises(U.ObjectiveMisuse):
        U.score_one(U.LOG_GROWTH_WITH_RUIN, s)
    # It is still scoreable over a SET, which is the correct use.
    assert U.score_many(U.EXPECTED_LOG_GROWTH, [s, s]) is not None


def test_expected_log_growth_DOES_reorder_across_a_DISTRIBUTION():
    """Where concavity actually bites: on the spread, not on one path.

    Two policies, same mean arithmetic return, different dispersion. Raw return
    calls them equal; expected log growth prefers the tighter one — which is
    the Kelly result, and it is invisible episode by episode.
    """
    tight = [U.path_stats(_wealth([r / 20] * 20))
             for r in (0.10, 0.10, 0.10, 0.10)]
    wide = [U.path_stats(_wealth([r / 20] * 20))
            for r in (-0.50, 0.70, -0.50, 0.70)]
    mean_t = sum(s.net_return_pct for s in tight) / 4
    mean_w = sum(s.net_return_pct for s in wide) / 4
    assert mean_w > mean_t                        # wide wins on raw return
    assert (U.score_many(U.EXPECTED_LOG_GROWTH, wide)
            < U.score_many(U.EXPECTED_LOG_GROWTH, tight)), (
        "expected log growth did not punish the dispersion — it is then not "
        "doing anything raw return was not already doing")


def test_the_ruin_constraint_is_not_compensable():
    survived = [U.path_stats(_wealth([0.01] * 20))]
    breached = [U.path_stats(_wealth([-0.25] * 5 + [0.35] * 8))]
    assert breached[0].terminal_wealth > survived[0].terminal_wealth
    assert (U.score_many(U.LOG_GROWTH_WITH_RUIN, breached)
            < U.score_many(U.LOG_GROWTH_WITH_RUIN, survived))
    # ...while plain expected-log growth, having no constraint, prefers it.
    assert (U.score_many(U.EXPECTED_LOG_GROWTH, breached)
            > U.score_many(U.EXPECTED_LOG_GROWTH, survived))


# ── break-even risk aversion ────────────────────────────────────────────────

def test_gamma_star_is_where_the_preference_flips_not_a_verdict():
    """'Selling was wrong' is a claim about an undeclared utility.
    'De-risking is worse below gamma* and better above it' is the same
    evidence, stated so four personalities can read their own answer."""
    risky = [1.60, 0.55, 1.60, 0.55]
    safe = [1.05, 1.03, 1.05, 1.03]
    g = U.break_even_gamma(risky, safe)
    assert g is not None and 0.0 < g < 30.0
    below, above = g - 0.5, g + 0.5
    assert U.expected_crra(risky, below) > U.expected_crra(safe, below)
    assert U.expected_crra(risky, above) < U.expected_crra(safe, above)


def test_dominance_reports_None_rather_than_an_invented_crossing():
    always_better = [1.20, 1.30, 1.25, 1.40]
    always_worse = [1.01, 1.02, 1.01, 1.03]
    assert U.break_even_gamma(always_better, always_worse) is None


def test_crra_at_gamma_one_is_the_log_utility():
    assert U.crra_utility(1.4, 1.0) == pytest.approx(math.log(1.4))
    assert U.crra_utility(1.4, 0.0) == pytest.approx(0.4)


# ── the surface names its objective ─────────────────────────────────────────

def _surface(rets):
    s = CF.ResponseSurface(episode_id="e1", security="X",
                           decision_ts="2026-01-02", horizon_days=len(rets),
                           taken_policy="hold")
    s.results = {n: PL.run_policy(n, rets) for n in PL.POLICY_MENU}
    return s


def test_the_historical_default_is_UNCHANGED_and_now_says_so():
    """Nothing published is restated. What changes is that the record names
    the objective the ranking was computed under."""
    rng = np.random.default_rng(7)
    s = _surface(list(rng.normal(0.001, 0.015, 60)))
    assert s.best().name == max(s.results.values(),
                                key=lambda r: r.net_return_pct).name
    d = s.as_dict()
    assert "objective_used" in d
    assert "total_return" in d["objective_used"]


def test_ranking_under_a_named_objective_can_pick_a_DIFFERENT_policy():
    """The levered arms win on raw return in an up window by construction."""
    rets = [0.004] * 40 + [-0.03] * 8 + [0.006] * 40
    s = _surface(rets)
    by_return = s.best().name
    by_dd = s.best("drawdown_penalised_lambda1").name
    assert by_return in ("buy_50", "buy_25")
    assert by_dd != by_return, (
        "a drawdown-penalised objective preferred the same levered arm as raw "
        "return on a window with an 8-day slide — the objective is not wired")
    assert s.objective_used("drawdown_penalised_lambda1") == "drawdown_penalised_lambda1"


def test_the_surface_REFUSES_to_rank_one_episode_by_a_distribution_objective():
    s = _surface([0.01] * 20)
    with pytest.raises(U.ObjectiveMisuse):
        s.ranked("expected_log_growth")


# ── the tensor and the flip atlas ───────────────────────────────────────────

def _series(n=900, seed=11):
    rng = np.random.default_rng(seed)
    rets, states = [], []
    for i in range(n):
        calm = (i // 120) % 2 == 0
        rets.append(float(rng.normal(0.0006 if calm else -0.0004,
                                     0.008 if calm else 0.030)))
        states.append("calm" if calm else "stress")
    return rets, states


def test_the_utility_tensor_recomputes_the_RAW_edge_identically():
    """The two tensors must be checkable against each other rather than
    trusted: a disagreement should be about the OBJECTIVE, never the sample."""
    from backend.services.research_gym import tensor as T

    rets, states = _series(400)
    series = {"AAA": (rets, states)}
    a = T.build_regret_tensor(series, horizons=(20,), stride_days=5)
    b = UT.build_utility_tensor(series, horizons=(20,), stride_days=5,
                                objectives=("total_return",))
    for (st, act, H), cell in a.cells.items():
        u = b.cell(st, act, H, "total_return")
        assert u is not None
        assert u.raw_edge_pp == pytest.approx(cell.mean_edge_vs_default_pp,
                                              abs=1e-9)
        assert u.power.n_effective == pytest.approx(cell.power.n_effective)


def test_every_utility_cell_carries_its_own_MDE():
    rets, states = _series()
    t = UT.build_utility_tensor({"AAA": (rets, states)}, horizons=(20, 60),
                                stride_days=5)
    assert t.cells
    for c in t.cells.values():
        assert c.power.n_effective is not None
        if c.action == t.default_policy:
            # The default's edge against ITSELF is identically zero, so it has
            # no dispersion and no MDE. Worth asserting rather than skipping: a
            # NONZERO sd here would mean the default was being differenced
            # against something other than itself.
            assert c.sd_utility_edge in (None, 0.0)
            assert c.utility_edge == pytest.approx(0.0, abs=1e-12)
            continue
        # §19: a cell that cannot print an MDE may not be read as a finding.
        assert (c.power.mde_mean_pct is not None) or (c.sd_utility_edge is None) \
            or c.power.n_effective < 2.0


def test_the_flip_atlas_reports_WHERE_the_preferred_action_changes():
    rets, states = _series()
    t = UT.build_utility_tensor({"AAA": (rets, states)},
                                horizons=(20, 60), stride_days=5)
    flips = t.flips()
    assert flips, "no flips at all is suspicious on a two-regime series"
    for f in flips:
        assert f.best_under_reference != f.best_under_objective
        assert f.reference_objective == "total_return"
        # A flip is not a finding until its gap clears the MDE of the DIFFERENCE.
        assert f.material in (True, False, None)


def test_a_flip_below_its_MDE_is_NOT_material():
    """§19 does not stop applying because the quantity became interesting."""
    rets, states = _series(300)
    t = UT.build_utility_tensor({"AAA": (rets, states)}, horizons=(60,),
                                stride_days=5)
    graded = [f for f in t.flips() if f.mde_of_gap is not None]
    for f in graded:
        assert f.material == (abs(f.gap_under_objective) >= f.mde_of_gap)


def test_the_tensor_records_gamma_star_per_state_and_horizon():
    rets, states = _series()
    t = UT.build_utility_tensor({"AAA": (rets, states)}, horizons=(20,),
                                stride_days=5)
    assert t.gamma_star
    # None is a legitimate answer — it means one policy dominates at every
    # risk aversion, which is a stronger statement than a crossing.
    assert all(v is None or 0.0 <= v <= 30.0 for v in t.gamma_star.values())


def test_the_tensor_serialises_with_its_atlas_and_names_its_reference():
    rets, states = _series(400)
    t = UT.build_utility_tensor({"AAA": (rets, states)}, horizons=(20,),
                                stride_days=5)
    d = t.as_dict()
    assert d["reference_objective"] == "total_return"
    assert d["objectives"][0] == "total_return"
    assert d["n_cells"] == len(d["cells"])
    assert "flip_atlas" in d and "gamma_star" in d


def test_an_undeclared_objective_is_refused_by_name():
    with pytest.raises(KeyError, match="unknown objective"):
        U.get_objective("sharpe_but_nicer")


def test_the_aggressive_objective_is_configurable_and_NOT_the_default():
    assert UT.REFERENCE_OBJECTIVE == "total_return"
    assert not any(o.startswith("aggressive")
                   for o in (UT.REFERENCE_OBJECTIVE,))
    a = U.aggressive_growth(dd_lambda=0.0)
    b = U.aggressive_growth(dd_lambda=2.0)
    s = U.path_stats(_wealth([-0.08] * 4 + [0.05] * 10))
    assert U.score_one(a, s) > U.score_one(b, s)
    # Risk-seeking, but ruin is still terminal.
    ruined = U.path_stats(_wealth([-0.30] * 4 + [0.9] * 4))
    assert ruined.ruin and U.score_one(a, ruined) == -100.0


def test_the_net_path_and_the_scalar_net_return_agree_to_a_cost_term():
    """They are computed differently on purpose — one charges turnover once at
    the end, the other as it is incurred — so the gap is bounded and stated
    rather than discovered later as a discrepancy."""
    rng = np.random.default_rng(3)
    rets = list(rng.normal(0.0005, 0.02, 120))
    for name in PL.POLICY_MENU:
        r = PL.run_policy(name, rets)
        gap = abs(r.path_net_return_pct - r.net_return_pct)
        assert gap < 1.0, (name, gap, r.turnover)


# ── the first positive result was an artefact, and the guard says so ────────

def test_a_lambda_1_drawdown_penalty_makes_CASH_optimal_and_is_flagged():
    """The atlas's first real run reported 13 MATERIAL flips. All thirteen
    were this objective, and all thirteen were `buy_50 -> sell_100`.

    A zero-exposure policy has zero return AND zero drawdown, so it scores ~0
    while any long policy whose drawdown exceeds its return scores below zero.
    The optimum is cash for a reason that has nothing to do with markets. §37
    says check the kills as hard as the passes; a new instrument's first
    POSITIVE result deserves the same treatment, because that is the one that
    looks like it working.
    """
    rets, states = _series()
    t = UT.build_utility_tensor({"AAA": (rets, states)}, horizons=(20, 60),
                                stride_days=5)
    deg = t.degenerate_objectives()
    assert deg["drawdown_penalised_lambda1"]["degenerate"] is True
    assert deg["drawdown_penalised_lambda1"]["frac_prefers_cash"] >= 0.5
    assert deg["total_return"]["degenerate"] is False
    assert "degenerate_objectives" in t.as_dict()


def test_cash_scores_zero_under_a_drawdown_penalty_which_is_the_whole_problem():
    flat = U.path_stats(_wealth([0.0] * 20))
    # A path that ends up 6% and got there through a 26% hole. Any investor
    # would call that a win; a lambda=1.0 penalty calls it worse than cash.
    risky = U.path_stats(_wealth([-0.05] * 6 + [0.02649] * 14))
    assert U.score_one(U.DRAWDOWN_PENALISED, flat) == pytest.approx(0.0)
    assert risky.net_return_pct > 0.0
    assert U.score_one(U.DRAWDOWN_PENALISED, risky) < 0.0
    # And a lighter penalty does not automatically prefer cash.
    assert U.score_one(U.DRAWDOWN_PENALISED_LIGHT, risky) > \
        U.score_one(U.DRAWDOWN_PENALISED, risky)


def test_gamma_star_carries_a_BOOTSTRAP_INTERVAL_not_just_a_point():
    """0.35 and 2.86 look like a large difference between two states until
    both intervals turn out to span the plausible range of risk aversions."""
    rng = np.random.default_rng(5)
    a = list(1.0 + rng.normal(0.10, 0.35, 60))
    b = list(1.0 + rng.normal(0.04, 0.06, 60))
    ci = U.bootstrap_gamma_star(a, b, n_boot=200)
    assert ci["n_boot"] == 200
    assert 0.0 <= ci["frac_crossing"] <= 1.0
    if ci["lo"] is not None:
        assert ci["lo"] <= ci["hi"]


def test_the_bootstrap_resamples_episodes_in_PAIRS():
    """Resampling the two policies independently would inject a difference
    that is not in the data. Identical inputs must give gamma* everywhere or
    nowhere — never a spurious crossing."""
    xs = [1.1, 0.9, 1.3, 0.8, 1.05, 0.95] * 5
    ci = U.bootstrap_gamma_star(xs, list(xs), n_boot=100)
    assert ci["frac_crossing"] == 0.0, (
        "two identical policies produced a break-even risk aversion — the "
        "resampling is not paired")
