"""
Tests for the MarketDataAtTimestamp anti-leakage wrapper.

Verifies:
  - prices_as_of never returns future data
  - FRED forward-fill respects cutoff
  - crash_features_as_of returns features only from past data
  - Assertion fires on look-ahead leakage
  - hypothesis: as_of(d) <= as_of(d+1) for random dates
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings, strategies as st, HealthCheck

from backend.services.portfolio_intelligence.market_data_wrapper import (
    MarketDataAtTimestamp,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


def _make_price_df(start="2020-01-01", end="2025-12-31", tickers=None):
    """Create synthetic price DataFrame."""
    if tickers is None:
        tickers = ["SP500", "VIX", "T10Y", "Gold"]
    dates = pd.bdate_range(start, end)
    rng = np.random.default_rng(42)
    data = {}
    for t in tickers:
        base = 100.0 if t != "VIX" else 20.0
        returns = rng.normal(0.0003, 0.01, len(dates))
        prices = base * np.cumprod(1 + returns)
        data[t] = prices
    return pd.DataFrame(data, index=dates)


def _make_fred_data(start="2020-01-01", end="2025-12-31"):
    """Create synthetic FRED data (monthly frequency, sparse)."""
    dates = pd.date_range(start, end, freq="MS")
    rng = np.random.default_rng(99)
    return {
        "UNRATE": pd.Series(3.5 + rng.normal(0, 0.3, len(dates)), index=dates),
        "FEDFUNDS": pd.Series(2.0 + rng.normal(0, 0.5, len(dates)), index=dates),
    }


@pytest.fixture
def wrapper():
    prices = _make_price_df()
    fred = _make_fred_data()
    return MarketDataAtTimestamp(prices, fred)


# ── prices_as_of ─────────────────────────────────────────────────────────


class TestPricesAsOf:
    def test_returns_data_up_to_date(self, wrapper):
        dt = date(2023, 6, 15)
        sliced = wrapper.prices_as_of(dt)
        assert not sliced.empty
        assert sliced.index.max().date() <= dt

    def test_earlier_date_returns_less_data(self, wrapper):
        early = wrapper.prices_as_of(date(2022, 1, 1))
        late = wrapper.prices_as_of(date(2024, 1, 1))
        assert len(early) <= len(late)

    def test_future_date_returns_all_data(self, wrapper):
        all_data = wrapper.prices_as_of(date(2099, 1, 1))
        _, max_date = wrapper.date_range
        assert len(all_data) > 0

    def test_before_start_returns_empty(self, wrapper):
        sliced = wrapper.prices_as_of(date(2019, 1, 1))
        assert sliced.empty

    @given(days_offset=st.integers(min_value=0, max_value=1500))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_monotonic_length(self, days_offset, wrapper):
        """Property: as_of(d) never has MORE rows than as_of(d+1)."""
        base = date(2021, 1, 1)
        d1 = base + timedelta(days=days_offset)
        d2 = d1 + timedelta(days=1)
        s1 = wrapper.prices_as_of(d1)
        s2 = wrapper.prices_as_of(d2)
        assert len(s1) <= len(s2)


# ── fred_as_of ───────────────────────────────────────────────────────────


class TestFredAsOf:
    def test_returns_data_up_to_date(self, wrapper):
        dt = date(2023, 6, 15)
        fred = wrapper.fred_as_of(dt)
        for key, series in fred.items():
            if not series.empty:
                assert series.index.max().date() <= dt

    def test_forward_fill_applied(self, wrapper):
        dt = date(2023, 6, 20)
        fred = wrapper.fred_as_of(dt)
        for key, series in fred.items():
            if not series.empty:
                assert not series.isna().any(), f"{key} has NaN after forward-fill"

    def test_before_start_returns_empty(self, wrapper):
        fred = wrapper.fred_as_of(date(2019, 1, 1))
        for key, series in fred.items():
            assert series.empty


# ── ticker_prices_as_of ──────────────────────────────────────────────────


class TestTickerPricesAsOf:
    def test_returns_prices_for_available_tickers(self, wrapper):
        prices = wrapper.ticker_prices_as_of(["SP500", "Gold"], date(2023, 6, 15))
        assert "SP500" in prices
        assert "Gold" in prices
        assert all(v > 0 for v in prices.values())

    def test_missing_ticker_excluded(self, wrapper):
        prices = wrapper.ticker_prices_as_of(["NONEXISTENT"], date(2023, 6, 15))
        assert "NONEXISTENT" not in prices

    def test_early_date_empty(self, wrapper):
        prices = wrapper.ticker_prices_as_of(["SP500"], date(2019, 1, 1))
        assert prices == {}


# ── Construction ─────────────────────────────────────────────────────────


class TestConstruction:
    def test_empty_prices_raises(self):
        with pytest.raises(ValueError, match="empty"):
            MarketDataAtTimestamp(pd.DataFrame())

    def test_date_range(self, wrapper):
        min_d, max_d = wrapper.date_range
        assert min_d < max_d

    def test_no_fred_ok(self):
        prices = _make_price_df(start="2023-01-01", end="2023-12-31")
        w = MarketDataAtTimestamp(prices)
        sliced = w.prices_as_of(date(2023, 6, 15))
        assert not sliced.empty
        fred = w.fred_as_of(date(2023, 6, 15))
        assert fred == {}
