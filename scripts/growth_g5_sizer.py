"""G5 — does NN sizing beat trailing-vol sizing on the champion book?

`docs/ROADMAP_2026-09-07_GROWTH_BOOK_AMENDMENT.md` §3, item G5.

THE QUESTION, PRECISELY
=======================
The champion frozen in G4 is held fixed. Two exposure rules are put on it:

  NN        a walk-forward GRU on market/regime features forecasting next
            month's q05/q50/q95 of THIS book, turned into quarter-Kelly
            exposure. Eight seeds; the SEED-MEAN is the object judged.
  BASELINE  Moreira-Muir trailing-volatility targeting. No learning.

Both are then re-levered to the SAME drawdown budget, and their terminal
wealths compared at that common risk. **Development era only** — 1999-2015. The
sealed era is not opened by this job and this module has no path to it.

WHY THE COMPARISON IS AT EQUAL DRAWDOWN AND NOT AT EQUAL EXPOSURE
=================================================================
Because two exposure rules produce two different risks, and a terminal wealth
compared across two risks is a comparison of two leverages. `growth.
admissible_leverage` puts both on the budget first; the receipt prints the
leverage each needed to get there, which is itself informative — a rule that
reaches the budget at 1.9x was running much less risk than one that reaches it
at 1.1x.

THE NULL THIS JOB OWES ITSELF
=============================
`constant_1x` — the champion held flat — is in the table. If neither sizing rule
beats holding the book, the sizing question is answered for both of them, and a
receipt that only compares the two rules to each other could not say so.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import receipt_provenance as RP          # noqa: E402
from learner import growth as GR                               # noqa: E402
from learner import growth_lab as GL                           # noqa: E402
from learner import growth_sizer as GS                         # noqa: E402
from scripts import growth_g2_generation0 as G2                # noqa: E402
from scripts import growth_g4_seal as G4                       # noqa: E402

OUT_DIR = GL.OUT_DIR
#: the sizer's development window. WIDER than the leaderboard's, because the
#: champion is a panel book that exists from 1999 and the sizer does not need
#: the model genomes' 2004 warm-up. Still development: it stops at 2015-12.
SIZER_DEV_START = GL.DEV_START
#: both rules are graded at this rate, the one G4's claim was made at.
COST_BPS = 25.0


def run(*, verbose: bool = True, argv=None, seeds=None) -> dict:
    t0 = datetime.now(timezone.utc)
    tracker = RP.InputTracker()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    from scripts import w3_neural_floored as W3B
    from learner import neural_long as N
    free = W3B.free_gb()
    if free is not None and free < 6.0:
        raise SystemExit(f"REFUSED: {free:.1f} GB free, floor 6.0 GB.")
    if not GS.torch_available():
        raise SystemExit("REFUSED: torch is not importable; this job will not "
                         "substitute a different model class under a neural "
                         "heading.")
    device, device_info = N.resolve_device(prefer_cuda=True)

    seal_path = OUT_DIR / "G4_seal.json"
    if not seal_path.exists():
        raise SystemExit(f"REFUSED: {seal_path} is missing; the sizer sizes a "
                         "FROZEN champion and cannot choose one.")
    tracker.opened(seal_path, note="the frozen champion")
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    champ = GL.Genome(
        genome_id=seal["champion_genome"]["genome_id"],
        family=seal["champion_genome"]["family"],
        base=seal["champion_genome"]["base"],
        spec=seal["champion_genome"]["spec"],
        overlay=tuple(seal["champion_genome"]["overlay"]),
        parent_ids=tuple(seal["champion_genome"]["parent_ids"]),
        mutation_history=tuple(seal["champion_genome"]["mutation_history"]))

    panel, uni, fp = G2.load_panel(tracker, verbose=verbose)
    ctx = GL.market_context(panel, tracker)
    book_full = G4.build_champion_series(champ, panel, ctx, COST_BPS)

    # ---- DEVELOPMENT ONLY, and the latch says so before anything is fitted.
    book = GL.dev(book_full, start=SIZER_DEV_START)
    GL.assert_development_only(book, "the champion book handed to the sizer")
    spy = GL.dev(ctx["spy"].dropna(), start=SIZER_DEV_START)
    rf = GL.dev(ctx["rf"].dropna(), start=SIZER_DEV_START)
    ctx_dev = ctx.loc[[m for m in ctx.index if str(m) in set(book.index)]]

    feats = GS.regime_features(ctx_dev, book, panel)
    GL.assert_development_only(feats["spy_vol_21d"], "the sizer's feature frame")
    if verbose:
        print(f"sizer window {book.index[0]}..{book.index[-1]} "
              f"({len(book)} months), {len(GS.FEATURES)} features, "
              f"device {device_info.get('device_actually_used')}", flush=True)

    use_seeds = tuple(seeds) if seeds else GS.SEEDS
    fc = GS.walk_forward_quantiles(feats, book, seeds=use_seeds, device=device,
                                   verbose=verbose)

    # ---------------------------------------------------------------- arms
    arms, exposures, metas = {}, {}, {}

    e_flat = pd.Series(1.0, index=pd.Index([str(x) for x in book.index]))
    arms["constant_1x_NULL"], metas["constant_1x_NULL"] = GS.apply_exposure(
        book, rf, e_flat, cost_bps=COST_BPS)
    exposures["constant_1x_NULL"] = e_flat

    e_vt = GS.trailing_vol_exposure(book)
    arms["trailing_vol_MOREIRA_MUIR"], metas["trailing_vol_MOREIRA_MUIR"] = \
        GS.apply_exposure(book, rf, e_vt, cost_bps=COST_BPS)
    exposures["trailing_vol_MOREIRA_MUIR"] = e_vt

    e_nn = GS.kelly_exposure(fc["seed_mean"], rf)
    arms["nn_seedmean_kelly"], metas["nn_seedmean_kelly"] = GS.apply_exposure(
        book, rf, e_nn, cost_bps=COST_BPS)
    exposures["nn_seedmean_kelly"] = e_nn

    for s in use_seeds:
        name = f"nn_seed_{s}_kelly"
        e = GS.kelly_exposure(fc["per_seed"][s], rf)
        arms[name], metas[name] = GS.apply_exposure(book, rf, e, cost_bps=COST_BPS)
        exposures[name] = e

    table = GS.compare_at_equal_drawdown(arms, spy, rf, cost_bps=COST_BPS)
    for name, row in table.items():
        row["exposure"] = {
            "mean": round(float(exposures[name].mean(skipna=True)), 4)
            if exposures[name].notna().any() else None,
            "min": round(float(exposures[name].min(skipna=True)), 4)
            if exposures[name].notna().any() else None,
            "max": round(float(exposures[name].max(skipna=True)), 4)
            if exposures[name].notna().any() else None,
            "months_without_a_forecast":
                metas[name].get("months_held_at_exposure_1_for_want_of_a_forecast"),
            "mean_abs_change": metas[name].get("mean_abs_exposure_change"),
            "overlay_cost_annual_pct": metas[name].get("overlay_cost_annual_pct"),
        }

    # ------------------------------------------------------- the deflation
    from learner import inference as INF
    n_sizer_cells = len(arms)
    for name, s in arms.items():
        d = INF.deflated_sharpe(
            (s - spy.reindex(s.index)).dropna().to_numpy(), n_trials=n_sizer_cells)
        table[name]["dsr_over_sizer_family"] = d.get("dsr")
        table[name]["dsr_block"] = d

    nn = table["nn_seedmean_kelly"]
    vt = table["trailing_vol_MOREIRA_MUIR"]
    flat = table["constant_1x_NULL"]
    verdict = {
        "nn_beats_trailing_vol_at_equal_drawdown": bool(
            (nn["tw_at_budget"] or 0) > (vt["tw_at_budget"] or 0)),
        "nn_beats_the_flat_null_at_equal_drawdown": bool(
            (nn["tw_at_budget"] or 0) > (flat["tw_at_budget"] or 0)),
        "trailing_vol_beats_the_flat_null_at_equal_drawdown": bool(
            (vt["tw_at_budget"] or 0) > (flat["tw_at_budget"] or 0)),
        "nn_dsr_over_the_sizer_family_gt_0_95": bool(
            (nn.get("dsr_over_sizer_family") or 0) > 0.95),
        "seed_mean_beats_the_median_seed": None,
    }
    seed_tw = sorted(table[f"nn_seed_{s}_kelly"]["tw_at_budget"] or 0.0
                     for s in use_seeds)
    med = float(np.median(seed_tw)) if seed_tw else None
    verdict["seed_mean_beats_the_median_seed"] = bool(
        (nn["tw_at_budget"] or 0) > (med or 0))
    verdict["MATURED"] = bool(
        verdict["nn_beats_trailing_vol_at_equal_drawdown"]
        and verdict["nn_dsr_over_the_sizer_family_gt_0_95"])
    verdict["maturity_rule"] = (
        "amendment §3: the NN 'matures' when its vol targeting beats trailing-vol "
        "targeting on after-cost TW at equal maxDD with DSR > 0.95. This job "
        "tests the DEVELOPMENT half of that; the sealed half belongs to a later "
        "session and is NOT run here.")

    out = {
        "job": "G5_sizer",
        "lane": "G growth book",
        "licence": "PRODUCT_EXPERIMENT",
        "question": ("on the frozen champion, does a walk-forward quantile "
                     "network sizing the book beat Moreira-Muir trailing-vol "
                     "targeting on after-cost terminal wealth at equal maxDD?"),
        "champion_genome_id": seal["champion_genome_id"],
        "champion_sha256": seal["champion_sha256"],
        "sizer": GS.describe(),
        "device": device_info,
        "cuda_available": device_info.get("cuda_available"),
        "device_actually_used": device_info.get("device_actually_used"),
        "requirements_gpu_satisfied": bool(device_info.get("cuda_available")),
        "development_window": [str(book.index[0]), str(book.index[-1])],
        "development_months": int(len(book)),
        "sealed_era_openings": len(GL.sealed_openings()),
        "sealed_era_touched_by_this_job": False,
        "walk_forward_folds": fc["folds"],
        "quantile_crossing_repair": fc["quantile_crossing_repair"],
        "cost_bps_per_side": COST_BPS,
        "sizer_family_cells": n_sizer_cells,
        "table": table,
        "verdict": verdict,
        "seed_spread_tw_at_budget": {
            "min": round(min(seed_tw), 4) if seed_tw else None,
            "median": round(med, 4) if med is not None else None,
            "max": round(max(seed_tw), 4) if seed_tw else None,
            "seed_mean_object": nn["tw_at_budget"],
        },
        "llm_spend_usd": 0.0,
        "llm_calls": 0,
        "memory_free_gb_before": free,
        "wall_seconds": round((datetime.now(timezone.utc) - t0).total_seconds(), 1),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }
    out["headline"] = (
        f"beta {nn['beta']} (NN) vs {vt['beta']} (trailing vol) vs {flat['beta']} "
        f"(flat): at the SAME drawdown budget over {out['development_months']} "
        f"development months at {COST_BPS:.0f} bps, NN sizing reaches TW "
        f"{nn['tw_at_budget']} at {nn['leverage_at_budget']}x, Moreira-Muir "
        f"{vt['tw_at_budget']} at {vt['leverage_at_budget']}x, and the flat book "
        f"{flat['tw_at_budget']} at {flat['leverage_at_budget']}x. "
        f"NN DSR {nn.get('dsr_over_sizer_family')} over {n_sizer_cells} sizer "
        f"cells; MATURED = {verdict['MATURED']}")
    RP.attach(out, argv or sys.argv,
              {"job": "G5_sizer", "cost_bps": COST_BPS,
               "seeds": list(use_seeds),
               "development_window": [SIZER_DEV_START, GL.DEV_END]}, tracker)
    (OUT_DIR / "G5_sizer.json").write_text(
        json.dumps(out, indent=1, default=str), encoding="utf-8")
    return out


def main(argv=None) -> int:                                # pragma: no cover
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", type=int, default=0,
                    help="use only the first N seeds (smoke runs); 0 = all 8")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    seeds = GS.SEEDS[:a.seeds] if a.seeds else None
    out = run(verbose=not a.quiet, argv=sys.argv, seeds=seeds)
    print("\n" + out["headline"])
    print(f"\nreceipt: {OUT_DIR / 'G5_sizer.json'}")
    return 0


if __name__ == "__main__":                                 # pragma: no cover
    raise SystemExit(main())
