"""Calendar endpoints — earnings + economic releases."""

from __future__ import annotations

from typing import Optional

from aegis.client import default_client


def earnings(
    ticker: Optional[str] = None,
    *,
    days_ahead: int = 30,
    client=None,
) -> dict:
    """Upcoming earnings releases (Finnhub). Optional per-ticker filter."""
    c = client or default_client()
    params = {"days_ahead": days_ahead}
    if ticker:
        params["ticker"] = ticker.upper()
    return c.get("/api/analytics/earnings-calendar", params=params)


def economic(days_ahead: int = 14, *, client=None) -> dict:
    """Upcoming macro data releases (Finnhub /calendar/economic)."""
    c = client or default_client()
    return c.get("/api/economic-calendar", params={"days_ahead": days_ahead})
