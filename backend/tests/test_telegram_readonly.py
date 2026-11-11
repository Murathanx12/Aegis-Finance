"""CH-05 R7: the Telegram agent's read-only table. Offline: the Telegram transport is a fake,
every model / broker / sim / subprocess entry point is booby-trapped, and receipts are
synthetic files in tmp_path. No message is sent anywhere."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from backend import config as C
from backend.services import telegram_bridge as TG
from backend.services import telegram_readonly as RO

NOW = datetime(2026, 11, 11, 4, 0, tzinfo=timezone.utc)
OWNER = "123456"


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


@pytest.fixture
def receipts(tmp_path):
    root = tmp_path / "optimus"
    (root / "system_status").mkdir(parents=True)
    (root / "system_status" / "status.json").write_text(json.dumps({
        "receipt": "system_status/1", "generated_utc": _iso(NOW - timedelta(hours=1)),
        "counts": {"OK": 30, "DEGRADED": 2, "DOWN": 1, "UNKNOWN": 1},
        "sections": {"learning": {"rows": [
            {"section": "learning", "name": "deepseek_envelope", "status": "DOWN", "detail": "EXHAUSTED"},
            {"section": "learning", "name": "learner", "status": "OK", "detail": "fine"}]},
            "tasks": {"rows": [{"section": "tasks", "name": "AegisAlerts", "status": "DEGRADED",
                                "detail": "funnel 35 d old"}]}},
        "undetermined": []}), encoding="utf-8")
    runs = root / "paper_accounts" / "fleet_manager" / "runs"
    runs.mkdir(parents=True)
    (runs / "run_20261110T143000Z.json").write_text(json.dumps({
        "pass": "preclose", "finished_utc": _iso(NOW - timedelta(hours=40)),
        "accounts": [{"role": "hack2", "equity": 101234.5, "n_positions": 2, "status": "ok",
                      "positions": [{"symbol": "NVDA"}, {"symbol": "ACN"}],
                      "stop_table": [{"symbol": "NVDA", "resting": True}]}]}), encoding="utf-8")
    return root


@pytest.fixture
def trapped(monkeypatch):
    """Anything that could spend, trade, start or shell out fails the test."""
    from backend.services import llm_analyzer as LA
    from backend.services import pc_broker as PB
    from backend.services import sim_session as SS

    def boom(*a, **k):
        raise AssertionError("a read-only reply reached a side-effecting entry point")

    monkeypatch.setattr(LA, "_call_llm", boom)
    monkeypatch.setattr(PB, "account", boom)
    monkeypatch.setattr(SS, "start", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    monkeypatch.setattr(subprocess, "run", boom)
    return boom


def test_status_reads_the_dashboard_receipt_worst_first(receipts, trapped):
    text = RO.answer("/status", root=receipts, now=NOW)["text"]
    lines = text.splitlines()
    assert lines[0] == "Status: 30 OK, 2 degraded, 1 down, 1 unknown"
    assert lines[1].startswith("DOWN learning/deepseek_envelope") and "DEGRADED tasks/AegisAlerts" in lines[2]
    assert "1.0 h old" in text and "STALE" not in text


def test_a_stale_or_missing_receipt_says_so(receipts, trapped, tmp_path):
    text = RO.answer("status", root=receipts, now=NOW + timedelta(hours=10))["text"]
    assert "STALE (limit 6 h)" in text
    assert "CANNOT DETERMINE" in RO.answer("status", root=tmp_path / "empty", now=NOW)["text"]
    pos = RO.answer("positions", root=receipts, now=NOW)["text"]
    assert "hack2: $101,234" in pos and "UNPROTECTED ['ACN']" in pos and "STALE (limit 26 h)" in pos


def test_budget_is_the_envelope_line(trapped):
    text = RO.budget_text(line_fn=lambda: "DEEPSEEK BUDGET OK: 2026-11 held $1.2 of $15.00 cap")
    assert text.startswith("DEEPSEEK BUDGET OK") and "monthly cap in config" in text

    def broken():
        raise RuntimeError("x")
    assert "CANNOT DETERMINE (RuntimeError)" in RO.budget_text(line_fn=broken)


def test_the_real_budget_line_reads_without_writing(tmp_path, monkeypatch, trapped):
    monkeypatch.setenv("AEGIS_DEEPSEEK_BUDGET_PATH", str(tmp_path / "absent" / "deepseek_local.json"))
    text = RO.answer("budget")["text"]
    assert "DEEPSEEK BUDGET" in text
    assert not (tmp_path / "absent").exists()


def test_books_nav_digest_answer_from_receipts_or_say_cannot(tmp_path, trapped):
    for cmd in ("books", "nav", "digest"):
        text = RO.answer(cmd, root=tmp_path, now=NOW)["text"]
        assert text and "failed" not in text.lower(), (cmd, text)
    assert "CANNOT DETERMINE" in RO.answer("books", root=tmp_path)["text"]


@pytest.mark.parametrize("text", ["buy NVDA", "/sim start 8", "/deep why is NVDA up", "/approve AP1",
                                  "hello there", "rm -rf /", "/research ACN", ""])
def test_everything_else_gets_a_plain_not_supported_reply(text, trapped):
    rep = RO.answer(text)
    assert rep["markdown"] is False
    assert rep["text"].startswith("Not supported") and "/status" in rep["text"]


def test_help_and_aliases():
    assert RO.answer("/help")["text"] == RO.help_text() == RO.answer("/start@aegis_bot")["text"]
    assert RO.command_of("/Status@aegis_bot extra") == "status"
    assert RO.command_of("health") == "status" and RO.command_of("spend") == "budget"


def test_the_table_is_exactly_the_read_commands():
    assert set(RO.COMMANDS) == {"status", "budget", "digest", "books", "nav", "positions"}
    assert set(RO.HANDLERS) == set(RO.COMMANDS) | {"help"} | set(RO.ALIASES)
    for forbidden in ("sim", "approve", "deny", "deep", "ask", "research", "broker", "pending"):
        assert forbidden not in RO.HANDLERS


# ───────────────────────────────────────────── through the real poller, fake transport

@pytest.fixture
def wire(monkeypatch, tmp_path, receipts):
    monkeypatch.setattr(TG, "OFFSET_PATH", tmp_path / "offset.json")
    monkeypatch.setattr(TG, "INBOX_PATH", tmp_path / "inbox.jsonl")
    monkeypatch.setattr(TG, "OUTBOX_PATH", tmp_path / "outbox.jsonl")
    monkeypatch.setattr(TG, "_INBOUND_TIMES", {"owner": [], "stranger": []})
    monkeypatch.setattr(TG, "_SUPPRESSED_NOTED_HOUR", {})
    monkeypatch.setattr(TG, "INBOUND_ROWS_SUPPRESSED", {"owner": 0, "stranger": 0})
    monkeypatch.setenv(TG.OWNER_ENV, OWNER)
    monkeypatch.setenv(TG.TOKEN_ENV, "synthetic-not-a-token")
    monkeypatch.setattr(C, "OPTIMUS_LEDGER_DIR", receipts)
    monkeypatch.setenv("AEGIS_DEEPSEEK_BUDGET_PATH", str(tmp_path / "budget" / "deepseek_local.json"))
    inbound: list[dict] = []
    sent: list[dict] = []

    def transport(method, payload=None, **kw):
        if method == "getUpdates":
            off = (payload or {}).get("offset") or 0
            return [u for u in inbound if u["update_id"] >= off]
        if method == "sendMessage":
            sent.append(payload)
            return {"message_id": len(sent)}
        if method == "answerCallbackQuery":
            return True
        raise AssertionError(f"unexpected Telegram method {method}")

    monkeypatch.setattr(TG, "_call", transport)

    def msg(uid, text, chat=OWNER):
        inbound.append({"update_id": uid, "message": {"message_id": uid, "chat": {"id": int(chat)},
                                                      "text": text}})
    return msg, sent


def test_an_owner_round_trip_through_poll(wire, trapped):
    msg, sent = wire
    msg(1, "/status")
    msg(2, "budget please")
    msg(3, "/sim start 8")
    TG.poll(RO.HANDLERS, text_handler=RO.text_reply, callback_handler=RO.callback_reply)
    assert [s["chat_id"] for s in sent] == [OWNER] * 3
    assert sent[0]["text"].startswith("Status: 30 OK") and "parse_mode" not in sent[0]
    assert "DEEPSEEK BUDGET" in sent[1]["text"]
    assert sent[2]["text"].startswith("Not supported: /sim")
    assert TG._offset() == 3


def test_a_stranger_gets_nothing(wire, trapped):
    msg, sent = wire
    msg(1, "/status", chat="999")
    TG.poll(RO.HANDLERS, text_handler=RO.text_reply, callback_handler=RO.callback_reply)
    assert sent == []


# ───────────────────────────────────────────── the agent's mode switch

def test_agent_defaults_to_read_only_and_refuses_an_unknown_mode(monkeypatch):
    from scripts import telegram_agent as A
    assert C.TELEGRAM_AGENT_MODE == "read_only" and A.agent_mode() == "read_only"
    h, t, cb = A.tables("read_only")
    assert h is RO.HANDLERS and t is RO.text_reply and cb is RO.callback_reply
    assert A.tables("full")[0] is A.HANDLERS
    monkeypatch.setattr(C, "TELEGRAM_AGENT_MODE", "yolo")
    assert A.agent_mode() is None
    monkeypatch.setattr(A.TG, "claim_owner", lambda: pytest.fail("must not claim"))
    assert A.main(["--once"]) == 2


def test_read_only_never_claims_an_owner(monkeypatch):
    from scripts import telegram_agent as A
    monkeypatch.delenv(TG.OWNER_ENV, raising=False)
    monkeypatch.setattr(A.TG, "claim_owner", lambda: pytest.fail("must not claim"))
    monkeypatch.setattr(A.TG, "status", lambda: pytest.fail("must not probe"))
    assert A.main(["--once"]) == 2


def test_persist_owner_writes_the_declared_keys_file(tmp_path, monkeypatch):
    keys = tmp_path / "declared.env"
    keys.write_text("OTHER=1\n", encoding="utf-8")
    monkeypatch.setattr(TG._cfg, "DOTENV_PATH", keys)
    monkeypatch.setattr(TG._cfg, "PROJECT_ROOT", tmp_path / "clone")
    monkeypatch.setenv(TG.OWNER_ENV, "")            # recorded, so the write below is undone
    TG._persist_owner("42")
    assert keys.read_text(encoding="utf-8").splitlines() == ["OTHER=1", f"{TG.OWNER_ENV}=42"]
    assert not (tmp_path / "clone" / ".env").exists()
