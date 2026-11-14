"""The owner's inbox to the Claude session (CH-22, 2026-11-14).

    python -m scripts.owner_inbox list [--unread] [--data-root D] [--json]
    python -m scripts.owner_inbox mark-read <id> [--data-root D]

The owner asked (2026-11-14) for a box in the desktop app where "when I write
something there it automatically sends to you directly, or saves it to the cache
so you can open it". There is no channel from the app to a Claude session, so
this is the second half of that sentence: a FILE the next brain session reads at
session start. Nothing here calls an LLM, sends a message or touches a broker.

The file is `<data-root>/owner_inbox/notes.jsonl`, append-only. Two row kinds:

    {"kind": "note",   "id": <uuid>, "utc": ..., "text": ..., "page": ..., "status": "unread"}
    {"kind": "status", "id": <uuid>, "utc": ..., "status": "read"}

A note is never edited. `mark-read` APPENDS a status row; the note's current
status is the last status row for its id (or the note's own "unread"). Every
write is append + flush + fsync, so a note the page reported as saved is on disk.

`<data-root>` defaults to `config.OPTIMUS_LEDGER_DIR`, which on the runtime
machine is the live data folder: pass `--data-root` to read anything else.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as C  # noqa: E402

SCHEMA = "owner_inbox/1"
STATUSES = ("unread", "read")


class InboxRefused(ValueError):
    """The note was not written (empty, too long, or not text). Carries the reason."""


def default_root() -> Path:
    # read at call time, so a test that points OPTIMUS_LEDGER_DIR at tmp_path is obeyed
    return Path(C.OPTIMUS_LEDGER_DIR)


def inbox_path(data_root: Optional[Path] = None) -> Path:
    return Path(data_root or default_root()) / "owner_inbox" / "notes.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _append(path: Path, row: dict) -> None:
    """One JSON line, appended, flushed and fsynced. The file is never rewritten."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno())


def clean_text(text: object, *, max_chars: Optional[int] = None) -> str:
    """The note as it will be stored, or `InboxRefused`. Trimmed, never cut."""
    lim = int(max_chars if max_chars is not None else C.OWNER_INBOX_MAX_CHARS)
    if not isinstance(text, str):
        raise InboxRefused("the note must be text")
    t = text.strip()
    if not t:
        raise InboxRefused("the note is empty; nothing was saved")
    if len(t) > lim:
        raise InboxRefused(f"the note is {len(t)} characters; the limit is {lim}. Nothing was saved -- split it in two")
    return t


def add_note(text: object, page: Optional[str] = None, *, data_root: Optional[Path] = None) -> dict:
    """Append one unread note and return the row exactly as written."""
    t = clean_text(text)
    pg = page.strip()[:300] if isinstance(page, str) and page.strip() else None
    row = {"kind": "note", "schema": SCHEMA, "id": str(uuid.uuid4()), "utc": _now(),
           "text": t, "page": pg, "status": "unread"}
    _append(inbox_path(data_root), row)
    return row


def _rows(path: Path) -> tuple[list[dict], int]:
    """(rows, unreadable line count). A torn or foreign line is counted, not fatal."""
    if not path.exists():
        return [], 0
    rows: list[dict] = []
    bad = 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except ValueError:
                bad += 1
                continue
            if isinstance(r, dict) and r.get("kind") in ("note", "status") and r.get("id"):
                rows.append(r)
            else:
                bad += 1
    return rows, bad


def list_notes(*, data_root: Optional[Path] = None, unread_only: bool = False,
               limit: Optional[int] = None) -> dict:
    """Every note with its CURRENT status, newest first (file order, which is time order)."""
    path = inbox_path(data_root)
    rows, bad = _rows(path)
    notes: dict[str, dict] = {}
    order: list[str] = []
    for r in rows:
        if r["kind"] == "note":
            if r["id"] in notes:          # a duplicate id is a foreign write; keep the first
                bad += 1
                continue
            notes[r["id"]] = dict(r)
            order.append(r["id"])
        elif r["id"] in notes and r.get("status") in STATUSES:
            notes[r["id"]]["status"] = r["status"]
            notes[r["id"]]["status_utc"] = r.get("utc")
    out = [notes[i] for i in reversed(order)]
    n_unread = sum(1 for n in out if n.get("status") == "unread")
    if unread_only:
        out = [n for n in out if n.get("status") == "unread"]
    if limit is not None:
        out = out[: max(0, int(limit))]
    return {"path": str(path), "exists": path.exists(), "n_notes": len(order),
            "n_unread": n_unread, "unreadable_lines": bad, "notes": out}


def mark(note_id: str, status: str = "read", *, data_root: Optional[Path] = None) -> dict:
    """Append a status row for an existing note. Unknown id or status -> `InboxRefused`."""
    if status not in STATUSES:
        raise InboxRefused(f"status must be one of {STATUSES}")
    path = inbox_path(data_root)
    rows, _ = _rows(path)
    if not any(r["kind"] == "note" and r["id"] == note_id for r in rows):
        raise InboxRefused(f"no note with id {note_id} in {path}")
    row = {"kind": "status", "schema": SCHEMA, "id": note_id, "utc": _now(), "status": status}
    _append(path, row)
    return row


def _print_notes(res: dict) -> None:
    print(f"{res['path']}: {res['n_notes']} notes, {res['n_unread']} unread"
          + (f", {res['unreadable_lines']} unreadable lines" if res["unreadable_lines"] else ""))
    for n in res["notes"]:
        print(f"\n[{n.get('status')}] {n.get('utc')}  id={n.get('id')}  page={n.get('page') or '-'}")
        print(n.get("text", ""))


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Read the owner's notes to the Claude session.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_list = sub.add_parser("list", help="print the notes, newest first")
    p_list.add_argument("--unread", action="store_true", help="only notes not yet marked read")
    p_list.add_argument("--json", action="store_true", help="print the result as JSON")
    p_mark = sub.add_parser("mark-read", help="append a 'read' status row for one note")
    p_mark.add_argument("id")
    for p in (p_list, p_mark):
        p.add_argument("--data-root", default=None,
                       help=f"the optimus data folder (default: {C.OPTIMUS_LEDGER_DIR})")
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    root = Path(a.data_root) if a.data_root else None
    if a.cmd == "list":
        res = list_notes(data_root=root, unread_only=a.unread)
        if a.json:
            print(json.dumps(res, indent=1, ensure_ascii=False))
        else:
            _print_notes(res)
        return 0
    try:
        row = mark(a.id, "read", data_root=root)
    except InboxRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(row, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
