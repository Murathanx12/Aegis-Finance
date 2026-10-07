"""C20 / D14: the PC-PAPER benchmark core behind `config.PC_BENCHMARK_CORE` (OFF).

Pins: the flag-OFF plan is byte-identical to a plan whose core seam is stubbed
out; the flag-ON plan adds ONE SPY target that `pc_broker.plan_orders` clips at
its unchanged MAX_NAME_FRAC; the reconciliation only goes OK with a full core
(which needs a second owner decision). Brokers are faked as in
test_u_plan_probe.py; dates derive from today.
"""

from __future__ import annotations

import json

import pytest

from backend import config
from backend.services import benchmark_core as BC
from backend.services import decision_contract as DC
from backend.services import pc_broker as PB
from backend.tests.test_u_plan_probe import (ASOF, EQUITY, PRICE, FakeBroker, _funnel,
                                             _ranking, _receipt, _run)
from scripts import sim_run as S


# ─────────────────────────────── pure ───────────────────────────────────────

def test_the_pc_broker_limits_are_unchanged():
    assert PB.MAX_NAME_FRAC == pytest.approx(0.12)
    assert PB.MAX_INVESTED_FRAC == pytest.approx(1.0)
    assert config.PC_BENCHMARK_CORE is False, "the core is the owner's flag; it ships OFF"
    assert config.PC_BENCHMARK_CORE_SYMBOL == config.DECISION_BENCHMARK_SYMBOL == "SPY"


def test_core_plan_off_is_inert():
    c = BC.core_plan({"A": 0.02}, enabled=False)
    assert c["enabled"] is False and c["applied"] is False
    assert "OFF" in c["line"]


def test_core_plan_on_wants_one_minus_active_and_is_clipped_by_the_broker_cap():
    c = BC.core_plan({f"N{i}": 0.02 for i in range(10)}, enabled=True)
    assert c["want_weight"] == pytest.approx(0.80)
    assert c["deliver_weight"] == pytest.approx(PB.MAX_NAME_FRAC)
    assert c["clipped"] is True and c["status"] == "CORE_CLIPPED_BY_MAX_NAME_FRAC"
    assert c["grading"]["basis"] == "excess_over_core" and c["grading"]["consistent"]
    full = BC.core_plan({"A": 0.95}, enabled=True)
    assert full["want_weight"] == pytest.approx(0.05) and full["clipped"] is False


def test_core_plan_refuses_when_the_core_symbol_is_a_sleeve_name():
    c = BC.core_plan({"SPY": 0.02}, enabled=True)
    assert c["applied"] is False and "already a sleeve" in c["line"]


def test_worst_case_arithmetic_core_and_sleeves():
    wc = BC.worst_case(equity=1_000_000, core_frac=0.80, core_sigma=0.007,
                       sleeve_weights={"A": 0.10, "B": 0.10}, sleeve_sigmas={"A": 0.03},
                       fallback_sigma=0.05, k=3.0, core_worst_day=-0.0586)
    assert wc["core_k_sigma_usd"] == pytest.approx(-0.80 * 3 * 0.007 * 1e6)
    assert wc["sleeves_k_sigma_usd"] == pytest.approx(-(0.10 * 3 * 0.03 + 0.10 * 3 * 0.05) * 1e6)
    assert wc["gross_over_equity"] == pytest.approx(1.0)
    assert wc["core_worst_day_usd"] == pytest.approx(-0.80 * 0.0586 * 1e6)
    assert wc["no_stop_ceiling_usd"] == pytest.approx(-1e6)
    assert "-$" in wc["line"] and "$-" not in wc["line"]


def test_grading_is_excess_over_the_core():
    assert BC.sleeve_excess({"A": 0.05, "B": -0.01}, 0.02) == pytest.approx({"A": 0.03, "B": -0.03})
    a = BC.account_attribution(0.03, 0.02, 0.80)
    assert a["core_part"] == pytest.approx(0.016)
    assert a["sleeves_part"] == pytest.approx(0.014)
    assert a["excess_over_full_core"] == pytest.approx(0.01)


def test_what_the_core_does_and_does_not_reconcile():
    """Pinned on the shape of the 2026-10-07 contract (benchmark 99.75%, cash 0,
    PROBE resolved at 0% BY CONSTRUCTION) against a broker with PROBE 20% held.

    * flag alone (12% SPY): POSITIONS_DISAGREE;
    * a FULL 80% core: STILL POSITIONS_DISAGREE -- the gap is the 20% PROBE
      sleeve the contract resolves to 0%, not the core;
    * only a resolution that counts the acting sleeve (core 80%, active 20%)
      reconciles with an 80% SPY core.
    So D14 alone cannot turn the line OK; the contract must also count the
    plan's acting PROBE gross (a decision_contract change, not made here)."""
    eq = 1_000_000.0
    names = [{"symbol": f"N{i}", "market_value": 0.02 * eq} for i in range(10)]

    def _rec(core_frac: float, resolution: dict) -> dict:
        pos = names + [{"symbol": "SPY", "market_value": core_frac * eq}]
        held = 0.20 + core_frac
        return DC.positions_reconciliation(
            [], capital=eq, resolution=resolution,
            equity={"equity_usd": eq, "cash_usd": (1 - held) * eq, "positions": pos, "as_of": "t"})
    today = {"benchmark_pct": 0.9975, "cash_pct": 0.0}
    for core in (0.0, PB.MAX_NAME_FRAC, 0.80):
        r = _rec(core, today)
        assert r["status"] == DC.MANDATE_UNRECONCILED, core
        assert any(d.startswith("POSITIONS_DISAGREE") for d in r["disagreements"])
    counted = {"benchmark_pct": 0.80, "cash_pct": 0.0}
    assert _rec(0.80, counted)["status"] == "OK"
    assert _rec(PB.MAX_NAME_FRAC, counted)["status"] == "OK", (
        "the check treats an unheld core as cash, so a clipped core held as cash also passes")


# ─────────────────────────────── u_plan ─────────────────────────────────────

_STABLE = ("verdict", "acting", "exploit_acting", "probe_acting", "n_targets", "n_orders",
           "orders_by_state", "sendable_by_state", "n_to_send", "send_block", "turnover_usd",
           "book", "refusals", "probe_weights", "worst_case", "risk_gate_line")


def _stable(rec: dict) -> dict:
    return {k: rec.get(k) for k in _STABLE}


def test_flag_off_plan_is_byte_identical_to_a_plan_without_the_core_seam(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PC_BENCHMARK_CORE", False)
    a, b = tmp_path / "a", tmp_path / "b"
    for d in (a, b):
        d.mkdir()
        _funnel(d, n=25)
        _ranking(d / "out", net=-0.2)
    fa = FakeBroker().install(monkeypatch)
    _run(a)
    rec_a = _receipt(a)
    calls = []

    def _no_seam(targets, **kw):
        calls.append(1)
        return {"enabled": False, "applied": False, "symbol": "SPY", "line": "stub"}
    monkeypatch.setattr(S, "_plan_benchmark_core", _no_seam)
    fb = FakeBroker().install(monkeypatch)
    _run(b)
    rec_b = _receipt(b)
    assert calls, "the stub must have been the seam u_plan called"
    assert json.dumps(_stable(rec_a), sort_keys=True, default=str) == \
        json.dumps(_stable(rec_b), sort_keys=True, default=str)
    assert set(rec_a) == set(rec_b)
    assert "benchmark_core" not in rec_a and "CORE" not in rec_a["sendable_by_state"]
    assert [(p.symbol, p.side, p.qty) for p in fa.submitted] == \
        [(p.symbol, p.side, p.qty) for p in fb.submitted]
    assert all(p.symbol != "SPY" for p in fa.submitted)


def test_flag_on_adds_one_spy_target_clipped_by_max_name_frac(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PC_BENCHMARK_CORE", True)
    fb = FakeBroker().install(monkeypatch)
    _funnel(tmp_path, n=25)
    _ranking(tmp_path / "out", net=-0.2)
    _run(tmp_path)
    rec = _receipt(tmp_path)
    core = rec["benchmark_core"]
    assert core["enabled"] and core["applied"]
    assert core["status"] == "CORE_CLIPPED_BY_MAX_NAME_FRAC"
    assert core["want_weight"] == pytest.approx(1.0 - config.PROBE_GROSS_CAP)
    spy_book = [x for x in rec["book"] if x["symbol"] == "SPY"]
    assert len(spy_book) == 1 and spy_book[0]["state"] == "CORE"
    spy = [p for p in fb.submitted if p.symbol == "SPY"]
    assert len(spy) == 1 and spy[0].side == "buy"
    assert spy[0].qty == int((PB.MAX_NAME_FRAC * EQUITY) // PRICE), "the broker cap clipped it"
    assert any(r["symbol"] == "SPY" and "MAX_NAME_FRAC" in (r["refused"] or "")
               for r in rec["refusals"])
    assert rec["sendable_by_state"]["CORE"] == 1
    assert core["worst_case"]["gross_over_equity"] == pytest.approx(
        PB.MAX_NAME_FRAC + config.PROBE_GROSS_CAP)
    assert "-$" in core["worst_case_line"]


def test_flag_on_in_observe_sends_no_core(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PC_BENCHMARK_CORE", True)
    fb = FakeBroker().install(monkeypatch)
    _funnel(tmp_path, n=25)
    _ranking(tmp_path / "out", net=-0.2)
    S.u_plan(tmp_path / "out", "observe", asof=ASOF,
             funnel_path=tmp_path / "funnel.json", ledger_path=tmp_path / "ledger.jsonl",
             contracts_dir=tmp_path / "decisions" / "pc_plan")
    assert fb.submitted == []
