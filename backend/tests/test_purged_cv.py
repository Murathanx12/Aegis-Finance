"""C7 regression tests — PurgedKFold must never silently degrade to k-fold.

History (2026-08-04): engine/autoresearch/aegis_prepare.py passed a
nonexistent ``horizon_days=`` kwarg to PurgedKFold (TypeError — the path had
never run), and PurgedKFold.split() without eval_times silently fell back to
UNPURGED standard k-fold. Both silent paths now raise; these tests pin that.
"""

import numpy as np
import pandas as pd
import pytest

from engine.validation.purged_cv import PurgedKFold, compute_eval_times


def _make_X(n: int = 300) -> pd.DataFrame:
    idx = pd.bdate_range("2015-01-01", periods=n)
    rng = np.random.default_rng(7)
    return pd.DataFrame({"f1": rng.standard_normal(n)}, index=idx)


def test_split_without_eval_times_raises():
    cv = PurgedKFold(n_splits=5, embargo_pct=0.01)
    with pytest.raises(ValueError, match="eval_times"):
        list(cv.split(_make_X()))


def test_split_with_mismatched_eval_times_raises():
    X = _make_X()
    cv = PurgedKFold(n_splits=5, embargo_pct=0.01)
    bad = compute_eval_times(X.index[:100], 63)
    with pytest.raises(ValueError, match="length"):
        list(cv.split(X, eval_times=bad))


def test_horizon_days_is_not_a_constructor_arg():
    # aegis_prepare's original bug: this must keep failing loudly, not be
    # absorbed by a future **kwargs.
    with pytest.raises(TypeError):
        PurgedKFold(n_splits=5, embargo_pct=0.01, horizon_days=63)


def test_purging_removes_overlapping_training_samples():
    X = _make_X(300)
    horizon = 63
    cv = PurgedKFold(n_splits=5, embargo_pct=0.0)
    eval_times = compute_eval_times(X.index, horizon)
    folds = list(cv.split(X, eval_times=eval_times))
    assert len(folds) >= 4

    for train_idx, test_idx in folds:
        test_start_time = X.index[test_idx[0]]
        for i in train_idx:
            if X.index[i] < test_start_time:
                # a pre-test training sample whose forward window reaches the
                # test period is exactly what purging must remove
                assert eval_times.iloc[i] < test_start_time, (
                    f"unpurged leak: train sample {i} ends "
                    f"{eval_times.iloc[i]} >= test start {test_start_time}"
                )


def test_purged_folds_are_smaller_than_naive_folds():
    # If purging did nothing, every fold would have exactly n - fold_size
    # training samples. With a forward window it must be strictly smaller
    # for at least the later folds.
    X = _make_X(300)
    cv = PurgedKFold(n_splits=5, embargo_pct=0.0)
    eval_times = compute_eval_times(X.index, 63)
    shrunk = 0
    for train_idx, test_idx in cv.split(X, eval_times=eval_times):
        if len(train_idx) < len(X) - len(test_idx):
            shrunk += 1
    assert shrunk >= 3


def test_aegis_prepare_split_construction_matches_fix():
    """The exact construction aegis_prepare now uses must work end-to-end
    on synthetic data (the real end-to-end needs network and is exercised
    separately)."""
    X = _make_X(260)
    cv = PurgedKFold(n_splits=5, embargo_pct=0.01)
    eval_times = compute_eval_times(X.index, 63)
    folds = list(cv.split(X, eval_times=eval_times))
    assert folds, "no folds produced"
    for train_idx, test_idx in folds:
        assert len(np.intersect1d(train_idx, test_idx)) == 0
