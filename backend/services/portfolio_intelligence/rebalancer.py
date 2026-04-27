"""
Aegis Finance — Trade Computation (Rebalancer)
=================================================

Pure functions that compute trades needed to move from one set of weights
to another. No DB, no IO, no side effects.

Functions:
  compute_trades(old, new, prices, notional, cost_bps, slippage_bps) → (trades, total_cost)
  estimate_turnover(old, new) → float

Usage:
    from backend.services.portfolio_intelligence.rebalancer import (
        compute_trades, estimate_turnover,
    )
"""

import logging

logger = logging.getLogger(__name__)


def estimate_turnover(
    old_weights: dict[str, float],
    new_weights: dict[str, float],
) -> float:
    """One-way turnover: sum of absolute weight changes / 2."""
    all_tickers = set(list(old_weights.keys()) + list(new_weights.keys()))
    total_change = sum(
        abs(old_weights.get(t, 0.0) - new_weights.get(t, 0.0))
        for t in all_tickers
    )
    return total_change / 2.0


def compute_trades(
    old_weights: dict[str, float],
    new_weights: dict[str, float],
    prices: dict[str, float],
    notional: float,
    cost_bps: float = 5.0,
    slippage_bps: float = 1.0,
) -> tuple[list[dict], float]:
    """Compute the trades needed to rebalance from old to new weights.

    Returns:
        (trades, total_cost) where trades is a list of dicts with:
            ticker, side, shares, price, weight_change, dollar_amount,
            transaction_cost, slippage
        and total_cost is the sum of all transaction costs + slippage.
    """
    all_tickers = set(list(old_weights.keys()) + list(new_weights.keys()))
    trades = []
    total_cost = 0.0

    cost_rate = cost_bps / 10_000
    slip_rate = slippage_bps / 10_000

    for ticker in sorted(all_tickers):
        old_w = old_weights.get(ticker, 0.0)
        new_w = new_weights.get(ticker, 0.0)
        delta_w = new_w - old_w

        if abs(delta_w) < 1e-6:
            continue

        price = prices.get(ticker)
        if price is None or price <= 0:
            continue

        dollar_amount = abs(delta_w) * notional
        shares = dollar_amount / price
        txn_cost = dollar_amount * cost_rate
        slippage = dollar_amount * slip_rate

        trades.append({
            "ticker": ticker,
            "side": "buy" if delta_w > 0 else "sell",
            "shares": round(shares, 4),
            "price": round(price, 2),
            "weight_change": round(delta_w, 6),
            "dollar_amount": round(dollar_amount, 2),
            "transaction_cost": round(txn_cost, 2),
            "slippage": round(slippage, 2),
        })

        total_cost += txn_cost + slippage

    return trades, round(total_cost, 2)
