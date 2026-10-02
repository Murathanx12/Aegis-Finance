"""Offline tests for the fleet manager's 2026-09-30 additions: the market CONTROL
(per-name cap override, contract-driven disaster stop), the protective re-id in
`submit_once`, the tight-stop counterfactual, and the source scoreboard / luck
table / forward-only trust that the learning report reads.

No network: `Venue` gets a fake transport. Dates derive from `today`.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from backend.services import fleet_manager as FM
from scripts import fleet_manager_run as RUN


def _control(tmp_path):
    caps = FM.caps_block()
    caps["name_cap_overrides"] = {"SPY": 0.95}
    caps["daily_turnover_frac"] = 1.0
    sr = FM.stop_rule_block(0.10)
    sr["min_frac"] = 0.10
    body = {"schema": "fleet_manager_contract/1", "role": "hackC", "version": "v2", "licence": FM.LICENCE,
            "alpha_source": "control", "caps": caps, "stop_rule": sr,
            "selection": {"kind": "market_control", "symbol": "SPY", "weight": 0.95},
            "twin": {"weights": {"SPY": 0.95}}}
    return FM.freeze_contract(body, base=tmp_path)


def _legacy(tmp_path):
    body = {"schema": "fleet_manager_contract/1", "role": "hackL", "version": "v1", "licence": FM.LICENCE,
            "alpha_source": "legacy", "caps": FM.caps_block(), "stop_rule": FM.stop_rule_block(0.12),
            "selection": {"kind": "legacy_hold"}, "twin": {"weights": {}}}
    return FM.freeze_contract(body, base=tmp_path)


class FakeTransport:
    def __init__(self):
        self.calls, self.orders = [], {}

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, body))
        if method == "GET" and "/v2/orders:by_client_order_id" in url:
            o = self.orders.get(url.split("client_order_id=")[1])
            return (200, json.dumps(o).encode()) if o else (404, b"{}")
        if method == "POST" and url.endswith("/v2/orders"):
            b = json.loads(body)
            if b["client_order_id"] in self.orders:
                return 422, b'{"message":"client_order_id must be unique"}'
            o = {"id": f"id-{len(self.orders)}", "status": "accepted", **b}
            self.orders[b["client_order_id"]] = o
            return 200, json.dumps(o).encode()
        return 200, b"{}"


# ─────────────────────────────── the control ────────────────────────────────

def test_control_may_hold_its_one_etf_at_95pct_and_nothing_else_above_10pct(tmp_path):
    c = _control(tmp_path)
    eq = 100_000.0
    spy = FM.Action("hackC", "buy", "SPY", 124, "buy", "limit", limit_price=760.0)      # 94.2%
    assert FM.check_limits(spy, equity=eq, cash=eq, held={}, mv={}, gross=0, contract=c) is None
    qqq = FM.Action("hackC", "buy", "QQQ", 150, "buy", "limit", limit_price=600.0)      # 90%, not named
    assert "of equity" in FM.check_limits(qqq, equity=eq, cash=eq, held={}, mv={}, gross=0, contract=c)
    too_big = FM.Action("hackC", "buy", "SPY", 131, "buy", "limit", limit_price=760.0)  # 99.6%
    assert FM.check_limits(too_big, equity=eq, cash=eq, held={}, mv={}, gross=0, contract=c) is not None
    assert FM.control_targets(c) == {"SPY": 0.95}


def test_control_rebalance_sizes_to_its_override_not_the_default_cap(tmp_path):
    c = _control(tmp_path)
    acts = FM.plan_rebalance("hackC", {"SPY": 0.95}, equity=100_000, held={}, prices={"SPY": 760.0},
                             legacy=set(), pending={}, contract=c, day=date.today().isoformat())
    assert len(acts) == 1 and acts[0].qty == int(95_000 // 760.0)


def test_stop_distance_follows_the_contracts_own_rule(tmp_path):
    ctrl, leg = _control(tmp_path), _legacy(tmp_path)
    # SPY sigma 0.8%: 3 sigma = 2.4%, but the control's disaster stop is 10% floor and cap
    assert FM.contract_stop_frac(ctrl, 0.008)[0] == 0.10
    # a legacy contract frozen with config values is unchanged by the refactor
    for sig in (0.005, 0.02, 0.09, None):
        assert FM.contract_stop_frac(leg, sig)[0] == FM.sigma_stop_frac(sig, max_frac=0.12)[0]


def test_legacy_names_in_the_new_targets_are_neither_sold_nor_topped_up(tmp_path):
    leg = _legacy(tmp_path)
    acts = FM.plan_rebalance("hackL", {"OLD": 0.10, "NEW": 0.05}, equity=100_000,
                             held={"OLD": 10.0}, prices={"OLD": 100.0, "NEW": 50.0},
                             legacy={"OLD"}, pending={}, contract=leg, day=date.today().isoformat())
    assert [a.symbol for a in acts] == ["NEW"]


# ─────────────────────────────── protective re-id ───────────────────────────

def test_a_dead_protective_id_gets_a_fresh_suffix_and_a_rerun_still_cannot_double_submit():
    t = FakeTransport()
    v = FM.Venue("k", "s", transport=t)
    coid = FM.client_order_id("hack1", date.today().isoformat(), "stop", "AAA", "h", "10")
    t.orders[coid] = {"id": "old", "status": "canceled", "client_order_id": coid}
    a = FM.Action("hack1", "stop_new", "AAA", 10, "sell", "stop", "gtc", stop_price=9.0, protective=True, coid=coid)
    r1 = FM.submit_once(v, a)
    assert r1["sent"] is True and a.coid == coid[:120] + "-r1"
    b = FM.Action("hack1", "stop_new", "AAA", 10, "sell", "stop", "gtc", stop_price=9.0, protective=True, coid=coid)
    r2 = FM.submit_once(v, b)
    assert r2["sent"] is False and "idempotent" in r2["outcome"]
    assert sum(1 for m, _, _ in t.calls if m == "POST") == 1


def test_a_dead_entry_id_is_not_resubmitted():
    t = FakeTransport()
    v = FM.Venue("k", "s", transport=t)
    coid = FM.client_order_id("hack1", date.today().isoformat(), "buy", "AAA", "h")
    t.orders[coid] = {"id": "old", "status": "canceled", "client_order_id": coid}
    a = FM.Action("hack1", "buy", "AAA", 10, "buy", "limit", limit_price=10.0, coid=coid)
    assert FM.submit_once(v, a)["sent"] is False


# ─────────────────────────────── counterfactual ─────────────────────────────

def _bars(start: date, rows):
    out, d = [], start
    for o, h, l, c in rows:
        d += timedelta(days=1)
        out.append({"d": d.isoformat(), "o": o, "h": h, "l": l, "c": c})
    return out


def test_counterfactual_tight_stop_vs_hold_and_a_gap_fills_at_the_open():
    reg_day = date.today() - timedelta(days=10)
    reg = {"role": "r", "symbol": "X", "qty": 100, "p0": 10.0, "registered_session": reg_day.isoformat(),
           "tight_stop": 9.8, "wide_stop": 9.0}
    bars = _bars(reg_day, [(10.0, 10.1, 9.7, 10.0), (10.0, 10.5, 9.9, 10.4), (8.5, 8.9, 8.4, 8.8)])
    asof = bars[-1]["d"]
    row = FM.cf_stop_row(reg, bars, asof)
    assert row["tight"]["triggered"] == bars[0]["d"] and row["tight"]["pnl_usd"] == -20.0
    assert row["wide_3sigma"]["exit_price"] == 8.5          # gapped through 9.0: filled at the open
    assert row["hold"]["pnl_usd"] == -120.0
    assert row["tight_minus_hold_usd"] == 100.0


def test_counterfactual_counts_the_rest_of_the_registration_session():
    reg_day = date.today() - timedelta(days=3)
    reg = {"role": "r", "symbol": "X", "qty": 10, "p0": 10.0, "registered_session": reg_day.isoformat(),
           "tight_stop": 9.9, "wide_stop": 9.0}
    part = FM.partial_bar([{"t": "b", "o": 10.0, "h": 10.1, "l": 9.85, "c": 10.05},
                           {"t": "a", "o": 10.0, "h": 10.0, "l": 9.95, "c": 10.0}], reg_day.isoformat())
    assert part["o"] == 10.0 and part["l"] == 9.85 and part["c"] == 10.05
    row = FM.cf_stop_row(reg, [], reg_day.isoformat(), reg_day_bar=part)
    assert row["tight"]["triggered"] == reg_day.isoformat()
    assert row["hold"]["pnl_usd"] == 0.5


# ─────────────────────────────── learning: scoreboard, luck, trust ──────────

def test_luck_table_best_of_five():
    lt = FM.luck_table(5, 1, 0.01, 0.0)
    assert lt["p_best_of_k_beats_benchmark_by_chance"] == round(1 - 0.5 ** 5, 4)
    assert lt["p_best_of_k_at_least_this_by_chance"] == round(1 - 0.5 ** 5, 4)
    assert 0.10 < lt["p_best_of_k_shows_t_ge_2_by_chance"] < 0.11


def test_trust_ignores_partial_blocks_so_one_night_cannot_move_a_weight():
    assert FM.source_trust([])["weight"] == 0.0
    assert FM.source_trust([])["trust_daily_excess"] == 0.0
    big = FM.source_trust([0.01])                     # one block of +1%/day: still heavily shrunk
    assert big["shrink"] < 0.06


def _g(role, day, acc, spy, ph, ver="v2", tw=None):
    return {"role": role, "session": day, "account_return": acc, "spy_return": spy, "vs_spy": acc - spy,
            "vs_twin": tw, "policy_hash": ph, "contract_version": ver, "written_utc": day}


def test_scoreboard_ranks_sources_against_the_control_and_prints_the_luck():
    d0 = date.today() - timedelta(days=30)
    days = [(d0 + timedelta(days=i)).isoformat() for i in range(4)]
    rows = []
    for d in days:
        rows += [_g("hack5", d, 0.001, 0.001, "ctl"), _g("hack2", d, 0.003, 0.001, "rev"),
                 _g("hack1", d, -0.002, 0.001, "thm")]
    sb = FM.source_scoreboard(rows, {"ctl": "control", "rev": "revisions", "thm": "themes"})
    assert sb["ranked_ex_control"][0] == "hack2"
    t = {r["role"]: r for r in sb["table"]}
    assert abs(t["hack2"]["sum_vs_control"] - 0.008) < 1e-9
    assert t["hack5"]["excess_basis"] == "vs SPY"
    assert all(r["completed_blocks"] == 0 and r["trust"]["weight"] == 0.0 for r in sb["table"])
    assert "p =" in sb["ahead"] and sb["luck"]["k_accounts"] == 3


def test_a_v1_control_row_is_not_used_as_the_control():
    d = (date.today() - timedelta(days=5)).isoformat()
    rows = [_g("hack5", d, -0.04, -0.007, "old", ver="v1"), _g("hack2", d, 0.0, -0.007, "rev")]
    sb = FM.source_scoreboard(rows, {})
    t = {(r["role"], r["policy_hash"]): r for r in sb["table"]}
    assert t[("hack2", "rev")]["sum_vs_control"] is None
    assert t[("hack2", "rev")]["excess_basis"] == "vs SPY"


def test_the_grade_uses_the_contract_in_force_on_the_graded_session():
    c1, c2 = {"version": "v1", "policy_hash": "a"}, {"version": "v2", "policy_hash": "b"}
    today = date.today()
    before, start = (today - timedelta(days=2)).isoformat(), today.isoformat()
    assert RUN.graded_contract(c2, c1, None, before) is c1
    assert RUN.graded_contract(c2, c1, start, before) is c1
    assert RUN.graded_contract(c2, c1, start, start) is c2
    assert RUN.graded_contract(c1, c1, start, start) is c1


def test_the_learning_report_states_the_leading_source_with_the_luck_table(tmp_path):
    from scripts import daily_learning_report as DLR
    root = tmp_path / "paper_accounts" / "fleet_manager"
    (root / "contracts").mkdir(parents=True)
    (root / "contracts" / "hack2_v2.json").write_text(json.dumps(
        {"role": "hack2", "version": "v2", "policy_hash": "rev", "alpha_source": "revisions"}))
    d0 = date.today() - timedelta(days=20)
    rows = []
    for i in range(6):
        d = (d0 + timedelta(days=i)).isoformat()
        rows += [_g("hack5", d, 0.001, 0.001, "ctl"), _g("hack2", d, 0.002, 0.001, "rev")]
    (root / "grades.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    day = date.today().isoformat()
    sec = DLR.s_fleet(day, tmp_path)
    assert sec["status"] == "OK"
    text = "\n".join(sec["lines"])
    assert "hack2" in text and "revisions" in text and "luck table" in text and "p =" in text
    t = {r["role"]: r for r in sec["scoreboard"]["table"]}
    assert t["hack2"]["completed_blocks"] == 1            # 6 sessions -> one completed block of 5
    # a report dated BEFORE the grades sees none of them (point in time)
    assert DLR.s_fleet((d0 - timedelta(days=1)).isoformat(), tmp_path)["status"] == "NO_DATA"
