"""
TRIAL-SMQ-FWD — smallmid-quality lane: attended seeding + MTM.

The `smallmid-quality` lane holds the BRAIN-007 composite book (top-30 by mean
winsorized z of PIT gross profitability + opportunistic-insider flag, formed in
the brain module and promoted as smallmid_quality_lanes.yaml holdings). Equal
weight at seed, buy-and-hold — there is NO daily management path: the composite
did the picking, the quarterly artifact refresh (a stamped config-version
change) does the re-picking. Benchmark: IWM (see the trial doc's decision rule).

Two entry points, mirroring exit_lane.py / book_management.py:

  • ``seed_smallmid_quality_lane`` — ATTENDED write-path, invoked only by the
    env-gated startup hook (AEGIS_SEED_SMALLMID_QUALITY=1). Prices the 30
    holdings, equal-weights $100k, stamps the ISOLATED SMQ config hash, and
    registers TRIAL-SMQ-FWD. Idempotent. ≤3 unpriceable tickers drop LOUDLY
    (audit + result); >3 → refuses (fail-loud, no partial book by stealth).

  • ``mark_all_smq_lanes`` — hourly MTM, skip-until-seeded.

HARD CONSTRAINTS: arms nothing; never touches reference/book/ATR lanes
(separate config hash); no reconstructed past (inception = seed day).
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from backend.config import smallmid_quality_lanes
from backend.db import (
    get_connection,
    get_smq_config_hash,
    init_db,
    insert_audit_log,
    insert_rebalance_event,
)
from backend.services.portfolio_intelligence import reference_engine as _re
from backend.services.portfolio_intelligence.nav import CASH_TICKER
from backend.services.portfolio_intelligence.rules import SMQ_LANES

logger = logging.getLogger(__name__)

LANE_ID = "smallmid-quality"
MAX_DROPPED_TICKERS = 3


def _lane_cfg() -> dict:
    cfg = smallmid_quality_lanes.get(LANE_ID)
    if not cfg or "purpose" not in cfg or not cfg.get("holdings"):
        raise ValueError(f"smallmid-quality lane config missing/invalid: {LANE_ID}")
    return cfg


def _is_seeded(conn) -> bool:
    return conn.execute(
        "SELECT 1 FROM paper_portfolios WHERE id = ?", (LANE_ID,)
    ).fetchone() is not None


def seed_smallmid_quality_lane(db_path=None, prices: dict | None = None) -> dict:
    """Seed the smallmid-quality lane: EW book at TODAY's prices, $100k notional.

    ATTENDED write-path (env-gated). Idempotent — an existing lane row is left
    untouched. Unpriceable tickers (no positive price) are dropped and logged;
    more than MAX_DROPPED_TICKERS unpriceable → the seed REFUSES so a broken
    price feed cannot silently seed a partial book.
    """
    cfg = _lane_cfg()
    holdings: list[str] = list(dict.fromkeys(cfg["holdings"]))
    notional = float((smallmid_quality_lanes.get("inception") or {})
                     .get("notional_usd", 100_000.0))

    init_db(db_path)
    conn = get_connection(db_path)
    try:
        if _is_seeded(conn):
            logger.info("Smallmid-quality lane already seeded — skipping (idempotent)")
            return {"lane_id": LANE_ID, "seeded": False, "reason": "already_exists"}

        if prices is None:
            prices = _re._get_current_prices(holdings)
        priced = [t for t in holdings if prices.get(t) and prices[t] > 0]
        dropped = [t for t in holdings if t not in priced]
        if len(dropped) > MAX_DROPPED_TICKERS:
            raise ValueError(
                f"smallmid-quality seed REFUSED: {len(dropped)} of "
                f"{len(holdings)} holdings unpriceable ({dropped}) — "
                f"max allowed {MAX_DROPPED_TICKERS}"
            )

        weight = 1.0 / len(priced)
        today = date.today().isoformat()
        config_hash = get_smq_config_hash()
        ts = datetime.now().isoformat()

        conn.execute(
            "INSERT INTO paper_portfolios (id, inception_date, inception_value, "
            "config_version) VALUES (?, ?, ?, ?)",
            (LANE_ID, today, notional, config_hash),
        )
        for ticker in priced:
            px = prices[ticker]
            conn.execute(
                "INSERT INTO paper_positions (portfolio_id, ticker, shares, "
                "cost_basis, opened_at) VALUES (?, ?, ?, ?, ?)",
                (LANE_ID, ticker, (weight * notional) / px, px, today),
            )
        conn.commit()

        weights = {t: weight for t in priced}
        insert_rebalance_event(
            conn, LANE_ID, ts, "initialization", {}, weights, None, None,
            f"Smallmid-quality inception at ${notional:,.0f} notional: BRAIN-007 "
            f"composite top-30 EW buy-and-hold ({len(priced)} priced"
            + (f", dropped {dropped}" if dropped else "")
            + "). Benchmark IWM; earliest decision 2028-07-22 (TRIAL-SMQ-FWD).",
            config_version=config_hash,
        )
        insert_audit_log(conn, ts, LANE_ID, "smq_seeded", {
            "notional": notional, "n_positions": len(priced),
            "dropped_unpriceable": dropped, "config_hash": config_hash,
            "purpose": cfg["purpose"],
        })
        if dropped:
            logger.warning("Smallmid-quality seeded with %d dropped tickers: %s",
                           len(dropped), dropped)
        logger.info("Seeded smallmid-quality lane: %d positions, $%s notional",
                    len(priced), f"{notional:,.0f}")
        result = {"lane_id": LANE_ID, "seeded": True, "notional": notional,
                  "n_positions": len(priced), "dropped": dropped}
    finally:
        conn.close()

    # Register AFTER closing the seed connection (nested-write-conn rule).
    _re._register_lane_trial(LANE_ID, config_hash, db_path=db_path)
    return result


def mark_all_smq_lanes(db_path=None) -> dict:
    """MTM the SEEDED smallmid-quality lane; skip until the attended seed runs."""
    out: dict = {}
    for lane_id in SMQ_LANES:
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
            logger.error("SMQ MTM failed for %s: %s", lane_id, e, exc_info=True)
            out[lane_id] = None
    return out
