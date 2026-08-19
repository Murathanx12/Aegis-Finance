"""AEGIS-RESEARCH-DAEMON-1 — the queue that decides what to test, and in what order.

    from backend.services import research_daemon as RD
    d = RD.ResearchDaemon(reserved=RD.load_reserved_windows())
    sub = d.submit(job)          # refuses here, not at analysis
    d.record_result(job_id, p_value=0.013, effect=0.021)
    d.decide()                   # ONE entry point, BH-FDR, m = tests we ran
    print(d.nightly_receipt())

WHAT THIS IS FOR (Order 17 P0-R1)
=================================
Mission rule 5 — *maximise information per dollar, not minimise API calls;
score experiments as `P(changes the roadmap) x value of decision improved -
cost`* — has been a sentence in CLAUDE.md and nothing that ran. This is that
sentence as a scheduler.

**HYPOTHESIS-BANDIT-1 IS HERE FROM DAY ONE, AND THAT IS THE DESIGN DECISION.**
Retrofitting a score onto a FIFO queue later is a rewrite, and worse, it is a
rewrite performed by someone who has already seen which jobs produced results.
Priority is computed AT SUBMISSION and **frozen** — `record_result` cannot
change it, and the daemon refuses to re-prioritise a job that already has one.
A ranking that can move after the outcome is known is not a prioritisation, it
is a story about why the winners were always the priority.

THE FOUR HARD CONSTRAINTS, WIRED IN RATHER THAN POLICED
========================================================

1.  **Reserved confirmation windows are unreachable BY CONSTRUCTION.** A job
    whose data range touches a reserved window is refused at `submit()`, not
    discovered at analysis. By analysis time the window has already been read
    — the refusal has to happen before the data is touched or it is a
    post-mortem. This is the single most important line in the file.

2.  **One `decide()` entry point** (§63). The daemon never picks between BH and
    Holm; it hands the window to `MultiplicityBudget.decide`, which applies
    whichever criterion that window's declared PURPOSE demands. Choosing the
    criterion at the call site is choosing it after seeing the p-values.

3.  **m is the daemon's OWN running test count.** Not the count of interesting
    results, not the count somebody remembers declaring. The machine that runs
    the tests counts them, because §63's `m = tests RUN` is only true if
    something is actually counting.

4.  **A corpse is confronted BY NAME, in a sentence.** `parent_corpse_ids`
    plus a `distinct_claim` that is not empty. Order 16 and 17 both put it the
    same way: *a distinct claim is a sentence, not a feeling.*

UNDERPOWERED IS NOT FALSE
=========================
The §64 power screen runs before a job is queued, and a job below its own MDE
goes to **SHELF**, not to REJECTED, carrying the states in which it appeared.
§19's asymmetry trap is that an underpowered null feels like a kill; a graveyard
that absorbs everything the calendar could not resolve is how a programme talks
itself out of its own good ideas. SHELF is that rule's data structure.

THE UNIT IS THE DATE BLOCK
==========================
`n_date_blocks`, never a row count. Pairs, panels and cross-sections all explode
rows without adding information — a million pairs on 500 dates is 500 (§58).
The field is named so that supplying a row count requires lying about what it is.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from backend import config as _config
from backend.services.iif1_grader import Z_STD_NORMAL

logger = logging.getLogger(__name__)

DAEMON = "AEGIS-RESEARCH-DAEMON-1"

#: Where the queue, the results and the nightly receipts live.
DAEMON_DIR = _config.OPTIMUS_LEDGER_DIR / "research_daemon"

# ── the four states, and SHELF is the one that matters ─────────────────────
REJECTED = "REJECTED"
SHELF = "SHELF"
PROMISING = "PROMISING"
NEED_MORE_DATA = "NEED_MORE_DATA"
STATES = (REJECTED, SHELF, PROMISING, NEED_MORE_DATA)


class JobRefused(RuntimeError):
    """A job was submitted that the daemon cannot honestly queue.

    Every case is a missing or unusable INPUT, refused before any data is read:

      * its date range touches a reserved confirmation window;
      * it names a corpse without stating, in a sentence, what it claims that
        the corpse's tests did not ask;
      * it declares a row count where a count of date blocks is required;
      * it cannot be power-screened because its own effect size, standard
        error or block count is missing — and a job that cannot be
        power-screened cannot be prioritised, because expected value is
        meaningless without P(resolves).
    """


@dataclass(frozen=True)
class ReservedWindow:
    """A confirmation window that is off-limits to exploration.

    Reserved windows are the campaign's only unspent evidence. Nothing the
    daemon queues may touch one — and "may not touch" is enforced by refusing
    the submission, because by the time an analysis notices, the data has been
    read and the window is gone whatever the analyst then does.
    """

    name: str
    universe: str
    outcome: str
    start: str
    end: str

    def touches(self, *, universe: str, outcome: str, start: str,
                end: str) -> bool:
        # Universe and outcome must both match for the window to bind: a
        # drawdown question and a terminal-return question on the same dates
        # are different windows with different power, and spending one does not
        # spend the other (§59). Same rule `multiplicity.window_id` uses.
        if self.universe != universe or self.outcome != outcome:
            return False
        return not (end < self.start or start > self.end)


def load_reserved_windows(path: Path | str | None = None) -> list[ReservedWindow]:
    """HAND-DECLARED supplement windows from disk. Absent is a legitimate state.

    This file is for reservations that exist nowhere machine-readable yet —
    a supplement, not the source of record. The source of record is the
    confirmation-budget ledger, and `derive_reserved_windows` reads it. An
    absent supplement is fine; an absent LEDGER is not (see the derivation).
    An unreadable file still REFUSES: unreadable and absent are different
    states and only one of them is a legitimate way to have declared nothing.
    """
    p = Path(path or (DAEMON_DIR / "reserved_windows.json"))
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise JobRefused(
            f"reserved windows at {p} are unreadable ({e}). Treating that as "
            f"'nothing is reserved' would make every window submittable, "
            f"which is the most permissive answer available and the one a "
            f"missing input must never produce.") from e
    return [ReservedWindow(**r) for r in raw]


def derive_reserved_windows(
        ledger_path: Path | str | None = None) -> list[ReservedWindow]:
    """DERIVE reserved windows from the confirmation-budget ledger.

    The programme's actual reservations live in
    `research_gym/confirmation_budget.jsonl` (every declared EXPORT budget is
    a confirmation window whose evidence is unspent). Until 2026-08-18 this
    module read only its own hand-authored JSON file, which no producer
    writes — so the guard at the "most important line in this module" passed
    every job unconditionally, in the live tree, for as long as the daemon
    existed. A guard must derive what it checks from data it can see, or
    refuse; this is the derivation.

    An ABSENT ledger refuses. Unlike the supplement file, the ledger cannot
    be legitimately absent in any environment where submitting research jobs
    makes sense — its absence means "wrong machine or wrong path", and the
    permissive reading of that state is exactly the failure this function
    exists to close. Callers who genuinely have no reservations declare it:
    `ResearchDaemon(reserved=[])`, in writing, at the call site.

    Windows stay reserved after their campaign decides — conservative on
    purpose. Post-decision reanalysis is a REANALYSIS purpose in the slice
    register, not an unmarked exploration through the daemon.
    """
    if ledger_path is None:
        from backend.services.research_gym import multiplicity as _mp
        ledger_path = _mp.LEDGER_PATH
    p = Path(ledger_path)
    if not p.exists():
        raise JobRefused(
            f"confirmation-budget ledger absent at {p}. Deriving 'nothing is "
            f"reserved' from a missing ledger is the most permissive answer "
            f"available and the one a missing input must never produce. If "
            f"nothing is genuinely reserved, say so at the call site: "
            f"ResearchDaemon(reserved=[]).")
    out: list[ReservedWindow] = []
    seen: set[str] = set()
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError as e:
            raise JobRefused(
                f"confirmation-budget ledger line {i} is unreadable ({e}); a "
                f"reservation that cannot be parsed cannot be skipped, because "
                f"skipping is the permissive direction.") from e
        if rec.get("kind") != "budget" or rec.get("purpose") != "EXPORT":
            continue
        wid = rec.get("window_id", "")
        if wid in seen:
            continue
        parts = wid.split("|")
        period = parts[1].split("..") if len(parts) == 3 else []
        if len(parts) != 3 or len(period) != 2:
            raise JobRefused(
                f"EXPORT budget window_id {wid!r} (ledger line {i}) does not "
                f"parse as universe|start..end|outcome. A malformed "
                f"reservation dropped silently is a reservation that does not "
                f"bind.")
        seen.add(wid)
        out.append(ReservedWindow(
            name=f"EXPORT:{rec.get('declared_by', '?')}:{wid}",
            universe=parts[0], outcome=parts[2],
            start=period[0], end=period[1]))
    return out


def default_reserved_windows() -> list[ReservedWindow]:
    """What `ResearchDaemon()` reserves when the caller does not say:
    everything the budget ledger declares, plus the hand-declared supplement.
    """
    return derive_reserved_windows() + load_reserved_windows()


@dataclass
class HypothesisJob:
    """One question, with everything needed to price it before it runs."""

    hypothesis_id: str
    question: str
    universe: str
    outcome: str
    start: str
    end: str

    #: DATE BLOCKS, never rows. Named so that supplying a row count requires
    #: lying about what it is (§58).
    n_date_blocks: int
    #: Standard error of the effect PER DATE BLOCK, in `effect_units`.
    se_per_block: float
    #: The effect the hypothesis predicts, in `effect_units`. Declared before
    #: the run — this is what the power screen tests for detectability.
    expected_effect: float
    effect_units: str

    #: What it costs to find out.
    cost_usd: float = 0.0
    cost_minutes: float = 0.0

    #: P(this job produces a resolvable answer at all) — data availability,
    #: coverage, tradability. Distinct from P(the hypothesis is true).
    p_resolves: float = 1.0
    #: How much a resolution would change what we do next, in [0, 1].
    decision_value: float = 0.5

    #: Corpses this job must confront BY NAME, and the sentence that says what
    #: it asks that they did not.
    parent_corpse_ids: tuple[str, ...] = ()
    distinct_claim: str = ""

    #: Provenance, per Order 17.
    code_sha: str = ""
    data_hash: str = ""
    pit_cutoff: str = ""
    seeds: tuple[int, ...] = ()

    horizon_days: int = 0
    alpha: float = 0.05
    power: float = 0.80


@dataclass
class Submission:
    """A queued job. `priority` and `mde` are FROZEN at submission."""

    job: HypothesisJob
    priority: float
    priority_terms: dict
    mde: float
    powered: bool
    submitted_at: str
    state: str = NEED_MORE_DATA
    p_value: float | None = None
    observed_effect: float | None = None
    output_hash: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def has_result(self) -> bool:
        return self.p_value is not None


# ── the power screen (§64), before anything is queued ──────────────────────
def power_screen(job: HypothesisJob) -> dict:
    """The MDE this job could detect, from its OWN blocks and standard error.

    §64 run forwards: a power check that consumes no outcome is free and
    therefore obligatory. Below its MDE a job returns "not established"
    whatever the world does, and the window is gone with nothing learned — so
    the check happens before the queue, not after the run.
    """
    if job.n_date_blocks is None or job.n_date_blocks < 2:
        raise JobRefused(
            f"{job.hypothesis_id}: n_date_blocks={job.n_date_blocks!r}. A "
            f"power screen needs at least two DATE BLOCKS — and if a row count "
            f"was supplied here, note that pairs and panels explode rows "
            f"without adding information (a million pairs on 500 dates is 500).")
    if not (job.se_per_block and math.isfinite(job.se_per_block)
            and job.se_per_block > 0):
        raise JobRefused(
            f"{job.hypothesis_id}: se_per_block={job.se_per_block!r}. Without "
            f"it there is no MDE, and without an MDE a null result is a "
            f"statement about the instrument rather than the world (§19).")
    if not math.isfinite(job.expected_effect):
        raise JobRefused(
            f"{job.hypothesis_id}: expected_effect is not finite. A job that "
            f"does not say how big the effect should be cannot be told apart "
            f"from one that found nothing.")
    z_a = Z_STD_NORMAL[round(1.0 - job.alpha / 2.0, 3)]
    z_b = Z_STD_NORMAL[round(job.power, 2)]
    mde = (z_a + z_b) * job.se_per_block / math.sqrt(job.n_date_blocks)
    return {"mde": mde, "powered": abs(job.expected_effect) >= mde,
            "n_date_blocks": job.n_date_blocks, "alpha": job.alpha,
            "power": job.power,
            "basis": "FORWARD_FROM_DECLARED_SE_AND_DATE_BLOCKS"}


# ── HYPOTHESIS-BANDIT-1: the score, fixed before the result ────────────────
def bandit_priority(job: HypothesisJob, screen: dict) -> dict:
    """`expected value x P(resolves) x information gain / cost`.

    Mission rule 5, made arithmetic. Every term is declared BEFORE the run and
    every one of them is on the job, so the score is reproducible from the
    submission alone — which is what makes "priority was fixed beforehand" a
    checkable claim instead of an assurance.

    INFORMATION GAIN IS WHERE POWER ENTERS. An underpowered job cannot change
    the roadmap however interesting it is, so its information gain is damped
    rather than its priority being zeroed: it still ranks, below everything
    that can actually resolve, which is what keeps SHELF from behaving like a
    graveyard with extra steps.

    Cost has a floor so a free job does not divide by zero and rank infinitely
    — "it costs nothing" is a reason to run something, not a reason to run it
    before everything else forever.
    """
    if not 0.0 <= job.p_resolves <= 1.0:
        raise JobRefused(f"{job.hypothesis_id}: p_resolves must be in [0,1]")
    if not 0.0 <= job.decision_value <= 1.0:
        raise JobRefused(f"{job.hypothesis_id}: decision_value must be in [0,1]")

    # Effect size relative to what is detectable: a job whose predicted effect
    # is twice its MDE is far more informative than one that is barely at it.
    ratio = (abs(job.expected_effect) / screen["mde"]) if screen["mde"] else 0.0
    info_gain = min(1.0, ratio / 2.0) if screen["powered"] else 0.05 * min(
        1.0, ratio)
    cost = max(0.25, job.cost_usd + job.cost_minutes / 60.0)
    priority = job.decision_value * job.p_resolves * info_gain / cost
    return {
        "priority": priority,
        "terms": {"decision_value": job.decision_value,
                  "p_resolves": job.p_resolves,
                  "info_gain": round(info_gain, 6),
                  "effect_over_mde": round(ratio, 4),
                  "cost_units": round(cost, 4),
                  "powered": screen["powered"]},
        "formula": "decision_value x p_resolves x info_gain / cost",
        "fixed_at": "SUBMISSION — never recomputed after a result exists",
    }


# ── corpse confrontation ───────────────────────────────────────────────────
def assert_distinct_from_corpses(job: HypothesisJob) -> None:
    """A corpse is named, and the distinct claim is a SENTENCE.

    Order 16 and 17 both put it this way. The check is deliberately crude —
    it cannot judge whether the sentence is *true* — but it can refuse the
    case that actually happens, which is a job inheriting a dead mechanism's
    reasoning with the corpse silently unmentioned, or mentioned with nothing
    said about what is different.
    """
    if not job.parent_corpse_ids:
        return
    claim = (job.distinct_claim or "").strip()
    if len(claim.split()) < 5:
        raise JobRefused(
            f"{job.hypothesis_id} names corpse(s) {list(job.parent_corpse_ids)} "
            f"but its distinct_claim is {claim!r}. A distinct claim is a "
            f"sentence, not a feeling: state what this asks that those tests "
            f"did not, or the thing is not built.")


def assert_not_reserved(job: HypothesisJob,
                        reserved: Sequence[ReservedWindow]) -> None:
    """REFUSED AT SUBMISSION. The most important line in this module.

    By analysis time the window has been read and is gone whatever anyone then
    decides. So the only place this check does any work is before the data is
    touched.
    """
    for w in reserved:
        if w.touches(universe=job.universe, outcome=job.outcome,
                     start=job.start, end=job.end):
            raise JobRefused(
                f"{job.hypothesis_id} spans {job.start}..{job.end} on "
                f"{job.universe}/{job.outcome}, which touches the RESERVED "
                f"confirmation window {w.name!r} ({w.start}..{w.end}). "
                f"Refused at submission: a reserved window discovered at "
                f"analysis time has already been read, and the refusal would "
                f"be a post-mortem rather than a guard.")


# ── the daemon ─────────────────────────────────────────────────────────────
class ResearchDaemon:
    """The queue. Prioritises before results and counts its own multiplicity."""

    def __init__(self, *, reserved: Sequence[ReservedWindow] | None = None,
                 window_id: str | None = None, budget=None) -> None:
        # `None` means "look at the world": derive from the budget ledger.
        # An explicit `[]` is a written declaration that nothing is reserved,
        # made at the call site where a reviewer can see it. The two are
        # different statements and conflating them (`reserved or []`) was how
        # the guard ran permissive in the live tree for its whole life.
        if reserved is None:
            reserved = default_reserved_windows()
        self.reserved = list(reserved)
        self._subs: dict[str, Submission] = {}
        self._window_id = window_id
        self._budget = budget

    # -- submission ---------------------------------------------------------
    def submit(self, job: HypothesisJob) -> Submission:
        if job.hypothesis_id in self._subs:
            raise JobRefused(
                f"{job.hypothesis_id} is already submitted. Re-submitting is "
                f"how one hypothesis becomes two entries in m.")
        assert_not_reserved(job, self.reserved)     # FIRST. Before anything.
        assert_distinct_from_corpses(job)
        screen = power_screen(job)
        pri = bandit_priority(job, screen)

        sub = Submission(
            job=job, priority=pri["priority"], priority_terms=pri,
            mde=screen["mde"], powered=screen["powered"],
            submitted_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            state=NEED_MORE_DATA if screen["powered"] else SHELF)
        if not screen["powered"]:
            sub.notes.append(
                f"SHELVED AT BIRTH: predicted effect {job.expected_effect:g} is "
                f"below its own MDE {screen['mde']:.6g} at "
                f"{job.n_date_blocks} date blocks. Underpowered is NOT false — "
                f"this keeps its states and returns when more blocks exist.")
        self._subs[job.hypothesis_id] = sub
        return sub

    # -- results ------------------------------------------------------------
    def record_result(self, hypothesis_id: str, *, p_value: float,
                      observed_effect: float | None = None,
                      output_hash: str = "") -> Submission:
        """Attach an outcome. It CANNOT touch the priority.

        The frozen priority is the whole point of the bandit: a ranking that
        can move after the outcome is known is not a prioritisation, it is a
        story about why the winners were always the priority.
        """
        sub = self._subs.get(hypothesis_id)
        if sub is None:
            raise JobRefused(f"no submitted job {hypothesis_id!r}")
        if sub.has_result:
            raise JobRefused(
                f"{hypothesis_id} already has a result. A second result for one "
                f"submission is either a re-run being reported as new evidence "
                f"or an m that has quietly stopped counting.")
        sub.p_value = float(p_value)
        sub.observed_effect = observed_effect
        sub.output_hash = output_hash
        return sub

    def reprioritise(self, hypothesis_id: str) -> None:
        """Deliberately not implemented. Kept as a named refusal."""
        raise JobRefused(
            f"{hypothesis_id}: priority is fixed at submission and there is no "
            f"path to change it. Retrofitting a score after results exist is a "
            f"rewrite performed by somebody who has already seen which jobs "
            f"paid off.")

    # -- the queue ----------------------------------------------------------
    def queue(self) -> list[Submission]:
        """Unrun jobs, highest priority first. Shelved jobs rank last."""
        pending = [s for s in self._subs.values() if not s.has_result]
        return sorted(pending, key=lambda s: (-s.priority, s.job.hypothesis_id))

    def tests_run(self) -> int:
        """m. Counted by the machine that ran them (§63)."""
        return sum(1 for s in self._subs.values() if s.has_result)

    # -- the single decide() entry point ------------------------------------
    def decide(self):
        """Route through `MultiplicityBudget.decide` — never a criterion here.

        The daemon does not choose between BH and Holm. It hands the window to
        the one entry point, which applies whichever criterion that window's
        declared PURPOSE demands. Picking here would be picking the error
        criterion after seeing the p-values, which is the thing §63 exists for.
        """
        if self._budget is None or self._window_id is None:
            raise JobRefused(
                "no multiplicity window declared, so there is nothing to "
                "control and no criterion to apply. A daemon that decided "
                "without a window would be spending an error rate nobody "
                "reserved.")
        return self._budget.decide(self._window_id)

    # -- the nightly receipt ------------------------------------------------
    def nightly_receipt(self, *, now: datetime | None = None) -> dict:
        """The dashboard. `m` here is the daemon's own count, by construction."""
        now = now or datetime.now(timezone.utc)
        by_state: dict[str, int] = {s: 0 for s in STATES}
        for sub in self._subs.values():
            by_state[sub.state] = by_state.get(sub.state, 0) + 1
        pending = self.queue()
        return {
            "daemon": DAEMON,
            "generated_at": now.isoformat(timespec="seconds"),
            "submitted": len(self._subs),
            "tests_run": self.tests_run(),
            "multiplicity_m": self.tests_run(),
            "m_basis": "COUNTED_BY_THE_DAEMON_THAT_RAN_THEM",
            "by_state": by_state,
            "shelved_underpowered": sum(
                1 for s in self._subs.values() if s.state == SHELF),
            "queue_depth": len(pending),
            "next_up": [{"hypothesis_id": s.job.hypothesis_id,
                         "priority": round(s.priority, 6),
                         "powered": s.powered,
                         "question": s.job.question[:80]}
                        for s in pending[:10]],
            "reserved_windows": [w.name for w in self.reserved],
            "note": ("SHELF is not a graveyard: an underpowered job keeps the "
                     "states in which it appeared and returns when more date "
                     "blocks exist. Underpowered is not false (§19/§64)."),
        }

    def write_receipt(self, *, out_dir: Path | None = None,
                      now: datetime | None = None) -> Path:
        d = Path(out_dir or DAEMON_DIR)
        d.mkdir(parents=True, exist_ok=True)
        rec = self.nightly_receipt(now=now)
        stamp = (now or datetime.now(timezone.utc)).date().isoformat()
        p = d / f"receipt_{stamp}.json"
        n = 1
        while p.exists():
            p = d / f"receipt_{stamp}.{n}.json"
            n += 1
        p.write_text(json.dumps(rec, indent=2, default=str), encoding="utf-8")
        return p

    # -- introspection ------------------------------------------------------
    def submissions(self) -> list[Submission]:
        return list(self._subs.values())

    def get(self, hypothesis_id: str) -> Submission | None:
        return self._subs.get(hypothesis_id)
