"""
Aegis Finance — Commodity Futures Curves
==========================================

Continuous-contract front-end commodity prices plus a multi-tenor curve
viewer that flags contango vs backwardation. Pulls front through 12-month
contracts from yfinance, since CME publishes settlement prices on a
public delay and that's all retail platforms expose for free.

Public surface
--------------
- ``DEFAULT_COMMODITIES`` — symbol map (WTI, Brent, NG, gold, silver, copper, ...)
- ``fetch_curve(symbol)`` — front + N month outright prices
- ``slope_diagnostics(curve)`` — contango/backwardation depth, term-structure roll yield
- ``commodity_dashboard()`` — table for UI

Why this matters
----------------
Bloomberg's CT/CTM futures pages are how energy and metals desks read
positioning. Koyfin shows continuous front prices but not the *curve*.
Adding a curve viewer + roll-yield analytic puts Aegis on par with the
free tier of Koyfin and ahead of OpenBB on commodities ergonomics.
"""

from __future__ import annotations

import logging
from typing import Optional

from backend.cache import cache_get, cache_set

logger = logging.getLogger(__name__)


# yfinance continuous front-month tickers per commodity. The "F" / "M*" / "U*"
# suffixes are CME month codes (e.g. CL=F front, CLM26.NYM = June 2026 WTI).
DEFAULT_COMMODITIES: dict[str, dict] = {
    "WTI": {
        "name": "WTI Crude Oil",
        "exchange": "NYM",
        "front": "CL=F",
        "prefix": "CL",
        "unit": "USD/bbl",
    },
    "BRENT": {
        "name": "Brent Crude Oil",
        "exchange": "NYM",
        "front": "BZ=F",
        "prefix": "BZ",
        "unit": "USD/bbl",
    },
    "NATGAS": {
        "name": "Natural Gas (Henry Hub)",
        "exchange": "NYM",
        "front": "NG=F",
        "prefix": "NG",
        "unit": "USD/MMBtu",
    },
    "GASOLINE": {
        "name": "RBOB Gasoline",
        "exchange": "NYM",
        "front": "RB=F",
        "prefix": "RB",
        "unit": "USD/gal",
    },
    "GOLD": {
        "name": "Gold",
        "exchange": "CMX",
        "front": "GC=F",
        "prefix": "GC",
        "unit": "USD/oz",
    },
    "SILVER": {
        "name": "Silver",
        "exchange": "CMX",
        "front": "SI=F",
        "prefix": "SI",
        "unit": "USD/oz",
    },
    "COPPER": {
        "name": "Copper",
        "exchange": "CMX",
        "front": "HG=F",
        "prefix": "HG",
        "unit": "USD/lb",
    },
    "PLATINUM": {
        "name": "Platinum",
        "exchange": "NYM",
        "front": "PL=F",
        "prefix": "PL",
        "unit": "USD/oz",
    },
    "PALLADIUM": {
        "name": "Palladium",
        "exchange": "NYM",
        "front": "PA=F",
        "prefix": "PA",
        "unit": "USD/oz",
    },
    "CORN": {
        "name": "Corn",
        "exchange": "CBT",
        "front": "ZC=F",
        "prefix": "ZC",
        "unit": "USC/bu",
    },
    "WHEAT": {
        "name": "Wheat",
        "exchange": "CBT",
        "front": "ZW=F",
        "prefix": "ZW",
        "unit": "USC/bu",
    },
    "SOY": {
        "name": "Soybeans",
        "exchange": "CBT",
        "front": "ZS=F",
        "prefix": "ZS",
        "unit": "USC/bu",
    },
}

# CME month codes
_MONTH_CODES = ["F", "G", "H", "J", "K", "M", "N", "Q", "U", "V", "X", "Z"]


def _contract_symbol(prefix: str, year_full: int, month: int, exchange: str) -> str:
    """Construct yfinance contract symbol like 'CLM26.NYM'."""
    if not 1 <= month <= 12:
        raise ValueError("month must be 1..12")
    code = _MONTH_CODES[month - 1]
    yy = year_full % 100
    return f"{prefix}{code}{yy:02d}.{exchange}"


def _next_n_months(n: int) -> list[tuple[int, int]]:
    """List of (year, month) pairs starting next calendar month."""
    import datetime as _dt
    today = _dt.date.today()
    out = []
    for i in range(1, n + 1):
        m = today.month + i
        y = today.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        out.append((y, m))
    return out


def fetch_curve(symbol: str, n_months: int = 12) -> dict:
    """Fetch front + next N forward outright prices for a commodity."""
    sym = symbol.upper().strip()
    if sym not in DEFAULT_COMMODITIES:
        return {"error": f"unknown commodity {sym}"}

    cache_key = f"commodity_curve:{sym}:{n_months}"
    cached = cache_get(cache_key, 1800)
    if cached is not None:
        return cached

    info = DEFAULT_COMMODITIES[sym]
    prefix = info["prefix"]
    exch = info["exchange"]
    front_symbol = info["front"]

    try:
        import yfinance as yf

        # Front price
        front_hist = yf.Ticker(front_symbol).history(period="5d")
        if front_hist is None or front_hist.empty:
            return {"error": f"front contract data unavailable ({front_symbol})"}
        front_price = float(front_hist["Close"].dropna().iloc[-1])

        # Forward outrights — try each next-month contract; some may be
        # untradeable for grain markets so we tolerate gaps.
        contracts: list[dict] = [
            {
                "tenor_months": 0,
                "contract": "front",
                "symbol": front_symbol,
                "price": round(front_price, 4),
            }
        ]
        for k, (yr, mo) in enumerate(_next_n_months(n_months), start=1):
            ctr = _contract_symbol(prefix, yr, mo, exch)
            try:
                h = yf.Ticker(ctr).history(period="5d")
                if h is None or h.empty:
                    continue
                p = float(h["Close"].dropna().iloc[-1])
                contracts.append(
                    {
                        "tenor_months": k,
                        "contract": f"{yr}-{mo:02d}",
                        "symbol": ctr,
                        "price": round(p, 4),
                    }
                )
            except Exception:
                continue

        slope = slope_diagnostics(contracts)
        result = {
            "symbol": sym,
            "name": info["name"],
            "unit": info["unit"],
            "front_price": round(front_price, 4),
            "n_contracts": len(contracts),
            "curve": contracts,
            **slope,
        }
        cache_set(cache_key, result)
        return result
    except Exception as e:
        logger.error("commodity curve fetch failed for %s: %s", sym, e)
        return {"error": str(e)}


def slope_diagnostics(contracts: list[dict]) -> dict:
    """Classify the term-structure shape and compute roll yield.

    - contango_pct: (back - front) / front * 100 over the longest tenor seen
    - shape: 'contango' (positive slope), 'backwardation' (negative), 'flat'
    - roll_yield_3m_pct: annualised slope of front → 3m contract
    """
    if not contracts or len(contracts) < 2:
        return {"shape": "unknown", "contango_pct": None, "roll_yield_3m_pct": None}

    front = contracts[0]["price"]
    back = contracts[-1]["price"]
    if front <= 0:
        return {"shape": "unknown", "contango_pct": None, "roll_yield_3m_pct": None}

    contango_pct = round((back - front) / front * 100, 4)
    shape = (
        "contango" if contango_pct > 0.5
        else "backwardation" if contango_pct < -0.5
        else "flat"
    )

    # Roll yield: short-front, long-3m equivalent
    by_tenor = {c["tenor_months"]: c["price"] for c in contracts}
    p3 = by_tenor.get(3) or by_tenor.get(2) or by_tenor.get(1)
    roll_yield_3m = None
    if p3 and p3 > 0:
        # Annualised: ((front - p3) / p3) * (12 / 3)
        slope_3m = (front - p3) / p3
        roll_yield_3m = round(slope_3m * (12 / 3) * 100, 4)

    return {
        "shape": shape,
        "contango_pct": contango_pct,
        "roll_yield_3m_pct": roll_yield_3m,
        "interpretation": _shape_interpretation(shape, contango_pct),
    }


def _shape_interpretation(shape: str, contango_pct: Optional[float]) -> str:
    if shape == "contango":
        return (
            "Contango: storage costs / abundance — long-only ETF holders pay "
            "negative roll yield."
        )
    if shape == "backwardation":
        return (
            "Backwardation: tight physical supply — long-only futures holders "
            "earn positive roll yield."
        )
    return "Flat curve — no meaningful storage or scarcity premium priced in."


def commodity_dashboard(
    symbols: Optional[list[str]] = None, n_months: int = 6
) -> dict:
    """Multi-commodity table with front + 6m forward + curve shape."""
    syms = symbols or list(DEFAULT_COMMODITIES.keys())
    rows = []
    for s in syms:
        c = fetch_curve(s, n_months=n_months)
        if "error" in c:
            rows.append({"symbol": s, "error": c["error"]})
            continue
        # Pick 1m / 6m forward outright if present
        by_tenor = {p["tenor_months"]: p["price"] for p in c.get("curve", [])}
        rows.append(
            {
                "symbol": s,
                "name": c["name"],
                "unit": c["unit"],
                "front_price": c["front_price"],
                "fwd_1m": by_tenor.get(1),
                "fwd_3m": by_tenor.get(3),
                "fwd_6m": by_tenor.get(6),
                "shape": c["shape"],
                "contango_pct": c["contango_pct"],
                "roll_yield_3m_pct": c["roll_yield_3m_pct"],
            }
        )
    return {"commodities": rows, "n": len(rows)}
