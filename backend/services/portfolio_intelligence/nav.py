"""
Aegis Finance — Shared Mark-to-Market NAV Engine
==================================================

The single source of truth for portfolio value, used by BOTH modes:

  - Live mode  : mark today's share book to today's real prices, persist daily.
  - Replay mode: mark the SAME share book to each past day's real prices.

Because both modes call the same functions here, live and replay produce
*identical* NAV from identical inputs — that is the whole point of "one engine,
two modes". A position's value is always shares × real price (+ cash earning
the risk-free rate); there is no separate, divergent valuation path.

No look-ahead by construction: every function values a book using only the
prices it is handed for the dates requested. Pass an as-of-sliced panel and you
get an as-of NAV; nothing reaches forward in time.
"""

from __future__ import annotations

import pandas as pd

# Risk-free ticker proxy for the cash sleeve (1-3y T-bills). Cash held as this
# sleeve earns the short rate; modeled via rf_daily when no live yield is given.
CASH_TICKER = "CASH"


def mark_to_market(
    shares: dict[str, float],
    prices: dict[str, float],
    cash: float = 0.0,
) -> float:
    """NAV = cash + Σ shares·price.

    Tickers without a valid price are skipped (can't mark what you can't price).
    `cash` is a dollar balance already in the books (the T-bill/cash sleeve).
    """
    equity = 0.0
    for ticker, n in shares.items():
        price = prices.get(ticker)
        if price is not None and price > 0:
            equity += n * price
    return float(cash + equity)


def weights_to_shares(
    weights: dict[str, float],
    prices: dict[str, float],
    notional: float,
) -> tuple[dict[str, float], float]:
    """Convert target weights + notional into a share book at the given prices.

    Returns (shares, cash) where `cash` is the dollar value of any CASH_TICKER
    weight (held as a balance, not as shares). Names without a price are dropped
    and their weight falls through to cash so notional is conserved.
    """
    shares: dict[str, float] = {}
    cash = 0.0
    invested = 0.0
    for ticker, w in weights.items():
        if w <= 0:
            continue
        dollars = w * notional
        if ticker == CASH_TICKER:
            cash += dollars
            invested += dollars
            continue
        price = prices.get(ticker)
        if price is not None and price > 0:
            shares[ticker] = dollars / price
            invested += dollars
    # Any unpriceable weight is parked in cash so total value == notional.
    cash += max(0.0, notional - invested)
    return shares, cash


def nav_series(
    shares: dict[str, float],
    price_panel: pd.DataFrame,
    cash: float = 0.0,
    rf_daily: float = 0.0,
) -> pd.Series:
    """Daily NAV path for a FIXED share book over a price panel (no rebalancing).

    Cash compounds at `rf_daily` each step (the T-bill sleeve earning the short
    rate). `price_panel` is a DataFrame indexed by date with one column per
    ticker. This is the canonical equity-curve builder shared by replay.
    """
    cols = [t for t in shares if t in price_panel.columns]
    navs: list[float] = []
    cash_t = cash
    for i, dt in enumerate(price_panel.index):
        if i > 0:
            cash_t *= (1.0 + rf_daily)
        prices = {t: price_panel.at[dt, t] for t in cols}
        navs.append(mark_to_market(shares, prices, cash_t))
    return pd.Series(navs, index=price_panel.index, name="nav")
