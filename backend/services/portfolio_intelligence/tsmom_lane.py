"""
TRIAL-TSMOM-XA — overlay + 60/40 control lanes: attended seeding + monthly
signal rebalance.

The `tsmom-overlay` lane runs the module-confirmed INSTR-TSMOM-XA spec
verbatim (50% SPY core + 50% cross-asset 12-1 TSMOM sleeve, vol-sized,
monthly): the first macro instrument to survive the explore/confirm wall
(2020 +9.2%, 2022 ≈flat, overlay maxDD −18.8% vs SPY −33.7% held-out).
`tsmom-6040-control` is the frozen 60/40 SPY/TLT control — the trial's
primary metric is the PAIRWISE drawdown comparison (Goal-B: defensive
diversifier, NOT beat-SPY). Canonical doc: docs/TRIALS/TRIAL-TSMOM-XA.md.

⚠️ NEVER-SHORTS EXEMPTION (declared): the sleeve takes short legs (negative
shares; proceeds in CASH). Murat authorized the paper-only exemption
2026-07-26 (attended). `_apply_rebalance_positions(allow_negative=True)` is
used ONLY here.

Entry points (the smq_lane / exit_lane pattern):
  • ``seed_tsmom_lanes``     — ATTENDED write-path (AEGIS_SEED_TSMOM_XA=1),
                               idempotent per lane, registers both trials.
  • ``run_tsmom_check``      — daily; NO-OP (not_seeded) until the attended
                               seed; rebalances on the first check of a new
                               calendar month; refuses on missing prices.
  • ``mark_all_tsmom_lanes`` — hourly MTM, skip-until-seeded.

HARD CONSTRAINTS: arms nothing; never touches reference/book/ATR/SMQ lanes
(own config hash); no reconstructed past (inception = seed day); params
frozen in tsmom_xa_lanes.yaml (part of the hash).
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime

from backend.config import tsmom_xa_lanes
from backend.db import (
    get_connection,
    get_tsmom_config_hash,
    init_db,
    insert_audit_log,
    insert_rebalance_event,
)
from backend.services.portfolio_intelligence import reference_engine as _re
from backend.services.portfolio_intelligence.nav import CASH_TICKER
from backend.services.portfolio_intelligence.rebalancer import (
    compute_trades,
    estimate_turnover,
)
from backend.services.portfolio_intelligence.rules import TSMOM_LANES

logger = logging.getLogger(__name__)

OVERLAY_LANE = "tsmom-overlay"
CONTROL_LANE = "tsmom-6040-control"


def _lane_cfg(lane_id: str) -> dict:
    cfg = tsmom_xa_lanes.get(lane_id)
    if not cfg or "purpose" not in cfg:
        raise ValueError(f"TSMOM lane config missing/invalid: {lane_id}")
    return cfg


def _is_seeded(conn, lane_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM paper_portfolios WHERE id = ?", (lane_id,)
    ).fetchone() is not None


# ────────────────────────────── frozen signal ──────────────────────────────

def compute_sleeve_weights(panel, as_of: date) -> tuple[dict[str, float], dict]:
    """The frozen INSTR-TSMOM-XA sleeve, computed at the last trading day of
    the month BEFORE `as_of` (signal-at-month-end-close → trade-next-day at
    lane cadence). Returns (signed sleeve weights, detail). Raises ValueError
    when the panel cannot support the spec — callers HOLD loudly, they never
    guess."""
    cfg = _lane_cfg(OVERLAY_LANE)
    assets = list(cfg["assets"])
    lookback = int(cfg["lookback_days"])
    skip = int(cfg["skip_days"])
    vol_win = int(cfg["vol_window_days"])
    vol_target = float(cfg["vol_target"])
    cap = float(cfg["leverage_cap"])

    if panel is None or getattr(panel, "empty", True):
        raise ValueError("no price panel")
    cols = [a for a in assets if a in panel.columns]
    if len(cols) != len(assets):
        raise ValueError(f"panel missing assets: {sorted(set(assets) - set(cols))}")

    month_key = (as_of.year, as_of.month)
    prior = [d for d in panel.index
             if (d.year, d.month) < month_key]
    if not prior:
        raise ValueError("panel has no data before the current month")
    me = prior[-1]
    pos = panel.index.get_loc(me)
    if pos < lookback + 1:
        raise ValueError(f"panel too short: {pos} rows before month-end, "
                         f"need {lookback + 1}")

    sleeve: dict[str, float] = {}
    detail: dict = {"month_end": str(getattr(me, "date", lambda: me)()),
                    "signals": {}, "vols": {}}
    raw: dict[str, float] = {}
    for a in assets:
        c = panel[a]
        c_far, c_near, c_me = c.iloc[pos - lookback], c.iloc[pos - skip], c.iloc[pos]
        window = c.iloc[max(pos - vol_win, 0): pos + 1].pct_change().dropna()
        if (any(x is None or (isinstance(x, float) and math.isnan(x))
                for x in (c_far, c_near, c_me)) or len(window) < vol_win // 2):
            continue
        sig = 1.0 if c_near / c_far - 1 > 0 else (-1.0 if c_near / c_far - 1 < 0 else 0.0)
        vol = float(window.std(ddof=1)) * math.sqrt(252)
        if not (vol > 0):
            continue
        raw[a] = sig * min(vol_target / vol, cap)
        detail["signals"][a] = sig
        detail["vols"][a] = round(vol, 4)
    if not raw:
        raise ValueError("no asset produced a valid signal")
    k = len(raw)
    sleeve = {a: w / k for a, w in raw.items()}
    detail["n_active"] = k
    return sleeve, detail


def overlay_target(sleeve: dict[str, float]) -> dict[str, float]:
    """50% SPY core + 50% sleeve, SPY legs netted; CASH = 1 − Σ assets
    (short proceeds raise cash)."""
    cfg = _lane_cfg(OVERLAY_LANE)
    core_w, sleeve_w = float(cfg["core_weight"]), float(cfg["sleeve_weight"])
    target: dict[str, float] = {"SPY": core_w}
    for a, w in sleeve.items():
        target[a] = target.get(a, 0.0) + sleeve_w * w
    target[CASH_TICKER] = 1.0 - sum(target.values())
    return {t: w for t, w in target.items() if abs(w) > 1e-9}


def control_target() -> dict[str, float]:
    return dict(_lane_cfg(CONTROL_LANE)["weights"])


def _target_for(lane_id: str, panel, as_of: date) -> tuple[dict[str, float], dict]:
    if lane_id == CONTROL_LANE:
        return control_target(), {"kind": "static_6040"}
    sleeve, detail = compute_sleeve_weights(panel, as_of)
    return overlay_target(sleeve), detail


def _new_month_since(last_rebalance: date | None, as_of: date) -> bool:
    if last_rebalance is None:
        return True
    return (as_of.year, as_of.month) > (last_rebalance.year, last_rebalance.month)


# ────────────────────────────── seed (attended) ──────────────────────────────

def seed_tsmom_lanes(db_path=None, prices: dict | None = None, panel=None) -> dict:
    """Seed BOTH TSMOM lanes at today's prices, $100k each, shared isolated
    hash. ATTENDED write-path (env-gated). Idempotent per lane. The overlay
    seeds at the prevailing month-end signal (the book the strategy would
    already hold — declared in the trial doc). REFUSES on any missing price
    or an uncomputable signal: no partial/guessed book under a signed sleeve.
    """
    notional = float((tsmom_xa_lanes.get("inception") or {}).get(
        "notional_usd", 100_000.0))
    assets = list(_lane_cfg(OVERLAY_LANE)["assets"])
    init_db(db_path)

    if panel is None:
        panel = _re._get_price_panel(assets)
    if prices is None:
        prices = _re._get_current_prices(assets)

    today = date.today()
    config_hash = get_tsmom_config_hash()
    results: dict = {}
    seeded_lanes: list[str] = []

    conn = get_connection(db_path)
    try:
        for lane_id in (OVERLAY_LANE, CONTROL_LANE):
            if _is_seeded(conn, lane_id):
                logger.info("TSMOM lane %s already seeded — skipping", lane_id)
                results[lane_id] = {"seeded": False, "reason": "already_exists"}
                continue

            target, detail = _target_for(lane_id, panel, today)
            legs = [t for t in target if t != CASH_TICKER]
            missing = [t for t in legs if not (prices.get(t) and prices[t] > 0)]
            if missing:
                raise ValueError(
                    f"TSMOM seed REFUSED for {lane_id}: no live price for "
                    f"{missing} — a signed book is never seeded on guesses")

            ts = datetime.now().isoformat()
            conn.execute(
                "INSERT INTO paper_portfolios (id, inception_date, "
                "inception_value, config_version) VALUES (?, ?, ?, ?)",
                (lane_id, today.isoformat(), notional, config_hash),
            )
            for ticker, weight in target.items():
                px = 1.0 if ticker == CASH_TICKER else prices[ticker]
                conn.execute(
                    "INSERT INTO paper_positions (portfolio_id, ticker, shares, "
                    "cost_basis, opened_at) VALUES (?, ?, ?, ?, ?)",
                    (lane_id, ticker, (weight * notional) / px, px,
                     today.isoformat()),
                )
            conn.commit()

            insert_rebalance_event(
                conn, lane_id, ts, "initialization", {}, target, None, None,
                f"TSMOM-XA inception at ${notional:,.0f} ({lane_id}): "
                "frozen INSTR-TSMOM-XA spec, pairwise trial vs 60/40 control; "
                "earliest decision 24mo from inception (TRIAL-TSMOM-XA).",
                config_version=config_hash,
            )
            insert_audit_log(conn, ts, lane_id, "tsmom_seeded", {
                "notional": notional, "target": target, "detail": detail,
                "config_hash": config_hash,
            })
            logger.info("Seeded TSMOM lane %s: %s", lane_id,
                        {t: round(w, 4) for t, w in target.items()})
            results[lane_id] = {"seeded": True, "target": target,
                                "detail": detail}
            seeded_lanes.append(lane_id)
    finally:
        conn.close()

    # Register AFTER closing the seed connection (nested-write-conn rule).
    for lane_id in seeded_lanes:
        _re._register_lane_trial(lane_id, config_hash, db_path=db_path)
    return {"lanes": results, "config_hash": config_hash}


# ────────────────────────────── daily check ──────────────────────────────

def run_tsmom_check(db_path=None, as_of_date=None, panel=None,
                    prices=None, force_reason=None) -> dict:
    """Monthly signal rebalance for both TSMOM lanes. NO-OP (not_seeded)
    until the attended seed. Trigger: first daily check of a new calendar
    month (frozen cadence — drift disabled by spec). Missing prices or an
    uncomputable signal HOLD loudly (degraded clause), never guess."""
    as_of_date = as_of_date or date.today()
    out: dict = {}
    assets = list(_lane_cfg(OVERLAY_LANE)["assets"])

    conn = get_connection(db_path)
    try:
        for lane_id in (OVERLAY_LANE, CONTROL_LANE):
            if not _is_seeded(conn, lane_id):
                out[lane_id] = {"status": "not_seeded"}
                continue

            last_rebalance = _re._get_last_rebalance_date(conn, lane_id)
            if force_reason is None and not _new_month_since(last_rebalance,
                                                             as_of_date):
                out[lane_id] = {"status": "hold", "reason": "same_month"}
                continue

            if prices is None:
                prices = _re._get_current_prices(assets)
            if panel is None:
                panel = _re._get_price_panel(assets)

            ts = datetime.now().isoformat()
            try:
                target, detail = _target_for(lane_id, panel, as_of_date)
            except ValueError as e:
                insert_audit_log(conn, ts, lane_id, "tsmom_signal_failed",
                                 {"error": str(e)})
                logger.warning("TSMOM %s: signal failed (%s) — HOLDING", lane_id, e)
                out[lane_id] = {"status": "hold", "reason": f"signal_failed: {e}"}
                continue

            legs = [t for t in target if t != CASH_TICKER]
            missing = [t for t in legs if not (prices.get(t) and prices[t] > 0)]
            if missing:
                insert_audit_log(conn, ts, lane_id, "tsmom_prices_missing",
                                 {"missing": missing})
                logger.warning("TSMOM %s: no live price for %s — HOLDING",
                               lane_id, missing)
                out[lane_id] = {"status": "hold", "reason": f"prices_missing: {missing}"}
                continue

            cfg = _lane_cfg(lane_id)
            current = _re._get_current_weights(conn, lane_id, prices)
            notional = _re._get_portfolio_notional(conn, lane_id, prices)
            reason = force_reason or "monthly_signal"
            trades, total_cost = compute_trades(
                current, target, prices, notional,
                cfg.get("transaction_cost_bps", 5), cfg.get("slippage_bps", 1),
            )
            event_id = insert_rebalance_event(
                conn, lane_id, ts, reason, current, target, None, None,
                f"TSMOM-XA rebalance ({reason}): {detail.get('kind', 'signal')} "
                f"{detail.get('signals', '')}",
                config_version=get_tsmom_config_hash(),
            )
            _re._apply_rebalance_positions(
                conn, lane_id, target, prices, notional, total_cost, ts,
                allow_negative=True,
            )
            insert_audit_log(conn, ts, lane_id, "rebalance_executed", {
                "event_id": event_id, "reason": reason,
                "turnover": round(estimate_turnover(current, target), 4),
                "total_cost": total_cost, "detail": detail,
            })
            out[lane_id] = {"status": "rebalanced", "reason": reason,
                            "event_id": event_id,
                            "target": {t: round(w, 4) for t, w in target.items()}}
    finally:
        conn.close()
    return out


# ────────────────────────────── hourly MTM ──────────────────────────────

def mark_all_tsmom_lanes(db_path=None) -> dict:
    """MTM the SEEDED TSMOM lanes; skip until the attended seed runs."""
    out: dict = {}
    for lane_id in TSMOM_LANES:
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
            logger.error("TSMOM MTM failed for %s: %s", lane_id, e, exc_info=True)
            out[lane_id] = None
    return out
