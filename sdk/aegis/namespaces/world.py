"""World markets tile + provider inventory."""

from __future__ import annotations

from aegis.client import default_client


def markets(*, client=None) -> dict:
    """WEI-style snapshot: global indices, FX, commodities, yields."""
    c = client or default_client()
    return c.get("/api/world-markets")


def providers(*, client=None) -> dict:
    """List data providers + availability + priority ordering."""
    c = client or default_client()
    return c.get("/api/providers")


def health(*, client=None) -> dict:
    c = client or default_client()
    return c.get("/api/health")
