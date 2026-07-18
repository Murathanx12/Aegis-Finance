"""
TRIAL-MOM-BACKTEST runner — the ONE frozen evaluation.
=======================================================

Spec frozen 2026-07-18 in docs/TRIALS/TRIAL-MOM-BACKTEST-12-1-momentum.md
(committed BEFORE the panel existed). Registered as trial #13
(mom-backtest-12-1). Panel-quality gate PASSED both checks 2026-07-18.

Frozen parameters (verbatim from the trial doc):
- Panel: EODHD archive (active + delisted US common stocks), 2017-01-01 ->
  2026-06-30.
- Eligibility at each rebalance: top 1000 by trailing-63-day MEDIAN dollar
  volume (Close x Volume), price >= $5.
- Signal: total return t-252 -> t-21 trading days (12-1), adjusted closes.
- Portfolio: top 50 by signal, equal weight, monthly rebalance (first
  trading day). Banding: held names kept while in the top 100; exits
  replaced by the highest-ranked non-held names.
- Costs: 20 bps per side on all traded dollars.
- Delisting: held name that stops trading exits at last adjusted close
  minus 30% haircut.
- Deciding: net Sharpe (rf=0, daily, annualized) vs SPY. Reported: CAGR,
  maxDD, turnover, RSP.
- PASS: Sharpe >= SPY AND maxDD <= 1.25 x SPY maxDD -> lane PROPOSAL only.

Implementation notes (deterministic, spec-neutral):
- Trading-day offsets computed on each name's own price index.
- Delisted-dir codes that ALSO exist in the active dir are DROPPED
  (recycled-symbol identity is ambiguous — the acceptance-test lesson);
  the count is logged loudly.
- After the frozen verdict is computed and printed, a parameter-cloud
  robustness annex (F-025) runs with +/- perturbations. It is REPORTED,
  NEVER DECIDING, and cannot flip the verdict — only temper a proposal.

    python -m engine.research.mom_backtest
"""

from __future__ import annotations

import gzip
import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("mom_backtest")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

DATA = Path(__file__).resolve().parents[1] / "data" / "eodhd"
OUT = Path(__file__).parent / f"mom_backtest_{date.today().isoformat()}.json"

START, END = "2017-01-01", "2026-06-30"
LOOKBACK_PAD = "2015-10-01"  # need ~252td before first rebalance
TOP_N, BAND_N = 50, 100
ELIG_N, MIN_PRICE = 1000, 5.0
COST = 0.0020            # 20 bps per side on traded dollars
DELIST_HAIRCUT = 0.30
SIG_LONG, SIG_SHORT = 252, 21
DVOL_WIN = 63


def _load_name(path: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(path, compression="gzip", parse_dates=["Date"],
                         index_col="Date",
                         usecols=["Date", "Close", "Adjusted_close", "Volume"])
    except Exception:
        return None
    if df.empty or df.index[-1] < pd.Timestamp(LOOKBACK_PAD):
        return None
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df.loc[LOOKBACK_PAD:]


def build_monthly_features() -> tuple[pd.DataFrame, list[pd.Timestamp]]:
    """Pass 1: per (name, rebalance-date) rows of eligibility + signal."""
    active_codes = {p.stem.replace(".csv", "") for p in (DATA / "active").glob("*.csv.gz")}
    files = [("A", p) for p in sorted((DATA / "active").glob("*.csv.gz"))]
    dropped_recycled = 0
    for p in sorted((DATA / "delisted").glob("*.csv.gz")):
        code = p.stem.replace(".csv", "")
        if code in active_codes:
            dropped_recycled += 1  # ambiguous recycled symbol — refuse
            continue
        files.append(("D", p))
    log.info("panel files: %d (dropped %d recycled-ambiguous delisted codes)",
             len(files), dropped_recycled)

    # rebalance grid from SPY's calendar (fetched once, also the benchmark)
    import yfinance as yf
    spy = yf.download(["SPY", "RSP"], start=LOOKBACK_PAD, end="2026-07-01",
                      auto_adjust=True, progress=False)["Close"].dropna()
    if spy.index.tz is not None:
        spy.index = spy.index.tz_localize(None)
    cal = spy.loc[START:END].index
    rebal_dates = [g.index[0] for _, g in
                   pd.Series(1, index=cal).groupby([cal.year, cal.month])]

    rows = []
    for i, (kind, path) in enumerate(files):
        df = _load_name(path)
        if df is None or len(df) < SIG_LONG + 5:
            continue
        code = path.stem.replace(".csv", "") + ("#D" if kind == "D" else "")
        adj = df["Adjusted_close"].to_numpy(dtype=float)
        close = df["Close"].to_numpy(dtype=float)
        dvol = pd.Series(close * df["Volume"].to_numpy(dtype=float),
                         index=df.index).rolling(DVOL_WIN).median().to_numpy()
        idx = df.index
        for d in rebal_dates:
            pos = idx.searchsorted(d, side="right") - 1
            if pos < SIG_LONG:
                continue
            if (d - idx[pos]).days > 7:
                continue  # name not trading around this rebalance
            sig = adj[pos - SIG_SHORT] / adj[pos - SIG_LONG] - 1.0
            if not np.isfinite(sig):
                continue
            rows.append((d, code, close[pos], dvol[pos], sig))
        if (i + 1) % 5000 == 0:
            log.info("pass 1: %d/%d files", i + 1, len(files))
    feats = pd.DataFrame(rows, columns=["date", "code", "price", "dvol", "sig"])
    log.info("pass 1 done: %d (name,month) rows, %d rebalance dates",
             len(feats), len(rebal_dates))
    return feats, rebal_dates, spy


def select_holdings(feats: pd.DataFrame, rebal_dates: list,
                    top_n: int = TOP_N, band_n: int = BAND_N,
                    elig_n: int = ELIG_N, min_price: float = MIN_PRICE) -> dict:
    """Frozen selection: eligibility -> rank by signal -> banded top-N."""
    holdings: dict[pd.Timestamp, list[str]] = {}
    held: list[str] = []
    for d in rebal_dates:
        f = feats[feats["date"] == d]
        f = f[(f["price"] >= min_price) & f["dvol"].notna()]
        f = f.nlargest(elig_n, "dvol")
        ranked = f.sort_values("sig", ascending=False)["code"].tolist()
        band = set(ranked[:band_n])
        keep = [c for c in held if c in band]
        fill = [c for c in ranked if c not in keep][: top_n - len(keep)]
        held = keep + fill
        holdings[d] = list(held)
    return holdings


def compute_nav(holdings: dict, rebal_dates: list, cal: pd.DatetimeIndex,
                cost: float = COST) -> tuple[pd.Series, float]:
    """Pass 2: daily NAV over held names only; monthly EW rebalance with
    per-side costs; delist haircut on names that stop trading."""
    needed = sorted({c for hs in holdings.values() for c in hs})
    log.info("pass 2: loading %d held names' daily series", len(needed))
    series = {}
    for c in needed:
        kind = "delisted" if c.endswith("#D") else "active"
        p = DATA / kind / (c.replace("#D", "") + ".csv.gz")
        df = _load_name(p)
        if df is not None:
            series[c] = df["Adjusted_close"]

    cash = 100_000.0
    shares: dict[str, float] = {}
    nav_out, turn_dollars = [], 0.0
    rb_days = set(rebal_dates)

    def last_px(c: str, day: pd.Timestamp):
        s = series.get(c)
        if s is None:
            return None, None
        pos = s.index.searchsorted(day, side="right") - 1
        if pos < 0:
            return None, None
        return float(s.iloc[pos]), s.index[pos]

    for day in cal:
        # 1) delist sweep: a held name with no print in >10 calendar days
        #    exits at its last print minus the haircut (proceeds to cash)
        for c in list(shares):
            px, when = last_px(c, day)
            if px is None:
                del shares[c]           # never priced — drop worthless (loud in spec)
                continue
            if when < day - pd.Timedelta(days=10):
                cash += shares[c] * px * (1 - DELIST_HAIRCUT)
                del shares[c]

        # 2) mark
        nav_val = cash + sum(sh * (last_px(c, day)[0] or 0.0)
                             for c, sh in shares.items())

        # 3) rebalance to the month's frozen holdings
        if day in rb_days:
            prices = {}
            for c in holdings[day]:
                px, when = last_px(c, day)
                if px is not None and when >= day - pd.Timedelta(days=7):
                    prices[c] = px
            if prices:
                cur_val = {c: shares.get(c, 0.0) * (last_px(c, day)[0] or 0.0)
                           for c in set(shares) | set(prices)}
                per = nav_val / len(prices)
                traded = sum(abs((per if c in prices else 0.0) - cur_val.get(c, 0.0))
                             for c in set(shares) | set(prices))
                fee = traded * cost
                nav_val -= fee
                turn_dollars += traded
                per = nav_val / len(prices)
                shares = {c: per / prices[c] for c in prices}
                cash = 0.0

        nav_out.append((day, nav_val))
    nav = pd.Series(dict(nav_out)).sort_index()
    return nav, turn_dollars


def _stats(nav: pd.Series) -> dict:
    r = nav.pct_change().dropna()
    yrs = (nav.index[-1] - nav.index[0]).days / 365.25
    return {"cagr_pct": round(((nav.iloc[-1] / nav.iloc[0]) ** (1 / yrs) - 1) * 100, 2),
            "sharpe_rf0": round(float(r.mean() / r.std() * np.sqrt(252)), 3),
            "max_dd_pct": round(float((nav / nav.cummax() - 1).min()) * 100, 2),
            "final": round(float(nav.iloc[-1]), 0)}


if __name__ == "__main__":
    compute_nav._cash = 0.0
    feats, rebal_dates, bench = build_monthly_features()
    cal = bench.loc[START:END].index

    holdings = select_holdings(feats, rebal_dates)
    nav, turned = compute_nav(holdings, rebal_dates, cal)
    strat = _stats(nav)
    spy = _stats(bench["SPY"].loc[START:END])
    rsp = _stats(bench["RSP"].loc[START:END])

    passed = (strat["sharpe_rf0"] >= spy["sharpe_rf0"]
              and strat["max_dd_pct"] >= 1.25 * spy["max_dd_pct"])  # dd negative
    verdict = "PASS (direction-check)" if passed else "FAIL"
    log.info("STRATEGY  %s", strat)
    log.info("SPY       %s", spy)
    log.info("RSP       %s", rsp)
    log.info("TRIAL-MOM-BACKTEST FROZEN VERDICT: %s", verdict)

    out = {"trial": "mom-backtest-12-1", "frozen_run": {
        "strategy": strat, "spy": spy, "rsp": rsp,
        "avg_annual_turnover_x": round(turned / 100_000 / 9.5, 2),
        "verdict": verdict}}

    # ---- Parameter-cloud robustness ANNEX (reported, never deciding) ----
    cloud = []
    for tn, bn, cost in [(40, 80, COST), (60, 120, COST), (40, 100, COST),
                         (60, 100, COST), (50, 80, COST), (50, 120, COST),
                         (50, 100, 0.0015), (50, 100, 0.0025)]:
        compute_nav._cash = 0.0
        h = select_holdings(feats, rebal_dates, top_n=tn, band_n=bn)
        n, _ = compute_nav(h, rebal_dates, cal, cost=cost)
        s = _stats(n)
        cloud.append({"top_n": tn, "band": bn, "cost_bps": cost * 1e4, **s})
        log.info("cloud top%d band%d %dbps -> %s", tn, bn, cost * 1e4, s)
    sharpes = [c["sharpe_rf0"] for c in cloud] + [strat["sharpe_rf0"]]
    out["parameter_cloud"] = {"runs": cloud,
                              "sharpe_mean": round(float(np.mean(sharpes)), 3),
                              "sharpe_min": min(sharpes), "sharpe_max": max(sharpes),
                              "note": "annex per F-025 — reported, never deciding"}
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    log.info("written: %s", OUT)
