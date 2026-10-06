"""Paper Arena API (chunk C19, 2026-10-07; review fixes F1/F8). READ ONLY.

GET /api/arena/v1/latest    every account/book from the newest ROI + book_dna receipts
GET /api/arena/v1/stories   the PC-PAPER plan's decision stories (C11) + the regret h5 table

Receipts are chosen by the run stamp in their NAME (never a hard-coded date, never the
mtime); every response carries each receipt's age, sha256 and FRESH / STALE status.
Every payload leaves through ONE deny-by-default sanitiser
(`legibility_sanitise.sanitise`, per-endpoint allow-list): no dollar equity, no account
numbers, no paths, PIDs, ports or credential env-var names reach a browser.

404 when no receipt exists; 422 on a malformed query; 500 names only the exception TYPE
(the message is logged, never served: it can carry a user-home path).
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.services import legibility as L
from backend.services import legibility_sanitise as S

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/arena/v1", tags=["arena-v1"])

_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,15}$")


def serve(fn, kind: str, what: str, absent: str, **kw) -> dict:
    """Build, 404 on absence, generic 500 on failure, sanitise by the kind's allow-list."""
    try:
        out = fn(**kw)
    except Exception as e:                                    # noqa: BLE001
        logger.exception("%s read failed", what)
        raise HTTPException(status_code=500, detail=f"{what}: internal error ({type(e).__name__})") from e
    if out is None:
        raise HTTPException(status_code=404, detail=absent)
    return S.sanitise(out, S.SPEC[kind])


@router.get("/latest")
def get_latest() -> dict:
    return serve(L.arena_payload, "arena", "paper arena", (
        "no run-stamped ROI receipt (paper_accounts/roi_<date>T<hhmmss>Z.json) on disk. It is written by "
        "`python -m scripts.paper_accounts_roi` (the daily pass's paper_accounts step); this endpoint "
        "reads one and never builds one."))


@router.get("/stories")
def get_stories(ticker: Optional[str] = Query(default=None), limit: int = Query(default=200, ge=1, le=2000)) -> dict:
    if ticker is not None and not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail="ticker must be 1-15 chars of letters, digits, '.' or '-'")
    return serve(L.stories_payload, "arena_stories", "decision stories", (
        "no decision_story/stories_<YYYY-MM>.jsonl on disk. Stories are frozen by the PC-PAPER plan "
        "(`decision_story.freeze_plan`, C11) once per session; none has been written here yet."),
        limit=limit, ticker=ticker)
