"""C0: receipts that can go red.

Dates derive from `date.today()` (protocol item 5): a fixture pinned to a
calendar moment fails the day after it passes.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.services import accrual_canary as ac


def _write(tmp_path, days_ago_list, today=None):
    p = tmp_path / "predictions.jsonl"
    today = today or date.today()
    with p.open("w", encoding="utf-8") as f:
        for d in days_ago_list:
            made = (today - timedelta(days=d)).isoformat() + "T12:00:00Z"
            f.write(json.dumps({"made_at": made, "p": 0.5}) + "\n")
    return p, today


def test_three_quiet_days_is_degraded(tmp_path):
    p, today = _write(tmp_path, [10, 9, 8])
    r = ac.forecast_accrual(p, today=today, window_days=3)
    assert r["status"] == "DEGRADED"
    assert "0 new rows" in r["reason"]


def test_a_row_yesterday_is_ok(tmp_path):
    p, today = _write(tmp_path, [1])
    assert ac.forecast_accrual(p, today=today, window_days=3)["status"] == "ok"


def test_missing_made_at_is_unknown_not_ok(tmp_path):
    p = tmp_path / "predictions.jsonl"
    p.write_text(json.dumps({"p": 0.5}) + "\n", encoding="utf-8")
    assert ac.forecast_accrual(p, today=date.today())["status"] == "UNKNOWN"


def test_absent_ledger_is_unknown(tmp_path):
    r = ac.forecast_accrual(tmp_path / "nope.jsonl", today=date.today())
    assert r["status"] == "UNKNOWN"


def test_only_the_tail_is_read_and_still_sees_the_newest_row(tmp_path):
    p = tmp_path / "predictions.jsonl"
    today = date.today()
    with p.open("w", encoding="utf-8") as f:
        for _ in range(2000):
            f.write(json.dumps({"made_at": "2020-01-01T00:00:00Z",
                                "pad": "x" * 200}) + "\n")
        f.write(json.dumps({"made_at": today.isoformat() + "T01:00:00Z"}) + "\n")
    r = ac.forecast_accrual(p, today=today, tail_bytes=4096)
    assert r["status"] == "ok"
    assert r["rows_by_day"] == {today.isoformat(): 1}


def test_stuck_counter():
    assert ac.stuck_counter([2, 2, 2, 2, 2, 2]) is True
    assert ac.stuck_counter([2, 3, 2, 2, 2]) is False
    assert ac.stuck_counter([]) is False


def test_n_considered_stuck_is_degraded_and_prints_the_funnel_beside_it(tmp_path):
    d = tmp_path / "decisions"
    d.mkdir()
    today = date.today()
    for i in range(6):
        day = (today - timedelta(days=i)).isoformat()
        (d / f"{day}.json").write_text(json.dumps(
            {"roi_ranking": {"n_considered": 2}}), encoding="utf-8")
    funnel = tmp_path / "funnel.json"
    funnel.write_text(json.dumps({"candidates": [{"ticker": f"T{i}"}
                                                 for i in range(25)]}),
                      encoding="utf-8")
    r = ac.n_considered_row(d, funnel)
    assert r["status"] == "DEGRADED"
    assert "funnel n_candidates 25" in r["line"]
    assert r["values"] == [2] * 6


def test_n_considered_moving_is_ok(tmp_path):
    d = tmp_path / "decisions"
    d.mkdir()
    today = date.today()
    for i, v in enumerate([2, 2, 25, 24, 25, 3]):
        day = (today - timedelta(days=6 - i)).isoformat()
        (d / f"{day}.json").write_text(json.dumps(
            {"roi_ranking": {"n_considered": v}}), encoding="utf-8")
    assert ac.n_considered_row(d, None)["status"] == "ok"


def test_collector_that_never_wrote_is_degraded(tmp_path):
    db = tmp_path / "pi.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE pit_observations (id INTEGER PRIMARY KEY, key TEXT,"
                " as_of TEXT, observed_at TEXT, value REAL, payload TEXT,"
                " source TEXT, revision INTEGER)")
    now = datetime.now(timezone.utc).isoformat()
    con.execute("INSERT INTO pit_observations (key, as_of, observed_at, source,"
                " revision) VALUES ('pead_score:AAA', ?, ?, 's', 0)",
                (now[:10], now))
    con.commit()
    con.close()
    rows = {r["collector"]: r for r in ac.collector_liveness(db, today=date.today())}
    assert rows["pead"]["status"] == "ok" and rows["pead"]["n_rows_7d"] == 1
    assert rows["congress"]["status"] == "DEGRADED"
    assert "NEVER" in rows["congress"]["reason"]


# ── OpenClaw: every call is a telemetry row; an empty log is red ─────────────

_ENVELOPE = {
    "runId": "r1", "status": "ok",
    "result": {"payloads": [{"text": '{"ticker": "AAA", "probability_1d": 0.52}'}],
               "meta": {"agentMeta": {
                   "model": "deepseek-flash",
                   "usage": {"input": 30000, "output": 2000, "cacheRead": 6000,
                             "reasoningTokens": 1500},
                   "costUsd": 0.0115,
                   "terminalReceipt": {"effective": {
                       "responseModel": "deepseek-flash"}}}}}}


@pytest.fixture
def tele(monkeypatch, tmp_path):
    from backend import config as C
    path = tmp_path / "llm_calls.jsonl"
    monkeypatch.setenv(C.LLM_TELEMETRY_PATH_ENV, str(path))
    return path


def _fake_run(stdout, rc=0):
    def run(*a, **k):
        return subprocess.CompletedProcess(a[0] if a else [], rc, stdout, "")
    return run


def _rows(path):
    from backend.services import llm_telemetry as LT
    return LT.read_calls(path)


def test_an_openclaw_call_writes_exactly_one_priced_row(monkeypatch, tmp_path, tele):
    from backend.services import openclaw_client as OC
    monkeypatch.setattr(subprocess, "run", _fake_run(json.dumps(_ENVELOPE)))
    msg = tmp_path / "m.md"
    msg.write_text("hello", encoding="utf-8")
    r = OC.agent(str(msg), model="deepseek/deepseek-flash", purpose="u_forecast")
    assert r["status"] == "OK"
    assert r["reply"].startswith('{"ticker"')
    rows = _rows(tele)
    assert len(rows) == 1
    row = rows[0]
    assert row["purpose"] == "u_forecast"
    assert row["meta"]["via"] == "openclaw"
    assert row["model"] == "deepseek-flash"
    assert row["tokens_in"] == 30000 and row["cached_tokens"] == 6000
    assert row["cost_usd"] is not None and row["cost_usd"] > 0
    assert row["meta"]["openclaw_cost_usd"] == pytest.approx(0.0115)


def test_default_purpose_starts_with_openclaw(monkeypatch, tmp_path, tele):
    from backend.services import openclaw_client as OC
    monkeypatch.setattr(subprocess, "run", _fake_run(json.dumps(_ENVELOPE)))
    msg = tmp_path / "m.md"
    msg.write_text("hello", encoding="utf-8")
    OC.agent(str(msg))
    assert _rows(tele)[0]["purpose"].startswith("openclaw:")


def test_an_empty_log_is_a_row_and_turns_the_health_row_red(monkeypatch, tmp_path, tele):
    from backend.services import openclaw_client as OC
    empty = json.loads(json.dumps(_ENVELOPE))
    empty["result"]["payloads"] = [{"text": ""}]
    empty["result"]["meta"]["agentMeta"]["usage"] = {}
    monkeypatch.setattr(subprocess, "run", _fake_run(json.dumps(empty)))
    msg = tmp_path / "m.md"
    msg.write_text("quest", encoding="utf-8")
    r = OC.agent(str(msg), purpose="openclaw:q2_power_bottleneck")
    assert r["status"] == "EMPTY_LOG"
    rows = _rows(tele)
    assert len(rows) == 1 and rows[0]["meta"]["status"] == "EMPTY_LOG"
    # no usage came back: the spend is UNKNOWN, never a zero
    assert rows[0]["cost_usd"] is None
    h = ac.openclaw_telemetry(tele, today=datetime.now(timezone.utc).date())
    assert h["status"] == "DEGRADED"
    assert "EMPTY_LOG" in h["reason"]


def test_no_openclaw_calls_is_idle_not_red(tele):
    h = ac.openclaw_telemetry(tele, today=date.today())
    assert h["status"] == "IDLE"


# ── the session row is written at START, so a crash is visible ───────────────

def test_a_crashed_session_is_visible_as_started_with_no_end(monkeypatch, tmp_path):
    from backend.services import sim_session as SS
    monkeypatch.setattr(SS, "STATE_DIR", tmp_path)
    monkeypatch.setattr(SS, "SESSION_PATH", tmp_path / "session.json")
    monkeypatch.setattr(SS, "STOP_FLAG", tmp_path / "STOP_REQUESTED")
    monkeypatch.setattr(SS, "HISTORY_PATH", tmp_path / "sessions.jsonl")
    s = SS.start(hours=6, launcher=lambda sess: 424242)
    # cycle 1 checkpoints, then the process dies: no finish() is ever called
    SS.record_cycle(1, {"units": {}, "elapsed_s": 1.0})
    hist = SS.history()
    assert len(hist) == 1
    assert hist[0]["id"] == s["id"]
    assert hist[0]["state"] == "STARTED"
    assert hist[0].get("ended") is None


def test_a_finished_session_folds_to_one_history_row(monkeypatch, tmp_path):
    from backend.services import sim_session as SS
    monkeypatch.setattr(SS, "STATE_DIR", tmp_path)
    monkeypatch.setattr(SS, "SESSION_PATH", tmp_path / "session.json")
    monkeypatch.setattr(SS, "STOP_FLAG", tmp_path / "STOP_REQUESTED")
    monkeypatch.setattr(SS, "HISTORY_PATH", tmp_path / "sessions.jsonl")
    monkeypatch.setattr(SS, "pid_alive", lambda pid: True)
    SS.start(hours=6, launcher=lambda sess: 424242)
    SS.finish("STOPPED", "stop requested", {"final_cycle": 2})
    hist = SS.history()
    assert len(hist) == 1 and hist[0]["state"] == "STOPPED"
    assert hist[0]["ended"]


def test_health_composes_every_row_and_never_raises():
    r = ac.health()
    for k in ("forecast_accrual", "collectors", "openclaw", "n_considered"):
        assert k in r
    assert r["status"] in ("ok", "DEGRADED")


# ── the endpoint carries the row, and a quiet ledger pages by NAME ───────────

def test_health_full_carries_the_accrual_row_and_names_a_quiet_ledger(monkeypatch):
    """C0 step 4: assert the row EXISTS (never that it is ok -- protocol item 5:
    whether it is ok depends on the day the suite runs). A DEGRADED forecast
    accrual must reach the top-level reasons with its name, or the prod
    monitor never sees the thirteen quiet days that motivated this row."""
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)
    body = client.get("/api/health/full").json()
    row = body["accrual_canary"]
    assert row["status"] in ("ok", "DEGRADED", "UNKNOWN")
    assert "forecast_accrual" in row

    fake = {"status": "DEGRADED", "degraded_reasons": ["x"],
            "forecast_accrual": {"status": "DEGRADED",
                                 "reason": "0 new rows in the last 3 day(s)"},
            "openclaw": {"status": "IDLE"}, "n_considered": {"status": "ok"},
            "collectors": []}
    monkeypatch.setattr(ac, "health", lambda **k: fake)
    body = client.get("/api/health/full").json()
    assert any(r.startswith("forecast_accrual:") and "0 new rows" in r
               for r in body["degraded_reasons"]), body["degraded_reasons"]
