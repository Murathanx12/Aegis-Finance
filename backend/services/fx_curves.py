"""
Aegis Finance — FX Spot & Forwards
=====================================

Live G10 FX spot rates plus a forward curve derived via covered interest
parity (CIP) from FRED short-rate differentials. Mirrors what the Koyfin
FREE tier already shows — Aegis previously had no first-class FX surface.

Public surface
--------------
- ``DEFAULT_PAIRS`` / ``DEFAULT_USD_RATES`` — convenience constants
- ``fetch_spot(pair)``                   — current spot from yfinance =X tickers
- ``forward_curve(pair, tenors_months)`` — CIP-implied forward points
- ``fx_dashboard()``                      — multi-pair table for UI

Covered interest parity
-----------------------
For a USD-quoted pair (e.g. EURUSD) the n-day forward rate is::

    F = S * (1 + r_quote * n/360) / (1 + r_base * n/360)

where ``r_quote`` is the quote-currency short rate (e.g. ECB ESTR for EUR)
and ``r_base`` is the base-currency rate (e.g. USD SOFR). We use the FRED
short-rate proxies that are publicly available and update daily.
"""

from __future__ import annotations

import logging
from typing import Optional


from backend.cache import cache_get, cache_set

logger = logging.getLogger(__name__)


# Major G10 pairs. yfinance ticker convention: 'EURUSD=X' for EUR/USD.
DEFAULT_PAIRS: list[str] = [
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "USDCHF",
    "AUDUSD",
    "USDCAD",
    "NZDUSD",
    "USDSEK",
    "USDNOK",
    "USDMXN",
]

# FRED short-rate proxies per currency. These are the closest publicly
# available equivalents of the actual interbank fixings used by FX desks.
SHORT_RATE_SERIES: dict[str, str] = {
    "USD": "DFF",          # Effective Fed Funds
    "EUR": "ECBESTRVOLWGTTRMDMNRT",  # ESTR (€STR)
    "GBP": "IUDSOIA",      # SONIA
    "JPY": "INTGSBJPM193N",  # 3-month interbank JPY proxy
    "CHF": "IRSTCI01CHM156N",  # CH 3-month rate
    "CAD": "IR3TIB01CAM156N",  # CA 3-month rate
    "AUD": "IR3TIB01AUM156N",
    "NZD": "IR3TIB01NZM156N",
    "SEK": "IR3TIB01SEM156N",
    "NOK": "IR3TIB01NOM156N",
    "MXN": "IRSTCI01MXM156N",
}

DEFAULT_USD_RATE = 0.04  # fallback when FRED unkeyed
TENORS_MONTHS_DEFAULT = (1, 3, 6, 12)


def _yf_pair_ticker(pair: str) -> str:
    """Convert 'EURUSD' to the yfinance symbol 'EURUSD=X'."""
    return f"{pair.upper()}=X"


def _split_pair(pair: str) -> tuple[str, str]:
    pair = pair.upper().strip()
    if len(pair) != 6:
        raise ValueError(f"FX pair must be 6 letters (got {pair!r})")
    return pair[:3], pair[3:]


def fetch_spot(pair: str) -> Optional[float]:
    """Current FX spot from yfinance with a 5-min cache."""
    pair = pair.upper().strip()
    cache_key = f"fx_spot:{pair}"
    cached = cache_get(cache_key, 300)
    if cached is not None:
        return float(cached)

    try:
        import yfinance as yf
        hist = yf.Ticker(_yf_pair_ticker(pair)).history(period="5d")
        if hist is None or hist.empty:
            return None
        spot = float(hist["Close"].dropna().iloc[-1])
        cache_set(cache_key, spot)
        return spot
    except Exception as e:
        logger.debug("fx spot fetch failed for %s: %s", pair, e)
        return None


def fetch_short_rate(currency: str) -> Optional[float]:
    """Short rate (decimal, e.g. 0.045) for a currency from FRED.

    Falls back to ``DEFAULT_USD_RATE`` for USD and ``None`` for other
    currencies if FRED is unkeyed.
    """
    currency = currency.upper().strip()
    series_id = SHORT_RATE_SERIES.get(currency)
    if not series_id:
        return None

    cache_key = f"fx_rate:{currency}"
    cached = cache_get(cache_key, 24 * 3600)
    if cached is not None:
        return float(cached)

    try:
        from backend.services.providers import registry
        s = registry.get_macro_series(series_id)
        if s is None or len(s) == 0:
            return DEFAULT_USD_RATE if currency == "USD" else None
        s = s.dropna() if hasattr(s, "dropna") else s
        if len(s) == 0:
            return DEFAULT_USD_RATE if currency == "USD" else None
        # FRED rates are in percent; convert to decimal
        rate = float(s.iloc[-1]) / 100.0
        cache_set(cache_key, rate)
        return rate
    except Exception as e:
        logger.debug("short rate fetch failed for %s: %s", currency, e)
        return DEFAULT_USD_RATE if currency == "USD" else None


def cip_forward(spot: float, base_rate: float, quote_rate: float, days: int) -> float:
    """Covered interest parity forward (act/360 day-count).

    Convention: ``spot`` is base / quote (e.g. 1.0850 EUR/USD means
    1 EUR = 1.0850 USD). Returns the no-arbitrage forward outright.
    """
    if days <= 0:
        return spot
    yf_base = 1.0 + base_rate * days / 360.0
    yf_quote = 1.0 + quote_rate * days / 360.0
    if yf_base <= 0:
        return float("nan")
    return spot * yf_quote / yf_base


def forward_curve(
    pair: str, tenors_months: tuple[int, ...] = TENORS_MONTHS_DEFAULT
) -> dict:
    """Build the CIP forward curve for one pair across standard tenors."""
    pair = pair.upper().strip()
    base, quote = _split_pair(pair)

    spot = fetch_spot(pair)
    if spot is None:
        return {"pair": pair, "error": "spot unavailable"}

    r_base = fetch_short_rate(base)
    r_quote = fetch_short_rate(quote)

    points: list[dict] = []
    for m in tenors_months:
        days = int(round(m * 30.4375))
        if r_base is not None and r_quote is not None:
            fwd = cip_forward(spot, r_base, r_quote, days)
        else:
            # Fall back to spot when rates missing — explicit 0 forward points
            fwd = spot
        # Forward points expressed in pips of the quote currency
        pip_size = 0.0001 if quote != "JPY" else 0.01
        fwd_points = round((fwd - spot) / pip_size, 2)
        points.append(
            {
                "tenor_months": m,
                "tenor_days": days,
                "forward": round(fwd, 6),
                "forward_points": fwd_points,
                "annualised_carry_bp": (
                    round(((fwd - spot) / spot) * (360.0 / max(days, 1)) * 10000, 2)
                ),
            }
        )

    return {
        "pair": pair,
        "spot": round(spot, 6),
        "rates": {
            "base": base,
            "quote": quote,
            "base_rate_pct": round(r_base * 100, 4) if r_base is not None else None,
            "quote_rate_pct": round(r_quote * 100, 4) if r_quote is not None else None,
        },
        "forwards": points,
        "method": "Covered interest parity (act/360) using FRED short rates",
    }


def fx_dashboard(pairs: list[str] = DEFAULT_PAIRS) -> dict:
    """Multi-pair table with spot + 1m/3m/12m forward + carry."""
    rows = []
    for p in pairs:
        try:
            curve = forward_curve(p, tenors_months=(1, 3, 12))
        except Exception as e:
            logger.warning("fx_dashboard: failed pair %s: %s", p, e)
            continue
        if "error" in curve:
            rows.append({"pair": p, "error": curve["error"]})
            continue
        m1 = next((f for f in curve["forwards"] if f["tenor_months"] == 1), {})
        m3 = next((f for f in curve["forwards"] if f["tenor_months"] == 3), {})
        m12 = next((f for f in curve["forwards"] if f["tenor_months"] == 12), {})
        rows.append(
            {
                "pair": p,
                "spot": curve["spot"],
                "fwd_1m": m1.get("forward"),
                "fwd_3m": m3.get("forward"),
                "fwd_12m": m12.get("forward"),
                "carry_3m_bp": m3.get("annualised_carry_bp"),
                "base_rate_pct": curve["rates"].get("base_rate_pct"),
                "quote_rate_pct": curve["rates"].get("quote_rate_pct"),
            }
        )
    return {"pairs": rows, "n": len(rows)}
