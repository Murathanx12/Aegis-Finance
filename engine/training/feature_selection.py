"""
Feature Selection via LASSO
=============================

Reduces 80+ (up to 208 with FRED) features to 25-30 using:
  1. Mutual information ranking (filter step)
  2. LASSO logistic regression (wrapper step)

The selected features are saved as SELECTED_FEATURES for use by
the crash model at inference time.

Usage:
    python -m engine.training.feature_selection
"""

import sys
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_selection import mutual_info_classif
from sklearn.linear_model import LogisticRegressionCV
from sklearn.preprocessing import StandardScaler

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

logger = logging.getLogger(__name__)


def select_features(
    X: pd.DataFrame,
    y: pd.Series,
    max_features: int = 30,
    min_features: int = 20,
    random_state: int = 42,
) -> list[str]:
    """Select top features using mutual information + LASSO.

    Args:
        X: Feature matrix (rows = observations, columns = features)
        y: Binary target (crash = 1, no crash = 0)
        max_features: Maximum features to select
        min_features: Minimum features to keep
        random_state: Random seed

    Returns:
        List of selected feature names
    """
    # Drop columns that are all-zero or all-NaN
    valid_cols = X.columns[X.std() > 1e-10]
    X_valid = X[valid_cols].copy()

    # Drop rows where target is NaN
    mask = y.notna()
    X_clean = X_valid[mask]
    y_clean = y[mask].astype(int)

    logger.info(
        "Feature selection: %d features, %d samples, %.1f%% crash rate",
        len(X_clean.columns),
        len(X_clean),
        y_clean.mean() * 100,
    )

    # ── Step 1: Mutual information ranking ──────────────────────────
    # Fast filter to get top candidates (2x target count)
    n_mi_candidates = min(len(X_clean.columns), max_features * 2)

    mi_scores = mutual_info_classif(
        X_clean.fillna(0),
        y_clean,
        random_state=random_state,
        n_neighbors=5,
    )

    mi_ranking = pd.Series(mi_scores, index=X_clean.columns).sort_values(
        ascending=False
    )
    top_candidates = mi_ranking.head(n_mi_candidates).index.tolist()

    logger.info(
        "MI ranking: top 10 = %s",
        list(mi_ranking.head(10).index),
    )

    # ── Step 2: LASSO logistic regression ───────────────────────────
    # Wrapper method: L1 penalty drives weak features to zero
    X_candidates = X_clean[top_candidates]

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_candidates.fillna(0))

    lasso = LogisticRegressionCV(
        penalty="l1",
        solver="saga",
        Cs=20,
        cv=5,
        max_iter=5000,
        random_state=random_state,
        scoring="neg_brier_score",
        class_weight="balanced",
    )
    lasso.fit(X_scaled, y_clean)

    # Features with non-zero coefficients survive LASSO
    coef_abs = np.abs(lasso.coef_[0])
    nonzero_mask = coef_abs > 1e-6
    lasso_survivors = [
        top_candidates[i] for i in range(len(top_candidates)) if nonzero_mask[i]
    ]

    logger.info(
        "LASSO: %d/%d features survived (non-zero coefficients)",
        len(lasso_survivors),
        len(top_candidates),
    )

    # ── Step 3: Ensure minimum count ────────────────────────────────
    if len(lasso_survivors) < min_features:
        # Add back top MI features that LASSO dropped
        for feat in top_candidates:
            if feat not in lasso_survivors:
                lasso_survivors.append(feat)
            if len(lasso_survivors) >= min_features:
                break

    # Cap at max_features
    selected = lasso_survivors[:max_features]

    logger.info("Selected %d features: %s", len(selected), selected)
    return selected


# ── Default selected features (fallback if selection hasn't been run) ────────
# These are reasonable defaults based on V7 analysis. Will be overwritten
# when feature_selection.py is run on actual data.
SELECTED_FEATURES: list[str] = [
    # Momentum
    "mom_1m", "mom_3m", "mom_6m", "mom_12m",
    # Volatility
    "vol_1m", "vol_3m", "vol_ratio_1m_3m", "vol_zscore", "vol_of_vol",
    # Drawdown
    "dist_52w_high", "max_drawdown_3m",
    # Technical
    "rsi_14d_norm", "macd_signal", "sma_200d_dev", "golden_cross",
    # Fixed income
    "term_spread", "yield_curve_inverted",
    # VIX
    "vix", "vix_zscore", "vix_change_1m",
    # Credit
    "credit_spread_proxy",
    # Cross-asset
    "gold_equity_ratio_change_3m", "small_large_change_3m",
    # Tail risk
    "max_daily_loss_63d", "neg_day_ratio_63d",
    # Interaction
    "vol_x_mom_3m", "drawdown_x_vix", "vix_x_spread",
    # FRED leading indicators
    "fred_initial_claims_zscore", "fred_nfci_zscore",
]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from engine.training.features import build_feature_matrix, build_target_crash

    # This would run on actual data when called offline
    print("Run train_crash_model.py instead — it calls feature selection.")
