"""
PEAD signal — post-earnings-announcement drift score (TRIAL-PEAD-IC)
====================================================================

Verified basis (docs/research/ENGINE_GAPS_2026_07_09.md): PEAD is real but
DECAYING in the US, concentrated in small/high-cost names, and disputed
net-of-cost in liquid large caps. Surprise definition matters: analyst-based
surprises beat time-series SUE, a two-way combination is stronger, and the
announcement-window abnormal return works as a comprehensive third measure.

So the score combines the two free-data measures (both computable from
yfinance): the analyst-based surprise %, and the 3-day announcement-window
return in excess of SPY. It is strongest when they AGREE (the two-way-sort
finding). The signal exists only within a post-announcement window — stale
earnings mean no signal, honestly zero.

Honest prior (pre-registered): expected weak-to-moderate forward IC on a
large-cap-tilted universe. Descriptive only until the forward IC says more.
No claim that PEAD is independent of momentum (that claim was REFUTED 0-3 in
verification) — correlation with the momentum sleeve is measured, not assumed.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MAX_AGE_DAYS = 90        # PEAD is post-announcement; beyond this = no signal
ABNORMAL_WINDOW_TD = 3   # announcement-window: close[t-1] -> close[t+2]
SURPRISE_SCALE = 10.0    # |surprise%| that saturates the component to ±1
ABN_RET_SCALE = 0.10     # |abnormal 3d return| that saturates to ±1

PEAD_LABEL = ("descriptive PEAD score — decaying anomaly, disputed net-of-cost "
              "in large caps; forward-IC candidate, never a buy/sell signal")


def fetch_pead_inputs(ticker: str) -> dict:
    """Live inputs from yfinance: last earnings row + prices around it."""
    import yfinance as yf
    t = yf.Ticker(ticker)
    ed = t.earnings_dates  # DataFrame indexed by announcement datetime
    prices = t.history(period="6mo")["Close"]
    spy = yf.Ticker("SPY").history(period="6mo")["Close"]
    return {"earnings_dates": ed, "prices": prices, "spy": spy}


def _last_reported(ed: Optional[pd.DataFrame], as_of: pd.Timestamp):
    """(announcement_ts, surprise_pct) of the most recent REPORTED earnings
    on/before as_of, or (None, None)."""
    if ed is None or len(ed) == 0:
        return None, None
    df = ed.copy()
    idx = pd.to_datetime(df.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    df.index = idx
    df = df[df.index <= as_of]
    # a REPORTED row has a reported EPS (future scheduled rows are NaN)
    rep_col = next((c for c in df.columns if "Reported" in str(c)), None)
    sur_col = next((c for c in df.columns if "Surprise" in str(c)), None)
    if rep_col is not None:
        df = df[df[rep_col].notna()]
    if len(df) == 0:
        return None, None
    row = df.sort_index().iloc[-1]
    ts = df.sort_index().index[-1]
    surprise = None
    if sur_col is not None and pd.notna(row[sur_col]):
        surprise = float(row[sur_col])
    return ts, surprise


def _abnormal_window_return(prices: pd.Series, spy: pd.Series,
                            ann_ts: pd.Timestamp) -> Optional[float]:
    """close[t-1] -> close[t+ABNORMAL_WINDOW_TD-1] return minus SPY's."""
    def _win_ret(s: pd.Series) -> Optional[float]:
        s = s.dropna()
        if s.empty:
            return None
        idx = s.index
        if getattr(idx, "tz", None) is not None:
            s = s.copy(); s.index = idx.tz_localize(None)
        i = s.index.searchsorted(ann_ts.normalize())
        if i == 0 or i + ABNORMAL_WINDOW_TD - 1 >= len(s):
            return None
        return float(s.iloc[i + ABNORMAL_WINDOW_TD - 1] / s.iloc[i - 1] - 1.0)
    r, m = _win_ret(prices), _win_ret(spy)
    if r is None or m is None:
        return None
    return r - m


def compute_pead_score(inputs: dict, as_of: str | None = None) -> dict:
    """Pure scorer. Returns {pead_score in [-1,1], components, status}.
    Score = mean of the two clipped components; 0 with an honest status when
    there is no fresh reported announcement or no usable component."""
    aso = pd.Timestamp(as_of) if as_of else pd.Timestamp(datetime.now().date())
    ann_ts, surprise_pct = _last_reported(inputs.get("earnings_dates"), aso)
    if ann_ts is None:
        return {"pead_score": 0.0, "status": "no_reported_earnings",
                "label": PEAD_LABEL}
    age = int((aso - ann_ts.normalize()).days)
    if age > MAX_AGE_DAYS:
        return {"pead_score": 0.0, "status": "stale_earnings",
                "days_since_earnings": age, "label": PEAD_LABEL}

    comps: list[float] = []
    surprise_comp = None
    if surprise_pct is not None:
        surprise_comp = float(np.clip(surprise_pct / SURPRISE_SCALE, -1, 1))
        comps.append(surprise_comp)
    abn = _abnormal_window_return(inputs.get("prices", pd.Series(dtype=float)),
                                  inputs.get("spy", pd.Series(dtype=float)), ann_ts)
    abn_comp = None
    if abn is not None:
        abn_comp = float(np.clip(abn / ABN_RET_SCALE, -1, 1))
        comps.append(abn_comp)

    if not comps:
        return {"pead_score": 0.0, "status": "no_usable_components",
                "days_since_earnings": age, "label": PEAD_LABEL}

    score = float(np.mean(comps))
    aligned = (len(comps) == 2 and np.sign(comps[0]) == np.sign(comps[1])
               and comps[0] != 0)
    return {
        "pead_score": round(score, 4),
        "status": "ok",
        "announcement_date": str(ann_ts.date()),
        "days_since_earnings": age,
        "surprise_pct": surprise_pct,
        "surprise_component": surprise_comp,
        "abnormal_3d_excess_return": None if abn is None else round(abn, 4),
        "abnormal_component": abn_comp,
        "two_way_aligned": bool(aligned),
        "n_components": len(comps),
        "label": PEAD_LABEL,
    }
