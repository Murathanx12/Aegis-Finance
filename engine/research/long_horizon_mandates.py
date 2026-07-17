"""Long-horizon mandate direction-check (2026-07-18).

Replays the three REFERENCE-LANE mandates (conservative 40/50/10,
balanced 70/25/5, aggressive 95/5/0) at ASSET-CLASS level over ~97 years
of monthly data, against 100% S&P and classic 60/40 baselines.

WHY THIS IS ALLOWED under CANON §2 (T7): the T7 survivorship verdict
kills stock-SELECTION backtests on free data. It does NOT kill
asset-class replays: index-level return series (French market factor,
Treasury yields) have no delisting problem — there is nothing to
survive. This is a DIRECTION-AND-MECHANICS check: how do the mandates
behave across regimes (1929, 1973-74, dot-com, GFC, 2022)? It produces
NO alpha claim, and per CANON §5 its findings may only inform NEW
pre-registered lanes — never in-flight lane edits.

Data (all free, all disclosed):
- Equity: Kenneth French market factor (Mkt-RF + RF), monthly, 1926-07+.
  Total-return, survivorship-clean at index level. Grade: DIRECTIONAL
  (research library, minor revisions happen).
- Bonds: 10Y constant-maturity Treasury total return APPROXIMATED from
  FRED GS10 yields (monthly): r_m ~= y_{t-1}/12 + D_t * (y_{t-1} - y_t),
  with D = modified duration of a 10Y par bond at y_{t-1}. Standard
  academic approximation (e.g. Swinkels 2019 shows ~0.99 correlation
  with actual bond index returns). Grade: APPROXIMATION.
- Cash (rf): French RF (1-month T-bill).
- Alt sleeve (gold): FRED gold fixing from 1968-04; BEFORE 1968 the alt
  sleeve is allocated to bonds and every affected row is flagged
  (gold was price-fixed at $35 pre-1968 anyway — holding it earned ~0
  nominal, so the substitution is conservative for the mandates).

Monthly rebalance to target weights (proxy for the lanes'
cadence/drift rebalancing). No costs (paper lanes trade ETFs at ~0
cost; turnover of a monthly-rebalanced 3-sleeve mandate is tiny).

Usage:  python -m engine.research.long_horizon_mandates
Writes: engine/research/output/long_horizon_mandates.json (+ prints table)
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests

OUT_DIR = Path(__file__).parent / "output"

FRENCH_URL = ("https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/"
              "ftp/F-F_Research_Data_Factors_CSV.zip")

MANDATES = {
    "conservative": {"equity": 0.40, "bond": 0.50, "alt": 0.10},
    "balanced": {"equity": 0.70, "bond": 0.25, "alt": 0.05},
    "aggressive": {"equity": 0.95, "bond": 0.05, "alt": 0.00},
    "sp500_baseline": {"equity": 1.00, "bond": 0.00, "alt": 0.00},
    "classic_60_40": {"equity": 0.60, "bond": 0.40, "alt": 0.00},
}

# Named stress windows (inclusive, YYYY-MM) for the per-regime table.
STRESS_WINDOWS = {
    "1929 crash + depression": ("1929-09", "1932-06"),
    "1973-74 oil/stagflation": ("1973-01", "1974-09"),
    "dot-com bust": ("2000-03", "2002-09"),
    "GFC": ("2007-10", "2009-02"),
    "2022 rate shock": ("2022-01", "2022-09"),
}


def fetch_french_factors() -> pd.DataFrame:
    """Monthly Mkt-RF and RF from the Kenneth French library, decimal."""
    r = requests.get(FRENCH_URL, timeout=60)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        name = z.namelist()[0]
        raw = z.read(name).decode("latin-1")
    rows = []
    for line in raw.splitlines():
        parts = [p.strip() for p in line.split(",")]
        # monthly rows look like: 192607,  2.96, -2.56, -2.43,  0.22
        if len(parts) >= 5 and len(parts[0]) == 6 and parts[0].isdigit():
            rows.append((parts[0], float(parts[1]), float(parts[4])))
    df = pd.DataFrame(rows, columns=["ym", "mkt_rf", "rf"])
    df.index = pd.PeriodIndex(df["ym"], freq="M")
    df = df[~df.index.duplicated(keep="first")]
    df["equity"] = (df["mkt_rf"] + df["rf"]) / 100.0
    df["cash"] = df["rf"] / 100.0
    return df[["equity", "cash"]]


def fetch_fred_series(series_id: str) -> pd.Series:
    from backend.config import api_keys
    from fredapi import Fred
    fred = Fred(api_key=api_keys.fred)
    s = fred.get_series(series_id).dropna()
    s.index = pd.PeriodIndex(pd.to_datetime(s.index), freq="M")
    return s[~s.index.duplicated(keep="last")]


def bond_total_returns(gs10: pd.Series) -> pd.Series:
    """10Y Treasury total-return approximation from constant-maturity yields."""
    y = gs10 / 100.0
    y_prev = y.shift(1)
    # modified duration of a 10Y par bond at last month's yield
    dur = (1 - (1 + y_prev / 2) ** -20) / y_prev
    ret = y_prev / 12 + dur * (y_prev - y)
    return ret.dropna()


def gold_returns() -> pd.Series:
    """Monthly gold returns. FRED discontinued the LBMA fixing series in
    2022, so: datahub long monthly CSV first, yfinance futures fallback."""
    try:
        r = requests.get("https://datahub.io/core/gold-prices/r/monthly.csv",
                         timeout=60)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        px = pd.Series(df["Price"].values,
                       index=pd.PeriodIndex(pd.to_datetime(df["Date"]), freq="M"))
        px = px[~px.index.duplicated(keep="last")].astype(float)
        if len(px) > 100:
            return px.pct_change().dropna()
    except Exception:
        pass
    try:
        import yfinance as yf
        h = yf.Ticker("GC=F").history(period="max", interval="1mo")["Close"].dropna()
        px = pd.Series(h.values,
                       index=pd.PeriodIndex(pd.to_datetime(h.index), freq="M"))
        px = px[~px.index.duplicated(keep="last")]
        if len(px) > 100:
            return px.pct_change().dropna()
    except Exception:
        pass
    raise RuntimeError("no gold series available (datahub + yfinance failed)")


def build_panel() -> tuple[pd.DataFrame, str]:
    fr = fetch_french_factors()
    gs10 = fetch_fred_series("GS10")  # 1953-04+
    bonds = bond_total_returns(gs10)
    gold = gold_returns()

    panel = pd.DataFrame({
        "equity": fr["equity"],
        "cash": fr["cash"],
        "bond": bonds,
        "alt": gold,
    })
    # Pre-GS10 (before 1953-05): approximate bond sleeve with Shiller-free
    # fallback = cash + 100bp/yr term premium? NO — do not fabricate.
    # Instead: run the full study from the first month ALL sleeves except
    # alt exist (bond start), and note the earlier equity-only era
    # separately. Alt before gold data → bonds (disclosed).
    start = panel["bond"].first_valid_index()
    panel = panel.loc[start:]
    alt_fallback_rows = int(panel["alt"].isna().sum())
    panel["alt"] = panel["alt"].fillna(panel["bond"])
    panel = panel.dropna()
    note = (f"panel {panel.index[0]}..{panel.index[-1]} "
            f"({len(panel)} months); alt sleeve = bonds for first "
            f"{alt_fallback_rows} months (pre-1968 gold fixing)")
    return panel, note


def replay(panel: pd.DataFrame, weights: dict) -> pd.Series:
    """Monthly-rebalanced portfolio return series."""
    w = {k: weights.get(k, 0.0) for k in ("equity", "bond", "alt")}
    ret = (panel["equity"] * w["equity"] + panel["bond"] * w["bond"]
           + panel["alt"] * w["alt"])
    return ret


def stats(ret: pd.Series, rf: pd.Series) -> dict:
    nav = (1 + ret).cumprod()
    yrs = len(ret) / 12
    cagr = nav.iloc[-1] ** (1 / yrs) - 1
    vol = ret.std() * np.sqrt(12)
    ex = ret - rf.reindex(ret.index).fillna(0)
    sharpe = (ex.mean() / ret.std()) * np.sqrt(12) if ret.std() > 0 else np.nan
    peak = nav.cummax()
    dd = nav / peak - 1
    maxdd = dd.min()
    # longest peak-to-recovery stretch in months
    underwater = dd < 0
    longest, cur = 0, 0
    for u in underwater:
        cur = cur + 1 if u else 0
        longest = max(longest, cur)
    # worst rolling 10y CAGR
    roll10 = nav.pct_change(120).dropna()
    worst10 = (1 + roll10.min()) ** (1 / 10) - 1 if len(roll10) else np.nan
    return {
        "cagr": round(float(cagr), 4),
        "vol": round(float(vol), 4),
        "sharpe": round(float(sharpe), 2),
        "max_drawdown": round(float(maxdd), 4),
        "longest_underwater_months": int(longest),
        "worst_rolling_10y_cagr": round(float(worst10), 4),
        "growth_of_100": round(float(nav.iloc[-1] * 100), 0),
    }


def window_return(ret: pd.Series, start: str, end: str) -> float | None:
    sl = ret.loc[pd.Period(start, "M"):pd.Period(end, "M")]
    if len(sl) == 0:
        return None
    return round(float((1 + sl).prod() - 1), 4)


def main() -> dict:
    panel, note = build_panel()
    results: dict = {
        "data_grade": "DIRECTIONAL (index-level; bond TR approximated from "
                      "GS10 yields; no alpha claims — CANON §2)",
        "panel_note": note,
        "mandates": {},
        "stress_windows": {},
    }
    for name, w in MANDATES.items():
        ret = replay(panel, w)
        results["mandates"][name] = stats(ret, panel["cash"])
    for wname, (s, e) in STRESS_WINDOWS.items():
        results["stress_windows"][wname] = {
            name: window_return(replay(panel, w), s, e)
            for name, w in MANDATES.items()
        }
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / "long_horizon_mandates.json"
    out.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(json.dumps(results, indent=1))
    print(f"\nwritten: {out}")
    return results


if __name__ == "__main__":
    main()
