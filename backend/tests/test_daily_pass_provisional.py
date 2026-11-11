"""CH-05 R5 (ported from the runtime's scripts/daily_pass.py): a cost-model
refusal of the decision contract leaves a PROVISIONAL, order-free assessment
instead of a bare refusal, a malformed context is refused before any build, and
the frozen-constituent rows the bars refresh adds are counted. Fixed clocks only;
nothing real is built, priced or written."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from backend.services import decision_contract as DC
from scripts import daily_pass as DP

CLOCK = datetime(2026, 11, 11, 22, 45, tzinfo=timezone.utc)


def _ctx(**kw):
    return {"date": "2026-11-11", "date_obj": date(2026, 11, 11), **kw}


def _refuse(**kw):
    raise DC.CostModelRefused("no cost model for 2026-11-11: spread table absent")


def test_a_cost_refusal_is_a_provisional_no_new_bet_never_an_order(monkeypatch):
    monkeypatch.setattr(DP, "build_decision_contracts", _refuse)
    row = DP.step_decision_contract(_ctx(), observed_clock=lambda: CLOCK)
    assert row["status"] == "refused"
    a = row["provisional_decision"]
    assert a["action"] == "NO_NEW_BET" and a["orders_authorized"] is False
    assert a["operational_action"] == "NO_AUTOMATED_CHANGE"
    assert a["asof"] == CLOCK.isoformat() and a["decision_status"] == "PROVISIONAL"
    assert a["context_cutoff"]["instant"] is None                # a date label, not a PIT instant
    assert a["price_usd"] is None and a["estimated_probability"] is None
    assert a["mandate_status"] == "NOT_SUPPLIED"
    assert row["runtime_requirement_fulfilled"] is False
    assert "spread table absent" in row["answer"]


def test_an_invalid_clock_or_mandate_is_named_never_invented(monkeypatch):
    monkeypatch.setattr(DP, "build_decision_contracts", _refuse)
    row = DP.step_decision_contract(_ctx(mandate="not an object"),
                                    observed_clock=lambda: datetime(2026, 11, 11, 22, 45))  # naive
    a = row["provisional_decision"]
    assert a["asof"] is None and a["decision_status"] == "PROVISIONAL_UNTIMED"
    assert a["mandate_status"] == "INVALID" and a["mandate"] is None
    assert len(a["data_quality_warnings"]) == 2
    good = DP.step_decision_contract(_ctx(mandate={"max_gross": 1.0}), observed_clock=lambda: CLOCK)
    assert good["provisional_decision"]["mandate"] == {"max_gross": 1.0}
    assert good["provisional_decision"]["mandate_status"] == "SUPPLIED_UNVERIFIED"


@pytest.mark.parametrize("ctx", [
    {"date": "2026-11-11", "date_obj": date(2026, 11, 10)},          # two different cutoffs
    {"date": "2026-11-11"},                                            # no date_obj
    {"date": "11/11/2026", "date_obj": date(2026, 11, 11)},            # not ISO
])
def test_a_malformed_context_is_refused_before_any_build(monkeypatch, ctx):
    monkeypatch.setattr(DP, "build_decision_contracts", lambda **kw: pytest.fail("no build"))
    row = DP.step_decision_contract(ctx, observed_clock=lambda: CLOCK)
    assert row["status"] == "error" and row["decision_status"] == "UNAVAILABLE"
    assert any(r.startswith("INVALID_DECISION_CONTEXT") for r in row["refusals"])


def test_frozen_constituent_rows_count_as_bars_added(monkeypatch):
    import scripts.survivorship_cache_producer as SCP
    monkeypatch.setattr(SCP, "produce", lambda **kw: {"status": "ok"})
    monkeypatch.setattr(DP, "run_bars_refresh", lambda **kw: {
        "status": "ok", "rc": 0, "line": "BARS_FRESH: newest=2026-11-10 sessions_old=0",
        "panels": {"ranker_deep": {"status": "unchanged", "rows_added": 0}},
        "frozen_constituents": {"status": "ok", "n_new_rows": 5}})
    row = DP.step_bars_refresh({})
    assert row["status"] == "ok" and row["rows"] == 5
    assert row["frozen_constituents"] == {"status": "ok", "n_new_rows": 5}
