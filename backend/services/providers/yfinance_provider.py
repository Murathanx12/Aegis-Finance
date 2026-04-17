"""yfinance provider — the primary free source for equity history/snapshots/fundamentals."""

from __future__ import annotations

import logging
import threading
from typing import Optional

import pandas as pd

from backend.cache import retry_with_backoff
from backend.services.providers.base import (
    BaseProvider,
    EquitySnapshot,
    FundamentalMetrics,
    AnalystEstimates,
    ProviderUnavailable,
)

logger = logging.getLogger(__name__)

# yfinance is NOT thread-safe — concurrent downloads corrupt DataFrames.
# Reuse the process-global lock so we don't double-lock when data_fetcher
# also grabs yfinance under its own lock.
_yf_lock = threading.Lock()


class YFinanceProvider(BaseProvider):
    name = "yfinance"
    capabilities = [
        "equity_history",
        "equity_snapshot",
        "fundamentals",
        "analyst_estimates",
    ]

    def is_available(self) -> bool:
        try:
            import yfinance  # noqa: F401
            return True
        except ImportError:
            return False

    @retry_with_backoff(max_retries=3, base_delay=1.0, max_delay=15.0)
    def get_equity_history(
        self, ticker: str, start: str, end: str
    ) -> Optional[pd.Series]:
        if not self.is_available():
            raise ProviderUnavailable("yfinance not installed")
        import yfinance as yf

        with _yf_lock:
            df = yf.download(ticker, start=start, end=end, progress=False)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            series = df["Close"].iloc[:, 0]
        else:
            series = df["Close"]
        out = series.ffill()
        out.attrs["source"] = self.name
        return out

    def get_equity_snapshot(self, ticker: str) -> Optional[EquitySnapshot]:
        if not self.is_available():
            raise ProviderUnavailable("yfinance not installed")
        import yfinance as yf

        try:
            with _yf_lock:
                t = yf.Ticker(ticker)
                fast = getattr(t, "fast_info", None) or {}
                # fast_info is a dict-like in modern yfinance
                price = _get(fast, "last_price") or _get(fast, "lastPrice")
                prev_close = _get(fast, "previous_close") or _get(fast, "previousClose")
                volume = _get(fast, "last_volume") or _get(fast, "lastVolume")
                day_open = _get(fast, "open") or _get(fast, "regularMarketOpen")
                day_high = _get(fast, "day_high") or _get(fast, "dayHigh")
                day_low = _get(fast, "day_low") or _get(fast, "dayLow")
        except Exception as e:
            logger.debug("yfinance snapshot failed for %s: %s", ticker, e)
            return None

        if price is None and prev_close is None:
            return None

        change = None
        change_pct = None
        if price is not None and prev_close is not None and prev_close != 0:
            change = float(price) - float(prev_close)
            change_pct = 100.0 * change / float(prev_close)

        return EquitySnapshot(
            ticker=ticker,
            price=_f(price),
            change=_f(change),
            change_pct=_f(change_pct),
            volume=_f(volume),
            prev_close=_f(prev_close),
            day_open=_f(day_open),
            day_high=_f(day_high),
            day_low=_f(day_low),
            source=self.name,
        )

    def get_fundamentals(self, ticker: str) -> Optional[FundamentalMetrics]:
        if not self.is_available():
            raise ProviderUnavailable("yfinance not installed")
        import yfinance as yf

        try:
            with _yf_lock:
                t = yf.Ticker(ticker)
                info = t.info or {}
        except Exception as e:
            logger.debug("yfinance fundamentals failed for %s: %s", ticker, e)
            return None

        if not info:
            return None

        return FundamentalMetrics(
            ticker=ticker,
            market_cap=_f(info.get("marketCap")),
            pe_ratio=_f(info.get("trailingPE")),
            forward_pe=_f(info.get("forwardPE")),
            pb_ratio=_f(info.get("priceToBook")),
            price_to_sales=_f(info.get("priceToSalesTrailing12Months")),
            debt_to_equity=_f(info.get("debtToEquity")),
            roe=_f(info.get("returnOnEquity")),
            roa=_f(info.get("returnOnAssets")),
            profit_margin=_f(info.get("profitMargins")),
            dividend_yield=_f(info.get("dividendYield")),
            beta=_f(info.get("beta")),
            shares_outstanding=_f(info.get("sharesOutstanding")),
            source=self.name,
        )

    def get_analyst_estimates(self, ticker: str) -> Optional[AnalystEstimates]:
        if not self.is_available():
            raise ProviderUnavailable("yfinance not installed")
        import yfinance as yf

        try:
            with _yf_lock:
                t = yf.Ticker(ticker)
                info = t.info or {}
        except Exception as e:
            logger.debug("yfinance estimates failed for %s: %s", ticker, e)
            return None

        if not info or info.get("targetMeanPrice") is None:
            return None

        return AnalystEstimates(
            ticker=ticker,
            target_mean=_f(info.get("targetMeanPrice")),
            target_high=_f(info.get("targetHighPrice")),
            target_low=_f(info.get("targetLowPrice")),
            target_median=_f(info.get("targetMedianPrice")),
            num_analysts=_i(info.get("numberOfAnalystOpinions")),
            source=self.name,
        )


def _get(obj, key):
    if obj is None:
        return None
    try:
        return obj[key]
    except (KeyError, TypeError):
        return getattr(obj, key, None)


def _f(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        if f != f:  # NaN
            return None
        return f
    except (TypeError, ValueError):
        return None


def _i(v) -> Optional[int]:
    f = _f(v)
    return int(f) if f is not None else None
