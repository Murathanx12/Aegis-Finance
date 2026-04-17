"""
Aegis Finance — Historical Asset-Allocation Backtester
=========================================================

Portfolio-Visualizer-style backtesting for canonical asset-allocation
strategies (60/40, 3-fund, Permanent Portfolio, All-Weather, Golden
Butterfly) and user-defined weights. Reports CAGR, volatility, Sharpe,
max drawdown, and the full equity curve.

Uses yfinance ETFs as building blocks so the free data path works
without any paid subscription.

References:
  - Bernstein (2000), The Intelligent Asset Allocator
  - Dalio (2007), All-Weather Portfolio
  - Bengen (1994), Safemax withdrawal rate
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from backend.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

_CACHE_TTL = 3600  # 1hr — historical data doesn't change intraday

# Named strategies → ETF weights
NAMED_STRATEGIES: dict[str, dict[str, float]] = {
    "60_40": {"SPY": 0.60, "AGG": 0.40},
    "3_fund": {"VTI": 0.60, "VXUS": 0.20, "BND": 0.20},
    "permanent_portfolio": {"SPY": 0.25, "TLT": 0.25, "GLD": 0.25, "BIL": 0.25},
    "all_weather": {
        "SPY": 0.30, "TLT": 0.40, "IEF": 0.15, "GLD": 0.075, "DBC": 0.075,
    },
    "golden_butterfly": {
        "VTI": 0.20, "VBR": 0.20, "TLT": 0.20, "SHY": 0.20, "GLD": 0.20,
    },
    "risk_parity_lite": {"SPY": 0.30, "TLT": 0.40, "GLD": 0.30},
    "100_equity": {"VTI": 1.0},
    "stocks_bonds_gold": {"SPY": 0.40, "AGG": 0.40, "GLD": 0.20},
}


def _download_closes(tickers: list[str], start: str) -> Optional[pd.DataFrame]:
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        df = yf.download(
            tickers=" ".join(tickers),
            start=start,
            auto_adjust=True,
            group_by="column",
            threads=True,
            progress=False,
        )
    except Exception as e:
        logger.warning("allocation_backtester yfinance download failed: %s", e)
        return None
    if df is None or df.empty:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        closes = df["Close"] if "Close" in df.columns.get_level_values(0) else df["Adj Close"]
    else:
        closes = df[["Close"]] if "Close" in df.columns else df
        closes.columns = tickers[:1]
    return closes.dropna(how="all")


def _rebalanced_equity_curve(
    closes: pd.DataFrame,
    weights: dict[str, float],
    rebalance_freq: str = "quarterly",
    initial_value: float = 10_000.0,
) -> pd.Series:
    """Compute the equity curve of a periodically rebalanced portfolio.

    Rebalance calendar:
      - "monthly"     → first business day of each month
      - "quarterly"   → first business day of Jan, Apr, Jul, Oct (default)
      - "annual"      → first business day of each year
      - "buy_and_hold" → never rebalance after inception
    """
    tickers = list(weights.keys())
    aligned = closes.reindex(columns=tickers).dropna(how="all")
    if aligned.empty:
        raise ValueError("No aligned price history for the given tickers")

    # Drop columns with no data at all — partial coverage is OK if >=1 ticker
    aligned = aligned.dropna(axis=1, how="all")
    if aligned.empty:
        raise ValueError("All requested tickers have empty history")

    # Forward-fill gaps (weekends/holidays handled upstream by yfinance)
    aligned = aligned.ffill().dropna()
    if len(aligned) < 2:
        raise ValueError("Need at least 2 observations to compute a backtest")

    # Normalize weights over available tickers
    active_weights = {t: w for t, w in weights.items() if t in aligned.columns}
    total_w = sum(active_weights.values())
    if total_w <= 0:
        raise ValueError("Active ticker weights sum to zero")
    active_weights = {t: w / total_w for t, w in active_weights.items()}

    # Determine rebalance dates
    if rebalance_freq == "buy_and_hold":
        rebalance_dates = {aligned.index[0]}
    else:
        freq_map = {"monthly": "MS", "quarterly": "QS", "annual": "YS"}
        rule = freq_map.get(rebalance_freq, "QS")
        resampled = aligned.resample(rule).first().index
        rebalance_dates = set(resampled)
        rebalance_dates.add(aligned.index[0])

    # Vectorized: track units per ticker; at rebalance, reset units to realize weights
    values = pd.Series(index=aligned.index, dtype=float)
    units = pd.Series({t: 0.0 for t in active_weights})
    pv = float(initial_value)

    for date, row in aligned.iterrows():
        if date in rebalance_dates or units.sum() == 0.0:
            # Reset units to hit target weights at current prices
            for t, w in active_weights.items():
                price = row[t]
                if not np.isnan(price) and price > 0:
                    units[t] = pv * w / price
        # Update pv from current prices
        pv = float(sum(units[t] * row[t] for t in active_weights if not np.isnan(row[t])))
        values.loc[date] = pv

    return values.dropna()


def _metrics(equity: pd.Series, periods_per_year: int = 252) -> dict:
    returns = equity.pct_change().dropna()
    if returns.empty:
        return {}
    n_years = max(len(returns) / periods_per_year, 1e-6)
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / n_years) - 1
    vol = float(returns.std() * np.sqrt(periods_per_year))
    sharpe = float(returns.mean() / returns.std() * np.sqrt(periods_per_year)) if returns.std() > 0 else None

    # Max drawdown
    cummax = equity.cummax()
    drawdown = equity / cummax - 1.0
    mdd = float(drawdown.min())
    peak = cummax.idxmax()
    trough = drawdown.idxmin()

    # Worst year + best year
    annual = equity.resample("YE").last().pct_change().dropna()
    best_year = float(annual.max()) if not annual.empty else None
    worst_year = float(annual.min()) if not annual.empty else None

    return {
        "cagr": round(float(cagr), 4),
        "volatility_annualized": round(vol, 4),
        "sharpe_ratio": None if sharpe is None else round(sharpe, 3),
        "max_drawdown": round(mdd, 4),
        "max_drawdown_peak_date": peak.strftime("%Y-%m-%d") if hasattr(peak, "strftime") else None,
        "max_drawdown_trough_date": trough.strftime("%Y-%m-%d") if hasattr(trough, "strftime") else None,
        "best_calendar_year": None if best_year is None else round(best_year, 4),
        "worst_calendar_year": None if worst_year is None else round(worst_year, 4),
        "final_value": round(float(equity.iloc[-1]), 2),
        "n_years": round(n_years, 2),
    }


def backtest_allocation(
    weights: dict[str, float],
    start: str = "2005-01-01",
    rebalance_freq: str = "quarterly",
    initial_value: float = 10_000.0,
    sample_curve_points: int = 250,
) -> dict:
    """Backtest a weighted allocation of ETFs and return metrics + equity curve."""
    if not weights:
        raise ValueError("weights must be non-empty")
    if abs(sum(weights.values()) - 1.0) > 0.02:
        raise ValueError(f"Weights must sum to ~1.0 (got {sum(weights.values()):.3f})")

    cache_key = f"aa_backtest:{hash(frozenset(weights.items()))}:{start}:{rebalance_freq}"
    cached = cache_get(cache_key, _CACHE_TTL)
    if cached is not None:
        return cached

    closes = _download_closes(list(weights.keys()), start)
    if closes is None or closes.empty:
        return {"error": "No price data for requested tickers"}

    equity = _rebalanced_equity_curve(closes, weights, rebalance_freq, initial_value)
    metrics = _metrics(equity)

    # Downsample curve for the frontend (avoid shipping ~5000 points)
    if len(equity) > sample_curve_points:
        step = max(1, len(equity) // sample_curve_points)
        equity_sampled = equity.iloc[::step]
    else:
        equity_sampled = equity
    curve = [
        {"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 2)}
        for d, v in equity_sampled.items()
    ]

    result = {
        "weights": weights,
        "start": start,
        "rebalance_freq": rebalance_freq,
        "initial_value": initial_value,
        "metrics": metrics,
        "equity_curve": curve,
        "n_observations": len(equity),
    }
    cache_set(cache_key, result)
    return result


def backtest_named(name: str, **kwargs) -> dict:
    """Backtest one of the predefined allocation strategies."""
    if name not in NAMED_STRATEGIES:
        raise ValueError(f"Unknown strategy {name!r}. Options: {sorted(NAMED_STRATEGIES.keys())}")
    return backtest_allocation(weights=NAMED_STRATEGIES[name], **kwargs)


def compare_strategies(
    names: Optional[list[str]] = None,
    start: str = "2005-01-01",
) -> dict:
    """Run several strategies and return a comparison table."""
    names = names or ["60_40", "3_fund", "permanent_portfolio", "all_weather"]
    rows = []
    for name in names:
        try:
            r = backtest_named(name, start=start)
        except Exception as e:
            rows.append({"name": name, "error": str(e)})
            continue
        metrics = r.get("metrics") or {}
        rows.append({
            "name": name,
            "weights": r.get("weights"),
            **metrics,
        })
    return {"start": start, "strategies": rows}
