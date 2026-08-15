"""Scope-aware verdicts — the ruling of 2026-08-16, pinned.

THE DEFECT THESE TESTS EXIST FOR
================================
`Autopsy` required `expected_unaffected_states`, validated them, and wrote them
to the lineage row. `adjudicate()` then produced its verdict from a FLAT COUNT
of slices where `passed` was true. The declaration changed no outcome.

So a mechanism that is real in its declared regime and correctly silent
everywhere else scored its correctly-silent slices as failures and came back
`REFUSED — survived 1 of 3`. The machinery could not tell *does not generalise*
from *is conditional, exactly as declared* — and it collected the discriminating
half of every hypothesis and threw it away.

The fix makes the bar HARDER, not looser. A declared-unaffected region is now a
placebo arm: silence there is confirming, and a strong effect there is
disconfirming, because firing everywhere is what beta does.
"""

from __future__ import annotations

import pytest

from backend.services.research_gym import autopsy as A
from backend.services.research_gym import scope as SC


# ── the vocabulary itself ───────────────────────────────────────────────────

def test_there_are_exactly_nine_verdicts_and_the_set_is_closed():
    assert len(SC.VERDICTS) == 9
    with pytest.raises(SC.ScopeRefused, match="not one of the nine"):
        SC.ScopedVerdict("DEAD", "everywhere", "it died")


def test_only_two_verdicts_close_anything():
    """And the first closes only its own scope."""
    assert SC.CLOSING_VERDICTS == {SC.REFUTED_IN_SCOPE, SC.STRUCTURALLY_CLOSED}
    for v in SC.VERDICTS:
        sv = SC.ScopedVerdict(
            v, "some region", "reason",
            revisit_when="x" if v in SC.NON_SUPPORT else "",
            closure_ground=("mathematical_impossibility"
                            if v == SC.STRUCTURALLY_CLOSED else ""))
        assert sv.closes_anything == (v in SC.CLOSING_VERDICTS)


def test_a_negative_without_a_resurrection_condition_is_refused():
    """A kill without a revisit_when is how a project loses ideas it never
    disproved."""
    with pytest.raises(SC.ScopeRefused, match="no revisit_when"):
        SC.ScopedVerdict(SC.NOT_DETECTABLE_IN_SCOPE, "VIX>=35", "below MDE")
    ok = SC.ScopedVerdict(SC.NOT_DETECTABLE_IN_SCOPE, "VIX>=35", "below MDE",
                          revisit_when="n_effective on this slice reaches 40")
    assert ok.as_dict()["revisit_when"]


def test_a_verdict_with_no_scope_is_a_global_claim_and_is_refused():
    with pytest.raises(SC.ScopeRefused, match="no scope"):
        SC.ScopedVerdict(SC.SUPPORTED_IN_SCOPE, "  ", "works")


def test_structural_closure_needs_a_ground_from_the_closed_list():
    """Otherwise STRUCTURALLY_CLOSED becomes the new DEAD within a week."""
    with pytest.raises(SC.ScopeRefused, match="needs a ground"):
        SC.ScopedVerdict(SC.STRUCTURALLY_CLOSED, "covariance", "no headroom",
                         revisit_when="never")
    # GRAPH-COVARIANCE-1's actual ground: a perfect-foresight oracle worth
    # <=15.4% against the trailing sample matrix, in the SAME objective.
    ok = SC.ScopedVerdict(
        SC.STRUCTURALLY_CLOSED, "semantic graph -> min-variance covariance",
        "oracle headroom <=15.4%", revisit_when="a different objective",
        closure_ground="oracle_no_headroom_same_objective")
    assert ok.closes_anything


def test_closure_ground_is_meaningless_on_a_non_closing_verdict():
    with pytest.raises(SC.ScopeRefused, match="only meaningful"):
        SC.ScopedVerdict(SC.NOT_DETECTABLE_IN_SCOPE, "x", "y",
                         revisit_when="z",
                         closure_ground="mathematical_impossibility")


# ── §18: the interaction tested as its own quantity ─────────────────────────

def test_significant_in_A_and_not_in_B_is_NOT_a_detectable_difference():
    """The §18 case, with numbers that make the trap concrete.

    A is +4.0 with SE 1.5 (t=2.7, "significant"). B is +1.0 with SE 1.5
    (t=0.67, "not significant"). The naive reading calls that conditionality.
    The difference is +3.0 with SE 2.12, MDE 5.94 — the instrument could not
    have seen it. Conditionality is not established.
    """
    it = SC.interaction("A-B", 4.0, 1.5, 30, 1.0, 1.5, 30)
    assert it.diff_pp == pytest.approx(3.0)
    assert it.se_diff_pp == pytest.approx((1.5 ** 2 + 1.5 ** 2) ** 0.5)
    assert it.mde_pp > abs(it.diff_pp)
    assert it.detectable is False
    assert "SS18" in it.as_dict()["note"]


def test_a_genuinely_large_separation_IS_detectable():
    it = SC.interaction("A-B", 12.0, 1.0, 60, 0.2, 1.0, 60)
    assert it.detectable is True


def test_an_interaction_with_a_missing_arm_reports_nothing_rather_than_zero():
    it = SC.interaction("A-B", None, None, None, 1.0, 0.5, 20)
    assert it.diff_pp is None and it.detectable is False


# ── the sign inversion, which is the point ──────────────────────────────────

def _cell(scope, mean, mde_driver_sd=1.0, n=40):
    """A cell whose MDE is controlled through its SD."""
    import math
    se = mde_driver_sd / math.sqrt(n)
    mde = (SC.PW.Z_ALPHA_TWO_SIDED_05 + SC.PW.Z_POWER_80) * se
    return SC.ScopedCell("slice_x", scope, n, 0, mean, se, mde, float(n))


def test_a_powered_NULL_in_a_declared_unaffected_region_is_CONFIRMING():
    """The mechanism's own placebo arm coming back empty."""
    v = _cell(SC.UNAFFECTED, 0.05).verdict()
    assert v.verdict == SC.SUPPORTED_IN_SCOPE
    assert "CONFIRMING" in v.reason


def test_firing_STRONGLY_in_a_declared_unaffected_region_is_DISCONFIRMING():
    """Whatever this is, it is broader than the declared mechanism."""
    v = _cell(SC.UNAFFECTED, 9.0).verdict()
    assert v.verdict == SC.REFUTED_IN_SCOPE
    assert "broader than the declared mechanism" in v.reason
    assert v.revisit_when


def test_an_affected_cell_that_clears_its_MDE_positively_is_supported():
    v = _cell(SC.AFFECTED, 9.0).verdict()
    assert v.verdict == SC.SUPPORTED_IN_SCOPE


def test_an_affected_cell_powered_in_the_WRONG_direction_is_the_real_kill():
    v = _cell(SC.AFFECTED, -9.0).verdict()
    assert v.verdict == SC.REFUTED_IN_SCOPE
    assert v.closes_anything


def test_an_affected_cell_below_its_own_MDE_is_NEVER_a_kill():
    """SS19, and the reason 195 existing kills are absence-of-evidence."""
    v = _cell(SC.AFFECTED, 0.10).verdict()
    assert v.verdict == SC.NOT_DETECTABLE_IN_SCOPE
    assert not v.closes_anything
    assert "not a kill" in v.reason


def test_a_cell_with_no_MDE_is_unpowered_not_negative():
    c = SC.ScopedCell("s", SC.AFFECTED, 3, 0, 1.0, None, None, 3.0)
    assert c.verdict().verdict == SC.UNPOWERED_IN_SCOPE


def test_a_cell_that_never_ran_is_UNTESTED_not_refuted():
    c = SC.ScopedCell("s", SC.AFFECTED, 0, 12, None, None, None, None)
    v = c.verdict()
    assert v.verdict == SC.UNTESTED
    assert "not a refutation" in v.reason


def test_an_out_of_scope_cell_earns_no_verdict_either_way():
    """Scoring it would be choosing a side after seeing the number."""
    v = _cell(SC.OUT_OF_SCOPE, 9.0).verdict()
    assert v.verdict == SC.CONDITIONAL_OPEN
    assert not v.closes_anything


def test_the_default_revisit_condition_is_computed_not_boilerplate():
    """An unpowered cell owes a SAMPLE SIZE, and the sample size is derivable."""
    v = _cell(SC.AFFECTED, 0.10).verdict()
    assert "n_effective on this slice reaches about" in v.revisit_when


def test_an_unknown_scope_label_is_refused():
    with pytest.raises(SC.ScopeRefused):
        SC.ScopedCell("s", "PROBABLY_AFFECTED", 5, 0, 1.0, 0.1, 0.2, 5.0)


# ── the autopsy side: an executable declaration ─────────────────────────────

class _FakeEp:
    def __init__(self, eid, state):
        self.episode_id, self.state = eid, state


class _R:
    def __init__(self, name, net):
        self.name, self.net_return_pct = name, net


class _S:
    def __init__(self, **nets):
        self.results = {k: _R(k, v) for k, v in nets.items()}


def _scoped_autopsy(**over):
    kw = dict(
        episode_id="ep_parent",
        contemporaneous_evidence=["vix 52"], post_outcome_evidence=["+15%"],
        failed_assumption="high vol means keep falling",
        proposed_mechanism="buy the capitulation, not the volatility",
        executable_precursor={"all": [{"feature": "vix", "op": ">=",
                                       "value": 35}]},
        expected_affected_states=["VIX >= 35"],
        expected_unaffected_states=["VIX < 20"],
        affected_precursor={"all": [{"feature": "vix", "op": ">=", "value": 35}]},
        unaffected_precursor={"all": [{"feature": "vix", "op": "<",
                                       "value": 20}]},
        falsifier="no edge in crisis slices",
        alternative_explanation="mechanical rebound",
        proposed_action="hold", default_action="sell_100")
    kw.update(over)
    return A.Autopsy(**kw)


def test_declaring_only_ONE_of_the_two_precursors_is_refused():
    """A region to score with no region to control it against is the flat
    slice count this replaced."""
    with pytest.raises(A.AutopsyRefused, match="must be declared together"):
        _scoped_autopsy(unaffected_precursor=None)


def test_the_scope_declarations_speak_the_TRANSFERABLE_vocabulary():
    with pytest.raises(A.VocabularyRefused):
        _scoped_autopsy(unaffected_precursor={
            "all": [{"feature": "sp500_1m_return_pct", "op": "<", "value": 0}]})


def test_scope_labels_come_from_the_declaration_not_the_result():
    au = _scoped_autopsy()
    assert au.scope_of({"vix": 50}) == SC.AFFECTED
    assert au.scope_of({"vix": 12}) == SC.UNAFFECTED
    assert au.scope_of({"vix": 27}) == SC.OUT_OF_SCOPE      # declared neither


def test_a_self_contradictory_declaration_is_counted_not_resolved():
    """Both halves firing is not a coin toss — it is an incoherent hypothesis."""
    au = _scoped_autopsy(
        affected_precursor={"all": [{"feature": "vix", "op": ">=", "value": 20}]},
        unaffected_precursor={"all": [{"feature": "vix", "op": ">=",
                                       "value": 30}]})
    assert au.declaration_conflicts_on({"vix": 40}) is True
    assert au.scope_of({"vix": 40}) == SC.OUT_OF_SCOPE


def test_an_unevaluable_state_RAISES_rather_than_labelling_out_of_scope():
    """The §37 lesson, applied to the new layer: an episode that cannot be
    evaluated is not an episode outside the mechanism's scope."""
    au = _scoped_autopsy()
    with pytest.raises(A.PrecursorRefused):
        au.scope_of({"drawdown_pct": -30.0})       # no `vix` at all


# ── adjudication end to end ─────────────────────────────────────────────────

def _rec(eid, vix, hold, sell):
    return (_FakeEp(eid, {"vix": vix}), _S(hold=hold, sell_100=sell))


#: Forward 63-day equity returns are dispersed, and the dispersion is what
#: sets every MDE in this file. The first version of these helpers used
#: `edge + (i % 3) * 0.1`, giving an SD of 0.08pp — under which a 0.10pp mean
#: is "detectable" and every placebo arm fires. That is a fixture artefact, but
#: it is the same artefact the real thing has to survive: an MDE is only as
#: honest as the variance it was computed from.
_EDGE_SD_PP = 8.0


def _slice_of(prefix, n, vix, mean_edge, seed):
    import numpy as np
    rng = np.random.default_rng(seed)
    draws = rng.normal(mean_edge, _EDGE_SD_PP, n)
    return [_rec(f"{prefix}{i}", vix, float(d), 0.0)
            for i, d in enumerate(draws)]


def _crisis(prefix, n, edge, seed=11):
    return _slice_of(prefix, n, 50, edge, seed)


def _calm(prefix, n, edge, seed=29):
    return _slice_of(f"{prefix}c", n, 12, edge, seed)


def test_a_mechanism_that_pays_off_EVERYWHERE_is_refuted_by_its_own_placebo():
    """Firing everywhere is what beta does.

    `hold` beats `sell_100` by ~9pp in the crisis slices AND by ~9pp in the calm
    slices the mechanism declared it should be silent in. On the old flat count
    this looked like a mechanism transferring beautifully. It is the ACTION.
    """
    au = _scoped_autopsy()
    slices = {f"s{j}": _crisis(f"a{j}_", 40, 9.0) + _calm(f"b{j}_", 40, 9.0)
              for j in range(3)}
    rep = A.adjudicate_scoped(au, slices)
    assert rep["verdict"] == SC.REFUTED_IN_SCOPE
    assert rep["exportable"] is False
    assert len(rep["placebo_fired_slices"]) == 3
    assert "the ACTION" in rep["verdict_detail"]["reason"]


def test_a_genuinely_conditional_mechanism_survives_where_the_flat_count_killed_it(
        tmp_path):
    """The regression the whole ruling is about.

    Real in crisis (+9pp), correctly silent in calm (~0pp). The declared-silent
    slices are the mechanism keeping its word — and the old flat count scored
    them as failures.
    """
    au = _scoped_autopsy()
    slices = {f"s{j}": _crisis(f"a{j}_", 60, 9.0, seed=100 + j)
                       + _calm(f"b{j}_", 60, 0.0, seed=200 + j)
              for j in range(3)}
    rep = A.adjudicate_scoped(au, slices)
    assert rep["verdict"] == SC.SUPPORTED_IN_SCOPE
    assert rep["supported_slices"] == ["s0", "s1", "s2"]
    assert rep["placebo_fired_slices"] == []
    assert rep["interaction"]["detectable"] is True
    assert rep["exportable"] is True


def test_support_short_of_k_slices_is_TRANSFER_PENDING_not_a_kill():
    au = _scoped_autopsy()
    slices = {"s0": _crisis("a0_", 60, 9.0, seed=1) + _calm("b0_", 60, 0.0,
                                                            seed=2),
              "s1": _crisis("a1_", 60, 0.05, seed=3) + _calm("b1_", 60, 0.0,
                                                             seed=4)}
    rep = A.adjudicate_scoped(au, slices)
    assert rep["verdict"] == SC.TRANSFER_PENDING
    assert rep["verdict_detail"]["revisit_when"]
    assert not rep["verdict_detail"]["closes"]


def test_a_precursor_that_never_fires_in_scope_is_UNTESTED_not_DEAD():
    au = _scoped_autopsy()
    slices = {"s0": _calm("b0_", 40, 1.0)}          # no crisis episodes at all
    rep = A.adjudicate_scoped(au, slices)
    assert rep["verdict"] == SC.UNTESTED
    assert "not run" in rep["verdict_detail"]["reason"] or \
           "was not run" in rep["verdict_detail"]["reason"]


def test_an_incoherent_declaration_blocks_the_verdict_entirely():
    au = _scoped_autopsy(
        affected_precursor={"all": [{"feature": "vix", "op": ">=", "value": 20}]},
        unaffected_precursor={"all": [{"feature": "vix", "op": ">=",
                                       "value": 30}]})
    rep = A.adjudicate_scoped(au, {"s0": _crisis("a_", 40, 9.0)})
    assert rep["verdict"] == SC.UNTESTED
    assert rep["n_declaration_conflicts"] > 0
    assert rep["exportable"] is False


def test_every_non_support_in_the_effect_surface_carries_a_revisit_condition():
    au = _scoped_autopsy()
    slices = {f"s{j}": _crisis(f"a{j}_", 40, 0.05) + _calm(f"b{j}_", 40, 0.0)
              for j in range(3)}
    rep = A.adjudicate_scoped(au, slices)
    for _slice, by_scope in rep["effect_surface"].items():
        for _sc, v in by_scope.items():
            if v["verdict"] != SC.SUPPORTED_IN_SCOPE:
                assert v["revisit_when"], v


def test_the_word_DEAD_is_gone_from_the_unscoped_path_too(tmp_path):
    """It was the wrong word for two different facts."""
    au = A.Autopsy(
        episode_id="ep_parent",
        contemporaneous_evidence=["x"], post_outcome_evidence=["y"],
        failed_assumption="a", proposed_mechanism="m",
        executable_precursor={"all": [{"feature": "vix", "op": ">=",
                                       "value": 90}]},
        expected_affected_states=["VIX>=90"], expected_unaffected_states=["calm"],
        falsifier="f", alternative_explanation="alt",
        proposed_action="hold", default_action="sell_100")
    rep = A.adjudicate(au, {"s0": _crisis("a_", 5, 1.0)},
                       ledger_path=tmp_path / "lineage.jsonl")
    assert "DEAD" not in rep["verdict"]
    assert rep["verdict"].startswith(SC.UNTESTED)


# ── the sample size the kills were manufactured out of (§37) ────────────────

class _DatedEp:
    """A probe episode carrying the timestamp the real ones carry."""
    def __init__(self, eid, state, decision_ts, security="QQQ"):
        self.episode_id, self.state = eid, state
        self.decision_ts, self.security = decision_ts, security


def test_six_correlated_tickers_in_one_month_are_not_six_observations():
    """The defect that produced five refutations, pinned.

    150 rows from SIX tickers (QQQ/IWM/XLF/XLE/XLK/EFA all move together)
    sampled MONTHLY over a ~3-month forward window is not 150 independent
    observations. It is about (distinct months / 3), further shrunk by burst
    clustering — and an understated MDE does not produce a neutral error, it
    manufactures detections, which in a placebo arm means it manufactures
    REFUTATIONS.
    """
    import numpy as np
    rng = np.random.default_rng(7)
    recs = []
    # 24 consecutive months x 6 tickers = 144 rows.
    for m in range(24):
        for t in ("QQQ", "IWM", "XLF", "XLE", "XLK", "EFA"):
            ts = f"2008-{m % 12 + 1:02d}-01" if m < 12 else \
                 f"2009-{m % 12 + 1:02d}-01"
            recs.append((_DatedEp(f"{t}{m}", {"vix": 50}, ts, t),
                         _S(hold=float(rng.normal(2.0, 8.0)), sell_100=0.0)))
    au = _scoped_autopsy()
    out = A.evaluate_slice_scoped(au, recs, "gfc")
    cell = out["cells"][SC.AFFECTED]
    assert cell.n == 144
    # 24 distinct months / 3-month window, then burst-clustered.
    assert cell.n_effective <= 8.0, cell.n_effective
    assert cell.n_effective < cell.n / 15


def test_the_standard_error_and_the_MDE_describe_the_SAME_sample():
    """They disagreed, and it was invisible while n_effective == n.

    `se_pp` was sd/sqrt(n) while `mde_pp` came from n_effective. A cell's
    t-statistic and its minimum detectable effect were then computed from two
    different beliefs about how much evidence it held.
    """
    import math
    import numpy as np
    rng = np.random.default_rng(3)
    # Months spread four apart so they are genuinely separate bursts — twelve
    # CONSECUTIVE months are one episode, and would carry no MDE at all, which
    # is itself the correct answer and the subject of the test above.
    recs = []
    for i in range(36):
        mm = i * 4
        recs.append((_DatedEp(f"e{i}", {"vix": 50},
                              f"{1990 + mm // 12}-{mm % 12 + 1:02d}-01"),
                     _S(hold=float(rng.normal(2.0, 8.0)), sell_100=0.0)))
    cell = A.evaluate_slice_scoped(_scoped_autopsy(), recs,
                                   "gfc")["cells"][SC.AFFECTED]
    implied = (SC.PW.Z_ALPHA_TWO_SIDED_05 + SC.PW.Z_POWER_80) * cell.se_pp
    assert cell.mde_pp == pytest.approx(implied, rel=1e-9)
    # and the SE is the effective one, not the raw-n one
    assert cell.se_pp > 1.0 / math.sqrt(cell.n)


def test_an_undated_probe_falls_back_rather_than_inventing_a_month():
    """`None` for unmeasured, never a fabricated position."""
    recs = [(_FakeEp(f"e{i}", {"vix": 50}), _S(hold=2.0 + i, sell_100=0.0))
            for i in range(10)]
    cell = A.evaluate_slice_scoped(_scoped_autopsy(), recs,
                                   "s")["cells"][SC.AFFECTED]
    assert cell.n == 10 and cell.n_effective == 10.0


# ── the scope-aware corpse check (§2.6) ─────────────────────────────────────

def _corpse(mid="OLD-1", op=">=", value=35, verdict=SC.REFUTED_IN_SCOPE,
            scope="US large-cap 1990-2010", proposed="hold",
            default="sell_100"):
    return SC.Corpse(mechanism_id=mid,
                     precursor={"all": [{"feature": "vix", "op": op,
                                         "value": value}]},
                     proposed_action=proposed, default_action=default,
                     verdict=verdict, scope=scope)


def _check(precursor=None, scope="US large-cap 1990-2010", corpses=(),
           prospective=True, proposed="hold", default="sell_100"):
    return SC.corpse_check(
        precursor=precursor or {"all": [{"feature": "vix", "op": ">=",
                                         "value": 35}]},
        proposed_action=proposed, default_action=default, scope=scope,
        corpses=list(corpses), prospectively_declared=prospective)


def test_the_exact_failed_rule_in_the_same_scope_is_blocked():
    assert _check(corpses=[_corpse()])["outcome"] == SC.BLOCKED


def test_a_cosmetic_threshold_change_pays_a_resurrection_tax():
    """`vix >= 30` after `vix >= 35` died is not a new idea."""
    r = _check(precursor={"all": [{"feature": "vix", "op": ">=", "value": 30}]},
               corpses=[_corpse()])
    assert r["outcome"] == SC.RESURRECTION_TAX
    assert r["parent_control_required"] is True


def test_the_same_threshold_shuffle_declared_AFTER_the_result_is_blocked():
    r = _check(precursor={"all": [{"feature": "vix", "op": ">=", "value": 30}]},
               corpses=[_corpse()], prospective=False)
    assert r["outcome"] == SC.BLOCKED


def test_a_mechanistically_distinct_descendant_runs_with_the_parent_as_control():
    r = _check(precursor={"all": [{"feature": "vol_ratio_20_60", "op": ">=",
                                   "value": 1.3},
                                  {"feature": "drawdown_pct", "op": "<=",
                                   "value": -10}]},
               corpses=[_corpse()])
    assert r["outcome"] == SC.ALLOWED_WITH_PARENT_CONTROL
    assert r["parent_control_required"] is True
    assert r["parent"] == "OLD-1"


def test_the_SAME_rule_in_a_DIFFERENT_scope_is_not_blocked():
    """REFUTED_IN_SCOPE closes one environment, not an idea."""
    r = _check(scope="Japan small-cap 2000-2020", corpses=[_corpse()])
    assert r["outcome"] == SC.ALLOWED_WITH_PARENT_CONTROL


def test_a_corpse_that_was_never_POWERED_blocks_nothing():
    """Where "195 kills are absence-of-evidence" stops being rhetoric."""
    weak = _corpse(verdict=SC.NOT_DETECTABLE_IN_SCOPE)
    assert weak.blocks_anything is False
    r = _check(corpses=[weak])
    assert r["outcome"] == SC.ALLOWED_WITH_PARENT_CONTROL
    assert r["corpses_that_block_nothing"][0]["id"] == "OLD-1"


@pytest.mark.parametrize("v", sorted(SC.VERDICTS))
def test_only_the_two_closing_verdicts_can_ever_block(v):
    r = _check(corpses=[_corpse(verdict=v)])
    blocks = r["outcome"] == SC.BLOCKED
    assert blocks == (v in SC.CLOSING_VERDICTS)


def test_rule_shape_strips_thresholds_but_keeps_the_mechanism():
    a = {"all": [{"feature": "vix", "op": ">=", "value": 35}]}
    b = {"all": [{"feature": "vix", "op": ">=", "value": 20}]}
    c = {"all": [{"feature": "drawdown_pct", "op": ">=", "value": 35}]}
    assert SC.rule_shape(a) == SC.rule_shape(b)
    assert SC.rule_shape(a) != SC.rule_shape(c)
    assert SC.rule_exact(a) != SC.rule_exact(b)


def test_the_scoped_run_records_BOTH_verdicts_so_the_migration_is_auditable(
        tmp_path):
    import json
    au = _scoped_autopsy()
    slices = {f"s{j}": _crisis(f"a{j}_", 60, 9.0, seed=100 + j)
                       + _calm(f"b{j}_", 60, 0.0, seed=200 + j)
              for j in range(3)}
    p = tmp_path / "lineage.jsonl"
    rep = A.adjudicate(au, slices, ledger_path=p)
    assert rep["scoped"] is not None
    row = json.loads(p.read_text(encoding="utf-8").strip().splitlines()[-1])
    fit = row["fitness"]
    assert fit["scoped_verdict"] == SC.SUPPORTED_IN_SCOPE
    assert fit["flat_verdict"]                       # the old answer, kept
    assert fit["scoped_interaction"]["detectable"] is True

    # THE HEADLINE REGRESSION, computed on the SAME data rather than recalled.
    # The flat count scores the declared-silent calm episodes as failed slices,
    # so a mechanism that kept its word everywhere is REFUSED for keeping it.
    assert rep["verdict"] == SC.SUPPORTED_IN_SCOPE
    assert "REFUSED" in rep["flat_verdict"]
