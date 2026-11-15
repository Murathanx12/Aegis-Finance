"""CH-48 slice 1: four owner commands on the Telegram read-only table (2026-11-15).

    /status        the systems receipt headline (counts, every DOWN row by name, age, STALE)
    /books         the six headline lines of the newest results voice, stamp and age
    /note <text>   one row in the owner inbox (same function and file as the desktop app)
    /help          these, and the existing read-only table

The owner no longer wants alerts; he wants to send a message and get an answer. Everything
here is DETERMINISTIC: no model, no broker, no subprocess, no network, no job start.

THE ONLY THINGS A MESSAGE CAN CAUSE (audited 2026-11-15, see the tests)
=======================================================================
  * a read of `system_status/status.json` or the newest `paper_accounts/results_voice_*.md`;
  * ONE append to `owner_inbox/notes.jsonl` (`scripts.owner_inbox.add_note`, source "telegram");
  * ONE append to `telegram/owner_commands.jsonl` (the journal: command name, sender-check
    result, reply length, stamp -- never the note text, never the chat id).
A note is UNVERIFIED text for the brain. Nothing in this module parses it as a command, and
`/note` text is never passed to anything but `add_note`.

HANDING TASKS TO OPENCLAW OR STARTING JOBS FROM CHAT IS NOT HERE and is the owner's open
permission decision (ROADMAP CH-48). `COMMANDS` is a closed tuple; an unknown command falls
through to today's behaviour (`telegram_readonly`), and `test_telegram_owner_commands` pins that
this module imports no subprocess, socket, model, broker or sim entry point.

The functions take (data root, now, message) so tests need no network; sending is injected.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from backend import config as _cfg

CANNOT = "CANNOT DETERMINE"
COMMANDS: tuple[str, ...] = ("status", "books", "note", "help")
JOURNAL_NAME = "owner_commands.jsonl"

#: The six headline lines of a results voice, in file order; `/books` prints these verbatim.
_HEAD_PREFIXES = ("RESULTS", "LEADER", "NEXT", "WHAT RAISES IT", "BEHIND", "CLAIMS PROMOTED")
_ABS_PATH = re.compile(r"(?:[A-Za-z]:[\\/][^\s,;)\"'`]*|(?<![\w.])/(?:home|Users|c|mnt)/[^\s,;)\"'`]*)")
_STAMP = re.compile(r"results_voice_(\d{4}-\d{2}-\d{2}T\d{6}Z)\.md$")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _root(root: Optional[Path]) -> Path:
    return Path(root or _cfg.OPTIMUS_LEDGER_DIR)


def _scrub(text: str) -> str:
    """No absolute paths in a phone reply."""
    return _ABS_PATH.sub("<path>", str(text))


def _parse_ts(v: Any) -> Optional[datetime]:
    s = str(v or "").strip()
    if not s:
        return None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{6}Z", s):
            return datetime.strptime(s, "%Y-%m-%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def age_line(stamp: Any, limit_h: float, what: str, *, now: datetime) -> str:
    """The receipt's OWN stamp against a limit. Unreadable or future = STALE, never fresh."""
    t = _parse_ts(stamp)
    if t is None:
        return f"{what}: no readable stamp -- STALE"
    h = (now - t).total_seconds() / 3600.0
    if h < -0.1:
        return f"{what}: stamped {t:%Y-%m-%d %H:%M} UTC, in the FUTURE -- STALE"
    flag = f" -- STALE (limit {limit_h:g} h)" if h > limit_h else ""
    return f"{what}: {t:%Y-%m-%d %H:%M} UTC, {h:.1f} h old{flag}"


def cap_reply(text: str, max_chars: Optional[int] = None) -> str:
    """Cut to the limit at a line boundary and say how many lines were left out."""
    lim = int(max_chars or _cfg.TELEGRAM_OWNER_REPLY_MAX_CHARS)
    if len(text) <= lim:
        return text
    lines = text.split("\n")
    keep: list[str] = []
    used = 0
    reserve = 40
    for ln in lines:
        if used + len(ln) + 1 > lim - reserve:
            break
        keep.append(ln[: lim - reserve] if not keep and len(ln) > lim - reserve else ln)
        used += len(ln) + 1
    omitted = len(lines) - len(keep)
    return "\n".join(keep + [f"... {omitted} more line(s) omitted"])


# ──────────────────────────────────────────────────────────────── the readers

def status_reply(root: Optional[Path] = None, *, now: Optional[datetime] = None) -> str:
    """Counts, every DOWN row by section/name, the receipt's age. A missing receipt says so."""
    now = now or _utcnow()
    p = _root(root) / "system_status" / "status.json"
    try:
        rec = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        rec = None
    if not isinstance(rec, dict) or rec.get("receipt") != "system_status/1":
        return (f"STATUS {CANNOT}: no readable systems receipt. This is NOT 'all good'; "
                "the dashboard has not written one.")
    c = rec.get("counts") if isinstance(rec.get("counts"), dict) else {}
    parts = [f"{k} {c[k]}" if isinstance(c.get(k), int) else f"{k} ?" for k in
             ("OK", "DEGRADED", "DOWN", "UNKNOWN")]
    out = ["Systems: " + ", ".join(parts)]
    down = sorted(
        f"{r.get('section')}/{r.get('name')}"
        for s in (rec.get("sections") or {}).values() if isinstance(s, dict)
        for r in (s.get("rows") or []) if isinstance(r, dict) and r.get("status") == "DOWN")
    out += [f"DOWN {n}" for n in down]
    if isinstance(c.get("DOWN"), int) and c["DOWN"] != len(down):
        out.append(f"note: counts say {c['DOWN']} DOWN, rows name {len(down)}")
    if rec.get("undetermined"):
        out.append(f"could not determine: {len(rec['undetermined'])} item(s)")
    out.append(age_line(rec.get("generated_utc"), float(_cfg.TELEGRAM_READONLY_STATUS_STALE_H),
                        "receipt", now=now))
    return cap_reply(_scrub("\n".join(out)))


def _newest_results_voice(root: Path) -> Optional[Path]:
    d = root / "paper_accounts"
    try:
        files = [p for p in d.iterdir() if _STAMP.search(p.name)]
    except OSError:
        return None
    return max(files, key=lambda p: p.name) if files else None


def books_reply(root: Optional[Path] = None, *, now: Optional[datetime] = None) -> str:
    """The headline lines of the newest results voice, verbatim, with run stamp and age.
    The CLAIMS PROMOTED line comes last and is never dropped."""
    now = now or _utcnow()
    p = _newest_results_voice(_root(root))
    if p is None:
        return f"BOOKS {CANNOT}: no results_voice_<run>.md on disk. This is NOT 'no change'."
    try:
        text = p.read_text(encoding="utf-8-sig")
    except OSError:
        return f"BOOKS {CANNOT}: the newest results voice could not be read."
    stamp = _STAMP.search(p.name).group(1)               # type: ignore[union-attr]
    head: dict[str, str] = {}
    for ln in text.split("\n"):
        if ln.startswith("## "):
            break                                        # the headline block ends at the first section
        for pre in _HEAD_PREFIXES:
            if ln.startswith(pre) and pre not in head:
                head[pre] = ln.rstrip()
                break
    lines = [head[k] for k in _HEAD_PREFIXES if k in head and k != "CLAIMS PROMOTED"]
    out = [f"Books, results voice run {stamp}"]
    out.append(age_line(stamp, float(_cfg.TELEGRAM_OWNER_BOOKS_STALE_H), "run", now=now))
    missing = [k for k in _HEAD_PREFIXES if k not in head]
    out += lines
    if missing:
        out.append(f"headline lines missing from the file: {', '.join(missing)}")
    out.append(head.get("CLAIMS PROMOTED", f"CLAIMS PROMOTED: {CANNOT} (line absent from the file)"))
    # cap the body but keep the claims line last
    body = cap_reply(_scrub("\n".join(out[:-1])), int(_cfg.TELEGRAM_OWNER_REPLY_MAX_CHARS) - len(out[-1]) - 2)
    return body + "\n" + _scrub(out[-1])


def note_reply(text: str, root: Optional[Path] = None, *, now: Optional[datetime] = None) -> str:
    """Append `text` to the owner inbox as an UNVERIFIED note and return the reply. Nothing
    reads the note as an instruction."""
    if not str(text or "").strip():
        return "Usage: /note <text>  (nothing was saved)"
    from scripts import owner_inbox as IB                 # lazy: the Railway image has no scripts/
    try:
        row = IB.add_note(text, None, data_root=_root(root), source="telegram")
    except IB.InboxRefused as exc:
        return cap_reply(_scrub(f"Note NOT saved: {exc}"))
    except IB.InboxBusy:
        return "Note NOT saved: the inbox is busy; send it again."
    except OSError as exc:
        return f"Note NOT saved: {type(exc).__name__}."
    return f"Note saved, id {row['id']} (unverified text for the brain; nothing runs it)."


def help_reply() -> str:
    return "\n".join([
        "AEGIS owner commands (deterministic, no model):",
        "/status -- systems receipt: counts, each DOWN row, its age",
        "/books -- headline of the newest results voice, with its age",
        "/note <text> -- leave an unverified note for the brain (same inbox as the app)",
        "/help -- this list",
        "Nothing here starts a job, places an order or runs a command."])


# ─────────────────────────────────────────────────────────── rate limit + journal

class RateLimiter:
    """Sliding one-hour window per (chat, kind). Injectable clock; thread-safe."""

    def __init__(self) -> None:
        self._t: dict[tuple[str, str], list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, chat: str, kind: str, limit: int, *, now_s: Optional[float] = None) -> bool:
        now_s = time.time() if now_s is None else now_s
        with self._lock:
            ts = [t for t in self._t.get((chat, kind), []) if now_s - t < 3600.0]
            if len(ts) >= limit:
                self._t[(chat, kind)] = ts
                return False
            ts.append(now_s)
            self._t[(chat, kind)] = ts
            return True


_LIMITER = RateLimiter()


def journal_path(root: Optional[Path] = None) -> Path:
    return _root(root) / "telegram" / JOURNAL_NAME


def _journal(root: Optional[Path], row: dict) -> None:
    p = journal_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def command_of(text: Any) -> Optional[str]:
    """The owner command a message names, or None (-> today's behaviour). Slash form only."""
    s = str(text or "").strip()
    if not s.startswith("/"):
        return None
    name = s.split(None, 1)[0][1:].split("@")[0].lower()
    return name if name in COMMANDS else None


def _chat_id(msg: dict) -> str:
    return str(((msg or {}).get("chat") or {}).get("id") or "")


def dispatch(msg: dict, *, data_root: Optional[Path] = None, now: Optional[datetime] = None,
             owner_chat_id: Optional[str] = None,
             send: Optional[Callable[[str, str], Any]] = None,
             limiter: Optional[RateLimiter] = None) -> Optional[str]:
    """Answer one owner command, or None.

    None means "no reply": a message from any chat but the configured owner's (journaled as
    refused, never answered), or text that is not one of `COMMANDS`. `send(chat_id, text)`
    is called when a reply exists, and the reply is also returned (the bridge sends it when
    this runs as a handler, with `send=None`). Never raises for a bad message.
    """
    now = now or _utcnow()
    lim = limiter or _LIMITER
    text = str((msg or {}).get("text") or "")
    cmd = command_of(text)
    if cmd is None:
        return None
    cid = _chat_id(msg)
    owner = str(owner_chat_id or "")
    now_s = now.timestamp()
    ident = hashlib.sha256(cid.encode()).hexdigest()[:8] if cid else ""
    row: dict[str, Any] = {"t": now.isoformat(timespec="seconds"), "cmd": cmd, "chat_sha8": ident}
    if not owner or cid != owner:
        row["sender_ok"] = False
        row["outcome"] = "refused"
        if lim.allow("*", "refused_journal", int(_cfg.TELEGRAM_OWNER_REFUSED_JOURNAL_MAX_PER_H), now_s=now_s):
            _journal(data_root, row)
        return None
    row["sender_ok"] = True
    if not lim.allow(cid, "cmd", int(_cfg.TELEGRAM_OWNER_CMD_MAX_PER_H), now_s=now_s):
        reply, row["outcome"] = "Rate limit: too many commands this hour; try again later.", "rate_limited"
    elif cmd == "note" and not lim.allow(cid, "note", int(_cfg.TELEGRAM_OWNER_NOTE_MAX_PER_H), now_s=now_s):
        reply, row["outcome"] = "Rate limit: too many notes this hour; nothing was saved.", "rate_limited"
    else:
        try:
            if cmd == "status":
                reply = status_reply(data_root, now=now)
            elif cmd == "books":
                reply = books_reply(data_root, now=now)
            elif cmd == "help":
                reply = help_reply()
            else:
                parts = text.strip().split(None, 1)
                reply = note_reply(parts[1] if len(parts) > 1 else "", data_root, now=now)
            row["outcome"] = "answered"
        except Exception as exc:                          # noqa: BLE001 -- a reply, never silence
            reply, row["outcome"] = f"/{cmd} {CANNOT} ({type(exc).__name__})", "error"
    reply = cap_reply(reply)
    row["reply_chars"] = len(reply)
    try:
        _journal(data_root, row)
    except OSError:
        pass                                              # the reply still goes; the agent log has the OSError
    if send is not None:
        send(cid, reply)
    return reply


__all__ = ["COMMANDS", "dispatch", "command_of", "status_reply", "books_reply", "note_reply",
           "help_reply", "cap_reply", "age_line", "RateLimiter", "journal_path"]
