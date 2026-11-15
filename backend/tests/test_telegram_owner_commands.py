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


def test_help_keeps_every_old_command_and_start_matches(env):
    _, _, go = env
    r = go("/help")
    assert all(c in r for c in ("/status", "/books", "/note", "/budget", "/digest", "/nav", "/positions"))
    assert r == RO.help_text() == RO.answer("/start")["text"]


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
    assert set(last) == {"t", "cmd", "sender_ok", "outcome", "reply_chars"}
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


def test_forwarded_note_is_refused_and_journaled(env):
    root, _, go = env
    for key in ("forward_origin", "forward_from", "forward_from_chat"):
        m = _msg("/note forwarded text")
        m[key] = {"x": 1}
        r = OC.dispatch(m, data_root=root, now=NOW, owner_chat_id=OWNER, limiter=OC.RateLimiter())
        assert "Forwarded" in r
    assert not (root / "owner_inbox").exists()
    assert [x["outcome"] for x in _journal(root)] == ["refused_forwarded"] * 3


def test_multi_slash_parses_the_same_in_both_places(env):
    root, _, go = env
    assert OC.command_of("//note x") == "note" == RO.command_of("//note x")
    assert "saved" in go("//note two slashes")
    assert OC.command_of("///status") == "status"


def test_failed_notes_do_not_use_the_note_slot(env, monkeypatch):
    root, _, go = env
    monkeypatch.setattr(C, "TELEGRAM_OWNER_NOTE_MAX_PER_H", 2)
    for _ in range(5):
        go("/note")                                        # usage, nothing saved
        go("/note " + "x" * (C.OWNER_INBOX_MAX_CHARS + 1))  # refused
    assert "saved" in go("/note a") and "saved" in go("/note b")
    assert "Rate limit" in go("/note c")


def test_cap_counts_utf16_units_and_cuts_a_long_first_line(env):
    root, _, go = env
    text = "\n".join(chr(0x1F600) * 100 for _ in range(60))        # 2 units per emoji
    r = OC.cap_reply(text)
    assert OC.u16(r) <= C.TELEGRAM_OWNER_REPLY_MAX_CHARS and "omitted" in r
    r2 = OC.cap_reply("y" * 9000)
    assert OC.u16(r2) <= C.TELEGRAM_OWNER_REPLY_MAX_CHARS


# ---- static audit: nothing on the path of the four commands can start or call anything ----

_BANNED_MODS = {"subprocess", "socket", "requests", "httpx", "urllib", "http", "ctypes", "asyncio",
                "importlib", "multiprocessing", "threading_start"}
_BANNED_PREFIX = ("backend.services.llm_analyzer", "backend.services.pc_broker",
                  "backend.services.sim_session", "backend.services.model_routing",
                  "backend.services.provider_budget", "backend.services.telegram_cockpit")
_BANNED_NAMES = {"exec", "eval", "__import__", "system", "popen", "Popen", "run", "call",
                 "check_output", "startfile", "spawn", "create_subprocess_exec", "import_module"}
#: the only things the owner handler may take from the bridge: reading the configured owner id
_BRIDGE_ALLOWED = {"owner_chat_id"}


def _audit(tree, label):
    problems = []
    bridge_aliases = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name.split(".")[0] in _BANNED_MODS or a.name.startswith(_BANNED_PREFIX):
                    problems.append(f"{label}: import {a.name}")
        elif isinstance(n, ast.ImportFrom):
            m = n.module or ""
            for a in n.names:
                full = f"{m}.{a.name}"
                if m.split(".")[0] in _BANNED_MODS or full.startswith(_BANNED_PREFIX):
                    problems.append(f"{label}: from {m} import {a.name}")
                if full == "backend.services.telegram_bridge":
                    bridge_aliases.add(a.asname or a.name)
        elif isinstance(n, ast.Call):
            f = n.func
            name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
            if name in _BANNED_NAMES:
                problems.append(f"{label}: call {name}")
        elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in bridge_aliases:
            if n.attr not in _BRIDGE_ALLOWED:
                problems.append(f"{label}: bridge attribute {n.attr}")
    return problems


def _func(tree, name):
    return next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)


def test_no_path_from_the_four_commands_can_start_or_call_anything():
    oc = ast.parse((REPO / "backend/services/telegram_owner_commands.py").read_text(encoding="utf-8"))
    ro = ast.parse((REPO / "backend/services/telegram_readonly.py").read_text(encoding="utf-8"))
    ib = ast.parse((REPO / "scripts/owner_inbox.py").read_text(encoding="utf-8"))
    problems = _audit(oc, "owner_commands") + _audit(_func(ro, "_owner_handler"), "readonly._owner_handler") \
        + _audit(_func(ro, "help_text"), "readonly.help_text") + _audit(ib, "owner_inbox")
    assert problems == []
    # the audit itself bites: a tree with a banned call is reported
    assert _audit(ast.parse("import subprocess; subprocess.run([1]); from backend.services import telegram_bridge as T; T.send(2)"), "t")
    # and the owner handler is what HANDLERS routes the four commands to
    assert all(RO.HANDLERS[c].__name__ == f"owner_{c}" for c in RO.OWNER_COMMANDS)


def test_list_strips_control_and_bidi_characters_and_prints_source(tmp_path, capsys):
    from scripts import owner_inbox as IB
    bad = "a" + chr(27) + "[31mb" + chr(7) + chr(0x202E) + "c" + chr(0x200B) + "d\ne\tf"
    # a pre-existing row (written raw, as before this fix) must be stripped on the way out
    p = IB.inbox_path(tmp_path)
    p.parent.mkdir(parents=True)
    raw = {"kind": "note", "id": "old1", "utc": "t", "text": bad, "page": None, "status": "unread"}
    p.write_text(json.dumps(raw) + "\n", encoding="utf-8")
    stored = IB.add_note(bad, data_root=tmp_path, source="telegram")
    assert chr(27) not in stored["text"] and chr(0x202E) not in stored["text"] and stored["source"] == "telegram"
    assert chr(27) in p.read_text(encoding="utf-8").splitlines()[0].encode().decode("unicode_escape")  # old row untouched
    assert IB.main(["list", "--data-root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert chr(27) not in out and chr(7) not in out and chr(0x202E) not in out and chr(0x200B) not in out
    assert "source=telegram" in out and "source=-" in out
    assert "stripped from this note" in out and "(app or telegram)" in out
    assert "d\ne\tf" in out
