"""Polygon provider — thin adapter over the existing PolygonClient."""

from __future__ import annotations

from typing import Optional

import pandas as pd

from backend.config import api_keys
from backend.services.polygon_client import PolygonClient
from backend.services.providers.base import (
    BaseProvider,
    EquitySnapshot,
    ProviderUnavailable,
)


class PolygonProvider(BaseProvider):
    name = "polygon"
    capabilities = ["equity_snapshot", "equity_history"]

    def __init__(self):
        self._client = PolygonClient()

    def is_available(self) -> bool:
        return bool(self._client.available) and api_keys.has("polygon")

    def get_equity_snapshot(self, ticker: str) -> Optional[EquitySnapshot]:
        if not self.is_available():
            raise ProviderUnavailable("Polygon not available")
        snap = self._client.get_snapshot(ticker)
        if snap is None:
            return None
        day = snap.get("day") or {}
        prev = snap.get("prev_day") or {}
        return EquitySnapshot(
            ticker=ticker,
            price=snap.get("price") or day.get("close") or prev.get("close"),
            change=snap.get("change"),
            change_pct=snap.get("change_pct"),
            volume=day.get("volume"),
            prev_close=prev.get("close"),
            day_open=day.get("open"),
            day_high=day.get("high"),
            day_low=day.get("low"),
            source=self.name,
            updated_ts=snap.get("updated_ts"),
        )

    def get_equity_history(
        self, ticker: str, start: str, end: str
    ) -> Optional[pd.Series]:
        if not self.is_available():
            raise ProviderUnavailable("Polygon not available")
        # Polygon free tier lets you pull 2y daily bars. Use day-span aggs.
        try:
            from polygon import RESTClient
            client = RESTClient(api_key=api_keys.polygon)
            aggs = client.get_aggs(ticker, 1, "day", start, end, limit=50000)
            if not aggs:
                return None
            rows = {}
            for bar in aggs:
                if bar.timestamp and bar.close is not None:
                    ts = pd.Timestamp(bar.timestamp, unit="ms")
                    rows[ts] = float(bar.close)
            if not rows:
                return None
            s = pd.Series(rows, dtype=float).sort_index()
            s.attrs["source"] = self.name
            return s
        except Exception:
            return None
