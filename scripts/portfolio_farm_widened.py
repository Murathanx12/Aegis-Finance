"""Re-ask the farm's question on the WIDEST replayable window, and re-power it.

    python -m scripts.portfolio_farm_widened
    python -m scripts.portfolio_farm_widened --start 1993 --end 2024

WHY THIS RUN EXISTS
===================
Every farm number on the board was computed on 2013-2024, and `power_check` on
the leading candidate said that window could never have answered the question
it was asked:

    tracking error  35.7%/yr    implied t          1.54
    observed excess 16.6%/yr    MDE at 80% power  30.3%/yr
    years available   10.9      YEARS NEEDED        36

That is a fact about the SAMPLE, not about momentum, so it applied equally to
every mechanism queued behind it. The 3.75x rebalance-phase spread, the
1.01x-vs-1.75x sub-period disagreement, the bootstrap CI containing zero and
the reality-check p of 0.126 are four faces of the same variance.

The 2026-08-25 re-pull gave 1990-2012 the columns the simulator's conventions
depend on. What that actually buys is smaller than 35 years and bigger than 12:

  * **1990-1991 are unusable and no pull can fix them.** CRSP began collecting
    open prices in mid-1992, so `openprc` is 0.0% in 1990 and 1991 and 41.6% in
    1992. Without an open there is no next-open fill, and a close-to-close
    fallback books the overnight gap that FOLLOWS the signal.
  * **1990-01..1992-10 are also too thin to screen.** The early PIT universe
    carries 243-475 eligible names in those 32 months against a top-500 cut, so
    the cut IS the screen boundary rather than a selection from a wider set.

Both constraints end at the same place, which is the one reassuring thing about
them: **1993**. That is 32 years against the 36 the effect needs — short of
resolution, but the t-statistic scales with the square root of time, so
1.54 -> ~2.6 IF the effect is stable. Whether it is stable is the actual
question, and 1993-2024 contains the dot-com peak, the GFC and COVID, which
2013-2024 does not.

WHAT WOULD MAKE THIS RUN A DISAPPOINTMENT, AND WHY THAT IS THE POINT
====================================================================
The honest prior is that the excess SHRINKS. 2013-2018 already returned 1.01x
the market on the leading rule while 2019-2024 returned 1.75x, so the effect
was never uniform inside the window it was found in. A 32-year replay that
returns a smaller excess with a tighter interval is a BETTER result than a
12-year replay that returned a larger one with an interval containing zero —
the point was never the number, it was whether the sample could carry it.

RUN ORDER, WHICH IS THE ORDER OF THE QUESTIONS
==============================================
    1. what window is actually replayable, and why not the rest
    2. the holding-period grid, across every rebalance phase
    3. the sub-period split, by decade rather than by half
    4. the power check on the winner, which decides whether 2 and 3 meant
       anything

The panel is LIQUIDITY-REDUCED by default. Over 32 years the dense panel is
~4.8 GB before the frame that builds it, and the reduction was verified to
produce byte-identical NAVs on 2013-2024 across four signals, three holding
periods, two sizings and five phases.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from backend.services.portfolio_farm import (bootstrap as B, farm,  # noqa: E402
                                             panel as P)
from backend.services.portfolio_farm.policy import Policy  # noqa: E402

#: The holding periods the 2013-2024 run found monotonic in gross terms. Kept
#: identical so the two runs answer the same question on different samples.
HOLDING_DAYS = (1, 2, 3, 5, 10, 21, 63)
TOP_K = 10
SIGNAL = "mom_12_1"
SIZING = "inverse_vol"
N_NULL_SEEDS = 10


def _pols(hd: int) -> list[Policy]:
    base = dict(signal=SIGNAL, holding_days=hd, top_k=TOP_K, sizing=SIZING)
    out = [Policy(**base, phase_offset=p) for p in range(hd)][:5]
    nb = {k: v for k, v in base.items() if k != "signal"}
    out += [Policy(signal=s, signal_seed=k, **nb)
            for s in ("random", "random_persistent")
            for k in range(N_NULL_SEEDS)]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", type=int, default=None,
                    help="default: the first replayable year")
    ap.add_argument("--end", type=int, default=2024)
    ap.add_argument("--no-reduce", action="store_true")
    ap.add_argument("--n-boot", type=int, default=1000)
    a = ap.parse_args(argv)

    # ── 1. what is replayable, and what is not ─────────────────────────────
    usable = P.replayable_years()
    print("REPLAYABLE WINDOW")
    print(f"  years on disk certified replayable: {usable[0]}-{usable[-1]} "
          f"({len(usable)} years)")
    refused = sorted(set(P.available_years()) - set(usable))
    if refused:
        print(f"  refused: {refused}")
        for y in refused[:4]:
            cov = P.year_open_coverage(y)
            miss = sorted(P.REQUIRED_COLUMNS - P.year_columns(y))
            why = (f"openprc coverage {cov:.1%} < {P.OPEN_COVERAGE_FLOOR:.0%}"
                   if not miss else f"missing columns {miss}")
            print(f"     {y}: {why}")
    start = a.start if a.start is not None else usable[0]
    if start not in usable:
        print(f"\n  REFUSING: {start} is not replayable.")
        return 1
    print(f"\n  running {start}-{a.end}\n")

    t0 = time.time()
    pan = P.load_panel(start, a.end,
                       reduce_for_universe_n=(None if a.no_reduce else 500))
    print(f"  panel {pan.shape[0]:,} sessions x {pan.shape[1]:,} permnos, "
          f"openprc usable on {pan.open_coverage:.2%} of traded cells "
          f"({time.time()-t0:.0f}s)")
    bench_all = P.market_benchmark(pan.dates)

    # ── 2. the holding grid ────────────────────────────────────────────────
    print(f"\nHOLDING GRID — {SIGNAL} / k={TOP_K} / {SIZING}, median across "
          f"phases, nulls at matching settings")
    hdr = (f"{'hold':>5} {'median$':>12} {'worst$':>12} {'best$':>12} "
           f"{'market$':>11} {'x mkt':>7} {'phases':>7}")
    print(hdr); print("-" * len(hdr))

    rows, keep = [], {}
    for hd in HOLDING_DAYS:
        res = farm.run_many(pan, _pols(hd), progress=False)
        ph = [r for r in farm.across_phases(res) if not r["is_null_control"]]
        if not ph:
            continue
        r0 = ph[0]
        bench = next((x.metrics.get("benchmark_terminal_usd") for x in res
                      if x.metrics.get("benchmark_terminal_usd")), None)
        med = r0.get("terminal_median_usd") or 0.0
        rows.append({"holding_days": hd, **r0, "benchmark_terminal_usd": bench})
        keep[hd] = res
        print(f"{hd:>5} {med:>12,.0f} "
              f"{(r0.get('terminal_min_usd') or 0):>12,.0f} "
              f"{(r0.get('terminal_max_usd') or 0):>12,.0f} "
              f"{(bench or 0):>11,.0f} "
              f"{(med/bench if bench else 0):>7.2f} "
              f"{r0.get('n_phases','-'):>7}")

    if not rows:
        print("  no policy produced a phase row")
        return 1
    best = max(rows, key=lambda r: r.get("terminal_median_usd") or 0.0)
    hd = best["holding_days"]
    print(f"\n  best by MEDIAN terminal wealth: hold {hd}d")

    # ── 3. by decade, not by half ──────────────────────────────────────────
    print("\nBY DECADE (the split 2013-2024 could not do)")
    print(f"  {'window':<12} {'median$':>12} {'market$':>12} {'x mkt':>7}")
    print("  " + "-" * 46)
    decades = [(y, min(y + 9, a.end)) for y in range(start, a.end + 1, 10)]
    dec_rows = []
    for s, e in decades:
        if e - s < 4:
            print(f"  {s}-{e:<7}  fewer than five years — not reported")
            continue
        pd_ = P.load_panel(s, e,
                           reduce_for_universe_n=(None if a.no_reduce else 500))
        rr = farm.run_many(pd_, _pols(hd), progress=False)
        pp = [x for x in farm.across_phases(rr) if not x["is_null_control"]]
        bm = next((x.metrics.get("benchmark_terminal_usd") for x in rr
                   if x.metrics.get("benchmark_terminal_usd")), None)
        m = (pp[0].get("terminal_median_usd") if pp else 0.0) or 0.0
        dec_rows.append({"window": [s, e], "median_usd": m, "market_usd": bm})
        print(f"  {s}-{e:<7} {m:>12,.0f} {(bm or 0):>12,.0f} "
              f"{(m/bm if bm else 0):>7.2f}")
        del pd_

    # ── 4. the check that decides whether any of the above meant anything ──
    res = keep[hd]
    lead = max((r for r in res if r.policy.signal == SIGNAL),
               key=lambda r: r.metrics["terminal_usd"])
    w0 = len(pan.dates) - len(lead.dates)
    bench = np.where(np.isfinite(bench_all[w0:]), bench_all[w0:], np.nan)
    pw = B.power_check(B.daily_returns(lead.nav), bench)

    print(f"\nPOWER CHECK on hold {hd}d (canon §64 — this is what decides)")
    for k in ("years", "tracking_error_annual_pct", "se_of_mean_excess_pct",
              "observed_excess_annual_pct", "implied_t",
              "mde_at_80pct_power_annual_pct",
              "years_needed_for_observed_effect",
              "sample_can_resolve_observed_effect"):
        print(f"     {k:<38} {pw.get(k)}")

    ci = B.excess_interval(B.daily_returns(lead.nav), bench, n_boot=a.n_boot)
    if ci.get("status") == "ok":
        print(f"\n  bootstrap 95% CI on excess: "
              f"[{ci['ci_lo_pct']:.2f}%, {ci['ci_hi_pct']:.2f}%] "
              f"excludes zero: {ci['excludes_zero']}")

    path = farm.save({"check": "widened", "window": [start, a.end],
                      "signal": SIGNAL, "top_k": TOP_K, "sizing": SIZING,
                      "reduced": not a.no_reduce,
                      "open_coverage": pan.open_coverage,
                      "holding_grid": rows, "best_holding_days": hd,
                      "by_decade": dec_rows, "power": pw, "excess_ci": ci},
                     f"farm_widened_{start}_{a.end}")
    print(f"\n  written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
