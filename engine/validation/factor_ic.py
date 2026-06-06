"""
Factor Information Coefficient (IC) Analysis
=============================================

The core of an Alphalens-style factor validation, computed directly so we
carry no fragile third-party dependency. Answers the only question that
matters for a factor grade: *does it actually predict forward returns?*

A factor's skill is measured by the Information Coefficient — the rank
correlation between the factor value and the subsequent return, computed
cross-sectionally on each date and then summarized across dates:

  - IC (per date)      : Spearman rank corr of factor vs forward return
  - mean IC            : average predictive strength (≈0 = no skill)
  - IC IR              : mean IC / std IC  (information ratio of the signal)
  - IC t-stat          : mean / (std/√n)   (significance across periods)
  - hit rate           : fraction of periods with IC > 0
  - quantile spread    : mean forward return of top minus bottom quantile

Rules of thumb (Grinold/Kahn, Qian et al.): a |mean IC| of 0.02–0.05 with a
t-stat ≥ 2 is a usable equity factor; near-zero IC means the grade is
cosmetic. These are computed on a tidy long panel with columns
[date, asset, <factor>, <forward_return>].

Caveat: if forward windows overlap, the IC t-stat is overstated by serial
correlation — sample on non-overlapping windows, or treat the t-stat as an
upper bound.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

MIN_ASSETS_PER_DATE = 5  # need a cross-section to rank


def cross_sectional_ic(
    factor: pd.Series, fwd_return: pd.Series, method: str = "spearman"
) -> float:
    """Rank correlation between a factor and forward return on one date.

    Returns NaN if fewer than MIN_ASSETS_PER_DATE valid pairs or no variance.
    """
    df = pd.DataFrame({"f": factor, "r": fwd_return}).dropna()
    if len(df) < MIN_ASSETS_PER_DATE:
        return float("nan")
    if df["f"].nunique() < 2 or df["r"].nunique() < 2:
        return float("nan")
    if method == "pearson":
        corr = df["f"].corr(df["r"])
    else:
        corr = df["f"].corr(df["r"], method="spearman")
    return float(corr)


def ic_by_date(
    panel: pd.DataFrame,
    factor_col: str,
    fwd_col: str,
    date_col: str = "date",
    method: str = "spearman",
) -> pd.Series:
    """IC computed independently on each date's cross-section.

    Args:
        panel: long DataFrame with [date, asset, factor, forward_return].
    Returns:
        Series of IC indexed by date (NaN dates dropped).
    """
    ics = {}
    for date, grp in panel.groupby(date_col):
        ic = cross_sectional_ic(grp[factor_col], grp[fwd_col], method=method)
        if not np.isnan(ic):
            ics[date] = ic
    return pd.Series(ics, name="ic").sort_index()


def ic_summary(ic_series: pd.Series) -> dict:
    """Summarize an IC time series into the headline skill statistics."""
    ic = pd.Series(ic_series).dropna()
    n = len(ic)
    if n == 0:
        return {"n_periods": 0, "reason": "no valid IC periods"}

    mean_ic = float(ic.mean())
    std_ic = float(ic.std(ddof=1)) if n > 1 else 0.0
    ir = mean_ic / std_ic if std_ic > 1e-12 else 0.0
    t_stat = ir * np.sqrt(n) if std_ic > 1e-12 else 0.0
    # Two-sided p-value under the t distribution with n-1 dof.
    p_value = float(2 * stats.t.sf(abs(t_stat), df=max(n - 1, 1))) if n > 1 else 1.0
    hit_rate = float((ic > 0).mean())

    return {
        "n_periods": n,
        "mean_ic": round(mean_ic, 4),
        "ic_std": round(std_ic, 4),
        "ic_ir": round(float(ir), 4),
        "t_stat": round(float(t_stat), 3),
        "p_value": round(p_value, 4),
        "hit_rate": round(hit_rate, 3),
        "verdict": _ic_verdict(mean_ic, t_stat),
    }


def _ic_verdict(mean_ic: float, t_stat: float) -> str:
    """Plain-language read of whether the factor has usable skill."""
    if abs(mean_ic) < 0.01 or abs(t_stat) < 2.0:
        return "no measurable skill"
    if abs(mean_ic) < 0.03:
        return "weak but significant"
    return "usable signal"


def quantile_return_spread(
    panel: pd.DataFrame,
    factor_col: str,
    fwd_col: str,
    date_col: str = "date",
    n_quantiles: int = 5,
) -> dict:
    """Mean forward return per factor quantile, plus top-minus-bottom spread.

    Bucketed within each date's cross-section (so it is regime-neutral), then
    averaged across dates. A monotonically increasing profile with a positive
    top-minus-bottom spread is the visual signature of a real factor.
    """
    rows = []
    for date, grp in panel.groupby(date_col):
        g = grp[[factor_col, fwd_col]].dropna()
        if len(g) < n_quantiles:
            continue
        try:
            q = pd.qcut(g[factor_col].rank(method="first"), n_quantiles, labels=False)
        except ValueError:
            continue
        g = g.assign(_q=q)
        rows.append(g.groupby("_q")[fwd_col].mean())

    if not rows:
        return {"available": False, "reason": "insufficient cross-sections"}

    by_q = pd.DataFrame(rows).mean()  # average each quantile's mean across dates
    means = {int(k): round(float(v), 5) for k, v in by_q.items()}
    top, bottom = by_q.index.max(), by_q.index.min()
    spread = float(by_q.loc[top] - by_q.loc[bottom])
    monotonic = bool(by_q.is_monotonic_increasing)

    return {
        "available": True,
        "n_quantiles": n_quantiles,
        "quantile_mean_fwd_return": means,
        "top_minus_bottom": round(spread, 5),
        "monotonic_increasing": monotonic,
    }


def analyze_factor(
    panel: pd.DataFrame,
    factor_col: str,
    fwd_col: str,
    date_col: str = "date",
    n_quantiles: int = 5,
) -> dict:
    """Full IC + quantile report for one factor on a long panel."""
    ic = ic_by_date(panel, factor_col, fwd_col, date_col=date_col)
    summary = ic_summary(ic)
    spread = quantile_return_spread(
        panel, factor_col, fwd_col, date_col=date_col, n_quantiles=n_quantiles
    )
    return {"factor": factor_col, "ic": summary, "quantiles": spread}
