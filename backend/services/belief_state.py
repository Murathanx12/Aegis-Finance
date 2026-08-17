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
import os
import shutil
import threading
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from backend import config as _config

logger = logging.getLogger(__name__)

#: WHERE THE LEDGER LIVES, AND WHY IT MOVED (NIGHT-14, defect F7)
#: ---------------------------------------------------------------
#: This used to be `Path(__file__).parents[1] / "data" / "optimus"` — a path
#: INSIDE the container image. On Railway the persistent volume is mounted at
#: AEGIS_DATA_DIR (=/data) and nothing else survives a deploy, so every record
#: the nightly specialists wrote was destroyed by the next push, and the forward
#: calibration clock — which starts at the first written record and cannot be
#: backfilled — would have silently restarted at zero, repeatedly, before the
#: first resolution came due (2026-09-12). The failure was invisible by
#: construction: a ledger that lost its history looks exactly like a ledger that
#: was always young.
#: Locally AEGIS_DATA_DIR is unset, DATA_DIR is backend/data, and this resolves
#: to the identical path it always had — dev is byte-for-byte unchanged.
#: Module-level names are kept (rather than functions) because every existing
#: caller and test binds `PREDICTIONS` / `BELIEFS` directly.
LEDGER_DIR = _config.OPTIMUS_LEDGER_DIR
PREDICTIONS = LEDGER_DIR / "predictions.jsonl"
BELIEFS = LEDGER_DIR / "beliefs.jsonl"

#: Ledger files carried across by the one-time migration below. Both are
#: append-only JSONL with one record per line.
LEDGER_FILES = ("predictions.jsonl", "beliefs.jsonl")

#: Set once the migration has been attempted in this process — the migration is
#: idempotent, but it should not stat the filesystem on every append.
_MIGRATION_ATTEMPTED = False

#: 1.1.0 (2026-08-14) adds the BELIEF-CHANGE contract — `prior`, `posterior`,
#: `belief_change` — as OPTIONAL fields. Purely additive: every 1.0.0 record
#: still reads, every consumer accesses by key, and `probability` remains the
#: graded quantity (it equals `posterior` when the contract is used).
#:
#: The contract exists because the old `p != 0.50` refusal solved one problem
#: and created another. It kept coin flips out of the ledger, but it also told
#: forecasters that 0.50 was rejected — an incentive to say 0.51 rather than to
#: say "this changed nothing". Under the new contract `belief_change = 0` is a
#: valid, gradeable answer, and the candidate signal is `posterior - prior`
#: rather than the level. Markets price changes in expectations, and the only
#: analyst family that ever came close to surviving in this programme was
#: revisions rather than target levels.
#: 1.2.0 (2026-08-14) adds `evidence_population` and `ledger_id`, also OPTIONAL
#: and also purely additive. Until it existed, a record could not say which of
#: the two forward ledgers it belonged to, and a report that read "the forward
#: ledger" was reading one of two different populations with no way to tell.
SCHEMA_VERSION = "1.2.0"

#: Horizons, in trading days. Frozen: a horizon invented after the fact is a
#: degree of freedom, and the resolution date is what makes a record honest.
#:
#: 1 and 2 were added on NIGHT-14 and the reason is a measurement, not taste.
#: With 5 as the floor the ledger's first grade fell on 2026-09-12 — a month of
#: nightly inference producing nothing checkable, which is the same shape as the
#: defect NIGHT-13 found (a resolver nobody called). A reaction hypothesis about
#: yesterday's move is ABOUT the next day or two; forcing it onto a 5-day
#: horizon grades a different claim than the one made. Adding the short end is
#: backward compatible: every existing record keeps its own horizon, and the
#: tuple is only ever checked for membership.
#:
#: The short end is NOT a licence to read a 1-day Brier as skill. One trading
#: day is mostly noise, so a 1d slice needs a far larger n before it says
#: anything — which is exactly why it is useful: it accrues n fast. CANON §19
#: applies unchanged; every slice prints its own count.
HORIZONS = (1, 2, 5, 20, 60, 120, 252)


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
    # ── the belief-change contract (schema 1.1.0), optional by design ───────
    #: `prior` is what the forecaster believed BEFORE seeing this evidence;
    #: `posterior` is what it believes after; `belief_change = posterior - prior`.
    #: `probability` stays the graded quantity and equals `posterior` when the
    #: contract is used, so nothing about resolution or scoring changes.
    #: All three are None on records written under the old contract.
    prior: float | None = None
    posterior: float | None = None
    belief_change: float | None = None
    #: Which experimental arm produced this record. None outside a trial that
    #: has arms. Recorded on the record rather than inferred from `specialist`,
    #: because an arm label reconstructed after the fact is not evidence.
    arm: str | None = None
    #: Which body of forward evidence this record belongs to (schema 1.2.0).
    #: There are two — the campaign's ~20,073-record history and the deployed
    #: product's own accrual — and they were read as one for a month because
    #: nothing on a record said which it was. Stamped by `append` from the
    #: ledger being written; None on every record written before 2026-08-14, and
    #: those are attributed by the file they live in. See
    #: `services/evidence_population.py`.
    evidence_population: str | None = None
    ledger_id: str | None = None
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
                    made_at: str | None = None,
                    prior: float | None = None,
                    posterior: float | None = None,
                    arm: str | None = None) -> PredictionRecord:
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
    # ── belief-change contract, when supplied ───────────────────────────────
    # Both halves or neither. A posterior with no prior is a level wearing the
    # contract's clothes, and `belief_change` computed against a missing prior
    # would silently become the posterior itself — which is exactly the level
    # this contract exists to stop being the signal.
    if (prior is None) != (posterior is None):
        raise ValueError(
            "the belief-change contract needs BOTH prior and posterior or "
            "neither; one alone cannot produce a belief change")
    belief_change = None
    if prior is not None:
        for nm, v in (("prior", prior), ("posterior", posterior)):
            if not 0.0 <= float(v) <= 1.0:
                raise ValueError(f"{nm} {v} is not a probability")
        belief_change = float(posterior) - float(prior)
        if abs(float(posterior) - float(probability)) > 1e-9:
            # `probability` is what gets graded. If it disagrees with the
            # posterior, two different numbers are being called the forecast and
            # the ledger cannot say which one the forecaster meant.
            raise ValueError(
                f"probability {probability} must equal posterior {posterior}; "
                f"the graded quantity and the stated belief cannot differ")
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
        model_version=model_version, prompt_hash=ph, input_snapshot_hash=snap,
        prior=(float(prior) if prior is not None else None),
        posterior=(float(posterior) if posterior is not None else None),
        belief_change=belief_change, arm=arm)


# ── persistence: getting the history onto the volume, exactly once ──────────
def _read_jsonl(path: Path) -> list[dict]:
    """Parse a JSONL ledger file. Raises on a malformed line, deliberately.

    A ledger file that will not parse must stop the migration rather than be
    partially copied: half a history is worse than a history in one place, and
    the corruption is a thing to be told about, not to route around.
    """
    out: list[dict] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{i} is not valid JSON: {e}") from e
    return out


def _verified_copy(src: Path, dst: Path) -> int:
    """Byte-copy src→dst and prove every record round-tripped. Returns the count.

    The copy lands on a staging file first and is only swapped in by an atomic
    `os.replace` AFTER the destination has been re-read and compared record by
    record against the source. A truncated copy (disk full, process killed
    mid-write) therefore leaves the destination untouched instead of silently
    shortening the calibration history — the whole point of the exercise is that
    these ~87 records cannot be regenerated, because forward calibration only
    accrues forward.

    Compared as parsed rows rather than by id: `beliefs.jsonl` carries no
    prediction_id, and a check that silently degrades to "both are None" on one
    of the two files is not a check.
    """
    src_rows = _read_jsonl(src)
    # Per-process staging name. Railway runs TWO replicas through a rolling
    # deploy (the same overlap that ate pi_ledger_resolve), so both can migrate
    # an empty volume at once. With a shared staging name, replica B's copyfile
    # could truncate the file replica A had just verified, and A's os.replace
    # would then publish a partial history. With a private one, each replica
    # verifies and atomically publishes its own complete copy; the loser's
    # replace is simply overwritten by an identical file.
    staging = dst.with_name(f"{dst.name}.migrating.{os.getpid()}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, staging)
    try:
        back = _read_jsonl(staging)
        if back != src_rows:
            raise ValueError(
                f"copy of {src} did not round-trip: {len(src_rows)} record(s) "
                f"in, {len(back)} out — destination left untouched")
        os.replace(staging, dst)
    except Exception:
        staging.unlink(missing_ok=True)
        raise
    return len(src_rows)


def ensure_ledger_migrated(dest_dir: Path | None = None,
                           legacy_dir: Path | None = None) -> dict:
    """One-time move of the pre-NIGHT-14 in-image ledger onto the volume (F7).

    THE RULE THAT MAKES THIS SAFE: a destination that already holds records is
    NEVER written to. Once the volume has a ledger, the volume is the truth —
    the image copy is a git snapshot that ages with every commit, and letting a
    stale snapshot overwrite records accrued in production would delete exactly
    the forward calibration this whole subsystem exists to accumulate. So the
    only state this function can change is "the volume has no ledger yet".

    Failure modes, all loud: a source that will not parse aborts before any
    write; a copy whose record ids do not round-trip is discarded and the
    destination left alone; both log at ERROR and are reported in the returned
    dict. Returns a report; callers must not branch on it beyond logging.
    """
    global _MIGRATION_ATTEMPTED
    dest_dir = Path(dest_dir or _config.OPTIMUS_LEDGER_DIR)
    legacy_dir = Path(legacy_dir or _config.OPTIMUS_LEDGER_LEGACY_DIR)
    report: dict = {"dest_dir": str(dest_dir), "legacy_dir": str(legacy_dir),
                    "files": {}}

    # Local dev (AEGIS_DATA_DIR unset): the two paths are the same directory and
    # there is nothing to move. Stated explicitly rather than falling through a
    # copy-onto-itself, which would truncate the file.
    if dest_dir.resolve() == legacy_dir.resolve():
        _MIGRATION_ATTEMPTED = True
        report["status"] = "same_path"
        report["reason"] = ("ledger dir and legacy dir are the same directory "
                            "(no AEGIS_DATA_DIR volume) — nothing to migrate")
        return report

    statuses = []
    for name in LEDGER_FILES:
        src, dst = legacy_dir / name, dest_dir / name
        entry: dict = {"src": str(src), "dst": str(dst)}
        try:
            src_rows = _read_jsonl(src) if src.exists() else []
            dst_rows = _read_jsonl(dst) if dst.exists() else []
            entry["legacy_records"] = len(src_rows)
            entry["dest_records"] = len(dst_rows)
            if dst_rows:
                # The steady state after the first migrated boot. Reported, not
                # acted on. If the image copy carries records the volume lacks,
                # say so — that is a real divergence and it should not be silent.
                # Compared by content hash so this means something for
                # beliefs.jsonl too, which has no prediction_id.
                legacy_only = ({_hash(r) for r in src_rows}
                               - {_hash(r) for r in dst_rows})
                entry["legacy_only_records"] = len(legacy_only)
                entry["status"] = "destination_not_empty"
                if legacy_only:
                    logger.warning(
                        "ledger migration: %s holds %d record(s) absent from "
                        "the persisted ledger at %s — NOT copied (the persisted "
                        "ledger is authoritative once non-empty)",
                        src, len(legacy_only), dst)
            elif not src_rows:
                entry["status"] = "nothing_to_migrate"
            else:
                n = _verified_copy(src, dst)
                entry["status"] = "migrated"
                entry["migrated_records"] = n
                logger.warning(
                    "LEDGER MIGRATION: copied %d record(s) from the in-image "
                    "ledger %s to the persistent ledger %s — this history was "
                    "previously destroyed on every redeploy (NIGHT-14 F7)",
                    n, src, dst)
        except Exception as e:
            entry["status"] = "failed"
            entry["error"] = str(e)
            logger.error("ledger migration FAILED for %s → %s: %s", src, dst, e,
                         exc_info=True)
        statuses.append(entry["status"])
        report["files"][name] = entry

    _MIGRATION_ATTEMPTED = True
    if "failed" in statuses:
        report["status"] = "failed"
    elif "migrated" in statuses:
        report["status"] = "migrated"
    else:
        report["status"] = "not_needed"
    return report


def _migrate_once() -> None:
    """Run the migration at most once per process, and never raise into a caller.

    Called from the write path (`append`) as a backstop for the startup call in
    main.py: if startup migration failed, the first night's write retries it
    rather than appending to a fresh empty file beside an unmigrated history.
    """
    global _MIGRATION_ATTEMPTED
    if _MIGRATION_ATTEMPTED:
        return
    try:
        ensure_ledger_migrated()
    except Exception as e:  # pragma: no cover - ensure_ledger_migrated catches
        _MIGRATION_ATTEMPTED = True
        logger.error("ledger migration raised unexpectedly: %s", e, exc_info=True)


#: Serialises the read-dedupe-append sequence WITHIN this process.
_APPEND_LOCK = threading.Lock()


def append(records: list[PredictionRecord], path: Path | None = None, *,
           population: "str | None" = None) -> None:
    """Append to the ledger. Returns None: nothing may branch on a write.

    EVERY RECORD IS STAMPED WITH ITS EVIDENCE POPULATION
    ----------------------------------------------------
    `population` defaults to the one that owns the file being written, which
    keeps every existing caller correct without a change. Passing it explicitly
    makes the write REFUSE if the target file belongs to the other population —
    the campaign resolver must never write the live volume and the production
    resolver must never write the repo ledger, and on Railway those are
    different files. See `services/evidence_population.py`.

    LOCKED because this is a read-modify-write, not a write. The dedupe reads
    the whole ledger and then appends; two threads interleaving between those
    two steps would each see the other's record as absent and write it twice,
    and a duplicate record is scored twice — which is worse than a missing one,
    because it silently doubles a forecaster's weight in its own calibration.
    LLM-SWARM-1 tore two rows out of `llm_telemetry` doing exactly this class of
    thing from 24 threads; this path happened to be called from one thread, and
    "happened to" is not a guarantee anyone should rely on.

    Same boundary as the telemetry lock: it serialises THIS process, not two
    processes or two Railway replicas sharing a volume.
    """
    if path is None:
        _migrate_once()
    path = path or PREDICTIONS
    path.parent.mkdir(parents=True, exist_ok=True)

    from backend.services import evidence_population as _pop
    try:
        pop = (_pop.parse(population) if population is not None
               else _pop.owner_of(path))
        if population is not None:
            _pop.assert_write_allowed(pop, path)
        _pop.stamp(records, pop)
    except _pop.PopulationRequired:
        # A test writing to a tmp_path is not one of the declared ledgers. That
        # is legitimate and must not stamp a population onto records — an
        # unattributable record is better than a mislabelled one.
        if population is not None:
            raise

    with _APPEND_LOCK:
        seen = {r["prediction_id"] for r in read_predictions(path)}
        with path.open("a", encoding="utf-8") as fh:
            for r in records:
                if r.prediction_id in seen:
                    logger.warning("%s already in the ledger — a duplicate "
                                   "record would be scored twice",
                                   r.prediction_id)
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
                today: date | None = None,
                skip_hashes: "frozenset | set | None" = None) -> dict:
    """Grade every record whose window has closed. Rewrites the ledger in place.

    `today` is injectable (threaded into resolve_one and the overdue check);
    default is the real date.today().

    `skip_hashes` names records this call must NOT grade, by the content hash in
    `evidence_population.record_hash`. They are written back verbatim and
    counted in `skipped`. This exists because resolution rewrites the whole
    file: without it, earning the right to grade ONE record in a ledger is
    earning the right to grade every record in it, which is how the quarantined
    campaign copies on the live volume nearly got graded as the product's own
    forward record (see `evidence_population.quarantined_hashes`).
    """
    path = path or PREDICTIONS
    today = today or date.today()
    rows = read_predictions(path)
    skip_hashes = frozenset(skip_hashes or ())
    if skip_hashes:
        from backend.services.evidence_population import record_hash
    graded, newly, skipped = [], 0, 0
    for r in rows:
        if skip_hashes and record_hash(r) in skip_hashes:
            # Passed through UNTOUCHED and counted. Not "no outcome available" —
            # deliberately ungradeable, and the count is what makes that visible
            # instead of looking like a price-panel gap.
            skipped += 1
            graded.append(r)
            continue
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
        # Separate the two reasons a record is sitting overdue, because the
        # remedies are opposite: a price gap is a bug to fix, a quarantined
        # copy is *supposed* to sit there until Murat disposes of it. Reporting
        # one number for both is how "25 overdue" read as a broken resolver.
        if skipped:
            logger.warning("%d record(s) past due and unresolved, of which %d "
                           "are deliberately quarantined and ungradeable; "
                           "check the price frame covers the remaining %d",
                           len(overdue), skipped, max(0, len(overdue) - skipped))
        else:
            logger.warning("%d record(s) are past their resolution date and still "
                           "unresolved — check the price frame covers them", len(overdue))
    return {"total": len(graded), "resolved": len(done), "void": len(void),
            "newly_resolved": newly, "skipped_quarantined": skipped,
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


def ledger_persistence(path: Path | None = None, *,
                       data_dir: Path | None = None) -> dict:
    """Does the ledger sit on the volume, or on a filesystem the next deploy eats?

    The F7 defect could run for months while every other number on the health
    surface stayed green: records were written, the append log said so, and the
    file simply ceased to exist at the next deploy. Nothing measured WHERE it
    was written. This does, and it is the only check that can see that class of
    failure before the resolutions it destroys come due.

    DEGRADED requires evidence: AEGIS_DATA_DIR is set (a persistent volume is
    configured, i.e. this is a deployment) AND the ledger resolves outside it.
    With no volume configured the path is the local repo one, which is correct
    for dev and indistinguishable from a prod box that forgot the variable —
    that contract is pinned separately by test_deploy_gate.py, and inventing a
    verdict here would be guessing.
    """
    p = Path(path or PREDICTIONS)
    d = Path(data_dir if data_dir is not None else _config.DATA_DIR)
    volume = os.environ.get("AEGIS_DATA_DIR")
    try:
        under = p.resolve().is_relative_to(d.resolve())
    except (ValueError, OSError) as e:
        # Different drives on Windows, or an unresolvable path. Treated as NOT
        # under the volume (the cautious direction: it degrades rather than
        # reassures) and logged, because a ledger path that will not resolve is
        # itself worth knowing about.
        logger.warning("ledger persistence: could not relate %s to %s: %s",
                       p, d, e)
        under = False
    row: dict = {
        "ledger_path": str(p),
        "data_dir": str(d),
        "volume_configured": bool(volume),
        "under_data_dir": under,
    }
    if volume and not under:
        row["status"] = "DEGRADED"
        row["reason"] = (
            f"AEGIS_DATA_DIR={volume} is set, so a persistent volume is mounted, "
            f"but the ledger resolves to {p}, which is NOT under {d} — every "
            f"record written there is destroyed by the next deploy and the "
            f"forward calibration clock silently restarts at zero")
    else:
        row["status"] = "ok"
        if not volume:
            row["note"] = (
                "AEGIS_DATA_DIR is unset, so DATA_DIR is the in-repo "
                "backend/data — the expected LOCAL configuration. This check "
                "cannot distinguish a dev box from a deployment that forgot the "
                "variable; the volume-mount contract itself is pinned by "
                "test_deploy_gate.py")
    return row


def ledger_health(path: Path | None = None, *, max_quiet_days: int = 7,
                  today: date | None = None,
                  quarantined_hashes: "frozenset | set | None" = None) -> dict:
    """Would anything say so if the specialists stopped writing?

    A prediction ledger is exactly the kind of subsystem that goes dark quietly:
    it fails by not growing, and an empty append looks identical to a night with
    nothing to say. This is the status row for it.

    `today` is injectable so the quiet/overdue clocks can be evaluated as-of a
    date; default is the real date.today().

    `quarantined_hashes` splits the overdue count into the part someone must ACT
    on and the part that is overdue ON PURPOSE. Added 2026-08-17 because this row
    reported a bare "25 forecast(s) past due and unresolved" for records the
    resolver was deliberately refusing to grade, and TWO independent reviewers
    read it as a dead scheduler and proposed rebuilding a scheduler that was
    working. A guard that refuses and a job that never ran produce the same
    silence, so the row has to say which one it is.
    """
    today = today or date.today()
    # Where the ledger lives is part of its health: a ledger on an ephemeral
    # filesystem reads perfectly right up until the deploy that empties it.
    persistence = ledger_persistence(path)
    rows = read_predictions(path)
    if not rows:
        return {"status": "DEGRADED", "n": 0,
                "reason": "the ledger is empty — no forecast has ever been "
                          "written, so no calibration can ever accrue",
                "persistence": persistence}
    last = max(r["made_at"][:10] for r in rows)
    quiet = (today - date.fromisoformat(last)).days
    overdue = [r for r in rows
               if r.get("outcome") is None and not r.get("void_reason")
               and today >= date.fromisoformat(r["resolves_after"][:10])]
    quarantined_hashes = frozenset(quarantined_hashes or ())
    if quarantined_hashes:
        from backend.services.evidence_population import record_hash
        q_overdue = [r for r in overdue
                     if record_hash(r) in quarantined_hashes]
        actionable = [r for r in overdue
                      if record_hash(r) not in quarantined_hashes]
    else:
        q_overdue, actionable = [], overdue
    # DEGRADED = ACTIONABLE overdue OR excessive quiet OR persistence failure.
    #
    # Adjudicated 2026-08-17 in review. The first version of the split put the
    # quarantine message into `problems` — which was better than a bare overdue
    # count, but `problems` is what computes DEGRADED, so 25 deliberately
    # ungradeable rows kept the canary red forever. A permanently red canary is
    # not a warning, it is alarm fatigue with extra steps: the next genuine
    # actionable overdue record would arrive on a page that already said DEGRADED
    # for months and nobody would look.
    #
    # The refinement that keeps it honest: quiet and persistence STILL degrade.
    # The narrow bug was the quarantine, not the concept — "make health depend
    # only on actionable overdue" would paint a dead or unpersisted ledger green,
    # which is the failure this row exists to catch.
    problems = []
    if quiet > max_quiet_days:
        problems.append(f"no new forecast in {quiet} days")
    if actionable:
        problems.append(f"{len(actionable)} forecast(s) past due and unresolved")
    if persistence["status"] != "ok":
        problems.append(f"ledger persistence: {persistence['reason']}")

    # Deliberate and NOT a fault, so it lives OUTSIDE `problems` — prominently
    # counted, never degrading. Phrased so it cannot be mistaken for a resolver
    # that stopped: it names the reason and where the decision sits.
    notices = []
    if q_overdue:
        notices.append(
            f"{len(q_overdue)} forecast(s) past due but QUARANTINED (campaign "
            f"copies on the live volume) — the resolver is refusing these on "
            f"purpose, not failing to reach them; disposition is attended")
    return {
        "status": "ok" if not problems else "DEGRADED",
        "problems": problems,
        # Never empty-by-omission: an absent key would read as "no quarantine"
        # to a caller that cannot tell missing from zero.
        "notices": notices,
        "persistence": persistence,
        "n_records": len(rows),
        "n_void": sum(1 for r in rows if r.get("void_reason")),
        "n_resolved": sum(1 for r in rows if r.get("outcome") is not None),
        "n_overdue": len(overdue),
        "n_overdue_actionable": len(actionable),
        "n_overdue_quarantined": len(q_overdue),
        "last_written": last,
        "days_quiet": quiet,
        "distinct_specialists": len({r["specialist"] for r in rows}),
        "distinct_models": len({f"{r['model']}:{r['model_version']}"
                                for r in rows}),
    }
