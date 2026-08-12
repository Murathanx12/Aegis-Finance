"""Optimus Portfolio Manager API.

The retail product surface: one call returns the whole morning brief for the
live book. Deliberately thin — every decision lives in `pm_engine`/`pm_actions`
so the same code serves the API, the CLI and the tests.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from backend.cache import cache_get, cache_set
from backend.services import analyst_ledger, pm_actions, pm_engine, pm_journal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/pm", tags=["portfolio-manager"])

BRIEF_TTL = 900          # 15 minutes; analyst data does not move faster


@router.get("/book")
def get_book() -> dict:
    """The book as configured, including whether it has been confirmed."""
    b = pm_engine.load_book(strict=False)
    problems = pm_engine.validate_book(b)
    return {
        "account": b.account, "confirmed": b.confirmed,
        "evidence_grade": b.evidence_grade, "as_of": b.as_of,
        "cash": b.cash,
        "cash_basis": ("stated" if b.cash is not None else
                       "UNRECOVERABLE — swept as a sensitivity parameter "
                       "(config.CASH_SENSITIVITY_GRID)"),
        "sizing_mode": b.sizing_mode,
        "wealth_targets": b.wealth_targets, "source": b.source,
        "positions": [p.__dict__ for p in b.positions],
        "closed": b.closed, "watchlist": b.watchlist,
        # NIGHT-13 §0: confirmation grades the evidence; it no longer blocks.
        "actionable": not problems,
        "problems": problems,
        "warning": (None if not problems else
                    "book validation problems — every dollar figure is "
                    "SIMULATED. Edit backend/data/murat_book.yaml before "
                    "acting on any ticket size"),
        "note": (None if b.confirmed else
                 "proposals priced on best-evidence book (unconfirmed) — "
                 "evidence grade, not a blocker"),
    }


@router.get("/book/validate")
def validate() -> dict:
    """Everything that stops this book from producing an executable ticket."""
    b = pm_engine.load_book(strict=False)
    problems = pm_engine.validate_book(b)
    return {
        "confirmed": b.confirmed, "evidence_grade": b.evidence_grade,
        "problems": problems,
        "actionable": not problems,
        "requirement": ("a confirmed position must carry a finite positive "
                        "share count — `dollars` cannot mark to market. "
                        "Confirmation itself is an evidence grade "
                        "(NIGHT-13 §0), not an actionability gate."),
    }


@router.get("/revisions/{ticker}")
def revisions(ticker: str) -> dict:
    """Real ΔTarget 7/30/90d from our own PIT ledger, or an explicit MISSING.

    These fields do not exist for a ticker the ledger has only seen once. They
    are never reconstructed from today's consensus.
    """
    return {"revisions": analyst_ledger.target_revisions(ticker.upper()),
            "ledger": analyst_ledger.coverage()}


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
    book = pm_engine.load_book(strict=False)
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
    if e.get("market_data_status") != "ok":
        raise HTTPException(status_code=404,
                            detail=f"no usable data for {ticker.upper()}: "
                                   + "; ".join(e.get("missing_reasons") or []))
    return {"state": e, "alpha": pm_engine.analyst_alpha(e),
            "distribution": pm_engine.distribution(e),
            "expected_return": pm_engine.expected_return(e),
            "decisionable": e.get("decisionable"),
            "missing_reasons": e.get("missing_reasons")}


@router.get("/wealth")
def wealth(mode: str | None = Query(None,
                                    pattern="^(growth|high_growth|moonshot)$")
           ) -> dict:
    """Where does this book land, and how often does it end badly?"""
    brief = daily(include_watchlist=False, max_candidates=1, mode=mode)
    return brief["wealth"]


@router.get("/catalysts")
def catalysts(ticker: str | None = Query(None)) -> dict:
    """What is scheduled to happen, and — as loudly — what we cannot see.

    An empty calendar here means "no earnings date in the window". It is not
    evidence that nothing is coming: PDUFA dates, readouts, offerings and
    lockups have no entitled source, and `coverage.uncovered` says so.
    """
    from backend.services import pm_catalysts
    if ticker:
        return pm_catalysts.catalysts_for(ticker.upper())
    book = pm_engine.load_book(strict=False)
    return pm_catalysts.calendar([p.ticker for p in book.positions],
                                 {p.ticker: p for p in book.positions})


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


@router.post("/snapshot")
def snapshot(tickers: str = Query("", description="comma-separated; blank = "
                                                 "the whole book + watchlist")
             ) -> dict:
    """Append today's analyst state to the PIT ledger for the given names.

    This is the only way ΔTarget over 7/30/90 days ever comes to exist: the
    only source we hold returns a current consensus with no history, so the
    history is one we write, one observation at a time, starting now.
    """
    book = pm_engine.load_book(strict=False)
    want = ([t.strip().upper() for t in tickers.split(",") if t.strip()]
            or [p.ticker for p in book.positions] + list(book.watchlist))
    written, skipped = [], []
    for t in want:
        e = pm_engine.enrich(t)
        if e.get("market_data_status") != "ok":
            skipped.append({"ticker": t, "why": e.get("missing_reasons")})
            continue
        row = analyst_ledger.snapshot_if_new(t, e)
        (written if row else skipped).append(
            row or {"ticker": t, "why": "already observed today"})
    return {"written": len([w for w in written if w]), "skipped": len(skipped),
            "coverage": analyst_ledger.coverage()}
