"""INTERNET-INVESTIGATOR-FWD-1 agent — arm isolation, contract, and failure.

Offline and network-blocked: the LLM call and the tool runner are both injected,
so nothing here reaches a vendor.

THE TESTS THAT DECIDE WHETHER THE TRIAL MEANS ANYTHING
======================================================
The primary contrast is `B_tools − A_snapshot`, and it is only about
investigation if the arms differ in EXACTLY two things: whether tools may be
called, and whether the engine snapshot is shown. Any other leak between arms
turns the trial into a comparison of two things nobody specified, and the null
it reports would carry the right label and the wrong meaning.

So the arm-isolation tests here are not hygiene. They are the trial's internal
validity, written down.
"""

from __future__ import annotations

import json

import pytest

from backend.services import investigator_tools as IT
from backend.services.investigator_agent import (FORECAST_CELLS, Investigator,
                                                 mask_ticker)


class FakeReply:
    def __init__(self, text: str, model: str = "deepseek-v4-flash"):
        self.text = text
        self.model_version = model
        self.tokens_in = 10
        self.tokens_out = 20


def _forecast_payload(prior=0.18, posterior=0.42):
    return {"forecasts": [
        {"observable": o, "horizon_days": h, "threshold": t,
         "prior": prior, "posterior": posterior, "rationale": "r"}
        for o, h, t in FORECAST_CELLS]}


def make_llm(script: dict | None = None, *, serves="deepseek-v4-flash"):
    """An LLM stub that answers by which system prompt it was handed.

    `serves` is what the stub REPLIES it was, independent of what the caller
    requested — because that is exactly the vendor behaviour this project got
    burned by: `deepseek-chat` and `deepseek-reasoner` were both silently served
    as `v4-flash`, so an entire model-diversity arm compared a model to itself.
    """
    seen: list[dict] = []
    script = script or {}

    def call(*, system: str, user: str, **kw):
        seen.append({"system": system, "user": user,
                     "requested_model": kw.get("model")})
        if "investigator" in system.lower() and "tools" in system.lower():
            key = "gather"
        elif "Extract what changed" in system:
            key = "event"
        elif "prior_market_belief" in system:
            key = "expectations"
        elif "MAGNITUDE" in system:
            key = "forecast"
        else:
            key = "critic"
        default = {
            "gather": {"calls": [{"tool": "search_news", "args": {}}],
                       "done": True},
            "event": {"what_changed": "earnings Thursday", "when": "2026-08-20",
                      "who_is_affected": ["X"], "novelty": "medium",
                      "expectedness": "fully_expected", "unknowns": []},
            "expectations": {"prior_market_belief": "b",
                             "what_moved_in_expectations": "m",
                             "already_priced": "partly"},
            "forecast": _forecast_payload(),
            "critic": {"strongest_objection": "o", "contradicting_evidence": "c",
                       "falsifying_check": "f", "confidence_in_chain": "low"},
        }[key]
        return FakeReply(json.dumps(script.get(key, default)), serves)

    call.seen = seen                                            # type: ignore
    return call


def fake_tools(name, args, budget=None):
    if budget is not None:
        budget.take()
        r = IT.ToolResult(name, IT.STATUS_OK, payload={"headline": "PDUFA"})
        budget.log.append(r.as_row())
        return r
    return IT.ToolResult(name, IT.STATUS_OK, payload={"headline": "PDUFA"})


# ── arm isolation: the trial's internal validity ────────────────────────────

def test_snapshot_arm_never_calls_a_tool():
    calls = []

    def spy(name, args, budget=None):
        calls.append(name)
        return fake_tools(name, args, budget)

    inv = Investigator("A_snapshot", llm_call=make_llm(),
                       tool_runner=spy).investigate("AAPL", {"iv_rank": 80})
    assert calls == [], "the control arm reached for a tool"
    assert inv.tool_log == []
    assert "no investigation tools" in inv.dossier


def test_tools_only_arm_is_never_shown_the_snapshot():
    llm = make_llm()
    Investigator("C_tools_only", llm_call=llm,
                 tool_runner=fake_tools).investigate("AAPL",
                                                     {"secret": "SNAPSHOT_LEAK"})
    body = " ".join(s["user"] for s in llm.seen)
    assert "SNAPSHOT_LEAK" not in body
    assert "not shown the engine snapshot" in body


def test_tool_arms_are_shown_the_snapshot():
    llm = make_llm()
    Investigator("B_tools", llm_call=llm,
                 tool_runner=fake_tools).investigate("AAPL",
                                                     {"k": "SNAPSHOT_MARKER"})
    body = " ".join(s["user"] for s in llm.seen)
    assert "SNAPSHOT_MARKER" in body


def test_anon_arm_never_shows_the_ticker_to_the_model():
    """§19 receipt 3 is tested, not argued — so the masking has to work."""
    llm = make_llm()
    Investigator("B_anon", llm_call=llm,
                 tool_runner=fake_tools).investigate("NVDA", {"note": "NVDA hot"})
    body = " ".join(s["user"] for s in llm.seen)
    assert "NVDA" not in body
    assert "COMPANY_X" in body


def test_the_model_cannot_redirect_a_lookup_to_another_company():
    """Silent cross-contamination between paired cells, closed.

    If the model could choose the symbol, one cell's evidence could arrive from
    another company's news — and nothing in the output would show it. The
    symbol is forced, not defaulted. It is also what lets the anonymised arm
    look things up without being told what it is looking at.
    """
    asked = []

    def spy(name, args, budget=None):
        asked.append(args.get("ticker"))
        return fake_tools(name, args, budget)

    llm = make_llm({"gather": {"calls": [
        {"tool": "search_news", "args": {"ticker": "TSLA"}}], "done": True}})
    Investigator("B_tools", llm_call=llm,
                 tool_runner=spy).investigate("AAPL", {})
    assert asked == ["AAPL"], f"lookup was redirected to {asked}"


def test_anon_arm_still_gets_real_data_masked_rather_than_no_data():
    """H3 must be answered by the effect of ticker knowledge, not by starvation.

    The anonymised arm looks up the REAL security and sees the results with the
    symbol masked. An arm that simply could not fetch anything would make H3
    unfalsifiable while looking like a control.
    """
    asked = []

    def spy(name, args, budget=None):
        asked.append(args.get("ticker"))
        if budget is not None:
            budget.take()
            r = IT.ToolResult(name, IT.STATUS_OK,
                              payload={"headline": "NVDA beats"})
            budget.log.append(r.as_row())
            return r
        return IT.ToolResult(name, IT.STATUS_OK, payload={"headline": "x"})

    llm = make_llm()
    inv = Investigator("B_anon", llm_call=llm,
                       tool_runner=spy).investigate("NVDA", {})
    assert asked == ["NVDA"], "the anon arm was starved instead of masked"
    assert "COMPANY_X" in inv.dossier and "NVDA" not in inv.dossier


def test_non_anon_arm_does_show_the_ticker():
    llm = make_llm()
    Investigator("B_tools", llm_call=llm,
                 tool_runner=fake_tools).investigate("NVDA", {"note": "x"})
    assert "NVDA" in " ".join(s["user"] for s in llm.seen)


def test_unknown_arm_raises_rather_than_defaulting():
    with pytest.raises(KeyError):
        Investigator("B_toolz", llm_call=make_llm())


def test_mask_is_word_boundary_anchored_and_case_insensitive():
    assert mask_ticker("NVDA and nvda but not NVDAX", "NVDA") == \
        "COMPANY_X and COMPANY_X but not NVDAX"


# ── the belief-change contract survives the chain ───────────────────────────

def test_forecasts_carry_prior_posterior_and_a_computed_belief_change():
    inv = Investigator("B_tools", llm_call=make_llm(),
                       tool_runner=fake_tools).investigate("AAPL", {})
    assert inv.status == "ok"
    assert len(inv.forecasts) == len(FORECAST_CELLS)
    for f in inv.forecasts:
        assert f["belief_change"] == pytest.approx(f["posterior"] - f["prior"])


def test_zero_belief_change_is_kept_not_discarded():
    """"This evidence changed nothing" must survive to the ledger.

    If the pipeline quietly dropped unchanged forecasts, the retired `p != 0.50`
    incentive would come straight back in a new costume — only confident answers
    would ever be recorded.
    """
    llm = make_llm({"forecast": _forecast_payload(prior=0.30, posterior=0.30)})
    inv = Investigator("B_tools", llm_call=llm,
                       tool_runner=fake_tools).investigate("AAPL", {})
    assert len(inv.forecasts) == len(FORECAST_CELLS)
    assert all(f["belief_change"] == 0.0 for f in inv.forecasts)


# ── validation refuses rather than repairs ──────────────────────────────────

def test_a_percent_shaped_threshold_is_dropped_not_coerced():
    """The swarm's `threshold >= 1.0` incident produced six guaranteed-wrong
    records. Coercing would be guessing at what the forecaster meant."""
    bad = {"forecasts": [{"observable": "abs_move_exceeds", "horizon_days": 5,
                          "threshold": 5.0, "prior": 0.2, "posterior": 0.5,
                          "rationale": "r"}]}
    inv = Investigator("B_tools", llm_call=make_llm({"forecast": bad}),
                       tool_runner=fake_tools).investigate("AAPL", {})
    assert inv.forecasts == []
    assert inv.status == "no_forecast"


def test_out_of_range_and_unrequested_cells_are_dropped():
    bad = {"forecasts": [
        {"observable": "abs_move_exceeds", "horizon_days": 5, "threshold": 0.05,
         "prior": 1.7, "posterior": 0.5, "rationale": "r"},          # bad prior
        {"observable": "abs_move_exceeds", "horizon_days": 37, "threshold": 0.05,
         "prior": 0.2, "posterior": 0.5, "rationale": "r"},          # not asked
        {"observable": "abs_move_exceeds", "horizon_days": 1, "threshold": 0.03,
         "prior": 0.2, "posterior": 0.5, "rationale": "r"},          # good
    ]}
    inv = Investigator("B_tools", llm_call=make_llm({"forecast": bad}),
                       tool_runner=fake_tools).investigate("AAPL", {})
    assert len(inv.forecasts) == 1
    assert inv.forecasts[0]["horizon_days"] == 1


# ── failure is recorded, never silently absorbed ────────────────────────────

def test_an_unparseable_reply_is_a_failed_call_not_an_empty_answer():
    def llm(*, system, user, **kw):
        return FakeReply("I'm afraid I can't do that.")
    inv = Investigator("A_snapshot", llm_call=llm).investigate("AAPL", {})
    assert inv.status == "no_forecast"
    assert any(not c.ok and "unparseable" in c.error for c in inv.calls)


def test_a_budget_exception_PROPAGATES_and_is_never_a_cell_failure():
    """The most expensive bug this module could have, pinned.

    `_task` catches `Exception` so a flaky vendor marks one microtask failed and
    the chain continues. A spend ceiling must NOT behave that way: absorbed into
    a per-cell failure it keeps calling the vendor, once per remaining microtask
    per remaining ticker per remaining arm, logging a warning each time.

    `llm_swarm.default_llm_call` already wrote this rule down — "an exhausted
    budget must stop the campaign, not be absorbed into a per-cell failure count
    where it would look like flakiness" — and this module reimplemented the bug
    anyway until its own test found it.
    """
    calls = {"n": 0}

    def broke(*, system, user, **kw):
        calls["n"] += 1
        raise IT.BudgetExhausted("nightly ceiling reached")

    with pytest.raises(IT.BudgetExhausted):
        Investigator("A_snapshot", llm_call=broke).investigate("AAPL", {})
    assert calls["n"] == 1, (
        f"the ceiling was swallowed and the vendor was called {calls['n']} "
        f"times after it tripped")


def test_a_governor_refusal_also_propagates():
    from backend.services.research_budget import ResearchBudgetExhausted

    def refused(*, system, user, **kw):
        raise ResearchBudgetExhausted("campaign budget exhausted")

    with pytest.raises(ResearchBudgetExhausted):
        Investigator("A_snapshot", llm_call=refused).investigate("AAPL", {})


def test_a_vendor_exception_is_recorded_on_the_call_not_raised():
    def llm(*, system, user, **kw):
        raise ConnectionError("vendor down")
    inv = Investigator("A_snapshot", llm_call=llm).investigate("AAPL", {})
    assert inv.status == "no_forecast"
    assert all(not c.ok for c in inv.calls)
    assert "ConnectionError" in inv.calls[0].error


def test_served_model_is_recorded_from_the_reply_not_from_the_request():
    """The API silently aliases: `deepseek-chat` and `deepseek-reasoner` were
    BOTH served as `v4-flash`, so a model-diversity arm compared a model to
    itself. The stub therefore requests one model and serves another, and the
    record must show what was SERVED."""
    llm = make_llm(serves="deepseek-v4-pro")
    inv = Investigator("A_snapshot", llm_call=llm,
                       model="deepseek-v4-flash").investigate("AAPL", {})
    assert {s["requested_model"] for s in llm.seen} == {"deepseek-v4-flash"}
    assert inv.served_models == {"deepseek-v4-pro"}


def test_tool_rounds_are_bounded():
    llm = make_llm({"gather": {"calls": [{"tool": "search_news", "args": {}}],
                               "done": False}})          # never says done
    inv = Investigator("B_tools", llm_call=llm, tool_runner=fake_tools,
                       max_tool_rounds=2).investigate("AAPL", {})
    assert sum(1 for c in inv.calls if c.task == "gather_plan") == 2


def test_tool_budget_bounds_the_number_of_lookups():
    llm = make_llm({"gather": {"calls": [{"tool": "search_news", "args": {}}
                                         for _ in range(6)], "done": False}})
    inv = Investigator("B_tools", llm_call=llm, tool_runner=fake_tools,
                       max_tool_rounds=4, tool_budget=3).investigate("AAPL", {})
    assert sum(1 for r in inv.tool_log if r["status"] == IT.STATUS_OK) <= 3
