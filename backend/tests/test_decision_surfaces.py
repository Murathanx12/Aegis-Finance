"""The two LLM surfaces and the board endpoint reach the Decision Contract.

THE FAILURE THIS SUITE PINS
===========================
Murat, 2026-09-19: *"When I was talking to the local model, what does the agent
think is a good buy? It did not say."* The audit found why: `"what's a good buy
today"` contains the word **today**, `_MORNING_WORDS` matched it first, and the
question was answered with a lane-vs-benchmark coin flip that is not a
per-ticker call and never could be. Meanwhile the copilot's ten tools could
narrate a stock's factor grades and could not retrieve the engine's own ranked
BUY list.

So three things are tested here, and the ORDER of the first is the whole point:

1. the decisions route wins over the morning words, for every phrasing;
2. retrieving a row RECORDS that it was seen — the thing neither repo tracked;
3. the board endpoint 404s when no contract exists, rather than returning an
   empty table that reads identically to "every candidate was refused".

`control_ask.ASK_SYSTEM` is pinned here too: the contract is a receipt, and the
authority clause does not move an inch because of it.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from backend.routers import control_ask as CA
from backend.services import ask_tools as AT
from backend.services import copilot as CP
from backend.services import decision_contract as DC
from backend.services import decision_ledger as DL


@pytest.fixture()
def contract(tmp_path, monkeypatch):
    """One BUY row on disk, and a ledger in tmp_path."""
    day = date(2026, 9, 19)
    rows = [{
        "decision_id": "d0001", "asof": str(day),
        "policy_id": "INVESTMENT_COMMITTEE_CORE_AND_TILTS",
        "policy_version": "2026-09-18T00:00:00+00:00",
        "licence": "PRODUCT_EXPERIMENT", "source": "investment_committee",
        "ticker": "AAA", "signal": "profitability_small", "direction": "BUY",
        "rank": 1, "expected_payoff": DC.NOT_CALIBRATED,
        "estimated_probability": None,
        "position_budget": {"weight": 0.03, "dollars": 1200.0, "shares": 40},
        "maximum_loss": {"worst_case_usd": -1200.0, "verdict": "whole notional"},
        "cost_model": {"name": "CANNOT DETERMINE", "priced": False},
        "falsifier": "gross profitability falls below the median",
        "expiry_utc": "2027-03-20T00:00:00+00:00",
        "artifact_sha256": "abc",
    }]
    DC.write_contracts(rows, asof=day, out_dir=tmp_path / "decisions",
                       notes=["capital $40,000 — the declared IPS capital"],
                       capital=40000.0, book={"degradation_reasons": []})
    monkeypatch.setattr(DC, "DECISIONS_DIR", tmp_path / "decisions")
    monkeypatch.setattr(DL, "LEDGER", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(DC, "latest",
                        lambda asof=None, out_dir=None: _read(tmp_path, day))
    return tmp_path


def _read(tmp_path, day):
    p = tmp_path / "decisions" / f"{day}.json"
    if not p.is_file():
        return None
    blob = json.loads(p.read_text(encoding="utf-8"))
    blob["path"] = str(p)
    return blob


@pytest.fixture()
def no_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(DC, "DECISIONS_DIR", tmp_path / "decisions")
    monkeypatch.setattr(DL, "LEDGER", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(DC, "latest", lambda asof=None, out_dir=None: None)
    return tmp_path


# ── the route ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("question", [
    "what should i buy",
    "what's a good buy today",
    "what would you buy today?",
    "what to buy this morning",
    "what would you short today",
    "decisions today",
])
def test_a_buy_question_routes_to_decisions_not_to_the_morning(question):
    r = AT.route(question)
    assert r["tool"] == "decisions", (
        f"{question!r} fell through to {r['tool']} — the morning words would "
        f"answer it with a lane-vs-benchmark coin flip")
    assert "Decision Contract" in r["why"]


def test_the_morning_route_still_owns_the_forecast_question():
    assert AT.route("what do you think happens today")["tool"] == "morning"
    assert AT.route("how did the fleet do")["tool"] == "fleet"


def test_decisions_is_a_declared_tool_with_a_handler():
    assert "decisions" in AT.TOOLS
    assert set(AT._DISPATCH) == set(AT.TOOLS)


# ── the desktop Ask ────────────────────────────────────────────────────────

def test_the_ask_tool_reads_the_contract_and_records_that_it_was_seen(contract):
    text, sources = AT.tool_decisions()
    assert "BUY AAA" in text
    assert "NOT CALIBRATED" in text
    assert "falsifier:" in text
    assert sources
    # DECIDED is BACKFILLED from the contract file: the file is the evidence
    # the decision was made, and refusing the delivery because the ledger's own
    # first row was missing would lose the one event this file exists for.
    assert DL.states_of("d0001") == [
        "DECIDED", "DELIVERED", "SEEN_BY_EXECUTOR"], (
        "retrieving a row IS the event this ledger exists to record")
    backfill = [r for r in DL.read() if r["state"] == "DECIDED"][0]
    assert backfill["by"] == "contract_file"


def test_the_ask_tool_says_the_absence_in_words(no_contract):
    text, sources = AT.tool_decisions()
    assert "has not said what it would buy" in text
    assert sources == []


def test_the_deterministic_answer_has_no_model_in_the_path(contract):
    answer, receipt, n = AT.decision_answer()
    assert n == 1
    assert receipt
    assert "BUY AAA" in answer
    assert "The engine sized these; nothing here placed an order." in answer


def test_the_ask_authority_clause_is_unchanged():
    """The contract is a RECEIPT. A pre-computed size the model reads out is
    not the model sizing anything, so this sentence must not soften."""
    assert ("You have no authority: you cannot run jobs, seal books, arm lanes, "
            "size positions or place orders, and you must never imply "
            "otherwise.") in CA.ASK_SYSTEM


# ── the copilot ────────────────────────────────────────────────────────────

def test_the_copilot_has_a_tool_that_returns_the_ranked_rows(contract):
    assert "get_todays_decisions" in CP.TOOLS
    out = CP.TOOLS["get_todays_decisions"]["impl"]({})
    assert out["contract_exists"] is True
    assert out["rows"][0]["ticker"] == "AAA"
    assert out["rows"][0]["falsifier"]
    assert out["rows"][0]["expiry_utc"]
    assert out["policy_id"] == "INVESTMENT_COMMITTEE_CORE_AND_TILTS"
    assert out["rows"][0]["expected_payoff"] == DC.NOT_CALIBRATED


def test_the_copilot_tool_records_seen_by_executor(contract):
    CP.TOOLS["get_todays_decisions"]["impl"]({})
    assert "SEEN_BY_EXECUTOR" in DL.states_of("d0001")


def test_the_copilot_tool_refuses_to_invent_a_contract(no_contract):
    out = CP.TOOLS["get_todays_decisions"]["impl"]({})
    assert out["contract_exists"] is False
    assert out["rows"] == []
    assert "has not said what it would buy" in out["answer"]


def test_the_system_prompt_licenses_reading_the_rows_and_names_the_policy():
    base = CP._SYSTEM_PROMPT_BASE
    assert "get_todays_decisions was called" in base
    assert "policy_id and policy_version" in base
    # and the disclaimer clause is still the only thing personal mode moves
    assert CP.SYSTEM_PROMPT == base + CP._DISCLAIMER_CLAUSE


def test_the_tool_schemas_still_build_with_the_new_tool():
    names = {t["function"]["name"] for t in CP._openai_tool_schema()}
    assert "get_todays_decisions" in names
    assert {t["name"] for t in CP._anthropic_tool_schema()} == set(CP.TOOLS)


# ── the board endpoint ─────────────────────────────────────────────────────

def test_the_endpoint_returns_the_contract_with_its_ledger(contract):
    from backend.routers.investment_committee import get_decisions
    blob = get_decisions(date="2026-09-19")
    assert blob["count_by_direction"]["BUY"] == 1
    assert blob["ledger"]["count_by_state"]["DECIDED"] == 0
    assert blob["rows"][0]["falsifier"]


def test_the_endpoint_404s_when_no_contract_exists(no_contract):
    from fastapi import HTTPException

    from backend.routers.investment_committee import get_decisions
    with pytest.raises(HTTPException) as exc:
        get_decisions(date="2026-09-19")
    assert exc.value.status_code == 404
    assert "reads one and never builds one" in exc.value.detail


def test_the_endpoint_builds_nothing(no_contract):
    """A read endpoint that could build a contract would let a page create a
    decision at a time nobody declared."""
    import inspect

    from backend.routers import investment_committee as R
    src = inspect.getsource(R.get_decisions)
    assert "build_daily_contracts" not in src
