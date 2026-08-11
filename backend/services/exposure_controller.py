"""Exposure control, not crash prediction — and never an exit without a re-entry.

WHY THIS IS NOT A CRASH MODEL
=============================

Murat's third self-diagnosed failure is that he rode a drawdown down without
reducing exposure. The tempting fix is a crash predictor, and this programme has
one that does not work (`crash_model.pkl` is broken, M3). The tempting fix is
also the wrong shape: a detector that sells correctly and misses the rebound
destroys compounding just as thoroughly as the drawdown it avoided, and it can
look brilliant in every bear market while losing the argument over a decade.

So the object here is an EXPOSURE BUDGET, not a forecast. It maps observable
market state to how much beta to carry, and it is judged on BOTH captures at
once. A book that captures 40% of the upside and 40% of the downside has no
timing skill; it has less risk, which anyone can buy for free by holding less.

EVERY REDUCTION SHIPS WITH ITS RE-ENTRY
---------------------------------------
`ExposurePolicy` cannot express "reduce" without also expressing what brings the
exposure back and how long it must wait. This is enforced in the constructor
rather than left to discipline, because the failure mode is silent: a controller
with no re-entry rule looks fine in every backtest that ends during the
drawdown.

WHAT THIS V0 IS NOT
-------------------
It is not calibrated, not promoted, and not attached to any lane. It is a
measuring instrument for a question that had none: what WOULD an exposure rule
have done to his book and to the lanes, on both captures.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

#: State -> fraction of full exposure. Frozen before any evaluation.
EXPOSURE_BUDGET = {"risk_on": 1.00, "neutral": 0.75, "risk_off": 0.50,
                   "crisis": 0.25}


@dataclass(frozen=True)
class ExposurePolicy:
    """A reduction rule and the re-entry rule that must accompany it."""
    trend_window: int = 200
    vol_window: int = 21
    vol_lookback: int = 252
    #: how far below its own moving average the benchmark must sit to de-risk
    trend_trigger: float = -0.02
    #: realised vol ratio above which the state escalates
    vol_trigger: float = 1.5
    #: THE RE-ENTRY. Minimum trading days at a reduced budget before exposure
    #: may rise again, so a whipsaw cannot sell the bottom and buy the top.
    min_dwell_days: int = 10
    #: the benchmark must recover ABOVE its moving average by this much to
    #: re-risk — a band, not a line, or the rule trades its own noise
    reentry_trigger: float = 0.01

    def __post_init__(self) -> None:
        if self.reentry_trigger <= self.trend_trigger:
            raise ValueError(
                "the re-entry threshold must sit above the de-risking one or "
                "the rule has no band and will trade its own noise")
        if self.min_dwell_days < 1:
            raise ValueError(
                "a reduction with no minimum dwell has no re-entry protocol; a "
                "detector that sells and misses the rebound destroys "
                "compounding as surely as the drawdown it avoided")


def classify(bench: pd.Series, policy: ExposurePolicy) -> pd.DataFrame:
    """Daily state and exposure budget from benchmark price alone.

    Uses only trend and realised volatility — both observable at the close, both
    already validated state variables in this programme. No crash probability
    appears anywhere.
    """
    px = bench.dropna()
    ma = px.rolling(policy.trend_window, min_periods=policy.trend_window).mean()
    gap = px / ma - 1.0
    r = px.pct_change(fill_method=None)
    v_now = r.rolling(policy.vol_window).std(ddof=1)
    v_ref = r.rolling(policy.vol_lookback).std(ddof=1)
    v_ratio = v_now / v_ref

    state, budget, dwell, warmup = [], [], 0, 0
    prev_state = "risk_on"
    for i in range(len(px)):
        g, vr = gap.iloc[i], v_ratio.iloc[i]
        if not np.isfinite(g) or not np.isfinite(vr):
            # Warmup: not enough history for the trend or vol reference. The
            # controller is silently FULL RISK here, which is a real state and
            # not a neutral one, so it is counted and reported.
            warmup += 1
            state.append("warmup_full_risk"); budget.append(1.0); continue

        if g < policy.trend_trigger and vr > policy.vol_trigger:
            s = "crisis"
        elif g < policy.trend_trigger:
            s = "risk_off"
        elif vr > policy.vol_trigger:
            s = "neutral"
        else:
            s = "risk_on"

        # re-entry: rising exposure requires BOTH the dwell and the band
        rising = EXPOSURE_BUDGET[s] > EXPOSURE_BUDGET[prev_state]
        if rising and not (dwell >= policy.min_dwell_days
                           and g > policy.reentry_trigger):
            s = prev_state
        dwell = dwell + 1 if s == prev_state else 0
        prev_state = s
        state.append(s)
        budget.append(EXPOSURE_BUDGET[s])

    if warmup:
        logger.warning("exposure controller: %d of %d days had insufficient "
                       "history and carried FULL risk by default — a short "
                       "price history silently disables the control", warmup,
                       len(px))
    return pd.DataFrame({"state": state, "exposure": budget}, index=px.index)


def apply_overlay(book_returns: pd.Series, exposure: pd.Series) -> pd.Series:
    """Apply yesterday's exposure to today's return.

    Lagged by one day, always. An overlay that uses the same day's classification
    is reading the close it is trading on.
    """
    e = exposure.reindex(book_returns.index).ffill().shift(1).fillna(1.0)
    return book_returns * e


def both_captures(book: pd.Series, bench: pd.Series) -> dict:
    """Up- and down-capture together, plus what the reduction actually cost.

    Reported as a pair with the ratio, because either number alone can be made
    to look good by carrying less risk.
    """
    idx = book.index.intersection(bench.index)
    b, m = book.reindex(idx).dropna(), bench.reindex(idx).dropna()
    idx = b.index.intersection(m.index)
    b, m = b.reindex(idx), m.reindex(idx)
    up, dn = m > 0, m < 0

    def _c(mask):
        if mask.sum() < 5 or abs(m[mask].mean()) < 1e-12:
            return None
        return float(b[mask].mean() / m[mask].mean())

    uc, dc = _c(up), _c(dn)
    return {
        "n_days": int(len(b)), "up_capture": uc, "down_capture": dc,
        "capture_ratio": (uc / dc if uc is not None and dc not in (None, 0)
                          else None),
        "total_return": float((1 + b).prod() - 1),
        "benchmark_total": float((1 + m).prod() - 1),
        "max_drawdown": float(((1 + b).cumprod()
                               / (1 + b).cumprod().cummax() - 1).min()),
        "benchmark_max_drawdown": float(((1 + m).cumprod()
                                         / (1 + m).cumprod().cummax() - 1).min()),
        "reading": ("a capture ratio above 1 is the only version of timing "
                    "skill this reports; below 1 with both captures reduced is "
                    "just less risk, which costs nothing to buy"),
    }
