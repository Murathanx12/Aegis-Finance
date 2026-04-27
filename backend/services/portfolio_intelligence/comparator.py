"""
Aegis Finance — Portfolio Comparator
======================================

Computes standardized MetricPack for multiple portfolios over a consistent
date window. Handles date alignment so all portfolios are measured over
exactly the same period.

Usage:
    from backend.services.portfolio_intelligence.comparator import (
        compute_comparison,
    )
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from backend.config import config
from backend.schemas.portfolio_intelligence import (
    ComparisonResponse,
    MetricPack,
)

logger = logging.getLogger(__name__)

_PERIOD_DAYS = {
    "1M": 21,
    "3M": 63,
    "6M": 126,
    "1Y": 252,
    "3Y": 756,
    "ALL": 5000,
}


def _resolve_period(period: str) -> int:
    """Convert period string to trading days. YTD computed dynamically."""
    if period == "YTD":
        now = datetime.now()
        start_of_year = datetime(now.year, 1, 1)
        cal_days = (now - start_of_year).days
        return max(int(cal_days * 252 / 365), 5)
    return _PERIOD_DAYS.get(period, 252)


def _fetch_benchmark_returns(
    ticker: str,
    trading_days: int,
) -> Optional[pd.Series]:
    """Fetch daily returns for a benchmark ticker."""
    try:
        import yfinance as yf
        end = datetime.now()
        start = end - timedelta(days=int(trading_days * 2))
        hist = yf.download(
            ticker,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True,
        )
        if hist.empty:
            return None
        close = hist["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        returns = close.pct_change().dropna()
        if len(returns) > trading_days:
            returns = returns.iloc[-trading_days:]
        return returns
    except Exception as e:
        logger.warning("Failed to fetch benchmark %s: %s", ticker, e)
        return None


def _build_6040_returns(
    spy_returns: pd.Series,
    agg_returns: pd.Series,
) -> pd.Series:
    """Construct 60/40 blended benchmark from SPY and AGG returns."""
    aligned = pd.DataFrame({"spy": spy_returns, "agg": agg_returns}).dropna()
    if aligned.empty:
        return pd.Series(dtype=float)
    return aligned["spy"] * 0.60 + aligned["agg"] * 0.40


def _returns_to_metric_pack(
    daily_returns: pd.Series,
    spy_returns: pd.Series | None = None,
) -> MetricPack:
    """Convert a daily return series into a standardized MetricPack."""
    rf = config.get("risk_free_rate", 0.04)
    returns = daily_returns.dropna()

    if len(returns) < 5:
        return MetricPack(
            total_return=0.0,
            annualized_return=0.0,
            annualized_volatility=0.0,
            max_drawdown=0.0,
        )

    total_return = float((1 + returns).prod() - 1)
    n_years = len(returns) / 252.0
    ann_return = float((1 + total_return) ** (1 / n_years) - 1) if n_years > 0 else 0.0
    ann_vol = float(returns.std() * np.sqrt(252))
    sharpe = float((ann_return - rf) / ann_vol) if ann_vol > 1e-10 else None

    # Max drawdown
    cum = (1 + returns).cumprod()
    peak = cum.cummax()
    dd = (cum / peak - 1)
    max_dd = float(dd.min())

    dd_duration = None
    in_dd = dd < 0
    if in_dd.any():
        groups = (~in_dd).cumsum()
        dd_lengths = in_dd.groupby(groups).sum()
        dd_duration = int(dd_lengths.max()) if len(dd_lengths) > 0 else None

    # Sortino
    sortino = None
    downside = returns[returns < 0]
    if len(downside) > 5:
        downside_std = float(downside.std() * np.sqrt(252))
        if downside_std > 1e-10:
            sortino = round(float((ann_return - rf) / downside_std), 4)

    # Beta / tracking vs SPY
    beta = None
    te = None
    ir = None
    if spy_returns is not None:
        aligned = pd.DataFrame({"port": returns, "spy": spy_returns}).dropna()
        if len(aligned) >= 60:
            p = aligned["port"].values
            s = aligned["spy"].values
            cov = np.cov(p, s)
            if cov[1, 1] > 1e-12:
                beta = round(float(cov[0, 1] / cov[1, 1]), 4)
            active = p - s
            te_val = float(np.std(active) * np.sqrt(252))
            te = round(te_val, 4)
            if te_val > 1e-10:
                ir = round(float(np.mean(active) * 252 / te_val), 4)

    return MetricPack(
        total_return=round(total_return, 6),
        annualized_return=round(ann_return, 6),
        annualized_volatility=round(ann_vol, 6),
        sharpe_ratio=round(sharpe, 4) if sharpe is not None else None,
        sortino_ratio=sortino,
        max_drawdown=round(max_dd, 6),
        max_drawdown_duration_days=dd_duration,
        beta_vs_spy=beta,
        tracking_error_vs_spy=te,
        information_ratio_vs_spy=ir,
    )


def compute_comparison(
    portfolio_returns: dict[str, pd.Series],
    benchmark_tickers: list[str],
    period: str = "1Y",
) -> ComparisonResponse:
    """Compute side-by-side MetricPack for portfolios and benchmarks.

    Args:
        portfolio_returns: {lane_id: daily_returns_series} for each portfolio
        benchmark_tickers: List of benchmark tickers (e.g., ["SPY", "AGG", "60-40"])
        period: Time period string ("1M", "3M", "6M", "YTD", "1Y", "3Y", "ALL")

    Returns:
        ComparisonResponse with standardized metrics for all lanes and benchmarks.
    """
    trading_days = _resolve_period(period)

    # Fetch benchmark returns
    spy_returns = _fetch_benchmark_returns("SPY", trading_days)
    agg_returns = _fetch_benchmark_returns("AGG", trading_days)

    benchmark_returns: dict[str, pd.Series] = {}
    for ticker in benchmark_tickers:
        if ticker == "60-40":
            if spy_returns is not None and agg_returns is not None:
                benchmark_returns["60-40"] = _build_6040_returns(spy_returns, agg_returns)
        else:
            ret = _fetch_benchmark_returns(ticker, trading_days)
            if ret is not None:
                benchmark_returns[ticker] = ret

    # Trim portfolio returns to period
    trimmed_portfolios: dict[str, pd.Series] = {}
    for lane_id, returns in portfolio_returns.items():
        if len(returns) > trading_days:
            trimmed_portfolios[lane_id] = returns.iloc[-trading_days:]
        else:
            trimmed_portfolios[lane_id] = returns

    # Compute metrics
    lane_metrics: dict[str, MetricPack] = {}
    for lane_id, returns in trimmed_portfolios.items():
        lane_metrics[lane_id] = _returns_to_metric_pack(returns, spy_returns)

    bench_metrics: dict[str, MetricPack] = {}
    for ticker, returns in benchmark_returns.items():
        bench_metrics[ticker] = _returns_to_metric_pack(returns, spy_returns)

    return ComparisonResponse(
        lanes=lane_metrics,
        benchmarks=bench_metrics,
        period=period,
    )
