"""C26: the fleet manager's NAMED GATES (`fleet_manager.GATES` / `run_gates`).

Pinned here: the order (and that config and code agree), that no gate can ever
enlarge a proposed size, that an EXIT is blocked only by a LEASE gate, the
cooldown boundary (blocked at N-1, allowed at N), and that the sector cap
shrinks the order that breaches it -- and only that one. Offline; dates are
derived from `today`.
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta, timezone

import pytest

from backend import config as _cfg
from backend.services import fleet_manager as FM


def _contract(tmp_path, **caps_over):
    caps = FM.caps_block()
    caps.update(caps_over)
    body = {"schema": "fleet_manager_contract/1", "role": "hackG", "version": "v1", "licence": FM.LICENCE,
            "alpha_source": "test", "selection": {"kind": "legacy_hold"},
            "stop_rule": FM.stop_rule_block(0.10), "caps": caps, "costs": FM.costs_block(),
            "twin": {"weights": {}}}
    return FM.freeze_contract(body, base=tmp_path)


def _ctx(c, **kw):
    base = dict(equity=100_000.0, cash=100_000.0, held={}, mv={}, gross=0.0, contract=c,
                today=date.today(), cooldown_sessions=5, sector_max_frac=0.40)
    base.update(kw)
    return FM.GateCtx(**base)


def _buy(sym="AAA", qty=50, px=100.0):
    return FM.Action("hackG", "buy", sym, qty, "buy", "limit", limit_price=px, price_ref=px)


def _session_ago(n: int, today: date) -> date:
    """The date that is exactly `n` sessions before `today` under sessions_between."""
    d = today
    while FM.sessions_between(d, today) < n:
        d -= timedelta(days=1)
    return d


# ─────────────────────────────── order ──────────────────────────────────────

def test_gate_order_is_lease_then_shape_then_risk_and_matches_config():
    names = [g[0] for g in FM.GATES]
    assert tuple(names) == tuple(_cfg.FLEET_GATE_ORDER)
    classes = [g[1] for g in FM.GATES]
    rank = {FM.GATE_LEASE: 0, FM.GATE_SHAPE: 1, FM.GATE_RISK: 2}
    assert [rank[c] for c in classes] == sorted(rank[c] for c in classes)
    for must in ("cooldown", "sector_concentration", "name_cap", "gross_cap", "stop_never_loosened",
                 "kill_switch", "credential", "reconciliation"):
        assert must in names
    cfg = FM.gates_config()
    assert cfg["order"] == names and len(cfg["hash"]) == 16


def test_trace_names_every_gate_in_order_for_a_clean_buy(tmp_path):
    c = _contract(tmp_path)
    a = _buy(qty=50)
    tr = FM.run_gates(a, _ctx(c), mode="DRY")
    assert [r["gate"] for r in tr] == list(_cfg.FLEET_GATE_ORDER)
    assert all(r["verdict"] == "PASS" for r in tr) and a.refused is None and a.qty == 50


def test_a_kill_ends_the_trace_with_the_gate_named(tmp_path):
    c = _contract(tmp_path)
    a = _buy()
    tr = FM.run_gates(a, _ctx(c, reconciliation_ok=False, reconciliation_status="MISMATCH"))
    assert tr[-1]["gate"] == "reconciliation" and tr[-1]["verdict"] == "KILL"
    assert a.refused.startswith("reconciliation:")


def test_a_planner_refusal_is_traced_not_regated(tmp_path):
    c = _contract(tmp_path)
    a = _buy()
    a.refused = "$172 < min order $250"
    tr = FM.run_gates(a, _ctx(c))
    assert tr == [{"gate": "planner", "class": "plan", "verdict": "KILL", "reason": "$172 < min order $250",
                   "qty_in": 50, "qty_out": 0}]


# ─────────────────────────────── never enlarge ──────────────────────────────

def test_no_gate_ever_increases_a_proposed_size(tmp_path):
    """Buys, sells, protective stops (some replacing a resting stop) and cancels,
    in BOTH new-gate modes: no row ever has qty_out > qty_in, and a stop's price
    only ever moves up (tighter)."""
    c = _contract(tmp_path)
    rng = random.Random(26)
    for mode_ in ("enforce", "shadow"):
        for _ in range(400):
            kind = rng.choice(["buy", "sell", "stop_new", "stop_renew", "cancel", "exit"])
            qty = rng.randint(1, 400)
            px = rng.uniform(5, 300)
            sym = rng.choice(["AAA", "BBB", "CCC", "DDD"])
            if kind == "buy":
                a = FM.Action("hackG", "buy", sym, qty, "buy", "limit", limit_price=px, price_ref=px)
            elif kind in ("sell", "exit"):
                a = FM.Action("hackG", kind, sym, qty, "sell", "limit", limit_price=px, price_ref=px)
            elif kind == "cancel":
                a = FM.Action("hackG", "cancel", sym, 0, "", "cancel", protective=True, cancel_order_id="x")
            else:
                sp = px * rng.uniform(0.80, 0.98)
                inp = {"replaces_stop": round(px * rng.uniform(0.80, 0.98), 2)} if rng.random() < 0.6 else {}
                a = FM.Action("hackG", kind, sym, qty, "sell", "stop", "gtc", stop_price=sp, price_ref=px,
                              protective=True, inputs=inp)
            sp0 = a.stop_price
            held = {s_: float(rng.randint(0, 300)) for s_ in ("AAA", "BBB", "CCC", "DDD")}
            mv = {s_: q * px for s_, q in held.items()}
            ctx = _ctx(c, cash=rng.uniform(-1000, 60_000), held=held, mv=dict(mv), gross=sum(mv.values()),
                       turnover_left=rng.uniform(0, 50_000), orders_used=rng.randint(0, 70),
                       sector_of={"AAA": "Tech", "BBB": "Tech", "CCC": "Energy"},
                       stopped_out={"DDD": date.today().isoformat()})
            tr = FM.run_gates(a, ctx, mode="DRY", new_gates_mode=mode_)
            assert a.qty <= qty
            for r in tr:
                assert r["qty_out"] <= r["qty_in"]
            if sp0 is not None:
                assert a.stop_price >= sp0


def test_a_gate_that_tries_to_enlarge_is_a_defect_and_kills(tmp_path):
    c = _contract(tmp_path)
    rogue = (("rogue", FM.GATE_RISK, lambda a, ctx: (FM.GATE_SHRINK, a.qty + 10, "bigger")),)
    a = _buy(qty=10)
    tr = FM.run_gates(a, _ctx(c), gates=rogue)
    assert tr[-1]["verdict"] == "KILL" and "GATE_DEFECT" in tr[-1]["reason"]
    assert a.qty == 10 and a.refused
    weird = (("weird", FM.GATE_RISK, lambda a, ctx: ("ENLARGE", 99, "?")),)
    b = _buy(qty=10)
    FM.run_gates(b, _ctx(c), gates=weird)
    assert b.qty == 10 and "GATE_DEFECT" in b.refused
    boom = (("boom", FM.GATE_RISK, lambda a, ctx: 1 / 0),)
    d = _buy(qty=10)
    FM.run_gates(d, _ctx(c), gates=boom)
    assert "GATE_ERROR" in d.refused


# ─────────────────────────────── exits pass ─────────────────────────────────

def _exits(held_qty=100):
    return [FM.Action("hackG", "exit", "AAA", held_qty, "sell", "limit", limit_price=50.0, price_ref=50.0),
            FM.Action("hackG", "sell", "AAA", held_qty, "sell", "limit", limit_price=50.0, price_ref=50.0),
            FM.Action("hackG", "stop_new", "AAA", held_qty, "sell", "stop", "gtc", stop_price=45.0,
                      price_ref=50.0, protective=True),
            FM.Action("hackG", "cancel", "AAA", 0, "", "cancel", protective=True, cancel_order_id="x")]


def test_exits_pass_every_risk_gate_however_bad_the_book(tmp_path):
    """Frozen terms (c26-p2): protective orders, cancels and declared exits pass
    every RISK gate except the per-run order count, which counts them as it did
    before C26. A rebalance sell to zero spends the turnover budget (the v2
    contract grants exits no exemption), so it is tested with budget left."""
    c = _contract(tmp_path)
    for a in _exits():
        ctx = _ctx(c, cash=-50_000.0, held={"AAA": 100.0}, mv={"AAA": 500_000.0}, gross=500_000.0,
                   turnover_left=(0.0 if a.kind != "sell" else 1e9), orders_used=0, sector_of={"AAA": "Tech"},
                   stopped_out=None, cooldown_sessions=99, sector_max_frac=0.01)
        q0 = a.qty
        tr = FM.run_gates(a, ctx, mode="LIVE", new_gates_mode="enforce")
        assert a.refused is None, (a.kind, tr)
        assert a.qty == q0


def test_the_order_cap_counts_and_caps_exits_again_but_never_a_cancel(tmp_path):
    c = _contract(tmp_path)
    cap = int(c["caps"]["max_orders_per_run"])
    for a in _exits():
        FM.run_gates(a, _ctx(c, held={"AAA": 100.0}, orders_used=cap, turnover_left=1e9), mode="LIVE")
        if a.kind == "cancel":
            assert a.refused is None
        else:
            assert a.refused and a.refused.startswith("order_count:")
    ctx = _ctx(c, held={"AAA": 100.0}, turnover_left=1e9)
    FM.run_gates(_exits()[2], ctx)
    assert ctx.orders_used == 1


def test_a_full_rebalance_sell_spends_and_can_exhaust_the_turnover_budget(tmp_path):
    c = _contract(tmp_path)
    ctx = _ctx(c, held={"AAA": 100.0}, turnover_left=1_000.0)
    sell = FM.Action("hackG", "sell", "AAA", 100, "sell", "limit", limit_price=50.0, price_ref=50.0)
    FM.run_gates(sell, ctx)
    assert sell.refused and sell.refused.startswith("turnover_budget:")
    ext = FM.Action("hackG", "exit", "AAA", 100, "sell", "limit", limit_price=50.0, price_ref=50.0)
    FM.run_gates(ext, ctx)
    assert ext.refused is None                # a declared horizon exit never spent it (pre-C26 too)


@pytest.mark.parametrize("lease", ["kill_switch", "credential", "reconciliation", "venue_window"])
def test_only_a_lease_gate_may_block_an_exit(tmp_path, lease):
    c = _contract(tmp_path)
    kw = {"kill_switch": {"stop_file_present": True}, "credential": {"credential_ok": False},
          "reconciliation": {"reconciliation_ok": False, "reconciliation_status": "FOREIGN_ORDERS"},
          "venue_window": {"market_ok": False}}[lease]
    for a in _exits():
        FM.run_gates(a, _ctx(c, held={"AAA": 100.0}, **kw), mode="LIVE")
        assert a.refused and a.refused.startswith(lease + ":")
    lease_names = {g[0] for g in FM.GATES if g[1] == FM.GATE_LEASE}
    assert lease_names == {"kill_switch", "credential", "reconciliation", "venue_window"}


def test_a_dry_exit_is_not_blocked_by_the_venue_window(tmp_path):
    c = _contract(tmp_path)
    a = _exits()[0]
    FM.run_gates(a, _ctx(c, held={"AAA": 100.0}, market_ok=False), mode="DRY")
    assert a.refused is None


def test_an_oversized_sell_shrinks_to_the_long_quantity_and_never_shorts(tmp_path):
    c = _contract(tmp_path)
    a = FM.Action("hackG", "sell", "AAA", 120, "sell", "limit", limit_price=50.0, price_ref=50.0)
    tr = FM.run_gates(a, _ctx(c, held={"AAA": 100.0}))
    assert a.qty == 100 and a.refused is None
    assert any(r["gate"] == "long_only" and r["verdict"] == "SHRINK" for r in tr)
    b = FM.Action("hackG", "sell", "ZZZ", 5, "sell", "limit", limit_price=50.0, price_ref=50.0)
    FM.run_gates(b, _ctx(c, held={}))
    assert b.refused.startswith("long_only:")


def test_a_replacing_stop_is_never_loosened(tmp_path):
    c = _contract(tmp_path)
    a = FM.Action("hackG", "stop_renew", "AAA", 100, "sell", "stop", "gtc", stop_price=40.0, price_ref=50.0,
                  protective=True, inputs={"replaces_stop": 44.0})
    tr = FM.run_gates(a, _ctx(c, held={"AAA": 100.0}))
    assert a.refused is None and a.stop_price == 44.0 and a.qty == 100
    assert [r for r in tr if r["gate"] == "stop_never_loosened"][0]["verdict"] == "SHRINK"
    ok = FM.Action("hackG", "stop_renew", "AAA", 100, "sell", "stop", "gtc", stop_price=46.0, price_ref=50.0,
                   protective=True, inputs={"replaces_stop": 44.0})
    FM.run_gates(ok, _ctx(c, held={"AAA": 100.0}))
    assert ok.stop_price == 46.0


# ─────────────────────────────── cooldown ───────────────────────────────────
#
# `cooldown` is one of the two NEW_GATES (C26) that default to SHADOW mode
# (`config.FLEET_NEW_GATES_MODE`): these two tests pin the gate's OWN verdict
# logic, so they call it with `new_gates_mode="enforce"` explicitly. The
# shadow-mode tests below pin the default (no `new_gates_mode` passed).

def test_cooldown_blocks_reentry_at_n_minus_1_and_allows_at_n(tmp_path):
    c = _contract(tmp_path)
    today = date.today()
    n = 5
    blocked = _buy("AAA", 10)
    FM.run_gates(blocked, _ctx(c, today=today, cooldown_sessions=n,
                               stopped_out={"AAA": _session_ago(n - 1, today).isoformat()}),
                new_gates_mode="enforce")
    assert blocked.refused and blocked.refused.startswith("cooldown:")
    allowed = _buy("AAA", 10)
    FM.run_gates(allowed, _ctx(c, today=today, cooldown_sessions=n,
                               stopped_out={"AAA": _session_ago(n, today).isoformat()}),
                new_gates_mode="enforce")
    assert allowed.refused is None
    other = _buy("BBB", 10)
    FM.run_gates(other, _ctx(c, today=today, stopped_out={"AAA": today.isoformat()}),
                new_gates_mode="enforce")
    assert other.refused is None


def test_cooldown_refuses_buys_when_the_stop_history_is_unreadable(tmp_path):
    c = _contract(tmp_path)
    a = _buy()
    FM.run_gates(a, _ctx(c, stopped_out=None), new_gates_mode="enforce")
    assert a.refused.startswith("cooldown:") and "unreadable" in a.refused


def test_the_venue_reader_finds_old_gtc_stops_through_their_fills():
    import json as _json
    fills = [{"symbol": "AAA", "side": "sell", "order_id": "old-gtc", "transaction_time": "2026-10-01T15:00:00Z"},
             {"symbol": "BBB", "side": "sell", "order_id": "lim-1", "transaction_time": "2026-10-01T15:00:00Z"},
             {"symbol": "CCC", "side": "buy", "order_id": "buy-1", "transaction_time": "2026-10-01T15:00:00Z"}]
    closed = [{"id": "lim-1", "type": "limit"}]       # the GTC stop was submitted BEFORE the window
    seen = []

    def t(method, url, headers, body):
        seen.append(url)
        if "/activities/FILL" in url:
            return 200, _json.dumps(fills).encode()
        if url.split("?")[0].endswith("/v2/orders/old-gtc"):
            return 200, _json.dumps({"id": "old-gtc", "type": "stop"}).encode()
        if url.split("?")[0].endswith("/v2/orders"):
            return 200, _json.dumps(closed).encode()
        return 404, b"{}"
    v = FM.Venue("k", "s", transport=t)
    out = v.stop_fills_since("2026-09-20T00:00:00Z")
    assert [(o["symbol"], o["type"]) for o in out] == [("AAA", "stop")]
    assert any(u.split("?")[0].endswith("/v2/orders/old-gtc") for u in seen)
    assert not any(u.split("?")[0].endswith("/v2/orders/lim-1") for u in seen)


def test_historical_order_404_uses_only_accepted_owned_order_evidence(tmp_path):
    import json as _json
    fills = [{"symbol": "AAA", "side": "sell", "order_id": "old-stop",
              "transaction_time": "2026-10-01T15:00:00Z"}]

    def t(method, url, headers, body):
        if "/activities/FILL" in url:
            return 200, _json.dumps(fills).encode()
        if url.split("?")[0].endswith("/v2/orders"):
            return 200, b"[]"
        if url.split("?")[0].endswith("/v2/orders/old-stop"):
            return 404, b'{"message":"historical order unavailable"}'
        return 404, b"{}"

    v = FM.Venue("k", "s", transport=t)
    with pytest.raises(FM.FleetRefusal, match="type unknown"):
        v.stop_fills_since("2026-09-20T00:00:00Z")
    FM.append_jsonl(FM.decisions_path(tmp_path), {"row": "decision", "role": "hackT",
                    "run_id": "r1", "coid": "owned-stop", "mode": "LIVE", "refused": None,
                    "type": "stop"})
    # A planned stop alone is not an accepted broker order.
    assert FM.owned_order_types("hackT", tmp_path) == {}
    FM.append_jsonl(FM.decisions_path(tmp_path), {"row": "outcome", "role": "hackT",
                    "run_id": "r1", "coid": "owned-stop", "outcome": "submitted new id old-stop",
                    "order_id": "old-stop"})
    assert v.stop_fills_since("2026-09-20T00:00:00Z",
                              owned_types=FM.owned_order_types("hackT", tmp_path))[0]["type"] == "stop"
    FM.append_jsonl(FM.decisions_path(tmp_path), {"row": "decision", "role": "hackT",
                    "run_id": "r2", "coid": "conflict", "mode": "LIVE", "refused": None,
                    "type": "limit"})
    FM.append_jsonl(FM.decisions_path(tmp_path), {"row": "outcome", "role": "hackT",
                    "run_id": "r2", "coid": "conflict", "outcome": "submitted new id old-stop",
                    "order_id": "old-stop"})
    assert FM.owned_order_types("hackT", tmp_path) == {}
    with pytest.raises(FM.FleetRefusal, match="type unknown"):
        v.stop_fills_since("2026-09-20T00:00:00Z",
                           owned_types=FM.owned_order_types("hackT", tmp_path))


@pytest.mark.parametrize("known_type", ["stop", "limit"])
@pytest.mark.parametrize("unknown_type", [None, "unknown_new_type"])
@pytest.mark.parametrize("unknown_first", [False, True])
def test_mixed_live_decision_types_keep_historical_404_unknown(
        tmp_path, known_type, unknown_type, unknown_first):
    types = (unknown_type, known_type) if unknown_first else (known_type, unknown_type)
    rows = [{"row": "decision", "role": "hackT", "run_id": "r", "coid": "c",
             "mode": "LIVE", "refused": None, "type": typ}
            for typ in types]
    for row in rows:
        FM.append_jsonl(FM.decisions_path(tmp_path), row)
    FM.append_jsonl(FM.decisions_path(tmp_path),
                    {"row": "outcome", "role": "hackT", "run_id": "r", "coid": "c",
                     "outcome": "submitted new id x", "order_id": "x"})

    def t(method, url, headers, body):
        if "/activities/FILL" in url:
            return 200, json.dumps([{"symbol": "AAA", "side": "sell", "order_id": "x",
                                     "transaction_time": "2026-10-01T15:00:00Z"}]).encode()
        if url.split("?")[0].endswith("/v2/orders"):
            return 200, b"[]"
        return 404, b"{}"

    owned = FM.owned_order_types("hackT", tmp_path)
    assert owned == {}
    with pytest.raises(FM.FleetRefusal, match="type unknown"):
        FM.Venue("k", "s", transport=t).stop_fills_since("2026-09-20T00:00:00Z", owned_types=owned)


@pytest.mark.parametrize("irrelevant", [{"mode": "DRY", "refused": None},
                                       {"mode": "LIVE", "refused": "venue_window: closed"}])
def test_unsubmitted_plans_do_not_poison_accepted_owned_type(tmp_path, irrelevant):
    for typ, fields in (("stop", {"mode": "LIVE", "refused": None}),
                        (None, irrelevant)):
        FM.append_jsonl(FM.decisions_path(tmp_path),
                        {"row": "decision", "role": "hackT", "run_id": "r", "coid": "c",
                         "type": typ, **fields})
    FM.append_jsonl(FM.decisions_path(tmp_path),
                    {"row": "outcome", "role": "hackT", "run_id": "r", "coid": "c",
                     "outcome": "submitted new id x", "order_id": "x"})
    assert FM.owned_order_types("hackT", tmp_path) == {"x": "stop"}


# ─────────────────────────────── sector cap ─────────────────────────────────
#
# `sector_concentration` is the other NEW_GATES member: these two tests pin
# its own verdict logic with `new_gates_mode="enforce"` (see the cooldown
# section above for why).

def test_sector_cap_shrinks_the_order_that_breaches_it_and_only_that_one(tmp_path):
    c = _contract(tmp_path)
    sector_of = {"TA": "Tech", "TB": "Tech", "TC": "Tech", "EA": "Energy"}
    # Tech is 35% of a 100k account holding 65k gross
    mv = {"TA": 20_000.0, "TB": 15_000.0, "EA": 30_000.0}
    ctx = _ctx(c, cash=35_000.0, held={"TA": 200.0, "TB": 150.0, "EA": 300.0}, mv=dict(mv),
               gross=sum(mv.values()), sector_of=sector_of, sector_max_frac=0.40)
    other = _buy("EB", 20, 100.0)             # unmapped name: the UNKNOWN bucket, far from the cap
    tech = _buy("TC", 90, 100.0)              # $9,000 would take Tech to $44k > 40% of $100k
    FM.run_gates(other, ctx, new_gates_mode="enforce")
    assert other.refused is None and other.qty == 20
    tr = FM.run_gates(tech, ctx, new_gates_mode="enforce")
    sec = [r for r in tr if r["gate"] == "sector_concentration"][0]
    assert sec["verdict"] == "SHRINK" and tech.refused is None
    assert all(r["verdict"] == "PASS" for r in tr if r["gate"] != "sector_concentration")
    # room n: (35k + n) <= 0.4 * max(67k + n, 100k)  ->  n <= 5,000 -> 50 shares
    assert tech.qty == 50
    assert ctx.sector_mv["Tech"] == pytest.approx(40_000.0)


def test_unknown_sector_is_one_bucket_and_the_declared_control_is_exempt(tmp_path):
    c = _contract(tmp_path, name_cap_overrides={"SPY": 0.95})
    ctx = _ctx(c, mv={"QQQ": 39_000.0}, held={"QQQ": 100.0}, gross=39_000.0, cash=61_000.0)
    x = _buy("XYZ", 50, 100.0)                # unknown sector -> joins QQQ's UNKNOWN bucket
    tr = FM.run_gates(x, ctx, new_gates_mode="enforce")
    assert x.refused is None and x.qty == 10  # room 40k - 39k = $1,000
    assert [r for r in tr if r["gate"] == "sector_concentration"][0]["verdict"] == "SHRINK"
    spy = _buy("SPY", 500, 100.0)
    tr = FM.run_gates(spy, _ctx(c), new_gates_mode="enforce")
    assert spy.refused is None and spy.qty == 500
    assert "declared cap" in [r for r in tr if r["gate"] == "sector_concentration"][0]["reason"]


# ───────────────────── C26 shadow mode: cooldown + sector_concentration ─────

def test_shadow_mode_is_the_default_and_never_kills_or_shrinks(tmp_path):
    """The default call (no `new_gates_mode`) reads `config.FLEET_NEW_GATES_MODE`,
    which is "shadow": a cooldown KILL and a sector SHRINK both become PASS,
    the order is untouched, and the real verdict is on `shadow_verdict`."""
    assert _cfg.FLEET_NEW_GATES_MODE == FM.SHADOW_MODE
    c = _contract(tmp_path)
    today = date.today()
    n = 5
    a = _buy("AAA", 10)
    tr = FM.run_gates(a, _ctx(c, today=today, cooldown_sessions=n,
                              stopped_out={"AAA": _session_ago(n - 1, today).isoformat()}))
    assert a.refused is None and a.qty == 10                 # not killed, not shrunk
    row = [r for r in tr if r["gate"] == "cooldown"][0]
    assert row["verdict"] == "PASS" and row["shadow_verdict"].startswith("SHADOW_WOULD_KILL")
    assert row["qty_out"] == 10

    sector_of = {"TA": "Tech", "TB": "Tech", "TC": "Tech", "EA": "Energy"}
    mv = {"TA": 20_000.0, "TB": 15_000.0, "EA": 30_000.0}
    ctx = _ctx(c, cash=35_000.0, held={"TA": 200.0, "TB": 150.0, "EA": 300.0}, mv=dict(mv),
               gross=sum(mv.values()), sector_of=sector_of, sector_max_frac=0.40)
    tech = _buy("TC", 90, 100.0)              # would SHRINK to 50 under enforce
    tr2 = FM.run_gates(tech, ctx)
    assert tech.refused is None and tech.qty == 90            # untouched
    row2 = [r for r in tr2 if r["gate"] == "sector_concentration"][0]
    assert row2["verdict"] == "PASS" and row2["shadow_verdict"] == "SHADOW_WOULD_SHRINK(to=50): sector Tech <= 40% of gross: 90 -> 50 (room $5,000)"
    # the running total still tracks the ACTUAL (unshrunk) buy, same as any PASS
    assert ctx.sector_mv["Tech"] == pytest.approx(44_000.0)


def test_enforce_mode_binds_both_new_gates_like_any_other_gate(tmp_path):
    c = _contract(tmp_path)
    today = date.today()
    a = _buy("AAA", 10)
    FM.run_gates(a, _ctx(c, today=today, cooldown_sessions=5,
                         stopped_out={"AAA": _session_ago(4, today).isoformat()}),
                new_gates_mode="enforce")
    assert a.refused and a.refused.startswith("cooldown:")

    sector_of = {"TA": "Tech", "TB": "Tech", "TC": "Tech"}
    mv = {"TA": 20_000.0, "TB": 15_000.0}
    ctx = _ctx(c, cash=65_000.0, held={"TA": 200.0, "TB": 150.0}, mv=dict(mv),
               gross=sum(mv.values()), sector_of=sector_of, sector_max_frac=0.40)
    tech = _buy("TC", 90, 100.0)
    tr = FM.run_gates(tech, ctx, new_gates_mode="enforce")
    row = [r for r in tr if r["gate"] == "sector_concentration"][0]
    assert row["verdict"] == "SHRINK" and "shadow_verdict" not in row
    assert tech.qty == 50


def test_every_other_gate_still_enforces_while_the_new_two_are_shadowed(tmp_path):
    """Shadow mode names only `cooldown` and `sector_concentration`: a gate
    outside that set keeps refusing even on the default call."""
    c = _contract(tmp_path)
    oversized = _buy("AAA", 200, 100.0)       # $20k vs a 10% name cap on 100k
    tr = FM.run_gates(oversized, _ctx(c))
    assert tr[-1]["gate"] == "name_cap" and tr[-1]["verdict"] == "KILL"
    assert oversized.qty == 200 and "shadow_verdict" not in tr[-1]


def test_sector_room_formula_is_continuous_at_the_equity_floor():
    x, e = 0.4, 100_000.0
    assert FM.sector_room_usd(10_000.0, 50_000.0, e, x) == pytest.approx(30_000.0)
    # above the floor the denominator is the gross after the order
    n = FM.sector_room_usd(35_000.0, 99_000.0, e, x)
    assert (35_000.0 + n) == pytest.approx(x * (99_000.0 + n))


# ─────────────────────────────── the other caps as gates ────────────────────

def test_cash_gross_name_and_turnover_refuse_as_the_frozen_terms_did(tmp_path):
    """c26-p2: these four REFUSE exactly like pre-C26 `check_limits` /
    `apply_turnover_budget` -- never shrink -- and agree with check_limits."""
    c = _contract(tmp_path)
    cases = [("name_cap", _buy("AAA", 200, 100.0), {}),
             ("gross_cap", _buy("BBB", 80, 100.0), {"gross": 95_000.0, "cash": 50_000.0}),
             ("cash", _buy("CCC", 80, 100.0), {"cash": 5_000.0})]
    for gate, a, kw in cases:
        ctx = _ctx(c, **kw)
        old = FM.check_limits(a, equity=ctx.equity, cash=ctx.cash, held=ctx.held, mv=ctx.mv,
                              gross=ctx.gross, contract=c)
        q0 = a.qty
        tr = FM.run_gates(a, ctx)
        assert old is not None
        assert a.refused.startswith(gate + ":") and a.qty == q0 and tr[-1]["verdict"] == "KILL"
    t = _buy("DDD", 50, 100.0)
    ctx = _ctx(c, turnover_left=3_000.0)
    FM.run_gates(t, ctx)
    assert t.refused.startswith("turnover_budget:") and t.qty == 50
    assert ctx.turnover_left == pytest.approx(3_000.0)


def test_turnover_is_spent_in_plan_order_even_when_a_later_gate_refuses(tmp_path):
    """Pre-C26 `apply_turnover_budget` ran over the whole plan BEFORE check_limits,
    so an order later refused for cash still spent the budget. Kept verbatim."""
    c = _contract(tmp_path)
    ctx = _ctx(c, turnover_left=6_000.0, cash=1_000.0)
    a = _buy("AAA", 50, 100.0)                # $5,000 spends the budget, then dies at cash
    FM.run_gates(a, ctx)
    assert a.refused.startswith("cash:") and ctx.turnover_left == pytest.approx(1_000.0)


def test_order_count_binds_entries(tmp_path):
    c = _contract(tmp_path)
    ctx2 = _ctx(c, orders_used=int(c["caps"]["max_orders_per_run"]), held={"AAA": 10.0})
    b = _buy("BBB", 5, 100.0)
    FM.run_gates(b, ctx2)
    assert b.refused.startswith("order_count:")


# ─────────────────────────────── the run receipt ────────────────────────────

class _VenueFake:
    """One readable paper account for `run_role`, every endpoint offline."""

    def __init__(self, today: date, stop_fill_day: date, *, historical_404: bool = False,
                 is_open: bool = False):
        self.today, self.stop_fill_day, self.calls = today, stop_fill_day, []
        self.historical_404 = historical_404
        self.is_open = is_open

    def __call__(self, method, url, headers, body):
        import json as _j
        self.calls.append((method, url))
        path = url.split("?")[0].replace(FM.TRADING_HOST, "").replace(FM.DATA_HOST, "")
        q = url.split("?")[1] if "?" in url else ""
        if method != "GET":
            return 500, b'{"message":"the test venue accepts no writes"}'
        if path == "/v2/account":
            return 200, _j.dumps({"equity": "100000", "cash": "90000", "last_equity": "100000",
                                  "account_number": "TEST"}).encode()
        if path == "/v2/clock":
            return 200, _j.dumps({"timestamp": f"{self.today.isoformat()}T10:00:00-04:00",
                                  "is_open": self.is_open,
                                  "next_close": (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()}).encode()
        if path == "/v2/positions":
            return 200, _j.dumps([
                {"symbol": "AAA", "qty": "100", "current_price": "50", "market_value": "5000", "asset_class": "us_equity"},
                {"symbol": "BBB", "qty": "250", "current_price": "20", "market_value": "5000", "asset_class": "us_equity"},
            ]).encode()
        if path == "/v2/orders" and "status=open" in q:
            return 200, _j.dumps([{"id": "s1", "symbol": "AAA", "side": "sell", "type": "stop", "qty": "100",
                                   "stop_price": "45", "client_order_id": "aegisfm-t-stop"}]).encode()
        if path == "/v2/orders" and "status=closed" in q:
            return 200, b"[]"                           # the stop was a GTC submitted long ago
        if path == "/v2/orders/o-ccc":
            if self.historical_404:
                return 404, b'{"message":"historical order unavailable"}'
            return 200, _j.dumps({"id": "o-ccc", "type": "stop"}).encode()
        if path == "/v2/orders":
            return 200, b"[]"
        if path.startswith("/v2/account/activities"):
            import urllib.parse as _u
            after = dict(_u.parse_qsl(q)).get("after", "")
            fill_t = f"{self.stop_fill_day.isoformat()}T15:00:00Z"
            if after and after < fill_t:
                return 200, _j.dumps([{"symbol": "CCC", "side": "sell", "qty": "10", "order_id": "o-ccc",
                                       "transaction_time": fill_t}]).encode()
            return 200, b"[]"
        if path == "/v2/stocks/trades/latest":
            return 200, _j.dumps({"trades": {s: {"p": 30.0} for s in ("CCC", "DDD")}}).encode()
        if path == "/v2/stocks/quotes/latest":
            return 200, b'{"quotes": {}}'
        return 200, b"{}"


@pytest.mark.parametrize("historical_404,seed_owned", [(False, False), (True, True), (True, False)])
def test_run_role_puts_a_named_gate_trace_on_every_action(tmp_path, monkeypatch, historical_404, seed_owned):
    from scripts import fleet_manager_run as RUN
    monkeypatch.setattr(FM, "root", lambda base=None: tmp_path if base is None else base)
    monkeypatch.setattr(RUN, "panel_sigma_and_screen",
                        lambda syms: ({s: 0.02 for s in syms}, {}, {}))
    monkeypatch.setattr(RUN, "stop_counterfactual_step", lambda *a, **k: {"skipped": "test"})
    today = date.today()
    fake = _VenueFake(today, _session_ago(1, today), historical_404=historical_404)
    monkeypatch.setattr(FM, "_urllib_transport", fake)
    caps = FM.caps_block()
    for v_, sel in (("v1", {"kind": "legacy_hold"}),
                    ("v2", {"kind": "frozen_book", "horizon_sessions": 21,
                            "positions": [{"ticker": "CCC", "weight": 0.05}, {"ticker": "DDD", "weight": 0.05}]})):
        FM.freeze_contract({"schema": "fleet_manager_contract/1", "role": "hackT", "version": v_,
                            "licence": FM.LICENCE, "alpha_source": "test", "selection": sel,
                            "stop_rule": FM.stop_rule_block(0.10), "caps": caps, "costs": FM.costs_block(),
                            "twin": {"weights": {}}}, base=tmp_path)
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "hackT.json").write_text(
        json.dumps({"t": f"{today.isoformat()}T23:59:00+00:00", "positions": {"AAA": 100.0, "BBB": 250.0}}),
        encoding="utf-8")
    if seed_owned:
        FM.append_jsonl(FM.decisions_path(tmp_path), {"row": "decision", "role": "hackT",
                        "run_id": "old", "coid": "old-stop", "mode": "LIVE", "refused": None,
                        "type": "stop"})
        FM.append_jsonl(FM.decisions_path(tmp_path), {"row": "outcome", "role": "hackT",
                        "run_id": "old", "coid": "old-stop", "outcome": "submitted new id o-ccc",
                        "order_id": "o-ccc"})
    env = {"AAT_HACKT_KEY_ID": "k", "AAT_HACKT_SECRET_KEY": "s"}
    res = RUN.run_role("hackT", env=env, modes={"hackT": {"contract": "v2", "maintenance": "LIVE",
                                                          "entries": "LIVE"}},
                       pass_="open", live_flag=False, run_id="t1", books={}, issuer_of={}, stitched=set(),
                       digest=None, digest_name=None, baseline=(None, {}), pool={}, rebaseline=False,
                       sector_of={"AAA": "Tech", "BBB": "Tech", "CCC": "Energy", "DDD": "Tech"})
    assert res["status"] == "ok"
    if historical_404 and not seed_owned:
        assert res["stopped_out_recent"] is None and res.get("stop_history_error")
    else:
        assert res["stopped_out_recent"]["CCC"] == fake.stop_fill_day.isoformat()
        assert "stop_history_error" not in res
    assert {m for m, _ in fake.calls} == {"GET"}                     # a DRY run sends nothing
    acts = {(a["kind"], a["symbol"]): a for a in res["actions"]}
    assert all(a.get("gates") and a.get("story_id", "").startswith("fs-") for a in res["actions"])
    # CCC was stopped out one session ago: `cooldown` is a NEW_GATES member
    # and `config.FLEET_NEW_GATES_MODE` defaults to "shadow", so the re-entry
    # is NOT killed -- the gate still evaluates and logs what it would have
    # done, and the order proceeds (this is the behaviour this mode exists
    # for: it must not change a live book's executed orders).
    ccc = acts[("buy", "CCC")]
    cooldown_row = [g for g in ccc["gates"] if g["gate"] == "cooldown"][0]
    assert cooldown_row["verdict"] == "PASS"
    assert cooldown_row["shadow_verdict"].startswith("SHADOW_WOULD_KILL")
    assert ccc["refused"] is None
    # DDD is Tech, and Tech already holds 10% of equity: the buy passes (40% cap) at its full size
    ddd = acts[("buy", "DDD")]
    assert ddd["refused"] is None and ddd["gates"][-1]["gate"] == "order_count"
    # BBB has no stop: the protective stop passes every gate (an exit), DRY
    bbb = acts[("stop_new", "BBB")]
    assert bbb["refused"] is None and bbb["mode"] == "DRY"
    assert res["gate_summary"]["cooldown"]["PASS"] >= 1
    assert "KILL" not in res["gate_summary"].get("cooldown", {})
    rows = [r for r in FM.read_jsonl(tmp_path / "decisions.jsonl")
            if r.get("row") == "decision" and r.get("run_id") == "t1"]
    assert rows and all(r["gates"] and r["gates_hash"] == RUN.GATES_CFG["hash"] for r in rows)
    # the shadow verdict reaches the committed decision row too
    ccc_row = next(r for r in rows if r.get("symbol") == "CCC" and r.get("side") == "buy")
    assert any(g.get("shadow_verdict", "").startswith("SHADOW_WOULD_KILL") for g in ccc_row["gates"])


def test_closed_venue_refuses_missing_stop_and_next_pass_replans_it(tmp_path, monkeypatch):
    from scripts import fleet_manager_run as RUN
    monkeypatch.setattr(FM, "root", lambda base=None: tmp_path if base is None else base)
    monkeypatch.setattr(RUN, "panel_sigma_and_screen", lambda syms: ({s: 0.02 for s in syms}, {}, {}))
    monkeypatch.setattr(RUN, "stop_counterfactual_step", lambda *a, **k: {"skipped": "test"})
    today = date.today()
    fake = _VenueFake(today, _session_ago(1, today))
    monkeypatch.setattr(FM, "_urllib_transport", fake)
    body = {"schema": "fleet_manager_contract/1", "role": "hackT", "version": "v1",
            "licence": FM.LICENCE, "alpha_source": "test", "selection": {"kind": "legacy_hold"},
            "stop_rule": FM.stop_rule_block(0.10), "caps": FM.caps_block(),
            "costs": FM.costs_block(), "twin": {"weights": {}}}
    FM.freeze_contract(body, base=tmp_path)
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "hackT.json").write_text(
        json.dumps({"t": f"{today.isoformat()}T23:59:00Z", "positions": {"AAA": 100.0, "BBB": 250.0}}),
        encoding="utf-8")
    kwargs = dict(env={"AAT_HACKT_KEY_ID": "k", "AAT_HACKT_SECRET_KEY": "s"},
                  modes={"hackT": {"contract": "v1", "maintenance": "LIVE", "entries": "DRY"}},
                  pass_="open", live_flag=True, books={}, issuer_of={}, stitched=set(),
                  digest=None, digest_name=None, baseline=(None, {}), pool={}, rebaseline=False)
    closed = RUN.run_role("hackT", run_id="closed", **kwargs)
    missed = next(a for a in closed["actions"] if a["kind"] == "stop_new" and a["symbol"] == "BBB")
    assert missed["qty"] == 250 and missed["refused"].startswith("venue_window:")
    assert {m for m, _ in fake.calls} == {"GET"}
    fake.is_open = True
    fake.calls.clear()
    retried = RUN.run_role("hackT", run_id="retry", **kwargs)
    stop = next(a for a in retried["actions"] if a["kind"] == "stop_new" and a["symbol"] == "BBB")
    assert stop["qty"] == 250 and stop["refused"] is None
    assert stop["outcome"].startswith("REJECTED http 500")
    assert any(m == "POST" for m, _ in fake.calls)  # fixture rejects it; no accepted protection


def test_fleet_new_gates_mode_is_shadow_by_default():
    """The decision pending in `docs/research_notes/2026-10-07/
    fleet_gates_and_eod_audit_2026-10-07.md` (hack2's Technology buys would be
    KILLED tonight at 22:45 HKT) is not yet made: the two new gates default to
    shadow everywhere, including `gates_config()`'s hashed receipt."""
    assert _cfg.FLEET_NEW_GATES_MODE == "shadow"
    gc = FM.gates_config()
    assert gc["new_gates_mode"] == "shadow"
    assert set(gc["new_gates"]) == {"cooldown", "sector_concentration"}
