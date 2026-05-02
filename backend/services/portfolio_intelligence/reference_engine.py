"""
Aegis Finance — Reference Engine
===================================

Orchestrates rules + rebalancer + audit for reference portfolio lanes.
This is the top-level entry point for running rebalance checks.

Usage:
    from backend.services.portfolio_intelligence.reference_engine import (
        run_reference_check, run_all_lanes, initialize_lane,
    )
"""

import json
import logging
from datetime import date, datetime

from backend.config import paper_portfolios
from backend.db import get_connection, insert_rebalance_event, insert_audit_log
from backend.schemas.portfolio_intelligence import (
    MetricPack,
    RebalanceEventResponse,
    SnapshotResponse,
)
from backend.services.portfolio_intelligence.audit import (
    create_rebalance_explanation,
    create_no_rebalance_explanation,
)
from backend.services.portfolio_intelligence.rebalancer import (
    compute_trades,
    estimate_turnover,
)
from backend.services.portfolio_intelligence.rules import (
    apply_crash_overlay,
    compute_target_weights,
    enforce_position_limits,
    should_rebalance,
)

logger = logging.getLogger(__name__)


def _get_lane_config(lane_id: str) -> dict | None:
    """Get lane configuration from paper_portfolios.yaml."""
    return paper_portfolios.get(lane_id)


def _get_current_weights(conn, portfolio_id: str) -> dict[str, float]:
    """Get current portfolio weights from DB."""
    rows = conn.execute(
        "SELECT ticker, shares FROM paper_positions WHERE portfolio_id = ? AND closed_at IS NULL",
        (portfolio_id,),
    ).fetchall()

    if not rows:
        return {}

    # Get current prices for weight computation
    total_value = 0.0
    positions = []
    for row in rows:
        ticker = row["ticker"]
        shares = row["shares"]
        # Use cost_basis as price proxy when we don't have live prices
        cost = row["cost_basis"] if "cost_basis" in row.keys() else 1.0
        value = shares * cost
        positions.append((ticker, value))
        total_value += value

    if total_value <= 0:
        return {}

    return {t: v / total_value for t, v in positions}


def _get_last_rebalance_date(conn, portfolio_id: str) -> date | None:
    """Get the date of the most recent rebalance for a lane."""
    row = conn.execute(
        "SELECT triggered_at FROM rebalance_events WHERE portfolio_id = ? ORDER BY id DESC LIMIT 1",
        (portfolio_id,),
    ).fetchone()
    if row:
        try:
            return date.fromisoformat(row["triggered_at"][:10])
        except (ValueError, TypeError):
            return None
    return None


def _get_portfolio_notional(conn, portfolio_id: str) -> float:
    """Get the portfolio's current notional value."""
    row = conn.execute(
        "SELECT inception_value FROM paper_portfolios WHERE id = ?",
        (portfolio_id,),
    ).fetchone()
    if row:
        return row["inception_value"]
    return 100_000.0


def _get_sector_map() -> dict[str, str]:
    """Get sector map for position limit enforcement."""
    from backend.services.portfolio_intelligence.real_analyzer import _get_sector_map
    return _get_sector_map()


def _get_crash_prob() -> float | None:
    """Get current 3-month crash probability from the crash model."""
    try:
        from backend.services.crash_model import CrashPredictor
        predictor = CrashPredictor()
        result = predictor.predict_proba()
        if result and "crash_3m" in result:
            return result["crash_3m"]
    except Exception as e:
        logger.warning("Failed to get crash probability: %s", e)
    return None


def _get_regime() -> str | None:
    """Get current market regime from regime detector."""
    try:
        from backend.services.regime_detector import detect_regime
        result = detect_regime()
        if result:
            return result.get("regime", result.get("state"))
    except Exception as e:
        logger.warning("Failed to get regime: %s", e)
    return None


def _ensure_lane_initialized(lane_id: str, db_path=None) -> None:
    """Ensure the parent paper_portfolios row exists. Idempotent.

    Without this, run_reference_check fails with FOREIGN KEY constraint failed
    on a fresh DB because rebalance_events references paper_portfolios(id).
    """
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT id FROM paper_portfolios WHERE id = ?", (lane_id,)
        ).fetchone()
        if row is None:
            conn.close()
            initialize_lane(lane_id, db_path=db_path)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def run_reference_check(
    lane_id: str,
    db_path=None,
    as_of_date: date | None = None,
    crash_prob_override: float | None = None,
) -> SnapshotResponse:
    """Run a single reference lane check: evaluate triggers, rebalance if needed.

    This is the main entry point called by the scheduler or manual trigger.

    Args:
        lane_id: 'conservative', 'balanced', or 'aggressive'
        db_path: Optional DB path override (for testing)
        as_of_date: Date to evaluate as-of (default: today)
        crash_prob_override: Override crash prob (for testing/replay)

    Returns:
        SnapshotResponse with current state and any rebalance that occurred.
    """
    if as_of_date is None:
        as_of_date = date.today()

    lane_config = _get_lane_config(lane_id)
    if lane_config is None:
        return SnapshotResponse(
            portfolio_id=lane_id,
            date=as_of_date.isoformat(),
            weights={},
        )

    # Auto-initialize parent row if missing — prevents FK constraint failure
    # when run_reference_check is the first call after a fresh DB.
    _ensure_lane_initialized(lane_id, db_path)

    conn = get_connection(db_path)
    try:
        current_weights = _get_current_weights(conn, lane_id)
        last_rebalance = _get_last_rebalance_date(conn, lane_id)
        notional = _get_portfolio_notional(conn, lane_id)

        # Compute target weights
        target_weights = compute_target_weights(lane_config, paper_portfolios.get("universe"))

        # Check crash probability
        crash_prob = crash_prob_override if crash_prob_override is not None else _get_crash_prob()

        # Apply crash overlay
        overlay_triggered = False
        if crash_prob is not None:
            target_weights, overlay_triggered = apply_crash_overlay(
                target_weights, crash_prob, lane_config,
            )

        # Enforce position limits
        sector_map = _get_sector_map()
        target_weights = enforce_position_limits(
            target_weights,
            lane_config["max_single_name"],
            lane_config["max_sector"],
            sector_map,
        )

        # Check rebalance trigger
        trigger, reason = should_rebalance(
            current_weights,
            target_weights,
            lane_config["rebalance_trigger_drift"],
            lane_config["rebalance_frequency"],
            last_rebalance,
            as_of_date,
        )

        timestamp = datetime.now().isoformat()

        if not trigger:
            # Log non-trigger
            max_drift = max(
                (abs(current_weights.get(t, 0) - target_weights.get(t, 0))
                 for t in set(list(current_weights.keys()) + list(target_weights.keys()))),
                default=0.0,
            )
            days_since = (as_of_date - last_rebalance).days if last_rebalance else None
            explanation = create_no_rebalance_explanation(
                lane_id, max_drift, lane_config["rebalance_trigger_drift"],
                days_since, lane_config["rebalance_frequency"],
            )
            insert_audit_log(conn, timestamp, lane_id, "no_rebalance", {
                "max_drift": round(max_drift, 4),
                "threshold": lane_config["rebalance_trigger_drift"],
                "crash_prob_3m": crash_prob,
                "explanation": explanation,
            })

            return SnapshotResponse(
                portfolio_id=lane_id,
                date=as_of_date.isoformat(),
                weights={t: round(w, 6) for t, w in current_weights.items()},
            )

        # Compute trades
        prices = _get_current_prices(list(target_weights.keys()))
        trades, total_cost = compute_trades(
            current_weights,
            target_weights,
            prices,
            notional,
            lane_config.get("transaction_cost_bps", 5),
            lane_config.get("slippage_bps", 1),
        )

        # Generate explanation
        regime = _get_regime()
        explanation = create_rebalance_explanation(
            lane_id, reason, current_weights, target_weights,
            trades, crash_prob, regime, lane_config, total_cost,
        )

        # Write rebalance event
        event_id = insert_rebalance_event(
            conn, lane_id, timestamp, reason,
            current_weights, target_weights,
            crash_prob, regime, explanation,
        )

        # Log to audit
        insert_audit_log(conn, timestamp, lane_id, "rebalance_executed", {
            "event_id": event_id,
            "reason": reason,
            "n_trades": len(trades),
            "turnover": round(estimate_turnover(current_weights, target_weights), 4),
            "total_cost": total_cost,
            "crash_overlay_armed": overlay_triggered,
        })

        rebalance_response = RebalanceEventResponse(
            id=event_id,
            portfolio_id=lane_id,
            triggered_at=timestamp,
            trigger_reason=reason,
            pre_weights={t: round(w, 6) for t, w in current_weights.items()},
            post_weights={t: round(w, 6) for t, w in target_weights.items()},
            crash_prob_3m=crash_prob,
            regime=regime,
            explanation=explanation,
        )

        return SnapshotResponse(
            portfolio_id=lane_id,
            date=as_of_date.isoformat(),
            weights={t: round(w, 6) for t, w in target_weights.items()},
            latest_rebalance=rebalance_response,
        )

    finally:
        conn.close()


def _get_current_prices(tickers: list[str]) -> dict[str, float]:
    """Get current prices for trade computation."""
    prices = {}
    try:
        from backend.services.data_fetcher import fetch_safe
        from datetime import timedelta
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        for ticker in tickers:
            series = fetch_safe(ticker, start, end, name=ticker)
            if series is not None and len(series) > 0:
                prices[ticker] = float(series.iloc[-1])
    except Exception as e:
        logger.warning("Failed to fetch prices: %s", e)
    return prices


def run_all_lanes(db_path=None) -> dict[str, SnapshotResponse]:
    """Run rebalance checks for all three reference lanes (not personal)."""
    results = {}
    for lane_id in ["conservative", "balanced", "aggressive"]:
        try:
            results[lane_id] = run_reference_check(lane_id, db_path=db_path)
        except Exception as e:
            logger.error("Failed to run %s lane: %s", lane_id, e, exc_info=True)
    return results


def initialize_lane(
    lane_id: str,
    notional: float = 100_000.0,
    db_path=None,
) -> None:
    """Create inception snapshot for a new lane.

    Computes initial target weights and stores them as the first positions.
    """
    from backend.db import init_db, get_config_hash

    init_db(db_path)
    conn = get_connection(db_path)
    try:
        # Check if already initialized
        row = conn.execute(
            "SELECT id FROM paper_portfolios WHERE id = ?", (lane_id,)
        ).fetchone()
        if row:
            logger.info("Lane %s already initialized", lane_id)
            return

        lane_config = _get_lane_config(lane_id)
        if lane_config is None:
            raise ValueError(f"Unknown lane: {lane_id}")

        today = date.today().isoformat()
        config_hash = get_config_hash()

        conn.execute(
            "INSERT INTO paper_portfolios (id, inception_date, inception_value, config_version) VALUES (?, ?, ?, ?)",
            (lane_id, today, notional, config_hash),
        )

        # Compute initial weights
        target_weights = compute_target_weights(lane_config, paper_portfolios.get("universe"))
        target_weights = enforce_position_limits(
            target_weights,
            lane_config["max_single_name"],
            lane_config["max_sector"],
            _get_sector_map(),
        )

        # Insert positions
        for ticker, weight in target_weights.items():
            shares = (weight * notional) / 100.0  # placeholder price
            conn.execute(
                """INSERT INTO paper_positions (portfolio_id, ticker, shares, cost_basis, opened_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (lane_id, ticker, shares, 100.0, today),
            )

        conn.commit()

        # Log initialization
        timestamp = datetime.now().isoformat()
        insert_rebalance_event(
            conn, lane_id, timestamp, "initialization",
            {}, target_weights, None, None,
            f"Initial construction of {lane_id} portfolio with ${notional:,.0f} notional.",
        )

        insert_audit_log(conn, timestamp, lane_id, "lane_initialized", {
            "notional": notional,
            "n_positions": len(target_weights),
            "config_hash": config_hash,
        })

        logger.info("Initialized %s lane: %d positions, $%,.0f notional",
                     lane_id, len(target_weights), notional)

    finally:
        conn.close()
