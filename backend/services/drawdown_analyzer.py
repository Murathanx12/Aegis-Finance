"""
Aegis Finance — Drawdown & Rolling Return Analysis
=====================================================

Portfolio Visualizer's most popular analytics, now in Aegis:

1. Drawdown Analysis: Identifies every drawdown from peak, measures depth,
   duration, and recovery time. Essential for understanding real portfolio pain.

2. Rolling Returns: Computes rolling 1Y, 3Y, 5Y returns over the full history.
   Shows how return expectations change depending on entry date.

3. Rolling Risk Metrics: Rolling Sharpe ratio, Sortino ratio, max drawdown —
   shows how risk-adjusted performance evolves over time.

References:
  - Magdon-Ismail et al. (2004), "On the Maximum Drawdown of a Brownian Motion"
  - Bailey & Lopez de Prado (2014), "The Deflated Sharpe Ratio"

Usage:
    from backend.services.drawdown_analyzer import (
        analyze_drawdowns, compute_rolling_returns,
        compute_rolling_risk_metrics, full_drawdown_analysis,
    )
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from backend.config import config

logger = logging.getLogger(__name__)


def analyze_drawdowns(
    prices: pd.Series,
    min_drawdown_pct: float = 5.0,
) -> dict:
    """Identify all drawdowns from peak, with depth, duration, and recovery time.

    A drawdown starts when price drops from a running peak and ends when
    price recovers to a new all-time high. This is how institutional investors
    measure real portfolio pain — not volatility, but actual losses experienced.

    Args:
        prices: Price series (DatetimeIndex)
        min_drawdown_pct: Minimum drawdown depth to report (default 5%)

    Returns:
        Dict with list of drawdowns, current drawdown status, and summary stats.
    """
    prices = prices.dropna()
    if len(prices) < 20:
        return {"drawdowns": [], "current": None, "summary": {}}

    # Running peak
    peak = prices.cummax()
    drawdown_pct = (prices / peak - 1) * 100  # Negative percentages

    # Identify drawdown periods
    drawdowns = []
    in_drawdown = False
    dd_start = None
    dd_peak_price = None
    dd_trough = 0.0
    dd_trough_date = None

    for i in range(len(prices)):
        dd = float(drawdown_pct.iloc[i])

        if dd < -min_drawdown_pct and not in_drawdown:
            # Start of a new drawdown
            in_drawdown = True
            # Find the peak date (last date AT OR BEFORE current index when
            # price equaled the running max). Must restrict to past dates only;
            # searching the full series would pick future dates if the same
            # price appears after recovery.
            peak_val = float(peak.iloc[i])
            past_prices = prices.iloc[:i + 1]
            peak_dates = past_prices[past_prices == peak_val].index
            dd_start = peak_dates[-1] if len(peak_dates) > 0 else prices.index[max(0, i-1)]
            dd_peak_price = peak_val
            dd_trough = dd
            dd_trough_date = prices.index[i]

        elif in_drawdown:
            if dd < dd_trough:
                dd_trough = dd
                dd_trough_date = prices.index[i]

            if dd >= -0.5:  # Recovered (within 0.5% of peak)
                # End of drawdown — record it
                recovery_date = prices.index[i]
                peak_to_trough_days = (dd_trough_date - dd_start).days
                trough_to_recovery_days = (recovery_date - dd_trough_date).days
                total_days = (recovery_date - dd_start).days

                drawdowns.append({
                    "peak_date": dd_start.strftime("%Y-%m-%d"),
                    "trough_date": dd_trough_date.strftime("%Y-%m-%d"),
                    "recovery_date": recovery_date.strftime("%Y-%m-%d"),
                    "depth_pct": round(dd_trough, 2),
                    "peak_price": round(dd_peak_price, 2),
                    "trough_price": round(dd_peak_price * (1 + dd_trough / 100), 2),
                    "peak_to_trough_days": peak_to_trough_days,
                    "trough_to_recovery_days": trough_to_recovery_days,
                    "total_days": total_days,
                    "recovered": True,
                })

                in_drawdown = False
                dd_trough = 0.0

    # Handle ongoing drawdown
    current_dd = None
    if in_drawdown:
        current_dd = {
            "peak_date": dd_start.strftime("%Y-%m-%d"),
            "trough_date": dd_trough_date.strftime("%Y-%m-%d"),
            "depth_pct": round(dd_trough, 2),
            "peak_price": round(dd_peak_price, 2),
            "trough_price": round(dd_peak_price * (1 + dd_trough / 100), 2),
            "days_since_peak": (prices.index[-1] - dd_start).days,
            "days_since_trough": (prices.index[-1] - dd_trough_date).days,
            "recovered": False,
        }

    # Summary statistics
    if drawdowns:
        depths = [d["depth_pct"] for d in drawdowns]
        durations = [d["total_days"] for d in drawdowns]
        recoveries = [d["trough_to_recovery_days"] for d in drawdowns]
        summary = {
            "n_drawdowns": len(drawdowns),
            "avg_depth_pct": round(float(np.mean(depths)), 2),
            "max_depth_pct": round(float(min(depths)), 2),
            "avg_duration_days": round(float(np.mean(durations))),
            "max_duration_days": int(max(durations)),
            "avg_recovery_days": round(float(np.mean(recoveries))),
            "max_recovery_days": int(max(recoveries)),
            "worst_drawdown": min(drawdowns, key=lambda d: d["depth_pct"]),
            "longest_drawdown": max(drawdowns, key=lambda d: d["total_days"]),
        }
    else:
        summary = {"n_drawdowns": 0}

    return {
        "drawdowns": drawdowns,
        "current": current_dd,
        "summary": summary,
    }


def compute_rolling_returns(
    prices: pd.Series,
    windows: Optional[list[int]] = None,
) -> dict:
    """Compute rolling annualized returns over multiple windows.

    This answers "What return would I have gotten if I invested N years ago?"
    for every possible entry date in the history.

    Args:
        prices: Daily price series
        windows: Rolling windows in trading days (default: [252, 756, 1260] = 1Y, 3Y, 5Y)

    Returns:
        Dict with rolling return series and summary statistics per window.
    """
    if windows is None:
        windows = [252, 756, 1260]  # 1Y, 3Y, 5Y

    prices = prices.dropna()
    results = {}

    for window in windows:
        if len(prices) < window + 10:
            continue

        years = window / 252
        label = f"{years:.0f}Y" if years >= 1 else f"{window}d"

        # Rolling annualized return
        rolling_ret = (prices / prices.shift(window)) ** (1 / years) - 1
        rolling_ret = rolling_ret.dropna() * 100  # As percentage

        # Summary stats
        results[label] = {
            "window_days": window,
            "n_observations": len(rolling_ret),
            "current": round(float(rolling_ret.iloc[-1]), 2) if len(rolling_ret) > 0 else None,
            "mean": round(float(rolling_ret.mean()), 2),
            "median": round(float(rolling_ret.median()), 2),
            "min": round(float(rolling_ret.min()), 2),
            "max": round(float(rolling_ret.max()), 2),
            "std": round(float(rolling_ret.std()), 2),
            "pct_positive": round(float((rolling_ret > 0).mean()) * 100, 1),
            "percentiles": {
                "p5": round(float(np.percentile(rolling_ret, 5)), 2),
                "p25": round(float(np.percentile(rolling_ret, 25)), 2),
                "p75": round(float(np.percentile(rolling_ret, 75)), 2),
                "p95": round(float(np.percentile(rolling_ret, 95)), 2),
            },
            # Downsampled time series for charting (monthly)
            "series": [
                {
                    "date": rolling_ret.index[i].strftime("%Y-%m-%d"),
                    "return_pct": round(float(rolling_ret.iloc[i]), 2),
                }
                for i in range(0, len(rolling_ret), 21)  # Monthly samples
            ][-120:],  # Last 10 years of monthly data
        }

    return results


def compute_rolling_risk_metrics(
    prices: pd.Series,
    window: int = 252,
    risk_free_rate: Optional[float] = None,
) -> dict:
    """Compute rolling Sharpe ratio, Sortino ratio, and max drawdown.

    Args:
        prices: Daily price series
        window: Rolling window in trading days (default 252 = 1 year)
        risk_free_rate: Annual risk-free rate (default from config)

    Returns:
        Dict with rolling risk metric time series.
    """
    if risk_free_rate is None:
        risk_free_rate = config.get("risk_free_rate", 0.04)

    prices = prices.dropna()
    returns = prices.pct_change().dropna()

    if len(returns) < window + 10:
        return {}

    daily_rf = risk_free_rate / 252

    # Rolling Sharpe
    rolling_mean = returns.rolling(window).mean()
    rolling_std = returns.rolling(window).std()
    rolling_sharpe = ((rolling_mean - daily_rf) / rolling_std * np.sqrt(252)).dropna()

    # Rolling Sortino (correct: downside deviation = sqrt(mean(min(r-rf, 0)^2)))
    excess = returns - daily_rf
    downside = excess.copy()
    downside[downside > 0] = 0
    rolling_downside_var = (downside ** 2).rolling(window, min_periods=window).mean()
    rolling_downside_std = np.sqrt(rolling_downside_var)
    rolling_sortino = ((rolling_mean - daily_rf) / rolling_downside_std * np.sqrt(252)).dropna()

    # Rolling max drawdown
    def _rolling_max_dd(prices_window):
        peak = prices_window.cummax()
        dd = (prices_window / peak - 1)
        return float(dd.min()) * 100

    # Start at window-1 so the first window covers prices[0:window] (includes index 0).
    # Previous code started at range(window, ...) which produced prices[1:window+1],
    # skipping the first data point and misaligning with rolling Sharpe/Sortino.
    rolling_mdd = pd.Series(
        [_rolling_max_dd(prices.iloc[max(0, i - window + 1):i + 1]) for i in range(window - 1, len(prices))],
        index=prices.index[window - 1:],
    )

    # Downsample for charting
    def _downsample(series, name):
        clean = series.dropna()
        if len(clean) == 0:
            return []
        return [
            {"date": clean.index[i].strftime("%Y-%m-%d"), name: round(float(clean.iloc[i]), 3)}
            for i in range(0, len(clean), 21)
        ][-120:]

    return {
        "window_days": window,
        "sharpe": {
            "current": round(float(rolling_sharpe.iloc[-1]), 3) if len(rolling_sharpe) > 0 else None,
            "mean": round(float(rolling_sharpe.mean()), 3),
            "series": _downsample(rolling_sharpe, "sharpe"),
        },
        "sortino": {
            "current": round(float(rolling_sortino.iloc[-1]), 3) if len(rolling_sortino) > 0 else None,
            "mean": round(float(rolling_sortino.mean()), 3),
            "series": _downsample(rolling_sortino, "sortino"),
        },
        "max_drawdown": {
            "current": round(float(rolling_mdd.iloc[-1]), 2) if len(rolling_mdd) > 0 else None,
            "worst": round(float(rolling_mdd.min()), 2),
            "series": _downsample(rolling_mdd, "max_dd"),
        },
    }


def full_drawdown_analysis(
    ticker: str,
    period: str = "10y",
) -> Optional[dict]:
    """Complete drawdown and rolling return analysis for a stock.

    Args:
        ticker: Stock ticker symbol
        period: yfinance period string

    Returns:
        Full analysis dict or None if insufficient data.
    """
    try:
        from backend.services.data_fetcher import RateLimited, fetch_ticker_history
        try:
            hist = fetch_ticker_history(ticker, period=period)
        except RateLimited:
            logger.warning("%s: drawdown analysis skipped — Yahoo throttling", ticker)
            return None
        if hist is None or hist.empty or len(hist) < 252:
            return None

        prices = hist["Close"]
    except Exception as e:
        logger.warning("Failed to fetch %s for drawdown analysis: %s", ticker, e)
        return None

    drawdowns = analyze_drawdowns(prices)
    rolling = compute_rolling_returns(prices)
    risk = compute_rolling_risk_metrics(prices)

    return {
        "ticker": ticker,
        "period": period,
        "n_trading_days": len(prices),
        "start_date": prices.index[0].strftime("%Y-%m-%d"),
        "end_date": prices.index[-1].strftime("%Y-%m-%d"),
        "drawdowns": drawdowns,
        "rolling_returns": rolling,
        "rolling_risk": risk,
    }
