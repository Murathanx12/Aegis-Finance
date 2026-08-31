"""Is the +400% upside band BAD NEWS or BAD DATA? Cut it open before softening it.

    python -m scripts.upside_band_decontamination --run
    python -m scripts.upside_band_decontamination --run --start 2013 --end 2024

THE QUESTION (Murat, 2026-08-31)
================================
    "when we limit stocks by high increase band saying overall bad we are
     losing on great winners too. rather than all %400+ upside band we can be
     more specific. lets learn why its priced at that per stock per sector.
     ... I said it again dont generalize go deeper to the root cause."

The 11-year backtest graded every absolute upside band and found a clean
monotone RISE up to +200-400% (+17.19%/yr excess, t 2.45) followed by a cliff:
the +400%+ band returned -26.47%/yr, t -4.71. On that number the tracker's
`UPSIDE_IMPLAUSIBLE_AT = 4.0` became a bar, and on 08-31 it barred WBUY.

But the receipt already contained the tell nobody pulled on: the +400%+ band
holds 54,232 name-months -- FIVE TIMES the band below it. Genuine optimism
should thin toward the extreme; a mechanical denominator balloons there. And
`feedback_a_stale_target_across_a_split_is_not_an_opinion` measured the band's
median at 44x, with capping flipping a screen -5.5% -> +3.9%/yr t 2.16.

So before `REJECT` is softened into `HIGH_UPSIDE_ANOMALY -- REVIEW` (the Fable
brief, 2237e7c) the band owes us a decomposition: how much of -26.47%/yr is
OPINION (analysts believe in a 5x) and how much is ARITHMETIC (a stale target
divided by a collapsed or rebased price)?

THE CONTROL DISCIPLINE, STATED BEFORE THE CUTS
==============================================
Every cell is graded TWICE: names in the +400%+ band inside the cell, and ALL
names inside the same cell regardless of band. The difference is what carrying
an extreme target ADDS, holding the cell fixed. Without that second leg,
"names that crashed 50% lose money" would be read as a fact about the band --
the exact error the 13F study caught with its trailing-return control, and the
min-names lesson: a filter can select the regime rather than clean the data.

THE CUTS
========
    price        raw close < $1 / $1-2 / $2-5 / >= $5   (a stale target over a
                 collapsed price is the mechanical route into the band)
    crashed      trailing 12m total return <= -50%
    split        share basis changed in the prior year (cfacpr)
    coverage     1 analyst vs >= 2 (one stale voice vs a refreshed consensus)
    CLEAN        >= $2, not crashed, no split, >= 2 analysts -- the cell the
                 softened gate would actually admit

Licence: PRODUCT_EXPERIMENT. Post-hoc, exploratory, costs not charged (band
grading is paired excess vs market, same convention as the parent backtest).
Receipt: backend/data/optimus/tracker_backtest/upside_band_decontamination.json
Parent:  scripts/tracker_ibes_backtest.py (machinery imported, never retyped).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.tracker_ibes_backtest import build_monthly, label, load_tracker_rules

OUT = Path(__file__).resolve().parent.parent / "backend" / "data" / "optimus" / "tracker_backtest"

#: The band under interrogation, and the band below it as the healthy control.
BAND_HOT = (4.00, 1e9)
BAND_CONTROL = (2.00, 4.00)


def paired_excess(sub: pd.DataFrame, market: pd.Series) -> dict | None:
    """Annualised mean monthly excess vs the equal-weight market, paired by month.

    Identical convention to the parent's `upside_bands`, so numbers line up
    against the -26.47% they are decomposing. None below 24 months / 300 rows:
    a cell too thin to grade is reported as ungradeable, not as zero.
    """
    if len(sub) < 300:
        return None
    per_month = sub.groupby("month")["fwd_1m"].mean()
    spread = (per_month - market.reindex(per_month.index)).dropna()
    if len(spread) < 24:
        return None
    t = (float(spread.mean() / (spread.std() / np.sqrt(len(spread))))
         if spread.std() > 0 else None)
    fwd = sub["fwd_1m"]
    return {
        "name_months": int(len(sub)),
        "months": int(len(spread)),
        "annualised_excess_vs_market": round(float(spread.mean()) * 12, 4),
        "t_stat_paired": round(t, 3) if t is not None else None,
        "median_fwd_1m": round(float(fwd.median()), 4),
        # Murat's "great winners" live here, if anywhere: the right tail.
        "share_fwd_1m_over_50pct": round(float((fwd > 0.50).mean()), 4),
        "share_fwd_1m_over_100pct": round(float((fwd > 1.00).mean()), 4),
    }


def cells(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Named boolean masks. Every mask must be computable on EVERY row."""
    prc = df["close"].astype(float)
    crashed = df["ret_12m"].fillna(0.0) <= -0.50
    split = df["split_prior_year"].fillna(False).astype(bool)
    cov1 = df["coverage"].fillna(0) < 2
    return {
        "price_under_1": prc < 1.0,
        "price_1_to_2": (prc >= 1.0) & (prc < 2.0),
        "price_2_to_5": (prc >= 2.0) & (prc < 5.0),
        "price_5_plus": prc >= 5.0,
        "crashed_50pct_12m": crashed,
        "not_crashed": ~crashed,
        "split_prior_year": split,
        "no_split": ~split,
        "coverage_1": cov1,
        "coverage_2_plus": ~cov1,
        "CLEAN": (prc >= 2.0) & ~crashed & ~split & ~cov1,
        "DIRTY_any": (prc < 2.0) | crashed | split | cov1,
    }


def run(start: int, end: int, lag_days: int) -> int:
    T, rules_sha = load_tracker_rules()
    print(f"tracker rules sha256 {rules_sha[:16]} | UPSIDE_IMPLAUSIBLE_AT = "
          f"{T.UPSIDE_IMPLAUSIBLE_AT:.0f}x\n")
    monthly = build_monthly(start, end, lag_days)
    lab = label(monthly, T)
    market = lab.groupby("month")["fwd_1m"].mean()

    hot = (lab["upside"] >= BAND_HOT[0]) & (lab["upside"] < BAND_HOT[1])
    ctl = (lab["upside"] >= BAND_CONTROL[0]) & (lab["upside"] < BAND_CONTROL[1])
    print(f"+400%+ band: {int(hot.sum()):,} name-months | +200-400% control: "
          f"{int(ctl.sum()):,} | whole panel: {len(lab):,}\n")

    report: dict = {
        "receipt": "UPSIDE-BAND-DECON-1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "licence": "PRODUCT_EXPERIMENT",
        "rules_sha256": rules_sha,
        "window": [start, end],
        "question": ("how much of the +400%+ band's -26.47%/yr is opinion and "
                     "how much is a stale target over a rebased/collapsed price?"),
        "control_discipline": ("every cell graded twice: band-in-cell AND "
                               "all-names-in-cell; the difference is what the "
                               "extreme target ADDS holding the cell fixed"),
        "baseline": {
            "band_400_plus": paired_excess(lab[hot], market),
            "band_200_400_control": paired_excess(lab[ctl], market),
        },
        "cells": {},
    }

    masks = cells(lab)
    hdr = (f"  {'cell':<20} {'n(band)':>9} {'band excess':>12} {'t':>6} "
           f"{'all-in-cell':>12} {'DELTA':>8} {'>+100% mo':>9}")
    print(hdr + "\n" + "  " + "-" * (len(hdr) - 2))
    for name, m in masks.items():
        in_band = paired_excess(lab[hot & m], market)
        in_cell = paired_excess(lab[m], market)
        band_ctl = paired_excess(lab[ctl & m], market)
        delta = (round(in_band["annualised_excess_vs_market"]
                       - in_cell["annualised_excess_vs_market"], 4)
                 if in_band and in_cell else None)
        report["cells"][name] = {
            "band_400_in_cell": in_band,
            "all_names_in_cell": in_cell,
            "band_200_400_in_cell": band_ctl,
            "band_minus_cell_pp_yr": delta,
            "share_of_band": round(float((hot & m).sum() / max(1, hot.sum())), 4),
        }
        b_ex = f"{in_band['annualised_excess_vs_market']*100:+.2f}%" if in_band else "--"
        b_t = (f"{in_band['t_stat_paired']:.2f}"
               if in_band and in_band["t_stat_paired"] is not None else "--")
        c_ex = f"{in_cell['annualised_excess_vs_market']*100:+.2f}%" if in_cell else "--"
        d_pp = f"{delta*100:+.1f}pp" if delta is not None else "--"
        tail = f"{in_band['share_fwd_1m_over_100pct']*100:.2f}%" if in_band else "--"
        print(f"  {name:<20} {int((hot & m).sum()):>9,} {b_ex:>12} {b_t:>6} "
              f"{c_ex:>12} {d_pp:>8} {tail:>9}")

    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / "upside_band_decontamination.json"
    dst.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"\nreceipt -> {dst}")
    return 0


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                           # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--start", type=int, default=2013)
    ap.add_argument("--end", type=int, default=2024)
    ap.add_argument("--lag-days", type=int, default=3)
    args = ap.parse_args(argv)
    if not args.run:
        ap.print_help()
        return 2
    return run(args.start, args.end, args.lag_days)


if __name__ == "__main__":
    raise SystemExit(main())
