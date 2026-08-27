"""WHEN does the equity return actually arrive? Overnight, or during the day?

    python -m scripts.crsp_when_return_happens --start 1993 --end 2024 --reduce

WHY ASK THIS
============
Every strategy this project has built selects WHICH names to hold. The 32-year
test (`FINDING_2026-08-28_VARIANCE_DRAG_ATE_THE_EDGE.md`) says that question is
worth less than nothing at a five-day horizon: our best configuration compounded
at +5.36% against the market's +10.61%.

So ask a different question. The market return decomposes exactly into two
disjoint pieces that we already have the columns for:

    overnight   previous close -> today's OPEN
    intraday    today's open   -> today's CLOSE

They sum to the total (up to the dividend/adjustment terms), they never overlap,
and nothing in this repo has ever looked at them separately. If one of them
carries the whole return, that is a fact about WHEN to hold rather than WHAT,
and it is orthogonal to every signal we have already refuted.

This is a `PRODUCT_EXPERIMENT` measurement, not a claim. It is also cheap: no
selection, no ranking, no leaderboard, so there is no multiplicity to correct.
"""

from __future__ import annotations

import argparse
import math

import numpy as np

from backend.services.portfolio_farm import panel as panel_mod


def stats(name: str, daily: np.ndarray, block: int = 5) -> None:
    """Report the compounded result, then the ratios -- terminal wealth first."""
    d = daily[np.isfinite(daily)]
    if d.size < 100:
        print(f"  {name:<28} too few observations ({d.size})")
        return
    wealth = float(np.prod(1.0 + d))
    yrs = d.size / 252.0
    cagr = (wealth ** (1.0 / yrs) - 1.0) if wealth > 0 else -1.0
    # t on NON-OVERLAPPING blocks, the same denominator the rest of the lab uses
    b = np.add.reduceat(d, np.arange(0, d.size, block))[:-1]
    t = float(np.mean(b) / (np.std(b, ddof=1) / math.sqrt(b.size))) if b.size > 2 else 0.0
    print(f"  {name:<28} {wealth:>12,.2f}x {cagr:>+8.2%} "
          f"{np.mean(d) * 252:>+8.2%} {np.std(d) * math.sqrt(252):>7.1%} {t:>+6.2f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=1993)
    ap.add_argument("--end", type=int, default=2024)
    ap.add_argument("--universe", type=int, default=200)
    ap.add_argument("--reduce", action="store_true")
    args = ap.parse_args()

    print(f"loading CRSP {args.start}-{args.end} ...")
    p = panel_mod.load_panel(args.start, args.end,
                             reduce_for_universe_n=500 if args.reduce else None,
                             with_characteristics=False)
    T, N = p.shape
    print(f"panel {T} x {N}  ({p.dates[0]} .. {p.dates[-1]})\n")

    # Liquidity screen, recomputed each session so the universe is point-in-time.
    with np.errstate(invalid="ignore"):
        dv20 = np.vstack([np.nanmean(p.dolvol[max(0, i - 20):i + 1], axis=0)
                          for i in range(T)])
    dv20 = np.nan_to_num(dv20, nan=0.0)

    overnight = np.full(T, np.nan)
    intraday = np.full(T, np.nan)
    total = np.full(T, np.nan)
    for i in range(1, T):
        dv = dv20[i - 1]                      # decided on YESTERDAY's information
        if int((dv > 0).sum()) <= args.universe:
            continue
        cut = np.partition(dv, -args.universe)[-args.universe]
        m = (dv >= cut) & p.traded[i] & p.traded[i - 1]
        if m.sum() < 20:
            continue
        pc, op, cl = p.close[i - 1, m], p.open_[i, m], p.close[i, m]
        ok = np.isfinite(pc) & np.isfinite(op) & np.isfinite(cl) & (pc > 0) & (op > 0)
        if ok.sum() < 20:
            continue
        overnight[i] = float(np.mean(op[ok] / pc[ok] - 1.0))
        intraday[i] = float(np.mean(cl[ok] / op[ok] - 1.0))
        total[i] = float(np.mean(cl[ok] / pc[ok] - 1.0))

    print(f"EQUAL-WEIGHT top {args.universe}, point-in-time liquidity screen")
    print(f"  {'segment':<28} {'wealth':>12} {'CAGR':>8} {'ann.mean':>8} "
          f"{'ann.vol':>7} {'t/5d':>6}")
    print("  " + "-" * 74)
    stats("CLOSE-to-CLOSE (all of it)", total)
    stats("OVERNIGHT only (close->open)", overnight)
    stats("INTRADAY only (open->close)", intraday)

    print("\n  Gross of costs. Overnight-only trades EVERY session, so it pays the")
    print("  spread twice a day: at ~1bp round trip that is ~2.5%/yr, at 5bps it is")
    print("  ~12.6%/yr. The cost line is the whole question and it is stated, not")
    print("  buried -- a 'result' that dies at realistic costs is not a result.")
    for bps in (1.0, 2.0, 5.0):
        net = overnight - 2.0 * bps / 10_000.0
        d = net[np.isfinite(net)]
        w = float(np.prod(1.0 + d))
        yrs = d.size / 252.0
        print(f"    overnight net of {bps:.0f}bps round trip: "
              f"{w:>10,.2f}x  {(w ** (1 / yrs) - 1) if w > 0 else -1:+7.2%}")

    print("\nBY DECADE (gross)")
    yrs_of = np.array([int(str(d)[:4]) for d in p.dates])
    for lo, hi in ((1993, 1999), (2000, 2009), (2010, 2019), (2020, 2024)):
        s = (yrs_of >= lo) & (yrs_of <= hi)
        for nm, arr in (("total", total), ("overnight", overnight), ("intraday", intraday)):
            d = arr[s]
            d = d[np.isfinite(d)]
            if d.size < 100:
                continue
            w = float(np.prod(1.0 + d))
            y = d.size / 252.0
            print(f"  {lo}-{hi} {nm:<10} {w:>9,.2f}x  "
                  f"{(w ** (1 / y) - 1) if w > 0 else -1:+7.2%}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
