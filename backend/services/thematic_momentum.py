"""
Aegis Finance — Thematic-Momentum Strategy (pure entry logic)
=============================================================

The mechanical, LLM-free expression of Murat's thesis: inside point-in-time
secular-demand baskets, buy the names whose trend is already turning up
(12-1 cross-sectional momentum, the textbook winner-continuation signal),
size by volatility target, cap concentration. Exits (the "let winners run"
half) are applied by `exit_engine` in the backtester between rebalances.

PURE: ``compute_target_weights`` is a function of (as_of_date, price frame
sliced to <= as_of_date) only — no I/O, no globals — so it backtests
leakage-free and unit-tests deterministically.

This is DESCRIPTIVE research code. It does not arm a live lane; the verdict on
whether it beats SPY net-of-cost-and-haircut is TRIAL-THEME (see
docs/research/THEMATIC_MOMENTUM_2026-06-15.md).
"""

from __future__ import annotations

import datetime as _dt
from typing import Optional

import numpy as np
import pandas as pd

from backend.services.exit_engine import volatility_target_weight
from backend.services.theme_baskets import members_as_of, theme_keys

DateLike = "str | _dt.date | _dt.datetime"

_TRADING_DAYS_MONTH = 21


def momentum_12_1(series: pd.Series, lookback_months: int = 12,
                  skip_months: int = 1) -> Optional[float]:
    """Textbook 12-1 momentum: return from t-lookback to t-skip (skips the most
    recent month to avoid short-term reversal). Returns None if history is short.
    """
    s = series.dropna()
    look = lookback_months * _TRADING_DAYS_MONTH
    skip = skip_months * _TRADING_DAYS_MONTH
    if len(s) < look + 1:
        return None
    p_start = float(s.iloc[-(look + 1)])
    p_end = float(s.iloc[-(skip + 1)]) if skip > 0 else float(s.iloc[-1])
    if p_start <= 0:
        return None
    return p_end / p_start - 1.0


def compute_target_weights(
    as_of: DateLike,
    prices_as_of: pd.DataFrame,
    *,
    lookback_months: int = 12,
    skip_months: int = 1,
    top_k: int = 10,
    vol_target: float = 0.20,
    max_weight: float = 0.25,
    vol_lookback: int = 63,
) -> dict[str, float]:
    """Target weights for the thematic-momentum strategy as of ``as_of``.

    Steps (all using only data in ``prices_as_of``, which must be pre-sliced to
    rows <= as_of):
      1. Union of point-in-time theme members available on ``as_of``.
      2. Keep names with computable, POSITIVE 12-1 momentum (trend filter — no
         falling knives).
      3. Take the top-``top_k`` by momentum across all themes.
      4. Volatility-target each (quiet names larger, violent names smaller),
         cap at ``max_weight``, renormalize to fully invest the selected sleeve.

    Returns ``{ticker: weight}`` summing to ~1.0 over the selected names, or
    ``{}`` (go to cash) if no name has positive momentum.
    """
    # 1. as-of theme universe
    universe: set[str] = set()
    for tk in theme_keys():
        universe.update(members_as_of(tk, as_of))
    cols = [t for t in universe if t in prices_as_of.columns]
    if not cols:
        return {}

    # 2. positive 12-1 momentum only
    scored: list[tuple[str, float]] = []
    for t in cols:
        m = momentum_12_1(prices_as_of[t], lookback_months, skip_months)
        if m is not None and m > 0:
            scored.append((t, m))
    if not scored:
        return {}

    # 3. top-K by momentum
    scored.sort(key=lambda x: x[1], reverse=True)
    selected = [t for t, _ in scored[:top_k]]

    # 4. vol-target sizing, capped, renormalized
    raw: dict[str, float] = {}
    for t in selected:
        rets = prices_as_of[t].dropna().pct_change().dropna()
        w = volatility_target_weight(
            rets, target_vol=vol_target, max_weight=max_weight,
            lookback=vol_lookback,
        )
        if w > 0:
            raw[t] = w

    total = sum(raw.values())
    if total <= 0:
        # momentum positive but vol unmeasurable → equal-weight the selection
        eq = 1.0 / len(selected)
        return {t: eq for t in selected}
    return {t: w / total for t, w in raw.items()}
