"""Integration tests for endpoints that route through the provider registry:
  - GET /api/analytics/earnings-calendar
  - GET /api/analytics/analyst-consensus/{ticker}
  - GET /api/providers (health inventory)

Mocks the registry so tests stay hermetic — no network, no API keys needed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.services.providers import (
    AnalystEstimates,
    EarningsEvent,
    ProviderHealth,
)


@pytest.fixture
def client():
    from backend.main import app
    return TestClient(app)


# ── /api/providers ────────────────────────────────────────────────────────────


class TestProvidersEndpoint:
    def test_returns_provider_inventory(self, client):
        r = client.get("/api/providers")
        assert r.status_code == 200
        body = r.json()
        assert "providers" in body
        assert "priority" in body
        names = {p["name"] for p in body["providers"]}
        # All six core providers must be reported
        assert {"yfinance", "polygon", "fmp", "finnhub", "alpha_vantage", "fred"} <= names
        for p in body["providers"]:
            assert isinstance(p["available"], bool)
            assert isinstance(p["capabilities"], list)

    def test_priority_order_is_exposed(self, client):
        r = client.get("/api/providers")
        prio = r.json()["priority"]
        assert "equity_snapshot" in prio
        assert "fundamentals" in prio


# ── /api/analytics/earnings-calendar ─────────────────────────────────────────


class TestEarningsCalendarEndpoint:
    def test_returns_events(self, client, monkeypatch):
        sample_events = [
            EarningsEvent(
                ticker="AAPL",
                date="2026-05-02",
                eps_estimate=1.60,
                revenue_estimate=90_000_000_000,
                time="amc",
                source="finnhub",
            ),
            EarningsEvent(
                ticker="MSFT",
                date="2026-05-03",
                eps_estimate=2.95,
                revenue_estimate=62_000_000_000,
                time="amc",
                source="finnhub",
            ),
        ]
        from backend.services.providers import registry
        monkeypatch.setattr(
            registry,
            "get_earnings_calendar",
            lambda ticker=None, days_ahead=30: sample_events,
        )
        # Clear any pre-existing cache entry
        from backend.cache import cache_clear
        cache_clear()

        r = client.get("/api/analytics/earnings-calendar", params={"days_ahead": 7})
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 2
        assert body["days_ahead"] == 7
        assert len(body["events"]) == 2
        assert body["events"][0]["ticker"] == "AAPL"
        assert body["events"][0]["source"] == "finnhub"

    def test_ticker_filter_passthrough(self, client, monkeypatch):
        captured = {}

        def fake(ticker=None, days_ahead=30):
            captured["ticker"] = ticker
            captured["days_ahead"] = days_ahead
            return []

        from backend.services.providers import registry
        monkeypatch.setattr(registry, "get_earnings_calendar", fake)
        from backend.cache import cache_clear
        cache_clear()

        r = client.get(
            "/api/analytics/earnings-calendar",
            params={"ticker": "NVDA", "days_ahead": 14},
        )
        assert r.status_code == 200
        assert captured["ticker"] == "NVDA"
        assert captured["days_ahead"] == 14
        body = r.json()
        assert body["ticker"] == "NVDA"
        assert body["count"] == 0

    def test_rejects_out_of_range_days(self, client):
        r = client.get(
            "/api/analytics/earnings-calendar",
            params={"days_ahead": 500},
        )
        assert r.status_code == 422


# ── /api/analytics/analyst-consensus/{ticker} ────────────────────────────────


class TestAnalystConsensusEndpoint:
    def test_returns_consensus(self, client, monkeypatch):
        est = AnalystEstimates(
            ticker="AAPL",
            target_mean=240.0,
            target_high=290.0,
            target_low=180.0,
            num_analysts=35,
            buy=20,
            hold=10,
            sell=5,
            source="finnhub",
        )
        from backend.services.providers import registry
        monkeypatch.setattr(registry, "get_analyst_estimates", lambda t: est)
        from backend.cache import cache_clear
        cache_clear()

        r = client.get("/api/analytics/analyst-consensus/aapl")
        assert r.status_code == 200
        body = r.json()
        assert body["ticker"] == "AAPL"
        assert body["target_mean"] == 240.0
        assert body["source"] == "finnhub"
        # None-valued fields stripped by to_dict()
        assert "target_median" not in body

    def test_404_when_no_provider_data(self, client, monkeypatch):
        from backend.services.providers import registry
        monkeypatch.setattr(registry, "get_analyst_estimates", lambda t: None)
        from backend.cache import cache_clear
        cache_clear()

        r = client.get("/api/analytics/analyst-consensus/XYZBOGUS")
        assert r.status_code == 404

    def test_rejects_bad_ticker(self, client):
        r = client.get("/api/analytics/analyst-consensus/**injection**")
        assert r.status_code == 422
