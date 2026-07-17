"""Financial Modeling Prep provider — fundamentals + analyst estimates + price fallback."""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
import requests

from backend.config import api_keys
from backend.cache import cache_get, cache_set
from backend.services.providers.base import (
    BaseProvider,
    EquitySnapshot,
    FundamentalMetrics,
    AnalystEstimates,
    ProviderUnavailable,
)

logger = logging.getLogger(__name__)

_BASE = "https://financialmodelingprep.com/api/v3"
_TIMEOUT = 10


class FMPProvider(BaseProvider):
    name = "fmp"
    capabilities = [
        "equity_history",
        "equity_snapshot",
        "fundamentals",
        "analyst_estimates",
    ]

    def is_available(self) -> bool:
        return api_keys.has("fmp")

    def _get(self, path: str, params: Optional[dict] = None) -> Optional[object]:
        if not self.is_available():
            raise ProviderUnavailable("FMP key not set")
        # Fallback traffic is metered (2026-07-17): this provider is the
        # biggest drain on the shared 250/day quota and it must never starve
        # the pre-registered congress-IC collector again.
        from backend.services import fmp_budget
        if not fmp_budget.try_spend():
            raise ProviderUnavailable("FMP daily budget spent — deferring to other providers")
        params = dict(params or {})
        params["apikey"] = api_keys.fmp
        try:
            r = requests.get(f"{_BASE}/{path}", params=params, timeout=_TIMEOUT)
            if r.status_code == 403 or r.status_code == 401:
                raise ProviderUnavailable(f"FMP auth failed: {r.status_code}")
            if r.status_code == 429:
                raise ProviderUnavailable("FMP rate limit")
            if r.status_code == 402:
                fmp_budget.mark_exhausted()
                raise ProviderUnavailable("FMP quota exhausted (402)")
            r.raise_for_status()
            return r.json()
        except ProviderUnavailable:
            raise
        except Exception as e:
            logger.debug("FMP request failed for %s: %s", path, api_keys.redact(str(e)))
            return None

    def get_equity_history(
        self, ticker: str, start: str, end: str
    ) -> Optional[pd.Series]:
        cache_key = f"fmp_hist:{ticker}:{start}:{end}"
        cached = cache_get(cache_key, 3600)
        if cached is not None:
            return _to_series(cached, self.name)
        data = self._get(
            f"historical-price-full/{ticker}",
            params={"from": start, "to": end},
        )
        if not data or "historical" not in data:
            return None
        rows = data["historical"]
        if not rows:
            return None
        closes = {row["date"]: row.get("close") for row in rows if row.get("close") is not None}
        cache_set(cache_key, closes)
        return _to_series(closes, self.name)

    def get_equity_snapshot(self, ticker: str) -> Optional[EquitySnapshot]:
        data = self._get(f"quote/{ticker}")
        if not data or not isinstance(data, list) or not data:
            return None
        q = data[0]
        return EquitySnapshot(
            ticker=ticker,
            price=_f(q.get("price")),
            change=_f(q.get("change")),
            change_pct=_f(q.get("changesPercentage")),
            volume=_f(q.get("volume")),
            prev_close=_f(q.get("previousClose")),
            day_open=_f(q.get("open")),
            day_high=_f(q.get("dayHigh")),
            day_low=_f(q.get("dayLow")),
            source=self.name,
        )

    def get_fundamentals(self, ticker: str) -> Optional[FundamentalMetrics]:
        profile = self._get(f"profile/{ticker}")
        if not profile or not isinstance(profile, list) or not profile:
            return None
        p = profile[0]
        ratios = self._get(f"ratios-ttm/{ticker}")
        r = ratios[0] if ratios and isinstance(ratios, list) and ratios else {}
        return FundamentalMetrics(
            ticker=ticker,
            market_cap=_f(p.get("mktCap")),
            pe_ratio=_f(r.get("peRatioTTM")),
            pb_ratio=_f(r.get("priceToBookRatioTTM")),
            price_to_sales=_f(r.get("priceToSalesRatioTTM")),
            debt_to_equity=_f(r.get("debtEquityRatioTTM")),
            roe=_f(r.get("returnOnEquityTTM")),
            roa=_f(r.get("returnOnAssetsTTM")),
            profit_margin=_f(r.get("netProfitMarginTTM")),
            dividend_yield=_f(r.get("dividendYielTTM") or r.get("dividendYieldTTM")),
            beta=_f(p.get("beta")),
            shares_outstanding=_f(p.get("sharesOutstanding") or p.get("volAvg")),
            source=self.name,
        )

    def get_analyst_estimates(self, ticker: str) -> Optional[AnalystEstimates]:
        target = self._get(f"price-target-consensus/{ticker}")
        if not target or not isinstance(target, list) or not target:
            return None
        t = target[0]
        # Ratings breakdown endpoint
        ratings = self._get(f"upgrades-downgrades-consensus/{ticker}")
        r = ratings[0] if ratings and isinstance(ratings, list) and ratings else {}
        return AnalystEstimates(
            ticker=ticker,
            target_mean=_f(t.get("targetConsensus")),
            target_high=_f(t.get("targetHigh")),
            target_low=_f(t.get("targetLow")),
            target_median=_f(t.get("targetMedian")),
            strong_buy=_i(r.get("strongBuy")),
            buy=_i(r.get("buy")),
            hold=_i(r.get("hold")),
            sell=_i(r.get("sell")),
            strong_sell=_i(r.get("strongSell")),
            source=self.name,
        )


def _to_series(closes: dict, source: str) -> Optional[pd.Series]:
    if not closes:
        return None
    s = pd.Series(closes, dtype=float)
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    s.attrs["source"] = source
    return s


def _f(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        if f != f:
            return None
        return f
    except (TypeError, ValueError):
        return None


def _i(v) -> Optional[int]:
    f = _f(v)
    return int(f) if f is not None else None
