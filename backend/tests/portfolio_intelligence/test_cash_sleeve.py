"""
Cash / T-bill sleeve (Step #1, item 3).

  - the crash overlay rotates cut equity into CASH (not just bonds),
  - the cash sleeve earns the risk-free rate (rf_daily hook),
  - cash is genuinely defensive in a rates-driven selloff where bonds fall.
"""

import numpy as np
import pandas as pd
import pytest

from backend.services.portfolio_intelligence.nav import (
    CASH_TICKER,
    nav_series,
    weights_to_shares,
)
from backend.services.portfolio_intelligence.rules import apply_crash_overlay, classify_asset


def test_cash_is_classified():
    assert classify_asset(CASH_TICKER) == "cash"


def test_crash_overlay_rotates_to_cash():
    target = {"SPY": 0.5, "XLK": 0.3, "AGG": 0.2}  # 80% equity, 20% bonds
    lane_cfg = {"crash_overlay": {"crash_prob_threshold": 0.25, "equity_cut_pct": 0.5}}
    adjusted, fired = apply_crash_overlay(target, crash_prob_3m=0.40, lane_config=lane_cfg)

    assert fired is True
    # Cut equity went to CASH, not bonds.
    assert adjusted.get(CASH_TICKER, 0.0) > 0.0
    assert adjusted["AGG"] == pytest.approx(0.2, abs=1e-9)  # bonds untouched
    # Equity roughly halved (50% cut), weights still sum to 1.
    assert adjusted["SPY"] < 0.5 and adjusted["XLK"] < 0.3
    assert sum(adjusted.values()) == pytest.approx(1.0, abs=1e-9)


def test_no_overlay_below_threshold():
    target = {"SPY": 0.8, "AGG": 0.2}
    lane_cfg = {"crash_overlay": {"crash_prob_threshold": 0.25, "equity_cut_pct": 0.5}}
    adjusted, fired = apply_crash_overlay(target, crash_prob_3m=0.10, lane_config=lane_cfg)
    assert fired is False
    assert adjusted == target


def test_cash_sleeve_earns_rf():
    dates = pd.bdate_range("2024-01-01", periods=21)
    panel = pd.DataFrame({"SPY": np.full(len(dates), 100.0)}, index=dates)  # flat equity
    # Book: 0 shares, all cash, rf 0.02%/day → NAV grows purely from rf.
    s = nav_series({}, panel, cash=10_000.0, rf_daily=0.0002)
    assert s.iloc[-1] == pytest.approx(10_000.0 * (1.0002 ** (len(dates) - 1)))
    assert s.iloc[-1] > s.iloc[0]


def test_cash_defensive_vs_long_bonds_in_rates_selloff():
    """Rates selloff: long bonds (TLT) fall; a cash sleeve does not."""
    dates = pd.bdate_range("2024-01-01", periods=60)
    # Equity flat (isolate the defensive sleeve); TLT falls 15% over the window.
    spy = np.full(len(dates), 100.0)
    tlt = np.linspace(100.0, 85.0, len(dates))
    panel = pd.DataFrame({"SPY": spy, "TLT": tlt}, index=dates)

    notional = 100_000.0
    # Book A: 50% SPY + 50% cash (earns rf). Book B: 50% SPY + 50% TLT.
    sa, ca = weights_to_shares({"SPY": 0.5, CASH_TICKER: 0.5}, {"SPY": 100.0}, notional)
    sb, cb = weights_to_shares({"SPY": 0.5, "TLT": 0.5}, {"SPY": 100.0, "TLT": 100.0}, notional)

    nav_cash = nav_series(sa, panel, cash=ca, rf_daily=0.0002)
    nav_bonds = nav_series(sb, panel, cash=cb, rf_daily=0.0002)

    # Cash sleeve held value (+rf); the long-bond sleeve lost ~7.5% of the book.
    assert nav_cash.iloc[-1] > nav_bonds.iloc[-1]
    assert nav_cash.iloc[-1] >= notional          # cash book defended principal
    assert nav_bonds.iloc[-1] < notional          # bond book fell
