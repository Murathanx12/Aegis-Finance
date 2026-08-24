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

    signal        median$    te%   excess%      t   mde80%   yrs_need
    liquid         98,059   12.6      9.76   2.55    10.72         13
    mom_6_1        93,395   35.7     15.03   1.39    30.29         44
    mom_12_1       85,482   33.6     13.72   1.35    28.46         47
    trend_200      73,990   39.8     13.35   1.11    33.75         70
    size_large     53,546    8.1      2.96   1.21     6.85         58
    mom_12_0       52,438   37.2     10.05   0.89    31.57        108
    ...
    equal (null)   43,122    7.4      0.49   0.22     6.26       1793

**ZERO of thirteen non-null signals produced an effect this window could
resolve at 80% power.** Not the leader, not one.

But the ORDERING is the useful part, and it is not the terminal-wealth
ordering. `liquid` carries the highest t on the board (2.55) at a third of
momentum's tracking error, and would need **13 years** rather than 47. It is
the one row the widened window is likely to settle. Note also that `liquid` and
`size_large` only look like this AFTER the split-adjustment fix — before it,
`liquid` read t=0.26, because forward splits are commonest among large liquid
names and the unadjusted P&L path taxed exactly that book.

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
            for s in names for p in range(HOLDING_DAYS)]
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

    rows.sort(key=lambda r: r["mde_at_80pct_power_annual_pct"])
    hdr = (f"{'signal':<18} {'median$':>10} {'te%':>7} {'excess%':>8} "
           f"{'t':>6} {'mde80%':>7} {'resolves':>9} {'yrs_need':>9}")
    print(hdr); print("-" * len(hdr))
    for r in rows:
        star = "  (null)" if r["is_null"] else ""
        yn = r["years_needed_for_observed_effect"]
        print(f"{r['signal']:<18} {r['terminal_median_usd']:>10,.0f} "
              f"{r['tracking_error_annual_pct']:>7.1f} "
              f"{r['observed_excess_annual_pct']:>8.2f} "
              f"{(r['implied_t'] or 0):>6.2f} "
              f"{r['mde_at_80pct_power_annual_pct']:>7.2f} "
              f"{str(r['sample_can_resolve_observed_effect']):>9} "
              f"{(f'{yn:.0f}' if yn else '-'):>9}{star}")

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
    print("\n  MDE falls with sqrt(T) and a real effect does not, so this table "
          "is the\n  thing to re-run when the window widens — the rows that "
          "move are the ones\n  the extra history bought.")

    path = farm.save({"check": "signal_power", "window": [a.start, a.end],
                      "holding_days": HOLDING_DAYS, "top_k": TOP_K,
                      "sizing": SIZING, "reduced": bool(a.reduce),
                      "rows": rows},
                     f"farm_signal_power_{a.start}_{a.end}")
    print(f"\n  written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
