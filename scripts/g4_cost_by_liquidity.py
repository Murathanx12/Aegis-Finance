"""The surviving 0.26pp/0.55pp had no cost path. This is the cost path.

    python -m scripts.g4_cost_by_liquidity

THE PREDICTION, WRITTEN DOWN BEFORE THE NUMBERS EXIST
=====================================================
From the review, recorded here verbatim so it can be embarrassed:

    "largest in the illiquid tercile, dies there under any reasonable cost
     bound"

The literature says the same thing twice over — Ng, Rusticus & Verdi found the
firms exhibiting more post-earnings drift are precisely those where transaction
costs are higher, and Novy-Marx & Velikov's taxonomy finds high-turnover
anomalies mostly do not survive costs. If our numbers disagree with that, one of
the two is wrong and it is probably ours.

WHY THE BREAK-EVEN IS THE PRIMARY OUTPUT AND "NET OF COSTS" IS NOT
==================================================================
A net return is my cost assumption plus the data. A **break-even cost** is the
data alone: "this edge dies above X basis points per crossing" is a fact about
the measurement, and the reader supplies their own X. Quoting a net number
invites arguing about my spread model instead of about the edge.

So the primary number is the break-even, and an illustrative schedule is
reported beside it, clearly labelled as an assumption.

FOUR CROSSINGS, NOT ONE
=======================
`C - D` is a LONG-SHORT contrast: long the beats, short the misses. Capturing it
means entering both legs and exiting both legs — **four crossings**, each paying
roughly the half-spread plus impact. A break-even quoted per-crossing is
therefore `edge / 4`, and reporting `edge` itself as the break-even (the
tempting simplification) would overstate the survivable cost by 4x.

WHAT THE SPREAD PROXY CAN AND CANNOT SAY
========================================
`hl_range_20d` is the mean daily (high-low)/mid, which runs ~2.3% at the median
here. Real large-cap spreads are a few basis points, so this is an upper bound
so loose it is nearly uninformative as a spread — the daily range is mostly real
price movement. It is used ONLY to rank, never as a cost level. The cost levels
come from a declared schedule, and the break-even is what actually decides.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

DATA = Path(r"C:\Users\mrthn\Aegis module\data\g4\earnings_v1")
N_BOOT = 2000
SEED = 20260817

#: Crossings needed to capture a long-short contrast: in long, in short,
#: out long, out short.
CROSSINGS = 4

#: ILLUSTRATIVE ONLY, and labelled as such wherever it is printed. Round-trip
#: cost per crossing in basis points, by dollar-volume tercile. Anchored on the
#: published equity-anomaly cost taxonomies rather than measured here — we have
#: no TAQ and estimating an effective spread from daily bars would be inventing
#: precision.
ILLUSTRATIVE_BPS = {"illiquid": 25.0, "mid": 10.0, "liquid": 4.0}


def load() -> list[dict]:
    rows: list[dict] = []
    for f in sorted(DATA.glob("*.jsonl")):
        with f.open(encoding="utf-8") as fh:
            rows += [json.loads(l) for l in fh]
    return rows


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    rows = [r for r in load()
            if r.get("numeric_surprise") is not None
            and r.get("market_reaction_tradable") is not None
            and r.get("actual") is not None
            and r.get("dollar_volume_20d")]
    print(f"events with surprise, TRADABLE reaction and liquidity: "
          f"{len(rows):,}")

    dates = np.array([str(r["first_public_ts"])[:10] for r in rows])
    surp = np.array([float(r["numeric_surprise"]) for r in rows])
    eps = np.array([float(r["actual"]) for r in rows])
    dv = np.array([float(r["dollar_volume_20d"]) for r in rows])
    trad = np.array([float(r["market_reaction_tradable"]) for r in rows])
    hl = np.array([float(r["hl_range_20d"]) if r.get("hl_range_20d")
                   else np.nan for r in rows])

    # Date-demean so the day's market move is gone, as in the 2x2.
    dem = np.full_like(trad, np.nan)
    for d in np.unique(dates):
        m = dates == d
        if m.sum() >= 2:
            dem[m] = trad[m] - trad[m].mean()
    keep = ~np.isnan(dem)

    # TERCILES BY YEAR, not pooled: dollar volume grows ~10x over 2006-2019, so
    # a pooled cut would put most of the early sample in "illiquid" and measure
    # the calendar instead of liquidity.
    year = np.array([d[:4] for d in dates])
    terc = np.full(len(rows), -1)
    for y in np.unique(year):
        m = (year == y) & keep
        if m.sum() < 30:
            continue
        q1, q2 = np.quantile(dv[m], [1 / 3, 2 / 3])
        terc[m & (dv <= q1)] = 0
        terc[m & (dv > q1) & (dv <= q2)] = 1
        terc[m & (dv > q2)] = 2
    names = {0: "illiquid", 1: "mid", 2: "liquid"}

    rng = np.random.default_rng(SEED)
    print("\n" + "=" * 74)
    print("C - D : surprise sign WITHIN negative EPS, by liquidity tercile")
    print("        (open-to-close, date-demeaned — the implementable half)")
    print("=" * 74)
    print(f"  {'tercile':<9} {'n':>7} {'median $vol':>12} {'C-D':>9} "
          f"{'SE':>7} {'z':>6} {'MDE':>7} {'break-even':>12}")

    results = {}
    for t in (0, 1, 2):
        m = keep & (terc == t)
        # The C/D cells: negative EPS, surprise sign either way.
        c = m & (eps <= 0) & (surp > 0)
        d_ = m & (eps <= 0) & (surp <= 0)
        if c.sum() < 30 or d_.sum() < 30:
            print(f"  {names[t]:<9} too few events ({c.sum()}/{d_.sum()})")
            continue
        est = dem[c].mean() - dem[d_].mean()
        # Block bootstrap over dates, within this tercile.
        uniq = np.unique(dates[m])
        idx = {u: np.flatnonzero(m & (dates == u)) for u in uniq}
        boots = np.empty(N_BOOT)
        for b in range(N_BOOT):
            pick = rng.choice(uniq, size=len(uniq), replace=True)
            sel = np.concatenate([idx[u] for u in pick])
            cc = sel[(eps[sel] <= 0) & (surp[sel] > 0)]
            dd = sel[(eps[sel] <= 0) & (surp[sel] <= 0)]
            boots[b] = (dem[cc].mean() - dem[dd].mean()
                        if len(cc) and len(dd) else np.nan)
        se = float(np.nanstd(boots, ddof=1))
        be = 1e4 * est / CROSSINGS          # bps per crossing
        results[names[t]] = {"n": int(m.sum()), "est": est, "se": se,
                             "breakeven_bps": be,
                             "median_dv": float(np.median(dv[m])),
                             "median_hl": float(np.nanmedian(hl[m]))}
        z = est / se if se > 0 else float("nan")
        mde = (1.959964 + 0.8416212) * se
        results[names[t]].update(z=z, mde=mde)
        print(f"  {names[t]:<9} {int(m.sum()):>7,} "
              f"${np.median(dv[m])/1e6:>10.0f}M {100*est:>8.2f}pp "
              f"{100*se:>6.2f}pp {z:>+6.1f} {100*mde:>6.2f}pp "
              f"{be:>10.1f}bp"
              + ("" if abs(est) >= mde else "   [below MDE]"))

    if len(results) < 2:
        print("\ninsufficient coverage to compare terciles.")
        return 1

    print("\n  THE PREDICTION UNDER TEST: 'largest in the illiquid tercile,")
    print("  dies there under any reasonable cost bound'")
    il, lq = results.get("illiquid"), results.get("liquid")
    if il and lq:
        d_ = il["est"] - lq["est"]
        print(f"    illiquid - liquid = {100*d_:+.2f}pp "
              f"({'illiquid larger' if d_ > 0 else 'liquid larger'})")
        print(f"    -> first half of the prediction "
              f"{'HOLDS' if d_ > 0 else 'FAILS'}")

    print("\n  DIES OR SURVIVES, against an ILLUSTRATIVE schedule "
          "(an assumption, not a measurement):")
    for k, v in results.items():
        c = ILLUSTRATIVE_BPS[k]
        net = v["est"] - CROSSINGS * c / 1e4
        print(f"    {k:<9} break-even {v['breakeven_bps']:>6.1f}bp/crossing  "
              f"vs assumed {c:>5.1f}bp  ->  net {100*net:+.2f}pp  "
              f"{'SURVIVES' if net > 0 else 'DIES'}")

    print("\n  The break-even is the fact; the schedule is my assumption. A")
    print("  reader who disputes the schedule can read the break-even column")
    print("  and substitute their own number, which is the point of leading")
    print("  with it. Both are BEFORE market impact, before borrow on the")
    print("  short leg, and before the fact that a strategy trading every")
    print("  earnings event in the market moves the prices it is trading.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
