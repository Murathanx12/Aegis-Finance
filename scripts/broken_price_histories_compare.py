"""Old vs new for the calendar-neutral leads, after the bar-defect screen (2026-09-29).

    python -m scripts.broken_price_histories_compare --old <run> --stitch <run> --screen <run>

Reads three `calendar_offsets_<run>.json` receipts and their monthly parquets
(nothing is recomputed from bars) and writes ONE comparison receipt
`strategy_library/broken_price_histories_compare_<run_id>.json`:

  OLD     the 2026-09-28 triplet (no stitch cut, no screen) -- the +661% row
  STITCH  the same code on today's bars with the stitch cut only (`--bar-screen off`)
  SCREEN  the stitch cut + `bar_defects.screen` (the reader default)

Per rule, calendar-neutral (1/3 in each quarterly offset): cum net since 2020,
rule - twin21 mean %/month with its block t and MDE, the hold-year sums keyed
on the month HELD, the leave-one-hold-year-out worst, and the verdict.
PRODUCT_EXPERIMENT; HINDSIGHT (every rule was registered 2026-09-26).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import calendar_offsets as CO             # noqa: E402
from scripts import night_backtest_factory as F                 # noqa: E402


def neutral_diff(monthly: pd.DataFrame, rule: str) -> pd.Series:
    """Calendar-neutral monthly (rule_net - twin21_net), over months common to all offsets."""
    m = monthly[monthly["rule"] == rule]
    piv_r = m.pivot_table(index="date", columns="offset", values="rule_net")
    piv_t = m.pivot_table(index="date", columns="offset", values="twin21_net")
    ok = piv_r.notna().all(axis=1) & piv_t.notna().all(axis=1)
    d = (piv_r[ok].mean(axis=1) - piv_t[ok].mean(axis=1))
    d.index = pd.DatetimeIndex(d.index)
    return d.sort_index()


def leg(receipt: dict, monthly: pd.DataFrame, rule: str) -> dict:
    e = (receipt.get("results") or {}).get(rule)
    if not e:
        return {"status": "MISSING", "why": (receipt.get("refused") or {}).get(rule)}
    ta = e["tranche_average"]
    d = neutral_diff(monthly, rule)
    lw = CO.loo_worst(d)
    return {"cum_net_since_2020": ta.get("cum_net_since_2020"),
            "cum_spy_since_2020": ta.get("cum_spy_since_2020"),
            "cagr_net": ta.get("cagr_net"),
            "rule_minus_twin21": ta.get("rule_minus_twin21"),
            "sealed_rule_minus_twin21": ta.get("sealed_rule_minus_twin21"),
            "by_hold_year_sum": {y: round(v["sum"], 5) for y, v in CO.by_hold_year(d).items()},
            "loo_worst_mean_monthly": lw["worst"], "loo_worst_dropped_year": lw["dropped_year"],
            "verdict": e["classification"]["verdict"],
            "offsets_cum_since_2020": {t: r.get("cum_net_since_2020") for t, r in e["offsets"].items()}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True)
    ap.add_argument("--stitch", required=True)
    ap.add_argument("--screen", required=True)
    a = ap.parse_args(argv)
    out = F.out_dir()
    legs = {"OLD": a.old, "STITCH": a.stitch, "SCREEN": a.screen}
    rec, mon = {}, {}
    for k, run in legs.items():
        rec[k] = json.loads((out / f"calendar_offsets_{run}.json").read_text(encoding="utf-8"))
        mon[k] = pd.read_parquet(out / f"calendar_offsets_monthly_{run}.parquet")
    rules = list(rec["OLD"].get("rules") or [])
    res = {r: {k: leg(rec[k], mon[k], r) for k in legs} for r in rules}
    run_id = F.new_run_id()
    rp = out / f"broken_price_histories_compare_{run_id}.json"
    doc = {"schema": "strategy_library/broken_price_histories_compare/1", "run_id": run_id,
           "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "label": "HINDSIGHT: the rules were registered 2026-09-26, after every month here",
           "legs": {k: {"run": v, "bar_screen": (rec[k].get("bar_screen") or {}).get("mode", "n/a (pre-screen code)"),
                        "panel": (rec[k].get("size_check") or {}).get("this_panel")}
                    for k, v in legs.items()},
           "conventions": {"neutral": "1/3 in each quarterly offset (calendar_offsets.tranche_average)",
                           "by_hold_year": "sum of monthly rule - twin21, keyed on the month HELD",
                           "loo": "leave-one-hold-year-out mean monthly rule - twin21, worst year"},
           "results": res}
    rp.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    for r in rules:
        print(r)
        for k in legs:
            x = res[r][k]
            if x.get("status") == "MISSING":
                print(f"  {k:7s} MISSING {x.get('why')}")
                continue
            rt = x["rule_minus_twin21"]
            print(f"  {k:7s} cum2020 {x['cum_net_since_2020']:+.1%}  rule-twin {rt['mean_monthly']:+.2%}/mo "
                  f"t {rt['t_blocks']:+.2f} MDE {rt['mde_monthly']:.2%}  LOO worst "
                  f"{x['loo_worst_mean_monthly']:+.2%} (drop {x['loo_worst_dropped_year']})  {x['verdict']}")
            print(f"          by hold year {x['by_hold_year_sum']}")
    print(f"-> {rp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
