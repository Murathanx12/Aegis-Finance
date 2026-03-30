"""
Aegis Autoresearch — Training Script (MUTABLE)
================================================

This file is part of the three-file autoresearch contract.
The autoresearch agent MAY modify this file to improve performance.

Modifiable parameters:
  - LightGBM hyperparameters
  - Feature subset selection
  - Ensemble weights (LightGBM vs Logistic)
  - Calibration method

Usage:
    python -m engine.autoresearch.aegis_train
    python -m engine.autoresearch.aegis_train --n-experiments 50
"""

import sys
import logging
import argparse
import json
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

RESULTS_DIR = Path("engine/autoresearch/results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
BEST_SCORE_FILE = RESULTS_DIR / "best_score.json"

# ══════════════════════════════════════════════════════════════════════════════
# MUTABLE CONFIGURATION — agent modifies these
# ══════════════════════════════════════════════════════════════════════════════

LGB_PARAMS = {
    "objective": "binary",
    "metric": "binary_logloss",
    "n_estimators": 800,
    "max_depth": 7,
    "num_leaves": 40,
    "learning_rate": 0.008,
    "min_child_samples": 30,
    "subsample": 0.75,
    "colsample_bytree": 0.65,
    "reg_alpha": 0.05,
    "reg_lambda": 0.5,
    "min_gain_to_split": 0.002,
    "random_state": 42,
    "verbose": -1,
    "n_jobs": -1,
}

LGB_WEIGHT = 0.70  # Blend weight for LightGBM (rest goes to Logistic)
CALIBRATION_METHOD = "isotonic"  # "isotonic" or "platt"
FEATURE_SUBSET = None  # None = use all selected features, or list of feature names


def get_config() -> dict:
    """Return current training configuration (for logging)."""
    return {
        "lgb_params": LGB_PARAMS,
        "lgb_weight": LGB_WEIGHT,
        "calibration": CALIBRATION_METHOD,
        "feature_subset": FEATURE_SUBSET,
    }


# ══════════════════════════════════════════════════════════════════════════════
# TRAINING LOOP
# ══════════════════════════════════════════════════════════════════════════════


def train_and_evaluate(data: dict, horizon: str = "3m") -> dict:
    """Train a model on purged CV splits and evaluate with composite metric.

    Args:
        data: Output from aegis_prepare.prepare_data()
        horizon: Which horizon to optimize for

    Returns:
        dict with metrics and config
    """
    try:
        import lightgbm as lgb
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
        from sklearn.isotonic import IsotonicRegression
    except ImportError as e:
        return {"success": False, "reason": str(e)}

    from engine.autoresearch.aegis_prepare import evaluate

    splits_info = data["splits"].get(horizon)
    if splits_info is None:
        return {"success": False, "reason": f"No splits for horizon {horizon}"}

    X_all = splits_info["X"]
    y_all = splits_info["y"]

    # Optional feature subset
    if FEATURE_SUBSET is not None:
        available = [f for f in FEATURE_SUBSET if f in X_all.columns]
        if len(available) >= 10:
            X_all = X_all[available]

    all_y_true = []
    all_y_pred = []
    fold_metrics = []

    for fold_info in splits_info["folds"]:
        train_idx = fold_info["train_idx"]
        test_idx = fold_info["test_idx"]

        X_train = X_all.iloc[train_idx]
        y_train = y_all.iloc[train_idx]
        X_test = X_all.iloc[test_idx]
        y_test = y_all.iloc[test_idx]

        if y_train.nunique() < 2 or y_test.nunique() < 2:
            continue

        # Class imbalance handling
        pos_rate = float(y_train.mean())
        scale_pos = min((1 - pos_rate) / max(pos_rate, 0.01), 10.0)
        params = {**LGB_PARAMS, "scale_pos_weight": scale_pos}

        # LightGBM
        lgb_model = lgb.LGBMClassifier(**params)
        lgb_model.fit(X_train, y_train.astype(int))
        lgb_raw = lgb_model.predict_proba(X_test)[:, 1]

        # Logistic Regression
        scaler = StandardScaler()
        X_train_sc = scaler.fit_transform(X_train.fillna(0))
        X_test_sc = scaler.transform(X_test.fillna(0))

        lr_model = LogisticRegression(
            penalty="l2", C=0.1, class_weight="balanced",
            max_iter=2000, random_state=42,
        )
        lr_model.fit(X_train_sc, y_train.astype(int))
        lr_raw = lr_model.predict_proba(X_test_sc)[:, 1]

        # Blend
        blended = LGB_WEIGHT * lgb_raw + (1 - LGB_WEIGHT) * lr_raw

        # Calibration (using train set as calibration set — imperfect but workable)
        lgb_cal_raw = lgb_model.predict_proba(X_train)[:, 1]
        lr_cal_raw = lr_model.predict_proba(X_train_sc)[:, 1]
        cal_blended = LGB_WEIGHT * lgb_cal_raw + (1 - LGB_WEIGHT) * lr_cal_raw

        if CALIBRATION_METHOD == "isotonic":
            calibrator = IsotonicRegression(y_min=0.01, y_max=0.99, out_of_bounds="clip")
            calibrator.fit(cal_blended, y_train.astype(int).values)
            y_pred = calibrator.predict(blended)
        else:
            y_pred = blended

        y_pred = np.clip(y_pred, 0.02, 0.98)

        all_y_true.extend(y_test.values)
        all_y_pred.extend(y_pred)

        # Per-fold metrics
        fold_result = evaluate(y_test.values, y_pred)
        fold_metrics.append(fold_result)

    if not all_y_true:
        return {"success": False, "reason": "No valid folds"}

    # Aggregate metrics across folds
    overall = evaluate(np.array(all_y_true), np.array(all_y_pred))
    overall["n_folds"] = len(fold_metrics)
    overall["fold_scores"] = [fm["aegis_score"] for fm in fold_metrics]
    overall["score_std"] = float(np.std(overall["fold_scores"]))
    overall["config"] = get_config()
    overall["success"] = True
    overall["horizon"] = horizon

    return overall


def run_experiment(data: dict, experiment_id: int) -> dict:
    """Run a single experiment and check against best score (ratchet pattern).

    The ratchet: only save the model if it beats the previous best.
    """
    logger.info("=" * 50)
    logger.info("Experiment %d", experiment_id)
    logger.info("=" * 50)

    result = train_and_evaluate(data, horizon="3m")

    if not result.get("success"):
        logger.warning("Experiment %d failed: %s", experiment_id, result.get("reason"))
        return result

    score = result["aegis_score"]
    logger.info(
        "Experiment %d: score=%.4f  AUC=%.3f  Brier=%.4f  Sharpe=%.3f",
        experiment_id, score, result["auc_roc"],
        result["brier_score"], result["signal_sharpe"],
    )

    # Ratchet: check against best
    best_score = _load_best_score()
    if score > best_score:
        logger.info("NEW BEST: %.4f > %.4f (improvement: +%.4f)",
                     score, best_score, score - best_score)
        _save_best_score(score, result)
        result["is_new_best"] = True
    else:
        logger.info("Score %.4f did not beat best %.4f", score, best_score)
        result["is_new_best"] = False

    # Save experiment log
    log_file = RESULTS_DIR / f"experiment_{experiment_id:04d}.json"
    with open(log_file, "w") as f:
        json.dump({k: v for k, v in result.items()
                   if k != "config" or isinstance(v, (str, int, float, bool, list, dict))},
                  f, indent=2, default=str)

    return result


def _load_best_score() -> float:
    """Load the current best score from disk."""
    if BEST_SCORE_FILE.exists():
        with open(BEST_SCORE_FILE) as f:
            data = json.load(f)
            return data.get("score", 0.0)
    return 0.0


def _save_best_score(score: float, result: dict) -> None:
    """Save new best score to disk."""
    with open(BEST_SCORE_FILE, "w") as f:
        json.dump({
            "score": score,
            "auc_roc": result["auc_roc"],
            "brier_score": result["brier_score"],
            "signal_sharpe": result["signal_sharpe"],
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Aegis autoresearch training loop")
    parser.add_argument("--n-experiments", type=int, default=1,
                       help="Number of experiments to run")
    parser.add_argument("--horizon", default="3m",
                       choices=["3m", "6m", "12m"],
                       help="Optimization horizon")
    args = parser.parse_args()

    logger.info("Aegis Autoresearch — Training Loop")
    logger.info("Experiments: %d, Horizon: %s", args.n_experiments, args.horizon)

    # Prepare data (immutable step)
    from engine.autoresearch.aegis_prepare import prepare_data
    data = prepare_data()

    results = []
    for i in range(args.n_experiments):
        result = run_experiment(data, experiment_id=i + 1)
        results.append(result)

    # Summary
    scores = [r["aegis_score"] for r in results if r.get("success")]
    if scores:
        logger.info("\n" + "=" * 50)
        logger.info("SUMMARY: %d experiments", len(scores))
        logger.info("  Best:  %.4f", max(scores))
        logger.info("  Mean:  %.4f", np.mean(scores))
        logger.info("  Std:   %.4f", np.std(scores))
        logger.info("=" * 50)


if __name__ == "__main__":
    main()
