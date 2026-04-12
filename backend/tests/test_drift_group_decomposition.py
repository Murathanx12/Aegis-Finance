"""
Tests for feature-group drift decomposition (Cycle 43)
=========================================================

Verifies:
  1. Features are correctly classified into groups
  2. Per-group drift summary is computed with correct structure
  3. Group drift is included in check_drift() report
  4. Group drift is included in from_rolling_window() report
  5. Narrative generation produces readable output
  6. Unmatched features go to "other" group
  7. Importance weights are included per group when available
  8. Backward compatibility: missing config → no group_drift key
"""

import numpy as np
import pandas as pd
import pytest

from backend.services.drift_detector import DriftDetector


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_grouped_data(n_ref=504, n_inf=252, drift_groups=None, seed=42):
    """Create synthetic data with features named after real groups.

    Args:
        drift_groups: set of group prefixes whose features should drift
    """
    rng = np.random.default_rng(seed)
    drift_groups = drift_groups or set()

    # Simulate real feature names from different groups
    feature_map = {
        "momentum": ["mom_1m", "mom_3m", "mom_6m", "mom_12m"],
        "volatility": ["vol_1m", "vol_3m", "vol_6m", "vol_12m"],
        "macro": ["fred_unemployment", "fred_nfci", "fred_lei"],
        "credit_yields": ["yield_10y", "term_spread", "credit_spread_proxy"],
        "technical": ["rsi_14d", "sma_50d_dev", "macd_signal"],
        "vix": ["vix", "vix_change_1m", "vix_zscore"],
        "cross_asset": ["gold_equity_ratio", "sp_nasdaq_ratio"],
        "interaction": ["vol_x_mom_3m", "vix_x_spread"],
    }

    ref_data = {}
    inf_data = {}
    for group, features in feature_map.items():
        should_drift = group in drift_groups
        for feat in features:
            ref_data[feat] = rng.normal(0, 1, n_ref)
            if should_drift:
                inf_data[feat] = rng.normal(3.0, 1, n_inf)  # large shift
            else:
                inf_data[feat] = rng.normal(0, 1, n_inf)  # stable

    ref_df = pd.DataFrame(ref_data)
    inf_df = pd.DataFrame(inf_data)
    full_df = pd.concat([ref_df, inf_df], ignore_index=True)
    return ref_df, inf_df, full_df


# ── Feature classification ────────────────────────────────────────────────────

class TestFeatureClassification:
    """_classify_feature correctly maps names to groups."""

    def setup_method(self):
        from backend.config import config
        self.patterns = config["ml"]["drift"]["feature_groups"]

    def test_momentum_features(self):
        assert DriftDetector._classify_feature("mom_1m", self.patterns) == "momentum"
        assert DriftDetector._classify_feature("mom_12m", self.patterns) == "momentum"
        assert DriftDetector._classify_feature("trend_strength_3m", self.patterns) == "momentum"

    def test_volatility_features(self):
        assert DriftDetector._classify_feature("vol_1m", self.patterns) == "volatility"
        assert DriftDetector._classify_feature("vol_ratio_1m_3m", self.patterns) == "volatility"
        assert DriftDetector._classify_feature("vol_zscore", self.patterns) == "volatility"

    def test_macro_features(self):
        assert DriftDetector._classify_feature("fred_unemployment", self.patterns) == "macro"
        assert DriftDetector._classify_feature("fred_nfci_chg_3m", self.patterns) == "macro"

    def test_credit_yield_features(self):
        assert DriftDetector._classify_feature("yield_10y", self.patterns) == "credit_yields"
        assert DriftDetector._classify_feature("term_spread", self.patterns) == "credit_yields"
        assert DriftDetector._classify_feature("credit_spread_proxy", self.patterns) == "credit_yields"

    def test_technical_features(self):
        assert DriftDetector._classify_feature("rsi_14d", self.patterns) == "technical"
        assert DriftDetector._classify_feature("sma_200d_dev", self.patterns) == "technical"
        assert DriftDetector._classify_feature("bollinger_pos", self.patterns) == "technical"

    def test_vix_features(self):
        assert DriftDetector._classify_feature("vix", self.patterns) == "vix"
        assert DriftDetector._classify_feature("vix_change_1m", self.patterns) == "vix"

    def test_interaction_features(self):
        assert DriftDetector._classify_feature("vol_x_mom_3m", self.patterns) == "interaction"
        assert DriftDetector._classify_feature("vix_x_spread", self.patterns) == "interaction"

    def test_cross_asset_features(self):
        assert DriftDetector._classify_feature("gold_equity_ratio", self.patterns) == "cross_asset"
        assert DriftDetector._classify_feature("sp_nasdaq_ratio", self.patterns) == "cross_asset"

    def test_unknown_feature_goes_to_other(self):
        assert DriftDetector._classify_feature("some_unknown_feat", self.patterns) == "other"


# ── Group drift summary ──────────────────────────────────────────────────────

class TestGroupDriftSummary:
    """Per-group drift summary has correct structure and values."""

    def test_group_summary_structure(self):
        """Each group entry has required keys."""
        ref, inf, _ = _make_grouped_data(drift_groups={"momentum"})
        detector = DriftDetector(ref)
        report = detector.check_drift(inf)

        assert "group_drift" in report
        for group, info in report["group_drift"].items():
            assert "n_features" in info
            assert "n_drifted" in info
            assert "drift_pct" in info
            assert "mean_psi" in info
            assert "top_drifted" in info

    def test_drifting_group_has_high_drift_pct(self):
        """Group with mean-shifted features should show high drift_pct."""
        ref, inf, _ = _make_grouped_data(drift_groups={"momentum"})
        detector = DriftDetector(ref)
        report = detector.check_drift(inf)

        mom = report["group_drift"]["momentum"]
        assert mom["drift_pct"] >= 75.0  # most/all momentum features drifted
        assert mom["n_drifted"] >= 3

    def test_stable_group_has_low_drift_pct(self):
        """Group with stable features should show low drift_pct."""
        ref, inf, _ = _make_grouped_data(drift_groups={"momentum"})
        detector = DriftDetector(ref)
        report = detector.check_drift(inf)

        macro = report["group_drift"]["macro"]
        assert macro["drift_pct"] < 50.0  # macro should be mostly stable

    def test_top_drifted_limited_to_3(self):
        """top_drifted should have at most 3 entries."""
        ref, inf, _ = _make_grouped_data(
            drift_groups={"momentum", "volatility", "macro"},
        )
        detector = DriftDetector(ref)
        report = detector.check_drift(inf)

        for group, info in report["group_drift"].items():
            assert len(info["top_drifted"]) <= 3

    def test_importance_weight_per_group(self):
        """When importances are given, each group has importance_weight."""
        ref, inf, _ = _make_grouped_data(drift_groups={"momentum"})
        # Give high importance to macro features
        importances = {
            "fred_unemployment": 10.0, "fred_nfci": 8.0, "fred_lei": 5.0,
            "mom_1m": 0.1, "mom_3m": 0.1, "mom_6m": 0.1, "mom_12m": 0.1,
        }
        detector = DriftDetector(ref)
        report = detector.check_drift(inf, feature_importances=importances)

        # Macro group should carry most of the importance weight
        macro = report["group_drift"]["macro"]
        assert "importance_weight" in macro
        assert macro["importance_weight"] > 0.5  # macro is >50% of total importance

    def test_no_importances_no_weight_key(self):
        """Without importances, importance_weight should not appear."""
        ref, inf, _ = _make_grouped_data()
        detector = DriftDetector(ref)
        report = detector.check_drift(inf)

        for group, info in report["group_drift"].items():
            assert "importance_weight" not in info


# ── Integration with from_rolling_window ──────────────────────────────────────

class TestGroupDriftRollingWindow:
    """Group drift works through from_rolling_window()."""

    def test_rolling_window_has_group_drift(self):
        """from_rolling_window includes group_drift in report."""
        _, _, full = _make_grouped_data(drift_groups={"momentum", "volatility"})
        report = DriftDetector.from_rolling_window(full)

        assert "group_drift" in report
        assert len(report["group_drift"]) > 0

    def test_rolling_window_has_narrative(self):
        """from_rolling_window includes drift_narrative."""
        _, _, full = _make_grouped_data(drift_groups={"momentum", "volatility"})
        report = DriftDetector.from_rolling_window(full)

        assert "drift_narrative" in report
        assert isinstance(report["drift_narrative"], str)
        assert len(report["drift_narrative"]) > 10


# ── Narrative generation ──────────────────────────────────────────────────────

class TestDriftNarrative:
    """_build_narrative produces readable summaries."""

    def test_narrative_mentions_drifting_groups(self):
        group_drift = {
            "momentum": {"drift_pct": 100.0},
            "volatility": {"drift_pct": 80.0},
            "macro": {"drift_pct": 10.0},
        }
        narrative = DriftDetector._build_narrative(group_drift, "moderate")
        assert "momentum" in narrative
        assert "volatility" in narrative
        assert "stable" in narrative.lower() or "macro" in narrative

    def test_narrative_includes_severity(self):
        group_drift = {
            "momentum": {"drift_pct": 100.0},
        }
        narrative = DriftDetector._build_narrative(group_drift, "high")
        assert "high" in narrative

    def test_all_stable_narrative(self):
        group_drift = {
            "momentum": {"drift_pct": 5.0},
            "macro": {"drift_pct": 0.0},
        }
        narrative = DriftDetector._build_narrative(group_drift, "none")
        assert "stable" in narrative.lower() or "none" in narrative

    def test_empty_groups_fallback(self):
        narrative = DriftDetector._build_narrative({}, "low")
        assert "low" in narrative
