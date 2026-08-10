"""Forward shadow portfolios — where a finalist earns its evidence, or doesn't.

The Arena ranks hundreds of policies on history. History is the one thing every
policy in the Arena has already seen, so a high rank there is a hypothesis, not
a track record. This module is where a small set of finalists starts producing
evidence nobody has looked at yet.

WHAT THIS IS NOT
----------------
* Not a lane. It never writes `paper_nav`, never touches `book_lanes.yaml`,
  never flips a flag. The ten live lanes are a separate, older instrument with
  their own inception dates and their own discipline.
* Not a trading system. There is no order path in this module and there is not
  going to be one.
* Not three hundred books. The hundreds belong in the historical Arena; a
  forward register with three hundred entries is a guarantee that one of them
  will look brilliant in a year for no reason. The finalist set is small and
  each entry names the mechanism family it represents.

THE FIREWALL, WHICH IS THE POINT
--------------------------------
Murat's instruction: the system should learn from outcomes, and the LLM must
never turn P&L into a position size. Those are compatible only if the path from
outcome to decision is explicit and deterministic:

    outcome ──> LearningSample ledger  (append-only, PIT, immutable)
                      │
                      ▼
            deterministic reliability update  (versioned, reversible)
                      │
                      ▼
            signal registry reliability_weight
                      │
                      ▼
            engine sizing arithmetic

The LLM may read a CALIBRATED reliability figure at the bottom of that chain.
It may not read the ledger, and there is no function here that returns a P&L to
a caller that also sizes anything. `record_outcome` writes; it does not return
a number anyone can trade on.

EVERY DECISION FREEZES ITS OWN EVIDENCE. A shadow decision that cannot say what
it knew at the time is worthless a year later, because there is no way to tell
whether it was right for its reasons or lucky. So each decision stores the
weights, the signal contributions, the evidence grades, the expected return and
risk, the cost assumption, the catalysts and the kill conditions — at decision
time, never refreshed.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

DATA = Path(__file__).resolve().parents[1] / "data"
REGISTRY_PATH = DATA / "shadow_portfolios.yaml"
DECISIONS = DATA / "shadow_decisions.jsonl"
LEARNING = DATA / "learning_samples.jsonl"

SCHEMA = "shadow-v1"

#: Rows that could not be parsed on the last read. A ledger that silently drops
#: a corrupt line returns a shorter, healthier-looking history — BUILD-1.1
#: found exactly that bug in analyst_ledger and it is not repeated here.
MALFORMED_ROWS: list[dict] = []


class ShadowError(RuntimeError):
    """A shadow record cannot be trusted. Never degrade quietly."""


@dataclass
class ShadowDecision:
    """One dated decision by one shadow portfolio. Immutable once written."""
    shadow_id: str
    decided_at: str
    as_of: str
    weights: dict[str, float]
    signal_contributions: dict[str, dict[str, float]]
    evidence_grades: dict[str, str]
    expected_return: dict[str, float]
    expected_risk: dict[str, float]
    cost_assumption: dict[str, Any]
    catalysts: dict[str, list] = field(default_factory=dict)
    kill_conditions: dict[str, str] = field(default_factory=dict)
    nav_basis: float = 100.0
    notes: str = ""
    schema: str = SCHEMA

    def payload_hash(self) -> str:
        blob = json.dumps({k: v for k, v in asdict(self).items()
                           if k != "decided_at"},
                          sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def validate(self) -> list[str]:
        bad: list[str] = []
        if not self.shadow_id:
            bad.append("no shadow_id")
        if not self.weights:
            bad.append("a decision with no weights is not a decision")
        tot = sum(self.weights.values())
        if tot > 1.0001:
            bad.append(f"weights sum to {tot:.4f} > 1 — leverage is not "
                       f"modelled and must not be implied")
        for t, w in self.weights.items():
            if w < 0:
                bad.append(f"{t}: negative weight — these books are long only")
        missing = [t for t in self.weights if t not in self.expected_return]
        if missing:
            bad.append(f"held with no expected return recorded: {missing[:5]} "
                       f"— a decision must say what it expected, or its "
                       f"outcome cannot grade it")
        return bad


def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def _read(path: Path) -> list[dict]:
    MALFORMED_ROWS.clear()
    if not path.exists():
        return []
    out: list[dict] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as exc:
            MALFORMED_ROWS.append({"file": str(path), "line": i,
                                   "error": str(exc)[:120]})
    if MALFORMED_ROWS:
        logger.error("%s: %d unparseable row(s) — the history you are reading "
                     "is SHORTER than the history on disk", path.name,
                     len(MALFORMED_ROWS))
    return out


def record_decision(decision: ShadowDecision, *, strict: bool = True) -> dict:
    problems = decision.validate()
    if problems and strict:
        raise ShadowError("this shadow decision cannot be recorded:\n  - "
                          + "\n  - ".join(problems))
    row = asdict(decision)
    row["payload_hash"] = decision.payload_hash()
    row["recorded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if problems:
        row["problems"] = problems
    _append(DECISIONS, row)
    return row


def decisions(shadow_id: str | None = None) -> list[dict]:
    rows = _read(DECISIONS)
    return [r for r in rows if shadow_id is None or r.get("shadow_id") == shadow_id]


# ────────────────────────── the learning ledger ─────────────────────────────

@dataclass
class LearningSample:
    """What actually happened, attached to what was expected and why.

    This is the ONLY object in the system through which an outcome may
    influence a future decision, and it does so through a deterministic
    reliability update rather than by being read as a number.
    """
    shadow_id: str
    decision_hash: str
    decided_as_of: str
    resolved_as_of: str
    horizon_days: int
    realised_return: float
    expected_return: float
    benchmark_return: Optional[float] = None
    signal_contributions: dict[str, float] = field(default_factory=dict)
    evidence_grades: dict[str, str] = field(default_factory=dict)
    n_names: int = 0
    notes: str = ""
    schema: str = SCHEMA

    @property
    def forecast_error(self) -> float:
        return self.realised_return - self.expected_return


def record_outcome(sample: LearningSample) -> None:
    """Append one resolved outcome. Returns NOTHING, deliberately.

    A function that both records a P&L and hands it back is one refactor away
    from being called inside a sizing routine. This one is a dead end by
    construction: to use an outcome you must go through
    `update_reliability()`, which is deterministic, versioned and reversible.
    """
    row = asdict(sample)
    row["forecast_error"] = sample.forecast_error
    row["recorded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _append(LEARNING, row)


def learning_samples(shadow_id: str | None = None) -> list[dict]:
    rows = _read(LEARNING)
    return [r for r in rows if shadow_id is None or r.get("shadow_id") == shadow_id]


#: Below this many resolved samples a reliability estimate is not an estimate.
#: The number is a judgement, and it is deliberately high enough that no signal
#: in this system will reach it for months.
MIN_SAMPLES_TO_CALIBRATE = 30

#: How far one update may move a weight. A reliability that can jump from 0.5
#: to 0.9 on a good quarter is a P&L-chasing loop wearing a Bayesian hat.
MAX_STEP = 0.05


def update_reliability(signal_id: str, *, samples: list[dict] | None = None,
                       prior: float | None = None) -> dict:
    """Deterministic, bounded, reversible reliability update.

    Shrinkage toward the prior, weighted by how much evidence there is. No
    optimiser, no likelihood surface, no neural anything — the simplest thing
    that can be audited, which is what the mandate asks for before anything
    more ambitious.

    Returns a PROPOSAL. It does not write the registry: changing what the PM is
    allowed to believe is an attended act, and it leaves a diff.
    """
    from backend.services import signal_registry as SR

    rows = samples if samples is not None else learning_samples()
    rel = [r for r in rows if signal_id in (r.get("signal_contributions") or {})]
    reg = SR.load()
    current = prior if prior is not None else reg.get(signal_id).weight

    out = {
        "signal_id": signal_id,
        "n_samples": len(rel),
        "current_weight": current,
        "proposed_weight": current,
        "status": "UNCALIBRATED",
        "applied": False,
        "why": "",
    }
    if len(rel) < MIN_SAMPLES_TO_CALIBRATE:
        out["why"] = (
            f"{len(rel)} resolved sample(s), floor {MIN_SAMPLES_TO_CALIBRATE}. "
            f"Until then reliability stays UNCALIBRATED, which the engine reads "
            f"as UNKNOWN (0.5) — never as 1.0.")
        return out

    # Hit rate of the signal's contribution against realised excess return.
    hits = 0
    for r in rel:
        contrib = (r.get("signal_contributions") or {}).get(signal_id, 0.0)
        excess = float(r.get("realised_return", 0.0)) - float(
            r.get("benchmark_return") or 0.0)
        if contrib * excess > 0:
            hits += 1
    hit_rate = hits / len(rel)

    # Shrink the observed hit rate toward the prior by sample weight, then cap
    # the step. Chance is 0.5, so the signal is the DISTANCE from chance.
    n = len(rel)
    k = n / (n + MIN_SAMPLES_TO_CALIBRATE)
    target = max(0.0, min(1.0, 2.0 * (hit_rate - 0.5) + 0.5))
    proposed = current + k * (target - current)
    proposed = max(current - MAX_STEP, min(current + MAX_STEP, proposed))

    out.update(
        status="CALIBRATED", hit_rate=round(hit_rate, 4),
        shrink_k=round(k, 4), target_weight=round(target, 4),
        proposed_weight=round(max(0.0, min(1.0, proposed)), 4),
        why=(f"{n} resolved samples, hit rate {hit_rate:.1%} against chance "
             f"50%. Shrunk toward the current weight by k={k:.2f} and capped "
             f"at +/-{MAX_STEP}. This is a PROPOSAL — applying it to the "
             f"registry is an attended edit that leaves a diff."))
    return out


def firewall_report() -> dict:
    """State the firewall as a checkable fact, not a convention."""
    return {
        "outcomes_reach_decisions_through": [
            "learning_samples.jsonl (append-only)",
            "update_reliability() — deterministic, bounded, reversible",
            "signal_registry reliability_weight (attended edit)",
            "engine sizing arithmetic",
        ],
        "llm_may_read": "a calibrated reliability weight, after the above",
        "llm_may_not_read": "the learning ledger, or any P&L series",
        "record_outcome_returns": None,
        "max_single_update_step": MAX_STEP,
        "min_samples_to_calibrate": MIN_SAMPLES_TO_CALIBRATE,
        "note": (
            "record_outcome() returns None on purpose. A function that both "
            "records a P&L and hands it back is one refactor away from being "
            "called inside a sizing routine."),
    }
