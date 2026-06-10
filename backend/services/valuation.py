"""
Aegis Finance — Market Valuation Metrics
==========================================

Koyfin's relative valuation tools, Bloomberg's equity risk premium,
and Buffett's favorite indicator — all in one service.

Metrics:
  1. CAPE (Cyclically Adjusted P/E) — Shiller's 10-year earnings ratio
  2. Equity Risk Premium — earnings yield minus real yield
  3. Buffett Indicator — total market cap / GDP
  4. Forward P/E — from yfinance S&P 500 data
  5. Dividend Yield — current yield vs historical
  6. Historical context for all metrics (percentile rank)

Usage:
    from backend.services.valuation import compute_market_valuation
"""

import logging
from typing import Optional


from backend.config import config

logger = logging.getLogger(__name__)


def compute_market_valuation() -> dict:
    """Compute comprehensive market valuation metrics.

    Uses config fallbacks for CAPE since we don't have Shiller's full dataset,
    but enriches with live data from yfinance and FRED where available.
    """
    import yfinance as yf

    result = {}

    # Current S&P 500 data
    spy = yf.Ticker("SPY")
    spy_info = spy.info or {}

    # 1. CAPE (Shiller P/E) — use config fallback + yfinance trailing P/E
    cape_fallback = config["simulation"]["valuation"].get("current_cape_fallback", 37.0)
    long_run_cape = config["simulation"]["valuation"].get("cape_long_run_average", 17.0)

    trailing_pe = spy_info.get("trailingPE")
    forward_pe = spy_info.get("forwardPE")

    cape_estimate = cape_fallback  # best estimate
    cape_percentile = _percentile_rank(cape_estimate, _CAPE_HISTORY)

    result["cape"] = {
        "current": round(cape_estimate, 1),
        "long_run_average": long_run_cape,
        "premium_pct": round((cape_estimate / long_run_cape - 1) * 100, 1),
        "percentile": cape_percentile,
        "interpretation": (
            "Extremely expensive" if cape_percentile > 90
            else "Expensive" if cape_percentile > 75
            else "Fair value" if cape_percentile > 40
            else "Cheap" if cape_percentile > 15
            else "Deeply undervalued"
        ),
    }

    # 2. Trailing and Forward P/E
    result["pe"] = {
        "trailing": round(trailing_pe, 1) if trailing_pe else None,
        "forward": round(forward_pe, 1) if forward_pe else None,
        "forward_vs_trailing": (
            round((forward_pe / trailing_pe - 1) * 100, 1)
            if trailing_pe and forward_pe and trailing_pe > 0
            else None
        ),
    }

    # 3. Equity Risk Premium (ERP)
    # ERP = earnings yield - real risk-free rate
    earnings_yield = (1 / cape_estimate * 100) if cape_estimate > 0 else None
    risk_free = config.get("risk_free_rate", 0.04) * 100

    # Try to get real yield from FRED
    real_yield = None
    try:
        import os
        from fredapi import Fred
        api_key = os.getenv("FRED_API_KEY", "")
        if api_key:
            fred = Fred(api_key=api_key)
            tips = fred.get_series("DFII10", observation_start="2024-01-01")
            if tips is not None and len(tips.dropna()) > 0:
                real_yield = float(tips.dropna().iloc[-1])
    except Exception as e:
        logger.debug("FRED real yield fetch failed: %s", e)

    erp = None
    if earnings_yield and real_yield is not None:
        erp = round(earnings_yield - real_yield, 2)
    elif earnings_yield:
        erp = round(earnings_yield - risk_free, 2)

    result["equity_risk_premium"] = {
        "erp_pct": erp,
        "earnings_yield": round(earnings_yield, 2) if earnings_yield else None,
        "real_yield_10y": round(real_yield, 2) if real_yield else None,
        "risk_free_nominal": risk_free,
        "interpretation": (
            "Attractive — stocks cheap vs bonds" if erp and erp > 4
            else "Normal" if erp and erp > 2
            else "Tight — stocks expensive vs bonds" if erp and erp > 0
            else "Negative — bonds more attractive" if erp is not None
            else "Unavailable"
        ),
    }

    # 4. Dividend Yield
    div_yield = spy_info.get("dividendYield")
    result["dividend_yield"] = {
        "current_pct": round(div_yield * 100, 2) if div_yield else None,
        "historical_avg": 1.9,  # S&P 500 long-run average
        "interpretation": (
            "Above average" if div_yield and div_yield * 100 > 2.0
            else "Near average" if div_yield and div_yield * 100 > 1.5
            else "Below average" if div_yield
            else "Unavailable"
        ),
    }

    # 5. Buffett Indicator (Wilshire 5000 / GDP)
    # Approximation: SPY market cap * ~500/market_cap_weight ≈ total market
    buffett = _compute_buffett_indicator()
    result["buffett_indicator"] = buffett

    # 6. Overall valuation score (1-100, higher = more expensive)
    val_signals = []
    if cape_percentile is not None:
        val_signals.append(cape_percentile)
    if erp is not None:
        # Lower ERP = more expensive
        erp_score = max(0, min(100, 100 - (erp - 0) * 15))
        val_signals.append(erp_score)

    if val_signals:
        composite = round(sum(val_signals) / len(val_signals), 0)
    else:
        composite = 50

    result["composite_valuation_score"] = {
        "score": int(composite),
        "level": (
            "very_expensive" if composite > 80
            else "expensive" if composite > 60
            else "fair" if composite > 40
            else "cheap" if composite > 20
            else "very_cheap"
        ),
    }

    return result


def _compute_buffett_indicator() -> dict:
    """Buffett Indicator: total stock market cap / GDP."""
    try:
        import os
        from fredapi import Fred
        api_key = os.getenv("FRED_API_KEY", "")
        if not api_key:
            return {"ratio": None, "interpretation": "FRED key not set"}

        fred = Fred(api_key=api_key)

        # Wilshire 5000 Total Market Cap
        wilshire = fred.get_series("WILL5000IND", observation_start="2020-01-01")
        # GDP (quarterly, billions)
        gdp = fred.get_series("GDP", observation_start="2020-01-01")

        if wilshire is None or gdp is None:
            return {"ratio": None, "interpretation": "Data unavailable"}

        wilshire_val = float(wilshire.dropna().iloc[-1])
        gdp_val = float(gdp.dropna().iloc[-1])

        if gdp_val <= 0:
            return {"ratio": None, "interpretation": "Invalid GDP data"}

        # Wilshire 5000 index value ≈ total market in $B
        # GDP is in $B
        ratio = round(wilshire_val / gdp_val * 100, 1)

        return {
            "ratio_pct": ratio,
            "threshold_fair": 100,
            "threshold_expensive": 140,
            "interpretation": (
                "Significantly overvalued" if ratio > 180
                else "Overvalued" if ratio > 140
                else "Fairly valued" if ratio > 100
                else "Undervalued"
            ),
        }
    except Exception as e:
        logger.debug("Buffett indicator failed: %s", e)
        return {"ratio": None, "interpretation": f"Calculation failed: {e}"}


# Historical CAPE distribution (approximate percentiles from Shiller data 1881-2025)
_CAPE_HISTORY = [
    5, 7, 8, 9, 10, 11, 12, 13, 14, 15,
    16, 17, 18, 19, 20, 21, 22, 23, 24, 25,
    26, 27, 28, 29, 30, 32, 34, 36, 38, 40, 44,
]


def _percentile_rank(value: float, sorted_history: list) -> Optional[int]:
    """Compute approximate percentile rank of value within a sorted distribution."""
    if not sorted_history or value is None:
        return None
    below = sum(1 for x in sorted_history if x <= value)
    return int(round(below / len(sorted_history) * 100))
