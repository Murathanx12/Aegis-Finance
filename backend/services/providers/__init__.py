"""
Aegis Finance — Data Provider Registry
========================================

OpenBB-style provider-adapter architecture. One `registry` entry point routes
every data request to the first available provider for the requested capability
and transparently falls back to the next when a provider is down or unkeyed.

Example:
    from backend.services.providers import registry

    snap = registry.get_equity_snapshot("AAPL")
    print(snap.source, snap.price)

    for h in registry.health():
        print(h.name, h.available, h.capabilities)
"""

from backend.services.providers.base import (
    AnalystEstimates,
    BaseProvider,
    DataProvider,
    EarningsEvent,
    EquitySnapshot,
    FundamentalMetrics,
    ProviderError,
    ProviderHealth,
    ProviderUnavailable,
)
from backend.services.providers.registry import ProviderRegistry, registry

__all__ = [
    "AnalystEstimates",
    "BaseProvider",
    "DataProvider",
    "EarningsEvent",
    "EquitySnapshot",
    "FundamentalMetrics",
    "ProviderError",
    "ProviderHealth",
    "ProviderRegistry",
    "ProviderUnavailable",
    "registry",
]
