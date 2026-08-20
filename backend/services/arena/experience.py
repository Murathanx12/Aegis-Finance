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
from datetime import date

from backend.services.arena import store

ACTIONS = ("ENTER", "EXIT", "HOLD", "REJECT", "TRIM", "EXEMPT_TRIM", "SWAP_IN",
           "SWAP_OUT")
HORIZONS = (1, 5, 21, 63, 126)

OUTCOME_CLASSES = ("GOOD_CALL", "BAD_CALL", "GOOD_PASS", "BAD_PASS",
                   "UNRESOLVED")


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


def mature_outcomes(panel, *, benchmark: str = "SPY", today: date | None = None,
                    root=None) -> dict:
    """Resolve every (experience, horizon) whose window has closed.

    Realized return is close→close over `horizon` SESSIONS from the decision
    date; excess is vs the benchmark over the same window. Paired regret for
    REJECT rows is left to the reader (both legs carry the same
    information_state_hash) — storing a joined number would freeze one
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
    for e in store.read_experiences(root):
        try:
            d0 = date.fromisoformat(str(e["ts"])[:10])
        except ValueError:
            continue
        i0 = sindex.get(d0)
        if i0 is None:
            continue
        for h in HORIZONS:
            key = (e["experience_id"], h)
            if key in done or i0 + h >= len(sessions):
                continue
            d1 = sessions[i0 + h]
            p0 = panel.close_price(e["entity_key"], d0)
            p1 = panel.close_price(e["entity_key"], d1)
            b0 = panel.close_price(benchmark, d0)
            b1 = panel.close_price(benchmark, d1)
            realized = (p1 / p0 - 1.0) if (p0 and p1) else None
            bench = (b1 / b0 - 1.0) if (b0 and b1) else None
            excess = (realized - bench) if (realized is not None
                                            and bench is not None) else None
            out_rows.append({
                "experience_id": e["experience_id"],
                "book_id": e["book_id"],
                "entity_key": e["entity_key"],
                "action": e["action"],
                "horizon_days": h,
                "decision_date": str(d0),
                "resolved_date": str(d1),
                "realized_return": realized,
                "benchmark_return": bench,
                "excess_return": excess,
                "outcome_class": classify_outcome(e["action"], excess),
                "price_missing": realized is None,
            })
            done.add(key)
    store.append_outcomes(out_rows, root)
    return {"resolved": len(out_rows)}
