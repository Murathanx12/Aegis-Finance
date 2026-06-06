"""
Tests for the shared NAV engine (nav.py) — the "one engine, two modes" core.

Acceptance criteria for Step #1:
  - live and replay produce IDENTICAL NAV from identical inputs (one engine)
  - no-look-ahead: a date's NAV depends only on prices up to that date
"""

import numpy as np
import pandas as pd
import pytest

from backend.services.portfolio_intelligence.nav import (
    CASH_TICKER,
    mark_to_market,
    nav_series,
    weights_to_shares,
)


def _panel(n=12, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-01", periods=n)
    a = 100 * np.cumprod(1 + rng.normal(0.001, 0.01, n))
    b = 50 * np.cumprod(1 + rng.normal(0.0005, 0.012, n))
    return pd.DataFrame({"A": a, "B": b}, index=idx)


def test_mark_to_market_basic():
    nav = mark_to_market({"A": 10, "B": 5}, {"A": 100.0, "B": 50.0}, cash=200.0)
    assert nav == pytest.approx(10 * 100 + 5 * 50 + 200)


def test_mark_to_market_skips_unpriceable():
    nav = mark_to_market({"A": 10, "B": 5}, {"A": 100.0}, cash=0.0)  # B has no price
    assert nav == pytest.approx(1000.0)


def test_weights_to_shares_conserves_notional():
    prices = {"A": 100.0, "B": 50.0}
    shares, cash = weights_to_shares({"A": 0.6, "B": 0.4}, prices, notional=10_000)
    # NAV at entry prices must equal the notional exactly.
    assert mark_to_market(shares, prices, cash) == pytest.approx(10_000)


def test_unpriceable_weight_falls_through_to_cash():
    prices = {"A": 100.0}  # B unpriceable
    shares, cash = weights_to_shares({"A": 0.5, "B": 0.5}, prices, 10_000)
    assert mark_to_market(shares, prices, cash) == pytest.approx(10_000)
    assert cash == pytest.approx(5_000)  # B's weight parked in cash


def test_cash_sleeve_weight_held_as_balance():
    prices = {"A": 100.0}
    shares, cash = weights_to_shares({"A": 0.7, CASH_TICKER: 0.3}, prices, 10_000)
    assert cash == pytest.approx(3_000)
    assert mark_to_market(shares, prices, cash) == pytest.approx(10_000)


def test_one_engine_live_equals_replay():
    """THE acceptance test: marking day-by-day (live) == nav_series (replay)."""
    panel = _panel()
    shares = {"A": 10.0, "B": 5.0}
    cash = 250.0

    replay = nav_series(shares, panel, cash=cash, rf_daily=0.0)
    live = pd.Series(
        {dt: mark_to_market(shares, {t: panel.at[dt, t] for t in shares}, cash)
         for dt in panel.index}
    )
    # Identical by construction — both go through mark_to_market.
    assert np.allclose(replay.values, live.values, rtol=0, atol=1e-12)


def test_no_look_ahead():
    """A date's NAV must not change when future prices are appended."""
    panel = _panel(n=12)
    shares = {"A": 10.0, "B": 5.0}
    t = panel.index[5]

    full = nav_series(shares, panel, cash=100.0)
    truncated = nav_series(shares, panel.loc[:t], cash=100.0)
    # NAV at t is the same whether or not the panel contains dates after t.
    assert full.loc[t] == pytest.approx(truncated.loc[t])
    assert truncated.index[-1] == t


def test_cash_compounds_at_rf():
    panel = _panel(n=6)
    s = nav_series({}, panel, cash=1000.0, rf_daily=0.001)
    # Pure cash book grows by rf each step.
    assert s.iloc[-1] == pytest.approx(1000.0 * (1.001 ** 5))
    assert s.iloc[0] == pytest.approx(1000.0)
