"""M2's known-answer tests: can a distilled rule be told from a random pairing?

The five the spec asks for -- planted-rule recovery, the shuffled noise floor,
`NOT_GENERALISED`, leaked-outcome rejection, M3 interop -- plus the guards that
make the whole thing safe to point at a live prompt: the over-trust cap and the
"a rule is a FORECAST, never an allocation" invariant.

Everything is synthetic and the model is a STUB. The local reader is not
started, not probed and not needed: the only thing it produces is rule TEXT,
and the arithmetic under test is what happens to that text afterwards.
"""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pytest

from learner import rule_distillation as RD

SEED = 20260912


# --------------------------------------------------------------- fixtures

def _row(i, *, mech="alphafam_a", era="bull", outcome=1, family=None, job=None):
    return {"prediction_id": f"p{i:05d}", "mechanism_id": mech,
            "family_id": family or mech, "era_tag": era,
            "specialist": "synthetic", "observable": "forward_excess_21d",
            "horizon_days": 21, "made_at": f"2026-0{1 + i % 9}-01",
            "resolves_after": f"2026-0{1 + i % 9}-22",
            "resolved_at": f"2026-0{1 + i % 9}-23",
            "outcome": int(outcome), "probability": 0.5,
            "vs_control": 0.01 if outcome else -0.01,
            "control_construction": "matched_twin",
            "job": job, "thesis": "t", "counter_thesis": "c",
            "next_observable": "n"}


def _planted(n=200, *, seed=SEED, p_hit=0.9, families=("alphafam_a",)):
    """`mechanism in families` AND `era_tag == bull` hits with p_hit; every
    other cell is a coin flip. The planted rule is therefore REAL and a rule
    that finds it should beat the pool base rate."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        # the OTHER mechanism is a different FAMILY (a different leading
        # token), which is what makes the held-out-family question askable
        mech = families[i % len(families)] if i % 2 == 0 else "zetafam_z"
        era = "bull" if i % 3 else "bear"
        hit = (mech in families and era == "bull")
        p = p_hit if hit else 0.5
        rows.append(_row(i, mech=mech, era=era,
                         outcome=int(rng.random() < p)))
    return rows


PLANTED_RULE = {
    "rule_text": "In alphafam_a during a bull era the forward excess is higher.",
    "applies_when": [{"field": "mechanism_id", "op": "eq", "value": "alphafam_a"},
                     {"field": "era_tag", "op": "eq", "value": "bull"}],
    "predicts": {"observable": "forward_excess_21d", "direction": "higher"},
    "evidence_pairs": ["alphafam_a::matched_twin::1"],
    "confidence": 0.9,
}


class _Reply:
    def __init__(self, text):
        self.text = text


def _stub(payload):
    """A model that always returns `payload`. The offline half of test 1: the
    slow test that runs the real 7B and checks the extracted condition is
    marked `slow` and is not in the fast suite."""
    def complete(backend, prompt, **kw):
        return _Reply(json.dumps(payload))
    return complete


# --------------------------------------------------- 1. planted-rule recovery

def test_a_planted_rule_is_recovered_and_beats_the_pool_base_rate():
    """The condition survives validation, fires on the planted cell only, and
    its Brier skill score against the pool base rate clears 0.3."""
    rows = _planted(400)
    cand, refusal = RD.validate_candidate(PLANTED_RULE)
    assert refusal is None, refusal
    scored = RD.score_rule(cand, rows)
    assert scored["n_fired"] > 40
    assert scored["beats_base_rate"] is True
    assert scored["bss"] > 0.3, scored
    # it fired ONLY where it said it would
    assert all(r["mechanism_id"] == "alphafam_a" and r["era_tag"] == "bull"
               for r in scored["fired_rows"])
    # and on held-out draws from the same generator it still does
    held = _planted(200, seed=SEED + 1)
    assert RD.score_rule(cand, held)["bss"] > 0.3


def test_a_rule_with_no_edge_does_not_beat_the_base_rate():
    """The other half of a discrimination test. A condition that selects a
    coin-flip subset must not clear the bar, or the bar is decoration."""
    rows = _planted(400)
    flat = {**PLANTED_RULE, "confidence": 0.9,
            "applies_when": [{"field": "mechanism_id", "op": "eq",
                              "value": "zetafam_z"}]}
    scored = RD.score_rule(flat, rows)
    assert scored["n_fired"] > 40
    assert scored["beats_base_rate"] is False, scored


def test_a_constant_forecast_can_only_TIE_its_own_subsets_climatology():
    """The arithmetic behind the gate's design, asserted rather than argued:
    this is WHY the pool base rate is the bar and the fired subset's own
    climatology is not."""
    rows = _planted(400)
    scored = RD.score_rule({**PLANTED_RULE, "confidence": 0.9}, rows)
    # best possible constant forecast equals the subset hit rate
    best = RD.score_rule({**PLANTED_RULE,
                          "confidence": scored["fired_subset_hit_rate"]}, rows)
    assert best["brier"] == pytest.approx(
        best["fired_subset_climatology_brier"], abs=1e-9)
    assert best["brier"] <= scored["brier"] + 1e-12


# --------------------------------------------------- 2. the shuffled floor

def test_shuffled_pairing_breaks_the_key_and_is_counted():
    """The noise floor's construction: a winner from one key against a loser
    from another, seeded from the month so nobody can pick the shuffle."""
    rows = (_planted(120, families=("alphafam_a",))
            + _planted(120, seed=99, families=("betafam_b",)))
    built = RD.make_pairs(rows, kinds=("book_vs_twin",), seed=SEED)
    assert built["pairs_sampled"] > 0
    assert built["pairs_sampled"] <= built["pairs_possible"]
    shuf = RD.shuffled_pairs(built, seed=SEED)
    assert len(shuf["pairs"]) == len(built["pairs"])
    assert all(p["pairing_key"].endswith("SHUFFLED") for p in shuf["pairs"])
    assert shuf["shuffle_seed"] == SEED + 1


def test_the_noise_floor_lands_on_climatology_within_sampling_noise():
    """A rule distilled from a random pairing is expected to score like the
    base rate. `indistinguishable`, not `worse than` -- the test the spec
    asks for."""
    rows = _planted(400)
    floor = RD.noise_floor([{**PLANTED_RULE, "confidence": 0.5,
                             "applies_when": [{"field": "mechanism_id",
                                               "op": "eq", "value": "zetafam_z"}]}],
                           rows)
    assert floor["status"] == "ok"
    assert floor["noise_floor_brier"] == pytest.approx(
        floor["climatology_brier"], abs=0.06), floor


# --------------------------------------------------------- 3. NOT_GENERALISED

def test_a_rule_real_in_ONE_family_files_NOT_GENERALISED_on_the_held_out_one():
    """Planted inside `synth_A` only. Once it has fired enough times on a
    family it was not distilled from, and those firings do not beat the base
    rate, the state is NOT_GENERALISED -- kept and scored, never deleted."""
    rows = _planted(400)
    # the rule's condition is widened to a family list so it FIRES out of
    # family; the planted edge exists only in synth_A
    rule = {**PLANTED_RULE,
            "applies_when": [{"field": "era_tag", "op": "eq", "value": "bull"}]}
    scored = RD.score_rule(rule, rows)
    gen = RD.generalisation_state(
        {**rule, "evidence_families": ["alphafam", "other"]},
        scored["fired_rows"])
    assert gen["n_heldout_firings"] >= RD.MIN_HELDOUT_FIRINGS
    assert gen["generalisation"] == "NOT_GENERALISED", gen
    assert gen["held_out_hit_rate"] is not None


def test_the_generalisation_gate_states_which_refusal_it_is():
    """`UNTESTED` and `INSUFFICIENT_HELDOUT_N` are different facts and both
    can go green later -- neither may be reported as NOT_GENERALISED."""
    one_family = RD.generalisation_state(
        {**PLANTED_RULE, "evidence_families": ["synth"]}, [])
    assert one_family["generalisation"] == "UNTESTED"
    thin = RD.generalisation_state(
        {**PLANTED_RULE, "evidence_families": ["a", "b"]},
        [_row(1, mech="c_other")] * 3)
    assert thin["generalisation"] == "INSUFFICIENT_HELDOUT_N"
    assert str(RD.MIN_HELDOUT_FIRINGS) in thin["why"]


# ------------------------------------------------- 4. the leaked-field guard

@pytest.mark.parametrize("field", ["outcome", "resolved_at", "brier",
                                   "vs_benchmark", "vs_control"])
def test_a_condition_on_an_OUTCOME_field_is_rejected_by_name(field):
    """The rule would memorise the answer key. Rejected with its own reason
    code, counted, and it never reaches `learned_rules.jsonl`."""
    bad = {**PLANTED_RULE,
           "applies_when": [{"field": field, "op": "eq", "value": 1}]}
    cand, refusal = RD.validate_candidate(bad)
    assert cand is None
    assert refusal.startswith("REJECTED_LEAKED_OUTCOME_FIELD")


def test_the_leak_is_counted_separately_from_a_schema_error(tmp_path):
    """Two different findings about the model. A schema that merely enumerated
    allowed fields would report a leak as a typo."""
    pairs = RD.make_pairs(_planted(80), kinds=("book_vs_twin",))["pairs"][:2]
    leaked = _stub({**PLANTED_RULE,
                    "applies_when": [{"field": "outcome", "op": "eq", "value": 1}]})
    out = RD.candidates_from_pairs(pairs, complete_fn=leaked)
    assert out["candidates"] == []
    assert out["refusals"]["REJECTED_LEAKED_OUTCOME_FIELD"] == len(pairs)
    assert out["refusals"]["SCHEMA_INVALID"] == 0

    junk = RD.candidates_from_pairs(pairs, complete_fn=_stub({"nope": 1}))
    assert junk["refusals"]["SCHEMA_INVALID"] == len(pairs)
    assert junk["refusals"]["REJECTED_LEAKED_OUTCOME_FIELD"] == 0


def test_the_model_never_sees_an_outcome_field_on_the_INPUT_side():
    """The allowlist, asserted on the actual prompt text rather than on the
    constant: a raw dict dump is how `vs_control` reaches the condition the
    model is asked to write."""
    pair = RD.make_pairs(_planted(80), kinds=("book_vs_twin",))["pairs"][0]
    prompt = RD.pair_prompt(pair)
    inputs = prompt.split("WINNER_OUTCOME")[0]
    for banned in ("vs_control", "\"outcome\"", "resolved_at", "probability"):
        assert banned not in inputs, banned
    assert "WINNER_OUTCOME: cleared its bar" in prompt


# ---------------------------------------------------------- 5. M3 interop

def test_ledger_retrieval_admits_scored_rules():
    """A rule has no `outcome` -- that is its normal condition, and the
    unmodified predicate would gate out every rule M2 ever writes."""
    from backend.services import ledger_retrieval as LR

    rule = {"rule_id": "RULE-2026-09-0001", "schema_version": RD.SCHEMA_VERSION,
            "state": "GENERALISED", "outcome": None,
            "resolution_date": "2026-09-30", "resolved_at": "2026-10-03"}
    ok, why = LR.visible_at(rule, date(2026, 10, 5))
    assert (ok, why) == (True, None)
    # a rule that has not been scored yet is refused, and says so by name
    ok2, why2 = LR.visible_at({**rule, "state": "CANDIDATE"}, date(2026, 10, 5))
    assert (ok2, why2) == (False, "rule_not_scored_yet")
    # and a FORECAST with no outcome is still `voided`, unchanged
    ok3, why3 = LR.visible_at(
        {"resolution_date": "2026-09-30", "resolved_at": "2026-10-03",
         "outcome": None}, date(2026, 10, 5))
    assert (ok3, why3) == (False, "voided")


def test_a_rule_scored_in_month_M_plus_1_is_invisible_inside_month_M():
    """The hindsight gate, on a rule row. `resolved_at` in October cannot be
    retrieved for a decision taken in September, whichever clause fires."""
    from backend.services import ledger_retrieval as LR

    rule = {"rule_id": "R", "schema_version": RD.SCHEMA_VERSION,
            "state": "GENERALISED", "outcome": None,
            "resolution_date": "2026-09-30", "resolved_at": "2026-10-03"}
    ok, why = LR.visible_at(rule, date(2026, 9, 20))
    assert ok is False and why == "unresolved_window"
    # the window HAS closed but the scoring had not run: `graded_after_t`
    ok2, why2 = LR.visible_at(rule, date(2026, 10, 1))
    assert ok2 is False and why2 == "graded_after_t"
    assert LR.rules_visible_at(date(2026, 9, 20), ledger=[rule]) == []
    assert len(LR.rules_visible_at(date(2026, 10, 5), ledger=[rule])) == 1


# ------------------------------------------------------ the over-trust cap

def test_the_prompt_weight_is_capped_by_MEASURED_skill_and_nothing_else():
    """arXiv:2505.16067's experience-following, closed: similarity and recency
    never enter, an unscored rule weighs zero, and a perfect skill score is
    still capped."""
    assert RD.prompt_weight(0.9, state="GENERALISED") == RD.MAX_RULE_WEIGHT
    assert RD.prompt_weight(0.19, state="GENERALISED") == pytest.approx(0.19)
    assert RD.prompt_weight(-2.0, state="GENERALISED") == 0.0
    assert RD.prompt_weight(None, state="GENERALISED") == 0.0
    for dead in ("CANDIDATE", "NOT_BETTER_THAN_NOISE", "STALE"):
        assert RD.prompt_weight(0.9, state=dead) == 0.0


def test_the_retrieval_report_surfaces_a_weight_for_every_rule():
    """An unscored rule may be SHOWN and must never move a number, so the
    column exists on every surfaced row rather than only on scored ones."""
    from backend.services import ledger_retrieval as LR

    rows = [{"schema_version": RD.SCHEMA_VERSION, "state": "GENERALISED",
             "outcome": None, "resolution_date": "2026-09-30",
             "resolved_at": "2026-10-01", "prompt_weight": 0.19},
            {"schema_version": RD.SCHEMA_VERSION, "state": "NOT_GENERALISED",
             "outcome": None, "resolution_date": "2026-09-30",
             "resolved_at": "2026-10-01"}]
    rep = LR.retrieval_report(date(2026, 10, 5), ledger=rows)
    assert rep["visible"] == 2
    assert [r["prompt_weight"] for r in rep["rules"]] == [0.19, 0.0]
    assert "similarity" in rep["prompt_weight_note"]


def test_a_rule_is_a_forecast_and_never_an_allocation():
    """The invariant that keeps a learned rule out of the order path: the row
    schema carries a probability, a Brier and a weight CAP, and no size, no
    ticker list and no rank."""
    cand, _ = RD.validate_candidate(PLANTED_RULE)
    row = RD.rule_row(cand, RD.score_rule(cand, _planted(200)),
                      RD.generalisation_state(cand, []),
                      month="2026-09", rule_id="RULE-2026-09-0001",
                      state="CANDIDATE", weight=0.0)
    for banned in ("weight_pct", "notional", "shares", "top_k", "rank",
                   "position", "order"):
        assert banned not in row, banned
    assert row["prompt_weight"] == 0.0
    assert row["outcome"] is None
    assert row["schema_version"] == RD.SCHEMA_VERSION


# ------------------------------------------------------------ the pairing

def test_a_degenerate_self_pair_is_dropped_and_counted():
    """A sloppy key puts the same row on both sides. Dropped, counted, and
    never distilled from."""
    # the same `prediction_id` written twice, once graded a winner and once a
    # loser -- which is what a duplicated append or a re-graded row looks like
    win = _row(1, outcome=1)
    lose = {**_row(1, outcome=0), "prediction_id": win["prediction_id"]}
    built = RD.make_pairs([win, lose], kinds=("book_vs_twin",))
    assert built["dropped_degenerate"] >= 1
    assert all(p["winner_id"] != p["loser_id"] for p in built["pairs"])


def test_the_pair_sample_is_capped_and_both_counts_are_reported():
    """40 winners and 3 losers is not 120 independent pairs."""
    rows = [_row(i, outcome=1) for i in range(40)] + [
        _row(100 + i, outcome=0) for i in range(3)]
    built = RD.make_pairs(rows, kinds=("book_vs_twin",), seed=1)
    assert built["pairs_possible"] == 120
    assert built["pairs_sampled"] == RD.MAX_PAIRS_PER_KEY
    # seeded: the same seed draws the same sample
    again = RD.make_pairs(rows, kinds=("book_vs_twin",), seed=1)
    assert [p["winner_id"] for p in built["pairs"]] == [
        p["winner_id"] for p in again["pairs"]]


def test_an_evidence_memory_row_pairs_on_its_verdict():
    """The three pair kinds read three vocabularies of 'winning' and the
    mapping is explicit, or a pair gets built out of two different meanings."""
    win = {"job": "G3", "run": 1, "cell": "c1", "family_id": "f",
           "verdict": "SUPPORTED", "utc": "2026-09-01T00:00:00"}
    lose = {"job": "G3", "run": 1, "cell": "c1", "family_id": "f",
            "verdict": "does not clear", "utc": "2026-09-01T00:00:00"}
    built = RD.make_pairs([win, lose], kinds=("arm_vs_control",))
    assert built["pairs_sampled"] == 1
    assert built["pairs"][0]["pair_kind"] == "arm_vs_control"


# --------------------------------------------------------------- the writers

def test_the_month_file_prints_the_losers_as_prominently_as_the_winners(tmp_path):
    """A file that printed only GENERALISED would be the gallery of survivors
    CLAUDE.md rule 4 forbids."""
    cand, _ = RD.validate_candidate(PLANTED_RULE)
    scored = RD.score_rule(cand, _planted(200))
    rows = [RD.rule_row(cand, scored, RD.generalisation_state(cand, []),
                        month="2026-09", rule_id=f"RULE-2026-09-{i:04d}",
                        state=state, weight=0.1)
            for i, state in enumerate(("GENERALISED", "NOT_GENERALISED",
                                       "NOT_BETTER_THAN_NOISE", "CANDIDATE",
                                       "STALE"), start=1)]
    p = RD.write_month("2026-09", rows, {"noise_floor": {"noise_floor_brier": 0.2},
                                         "shuffle_seed": 1, "pairs_sampled": 3,
                                         "pairs_possible": 9, "n_shuffled": 3,
                                         "dropped_degenerate": 0,
                                         "model": "stub", "contract_hash": "abc"},
                       dir_=tmp_path)
    text = p.read_text(encoding="utf-8")
    for state in ("GENERALISED", "NOT_GENERALISED", "NOT_BETTER_THAN_NOISE",
                  "CANDIDATE", "STALE"):
        assert f"## {state} (n=1)" in text
    assert "Noise floor" in text


def test_learned_rules_is_append_only(tmp_path):
    p = tmp_path / "learned_rules.jsonl"
    RD.append_rules([{"rule_id": "A", "state": "CANDIDATE"}], p)
    RD.append_rules([{"rule_id": "A", "state": "GENERALISED"}], p)
    lines = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]
    assert [r["state"] for r in lines] == ["CANDIDATE", "GENERALISED"]


# ---------------------------------------------------------------- the job

def test_the_job_runs_end_to_end_on_a_stub_and_scores_its_rules(tmp_path):
    payload = RD.M2_distill(month="2026-09", complete_fn=_stub(PLANTED_RULE),
                            out_dir=tmp_path,
                            rules_path=tmp_path / "learned_rules.jsonl")
    assert payload["model_state"] == "ok"
    assert payload["n_candidates"] >= 0
    assert "first_rule_with_its_own_brier" in payload
    assert (tmp_path / "LEARNED_2026-09.md").is_file()


def test_the_job_says_PENDING_MODEL_BY_NAME_when_the_reader_is_down(tmp_path,
                                                                    monkeypatch):
    """Everything that does not need the model still runs, the pair pool is
    frozen and hashed, and the first rule's Brier is CANNOT DETERMINE rather
    than a number."""
    monkeypatch.setattr(RD, "_probe", lambda backend: "ProviderRefusal: down")
    payload = RD.M2_distill(month="2026-09", out_dir=tmp_path)
    assert payload["model_state"] == "PENDING_MODEL"
    assert "down" in payload["model_refusal"]
    assert payload["first_rule_with_its_own_brier"].startswith("CANNOT DETERMINE")
    assert len(payload["pair_pool_sha256"]) == 16
    assert payload["pairs"]["pairs_sampled"] >= 0
    assert (tmp_path / "LEARNED_2026-09.md").is_file()
    assert "PENDING_MODEL" in (tmp_path / "LEARNED_2026-09.md").read_text(
        encoding="utf-8")
