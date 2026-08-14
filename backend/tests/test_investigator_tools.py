"""INTERNET-INVESTIGATOR-FWD-1 tool layer — contract and disclosure tests.

Fast, offline, network-blocked. Every external call is mocked; if one of these
ever reaches the wire, `conftest.py`'s socket guard will fail it, which is the
intended behaviour.

THE TESTS THAT MATTER MOST ARE THE DISCLOSURE ONES
==================================================
This project's recurring, expensive failure is a fetch that dies quietly and
gets read as information — the GDELT 429 that was reported as "geopolitics
quiet", the insider collector that "ran" and fetched nothing, the crash overlay
that was structurally dark for weeks. In this trial that failure would be worse
than usual: a model told "no news found" when the news feed was down will
confidently forecast calm, and that forecast gets graded and attributed to the
architecture rather than to the outage.

So `empty` and `unavailable` must never merge, and the difference must survive
all the way into the text the model actually reads.
"""

from __future__ import annotations

import pytest

from backend.services import investigator_tools as T


# ── contract ────────────────────────────────────────────────────────────────

def test_every_tool_has_a_well_formed_schema():
    schemas = T.openai_tool_schemas(list(T.TOOLS))
    assert len(schemas) == len(T.TOOLS)
    for s in schemas:
        fn = s["function"]
        assert fn["name"] in T.TOOLS
        assert fn["description"].strip()
        assert fn["parameters"]["type"] == "object"
        assert "ticker" in fn["parameters"]["properties"]


def test_an_unknown_tool_name_raises_instead_of_being_skipped():
    # A typo in an arm's tool list must not silently produce a smaller toolset:
    # that would change which arm the arm IS, and the trial would grade it under
    # the wrong label.
    with pytest.raises(KeyError):
        T.openai_tool_schemas(["search_news", "query_the_future"])


def test_snapshot_arm_gets_no_tools_and_that_is_what_makes_it_the_control():
    assert T.tools_for_arm("A_snapshot") == []
    for arm in ("B_tools", "C_tools_only", "B_anon", "D_all"):
        assert len(T.tools_for_arm(arm)) >= 6


def test_unknown_arm_raises():
    with pytest.raises(KeyError):
        T.tools_for_arm("E_whatever")


# ── disclosure: the load-bearing distinction ────────────────────────────────

def test_a_failing_tool_reports_unavailable_not_empty(monkeypatch):
    def boom(ticker: str, **_):
        raise ConnectionError("429 Too Many Requests")
    monkeypatch.setitem(T.TOOLS, "search_news",
                        T.ToolSpec("search_news", "d", {"type": "object"}, boom))
    r = T.run_tool("search_news", {"ticker": "AAPL"})
    assert r.status == T.STATUS_UNAVAILABLE
    assert "429" in r.reason
    assert not r.ok


def test_a_genuinely_empty_result_reports_empty_not_unavailable(monkeypatch):
    monkeypatch.setitem(T.TOOLS, "search_news",
                        T.ToolSpec("search_news", "d", {"type": "object"},
                                   lambda ticker, **_: []))
    r = T.run_tool("search_news", {"ticker": "AAPL"})
    assert r.status == T.STATUS_EMPTY


def test_the_model_visible_text_distinguishes_failure_from_absence():
    """The regression that protects against fabricated calm.

    If these two strings ever become interchangeable, a throttled feed will be
    forecast as a quiet week and the error will be attributed to the model.
    """
    failed = T.ToolResult("search_news", T.STATUS_UNAVAILABLE,
                          reason="429 Too Many Requests").as_model_text()
    empty = T.ToolResult("search_news", T.STATUS_EMPTY).as_model_text()

    assert "LOOKUP FAILED" in failed
    assert "do not treat it as" in failed
    assert "found nothing" in empty
    assert "real negative result" in empty
    assert failed != empty
    # and the failure text must not contain language a model could read as
    # "there was nothing to find"
    assert "found nothing" not in failed


def test_a_successful_result_carries_its_payload_into_the_text():
    r = T.ToolResult("query_options", T.STATUS_OK,
                     payload={"iv_rank": 88, "skew": -0.4})
    txt = r.as_model_text()
    assert "iv_rank" in txt and "88" in txt


def test_model_text_survives_an_unserialisable_payload():
    class Weird:
        def __repr__(self) -> str:
            return "<weird>"
    r = T.ToolResult("query_prices", T.STATUS_OK, payload={"x": Weird()})
    assert "weird" in r.as_model_text()


# ── budget ──────────────────────────────────────────────────────────────────

def test_budget_refuses_rather_than_overspending(monkeypatch):
    monkeypatch.setitem(T.TOOLS, "query_prices",
                        T.ToolSpec("query_prices", "d", {"type": "object"},
                                   lambda ticker, **_: {"last": 1.0}))
    b = T.ToolBudget(max_calls=3)
    got = [T.run_tool("query_prices", {"ticker": "X"}, b) for _ in range(5)]
    assert [g.status for g in got[:3]] == [T.STATUS_OK] * 3
    assert all(g.status == T.STATUS_UNAVAILABLE for g in got[3:])
    assert "budget exhausted" in got[3].reason
    assert b.used == 3 and b.exhausted


def test_budget_logs_every_attempt_including_the_refusals(monkeypatch):
    monkeypatch.setitem(T.TOOLS, "query_prices",
                        T.ToolSpec("query_prices", "d", {"type": "object"},
                                   lambda ticker, **_: {"last": 1.0}))
    b = T.ToolBudget(max_calls=2)
    for _ in range(4):
        T.run_tool("query_prices", {"ticker": "X"}, b)
    # refusals never reach the implementation, so they are not "attempts" in the
    # vendor sense — but they must still be visible, or a night that hit the cap
    # looks identical to a night that had nothing to ask.
    assert len(b.log) == 4
    assert sum(1 for r in b.log if r["status"] == T.STATUS_UNAVAILABLE) == 2


def test_bad_arguments_are_not_labelled_a_vendor_failure(monkeypatch):
    monkeypatch.setitem(T.TOOLS, "query_prices",
                        T.ToolSpec("query_prices", "d", {"type": "object"},
                                   lambda ticker, **_: {"last": 1.0}))
    r = T.run_tool("query_prices", {"not_a_param": 1})
    assert r.status == T.STATUS_UNAVAILABLE
    assert "bad arguments" in r.reason


def test_an_unregistered_tool_call_is_refused_by_name():
    r = T.run_tool("query_the_future", {"ticker": "AAPL"})
    assert r.status == T.STATUS_UNAVAILABLE
    assert "no such tool" in r.reason


def test_latency_is_recorded_on_every_path(monkeypatch):
    monkeypatch.setitem(T.TOOLS, "query_prices",
                        T.ToolSpec("query_prices", "d", {"type": "object"},
                                   lambda ticker, **_: {"last": 1.0}))
    assert T.run_tool("query_prices", {"ticker": "X"}).latency_ms >= 0.0
    assert T.run_tool("nope", {}).latency_ms >= 0.0
