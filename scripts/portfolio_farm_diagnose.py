"""Signal diagnostics BEFORE portfolio diagnostics, for every registered signal.

    python -m scripts.portfolio_farm_diagnose --start 2013 --end 2024
    python -m scripts.portfolio_farm_diagnose --start 1993 --end 2024 --reduce
    python -m scripts.portfolio_farm_diagnose --signals profit_roe value_bm

WHAT QUESTION THIS ANSWERS, AND WHICH ONE IT REFUSES TO
=======================================================
    does expected return move monotonically with the signal?

and NOT "what did the top-k book earn". Every farm leaderboard to date answered
the second question and was read as answering the first. They are different
questions, and when the second one disappoints there is no way to tell whether
the signal was weak, the construction destroyed it, the exposures ate it, or
the benchmark was wrong.

The cost of that conflation is on the record twice:

  * `value_bm` reads as a failed signal. Value is not implemented as "buy the
    ten highest book-to-market names out of 500 mega-liquid stocks", and that
    book is a distress portfolio. The decile curve says so; terminal wealth
    never did;
  * `liquid` had the best t on the 2013-2024 grid and was a static FAANG list.

READ THE COLUMNS IN THIS ORDER
==============================
`ic_t` first — does the score order returns at all, over NON-OVERLAPPING dates.
Then `mono`, the Spearman of bucket index against bucket mean: a signal that
only works in its top bucket is usually a few names, not an edge. Then
`t-b`, the annualised top-minus-bottom spread, which is the long-short the
signal would support before any long-only construction. Then `names/slot` and
`turn` — a book with barely more distinct names than slots is a static list
wearing a signal's name, whatever its t.

Terminal wealth is deliberately not printed here. `portfolio_farm_run` prints
it, and it should be read after this, not instead of it.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services.portfolio_farm import (              # noqa: E402
    diagnostics as D, farm, panel as P, signals as SIG)
from backend.services.portfolio_farm.policy import Policy  # noqa: E402

HOLDING_DAYS = 21
TOP_K = 20          # k=20, not k=10: the 32-year breadth verdict superseded it


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", type=int, default=2013)
    ap.add_argument("--end", type=int, default=2024)
    ap.add_argument("--reduce", action="store_true")
    ap.add_argument("--holding-days", type=int, default=HOLDING_DAYS)
    ap.add_argument("--top-k", type=int, default=TOP_K)
    ap.add_argument("--quantiles", type=int, default=5)
    ap.add_argument("--signals", nargs="*", default=None)
    a = ap.parse_args(argv)

    pan = P.load_panel(a.start, a.end,
                       reduce_for_universe_n=(500 if a.reduce else None))
    names = a.signals or list(SIG.SIGNALS)

    print(f"SIGNAL DIAGNOSTICS — {a.start}-{a.end}, h={a.holding_days} "
          f"k={a.top_k}, {a.quantiles} buckets")
    print(f"  panel {pan.shape[0]:,} sessions x {pan.shape[1]:,} permnos, "
          f"openprc usable on {pan.open_coverage:.2%} of traded cells")
    print("  forward returns are next-open to next-open, dividends included; "
          "formation dates are non-overlapping\n")

    hdr = (f"{'signal':<18} {'ic_t':>6} {'ic':>7} {'mono':>6} {'t-b%':>8} "
           f"{'t-b_t':>6} {'names/slot':>11} {'turn%':>6} {'age%':>6} "
           f"{'size%':>6}  verdict")
    print(hdr)
    print("-" * len(hdr))

    out = []
    for name in names:
        try:
            rep = D.signal_report(pan, name, top_k=a.top_k,
                                  holding_days=a.holding_days,
                                  n_quantiles=a.quantiles)
        except Exception as exc:                              # noqa: BLE001
            print(f"{name:<18} REFUSED: {type(exc).__name__}: {exc}")
            continue
        if "error" in rep:
            print(f"{name:<18} {rep['error']}")
            continue
        ic, qp, cen = rep["rank_ic"], rep["quantiles"], rep["census"]
        v = rep["verdict"]
        mark = "OK" if v["cross_section_supports_a_book"] else "; ".join(
            v["failed"])[:44]
        if rep["is_null"]:
            mark = f"[baseline] {mark}"

        def f(x, w, p=2):
            return f"{x:>{w}.{p}f}" if isinstance(x, (int, float)) else \
                f"{'-':>{w}}"

        print(f"{name:<18} {f(ic.get('ic_t'), 6, 2)} {f(ic.get('ic_mean'), 7, 4)} "
              f"{f(qp.get('monotonicity_spearman'), 6, 2)} "
              f"{f(qp.get('top_minus_bottom_annual_pct'), 8, 2)} "
              f"{f(qp.get('top_minus_bottom_t'), 6, 2)} "
              f"{f(cen.get('distinct_names_per_slot'), 11, 1)} "
              f"{f(cen.get('mean_turnover_pct'), 6, 1)} "
              f"{f(cen.get('mean_permno_percentile_of_holdings'), 6, 1)} "
              f"{f(cen.get('mean_size_percentile_of_holdings'), 6, 1)}  {mark}")
        out.append(rep)

    print("\n  age%  = mean permno percentile of holdings, against the "
          "ELIGIBLE set on each date.")
    print("          LOW = OLD listings. 50 = typical age for a name this "
          "book could have bought.")
    print("          Sanity check: oldest_listing must read ~0 and "
          "newest_listing ~100.")
    print("          This is the axis raw profit_roe was confounded on "
          "(126 years vs the age book).")
    print("  size% = mean market-cap percentile of holdings, same baseline.")
    print("  Both are DESCRIPTIVE, not point-in-time. Everything above them "
          "is point-in-time.")

    d = farm.RESULTS_DIR
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    p = d / f"signal_diagnostics_{a.start}_{a.end}_{stamp}.json"
    p.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window": [a.start, a.end],
        "holding_days": a.holding_days,
        "top_k": a.top_k,
        "n_quantiles": a.quantiles,
        "reduced": bool(a.reduce),
        "panel": {"sessions": int(pan.shape[0]), "permnos": int(pan.shape[1]),
                  "open_coverage": float(pan.open_coverage)},
        "reports": out,
    }, indent=2, default=str), encoding="utf-8")
    print(f"\n  receipt: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
