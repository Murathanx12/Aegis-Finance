"""
Drift Detection (Phase 4.4)
============================

Population Stability Index (PSI) and Kolmogorov-Smirnov tests
to detect feature distribution drift between training and inference.

Triggers retraining when drift exceeds thresholds.

Usage:
    from backend.services.drift_detector import DriftDetector

    detector = DriftDetector(training_features)
    report = detector.check_drift(inference_features)
    if report["drift_detected"]:
        logger.warning("Feature drift detected: %s", report["drifted_features"])
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from backend.config import config

logger = logging.getLogger(__name__)


class DriftDetector:
    """Detect feature distribution drift using PSI and KS tests."""

    def __init__(
        self,
        reference_data: pd.DataFrame,
        n_bins: Optional[int] = None,
        psi_threshold: Optional[float] = None,
        ks_p_threshold: Optional[float] = None,
        seed: int = 42,
    ):
        """Initialize with training (reference) distribution.

        Args:
            reference_data: Training feature matrix (used as baseline)
            n_bins: Number of bins for PSI (default from config)
            psi_threshold: PSI threshold for drift (default 0.2)
            ks_p_threshold: KS test p-value threshold (default 0.01)
            seed: Random seed for reproducible KS tests
        """
        drift_cfg = config["ml"].get("drift", {})
        self.n_bins = n_bins or drift_cfg.get("n_bins", 10)
        self.psi_threshold = psi_threshold or drift_cfg.get("psi_threshold", 0.2)
        self.ks_p_threshold = ks_p_threshold or drift_cfg.get("ks_p_threshold", 0.01)
        self._rng = np.random.default_rng(seed)

        # Store reference quantile edges for each feature
        self._reference_edges: dict[str, np.ndarray] = {}
        self._reference_proportions: dict[str, np.ndarray] = {}

        self._fit_reference(reference_data)

    def _fit_reference(self, data: pd.DataFrame) -> None:
        """Compute bin edges and proportions from training data."""
        for col in data.columns:
            values = data[col].dropna().values
            if len(values) < self.n_bins * 2:
                continue

            # Use quantile-based bins for robustness
            edges = np.quantile(
                values,
                np.linspace(0, 1, self.n_bins + 1),
            )
            # Ensure unique edges
            edges = np.unique(edges)
            if len(edges) < 3:
                continue

            counts = np.histogram(values, bins=edges)[0]
            proportions = counts / counts.sum()
            # Floor small bins to avoid log(0)
            proportions = np.maximum(proportions, 1e-6)

            self._reference_edges[col] = edges
            self._reference_proportions[col] = proportions

    @staticmethod
    def _psi(reference: np.ndarray, actual: np.ndarray) -> float:
        """Compute Population Stability Index between two distributions.

        PSI = sum((actual_i - reference_i) * ln(actual_i / reference_i))

        Interpretation:
            PSI < 0.1: No significant change
            0.1 <= PSI < 0.2: Moderate change
            PSI >= 0.2: Significant drift
        """
        # Floor to avoid division by zero / log(0)
        ref = np.maximum(reference, 1e-6)
        act = np.maximum(actual, 1e-6)

        psi_value = float(np.sum((act - ref) * np.log(act / ref)))
        return psi_value

    def check_drift(
        self,
        inference_data: pd.DataFrame,
        feature_importances: Optional[dict[str, float]] = None,
    ) -> dict:
        """Check for feature drift between training and inference data.

        Args:
            inference_data: New feature matrix to check against training baseline
            feature_importances: Optional dict mapping feature names to importance
                scores (e.g. from CrashPredictor.get_top_features()). When provided,
                computes importance-weighted drift percentage — features that the model
                relies on more count more toward the drift score. This prevents low-
                importance features (momentum, short-term vol) from inflating drift
                severity and unnecessarily disabling the crash model.

        Returns:
            dict with drift report including:
                - drift_pct: raw (unweighted) percentage of features drifting
                - importance_weighted_drift_pct: weighted by model reliance (if importances given)
                - drift_direction: per-feature shift direction and magnitude
                - stable_important_features: important features that are NOT drifting
        """
        results = {}
        drifted_features = []

        for col in self._reference_edges:
            if col not in inference_data.columns:
                continue

            values = inference_data[col].dropna().values
            if len(values) < 10:
                continue

            edges = self._reference_edges[col]
            ref_proportions = self._reference_proportions[col]

            # Compute actual proportions using same bin edges
            counts = np.histogram(values, bins=edges)[0]
            if counts.sum() == 0:
                continue
            actual_proportions = counts / counts.sum()
            actual_proportions = np.maximum(actual_proportions, 1e-6)

            psi = self._psi(ref_proportions, actual_proportions)

            # KS test
            ks_stat, ks_p = self._ks_test(col, values)

            drift_flag = psi >= self.psi_threshold or ks_p < self.ks_p_threshold

            # Drift direction: compare distribution centers and spreads
            direction = self._drift_direction(col, values)

            results[col] = {
                "psi": round(psi, 4),
                "ks_stat": round(ks_stat, 4),
                "ks_p": round(ks_p, 6),
                "drift": drift_flag,
                **direction,
            }

            if drift_flag:
                drifted_features.append(col)

        drift_detected = len(drifted_features) > 0
        n_features_checked = len(results)
        drift_pct = (
            len(drifted_features) / n_features_checked * 100
            if n_features_checked > 0
            else 0
        )

        # Importance-weighted drift: weight each feature's drift flag by its
        # importance in the model. A feature that the model barely uses
        # contributes little to the weighted score even if it's drifting.
        iw_drift_pct = None
        stable_important = []
        if feature_importances is not None and n_features_checked > 0:
            iw_drift_pct, stable_important = self._importance_weighted_drift(
                results, feature_importances,
            )

        if drift_detected:
            if iw_drift_pct is not None:
                logger.warning(
                    "Drift detected in %d/%d features (%.0f%% raw, %.0f%% importance-weighted): %s",
                    len(drifted_features), n_features_checked,
                    drift_pct, iw_drift_pct, drifted_features[:5],
                )
            else:
                logger.warning(
                    "Drift detected in %d/%d features (%.0f%%): %s",
                    len(drifted_features), n_features_checked,
                    drift_pct, drifted_features[:5],
                )
        else:
            logger.info(
                "No drift detected across %d features", n_features_checked
            )

        report = {
            "drift_detected": drift_detected,
            "drifted_features": drifted_features,
            "n_features_checked": n_features_checked,
            "n_drifted": len(drifted_features),
            "drift_pct": round(drift_pct, 1),
            "feature_details": results,
        }

        if iw_drift_pct is not None:
            report["importance_weighted_drift_pct"] = round(iw_drift_pct, 1)
            report["stable_important_features"] = stable_important

        return report

    def _drift_direction(self, col: str, inference_values: np.ndarray) -> dict:
        """Characterize how a feature's distribution shifted.

        Returns dict with:
            - mean_shift: signed change in distribution center
              (positive = shifted higher, negative = shifted lower)
            - spread_change: ratio of inference spread to reference spread
              (>1 = wider/more volatile, <1 = narrower/compressed)
        """
        edges = self._reference_edges[col]
        ref_proportions = self._reference_proportions[col]

        # Approximate reference mean from bin centers and proportions
        bin_centers = (edges[:-1] + edges[1:]) / 2.0
        ref_mean = float(np.dot(bin_centers, ref_proportions / ref_proportions.sum()))
        inf_mean = float(np.mean(inference_values))

        # Spread: IQR ratio (robust to outliers)
        ref_iqr = float(edges[-1] - edges[0])  # full range from quantile edges
        if len(inference_values) >= 4:
            inf_q25, inf_q75 = np.quantile(inference_values, [0.0, 1.0])
            inf_iqr = float(inf_q75 - inf_q25)
        else:
            inf_iqr = ref_iqr

        spread_ratio = inf_iqr / ref_iqr if ref_iqr > 1e-9 else 1.0

        return {
            "mean_shift": round(inf_mean - ref_mean, 6),
            "spread_change": round(spread_ratio, 3),
        }

    @staticmethod
    def _importance_weighted_drift(
        feature_details: dict,
        feature_importances: dict[str, float],
    ) -> tuple[float, list[str]]:
        """Compute importance-weighted drift percentage.

        Instead of counting drifted features equally (89% raw drift when
        141/158 features drift), this weights each feature by its model
        importance. If the model's top features (leading indicators) are
        stable while low-importance features (momentum, vol) drift, the
        weighted drift is much lower — and the model is still reliable.

        Args:
            feature_details: Per-feature drift results from check_drift()
            feature_importances: {feature_name: importance_score}

        Returns:
            (importance_weighted_drift_pct, stable_important_features_list)
        """
        total_weight = 0.0
        drifted_weight = 0.0
        stable_important = []

        # Normalize importances to sum to 1
        all_imp = {f: feature_importances.get(f, 0.0) for f in feature_details}
        imp_sum = sum(all_imp.values())
        if imp_sum <= 0:
            # No importance info available — fall back to unweighted
            n_checked = len(feature_details)
            n_drifted = sum(1 for v in feature_details.values() if v["drift"])
            return (n_drifted / n_checked * 100 if n_checked > 0 else 0.0), []

        for feat, detail in feature_details.items():
            w = all_imp[feat] / imp_sum
            total_weight += w
            if detail["drift"]:
                drifted_weight += w
            elif all_imp[feat] > 0:
                stable_important.append((feat, round(all_imp[feat], 4)))

        # Sort stable features by importance (most important first)
        stable_important.sort(key=lambda x: x[1], reverse=True)
        # Keep top 20 for readability
        stable_names = [f for f, _ in stable_important[:20]]

        iw_pct = (drifted_weight / total_weight * 100) if total_weight > 0 else 0.0
        return iw_pct, stable_names

    @staticmethod
    def from_rolling_window(
        features: pd.DataFrame,
        reference_days: int = 504,
        inference_days: int = 252,
        feature_importances: Optional[dict[str, float]] = None,
        **kwargs,
    ) -> dict:
        """Create a DriftDetector using a rolling window split.

        Instead of the static 80/20 split that compares 2000-2020 vs 2020-2026
        (guaranteed to show drift on financial time series), this compares
        the *recent* inference window against the *prior* reference window.

        Example with defaults (504/252):
            reference = features[-756:-252]  (2 years before the inference window)
            inference = features[-252:]       (last 1 year)

        This detects *recent* distribution shifts, not historical regime changes.

        Args:
            features: Full feature matrix (DatetimeIndex, chronologically sorted)
            reference_days: Number of trading days for the reference window
            inference_days: Number of trading days for the inference window
            feature_importances: Optional dict mapping feature names to importance
                scores from the crash model. When provided, computes importance-
                weighted drift and uses it for severity classification. This prevents
                89% raw drift from disabling the crash model when the important
                features are actually stable.
            **kwargs: Passed to DriftDetector.__init__

        Returns:
            dict with drift report, severity, and (if importances given)
            importance-weighted metrics.
        """
        n = len(features)
        total_needed = reference_days + inference_days
        if n < total_needed:
            # Fall back to proportional split if not enough data
            split = int(n * 0.6)
            reference = features.iloc[:split]
            inference = features.iloc[split:]
        else:
            inference = features.iloc[-inference_days:]
            reference = features.iloc[-(reference_days + inference_days):-inference_days]

        detector = DriftDetector(reference, **kwargs)
        report = detector.check_drift(inference, feature_importances=feature_importances)

        # Raw severity classification (backward compatible)
        drift_pct = report["drift_pct"]
        if drift_pct == 0:
            severity = "none"
        elif drift_pct < 10:
            severity = "low"
        elif drift_pct < 30:
            severity = "moderate"
        elif drift_pct < 60:
            severity = "high"
        else:
            severity = "critical"

        report["severity"] = severity
        report["reference_window"] = reference_days
        report["inference_window"] = inference_days

        # Importance-weighted severity: uses the model's own feature importances
        # to determine how much the drifting features actually matter. When 89%
        # of features drift but the important ones are stable, the effective
        # severity may be much lower (e.g. "moderate" instead of "critical").
        if "importance_weighted_drift_pct" in report:
            iw_pct = report["importance_weighted_drift_pct"]
            if iw_pct == 0:
                iw_severity = "none"
            elif iw_pct < 15:
                iw_severity = "low"
            elif iw_pct < 35:
                iw_severity = "moderate"
            elif iw_pct < 65:
                iw_severity = "high"
            else:
                iw_severity = "critical"
            report["importance_weighted_severity"] = iw_severity
            # The effective severity is the importance-weighted one when available
            report["effective_severity"] = iw_severity
        else:
            report["effective_severity"] = severity

        return report

    def _ks_test(self, col: str, values: np.ndarray) -> tuple[float, float]:
        """Two-sample Kolmogorov-Smirnov test against reference distribution.

        Returns (ks_statistic, p_value).
        """
        try:
            from scipy.stats import ks_2samp

            # Reconstruct reference sample from stored edges and proportions
            edges = self._reference_edges[col]
            ref_proportions = self._reference_proportions[col]

            # Generate synthetic reference sample from bin proportions
            n_synthetic = max(len(values), 1000)
            ref_samples = []
            for i, prop in enumerate(ref_proportions):
                n_in_bin = max(1, int(prop * n_synthetic))
                bin_samples = self._rng.uniform(edges[i], edges[i + 1], size=n_in_bin)
                ref_samples.append(bin_samples)
            ref_samples = np.concatenate(ref_samples)

            stat, p = ks_2samp(ref_samples, values)
            return float(stat), float(p)
        except ImportError:
            return 0.0, 1.0
