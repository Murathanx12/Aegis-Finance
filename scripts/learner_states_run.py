"""UNSUPERVISED STATES v1 -- discover the world, then grade what works in it.

    python -m scripts.learner_states_run                  # the full run
    python -m scripts.learner_states_run --autoencoder    # + the torch arm
    python -m scripts.learner_states_run --quick          # small: a smoke run

WHAT THIS PRODUCES
==================
    backend/data/optimus/tracker_backtest/unsupervised_states_20260903.json
        the receipt: state definitions, sizes, transitions, per-state
        conditional tables, the market regime table, and the shuffled null.
    backend/data/optimus/learner/states/company_states.parquet
        one row per (permno, month) that was assigned OUT OF SAMPLE: its state
        at every k on the ladder, its anomaly score, its first four embedding
        coordinates, and its three nearest historical analogues with distances.
    backend/data/optimus/learner/states/market_states.parquet
        one row per month: the market-level regime, assigned by a KMeans that
        saw only months strictly before it.

LICENCE: PRODUCT_EXPERIMENT. This places nothing, recommends nothing and has
no broker path. It is a measurement.

THE ORDER OF OPERATIONS IS THE EXPERIMENT
=========================================
1. fit the representation on the past, with NO target column reachable;
2. assign the present out of sample;
3. only then join matured returns and grade.

Step 3 may look at the future. Steps 1 and 2 may not, and
`learner.states.assert_no_target_columns` refuses rather than trusting this
paragraph.

WHAT WOULD MAKE THIS A NEGATIVE RESULT
======================================
The states are a partition, and any partition of a fat-tailed cross-section
produces per-state means that differ. The null is a WITHIN-MONTH shuffle of the
state labels: same months, same per-month state sizes, same returns, random
membership. If the observed max-minus-min spread of per-state mean monthly
excess sits inside that null's bulk, the states have found nothing and the
document says so.
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

from sklearn.metrics import silhouette_score                           # noqa: E402

from learner import dataset as D                                       # noqa: E402
from learner import nullbar as NB                                      # noqa: E402
from learner import prior as P                                         # noqa: E402
from learner import states as S                                        # noqa: E402

RECEIPT = (REPO / "backend" / "data" / "optimus" / "tracker_backtest"
           / "unsupervised_states_20260903.json")
OOS_PREDICTIONS = REPO / "backend" / "data" / "optimus" / "learner" / "oos_predictions_1m.parquet"
LEARNER_V2 = (REPO / "backend" / "data" / "optimus" / "tracker_backtest"
              / "learner_v2_20260903.json")

#: Columns pulled from the train table. The FEATURE half and the TARGET half
#: are named separately and never handed to the same function.
ID_COLS = ["permno", "month", "entry_date", "band", "in_admissible", "sector",
           "ratio", "close", "coverage"]
TARGET_COLS = ["excess_vw_1m", "excess_vw_3m", "excess_ew_1m",
               "fwd_1m", "fwd_3m", "prior_1m", "prior_3m", "mat_date_1m"]

#: CRSP SIC 9999 = NONCLASSIFIABLE, and PRE-FIX panels label it
#: "Public Administration" -- 99,334 of 441,278 rows (22.51%). That was
#: MISSINGNESS wearing an industry's name. The source was fixed on 2026-09-03
#: (`tracker_ibes_backtest.SIC_DIVISIONS` now sends 9900-9999 to
#: "Unclassified" and keeps "Public Administration" for the genuine 9000-9899
#: codes), but a built parquet is immutable, so BOTH vintages remain readable
#: here: on a panel that carries the post-fix label, "Public Administration"
#: is genuine and must NOT be relabelled; on an older panel it still means
#: 98.8% code 9999 and is. The vintage is derived from the labels present,
#: never assumed from a date.
#:
#: None of this touches the representation -- `sector` is not in
#: `S.STATE_FEATURES` and not in `S.MARKET_FEATURES`, so no state can be
#: "the Public Administration state". Relabelling happens only where a state's
#: composition is REPORTED, so a reader cannot mistake the bucket for an
#: industry when interpreting what a state contains.
MISLABELLED_SECTOR = "Public Administration"
UNKNOWN_SECTOR_LABEL = "UNKNOWN_sic_9999 (panel mislabels this 'Public Administration')"
#: The honest source label, post-fix. String pinned against the source by
#: `backend/tests/test_sic_divisions.py`.
SOURCE_UNCLASSIFIED_LABEL = "Unclassified"

#: The model predictions graded per state. `NULL_shuffled_target__lgbm_raw` is
#: v1's own null arm and is graded here for the same reason it was graded
#: there: a state table in which the null looks skilful is a broken table.
PRED_COLS = ["prior", "lgbm_clf", "lgbm__raw", "lgbm__residual", "ridge__raw",
             "mlp__raw", "rank_upside", "NULL_shuffled_target__lgbm_raw"]


#: The receipt as it stood BEFORE this invocation sealed its header. Populated
#: in `main`; the only legitimate way for a re-grade to carry a block forward.
_PREVIOUS_RECEIPT: dict = {}


def log(*a):
    print(*a, flush=True)


# ------------------------------------------------------------------- loading

def load_frame(quick: bool = False) -> pd.DataFrame:
    cols = sorted(set(ID_COLS + TARGET_COLS + list(S.STATE_FEATURES)))
    df = pd.read_parquet(D.TRAIN_TABLE, columns=cols)
    df = df.sort_values(["month", "permno"]).reset_index(drop=True)
    if quick:
        keep = sorted(df["month"].unique())[:60]
        df = df[df["month"].isin(keep)].reset_index(drop=True)
    return df


def choose_k(Z: np.ndarray, ks, seed: int) -> dict:
    """k by silhouette on TRAIN ONLY. The target is not in this room."""
    from sklearn.cluster import KMeans
    rng = np.random.default_rng(seed)
    idx = (rng.choice(len(Z), S.SILHOUETTE_SAMPLE, replace=False)
           if len(Z) > S.SILHOUETTE_SAMPLE else np.arange(len(Z)))
    sub = Z[idx]
    out = {}
    for k in ks:
        km = KMeans(n_clusters=k, n_init=5, random_state=seed).fit(sub)
        out[int(k)] = round(float(silhouette_score(sub, km.labels_)), 5)
    best = max(out, key=lambda k: out[k])
    return {"silhouette_by_k": out, "chosen_k": int(best),
            "rule": "argmax mean silhouette on a train-only subsample of the FIRST block"}


# --------------------------------------------- joining the learners' scores

def _provenance(p: Path) -> dict:
    """Path, size, mtime and content hash of a file another session wrote.

    Written because it bit: at 14:33 this run followed `learner_v2`'s receipt to
    a predictions file that a SIBLING SESSION was still producing, whose columns
    are named `lgbm_clf__1m` rather than `lgbm_clf`, and died on a log line. A
    cross-session artefact is an input like any other -- its identity belongs in
    the receipt, and reading it must never be able to crash the run that reads it.
    """
    import hashlib
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return {"path": str(p), "bytes": p.stat().st_size,
            "mtime_utc": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc)
            .isoformat(timespec="seconds"),
            "sha256_16": h.hexdigest()[:16]}


def join_predictions(g: pd.DataFrame):
    """Attach BOTH learners' OOS scores, whichever of them exist.

    v1 columns keep their names; v2's one-month columns arrive prefixed `v2__`
    with the `__1m` suffix stripped, so `lgbm_clf` and `v2__lgbm_clf` sit side
    by side in every state table. Grading both is strictly more informative
    than choosing, and it removes the failure this replaced -- an either/or that
    silently swapped the column set out from under the run.

    Absence is reported as CANNOT DETERMINE. A missing predictions file is not
    evidence that a model has no state-conditional skill.
    """
    meta: dict = {"v1": {"status": "ABSENT"}, "v2": {"status": "ABSENT"}}
    graded: list = []

    if OOS_PREDICTIONS.exists():
        pr = pd.read_parquet(OOS_PREDICTIONS)
        cols = [c for c in PRED_COLS if c in pr.columns]
        g = g.merge(pr[["permno", "month"] + cols], on=["permno", "month"], how="left")
        graded += cols
        meta["v1"] = {"status": "JOINED", "columns": cols,
                      "provenance": _provenance(OOS_PREDICTIONS)}

    if LEARNER_V2.exists():
        try:
            v2 = json.loads(LEARNER_V2.read_text(encoding="utf-8"))
        except Exception as e:                                   # noqa: BLE001
            meta["v2"] = {"status": f"RECEIPT UNREADABLE ({e}) -- CANNOT DETERMINE"}
            v2 = {}
        p = v2.get("oos_predictions_path")
        finished = "verdicts" in v2 or "champions" in v2
        if not p:
            meta["v2"] = {"status": "RECEIPT PRESENT BUT NAMES NO PREDICTIONS FILE "
                                    "-- CANNOT DETERMINE (it may still be running)"}
        elif not Path(p).exists():
            meta["v2"] = {"status": f"RECEIPT NAMES A MISSING FILE ({p}) -- CANNOT DETERMINE"}
        else:
            pv = pd.read_parquet(p)
            take = {c: "v2__" + c[:-4] for c in pv.columns if c.endswith("__1m")}
            if take:
                sub = pv[["permno", "month"] + list(take)].rename(columns=take)
                g = g.merge(sub, on=["permno", "month"], how="left")
                graded += list(take.values())
            meta["v2"] = {"status": "JOINED", "receipt_looks_complete": bool(finished),
                          "columns": sorted(take.values()),
                          "provenance": _provenance(Path(p)),
                          "note": ("v2 writes one column per (arm, horizon); only the "
                                   "__1m columns are joined, renamed v2__<arm>.")}
    else:
        meta["v2"] = {"status": "ABSENT -- learner_v2 receipt does not exist"}

    champ = next((c for c in ("v2__lgbm_clf", "lgbm_clf") if c in g.columns), None)
    meta["champion_column"] = champ or "NONE -- CANNOT DETERMINE"
    meta["rows_with_champion_score"] = int(g[champ].notna().sum()) if champ else 0
    meta["columns_graded"] = graded
    return g, meta, graded


# ------------------------------------------------- the out-of-sample sweep

def run_company_states(df: pd.DataFrame, ks, embedder: str = "pca",
                       seed: int = S.SEED, refit_every: int = S.REFIT_EVERY_MONTHS,
                       min_train_months: int = S.MIN_TRAIN_MONTHS):
    months = sorted(df["month"].unique())
    blocks_months = S.month_blocks(months, refit_every, min_train_months)
    log(f"  months {len(months)}  ->  {len(blocks_months)} refit blocks "
        f"(burn-in {min_train_months}, refit every {refit_every})")

    assignments, blocks, block_meta = [], [], []
    prev_ref = {k: None for k in ks}          # stable-ordered centroids per k
    ref_embedder = None
    k_choice = None

    for bi, bm in enumerate(blocks_months):
        te = df[df["month"].isin(bm)]
        if te.empty:
            continue
        first_entry = te["entry_date"].min()
        tr = df[df["entry_date"] < first_entry]
        if tr["month"].nunique() < min_train_months:
            continue

        t0 = time.time()
        fitted = S.fit_block(tr, ks, seed=seed, embedder=embedder,
                             nn_reference_cutoff=first_entry)
        if ref_embedder is None:
            ref_embedder = fitted["embedder"]
            Ztr = ref_embedder.transform(tr[list(S.STATE_FEATURES)].to_numpy(dtype="float64"))
            k_choice = choose_k(Ztr, ks, seed)
            log(f"    k selection (train-only silhouette): {k_choice['silhouette_by_k']} "
                f"-> k={k_choice['chosen_k']}")

        res = S.assign_block(fitted, te, ks)

        # ---- stable ids: Hungarian-match this block's centroids to the last.
        # One implementation, shared with the test -- the version that lived
        # only here let the test's own loop mix two blocks' labels and cancel a
        # planted effect. See `S.stabilise_block_labels`.
        drifts = S.stabilise_block_labels(fitted, res, ks, prev_ref, ref_embedder)

        res["block_id"] = bi
        assignments.append(res.drop(columns=[c for c in res.columns if c.startswith("gmm_k")]))

        b = S.Block(block_id=bi, train_last_date=tr["entry_date"].max(),
                    assign_first_date=first_entry, assign_months=list(bm),
                    n_train_rows=int(len(tr)), n_train_months=int(tr["month"].nunique()),
                    n_assign_rows=int(len(te)))
        blocks.append(b)
        block_meta.append({"block_id": bi, "months": list(bm),
                           "train_rows": int(len(tr)),
                           "train_months": int(tr["month"].nunique()),
                           "embed": fitted["embed_meta"],
                           "nn_pool_rows": fitted.get("nn_pool_rows"),
                           "per_k": drifts,
                           "seconds": round(time.time() - t0, 1)})
        log(f"    block {bi:2d} {bm[0]}..{bm[-1]}  train {len(tr):,} rows / "
            f"{tr['month'].nunique()} mo  ->  assign {len(te):,}  "
            f"({time.time() - t0:.1f}s)")

    A = pd.concat(assignments, ignore_index=True)
    # anomaly percentile within the month it was scored in
    A["anomaly_pct"] = A.groupby("month")["anomaly"].rank(pct=True)
    ordering = S.assert_block_ordering(blocks)

    # the final block's centroid profile, in reference-scaled units
    profiles = {}
    for k in ks:
        prof = pd.DataFrame(prev_ref[k], columns=list(S.STATE_FEATURES))
        profiles[int(k)] = {"hints": S.name_states(prof),
                            "centroid_profile_scaled": prof.round(3).to_dict(orient="index")}
    return A, {"blocks": block_meta, "ordering_guard": ordering,
               "k_choice": k_choice, "profiles": profiles,
               "embedder": embedder}


# ------------------------------------------------------------------ grading

def stability_verdict(meta: dict, k: int) -> dict:
    """How many of the k states are the SAME state across refits?

    Two conditions, both necessary: the matched centroid never drifts more than
    `MAX_DRIFT_RATIO` of the typical inter-centroid distance, and the state
    never falls below `MIN_STATE_SHARE` of a block. A cluster that vanishes in
    2020 and returns in 2022 is two clusters wearing one number.
    """
    per_state_ok = {}
    drift_ratios = []
    for b in meta["blocks"]:
        d = b["per_k"].get(str(k), b["per_k"].get(k, {}))
        if d.get("drift_over_separation") is not None:
            drift_ratios.append(d["drift_over_separation"])
        for s, share in d.get("state_shares", {}).items():
            per_state_ok.setdefault(s, []).append(share)
    stable = []
    for s, shares in per_state_ok.items():
        if min(shares) >= S.MIN_STATE_SHARE and len(shares) == len(meta["blocks"]):
            stable.append(int(s))
    mean_ratio = float(np.mean(drift_ratios)) if drift_ratios else float("nan")
    return {
        "k": int(k),
        "mean_drift_over_separation": (None if mean_ratio != mean_ratio else round(mean_ratio, 4)),
        "max_drift_over_separation": (round(float(np.max(drift_ratios)), 4)
                                      if drift_ratios else None),
        "drift_criterion": f"mean matched-centroid drift < {S.MAX_DRIFT_RATIO} x inter-centroid distance",
        "size_criterion": f"state share >= {S.MIN_STATE_SHARE} in EVERY block",
        "states_present_and_large_in_every_block": sorted(stable),
        "n_stable_states": len(stable),
        "identity_is_readable": bool(drift_ratios and mean_ratio < S.MAX_DRIFT_RATIO),
    }


def anomaly_table(g: pd.DataFrame, target: str = "excess_vw_1m") -> list:
    q = pd.qcut(g["anomaly_pct"], 10, labels=False, duplicates="drop")
    rows = []
    for d, sub in g.assign(_d=q).groupby("_d"):
        v = sub[target].dropna()
        if len(v) < 100:
            continue
        m, n, t = S._tstat_of_monthly_means(sub, target)
        rows.append({"decile": int(d) + 1, "n": int(len(v)),
                     "mean_anomaly": round(float(sub["anomaly"].mean()), 4),
                     "mean_excess_1m": round(float(v.mean()), 5),
                     "monthly_mean": round(m, 5), "months": int(n),
                     "t_stat_months": round(t, 3),
                     "tail_loss_worst_5pct": round(float(v[v <= v.quantile(0.05)].mean()), 5)})
    return rows


def band_premium_by_market_state(g: pd.DataFrame, band: str = "b_3_5",
                                 target: str = "excess_vw_1m") -> dict:
    """Is the 3-5 band's monthly premium regime-conditional?

    The band's premium is a MONTHLY series (the equal-weighted mean excess of
    the names in the band that month). Grouping months by market state and
    testing across states is therefore a test on ~120 date blocks, not on
    50,000 name-months that share a month.
    """
    sub = g[g["band"] == band]
    if sub.empty:
        return {"note": f"no rows in band {band}"}
    monthly = sub.groupby(["month", "market_state"])[target].mean().reset_index()
    out = {"band": band, "target": target,
           "months_with_the_band": int(monthly["month"].nunique())}
    per = {}
    for s, gg in monthly.groupby("market_state"):
        v = gg[target].dropna()
        if len(v) < 4:
            per[str(int(s))] = {"months": int(len(v)), "note": "too few months"}
            continue
        sd = float(v.std(ddof=1))
        t = float(v.mean() / (sd / np.sqrt(len(v)))) if sd > 0 else float("nan")
        per[str(int(s))] = {
            "months": int(len(v)),
            "mean_monthly_excess": round(float(v.mean()), 5),
            "annualised": round(float((1 + v.mean()) ** 12 - 1), 5),
            "median_monthly": round(float(v.median()), 5),
            "t_stat": round(t, 3),
            "share_months_positive": round(float((v > 0).mean()), 4),
        }
    all_v = monthly[target].dropna()
    sd = float(all_v.std(ddof=1))
    out["pooled"] = {"months": int(len(all_v)),
                     "mean_monthly_excess": round(float(all_v.mean()), 5),
                     "annualised": round(float((1 + all_v.mean()) ** 12 - 1), 5),
                     "t_stat": round(float(all_v.mean() / (sd / np.sqrt(len(all_v)))), 3)
                     if sd > 0 else None}
    out["by_market_state"] = per
    means = [v["mean_monthly_excess"] for v in per.values() if "mean_monthly_excess" in v]
    out["spread_max_minus_min"] = round(float(max(means) - min(means)), 5) if len(means) > 1 else None
    return out


def market_state_null(monthly: pd.DataFrame, value_col: str, state_col: str,
                      n_shuffles: int = 2000, seed: int = S.SEED) -> dict:
    """Permute the month -> market-state map. 120 months is a small sample and
    a three-way split of 120 noisy monthly means produces a spread by itself."""
    rng = np.random.default_rng(seed)
    v = monthly[value_col].to_numpy(dtype="float64")
    s = monthly[state_col].to_numpy()
    ok = ~np.isnan(v)
    v, s = v[ok], s[ok]

    def spread(labels):
        means = [v[labels == u].mean() for u in np.unique(labels) if (labels == u).sum() >= 4]
        return float(max(means) - min(means)) if len(means) > 1 else float("nan")

    obs = spread(s)
    draws = np.array([spread(rng.permutation(s)) for _ in range(n_shuffles)])
    draws = draws[~np.isnan(draws)]
    return {"observed_spread": round(obs, 6), "shuffles": int(len(draws)),
            "null_mean": round(float(draws.mean()), 6),
            "null_p95": round(float(np.quantile(draws, 0.95)), 6),
            "p_value_one_sided": round(float((draws >= obs).mean()), 4),
            "beats_random_month_partition": bool((draws >= obs).mean() < 0.05),
            "shuffle": "the month -> state map is permuted ACROSS months; the monthly "
                       "values themselves are untouched",
            # S36 stamp: every draw re-randomises the map, so a PERSISTENT
            # regime labelling holding one tilt for the window is exactly what
            # this null cannot represent (learner/nullbar.py).
            "null_bar": NB.LEGACY_SHUFFLED_RANKING}


# --------------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--autoencoder", action="store_true",
                    help="also run the torch AE embedder and compare it to PCA")
    ap.add_argument("--quick", action="store_true", help="first 60 months only (smoke)")
    ap.add_argument("--shuffles", type=int, default=200)
    ap.add_argument("--refit-every", type=int, default=S.REFIT_EVERY_MONTHS)
    ap.add_argument("--reuse-assignments", action="store_true",
                    help="skip the OOS sweep and re-grade the persisted assignments. "
                         "Changes nothing upstream -- it exists because a grading bug "
                         "should not cost the sweep a second time.")
    argv = ap.parse_args(argv)

    t_start = time.time()
    ks = list(S.K_LADDER)

    receipt = {
        "artefact": "AEGIS_UNSUPERVISED_STATES_v1",
        "licence": "PRODUCT_EXPERIMENT",
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "question": ("Do latent states discovered WITHOUT future returns condition "
                     "(a) the forward return distribution, (b) BAND_PRIOR reliability, "
                     "and (c) learner reliability? That last one is the "
                     "mixture-of-experts foundation."),
        "contract": {
            "representation_may_see": "the PIT feature columns only",
            "representation_may_never_see": list(S.TARGET_PREFIXES),
            "grading_may_see": "matured future returns -- that is what grading is",
            "enforced_by": "learner.states.assert_no_target_columns + assert_block_ordering",
        },
        "schema": S.schema(),
        "schema_hash": S.schema_hash(),
        "places_orders": False,
    }
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    # Read the PREVIOUS receipt before the header overwrites it. The first
    # version of the AE carry-forward read RECEIPT *after* this line and always
    # found the header it had just written -- a carry-forward that could only
    # ever carry forward nothing, silently.
    global _PREVIOUS_RECEIPT
    try:
        _PREVIOUS_RECEIPT = json.loads(RECEIPT.read_text(encoding="utf-8")) if RECEIPT.exists() else {}
    except Exception:                                            # noqa: BLE001
        _PREVIOUS_RECEIPT = {}
    RECEIPT.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")
    log(f"  header sealed -> {RECEIPT}")

    log("\n[1] loading the PIT train table")
    df = load_frame(quick=argv.quick)
    log(f"  {len(df):,} rows, {df['month'].nunique()} months, {df['permno'].nunique():,} names")
    receipt["dataset"] = {
        "table": str(D.TRAIN_TABLE), "rows": int(len(df)),
        "months": int(df["month"].nunique()), "names": int(df["permno"].nunique()),
        "first_month": str(df["month"].min()), "last_month": str(df["month"].max()),
        "quick_mode": bool(argv.quick),
    }

    comp_path = S.STATES_DIR / ("company_states_quick.parquet" if argv.quick
                                else "company_states.parquet")
    mkt_path = S.STATES_DIR / ("market_states_quick.parquet" if argv.quick
                               else "market_states.parquet")
    meta_path = S.STATES_DIR / ("sweep_meta_quick.json" if argv.quick else "sweep_meta.json")
    if argv.reuse_assignments and comp_path.exists() and meta_path.exists():
        log("\n[2+3] REUSING the persisted out-of-sample assignments (grading only)")
        A = pd.read_parquet(comp_path)
        MS = pd.read_parquet(mkt_path)
        sm = json.loads(meta_path.read_text(encoding="utf-8"))
        receipt["company_states"] = sm["company_states"]
        receipt["market_states"] = sm["market_states"]
        receipt["reused_assignments"] = {
            "note": "the sweep was NOT re-run; assignments come from disk",
            "company_states": _provenance(comp_path),
            "market_states": _provenance(mkt_path)}
        k, mk = int(sm["primary_k"]), int(sm["market_k"])
        meta = {"blocks": receipt["company_states"]["blocks"]}
        log(f"  {len(A):,} rows, primary k = {k}, market k = {mk}")
        return _grade(argv, receipt, df, A, MS, meta, k, mk, ks, t_start)

    log("\n[2] company states, out of sample (PCA -> KMeans/GMM -> IForest -> kNN)")
    A, meta = run_company_states(df, ks, embedder="pca", refit_every=argv.refit_every)
    k = meta["k_choice"]["chosen_k"]
    log(f"  assigned {len(A):,} company-vintages; primary k = {k}")
    receipt["company_states"] = {
        "assigned_rows": int(len(A)), "assigned_months": int(A["month"].nunique()),
        "primary_k": int(k), "k_choice": meta["k_choice"],
        "blocks": meta["blocks"], "ordering_guard": meta["ordering_guard"],
        "state_profiles": meta["profiles"],
    }

    log("\n[3] market states, out of sample (expanding window, refit every month)")
    mf = S.market_month_features(df)
    ms_all = {}
    for mk in S.MARKET_K_LADDER:
        msdf, msmeta = S.run_market_states(mf, mk)
        ms_all[mk] = (msdf, msmeta)
        log(f"    k={mk}: {msmeta['assigned_months']} months, "
            f"drift/sep {msmeta['drift_over_separation']}, "
            f"counts {msmeta['state_month_counts']}")
    # market k by the same train-only rule, on the FIRST fit window
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import RobustScaler
    tr0 = mf.iloc[:S.MIN_TRAIN_MONTHS].to_numpy(dtype="float64")
    imp0 = SimpleImputer(strategy="median").fit(tr0)
    sc0 = RobustScaler().fit(imp0.transform(tr0))
    Z0 = np.clip(sc0.transform(imp0.transform(tr0)), -S.CLIP_SD, S.CLIP_SD)
    mk_choice = choose_k(Z0, S.MARKET_K_LADDER, S.SEED)
    mk = mk_choice["chosen_k"]
    MS, msmeta = ms_all[mk]
    log(f"  market k = {mk} (silhouette {mk_choice['silhouette_by_k']})")
    receipt["market_states"] = {"k_choice": mk_choice, "chosen": msmeta,
                                "ladder": {str(kk): ms_all[kk][1] for kk in ms_all},
                                "features": list(S.MARKET_FEATURES)}

    # ---- persist BEFORE grading. The expensive, reusable half of the run is
    # the sweep; grading is cheap and is where the bugs are. Writing the
    # assignments here means a grading failure costs seconds, not the sweep.
    return _grade(argv, receipt, df, A, MS, meta, k, mk, ks, t_start)


def _grade(argv, receipt, df, A, MS, meta, k, mk, ks, t_start) -> int:
    """Everything downstream of the sweep. Split out so `--reuse-assignments`
    can re-run grading against the persisted assignments without refitting a
    representation that did not change."""
    log("\n[3b] persisting the out-of-sample assignments (before any grading)")
    S.STATES_DIR.mkdir(parents=True, exist_ok=True)
    comp = S.STATES_DIR / ("company_states_quick.parquet" if argv.quick
                           else "company_states.parquet")
    mpath = S.STATES_DIR / ("market_states_quick.parquet" if argv.quick
                            else "market_states.parquet")
    sweep_meta = S.STATES_DIR / ("sweep_meta_quick.json" if argv.quick else "sweep_meta.json")
    A.to_parquet(comp, index=False)
    MS.to_parquet(mpath, index=False)
    sweep_meta.write_text(json.dumps(
        {"company_states": receipt["company_states"],
         "market_states": receipt["market_states"],
         "primary_k": int(k), "market_k": int(mk)}, indent=2, default=str), encoding="utf-8")
    log(f"  -> {comp.name}  {mpath.name}  {sweep_meta.name}")

    log("\n[4] joining matured targets and the learners' OOS predictions -- GRADING BEGINS")
    g = A.merge(df[["permno", "month"] + [c for c in TARGET_COLS if c in df.columns]
                   + ["band", "in_admissible", "ratio", "sector"]],
                on=["permno", "month"], how="left")
    g, pred_meta, graded_preds = join_predictions(g)
    receipt["predictions"] = pred_meta
    log(f"  graded prediction columns: {graded_preds}")
    #: the short list carried into the secondary tables -- the incumbent, the
    #: champion whichever learner produced it, and v1's shuffled-target null.
    headline_preds = [c for c in ([pred_meta["champion_column"], "prior",
                                   "NULL_shuffled_target__lgbm_raw"])
                      if c in g.columns]
    g = g.merge(MS[["month", "market_state"]], on="month", how="left")

    state_col = f"state_k{k}"
    log("\n[5] conditional tables")
    tables = {}
    for kk in ks:
        tables[str(kk)] = S.conditional_table(g, f"state_k{kk}")
    receipt["conditional_return_tables_by_k"] = tables
    receipt["primary_state_col"] = state_col

    receipt["transitions"] = {str(kk): S.transition_matrix(A, f"state_k{kk}") for kk in ks}
    receipt["stability"] = {str(kk): stability_verdict(meta, kk) for kk in ks}
    log(f"  stability at k={k}: {receipt['stability'][str(k)]}")

    log("\n[6] the null -- a within-month shuffle of the state labels")
    nulls = {}
    for kk in ks:
        nulls[str(kk)] = S.shuffled_null(g, f"state_k{kk}", "excess_vw_1m",
                                         n_shuffles=argv.shuffles)
        log(f"    k={kk}: observed {nulls[str(kk)]['observed']} vs null p95 "
            f"{nulls[str(kk)]['null_p95']}  p={nulls[str(kk)]['p_value_one_sided']}")
    receipt["shuffled_null_by_k"] = nulls

    log("\n[7] model reliability by state -- the money question")
    ic_tbl = S.state_ic_table(g, state_col, graded_preds, "excess_vw_1m")
    receipt["model_ic_by_state"] = {
        "primary_k": int(k),
        "target": "excess_vw_1m",
        "table": ic_tbl,
        "mixture_of_experts_summary": S.mixture_of_experts_summary(ic_tbl),
    }
    for mdl, blk in receipt["model_ic_by_state"]["mixture_of_experts_summary"].items():
        log(f"    {mdl:32s} {blk.get('verdict', blk.get('note'))}")
    receipt["model_ic_by_state_3m"] = {
        "target": "excess_vw_3m",
        "table": S.state_ic_table(g, state_col, headline_preds, "excess_vw_3m"),
    }
    receipt["band_prior_ic_by_state"] = {
        "note": ("BAND_PRIOR reliability conditional on state. `prior_1m` is the band "
                 "constant compounded to one month -- inside a state it takes at most "
                 "five distinct values, so a flat IC can mean 'the state contains one "
                 "band' rather than 'the prior fails here'. `distinct_prior_values` "
                 "says which."),
        "by_state": {
            str(int(s)): {
                "ic": S.monthly_ic(gg, "prior_1m", "excess_vw_1m"),
                "distinct_prior_values": int(gg["prior_1m"].nunique()),
                "band_mix": {str(b): round(float(v), 4) for b, v
                             in gg["band"].value_counts(normalize=True).items()},
            } for s, gg in g.groupby(state_col)},
        "pooled": S.monthly_ic(g, "prior_1m", "excess_vw_1m"),
    }

    log("\n[7b] the control -- does the state still separate INSIDE one band?")
    # RUN THE CONTROL YOU WOULD NOT HAVE CHOSEN. State 0 is 45% no_opinion +
    # 25% toxic and state 1 is 85% lt_1_5, so "the prior works in state 0 and
    # not in state 1" could be nothing but "state 1 contains one band, and a
    # constant cannot rank a constant". The honest test is to hold the band
    # FIXED and ask whether the state still does anything. If it does not, the
    # states are the band partition wearing a new coat.
    band_ctrl: dict = {}
    for b in P.ALL_BAND_LABELS:
        gb = g[g["band"] == b]
        if len(gb) < 20_000 or gb[state_col].nunique() < 2:
            band_ctrl[b] = {"rows": int(len(gb)),
                            "note": "too few rows or only one state present -- not tested"}
            continue
        tbl = S.state_ic_table(gb, state_col, headline_preds + ["mlp__raw"], "excess_vw_1m")
        band_ctrl[b] = {
            "rows": int(len(gb)),
            "state_shares": {str(int(s)): round(float(v), 4) for s, v
                             in gb[state_col].value_counts(normalize=True).sort_index().items()},
            "conditional_return_table": S.conditional_table(gb, state_col),
            "shuffled_null": S.shuffled_null(gb, state_col, "excess_vw_1m",
                                             n_shuffles=argv.shuffles),
            "model_ic_by_state": tbl,
            "mixture_of_experts_summary": S.mixture_of_experts_summary(tbl),
        }
        n = band_ctrl[b]["shuffled_null"]
        log(f"    band {b:12s} rows {len(gb):>7,}  spread {n['observed']:.5f} vs null p95 "
            f"{n['null_p95']:.5f}  p={n['p_value_one_sided']}  "
            f"beats={n['beats_random_partition']}")
    receipt["state_within_band_control"] = {
        "question": ("Held inside ONE band, does the discovered state still separate future "
                     "returns and model reliability? A yes means the states carry information "
                     "the band prior does not. A no means they are the band partition "
                     "rediscovered, and every state-conditional number above should be read "
                     "as a band-conditional number."),
        "by_band": band_ctrl,
    }

    receipt["sector_caveat"] = {
        "finding": ("CRSP SIC 9999 (NONCLASSIFIABLE) was labelled 'Public Administration' "
                    "in pre-fix panels: 99,334 / 441,278 rows = 22.51% -- missingness, "
                    "not an industry. The source was fixed 2026-09-03 "
                    "(tracker_ibes_backtest.SIC_DIVISIONS: 9900-9999 -> 'Unclassified'); "
                    "already-built panels are immutable, so this run detects the vintage "
                    "from the labels present and only relabels a pre-fix panel."),
        "effect_on_this_receipt": (
            "NONE on the representation. `sector` is not in STATE_FEATURES and not in "
            "MARKET_FEATURES, so no discovered state can be an artefact of the mislabel -- "
            "the clustering never saw a sector column at all. It is relabelled below where "
            "a state's composition is merely DESCRIBED."),
        "sector_is_a_state_feature": "sector" in S.STATE_FEATURES,
        "panel_sector_counts": {str(a): int(b) for a, b
                                in df["sector"].value_counts().items()},
    }
    _sec = df[["permno", "month", "sector"]].copy()
    # Vintage-aware: a post-fix panel (source fixed 2026-09-03) already says
    # "Unclassified" honestly and its "Public Administration" is GENUINE, so
    # relabelling it would put "unknown" on rows whose sector is known. Only a
    # pre-fix panel carries the mislabel this rename exists to disarm.
    if not bool((_sec["sector"] == SOURCE_UNCLASSIFIED_LABEL).any()):
        _sec["sector"] = _sec["sector"].replace({MISLABELLED_SECTOR: UNKNOWN_SECTOR_LABEL})
    _gs = g[["permno", "month", state_col]].merge(_sec, on=["permno", "month"], how="left")
    receipt["state_sector_composition"] = {
        "note": ("DESCRIPTIVE ONLY -- sector did not enter the representation. The 9999 "
                 "bucket is relabelled so a reader cannot read missingness as an industry."),
        "by_state": {str(int(s)): {str(a): round(float(b), 4) for a, b in
                                   gg["sector"].value_counts(normalize=True).items()}
                     for s, gg in _gs.groupby(state_col)},
    }

    log("\n[8] anomaly score and retrieval")
    receipt["anomaly_decile_table"] = anomaly_table(g)
    if "nn_excess_1m_mean" in g.columns:
        receipt["retrieval"] = {
            "what": ("mean realised 1m excess of the 3 nearest historical analogues, "
                     "where the pool is restricted to rows whose own 1m target had "
                     "matured before the assigned month began -- so this is a PIT "
                     "predictor, not a lookup of the answer"),
            "ic": S.monthly_ic(g, "nn_excess_1m_mean", "excess_vw_1m"),
            "by_state": {str(int(s)): S.monthly_ic(gg, "nn_excess_1m_mean", "excess_vw_1m")
                         for s, gg in g.groupby(state_col)},
            "mean_distance": round(float(g["nn1_dist"].mean()), 4),
            "median_distance": round(float(g["nn1_dist"].median()), 4),
        }

    log("\n[9] the 3-5 band's premium, conditional on the market regime")
    receipt["band_3_5_by_market_state"] = band_premium_by_market_state(g)
    monthly35 = (g[g["band"] == "b_3_5"].groupby(["month", "market_state"])["excess_vw_1m"]
                 .mean().reset_index())
    receipt["band_3_5_market_state_null"] = market_state_null(
        monthly35, "excess_vw_1m", "market_state")
    receipt["all_bands_by_market_state"] = {
        b: band_premium_by_market_state(g, band=b) for b in P.ALL_BAND_LABELS}
    mkt_ic = S.state_ic_table(g, "market_state",
                              headline_preds + ["nn_excess_1m_mean"], "excess_vw_1m")
    receipt["model_ic_by_market_state"] = {
        "table": mkt_ic,
        "mixture_of_experts_summary": S.mixture_of_experts_summary(mkt_ic)}

    if not argv.autoencoder and argv.reuse_assignments and _PREVIOUS_RECEIPT:
        # A re-grade must not silently DROP a result the previous run measured.
        # Carrying the block forward, stamped, is honest; deleting it because
        # this invocation did not rerun torch is not.
        try:
            prev = _PREVIOUS_RECEIPT
            if "autoencoder_arm" in prev:
                receipt["autoencoder_arm"] = dict(prev["autoencoder_arm"])
                receipt["autoencoder_arm"]["carried_forward"] = (
                    "measured by an earlier run of this script; NOT re-measured in this "
                    "re-grade. The AE arm depends only on the sweep, which was reused.")
                log("\n[10] autoencoder arm CARRIED FORWARD from the previous receipt")
        except Exception as e:                                   # noqa: BLE001
            log(f"    could not carry the AE arm forward ({e})")

    if argv.autoencoder:
        log("\n[10] the autoencoder arm -- kept only if it beats PCA")
        A2, meta2 = run_company_states(df, [k], embedder="ae", refit_every=argv.refit_every)
        g2 = A2.merge(df[["permno", "month", "excess_vw_1m", "excess_vw_3m", "fwd_3m",
                          "prior_1m", "band"]], on=["permno", "month"], how="left")
        ae_null = S.shuffled_null(g2, f"state_k{k}", "excess_vw_1m", n_shuffles=argv.shuffles)
        receipt["autoencoder_arm"] = {
            "k": int(k), "blocks": meta2["blocks"][-1:],
            "conditional_table": S.conditional_table(g2, f"state_k{k}"),
            "shuffled_null": ae_null,
            "pca_shuffled_null": nulls[str(k)],
            "verdict": ("KEPT" if ae_null["observed"] > nulls[str(k)]["observed"]
                        and ae_null["p_value_one_sided"] <= nulls[str(k)]["p_value_one_sided"]
                        else "NOT KEPT -- PCA+KMeans is at least as good and is simpler"),
        }
        log(f"    {receipt['autoencoder_arm']['verdict']}")

    log("\n[11] the assignments were persisted BEFORE grading -- see step [3b]")
    (S.STATES_DIR / "README.md").write_text(
        "# learner/states assignments\n\n"
        "`company_states.parquet` -- one row per (permno, month) assigned OUT OF SAMPLE by a\n"
        "representation fitted only on data strictly before that month. `state_k*` are\n"
        "STABLE ids (Hungarian-matched across refits), `anomaly` is higher = more unusual,\n"
        "`nn*_permno` / `nn*_month` / `nn*_dist` are the three nearest historical analogues,\n"
        "and `nn_excess_1m_mean` is the mean 1m excess THOSE analogues realised (a PIT\n"
        "retrieval predictor -- their targets had matured before this month began).\n\n"
        "`market_states.parquet` -- one row per month, `market_state` assigned by a KMeans\n"
        "fitted only on months strictly before it.\n\n"
        "Written by `scripts/learner_states_run.py`. Receipt:\n"
        "`backend/data/optimus/tracker_backtest/unsupervised_states_20260903.json`.\n",
        encoding="utf-8")
    receipt["artefacts"] = {"company_states": str(comp), "market_states": str(mpath),
                            "rows": int(len(A)), "market_rows": int(len(MS))}

    receipt["runtime_seconds"] = round(time.time() - t_start, 1)
    RECEIPT.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")
    log(f"\n  receipt -> {RECEIPT}  ({receipt['runtime_seconds']}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
