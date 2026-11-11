"""CH-05 R5 (ported from the runtime's scripts/daily_pass.py): a cost-model
refusal of the decision contract leaves a PROVISIONAL, order-free assessment
instead of a bare refusal, a malformed context is refused before any build, and
the frozen-constituent rows the bars refresh adds are counted. Fixed clocks only;
nothing real is built, priced or written."""
from __future__ import annotations

import re
import sys
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


# ── CH-05 (2026-11-11): the row comes from provisional_decision, and reaches no order path ──

def test_the_refusal_row_is_built_by_the_sibling_module_not_a_copy(monkeypatch):
    """One implementation: daily_pass calls `provisional_decision.cost_refusal_assessment`
    (R3's §4), so `decision_contract.py` stays byte-equal to the epoch pin and the
    assessment text cannot drift between two copies."""
    from backend.services import provisional_decision as PD
    assert not hasattr(DP, "_cost_refusal_assessment")
    seen = []
    real = PD.cost_refusal_assessment

    def spy(ctx, exc, **kw):
        seen.append(type(exc).__name__)
        return real(ctx, exc, **kw)
    monkeypatch.setattr(PD, "cost_refusal_assessment", spy)
    monkeypatch.setattr(DP, "build_decision_contracts", _refuse)
    row = DP.step_decision_contract(_ctx(), observed_clock=lambda: CLOCK)
    assert seen == ["CostModelRefused"]
    assert row["provisional_decision"] == real(_ctx(), DC.CostModelRefused(
        "no cost model for 2026-11-11: spread table absent"), observed_clock=lambda: CLOCK)


def test_no_order_path_is_reachable_from_the_provisional_row(monkeypatch):
    """Every Python function the refused step calls is recorded (sys.setprofile); none
    lives in a broker / fleet / sim module and none is named like an order call. The
    broker's submit functions are booby-trapped as a second net, and the conftest
    network guard is the third."""
    import os
    from backend.services import pc_broker as PB
    for name in ("submit", "submit_epoch_core_exit", "submit_epoch_stock"):
        monkeypatch.setattr(PB, name, lambda *a, **k: pytest.fail("an order call was reached"))
    monkeypatch.setattr(DP, "build_decision_contracts", _refuse)
    called: set[tuple[str, str]] = set()

    def prof(frame, event, arg):
        if event == "call":
            called.add((frame.f_code.co_filename, frame.f_code.co_name))
    sys.setprofile(prof)
    try:
        row = DP.step_decision_contract(_ctx(mandate={"max_gross": 1.0}), observed_clock=lambda: CLOCK)
    finally:
        sys.setprofile(None)
    assert row["provisional_decision"]["orders_authorized"] is False
    files = {os.path.basename(f) for f, _ in called}
    banned = {"pc_broker.py", "pc_epoch_broker.py", "pc_epoch_planner.py", "fleet_manager.py",
              "sim_session.py", "sim_run.py", "alpaca_mirror.py", "execution_ledger.py"}
    assert not files & banned, sorted(files & banned)
    assert not [n for _, n in called if re.search(r"submit|place_order|_order\b", n)]
    assert "provisional_decision.py" in files
