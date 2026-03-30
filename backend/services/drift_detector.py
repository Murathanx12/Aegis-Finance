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
    ):
        """Initialize with training (reference) distribution.

        Args:
            reference_data: Training feature matrix (used as baseline)
            n_bins: Number of bins for PSI (default from config)
            psi_threshold: PSI threshold for drift (default 0.2)
            ks_p_threshold: KS test p-value threshold (default 0.01)
        """
        drift_cfg = config["ml"].get("drift", {})
        self.n_bins = n_bins or drift_cfg.get("n_bins", 10)
        self.psi_threshold = psi_threshold or drift_cfg.get("psi_threshold", 0.2)
        self.ks_p_threshold = ks_p_threshold or drift_cfg.get("ks_p_threshold", 0.01)

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
    ) -> dict:
        """Check for feature drift between training and inference data.

        Args:
            inference_data: New feature matrix to check against training baseline

        Returns:
            dict with drift report
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

            results[col] = {
                "psi": round(psi, 4),
                "ks_stat": round(ks_stat, 4),
                "ks_p": round(ks_p, 6),
                "drift": drift_flag,
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

        if drift_detected:
            logger.warning(
                "Drift detected in %d/%d features (%.0f%%): %s",
                len(drifted_features),
                n_features_checked,
                drift_pct,
                drifted_features[:5],
            )
        else:
            logger.info(
                "No drift detected across %d features", n_features_checked
            )

        return {
            "drift_detected": drift_detected,
            "drifted_features": drifted_features,
            "n_features_checked": n_features_checked,
            "n_drifted": len(drifted_features),
            "drift_pct": round(drift_pct, 1),
            "feature_details": results,
        }

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
                bin_samples = np.random.uniform(edges[i], edges[i + 1], size=n_in_bin)
                ref_samples.append(bin_samples)
            ref_samples = np.concatenate(ref_samples)

            stat, p = ks_2samp(ref_samples, values)
            return float(stat), float(p)
        except ImportError:
            return 0.0, 1.0
