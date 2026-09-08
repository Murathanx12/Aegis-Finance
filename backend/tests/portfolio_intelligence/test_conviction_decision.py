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


# ── H2: the journal → thesis bridge ───────────────────────────────────────────
# A conviction row with a rationale and a 1-5 conviction can be REMEMBERED and
# cannot be GRADED. These tests pin the bridge that turns the same decision into
# a `Thesis` (the execution repo's schema, verbatim) and a PENDING row in the
# four-counterfactual decision log — and, just as importantly, pin that a row
# WITHOUT those fields is told so at the moment it is written.


@pytest.fixture
def isolated_journal(tmp_path, monkeypatch):
    from backend.services import decision_log as dl
    from backend.services import human_thesis as ht

    monkeypatch.setattr(ht, "HUMAN_THESIS_LOG", tmp_path / "theses.jsonl")
    monkeypatch.setattr(ht, "HUMAN_BOOK_LOG", tmp_path / "book.jsonl")
    monkeypatch.setattr(dl, "DECISION_LOG_PATH", tmp_path / "decisions.jsonl")
    monkeypatch.setattr(dl, "DECISION_GRADE_LOG_PATH", tmp_path / "grades.jsonl")
    return tmp_path


def _future_iso(days: int = 30) -> str:
    """Derived from `today` — a literal date fails the day after it passes."""
    import datetime as _dt

    return (_dt.datetime.now(_dt.timezone.utc)
            + _dt.timedelta(days=days)).isoformat(timespec="seconds")


def test_a_decision_without_a_falsifier_says_it_cannot_be_graded(
        tmp_db, client, isolated_journal):
    body = client.post("/api/pi/conviction/decision", json=_payload()).json()
    assert body["thesis"]["status"] == "NOT_CREATED"
    assert "GRADED" in body["thesis"]["reason"]
    assert "falsifier" in body["thesis"]["missing"]
    assert not (isolated_journal / "theses.jsonl").exists()


def test_a_decision_with_the_h2_fields_opens_a_thesis_and_a_pending_row(
        tmp_db, client, isolated_journal):
    body = client.post("/api/pi/conviction/decision", json=_payload(
        ticker="NVDA", action="enter", direction="up", expected_move=0.06,
        catalyst="Q3 FY27 print", catalyst_at_utc=_future_iso(30),
        falsifier="Q4 revenue guide at or below $104bn, or GM guide below 74%",
        horizon_sessions=63, min_normal_hold_sessions=21,
        loss_budget_ref="thesis_3m_v1")).json()
    t = body["thesis"]
    assert t["status"] == "CREATED", t
    assert t["brain"] == "human:murat"
    assert (t["horizon_sessions"], t["min_normal_hold_sessions"],
            t["loss_budget_ref"]) == (63, 21, "thesis_3m_v1")
    assert t["decision_row_id"] and t["resolves_on"]
    assert (isolated_journal / "theses.jsonl").exists()
    assert (isolated_journal / "decisions.jsonl").exists()


def test_an_immutable_decision_row_survives_a_refused_thesis(
        tmp_db, client, isolated_journal):
    """The decision row is written FIRST. Losing it because a falsifier was 14
    characters long would be the write path punishing the honest half."""
    r = client.post("/api/pi/conviction/decision", json=_payload(
        direction="up", expected_move=0.06, catalyst="a print",
        catalyst_at_utc=_future_iso(10), falsifier="too short"))
    assert r.status_code == 200
    assert r.json()["thesis"]["status"] == "REFUSED"
    assert "falsifier" in r.json()["thesis"]["reason"]
    conn = get_connection(tmp_db)
    try:
        assert len(list_personal_decisions(conn)) == 1
    finally:
        conn.close()


def test_a_backdated_thesis_is_refused_but_the_decision_stands(
        tmp_db, client, isolated_journal):
    r = client.post("/api/pi/conviction/decision", json=_payload(
        direction="up", expected_move=0.06, catalyst="already happened",
        catalyst_at_utc=_future_iso(-5),
        falsifier="Q4 revenue guide at or below $104bn, or GM below 74%"))
    assert r.json()["thesis"]["status"] == "REFUSED"
    assert "memory" in r.json()["thesis"]["reason"].lower()
