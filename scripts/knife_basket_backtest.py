"""KNIFE_BASKET -- does buying a high-vol basket after a 20-session drawdown pay over 5 sessions?

    python -m scripts.knife_basket_backtest

WHAT IT TESTS (the exact bet `hack3` is making, 2026-08-28)
==========================================================
The fleet's thesis account buys ~15 future-state names (rv60 60-170%) that are
DOWN 20-50% over the prior 20 sessions, sized 6% each, held for the contest
window. The human's rule is "if it has dropped a lot recently, look". CRSP
cannot say whether robotics or quantum re-rate, but it can say what the
CONSTRUCTION did historically: on every session 2013-2024, take names with
price >= $2, 20-session median dollar volume >= $2M, 60-session realised vol in
a band, and 20-session drawdown in a band; equal-weight them; hold 5 sessions;
report the excess over the equal-weighted market and over a same-vol control
that did NOT fall. Week-blocked t, terminal wealth of rolling the basket, and
the split by vol band and drawdown band.

The control matters more than the mean: a high-vol basket has a high-vol
return whatever it did last month. "Falling knives rebound" is only a claim if
the fallen basket beats the un-fallen basket at the same vol.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
WRDS = ROOT / "backend" / "data" / "optimus" / "wrds"
OUT = ROOT / "backend" / "data" / "optimus" / "knife_basket_2013_2024.json"
HOLD = 5


def load() -> pd.DataFrame:
    frames = []
    for y in range(2013, 2025):
        p = WRDS / f"crsp_dsf_{y}.parquet"
        if p.exists():
            frames.append(pd.read_parquet(p, columns=["permno", "date", "prc", "ret", "vol"]))
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"])
    d["ret"] = pd.to_numeric(d["ret"], errors="coerce")
    d["prc"] = pd.to_numeric(d["prc"], errors="coerce").abs()
    d["vol"] = pd.to_numeric(d["vol"], errors="coerce")
    return d.dropna(subset=["ret", "prc"]).sort_values(["permno", "date"]).reset_index(drop=True)


def main() -> int:
    d = load()
    print(f"rows {len(d):,}  permnos {d.permno.nunique():,}")
    piv_ret = d.pivot(index="date", columns="permno", values="ret")
    piv_prc = d.pivot(index="date", columns="permno", values="prc")
    piv_dv = (d.assign(dv=d.prc * d.vol).pivot(index="date", columns="permno", values="dv"))
    mkt = piv_ret.mean(axis=1)
    logret = np.log1p(piv_ret)
    rv60 = logret.rolling(60, min_periods=40).std() * math.sqrt(252)
    hi20 = piv_prc.rolling(20, min_periods=15).max()
    dd20 = piv_prc / hi20 - 1.0
    dv20 = piv_dv.rolling(20, min_periods=15).median()
    # forward 5-session compounded return and market
    fwd = (np.exp(logret.shift(-1).rolling(HOLD).sum().shift(-(HOLD - 1))) - 1.0)
    mfwd = (np.exp(np.log1p(mkt).shift(-1).rolling(HOLD).sum().shift(-(HOLD - 1))) - 1.0)
    dates = piv_ret.index[::HOLD]          # NON-overlapping windows
    liquid = (piv_prc >= 2.0) & (dv20 >= 2e6)

    bands_vol = [(0.6, 1.0), (1.0, 1.8)]
    bands_dd = [(-0.99, -0.50), (-0.50, -0.30), (-0.30, -0.20), (-0.20, -0.10), (-0.10, 0.0)]
    out = {"hold": HOLD, "windows": int(len(dates)), "cells": {}}

    def cell(mask, name):
        rows = []
        for t in dates:
            if t not in mask.index:
                continue
            m = mask.loc[t]
            sel = m[m].index
            if len(sel) < 5:
                continue
            r = fwd.loc[t, sel].dropna()
            if len(r) < 5:
                continue
            rows.append((t, float(r.mean()), float(mfwd.loc[t]), int(len(r))))
        if len(rows) < 20:
            return {"n_windows": len(rows)}
        df = pd.DataFrame(rows, columns=["t", "basket", "mkt", "n"])
        ex = df.basket - df.mkt
        t_stat = ex.mean() / (ex.std(ddof=1) / math.sqrt(len(ex)))
        wealth = float(np.prod(1 + df.basket))
        mwealth = float(np.prod(1 + df.mkt))
        return {"n_windows": int(len(df)), "mean_basket": round(float(df.basket.mean()), 5),
                "mean_excess": round(float(ex.mean()), 5), "median_excess": round(float(ex.median()), 5),
                "hit_vs_mkt": round(float((ex > 0).mean()), 3), "t": round(float(t_stat), 2),
                "terminal_wealth": round(wealth, 3), "market_wealth": round(mwealth, 3),
                "avg_names": round(float(df.n.mean()), 1)}

    print(f"\n{'vol band':<10}{'dd20 band':<14}{'win':>5}{'names':>7}{'mean':>9}{'excess':>9}{'med ex':>9}{'hit':>6}{'t':>7}{'wealth':>9}{'mkt':>8}")
    for vlo, vhi in bands_vol:
        for dlo, dhi in bands_dd:
            mask = liquid & (rv60 >= vlo) & (rv60 < vhi) & (dd20 >= dlo) & (dd20 < dhi)
            name = f"rv{vlo:.1f}-{vhi:.1f}|dd{dlo:+.2f}..{dhi:+.2f}"
            c = cell(mask, name)
            out["cells"][name] = c
            if "t" in c:
                print(f"{vlo:.1f}-{vhi:.1f}   {dlo:+.2f}..{dhi:+.2f}  {c['n_windows']:>5}{c['avg_names']:>7}{c['mean_basket']:>+9.2%}"
                      f"{c['mean_excess']:>+9.2%}{c['median_excess']:>+9.2%}{c['hit_vs_mkt']:>6.0%}{c['t']:>7.2f}{c['terminal_wealth']:>9.2f}{c['market_wealth']:>8.2f}")
    # the hack3 cell: rv 0.6-1.8, dd -0.50..-0.20
    mask = liquid & (rv60 >= 0.6) & (rv60 < 1.8) & (dd20 >= -0.50) & (dd20 < -0.20)
    out["hack3_cell"] = cell(mask, "hack3")
    ctrl = liquid & (rv60 >= 0.6) & (rv60 < 1.8) & (dd20 >= -0.10)
    out["same_vol_unfallen_control"] = cell(ctrl, "control")
    print("\nhack3 cell (rv 60-180%, dd20 -50..-20%):", out["hack3_cell"])
    print("same-vol UNFALLEN control (dd20 > -10%):", out["same_vol_unfallen_control"])
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"receipt: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
