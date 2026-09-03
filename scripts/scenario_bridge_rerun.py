"""RE-RUN the 20 graded scenarios after EDGAR 8-K acquisition #1.

    python -m scripts.scenario_bridge_rerun

Same scenarios (scenarios_20260903.jsonl -- NOT regenerated, zero LLM spend),
same panel, same retrieval and grading code. What changed is OWNERSHIP:
`scripts/edgar_8k_items.py` pulled a dated 8-K item-code tape from SEC EDGAR,
so `event_type` -- the 20260903 receipt's largest absence -- now grades PROXY
via `scenario_bridge.EIGHTK_ITEM_EVENT_TYPE` instead of UNMAPPABLE.

WHAT THIS RECEIPT REPORTS, HONESTLY
===================================
1. The MAPPABILITY DELTA: fields mapping to nothing owned, before vs after.
2. GRADE CHANGES: expected NONE -- event_type is not a retrieval predicate yet
   (the tape is survivor-tilted and not panel-joined; see
   `scenario_bridge.field_map_current`), so every spread must reproduce. A
   difference would mean the re-run changed something it claimed not to touch,
   and the comparison table would say so instead of hiding it.
3. The 8-K tape's own stats and how far it is from becoming a predicate:
   what fraction of the 2013-2024 panel's permnos even resolve to a CIK
   through today's ticker map.

Writes: backend/data/optimus/tracker_backtest/scenario_bridge_rerun_20260904.json
Licence: PRODUCT_EXPERIMENT.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import scenario_bridge as SB                       # noqa: E402
from scripts import scenario_bridge_grade as SBG                # noqa: E402
from scripts import edgar_8k_items as E8K                       # noqa: E402

RERUN_PATH = (REPO / "backend" / "data" / "optimus" / "tracker_backtest"
              / "scenario_bridge_rerun_20260904.json")


def panel_cik_resolution() -> dict:
    """How far the tape is from a panel join: of the train table's permnos,
    how many resolve permno -> last CRSP ticker -> current CIK?

    This is the honest distance between "we own a dated event tape" and
    "event_type can filter the 2013-2024 panel". Delisted names fail the
    ticker->CIK hop because company_tickers.json is current registrants only.
    """
    import pandas as pd
    panel_permnos = set(
        pd.read_parquet(SB.TRAIN_TABLE, columns=["permno"])["permno"]
        .astype("int64").unique().tolist())
    px = pd.read_parquet(E8K.CRSP_PIT_MONTHLY,
                         columns=["permno", "date", "ticker"])
    px = px[px["permno"].isin(panel_permnos) & px["ticker"].notna()]
    last = px.sort_values("date").groupby("permno")["ticker"].last()
    t2c = {str(v["ticker"]).upper(): int(v["cik_str"]) for v in
           json.loads(E8K.TICKER_CIK_CACHE.read_text(encoding="utf-8")).values()}
    n_ticker = int(len(last))
    n_cik = int(sum(1 for t in last.values if str(t).upper() in t2c))
    n = len(panel_permnos)
    return {
        "panel_permnos": n,
        "with_crsp_ticker": n_ticker,
        "resolving_to_current_cik": n_cik,
        "cik_resolution_rate": round(n_cik / n, 4),
        "reads_as": ("the fraction of panel names a survivor-tilted ticker->CIK "
                     "map can reach at all. The gap is mostly delistings; a "
                     "panel-joined event predicate needs a historical CIK link "
                     "(EDGAR full-text index or CRSP-CIK link table), not a "
                     "bigger pull through today's map."),
    }


def main() -> int:
    st = SB.eightk_tape_status()
    if not st.get("exists"):
        raise SystemExit(f"REFUSED: no 8-K tape on disk -- {st.get('why')}. "
                         "Run scripts/edgar_8k_items.py --pull --compact first; "
                         "re-running without it would reproduce the old receipt "
                         "and call it a delta.")

    manifest = json.loads(E8K.MANIFEST.read_text(encoding="utf-8"))
    fm_new = SB.field_map_current()
    map_before = SB.mappability_summary()                 # panel-only, static
    map_after = SB.mappability_summary(fm_new)

    # share of collected 8-K filings whose item codes map to >=1 event_type
    items_hist = manifest.get("item_histogram", {})
    mapped_items = {i for i, ts in SB.EIGHTK_ITEM_EVENT_TYPE.items() if ts}
    n_item_mentions = sum(items_hist.values())
    n_mapped_mentions = sum(v for k, v in items_hist.items()
                            if k in mapped_items)

    extra = {
        "what_changed_since_20260903": (
            "scenario-bridge acquisition #1: a dated SEC EDGAR 8-K item-code "
            "tape now exists in-repo (scripts/edgar_8k_items.py). event_type "
            "grades PROXY instead of UNMAPPABLE. Retrieval and grading code "
            "are UNCHANGED; scenarios are the SAME 20 (not regenerated)."),
        "edgar_8k": {
            "tape": st,
            "universe": ("scenario-receipt exemplar permnos + tracker "
                         "watchlist, resolved through company_tickers.json"),
            "item_histogram": items_hist,
            "item_event_type_map": {k: list(v) for k, v in
                                    SB.EIGHTK_ITEM_EVENT_TYPE.items()},
            "item_mentions_total": n_item_mentions,
            "item_mentions_mapped_to_event_type": n_mapped_mentions,
            "item_mention_mapped_rate": round(
                n_mapped_mentions / max(n_item_mentions, 1), 4),
            "event_types_with_an_item_proxy": sorted(
                {t for ts in SB.EIGHTK_ITEM_EVENT_TYPE.values() for t in ts}),
            "panel_cik_resolution": panel_cik_resolution(),
        },
        "mappability_before": map_before,
        "mappability_delta": {
            "unmappable_fields_before": map_before["unmappable"],
            "unmappable_fields_after": map_after["unmappable"],
            "maps_to_nothing_rate_before": round(
                map_before["unmappable"] / map_before["retrieval_fields"], 4),
            "maps_to_nothing_rate_after": round(
                map_after["unmappable"] / map_after["retrieval_fields"], 4),
            "any_mapping_rate_before": map_before["any_mapping_rate"],
            "any_mapping_rate_after": map_after["any_mapping_rate"],
            "direct_rate_unchanged": map_after["direct_rate"],
            "field_that_moved": "event_type: UNMAPPABLE -> PROXY",
        },
        "llm_spend": {
            "n_calls": 0, "usd": 0.0,
            "note": ("the re-run regenerates nothing -- the same 20 scenarios "
                     "are re-graded by code alone. DeepSeek (the sole "
                     "provider) was not called."),
        },
    }

    receipt = SBG.run(k=20, with_holders=True, receipt_path=RERUN_PATH,
                      field_map=fm_new, run_tag="20260904_rerun", extra=extra)

    # ---- grade comparison against the 20260903 receipt, scenario by scenario
    old = json.loads(SB.RECEIPT_PATH.read_text(encoding="utf-8"))

    def _by_id(rec):
        out = {}
        for r in rec.get("scenarios", []):
            h = str(r.get("expected_horizon_months"))
            hh = ((r.get("grade") or {}).get("horizons") or {}).get(h) or {}
            out[r["scenario_id"]] = {
                "status": (r.get("grade") or {}).get("status"),
                "horizon": h,
                "spread_net": hh.get("spread_net"),
                "t_paired_by_month": hh.get("t_paired_by_month"),
            }
        return out

    o, n = _by_id(old), _by_id(receipt)
    comparison, changed = [], []
    for sid in sorted(set(o) | set(n)):
        row = {"scenario_id": sid, "old": o.get(sid), "new": n.get(sid),
               "changed": o.get(sid) != n.get(sid)}
        comparison.append(row)
        if row["changed"]:
            changed.append(sid)
    receipt["grade_comparison"] = {
        "vs_receipt": str(SB.RECEIPT_PATH),
        "n_scenarios": len(comparison),
        "n_changed": len(changed),
        "changed_ids": changed,
        "expected": ("zero changes: event_type is not a retrieval predicate, "
                     "so the analogue sets are identical by construction. A "
                     "nonzero count here is a bug report, not a finding."),
        "rows": comparison,
    }
    receipt["compared_at_utc"] = datetime.now(timezone.utc).isoformat()
    RERUN_PATH.write_text(json.dumps(receipt, indent=1, default=str),
                          encoding="utf-8")

    d = receipt["mappability_delta"]
    print(f"\nMAPPABILITY: maps-to-nothing {d['maps_to_nothing_rate_before']:.1%}"
          f" -> {d['maps_to_nothing_rate_after']:.1%} ({d['field_that_moved']})")
    print(f"GRADE CHANGES: {len(changed)} of {len(comparison)}"
          + (f" -- {changed}" if changed else " (as expected)"))
    print(f"[receipt] -> {RERUN_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
