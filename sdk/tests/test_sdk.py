"""Unit tests for the Aegis SDK — all requests mocked.

Run from the repo root with:
    python -m pytest sdk/tests/ -v
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Make the SDK importable when running from repo root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import aegis  # noqa: E402
from aegis.client import AegisClient, AegisError, default_client, configure  # noqa: E402


@pytest.fixture(autouse=True)
def reset_default_client():
    """Each test starts from a fresh default client so they don't bleed."""
    import aegis.client as client_mod
    client_mod._default_client = None
    yield
    client_mod._default_client = None


# ── Client behaviour ─────────────────────────────────────────────────────────


class TestAegisClient:
    def test_default_base_url(self):
        c = AegisClient()
        assert c.base_url == "http://localhost:8000"

    def test_env_var_override(self, monkeypatch):
        monkeypatch.setenv("AEGIS_API_URL", "https://staging.example.com/")
        c = AegisClient()
        assert c.base_url == "https://staging.example.com"  # trailing slash stripped

    def test_explicit_base_url_wins(self, monkeypatch):
        monkeypatch.setenv("AEGIS_API_URL", "https://ignored.example.com")
        c = AegisClient(base_url="https://chosen.example.com")
        assert c.base_url == "https://chosen.example.com"

    def test_get_serialises_json(self):
        c = AegisClient()
        with patch("aegis.client.requests.request") as r:
            r.return_value = _fake_response(200, {"ok": True})
            out = c.get("/api/foo", params={"x": 1})
            assert out == {"ok": True}
            args, kwargs = r.call_args
            assert args[0] == "GET"
            assert args[1] == "http://localhost:8000/api/foo"
            assert kwargs["params"] == {"x": 1}

    def test_post_serialises_json_body(self):
        c = AegisClient()
        with patch("aegis.client.requests.request") as r:
            r.return_value = _fake_response(200, {"ok": True})
            c.post("/api/foo", json={"a": 1})
            _, kwargs = r.call_args
            assert kwargs["json"] == {"a": 1}

    def test_non_2xx_raises_aegis_error(self):
        c = AegisClient()
        with patch("aegis.client.requests.request") as r:
            r.return_value = _fake_response(404, {"detail": "gone"})
            with pytest.raises(AegisError) as excinfo:
                c.get("/api/missing")
            assert excinfo.value.status_code == 404
            assert excinfo.value.payload == {"detail": "gone"}

    def test_5xx_retries_then_succeeds(self):
        c = AegisClient(max_retries=1)
        responses = [_fake_response(503, {"detail": "down"}), _fake_response(200, {"ok": True})]
        with patch("aegis.client.requests.request", side_effect=responses), patch(
            "aegis.client.time.sleep"
        ):
            out = c.get("/api/flaky")
            assert out == {"ok": True}

    def test_html_response_returned_as_text(self):
        c = AegisClient()
        with patch("aegis.client.requests.request") as r:
            r.return_value = _fake_response(200, None, content_type="text/html", text="<h1>hi</h1>")
            out = c.get("/api/tearsheet.html")
            assert out == "<h1>hi</h1>"

    def test_binary_response_returned_as_bytes(self):
        c = AegisClient()
        with patch("aegis.client.requests.request") as r:
            r.return_value = _fake_response(
                200, None, content_type="application/octet-stream", content=b"PKBINARY"
            )
            out = c.get("/api/tearsheet.xlsx")
            assert out == b"PKBINARY"


class TestConfigure:
    def test_configure_replaces_default_client(self):
        c = configure(base_url="https://x.example.com", timeout=120)
        assert c.base_url == "https://x.example.com"
        assert default_client() is c
        assert c.timeout == 120


# ── Namespace dispatch (spot-check one per namespace) ────────────────────────


class TestNamespaces:
    def test_equity_snapshot(self):
        with patch("aegis.client.requests.request") as r:
            r.return_value = _fake_response(200, {"ticker": "AAPL", "price": 230.0})
            out = aegis.equity.snapshot("aapl")
            assert out["price"] == 230.0
            args, _ = r.call_args
            assert args[1].endswith("/api/realtime/AAPL")

    def test_equity_ownership(self):
        with patch("aegis.client.requests.request") as r:
            r.return_value = _fake_response(200, {"ticker": "AAPL", "holders": []})
            aegis.equity.ownership("AAPL")
            args, _ = r.call_args
            assert args[1].endswith("/api/stock/AAPL/ownership")

    def test_portfolio_optimize_mpc_strips_none(self):
        with patch("aegis.client.requests.request") as r:
            r.return_value = _fake_response(200, {"status": "optimal"})
            aegis.portfolio.optimize_mpc(
                ["AAPL", "MSFT"],
                tracking_error_limit=None,  # must be stripped
                gamma=5.0,
            )
            _, kwargs = r.call_args
            assert "tracking_error_limit" not in kwargs["json"]
            assert kwargs["json"]["gamma"] == 5.0
            assert kwargs["json"]["tickers"] == ["AAPL", "MSFT"]

    def test_risk_crash_probability_params(self):
        with patch("aegis.client.requests.request") as r:
            r.return_value = _fake_response(200, {"prob": 0.12})
            aegis.risk.crash_probability(horizon="6m", explain=True)
            _, kwargs = r.call_args
            assert kwargs["params"] == {"horizon": "6m", "explain": "true"}

    def test_macro_status(self):
        with patch("aegis.client.requests.request") as r:
            r.return_value = _fake_response(200, {"regime": "Bull"})
            aegis.macro.status()
            args, _ = r.call_args
            assert args[1].endswith("/api/market-status")

    def test_calendar_earnings_adds_ticker_param(self):
        with patch("aegis.client.requests.request") as r:
            r.return_value = _fake_response(200, {"count": 0})
            aegis.calendar.earnings("nvda", days_ahead=7)
            _, kwargs = r.call_args
            assert kwargs["params"]["ticker"] == "NVDA"
            assert kwargs["params"]["days_ahead"] == 7

    def test_world_providers(self):
        with patch("aegis.client.requests.request") as r:
            r.return_value = _fake_response(200, {"providers": []})
            aegis.world.providers()
            args, _ = r.call_args
            assert args[1].endswith("/api/providers")


# ── Helpers ──────────────────────────────────────────────────────────────────


def _fake_response(
    status: int,
    json_body,
    *,
    content_type: str = "application/json",
    text: str | None = None,
    content: bytes | None = None,
) -> MagicMock:
    m = MagicMock()
    m.status_code = status
    m.ok = status < 400
    m.headers = {"Content-Type": content_type}
    if json_body is not None:
        m.json.return_value = json_body
    if text is not None:
        m.text = text
    if content is not None:
        m.content = content
    return m
