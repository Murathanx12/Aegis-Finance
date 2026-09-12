"""LANE B5 — one graded forecast per book decision, and one for its twin.

WHAT THIS WRITES
================
At every book decision the pass writes, into the SAME `predictions.jsonl` that
every other forecast in this programme goes into:

* one row for the book — `observable = beats_benchmark`, `benchmark` = the
  twin's book id, `horizon_days` = the cadence in trading sessions,
  `model = "engine"`, `policy_hash` = the contract's fingerprint,
  `control_twin_id` = the twin, `control_construction` = how the twin was built,
  `costs_charged = True` with the rate;
* one row for the TWIN at `probability = 0.5` — the base-rate forecaster is a
  row in the same ledger (M1's control), not a number computed at reporting
  time. A base rate that only exists when someone remembers to compute it is a
  base rate that will be computed after the result is known.

WHERE THE PROBABILITY COMES FROM, AND WHY IT IS NOT AN LLM's
============================================================
No LLM produces this number and none may: *no LLM output ever sizes or ranks*.
The convention is `spec_first_books.md` §0B — **p = Φ(trailing IR vs the twin)**,
the normal CDF of the book's own realised information ratio against its own twin,
recomputed each period from history that had already happened. It is
deterministic, auditable, and 0.5 exactly when there is no history — which is
the honest prior for a book that has never been marked.

It is a STAND-IN for a confidence, and it is a weak one: a book with three
sessions of history will produce a number that looks like a forecast and is
mostly noise. That is why it is graded by Brier against the twin's own 0.5 row:
if the stand-in carries no information, the two rows score the same and the
ledger says so.

WHY THE ROW IS WRITTEN BEFORE THE OUTCOME EXISTS
================================================
Because that is the only kind of row worth anything. The clock only runs
forward: a forecast minted after the fact is prose with a number in it.
"""

from __future__ import annotations

import logging
import math
import sqlite3
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

from backend.services import paper_books as PB
from backend.services.belief_state import (Observable, PredictionRecord, append,
                                           make_prediction)
from backend.services.paper_books import PaperBook

logger = logging.getLogger(__name__)

#: The mechanism family every paper-book forecast belongs to. Frozen: a typo
#: here silently creates a second mechanism with a second trial count.
MECHANISM_ID = "paper_book_v1"

#: What the base-rate row forecasts. 0.5 and nothing else -- a base rate fitted
#: to the sample it is the control for is not a control.
BASE_RATE = 0.5

MODEL = "engine"
MODEL_VERSION = "book_cadence_v1"

#: Where `write_decision_forecasts` appends when the caller names no path.
#: `None` means `belief_state.PREDICTIONS`, which is what production wants. It
#: exists as a module constant so the test suite can redirect THIS writer --
#: the one that fires from the Morning click without any caller naming a path --
#: without redirecting every reader of the real ledger too.
DEFAULT_LEDGER: Path | None = None


def _returns(series: Sequence[tuple[str, float]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for (d0, n0), (d1, n1) in zip(series, series[1:]):
        if n0:
            out[d1] = n1 / n0 - 1.0
    return out


def trailing_ir(book_series: Sequence[tuple[str, float]],
                twin_series: Sequence[tuple[str, float]]) -> tuple[float | None, int]:
    """(information ratio of book-minus-twin daily excess, n paired days).

    None when fewer than two paired days exist or the excess has no dispersion:
    an IR from one observation is a number with no sampling distribution behind
    it, and returning it would put a confident probability on the row.
    """
    import statistics as st

    rb, rt = _returns(book_series), _returns(twin_series)
    paired = sorted(set(rb) & set(rt))
    diffs = [rb[d] - rt[d] for d in paired]
    if len(diffs) < 2:
        return None, len(diffs)
    sd = st.pstdev(diffs)
    if sd <= 0:
        return None, len(diffs)
    return (st.fmean(diffs) / sd) * math.sqrt(len(diffs)), len(diffs)


def probability_from_ir(ir: float | None) -> float:
    """Φ(IR), clipped away from 0 and 1.

    Clipped because a Brier of exactly 0 or 1 on a stand-in confidence is a
    claim the construction cannot support, and because an unclipped 1.0 that
    turns out wrong dominates every other row in the mean.
    """
    if ir is None:
        return BASE_RATE
    p = 0.5 * (1.0 + math.erf(float(ir) / math.sqrt(2.0)))
    return max(0.02, min(0.98, p))


def _thesis(book: PaperBook, twin_id: str, ir: float | None, n: int) -> str:
    return (f"{book.book_id} ({book.strategy.signal.name}, k="
            f"{book.strategy.construction.k}, {book.cadence}) beats its control "
            f"{twin_id} over {book.horizon_sessions} session(s). "
            f"p = Phi(trailing IR) with IR="
            f"{'none yet' if ir is None else round(ir, 3)} on {n} paired day(s).")


def _counter_thesis(book: PaperBook, twin_id: str) -> str:
    return (f"the book's edge is the liquidity band and the construction, both "
            f"of which {twin_id} also has -- in which case the two NAV series "
            f"differ only by noise and the trailing IR is reading that noise.")


def build_rows(books: Iterable[PaperBook], *, conn: sqlite3.Connection,
               asof: date) -> list[PredictionRecord]:
    """One row per (book, first twin) plus the twin's base-rate row."""
    series = PB.nav_series(conn=conn)
    rows: list[PredictionRecord] = []
    for book in books:
        if book.is_twin or not book.control_twin_ids:
            continue
        twin_id = book.control_twin_ids[0]
        ir, n = trailing_ir(series.get(book.book_id) or [],
                            series.get(twin_id) or [])
        p = probability_from_ir(ir)
        rate = float(book.strategy.costs.transaction_cost_bps
                     + book.strategy.costs.slippage_bps)
        common = dict(
            observable=Observable.BEATS_BENCHMARK,
            horizon_days=book.horizon_sessions,
            benchmark=twin_id,
            next_observable=f"the {book.cadence} mark on {book.book_id}",
            model=MODEL, model_version=MODEL_VERSION,
            prompt=f"{MECHANISM_ID}|{book.strategy.fingerprint}",
            input_snapshot={"asof": str(asof), "nav_days": len(series.get(book.book_id) or []),
                            "fingerprint": book.strategy.fingerprint},
            mechanism_id=MECHANISM_ID,
            decision_date=str(asof),
            policy_hash=book.strategy.fingerprint,
            inputs_used={"source": "backend/data/optimus/prices_2025_26/bars.parquet",
                         "as_of": str(asof), "marked_from": "daily close"},
            control_twin_id=twin_id,
            control_construction=book.control_construction or "see the twin's contract",
            costs_charged=True, cost_rate_bps=rate,
            licence=book.strategy.licence.value,
            # `made_at` IS the decision moment, and the decision is taken at
            # the close of `asof` (see book_cadence's clock section). Writing
            # wall-clock-now instead would date the claim to whenever the pass
            # happened to run -- which on a catch-up run is days later, and the
            # resolver measures the outcome window FROM `made_at`. The real
            # wall clock is kept on the decision row (`decided_utc`).
            made_at=f"{asof}T21:00:00+00:00", session_as_of=str(asof),
        )
        rows.append(make_prediction(
            ticker=book.book_id, specialist=f"book:{book.strategy.signal.name}",
            probability=p, thesis=_thesis(book, twin_id, ir, n),
            counter_thesis=_counter_thesis(book, twin_id), **common))
        # THE BASE-RATE ROW. Same ledger, same horizon, same clock -- a control
        # that is computed later from the same data is not a control.
        rows.append(make_prediction(
            ticker=book.book_id, specialist="base_rate",
            probability=BASE_RATE,
            thesis=(f"the base-rate forecaster says {book.book_id} beats "
                    f"{twin_id} with probability 0.5, having looked at nothing."),
            counter_thesis=("if the engine's row cannot beat this one's Brier, "
                            "the trailing-IR stand-in carries no information "
                            "and the book has no measured confidence."),
            **{**common, "notes_text": "M1 base-rate control row"}))
    return rows


def write_decision_forecasts(books: Iterable[PaperBook], *,
                             conn: sqlite3.Connection, asof: date,
                             path: Path | None = None) -> dict:
    """Build and append the rows. Returns what was written, for the receipt."""
    rows = build_rows(books, conn=conn, asof=asof)
    if not rows:
        return {"n_rows": 0, "reason": ("no book had both a decision and a twin "
                                        "this pass -- nothing to forecast about")}
    append(rows, path if path is not None else DEFAULT_LEDGER)
    return {"n_rows": len(rows),
            "mechanism_id": MECHANISM_ID,
            "prediction_ids": [r.prediction_id for r in rows],
            "books": sorted({r.ticker for r in rows}),
            "horizons": sorted({r.horizon_days for r in rows}),
            "note": ("one row per book against its first twin, plus the twin's "
                     "own base-rate row at p=0.5 in the same ledger")}


__all__ = ["BASE_RATE", "MECHANISM_ID", "build_rows", "probability_from_ir",
           "trailing_ir", "write_decision_forecasts"]
