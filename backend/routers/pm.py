"""Optimus Portfolio Manager API.

The retail product surface: one call returns the whole morning brief for the
live book. Deliberately thin — every decision lives in `pm_engine`/`pm_actions`
so the same code serves the API, the CLI and the tests.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from backend.cache import cache_get, cache_set
from backend.services import pm_actions, pm_engine, pm_journal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/pm", tags=["portfolio-manager"])

BRIEF_TTL = 900          # 15 minutes; analyst data does not move faster


@router.get("/book")
def get_book() -> dict:
    """The book as configured, including whether it has been confirmed."""
    b = pm_engine.load_book()
    return {
        "account": b.account, "confirmed": b.confirmed, "as_of": b.as_of,
        "cash": b.cash, "sizing_mode": b.sizing_mode,
        "wealth_targets": b.wealth_targets, "source": b.source,
        "positions": [p.__dict__ for p in b.positions],
        "closed": b.closed, "watchlist": b.watchlist,
        "warning": None if b.confirmed else
        "positions are unconfirmed placeholders — edit "
        "backend/data/murat_book.yaml before acting on any ticket size",
    }


@router.get("/daily")
def daily(include_watchlist: bool = Query(True),
          max_candidates: int = Query(10, ge=1, le=40),
          mode: str | None = Query(None, pattern="^(growth|high_growth|moonshot)$"),
          refresh: bool = Query(False)) -> dict:
    """The morning brief: state, actions, opportunities, threats, odds.

    `mode` overrides the book's sizing mode for this call only. It changes
    position limits and nothing about the evidence.
    """
    key = f"pm:daily:{include_watchlist}:{max_candidates}:{mode}"
    if not refresh:
        hit = cache_get(key, BRIEF_TTL)
        if hit is not None:
            return hit
    book = pm_engine.load_book()
    if mode:
        book.sizing_mode = mode
    try:
        out = pm_actions.daily_brief(book, include_watchlist=include_watchlist,
                                     max_candidates=max_candidates)
    except Exception as e:                       # noqa: BLE001
        logger.exception("daily brief failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
    cache_set(key, out)
    return out


@router.get("/name/{ticker}")
def one_name(ticker: str) -> dict:
    """Everything the engine knows about a single name, held or not."""
    e = pm_engine.enrich(ticker.upper())
    if not e.get("available"):
        raise HTTPException(status_code=404,
                            detail=f"no usable data for {ticker.upper()}")
    return {"state": e, "alpha": pm_engine.analyst_alpha(e),
            "distribution": pm_engine.distribution(e)}


@router.get("/wealth")
def wealth(mode: str | None = Query(None,
                                    pattern="^(growth|high_growth|moonshot)$")
           ) -> dict:
    """Where does this book land, and how often does it end badly?"""
    brief = daily(include_watchlist=False, max_candidates=1, mode=mode)
    return brief["wealth"]


@router.get("/journal")
def journal(limit: int = Query(50, ge=1, le=500)) -> dict:
    """Every recommendation ever issued, so they can be scored later."""
    return {"entries": pm_journal.tail(limit),
            "counts": pm_journal.summary()}


@router.post("/journal/record")
def record(note: str = Query("", max_length=500)) -> dict:
    """Freeze today's brief into the decision journal.

    This is what makes the engine accountable: every instruction is written
    down with the state that produced it, so in three months it can be asked
    whether the thesis, the catalyst or the sizing was the thing that was wrong.
    """
    brief = daily(refresh=True)
    return pm_journal.record_brief(brief, note=note)
