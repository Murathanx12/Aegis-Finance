"""Offline tests for the fleet daily manager (`backend/services/fleet_manager.py`).

No network: the only object that could reach the venue is `Venue`, and every
test hands it a fake transport. Dates are derived from `today`, never literal.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.services import fleet_manager as FM


def _contract(tmp_path, **over):
    body = {"schema": "fleet_manager_contract/1", "role": "hackX", "version": "v1",
            "licence": FM.LICENCE, "alpha_source": "test", "selection": {"kind": "legacy_hold"},
            "legacy_terms": {"expected_horizon_sessions": 21, "min_normal_hold_sessions": 5,
                             "stop_frac": 0.10, "profit_target_frac": None},
            "stop_rule": FM.stop_rule_block(0.10), "caps": FM.caps_block(), "costs": FM.costs_block(),
            "twin": {"weights": {}}}
    body.update(over)
    return FM.freeze_contract(body, base=tmp_path)


class FakeTransport:
    """Records every call; answers from a small in-memory venue."""

    def __init__(self):
        self.calls = []
        self.orders = {}          # coid -> order

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, body))
        if method == "GET" and "/v2/orders:by_client_order_id" in url:
            coid = url.split("client_order_id=")[1]
            o = self.orders.get(coid)
            return (200, json.dumps(o).encode()) if o else (404, b'{"message":"not found"}')
        if method == "POST" and url.endswith("/v2/orders"):
            b = json.loads(body)
            if b["client_order_id"] in self.orders:
                return 422, b'{"message":"client_order_id must be unique"}'
            o = {"id": f"id-{len(self.orders)}", "status": "accepted", **b}
            self.orders[b["client_order_id"]] = o
            return 200, json.dumps(o).encode()
        return 200, b"{}"


# ─────────────────────────────── hard limits ────────────────────────────────

def test_limits_refuse_leverage_gross_name_short_options_and_market(tmp_path):
    c = _contract(tmp_path)
    eq = 100_000.0
    buy = FM.Action("hackX", "buy", "AAA", 100, "buy", "limit", limit_price=100.0)
    # cash would go negative -> borrowing
    assert "no leverage" in FM.check_limits(buy, equity=eq, cash=5_000, held={}, mv={}, gross=0, contract=c)
    # gross above 100% of equity
    assert "gross" in FM.check_limits(buy, equity=eq, cash=50_000, held={}, mv={}, gross=95_000, contract=c)
    # one name above 10%
    big = FM.Action("hackX", "buy", "AAA", 120, "buy", "limit", limit_price=100.0)
    assert "of equity" in FM.check_limits(big, equity=eq, cash=50_000, held={}, mv={}, gross=0, contract=c)
    # a sell larger than the long position would open a short
    sell = FM.Action("hackX", "sell", "AAA", 11, "sell", "limit", limit_price=100.0)
    assert "short" in FM.check_limits(sell, equity=eq, cash=0, held={"AAA": 10}, mv={}, gross=0, contract=c)
    # an option symbol can never be ordered
    opt = FM.Action("hackX", "buy", "BE261016C00290000", 1, "buy", "limit", limit_price=5.0)
    assert "not a plain equity" in FM.check_limits(opt, equity=eq, cash=eq, held={}, mv={}, gross=0, contract=c)
    # market orders are refused
    mkt = FM.Action("hackX", "buy", "AAA", 1, "buy", "market", limit_price=100.0)
    assert "never market" in FM.check_limits(mkt, equity=eq, cash=eq, held={}, mv={}, gross=0, contract=c)
    # an admissible buy passes
    ok = FM.Action("hackX", "buy", "AAA", 50, "buy", "limit", limit_price=100.0)
    assert FM.check_limits(ok, equity=eq, cash=50_000, held={}, mv={}, gross=10_000, contract=c) is None


def test_caps_are_hard_and_unlevered():
    caps = FM.caps_block()
    assert caps["max_gross_frac"] <= 1.0
    assert caps["max_name_frac"] <= 0.10
    assert caps["shorting"] is False and caps["new_options"] is False and caps["leverage"] is False


def test_turnover_budget_refuses_by_name_and_spares_protection():
    acts = [FM.Action("r", "buy", s, 100, "buy", "limit", limit_price=100.0) for s in ("A", "B", "C")]
    acts.append(FM.Action("r", "stop_new", "D", 100, "sell", "stop", "gtc", stop_price=90.0, protective=True))
    spent = FM.apply_turnover_budget(acts, equity=50_000, used_today=0.0, frac=0.5)
    assert spent == 20_000
    assert acts[2].refused and "turnover" in acts[2].refused
    assert acts[3].refused is None


# ─────────────────────────────── idempotency ────────────────────────────────

def test_client_order_id_is_deterministic_and_price_free():
    day = date.today().isoformat()
    a = FM.client_order_id("hack1", day, "buy", "AAA", "h1")
    assert a == FM.client_order_id("hack1", day, "buy", "AAA", "h1")
    assert a.startswith(FM.COID_PREFIX + "-hack1-")
    assert a != FM.client_order_id("hack1", day, "buy", "AAA", "h2")          # another contract
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert a != FM.client_order_id("hack1", tomorrow, "buy", "AAA", "h1")      # another session
    assert len(a) <= 128


def test_a_rerun_cannot_double_submit():
    t = FakeTransport()
    v = FM.Venue("k", "s", transport=t)
    coid = FM.client_order_id("hack1", date.today().isoformat(), "buy", "AAA", "h")
    a1 = FM.Action("hack1", "buy", "AAA", 10, "buy", "limit", limit_price=10.01, coid=coid)
    a2 = FM.Action("hack1", "buy", "AAA", 10, "buy", "limit", limit_price=10.07, coid=coid)  # price moved
    r1, r2 = FM.submit_once(v, a1), FM.submit_once(v, a2)
    assert r1["sent"] is True
    assert r2["sent"] is False and "idempotent" in r2["outcome"]
    assert sum(1 for m, u, _ in t.calls if m == "POST") == 1


def test_venue_refuses_a_live_host():
    with pytest.raises(FM.FleetRefusal):
        FM.Venue("k", "s", host="https://api.alpaca.markets", transport=FakeTransport())


# ─────────────────────────────── reconciliation ─────────────────────────────

def test_reconcile_ok_when_fills_explain_the_change():
    prev = {"AAA": 100.0}
    fills = [{"symbol": "AAA", "side": "sell", "qty": "100"}, {"symbol": "BBB", "side": "buy", "qty": "5"}]
    r = FM.reconcile(prev, fills, {"BBB": 5.0}, [{"client_order_id": "aegisfm-x"}])
    assert r["ok"] and r["status"] == "OK"


def test_reconcile_refuses_an_unexplained_position():
    r = FM.reconcile({"AAA": 100.0}, [], {"AAA": 60.0}, [])
    assert not r["ok"] and r["status"] == "MISMATCH"
    assert r["mismatches"][0]["symbol"] == "AAA"


def test_reconcile_refuses_a_foreign_executor():
    r = FM.reconcile({}, [], {}, [{"client_order_id": "manual-close-hack5-1", "symbol": "X"}])
    assert not r["ok"] and r["status"] == "FOREIGN_ORDERS"


def test_reconcile_without_a_baseline_is_not_ok():
    assert FM.reconcile(None, [], {}, [])["ok"] is False


# ─────────────────────────────── stops in sigma ─────────────────────────────

def test_stop_distance_is_quoted_in_sigma_and_clipped():
    d, how = FM.sigma_stop_frac(0.02, max_frac=0.10, k=3.0, min_frac=0.04)
    assert d == pytest.approx(0.06) and "sigma" in how
    assert FM.sigma_stop_frac(0.005, max_frac=0.10, k=3.0, min_frac=0.04)[0] == pytest.approx(0.04)
    assert FM.sigma_stop_frac(0.09, max_frac=0.12, k=3.0, min_frac=0.04)[0] == pytest.approx(0.12)
    assert FM.sigma_stop_frac(None, max_frac=0.10)[0] == pytest.approx(0.10)


def test_maintenance_protects_the_uncovered_quantity_at_the_sigma_distance(tmp_path):
    c = _contract(tmp_path)
    day = date.today().isoformat()
    pos = [{"symbol": "AAA", "qty": "100", "current_price": "50", "asset_class": "us_equity"}]
    far = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
    orders = [{"id": "o1", "symbol": "AAA", "side": "sell", "type": "stop", "qty": "40",
               "stop_price": "45", "client_order_id": "aat-stop-1", "expires_at": far}]
    acts, flags, table = FM.plan_maintenance("hackX", pos, orders, {"AAA": 0.02}, c, day, date.today())
    assert len(acts) == 1
    a = acts[0]
    assert a.kind == "stop_new" and a.qty == 60 and a.order_type == "stop" and a.tif == "gtc"
    assert a.stop_price == pytest.approx(47.0)            # 50 x (1 - 3 x 0.02)
    assert table[0]["resting"][0]["distance_sigma"] == pytest.approx(5.0)
    # a full cover needs nothing
    orders[0]["qty"] = "100"
    acts2, _, _ = FM.plan_maintenance("hackX", pos, orders, {"AAA": 0.02}, c, day, date.today())
    assert acts2 == []


def test_an_expiring_stop_is_renewed_never_loosened(tmp_path):
    c = _contract(tmp_path)
    soon = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    pos = [{"symbol": "AAA", "qty": "100", "current_price": "50", "asset_class": "us_equity"}]
    orders = [{"id": "o1", "symbol": "AAA", "side": "sell", "type": "stop", "qty": "100",
               "stop_price": "48.5", "client_order_id": "aat-stop-1", "expires_at": soon}]
    acts, _, _ = FM.plan_maintenance("hackX", pos, orders, {"AAA": 0.02}, c, date.today().isoformat(), date.today())
    kinds = [a.kind for a in acts]
    assert kinds == ["cancel", "stop_renew"]
    assert acts[1].stop_price == pytest.approx(48.5)      # the sigma stop (47.0) would loosen it


def test_short_options_and_shares_are_flagged_not_traded(tmp_path):
    c = _contract(tmp_path)
    exp = (date.today() + timedelta(days=3)).strftime("%y%m%d")
    pos = [{"symbol": f"BE{exp}C00320000", "qty": "-7", "current_price": "3", "asset_class": "us_option"},
           {"symbol": "ZZZ", "qty": "-10", "current_price": "5", "asset_class": "us_equity"}]
    acts, flags, _ = FM.plan_maintenance("hackX", pos, [], {}, c, date.today().isoformat(), date.today())
    assert acts == []
    joined = " ".join(flags)
    assert "NAKED_SHORT_OPTIONS" in joined and "OPTION_DTE" in joined and "SHORT_SHARES" in joined


# ─────────────────────────────── contracts ──────────────────────────────────

def test_a_frozen_contract_cannot_be_edited(tmp_path):
    c = _contract(tmp_path)
    again = _contract(tmp_path)                          # same body: same hash, no refusal
    assert again["policy_hash"] == c["policy_hash"]
    with pytest.raises(FM.FleetRefusal):
        _contract(tmp_path, alpha_source="a different rule")
    p = FM.contract_file("hackX", "v1", tmp_path)
    d = json.loads(p.read_text(encoding="utf-8"))
    d["caps"]["max_name_frac"] = 0.5
    p.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(FM.FleetRefusal):
        FM.load_contract("hackX", "v1", tmp_path)


# ─────────────────────────────── targets / plan ─────────────────────────────

def test_book_targets_drop_share_classes_defects_and_clip():
    pos = [{"ticker": "GOOG", "weight": 0.094}, {"ticker": "GOOGL", "weight": 0.093},
           {"ticker": "JAZZ", "weight": 0.115}, {"ticker": "BAD", "weight": 0.05},
           {"ticker": "CASH", "weight": 0.1}]
    t, drops = FM.book_targets(pos, max_name=0.10, excluded={"BAD": "bar-defect screen"},
                               issuer_of={"GOOG": "alphabet", "GOOGL": "alphabet"})
    assert set(t) == {"GOOG", "JAZZ"}
    assert t["JAZZ"] == pytest.approx(0.10)
    whys = " ".join(d["why"] for d in drops)
    assert "share class" in whys and "bar-defect" in whys and "clipped" in whys


def test_rebalance_keeps_legacy_and_fills_only_remaining_capacity(tmp_path):
    c = _contract(tmp_path)
    acts = FM.plan_rebalance("hackX", {"AAA": 0.10, "BBB": 0.10}, equity=100_000,
                             held={"OLD": 900.0}, prices={"OLD": 100.0, "AAA": 50.0, "BBB": 25.0},
                             legacy={"OLD"}, pending={}, contract=c, day=date.today().isoformat())
    assert all(a.symbol != "OLD" for a in acts)          # legacy is never sold by the rebalance
    buys = {a.symbol: a for a in acts if a.side == "buy"}
    # legacy gross 90k of a 100k cap leaves 10k for 20k of targets: scale 0.5
    assert buys["AAA"].qty == 100 and buys["BBB"].qty == 200


def test_news_targets_are_long_only_capped_and_skip_the_already_moved():
    sig = {"UPA": {"d": 0.5, "n": 2}, "UPB": {"d": 0.3, "n": 1}, "DOWN": {"d": -0.6, "n": 3},
           "MOVED": {"d": 0.9, "n": 1}}
    t, drops = FM.news_targets(sig, unit=0.01, max_names=1, already_moved={"MOVED": 3.1}, max_moved=2.0)
    assert t == {"UPA": 0.01}
    assert "DOWN" not in t
    assert any("already moved" in d["why"] for d in drops)


# ─────────────────────────────── worst case, twins, grade ───────────────────

def test_worst_case_in_dollars_counts_unprotected_positions_whole():
    pos = [{"symbol": "AAA", "qty": "100", "current_price": "50", "asset_class": "us_equity"},
           {"symbol": "BBB", "qty": "10", "current_price": "20", "asset_class": "us_equity"}]
    orders = [{"symbol": "AAA", "side": "sell", "type": "stop", "qty": "100", "stop_price": "45"}]
    w = FM.worst_case(pos, orders, [], 10_000, {})
    assert w["worst_usd"] == pytest.approx(500 + 200)    # (50-45) x 100 + the whole unprotected BBB
    assert w["gross_over_equity"] == pytest.approx(0.52)
    f = FM.formula_worst_case(10, 0.10, 0.12, 100_000)
    assert f["worst_usd"] == pytest.approx(12_000) and f["gross_over_equity"] == pytest.approx(1.0)


def test_twin_is_seeded_and_sigma_matched():
    pool = {f"P{i}": 0.01 + 0.001 * i for i in range(100)}
    held = {"H1": 0.05, "H2": 0.07}
    sig = {"H1": 0.012, "H2": 0.10}
    a = FM.matched_random_twin(held, sig, pool, seed=7)
    assert a == FM.matched_random_twin(held, sig, pool, seed=7)
    assert sorted(a.values()) == [0.05, 0.07]
    assert not set(a) & set(held)


def test_grade_row_differences():
    g = FM.grade_row("hackX", date.today().isoformat(), account_ret=0.01, spy_ret=0.004, twin_ret=None,
                     twin_priced_share=0.0, contract={"version": "v1", "policy_hash": "h"})
    assert g["vs_spy"] == pytest.approx(0.006) and g["vs_twin"] is None


def test_lot_entry_walks_back_to_the_fill_that_opened_the_lot():
    today = date.today()
    d = lambda k: (today - timedelta(days=k)).isoformat() + "T14:00:00Z"   # noqa: E731
    fills = [{"side": "buy", "qty": "50", "transaction_time": d(1)},
             {"side": "sell", "qty": "30", "transaction_time": d(5)},
             {"side": "buy", "qty": "80", "transaction_time": d(10)}]
    e, how = FM.lot_entry_date(100, fills)
    assert e == today - timedelta(days=10) and how == "exact"


def test_sessions_between_counts_weekdays_only():
    start = date.today()
    while start.weekday() != 0:           # a Monday, derived
        start -= timedelta(days=1)
    assert FM.sessions_between(start, start + timedelta(days=7)) == 5
