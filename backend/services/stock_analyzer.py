"""
Aegis Finance — Individual Stock Analysis
============================================

Per-ticker projections using fundamental-aware Monte Carlo:
  1. Fetch price history + fundamentals from Yahoo Finance
  2. Cap drift by market-cap tier
  3. Blend with analyst targets
  4. Run jump-diffusion Monte Carlo

Usage:
    from backend.services.stock_analyzer import analyze_stock, analyze_stocks
"""

import logging
from typing import Optional

import numpy as np
import yfinance as yf

from backend.config import config
from backend.services.monte_carlo import simulate_paths

logger = logging.getLogger(__name__)

# CAGR caps by market cap tier
STOCK_CAGR_CAPS = {
    "mega":  (0.04, 0.15),
    "large": (0.05, 0.20),
    "mid":   (0.06, 0.25),
    "small": (0.08, 0.30),
}

DEFAULT_WATCHLIST = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META",
    "TSLA", "JPM", "JNJ", "V", "UNH", "XOM",
]

SECTOR_STOCK_MAP = {
    "Technology":       ["AAPL", "MSFT", "NVDA", "AVGO", "CRM", "PLTR", "NOW", "AMD"],
    "Healthcare":       ["UNH", "LLY", "JNJ", "ISRG", "VRTX", "DXCM", "GEHC"],
    "Financials":       ["JPM", "V", "MA", "GS", "BLK", "COIN", "SQ"],
    "Energy":           ["XOM", "CVX", "SLB", "OKE", "FSLR", "ENPH"],
    "Consumer Disc.":   ["AMZN", "TSLA", "HD", "NKE", "BKNG", "ABNB"],
    "Industrials":      ["CAT", "GE", "RTX", "UBER", "AXON", "TT"],
    "Communications":   ["META", "GOOGL", "NFLX", "DIS", "RBLX", "SPOT"],
    "Consumer Staples": ["COST", "PG", "KO", "WMT", "MNST"],
    "Materials":        ["LIN", "FCX", "NEM", "VMC"],
    "Utilities":        ["NEE", "VST", "CEG", "SO"],
    "Real Estate":      ["PLD", "AMT", "EQIX", "O"],
}


def _get_cap_tier(market_cap) -> str:
    if market_cap is None or market_cap <= 0:
        return "large"
    b = market_cap / 1e9
    if b > 200:
        return "mega"
    elif b > 10:
        return "large"
    elif b > 2:
        return "mid"
    else:
        return "small"


def select_stocks_from_sectors(sector_results: dict, n_stocks: int = 20) -> list[str]:
    """Data-driven stock selection from top-performing sectors."""
    if not sector_results:
        return DEFAULT_WATCHLIST[:n_stocks]

    ranked = sorted(
        sector_results.items(),
        key=lambda x: x[1].get("expected_total", x[1].get("expected_return", 0)),
        reverse=True,
    )
    selected = []

    for i, (sector_name, _) in enumerate(ranked):
        if sector_name not in SECTOR_STOCK_MAP:
            continue
        pool = SECTOR_STOCK_MAP[sector_name]
        picks = min(3, len(pool)) if i < 3 else min(2, len(pool)) if i < 7 else 1
        selected.extend(pool[:picks])
        if len(selected) >= n_stocks:
            break

    seen = set()
    return [t for t in selected if not (t in seen or seen.add(t))][:n_stocks]


def analyze_stock(
    ticker: str,
    forecast_days: int = 1260,
    risk_free_rate: float = 0.04,
) -> Optional[dict]:
    """Analyze a single stock with fundamental-aware Monte Carlo."""
    max_5y_return = config["simulation"]["max_5y_return"]

    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}

        hist = stock.history(period="5y")
        if hist.empty or len(hist) < 252:
            logger.warning("%s: Insufficient price history", ticker)
            return None

        prices = hist["Close"]
        current_price = float(prices.iloc[-1])

        market_cap = info.get("marketCap", None)
        cap_tier = _get_cap_tier(market_cap)
        beta = info.get("beta", 1.0)
        if beta is None or beta <= 0:
            beta = 1.0
        analyst_target = info.get("targetMeanPrice", None)
        company_name = info.get("shortName", ticker)
        sector = info.get("sector", "Unknown")
        pe_ratio = info.get("trailingPE", None)

        returns = prices.pct_change().dropna()
        log_returns = np.log(1 + returns)
        hist_mu = float(log_returns.mean() * 252)
        hist_sigma = float(returns.std() * np.sqrt(252))

        min_cagr, max_cagr = STOCK_CAGR_CAPS[cap_tier]
        capped_mu = np.clip(hist_mu, min_cagr, max_cagr)

        if analyst_target is not None and analyst_target > 0:
            analyst_1y_return = (analyst_target / current_price) - 1
            analyst_annual = np.clip(analyst_1y_return, -0.30, max_cagr)
            blended_mu = 0.60 * capped_mu + 0.40 * analyst_annual
        else:
            blended_mu = capped_mu

        final_mu = float(np.clip(blended_mu, min_cagr * 0.5, max_cagr))
        final_sigma = float(np.clip(hist_sigma, 0.15, 0.80))

        base_scenario = {"drift_adj": 0, "vol_mult": 1.0, "crash_mult": 1.0}
        paths = simulate_paths(
            current_price, final_mu, final_sigma,
            forecast_days, 3000, 0.07, 0.0, base_scenario,
        )

        final_prices = np.minimum(paths[-1], current_price * (1 + max_5y_return))
        exp_return = float(np.mean(final_prices) / current_price - 1) * 100
        med_return = float(np.median(final_prices) / current_price - 1) * 100
        p05 = float(np.percentile(final_prices, 5))
        p95 = float(np.percentile(final_prices, 95))
        prob_loss = float(np.mean(final_prices < current_price)) * 100

        running_peak = np.maximum.accumulate(paths, axis=0)
        drawdowns = (paths - running_peak) / running_peak
        avg_max_dd = float(np.mean(drawdowns.min(axis=0))) * 100

        sharpe = (final_mu - risk_free_rate) / final_sigma if final_sigma > 0 else 0

        # Enriched data from yfinance
        analyst_targets = _get_analyst_targets(stock)
        recommendations = _get_recommendations(stock)
        holders = _get_holders(stock)
        news = _get_news(stock)
        earnings = _get_earnings(stock)

        return {
            "ticker": ticker, "name": company_name, "sector": sector,
            "current_price": current_price,
            "market_cap": market_cap, "cap_tier": cap_tier,
            "beta": beta, "pe_ratio": pe_ratio,
            "analyst_target": analyst_target,
            "hist_drift": hist_mu * 100, "capped_drift": final_mu * 100,
            "volatility": final_sigma * 100,
            "expected_return": exp_return, "median_return": med_return,
            "p05_price": p05, "p95_price": p95,
            "prob_loss_5y": prob_loss, "avg_max_drawdown": avg_max_dd,
            "sharpe": sharpe,
            "analyst_targets": analyst_targets,
            "recommendations": recommendations,
            "holders": holders,
            "news": news,
            "earnings": earnings,
        }

    except Exception as e:
        logger.warning("%s: Analysis failed — %s", ticker, e)
        return None


def _get_analyst_targets(stock) -> Optional[dict]:
    """Extract analyst price targets from yfinance Ticker."""
    try:
        targets = stock.analyst_price_targets
        if targets is None:
            return None
        # Could be a DataFrame or dict-like
        if hasattr(targets, "to_dict"):
            t = targets.to_dict() if hasattr(targets, "to_dict") else {}
        elif isinstance(targets, dict):
            t = targets
        else:
            return None
        return {
            "current": t.get("current"),
            "low": t.get("low"),
            "mean": t.get("mean"),
            "median": t.get("median"),
            "high": t.get("high"),
        }
    except Exception:
        return None


def _get_recommendations(stock) -> Optional[dict]:
    """Extract analyst recommendations summary."""
    try:
        rec = stock.recommendations
        if rec is None or (hasattr(rec, "empty") and rec.empty):
            return None
        # Get the most recent row
        if hasattr(rec, "iloc"):
            latest = rec.iloc[-1] if len(rec) > 0 else None
            if latest is None:
                return None
            return {
                "strongBuy": int(latest.get("strongBuy", 0)),
                "buy": int(latest.get("buy", 0)),
                "hold": int(latest.get("hold", 0)),
                "sell": int(latest.get("sell", 0)),
                "strongSell": int(latest.get("strongSell", 0)),
            }
        return None
    except Exception:
        return None


def _get_holders(stock) -> Optional[dict]:
    """Extract major holders + top institutional holders."""
    try:
        result = {}

        # Major holders (% insider, % institution)
        major = stock.major_holders
        if major is not None and hasattr(major, "iloc"):
            for idx in range(len(major)):
                val = str(major.iloc[idx, 0]) if major.shape[1] > 0 else ""
                label = str(major.iloc[idx, 1]) if major.shape[1] > 1 else ""
                label_lower = label.lower()
                if "insider" in label_lower:
                    result["insider_pct"] = val
                elif "institution" in label_lower:
                    result["institution_pct"] = val

        # Top institutional holders
        inst = stock.institutional_holders
        if inst is not None and hasattr(inst, "iterrows") and not inst.empty:
            top = []
            for _, row in inst.head(10).iterrows():
                holder = {
                    "name": str(row.get("Holder", "")),
                    "shares": int(row.get("Shares", 0)) if row.get("Shares") else 0,
                    "pct": float(row.get("% Out", 0)) if row.get("% Out") else 0,
                }
                top.append(holder)
            result["top_holders"] = top

        return result if result else None
    except Exception:
        return None


def _get_news(stock, max_items: int = 8) -> Optional[list]:
    """Extract recent news from yfinance."""
    try:
        raw = stock.news
        if not raw:
            return None
        items = []
        for item in raw[:max_items]:
            content = item.get("content", item)
            items.append({
                "title": content.get("title", item.get("title", "")),
                "publisher": content.get("provider", {}).get("displayName", "") if isinstance(content.get("provider"), dict) else item.get("publisher", ""),
                "link": content.get("canonicalUrl", {}).get("url", "") if isinstance(content.get("canonicalUrl"), dict) else item.get("link", ""),
                "date": content.get("pubDate", item.get("providerPublishTime", "")),
            })
        return items if items else None
    except Exception:
        return None


def _get_earnings(stock) -> Optional[dict]:
    """Extract upcoming earnings info."""
    try:
        import pandas as pd
        dates = stock.earnings_dates
        if dates is None or (hasattr(dates, "empty") and dates.empty):
            return None

        now = pd.Timestamp.now(tz="UTC") if dates.index.tz else pd.Timestamp.now()
        future = dates[dates.index >= now]
        next_date = str(future.index[0].date()) if len(future) > 0 else None

        estimate = None
        if len(future) > 0 and "EPS Estimate" in future.columns:
            est = future.iloc[0].get("EPS Estimate")
            if est is not None and not (isinstance(est, float) and np.isnan(est)):
                estimate = float(est)

        # Surprise history (last 4 quarters)
        past = dates[dates.index < now].head(4)
        surprises = []
        if "Surprise(%)" in past.columns:
            for _, row in past.iterrows():
                s = row.get("Surprise(%)")
                if s is not None and not (isinstance(s, float) and np.isnan(s)):
                    surprises.append(float(s))

        return {
            "next_date": next_date,
            "estimate": estimate,
            "surprise_history": surprises,
        }
    except Exception:
        return None


def analyze_stocks(
    tickers: Optional[list[str]] = None,
    forecast_days: int = 1260,
    risk_free_rate: float = 0.04,
) -> dict:
    """Analyze a portfolio of individual stocks."""
    if tickers is None:
        tickers = DEFAULT_WATCHLIST

    logger.info("Analyzing %d stocks...", len(tickers))
    results = {}

    for ticker in tickers:
        result = analyze_stock(ticker, forecast_days, risk_free_rate)
        if result is not None:
            results[ticker] = result

    logger.info("%d/%d stocks analyzed", len(results), len(tickers))
    return results
