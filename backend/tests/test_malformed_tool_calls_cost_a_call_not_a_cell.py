"""A malformed tool call must cost a LOOKUP, never a cell.

THE DEFECT THIS PINS (Night 1, 2026-08-17)
==========================================
    ERROR investigator_agent: [B_tools/ICE] investigation failed
      investigator_agent.py:444   args = dict(call.get("args") or {})
      ValueError: dictionary update sequence element #0 has length 3; 2 is required

A model-emitted tool call whose `args` was not a mapping, trusted straight into
`dict()`. It killed one cell of 200 — and because the pairing key is
`night × ticker × observable × horizon × threshold`, losing `B_tools/ICE` dropped
three paired cells from every OTHER arm too: 120 union, 117 paired.

So a 0.5% cell failure cost 2.5% of the primary contrast. Worse, the bug can only
strike tool-USING arms, which makes it a bias with a DIRECTION rather than noise:
it pushes `B_tools − A_snapshot` toward the null, which is the direction that
looks like a clean negative.

Two properties are pinned here:
  1. malformed replies are survived, per shape, and the cell still produces;
  2. they are COUNTED per arm, because a silent recovery would hide exactly the
     asymmetry that biases H1.
"""

from __future__ import annotations

import json

import pytest

from backend.services import investigator_agent as IA
from backend.services import investigator_tools as IT
from backend.services.investigator_agent import (FORECAST_CELLS, Investigator,
                                                 TOOL_CALL_DROP_REASONS)


class FakeReply:
    def __init__(self, text: str, model: str = "deepseek-v4-flash"):
        self.text = text
        self.model_version = model
        self.tokens_in = 10
        self.tokens_out = 20


def _forecast_payload():
    return {"forecasts": [
        {"observable": o, "horizon_days": h, "threshold": t,
         "prior": 0.18, "posterior": 0.42, "rationale": "r"}
        for o, h, t in FORECAST_CELLS]}


def make_llm(gather_reply: dict):
    """Same routing as test_investigator_agent's stub; only `gather` varies."""
    def call(*, system: str, user: str, **kw):
        if "investigator" in system.lower() and "tools" in system.lower():
            payload = gather_reply
        elif "Extract what changed" in system:
            payload = {"what_changed": "earnings", "when": "2026-08-20",
                       "who_is_affected": ["X"], "novelty": "medium",
                       "expectedness": "fully_expected", "unknowns": []}
        elif "prior_market_belief" in system:
            payload = {"prior_market_belief": "b",
                       "what_moved_in_expectations": "m",
                       "already_priced": "partly"}
        elif "MAGNITUDE" in system:
            payload = _forecast_payload()
        else:
            payload = {"strongest_objection": "o", "contradicting_evidence": "c",
                       "falsifying_check": "f", "confidence_in_chain": "low"}
        return FakeReply(json.dumps(payload))
    return call


def fake_tools(name, args, budget=None):
    if budget is not None:
        budget.take()
        r = IT.ToolResult(name, IT.STATUS_OK, payload={"headline": "PDUFA"})
        budget.log.append(r.as_row())
        return r
    return IT.ToolResult(name, IT.STATUS_OK, payload={"headline": "PDUFA"})


# ── (1) the exact Night 1 payload ───────────────────────────────────────────
def test_the_night_1_payload_no_longer_kills_the_cell():
    """`args` as a list of 3-element sequences — what ICE actually emitted.

    `dict([[1,2,3]])` is the ValueError from the receipt. The cell must survive.
    """
    bad = {"calls": [{"tool": "search_news", "args": [[1, 2, 3]]}],
           "done": True}
    inv = Investigator("B_tools", llm_call=make_llm(bad),
                       tool_runner=fake_tools).investigate("ICE", {"iv_rank": 80})

    assert inv.status != "failed", (
        f"the cell died on a malformed tool call: {inv.error!r}. One dead cell "
        f"costs three paired cells from every other arm.")
    assert len(inv.forecasts) == len(FORECAST_CELLS), (
        "the cell must still produce its forecasts — surviving the crash is "
        "only half the property")
    assert inv.tool_call_drops == {IA.TOOL_DROP_ARGS_NOT_A_MAPPING: 1}


@pytest.mark.parametrize("gather,expected", [
    ({"calls": [{"tool": "search_news", "args": [[1, 2, 3]]}], "done": True},
     IA.TOOL_DROP_ARGS_NOT_A_MAPPING),
    ({"calls": [{"tool": "search_news", "args": "ticker=ICE"}], "done": True},
     IA.TOOL_DROP_ARGS_NOT_A_MAPPING),
    ({"calls": ["search_news"], "done": True},
     IA.TOOL_DROP_CALL_NOT_A_MAPPING),
    ({"calls": [None], "done": True},
     IA.TOOL_DROP_CALL_NOT_A_MAPPING),
    ({"calls": "search_news", "done": True},
     IA.TOOL_DROP_CALLS_NOT_A_LIST),
])
def test_every_malformed_shape_is_survived_and_named(gather, expected):
    inv = Investigator("B_tools", llm_call=make_llm(gather),
                       tool_runner=fake_tools).investigate("ICE", {"k": 1})
    assert inv.status != "failed", inv.error
    assert inv.tool_call_drops.get(expected), (
        f"expected {expected!r}, got {inv.tool_call_drops!r}")


def test_a_string_calls_value_is_refused_not_iterated_as_characters():
    """`"search_news"` must not become six one-character tool calls.

    This is the shape that would NOT have raised — it would have produced
    plausible-looking nonsense, which is worse than the crash that was found.
    """
    called = []

    def spy(name, args, budget=None):
        called.append(name)
        return fake_tools(name, args, budget)

    inv = Investigator("B_tools", llm_call=make_llm({"calls": "search_news",
                                                     "done": True}),
                       tool_runner=spy).investigate("ICE", {"k": 1})
    assert called == [], f"iterated a string into tool calls: {called}"
    assert inv.tool_call_drops.get(IA.TOOL_DROP_CALLS_NOT_A_LIST)


def test_a_malformed_call_does_not_block_a_wellformed_one_beside_it():
    """One bad element must cost itself and nothing else."""
    mixed = {"calls": [{"tool": "search_news", "args": [[1, 2, 3]]},
                       {"tool": "search_filings", "args": {}}],
             "done": True}
    called = []

    def spy(name, args, budget=None):
        called.append(name)
        return fake_tools(name, args, budget)

    inv = Investigator("B_tools", llm_call=make_llm(mixed),
                       tool_runner=spy).investigate("ICE", {"k": 1})
    assert called == ["search_filings"]
    assert inv.tool_call_drops.get(IA.TOOL_DROP_ARGS_NOT_A_MAPPING) == 1


def test_malformed_args_are_never_coerced_into_a_mapping():
    """Deliberately NOT permissive.

    `[["ticker", "AAPL"]]` is coercible by `dict()`, and coercing it would be
    the wrong call: it invents an interpretation of a malformed reply, and a
    tool that runs with guessed arguments is worse than one that does not run.
    The anonymised arm makes this concrete — a guessed `ticker` would silently
    redirect a lookup to another company.
    """
    coercible = {"calls": [{"tool": "search_news",
                            "args": [["some_field", "some_value"]]}],
                 "done": True}
    called = []

    def spy(name, args, budget=None):
        called.append((name, dict(args)))
        return fake_tools(name, args, budget)

    inv = Investigator("B_tools", llm_call=make_llm(coercible),
                       tool_runner=spy).investigate("ICE", {"k": 1})
    assert called == [], "a coercible-but-malformed args was accepted"
    assert inv.tool_call_drops.get(IA.TOOL_DROP_ARGS_NOT_A_MAPPING) == 1


# ── (2) counted, and on the row even when zero ──────────────────────────────
def test_the_row_carries_the_count_even_when_it_is_zero():
    """A field that only appears when it is bad teaches readers absence is fine.

    And this count's whole value is being read on CLEAN nights: it is only ever
    recordable by tool-using arms, so a drift toward tool-arm-only failures has
    to be visible while it is still small.
    """
    good = {"calls": [{"tool": "search_news", "args": {}}], "done": True}
    row = Investigator("B_tools", llm_call=make_llm(good),
                       tool_runner=fake_tools).investigate("ICE", {}).as_row()
    assert row["n_tool_call_drops"] == 0
    assert row["tool_call_drops"] == {}
    assert "n_tool_call_drops" in row


def test_the_drop_vocabulary_is_closed_and_value_free():
    """Codes only. The receipt is read every morning during a 40-night blind, so
    a reason may never carry a model-stated number or name a cell."""
    for code in TOOL_CALL_DROP_REASONS:
        assert code.replace("_", "").isalpha(), (
            f"{code!r} carries a value; drop reasons describe SHAPE only")
    with pytest.raises(AssertionError):
        IA._drop_tool_call(IA.Investigation(arm="B_tools", ticker="ICE"),
                           "some_reason_not_in_the_vocabulary")


def test_a_snapshot_arm_can_never_record_a_tool_call_drop():
    """The asymmetry, stated as a test.

    This is WHY the count is per-arm: A_snapshot cannot reach the code that
    records it, so a nonzero value in a tool arm has no matched counterpart in
    the control, and the resulting cell losses are one-sided by construction.
    """
    bad = {"calls": [{"tool": "search_news", "args": [[1, 2, 3]]}], "done": True}
    inv = Investigator("A_snapshot", llm_call=make_llm(bad),
                       tool_runner=fake_tools).investigate("ICE", {"k": 1})
    assert inv.tool_call_drops == {}
    assert inv.as_row()["n_tool_call_drops"] == 0
