"""X4_regime_route -- does routing R2's read through the sensor help?

FINSABER's failure is asymmetric: the LLM trader is right in bulls and wrong in
bears. So route the read through a market sensor and grade ROUTED against
UNROUTED -- against the same mechanism run on every block, never against a
naive benchmark, because the question is what the ROUTING contributes and not
whether the base mechanism works (that is TRIAL-R2's job).

NO NEW MODEL CALLS. R2's answers are on disk; this job re-grades them twice
with a block filter in between. The sensor needs SPY bars (local) and the VIX
(FRED, network): when either is unobserved the job says so BY NAME and reports
`unknown` rather than routing on half a sensor.

THE EXPLORATORY SPLIT IS LABELLED AS ONE
========================================
Spec section 5.2: looking at PANEL-B's 19 existing blocks to see where the edge
sits is permitted under `PRODUCT_EXPERIMENT`'s explore-dirty licence -- but the
rule that comes out of that look is then evaluated OUT OF SAMPLE on new blocks,
not treated as proven. This receipt therefore prints the in-sample split as
`EXPLORATORY_IN_SAMPLE` and admits nothing.

    python -m scripts.night_x4_regime_route --run 1
    python -m scripts.night_factory_jobs X4_regime_route --run 1
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import market_sensor as ms                       # noqa: E402
from backend.services import protocol_p16 as pp                        # noqa: E402
from backend.services import x_lane_data as xd                         # noqa: E402
from backend.services.portfolio_intelligence.r2_trial import (         # noqa: E402
    COST_BPS_PER_SIDE)
from scripts.night_l3_lookahead import MODEL_CUTOFFS                   # noqa: E402
from scripts.night_r2_monthly_llm import _nw_t, _r, grade              # noqa: E402

RUN_DATE = "2026-09-12"
OUT = REPO / "backend" / "data" / "optimus" / f"night_factory_{RUN_DATE}"
JOB = "X4_regime_route"

#: The regime the routed book is admitted in. Declared here, before the split
#: is looked at, so the exploratory look cannot quietly choose it.
ADMITTED_REGIME = ms.RISK_ON


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def month_start(month: str) -> str:
    """The routing decision for month M is taken at M's FIRST day, from data
    published before it -- the sensor reads a trailing window that ends there,
    so nothing inside month M informs the decision to trade month M."""
    return f"{month}-01"


def regime_by_month(months, *, bars=None, bars_path=None, vix_series=None) -> dict:
    rows = ms.regime_series([month_start(m) for m in months], bars=bars,
                            bars_path=bars_path, vix_series=vix_series)
    return {m: r for m, r in zip(months, rows)}


def route(answers: list[dict], regimes: dict, *, tag: str = "read_MASKED",
          admitted: str = ADMITTED_REGIME) -> dict:
    """Grade the same answers routed and unrouted, and difference the blocks."""
    rows = [r for r in answers if str(r.get("tag")) == tag]
    kept = [r for r in rows
            if (regimes.get(str(r.get("month"))) or {}).get("regime") == admitted]
    unrouted = grade(rows, "unrouted: every block")
    routed = grade(kept, f"routed: {admitted} blocks only")
    out = {"admitted_regime": admitted,
           "unrouted": {k: v for k, v in unrouted.items() if not k.startswith("_")},
           "routed": {k: v for k, v in routed.items() if not k.startswith("_")},
           "blocks_admitted": sorted({str(r.get("month")) for r in kept}),
           "blocks_total": sorted({str(r.get("month")) for r in rows}),
           "cells_admitted": len(kept), "cells_total": len(rows)}
    # THE ROUTED BOOK IS COMPARED ON THE BLOCKS IT KEPT, and the unrouted one on
    # all of them, so the difference of the two MEANS is not a paired
    # difference and is not reported as one. What IS paired: on the admitted
    # blocks the two books are identical by construction, so the only thing
    # routing can change is which blocks are in the average. That is stated.
    ur = np.asarray(unrouted.get("_monthly_net") or [], dtype="float64")
    ro = np.asarray(routed.get("_monthly_net") or [], dtype="float64")
    out["comparison"] = {
        "routed_net_ann_pct": routed.get("long_short_ann_pct_NET"),
        "unrouted_net_ann_pct": unrouted.get("long_short_ann_pct_NET"),
        "difference_ann_pct": (
            None if (routed.get("long_short_ann_pct_NET") is None
                     or unrouted.get("long_short_ann_pct_NET") is None)
            else _r(routed["long_short_ann_pct_NET"] - unrouted["long_short_ann_pct_NET"], 3)),
        "routed_blocks": int(ro.size), "unrouted_blocks": int(ur.size),
        "routed_t_nw": _r(_nw_t(ro), 3) if ro.size >= 6 else None,
        "unrouted_t_nw": _r(_nw_t(ur), 3) if ur.size >= 6 else None,
        "not_a_paired_test": (
            "the two books hold the SAME positions on every admitted block; routing "
            "changes only which blocks are in the average, so this difference of two "
            "means is not a paired difference and carries no t of its own. The t on "
            "each book is its own"),
    }
    return out


def _stanzas(*, sensor_ok: bool, evidence: str | None) -> dict:
    cut = MODEL_CUTOFFS["Qwen2.5-7B-Instruct"]
    return {
        "P1_P6": pp.block(
            anonymised=True, anonymised_evidence=str(xd.R2_PANEL_B_ANSWERS),
            placebo_run=False,
            placebo_evidence=None,
            time_locked_run=False,
            time_locked_model="not applicable: X4 makes no model call of its own",
            cutoff=cut["cutoff"], cutoff_source=cut["source"],
            cutoff_confidence=cut["confidence"],
            universe_vintage_id=None, delisting_handled=True,
            universe_note=("the cells are R2's own, whose label construction requires "
                           "the successor month to be literally the next one"),
            flip_pass_rate=None, flip_n=0,
            flip_test="not run in this job: the flip test belongs to X2",
            ece=None, n_bins=10, brier=None, brier_decomposition={},
            cost_curve_id="r2_trial.COST_BPS_PER_SIDE (25 bps/side on realised turnover)",
            cost_bps_per_side=COST_BPS_PER_SIDE, realised_bps=None,
            costed=True, gross_reported_separately=True,
            single_agent_baseline_run=True,
            field_provenance={
                "dir, conf": "Qwen2.5-7B via the frozen TRIAL-R2 prompt, read from disk",
                "regime": ("deterministic: 21-session SPY trend from bars.parquet and "
                           "FRED VIXCLS, thresholds frozen in market_sensor.THRESHOLDS"),
                "routed/unrouted net": "night_r2_monthly_llm.grade, unchanged"}),
        "LAP": pp.lap(False, reason=(
            "PANEL-B (2025-01..2026-07) is entirely AFTER Qwen2.5-7B's ~2024-06 cutoff, "
            "so LAP is structurally near zero on every cell this job re-grades "
            "(spec section 1.3); L3 owns the measurement")),
        "anonymisation_gap": pp.anonymisation_gap(reason=(
            "X4 re-grades R2's already-masked answers and adds no text arm of its own; "
            "X_anon_gap owns the gap")),
    }


def X4_regime_route(bars_path=None, vix_series=None, smoke: bool = False,
                    run: int = 1) -> dict:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    answers = xd.read_answers()
    base = {
        "job": JOB, "lane": "X", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "panel": "PANEL-B", "model_calls": 0,
        "question": ("Does admitting R2's monthly read only in the sensor's risk-on "
                     "regime beat the SAME read admitted in every block?"),
        "sensor": ms.declaration(),
        "control": ("the UNROUTED read over the identical window -- never a naive "
                    "benchmark, because the question is what the routing contributes"),
        "status": "EXPLORATORY_IN_SAMPLE",
        "why_exploratory": (
            "this looks at PANEL-B's existing blocks, which is permitted under "
            "PRODUCT_EXPERIMENT's explore-dirty licence; the rule it suggests is "
            "evaluated OUT OF SAMPLE on new blocks before it is believed, and nothing "
            "here admits or promotes anything (spec section 5.2)"),
    }
    if not answers:
        return {**base, "verdict": f"REFUSED: no R2 answers at {xd.R2_PANEL_B_ANSWERS}",
                "headline": "no answers to route on this checkout",
                **_stanzas(sensor_ok=False, evidence=None),
                "elapsed_s": round(time.time() - t0, 1), "written_utc": _now()}

    months = sorted({str(r.get("month")) for r in answers
                     if str(r.get("tag")) == "read_MASKED"})
    if smoke:
        months = months[:4]
    regimes = regime_by_month(months, bars_path=bars_path, vix_series=vix_series)
    counts: dict[str, int] = {}
    for r in regimes.values():
        counts[str(r.get("regime"))] = counts.get(str(r.get("regime")), 0) + 1
    refusals = sorted({str(r.get("vix_refusal") or r.get("reason"))
                       for r in regimes.values()
                       if r.get("vix_refusal") or r.get("reason")})
    base["regime_by_month"] = regimes
    base["regime_counts"] = counts
    base["sensor_refusals"] = refusals

    if counts.get(ms.UNKNOWN, 0) == len(months) and months:
        return {**base,
                "verdict": ("REFUSED: the sensor could not observe a regime for any "
                            "month, so there is nothing to route on. "
                            + (refusals[0] if refusals else "")),
                "headline": (f"{len(months)} month blocks, 0 with an observed regime; "
                             "the routing question is not answerable from this checkout"),
                **_stanzas(sensor_ok=False, evidence=str(xd.R2_PANEL_B_ANSWERS)),
                "elapsed_s": round(time.time() - t0, 1), "written_utc": _now()}

    routed = route(answers, regimes)
    c = routed["comparison"]
    verdict = (
        f"EXPLORATORY_IN_SAMPLE: routing to {ADMITTED_REGIME} keeps "
        f"{len(routed['blocks_admitted'])}/{len(routed['blocks_total'])} blocks and "
        f"{c['routed_net_ann_pct']}%/yr net against the unrouted "
        f"{c['unrouted_net_ann_pct']}%/yr. This is a look at already-collected data "
        "under the explore-dirty licence; the rule is not admitted until it is "
        "evaluated on blocks it did not choose.")
    return {**base, **routed,
            "verdict": verdict,
            "headline": (f"routed {c['routed_net_ann_pct']}%/yr net on "
                         f"{c['routed_blocks']} blocks vs unrouted "
                         f"{c['unrouted_net_ann_pct']}%/yr on {c['unrouted_blocks']}; "
                         f"regimes {counts}"),
            "family_max_p": None,
            **_stanzas(sensor_ok=True, evidence=str(xd.R2_PANEL_B_ANSWERS)),
            "elapsed_s": round(time.time() - t0, 1), "written_utc": _now()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", default=None)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--out", default=None)
    ap.add_argument("--sensor-only", action="store_true",
                    help="print the sensor's last N sessions and exit")
    ap.add_argument("--sessions", type=int, default=60)
    a = ap.parse_args(argv)
    if a.sensor_only:
        import pandas as pd

        tr = ms.spy_trend(bars_path=Path(a.bars) if a.bars else None)
        tail = tr.tail(a.sessions)
        rows = ms.regime_series([pd.Timestamp(d).date() for d in tail["date"]],
                                bars_path=Path(a.bars) if a.bars else None)
        print(json.dumps({"thresholds": ms.THRESHOLDS, "sessions": rows}, indent=1,
                         default=str))
        return 0
    p = X4_regime_route(bars_path=Path(a.bars) if a.bars else None, smoke=a.smoke,
                        run=a.run)
    p["run"] = a.run
    OUT.mkdir(parents=True, exist_ok=True)
    out = Path(a.out) if a.out else OUT / f"{JOB}_run{a.run:02d}{'_smoke' if a.smoke else ''}.json"
    out.write_text(json.dumps(p, indent=1, default=str), encoding="utf-8")
    print(f"\n{JOB}: {p['headline']}\n  verdict: {p['verdict']}\n  -> {out}")
    reasons = pp.refuse_reasons(JOB, p)
    if reasons:
        print("  PROTOCOL INCOMPLETE: " + "; ".join(reasons))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
