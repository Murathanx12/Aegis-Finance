"""The spine: what Optimus believes, and the record that lets it be wrong.

WHY THIS IS THE PREREQUISITE
============================

Murat wants Optimus to work as a brain that talks back and forth with an agent
about what to buy. The blocker has never been that the MCP is read-only. It is
that there has been **no shared object to talk about** — no per-security belief
either side can point at, and no forecast that can later be scored. Making the
channel writable without that just adds chat.

Two objects fix it:

* `BeliefState` — what Optimus currently thinks about one security, including
  what the MARKET appears to think, so the interesting quantity (the gap between
  them) is representable rather than implied.
* `PredictionRecord` — a falsifiable claim with a resolution date, frozen inputs
  and a machine-checkable rule. This is the unit that turns "the LLM said
  something" into "the LLM was right 61% of the time on 6-month biotech
  catalysts and overconfident by 14 points."

THE CLOCK ONLY RUNS FORWARD
---------------------------
Forward calibration accrues from the first written record and from no earlier
date. Every night without records is a night of calibration that cannot be
recovered later, which is why this ships before the analysis that would justify
it. NIGHT-3 measured that the LLM earns no role in stock selection (t 0.04 and
0.93 over 16,320 decisions); that finding is about ORDERING stocks. This
measures something it was never asked: whether its stated probabilities are
calibrated. Those are different questions and the second one has never had an
instrument.

WHAT A PREDICTION MAY BE ABOUT
------------------------------
Only observables a machine can resolve without a human, from data the programme
already has. A claim nobody can grade is not a prediction; it is prose with a
number in it. The four supported observables deliberately include two about the
SHAPE of the payoff rather than its direction — a binary-catalyst biotech is not
a small normally-distributed edge, and `ABS_MOVE_EXCEEDS` is how a probability
tree gets stated in a form the engine can score.

THE FIREWALL
------------
A PredictionRecord carries no weight, no size and no position. The LLM proposes
and forecasts; the engine computes and allocates. `record_outcome()` returns
None, by house rule, so no caller can branch on a write.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LEDGER_DIR = Path(__file__).resolve().parents[1] / "data" / "optimus"
PREDICTIONS = LEDGER_DIR / "predictions.jsonl"
BELIEFS = LEDGER_DIR / "beliefs.jsonl"

SCHEMA_VERSION = "1.0.0"

#: Horizons, in trading days. Frozen: a horizon invented after the fact is a
#: degree of freedom, and the resolution date is what makes a record honest.
HORIZONS = (5, 20, 60, 120, 252)


class Observable(str, Enum):
    """What a prediction can be ABOUT.

    Every member resolves from adjusted closes alone, with no human judgment and
    no vendor whose definition can drift.
    """
    RETURN_SIGN = "return_sign"                 # P(total return > 0)
    BEATS_BENCHMARK = "beats_benchmark"         # P(stock return > benchmark)
    ABS_MOVE_EXCEEDS = "abs_move_exceeds"       # P(|return| > threshold)
    DRAWDOWN_EXCEEDS = "drawdown_exceeds"       # P(max drawdown > threshold)


def _hash(payload: Any) -> str:
    """Stable content hash. Two records with the same hash saw the same world."""
    blob = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


@dataclass
class ScenarioLeg:
    """One branch of a probability tree.

    The object the external reviews correctly said Aegis could not evaluate: a
    clinical-stage biotech is not an average-alpha anomaly, it is a small number
    of branches with very different payoffs. Stating it this way makes the
    implied expected value computable and the branch probabilities scoreable.
    """
    label: str
    probability: float
    price_target: float | None = None
    rationale: str = ""


@dataclass
class BeliefState:
    """What Optimus thinks about one security, and what the market seems to.

    The Murat-style fields are not decoration. His process was thematic and
    catalyst-driven — `theme`, `causal_chain`, `adoption_stage`,
    `catalyst_timeline` are the parts of it a machine can carry. `thesis_breakers`
    and `next_observable` are the parts his process was MISSING: he held NTLA
    waiting for a price it once printed, which is an anchor rather than a thesis,
    and an anchor cannot be falsified because it makes no claim about the world.
    """
    ticker: str
    as_of: str
    theme: str = ""
    causal_chain: list[str] = field(default_factory=list)
    adoption_stage: str = ""
    catalyst_timeline: list[dict] = field(default_factory=list)
    scenarios: list[ScenarioLeg] = field(default_factory=list)
    payoff_skew: str = ""
    thesis_breakers: list[str] = field(default_factory=list)
    next_observable: str = ""
    market_implied_expectation: str = ""
    optimus_expectation: str = ""
    dislocation: str = ""
    regime_sensitivity: str = ""
    replacement_edge: str = ""
    confidence: float | None = None
    source: str = ""
    schema_version: str = SCHEMA_VERSION

    def expected_value(self) -> float | None:
        """Probability-weighted target, when the tree is complete enough to have
        one. Returns None rather than a number built on branches that do not sum
        to one — an EV from an incoherent tree is worse than no EV."""
        legs = [s for s in self.scenarios if s.price_target is not None]
        if not legs:
            return None
        total = sum(s.probability for s in self.scenarios)
        if not 0.97 <= total <= 1.03:
            logger.warning("%s: scenario probabilities sum to %.3f, not 1 — no "
                           "expected value computed", self.ticker, total)
            return None
        return sum(s.probability * s.price_target for s in legs)


@dataclass
class PredictionRecord:
    """A falsifiable claim with a resolution date and a machine-checkable rule."""
    prediction_id: str
    ticker: str
    specialist: str
    observable: str
    horizon_days: int
    probability: float
    threshold: float | None
    benchmark: str | None
    made_at: str
    resolves_after: str
    thesis: str
    counter_thesis: str
    next_observable: str
    model: str
    model_version: str
    prompt_hash: str
    input_snapshot_hash: str
    schema_version: str = SCHEMA_VERSION
    # filled at resolution, never at write time
    resolved_at: str | None = None
    void_reason: str | None = None
    outcome: int | None = None
    brier: float | None = None
    resolution_detail: dict = field(default_factory=dict)

    @staticmethod
    def resolution_date(made_at: str, horizon_days: int) -> str:
        """Calendar date by which the horizon has certainly elapsed.

        Trading days are converted with a deliberately generous factor: a record
        that claims to be resolvable before its window has closed would be graded
        on a partial outcome, and grading early is indistinguishable from being
        right early.
        """
        d = datetime.fromisoformat(made_at).date()
        return str(d + timedelta(days=int(horizon_days * 1.45) + 3))


def make_prediction(*, ticker: str, specialist: str, observable: Observable,
                    horizon_days: int, probability: float, thesis: str,
                    counter_thesis: str, next_observable: str, model: str,
                    model_version: str, prompt: str, input_snapshot: Any,
                    threshold: float | None = None,
                    benchmark: str | None = None,
                    made_at: str | None = None) -> PredictionRecord:
    """Build a record, refusing the ones that cannot be graded."""
    if horizon_days not in HORIZONS:
        raise ValueError(f"horizon {horizon_days} is not one of {HORIZONS}; a "
                         f"horizon chosen per-prediction is a free parameter")
    if not 0.0 <= probability <= 1.0:
        raise ValueError(f"probability {probability} is not a probability")
    if observable in (Observable.ABS_MOVE_EXCEEDS, Observable.DRAWDOWN_EXCEEDS):
        if threshold is None or threshold <= 0:
            raise ValueError(f"{observable} needs a positive threshold or there "
                             f"is nothing to resolve against")
        if threshold >= 1.0:
            # A percent/fraction mixup does not fail — it silently converts a
            # forecast into one that cannot come true. "|move| > 20.0" is a
            # 2000% move; at p=0.75 that is a guaranteed-wrong record scored
            # against a specialist whose judgment had nothing to do with it.
            # The first live run produced six of these, ALL from one specialist,
            # so the damage was systematic rather than scattered.
            raise ValueError(
                f"threshold {threshold} for {observable} must be a decimal "
                f"fraction below 1.0 (0.25 = 25%). A value at or above 1 is "
                f"almost certainly percent, and coercing it would be guessing "
                f"at what the forecaster meant")
    if observable is Observable.BEATS_BENCHMARK and not benchmark:
        raise ValueError("BEATS_BENCHMARK needs a benchmark")
    made_at = made_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    snap = _hash(input_snapshot)
    ph = _hash(prompt)
    pid = _hash([ticker, specialist, observable.value, horizon_days, made_at,
                 snap, ph])
    return PredictionRecord(
        prediction_id=pid, ticker=ticker, specialist=specialist,
        observable=observable.value, horizon_days=horizon_days,
        probability=float(probability), threshold=threshold,
        benchmark=benchmark, made_at=made_at,
        resolves_after=PredictionRecord.resolution_date(made_at, horizon_days),
        thesis=thesis.strip(), counter_thesis=counter_thesis.strip(),
        next_observable=next_observable.strip(), model=model,
        model_version=model_version, prompt_hash=ph, input_snapshot_hash=snap)


def append(records: list[PredictionRecord], path: Path | None = None) -> None:
    """Append to the ledger. Returns None: nothing may branch on a write."""
    path = path or PREDICTIONS
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = {r["prediction_id"] for r in read_predictions(path)}
    with path.open("a", encoding="utf-8") as fh:
        for r in records:
            if r.prediction_id in seen:
                logger.warning("%s already in the ledger — a duplicate record "
                               "would be scored twice", r.prediction_id)
                continue
            fh.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
            seen.add(r.prediction_id)
    logger.info("ledger: %d record(s) written to %s", len(records), path)


def read_predictions(path: Path | None = None) -> list[dict]:
    path = path or PREDICTIONS
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def append_belief(states: list[BeliefState], path: Path | None = None) -> None:
    """Append belief states. Append-only: a belief that was held and later
    abandoned is the record of a mind changing, and overwriting it deletes the
    only evidence that it did."""
    path = path or BELIEFS
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for s in states:
            fh.write(json.dumps(asdict(s), ensure_ascii=False) + "\n")
    logger.info("beliefs: %d state(s) written to %s", len(states), path)


# ── resolution ──────────────────────────────────────────────────────────────
def resolve_one(rec: dict, prices, *, today: date | None = None) -> dict | None:
    """Grade one record against prices. None if its window has not closed.

    Grading early is indistinguishable from being right early, so a record whose
    resolution date has not arrived is left alone rather than scored on a partial
    window.

    `today` is injectable so callers (and tests) can grade as-of a date without
    monkeypatching the clock; default is the real date.today().
    """
    import pandas as pd

    if rec.get("void_reason"):
        # A void record stays in the ledger as evidence that it was made, and
        # stays out of every score. Deleting it would hide a defect; grading it
        # would charge a forecaster for the defect.
        return None
    if rec.get("outcome") is not None:
        return rec
    today = today or date.today()
    if today < date.fromisoformat(rec["resolves_after"][:10]):
        return None
    tkr = rec["ticker"]
    if tkr not in prices.columns:
        # Distinguishable from "not yet due": a record whose security is absent
        # from the price frame will NEVER resolve, and counting it as pending
        # hides a permanently dark forecast behind a growing backlog.
        logger.warning("%s: %s is not in the price frame — this record can "
                       "never resolve", rec["prediction_id"], tkr)
        return None
    start = pd.Timestamp(rec["made_at"][:10])
    s = prices[tkr].loc[start:].dropna()
    # The window is horizon_days + 1 bars (entry bar + horizon). Grading on
    # fewer bars grades a shorter horizon than the forecast committed to.
    if len(s) < rec["horizon_days"] + 1:
        return None
    w = s.iloc[: rec["horizon_days"] + 1]
    ret = float(w.iloc[-1] / w.iloc[0] - 1.0)
    obs = rec["observable"]
    detail = {"realised_return": ret, "n_bars": len(w)}

    if obs == Observable.RETURN_SIGN.value:
        outcome = int(ret > 0)
    elif obs == Observable.BEATS_BENCHMARK.value:
        if rec["benchmark"] not in prices.columns:
            # Same failure class as a missing ticker: without the benchmark
            # column this record can never resolve, and raising here would take
            # every OTHER record in the batch down with it.
            logger.warning("%s: benchmark %s is not in the price frame — this "
                           "record can never resolve", rec["prediction_id"],
                           rec["benchmark"])
            return None
        b = prices[rec["benchmark"]].loc[start:].dropna()
        # Same window guard as the ticker leg: a truncated benchmark series
        # (e.g. a frozen CSV ending mid-window beside a fresh-fetched ticker)
        # would otherwise grade a full-horizon return against a partial one and
        # write a permanently wrong outcome with status ok.
        if len(b) < rec["horizon_days"] + 1:
            logger.warning("%s: benchmark %s has %d bars < horizon %d + 1 — "
                           "not graded this run", rec["prediction_id"],
                           rec["benchmark"], len(b), rec["horizon_days"])
            return None
        b = b.iloc[: rec["horizon_days"] + 1]
        bret = float(b.iloc[-1] / b.iloc[0] - 1.0)
        detail["benchmark_return"] = bret
        outcome = int(ret > bret)
    elif obs == Observable.ABS_MOVE_EXCEEDS.value:
        outcome = int(abs(ret) > rec["threshold"])
    elif obs == Observable.DRAWDOWN_EXCEEDS.value:
        dd = float((w / w.cummax() - 1.0).min())
        detail["max_drawdown"] = dd
        outcome = int(abs(dd) > rec["threshold"])
    else:
        logger.warning("unknown observable %s — not resolved", obs)
        return None

    rec = dict(rec)
    rec["outcome"] = outcome
    rec["resolved_at"] = str(today)
    rec["brier"] = float((rec["probability"] - outcome) ** 2)
    rec["resolution_detail"] = detail
    return rec


def resolve_all(prices, path: Path | None = None, *,
                today: date | None = None) -> dict:
    """Grade every record whose window has closed. Rewrites the ledger in place.

    `today` is injectable (threaded into resolve_one and the overdue check);
    default is the real date.today().
    """
    path = path or PREDICTIONS
    today = today or date.today()
    rows = read_predictions(path)
    graded, newly = [], 0
    for r in rows:
        out = resolve_one(r, prices, today=today)
        if out is not None and r.get("outcome") is None and out.get("outcome") is not None:
            newly += 1
        graded.append(out if out is not None else r)
    if newly:
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                                  for r in graded) + "\n", encoding="utf-8")
    done = [r for r in graded if r.get("outcome") is not None]
    void = [r for r in graded if r.get("void_reason")]
    overdue = [r for r in graded
               if r.get("outcome") is None and not r.get("void_reason")
               and today >= date.fromisoformat(r["resolves_after"][:10])]
    if overdue:
        logger.warning("%d record(s) are past their resolution date and still "
                       "unresolved — check the price frame covers them", len(overdue))
    return {"total": len(graded), "resolved": len(done), "void": len(void),
            "newly_resolved": newly,
            "pending_not_yet_due": len(graded) - len(done) - len(void) - len(overdue),
            "OVERDUE_AND_UNRESOLVED": len(overdue),
            "overdue_ids": [r["prediction_id"] for r in overdue][:20],
            "health": "ok" if not overdue else "DEGRADED: forecasts past due"}


def calibration(path: Path | None = None, *, by: str = "specialist") -> dict:
    """Brier and calibration, sliced.

    Reported with the count beside every number. A Brier score on eleven
    resolved records is a description of eleven records, and the whole point of
    the ledger is that it will not be eleven forever.
    """
    rows = [r for r in read_predictions(path)
            if r.get("outcome") is not None and not r.get("void_reason")]
    if not rows:
        return {"n_resolved": 0,
                "reading": "nothing has resolved yet — the clock started when "
                           "the first record was written, and calibration is a "
                           "statement about resolved records only"}
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(str(r.get(by, "?")), []).append(r)
    out = {}
    for k, g in groups.items():
        briers = [r["brier"] for r in g]
        base = sum(r["outcome"] for r in g) / len(g)
        mean_p = sum(r["probability"] for r in g) / len(g)
        out[k] = {
            "n": len(g),
            "brier": sum(briers) / len(briers),
            "base_rate": base,
            "mean_probability": mean_p,
            "overconfidence": mean_p - base,
            "climatology_brier": base * (1 - base),
            "beats_climatology": bool(
                sum(briers) / len(briers) < base * (1 - base)),
        }
    return {"n_resolved": len(rows), "sliced_by": by, "groups": out,
            "note": ("a Brier score below climatology is the only version of "
                     "'the forecast was informative' this ledger recognises")}


def ledger_health(path: Path | None = None, *, max_quiet_days: int = 7,
                  today: date | None = None) -> dict:
    """Would anything say so if the specialists stopped writing?

    A prediction ledger is exactly the kind of subsystem that goes dark quietly:
    it fails by not growing, and an empty append looks identical to a night with
    nothing to say. This is the status row for it.

    `today` is injectable so the quiet/overdue clocks can be evaluated as-of a
    date; default is the real date.today().
    """
    today = today or date.today()
    rows = read_predictions(path)
    if not rows:
        return {"status": "DEGRADED", "n": 0,
                "reason": "the ledger is empty — no forecast has ever been "
                          "written, so no calibration can ever accrue"}
    last = max(r["made_at"][:10] for r in rows)
    quiet = (today - date.fromisoformat(last)).days
    overdue = [r for r in rows
               if r.get("outcome") is None and not r.get("void_reason")
               and today >= date.fromisoformat(r["resolves_after"][:10])]
    problems = []
    if quiet > max_quiet_days:
        problems.append(f"no new forecast in {quiet} days")
    if overdue:
        problems.append(f"{len(overdue)} forecast(s) past due and unresolved")
    return {
        "status": "ok" if not problems else "DEGRADED",
        "problems": problems,
        "n_records": len(rows),
        "n_void": sum(1 for r in rows if r.get("void_reason")),
        "n_resolved": sum(1 for r in rows if r.get("outcome") is not None),
        "n_overdue": len(overdue),
        "last_written": last,
        "days_quiet": quiet,
        "distinct_specialists": len({r["specialist"] for r in rows}),
        "distinct_models": len({f"{r['model']}:{r['model_version']}"
                                for r in rows}),
    }
