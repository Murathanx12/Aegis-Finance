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
    def test_creates_scheduler_with_three_jobs(self):
        """Scheduler should register hourly MTM, daily check, and weekly aggressive."""
        from backend.services.portfolio_intelligence.scheduler import (
            setup_scheduler, shutdown_scheduler,
        )

        async def _run():
            scheduler = setup_scheduler()
            assert scheduler is not None
            jobs = scheduler.get_jobs()
            job_ids = {j.id for j in jobs}
            assert "pi_hourly_mtm" in job_ids, "Missing hourly MTM job"
            assert "pi_daily_check" in job_ids, "Missing daily check job"
            assert "pi_weekly_aggressive" in job_ids, "Missing weekly aggressive job"
            assert len(jobs) == 3
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
