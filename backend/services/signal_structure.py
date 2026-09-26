"""Signal structure of the strategy library: how many DISTINCT bets, and what they load on.

Licence: PRODUCT_EXPERIMENT diagnostics ($0, no LLM). Every number is HINDSIGHT:
the library's rules were written on 2026-09-26, after every month scored here.

Three questions (Reviewer D+E idea #1, `docs/reviews/REVIEW_2026-09-26_CHUNKS_D_E.md`):

1. **How many bets?** 849 cells are not 849 independent trials. The monthly
   ACTIVE returns (rule net - SPY) are correlated; average-linkage clustering on
   1 - rho with a cut at rho = 0.8 counts the distinct bets. That count is the
   honest multiplicity denominator beside the nominal one.
2. **What do they load on?** The 2024-26 window rewarded semiconductors and
   momentum. Regressing each rule's monthly active return on ETF spreads
   (SMH, IWM, MTUM, USMV, QUAL, VLUE, each minus SPY) says how much of a rule's
   excess is a sector/style beta anyone could buy for 0.35%/yr.
3. **Does anything lead anything?** Cross-correlation of each cluster
   representative with the library's own momentum and with SMH - SPY at lags
   0, +1, +2 months. Output is HYPOTHESIS only.

The series source is the factory checkpoint of a VALID run: each cell carries
`active_returns` (net - SPY, one per month, no gaps when
`n_months_without_spy == 0`) and its `span`. Net is reconstructed as
active + SPY over the same (month-end, next month-end] period, with SPY from the
same yfinance adjusted-close leg the factory used; the reconstruction is
checked against the checkpoint's own `by_year` net and the gap is printed.
"""
from __future__ import annotations

import math
from typing import Iterable, Optional

import numpy as np
import pandas as pd

RHO_CUT = 0.8
MIN_MONTHS = 12                  # the receipt refuses below this
MIN_PAIR_MONTHS = 24             # pairwise-complete correlation floor per window
ETF_TICKERS = ("SPY", "QQQ", "IWM", "SMH", "USMV", "MTUM", "VLUE", "QUAL")
FACTOR_SPREADS = ("SMH", "IWM", "MTUM", "USMV", "QUAL", "VLUE")   # each minus SPY
LEAD_LAGS = (0, 1, 2)
LEAD_LAG_RHO = 0.3


class InsufficientHistory(RuntimeError):
    """Fewer than MIN_MONTHS monthly observations: the receipt refuses."""


# ── series ──────────────────────────────────────────────────────────────────

def month_end_sessions(daily_index: Iterable) -> pd.DatetimeIndex:
    """The last session of every calendar month in a daily index."""
    idx = pd.DatetimeIndex(sorted(pd.DatetimeIndex(daily_index).unique()))
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    s = pd.Series(idx, index=idx)
    return pd.DatetimeIndex(s.groupby(idx.to_period("M")).max().to_numpy())


def period_returns(daily: pd.Series, decision_dates: pd.DatetimeIndex) -> pd.Series:
    """Daily simple returns compounded over (d_i, d_{i+1}], indexed by d_i.

    Identical to `night_backtest_factory.spy_leg`'s canonical construction, so an
    ETF spread lines up with the factory's SPY leg period for period."""
    r = daily.copy()
    r.index = pd.DatetimeIndex(r.index)
    if getattr(r.index, "tz", None) is not None:
        r.index = r.index.tz_localize(None)
    r = r.sort_index()
    vals = {}
    arr, ix = r.to_numpy(dtype=float), r.index
    for a, z in zip(decision_dates[:-1], decision_dates[1:]):
        lo, hi = ix.searchsorted(a, side="right"), ix.searchsorted(z, side="right")
        seg = arr[lo:hi]
        seg = seg[np.isfinite(seg)]
        vals[a] = float(np.prod(1.0 + seg) - 1.0) if len(seg) else np.nan
    return pd.Series(vals, dtype=float)


def cell_id(rule_id: str, k) -> str:
    return f"{rule_id}@k{int(k)}"


def cells_from_checkpoint(done: dict) -> tuple[dict, list]:
    """{cell_id: {rule, k, family, control, primary, hold_months, span, active}}.

    Returns (cells, refused) where refused lists (cell_id, why)."""
    cells, refused = {}, []
    for rid, res in done.items():
        if res.get("status") != "OK":
            refused.append((rid, res.get("why", "rule refused")))
            continue
        meta = res.get("meta") or {}
        for k, c in (res.get("cells") or {}).items():
            cid = cell_id(rid, k)
            if c.get("status") != "OK":
                refused.append((cid, c.get("why", "cell refused")))
                continue
            if int(c.get("n_months_without_spy") or 0) != 0:
                refused.append((cid, "months without SPY: active_returns has gaps, dates not recoverable"))
                continue
            a = list(c.get("active_returns") or [])
            if len(a) != int(c.get("n_months") or -1):
                refused.append((cid, f"{len(a)} active returns vs n_months {c.get('n_months')}"))
                continue
            cells[cid] = {"rule": rid, "k": int(k), "family": meta.get("family"),
                          "control": bool(meta.get("control")),
                          "primary": str(k) == str(res.get("primary_k", meta.get("k"))),
                          "hold_months": int(meta.get("hold_months") or 1),
                          "span": list(c.get("span") or []), "active": a,
                          "by_year": c.get("by_year") or {}}
    return cells, refused


def active_frame(cells: dict, decision_dates: pd.DatetimeIndex) -> tuple[pd.DataFrame, list]:
    """date x cell of monthly ACTIVE returns, placed on the decision-date grid."""
    dd = pd.DatetimeIndex(decision_dates)
    pos = {d: i for i, d in enumerate(dd)}
    cols, refused = {}, []
    for cid, c in cells.items():
        s0, s1 = (pd.Timestamp(x) for x in c["span"])
        i0 = pos.get(s0)
        n = len(c["active"])
        if i0 is None or i0 + n > len(dd) or dd[i0 + n - 1] != s1:
            refused.append((cid, f"span {c['span']} with {n} months does not sit on the month-end grid"))
            continue
        cols[cid] = pd.Series(c["active"], index=dd[i0:i0 + n], dtype=float)
    frame = pd.DataFrame(cols).reindex(dd)
    return frame, refused


def reconstruction_gap(cells: dict, net: pd.DataFrame) -> dict:
    """max |compounded net by year (reconstructed) - checkpoint by_year net|."""
    worst, n = 0.0, 0
    for cid in net.columns:
        by = cells[cid]["by_year"]
        s = net[cid].dropna()
        for y, g in s.groupby(s.index.year):
            ref = (by.get(str(y)) or {}).get("net")
            if ref is None:
                continue
            gap = abs(float(np.prod(1.0 + g) - 1.0) - float(ref))
            worst = max(worst, gap)
            n += 1
    return {"max_abs_gap_by_year": worst, "n_year_cells_compared": n}


# ── windows ─────────────────────────────────────────────────────────────────

def window_masks(index: pd.DatetimeIndex) -> dict:
    """dev / sealed masks by ENTRY session, the factory's own split."""
    from backend.services import strategy_library as SL
    w = SL.split_windows(index)
    return {"dev": w["dev"], "sealed": w["sealed"]}


# ── correlation + clustering ────────────────────────────────────────────────

def corr_matrix(active: pd.DataFrame, *, min_periods: int = MIN_PAIR_MONTHS) -> pd.DataFrame:
    """Pairwise-complete Pearson correlation; columns with < min_periods months dropped."""
    keep = [c for c in active.columns if active[c].notna().sum() >= min_periods]
    return active[keep].corr(min_periods=min_periods)


def cluster(corr: pd.DataFrame, *, rho_cut: float = RHO_CUT) -> pd.Series:
    """Average-linkage clusters on distance 1 - rho, cut at distance 1 - rho_cut.

    A pair without enough overlap (NaN rho) is treated as uncorrelated
    (distance 1) -- it can only split clusters, never merge them."""
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform
    names = list(corr.columns)
    if len(names) == 0:
        return pd.Series(dtype=int)
    if len(names) == 1:
        return pd.Series([1], index=names)
    d = 1.0 - corr.to_numpy(dtype=float)
    d = np.where(np.isfinite(d), d, 1.0)
    d = np.clip((d + d.T) / 2.0, 0.0, 2.0)
    np.fill_diagonal(d, 0.0)
    z = linkage(squareform(d, checks=False), method="average")
    lab = fcluster(z, t=1.0 - rho_cut, criterion="distance")
    return pd.Series(lab, index=names)


# ── regression ──────────────────────────────────────────────────────────────

def ols(y: pd.Series, X: pd.DataFrame) -> dict:
    """OLS with intercept: alpha, t(alpha), betas, t(betas), R^2, n.

    Refuses (InsufficientHistory) below MIN_MONTHS or with too few degrees of
    freedom. Plain OLS standard errors: the monthly blocks do not overlap for a
    hold-1 rule; for hold > 1 they understate the SE and the caller says so."""
    df = pd.concat([y.rename("__y"), X], axis=1).dropna()
    n, p = len(df), X.shape[1] + 1
    if n < MIN_MONTHS or n - p < 3:
        raise InsufficientHistory(f"{n} months for {p} parameters (need >= {MIN_MONTHS} and n - p >= 3)")
    Y = df["__y"].to_numpy(dtype=float)
    A = np.column_stack([np.ones(n), df[X.columns].to_numpy(dtype=float)])
    coef, *_ = np.linalg.lstsq(A, Y, rcond=None)
    resid = Y - A @ coef
    dof = n - p
    s2 = float(resid @ resid) / dof
    cov = s2 * np.linalg.pinv(A.T @ A)
    se = np.sqrt(np.clip(np.diag(cov), 0, None))
    tss = float(((Y - Y.mean()) ** 2).sum())
    r2 = 1.0 - float(resid @ resid) / tss if tss > 0 else float("nan")
    t = np.where(se > 0, coef / np.where(se > 0, se, 1), np.nan)
    means = df[X.columns].mean()
    contrib = {c: float(coef[i + 1] * means[c]) for i, c in enumerate(X.columns)}
    return {"n": int(n), "alpha_monthly": float(coef[0]), "t_alpha": float(t[0]),
            "betas": {c: float(coef[i + 1]) for i, c in enumerate(X.columns)},
            "t_betas": {c: float(t[i + 1]) for i, c in enumerate(X.columns)},
            "r2": float(r2), "mean_active_monthly": float(Y.mean()),
            "contribution_monthly": contrib}


def factor_spreads(etf: pd.DataFrame, spreads: Iterable[str] = FACTOR_SPREADS) -> pd.DataFrame:
    return pd.DataFrame({f"{t}-SPY": etf[t] - etf["SPY"] for t in spreads})


# ── lead-lag ────────────────────────────────────────────────────────────────

def lagged_corr(y: pd.Series, x: pd.Series, lag: int) -> tuple[float, int]:
    """corr(y_t, x_{t-lag}): lag > 0 means x LEADS y by `lag` months."""
    df = pd.concat([y.rename("y"), x.shift(lag).rename("x")], axis=1).dropna()
    if len(df) < MIN_MONTHS or df["y"].std() == 0 or df["x"].std() == 0:
        return float("nan"), int(len(df))
    return float(df["y"].corr(df["x"])), int(len(df))


def require_months(n: int, what: str = "series") -> None:
    if n < MIN_MONTHS:
        raise InsufficientHistory(f"{what}: {n} months < {MIN_MONTHS}; the receipt refuses")


def dsr_at(active: Iterable[float], n_trials: int) -> Optional[float]:
    from learner.inference import deflated_sharpe
    d = deflated_sharpe(list(active), n_trials=int(n_trials))
    v = d.get("dsr")
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)
