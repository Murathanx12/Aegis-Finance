"""Per-ticker endpoints: snapshot, analysis, ownership, fundamentals, etc."""

from __future__ import annotations

from typing import Optional

from aegis.client import default_client


def snapshot(ticker: str, *, client=None) -> dict:
    """Live-ish price snapshot via the provider registry (Finnhub/Polygon/yfinance)."""
    c = client or default_client()
    return c.get(f"/api/realtime/{ticker.upper()}")


def analysis(ticker: str, *, client=None) -> dict:
    """Full stock analysis — projections, factors, signals."""
    c = client or default_client()
    return c.get(f"/api/stock/{ticker.upper()}")


def technicals(ticker: str, *, client=None) -> dict:
    c = client or default_client()
    return c.get(f"/api/analytics/technicals/{ticker.upper()}")


def fundamentals(ticker: str, *, client=None) -> dict:
    c = client or default_client()
    return c.get(f"/api/stock/{ticker.upper()}/fundamentals")


def ownership(ticker: str, *, client=None) -> dict:
    """Top institutional holders + crowding + QoQ activity."""
    c = client or default_client()
    return c.get(f"/api/stock/{ticker.upper()}/ownership")


def etf_lookthrough(ticker: str, *, client=None) -> dict:
    """ETF top holdings + sector weightings. Raises on non-ETF (404)."""
    c = client or default_client()
    return c.get(f"/api/stock/{ticker.upper()}/etf-lookthrough")


def insiders(ticker: str, *, client=None) -> dict:
    c = client or default_client()
    return c.get(f"/api/stock/{ticker.upper()}/insiders")


def options(ticker: str, *, client=None) -> dict:
    c = client or default_client()
    return c.get(f"/api/options/{ticker.upper()}")


def shap(ticker: str, *, client=None) -> dict:
    """Return SHAP feature-importance for the crash model on this ticker."""
    c = client or default_client()
    return c.get(f"/api/stock/{ticker.upper()}/shap")


def factors(ticker: str, *, client=None) -> dict:
    """Fama-French 5-factor decomposition."""
    c = client or default_client()
    return c.get(f"/api/analytics/factors/{ticker.upper()}")


def analyst_consensus(ticker: str, *, client=None) -> dict:
    """Unified target-price + rating breakdown (Finnhub/FMP/yfinance)."""
    c = client or default_client()
    return c.get(f"/api/analytics/analyst-consensus/{ticker.upper()}")
