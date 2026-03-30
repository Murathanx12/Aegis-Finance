"""
Sample Uniqueness Weighting (Phase 1.5)
========================================

Computes average uniqueness for each training sample based on
overlapping forward-looking label windows (Lopez de Prado AFML Ch. 4).

Samples whose label windows overlap heavily with other samples carry
redundant information. Weighting by uniqueness reduces overfit from
overlapping 3m/6m/12m forward windows.

Usage:
    from engine.training.sample_uniqueness import compute_sample_weights
    weights = compute_sample_weights(label_start_dates, label_end_dates)
    lgb_model.fit(X, y, sample_weight=weights)
"""

import numpy as np
import pandas as pd


def _build_indicator_matrix(
    start_dates: pd.DatetimeIndex,
    end_dates: pd.DatetimeIndex,
    price_dates: pd.DatetimeIndex,
) -> np.ndarray:
    """Build binary indicator matrix: which price bars does each label span?

    Args:
        start_dates: Label start (observation date) for each sample
        end_dates: Label end (horizon date) for each sample
        price_dates: Full date index of price bars

    Returns:
        np.ndarray of shape (n_bars, n_samples) — 1 where label i spans bar t
    """
    n_bars = len(price_dates)
    n_samples = len(start_dates)
    ind_mat = np.zeros((n_bars, n_samples), dtype=np.float32)

    # Map dates to integer indices for speed
    date_to_idx = {d: i for i, d in enumerate(price_dates)}

    for j in range(n_samples):
        s = start_dates[j]
        e = end_dates[j]
        si = date_to_idx.get(s)
        ei = date_to_idx.get(e)
        if si is not None and ei is not None:
            ind_mat[si : ei + 1, j] = 1.0

    return ind_mat


def _average_uniqueness(ind_mat: np.ndarray) -> np.ndarray:
    """Compute average uniqueness for each sample.

    For each bar t, uniqueness_t = 1 / (number of labels spanning bar t).
    Sample j's average uniqueness = mean of uniqueness_t over bars where label j is active.

    Returns:
        np.ndarray of shape (n_samples,) with values in (0, 1]
    """
    # Number of labels concurrent at each bar
    concurrency = ind_mat.sum(axis=1)  # (n_bars,)
    concurrency[concurrency == 0] = 1  # avoid division by zero

    # Uniqueness at each bar
    uniqueness = 1.0 / concurrency  # (n_bars,)

    # Per-sample average uniqueness
    n_samples = ind_mat.shape[1]
    avg_uniq = np.zeros(n_samples)
    for j in range(n_samples):
        mask = ind_mat[:, j] > 0
        if mask.any():
            avg_uniq[j] = uniqueness[mask].mean()
        else:
            avg_uniq[j] = 1.0

    return avg_uniq


def compute_sample_weights(
    observation_dates: pd.DatetimeIndex,
    horizon_dates: pd.DatetimeIndex,
    price_dates: pd.DatetimeIndex,
    temporal_decay: bool = True,
) -> np.ndarray:
    """Compute sample weights combining uniqueness and temporal decay.

    Args:
        observation_dates: Date each sample was observed
        horizon_dates: End of forward-looking window for each sample's label
        price_dates: Full trading date index
        temporal_decay: If True, also apply linear temporal weighting (recent = higher)

    Returns:
        np.ndarray of sample weights (same length as observation_dates)
    """
    ind_mat = _build_indicator_matrix(observation_dates, horizon_dates, price_dates)
    uniqueness = _average_uniqueness(ind_mat)

    if temporal_decay:
        n = len(uniqueness)
        temporal = np.linspace(0.5, 1.5, n)
        weights = uniqueness * temporal
    else:
        weights = uniqueness

    # Normalize to mean 1.0
    mean_w = weights.mean()
    if mean_w > 0:
        weights = weights / mean_w

    return weights


def compute_horizon_end_dates(
    observation_dates: pd.DatetimeIndex,
    horizon_days: int,
    price_dates: pd.DatetimeIndex,
) -> pd.DatetimeIndex:
    """Compute the end date for each sample's forward-looking label window.

    Args:
        observation_dates: Date each sample was observed
        horizon_days: Number of trading days in the label window
        price_dates: Full trading date index

    Returns:
        pd.DatetimeIndex of end dates (clipped to last available date)
    """
    date_list = list(price_dates)
    date_to_idx = {d: i for i, d in enumerate(date_list)}
    last_idx = len(date_list) - 1

    end_dates = []
    for d in observation_dates:
        idx = date_to_idx.get(d, None)
        if idx is not None:
            end_idx = min(idx + horizon_days, last_idx)
            end_dates.append(date_list[end_idx])
        else:
            end_dates.append(d)

    return pd.DatetimeIndex(end_dates)
