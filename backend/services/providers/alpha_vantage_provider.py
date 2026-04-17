"""Alpha Vantage provider — cheap fallback for daily OHLCV + overview fundamentals."""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
import requests

from backend.config import api_keys
from backend.cache import cache_get, cache_set
from backend.services.providers.base import (
    BaseProvider,
    FundamentalMetrics,
    ProviderUnavailable,
)

logger = logging.getLogger(__name__)

_BASE = "https://www.alphavantage.co/query"
_TIMEOUT = 15


class AlphaVantageProvider(BaseProvider):
    name = "alpha_vantage"
    capabilities = ["equity_history", "fundamentals"]

    def is_available(self) -> bool:
        return api_keys.has("alpha_vantage")

    def _get(self, params: dict) -> Optional[dict]:
        if not self.is_available():
            raise ProviderUnavailable("Alpha Vantage key not set")
        params = dict(params)
        params["apikey"] = api_keys.alpha_vantage
        try:
            r = requests.get(_BASE, params=params, timeout=_TIMEOUT)
            if r.status_code in (401, 403):
                raise ProviderUnavailable(f"AV auth failed: {r.status_code}")
            r.raise_for_status()
            data = r.json()
            # AV's rate-limit response is a 200 with "Note" or "Information"
            if "Note" in data or "Information" in data:
                raise ProviderUnavailable("Alpha Vantage rate limit")
            return data
        except ProviderUnavailable:
            raise
        except Exception as e:
            logger.debug("Alpha Vantage request failed: %s", e)
            return None

    def get_equity_history(
        self, ticker: str, start: str, end: str
    ) -> Optional[pd.Series]:
        cache_key = f"av_hist:{ticker}:{start}:{end}"
        cached = cache_get(cache_key, 3600)
        if cached is not None:
            return _to_series(cached, self.name)
        data = self._get(
            {
                "function": "TIME_SERIES_DAILY_ADJUSTED",
                "symbol": ticker,
                "outputsize": "full",
            }
        )
        if not data or "Time Series (Daily)" not in data:
            return None
        series_raw = data["Time Series (Daily)"]
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        closes = {}
        for date_str, bar in series_raw.items():
            try:
                ts = pd.Timestamp(date_str)
            except Exception:
                continue
            if ts < start_ts or ts > end_ts:
                continue
            c = bar.get("5. adjusted close") or bar.get("4. close")
            if c is not None:
                closes[date_str] = float(c)
        if not closes:
            return None
        cache_set(cache_key, closes)
        return _to_series(closes, self.name)

    def get_fundamentals(self, ticker: str) -> Optional[FundamentalMetrics]:
        cache_key = f"av_overview:{ticker}"
        cached = cache_get(cache_key, 86400)
        if cached is not None:
            return FundamentalMetrics(**cached)
        data = self._get({"function": "OVERVIEW", "symbol": ticker})
        if not data or "Symbol" not in data:
            return None
        fm = FundamentalMetrics(
            ticker=ticker,
            market_cap=_f(data.get("MarketCapitalization")),
            pe_ratio=_f(data.get("PERatio")),
            forward_pe=_f(data.get("ForwardPE")),
            pb_ratio=_f(data.get("PriceToBookRatio")),
            price_to_sales=_f(data.get("PriceToSalesRatioTTM")),
            roe=_f(data.get("ReturnOnEquityTTM")),
            roa=_f(data.get("ReturnOnAssetsTTM")),
            profit_margin=_f(data.get("ProfitMargin")),
            dividend_yield=_f(data.get("DividendYield")),
            beta=_f(data.get("Beta")),
            shares_outstanding=_f(data.get("SharesOutstanding")),
            source=self.name,
        )
        cache_set(cache_key, fm.__dict__)
        return fm


def _to_series(closes: dict, source: str) -> Optional[pd.Series]:
    if not closes:
        return None
    s = pd.Series(closes, dtype=float)
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    s.attrs["source"] = source
    return s


def _f(v) -> Optional[float]:
    if v is None or v == "None" or v == "-":
        return None
    try:
        f = float(v)
        if f != f:
            return None
        return f
    except (TypeError, ValueError):
        return None
