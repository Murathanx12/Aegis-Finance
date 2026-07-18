"""
Local lane-mandate replay, 2015 -> today — the SAME spec as the QuantConnect
algorithm (engine/research/quantconnect/aegis_lane_mandates.py), run on
yfinance adjusted closes so we have numbers without waiting for the cloud.

Why this is survivorship-safe when the T7 stock backtests were not: the
sleeves hold only broad/bond/alt ETFs and every one of them is alive today —
there is no delisted-member hole to fall into. (The individual-stock
universe stays out for exactly that reason; see the QC file header.)

DIRECTION-CHECK, NOT THE TRACK RECORD (docs/research/
QUANTCONNECT_REPLAY_2026-07-18.md). Pre-committed reading: a diversified
mandate in the 2015-2026 US bull market is EXPECTED to trail SPY with a
smaller drawdown. One run per lane, zero parameter search -> no DSR/PBO
deflation is owed (nothing was selected); any future variant-tinkering here
counts as trials and must be logged.

    python -m engine.research.mandate_replay
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("mandate_replay")
logging.basicConfig(level=logging.INFO, format="%(message)s")

START = "2015-01-01"
CASH0 = 100_000.0
COST_BPS = 6  # 5 bps transaction + 1 bp slippage, per side, on turnover
OUT = Path(__file__).parent / f"mandate_replay_{date.today().isoformat()}.json"

# Mirrors paper_portfolios.yaml sleeve targets + the QC algorithm exactly.
MANDATES = {
    "conservative": {"equity": 0.40, "bonds": 0.50, "alts": 0.10, "cadence": "M"},
    "balanced":     {"equity": 0.70, "bonds": 0.25, "alts": 0.05, "cadence": "M"},
    "aggressive":   {"equity": 0.95, "bonds": 0.05, "alts": 0.00, "cadence": "W"},
}
SLEEVES = {
    "equity": ["SPY", "QQQ", "IWM", "VTI", "VEA", "VWO"],
    "bonds": ["AGG", "TLT", "IEF", "SHY", "LQD", "HYG", "TIP"],
    "alts": ["GLD", "IAU", "USO", "VNQ"],
}
ALL_TICKERS = sorted({t for s in SLEEVES.values() for t in s})


def fetch_panel() -> pd.DataFrame:
    """Adjusted (total-return) closes for all sleeve ETFs + SPY benchmark."""
    import yfinance as yf
    px = yf.download(ALL_TICKERS, start=START, auto_adjust=True,
                     progress=False)["Close"]
    px = px.dropna(how="all")
    missing = [t for t in ALL_TICKERS if t not in px.columns or px[t].isna().all()]
    if missing:
        raise RuntimeError(f"no data for {missing} — refusing a silent hole")
    first_valid = {t: str(px[t].first_valid_index().date()) for t in ALL_TICKERS}
    late = {t: d for t, d in first_valid.items() if d > "2015-01-05"}
    if late:
        # every sleeve member should pre-date 2015 by construction — loud if not
        raise RuntimeError(f"tickers list after start (breaks EW math): {late}")
    return px.ffill()


def target_weights(lane: str) -> dict[str, float]:
    m = MANDATES[lane]
    w: dict[str, float] = {}
    for sleeve, members in SLEEVES.items():
        sw = m[sleeve]
        if sw <= 0:
            continue
        for t in members:
            w[t] = sw / len(members)
    return w


def replay(lane: str, px: pd.DataFrame) -> dict:
    """Daily NAV path: hold shares between rebalances; on each rebalance date
    reset to target weights and pay COST_BPS on one-sided turnover."""
    w_target = target_weights(lane)
    tickers = list(w_target)
    cadence = MANDATES[lane]["cadence"]
    # rebalance on the first trading day of each period (month or week)
    period = px.index.to_period(cadence)
    is_first = pd.Series(period, index=px.index).ne(
        pd.Series(period, index=px.index).shift()).values

    nav = np.empty(len(px))
    shares = None
    cash = CASH0
    for i, (ts, row) in enumerate(zip(px.index, px[tickers].values)):
        if shares is not None:
            cash = float(np.dot(shares, row))
        if is_first[i] or shares is None:
            new_shares = np.array([cash * w_target[t] for t in tickers]) / row
            if shares is not None:
                turnover = float(np.abs((new_shares - shares) * row).sum()) / 2
                cash -= turnover * (COST_BPS / 1e4)
                new_shares = np.array([cash * w_target[t] for t in tickers]) / row
            shares = new_shares
        nav[i] = cash
    return _stats(pd.Series(nav, index=px.index), lane)


def benchmark_6040(px: pd.DataFrame) -> dict:
    spy, agg = px["SPY"], px["AGG"]
    period = px.index.to_period("M")
    is_first = pd.Series(period, index=px.index).ne(
        pd.Series(period, index=px.index).shift()).values
    nav = np.empty(len(px))
    sh = None
    cash = CASH0
    for i in range(len(px)):
        p = np.array([spy.iloc[i], agg.iloc[i]])
        if sh is not None:
            cash = float(np.dot(sh, p))
        if is_first[i] or sh is None:
            sh = np.array([cash * 0.6, cash * 0.4]) / p
        nav[i] = cash
    return _stats(pd.Series(nav, index=px.index), "60-40")


def _stats(nav: pd.Series, name: str) -> dict:
    rets = nav.pct_change().dropna()
    years = (nav.index[-1] - nav.index[0]).days / 365.25
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / years) - 1
    vol = rets.std() * np.sqrt(252)
    sharpe = (rets.mean() / rets.std()) * np.sqrt(252) if rets.std() > 0 else 0.0
    dd = (nav / nav.cummax() - 1).min()
    return {"name": name, "start": str(nav.index[0].date()),
            "end": str(nav.index[-1].date()),
            "final_value": round(float(nav.iloc[-1]), 2),
            "cagr_pct": round(float(cagr) * 100, 2),
            "vol_pct": round(float(vol) * 100, 2),
            "sharpe_rf0": round(float(sharpe), 3),
            "max_drawdown_pct": round(float(dd) * 100, 2)}


if __name__ == "__main__":
    px = fetch_panel()
    results = [replay(lane, px) for lane in MANDATES]
    results.append(_stats(px["SPY"] / px["SPY"].iloc[0] * CASH0, "SPY"))
    results.append(benchmark_6040(px))
    for r in results:
        log.info("%-14s CAGR %6.2f%%  vol %5.2f%%  Sharpe %5.2f  maxDD %7.2f%%  -> $%s",
                 r["name"], r["cagr_pct"], r["vol_pct"], r["sharpe_rf0"],
                 r["max_drawdown_pct"], f"{r['final_value']:,.0f}")
    OUT.write_text(json.dumps({"spec": "ETF-sleeve EW mandate replay, "
                               f"{COST_BPS}bps per-side, rf=0",
                               "results": results}, indent=2), encoding="utf-8")
    log.info("written: %s", OUT)
