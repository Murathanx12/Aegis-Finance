"""
The Human Loop — `/api/journal/*`   (Mode A: Murat decides, the machine grades)
==============================================================================

Roadmap `docs/ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md` §2 **H2 · H4/T2 · H5**.
Licence `PRODUCT_EXPERIMENT`.

WHY THIS ROUTER EXISTS
======================
Mode A (Murat decides, the machine assists) and Mode B (the machine decides,
Murat audits) are one system at two authority levels, and **Mode A is how Mode B
gets its labels.** Nothing else in this programme produces labelled decision data
that nobody else has. Before this router, none of it was captured: the conviction
journal wrote an immutable row with a rationale and a 1-5 conviction and no
falsifier, no catalyst, no horizon and no declared hold — a row that can be
remembered and cannot be graded.

WHAT IT DOES
============
* **H2**  a decision becomes a `Thesis` (the execution repo's schema, verbatim)
          plus the three hold fields the remapped fleet made mandatory, and a
          pre-open prediction-book row under brain `human:murat`.
* **T2/H4** every decision — human AND machine — is written PENDING and resolved
          at **its own horizon** against four counterfactuals, with an `as_of`
          gate so a lesson can never be read before it was learnable.
* **H5**  the execution repo's seals, fills, refusals, autopsies and learning
          reports, mirrored read-only, visible on the web for the first time.

TWO HONESTY RULES THIS ROUTER ENFORCES IN CODE
==============================================
1. **No P&L claim under 20 graded rows.** `/scoreboard` reports process metrics
   only below the gate and stamps `claim: "a receipt, not a result"`. The number
   is `config.DECISION_LOG_MIN_GRADED_ROWS_FOR_PNL_CLAIM`, and `pnl` is `null`
   rather than a small-sample number nobody will re-check.
2. **The SPY leg names its source.** The `market` paper account (PA3I7VTCC0BM,
   `PASSIVE_BETA_v1`) holds SPY and its keys are not in this environment, so the
   benchmark counterfactual is computed from PRICE DATA. A source that cannot
   answer yields `NOT_AVAILABLE` with a reason — never 0.0, which reads as "the
   benchmark was flat" and would make it free exactly when the data was worst.

WRITE AUTHORITY
===============
Three endpoints write, and all three write **only** to append-only JSONL under
`config.HUMAN_LOOP_DIR` or into the mirror directory. Nothing here places an
order, sizes a position, seals a prediction book, or touches the paper-NAV write
path. `/terminal-state/sync` copies files ONE WAY out of the execution repo and
`backend/services/terminal_state_reader.py` is proven read-only upstream by
three separate tests.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.config import (COUNTERFACTUAL_BENCHMARK_ACCOUNT,
                            COUNTERFACTUAL_BENCHMARK_CONTRACT,
                            COUNTERFACTUAL_BENCHMARK_SYMBOL,
                            DECISION_LOG_MIN_GRADED_ROWS_FOR_PNL_CLAIM,
                            HUMAN_BOOK_BRAIN, HUMAN_LOOP_VERSION, LOSS_BUDGETS)
from backend.services import counterfactual_prices as cp
from backend.services import decision_log as dl
from backend.services import human_thesis as ht
from backend.services import terminal_state_reader as tsr

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/journal", tags=["journal"])

AUTHORITY = (
    "PRODUCT_EXPERIMENT. This surface records decisions and grades them. It "
    "places no order, sizes no position, seals no prediction book and writes "
    "nothing outside backend/data/human_loop and the read-only terminal mirror."
)


def _envelope(**kw) -> dict:
    return {"version": HUMAN_LOOP_VERSION, "licence": "PRODUCT_EXPERIMENT",
            "authority": AUTHORITY, **kw}


# ── request models ──────────────────────────────────────────────────────────
class ThesisRequest(BaseModel):
    """A journal row that can be GRADED. Every field that refuses says why."""

    symbol: str
    direction: str = Field(description="up | down | none")
    catalyst: str
    catalyst_at_utc: str = Field(description="ISO; must be AFTER stated_at")
    reason: str = Field(description=">= 10 chars; it is what gets distilled")
    falsifier: str = Field(description=">= 15 chars; what would make this WRONG")
    expected_move: Optional[float] = Field(
        default=None, description="signed fraction of spot; required with a direction")
    magnitude: str = "unknown"
    conviction: float = 1.0
    action: str = "enter"
    horizon_sessions: Optional[int] = None
    min_normal_hold_sessions: Optional[int] = None
    loss_budget_ref: Optional[str] = None
    stated_at_utc: Optional[str] = None
    entry_price: Optional[float] = None
    shares_delta: Optional[float] = None
    engine_pick_symbol: Optional[str] = None
    engine_pick_source: Optional[str] = None
    observed: Optional[bool] = None
    ranked: Optional[bool] = None
    bought: Optional[bool] = None
    decision_id_hint: Optional[int] = Field(
        default=None, description="row id from POST /api/pi/conviction/decision")


class ResolveRequest(BaseModel):
    as_of: Optional[str] = Field(default=None, description="YYYY-MM-DD; default today")
    reflect: bool = Field(default=False,
                          description="run the 2-4 sentence reflection on a FREE backend")
    limit: int = Field(default=50, ge=1, le=500)


# ── read endpoints ──────────────────────────────────────────────────────────
@router.get("")
@router.get("/")
async def overview():
    """Read this first: what exists, what it costs, and what it may claim."""
    try:
        board = dl.scoreboard()
        return _envelope(
            mode="A + B (one ledger, two authority levels — invariant 18)",
            brain=HUMAN_BOOK_BRAIN,
            schema_provenance=ht.schema_provenance(),
            loss_budgets=LOSS_BUDGETS,
            taxonomy=dl.TAXONOMY_MEANING,
            counterfactuals=list(dl.COUNTERFACTUALS),
            benchmark={"symbol": COUNTERFACTUAL_BENCHMARK_SYMBOL,
                       "account": COUNTERFACTUAL_BENCHMARK_ACCOUNT,
                       "contract": COUNTERFACTUAL_BENCHMARK_CONTRACT,
                       "keys_present": False,
                       "note": ("no key for that account is in this environment; "
                                "the SPY leg is computed from PRICE DATA and "
                                "names the source that answered")},
            price_sources=cp.source_report(),
            scoreboard=board,
            terminal_mirror=tsr.inventory(),
        )
    except Exception as e:                                       # noqa: BLE001
        logger.error("journal overview failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/decisions")
async def get_decisions(limit: int = Query(default=100, ge=1, le=500),
                        source: Optional[str] = None,
                        status: Optional[str] = None):
    """The decision log, newest first. Human and machine rows in one list."""
    rows = dl.load_decisions()
    if source:
        rows = [r for r in rows if r.get("source") == source]
    if status:
        rows = [r for r in rows if r.get("status") == status]
    rows = list(reversed(rows))[:limit]
    return _envelope(n=len(rows), rows=rows,
                     note=("`status` is the row's state at WRITE time. A row is "
                           "PENDING until its own horizon resolves; the grade "
                           "lives in /grades."))


@router.get("/grades")
async def get_grades(as_of: Optional[str] = Query(
        default=None, description="YYYY-MM-DD. Only lessons learnable BY this date."),
        decision_id: Optional[str] = None):
    """Graded rows, through the `as_of` gate.

    Asking for a named `decision_id` that had not resolved by `as_of` is a
    **425 Too Early**, not an empty list: "there is no lesson" and "the lesson
    exists and you may not have seen it yet" are opposite facts.
    """
    try:
        if as_of is None and decision_id is None:
            g = dl.load_grades()
            return _envelope(n=len(g), as_of=None, n_withheld=0, lessons=g,
                             gate_note=("no as_of was given, so nothing was "
                                        "withheld. Pass as_of to replay."))
        out = dl.lessons(as_of=as_of or "9999-12-31", decision_id=decision_id)
        return _envelope(**out)
    except dl.LessonNotYetLearnable as e:
        raise HTTPException(status_code=425, detail=str(e))
    except Exception as e:                                       # noqa: BLE001
        logger.error("journal grades failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scoreboard")
async def get_scoreboard(as_of: Optional[str] = None):
    """Process metrics, and P&L ONLY above the 20-graded-row gate."""
    try:
        return _envelope(**dl.scoreboard(as_of=as_of))
    except Exception as e:                                       # noqa: BLE001
        logger.error("journal scoreboard failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/known-answer")
async def get_known_answer():
    """The grader's known-answer battery, run live over a planted panel.

    A grader nobody has shown to produce the right regret on a constructed
    example is not a grader, so the proof is an endpoint rather than a claim in
    a document. Returns 500 if any planted case fails — a broken grader must not
    serve 200.
    """
    r = dl.known_answer_battery()
    if not r["all_pass"]:
        raise HTTPException(status_code=500,
                            detail=f"{r['n_fail']} planted cases FAILED: "
                                   f"{[c['case'] for c in r['cases'] if not c['pass']]}")
    return _envelope(**r)


@router.get("/taxonomy")
async def get_taxonomy():
    return _envelope(states=list(dl.TAXONOMY), unclassified=dl.UNCLASSIFIED,
                     meaning=dl.TAXONOMY_MEANING,
                     source=("alpha/recall.py in the execution repo, verbatim "
                             "(receipt B3_2_autopsy_and_opportunity_recall.json)"))


@router.get("/terminal-state")
async def get_terminal_state():
    """H5: what the read-only mirror holds. NEVER_SYNCED is not empty."""
    return _envelope(**tsr.inventory())


@router.get("/terminal-state/{kind}/{name}")
async def get_terminal_artefact(kind: str, name: str):
    try:
        return _envelope(**tsr.read(kind, name))
    except tsr.MirrorRefused as e:
        code = 404 if "not in the mirror" in str(e) else 422
        raise HTTPException(status_code=code, detail=str(e))


# ── write endpoints (append-only; nothing here orders or seals) ─────────────
@router.post("/thesis")
async def post_thesis(body: ThesisRequest):
    """H2: turn a journal decision into a gradeable THESIS + a PENDING row.

    422 with the schema's own refusal text when the decision cannot be graded —
    a missing falsifier, a catalyst already past, a zero minimum hold outside an
    event budget. Those are the point of the endpoint, not an inconvenience.
    """
    try:
        t = ht.build(
            symbol=body.symbol, direction=body.direction, catalyst=body.catalyst,
            catalyst_at_utc=body.catalyst_at_utc, reason=body.reason,
            falsifier=body.falsifier, expected_move=body.expected_move,
            magnitude=body.magnitude, conviction=body.conviction,
            horizon_sessions=body.horizon_sessions,
            min_normal_hold_sessions=body.min_normal_hold_sessions,
            loss_budget_ref=body.loss_budget_ref,
            stated_at_utc=body.stated_at_utc)
        sealed = ht.record(t, decision_id=body.decision_id_hint)
        row = dl.from_thesis(
            t, action=body.action, entry_price=body.entry_price,
            shares_delta=body.shares_delta,
            engine_pick_symbol=body.engine_pick_symbol,
            engine_pick_source=body.engine_pick_source,
            observed=body.observed, ranked=body.ranked, bought=body.bought)
        written = dl.record_decision(row)
    except ht.ThesisRefusal as e:
        raise HTTPException(status_code=422, detail=str(e))
    except dl.DecisionRefused as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:                                       # noqa: BLE001
        logger.error("thesis bridge failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    return _envelope(
        thesis=sealed, decision_row=written,
        book_entry=ht.export_for_seal(t),
        note=("the prediction-book row is BUILT here and SEALED by a human in "
              "the execution repo. An agent session does not seal."))


@router.post("/resolve")
async def post_resolve(body: ResolveRequest):
    """Resolve every PENDING row whose OWN horizon has arrived, and grade it.

    Idempotent in effect: a grade is append-only and `load_grades` keeps the
    newest per `decision_id`, so re-running replaces rather than duplicates.
    """
    try:
        rows = dl.load_decisions()
        already = {g.get("decision_id") for g in dl.load_grades()
                   if g.get("status") == "RESOLVED"}
        out, n_pending = [], 0
        for raw in rows[: body.limit]:
            if raw.get("decision_id") in already:
                continue
            try:
                row = dl.DecisionRow(**{k: v for k, v in raw.items()
                                        if k in dl.DecisionRow.__dataclass_fields__})
            except dl.DecisionRefused as e:
                out.append({"decision_id": raw.get("decision_id"),
                            "status": "UNGRADEABLE", "reason": str(e)})
                continue
            g = dl.resolve(row, as_of=body.as_of)
            if g["status"] == "PENDING":
                n_pending += 1
                continue
            if body.reflect:
                g["reflection"] = dl.reflect(g)
            dl.record_grade(g)
            out.append(g)
        return _envelope(n_graded=len(out), n_still_pending=n_pending,
                         as_of=body.as_of, reflected=body.reflect,
                         llm_cost_usd=sum(float((g.get("reflection") or {}).get(
                             "cost_usd") or 0.0) for g in out if isinstance(g, dict)),
                         llm_note=("reflections run on a FREE backend "
                                   "(config.DECISION_REFLECTION_BACKENDS); the "
                                   "paid provider is refused by decision_log.reflect"),
                         grades=out)
    except Exception as e:                                       # noqa: BLE001
        logger.error("journal resolve failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/terminal-state/sync")
async def post_terminal_sync():
    """H5: refresh the mirror. Copies ONE WAY; writes only inside the mirror."""
    try:
        r = tsr.sync()
        return _envelope(**{k: v for k, v in r.items() if k != "artefacts"})
    except tsr.MirrorRefused as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:                                       # noqa: BLE001
        logger.error("terminal mirror sync failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gate")
async def get_gate():
    """The honesty gate, on its own, so a page can render it without the rest."""
    b = dl.scoreboard()
    return _envelope(**b["gate"], claim=b["claim"],
                     min_rows=DECISION_LOG_MIN_GRADED_ROWS_FOR_PNL_CLAIM)
