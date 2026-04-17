"""Finnhub provider — real-time quotes, analyst recommendations, earnings calendar."""

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
    AnalystEstimates,
    EarningsEvent,
    ProviderUnavailable,
)

logger = logging.getLogger(__name__)

_BASE = "https://finnhub.io/api/v1"
_TIMEOUT = 10


class FinnhubProvider(BaseProvider):
    name = "finnhub"
    capabilities = [
        "equity_snapshot",
        "analyst_estimates",
        "earnings_calendar",
    ]

    def is_available(self) -> bool:
        return api_keys.has("finnhub")

    def _get(self, path: str, params: Optional[dict] = None) -> Optional[object]:
        if not self.is_available():
            raise ProviderUnavailable("Finnhub key not set")
        params = dict(params or {})
        params["token"] = api_keys.finnhub
        try:
            r = requests.get(f"{_BASE}/{path}", params=params, timeout=_TIMEOUT)
            if r.status_code in (401, 403):
                raise ProviderUnavailable(f"Finnhub auth failed: {r.status_code}")
            if r.status_code == 429:
                raise ProviderUnavailable("Finnhub rate limit")
            r.raise_for_status()
            return r.json()
        except ProviderUnavailable:
            raise
        except Exception as e:
            logger.debug("Finnhub request failed for %s: %s", path, e)
            return None

    def get_equity_snapshot(self, ticker: str) -> Optional[EquitySnapshot]:
        cache_key = f"finnhub_quote:{ticker}"
        cached = cache_get(cache_key, 60)
        if cached is not None:
            return EquitySnapshot(**cached)

        q = self._get("quote", {"symbol": ticker})
        if not q or q.get("c") in (0, None):
            return None

        price = _f(q.get("c"))
        prev = _f(q.get("pc"))
        change = _f(q.get("d"))
        change_pct = _f(q.get("dp"))

        snap = EquitySnapshot(
            ticker=ticker,
            price=price,
            change=change,
            change_pct=change_pct,
            prev_close=prev,
            day_open=_f(q.get("o")),
            day_high=_f(q.get("h")),
            day_low=_f(q.get("l")),
            source=self.name,
            updated_ts=_f(q.get("t")),
        )
        cache_set(cache_key, snap.__dict__)
        return snap

    def get_analyst_estimates(self, ticker: str) -> Optional[AnalystEstimates]:
        cache_key = f"finnhub_recs:{ticker}"
        cached = cache_get(cache_key, 86400)
        if cached is not None:
            return AnalystEstimates(**cached)

        recs = self._get("stock/recommendation", {"symbol": ticker})
        if not recs or not isinstance(recs, list) or not recs:
            return None
        latest = recs[0]
        # Price target
        target = self._get("stock/price-target", {"symbol": ticker})
        t = target or {}
        est = AnalystEstimates(
            ticker=ticker,
            target_mean=_f(t.get("targetMean")),
            target_high=_f(t.get("targetHigh")),
            target_low=_f(t.get("targetLow")),
            target_median=_f(t.get("targetMedian")),
            num_analysts=_i(t.get("numberOfAnalysts")),
            strong_buy=_i(latest.get("strongBuy")),
            buy=_i(latest.get("buy")),
            hold=_i(latest.get("hold")),
            sell=_i(latest.get("sell")),
            strong_sell=_i(latest.get("strongSell")),
            source=self.name,
            as_of=str(latest.get("period", "")) or None,
        )
        cache_set(cache_key, est.__dict__)
        return est

    def get_earnings_calendar(
        self, ticker: Optional[str] = None, days_ahead: int = 30
    ) -> list[EarningsEvent]:
        today = pd.Timestamp.today()
        end = (today + pd.Timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        start = today.strftime("%Y-%m-%d")
        params = {"from": start, "to": end}
        if ticker:
            params["symbol"] = ticker

        cache_key = f"finnhub_earnings:{ticker or 'all'}:{start}:{end}"
        cached = cache_get(cache_key, 3600)
        if cached is not None:
            return [EarningsEvent(**e) for e in cached]

        data = self._get("calendar/earnings", params)
        if not data or "earningsCalendar" not in data:
            return []
        events = []
        for row in data["earningsCalendar"]:
            events.append(
                EarningsEvent(
                    ticker=row.get("symbol", ""),
                    date=row.get("date", ""),
                    eps_estimate=_f(row.get("epsEstimate")),
                    eps_actual=_f(row.get("epsActual")),
                    revenue_estimate=_f(row.get("revenueEstimate")),
                    revenue_actual=_f(row.get("revenueActual")),
                    time=row.get("hour"),
                    source=self.name,
                )
            )
        cache_set(cache_key, [e.__dict__ for e in events])
        return events


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
