"""Chunk G -- model routing, pinned.

* the routing TABLE: each Telegram command reaches the provider Murat named,
  and the four money/state commands read receipts and make NO model call;
* `llama_server.ensure` starts once, and the idle watchdog stops BY PID (a fake
  process: the stop goes through `taskkill /PID <n>`, never an image name);
* NVIDIA is a NAMED provider: it parses a reply (including a reasoning model's
  `reasoning_content`), pins the language, and writes a telemetry row priced
  from the house table -- while DeepSeek stays the sole PRIMARY;
* `/compare` writes three forecast rows with the SAME packet hash and a receipt
  aggregating cost and latency per provider;
* nothing starts llama-server at boot any more.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

from backend import config as C
from backend.services import llama_server as LS
from backend.services import llm_analyzer as LA
from backend.services import model_routing as MR


# ─────────────────────────────── fixtures ───────────────────────────────────

def _receipts(root):
    (root / "paper_accounts").mkdir(parents=True)
    (root / "paper_accounts" / "roi_2026-09-26.json").write_text(json.dumps({
        "generated_utc": "2026-09-26T03:57:21+00:00",
        "aggregate": {"priced_excluding_control_twins": {"n": 2, "sum_equity": 201000.0,
                                                         "pnl": 1000.0, "roi_pct": 0.5},
                      "n_ahead_of_spy": 1, "n_behind_spy": 1},
        "rows": [{"account": "book-a", "family": "night_books", "roi_pct": 1.2, "vs_spy_pp": 0.4},
                 {"account": "book-a-twin", "family": "night_books_twin", "roi_pct": 9.0,
                  "vs_spy_pp": 9.0}]}), encoding="utf-8")
    (root / "sim").mkdir()
    (root / "sim" / "session.json").write_text(json.dumps({
        "id": "e237a0255b9f", "state": "STOPPED", "mode": "paper_profit", "cycle": 86,
        "started": "2026-09-25T19:23:48+00:00", "heartbeat": "2026-09-26T02:53:48+00:00",
        "ended": "2026-09-26T02:54:21+00:00", "end_reason": "stop requested"}), encoding="utf-8")
    (root / "llm_portfolio").mkdir()
    (root / "llm_portfolio" / "leaderboard_2026-09-26.json").write_text(json.dumps({
        "bars_through": "2026-09-24", "n_books": 2, "n_twins": 4,
        "books": [{"name": "rev_flow", "status": "LIVE", "net_to_date": 0.02,
                   "vs_benchmark": 0.01, "benchmark": "SPY"},
                  {"name": "other", "status": "PENDING", "vs_benchmark": None}]}),
        encoding="utf-8")
    (root / "forecasts").mkdir()
    (root / "forecasts" / "day_2026-09-26.json").write_text(json.dumps({
        "day": "2026-09-26", "state": "DONE", "specialist": "investigator:evidence_v3",
        "model": "deepseek/deepseek-flash", "horizons": [1, 5], "done": ["A", "B"],
        "unpriced": [], "refused": [], "n_rows_written": 4, "spent_usd": 0.3,
        "cap_usd": 2.0}), encoding="utf-8")
    return root


def _no_model(*a, **k):
    raise AssertionError("a deterministic command reached a model")


def _fake_call(texts: dict | None = None, log: list | None = None):
    texts = texts or {}

    def call(provider, system, user, *, purpose, **kw):
        if log is not None:
            log.append({"provider": provider, "user": user, "purpose": purpose, **kw})
        return {"provider": provider, "model": f"{provider}-model", "ok": True,
                "status": "OK", "text": texts.get(provider, f"answer from {provider}"),
                "cost_usd": 0.0 if provider != "deepseek" else 0.00042,
                "cost_status": "LISTED", "latency_s": 1.5, "error": None}
    return call


# ─────────────────────────────── the table ──────────────────────────────────

def test_the_routing_table_is_the_one_murat_specified():
    assert MR.ROUTES == {
        "nav": "deterministic", "status": "deterministic", "books": "deterministic",
        "forecasts": "deterministic", "ask": "local", "research": "openclaw+local",
        "deep": "deepseek|nvidia", "compare": "local+deepseek+nvidia"}
    assert MR.COMPARE_PROVIDERS == ("local", "deepseek", "nvidia")


@pytest.mark.parametrize("cmd", sorted(MR.DETERMINISTIC))
def test_deterministic_commands_read_receipts_and_make_no_model_call(cmd, tmp_path):
    root = _receipts(tmp_path)
    out = MR.route(cmd, [], call_fn=_no_model, quest_fn=_no_model, root=root,
                   llama_status=lambda: {"listening": False, "ready": False, "pid": None,
                                         "detail": "not running"})
    assert "CANNOT DETERMINE" not in out, out
    marker = {"nav": "book-a", "status": "e237a0255b9f", "books": "rev_flow",
              "forecasts": "investigator:evidence_v3"}[cmd]
    assert marker in out
    if cmd == "nav":
        assert "book-a-twin" not in out          # control twins are not accounts


def test_a_missing_receipt_says_CANNOT_DETERMINE_not_zero(tmp_path):
    for cmd in ("nav", "books", "forecasts"):
        assert "CANNOT DETERMINE" in MR.route(cmd, [], call_fn=_no_model, root=tmp_path)


def test_ask_goes_to_the_LOCAL_model_and_prints_provider_cost_latency():
    log = []
    out = MR.route("ask", ["what", "is", "beta?"], call_fn=_fake_call(log=log))
    assert [x["provider"] for x in log] == ["local"]
    assert log[0]["ensure_reason"] == "telegram:/ask"
    assert "local · local-model · cost $0.00000 · latency 1.5s" in out


@pytest.mark.parametrize("text,provider", [("why did MU move", "deepseek"),
                                           ("why did MU move --nvidia", "nvidia")])
def test_deep_is_deepseek_unless_nvidia_is_named(text, provider):
    log = []
    out = MR.route("deep", text.split(), call_fn=_fake_call(log=log))
    assert [x["provider"] for x in log] == [provider]
    assert "--nvidia" not in log[0]["user"]
    assert f"_{provider} · " in out


def test_research_is_the_openclaw_quest_then_LOCAL_synthesis():
    quests, log = [], []

    def quest(ticker, prompt):
        quests.append((ticker, prompt))
        return {"status": "OK", "reply": "{}", "latency_s": 3.0, "openclaw_cost_usd": 0.01}

    out = MR.route("research", ["mu"], call_fn=_fake_call(log=log), quest_fn=quest)
    assert quests and quests[0][0] == "MU" and "ticker MU" in quests[0][1]
    assert [x["provider"] for x in log] == ["local"]
    assert log[0]["ensure_reason"] == "telegram:/research"
    assert out.startswith("*Research* MU") and "_local · " in out


# ─────────────────────────────── /compare ───────────────────────────────────

def test_compare_freezes_THREE_rows_with_the_SAME_packet_hash(tmp_path):
    from backend.services import belief_state as B
    ledger = tmp_path / "predictions.jsonl"
    log = []
    texts = {p: f"reasoning.\nFOR: up\nAGAINST: down\nP_BEATS_SPY_5D: {v}"
             for p, v in (("local", "0.55"), ("deepseek", "0.40"), ("nvidia", "0.62"))}
    packet = {"ticker": "MU", "asof": "2026-09-26", "stock": {"ret_5d": 0.03}}
    text, res = MR.compare("MU", packet=packet, call_fn=_fake_call(texts, log),
                           ledger_path=ledger, receipt_root=tmp_path)
    assert [x["provider"] for x in log] == ["local", "deepseek", "nvidia"]
    assert len({x["user"] for x in log}) == 1           # the SAME packet to all three
    rows = B.read_predictions(ledger)
    assert len(rows) == 3
    assert sorted(r["specialist"] for r in rows) == [
        "compare:deepseek", "compare:local", "compare:nvidia"]
    assert len({r["input_snapshot_hash"] for r in rows}) == 1
    assert {r["inputs_used"]["packet_hash"] for r in rows} == {res["packet_hash"]}
    for r in rows:
        assert r["observable"] == "beats_benchmark" and r["benchmark"] == "SPY"
        assert r["horizon_days"] == 5
        assert r["raw_probability"] == r["probability"]
    assert {r["specialist"]: r["probability"] for r in rows}["compare:nvidia"] == 0.62
    rec = json.loads(open(res["receipt"], encoding="utf-8").read())
    assert res["receipt"].startswith(str(tmp_path / "model_routing" / "compare_"))
    assert rec["n_events"] == 1
    assert set(rec["by_provider"]) == {"local", "deepseek", "nvidia"}
    assert rec["by_provider"]["deepseek"]["cost_usd"] == pytest.approx(0.00042)
    assert rec["by_provider"]["nvidia"]["n_rows"] == 1
    assert rec["graded_by_provider"]["local"]["n_rows"] == 1
    assert rec["graded_by_provider"]["local"]["brier"] is None     # nothing graded yet
    assert "p=0.62" in text


def test_compare_writes_no_row_for_an_answer_without_a_probability(tmp_path):
    from backend.services import belief_state as B
    ledger = tmp_path / "p.jsonl"
    texts = {"local": "no idea", "deepseek": "P_BEATS_SPY_5D: 0.3",
             "nvidia": "P_BEATS_SPY_5D: 7"}                        # out of range: refused
    _, res = MR.compare("MU", packet={"t": 1}, call_fn=_fake_call(texts),
                        ledger_path=ledger, receipt_root=tmp_path)
    assert [r["specialist"] for r in B.read_predictions(ledger)] == ["compare:deepseek"]
    st = {a["provider"]: a["status"] for a in res["answers"]}
    assert st == {"local": "NO_PROBABILITY", "deepseek": "OK", "nvidia": "NO_PROBABILITY"}


def test_the_receipt_computes_brier_by_provider_once_rows_are_graded(tmp_path):
    ledger = tmp_path / "p.jsonl"
    rows = [{"prediction_id": "a", "specialist": "compare:local", "probability": 0.8,
             "outcome": 1}, {"prediction_id": "b", "specialist": "compare:local",
                             "probability": 0.4, "outcome": 0},
            {"prediction_id": "c", "specialist": "compare:nvidia", "probability": 0.5}]
    ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    g = MR._brier_by_provider(ledger)
    assert g["local"] == {"n_rows": 2, "n_graded": 2, "brier": pytest.approx(0.1)}
    assert g["nvidia"]["brier"] is None


def test_packet_is_point_in_time():
    import pandas as pd
    bars = pd.DataFrame({"symbol": ["MU"] * 3 + ["SPY"] * 3,
                         "date": ["2026-09-23", "2026-09-24", "2026-09-29"] * 2,
                         "close": [100.0, 110.0, 999.0, 500.0, 505.0, 1.0]})
    from datetime import date
    pkt = MR.build_packet("mu", asof=date(2026, 9, 25), bars=bars)
    assert pkt["stock"]["last_close"] == 110.0         # the 09-29 bar is not knowable
    assert pkt["last_bar"] == "2026-09-24"


# ─────────────────────────────── ensure / idle ──────────────────────────────

@pytest.fixture
def fake_server(tmp_path, monkeypatch):
    """A fake llama-server: state in a dict, the OS calls recorded."""
    monkeypatch.setattr(LS, "OWNER_FILE", tmp_path / "owner.json")
    state = {"listening": False, "pid": None, "starts": 0, "os_calls": []}

    def status():
        owner = LS._read_owner()
        mine = bool(state["listening"] and owner.get("pid") == state["pid"])
        return {"listening": state["listening"], "ready": state["listening"],
                "pid": state["pid"], "started_by_aegis": mine,
                "foreign": bool(state["listening"] and not mine), "detail": "fake"}

    def start(wait_s=90.0, bind=True):
        state["starts"] += 1
        state.update(listening=True, pid=4242)
        LS._write_owner({"pid": 4242, "started_utc": LS._now(), "owner_pid": os.getpid()})
        return {"ok": True, "action": "started", "pid": 4242, "status": status()}

    def run(cmd, **kw):
        state["os_calls"].append(list(cmd))
        if cmd[:2] == ["taskkill", "/PID"]:
            state.update(listening=False, pid=None)
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(LS, "status", status)
    monkeypatch.setattr(LS, "start", start)
    monkeypatch.setattr(LS, "health_ok", lambda timeout=2.0: state["listening"])
    monkeypatch.setattr(LS, "busy", lambda timeout=2.0: False)
    monkeypatch.setattr(LS, "pid_alive", lambda pid: False)
    monkeypatch.setattr(LS.qsp, "run", run)
    monkeypatch.setattr(LS.os, "kill", lambda pid, sig: run(["taskkill", "/PID", str(pid)]))
    monkeypatch.setattr(LS, "start_watchdog", lambda: True)
    return state


def test_ensure_starts_ONCE_and_records_what_it_was_started_for(fake_server):
    a = LS.ensure("telegram:/ask", wait_s=0)
    b = LS.ensure("telegram:/compare", wait_s=0)
    assert fake_server["starts"] == 1
    assert a["action"] == "started" and a["started_for"] == "telegram:/ask"
    assert b["action"] == "reused" and b["started_for"] == "telegram:/ask"
    assert b["requested_for"] == "telegram:/compare"
    owner = LS._read_owner()
    assert owner["uses"] == 2 and owner["last_used_for"] == "telegram:/compare"


def test_idle_watchdog_stops_BY_PID_after_the_idle_window(fake_server):
    LS.ensure("telegram:/ask", wait_s=0)
    t0 = LS._read_owner()["last_used_ts"]
    early = LS.idle_check(now=t0 + LS.IDLE_SHUTDOWN_S - 5)
    assert early["action"] == "none" and fake_server["listening"]
    late = LS.idle_check(now=t0 + LS.IDLE_SHUTDOWN_S + 5)
    assert late["action"] == "idle_stopped" and late["pid"] == 4242
    assert late["started_for"] == "telegram:/ask"
    kills = [c for c in fake_server["os_calls"] if c and c[0] == "taskkill"]
    assert kills and all(c[1] == "/PID" and c[2] == "4242" for c in kills)
    assert not any("/IM" in c for c in fake_server["os_calls"])
    assert not fake_server["listening"]


def test_only_the_STARTING_process_may_idle_stop(fake_server):
    LS.ensure("telegram:/ask", wait_s=0)
    owner = LS._read_owner()
    owner["owner_pid"] = os.getpid() + 1          # another Aegis instance started it
    LS._write_owner(owner)
    out = LS.idle_check(now=owner["last_used_ts"] + 10 * LS.IDLE_SHUTDOWN_S)
    assert out["action"] == "none" and out["reason"] == "not the starting process"
    assert fake_server["listening"]


def test_ensure_honours_the_operator_hold(fake_server):
    LS.hold_path().write_text("suite", encoding="utf-8")
    out = LS.ensure("telegram:/ask", wait_s=0)
    assert out["ok"] is False and out["reason"] == "OPERATOR_HOLD"
    assert fake_server["starts"] == 0


def test_a_foreign_server_is_used_but_never_adopted(fake_server):
    fake_server.update(listening=True, pid=999)          # nobody's owner note
    out = LS.ensure("telegram:/ask", wait_s=0)
    assert out["action"] == "reused" and out["started_for"] is None
    assert fake_server["starts"] == 0 and LS._read_owner() == {}


# ─────────────────────────────── NVIDIA ─────────────────────────────────────

class _FakeClient:
    def __init__(self, content, reasoning=None, usage=(120, 30)):
        msg = SimpleNamespace(content=content, reasoning_content=reasoning)
        self.resp = SimpleNamespace(
            choices=[SimpleNamespace(message=msg)],
            usage=SimpleNamespace(prompt_tokens=usage[0], completion_tokens=usage[1],
                                  prompt_cache_hit_tokens=0))
        self.sent = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.sent.append(kw)
        return self.resp


def test_nvidia_is_a_named_provider_that_parses_and_records_telemetry(tmp_path, monkeypatch):
    from backend.services import llm_telemetry as T
    tele = tmp_path / "calls.jsonl"
    monkeypatch.setenv(C.LLM_TELEMETRY_PATH_ENV, str(tele))
    fake = _FakeClient("MU beats SPY. P_BEATS_SPY_5D: 0.6")
    monkeypatch.setattr(LA, "_get_nvidia_client", lambda: fake)
    r = LA.call_named("nvidia", "sys", "user", purpose="compare:nvidia")
    assert r["ok"] and r["provider"] == "nvidia" and "0.6" in r["text"]
    assert r["model"] == C.MODEL_ROUTING_NVIDIA_MODEL
    assert r["tokens_in"] == 120 and r["tokens_out"] == 30
    assert r["cost_status"] == "LISTED" and r["cost_usd"] == 0.0   # NIM free tier, a LINE
    assert fake.sent[0]["messages"][0]["content"].endswith(LA._LANGUAGE_PIN)
    rows = T.read_calls(tele)
    assert len(rows) == 1 and rows[0]["provider"] == "nvidia"
    assert rows[0]["purpose"] == "compare:nvidia" and rows[0]["cost_usd"] == 0.0


def test_a_reasoning_models_answer_in_reasoning_content_is_not_lost(monkeypatch):
    monkeypatch.setattr(LA, "_get_nvidia_client", lambda: _FakeClient(None, "the answer"))
    assert LA.call_named("nvidia", "s", "u", purpose="t")["text"] == "the answer"


def test_nvidia_without_a_key_is_a_REFUSAL_not_a_fallback(monkeypatch):
    monkeypatch.setattr(LA, "_get_nvidia_client", lambda: None)
    r = LA.call_named("nvidia", "s", "u", purpose="t")
    assert r["ok"] is False and r["status"] == "NOT_CONFIGURED" and r["text"] is None


def test_deepseek_stays_the_sole_PRIMARY_and_nvidia_is_listed_as_adjudicator():
    assert LA.SOLE_PROVISIONED_PROVIDER == "deepseek"
    st = LA.provider_status()
    assert st["roles"] == {"deepseek": "primary", "nvidia": "adjudicator",
                           "local": "on_demand"}
    assert st["named"]["nvidia"]["role"] == "adjudicator"
    assert "nvidia" not in st["configured"]          # never a candidate for `active`


def test_cost_status_is_derived_from_the_price_table():
    assert LA.cost_status("deepseek-chat") == "LISTED"
    assert LA.cost_status("no-such-model-x") == "UNPRICED"
    for name, row in C.MODEL_ROUTING_PROVIDERS.items():
        assert row["cost_status"] == LA.cost_status(row["model"]), name


def test_local_route_goes_through_ensure_and_refuses_when_it_cannot_start(monkeypatch):
    seen = []
    monkeypatch.setattr(LS, "ensure", lambda reason, **k: seen.append(reason) or
                        {"ok": False, "action": "refused", "reason": "OPERATOR_HOLD"})
    r = LA.call_named("local", "s", "u", purpose="telegram:ask",
                      ensure_reason="telegram:/ask")
    assert seen == ["telegram:/ask"]
    assert r["status"] == "LOCAL_UNAVAILABLE" and "OPERATOR_HOLD" in r["error"]


# ─────────────────────────────── boot ───────────────────────────────────────

def test_nothing_starts_llama_server_at_boot():
    assert C.MODEL_ROUTING_START_AT_BOOT is False
    assert C.LAB_STARTS_MODEL_SERVER is C.MODEL_ROUTING_START_AT_BOOT
    assert C.MODEL_ROUTING_IDLE_SHUTDOWN_S == 900
    import inspect
    from scripts import night_run_until as N
    assert "MODEL_ROUTING_START_AT_BOOT" in inspect.getsource(N.Night.run)
    from desktop import aegis_desktop as AD
    assert "MODEL_ROUTING_START_AT_BOOT" in inspect.getsource(AD.main)


def test_the_telegram_agent_routes_through_the_table():
    from scripts import telegram_agent as TA
    for cmd in MR.ROUTES:
        assert TA.HANDLERS[cmd].__name__ == f"routed_{cmd}", cmd
