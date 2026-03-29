"""
3-State Hidden Markov Model for Regime Detection
===================================================

Learns Bull/Bear/Crisis regimes from statistical properties of
returns, VIX, and volatility rather than manual thresholds.

Outputs regime probabilities instead of binary signals.

Usage:
    from backend.models.hmm import fit_hmm_regimes, get_regime_probs
"""

import logging
from typing import NamedTuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class HMMResult(NamedTuple):
    model: object
    regime_labels: pd.Series
    regime_probs: np.ndarray  # [bull, bear, crisis]
    current_regime: str
    transition_matrix: np.ndarray
    state_means: np.ndarray
    state_vols: np.ndarray
    success: bool
    feature_mean: np.ndarray = None
    feature_std: np.ndarray = None


def fit_hmm_regimes(
    data: pd.DataFrame,
    n_states: int = 3,
    n_fits: int = 10,
) -> HMMResult:
    """Fit a 3-state Gaussian HMM on market features.

    Features: smoothed log returns, realized vol, VIX (if available).
    Multiple random restarts to avoid local optima.
    """
    try:
        from hmmlearn.hmm import GaussianHMM
    except ImportError:
        logger.warning("hmmlearn not available, using fallback")
        return _fallback_result(data)

    returns = data["SP500"].pct_change().dropna()
    log_ret = np.log(1 + returns)

    ret_smooth = log_ret.rolling(5).mean() * 252
    real_vol = returns.rolling(20).std() * np.sqrt(252)

    features_list = [ret_smooth, real_vol]
    if "VIX" in data.columns:
        features_list.append(data["VIX"].reindex(returns.index))

    features = pd.concat(features_list, axis=1).dropna()
    if len(features) < 500:
        logger.warning("Not enough data for HMM (%d rows)", len(features))
        return _fallback_result(data)

    X = features.values
    X_mean = X.mean(axis=0)
    X_std = X.std(axis=0)
    X_std[X_std == 0] = 1
    X_norm = (X - X_mean) / X_std

    best_score = -np.inf
    best_model = None

    for seed in range(n_fits):
        try:
            model = GaussianHMM(
                n_components=n_states,
                covariance_type="full",
                n_iter=200,
                random_state=seed,
                tol=1e-4,
            )
            model.fit(X_norm)
            score = model.score(X_norm)
            if score > best_score:
                best_score = score
                best_model = model
        except Exception:
            continue

    if best_model is None:
        logger.warning("All HMM fits failed")
        return _fallback_result(data)

    states = best_model.predict(X_norm)
    probs = best_model.predict_proba(X_norm)

    # Label states by mean return
    state_mean_returns = []
    state_mean_vols = []
    for s in range(n_states):
        mask = states == s
        if mask.sum() > 0:
            state_mean_returns.append(float(X[mask, 0].mean()))
            state_mean_vols.append(float(X[mask, 1].mean()))
        else:
            state_mean_returns.append(0)
            state_mean_vols.append(0.2)

    sorted_indices = np.argsort(state_mean_returns)
    label_map = {
        sorted_indices[0]: "Crisis",
        sorted_indices[1]: "Bear",
        sorted_indices[2]: "Bull",
    }

    state_names = [label_map[s] for s in states]
    regime_series = pd.Series(state_names, index=features.index)

    full_regimes = pd.Series("Unknown", index=data.index)
    full_regimes.loc[regime_series.index] = regime_series
    mask = full_regimes == "Unknown"
    full_regimes[mask] = np.nan
    full_regimes = full_regimes.ffill().bfill().fillna("Bull")

    # Reorder probabilities to [bull, bear, crisis]
    current_probs_raw = probs[-1]
    current_probs = np.zeros(n_states)
    for raw_idx, name in label_map.items():
        ordered_idx = ["Bull", "Bear", "Crisis"].index(name) if name in ["Bull", "Bear", "Crisis"] else raw_idx
        if ordered_idx < n_states:
            current_probs[ordered_idx] = current_probs_raw[raw_idx]

    current = label_map[states[-1]]
    logger.info("HMM: current regime=%s, log-likelihood=%.0f", current, best_score)

    return HMMResult(
        model=best_model,
        regime_labels=full_regimes,
        regime_probs=current_probs,
        current_regime=current,
        transition_matrix=best_model.transmat_,
        state_means=np.array(state_mean_returns),
        state_vols=np.array(state_mean_vols),
        success=True,
        feature_mean=X_mean,
        feature_std=X_std,
    )


def get_regime_probs(hmm_result: HMMResult) -> dict:
    """Convert HMM regime probabilities to scenario weight adjustments."""
    if not hmm_result.success:
        return {"bull_prob": 0.50, "bear_prob": 0.30, "crisis_prob": 0.20}

    probs = hmm_result.regime_probs
    total = probs.sum()
    if total > 0:
        probs = probs / total

    return {
        "bull_prob": float(probs[0]),
        "bear_prob": float(probs[1]),
        "crisis_prob": float(probs[2]) if len(probs) > 2 else 0.0,
    }


def _fallback_result(data: pd.DataFrame) -> HMMResult:
    regimes = pd.Series("Bull", index=data.index)
    return HMMResult(
        model=None,
        regime_labels=regimes,
        regime_probs=np.array([0.5, 0.3, 0.2]),
        current_regime="Bull",
        transition_matrix=np.eye(3),
        state_means=np.array([0.10, -0.05, -0.30]),
        state_vols=np.array([0.15, 0.20, 0.35]),
        success=False,
    )
