"""The forward EXPERIENCE writer — the piece that never existed.

Schema-compatible with the night3 store (`Aegis module\\aegis_brain\\night3\\
experience.py`) and the 2026-08-09 memory-taxonomy design: one record per
graded decision, information state hashed before outcomes exist, outcomes
matured later and NEVER visible at decision time.

Two append-only files instead of one mutable one:
  experiences.jsonl          one row per decision (chosen AND rejected)
  experience_outcomes.jsonl  one row per (experience_id, horizon) at maturity

Write-once purity is per file: a decision row is never edited, an outcome row
is never edited; joining them is the reader's job. Training rules (standing):
never on same-day P&L; reliability updates only from matured outcomes; the
unit is decision/security/information-state, never portfolio-day.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date

from backend.services.arena import store

logger = logging.getLogger(__name__)

ACTIONS = ("ENTER", "EXIT", "HOLD", "REJECT", "TRIM", "EXEMPT_TRIM", "SWAP_IN",
           "SWAP_OUT")
HORIZONS = (1, 5, 21, 63, 126)

OUTCOME_CLASSES = ("GOOD_CALL", "BAD_CALL", "GOOD_PASS", "BAD_PASS",
                   "UNRESOLVED")

#: Actions that actually move capital. HOLD and REJECT have a forecast leg but
#: no fill, so their execution leg is a counterfactual, not a realised trade.
TRADING_ACTIONS = frozenset({"ENTER", "EXIT", "SWAP_IN", "SWAP_OUT", "TRIM"})

#: Outcome-row schema. v1 carried ONE close→close leg and called it the
#: outcome; v2 carries the forecast leg and the execution leg separately,
#: because the paper book fills at the NEXT session's open and an overnight gap
#: that happened before the fill is not a fact about the decision. A reader
#: that pools v1 and v2 rows in one statistic is pooling two questions —
#: `reliability.py` refuses to.
OUTCOME_SCHEMA_VERSION = 2

FORECAST_BASIS = "decision_close_to_close_plus_h"
EXECUTION_BASIS = "next_open_to_open_plus_h"


class ExperienceInvalid(ValueError):
    pass


def _hash(payload) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]


def make_experience(*, book_id: str, policy_version: int, ticker: str,
                    action: str, decision_date: str,
                    information_state_hash: str, model_id: str,
                    thesis: str, confidence: float | None = None,
                    invalidation: str = "", weight: float | None = None,
                    rank: int | None = None, score: float | None = None,
                    chosen_alternative: str | None = None,
                    llm_prediction_id: str | None = None) -> dict:
    """One decision record. Refuses what cannot be graded later."""
    if action not in ACTIONS:
        raise ExperienceInvalid(f"action {action!r} not in {ACTIONS}")
    if confidence is not None and not (0.0 <= confidence <= 1.0):
        raise ExperienceInvalid(f"confidence {confidence} not in [0,1]")
    if not information_state_hash:
        raise ExperienceInvalid("an experience without an information state "
                                "cannot be replayed, only rationalized")
    rec = {
        "experience_id": _hash([information_state_hash, book_id, ticker,
                                action, decision_date]),
        "ts": decision_date,
        "book_id": book_id,
        "policy_version": policy_version,
        "entity_key": ticker,
        "action": action,
        "direction": "long",
        "information_state_hash": information_state_hash,
        "model_id": model_id,
        "brain_version": f"arena-gen1-{book_id}@p{policy_version}",
        "thesis": thesis,
        "confidence": confidence,
        "invalidation": invalidation,
        "weight": weight,
        "rank": rank,
        "score": score,
        "chosen_alternative": chosen_alternative,
        "llm_prediction_id": llm_prediction_id,
        "validation_status": "PRODUCT_EXPERIMENT",
        "simulation": True,
    }
    return rec


def classify_outcome(action: str, excess_return: float | None) -> str:
    if excess_return is None:
        return "UNRESOLVED"
    took = action in ("ENTER", "HOLD", "SWAP_IN", "EXEMPT_TRIM")
    if took:
        return "GOOD_CALL" if excess_return > 0 else "BAD_CALL"
    return "GOOD_PASS" if excess_return <= 0 else "BAD_PASS"


def _leg(px0: float | None, px1: float | None,
         b0: float | None, b1: float | None) -> tuple:
    """(realized, benchmark, excess) for one window, or Nones."""
    realized = (px1 / px0 - 1.0) if (px0 and px1) else None
    bench = (b1 / b0 - 1.0) if (b0 and b1) else None
    excess = (realized - bench) if (realized is not None
                                    and bench is not None) else None
    return realized, bench, excess


def mature_outcomes(panel, *, benchmark: str = "SPY", today: date | None = None,
                    root=None) -> dict:
    """Resolve every (experience, horizon) whose windows have closed.

    TWO legs per row, because they answer two different questions and mixing
    them attributes an overnight gap the book never traded through to the
    decision that preceded it:

      forecast  close(d0) → close(d0+h)      "was the belief right?"
      execution open(d0+1) → open(d0+1+h)    "what could the book capture?"

    A row is written only when BOTH windows have closed — one session later
    than the forecast leg alone. That costs a day of latency and buys an
    immutable row: the files are append-only, so a row written with a pending
    execution leg could never be completed, only contradicted.

    Paired regret for REJECT rows is left to the reader (both legs carry the
    same information_state_hash) — storing a joined number would freeze one
    definition of regret into the ledger.
    """
    sessions = panel.sessions()
    if today is not None:
        sessions = [s for s in sessions if s <= today]
    if not sessions:
        return {"resolved": 0, "reason": "no_sessions"}
    sindex = {s: i for i, s in enumerate(sessions)}
    done = {(o["experience_id"], o["horizon_days"])
            for o in store.read_outcomes(root)}
    out_rows: list[dict] = []
    n_price_holes = 0
    for e in store.read_experiences(root):
        try:
            d0 = date.fromisoformat(str(e["ts"])[:10])
        except ValueError:
            continue
        i0 = sindex.get(d0)
        if i0 is None:
            continue
        tkr = e["entity_key"]
        for h in HORIZONS:
            key = (e["experience_id"], h)
            # i0 + 1 + h is the execution exit session; requiring it (not just
            # i0 + h) is what makes the row complete on first write.
            if key in done or i0 + 1 + h >= len(sessions):
                continue
            d1 = sessions[i0 + h]
            f_ret, f_bench, f_excess = _leg(
                panel.close_price(tkr, d0), panel.close_price(tkr, d1),
                panel.close_price(benchmark, d0),
                panel.close_price(benchmark, d1))
            e0, e1 = sessions[i0 + 1], sessions[i0 + 1 + h]
            x_ret, x_bench, x_excess = _leg(
                panel.open_price(tkr, e0), panel.open_price(tkr, e1),
                panel.open_price(benchmark, e0),
                panel.open_price(benchmark, e1))
            if f_ret is None or x_ret is None:
                n_price_holes += 1
            out_rows.append({
                "schema_version": OUTCOME_SCHEMA_VERSION,
                "experience_id": e["experience_id"],
                "book_id": e["book_id"],
                "entity_key": tkr,
                "action": e["action"],
                "traded": e["action"] in TRADING_ACTIONS,
                "horizon_days": h,
                "decision_date": str(d0),
                "resolved_date": str(d1),
                # ── forecast leg (the belief question) ──
                "basis": FORECAST_BASIS,
                "realized_return": f_ret,
                "benchmark_return": f_bench,
                "excess_return": f_excess,
                "outcome_class": classify_outcome(e["action"], f_excess),
                "price_missing": f_ret is None,
                # ── execution leg (the capturable question) ──
                "execution_basis": EXECUTION_BASIS,
                "execution_entry_date": str(e0),
                "execution_exit_date": str(e1),
                "execution_realized_return": x_ret,
                "execution_benchmark_return": x_bench,
                "execution_excess_return": x_excess,
                "execution_outcome_class": classify_outcome(e["action"],
                                                            x_excess),
                "execution_price_missing": x_ret is None,
            })
            done.add(key)
    store.append_outcomes(out_rows, root)
    return {"resolved": len(out_rows), "price_holes": n_price_holes,
            "schema_version": OUTCOME_SCHEMA_VERSION}


# ── perception grading ──────────────────────────────────────────────────────
def close_frame(panel, tickers, *, today: date | None = None):
    """A pandas close panel (DatetimeIndex × tickers) built from the injected
    price protocol, so the same code grades a live panel and a test stub.

    A ticker with no usable prices is LEFT OUT rather than filled with NaN:
    `belief_state.resolve_one` distinguishes "absent from the frame — this
    record can never resolve" from "not yet due", and an all-NaN column would
    collapse that distinction into a silent backlog.
    """
    import pandas as pd

    fast = getattr(panel, "close_frame_fast", None)
    if callable(fast):
        return fast(tickers, today=today)
    sessions = [s for s in panel.sessions() if today is None or s <= today]
    if not sessions:
        return pd.DataFrame()
    cols = {}
    for t in sorted(set(tickers)):
        col = [panel.close_price(t, s) for s in sessions]
        if any(v is not None for v in col):
            cols[t] = col
    if not cols:
        return pd.DataFrame()
    return pd.DataFrame(cols, index=pd.to_datetime([str(s) for s in sessions]))


def resolve_perceptions(panel, *, today: date | None = None, root=None) -> dict:
    """Grade every arena LLM prediction whose window has closed.

    The arena mints gradeable PredictionRecords at every decision and, until
    this ran, nothing ever scored them — a forecasting ledger that only ever
    grows is a diary. Grades the ARENA ledger only; `predictions.jsonl`'s
    evidence populations are spoken for and are never touched from here.
    """
    from backend.services import belief_state as B

    path = store.predictions_path(root)
    rows = store._read_jsonl(path)
    if not rows:
        return {"status": "no_records", "total": 0, "newly_resolved": 0}
    tickers = {str(r.get("ticker")) for r in rows if r.get("ticker")}
    tickers |= {str(r.get("benchmark")) for r in rows if r.get("benchmark")}
    prices = close_frame(panel, tickers, today=today)
    if getattr(prices, "empty", True):
        # Loud: an empty frame resolves nothing and would otherwise look
        # identical to "nothing was due".
        logger.warning("ARENA: perception grading has NO price frame for %d "
                       "ticker(s) — 0 records graded, none are due-and-missed",
                       len(tickers))
        return {"status": "no_price_frame", "total": len(rows),
                "newly_resolved": 0, "tickers_wanted": len(tickers)}
    out = B.resolve_all(prices, path, today=today)
    out["status"] = "ok"
    out["tickers_priced"] = int(prices.shape[1])
    return out
