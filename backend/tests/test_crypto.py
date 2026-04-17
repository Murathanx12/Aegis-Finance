"""Tests for crypto + DeFi services (HTTP mocked)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.services import crypto_market as cm
from backend.services import defi_metrics as dm
from backend.cache import cache_clear


@pytest.fixture(autouse=True)
def _clear_cache():
    cache_clear()
    yield
    cache_clear()


# ── crypto_market ──────────────────────────────────────────────────────


def test_default_coin_list_nonempty():
    assert "bitcoin" in cm.DEFAULT_TOP_COINS
    assert "ethereum" in cm.DEFAULT_TOP_COINS


def test_fetch_markets_parses_payload():
    fake = [
        {
            "id": "bitcoin", "symbol": "btc", "name": "Bitcoin",
            "current_price": 90000.0, "market_cap": 1.7e12,
            "market_cap_rank": 1, "total_volume": 4.2e10,
            "price_change_percentage_1h_in_currency": 0.1,
            "price_change_percentage_24h_in_currency": 1.5,
            "price_change_percentage_7d_in_currency": -2.0,
            "price_change_percentage_30d_in_currency": 5.0,
            "ath": 99000.0, "ath_change_percentage": -9.0,
            "ath_date": "2025-01-01",
            "circulating_supply": 19_500_000, "total_supply": 21_000_000,
        }
    ]
    with patch.object(cm, "_get", return_value=fake):
        rows = cm.fetch_markets(ids=["bitcoin"])
    assert len(rows) == 1
    assert rows[0]["symbol"] == "BTC"
    assert rows[0]["price"] == 90000.0


def test_fetch_markets_handles_none():
    """Bypass cache by using a unique id; verify None upstream → empty list."""
    with patch.object(cm, "_get", return_value=None):
        rows = cm.fetch_markets(ids=["test_handles_none_only"])
    assert rows == []


def test_summarise_aggregates():
    rows = [
        {"market_cap": 100, "volume_24h": 50, "change_24h_pct": 1.0},
        {"market_cap": 200, "volume_24h": 25, "change_24h_pct": -0.5},
        {"market_cap": 300, "volume_24h": 75, "change_24h_pct": 2.0},
    ]
    s = cm._summarise(rows)
    assert s["n"] == 3
    assert s["total_market_cap_usd"] == 600
    assert s["total_volume_24h_usd"] == 150
    assert s["advancers_24h"] == 2
    assert s["decliners_24h"] == 1


def test_summarise_empty():
    assert cm._summarise([]) == {"n": 0}


def test_fetch_history_parses_pairs():
    fake = {
        "prices": [[1700000000000, 30000], [1700086400000, 31000]],
        "total_volumes": [[1700000000000, 1.0e9], [1700086400000, 1.5e9]],
    }
    with patch.object(cm, "_get", return_value=fake):
        out = cm.fetch_history("bitcoin", days=2)
    assert len(out) == 2
    assert out[0]["price"] == 30000
    assert out[1]["volume"] == 1.5e9


def test_crypto_dashboard_returns_summary(monkeypatch):
    fake_rows = [{"market_cap": 100, "volume_24h": 50, "change_24h_pct": 1}]
    monkeypatch.setattr(cm, "fetch_markets", lambda **kw: fake_rows)
    out = cm.crypto_dashboard(top_n=1)
    assert out["coins"] == fake_rows
    assert out["summary"]["n"] == 1
    assert "CoinGecko" in out["source"]


# ── defi_metrics ──────────────────────────────────────────────────────


def test_total_tvl_picks_last_record():
    fake = [
        {"date": 1700000000, "tvl": 50e9},
        {"date": 1700086400, "tvl": 55e9},
    ]
    with patch.object(dm, "_get", return_value=fake):
        out = dm.fetch_total_tvl()
    assert out["tvl_usd"] == 55e9


def test_chains_tvl_sorted_desc():
    fake = [
        {"name": "Ethereum", "tvl": 60e9, "tokenSymbol": "ETH", "chainId": 1},
        {"name": "Solana", "tvl": 8e9, "tokenSymbol": "SOL"},
        {"name": "Tron", "tvl": 30e9, "tokenSymbol": "TRX"},
    ]
    with patch.object(dm, "_get", return_value=fake):
        rows = dm.fetch_chains_tvl(top_n=3)
    assert [r["name"] for r in rows] == ["Ethereum", "Tron", "Solana"]


def test_protocols_filters_zero_tvl():
    fake = [
        {"name": "AaveV3", "tvl": 12e9, "category": "Lending", "chain": "Ethereum"},
        {"name": "DeadProtocol", "tvl": 0, "category": "DEX", "chain": "BSC"},
        {"name": "Lido", "tvl": 25e9, "category": "Liquid Staking", "chain": "Ethereum"},
    ]
    with patch.object(dm, "_get", return_value=fake):
        rows = dm.fetch_protocols(top_n=10)
    names = [r["name"] for r in rows]
    assert "DeadProtocol" not in names
    assert names[0] == "Lido"  # higher TVL ranked first


def test_trend_pct_handles_short_series():
    history = [{"tvl_usd": 100}, {"tvl_usd": 110}]
    assert dm._trend_pct(history, 1) == 10.0


def test_trend_pct_zero_start():
    history = [{"tvl_usd": 0}, {"tvl_usd": 100}]
    assert dm._trend_pct(history, 1) is None


def test_defi_dashboard_composes(monkeypatch):
    monkeypatch.setattr(dm, "fetch_total_tvl", lambda: {"tvl_usd": 200e9, "as_of_unix": 1700000000})
    monkeypatch.setattr(
        dm, "fetch_tvl_history",
        lambda days: [{"ts": 1, "tvl_usd": 180e9}, {"ts": 2, "tvl_usd": 200e9}],
    )
    monkeypatch.setattr(dm, "fetch_chains_tvl", lambda top_n: [{"name": "Ethereum", "tvl_usd": 90e9}])
    monkeypatch.setattr(dm, "fetch_protocols", lambda top_n: [{"name": "Lido", "tvl_usd": 25e9}])
    out = dm.defi_dashboard()
    assert out["total_tvl_usd"] == 200e9
    assert out["top_chains"][0]["name"] == "Ethereum"
    # Trend should be positive
    assert out["trend"]["tvl_change_1d_pct"] is not None
