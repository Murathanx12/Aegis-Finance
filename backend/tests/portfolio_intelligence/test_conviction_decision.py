"""
Tests for conviction-lane decision capture (P1 #6 groundwork).

The decision LOG (`personal_decisions`) is immutable and forward-only:
timestamp = server-now (never backdated), late_entry flags after-the-fact logging,
corrections append via amends_id (update/delete forbidden by DB triggers). These
tests pin that contract on the endpoint, the read path, the v6 migration, and the CLI.
"""

import pytest
from fastapi.testclient import TestClient

from backend import db as db_module
from backend.db import get_connection, init_db, list_personal_decisions
from backend.main import app

_GOOD_RATIONALE = "Adding on the pullback; the offshore production ramp is on track and the thesis is intact."


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db = tmp_path / "conv.db"
    monkeypatch.setattr(db_module, "DB_PATH", db)
    init_db(db)
    return db


@pytest.fixture
def client():
    return TestClient(app)


def _payload(**over):
    p = {"ticker": "soc", "action": "add", "shares_delta": 100, "price": 6.8,
         "rationale": _GOOD_RATIONALE, "conviction": 4}
    p.update(over)
    return p


# ── endpoint happy path + read ────────────────────────────────────────────────


def test_log_decision_and_read_back(tmp_db, client):
    r = client.post("/api/pi/conviction/decision", json=_payload(thesis_tags=["offshore"], late_entry=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] > 0 and body["late_entry"] is True

    got = client.get("/api/pi/conviction/decisions").json()["decisions"]
    assert len(got) == 1
    d = got[0]
    assert d["ticker"] == "SOC"          # normalized upper
    assert d["action"] == "add" and d["shares_delta"] == 100
    assert d["late_entry"] is True
    assert d["thesis_tags"] == ["offshore"]
    assert d["timestamp"]                 # server-set


def test_timestamp_is_server_set_not_client(tmp_db, client):
    # A client-supplied timestamp is ignored (never backdated).
    r = client.post("/api/pi/conviction/decision",
                    json=_payload(timestamp="2000-01-01T00:00:00"))
    assert r.status_code == 200
    ts = client.get("/api/pi/conviction/decisions").json()["decisions"][0]["timestamp"]
    assert not ts.startswith("2000")


# ── validation → 422 ──────────────────────────────────────────────────────────


def test_short_rationale_rejected(tmp_db, client):
    r = client.post("/api/pi/conviction/decision", json=_payload(rationale="too short"))
    assert r.status_code == 422


def test_bad_conviction_rejected(tmp_db, client):
    r = client.post("/api/pi/conviction/decision", json=_payload(conviction=9))
    assert r.status_code == 422


def test_bad_action_rejected(tmp_db, client):
    r = client.post("/api/pi/conviction/decision", json=_payload(action="yolo"))
    assert r.status_code == 422


# ── corrections append (immutability) ─────────────────────────────────────────


def test_correction_appends_not_overwrites(tmp_db, client):
    first = client.post("/api/pi/conviction/decision", json=_payload()).json()["id"]
    second = client.post("/api/pi/conviction/decision",
                         json=_payload(shares_delta=120, amends_id=first,
                                       rationale="Correcting the share count on the prior SOC add; fat-fingered it."))
    assert second.status_code == 200
    decisions = client.get("/api/pi/conviction/decisions").json()["decisions"]
    assert len(decisions) == 2  # appended, original still present

    # The original row is immutable at the DB layer.
    conn = get_connection(tmp_db)
    try:
        with pytest.raises(Exception):
            conn.execute("UPDATE personal_decisions SET price = 0 WHERE id = ?", (first,))
            conn.commit()
    finally:
        conn.close()


# ── v6 migration ──────────────────────────────────────────────────────────────


def test_v6_fresh_db_has_late_entry_column(tmp_path):
    db = tmp_path / "v6.db"
    init_db(db)
    conn = get_connection(db)
    try:
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(personal_decisions)").fetchall()]
    finally:
        conn.close()
    assert "late_entry" in cols


# ── CLI: log a decision in one command ────────────────────────────────────────


def test_cli_logs_a_decision(tmp_db, monkeypatch):
    import scripts.log_conviction as cli

    monkeypatch.setattr(
        "sys.argv",
        ["log_conviction.py", "-t", "dkng", "-a", "trim", "-s", "-50", "-p", "31.2",
         "-c", "3", "-r", "Trimming into strength to manage single-name concentration after the run-up."],
    )
    rc = cli.main()
    assert rc == 0
    rows = list_personal_decisions(get_connection(tmp_db))
    assert len(rows) == 1 and rows[0]["ticker"] == "DKNG" and rows[0]["action"] == "trim"
