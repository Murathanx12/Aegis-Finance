"""
Aegis Finance — Portfolio Intelligence Scheduler
===================================================

In-process APScheduler with SQLite job store for persistence across
Railway redeploys. Railway cron endpoint as belt-and-suspenders fallback.

Schedule:
  - Hourly (market hours): mark-to-market, short-circuits if no new data
  - Daily 16:30 ET: full rebalance check for all lanes
  - Weekly Mon 09:00 ET: additional aggressive lane check

Usage:
    from backend.services.portfolio_intelligence.scheduler import (
        setup_scheduler, manual_trigger,
    )
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

_scheduler = None
_last_mtm_timestamp: datetime | None = None

_DB_DIR = Path(__file__).parent.parent.parent / "data"


def setup_scheduler():
    """Set up APScheduler with SQLite persistence.

    Uses SQLAlchemyJobStore backed by the same data/ directory as
    the PI database, so scheduled jobs survive Railway redeploys.
    """
    global _scheduler

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
    except ImportError:
        logger.warning("APScheduler not installed — scheduler disabled")
        return None

    _DB_DIR.mkdir(parents=True, exist_ok=True)
    job_store_url = f"sqlite:///{_DB_DIR / 'apscheduler_jobs.db'}"

    jobstores = {
        "default": SQLAlchemyJobStore(url=job_store_url),
    }

    _scheduler = AsyncIOScheduler(jobstores=jobstores)

    # Hourly mark-to-market during US market hours (9:30-16:30 ET)
    _scheduler.add_job(
        _hourly_mtm,
        CronTrigger(
            hour="10-16", minute=30,
            day_of_week="mon-fri",
            timezone="US/Eastern",
        ),
        id="pi_hourly_mtm",
        name="PI hourly mark-to-market",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Daily full rebalance check at market close
    _scheduler.add_job(
        _daily_check,
        CronTrigger(hour=16, minute=30, timezone="US/Eastern"),
        id="pi_daily_check",
        name="PI daily rebalance check",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Weekly aggressive lane check
    _scheduler.add_job(
        _weekly_aggressive_check,
        CronTrigger(day_of_week="mon", hour=9, minute=0, timezone="US/Eastern"),
        id="pi_weekly_aggressive",
        name="PI weekly aggressive check",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    _scheduler.start()
    logger.info(
        "Portfolio Intelligence scheduler started (job store: %s, %d jobs)",
        job_store_url, len(_scheduler.get_jobs()),
    )
    return _scheduler


def scheduler_health() -> dict:
    """Health snapshot for the /health/scheduler canary.

    A silently-dead scheduler means a flat-line track record (no MTM, no
    rebalances) — the #1 deploy risk. This exposes enough for an external
    uptime check to alarm on: running flag, job count/ids, persistent job
    store type, and the last successful mark-to-market timestamp.
    """
    if _scheduler is None:
        return {"running": False, "n_jobs": 0, "jobstore": None,
                "job_ids": [], "last_mtm": None,
                "reason": "scheduler not started (APScheduler missing or setup failed)"}
    try:
        jobs = _scheduler.get_jobs()
        store = _scheduler._jobstores.get("default")
        return {
            "running": bool(getattr(_scheduler, "running", False)),
            "n_jobs": len(jobs),
            "job_ids": sorted(j.id for j in jobs),
            "jobstore": type(store).__name__ if store else None,
            "persistent": bool(store and "SQLAlchemy" in type(store).__name__),
            "last_mtm": _last_mtm_timestamp.isoformat() if _last_mtm_timestamp else None,
        }
    except Exception as e:
        return {"running": False, "error": str(e)}


def shutdown_scheduler():
    """Gracefully shut down the scheduler."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Portfolio Intelligence scheduler stopped")


async def _hourly_mtm():
    """Hourly mark-to-market during market hours.

    Short-circuits if no new market data since last run (avoids
    redundant computation when data hasn't changed).
    """
    global _last_mtm_timestamp

    now = datetime.now()
    if _last_mtm_timestamp and (now - _last_mtm_timestamp) < timedelta(minutes=50):
        logger.debug("Hourly MTM: skipping, last run was %s", _last_mtm_timestamp)
        return

    # Check if market data has been updated since last MTM
    try:
        from backend.cache import cache_get
        cached_ts = cache_get("market_data_timestamp")
        if cached_ts and _last_mtm_timestamp:
            if isinstance(cached_ts, str):
                cached_dt = datetime.fromisoformat(cached_ts)
            else:
                cached_dt = cached_ts
            if cached_dt <= _last_mtm_timestamp:
                logger.debug("Hourly MTM: no new market data since %s", _last_mtm_timestamp)
                return
    except Exception:
        pass  # If cache check fails, proceed with MTM

    import asyncio
    from backend.services.portfolio_intelligence.reference_engine import mark_all_lanes

    logger.info("Running hourly MTM at %s", now.isoformat())
    try:
        # Hourly job MARKS TO MARKET (persists daily NAV) — it does not rebalance.
        # Rebalance decisions happen in the daily check.
        await asyncio.to_thread(mark_all_lanes)
        _last_mtm_timestamp = now
    except Exception as e:
        logger.error("Hourly MTM failed: %s", e, exc_info=True)


async def _daily_check():
    """Run daily rebalance check for all lanes."""
    import asyncio
    from backend.services.portfolio_intelligence.reference_engine import run_all_lanes

    logger.info("Running daily PI check at %s", datetime.now().isoformat())
    try:
        results = await asyncio.to_thread(run_all_lanes)
        for lane_id, snapshot in results.items():
            if snapshot.latest_rebalance:
                logger.info("Lane %s rebalanced: %s", lane_id, snapshot.latest_rebalance.trigger_reason)
            else:
                logger.info("Lane %s: no rebalance needed", lane_id)
    except Exception as e:
        logger.error("Daily PI check failed: %s", e, exc_info=True)


async def _weekly_aggressive_check():
    """Additional weekly check for aggressive lane."""
    import asyncio
    from backend.services.portfolio_intelligence.reference_engine import run_reference_check

    logger.info("Running weekly aggressive check at %s", datetime.now().isoformat())
    try:
        result = await asyncio.to_thread(run_reference_check, "aggressive")
        if result.latest_rebalance:
            logger.info("Aggressive lane rebalanced: %s", result.latest_rebalance.trigger_reason)
    except Exception as e:
        logger.error("Weekly aggressive check failed: %s", e, exc_info=True)


async def manual_trigger(lane_id: str | None = None) -> dict:
    """Manual trigger for testing or Railway cron fallback.

    Args:
        lane_id: Specific lane, or None for all lanes.

    Returns:
        Dict with results per lane.
    """
    import asyncio

    if lane_id:
        from backend.services.portfolio_intelligence.reference_engine import run_reference_check
        result = await asyncio.to_thread(run_reference_check, lane_id)
        return {lane_id: {
            "portfolio_id": result.portfolio_id,
            "date": result.date,
            "rebalanced": result.latest_rebalance is not None,
            "trigger_reason": result.latest_rebalance.trigger_reason if result.latest_rebalance else None,
        }}
    else:
        from backend.services.portfolio_intelligence.reference_engine import run_all_lanes
        results = await asyncio.to_thread(run_all_lanes)
        return {
            lane_id: {
                "portfolio_id": snapshot.portfolio_id,
                "date": snapshot.date,
                "rebalanced": snapshot.latest_rebalance is not None,
                "trigger_reason": snapshot.latest_rebalance.trigger_reason if snapshot.latest_rebalance else None,
            }
            for lane_id, snapshot in results.items()
        }
