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


# ── Crypto RISK-APPETITE SENSOR (chunk C16, 2026-10-07) ──────────────────────
#
# WE DO NOT TRADE IT. Three public, keyless inputs as MARKET-STATE readings with
# their own timestamps: total stablecoin supply (DeFiLlama), perpetual funding
# rates (Binance + OKX public endpoints) and BTC/ETH spot (CoinGecko). One row
# per snapshot in `public_flow/tables/crypto_risk_sensor.jsonl`. A component
# that fails is written as REFUSED with its reason and the snapshot is DEGRADED:
# a failed fetch is never a zero (the false-zero lesson).

SENSOR_BANNER = ("SENSOR -- crypto risk appetite as market state (stablecoin supply, "
                 "funding, spot); never traded, never a signal on its own")
SENSOR_TABLE = "crypto_risk_sensor"
FUNDING_SYMBOLS = {"BTC": ("BTCUSDT", "BTC-USDT-SWAP"), "ETH": ("ETHUSDT", "ETH-USDT-SWAP")}


def _sensor_get(url: str, params: Optional[dict] = None) -> object:
    """One GET that RAISES on any failure (the sensor path; `_get` above returns
    None for the UI path, which must not be reused here). Tests patch this."""
    r = requests.get(url, params=params or {}, timeout=_TIMEOUT,
                     headers={"User-Agent": "AegisFinance-reader/1.0 (personal research; read-only)"})
    r.raise_for_status()
    return r.json()


def _ms_iso(ms) -> Optional[str]:
    from datetime import datetime, timezone
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError):
        return None


def fetch_stablecoin_supply() -> dict:
    """Total USD-pegged stablecoin circulating supply, today and its prior-day /
    week / month readings (DeFiLlama `stablecoins`; cite "DefiLlama")."""
    from backend import config as _cfg
    d = _sensor_get(f"{_cfg.DEFILLAMA_STABLECOINS_BASE}/stablecoins", {"includePrices": "false"})
    assets = (d or {}).get("peggedAssets") if isinstance(d, dict) else None
    if not assets:
        raise ValueError("DeFiLlama returned no peggedAssets")

    def tot(key: str) -> Optional[float]:
        vals = [((a.get(key) or {}).get("peggedUSD")) for a in assets
                if a.get("pegType") == "peggedUSD"]
        vals = [float(v) for v in vals if isinstance(v, (int, float))]
        return round(sum(vals), 2) if vals else None
    now, d1, w1, m1 = (tot("circulating"), tot("circulatingPrevDay"),
                       tot("circulatingPrevWeek"), tot("circulatingPrevMonth"))
    if not now:
        raise ValueError("DeFiLlama USD-pegged supply summed to nothing")

    def chg(prev: Optional[float]) -> Optional[float]:
        return round(now / prev - 1.0, 6) if prev else None
    return {"usd_pegged_supply": now, "chg_1d": chg(d1), "chg_7d": chg(w1), "chg_30d": chg(m1),
            "n_assets": len(assets), "source": "DefiLlama stablecoins API",
            "as_of": "fetch time (DefiLlama updates hourly)"}


def fetch_funding_rates() -> list[dict]:
    """Latest settled 8 h funding per venue and asset, with the venue's own
    settlement timestamp. Positive funding = longs pay shorts (leverage demand)."""
    from backend import config as _cfg
    out = []
    for asset, (bin_sym, okx_inst) in FUNDING_SYMBOLS.items():
        b = _sensor_get(f"{_cfg.BINANCE_FAPI_BASE}/fapi/v1/fundingRate", {"symbol": bin_sym, "limit": 1})
        if not isinstance(b, list) or not b:
            raise ValueError(f"Binance funding for {bin_sym} empty")
        out.append({"venue": "binance", "asset": asset, "funding_8h": float(b[-1]["fundingRate"]),
                    "settled_utc": _ms_iso(b[-1].get("fundingTime")),
                    "mark_price": float(b[-1]["markPrice"]) if b[-1].get("markPrice") else None})
        o = _sensor_get(f"{_cfg.OKX_API_BASE}/api/v5/public/funding-rate", {"instId": okx_inst})
        data = (o or {}).get("data") if isinstance(o, dict) else None
        if not data or str((o or {}).get("code")) != "0":
            raise ValueError(f"OKX funding for {okx_inst} empty or code {(o or {}).get('code')}")
        x = data[0]
        sett = x.get("settFundingRate")
        out.append({"venue": "okx", "asset": asset,
                    "funding_8h": float(sett) if sett not in (None, "") else None,
                    "settled_utc": _ms_iso(x.get("prevFundingTime")),
                    "current_period_rate": float(x["fundingRate"]) if x.get("fundingRate") else None,
                    "venue_ts_utc": _ms_iso(x.get("ts"))})
    return out


def fetch_spot() -> dict:
    """BTC and ETH spot in USD with CoinGecko's own last-updated time."""
    from datetime import datetime, timezone
    d = _sensor_get(f"{_BASE}/simple/price", {"ids": "bitcoin,ethereum", "vs_currencies": "usd",
                                               "include_last_updated_at": "true",
                                               "include_24hr_change": "true"})
    if not isinstance(d, dict) or not d.get("bitcoin") or not d.get("ethereum"):
        raise ValueError("CoinGecko simple/price missing bitcoin or ethereum")

    def one(k: str) -> dict:
        x = d[k]
        ts = x.get("last_updated_at")
        return {"usd": float(x["usd"]), "chg_24h_pct": x.get("usd_24h_change"),
                "venue_ts_utc": (datetime.fromtimestamp(int(ts), tz=timezone.utc)
                                 .isoformat(timespec="seconds") if ts else None)}
    return {"BTC": one("bitcoin"), "ETH": one("ethereum"), "source": "CoinGecko v3 simple/price"}


def risk_sensor_snapshot(*, write: bool = True, base=None, now=None) -> dict:
    """One snapshot of the three components; DEGRADED when any refused; REFUSED
    when all did. Written to the public-flow table and a receipt. Never trades."""
    from backend.services import public_flow_common as PF
    now = now or PF.now_utc()
    comp: dict = {}
    for name, fn in (("stablecoins", fetch_stablecoin_supply), ("funding", fetch_funding_rates),
                     ("spot", fetch_spot)):
        try:
            comp[name] = {"status": "OK", "fetched_utc": PF.iso(PF.now_utc()), "value": fn()}
        except Exception as exc:  # noqa: BLE001 -- a refused component is recorded, never zeroed
            comp[name] = {"status": "REFUSED", "why": f"{type(exc).__name__}: {str(exc)[:200]}"}
    ok = [k for k, v in comp.items() if v["status"] == "OK"]
    status = "OK" if len(ok) == len(comp) else ("REFUSED" if not ok else "DEGRADED")

    def val(name: str) -> dict:
        c = comp[name]
        return (c.get("value") or {}) if c["status"] == "OK" else {}
    fund = (comp["funding"].get("value") or []) if comp["funding"]["status"] == "OK" else []

    def avg_f(asset: str) -> Optional[float]:
        v = [f["funding_8h"] for f in fund if f["asset"] == asset and f.get("funding_8h") is not None]
        return round(sum(v) / len(v), 8) if v else None
    row = {"row_id": f"crypto_sensor:{PF.iso(now)}", "source": "crypto_risk_sensor",
           "snapshot_utc": PF.iso(now), "snapshot_date": now.date().isoformat(),
           "public_ts_basis": "FETCH_TIME (live market data)", "status": status,
           "usd_stablecoin_supply": val("stablecoins").get("usd_pegged_supply"),
           "stablecoin_chg_7d": val("stablecoins").get("chg_7d"),
           "btc_funding_8h_avg": avg_f("BTC"), "eth_funding_8h_avg": avg_f("ETH"),
           "btc_usd": (val("spot").get("BTC") or {}).get("usd"),
           "eth_usd": (val("spot").get("ETH") or {}).get("usd"),
           "components": comp, "banner": SENSOR_BANNER}
    out = {"status": status, "row": row}
    if write:
        wr = PF.append_rows(SENSOR_TABLE, [row], event_field="snapshot_date", base=base, now=now)
        out["rows_added"] = wr["written"]
        out["receipt"] = str(PF.write_receipt(
            "crypto_risk_sensor",
            {"status": status, "rows_added": wr["written"],
             "components": {k: (v["status"] if v["status"] == "OK" else v) for k, v in comp.items()},
             "banner": SENSOR_BANNER,
             "citation": "DefiLlama (stablecoins); Binance, OKX public market data; CoinGecko"},
            base, now))
    return out
