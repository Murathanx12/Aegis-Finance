"""
Tests for the Portfolio Intelligence scheduler.

Verifies:
  - Scheduler setup registers 3 jobs (hourly MTM, daily check, weekly aggressive)
  - SQLAlchemyJobStore is used (persistent, not in-memory)
  - Hourly MTM short-circuits when no new data
  - Manual trigger returns expected format
  - Scheduler shutdown is clean
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock


from backend.services.portfolio_intelligence.scheduler import (
    manual_trigger,
)


class TestSetupScheduler:
    def test_creates_scheduler_with_exactly_the_declared_job_set(self):
        """The registered jobs must equal EXPECTED_JOB_IDS — set equality, not a
        count.

        This assertion used to read `len(jobs) == 5` alongside five membership
        checks, and adding `pi_why_moved` broke it in CI while every scheduler
        test passed locally. That is the same shape as the count-based
        `/health/scheduler` gate which could not see NIGHT-13's vanished job: a
        number is a weak proxy for a set, and it fails in both directions — it
        breaks on a legitimate addition and it stays silent when two jobs swap.

        Comparing against EXPECTED_JOB_IDS instead means the declaration is the
        single source of truth: a job added without declaring it fails here, a
        job declared without registering it fails here, and a correctly-added
        job needs no edit to this test at all.
        """
        from backend.services.portfolio_intelligence.scheduler import (
            EXPECTED_JOB_IDS, setup_scheduler, shutdown_scheduler,
        )

        async def _run():
            scheduler = setup_scheduler()
            assert scheduler is not None
            job_ids = {j.id for j in scheduler.get_jobs()}
            assert job_ids == set(EXPECTED_JOB_IDS), (
                f"registered {sorted(job_ids)} != declared "
                f"{sorted(EXPECTED_JOB_IDS)}")
            shutdown_scheduler()

        asyncio.run(_run())

    def test_uses_persistent_job_store(self):
        """Scheduler should use SQLAlchemyJobStore, not in-memory default."""
        from backend.services.portfolio_intelligence.scheduler import (
            setup_scheduler, shutdown_scheduler,
        )

        async def _run():
            scheduler = setup_scheduler()
            assert scheduler is not None
            store = scheduler._jobstores.get("default")
            assert store is not None
            assert "SQLAlchemy" in type(store).__name__, (
                f"Expected SQLAlchemyJobStore, got {type(store).__name__}"
            )
            shutdown_scheduler()

        asyncio.run(_run())

    def test_shutdown_without_start(self):
        from backend.services.portfolio_intelligence.scheduler import shutdown_scheduler
        shutdown_scheduler()


class TestHourlyMTM:
    def test_short_circuits_when_recent(self):
        """Hourly MTM should skip if last run was < 50 minutes ago."""
        import backend.services.portfolio_intelligence.scheduler as sched

        sched._last_mtm_timestamp = datetime.now() - timedelta(minutes=30)

        with patch("backend.services.portfolio_intelligence.reference_engine.run_all_lanes") as mock:
            asyncio.run(sched._hourly_mtm())
            mock.assert_not_called()

        sched._last_mtm_timestamp = None


class TestDailyCheckWiresBookLanes:
    def test_daily_check_invokes_book_management(self):
        """Plan 3: the daily check must drive book-lane management (mirror cadence
        + conviction decisions), isolated so a book failure can't break the
        reference-lane check."""
        import backend.services.portfolio_intelligence.scheduler as sched

        with patch(
            "backend.services.portfolio_intelligence.reference_engine.run_all_lanes",
            return_value={},
        ), patch(
            "backend.services.portfolio_intelligence.book_management.run_all_book_management",
            return_value={"mirror": {"status": "not_seeded"},
                          "conviction": {"status": "not_seeded"}},
        ) as mock_book, patch(
            "backend.services.portfolio_intelligence.fragility.run_lppls_eval",
            return_value={},
        ), patch(
            "backend.services.portfolio_intelligence.fragility.run_fragility_eval",
            return_value={},
        ):
            asyncio.run(sched._daily_check())
            mock_book.assert_called_once()

    def test_daily_check_invokes_new_collectors(self):
        """The fragility-candidate and 13F collectors must run on the daily
        check (wired 2026-07-08), each isolated so a failure can't break lane
        processing."""
        import backend.services.portfolio_intelligence.scheduler as sched

        with patch(
            "backend.services.portfolio_intelligence.reference_engine.run_all_lanes",
            return_value={},
        ), patch(
            "backend.services.portfolio_intelligence.book_management.run_all_book_management",
            return_value={},
        ), patch(
            "backend.services.portfolio_intelligence.fragility.run_lppls_eval",
            return_value={},
        ), patch(
            "backend.services.portfolio_intelligence.fragility.run_fragility_eval",
            return_value={},
        ), patch(
            "backend.services.portfolio_intelligence.fragility_candidates.collect_fragility_candidates",
            return_value={"status": "collected", "n": 3, "nonzero": 3},
        ) as mock_frag, patch(
            "backend.services.pit_collectors.collect_all_13f",
            return_value={"recorded": [], "unchanged": [], "errors": []},
        ) as mock_13f:
            asyncio.run(sched._daily_check())
            mock_frag.assert_called_once()
            mock_13f.assert_called_once()


class TestManualTrigger:
    def test_single_lane(self):
        mock_snapshot = MagicMock()
        mock_snapshot.portfolio_id = "conservative"
        mock_snapshot.date = "2026-04-27"
        mock_snapshot.latest_rebalance = None

        with patch(
            "backend.services.portfolio_intelligence.reference_engine.run_reference_check",
            return_value=mock_snapshot,
        ):
            result = asyncio.run(manual_trigger("conservative"))
        assert "conservative" in result
        assert result["conservative"]["rebalanced"] is False

    def test_all_lanes(self):
        mock_snapshot = MagicMock()
        mock_snapshot.portfolio_id = "test"
        mock_snapshot.date = "2026-04-27"
        mock_snapshot.latest_rebalance = None

        with patch(
            "backend.services.portfolio_intelligence.reference_engine.run_all_lanes",
            return_value={
                "conservative": mock_snapshot,
                "balanced": mock_snapshot,
                "aggressive": mock_snapshot,
            },
        ):
            result = asyncio.run(manual_trigger(None))
        assert len(result) == 3


class TestWhyMovedNightly:
    def test_nightly_call_satisfies_the_real_signature(self, monkeypatch):
        """The wrapper shipped calling run_why_moved() with no arguments and
        crashed with a TypeError EVERY night until 2026-08-22 — the exact
        green-and-empty failure its own docstring warns about, surviving
        because nothing ever exercised the call. This test binds the wrapper
        to the REAL function's signature: the fake below enforces the same
        required parameters, so a future drift fails here, offline, not in
        prod at 17:15 ET."""
        from backend.services import why_moved as wm
        from backend.services.portfolio_intelligence import scheduler as sched

        seen: dict = {}

        def fake_run_why_moved(positions, requested_date, *,
                               with_hypotheses=True, write_ledger=False,
                               skip_if_minted=False, **kw):
            seen["positions"] = positions
            seen["requested_date"] = requested_date
            seen["write_ledger"] = write_ledger
            seen["skip_if_minted"] = skip_if_minted
            return {"status": "ok", "as_of": requested_date,
                    "n_predictions_minted": 1, "hypotheses": [],
                    "lenses": [], "attribution": {"pnl_usd": 0.0,
                                                  "pnl_pct": 0.0}}

        monkeypatch.setattr(wm, "run_why_moved", fake_run_why_moved)
        monkeypatch.setattr(wm, "book_positions",
                            lambda: [("AAPL", 10.0)])
        asyncio.run(sched._why_moved_nightly())
        assert seen["positions"] == [("AAPL", 10.0)]
        assert seen["requested_date"]  # a date string, derived not defaulted
        assert seen["write_ledger"] is True  # minting is the point of the job
        assert seen["skip_if_minted"] is True  # catch-up slots must not re-mint

    def test_already_written_retry_is_a_quiet_no_op(self, monkeypatch, caplog):
        """A catch-up firing on a minted day logs INFO, never the
        NOTHING-GRADEABLE warning — the loud path is reserved for a FIRST
        pass that bought nothing, and a nightly false alarm trains the
        reader to ignore the real one."""
        import logging

        from backend.services import why_moved as wm
        from backend.services.portfolio_intelligence import scheduler as sched

        def fake_run_why_moved(positions, requested_date, **kw):
            return {"status": "already_written", "as_of": requested_date,
                    "n_predictions_minted": 0, "hypotheses": [], "lenses": [],
                    "attribution": {"pnl_usd": 0.0, "pnl_pct": 0.0}}

        monkeypatch.setattr(wm, "run_why_moved", fake_run_why_moved)
        monkeypatch.setattr(wm, "book_positions", lambda: [("AAPL", 10.0)])
        with caplog.at_level(logging.INFO,
                             logger=sched.logger.name):
            asyncio.run(sched._why_moved_nightly())
        assert not any(r.levelno >= logging.WARNING for r in caplog.records)
        assert any("already minted" in r.getMessage() for r in caplog.records)

    def test_trigger_has_day_guard_and_catch_up_slots(self):
        """ORDER 27 carry-over, pinned: without mon-fri a weekend firing
        walks back to Friday and re-mints Friday's records; without the
        17-19 slots a process restart at 17:15 erases the night (the
        2026-08-21 arena lesson, 4 restarts in 71 minutes)."""
        from backend.services.portfolio_intelligence.scheduler import (
            setup_scheduler, shutdown_scheduler,
        )

        async def _run():
            scheduler = setup_scheduler()
            trigger = str(scheduler.get_job("pi_why_moved").trigger)
            assert "day_of_week='mon-fri'" in trigger, trigger
            assert "hour='17-19'" in trigger, trigger
            assert "minute='15'" in trigger, trigger
            shutdown_scheduler()

        asyncio.run(_run())


class TestEveryJobIsInvocableAndGated:
    """The why_moved lesson, generalized: a scheduled job that cannot even be
    CALLED the way APScheduler calls it (zero arguments) is a bug that ships
    silently — the TypeError lands in a log nobody reads at 17:15 ET. This
    walks the REAL registrations, so a job added tomorrow is covered the day
    it is added, with no edit here."""

    def test_registered_funcs_are_async_zero_arg_and_gated(self):
        import inspect

        from backend.services.portfolio_intelligence.scheduler import (
            EXPECTED_JOB_IDS, setup_scheduler, shutdown_scheduler,
        )

        async def _run():
            scheduler = setup_scheduler()
            assert scheduler is not None
            jobs = {j.id: j for j in scheduler.get_jobs()}
            assert set(jobs) == set(EXPECTED_JOB_IDS)
            for job_id, job in jobs.items():
                fn = job.func
                assert inspect.iscoroutinefunction(fn), (
                    f"{job_id}: scheduled func must be async "
                    f"(AsyncIOScheduler), got {fn!r}")
                # APScheduler fires with the job's args/kwargs — ours are
                # empty, so the signature must bind with nothing.
                try:
                    inspect.signature(fn).bind(*job.args or (),
                                               **job.kwargs or {})
                except TypeError as e:
                    raise AssertionError(
                        f"{job_id}: registered call does not satisfy the "
                        f"function signature — the why_moved bug shape: {e}")
                # Every job runs behind the heavy-work gate (the 2026-08-21
                # OOM lesson). functools.wraps leaves __wrapped__ behind.
                assert hasattr(fn, "__wrapped__"), (
                    f"{job_id}: job is not @_gated — background computes "
                    f"may stack and OOM the process")
            shutdown_scheduler()

        asyncio.run(_run())


# ── The execution clock: submit in the pass that decided ───────────────────
# An arena book decides at 17:45 for the next open. The Alpaca sync lived in
# the 16:30 job, which runs BEFORE that — so the external account executed each
# decision roughly two sessions late and was validating a delayed variant of
# the strategy. Which job owns which target kind is therefore load-bearing, not
# a scheduling detail.


class TestPaperBrokerExecutionClock:

    def _stub(self, monkeypatch, target_id, calls):
        from backend.services.portfolio_intelligence import (
            alpaca_mirror, paper_broker_targets, scheduler as sched,
        )
        monkeypatch.setenv("AEGIS_PAPER_BROKER_TARGET", target_id)
        monkeypatch.delenv("AEGIS_ARENA_BROKER_TARGET", raising=False)
        monkeypatch.setattr(
            alpaca_mirror, "sync_alpaca_mirror",
            lambda db_path=None, target=None: (
                calls.append(getattr(target, "target_id", None))
                or {"status": "synced", "trades": [], "basis": "intent"}))
        return sched, paper_broker_targets

    def test_an_arena_target_is_submitted_after_the_deciding_pass(
            self, monkeypatch):
        calls = []
        sched, _ = self._stub(monkeypatch, "arena:CURRENT_BEST_v1", calls)
        asyncio.run(sched._submit_arena_broker_intent())
        assert calls == ["arena:CURRENT_BEST_v1"], (
            "the arena's queued intent never reached the paper broker in the "
            "pass that produced it")

    def test_a_lane_target_is_NOT_submitted_from_the_arena_pass(
            self, monkeypatch):
        calls = []
        sched, _ = self._stub(monkeypatch, "lane:mirror", calls)
        asyncio.run(sched._submit_arena_broker_intent())
        assert calls == [], (
            "the mirror lane was traded twice a day — once from the 16:30 "
            "job and once from the arena pass")

    def test_the_arena_book_is_declared_independently_of_the_lane(
            self, monkeypatch):
        """Both mirrors run: the lane keeps its verified account and its 16:30
        sync, the arena book gets its own account and this submit."""
        calls = []
        sched, _ = self._stub(monkeypatch, "lane:mirror", calls)
        monkeypatch.setenv("AEGIS_ARENA_BROKER_TARGET", "CURRENT_BEST_v1")
        asyncio.run(sched._submit_arena_broker_intent())
        assert calls == ["arena:CURRENT_BEST_v1"], (
            "declaring an arena book did not reach the submit, or it "
            "hijacked the lane's declaration")

    def test_a_RAISED_pass_submits_nothing(self, monkeypatch):
        """The defect fixed 2026-09-01.

        `_arena_daily` swallowed `run_daily`'s exception and then called the
        submit unconditionally underneath it. A raised pass therefore queued
        the PREVIOUS session's intent for today's open -- exactly the failure
        the function's own comment says it exists to prevent. `decided_for`
        travelled onto the submission and named the stale session correctly,
        and gated nothing: the provenance was right and nobody read it.
        """
        from backend.services.arena import engine as arena_engine
        calls = []
        sched, _ = self._stub(monkeypatch, "arena:CURRENT_BEST_v1", calls)

        def _boom():
            raise RuntimeError("arena engine down")
        monkeypatch.setattr(arena_engine, "run_daily", _boom)

        asyncio.run(sched._arena_daily())          # must not raise
        assert calls == [], (
            "a pass that produced no decision still submitted orders -- that "
            "is an order placed for an open no book decided for")

    def test_a_pass_that_COMPLETED_still_submits(self, monkeypatch):
        """The guard must only cut the unambiguous case. A completed pass --
        even a degraded one -- produced fresh intent and must still reach the
        broker, or the fix would silently stop the arena trading."""
        from backend.services.arena import engine as arena_engine
        calls = []
        sched, _ = self._stub(monkeypatch, "arena:CURRENT_BEST_v1", calls)
        monkeypatch.setattr(arena_engine, "run_daily",
                            lambda: {"status": "ok", "receipts": [], "session": "2026-09-01"})
        asyncio.run(sched._arena_daily())
        assert calls == ["arena:CURRENT_BEST_v1"]

    def test_the_triggerable_half_never_submits(self, monkeypatch):
        """`/api/optimus/run_job/pi_arena_daily` is bound to
        `_arena_daily_pass`, not `_arena_daily`. Pressing a button at 08:00
        must repair the forecast record without placing a single order."""
        from backend.services.arena import engine as arena_engine
        calls = []
        sched, _ = self._stub(monkeypatch, "arena:CURRENT_BEST_v1", calls)
        monkeypatch.setattr(arena_engine, "run_daily",
                            lambda: {"status": "ok", "receipts": [], "session": "2026-09-01"})
        assert asyncio.run(sched._arena_daily_pass()) is True
        assert calls == [], "the triggerable half submitted orders"

    def test_the_allowlist_binds_the_decision_half_not_the_trading_one(self):
        """Pinned because the difference is one underscore-suffixed name and
        getting it wrong turns a repair endpoint into an order button."""
        from backend.routers import optimus_ledger
        import inspect
        src = inspect.getsource(optimus_ledger.run_job_now)
        assert '"pi_arena_daily": _sched._arena_daily_pass' in src, src

    def test_an_unresolvable_target_does_not_kill_the_arena_pass(
            self, monkeypatch):
        calls = []
        sched, _ = self._stub(monkeypatch, "nonsense", calls)
        asyncio.run(sched._submit_arena_broker_intent())  # must not raise
        assert calls == []
