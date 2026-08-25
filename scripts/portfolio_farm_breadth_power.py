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
(after the 2026-08-25 split-adjustment fix — the pre-fix numbers differed and
the pre-fix RANKING differed more)

    signal        k   median$    te%   excess%      t   mde80%
    mom_12_1     10    85,482   33.6     13.72   1.35    28.46   <- peak t
    mom_12_1     20    60,638   25.4      7.96   1.03    21.54
    mom_12_1     30    43,852   21.0      3.71   0.58    17.80
    mom_12_1     50    51,280   16.4      4.00   0.81    13.89
    liquid       10    98,059   12.6      9.76   2.55    10.72   <- peak t
    liquid       20    48,785    7.4      2.49   1.11     6.29
    liquid       50    34,560    3.5     -1.38  -1.29     2.98
    size_large   10    53,546    8.1      2.96   1.21     6.85   <- peak t
    size_large   50    35,748    5.0     -1.39  -0.91     4.28

**The MDE collapses with breadth exactly as predicted — and the excess
collapses FASTER.** The information ratio peaks at the most concentrated book
the grid contains and decays from there, which is the opposite of what a real
cross-sectional signal does.

Every signal tested shows the same shape, fitted over k=10..50:

    mom_12_1   t vs log(k) slope -0.40,  peak t at k=10
    liquid     t vs log(k) slope -2.37,  peak t at k=10
    size_large t vs log(k) slope -1.24,  peak t at k=10

`liquid` is the sharpest case and the most instructive one. It has the best
t on the whole signal grid (2.55) AND the steepest decay with breadth, and
those are the same fact: at k=10 out of a 500-name liquid universe it is a
ten-name mega-cap book, so its "edge" over 2013-2024 is a bet on mega-cap
dominance in a mega-cap decade, not a cross-sectional signal. Whether that is
a regime or an effect is precisely what 1993-2024 gets to answer.

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


# The receipt name keys on the WINDOW only. A run with `--signals` covers part
# of the grid, so writing it whole would delete every other signal's rows — and
# a partial table that reads as complete is worse than no table.
_CONSTRUCTION = ("window", "holding_days", "sizing", "clean_max_k", "reduced")


def merge_prior(payload: dict, name: str) -> int:
    """Fold in rows from a previous receipt at the SAME construction.

    Returns the number of rows carried forward. Refuses to merge across a
    different holding period / sizing / reduction: those rows are not
    comparable, and a mixed table would hide that.
    """
    import json
    from backend.services.portfolio_farm import farm as _farm

    path = Path(_farm.RESULTS_DIR) / f"{name}.json"
    if not path.exists():
        return 0
    try:
        prior = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    if any(prior.get(k) != payload.get(k) for k in _CONSTRUCTION):
        print(f"  NOT merging {path.name}: different construction "
              f"({ {k: prior.get(k) for k in _CONSTRUCTION} })")
        return 0

    have = {(r["signal"], r["top_k"]) for r in payload["rows"]}
    carried = [r for r in prior.get("rows", ())
               if (r.get("signal"), r.get("top_k")) not in have]
    if not carried:
        return 0
    payload["rows"] = payload["rows"] + carried
    fresh = {r["signal"] for r in payload["rows"] if (r["signal"], r["top_k"]) in have}
    for sig, v in (prior.get("verdicts") or {}).items():
        if sig not in fresh:
            payload["verdicts"].setdefault(sig, v)
    payload["rows"].sort(key=lambda r: (r["signal"], r["top_k"]))
    return len(carried)


def breadth_verdict(ts) -> dict:
    """Score one signal's (k, t, excess) triples for Grinold's shape.

    TWO conditions, because either alone can be produced by one noisy point:
    the fitted trend must RISE and the best information ratio must not sit at
    the narrowest book in the clean range.

    And a THIRD, added 2026-08-25 after the verdict line said "SCALES with
    breadth" about two signals that lose money at every breadth. A rising `t`
    on a NEGATIVE excess is a loss being diluted, not an edge being
    diversified, and the two produce an identical slope. `value_bm` ran
    t -0.77 -> -0.39 and `low_vol` -1.09 -> -0.84; both climb toward zero from
    below and both passed. Grinold's law is about an information ratio
    GROWING, so require the quantity to be positive before scoring how it
    grows.
    """
    kk = np.array([x[0] for x in ts], dtype=float)
    tt = np.array([x[1] for x in ts], dtype=float)
    ee = np.array([x[2] for x in ts], dtype=float)
    slope = float(np.polyfit(np.log(kk), tt, 1)[0])
    peak_k = int(ts[int(np.argmax(tt))][0])
    positive = bool(np.median(ee) > 0)
    return {"t_vs_log_k_slope": round(slope, 3),
            "peak_t_at_k": peak_k,
            "fitted_over_k": [int(kk[0]), int(kk[-1])],
            "median_excess_annual_pct": round(float(np.median(ee)), 3),
            "excess_positive_over_grid": positive,
            "scales_with_breadth": bool(positive and slope > 0
                                        and peak_k > CLEAN_MIN_K)}


def verdict_text(v: dict) -> str:
    if v["scales_with_breadth"]:
        return "SCALES with breadth"
    if not v["excess_positive_over_grid"]:
        return ("excess NEGATIVE across the grid - breadth test N/A, "
                "the loss merely dilutes")
    return "does NOT scale - concentrated, not cross-sectional"


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
                ts.append((k, pw["implied_t"] or 0.0,
                           pw["observed_excess_annual_pct"] or 0.0))
            mark = "" if k <= CLEAN_MAX_K else "   (>40% of universe)"
            print(f"{s:<12} {k:>4} {med:>11,.0f} "
                  f"{pw['tracking_error_annual_pct']:>7.1f} "
                  f"{pw['observed_excess_annual_pct']:>8.2f} "
                  f"{(pw['implied_t'] or 0):>6.2f} "
                  f"{pw['mde_at_80pct_power_annual_pct']:>7.2f} "
                  f"{str(pw['sample_can_resolve_observed_effect']):>9}{mark}")
        if len(ts) >= 3:
            # BOTH conditions, because either alone can be produced by one
            # noisy point: the fitted trend must rise AND the best information
            # ratio must not sit at the narrowest book in the clean range.
            verdicts[s] = breadth_verdict(ts)
            verdict = verdict_text(verdicts[s])
            v = verdicts[s]
            print(f"  -> t vs log(k) slope {v['t_vs_log_k_slope']:+.2f} over "
                  f"k={v['fitted_over_k'][0]}..{v['fitted_over_k'][1]}, peak t "
                  f"at k={v['peak_t_at_k']}: {verdict}" + chr(10))

    print("  A negative slope means the edge lives in the extreme tail of the "
          "ranking\n  and dilutes faster than it diversifies. Grinold says a "
          "real signal does the\n  opposite. This is a diagnostic, not a "
          "verdict: it licenses what to build\n  next, never a claim.")

    payload = {"check": "breadth_power", "window": [a.start, a.end],
               "holding_days": HOLDING_DAYS, "sizing": SIZING,
               "clean_max_k": CLEAN_MAX_K, "reduced": bool(a.reduce),
               "rows": rows, "verdicts": verdicts}
    name = f"farm_breadth_power_{a.start}_{a.end}"
    fresh_signals = {r["signal"] for r in rows}
    kept = merge_prior(payload, name)
    path = farm.save(payload, name)
    if kept:
        carried = sorted({r["signal"] for r in payload["rows"]} - fresh_signals)
        print(f"\n  merged {kept} row(s) for {len(carried)} signal(s) "
              f"({', '.join(carried)}) from the previous receipt")
    print(f"\n  written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
