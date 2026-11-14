"""CH-22 -- the ticker hub routes (control plane, local only).

GET /api/control/ticker/{symbol}/hub?days=30
    news[] (our own corpus, newest first, with source, time, headline, link, how it was
    tagged and the typed event when the world digest typed it), forecasts{open, resolved,
    void, counts}, calendar (forward calendar, point in time), events (event nodes),
    related[] (universe-graph links + same sector), coverage{status OK/STALE/NO_INDEX,
    index_built_utc, index_age_s, sources, newest_utc, n_rows}.
GET /api/control/news/feed?ticker=&sector=&source=&days=&limit=
    rows + facets (counts by ticker, sector, source).

BOTH routes refuse (403) unless `AEGIS_CONTROL_ENABLED=1` -- the flag the desktop shell
sets when it starts the backend on localhost (`backend/routers/control.py` `_enabled`).
Unlike the control plane's other reads they serve licensed headline text (the Dow Jones
reader's pages), and the corpus exists only on this PC, so on the Railway website they
are inert. Unknown symbol -> 404. The index is built by `python -m scripts.ticker_hub
build`; a request reads the index, never the corpus.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.services import ticker_hub as TH

router = APIRouter(prefix="/api/control", tags=["control", "ticker-hub"])


def _require_enabled() -> None:
    """The same flag as `backend/routers/control.py::_enabled` (read, not imported, so
    this router carries no import of the job-spawning module)."""
    if os.getenv("AEGIS_CONTROL_ENABLED", "") != "1":
        raise HTTPException(status_code=403, detail=(
            "the ticker hub is local only: AEGIS_CONTROL_ENABLED=1 is set by the desktop "
            "shell on localhost"))


def _valid_symbol(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if not s or len(s) > 12 or not all(c.isalnum() or c in ".-" for c in s):
        raise HTTPException(status_code=422, detail=f"not a ticker: {symbol!r}")
    return s


@router.get("/ticker/{symbol}/hub")
def ticker_hub(symbol: str, days: int = Query(default=30, ge=1, le=365)) -> dict:
    _require_enabled()
    s = _valid_symbol(symbol)
    try:
        return TH.hub(s, days=days)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"{s} is not in the universe (issuer table)")


@router.get("/news/feed")
def news_feed(ticker: Optional[str] = None, sector: Optional[str] = None, source: Optional[str] = None,
              days: int = Query(default=30, ge=1, le=365),
              limit: int = Query(default=200, ge=1, le=2000)) -> dict:
    _require_enabled()
    t = _valid_symbol(ticker) if ticker else None
    try:
        return TH.feed(ticker=t, sector=sector or None, source=source or None, days=days, limit=limit)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"{t} is not in the universe (issuer table)")
