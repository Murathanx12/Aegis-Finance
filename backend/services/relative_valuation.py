"""
Aegis Finance — Relative Valuation & Peer Comparison
======================================================

Koyfin-style relative valuation that ranks a stock against its sector peers
on multiple valuation metrics with percentile rankings, historical context,
and a composite valuation score.

Metrics compared:
  - P/E (trailing), Forward P/E, PEG ratio
  - EV/EBITDA, P/S (price-to-sales), P/B (price-to-book)
  - Dividend yield, FCF yield
  - Revenue growth, earnings growth

Usage:
    from backend.services.relative_valuation import get_relative_valuation
    result = get_relative_valuation("AAPL")
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import numpy as np
import yfinance as yf

from backend.config import config

logger = logging.getLogger(__name__)

# Sector → peer tickers from config
_universe = config.get("stock_universe", {})
SECTOR_STOCK_MAP: dict = _universe.get("sector_stocks", {})

# Valuation config
_val_cfg = config.get("relative_valuation", {})
_PEER_FETCH_WORKERS = _val_cfg.get("peer_fetch_workers", 6)
_HISTORY_YEARS = _val_cfg.get("history_years", 5)

# Metrics to extract from yfinance info
_METRIC_KEYS = {
    "pe_trailing": "trailingPE",
    "pe_forward": "forwardPE",
    "peg_ratio": "pegRatio",
    "ev_ebitda": "enterpriseToEbitda",
    "price_to_sales": "priceToSalesTrailing12Months",
    "price_to_book": "priceToBook",
    "dividend_yield": "dividendYield",
    "revenue_growth": "revenueGrowth",
    "earnings_growth": "earningsGrowth",
    "profit_margin": "profitMargins",
    "roe": "returnOnEquity",
    "debt_to_equity": "debtToEquity",
}

# For composite score: lower is cheaper for these metrics
_LOWER_IS_CHEAPER = {"pe_trailing", "pe_forward", "peg_ratio", "ev_ebitda",
                      "price_to_sales", "price_to_book", "debt_to_equity"}
# Higher is better for these
_HIGHER_IS_BETTER = {"dividend_yield", "revenue_growth", "earnings_growth",
                      "profit_margin", "roe"}

# Weights for composite valuation score
_COMPOSITE_WEIGHTS = _val_cfg.get("composite_weights", {
    "pe_trailing": 0.15,
    "pe_forward": 0.15,
    "peg_ratio": 0.12,
    "ev_ebitda": 0.15,
    "price_to_sales": 0.10,
    "price_to_book": 0.08,
    "dividend_yield": 0.05,
    "revenue_growth": 0.08,
    "earnings_growth": 0.07,
    "profit_margin": 0.05,
})


def _fetch_ticker_metrics(ticker: str) -> Optional[dict]:
    """Fetch valuation metrics for a single ticker from Yahoo Finance."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}
        if not info or info.get("regularMarketPrice") is None:
            return None

        metrics = {"ticker": ticker}
        for key, yf_key in _METRIC_KEYS.items():
            val = info.get(yf_key)
            if val is not None and isinstance(val, (int, float)) and np.isfinite(val):
                metrics[key] = float(val)
            else:
                metrics[key] = None

        # FCF yield = FCF / market cap
        fcf = info.get("freeCashflow")
        mcap = info.get("marketCap")
        if fcf and mcap and mcap > 0:
            metrics["fcf_yield"] = float(fcf / mcap)
        else:
            metrics["fcf_yield"] = None

        metrics["market_cap"] = float(mcap) if mcap else None
        metrics["name"] = info.get("shortName", ticker)
        metrics["sector"] = info.get("sector", "Unknown")

        # Inputs for the comps-based fair value (analyst method)
        metrics["price"] = float(info["regularMarketPrice"])
        for k, yk in (("forward_eps", "forwardEps"),
                      ("trailing_eps", "trailingEps"),
                      ("revenue_per_share", "revenuePerShare")):
            v = info.get(yk)
            metrics[k] = float(v) if isinstance(v, (int, float)) and np.isfinite(v) else None

        return metrics
    except Exception as e:
        logger.debug("relative_valuation fetch failed for %s: %s", ticker, e)
        return None


def _compute_percentile(value: float, all_values: list[float]) -> float:
    """Compute the percentile of a value within a list (0-100)."""
    if not all_values or len(all_values) < 2:
        return 50.0
    below = sum(1 for v in all_values if v < value)
    equal = sum(1 for v in all_values if v == value)
    return float(round((below + 0.5 * equal) / len(all_values) * 100, 1))


def _compute_historical_valuation(ticker: str) -> Optional[dict]:
    """Compute historical P/E and P/S ranges using price history + financials.

    Returns current vs historical average percentile for context.
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}

        current_pe = info.get("trailingPE")
        current_ps = info.get("priceToSalesTrailing12Months")
        current_pb = info.get("priceToBook")

        # Get 5Y price history for rough historical multiples
        hist = stock.history(period="5y")
        if hist is None or len(hist) < 252:
            return None

        prices = hist["Close"].dropna()
        if len(prices) < 252:
            return None

        # Use trailing EPS to estimate historical P/E range
        eps_ttm = info.get("trailingEps")
        revenue_per_share = info.get("revenuePerShare")
        book_value = info.get("bookValue")

        result = {}

        if current_pe and eps_ttm and eps_ttm > 0:
            historical_pes = (prices / eps_ttm).dropna()
            if len(historical_pes) > 50:
                result["pe_current"] = float(current_pe)
                result["pe_5y_avg"] = float(round(historical_pes.mean(), 2))
                result["pe_5y_min"] = float(round(historical_pes.min(), 2))
                result["pe_5y_max"] = float(round(historical_pes.max(), 2))
                result["pe_5y_median"] = float(round(historical_pes.median(), 2))
                pctile = _compute_percentile(current_pe, historical_pes.tolist())
                result["pe_percentile_vs_history"] = pctile

        if current_ps and revenue_per_share and revenue_per_share > 0:
            historical_ps = (prices / revenue_per_share).dropna()
            if len(historical_ps) > 50:
                result["ps_current"] = float(current_ps)
                result["ps_5y_avg"] = float(round(historical_ps.mean(), 2))
                result["ps_5y_min"] = float(round(historical_ps.min(), 2))
                result["ps_5y_max"] = float(round(historical_ps.max(), 2))

        if current_pb and book_value and book_value > 0:
            historical_pb = (prices / book_value).dropna()
            if len(historical_pb) > 50:
                result["pb_current"] = float(current_pb)
                result["pb_5y_avg"] = float(round(historical_pb.mean(), 2))

        return result if result else None
    except Exception as e:
        logger.debug("historical valuation failed for %s: %s", ticker, e)
        return None


def _find_sector_peers(ticker: str, sector: str) -> list[str]:
    """Find sector peers for a ticker from the configured stock universe."""
    peers = []
    for sector_name, tickers in SECTOR_STOCK_MAP.items():
        if ticker in tickers:
            peers = [t for t in tickers if t != ticker]
            break

    # Fallback: search by sector name
    if not peers:
        for sector_name, tickers in SECTOR_STOCK_MAP.items():
            if sector_name.lower() in sector.lower() or sector.lower() in sector_name.lower():
                peers = [t for t in tickers if t != ticker]
                break

    return peers


def get_relative_valuation(ticker: str) -> Optional[dict]:
    """Compute relative valuation for a stock vs its sector peers.

    Returns:
        Dict with peer_comparison, percentile_rankings, composite_score,
        historical_context, and valuation_verdict.
    """
    # Fetch target stock metrics
    target = _fetch_ticker_metrics(ticker)
    if target is None:
        return None

    sector = target.get("sector", "Unknown")

    # Find and fetch peer metrics in parallel
    peers = _find_sector_peers(ticker, sector)
    if not peers:
        logger.info("No sector peers found for %s (%s)", ticker, sector)
        return None

    all_metrics = [target]
    with ThreadPoolExecutor(max_workers=_PEER_FETCH_WORKERS) as executor:
        futures = {executor.submit(_fetch_ticker_metrics, p): p for p in peers}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                all_metrics.append(result)

    if len(all_metrics) < 3:
        logger.info("Too few peers for %s: %d found", ticker, len(all_metrics) - 1)
        return None

    # Compute percentile rankings for each metric
    rankings = {}
    metric_keys = list(_METRIC_KEYS.keys()) + ["fcf_yield"]

    for metric in metric_keys:
        target_val = target.get(metric)
        if target_val is None:
            rankings[metric] = {"value": None, "percentile": None, "peer_avg": None}
            continue

        peer_values = [m[metric] for m in all_metrics if m.get(metric) is not None]
        if len(peer_values) < 3:
            rankings[metric] = {"value": round(target_val, 4), "percentile": None, "peer_avg": None}
            continue

        pctile = _compute_percentile(target_val, peer_values)
        other_values = [v for v in peer_values if v != target_val]
        peer_avg = float(np.mean(other_values)) if other_values else None

        # For valuation ratios, invert percentile so lower = cheaper = better
        valuation_pctile = pctile
        if metric in _LOWER_IS_CHEAPER:
            valuation_pctile = 100.0 - pctile  # Now higher = cheaper = better

        rankings[metric] = {
            "value": round(target_val, 4),
            "percentile": round(pctile, 1),
            "valuation_percentile": round(valuation_pctile, 1),
            "peer_avg": round(peer_avg, 4) if peer_avg is not None else None,
            "peer_count": len(peer_values) - 1,  # exclude target
            "vs_peers": _interpret_vs_peers(metric, target_val, peer_avg),
        }

    # Composite valuation score (0-100, higher = cheaper/more attractive)
    composite_score, score_components = _compute_composite_score(rankings)

    # Historical valuation context
    historical = _compute_historical_valuation(ticker)

    # Peer comparison table
    peer_table = []
    for m in all_metrics:
        row = {
            "ticker": m["ticker"],
            "name": m.get("name", m["ticker"]),
            "is_target": m["ticker"] == ticker,
        }
        for metric in ["pe_trailing", "pe_forward", "ev_ebitda", "price_to_sales",
                        "price_to_book", "dividend_yield", "revenue_growth", "profit_margin"]:
            val = m.get(metric)
            row[metric] = round(val, 4) if val is not None else None
        row["market_cap"] = m.get("market_cap")
        peer_table.append(row)

    # Sort peer table by market cap descending
    peer_table.sort(key=lambda x: x.get("market_cap") or 0, reverse=True)

    # Valuation verdict
    verdict = _compute_verdict(composite_score, historical)

    # Comps-based fair value — the sell-side method (peer-median multiple ×
    # the company's own per-share figure), NOT a prediction like the MC.
    fair_value = _compute_implied_fair_value(target, all_metrics)

    return {
        "ticker": ticker,
        "sector": sector,
        "peer_count": len(all_metrics) - 1,
        "rankings": rankings,
        "composite_score": composite_score,
        "score_components": score_components,
        "verdict": verdict,
        "historical": historical,
        "peer_table": peer_table,
        "implied_fair_value": fair_value,
    }


def _compute_implied_fair_value(target: dict, all_metrics: list[dict]) -> Optional[dict]:
    """Comps-based fair value: peer-MEDIAN multiple × the target's own
    per-share figure — the standard analyst comparables method. Estimates
    are only produced where the input is meaningful (positive EPS/revenue);
    the blended value is the mean of the available estimates."""
    peers = [m for m in all_metrics if m["ticker"] != target["ticker"]]
    price = target.get("price")
    if not price or price <= 0:
        return None

    def _peer_median(metric: str) -> Optional[float]:
        vals = [m[metric] for m in peers
                if m.get(metric) is not None and m[metric] > 0]
        return float(np.median(vals)) if len(vals) >= 3 else None

    estimates = {}
    fwd_eps = target.get("forward_eps")
    med_fwd_pe = _peer_median("pe_forward")
    if fwd_eps and fwd_eps > 0 and med_fwd_pe:
        estimates["forward_pe"] = round(fwd_eps * med_fwd_pe, 2)
    ttm_eps = target.get("trailing_eps")
    med_ttm_pe = _peer_median("pe_trailing")
    if ttm_eps and ttm_eps > 0 and med_ttm_pe:
        estimates["trailing_pe"] = round(ttm_eps * med_ttm_pe, 2)
    rps = target.get("revenue_per_share")
    med_ps = _peer_median("price_to_sales")
    if rps and rps > 0 and med_ps:
        estimates["price_to_sales"] = round(rps * med_ps, 2)

    if not estimates:
        return None
    blended = float(np.mean(list(estimates.values())))
    return {
        "blended": round(blended, 2),
        "upside_pct": round((blended / price - 1) * 100, 1),
        "estimates": estimates,
        "peer_medians": {"pe_forward": med_fwd_pe, "pe_trailing": med_ttm_pe,
                         "price_to_sales": med_ps},
        "method": ("peer-median multiples × own per-share figures (comps) — "
                   "what the stock would trade at if priced like its sector "
                   "median; not a forecast"),
    }


def _interpret_vs_peers(metric: str, value: float, peer_avg: Optional[float]) -> str:
    """Generate a human-readable interpretation of a metric vs peer average."""
    if peer_avg is None or peer_avg == 0:
        return "N/A"

    diff_pct = (value / peer_avg - 1) * 100

    if metric in _LOWER_IS_CHEAPER:
        if diff_pct < -20:
            return "significantly cheaper"
        elif diff_pct < -5:
            return "cheaper"
        elif diff_pct < 5:
            return "in line"
        elif diff_pct < 20:
            return "premium"
        else:
            return "significant premium"
    elif metric in _HIGHER_IS_BETTER:
        if diff_pct > 20:
            return "significantly above peers"
        elif diff_pct > 5:
            return "above peers"
        elif diff_pct > -5:
            return "in line"
        elif diff_pct > -20:
            return "below peers"
        else:
            return "significantly below peers"
    return "N/A"


def _compute_composite_score(rankings: dict) -> tuple[float, dict]:
    """Compute a composite valuation attractiveness score (0-100).

    Higher = more attractively valued (cheaper ratios, better growth).
    """
    total_weight = 0.0
    weighted_sum = 0.0
    components = {}

    for metric, weight in _COMPOSITE_WEIGHTS.items():
        r = rankings.get(metric, {})
        val_pctile = r.get("valuation_percentile")
        if val_pctile is None:
            continue

        weighted_sum += val_pctile * weight
        total_weight += weight
        components[metric] = {
            "percentile": val_pctile,
            "weight": weight,
            "contribution": round(val_pctile * weight, 2),
        }

    if total_weight < 0.3:
        return 50.0, components

    score = round(weighted_sum / total_weight, 1)
    return score, components


def _compute_verdict(composite_score: float, historical: Optional[dict]) -> dict:
    """Generate a valuation verdict based on composite score and historical context."""
    thresholds = _val_cfg.get("verdict_thresholds", {
        "deep_value": 75,
        "undervalued": 60,
        "fair_value_upper": 55,
        "fair_value_lower": 45,
        "overvalued": 35,
    })

    if composite_score >= thresholds.get("deep_value", 75):
        label = "Deep Value"
        color = "green"
        description = "Trading at a significant discount to sector peers across multiple metrics"
    elif composite_score >= thresholds.get("undervalued", 60):
        label = "Undervalued"
        color = "green"
        description = "Cheaper than most sector peers on key valuation metrics"
    elif composite_score >= thresholds.get("fair_value_upper", 55):
        label = "Fair Value"
        color = "yellow"
        description = "Valued roughly in line with sector peers"
    elif composite_score >= thresholds.get("fair_value_lower", 45):
        label = "Fair Value"
        color = "yellow"
        description = "Valued roughly in line with sector peers"
    elif composite_score >= thresholds.get("overvalued", 35):
        label = "Overvalued"
        color = "orange"
        description = "Trading at a premium to most sector peers"
    else:
        label = "Significantly Overvalued"
        color = "red"
        description = "Trading at a significant premium to sector peers across multiple metrics"

    result = {
        "label": label,
        "color": color,
        "description": description,
        "composite_score": composite_score,
    }

    # Enrich with historical context if available
    if historical:
        pe_hist_pctile = historical.get("pe_percentile_vs_history")
        if pe_hist_pctile is not None:
            if pe_hist_pctile > 80:
                result["historical_note"] = "P/E is near 5-year highs — historically expensive for this stock"
            elif pe_hist_pctile < 20:
                result["historical_note"] = "P/E is near 5-year lows — historically cheap for this stock"
            else:
                result["historical_note"] = f"P/E is at the {pe_hist_pctile:.0f}th percentile of its 5-year range"

    return result


def get_valuation_summary(ticker: str) -> Optional[dict]:
    """Lightweight summary for embedding in stock analysis responses.

    Returns just the composite score, verdict label, and top metric comparisons.
    """
    full = get_relative_valuation(ticker)
    if full is None:
        return None

    # Pick top 3 most notable metric comparisons
    notable = []
    for metric, r in full["rankings"].items():
        if r.get("percentile") is not None and r.get("vs_peers") not in (None, "N/A", "in line"):
            notable.append({
                "metric": metric,
                "value": r["value"],
                "peer_avg": r["peer_avg"],
                "vs_peers": r["vs_peers"],
                "percentile": r["percentile"],
            })

    # Sort by extremity (distance from 50th percentile)
    notable.sort(key=lambda x: abs(x["percentile"] - 50), reverse=True)

    return {
        "composite_score": full["composite_score"],
        "verdict": full["verdict"]["label"],
        "verdict_color": full["verdict"]["color"],
        "peer_count": full["peer_count"],
        "sector": full["sector"],
        "notable_metrics": notable[:4],
        "historical_pe_pctile": full.get("historical", {}).get("pe_percentile_vs_history") if full.get("historical") else None,
        "implied_fair_value": full.get("implied_fair_value"),
    }
