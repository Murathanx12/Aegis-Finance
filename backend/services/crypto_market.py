"""
Aegis Finance — Crypto Market Snapshot
========================================

Spot prices, 24h volume / market cap, and 7-day price history for the
top crypto assets via the CoinGecko v3 demo API. Free, no key required
(rate limit ≈ 30 req/min — covered by our cache).

Public surface
--------------
- ``DEFAULT_TOP_COINS``                 — id list passed to CoinGecko
- ``fetch_markets(ids=None, vs="usd")`` — current snapshot table
- ``fetch_history(coin_id, days=30)``   — daily price history
- ``crypto_dashboard(top_n=20)``        — UI rollup with sparklines

Why this exists
---------------
Both Koyfin Pro and OpenBB shipped first-class crypto in 2025-26.
Aegis previously only had equities + FX/commodity context. Adding a
slim crypto+DeFi tab keeps the platform comparable to retail terminals
without committing to a wallet integration or DEX trading code.
"""

from __future__ import annotations

import logging
from typing import Optional

import requests

from backend.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

_BASE = "https://api.coingecko.com/api/v3"
_TIMEOUT = 10
_SNAPSHOT_TTL = 180   # 3 min — free tier rate-limit friendly
_HISTORY_TTL = 1800   # 30 min

# Stable list of top cap coins — kept short to stay under free-tier limits.
DEFAULT_TOP_COINS: list[str] = [
    "bitcoin",
    "ethereum",
    "tether",
    "solana",
    "binancecoin",
    "ripple",
    "usd-coin",
    "dogecoin",
    "cardano",
    "tron",
    "avalanche-2",
    "chainlink",
    "polkadot",
    "polygon-pos",
    "litecoin",
    "internet-computer",
    "uniswap",
    "stellar",
    "aptos",
    "near",
]


def _get(path: str, params: Optional[dict] = None) -> Optional[object]:
    """Light wrapper around requests with a defensive timeout."""
    try:
        r = requests.get(f"{_BASE}/{path}", params=params or {}, timeout=_TIMEOUT)
        if r.status_code in (401, 403):
            return None
        if r.status_code == 429:
            logger.warning("CoinGecko rate-limited")
            return None
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.debug("CoinGecko request %s failed: %s", path, e)
        return None


def fetch_markets(
    ids: Optional[list[str]] = None,
    vs: str = "usd",
    *,
    sparkline: bool = False,
) -> list[dict]:
    """Snapshot table (price, mcap, 24h vol, 24h Δ, ATH) for given coin ids."""
    coin_ids = ids or DEFAULT_TOP_COINS
    cache_key = f"crypto_markets:{','.join(coin_ids)}:{vs}:{int(sparkline)}"
    cached = cache_get(cache_key, _SNAPSHOT_TTL)
    if cached is not None:
        return cached

    params = {
        "vs_currency": vs,
        "ids": ",".join(coin_ids),
        "order": "market_cap_desc",
        "per_page": min(len(coin_ids), 100),
        "page": 1,
        "sparkline": str(sparkline).lower(),
        "price_change_percentage": "1h,24h,7d,30d",
    }
    data = _get("coins/markets", params=params)
    if not isinstance(data, list):
        return []

    rows: list[dict] = []
    for c in data:
        rows.append(
            {
                "id": c.get("id"),
                "symbol": (c.get("symbol") or "").upper(),
                "name": c.get("name"),
                "price": c.get("current_price"),
                "market_cap": c.get("market_cap"),
                "market_cap_rank": c.get("market_cap_rank"),
                "volume_24h": c.get("total_volume"),
                "change_1h_pct": c.get("price_change_percentage_1h_in_currency"),
                "change_24h_pct": c.get("price_change_percentage_24h_in_currency"),
                "change_7d_pct": c.get("price_change_percentage_7d_in_currency"),
                "change_30d_pct": c.get("price_change_percentage_30d_in_currency"),
                "ath": c.get("ath"),
                "ath_change_pct": c.get("ath_change_percentage"),
                "ath_date": c.get("ath_date"),
                "circulating_supply": c.get("circulating_supply"),
                "total_supply": c.get("total_supply"),
            }
        )
    cache_set(cache_key, rows)
    return rows


def fetch_history(coin_id: str, days: int = 30, vs: str = "usd") -> list[dict]:
    """Daily OHLC-ish series for a single coin (CoinGecko market_chart)."""
    coin_id = coin_id.lower().strip()
    days = max(1, min(int(days), 365))

    cache_key = f"crypto_history:{coin_id}:{days}:{vs}"
    cached = cache_get(cache_key, _HISTORY_TTL)
    if cached is not None:
        return cached

    data = _get(
        f"coins/{coin_id}/market_chart",
        params={"vs_currency": vs, "days": days, "interval": "daily"},
    )
    if not isinstance(data, dict):
        return []

    prices = data.get("prices") or []
    vols = data.get("total_volumes") or []
    series: list[dict] = []
    for i, (ts, price) in enumerate(prices):
        v = vols[i][1] if i < len(vols) else None
        series.append({"ts_ms": int(ts), "price": price, "volume": v})
    cache_set(cache_key, series)
    return series


def _summarise(rows: list[dict]) -> dict:
    """Aggregate stats across a coin universe — useful for risk-on/off reads."""
    if not rows:
        return {"n": 0}
    total_mcap = sum(r.get("market_cap") or 0 for r in rows)
    total_vol = sum(r.get("volume_24h") or 0 for r in rows)
    avg_24h = sum(
        (r.get("change_24h_pct") or 0)
        for r in rows
        if r.get("change_24h_pct") is not None
    ) / max(len(rows), 1)
    movers_up = sum(1 for r in rows if (r.get("change_24h_pct") or 0) > 0)
    return {
        "n": len(rows),
        "total_market_cap_usd": total_mcap,
        "total_volume_24h_usd": total_vol,
        "avg_change_24h_pct": round(avg_24h, 4),
        "advancers_24h": movers_up,
        "decliners_24h": len(rows) - movers_up,
    }


def crypto_dashboard(top_n: int = 20) -> dict:
    """Top N coins + summary block. Falls back to empty list if API blocked."""
    ids = DEFAULT_TOP_COINS[: max(1, min(top_n, len(DEFAULT_TOP_COINS)))]
    rows = fetch_markets(ids=ids)
    return {
        "coins": rows,
        "summary": _summarise(rows),
        "source": "CoinGecko v3 (demo)",
    }
