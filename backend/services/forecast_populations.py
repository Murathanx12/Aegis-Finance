"""Every population of forward forecasts, named, with its own health row.

THE BUG THIS MODULE EXISTS TO PREVENT
=====================================
On 2026-08-23 `/api/health/full` reported the whole deploy DEGRADED for one
reason: "no new forecast in 11 days". That sentence was TRUE about the ledger it
was computed on -- and it was read, by a reviewer and very nearly by a session,
as "the continuously-learning engine has stopped forecasting".

It had not. The arena had written 25 LLM forecasts two days earlier, on the last
trading session before the check. The alarm and the arena were looking at two
different files:

    <LEDGER_DIR>/predictions.jsonl          <- what health measured
    <LEDGER_DIR>/arena/predictions.jsonl    <- where the arena actually writes

`evidence_population` already separates CAMPAIGN_FORWARD from LIVE_FORWARD, and
that separation is correct and load-bearing. But it enumerates two populations
and the system has three, so the third was invisible to every health surface --
not refused, not flagged, simply absent. A population nobody registered leaves
no trace in a registry that only lists the populations somebody registered. That
is the same structural bug as the WRDS pull reporting complete with seven tables
never attempted: **a check that reads the record of what happened cannot see
what never got asked for.** The fix in both cases is the same shape -- enumerate
the PLAN (every population that exists), not the record.

WHAT THIS MODULE GUARANTEES
===========================
* Every forecast population is listed, with producer, consumer and purpose.
* Health is computed PER POPULATION. There is no "the ledger" status, because
  there is no such thing.
* A consumer names the population(s) it is licensed to read. Reading "the
  forecasts" without naming one is refused.
* Populations are never pooled. Two ledgers with different producers and
  different resolvers do not add up to one estimate, and there is no
  prospectively declared pooling rule that would make them.

ADDING A POPULATION
===================
Append to `_POPULATIONS`. `test_forecast_populations.py` asserts that every
`*/predictions.jsonl` reachable under the ledger root is claimed by exactly one
registered population, so a new ledger that nobody registers FAILS THE SUITE
rather than going quietly unmonitored.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from backend import config as _config

logger = logging.getLogger(__name__)


class UnknownPopulation(KeyError):
    """A population id that is not in the registry."""


class PopulationNotNamed(ValueError):
    """A consumer asked for "the forecasts" without saying which population."""


class PopulationPoolingRefused(RuntimeError):
    """Two populations were about to be summed. There is no pooling rule."""


@dataclass(frozen=True)
class Population:
    """One body of forward forecasts and everything needed to judge it."""

    population_id: str
    purpose: str
    producer: str
    consumers: tuple[str, ...]
    #: Path relative to this population's BASE dir. Resolved late so tests and
    #: the local machine (where AEGIS_DATA_DIR is unset) see their own root.
    relative_path: str
    #: Days of silence before the population is considered to have gone dark.
    #: Not one number for all three: the arena writes only on trading days, the
    #: campaign is attended and bursty, and live accrual should be steady.
    #:
    #: `base` = which base directory the population lives under. NOT one base
    #: for all three: the campaign's history is a REPOSITORY artifact and must
    #: not follow a volume mount around, while the live and arena ledgers are
    #: the deployment's own and sit on the volume. On a dev machine the two
    #: bases coincide -- which is exactly why hard-coding one base looked
    #: correct here and would have reported the volume's file as the
    #: campaign's in production.
    max_quiet_days: int
    base: str = "ledger"          # "ledger" -> OPTIMUS_LEDGER_DIR
                                  # "legacy" -> OPTIMUS_LEDGER_LEGACY_DIR
    #: True when silence is a fault. A population that is DECLARED dormant
    #: (superseded, or awaiting an attended decision) is reported, not alarmed
    #: on -- but it must say so out loud rather than being dropped.
    quiet_is_a_fault: bool = True
    #: True when an OVERDUE-and-unresolved record is a fault. False for a
    #: population whose resolver is ATTENDED rather than scheduled: nobody
    #: running the resolver today is a TODO, not an outage, and reporting it as
    #: an outage buries the populations whose resolvers really are supposed to
    #: run on their own. The count is REPORTED either way -- this changes the
    #: alarm, never the number.
    overdue_is_a_fault: bool = True
    dormant_reason: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    def base_dir(self) -> Path:
        if self.base == "legacy":
            return _config.OPTIMUS_LEDGER_LEGACY_DIR
        return _config.OPTIMUS_LEDGER_DIR

    def path(self, root: Path | None = None) -> Path:
        # An explicit `root` collapses every base into one directory. That is
        # the dev-machine case by construction (no volume), and it is what
        # tests want; production passes no root and gets the real split.
        return (root or self.base_dir()) / self.relative_path


#: THE PLAN. Every population that exists, whether or not it is healthy, and
#: whether or not anything is currently reading it.
_POPULATIONS: tuple[Population, ...] = (
    Population(
        population_id="campaign_forward",
        purpose=("the research campaign's own forward records -- written by "
                 "the swarm, the nightly trials and historical arena runs. "
                 "What ABLATION_FWD certifies against."),
        producer="offline research runs (attended, local)",
        consumers=("scripts/resolve_campaign_ledger.py",
                   "ABLATION_FWD certification"),
        relative_path="predictions.jsonl",
        base="legacy",
        max_quiet_days=90,
        quiet_is_a_fault=False,
        overdue_is_a_fault=False,
        dormant_reason=("attended and bursty by design: it grows when a "
                        "campaign runs, not on a schedule. Silence here is "
                        "not evidence of a fault."),
        notes=("On Railway this file is the LIVE ledger's path too; the two "
               "are told apart by the `population` FIELD on each record, not "
               "by path alone. See evidence_population.py.",),
    ),
    Population(
        population_id="live_forward",
        purpose=("the deployed product's own forward accrual. Authoritative "
                 "for anything claimed about the live deployment, and the "
                 "only population G7 (calibrated forward forecasting) may "
                 "count."),
        producer="production nightly specialists",
        consumers=("pi_ledger_resolve", "G7 gate", "/api/health/full"),
        relative_path="predictions.jsonl",
        max_quiet_days=7,
        quiet_is_a_fault=True,
        notes=("Its true size is ZERO: the 112 records on the volume are "
               "content-identical to the first 112 rows of the campaign "
               "ledger -- a partial copy that predates the migration guard. "
               "See docs/LEDGER_DIVERGENCE_ADJUDICATION_2026-08-15.md.",),
    ),
    Population(
        population_id="arena_forward",
        purpose=("the live arena's daily LLM belief forecasts -- one record "
                 "per reviewed name per session, graded by the arena's own "
                 "resolver into reliability cells. This is the population the "
                 "continuously-learning loop actually writes to."),
        producer="pi_arena_daily (17:45 ET, trading days only)",
        consumers=("arena.experience.resolve_perceptions",
                   "arena.reliability", "RELIABILITY_ROUTER_v1"),
        relative_path="arena/predictions.jsonl",
        #: Trading days only, so a normal weekend is 3 days of silence and a
        #: long holiday weekend is 4. 5 alarms on a real outage without
        #: crying wolf every Sunday -- which is exactly what a flat 7-day
        #: clock did to the live_forward row it was borrowed from.
        max_quiet_days=5,
        quiet_is_a_fault=True,
        notes=("Was invisible to every health surface until 2026-08-23. The "
               "deploy read DEGRADED on live_forward's silence while THIS "
               "population was writing normally.",),
    ),
)

BY_ID = {p.population_id: p for p in _POPULATIONS}


def all_populations() -> tuple[Population, ...]:
    return _POPULATIONS


def get(population_id: str) -> Population:
    try:
        return BY_ID[population_id]
    except KeyError:
        raise UnknownPopulation(
            f"{population_id!r} is not a registered forecast population. "
            f"Known: {sorted(known_ids())}. Register it in "
            f"forecast_populations._POPULATIONS rather than reading an "
            f"unregistered ledger.") from None


def known_ids() -> list[str]:
    return sorted(BY_ID)


def health(population_id: str, *, root: Path | None = None,
           today: date | None = None) -> dict:
    """Health of ONE named population. Never "the ledger"."""
    pop = get(population_id)
    from backend.services.belief_state import ledger_health

    path = pop.path(root)
    row: dict = {
        "population_id": pop.population_id,
        "path": str(path),
        "producer": pop.producer,
        "consumers": list(pop.consumers),
        "purpose": pop.purpose,
        "max_quiet_days": pop.max_quiet_days,
        "quiet_is_a_fault": pop.quiet_is_a_fault,
        "overdue_is_a_fault": pop.overdue_is_a_fault,
        "notes": list(pop.notes),
    }
    if pop.dormant_reason:
        row["dormant_reason"] = pop.dormant_reason

    if not path.exists():
        # Absent is a real, reportable state and NOT the same as empty: an
        # empty file means a producer ran and had nothing to say; a missing
        # file means nothing has ever written here.
        row.update(status="ABSENT", exists=False, n_records=0,
                   last_written=None, days_quiet=None,
                   reason="no file at this path -- nothing has ever been "
                          "written to this population")
        return row

    quarantined = None
    if pop.population_id in ("live_forward", "campaign_forward"):
        try:
            from backend.services.evidence_population import quarantined_hashes
            quarantined = quarantined_hashes()
        except Exception as e:                                  # noqa: BLE001
            logger.warning("population %s: quarantine set unavailable (%s) -- "
                           "overdue counts reported UNSPLIT",
                           pop.population_id, e)

    try:
        h = ledger_health(path, max_quiet_days=pop.max_quiet_days,
                          today=today, quarantined_hashes=quarantined)
    except Exception as e:                                      # noqa: BLE001
        row.update(status="UNREADABLE", exists=True, error=str(e))
        return row

    row.update(h)
    row["exists"] = True
    row["quarantine_split_available"] = quarantined is not None

    # A DECLARED-dormant population is not a fault for the things it is
    # declared dormant ABOUT. It still reports every count -- it just does not
    # drag the deploy red for a resolver that was never scheduled to run.
    if row.get("status") == "DEGRADED":
        unexplained = [p for p in (row.get("problems") or [])
                       if not _excused(p, pop)]
        empty_only = (not row.get("problems")
                      and str(row.get("reason", "")).startswith(
                          "the ledger is empty"))
        if not unexplained and (row.get("problems") or empty_only):
            row["status"] = "DORMANT_BY_DESIGN"
            row["downgraded_from"] = "DEGRADED"
            row["downgrade_reason"] = (
                "every problem on this row is one this population is DECLARED "
                "dormant about; the counts are unchanged")
    return row


def _excused(problem: str, pop: Population) -> bool:
    """Is this specific problem one the population is declared dormant about?"""
    p = str(problem).lower()
    if not pop.quiet_is_a_fault and ("quiet" in p or "no new forecast" in p):
        return True
    if not pop.overdue_is_a_fault and ("past due" in p or "overdue" in p):
        return True
    return False


def registry_health(*, root: Path | None = None,
                    today: date | None = None) -> dict:
    """Every population, each with its own row, and a status that says WHICH.

    The top-level status is deliberately NOT a pooled judgement. It names the
    populations that are unhealthy, so a reader can never again mistake one
    population's silence for the system's.
    """
    rows = [health(p.population_id, root=root, today=today)
            for p in _POPULATIONS]
    bad = [r["population_id"] for r in rows
           if r.get("status") not in ("ok", "OK", "DORMANT_BY_DESIGN")]
    return {
        "status": "ok" if not bad else "DEGRADED",
        "degraded_populations": bad,
        "n_populations": len(rows),
        "populations": {r["population_id"]: r for r in rows},
        "pooling": ("REFUSED -- these populations have different producers "
                    "and different resolvers. There is no prospectively "
                    "declared rule for combining them, so no surface sums "
                    "them."),
    }


def assert_named(population_id: str | None, *, consumer: str) -> Population:
    """A consumer must say which population it reads. Refuses the blank case."""
    if not population_id:
        raise PopulationNotNamed(
            f"{consumer} asked for forecasts without naming a population. "
            f"There are {len(_POPULATIONS)} and they are not "
            f"interchangeable: {known_ids()}.")
    pop = get(population_id)
    if consumer not in pop.consumers:
        logger.warning("consumer %r is reading population %r, which does not "
                       "list it. Declare it in _POPULATIONS.consumers so the "
                       "dependency is visible.", consumer, population_id)
    return pop


def refuse_pooling(*population_ids: str) -> None:
    """Called at any site tempted to add two populations together."""
    if len(set(population_ids)) > 1:
        raise PopulationPoolingRefused(
            f"refusing to pool {sorted(set(population_ids))}: different "
            f"producers, different resolvers, no declared pooling rule. "
            f"Report them side by side or pick one.")
