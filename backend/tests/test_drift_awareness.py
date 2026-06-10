"""
Tests for drift-aware prediction pipeline (Phase 4.5)
======================================================

Verifies:
  1. Signal engine reduces crash_prob weight under drift
  2. Drift severity propagates into signal output
  3. Config-driven confidence multipliers work correctly
  4. Backward compatibility: no drift_severity → no change
"""

from backend.services.signal_engine import get_market_signal
from backend.config import config


# ── Baseline signal parameters (normal market conditions) ────────────────────

_BASE_KWARGS = dict(
    crash_prob_3m=15.0,
    crash_prob_12m=25.0,
    regime="Bull",
    risk_score=0.5,
    sp500_1m_return=2.0,
    sp500_3m_return=5.0,
    sp500_ytd_return=8.0,
    vix=18.0,
    yield_curve=1.0,
    external_consensus="BULLISH",
    drawdown_pct=-3.0,
)


class TestDriftAwareSignalWeighting:
    """Signal engine should reduce crash_prob weight when drift is significant."""

    def test_no_drift_no_change(self):
        """No drift severity → signal unchanged from pre-drift behavior."""
        sig_none = get_market_signal(**_BASE_KWARGS, drift_severity=None)
        sig_no_drift = get_market_signal(**_BASE_KWARGS, drift_severity="none")
        assert sig_none["composite_score"] == sig_no_drift["composite_score"]

    def test_low_drift_no_change(self):
        """Low drift → weight multiplier is 1.0, signal unchanged."""
        sig_none = get_market_signal(**_BASE_KWARGS, drift_severity="none")
        sig_low = get_market_signal(**_BASE_KWARGS, drift_severity="low")
        assert sig_none["composite_score"] == sig_low["composite_score"]

    def test_critical_drift_changes_signal(self):
        """Critical drift → crash_prob weight reduced, signal changes."""
        sig_none = get_market_signal(**_BASE_KWARGS, drift_severity="none")
        sig_critical = get_market_signal(**_BASE_KWARGS, drift_severity="critical")
        assert sig_none["composite_score"] != sig_critical["composite_score"]

    def test_high_drift_changes_signal(self):
        """High drift → signal should differ from no-drift."""
        sig_none = get_market_signal(**_BASE_KWARGS, drift_severity="none")
        sig_high = get_market_signal(**_BASE_KWARGS, drift_severity="high")
        assert sig_none["composite_score"] != sig_high["composite_score"]

    def test_moderate_drift_changes_signal(self):
        """Moderate drift → signal should differ from no-drift."""
        sig_none = get_market_signal(**_BASE_KWARGS, drift_severity="none")
        sig_mod = get_market_signal(**_BASE_KWARGS, drift_severity="moderate")
        assert sig_none["composite_score"] != sig_mod["composite_score"]

    def test_drift_severity_monotonic_effect(self):
        """Higher drift severity → larger deviation from no-drift signal."""
        sig_none = get_market_signal(**_BASE_KWARGS, drift_severity="none")
        sig_mod = get_market_signal(**_BASE_KWARGS, drift_severity="moderate")
        sig_high = get_market_signal(**_BASE_KWARGS, drift_severity="high")
        sig_crit = get_market_signal(**_BASE_KWARGS, drift_severity="critical")

        delta_mod = abs(sig_none["composite_score"] - sig_mod["composite_score"])
        delta_high = abs(sig_none["composite_score"] - sig_high["composite_score"])
        delta_crit = abs(sig_none["composite_score"] - sig_crit["composite_score"])

        assert delta_mod <= delta_high <= delta_crit


class TestDriftMetadataInSignal:
    """Signal output should include drift metadata when severity > none."""

    def test_no_drift_no_metadata(self):
        """No drift → output has no drift_severity key."""
        sig = get_market_signal(**_BASE_KWARGS, drift_severity="none")
        assert "drift_severity" not in sig

    def test_critical_drift_has_metadata(self):
        """Critical drift → output includes drift_severity and weight multiplier."""
        sig = get_market_signal(**_BASE_KWARGS, drift_severity="critical")
        assert sig["drift_severity"] == "critical"
        assert sig["drift_crash_weight_mult"] == 0.2

    def test_moderate_drift_has_metadata(self):
        sig = get_market_signal(**_BASE_KWARGS, drift_severity="moderate")
        assert sig["drift_severity"] == "moderate"
        assert sig["drift_crash_weight_mult"] == 0.7

    def test_drift_reason_in_reasons(self):
        """Critical drift → a drift reason appears in the reasons list."""
        sig = get_market_signal(**_BASE_KWARGS, drift_severity="critical")
        drift_reasons = [r for r in sig["reasons"] if "drift" in r.lower()]
        assert len(drift_reasons) >= 1


class TestDriftConfidenceConfig:
    """Config-driven confidence multipliers are correctly structured."""

    def test_confidence_multiplier_exists(self):
        drift_cfg = config["ml"]["drift"]
        assert "confidence_multiplier" in drift_cfg

    def test_all_severities_have_multiplier(self):
        mult = config["ml"]["drift"]["confidence_multiplier"]
        for severity in ["none", "low", "moderate", "high", "critical"]:
            assert severity in mult
            assert 0 < mult[severity] <= 1.0

    def test_multipliers_decrease_with_severity(self):
        mult = config["ml"]["drift"]["confidence_multiplier"]
        assert mult["none"] >= mult["low"] >= mult["moderate"] >= mult["high"] >= mult["critical"]

    def test_signal_weight_multiplier_exists(self):
        mult = config["ml"]["drift"]["signal_weight_multiplier"]
        for severity in ["none", "low", "moderate", "high", "critical"]:
            assert severity in mult
            assert 0 < mult[severity] <= 1.0


class TestBackwardCompatibility:
    """Existing callers without drift_severity should work unchanged."""

    def test_no_drift_param(self):
        """Calling without drift_severity at all should work."""
        sig = get_market_signal(**_BASE_KWARGS)
        assert "action" in sig
        assert "composite_score" in sig
        assert "confidence" in sig

    def test_none_drift_same_as_omitted(self):
        """drift_severity=None should produce same result as omitting it."""
        sig_omitted = get_market_signal(**_BASE_KWARGS)
        sig_none = get_market_signal(**_BASE_KWARGS, drift_severity=None)
        assert sig_omitted["composite_score"] == sig_none["composite_score"]

    def test_unknown_severity_treated_as_none(self):
        """Unknown severity string → multiplier defaults to 1.0 (no effect)."""
        sig_none = get_market_signal(**_BASE_KWARGS, drift_severity="none")
        sig_unknown = get_market_signal(**_BASE_KWARGS, drift_severity="unknown_level")
        assert sig_none["composite_score"] == sig_unknown["composite_score"]
