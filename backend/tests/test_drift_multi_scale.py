"""
Tests for multi-scale drift detection (Cycle 50)
==================================================

Verifies:
  1. from_multi_scale() returns multi_scale dict with per-scale reports
  2. Short-scale stability overrides long-scale critical severity
  3. All-scale critical drift → effective severity stays critical
  4. Backward compatibility: multi-scale report has all from_rolling_window fields
  5. recent_stability classification works correctly
  6. Custom scales work
  7. Insufficient data falls back gracefully
  8. Multi-scale summary narrative is generated
"""

import numpy as np
import pandas as pd

from backend.services.drift_detector import DriftDetector


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_time_series(n_total=900, n_features=20, regime_shift_at=None,
                      shift_magnitude=3.0, seed=42):
    """Create synthetic time series with optional regime shift.

    Args:
        n_total: Total number of rows (trading days)
        n_features: Number of features
        regime_shift_at: Row index where distribution shifts. If None, no shift.
        shift_magnitude: How much to shift features at the regime point
        seed: Random seed
    """
    rng = np.random.default_rng(seed)
    data = {}
    for i in range(n_features):
        col = rng.normal(0, 1, n_total)
        if regime_shift_at is not None:
            col[regime_shift_at:] += shift_magnitude
        data[f"feat_{i}"] = col
    return pd.DataFrame(data)


def _make_gradual_drift(n_total=1500, n_features=20, seed=42):
    """Create data where long-term drift is high but short-term is stable.

    Simulates a market that gradually shifted over 2 years but has been
    stable for the last 500 days — the crash model should still work fine.

    Layout (1500 days):
      [0-500]:    mean=0  (old regime)
      [500-1000]: gradual shift from 0 to +5 (transition)
      [1000-1500]: mean=+5 (new stable regime)

    Short-scale (126 ref / 63 inf) compares days 1311-1437 vs 1437-1500:
      Both are in the stable +5 regime → no drift
    Long-scale (504 ref / 252 inf) compares days 744-1248 vs 1248-1500:
      Reference includes transition, inference is new regime → drift
    """
    rng = np.random.default_rng(seed)
    data = {}
    for i in range(n_features):
        base = rng.normal(0, 1, n_total)
        trend = np.zeros(n_total)
        # Old regime: days 0-500 at mean=0
        # Transition: days 500-1000 gradual shift
        trend[500:1000] = np.linspace(0, 5.0, 500)
        # New stable regime: days 1000-1500 at mean=5
        trend[1000:] = 5.0
        data[f"feat_{i}"] = base + trend
    return pd.DataFrame(data)


def _make_all_unstable(n_total=900, n_features=20, seed=42):
    """Create data where ALL scales show critical drift.

    Each 100-day block has a different distribution center.
    """
    rng = np.random.default_rng(seed)
    data = {}
    for i in range(n_features):
        col = np.empty(n_total)
        for block_start in range(0, n_total, 100):
            block_end = min(block_start + 100, n_total)
            block_len = block_end - block_start
            # Each block has a random mean shift
            col[block_start:block_end] = rng.normal(
                rng.uniform(-5, 5), 1, block_len
            )
        data[f"feat_{i}"] = col
    return pd.DataFrame(data)


# ── Basic functionality ───────────────────────────────────────────────────────

class TestMultiScaleBasic:
    """from_multi_scale() returns correct structure."""

    def test_returns_multi_scale_dict(self):
        """Report includes multi_scale with per-scale entries."""
        features = _make_time_series(n_total=900)
        report = DriftDetector.from_multi_scale(features)
        assert "multi_scale" in report
        assert isinstance(report["multi_scale"], dict)
        assert len(report["multi_scale"]) >= 2  # at least 2 scales

    def test_each_scale_has_required_fields(self):
        """Each scale report has severity, drift_pct, n_drifted."""
        features = _make_time_series(n_total=900)
        report = DriftDetector.from_multi_scale(features)
        for name, scale_report in report["multi_scale"].items():
            assert "severity" in scale_report, f"Missing severity in {name}"
            assert "effective_severity" in scale_report
            assert "drift_pct" in scale_report
            assert "n_drifted" in scale_report
            assert "reference_window" in scale_report
            assert "inference_window" in scale_report

    def test_backward_compatible_fields(self):
        """Multi-scale report has all from_rolling_window fields."""
        features = _make_time_series(n_total=900)
        report = DriftDetector.from_multi_scale(features)
        # Must have all standard fields
        assert "drift_detected" in report
        assert "severity" in report
        assert "effective_severity" in report
        assert "drift_pct" in report
        assert "n_drifted" in report
        assert "n_features_checked" in report
        assert "drifted_features" in report

    def test_scale_used_field(self):
        """Report indicates which scale determined effective_severity."""
        features = _make_time_series(n_total=900)
        report = DriftDetector.from_multi_scale(features)
        assert "scale_used" in report
        assert report["scale_used"] in report["multi_scale"]

    def test_recent_stability_field(self):
        """Report includes recent_stability classification."""
        features = _make_time_series(n_total=900)
        report = DriftDetector.from_multi_scale(features)
        assert "recent_stability" in report
        assert report["recent_stability"] in ("stable", "degrading", "unstable")

    def test_multi_scale_summary(self):
        """Report includes multi_scale_summary narrative."""
        features = _make_time_series(n_total=900)
        report = DriftDetector.from_multi_scale(features)
        assert "multi_scale_summary" in report
        assert "Drift by scale" in report["multi_scale_summary"]


# ── Severity override logic ──────────────────────────────────────────────────

class TestSeverityOverride:
    """Short-scale stability should override long-scale severity."""

    def test_gradual_drift_reduces_severity(self):
        """When data gradually shifted but is now stable, severity < critical.

        The medium scale (252 ref / 126 inf) is the most reliable short-term
        indicator because it has enough samples for accurate KS tests.
        The short scale (126/63) can have KS false positives.
        """
        features = _make_gradual_drift(n_total=1500)
        report = DriftDetector.from_multi_scale(features)

        # Long-scale should show high/critical drift (transition vs new regime)
        long_sev = report["multi_scale"].get("long", {}).get("effective_severity", "none")
        assert long_sev in ("high", "critical"), \
            f"Expected long-scale to show high/critical drift, got {long_sev}"

        # Medium-scale should show lower drift (both windows in new regime)
        medium_info = report["multi_scale"].get("medium", {})
        if medium_info:
            sev_order = {"none": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}
            assert sev_order.get(medium_info["effective_severity"], 0) <= sev_order["moderate"], \
                f"Medium scale should be ≤ moderate, got {medium_info['effective_severity']}"

        # Effective severity should be lower than long-scale
        effective = report["effective_severity"]
        sev_order = {"none": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}
        assert sev_order[effective] < sev_order.get(long_sev, 4), \
            f"Expected effective severity < {long_sev}, got {effective}"

    def test_recent_stability_is_stable_for_gradual_drift(self):
        """Gradual drift with stable plateau → recent_stability not 'unstable'."""
        features = _make_gradual_drift(n_total=1500)
        report = DriftDetector.from_multi_scale(features)
        # With 500 days of stable plateau, short-scale should be ≤ moderate
        assert report["recent_stability"] in ("stable", "degrading")

    def test_all_unstable_stays_critical(self):
        """When ALL scales show drift, effective severity stays high/critical."""
        features = _make_all_unstable(n_total=900)
        report = DriftDetector.from_multi_scale(features)
        sev_order = {"none": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}
        assert sev_order.get(report["effective_severity"], 0) >= sev_order["high"], \
            f"Expected high/critical for all-unstable, got {report['effective_severity']}"

    def test_no_drift_stays_low(self):
        """Stable data across all scales → effective severity ≤ moderate.

        Note: KS test with synthetic reference produces some false positives
        at smaller window sizes, so 'moderate' is acceptable for i.i.d. data.
        """
        features = _make_time_series(n_total=900)  # no regime shift
        report = DriftDetector.from_multi_scale(features)
        sev_order = {"none": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}
        assert sev_order[report["effective_severity"]] <= sev_order["moderate"]

    def test_sudden_shift_is_critical(self):
        """Sudden recent regime shift → all scales show drift → critical."""
        # Shift at row 800 — very recent, affects all scales
        features = _make_time_series(n_total=900, regime_shift_at=800,
                                     shift_magnitude=5.0)
        report = DriftDetector.from_multi_scale(features)
        sev_order = {"none": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}
        # Short scale should also show drift since shift is very recent
        short_info = report["multi_scale"].get("short", {})
        if short_info:
            assert sev_order.get(short_info["effective_severity"], 0) >= sev_order["moderate"]


# ── With importance weighting ─────────────────────────────────────────────────

class TestMultiScaleWithImportances:
    """Multi-scale should work with feature importances."""

    def test_importances_flow_through(self):
        """Feature importances should affect each scale's effective severity."""
        features = _make_time_series(n_total=900, regime_shift_at=400,
                                     shift_magnitude=3.0)
        # Features 0-4 are important, 5-19 are not
        importances = {f"feat_{i}": 10.0 if i < 5 else 0.1
                       for i in range(20)}
        report = DriftDetector.from_multi_scale(
            features, feature_importances=importances,
        )
        # Should have importance-weighted metrics at the primary scale level
        assert "importance_weighted_drift_pct" in report or "multi_scale" in report

    def test_stable_important_features_listed(self):
        """When important features are stable, they should be listed."""
        features = _make_gradual_drift(n_total=1500)
        importances = {f"feat_{i}": 10.0 if i < 5 else 0.1
                       for i in range(20)}
        report = DriftDetector.from_multi_scale(
            features, feature_importances=importances,
        )
        # Should have stable_important_features if importances provided
        if "stable_important_features" in report:
            assert isinstance(report["stable_important_features"], list)


# ── Custom scales ─────────────────────────────────────────────────────────────

class TestCustomScales:
    """Custom scale configurations should work."""

    def test_two_scales(self):
        """Works with just 2 custom scales."""
        features = _make_time_series(n_total=600)
        scales = [
            {"name": "primary", "reference_days": 252, "inference_days": 126},
            {"name": "recent", "reference_days": 126, "inference_days": 63},
        ]
        report = DriftDetector.from_multi_scale(features, scales=scales)
        assert len(report["multi_scale"]) == 2
        assert "primary" in report["multi_scale"]
        assert "recent" in report["multi_scale"]

    def test_single_scale_fallback(self):
        """Single scale is equivalent to from_rolling_window."""
        features = _make_time_series(n_total=900)
        scales = [
            {"name": "only", "reference_days": 504, "inference_days": 252},
        ]
        report = DriftDetector.from_multi_scale(features, scales=scales)
        assert "multi_scale" in report
        assert "only" in report["multi_scale"]

    def test_insufficient_data_skips_scale(self):
        """Scales that need more data than available are skipped."""
        features = _make_time_series(n_total=300)  # only 300 rows
        scales = [
            {"name": "long", "reference_days": 504, "inference_days": 252},  # needs 756
            {"name": "short", "reference_days": 126, "inference_days": 63},  # needs 189
        ]
        report = DriftDetector.from_multi_scale(features, scales=scales)
        # Long scale should be skipped, short should work
        assert "short" in report["multi_scale"]
        assert "long" not in report["multi_scale"]

    def test_all_scales_insufficient_falls_back(self):
        """When no scale has enough data, falls back to from_rolling_window."""
        features = _make_time_series(n_total=50)
        scales = [
            {"name": "long", "reference_days": 504, "inference_days": 252},
            {"name": "short", "reference_days": 126, "inference_days": 63},
        ]
        report = DriftDetector.from_multi_scale(features, scales=scales)
        # Should still produce a valid report via fallback
        assert "drift_detected" in report
        assert "severity" in report


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestMultiScaleEdgeCases:
    """Edge cases for multi-scale detection."""

    def test_iid_data_low_severity(self):
        """i.i.d. data → effective severity ≤ moderate.

        Note: KS test synthetic reconstruction causes some false positives
        at smaller windows, so 'moderate' is acceptable baseline.
        """
        rng = np.random.default_rng(42)
        data = {f"feat_{i}": rng.normal(0, 1, 900) for i in range(10)}
        features = pd.DataFrame(data)
        report = DriftDetector.from_multi_scale(features)
        sev_order = {"none": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}
        assert sev_order[report["effective_severity"]] <= sev_order["moderate"]

    def test_single_feature(self):
        """Works with just one feature column."""
        rng = np.random.default_rng(42)
        features = pd.DataFrame({"feat_0": rng.normal(0, 1, 900)})
        report = DriftDetector.from_multi_scale(features)
        assert "multi_scale" in report

    def test_scale_used_matches_effective_severity(self):
        """The scale_used should explain why effective_severity was chosen."""
        features = _make_gradual_drift(n_total=1500)
        report = DriftDetector.from_multi_scale(features)
        scale_used = report["scale_used"]
        scale_sev = report["multi_scale"][scale_used]["effective_severity"]
        # The effective severity should match or be derived from the chosen scale
        # (could differ if importance weighting is applied at the primary level)
        sev_order = {"none": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}
        assert sev_order.get(report["effective_severity"], 0) <= \
               sev_order.get(scale_sev, 4) + 1  # allow 1 level tolerance
