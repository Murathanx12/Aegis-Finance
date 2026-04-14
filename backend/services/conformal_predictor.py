"""
Aegis Finance — Conformal Prediction Intervals for Crash Probabilities
========================================================================

Adds calibrated uncertainty quantification to crash model predictions.
Instead of just "7% crash probability", users get "7% [3%–15%] at 90% coverage".

Split Conformal Prediction (Vovk, Gammerman & Shafer, 2005):
  - Model-free: works with any predictor (LightGBM, Logistic, ensemble)
  - Distribution-free: no assumptions about data distribution
  - Finite-sample coverage guarantee: P(y ∈ C(x)) ≥ 1 - α for any α

Implementation:
  1. On calibration data, compute nonconformity scores: |p_hat - y_actual|
  2. For new prediction p_hat, the interval is:
     [p_hat - q, p_hat + q] where q = quantile(scores, (1-α)(1+1/n))
  3. Clip to [0, 1] since these are probabilities

This is stored per-horizon and recomputed when the model is retrained.
The scores persist alongside the crash model weights.

References:
  - Vovk, Gammerman & Shafer (2005), "Algorithmic Learning in a Random World"
  - Lei et al. (2018), "Distribution-Free Predictive Inference for Regression"
  - Romano, Patterson & Candès (2019), "Conformalized Quantile Regression"

Usage:
    from backend.services.conformal_predictor import (
        ConformalCrashPredictor, conformal_crash_interval,
    )
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np

from backend.config import config

logger = logging.getLogger(__name__)


class ConformalCrashPredictor:
    """Wraps CrashPredictor with conformal prediction intervals.

    After the crash model is trained, call calibrate() with held-out data
    to compute nonconformity scores. Then predict_with_interval() returns
    both the point prediction and a calibrated interval.
    """

    def __init__(self):
        # {horizon: sorted array of nonconformity scores}
        self._scores: dict[str, np.ndarray] = {}
        # {horizon: number of calibration samples}
        self._n_cal: dict[str, int] = {}
        self.is_calibrated: bool = False

    def calibrate(
        self,
        predictor,
        cal_features,
        cal_targets: dict,
    ) -> dict:
        """Compute nonconformity scores from calibration data.

        Args:
            predictor: Trained CrashPredictor instance
            cal_features: Feature DataFrame for calibration set
            cal_targets: {horizon: binary_series} — actual crash labels

        Returns:
            Dict with calibration summary per horizon.
        """
        results = {}
        for horizon, y_true in cal_targets.items():
            if horizon not in predictor.lgb_models:
                continue

            # Align features and targets
            valid = y_true.notna()
            if hasattr(cal_features, "loc"):
                X_cal = cal_features[valid]
            else:
                X_cal = cal_features
            y_cal = y_true[valid].values.astype(float)

            if len(y_cal) < 20:
                logger.warning(
                    "Conformal %s: only %d calibration samples (need ≥20)",
                    horizon, len(y_cal),
                )
                continue

            # Get calibrated predictions
            p_hat = predictor.predict_proba(X_cal, horizon)

            # Nonconformity score: absolute residual |p_hat - y_actual|
            # For binary y ∈ {0,1}, this measures how "surprised" the model is
            scores = np.abs(p_hat - y_cal)

            # Sort for efficient quantile computation
            self._scores[horizon] = np.sort(scores)
            self._n_cal[horizon] = len(scores)

            results[horizon] = {
                "n_calibration": len(scores),
                "score_mean": round(float(np.mean(scores)), 4),
                "score_median": round(float(np.median(scores)), 4),
                "score_p90": round(float(np.percentile(scores, 90)), 4),
                "score_p95": round(float(np.percentile(scores, 95)), 4),
            }

            logger.info(
                "Conformal %s: %d cal samples, median score=%.4f, p90=%.4f",
                horizon, len(scores), np.median(scores), np.percentile(scores, 90),
            )

        if results:
            self.is_calibrated = True
        return results

    def get_interval(
        self,
        point_prediction: float,
        horizon: str = "3m",
        alpha: float = 0.10,
    ) -> dict:
        """Compute conformal prediction interval for a crash probability.

        Args:
            point_prediction: Calibrated crash probability (0-1)
            horizon: Prediction horizon ("3m", "6m", "12m")
            alpha: Miscoverage rate (0.10 = 90% coverage interval)

        Returns:
            Dict with lower, upper bounds and interval width.
            Coverage guarantee: P(true_prob ∈ [lower, upper]) ≥ 1-α.
        """
        if not self.is_calibrated or horizon not in self._scores:
            # Fallback: use a heuristic interval based on prediction magnitude
            return _heuristic_interval(point_prediction, alpha)

        scores = self._scores[horizon]
        n = self._n_cal[horizon]

        # Conformal quantile: ceil((1-α)(1+1/n))-th order statistic
        # This gives exact finite-sample coverage of ≥ 1-α
        q_level = min((1 - alpha) * (1 + 1 / n), 1.0)
        q_idx = int(np.ceil(q_level * n)) - 1
        q_idx = min(q_idx, n - 1)
        q = float(scores[q_idx])

        lower = max(0.0, point_prediction - q)
        upper = min(1.0, point_prediction + q)

        return {
            "lower": round(lower, 4),
            "upper": round(upper, 4),
            "point": round(point_prediction, 4),
            "width": round(upper - lower, 4),
            "coverage_target": round(1 - alpha, 2),
            "n_calibration": n,
            "method": "split_conformal",
        }

    def get_multi_horizon_intervals(
        self,
        predictions: dict[str, float],
        alpha: float = 0.10,
    ) -> dict:
        """Compute conformal intervals for all horizons, enforcing monotonicity.

        The intervals respect the same monotonicity constraint as the
        point predictions: lower bounds are monotonically increasing across
        horizons, as are upper bounds.

        Args:
            predictions: {horizon: crash_probability} point predictions
            alpha: Miscoverage rate

        Returns:
            Dict of {horizon: interval_dict}
        """
        intervals = {}
        for horizon, prob in predictions.items():
            intervals[horizon] = self.get_interval(prob, horizon, alpha)

        # Enforce monotonicity on lower and upper bounds
        ordered = ["3m", "6m", "12m"]
        available = [h for h in ordered if h in intervals]
        for i in range(1, len(available)):
            prev, curr = available[i - 1], available[i]
            # Longer horizon bounds must be ≥ shorter horizon bounds
            intervals[curr]["lower"] = round(
                max(intervals[curr]["lower"], intervals[prev]["lower"]), 4
            )
            intervals[curr]["upper"] = round(
                max(intervals[curr]["upper"], intervals[prev]["upper"]), 4
            )
            intervals[curr]["width"] = round(
                intervals[curr]["upper"] - intervals[curr]["lower"], 4
            )

        return intervals

    def save(self, path: str) -> None:
        """Serialize conformal scores to disk."""
        try:
            import joblib
            state = {
                "scores": self._scores,
                "n_cal": self._n_cal,
            }
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(state, path)
            logger.info("Conformal predictor saved to %s", path)
        except Exception as e:
            logger.warning("Failed to save conformal predictor: %s", e)

    def load(self, path: str) -> bool:
        """Load conformal scores from disk. Returns True on success."""
        try:
            import joblib
            if not Path(path).exists():
                return False
            state = joblib.load(path)
            self._scores = state["scores"]
            self._n_cal = state["n_cal"]
            self.is_calibrated = bool(self._scores)
            logger.info(
                "Conformal predictor loaded from %s (horizons: %s)",
                path, list(self._scores.keys()),
            )
            return True
        except Exception as e:
            logger.warning("Failed to load conformal predictor: %s", e)
            return False


def _heuristic_interval(
    point_prediction: float,
    alpha: float = 0.10,
) -> dict:
    """Heuristic fallback interval when conformal calibration is unavailable.

    Uses prediction-dependent width: wider intervals for mid-range predictions
    (most uncertain), narrower at extremes (more certain).
    Width is scaled by alpha to maintain approximate coverage semantics.
    """
    # Beta distribution-inspired width: max uncertainty at p=0.5
    base_width = 2.0 * np.sqrt(point_prediction * (1 - point_prediction))
    # Scale by confidence level (wider for higher coverage)
    z_scale = {0.20: 0.15, 0.10: 0.20, 0.05: 0.25, 0.01: 0.35}
    scale = z_scale.get(alpha, 0.20)
    half_width = base_width * scale

    lower = max(0.0, point_prediction - half_width)
    upper = min(1.0, point_prediction + half_width)

    return {
        "lower": round(lower, 4),
        "upper": round(upper, 4),
        "point": round(point_prediction, 4),
        "width": round(upper - lower, 4),
        "coverage_target": round(1 - alpha, 2),
        "n_calibration": 0,
        "method": "heuristic",
    }


# ══════════════════════════════════════════════════════════════════════════════
# Convenience function for use in stock_analyzer / routers
# ══════════════════════════════════════════════════════════════════════════════

# Module-level singleton (loaded once, reused)
_conformal_predictor: Optional[ConformalCrashPredictor] = None


def get_conformal_predictor() -> ConformalCrashPredictor:
    """Get or initialize the module-level conformal predictor."""
    global _conformal_predictor
    if _conformal_predictor is None:
        _conformal_predictor = ConformalCrashPredictor()
        # Try to load pre-computed scores
        model_dir = Path(__file__).parent.parent / "models"
        conformal_path = model_dir / "conformal_scores.pkl"
        _conformal_predictor.load(str(conformal_path))
    return _conformal_predictor


def conformal_crash_interval(
    crash_prob: float,
    horizon: str = "3m",
    alpha: float = 0.10,
) -> dict:
    """Quick access: get conformal interval for a crash probability.

    Args:
        crash_prob: Point estimate of crash probability (0-1 scale)
        horizon: Prediction horizon
        alpha: Miscoverage rate (0.10 = 90% coverage)

    Returns:
        Dict with lower, upper, point, width, coverage_target, method.
    """
    cp = get_conformal_predictor()
    return cp.get_interval(crash_prob, horizon, alpha)
