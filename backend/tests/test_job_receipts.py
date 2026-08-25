"""Every scheduled job leaves a dated record, including the runs that did nothing.

THE FOUR STATES THAT PRODUCED IDENTICAL EVIDENCE
================================================
    the job was skipped        the job never ran
    the job ran and failed     the job wrote to the wrong place

`options_pit` wrote inside the container image and every deploy destroyed it.
`_hourly_mtm` dropped four `paper_nav` days behind two early returns that logged
at DEBUG — below production level — and wrote nothing. Both emitted output that
LOOKED like a measurement and was an absence.

This is the generic wrapper that replaces writing a twelfth bespoke receipt by
hand. After it, no new observability work without a concrete failure.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from backend.services import job_receipts as JR


@pytest.fixture(autouse=True)
def _tmp_ledger(monkeypatch, tmp_path):
    from backend import config as _config
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_DIR", tmp_path)
    return tmp_path


def _run(coro):
    return asyncio.run(coro)


def _receipts(job: str) -> list[dict]:
    return JR.read(job, limit=50)["receipts"]


# ── every outcome leaves exactly one record ─────────────────────────────────


def test_a_job_that_succeeds_writes_a_receipt():
    @JR.receipted("t_ok")
    async def job():
        return "done"

    assert _run(job()) == "done"
    r = _receipts("t_ok")
    assert len(r) == 1
    assert r[0]["status"] == "ran"
    assert r[0]["started_at"] and r[0]["finished_at"]
    assert r[0]["duration_seconds"] >= 0


def test_a_job_that_RAISES_still_writes_one_and_the_exception_propagates():
    """The receipt must not swallow the failure — a job that silently
    'succeeded' because it was being observed is worse than no observation."""
    @JR.receipted("t_boom")
    async def job():
        raise ValueError("nope")

    with pytest.raises(ValueError):
        _run(job())
    r = _receipts("t_boom")
    assert len(r) == 1
    assert r[0]["status"] == "raised"
    assert "ValueError: nope" in r[0]["exception"]
    assert r[0]["finished_at"], "a raising job must still be timed"


def test_a_SKIP_is_a_RESULT_and_says_why():
    """THE DEFECT. An early return that leaves nothing behind is
    indistinguishable from a job that never fired."""
    @JR.receipted("t_skip")
    async def job():
        JR.note(skip_reason="cached timestamp not newer than last mark",
                expected_data_date="2026-08-24")
        return None

    _run(job())
    r = _receipts("t_skip")[0]
    assert r["status"] == "skipped"
    assert "cached timestamp" in r["skip_reason"]
    assert r["expected_data_date"] == "2026-08-24"


def test_a_job_that_returns_without_annotating_is_recorded_as_ran_with_nothing():
    """Recorded as a CLAIM a reader can challenge, rather than as silence."""
    @JR.receipted("t_quiet")
    async def job():
        return None

    _run(job())
    r = _receipts("t_quiet")[0]
    assert r["status"] == "ran"
    assert r["writes"] is None and r["skip_reason"] is None


def test_what_a_job_wrote_is_on_the_receipt():
    @JR.receipted("t_writes")
    async def job():
        JR.note(writes={"lanes_marked": ["balanced", "mirror"]})

    _run(job())
    assert _receipts("t_writes")[0]["writes"]["lanes_marked"] == [
        "balanced", "mirror"]


# ── the wrapper must not break the scheduler ────────────────────────────────


def test_the_wrapper_preserves_the_qualname_the_jobstore_resolves():
    """NIGHT-13: the persistent SQLAlchemy jobstore resolves jobs by module
    reference, and APScheduler REMOVES jobs it cannot deserialize. A wrapper
    that lost the name would silently delete the job at a rolling deploy."""
    async def _arena_daily():
        return None

    wrapped = JR.receipted()(_arena_daily)
    assert wrapped.__name__ == "_arena_daily"
    assert wrapped.__qualname__ == _arena_daily.__qualname__


def test_the_default_job_name_strips_the_private_underscore():
    @JR.receipted()
    async def _ownership_collect():
        return None

    _run(_ownership_collect())
    assert JR.read("ownership_collect")["n_receipts"] == 1


def test_a_receipt_failure_never_takes_down_the_job(monkeypatch):
    """A job must not die because its observer did."""
    monkeypatch.setattr(JR, "_root",
                        lambda: (_ for _ in ()).throw(OSError("no disk")))

    @JR.receipted("t_nodisk")
    async def job():
        return 42

    assert _run(job()) == 42


def test_note_outside_a_job_is_a_noop_not_a_crash():
    """So a job body stays callable in isolation, in a test or a REPL."""
    JR.note(skip_reason="nothing in flight")


def test_concurrent_jobs_do_not_annotate_each_others_receipts():
    """A ContextVar and not a module global: jobs are async and the heavy-work
    gate may interleave them."""
    @JR.receipted("t_a")
    async def a():
        await asyncio.sleep(0.01)
        JR.note(skip_reason="A's reason")

    @JR.receipted("t_b")
    async def b():
        JR.note(skip_reason="B's reason")

    async def both():
        await asyncio.gather(a(), b())

    _run(both())
    assert _receipts("t_a")[0]["skip_reason"] == "A's reason"
    assert _receipts("t_b")[0]["skip_reason"] == "B's reason"


# ── reading them back ───────────────────────────────────────────────────────


def test_read_names_the_directory_it_looked_in_even_when_empty():
    """`options_pit` cost an hour because `ABSENT` did not say absent FROM
    WHERE."""
    out = JR.read("never_ran")
    assert out["exists"] is False
    assert out["n_receipts"] == 0
    assert "dir" in out and "never_ran" in out["dir"]


def test_receipts_come_back_newest_first():
    @JR.receipted("t_order")
    async def job():
        return None

    for _ in range(3):
        _run(job())
    r = _receipts("t_order")
    assert len(r) == 3
    assert [x["started_at"] for x in r] == sorted(
        [x["started_at"] for x in r], reverse=True)


def test_pruning_is_PER_JOB_so_a_chatty_job_cannot_evict_a_quiet_one():
    """The absence being investigated is usually the quiet job's."""
    monkey = JR.MAX_RECEIPTS_PER_JOB
    try:
        JR.MAX_RECEIPTS_PER_JOB = 3

        @JR.receipted("t_chatty")
        async def chatty():
            return None

        @JR.receipted("t_quiet2")
        async def quiet():
            return None

        _run(quiet())
        for _ in range(6):
            _run(chatty())
        assert JR.read("t_chatty")["n_receipts"] <= 3
        assert JR.read("t_quiet2")["n_receipts"] == 1, (
            "a chatty job evicted a quiet job's only receipt")
    finally:
        JR.MAX_RECEIPTS_PER_JOB = monkey


def test_known_jobs_lists_what_has_actually_written():
    @JR.receipted("t_listed")
    async def job():
        return None

    _run(job())
    assert "t_listed" in JR.known_jobs()


# ── the scheduler is actually wired to it ───────────────────────────────────


def test_the_scheduled_jobs_are_wrapped():
    """A wrapper nothing applies is the `detectability_gate` failure: a guard
    named in comments and invoked by nobody."""
    from pathlib import Path
    src = Path("backend/services/portfolio_intelligence/scheduler.py").read_text(
        encoding="utf-8")
    assert "from backend.services.job_receipts import" in src
    for job in ("_arena_daily", "_ledger_resolve", "_options_pit_capture",
                "_daily_check", "_ownership_collect"):
        assert f"@receipted()\n@_gated\nasync def {job}(" in src, (
            f"{job} is not wrapped, so a silent skip in it is still invisible")


def test_hourly_mtm_keeps_its_bespoke_receipt_for_now():
    """DELIBERATE. Its receipt was deployed at 38d028d to diagnose four missing
    `paper_nav` days and fires at 16:30 ET. Refactoring it before that firing
    would forfeit the diagnosis to remove a duplication — the wrong trade. This
    test is the reminder to migrate it AFTER the receipt has been read."""
    from pathlib import Path
    src = Path("backend/services/portfolio_intelligence/scheduler.py").read_text(
        encoding="utf-8")
    assert "_write_mtm_receipt" in src
    assert "@receipted()\n@_gated\nasync def _hourly_mtm(" not in src


def test_the_endpoint_serves_every_jobs_receipts():
    from pathlib import Path
    src = Path("backend/routers/optimus_ledger.py").read_text(encoding="utf-8")
    assert "scheduled_jobs" in src and "JR.known_jobs()" in src


def test_the_ledger_root_is_resolved_through_config_not_dunder_file():
    """The `options_pit` defect: a path rebuilt from `__file__` points inside
    the deployed image, which Railway wipes on every deploy."""
    from pathlib import Path
    src = Path("backend/services/job_receipts.py").read_text(encoding="utf-8")
    assert "OPTIMUS_LEDGER_DIR" in src
    assert "Path(__file__).resolve().parents" not in src
