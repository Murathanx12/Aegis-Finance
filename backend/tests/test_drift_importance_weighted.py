"""
Tests for importance-weighted drift detection (Cycle 42)
=========================================================

Verifies:
  1. Importance-weighted drift % is computed correctly
  2. Weighted severity can differ from raw severity
  3. Drift direction attribution works
  4. Stable important features are identified
  5. Backward compatibility: no importances → raw drift unchanged
  6. Integration with from_rolling_window()
"""

import numpy as np
import pandas as pd
import pytest

from backend.services.drift_detector import DriftDetector


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_data(n_ref=504, n_inf=252, n_features=10, drift_features=None,
               drift_mean_shift=3.0, seed=42):
    """Create synthetic reference + inference data with controlled drift.

    Args:
        drift_features: list of feature indices that should drift (mean shift)
    """
    rng = np.random.default_rng(seed)
    drift_features = drift_features or []

    ref_data = {}
    inf_data = {}
    for i in range(n_features):
        ref_data[f"feat_{i}"] = rng.normal(0, 1, n_ref)
        if i in drift_features:
            inf_data[f"feat_{i}"] = rng.normal(drift_mean_shift, 1, n_inf)
        else:
            inf_data[f"feat_{i}"] = rng.normal(0, 1, n_inf)

    ref_df = pd.DataFrame(ref_data)
    inf_df = pd.DataFrame(inf_data)
    full_df = pd.concat([ref_df, inf_df], ignore_index=True)
    return ref_df, inf_df, full_df


def _make_importances(n_features=10, important_indices=None):
    """Create feature importance dict where specified features are important."""
    important_indices = important_indices or [0, 1]
    imp = {}
    for i in range(n_features):
        if i in important_indices:
            imp[f"feat_{i}"] = 10.0  # high importance
        else:
            imp[f"feat_{i}"] = 0.1   # low importance
    return imp


# ── Core importance-weighted drift ─────────────────────────────────────────────

class TestImportanceWeightedDrift:
    """Importance-weighted drift should reflect model reliance on drifted features."""

    def test_low_importance_drift_reduces_weighted_pct(self):
        """When only low-importance features drift, weighted drift is much lower."""
        # Features 2-9 drift (low importance), features 0-1 stable (high importance)
        ref_df, inf_df, _ = _make_data(
            n_features=10, drift_features=[2, 3, 4, 5, 6, 7, 8, 9],
        )
        importances = _make_importances(n_features=10, important_indices=[0, 1])

        detector = DriftDetector(ref_df)
        report = detector.check_drift(inf_df, feature_importances=importances)

        # Raw drift is 80% (8/10 features)
        assert report["drift_pct"] >= 70.0

        # Importance-weighted drift should be MUCH lower because the drifted
        # features only account for ~8% of total importance (8 × 0.1 / (2×10 + 8×0.1))
        assert "importance_weighted_drift_pct" in report
        assert report["importance_weighted_drift_pct"] < 20.0

    def test_high_importance_drift_keeps_weighted_pct_high(self):
        """When important features drift, weighted drift stays high."""
        # Features 0-1 drift (high importance), features 2-9 stable
        ref_df, inf_df, _ = _make_data(
            n_features=10, drift_features=[0, 1],
        )
        importances = _make_importances(n_features=10, important_indices=[0, 1])

        detector = DriftDetector(ref_df)
        report = detector.check_drift(inf_df, feature_importances=importances)

        # Raw drift is 20% (2/10 features)
        assert report["drift_pct"] <= 30.0

        # But importance-weighted drift is HIGH because the 2 drifted features
        # account for ~96% of total importance
        assert report["importance_weighted_drift_pct"] > 80.0

    def test_no_drift_weighted_is_zero(self):
        """When no features drift, weighted drift is also 0."""
        ref_df, inf_df, _ = _make_data(n_features=5, drift_features=[])
        importances = _make_importances(n_features=5, important_indices=[0, 1])

        detector = DriftDetector(ref_df)
        report = detector.check_drift(inf_df, feature_importances=importances)

        assert report["drift_pct"] == 0.0
        assert report["importance_weighted_drift_pct"] == 0.0

    def test_all_drift_weighted_is_100(self):
        """When all features drift, weighted drift is ~100% regardless of weights."""
        ref_df, inf_df, _ = _make_data(
            n_features=5, drift_features=[0, 1, 2, 3, 4],
        )
        importances = _make_importances(n_features=5, important_indices=[0])

        detector = DriftDetector(ref_df)
        report = detector.check_drift(inf_df, feature_importances=importances)

        assert report["importance_weighted_drift_pct"] > 95.0

    def test_uniform_importances_match_raw(self):
        """When all features have equal importance, weighted ≈ raw."""
        ref_df, inf_df, _ = _make_data(
            n_features=10, drift_features=[0, 1, 2, 3, 4],
        )
        uniform_imp = {f"feat_{i}": 1.0 for i in range(10)}

        detector = DriftDetector(ref_df)
        report = detector.check_drift(inf_df, feature_importances=uniform_imp)

        # Should be close to raw drift_pct
        assert abs(report["importance_weighted_drift_pct"] - report["drift_pct"]) < 5.0


# ── Stable important features ─────────────────────────────────────────────────

class TestStableImportantFeatures:
    """Should identify important features that are NOT drifting."""

    def test_stable_features_identified(self):
        """Important features that don't drift should appear in stable list."""
        ref_df, inf_df, _ = _make_data(
            n_features=10, drift_features=[2, 3, 4, 5, 6, 7, 8, 9],
        )
        importances = _make_importances(n_features=10, important_indices=[0, 1])

        detector = DriftDetector(ref_df)
        report = detector.check_drift(inf_df, feature_importances=importances)

        stable = report.get("stable_important_features", [])
        assert "feat_0" in stable
        assert "feat_1" in stable

    def test_drifted_features_not_in_stable(self):
        """Drifted features should NOT appear in stable list."""
        ref_df, inf_df, _ = _make_data(
            n_features=10, drift_features=[0, 1],
        )
        importances = _make_importances(n_features=10, important_indices=[0, 1])

        detector = DriftDetector(ref_df)
        report = detector.check_drift(inf_df, feature_importances=importances)

        stable = report.get("stable_important_features", [])
        assert "feat_0" not in stable
        assert "feat_1" not in stable

    def test_stable_sorted_by_importance(self):
        """Stable features should be sorted by importance (highest first)."""
        ref_df, inf_df, _ = _make_data(
            n_features=10, drift_features=[5, 6, 7, 8, 9],
        )
        # feat_0 most important, feat_1 second, etc.
        importances = {f"feat_{i}": float(10 - i) for i in range(10)}

        detector = DriftDetector(ref_df)
        report = detector.check_drift(inf_df, feature_importances=importances)

        stable = report.get("stable_important_features", [])
        assert len(stable) >= 3
        # Should be sorted: feat_0, feat_1, feat_2, ...
        assert stable[0] == "feat_0"
        assert stable[1] == "feat_1"


# ── Drift direction attribution ───────────────────────────────────────────────

class TestDriftDirection:
    """Per-feature drift direction and spread change."""

    def test_positive_mean_shift(self):
        """Feature that shifted higher should have positive mean_shift."""
        ref_df, inf_df, _ = _make_data(
            n_features=1, drift_features=[0], drift_mean_shift=5.0,
        )
        detector = DriftDetector(ref_df)
        report = detector.check_drift(inf_df)

        detail = report["feature_details"]["feat_0"]
        assert detail["mean_shift"] > 2.0  # shifted up significantly

    def test_negative_mean_shift(self):
        """Feature that shifted lower should have negative mean_shift."""
        ref_df, inf_df, _ = _make_data(
            n_features=1, drift_features=[0], drift_mean_shift=-5.0,
        )
        detector = DriftDetector(ref_df)
        report = detector.check_drift(inf_df)

        detail = report["feature_details"]["feat_0"]
        assert detail["mean_shift"] < -2.0  # shifted down

    def test_no_drift_small_mean_shift(self):
        """Stationary feature should have near-zero mean_shift."""
        ref_df, inf_df, _ = _make_data(
            n_features=1, drift_features=[],
        )
        detector = DriftDetector(ref_df)
        report = detector.check_drift(inf_df)

        detail = report["feature_details"]["feat_0"]
        assert abs(detail["mean_shift"]) < 0.5

    def test_spread_change_present(self):
        """Spread change ratio should be present in feature details."""
        ref_df, inf_df, _ = _make_data(n_features=1, drift_features=[])
        detector = DriftDetector(ref_df)
        report = detector.check_drift(inf_df)

        detail = report["feature_details"]["feat_0"]
        assert "spread_change" in detail
        assert detail["spread_change"] > 0  # always positive ratio


# ── from_rolling_window with importances ───────────────────────────────────────

class TestRollingWindowWithImportances:
    """from_rolling_window() should use importances for effective_severity."""

    def test_effective_severity_lower_with_importances(self):
        """When important features are stable, effective severity < raw severity."""
        rng = np.random.default_rng(42)
        n = 800  # > 504 + 252

        # 10 features: 8 drift, 2 stable (the important ones)
        data = {}
        for i in range(10):
            ref = rng.normal(0, 1, 504)
            if i >= 2:  # drift features 2-9
                inf = rng.normal(4, 1, 296)
            else:  # stable features 0-1
                inf = rng.normal(0, 1, 296)
            data[f"feat_{i}"] = np.concatenate([ref, inf])

        features = pd.DataFrame(data)
        importances = _make_importances(n_features=10, important_indices=[0, 1])

        report = DriftDetector.from_rolling_window(
            features, feature_importances=importances,
        )

        # Raw severity should be high/critical (80% features drift)
        assert report["severity"] in ("high", "critical")

        # Effective severity should be lower
        assert report["effective_severity"] in ("none", "low", "moderate")

        # Both should be present
        assert "importance_weighted_severity" in report
        assert "importance_weighted_drift_pct" in report

    def test_no_importances_effective_equals_raw(self):
        """Without importances, effective_severity == raw severity."""
        rng = np.random.default_rng(42)
        features = pd.DataFrame({"x": rng.normal(0, 1, 1000)})

        report = DriftDetector.from_rolling_window(features)

        assert report["effective_severity"] == report["severity"]
        assert "importance_weighted_drift_pct" not in report

    def test_effective_severity_in_report(self):
        """effective_severity should always be present."""
        rng = np.random.default_rng(42)
        features = pd.DataFrame({"x": rng.normal(0, 1, 1000)})

        report = DriftDetector.from_rolling_window(features)
        assert "effective_severity" in report


# ── Backward compatibility ─────────────────────────────────────────────────────

class TestBackwardCompatibility:
    """Existing callers without feature_importances should work unchanged."""

    def test_check_drift_without_importances(self):
        """check_drift() without importances returns same format as before."""
        ref_df, inf_df, _ = _make_data(n_features=5, drift_features=[0, 1])
        detector = DriftDetector(ref_df)
        report = detector.check_drift(inf_df)

        assert "drift_detected" in report
        assert "drift_pct" in report
        assert "drifted_features" in report
        assert "n_features_checked" in report
        assert "feature_details" in report
        # Should NOT have importance-weighted fields
        assert "importance_weighted_drift_pct" not in report

    def test_from_rolling_window_without_importances(self):
        """from_rolling_window() without importances works as before."""
        rng = np.random.default_rng(42)
        features = pd.DataFrame({"x": rng.normal(0, 1, 1000)})

        report = DriftDetector.from_rolling_window(features)

        assert "severity" in report
        assert "reference_window" in report
        assert "inference_window" in report
        assert report["effective_severity"] == report["severity"]
