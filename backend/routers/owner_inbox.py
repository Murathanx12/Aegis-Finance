"""The owner's "Note to Claude" box (CH-22, 2026-11-14) -- local desktop only.

    POST /api/control/owner-note    {text, page?}  -> the row as written
    GET  /api/control/owner-notes?limit=N          -> newest first, with status

A note is one append-only JSONL row under `<OPTIMUS_LEDGER_DIR>/owner_inbox/`
(`scripts/owner_inbox.py` owns the file format and the CLI a Claude session reads
it with). This router calls no LLM, sends nothing anywhere and imports no broker.

Two gates, both on BOTH routes (review of PR #143, H1):
  * `control.check_local_request` -- loopback Host with the served port, a
    same-origin Origin if any, Sec-Fetch-Site same-origin/none, and
    `Content-Type: application/json` on the POST. A hostile page's no-cors
    "simple request" and a DNS-rebinding read both stop here, before the body.
  * `_require_enabled()` -- the control plane is off unless the desktop shell set
    `AEGIS_CONTROL_ENABLED=1`, so the website never serves the owner's notes.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from backend import config as C
from backend.routers.control import _require_enabled, check_local_request

router = APIRouter(prefix="/api/control", tags=["owner-inbox"],
                   dependencies=[Depends(check_local_request)])


def _inbox():
    # Lazy and AFTER the gates: the Railway image does not ship `scripts/`, and a
    # request it must refuse should not first fail on an import.
    from scripts import owner_inbox
    return owner_inbox


@router.post("/owner-note")
def post_owner_note(request: Request, body: dict = Body(...)) -> dict:
    _require_enabled()
    ib = _inbox()
    h = request.headers
    try:
        row = ib.add_note(body.get("text"), body.get("page"), origin=h.get("origin"),
                          host=h.get("host"), user_agent=h.get("user-agent"))
    except ib.InboxRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ib.InboxBusy as exc:
        raise HTTPException(status_code=503, detail=f"the note was NOT saved: {exc}") from exc
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
