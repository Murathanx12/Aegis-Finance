"""Build the versioned RISK-HEAD artifact the G2 lane transport pins.

Order 24 Phase 6/7. The programme's model layer is currently the
unpinned surface: lane configs pin data and config hashes, but a model
was until now a file someone trained. This produces the contract:

    models/<name>/<semver>/
        model.txt            LightGBM booster (text, diffable)
        features.json        exact columns, order, transforms
        calibration.json     the level correction, fitted on train folds
        train_window.json    start/end, folds, embargo, purge
        model_card.md        what it beat, on what loss, and how it fails
        MANIFEST.sha256      every file above, hashed

A lane may reference a model only by `name@semver@sha256`. If the hash
does not resolve, the lane refuses to mark.

WHY THIS MODEL, AND WHAT IT IS NOT
----------------------------------
OPTION-INCREMENTAL-RISK-1 settled the model choice with the baselines
that actually threaten it, in BOTH eras:
  - it beats IV-scaled on MSE(log variance)   (+0.144 modern, +0.064 early)
  - it beats its own numeric twin             (+0.113 modern, +0.064 early)
  - HAR-RV loses to IV; the numeric-only model does NOT clear IV
  - it survives a +1-month feature lag with graceful degradation

But raw implied variance still wins QLIKE, by OVER-FORECASTING (bias
-0.32 in logs, under-forecasting only 31% of the time — the variance
risk premium, which QLIKE's asymmetry rewards). The model's edge is in
ORDERING, and its level is close to unbiased, which is worse under QLIKE
and better for anything that needs a calibrated number.

Sizing consumes the LEVEL. So this artifact ships with an explicit level
calibration fitted on a span DISJOINT from both the fit rows and the
holdout, and the model card states plainly that the ordering is the
evidence and the level is a correction.

(The first build got this wrong in an instructive way: the offset was
fitted on the fit rows, where the booster had already driven the mean
residual to ~0, so "raw" and "calibrated" came out byte-identical. A
calibration that silently does nothing while still printing a
"calibrated" column is precisely the house failure mode — green, and
empty. Hence three disjoint spans, in time order.)

    python -m scripts.build_risk_head_artifact --version 2.0.0
"""

from __future__ import annotations

import argparse
import hashlib
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
from scripts.option_incremental_risk_1 import (              # noqa: E402
    ERAS, VAR_FLOOR, WITH_OPT, build, qlike)

MODELS = _config.OPTIMUS_LEDGER_DIR / "models"
NAME = "risk_head_vol_lgbm_options"
SEED = 20260820


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="2.0.0")
    ap.add_argument("--era", default="modern", choices=list(ERAS))
    ap.add_argument("--calib-years", type=int, default=2,
                    help="years reserved from the END of training to fit "
                         "the level offset; must be disjoint from the fit "
                         "span or the calibration is a no-op")
    ap.add_argument("--train-through", type=int, default=2021,
                    help="last TRAIN year; later years are the held-out "
                         "evaluation the model card reports")
    a = ap.parse_args()

    cfg = ERAS[a.era]
    print(f"building {a.era} panel...")
    df = build(a.era)
    need = list(dict.fromkeys(list(WITH_OPT) + ["fwd_var"]))
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=need)

    # THREE disjoint spans, not two. A level offset fitted on the same
    # rows the booster minimised squared error over is ~0 BY
    # CONSTRUCTION — the calibration would be a silent no-op that still
    # printed a "calibrated" column. Caught on the first build (raw and
    # calibrated were byte-identical). The offset therefore needs its own
    # fold: fit -> calibrate -> evaluate, all disjoint and in time order.
    cal_from = a.train_through - a.calib_years + 1
    fit = df[df["date"].dt.year < cal_from]
    cal = df[(df["date"].dt.year >= cal_from)
             & (df["date"].dt.year <= a.train_through)]
    te = df[df["date"].dt.year > a.train_through]
    print(f"fit  {len(fit):,} rows (< {cal_from})\n"
          f"calib {len(cal):,} rows ({cal_from}..{a.train_through})\n"
          f"holdout {len(te):,} rows (> {a.train_through})")
    if not len(cal) or not len(te):
        raise SystemExit("empty calibration or holdout span")

    from lightgbm import LGBMRegressor
    feats = list(WITH_OPT)
    m = LGBMRegressor(n_estimators=300, num_leaves=31, learning_rate=0.05,
                      random_state=SEED, verbose=-1)
    m.fit(fit[feats].to_numpy(), np.log(fit["fwd_var"].to_numpy()))

    # LEVEL CALIBRATION on the held-out calibration span. Predicting log
    # variance and exponentiating is biased in levels (Jensen); sizing
    # consumes levels. A single additive constant in log space is
    # deliberately the simplest correction that can be audited.
    cal_pred_log = m.predict(cal[feats].to_numpy())
    offset = float(np.mean(np.log(cal["fwd_var"].to_numpy())
                           - cal_pred_log))
    tr = fit

    def predict_var(frame):
        return np.exp(m.predict(frame[feats].to_numpy()) + offset)

    # held-out metrics, uncalibrated vs calibrated
    from backend.services.net_tournament import rank_ic_by_date
    a_true = te["fwd_var"].to_numpy()
    raw = np.exp(m.predict(te[feats].to_numpy()))
    cal = predict_var(te)
    iv = np.exp(te["log_iv_var"].to_numpy())
    metrics = {}
    for tag, pred in (("model_raw", raw), ("model_calibrated", cal),
                      ("iv_only_baseline", iv)):
        lr = np.log(a_true / np.clip(pred, VAR_FLOOR, None))
        metrics[tag] = {
            "mean_qlike": round(float(np.mean(qlike(a_true, pred))), 5),
            "mse_log_var": round(float(np.mean(lr ** 2)), 5),
            "bias_mean_log_ratio": round(float(np.mean(lr)), 5),
            "mean_rank_ic": round(float(rank_ic_by_date(
                pred, a_true, te["date"].to_numpy()).mean()), 4)}

    d = MODELS / NAME / a.version
    d.mkdir(parents=True, exist_ok=True)
    m.booster_.save_model(str(d / "model.txt"))
    (d / "features.json").write_text(json.dumps({
        "features": feats,
        "target": "log(annualized realized variance over t+1..t+21)",
        "prediction_units": "annualized realized VARIANCE (not vol, not "
                            "a probability); take sqrt for vol",
        "transforms": {
            "log_rv_d/w/m/q": "log of mean(ret^2) over 1/5/21/63 days, "
                              "annualized x252, floored at 1e-8",
            "log_iv_var": "log(ATM implied vol ^ 2), floored at 1e-8",
            "opt_*": "OptionMetrics 30d surface, last obs of month, "
                     "staleness-capped at 14 calendar days"},
        "formation_convention": "features read at the month-end CLOSE of "
                                "t; target spans t+1..t+21 and never "
                                "includes t (CHRONOLOGY-AUDIT-1 C2)",
        "missing_data": "rows lacking any feature are DROPPED, never "
                        "imputed — the ladder compared arms on identical "
                        "rows and the artifact keeps that rule"},
        indent=2), encoding="utf-8")
    (d / "calibration.json").write_text(json.dumps({
        "kind": "additive offset in log-variance space",
        "offset": offset,
        "fitted_on": f"a DISJOINT calibration span "
                     f"({a.train_through - a.calib_years + 1}.."
                     f"{a.train_through}), never the fit span — an offset "
                     f"fitted where the booster already minimised squared "
                     f"error is ~0 by construction and calibrates nothing",
        "why": "predicting log variance and exponentiating is biased in "
               "levels; ordering is the evidence, level is a correction",
        "apply": "var_hat = exp(booster.predict(X) + offset)"},
        indent=2), encoding="utf-8")
    (d / "train_window.json").write_text(json.dumps({
        "era": a.era,
        "universe": cfg["univ"],
        "fit_years": [cfg["years"][0], a.train_through - a.calib_years],
        "calibration_years": [a.train_through - a.calib_years + 1,
                              a.train_through],
        "holdout_years": [a.train_through + 1, cfg["years"][1]],
        "n_fit_rows": int(len(tr)), "n_holdout_rows": int(len(te)),
        "embargo": "none needed at this cadence: features are month-end "
                   "and the target spans the FOLLOWING 21 trading days, "
                   "so train and holdout share no outcome days across "
                   "the year boundary except at most one month, which "
                   "the year split already excludes",
        "seed": SEED,
        "library_versions": _libs()}, indent=2), encoding="utf-8")
    (d / "model_card.md").write_text(_card(a, metrics, offset, feats, tr,
                                           te), encoding="utf-8")

    man = {f.name: sha(f) for f in sorted(d.iterdir())
           if f.name != "MANIFEST.sha256"}
    (d / "MANIFEST.sha256").write_text(
        "\n".join(f"{v}  {k}" for k, v in man.items()) + "\n",
        encoding="utf-8")

    print(f"\nartifact -> {d}")
    for k, v in metrics.items():
        print(f"  {k:18s} QLIKE {v['mean_qlike']:>8.4f}  "
              f"MSElogV {v['mse_log_var']:.4f}  "
              f"rankIC {v['mean_rank_ic']:.4f}  "
              f"bias {v['bias_mean_log_ratio']:+.4f}")
    print(f"\npin as: {NAME}@{a.version}@"
          f"{man.get('model.txt', '')[:16]}")
    return 0


def _libs() -> dict:
    import lightgbm
    import sklearn
    return {"lightgbm": lightgbm.__version__,
            "numpy": np.__version__, "pandas": pd.__version__,
            "scikit-learn": sklearn.__version__,
            "python": sys.version.split()[0]}


def _card(a, metrics, offset, feats, tr, te) -> str:
    m = metrics
    return f"""# Model card — {NAME} v{a.version}

Built {datetime.now(timezone.utc).isoformat(timespec='seconds')} by
`scripts/build_risk_head_artifact.py`. **SIMULATION / research artifact.**
It has no track record and marking a lane with it does not create one.

## What it predicts

Annualized realized **variance** over t+1..t+21, from month-end features
at t. Not volatility, not a probability, not a crash flag. Take the
square root for vol.

## What it beat, and on which loss

From OPTION-INCREMENTAL-RISK-1, on identical rows, folds and missingness,
in **both** eras (modern 2017-2024, early 2001-2012):

| contrast | modern | early |
|---|---|---|
| vs IV-scaled, MSE(log var) | +0.144 (MDE 0.064) CLEARS | +0.064 (MDE 0.016) CLEARS |
| vs numeric-only twin | +0.113 (MDE 0.062) CLEARS | +0.064 (MDE 0.016) CLEARS |
| HAR-RV vs IV-scaled | -0.131 CLEARS (IV wins) | -0.169 CLEARS (IV wins) |
| numeric-only vs IV-scaled | +0.031, below MDE | -0.000, below MDE |

Read that last row carefully: **without options features, this model
family does not clear the IV baseline.** The options block is not a
refinement, it is the reason the model beats the market's own estimate.

The classical challenger, HAR-RV (Corsi), is *not* the strongest
baseline here — implied variance is. HAR beats only the trailing-realized
-variance arm.

## Held-out performance (this artifact, years > {a.train_through})

| arm | QLIKE | MSE(log var) | rank IC | bias |
|---|---|---|---|---|
| model (raw) | {m['model_raw']['mean_qlike']} | {m['model_raw']['mse_log_var']} | {m['model_raw']['mean_rank_ic']} | {m['model_raw']['bias_mean_log_ratio']:+} |
| model (calibrated) | {m['model_calibrated']['mean_qlike']} | {m['model_calibrated']['mse_log_var']} | {m['model_calibrated']['mean_rank_ic']} | {m['model_calibrated']['bias_mean_log_ratio']:+} |
| IV-only baseline | {m['iv_only_baseline']['mean_qlike']} | {m['iv_only_baseline']['mse_log_var']} | {m['iv_only_baseline']['mean_rank_ic']} | {m['iv_only_baseline']['bias_mean_log_ratio']:+} |

Calibration is an additive offset of {offset:+.4f} in log-variance space,
fitted on train rows only.

## Known failure modes

1. **QLIKE will often favour raw IV over this model, and that is not a
   defect to fix by chasing QLIKE.** QLIKE punishes under-forecasting
   ~linearly and over-forecasting only ~logarithmically; implied variance
   embeds a variance risk premium and so over-forecasts by construction,
   which the loss rewards. If a downstream consumer needs "never
   understate risk", it should say so and use an explicitly conservative
   quantile — not silently adopt IV because one loss preferred it.
2. **The ordering is the evidence; the level is a correction.** Rank IC
   is where this model is strong. The level rests on a one-parameter
   offset that has not been validated across regimes.
3. **Linear and neural arms blow up in the tail.** In the early era,
   ridge and the MLP produced occasional catastrophic under-forecasts
   (mean QLIKE ~581 and ~585 against ~0.32 for this model) while their
   MSE(log var) looked healthy. A model can be fine on average and
   ruinous in the tail that sizing actually cares about. This is why the
   MLP is not the shipped artifact despite competitive rank IC.
4. **Options coverage gates the population.** ~98.5% of modern rows and
   ~83.5% of early rows carry a complete options block; rows without one
   are dropped, not imputed. The model has nothing to say about names
   with no listed options, which is a real and unmodelled selection.
5. **The entitled CRSP vintage ends 2024-12-31.** Nothing in training
   knows anything after that date.

## Provenance and PIT

- Features read at the month-end close of t; target spans t+1..t+21 and
  never includes t (CHRONOLOGY-AUDIT-1 C2 PASS).
- Options joined with a measured, sign-asserted lag: 307,924 joins,
  min lag 0 days, max 30, **zero negative** — no surface postdates its
  formation date (C1 PASS). Both consumers now refuse on a negative lag
  rather than relying on the one-sided staleness filter.
- Shift-invariance: with every feature lagged one extra month the model
  degrades gracefully and all comparative conclusions hold.
- Train rows {len(tr):,}; holdout rows {len(te):,}; features {len(feats)}.

## Licence

Trained on WRDS-entitled data (CRSP, OptionMetrics). Per
`docs/DECISION_WRDS_RECEIPT_POLICY.md` the weights are publishable as a
low-parameter model over ~10^5 rows, but the training panel is **not**.
Reproduction requires the same entitlement.
"""


if __name__ == "__main__":
    raise SystemExit(main())
