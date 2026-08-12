"""The scheduler job-set canary (NIGHT-13 §8, built NIGHT-14).

On 2026-08-12 a rolling deploy silently deleted `pi_ledger_resolve`. Mechanism,
verified live: both replicas share the persistent SQLAlchemyJobStore under
DATA_DIR. The OLD replica — running code that has never heard of the new job's
target function — called get_jobs(), failed to deserialize it, and APScheduler
REMOVES jobs it cannot restore. Startup logged "5 jobs"; the live scheduler then
had 4, and the ledger resolver simply never ran.

Nothing measured the job SET, so nothing could see it: four jobs is a perfectly
plausible number. These tests pin the set, the missing/unexpected diff, and its
appearance in /api/health/full's degraded_reasons WITH the job id named.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from backend.main import app
from backend.services.portfolio_intelligence import scheduler as sched_mod

client = TestClient(app)


class _FakeJob:
    def __init__(self, job_id: str) -> None:
        self.id = job_id
        self.next_run_time = None


class _FakeJobStore:
    """Stands in for SQLAlchemyJobStore — only its class name is read."""


class _FakeScheduler:
    """The live scheduler as the health surface sees it: an id list."""

    running = True

    def __init__(self, job_ids) -> None:
        self._jobs = [_FakeJob(j) for j in job_ids]
        self._jobstores = {"default": _FakeJobStore()}

    def get_jobs(self):
        return list(self._jobs)


# ── the declaration is the single source of truth ───────────────────────────
def test_every_job_setup_registers_is_declared_and_vice_versa():
    """EXPECTED_JOB_IDS must equal the ids setup_scheduler() actually adds.

    Read off the source rather than by starting a scheduler: a declaration that
    drifts from the add_job() calls turns the canary into decoration, and the
    drift would otherwise only surface as a false alarm in production.
    """
    import inspect

    src = inspect.getsource(sched_mod.setup_scheduler)
    registered = set(re.findall(r'\n\s*id="([^"]+)"', src))
    assert registered, "no add_job ids found — the scraper needs updating"
    assert registered == set(sched_mod.EXPECTED_JOB_IDS), (
        f"declared {sorted(sched_mod.EXPECTED_JOB_IDS)} != registered "
        f"{sorted(registered)}")


def test_the_job_that_vanished_is_in_the_expected_set():
    """The specific regression: `pi_ledger_resolve` is the job the rolling
    deploy ate, and the ledger cannot resolve without it."""
    assert "pi_ledger_resolve" in sched_mod.EXPECTED_JOB_IDS


# ── the diff ────────────────────────────────────────────────────────────────
def test_a_missing_job_is_degraded_and_named(monkeypatch):
    live = set(sched_mod.EXPECTED_JOB_IDS) - {"pi_ledger_resolve"}
    monkeypatch.setattr(sched_mod, "_scheduler", _FakeScheduler(live))
    row = sched_mod.scheduler_jobs_health()
    assert row["status"] == "DEGRADED"
    assert row["missing"] == ["pi_ledger_resolve"]
    assert row["unexpected"] == []
    assert "pi_ledger_resolve" in row["reason"]


def test_a_full_job_set_reads_ok(monkeypatch):
    monkeypatch.setattr(sched_mod, "_scheduler",
                        _FakeScheduler(sched_mod.EXPECTED_JOB_IDS))
    row = sched_mod.scheduler_jobs_health()
    assert row["status"] == "ok"
    assert row["missing"] == [] and row["unexpected"] == []
    assert row["actual"] == sorted(sched_mod.EXPECTED_JOB_IDS)


def test_an_undeclared_job_is_degraded_too(monkeypatch):
    """A renamed job whose old id is still persisted in the shared jobstore
    keeps firing forever beside the new one — the other half of the same
    jobstore-rollover failure."""
    monkeypatch.setattr(sched_mod, "_scheduler",
                        _FakeScheduler({*sched_mod.EXPECTED_JOB_IDS, "pi_old_ghost"}))
    row = sched_mod.scheduler_jobs_health()
    assert row["status"] == "DEGRADED"
    assert row["unexpected"] == ["pi_old_ghost"]


def test_no_scheduler_reports_unavailable_rather_than_five_missing_jobs(monkeypatch):
    """Absence of a scheduler is not evidence of deleted jobs. Fabricating five
    missing ids in every test run and local process would bury the real one."""
    monkeypatch.setattr(sched_mod, "_scheduler", None)
    row = sched_mod.scheduler_jobs_health()
    assert row["status"] == "unavailable"
    assert row["missing"] == [] and row["actual"] == []
    assert "not started" in row["reason"]


def test_an_unreadable_jobstore_is_unavailable_not_ok(monkeypatch):
    class _Broken(_FakeScheduler):
        def get_jobs(self):
            raise RuntimeError("jobstore locked")

    monkeypatch.setattr(sched_mod, "_scheduler", _Broken([]))
    row = sched_mod.scheduler_jobs_health()
    assert row["status"] == "unavailable"
    assert "jobstore locked" in row["error"]


# ── the health surface ──────────────────────────────────────────────────────
def test_health_full_names_the_missing_job_in_degraded_reasons(monkeypatch):
    live = set(sched_mod.EXPECTED_JOB_IDS) - {"pi_ledger_resolve"}
    monkeypatch.setattr(sched_mod, "_scheduler", _FakeScheduler(live))
    body = client.get("/api/health/full").json()
    jobs = body["scheduler"]["jobs"]
    assert jobs["missing"] == ["pi_ledger_resolve"]
    assert body["status"] == "DEGRADED"
    assert "scheduler job missing: pi_ledger_resolve" in body["degraded_reasons"], (
        "the id must be named — 'scheduler degraded' sends the next session hunting")


def test_health_full_adds_no_job_reason_when_the_set_is_whole(monkeypatch):
    monkeypatch.setattr(sched_mod, "_scheduler",
                        _FakeScheduler(sched_mod.EXPECTED_JOB_IDS))
    body = client.get("/api/health/full").json()
    jobs = body["scheduler"]["jobs"]
    assert jobs["status"] == "ok"
    # Other canaries (nav freshness, ledger) may legitimately degrade in a test
    # environment; what is pinned here is that no JOB reason is invented.
    assert not any(r.startswith("scheduler job ")
                   for r in body["degraded_reasons"])


def test_health_full_carries_the_jobs_block_even_with_no_scheduler(monkeypatch):
    monkeypatch.setattr(sched_mod, "_scheduler", None)
    body = client.get("/api/health/full").json()
    jobs = body["scheduler"]["jobs"]
    assert jobs["status"] == "unavailable"
    assert jobs["expected"] == sorted(sched_mod.EXPECTED_JOB_IDS)
    assert not any(r.startswith("scheduler job ")
                   for r in body["degraded_reasons"])
