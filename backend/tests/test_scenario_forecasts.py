"""X3's contract: the schema, the grader, the control -- and that it is not wired.

Spec section 7 step 6's known answers first: one scenario matching at 0.7 with two
others at 0.15 must score exactly 0.135, and a set where NONE match must include
the residual-mass term rather than silently dropping it.

The vocabulary tuple is DERIVED from the spec's own table in one test rather
than eyeballed, so an edit to either cannot drift past the other.
"""

from __future__ import annotations

import re
from dataclasses import fields
from pathlib import Path

import pytest

from backend.services import belief_state
from backend.services import scenario_forecasts as sf

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / "docs" / "research_notes" / "2026-09-11" / "spec_events_and_calibration.md"


def _set(probs=(0.7, 0.15, 0.15),
         types=("earnings_report", "guidance_change", "litigation_filed")):
    scenarios = [{"headline": f"headline {i}", "probability": p, "event_type": t,
                  "direction": 1, "magnitude_bucket": "MODERATE"}
                 for i, (p, t) in enumerate(zip(probs, types))]
    return {"scenario_set_id": sf.set_id("AAA", "2026-09-11", scenarios),
            "symbol": "AAA", "as_of": "2026-09-11", "scenarios": scenarios}


def _realised(event_type, magnitude="MODERATE", confidence=0.9):
    return [{"event_type": event_type, "magnitude_bucket": magnitude,
             "confidence": confidence}]


# ------------------------------------------------------------ known answers

def test_the_specs_own_brier():
    """0.7 matches, 0.15 and 0.15 do not: (1-0.7)^2 + 0.15^2 + 0.15^2 = 0.135."""
    g = sf.grade_set(_set(), _realised("earnings_report"))
    assert g["matched_index"] == 0
    assert g["brier"] == pytest.approx(0.135)
    assert g["residual_term"] == pytest.approx(0.0), "mass is 1.0, so nothing is left over"
    assert g["brier_mean"] == pytest.approx(0.045)


def test_a_set_that_matched_nothing_keeps_its_residual_term():
    g = sf.grade_set(_set(), _realised("sanction"))
    assert g["matched"] is False
    assert g["residual_outcome"] == 1.0
    assert g["residual_term"] == pytest.approx(1.0)
    assert g["brier"] == pytest.approx(0.7 ** 2 + 0.15 ** 2 + 0.15 ** 2 + 1.0)
    assert "not a data gap" in g["note"]


def test_a_realised_no_event_day_is_a_miss_when_no_scenario_said_no_event():
    g = sf.grade_set(_set(), _realised("no_event", magnitude="NEGLIGIBLE"))
    assert g["matched"] is False and g["realised_event_type"] == "no_event"
    assert g["residual_term"] > 0


def test_a_scenario_that_declared_no_event_can_match_one():
    s = _set(types=("no_event", "guidance_change", "litigation_filed"))
    g = sf.grade_set(s, _realised("no_event", magnitude="NEGLIGIBLE"))
    assert g["matched_index"] == 0 and g["brier"] == pytest.approx(0.135)


def test_a_day_with_no_extraction_at_all_is_not_the_same_as_a_no_event_day():
    g = sf.grade_set(_set(), [])
    assert g["realised_day_had_no_extraction"] is True
    assert g["realised_event_type"] is None and g["matched"] is False


def test_the_residual_term_makes_the_score_proper_in_both_directions():
    """The residual mass is scored against an implicit "none of these" bucket,
    so hedging is not free and is not punished either -- it is priced. A set
    that keeps 0.94 of its mass out of the named scenarios does WELL when none
    of them happens and BADLY when one does, which is what a proper score has
    to do. Without the term, a set that claimed 0.06 of total mass and matched
    nothing would score 0.0012 and look brilliant."""
    timid_miss = sf.grade_set(_set(probs=(0.02, 0.02, 0.02)), _realised("sanction"))
    bold_miss = sf.grade_set(_set(probs=(0.7, 0.15, 0.15)), _realised("sanction"))
    assert timid_miss["brier"] < bold_miss["brier"], "hedging pays when nothing matches"

    timid_hit = sf.grade_set(_set(probs=(0.02, 0.02, 0.02)),
                             _realised("earnings_report"))
    bold_hit = sf.grade_set(_set(probs=(0.7, 0.15, 0.15)), _realised("earnings_report"))
    assert timid_hit["brier"] > bold_hit["brier"], "and costs when something does"

    # and the term is never silently dropped: it is a named line in the payload
    for g in (timid_miss, bold_miss, timid_hit, bold_hit):
        assert "residual_term" in g and "residual_mass" in g
    without_the_term = sum(t["term"] for t in timid_miss["terms"])
    assert without_the_term == pytest.approx(0.0012)
    assert timid_miss["brier"] > without_the_term


def test_ties_are_broken_by_the_highest_realised_magnitude():
    realised = [{"event_type": "guidance_change", "magnitude_bucket": "SMALL",
                 "confidence": 0.9},
                {"event_type": "earnings_report", "magnitude_bucket": "LARGE",
                 "confidence": 0.4}]
    assert sf.dominant_event(realised)["event_type"] == "earnings_report"


def test_equal_magnitudes_fall_back_to_confidence():
    realised = [{"event_type": "guidance_change", "magnitude_bucket": "LARGE",
                 "confidence": 0.4},
                {"event_type": "earnings_report", "magnitude_bucket": "LARGE",
                 "confidence": 0.9}]
    assert sf.dominant_event(realised)["event_type"] == "earnings_report"


# ------------------------------------------------------------ the vocabulary

def test_the_vocabulary_is_the_specs_own_table():
    """DERIVED from the spec's markdown, not eyeballed: an edit to either the
    table or the tuple that does not reach the other turns this red."""
    text = SPEC.read_text(encoding="utf-8")
    section = text[text.index("### 1.2 The frozen vocabulary"):
                   text.index("That is 38 substantive")]
    ids = [m.group(1) for m in
           (re.match(r"^\|\s*`([a-z0-9_]+)`\s*\|", line) for line in section.splitlines())
           if m]
    v2 = text[text.index("#### Analyst actions (v2)"):text.index("That is 42 substantive")]
    ids += [m.group(1) for m in
            (re.match(r"^\|\s*`([a-z0-9_]+)`\s*\|", line) for line in v2.splitlines())
            if m]
    # section 1.2b's rows go BEFORE the refusal class, which is where the module
    # puts them too
    assert tuple(ids[:-4] + ids[-3:] + ids[-4:-3]) == sf.EVENT_TYPES
    assert len(set(ids)) == len(ids), "a duplicate id in the frozen vocabulary"


def test_the_count_discrepancy_in_the_spec_is_recorded_not_silently_resolved():
    """The section heading says "39 event types + no_event"; its closing
    sentence says "38 substantive + no_event = 39". The v1 table has 39
    substantive rows, so the heading is right and the sentence is off by one.
    Recorded here so the next reader does not re-derive it. v2 (section 1.2b)
    adds the three analyst rows on top of that."""
    from backend.services import event_vocabulary as ev
    assert len(ev.VOCABULARY_V1) == 40
    assert len(sf.EVENT_TYPES) == 43
    assert sf.EVENT_TYPES[-1] == "no_event"
    assert len([t for t in sf.EVENT_TYPES if t != "no_event"]) == 42


# ---------------------------------------------------------------- the schema

def test_a_valid_set_passes():
    assert sf.validate_scenario_set(_set()) == []


@pytest.mark.parametrize("key", ["scenario_set_id", "symbol", "as_of", "scenarios"])
def test_a_missing_top_level_field_is_refused_naming_it(key):
    s = _set()
    del s[key]
    assert any(x.startswith(key) for x in sf.validate_scenario_set(s))


@pytest.mark.parametrize("key", ["headline", "probability", "event_type", "direction",
                                 "magnitude_bucket"])
def test_a_missing_scenario_field_is_refused_naming_it(key):
    s = _set()
    del s["scenarios"][1][key]
    assert any(f"scenarios[1].{key}" in x for x in sf.validate_scenario_set(s))


def test_an_unknown_event_type_is_refused():
    s = _set()
    s["scenarios"][0]["event_type"] = "the_stock_goes_up"
    assert any("event_type" in x for x in sf.validate_scenario_set(s))


def test_a_probability_outside_the_unit_interval_is_refused():
    s = _set()
    s["scenarios"][0]["probability"] = 1.4
    assert any("probability" in x for x in sf.validate_scenario_set(s))


def test_more_than_k_scenarios_is_refused():
    s = _set(probs=(0.3, 0.3, 0.3), types=("earnings_report", "guidance_change",
                                           "litigation_filed"))
    s["scenarios"].append(dict(s["scenarios"][0]))
    assert any("scenarios:" in x for x in sf.validate_scenario_set(s))


def test_an_extra_key_is_refused_because_additional_properties_is_false():
    s = _set()
    s["expected_return"] = 0.03
    assert any("expected_return" in x for x in sf.validate_scenario_set(s))
    s2 = _set()
    s2["scenarios"][0]["expected_return"] = 0.03
    assert any("expected_return" in x for x in sf.validate_scenario_set(s2))


def test_the_probability_mass_is_reported_and_not_constrained():
    """Three scenarios each at 0.9 is a calibration defect that must be VISIBLE,
    not a schema violation: the k scenarios are not exhaustive."""
    s = _set(probs=(0.9, 0.9, 0.9))
    assert sf.validate_scenario_set(s) == []
    assert sf.probability_mass(s) == pytest.approx(2.7)


def test_the_hand_written_validator_and_the_published_schema_agree():
    props = sf.SCENARIO_SET_SCHEMA["properties"]
    item = props["scenarios"]["items"]
    assert set(sf.SCENARIO_SET_SCHEMA["required"]) == {"scenario_set_id", "symbol",
                                                       "as_of", "scenarios"}
    assert item["properties"]["event_type"]["enum"] == list(sf.EVENT_TYPES)
    assert item["properties"]["magnitude_bucket"]["enum"] == list(sf.MAGNITUDES)
    assert props["scenarios"]["maxItems"] == sf.K_DEFAULT
    assert sf.SCENARIO_SET_SCHEMA["additionalProperties"] is False


def test_the_set_id_is_a_content_hash():
    a = _set()
    b = _set()
    assert a["scenario_set_id"] == b["scenario_set_id"]
    c = _set(probs=(0.6, 0.2, 0.2))
    assert c["scenario_set_id"] != a["scenario_set_id"]


# ---------------------------------------------------------------- the pricing

def test_a_missing_base_rate_raises_rather_than_pricing_at_zero():
    price = sf.pricer({("earnings_report", "2026H2"): {"mean": 0.012, "sd": 0.04, "n": 310}})
    assert price("earnings_report", "2026H2")["priced_return"] == pytest.approx(0.012)
    with pytest.raises(sf.BaseRateMissing) as exc:
        price("sanction", "2026H2")
    assert "not priced at zero" in str(exc.value)


def test_the_model_never_supplies_a_number():
    """X5: the LLM proposes the scenario, the engine prices it. The prompt
    forbids a return or a target, and the record's price comes only from the
    lookup."""
    assert "Do not state an expected return or a price target" in sf.PROMPT
    rows = sf.prediction_rows(
        _set(), price=sf.pricer({("earnings_report", "2026H2"):
                                 {"mean": 0.02, "sd": 0.03, "n": 100}}),
        era="2026H2", made_at="2026-09-11T21:00:00Z", model="qwen2.5-7b",
        prompt_hash="abc", input_snapshot_hash="def")
    assert rows[0]["inputs_used"]["priced_return"] == pytest.approx(0.02)
    assert rows[1]["inputs_used"]["priced_return"] is None
    assert "not priced at zero" in rows[1]["inputs_used"]["pricing_refusal"]
    assert "never a number" in rows[0]["inputs_used"]["priced_by"]


# -------------------------------------------------------- the record's shape

def test_every_field_the_rows_use_exists_on_PredictionRecord():
    """The shape cannot drift away from the ledger it is meant to enter."""
    known = {f.name for f in fields(belief_state.PredictionRecord)}
    rows = sf.prediction_rows(_set(), era="2026H2", made_at="2026-09-11T21:00:00Z",
                              model="qwen2.5-7b", prompt_hash="abc",
                              input_snapshot_hash="def")
    for row in rows:
        unknown = set(row) - known
        assert not unknown, f"{sorted(unknown)} are not PredictionRecord fields"


def test_one_row_per_scenario_sharing_the_set_id():
    rows = sf.prediction_rows(_set(), era="2026H2", made_at="2026-09-11T21:00:00Z",
                              model="qwen2.5-7b", prompt_hash="abc",
                              input_snapshot_hash="def")
    assert len(rows) == 3
    assert len({r["inputs_used"]["scenario_set_id"] for r in rows}) == 1
    assert len({r["prediction_id"] for r in rows}) == 3
    assert all(r["mechanism_id"] == sf.MECHANISM_ID for r in rows)
    assert all(r["licence"] == "PRODUCT_EXPERIMENT" for r in rows)
    assert all(r["costs_charged"] is False for r in rows)
    assert all(r["control_twin_id"].endswith("-baserate") for r in rows)


def test_the_control_twin_is_named_at_creation_not_after():
    """Invariant 18: a twin is created with the book, not once its number is
    known. Every row names its control and how the control is built."""
    rows = sf.prediction_rows(_set(), era="2026H2", made_at="x", model="m",
                              prompt_hash="a", input_snapshot_hash="b")
    assert all(r["control_construction"] and "never against zero" not in r["thesis"]
               for r in rows)
    assert "unconditional event-type frequencies" in rows[0]["control_construction"]


# ---------------------------------------------------------------- the control

def test_the_base_rate_control_needs_no_model_and_grades_identically():
    freqs = {"earnings_report": 0.22, "guidance_change": 0.11, "litigation_filed": 0.07,
             "sanction": 0.01, "not_a_real_type": 0.9}
    ctl = sf.base_rate_control("AAA", "2026-09-11", freqs, k=3)
    assert sf.validate_scenario_set(ctl) == []
    assert [s["event_type"] for s in ctl["scenarios"]] == [
        "earnings_report", "guidance_change", "litigation_filed"]
    assert ctl["scenarios"][0]["probability"] == pytest.approx(0.22)
    graded = sf.grade_set(ctl, _realised("earnings_report"))
    assert graded["matched_index"] == 0


def test_an_unknown_type_cannot_enter_the_control():
    ctl = sf.base_rate_control("AAA", "2026-09-11", {"not_a_real_type": 0.9}, k=3)
    assert ctl["scenarios"] == []


def test_the_comparison_is_against_the_control_never_against_zero():
    llm = sf.grade_set(_set(), _realised("earnings_report"))
    ctl = sf.grade_set(sf.base_rate_control(
        "AAA", "2026-09-11", {"sanction": 0.3, "spinoff": 0.2, "no_event": 0.1}),
        _realised("earnings_report"))
    out = sf.compare(llm, ctl)
    assert out["llm_better"] is True
    assert out["difference"] == pytest.approx(llm["brier"] - ctl["brier"])
    assert "never against 0" in out["never_against_zero"]


# ------------------------------------------------------- not wired, and said

def test_the_module_says_it_is_not_wired_and_why():
    d = sf.declaration()
    assert d["wired"] is False
    assert "L2" in d["why_not"] and "E1" in d["why_not"]
    assert sf.NOT_WIRED == d["why_not"]


def test_the_unwired_module_is_classified_in_signal_reachability():
    """A new module with no caller must be a red suite, not a discovery three
    weeks later. X3 has no caller ON PURPOSE, so it carries its reason."""
    from backend.services import signal_reachability as sr

    reason = sr.CLASSIFIED.get("backend.services.scenario_forecasts")
    assert reason and reason.startswith("AWAITS")
    assert "chunk 9" in reason


def test_the_prompt_is_fingerprinted_so_a_receipt_can_pin_it():
    fp = sf.prompt_fingerprint()
    assert fp["n_event_types"] == len(sf.EVENT_TYPES) and fp["k"] == 3
    assert len(fp["system_sha256"]) == 64 and len(fp["user_template_sha256"]) == 64
    rendered = sf.prompt_for("AAA", "2026-09-11", "nothing notable", k=3)
    assert "AAA" in rendered and "earnings_report" in rendered
    assert "need NOT sum to 1" in rendered
