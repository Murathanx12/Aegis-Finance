"""CH-22 -- the ticker hub routes (control plane, local only).

GET /api/control/ticker/{symbol}/hub?days=30&tier=about
    news[] (distinct stories, newest first, each with source, both times, headline, link,
    copies across sources, "tagged by" and its tier), tier_counts, forecasts, calendar,
    events, related[] (with how each was ranked), coverage{status OK/STALE/DEGRADED/NO_INDEX,
    problems[], sources[] with each source's newest-row age, stale_sources[], ...}.
GET /api/control/ticker/{symbol}/news?days=&tier=&offset=&limit=
    the next page of stories ("load more").
GET /api/control/news/feed?ticker=&sector=&source=&days=&limit=&tier=
    stories + facets (row counts by ticker, sector, source).

EVERY route refuses (403) unless `AEGIS_CONTROL_ENABLED=1` (the flag the desktop shell
sets on localhost) AND the request passes `control.check_local_request` (#143): a
loopback Host with the served port, no foreign Origin, Sec-Fetch-Site same-origin. These
routes serve licensed headline text, so DNS rebinding (an attacker's name resolving to
127.0.0.1) must not read them. Unknown symbol -> 404. A damaged index answers 200 with
status DEGRADED and the named problems, never a 404 for every symbol or a 500.
"""
from __future__ import annotations

import os
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.routers.control import check_local_request
from backend.services import ticker_hub as TH

router = APIRouter(prefix="/api/control", tags=["control", "ticker-hub"],
                   dependencies=[Depends(check_local_request)])


def _require_enabled() -> None:
    """The same flag as `backend/routers/control.py::_enabled`."""
    if os.getenv("AEGIS_CONTROL_ENABLED", "") != "1":
        raise HTTPException(status_code=403, detail=(
            "the ticker hub is local only: AEGIS_CONTROL_ENABLED=1 is set by the desktop "
            "shell on localhost"))


def _valid_symbol(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if not s or len(s) > 12 or not all(c.isalnum() or c in ".-" for c in s):
        raise HTTPException(status_code=422, detail=f"not a ticker: {symbol!r}")
    return s


Tier = Literal["about", "all"]


@router.get("/ticker/{symbol}/hub")
def ticker_hub(symbol: str, days: int = Query(default=30, ge=1, le=365), tier: Tier = "about",
               limit: int = Query(default=50, ge=1, le=500)) -> dict:
    _require_enabled()
    s = _valid_symbol(symbol)
    try:
        return TH.hub(s, days=days, tier=tier, limit=limit)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"{s} is not in the universe (issuer table)")


@router.get("/ticker/{symbol}/news")
def ticker_news(symbol: str, days: int = Query(default=30, ge=1, le=365), tier: Tier = "about",
                offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=500)) -> dict:
    _require_enabled()
    s = _valid_symbol(symbol)
    try:
        return TH.news(s, days=days, tier=tier, offset=offset, limit=limit)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"{s} is not in the universe (issuer table)")


@router.get("/news/feed")
def news_feed(ticker: Optional[str] = None, sector: Optional[str] = None, source: Optional[str] = None,
              days: int = Query(default=30, ge=1, le=365),
              limit: int = Query(default=200, ge=1, le=2000), tier: Tier = "about") -> dict:
    _require_enabled()
    t = _valid_symbol(ticker) if ticker else None
    try:
        return TH.feed(ticker=t, sector=sector or None, source=source or None, days=days, limit=limit, tier=tier)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"{t} is not in the universe (issuer table)")
