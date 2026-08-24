"""What a NAV series is worth — and what each number is allowed to claim.

THE ORDER IS DELIBERATE. `terminal_usd` first, `sharpe` late. Murat's question
is "if I had handed AEGIS $10,000, what did it actually do?", and a leaderboard
sorted by a risk-adjusted ratio answers a different one. Ratios are here
because drawdown and volatility are real constraints, not because they are the
objective — CLAUDE.md is explicit that the objective is terminal wealth under a
declared utility.

EVERY RATIO NAMES ITS CONVENTION, because the same word means three things in
three libraries:

  * `sharpe` is EXCESS over the risk-free rate from the pinned Fama-French
    file, annualised by sqrt(252). A "Sharpe" computed on raw returns during a
    5% cash era is a different and much friendlier number.
  * `sortino` uses downside deviation about ZERO excess, not about the mean.
  * `max_drawdown` is on the daily CLOSE NAV, so an intraday trough that the
    book never marked is not counted.
  * `turnover_annual` is traded notional over average equity, per year, ONE
    WAY. Doubling it is the round-trip figure; the two conventions differ by 2x
    and are quoted interchangeably in the literature.
"""

from __future__ import annotations

import math

import numpy as np

TRADING_DAYS = 252


def _rf_daily(dates, panel) -> np.ndarray:
    """Daily risk-free from the pinned FF file, NaN where uncovered."""
    try:
        import pandas as pd

        from backend.services.portfolio_farm.panel import FF_DAILY
        if not FF_DAILY.exists():
            return np.zeros(len(dates))
        ff = pd.read_csv(FF_DAILY)
        s = pd.Series(ff["RF"].astype(float).to_numpy(),
                      index=ff["Date"].astype(str).to_numpy())
        s = s[~s.index.duplicated(keep="last")]
        return s.reindex(list(dates)).to_numpy(dtype=float)
    except Exception:                                          # noqa: BLE001
        return np.zeros(len(dates))


def max_drawdown(nav: np.ndarray) -> tuple[float, int]:
    """(depth as a negative fraction, longest underwater run in sessions)."""
    peak, mdd, under, worst_under = -np.inf, 0.0, 0, 0
    for v in nav:
        if not math.isfinite(v):
            continue
        if v >= peak:
            peak, under = v, 0
        else:
            under += 1
            worst_under = max(worst_under, under)
            mdd = min(mdd, v / peak - 1.0)
    return float(mdd), int(worst_under)


def summarise(dates, nav: np.ndarray, panel=None,
              benchmark: np.ndarray | None = None) -> dict:
    """The leaderboard row for one NAV series."""
    nav = np.asarray(nav, dtype=float)
    ok = np.isfinite(nav)
    if ok.sum() < 2:
        return {"status": "no_nav", "terminal_usd": None}
    v = nav[ok]
    r = np.diff(v) / v[:-1]
    n_days = len(v)
    years = n_days / TRADING_DAYS
    total = v[-1] / v[0] - 1.0
    cagr = (v[-1] / v[0]) ** (1.0 / years) - 1.0 if years > 0 else float("nan")

    rf = _rf_daily(list(np.asarray(dates)[ok]), panel)[1:]
    rf = np.where(np.isfinite(rf), rf, 0.0)
    ex = r - rf
    sd = float(np.std(r, ddof=0))
    sd_ex = float(np.std(ex, ddof=0))
    down = ex[ex < 0]
    dd_sd = float(np.sqrt(np.mean(down ** 2))) if down.size else 0.0

    mdd, under = max_drawdown(v)
    out = {
        "status": "ok",
        "terminal_usd": round(float(v[-1]), 2),
        "total_return_pct": round(100.0 * total, 3),
        "cagr_pct": round(100.0 * cagr, 3),
        "vol_annual_pct": round(100.0 * sd * math.sqrt(TRADING_DAYS), 3),
        "sharpe": round(float(np.mean(ex) / sd_ex * math.sqrt(TRADING_DAYS)), 3)
        if sd_ex > 0 else None,
        "sortino": round(float(np.mean(ex) / dd_sd * math.sqrt(TRADING_DAYS)), 3)
        if dd_sd > 0 else None,
        "max_drawdown_pct": round(100.0 * mdd, 3),
        "longest_underwater_sessions": under,
        "calmar": round(float(cagr / abs(mdd)), 3) if mdd < 0 else None,
        "n_sessions": n_days,
        "years": round(years, 2),
        "best_day_pct": round(100.0 * float(r.max()), 3),
        "worst_day_pct": round(100.0 * float(r.min()), 3),
        "pct_days_up": round(100.0 * float((r > 0).mean()), 2),
    }

    if benchmark is not None:
        b = np.asarray(benchmark, dtype=float)[ok][1:]
        b = np.where(np.isfinite(b), b, 0.0)
        bench_terminal = float(v[0] * np.prod(1.0 + b))
        bench_cagr = ((bench_terminal / v[0]) ** (1.0 / years) - 1.0
                      if years > 0 else float("nan"))
        active = r - b
        out.update({
            "benchmark_terminal_usd": round(bench_terminal, 2),
            "benchmark_cagr_pct": round(100.0 * bench_cagr, 3),
            "excess_cagr_pct": round(100.0 * (cagr - bench_cagr), 3),
            "tracking_error_pct": round(
                100.0 * float(np.std(active, ddof=0)) * math.sqrt(TRADING_DAYS),
                3),
            "information_ratio": round(
                float(np.mean(active) / np.std(active, ddof=0)
                      * math.sqrt(TRADING_DAYS)), 3)
            if np.std(active, ddof=0) > 0 else None,
            # The number that decides. Beating the market by 2%/yr with 3x its
            # drawdown is not obviously better, so the pair travels together.
            "beat_benchmark": bool(v[-1] > bench_terminal),
        })
    return out


def turnover_annual(traded_notional_usd: float, avg_equity: float,
                    years: float) -> float:
    """One-way turnover per year. See the module docstring on the 2x."""
    if avg_equity <= 0 or years <= 0:
        return float("nan")
    return round(traded_notional_usd / avg_equity / years, 3)
