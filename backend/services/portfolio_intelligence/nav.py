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

import logging

import pandas as pd

logger = logging.getLogger(__name__)

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
        if ticker == CASH_TICKER:
            equity += n  # cash sleeve held as a $-balance (price ≡ 1.0)
            continue
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


_RF_CACHE: dict[str, float] = {}


def get_rf_daily(annual_fallback: float = 0.04) -> float:
    """Daily risk-free rate from FRED's 3-month T-bill (DGS3MO), cached.

    This is the `rf_daily` the cash sleeve earns. Converts the latest annual
    yield (percent) to a daily compounding rate. Falls back to `annual_fallback`
    if FRED is unavailable, so callers never get a hard dependency on the API.
    """
    if "v" in _RF_CACHE:
        return _RF_CACHE["v"]
    annual = annual_fallback
    source = "fallback"
    try:
        from backend.services.data_fetcher import api_keys
        if api_keys.has("fred"):
            from fredapi import Fred
            series = Fred(api_key=api_keys.fred).get_series("DGS3MO").dropna()
            if len(series):
                annual = float(series.iloc[-1]) / 100.0
                source = "FRED:DGS3MO"
    except Exception as e:
        logger.warning("get_rf_daily: FRED fetch failed (%s); using fallback", e)
        annual = annual_fallback
    # Log which source is active — a silent fallback to 4% would distort cash returns.
    logger.info("get_rf_daily: rf=%.3f%% annual (source=%s)", annual * 100, source)
    rf = (1.0 + annual) ** (1.0 / 252.0) - 1.0
    _RF_CACHE["v"] = rf
    return rf


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
