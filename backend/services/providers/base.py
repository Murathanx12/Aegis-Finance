"""
Aegis Finance — Provider Adapter Base
======================================

Common contract for every data provider (yfinance, FRED, Polygon, FMP, Finnhub,
Alpha Vantage, …). OpenBB-style: each provider implements the subset of methods
it can serve; the registry composes them into a single best-available surface
with transparent fallback.

Design rules:
  - Providers raise `ProviderUnavailable` when the API key is missing or the
    service is down. Callers catch this and try the next provider.
  - Providers return a canonical dataclass (`EquitySnapshot`,
    `FundamentalMetrics`, …) or a pd.Series for historical prices so existing
    code paths keep working unchanged.
  - Every method is read-only and side-effect-free (apart from caching).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

import pandas as pd


class ProviderUnavailable(Exception):
    """Raised when a provider cannot fulfill a request (no key, down, rate-limited)."""


class ProviderError(Exception):
    """Raised for a genuine fetch failure after retries — not a fallback trigger."""


# ── Canonical result shapes ──────────────────────────────────────────────────


@dataclass
class EquitySnapshot:
    ticker: str
    price: Optional[float] = None
    change: Optional[float] = None
    change_pct: Optional[float] = None
    volume: Optional[float] = None
    prev_close: Optional[float] = None
    day_open: Optional[float] = None
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    source: str = ""
    updated_ts: Optional[float] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class FundamentalMetrics:
    ticker: str
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    pb_ratio: Optional[float] = None
    price_to_sales: Optional[float] = None
    debt_to_equity: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None
    profit_margin: Optional[float] = None
    dividend_yield: Optional[float] = None
    beta: Optional[float] = None
    shares_outstanding: Optional[float] = None
    source: str = ""
    as_of: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class AnalystEstimates:
    ticker: str
    target_mean: Optional[float] = None
    target_high: Optional[float] = None
    target_low: Optional[float] = None
    target_median: Optional[float] = None
    num_analysts: Optional[int] = None
    strong_buy: Optional[int] = None
    buy: Optional[int] = None
    hold: Optional[int] = None
    sell: Optional[int] = None
    strong_sell: Optional[int] = None
    source: str = ""
    as_of: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class EarningsEvent:
    ticker: str
    date: str
    eps_estimate: Optional[float] = None
    eps_actual: Optional[float] = None
    revenue_estimate: Optional[float] = None
    revenue_actual: Optional[float] = None
    time: Optional[str] = None  # "bmo", "amc", or None
    source: str = ""


@dataclass
class ProviderHealth:
    name: str
    available: bool
    reason: str = ""
    capabilities: list = field(default_factory=list)


# ── Provider protocol ────────────────────────────────────────────────────────


@runtime_checkable
class DataProvider(Protocol):
    """Every provider declares which capabilities it supports via `capabilities`.

    Capabilities: "equity_history", "equity_snapshot", "fundamentals",
    "analyst_estimates", "earnings_calendar", "macro_series".
    """

    name: str
    capabilities: list

    def is_available(self) -> bool: ...

    def health(self) -> ProviderHealth: ...

    def get_equity_history(
        self, ticker: str, start: str, end: str
    ) -> Optional[pd.Series]:
        """Return a date-indexed pd.Series of close prices. Raises ProviderUnavailable."""
        ...

    def get_equity_snapshot(self, ticker: str) -> Optional[EquitySnapshot]: ...

    def get_fundamentals(self, ticker: str) -> Optional[FundamentalMetrics]: ...

    def get_analyst_estimates(self, ticker: str) -> Optional[AnalystEstimates]: ...


# ── Base class for concrete providers ────────────────────────────────────────


class BaseProvider:
    """Default-implementation mixin. Concrete providers override what they can."""

    name: str = "base"
    capabilities: list = []

    def is_available(self) -> bool:  # pragma: no cover - trivial default
        return False

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            name=self.name,
            available=self.is_available(),
            reason="" if self.is_available() else "no API key",
            capabilities=list(self.capabilities),
        )

    # All fetch methods default to raising ProviderUnavailable so the registry
    # cleanly skips past providers that don't implement a capability.

    def get_equity_history(self, ticker: str, start: str, end: str):
        raise ProviderUnavailable(f"{self.name}: equity_history not supported")

    def get_equity_snapshot(self, ticker: str):
        raise ProviderUnavailable(f"{self.name}: equity_snapshot not supported")

    def get_fundamentals(self, ticker: str):
        raise ProviderUnavailable(f"{self.name}: fundamentals not supported")

    def get_analyst_estimates(self, ticker: str):
        raise ProviderUnavailable(f"{self.name}: analyst_estimates not supported")

    def get_earnings_calendar(self, ticker: str):
        raise ProviderUnavailable(f"{self.name}: earnings_calendar not supported")
