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

from backend.config import DATA_DIR

logger = logging.getLogger(__name__)

_scheduler = None
_last_mtm_timestamp: datetime | None = None

# Env-configurable (AEGIS_DATA_DIR) so the job store persists on the same Railway
# volume as aegis_pi.db. See config.DATA_DIR for the volume-mount contract.
_DB_DIR = DATA_DIR


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


def _expected_nav_date(now_et: datetime | None = None) -> str:
    """Most recent trading day whose paper_nav row should exist by now.

    Today's row only becomes "due" after the close-of-day MTM window (post
    16:30 ET); before that, the freshest complete row is the prior session's.
    Weekends and NYSE holidays (config.US_MARKET_HOLIDAYS) are skipped.
    """
    from zoneinfo import ZoneInfo
    from backend.config import US_MARKET_HOLIDAYS

    if now_et is None:
        now_et = datetime.now(ZoneInfo("US/Eastern"))
    d = now_et.date()
    if now_et.hour < 17:
        d -= timedelta(days=1)
    while d.weekday() >= 5 or d.isoformat() in US_MARKET_HOLIDAYS:
        d -= timedelta(days=1)
    return d.isoformat()


def nav_freshness() -> dict:
    """Per-lane paper_nav freshness vs the expected last trading day.

    This is the check liveness can't do: last_mtm proves the job RAN, this
    proves rows LANDED. A lane is fresh iff MAX(date) >= expected trading day.
    """
    from backend.services.portfolio_intelligence.rules import (
        BOOK_LANES,
        CONSERVATIVE_ATR_LANES,
        REFERENCE_LANES,
    )
    try:
        from backend.db import get_connection

        expected = _expected_nav_date()
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT portfolio_id, MAX(date) AS last_date "
                "FROM paper_nav GROUP BY portfolio_id"
            ).fetchall()
            # Book lanes (P1 #6) count toward freshness ONLY once seeded — an
            # unseeded book lane has no paper_portfolios row and must not drag
            # all_fresh false before the attended seed runs.
            seeded = {r[0] for r in conn.execute(
                "SELECT id FROM paper_portfolios"
            ).fetchall()}
        finally:
            conn.close()
        # Book + conservative-ATR lanes count toward freshness ONLY once seeded —
        # an unseeded attended lane has no paper_portfolios row and must not drag
        # all_fresh false before its attended seed runs.
        _optional = (*BOOK_LANES, *CONSERVATIVE_ATR_LANES)
        lane_ids = (*REFERENCE_LANES, *[l for l in _optional if l in seeded])
        last_dates = {r["portfolio_id"]: r["last_date"] for r in rows}
        lanes = {
            lane_id: {
                "last_nav_date": last_dates.get(lane_id),
                "fresh": bool(last_dates.get(lane_id)
                              and last_dates[lane_id] >= expected),
            }
            for lane_id in lane_ids
        }
        return {
            "expected_nav_date": expected,
            "lanes": lanes,
            "all_fresh": all(v["fresh"] for v in lanes.values()),
        }
    except Exception as e:
        return {"error": str(e), "all_fresh": False}


def overlay_status() -> dict:
    """Per-lane crash-overlay operational status (the canary for a dark overlay).

    Reads the latest `crash_overlay_eval` audit row per lane. `operational`
    means the overlay actually evaluated (a model ran or an override was given);
    a lane that is `model_not_deployed`, errored, or never evaluated is NOT
    operational. `all_operational` is the one-glance canary — when false, the
    overlay engine is dark and lanes are running with no crash protection even
    though their mandate assumes one (the bug that hid for days under a
    swallowed per-cycle WARNING). `armed` reflects whether the overlay actually
    cut equity on the last evaluation (false in a calm tape is normal).
    """
    import json

    from backend.services.portfolio_intelligence.rules import REFERENCE_LANES

    out: dict = {"lanes": {}, "all_operational": True}
    try:
        from backend.db import get_connection

        conn = get_connection()
        try:
            for lane_id in REFERENCE_LANES:
                row = conn.execute(
                    "SELECT timestamp, payload FROM audit_log "
                    "WHERE portfolio_id = ? AND event_type = 'crash_overlay_eval' "
                    "ORDER BY id DESC LIMIT 1",
                    (lane_id,),
                ).fetchone()
                if row is None:
                    out["lanes"][lane_id] = {
                        "status": "never_evaluated", "operational": False,
                    }
                    out["all_operational"] = False
                    continue
                try:
                    p = json.loads(row["payload"])
                except Exception:
                    p = {}
                status = p.get("status", "unknown")
                operational = status in ("evaluated", "override")
                if not operational:
                    out["all_operational"] = False
                out["lanes"][lane_id] = {
                    "status": status,
                    "operational": operational,
                    "armed": p.get("armed"),
                    "crash_prob_3m": p.get("crash_prob_3m"),
                    "threshold": p.get("threshold"),
                    "last_evaluated": row["timestamp"],
                }
        finally:
            conn.close()
        return out
    except Exception as e:
        return {"error": str(e), "all_operational": False, "lanes": {}}


def lppls_status() -> dict:
    """LPPLS descriptive-fragility flag status (canary for a dark/stale flag).

    Reads the latest market-level `lppls_eval` audit row. `operational` means
    the flag actually evaluated last cycle (status == 'evaluated'); a missing
    model, data outage, or never-evaluated state is NOT operational. Mirrors
    overlay_status() so a dark fragility flag can't run unseen for days. This is
    DESCRIPTIVE only — it never arms a lane (see services/.../fragility.py).
    """
    import json

    from backend.services.portfolio_intelligence.fragility import LPPLS_LABEL, MARKET_ID

    try:
        from backend.db import get_connection

        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT timestamp, payload FROM audit_log "
                "WHERE portfolio_id = ? AND event_type = 'lppls_eval' "
                "ORDER BY id DESC LIMIT 1",
                (MARKET_ID,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return {"status": "never_evaluated", "operational": False,
                    "armed": False, "label": LPPLS_LABEL}
        try:
            p = json.loads(row["payload"])
        except Exception:
            p = {}
        status = p.get("status", "unknown")
        return {
            "status": status,
            "operational": status == "evaluated",
            "armed": False,  # HARD invariant: this flag never arms a lane
            "confidence": p.get("confidence"),
            "is_bubble": p.get("is_bubble"),
            "tc_date": p.get("tc_date"),
            "last_evaluated": row["timestamp"],
            "label": LPPLS_LABEL,
        }
    except Exception as e:
        return {"error": str(e), "operational": False, "armed": False}


def scheduler_health() -> dict:
    """Health snapshot for the /health/scheduler canary.

    A silently-dead scheduler means a flat-line track record (no MTM, no
    rebalances) — the #1 deploy risk. Exposes liveness (running flag, jobs,
    last MTM timestamp) AND freshness (per-lane paper_nav MAX(date) vs the
    expected last trading day) — a green liveness over zero persisted rows
    is exactly the failure this canary must catch.
    """
    if _scheduler is None:
        return {"running": False, "n_jobs": 0, "jobstore": None,
                "job_ids": [], "last_mtm": None,
                "nav": nav_freshness(),
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
            "nav": nav_freshness(),
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
    from backend.services.portfolio_intelligence.reference_engine import (
        mark_all_book_lanes,
        mark_all_lanes,
    )

    logger.info("Running hourly MTM at %s", now.isoformat())
    try:
        # Hourly job MARKS TO MARKET (persists daily NAV) — it does not rebalance.
        # Rebalance decisions happen in the daily check. Book lanes (P1 #6) mark
        # alongside the reference lanes; unseeded book lanes are skipped.
        results = await asyncio.to_thread(mark_all_lanes)
        book_results = await asyncio.to_thread(mark_all_book_lanes)
        results.update(book_results)
        # Conservative-ATR lane (TRIAL-EXIT) marks alongside; skipped until seeded.
        try:
            from backend.services.portfolio_intelligence.exit_lane import (
                mark_all_conservative_atr_lanes,
            )
            results.update(await asyncio.to_thread(mark_all_conservative_atr_lanes))
        except Exception as e:
            logger.error("Conservative-ATR MTM failed: %s", e, exc_info=True)
        if any(v is not None for v in results.values()):
            _last_mtm_timestamp = now
        else:
            # Stamping here would turn the canary green over zero persisted
            # rows — the silent-flat-line failure mode. Leave it stale so the
            # freshness check pages within one cycle.
            logger.error(
                "Hourly MTM: every lane failed to mark (%s) — last_mtm NOT stamped",
                results,
            )
    except Exception as e:
        logger.error("Hourly MTM failed: %s", e, exc_info=True)


async def _daily_check():
    """Run daily rebalance check for all lanes (reference + book)."""
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

    # Plan-3 (active mirror management): book lanes run on the SAME daily cadence.
    # Mirror checks its monthly/drift trigger; conviction applies any new logged
    # decisions. Both no-op (status=not_seeded) until AEGIS_SEED_BOOK_LANES seeds
    # them, so wiring this is safe pre-seed. Stamped with the BOOK config hash —
    # fully isolated from the 4 reference lanes' track record (separate
    # config_version → cannot perturb their NAV). Wrapped so a book-lane failure
    # never breaks the reference-lane check above.
    try:
        from backend.services.portfolio_intelligence.book_management import run_all_book_management
        book = await asyncio.to_thread(run_all_book_management)
        for lane_id, res in book.items():
            logger.info("Book lane %s: %s", lane_id, res.get("status"))
    except Exception as e:
        logger.error("Book-lane management failed: %s", e, exc_info=True)

    # TRIAL-EXIT (conservative-ATR): apply the ATR exit overlay + vol cap on the
    # mandate cadence. NO-OP (status=not_seeded) until AEGIS_SEED_CONSERVATIVE_ATR
    # seeds it, so wiring this pre-seed is safe. Stamped with the ISOLATED
    # conservative-ATR config hash — cannot perturb the reference lanes' NAV or
    # the frozen `conservative` control's segment. Wrapped so a failure here never
    # breaks the reference/book checks above.
    try:
        from backend.services.portfolio_intelligence.exit_lane import run_exit_overlay_check
        atr = await asyncio.to_thread(run_exit_overlay_check)
        logger.info("Conservative-ATR lane: status=%s reason=%s n_stopped=%s",
                    atr.get("status"), atr.get("reason"), atr.get("n_stopped"))
    except Exception as e:
        logger.error("Conservative-ATR exit-overlay check failed: %s", e, exc_info=True)

    # Descriptive LPPLS fragility flag (T1) — market-level, persisted each cycle
    # for the forward-Brier measurement. Descriptive only; never arms a lane.
    try:
        from backend.services.portfolio_intelligence.fragility import run_lppls_eval
        reading = await asyncio.to_thread(run_lppls_eval)
        logger.info("LPPLS fragility: status=%s confidence=%s (descriptive)",
                    reading.get("status"), reading.get("confidence"))
    except Exception as e:
        logger.error("LPPLS fragility eval failed: %s", e, exc_info=True)

    # Descriptive fragility COMPOSITE (TRIAL-CRASH) — persisted each cycle for
    # forward Brier. Descriptive only; never arms a lane.
    try:
        from backend.services.portfolio_intelligence.fragility import run_fragility_eval
        comp = await asyncio.to_thread(run_fragility_eval)
        logger.info("Fragility composite: status=%s score=%s n_inputs=%s (descriptive)",
                    comp.get("status"), comp.get("composite"), comp.get("n_inputs"))
    except Exception as e:
        logger.error("Fragility composite eval failed: %s", e, exc_info=True)

    # V4 alert engine — evaluates change rules against the fragility eval just
    # persisted (+ regime when cheaply available), 48h cooldown, log/Telegram
    # delivery. Risk-awareness framing only; the event-driven lane that would
    # ACT on alerts is a separate attended pre-registered seed.
    try:
        from backend.services.portfolio_intelligence.alert_engine import run_alert_check
        from backend.services.portfolio_intelligence.reference_engine import _get_regime
        regime = await asyncio.to_thread(_get_regime)  # cached market data → cheap
        al = await asyncio.to_thread(run_alert_check, regime)
        logger.info("Alert check: emitted=%d suppressed=%d readings=%s",
                    len(al.get("emitted", [])), al.get("suppressed_by_cooldown", 0),
                    al.get("readings"))
    except Exception as e:
        logger.error("Alert check failed: %s", e, exc_info=True)

    # TRIAL-INSIDER-IC (T9) — snapshot the opportunistic open-market buy score per
    # book name into the PIT store, starting the forward information-coefficient
    # clock. Internally throttled to ~weekly, so running it every daily check is
    # cheap. Descriptive only; never arms a lane. Wrapped so a SEC outage can't
    # break lane processing.
    try:
        from backend.services.portfolio_intelligence.insider_collector import (
            collect_insider_opp_scores,
        )
        ins = await asyncio.to_thread(collect_insider_opp_scores)
        logger.info("Insider-IC collect: status=%s n=%s nonzero=%s (descriptive)",
                    ins.get("status"), ins.get("n"), ins.get("nonzero"))
    except Exception as e:
        logger.error("Insider-IC collection failed: %s", e, exc_info=True)

    # TRIAL-REVISIONS-IC (T10) — snapshot the analyst revision-momentum score
    # (net Raises/Lowers + up/downgrades over 90d, NOT implied upside) per book
    # name. Weekly-throttled, descriptive, forward-only. Starts that IC clock.
    try:
        from backend.services.portfolio_intelligence.revisions_collector import (
            collect_revision_scores,
        )
        rev = await asyncio.to_thread(collect_revision_scores)
        logger.info("Revisions-IC collect: status=%s n=%s nonzero=%s (descriptive)",
                    rev.get("status"), rev.get("n"), rev.get("nonzero"))
    except Exception as e:
        logger.error("Revisions-IC collection failed: %s", e, exc_info=True)

    # TRIAL-PEAD-IC — snapshot the post-earnings-announcement-drift score
    # (analyst surprise + announcement-window excess return, two-way) per book
    # name. Weekly-throttled, descriptive, forward-only. Honest prior: decayed
    # anomaly, disputed net-of-cost in large caps (ENGINE_GAPS_2026_07_09).
    try:
        from backend.services.portfolio_intelligence.pead_collector import (
            collect_pead_scores,
        )
        pd_ = await asyncio.to_thread(collect_pead_scores)
        logger.info("PEAD-IC collect: status=%s n=%s nonzero=%s (descriptive)",
                    pd_.get("status"), pd_.get("n"), pd_.get("nonzero"))
    except Exception as e:
        logger.error("PEAD-IC collection failed: %s", e, exc_info=True)

    # TRIAL-QUALITY-IC — snapshot gross profitability (GP/A, Novy-Marx) per
    # book name via the hang-safe yfinance path (edgartools stays rejected).
    # Weekly-throttled, descriptive, forward-only. The T8 deferred quality slot.
    try:
        from backend.services.portfolio_intelligence.quality_collector import (
            collect_quality_scores,
        )
        q = await asyncio.to_thread(collect_quality_scores)
        logger.info("Quality-IC collect: status=%s n=%s nonzero=%s (descriptive)",
                    q.get("status"), q.get("n"), q.get("nonzero"))
    except Exception as e:
        logger.error("Quality-IC collection failed: %s", e, exc_info=True)

    # TRIAL-MULTIFACTOR-IC (T8) — combine momentum + insider + revisions into a
    # cross-sectional composite and snapshot it. Runs AFTER the two collectors
    # above so it reads their fresh PIT values. Descriptive, forward-only.
    try:
        from backend.services.portfolio_intelligence.multifactor import (
            collect_multifactor_scores,
        )
        mf = await asyncio.to_thread(collect_multifactor_scores)
        logger.info("Multifactor collect: status=%s n=%s (descriptive)",
                    mf.get("status"), mf.get("n"))
    except Exception as e:
        logger.error("Multifactor collection failed: %s", e, exc_info=True)

    # TRIAL-CONGRESS-IC — snapshot the congressional (STOCK Act) net
    # distinct-member purchase score over 90d of DISCLOSURES (FMP, both
    # chambers). Dynamic ~150-name universe (first non-book cross-section).
    # Weekly-throttled, descriptive, forward-only. A source failure raises
    # BEFORE any PIT write — no false-zero cross-sections.
    try:
        from backend.services.portfolio_intelligence.congress_collector import (
            collect_congress_scores,
        )
        cg = await asyncio.to_thread(collect_congress_scores)
        logger.info("Congress-IC collect: status=%s n=%s nonzero=%s (descriptive)",
                    cg.get("status"), cg.get("n"), cg.get("nonzero"))
    except Exception as e:
        logger.error("Congress-IC collection failed: %s", e, exc_info=True)

    # Fragility CANDIDATE inputs (Branch 1 item 3) — IPO issuance, mega-cap
    # concentration, crash-narrative. Snapshot-only (PIT store); weekly-throttled;
    # NEVER touches the composite (TRIAL-CRASH metric unchanged). Descriptive.
    try:
        from backend.services.portfolio_intelligence.fragility_candidates import (
            collect_fragility_candidates,
        )
        fc = await asyncio.to_thread(collect_fragility_candidates)
        logger.info("Fragility-candidate collect: status=%s n=%s nonzero=%s (descriptive)",
                    fc.get("status"), fc.get("n"), fc.get("nonzero"))
    except Exception as e:
        logger.error("Fragility-candidate collection failed: %s", e, exc_info=True)

    # TRIAL-ARK-IC — snapshot ARK's daily fund holdings (raw shares per fund,
    # as_of = the CSV's own file date); the 21-session flow score self-arms
    # once the baseline accrues. ALL-funds-failed raises loudly; a single
    # fund failing is isolated + logged. Descriptive, forward-only.
    try:
        from backend.services.portfolio_intelligence.ark_collector import (
            collect_ark_holdings,
        )
        ark = await asyncio.to_thread(collect_ark_holdings)
        logger.info("ARK collect: status=%s rows=%s score_status=%s (descriptive)",
                    ark.get("status"), ark.get("rows"), ark.get("score_status"))
    except Exception as e:
        logger.error("ARK collection failed: %s", e, exc_info=True)

    # 13F institutional-filing activity (V3 data layer, built 2026-06-14, wired
    # 2026-07-08). ~12 paced data.sec.gov calls via the shared EDGAR limiter;
    # snapshot() dedups unchanged filings so daily runs are cheap. Descriptive
    # positioning context on the legal ~45-day lag — never a timing signal.
    try:
        from backend.services.pit_collectors import collect_all_13f
        t13f = await asyncio.to_thread(collect_all_13f)
        logger.info("13F collect: recorded=%d unchanged=%d errors=%d (descriptive)",
                    len(t13f.get("recorded", [])), len(t13f.get("unchanged", [])),
                    len(t13f.get("errors", [])))
    except Exception as e:
        logger.error("13F collection failed: %s", e, exc_info=True)

    # TRIAL-SMARTGROWTH — weekly top-10 basket from the frozen blend of the
    # PIT signal streams. Runs LAST so it reads the values every collector
    # above just wrote. Descriptive, forward-only; renders as measured
    # candidates, never advice.
    try:
        from backend.services.portfolio_intelligence.smartgrowth import (
            collect_smartgrowth_picks,
        )
        sg = await asyncio.to_thread(collect_smartgrowth_picks)
        logger.info("Smartgrowth collect: status=%s n=%s (descriptive)",
                    sg.get("status"), sg.get("n"))
    except Exception as e:
        logger.error("Smartgrowth collection failed: %s", e, exc_info=True)


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
