"""
Momentum Factor Validation (OFFLINE RESEARCH TOOL)
===================================================

Answers: does the momentum grade in `factor_grades.py` actually predict
forward returns? Momentum is the one of the five graded factors that is
purely price-derived, so it can be reconstructed historically with no
look-ahead and validated rigorously (the four fundamental factors would
need a point-in-time fundamentals panel — see docs/FACTOR_VALIDATION.md).

It reconstructs, on a grid of non-overlapping monthly rebalance dates:

  - `composite` : the EXACT factor used by the grade today — a weighted
                  blend of 1M/3M/6M/12M trailing returns
                  (weights 0.10/0.25/0.35/0.30, from cross_sectional_momentum)
  - `mom_12_1`  : textbook Jegadeesh-Titman momentum — the 12-month return
                  that SKIPS the most recent month (short-term reversal)

and measures each against the forward `fwd_days` return via the IC tools in
`factor_ic.py`. If 12-1 beats the composite, the honest fix is to drop/reduce
the 1M weight in the composite.

Not exposed via the API. Run from the repo root:
    python -m engine.validation.validate_momentum
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from engine.validation.factor_ic import analyze_factor

# Same lookback windows + weights the live grade uses.
_TRADING_DAYS = {"1M": 21, "3M": 63, "6M": 126, "12M": 252}
_WEIGHTS = {"1M": 0.10, "3M": 0.25, "6M": 0.35, "12M": 0.30}


def _universe() -> list[str]:
    from backend.config import config
    u = config.get("stock_universe", {})
    tickers = set(u.get("default_watchlist", []))
    for s in (u.get("sector_stocks", {}) or {}).values():
        tickers.update(s)
    return sorted(tickers)


def _download(tickers: list[str], years: int) -> pd.DataFrame:
    import yfinance as yf
    data = yf.download(tickers, period=f"{years}y", auto_adjust=True,
                       progress=False, threads=True)
    if data.empty:
        return pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        return data["Close"]
    return pd.DataFrame({tickers[0]: data["Close"]})


def build_panel(prices: pd.DataFrame, fwd_days: int = 21,
                step_days: int = 21) -> pd.DataFrame:
    """Reconstruct the momentum factors + forward returns with no look-ahead."""
    idx = prices.index
    n = len(idx)
    start = max(_TRADING_DAYS.values())          # need 12M of history
    rows = []
    for i in range(start, n - fwd_days, step_days):
        date = idx[i]
        for ticker in prices.columns:
            col = prices[ticker].values
            p_now = col[i]
            p_fwd = col[i + fwd_days]
            if not (np.isfinite(p_now) and np.isfinite(p_fwd)) or p_now <= 0:
                continue

            # Composite: weighted blend of available trailing windows.
            comp, tw = 0.0, 0.0
            for period, d in _TRADING_DAYS.items():
                p_past = col[i - d]
                if np.isfinite(p_past) and p_past > 0:
                    comp += _WEIGHTS[period] * (p_now / p_past - 1.0)
                    tw += _WEIGHTS[period]
            if tw <= 0:
                continue
            comp /= tw

            # 12-1 momentum: t-252 → t-21 (skip the most recent month).
            p_12, p_1 = col[i - 252], col[i - 21]
            mom_12_1 = (p_1 / p_12 - 1.0) if (np.isfinite(p_12) and np.isfinite(p_1)
                                              and p_12 > 0) else np.nan

            rows.append({
                "date": date, "asset": ticker,
                "composite": comp, "mom_12_1": mom_12_1,
                "fwd": p_fwd / p_now - 1.0,
            })
    return pd.DataFrame(rows)


def run_momentum_validation(years: int = 6, fwd_days: int = 21,
                            step_days: int = 21) -> dict:
    tickers = _universe()
    prices = _download(tickers, years)
    if prices.empty:
        return {"error": "no price data"}

    panel = build_panel(prices, fwd_days=fwd_days, step_days=step_days)
    if panel.empty:
        return {"error": "empty panel"}

    return {
        "config": {
            "universe_size": len(tickers),
            "years": years,
            "fwd_days": fwd_days,
            "step_days": step_days,
            "non_overlapping": step_days >= fwd_days,
            "rebalance_dates": int(panel["date"].nunique()),
            "observations": int(len(panel)),
        },
        "composite_current_grade": analyze_factor(panel, "composite", "fwd"),
        "mom_12_1_textbook": analyze_factor(panel, "mom_12_1", "fwd"),
    }


if __name__ == "__main__":
    report = run_momentum_validation()
    print(json.dumps(report, indent=2, default=str))
