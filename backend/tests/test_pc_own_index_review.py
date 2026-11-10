"""Review of PR #89 (2026-11-11): four ways the own index could move money nobody decided.

R1  main shipped PC_BENCHMARK_CORE=False: ~$474k of SPY had no owner and the first
    EXPLOIT-acting session would sell it as an EXIT. Main now ships the core ON
    (merging changes no holding) and a held SPY with the core OFF and no own
    index is HELD (never planned), so retiring SPY happens only through the
    attended own-index activation.
R2  a contract that stops verifying turned every held index name into an EXIT.
    It now REFUSES: the held members are held, the session sends NO orders,
    and u_plan raises (red) after writing its receipt; the session start refuses
    non-zero.
R3  index buys went out when the SPY sell was skipped or failed (margin). Buys
    now wait for every sell to be CONFIRMED filled, are sized from the broker's
    cash after those fills, and are checked against equity before any buy.
R4  a young listing dropped 2020 from the binding 21-session window and lifted
    the index from 30% to 60%. The window is fixed (PC_OWN_INDEX_HISTORY_START),
    a member without that history is excluded (its slot is cash), the bound is
    min(full-coverage, any-coverage), and the gross never exceeds
    PC_OWN_INDEX_MAX_GROSS (the owner-approved 30%).

Offline. The broker is the replay fake from test_pc_plan_replay_owner_d14.py.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend import config
from backend.services import pc_broker as PB
from backend.services import pc_own_index as OI

NOW = datetime.now(timezone.utc)


def _funnel(tmp: Path, tickers: list[str], *, age_days: float = 1.0,
            name: str = "funnel.json") -> Path:
    p = tmp / name
    p.write_text(json.dumps({"generated_at": (NOW - timedelta(days=age_days)).isoformat(
        timespec="seconds"), "candidates": [
        {"ticker": t, "score": 1.0 - i / 100.0, "median_dollar_vol": 5e9 - i,
         "vol_annual": 0.30} for i, t in enumerate(tickers)]}), encoding="utf-8")
    return p


# ─────────────────────────── harness through sim_run.u_plan ─────────────────

class _Capture:
    """Every PlannedOrder pc_broker.plan_orders returns this session."""

    def __init__(self, mp: pytest.MonkeyPatch):
        self.plans: list = []
        real = PB.plan_orders

        def _wrapped(*a, **k):
            out = real(*a, **k)
            self.plans.extend(out)
            return out
        mp.setattr(PB, "plan_orders", _wrapped)

    def planned(self, sym: str) -> list:
        return [p for p in self.plans if p.symbol == sym and p.qty > 0]


def _harness(tmp: Path, mp: pytest.MonkeyPatch, *, own: bool, core: bool,
             extra: list | None = None, spy_qty: float = 100.0, open_syms: list | None = None,
             fills: str = "filled", freeze: bool = True, invalidate: bool = False,
             members: list | None = None, cash: float | None = None,
             fail_sells: bool = False, hist: dict | None = None,
             funnel_age: float = 1.0, funnel_tickers: list | None = None,
             previous: list | None = None, no_client_id_lookup: bool = False,
             setup=None):
    from backend.services import investment_committee as IC
    from backend.tests import test_pc_plan_replay_owner_d14 as R
    from backend.tests.test_u_plan_probe import ASOF, _ranking
    from scripts import sim_run as S
    pos = ([{"symbol": "SPY", "qty": spy_qty, "market_value": spy_qty * 779.705,
             "current_price": 779.705}] if spy_qty else []) + list(extra or [])
    rb = R.ReplayBroker(extra=pos).install(mp)
    R._rf_stub(mp)
    cap = _Capture(mp)
    mp.setattr(config, "PC_SLEEVE_REVISION_FLOW", True)
    mp.setattr(config, "PC_BENCHMARK_CORE", core)
    mp.setattr(config, "PC_BENCHMARK_CORE_EXEMPT_FROM_NAME_CAP", core)
    mp.setattr(config, "PC_OWN_INDEX", own)
    from backend.services import pc_sleeves as SL

    def _hist(names, *a, **k):
        if callable(hist):
            return hist(names)
        if hist is not None:
            return {"eligible": list(names), "short_history": [], **hist}
        return {"worst_window_return": -0.20, "worst_window_end": "2020-03-16",
                "window_sessions": 21, "worst_day_return": -0.08, "worst_day": "2020-03-12",
                "panel": "stub", "eligible": list(names), "short_history": []}
    mp.setattr(SL, "bound_history", _hist)
    mp.setattr(OI, "bound_history", _hist, raising=False)
    mp.setattr(IC, "issuer_map", lambda *a, **k: ({}, "stub"))
    # an order book that confirms fills, and an account the gate re-reads
    sent_orders: dict = {}

    def _submit(plan, **kw):
        if fail_sells and plan.side == "sell":
            raise PB.BrokerError("rejected by the venue (test)")
        rb.submitted.append(plan)
        coid = f"aegispc-test-{len(rb.submitted):04d}"
        sent_orders[coid] = plan
        return {"status": "submitted", "client_order_id": coid, "order_id": coid,
                "symbol": plan.symbol, "side": plan.side, "qty": plan.qty,
                "notional": plan.notional, "reason": plan.reason}
    mp.setattr(PB, "submit", _submit)
    def _by_coid(coid):
        return {"client_order_id": coid, "status": fills, "symbol": sent_orders[coid].symbol,
                "filled_qty": str(sent_orders[coid].qty if fills == "filled" else 0)}
    if no_client_id_lookup:
        # the RUNTIME's pc_broker (wip/2026-10-07-day) has no order_by_client_id
        mp.delattr(PB, "order_by_client_id", raising=False)
    else:
        mp.setattr(PB, "order_by_client_id", _by_coid)

    def _orders(status: str = "all", limit: int = 100, after=None, **kw):
        if status == "open":
            return [{"symbol": s} for s in (open_syms or [])]
        return [_by_coid(c) for c in reversed(list(sent_orders))][:limit]
    mp.setattr(PB, "orders", _orders)
    eq = float(R.STATE["equity"])

    def _account():
        proceeds = sum(p.qty * p.price for p in rb.submitted if p.side == "sell")
        spent = sum(p.qty * p.price for p in rb.submitted if p.side == "buy")
        c = (float(R.STATE["cash"]) if cash is None else cash) + proceeds - spent
        return {"cash": str(c), "equity": str(eq), "long_market_value": str(eq - c),
                "account_number": config.PC_PAPER_ACCOUNT_NUMBER}
    mp.setattr(PB, "account", _account)
    mp.setattr(OI, "_sleep", lambda s: None, raising=False)
    folder = tmp / "decisions" / "pc_plan"
    if freeze:
        OI.freeze(folder / OI.CONTRACT_FILE)
    if members is not None:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / OI.MEMBERS_FILE).write_text(json.dumps({
            "schema": OI.MEMBERS_SCHEMA, "policy_hash": "x", "frozen_utc": NOW.isoformat(),
            "members": members, "previous_members": list(previous or [])}),
            encoding="utf-8")
    if invalidate:
        # any edit to config or code the contract covers: here a shared key
        mp.setattr(config, "PC_OWN_INDEX_N", int(config.PC_OWN_INDEX_N) + 1)
    f = _funnel(tmp, (R.HELD + ["IDX1", "IDX2", "SPY", "IDX3", "IDX4", "IDX5"]
                      if funnel_tickers is None else funnel_tickers), age_days=funnel_age)
    if setup is not None:
        setup(mp)
    _ranking(tmp / "out", net=-0.2)
    err = None
    try:
        S.u_plan(tmp / "out", "paper_profit", asof=ASOF, funnel_path=f,
                 ledger_path=tmp / "ledger.jsonl", contracts_dir=folder,
                 bars_paths=[tmp / "bars.parquet"])
    except Exception as exc:                                       # noqa: BLE001
        err = exc
    rec = json.loads((tmp / "out" / "intended_book.json").read_text(encoding="utf-8"))
    return rec, rb, cap, err


def _held(sym: str, qty: float, px: float = 50.0) -> dict:
    return {"symbol": sym, "qty": qty, "market_value": qty * px, "current_price": px}


# ─────────────────────────── R1 ─────────────────────────────────────────────

def test_main_ships_the_spy_core_on_so_merging_changes_no_holding():
    from backend.tests.conftest import SHIPPED_OWNER_D14_FLAGS
    assert SHIPPED_OWNER_D14_FLAGS["PC_BENCHMARK_CORE"] is True
    assert SHIPPED_OWNER_D14_FLAGS["PC_OWN_INDEX"] is False


def test_core_off_without_the_own_index_never_plans_a_spy_sell(tmp_path, monkeypatch):
    rec, rb, cap, err = _harness(tmp_path, monkeypatch, own=False, core=False, spy_qty=633.0)
    assert err is None
    assert cap.planned("SPY") == [], "a held SPY with no owner must be HELD, never an EXIT"
    assert not [p for p in rb.submitted if p.symbol == "SPY"]
    assert "SPY" in (rec.get("benchmark_hold") or {}).get("held", [])


# ─────────────────────────── R2 ─────────────────────────────────────────────

IDX_HELD = [_held(s, 200.0) for s in ("IDX1", "IDX2", "IDX3")]


def test_a_contract_that_stops_verifying_refuses_and_liquidates_nothing(tmp_path, monkeypatch):
    rec, rb, cap, err = _harness(tmp_path, monkeypatch, own=True, core=False,
                                 extra=IDX_HELD, members=["IDX1", "IDX2", "IDX3"],
                                 invalidate=True)
    for s in ("IDX1", "IDX2", "IDX3", "SPY"):
        assert not [p for p in cap.planned(s) if p.side == "sell"], s
    assert rb.submitted == [], "a contract refusal sends NO orders at all"
    assert "changed since the freeze" in rec["own_index"]["refused"]
    assert rec["send_block"] and "own index contract" in rec["send_block"]
    assert isinstance(err, OI.OwnIndexRefused), "the plan unit goes red"


def test_rollback_flag_off_holds_the_index_names_instead_of_exiting_them(tmp_path, monkeypatch):
    rec, rb, cap, err = _harness(tmp_path, monkeypatch, own=False, core=False,
                                 extra=IDX_HELD, members=["IDX1", "IDX2", "IDX3"])
    for s in ("IDX1", "IDX2", "IDX3"):
        assert not cap.planned(s), s
    assert set(rec["own_index_rollback_hold"]["held"]) == {"IDX1", "IDX2", "IDX3"}


def test_the_session_start_refuses_non_zero_on_a_contract_mismatch(tmp_path, monkeypatch):
    from scripts import sim_run as S
    monkeypatch.setattr(config, "PC_OWN_INDEX", True)
    folder = tmp_path / "pc_plan"
    OI.freeze(folder / OI.CONTRACT_FILE)
    assert S._own_index_startup_refusal(folder) is None
    monkeypatch.setattr(config, "PC_OWN_INDEX_N", int(config.PC_OWN_INDEX_N) + 1)
    assert "changed since the freeze" in S._own_index_startup_refusal(folder)
    monkeypatch.setattr(config, "PC_OWN_INDEX", False)
    assert S._own_index_startup_refusal(folder) is None


# ─────────────────────────── R3 ─────────────────────────────────────────────

def _idx_buys(rb) -> list:
    return [p for p in rb.submitted if p.side == "buy" and p.symbol.startswith("IDX")]


def test_baseline_index_buys_go_out_after_the_spy_sell_is_confirmed(tmp_path, monkeypatch):
    rec, rb, cap, err = _harness(tmp_path, monkeypatch, own=True, core=False)
    assert err is None, err
    assert ("SPY", "sell") in {(p.symbol, p.side) for p in rb.submitted}
    assert _idx_buys(rb), rec["own_index"].get("line")
    first_buy = min(i for i, p in enumerate(rb.submitted) if p.side == "buy")
    assert all(p.side == "sell" for p in rb.submitted[:first_buy])


def test_no_index_buy_when_the_spy_sell_is_skipped_for_an_open_order(tmp_path, monkeypatch):
    rec, rb, cap, err = _harness(tmp_path, monkeypatch, own=True, core=False, open_syms=["SPY"])
    assert not [p for p in rb.submitted if p.symbol == "SPY"]
    assert _idx_buys(rb) == [], "index buys went out although the SPY sell did not"
    assert any(s.get("state") == "OWN_INDEX" and s.get("status") == "skipped"
               for s in rec["sent"])


def test_no_index_buy_when_the_spy_sell_fails(tmp_path, monkeypatch):
    rec, rb, cap, err = _harness(tmp_path, monkeypatch, own=True, core=False, fail_sells=True)
    assert any(x.get("symbol") == "SPY" and x.get("status") == "FAILED" for x in rec["sent"])
    assert _idx_buys(rb) == [], "index buys went out although the SPY sell failed"


def test_no_index_buy_when_the_sell_is_not_confirmed_filled(tmp_path, monkeypatch):
    rec, rb, cap, err = _harness(tmp_path, monkeypatch, own=True, core=False, fills="new")
    assert ("SPY", "sell") in {(p.symbol, p.side) for p in rb.submitted}
    assert _idx_buys(rb) == []


def test_index_buys_are_sized_from_cash_after_the_fills(tmp_path, monkeypatch):
    # little cash and a small SPY: the buys must shrink to cash - buffer, never margin
    rec, rb, cap, err = _harness(tmp_path, monkeypatch, own=True, core=False, spy_qty=10.0,
                                 cash=5_000.0)
    spent = sum(p.qty * p.price for p in _idx_buys(rb))
    proceeds = sum(p.qty * p.price for p in rb.submitted if p.side == "sell")
    eq = float(rec["equity"])
    assert spent <= 5_000.0 + proceeds - config.PC_OWN_INDEX_CASH_BUFFER * eq + 1e-6


class _GateBroker:
    def __init__(self, *, status="filled", acct=None):
        self.status, self.acct = status, acct

    def order_by_client_id(self, coid):
        return {"client_order_id": coid, "status": self.status}

    def account(self):
        if isinstance(self.acct, Exception):
            raise self.acct
        return self.acct


def _gate(sent, buys, broker, *, other_buys=()):
    return OI.gate_index_buys(buys, sells=[p for p in [PB.PlannedOrder(
        "SPY", "sell", 100, 70_000.0, "x", price=700.0)]], sent=sent, broker=broker,
        cash_buffer=0.01, other_buys=list(other_buys), wait_s=0.0, poll_s=0.0,
        sleep=lambda s: None)


def _buy(sym, qty, px=100.0):
    return PB.PlannedOrder(sym, "buy", qty, qty * px, "x", price=px)


@pytest.mark.parametrize("sent", [
    [{"status": "skipped", "symbol": "SPY", "why": "open"}],
    [{"status": "FAILED", "symbol": "SPY", "error": "rejected"}],
    [],
])
def test_gate_refuses_every_index_buy_when_a_sell_did_not_go_out(sent):
    g = _gate(sent, [_buy("A", 10)], _GateBroker(acct={"cash": "1e6", "equity": "1e6",
                                                     "long_market_value": "0"}))
    assert g["allowed"] == {} and "SPY" in g["line"]


def test_gate_refuses_when_the_account_is_unreadable_or_the_fill_unconfirmed():
    ok = [{"status": "submitted", "symbol": "SPY", "client_order_id": "c1"}]
    g = _gate(ok, [_buy("A", 10)], _GateBroker(acct=PB.BrokerError("401")))
    assert g["allowed"] == {}
    g = _gate(ok, [_buy("A", 10)], _GateBroker(status="partially_filled",
                                               acct={"cash": "1e6", "equity": "1e6",
                                                     "long_market_value": "0"}))
    assert g["allowed"] == {} and "partially_filled" in g["line"]


def test_gate_sizes_buys_from_cash_and_checks_gross_against_equity():
    ok = [{"status": "submitted", "symbol": "SPY", "client_order_id": "c1"}]
    # cash 30k, equity 1m, buffer 1% => 20k of room; a 5k buy elsewhere leaves 15k
    a, b = _buy("A", 100), _buy("B", 100)
    g = _gate(ok, [a, b], _GateBroker(acct={"cash": "30000", "equity": "1000000",
                                            "long_market_value": "970000"}),
              other_buys=[_buy("X", 50)])
    spent = sum(q * 100.0 * (1 + OI.BUY_PRICE_MARGIN) for q in g["allowed"].values())
    assert spent <= 15_000.0 + 1e-6
    assert g["allowed"][id(a)] == 100 and 0 < g["allowed"][id(b)] < 100
    assert g["cut_shares"] == {"B": 100 - g["allowed"][id(b)]}
    # plenty of cash but the book is already at 99% gross: nothing fits
    g = _gate(ok, [_buy("A", 10)], _GateBroker(acct={"cash": "500000", "equity": "1000000",
                                                     "long_market_value": "990000"}))
    assert g["allowed"] == {}


# ─────────────────────────── R4 ─────────────────────────────────────────────

def _bars(path: Path) -> Path:
    """OLD1/OLD2 priced since 2016 with a -35% March 2020; YOUNG listed 2025."""
    days = pd.bdate_range("2016-01-04", "2026-10-30")
    rng = np.random.default_rng(5)
    rows = []
    for sym, start in (("OLD1", "2016-01-04"), ("OLD2", "2016-01-04"), ("YOUNG", "2025-03-03")):
        d = days[days >= pd.Timestamp(start)]
        r = rng.normal(0.0003, 0.01, len(d))
        crash = (d >= pd.Timestamp("2020-02-24")) & (d <= pd.Timestamp("2020-03-20"))
        r[crash] = -0.022
        close = 100 * np.cumprod(1 + r)
        rows += [{"symbol": sym, "date": x, "close": c} for x, c in zip(d, close)]
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def test_a_young_listing_is_excluded_and_cannot_drop_2020_from_the_bound(tmp_path, monkeypatch):
    from backend.services import pc_sleeves as SL
    bars = _bars(tmp_path / "bars.parquet")
    monkeypatch.setattr(SL, "deep_bars_path", lambda: bars)
    h = OI.bound_history(["OLD1", "OLD2", "YOUNG"])
    assert h["short_history"] == ["YOUNG"] and h["eligible"] == ["OLD1", "OLD2"]
    assert h["worst_window_return"] < -0.30, h        # March 2020 stays in the window
    assert h["history_start"] == str(config.PC_OWN_INDEX_HISTORY_START)
    # the mechanism the review found: with YOUNG, the full-coverage window starts 2025
    sl = SL.basket_history(["OLD1", "OLD2", "YOUNG"], bars)
    assert sl["worst_window_return"] > -0.30


def test_the_index_never_exceeds_the_owner_approved_share():
    pick = OI.choose_gross(names=[f"N{i}" for i in range(20)], n_declared=20,
                           max_name_frac=0.03, room=0.63, other_weights={"RF": 0.30},
                           sigmas={}, fallback=0.02, k=3.0, day_limit=0.10,
                           worst_21=-0.12, window_limit=0.10, step=0.05,
                           max_gross=float(config.PC_OWN_INDEX_MAX_GROSS))
    assert config.PC_OWN_INDEX_MAX_GROSS == pytest.approx(0.30)
    assert pick["gross"] <= 0.30 + 1e-12 and pick["binding"] == "owner_max_gross"


def test_the_plan_leaves_a_short_history_members_slot_in_cash(tmp_path):
    c = OI.freeze(tmp_path / OI.CONTRACT_FILE, now=NOW)
    row = {"members": ["AAA", "BBB", "YNG"], "previous_members": [], "frozen_utc": NOW.isoformat()}
    res = OI.plan(contract=c, members_row=row, refusal=None, equity=1_000_000.0, held={},
                  prices={"AAA": 100.0, "BBB": 50.0, "YNG": 20.0}, acting_weights={},
                  claimed=set(), held_residual={}, sigmas={}, fallback_sigma=0.02,
                  history={"worst_window_return": -0.25, "short_history": ["YNG"],
                           "eligible": ["AAA", "BBB"]}, mode="paper_profit")
    assert "YNG" not in res["weights"] and res["skipped_short_history"] == ["YNG"]
    assert res["n_slots_cash"] == config.PC_OWN_INDEX_N - 2


def test_choose_gross_refuses_a_zero_declared_count():
    pick = OI.choose_gross(names=["A"], n_declared=0, max_name_frac=0.03, room=0.5,
                           other_weights={}, sigmas={}, fallback=0.02, k=3.0, day_limit=0.1,
                           worst_21=-0.1, window_limit=0.1, step=0.05, max_gross=0.3)
    assert pick["gross"] == 0.0 and pick["binding"] == "n_declared_zero"
