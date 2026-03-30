"""
Fractionally Differentiated Features
======================================

Implements fixed-width window fractional differencing (FFD) from
Lopez de Prado (AFML, Ch. 5).

Standard differencing (d=1) removes memory entirely.
Fractional differencing (d~0.3-0.5) preserves long-memory while
achieving stationarity — the minimum amount of differencing needed.

Reference: mlfinlab/features/fracdiff.py (structure)

Usage:
    from engine.training.fracdiff import frac_diff_ffd, find_min_d
    stationary = frac_diff_ffd(prices, d=0.4)
    min_d = find_min_d(prices)
"""

import numpy as np
import pandas as pd
from typing import Optional


def get_weights_ffd(d: float, thresh: float = 1e-2, max_len: int = 500) -> np.ndarray:
    """Compute fixed-width window weights for fractional differencing.

    The weights for fractional differencing at order d are:
        w_0 = 1
        w_k = -w_{k-1} * (d - k + 1) / k

    For the FFD variant, we truncate weights below `thresh` to create
    a fixed-width window, avoiding the expanding window problem.

    Args:
        d: Fractional differencing order (0 < d < 1, typically 0.3-0.5)
        thresh: Minimum weight magnitude (below this, truncate)
        max_len: Maximum number of weights

    Returns:
        Array of weights (descending from w_0=1)
    """
    weights = [1.0]
    k = 1
    while k < max_len:
        w = -weights[-1] * (d - k + 1) / k
        if abs(w) < thresh:
            break
        weights.append(w)
        k += 1
    return np.array(weights[::-1])  # Reverse so oldest weight is first


def frac_diff_ffd(
    series: pd.Series,
    d: float,
    thresh: float = 1e-2,
) -> pd.Series:
    """Apply fixed-width window fractional differencing.

    This is the preferred method (over expanding window) because:
    1. Fixed computation cost per observation
    2. No look-ahead bias
    3. Numerically stable

    Args:
        series: Price or return series
        d: Fractional differencing order
        thresh: Weight cutoff threshold

    Returns:
        Fractionally differenced series (shorter by len(weights)-1)
    """
    weights = get_weights_ffd(d, thresh)
    width = len(weights)

    result = pd.Series(dtype=float, index=series.index)
    vals = series.values

    for i in range(width - 1, len(vals)):
        window = vals[i - width + 1:i + 1]
        result.iloc[i] = np.dot(weights, window)

    return result


def find_min_d(
    series: pd.Series,
    d_range: tuple[float, float] = (0.0, 1.0),
    d_step: float = 0.05,
    p_value_thresh: float = 0.05,
    thresh: float = 1e-2,
) -> float:
    """Find minimum fractional differencing order for stationarity.

    Searches over d values from d_range[0] to d_range[1] in steps of d_step.
    For each d, applies FFD and runs Augmented Dickey-Fuller (ADF) test.
    Returns the smallest d where ADF p-value < p_value_thresh.

    Args:
        series: Price series to test
        d_range: Range of d values to search
        d_step: Step size for d search
        p_value_thresh: ADF p-value threshold for stationarity

    Returns:
        Minimum d for stationarity (defaults to 0.5 if ADF not available)
    """
    try:
        from statsmodels.tsa.stattools import adfuller
    except ImportError:
        # Without statsmodels, use a reasonable default
        return 0.5

    d_values = np.arange(d_range[0] + d_step, d_range[1] + d_step, d_step)

    for d in d_values:
        diff_series = frac_diff_ffd(series, d, thresh)
        clean = diff_series.dropna()

        if len(clean) < 100:
            continue

        try:
            adf_result = adfuller(clean, maxlag=10, autolag="AIC")
            p_value = adf_result[1]

            if p_value < p_value_thresh:
                return round(d, 2)
        except Exception:
            continue

    return 1.0  # Fall back to full differencing


def build_fracdiff_features(
    data: pd.DataFrame,
    columns: Optional[list[str]] = None,
    d_values: Optional[dict[str, float]] = None,
    auto_find_d: bool = True,
) -> pd.DataFrame:
    """Build fractionally differentiated versions of price-based features.

    For each specified column, computes the FFD transform using either
    a pre-specified d value or automatically finding the minimum d.

    Args:
        data: DataFrame with price columns
        columns: List of columns to transform. If None, uses defaults.
        d_values: Dict of {column: d_value}. If None, auto-computes d.
        auto_find_d: Whether to automatically find minimum d

    Returns:
        DataFrame with fracdiff columns named "{col}_ffd"
    """
    if columns is None:
        # Default: apply to main price series
        candidates = ["SP500", "Gold", "NASDAQ", "Russell"]
        columns = [c for c in candidates if c in data.columns]

    if d_values is None:
        d_values = {}

    result = pd.DataFrame(index=data.index)

    for col in columns:
        if col not in data.columns:
            continue

        series = data[col].dropna()
        if len(series) < 200:
            continue

        # Get or compute d
        if col in d_values:
            d = d_values[col]
        elif auto_find_d:
            d = find_min_d(series)
        else:
            d = 0.4  # Safe default

        # Apply FFD
        ffd = frac_diff_ffd(series, d)
        result[f"{col.lower()}_ffd"] = ffd
        result[f"{col.lower()}_ffd_d"] = d  # Store d for reference

    return result
