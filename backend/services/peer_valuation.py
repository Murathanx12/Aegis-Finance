"""
Aegis Finance — Peer Relative Valuation Service
==================================================

Compares a stock's valuation multiples against its sector peers, computing
percentile ranks, premium/discount to peer median, and a composite
valuation score (cheap/fair/expensive).

Metrics compared:
- P/E (trailing), Forward P/E, PEG ratio
- P/B (price-to-book), P/S (price-to-sales)
- EV/EBITDA, EV/Revenue
- Dividend yield, ROE, debt/equity
- Free cash flow yield, operating margin

This is Koyfin's core feature — relative valuation vs peers.

Usage:
    from backend.services.peer_valuation import get_peer_valuation
"""

import logging
from typing import Optional

import numpy as np
import yfinance as yf

from backend.cache import cache_get, cache_set
from backend.config import config
from backend.services.stock_analyzer import SECTOR_STOCK_MAP

logger = logging.getLogger(__name__)

_CACHE_TTL = 3600  # 1 hour — fundamentals don't change intraday

# Valuation multiples we compare across peers
VALUATION_METRICS = [
    "trailingPE",
    "forwardPE",
    "pegRatio",
    "priceToBook",
    "priceToSalesTrailing12Months",
    "enterpriseToEbitda",
    "enterpriseToRevenue",
    "dividendYield",
    "returnOnEquity",
    "debtToEquity",
    "freeCashflow",
    "operatingMargins",
    "profitMargins",
    "revenueGrowth",
    "earningsGrowth",
]

# Human-readable names
METRIC_NAMES = {
    "trailingPE": "P/E (Trailing)",
    "forwardPE": "P/E (Forward)",
    "pegRatio": "PEG Ratio",
    "priceToBook": "Price / Book",
    "priceToSalesTrailing12Months": "Price / Sales",
    "enterpriseToEbitda": "EV / EBITDA",
    "enterpriseToRevenue": "EV / Revenue",
    "dividendYield": "Dividend Yield",
    "returnOnEquity": "Return on Equity",
    "debtToEquity": "Debt / Equity",
    "freeCashflow": "Free Cash Flow",
    "operatingMargins": "Operating Margin",
    "profitMargins": "Profit Margin",
    "revenueGrowth": "Revenue Growth",
    "earningsGrowth": "Earnings Growth",
}

# Which metrics are "lower is better" (for valuation score)
LOWER_IS_BETTER = {
    "trailingPE", "forwardPE", "pegRatio", "priceToBook",
    "priceToSalesTrailing12Months", "enterpriseToEbitda",
    "enterpriseToRevenue", "debtToEquity",
}

# Which metrics are "higher is better"
HIGHER_IS_BETTER = {
    "dividendYield", "returnOnEquity", "freeCashflow",
    "operatingMargins", "profitMargins", "revenueGrowth",
    "earningsGrowth",
}

# Weights for composite valuation score (most important multiples weighted higher)
COMPOSITE_WEIGHTS = config.get("peer_valuation", {}).get("composite_weights", {
    "forwardPE": 0.20,
    "enterpriseToEbitda": 0.18,
    "priceToBook": 0.10,
    "priceToSalesTrailing12Months": 0.10,
    "pegRatio": 0.12,
    "returnOnEquity": 0.10,
    "operatingMargins": 0.08,
    "revenueGrowth": 0.07,
    "freeCashflow": 0.05,
})


def _fetch_peer_fundamentals(ticker: str) -> Optional[dict]:
    """Fetch key valuation multiples for a single ticker from yfinance."""
    cache_key = f"peer_fundamentals_{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL)
    if cached is not None:
        return cached

    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}
        if not info.get("shortName"):
            return None

        result = {
            "ticker": ticker,
            "name": info.get("shortName", ticker),
            "sector": info.get("sector", "Unknown"),
            "market_cap": info.get("marketCap"),
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
        }

        for metric in VALUATION_METRICS:
            val = info.get(metric)
            if val is not None and isinstance(val, (int, float)) and not np.isnan(val):
                result[metric] = float(val)
            else:
                result[metric] = None

        # Compute FCF yield if we have market cap and FCF
        if result.get("freeCashflow") and result.get("market_cap") and result["market_cap"] > 0:
            result["fcf_yield"] = result["freeCashflow"] / result["market_cap"]
        else:
            result["fcf_yield"] = None

        cache_set(cache_key, result)
        return result

    except Exception as e:
        logger.debug("Peer fundamentals fetch failed for %s: %s", ticker, e)
        return None


def _get_sector_for_ticker(ticker: str) -> Optional[str]:
    """Find which sector a ticker belongs to in our universe."""
    for sector, tickers in SECTOR_STOCK_MAP.items():
        if ticker in tickers:
            return sector
    return None


def _get_expanded_peers(ticker: str, sector: str) -> list[str]:
    """Get peer tickers for comparison, excluding the target ticker."""
    peer_cfg = config.get("peer_valuation", {})
    max_peers = peer_cfg.get("max_peers", 15)

    # Start with our sector map peers
    peers = list(SECTOR_STOCK_MAP.get(sector, []))

    # Remove the target ticker
    peers = [p for p in peers if p != ticker]

    return peers[:max_peers]


def get_peer_valuation(ticker: str) -> Optional[dict]:
    """Compare a stock's valuation multiples against sector peers.

    Returns:
        dict with:
        - target: the target stock's metrics
        - peers: list of peer metrics
        - comparison: per-metric percentile rank, peer median, premium/discount
        - composite_score: 0-100 (0 = cheapest, 100 = most expensive)
        - verdict: "cheap" / "fair" / "expensive"
        - peer_count: number of peers with data
    """
    ticker = ticker.upper()
    cache_key = f"peer_valuation_{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL)
    if cached is not None:
        return cached

    # Fetch target stock fundamentals
    target = _fetch_peer_fundamentals(ticker)
    if target is None:
        return None

    # Determine sector
    sector = target.get("sector", "Unknown")
    mapped_sector = _get_sector_for_ticker(ticker)
    if mapped_sector:
        sector = mapped_sector

    # Get peers
    peer_tickers = _get_expanded_peers(ticker, sector)
    if not peer_tickers:
        return {"error": "No peers found for sector", "sector": sector}

    # Fetch peer fundamentals
    peer_data = []
    for pt in peer_tickers:
        pf = _fetch_peer_fundamentals(pt)
        if pf is not None:
            peer_data.append(pf)

    if len(peer_data) < 2:
        return {"error": "Insufficient peer data", "peer_count": len(peer_data)}

    # Compare each metric
    comparison = {}
    valuation_scores = []

    for metric in VALUATION_METRICS:
        target_val = target.get(metric)
        peer_vals = [p.get(metric) for p in peer_data if p.get(metric) is not None]

        if target_val is None or len(peer_vals) < 2:
            comparison[metric] = {
                "name": METRIC_NAMES.get(metric, metric),
                "target_value": target_val,
                "peer_median": None,
                "peer_mean": None,
                "peer_min": None,
                "peer_max": None,
                "percentile": None,
                "premium_discount_pct": None,
                "available": False,
            }
            continue

        peer_arr = np.array(peer_vals)
        peer_median = float(np.median(peer_arr))
        peer_mean = float(np.mean(peer_arr))
        peer_min = float(np.min(peer_arr))
        peer_max = float(np.max(peer_arr))

        # Percentile rank: what % of peers have a lower value
        all_vals = np.append(peer_arr, target_val)
        rank = float(np.sum(all_vals < target_val) / len(all_vals) * 100)

        # Premium/discount vs peer median
        if peer_median != 0:
            premium_pct = float((target_val - peer_median) / abs(peer_median) * 100)
        else:
            premium_pct = 0.0

        comparison[metric] = {
            "name": METRIC_NAMES.get(metric, metric),
            "target_value": round(target_val, 4),
            "peer_median": round(peer_median, 4),
            "peer_mean": round(peer_mean, 4),
            "peer_min": round(peer_min, 4),
            "peer_max": round(peer_max, 4),
            "percentile": round(rank, 1),
            "premium_discount_pct": round(premium_pct, 1),
            "n_peers": len(peer_vals),
            "available": True,
        }

        # Contribute to composite valuation score
        weight = COMPOSITE_WEIGHTS.get(metric)
        if weight is not None and weight > 0:
            if metric in LOWER_IS_BETTER:
                # High percentile = expensive = high score
                valuation_scores.append((weight, rank))
            elif metric in HIGHER_IS_BETTER:
                # High percentile = good fundamentals = low valuation score
                valuation_scores.append((weight, 100 - rank))

    # FCF yield comparison (derived metric)
    target_fcf_yield = target.get("fcf_yield")
    peer_fcf_yields = [p.get("fcf_yield") for p in peer_data if p.get("fcf_yield") is not None]
    if target_fcf_yield is not None and len(peer_fcf_yields) >= 2:
        peer_arr = np.array(peer_fcf_yields)
        all_vals = np.append(peer_arr, target_fcf_yield)
        rank = float(np.sum(all_vals < target_fcf_yield) / len(all_vals) * 100)
        comparison["fcf_yield"] = {
            "name": "FCF Yield",
            "target_value": round(target_fcf_yield * 100, 2),
            "peer_median": round(float(np.median(peer_arr)) * 100, 2),
            "peer_mean": round(float(np.mean(peer_arr)) * 100, 2),
            "peer_min": round(float(np.min(peer_arr)) * 100, 2),
            "peer_max": round(float(np.max(peer_arr)) * 100, 2),
            "percentile": round(rank, 1),
            "premium_discount_pct": round(
                (target_fcf_yield - float(np.median(peer_arr))) / abs(float(np.median(peer_arr))) * 100
                if float(np.median(peer_arr)) != 0 else 0, 1
            ),
            "n_peers": len(peer_fcf_yields),
            "available": True,
        }
        # FCF yield: higher is better (cheaper)
        valuation_scores.append((0.05, 100 - rank))

    # Compute weighted composite valuation score
    if valuation_scores:
        total_weight = sum(w for w, _ in valuation_scores)
        composite = sum(w * s for w, s in valuation_scores) / total_weight if total_weight > 0 else 50.0
        composite = float(np.clip(composite, 0, 100))
    else:
        composite = 50.0  # neutral if no data

    # Verdict
    peer_cfg = config.get("peer_valuation", {})
    cheap_threshold = peer_cfg.get("cheap_threshold", 35)
    expensive_threshold = peer_cfg.get("expensive_threshold", 65)

    if composite < cheap_threshold:
        verdict = "cheap"
    elif composite > expensive_threshold:
        verdict = "expensive"
    else:
        verdict = "fair"

    # Build peer summary table
    peer_summary = []
    for p in peer_data:
        peer_summary.append({
            "ticker": p["ticker"],
            "name": p.get("name", p["ticker"]),
            "market_cap": p.get("market_cap"),
            "pe_trailing": p.get("trailingPE"),
            "pe_forward": p.get("forwardPE"),
            "pb": p.get("priceToBook"),
            "ps": p.get("priceToSalesTrailing12Months"),
            "ev_ebitda": p.get("enterpriseToEbitda"),
            "dividend_yield": round(p["dividendYield"] * 100, 2) if p.get("dividendYield") else None,
            "roe": round(p["returnOnEquity"] * 100, 2) if p.get("returnOnEquity") else None,
            "operating_margin": round(p["operatingMargins"] * 100, 2) if p.get("operatingMargins") else None,
        })

    result = {
        "ticker": ticker,
        "name": target.get("name", ticker),
        "sector": sector,
        "target": {
            "pe_trailing": target.get("trailingPE"),
            "pe_forward": target.get("forwardPE"),
            "peg": target.get("pegRatio"),
            "pb": target.get("priceToBook"),
            "ps": target.get("priceToSalesTrailing12Months"),
            "ev_ebitda": target.get("enterpriseToEbitda"),
            "ev_revenue": target.get("enterpriseToRevenue"),
            "dividend_yield": round(target["dividendYield"] * 100, 2) if target.get("dividendYield") else None,
            "roe": round(target["returnOnEquity"] * 100, 2) if target.get("returnOnEquity") else None,
            "debt_equity": target.get("debtToEquity"),
            "operating_margin": round(target["operatingMargins"] * 100, 2) if target.get("operatingMargins") else None,
            "profit_margin": round(target["profitMargins"] * 100, 2) if target.get("profitMargins") else None,
            "revenue_growth": round(target["revenueGrowth"] * 100, 2) if target.get("revenueGrowth") else None,
            "earnings_growth": round(target["earningsGrowth"] * 100, 2) if target.get("earningsGrowth") else None,
            "fcf_yield": round(target["fcf_yield"] * 100, 2) if target.get("fcf_yield") else None,
            "market_cap": target.get("market_cap"),
        },
        "comparison": comparison,
        "peers": peer_summary,
        "composite_score": round(composite, 1),
        "verdict": verdict,
        "peer_count": len(peer_data),
        "sector_peer_tickers": [p["ticker"] for p in peer_data],
    }

    cache_set(cache_key, result)
    return result


def get_peer_valuation_summary(ticker: str) -> Optional[dict]:
    """Lightweight summary for embedding in stock analysis responses.

    Returns composite score, verdict, and key relative metrics.
    """
    full = get_peer_valuation(ticker)
    if full is None or "error" in full:
        return None

    # Extract the most important comparisons
    key_metrics = {}
    for metric_key in ["forwardPE", "enterpriseToEbitda", "priceToBook", "returnOnEquity"]:
        comp = full["comparison"].get(metric_key, {})
        if comp.get("available"):
            key_metrics[metric_key] = {
                "value": comp["target_value"],
                "peer_median": comp["peer_median"],
                "percentile": comp["percentile"],
                "premium_pct": comp["premium_discount_pct"],
            }

    return {
        "composite_score": full["composite_score"],
        "verdict": full["verdict"],
        "peer_count": full["peer_count"],
        "sector": full["sector"],
        "key_metrics": key_metrics,
    }
