"""Tests for polygon_client — exercised without network where possible."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.services import polygon_client as pc


def _client_no_key():
    """Build a PolygonClient that reports itself as unavailable."""
    with patch.object(pc.api_keys, "has", return_value=False):
        return pc.PolygonClient()


def test_unavailable_when_no_api_key():
    client = _client_no_key()
    assert client.available is False
    assert client._client is None


def test_snapshot_returns_none_when_unavailable():
    assert _client_no_key().get_snapshot("AAPL") is None


def test_previous_close_returns_none_when_unavailable():
    assert _client_no_key().get_previous_close("AAPL") is None


def test_ticker_details_returns_none_when_unavailable():
    assert _client_no_key().get_ticker_details("AAPL") is None


def test_intraday_bars_returns_none_when_unavailable():
    assert _client_no_key().get_intraday_bars("AAPL") is None


def test_market_status_returns_none_when_unavailable():
    assert _client_no_key().get_market_status() is None


def test_snapshot_parses_polygon_object_fields():
    """Ensure get_snapshot extracts expected fields and populates the cache."""
    if not pc.HAS_POLYGON:
        pytest.skip("polygon-api-client not installed")

    fake_day = SimpleNamespace(open=100.0, high=105.0, low=99.0, close=104.0, volume=1_000_000, vwap=102.0)
    fake_prev = SimpleNamespace(open=98.0, high=102.0, low=97.0, close=101.0, volume=900_000, vwap=100.0)
    fake_snapshot = SimpleNamespace(
        updated=1_700_000_000_000_000_000,
        day=fake_day,
        prev_day=fake_prev,
        todays_change=3.0,
        todays_change_perc=3.0,
    )
    mock_rest = MagicMock()
    mock_rest.get_snapshot_ticker.return_value = fake_snapshot

    with patch.object(pc.api_keys, "has", return_value=True), \
         patch.object(pc.api_keys, "polygon", "dummy", create=True), \
         patch.object(pc, "RESTClient", return_value=mock_rest, create=True):
        client = pc.PolygonClient()
        # Invalidate cache by namespacing ticker
        result = client.get_snapshot("ZZZ_TEST")

    assert result is not None
    assert result["ticker"] == "ZZZ_TEST"
    assert result["day"]["close"] == 104.0
    assert result["prev_day"]["close"] == 101.0
    assert result["change"] == 3.0
    assert result["change_pct"] == 3.0


def test_snapshot_handles_missing_day_block():
    """A ticker with no intraday data (e.g. pre-market or delisted) should still return cleanly."""
    if not pc.HAS_POLYGON:
        pytest.skip("polygon-api-client not installed")

    fake_snapshot = SimpleNamespace(updated=None, day=None, prev_day=None)
    mock_rest = MagicMock()
    mock_rest.get_snapshot_ticker.return_value = fake_snapshot

    with patch.object(pc.api_keys, "has", return_value=True), \
         patch.object(pc.api_keys, "polygon", "dummy", create=True), \
         patch.object(pc, "RESTClient", return_value=mock_rest, create=True):
        client = pc.PolygonClient()
        result = client.get_snapshot("ZZZ_MISSING")

    assert result is not None
    assert result["ticker"] == "ZZZ_MISSING"
    assert "day" not in result
    assert "prev_day" not in result


def test_snapshot_swallows_api_exception():
    if not pc.HAS_POLYGON:
        pytest.skip("polygon-api-client not installed")

    mock_rest = MagicMock()
    mock_rest.get_snapshot_ticker.side_effect = RuntimeError("network blip")

    with patch.object(pc.api_keys, "has", return_value=True), \
         patch.object(pc.api_keys, "polygon", "dummy", create=True), \
         patch.object(pc, "RESTClient", return_value=mock_rest, create=True):
        client = pc.PolygonClient()
        result = client.get_snapshot("ZZZ_ERR")

    assert result is None
