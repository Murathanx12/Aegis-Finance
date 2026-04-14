"""
Aegis Finance — Anomaly Detection + Bayesian Changepoint Detection
====================================================================

Two complementary tools for model confidence:

1. Isolation Forest: Flags days where feature vector is unlike training data.
   When anomalous, ML predictions should be treated with lower confidence.

2. Bayesian Online Changepoint Detection (BOCPD): Identifies exact day when
   statistical properties of returns shift — detecting regime transitions
   in real time rather than in hindsight (Adams & MacKay 2007).

Ported from market-prediction-engine with Aegis config integration.

Usage:
    from backend.services.anomaly_detector import AnomalyDetector, BayesianChangepoint
"""

import logging

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


class AnomalyDetector:
    """Isolation Forest anomaly detector for market conditions.

    Flags days where the feature vector looks unlike anything in training history.
    """

    def __init__(self, contamination: float = 0.05, n_estimators: int = 200, random_state: int = 42):
        self.contamination = contamination
        self.n_estimators = n_estimators
        self.random_state = random_state
        self.model = None
        self.scaler = None
        self.is_fitted = False
        self._feature_names: list[str] = []

    def fit(self, features: pd.DataFrame) -> dict:
        """Fit on historical feature data."""
        self._feature_names = list(features.columns)
        X = features.values.astype(np.float64)
        # Replace inf with NaN, then impute with column medians (not zeros,
        # which would bias the Isolation Forest toward flagging median-like data)
        X = np.where(np.isinf(X), np.nan, X)
        col_medians = np.nanmedian(X, axis=0)
        col_medians = np.where(np.isnan(col_medians), 0.0, col_medians)
        nan_mask = np.isnan(X)
        X = np.where(nan_mask, col_medians[np.newaxis, :], X)

        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        self.model = IsolationForest(
            n_estimators=self.n_estimators,
            contamination=self.contamination,
            random_state=self.random_state,
            n_jobs=-1,
        )
        self.model.fit(X_scaled)
        self.is_fitted = True

        scores = self.model.decision_function(X_scaled)
        return {
            "n_samples": len(X),
            "n_features": X.shape[1],
            "anomaly_threshold": round(float(np.percentile(scores, self.contamination * 100)), 4),
            "mean_score": round(float(scores.mean()), 4),
        }

    def score(self, features: pd.DataFrame) -> np.ndarray:
        """Compute anomaly scores. Lower = more anomalous. Negative = flagged."""
        if not self.is_fitted:
            raise RuntimeError("AnomalyDetector not fitted")
        X = features[self._feature_names].values if isinstance(features, pd.DataFrame) else features
        X = X.astype(np.float64)
        X = np.where(np.isinf(X), np.nan, X)
        col_medians = np.nanmedian(X, axis=0)
        col_medians = np.where(np.isnan(col_medians), 0.0, col_medians)
        X = np.where(np.isnan(X), col_medians[np.newaxis, :], X)
        return self.model.decision_function(self.scaler.transform(X))

    def is_anomalous(self, features: pd.DataFrame) -> np.ndarray:
        """Boolean array: True where current conditions are anomalous."""
        if not self.is_fitted:
            return np.zeros(len(features), dtype=bool)
        return self.score(features) < 0

    def anomaly_report(self, features: pd.DataFrame) -> dict:
        """Human-readable anomaly assessment with confidence adjustment."""
        if not self.is_fitted:
            return {"status": "UNKNOWN", "score": 0.0, "confidence_factor": 1.0}

        scores = self.score(features)
        latest_score = float(scores[-1]) if len(scores) > 0 else 0.0
        is_anom = latest_score < 0

        confidence_factor = max(0.3, min(1.0, 1.0 + latest_score)) if is_anom else 1.0

        return {
            "status": "ANOMALOUS" if is_anom else "NORMAL",
            "score": round(latest_score, 4),
            "is_anomalous": is_anom,
            "confidence_factor": round(confidence_factor, 3),
            "interpretation": (
                f"Market conditions are {'UNLIKE' if is_anom else 'consistent with'} "
                f"historical patterns (score={latest_score:.3f}). "
                f"{'Model predictions may be unreliable.' if is_anom else 'Predictions should be reliable.'}"
            ),
        }


def _gaussian_pdf(x: float, mu: float, var: float) -> float:
    """Gaussian probability density."""
    return np.exp(-0.5 * (x - mu) ** 2 / var) / np.sqrt(2 * np.pi * var)


class BayesianChangepoint:
    """Bayesian Online Changepoint Detection (BOCPD).

    Detects when statistical properties of returns shift, identifying
    regime transitions in real time. Based on Adams & MacKay (2007).
    """

    def __init__(self, hazard_rate: float = 1 / 252, mu_prior: float = 0.0, var_prior: float = 1.0):
        self.hazard_rate = hazard_rate
        self.mu_prior = mu_prior
        self.var_prior = var_prior

    def detect(self, returns: pd.Series, window: int = 60) -> pd.DataFrame:
        """Run BOCPD on a return series.

        Returns DataFrame with changepoint_prob and regime_age columns.
        """
        x = returns.dropna().values[-window:] if window else returns.dropna().values
        n = len(x)
        if n < 10:
            return pd.DataFrame(
                {"changepoint_prob": np.zeros(len(returns)), "regime_age": np.full(len(returns), float(len(returns)))},
                index=returns.index,
            )

        max_run = n + 1
        R = np.zeros((n + 1, max_run))
        R[0, 0] = 1.0

        counts = np.zeros(max_run)
        sums = np.zeros(max_run)
        sum_sq = np.zeros(max_run)

        changepoint_probs = np.zeros(n)
        regime_ages = np.zeros(n)
        h = self.hazard_rate

        for t in range(n):
            predprobs = np.zeros(t + 1)
            for r in range(t + 1):
                if counts[r] < 2:
                    predprobs[r] = _gaussian_pdf(x[t], self.mu_prior, self.var_prior)
                else:
                    mean = sums[r] / counts[r]
                    var = max(sum_sq[r] / counts[r] - mean**2, 1e-10) + self.var_prior / counts[r]
                    predprobs[r] = _gaussian_pdf(x[t], mean, var)

            R[t + 1, 1:t + 2] = R[t, :t + 1] * predprobs * (1 - h)
            R[t + 1, 0] = np.sum(R[t, :t + 1] * predprobs * h)

            evidence = R[t + 1, :t + 2].sum()
            if evidence > 0:
                R[t + 1, :t + 2] /= evidence

            changepoint_probs[t] = float(R[t + 1, 0])
            regime_ages[t] = float(np.sum(np.arange(t + 2) * R[t + 1, :t + 2]))

            new_counts = counts[:t + 1] + 1
            new_sums = sums[:t + 1] + x[t]
            new_sum_sq = sum_sq[:t + 1] + x[t] ** 2

            counts[1:t + 2] = new_counts
            sums[1:t + 2] = new_sums
            sum_sq[1:t + 2] = new_sum_sq
            counts[0] = sums[0] = sum_sq[0] = 0

        result_index = returns.dropna().index[-n:] if window else returns.dropna().index
        result = pd.DataFrame(
            {"changepoint_prob": changepoint_probs, "regime_age": regime_ages},
            index=result_index,
        )
        return result.reindex(returns.index).ffill().bfill()

    def recent_changepoint(self, returns: pd.Series, window: int = 60, threshold: float = 0.30) -> dict:
        """Check if a recent changepoint was detected."""
        result = self.detect(returns, window=window)
        cp = result["changepoint_prob"].dropna()
        if len(cp) == 0:
            return {"detected": False, "days_ago": window, "max_prob": 0.0}

        max_prob = float(cp.max())
        if max_prob >= threshold:
            days_ago = int(len(cp) - cp.values.argmax() - 1)
            return {"detected": True, "days_ago": days_ago, "max_prob": round(max_prob, 4)}
        return {"detected": False, "days_ago": window, "max_prob": round(max_prob, 4)}
