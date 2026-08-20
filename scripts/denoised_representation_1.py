"""DENOISED-REPRESENTATION-1 — does removing the noise actually help?

CROSS-SOURCE-STRUCTURE-1 found 3-7 genuine signal factors among 28
features from four sources, with the noise floor set analytically by
Marchenko-Pastur. That is a claim about the DATA. This is the claim's
consequence, and the only version of it that can be checked:

    if most of those 28 dimensions really are estimation noise, then a
    model given only the SIGNAL subspace should do as well as one given
    everything — with a fraction of the inputs.

If it does, the noise removal is real and useful, and the unsupervised
layer has earned a place in the pipeline. If the raw features win, then
the "noise" was carrying something the spectrum could not see, or the
learner was already robust to it. Either answer is worth having, and the
second is the more likely one for a gradient-boosted tree, which is not
badly hurt by uninformative inputs. Declared in advance: **the denoised
arm is expected to MATCH, not beat, the raw arm; the interesting outcome
is how few dimensions it needs to do it.**

ARMS, all on identical rows and folds, predicting log forward variance:

    raw            all 28 features                       (incumbent)
    mp_denoised    projection onto the top-k eigenvectors, k chosen by
                   the MP bound, both FIT ON TRAIN ONLY
    random_k       k RANDOM orthogonal directions — separates "the TOP-k
                   subspace is informative" from "any k dimensions would
                   do"
    pca_half_k     k/2 components — a deliberately too-aggressive control

RESULT (modern era, k = 7 of 28 every fold): the declared expectation was
REFUTED. Denoising did not match raw, it lost, and by a powered margin:

    arm            rankIC   MSE(logV)   vs raw
    raw            0.8018     0.76075   —
    mp_denoised    0.7676     0.89189   -0.131  (MDE 0.023) POWERED
    pca_half_k     0.7323     0.96142   -0.201  POWERED
    random_k       0.6695     1.01375   -0.253  POWERED

Read the last two rows together: the top-7 subspace is much better than 7
RANDOM directions, so the eigen-ORDERING is genuinely informative. What
fails is the CUTOFF. Marchenko-Pastur separates signal from noise in a
COVARIANCE; it never saw the target, and a direction can carry little
cross-sectional variance while still predicting forward variance. The
correlation-noise floor is not the prediction-relevance floor.

Practical consequence: the repo's denoiser belongs where it already is —
covariance estimation for portfolio construction — and NOT in feature
selection for a supervised head.

THE DISCIPLINE THAT MATTERS: the eigenbasis is estimated on the training
fold alone and then APPLIED to the test fold. Fitting the decomposition
on the pooled panel would let the test fold's covariance choose the
representation that predicts it — a subtle and very common leak, and one
this programme has already paid for in other forms.

    python -m scripts.denoised_representation_1

SCREEN.
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

from backend import config as _config                        # noqa: E402
from backend.services.net_tournament import (                # noqa: E402
    bootstrap_block_dates, rank_ic_by_date)
from backend.services.world_model import (                   # noqa: E402
    block_bootstrap_paired)
from scripts.cross_source_structure_1 import build_panel     # noqa: E402
from scripts.option_incremental_risk_1 import (              # noqa: E402
    VAR_FLOOR, qlike)

OUT = _config.OPTIMUS_LEDGER_DIR / "structure"
SEED = 20260820


def mp_k(Z: np.ndarray) -> tuple[int, np.ndarray]:
    """Signal-factor count and eigenvectors, from TRAIN rows only."""
    from backend.services.covariance import marchenko_pastur_bound
    C = np.corrcoef(Z, rowvar=False)
    C = np.nan_to_num(C, nan=0.0)
    np.fill_diagonal(C, 1.0)
    w, v = np.linalg.eigh(C)
    w, v = w[::-1], v[:, ::-1]
    T, N = Z.shape
    # unit noise variance: exact for a correlation matrix under the null
    lam = marchenko_pastur_bound(T, N, var=1.0)
    k = max(int((w > lam).sum()), 1)
    return k, v


def main() -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--era", default="modern")
    a = ap.parse_args()

    print("building cross-source panel...")
    df, src = build_panel(a.era)
    # keep only well-covered sources, as in CROSS-SOURCE-STRUCTURE-1
    for k in list(src):
        cs = [c for c in src[k] if c in df.columns]
        if not cs or float(df[cs].notna().all(axis=1).mean()) < 0.60:
            src.pop(k, None)
    feats = [c for v in src.values() for c in v if c in df.columns]
    sub = df[["date", "permno", "fwd_var"] + feats].replace(
        [np.inf, -np.inf], np.nan).dropna()
    print(f"panel: {len(sub):,} rows, {len(feats)} features, "
          f"{sub['date'].nunique()} dates")

    from lightgbm import LGBMRegressor
    years = sorted(sub["date"].dt.year.unique())
    test_years = [y for y in years if y >= years[0] + 4]
    # `pca_same_k` was originally listed as a separate arm; it is
    # IDENTICAL to mp_denoised by construction (same eigenvectors, same
    # k), so reporting both would have shown one result twice as if it
    # were two. Replaced by a genuine control: k RANDOM orthogonal
    # directions, which tests whether the TOP-k subspace matters or only
    # the dimension count.
    arms = ("raw", "mp_denoised", "random_k", "pca_half_k")
    ic = {x: [] for x in arms}
    ql = {x: [] for x in arms}
    mse = {x: [] for x in arms}
    ks = []

    for y in test_years:
        tr = sub[sub["date"].dt.year < y]
        te = sub[sub["date"].dt.year == y]
        if len(tr) < 5000 or len(te) < 500:
            continue
        # cross-sectional rank-normalise within date (both folds use
        # their OWN dates, so this is not a leak)
        Ztr = (tr.groupby("date")[feats].rank(pct=True) - 0.5).to_numpy(float)
        Zte = (te.groupby("date")[feats].rank(pct=True) - 0.5).to_numpy(float)
        k, V = mp_k(Ztr)                       # TRAIN ONLY
        ks.append({"year": int(y), "k": int(k), "n_features": len(feats)})
        ytr = np.log(tr["fwd_var"].to_numpy())
        atrue = te["fwd_var"].to_numpy()
        rng = np.random.default_rng(SEED + y)
        Q, _ = np.linalg.qr(rng.normal(size=(len(feats), k)))
        reps = {
            "raw": (Ztr, Zte),
            "mp_denoised": (Ztr @ V[:, :k], Zte @ V[:, :k]),
            "random_k": (Ztr @ Q, Zte @ Q),
            "pca_half_k": (Ztr @ V[:, :max(k // 2, 1)],
                           Zte @ V[:, :max(k // 2, 1)]),
        }
        for arm, (Xtr, Xte) in reps.items():
            m = LGBMRegressor(n_estimators=300, num_leaves=31,
                              learning_rate=0.05, random_state=SEED,
                              verbose=-1)
            m.fit(Xtr, ytr)
            pred = np.exp(m.predict(Xte))
            ic[arm].append(rank_ic_by_date(pred, atrue,
                                           te["date"].to_numpy()))
            lr = np.log(atrue / np.clip(pred, VAR_FLOOR, None))
            ql[arm].append(pd.Series(qlike(atrue, pred),
                                     index=te["date"].to_numpy()))
            mse[arm].append(pd.Series(lr ** 2,
                                      index=te["date"].to_numpy()))
        print(f"  fold {y}: k={k}/{len(feats)}  train {len(tr):,}")

    ICs = {x: pd.concat(v) for x, v in ic.items()}
    MSE = {x: pd.concat(v).groupby(level=0).mean() for x, v in mse.items()}
    QL = {x: pd.concat(v).groupby(level=0).mean() for x, v in ql.items()}
    ix = MSE["raw"].index
    for x in arms:
        ix = ix.intersection(MSE[x].index)
    dates = np.array(sorted(ix), dtype="datetime64[D]")
    blk = bootstrap_block_dates(dates, 21)

    summary = {x: {"mean_rank_ic": round(float(ICs[x].reindex(ix).mean()), 4),
                   "mse_log_var": round(float(MSE[x].loc[ix].mean()), 5),
                   "mean_qlike": round(float(QL[x].loc[ix].mean()), 5)}
               for x in arms}
    contrasts = {}
    for x in arms:
        if x == "raw":
            continue
        d = (MSE["raw"].loc[ix] - MSE[x].loc[ix]).to_numpy(float)
        inf = block_bootstrap_paired(d, dates, block_days=blk,
                                     seed=SEED).as_dict()
        contrasts[f"{x}_vs_raw"] = {
            "d_mse_log_var": round(inf["mean"], 6),
            "arm_better": bool(inf["mean"] > 0),
            "ci": [round(inf["ci_lo"], 6), round(inf["ci_hi"], 6)],
            "mde_80": round(inf["mde_80pct_power"], 6),
            "significant": bool(inf["ci_lo"] > 0 or inf["ci_hi"] < 0),
            "clears_mde": bool(abs(inf["mean"])
                               >= inf["mde_80pct_power"])}

    mp = contrasts["mp_denoised_vs_raw"]
    rnd = contrasts.get("random_k_vs_raw", {})
    mean_k = float(np.mean([r["k"] for r in ks])) if ks else 0.0
    if not mp["significant"]:
        verdict = (f"REPRESENTATION_NEUTRAL — {mean_k:.1f} of "
                   f"{len(feats)} dimensions carry everything the raw "
                   f"feature set does; the discarded dimensions were "
                   f"noise the learner was already ignoring")
    elif mp["arm_better"]:
        verdict = "DENOISING_HELPS — the signal subspace beats raw"
    else:
        better_than_random = (mp["d_mse_log_var"]
                              > rnd.get("d_mse_log_var", -9e9))
        verdict = ("DENOISING_HURTS — the discarded dimensions carried "
                   "information the correlation spectrum could not see. "
                   "Marchenko-Pastur separates signal from noise in a "
                   "COVARIANCE, which is not the same as separating "
                   "useful from useless for predicting a TARGET: a "
                   "low-variance direction can still be predictive, and "
                   "the decomposition never saw the target. "
                   + ("The top-k subspace does still beat k random "
                      "directions, so the ordering is real — it is the "
                      "TRUNCATION that costs."
                      if better_than_random else
                      "It does not even beat k random directions."))

    res = {"trial": "DENOISED-REPRESENTATION-1", "mode": "SCREEN",
           "era": a.era,
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "n_features": len(feats), "features": feats,
           "sources": {k: v for k, v in src.items()},
           "k_by_fold": ks, "mean_k": round(mean_k, 2),
           "leak_control": "the eigenbasis is estimated on the TRAINING "
                           "fold only and applied to the test fold; "
                           "fitting it on the pooled panel would let the "
                           "test fold choose its own representation",
           "summary": summary, "contrasts": contrasts, "verdict": verdict}
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"denoised_representation_1_{a.era}_2026-08-20.json"
    p.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")

    print(f"\n{'arm':14s} {'rankIC':>8s} {'MSElogV':>9s} {'QLIKE':>9s}")
    for x in arms:
        s_ = summary[x]
        print(f"{x:14s} {s_['mean_rank_ic']:>8.4f} "
              f"{s_['mse_log_var']:>9.5f} {s_['mean_qlike']:>9.4f}")
    print("\nvs raw (positive == arm better on MSE log variance):")
    for kk, c in contrasts.items():
        t = ("POWERED" if c["clears_mde"]
             else ("significant" if c["significant"] else "ns"))
        print(f"  {kk:26s} {c['d_mse_log_var']:+.5f} "
              f"MDE {c['mde_80']:.5f}  {t}")
    print(f"\nmean k = {mean_k:.1f} of {len(feats)} features")
    print(f"VERDICT: {verdict}")
    print(f"receipt -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
