"""
Automated Retraining with Model Versioning
=============================================

Wrapper around train_crash_model that:
  1. Trains a new model on the latest data
  2. Compares it to the currently deployed model on a recent holdout
  3. Only deploys the new model if it improves Brier score by > threshold
  4. Logs every run to training_log.csv for auditing

Usage:
    cd aegis-finance
    python -m engine.training.retrain
    python -m engine.training.retrain --force   # deploy even if worse
"""

import sys
import csv
import logging
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd

from backend.config import config
from backend.services.data_fetcher import DataFetcher
from backend.services.crash_model import CrashPredictor
from engine.training.features import build_feature_matrix, build_target_crash_multi
from engine.training.feature_selection import select_features, SELECTED_FEATURES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

MODEL_DIR = Path("backend/models")
DEPLOY_PATH = MODEL_DIR / "crash_model.pkl"
LOG_PATH = Path("engine/training/training_log.csv")
IMPROVEMENT_THRESHOLD = 0.001  # Brier score must improve by at least this


def _evaluate_on_holdout(
    predictor: CrashPredictor,
    features: pd.DataFrame,
    targets: dict,
    holdout_size: int = 504,
) -> dict:
    """Evaluate a trained model on the most recent holdout_size rows."""
    from sklearn.metrics import brier_score_loss, roc_auc_score

    results = {}
    for horizon in ["3m", "6m", "12m"]:
        if horizon not in predictor.lgb_models:
            continue

        X_hold = features.iloc[-holdout_size:]
        y_hold = targets[horizon].iloc[-holdout_size:]

        valid = y_hold.notna()
        X_v = X_hold[valid]
        y_v = y_hold[valid].astype(int)

        if len(y_v) < 50 or y_v.nunique() < 2:
            continue

        probs = predictor.predict_proba(X_v, horizon)
        brier = float(brier_score_loss(y_v, probs))
        try:
            auc = float(roc_auc_score(y_v, probs))
        except ValueError:
            auc = 0.5

        results[horizon] = {"brier": brier, "auc": auc, "n": len(y_v)}

    return results


def _log_run(
    timestamp: str,
    action: str,
    new_brier: float,
    old_brier: float,
    model_path: str,
    note: str = "",
) -> None:
    """Append one row to training_log.csv."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_header = not LOG_PATH.exists()

    with open(LOG_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow([
                "timestamp", "action", "new_brier_3m", "old_brier_3m",
                "improvement", "model_path", "note",
            ])
        writer.writerow([
            timestamp, action, f"{new_brier:.6f}", f"{old_brier:.6f}",
            f"{old_brier - new_brier:.6f}", model_path, note,
        ])


def retrain(force: bool = False) -> dict:
    """Run full retraining pipeline with versioning.

    Returns dict with training outcome details.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.info("=" * 60)
    logger.info("AEGIS FINANCE — Automated Retraining (%s)", timestamp)
    logger.info("=" * 60)

    # ── Fetch data ────────────────────────────────────────────────
    logger.info("Fetching market data...")
    fetcher = DataFetcher()
    data, _ = fetcher.fetch_market_data()
    fred_data = fetcher.fetch_fred_data()

    # ── Build features + targets ──────────────────────────────────
    logger.info("Building features...")
    features = build_feature_matrix(data, fred_data=fred_data)
    threshold = -config["risk"]["crash_threshold"]
    crash_targets = build_target_crash_multi(data, threshold=threshold)

    # ── Feature selection ─────────────────────────────────────────
    logger.info("Running feature selection...")
    primary_target = crash_targets["3m"]
    try:
        selected = select_features(features, primary_target, max_features=30, min_features=20)
    except Exception as e:
        logger.warning("Feature selection failed (%s), using defaults", e)
        selected = [f for f in SELECTED_FEATURES if f in features.columns]

    if len(selected) < 10:
        selected = [f for f in SELECTED_FEATURES if f in features.columns]

    features_sel = features[selected]

    # ── Train new model ───────────────────────────────────────────
    logger.info("Training new model...")
    new_model = CrashPredictor(n_estimators=800, random_state=42)
    new_model.train(features_sel, crash_targets, min_train_samples=252 * 5)

    if not new_model.is_trained:
        logger.error("New model training failed")
        return {"deployed": False, "reason": "training_failed"}

    # ── Evaluate new model on holdout ─────────────────────────────
    new_metrics = _evaluate_on_holdout(new_model, features_sel, crash_targets)
    new_brier = new_metrics.get("3m", {}).get("brier", 1.0)
    logger.info("New model 3m Brier: %.4f", new_brier)

    # ── Compare to existing model ─────────────────────────────────
    old_brier = 1.0
    if DEPLOY_PATH.exists():
        logger.info("Loading existing deployed model for comparison...")
        try:
            old_model = CrashPredictor()
            old_model.load_model(str(DEPLOY_PATH))

            # Re-select features that old model knows
            old_features = features[[f for f in old_model.feature_names if f in features.columns]]
            old_metrics = _evaluate_on_holdout(old_model, old_features, crash_targets)
            old_brier = old_metrics.get("3m", {}).get("brier", 1.0)
            logger.info("Old model 3m Brier: %.4f", old_brier)
        except Exception as e:
            logger.warning("Could not evaluate old model: %s", e)
            old_brier = 1.0
    else:
        logger.info("No existing model — will deploy unconditionally")

    # ── Deploy decision ───────────────────────────────────────────
    improvement = old_brier - new_brier
    logger.info("Brier improvement: %.4f", improvement)

    # Save versioned copy regardless
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    versioned_path = MODEL_DIR / f"crash_model_{timestamp}.pkl"
    new_model.save_model(str(versioned_path))
    logger.info("Versioned model saved: %s", versioned_path)

    deploy = force or (improvement > IMPROVEMENT_THRESHOLD) or not DEPLOY_PATH.exists()

    if deploy:
        new_model.save_model(str(DEPLOY_PATH))
        action = "deployed_force" if force and improvement <= IMPROVEMENT_THRESHOLD else "deployed"
        logger.info("Model DEPLOYED to %s", DEPLOY_PATH)
    else:
        action = "skipped"
        logger.info(
            "Model NOT deployed (improvement %.4f < threshold %.4f)",
            improvement, IMPROVEMENT_THRESHOLD,
        )

    _log_run(timestamp, action, new_brier, old_brier, str(versioned_path))

    # ── Cleanup old versions (keep last 3) ────────────────────────
    versioned = sorted(MODEL_DIR.glob("crash_model_*.pkl"), reverse=True)
    for old_file in versioned[3:]:
        old_file.unlink()
        logger.info("Cleaned up old version: %s", old_file.name)

    return {
        "deployed": deploy,
        "action": action,
        "new_brier": new_brier,
        "old_brier": old_brier,
        "improvement": improvement,
        "versioned_path": str(versioned_path),
        "new_metrics": new_metrics,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aegis Finance — Automated Retraining")
    parser.add_argument("--force", action="store_true", help="Deploy even if not better")
    args = parser.parse_args()

    result = retrain(force=args.force)

    print("\n" + "=" * 60)
    print("RETRAINING RESULT")
    print("=" * 60)
    print(f"  Action:      {result['action']}")
    print(f"  New Brier:   {result['new_brier']:.4f}")
    print(f"  Old Brier:   {result['old_brier']:.4f}")
    print(f"  Improvement: {result['improvement']:.4f}")
    print(f"  Deployed:    {result['deployed']}")
    print(f"  Saved to:    {result['versioned_path']}")
