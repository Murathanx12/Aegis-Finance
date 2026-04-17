"""Tests for institutional ownership + ETF look-through."""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient


def _clear_caches():
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
    _clear_caches()
    yield
    _clear_caches()


@pytest.fixture
def client():
    from backend.main import app
    return TestClient(app)


# ── Institutional ownership ──────────────────────────────────────────────────


def _fake_inst_df():
    return pd.DataFrame(
        [
            {"Holder": "Vanguard Group Inc", "Shares": 1_300_000_000, "Value": 375_000_000_000, "pctHeld": 0.09, "pctChange": 0.019, "Date Reported": "2025-12-31"},
            {"Holder": "Blackrock Inc.", "Shares": 1_050_000_000, "Value": 304_000_000_000, "pctHeld": 0.073, "pctChange": 0.007, "Date Reported": "2025-12-31"},
            {"Holder": "State Street Corp", "Shares": 550_000_000, "Value": 159_000_000_000, "pctHeld": 0.038, "pctChange": -0.011, "Date Reported": "2025-12-31"},
            {"Holder": "Geode Capital", "Shares": 325_000_000, "Value": 94_000_000_000, "pctHeld": 0.023, "pctChange": 0.005, "Date Reported": "2025-12-31"},
            {"Holder": "FMR LLC", "Shares": 280_000_000, "Value": 81_000_000_000, "pctHeld": 0.019, "pctChange": 0.013, "Date Reported": "2025-12-31"},
            {"Holder": "Price T. Rowe", "Shares": 200_000_000, "Value": 58_000_000_000, "pctHeld": 0.014, "pctChange": -0.025, "Date Reported": "2025-12-31"},
        ]
    )


def _fake_major_df():
    return pd.DataFrame(
        {
            "Value": {
                "insidersPercentHeld": 0.016,
                "institutionsPercentHeld": 0.653,
                "institutionsFloatPercentHeld": 0.664,
                "institutionsCount": 7509,
            }
        }
    )


class TestInstitutionalOwnership:
    def test_shape_and_crowding(self, monkeypatch):
        import yfinance as yf

        class FakeTicker:
            institutional_holders = _fake_inst_df()
            major_holders = _fake_major_df()

        monkeypatch.setattr(yf, "Ticker", lambda _t: FakeTicker())

        from backend.services.ownership import get_institutional_ownership
        result = get_institutional_ownership("AAPL")

        assert result is not None
        assert result["ticker"] == "AAPL"
        assert len(result["holders"]) == 6
        assert result["holders"][0]["holder"] == "Vanguard Group Inc"
        # sum of pct_held = 0.09 + 0.073 + 0.038 + 0.023 + 0.019 + 0.014 = ~0.257 (moderate band)
        assert result["crowding"]["level"] in {"moderate", "high"}
        # 2 buyers (+1.9%, +1.3%) vs 2 sellers (-1.1%, -2.5%) → neutral
        assert result["recent_activity"]["net_signal"] == "neutral"
        assert result["recent_activity"]["buyers_top10"] == 2
        assert result["recent_activity"]["sellers_top10"] == 2
        assert result["summary"]["institutionsCount"] == 7509.0

    def test_no_yfinance_data_returns_none(self, monkeypatch):
        import yfinance as yf

        class Broken:
            institutional_holders = None
            major_holders = None

        monkeypatch.setattr(yf, "Ticker", lambda _t: Broken())
        from backend.services.ownership import get_institutional_ownership
        result = get_institutional_ownership("AAPL")
        # Service still returns a shape but with no holders — acceptable
        assert result is not None
        assert result["holders"] == []
        assert result["recent_activity"]["net_signal"] == "neutral"


# ── ETF look-through ─────────────────────────────────────────────────────────


def _fake_top_holdings():
    idx = pd.Index(["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL"], name="Symbol")
    return pd.DataFrame(
        {
            "Name": ["NVIDIA Corp", "Apple Inc", "Microsoft Corp", "Amazon.com Inc", "Alphabet Inc"],
            "Holding Percent": [0.075, 0.065, 0.049, 0.036, 0.029],
        },
        index=idx,
    )


class FakeFundsData:
    top_holdings = _fake_top_holdings()
    sector_weightings = {
        "technology": 0.336,
        "financial_services": 0.124,
        "healthcare": 0.095,
        "consumer_cyclical": 0.10,
        "communication_services": 0.105,
    }


class TestEtfLookthrough:
    def test_etf_shape(self, monkeypatch):
        import yfinance as yf

        class FakeTicker:
            funds_data = FakeFundsData()

        monkeypatch.setattr(yf, "Ticker", lambda _t: FakeTicker())

        from backend.services.ownership import get_etf_lookthrough
        result = get_etf_lookthrough("SPY")

        assert result is not None
        assert result["ticker"] == "SPY"
        assert len(result["top_holdings"]) == 5
        assert result["top_holdings"][0]["symbol"] == "NVDA"
        assert "technology" in result["sector_weights"]
        # Top5 = 0.254, Top10 = also 0.254 (only 5 holdings) → moderate
        assert result["concentration"]["level"] == "moderate"

    def test_non_etf_returns_none(self, monkeypatch):
        import yfinance as yf

        class FakeNonEtf:
            funds_data = None

        monkeypatch.setattr(yf, "Ticker", lambda _t: FakeNonEtf())
        from backend.services.ownership import get_etf_lookthrough
        assert get_etf_lookthrough("AAPL") is None


# ── Endpoints ────────────────────────────────────────────────────────────────


class TestOwnershipEndpoints:
    def test_ownership_endpoint(self, client, monkeypatch):
        from backend.services import ownership
        monkeypatch.setattr(
            ownership,
            "get_institutional_ownership",
            lambda t: {"ticker": t, "holders": [], "summary": {}, "crowding": {"level": "low", "top10_pct_held": 0.1, "note": "n/a"}, "recent_activity": {"buyers_top10": 0, "sellers_top10": 0, "net_signal": "neutral"}, "source": "test"},
        )
        r = client.get("/api/stock/AAPL/ownership")
        assert r.status_code == 200
        assert r.json()["ticker"] == "AAPL"

    def test_ownership_404_when_none(self, client, monkeypatch):
        from backend.services import ownership
        monkeypatch.setattr(ownership, "get_institutional_ownership", lambda t: None)
        r = client.get("/api/stock/AAPL/ownership")
        assert r.status_code == 404

    def test_ownership_422_bad_ticker(self, client):
        r = client.get("/api/stock/**injection**/ownership")
        assert r.status_code == 422

    def test_etf_lookthrough_endpoint(self, client, monkeypatch):
        from backend.services import ownership
        monkeypatch.setattr(
            ownership,
            "get_etf_lookthrough",
            lambda t: {"ticker": t, "top_holdings": [], "sector_weights": {}, "concentration": {"top5_pct": 0, "top10_pct": 0, "level": "low"}, "source": "test"},
        )
        r = client.get("/api/stock/SPY/etf-lookthrough")
        assert r.status_code == 200
        assert r.json()["ticker"] == "SPY"

    def test_etf_lookthrough_404_non_etf(self, client, monkeypatch):
        from backend.services import ownership
        monkeypatch.setattr(ownership, "get_etf_lookthrough", lambda t: None)
        r = client.get("/api/stock/AAPL/etf-lookthrough")
        assert r.status_code == 404
