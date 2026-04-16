"""
Aegis Finance — Portfolio Benchmark Analytics
================================================

Bloomberg PORT-style benchmark-relative analytics:

1. Tracking Error: Annualized std dev of active returns (portfolio - benchmark)
2. Information Ratio: Active return / tracking error (skill measure)
3. Active Share: % of portfolio that differs from benchmark (Cremers & Petajisto, 2009)
4. Up/Down Capture Ratios: Performance in rising vs falling markets
5. Rolling Tracking Error: Time-varying tracking error for regime detection
6. Beta & R-Squared vs Benchmark: Systematic risk decomposition
7. Style Drift Score: How much the portfolio's factor profile has changed

References:
  - Cremers & Petajisto (2009), "How Active Is Your Fund Manager?"
  - Grinold & Kahn (2000), "Active Portfolio Management"
  - Bailey & Lopez de Prado (2012), "The Sharpe Ratio Efficient Frontier"

Usage:
    from backend.services.benchmark_analytics import compute_benchmark_analytics
    result = compute_benchmark_analytics(weights, benchmark="SPY", lookback_days=504)
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

from backend.config import config

logger = logging.getLogger(__name__)

_cfg = config.get("benchmark_analytics", {})
_DEFAULT_BENCHMARK = _cfg.get("default_benchmark", "SPY")
_DEFAULT_LOOKBACK = _cfg.get("default_lookback_days", 504)
_ROLLING_WINDOW = _cfg.get("rolling_te_window", 63)
_ANNUALIZATION_FACTOR = _cfg.get("annualization_factor", 252)


def compute_benchmark_analytics(
    weights: dict[str, float],
    benchmark: str = _DEFAULT_BENCHMARK,
    lookback_days: int = _DEFAULT_LOOKBACK,
) -> Optional[dict]:
    """Compute full benchmark-relative analytics for a portfolio.

    Args:
        weights: {ticker: weight} dict, weights should sum to ~1.0
        benchmark: Benchmark ticker (default SPY)
        lookback_days: Days of history to analyze

    Returns:
        Dict with tracking_error, information_ratio, active_share,
        capture_ratios, rolling_te, and style_analysis.
    """
    if not weights or sum(weights.values()) < 0.01:
        return None

    tickers = list(weights.keys())
    all_tickers = list(set(tickers + [benchmark]))

    # Fetch price data
    period = f"{max(lookback_days // 252, 2)}y"
    try:
        data = yf.download(all_tickers, period=period, progress=False)
    except Exception as e:
        logger.error("benchmark_analytics download failed: %s", e)
        return None

    if data is None or data.empty:
        return None

    # Extract close prices
    if len(all_tickers) == 1:
        close = data["Close"].to_frame(all_tickers[0])
    else:
        close = data["Close"]

    if close is None or len(close) < 60:
        return None

    # Compute daily returns
    returns = close.pct_change().dropna()

    # Ensure benchmark exists
    if benchmark not in returns.columns:
        logger.warning("Benchmark %s not found in data", benchmark)
        return None

    bench_returns = returns[benchmark]

    # Build portfolio return series
    port_returns = _build_portfolio_returns(returns, weights)
    if port_returns is None or len(port_returns) < 30:
        return None

    # Align series
    aligned = pd.DataFrame({
        "portfolio": port_returns,
        "benchmark": bench_returns,
    }).dropna()

    if len(aligned) < 30:
        return None

    port_ret = aligned["portfolio"]
    bench_ret = aligned["benchmark"]
    active_ret = port_ret - bench_ret

    # 1. Tracking Error
    te_daily = float(active_ret.std())
    tracking_error = float(te_daily * np.sqrt(_ANNUALIZATION_FACTOR))

    # 2. Information Ratio
    active_return_annual = float(active_ret.mean() * _ANNUALIZATION_FACTOR)
    information_ratio = (
        float(active_return_annual / tracking_error)
        if tracking_error > 1e-8
        else 0.0
    )

    # 3. Active Share
    active_share = _compute_active_share(weights, benchmark)

    # 4. Up/Down Capture Ratios
    capture = _compute_capture_ratios(port_ret, bench_ret)

    # 5. Rolling Tracking Error
    rolling_te = _compute_rolling_tracking_error(
        active_ret, window=_ROLLING_WINDOW,
    )

    # 6. Beta & R-squared vs benchmark
    regression = _compute_regression_stats(port_ret, bench_ret)

    # 7. Return comparison (various periods)
    period_returns = _compute_period_returns(port_ret, bench_ret)

    # 8. Risk-adjusted comparison
    risk_comparison = _compute_risk_comparison(port_ret, bench_ret)

    # 9. Interpretations
    interpretation = _interpret_results(
        tracking_error, information_ratio, active_share, capture,
    )

    return {
        "benchmark": benchmark,
        "lookback_days": len(aligned),
        "tracking_error": round(tracking_error, 4),
        "tracking_error_pct": round(tracking_error * 100, 2),
        "information_ratio": round(information_ratio, 4),
        "active_return_annual_pct": round(active_return_annual * 100, 2),
        "active_share": active_share,
        "capture_ratios": capture,
        "rolling_tracking_error": rolling_te,
        "regression": regression,
        "period_returns": period_returns,
        "risk_comparison": risk_comparison,
        "interpretation": interpretation,
    }


def _build_portfolio_returns(
    returns: pd.DataFrame, weights: dict[str, float],
) -> Optional[pd.Series]:
    """Build weighted portfolio return series."""
    available = [t for t in weights if t in returns.columns]
    if not available:
        return None

    # Re-normalize weights to available tickers
    total_w = sum(weights[t] for t in available)
    if total_w < 0.01:
        return None

    w_arr = np.array([weights[t] / total_w for t in available])
    port_returns = (returns[available] * w_arr).sum(axis=1)
    return port_returns


def _compute_active_share(
    weights: dict[str, float], benchmark: str,
) -> Optional[dict]:
    """Compute Active Share (Cremers & Petajisto, 2009).

    Active Share = 0.5 * Σ|w_p,i - w_b,i|

    For individual stocks vs SPY, we approximate SPY weights using
    market-cap-weighted composition. Since exact SPY weights require
    a premium data feed, we use yfinance market caps as proxy.
    """
    try:
        # Get benchmark holdings weights (approximate from market caps)
        bench_weights = _get_approximate_benchmark_weights(benchmark, list(weights.keys()))

        if not bench_weights:
            return None

        # Compute active share
        all_tickers = set(list(weights.keys()) + list(bench_weights.keys()))
        total_diff = 0.0
        details = []

        for ticker in all_tickers:
            w_port = weights.get(ticker, 0.0)
            w_bench = bench_weights.get(ticker, 0.0)
            diff = abs(w_port - w_bench)
            total_diff += diff

            if w_port > 0 or w_bench > 0.001:
                details.append({
                    "ticker": ticker,
                    "portfolio_weight": round(w_port * 100, 2),
                    "benchmark_weight": round(w_bench * 100, 2),
                    "active_weight": round((w_port - w_bench) * 100, 2),
                })

        active_share_pct = round(min(total_diff / 2 * 100, 100.0), 1)

        # Sort by absolute active weight
        details.sort(key=lambda x: abs(x["active_weight"]), reverse=True)

        # Interpretation
        if active_share_pct >= 80:
            label = "Stock Picker"
            description = "Highly active — portfolio is very different from benchmark"
        elif active_share_pct >= 60:
            label = "Active"
            description = "Meaningfully different from benchmark — genuine active bets"
        elif active_share_pct >= 40:
            label = "Moderately Active"
            description = "Some active positions but significant benchmark overlap"
        elif active_share_pct >= 20:
            label = "Closet Indexer"
            description = "Portfolio closely tracks benchmark — limited active risk"
        else:
            label = "Index Fund"
            description = "Nearly identical to benchmark"

        return {
            "active_share_pct": active_share_pct,
            "label": label,
            "description": description,
            "top_active_positions": details[:10],
        }
    except Exception as e:
        logger.debug("active share computation failed: %s", e)
        return None


def _get_approximate_benchmark_weights(
    benchmark: str, portfolio_tickers: list[str],
) -> dict[str, float]:
    """Approximate benchmark weights for active share calculation.

    For SPY/S&P500: uses market caps of portfolio tickers relative to
    the total S&P 500 market cap to approximate their benchmark weight.
    """
    try:
        # Get market caps for portfolio tickers
        mcaps = {}
        for ticker in portfolio_tickers:
            try:
                info = yf.Ticker(ticker).info or {}
                mc = info.get("marketCap")
                if mc and mc > 0:
                    mcaps[ticker] = float(mc)
            except Exception:
                pass

        if not mcaps:
            return {}

        # For SPY: approximate total S&P 500 market cap
        # ~$50T as of 2026 (approximate)
        sp500_total_mcap = _cfg.get("sp500_approximate_mcap", 50_000_000_000_000)

        bench_weights = {}
        for ticker, mc in mcaps.items():
            bench_weights[ticker] = mc / sp500_total_mcap

        return bench_weights
    except Exception as e:
        logger.debug("benchmark weight approximation failed: %s", e)
        return {}


def _compute_capture_ratios(
    port_ret: pd.Series, bench_ret: pd.Series,
) -> dict:
    """Compute up-capture and down-capture ratios.

    Up Capture = (geometric portfolio return in up months) / (geometric benchmark return in up months)
    Down Capture = (geometric portfolio return in down months) / (geometric benchmark return in down months)

    Uses monthly returns for more stable estimates.
    """
    # Resample to monthly returns
    combined = pd.DataFrame({"port": port_ret, "bench": bench_ret})
    monthly = (1 + combined).resample("ME").prod() - 1

    if len(monthly) < 6:
        return {
            "up_capture": None,
            "down_capture": None,
            "capture_ratio": None,
            "up_months": 0,
            "down_months": 0,
        }

    up_months = monthly[monthly["bench"] > 0]
    down_months = monthly[monthly["bench"] < 0]

    # Up capture
    up_capture = None
    if len(up_months) >= 3:
        port_up_geo = float((1 + up_months["port"]).prod() ** (1 / len(up_months)) - 1)
        bench_up_geo = float((1 + up_months["bench"]).prod() ** (1 / len(up_months)) - 1)
        if abs(bench_up_geo) > 1e-8:
            up_capture = round(port_up_geo / bench_up_geo * 100, 1)

    # Down capture
    down_capture = None
    if len(down_months) >= 3:
        port_down_geo = float((1 + down_months["port"]).prod() ** (1 / len(down_months)) - 1)
        bench_down_geo = float((1 + down_months["bench"]).prod() ** (1 / len(down_months)) - 1)
        if abs(bench_down_geo) > 1e-8:
            down_capture = round(port_down_geo / bench_down_geo * 100, 1)

    # Capture ratio = up_capture / down_capture (higher is better)
    capture_ratio = None
    if up_capture is not None and down_capture is not None and abs(down_capture) > 1e-8:
        capture_ratio = round(up_capture / down_capture, 2)

    # Interpretation
    interpretation = None
    if up_capture is not None and down_capture is not None:
        if up_capture > 100 and down_capture < 100:
            interpretation = "Excellent: captures more upside and less downside than benchmark"
        elif up_capture > 100 and down_capture > 100:
            interpretation = "Aggressive: captures more of both up and down moves"
        elif up_capture < 100 and down_capture < 100:
            interpretation = "Defensive: captures less of both up and down moves"
        elif up_capture < 100 and down_capture > 100:
            interpretation = "Poor: captures less upside but more downside"

    return {
        "up_capture": up_capture,
        "down_capture": down_capture,
        "capture_ratio": capture_ratio,
        "up_months": len(up_months),
        "down_months": len(down_months),
        "interpretation": interpretation,
    }


def _compute_rolling_tracking_error(
    active_ret: pd.Series, window: int = 63,
) -> dict:
    """Compute rolling annualized tracking error.

    Returns current, min, max, and trend direction.
    """
    if len(active_ret) < window + 10:
        return {"available": False}

    rolling_te = active_ret.rolling(window).std() * np.sqrt(_ANNUALIZATION_FACTOR)
    rolling_te = rolling_te.dropna()

    if len(rolling_te) < 2:
        return {"available": False}

    current = float(rolling_te.iloc[-1])
    avg = float(rolling_te.mean())
    min_te = float(rolling_te.min())
    max_te = float(rolling_te.max())

    # Trend: compare last quarter to prior quarter
    if len(rolling_te) >= 126:
        recent_avg = float(rolling_te.iloc[-63:].mean())
        prior_avg = float(rolling_te.iloc[-126:-63].mean())
        if recent_avg > prior_avg * 1.1:
            trend = "increasing"
        elif recent_avg < prior_avg * 0.9:
            trend = "decreasing"
        else:
            trend = "stable"
    else:
        trend = "insufficient_data"

    # Recent time series (last 12 months, weekly samples)
    ts_data = []
    weekly = rolling_te.resample("W").last().dropna()
    for date, val in weekly.tail(52).items():
        ts_data.append({
            "date": date.strftime("%Y-%m-%d"),
            "tracking_error_pct": round(float(val) * 100, 2),
        })

    return {
        "available": True,
        "current_pct": round(current * 100, 2),
        "average_pct": round(avg * 100, 2),
        "min_pct": round(min_te * 100, 2),
        "max_pct": round(max_te * 100, 2),
        "trend": trend,
        "window_days": window,
        "time_series": ts_data,
    }


def _compute_regression_stats(
    port_ret: pd.Series, bench_ret: pd.Series,
) -> dict:
    """Compute beta, alpha, R-squared vs benchmark using OLS."""
    # Simple OLS: port = alpha + beta * bench + epsilon
    x = bench_ret.values
    y = port_ret.values

    n = len(x)
    if n < 30:
        return {"available": False}

    x_mean = np.mean(x)
    y_mean = np.mean(y)

    cov_xy = np.sum((x - x_mean) * (y - y_mean)) / (n - 1)
    var_x = np.sum((x - x_mean) ** 2) / (n - 1)

    if var_x < 1e-12:
        return {"available": False}

    beta = float(cov_xy / var_x)
    alpha_daily = float(y_mean - beta * x_mean)
    alpha_annual = float(alpha_daily * _ANNUALIZATION_FACTOR)

    # R-squared
    y_pred = alpha_daily + beta * x
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y_mean) ** 2)
    r_squared = float(1 - ss_res / ss_tot) if ss_tot > 1e-12 else 0.0
    r_squared = max(0.0, min(1.0, r_squared))

    # Residual volatility (idiosyncratic risk)
    residuals = y - y_pred
    residual_vol = float(np.std(residuals, ddof=1) * np.sqrt(_ANNUALIZATION_FACTOR))

    # Interpretation
    if r_squared > 0.95:
        r2_label = "Very high — portfolio closely tracks benchmark"
    elif r_squared > 0.85:
        r2_label = "High — mostly systematic risk"
    elif r_squared > 0.70:
        r2_label = "Moderate — meaningful idiosyncratic risk"
    else:
        r2_label = "Low — portfolio behaves differently from benchmark"

    return {
        "available": True,
        "beta": round(beta, 4),
        "alpha_annual_pct": round(alpha_annual * 100, 2),
        "r_squared": round(r_squared, 4),
        "residual_vol_pct": round(residual_vol * 100, 2),
        "r_squared_interpretation": r2_label,
    }


def _compute_period_returns(
    port_ret: pd.Series, bench_ret: pd.Series,
) -> dict:
    """Compute portfolio vs benchmark returns for standard periods."""
    results = {}

    periods = {
        "1m": 21,
        "3m": 63,
        "6m": 126,
        "1y": 252,
        "ytd": None,  # Special handling
    }

    for label, days in periods.items():
        if label == "ytd":
            # YTD: from start of current year
            current_year = port_ret.index[-1].year
            ytd_mask = port_ret.index.year == current_year
            p = port_ret[ytd_mask]
            b = bench_ret[ytd_mask]
            if len(p) < 5:
                continue
        else:
            if len(port_ret) < days:
                continue
            p = port_ret.iloc[-days:]
            b = bench_ret.iloc[-days:]

        port_cum = float((1 + p).prod() - 1)
        bench_cum = float((1 + b).prod() - 1)
        active = port_cum - bench_cum

        results[label] = {
            "portfolio_pct": round(port_cum * 100, 2),
            "benchmark_pct": round(bench_cum * 100, 2),
            "active_return_pct": round(active * 100, 2),
            "outperformed": active > 0,
        }

    return results


def _compute_risk_comparison(
    port_ret: pd.Series, bench_ret: pd.Series,
) -> dict:
    """Compare risk metrics between portfolio and benchmark."""
    ann = _ANNUALIZATION_FACTOR

    port_vol = float(port_ret.std() * np.sqrt(ann))
    bench_vol = float(bench_ret.std() * np.sqrt(ann))

    port_annual = float(port_ret.mean() * ann)
    bench_annual = float(bench_ret.mean() * ann)

    # Sharpe (assume 4.5% risk-free for 2026)
    rf = _cfg.get("risk_free_rate", 0.045)
    port_sharpe = float((port_annual - rf) / port_vol) if port_vol > 1e-8 else 0.0
    bench_sharpe = float((bench_annual - rf) / bench_vol) if bench_vol > 1e-8 else 0.0

    # Sortino
    port_downside = float(port_ret[port_ret < 0].std() * np.sqrt(ann)) if (port_ret < 0).any() else 0.0
    bench_downside = float(bench_ret[bench_ret < 0].std() * np.sqrt(ann)) if (bench_ret < 0).any() else 0.0

    port_sortino = float((port_annual - rf) / port_downside) if port_downside > 1e-8 else 0.0
    bench_sortino = float((bench_annual - rf) / bench_downside) if bench_downside > 1e-8 else 0.0

    # Max drawdown
    port_cumulative = (1 + port_ret).cumprod()
    bench_cumulative = (1 + bench_ret).cumprod()

    port_dd = float((port_cumulative / port_cumulative.cummax() - 1).min())
    bench_dd = float((bench_cumulative / bench_cumulative.cummax() - 1).min())

    return {
        "portfolio": {
            "annual_return_pct": round(port_annual * 100, 2),
            "volatility_pct": round(port_vol * 100, 2),
            "sharpe": round(port_sharpe, 3),
            "sortino": round(port_sortino, 3),
            "max_drawdown_pct": round(port_dd * 100, 2),
        },
        "benchmark": {
            "annual_return_pct": round(bench_annual * 100, 2),
            "volatility_pct": round(bench_vol * 100, 2),
            "sharpe": round(bench_sharpe, 3),
            "sortino": round(bench_sortino, 3),
            "max_drawdown_pct": round(bench_dd * 100, 2),
        },
    }


def _interpret_results(
    tracking_error: float,
    information_ratio: float,
    active_share: Optional[dict],
    capture: dict,
) -> dict:
    """Generate Bloomberg-style interpretation of benchmark analytics."""
    insights = []

    # Tracking error interpretation
    te_pct = tracking_error * 100
    if te_pct < 2:
        te_label = "Low"
        insights.append("Portfolio closely tracks benchmark — low active risk")
    elif te_pct < 5:
        te_label = "Moderate"
        insights.append("Moderate tracking error — balanced active management")
    elif te_pct < 10:
        te_label = "High"
        insights.append("High tracking error — significant active bets vs benchmark")
    else:
        te_label = "Very High"
        insights.append("Very high tracking error — portfolio behaves very differently from benchmark")

    # Information ratio interpretation (Grinold & Kahn benchmark: 0.5 = good, 1.0 = exceptional)
    if information_ratio > 1.0:
        ir_label = "Exceptional"
        insights.append("Exceptional information ratio — rare skill in active management")
    elif information_ratio > 0.5:
        ir_label = "Good"
        insights.append("Good information ratio — active bets are generating positive risk-adjusted alpha")
    elif information_ratio > 0.0:
        ir_label = "Positive"
        insights.append("Positive but modest information ratio — some alpha, room for improvement")
    elif information_ratio > -0.5:
        ir_label = "Negative"
        insights.append("Negative information ratio — active bets are destroying value vs indexing")
    else:
        ir_label = "Poor"
        insights.append("Significantly negative IR — strong case for switching to index fund")

    # Active share + TE quadrant (Cremers & Petajisto classification)
    classification = None
    if active_share and active_share.get("active_share_pct") is not None:
        as_pct = active_share["active_share_pct"]
        if as_pct >= 60 and te_pct >= 5:
            classification = "Concentrated Stock Picker"
        elif as_pct >= 60 and te_pct < 5:
            classification = "Diversified Stock Picker"
        elif as_pct < 60 and te_pct >= 5:
            classification = "Factor Bet / Sector Tilter"
        else:
            classification = "Closet Indexer"

    # Capture ratio insight
    up_cap = capture.get("up_capture")
    down_cap = capture.get("down_capture")
    if up_cap is not None and down_cap is not None:
        if up_cap > 105 and down_cap < 95:
            insights.append("Asymmetric capture profile — outperforms in both directions")
        elif down_cap > 110:
            insights.append("Warning: high downside capture — portfolio amplifies losses")

    return {
        "tracking_error_label": te_label,
        "information_ratio_label": ir_label,
        "management_style": classification,
        "insights": insights,
    }
