"""
Aegis Finance — Thematic-Momentum Backtest (TRIAL-THEME, the decisive run)
==========================================================================

Tests Murat's structural thesis MECHANICALLY (no LLM, no hindsight):
inside point-in-time secular baskets, buy positive-12-1-momentum names, size by
vol target, let winners run via ATR trailing stops, cut losers when the stop
fires. Compare net-of-cost vs buy-and-hold SPY, then apply the overfitting
haircut (PBO via CSCV; DSR deflated against the cumulative trial count + every
swept variant).

CHUNK 4b — the close-out controls that separate SKILL from BETA + SURVIVORSHIP:
  - equal-weight-themes control  = "thematic beta" (no momentum selection, no stops)
  - broad-universe momentum      = "generic momentum" (same engine, S&P-ish universe)
  - matched-volatility compare   = beta-neutral (Sharpe is the honest comparator)
  - survivorship correction      = dead "next big thing" names added to the baskets
If thematic ≈ broad ≈ EW-themes at matched vol, theme-selection has no mechanical
alpha → TRIAL-THEME REJECT. If thematic beats both, that's a real surprise.

Research code (network: yfinance). Writes JSON + prints. Does NOT touch the live
registry or any paper lane.

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
from backend.services.exit_engine import compute_atr, volatility_target_weight
from backend.services.theme_baskets import all_tickers, members_as_of, theme_keys
from backend.services.thematic_momentum import compute_target_weights, momentum_12_1
from engine.validation.overfitting import (
    deflated_sharpe_from_returns,
    probability_of_backtest_overfitting,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("thematic_backtest")

START = "2014-01-01"
TRADE_START = "2015-06-01"
END = "2025-06-01"
COST_RATE = 0.0010
TRADING_DAYS = 252
NO_STOP = 1e9   # effectively disables the trailing stop (EW-themes control)


# ── universes ─────────────────────────────────────────────────────────────────


def broad_universe() -> list[str]:
    u = config.get("stock_universe", {})
    names = set(u.get("default_watchlist", []))
    for lst in u.get("sector_stocks", {}).values():
        names.update(lst)
    return sorted(names)


# ── metrics ───────────────────────────────────────────────────────────────────


def perf_metrics(returns: pd.Series) -> dict:
    r = returns.dropna()
    if len(r) < 2:
        return {"cagr": 0.0, "sharpe": 0.0, "vol": 0.0, "max_dd": 0.0}
    curve = (1 + r).cumprod()
    years = len(r) / TRADING_DAYS
    cagr = curve.iloc[-1] ** (1 / years) - 1 if years > 0 else 0.0
    sd = r.std(ddof=1)
    vol = sd * np.sqrt(TRADING_DAYS)
    sharpe = (r.mean() / sd * np.sqrt(TRADING_DAYS)) if sd > 0 else 0.0
    dd = (curve / curve.cummax() - 1).min()
    return {"cagr": round(float(cagr), 4), "sharpe": round(float(sharpe), 4),
            "vol": round(float(vol), 4), "max_dd": round(float(dd), 4)}


def matched_vol_cagr(returns: pd.Series, target_vol: float) -> float:
    """CAGR after scaling the return stream to `target_vol` (beta-neutral view).
    Equivalent ranking to Sharpe, but reads as 'return at SPY's risk level'."""
    r = returns.dropna()
    sd = r.std(ddof=1) * np.sqrt(TRADING_DAYS)
    if sd <= 0:
        return 0.0
    scaled = r * (target_vol / sd)
    curve = (1 + scaled).cumprod()
    years = len(scaled) / TRADING_DAYS
    return round(float(curve.iloc[-1] ** (1 / years) - 1), 4) if years > 0 else 0.0


# ── data ──────────────────────────────────────────────────────────────────────


def fetch_prices() -> tuple[pd.DataFrame, pd.Series]:
    import yfinance as yf

    tickers = sorted(set(all_tickers()) | set(broad_universe()))
    log.info("Fetching %d tickers (themes ∪ broad) + SPY (%s → %s)…",
             len(tickers), START, END)
    raw = yf.download(tickers + ["SPY"], start=START, end=END,
                      auto_adjust=True, progress=False, threads=True)
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    close = close.dropna(how="all")
    spy = close["SPY"].dropna()
    prices = close.drop(columns=["SPY"])
    have = [t for t in tickers if t in prices.columns and prices[t].notna().sum() > 252]
    return prices[have], spy


# ── selection rules (the strategy and its controls) ───────────────────────────


def select_thematic(as_of, sl, *, lookback_months, top_k):
    return compute_target_weights(as_of, sl, lookback_months=lookback_months, top_k=top_k)


def select_broad_momentum(as_of, sl, *, lookback_months, top_k, universe):
    cols = [t for t in universe if t in sl.columns]
    scored = []
    for t in cols:
        m = momentum_12_1(sl[t], lookback_months, 1)
        if m is not None and m > 0:
            scored.append((t, m))
    if not scored:
        return {}
    scored.sort(key=lambda x: x[1], reverse=True)
    sel = [t for t, _ in scored[:top_k]]
    raw = {}
    for t in sel:
        w = volatility_target_weight(sl[t].dropna().pct_change().dropna(),
                                     target_vol=0.20, max_weight=0.25)
        if w > 0:
            raw[t] = w
    tot = sum(raw.values())
    return {t: w / tot for t, w in raw.items()} if tot > 0 else {t: 1 / len(sel) for t in sel}


def select_equal_weight_themes(as_of, sl):
    members = set()
    for tk in theme_keys():
        members.update(members_as_of(tk, as_of))
    cols = [t for t in members if t in sl.columns and sl[t].dropna().shape[0] > 60]
    if not cols:
        return {}
    w = 1.0 / len(cols)
    return {t: w for t in cols}


# ── event-driven sim ──────────────────────────────────────────────────────────


def run_backtest(prices, *, atr_multiple, select_fn) -> pd.Series:
    cfg = config.get("exit_engine", {})
    atr_period = int(cfg.get("atr_period", 14))
    dates = prices.index
    atr = {t: compute_atr(prices[t], period=atr_period) for t in prices.columns}
    tdates = dates[(dates >= pd.Timestamp(TRADE_START)) & (dates <= pd.Timestamp(END))]
    if len(tdates) == 0:
        return pd.Series(dtype=float)
    start_i = dates.get_loc(tdates[0])

    cash, holdings, nav_hist, last_month = 1.0, {}, [], None

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

        if last_month != today.month:
            last_month = today.month
            pv = nav(i)
            if pv > 0:
                target = select_fn(today, prices.iloc[: i + 1])
                cur = {t: (h["shares"] * price(t, i) if price(t, i) else 0.0)
                       for t, h in holdings.items()}
                tgt = {t: w * pv for t, w in target.items()}
                traded = 0.0
                for t in set(cur) | set(tgt):
                    p = price(t, i)
                    if p is None or p <= 0:
                        continue
                    delta = tgt.get(t, 0.0) - cur.get(t, 0.0)
                    traded += abs(delta)
                    new_shares = tgt.get(t, 0.0) / p
                    if new_shares <= 1e-12:
                        holdings.pop(t, None)
                    elif t in holdings:
                        holdings[t]["shares"] = new_shares
                    else:
                        a = float(atr[t].iloc[i]) if pd.notna(atr[t].iloc[i]) else 0.0
                        holdings[t] = {"shares": new_shares, "peak": p,
                                       "stop": p - atr_multiple * a}
                cash = pv - sum(h["shares"] * price(t, i) for t, h in holdings.items()
                                if price(t, i)) - traded * COST_RATE
        nav_hist.append((today, nav(i)))

    nav_s = pd.Series({d: v for d, v in nav_hist})
    return nav_s.pct_change().dropna()


# ── main ──────────────────────────────────────────────────────────────────────


def main() -> dict:
    prices, spy = fetch_prices()
    broad = broad_universe()
    spy_ret = spy.reindex(prices.index).pct_change().dropna()
    spy_ret = spy_ret[spy_ret.index >= pd.Timestamp(TRADE_START)]
    spy_m = perf_metrics(spy_ret)
    spy_vol = spy_m["vol"]

    # --- thematic sweep (survivorship-corrected baskets) ---
    atr_grid = config.get("exit_engine", {}).get("atr_multiple_grid", [2.0, 3.0, 4.0])
    lookback_grid = [6, 9, 12]
    configs = list(itertools.product(atr_grid, lookback_grid))
    log.info("Sweeping %d thematic configs (de-biased baskets)…", len(configs))
    results, ret_series = {}, {}
    for k, lb in configs:
        r = run_backtest(prices, atr_multiple=k,
                         select_fn=lambda d, s, lb=lb: select_thematic(d, s, lookback_months=lb, top_k=10))
        if len(r) > 50:
            ret_series[(k, lb)] = r
            results[(k, lb)] = perf_metrics(r)

    common = None
    for r in ret_series.values():
        common = r.index if common is None else common.intersection(r.index)
    mat = np.column_stack([ret_series[c].reindex(common).values for c in ret_series])
    pbo = probability_of_backtest_overfitting(mat, n_partitions=10)
    best_c = max(results, key=lambda c: results[c]["sharpe"])
    sharpes = np.array([results[c]["sharpe"] for c in results])
    sr_var = float(np.var(sharpes / np.sqrt(TRADING_DAYS), ddof=1))
    n_trials = 3 + len(configs)
    dsr = deflated_sharpe_from_returns(ret_series[best_c].values, n_trials, sr_var)
    headline = (3.0, 12) if (3.0, 12) in results else best_c

    # --- controls (Chunk 4b) ---
    log.info("Running controls: EW-themes, broad-momentum…")
    ew = run_backtest(prices, atr_multiple=NO_STOP, select_fn=select_equal_weight_themes)
    bm = run_backtest(prices, atr_multiple=3.0,
                      select_fn=lambda d, s: select_broad_momentum(d, s, lookback_months=12, top_k=10, universe=broad))
    ew_m, bm_m = perf_metrics(ew), perf_metrics(bm)
    th = ret_series[headline]
    th_m = results[headline]

    table = {
        "SPY_buyhold": {**spy_m, "matched_vol_cagr": spy_m["cagr"]},
        "thematic_momentum": {**th_m, "matched_vol_cagr": matched_vol_cagr(th, spy_vol)},
        "equal_weight_themes": {**ew_m, "matched_vol_cagr": matched_vol_cagr(ew, spy_vol)},
        "broad_momentum": {**bm_m, "matched_vol_cagr": matched_vol_cagr(bm, spy_vol)},
    }

    # --- verdict: does theme-SELECTION beat generic momentum AND beta at matched vol? ---
    th_sh, bm_sh, ew_sh = th_m["sharpe"], bm_m["sharpe"], ew_m["sharpe"]
    selection_edge = th_sh - max(bm_sh, ew_sh)
    beats_spy = th_sh > spy_m["sharpe"]
    verdict = ("SELECTION-SKILL" if (selection_edge > 0.10 and beats_spy)
               else "REJECT (≈ momentum/beta)")

    out = {
        "window": {"trade_start": TRADE_START, "end": END}, "cost_bps": COST_RATE * 1e4,
        "headline_config": {"atr_multiple": headline[0], "lookback_months": headline[1]},
        "best_config": {"atr_multiple": best_c[0], "lookback_months": best_c[1], **results[best_c]},
        "comparison_table": table, "pbo": pbo, "dsr": dsr,
        "n_trials_deflated_against": n_trials,
        "selection_edge_sharpe_vs_best_control": round(selection_edge, 4),
        "verdict": verdict,
    }

    log.info("\n%s", "=" * 70)
    log.info("%-22s %8s %7s %7s %14s", "Strategy", "CAGR", "Sharpe", "maxDD", "matchedVolCAGR")
    for name, m in table.items():
        log.info("%-22s %+7.1f%% %7.2f %+6.1f%% %+13.1f%%",
                 name, m["cagr"] * 100, m["sharpe"], m["max_dd"] * 100,
                 m["matched_vol_cagr"] * 100)
    log.info("-" * 70)
    log.info("PBO=%.2f (%s)  DSR=%.3f vs %d trials", pbo.get("pbo", float("nan")),
             pbo.get("interpretation", "?"), dsr["dsr"], n_trials)
    log.info("Selection edge (thematic Sharpe − best control) = %+.2f", selection_edge)
    log.info("VERDICT: %s", verdict)
    log.info("=" * 70)

    out_path = Path(PROJECT_ROOT) / "docs" / "research" / "thematic_backtest_results.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    log.info("Wrote %s", out_path)
    return out


if __name__ == "__main__":
    main()
