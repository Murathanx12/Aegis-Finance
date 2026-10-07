"""C27: top-ups made lawful under the broker's wash-trade rule, no frozen term weakened.

Alpaca (docs.alpaca.markets/us/docs/user-protection, fetched 2026-10-07):
"| stop sell | limit buy | always rejected |" and "| limit buy | stop sell | always
rejected |" -- so a top-up of a name with a resting sell stop is sent as
cancel stop -> buy -> wait terminal -> ONE combined stop, with a rollback.

Pinned here:
* the conflict classifier follows the broker's table (stop / stop_limit / limit /
  trailing_stop / complex-order exemption);
* the atomic sequence on a fake broker that ENFORCES the table: the happy path,
  buy rejected -> original stop re-placed, new stop rejected -> protective stop +
  REFUSED, everything rejected -> UNPROTECTED named, a cancel that will not
  confirm -> no buy, a buy that stays open -> remainder cancelled first, a stop
  renewed earlier in the run is released too;
* `stop_never_loosened` on the combined stop;
* the REAL 2026-10-06 open plans: on the rule-enforcing fake the old path is
  rejected exactly where the broker rejected it (15 of 19), and the C27 path
  reaches the broker with every one, hack2's three Technology top-ups included,
  in SHADOW -- the sequence is not a gate and is not shadowed;
* the run receipt, the EOD audit and the health reader count rejections by
  reason and read > 20% rejected buys as DEGRADED.
Offline; no network, no clock-dependent dates.
"""
from __future__ import annotations

import itertools
import json
import random
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import pytest

from backend import config as _cfg
from backend.services import fleet_eod_audit as EOD
from backend.services import fleet_manager as FM

FX = Path(__file__).parent / "fixtures"
C26_FIXTURE = FX / "c26" / "replay_2026-10-06.json"
C27_FIXTURE = FX / "c27" / "resting_2026-10-06_open.json"


# ─────────────────────────────── a broker that enforces the table ───────────

class RuleBroker:
    """A paper venue that applies Alpaca's wash-trade table to simple orders,
    refuses a sell beyond the free long quantity, and fills marketable buys.

    knobs: buy_fill = "fill" | "open" | "partial"; reject_buys / reject_stops = how
    many of the next such submissions to reject (403); cancel_mode = "ok" | "stuck"."""

    def __init__(self, positions: dict[str, float], resting: list[dict], *, buy_fill: str = "fill",
                 reject_buys: int = 0, reject_stops: int = 0, cancel_mode: str = "ok"):
        self.pos = {k: float(v) for k, v in positions.items()}
        self.orders: dict[str, dict] = {}
        self.ids = itertools.count(1)
        self.buy_fill, self.reject_buys, self.reject_stops, self.cancel_mode = (
            buy_fill, reject_buys, reject_stops, cancel_mode)
        self.log: list[tuple] = []
        for o in resting:
            o = dict(o, status="new", side="sell", type=o.get("type", "stop"), filled_qty="0")
            o.setdefault("client_order_id", f"seed-{o['id']}")
            self.orders[o["id"]] = o

    def open_for(self, sym: str) -> list[dict]:
        return [o for o in self.orders.values() if o["symbol"] == sym
                and o["status"] in ("new", "accepted", "partially_filled", "pending_new")]

    def wash(self, b: dict) -> Optional[str]:
        for o in self.open_for(b["symbol"]):
            if o["side"] == b["side"]:
                continue
            ex, new = (o["type"], o["side"]), (b["type"], b["side"])
            if ex == ("stop", "sell") and new == ("limit", "buy"):
                return o["id"]
            if ex == ("limit", "buy") and new == ("stop", "sell"):
                return o["id"]
        return None

    def __call__(self, method, url, headers, body):
        import urllib.parse as up
        path = url.split("?")[0].replace(FM.TRADING_HOST, "")
        q = dict(up.parse_qsl(url.split("?")[1])) if "?" in url else {}
        if method == "GET" and path == "/v2/positions":
            return 200, json.dumps([{"symbol": s, "qty": str(v), "current_price": "100", "asset_class": "us_equity"}
                                    for s, v in self.pos.items() if v]).encode()
        if method == "GET" and path == "/v2/orders" and q.get("status") == "open":
            return 200, json.dumps([o for o in self.orders.values()
                                    if o["status"] in ("new", "accepted", "partially_filled")]).encode()
        if method == "GET" and path == "/v2/orders:by_client_order_id":
            for o in self.orders.values():
                if o.get("client_order_id") == q.get("client_order_id"):
                    return 200, json.dumps(o).encode()
            return 404, b'{"message":"not found"}'
        if method == "GET" and path.startswith("/v2/orders/"):
            o = self.orders.get(path.rsplit("/", 1)[1])
            return (200, json.dumps(o).encode()) if o else (404, b"{}")
        if method == "DELETE" and path.startswith("/v2/orders/"):
            oid = path.rsplit("/", 1)[1]
            o = self.orders.get(oid)
            self.log.append(("cancel", oid))
            if not o:
                return 404, b"{}"
            if self.cancel_mode == "stuck":
                o["status"] = "pending_cancel"
                return 204, b""
            if o["status"] in ("new", "accepted", "partially_filled"):
                o["status"] = "canceled"
            return 204, b""
        if method == "POST" and path == "/v2/orders":
            b = json.loads(body)
            self.log.append(("submit", b["side"], b["type"], b["symbol"], int(b["qty"]), b.get("stop_price")))
            hit = self.wash(b)
            if hit:
                return 403, json.dumps({"code": 40310000, "existing_order_id": hit,
                                        "message": "potential wash trade detected. use complex orders"}).encode()
            if b["side"] == "buy" and self.reject_buys:
                self.reject_buys -= 1
                return 403, b'{"message": "insufficient buying power"}'
            if b["type"] == "stop" and self.reject_stops:
                self.reject_stops -= 1
                return 422, b'{"message": "stop price invalid"}'
            if b["side"] == "sell":
                reserved = sum(float(o["qty"]) for o in self.open_for(b["symbol"]) if o["side"] == "sell")
                if reserved + float(b["qty"]) > self.pos.get(b["symbol"], 0.0) + 1e-9:
                    return 403, b'{"message": "insufficient qty available for order"}'
            oid = f"o{next(self.ids)}"
            o = dict(b, id=oid, status="new", filled_qty="0")
            if b["side"] == "buy":
                n = int(b["qty"])
                f = n if self.buy_fill == "fill" else (n // 2 if self.buy_fill == "partial" else 0)
                o["filled_qty"] = str(f)
                o["status"] = "filled" if f == n else ("partially_filled" if f else "new")
                self.pos[b["symbol"]] = self.pos.get(b["symbol"], 0.0) + f
            self.orders[oid] = o
            return 200, json.dumps(o).encode()
        return 200, b"{}"

    def stops(self, sym: str) -> list[dict]:
        return [o for o in self.open_for(sym) if o["type"] == "stop" and o["side"] == "sell"]


def _topup(broker: RuleBroker, *, sym="AAA", held=10, add=5, limit=101.0, px=100.0, frac=0.05, day="2026-10-06"):
    v = FM.Venue("k", "s", transport=broker)
    oo = v.open_orders()
    a = FM.Action("hackT", "buy", sym, add, "buy", "limit", "day", limit_price=limit, price_ref=px,
                  coid=FM.client_order_id("hackT", day, "buy", sym, "h0"))
    cancels, stop, why = FM.plan_topup_sequence(a, oo, held_qty=held, stop_frac=frac, stop_how="test",
                                                contract_hash="h0", day=day)
    return v, a, cancels, stop, why


def _run_seq(v, a, cancels, stop, **kw):
    kw.setdefault("wait_buy_s", 0.05)
    kw.setdefault("wait_cancel_s", 0.05)
    return FM.execute_topup_sequence(v, a, cancels, stop, sleep=lambda s: None, **kw)


# ─────────────────────────────── the broker's table ─────────────────────────

def test_the_conflict_classifier_follows_the_brokers_table():
    oo = [{"id": "1", "symbol": "A", "side": "sell", "type": "stop", "stop_price": "90"},
          {"id": "2", "symbol": "A", "side": "sell", "type": "trailing_stop"},                # exempt
          {"id": "3", "symbol": "A", "side": "sell", "type": "stop", "order_class": "oco"},     # complex: exempt
          {"id": "4", "symbol": "A", "side": "sell", "type": "stop_limit", "limit_price": "105"},  # 101 < 105
          {"id": "5", "symbol": "A", "side": "sell", "type": "stop_limit", "limit_price": "99"},   # 101 >= 99
          {"id": "6", "symbol": "A", "side": "sell", "type": "limit", "limit_price": "100"},       # exit in flight
          {"id": "7", "symbol": "A", "side": "buy", "type": "limit", "limit_price": "100"},        # same side
          {"id": "8", "symbol": "B", "side": "sell", "type": "stop", "stop_price": "90"}]         # other name
    got = {o["id"]: k for o, k in FM.wash_conflicts("A", 101.0, oo)}
    assert got == {"1": "stop", "5": "stop", "6": "blocking"}
    assert "stop sell | limit buy | always rejected" in FM.WASH_RULE_QUOTE
    assert "limit buy | stop sell | always rejected" in FM.WASH_RULE_QUOTE


def test_a_new_name_is_untouched_and_an_exit_in_flight_refuses_by_name():
    a = FM.Action("hackT", "buy", "NEW", 5, "buy", "limit", limit_price=10.0, price_ref=10.0, coid="c")
    assert FM.plan_topup_sequence(a, [], held_qty=0, stop_frac=0.05, stop_how="", contract_hash="h",
                                  day="2026-10-06") == ([], None, None)
    a2 = FM.Action("hackT", "buy", "A", 5, "buy", "limit", limit_price=101.0, price_ref=100.0, coid="c2")
    _, stop, why = FM.plan_topup_sequence(
        a2, [{"id": "6", "symbol": "A", "side": "sell", "type": "limit", "limit_price": "100"}],
        held_qty=10, stop_frac=0.05, stop_how="", contract_hash="h", day="2026-10-06")
    assert stop is None and why.startswith(FM.REFUSED_WASH_TRADE_RULE)


def test_the_bare_top_up_is_what_the_broker_rejects():
    b = RuleBroker({"AAA": 10}, [{"id": "s1", "symbol": "AAA", "stop_price": 90.0, "qty": 10}])
    v = FM.Venue("k", "s", transport=b)
    a = FM.Action("hackT", "buy", "AAA", 5, "buy", "limit", limit_price=101.0, coid="bare")
    so = FM.submit_once(v, a)
    assert "REJECTED http 403" in so["outcome"] and FM.classify_rejection(so["outcome"]) == FM.REJ_WASH


# ─────────────────────────────── the atomic sequence ────────────────────────

def test_the_sequence_cancels_buys_then_places_one_combined_stop():
    b = RuleBroker({"AAA": 10}, [{"id": "s1", "symbol": "AAA", "stop_price": 90.0, "qty": 10}])
    v, a, cancels, stop, why = _topup(b)
    assert why is None and [c.cancel_order_id for c in cancels] == ["s1"]
    assert stop.qty == 15 and stop.stop_price == max(90.0, FM.stop_price_for(100.0, 0.05))
    r = _run_seq(v, a, cancels, stop)
    assert r["status"] == "OK" and r["refused"] is None
    assert [e["e"] for e in r["events"]][:5] == ["cancel_sent", "cancel_terminal", "buy_sent", "buy_terminal",
                                                 "combined_stop_sent"]
    st = b.stops("AAA")
    assert len(st) == 1 and int(st[0]["qty"]) == 15 and float(st[0]["stop_price"]) == stop.stop_price
    assert b.pos["AAA"] == 15
    assert r["stopless_window_s"] is not None and 0 <= r["stopless_window_s"] < 5
    assert all(e["t"].endswith("Z") for e in r["events"])            # every step timestamped (UTC, ms)
    assert not [x for x in b.log if x[0] == "submit" and "403" in str(x)]


def test_buy_rejected_re_places_the_original_stop():
    b = RuleBroker({"AAA": 10}, [{"id": "s1", "symbol": "AAA", "stop_price": 90.0, "qty": 10}], reject_buys=1)
    v, a, cancels, stop, _ = _topup(b)
    r = _run_seq(v, a, cancels, stop)
    assert r["status"] == "BUY_REJECTED_ROLLED_BACK" and r["unprotected_qty"] == 0
    st = b.stops("AAA")
    assert len(st) == 1 and int(st[0]["qty"]) == 10 and float(st[0]["stop_price"]) == 90.0   # the ORIGINAL
    assert b.pos["AAA"] == 10 and r["stopless_window_s"] is not None


def test_new_stop_rejected_places_a_protective_stop_and_raises_refused():
    b = RuleBroker({"AAA": 10}, [{"id": "s1", "symbol": "AAA", "stop_price": 90.0, "qty": 10}], reject_stops=1)
    v, a, cancels, stop, _ = _topup(b)
    r = _run_seq(v, a, cancels, stop)
    assert r["status"] == "REFUSED" and r["refused"].startswith("REFUSED: the combined stop was rejected")
    st = b.stops("AAA")
    assert len(st) == 1 and int(st[0]["qty"]) == 15 and float(st[0]["stop_price"]) == stop.stop_price
    assert st[0]["client_order_id"].endswith("-p")


def test_every_stop_rejected_is_named_unprotected():
    b = RuleBroker({"AAA": 10}, [{"id": "s1", "symbol": "AAA", "stop_price": 90.0, "qty": 10}], reject_stops=99)
    v, a, cancels, stop, _ = _topup(b)
    r = _run_seq(v, a, cancels, stop)
    assert r["status"] == "UNPROTECTED" and r["unprotected_qty"] == 15 and "UNPROTECTED" in r["refused"]
    assert FM.wash_sequence_summary([r])["unprotected_qty"] == 15


def test_a_cancel_that_will_not_confirm_sends_no_buy():
    b = RuleBroker({"AAA": 10}, [{"id": "s1", "symbol": "AAA", "stop_price": 90.0, "qty": 10}], cancel_mode="stuck")
    v, a, cancels, stop, _ = _topup(b)
    r = _run_seq(v, a, cancels, stop)
    assert r["status"] == FM.REFUSED_WASH_TRADE_RULE and r["refused"].startswith(FM.REFUSED_WASH_TRADE_RULE)
    assert not [x for x in b.log if x[0] == "submit" and x[1] == "buy"]
    assert r["outcomes"][a.coid].startswith(FM.REFUSED_WASH_TRADE_RULE)


def test_a_buy_left_open_is_cancelled_before_the_stop_and_the_stop_covers_what_filled():
    b = RuleBroker({"AAA": 10}, [{"id": "s1", "symbol": "AAA", "stop_price": 90.0, "qty": 10}], buy_fill="partial",
                   reject_stops=0)
    v, a, cancels, stop, _ = _topup(b, add=6)
    r = _run_seq(v, a, cancels, stop)
    assert r["status"] == "OK" and r["buy_filled_qty"] == 3 and r["combined_qty"] == 13
    assert any(e["e"] == "buy_remainder_cancel" for e in r["events"])
    st = b.stops("AAA")
    assert len(st) == 1 and int(st[0]["qty"]) == 13


def test_a_stop_renewed_earlier_in_the_run_is_released_too_and_never_loosened():
    b = RuleBroker({"AAA": 10}, [{"id": "s1", "symbol": "AAA", "stop_price": 90.0, "qty": 10}])
    v, a, cancels, stop, _ = _topup(b)
    # maintenance renewed the stop in this run (new id, HIGHER price) after the plan was made
    b.orders["s1"]["status"] = "canceled"
    b.orders["s9"] = {"id": "s9", "symbol": "AAA", "side": "sell", "type": "stop", "stop_price": 96.5,
                      "qty": "10", "status": "new", "client_order_id": "renewed", "filled_qty": "0"}
    r = _run_seq(v, a, cancels, stop)
    assert r["status"] == "OK"
    st = b.stops("AAA")
    assert len(st) == 1 and int(st[0]["qty"]) == 15 and float(st[0]["stop_price"]) == 96.5


# ─────────────────────────────── never looser ───────────────────────────────

def test_the_combined_stop_is_never_looser_than_any_stop_it_replaces():
    rng = random.Random(27)
    for _ in range(300):
        px = rng.uniform(5, 800)
        olds = [round(px * (1 - rng.uniform(0.01, 0.3)), 2) for _ in range(rng.randint(1, 3))]
        oo = [{"id": f"s{i}", "symbol": "A", "side": "sell", "type": "stop", "stop_price": str(p), "qty": "5"}
              for i, p in enumerate(olds)]
        a = FM.Action("hackT", "buy", "A", rng.randint(1, 50), "buy", "limit", limit_price=px * 1.001,
                      price_ref=px, coid=f"c{_}")
        _, stop, why = FM.plan_topup_sequence(a, oo, held_qty=5 * len(olds), stop_frac=rng.uniform(0.02, 0.2),
                                              stop_how="", contract_hash="h", day="2026-10-06")
        assert why is None and stop.stop_price >= max(olds) and stop.stop_price < px
        assert stop.inputs["replaces_stop"] == max(olds)


def test_stop_never_loosened_applies_to_the_combined_stop():
    ctx = FM.GateCtx(equity=1e5, cash=1e5, held={"A": 15}, mv={}, gross=0.0,
                     contract={"caps": FM.caps_block(), "policy_hash": "h"}, today=date(2026, 10, 6))
    stop = FM.Action("hackT", "stop_combined", "A", 15, "sell", "stop", "gtc", stop_price=80.0, price_ref=100.0,
                     protective=True, coid="cmb", inputs={"replaces_stop": 90.0})
    tr = FM.run_gates(stop, ctx, mode="LIVE")
    assert stop.refused is None and stop.stop_price == 90.0 and stop.qty == 15
    row = next(r for r in tr if r["gate"] == "stop_never_loosened")
    assert row["verdict"] == FM.GATE_SHRINK and row["qty_out"] == 15


def test_the_policy_version_names_the_sequence_and_it_is_not_a_gate():
    gc = FM.gates_config()
    assert gc["gate_policy_version"] == "c27-wash-trade-sequence" == FM.GATE_POLICY_VERSION
    assert "NOT a gate and NOT shadowed" in gc["gate_policy_choices"]["wash_trade_sequence"]
    assert "wash_trade_sequence" not in [g[0] for g in FM.GATES]
    assert "wash_trade_sequence" not in FM.NEW_GATES


def test_topup_worst_case_tightened_held_stop_lowers_the_worst_case():
    w = FM.topup_worst_case(held=10, px=100.0, resting=[{"stop_price": 90.0, "qty": 10}], add_qty=5, add_px=100.1,
                            combined_sp=95.0, planned_frac=0.05)
    assert w["now"] == 100.0 and w["sequence"] == pytest.approx(50 + 25.5)
    assert w["sequence"] <= w["old_plan"] and w["delta_vs_now"] < 0       # the held stop was tightened


# ─────────────────────────────── the real 10-06 plans ───────────────────────

def _plans_10_06(new_gates_mode: str):
    """The 10-06 OPEN plans through the gates (as the C26 replay test does), then the
    C27 planner over the resting stops of that pass. Yields (role, buy Action, seq)."""
    fx = json.loads(C26_FIXTURE.read_text(encoding="utf-8"))
    rs = json.loads(C27_FIXTURE.read_text(encoding="utf-8"))["accounts"]
    p = next(x for x in fx["passes"] if x["pass"] == "open")
    for acc in p["accounts"]:
        if acc["role"] not in rs:
            continue
        r = rs[acc["role"]]
        held = {q["symbol"]: float(q["qty"]) for q in acc["positions"]}
        mv = {q["symbol"]: abs(float(q["market_value"])) for q in acc["positions"]}
        ck = acc["clock"]
        ctx = FM.GateCtx(equity=acc["equity"], cash=acc["cash"], held=held, mv=mv, gross=sum(mv.values()),
                         contract={"caps": acc["caps"], "policy_hash": acc["policy_hash"]},
                         today=date.fromisoformat(ck["session_day_et"]), market_ok=True,
                         turnover_left=acc["caps"]["daily_turnover_frac"] * acc["equity"],
                         stopped_out={}, sector_of=fx["sector_of"])
        oo = [o for lst in r["resting"].values() for o in lst]
        for x in acc["actions"]:
            if x["kind"] != "buy" or x["mode"] != "LIVE":
                continue
            a = FM.Action(acc["role"], "buy", x["symbol"], int(x["qty"]), "buy", "limit", "day",
                          limit_price=x["limit"], price_ref=float(r["price"].get(x["symbol"]) or x["limit"]),
                          coid=f"replay-{acc['role']}-{x['symbol']}")
            FM.run_gates(a, ctx, mode="LIVE", new_gates_mode=new_gates_mode)
            seq = FM.plan_topup_sequence(a, oo, held_qty=held.get(x["symbol"], 0.0),
                                         stop_frac=float(r["stop_frac"].get(x["symbol"]) or 0.05),
                                         stop_how="replay", contract_hash=acc["policy_hash"], day="2026-10-06")
            yield acc["role"], a, seq, r


def test_the_10_06_open_plans_on_the_rule_broker_old_path_vs_c27():
    old_rej, new_rej, reached, seqd = [], [], [], []
    for role, a, (cancels, stop, why), r in _plans_10_06("shadow"):
        assert a.refused is None and why is None                       # shadow: nothing refused tonight
        sym = a.symbol
        rest = r["resting"].get(sym) or []
        held = {sym: sum(float(o["qty"]) for o in rest) or 0.0}
        # the OLD path: the bare buy on a broker holding the resting stops
        b_old = RuleBroker(held, [dict(o) for o in rest])
        so = FM.submit_once(FM.Venue("k", "s", transport=b_old),
                            FM.Action(role, "buy", sym, a.qty, "buy", "limit", limit_price=a.limit_price, coid="old"))
        if FM.classify_rejection(so["outcome"]):
            old_rej.append((role, sym))
        # the C27 path
        b_new = RuleBroker(held, [dict(o) for o in rest])
        v = FM.Venue("k", "s", transport=b_new)
        if stop is None:
            so2 = FM.submit_once(v, a)
            ok = bool(so2.get("order_id"))
        else:
            seqd.append((role, sym))
            res = _run_seq(v, a, cancels, stop)
            ok = res["status"] == "OK"
            st = b_new.stops(sym)
            assert len(st) == 1 and int(float(st[0]["qty"])) == int(held[sym]) + a.qty
            assert float(st[0]["stop_price"]) >= max(o["stop_price"] for o in rest)
        (reached if ok else new_rej).append((role, sym))
    observed = [(role, s) for role, d in json.loads(C27_FIXTURE.read_text(encoding="utf-8"))["accounts"].items()
                for s, ans in d["broker_answer"].items() if ans == "403_wash"]
    # the rule broker reproduces the REAL broker's answers exactly: 15 of 19 rejected
    assert sorted(old_rej) == sorted(observed) and len(old_rej) == 15
    assert len(reached) + len(new_rej) == 19
    # C27: every one of the 19 reaches the broker; the 15 top-ups through the sequence
    assert new_rej == [] and sorted(seqd) == sorted(observed)
    assert {("hack2", "MDB"), ("hack2", "NET"), ("hack2", "SNOW")} <= set(seqd)


def test_in_enforce_the_sector_gate_still_refuses_hack2_tech_before_any_sequence():
    refused = {(role, a.symbol) for role, a, seq, _ in _plans_10_06("enforce") if a.refused}
    assert refused == {("hack2", "MDB"), ("hack2", "NET"), ("hack2", "SNOW")}
    for role, a, (cancels, stop, why), _ in _plans_10_06("enforce"):
        if a.refused:
            assert stop is None and cancels == []          # a refused buy never opens a stop-less window


# ─────────────────────────────── run_role, DRY ──────────────────────────────

def test_run_role_plans_a_top_up_as_cancel_buy_combined_stop(tmp_path, monkeypatch, capsys):
    from backend.tests.test_fleet_gates_c26_review import _run
    from scripts import fleet_manager_run as RUN
    res, _ = _run(tmp_path, monkeypatch, positions=[{"ticker": "AAA", "weight": 0.08},
                                                    {"ticker": "DDD", "weight": 0.05}])
    acts = res["actions"]
    i_c = next(i for i, a in enumerate(acts) if a["kind"] == "cancel" and a["symbol"] == "AAA")
    i_b = next(i for i, a in enumerate(acts) if a["kind"] == "buy" and a["symbol"] == "AAA")
    i_s = next(i for i, a in enumerate(acts) if a["kind"] == "stop_combined" and a["symbol"] == "AAA")
    assert i_c < i_b < i_s
    buy, cmb = acts[i_b], acts[i_s]
    assert buy["refused"] is None and cmb["refused"] is None
    assert cmb["qty"] == 100 + buy["qty"] and cmb["stop"] >= 45.0
    assert cmb["gates"] and any(g["gate"] == "stop_never_loosened" for g in cmb["gates"])
    assert res["wash_sequences"]["planned"] and res["c27_worst_case"]["per_topup"]
    wc = res["c27_worst_case"]
    assert wc["worst_after_sequences_usd"] <= wc["worst_now_usd"] + wc["old_plan_topups_usd"] + 1e-6
    assert "rejections" in res and res["rejections"]["n_live_buys_sent"] == 0      # DRY: nothing sent
    RUN.print_role(res)
    assert "C27 rejections:" in capsys.readouterr().out


def test_a_top_up_above_the_contract_line_is_refused_by_name(tmp_path, monkeypatch):
    from backend.tests.test_fleet_gates_c26_review import _run
    monkeypatch.setattr(FM, "topup_worst_case", lambda **k: {"now": 0.0, "old_plan": 1e9, "sequence": 1e9,
                                                             "delta_vs_now": 1e9, "delta_vs_old_plan": 0.0})
    res, _ = _run(tmp_path, monkeypatch, positions=[{"ticker": "AAA", "weight": 0.08}])
    buy = next(a for a in res["actions"] if a["kind"] == "buy" and a["symbol"] == "AAA")
    assert buy["refused"].startswith(FM.REFUSED_WORST_CASE_LINE)
    assert any(g["gate"] == "worst_case_line" for g in buy["gates"])
    assert res["c27_worst_case"]["per_topup"][0]["verdict"] == FM.REFUSED_WORST_CASE_LINE
    assert FM.rejection_summary(res["actions"])["refused_before_broker"] == 1


# ─────────────────────────────── counting, audit, health ────────────────────

def _real_10_06_open_actions() -> list[dict]:
    """The 19 LIVE buys of the real 10-06 open pass with the broker's answer, as actions."""
    d = json.loads(C27_FIXTURE.read_text(encoding="utf-8"))["accounts"]
    out = []
    for role, acc in d.items():
        for s, ans in acc["broker_answer"].items():
            oc = ("REJECTED http 403: {'code': 40310000, 'message': 'potential wash trade detected. use complex "
                  "orders'}" if ans == "403_wash" else "submitted pending_new id x")
            out.append({"role": role, "kind": "buy", "side": "buy", "symbol": s, "mode": "LIVE", "outcome": oc})
    return out


def test_rejections_are_counted_by_reason_and_today_reads_degraded():
    acts = _real_10_06_open_actions() + [
        {"kind": "buy", "side": "buy", "mode": "LIVE", "outcome": "REJECTED http 422: {'message': 'x'}"},
        {"kind": "buy", "side": "buy", "mode": "LIVE", "outcome": "submitted new id y", "entry_status": "rejected"},
        {"kind": "buy", "side": "buy", "mode": "REFUSED", "refused": f"{FM.REFUSED_WASH_TRADE_RULE}: x"}]
    s = FM.rejection_summary(acts)
    assert s["n_live_buys_sent"] == 21 and s["by_reason"] == {"wash_trade_403": 15, "http_422": 1, "other": 1}
    assert s["refused_before_broker"] == 1 and s["degraded"] and "DEGRADED" in s["line"]
    assert not FM.rejection_summary([a for a in acts if "REJECTED" not in str(a.get("outcome"))
                                     and a.get("entry_status") != "rejected"])["degraded"]


def test_the_health_reader_turns_a_day_of_rejected_buys_degraded(tmp_path):
    from backend.services import task_receipts as TR
    acts = _real_10_06_open_actions()
    accs = [{"role": r, "status": "ok", "equity": 1.0, "actions": [a for a in acts if a["role"] == r]}
            for r in sorted({a["role"] for a in acts})]
    runs = tmp_path / "optimus" / "paper_accounts" / "fleet_manager" / "runs"
    runs.mkdir(parents=True)
    (runs / "run_20991231T000000Z-aaaaaa.json").write_text(json.dumps(
        {"run_id": "x", "pass": "open", "started_utc": "2099-12-31T00:00:00Z", "finished_utc": "2099-12-31T00:01:00Z",
         "accounts": accs}), encoding="utf-8")
    r = TR._fleet_pass("open")(SimpleNamespace(optimus_dir=tmp_path / "optimus"), None)
    assert r.status == "DEGRADED"
    assert "15 of 19" in r.reason and "15 wash-trade 403" in r.reason and "hack4 9/9" in r.reason
    st, why = TR._fleet_rejections_status({"accounts": [{"actions": [a for a in acts
                                                                     if "submitted" in a["outcome"]]}]})
    assert st == "OK" and why == ""


def test_the_eod_audit_counts_rejections_from_our_ledger_and_the_stopless_windows():
    day = "2026-10-06"
    ymd = day.replace("-", "")
    dec = []
    for i, (sym, oc) in enumerate([("AAA", "REJECTED http 403: {'message': 'potential wash trade detected'}"),
                                   ("BBB", "REJECTED http 403: {'message': 'potential wash trade detected'}"),
                                   ("CCC", "submitted pending_new id 1"),
                                   ("DDD", "REJECTED http 422: {'message': 'x'}")]):
        dec.append({"row": "outcome", "role": "hack4", "coid": f"aegisfm-hack4-{ymd}-buy-{sym}-abc", "outcome": oc})
    dec.append({"row": "outcome", "role": "hack4", "coid": f"aegisfm-hack4-{ymd}-buy-CCC-abc",
                "outcome": "ALREADY SUBMITTED (filled): idempotent skip"})                    # a re-run
    dec.append({"row": "outcome", "role": "hack4", "coid": f"aegisfm-hack4-{ymd}-stop-AAA-abc",
                "outcome": "REJECTED http 403: x"})                                           # not a buy
    dec.append({"row": "outcome", "role": "hack2", "coid": f"aegisfm-hack2-{ymd}-buy-ZZZ-abc",
                "outcome": "REJECTED http 403: wash trade"})                                  # other account
    dec.append({"row": "wash_sequence", "role": "hack4", "session": day, "status": "OK",
                "stopless_window_s": 2.4, "unprotected_qty": 0})
    s = EOD.rejections_today("hack4", day, dec, [])
    assert s["n_live_buys_sent"] == 4 and s["by_reason"] == {"wash_trade_403": 2, "http_422": 1, "other": 0}
    assert s["degraded"] and s["wash_sequences"]["stopless_events"] == 1
    assert s["wash_sequences"]["max_stopless_window_s"] == 2.4


def test_the_eod_audit_row_is_degraded_on_rejected_buys(tmp_path, monkeypatch):
    """audit_account end to end on a GET-only fake: the row carries `rejections` and the flag."""
    today = date(2026, 10, 6)

    class GetOnly:
        def __call__(self, method, url, headers, body):
            path = url.split("?")[0].replace(FM.TRADING_HOST, "")
            if path == "/v2/account":
                return 200, b'{"equity": "1000", "cash": "100", "last_equity": "1000"}'
            if path == "/v2/clock":
                return 200, json.dumps({"timestamp": f"{today}T15:00:00-04:00"}).encode()
            return 200, b"[]"
    v = FM.Venue("k", "s", transport=EOD.readonly_transport(GetOnly()))
    ymd = today.isoformat().replace("-", "")
    dec = [{"row": "outcome", "role": "hackT", "coid": f"aegisfm-hackT-{ymd}-buy-AAA-x",
            "outcome": "REJECTED http 403: potential wash trade detected"}]
    row = EOD.audit_account("hackT", v, state=None, grades=[], run_id="r", trigger="t", decisions=dec)
    assert row["rejections"]["n_rejected"] == 1 and any(f.startswith("REJECTED_BUYS") for f in row["flags"])
    assert row["status"] == "DEGRADED" and row["orders_today"]["rejected"] == 0


def test_the_threshold_lives_in_config():
    assert _cfg.FLEET_REJECTED_BUY_DEGRADED_FRAC == 0.20
    assert FM.rejection_summary([])["threshold"] == 0.20
    assert _cfg.FLEET_WASH_SEQ_MAX_WINDOW_S > _cfg.FLEET_WASH_SEQ_BUY_WAIT_S + _cfg.FLEET_WASH_SEQ_CANCEL_WAIT_S


# ─────────────────────────────── run_role, LIVE on the rule broker ──────────

class LiveRuleBroker(RuleBroker):
    """RuleBroker + the account / clock / data reads run_role makes. AAA 100 @ 50
    with resting stop s1 at 45 (a top-up target), BBB 250 @ 20 (no stop)."""

    def __init__(self, today: date, **kw):
        super().__init__({"AAA": 100.0, "BBB": 250.0},
                         [{"id": "s1", "symbol": "AAA", "stop_price": 45.0, "qty": 100,
                           "client_order_id": "aegisfm-t-stop", "expires_at": "2099-01-01T00:00:00Z"}], **kw)
        self.today = today

    def __call__(self, method, url, headers, body):
        path = url.split("?")[0].replace(FM.TRADING_HOST, "").replace(FM.DATA_HOST, "")
        px = {"AAA": 50.0, "BBB": 20.0, "DDD": 30.0}
        if method == "GET" and path == "/v2/account":
            return 200, b'{"equity": "100000", "cash": "90000", "last_equity": "100000"}'
        if method == "GET" and path == "/v2/clock":
            return 200, json.dumps({"timestamp": f"{self.today}T10:45:00-04:00", "is_open": True,
                                    "next_close": "2999-01-01T20:00:00Z"}).encode()
        if method == "GET" and path == "/v2/positions":
            return 200, json.dumps([{"symbol": s, "qty": str(q), "current_price": str(px[s]),
                                     "market_value": str(q * px[s]), "asset_class": "us_equity"}
                                    for s, q in self.pos.items() if q]).encode()
        if method == "GET" and path.startswith("/v2/account/activities"):
            return 200, b"[]"
        if method == "GET" and path == "/v2/orders" and "status=open" not in url:
            return 200, b"[]"
        if method == "GET" and path == "/v2/stocks/trades/latest":
            return 200, json.dumps({"trades": {s: {"p": p} for s, p in px.items()}}).encode()
        if method == "GET" and path == "/v2/stocks/quotes/latest":
            return 200, b'{"quotes": {}}'
        if method == "GET" and path.startswith("/v2/stocks/"):
            return 200, b'{"bars": {}}'
        return super().__call__(method, url, headers, body)


def test_run_role_live_sends_the_top_up_through_the_sequence_and_the_broker_accepts_it(tmp_path, monkeypatch):
    from scripts import fleet_manager_run as RUN
    monkeypatch.setattr(FM, "root", lambda base=None: tmp_path if base is None else base)
    monkeypatch.setattr(RUN, "panel_sigma_and_screen", lambda syms: ({s: 0.02 for s in syms}, {}, {}))
    monkeypatch.setattr(RUN, "stop_counterfactual_step", lambda *a, **k: {"skipped": "test"})
    monkeypatch.setattr(RUN, "grade_role", lambda *a, **k: {"skipped": "test"})
    monkeypatch.setattr(FM, "wait_terminal", lambda v, oid, timeout_s=12.0, sleep=None:
                        FM.Venue.order(v, oid).get("status", "unknown"))
    today = date.today()
    broker = LiveRuleBroker(today)
    monkeypatch.setattr(FM, "_urllib_transport", broker)
    caps = FM.caps_block()
    for v_, sel in (("v1", {"kind": "legacy_hold"}),
                    ("v2", {"kind": "frozen_book", "horizon_sessions": 21,
                            "positions": [{"ticker": "AAA", "weight": 0.08}, {"ticker": "BBB", "weight": 0.05},
                                          {"ticker": "DDD", "weight": 0.03}]})):
        FM.freeze_contract({"schema": "fleet_manager_contract/1", "role": "hackT", "version": v_,
                            "licence": FM.LICENCE, "alpha_source": "test", "selection": sel,
                            "stop_rule": FM.stop_rule_block(0.10), "caps": caps, "costs": FM.costs_block(),
                            "twin": {"weights": {}}}, base=tmp_path)
    (tmp_path / "state").mkdir(exist_ok=True)
    (tmp_path / "state" / "hackT.json").write_text(json.dumps(
        {"t": f"{today}T00:00:00+00:00", "positions": {"AAA": 100.0, "BBB": 250.0},
         "v2_names": ["AAA", "BBB"]}), encoding="utf-8")
    res = RUN.run_role("hackT", env={"AAT_HACKT_KEY_ID": "k", "AAT_HACKT_SECRET_KEY": "s"},
                       modes={"hackT": {"contract": "v2", "maintenance": "LIVE", "entries": "LIVE"}},
                       pass_="open", live_flag=True, run_id="t-live", books={}, issuer_of={}, stitched=set(),
                       digest=None, digest_name=None, baseline=(None, {}), pool={}, rebaseline=False,
                       sector_of={"AAA": "Tech", "BBB": "Tech", "DDD": "Tech"}, sector_age_days=3)
    assert res["status"] == "ok", res.get("why")
    buy = next(a for a in res["actions"] if a["kind"] == "buy" and a["symbol"] == "AAA")
    assert buy["mode"] == "LIVE" and "submitted" in buy["outcome"] and buy["wash_seq_status"] == "OK"
    assert broker.pos["AAA"] == 160                                         # 100 held + 60 top-up
    st = broker.stops("AAA")
    assert len(st) == 1 and int(st[0]["qty"]) == 160 and float(st[0]["stop_price"]) >= 45.0
    assert not [x for x in broker.log if x[0] == "submit" and FM.classify_rejection(str(x))]
    assert res["rejections"]["n_rejected"] == 0 and res["rejections"]["n_live_buys_sent"] >= 1
    rows = FM.read_jsonl(FM.decisions_path())
    i_first_seq = next(i for i, r in enumerate(rows) if r.get("row") == "wash_sequence")
    seq_coids = {a["coid"] for a in res["actions"] if a.get("wash_seq")}
    decided = {r["coid"] for r in rows[:i_first_seq] if r.get("row") == "decision"}
    assert seq_coids <= decided                       # every member decided before any order went out
    ws = rows[i_first_seq]
    assert ws["status"] == "OK" and ws["stopless_window_s"] is not None
    # a new name (DDD) is not a top-up: no sequence, sent as before, then entry protection
    ddd = next(a for a in res["actions"] if a["kind"] == "buy" and a["symbol"] == "DDD")
    assert not ddd.get("wash_seq") and "submitted" in ddd["outcome"]


def test_the_worst_case_line_on_the_real_10_06_plan_refuses_hack2s_top_ups_by_name():
    """hack2 sat $83 ABOVE its v2 contract line before any order on 10-06 ($12,427 vs
    $12,344): every top-up adds worst case even under the combined stop, so the line
    rule refuses all five by name. hack1 and hack4 pass (hack4's sequences LOWER its
    worst case: the combined stops re-base NVDA and AVPT upward)."""
    fx = json.loads(C27_FIXTURE.read_text(encoding="utf-8"))["accounts"]
    deltas: dict[str, list] = {}
    for role, a, (cancels, stop, why), r in _plans_10_06("shadow"):
        if stop is None:
            continue
        rest = r["resting"][a.symbol]
        w = FM.topup_worst_case(held=sum(o["qty"] for o in rest), px=r["price"][a.symbol], resting=rest,
                                add_qty=a.qty, add_px=a.limit_price, combined_sp=stop.stop_price,
                                planned_frac=r["stop_frac"][a.symbol])
        # never above what the old path would have added, except the limit's slippage over the
        # reference price (the old figure charged the stop fraction on the limit; the stop is set
        # from the reference)
        slip = a.qty * max(0.0, a.limit_price - r["price"][a.symbol])
        assert w["sequence"] <= w["old_plan"] + slip + 1e-6
        deltas.setdefault(role, []).append((a.symbol, w["delta_vs_now"]))
    v = {role: FM.topup_line_walk(fx[role]["worst_case_now_usd"], fx[role]["contract_line_usd"], d)
         for role, d in deltas.items()}
    assert fx["hack2"]["worst_case_now_usd"] > fx["hack2"]["contract_line_usd"]
    assert set(v["hack2"].values()) == {FM.REFUSED_WORST_CASE_LINE} and len(v["hack2"]) == 5
    assert set(v["hack1"].values()) == {"OK"} and set(v["hack4"].values()) == {"OK"} and len(v["hack4"]) == 9
    assert sum(d for _, d in deltas["hack4"]) < 0
