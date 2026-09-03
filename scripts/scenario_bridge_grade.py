"""Retrieve real analogues for every generated scenario, and let REALITY grade.

    python -m scripts.scenario_bridge_grade
    python -m scripts.scenario_bridge_grade --k 20 --no-holders

Reads `backend/data/optimus/scenario_bridge/scenarios_<tag>.jsonl`, maps each
scenario onto the 2013-2024 point-in-time panel, builds matched controls, and
writes ONE receipt:

    backend/data/optimus/tracker_backtest/scenario_bridge_20260903.json

WHAT THE RECEIPT IS FOR
=======================
Every headline number in the write-up must be in it -- `corr = 0.516` once lived
in prose only and turned out to be a filtered subset nobody had named. So the
receipt carries the mapping table, the per-scenario n's, the refusals, the
losers, the cost rate, and the LLM spend, not just the three spreads that
happened to be large.

THE RANKING IS EXPLORATORY AND SAYS SO
======================================
Twenty scenarios are twenty looks at one panel. There is no multiplicity control
here and there is not supposed to be one -- this is a `PRODUCT_EXPERIMENT`, and
its output is a QUEUE of things worth pre-registering, not a verdict. The
receipt stamps `licence: PRODUCT_EXPERIMENT` so a later reader cannot mistake a
t of 2.6 chosen from twenty for a t of 2.6 that was predicted.
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

from scripts import scenario_bridge as SB                       # noqa: E402


def run(k: int = 20, with_holders: bool = True, verbose: bool = True) -> dict:
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)

    scenarios = SB.load_scenarios()
    log(f"[scenarios] {len(scenarios)} valid")

    log("[panel] loading ...")
    panel, prov = SB.load_panel(with_holders=with_holders)
    log(f"[panel] {prov['rows']:,} rows, {prov['months']} months, "
        f"{prov['names']:,} names; holder coverage "
        f"{prov['holder_action'].get('coverage')}")

    results = []
    for s in scenarios:
        ret, g = SB.retrieve_and_grade(panel, s, k=k)
        row = {
            "scenario_id": s.get("scenario_id"),
            "event_type": s.get("event_type"),
            "sector_theme": s.get("sector_theme"),
            "sic_division_hint": s.get("sic_division_hint"),
            "direction": s.get("direction"),
            "expected_horizon_months": s.get("expected_horizon_months"),
            "mechanism": s.get("mechanism"),
            "falsifier": s.get("falsifier"),
            "scenario": {kk: vv for kk, vv in s.items() if not kk.startswith("_")},
            "retrieval": {kk: vv for kk, vv in ret.items()
                          if kk not in ("treated_index", "control_index")},
            "grade": g,
        }
        results.append(row)
        st = g.get("status")
        h = str(s.get("expected_horizon_months", "3"))
        hh = (g.get("horizons") or {}).get(h, {})
        log(f"  {row['scenario_id']} {st:<18} L{g.get('backoff_level')} "
            f"n_t={ret.get('n_treated', 0):>6} "
            f"n_c={ret.get('n_control', 0):>7} months={ret.get('n_month_blocks', 0):>3} "
            f"h={h}m spread={hh.get('spread_net')} t={hh.get('t_paired_by_month')}")

    # ---- the ranking, at each scenario's OWN declared horizon
    ranked = []
    for r in results:
        h = str(r["expected_horizon_months"])
        hh = (r["grade"].get("horizons") or {}).get(h)
        if not hh or hh.get("status") != "GRADED":
            continue
        ranked.append({
            "scenario_id": r["scenario_id"], "horizon_months": int(h),
            "direction": r["direction"],
            "backoff_level": r["grade"].get("backoff_level"),
            "backoff_dropped": r["grade"].get("backoff_dropped"),
            "spread_gross": hh["spread_gross"], "spread_net": hh["spread_net"],
            "t_paired_by_month": hh["t_paired_by_month"],
            "n_month_blocks": hh["n_month_blocks"],
            "n_treated_rows": hh["n_treated_rows"],
            "n_control_rows": hh["n_control_rows"],
            "share_months_positive": hh["share_months_positive"],
            "mechanism": r["mechanism"],
        })
    ranked.sort(key=lambda x: -(x["t_paired_by_month"] or -99))

    # ---- what fell through, across ALL scenarios: the acquisition list
    unmappable_counts: dict[str, int] = {}
    predicate_counts: dict[str, int] = {}
    for r in results:
        m = r["retrieval"].get("mapping", {})
        for f in m.get("unmappable_fields", []):
            unmappable_counts[f] = unmappable_counts.get(f, 0) + 1
        for f in m.get("predicates_used", {}):
            predicate_counts[f] = predicate_counts.get(f, 0) + 1

    n_sc = max(len(results), 1)
    per_scenario_direct = [
        sum(1 for f in r["retrieval"].get("mapping", {}).get("predicates_used", {})
            if SB.FIELD_MAP_DOC.get(f, {}).get("grade") == "DIRECT")
        for r in results]

    receipt = {
        "receipt": "scenario_bridge",
        "run_tag": SB.RUN_TAG,
        "licence": "PRODUCT_EXPERIMENT",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": SB.SCHEMA_VERSION,
        "what_this_is": (
            "An LLM invented the scenarios; code retrieved real 2013-2024 "
            "company-months that matched their OBSERVABLE fields; realised "
            "value-weighted excess returns graded matched-vs-control, paired by "
            "month block. No scenario ever received an invented return."),
        "panel_provenance": prov,
        "mappability": SB.mappability_summary(),
        "field_map": SB.FIELD_MAP_DOC,
        "retrieval_bands": SB._BANDS_DOC(),
        "floors": {
            "min_treated_rows": SB.MIN_TREATED_ROWS,
            "min_month_blocks": SB.MIN_MONTH_BLOCKS,
            "min_controls_per_stratum": SB.MIN_CONTROLS_PER_STRATUM,
        },
        "cost_convention": {
            "bps_round_trip_per_leg": SB.COST_BPS_ROUND_TRIP_PER_LEG,
            "legs": 2,
            "total_decimal": 2 * SB.COST_BPS_ROUND_TRIP_PER_LEG / 10_000.0,
        },
        "counts": {
            "scenarios": len(results),
            "graded": sum(1 for r in results if r["grade"].get("status") == "GRADED"),
            "refused_too_thin": sum(1 for r in results
                                    if r["grade"].get("status") == "REFUSED_TOO_THIN"),
            "no_analogue": sum(1 for r in results
                               if r["retrieval"].get("status") == "NO_ANALOGUE"),
            "mean_direct_predicates_per_scenario": round(
                sum(per_scenario_direct) / n_sc, 3),
        },
        "backoff": {
            "order": list(SB.BACKOFF_ORDER),
            "why": ("a five-way conjunction of quantile bands cuts a sector to a "
                    "few dozen name-months; the ladder drops the least central "
                    "predicate until the floor is met and NAMES what it dropped. "
                    "Two scenarios at different levels answer different "
                    "questions -- the ranking does not equate them."),
            "levels_used": {},
        },
        "llm_disagreement": SB.disagreement_summary(),
        "predicate_usage": predicate_counts,
        "unmappable_concepts": {
            "counts_across_scenarios": unmappable_counts,
            "reads_as": ("each row is a concept the LLM used that this panel "
                         "cannot express. This IS the next data-acquisition "
                         "list, in priority order by count."),
        },
        "ranked_at_declared_horizon": ranked,
        "scenarios": results,
    }

    lv: dict[str, int] = {}
    for r in results:
        key = str(r["grade"].get("backoff_level"))
        lv[key] = lv.get(key, 0) + 1
    receipt["backoff"]["levels_used"] = lv

    SB.RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SB.RECEIPT_PATH.write_text(json.dumps(receipt, indent=1, default=str),
                               encoding="utf-8")
    log(f"\n[receipt] -> {SB.RECEIPT_PATH}")
    return receipt


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--k", type=int, default=20, help="exemplars per scenario")
    ap.add_argument("--no-holders", action="store_true",
                    help="skip the 13F join (faster; holder_action then maps to nothing)")
    a = ap.parse_args(argv)
    r = run(k=a.k, with_holders=not a.no_holders)
    top = r["ranked_at_declared_horizon"][:3]
    print("\nTOP 3 BY PAIRED t AT THE DECLARED HORIZON")
    for x in top:
        print(f"  {x['scenario_id']} h={x['horizon_months']}m {x['direction']:<5} "
              f"L{x['backoff_level']} net {x['spread_net']:+.5f} "
              f"t {x['t_paired_by_month']} months {x['n_month_blocks']} "
              f"n_t {x['n_treated_rows']} dropped={x['backoff_dropped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
