"""
Aegis Finance — Thematic-Momentum Backtest (TRIAL-THEME, the decisive run)
==========================================================================

Tests Murat's structural thesis MECHANICALLY (no LLM, no hindsight):
inside point-in-time secular baskets, buy positive-12-1-momentum names, size by
vol target, let winners run via ATR trailing stops, cut losers when the stop
fires. Compare net-of-cost vs buy-and-hold SPY, then apply the overfitting
haircut (PBO via CSCV; DSR deflated against the cumulative trial count + every
swept variant).

This is research code (network: yfinance). It writes a JSON result and prints a
table. It does NOT touch the live registry or any paper lane — recording
TRIAL-THEME to the registry is a separate attended step.

Run:
    python -m engine.research.thematic_backtest
"""

from __future__ import annotations

import itertools
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from backend.config import PROJECT_ROOT, config
from backend.services.exit_engine import compute_atr
from backend.services.theme_baskets import all_tickers
from backend.services.thematic_momentum import compute_target_weights
from engine.validation.overfitting import (
    deflated_sharpe_from_returns,
    probability_of_backtest_overfitting,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("thematic_backtest")

START = "2014-01-01"     # fetch floor (need 252d warmup before first trade)
TRADE_START = "2015-06-01"
END = "2025-06-01"
COST_RATE = 0.0010       # 10 bps per dollar traded (round-trip-ish for liquid LC)
TRADING_DAYS = 252


# ── metrics ───────────────────────────────────────────────────────────────────


def perf_metrics(returns: pd.Series) -> dict:
    r = returns.dropna()
    if len(r) < 2:
        return {"cagr": 0.0, "sharpe": 0.0, "vol": 0.0, "max_dd": 0.0}
    curve = (1 + r).cumprod()
    years = len(r) / TRADING_DAYS
    cagr = curve.iloc[-1] ** (1 / years) - 1 if years > 0 else 0.0
    vol = r.std(ddof=1) * np.sqrt(TRADING_DAYS)
    sharpe = (r.mean() / r.std(ddof=1) * np.sqrt(TRADING_DAYS)) if r.std(ddof=1) > 0 else 0.0
    dd = (curve / curve.cummax() - 1).min()
    return {
        "cagr": round(float(cagr), 4),
        "sharpe": round(float(sharpe), 4),
        "vol": round(float(vol), 4),
        "max_dd": round(float(dd), 4),
    }


# ── data ──────────────────────────────────────────────────────────────────────


def fetch_prices() -> tuple[pd.DataFrame, pd.Series]:
    import yfinance as yf

    tickers = all_tickers()
    log.info("Fetching %d theme tickers + SPY (%s → %s)…", len(tickers), START, END)
    raw = yf.download(tickers + ["SPY"], start=START, end=END,
                      auto_adjust=True, progress=False, threads=True)
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    close = close.dropna(how="all")
    spy = close["SPY"].dropna()
    prices = close.drop(columns=["SPY"])
    have = [t for t in tickers if t in prices.columns and prices[t].notna().sum() > 252]
    missing = sorted(set(tickers) - set(have))
    if missing:
        log.info("  (no/short data, dropped: %s)", ", ".join(missing))
    return prices[have], spy


# ── the event-driven sim ──────────────────────────────────────────────────────


def run_backtest(prices: pd.DataFrame, *, atr_multiple: float,
                 lookback_months: int, top_k: int = 10) -> pd.Series:
    """Daily NAV → daily returns for one config. Monthly momentum rebalance,
    daily ATR trailing-stop exits to cash, turnover costs."""
    cfg = config.get("exit_engine", {})
    atr_period = int(cfg.get("atr_period", 14))
    vol_target = float(cfg.get("vol_target_annual", 0.20))
    max_w = float(cfg.get("max_position_weight", 0.25))

    dates = prices.index
    atr = {t: compute_atr(prices[t], period=atr_period) for t in prices.columns}

    trade_dates = dates[(dates >= pd.Timestamp(TRADE_START)) & (dates <= pd.Timestamp(END))]
    if len(trade_dates) == 0:
        return pd.Series(dtype=float)
    start_i = dates.get_loc(trade_dates[0])

    cash = 1.0
    holdings: dict[str, dict] = {}   # ticker -> {shares, peak, stop}
    nav_hist: list[tuple[pd.Timestamp, float]] = []
    last_month = None

    def price(t, i):
        v = prices[t].iloc[i]
        return float(v) if pd.notna(v) else None

    def nav(i):
        v = cash
        for t, h in holdings.items():
            p = price(t, i)
            if p is not None:
                v += h["shares"] * p
        return v

    for i in range(start_i, len(dates)):
        today = dates[i]

        # --- daily trailing-stop exits (skip on the very first bar) ---
        for t in list(holdings.keys()):
            p = price(t, i)
            if p is None:
                continue
            h = holdings[t]
            h["peak"] = max(h["peak"], p)
            a = float(atr[t].iloc[i]) if pd.notna(atr[t].iloc[i]) else 0.0
            h["stop"] = max(h["stop"], h["peak"] - atr_multiple * a)
            if p <= h["stop"]:
                proceeds = h["shares"] * p
                cash += proceeds - abs(proceeds) * COST_RATE
                del holdings[t]

        # --- monthly rebalance ---
        if last_month != today.month:
            last_month = today.month
            pv = nav(i)
            if pv > 0:
                target = compute_target_weights(
                    today, prices.iloc[: i + 1],
                    lookback_months=lookback_months, top_k=top_k,
                    vol_target=vol_target, max_weight=max_w,
                )
                # current dollar positions
                cur = {}
                for t, h in holdings.items():
                    p = price(t, i)
                    cur[t] = h["shares"] * p if p is not None else 0.0
                tgt_dollars = {t: w * pv for t, w in target.items()}

                traded = 0.0
                for t in set(cur) | set(tgt_dollars):
                    p = price(t, i)
                    if p is None or p <= 0:
                        continue
                    cur_d = cur.get(t, 0.0)
                    tgt_d = tgt_dollars.get(t, 0.0)
                    delta = tgt_d - cur_d
                    traded += abs(delta)
                    new_shares = tgt_d / p
                    if new_shares <= 1e-12:
                        holdings.pop(t, None)
                    else:
                        if t in holdings:
                            holdings[t]["shares"] = new_shares  # keep peak/stop (let it run)
                        else:
                            a = float(atr[t].iloc[i]) if pd.notna(atr[t].iloc[i]) else 0.0
                            holdings[t] = {"shares": new_shares, "peak": p,
                                           "stop": p - atr_multiple * a}
                cost = traded * COST_RATE
                cash = pv - sum(h["shares"] * price(t, i) for t, h in holdings.items()
                                if price(t, i)) - cost

        nav_hist.append((today, nav(i)))

    nav_s = pd.Series({d: v for d, v in nav_hist})
    return nav_s.pct_change().dropna()


# ── the sweep + haircut ───────────────────────────────────────────────────────


def main() -> dict:
    prices, spy = fetch_prices()
    spy_ret = spy.reindex(prices.index).pct_change().dropna()
    spy_ret = spy_ret[(spy_ret.index >= pd.Timestamp(TRADE_START))]
    spy_m = perf_metrics(spy_ret)

    atr_grid = config.get("exit_engine", {}).get("atr_multiple_grid", [2.0, 3.0, 4.0])
    lookback_grid = [6, 9, 12]
    configs = list(itertools.product(atr_grid, lookback_grid))
    log.info("Running %d configs (atr × lookback)…", len(configs))

    results = {}
    ret_series = {}
    for k, lb in configs:
        r = run_backtest(prices, atr_multiple=k, lookback_months=lb)
        if len(r) > 50:
            ret_series[(k, lb)] = r
            results[(k, lb)] = perf_metrics(r)
            log.info("  atr=%.1f lb=%2d → CAGR %+.1f%%  Sharpe %.2f  maxDD %.1f%%",
                     k, lb, results[(k, lb)]["cagr"] * 100,
                     results[(k, lb)]["sharpe"], results[(k, lb)]["max_dd"] * 100)

    # align all configs on common dates for the PBO matrix
    common = None
    for r in ret_series.values():
        common = r.index if common is None else common.intersection(r.index)
    mat = np.column_stack([ret_series[c].reindex(common).values for c in ret_series])
    pbo = probability_of_backtest_overfitting(mat, n_partitions=10)

    # selected = best in-sample Sharpe; deflate against cumulative trials + variants
    best_c = max(results, key=lambda c: results[c]["sharpe"])
    sharpes = np.array([results[c]["sharpe"] for c in results])
    sr_var = float(np.var(sharpes / np.sqrt(TRADING_DAYS), ddof=1))  # per-obs SR variance
    cumulative_prior_trials = 3   # registry count as of 2026-06-15
    n_trials = cumulative_prior_trials + len(configs)
    dsr = deflated_sharpe_from_returns(ret_series[best_c].values, n_trials, sr_var)

    headline = (3.0, 12) if (3.0, 12) in results else best_c
    out = {
        "spy": spy_m,
        "headline_config": {"atr_multiple": headline[0], "lookback_months": headline[1],
                            **results[headline]},
        "best_config": {"atr_multiple": best_c[0], "lookback_months": best_c[1],
                        **results[best_c]},
        "all_configs": {f"atr{c[0]}_lb{c[1]}": results[c] for c in results},
        "pbo": pbo,
        "dsr": dsr,
        "n_trials_deflated_against": n_trials,
        "cost_rate_bps": COST_RATE * 1e4,
        "window": {"trade_start": TRADE_START, "end": END},
        "n_obs": int(len(common)),
        "verdict_gate": {
            "dsr_ship_threshold": 0.95, "pbo_reject_threshold": 0.5,
            "dsr_pass": dsr["dsr"] >= 0.95, "pbo_pass": pbo.get("pbo", 1.0) < 0.5,
        },
    }
    out["verdict"] = "PASS" if (out["verdict_gate"]["dsr_pass"]
                               and out["verdict_gate"]["pbo_pass"]) else "FAIL"

    log.info("\n%s", "=" * 64)
    log.info("SPY buy&hold      : CAGR %+.1f%%  Sharpe %.2f  maxDD %.1f%%",
             spy_m["cagr"] * 100, spy_m["sharpe"], spy_m["max_dd"] * 100)
    h = out["headline_config"]
    log.info("Thematic (atr3,12): CAGR %+.1f%%  Sharpe %.2f  maxDD %.1f%%",
             h["cagr"] * 100, h["sharpe"], h["max_dd"] * 100)
    b = out["best_config"]
    log.info("Best in-sample    : atr=%.1f lb=%d  CAGR %+.1f%%  Sharpe %.2f",
             b["atr_multiple"], b["lookback_months"], b["cagr"] * 100, b["sharpe"])
    log.info("PBO=%.2f (%s)  DSR=%.3f (need ≥0.95)  → deflated vs %d trials",
             pbo.get("pbo", float("nan")), pbo.get("interpretation", "?"),
             dsr["dsr"], n_trials)
    log.info("VERDICT: %s", out["verdict"])
    log.info("=" * 64)

    out_path = Path(PROJECT_ROOT) / "docs" / "research" / "thematic_backtest_results.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    log.info("Wrote %s", out_path)
    return out


if __name__ == "__main__":
    main()
