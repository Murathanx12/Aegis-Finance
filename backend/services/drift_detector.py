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

        # Feature-group decomposition: breaks the flat drift list into
        # interpretable categories so users can see WHAT is drifting
        group_patterns = config["ml"].get("drift", {}).get("feature_groups")
        if group_patterns and results:
            report["group_drift"] = self._group_drift_summary(
                results, group_patterns, feature_importances,
            )

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
    def _classify_feature(feature_name: str, group_patterns: dict[str, list[str]]) -> str:
        """Classify a feature into a group based on config patterns.

        Args:
            feature_name: Feature column name
            group_patterns: {group_name: [prefix_patterns]} from config

        Returns:
            Group name, or "other" if no pattern matches.
        """
        for group, patterns in group_patterns.items():
            for pat in patterns:
                if pat in feature_name:
                    return group
        return "other"

    @staticmethod
    def _group_drift_summary(
        feature_details: dict,
        group_patterns: dict[str, list[str]],
        feature_importances: Optional[dict[str, float]] = None,
    ) -> dict[str, dict]:
        """Compute per-group drift summary.

        Returns:
            {group_name: {
                n_features, n_drifted, drift_pct, mean_psi,
                importance_weight (if importances given),
                top_drifted: [feature names with highest PSI]
            }}
        """
        groups: dict[str, list[tuple[str, dict]]] = {}
        for feat, detail in feature_details.items():
            group = DriftDetector._classify_feature(feat, group_patterns)
            groups.setdefault(group, []).append((feat, detail))

        # Normalize importances if available
        imp_sum = 0.0
        if feature_importances:
            imp_sum = sum(
                feature_importances.get(f, 0.0) for f in feature_details
            )

        summary = {}
        for group, members in sorted(groups.items()):
            n = len(members)
            drifted = [(f, d) for f, d in members if d["drift"]]
            n_drifted = len(drifted)
            psi_values = [d["psi"] for _, d in members]
            mean_psi = float(np.mean(psi_values)) if psi_values else 0.0

            entry: dict = {
                "n_features": n,
                "n_drifted": n_drifted,
                "drift_pct": round(n_drifted / n * 100, 1) if n > 0 else 0.0,
                "mean_psi": round(mean_psi, 4),
            }

            # Top drifted features by PSI (max 3)
            drifted_by_psi = sorted(drifted, key=lambda x: x[1]["psi"], reverse=True)
            entry["top_drifted"] = [f for f, _ in drifted_by_psi[:3]]

            # Importance weight of this group (what fraction of model importance it carries)
            if feature_importances and imp_sum > 0:
                group_imp = sum(
                    feature_importances.get(f, 0.0) for f, _ in members
                )
                entry["importance_weight"] = round(group_imp / imp_sum, 4)

            summary[group] = entry

        return summary

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

        # Generate human-readable narrative from group drift
        if "group_drift" in report:
            report["drift_narrative"] = DriftDetector._build_narrative(
                report["group_drift"],
                report["effective_severity"],
            )

        return report

    @staticmethod
    def _build_narrative(
        group_drift: dict[str, dict],
        effective_severity: str,
    ) -> str:
        """Build a one-sentence human-readable drift summary.

        Examples:
            "Momentum and volatility features are drifting (expected in trending markets),
             but macro indicators remain stable — model reliability is moderate."
        """
        high_drift = []  # groups with >60% drift
        moderate_drift = []  # 20-60%
        stable = []  # <20%

        for group, info in group_drift.items():
            pct = info["drift_pct"]
            if pct >= 60:
                high_drift.append(group)
            elif pct >= 20:
                moderate_drift.append(group)
            else:
                stable.append(group)

        parts = []
        if high_drift:
            names = ", ".join(sorted(high_drift))
            parts.append(f"{names} features are drifting significantly")
        if stable:
            names = ", ".join(sorted(stable))
            parts.append(f"{names} remain stable")

        if not parts:
            return f"Drift severity: {effective_severity}"

        narrative = "; ".join(parts)
        narrative += f" — effective severity: {effective_severity}"
        return narrative

    @staticmethod
    def from_multi_scale(
        features: pd.DataFrame,
        feature_importances: Optional[dict[str, float]] = None,
        scales: Optional[list[dict]] = None,
        **kwargs,
    ) -> dict:
        """Multi-scale drift detection: checks drift at multiple time horizons.

        Financial features are non-stationary by nature. A 2-year vs 1-year
        comparison (the default single-scale approach) will almost always show
        high drift after a regime change — even when the model is tracking
        recent patterns well.

        Multi-scale detection fixes this by checking at three horizons:
          - Long:  504 ref / 252 inf  (2yr vs 1yr — structural shifts)
          - Medium: 252 ref / 126 inf (1yr vs 6mo — recent trend changes)
          - Short:  126 ref / 63 inf  (6mo vs 1Q — immediate stability)

        Decision logic:
          - If short-scale drift is low/moderate, the model is tracking well
            regardless of long-term drift → effective severity from short scale
          - If ALL scales show high/critical drift, the model is genuinely
            degraded → effective severity stays critical
          - Importance weighting still applies at each scale

        Args:
            features: Full feature matrix (DatetimeIndex, chronologically sorted)
            feature_importances: Optional importance weights from crash model
            scales: Override the default scales. List of dicts with
                    {name, reference_days, inference_days} entries.
            **kwargs: Passed to DriftDetector.__init__

        Returns:
            dict with:
              - All fields from from_rolling_window() (backward compatible)
              - multi_scale: per-scale drift reports
              - scale_used: which scale determined effective_severity
              - recent_stability: "stable" / "degrading" / "unstable"
        """
        drift_cfg = config["ml"].get("drift", {})
        if scales is None:
            scales = drift_cfg.get("multi_scale_windows", [
                {"name": "long", "reference_days": 504, "inference_days": 252},
                {"name": "medium", "reference_days": 252, "inference_days": 126},
                {"name": "short", "reference_days": 126, "inference_days": 63},
            ])

        n = len(features)
        scale_reports = {}
        severities = {}
        full_reports = {}  # cache full reports to avoid recomputation

        for scale in scales:
            name = scale["name"]
            ref_days = scale["reference_days"]
            inf_days = scale["inference_days"]
            total = ref_days + inf_days

            if n < total:
                # Not enough data for this scale — skip
                continue

            report = DriftDetector.from_rolling_window(
                features,
                reference_days=ref_days,
                inference_days=inf_days,
                feature_importances=feature_importances,
                **kwargs,
            )
            full_reports[name] = report

            scale_reports[name] = {
                "severity": report.get("severity", "none"),
                "effective_severity": report.get("effective_severity", "none"),
                "drift_pct": report.get("drift_pct", 0),
                "n_drifted": report.get("n_drifted", 0),
                "n_features_checked": report.get("n_features_checked", 0),
                "reference_window": ref_days,
                "inference_window": inf_days,
            }
            if "importance_weighted_drift_pct" in report:
                scale_reports[name]["importance_weighted_drift_pct"] = report[
                    "importance_weighted_drift_pct"
                ]
            severities[name] = report.get("effective_severity", "none")

        if not scale_reports:
            # Fallback to single-scale
            return DriftDetector.from_rolling_window(
                features,
                feature_importances=feature_importances,
                **kwargs,
            )

        # Determine effective severity using shortest stable scale.
        # Severity ordering for comparison
        sev_order = {"none": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}

        # Use the primary (long) scale as the base report (reuse cached)
        primary_name = scales[0]["name"]
        if primary_name in full_reports:
            primary_report = full_reports[primary_name]
        else:
            # Primary scale was skipped (insufficient data) — use first available
            primary_name = next(iter(scale_reports))
            primary_report = full_reports[primary_name]

        # Find the shortest scale with acceptable drift
        scale_used = primary_name
        best_severity = severities.get(primary_name, "critical")

        for scale in reversed(scales):  # shortest first
            name = scale["name"]
            if name not in severities:
                continue
            sev = severities[name]
            if sev_order.get(sev, 4) <= sev_order["moderate"]:
                # This shorter scale shows acceptable drift
                best_severity = sev
                scale_used = name
                break

        # Classify recent stability using the best non-primary scale.
        # Use the minimum severity among all non-primary scales because
        # the KS test can produce false positives at very small windows
        # (e.g., 63 inference samples), so the most reliable short-term
        # signal is the best one across medium and short scales.
        non_primary = [s["name"] for s in scales[1:] if s["name"] in severities]
        if non_primary:
            best_recent_ord = min(
                sev_order.get(severities[n], 4) for n in non_primary
            )
        else:
            best_recent_ord = sev_order.get(
                severities.get(scales[0]["name"], "none"), 0
            )

        if best_recent_ord <= sev_order["low"]:
            recent_stability = "stable"
        elif best_recent_ord <= sev_order["moderate"]:
            recent_stability = "degrading"
        else:
            recent_stability = "unstable"

        # Override effective severity based on multi-scale analysis
        primary_report["effective_severity"] = best_severity
        primary_report["multi_scale"] = scale_reports
        primary_report["scale_used"] = scale_used
        primary_report["recent_stability"] = recent_stability

        # Rebuild narrative if group_drift is available
        if "group_drift" in primary_report:
            primary_report["drift_narrative"] = DriftDetector._build_narrative(
                primary_report["group_drift"],
                best_severity,
            )

        # Add a human-readable multi-scale summary
        primary_report["multi_scale_summary"] = (
            DriftDetector._build_multi_scale_summary(
                scale_reports, best_severity, scale_used, recent_stability,
            )
        )

        return primary_report

    @staticmethod
    def _build_multi_scale_summary(
        scale_reports: dict,
        effective_severity: str,
        scale_used: str,
        recent_stability: str,
    ) -> str:
        """Build human-readable multi-scale summary."""
        parts = []
        for name, info in scale_reports.items():
            sev = info["effective_severity"]
            pct = info["drift_pct"]
            parts.append(f"{name}: {sev} ({pct:.0f}%)")

        summary = "Drift by scale: " + ", ".join(parts)
        if recent_stability == "stable":
            summary += f". Recent data is stable — effective severity: {effective_severity}"
        elif recent_stability == "degrading":
            summary += f". Recent data showing moderate drift — effective severity: {effective_severity}"
        else:
            summary += f". Drift across all scales — effective severity: {effective_severity}"

        return summary

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
