"""Does the competition's winning rule survive 32 years of CRSP?

    python -m scripts.crsp_five_day_momentum --start 1993 --end 2024 --reduce

The Alpaca lab found `mega-cap mom 6m k=5` -- six-month trailing return, top 5
of a liquid universe, held five sessions -- at t=2.99 over two years and t=2.62
over one. Two years is ONE AI regime, and every farm result on record says a
window that omits a regime produces a number dressed as a target.

So the same rule is replayed here on the same frozen CRSP history every other
farm result uses: decide at the close, fill at the NEXT OPEN, pay costs, and
report the t on NON-OVERLAPPING blocks.

This is a `PRODUCT_EXPERIMENT` check on a candidate, not a RESEARCH_CLAIM.
"""
from __future__ import annotations

import argparse
import math

import numpy as np

from backend.services.portfolio_farm import panel as panel_mod

COST_BPS = 10.0   # 5bps spread + 5bps impact each way, a 1990s-inclusive figure


def trailing(tri: np.ndarray, i: int, back: int) -> np.ndarray:
    if i - back < 0:
        return np.full(tri.shape[1], np.nan)
    prev = tri[i - back]
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(prev > 0, tri[i] / prev - 1.0, np.nan)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=1993)
    ap.add_argument("--end", type=int, default=2024)
    ap.add_argument("--lookback", type=int, default=126, help="sessions of momentum")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--hold", type=int, default=5)
    ap.add_argument("--universe", type=int, default=200, help="liquidity screen depth")
    ap.add_argument("--reduce", action="store_true")
    ap.add_argument("--trend", action="store_true",
                    help="hold the book only while the equal-weight universe is "
                         "above its own 200-session average. 2000-2009 took the "
                         "5-name book to 0.07x; a regime filter is the cheapest "
                         "thing that could have prevented it, so it is TESTED "
                         "rather than assumed.")
    ap.add_argument("--sweep", action="store_true",
                    help="sweep k and lookback on ONE panel load. Terminal wealth "
                         "is the ranking column: a book with a positive MEAN and "
                         "0.1x terminal wealth is a losing book, and the 5-name "
                         "version of this rule is exactly that.")
    args = ap.parse_args()

    print(f"loading CRSP {args.start}-{args.end} ...")
    p = panel_mod.load_panel(args.start, args.end,
                            reduce_for_universe_n=500 if args.reduce else None,
                            with_characteristics=False)
    T, N = p.shape
    print(f"panel {T} sessions x {N} permnos  ({p.dates[0]} .. {p.dates[-1]})")

    # Equal-weight universe index, built from the panel itself so the filter
    # uses no information the strategy does not already have.
    with np.errstate(invalid="ignore"):
        breadth = np.nanmean(np.where(p.traded, p.ret, np.nan), axis=1)
    breadth = np.nan_to_num(breadth, nan=0.0)
    mkt_tri = np.cumprod(1.0 + breadth)

    def in_uptrend(i: int, window: int = 200) -> bool:
        if i < window:
            return True
        return bool(mkt_tri[i] >= float(np.mean(mkt_tri[i - window:i + 1])))

    def replay(lookback: int, k: int, hold: int):
        rets, dates = [], []
        for i in range(lookback + 5, T - hold - 1):
            dv = np.nanmean(p.dolvol[max(0, i - 20):i + 1], axis=0)
            dv = np.nan_to_num(dv, nan=0.0)
            if int((dv > 0).sum()) <= args.universe:
                continue
            cut = np.partition(dv, -args.universe)[-args.universe]
            mask = (dv >= cut) & p.traded[i]
            if args.trend and not in_uptrend(i):
                rets.append(0.0)          # in cash, and cash is a position
                dates.append(str(p.dates[i]))
                continue
            score = np.where(mask, trailing(p.tri, i, lookback), np.nan)
            if int(np.isfinite(score).sum()) < k:
                continue
            pick = np.argsort(np.where(np.isfinite(score), -score, np.inf))[:k]
            entry, exit_ = p.open_[i + 1, pick], p.open_[i + 1 + hold, pick]
            ok = np.isfinite(entry) & np.isfinite(exit_) & (entry > 0)
            if ok.sum() < k * 0.6:
                continue
            leg = exit_[ok] / entry[ok] - 1.0
            rets.append(float(np.mean(leg)) - 2.0 * COST_BPS / 10_000.0)
            dates.append(str(p.dates[i]))
        return rets, dates

    if args.sweep:
        print("")
        print(f"{'lookback':>9} {'k':>4} {'hold':>5} {'mean':>8} {'wealth':>10} "
              f"{'CAGR':>8} {'t':>6} {'worst':>8}")
        print("-" * 64)
        for lookback in (21, 63, 126, 252):
            for k in (5, 20, 50, 100):
                rr, _ = replay(lookback, k, args.hold)
                if len(rr) < 100:
                    continue
                a = np.asarray(rr)
                b = a[::args.hold]
                w = float(np.prod(1.0 + b))
                yrs = b.size * args.hold / 252.0
                cg = (w ** (1 / yrs) - 1) if w > 0 else -1.0
                tt = float(np.mean(b) / (np.std(b, ddof=1) / math.sqrt(b.size)))
                print(f"{lookback:>9} {k:>4} {args.hold:>5} {np.mean(a):>+8.3%} "
                      f"{w:>9,.2f}x {cg:>+8.2%} {tt:>+6.2f} {np.min(a):>+8.2%}")
        return 0

    rets, dates = [], []
    for i in range(args.lookback + 5, T - args.hold - 1):
        dv = np.nanmean(p.dolvol[max(0, i - 20):i + 1], axis=0)
        dv = np.nan_to_num(dv, nan=0.0)
        n_ok = int((dv > 0).sum())
        if n_ok <= args.universe:
            continue
        cut = np.partition(dv, -args.universe)[-args.universe]
        mask = (dv >= cut) & p.traded[i]
        score = np.where(mask, trailing(p.tri, i, args.lookback), np.nan)
        if int(np.isfinite(score).sum()) < args.k:
            continue
        pick = np.argsort(np.where(np.isfinite(score), -score, np.inf))[:args.k]
        entry, exit_ = p.open_[i + 1, pick], p.open_[i + 1 + args.hold, pick]
        ok = np.isfinite(entry) & np.isfinite(exit_) & (entry > 0)
        if ok.sum() < args.k * 0.6:
            continue
        leg = exit_[ok] / entry[ok] - 1.0
        rets.append(float(np.mean(leg)) - 2.0 * COST_BPS / 10_000.0)
        dates.append(str(p.dates[i]))

    r = np.asarray(rets)
    blk = r[::args.hold]
    n = blk.size
    sd = float(np.std(blk, ddof=1))
    t = float(np.mean(blk) / (sd / math.sqrt(n)))
    wealth = float(np.prod(1.0 + blk))
    years = n * args.hold / 252.0
    cagr = wealth ** (1.0 / years) - 1.0 if wealth > 0 else -1.0

    print(f"\nRULE  mom {args.lookback}d, top {args.k} of the {args.universe} most liquid, "
          f"hold {args.hold}, next-open fill, {COST_BPS:.0f}bps each way")
    print(f"  windows {r.size}   NON-OVERLAPPING blocks {n}   ({years:.1f} years)")
    print(f"  mean {np.mean(r):+.3%}   median {np.median(r):+.3%}   hit {np.mean(r > 0):.1%}")
    print(f"  t on blocks {t:+.2f}   terminal wealth {wealth:,.1f}x   CAGR {cagr:+.2%}")
    print(f"  worst window {np.min(r):+.2%}   best {np.max(r):+.2%}")

    print("\nBY DECADE -- a rule that only works in one regime says so here")
    for lo, hi in ((1993, 1999), (2000, 2009), (2010, 2019), (2020, 2024)):
        sel = [x for x, d in zip(rets, dates) if lo <= int(d[:4]) <= hi]
        if len(sel) < 30:
            continue
        b = np.asarray(sel)[::args.hold]
        w = float(np.prod(1.0 + b))
        yrs = b.size * args.hold / 252.0
        tt = float(np.mean(b) / (np.std(b, ddof=1) / math.sqrt(b.size)))
        print(f"  {lo}-{hi}  {b.size:4d} blocks  wealth {w:9,.2f}x  "
              f"CAGR {(w ** (1/yrs) - 1) if w > 0 else -1:+7.2%}  t {tt:+5.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
