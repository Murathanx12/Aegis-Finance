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

import numpy as np
import pandas as pd

from backend.config import config

logger = logging.getLogger(__name__)

# Execution cost config
EXEC_CFG = config.get("execution_costs", {})
SLIPPAGE_BPS = EXEC_CFG.get("slippage_bps", 5)     # 5 bps one-way slippage
COMMISSION_BPS = EXEC_CFG.get("commission_bps", 1)  # 1 bp commission
MARKET_IMPACT_FACTOR = EXEC_CFG.get("market_impact_factor", 0.1)  # Square-root model coefficient


def estimate_execution_cost(
    trade_value: float = 100000.0,
    avg_daily_volume_usd: float = 1e9,
    is_round_trip: bool = True,
) -> dict:
    """Estimate execution cost for a trade using the square-root market impact model.

    Components:
    1. Fixed slippage (bid-ask spread proxy)
    2. Commission
    3. Market impact: η * σ * sqrt(Q/V) where Q=trade size, V=ADV

    Args:
        trade_value: Dollar amount of the trade.
        avg_daily_volume_usd: Average daily dollar volume of the asset.
        is_round_trip: If True, double the cost (entry + exit).

    Returns:
        dict with slippage_bps, commission_bps, market_impact_bps, total_bps, total_pct.
    """
    # Market impact via square-root model (Almgren-Chriss simplified)
    participation_rate = trade_value / max(avg_daily_volume_usd, 1e6)
    impact_bps = MARKET_IMPACT_FACTOR * np.sqrt(participation_rate) * 10000

    one_way_bps = SLIPPAGE_BPS + COMMISSION_BPS + impact_bps
    total_bps = one_way_bps * (2 if is_round_trip else 1)

    return {
        "slippage_bps": SLIPPAGE_BPS * (2 if is_round_trip else 1),
        "commission_bps": COMMISSION_BPS * (2 if is_round_trip else 1),
        "market_impact_bps": round(impact_bps * (2 if is_round_trip else 1), 2),
        "total_bps": round(total_bps, 2),
        "total_pct": round(total_bps / 100, 4),
    }


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
    # Track with and without execution costs
    #
    # IMPORTANT: Forward returns are 3-month windows evaluated monthly, so they
    # overlap. We collect ALL monthly observations for hit-rate / avg-return stats,
    # but use only non-overlapping quarterly observations (every 3rd row) for
    # total-return compounding and Sharpe ratios to avoid double-counting.
    strategy_returns_gross = []
    strategy_returns_net = []
    bh_returns = []
    prev_action = None
    round_trip_cost = estimate_execution_cost()
    cost_per_trade = round_trip_cost["total_pct"] / 100  # as a fraction
    total_trades = 0

    for idx, (_, row) in enumerate(df.iterrows()):
        fwd = row["forward_3m_return"] / 100
        action = row["signal_action"]

        # Detect position change (trade)
        traded = prev_action is not None and action != prev_action
        trade_cost = cost_per_trade if traded else 0.0
        if traded:
            total_trades += 1

        if action in ("Strong Buy", "Buy"):
            strategy_returns_gross.append(fwd)
            strategy_returns_net.append(fwd - trade_cost)
        elif action in ("Strong Sell", "Sell"):
            strategy_returns_gross.append(0.0)
            strategy_returns_net.append(-trade_cost if traded else 0.0)
        else:
            strategy_returns_gross.append(fwd * 0.5)
            strategy_returns_net.append(fwd * 0.5 - trade_cost)

        bh_returns.append(fwd)
        prev_action = action

    strategy_arr_gross = np.array(strategy_returns_gross)
    strategy_arr_net = np.array(strategy_returns_net)
    bh_arr = np.array(bh_returns)

    # Use non-overlapping quarterly observations (every 3rd) for compounding
    # and Sharpe to avoid inflating returns from overlapping 3M windows.
    q_idx = np.arange(0, len(strategy_arr_gross), 3)
    strategy_q_gross = strategy_arr_gross[q_idx]
    strategy_q_net = strategy_arr_net[q_idx]
    bh_q = bh_arr[q_idx]

    strategy_sharpe_gross = float(np.mean(strategy_q_gross) / max(np.std(strategy_q_gross), 1e-8) * np.sqrt(4))
    strategy_sharpe_net = float(np.mean(strategy_q_net) / max(np.std(strategy_q_net), 1e-8) * np.sqrt(4))
    bh_sharpe = float(np.mean(bh_q) / max(np.std(bh_q), 1e-8) * np.sqrt(4))

    strategy_total_gross = float((1 + strategy_q_gross).prod() - 1) * 100
    strategy_total_net = float((1 + strategy_q_net).prod() - 1) * 100
    bh_total = float((1 + bh_q).prod() - 1) * 100

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
        # Gross returns (before execution costs)
        "strategy_total_return_gross": round(strategy_total_gross, 2),
        # Net returns (after slippage + commission + market impact)
        "strategy_total_return": round(strategy_total_net, 2),
        "buy_hold_total_return": round(bh_total, 2),
        "strategy_sharpe_gross": round(strategy_sharpe_gross, 3),
        "strategy_sharpe": round(strategy_sharpe_net, 3),
        "buy_hold_sharpe": round(bh_sharpe, 3),
        # Execution cost summary
        "execution_costs": {
            "total_trades": total_trades,
            "cost_per_trade_bps": round_trip_cost["total_bps"],
            "total_cost_drag_pct": round(total_trades * cost_per_trade * 100, 2),
            "gross_minus_net_pct": round(strategy_total_gross - strategy_total_net, 2),
        },
        "missed_calls": period_analysis[:10],
        "signals_by_action": {
            action: len(df[df["signal_action"] == action])
            for action in ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"]
        },
    }
