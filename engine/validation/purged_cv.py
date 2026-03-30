"""
Purged K-Fold Cross-Validation with Embargo
=============================================

Implements purged CV for time-series ML validation, adapted from
Lopez de Prado (Advances in Financial Machine Learning, Ch. 7).

Key idea: when labels have forward-looking windows (e.g., "does a crash
occur in the next 3 months?"), naive k-fold leaks future information
because training samples near the test boundary have overlapping
forward windows. Purging removes these contaminated samples, and
the embargo period adds an additional safety buffer.

Reference: mlfinlab/cross_validation/cross_validation.py (structure)

Usage:
    from engine.validation.purged_cv import PurgedKFold
    cv = PurgedKFold(n_splits=5, embargo_pct=0.01)
    for train_idx, test_idx in cv.split(X, y, pred_times, eval_times):
        model.fit(X[train_idx], y[train_idx])
        model.predict(X[test_idx])
"""

import numpy as np
import pandas as pd
from typing import Optional


class PurgedKFold:
    """K-Fold cross-validation with purging and embargo for time-series.

    For each fold:
        1. Split data into k temporal folds (ordered by time)
        2. For each test fold, PURGE any training samples whose
           forward-looking label window overlaps with the test period
        3. Apply EMBARGO: remove additional training samples after
           each test fold boundary to prevent information leakage
           from serial correlation

    Args:
        n_splits: Number of folds (default 5)
        embargo_td: Embargo period in trading days. If None, uses embargo_pct.
        embargo_pct: Fraction of total samples to embargo (default 0.01 = 1%)
    """

    def __init__(
        self,
        n_splits: int = 5,
        embargo_td: Optional[int] = None,
        embargo_pct: float = 0.01,
    ):
        self.n_splits = n_splits
        self.embargo_td = embargo_td
        self.embargo_pct = embargo_pct

    def split(
        self,
        X: pd.DataFrame,
        y: Optional[pd.Series] = None,
        pred_times: Optional[pd.Series] = None,
        eval_times: Optional[pd.Series] = None,
    ):
        """Generate purged train/test indices.

        Args:
            X: Feature matrix with DatetimeIndex
            y: Target series (unused, for sklearn compatibility)
            pred_times: Series mapping each sample index to its prediction time
                       (when the prediction is made). If None, uses X.index.
            eval_times: Series mapping each sample index to the end of its
                       forward-looking evaluation window. This is critical —
                       it tells us which training samples could leak into test.
                       If None, no purging is applied (falls back to standard k-fold).

        Yields:
            (train_indices, test_indices) as integer arrays
        """
        n_samples = len(X)
        if n_samples < self.n_splits:
            raise ValueError(f"Cannot split {n_samples} samples into {self.n_splits} folds")

        # Compute embargo size
        if self.embargo_td is not None:
            embargo = self.embargo_td
        else:
            embargo = int(n_samples * self.embargo_pct)

        # Create temporal folds (ordered by index position)
        indices = np.arange(n_samples)
        fold_sizes = np.full(self.n_splits, n_samples // self.n_splits, dtype=int)
        fold_sizes[:n_samples % self.n_splits] += 1
        fold_starts = np.cumsum(np.r_[0, fold_sizes])

        for fold in range(self.n_splits):
            test_start = fold_starts[fold]
            test_end = fold_starts[fold + 1]
            test_idx = indices[test_start:test_end]

            # Start with all non-test indices as training candidates
            train_mask = np.ones(n_samples, dtype=bool)
            train_mask[test_start:test_end] = False

            # PURGE: remove training samples whose eval window overlaps test
            if eval_times is not None and len(eval_times) == n_samples:
                test_start_time = X.index[test_start]
                test_end_time = X.index[min(test_end - 1, n_samples - 1)]

                for i in range(n_samples):
                    if not train_mask[i]:
                        continue
                    # If this training sample's evaluation window extends
                    # into or past the test period, purge it
                    if eval_times.iloc[i] >= test_start_time:
                        # Only purge if the sample is BEFORE the test set
                        if X.index[i] < test_start_time:
                            train_mask[i] = False

            # PRE-EMBARGO: remove training samples immediately before test set
            # This prevents information leakage from serial correlation
            pre_embargo_start = max(0, test_start - embargo)
            train_mask[pre_embargo_start:test_start] = False

            # POST-EMBARGO: remove training samples immediately after test set
            embargo_end = min(test_end + embargo, n_samples)
            train_mask[test_end:embargo_end] = False

            train_idx = indices[train_mask]

            if len(train_idx) < 10:
                continue

            yield train_idx, test_idx

    def get_n_splits(self):
        return self.n_splits


def compute_eval_times(
    index: pd.DatetimeIndex,
    horizon_days: int,
) -> pd.Series:
    """Compute evaluation end times for each sample.

    For crash prediction with a 3-month horizon, each sample at time t
    has a forward-looking window [t, t + 63 trading days]. The eval_time
    is t + 63 days.

    Args:
        index: DatetimeIndex of the feature matrix
        horizon_days: Forward-looking window in trading days (63=3m, 126=6m, 252=12m)

    Returns:
        Series of eval end times, indexed like the feature matrix
    """
    n = len(index)
    eval_times = pd.Series(index=index, dtype="datetime64[ns]")
    for i in range(n):
        end_idx = min(i + horizon_days, n - 1)
        eval_times.iloc[i] = index[end_idx]
    return eval_times


def purged_train_test_split(
    X: pd.DataFrame,
    y: pd.Series,
    test_size: float = 0.20,
    embargo_td: int = 21,
    horizon_days: int = 63,
) -> tuple:
    """Single purged train/test split for quick validation.

    Simpler than full PurgedKFold — just one temporal split with purging.

    Args:
        X: Feature matrix with DatetimeIndex
        y: Target series
        test_size: Fraction of data for test set (from the end)
        embargo_td: Embargo period in trading days
        horizon_days: Forward-looking window for label computation

    Returns:
        (X_train, X_test, y_train, y_test) with purging applied
    """
    n = len(X)
    test_start = int(n * (1 - test_size))

    # Test set: last test_size fraction
    X_test = X.iloc[test_start:]
    y_test = y.iloc[test_start:]

    # Training set: everything before, minus purged + embargoed samples
    test_start_time = X.index[test_start]

    # Purge: remove training samples whose forward window reaches test set
    purge_start = test_start - horizon_days
    purge_start = max(0, purge_start)

    # Embargo: additional buffer after purge boundary
    effective_end = purge_start - embargo_td
    effective_end = max(0, effective_end)

    X_train = X.iloc[:effective_end]
    y_train = y.iloc[:effective_end]

    return X_train, X_test, y_train, y_test


# Embargo periods per horizon (trading days)
EMBARGO_PERIODS = {
    "3m": 21,   # 1 month
    "6m": 63,   # 3 months
    "12m": 126, # 6 months
}

# Forward-looking windows per horizon
HORIZON_DAYS = {
    "3m": 63,
    "6m": 126,
    "12m": 252,
}
