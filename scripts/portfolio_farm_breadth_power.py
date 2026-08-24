"""Does the edge SCALE with breadth? The one diagnostic a leaderboard cannot give.

    python -m scripts.portfolio_farm_breadth_power
    python -m scripts.portfolio_farm_breadth_power --start 1993 --end 2024 --reduce

THE TEST
========
Grinold's fundamental law: `IR ~ IC * sqrt(breadth)`. A genuine cross-sectional
signal applied to more names should produce a HIGHER information ratio, because
independent bets average out idiosyncratic risk faster than they dilute the
edge. A result that is really a handful of large winners in one regime does the
opposite — it peaks at maximum concentration and decays as soon as it is spread.

That distinction is invisible on a terminal-wealth leaderboard, where a
concentrated book wins whenever its few winners were big enough, and it is the
cheapest available test of whether a farm candidate is alpha or luck.

It also matters directly for POWER. `MDE = z * te / sqrt(T)`, and tracking
error falls steeply with breadth, so a wider book needs a much smaller effect to
be detectable. If the excess survived diversification, breadth would be the
cheap way to buy resolution that more history buys expensively.

MEASURED 2013-2024, h=5, inverse_vol, median phase, universe 500
================================================================

    signal        k   median$    te%   excess%      t   mde80%
    mom_12_1      5    33,548   46.7     10.27   0.73    39.58
    mom_12_1     10    77,002   35.7     13.39   1.24    30.31   <- peak t
    mom_12_1     20    47,597   26.1      5.91   0.75    22.17
    mom_12_1     30    34,510   21.3      1.57   0.24    18.09
    mom_12_1     50    39,054   16.8      1.54   0.30    14.25
    mom_6_1      10    83,908   37.6     14.62   1.28    31.93   <- peak t
    mom_6_1      50    37,285   15.4      0.60   0.13    13.04

**The MDE collapses with breadth exactly as predicted — 30.3% at k=10 down to
14.3% at k=50 — and the excess collapses FASTER.** The information ratio peaks
at the most concentrated book the grid contains and decays from there, which is
the opposite of what a real cross-sectional signal does.

All three signals tested show the same shape, fitted over k=10..50:

    mom_12_1   t vs log(k) slope -0.63,  peak t at k=10
    mom_6_1    t vs log(k) slope -0.73,  peak t at k=10
    trend_200  t vs log(k) slope -0.47,  peak t at k=10

So breadth does NOT buy resolution here, and the reason it does not is itself
the finding: **the k=10 result behaves like a small number of large winners
rather than a broad effect.** That is consistent with the sub-period split
(1.01x the market over 2013-2018, 1.75x over 2019-2024) and with a phase spread
of 3.75x, and it is a third independent symptom of the same thing.

WHAT THIS DOES NOT SAY
======================
* It does not say momentum is not real. It says THIS window cannot show it
  scaling, and that a rule selected at k=10 on this window has no breadth
  evidence behind it.
* Rows at `k >= 100` are contaminated as a signal test: with `universe_n=500` a
  200-name book holds 40% of its own universe, so "excess vs the CRSP
  value-weighted market" there is mostly equal-weight-vs-cap-weight and
  liquid-500-vs-total-market, not the signal. The trend is read over
  k=10..50.
* It is a `PRODUCT_EXPERIMENT` diagnostic. It licenses choosing what to build
  next, never a claim.

WHY RE-RUN IT ON A WIDER WINDOW
===============================
MDE falls with `sqrt(T)` and a real effect does not. If the 1993-2024 replay
shows `t` RISING with breadth where 2013-2024 shows it falling, the extra
history bought a different answer and not merely a tighter one. That is the
single most informative comparison the widened sample makes available.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from backend.services.portfolio_farm import (bootstrap as B, farm,  # noqa: E402
                                             panel as P)
from backend.services.portfolio_farm.policy import Policy  # noqa: E402

HOLDING_DAYS = 5
SIZING = "inverse_vol"

#: Stops at 50 for the headline reading. 100 and 200 are run and reported so the
#: contamination is visible rather than hidden, but they are not signal tests.
BREADTHS = (5, 10, 20, 30, 50, 100, 200)
CLEAN_MAX_K = 50

#: The trend is fitted from k=10, not k=5. A five-name book is dominated by
#: single-name idiosyncrasy and is noisy in BOTH directions, and it broke the
#: first version of this diagnostic: `trend_200` returned -23%/yr at k=5, which
#: dragged a straight line through log(k) to a POSITIVE slope and printed
#: "SCALES with breadth" for a series whose t reads 0.68, 0.30, 0.35, -0.16
#: across k=10..50. One outlier at the noisiest end decided the verdict.
CLEAN_MIN_K = 10

SIGNALS = ("mom_12_1", "mom_6_1", "trend_200")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", type=int, default=2013)
    ap.add_argument("--end", type=int, default=2024)
    ap.add_argument("--reduce", action="store_true")
    ap.add_argument("--signals", nargs="*", default=list(SIGNALS))
    a = ap.parse_args(argv)

    pan = P.load_panel(a.start, a.end,
                       reduce_for_universe_n=(500 if a.reduce else None))
    bench_all = P.market_benchmark(pan.dates)
    print(f"BREADTH POWER — {a.start}-{a.end}, h={HOLDING_DAYS} {SIZING}, "
          f"median phase")
    print(f"  panel {pan.shape[0]:,} sessions x {pan.shape[1]:,} permnos, "
          f"openprc usable on {pan.open_coverage:.2%} of traded cells")
    print(f"  Grinold: a real cross-sectional signal should show t RISING with "
          f"k.\n")

    pols = [Policy(signal=s, holding_days=HOLDING_DAYS, top_k=k,
                   sizing=SIZING, phase_offset=p)
            for s in a.signals for k in BREADTHS
            for p in range(HOLDING_DAYS)]
    res = farm.run_many(pan, pols, progress=False)

    groups: dict[tuple, list] = {}
    for r in res:
        if r.metrics.get("status") == "ok":
            groups.setdefault((r.policy.signal, r.policy.top_k), []).append(r)

    hdr = (f"{'signal':<12} {'k':>4} {'median$':>11} {'te%':>7} "
           f"{'excess%':>8} {'t':>6} {'mde80%':>7} {'resolves':>9}")
    rows, verdicts = [], {}
    for s in a.signals:
        print(hdr); print("-" * len(hdr))
        ts = []
        for k in BREADTHS:
            g = groups.get((s, k))
            if not g:
                continue
            g.sort(key=lambda r: r.metrics["terminal_usd"])
            lead = g[len(g) // 2]
            w0 = len(pan.dates) - len(lead.dates)
            bench = np.where(np.isfinite(bench_all[w0:]), bench_all[w0:],
                             np.nan)
            pw = B.power_check(B.daily_returns(lead.nav), bench)
            if pw.get("status") != "ok":
                continue
            med = float(np.median([x.metrics["terminal_usd"] for x in g]))
            rows.append({"signal": s, "top_k": k, "median_usd": med, **pw})
            if CLEAN_MIN_K <= k <= CLEAN_MAX_K:
                ts.append((k, pw["implied_t"] or 0.0))
            mark = "" if k <= CLEAN_MAX_K else "   (>40% of universe)"
            print(f"{s:<12} {k:>4} {med:>11,.0f} "
                  f"{pw['tracking_error_annual_pct']:>7.1f} "
                  f"{pw['observed_excess_annual_pct']:>8.2f} "
                  f"{(pw['implied_t'] or 0):>6.2f} "
                  f"{pw['mde_at_80pct_power_annual_pct']:>7.2f} "
                  f"{str(pw['sample_can_resolve_observed_effect']):>9}{mark}")
        if len(ts) >= 3:
            kk = np.array([x[0] for x in ts], dtype=float)
            tt = np.array([x[1] for x in ts], dtype=float)
            slope = float(np.polyfit(np.log(kk), tt, 1)[0])
            peak_k = int(ts[int(np.argmax(tt))][0])
            # BOTH conditions, because either alone can be produced by one
            # noisy point: the fitted trend must rise AND the best information
            # ratio must not sit at the narrowest book in the clean range.
            scales = bool(slope > 0 and peak_k > CLEAN_MIN_K)
            verdicts[s] = {"t_vs_log_k_slope": round(slope, 3),
                           "peak_t_at_k": peak_k,
                           "fitted_over_k": [int(kk[0]), int(kk[-1])],
                           "scales_with_breadth": scales}
            verdict = ("SCALES with breadth" if scales else
                       "does NOT scale - concentrated, not cross-sectional")
            print(f"  -> t vs log(k) slope {slope:+.2f} over k="
                  f"{int(kk[0])}..{int(kk[-1])}, peak t at k={peak_k}: "
                  f"{verdict}" + chr(10))

    print("  A negative slope means the edge lives in the extreme tail of the "
          "ranking\n  and dilutes faster than it diversifies. Grinold says a "
          "real signal does the\n  opposite. This is a diagnostic, not a "
          "verdict: it licenses what to build\n  next, never a claim.")

    path = farm.save({"check": "breadth_power", "window": [a.start, a.end],
                      "holding_days": HOLDING_DAYS, "sizing": SIZING,
                      "clean_max_k": CLEAN_MAX_K, "reduced": bool(a.reduce),
                      "rows": rows, "verdicts": verdicts},
                     f"farm_breadth_power_{a.start}_{a.end}")
    print(f"\n  written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
