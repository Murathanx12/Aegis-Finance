"""KNIFE_REBOUND_SPLIT -- is the one paying cell (down >50%/20d at >100% vol) one regime?

    python -m scripts.knife_rebound_split

`knife_basket_backtest` found exactly one cell with a positive excess over
2013-2024: 20-session drawdown below -50% at 60-session realised vol above
100% (+2.32%/5 sessions, t 2.60, n=88 non-overlapping windows). `theme_basket`
now buys that cell. n=88 is thin, so before it is trusted:

  * by YEAR  -- if 2020 (March) is the whole result, it is a regime, not a rule;
  * by HOLD  -- 1 / 3 / 5 / 10 sessions: does the rebound arrive on day one
                (a gap the fleet cannot catch) or accrue over the week;
  * by SIZE  -- dollar-volume tercile inside the cell;
  * the WIDER cell -60..-40% and the vol threshold 80% vs 100%, so the rule's
    edges are seen, not assumed.

Same conventions as the parent: liquid (>= $2, >= $2M/day), equal weight,
excess over the equal-weighted market, non-overlapping windows, week-blocked t.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
WRDS = ROOT / "backend" / "data" / "optimus" / "wrds"
OUT = ROOT / "backend" / "data" / "optimus" / "knife_rebound_split_2013_2024.json"


def load() -> pd.DataFrame:
    frames = [pd.read_parquet(WRDS / f"crsp_dsf_{y}.parquet", columns=["permno", "date", "prc", "ret", "vol"])
              for y in range(2013, 2025) if (WRDS / f"crsp_dsf_{y}.parquet").exists()]
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"])
    for c in ("ret", "prc", "vol"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["prc"] = d["prc"].abs()
    return d.dropna(subset=["ret", "prc"]).sort_values(["permno", "date"]).reset_index(drop=True)


def main() -> int:
    d = load()
    piv_ret = d.pivot(index="date", columns="permno", values="ret")
    piv_prc = d.pivot(index="date", columns="permno", values="prc")
    piv_dv = d.assign(dv=d.prc * d.vol).pivot(index="date", columns="permno", values="dv")
    logret = np.log1p(piv_ret)
    mlog = np.log1p(piv_ret.mean(axis=1))
    rv60 = logret.rolling(60, min_periods=40).std() * math.sqrt(252)
    dd20 = piv_prc / piv_prc.rolling(20, min_periods=15).max() - 1.0
    dv20 = piv_dv.rolling(20, min_periods=15).median()
    liquid = (piv_prc >= 2.0) & (dv20 >= 2e6)

    def fwd(h):
        f = np.exp(logret.shift(-1).rolling(h).sum().shift(-(h - 1))) - 1.0
        m = np.exp(mlog.shift(-1).rolling(h).sum().shift(-(h - 1))) - 1.0
        return f, m

    def stats(mask, h, dates):
        f, m = fwd(h)
        rows = []
        for t in dates:
            sel = mask.loc[t]
            sel = sel[sel].index
            if len(sel) < 3:
                continue
            r = f.loc[t, sel].dropna()
            if len(r) < 3:
                continue
            rows.append((t, float(r.mean()), float(m.loc[t]), int(len(r))))
        if len(rows) < 8:
            return {"n": len(rows)}
        df = pd.DataFrame(rows, columns=["t", "b", "m", "n"])
        ex = df.b - df.m
        return {"n": int(len(df)), "excess": round(float(ex.mean()), 4), "median": round(float(ex.median()), 4),
                "hit": round(float((ex > 0).mean()), 2), "t": round(float(ex.mean() / (ex.std(ddof=1) / math.sqrt(len(ex)))), 2),
                "wealth": round(float(np.prod(1 + df.b)), 2), "mkt": round(float(np.prod(1 + df.m)), 2),
                "names": round(float(df.n.mean()), 1)}

    out = {}
    cell = liquid & (rv60 >= 1.0) & (dd20 <= -0.50)
    print("BY HOLD (rv>=100%, dd20<=-50%):")
    for h in (1, 3, 5, 10):
        dates = piv_ret.index[::h]
        s = stats(cell, h, dates); out[f"hold_{h}"] = s
        print(f"  hold {h:>2}: {s}")
    print("\nBY YEAR (hold 5):")
    dates5 = piv_ret.index[::5]
    out["by_year"] = {}
    for y in range(2013, 2025):
        dy = [t for t in dates5 if t.year == y]
        s = stats(cell, 5, dy); out["by_year"][y] = s
        print(f"  {y}: {s}")
    print("\nEDGES (hold 5):")
    out["edges"] = {}
    for name, m in [("rv>=0.8, dd<=-0.50", liquid & (rv60 >= 0.8) & (dd20 <= -0.50)),
                    ("rv>=1.0, dd<=-0.40", liquid & (rv60 >= 1.0) & (dd20 <= -0.40)),
                    ("rv>=1.0, -0.60<dd<=-0.50", liquid & (rv60 >= 1.0) & (dd20 <= -0.50) & (dd20 > -0.60)),
                    ("rv>=1.0, dd<=-0.60", liquid & (rv60 >= 1.0) & (dd20 <= -0.60)),
                    ("rv>=1.5, dd<=-0.50", liquid & (rv60 >= 1.5) & (dd20 <= -0.50))]:
        s = stats(m, 5, dates5); out["edges"][name] = s
        print(f"  {name:<28}: {s}")
    print("\nBY SIZE tercile inside the cell (hold 5):")
    out["by_size"] = {}
    # dollar-volume tercile across the whole liquid universe on each date
    rank = dv20.rank(axis=1, pct=True)
    for name, lo, hi in [("small", 0.0, 1 / 3), ("mid", 1 / 3, 2 / 3), ("large", 2 / 3, 1.01)]:
        s = stats(cell & (rank >= lo) & (rank < hi), 5, dates5); out["by_size"][name] = s
        print(f"  {name}: {s}")
    OUT.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(f"receipt: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
