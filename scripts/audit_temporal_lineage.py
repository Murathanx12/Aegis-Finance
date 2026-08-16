"""Every research design with a forward label, measured against the real calendar.

    python -m scripts.audit_temporal_lineage

WHY A SWEEP AND NOT A PATCH (2026-08-16)
========================================
N9's leak — build `fwd_20` on the full series, then slice the features at
`TRAIN_END` — was found by accident, while writing a *different* script that
happened not to be able to commit it. "Fix N9" is the wrong size of response to
a defect found that way. The question is how many other designs in this repo do
the same thing, and the only honest way to answer it is to check all of them
and publish the list, including the ones that come back clean.

WHAT IS MEASURED, AND WHY IT NEEDS THE REAL CALENDAR
====================================================
Two of these designs embargo in **calendar days** against a label defined in
**trading bars**. That is not automatically wrong — it is wrong exactly when
twenty trading bars happen to span more than the allowance, which is a property
of the NYSE holiday schedule and cannot be settled by reading the code.

Measured on the real 1999-2026 grid: twenty trading bars span **29.0 calendar
days on average and up to 35**. So a `1.5 * H`-day embargo (30 days at H=20) is
short on **15.7%** of possible boundaries and a `2 * H`-day embargo (40) is
never short. The audit then asks the only question that decides anything: do
each design's ACTUAL fold boundaries land on one of the short ones?

The verdicts are deliberately three, not two:

    LEAKS         measured training rows whose label reads past the split
    CLEAN         none, on this design's own boundaries
    NO_SPLIT      the design has no train/test boundary to leak across —
                  which is a finding about scope, not a missing check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend import config as _config
from backend.services.research_gym import lineage as LG

OUT = _config.OPTIMUS_LEDGER_DIR / "research_gym" / "temporal_lineage_audit.json"

#: One row per design. `split` returns a list of `(label, cutoff_ts)` pairs —
#: the last bar each training period owns — or None when the design has no
#: train/test boundary at all.
DESIGNS: list[dict] = []


def _register(name: str, horizons, note: str, split) -> None:
    DESIGNS.append({"name": name, "horizons": tuple(horizons), "note": note,
                    "split": split})


def _next_bar(dates, after: str) -> str | None:
    for t in dates:
        if t > after:
            return t
    return None


def _n9_splits(dates, _mod):
    """Train is everything up to TRAIN_END, with no embargo of any kind."""
    import scripts.n9_mine_the_85 as m
    return [("train<=TRAIN_END", m.TRAIN_END, _next_bar(dates, m.TRAIN_END))]


def _n21_splits(dates, _mod):
    """Same cutoff, but the freeze never downloads past it.

    Truncating the download is not an embargo — it is a purge by starvation:
    the last H rows get a NaN label and are dropped by the `~isnan` filter
    downstream. It produces the right training set, and it produces it as a
    side effect of an unrelated decision. Audited as its own case because a
    correct outcome from an implicit mechanism is one refactor from a leak.
    """
    import scripts.n21_policy_utility as m
    return [("train<=TRAIN_END (download truncated)", m.TRAIN_END,
             _next_bar(dates, m.TRAIN_END))]


def _equal_fold_splits(dates, mod, calendar_multiplier: float):
    """`np.array_split` into N_FOLDS+1, embargo `mult * H` CALENDAR days."""
    import numpy as np
    import pandas as pd
    bounds = np.array_split(np.asarray(dates), int(mod.N_FOLDS) + 1)
    out = []
    for k in range(1, int(mod.N_FOLDS) + 1):
        train_end = pd.Timestamp(str(bounds[k - 1][-1]))
        test_start = str(bounds[k][0])[:10]
        for H in mod.HORIZONS:
            emb = train_end - pd.Timedelta(days=int(H * calendar_multiplier))
            out.append((f"fold{k} H={H} emb={int(H * calendar_multiplier)}d",
                        str(emb)[:10], H, test_start))
    return out


def _wm0_splits(dates, _mod):
    """Annual expanding folds, embargo `2 * H` CALENDAR days."""
    import numpy as np
    import pandas as pd
    import scripts.wm0_train as m
    d = np.asarray(dates)
    years = pd.DatetimeIndex(d).year
    out = []
    for y in range(int(m.FIRST_TEST_YEAR), int(years.max()) + 1):
        sel = list(d[years == y])
        if not sel:
            continue
        test_start = str(min(sel))[:10]
        cutoff = pd.Timestamp(test_start) - pd.Timedelta(days=m.HORIZON * 2)
        out.append((f"test{y} emb={m.HORIZON * 2}d", str(cutoff)[:10],
                    m.HORIZON, test_start))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", default="1999-01-01")
    ap.add_argument("--end", default="2026-08-16")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    import numpy as np
    import pandas as pd
    import yfinance as yf

    px = yf.download("SPY", start=a.start, end=a.end, progress=False,
                     auto_adjust=False)["Close"].dropna()
    idx = pd.DatetimeIndex(np.asarray(px.index))
    dates = [str(t)[:10] for t in idx]
    print(f"trading calendar: {len(dates)} bars {dates[0]} .. {dates[-1]}")

    # ── the calendar fact both embargo rules depend on and neither states ──
    spans = {}
    for H in (5, 20, 60):
        s = np.array([(idx[i + H] - idx[i]).days for i in range(len(idx) - H)])
        spans[H] = {"mean": float(s.mean()), "max": int(s.max()),
                    "pct_over_1_5H": float((s > 1.5 * H).mean()),
                    "pct_over_2H": float((s > 2.0 * H).mean())}
        print(f"  {H:>2d} trading bars span {s.mean():.1f} calendar days "
              f"(max {s.max()});  a 1.5H={1.5 * H:.0f}d embargo is short on "
              f"{100 * (s > 1.5 * H).mean():.1f}% of boundaries, "
              f"2H={2 * H}d on {100 * (s > 2.0 * H).mean():.1f}%")

    import scripts.n11_vol_baseline_ladder as n11
    import scripts.n6_moments as n6

    import scripts.n21_policy_utility as n21
    import scripts.n9_mine_the_85 as n9

    # (name, note, split_fn, index_end) — `index_end` is the last bar the
    # design's OWN download reaches. It is not cosmetic: a label whose window
    # runs past the end of the downloaded series does not exist, and a row with
    # no label is dropped rather than leaked. Auditing every design against the
    # full 2026 calendar would report n21's starved rows as a leak, which is
    # the mirror of the error being audited for.
    designs = [
        ("n9_mine_the_85",
         "train sliced at TRAIN_END AFTER fwd_H computed on prices to 2026",
         lambda d: [(lab, ts, H, ev) for lab, ts, ev in _n9_splits(d, None)
                    for H in (20, 60)], None),
        ("n21_policy_utility --freeze",
         "same cutoff; download TRUNCATED at TRAIN_END, so the label starves",
         lambda d: [(lab, ts, 20, ev) for lab, ts, ev in _n21_splits(d, None)],
         n21.TRAIN_END),
        ("n11_vol_baseline_ladder",
         "6 equal folds, embargo 1.5*H CALENDAR days, label in trading bars",
         lambda d: _equal_fold_splits(d, n11, 1.5), None),
        ("n6_moments",
         "6 equal folds, embargo 1.5*H CALENDAR days, label in trading bars",
         lambda d: _equal_fold_splits(d, n6, 1.5), None),
        ("wm0_train",
         "annual expanding folds, embargo 2*H CALENDAR days",
         lambda d: _wm0_splits(d, None), None),
    ]
    assert n9.TRAIN_END == n21.TRAIN_END, "the two designs share a cutoff"

    rows = []
    for name, note, split_fn, index_end in designs:
        grid = [t for t in dates if index_end is None or t <= index_end]
        splits = split_fn(grid)
        worst, total_leaking, total_starved, detail = 0, 0, 0, []
        for lab, cutoff, H, eval_start in splits:
            rep = LG.check_split(grid, split_cutoff=cutoff, eval_start=eval_start,
                                 windows=[LG.LabelWindow(f"fwd_{H}", int(H))])
            (w,) = rep.windows
            total_leaking += w.n_leaking
            total_starved += w.n_unresolved
            worst = max(worst, w.max_reach_rows)
            if w.n_leaking:
                detail.append({"split": lab, "cutoff": cutoff, "H": int(H),
                               "eval_start": eval_start,
                               "n_leaking_dates": w.n_leaking,
                               "max_reach_bars": w.max_reach_rows,
                               "reaches_to": w.max_reach_ts})
        verdict = "LEAKS" if total_leaking else "CLEAN"
        rows.append({"design": name, "note": note, "verdict": verdict,
                     "index_end": index_end,
                     "n_splits_checked": len(splits),
                     "n_leaking_dates_total": total_leaking,
                     "n_starved_dates_total": total_starved,
                     "max_reach_bars": worst, "leaking_splits": detail})
        print(f"\n{name}")
        print(f"  {note}")
        print(f"  -> {verdict}: {total_leaking} leaking training DATES across "
              f"{len(splits)} split x horizon combinations"
              + (f", worst reaches {worst} bars past the boundary" if worst
                 else "")
              + (f"; {total_starved} dates have no label at all (dropped, not "
                 f"leaked)" if total_starved else ""))
        for d in detail[:8]:
            print(f"       {d['split']:<34s} {d['n_leaking_dates']:>3d} dates, "
                  f"+{d['max_reach_bars']} bars to {d['reaches_to']}")

    # Designs with no train/test boundary. Recorded rather than omitted: "this
    # script was not audited" and "this script has nothing to audit" look
    # identical in a list that only prints failures.
    no_split = [
        ("n4_precursor_coverage", "coverage of one slice; no fitted split"),
        ("n4b_coverage_equivalence", "equivalence on one slice; no fitted split"),
        ("n20_conditional_mu_rest", "conditional means on one slice; no split"),
        ("gym_dissect_timing", "decomposition of recorded episodes; no label fit"),
        ("wm0_inference", "re-does inference on wm0_train's cached folds"),
    ]
    print("\nNO_SPLIT (nothing to leak across — stated, not omitted)")
    for n, why in no_split:
        rows.append({"design": n, "note": why, "verdict": "NO_SPLIT",
                     "n_splits_checked": 0, "n_leaking_dates_total": 0,
                     "max_reach_bars": 0, "leaking_splits": []})
        print(f"  {n:<32s} {why}")

    p = Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(
        {"calendar_bars": len(dates), "start": dates[0], "end": dates[-1],
         "trading_bar_spans": spans, "designs": rows}, indent=2),
        encoding="utf-8")
    print(f"\nwritten  {p}")
    leaks = [r["design"] for r in rows if r["verdict"] == "LEAKS"]
    print(f"\nLEAKS: {len(leaks)} — {', '.join(leaks) if leaks else 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
