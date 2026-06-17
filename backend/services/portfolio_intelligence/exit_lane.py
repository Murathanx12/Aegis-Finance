"""
TRIAL-EXIT — conservative-ATR lane: seeding + daily exit-overlay management.

The `conservative-atr` lane runs the conservative mandate (identical HRP-on-the-
equity-sleeve allocation, same universe / cadence / cost model) PLUS the ATR
Chandelier trailing-stop + volatility-target exit overlay. The existing
`conservative` lane is the FROZEN, unmanaged control — the only treatment
difference is the overlay, so the forward NAV delta isolates it.

Two entry points, both mirroring the book-lane pattern (book_management.py):

  • ``seed_conservative_atr_lane`` — ATTENDED write-path, invoked only by the
    env-gated startup hook (AEGIS_SEED_CONSERVATIVE_ATR=1). Builds the lane at
    today's mandate weights, stamps the ISOLATED conservative-ATR config hash
    (never the reference hash → the frozen control's segment is untouched), and
    registers TRIAL-EXIT. Idempotent.

  • ``run_exit_overlay_check`` — wired into the daily check, NO-OP (status
    ``not_seeded``) until the lane is seeded, exactly like Plan-3 book management.
    Once seeded it (1) recomputes the mandate target, (2) applies the ATR exit
    overlay — names whose trailing stop fired rotate to CASH, (3) applies the
    vol-target cap to the equity sleeve, then (4) rebalances on the mandate
    cadence/drift OR immediately when the overlay forces an exit. Every write is
    stamped with the conservative-ATR hash.

HARD CONSTRAINTS (from the trial doc): this arms nothing on its own (dormant
until the attended seed); exit params are FROZEN at config["exit_engine"]
defaults (no per-lane tuning); it NEVER touches the reference lanes or the book
lanes (separate config hash → cannot perturb their NAV / TRIAL-001).
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from backend.config import conservative_atr_lanes, paper_portfolios
from backend.db import (
    get_conservative_atr_config_hash,
    get_connection,
    init_db,
    insert_audit_log,
    insert_rebalance_event,
)
from backend.services.portfolio_intelligence import reference_engine as _re
from backend.services.portfolio_intelligence.exit_overlay import (
    evaluate_exit_overlay,
    vol_capped_weights,
)
from backend.services.portfolio_intelligence.nav import CASH_TICKER
from backend.services.portfolio_intelligence.rebalancer import (
    compute_trades,
    estimate_turnover,
)
from backend.services.portfolio_intelligence.rules import (
    CONSERVATIVE_ATR_LANES,
    _get_sleeve_tickers,
    classify_asset,
    compute_target_weights,
    enforce_position_limits,
    should_rebalance,
)

logger = logging.getLogger(__name__)

LANE_ID = "conservative-atr"


def _lane_cfg() -> dict:
    cfg = conservative_atr_lanes.get(LANE_ID)
    if not cfg or "purpose" not in cfg:
        raise ValueError(f"conservative-ATR lane config missing/invalid: {LANE_ID}")
    return cfg


def _is_seeded(conn) -> bool:
    return conn.execute(
        "SELECT 1 FROM paper_portfolios WHERE id = ?", (LANE_ID,)
    ).fetchone() is not None


def _mandate_tickers() -> list[str]:
    sleeves = _get_sleeve_tickers(paper_portfolios.get("universe", {}))
    return list(dict.fromkeys(sleeves["equity"] + sleeves["bond"] + sleeves["alternative"]))


def _base_target(panel, meta: dict) -> dict[str, float]:
    """Conservative mandate weights (HRP-on-equity + position limits) — identical
    to what the frozen control computes. Equal-weight fallback (loud, via meta) if
    no panel / HRP can't produce valid weights."""
    cfg = _lane_cfg()
    weights = compute_target_weights(cfg, paper_portfolios.get("universe"), panel, meta)
    return enforce_position_limits(
        weights, cfg["max_single_name"], cfg["max_sector"], _re._get_sector_map()
    )


def _open_positions_with_entry(conn) -> dict[str, dict]:
    """Currently-held positions → {ticker: {entry_date}} for the exit overlay.
    entry_date = the position's opened_at (when the lane last (re)booked it)."""
    rows = conn.execute(
        "SELECT ticker, opened_at FROM paper_positions "
        "WHERE portfolio_id = ? AND closed_at IS NULL", (LANE_ID,),
    ).fetchall()
    out: dict[str, dict] = {}
    for r in rows:
        if r["ticker"] == CASH_TICKER:
            continue
        oa = r["opened_at"]
        out[r["ticker"]] = {"entry_date": (oa[:10] if oa else None)}
    return out


def _apply_exit_overlay(conn, base_target: dict[str, float], panel) -> tuple[dict[str, float], list[str], dict]:
    """Rotate ATR-stopped names to CASH, then vol-cap the equity sleeve.

    Returns (adjusted_target, stopped_tickers, exit_detail). Pure of DB writes —
    only READS current positions (for entry dates) to evaluate the stops.
    """
    positions = _open_positions_with_entry(conn)
    price_series: dict = {}
    if panel is not None:
        cols = getattr(panel, "columns", [])
        for t in positions:
            if t in cols:
                s = panel[t].dropna()
                if len(s) >= 2:
                    price_series[t] = s

    decisions = evaluate_exit_overlay(positions, price_series)
    stopped = sorted(t for t, d in decisions.items() if d.get("action") == "exit")

    target = dict(base_target)
    freed = 0.0
    for t in stopped:
        freed += target.get(t, 0.0)
        target[t] = 0.0
    if freed > 0:
        target[CASH_TICKER] = target.get(CASH_TICKER, 0.0) + freed

    # Vol-target cap on the (surviving) equity sleeve only — bonds/alts/cash are
    # left untouched. vol_capped_weights renormalises to the equity total, so the
    # sleeve's overall allocation is preserved; only WITHIN-sleeve sizing shifts.
    eq = {t: w for t, w in target.items() if w > 0 and classify_asset(t) == "equity"}
    if eq and panel is not None:
        cols = getattr(panel, "columns", [])
        rets = {t: panel[t].pct_change().dropna().tolist() for t in eq if t in cols}
        if rets:
            capped = vol_capped_weights(eq, rets)
            # Guard: if every sized name had non-finite/zero vol the cap collapses
            # to all-zero — don't let that vanish the equity sleeve; keep uncapped.
            if sum(capped.values()) > 0:
                target.update(capped)

    total = sum(w for w in target.values() if w > 0)
    if total > 0:
        target = {t: w / total for t, w in target.items() if w > 0}
    return target, stopped, {t: decisions[t] for t in stopped}


def seed_conservative_atr_lane(db_path=None, prices: dict | None = None, panel=None) -> dict:
    """Seed the conservative-ATR lane at TODAY's mandate weights, $100k notional.

    ATTENDED write-path (env-gated). Inception = today; NO reconstructed past
    (look-ahead). Idempotent: if the lane already has a paper_portfolios row it is
    left untouched. Stamped with the ISOLATED conservative-ATR hash, then
    registers TRIAL-EXIT in rule_experiments (cumulative trial count → +1).

    Returns {lane_id, seeded, notional, weights, n_positions} (seeded=False if it
    already existed).
    """
    cfg = _lane_cfg()
    notional = float((conservative_atr_lanes.get("inception") or {}).get("notional_usd", 100_000.0))

    init_db(db_path)
    conn = get_connection(db_path)
    try:
        if _is_seeded(conn):
            logger.info("Conservative-ATR lane already seeded — skipping (idempotent)")
            return {"lane_id": LANE_ID, "seeded": False, "reason": "already_exists"}

        meta: dict = {}
        if panel is None:
            panel = _re._get_price_panel(_mandate_tickers())
        weights = _base_target(panel, meta)
        if not weights:
            raise ValueError("conservative-ATR seed produced empty weights — refusing to seed")

        tickers = [t for t in weights if t != CASH_TICKER]
        if prices is None:
            prices = _re._get_current_prices(tickers)

        today = date.today().isoformat()
        config_hash = get_conservative_atr_config_hash()
        ts = datetime.now().isoformat()

        conn.execute(
            "INSERT INTO paper_portfolios (id, inception_date, inception_value, "
            "config_version) VALUES (?, ?, ?, ?)",
            (LANE_ID, today, notional, config_hash),
        )
        for ticker, weight in weights.items():
            if weight <= 0:
                continue
            if ticker == CASH_TICKER:
                px = 1.0
            else:
                px = prices.get(ticker)
                px = px if (px is not None and px > 0) else 100.0
            shares = (weight * notional) / px
            conn.execute(
                "INSERT INTO paper_positions (portfolio_id, ticker, shares, "
                "cost_basis, opened_at) VALUES (?, ?, ?, ?, ?)",
                (LANE_ID, ticker, shares, px, today),
            )
        conn.commit()

        insert_rebalance_event(
            conn, LANE_ID, ts, "initialization", {}, weights, None, None,
            f"Conservative-ATR inception at ${notional:,.0f} notional "
            f"({len(weights)} names): the conservative mandate + ATR exit overlay. "
            "Frozen `conservative` lane is the unmanaged control; inception today.",
            config_version=config_hash,
        )
        insert_audit_log(conn, ts, LANE_ID, "conservative_atr_seeded", {
            "notional": notional, "n_positions": len(weights),
            "config_hash": config_hash, "purpose": cfg["purpose"],
            "optimizer": meta.get("optimizer_used") or "equal_weight_fallback",
        })
        logger.info("Seeded conservative-ATR lane: %d positions, $%s notional",
                    len(weights), f"{notional:,.0f}")
        result = {"lane_id": LANE_ID, "seeded": True, "notional": notional,
                  "weights": weights, "n_positions": len(weights)}
    finally:
        conn.close()

    # Register AFTER closing the seed connection (avoids nested write conns), like
    # seed_book_lane. Enters the cumulative trial count that deflates future DSR/PBO.
    _re._register_lane_trial(LANE_ID, config_hash, db_path=db_path)
    return result


def run_exit_overlay_check(db_path=None, as_of_date=None, panel=None,
                           prices=None, force_reason=None) -> dict:
    """Daily exit-overlay management for the conservative-ATR lane.

    NO-OP (status ``not_seeded``) until the attended seed runs — safe to wire
    pre-seed, mirroring Plan-3 book management. Once seeded: recompute the mandate
    target, apply the ATR exit overlay (stopped names → cash) + vol cap, then
    rebalance on the mandate cadence/drift OR immediately if a stop fired. HOLDS
    (no write) when nothing triggers. Every boundary stamped with the ATR hash.
    """
    as_of_date = as_of_date or date.today()
    conn = get_connection(db_path)
    try:
        if not _is_seeded(conn):
            return {"lane": LANE_ID, "status": "not_seeded"}

        cfg = _lane_cfg()
        tickers = _mandate_tickers()
        if prices is None:
            prices = _re._get_current_prices(tickers)
        if panel is None:
            panel = _re._get_price_panel(tickers)

        current = _re._get_current_weights(conn, LANE_ID, prices)
        last_rebalance = _re._get_last_rebalance_date(conn, LANE_ID)
        notional = _re._get_portfolio_notional(conn, LANE_ID)

        meta: dict = {}
        base = _base_target(panel, meta)
        target, stopped, exit_detail = _apply_exit_overlay(conn, base, panel)
        ts = datetime.now().isoformat()

        audit = {
            "optimizer_used": meta.get("optimizer_used"),
            "optimizer_fallback": meta.get("optimizer_fallback"),
            "n_stopped": len(stopped), "stopped": stopped,
        }
        insert_audit_log(conn, ts, LANE_ID, "exit_overlay_eval", audit)

        if force_reason is not None:
            trigger, reason = True, force_reason
        elif stopped:
            trigger, reason = True, "exit_overlay"
        else:
            trigger, reason = should_rebalance(
                current, target, cfg["rebalance_trigger_drift"],
                cfg["rebalance_frequency"], last_rebalance, as_of_date,
            )

        if not trigger:
            insert_audit_log(conn, ts, LANE_ID, "no_rebalance", {"reason": reason, **audit})
            return {"lane": LANE_ID, "status": "hold", "reason": reason,
                    "n_stopped": len(stopped)}

        trades, total_cost = compute_trades(
            current, target, prices, notional,
            cfg.get("transaction_cost_bps", 5), cfg.get("slippage_bps", 1),
        )
        if stopped:
            expl = (f"Conservative-ATR rebalance ({reason}): ATR stop fired on "
                    f"{stopped} → rotated to cash; vol-capped equity sleeve.")
        else:
            expl = f"Conservative-ATR rebalance ({reason}): mandate + vol-capped sleeve."

        event_id = insert_rebalance_event(
            conn, LANE_ID, ts, reason, current, target, None, None, expl,
            config_version=get_conservative_atr_config_hash(),  # ATR hash — never ref/book
        )
        _re._apply_rebalance_positions(conn, LANE_ID, target, prices, notional,
                                       total_cost, ts)
        insert_audit_log(conn, ts, LANE_ID, "rebalance_executed", {
            "event_id": event_id, "reason": reason, "n_trades": len(trades),
            "turnover": round(estimate_turnover(current, target), 4),
            "total_cost": total_cost, "stopped": stopped, "exit_detail": exit_detail,
        })
        return {"lane": LANE_ID, "status": "rebalanced", "reason": reason,
                "event_id": event_id, "n_stopped": len(stopped), "stopped": stopped}
    finally:
        conn.close()


def mark_all_conservative_atr_lanes(db_path=None) -> dict:
    """Mark the SEEDED conservative-ATR lane to market (persist daily NAV).

    Skips the lane until it is seeded — MTM never auto-creates it (seeding is the
    attended write-path). Mirrors mark_all_book_lanes.
    """
    out: dict = {}
    for lane_id in CONSERVATIVE_ATR_LANES:
        try:
            conn = get_connection(db_path)
            try:
                seeded = conn.execute(
                    "SELECT 1 FROM paper_portfolios WHERE id = ?", (lane_id,)
                ).fetchone()
            finally:
                conn.close()
            if not seeded:
                out[lane_id] = None
                continue
            out[lane_id] = _re.mark_lane_to_market(lane_id, db_path=db_path)
        except Exception as e:
            logger.error("Conservative-ATR MTM failed for %s: %s", lane_id, e, exc_info=True)
            out[lane_id] = None
    return out
