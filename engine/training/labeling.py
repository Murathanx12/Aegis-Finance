"""
Triple-Barrier Labeling for Crash Prediction
==============================================

Implements the triple-barrier method from Lopez de Prado (AFML, Ch. 3)
adapted for crash prediction rather than trade labeling.

Three barriers:
    1. Upper barrier (profit target): price rises +X% → label = 0 (no crash)
    2. Lower barrier (stop loss): price falls -Y% → label = 1 (crash)
    3. Vertical barrier (time expiration): neither barrier hit → check net return

This produces better-quality labels than the fixed-threshold approach
because it captures the PATH of prices, not just the endpoint.

Reference: mlfinlab/labeling/labeling.py (structure)

Usage:
    from engine.training.labeling import build_triple_barrier_labels
    labels = build_triple_barrier_labels(prices, horizon_days=63)
"""

import numpy as np
import pandas as pd
from typing import Optional


def add_vertical_barrier(
    t_events: pd.DatetimeIndex,
    close: pd.Series,
    num_days: int,
) -> pd.Series:
    """Add vertical (time) barrier for each event.

    Args:
        t_events: Event timestamps (when to start labeling)
        close: Price series
        num_days: Maximum holding period in trading days

    Returns:
        Series of vertical barrier timestamps
    """
    t1 = close.index.searchsorted(t_events + pd.Timedelta(days=num_days * 1.5))
    t1 = t1[t1 < close.shape[0]]
    t1 = pd.Series(close.index[t1], index=t_events[:t1.shape[0]])
    return t1


def apply_triple_barrier(
    close: pd.Series,
    events: pd.DataFrame,
    pt_sl: tuple[float, float],
) -> pd.DataFrame:
    """Apply profit-taking and stop-loss barriers to events.

    Args:
        close: Price series
        events: DataFrame with columns ['t1'] (vertical barrier time)
                indexed by event start time
        pt_sl: Tuple of (profit_target, stop_loss) as positive multipliers
               of the target return. E.g., (1.0, 1.0) means symmetric.

    Returns:
        DataFrame with columns ['t1', 'sl', 'pt'] — timestamps when
        each barrier was first touched (NaT if not touched)
    """
    out = events[["t1"]].copy()
    if pt_sl[0] > 0:
        pt = pt_sl[0] * events["target"]
    else:
        pt = pd.Series(dtype=float, index=events.index)

    if pt_sl[1] > 0:
        sl = -pt_sl[1] * events["target"]
    else:
        sl = pd.Series(dtype=float, index=events.index)

    for loc, t1 in events["t1"].items():
        df0 = close[loc:t1]
        if len(df0) < 2:
            continue
        path = df0 / close[loc] - 1.0

        # Check stop loss
        if sl.get(loc, 0) != 0:
            sl_times = path[path < sl[loc]]
            if not sl_times.empty:
                out.loc[loc, "sl"] = sl_times.index[0]

        # Check profit taking
        if pt.get(loc, 0) != 0:
            pt_times = path[path > pt[loc]]
            if not pt_times.empty:
                out.loc[loc, "pt"] = pt_times.index[0]

    return out


def get_barrier_labels(
    close: pd.Series,
    events: pd.DataFrame,
) -> pd.Series:
    """Determine which barrier was touched first and assign labels.

    Labels:
        1 = crash (stop-loss barrier hit first)
        0 = no crash (profit-taking or vertical barrier hit first with positive return)

    Returns:
        Series of binary labels (0 or 1)
    """
    out = pd.Series(dtype=float, index=events.index)

    for loc, row in events.iterrows():
        t1 = row.get("t1")
        sl = row.get("sl")
        pt = row.get("pt")

        # Find which barrier was touched first
        barriers = {}
        if pd.notna(sl):
            barriers["sl"] = sl
        if pd.notna(pt):
            barriers["pt"] = pt
        if pd.notna(t1):
            barriers["t1"] = t1

        if not barriers:
            continue

        first_barrier = min(barriers, key=barriers.get)

        if first_barrier == "sl":
            out[loc] = 1  # Crash — stop loss hit
        elif first_barrier == "pt":
            out[loc] = 0  # No crash — profit target hit
        else:
            # Vertical barrier: label based on return at expiry
            if loc in close.index and t1 in close.index:
                ret = close[t1] / close[loc] - 1
                out[loc] = 1 if ret < 0 else 0
            else:
                out[loc] = np.nan

    return out


def build_triple_barrier_labels(
    prices: pd.Series,
    horizon_days: int = 63,
    pt_pct: float = 0.10,
    sl_pct: float = 0.20,
    min_ret: float = 0.0,
    sample_freq: int = 1,
) -> pd.Series:
    """Build crash labels using the triple-barrier method.

    This is the main entry point for triple-barrier labeling in Aegis.

    Args:
        prices: Daily price series (e.g., S&P 500 close)
        horizon_days: Maximum holding period (vertical barrier)
                     63 = 3 months, 126 = 6 months, 252 = 12 months
        pt_pct: Profit target as percentage (default 10% = no crash)
        sl_pct: Stop loss as percentage (default 20% = crash)
        min_ret: Minimum return to consider an event (filter noise)
        sample_freq: Sample every N days (1 = daily, 5 = weekly)

    Returns:
        Series of binary labels: 1 = crash, 0 = no crash
        Indexed by the date of prediction (when you'd make the call)
    """
    # Handle DataFrame input (yfinance returns DataFrames)
    if isinstance(prices, pd.DataFrame):
        close = prices.squeeze().copy()
    else:
        close = prices.copy()

    # Define events: sample points at specified frequency
    if sample_freq > 1:
        t_events = close.index[::sample_freq]
    else:
        t_events = close.index

    # Remove events too close to end (can't evaluate full horizon)
    max_idx = len(close) - horizon_days - 1
    t_events = t_events[t_events <= close.index[max(0, max_idx)]]

    if len(t_events) == 0:
        return pd.Series(dtype=float, index=close.index)

    # Compute daily volatility for dynamic barriers
    daily_vol = close.pct_change().rolling(63).std()

    # Build events DataFrame
    t1 = pd.Series(dtype="datetime64[ns]", index=t_events)
    target = pd.Series(dtype=float, index=t_events)

    for i, t in enumerate(t_events):
        # Vertical barrier
        end_idx = close.index.searchsorted(t) + horizon_days
        if end_idx >= len(close):
            end_idx = len(close) - 1
        t1.iloc[i] = close.index[end_idx]

        # Target: use fixed percentages (not vol-scaled) for crash prediction
        target.iloc[i] = 1.0  # Multiplier — actual barriers are pt_pct and sl_pct

    events = pd.DataFrame({"t1": t1, "target": target})
    events = events.dropna()

    # Set barrier levels
    events["target"] = sl_pct  # Use sl_pct as the base target

    # Apply barriers
    # pt_sl = (pt/target, sl/target) — ratio of barrier to target
    pt_ratio = pt_pct / sl_pct
    barriers = apply_triple_barrier(close, events, pt_sl=(pt_ratio, 1.0))

    # Get labels
    labels = get_barrier_labels(close, barriers)

    # Reindex to full daily index
    full_labels = labels.reindex(close.index)

    return full_labels


def build_triple_barrier_multi(
    prices: pd.Series,
    pt_pct: float = 0.10,
    sl_pct: float = 0.20,
) -> dict:
    """Build triple-barrier labels for all three horizons.

    Returns:
        Dict of {"3m": Series, "6m": Series, "12m": Series}
    """
    horizons = {"3m": 63, "6m": 126, "12m": 252}
    return {
        name: build_triple_barrier_labels(
            prices,
            horizon_days=days,
            pt_pct=pt_pct,
            sl_pct=sl_pct,
        )
        for name, days in horizons.items()
    }
