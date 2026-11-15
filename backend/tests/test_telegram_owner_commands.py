"""CH-48 slice 1: /status /books /note /help from the owner's chat only. Offline: synthetic
receipts under tmp_path, an injected sender, no network, no model, no subprocess."""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend import config as C
from backend.services import telegram_bridge as TG
from backend.services import telegram_owner_commands as OC
from backend.services import telegram_readonly as RO

OWNER = "424242"
NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
REPO = Path(__file__).resolve().parents[2]

HEAD = [
    "RESULTS as of the marks (run RUNID): 3 of 9 strategy accounts are ahead of SPY.",
    "LEADER book_a: +4.00% vs SPY -1.00% = +5.00 pp, 30 sessions, OBSERVED.",
    "NEXT: book_b +3.00 pp (20 s, OBSERVED)",
    "WHAT RAISES IT: book_a -> EARLY_EVIDENCE at 60 sessions.",
    "BEHIND: 6 of 9; worst mirror book_z -9.00 pp.",
    "CLAIMS PROMOTED: none",
]


def _iso(dt):
    return dt.isoformat(timespec="seconds")


def _status(root, *, age_h=1.0, down=("alpha", "beta")):
    d = root / "system_status"
    d.mkdir(parents=True, exist_ok=True)
    rows = [{"section": "tasks", "name": n, "status": "DOWN",
             "detail": r"secret C:\Users\x\file.py detail"} for n in down]
    rows.append({"section": "tasks", "name": "fine", "status": "OK", "detail": "ok"})
    (d / "status.json").write_text(json.dumps({
        "receipt": "system_status/1", "generated_utc": _iso(NOW - timedelta(hours=age_h)),
        "counts": {"OK": 10, "DEGRADED": 2, "DOWN": len(down), "UNKNOWN": 1},
        "sections": {"tasks": {"rows": rows}}, "undetermined": []}), encoding="utf-8")


def _voice(root, stamp="2026-05-31T120000Z", head=HEAD):
    d = root / "paper_accounts"
    d.mkdir(parents=True, exist_ok=True)
    body = ["# RESULTS VOICE", "", "Licence PRODUCT_EXPERIMENT; Receipts: `C:\\x\\roi.json`.", ""]
    body += [h.replace("RUNID", stamp) for h in head]
    body += ["", "## Families", "RESULTS-like table row that must not appear"]
    (d / f"results_voice_{stamp}.md").write_text("\n".join(body), encoding="utf-8")


def _msg(text, chat=OWNER):
    return {"message_id": 1, "chat": {"id": int(chat)}, "text": text}


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "optimus"
    root.mkdir()
    sent: list[tuple[str, str]] = []
    lim = OC.RateLimiter()

    def go(text, chat=OWNER, now=NOW):
        return OC.dispatch(_msg(text, chat), data_root=root, now=now, owner_chat_id=OWNER,
                           send=lambda c, t: sent.append((c, t)), limiter=lim)
    return root, sent, go


def _journal(root):
    p = OC.journal_path(root)
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def test_status_names_both_down_rows_counts_and_age(env):
    root, sent, go = env
    _status(root)
    r = go("/status")
    assert r.startswith("Systems: OK 10, DEGRADED 2, DOWN 2, UNKNOWN 1")
    assert "DOWN tasks/alpha" in r and "DOWN tasks/beta" in r and "fine" not in r
    assert "1.0 h old" in r and "STALE" not in r
    assert "C:\\" not in r and "secret" not in r          # row detail (paths) is never sent
    assert sent == [(OWNER, r)]


def test_status_stale_and_missing_say_so(env):
    root, _, go = env
    r = go("/status")
    assert "CANNOT DETERMINE" in r and "NOT 'all good'" in r
    _status(root, age_h=30)
    assert "STALE" in go("/status")


def test_books_headline_verbatim_with_stamp_age_and_claims_last(env):
    root, _, go = env
    _voice(root)
    r = go("/books")
    lines = r.split("\n")
    assert "2026-05-31T120000Z" in lines[0] and "24.0 h old" in lines[1]
    for h in HEAD[:5]:
        assert h.replace("RUNID", "2026-05-31T120000Z") in lines
    assert lines[-1] == "CLAIMS PROMOTED: none"
    assert "table row" not in r and "C:\\" not in r


def test_books_stale_and_missing(env):
    root, _, go = env
    assert "CANNOT DETERMINE" in go("/books")
    _voice(root, stamp="2026-05-20T000000Z")
    assert "STALE" in go("/books")


def test_books_picks_newest_run(env):
    root, _, go = env
    _voice(root, stamp="2026-05-01T000000Z")
    _voice(root, stamp="2026-05-31T000000Z")
    assert "run 2026-05-31T000000Z" in go("/books")


def test_help_lists_the_three(env):
    _, _, go = env
    r = go("/help")
    assert all(c in r for c in ("/status", "/books", "/note"))


def test_note_writes_one_inbox_row_readable_by_the_cli(env):
    root, sent, go = env
    r = go("/note remember to review the PR\nsecond line")
    from scripts import owner_inbox as IB
    rows = [json.loads(x) for x in IB.inbox_path(root).read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1 and rows[0]["source"] == "telegram" and rows[0]["status"] == "unread"
    assert rows[0]["text"] == "remember to review the PR\nsecond line"
    assert rows[0]["id"] in r
    out = subprocess.run([sys.executable, "-m", "scripts.owner_inbox", "list", "--unread",
                          "--data-root", str(root)], cwd=REPO, capture_output=True, text=True)
    assert out.returncode == 0 and "remember to review the PR" in out.stdout


def test_note_empty_too_long_and_journal_has_no_text(env):
    root, _, go = env
    assert "Usage" in go("/note")
    assert not (root / "owner_inbox" / "notes.jsonl").exists()
    long = "x" * (C.OWNER_INBOX_MAX_CHARS + 1)
    assert "NOT saved" in go("/note " + long)
    assert not (root / "owner_inbox" / "notes.jsonl").exists()
    go("/note SECRETNOTEWORD hello")
    raw = OC.journal_path(root).read_text(encoding="utf-8")
    assert "SECRETNOTEWORD" not in raw and OWNER not in raw
    last = _journal(root)[-1]
    assert set(last) == {"t", "cmd", "chat_sha8", "sender_ok", "outcome", "reply_chars"}
    assert last["cmd"] == "note" and last["sender_ok"] is True and last["reply_chars"] > 0


def test_other_chat_gets_nothing_and_a_refused_row_and_no_note(env):
    root, sent, go = env
    _status(root)
    for t in ("/status", "/books", "/note hostile", "/help"):
        assert go(t, chat="777") is None
    assert sent == []
    j = _journal(root)
    assert len(j) == 4 and all(x["sender_ok"] is False and x["outcome"] == "refused" for x in j)
    assert not (root / "owner_inbox").exists()
    assert "777" not in OC.journal_path(root).read_text(encoding="utf-8")


def test_no_owner_configured_refuses_everyone(tmp_path):
    assert OC.dispatch(_msg("/status"), data_root=tmp_path, now=NOW, owner_chat_id=None,
                       limiter=OC.RateLimiter()) is None


def test_other_text_is_not_ours(env):
    _, sent, go = env
    for t in ("status", "/sim start 8", "/notes x", "hello", "/deep q"):
        assert go(t) is None
    assert sent == []


def test_rate_limits_per_chat(env, monkeypatch):
    root, _, go = env
    monkeypatch.setattr(C, "TELEGRAM_OWNER_CMD_MAX_PER_H", 4)
    monkeypatch.setattr(C, "TELEGRAM_OWNER_NOTE_MAX_PER_H", 2)
    assert "saved" in go("/note a") and "saved" in go("/note b")
    assert "Rate limit" in go("/note c")                   # note cap hit; 3 command slots used
    assert go("/help").startswith("AEGIS")                 # 4th command slot
    assert "Rate limit" in go("/help")                     # command cap
    assert len((root / "owner_inbox" / "notes.jsonl").read_text().splitlines()) == 2
    assert go("/help", now=NOW + timedelta(hours=1, seconds=1)).startswith("AEGIS")


def test_reply_is_capped_with_omitted_count(env):
    root, _, go = env
    _status(root, down=tuple(f"task_{i:03d}" for i in range(400)))
    r = go("/status")
    assert len(r) <= C.TELEGRAM_OWNER_REPLY_MAX_CHARS < 4096
    assert "more line(s) omitted" in r


def test_handler_wiring_through_the_real_poller(env, monkeypatch, tmp_path):
    root, _, _ = env
    _status(root)
    monkeypatch.setattr(C, "OPTIMUS_LEDGER_DIR", root)
    monkeypatch.setenv(TG.OWNER_ENV, OWNER)
    monkeypatch.setenv(TG.TOKEN_ENV, "synthetic-not-a-token")
    for n, v in (("OFFSET_PATH", tmp_path / "off.json"), ("INBOX_PATH", tmp_path / "in.jsonl"),
                 ("OUTBOX_PATH", tmp_path / "out.jsonl")):
        monkeypatch.setattr(TG, n, v)
    monkeypatch.setattr(TG, "_INBOUND_TIMES", {"owner": [], "stranger": []})
    monkeypatch.setattr(OC, "_LIMITER", OC.RateLimiter())
    inbound = [{"update_id": 1, "message": _msg("/status")},
               {"update_id": 2, "message": _msg("/note via poller")},
               {"update_id": 3, "message": _msg("/status", chat="9")}]
    sent = []

    def transport(method, payload=None, **kw):
        if method == "getUpdates":
            return [u for u in inbound if u["update_id"] >= ((payload or {}).get("offset") or 0)]
        sent.append(payload)
        return {"message_id": 1}
    monkeypatch.setattr(TG, "_call", transport)
    TG.poll(RO.HANDLERS, text_handler=RO.text_reply, callback_handler=RO.callback_reply)
    assert [s["chat_id"] for s in sent] == [OWNER, OWNER]
    assert sent[0]["text"].startswith("Systems:") and "Note saved" in sent[1]["text"]
    assert "parse_mode" not in sent[0]


def test_module_has_no_way_to_start_anything():
    """Static audit: no subprocess/os/socket/model/broker/sim import, no exec/eval/open call."""
    src = (REPO / "backend" / "services" / "telegram_owner_commands.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mods.add((n.module or "").split(".")[0])
            mods |= {f"{n.module}.{a.name}" for a in n.names}
    banned = {"subprocess", "os", "socket", "requests", "urllib", "http", "ctypes", "asyncio",
              "backend.services.llm_analyzer", "backend.services.pc_broker",
              "backend.services.sim_session", "backend.services.telegram_bridge"}
    assert not (mods & banned), mods & banned
    calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert not (calls & {"exec", "eval", "compile", "__import__"})
    assert {m for m in mods if m.startswith("scripts")} <= {"scripts", "scripts.owner_inbox"}
