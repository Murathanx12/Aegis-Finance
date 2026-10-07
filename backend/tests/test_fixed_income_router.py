"""GET /api/analytics/fixed-income — Q15 (2026-10-07).

`get_fixed_income_dashboard()` now returns a `degraded` flag instead of
letting an empty-series read pass for a healthy one. This file pins that the
ROUTER actually surfaces that flag in its response body, and that a degraded
read is not cached for 30 minutes as if it were healthy (a transient FRED
outage should not be force-fed to every request for the next half hour).

Offline: `backend.services.fixed_income.get_fixed_income_dashboard` is
monkeypatched directly, so no network and no real FRED call happens.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend import cache as _cache
from backend.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_cache():
    _cache.cache_clear()
    yield
    _cache.cache_clear()


def test_degraded_response_surfaces_the_flag(monkeypatch):
    degraded_payload = {
        "yield_curve": {"error": "No yield curve data available", "yields": {}},
        "credit": {"spreads": {}, "real_yield_10y": None,
                   "breakeven_inflation_10y": None,
                   "stress": {"level": "UNKNOWN", "signals": [],
                              "missing_because": "no credit-spread FRED series loaded"}},
        "degraded": True,
        "missing_series": ["hy_oas", "ig_oas"],
    }
    monkeypatch.setattr(
        "backend.services.fixed_income.get_fixed_income_dashboard",
        lambda: degraded_payload,
    )
    r = client.get("/api/analytics/fixed-income")
    assert r.status_code == 200
    body = r.json()
    assert body["degraded"] is True
    assert body["credit"]["stress"]["level"] == "UNKNOWN"


def test_degraded_response_is_not_cached(monkeypatch):
    calls = {"n": 0}

    def _flaky():
        calls["n"] += 1
        return {"yield_curve": {"yields": {}}, "credit": {"spreads": {}},
                "degraded": True, "missing_series": ["hy_oas"]}

    monkeypatch.setattr(
        "backend.services.fixed_income.get_fixed_income_dashboard", _flaky
    )
    client.get("/api/analytics/fixed-income")
    client.get("/api/analytics/fixed-income")
    # Both calls hit the service — a degraded read must not be served from
    # the 30-min cache on the second request.
    assert calls["n"] == 2


def test_healthy_response_is_cached(monkeypatch):
    calls = {"n": 0}

    def _healthy():
        calls["n"] += 1
        return {"yield_curve": {"yields": {"10y": 4.0}}, "credit": {"spreads": {}},
                "degraded": False, "missing_series": []}

    monkeypatch.setattr(
        "backend.services.fixed_income.get_fixed_income_dashboard", _healthy
    )
    client.get("/api/analytics/fixed-income")
    client.get("/api/analytics/fixed-income")
    assert calls["n"] == 1
