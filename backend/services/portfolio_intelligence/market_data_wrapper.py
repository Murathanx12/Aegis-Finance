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
        """Return prices up to and including dt. Never returns future data.

        C5 (2026-08-04): the old assertion re-checked what ``.loc[:ts]`` on a
        sorted index guarantees by construction — it could never fire. The
        real precondition that CAN break (and silently corrupts every slice)
        is index monotonicity, so that is what is asserted.
        """
        ts = pd.Timestamp(dt)
        assert self._prices.index.is_monotonic_increasing, (
            "price index lost monotonicity — .loc slicing is undefined; "
            "something mutated _prices after construction"
        )
        return self._prices.loc[:ts]

    def fred_as_of(self, dt: date) -> dict[str, pd.Series]:
        """Return FRED data PUBLISHED by dt, forward-filled.

        C5 (2026-08-04): the old version sliced on the REFERENCE-date index —
        the one axis that is safe by construction — while serving values the
        public had not yet seen (a March print is released in April). Each
        series' index is now shifted by its publication lag from config
        (``fred_publication_lag_days``) before slicing, so the availability
        check is on the RELEASE axis and genuinely binds. Series mapped to
        None (RECPROUSM156N: retrospectively re-smoothed) are not served.

        Remaining known gap, documented not hidden: values are latest-REVISED,
        not first-release vintages — FRED does not serve vintages through this
        API. The lag guard fixes the timing axis; the revision axis needs ALFRED.
        """
        from backend.config import config as _cfg
        lags = _cfg["data"].get("fred_publication_lag_days", {})
        default_lag = _cfg["data"].get("fred_publication_lag_default", 45)

        ts = pd.Timestamp(dt)
        result = {}
        for key, series in self._fred.items():
            lag = lags.get(key, default_lag)
            if lag is None:
                continue
            shifted = series.copy()
            shifted.index = shifted.index + pd.Timedelta(days=int(lag))
            sliced = shifted.loc[:ts]
            if not sliced.empty:
                sliced = sliced.ffill()
                # a real, fail-able guard: the newest served observation must
                # be one whose RELEASE date has passed
                newest_release = sliced.index.max()
                assert newest_release <= ts, (
                    f"FRED release-date leak on {key}: newest served release "
                    f"{newest_release} > as_of {ts}"
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
        # fred_as_of already shifted every series to its release date —
        # build_feature_matrix must NOT apply the lags a second time.
        features = build_feature_matrix(
            prices, fred_data=fred if fred else None,
            apply_publication_lags=False,
        )

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
