"""
Portfolio Intelligence Router
================================

POST /api/pi/real-portfolio/analyze    — Full metric pack for user holdings
GET  /api/pi/reference/{lane_id}/state — Current allocation + metrics
GET  /api/pi/reference/{lane_id}/history?period= — Equity curve + rebalance log
GET  /api/pi/reference/{lane_id}/explain — Most recent rebalance explanation
GET  /api/pi/compare?ids=&period=      — All lanes + benchmarks side-by-side
POST /api/pi/trigger-check             — Manual rebalance check (Railway cron target)
GET  /api/pi/replay/{lane_id}          — Replay backtest results
"""

import asyncio
import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel as _BaseModel, Field as _PydField

from backend.schemas.portfolio_intelligence import (
    AnalyzePortfolioRequest,
    ComparisonResponse,
    ExplainResponse,
    HistoryEquityPoint,
    HistoryRebalanceEntry,
    HistoryResponse,
    MetricPack,
    ReplayResult,
    ReplaySnapshotResponse,
    SnapshotResponse,
    TrackRecordPoint,
    TrackRecordResponse,
)
from backend.services.portfolio_intelligence.real_analyzer import analyze_portfolio

router = APIRouter(prefix="/api/pi", tags=["portfolio-intelligence"])
logger = logging.getLogger(__name__)

from backend.services.portfolio_intelligence.rules import REFERENCE_LANES

_VALID_LANES = REFERENCE_LANES
_VALID_PERIODS = ("1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y", "ALL")


def _period_to_days(period: str) -> Optional[int]:
    """Convert period string to lookback days. Returns None for ALL."""
    period = period.upper()
    if period == "ALL":
        return None
    if period == "YTD":
        today = date.today()
        return (today - date(today.year, 1, 1)).days
    mapping = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365, "3Y": 1095, "5Y": 1825}
    return mapping.get(period, 365)


@router.post("/real-portfolio/analyze", response_model=SnapshotResponse)
async def analyze_real_portfolio(request: AnalyzePortfolioRequest):
    """Analyze a real portfolio: returns SnapshotResponse with MetricPack + risk flags."""
    try:
        result = await asyncio.to_thread(analyze_portfolio, request.holdings)
        return result
    except Exception as e:
        logger.error("Portfolio analysis failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get("/reference/{lane_id}/state", response_model=SnapshotResponse)
async def get_reference_state(lane_id: str):
    """Get current state of a reference portfolio lane."""
    if lane_id not in _VALID_LANES:
        raise HTTPException(status_code=404, detail=f"Unknown lane: {lane_id}")

    from backend.services.portfolio_intelligence.reference_engine import run_reference_check

    try:
        result = await asyncio.to_thread(run_reference_check, lane_id)
        return result
    except Exception as e:
        logger.error("Reference state failed for %s: %s", lane_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reference/{lane_id}/history", response_model=HistoryResponse)
async def get_reference_history(
    lane_id: str,
    period: str = Query(default="1Y", pattern="^(1M|3M|6M|YTD|1Y|3Y|5Y|ALL)$"),
):
    """Live forward equity curve + rebalance log for a reference lane.

    The equity curve is the real mark-to-market NAV series from paper_nav
    (persisted by the hourly MTM job), with per-point config_version so
    versioned rule changes render as clean track-record segment boundaries.
    An empty curve ships with has_nav_data=false — "no data" is structurally
    distinct from a flat line of real NAV.
    """
    if lane_id not in _VALID_LANES:
        raise HTTPException(status_code=404, detail=f"Unknown lane: {lane_id}")

    from backend.db import get_connection, get_nav_series
    from backend.services.portfolio_intelligence.reference_engine import (
        _ensure_lane_initialized,
    )

    try:
        # Make sure parent row exists; otherwise queries return zero events for
        # a different reason than the user expects.
        await asyncio.to_thread(_ensure_lane_initialized, lane_id)

        cutoff_days = _period_to_days(period)
        cutoff_iso: Optional[str] = None
        if cutoff_days is not None:
            cutoff_iso = (datetime.now() - timedelta(days=cutoff_days)).isoformat()

        conn = get_connection()
        try:
            if cutoff_iso:
                rows = conn.execute(
                    "SELECT triggered_at, trigger_reason, crash_prob_3m, explanation, post_weights "
                    "FROM rebalance_events WHERE portfolio_id = ? AND triggered_at >= ? "
                    "ORDER BY id ASC",
                    (lane_id, cutoff_iso),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT triggered_at, trigger_reason, crash_prob_3m, explanation, post_weights "
                    "FROM rebalance_events WHERE portfolio_id = ? "
                    "ORDER BY id ASC",
                    (lane_id,),
                ).fetchall()

            inception = conn.execute(
                "SELECT inception_date, inception_value FROM paper_portfolios WHERE id = ?",
                (lane_id,),
            ).fetchone()
            nav_rows = get_nav_series(conn, lane_id)
        finally:
            conn.close()

        rebalance_log: list[HistoryRebalanceEntry] = []
        for row in rows:
            reason = row["trigger_reason"]
            rebalance_log.append(HistoryRebalanceEntry(
                date=row["triggered_at"][:10],
                reason=reason,
                crash_prob=row["crash_prob_3m"],
                overlay_armed=(reason == "crash_overlay"),
                explanation=row["explanation"],
            ))

        cutoff_date = cutoff_iso[:10] if cutoff_iso else None
        equity_curve = [
            HistoryEquityPoint(
                date=r["date"],
                value=r["nav"],
                config_version=r["config_version"],
            )
            for r in nav_rows
            if cutoff_date is None or r["date"] >= cutoff_date
        ]

        return HistoryResponse(
            portfolio_id=lane_id,
            period=period.upper(),
            equity_curve=equity_curve,
            rebalance_log=rebalance_log,
            has_rebalance_events=len(rebalance_log) > 0,
            has_nav_data=len(equity_curve) > 0,
            inception_date=inception["inception_date"] if inception else None,
            inception_value=inception["inception_value"] if inception else None,
        )
    except Exception as e:
        logger.error("History fetch failed for %s: %s", lane_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _benchmark_track(inception: str, notional: float = 100_000.0) -> dict:
    """SPY / AGG / 60-40 overlays normalized to the lanes' inception notional.

    60/40 is a daily-rebalanced blend of SPY/AGG daily returns. Cached 30min —
    benchmark closes only change once per trading day.
    """
    from backend.cache import cache_get, cache_set

    cache_key = f"pi:track-record:benchmarks:{inception}"
    hit = cache_get(cache_key, 1800)
    if hit is not None:
        return hit

    import pandas as pd
    from backend.services.data_fetcher import fetch_safe

    start = (date.fromisoformat(inception) - timedelta(days=10)).isoformat()
    end = (date.today() + timedelta(days=1)).isoformat()
    spy = fetch_safe("SPY", start, end, name="SPY")
    agg = fetch_safe("AGG", start, end, name="AGG")
    if spy is None or agg is None or len(spy) == 0 or len(agg) == 0:
        logger.warning("track-record: benchmark fetch failed (SPY=%s, AGG=%s)",
                       spy is not None, agg is not None)
        return {}

    df = pd.DataFrame({"SPY": spy, "AGG": agg}).dropna()
    df = df[df.index >= pd.Timestamp(inception)]
    if df.empty:
        return {}

    norm = df / df.iloc[0] * notional
    rets = df.pct_change().fillna(0.0)
    blend = (1 + 0.6 * rets["SPY"] + 0.4 * rets["AGG"]).cumprod() * notional

    def _points(series) -> list[TrackRecordPoint]:
        return [
            TrackRecordPoint(date=str(idx)[:10], value=round(float(v), 2))
            for idx, v in series.items()
        ]

    out = {"SPY": _points(norm["SPY"]), "AGG": _points(norm["AGG"]),
           "60_40": _points(blend)}
    cache_set(cache_key, out)
    return out


@router.get("/registry")
async def get_experiment_registry(limit: int = Query(default=100, le=500)):
    """Read-only view of the experiment registry (rule_experiments).

    The registry LIVES in Aegis (guardrail: Optimus reads it, never owns it).
    This is the endpoint Optimus MCP and auditors consume: every trial ever
    recorded — adopted AND rejected — with the cumulative count the DSR/PBO
    guards deflate against, and pre-registered decision rules in notes.
    """
    import json as _json

    from backend.db import count_cumulative_trials, get_connection
    from backend.services.portfolio_intelligence.experiment_registry import (
        effective_independent_trials,
    )

    def _read():
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT id, created_at, config_version, lane_id, param, "
                "       old_value, new_value, observed_sharpe, n_obs, "
                "       batch_trials, cumulative_trials, dsr, pbo, "
                "       effective_trials, verdict, notes "
                "FROM rule_experiments ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            total = count_cumulative_trials(conn)
        finally:
            conn.close()
        trials = []
        for r in rows:
            d = dict(r)
            try:
                d["notes"] = _json.loads(d["notes"]) if d["notes"] else None
            except Exception:
                pass  # keep raw string notes
            trials.append(d)
        verdicts = {}
        for t in trials:
            verdicts[t["verdict"]] = verdicts.get(t["verdict"], 0) + 1
        return {
            # The GATE count: every trial ever recorded (lanes + rule tweaks).
            # The DSR/PBO guards deflate against THIS — a strictness floor.
            "cumulative_trials": total,
            # REPORTED, NOT gating: the participation-ratio estimate of how many
            # *independent* lanes the correlated return streams really represent.
            # Surfaced for audit; never loosens the adoption bar. See
            # experiment_registry.effective_independent_trials.
            "effective_independent_trials": effective_independent_trials(),
            "verdict_counts": verdicts,
            "trials": trials,
        }

    try:
        return await asyncio.to_thread(_read)
    except Exception as e:
        logger.error("Registry read failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fragility")
async def get_fragility():
    """Descriptive LPPLS bubble-structure flag + its forward-Brier measurement.

    READ-ONLY and DESCRIPTIVE. The LPPLS predictive skill for crash timing was
    adversarially refuted twice (see DEEP_RESEARCH_2026-06-14_DECISION.md §1.1);
    this surface ships the flag as a *bubble-structure* reading only — it never
    arms a lane, never sizes a position, and emits no buy/sell language. Its
    skill is measured FORWARD against climatology (TRIAL-LPPLS); until enough
    matured observations exist the Brier reports `insufficient_forward_data`.
    """
    def _read():
        from backend.services.portfolio_intelligence.fragility import (
            CRASH_DECISION_RULE, LPPLS_DECISION_RULE,
            compute_fragility_index, forward_brier_status,
            forward_brier_status_composite,
        )
        from backend.services.portfolio_intelligence.scheduler import lppls_status
        from backend.services.portfolio_intelligence.fragility_candidates import (
            latest_candidate_readings,
        )
        return {
            "latest_reading": lppls_status(),
            "forward_brier": forward_brier_status(),
            "trial": LPPLS_DECISION_RULE,
            # Descriptive structural-fragility composite (TRIAL-CRASH).
            "composite": compute_fragility_index(),
            "composite_forward_brier": forward_brier_status_composite(),
            "composite_trial": CRASH_DECISION_RULE,
            # Candidate inputs collected forward (PIT) — NOT in the composite.
            "candidate_readings": latest_candidate_readings(),
            "disclaimer": (
                "Descriptive bubble-structure flag + structural-fragility composite, "
                "NOT a crash forecast or timing call. LPPLS predictive skill was "
                "refuted; neither this flag nor the composite arms a lane, sizes a "
                "position, or implies a crash is imminent. No skill claim until a "
                "pre-registered forward Brier beats climatology."
            ),
        }

    try:
        return await asyncio.to_thread(_read)
    except Exception as e:
        logger.error("Fragility read failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── Conviction lane: decision capture (P1 #6 groundwork) ──────────────────────
# Writes to the immutable `personal_decisions` LOG (separate from paper_nav — NOT
# the track-record write path). Decisions are forward-only: timestamp is always
# server-now (never backdated); a past action is flagged late_entry; corrections
# append via amends_id (the table's triggers forbid update/delete). The conviction
# *lane* (positions driven by these decisions) is the attended seeding session.

class ConvictionDecisionRequest(_BaseModel):
    ticker: str
    action: str                      # enter | add | trim | exit
    shares_delta: float
    price: float
    rationale: str                   # >= 50 chars (honest-record discipline)
    conviction: int                  # 1-5
    thesis_tags: list[str] = _PydField(default_factory=list)
    target_price: Optional[float] = None
    stop_price: Optional[float] = None
    planned_exit_trigger: Optional[str] = None
    catalyst_dates: list[str] = _PydField(default_factory=list)
    amends_id: Optional[int] = None  # correction → appends a new row referencing the original
    late_entry: bool = False         # the action already happened; logged after the fact
    portfolio_snapshot: dict = _PydField(default_factory=dict)


@router.post("/conviction/decision")
async def log_conviction_decision(body: ConvictionDecisionRequest):
    """Log a conviction-lane decision (immutable, forward-only). Returns the row id."""
    def _write():
        from backend.db import get_connection, init_db, insert_personal_decision
        init_db()
        conn = get_connection()
        try:
            ts = datetime.now().isoformat()  # server-now; never client-supplied/backdated
            rid = insert_personal_decision(
                conn, timestamp=ts, ticker=body.ticker.upper().strip(),
                action=body.action, shares_delta=body.shares_delta, price=body.price,
                rationale=body.rationale, thesis_tags=body.thesis_tags,
                conviction=body.conviction, portfolio_snapshot=body.portfolio_snapshot,
                target_price=body.target_price, stop_price=body.stop_price,
                planned_exit_trigger=body.planned_exit_trigger,
                catalyst_dates=body.catalyst_dates, amends_id=body.amends_id,
                late_entry=body.late_entry,
            )
            return {"id": rid, "timestamp": ts, "late_entry": body.late_entry}
        finally:
            conn.close()

    try:
        return await asyncio.to_thread(_write)
    except ValueError as e:  # rationale<50 / conviction range / bad action
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Conviction decision write failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/risk-watch")
async def get_risk_watch():
    """One fast read for the Risk Watch surface: the last PERSISTED fragility
    reading (never recomputes), the candidate readings (PIT), and recent
    alerts. All descriptive — risk-awareness, never orders."""
    def _read():
        from backend.services.portfolio_intelligence.alert_engine import recent_alerts
        from backend.services.portfolio_intelligence.fragility import (
            latest_persisted_composite,
        )
        from backend.services.portfolio_intelligence.fragility_candidates import (
            latest_candidate_readings,
        )
        return {
            "fragility": latest_persisted_composite(),
            "candidate_readings": latest_candidate_readings(),
            "alerts": recent_alerts(limit=30),
            "disclaimer": ("Descriptive risk-awareness context — measures "
                           "fragility, never predicts crashes, never orders."),
        }

    try:
        return await asyncio.to_thread(_read)
    except Exception as e:
        logger.error("Risk-watch read failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts")
async def get_alerts(limit: int = Query(default=50, le=200)):
    """Recent engine alerts (newest first). Risk-awareness context, never orders."""
    def _read():
        from backend.services.portfolio_intelligence.alert_engine import recent_alerts
        return {"alerts": recent_alerts(limit=limit),
                "disclaimer": "Risk-awareness context, not advice or orders."}

    try:
        return await asyncio.to_thread(_read)
    except Exception as e:
        logger.error("Alert read failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conviction/calibration")
async def get_conviction_calibration():
    """Reliability curve of logged conviction decisions (matured horizons only).
    Descriptive process-memory — never a training signal."""
    def _read():
        from backend.services.portfolio_intelligence.conviction_calibration import (
            calibration_scorecard,
        )
        return calibration_scorecard()

    try:
        return await asyncio.to_thread(_read)
    except Exception as e:
        logger.error("Conviction calibration failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conviction/decisions")
async def get_conviction_decisions(limit: int = Query(default=100, le=500)):
    """Read the conviction decision log (newest first). Read-only."""
    def _read():
        from backend.db import get_connection, init_db, list_personal_decisions
        init_db()
        conn = get_connection()
        try:
            return {"decisions": list_personal_decisions(conn, limit=limit)}
        finally:
            conn.close()

    try:
        return await asyncio.to_thread(_read)
    except Exception as e:
        logger.error("Conviction decisions read failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/track-record", response_model=TrackRecordResponse)
async def get_track_record():
    """The canonical live forward track record (see TRACK_RECORD_POLICY.md).

    Real paper_nav rows for all three lanes (per-point config_version for
    segment boundaries) + SPY/AGG/60-40 overlays normalized at inception.
    Read-only. intraday_date flags a latest row that still re-marks hourly.
    """
    from zoneinfo import ZoneInfo

    from backend.db import get_connection, get_nav_series
    from backend.services.portfolio_intelligence.rules import (
        BOOK_LANES,
        CONSERVATIVE_ATR_LANES,
    )
    from backend.services.portfolio_intelligence.scheduler import nav_freshness

    def _build() -> TrackRecordResponse:
        conn = get_connection()
        try:
            lanes: dict[str, list[TrackRecordPoint]] = {}
            # Reference lanes (always seeded) + book lanes (mirror/conviction) once
            # seeded. A book lane with no NAV rows yet (unseeded) is simply skipped.
            # Surfacing book lanes here is safe: reading their NAV series never
            # touches the reference lanes' config hash (TRIAL-001 isolation is a
            # write-path concern, not a read one). Without this they were marked-to-
            # market and fresh yet INVISIBLE on the canonical track record.
            _optional = (*BOOK_LANES, *CONSERVATIVE_ATR_LANES)
            for lane_id in (*REFERENCE_LANES, *_optional):
                rows = get_nav_series(conn, lane_id)
                if not rows and lane_id in _optional:
                    continue  # unseeded attended lane — not on the record yet
                lanes[lane_id] = [
                    TrackRecordPoint(
                        date=r["date"], value=round(r["nav"], 2),
                        config_version=r["config_version"],
                    )
                    for r in rows
                ]
            # Canonical inception/benchmark anchor = the REFERENCE lanes' earliest.
            # Book lanes legitimately start later (seeded at their own inception);
            # they should not pull the benchmark normalization date earlier.
            _ph = ",".join("?" for _ in REFERENCE_LANES)
            inc = conn.execute(
                "SELECT MIN(inception_date) AS d FROM paper_portfolios "
                f"WHERE id IN ({_ph})", REFERENCE_LANES,
            ).fetchone()
        finally:
            conn.close()

        inception = inc["d"] if inc and inc["d"] else None
        fresh = nav_freshness()

        now_et = datetime.now(ZoneInfo("US/Eastern"))
        today_et = now_et.date().isoformat()
        latest = max((p[-1].date for p in lanes.values() if p), default=None)
        intraday = today_et if (latest == today_et and now_et.hour < 17) else None

        return TrackRecordResponse(
            inception_date=inception,
            age_days=(date.today() - date.fromisoformat(inception)).days
            if inception else None,
            expected_nav_date=fresh.get("expected_nav_date"),
            all_fresh=bool(fresh.get("all_fresh")),
            intraday_date=intraday,
            lanes=lanes,
            benchmarks=_benchmark_track(inception) if inception else {},
        )

    try:
        return await asyncio.to_thread(_build)
    except Exception as e:
        logger.error("track-record failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _record_lanes() -> tuple:
    """Every lane that can appear on the track record (reference + seeded
    book + ATR overlay). Import stays local — rules pulls YAML at import."""
    from backend.services.portfolio_intelligence.rules import (
        BOOK_LANES,
        CONSERVATIVE_ATR_LANES,
    )
    return (*REFERENCE_LANES, *BOOK_LANES, *CONSERVATIVE_ATR_LANES)


@router.get("/lane/{lane_id}/stats-ci")
async def get_lane_stats_ci(lane_id: str):
    """Sharpe / Sortino / max drawdown for a lane's forward paper record,
    each with a 95% bootstrap CI (BCa; block bootstrap for drawdown).

    The honest headline: "Sharpe 1.1 [95% CI: −0.2, 2.4]" — at 6 weeks of
    history the intervals are wide, and that is the point. Read-only.
    """
    if lane_id not in _record_lanes():
        raise HTTPException(status_code=404, detail=f"Unknown lane: {lane_id}")

    from backend.cache import cache_get, cache_set
    from backend.services.portfolio_intelligence.tearsheet import (
        lane_stats_with_cis,
    )

    cache_key = f"pi:stats-ci:{lane_id}"
    cached = cache_get(cache_key, 3600)
    if cached is not None:
        return cached
    try:
        result = await asyncio.to_thread(lane_stats_with_cis, lane_id)
    except Exception as e:
        logger.error("stats-ci failed for %s: %s", lane_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    cache_set(cache_key, result)
    return result


@router.get("/lane/{lane_id}/tearsheet")
async def get_lane_tearsheet(lane_id: str):
    """Full quantstats HTML tearsheet rendered from the lane's REAL paper_nav
    rows (quantstats as renderer only — no quantstats network utilities).
    Served as text/html; generated on demand and cached for 6h."""
    from fastapi.responses import HTMLResponse

    if lane_id not in _record_lanes():
        raise HTTPException(status_code=404, detail=f"Unknown lane: {lane_id}")

    from backend.cache import cache_get, cache_set
    from backend.services.portfolio_intelligence.tearsheet import (
        lane_tearsheet_html,
    )

    cache_key = f"pi:tearsheet:{lane_id}"
    cached = cache_get(cache_key, 6 * 3600)
    if cached is not None:
        return HTMLResponse(content=cached)
    try:
        html = await asyncio.to_thread(lane_tearsheet_html, lane_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("tearsheet failed for %s: %s", lane_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    cache_set(cache_key, html)
    return HTMLResponse(content=html)


@router.get("/reference/{lane_id}/explain", response_model=ExplainResponse)
async def get_reference_explain(lane_id: str):
    """Most recent rebalance explanation. Shape consistent whether events exist or not."""
    if lane_id not in _VALID_LANES:
        raise HTTPException(status_code=404, detail=f"Unknown lane: {lane_id}")

    from backend.db import get_connection
    from backend.services.portfolio_intelligence.reference_engine import (
        _ensure_lane_initialized,
    )

    try:
        await asyncio.to_thread(_ensure_lane_initialized, lane_id)

        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT explanation, trigger_reason, triggered_at FROM rebalance_events "
                "WHERE portfolio_id = ? ORDER BY id DESC LIMIT 1",
                (lane_id,),
            ).fetchone()
        finally:
            conn.close()

        if not row:
            return ExplainResponse(
                portfolio_id=lane_id,
                explanation=f"No rebalance events yet for {lane_id}.",
                last_rebalance_date=None,
                has_rebalance_events=False,
            )

        return ExplainResponse(
            portfolio_id=lane_id,
            explanation=row["explanation"],
            last_rebalance_date=row["triggered_at"][:10] if row["triggered_at"] else None,
            has_rebalance_events=True,
        )
    except Exception as e:
        logger.error("Explain fetch failed for %s: %s", lane_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


_COMPARE_CACHE_TTL = 600  # 10 min — replays don't change intra-session
_REPLAY_CACHE_TTL = 1800  # 30 min — backtest is deterministic per (lane, dates)
_LANE_FAST_CACHE_TTL = 600  # 10 min — fast static-weight lane metrics

# Static target allocations (from data/paper_portfolios.yaml). Compare uses these
# for a fast buy-and-hold equivalent (no walk-forward, no rebalance) so the page
# loads in seconds rather than the 5+ min the full replay needs. The dedicated
# /replay/{lane_id} page still runs the real walk-forward backtest.
_LANE_ALLOCATIONS: dict[str, dict[str, float]] = {
    "conservative": {"SPY": 0.40, "AGG": 0.50, "GLD": 0.10},
    "balanced":     {"SPY": 0.70, "AGG": 0.25, "GLD": 0.05},
    "aggressive":   {"SPY": 0.95, "AGG": 0.05},
}


def _cached_replay(lane_id: str, start_iso: str, end_iso: str) -> ReplayResult:
    """Run replay with persistent SQLite cache.

    Cache key: (lane_id, universe_hash, rules_hash, market_data_date=today).
    Hashes auto-invalidate when paper_portfolios.yaml changes; the date
    component gives natural daily rollover (24h TTL).
    """
    from backend.db import (
        compute_rules_hash,
        compute_universe_hash,
        get_cached_replay,
        save_cached_replay,
    )
    from backend.services.portfolio_intelligence.replay import ReplayEngine

    universe_hash = compute_universe_hash()
    rules_hash = compute_rules_hash(lane_id)
    today = date.today().isoformat()

    cached_json = get_cached_replay(lane_id, universe_hash, rules_hash, today)
    if cached_json:
        return ReplayResult.model_validate(json.loads(cached_json))

    # Cash sleeve earns the live short rate (FRED DGS3MO) — don't leave rf at 0.
    from backend.services.portfolio_intelligence.nav import get_rf_daily
    result = ReplayEngine().run(lane_id, start_iso, end_iso, rf_daily=get_rf_daily())
    save_cached_replay(
        lane_id, universe_hash, rules_hash, today,
        result.model_dump_json(),
    )
    return result


def _compute_lane_metrics_fast(lane_id: str, start_d: date, end_d: date) -> Optional[MetricPack]:
    """Buy-and-hold MetricPack for a lane using its target allocation on representative ETFs.

    This is the FAST path used by /compare (sub-second). The dedicated /replay
    endpoint still runs the full walk-forward with rebalances + crash overlay.
    """
    import numpy as np
    import pandas as pd
    from backend.cache import cache_get, cache_set
    from backend.services.data_fetcher import fetch_safe

    weights = _LANE_ALLOCATIONS.get(lane_id)
    if not weights:
        return None

    start_s = start_d.isoformat()
    end_s = end_d.isoformat()
    cache_key = f"pi_lane_fast:{lane_id}:{start_s}:{end_s}"
    cached = cache_get(cache_key, _LANE_FAST_CACHE_TTL)
    if cached is not None:
        return cached

    series_map: dict[str, pd.Series] = {}
    for tkr in weights:
        s = fetch_safe(tkr, start_s, end_s, name=tkr)
        if s is None or len(s) < 20:
            return None
        series_map[tkr] = s

    df = pd.DataFrame(series_map).dropna()
    if len(df) < 20:
        return None
    rets = df.pct_change().dropna()
    if rets.empty:
        return None

    port_rets = sum(rets[tkr] * w for tkr, w in weights.items())

    total_return = float((1 + port_rets).prod() - 1)
    n_years = len(port_rets) / 252.0
    ann_return = float((1 + total_return) ** (1 / n_years) - 1) if n_years > 0 else 0.0
    ann_vol = float(port_rets.std() * np.sqrt(252))
    sharpe = float((ann_return - 0.04) / ann_vol) if ann_vol > 1e-10 else None

    cum = (1 + port_rets).cumprod()
    peak = cum.cummax()
    max_dd = float((cum / peak - 1).min())

    pack = MetricPack(
        total_return=round(total_return, 6),
        annualized_return=round(ann_return, 6),
        annualized_volatility=round(ann_vol, 6),
        sharpe_ratio=round(sharpe, 4) if sharpe is not None else None,
        max_drawdown=round(max_dd, 6),
    )
    cache_set(cache_key, pack)
    return pack


@router.get("/compare", response_model=ComparisonResponse)
async def compare_lanes(
    ids: str = Query(default="conservative,balanced,aggressive"),
    period: str = Query(default="1Y", pattern="^(1M|3M|6M|YTD|1Y|3Y|5Y|ALL)$"),
):
    """Side-by-side comparison of lanes + standard benchmarks.

    Lane MetricPacks come from the replay endpoint (backtested numbers).
    Benchmark MetricPacks (SPY, AGG, 60-40) are computed inline from price data
    over the same period for honest comparison.

    Performance: cached 10 min; lane replays + benchmarks run in parallel.
    """
    from backend.cache import cache_get, cache_set

    requested_ids = [s.strip() for s in ids.split(",") if s.strip()]
    lane_ids = [i for i in requested_ids if i in _VALID_LANES]
    if not lane_ids:
        lane_ids = list(_VALID_LANES)

    period_u = period.upper()
    cache_key = f"pi_compare:{','.join(sorted(lane_ids))}:{period_u}"
    cached = cache_get(cache_key, _COMPARE_CACHE_TTL)
    if cached is not None:
        return cached

    cutoff_days = _period_to_days(period_u)
    end_d = date.today()
    if cutoff_days is None:
        start_d = date(2021, 1, 4)
    else:
        start_d = end_d - timedelta(days=cutoff_days)

    # Fast static-weight buy-and-hold per lane (no walk-forward) + benchmarks,
    # all concurrent. /replay/{lane_id} still has the full walk-forward.
    lane_tasks = [
        asyncio.create_task(asyncio.to_thread(
            _compute_lane_metrics_fast, lid, start_d, end_d,
        ))
        for lid in lane_ids
    ]
    bench_names = ("SPY", "AGG", "60-40")
    bench_tasks = [
        asyncio.create_task(asyncio.to_thread(
            _compute_benchmark_metrics, b, start_d, end_d,
        ))
        for b in bench_names
    ]

    lane_results = await asyncio.gather(*lane_tasks, return_exceptions=True)
    bench_results = await asyncio.gather(*bench_tasks, return_exceptions=True)

    lanes_metrics: dict[str, Optional[MetricPack]] = {}
    for lid, res in zip(lane_ids, lane_results):
        if isinstance(res, Exception):
            logger.warning("Compare: lane %s failed: %s", lid, res)
            lanes_metrics[lid] = None
        else:
            lanes_metrics[lid] = res

    benchmarks_metrics: dict[str, Optional[MetricPack]] = {}
    for bname, res in zip(bench_names, bench_results):
        if isinstance(res, Exception):
            logger.warning("Compare: benchmark %s failed: %s", bname, res)
            benchmarks_metrics[bname] = None
        else:
            benchmarks_metrics[bname] = res

    response = ComparisonResponse(
        lanes=lanes_metrics,
        benchmarks=benchmarks_metrics,
        period=period_u,
        start_date=start_d.isoformat(),
        end_date=end_d.isoformat(),
    )
    cache_set(cache_key, response)
    return response


def _compute_benchmark_metrics(name: str, start_d: date, end_d: date) -> Optional[MetricPack]:
    """Compute a MetricPack for a single benchmark by name."""
    import numpy as np
    import pandas as pd
    from backend.services.data_fetcher import fetch_safe

    start_s = start_d.isoformat()
    end_s = end_d.isoformat()

    if name in ("SPY", "AGG"):
        series = fetch_safe(name, start_s, end_s, name=name)
        if series is None or len(series) < 20:
            return None
        returns = series.pct_change().dropna()
    elif name == "60-40":
        spy = fetch_safe("SPY", start_s, end_s, name="SPY")
        agg = fetch_safe("AGG", start_s, end_s, name="AGG")
        if spy is None or agg is None or len(spy) < 20 or len(agg) < 20:
            return None
        df = pd.DataFrame({"SPY": spy, "AGG": agg}).dropna()
        rets = df.pct_change().dropna()
        returns = rets["SPY"] * 0.6 + rets["AGG"] * 0.4
    else:
        return None

    if returns.empty:
        return None

    total_return = float((1 + returns).prod() - 1)
    n_years = len(returns) / 252.0
    ann_return = float((1 + total_return) ** (1 / n_years) - 1) if n_years > 0 else 0.0
    ann_vol = float(returns.std() * np.sqrt(252))
    sharpe = float((ann_return - 0.04) / ann_vol) if ann_vol > 1e-10 else None

    cum = (1 + returns).cumprod()
    peak = cum.cummax()
    max_dd = float((cum / peak - 1).min())

    return MetricPack(
        total_return=round(total_return, 6),
        annualized_return=round(ann_return, 6),
        annualized_volatility=round(ann_vol, 6),
        sharpe_ratio=round(sharpe, 4) if sharpe is not None else None,
        max_drawdown=round(max_dd, 6),
    )


@router.post("/trigger-check")
async def trigger_check(lane_id: Optional[str] = None):
    """Manual rebalance check — Railway cron target.

    POST /api/pi/trigger-check          — check all lanes
    POST /api/pi/trigger-check?lane_id=conservative — check one lane
    """
    from backend.services.portfolio_intelligence.scheduler import manual_trigger

    try:
        result = await manual_trigger(lane_id)
        return result
    except Exception as e:
        logger.error("Trigger check failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/replay/{lane_id}", response_model=ReplayResult)
async def get_replay(
    lane_id: str,
    start_date: str = Query(default="2021-01-01"),
    end_date: Optional[str] = Query(default=None),
):
    """Run walk-forward replay backtest for a reference lane.

    WARNING: This is computationally expensive (fetches years of data).
    Result is persisted to SQLite for 24h. Prefer /reference/{lane}/snapshot
    for fast reads — this endpoint forces a recompute on cache miss.
    """
    if lane_id not in _VALID_LANES:
        raise HTTPException(status_code=404, detail=f"Unknown lane: {lane_id}")

    end_iso = end_date or date.today().isoformat()

    try:
        result = await asyncio.to_thread(
            _cached_replay, lane_id, start_date, end_iso,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Replay failed for %s: %s", lane_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reference/{lane_id}/snapshot", response_model=ReplaySnapshotResponse)
async def get_replay_snapshot(lane_id: str):
    """Fast read of the cached walk-forward replay (<100ms when warm).

    Never triggers a recompute. Returns:
      - status="cached", fresh=True   → today's result
      - status="stale", fresh=False   → previous result (frontend should offer refresh)
      - status="missing", result=None → never computed (frontend prompts refresh)
    """
    if lane_id not in _VALID_LANES:
        raise HTTPException(status_code=404, detail=f"Unknown lane: {lane_id}")

    from backend.db import (
        compute_rules_hash,
        compute_universe_hash,
        get_cached_replay,
        get_latest_cached_replay,
    )

    try:
        universe_hash = compute_universe_hash()
        rules_hash = compute_rules_hash(lane_id)
        today = date.today().isoformat()

        fresh_json = await asyncio.to_thread(
            get_cached_replay, lane_id, universe_hash, rules_hash, today,
        )
        if fresh_json:
            return ReplaySnapshotResponse(
                lane_id=lane_id,
                status="cached",
                cached_at=today,
                fresh=True,
                result=ReplayResult.model_validate(json.loads(fresh_json)),
            )

        latest = await asyncio.to_thread(get_latest_cached_replay, lane_id)
        if latest:
            stale_json, computed_at = latest
            return ReplaySnapshotResponse(
                lane_id=lane_id,
                status="stale",
                cached_at=computed_at,
                fresh=False,
                result=ReplayResult.model_validate(json.loads(stale_json)),
            )

        return ReplaySnapshotResponse(
            lane_id=lane_id,
            status="missing",
            cached_at=None,
            fresh=False,
            result=None,
        )
    except Exception as e:
        logger.error("Snapshot read failed for %s: %s", lane_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/replay/{lane_id}/refresh", response_model=ReplayResult)
async def refresh_replay(
    lane_id: str,
    start_date: str = Query(default="2021-01-01"),
    end_date: Optional[str] = Query(default=None),
):
    """Invalidate cache and recompute the walk-forward replay.

    Slow (10+ minutes) — frontend should show a progress indicator.
    """
    if lane_id not in _VALID_LANES:
        raise HTTPException(status_code=404, detail=f"Unknown lane: {lane_id}")

    from backend.db import invalidate_replay_cache

    end_iso = end_date or date.today().isoformat()

    try:
        await asyncio.to_thread(invalidate_replay_cache, lane_id)
        result = await asyncio.to_thread(
            _cached_replay, lane_id, start_date, end_iso,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Refresh failed for %s: %s", lane_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
