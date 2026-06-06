"""
Live mark-to-market persistence (Step #1, item 1 — the real fix for Issue 7).

Acceptance:
  - a lane's live NAV CHANGES when prices change (it actually marks to market),
  - daily NAV rows persist to paper_nav, stamped with config_version.
"""

from datetime import date

import pytest

from backend.config import paper_portfolios
from backend.db import get_config_hash, get_connection, get_nav_series, init_db
from backend.services.portfolio_intelligence.reference_engine import (
    initialize_lane,
    mark_lane_to_market,
)
from backend.services.portfolio_intelligence.rules import _get_sleeve_tickers


def _universe_prices(value: float) -> dict:
    sleeves = _get_sleeve_tickers(paper_portfolios["universe"])
    tickers = sleeves["equity"] + sleeves["bond"] + sleeves["alternative"]
    return {t: value for t in tickers}


def test_live_nav_moves_and_persists(tmp_path):
    db = tmp_path / "pi.db"
    init_db(db)

    p1 = _universe_prices(100.0)
    initialize_lane("balanced", notional=100_000.0, db_path=db, prices=p1)

    # Mark at entry prices → NAV ≈ notional.
    nav1 = mark_lane_to_market("balanced", prices=p1, as_of_date=date(2026, 6, 1), db_path=db)
    assert nav1 == pytest.approx(100_000.0, rel=1e-3)

    # Every price +10% → NAV must move up ~10% (it genuinely marks to market).
    p2 = _universe_prices(110.0)
    nav2 = mark_lane_to_market("balanced", prices=p2, as_of_date=date(2026, 6, 2), db_path=db)
    assert nav2 > nav1
    assert nav2 == pytest.approx(110_000.0, rel=1e-2)

    # Two daily rows persisted, stamped with the current config_version.
    conn = get_connection(db)
    try:
        series = get_nav_series(conn, "balanced")
    finally:
        conn.close()
    assert len(series) == 2
    assert {r["date"] for r in series} == {"2026-06-01", "2026-06-02"}
    assert all(r["config_version"] == get_config_hash() for r in series)


def test_mark_lane_with_no_positions_returns_none(tmp_path):
    db = tmp_path / "pi.db"
    init_db(db)
    # No initialize_lane → _ensure_lane_initialized would create it; instead
    # check the empty-book guard directly by marking a lane with a price map
    # but force-empty positions via a fresh lane id is not possible, so we rely
    # on initialize then closing all positions. Simpler: a lane that initializes
    # then has its positions cleared.
    initialize_lane("conservative", db_path=db, prices=_universe_prices(100.0))
    conn = get_connection(db)
    conn.execute("UPDATE paper_positions SET closed_at = '2026-06-01' WHERE portfolio_id='conservative'")
    conn.commit()
    conn.close()
    assert mark_lane_to_market("conservative", prices=_universe_prices(100.0),
                               as_of_date=date(2026, 6, 3), db_path=db) is None
