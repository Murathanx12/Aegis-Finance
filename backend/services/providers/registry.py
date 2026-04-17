"""
Aegis Finance — Provider Registry
==================================

Single entry point for multi-source data access. Registers providers in
priority order per capability, tries each in turn, and transparently falls back
to the next when a provider is unavailable or returns no data.

Example:
    from backend.services.providers import registry

    hist = registry.get_equity_history("AAPL", "2024-01-01", "2024-12-31")
    print(hist.attrs.get("source"))  # "yfinance" or fallback name

    snap = registry.get_equity_snapshot("AAPL")
    print(snap.price, snap.source)
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from backend.services.providers.base import (
    AnalystEstimates,
    DataProvider,
    EquitySnapshot,
    FundamentalMetrics,
    ProviderHealth,
    ProviderUnavailable,
)
from backend.services.providers.yfinance_provider import YFinanceProvider
from backend.services.providers.fmp_provider import FMPProvider
from backend.services.providers.finnhub_provider import FinnhubProvider
from backend.services.providers.alpha_vantage_provider import AlphaVantageProvider
from backend.services.providers.polygon_provider import PolygonProvider
from backend.services.providers.fred_provider import FredProvider

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Holds provider instances and routes capability calls with fallback."""

    def __init__(self):
        # Instances are cheap (no network at import time).
        self._providers: dict[str, DataProvider] = {
            "yfinance": YFinanceProvider(),
            "polygon": PolygonProvider(),
            "fmp": FMPProvider(),
            "finnhub": FinnhubProvider(),
            "alpha_vantage": AlphaVantageProvider(),
            "fred": FredProvider(),
        }
        # Default priority order per capability — leftmost tried first.
        self._priority: dict[str, list[str]] = {
            "equity_history": ["yfinance", "fmp", "polygon", "alpha_vantage"],
            # Snapshot: Finnhub + Polygon are near-real-time, yfinance is 15-min delayed
            "equity_snapshot": ["finnhub", "polygon", "yfinance", "fmp"],
            "fundamentals": ["fmp", "yfinance", "alpha_vantage"],
            "analyst_estimates": ["finnhub", "fmp", "yfinance"],
            "earnings_calendar": ["finnhub"],
            "macro_series": ["fred"],
        }

    # ── Introspection ──────────────────────────────────────────────────────

    def health(self) -> list[ProviderHealth]:
        return [p.health() for p in self._providers.values()]

    def available_providers(self, capability: str) -> list[str]:
        return [
            n
            for n in self._priority.get(capability, [])
            if self._providers[n].is_available()
            and capability in self._providers[n].capabilities
        ]

    def set_priority(self, capability: str, order: list[str]) -> None:
        """Override provider priority for a capability (e.g., force Finnhub first)."""
        unknown = [n for n in order if n not in self._providers]
        if unknown:
            raise ValueError(f"Unknown providers: {unknown}")
        self._priority[capability] = list(order)

    # ── Dispatch ───────────────────────────────────────────────────────────

    def _try(
        self, capability: str, call: Callable[[DataProvider], object]
    ) -> Optional[object]:
        """Try each provider in priority order; return the first non-None result."""
        errors: list[str] = []
        for name in self._priority.get(capability, []):
            p = self._providers.get(name)
            if p is None:
                continue
            if capability not in p.capabilities:
                continue
            if not p.is_available():
                continue
            try:
                result = call(p)
                if result is not None and not _is_empty(result):
                    return result
            except ProviderUnavailable as e:
                errors.append(f"{name}: {e}")
                continue
            except Exception as e:
                # Real fetch error — log but keep trying
                logger.warning("%s provider error for %s: %s", name, capability, e)
                errors.append(f"{name}: {type(e).__name__}")
                continue
        if errors:
            logger.debug("All providers exhausted for %s: %s", capability, errors)
        return None

    # ── Public capability surface ──────────────────────────────────────────

    def get_equity_history(self, ticker: str, start: str, end: str):
        return self._try(
            "equity_history",
            lambda p: p.get_equity_history(ticker, start, end),
        )

    def get_equity_snapshot(self, ticker: str) -> Optional[EquitySnapshot]:
        return self._try(
            "equity_snapshot",
            lambda p: p.get_equity_snapshot(ticker),
        )

    def get_fundamentals(self, ticker: str) -> Optional[FundamentalMetrics]:
        return self._try(
            "fundamentals",
            lambda p: p.get_fundamentals(ticker),
        )

    def get_analyst_estimates(self, ticker: str) -> Optional[AnalystEstimates]:
        return self._try(
            "analyst_estimates",
            lambda p: p.get_analyst_estimates(ticker),
        )

    def get_earnings_calendar(self, ticker: Optional[str] = None, days_ahead: int = 30):
        # Earnings calendar currently only on Finnhub — no fallback
        p = self._providers["finnhub"]
        if not p.is_available():
            return []
        try:
            return p.get_earnings_calendar(ticker, days_ahead)
        except ProviderUnavailable:
            return []

    def get_macro_series(self, series_id: str):
        p = self._providers["fred"]
        if not p.is_available():
            return None
        try:
            return p.get_macro_series(series_id)
        except ProviderUnavailable:
            return None


def _is_empty(result) -> bool:
    """Treat empty Series/dict/list as no-data so we try the next provider."""
    try:
        if hasattr(result, "empty"):
            return bool(result.empty)
        if hasattr(result, "__len__"):
            return len(result) == 0
    except Exception:
        pass
    return False


# Process-global singleton — cheap to construct, providers lazy-check availability.
registry = ProviderRegistry()
