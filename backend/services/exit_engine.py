"""
Aegis Finance — Exit Engine & Position Sizing
=============================================

The mechanical answer to the disposition effect — the documented behavioural
leak behind "I sold NVDA/MRVL/MU too early." Odean (1998, JF): investors are
>50% more likely to sell a winner than a loser, and the winners they sell beat
the losers they hold by 3.4pp/year. An engine that cannot *express* "let this
winner run" will always cut it early. This module gives it that vocabulary.

Three evidence-backed primitives, all PURE and STATELESS (so they backtest
leakage-free and unit-test deterministically):

  1. ATR trailing stop (Chandelier Exit, LeBeau): stop ratchets UP with the
     highest close since entry, never down — `stop = peak_close - k * ATR`.
     This is the canonical "let winners run, but protect the gain" rule. It
     does NOT use a fixed % target (the thing that made you sell at +200%).

  2. Volatility targeting: size a position so its expected contribution to
     portfolio vol is ~constant. High-vol names get a smaller weight. Reduces
     the path-dependence that shakes you out of a good name on noise.

  3. Fractional Kelly: bet a fraction of the growth-optimal Kelly stake. Full
     Kelly is too aggressive out-of-sample (estimation error in p and b);
     quarter-Kelly is the practitioner default.

HARD CONSTRAINT: descriptive-only. Nothing here arms a live lane or emits
buy/sell language until a pre-registered backtest (TRIAL-THEME) clears the
DSR/PBO gate. Params live in config["exit_engine"].

Usage:
    from backend.services.exit_engine import (
        compute_atr, simulate_trailing_exit,
        volatility_target_weight, fractional_kelly_fraction,
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from backend.config import config

logger = logging.getLogger(__name__)


def _exit_cfg() -> dict:
    return config.get("exit_engine", {})


# ── Average True Range (Wilder) ───────────────────────────────────────────────


def compute_atr(
    close: pd.Series,
    high: Optional[pd.Series] = None,
    low: Optional[pd.Series] = None,
    period: Optional[int] = None,
) -> pd.Series:
    """Wilder's Average True Range.

    If ``high``/``low`` are provided, uses the true range
    ``max(H-L, |H-prev_close|, |L-prev_close|)``. If only ``close`` is
    available (the common case in a close-only backtest), falls back to the
    absolute close-to-close move as the true-range proxy — a slightly smoother,
    conservative ATR. Returns a series aligned to ``close`` (first value is the
    seed, never NaN after the warm-up).
    """
    if period is None:
        period = int(_exit_cfg().get("atr_period", 14))

    close = close.astype(float)
    prev_close = close.shift(1)

    if high is not None and low is not None:
        high = high.astype(float)
        low = low.astype(float)
        tr = pd.concat(
            [
                (high - low),
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
    else:
        # Close-only proxy: |Δclose|. First bar has no prior → seed with 0.
        tr = (close - prev_close).abs()

    tr.iloc[0] = tr.iloc[1] if len(tr) > 1 else 0.0
    # Wilder smoothing ≈ EMA with alpha = 1/period.
    atr = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    return atr


# ── Trailing-stop exit simulation (the testable core) ─────────────────────────


@dataclass
class ExitResult:
    """Outcome of holding a position from ``entry_index`` under a trailing stop."""

    exit_index: int
    exit_price: float
    reason: str  # "trailing_stop" | "end_of_data"
    bars_held: int
    return_pct: float          # realised return entry→exit
    max_favorable_pct: float   # peak unrealised gain reached while held
    stop_path: list[float] = field(default_factory=list)


def simulate_trailing_exit(
    close: pd.Series,
    high: Optional[pd.Series] = None,
    low: Optional[pd.Series] = None,
    entry_index: int = 0,
    atr_period: Optional[int] = None,
    atr_multiple: Optional[float] = None,
) -> ExitResult:
    """Hold from ``entry_index`` until an ATR (Chandelier) trailing stop fires.

    The stop ratchets up with the highest close seen since entry and never
    moves down: ``stop_t = max(stop_{t-1}, peak_close_t - k * ATR_t)``. The
    position exits the first bar whose close is at/below the prevailing stop,
    filled CONSERVATIVELY at that bar's close (no intrabar/gap optimism — if
    ``low`` is supplied it is used only to *detect* an intrabar breach, the
    fill is still the close). If the stop never fires, exits at the last bar
    (reason ``end_of_data``).

    Pure function of its inputs — no I/O, no global state.
    """
    cfg = _exit_cfg()
    if atr_period is None:
        atr_period = int(cfg.get("atr_period", 14))
    if atr_multiple is None:
        atr_multiple = float(cfg.get("atr_stop_multiple", 3.0))

    close = close.astype(float).reset_index(drop=True)
    if high is not None:
        high = high.astype(float).reset_index(drop=True)
    if low is not None:
        low = low.astype(float).reset_index(drop=True)

    n = len(close)
    if n == 0:
        raise ValueError("close series is empty")
    if not (0 <= entry_index < n):
        raise ValueError(f"entry_index {entry_index} out of range [0, {n})")

    atr = compute_atr(close, high, low, period=atr_period).reset_index(drop=True)

    entry_price = float(close.iloc[entry_index])
    peak_close = entry_price
    stop = peak_close - atr_multiple * float(atr.iloc[entry_index])
    stop_path: list[float] = [stop]
    max_favorable = 0.0

    for i in range(entry_index + 1, n):
        px = float(close.iloc[i])
        peak_close = max(peak_close, px)
        max_favorable = max(max_favorable, peak_close / entry_price - 1.0)

        # Ratchet the stop up; never down.
        candidate = peak_close - atr_multiple * float(atr.iloc[i])
        stop = max(stop, candidate)
        stop_path.append(stop)

        breached = px <= stop
        if low is not None:
            breached = breached or (float(low.iloc[i]) <= stop)

        if breached:
            exit_price = px  # conservative close fill
            return ExitResult(
                exit_index=i,
                exit_price=exit_price,
                reason="trailing_stop",
                bars_held=i - entry_index,
                return_pct=exit_price / entry_price - 1.0,
                max_favorable_pct=max_favorable,
                stop_path=stop_path,
            )

    last = n - 1
    exit_price = float(close.iloc[last])
    return ExitResult(
        exit_index=last,
        exit_price=exit_price,
        reason="end_of_data",
        bars_held=last - entry_index,
        return_pct=exit_price / entry_price - 1.0,
        max_favorable_pct=max_favorable,
        stop_path=stop_path,
    )


# ── Position sizing ───────────────────────────────────────────────────────────


def realized_vol(returns: pd.Series, lookback: Optional[int] = None,
                 trading_days_year: Optional[int] = None) -> float:
    """Annualized realized volatility from a daily-return series."""
    cfg = _exit_cfg()
    if lookback is None:
        lookback = int(cfg.get("vol_lookback_days", 63))
    if trading_days_year is None:
        trading_days_year = int(cfg.get("trading_days_year", 252))

    r = pd.Series(returns).dropna().astype(float)
    if len(r) < 2:
        return float("nan")
    window = r.iloc[-lookback:] if len(r) > lookback else r
    return float(window.std(ddof=1) * np.sqrt(trading_days_year))


def volatility_target_weight(
    returns: pd.Series,
    target_vol: Optional[float] = None,
    max_weight: Optional[float] = None,
    lookback: Optional[int] = None,
) -> float:
    """Weight that scales a position to a target annualized volatility.

    ``w = target_vol / realized_vol``, clamped to ``[0, max_weight]``. A
    quiet name gets up to the cap; a violent name gets trimmed. Returns 0.0 if
    realized vol is non-finite or non-positive (can't size what we can't
    measure).
    """
    cfg = _exit_cfg()
    if target_vol is None:
        target_vol = float(cfg.get("vol_target_annual", 0.20))
    if max_weight is None:
        max_weight = float(cfg.get("max_position_weight", 0.25))

    rv = realized_vol(returns, lookback=lookback)
    if not np.isfinite(rv) or rv <= 0:
        return 0.0
    return float(min(max_weight, max(0.0, target_vol / rv)))


def fractional_kelly_fraction(
    win_prob: float,
    win_loss_ratio: float,
    fraction: Optional[float] = None,
    cap: Optional[float] = None,
) -> float:
    """Fractional-Kelly bet size.

    Full Kelly for a binary bet: ``f* = p - (1 - p) / b`` where ``b`` is the
    win/loss payoff ratio. We return ``fraction * f*`` clamped to ``[0, cap]``.
    A non-positive edge → 0.0 (don't bet). Full Kelly is deliberately scaled
    down: out-of-sample, estimation error in ``p`` and ``b`` makes full Kelly
    over-bet and blow through drawdowns.
    """
    cfg = _exit_cfg()
    if fraction is None:
        fraction = float(cfg.get("kelly_fraction", 0.25))
    if cap is None:
        cap = float(cfg.get("kelly_cap", 0.25))

    if not (0.0 <= win_prob <= 1.0):
        raise ValueError(f"win_prob must be in [0, 1], got {win_prob}")
    if win_loss_ratio <= 0:
        return 0.0

    kelly = win_prob - (1.0 - win_prob) / win_loss_ratio
    if kelly <= 0:
        return 0.0
    return float(min(cap, max(0.0, fraction * kelly)))
