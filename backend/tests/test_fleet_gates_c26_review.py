"""C26 review fixes (docs/reviews/REVIEW_2026-10-07_C26_FLEET_GATES_EOD_AUDIT.md).

Pinned here:
* the REAL 2026-10-06 open + preclose plans replay through the full gate list
  with identical quantities and LIVE/REFUSED outcomes (sanitised fixture);
* a failing stop-history read never aborts the account, and health reads it
  as DEGRADED;
* the C26 delta line on every account;
* the re-protect stop is sized AFTER the gates, and a refused sell leaves its
  resting stops untouched;
* enforce mode is refused for the sector gate on a stale map or a blind book;
* the audit's previous session skips exchange holidays.
Offline; dates derive from `today`.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from backend import config as _cfg
from backend.services import fleet_eod_audit as EOD
from backend.services import fleet_manager as FM

FIXTURE = Path(__file__).parent / "fixtures" / "c26" / "replay_2026-10-06.json"


# ─────────────────────────────── replay ─────────────────────────────────────

def _replay(new_gates_mode: str) -> list[dict]:
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    out = []
    for p in fx["passes"]:
        for acc in p["accounts"]:
            contract = {"caps": acc["caps"], "policy_hash": acc["policy_hash"]}
            held = {q["symbol"]: float(q["qty"]) for q in acc["positions"]}
            mv = {q["symbol"]: abs(float(q["market_value"])) for q in acc["positions"]}
            ck = acc["clock"]
            ctx = FM.GateCtx(equity=acc["equity"], cash=acc["cash"], held=held, mv=mv, gross=sum(mv.values()),
                             contract=contract, today=date.fromisoformat(ck["session_day_et"]),
                             reconciliation_ok=bool(acc["reconcile"]["ok"]),
                             reconciliation_status=str(acc["reconcile"]["status"]),
                             market_ok=bool(ck["is_open"]) and (ck["minutes_to_close"] or 0)
                             >= _cfg.FLEET_MANAGER_MIN_MINUTES_TO_CLOSE,
                             turnover_left=acc["caps"]["daily_turnover_frac"] * acc["equity"],
                             stopped_out={}, sector_of=fx["sector_of"])
            for x in acc["actions"]:
                prot = x["kind"] in ("cancel", "stop_new", "stop_renew")
                a = FM.Action(acc["role"], x["kind"], x["symbol"], int(x["qty"] or 0), x["side"] or "",
                              x["type"] or "", limit_price=x["limit"], stop_price=x["stop"],
                              price_ref=float(x["limit"] or x["stop"] or 0), protective=prot)
                if x["refused"] and "min order" in x["refused"]:
                    a.refused = x["refused"]            # the planner's refusal, before any gate
                tr = FM.run_gates(a, ctx, mode="LIVE" if p["live_flag"] else "DRY",
                                  new_gates_mode=new_gates_mode)
                out.append({"pass": p["pass"], "role": acc["role"], "symbol": x["symbol"], "kind": x["kind"],
                            "old_qty": x["qty"], "old_refused": bool(x["refused"]),
                            "new_qty": a.qty, "new_refused": bool(a.refused), "refused": a.refused, "trace": tr})
    return out


def test_the_real_10_06_plans_replay_identically_through_the_gates():
    rows = _replay("shadow")
    assert len(rows) >= 50
    diff = [(r["role"], r["kind"], r["symbol"], r["old_qty"], r["new_qty"], r["refused"]) for r in rows
            if r["old_qty"] != r["new_qty"] or r["old_refused"] != r["new_refused"]]
    assert diff == []
    shadow = [(r["role"], r["symbol"]) for r in rows for g in r["trace"]
              if str(g.get("shadow_verdict", "")).startswith("SHADOW_WOULD_KILL")]
    # the review's hand replay: hack2's Technology top-ups are the only would-kills
    assert shadow and all(role == "hack2" for role, _ in shadow)
    assert FM.c26_delta(r["trace"] for r in rows)["shrinks_applied"] == 0


def test_in_enforce_the_only_replay_difference_is_the_sector_gate_on_hack2():
    rows = _replay("enforce")
    diff = [r for r in rows if r["old_refused"] != r["new_refused"] or r["old_qty"] != r["new_qty"]]
    assert diff and all(r["role"] == "hack2" and r["refused"].startswith("sector_concentration:") for r in diff)


# ─────────────────────────────── run_role harness ───────────────────────────

class Fake:
    """A readable paper account: AAA 100 @ 50 (resting stop s1 at 45), BBB 250 @ 20 (no stop)."""

    def __init__(self, today: date, history: str = "ok"):
        self.today, self.history, self.calls = today, history, []

    def __call__(self, method, url, headers, body):
        import urllib.parse as up
        self.calls.append((method, url))
        path = url.split("?")[0].replace(FM.TRADING_HOST, "").replace(FM.DATA_HOST, "")
        q = dict(up.parse_qsl(url.split("?")[1])) if "?" in url else {}
        if method != "GET":
            return 500, b'{"message":"the test venue accepts no writes"}'
        if path == "/v2/account":
            return 200, json.dumps({"equity": "100000", "cash": "90000", "last_equity": "100000"}).encode()
        if path == "/v2/clock":
            return 200, json.dumps({"timestamp": f"{self.today}T10:00:00-04:00", "is_open": False}).encode()
        if path == "/v2/positions":
            return 200, json.dumps([
                {"symbol": "AAA", "qty": "100", "current_price": "50", "market_value": "5000", "asset_class": "us_equity"},
                {"symbol": "BBB", "qty": "250", "current_price": "20", "market_value": "5000", "asset_class": "us_equity"},
            ]).encode()
        if path == "/v2/orders" and q.get("status") == "open":
            return 200, json.dumps([{"id": "s1", "symbol": "AAA", "side": "sell", "type": "stop", "qty": "100",
                                     "stop_price": "45", "client_order_id": "aegisfm-t-stop"}]).encode()
        if path == "/v2/orders":
            return 200, b"[]"
        if path.startswith("/v2/account/activities"):
            lookback = q.get("after", "") and q["after"] < f"{self.today}T00:00:00Z"
            if lookback and self.history == "timeout":
                raise TimeoutError("the read timed out")
            if lookback and self.history == "malformed":
                return 200, b'{"message": "an error envelope with HTTP 200"}'
            return 200, b"[]"
        if path == "/v2/stocks/trades/latest":
            return 200, json.dumps({"trades": {s: {"p": 30.0} for s in ("CCC", "DDD")}}).encode()
        if path == "/v2/stocks/quotes/latest":
            return 200, b'{"quotes": {}}'
        return 200, b"{}"


def _run(tmp_path, monkeypatch, *, history="ok", turnover=0.5, positions=None, sector_age=3, sector_of=None):
    from scripts import fleet_manager_run as RUN
    monkeypatch.setattr(FM, "root", lambda base=None: tmp_path if base is None else base)
    monkeypatch.setattr(RUN, "panel_sigma_and_screen", lambda syms: ({s: 0.02 for s in syms}, {}, {}))
    monkeypatch.setattr(RUN, "stop_counterfactual_step", lambda *a, **k: {"skipped": "test"})
    today = date.today()
    fake = Fake(today, history)
    monkeypatch.setattr(FM, "_urllib_transport", fake)
    caps = FM.caps_block()
    caps["daily_turnover_frac"] = turnover
    pos = positions or [{"ticker": "AAA", "weight": 0.01}, {"ticker": "DDD", "weight": 0.05}]
    for v_, sel in (("v1", {"kind": "legacy_hold"}),
                    ("v2", {"kind": "frozen_book", "horizon_sessions": 21, "positions": pos})):
        FM.freeze_contract({"schema": "fleet_manager_contract/1", "role": "hackT", "version": v_,
                            "licence": FM.LICENCE, "alpha_source": "test", "selection": sel,
                            "stop_rule": FM.stop_rule_block(0.10), "caps": caps, "costs": FM.costs_block(),
                            "twin": {"weights": {}}}, base=tmp_path)
    (tmp_path / "state").mkdir(exist_ok=True)
    (tmp_path / "state" / "hackT.json").write_text(json.dumps(
        {"t": f"{today}T23:59:00+00:00", "positions": {"AAA": 100.0, "BBB": 250.0},
         "v2_names": ["AAA", "BBB"]}), encoding="utf-8")
    res = RUN.run_role("hackT", env={"AAT_HACKT_KEY_ID": "k", "AAT_HACKT_SECRET_KEY": "s"},
                       modes={"hackT": {"contract": "v2", "maintenance": "LIVE", "entries": "LIVE"}},
                       pass_="open", live_flag=False, run_id="t1", books={}, issuer_of={}, stitched=set(),
                       digest=None, digest_name=None, baseline=(None, {}), pool={}, rebaseline=False,
                       sector_of=sector_of if sector_of is not None else {"AAA": "Tech", "BBB": "Tech", "DDD": "Tech"},
                       sector_age_days=sector_age)
    return res, fake


# ─────────────────────────────── item 1: the stop-history read ──────────────

@pytest.mark.parametrize("history", ["timeout", "malformed"])
def test_a_failing_stop_history_read_never_aborts_the_account(tmp_path, monkeypatch, history):
    res, _ = _run(tmp_path, monkeypatch, history=history)
    assert res["status"] == "ok" and res["stopped_out_recent"] is None
    assert res["stop_history_error"]
    assert any(a["kind"] == "stop_new" and a["symbol"] == "BBB" for a in res["actions"])   # maintenance ran
    # health: the account is DEGRADED, named
    from types import SimpleNamespace

    from backend.services import task_receipts as TR
    runs = tmp_path / "optimus" / "paper_accounts" / "fleet_manager" / "runs"
    runs.mkdir(parents=True)
    (runs / "run_20991231T000000Z-aaaaaa.json").write_text(json.dumps(
        {"run_id": "x", "pass": "open", "started_utc": "2099-12-31T00:00:00Z", "accounts": [res]}, default=str),
        encoding="utf-8")
    r = TR._fleet_pass("open")(SimpleNamespace(optimus_dir=tmp_path / "optimus"), None)
    assert r.status == "DEGRADED" and "stop history unreadable" in r.reason


# ─────────────────────────────── item 2: the C26 line ───────────────────────

def test_every_account_carries_and_prints_the_c26_line(tmp_path, monkeypatch, capsys):
    from scripts import fleet_manager_run as RUN
    res, _ = _run(tmp_path, monkeypatch)
    d = res["c26_delta"]
    assert d["line"] == (f"C26: {d['shadow_would_kill']} shadow-would-kill, {d['shadow_would_shrink']} "
                         f"shadow-would-shrink, {d['shrinks_applied']} shrinks applied, "
                         f"{d['refusals_to_shrink']} refusals→shrink")
    assert d["gate_policy_version"] == FM.GATE_POLICY_VERSION
    RUN.print_role(res)
    assert d["line"] in capsys.readouterr().out


def test_shadow_verdicts_are_counted_as_shadow_not_pass():
    tr = [[{"gate": "cooldown", "verdict": "PASS", "shadow_verdict": "SHADOW_WOULD_KILL: x"},
           {"gate": "sector_concentration", "verdict": "PASS", "shadow_verdict": "SHADOW_WOULD_SHRINK(to=3): y"},
           {"gate": "long_only", "verdict": "SHRINK"}]]
    s = FM.gate_summary(tr)
    assert s["cooldown"] == {"SHADOW_WOULD_KILL": 1} and s["sector_concentration"] == {"SHADOW_WOULD_SHRINK": 1}
    assert FM.c26_delta(tr)["line"] == ("C26: 1 shadow-would-kill, 1 shadow-would-shrink, 1 shrinks applied, "
                                        "1 refusals→shrink")


# ─────────────────────────────── item 4: re-protect after the gates ─────────

def test_a_refused_trim_leaves_its_resting_stop_alone(tmp_path, monkeypatch):
    res, _ = _run(tmp_path, monkeypatch, turnover=0.01)        # $1,000 budget: both sells refused
    sell = next(a for a in res["actions"] if a["kind"] == "sell" and a["symbol"] == "AAA")
    assert sell["refused"] and sell["refused"].startswith("turnover_budget:")
    assert not any(a["kind"] == "cancel" and a["symbol"] == "AAA" for a in res["actions"])
    assert not any(a["kind"] == "stop_new" and a["symbol"] == "AAA" for a in res["actions"])


def test_the_re_protect_stop_is_sized_from_the_post_gate_quantity(tmp_path, monkeypatch):
    res, _ = _run(tmp_path, monkeypatch, turnover=1.0)
    acts = res["actions"]
    i_c = next(i for i, a in enumerate(acts) if a["kind"] == "cancel" and a["symbol"] == "AAA")
    i_s = next(i for i, a in enumerate(acts) if a["kind"] == "sell" and a["symbol"] == "AAA")
    i_p = next(i for i, a in enumerate(acts) if a["kind"] == "stop_new" and a["symbol"] == "AAA")
    assert i_c < i_s < i_p
    sold, prot = acts[i_s], acts[i_p]
    assert sold["refused"] is None and prot["refused"] is None
    assert prot["qty"] == 100 - sold["qty"] and prot["stop"] >= 45.0
    assert prot["gates"] and acts[i_c]["gates"]


# ─────────────────────────────── item 5: enforce refused on a bad map ───────

def test_enforce_is_refused_for_the_sector_gate_on_a_stale_or_blind_map(tmp_path, monkeypatch):
    monkeypatch.setattr(_cfg, "FLEET_NEW_GATES_MODE", "enforce")
    res, _ = _run(tmp_path, monkeypatch, sector_age=35)
    nm = res["new_gates_mode"]
    assert nm["effective"]["sector_concentration"] == "shadow" and nm["effective"]["cooldown"] == "enforce"
    assert any("35 days" in x for x in nm["sector_enforce_refused"])
    res2, _ = _run(tmp_path / "b", monkeypatch, sector_age=3, sector_of={})       # everything UNKNOWN
    assert res2["new_gates_mode"]["effective"]["sector_concentration"] == "shadow"
    assert any("UNKNOWN" in x for x in res2["new_gates_mode"]["sector_enforce_refused"])
    res3, _ = _run(tmp_path / "c", monkeypatch, sector_age=3)
    assert res3["new_gates_mode"]["effective"]["sector_concentration"] == "enforce"


def test_the_sector_map_age_is_read_from_its_file_name():
    from scripts import fleet_manager_run as RUN
    t = date.today()
    src = f"potential_universe/{(t - timedelta(days=35)).isoformat()}.jsonl identity.sector (3052 symbols)"
    assert RUN.sector_map_age_days(src, t) == 35
    assert RUN.sector_map_age_days("REFUSED: unreadable", t) is None


# ─────────────────────────────── item 7: holidays ───────────────────────────

def test_the_previous_session_skips_exchange_holidays():
    assert EOD.prev_weekday(date(2026, 11, 27)) == date(2026, 11, 25)      # Thanksgiving 11-26
    assert EOD.prev_weekday(date(2026, 9, 8)) == date(2026, 9, 4)          # Labor Day 09-07 + weekend
    for h in _cfg.US_MARKET_HOLIDAYS:
        d = date.fromisoformat(h) + timedelta(days=1)
        assert EOD.prev_weekday(d).isoformat() not in _cfg.US_MARKET_HOLIDAYS


def test_the_receipt_names_the_known_wash_trade_defect():
    assert "403" in _cfg.FLEET_KNOWN_DEFECT_WASH_TRADE and "49 of 75" in _cfg.FLEET_KNOWN_DEFECT_WASH_TRADE
    gc = FM.gates_config()
    assert gc["gate_policy_version"] == "c26-p2-frozen-terms" and "cash" in gc["gate_policy_choices"]
