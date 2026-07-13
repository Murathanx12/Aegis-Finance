# TRIAL-CRASH-2 — Drawdown-severity (exceedance) model

**Pre-registered:** 2026-07-14 (commit `fe6edf3`) · **Purpose:** experimental · **Status:** ⛔ **CONCLUDED — REJECT (2026-07-14)**

> **Result (single evaluation run, protocol unmodified):** 0/6 dense cells
> passed the gate. All dense cells show negative Brier skill vs climatology
> (5% cells −0.32 to −0.54 — systematic over-prediction out-of-distribution);
> STLFSI4 itself barely beats climatology. Reported-not-deciding: the 10%
> cells show ranking signal (PR-AUC up to ~3.6× prevalence at 30d) with
> unusable calibration. The model stays dark; overlay stays
> `model_not_deployed`. Published as NEGATIVE_RESULTS §7. Any
> calibration-on-top-of-ranker attempt = a NEW trial (TRIAL-CRASH-3), not a
> rerun. Full metrics: `engine/training/output/crash2_eval_2026-07-14.json`.
**Canonical decision rule:** mirrored in the experiment registry notes (param `crash2-severity-model`) and `backend/services/portfolio_intelligence/fragility.py::CRASH2_DECISION_RULE`.
**Successor to:** the held M3 binary crash model (NEGATIVE_RESULTS §6 — binary ≥20%-drawdown label unlearnable: AUC unmeasurable, near-constant outputs). Design per `docs/research/CRASH_AND_OSS_RESEARCH_2026-07-11.md` P2 (BIS WP 1250 target design).

## Why this is pre-registered before the first fit

The M3 failure taught that with rare-event labels, any post-hoc metric choice
can be made to look like skill. This trial commits the target, folds,
baselines, metrics, and adopt/reject gate **before any model is trained**, so
the offline verdict cannot be reverse-engineered. The git timestamp of this
file is the tamper evidence.

## Hypothesis

A LightGBM model of forward SPY max-drawdown severity, read out as exceedance
probabilities P(maxDD ≥ x within h), can beat BOTH climatology and an
STLFSI4-only baseline on held-out walk-forward folds at the **dense cells**
(x ∈ {5%, 10%} × h ∈ {30, 60, 90d}), with structurally monotone exceedance
curves.

**Prior (honest):** dense cells plausibly learnable (BIS WP 1250 line of
evidence: tree ensembles beat linear on tail stress distributions). The sparse
headline cells (15%, 20%) are expected to remain statistically unresolvable
offline — canon A5 (crash-*timing* skill ≈ 0) is NOT being challenged. A
partial result (dense cells pass, sparse cells inconclusive) is the expected
outcome and is what the gate below is written for.

## Frozen protocol (may not be tuned after the first fit)

- **Outcome:** forward max drawdown from the reading date:
  `maxDD(t, h) = min(close[t+1 .. t+h]) / close[t] − 1` on SPY daily closes
  (same "from the reading date" convention as TRIAL-LPPLS).
- **Cells:** thresholds x ∈ {5, 10, 15, 20%} × horizons h ∈ {30, 60, 90
  calendar days} (converted to trading days ≈ {21, 42, 63}).
- **Model:** one LightGBM binary classifier per cell (the ordinal/exceedance
  readout), shared fixed hyperparameters: n_estimators=400, learning_rate=0.05,
  max_depth=4, min_child_samples=100, deterministic, seed=42. NO per-cell
  hyperparameter tuning, NO feature selection tuned on validation folds.
- **Features:** the existing crash-model feature matrix
  (`engine.training.features.build_feature_matrix`, ~86 features) as of commit
  time, plus nothing else. LightGBM handles NaN natively (house rule).
- **Monotonicity:** after prediction, enforce P(≥5%) ≥ P(≥10%) ≥ P(≥15%) ≥
  P(≥20%) (cumulative min across thresholds) and P(x,30d) ≤ P(x,60d) ≤
  P(x,90d) (cumulative max across horizons). Enforcement is part of the model
  under evaluation, not a post-hoc fix.
- **Folds:** expanding walk-forward, 5 validation folds over the final ~10
  years, with **purge = 63 trading days** (max label span) plus **embargo = 21
  trading days** between train end and validation start. No sample whose label
  window overlaps the validation period may appear in training.
- **Baselines (both must be beaten):**
  1. *Climatology:* the train-fold base rate of the cell, predicted constantly.
  2. *STLFSI4-as-predictor:* a single-feature logistic regression on the
     latest available STLFSI4 level (FRED, lagged to publication), fit on the
     same train folds. This is "just use the Fed's free stress index" — if we
     can't beat it, we ship nothing.

## Primary metric + decision rule

- **Primary (deciding):** held-out **Brier skill score** per cell:
  `skill = 1 − brier_model / brier_baseline`, computed against each baseline.
- **ADOPT (model may surface as descriptive exceedance curves):** skill > 0
  vs BOTH baselines on ALL SIX dense cells ({5%, 10%} × {30, 60, 90d}),
  pooled across the 5 folds.
- **REJECT (stays dark, published in NEGATIVE_RESULTS):** anything less.
- **Reported, never deciding:** PR-AUC per cell (vs prevalence), event-window
  hit/false-alarm table (30/60d lead before each ≥10% episode in the
  validation years), reliability diagrams, sparse-cell (15/20%) results.
- **One evaluation run.** The trainer runs once against this protocol; if the
  result motivates protocol changes, this trial is recorded as concluded and a
  successor (TRIAL-CRASH-3) must be registered. Bug fixes that do not change
  the protocol (e.g. a label-alignment error) are permitted with the rerun
  noted in this file.
- **Forward phase (only if adopted):** daily persisted exceedance readings;
  forward Brier per cell reported `insufficient_forward_data` until ≥30
  matured observations; adoption **as a signal** (anything lane-adjacent) is a
  separate registry trial.

## What this rule may NOT do

- May NOT arm a lane, size a position, or emit buy/sell language — ever.
  There is no code path from this model to a trade.
- May NOT substitute metrics, drop a baseline, re-pick folds, or move
  thresholds after the first fit.
- May NOT claim skill from the offline result alone — offline pass means
  "earned a descriptive UI surface and a forward clock," nothing more. No
  skill claims before the standing 24-month bar, and survivor-only-data
  caveats (T7) apply to any equity-universe extension.
- Crash-event override: if SPY enters a ≥20% drawdown during the forward
  phase, forward-phase decisions defer to ≥6 months past the trough.
- Contamination clause: a discovered data defect (label misalignment, feature
  leakage, stale FRED reads) voids the affected cells and is disclosed here.
