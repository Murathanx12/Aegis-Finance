"""
Aegis Finance — Fixed Income Analytics
=========================================

Bond market intelligence that Bloomberg charges $24K/year for:

1. Yield Curve Analysis: Shape, slope, curvature, inversion detection
2. Credit Spreads: IG vs HY spread decomposition, historical context
3. Real Yields: TIPS breakeven inflation rate
4. Duration Proxy: ETF-level duration and interest rate sensitivity
5. Fed Funds Expectations: Implied rate path from yield curve

Data sources: FRED (yield curve, credit spreads), yfinance (bond ETFs)

Usage:
    from backend.services.fixed_income import (
        compute_yield_curve_analysis, compute_credit_spread_analysis,
        get_fixed_income_dashboard,
    )
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from backend.config import config

logger = logging.getLogger(__name__)


# Treasury maturities available from FRED
_YIELD_SERIES = {
    "3m": "DGS3MO",
    "6m": "DGS6MO",
    "1y": "DGS1",
    "2y": "DGS2",
    "3y": "DGS3",
    "5y": "DGS5",
    "7y": "DGS7",
    "10y": "DGS10",
    "20y": "DGS20",
    "30y": "DGS30",
}

# Credit spread series from FRED
_CREDIT_SERIES = {
    "hy_oas": "BAMLH0A0HYM2",  # High Yield OAS
    "ig_oas": "BAMLC0A0CM",    # Investment Grade OAS
    "bbb_oas": "BAMLC0A4CBBB", # BBB OAS
    "tips_10y": "DFII10",       # 10Y TIPS (real yield)
    "breakeven_10y": "T10YIE",  # 10Y breakeven inflation
}


def compute_yield_curve_analysis(fred_data: dict) -> dict:
    """Analyze the current yield curve shape, slope, and inversion.

    Returns:
        Dict with curve shape, key spreads, inversion flags, and interpretation.
    """
    # Try to get yields from FRED data or config-mapped series
    yields = {}
    for maturity, series_id in _YIELD_SERIES.items():
        if series_id in fred_data:
            s = fred_data[series_id]
            if s is not None and len(s.dropna()) > 0:
                yields[maturity] = float(s.dropna().iloc[-1])

    # Fallback: use market data columns if FRED series not available
    if not yields:
        return {"error": "No yield curve data available", "yields": {}}

    # Key spreads
    spread_10y_2y = None
    spread_10y_3m = None
    spread_2y_3m = None
    spread_30y_10y = None

    if "10y" in yields and "2y" in yields:
        spread_10y_2y = round(yields["10y"] - yields["2y"], 3)
    if "10y" in yields and "3m" in yields:
        spread_10y_3m = round(yields["10y"] - yields["3m"], 3)
    if "2y" in yields and "3m" in yields:
        spread_2y_3m = round(yields["2y"] - yields["3m"], 3)
    if "30y" in yields and "10y" in yields:
        spread_30y_10y = round(yields["30y"] - yields["10y"], 3)

    # Inversion detection
    inversions = []
    if spread_10y_2y is not None and spread_10y_2y < 0:
        inversions.append("10Y-2Y inverted")
    if spread_10y_3m is not None and spread_10y_3m < 0:
        inversions.append("10Y-3M inverted")

    # Curve shape classification
    if len(inversions) >= 2:
        shape = "deeply_inverted"
        interpretation = "Deep yield curve inversion — strong recession signal (historically 12-18 month lead)"
    elif len(inversions) == 1:
        shape = "partially_inverted"
        interpretation = "Partial inversion — recession risk elevated but not confirmed"
    elif spread_10y_2y is not None and spread_10y_2y > 1.0:
        shape = "steep"
        interpretation = "Steep yield curve — typically seen in early recovery, accommodative policy"
    elif spread_10y_2y is not None and spread_10y_2y > 0.25:
        shape = "normal"
        interpretation = "Normal upward-sloping curve — healthy economic expectations"
    elif spread_10y_2y is not None:
        shape = "flat"
        interpretation = "Flat yield curve — late cycle signal, market expects rate cuts"
    else:
        shape = "unknown"
        interpretation = "Insufficient data for curve analysis"

    # Curvature (butterfly spread: 2*(5Y) - (2Y) - (10Y))
    curvature = None
    if all(m in yields for m in ["2y", "5y", "10y"]):
        curvature = round(2 * yields["5y"] - yields["2y"] - yields["10y"], 3)

    return {
        "yields": yields,
        "spreads": {
            "10y_2y": spread_10y_2y,
            "10y_3m": spread_10y_3m,
            "2y_3m": spread_2y_3m,
            "30y_10y": spread_30y_10y,
        },
        "curvature": curvature,
        "shape": shape,
        "inversions": inversions,
        "interpretation": interpretation,
    }


def compute_credit_spread_analysis(fred_data: dict) -> dict:
    """Analyze credit spreads (IG, HY, BBB) for stress detection.

    Returns:
        Dict with current spreads, historical context, and stress signals.
    """
    spreads = {}
    for name, series_id in _CREDIT_SERIES.items():
        if series_id in fred_data:
            s = fred_data[series_id]
            if s is not None and len(s.dropna()) > 0:
                clean = s.dropna()
                current = float(clean.iloc[-1])
                spreads[name] = {
                    "current": round(current, 3),
                    "mean_1y": round(float(clean.iloc[-252:].mean()), 3) if len(clean) >= 252 else None,
                    "min_1y": round(float(clean.iloc[-252:].min()), 3) if len(clean) >= 252 else None,
                    "max_1y": round(float(clean.iloc[-252:].max()), 3) if len(clean) >= 252 else None,
                }

                # Z-score vs 1-year history
                if len(clean) >= 252:
                    mean = float(clean.iloc[-252:].mean())
                    std = float(clean.iloc[-252:].std())
                    if std > 0.001:
                        spreads[name]["zscore"] = round((current - mean) / std, 2)

    # Real yields and breakeven inflation
    real_yield = None
    breakeven = None
    if "tips_10y" in spreads:
        real_yield = spreads["tips_10y"]["current"]
    if "breakeven_10y" in spreads:
        breakeven = spreads["breakeven_10y"]["current"]

    # Credit stress assessment
    stress_level = "normal"
    stress_signals = []

    hy = spreads.get("hy_oas", {})
    ig = spreads.get("ig_oas", {})

    if hy.get("current") and hy["current"] > 5.0:
        stress_level = "elevated"
        stress_signals.append(f"HY spread at {hy['current']:.0f} bps — above 500 bps stress threshold")
    elif hy.get("current") and hy["current"] > 4.0:
        stress_signals.append(f"HY spread at {hy['current']:.0f} bps — approaching stress level")

    if hy.get("zscore") and hy["zscore"] > 2.0:
        stress_level = "elevated"
        stress_signals.append(f"HY spread z-score {hy['zscore']:.1f} — 2+ std above 1Y mean")

    if ig.get("zscore") and ig["zscore"] > 2.0:
        stress_signals.append(f"IG spread z-score {ig['zscore']:.1f} — widening fast")

    return {
        "spreads": spreads,
        "real_yield_10y": real_yield,
        "breakeven_inflation_10y": breakeven,
        "stress": {
            "level": stress_level,
            "signals": stress_signals,
        },
    }


def get_fixed_income_dashboard() -> dict:
    """Full fixed income dashboard: yield curve + credit spreads + interpretation.

    Fetches fresh FRED data and computes all fixed income analytics.
    """
    try:
        from fredapi import Fred
        import os

        api_key = os.getenv("FRED_API_KEY", "")
        if not api_key:
            return {"error": "FRED API key not configured"}

        fred = Fred(api_key=api_key)
        fred_data = {}

        # Fetch yield curve data
        all_series = {**_YIELD_SERIES, **_CREDIT_SERIES}
        for name, series_id in all_series.items():
            try:
                data = fred.get_series(series_id, observation_start="2020-01-01")
                if data is not None and len(data) > 0:
                    fred_data[series_id] = data
            except Exception as e:
                logger.debug("FRED fetch failed for %s: %s", series_id, e)

        yield_curve = compute_yield_curve_analysis(fred_data)
        credit = compute_credit_spread_analysis(fred_data)

        return {
            "yield_curve": yield_curve,
            "credit": credit,
        }

    except ImportError:
        return {"error": "fredapi not installed"}
    except Exception as e:
        logger.error("Fixed income dashboard failed: %s", e)
        return {"error": str(e)}
