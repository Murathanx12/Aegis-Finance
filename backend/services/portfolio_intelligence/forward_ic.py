"""
Forward-IC scorecard — read PIT signal snapshots back and grade them.
====================================================================

The collectors (T8 multifactor, T9 insider, T10 revisions) WRITE a per-ticker
score into ``pit_observations`` every week, forward, leak-free. Nothing yet READS
them back to answer the only question that matters: *does the signal actually
predict forward returns?* This module closes that loop.

For each ticker it reads the OBSERVED score series (``get_series_observable`` —
leak-free, value as it was knowable), joins each ``as_of`` score with the realized
forward return over a horizon, and runs the in-repo ``factor_ic`` bench (the
project's own Alphalens-style IC, no third-party dep).

Grade discipline:
  - **Directional by construction** — forward returns come from yfinance, so the
    realized-return leg is survivorship-biased. Every report is stamped
    ``data_grade`` (see data_integrity) so a forward-IC number is never mistaken
    for a sizing-grade backtest.
  - **Forward-only / leak-free** — the factor is what we KNEW at ``as_of``
    (``observed_at <= as_of_ts``); the forward return is strictly AFTER ``as_of``
    (the label). The IC clocks only started accruing in June 2026, so this will
    honestly report ``insufficient_history`` until enough weeks land — that is the
    bench working, not failing.
"""

from __future__ import annotations

import sqlite3
from typing import Callable, Optional

import pandas as pd

from backend.services.data_integrity import DEFAULT_PRICE_SOURCE, data_grade
from engine.validation.factor_ic import analyze_factor

# Need a real cross-section over several dates before an IC means anything.
MIN_PANEL_ROWS = 20
MIN_DATES = 3

# A price-history fetcher: ticker -> date-indexed close Series (or None).
PriceFetch = Callable[[str], "Optional[pd.Series]"]


def _forward_return(prices: pd.Series, as_of: pd.Timestamp, horizon_days: int) -> Optional[float]:
    """Realized return from the last close <= as_of to ``horizon_days`` trading
    days later. None if either leg is unavailable. ``prices`` must be sorted."""
    pos = int(prices.index.searchsorted(as_of, side="right")) - 1  # last idx <= as_of
    if pos < 0:
        return None
    exit_pos = pos + horizon_days
    if exit_pos >= len(prices):
        return None
    p0 = float(prices.iloc[pos])
    p1 = float(prices.iloc[exit_pos])
    if p0 == 0:
        return None
    return p1 / p0 - 1.0


def build_signal_panel(
    conn: sqlite3.Connection,
    key_prefix: str,
    tickers: list[str],
    *,
    price_history: PriceFetch,
    horizon_days: int = 21,
    as_of_ts: Optional[str] = None,
) -> pd.DataFrame:
    """Assemble a leak-safe long panel [date, asset, factor, fwd_return] from PIT.

    ``key_prefix`` is the signal family, e.g. ``"multifactor_score:"`` so the
    per-ticker key is ``f"{key_prefix}{ticker}"``. ``price_history(ticker)``
    returns a date-indexed close Series (network lives in the injected fetcher,
    so this stays unit-testable offline).
    """
    from backend.db import get_series_observable

    rows: list[dict] = []
    for t in tickers:
        series = get_series_observable(conn, f"{key_prefix}{t}", as_of_ts)
        if not series:
            continue
        prices = price_history(t)
        if prices is None or len(prices) == 0:
            continue
        prices = prices.sort_index()
        for obs in series:
            val = obs.get("value")
            if val is None:
                continue
            as_of = pd.Timestamp(obs["as_of"])
            fr = _forward_return(prices, as_of, horizon_days)
            if fr is None:
                continue
            rows.append(
                {"date": obs["as_of"], "asset": t, "factor": float(val), "fwd_return": fr}
            )
    return pd.DataFrame(rows, columns=["date", "asset", "factor", "fwd_return"])


def score_forward_ic(
    panel: pd.DataFrame,
    factor_col: str = "factor",
    fwd_col: str = "fwd_return",
    source: str = DEFAULT_PRICE_SOURCE,
    n_quantiles: int = 5,
) -> dict:
    """Pure: grade a [date, asset, factor, fwd_return] panel via ``factor_ic``,
    stamped with the data grade of the forward-return source. Reports
    ``insufficient_history`` rather than a misleading number on a thin panel."""
    n_rows = 0 if panel is None else len(panel)
    n_dates = 0 if panel is None or panel.empty else int(panel["date"].nunique())
    grade = data_grade(source).value
    if panel is None or n_rows < MIN_PANEL_ROWS or n_dates < MIN_DATES:
        return {
            "status": "insufficient_history",
            "n_rows": n_rows,
            "n_dates": n_dates,
            "data_grade": grade,
        }
    report = analyze_factor(panel, factor_col, fwd_col, n_quantiles=n_quantiles)
    report["status"] = "scored"
    report["data_grade"] = grade
    report["n_rows"] = n_rows
    report["n_dates"] = n_dates
    return report


def forward_ic_scorecard(
    conn: sqlite3.Connection,
    key_prefix: str,
    tickers: list[str],
    *,
    price_history: PriceFetch,
    horizon_days: int = 21,
    source: str = DEFAULT_PRICE_SOURCE,
    as_of_ts: Optional[str] = None,
) -> dict:
    """End-to-end: read PIT snapshots for ``key_prefix`` across ``tickers``,
    build the leak-safe panel, and grade it. Directional-grade (forward returns
    from a directional source)."""
    panel = build_signal_panel(
        conn, key_prefix, tickers,
        price_history=price_history, horizon_days=horizon_days, as_of_ts=as_of_ts,
    )
    out = score_forward_ic(panel, source=source)
    out["key_prefix"] = key_prefix
    out["horizon_days"] = horizon_days
    out["n_tickers"] = len(tickers)
    return out
