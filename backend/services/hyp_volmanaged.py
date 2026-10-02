"""Volatility-managed market exposure with the engine's size forecast (hypothesis lab, 2026-09-30).

The afternoon of 2026-09-29 showed the stock-level size forecast does not help STOCK
sizing. This module asks the book-level question: hold the market, and set exposure
each period to target / forecast volatility. Does a better volatility forecast --
trailing realised variance, a HAR model fitted on the design window, and HAR plus the
earnings-season intensity (share of market value EXPECTED to report inside the hold
window, from each firm's report date a year earlier: known beforehand) -- raise log
utility or cut drawdown versus buy-and-hold at the SAME average exposure, net of costs?

Pure, offline pieces; the runner is `scripts/hyp_volmanaged.py`; tests in
`backend/tests/test_hyp_volmanaged.py`.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd

TRADE_COST = 0.0002          # per unit of |change in exposure| (index future, incl. slippage)
LEVER_SPREAD_ANNUAL = 0.005  # financing spread over rf on exposure above 1
MAX_EXPOSURE = 2.0
TD_YEAR = 252


def realised_features(r: pd.Series) -> pd.DataFrame:
    """Per day t, from returns up to AND including t (known at t's close): daily variance
    averages over 1, 5, 22 and 63 sessions."""
    r2 = pd.Series(r, dtype=float) ** 2
    return pd.DataFrame({"rv1": r2, "rv5": r2.rolling(5).mean(), "rv22": r2.rolling(22).mean(),
                         "rv63": r2.rolling(63).mean()})


def future_var(r: pd.Series, h: int) -> pd.Series:
    """Mean daily squared return over t+1 .. t+h (the TARGET; never a feature)."""
    r2 = pd.Series(r, dtype=float) ** 2
    return r2[::-1].rolling(h).mean()[::-1].shift(-1)


def decision_days(idx: pd.DatetimeIndex, freq: str) -> pd.DatetimeIndex:
    """Last session of each month ('M') or every 5th session ('W')."""
    idx = pd.DatetimeIndex(idx)
    if freq == "M":
        s = pd.Series(idx, index=idx)
        return pd.DatetimeIndex(s.groupby(idx.to_period("M")).max().to_numpy())
    if freq == "W":
        return idx[::5]
    raise ValueError(freq)


def fit_har(X: pd.DataFrame, y: pd.Series, cols: list) -> dict:
    """OLS of log(y) on log(features) [+ raw extras]; returns coefficients and residual var."""
    Z = pd.DataFrame({c: (np.log(X[c]) if c.startswith("rv") else X[c]) for c in cols})
    Z = Z.replace([np.inf, -np.inf], np.nan)
    ly = np.log(y.replace(0, np.nan))
    ok = Z.notna().all(axis=1) & ly.notna()
    A = np.column_stack([np.ones(int(ok.sum()))] + [Z.loc[ok, c].to_numpy() for c in cols])
    b, *_ = np.linalg.lstsq(A, ly[ok].to_numpy(), rcond=None)
    res = ly[ok].to_numpy() - A @ b
    return {"cols": cols, "coef": b.tolist(), "resid_var": float(res.var(ddof=A.shape[1])), "n": int(ok.sum())}


def predict_har(model: dict, X: pd.DataFrame) -> pd.Series:
    cols = model["cols"]
    Z = pd.DataFrame({c: (np.log(X[c]) if c.startswith("rv") else X[c]) for c in cols}).replace(
        [np.inf, -np.inf], np.nan)
    b = np.asarray(model["coef"])
    lf = b[0] + sum(b[i + 1] * Z[c] for i, c in enumerate(cols))
    return np.exp(lf + 0.5 * model["resid_var"])


def exposures(sigma_hat: pd.Series, c: float, cap: float = MAX_EXPOSURE) -> pd.Series:
    """Vol targeting: w = c / sigma_hat, clipped to [0, cap]."""
    return (c / sigma_hat).clip(lower=0.0, upper=cap)


def scale_for_mean_exposure(sigma_hat: pd.Series, target_mean: float = 1.0, cap: float = MAX_EXPOSURE) -> float:
    """The constant c such that mean(clip(c / sigma_hat)) = target_mean on the given (design) dates."""
    s = sigma_hat.dropna()
    lo, hi = 0.0, float(s.max() * cap * 10 + 1e-9)
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if exposures(s, mid, cap).mean() < target_mean:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def policy_returns(r: pd.Series, rf: pd.Series, w_dec: pd.Series) -> pd.DataFrame:
    """Daily returns of: rf + w (r - rf) - costs, with w set at each decision day's close
    and held from the next session; cost TRADE_COST x |dw| on the day the change takes
    effect, financing LEVER_SPREAD_ANNUAL / 252 x max(w - 1, 0) per day."""
    w = w_dec.reindex(r.index).ffill().shift(1)
    dw = w.diff().abs().fillna(w.abs())
    ex = r - rf
    cost = TRADE_COST * dw.fillna(0.0) + LEVER_SPREAD_ANNUAL / TD_YEAR * (w - 1.0).clip(lower=0.0).fillna(0.0)
    ret = rf + w * ex - cost
    return pd.DataFrame({"w": w, "ret": ret, "cost": cost, "ex": ex, "rf": rf}).dropna(subset=["w"])


def window_days(df: pd.DataFrame, lo: Optional[str], hi: Optional[str]) -> pd.DataFrame:
    m = np.ones(len(df), dtype=bool)
    if lo:
        m &= df.index >= pd.Timestamp(lo)
    if hi:
        m &= df.index <= pd.Timestamp(hi)
    return df[m]


def compare(pol: pd.DataFrame, lo: Optional[str], hi: Optional[str]) -> dict:
    """The policy vs buy-and-hold at the SAME average exposure over the window (and at
    matched realised vol, reported beside). Monthly log-return differences carry the t."""
    d = window_days(pol, lo, hi)
    if len(d) < 60:
        return {"n_days": int(len(d))}
    ebar = float(d["w"].mean())
    bench = d["rf"] + ebar * d["ex"]
    vol_p, vol_m = float(d["ret"].std()), float(d["ex"].std())
    k = vol_p / vol_m if vol_m > 0 else np.nan
    bench_v = d["rf"] + k * d["ex"]
    lp, lb, lv = np.log1p(d["ret"]), np.log1p(bench), np.log1p(bench_v)
    mon = pd.DataFrame({"p": lp, "b": lb, "v": lv}).groupby(d.index.to_period("M")).sum()
    diff = mon["p"] - mon["b"]
    n = len(diff)
    blk = np.arange(n) // 3
    sums = diff.groupby(blk).sum()
    se = float(sums.std(ddof=1) / math.sqrt(len(sums))) if len(sums) > 2 else np.nan
    t = float(sums.mean() / se) if se and se > 0 else None
    yrs = diff.groupby(diff.index.year).sum()

    def mdd(x: pd.Series) -> float:
        nav = np.exp(x.cumsum())
        return float((nav / nav.cummax() - 1).min())

    def sharpe(x: pd.Series) -> float:
        e = x - d["rf"]
        return float(e.mean() / e.std() * math.sqrt(TD_YEAR)) if e.std() > 0 else np.nan

    return {"n_days": int(len(d)), "mean_exposure": ebar, "exposure_sd": float(d["w"].std()),
            "log_util_per_month_policy": float(mon["p"].mean()), "log_util_per_month_bench": float(mon["b"].mean()),
            "diff_log_per_month": float(diff.mean()), "t_blocks": t,
            "mde_per_month": 2.8 * se / 3 if se == se else None,
            "diff_vs_matched_vol_per_month": float((mon["p"] - mon["v"]).mean()),
            "terminal_wealth_policy": float(np.exp(lp.sum())), "terminal_wealth_bench": float(np.exp(lb.sum())),
            "terminal_wealth_bench_matched_vol": float(np.exp(lv.sum())),
            "sharpe_policy": sharpe(d["ret"]), "sharpe_bench": sharpe(bench),
            "max_dd_policy": mdd(lp), "max_dd_bench": mdd(lb), "max_dd_bench_matched_vol": mdd(lv),
            "cost_per_year": float(d["cost"].mean() * TD_YEAR),
            "years_positive": f"{int((yrs > 0).sum())} of {len(yrs)}",
            "by_year": {str(k_): round(float(v), 5) for k_, v in yrs.items()}}


def qlike(var_hat: pd.Series, var_real: pd.Series) -> float:
    """Mean QLIKE loss (lower is better) on dates where both exist."""
    j = pd.concat([var_hat, var_real], axis=1).dropna()
    j = j[(j.iloc[:, 0] > 0) & (j.iloc[:, 1] > 0)]
    ratio = j.iloc[:, 1] / j.iloc[:, 0]
    return float((ratio - np.log(ratio) - 1).mean()) if len(j) else float("nan")
