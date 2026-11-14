"""The owner's "Note to Claude" box (CH-22, 2026-11-14) -- local desktop only.

    POST /api/control/owner-note    {text, page?}  -> the row as written
    GET  /api/control/owner-notes?limit=N          -> newest first, with status

A note is one append-only JSONL row under `<OPTIMUS_LEDGER_DIR>/owner_inbox/`
(`scripts/owner_inbox.py` owns the file format and the CLI the brain session
reads it with). This router calls no LLM, sends nothing anywhere and imports no
broker: it writes a file the next Claude session opens. Both routes, the read
included, are gated by the control plane's `_require_enabled()` -- the owner's
notes are never served by the public website.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query

from backend import config as C
from backend.routers.control import _require_enabled

router = APIRouter(prefix="/api/control", tags=["owner-inbox"])


def _inbox():
    # Lazy and AFTER the gate: the Railway image does not ship `scripts/`, and a
    # request it must refuse should not first fail on an import.
    from scripts import owner_inbox
    return owner_inbox


@router.post("/owner-note")
def post_owner_note(body: dict = Body(...)) -> dict:
    _require_enabled()
    ib = _inbox()
    try:
        row = ib.add_note(body.get("text"), body.get("page"))
    except ib.InboxRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500,
                            detail=f"the note was NOT saved: {type(exc).__name__}: {exc}") from exc
    return {"saved": True, "path": str(ib.inbox_path()), "note": row}


@router.get("/owner-notes")
def get_owner_notes(limit: Optional[int] = Query(default=None, ge=1)) -> dict:
    _require_enabled()
    ib = _inbox()
    n = min(int(limit or C.OWNER_INBOX_LIST_DEFAULT), int(C.OWNER_INBOX_LIST_MAX))
    return ib.list_notes(limit=n)
