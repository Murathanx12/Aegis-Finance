"""
Active management for the P1 #6 book lanes (mirror + conviction).

Mirror — rebalanced by the ALREADY-ADOPTED config-v2 HRP rules over the book's
own names (leakage-safe as-of panel, monthly cadence + drift), reusing the frozen
engine's HRP + rebalance-write helpers. Every segment boundary is stamped with
the BOOK config hash (get_book_config_hash) — NEVER the reference-lane hash, so
the 4 reference lanes are provably untouched.

Conviction — positions move ONLY when Murat logs a personal_decision. Each new
decision updates the REAL share-count book (seed counts + deltas); the lane is
rebalanced to that book's current-market-value weights. This tracks Murat's
actual allocation at the lanes' $100k scale (apples-to-apples vs the rules
baselines), rather than dumping raw share counts onto a normalized lane.

Both lanes are DORMANT until wired to the scheduler (gated on the final go) and
then HOLD until their first trigger (mirror: monthly/drift; conviction: a logged
decision). No path here arms a crash overlay or auto-adopts a rule.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime

from backend.config import book_lanes
from backend.db import (
    get_book_config_hash,
    get_connection,
    insert_audit_log,
    insert_rebalance_event,
)
from backend.services.portfolio_intelligence import reference_engine as _re
from backend.services.portfolio_intelligence.rebalancer import (
    compute_trades,
    estimate_turnover,
)
from backend.services.portfolio_intelligence.rules import (
    _equal_weight,
    _hrp_equity_weights,
    compute_book_mv_weights,
    enforce_position_limits,
    should_rebalance,
)

logger = logging.getLogger(__name__)


def _book_tickers() -> list[str]:
    return list((book_lanes.get("holdings") or {}).keys())


def _is_seeded(conn, lane_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM paper_portfolios WHERE id = ?", (lane_id,)
    ).fetchone() is not None


def _optimizer_audit(meta: dict) -> dict:
    """Compact, human-readable record of the optimizer decision for the audit log
    — shows when HRP is actually biting vs falling back, and which names dropped."""
    return {
        "optimizer_used": meta.get("optimizer_used"),
        "optimizer_fallback": meta.get("optimizer_fallback"),
        "dropped": meta.get("optimizer_dropped", {}),
        "as_of": meta.get("optimizer_as_of"),
        "n_obs": meta.get("optimizer_n_obs"),
    }


# ── Mirror lane ───────────────────────────────────────────────────────────────


def _mirror_target_weights(panel, meta: dict) -> dict[str, float]:
    """HRP over the book's names (all-equity → target_eq=1.0), then the mirror's
    position limits. Loud equal-weight fallback over the priced names if HRP
    can't produce valid weights — meta carries the reason + dropped names."""
    tickers = _book_tickers()
    hrp = _hrp_equity_weights(tickers, panel, 1.0, meta) if panel is not None else None
    if hrp:
        weights = hrp
    else:
        meta.setdefault("optimizer_fallback", "no as-of price panel")
        weights = _equal_weight(tickers, 1.0)
    cfg = book_lanes["mirror"]
    return enforce_position_limits(
        weights, cfg["max_single_name"], cfg["max_sector"], _re._get_sector_map()
    )


def run_mirror_check(db_path=None, as_of_date=None, force_reason=None,
                     panel=None, prices=None) -> dict:
    """Mirror lane: rebalance to config-v2 HRP weights over the book on the
    monthly cadence (or drift). Boundary stamped with the BOOK hash. Returns a
    status dict; HOLDS (no write) when no trigger fires."""
    lane_id = "mirror"
    as_of_date = as_of_date or date.today()
    conn = get_connection(db_path)
    try:
        if not _is_seeded(conn, lane_id):
            return {"lane": lane_id, "status": "not_seeded"}

        tickers = _book_tickers()
        if prices is None:
            prices = _re._get_current_prices(tickers)
        current = _re._get_current_weights(conn, lane_id, prices)
        last_rebalance = _re._get_last_rebalance_date(conn, lane_id)
        notional = _re._get_portfolio_notional(conn, lane_id)

        meta: dict = {}
        if panel is None:
            panel = _re._get_price_panel(tickers)
        target = _mirror_target_weights(panel, meta)
        opt = _optimizer_audit(meta)
        cfg = book_lanes["mirror"]
        ts = datetime.now().isoformat()

        # Always record the optimizer decision (biting vs fallback + dropped).
        insert_audit_log(conn, ts, lane_id, "book_optimizer_eval", opt)

        if force_reason is not None:
            trigger, reason = True, force_reason
        else:
            trigger, reason = should_rebalance(
                current, target, cfg["rebalance_trigger_drift"],
                cfg["rebalance_frequency"], last_rebalance, as_of_date,
            )
        if not trigger:
            insert_audit_log(conn, ts, lane_id, "no_rebalance", {"reason": reason, **opt})
            return {"lane": lane_id, "status": "hold", "reason": reason, "optimizer": opt}

        trades, total_cost = compute_trades(
            current, target, prices, notional,
            cfg.get("transaction_cost_bps", 5), cfg.get("slippage_bps", 1),
        )
        if meta.get("optimizer_used"):
            expl = (f"Mirror rebalance ({reason}): HRP over "
                    f"{meta.get('optimizer_n_obs')} obs as-of {meta.get('optimizer_as_of')}")
        else:
            expl = (f"Mirror rebalance ({reason}): EQUAL-WEIGHT FALLBACK — "
                    f"{meta.get('optimizer_fallback')}")
        if opt["dropped"]:
            expl += f"; dropped {sorted(opt['dropped'])}"

        event_id = insert_rebalance_event(
            conn, lane_id, ts, reason, current, target, None, None, expl,
            config_version=get_book_config_hash(),  # BOOK hash — never the ref-lane hash
        )
        _re._apply_rebalance_positions(conn, lane_id, target, prices, notional,
                                       total_cost, ts)
        insert_audit_log(conn, ts, lane_id, "rebalance_executed", {
            "event_id": event_id, "reason": reason, "n_trades": len(trades),
            "turnover": round(estimate_turnover(current, target), 4),
            "total_cost": total_cost, **opt,
        })
        return {"lane": lane_id, "status": "rebalanced", "reason": reason,
                "event_id": event_id, "optimizer": opt}
    finally:
        conn.close()


# ── Conviction lane ───────────────────────────────────────────────────────────


def _real_book_after_decisions(rows) -> dict[str, float]:
    """The real share-count book = seed counts + applied decision deltas.
    enter/add: +|delta|; trim: -|delta| (floored at 0); exit: 0. Zero/closed
    names are dropped."""
    book = {t: float(s) for t, s in (book_lanes.get("holdings") or {}).items()}
    for r in rows:
        t, action = r["ticker"], r["action"]
        delta = abs(float(r["shares_delta"] or 0.0))
        cur = book.get(t, 0.0)
        if action in ("enter", "add"):
            book[t] = cur + delta
        elif action == "trim":
            book[t] = max(cur - delta, 0.0)
        elif action == "exit":
            book[t] = 0.0
    return {t: s for t, s in book.items() if s > 0}


def apply_conviction_decisions(db_path=None, as_of_date=None, prices=None) -> dict:
    """Conviction lane: apply any not-yet-applied personal_decisions by recomputing
    the real book (seed + deltas) -> current-MV weights -> rebalance the $100k lane
    to them. Idempotent (each decision applied once, tracked in the audit log)."""
    lane_id = "conviction"
    as_of_date = as_of_date or date.today()
    conn = get_connection(db_path)
    try:
        if not _is_seeded(conn, lane_id):
            return {"lane": lane_id, "status": "not_seeded"}

        applied_ids = set()
        for r in conn.execute(
            "SELECT payload FROM audit_log WHERE portfolio_id = ? "
            "AND event_type = 'conviction_applied'", (lane_id,)
        ).fetchall():
            try:
                applied_ids.add(json.loads(r["payload"]).get("decision_id"))
            except Exception:
                pass

        all_rows = conn.execute(
            "SELECT id, ticker, action, shares_delta FROM personal_decisions "
            "ORDER BY id ASC"
        ).fetchall()
        new = [r for r in all_rows if r["id"] not in applied_ids]
        if not new:
            return {"lane": lane_id, "status": "no_new_decisions"}

        real_book = _real_book_after_decisions(all_rows)
        tickers = list(real_book.keys())
        if prices is None:
            prices = _re._get_current_prices(tickers)
        try:
            target = compute_book_mv_weights(real_book, prices)
        except ValueError as e:
            # Can't fully price the post-decision book → do NOT trade on junk.
            ts = datetime.now().isoformat()
            logger.warning("Conviction: cannot reweight (%s) — decisions NOT applied", e)
            insert_audit_log(conn, ts, lane_id, "conviction_reweight_skipped",
                             {"error": str(e), "pending_decision_ids": [r["id"] for r in new]})
            return {"lane": lane_id, "status": "skipped_unpriceable",
                    "pending": [r["id"] for r in new]}

        current = _re._get_current_weights(conn, lane_id, prices)
        notional = _re._get_portfolio_notional(conn, lane_id)
        cfg = book_lanes["conviction"]
        trades, total_cost = compute_trades(
            current, target, prices, notional,
            cfg.get("transaction_cost_bps", 5), cfg.get("slippage_bps", 1),
        )
        ts = datetime.now().isoformat()
        decided = ", ".join(f"{r['action']} {r['ticker']}" for r in new)
        expl = (f"Conviction update: applied {len(new)} decision(s) [{decided}] "
                "-> real-book current-MV weights")
        event_id = insert_rebalance_event(
            conn, lane_id, ts, "conviction_decision", current, target, None, None,
            expl, config_version=get_book_config_hash(),
        )
        _re._apply_rebalance_positions(conn, lane_id, target, prices, notional,
                                       total_cost, ts)
        for r in new:
            insert_audit_log(conn, ts, lane_id, "conviction_applied", {
                "decision_id": r["id"], "ticker": r["ticker"],
                "action": r["action"], "shares_delta": r["shares_delta"],
                "event_id": event_id,
            })
        return {"lane": lane_id, "status": "applied", "n": len(new),
                "decision_ids": [r["id"] for r in new], "event_id": event_id}
    finally:
        conn.close()


def run_all_book_management(db_path=None) -> dict:
    """Run book-lane management: conviction applies new decisions, mirror checks
    its cadence. DORMANT until wired to the scheduler (gated on the final go);
    both lanes HOLD until their trigger."""
    return {
        "conviction": apply_conviction_decisions(db_path=db_path),
        "mirror": run_mirror_check(db_path=db_path),
    }
