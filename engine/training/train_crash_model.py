"""
Offline Crash Model Training Script
======================================

Fetches data, builds features, runs LASSO feature selection,
trains LightGBM + Logistic Regression, and serializes the model
to backend/models/crash_model.pkl for fast inference by the API.

Supports:
    - Standard threshold labels (default)
    - Triple-barrier labels (--labels triple-barrier)
    - Fractionally differentiated features (--fracdiff)

Usage:
    cd aegis-finance
    python -m engine.training.train_crash_model
    python -m engine.training.train_crash_model --labels triple-barrier
    python -m engine.training.train_crash_model --fracdiff
"""

import sys
import logging
import argparse
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
    parser = argparse.ArgumentParser(description="Train crash prediction model")
    parser.add_argument("--labels", choices=["standard", "triple-barrier"],
                       default="standard", help="Labeling method")
    parser.add_argument("--fracdiff", action="store_true",
                       help="Add fractionally differentiated features")
    parser.add_argument("--output", type=str, default=str(MODEL_OUTPUT),
                       help="Output path for serialized model")
    args = parser.parse_args()

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

    # Optional: add fractionally differentiated features (Phase 1.4)
    if args.fracdiff:
        try:
            from engine.training.fracdiff import build_fracdiff_features
            logger.info("Step 2b: Computing fractionally differentiated features...")
            ffd_features = build_fracdiff_features(data)
            # Drop the d-value columns (metadata, not features)
            ffd_cols = [c for c in ffd_features.columns if not c.endswith("_d")]
            if ffd_cols:
                features = pd.concat([features, ffd_features[ffd_cols]], axis=1)
                features = features.replace([np.inf, -np.inf], np.nan).ffill().fillna(0)
                logger.info("Added %d fracdiff features", len(ffd_cols))
        except ImportError:
            logger.warning("fracdiff module not available, skipping")

    # ── Step 3: Build targets ───────────────────────────────────────
    logger.info("Step 3: Building crash targets (method: %s)...", args.labels)
    threshold = -config["risk"]["crash_threshold"]

    if args.labels == "triple-barrier":
        try:
            from engine.training.labeling import build_triple_barrier_multi
            crash_targets = build_triple_barrier_multi(data["SP500"])
            logger.info("Using triple-barrier labels")
        except ImportError:
            logger.warning("Triple-barrier labeling not available, falling back to standard")
            crash_targets = build_target_crash_multi(data, threshold=threshold)
    else:
        crash_targets = build_target_crash_multi(data, threshold=threshold)

    for horizon, target in crash_targets.items():
        n_valid = target.notna().sum()
        crash_rate = target.dropna().mean() * 100 if target.dropna().any() else 0
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
    output_path = Path(args.output)
    logger.info("Step 6: Saving model to %s", output_path)
    predictor.save_model(str(output_path))

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
    logger.info("Training complete. Model saved to %s", output_path)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
