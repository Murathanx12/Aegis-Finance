"""
Aegis Finance — Signal Engine Backtesting Harness
====================================================

Tests whether the signal engine would have produced correct buy/sell calls
historically. Uses walk-forward approach: at each month, only data available
up to that date is used to generate signals.

Usage:
    from backend.services.backtest import backtest_signal_engine, evaluate_backtest
"""

import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def backtest_signal_engine(
    start_date: str = "2020-01-01",
    end_date: str = "2025-06-01",
    tickers: list[str] | None = None,
) -> pd.DataFrame:
    """Run walk-forward backtest of the signal engine.

    Steps through historical data month-by-month, computes signal using
    only data available up to that date, and records actual forward returns.

    Args:
        start_date: Backtest start (YYYY-MM-DD)
        end_date: Backtest end (YYYY-MM-DD)
        tickers: Tickers to test (default: ["SPY"])

    Returns:
        DataFrame with columns: date, signal_action, confidence, composite_score,
        forward_3m_return, forward_12m_return, reasons
    """
    import yfinance as yf
    from backend.services.signal_engine import get_market_signal

    if tickers is None:
        tickers = ["SPY"]

    # Download all data we need upfront (S&P 500 + VIX for the full period + forward window)
    buffer_end = (pd.Timestamp(end_date) + pd.DateOffset(months=14)).strftime("%Y-%m-%d")
    data_start = (pd.Timestamp(start_date) - pd.DateOffset(years=2)).strftime("%Y-%m-%d")

    logger.info("Downloading backtest data %s to %s", data_start, buffer_end)
    sp500 = yf.download("^GSPC", start=data_start, end=buffer_end, progress=False)["Close"]
    vix = yf.download("^VIX", start=data_start, end=buffer_end, progress=False)["Close"]

    if isinstance(sp500, pd.DataFrame):
        sp500 = sp500.squeeze()
    if isinstance(vix, pd.DataFrame):
        vix = vix.squeeze()

    if sp500.empty:
        raise ValueError("Could not download S&P 500 data")

    # Generate monthly evaluation dates
    eval_dates = pd.date_range(start=start_date, end=end_date, freq="MS")

    results = []
    for eval_date in eval_dates:
        # Find nearest trading day
        mask = sp500.index <= eval_date
        if mask.sum() < 63:
            continue
        actual_date = sp500.index[mask][-1]

        # Data available up to eval_date
        sp_slice = sp500.loc[:actual_date]
        vix_slice = vix.loc[:actual_date] if not vix.empty else pd.Series(dtype=float)

        # Compute inputs for signal engine
        current_vix = float(vix_slice.iloc[-1]) if len(vix_slice) > 0 else 20.0

        sp_1m = float(sp_slice.iloc[-1] / sp_slice.iloc[-22] - 1) * 100 if len(sp_slice) > 22 else 0.0
        sp_3m = float(sp_slice.iloc[-1] / sp_slice.iloc[-63] - 1) * 100 if len(sp_slice) > 63 else 0.0

        # Simple regime from returns
        sp_252d = float(sp_slice.iloc[-1] / sp_slice.iloc[-min(252, len(sp_slice)-1)] - 1) if len(sp_slice) > 1 else 0.0
        if sp_252d > 0.10:
            regime = "Bull"
        elif sp_252d < -0.10:
            regime = "Bear"
        elif current_vix > 25:
            regime = "Volatile"
        else:
            regime = "Neutral"

        # Short-window regime override (matching our fix)
        if regime == "Bull":
            if sp_1m / 100 < -0.05 or sp_3m / 100 < -0.08:
                regime = "Neutral"

        try:
            signal = get_market_signal(
                regime=regime,
                risk_score=current_vix / 30,  # rough proxy
                sp500_1m_return=sp_1m,
                sp500_3m_return=sp_3m,
                vix=current_vix,
            )
        except Exception as e:
            logger.warning("Signal failed for %s: %s", eval_date, e)
            continue

        # Forward returns
        forward_3m_date = actual_date + pd.DateOffset(months=3)
        forward_12m_date = actual_date + pd.DateOffset(months=12)

        fwd_3m_mask = sp500.index >= forward_3m_date
        fwd_12m_mask = sp500.index >= forward_12m_date

        fwd_3m_return = None
        if fwd_3m_mask.any():
            fwd_3m_price = float(sp500.loc[sp500.index[fwd_3m_mask][0]])
            fwd_3m_return = (fwd_3m_price / float(sp_slice.iloc[-1]) - 1) * 100

        fwd_12m_return = None
        if fwd_12m_mask.any():
            fwd_12m_price = float(sp500.loc[sp500.index[fwd_12m_mask][0]])
            fwd_12m_return = (fwd_12m_price / float(sp_slice.iloc[-1]) - 1) * 100

        results.append({
            "date": actual_date.strftime("%Y-%m-%d"),
            "signal_action": signal["action"],
            "confidence": signal["confidence"],
            "composite_score": signal["composite_score"],
            "vix": current_vix,
            "sp500_1m": round(sp_1m, 2),
            "sp500_3m": round(sp_3m, 2),
            "regime": regime,
            "forward_3m_return": round(fwd_3m_return, 2) if fwd_3m_return is not None else None,
            "forward_12m_return": round(fwd_12m_return, 2) if fwd_12m_return is not None else None,
            "reasons": signal["reasons"],
        })

    return pd.DataFrame(results)


def evaluate_backtest(df: pd.DataFrame) -> dict:
    """Evaluate backtest results with hit rates, returns, and Sharpe comparison.

    Args:
        df: DataFrame from backtest_signal_engine()

    Returns:
        Dict with hit rates, average returns, Sharpe ratios, period analysis
    """
    df = df.dropna(subset=["forward_3m_return"])

    if df.empty:
        return {"error": "No data with forward returns available"}

    # Categorize signals
    bullish = df[df["signal_action"].isin(["Strong Buy", "Buy"])]
    bearish = df[df["signal_action"].isin(["Strong Sell", "Sell"])]
    hold = df[df["signal_action"] == "Hold"]

    # Hit rates
    buy_hit_rate = float((bullish["forward_3m_return"] > 0).mean() * 100) if len(bullish) > 0 else None
    sell_hit_rate = float((bearish["forward_3m_return"] < 0).mean() * 100) if len(bearish) > 0 else None

    # Average returns by signal type
    buy_avg_3m = float(bullish["forward_3m_return"].mean()) if len(bullish) > 0 else None
    sell_avg_3m = float(bearish["forward_3m_return"].mean()) if len(bearish) > 0 else None
    hold_avg_3m = float(hold["forward_3m_return"].mean()) if len(hold) > 0 else None
    overall_avg_3m = float(df["forward_3m_return"].mean())

    # Signal-following strategy vs buy-and-hold
    # Strategy: invest when Buy/Strong Buy, cash when Sell/Strong Sell, 50% when Hold
    strategy_returns = []
    bh_returns = []
    for _, row in df.iterrows():
        fwd = row["forward_3m_return"] / 100
        if row["signal_action"] in ("Strong Buy", "Buy"):
            strategy_returns.append(fwd)
        elif row["signal_action"] in ("Strong Sell", "Sell"):
            strategy_returns.append(0.0)  # cash
        else:
            strategy_returns.append(fwd * 0.5)  # half exposure
        bh_returns.append(fwd)

    strategy_arr = np.array(strategy_returns)
    bh_arr = np.array(bh_returns)

    strategy_sharpe = float(np.mean(strategy_arr) / max(np.std(strategy_arr), 1e-8) * np.sqrt(4))
    bh_sharpe = float(np.mean(bh_arr) / max(np.std(bh_arr), 1e-8) * np.sqrt(4))

    strategy_total = float((1 + strategy_arr).prod() - 1) * 100
    bh_total = float((1 + bh_arr).prod() - 1) * 100

    # Period analysis — identify which periods failed
    period_analysis = []
    for _, row in df.iterrows():
        if row["forward_3m_return"] is not None:
            correct = (
                (row["signal_action"] in ("Buy", "Strong Buy") and row["forward_3m_return"] > 0) or
                (row["signal_action"] in ("Sell", "Strong Sell") and row["forward_3m_return"] < 0) or
                (row["signal_action"] == "Hold" and abs(row["forward_3m_return"]) < 10)
            )
            if not correct:
                period_analysis.append({
                    "date": row["date"],
                    "signal": row["signal_action"],
                    "forward_3m": row["forward_3m_return"],
                    "vix": row["vix"],
                    "regime": row["regime"],
                })

    return {
        "total_signals": len(df),
        "buy_signals": len(bullish),
        "sell_signals": len(bearish),
        "hold_signals": len(hold),
        "buy_hit_rate_3m": round(buy_hit_rate, 1) if buy_hit_rate is not None else None,
        "sell_hit_rate_3m": round(sell_hit_rate, 1) if sell_hit_rate is not None else None,
        "avg_return_on_buy_3m": round(buy_avg_3m, 2) if buy_avg_3m is not None else None,
        "avg_return_on_sell_3m": round(sell_avg_3m, 2) if sell_avg_3m is not None else None,
        "avg_return_on_hold_3m": round(hold_avg_3m, 2) if hold_avg_3m is not None else None,
        "overall_avg_3m": round(overall_avg_3m, 2),
        "strategy_total_return": round(strategy_total, 2),
        "buy_hold_total_return": round(bh_total, 2),
        "strategy_sharpe": round(strategy_sharpe, 3),
        "buy_hold_sharpe": round(bh_sharpe, 3),
        "missed_calls": period_analysis[:10],
        "signals_by_action": {
            action: len(df[df["signal_action"] == action])
            for action in ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"]
        },
    }
