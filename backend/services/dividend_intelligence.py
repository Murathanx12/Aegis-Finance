"""
Aegis Finance — Dividend Intelligence Service
================================================

Morningstar-style dividend analytics: yield, growth rates, safety score,
aristocrat status, DDM fair value, and forward income projections.

All data sourced from yfinance — no additional API keys required.

Key metrics:
  - Trailing & forward dividend yield
  - Dividend growth rates (1Y, 3Y, 5Y, 10Y CAGR)
  - Payout ratio (earnings-based and FCF-based)
  - Dividend safety score (0-100 composite)
  - Consecutive years of dividend growth
  - Aristocrat / Champion / Contender / Challenger classification
  - Gordon Growth Model (DDM) intrinsic value
  - Forward annual income projection per $10k invested
  - Ex-dividend dates and payment frequency

Usage:
    from backend.services.dividend_intelligence import get_dividend_intelligence
    result = get_dividend_intelligence("JNJ")
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

from backend.cache import cache_get, cache_set
from backend.config import config

logger = logging.getLogger(__name__)

_CACHE_TTL = 3600  # 1 hour — dividends don't change often

# ── Configuration ────────────────────────────────────────────────────────────

_DIV_CONFIG = config.get("dividend_intelligence", {})
_SAFETY_WEIGHTS = _DIV_CONFIG.get("safety_weights", {
    "payout_ratio": 0.30,
    "fcf_coverage": 0.25,
    "earnings_stability": 0.25,
    "debt_equity": 0.20,
})
_DDM_DISCOUNT_RATE = _DIV_CONFIG.get("ddm_discount_rate", 0.10)
_DDM_TERMINAL_GROWTH = _DIV_CONFIG.get("ddm_terminal_growth", 0.03)
_INCOME_INVESTMENT = _DIV_CONFIG.get("income_projection_amount", 10000)

# Consecutive growth year thresholds
_ARISTOCRAT_YEARS = 25   # S&P 500 Dividend Aristocrat
_CHAMPION_YEARS = 25     # Dividend Champion (broader universe)
_CONTENDER_YEARS = 10    # Dividend Contender
_CHALLENGER_YEARS = 5    # Dividend Challenger


def get_dividend_intelligence(ticker: str) -> Optional[dict]:
    """Full dividend analytics for a single stock.

    Args:
        ticker: Stock ticker symbol (e.g., "JNJ", "AAPL").

    Returns:
        dict with yield, growth, safety, classification, DDM value,
        income projection, and dividend history. None if unavailable.
    """
    cache_key = f"dividend_intel:{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL)
    if cached is not None:
        return cached

    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}
        dividends = stock.dividends

        if dividends is None or dividends.empty:
            return {
                "ticker": ticker,
                "pays_dividend": False,
                "message": f"{ticker} does not pay a dividend",
            }

        result = _build_dividend_report(ticker, stock, info, dividends)
        cache_set(cache_key, result)
        return result

    except Exception as e:
        logger.warning("%s: dividend intelligence failed — %s", ticker, e)
        return None


def get_dividend_summary(ticker: str) -> Optional[dict]:
    """Compact dividend summary for embedding in stock analysis.

    Returns a small dict with yield, growth_5y, safety_score,
    classification, and ddm_upside — suitable for the screener.
    """
    full = get_dividend_intelligence(ticker)
    if full is None or not full.get("pays_dividend", False):
        return None

    return {
        "trailing_yield": full.get("trailing_yield"),
        "forward_yield": full.get("forward_yield"),
        "growth_5y": full.get("growth_rates", {}).get("cagr_5y"),
        "safety_score": full.get("safety", {}).get("score"),
        "safety_grade": full.get("safety", {}).get("grade"),
        "consecutive_growth_years": full.get("consecutive_growth_years"),
        "classification": full.get("classification"),
        "ddm_upside_pct": full.get("ddm", {}).get("upside_pct"),
        "annual_income_per_10k": full.get("income_projection", {}).get("annual_income"),
    }


# ── Internal Implementation ──────────────────────────────────────────────────


def _build_dividend_report(
    ticker: str,
    stock: "yf.Ticker",
    info: dict,
    dividends: pd.Series,
) -> dict:
    """Assemble the full dividend intelligence report."""
    current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)

    # Yield
    trailing_yield = _compute_trailing_yield(dividends, current_price)
    forward_yield = info.get("dividendYield")
    if forward_yield is not None:
        forward_yield = round(forward_yield * 100, 2)

    # Growth rates
    growth_rates = _compute_growth_rates(dividends)

    # Payout ratios
    payout = _compute_payout_ratios(info)

    # Consecutive growth years
    annual_divs = _annual_dividends(dividends)
    consecutive_years = _consecutive_growth_years(annual_divs)
    classification = _classify_dividend_status(consecutive_years)

    # Dividend frequency
    frequency = _detect_frequency(dividends)

    # Safety score
    safety = _compute_safety_score(info, payout, growth_rates, consecutive_years)

    # DDM valuation
    ddm = _compute_ddm(dividends, current_price, growth_rates)

    # Income projection
    income = _compute_income_projection(
        trailing_yield, current_price, _INCOME_INVESTMENT
    )

    # Recent dividend history (last 20 payments)
    history = _format_history(dividends, tail=20)

    # Ex-dividend date
    ex_date = info.get("exDividendDate")
    if ex_date is not None:
        try:
            ex_date = pd.Timestamp(ex_date, unit="s").strftime("%Y-%m-%d")
        except Exception:
            ex_date = None

    return {
        "ticker": ticker,
        "pays_dividend": True,
        "current_price": _safe_round(current_price, 2),
        "trailing_yield": trailing_yield,
        "forward_yield": forward_yield,
        "annual_dividend": _safe_round(_trailing_annual_dividend(dividends), 4),
        "frequency": frequency,
        "ex_dividend_date": ex_date,
        "growth_rates": growth_rates,
        "payout": payout,
        "consecutive_growth_years": consecutive_years,
        "classification": classification,
        "safety": safety,
        "ddm": ddm,
        "income_projection": income,
        "history": history,
        "years_of_data": _years_of_data(dividends),
    }


def _compute_trailing_yield(dividends: pd.Series, price: float) -> Optional[float]:
    """Trailing 12-month dividend yield as a percentage."""
    if price <= 0:
        return None
    annual = _trailing_annual_dividend(dividends)
    if annual is None or annual <= 0:
        return None
    return round((annual / price) * 100, 2)


def _trailing_annual_dividend(dividends: pd.Series) -> Optional[float]:
    """Sum of dividends paid in the trailing 12 months."""
    if dividends.empty:
        return None
    cutoff = dividends.index[-1] - pd.DateOffset(years=1)
    recent = dividends[dividends.index >= cutoff]
    if recent.empty:
        return None
    return float(recent.sum())


def _compute_growth_rates(dividends: pd.Series) -> dict:
    """Compute 1Y, 3Y, 5Y, 10Y dividend CAGR."""
    annual = _annual_dividends(dividends)
    if len(annual) < 2:
        return {}

    result = {}
    for label, years in [("cagr_1y", 1), ("cagr_3y", 3), ("cagr_5y", 5), ("cagr_10y", 10)]:
        if len(annual) > years:
            start = annual.iloc[-(years + 1)]
            end = annual.iloc[-1]
            if start > 0 and end > 0:
                cagr = (end / start) ** (1 / years) - 1
                result[label] = round(cagr * 100, 2)

    return result


def _annual_dividends(dividends: pd.Series) -> pd.Series:
    """Aggregate dividends by calendar year."""
    if dividends.empty:
        return pd.Series(dtype=float)
    annual = dividends.groupby(dividends.index.year).sum()
    # Drop current year if it's incomplete (less than 6 months of data)
    now = pd.Timestamp.now()
    if now.month < 7 and len(annual) > 1 and annual.index[-1] == now.year:
        annual = annual.iloc[:-1]
    return annual


def _consecutive_growth_years(annual: pd.Series) -> int:
    """Count consecutive years where dividend increased."""
    if len(annual) < 2:
        return 0
    count = 0
    for i in range(len(annual) - 1, 0, -1):
        if annual.iloc[i] > annual.iloc[i - 1]:
            count += 1
        else:
            break
    return count


def _classify_dividend_status(consecutive_years: int) -> str:
    """Classify based on consecutive dividend growth years."""
    if consecutive_years >= _ARISTOCRAT_YEARS:
        return "Dividend Aristocrat"
    elif consecutive_years >= _CONTENDER_YEARS:
        return "Dividend Contender"
    elif consecutive_years >= _CHALLENGER_YEARS:
        return "Dividend Challenger"
    elif consecutive_years >= 1:
        return "Dividend Grower"
    else:
        return "No Consecutive Growth"


def _detect_frequency(dividends: pd.Series) -> str:
    """Detect payment frequency from spacing between payments."""
    if len(dividends) < 3:
        return "unknown"
    # Compute median gap in days between payments
    gaps = dividends.index.to_series().diff().dropna().dt.days
    if gaps.empty:
        return "unknown"
    median_gap = gaps.median()
    if median_gap < 45:
        return "monthly"
    elif median_gap < 120:
        return "quarterly"
    elif median_gap < 240:
        return "semi-annual"
    else:
        return "annual"


def _compute_payout_ratios(info: dict) -> dict:
    """Earnings-based and FCF-based payout ratios."""
    result = {}

    # Earnings payout ratio
    payout = info.get("payoutRatio")
    if payout is not None:
        result["earnings_payout_pct"] = round(payout * 100, 2)

    # FCF payout: annual dividend per share / FCF per share
    trailing_eps = info.get("trailingEps")
    dividend_rate = info.get("dividendRate")
    if trailing_eps and dividend_rate and trailing_eps > 0:
        result["eps_payout_pct"] = round((dividend_rate / trailing_eps) * 100, 2)

    fcf_ps = info.get("freeCashflow")
    shares = info.get("sharesOutstanding")
    if fcf_ps and shares and shares > 0 and dividend_rate:
        fcf_per_share = fcf_ps / shares
        if fcf_per_share > 0:
            result["fcf_payout_pct"] = round((dividend_rate / fcf_per_share) * 100, 2)

    return result


def _compute_safety_score(
    info: dict,
    payout: dict,
    growth_rates: dict,
    consecutive_years: int,
) -> dict:
    """Composite dividend safety score (0-100).

    Components:
      - Payout ratio score: lower is safer (30% weight)
      - FCF coverage score: higher is safer (25% weight)
      - Earnings stability: consecutive growth as proxy (25% weight)
      - Debt/equity: lower is safer (20% weight)
    """
    scores = {}

    # 1. Payout ratio score (0-100, lower payout = higher score)
    earnings_payout = payout.get("earnings_payout_pct")
    if earnings_payout is not None:
        if earnings_payout <= 0:
            scores["payout_ratio"] = 0  # Negative earnings
        elif earnings_payout <= 30:
            scores["payout_ratio"] = 100
        elif earnings_payout <= 50:
            scores["payout_ratio"] = 85
        elif earnings_payout <= 60:
            scores["payout_ratio"] = 70
        elif earnings_payout <= 75:
            scores["payout_ratio"] = 50
        elif earnings_payout <= 90:
            scores["payout_ratio"] = 30
        elif earnings_payout <= 100:
            scores["payout_ratio"] = 15
        else:
            scores["payout_ratio"] = 0  # Paying more than earnings

    # 2. FCF coverage (0-100, lower FCF payout = higher score)
    fcf_payout = payout.get("fcf_payout_pct")
    if fcf_payout is not None:
        if fcf_payout <= 0:
            scores["fcf_coverage"] = 0
        elif fcf_payout <= 40:
            scores["fcf_coverage"] = 100
        elif fcf_payout <= 60:
            scores["fcf_coverage"] = 80
        elif fcf_payout <= 80:
            scores["fcf_coverage"] = 55
        elif fcf_payout <= 100:
            scores["fcf_coverage"] = 25
        else:
            scores["fcf_coverage"] = 0

    # 3. Earnings stability (consecutive growth years as proxy)
    if consecutive_years >= 25:
        scores["earnings_stability"] = 100
    elif consecutive_years >= 15:
        scores["earnings_stability"] = 85
    elif consecutive_years >= 10:
        scores["earnings_stability"] = 70
    elif consecutive_years >= 5:
        scores["earnings_stability"] = 55
    elif consecutive_years >= 3:
        scores["earnings_stability"] = 40
    elif consecutive_years >= 1:
        scores["earnings_stability"] = 25
    else:
        scores["earnings_stability"] = 10

    # 4. Debt/equity (0-100, lower is safer)
    de_ratio = info.get("debtToEquity")
    if de_ratio is not None:
        de_ratio = de_ratio / 100  # yfinance returns as percentage
        if de_ratio <= 0.3:
            scores["debt_equity"] = 100
        elif de_ratio <= 0.5:
            scores["debt_equity"] = 85
        elif de_ratio <= 1.0:
            scores["debt_equity"] = 65
        elif de_ratio <= 1.5:
            scores["debt_equity"] = 45
        elif de_ratio <= 2.0:
            scores["debt_equity"] = 25
        else:
            scores["debt_equity"] = 10

    # Weighted composite
    if not scores:
        return {"score": None, "grade": "N/A", "components": {}}

    weights = _SAFETY_WEIGHTS
    total_weight = sum(weights.get(k, 0) for k in scores)
    if total_weight <= 0:
        return {"score": None, "grade": "N/A", "components": scores}

    composite = sum(
        scores[k] * weights.get(k, 0) for k in scores
    ) / total_weight

    composite = round(composite, 1)

    # Grade assignment
    if composite >= 80:
        grade = "Very Safe"
    elif composite >= 60:
        grade = "Safe"
    elif composite >= 40:
        grade = "Borderline"
    elif composite >= 20:
        grade = "Unsafe"
    else:
        grade = "Very Unsafe"

    return {
        "score": composite,
        "grade": grade,
        "components": scores,
    }


def _compute_ddm(
    dividends: pd.Series,
    current_price: float,
    growth_rates: dict,
) -> dict:
    """Gordon Growth Model (single-stage DDM) intrinsic value.

    Uses 5Y CAGR as growth rate (capped at terminal growth to discount rate gap).
    Falls back to 3Y or 1Y if 5Y unavailable.
    """
    annual_div = _trailing_annual_dividend(dividends)
    if annual_div is None or annual_div <= 0 or current_price <= 0:
        return {"intrinsic_value": None, "upside_pct": None}

    # Pick best available growth rate
    g = None
    for key in ["cagr_5y", "cagr_3y", "cagr_1y"]:
        if key in growth_rates:
            g = growth_rates[key] / 100  # Convert from pct
            break

    if g is None:
        g = _DDM_TERMINAL_GROWTH  # Assume terminal growth if no history

    # Cap growth below discount rate (Gordon model requires r > g)
    r = _DDM_DISCOUNT_RATE
    max_g = r - 0.01  # At least 1% spread
    g = min(g, max_g)
    g = max(g, 0)  # No negative growth for DDM

    # Next year's expected dividend
    d1 = annual_div * (1 + g)

    intrinsic = d1 / (r - g) if (r - g) > 0.005 else None
    if intrinsic is None:
        return {"intrinsic_value": None, "upside_pct": None}

    intrinsic = round(intrinsic, 2)
    upside = round(((intrinsic / current_price) - 1) * 100, 2)

    return {
        "intrinsic_value": intrinsic,
        "upside_pct": upside,
        "growth_rate_used": round(g * 100, 2),
        "discount_rate": round(r * 100, 2),
        "model": "Gordon Growth (single-stage DDM)",
    }


def _compute_income_projection(
    trailing_yield: Optional[float],
    current_price: float,
    investment: float,
) -> dict:
    """Project annual dividend income from a fixed investment amount."""
    if trailing_yield is None or trailing_yield <= 0 or current_price <= 0:
        return {"annual_income": None, "monthly_income": None}

    shares = investment / current_price
    annual_income = shares * current_price * (trailing_yield / 100)
    monthly_income = annual_income / 12

    return {
        "investment_amount": investment,
        "shares": round(shares, 2),
        "annual_income": round(annual_income, 2),
        "monthly_income": round(monthly_income, 2),
        "yield_on_cost": trailing_yield,
    }


def _format_history(dividends: pd.Series, tail: int = 20) -> list:
    """Format recent dividend payments as a list of dicts."""
    recent = dividends.tail(tail)
    return [
        {
            "date": idx.strftime("%Y-%m-%d"),
            "amount": round(float(val), 4),
        }
        for idx, val in recent.items()
    ]


def _years_of_data(dividends: pd.Series) -> Optional[float]:
    """How many years of dividend history we have."""
    if dividends.empty:
        return None
    span = (dividends.index[-1] - dividends.index[0]).days / 365.25
    return round(span, 1)


def _safe_round(value, decimals: int = 2):
    """Round a value, returning None if it's not numeric."""
    if value is None:
        return None
    try:
        if np.isnan(value) or np.isinf(value):
            return None
        return round(float(value), decimals)
    except (TypeError, ValueError):
        return None
