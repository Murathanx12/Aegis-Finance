# Full-sample-fit audit — every scaler/selector/calibrator fit site (M4)

**Date:** 2026-08-04 · **Scope:** `engine/` (aegis-finance) + `aegis_brain/`
(Aegis module) · **Rule audited:** no estimator may be fitted on data spanning
a train/test wall (walk-forward folds, holdout, or the factory's
explore(2004-2018)/confirm(2019-2024) wall).

Method: exhaustive grep for `StandardScaler|MinMaxScaler|RobustScaler|
SimpleImputer|QuantileTransformer|PCA(|.fit(|fit_transform` over both repos,
then manual window tracing of every hit.

## The table

| # | Site | What is fitted | Data window | Verdict |
|---|---|---|---|---|
| 1 | `engine/training/feature_selection.py:71` (MI), `:92` (StandardScaler), `:105` (LassoCV) | the entire feature-selection pipeline | **FULL SAMPLE** — callers pass the complete feature matrix and target | **DEFECT FS-1** (below) |
| 2 | `engine/autoresearch/aegis_train.py:144-152` | per-fold scaler + LogisticRegression + LightGBM | train fold only; `scaler.transform` on test | OK |
| 3 | `engine/autoresearch/aegis_train.py:163-166` | isotonic calibrator | fitted on **train** predictions, applied to test; evaluated on test | OK-with-note: calibrating on in-sample train predictions biases the calibrator optimistic (self-described "imperfect but workable"). Not a wall-crossing leak; evaluation is out-of-fold, so the CANON rule (never evaluate calibration on the calibrator's own fit data) is respected |
| 4 | `engine/training/train_severity_model.py:157-171` | per-fold LGBM + STLFSI logistic + median fill | train fold only; median explicitly computed within train (`:166`) | OK |
| 5 | `engine/training/sample_uniqueness.py:15` | LGBM for uniqueness weights | caller-supplied | caller-dependent utility; both current callers pass train-fold data — OK today, no guard |
| 6 | `aegis_brain/` (entire factory) | — | — | **CLEAN**: zero sklearn fit sites; the factory is scan-based (rank/sort/threshold), nothing is estimated |

## DEFECT FS-1 — full-sample feature selection (two production call sites)

`select_features(features, target)` runs mutual-information ranking +
standardization + LassoCV **on the complete history**, and the surviving
feature list is then used inside every walk-forward fold and the holdout:

- `engine/training/train_crash_model.py:120` — **the production crash-model
  trainer**. Every walk-forward AUC/Brier this project has reported for the
  crash model was computed on features chosen with knowledge of the full
  sample, including every test fold. Classic selection-before-split bias:
  the fold metrics are optimistic by an unmeasured amount.
- `engine/autoresearch/aegis_prepare.py:98` — same pattern in the
  autoresearch path (which, per C7, had additionally never run to the split
  stage before 2026-08-04).

Aggravating: `feature_selection.py:72,93` and `aegis_train.py:145-146` use
`fillna(0)` on feature matrices — a direct violation of the house rule
(sklearn paths must use `SimpleImputer(strategy="median")`; zeros are
in-distribution values for z-scored macro features).

**Filed remediation (belongs to the C4/M4 re-run, not this audit):**
selection must see only data before the first test boundary (or run
per-fold). The C4 FRED publication-lag re-run should carry this fix in the
same before/after table, since both shift measured AUC/Brier in the honest
direction and the deltas are paper exhibits either way.

**Blast radius if unfixed:** every historical crash-model walk-forward metric
(the "Walk-forward AUC-ROC ≥ 0.70" health line included) is upper-biased.
Does NOT affect: severity model (clean), factory/lanes (no estimators), the
M1 calibration (asserts its own constants, uses no sklearn).
