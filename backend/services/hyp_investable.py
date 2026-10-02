"""Investable comparisons for "beats its twin" results (hypothesis lab, 2026-09-30).

The library's matched twin is an equal-weight, 100%-turnover redraw from size x vol x
momentum cells. A rule can beat it while losing to the market, because the twin itself
trails the market. This module holds the pure pieces that turn a rule's monthly picks
into comparisons an investor could actually hold:

- a deterministic twin BASKET (the selection's cell mix x every non-selected eligible
  name in those cells, equal weight within a cell) whose own turnover and spread can be
  charged when it is the SHORT leg;
- a band-matched value-weight index (the rule's size-band mix, cap-weighted inside each
  band) -- the "short the size index" hedge;
- a point-in-time beta (trailing months strictly before the decision) for the
  "short the market future" hedge;
- spread statistics keyed on the HOLD month with 3-month-block t, MDE, by-year and the
  drawdown of the compounded spread.

Everything is offline and synthetic-testable (`backend/tests/test_hyp_investable.py`).
The runner is `scripts/hyp_investable.py`.
"""
from __future__ import annotations

import math
from typing import Iterable, Optional

import numpy as np
import pandas as pd

#: annual borrow fee charged on a SHORT stock leg, by the engine's size band (declared
#: before any spread was read; general-collateral levels with a small-cap hard-to-borrow load)
BORROW_ANNUAL = {"mega": 0.0025, "large": 0.0030, "mid": 0.0060, "small": 0.0150, "na": 0.0150}
#: all-in annual cost of shorting a size index through an ETF/future (borrow + fees + roll)
INDEX_SHORT_ANNUAL = 0.0035
#: all-in annual cost of a market future hedge (roll + basis drag)
FUTURE_ANNUAL = 0.0012
BETA_WINDOW, BETA_MIN = 36, 24


def twin_basket(sel: Iterable[str], cells: pd.Series, eligible_fwd_ok: pd.Series) -> dict:
    """{symbol: weight} of the twin basket.

    `cells`: symbol -> cell key for the date's eligible names; `eligible_fwd_ok`:
    symbol -> bool (eligible with a forward return). The selection's cell mix is taken
    from the selected names that have a cell; each cell's share is spread equally over
    that cell's NON-selected eligible names. A cell with no such name drops out and the
    mix is renormalised. Returns {} when nothing can be matched."""
    sel = [s for s in dict.fromkeys(sel)]
    sk = cells.reindex(sel).dropna()
    if not len(sk):
        return {}
    mix = sk.value_counts(normalize=True)
    ok = eligible_fwd_ok.reindex(cells.index).fillna(False).astype(bool)
    pool = cells[ok & ~cells.index.isin(sel)]
    members = pool.groupby(pool).groups
    w: dict = {}
    tot = 0.0
    for c, share in mix.items():
        names = list(members.get(c, []))
        if not names:
            continue
        tot += share
        for s in names:
            w[s] = w.get(s, 0.0) + share / len(names)
    if tot <= 0:
        return {}
    return {s: v / tot for s, v in w.items()}


def band_index(sel_bands: pd.Series, band: pd.Series, mcap: pd.Series, ok: pd.Series) -> dict:
    """{symbol: weight}: the selection's band mix, cap-weighted inside each band over
    eligible names with a forward return and a positive cap (selected names included:
    an index fund holds them too)."""
    if not len(sel_bands):
        return {}
    mix = sel_bands.value_counts(normalize=True)
    w: dict = {}
    tot = 0.0
    okm = ok.reindex(band.index).fillna(False).astype(bool) & (mcap.reindex(band.index) > 0)
    for b, share in mix.items():
        m = okm & (band == b)
        if not m.any():
            continue
        c = mcap.reindex(band.index)[m]
        tot += share
        for s, v in (c / c.sum() * share).items():
            w[s] = w.get(s, 0.0) + float(v)
    if tot <= 0:
        return {}
    return {s: v / tot for s, v in w.items()}


def book_return(w: dict, fwd: pd.Series) -> float:
    """Weighted forward return; a held name with no return earns 0 (cash)."""
    if not w:
        return float("nan")
    r = fwd.reindex(list(w)).to_numpy(dtype=float)
    ww = np.array(list(w.values()), dtype=float)
    return float(np.nansum(ww * np.where(np.isfinite(r), r, 0.0)))


def trade_cost(prev_w: dict, w: dict, spread: dict, default: float) -> tuple[float, float]:
    """(cost, one-way turnover): each |dw| pays half its name's round-trip spread."""
    cost, to = 0.0, 0.0
    for s in set(prev_w) | set(w):
        dw = abs(w.get(s, 0.0) - prev_w.get(s, 0.0))
        if dw:
            sp = spread.get(s, default)
            cost += dw * (sp if np.isfinite(sp) else default) / 2.0
            to += dw
    return cost, to / 2.0


def drift(w: dict, fwd: pd.Series) -> dict:
    """Weights after one period of returns (renormalised); names without a return keep weight."""
    if not w:
        return {}
    r = fwd.reindex(list(w)).to_numpy(dtype=float)
    v = np.array(list(w.values())) * (1.0 + np.where(np.isfinite(r), r, 0.0))
    v = np.clip(v, 0.0, None)
    t = v.sum()
    return {s: float(x / t) for s, x in zip(w, v)} if t > 0 else {}


def borrow_cost_monthly(w: dict, band_of: dict) -> float:
    return float(sum(v * BORROW_ANNUAL.get(band_of.get(s, "na"), BORROW_ANNUAL["na"]) for s, v in w.items()) / 12.0)


def pit_beta(y: pd.Series, x: pd.Series, window: int = BETA_WINDOW, min_n: int = BETA_MIN) -> pd.Series:
    """Beta of y on x at each date using ONLY rows strictly before that date (the row keyed
    at d is the period d -> next d, realised at the next decision). NaN until `min_n` rows."""
    df = pd.DataFrame({"y": y, "x": x}).sort_index()
    out = {}
    for i, d in enumerate(df.index):
        h = df.iloc[max(0, i - window):i].dropna()
        if len(h) < min_n or h["x"].var() <= 0:
            out[d] = np.nan
            continue
        out[d] = float(np.cov(h["y"], h["x"], ddof=1)[0, 1] / h["x"].var(ddof=1))
    return pd.Series(out, dtype=float)


def hold_index(idx) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(idx) + pd.offsets.BDay(1)


def window(s: pd.Series, lo: Optional[str], hi: Optional[str]) -> pd.Series:
    s = pd.Series(s, dtype=float).dropna()
    h = hold_index(s.index)
    m = np.ones(len(s), dtype=bool)
    if lo:
        m &= h >= pd.Timestamp(lo)
    if hi:
        m &= h <= pd.Timestamp(hi)
    return s[m]


def max_drawdown(s: pd.Series) -> Optional[float]:
    s = pd.Series(s, dtype=float).dropna()
    if not len(s):
        return None
    nav = (1.0 + s).cumprod()
    return float((nav / nav.cummax() - 1.0).min())


def spread_stats(s: pd.Series, lo: Optional[str] = None, hi: Optional[str] = None, *,
                 block: int = 3, mde_z: float = 2.8) -> dict:
    """Mean monthly spread over [lo, hi] on the HOLD month, t on non-overlapping
    `block`-month blocks, MDE = 2.8 SE, by-year sums, years positive, drawdown."""
    w = window(s, lo, hi)
    n = int(len(w))
    out = {"window": [lo, hi], "n_months": n, "mean_monthly": float(w.mean()) if n else None,
           "t_blocks": None, "mde_monthly": None, "sd_monthly": float(w.std()) if n > 2 else None,
           "max_drawdown": max_drawdown(w), "by_year": {}, "years_positive": None}
    if n >= block * 3:
        b = np.arange(n) // block
        sums = w.groupby(b).sum()
        nb = len(sums)
        sd = float(sums.std(ddof=1))
        if nb > 2 and sd > 0:
            se_b = sd / math.sqrt(nb)
            out["t_blocks"] = float(sums.mean() / se_b)
            out["mde_monthly"] = mde_z * se_b / float(w.groupby(b).size().mean())
    if n:
        yrs = hold_index(w.index).year
        by = w.groupby(yrs).sum()
        out["by_year"] = {str(int(k)): round(float(v), 5) for k, v in by.items()}
        out["years_positive"] = f"{int((by > 0).sum())} of {len(by)}"
    return out


def survives(design: dict, validate: dict, *, t_min: float = 2.0) -> tuple[bool, list]:
    """The declared line: design mean > 0, validate mean > 0 at t >= t_min, and a
    strict majority of validate years positive."""
    fails = []
    if not ((design.get("mean_monthly") or 0) > 0):
        fails.append("design mean <= 0")
    if not ((validate.get("mean_monthly") or 0) > 0):
        fails.append("validate mean <= 0")
    if not ((validate.get("t_blocks") or 0) >= t_min):
        fails.append(f"validate t < {t_min}")
    yp = validate.get("years_positive") or "0 of 0"
    a, b = (int(x) for x in yp.split(" of "))
    if not (b and a * 2 > b):
        fails.append("validate years positive not a majority")
    return (not fails), fails
