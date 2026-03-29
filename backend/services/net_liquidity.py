"""
Aegis Finance — Net Liquidity Tracker
=======================================

Formula: Net Liquidity = WALCL - (TGA + RRP)

- WALCL (Fed total assets): liquidity injection
- WTREGEN (Treasury General Account): drains liquidity when rising
- RRPONTSYD (Overnight reverse repos): drains liquidity when rising

Interpretation:
- Rising Net Liquidity = more money in system = BULLISH
- Falling Net Liquidity = money being drained = BEARISH (crash risk)

Adapted from V6 services/net_liquidity_service.py.

Usage:
    from backend.services.net_liquidity import get_net_liquidity
"""

import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from backend.config import api_keys
from backend.cache import cache_get, cache_set

logger = logging.getLogger(__name__)


def get_net_liquidity() -> dict:
    """Returns current and historical Net Liquidity data.

    Returns:
        Dict with current snapshot, formula, history (52 weeks), signal.
    """
    cached = cache_get("net_liquidity", 86400)  # 24hr TTL (WALCL is weekly)
    if cached is not None:
        return cached

    try:
        result = _fetch_and_calculate()
        cache_set("net_liquidity", result)
        return result
    except Exception as e:
        logger.error("Net liquidity fetch failed: %s", e)
        return _default_response(str(e))


def _fetch_and_calculate() -> dict:
    if not api_keys.has("fred"):
        return _default_response("FRED_API_KEY not set")

    try:
        from fredapi import Fred
    except ImportError:
        return _default_response("fredapi not installed")

    fred = Fred(api_key=api_keys.fred)

    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * 3)

    walcl = fred.get_series("WALCL", start_date, end_date)
    tga = fred.get_series("WTREGEN", start_date, end_date)
    rrp = fred.get_series("RRPONTSYD", start_date, end_date)

    # Align to weekly frequency (WALCL is weekly, others daily)
    df = pd.DataFrame({
        "walcl": walcl,
        "tga": tga,
        "rrp": rrp * 1000,  # Convert billions to millions
    }).dropna(how="all").resample("W").last().dropna()

    if len(df) < 4:
        return _default_response("Insufficient data from FRED")

    # Net Liquidity = WALCL - (TGA + RRP)
    df["net_liquidity"] = df["walcl"] - (df["tga"] + df["rrp"])

    # Normalize to trillions for display
    df_t = df / 1_000_000

    df_t["net_liq_change_wow"] = df_t["net_liquidity"].diff()
    df_t["net_liq_change_pct"] = df_t["net_liquidity"].pct_change() * 100

    current = df_t.iloc[-1]

    wow_change = float(current.get("net_liq_change_wow", 0))
    if pd.isna(wow_change):
        wow_change = 0.0

    if wow_change > 0.05:
        signal = "BULLISH"
    elif wow_change < -0.05:
        signal = "BEARISH"
    else:
        signal = "NEUTRAL"

    # History for chart (last 52 weeks)
    history = []
    for date, row in df_t.tail(52).iterrows():
        wow = row.get("net_liq_change_wow", 0)
        history.append({
            "date": date.strftime("%Y-%m-%d"),
            "walcl": round(float(row["walcl"]), 3),
            "tga": round(float(row["tga"]), 3),
            "rrp": round(float(row["rrp"]), 3),
            "net_liquidity": round(float(row["net_liquidity"]), 3),
            "wow_change": round(float(wow if not pd.isna(wow) else 0), 4),
        })

    wow_pct = current.get("net_liq_change_pct", 0)

    return {
        "current": {
            "walcl": round(float(current["walcl"]), 3),
            "tga": round(float(current["tga"]), 3),
            "rrp": round(float(current["rrp"]), 3),
            "net_liquidity": round(float(current["net_liquidity"]), 3),
            "wow_change": round(wow_change, 4),
            "wow_change_pct": round(float(wow_pct if not pd.isna(wow_pct) else 0), 2),
            "signal": signal,
        },
        "formula": "Net_Liq = WALCL - (TGA + RRP)",
        "unit": "Trillions USD",
        "history": history,
        "last_updated": datetime.now().isoformat(),
    }


def _default_response(error: str = "") -> dict:
    return {
        "current": {
            "walcl": None,
            "tga": None,
            "rrp": None,
            "net_liquidity": None,
            "wow_change": None,
            "wow_change_pct": None,
            "signal": "UNKNOWN",
        },
        "formula": "Net_Liq = WALCL - (TGA + RRP)",
        "unit": "Trillions USD",
        "history": [],
        "error": error or "Data unavailable",
        "last_updated": datetime.now().isoformat(),
    }
