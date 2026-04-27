"""
Aegis Finance — Market Data Wrapper (Anti-Leakage Guard)
==========================================================

Restricts data access to only data available as-of a given date.
This is the ONLY defense against look-ahead leakage in replay.

Usage:
    wrapper = MarketDataAtTimestamp(prices, fred_data)
    as_of_prices = wrapper.prices_as_of(date(2024, 6, 15))
    as_of_features = wrapper.crash_features_as_of(date(2024, 6, 15))
"""

import logging
from datetime import date

import pandas as pd

logger = logging.getLogger(__name__)


class MarketDataAtTimestamp:
    """Restricts market data access to prevent look-ahead bias.

    Pre-fetches full history once, then provides sliced views.
    Hard assertion: any returned data has index <= requested date.
    """

    def __init__(
        self,
        prices: pd.DataFrame,
        fred_data: dict[str, pd.Series] | None = None,
    ):
        if prices.empty:
            raise ValueError("prices DataFrame is empty")

        self._prices = prices.sort_index()
        self._fred = {}
        if fred_data:
            for key, series in fred_data.items():
                if series is not None and len(series) > 0:
                    self._fred[key] = series.sort_index()

        self._min_date = self._prices.index.min().date() if hasattr(self._prices.index.min(), 'date') else self._prices.index.min()
        self._max_date = self._prices.index.max().date() if hasattr(self._prices.index.max(), 'date') else self._prices.index.max()

    @property
    def date_range(self) -> tuple[date, date]:
        return self._min_date, self._max_date

    def prices_as_of(self, dt: date) -> pd.DataFrame:
        """Return prices up to and including dt. Never returns future data."""
        ts = pd.Timestamp(dt)
        sliced = self._prices.loc[:ts]
        if not sliced.empty:
            actual_max = sliced.index.max()
            assert actual_max <= ts, (
                f"Look-ahead leakage: returned data up to {actual_max}, "
                f"but as_of date is {ts}"
            )
        return sliced

    def fred_as_of(self, dt: date) -> dict[str, pd.Series]:
        """Return FRED data up to and including dt, forward-filled.

        FRED releases are sparse (weekly/monthly). Forward-fill brings
        the latest known value forward, but never past dt.
        """
        ts = pd.Timestamp(dt)
        result = {}
        for key, series in self._fred.items():
            sliced = series.loc[:ts]
            if not sliced.empty:
                sliced = sliced.ffill()
                actual_max = sliced.index.max()
                assert actual_max <= ts, (
                    f"FRED look-ahead leakage on {key}: "
                    f"data up to {actual_max}, as_of {ts}"
                )
            result[key] = sliced
        return result

    def crash_features_as_of(self, dt: date) -> pd.DataFrame | None:
        """Compute crash model features using only data available as-of dt.

        Uses the same feature pipeline as crash_model.py but with sliced data.
        Returns a single-row DataFrame suitable for predict_proba().
        """
        try:
            from engine.training.features import build_feature_matrix
        except ImportError:
            logger.warning("engine.training.features not available for replay")
            return None

        prices = self.prices_as_of(dt)
        if prices.empty or len(prices) < 60:
            return None

        fred = self.fred_as_of(dt)
        features = build_feature_matrix(prices, fred_data=fred if fred else None)

        if features.empty:
            return None

        last_row = features.iloc[[-1]]

        if hasattr(last_row.index[-1], 'date'):
            row_date = last_row.index[-1].date()
        else:
            row_date = last_row.index[-1]
        assert row_date <= dt, (
            f"Feature look-ahead: feature date {row_date} > as_of {dt}"
        )

        return last_row

    def ticker_prices_as_of(
        self,
        tickers: list[str],
        dt: date,
        lookback_days: int = 5,
    ) -> dict[str, float]:
        """Get latest price for each ticker as-of dt.

        Looks back up to lookback_days for the most recent available price.
        """
        ts = pd.Timestamp(dt)
        start = ts - pd.Timedelta(days=lookback_days)
        prices = {}
        for ticker in tickers:
            if ticker in self._prices.columns:
                series = self._prices[ticker].loc[start:ts].dropna()
                if not series.empty:
                    prices[ticker] = float(series.iloc[-1])
        return prices
