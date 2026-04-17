"""Macro endpoints — regime, yield curve, credit, net liquidity."""

from __future__ import annotations

from aegis.client import default_client


def status(*, client=None) -> dict:
    """Unified market-status snapshot (regime + risk score + crash + systemic)."""
    c = client or default_client()
    return c.get("/api/market-status")


def dashboard(*, client=None) -> dict:
    c = client or default_client()
    return c.get("/api/dashboard")


def macro(*, client=None) -> dict:
    c = client or default_client()
    return c.get("/api/macro")


def regime(*, client=None) -> dict:
    c = client or default_client()
    return c.get("/api/analytics/macro-regime")


def cross_asset(*, client=None) -> dict:
    c = client or default_client()
    return c.get("/api/analytics/cross-asset")


def fixed_income(*, client=None) -> dict:
    """Yield curve + credit spreads + real yields + inversion flags."""
    c = client or default_client()
    return c.get("/api/analytics/fixed-income")


def net_liquidity(*, client=None) -> dict:
    c = client or default_client()
    return c.get("/api/net-liquidity")


def valuation(*, client=None) -> dict:
    """Market-level CAPE / ERP / Buffett indicator."""
    c = client or default_client()
    return c.get("/api/analytics/valuation")
