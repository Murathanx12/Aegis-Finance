"""
Aegis Autoresearch — Data Preparation (IMMUTABLE)
===================================================

This file is part of the three-file autoresearch contract.
It MUST NOT be modified by the training agent.

Responsibilities:
  1. Fetch and cache market data
  2. Build feature matrix
  3. Build crash target labels
  4. Create purged walk-forward splits
  5. Define the evaluation function (composite metric)

Usage:
    python -m engine.autoresearch.aegis_prepare
"""

import sys
import logging
import hashlib
import json
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd

from backend.config import config
from backend.services.data_fetcher import DataFetcher
from engine.training.features import build_feature_matrix, build_target_crash_multi
from engine.training.feature_selection import select_features, SELECTED_FEATURES
from engine.validation.purged_cv import PurgedKFold, HORIZON_DAYS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

CACHE_DIR = Path("engine/autoresearch/.cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def prepare_data(
    use_fracdiff: bool = False,
    use_triple_barrier: bool = False,
) -> dict:
    """Fetch data, build features and targets, create splits.

    Returns:
        dict with keys: features, targets, splits, feature_names, metadata
    """
    # ── Step 1: Fetch data ──────────────────────────────────────
    logger.info("Fetching market data...")
    fetcher = DataFetcher()
    data, sector_data = fetcher.fetch_market_data()
    fred_data = fetcher.fetch_fred_data()
    logger.info("Data: %d rows, range %s to %s",
                len(data), data.index[0].date(), data.index[-1].date())

    # ── Step 2: Build features ──────────────────────────────────
    logger.info("Building feature matrix...")
    features = build_feature_matrix(data, fred_data=fred_data)

    if use_fracdiff:
        try:
            from engine.training.fracdiff import build_fracdiff_features
            ffd = build_fracdiff_features(data)
            ffd_cols = [c for c in ffd.columns if not c.endswith("_d")]
            if ffd_cols:
                features = pd.concat([features, ffd[ffd_cols]], axis=1)
                features = features.replace([np.inf, -np.inf], np.nan).ffill().fillna(0)
                logger.info("Added %d fracdiff features", len(ffd_cols))
        except ImportError:
            logger.warning("fracdiff not available, skipping")

    # ── Step 3: Build targets ───────────────────────────────────
    logger.info("Building crash targets...")
    threshold = -config["risk"]["crash_threshold"]

    if use_triple_barrier:
        try:
            from engine.training.labeling import build_triple_barrier_multi
            targets = build_triple_barrier_multi(data["SP500"])
            logger.info("Using triple-barrier labels")
        except ImportError:
            targets = build_target_crash_multi(data, threshold=threshold)
    else:
        targets = build_target_crash_multi(data, threshold=threshold)

    # ── Step 4: Feature selection ───────────────────────────────
    logger.info("Running feature selection...")
    primary_target = targets["3m"]
    try:
        selected = select_features(features, primary_target, max_features=30, min_features=20)
    except Exception:
        selected = [f for f in SELECTED_FEATURES if f in features.columns]

    if len(selected) < 10:
        selected = [f for f in SELECTED_FEATURES if f in features.columns]

    features_selected = features[selected]
    logger.info("Selected %d features", len(selected))

    # ── Step 5: Create purged walk-forward splits ───────────────
    logger.info("Creating purged CV splits...")
    splits = {}
    for horizon in ["3m", "6m", "12m"]:
        target = targets[horizon]
        valid = target.notna() & features_selected.notna().any(axis=1)
        X_valid = features_selected[valid]
        y_valid = target[valid]

        h_days = HORIZON_DAYS.get(horizon, 63)
        cv = PurgedKFold(n_splits=5, embargo_pct=0.01, horizon_days=h_days)

        horizon_splits = []
        for fold, (train_idx, test_idx) in enumerate(cv.split(X_valid)):
            horizon_splits.append({
                "fold": fold,
                "train_idx": train_idx,
                "test_idx": test_idx,
                "n_train": len(train_idx),
                "n_test": len(test_idx),
            })
        splits[horizon] = {
            "folds": horizon_splits,
            "X": X_valid,
            "y": y_valid,
        }

    # ── Step 6: Reserve holdout ─────────────────────────────────
    holdout_years = config["ml"].get("walk_forward", {}).get("holdout_years", 2)
    holdout_days = holdout_years * 252
    holdout_cutoff = len(features_selected) - holdout_days

    metadata = {
        "n_features": len(selected),
        "feature_names": selected,
        "n_samples": len(features_selected),
        "holdout_cutoff": holdout_cutoff,
        "holdout_days": holdout_days,
        "date_range": (str(features_selected.index[0].date()),
                       str(features_selected.index[-1].date())),
    }

    return {
        "features": features_selected,
        "targets": targets,
        "splits": splits,
        "metadata": metadata,
    }


def evaluate(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    returns: Optional[np.ndarray] = None,
) -> dict:
    """Compute composite evaluation metric.

    aegis_score = 0.40 * AUC + 0.25 * (1 - Brier) + 0.20 * signal_sharpe + 0.15 * (1 - MaxDD_penalty)

    Args:
        y_true: Binary crash labels
        y_pred: Predicted probabilities
        returns: Optional forward returns for signal Sharpe computation

    Returns:
        dict with individual metrics and composite score
    """
    from sklearn.metrics import brier_score_loss, roc_auc_score

    # Brier score
    brier = brier_score_loss(y_true, y_pred)

    # AUC-ROC
    try:
        auc = roc_auc_score(y_true, y_pred)
    except ValueError:
        auc = 0.5

    # Signal Sharpe (if returns provided)
    signal_sharpe = 0.0
    max_dd_penalty = 0.0
    if returns is not None and len(returns) > 0:
        # Simple strategy: reduce exposure when crash prob > median
        threshold = np.median(y_pred)
        positions = np.where(y_pred > threshold, 0.0, 1.0)  # 0 = out, 1 = in
        strategy_returns = positions * returns

        sr_mean = strategy_returns.mean()
        sr_std = strategy_returns.std()
        if sr_std > 0:
            signal_sharpe = sr_mean / sr_std * np.sqrt(252)

        # Max drawdown of signal strategy
        cumulative = (1 + strategy_returns).cumprod()
        peak = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - peak) / np.where(peak > 0, peak, 1.0)
        max_dd = abs(drawdown.min())
        # Penalize if max drawdown > 20%
        max_dd_penalty = max(0, max_dd - 0.20) * 2.0
        max_dd_penalty = min(max_dd_penalty, 1.0)

    # Composite score
    aegis_score = (
        0.40 * auc
        + 0.25 * (1 - brier)
        + 0.20 * max(0, min(1, (signal_sharpe + 1) / 4))  # Normalize Sharpe to [0,1]
        + 0.15 * (1 - max_dd_penalty)
    )

    return {
        "aegis_score": round(aegis_score, 4),
        "auc_roc": round(auc, 4),
        "brier_score": round(brier, 4),
        "signal_sharpe": round(signal_sharpe, 4),
        "max_dd_penalty": round(max_dd_penalty, 4),
    }


if __name__ == "__main__":
    result = prepare_data()
    logger.info("Preparation complete:")
    logger.info("  Features: %d", result["metadata"]["n_features"])
    logger.info("  Samples: %d", result["metadata"]["n_samples"])
    logger.info("  Date range: %s", result["metadata"]["date_range"])
    for h, s in result["splits"].items():
        logger.info("  %s: %d folds", h, len(s["folds"]))
