"""AUTOPSY-TO-RULE-1: a mechanism that only explains its parent must die here.

WHAT THESE TESTS ARE FOR
========================
The autopsy layer is where hindsight enters the system on purpose — Optimus is
shown the outcome, because that is what an autopsy is. Every test below exists
to pin one of the places that permission could leak into a claim:

  * a precursor that reads the outcome (fires on exactly what already happened);
  * a mechanism with no declared unaffected states (cannot be wrong anywhere);
  * a transfer test that includes the parent episode (proves itself);
  * a slice that "passed" without clearing its own MDE (SS19);
  * a mechanism that fires nowhere else and is quietly dropped instead of
    ledgered as dead (SS20 — the campaign's comparison count understates).
"""

from __future__ import annotations

import pytest

from backend.services.research_gym import autopsy as A
from backend.services.research_gym import episode as EP


# ── the precursor is executable, closed, and cannot read the outcome ─────────

def test_a_precursor_compiles_and_runs_against_state():
    fn = A.compile_precursor({"all": [
        {"feature": "vix", "op": ">=", "value": 35},
        {"feature": "drawdown_pct", "op": "<=", "value": -15.0}]})
    assert fn({"vix": 57.0, "drawdown_pct": -30.0}) is True
    assert fn({"vix": 57.0, "drawdown_pct": -2.0}) is False


def test_any_and_not_compose():
    fn = A.compile_precursor({"any": [
        {"feature": "vix", "op": ">=", "value": 35},
        {"not": {"feature": "regime", "op": "==", "value": "bull"}}]})
    assert fn({"vix": 12.0, "regime": "bear"}) is True
    assert fn({"vix": 12.0, "regime": "bull"}) is False


def test_a_precursor_that_reads_the_outcome_is_REFUSED():
    # It would fire on exactly the episodes that already happened and transfer
    # to nothing — while looking like a perfect rule on its parent.
    with pytest.raises(A.PrecursorRefused, match="OUTCOME field"):
        A.compile_precursor({"feature": "realised_return_pct", "op": ">",
                             "value": 0})


def test_an_unknown_operator_is_refused_rather_than_becoming_arbitrary_code():
    with pytest.raises(A.PrecursorRefused, match="closed"):
        A.compile_precursor({"feature": "vix", "op": "matches_regex",
                             "value": ".*"})


def test_a_missing_feature_RAISES_instead_of_evaluating_false():
    """The difference between 'did not fire' and 'could not be evaluated'.

    Evaluating a typo as False produces a mechanism that never fires, which
    reads on every report as "tested and did not transfer" when it was in fact
    never run.
    """
    fn = A.compile_precursor({"feature": "vixx", "op": ">", "value": 1})
    with pytest.raises(A.PrecursorRefused, match="untested mechanism"):
        fn({"vix": 40.0})


# ── the vocabulary: the defect the first real run produced ──────────────────

def test_a_precursor_outside_the_shared_vocabulary_is_refused():
    """THE DEFECT, 2026-08-15, first live run of this pipeline.

    The model wrote precursors over `sp500_1m_return_pct` — a real field, on
    every dataset-zero episode. The transfer probes carried `vix` and
    `drawdown_pct`. Every lookup raised, every raise was swallowed as "did not
    fire", and all three mechanisms were reported **DEAD — never fires outside
    its parent**. Confident, plausible, and false; they were never run.

    Counting unevaluable episodes is the symptom fix. This is the cause fix: a
    rule written in words the test corpus does not speak is untestable BY
    CONSTRUCTION, and the cheapest place to say so is where the rule is built.
    """
    with pytest.raises(A.VocabularyRefused, match="untestable BY CONSTRUCTION"):
        A.compile_precursor({"feature": "sp500_1m_return_pct", "op": "<=",
                             "value": -8},
                            vocabulary=A.TRANSFERABLE_FEATURES)


def test_the_vocabulary_check_reaches_nested_clauses():
    with pytest.raises(A.VocabularyRefused):
        A.compile_precursor(
            {"all": [{"feature": "vix", "op": ">=", "value": 35},
                     {"not": {"feature": "composite_score", "op": "<",
                              "value": 0}}]},
            vocabulary=A.TRANSFERABLE_FEATURES)


def test_an_autopsy_enforces_the_vocabulary_at_construction():
    with pytest.raises(A.VocabularyRefused):
        _autopsy(executable_precursor={"feature": "regime", "op": "==",
                                       "value": "bear"})


def test_an_unmeasured_feature_is_None_and_is_never_compared():
    """A cold rolling window is unmeasured, not zero.

    The first corpus filled a NaN 20-day realised volatility with 0.0, so
    every episode in the first month of the sample declared a volatility of
    exactly zero. A rule reading `realised_vol_20d < 5` would have fired on all
    of them for a reason having nothing to do with volatility — this repo bans
    `fillna(0)` on feature matrices and a state vector is a feature matrix with
    one row.
    """
    fn = A.compile_precursor({"feature": "realised_vol_20d", "op": "<",
                              "value": 5.0})
    assert fn({"realised_vol_20d": 3.0}) is True
    with pytest.raises(A.PrecursorRefused, match="was not measurable"):
        fn({"realised_vol_20d": None})


def test_unevaluable_episodes_are_counted_not_read_as_non_firing():
    au = _autopsy()
    # A slice whose episodes carry no `vix` at all — the shape of the failure.
    class _NoVix:
        episode_id, state = "x", {"drawdown_pct": -20.0}
    recs = [(_NoVix(), _S(hold=5.0, sell_100=0.0))]
    r = A.evaluate_slice(au, recs, "s")
    assert r.n_fired == 0
    assert r.n_unevaluable == 1
    assert r.was_actually_run is False
    assert "UNEVALUABLE" in r.reason
    assert "not a refutation" in r.reason


def test_a_mechanism_that_could_not_be_evaluated_is_UNTESTED_not_DEAD(tmp_path):
    au = _autopsy()

    class _NoVix:
        def __init__(self, eid):
            self.episode_id, self.state = eid, {"drawdown_pct": -20.0}

    slices = {"s1": [(_NoVix("a"), _S(hold=5.0, sell_100=0.0))],
              "s2": [(_NoVix("b"), _S(hold=5.0, sell_100=0.0))]}
    rep = A.adjudicate(au, slices, ledger_path=tmp_path / "l.jsonl")

    assert rep["verdict"].startswith("UNTESTED")
    assert "vocabulary failure, not a refutation" in rep["verdict"]
    assert rep["was_actually_run"] is False
    assert rep["n_unevaluable"] == 2
    # A hypothesis must not be retired on the strength of a schema mismatch.
    assert not rep["verdict"].startswith("DEAD")


# ── the autopsy schema refuses what cannot be tested ────────────────────────

def _autopsy(**over):
    kw = dict(
        episode_id="ep_parent",
        contemporaneous_evidence=["VIX printed 57", "price 30% off the high"],
        post_outcome_evidence=["the index rallied 15% over the next quarter"],
        failed_assumption="that extreme stress implies a negative expected "
                          "return over the next quarter",
        proposed_mechanism="forced liquidation exhausts sellers, so extreme "
                           "realised volatility marks the end of the fall "
                           "rather than the middle of it",
        executable_precursor={"all": [{"feature": "vix", "op": ">=",
                                       "value": 35}]},
        expected_affected_states=["vix>=35"],
        expected_unaffected_states=["vix<15", "vix15-20"],
        falsifier="if 63-day returns after VIX>=35 are indistinguishable from "
                  "those after VIX 20-25 across foreign slices, this is dead",
        alternative_explanation="the drawdown alone carries it and the "
                                "volatility reading adds nothing",
        proposed_action="hold",
        default_action="sell_100",
    )
    kw.update(over)
    return A.Autopsy(**kw)


def test_a_mechanism_with_no_unaffected_states_is_refused():
    with pytest.raises(A.AutopsyRefused, match="predicts every state"):
        _autopsy(expected_unaffected_states=[])


def test_a_state_declared_both_affected_and_unaffected_is_refused():
    with pytest.raises(A.AutopsyRefused, match="resolves either way"):
        _autopsy(expected_unaffected_states=["vix>=35", "vix<15"])


@pytest.mark.parametrize("field", ["failed_assumption", "proposed_mechanism",
                                   "falsifier", "alternative_explanation"])
def test_every_load_bearing_field_must_be_present(field):
    with pytest.raises(A.AutopsyRefused, match=field):
        _autopsy(**{field: "   "})


def test_an_autopsy_never_renders_as_a_claim():
    assert _autopsy().as_dict()["citable"] is False


def test_a_mechanism_whose_proposal_equals_its_control_is_refused():
    """Its edge is zero on every slice, by construction.

    Found by a test that used `hold` for both and reported a mean edge of
    exactly 0.00pp on three episodes. That would have run, produced a clean
    table of zeros, and been recorded as a mechanism that was tested and did
    not transfer — the most expensive kind of null, because it looks like a
    measurement.
    """
    with pytest.raises(A.AutopsyRefused, match="zero by construction"):
        _autopsy(proposed_action="hold", default_action="hold")


# ── the transfer test, with the parent barred mechanically ──────────────────

class _R:
    def __init__(self, name, net):
        self.name, self.net_return_pct = name, net


class _S:
    def __init__(self, **nets):
        self.results = {k: _R(k, v) for k, v in nets.items()}

    taken_policy = "sell_100"

    @property
    def taken(self):
        return self.results.get(self.taken_policy)

    def ranked(self):
        return sorted(self.results.values(), key=lambda r: -r.net_return_pct)


def _ep(eid, vix, resolved=True):
    e = EP.DecisionEpisode(
        decision_ts="2020-03-16", security="SPY", action="SELL",
        provenance=EP.GYM, exposure_before=1.0, exposure_after=0.0,
        stated_reason="stress", state={"vix": vix},
        beliefs=EP.Beliefs(p_up=0.3, horizon_days=63),
        outcome=EP.Outcome(resolved_at="2020-06-16", horizon_days=63,
                           realised_return_pct=15.0) if resolved else None)
    object.__setattr__(e, "_forced_id", eid)
    return e


class _FakeEp:
    """A minimal episode with a controllable id — `episode_id` is a content
    hash on the real type, and these tests are about identity, not hashing."""
    def __init__(self, eid, state):
        self.episode_id, self.state = eid, state


def _rec(eid, vix, hold, sell):
    return (_FakeEp(eid, {"vix": vix}), _S(hold=hold, sell_100=sell))


def test_the_parent_episode_is_excluded_from_its_own_proof(tmp_path):
    au = _autopsy()
    slices = {"s1": [_rec("ep_parent", 50, 20.0, 0.0),
                     _rec("ep_other", 50, 18.0, 0.0)]}
    tt, results = A.run_transfer(au, slices)
    assert "ep_parent" not in tt.tested_episode_ids
    assert tt.is_clean()
    assert results["s1"].n_fired == 1


def test_exclusion_is_not_left_to_the_caller(tmp_path):
    """The wall is wired, not documented.

    `run_transfer` removes the origin episodes itself. A caller who forgets is
    the failure mode this exists for, and a contaminated transfer test looks
    STRONGER, so nothing downstream would notice.
    """
    au = _autopsy()
    slices = {"s1": [_rec("ep_parent", 50, 99.0, 0.0)]}
    tt, results = A.run_transfer(au, slices)
    assert tt.tested_episode_ids == []
    assert results["s1"].n_fired == 0


def test_a_mechanism_whose_conditions_never_OCCUR_is_untested_and_ledgered(
        tmp_path):
    """Renamed from `..._is_DEAD_...` on 2026-08-16, and the rename is the point.

    This corpus contains no episode where the precursor's conditions hold. The
    mechanism was therefore never presented with a chance to be wrong. Calling
    that DEAD retires a hypothesis on the strength of what the corpus happens to
    contain — which is exactly how 195 existing kills became absence-of-evidence.

    What is still pinned, unchanged: it is not exportable, and the non-result is
    LEDGERED (SS20), because a search whose failures go unrecorded reports a
    multiple-comparison count that understates.
    """
    led = tmp_path / "lineage.jsonl"
    au = _autopsy()
    # Everywhere else, the precursor does not fire.
    slices = {"s1": [_rec("a", 12, 5.0, 0.0)],
              "s2": [_rec("b", 18, 5.0, 0.0)]}
    rep = A.adjudicate(au, slices, ledger_path=led)

    assert rep["verdict"].startswith("UNTESTED")
    assert "DEAD" not in rep["verdict"]
    assert "Revisit when" in rep["verdict"]
    assert rep["exportable"] is False
    assert rep["n_fired_outside_parent"] == 0
    # SS20: an unledgered death makes the campaign's comparison count
    # understate, and every deflation computed against it is too generous.
    rows = [r for r in led.read_text(encoding="utf-8").splitlines() if r.strip()]
    assert len(rows) == 1
    import json
    row = json.loads(rows[0])
    assert row["parent_id"] == "ep_parent"
    assert row["fitness"]["n_fired_outside_parent"] == 0
    assert row["citable"] is False


def test_a_slice_where_the_precursor_never_fires_is_UNTESTED_not_refuted():
    au = _autopsy()
    r = A.evaluate_slice(au, [_rec("a", 12, 5.0, 0.0)], "calm")
    assert r.passed is False
    assert "untested here" in r.reason
    assert "not the same as refuted" in r.reason


def test_a_positive_edge_below_its_own_MDE_does_not_pass(tmp_path):
    """SS19 inside the transfer test: undetectable is not a pass and not a kill."""
    au = _autopsy()
    # Three firing episodes with a small mean edge and large spread.
    recs = [_rec("a", 50, 1.0, 0.0), _rec("b", 50, -8.0, 0.0),
            _rec("c", 50, 9.0, 0.0)]
    r = A.evaluate_slice(au, recs, "s")
    assert r.n_fired == 3
    assert r.mean_edge_pp > 0
    assert r.passed is False
    assert "below its own MDE" in r.reason


def test_a_large_consistent_edge_does_pass():
    au = _autopsy()
    recs = [_rec(c, 50, 20.0 + i * 0.2, 0.0)
            for i, c in enumerate("abcdefghij")]
    r = A.evaluate_slice(au, recs, "s")
    assert r.passed is True
    assert r.mean_edge_pp == pytest.approx(20.9, abs=0.2)


def test_export_still_needs_prereg_and_forward_even_after_three_slices(tmp_path):
    au = _autopsy()
    slices = {f"s{i}": [_rec(f"{i}{c}", 50, 20.0 + j * 0.2, 0.0)
                        for j, c in enumerate("abcdefghij")]
              for i in range(3)}
    rep = A.adjudicate(au, slices, ledger_path=tmp_path / "l.jsonl")
    assert rep["exportable"] is False
    joined = " ".join(rep["missing"])
    assert "pre-registration" in joined
    assert "forward certification" in joined
    # The Gym cannot certify itself no matter how many slices it wins.


# ── the LLM proposer refuses what it cannot test ────────────────────────────

def test_a_truncated_reply_is_a_NAMED_drop_not_a_bad_answer():
    """The failure that voided IIF-1 Night 1, pinned in a second place."""
    from backend.services.research_gym import autopsy_llm as L

    def fake_ask(prompt, **kw):
        return {"text": "", "call": {}, "truncated": True,
                "finish_reason": "length"}

    out = L.propose(_FakeEpisodeForPrompt(), _S(hold=1.0, sell_100=0.0),
                    ask=fake_ask)
    assert out["autopsy"] is None
    assert "reply_truncated_at_token_ceiling" in out["drop_reason"]
    assert "thinking plus answer" in out["drop_reason"]


def test_an_untestable_reply_is_returned_as_a_result_not_raised():
    """"The model produced nothing testable" belongs in the yield denominator."""
    from backend.services.research_gym import autopsy_llm as L

    def fake_ask(prompt, **kw):
        return {"text": '{"proposed_mechanism": "stress is bullish"}',
                "call": {}, "truncated": False}

    out = L.propose(_FakeEpisodeForPrompt(), _S(hold=1.0, sell_100=0.0),
                    ask=fake_ask)
    assert out["autopsy"] is None
    assert out["drop_reason"].startswith("reply_not_testable")


def test_a_good_reply_becomes_a_testable_autopsy():
    from backend.services.research_gym import autopsy_llm as L
    import json

    body = {
        "contemporaneous_evidence": ["VIX 57"],
        "post_outcome_evidence": ["rallied"],
        "failed_assumption": "stress implies negative expected return",
        "proposed_mechanism": "seller exhaustion",
        "executable_precursor": {"feature": "vix", "op": ">=", "value": 35},
        "expected_affected_states": ["vix>=35"],
        "expected_unaffected_states": ["vix<15"],
        "falsifier": "no difference across foreign slices",
        "alternative_explanation": "drawdown alone",
        "proposed_action": "hold", "default_action": "sell_100",
    }

    def fake_ask(prompt, **kw):
        assert kw["max_tokens"] >= 8000, (
            "a large structured reply requested under a small ceiling is the "
            "exact shape of the Night 1 void")
        return {"text": "here you go\n" + json.dumps(body), "call": {},
                "truncated": False}

    out = L.propose(_FakeEpisodeForPrompt(), _S(hold=1.0, sell_100=0.0),
                    ask=fake_ask)
    assert out["drop_reason"] == ""
    assert out["autopsy"].fires_on({"vix": 40.0}) is True


def test_the_prompt_hands_over_all_three_denominators():
    """A model given only '+26pp of regret' explains a number that is half
    denominator, and writes a mechanism to fit it."""
    from backend.services.research_gym import autopsy_llm as L
    p = L.build_prompt(_FakeEpisodeForPrompt(), _S(hold=1.0, sell_100=0.0))
    assert "UPPER BOUND" in p
    assert "vs a fixed HOLD" in p
    assert "excess over the null" in p


class _FakeEpisodeForPrompt:
    episode_id = "ep_parent"
    decision_ts = "2020-03-16"
    security = "SPY"
    action = "SELL"
    exposure_before, exposure_after = 1.0, 0.0
    stated_reason = "extreme stress"
    state = {"vix": 57.0}
    regret = {"vs_ex_post_best_pp": 26.5, "vs_fixed_default_pp": 13.9,
              "excess_vs_matched_null_pp": 9.2}

    class beliefs:
        p_up, horizon_days = 0.3, 63

    class outcome:
        realised_return_pct, horizon_days = 15.0, 63
