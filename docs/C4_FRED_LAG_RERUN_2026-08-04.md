# C4 — FRED publication-lag + FS-1 selection rerun
**Run:** 2026-08-04T06:20:48+00:00 · harness: purged 5-fold CV, predictions pooled across folds (`aegis_train.train_and_evaluate`, LGB+LR blend, isotonic, seed 42) · same data snapshot for all three configs

A = pre-fix behavior (reference-date FRED, RECPROUSM156N included, full-sample LASSO selection). B adds publication-lag alignment (recession_prob excluded). C additionally restricts selection to the first 60% of the sample. **C is the honest pipeline; A-vs-C is the measured cost of the two leaks.**

| Config | features | 3m AUC | 3m Brier | 6m AUC | 6m Brier | 12m AUC | 12m Brier |
|---|---|---|---|---|---|---|---|
| A baseline (ref-date, full-sample selection) | 30 | 0.499 | 0.051 | 0.500 | 0.125 | 0.650 | 0.141 |
| B +publication lags | 20 | 0.500 | 0.051 | 0.597 | 0.110 | 0.549 | 0.186 |
| C +selection window (honest pipeline) | 20 | 0.499 | 0.051 | 0.528 | 0.122 | 0.461 | 0.323 |

Notes: the deltas are the exhibit — if A > C, the historical numbers were flattered by look-ahead exactly as filed in `FULL_SAMPLE_FIT_AUDIT_2026-08-04.md`; if A ≈ C, the leaks were present but not load-bearing, which is also worth knowing. Validation split, trainer, seed and data snapshot are identical across rows; only alignment and selection window differ.
## Interpretation (written same day, before any further tuning)

1. **The pre-fix 12m "skill" was substantially leak-driven.** A's 12m AUC of
   0.650 is the only cell resembling the historically quoted numbers; under
   the honest pipeline (C) it falls to 0.461 — below chance. The two leaks
   (reference-date FRED + full-sample selection) were load-bearing for the
   one horizon that looked good.
2. **3m and 6m are at chance in every configuration** — including the leaky
   baseline. The historically quoted "walk-forward AUC ≥ 0.70" does not
   reproduce on this harness even before the fixes, so part of the gap is
   harness-dependence (different era mix, features, and split scheme), not
   only leakage. Both facts go in the paper; neither excuses the other.
3. **B's 6m bump (0.597) is not evidence of skill** — single run, no
   confidence interval, sandwiched between two chance-level cells; read as
   noise until someone pre-registers a reason to believe it.
4. Consistency check: prod already treats the crash model as having no
   deployable skill (overlay disabled, `model_not_deployed`,
   NEGATIVE_RESULTS on 12m). This rerun deepens that record: the model is
   not merely unlucky live — its offline case was inflated by construction.
5. **No retraining/tuning in response to this table** without pre-registered
   changes: post-hoc fixing until AUC recovers would be exactly the process
   this project exists to prevent.
