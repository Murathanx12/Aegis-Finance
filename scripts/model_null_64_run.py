"""The 64-draw MODEL NULL for the two studies still gated by a one-draw shuffle.

    python -m scripts.model_null_64_run --study v1         # learner_v1's null arm, x64
    python -m scripts.model_null_64_run --study families   # feature-families null_check, x64
    python -m scripts.model_null_64_run --study all        # the overnight driver

WHY (S36, learner/nullbar.py)
=============================
`learner_v1.json` and `feature_ablation_20260903.json` each ran ONE
shuffled-target draw and read it against `|t| < 2`. That bar is mis-specified:
a model fitted on noise holds one persistent tilt, so the null's own naive t
spans -9..+12 across seeds and a single draw is close to a coin flip. Both
receipts were stamped LEGACY on 2026-09-03; this script buys the correct bar
-- the SAME pipeline fitted on >= 64 distinct within-month permutations
(`shuffle_seed`, threaded through `learner.models.fit_predict` and
`scripts.feature_families_run.walk_forward_preds` for exactly this purpose)
-- and quotes every observed arm as a PERCENTILE of that distribution.

RESUMABILITY
============
One draw is ~9 walk-forward LightGBM fits and minutes of wall clock, so a
crash must lose one draw, not the night: every completed draw is appended as
one JSON line to a scratch file keyed by (study, seed), and a restart skips
seeds already on disk. The final receipt is a NEW file beside the sealed one
-- the sealed receipts are never rewritten (their LEGACY stamp stands; this
file is the correction, not an edit).

WHAT EACH DRAW IS
=================
* v1:        `M.fit_predict("lgbm", "raw", ...)` over `D.walk_forward_splits`,
             horizon 1m -- byte-for-byte the pipeline of v1's NULL arm, with
             the permutation seed varied per draw. Graded by `E.rank_ic` and
             `E.book` (top-50 VW, same costs), like the v1 scoreboard.
* families:  `walk_forward_preds(cols=base+analyst+holder+interaction,
             "lgbm", h=1, shuffle=True)` -- byte-for-byte the pipeline of
             `null_check`, seed varied per draw. Graded by the study's own
             `monthly_ic` / `book_for_horizon`.

Observed statistics are READ from the sealed receipts, never recomputed --
recomputing would grade a different run and call it the same one. The final
block quotes, per arm: p_one_sided (add-one), percentile, and the family
max-statistic correction across ML arms (nullbar.family_max_p), because the
champion was SELECTED for winning.

LICENCE: PRODUCT_EXPERIMENT. This script fits on permuted targets only,
places nothing, and imports no broker.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from learner import dataset as D                            # noqa: E402
from learner import evaluate as E                           # noqa: E402
from learner import models as M                             # noqa: E402
from learner import nullbar as NB                           # noqa: E402

OUT_DIR = REPO / "backend" / "data" / "optimus" / "tracker_backtest"
V1_RECEIPT = OUT_DIR / "learner_v1.json"
FAM_RECEIPT = OUT_DIR / "feature_ablation_20260903.json"

#: the NEW receipts -- beside the sealed ones, never inside them
V1_OUT = OUT_DIR / "learner_v1_model_null_64_20260904.json"
FAM_OUT = OUT_DIR / "feature_ablation_model_null_64_20260904.json"

#: per-draw checkpoints (JSONL, one line per completed draw)
V1_SCRATCH = OUT_DIR / "scratch_model_null_v1.jsonl"
FAM_SCRATCH = OUT_DIR / "scratch_model_null_families.jsonl"

N_DRAWS = NB.MIN_DRAWS          # 64 -- the DEV gate, and tonight's budget
SEED0 = 20260904                # draw i uses SEED0 + i; disjoint from v1's fixed seed
TEST_YEARS = tuple(range(2016, 2025))
HORIZON = 1
BOOK_K = 50

#: the v1 arms whose observed statistics get a percentile (ML arms only --
#: the baselines were never claimed as skill and `prior` saw the test years)
V1_ARMS = ("ridge__raw", "ridge__residual", "lgbm__raw", "lgbm__residual",
           "mlp__raw", "mlp__residual", "lgbm_clf")


# ------------------------------------------------------------- checkpointing

def _done_seeds(scratch: Path) -> dict[int, dict]:
    """Draws already on disk. A malformed trailing line (crash mid-write) is
    dropped, not fatal -- that draw simply reruns."""
    out: dict[int, dict] = {}
    if not scratch.exists():
        return out
    for line in scratch.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            out[int(row["seed"])] = row
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    return out


def _append(scratch: Path, row: dict) -> None:
    with scratch.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


# ------------------------------------------------------------------ v1 draws

def _v1_one_draw(df: pd.DataFrame, feature_cols: list[str], seed: int) -> dict:
    """v1's null-arm pipeline, one permutation seed. Returns the four numbers
    the scoreboard quotes for every arm."""
    pred = pd.Series(np.nan, index=df.index, dtype="float64")
    for _year, tr, te in D.walk_forward_splits(df, TEST_YEARS, HORIZON):
        p, _meta = M.fit_predict("lgbm", "raw", df.loc[tr], df.loc[te],
                                 feature_cols, HORIZON,
                                 shuffle_target=True, shuffle_seed=seed)
        pred.loc[te] = p
    y = f"excess_vw_{HORIZON}m"
    sub = df.assign(_p=pred)
    sub = sub[sub["_p"].notna() & sub[y].notna()]
    ic = E.rank_ic(sub, "_p", y)
    bk = E.book(sub, "_p", k=BOOK_K, weight="vw")
    return {"seed": seed,
            "mean_ic": ic.get("mean_ic"), "ic_t": ic.get("t_stat"),
            "pair_t": bk.get("t_stat_paired_vs_market"),
            "tw": bk.get("terminal_wealth_net"),
            "exc": bk.get("annualised_excess")}


def run_v1(n_draws: int = N_DRAWS, max_draws_this_call: int | None = None) -> int:
    df = D.load()
    feature_cols = D.feature_columns()
    done = _done_seeds(V1_SCRATCH)
    todo = [SEED0 + i for i in range(n_draws) if SEED0 + i not in done]
    if max_draws_this_call is not None:
        todo = todo[:max_draws_this_call]
    print(f"[v1] {len(done)} draws on disk, {len(todo)} to run "
          f"({len(df):,} rows, {len(feature_cols)} features)", flush=True)
    for seed in todo:
        t0 = time.time()
        row = _v1_one_draw(df, feature_cols, seed)
        _append(V1_SCRATCH, row)
        done[seed] = row
        print(f"[v1] draw seed {seed}: ic_t {row['ic_t']:+.2f}  "
              f"pair_t {row['pair_t']:+.2f}  tw {row['tw']:.3f}  "
              f"({time.time() - t0:.0f}s, {len(done)}/{n_draws})", flush=True)
    if len(done) >= n_draws:
        _finalise_v1({s: done[s] for s in sorted(done)[:n_draws]})
    return 0


def _finalise_v1(done: dict[int, dict]) -> None:
    sealed = json.loads(V1_RECEIPT.read_text(encoding="utf-8"))
    sb = sealed["scoreboard_1m"]
    rows = list(done.values())
    ic_t = np.asarray([r["ic_t"] for r in rows], dtype="float64")
    pair_t = np.asarray([r["pair_t"] for r in rows], dtype="float64")
    tw = np.asarray([r["tw"] for r in rows], dtype="float64")

    arms = {}
    obs_pair_t: dict[str, float] = {}
    for a in V1_ARMS:
        row = sb.get(a) or {}
        o_ic = (row.get("rank_ic") or {}).get("t_stat")
        bk = row.get("book_top50_vw") or {}
        o_pt, o_tw = bk.get("t_stat_paired_vs_market"), bk.get("terminal_wealth_net")
        arms[a] = {
            "observed_ic_t": o_ic, "observed_paired_t": o_pt,
            "observed_terminal_wealth_net": o_tw,
            "p_vs_model_null_ic_t": (None if o_ic is None
                                     else round(NB.p_one_sided(o_ic, ic_t), 4)),
            "p_vs_model_null_paired_t": (None if o_pt is None
                                         else round(NB.p_one_sided(o_pt, pair_t), 4)),
            "p_vs_model_null_terminal_wealth": (None if o_tw is None
                                                else round(NB.p_one_sided(o_tw, tw), 4)),
            "verdict_ic_t": (NB.verdict(o_ic, ic_t) if o_ic is not None else None),
            "verdict_paired_t": (NB.verdict(o_pt, pair_t) if o_pt is not None else None),
        }
        if o_pt is not None:
            obs_pair_t[a] = o_pt

    fam = NB.family_max_p(obs_pair_t,
                          [{a: r["pair_t"] for a in obs_pair_t} for r in rows])

    receipt = {
        "artefact": "LEARNER_v1 MODEL NULL x64",
        "licence": "PRODUCT_EXPERIMENT",
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "corrects": str(V1_RECEIPT.name) + " (its one-draw null, stamped LEGACY 2026-09-03)",
        "construction": ("lgbm raw refitted on targets permuted WITHIN each month, "
                         "walk-forward 2016-2024 at 1m, one permutation seed per draw "
                         f"(seeds {SEED0}..{SEED0 + len(rows) - 1}); graded by "
                         "evaluate.rank_ic + evaluate.book(top-50 VW, 10bps/side) "
                         "exactly as the sealed scoreboard was"),
        "caveat": ("the null pipeline is lgbm RAW; ridge/mlp/residual/clf arms are "
                   "read against it as the closest available model null, not their "
                   "own -- fitting seven nulls was not bought tonight. lgbm__raw "
                   "and lgbm_clf are the load-bearing comparisons."),
        "model_null_64_20260904": {
            "null_bar": NB.MODEL_NULL_BAR,
            "n_draws": len(rows),
            "null_ic_t": {**NB.summarise_null(ic_t),
                          "share_abs_gt_2": round(float((np.abs(ic_t) > 2).mean()), 3)},
            "null_paired_t": {**NB.summarise_null(pair_t),
                              "share_abs_gt_2": round(float((np.abs(pair_t) > 2).mean()), 3)},
            "null_terminal_wealth": NB.summarise_null(tw),
            "arms": arms,
            "family_correction_paired_t": fam,
        },
        "draws": rows,
    }
    V1_OUT.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")
    print(f"[v1] RECEIPT -> {V1_OUT.name}", flush=True)
    blk = receipt["model_null_64_20260904"]
    print(f"[v1] null ic_t sd {blk['null_ic_t']['sd']}  "
          f"|t|>2 in {blk['null_ic_t']['share_abs_gt_2']:.0%}  "
          f"family p {fam.get('p_one_sided_family')}", flush=True)


# ------------------------------------------------------------ families draws

def _fam_setup():
    import scripts.feature_families_run as FF
    from learner import features_ext as F
    df = D.load()
    holder, analyst, _diag = F.load_or_build(rebuild=False, verbose=False)
    df, _ = F.attach(df, holder, analyst)
    cols = D.feature_columns() + F.columns_for(("analyst", "holder", "interaction"))
    return FF, df, cols


def _fam_one_draw(FF, df: pd.DataFrame, cols: list[str], seed: int) -> dict:
    pred, _ = FF.walk_forward_preds(df, cols, "lgbm", HORIZON, shuffle=True,
                                    verbose=False, shuffle_seed=seed)
    y = f"excess_vw_{HORIZON}m"
    scored = df.assign(_pred=pred)
    scored = scored[scored["_pred"].notna() & scored[y].notna()]
    ic = FF.monthly_ic(scored, "_pred", y)
    t = FF._t_of(ic)
    bk = FF.book_for_horizon(scored, "_pred", HORIZON)
    return {"seed": seed, "months": int(len(ic)),
            "mean_ic": round(float(ic.mean()), 5) if len(ic) else None,
            "ic_t": round(t, 3) if t is not None else None,
            "pair_t": bk.get("t_stat_paired_vs_market"),
            "tw": bk.get("terminal_wealth_net")}


def run_families(n_draws: int = N_DRAWS, max_draws_this_call: int | None = None) -> int:
    FF, df, cols = _fam_setup()
    done = _done_seeds(FAM_SCRATCH)
    todo = [SEED0 + i for i in range(n_draws) if SEED0 + i not in done]
    if max_draws_this_call is not None:
        todo = todo[:max_draws_this_call]
    print(f"[families] {len(done)} draws on disk, {len(todo)} to run "
          f"({len(df):,} rows, {len(cols)} features)", flush=True)
    for seed in todo:
        t0 = time.time()
        row = _fam_one_draw(FF, df, cols, seed)
        _append(FAM_SCRATCH, row)
        done[seed] = row
        print(f"[families] draw seed {seed}: ic_t {row['ic_t']:+.2f}  "
              f"pair_t {row['pair_t']:+.2f}  tw {row['tw']:.3f}  "
              f"({time.time() - t0:.0f}s, {len(done)}/{n_draws})", flush=True)
    if len(done) >= n_draws:
        _finalise_families({s: done[s] for s in sorted(done)[:n_draws]})
    return 0


def _finalise_families(done: dict[int, dict]) -> None:
    sealed = json.loads(FAM_RECEIPT.read_text(encoding="utf-8"))
    rows = list(done.values())
    ic_t = np.asarray([r["ic_t"] for r in rows], dtype="float64")
    pair_t = np.asarray([r["pair_t"] for r in rows if r["pair_t"] is not None],
                        dtype="float64")
    tw = np.asarray([r["tw"] for r in rows if r["tw"] is not None], dtype="float64")

    # observed: the full-feature lgbm cell (same cols as null_check) at 1m
    full = (sealed.get("horizons", {}).get("1m", {}).get("sets", {})
            .get("base+analyst+holder+interaction", {}).get("models", {})
            .get("lgbm", {}))
    o_ic = (full.get("rank_ic") or {}).get("t_stat")
    o_bk = full.get("book") or {}
    o_pt, o_tw = o_bk.get("t_stat_paired_vs_market"), o_bk.get("terminal_wealth_net")
    one_draw = sealed.get("null_shuffled_within_month_1m") or {}

    receipt = {
        "artefact": "FEATURE-FAMILIES MODEL NULL x64",
        "licence": "PRODUCT_EXPERIMENT",
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "corrects": str(FAM_RECEIPT.name) + " (its one-draw null_check, stamped LEGACY "
                    "2026-09-03; that draw's t was "
                    + str(one_draw.get("t_stat")) + ")",
        "construction": ("null_check's exact pipeline -- lgbm raw on base+analyst+"
                         "holder+interaction, walk-forward 2016-2024 at 1m, target "
                         "permuted WITHIN each month -- one permutation seed per draw "
                         f"(seeds {SEED0}..{SEED0 + len(rows) - 1})"),
        "note": ("the study's VERDICTS rest on paired deltas between feature sets, "
                 "not on this arm's level; this block prices the level claim anyway "
                 "so the receipt stops leaning on one draw"),
        "model_null_64_20260904": {
            "null_bar": NB.MODEL_NULL_BAR,
            "n_draws": len(rows),
            "null_ic_t": {**NB.summarise_null(ic_t),
                          "share_abs_gt_2": round(float((np.abs(ic_t) > 2).mean()), 3)},
            "null_paired_t": {**NB.summarise_null(pair_t),
                              "share_abs_gt_2": round(float((np.abs(pair_t) > 2).mean()), 3)},
            "null_terminal_wealth": NB.summarise_null(tw),
            "observed_full_feature_lgbm": {
                "ic_t": o_ic, "paired_t": o_pt, "terminal_wealth_net": o_tw,
                "p_vs_model_null_ic_t": (None if o_ic is None
                                         else round(NB.p_one_sided(o_ic, ic_t), 4)),
                "p_vs_model_null_paired_t": (None if o_pt is None
                                             else round(NB.p_one_sided(o_pt, pair_t), 4)),
                "p_vs_model_null_terminal_wealth": (
                    None if o_tw is None else round(NB.p_one_sided(o_tw, tw), 4)),
                "verdict_ic_t": (NB.verdict(o_ic, ic_t) if o_ic is not None else None),
            },
        },
        "draws": rows,
    }
    FAM_OUT.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")
    print(f"[families] RECEIPT -> {FAM_OUT.name}", flush=True)
    blk = receipt["model_null_64_20260904"]
    print(f"[families] null ic_t sd {blk['null_ic_t']['sd']}  "
          f"|t|>2 in {blk['null_ic_t']['share_abs_gt_2']:.0%}", flush=True)


# ------------------------------------------------------------------- driver

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--study", choices=("v1", "families", "all"), required=True)
    ap.add_argument("--draws", type=int, default=N_DRAWS,
                    help="total draws per study (the receipt refuses < 64 anyway "
                         "via nullbar at finalisation)")
    ap.add_argument("--max-this-call", type=int, default=None,
                    help="stop after N new draws this invocation (checkpoint stands)")
    a = ap.parse_args(argv)
    if a.study == "v1":
        return run_v1(a.draws, a.max_this_call)
    if a.study == "families":
        return run_families(a.draws, a.max_this_call)
    # the overnight driver: SEQUENTIAL, never parallel -- the draws contend
    # for the same cores. One families draw runs first so both studies have
    # first-draw evidence tonight (its checkpoint makes it not wasted).
    print(f"=== driver start {datetime.now(timezone.utc).isoformat(timespec='seconds')} "
          f"UTC ===", flush=True)
    run_families(a.draws, max_draws_this_call=1)
    run_v1(a.draws, None)
    run_families(a.draws, None)
    print("=== driver done ===", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
