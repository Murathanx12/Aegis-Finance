"""Tests for WEI-style world-markets snapshot + economic calendar wiring."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.services.providers import EquitySnapshot


def _clear_all_caches():
    """@cached has both memory + disk layers; clear both for test isolation."""
    from backend.cache import cache_clear, _get_disk_cache

    cache_clear()
    dc = _get_disk_cache()
    if dc is not None:
        try:
            dc.clear()
        except Exception:
            pass


@pytest.fixture(autouse=True)
def reset_caches():
    _clear_all_caches()
    yield
    _clear_all_caches()


# ── Unit: world_markets service ──────────────────────────────────────────────


class TestWorldMarketsService:
    def test_returns_all_categories(self, monkeypatch):
        from backend.services import world_markets

        def fake_snap(ticker):
            return {
                "price": 100.0 + hash(ticker) % 50,
                "change": 0.5,
                "change_pct": 0.5,
                "prev_close": 100.0,
                "source": "fake",
            }

        monkeypatch.setattr(world_markets, "_snapshot_one", fake_snap)
        # Bust the @cached decorator by clearing memo
        from backend.cache import cache_clear
        cache_clear()

        result = world_markets.get_world_markets_snapshot()
        assert "indices" in result
        assert "fx" in result
        assert "commodities" in result
        assert "yields" in result
        assert result["counts"]["total_fetched"] > 0
        # Every row has the canonical shape
        for row in result["indices"]:
            assert {"ticker", "name", "region", "category", "price", "source"} <= row.keys()
            assert row["category"] == "index"
        # Gainers/losers bounded at 5
        assert len(result["top_gainers"]) <= 5
        assert len(result["top_losers"]) <= 5

    def test_handles_partial_failures(self, monkeypatch):
        from backend.services import world_markets

        # Deterministic: fail on a known set of tickers from the universe.
        FAILING = {"^GSPC", "EURUSD=X", "GC=F", "^TNX", "^FTSE", "USDJPY=X"}

        def flaky(ticker):
            if ticker in FAILING:
                return None
            return {"price": 10.0, "change": 0.0, "change_pct": 0.0, "prev_close": 10.0, "source": "f"}

        monkeypatch.setattr(world_markets, "_snapshot_one", flaky)
        from backend.cache import cache_clear
        cache_clear()

        result = world_markets.get_world_markets_snapshot()
        total = result["counts"]["total_attempted"]
        fetched = result["counts"]["total_fetched"]
        assert fetched > 0
        assert fetched == total - len(FAILING)  # exactly our failures dropped


class TestEconomicCalendar:
    def test_empty_when_no_finnhub_key(self, monkeypatch):
        from backend.services import world_markets
        from backend.config import api_keys

        monkeypatch.setattr(api_keys, "finnhub", "")
        result = world_markets.get_economic_calendar(days_ahead=7)
        assert result["count"] == 0
        assert result["events"] == []
        assert "note" in result

    def test_passes_through_finnhub_response(self, monkeypatch):
        import requests
        from backend.services import world_markets
        from backend.config import api_keys

        monkeypatch.setattr(api_keys, "finnhub", "test-key")

        class FakeResponse:
            status_code = 200

            def json(self):
                return {
                    "economicCalendar": [
                        {
                            "time": "2026-04-18 08:30:00",
                            "country": "US",
                            "event": "Nonfarm Payrolls",
                            "estimate": 180000,
                            "prev": 175000,
                            "actual": None,
                            "impact": "high",
                            "unit": "K",
                        },
                    ]
                }

            def raise_for_status(self):
                pass

        monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse())
        result = world_markets.get_economic_calendar(days_ahead=7)
        assert result["count"] == 1
        assert result["events"][0]["event"] == "Nonfarm Payrolls"
        assert result["events"][0]["estimate"] == 180000.0
        assert result["events"][0]["date"] == "2026-04-18"


# ── Integration: /api/world-markets and /api/economic-calendar ───────────────


@pytest.fixture
def client():
    from backend.main import app
    return TestClient(app)


class TestWorldMarketsEndpoint:
    def test_endpoint_returns_shape(self, client, monkeypatch):
        fake_payload = {
            "counts": {
                "indices": 1,
                "fx": 0,
                "commodities": 0,
                "yields": 0,
                "total_attempted": 1,
                "total_fetched": 1,
            },
            "indices": [
                {
                    "ticker": "^GSPC",
                    "name": "S&P 500",
                    "region": "Americas",
                    "category": "index",
                    "price": 5500.0,
                    "change": 10.0,
                    "change_pct": 0.18,
                    "source": "fake",
                }
            ],
            "fx": [],
            "commodities": [],
            "yields": [],
            "top_gainers": [],
            "top_losers": [],
        }
        from backend.services import world_markets
        monkeypatch.setattr(world_markets, "get_world_markets_snapshot", lambda: fake_payload)
        from backend.cache import cache_clear
        cache_clear()

        r = client.get("/api/world-markets")
        assert r.status_code == 200
        body = r.json()
        assert body["counts"]["total_fetched"] == 1
        assert body["indices"][0]["ticker"] == "^GSPC"


class TestEconomicCalendarEndpoint:
    def test_rejects_out_of_range(self, client):
        r = client.get("/api/economic-calendar?days_ahead=200")
        assert r.status_code == 422

    def test_returns_empty_safely(self, client, monkeypatch):
        from backend.services import world_markets
        monkeypatch.setattr(
            world_markets,
            "get_economic_calendar",
            lambda days_ahead=14: {"days_ahead": days_ahead, "count": 0, "events": []},
        )
        from backend.cache import cache_clear
        cache_clear()
        r = client.get("/api/economic-calendar?days_ahead=5")
        assert r.status_code == 200
        assert r.json() == {"days_ahead": 5, "count": 0, "events": []}

    # Keep the EquitySnapshot import from being pruned in fixer runs
    def test_snapshot_dataclass_import_smoke(self):
        s = EquitySnapshot(ticker="AAPL", price=100.0, source="test")
        assert s.ticker == "AAPL"
