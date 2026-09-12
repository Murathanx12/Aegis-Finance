"""X_anon_gap -- what does anonymising the digest COST, measured on our data?

The literature disagrees by design, not by noise. arXiv:2511.15364 (credit
downgrades) finds anonymisation degrades performance by more than the lookahead
bias it prevents; Glasserman-Lin find the opposite on a daily sentiment
long-short -- anonymising tickers IMPROVED returns. `NEGATIVE_RESULTS.md`
section 19 already carries the second. Neither ran THIS model on THIS
cross-section, so neither settles it, and picking a side by citation count is
not a method.

So: R2's frozen prompt, the SAME cells, three ways -- `read_MASKED` (the live
arm), `read_RAW` (identical construction from the un-anonymised text), and the
shuffled-digest control for each -- and the gap is the block-paired difference
of their NET returns with its own Newey-West t. Spec
`docs/research_notes/2026-09-12/spec_lane_x.md` section 2.

TWO THINGS THIS JOB WILL NOT DO
===============================
It will not start the model server. `llama-server` is owned by the desktop
shell; a research job that boots an 8 GB server is a job that collides with
another one mid-run. When the reader is not answering this writes
`PENDING_MODEL` with the **exact cell list frozen and hashed**, so the run that
happens when the model is up asks the same question rather than a similar one.

It will not switch the lane to the raw arm on a citation. Spec section 2.2's
default stands until a measured, block-paired gap from our own PANEL-B says
otherwise, and the AMNESIA canary cross-checks it: a raw arm that wins WHILE
the canary gap is large is presumptively memorisation, and MASKED is adopted
regardless of the raw arm's score.

    python -m scripts.night_x_anonymisation_gap --cells 300 --run 1
    python -m scripts.night_factory_jobs X_anon_gap --run 1
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import protocol_p16 as pp                         # noqa: E402
from backend.services import x_lane_data as xd                          # noqa: E402
from backend.services.portfolio_intelligence.r2_trial import (          # noqa: E402
    COST_BPS_PER_SIDE, fingerprint as prereg_fingerprint)
from scripts.night_r2_monthly_llm import (                              # noqa: E402
    _nw_t, _probe, _r, _run_digests, grade, paired_vs,
    widened_cells_and_docs, widened_digests)

RUN_DATE = "2026-09-12"
OUT = REPO / "backend" / "data" / "optimus" / f"night_factory_{RUN_DATE}"
JOB = "X_anon_gap"

#: The rule this lane adopts, verbatim from spec section 2.2, so a reader of the
#: receipt never has to re-derive why an arm was chosen.
ADOPTION_RULE = (
    "1. Compute the anonymisation gap on PANEL-B: net_ann_pct(read_RAW) minus "
    "net_ann_pct(read_MASKED), block-paired, Newey-West lag 2, net of "
    "25 bps a side on realised turnover. This settles sign and size for THIS "
    "model, prompt and cross-section; it does not have to agree with either "
    "paper, because neither paper ran this model on this data. "
    "2. Cross-check the AMNESIA canary: if read_RAW beats read_MASKED but the "
    "canary's real-name-minus-masked accuracy gap is also large and positive, "
    "the raw arm's edge is presumptively memorisation and MASKED is adopted "
    "regardless of the raw score. If the canary gap stays at or below +0.02 "
    "(TRIAL-R2's own adopt threshold) while read_RAW still wins, the extra "
    "accuracy is more plausibly entity information masking destroys, and RAW "
    "may be preferred -- but every receipt from that point prints BOTH numbers "
    "and the canary cross-check, permanently, never just the winner. "
    "3. Default while the raw arm has not run: stay on read_MASKED, the "
    "registered TRIAL-R2 arm. Switch only on a measured gap from our PANEL-B.")

#: TRIAL-R2's own adopt threshold for the canary, reused rather than re-chosen.
AMNESIA_ADOPT_MAX = 0.02


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def paired_gap(raw: dict, masked: dict) -> dict:
    """RAW minus MASKED, block by block, on the NET series.

    A level subtraction of two annualised numbers has no standard error. The
    gap is a paired difference over the shared month blocks, which is what a t
    can be computed on -- and when the two arms produce an IDENTICAL series
    (the degenerate case the known-answer test uses: a no-op mask), the
    difference has zero variance and the t is REFUSED as `None` rather than
    reported as 0.0 from a 1e-18 floor.
    """
    a = np.asarray(raw.get("_monthly_net") or [], dtype="float64")
    b = np.asarray(masked.get("_monthly_net") or [], dtype="float64")
    n = min(len(a), len(b))
    if n == 0:
        return {"gap_pct_pt": None, "gap_nw_t": None, "gap_paired_blocks": 0,
                "note": "neither arm produced a graded month block"}
    ma, mb = raw.get("_months") or [], masked.get("_months") or []
    if ma[:n] != mb[:n]:
        return {"gap_pct_pt": None, "gap_nw_t": None, "gap_paired_blocks": n,
                "note": ("REFUSED: the two arms do not share their month blocks, so a "
                         "paired difference would pair different dates")}
    d = a[:n] - b[:n]
    degenerate = bool(np.all(np.abs(d) < 1e-12))
    return {
        "gap_pct_pt": _r(float(d.mean()) * 12 * 100, 4),
        "gap_nw_t": None if (degenerate or n < 6) else _r(_nw_t(d), 3),
        "gap_paired_blocks": int(n),
        "gap_monthly_sd_pp": (None if n < 2 else _r(float(d.std(ddof=1)) * 100, 4)),
        "note": ("the two arms read the SAME cells in the same months, so this is a "
                 "paired difference, not two levels subtracted"
                 + ("; the difference is identically zero, so its t is undefined and is "
                    "reported as null rather than as 0.0" if degenerate else "")
                 + ("; fewer than 6 paired blocks, no t" if (n < 6 and not degenerate) else "")),
    }


def adjudicate(gap: dict, canary: dict) -> tuple[str, str]:
    """(adopted_arm, why) under spec section 2.2, applied literally."""
    g = gap.get("gap_pct_pt")
    am = canary.get("gap")
    if g is None:
        return ("CONDITIONAL_INSUFFICIENT_DATA",
                "no measured gap: the raw arm has not produced a graded block series")
    if g <= 0:
        return ("MASKED",
                f"the raw arm does not beat the masked arm ({g:+.4f} pp/yr net); rule 3's "
                "default stands and nothing changes")
    if am is None:
        return ("CONDITIONAL_INSUFFICIENT_DATA",
                f"the raw arm leads by {g:+.4f} pp/yr net but the AMNESIA canary gap could "
                "not be read, and rule 2 requires the cross-check before a switch")
    if am > AMNESIA_ADOPT_MAX:
        return ("MASKED",
                f"the raw arm leads by {g:+.4f} pp/yr net but the AMNESIA canary gap is "
                f"{am:+.4f} > +{AMNESIA_ADOPT_MAX}: the edge is presumptively memorisation, "
                "and rule 2 adopts MASKED regardless of the raw score")
    return ("RAW",
            f"the raw arm leads by {g:+.4f} pp/yr net while the AMNESIA canary gap is "
            f"{am:+.4f} <= +{AMNESIA_ADOPT_MAX}: rule 2's second branch. Every receipt from "
            "here prints BOTH arms and the canary, permanently")


def _protocol(payload_paths: dict, *, flip_rate=None, flip_n=0, realised_bps=None,
              nothing_was_read: bool = False) -> dict:
    """The P1-P6 block this job writes.

    `nothing_was_read` is the refusal path: no digests were built, so no control
    ran, and claiming `anonymised: true` there would be a claim with no artefact
    -- refused by the validator, correctly.
    """
    return pp.block(
        anonymised=not nothing_was_read,
        anonymised_evidence=payload_paths["masked_digests"],
        placebo_run=not nothing_was_read,
        placebo_evidence=payload_paths["shuffled_control"],
        time_locked_run=False,
        time_locked_model=("ChronoGPT is specced as an OPTIONAL separate deliverable "
                           "(spec section 1.6); it is not distributed as GGUF and needs a "
                           "transformers path this job does not have"),
        cutoff="2024-06-30", cutoff_source=(
            "community cutoff trackers + provider pages for Qwen2.5-7B-Instruct; NOT an "
            "official Alibaba cutoff page (spec section 1.3)"),
        cutoff_confidence="MEDIUM",
        universe_vintage_id=payload_paths.get("universe_vintage_id"),
        delisting_handled=True,
        universe_note=("PANEL-B cells require the SUCCESSOR month to be literally the next "
                       "one, so a delisted or halted name contributes no two-month return "
                       "labelled as one (night_r2_monthly_llm.widened_forward_excess)"),
        flip_pass_rate=flip_rate, flip_n=flip_n,
        flip_test=("not run in this job: the direction-flip test needs C1's sign_flip "
                   "counterfactuals, which X2_elasticity reads (spec section 3.5)"),
        ece=None, n_bins=10, brier=None, brier_decomposition={},
        cost_curve_id="r2_trial.COST_BPS_PER_SIDE (25 bps/side on realised turnover)",
        cost_bps_per_side=COST_BPS_PER_SIDE, realised_bps=realised_bps,
        costed=not nothing_was_read, gross_reported_separately=True,
        single_agent_baseline_run=True,
        field_provenance={
            "dir, conf": "Qwen2.5-7B-Instruct-Q4_K_M via the frozen TRIAL-R2 system+user prompt",
            "fwd": "deterministic: SPY-excess open-to-open month return from bars.parquet",
            "gap_pct_pt, gap_nw_t": "deterministic arithmetic in night_x_anonymisation_gap",
        },
        homogeneity_metric=None)


def X_anon_gap(backend: str = "local_gguf", cells: int = 300, seed: int = 20260909,
               max_tokens: int = 48, smoke: bool = False, run: int = 1) -> dict:
    """The raw-vs-masked read on one stratified sample of PANEL-B cells."""
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    canary = xd.amnesia_gap()
    base = {
        "job": JOB, "lane": "X", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "panel": "PANEL-B", "backend": backend,
        "PREREGISTRATION": prereg_fingerprint(),
        "question": ("Does R2's frozen prompt read the SAME PANEL-B cells better from the "
                     "RAW text than from the anonymised text -- and if it does, is that "
                     "information or memory?"),
        "adoption_rule_text": ADOPTION_RULE,
        "amnesia_gap": canary,
        "cost_model": {"cost_bps_per_side": COST_BPS_PER_SIDE,
                       "charged_on": "realised turnover sum|dw| per monthly rebalance"},
    }
    try:
        panel_cells, news, funnel = widened_cells_and_docs()
    except (FileNotFoundError, ValueError) as exc:
        return {**base, "verdict": f"REFUSED: {exc}",
                "headline": "the widened panel could not be built on this checkout",
                # NOTHING was read, so nothing is claimed: `anonymised` is false
                # with a null path rather than true with no artefact behind it.
                # A receipt that claims its controls ran on a checkout where the
                # panel does not exist is the exact failure P1's evidence paths
                # were added to catch.
                "P1_P6": _protocol({"masked_digests": None, "shuffled_control": None},
                                   nothing_was_read=True),
                "LAP": pp.lap(False, reason=(
                    "PANEL-B (2025-01..2026-07) is entirely AFTER Qwen2.5-7B's ~2024-06 "
                    "cutoff, so LAP is structurally near zero here (spec section 1.3); L3 "
                    "measures it on PANEL-A")),
                "anonymisation_gap": pp.anonymisation_gap(
                    reason="the panel could not be built, so no arm was read"),
                "elapsed_s": round(time.time() - t0, 1), "written_utc": _now()}

    dig_mask, dig_real, cov = widened_digests(panel_cells, news)
    shared = sorted(set(dig_mask) & set(dig_real))
    n_draw = 8 if smoke else min(cells, len(shared))
    drawn = xd.stratified_cells(shared, n=n_draw, seed=seed)
    fp = xd.cells_fingerprint(drawn)
    # NAME THE SIDECAR SO THE BOARD CANNOT READ IT AS A RECEIPT.
    # `night_leaderboard_sync.RECEIPT` is `^(?P<job>.+)_run(\d{2})\.json$`, so a
    # file called `X_anon_gap_cells_run01.json` parses as a JOB called
    # `X_anon_gap_cells` and reaches the board as a row -- refused for having no
    # P1_P6 block, which is a true statement about a file that was never a
    # receipt. The suffix goes AFTER the run number.
    cells_path = OUT / f"{JOB}_run{run:02d}{'_smoke' if smoke else ''}_cells.json"
    cells_path.write_text(json.dumps(
        {"job": JOB, "run": run, "seed": seed, "stratified_by": "month block",
         "drawn_from_cells": len(shared), **fp,
         "cells": [list(c) for c in drawn], "written_utc": _now()},
        indent=1), encoding="utf-8")

    fwd = {(str(r.symbol), str(r.month)): float(r.excess_vw_1m)
           for r in panel_cells.itertuples()}
    sub_mask = {k: dig_mask[k] for k in drawn}
    sub_real = {k: dig_real[k] for k in drawn}
    paths = {"masked_digests": str(cells_path),
             "shuffled_control": str(cells_path),
             "universe_vintage_id": None}
    base.update({
        "construction": funnel, "masking": cov,
        "cells_frozen": {**fp, "file": str(cells_path), "seed": seed,
                         "stratified_by": "month block (canon section 58's dependence unit)",
                         "drawn_from_cells": len(shared),
                         "months": sorted({k[1] for k in drawn})},
    })

    refusal = _probe(backend)
    if refusal is not None:
        return {**base,
                "P1_P6": _protocol(paths),
                "LAP": pp.lap(False, reason=(
                    "PANEL-B (2025-01..2026-07) is entirely AFTER Qwen2.5-7B's ~2024-06 "
                    "cutoff, so every cell here is already the post-cutoff arm of L3's "
                    "split (spec section 1.3)")),
                "anonymisation_gap": pp.anonymisation_gap(reason=(
                    "PENDING_MODEL: the raw arm has not been read, so there is no gap. "
                    "The cell list is frozen and hashed so the run that measures it asks "
                    "the same question")),
                "pending_when_the_reader_is_up": [
                    f"read_RAW: the {len(drawn)} frozen cells, un-anonymised digests",
                    f"read_MASKED: the SAME {len(drawn)} cells, anonymised digests",
                    "control_SHUFFLED_masked and control_SHUFFLED_raw: the same cells, "
                    f"each given a digest from a different month (rng seed {seed})",
                    "the gap: net(raw) minus net(masked), block-paired, NW lag 2",
                    f"one command: python -m scripts.night_x_anonymisation_gap "
                    f"--cells {n_draw} --seed {seed} --run {run}",
                ],
                "verdict": (
                    "PENDING_MODEL: the cell draw, the digests and the adjudication rule are "
                    "built and frozen; the reader is not answering and this job does not "
                    f"start it (the desktop shell owns llama-server). Probe said: {refusal}"),
                "headline": (
                    f"{len(drawn)} cells over {len(set(k[1] for k in drawn))} month blocks "
                    f"frozen at sha256 {fp['cells_sha256'][:12]}; AMNESIA gap "
                    f"{canary.get('gap')} carried from R2; NO model call was made"),
                "elapsed_s": round(time.time() - t0, 1), "written_utc": _now()}

    rng = random.Random(seed)
    rows_path = OUT / f"{JOB}_answers_run{run:02d}{'_smoke' if smoke else ''}.jsonl"
    if rows_path.exists():
        rows_path.unlink()
    kw = {"backend": backend, "max_tokens": max_tokens, "rng": rng, "fwd": fwd,
          "t0": t0, "rows_path": rows_path}
    rows_raw, u_raw = _run_digests(sub_real, "read_RAW", **kw)
    rows_mask, u_mask = _run_digests(sub_mask, "read_MASKED", **kw)
    rows_craw, u_craw = _run_digests(sub_real, "control_SHUFFLED_raw", shuffle=True, **kw)
    rows_cmask, u_cmask = _run_digests(sub_mask, "control_SHUFFLED_masked", shuffle=True, **kw)

    g_raw = grade(rows_raw, "raw digest -> direction")
    g_mask = grade(rows_mask, "masked digest -> direction")
    g_craw = grade(rows_craw, "shuffled raw digest (control)")
    g_cmask = grade(rows_cmask, "shuffled masked digest (control)")
    gap = paired_gap(g_raw, g_mask)
    adopted, why = adjudicate(gap, canary)
    realised = g_mask.get("turnover_per_rebalance")
    realised_bps = (None if realised is None
                    else _r(float(realised) * COST_BPS_PER_SIDE, 2))

    out = {
        **base,
        "answers_file": str(rows_path),
        "arms": {"read_RAW": {k: v for k, v in g_raw.items() if not k.startswith("_")},
                 "read_MASKED": {k: v for k, v in g_mask.items() if not k.startswith("_")},
                 "control_SHUFFLED_raw": {k: v for k, v in g_craw.items()
                                          if not k.startswith("_")},
                 "control_SHUFFLED_masked": {k: v for k, v in g_cmask.items()
                                             if not k.startswith("_")}},
        "raw_minus_its_control": paired_vs(g_raw, g_craw, "raw read minus shuffled raw"),
        "masked_minus_its_control": paired_vs(g_mask, g_cmask,
                                              "masked read minus shuffled masked"),
        "ANONYMISATION_GAP": {**gap, "net_ann_pct_raw": g_raw.get("long_short_ann_pct_NET"),
                              "net_ann_pct_masked": g_mask.get("long_short_ann_pct_NET"),
                              "net_ann_pct_shuffled_control_raw":
                                  g_craw.get("long_short_ann_pct_NET"),
                              "net_ann_pct_shuffled_control_masked":
                                  g_cmask.get("long_short_ann_pct_NET"),
                              "adopted_arm": adopted, "why": why},
        "usage": {"tokens_in": sum(u["tokens_in"] for u in (u_raw, u_mask, u_craw, u_cmask)),
                  "tokens_out": sum(u["tokens_out"] for u in (u_raw, u_mask, u_craw, u_cmask)),
                  "cost_usd": 0.0,
                  "refusals": {"read_RAW": u_raw["refused"], "read_MASKED": u_mask["refused"],
                               "control_SHUFFLED_raw": u_craw["refused"],
                               "control_SHUFFLED_masked": u_cmask["refused"]}},
        "P1_P6": _protocol({**paths, "shuffled_control": str(rows_path),
                            "masked_digests": str(rows_path)},
                           realised_bps=realised_bps),
        "LAP": pp.lap(False, reason=(
            "PANEL-B (2025-01..2026-07) is entirely AFTER Qwen2.5-7B's ~2024-06 cutoff, so "
            "every cell here is already the post-cutoff arm of L3's split (spec section 1.3)")),
        "anonymisation_gap": pp.anonymisation_gap(
            gap.get("gap_pct_pt"), t=gap.get("gap_nw_t"), adopted_arm=adopted,
            reason=None if gap.get("gap_pct_pt") is not None else why),
        "elapsed_s": round(time.time() - t0, 1), "written_utc": _now(),
    }
    out["headline"] = (
        f"{len(drawn)} cells, {gap.get('gap_paired_blocks')} paired blocks: raw "
        f"{g_raw.get('long_short_ann_pct_NET')}%/yr net vs masked "
        f"{g_mask.get('long_short_ann_pct_NET')}%/yr net -> gap "
        f"{gap.get('gap_pct_pt')} pp/yr t {gap.get('gap_nw_t')}; AMNESIA canary "
        f"{canary.get('gap')}; adopted {adopted}")
    out["verdict"] = f"ADOPTED_ARM={adopted}: {why}"
    out["family_max_p"] = None
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="local_gguf")
    ap.add_argument("--cells", type=int, default=300,
                    help="stratified sample size, equal across month blocks")
    ap.add_argument("--seed", type=int, default=20260909)
    ap.add_argument("--max-tokens", type=int, default=48)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    p = X_anon_gap(backend=a.backend, cells=a.cells, seed=a.seed,
                   max_tokens=a.max_tokens, smoke=a.smoke, run=a.run)
    p["run"] = a.run
    OUT.mkdir(parents=True, exist_ok=True)
    out = Path(a.out) if a.out else OUT / f"{JOB}_run{a.run:02d}{'_smoke' if a.smoke else ''}.json"
    out.write_text(json.dumps(p, indent=1, default=str), encoding="utf-8")
    reasons = pp.refuse_reasons(JOB, p)
    print(f"\n{JOB}: {p['headline']}\n  verdict: {p['verdict']}\n  -> {out}")
    if reasons:
        print("  PROTOCOL INCOMPLETE (the leaderboard will refuse this row): "
              + "; ".join(reasons))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
