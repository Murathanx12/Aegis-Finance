"""Analyst revision flow as a TILT on a market-like base, not as a book (2026-09-29).

Pure, offline functions. The caller is `scripts/revision_tilt_on_crsp.py`.

WHY: revision flow beat its matched twin in 1991-2008, 2009-2016 and 2017-2024,
but as a stand-alone book it lost to the market net of spreads, because the twin
universe itself trails the market and the book turns over 44-95% a month
(`docs/research_notes/2026-09-29/analyst_insider_on_crsp_2026-09-29.md`). A
relative signal belongs on top of a base that already tracks the market.

CONSTRUCTION (every step uses only columns dated on or before the decision date):

1. `base_weights`: the top `n` names by trailing median dollar volume (rank, not
   a nominal floor) among eligible names; cap weight (shares x |price|) or equal.
2. `signal_score`: net raises, revision breadth (net raises / distinct brokers),
   or the rank-average of the announcement return and net raises. Missing -> 0.
3. `target_active`: cross-sectional ranks mapped to [-1, 1], de-meaned within
   sector when sectors are given, times a scale found by bisection so that the
   active share (0.5 * sum |a|) hits its target; each active weight is clipped
   to [-min(base weight, cap), +cap] (long-only, per-name cap both ways), then balanced within each
   sector so every sector's active sum is zero.
4. `step_active`: a no-trade band on each name's active weight, then a turnover
   budget on the active trades (a partial step toward the target), then a
   projection so the active weights sum to zero with every cap kept.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

SIGNALS = ("net_raises", "breadth", "ear_flow")


def base_weights(dollar_vol: np.ndarray, eligible: np.ndarray, mcap: Optional[np.ndarray], *,
                 n: int = 500, scheme: str = "cap", rank_lo: int = 0) -> np.ndarray:
    """Weights over the input rows: eligible names ranked `rank_lo+1 .. rank_lo+n` by
    dollar volume, cap- or equal-weighted. `rank_lo=0` (default) is the top-`n` base
    exactly as before; `rank_lo=500, n=1000` is ranks 501-1500 (added 2026-09-29)."""
    if rank_lo < 0:
        raise ValueError("rank_lo must be >= 0")
    dv = np.where(eligible & np.isfinite(dollar_vol), dollar_vol, -np.inf)
    order = np.argsort(-dv, kind="stable")
    n_fin = int(np.isfinite(dv).sum())
    k = int(max(0, min(n, n_fin - rank_lo)))
    pick = order[rank_lo:rank_lo + k]
    w = np.zeros(len(dv))
    if k == 0:
        return w
    if scheme == "equal":
        w[pick] = 1.0 / k
        return w
    if scheme != "cap":
        raise ValueError(f"scheme must be cap or equal, got {scheme}")
    if mcap is None:
        raise ValueError("cap weighting needs mcap")
    m = np.asarray(mcap, dtype=float)[pick]
    fill = np.nanmedian(m) if np.isfinite(m).any() else 1.0
    m = np.where(np.isfinite(m) & (m > 0), m, fill)
    w[pick] = m / m.sum()
    return w


def _rank_pm1(x: np.ndarray) -> np.ndarray:
    """Ranks of the finite entries mapped to [-1, 1]; non-finite -> 0 (no view)."""
    out = np.zeros(len(x))
    f = np.isfinite(x)
    if f.sum() < 2:
        return out
    r = pd.Series(x[f]).rank(method="average").to_numpy()
    out[f] = 2.0 * (r - 1.0) / (f.sum() - 1.0) - 1.0
    return out


def signal_score(df: pd.DataFrame, signal: str) -> np.ndarray:
    """A higher score = more positive revision flow. NaN where the name has no view."""
    nr = pd.to_numeric(df["net_raises"], errors="coerce").to_numpy(dtype=float)
    if signal == "net_raises":
        return nr
    if signal == "breadth":
        nf = pd.to_numeric(df["n_firms"], errors="coerce").to_numpy(dtype=float)
        return np.where(np.isfinite(nr) & (nf > 0), nr / np.where(nf > 0, nf, 1.0), np.nan)
    if signal == "ear_flow":
        ea = pd.to_numeric(df["ear_last"], errors="coerce").to_numpy(dtype=float)
        a, b = _rank_pm1(ea), _rank_pm1(nr)
        fa, fb = np.isfinite(ea), np.isfinite(nr)
        n = fa.astype(float) + fb.astype(float)
        return np.where(n > 0, (np.where(fa, a, 0) + np.where(fb, b, 0)) / np.where(n > 0, n, 1), np.nan)
    raise ValueError(f"signal must be one of {SIGNALS}")


def _balance_by_group(a: np.ndarray, groups: np.ndarray) -> np.ndarray:
    """Scale the larger side of each group down so the group's active sum is zero."""
    a = a.copy()
    for g in np.unique(groups):
        m = groups == g
        pos, neg = a[m & (a > 0)].sum(), -a[m & (a < 0)].sum()
        if pos <= 0 or neg <= 0:
            a[m] = 0.0
            continue
        if pos > neg:
            a[m & (a > 0)] *= neg / pos
        else:
            a[m & (a < 0)] *= pos / neg
    return a


def _active_at(scale: float, z: np.ndarray, base: np.ndarray, cap: float, groups: np.ndarray) -> np.ndarray:
    a = np.clip(scale * z, -np.minimum(base, cap), cap)
    return _balance_by_group(a, groups)


def target_active(score: np.ndarray, base: np.ndarray, *, active_share: float, cap: float,
                  sector: Optional[np.ndarray] = None, iters: int = 40) -> np.ndarray:
    """Active weights over the base's names (zero outside it), sum zero, |a| within caps."""
    inb = base > 0
    z = np.zeros(len(base))
    s = np.where(inb, score, np.nan)
    if sector is not None:
        sec = np.asarray(sector, dtype=float)
        sec = np.where(np.isfinite(sec), sec, -1.0)
        for g in np.unique(sec[inb]):
            m = inb & (sec == g)
            z[m] = _rank_pm1(s[m])
            fin = m & np.isfinite(s)
            if fin.sum() > 1:
                z[fin] -= z[fin].mean()
        groups = np.where(inb, sec, -2.0)
    else:
        z[inb] = _rank_pm1(s[inb])
        fin = inb & np.isfinite(s)
        if fin.sum() > 1:
            z[fin] -= z[fin].mean()
        groups = np.where(inb, 0.0, -2.0)
    if not np.any(z != 0):
        return np.zeros(len(base))
    lo, hi = 0.0, 1.0
    while 0.5 * np.abs(_active_at(hi, z, base, cap, groups)).sum() < active_share and hi < 1e4:
        hi *= 2.0
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        if 0.5 * np.abs(_active_at(mid, z, base, cap, groups)).sum() < active_share:
            lo = mid
        else:
            hi = mid
    return _active_at(lo, z, base, cap, groups)


def _project_zero_sum(a: np.ndarray, base: np.ndarray, cap: float) -> np.ndarray:
    """Make sum(a) == 0 by moving positive actives toward zero (r > 0) or negative
    actives toward zero (r < 0), pro rata. Keeps -min(base, cap) <= a <= cap."""
    a = np.clip(a, -np.minimum(base, cap), cap)
    r = a.sum()
    if r > 0:
        p = a > 0
        tot = a[p].sum()
        if tot > 0:
            a[p] -= a[p] * min(1.0, r / tot)
    elif r < 0:
        q = a < 0
        tot = -a[q].sum()
        if tot > 0:
            a[q] += (-a[q]) * min(1.0, -r / tot)
    return a


def step_active(a_prev: np.ndarray, a_target: np.ndarray, base: np.ndarray, *, cap: float, band: float,
                budget: float) -> tuple[np.ndarray, float]:
    """One monthly rebalance of the ACTIVE weights. `a_prev` is the drifted book
    minus the current base (outside the base the name must go: its active is -held,
    so it is traded to zero regardless of the band). The budget binds the banded move; the zero-sum
    projection after it can add a little, so the MEASURED active turnover is returned and reported.
    Returns (new active, measured active turnover over base names)."""
    inb = base > 0
    a_prev = np.where(inb, np.clip(a_prev, -np.minimum(base, cap), cap), 0.0)
    move = a_target - a_prev
    move = np.where(inb & (np.abs(move) < band), 0.0, move)
    turn = 0.5 * np.abs(move).sum()
    if turn > budget > 0:
        move *= budget / turn
    a = _project_zero_sum(np.where(inb, a_prev + move, 0.0), base, cap)
    return a, float(0.5 * np.abs(a - a_prev).sum())


def drift(w: np.ndarray, r: np.ndarray) -> np.ndarray:
    """Weights after one period's returns (NaN return -> 0, counted by the caller)."""
    rr = np.where(np.isfinite(r), r, 0.0)
    v = w * (1.0 + rr)
    s = v.sum()
    return v / s if s > 0 else w


def max_drawdown(r: pd.Series) -> float:
    """Max drawdown of the compounded series (active returns compound like a long-short)."""
    x = (1.0 + pd.Series(r).fillna(0.0)).cumprod()
    return float((x / x.cummax() - 1.0).min()) if len(x) else float("nan")


def kill_line(sd_monthly: float, months: float, *, z: float = 1.645) -> dict:
    """One-sided kill line on the cumulative active return over `months`, with
    false-kill rate under zero edge and P(kill) under a given true edge."""
    from scipy.stats import norm                                      # noqa: PLC0415
    sd = sd_monthly * np.sqrt(months)
    line = -z * sd
    out = {"sd_horizon": float(sd), "kill_at": float(line), "false_kill_rate": float(norm.cdf(-z))}
    for edge in (0.001, 0.0025, 0.005, -0.005, -0.01):
        out[f"p_kill_if_true_{edge*100:+.2f}pct_mo"] = float(norm.cdf((line - edge * months) / sd))
    out["true_gap_for_50pct_power_monthly"] = float(line / months)
    return out
