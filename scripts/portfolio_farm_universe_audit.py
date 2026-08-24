"""Can the PIT superset's forward-looking construction bias the farm's universe?

    python -m scripts.portfolio_farm_universe_audit

THE WORRY, STATED PROPERLY
==========================
The CRSP daily files the farm replays are not all of CRSP. They were pulled for
the **6,894-PERMNO superset** of `crsp_pit_monthly_v1` — every permno that
passed a monthly screen at ANY point in 2013-2024. That screen is
(`crsp_pit_monthly_v1.meta.json`, `filters_frozen`):

    shrcd  10, 11          ordinary common shares
    exchcd 1, 2, 3         NYSE / AMEX / NASDAQ
    min_price              $5.00
    min_dollar_vol_month   $100,000,000

`shrcd` and `exchcd` are contemporaneous facts and a declared universe choice —
common stocks on the three main exchanges, the standard academic universe, not
lookahead. The DOLLAR VOLUME bar is the problem: "ever cleared $100M in a month
across 2013-2024" is a statement about a name's whole life, applied when
deciding whether to put it in the file at all. A name that was never liquid is
absent from the daily panel entirely, and the farm can never have held it.

If the farm's own selections sat anywhere near that bar, every farm number would
inherit a survivorship tilt.

HOW THIS SETTLES IT
===================
Compare the bar to the farm's own cut. The farm ranks by trailing 21-day mean
dollar volume and keeps the top 500. If the 500th name trades far more than
$100M/month, then a name excluded from the superset for missing that bar could
never have ranked into a farm book on any date — and the restriction cannot
bind, whatever its construction.

MEASURED 2026-08-24, sampling one date a year across 2013-2024:

    500th-ranked name        $76M - $137M per DAY  = $1.6B - $2.9B per month
    superset inclusion bar   $100M per MONTH
    minimum margin           15.4x        (median 20.4x)
    eligible names per date  2,770 - 3,439, of which the farm takes 500

Fifteen times, at the worst sampled date. It is not close, and the farm's cut is
well inside the available set rather than pressed against its boundary.

**VERDICT: the superset's forward-looking construction cannot bias the farm's
universe.** This is a negative result and it is worth as much as a positive one:
it was the largest unaudited assumption left standing under the farm, and the
handoff named it as the next thing to attack.

WHAT THIS DOES NOT SAY
======================
It does not clear the SHRCD/EXCHCD restriction, which is a declared universe
choice — no ADRs, no closed-end funds, no OTC. A farm result is a result about
common stocks on the three main exchanges, and always was.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from backend.services.portfolio_farm import panel as P, signals as SIG  # noqa: E402

#: `crsp_pit_monthly_v1.meta.json` -> filters_frozen.min_dollar_vol_month.
#: Read from the meta file when present so this cannot drift from the screen it
#: is auditing; the literal is the dated fallback.
PIT_BAR_MONTHLY_DEFAULT = 100_000_000.0
PIT_META = (Path(__file__).resolve().parents[1] / "backend" / "data" / "optimus"
            / "crsp_pit" / "crsp_pit_monthly_v1.meta.json")

#: Trading days per month, for turning a daily mean into a monthly figure.
DAYS_PER_MONTH = 21

#: Below this multiple the audit REFUSES to call the restriction non-binding.
#: Three is deliberately generous: the measured minimum is 15.4x, so a future
#: run that trips this has seen the universe change materially, not drift.
MIN_SAFE_MARGIN = 3.0


def pit_bar_monthly() -> tuple[float, str]:
    try:
        m = json.loads(PIT_META.read_text(encoding="utf-8"))
        v = float(m["filters_frozen"]["min_dollar_vol_month"])
        return v, f"read from {PIT_META.name}"
    except Exception:                                          # noqa: BLE001
        return PIT_BAR_MONTHLY_DEFAULT, "DATED FALLBACK — meta file unreadable"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", type=int, default=2013)
    ap.add_argument("--end", type=int, default=2024)
    ap.add_argument("--universe-n", type=int, default=500)
    ap.add_argument("--min-price", type=float, default=5.0)
    ap.add_argument("--every", type=int, default=250, help="sample every N sessions")
    a = ap.parse_args(argv)

    bar, bar_src = pit_bar_monthly()
    pan = P.load_panel(a.start, a.end)
    dm = SIG._roll_mean(pan.dolvol.astype(np.float64), SIG.MONTH, 5)

    print(f"UNIVERSE AUDIT  {a.start}-{a.end}  top_k universe = {a.universe_n}")
    print(f"PIT superset inclusion bar: ${bar/1e6:.0f}M / MONTH  ({bar_src})")
    print(f"                          = ${bar/DAYS_PER_MONTH/1e6:.1f}M / day\n")
    hdr = (f"{'date':<12} {'eligible':>9} {'Nth $/day':>12} {'Nth $/mo':>11} "
           f"{'x over bar':>11}")
    print(hdr)
    print("-" * len(hdr))

    ratios, counts, thin = [], [], []
    for i in range(300, pan.shape[0], a.every):
        px = pan.close[i].astype(np.float64)
        ok = (pan.traded[i] & np.isfinite(px) & (px >= a.min_price)
              & np.isfinite(dm[i]))
        cand = np.flatnonzero(ok)
        counts.append(int(cand.size))
        if cand.size < a.universe_n:
            thin.append(str(pan.dates[i]))
            print(f"{str(pan.dates[i]):<12} {cand.size:>9}   FEWER THAN "
                  f"{a.universe_n} ELIGIBLE — the cut IS the boundary here")
            continue
        nth = np.sort(dm[i][cand])[::-1][a.universe_n - 1]
        monthly = nth * DAYS_PER_MONTH
        ratios.append(monthly / bar)
        print(f"{str(pan.dates[i]):<12} {cand.size:>9} {nth/1e6:>11.1f}M "
              f"{monthly/1e6:>10.0f}M {monthly/bar:>10.1f}x")

    r = np.asarray(ratios)
    ok = bool(r.size and r.min() >= MIN_SAFE_MARGIN and not thin)
    print(f"\n  margin over the bar : min {r.min():.1f}x  median "
          f"{np.median(r):.1f}x  (across {r.size} sampled dates)")
    print(f"  eligible per date   : min {min(counts)}  median "
          f"{int(np.median(counts))}  max {max(counts)}")
    print()
    if ok:
        print(f"  VERDICT: the superset restriction CANNOT BIND. The farm's "
              f"{a.universe_n}th name\n"
              f"  trades at least {r.min():.0f}x the bar a name needed to clear "
              f"to be in the file at\n  all, so an excluded name could never "
              f"have ranked into a book.")
    else:
        print("  VERDICT: NOT CLEARED. Either a sampled date had fewer eligible "
              "names than the\n  universe size (the cut IS the boundary), or "
              f"the margin fell under {MIN_SAFE_MARGIN}x.\n  Farm results "
              "inherit a survivorship tilt until this is resolved.")
        if thin:
            print(f"  thin dates: {thin}")
    print("\n  Does NOT clear the shrcd/exchcd restriction — common stocks on "
          "NYSE/AMEX/NASDAQ\n  is a DECLARED universe choice, and every farm "
          "result is a result about that universe.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
