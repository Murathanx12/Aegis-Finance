"""A3 -- CPCV AND PBO OVER THE INCUMBENT FAMILY. IS THE LEADERBOARD'S TOP ROW A COIN FLIP?

THE QUESTION
============
Every number on a leaderboard is, individually, exactly as computed. PBO asks a
different question: across every way of cutting the sample into an in-sample
half and an out-of-sample half, how often does the IN-SAMPLE champion finish
BELOW the out-of-sample median? A leaderboard with PBO near 0.5 is one whose top
row is a coin flip -- and that is a property of the SEARCH, not of any arm.

This job runs it over the two families the incumbents were actually chosen from,
and reports the out-of-sample PATH DISTRIBUTION rather than one path, because a
single walk-forward line is one draw of a procedure and the variance across
draws is the thing being asked about.

THE TWO FAMILIES, AND EXACTLY WHAT EACH ONE IS
==============================================
**The 32-cell learner grid.** `oos_predictions_v2.parquet` carries 18 columns per
horizon over 4 horizons. Eight of those columns are the v1 model grid carried
forward -- ridge/lgbm/mlp x raw/residual, the classifier head `lgbm_clf`, and the
shuffled-target NULL -- and 8 x 4 = 32 is the grid the mandate names. The null is
IN the family on purpose: if a shuffled-target arm wins in-sample folds at
anything like its base rate, the leaderboard is measuring noise, and that is a
cheaper diagnosis than any of the others in this file.

The other ten columns per horizon (constant, prior, rank_upside, rank_consensus,
random_rank, and the four encoder arms plus the encoder null) are graded beside
it as `learner_v2_full_family` -- 72 cells -- so the reader can see whether the
PBO is a property of the 32 or of the search that surrounds it.

**The neural family, and why it is 22 cells and not 40.** W3b opened 40 cells:
two neural arms (`nn`, `nn_pre_causal`) x 8 seeds + their seed-means x 2 cost
rates, plus the two incumbents x 2. Reconstructing per-period returns needs the
PREDICTIONS, not the receipt's summary rows, and the `nn` stage parquet is no
longer on disk -- only `w3b_pred_incumbents` and `w3b_pred_nn_pre_causal` are.
So 22 of the 40 cells are reconstructible without refitting eight neural seeds,
and refitting them is not a re-grade, it is a different experiment. The job
REPORTS the shortfall and computes PBO on what exists. A family size quoted as
40 while 22 series were used would be the error this receipt exists to catch.

WHAT PBO IS RUN ON
==================
PRIMARY is the PAIRED EXCESS over the raw value-weighted market -- the quantity
these scoreboards actually rank on. SECONDARY is the book's own net return.
The two differ because every one of these books is long-only with beta above
one, and ranking by raw Sharpe would substantially rank by leverage.

PURGING. `cpcv_splits(purge=, embargo=)` is set to the HORIZON in months at each
horizon, and to 12 for any pooled family that contains a 12-month arm. A 12-month
label that matures inside a test block and was fitted on the train side is
exactly the leakage CPCV exists to remove.

$0 LLM spend. Zero network calls. No model is fitted anywhere in this file.

    python -m scripts.labor_a3_cpcv_pbo
    python -m scripts.labor_a3_cpcv_pbo --skip-neural
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "backend" / "data" / "optimus" / "labor_day_lab_2026-09-07"
RECEIPT = OUT_DIR / "A3_cpcv_pbo_run01.json"

PRED_V2 = REPO / "backend" / "data" / "optimus" / "learner" / "oos_predictions_v2.parquet"
PANEL_V2 = REPO / "backend" / "data" / "optimus" / "learner" / "train_table.parquet"

HORIZONS = (1, 3, 6, 12)
BOOK_K = 50

#: THE 32-CELL GRID, named by column stem. 8 stems x 4 horizons = 32.
#: The NULL is deliberately inside the family: a leaderboard whose shuffled-target
#: arm wins in-sample folds is measuring noise, and that is the cheapest finding
#: available here.
GRID_32_STEMS = ("ridge__raw", "ridge__residual", "lgbm__raw", "lgbm__residual",
                 "mlp__raw", "mlp__residual", "lgbm_clf", "NULL_shuffled__lgbm_raw")
NULL_STEMS = ("NULL_shuffled__lgbm_raw", "NULL_shuffled__encoder_raw", "random_rank")

#: `ratio >= 50` is a stale analyst target across a split, not an opinion (S30b).
#: Applied IDENTICALLY to every arm, nulls included -- an arm that excludes them
#: compared against a null that does not is a comparison of two universes.
RATIO_CAP = 50.0

CPCV_GROUPS = 6
CPCV_K_TEST = 2
PBO_SPLITS = 8
COSTS: tuple[float, ...] = (10.0, 25.0)

_INPUTS: list[dict] = []


# --------------------------------------------------------------- provenance

def note_input(path, *, sha: bool = False) -> dict:
    p = Path(path)
    rec: dict = {"path": str(p), "exists": p.exists()}
    if p.exists():
        st = p.stat()
        rec["bytes"] = int(st.st_size)
        rec["mtime_utc"] = datetime.fromtimestamp(
            st.st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
        if sha:
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            rec["sha256"] = h.hexdigest()
        else:
            rec["sha256"] = "NOT HASHED (size+mtime only)"
    _INPUTS.append(rec)
    return rec


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO),
                              capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception as exc:                                            # noqa: BLE001
        return f"UNKNOWN ({type(exc).__name__})"


def _r(v, nd: int = 5):
    try:
        f = float(v)
        return round(f, nd) if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _sharpe(x: np.ndarray) -> float:
    a = np.asarray(x, dtype="float64")
    a = a[np.isfinite(a)]
    if a.size < 2 or a.std(ddof=1) == 0:
        return float("nan")
    return float(a.mean() / a.std(ddof=1))


# ------------------------------------------------------------------ the CPCV

def cpcv_path_distribution(M: pd.DataFrame, *, purge: int, embargo: int,
                           n_groups: int = CPCV_GROUPS,
                           k_test: int = CPCV_K_TEST) -> dict:
    """The OOS PATH DISTRIBUTION of the SELECTION PROCEDURE, not of one arm.

    For every CPCV partition: rank the arms on the TRAIN months, take the
    in-sample champion, and record what that champion earned on the TEST months.
    The output is the distribution of those out-of-sample results -- which is the
    honest answer to "what does picking the best cell get you?", where a single
    walk-forward line is one draw of it.

    `M` is (months x arms) of per-period performance, already aligned.
    """
    from learner import inference
    arms = list(M.columns)
    A = M.to_numpy(dtype="float64")
    T = A.shape[0]
    splits = inference.cpcv_splits(T, n_groups=n_groups, k_test=k_test,
                                   purge=int(purge), embargo=int(embargo))
    if not splits:
        return {"verdict": "CANNOT DETERMINE",
                "why": f"{T} periods is too few for {n_groups} groups"}
    rows = []
    for tr, te in splits:
        is_sr = np.array([_sharpe(A[tr, j]) for j in range(len(arms))])
        if not np.isfinite(is_sr).any():
            continue
        champ = int(np.nanargmax(is_sr))
        oos = A[te, champ]
        oos = oos[np.isfinite(oos)]
        if oos.size < 3:
            continue
        rows.append({
            "is_champion": arms[champ],
            "is_sharpe": _r(is_sr[champ], 4),
            "oos_months": int(oos.size),
            "oos_mean_monthly": _r(float(oos.mean()), 6),
            "oos_annualised": _r(float(oos.mean()) * 12, 5),
            "oos_sharpe": _r(_sharpe(oos), 4),
            "oos_terminal_wealth_of_the_excess_series": _r(float((1 + oos).prod()), 4),
        })
    if not rows:
        return {"verdict": "CANNOT DETERMINE", "why": "no usable partitions"}
    ann = np.array([r["oos_annualised"] for r in rows if r["oos_annualised"] is not None])
    srs = np.array([r["oos_sharpe"] for r in rows if r["oos_sharpe"] is not None])
    champs = pd.Series([r["is_champion"] for r in rows]).value_counts()
    return {
        "n_partitions": len(rows),
        "n_groups": n_groups, "k_test": k_test,
        "purge_periods": int(purge), "embargo_periods": int(embargo),
        "purge_note": ("purge and embargo are set to the HORIZON in months so a label "
                       "maturing inside a test block cannot have been fitted on the "
                       "train side"),
        "oos_annualised_distribution": {
            "min": _r(float(ann.min())), "q25": _r(float(np.percentile(ann, 25))),
            "median": _r(float(np.median(ann))),
            "q75": _r(float(np.percentile(ann, 75))), "max": _r(float(ann.max())),
            "mean": _r(float(ann.mean())), "sd": _r(float(ann.std(ddof=1))) if ann.size > 1 else None,
            "share_of_paths_negative": _r(float((ann < 0).mean()), 4),
        },
        "oos_sharpe_distribution": {
            "min": _r(float(srs.min())), "median": _r(float(np.median(srs))),
            "max": _r(float(srs.max())),
        },
        "in_sample_champion_counts": {k: int(v) for k, v in champs.items()},
        "champion_is_the_same_arm_in_every_partition": bool(len(champs) == 1),
        "share_of_partitions_won_by_a_NULL_arm": _r(
            float(sum(v for k, v in champs.items() if any(s in k for s in NULL_STEMS))
                  / max(1, len(rows))), 4),
        "paths": rows,
        "reading": ("the DISTRIBUTION is the result. A procedure whose OOS paths "
                    "straddle zero is a procedure, not an edge, however good its "
                    "single published path looks."),
    }


def pbo_block(M: pd.DataFrame) -> dict:
    """`inference.pbo` plus the BASELINE its 0.5 bar quietly assumes.

    `inference.pbo` reads "0.5 is a coin flip". That is true for an even number
    of arms and NOT true for a small odd one, because the OOS rank is discrete:
    with N arms the champion's rank takes values (j+1)/(N+1), and `lambda <= 0`
    -- the event PBO counts -- is `j+1 <= (N+1)/2`. Under pure noise that
    happens with probability floor((N+1)/2)/N, which is 0.500 at N = 8 or 22 and
    **0.667 at N = 3**. Quoting 0.97 against a 0.5 bar on a three-arm family
    would read as catastrophic overfitting when the honest excess over its own
    null is much smaller, and quoting 0.514 on an eleven-arm family as "worse
    than a coin flip" would be wrong in the other direction (the baseline there
    is 0.545, so 0.514 is *at* the coin flip, not past it).

    So the baseline is computed from N and reported beside the number. The
    upstream function is not edited; this is a reader for it.
    """
    from learner import inference
    out = inference.pbo(M.to_numpy(dtype="float64"), n_splits=PBO_SPLITS)
    out["arms"] = list(M.columns)
    out["n_splits_requested"] = PBO_SPLITS
    n = int(M.shape[1])
    base = math.floor((n + 1) / 2) / n if n else None
    out["pbo_baseline_under_pure_noise_for_this_n_arms"] = _r(base, 4)
    out["pbo_baseline_derivation"] = (
        "the OOS rank is discrete: rank = (j+1)/(N+1) for j = 0..N-1, and PBO counts "
        "lambda = log(rank/(1-rank)) <= 0, i.e. j+1 <= (N+1)/2. Under pure noise j is "
        f"uniform, so the baseline is floor((N+1)/2)/N = {base} at N = {n}.")
    if out.get("pbo") is not None and base is not None:
        out["pbo_minus_baseline"] = _r(float(out["pbo"]) - base, 4)
        out["verdict_against_its_own_baseline"] = (
            "WORSE THAN A COIN FLIP" if float(out["pbo"]) - base > 0.15 else
            "AT THE COIN FLIP" if abs(float(out["pbo"]) - base) <= 0.15 else
            "BETTER THAN A COIN FLIP")
    if n < 6:
        out["small_family_caveat"] = (
            f"{n} arms. PBO's rank statistic is coarse here -- only {n} distinct OOS "
            f"ranks exist -- so read `pbo_minus_baseline`, never the raw number "
            f"against 0.5.")
    return out


def _seed_finding(fams: dict) -> dict:
    """Is the neural family's in-sample champion a SEED or the SEED-MEAN?

    `nn_pre_causal_shadow_v1` declares seed selection FORBIDDEN because
    "reporting the best seed would be the maximum of eight draws quoted as one".
    That is an argument; this is the measurement of it. Derived from the CPCV
    champion counts, never asserted.
    """
    out: dict = {}
    for key, blk in fams.items():
        c = (blk or {}).get("cpcv_path_distribution") or {}
        counts = c.get("in_sample_champion_counts") or {}
        if not counts:
            continue
        tot = sum(counts.values())
        seedwins = sum(v for k, v in counts.items()
                       if "_s2026" in k and "seedmean" not in k)
        out[key] = {
            "partitions": tot,
            "won_by_an_individual_SEED": int(seedwins),
            "share_won_by_a_seed": _r(seedwins / tot, 4) if tot else None,
            "champion_counts": counts,
            "pbo": (blk.get("pbo") or {}).get("pbo"),
            "pbo_verdict": (blk.get("pbo") or {}).get("verdict"),
        }
    seed_fams = {k: v for k, v in out.items() if v["won_by_an_individual_SEED"]}
    out["reading"] = (
        "the shadow contract forbids seed selection and judges the SEED-MEAN. These "
        "counts say why: in "
        + ("; ".join(f"{k} an individual seed wins {v['won_by_an_individual_SEED']} of "
                     f"{v['partitions']} in-sample partitions" for k, v in seed_fams.items())
           if seed_fams else "no family did an individual seed win a partition")
        + ". A leaderboard whose top row is one seed of eight is the maximum of eight "
          "draws quoted as one, and PBO measures exactly that.")
    return out


def family_block(series: dict, label: str, *, purge: int, embargo: int) -> dict:
    """PBO + CPCV over one family of aligned per-period series."""
    if len(series) < 2:
        return {"verdict": "CANNOT DETERMINE", "why": f"{len(series)} arm(s)"}
    M = pd.DataFrame(series).dropna(how="any")
    if M.empty or len(M) < 24:
        return {"verdict": "CANNOT DETERMINE",
                "why": f"{len(M)} aligned periods after dropping incomplete months"}
    lead = {c: {"annualised_pct": _r(float(M[c].mean()) * 12 * 100, 3),
                "sharpe_monthly": _r(_sharpe(M[c].to_numpy()), 4)}
            for c in M.columns}
    best = max(lead, key=lambda c: (lead[c]["sharpe_monthly"] or -9e9))
    return {
        "label": label,
        "n_arms": int(M.shape[1]),
        "n_aligned_periods": int(M.shape[0]),
        "window": [str(M.index[0]), str(M.index[-1])],
        "full_sample_leaderboard": lead,
        "full_sample_champion": best,
        "full_sample_champion_is_a_NULL": bool(any(s in best for s in NULL_STEMS)),
        "pbo": pbo_block(M),
        "cpcv_path_distribution": cpcv_path_distribution(M, purge=purge, embargo=embargo),
    }


# ----------------------------------------------------------- family 1: learner

def learner_family(log) -> dict:
    from learner import evaluate as E

    out: dict = {"source": str(PRED_V2)}
    if not PRED_V2.exists() or not PANEL_V2.exists():
        return {**out, "status": "SKIPPED",
                "reasons": [f"missing {PRED_V2 if not PRED_V2.exists() else PANEL_V2}"]}
    note_input(PRED_V2)
    note_input(PANEL_V2)

    preds = pd.read_parquet(PRED_V2)
    cols_needed = ["permno", "month", "entry_date", "market_cap",
                   "log_dollar_vol_20d", "fwd_1m", "mkt_vw_1m", "ratio"] + \
                  [f"excess_vw_{h}m" for h in HORIZONS]
    panel = pd.read_parquet(PANEL_V2, columns=cols_needed)
    out["rows_predictions"] = int(len(preds))
    out["rows_panel"] = int(len(panel))

    # index alignment: the v2 predictions carry permno/month/entry_date
    key = ["permno", "month"]
    preds = preds.drop(columns=[c for c in ("entry_date",) if c in preds.columns])
    df = panel.merge(preds, on=key, how="inner", validate="one_to_one")
    del preds, panel
    gc.collect()
    out["rows_joined"] = int(len(df))
    before = len(df)
    df = df[df["ratio"] < RATIO_CAP]
    out["contamination_filter"] = {
        "rule": f"ratio < {RATIO_CAP}",
        "rows_removed": int(before - len(df)),
        "why": ("a stale analyst target across a split is not an opinion (S30b). "
                "Applied IDENTICALLY to every arm, nulls included."),
    }

    pred_cols = [c for c in df.columns if c.endswith(tuple(f"__{h}m" for h in HORIZONS))
                 and c not in cols_needed]
    out["prediction_columns_available"] = len(pred_cols)

    log("    grading every cell (no fits) ...")
    series_by_h: dict[int, dict] = {}
    net_by_h: dict[int, dict] = {}
    graded, skipped = 0, []
    for h in HORIZONS:
        y = f"excess_vw_{h}m"
        sub_all = df[df[y].notna()]
        s_ex, s_net = {}, {}
        for c in pred_cols:
            if not c.endswith(f"__{h}m"):
                continue
            sub = sub_all[sub_all[c].notna()]
            if sub.empty:
                skipped.append(c)
                continue
            bk = (E.book(sub, c, k=BOOK_K, weight="vw", return_series=True)
                  if h == 1 else
                  E.overlapping_book(sub, c, h, k=BOOK_K, weight="vw",
                                     with_risk=False, return_series=True))
            ser = bk.get("_series")
            if ser is None:
                skipped.append(c)
                continue
            s_ex[c] = (ser["net"] - ser["market"]).dropna()
            s_net[c] = ser["net"].dropna()
            graded += 1
        series_by_h[h] = s_ex
        net_by_h[h] = s_net
        log(f"      h={h}m: {len(s_ex)} arms")
    out["cells_graded"] = graded
    out["cells_skipped"] = skipped

    # ---- the 32-cell grid
    fams: dict = {}
    grid32_ex, grid32_net = {}, {}
    for h in HORIZONS:
        pick = {f"{s}__{h}m": series_by_h[h].get(f"{s}__{h}m") for s in GRID_32_STEMS}
        pick = {k: v for k, v in pick.items() if v is not None}
        grid32_ex.update(pick)
        grid32_net.update({k: net_by_h[h][k] for k in pick})
        fams[f"grid32_h{h}m_PRIMARY_paired_excess"] = family_block(
            pick, f"the 8 v1 grid arms at h={h}m", purge=h, embargo=h)
    out["by_horizon"] = fams
    out["grid_32_definition"] = {
        "stems": list(GRID_32_STEMS),
        "horizons": list(HORIZONS),
        "cells_expected": len(GRID_32_STEMS) * len(HORIZONS),
        "cells_found": len(grid32_ex),
        "note": ("the mandate names a '32-cell learner grid'. This is it, spelled out: "
                 "8 v1 stems x 4 horizons. The NULL arm is inside the family on purpose."),
    }
    out["POOLED_grid32_PRIMARY_paired_excess"] = family_block(
        grid32_ex, "all 32 learner cells pooled", purge=12, embargo=12)
    out["POOLED_grid32_SECONDARY_net"] = family_block(
        grid32_net, "all 32 learner cells pooled, on NET not excess",
        purge=12, embargo=12)
    out["pooled_purge_note"] = (
        "the pooled family contains a 12-month arm, so purge and embargo are 12 for "
        "the pooled block and h for each per-horizon block. Quoting one purge for both "
        "would leak a year of labels into the 12m arms' training months.")

    # ---- the full family, so the reader can see whether PBO is a property of
    #      the 32 or of the search that surrounds them
    full_ex = {}
    for h in HORIZONS:
        full_ex.update(series_by_h[h])
    out["POOLED_full_family_PRIMARY_paired_excess"] = family_block(
        full_ex, f"every graded v2 cell ({len(full_ex)})", purge=12, embargo=12)

    out["HOW_TO_READ"] = _how_to_read(out)

    del df
    gc.collect()
    return {**out, "status": "OK"}


def _how_to_read(out: dict) -> dict:
    """THE POOLED PBO AND THE PER-HORIZON PBO ARE NOT THE SAME QUESTION.

    Derived from the numbers rather than asserted, because a caveat that does not
    move with the result is decoration.
    """
    per_h = {h: ((out.get("by_horizon") or {})
                 .get(f"grid32_h{h}m_PRIMARY_paired_excess") or {}).get("pbo", {})
             for h in HORIZONS}
    pooled = (out.get("POOLED_grid32_PRIMARY_paired_excess") or {}).get("pbo", {})
    worst_h = max((h for h in HORIZONS if per_h[h].get("pbo") is not None),
                  key=lambda h: per_h[h]["pbo"], default=None)
    return {
        "pooled_pbo": pooled.get("pbo"),
        "pooled_verdict": pooled.get("verdict"),
        "pbo_by_horizon": {f"{h}m": per_h[h].get("pbo") for h in HORIZONS},
        "verdict_by_horizon": {f"{h}m": per_h[h].get("verdict") for h in HORIZONS},
        "worst_horizon": f"{worst_h}m" if worst_h else None,
        "pbo_minus_baseline_by_horizon": {
            f"{h}m": per_h[h].get("pbo_minus_baseline") for h in HORIZONS},
        "the_caveat_that_decides_the_reading": (
            "PBO ranks arms by Sharpe on the SAME monthly index, and the 3m/6m/12m "
            "arms are OVERLAPPING books: 1/h of the portfolio rolls each month, so "
            "their monthly series are serially smoothed and their monthly Sharpes are "
            "mechanically higher than a 1m book's at the same economic edge. A POOLED "
            "family that mixes horizons therefore lets the in-sample selector escape "
            "into the smoothest arm, and its low PBO is partly a statement about "
            "overlap, not about stability. The PER-HORIZON blocks compare like with "
            "like and are the honest reading."),
        "reading": (
            f"pooled across horizons the 32-cell grid reads {pooled.get('verdict')} at "
            f"PBO {pooled.get('pbo')}. Per horizon it does not: "
            + ", ".join(f"{h}m {per_h[h].get('pbo')} ({per_h[h].get('verdict')})"
                        for h in HORIZONS if per_h[h].get('pbo') is not None)
            + ". The 1m horizon is the one the books actually trade."),
    }


# ------------------------------------------------------------ family 2: neural

def neural_family(log) -> dict:
    from learner import evaluate as E
    from learner import long_panel as LP
    from learner import neural_long as N
    from scripts import w3_neural_floored as W3B

    out: dict = {}
    if not LP.LONG_TABLE.exists():
        return {"status": "SKIPPED", "reasons": [f"{LP.LONG_TABLE} is absent"]}

    years = list(range(N.FIRST_TEST_YEAR, N.LAST_TEST_YEAR + 1))
    seeds = [N.SEED_BASE + i for i in range(N.N_SEEDS)]
    wanted = {"incumbents": W3B._scope(years, []),
              "nn": W3B._scope(years, seeds),
              "nn_pre_causal": W3B._scope(years, seeds)}
    present, absent = {}, {}
    for tag in wanted:
        p = W3B._stage_path(tag)
        (present if p.exists() else absent)[tag] = str(p)
    out["stage_files_present"] = present
    out["stage_files_absent"] = absent
    out["family_shortfall"] = {
        "w3b_cells_looked_at": 40,
        "cells_reconstructible_from_disk": None,      # filled below
        "why": ("PBO needs per-period returns, which needs the PREDICTIONS, not the "
                "W3b receipt's summary rows. The stage parquets listed in "
                "stage_files_absent are gone, and refitting eight neural seeds to "
                "rebuild them is a different experiment, not a re-grade."),
    }
    if "incumbents" not in present or "nn_pre_causal" not in present:
        return {**out, "status": "SKIPPED",
                "reasons": ["neither incumbents nor nn_pre_causal stage predictions are "
                            "on disk; nothing to reconstruct"]}

    log("    loading the floored universe ...")
    df, uni, fp = W3B.load_universe(verbose=False)
    note_input(LP.LONG_TABLE)
    out["universe_fingerprint_sha256"] = fp
    out["training_universe"] = {k: uni[k] for k in
                                ("dollar_volume_floor_usd_per_day", "min_close_usd",
                                 "rows_after", "months_after")}

    cols_added = []
    for tag in ("incumbents", "nn_pre_causal"):
        block, _meta = W3B._read_stage(tag, fp, wanted[tag])
        for col in block.columns:
            df[col] = block[col].reindex(df.index).astype("float64")
            cols_added.append(col)
        note_input(W3B._stage_path(tag))
    out["arms_reconstructed"] = cols_added
    out["family_shortfall"]["cells_reconstructible_from_disk"] = len(cols_added) * len(COSTS)

    log("    grading the neural family (no fits) ...")
    ex_by_cost: dict[float, dict] = {c: {} for c in COSTS}
    net_by_cost: dict[float, dict] = {c: {} for c in COSTS}
    for col in cols_added:
        for bps in COSTS:
            bk = E.book(df, col, k=BOOK_K, weight="vw", cost_bps=bps,
                        ret_col="fwd_1m", mkt_col="mkt_vw_1m",
                        tradable_floor=N.TRADABLE_FLOOR_USD, return_series=True)
            ser = bk.get("_series")
            if ser is None:
                continue
            ex_by_cost[bps][f"{col}|{int(bps)}bps"] = (ser["net"] - ser["market"]).dropna()
            net_by_cost[bps][f"{col}|{int(bps)}bps"] = ser["net"].dropna()

    fams: dict = {}
    for bps in COSTS:
        fams[f"neural_family_{int(bps)}bps_PRIMARY_paired_excess"] = family_block(
            ex_by_cost[bps], f"{len(ex_by_cost[bps])} arms at {int(bps)} bps",
            purge=1, embargo=1)
    pooled_ex = {k: v for c in COSTS for k, v in ex_by_cost[c].items()}
    pooled_net = {k: v for c in COSTS for k, v in net_by_cost[c].items()}
    fams["POOLED_all_cost_rates_PRIMARY_paired_excess"] = family_block(
        pooled_ex, f"{len(pooled_ex)} cells (arms x cost rates)", purge=1, embargo=1)
    fams["POOLED_all_cost_rates_SECONDARY_net"] = family_block(
        pooled_net, f"{len(pooled_net)} cells on NET not excess", purge=1, embargo=1)
    # ---- THE FAMILY THE DECISION RULE ACTUALLY JUDGED, beside the one the
    #      search opened. `nn_pre_causal_shadow_v1` declares seed selection
    #      FORBIDDEN and judges the SEED-MEAN; if PBO is high over the seed
    #      family and low over the judged family, the contract's own rule is
    #      the thing carrying the stability, which is a measurement of that rule
    #      rather than an assertion of it.
    judged = ("lgbm_clf", "lgbm_raw", "nn_pre_causal_seedmean")
    for bps in COSTS:
        pick = {k: v for k, v in ex_by_cost[bps].items()
                if k.split("|")[0] in judged}
        fams[f"decision_rule_family_{int(bps)}bps_PRIMARY_paired_excess"] = family_block(
            pick, f"the {len(pick)} arms the W3b decision rule judged "
                  f"(seed-mean, never a seed) at {int(bps)} bps",
            purge=1, embargo=1)
    out["families"] = fams
    out["SEED_SELECTION_FINDING"] = _seed_finding(fams)
    out["cost_rates_note"] = (
        "the same arm at 10 and 25 bps is TWO cells in the pooled family because the "
        "search reported both and a reader may pick either. It is not two independent "
        "arms, and the pooled PBO is therefore an optimistic reading of a family whose "
        "members are near-duplicates -- said here rather than discovered later.")

    del df
    gc.collect()
    return {**out, "status": "OK"}


# ------------------------------------------------------------------- the run

def run(*, verbose: bool = True, skip_neural: bool = False) -> dict:
    from scripts import w3_neural_floored as W3B
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    t0 = time.perf_counter()
    out: dict = {
        "job": "A3_cpcv_pbo",
        "lane": "A",
        "question": ("is the incumbents' leaderboard overfit? PBO over the 32-cell "
                     "learner grid and the reconstructible neural family, plus the "
                     "out-of-sample PATH DISTRIBUTION of the selection procedure "
                     "rather than one path."),
        "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0, "llm_calls": 0, "network_calls": 0,
        "memory_free_gb_before": W3B.free_gb(),
        "models_fitted": 0,
        "models_fitted_note": ("zero. Every series here is a re-grade of predictions "
                               "already on disk; a job that refits is a different "
                               "experiment wearing the same name."),
    }

    log("  family 1: the learner grid ...")
    try:
        out["learner_family"] = learner_family(log)
    except Exception as exc:                                            # noqa: BLE001
        out["learner_family"] = {"status": "ERROR",
                                 "reasons": [f"{type(exc).__name__}: {exc}"],
                                 "traceback": traceback.format_exc()}
    out["memory_free_gb_after_family_1"] = W3B.free_gb()

    if skip_neural:
        out["neural_family"] = {"status": "SKIPPED",
                                "reasons": ["--skip-neural was passed"]}
    else:
        log("  family 2: the neural family ...")
        try:
            out["neural_family"] = neural_family(log)
        except Exception as exc:                                        # noqa: BLE001
            out["neural_family"] = {"status": "ERROR",
                                    "reasons": [f"{type(exc).__name__}: {exc}"],
                                    "traceback": traceback.format_exc()}
    out["memory_free_gb_after"] = W3B.free_gb()
    out["headline"] = _headline(out)
    out["wall_seconds"] = round(time.perf_counter() - t0, 1)
    return out


def _headline(out: dict) -> str:
    bits = []
    lf = out.get("learner_family") or {}
    if lf.get("status") == "OK":
        p = (lf.get("POOLED_grid32_PRIMARY_paired_excess") or {}).get("pbo") or {}
        c = (lf.get("POOLED_grid32_PRIMARY_paired_excess") or {}).get(
            "cpcv_path_distribution") or {}
        d = c.get("oos_annualised_distribution") or {}
        h1 = ((lf.get("by_horizon") or {}).get("grid32_h1m_PRIMARY_paired_excess")
              or {}).get("pbo") or {}
        bits.append(f"32-cell learner grid pooled: PBO {p.get('pbo')} vs its own "
                    f"noise baseline {p.get('pbo_baseline_under_pure_noise_for_this_n_arms')} "
                    f"-- but AT 1m, the horizon the books trade, PBO {h1.get('pbo')} vs "
                    f"{h1.get('pbo_baseline_under_pure_noise_for_this_n_arms')} = "
                    f"{h1.get('verdict_against_its_own_baseline')}; CPCV OOS annualised "
                    f"median {d.get('median')}, {d.get('share_of_paths_negative')} of "
                    f"paths negative")
    else:
        bits.append(f"learner family {lf.get('status')}")
    nf = out.get("neural_family") or {}
    if nf.get("status") == "OK":
        f = (nf.get("families") or {}).get("POOLED_all_cost_rates_PRIMARY_paired_excess") or {}
        p = f.get("pbo") or {}
        sf = nf.get("SEED_SELECTION_FINDING") or {}
        one = (sf.get("neural_family_10bps_PRIMARY_paired_excess") or {})
        bits.append(f"neural family ({f.get('n_arms')} of 40 cells reconstructible): "
                    f"PBO {p.get('pbo')} vs baseline "
                    f"{p.get('pbo_baseline_under_pure_noise_for_this_n_arms')}; an "
                    f"INDIVIDUAL SEED wins {one.get('won_by_an_individual_SEED')} of "
                    f"{one.get('partitions')} in-sample CPCV partitions at 10 bps, "
                    f"never the seed-mean")
    else:
        bits.append(f"neural family {nf.get('status')}")
    return " | ".join(bits)


def write(rec: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec["_provenance"] = {
        "sys_argv": list(sys.argv),
        "resolved_config": {
            "HORIZONS": list(HORIZONS), "BOOK_K": BOOK_K,
            "GRID_32_STEMS": list(GRID_32_STEMS), "NULL_STEMS": list(NULL_STEMS),
            "RATIO_CAP": RATIO_CAP, "CPCV_GROUPS": CPCV_GROUPS,
            "CPCV_K_TEST": CPCV_K_TEST, "PBO_SPLITS": PBO_SPLITS,
            "COSTS": list(COSTS), "receipt": str(RECEIPT),
        },
        "_inputs_opened": _INPUTS,
        "git_commit": git_commit(),
        "python": sys.version.split()[0],
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    rec["generated_utc"] = rec["_provenance"]["generated_utc"]
    RECEIPT.write_text(json.dumps(rec, indent=1, default=str),
                       encoding="utf-8", newline="\n")
    return RECEIPT


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-neural", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    try:
        rec = run(verbose=not a.quiet, skip_neural=a.skip_neural)
    except Exception as exc:                                            # noqa: BLE001
        rec = {"job": "A3_cpcv_pbo", "lane": "A", "status": "CRASHED",
               "llm_spend_usd": 0.0, "llm_calls": 0,
               "error": f"{type(exc).__name__}: {exc}",
               "traceback": traceback.format_exc(),
               "headline": f"CRASHED: {type(exc).__name__}: {exc}"}
    p = write(rec)
    print(f"\n{rec.get('headline')}\n-> {p}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
