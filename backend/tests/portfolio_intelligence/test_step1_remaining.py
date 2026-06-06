"""
Acceptance tests for Step #1 items 2 (replay uses nav.py) and 4 (sector map).

Item 2: the replay equity curve is produced by the shared nav.py engine
        (shares × real price). Under a uniform price move, NAV must scale by
        exactly that factor regardless of weights/rebalances — the signature of
        a real mark-to-market valuation rather than a weight-return approximation.

Item 4: the equity-sector cap clips a tech-concentrated equity book, but the
        bond sleeve (and other exempt sleeves) are NOT wrongly capped.
"""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from backend.config import paper_portfolios
from backend.services.portfolio_intelligence.market_data_wrapper import MarketDataAtTimestamp
from backend.services.portfolio_intelligence.replay import ReplayEngine
from backend.services.portfolio_intelligence.rules import (
    _get_sleeve_tickers,
    enforce_position_limits,
    lane_sector_map,
)


def _uniform_panel(start="2023-01-02", end="2024-06-28", daily=0.0008):
    """Every ticker follows the SAME path → value scales with price, not weights."""
    sleeves = _get_sleeve_tickers(paper_portfolios["universe"])
    tickers = sleeves["equity"] + sleeves["bond"] + sleeves["alternative"]
    dates = pd.bdate_range(start, end)
    series = 100.0 * np.cumprod(1 + np.full(len(dates), daily))
    return pd.DataFrame({t: series.copy() for t in tickers}, index=dates)


# ── Item 2: replay equity curve == nav.py shares × price ─────────────────


@patch("backend.services.portfolio_intelligence.replay.ReplayEngine._get_ticker_universe_prices")
def test_replay_equity_curve_is_nav_shares_times_price(mock_prices):
    panel = _uniform_panel()
    mock_prices.return_value = panel
    engine = ReplayEngine(wrapper=MarketDataAtTimestamp(panel))

    result = engine.run(
        "conservative", "2023-01-02", "2024-06-28",
        initial_notional=100_000.0, crash_prob_override=0.05,  # no guard
    )

    # The equity curve ends at the LAST CHECK DATE (monthly), not the panel end,
    # so reference the uniform price at that date. NAV = shares × price must
    # scale by exactly that ratio regardless of weights/rebalances — within a
    # hair for the tiny one-off initialization cost.
    last_date = pd.Timestamp(result.equity_curve[-1]["date"])
    p_last = float(panel.loc[:last_date].iloc[-1, 0])
    p0 = float(panel.iloc[0, 0])
    final_nav = result.equity_curve[-1]["value"]
    assert final_nav == pytest.approx(100_000.0 * p_last / p0, rel=5e-3)
    assert len(result.equity_curve) > 0


# ── Item 4: sector cap clips equity sector, exempts bond sleeve ──────────


def test_sector_cap_clips_tech_but_not_bonds():
    smap = lane_sector_map()
    weights = {
        "XLK": 0.25, "AAPL": 0.20,   # Technology = 0.45
        "XLV": 0.10, "JNJ": 0.05,    # Healthcare = 0.15
        "XLF": 0.05, "JPM": 0.05,    # Financials = 0.10
        "AGG": 0.20, "TLT": 0.10,    # Bonds      = 0.30 (EXEMPT)
    }
    out = enforce_position_limits(weights, max_single_name=0.5, max_sector=0.25,
                                  sector_map=smap)

    tech = out["XLK"] + out["AAPL"]
    bonds = out["AGG"] + out["TLT"]
    assert tech <= 0.25 + 1e-6, f"tech not clipped: {tech}"
    # Bond sleeve preserved — NOT clipped as if it were one equity sector.
    assert bonds == pytest.approx(0.30, abs=1e-3), f"bonds wrongly capped: {bonds}"
    assert abs(sum(out.values()) - 1.0) < 1e-6


def test_broad_equity_etf_is_exempt_from_sector_cap():
    """A diversified SPY weight must not be treated as a single equity sector."""
    smap = lane_sector_map()
    assert "SPY" not in smap and "QQQ" not in smap and "AGG" not in smap
    assert smap["XLK"] == "Technology"  # sector ETFs ARE classified
    weights = {"SPY": 0.6, "AGG": 0.4}
    out = enforce_position_limits(weights, max_single_name=1.0, max_sector=0.25,
                                  sector_map=smap)
    # Neither is an equity sector → both pass through unclipped.
    assert out["SPY"] == pytest.approx(0.6, abs=1e-6)
    assert out["AGG"] == pytest.approx(0.4, abs=1e-6)
