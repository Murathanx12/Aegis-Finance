"""
Aegis Finance — DeFi Metrics
==============================

DeFi total value locked (TVL) by chain and protocol via the DefiLlama
open API (no key, no rate limit hard cap). Lets users see a Bloomberg-
adjacent on-chain liquidity picture without paying for Glassnode.

Public surface
--------------
- ``fetch_total_tvl()``                   — current global DeFi TVL
- ``fetch_tvl_history(days=90)``          — global TVL series
- ``fetch_chains_tvl(top_n=20)``          — TVL by chain
- ``fetch_protocols(top_n=30)``           — TVL by protocol (sortable)
- ``defi_dashboard()``                     — composite UI rollup

Why this exists
---------------
On-chain TVL is the single best free proxy for DeFi flow + crypto-
market risk-on / risk-off appetite. DefiLlama covers 7,000+ protocols
across 500+ chains and exposes everything via JSON.
"""

from __future__ import annotations

import logging
from typing import Optional

import requests

from backend.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

_BASE = "https://api.llama.fi"
_TIMEOUT = 12
_TVL_TTL = 600  # 10 min


def _get(path: str) -> Optional[object]:
    try:
        r = requests.get(f"{_BASE}{path}", timeout=_TIMEOUT)
        if r.status_code in (401, 403):
            return None
        if r.status_code == 429:
            logger.warning("DefiLlama rate-limited")
            return None
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.debug("DefiLlama %s failed: %s", path, e)
        return None


def fetch_total_tvl() -> Optional[dict]:
    """Latest snapshot from /v2/historicalChainTvl (global series tail)."""
    cache_key = "defi_total_tvl"
    cached = cache_get(cache_key, _TVL_TTL)
    if cached is not None:
        return cached
    data = _get("/v2/historicalChainTvl")
    if not isinstance(data, list) or not data:
        return None
    last = data[-1]
    out = {
        "tvl_usd": float(last.get("tvl") or 0),
        "as_of_unix": int(last.get("date") or 0),
    }
    cache_set(cache_key, out)
    return out


def fetch_tvl_history(days: int = 90) -> list[dict]:
    """Global DeFi TVL daily history (latest N days)."""
    days = max(7, min(int(days), 1825))
    cache_key = f"defi_tvl_history:{days}"
    cached = cache_get(cache_key, _TVL_TTL)
    if cached is not None:
        return cached

    data = _get("/v2/historicalChainTvl")
    if not isinstance(data, list):
        return []
    series = [
        {"ts": int(p.get("date") or 0), "tvl_usd": float(p.get("tvl") or 0)}
        for p in data[-days:]
    ]
    cache_set(cache_key, series)
    return series


def fetch_chains_tvl(top_n: int = 20) -> list[dict]:
    """TVL by chain, sorted descending (Ethereum, Solana, Tron, ...)."""
    cache_key = f"defi_chains:{top_n}"
    cached = cache_get(cache_key, _TVL_TTL)
    if cached is not None:
        return cached

    data = _get("/v2/chains")
    if not isinstance(data, list):
        return []
    rows = [
        {
            "name": c.get("name"),
            "tvl_usd": float(c.get("tvl") or 0),
            "token_symbol": c.get("tokenSymbol"),
            "chain_id": c.get("chainId"),
        }
        for c in data
        if c.get("tvl") is not None
    ]
    rows.sort(key=lambda r: r["tvl_usd"], reverse=True)
    rows = rows[: max(1, top_n)]
    cache_set(cache_key, rows)
    return rows


def fetch_protocols(top_n: int = 30) -> list[dict]:
    """Top N DeFi protocols by TVL with category metadata."""
    cache_key = f"defi_protocols:{top_n}"
    cached = cache_get(cache_key, _TVL_TTL)
    if cached is not None:
        return cached

    data = _get("/protocols")
    if not isinstance(data, list):
        return []
    rows = [
        {
            "name": p.get("name"),
            "symbol": p.get("symbol"),
            "category": p.get("category"),
            "chain": p.get("chain"),
            "tvl_usd": float(p.get("tvl") or 0),
            "change_1d_pct": p.get("change_1d"),
            "change_7d_pct": p.get("change_7d"),
            "url": p.get("url"),
        }
        for p in data
        if p.get("tvl")
    ]
    rows.sort(key=lambda r: r["tvl_usd"], reverse=True)
    rows = rows[: max(1, top_n)]
    cache_set(cache_key, rows)
    return rows


def _trend_pct(history: list[dict], days: int) -> Optional[float]:
    """Compute % change in TVL over the last N days from a tail series."""
    if not history or len(history) < 2:
        return None
    pts = history[-days - 1 :] if len(history) > days else history
    start = pts[0]["tvl_usd"]
    end = pts[-1]["tvl_usd"]
    if start <= 0:
        return None
    return round((end - start) / start * 100, 4)


def defi_dashboard() -> dict:
    """One-call rollup for a UI: total TVL + 1d/7d/30d trend + top chains + protocols."""
    snap = fetch_total_tvl()
    history = fetch_tvl_history(60)
    chains = fetch_chains_tvl(top_n=10)
    protocols = fetch_protocols(top_n=15)

    trend = {
        "tvl_change_1d_pct": _trend_pct(history, 1),
        "tvl_change_7d_pct": _trend_pct(history, 7),
        "tvl_change_30d_pct": _trend_pct(history, 30),
    }
    return {
        "total_tvl_usd": (snap or {}).get("tvl_usd"),
        "as_of_unix": (snap or {}).get("as_of_unix"),
        "trend": trend,
        "top_chains": chains,
        "top_protocols": protocols,
        "source": "DefiLlama (https://defillama.com)",
    }
