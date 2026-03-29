"""
Offline Crash Model Training Script
======================================

Fetches data, builds features, runs LASSO feature selection,
trains LightGBM + Logistic Regression, and serializes the model
to backend/models/crash_model.pkl for fast inference by the API.

Usage:
    cd aegis-finance
    python -m engine.training.train_crash_model
"""

import sys
import logging
from pathlib import Path

# Add project root to path
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

MODEL_OUTPUT = Path("backend/models/crash_model.pkl")


def main():
    logger.info("=" * 60)
    logger.info("AEGIS FINANCE — Crash Model Training")
    logger.info("=" * 60)

    # ── Step 1: Fetch data ──────────────────────────────────────────
    logger.info("Step 1: Fetching market data...")
    fetcher = DataFetcher()
    data, sector_data = fetcher.fetch_market_data()
    fred_data = fetcher.fetch_fred_data()
    logger.info(
        "Data: %d rows, %d columns, range %s to %s",
        len(data), len(data.columns),
        data.index[0].date(), data.index[-1].date(),
    )

    # ── Step 2: Build features ──────────────────────────────────────
    logger.info("Step 2: Building feature matrix...")
    features = build_feature_matrix(data, fred_data=fred_data)
    logger.info("Built %d features", len(features.columns))

    # ── Step 3: Build targets ───────────────────────────────────────
    logger.info("Step 3: Building crash targets...")
    threshold = -config["risk"]["crash_threshold"]
    crash_targets = build_target_crash_multi(data, threshold=threshold)
    for horizon, target in crash_targets.items():
        n_valid = target.notna().sum()
        crash_rate = target.dropna().mean() * 100
        logger.info(
            "  %s: %d valid samples, %.1f%% crash rate",
            horizon, n_valid, crash_rate,
        )

    # ── Step 4: Feature selection ───────────────────────────────────
    logger.info("Step 4: Running LASSO feature selection...")
    primary_target = crash_targets["3m"]  # Optimize for 3-month prediction

    try:
        selected = select_features(
            features,
            primary_target,
            max_features=30,
            min_features=20,
        )
        logger.info("Selected %d features via LASSO", len(selected))
    except Exception as e:
        logger.warning("Feature selection failed (%s), using defaults", e)
        # Use default features, filtered to what actually exists
        selected = [f for f in SELECTED_FEATURES if f in features.columns]
        logger.info("Using %d default features", len(selected))

    if len(selected) < 10:
        logger.warning("Too few features selected, falling back to defaults")
        selected = [f for f in SELECTED_FEATURES if f in features.columns]

    features_selected = features[selected]

    # ── Step 5: Train model ─────────────────────────────────────────
    logger.info("Step 5: Training LightGBM + Logistic Regression...")
    predictor = CrashPredictor(n_estimators=800, random_state=42)

    results = predictor.train(
        features_selected,
        crash_targets,
        min_train_samples=252 * 5,
    )

    logger.info("Training results:")
    for horizon, r in results.items():
        if isinstance(r, dict):
            if r.get("success"):
                logger.info(
                    "  %s: Brier=%.4f, AUC=%.3f, range=%s",
                    horizon,
                    r.get("val_brier", -1),
                    r.get("val_auc", -1),
                    r.get("pred_range", "N/A"),
                )
            else:
                logger.warning("  %s: FAILED — %s", horizon, r.get("reason"))

    # ── Step 6: Save model ──────────────────────────────────────────
    logger.info("Step 6: Saving model to %s", MODEL_OUTPUT)
    predictor.save_model(str(MODEL_OUTPUT))

    # ── Step 7: Validation smoke test ───────────────────────────────
    logger.info("Step 7: Smoke test — predicting on latest data...")
    latest_features = features_selected.iloc[[-1]]
    for horizon in predictor.lgb_models:
        prob = predictor.predict_proba(latest_features, horizon)[0]
        logger.info("  Current %s crash probability: %.1f%%", horizon, prob * 100)

    # Print top features
    logger.info("\nTop 15 features by importance:")
    for feat, imp in predictor.get_top_features(15):
        logger.info("  %-35s %.4f", feat, imp)

    logger.info("\n" + "=" * 60)
    logger.info("Training complete. Model saved to %s", MODEL_OUTPUT)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
