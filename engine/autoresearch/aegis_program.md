# Aegis Autoresearch Program

## Objective

Improve the Aegis crash prediction model's composite score by modifying
`aegis_train.py` hyperparameters. The composite metric balances:

- **AUC-ROC (40%)** — discrimination power
- **Brier Score (25%)** — calibration quality (critical: poorly calibrated probs poison MC)
- **Signal Sharpe (20%)** — practical trading value of the signal
- **MaxDD Penalty (15%)** — penalizes catastrophic failures

## What You CAN Modify

Only `aegis_train.py` — specifically:

1. **LGB_PARAMS dict** — LightGBM hyperparameters:
   - `n_estimators`: [200, 2000]
   - `max_depth`: [3, 12]
   - `num_leaves`: [15, 127]
   - `learning_rate`: [0.001, 0.1]
   - `min_child_samples`: [10, 100]
   - `subsample`: [0.5, 1.0]
   - `colsample_bytree`: [0.3, 1.0]
   - `reg_alpha`: [0, 1.0]
   - `reg_lambda`: [0, 2.0]
   - `min_gain_to_split`: [0, 0.01]

2. **LGB_WEIGHT** — blend weight for LightGBM vs Logistic: [0.3, 0.9]

3. **CALIBRATION_METHOD** — "isotonic" or "platt"

4. **FEATURE_SUBSET** — list of feature names, or None for all

## What You MUST NOT Do

- Modify `aegis_prepare.py` (the evaluation function is immutable)
- Use features from the future (all features are already backward-looking)
- Skip purged CV (splits are pre-computed with embargo)
- Use fewer than 10 features
- Use a training window shorter than 5 years (1260 trading days)
- Overfit to a single fold — the score is averaged across all folds
- Report metrics from training data — only test-fold predictions count

## Strategy Guide

1. **Start with learning rate**: Try 0.003, 0.008, 0.02, 0.05
2. **Then tree complexity**: max_depth × num_leaves interaction matters
3. **Then regularization**: reg_alpha + reg_lambda prevent overfit
4. **Then subsampling**: subsample + colsample_bytree for variance reduction
5. **Feature selection**: Try dropping highly correlated features
6. **Blend weight**: Try 0.5, 0.6, 0.7, 0.8 — more LGB isn't always better
7. **Calibration**: isotonic usually wins with enough data

## Success Criteria

- Target aegis_score > 0.65 after 50 experiments
- Score std across folds < 0.05 (stable model)
- AUC-ROC ≥ 0.65 (better than random + baselines)
- Brier ≤ 0.08 (well-calibrated)

## Running

```bash
cd aegis-finance

# Single experiment
python -m engine.autoresearch.aegis_train

# Batch run (10 experiments)
python -m engine.autoresearch.aegis_train --n-experiments 10

# Check best score
cat engine/autoresearch/results/best_score.json
```
