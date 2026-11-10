"""Second review of PR #89 (2026-11-11): a refusal never sells; the owner cap and
min(full, any) are pinned; the buy gate works on the RUNTIME's broker.

B1  When the 21-session bound could not be computed, or no gross passed both
    limits, `plan()` refused -- and then planned a full SELL of every held
    member (OWN_INDEX_EXIT) and of SPY (CORE_EXIT). A refusal of ANY kind now
    holds everything: no index sell, no SPY sell. Names leave only at a
    SUCCESSFUL rebuild (members chosen AND sized), and SPY is retired only in
    the same plan that buys the index (all-or-nothing in intent).
R5  Removing the owner cap from `plan()`, or taking the bound as `full`
    instead of min(full, any), left every test green. Two tests now fail
    under each mutation.
B2  The runtime's pc_broker (wip/2026-10-07-day) has no `order_by_client_id`.
    The gate now confirms fills through `orders(status="all")` when the
    lookup is absent (both broker versions expose it), and the session start
    refuses (rc 7) when a broker exposes neither.

Offline. The harness drives the real `sim_run.u_plan` (test_pc_own_index_review).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend import config
from backend.services import pc_broker as PB
from backend.services import pc_own_index as OI
from backend.tests.test_pc_own_index_review import IDX_HELD, NOW, _harness, _idx_buys
from backend.tests.test_pc_plan_replay_owner_d14 import HELD as REPLAY_HELD

INDEX_SYMS = ("SPY", "IDX1", "IDX2", "IDX3", "IDX4", "IDX5")
#: PROBE reads the same candidate file and takes its top names; the replay's
#: held names go first so the IDX names are the index's (as in the R-harness).
NO_IDX3 = REPLAY_HELD + ["IDX1", "IDX2", "IDX4", "IDX5"]


def _index_sells(rb, cap, *, skip_spy: bool = False) -> dict:
    """Every sell INTENT (planned, qty > 0) and every SUBMITTED sell of SPY or an IDX name."""
    syms = [s for s in INDEX_SYMS if not (skip_spy and s == "SPY")]
    return {"planned": sorted((p.symbol, p.qty) for p in cap.plans
                              if p.side == "sell" and p.qty > 0 and p.symbol in syms),
            "submitted": sorted((p.symbol, p.qty) for p in rb.submitted
                                if p.side == "sell" and p.symbol in syms)}


def _raise(exc):
    def _f(*a, **k):
        raise exc
    return _f


def _all_short(names):
    return {"error": "no member has history from 2020-01-02 (+10 d)", "eligible": [],
            "short_history": list(names)}


# Every refusal path the module and its sim_run hook have, through the REAL u_plan.
REFUSALS = {
    "bound_21_unknown": dict(hist={"error": "basket_history failed (test)"}),
    "bound_fails_at_every_step": dict(hist={"worst_window_return": -50.0,
                                            "worst_window_end": "2020-03-16"}),
    "all_members_short_history": dict(hist=_all_short),
    "candidate_file_stale": dict(funnel_age=30.0),
    "candidate_file_empty": dict(funnel_tickers=[]),
    "candidate_file_only_excluded": dict(funnel_tickers=["QQQ", "IWM"]),
    "membership_raises": dict(setup=lambda mp: mp.setattr(
        OI, "membership", _raise(ValueError("corrupt members file (test)")))),
    "plan_raises": dict(setup=lambda mp: mp.setattr(
        OI, "plan", _raise(RuntimeError("bug (test)")))),
    "bound_history_raises": dict(setup=lambda mp: mp.setattr(
        OI, "bound_history", _raise(OSError("panel unreadable (test)")))),
    "contract_mismatch": dict(invalidate=True),
    "contract_missing": dict(freeze=False),
    "leaver_with_bound_unknown": dict(hist={"error": "basket_history failed (test)"},
                                      funnel_tickers=NO_IDX3),
    "broker_cannot_confirm_a_fill": dict(setup=lambda mp: mp.setattr(
        OI, "fill_lookup_method", lambda broker: None)),
}


@pytest.mark.parametrize("case", sorted(REFUSALS))
def test_no_refusal_of_any_kind_produces_a_sell_intent(tmp_path, monkeypatch, case):
    rec, rb, cap, err = _harness(tmp_path, monkeypatch, own=True, core=False,
                                 extra=IDX_HELD, members=["IDX1", "IDX2", "IDX3"],
                                 **REFUSALS[case])
    oi = rec.get("own_index") or {}
    assert oi.get("refused"), f"{case}: expected a refusal, got {oi.get('line')}"
    assert _index_sells(rb, cap) == {"planned": [], "submitted": []}, (case, oi.get("line"))
    assert _idx_buys(rb) == [], case
    for s in ("IDX1", "IDX2", "IDX3", "SPY"):
        assert oi.get("state_of", {}).get(s) in (OI.HOLD_STATE, None), (case, s)
    if case in ("plan_raises", "bound_21_unknown", "candidate_file_stale"):
        # the receipt says HOLD, not EXIT, for what the index owns
        assert all(oi["state_of"].get(s) == OI.HOLD_STATE for s in ("IDX1", "IDX2", "IDX3")), case


def test_core_and_index_both_on_refuses_and_holds_the_held_members(tmp_path, monkeypatch):
    # the core plans SPY as before; the index's held members must not become EXITs
    rec, rb, cap, err = _harness(tmp_path, monkeypatch, own=True, core=True,
                                 extra=IDX_HELD, members=["IDX1", "IDX2", "IDX3"])
    assert "both True" in str((rec.get("own_index") or {}).get("refused"))
    assert _index_sells(rb, cap, skip_spy=True) == {"planned": [], "submitted": []}


def test_a_leaver_is_sold_only_at_a_successful_rebuild(tmp_path, monkeypatch):
    # the positive control for the leaver case above: a healthy rebuild sells IDX3
    rec, rb, cap, err = _harness(tmp_path, monkeypatch, own=True, core=False,
                                 extra=IDX_HELD, members=["IDX1", "IDX2", "IDX3"],
                                 funnel_tickers=NO_IDX3)
    assert err is None, err
    assert not rec["own_index"].get("refused"), rec["own_index"]["line"]
    assert rec["own_index"]["state_of"]["IDX3"] == OI.EXIT_STATE
    assert ("IDX3", 200) in _index_sells(rb, cap)["submitted"]
    assert ("SPY", "sell") in {(p.symbol, p.side) for p in rb.submitted}


# ─────────────────────── the same, on plan() alone ──────────────────────────

def _contract(tmp: Path) -> dict:
    return OI.freeze(tmp / OI.CONTRACT_FILE, now=NOW)


def _plan(tmp: Path, **over) -> dict:
    kw = dict(contract=_contract(tmp),
              members_row={"members": ["AAA", "BBB"], "previous_members": ["AAA", "OLD"],
                           "frozen_utc": NOW.isoformat()},
              refusal=None, equity=1_000_000.0,
              held={"SPY": 600.0, "AAA": 100.0, "OLD": 50.0},
              prices={"SPY": 700.0, "AAA": 100.0, "BBB": 50.0, "OLD": 20.0},
              acting_weights={}, claimed=set(), held_residual={}, sigmas={},
              fallback_sigma=0.02,
              history={"worst_window_return": -0.25, "eligible": ["AAA", "BBB"],
                       "short_history": []}, mode="paper_profit")
    kw.update(over)
    return OI.plan(**kw)


def _sells(res: dict) -> list:
    return [(p.symbol, p.qty) for p in res["plans"] if p.side == "sell" and p.qty > 0]


PLAN_REFUSALS = {
    "no_contract": dict(contract=None, refusal="no frozen contract"),
    "membership_refused": dict(refusal="candidate file is 30 days old",
                               members_row={"members": [], "previous_members": ["AAA", "OLD"]}),
    "members_empty": dict(members_row={"members": [], "previous_members": ["AAA", "OLD"]}),
    "all_claimed": dict(claimed={"AAA", "BBB"}),
    "all_short_history": dict(history={"error": "x", "short_history": ["AAA", "BBB"],
                                       "eligible": []}),
    "history_none": dict(history=None),
    "bound_unknown": dict(history={"error": "basket_history failed", "eligible": ["AAA", "BBB"],
                                   "short_history": []}),
    "bound_fails_every_step": dict(history={"worst_window_return": -50.0,
                                            "eligible": ["AAA", "BBB"], "short_history": []}),
    "one_day_budget_used_by_an_acting_sleeve": dict(acting_weights={"ACT": 0.85},
                                                    sigmas={"ACT": 0.05}),
    "no_room": dict(held_residual={"RES": 0.995}),
}


@pytest.mark.parametrize("case", sorted(PLAN_REFUSALS))
def test_plan_refusal_plans_no_sell(tmp_path, case):
    res = _plan(tmp_path, **PLAN_REFUSALS[case])
    assert res.get("refused"), case
    assert _sells(res) == [], (case, res.get("line"))
    assert res.get("exit_acting") is False
    assert not res.get("applied")


def test_plan_success_retires_spy_and_sells_the_leaver(tmp_path):
    # positive control: the same inputs, healthy, DO sell OLD and SPY
    res = _plan(tmp_path)
    assert not res.get("refused"), res["line"]
    sells = dict(_sells(res))
    assert sells.get("SPY") == 600 and sells.get("OLD") == 50
    assert res["state_of"]["OLD"] == OI.EXIT_STATE and res["exit_acting"] is True


def test_a_held_short_history_member_is_held_not_sold(tmp_path):
    res = _plan(tmp_path, held={"SPY": 600.0, "AAA": 100.0, "BBB": 300.0},
                history={"worst_window_return": -0.25, "eligible": ["AAA"],
                         "short_history": ["BBB"]})
    assert not res.get("refused"), res["line"]
    assert "BBB" not in dict(_sells(res)), "a member is sold only when it LEAVES the index"
    assert res["state_of"]["BBB"] == OI.HOLD_STATE


# ─────────────────────────── R5 ─────────────────────────────────────────────

def test_plan_caps_the_index_at_the_owner_approved_share(tmp_path):
    # 20 names, a mild bound and no other sleeve: without the cap the index is 60%
    names = [f"N{i:02d}" for i in range(20)]
    res = _plan(tmp_path, members_row={"members": names, "previous_members": [],
                                       "frozen_utc": NOW.isoformat()},
                held={}, prices={s: 100.0 for s in names},
                history={"worst_window_return": -0.10, "eligible": names, "short_history": []})
    assert res["gross"] == pytest.approx(float(config.PC_OWN_INDEX_MAX_GROSS))
    assert res["sizing"]["binding"] == "owner_max_gross"
    assert res["worst_case"]["largest_admissible"]["gross"] <= config.PC_OWN_INDEX_MAX_GROSS


def test_u_plan_never_sizes_the_index_above_the_owner_approved_share(tmp_path, monkeypatch):
    # bound -10%: bound 2 alone would allow 100%; N x cap is 60%
    rec, rb, cap, err = _harness(tmp_path, monkeypatch, own=True, core=False,
                                 hist={"worst_window_return": -0.10,
                                       "worst_window_end": "2020-03-16"},
                                 funnel_tickers=REPLAY_HELD + [f"IDX{i}" for i in range(1, 25)],
                                 setup=lambda mp: mp.setattr(config, "PC_SLEEVE_REVISION_FLOW",
                                                             False))
    assert err is None, err
    oi = rec["own_index"]
    assert oi["sizing"]["upper"] <= config.PC_OWN_INDEX_MAX_GROSS + 1e-9, oi["line"]
    assert oi["gross"] <= config.PC_OWN_INDEX_MAX_GROSS + 1e-9, oi["line"]
    assert oi["sizing"]["upper_set_by"] == "owner_max_gross", "room must not be what binds here"


def _gap_bars(path: Path) -> Path:
    """GAP1 and GAP2 priced since 2016; GAP2 has no bars May-June 2022 while
    GAP1 falls ~35%. Only the any-coverage window sees the fall."""
    days = pd.bdate_range("2016-01-04", "2026-10-30")
    rng = np.random.default_rng(11)
    rows = []
    hole = (days >= pd.Timestamp("2022-05-02")) & (days <= pd.Timestamp("2022-06-30"))
    for sym in ("GAP1", "GAP2"):
        r = rng.normal(0.0003, 0.006, len(days))
        if sym == "GAP1":
            r[(days >= pd.Timestamp("2022-05-02")) & (days <= pd.Timestamp("2022-05-31"))] = -0.022
        close = 100 * np.cumprod(1 + r)
        keep = ~hole if sym == "GAP2" else np.ones(len(days), bool)
        rows += [{"symbol": sym, "date": d, "close": c}
                 for d, c, k in zip(days, close, keep) if k]
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def test_the_bound_is_the_worse_of_full_and_any_coverage(tmp_path, monkeypatch):
    from backend.services import pc_sleeves as SL
    bars = _gap_bars(tmp_path / "bars.parquet")
    monkeypatch.setattr(SL, "deep_bars_path", lambda: bars)
    h = OI.bound_history(["GAP1", "GAP2"])
    assert h["eligible"] == ["GAP1", "GAP2"] and not h.get("error"), h
    assert h["worst_window_return_any"] < -0.30, h
    assert h["worst_window_return_full"] > -0.20, h
    assert h["worst_window_return"] == pytest.approx(h["worst_window_return_any"])


# ─────────────────────────── B2 ─────────────────────────────────────────────

class _RuntimeShapedBroker:
    """The runtime's pc_broker surface: orders(status, limit, after) and account();
    NO order_by_client_id."""

    def __init__(self, rows, acct):
        self.rows, self.acct, self.calls = rows, acct, []

    def orders(self, status: str = "all", limit: int = 100, after=None):
        self.calls.append((status, limit))
        return list(self.rows)

    def account(self):
        return self.acct


def _sell_sent():
    return [{"status": "submitted", "symbol": "SPY", "client_order_id": "aegispc-c1"}]


def _gate(broker, sent=None, buys=None):
    return OI.gate_index_buys(
        buys or [PB.PlannedOrder("A", "buy", 10, 1_000.0, "x", price=100.0)],
        sells=[PB.PlannedOrder("SPY", "sell", 100, 70_000.0, "x", price=700.0)],
        sent=_sell_sent() if sent is None else sent, broker=broker, cash_buffer=0.01,
        other_buys=[], wait_s=0.0, poll_s=0.0, sleep=lambda s: None)


ACCT = {"cash": "100000", "equity": "1000000", "long_market_value": "900000"}


def test_gate_confirms_fills_through_orders_when_the_broker_has_no_client_id_lookup():
    b = _RuntimeShapedBroker([{"client_order_id": "aegispc-other", "status": "new"},
                              {"client_order_id": "aegispc-c1", "status": "filled"}], ACCT)
    g = _gate(b)
    assert not g.get("refused"), g["line"]
    assert list(g["allowed"].values()) == [10]
    assert b.calls and b.calls[0][0] == "all"
    assert g["fill_lookup"] == "orders"


@pytest.mark.parametrize("rows", [[], [{"client_order_id": "aegispc-c1", "status": "new"}],
                                  [{"client_order_id": "aegispc-c1",
                                    "status": "partially_filled"}]])
def test_gate_on_the_runtime_broker_refuses_an_unlisted_or_unfilled_sell(rows):
    g = _gate(_RuntimeShapedBroker(rows, ACCT))
    assert g["allowed"] == {} and g.get("refused")


def test_gate_refuses_at_once_when_the_broker_has_no_order_lookup_at_all():
    class _Bare:
        def account(self):
            return ACCT
    slept = []
    g = OI.gate_index_buys([PB.PlannedOrder("A", "buy", 10, 1_000.0, "x", price=100.0)],
                           sells=[PB.PlannedOrder("SPY", "sell", 100, 7e4, "x", price=700.0)],
                           sent=_sell_sent(), broker=_Bare(), cash_buffer=0.01, other_buys=[],
                           wait_s=60.0, poll_s=1.0, sleep=slept.append)
    assert g["allowed"] == {} and "no order lookup" in g["line"] and slept == []


def test_u_plan_on_a_runtime_shaped_broker_still_buys_the_index_after_the_spy_sell(
        tmp_path, monkeypatch):
    rec, rb, cap, err = _harness(tmp_path, monkeypatch, own=True, core=False,
                                 no_client_id_lookup=True)
    assert err is None, err
    assert not hasattr(PB, "order_by_client_id")
    assert ("SPY", "sell") in {(p.symbol, p.side) for p in rb.submitted}
    assert _idx_buys(rb), rec["own_index"].get("line")


def test_the_session_start_refuses_when_the_broker_cannot_confirm_a_fill(tmp_path,
                                                                         monkeypatch):
    from scripts import sim_run as S
    monkeypatch.setattr(config, "PC_OWN_INDEX", True)
    folder = tmp_path / "pc_plan"
    OI.freeze(folder / OI.CONTRACT_FILE)
    assert S._own_index_startup_refusal(folder) is None
    monkeypatch.delattr(PB, "order_by_client_id", raising=False)
    assert S._own_index_startup_refusal(folder) is None, "orders() is enough"
    monkeypatch.delattr(PB, "orders", raising=False)
    assert "cannot confirm" in str(S._own_index_startup_refusal(folder))


def test_u_plan_holds_everything_when_the_broker_cannot_confirm_a_fill(tmp_path, monkeypatch):
    # all-or-nothing in intent: no SPY sale unless the path that later buys exists
    rec, rb, cap, err = _harness(
        tmp_path, monkeypatch, own=True, core=False, extra=IDX_HELD,
        members=["IDX1", "IDX2", "IDX3"],
        setup=lambda mp: mp.setattr(OI, "fill_lookup_method", lambda broker: None))
    assert "cannot confirm" in str(rec["own_index"].get("refused"))
    assert _index_sells(rb, cap) == {"planned": [], "submitted": []}
    assert rec["own_index"]["state_of"]["SPY"] == OI.HOLD_STATE


def test_preflight_lookup_method_is_reported():
    assert OI.fill_lookup_method(PB) in ("order_by_client_id", "orders")

    class _Bare:
        pass
    assert OI.fill_lookup_method(_Bare()) is None


def test_dry_run_reads_the_fill_lookup_from_the_broker_source(tmp_path):
    from scripts import pc_own_index as CLI
    assert CLI.broker_fill_lookup() == "order_by_client_id"          # this checkout (main)
    rt = tmp_path / "pc_broker_runtime.py"
    rt.write_text("def orders(status='all', limit=100, after=None):\n    return []\n",
                  encoding="utf-8")
    assert CLI.broker_fill_lookup(rt) == "orders"                    # the runtime's shape
    bare = tmp_path / "pc_broker_bare.py"
    bare.write_text("def account():\n    return {}\n", encoding="utf-8")
    assert CLI.broker_fill_lookup(bare) is None
    rc = CLI.main(["dry-run", "--broker-source", str(bare), "--snapshot",
                   str(tmp_path / "missing.json")])
    assert rc == CLI.RC_REFUSED
