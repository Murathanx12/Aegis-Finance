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

import logging
from datetime import date, datetime, timedelta

from backend.config import paper_portfolios
from backend.db import get_connection, insert_rebalance_event, insert_audit_log
from backend.schemas.portfolio_intelligence import (
    RebalanceEventResponse,
    SnapshotResponse,
)
from backend.services.portfolio_intelligence.audit import (
    create_rebalance_explanation,
    create_no_rebalance_explanation,
)
from backend.services.portfolio_intelligence.nav import CASH_TICKER
from backend.services.portfolio_intelligence.rebalancer import (
    compute_trades,
    estimate_turnover,
)
from backend.services.portfolio_intelligence.rules import (
    BOOK_LANES,
    REFERENCE_LANES,
    apply_crash_overlay,
    compute_target_weights,
    enforce_position_limits,
    should_rebalance,
)

logger = logging.getLogger(__name__)


def _get_lane_config(lane_id: str) -> dict | None:
    """Get lane configuration from paper_portfolios.yaml."""
    return paper_portfolios.get(lane_id)


def _get_current_weights(conn, portfolio_id: str, prices: dict | None = None) -> dict[str, float]:
    """Get current portfolio weights from DB, marked to market.

    Each position is valued at shares × current price. When a live price is
    unavailable (or `prices` is None), it falls back to the position's
    cost_basis — so weights still reconstruct, but the drift trigger only
    'sees' real market moves when current prices are supplied. The live path
    (run_reference_check) passes fetched prices; the simplest tests pass none.
    """
    rows = conn.execute(
        "SELECT ticker, shares, cost_basis FROM paper_positions "
        "WHERE portfolio_id = ? AND closed_at IS NULL",
        (portfolio_id,),
    ).fetchall()

    if not rows:
        return {}

    prices = prices or {}
    total_value = 0.0
    positions = []
    for row in rows:
        ticker = row["ticker"]
        shares = row["shares"]
        cost = row["cost_basis"] if "cost_basis" in row.keys() else 1.0
        px = prices.get(ticker)
        mark = px if (px is not None and px > 0) else cost
        value = shares * mark
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
            # H5: a malformed timestamp makes cadence look "never rebalanced"
            # → an early rebalance could fire. Loud, not silent.
            logger.warning("malformed triggered_at %r for %s — treating as no "
                           "prior rebalance", row["triggered_at"], portfolio_id)
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
    """Sector map for the reference lanes' position-limit enforcement.

    Uses the universe-aware lane map: sector ETFs + individual stocks map to
    GICS sectors (capped); broad-equity, bond, alt and cash sleeves are EXEMPT
    (absent from the map) so they are not wrongly clipped by the equity cap.
    """
    from backend.services.portfolio_intelligence.rules import lane_sector_map
    return lane_sector_map()


# Overlay statuses that are operational (the overlay actually evaluated) vs
# dark (the overlay engine could not run). `model_not_deployed` is the
# expected steady state in prod today — the crash model .pkl is gitignored
# (*.pkl) and not baked into the image, so no model loads on Railway. That
# state is surfaced LOUDLY in /api/health/full (overlay block) and logged
# ONCE per process here instead of spamming a WARNING per lane per cycle.
_OVERLAY_OPERATIONAL = {"evaluated", "override"}
_logged_overlay_statuses: set[str] = set()


def _log_overlay_status_once(status: str, detail: str = "") -> None:
    """Log a dark-overlay status without per-lane-per-cycle spam.

    Operational statuses are silent. `model_not_deployed` (expected) is logged
    once per process at INFO (it is always visible in the health overlay block
    regardless). A genuine error with a model PRESENT is a real anomaly and is
    logged at WARNING every time.
    """
    if status in _OVERLAY_OPERATIONAL:
        return
    if status == "model_not_deployed":
        if status not in _logged_overlay_statuses:
            _logged_overlay_statuses.add(status)
            logger.info(
                "Crash overlay DARK: no trained model deployed — overlay skipped "
                "on all reference lanes (expected in prod; *.pkl not in image). "
                "Status is exposed per-lane in /api/health/full overlay block. "
                "This message is logged once per process.")
        return
    # Model present but evaluation failed — a real anomaly, never suppressed.
    logger.warning("Crash overlay evaluation failed (%s): %s", status, detail)


def _evaluate_crash_overlay() -> tuple[float | None, str]:
    """Current 3-month crash probability for the overlay, with a status code.

    Mirrors the live dashboard path (market_dashboard._build_crash_section):
    load the shared predictor, build CURRENT features, call the model with the
    correct signature `predict_proba(features, "3m")`. The previous call site
    invoked `predict_proba()` with no args (raising every cycle) and expected a
    dict it never returned — see TRIAL-001 contamination note.

    Returns (crash_prob_3m | None, status) where status is one of:
      evaluated          — model ran, prob is the result
      model_not_deployed — no trained model present (expected in prod today)
      feature_unavailable— feature pipeline produced nothing
      predict_error      — model present but prediction raised
    """
    # Shared, process-cached predictor (loads the .pkl once if present).
    from backend.services.portfolio_intelligence.replay import _get_shared_predictor

    predictor = _get_shared_predictor()
    if predictor is None or not getattr(predictor, "is_trained", False):
        return None, "model_not_deployed"

    try:
        from backend.services.data_fetcher import DataFetcher
        from engine.training.features import build_feature_matrix
    except ImportError as e:
        logger.warning("Crash overlay feature pipeline unavailable: %s", e)
        return None, "feature_unavailable"

    try:
        fetcher = DataFetcher()
        data, _ = fetcher.fetch_market_data()
        fred_data = fetcher.fetch_fred_data()
        features = build_feature_matrix(data, fred_data=fred_data)
        if features is None or features.empty:
            return None, "feature_unavailable"
        available = [f for f in predictor.feature_names if f in features.columns]
        latest = features[available].iloc[[-1]] if available else features.iloc[[-1]]
        prob = predictor.predict_proba(latest, "3m")
        if prob is not None and len(prob) > 0:
            return float(prob[0]), "evaluated"
        return None, "predict_error"
    except Exception as e:  # model present but evaluation failed — keep loud
        logger.warning("Crash overlay prediction failed: %s", e)
        return None, "predict_error"


def _get_regime() -> str | None:
    """Get current market regime from regime detector."""
    try:
        from backend.services.data_fetcher import DataFetcher
        from backend.services.regime_detector import detect_regimes
        data, _ = DataFetcher().fetch_market_data()
        _, regime = detect_regimes(data)
        return regime
    except Exception as e:
        logger.warning("Failed to get regime: %s", e)
    return None


def _ensure_lane_initialized(lane_id: str, db_path=None) -> None:
    """Ensure the parent paper_portfolios row exists. Idempotent.

    Without this, run_reference_check fails with FOREIGN KEY constraint failed
    on a fresh DB because rebalance_events references paper_portfolios(id).
    Also creates the schema on a cold DB so the SELECT below doesn't fail
    with "no such table: paper_portfolios".
    """
    from backend.db import init_db
    init_db(db_path)

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
    force_reason: str | None = None,
) -> SnapshotResponse:
    """Run a single reference lane check: evaluate triggers, rebalance if needed.

    This is the main entry point called by the scheduler or manual trigger.

    Args:
        lane_id: A lane id from REFERENCE_LANES
        db_path: Optional DB path override (for testing)
        as_of_date: Date to evaluate as-of (default: today)
        crash_prob_override: Override crash prob (for testing/replay)
        force_reason: When set, skip the drift/frequency trigger and rebalance
            unconditionally with this reason — used for explicit config-change
            boundaries (v1→v2) so the segment break and the allocation change
            coincide exactly.

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
        # Fetch current prices once (whole universe) so current weights mark to
        # market and the drift trigger sees real moves; reused for trade pricing.
        from backend.services.portfolio_intelligence.rules import _get_sleeve_tickers
        _sleeves = _get_sleeve_tickers(paper_portfolios.get("universe", {}))
        _universe_tickers = _sleeves["equity"] + _sleeves["bond"] + _sleeves["alternative"]
        prices = _get_current_prices(_universe_tickers)

        current_weights = _get_current_weights(conn, lane_id, prices)
        last_rebalance = _get_last_rebalance_date(conn, lane_id)
        notional = _get_portfolio_notional(conn, lane_id)

        # Compute target weights. Lanes with optimizer=hrp get an AS-OF price
        # panel (live: ends at the latest bar) — the optimizer never fetches
        # its own data, which is what makes the replay path leakage-safe too.
        opt_meta: dict = {}
        price_panel = None
        if lane_config.get("optimizer") == "hrp":
            price_panel = _get_price_panel(_sleeves["equity"])
        target_weights = compute_target_weights(
            lane_config, paper_portfolios.get("universe"),
            price_data=price_panel, meta=opt_meta,
        )
        if opt_meta.get("optimizer_fallback"):
            # The gate fired: equal-weight fallback. Loud + audited, never silent.
            insert_audit_log(conn, datetime.now().isoformat(), lane_id,
                             "optimizer_fallback",
                             {"reason": opt_meta["optimizer_fallback"]})

        # Check crash probability (with a status so a dark overlay is visible)
        if crash_prob_override is not None:
            crash_prob, overlay_status = crash_prob_override, "override"
        else:
            crash_prob, overlay_status = _evaluate_crash_overlay()

        # Apply crash overlay
        overlay_triggered = False
        if crash_prob is not None:
            target_weights, overlay_triggered = apply_crash_overlay(
                target_weights, crash_prob, lane_config,
            )

        # Persist the overlay evaluation so a structurally-dark overlay can
        # never again run unseen for days: /api/health/full reads the latest
        # crash_overlay_eval row per lane (see scheduler.overlay_status()).
        insert_audit_log(conn, datetime.now().isoformat(), lane_id,
                         "crash_overlay_eval", {
                             "status": overlay_status,
                             "crash_prob_3m": crash_prob,
                             "armed": overlay_triggered,
                             "threshold": lane_config.get(
                                 "crash_overlay", {}).get("crash_prob_threshold"),
                         })
        _log_overlay_status_once(overlay_status)

        # Enforce position limits
        sector_map = _get_sector_map()
        target_weights = enforce_position_limits(
            target_weights,
            lane_config["max_single_name"],
            lane_config["max_sector"],
            sector_map,
        )

        # Check rebalance trigger (or honor an explicit config-change force)
        if force_reason is not None:
            trigger, reason = True, force_reason
        else:
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

        # Compute trades (reuse the prices fetched above — superset of targets)
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
        if opt_meta.get("optimizer_used"):
            explanation += (
                f" [optimizer: hrp, as-of {opt_meta.get('optimizer_as_of')}, "
                f"{opt_meta.get('optimizer_n_obs')} obs]"
            )
        elif lane_config.get("optimizer") == "hrp":
            explanation += (
                f" [optimizer: equal-weight FALLBACK — "
                f"{opt_meta.get('optimizer_fallback', 'unknown')}]"
            )

        # Write rebalance event (stamped with the producing config version)
        from backend.db import get_config_hash
        event_id = insert_rebalance_event(
            conn, lane_id, timestamp, reason,
            current_weights, target_weights,
            crash_prob, regime, explanation,
            config_version=get_config_hash(),
        )

        # Apply the trades to the book: close open positions, open the target
        # book at current prices. Without this the event is paper-only and the
        # NAV keeps tracking the OLD holdings (latent divergence bug found in
        # the Step #2 session — events never traded before this).
        _apply_rebalance_positions(
            conn, lane_id, target_weights, prices, notional,
            total_cost, timestamp,
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
    """Get current prices for trade computation.

    Degrades gracefully: one ticker's fetch failure never aborts the rest —
    callers fall back to cost_basis for any ticker missing from the result.
    """
    prices: dict[str, float] = {}
    try:
        from backend.services.data_fetcher import fetch_safe
        from datetime import timedelta
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
    except Exception as e:
        logger.warning("Price fetch unavailable: %s", e)
        return prices
    for ticker in tickers:
        try:
            series = fetch_safe(ticker, start, end, name=ticker)
            if series is not None and len(series) > 0:
                prices[ticker] = float(series.iloc[-1])
        except Exception as e:
            logger.warning("Price fetch failed for %s: %s", ticker, e)
    return prices


def _get_price_panel(tickers: list[str], lookback_days: int = 504):
    """As-of wide close-price panel for the optimizer (live path: ends at the
    latest bar). Batch-fetched, cached for the day — the optimizer itself
    never fetches data, so replay can hand it a truncated panel instead.
    """
    from backend.cache import cache_get, cache_set

    key = f"pi:price-panel:{lookback_days}:{date.today().isoformat()}"
    hit = cache_get(key, 3600)
    if hit is not None:
        return hit
    try:
        import pandas as pd
        from backend.services.data_fetcher import _fetch_batch_yahoo

        start = (date.today() - timedelta(days=int(lookback_days * 1.6))).isoformat()
        end = (date.today() + timedelta(days=1)).isoformat()
        batch = _fetch_batch_yahoo(tickers, start, end)
        if not batch:
            return None
        panel = pd.DataFrame(batch)
        cache_set(key, panel)
        return panel
    except Exception as e:
        logger.error("Price panel fetch failed (optimizer will fall back): %s", e)
        return None


def _apply_rebalance_positions(
    conn,
    lane_id: str,
    target_weights: dict[str, float],
    prices: dict[str, float],
    notional: float,
    total_cost: float,
    timestamp: str,
) -> None:
    """Re-book the lane at the target weights: close all open positions and
    open the target book at current prices (CASH at 1.0). Net notional after
    transaction costs. This is what makes a rebalance event REAL — before
    this existed, events were recorded but the book never traded.
    """
    from backend.db import _write_lock

    net_notional = max(notional - (total_cost or 0.0), 0.0)
    with _write_lock:
        conn.execute(
            "UPDATE paper_positions SET closed_at = ? "
            "WHERE portfolio_id = ? AND closed_at IS NULL",
            (timestamp, lane_id),
        )
        for ticker, weight in target_weights.items():
            if weight <= 0:
                continue
            if ticker == CASH_TICKER:
                px = 1.0
            else:
                px = prices.get(ticker)
                if px is None or px <= 0:
                    # No live price: book at a $100 placeholder like
                    # initialize_lane does — MTM falls back to cost_basis so
                    # the position stays valued at its booked weight.
                    px = 100.0
            shares = (weight * net_notional) / px
            conn.execute(
                "INSERT INTO paper_positions "
                "(portfolio_id, ticker, shares, cost_basis, opened_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (lane_id, ticker, shares, px, timestamp),
            )
        conn.commit()


def run_all_lanes(db_path=None) -> dict[str, SnapshotResponse]:
    """Run rebalance checks for all reference lanes (not personal)."""
    results = {}
    for lane_id in REFERENCE_LANES:
        try:
            results[lane_id] = run_reference_check(lane_id, db_path=db_path)
        except Exception as e:
            logger.error("Failed to run %s lane: %s", lane_id, e, exc_info=True)
    return results


def apply_config_change_rebalances(db_path=None) -> dict[str, str]:
    """Idempotent startup migration for SHA-versioned config changes.

    For each lane: if it doesn't exist yet → initialize it (new lanes, e.g.
    the balanced-ew-control trial) and register it in the experiment registry;
    if its stored config_version differs from the current YAML hash → force an
    explicit rebalance (sharp segment boundary: the event, the allocation
    change, and the version flip coincide) and update the stored version.

    Idempotency: once config_version matches, nothing fires. If the process
    dies between the forced rebalance and the version update, the next boot
    fires a second forced event with near-zero trades — visible and harmless,
    never corrupting.
    """
    from backend.db import get_config_hash, init_db

    init_db(db_path)
    current = get_config_hash()
    out: dict[str, str] = {}

    for lane_id in REFERENCE_LANES:
        try:
            conn = get_connection(db_path)
            try:
                row = conn.execute(
                    "SELECT config_version FROM paper_portfolios WHERE id = ?",
                    (lane_id,),
                ).fetchone()
            finally:
                conn.close()

            if row is None:
                initialize_lane(lane_id, db_path=db_path)
                _register_lane_trial(lane_id, current, db_path=db_path)
                out[lane_id] = "initialized"
                continue

            if row["config_version"] == current:
                out[lane_id] = "current"
                continue

            old = row["config_version"]
            reason = f"config_change {old[:8]}->{current[:8]}"
            logger.warning("Lane %s: %s — forcing explicit boundary rebalance",
                           lane_id, reason)
            run_reference_check(lane_id, db_path=db_path, force_reason=reason)

            conn = get_connection(db_path)
            try:
                conn.execute(
                    "UPDATE paper_portfolios SET config_version = ? WHERE id = ?",
                    (current, lane_id),
                )
                conn.commit()
            finally:
                conn.close()
            out[lane_id] = "rebalanced"
        except Exception as e:
            logger.error("Config-change migration failed for %s: %s",
                         lane_id, e, exc_info=True)
            out[lane_id] = f"error: {e}"

    try:
        ensure_trial_decision_rules(db_path=db_path)
    except Exception as e:
        logger.error("Decision-rule embedding failed: %s", e, exc_info=True)
    return out


_TRIAL_DECISION_RULES = {
    "balanced-ew-control": {
        "trial": "TRIAL-001",
        "primary_metric": "full-window net Sharpe from daily paper_nav returns, inception 2026-06-10",
        "min_window_months": 12,
        "earliest_decision": "2027-06-10",
        "evaluation_cadence": "quarterly after month 12",
        "revert_threshold": "HRP trails control net Sharpe by >= 0.30 -> revert as config v3 via guarded loop",
        "adopt_threshold": "HRP leads by >= 0.30 -> recorded adopted-confirmed",
        "secondary_metrics_reported_not_deciding": [
            "max_drawdown", "annualized_volatility", "calmar",
            "turnover", "transaction_costs", "tracking_error",
        ],
        "crash_event_override": "SPY drawdown >= 20% in-window -> no decision until >= 6 months past trough",
        "canonical_doc": "docs/TRIALS/TRIAL-001-hrp-vs-ew.md",
        "pre_registered": "2026-06-11",
    },
}


def ensure_trial_decision_rules(db_path=None) -> int:
    """Idempotently embed pre-registered decision rules into registry notes.

    Pre-registration must live IN the registry (not only in git) so the rule
    travels with the trial row Optimus ingests. Only ever ADDS a missing
    decision_rule key — a rule already present is never modified (changing a
    rule after data accrues invalidates the trial; do that in a new trial).
    Returns the number of rows updated.
    """
    import json as _json

    updated = 0
    conn = get_connection(db_path)
    try:
        for lane_id, rule in _TRIAL_DECISION_RULES.items():
            row = conn.execute(
                "SELECT id, notes FROM rule_experiments "
                "WHERE lane_id = ? ORDER BY id LIMIT 1",
                (lane_id,),
            ).fetchone()
            if row is None:
                continue
            try:
                notes = _json.loads(row["notes"]) if row["notes"] else {}
            except Exception:
                notes = {"raw_notes": row["notes"]}
            if "decision_rule" in notes:
                continue  # never touch an existing pre-registration
            notes["decision_rule"] = rule
            conn.execute(
                "UPDATE rule_experiments SET notes = ? WHERE id = ?",
                (_json.dumps(notes), row["id"]),
            )
            conn.commit()
            updated += 1
            logger.info("Pre-registered decision rule embedded for trial lane %s",
                        lane_id)
    finally:
        conn.close()
    return updated


def _register_lane_trial(lane_id: str, config_version: str, db_path=None) -> None:
    """Every paper lane is a registered trial (guardrail): it enters the
    cumulative trial count that deflates future DSR/PBO. The registry schema
    has no hypothesis/purpose columns yet (P1 #6 generalizes it) — they ride
    in structured notes JSON.
    """
    import json as _json

    hypotheses = {
        "balanced-ew-control": {
            "hypothesis": "HRP adds value over equal-weight on forward data "
                          "(control: balanced mandate frozen at equal-weight)",
            "purpose": "optimizer-variant",
        },
        "mirror": {
            "hypothesis": "Aegis managing Murat's actual book by its own rules "
                          "(HRP, balanced cadence) beats Murat's conviction "
                          "management of the same book, and the rules baselines, "
                          "on forward data — from a shared today-dated inception",
            "purpose": "portfolio-mirror",
            "canonical_doc": "docs/TRIALS/TRIAL-002-mirror-vs-rules.md",
            "pre_registered": "2026-06-14",
        },
        "conviction": {
            "hypothesis": "Murat's logged conviction decisions add value over the "
                          "rules baselines on forward data (single pre-registered "
                          "strategy; inception today, prior return excluded)",
            "purpose": "conviction",
            "canonical_doc": "docs/TRIALS/TRIAL-003-conviction-vs-rules.md",
            "pre_registered": "2026-06-14",
        },
        "conservative-atr": {
            "hypothesis": "Adding an ATR Chandelier trailing stop + vol-target cap "
                          "to the conservative mandate improves risk-adjusted return "
                          "vs the frozen unmanaged `conservative` control, primarily "
                          "by reducing drawdown — honest prior: shallower maxDD at "
                          "~flat-to-slightly-lower Sharpe, NOT a Sharpe increase",
            "purpose": "exit-overlay-trial",
            "canonical_doc": "docs/TRIALS/TRIAL-EXIT-atr-trailing-stops.md",
            "pre_registered": "2026-06-15",
            "decision_rule": {
                "trial": "TRIAL-EXIT",
                "primary_metric": "full-window net Sharpe vs conservative control",
                "co_primary": "max drawdown (must be shallower — the overlay's claim)",
                "min_window_months": 12,
                "adopt_threshold": "net Sharpe within -0.10 AND maxDD shallower by >=3 pts",
                "reject_threshold": "net Sharpe trails by >=0.20 OR maxDD not shallower",
                "params_frozen": "atr_stop_multiple/vol_target at config defaults (no tuning)",
                "crash_event_override": "SPY drawdown >=20% defers decisions until >=6mo past trough",
            },
        },
        "smallmid-quality": {
            "hypothesis": "The BRAIN-007 composite book (top-30 by mean winsorized "
                          "z of PIT gross profitability + opportunistic-insider "
                          "flag, EW buy-and-hold, quarterly artifact refresh) "
                          "beats IWM on forward data. Backtest prior: replicated "
                          "in 3 independent windows over 42y but DSR~0.10 and "
                          "FF6 alpha negative — the forward clock is the test",
            "purpose": "smq-forward-trial",
            "canonical_doc": "docs/TRIALS/TRIAL-SMQ-FWD.md",
            "pre_registered": "2026-07-22",
            "decision_rule": {
                "trial": "TRIAL-SMQ-FWD",
                "primary_metric": "since-inception total return vs IWM",
                "min_window_months": 24,
                "earliest_decision": "2028-07-22",
                "adopt_threshold": "lane - IWM > 0 with bootstrap 90% CI excluding 0",
                "reject_threshold": "lane - IWM < -5pp at 24mo",
                "params_frozen": "holdings are the yaml hash; refresh = stamped config change",
                "degraded_clause": ">3 holdings unpriceable mid-flight flags the lane degraded",
            },
        },
    }
    meta = hypotheses.get(lane_id, {
        "hypothesis": f"lane {lane_id} forward trial",
        "purpose": "benchmark",
    })

    conn = get_connection(db_path)
    try:
        from backend.db import count_cumulative_trials
        cumulative = count_cumulative_trials(conn) + 1
        conn.execute(
            "INSERT INTO rule_experiments "
            "(created_at, config_version, lane_id, param, old_value, new_value, "
            " batch_trials, cumulative_trials, verdict, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now().isoformat(), config_version, lane_id,
                f"lane:{lane_id}", None, "registered",
                1, cumulative, "adopted", _json.dumps(meta),
            ),
        )
        conn.commit()
        logger.info("Registered lane trial %s (cumulative trials now %d)",
                    lane_id, cumulative)
    finally:
        conn.close()


def mark_lane_to_market(
    lane_id: str,
    prices: dict | None = None,
    as_of_date: date | None = None,
    db_path=None,
) -> float | None:
    """Mark a lane's open positions to current prices and persist daily NAV.

    Reuses the shared nav.py engine (NOT a second valuation path): NAV is
    shares × current price, summed. A position with no current price falls
    back to its cost_basis so NAV is never silently understated. The NAV row
    is stamped with the current config_version so a versioned rule/optimization
    change starts a clean track-record segment.

    Returns the NAV, or None if the lane has no open positions or no live
    price could be fetched for ANY position (a flat all-cost-basis NAV row
    would be indistinguishable from real data — fail loudly instead).
    """
    from backend.db import get_config_hash, insert_nav
    from backend.services.portfolio_intelligence.nav import mark_to_market

    if as_of_date is None:
        as_of_date = date.today()

    _ensure_lane_initialized(lane_id, db_path)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT ticker, shares, cost_basis FROM paper_positions "
            "WHERE portfolio_id = ? AND closed_at IS NULL",
            (lane_id,),
        ).fetchall()
        if not rows:
            return None

        tickers = [r["ticker"] for r in rows]
        if prices is None:
            prices = _get_current_prices(tickers)

        # Total price failure must NOT persist a NAV row: marking every position
        # at cost_basis would write a flat line indistinguishable from real data.
        # Partial failures still degrade per-ticker to cost_basis below.
        if not any(prices.get(t) for t in tickers):
            logger.error(
                "MTM %s: no live price for any of %d tickers — NAV row NOT persisted",
                lane_id, len(tickers),
            )
            return None

        shares = {r["ticker"]: r["shares"] for r in rows}
        # Fill any missing live price with the position's cost_basis (last known).
        marks = {}
        for r in rows:
            px = prices.get(r["ticker"])
            marks[r["ticker"]] = px if (px is not None and px > 0) else r["cost_basis"]

        nav_value = mark_to_market(shares, marks, cash=0.0)

        insert_nav(
            conn, lane_id, as_of_date.isoformat(), float(nav_value),
            get_config_hash(), datetime.now().isoformat(),
        )
        return float(nav_value)
    finally:
        conn.close()


def mark_all_lanes(db_path=None) -> dict[str, float | None]:
    """Mark all reference lanes to market and persist daily NAV."""
    out: dict[str, float | None] = {}
    for lane_id in REFERENCE_LANES:
        try:
            out[lane_id] = mark_lane_to_market(lane_id, db_path=db_path)
        except Exception as e:
            logger.error("MTM failed for %s: %s", lane_id, e, exc_info=True)
            out[lane_id] = None
    return out


def mark_all_book_lanes(db_path=None) -> dict[str, float | None]:
    """Mark SEEDED book lanes (P1 #6) to market and persist daily NAV.

    Only marks book lanes that already have a paper_portfolios row — an unseeded
    book lane is skipped, so MTM never auto-creates one (seeding is the explicit,
    attended write-path; auto-init here would write a junk inception). Reuses
    mark_lane_to_market, which already degrades per-ticker to cost_basis on a
    single bad symbol and refuses to persist a NAV row if EVERY price fails.
    """
    out: dict[str, float | None] = {}
    for lane_id in BOOK_LANES:
        try:
            conn = get_connection(db_path)
            try:
                seeded = conn.execute(
                    "SELECT 1 FROM paper_portfolios WHERE id = ?", (lane_id,)
                ).fetchone()
            finally:
                conn.close()
            if not seeded:
                out[lane_id] = None  # not yet seeded — skip, never auto-create
                continue
            out[lane_id] = mark_lane_to_market(lane_id, db_path=db_path)
        except Exception as e:
            logger.error("Book MTM failed for %s: %s", lane_id, e, exc_info=True)
            out[lane_id] = None
    return out


def seed_all_book_lanes(db_path=None, prices: dict | None = None) -> dict:
    """Seed every book lane (idempotent) then immediately mark to market, so the
    freshness canary is green from the first health check after seeding.

    ATTENDED WRITE-PATH — invoked only by the env-gated startup hook
    (AEGIS_SEED_BOOK_LANES=1) or scripts/seed_p1_6_lanes.py, never on a normal
    boot. Idempotent: already-seeded lanes are skipped.
    """
    out: dict = {"seeded": {}, "mtm": {}}
    for lane_id in BOOK_LANES:
        out["seeded"][lane_id] = seed_book_lane(lane_id, db_path=db_path, prices=prices)
    out["mtm"] = mark_all_book_lanes(db_path=db_path)
    return out


def initialize_lane(
    lane_id: str,
    notional: float = 100_000.0,
    db_path=None,
    prices: dict | None = None,
) -> None:
    """Create inception snapshot for a new lane.

    Computes initial target weights and stores them as the first positions at
    REAL entry prices (shares = weight·notional / price), so the book holds
    genuine share counts that mark to market. Falls back to a $100 placeholder
    only for tickers whose price can't be fetched.
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

        # Real entry prices so positions hold genuine share counts that MTM.
        if prices is None:
            prices = _get_current_prices(list(target_weights.keys()))

        # Insert positions at real entry prices ($100 placeholder only if a
        # ticker can't be priced, so the lane still initializes offline).
        for ticker, weight in target_weights.items():
            px = prices.get(ticker)
            entry = px if (px is not None and px > 0) else 100.0
            shares = (weight * notional) / entry
            conn.execute(
                """INSERT INTO paper_positions (portfolio_id, ticker, shares, cost_basis, opened_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (lane_id, ticker, shares, entry, today),
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

        logger.info("Initialized %s lane: %d positions, $%s notional",
                     lane_id, len(target_weights), f"{notional:,.0f}")

    finally:
        conn.close()


def seed_book_lane(lane_id: str, db_path=None, prices: dict | None = None) -> dict:
    """Seed a P1 #6 book lane (mirror/conviction) at TODAY's market value.

    Inception = today, at CURRENT prices, current-market-value weights from the
    confirmed share-count book, normalized to the $100k notional. NO historical
    buy prices, NO reconstructed past inception (look-ahead). Idempotent: if the
    lane already has a paper_portfolios row it is left untouched (re-running never
    double-seeds).

    Fail-loud garbage gate: unlike initialize_lane (which books an unpriceable ETF
    at a $100 placeholder for offline init), a REAL book must be fully priced —
    compute_book_mv_weights raises BEFORE any write if a name is unpriceable, so a
    junk inception is never persisted. Stamped with get_book_config_hash() (the
    book-lane file hash — independent of the reference lanes' versioning).

    Returns {lane_id, seeded, notional, weights, n_positions} (seeded=False if it
    already existed).
    """
    from backend.config import book_lanes as _book_lanes
    from backend.db import get_book_config_hash, init_db
    from backend.services.portfolio_intelligence.rules import compute_book_mv_weights

    lane_cfg = _book_lanes.get(lane_id)
    if not lane_cfg or "purpose" not in lane_cfg:
        raise ValueError(f"Unknown book lane: {lane_id}")

    holdings = _book_lanes.get("holdings") or {}
    notional = float((_book_lanes.get("inception") or {}).get("notional_usd", 100_000.0))

    init_db(db_path)
    conn = get_connection(db_path)
    try:
        if conn.execute(
            "SELECT id FROM paper_portfolios WHERE id = ?", (lane_id,)
        ).fetchone():
            logger.info("Book lane %s already seeded — skipping (idempotent)", lane_id)
            return {"lane_id": lane_id, "seeded": False, "reason": "already_exists"}

        tickers = list(holdings.keys())
        if prices is None:
            prices = _get_current_prices(tickers)
        # Fail loud on any unpriceable name — raises before any DB write.
        weights = compute_book_mv_weights(holdings, prices)

        today = date.today().isoformat()
        config_hash = get_book_config_hash()
        timestamp = datetime.now().isoformat()

        conn.execute(
            "INSERT INTO paper_portfolios (id, inception_date, inception_value, "
            "config_version) VALUES (?, ?, ?, ?)",
            (lane_id, today, notional, config_hash),
        )
        for ticker, weight in weights.items():
            px = float(prices[ticker])  # present + positive (guaranteed by the gate)
            shares = (weight * notional) / px
            conn.execute(
                "INSERT INTO paper_positions (portfolio_id, ticker, shares, "
                "cost_basis, opened_at) VALUES (?, ?, ?, ?, ?)",
                (lane_id, ticker, shares, px, today),
            )
        conn.commit()

        insert_rebalance_event(
            conn, lane_id, timestamp, "initialization", {}, weights, None, None,
            f"Book-lane inception of {lane_id} at ${notional:,.0f} notional, "
            f"current-market-value weights ({len(weights)} names). Inception today; "
            "prior personal performance is NOT part of this record.",
            config_version=config_hash,
        )
        insert_audit_log(conn, timestamp, lane_id, "book_lane_seeded", {
            "notional": notional, "n_positions": len(weights),
            "config_hash": config_hash, "purpose": lane_cfg["purpose"],
        })
        logger.info("Seeded book lane %s: %d positions, $%s notional (purpose=%s)",
                    lane_id, len(weights), f"{notional:,.0f}", lane_cfg["purpose"])
        result = {"lane_id": lane_id, "seeded": True, "notional": notional,
                  "weights": weights, "n_positions": len(weights)}
    finally:
        conn.close()

    # Register the lane as a trial AFTER the seed connection is closed (avoids
    # nested write connections). Every paper lane is a registered trial — it
    # enters the cumulative count that deflates future DSR/PBO.
    _register_lane_trial(lane_id, config_hash, db_path=db_path)
    return result
