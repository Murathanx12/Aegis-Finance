# Model card — risk_head_vol_lgbm_options v2.0.0

Built 2026-08-20T04:44:12+00:00 by
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

## Held-out performance (this artifact, years > 2021)

| arm | QLIKE | MSE(log var) | rank IC | bias |
|---|---|---|---|---|
| model (raw) | 0.55802 | 0.39635 | 0.814 | +0.08704 |
| model (calibrated) | 0.50002 | 0.38903 | 0.814 | -0.01595 |
| IV-only baseline | 0.2668 | 0.73727 | 0.753 | -0.31506 |

Calibration is an additive offset of +0.1030 in log-variance space,
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
6. **Its ranking edge does NOT convert into position-sizing value.**
   `RISK-SIZING-VALUE-1` sized books by `1/sqrt(predicted var)` against
   `1/sqrt(trailing 63d var)`, holding selection fixed: pooled
   d_ann_vol **+0.0103, ns** — the wrong sign. Cause measured: the
   model is **shrunk**, with cross-sectional dispersion of log predicted
   variance only 0.67-0.82x trailing (and below realized). Inverse-vol
   weights are driven by an estimator's SPREAD, not its ordering, so a
   well-ranked but shrunk forecast produces near-equal weights. A
   rank-preserving quantile map fixes the shrinkage (POWERED, -0.0084
   vol vs uncorrected) and still does not beat trailing. **Anyone using
   this model for weights, rather than for ranking or for a level
   estimate, must apply a dispersion correction and should expect no
   advantage over trailing vol.**

## Provenance and PIT

- Features read at the month-end close of t; target spans t+1..t+21 and
  never includes t (CHRONOLOGY-AUDIT-1 C2 PASS).
- Options joined with a measured, sign-asserted lag: 307,924 joins,
  min lag 0 days, max 30, **zero negative** — no surface postdates its
  formation date (C1 PASS). Both consumers now refuse on a negative lag
  rather than relying on the one-sided staleness filter.
- Shift-invariance: with every feature lagged one extra month the model
  degrades gracefully and all comparative conclusions hold.
- Train rows 119,094; holdout rows 63,682; features 13.

## Licence

Trained on WRDS-entitled data (CRSP, OptionMetrics). Per
`docs/DECISION_WRDS_RECEIPT_POLICY.md` the weights are publishable as a
low-parameter model over ~10^5 rows, but the training panel is **not**.
Reproduction requires the same entitlement.
