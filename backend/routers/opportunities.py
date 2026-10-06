"""Opportunity Explorer API (chunk C4, 2026-10-06). READ ONLY.

GET /api/opportunities/latest      the list switcher + legend + the first list's rows
GET /api/opportunities/{list_id}   one list's rows

Both read the NEWEST receipt written by `scripts/opportunities_build.py`
(`backend/services/opportunities.py` picks it by the run stamp in its name). This
router builds nothing: a request can never create a ranking at a time nobody
declared.

404 when no receipt exists (or the list id is not in it): an absence, never an
empty table that would read like "every name was refused". 422 on a list id
that is not a list id at all.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backend.services import opportunities as OPP

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])

_NO_RECEIPT = ("no Opportunity Explorer receipt on disk. It is written by "
               "`python -m scripts.opportunities_build`; this endpoint reads one and never builds one.")


def _load() -> dict:
    try:
        blob = OPP.load_latest()
    except Exception as e:                                    # noqa: BLE001
        logger.exception("opportunities receipt read failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}") from e
    if blob is None:
        raise HTTPException(status_code=404, detail=_NO_RECEIPT)
    return blob


def _envelope(blob: dict) -> dict:
    return {k: blob.get(k) for k in ("schema", "generated_utc", "asof", "run_id", "builder", "licence",
                                     "legend", "inputs", "receipt_file", "skipped_receipts")} | {
        "lists": OPP.list_index(blob)}


@router.get("/latest")
def get_latest() -> dict:
    """The switcher (every list without rows), the legend, and the first list in full."""
    blob = _load()
    out = _envelope(blob)
    first = (blob.get("lists") or [None])[0]
    out["list"] = OPP.with_ages(first) if first else None
    return out


@router.get("/{list_id}")
def get_list(list_id: str) -> dict:
    """One list's rows, with `last_update_age_days` computed at serve time."""
    if not OPP.LIST_ID_RE.match(list_id or ""):
        raise HTTPException(status_code=422,
                            detail="list_id must be 1-80 chars of lowercase letters, digits, '_' or '-'")
    blob = _load()
    lst = OPP.find_list(blob, list_id)
    if lst is None:
        raise HTTPException(status_code=404,
                            detail=f"no list '{list_id}' in {blob.get('receipt_file')}; "
                                   f"available: {[x['list_id'] for x in OPP.list_index(blob)]}")
    out = _envelope(blob)
    out["list"] = OPP.with_ages(lst)
    return out
