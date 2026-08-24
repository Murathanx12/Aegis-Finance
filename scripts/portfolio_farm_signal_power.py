"""Which signals could this sample RESOLVE — asked before which signals won.

    python -m scripts.portfolio_farm_signal_power
    python -m scripts.portfolio_farm_signal_power --start 1993 --end 2024 --reduce

THE QUESTION THIS REPLACES
==========================
`--preset signals` ranks sixteen signals by terminal wealth and prints a
leaderboard. That is the wrong first question, and it has been the wrong first
question for ~1,700 policies: the top row of a leaderboard was selected FOR
being the top row, and canon §64 requires a power check BEFORE any confirmation.

The leading candidate's power check, run after the fact on 2026-08-24, explained
every other result at once — implied t 1.54, MDE 30.3%/yr against a 16.6%/yr
effect, 36 years needed and 10.9 available. So the honest first question about a
signal grid is not "which won" but:

    for each signal, given ITS OWN tracking error against the market,
    what effect would this window have needed in order to detect one?

A signal whose MDE exceeds any plausible excess return **cannot be evaluated
here**, and its position on a leaderboard is noise wearing a rank. That is a
statement about the instrument, not about the signal, and it is knowable before
looking at the outcome.

MEASURED 2013-2024 (h=5, k=10, inverse_vol, median phase, AFTER the split fix)
==============================================================================

    signal        median$    te%  excess%  vs null      t   mde80%   yrs_need
    liquid         98,059   12.6     9.76    13.41   2.55    10.72         13
    mom_6_1        93,395   35.7    15.03    18.68   1.39    30.29         44
    mom_12_1       85,482   33.6    13.72    17.38   1.35    28.46         47
    trend_200      73,990   39.8    13.35    17.00   1.11    33.75         70
    size_large     53,546    8.1     2.96     6.62   1.21     6.85         58
    mom_12_0       52,438   37.2    10.05    13.70   0.89    31.57        108
    ...
    equal (null)   43,122    7.4     0.49     4.14   0.22     6.26       1793

TWO BENCHMARKS, BOTH NAMED
==========================
`excess%` is against the CAP-WEIGHTED market — the question "should I hold this
instead of an index fund". But a 10-name book drawn from a 500-name liquid
universe is TILTED against that benchmark before any signal is applied, so the
null signals' own excess is the other half of the picture:

    NULL BASELINE over 125 draws (12 seeds x 5 phases x the null signals)
    median -3.66%/yr,  5th-95th percentile [-9.77, +1.00]

`vs null` is against that — the question "does the signal add information".
They are different questions and a row that answers one does not answer the
other.

**The null SPREAD is the intuition behind every MDE in the table.** Ten points
separate the 5th and 95th percentile of doing nothing at all: pick ten names at
random instead of ten other names at random, and twelve years later you are
anywhere in a ten-point-wide band. An "edge" narrower than that band cannot be
told from which names you happened to pick — and every non-null row above is
inside it.

One draw is not a baseline. At seed 0 alone, `random` returned -11.00%/yr over
2013-2018, which is near the 5th percentile — reading that single number as
"the construction drag" would have inflated every signal's `vs null` by about
seven points.

**ZERO of thirteen non-null signals produced an effect this window could
resolve at 80% power.** Not the leader, not one.

But the ORDERING is the useful part, and it is not the terminal-wealth
ordering. `liquid` carries the highest t on the board (2.55) at a third of
momentum's tracking error, and would need **13 years** rather than 47. It is
the one row the widened window is likely to settle. Note also that `liquid` and
`size_large` only look like this AFTER the split-adjustment fix — before it,
`liquid` read t=0.26, because forward splits are commonest among large liquid
names and the unadjusted P&L path taxed exactly that book.

AND THE MULTIPLICITY, WHICH NO PER-SIGNAL t CAN SEE
====================================================
White's Reality Check over all sixteen signals (nulls in the pool, because they
are what "the best of N tries under no effect" looks like):

    best of sixteen    mom_6_1 at 15.03%/yr
    reality-check p    0.358

**The best of sixteen signals is unremarkable against the search that found
it.** A t of 2.55 read off the top row is a t that was selected for being the
top row, and 0.358 is what that costs. This does not retire any signal — it
says the grid has produced nothing a claim could rest on, which is the same
answer the per-signal MDEs give, arrived at from the other direction.

WHY THIS IS THE DIRECT ATTACK ON THE STATED BOTTLENECK
=======================================================
`CLAUDE.md`: *all ten arena books declare `selection: composite_top_k` over ONE
signal — they differ in portfolio treatment, not in alpha source*, and
`COMPOSITE_WEIGHTS` coverage is `{"1": 206, "6": 1}`, so the composite IS 12-1
momentum for 99.5% of names. The roadmap wants INDEPENDENT selectors.

An independent selector is only worth building if the sample can tell it apart
from momentum. This table says, per signal and before any outcome is consulted,
whether that comparison was ever available — and it is the natural thing to
re-run once the window widens, because MDE falls with sqrt(T) while a real
effect does not.

READING THE OUTPUT
==================
  `te`        annualised tracking error of the signal's book vs the market
  `excess`    its observed annualised excess return (the thing under test)
  `t`         excess / standard error
  `mde80`     the excess this window could have detected at 80% power
  `resolves`  excess > mde80 — FALSE means the row answered nothing
  `yrs_need`  years this window would need for the OBSERVED effect

A row with `resolves=False` and a large positive `excess` is the dangerous one:
it looks like a winner and is indistinguishable from noise at this sample size.
Sorted by MDE, cheapest-to-resolve first, so the ordering itself is the finding
rather than the wealth column.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from backend.services.portfolio_farm import (bootstrap as B, farm,  # noqa: E402
                                             panel as P, signals as SIG)
from backend.services.portfolio_farm.policy import Policy  # noqa: E402

#: Held fixed across signals so the comparison is a signal comparison. These are
#: the leading candidate's own settings, which is the only reason to prefer them.
HOLDING_DAYS = 5
TOP_K = 10
SIZING = "inverse_vol"

#: Seeds per NULL signal. One draw is not a baseline: `random` at seed 0
#: returned -11.00%/yr over 2013-2018 and -2.99%/yr over 2013-2024, and the
#: difference between those is mostly which ten names one seed happened to pick.
#: The baseline is the median across seeds, and the spread across them is
#: printed so a reader can see how much of it is draw noise.
NULL_SEEDS = 12


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", type=int, default=2013)
    ap.add_argument("--end", type=int, default=2024)
    ap.add_argument("--reduce", action="store_true")
    a = ap.parse_args(argv)

    pan = P.load_panel(a.start, a.end,
                       reduce_for_universe_n=(500 if a.reduce else None))
    bench_all = P.market_benchmark(pan.dates)
    print(f"SIGNAL POWER — {a.start}-{a.end}, h={HOLDING_DAYS} k={TOP_K} "
          f"{SIZING}, median phase per signal")
    print(f"  panel {pan.shape[0]:,} sessions x {pan.shape[1]:,} permnos, "
          f"openprc usable on {pan.open_coverage:.2%} of traded cells\n")

    names = [s for s in SIG.SIGNALS]
    pols = [Policy(signal=s, holding_days=HOLDING_DAYS, top_k=TOP_K,
                   sizing=SIZING, phase_offset=p)
            for s in names if s not in SIG.NULL_SIGNALS
            for p in range(HOLDING_DAYS)]
    # every null gets several SEEDS as well as every phase — a null signal's
    # whole job is to say what "no information" looks like, and one draw of ten
    # names cannot do that.
    pols += [Policy(signal=s, holding_days=HOLDING_DAYS, top_k=TOP_K,
                    sizing=SIZING, phase_offset=p, signal_seed=k)
             for s in names if s in SIG.NULL_SIGNALS
             for p in range(HOLDING_DAYS)
             for k in (range(NULL_SEEDS) if s != "equal" else (0,))]
    res = farm.run_many(pan, pols, progress=False)

    rows = []
    by_sig: dict[str, list] = {}
    for r in res:
        if r.metrics.get("status") == "ok":
            by_sig.setdefault(r.policy.signal, []).append(r)
    for s, group in by_sig.items():
        # the MEDIAN phase, so the row is a property of the rule and not of the
        # calendar alignment that happened to be tried
        group.sort(key=lambda r: r.metrics["terminal_usd"])
        lead = group[len(group) // 2]
        w0 = len(pan.dates) - len(lead.dates)
        bench = np.where(np.isfinite(bench_all[w0:]), bench_all[w0:], np.nan)
        pw = B.power_check(B.daily_returns(lead.nav), bench)
        if pw.get("status") != "ok":
            continue
        rows.append({
            "signal": s,
            "is_null": s in SIG.NULL_SIGNALS,
            "terminal_median_usd": float(np.median(
                [g.metrics["terminal_usd"] for g in group])),
            **{k: pw.get(k) for k in
               ("tracking_error_annual_pct", "observed_excess_annual_pct",
                "implied_t", "mde_at_80pct_power_annual_pct",
                "years_needed_for_observed_effect",
                "sample_can_resolve_observed_effect", "years")},
        })

    # WHITE'S REALITY CHECK over the whole grid. A t read off the BEST of
    # sixteen signals was selected for being the best of sixteen, and a
    # per-signal power check cannot see that. The nulls stay in the pool on
    # purpose: they are what 'the best of N tries under no effect' looks like.
    excess_by_signal = {}
    for s, group in by_sig.items():
        group.sort(key=lambda r: r.metrics['terminal_usd'])
        lead = group[len(group) // 2]
        w0 = len(pan.dates) - len(lead.dates)
        sr = B.daily_returns(lead.nav)
        bm = bench_all[w0:]
        n = min(sr.size, bm.size)
        excess_by_signal[s] = np.where(
            np.isfinite(sr[:n]) & np.isfinite(bm[:n]), sr[:n] - bm[:n], np.nan)
    rc = B.reality_check(excess_by_signal)

    # THE NULL BASELINE, and it is not zero. The benchmark is the CAP-WEIGHTED
    # market, so any 10-name book drawn from a 500-name liquid universe carries
    # a structural tilt against it before any signal is applied. Measured
    # 2013-2018: a RANDOM top-10 book returns -11.00%/yr of "excess". Reporting
    # a signal's excess against the market without that number beside it
    # invites reading construction drag as signal, in either direction.
    # median over EVERY null draw, not over the three null signals' medians
    null_draws = []
    for s, group in by_sig.items():
        if s not in SIG.NULL_SIGNALS:
            continue
        for r in group:
            w0 = len(pan.dates) - len(r.dates)
            bm = bench_all[w0:]
            sr = B.daily_returns(r.nav)
            n = min(sr.size, bm.size)
            ok2 = np.isfinite(sr[:n]) & np.isfinite(bm[:n])
            if ok2.sum() > 252:
                null_draws.append(float((sr[:n] - bm[:n])[ok2].mean()) * 252 * 100)
    null_base = float(np.median(null_draws)) if null_draws else 0.0
    null_lo, null_hi = ((float(np.percentile(null_draws, 5)),
                         float(np.percentile(null_draws, 95)))
                        if null_draws else (0.0, 0.0))
    for r in rows:
        r["null_baseline_excess_annual_pct"] = round(null_base, 3)
        r["excess_vs_null_annual_pct"] = round(
            r["observed_excess_annual_pct"] - null_base, 3)

    rows.sort(key=lambda r: r["mde_at_80pct_power_annual_pct"])
    hdr = (f"{'signal':<18} {'median$':>10} {'te%':>7} {'excess%':>8} "
           f"{'vs null':>8} {'t':>6} {'mde80%':>7} {'resolves':>9} "
           f"{'yrs_need':>9}")
    print(hdr); print("-" * len(hdr))
    for r in rows:
        star = "  (null)" if r["is_null"] else ""
        yn = r["years_needed_for_observed_effect"]
        print(f"{r['signal']:<18} {r['terminal_median_usd']:>10,.0f} "
              f"{r['tracking_error_annual_pct']:>7.1f} "
              f"{r['observed_excess_annual_pct']:>8.2f} "
              f"{r['excess_vs_null_annual_pct']:>8.2f} "
              f"{(r['implied_t'] or 0):>6.2f} "
              f"{r['mde_at_80pct_power_annual_pct']:>7.2f} "
              f"{str(r['sample_can_resolve_observed_effect']):>9} "
              f"{(f'{yn:.0f}' if yn else '-'):>9}{star}")

    print("")
    print(f"  NULL BASELINE over {len(null_draws)} null draws "
          f"(seeds x phases): median {null_base:+.2f}%/yr, "
          f"5-95pct [{null_lo:+.2f}, {null_hi:+.2f}]")
    print("     The benchmark is the CAP-WEIGHTED market, so a 10-name book "
          "from a 500-name")
    print("     liquid universe is tilted against it before any signal is "
          "applied.")
    print("     `excess%` is vs the MARKET (should I hold this instead of an "
          "index);")
    print("     `vs null` is vs a random book of the SAME construction (does "
          "the signal")
    print("     add information). Different questions, both named.")

    real = [r for r in rows if not r["is_null"]]
    resolvable = [r for r in real if r["sample_can_resolve_observed_effect"]]
    print(f"\n  {len(resolvable)} of {len(real)} non-null signals produced an "
          f"effect this window could resolve at 80% power.")
    if not resolvable:
        print("  NONE. Every row above is a rank without a resolution behind "
              "it, and\n  a leaderboard over them ranks noise. That is a "
              "statement about the\n  sample, not about the signals — the same "
              "fact as the 3.75x phase spread\n  and the sub-period "
              "disagreement.")
    else:
        print("  " + ", ".join(r["signal"] for r in resolvable))
    cheap = min(real, key=lambda r: r["mde_at_80pct_power_annual_pct"])
    dear = max(real, key=lambda r: r["mde_at_80pct_power_annual_pct"])
    print(f"\n  cheapest to resolve: {cheap['signal']} "
          f"(MDE {cheap['mde_at_80pct_power_annual_pct']:.1f}%/yr, "
          f"te {cheap['tracking_error_annual_pct']:.0f}%)")
    print(f"  dearest to resolve:  {dear['signal']} "
          f"(MDE {dear['mde_at_80pct_power_annual_pct']:.1f}%/yr, "
          f"te {dear['tracking_error_annual_pct']:.0f}%)")
    if rc.get("status") == "ok":
        print("")
        print(f"  WHITE'S REALITY CHECK over all "
              f"{rc['n_policies']} signals (nulls included)")
        print(f"     best              {rc['best_policy']} at "
              f"{rc['best_excess_annual_pct']:.2f}%/yr")
        print(f"     reality-check p   {rc['reality_check_p']}")
        print("     This prices the SEARCH: the top row was selected for "
              "being the top row.")
        print("     A per-signal t cannot see that, and sixteen were tried.")

    print("\n  MDE falls with sqrt(T) and a real effect does not, so this table "
          "is the\n  thing to re-run when the window widens — the rows that "
          "move are the ones\n  the extra history bought.")

    path = farm.save({"check": "signal_power", "window": [a.start, a.end],
                      "holding_days": HOLDING_DAYS, "top_k": TOP_K,
                      "sizing": SIZING, "reduced": bool(a.reduce),
                      "rows": rows, "reality_check": rc,
                      "null_baseline_pct": round(null_base, 3),
                      "null_draws_5_95_pct": [round(null_lo, 3),
                                             round(null_hi, 3)],
                      "n_null_draws": len(null_draws)},
                     f"farm_signal_power_{a.start}_{a.end}")
    print(f"\n  written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
