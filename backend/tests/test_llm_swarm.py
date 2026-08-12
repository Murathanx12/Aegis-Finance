"""LLM-SWARM-1: the refusals are the product, so the refusals are the tests.

Every test here is OFFLINE. The LLM call is injected, so nothing in this file
can reach the network, and the fast suite is network-blocked anyway. That is not
a convenience — the parse/reject/abstain surface is the part of the campaign
that decides whether thousands of calls bought information or tokens, and a
surface that can only be exercised by spending money is a surface nobody
exercises.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from backend.services import llm_swarm as sw
from backend.services.belief_state import HORIZONS, Observable
from backend.services.research_budget import ResearchBudgetExhausted

SNAP = {"ticker": "NVDA", "as_of": "2026-08-11", "last_close": 217.5,
        "sector": "Technology", "n_bars_available": 500}


def _reply(**over) -> str:
    """A reply that satisfies the whole contract, before a test breaks one part."""
    base = {
        "security": "NVDA", "abstain": False, "abstain_reason": "",
        "evidence": [{"what": "hyperscaler capex guidance",
                      "source": "10-Q", "first_public_timestamp": "2026-07-30"}],
        "market_implied_expectation": "continued acceleration",
        "optimus_expectation": "deceleration into next year",
        "expectation_discrepancy": "the market prices no decel; we price some",
        "causal_chain": ["capex digestion", "order lead times fall"],
        "scenarios": [
            {"label": "bull", "probability": 0.25, "price_target": 300.0,
             "rationale": "capex re-accelerates"},
            {"label": "base", "probability": 0.5, "price_target": 220.0,
             "rationale": "in line"},
            {"label": "bear", "probability": 0.25, "price_target": 150.0,
             "rationale": "digestion"}],
        "thesis_breakers": ["a cut to hyperscaler capex"],
        "next_observable": "the next capex guide",
        "confidence": 0.4,
        "counterargument": "supply remains the binding constraint",
        "forecasts": [
            {"observable": "abs_move_exceeds", "horizon_days": 5,
             "probability": 0.65, "threshold": 0.08, "thesis": "vol is high",
             "counter_thesis": "realised vol collapses",
             "next_observable": "weekly range"},
            {"observable": "beats_benchmark", "horizon_days": 20,
             "probability": 0.4, "threshold": None, "thesis": "crowded",
             "counter_thesis": "momentum persists",
             "next_observable": "relative strength"}],
    }
    base.update(over)
    return json.dumps(base)


def parse(text: str, specialist: str = "semis_technology") -> sw.ParsedCall:
    return sw.parse_reply(specialist, SNAP, text)


def reasons(p: sw.ParsedCall) -> list[str]:
    return [r["reason"] for r in p.rejections]


# ── the happy path, so the refusals below mean something ────────────────────

def test_a_complete_reply_yields_gradeable_forecasts_and_a_belief():
    p = parse(_reply())
    assert p.rejections == []
    assert len(p.forecasts) == 2
    assert p.belief is not None
    assert p.belief.expected_value() == pytest.approx(0.25 * 300 + 0.5 * 220
                                                      + 0.25 * 150)
    assert p.confidence == 0.4


def test_minting_goes_through_the_ledger_spine_not_around_it():
    p = parse(_reply())
    recs = sw.mint(p, snapshot=SNAP, prompt="p", model="deepseek-chat",
                   model_version="deepseek-chat")
    assert len(recs) == 2
    assert {r.specialist for r in recs} == {"semis_technology"}
    assert all(r.ticker == "NVDA" for r in recs)
    assert all(r.horizon_days in HORIZONS for r in recs)
    # The resolution date is the ledger's, not ours.
    assert all(r.resolves_after > r.made_at[:10] for r in recs)


# ── abstention is a first-class answer ──────────────────────────────────────

def test_an_abstention_is_counted_and_mints_nothing():
    p = parse(json.dumps({"abstain": True,
                          "abstain_reason": "no information distinguishes this "
                                            "name from its sector"}))
    assert p.abstained is True
    assert p.forecasts == []
    assert p.rejections == []
    assert sw.mint(p, snapshot=SNAP, prompt="p", model="m",
                   model_version="m") == []


def test_an_abstention_with_no_reason_is_refused():
    # Otherwise it is indistinguishable from a reply that fell over, and the two
    # say very different things about the specialist.
    p = parse(json.dumps({"abstain": True, "abstain_reason": "  "}))
    assert p.abstained is False
    assert reasons(p) == ["abstain_without_reason"]


# ── the three rules that cost us something to learn ─────────────────────────

def test_exact_one_half_is_refused_because_a_coin_flip_is_not_a_forecast():
    p = parse(_reply(forecasts=[
        {"observable": "return_sign", "horizon_days": 5, "probability": 0.5,
         "threshold": None, "thesis": "t", "counter_thesis": "c",
         "next_observable": "n"}]))
    assert reasons(p) == ["coin_flip_filler"]
    assert p.forecasts == []


def test_a_credence_just_off_one_half_is_a_forecast_and_is_kept():
    p = parse(_reply(forecasts=[
        {"observable": "return_sign", "horizon_days": 5, "probability": 0.52,
         "threshold": None, "thesis": "t", "counter_thesis": "c",
         "next_observable": "n"},
        {"observable": "drawdown_exceeds", "horizon_days": 20,
         "probability": 0.3, "threshold": 0.12, "thesis": "t",
         "counter_thesis": "c", "next_observable": "n"}]))
    assert p.rejections == []
    assert len(p.forecasts) == 2


def test_a_percent_threshold_is_surfaced_as_a_counted_rejection_not_swallowed():
    # The bug that once wrote six guaranteed-wrong records: |move| > 20.0 is a
    # 2000% move. make_prediction refuses it; the refusal must be COUNTED.
    p = parse(_reply(forecasts=[
        {"observable": "abs_move_exceeds", "horizon_days": 20,
         "probability": 0.7, "threshold": 20.0, "thesis": "t",
         "counter_thesis": "c", "next_observable": "n"},
        {"observable": "return_sign", "horizon_days": 60, "probability": 0.6,
         "threshold": None, "thesis": "t", "counter_thesis": "c",
         "next_observable": "n"}]))
    assert p.rejections == []          # the parser cannot know; the ledger does
    recs = sw.mint(p, snapshot=SNAP, prompt="p", model="m", model_version="m")
    assert len(recs) == 1
    assert reasons(p) == ["ledger_refused"]
    assert "decimal fraction" in p.rejections[0]["detail"]


def test_a_batch_that_is_one_observable_at_one_horizon_is_refused_whole():
    same = {"observable": "return_sign", "horizon_days": 5, "threshold": None,
            "thesis": "t", "counter_thesis": "c", "next_observable": "n"}
    p = parse(_reply(forecasts=[dict(same, probability=0.6),
                                dict(same, probability=0.62),
                                dict(same, probability=0.58)]))
    assert reasons(p) == ["monoculture_batch"]
    assert p.forecasts == []


def test_one_forecast_alone_is_not_a_monoculture():
    p = parse(_reply(forecasts=[
        {"observable": "return_sign", "horizon_days": 5, "probability": 0.6,
         "threshold": None, "thesis": "t", "counter_thesis": "c",
         "next_observable": "n"}]))
    assert p.rejections == []
    assert len(p.forecasts) == 1


# ── structural refusals ─────────────────────────────────────────────────────

def test_unparseable_output_is_the_most_interesting_row_in_the_ledger():
    p = parse("I think NVDA goes up. No JSON here.")
    assert reasons(p) == ["unparseable_json"]


def test_fenced_json_is_still_json():
    p = parse("```json\n" + _reply() + "\n```")
    assert p.rejections == []
    assert len(p.forecasts) == 2


@pytest.mark.parametrize("field", list(sw.REQUIRED_FIELDS))
def test_every_required_field_is_actually_required(field):
    body = json.loads(_reply())
    body.pop(field)
    p = parse(json.dumps(body))
    assert "missing_required_field" in reasons(p)
    assert field in p.rejections[0]["detail"]


def test_a_reply_about_a_different_security_is_refused():
    p = parse(_reply(security="AMD"))
    assert reasons(p) == ["wrong_security"]


def test_a_scenario_tree_that_does_not_sum_to_one_never_reaches_the_ledger():
    body = json.loads(_reply())
    body["scenarios"][0]["probability"] = 0.6
    p = parse(json.dumps(body))
    assert reasons(p) == ["scenario_probs_dont_sum"]
    assert p.forecasts == []


def test_scenarios_must_be_the_three_named_branches():
    body = json.loads(_reply())
    body["scenarios"] = body["scenarios"][:2]
    assert reasons(parse(json.dumps(body))) == ["scenarios_not_three"]
    body = json.loads(_reply())
    body["scenarios"][0]["label"] = "moon"
    assert reasons(parse(json.dumps(body))) == ["scenario_labels_wrong"]


def test_a_branch_with_no_price_target_cannot_be_priced_and_is_refused():
    body = json.loads(_reply())
    body["scenarios"][1]["price_target"] = None
    assert reasons(parse(json.dumps(body))) == ["scenario_missing_price_target"]


def test_evidence_must_carry_when_it_became_public():
    body = json.loads(_reply())
    body["evidence"] = [{"what": "a rumour", "source": "x"}]
    assert reasons(parse(json.dumps(body))) == [
        "evidence_without_first_public_timestamp"]
    body["evidence"] = []
    assert reasons(parse(json.dumps(body))) == ["no_evidence"]


def test_unknown_timestamps_are_allowed_because_inventing_one_is_worse():
    body = json.loads(_reply())
    body["evidence"] = [{"what": "a rumour", "source": "x",
                         "first_public_timestamp": "unknown"}]
    assert parse(json.dumps(body)).rejections == []


@pytest.mark.parametrize("bad", [1.4, -0.1, "high", None])
def test_confidence_must_be_a_credence(bad):
    p = parse(_reply(confidence=bad))
    assert reasons(p)[0].startswith("confidence_not_")


def test_recommendation_language_is_refused_rather_than_sanitised():
    p = parse(_reply(forecasts=[
        {"observable": "return_sign", "horizon_days": 20, "probability": 0.6,
         "threshold": None, "thesis": "we recommend this name",
         "counter_thesis": "c", "next_observable": "n"}]))
    assert reasons(p) == ["recommendation_language"]


def test_a_forecast_with_no_counter_thesis_is_not_falsifiable():
    p = parse(_reply(forecasts=[
        {"observable": "return_sign", "horizon_days": 20, "probability": 0.6,
         "threshold": None, "thesis": "t", "counter_thesis": "  ",
         "next_observable": "n"}]))
    assert reasons(p) == ["no_counter_thesis"]


def test_an_unfrozen_horizon_is_a_free_parameter_and_is_refused():
    p = parse(_reply(forecasts=[
        {"observable": "return_sign", "horizon_days": 33, "probability": 0.6,
         "threshold": None, "thesis": "t", "counter_thesis": "c",
         "next_observable": "n"}]))
    assert reasons(p) == ["horizon_not_frozen"]


def test_a_magnitude_observable_with_no_threshold_has_nothing_to_resolve():
    p = parse(_reply(forecasts=[
        {"observable": "abs_move_exceeds", "horizon_days": 20,
         "probability": 0.6, "threshold": None, "thesis": "t",
         "counter_thesis": "c", "next_observable": "n"}]))
    assert reasons(p) == ["threshold_missing"]


def test_forecasts_past_the_cap_are_counted_not_silently_dropped():
    f = [{"observable": o, "horizon_days": h, "probability": 0.6,
          "threshold": None, "thesis": "t", "counter_thesis": "c",
          "next_observable": "n"}
         for o, h in [("return_sign", 5), ("beats_benchmark", 20),
                      ("return_sign", 60), ("return_sign", 120),
                      ("beats_benchmark", 252)]]
    p = parse(_reply(forecasts=f))
    assert "forecasts_past_cap" in reasons(p)
    assert len(p.forecasts) == sw.SWARM_MAX_FORECASTS_PER_CALL


def test_a_non_abstaining_reply_with_no_forecasts_is_a_paragraph():
    assert reasons(parse(_reply(forecasts=[]))) == ["no_forecasts"]


# ── the vendor layer, still offline ─────────────────────────────────────────

def test_run_cell_records_a_wire_failure_as_failed_and_mints_nothing():
    def boom(system: str, user: str):
        raise RuntimeError("connection reset")

    res = sw.run_cell("skeptic", SNAP, llm_call=boom)
    assert res.status == "failed"
    assert res.records == []
    assert "connection reset" in (res.error or "")


def test_an_exhausted_budget_stops_the_campaign_it_is_not_a_flaky_cell():
    def broke(system: str, user: str):
        raise ResearchBudgetExhausted("call ceiling reached")

    with pytest.raises(ResearchBudgetExhausted):
        sw.run_cell("skeptic", SNAP, llm_call=broke)


def test_run_cell_end_to_end_with_an_injected_model():
    def fake(system: str, user: str):
        assert "NVDA" in user and "abstain" in system
        return sw.SwarmReply(text=_reply(), model_version="deepseek-chat-x",
                             tokens_in=1400, tokens_out=1100)

    res = sw.run_cell("semis_technology", SNAP, llm_call=fake)
    assert res.status == "ok"
    assert len(res.records) == 2
    assert all(r.model_version == "deepseek-chat-x" for r in res.records)
    row = res.as_row()
    assert row["n_records"] == 2 and row["tokens_in"] == 1400
    assert len(row["prediction_ids"]) == 2


def test_an_abstaining_cell_is_status_abstained_not_zero_yield():
    def fake(system: str, user: str):
        return sw.SwarmReply(text=json.dumps(
            {"abstain": True, "abstain_reason": "outside my competence"}),
            model_version="m")

    assert sw.run_cell("biotech_pharma", SNAP, llm_call=fake).status == "abstained"


def test_a_parsed_reply_that_mints_nothing_is_zero_yield():
    def fake(system: str, user: str):
        return sw.SwarmReply(text=_reply(forecasts=[]), model_version="m")

    res = sw.run_cell("skeptic", SNAP, llm_call=fake)
    assert res.status == "zero_yield"
    assert res.records == []


def test_retryable_errors_are_recognised_and_others_are_not():
    assert sw._is_retryable(RuntimeError("HTTP 429 rate limit"))
    assert sw._is_retryable(TimeoutError("read timed out"))
    assert not sw._is_retryable(ValueError("bad prompt"))


# ── the prompt contract ─────────────────────────────────────────────────────

def test_there_are_fourteen_roles_and_the_prompt_binds_them_all():
    assert len(sw.SPECIALISTS) == 14
    for name in sw.SPECIALISTS:
        system, user = sw.build_prompt(name, SNAP)
        assert "abstain" in system
        assert "0.50 IS REJECTED" in system
        assert str(list(HORIZONS)) in system
        assert "NVDA" in user


def test_an_unknown_specialist_is_a_key_error_not_a_default():
    with pytest.raises(KeyError):
        sw.build_prompt("astrology", SNAP)


def test_no_specialist_is_shown_another_specialists_answer():
    # The §20 property, asserted structurally: the only inputs to a prompt are
    # the role and the snapshot, so there is no channel through which one
    # specialist could see another's output.
    a, _ = sw.build_prompt("skeptic", SNAP)
    b, _ = sw.build_prompt("macro_rates", SNAP)
    assert a != b
    for other in sw.SPECIALISTS:
        if other not in ("skeptic",):
            assert other not in a.lower().replace(" ", "_")


# ── CANON §20 ───────────────────────────────────────────────────────────────

def test_identical_forecasts_collapse_to_one_effective_idea():
    preds = [{"ticker": "NVDA", "observable": "return_sign",
              "probability": 0.61, "horizon_days": 20} for _ in range(50)]
    e = sw.effective_distinct_ideas(preds)
    assert e["n_forecasts"] == 50
    assert e["effective_distinct_ideas"] == 1
    assert e["ratio"] == pytest.approx(0.02)


def test_genuinely_different_forecasts_do_not_collapse():
    preds = [{"ticker": t, "observable": o, "probability": p,
              "horizon_days": 20}
             for t in ("NVDA", "AMD") for o in ("return_sign", "beats_benchmark")
             for p in (0.2, 0.8)]
    e = sw.effective_distinct_ideas(preds)
    assert e["effective_distinct_ideas"] == 8
    assert e["ratio"] == 1.0


def test_the_empty_swarm_has_no_ratio_rather_than_a_ratio_of_zero():
    assert sw.effective_distinct_ideas([])["ratio"] is None


def test_it_matches_the_rule_optimus_specialists_already_uses():
    from backend.services import optimus_specialists as osp
    from backend.services.belief_state import make_prediction
    recs = [make_prediction(
        ticker="NVDA", specialist="s", observable=Observable.RETURN_SIGN,
        horizon_days=20, probability=p, thesis="t", counter_thesis="c",
        next_observable="n", model="m", model_version="m", prompt="p",
        input_snapshot={}) for p in (0.6, 0.61, 0.9)]
    assert (sw.effective_distinct_ideas(recs)["effective_distinct_ideas"]
            == osp.effective_distinct_ideas(recs)["effective_distinct_ideas"])


# ── the snapshot is point-in-time by construction ───────────────────────────

def _panel(n: int = 400) -> pd.DataFrame:
    idx = pd.bdate_range("2024-06-03", periods=n)
    return pd.DataFrame(
        {"NVDA": [100.0 + i * 0.1 for i in range(n)],
         "SPY": [400.0 + i * 0.05 for i in range(n)]}, index=idx)


def test_nothing_after_the_observation_timestamp_reaches_the_snapshot():
    panel = _panel()
    cut = str(panel.index[300].date())
    s = sw.snapshot_from_panel("NVDA", panel, as_of=cut)
    assert s is not None
    assert s["n_bars_available"] == 301
    assert s["last_close"] == pytest.approx(float(panel["NVDA"].iloc[300]))
    # Poison every bar after the cut. A PIT snapshot cannot notice.
    poisoned = panel.copy()
    poisoned.iloc[301:] = 1e9
    assert sw.snapshot_from_panel("NVDA", poisoned, as_of=cut) == s


def test_a_security_we_cannot_price_gets_no_snapshot_rather_than_a_zero_one():
    panel = _panel()
    assert sw.snapshot_from_panel("MISSING", panel, as_of="2025-01-02") is None
    short = panel.iloc[:10]
    assert sw.snapshot_from_panel("NVDA", short, as_of=str(short.index[-1].date())) is None


def test_absent_history_is_none_never_a_fabricated_zero_return():
    panel = _panel(n=60)
    s = sw.snapshot_from_panel("NVDA", panel, as_of=str(panel.index[-1].date()))
    assert s["trailing_return_pct"]["252d"] is None
    assert s["trailing_return_pct"]["21d"] is not None
