"""How many SESSIONS is the edge? And what were they? — the check that found a bug.

    python -m scripts.portfolio_farm_concentration
    python -m scripts.portfolio_farm_concentration --signals mom_12_1 liquid
    python -m scripts.portfolio_farm_concentration --start 1993 --end 2024 --reduce

WHY THIS IS WORTH RUNNING BEFORE ANYTHING ELSE
==============================================
A twelve-year excess return is an average over ~3,000 numbers, and an average
hides whether it came from 3,000 small edges or from ten enormous ones. Those
are completely different claims and a leaderboard cannot tell them apart.

**It also catches instrument defects that no unit test was looking for**, which
is how it earned its place. Run on `mom_12_1 / h5 / k10` over 2013-2024, it
reported that the top session was 2015-01-02 at **+36.34%** — and that the same
date was the top session for `mom_6_1` too, at +35.53%. An identical extreme on
one date for two different rules is not a strategy, it is an instrument.

It was permno 85035's 1-for-4 reverse split. The panel marked SHARE COUNTS at
raw prices, so every corporate action in the sample was being booked as a
return (`test_portfolio_farm_split_adjustment.py`). Fixing it moved the
`liquid` signal from t=0.26 to t=2.55.

So the rule this encodes: **print the dates, not just the distribution.** The
histogram said "fat-tailed", which is true of every equity strategy and would
have explained nothing. The DATES said "same day, two rules".

READING IT
==========
Two columns matter and they must be read together:

  `drop best N`   excess after removing the N best sessions
  `drop worst N`  the symmetric control

A strategy whose best-N collapse is dramatic AND whose worst-N control is
equally dramatic simply has fat tails, which is not news. The finding, if there
is one, is the ASYMMETRY — and the dates.

MEASURED 2013-2024 after the split fix, `mom_12_1 / h5 / k10 / inverse_vol`:

    excess 13.72%/yr over 2,746 sessions
    drop best  1 ->  12.37%     drop worst  1 -> 14.6%
    drop best  5 ->   8.35%     drop worst  5 -> 17.9%
    drop best 10 ->   4.46%     drop worst 10 -> 21.2%
    drop best 20 ->  -2.50%     drop worst 20 -> 27.2%

**Ten sessions out of 2,746 — 0.36% of the sample — carry two thirds of the
edge, and twenty carry all of it.** The upside tail is the larger one (removing
the best 10 costs 9.3 points, removing the worst 10 gains 7.5), which is what a
momentum book should look like; but a rule whose entire measured advantage
lives in twenty days has not been shown to have an advantage at this sample
size, and that is the same statement as its t of 1.35.

The surviving dates are their own finding: after the split fix, **8 of the top
10 sessions for `mom_12_1` and 9 of 10 for `mom_6_1` fall in 2021**. That is a
specific, checkable claim about where the 2019-2024 sub-period advantage came
from, and it is not a claim a leaderboard could have made.

AND THE CONTRAST, WHICH IS THE MOST USEFUL OUTPUT
=================================================
`liquid` behaves completely differently on the same measure:

    drop best 10 -> 66.2% of its edge survives   (mom_12_1: 32.5%)
    largest single session   +5.18%              (mom_12_1: +14.75%)
    top-10 sessions spread over NINE YEARS       (mom_12_1: 2020-21)

So on every axis this file measures — concentration in time, size of the
largest day, spread across regimes — `liquid` is the better-behaved rule, and
that agrees with it having the best t and the lowest tracking error on the
grid. Its one bad property is the breadth decay
(`portfolio_farm_breadth_power`), which says the edge is mega-cap
concentration. Both readings are consistent: a persistent, low-tracking-error
bet on the largest names in a decade that rewarded them.

A SHARED DATE IS A FLAG, NOT A VERDICT
======================================
The script prints the dates that appear in EVERY signal's top ten and tells you
to inspect the panel there. On 2013-2024 that is `2021-03-09`, and inspection
clears it: no `cfacpr` change on that date, market +1.77%, cross-sectional mean
return +2.59% with a p99 of +19.63% — a genuine broad growth-rebound day that a
high-beta book would have loved. The flag did its job by being cheap to
dismiss.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from backend.services.portfolio_farm import (bootstrap as B, farm,  # noqa: E402
                                             panel as P)
from backend.services.portfolio_farm.policy import Policy  # noqa: E402

HOLDING_DAYS = 5
TOP_K = 10
SIZING = "inverse_vol"
DROPS = (1, 3, 5, 10, 20, 40)
N_DATES_SHOWN = 10


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", type=int, default=2013)
    ap.add_argument("--end", type=int, default=2024)
    ap.add_argument("--reduce", action="store_true")
    ap.add_argument("--signals", nargs="*",
                    default=["mom_12_1", "mom_6_1", "liquid"])
    a = ap.parse_args(argv)

    pan = P.load_panel(a.start, a.end,
                       reduce_for_universe_n=(500 if a.reduce else None))
    bench_all = P.market_benchmark(pan.dates)
    print(f"EXCESS CONCENTRATION — {a.start}-{a.end}, h={HOLDING_DAYS} "
          f"k={TOP_K} {SIZING}, median phase")
    print(f"  panel {pan.shape[0]:,} sessions x {pan.shape[1]:,} permnos\n")

    pols = [Policy(signal=s, holding_days=HOLDING_DAYS, top_k=TOP_K,
                   sizing=SIZING, phase_offset=p)
            for s in a.signals for p in range(HOLDING_DAYS)]
    res = farm.run_many(pan, pols, progress=False)

    out, top_dates = [], {}
    for s in a.signals:
        g = sorted([r for r in res if r.policy.signal == s
                    and r.metrics.get("status") == "ok"],
                   key=lambda r: r.metrics["terminal_usd"])
        if not g:
            continue
        lead = g[len(g) // 2]
        dates = np.asarray([str(x) for x in lead.dates])
        w0 = len(pan.dates) - len(lead.dates)
        sr = B.daily_returns(lead.nav)
        bm = bench_all[w0:]
        n = min(sr.size, bm.size)
        ok = np.isfinite(sr[:n]) & np.isfinite(bm[:n])
        d_full = np.where(ok, sr[:n] - bm[:n], np.nan)
        d = d_full[ok]
        total = float(d.mean()) * 252
        order = np.argsort(-d)

        print(f"{s}  —  {d.size:,} sessions, excess {100*total:.2f}%/yr")
        print(f"  {'N':>4} {'drop best':>11} {'share left':>11} "
              f"{'drop worst':>11}")
        rows = []
        for m in DROPS:
            kb = np.ones(d.size, bool); kb[order[:m]] = False
            kw = np.ones(d.size, bool); kw[order[-m:]] = False
            eb, ew = d[kb].mean() * 252, d[kw].mean() * 252
            rows.append({"n": m, "excess_drop_best_pct": round(100*eb, 3),
                         "excess_drop_worst_pct": round(100*ew, 3),
                         "share_of_original": (round(float(eb/total), 3)
                                               if total else None)})
            print(f"  {m:>4} {100*eb:>10.2f}% "
                  f"{(eb/total if total else 0):>10.1%} {100*ew:>10.2f}%")

        # THE DATES. The distribution said "fat-tailed" and explained nothing;
        # the dates said "same day, two rules" and found a bug.
        idx_full = np.argsort(-np.nan_to_num(d_full, nan=-1e9))[:N_DATES_SHOWN]
        picked = sorted(int(i) for i in idx_full)
        print(f"  top {N_DATES_SHOWN} sessions:")
        for i in picked:
            print(f"     {dates[i]}  {100*d_full[i]:+.2f}%")
        yrs = Counter(str(dates[i])[:4] for i in picked)
        print(f"  by year: {dict(sorted(yrs.items()))}\n")
        top_dates[s] = [str(dates[i]) for i in picked]
        out.append({"signal": s, "n_sessions": int(d.size),
                    "excess_annual_pct": round(100*total, 3),
                    "drops": rows,
                    "top_dates": [{"date": str(dates[i]),
                                   "excess_pct": round(100*float(d_full[i]), 3)}
                                  for i in picked]})

    # the check that found the bug, made automatic
    if len(top_dates) > 1:
        sets = list(top_dates.values())
        shared = set(sets[0]).intersection(*[set(x) for x in sets[1:]])
        print(f"  DATES SHARED BY EVERY SIGNAL'S TOP {N_DATES_SHOWN}: "
              f"{sorted(shared) if shared else 'none'}")
        if shared:
            print("     A date that is an extreme for every rule tested is a "
                  "property of the\n     INSTRUMENT, not of any strategy. That "
                  "is how the split-adjustment bug\n     was found — check the "
                  "panel at those dates before believing the run.")

    path = farm.save({"check": "concentration", "window": [a.start, a.end],
                      "holding_days": HOLDING_DAYS, "top_k": TOP_K,
                      "sizing": SIZING, "reduced": bool(a.reduce),
                      "signals": out,
                      "dates_shared_by_all": sorted(
                          set(list(top_dates.values())[0]).intersection(
                              *[set(x) for x in list(top_dates.values())[1:]]))
                      if len(top_dates) > 1 else []},
                     f"farm_concentration_{a.start}_{a.end}")
    print(f"\n  written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
