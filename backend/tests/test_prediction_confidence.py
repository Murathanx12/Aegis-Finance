"""
Tests for prediction_confidence.py — drift-aware uncertainty scoring.
"""

from backend.services.prediction_confidence import score_prediction_confidence


class TestPredictionConfidenceBasic:
    """Basic functionality tests."""

    def test_returns_required_keys(self):
        result = score_prediction_confidence(
            mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
        )
        required = {"grade", "score", "components", "drift_severity",
                     "interpretation", "mc_p10", "mc_p90", "mc_median",
                     "adjusted_p10", "adjusted_p90", "interval_widening"}
        assert required.issubset(result.keys())

    def test_score_in_range(self):
        result = score_prediction_confidence(
            mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
        )
        assert 0.0 <= result["score"] <= 1.0

    def test_grade_is_valid(self):
        result = score_prediction_confidence(
            mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
        )
        assert result["grade"] in ("A", "B", "C", "D", "F")

    def test_components_present(self):
        result = score_prediction_confidence(
            mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
        )
        expected_components = {"drift", "mc_spread", "tail_quality",
                                "data_sufficiency", "beta_stability"}
        assert expected_components == set(result["components"].keys())

    def test_all_components_in_range(self):
        result = score_prediction_confidence(
            mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
            garch_nu=8.0, garch_persistence=0.95, data_years=4.0,
            drift_severity="moderate", beta=1.2,
        )
        for name, val in result["components"].items():
            assert 0.0 <= val <= 1.0, f"Component {name}={val} out of range"


class TestDriftImpact:
    """Drift severity should reduce confidence and widen intervals."""

    def test_no_drift_highest_confidence(self):
        no_drift = score_prediction_confidence(
            mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
            drift_severity="none",
        )
        critical = score_prediction_confidence(
            mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
            drift_severity="critical",
        )
        assert no_drift["score"] > critical["score"]

    def test_drift_monotonicity(self):
        """Higher drift severity → strictly lower confidence."""
        severities = ["none", "low", "moderate", "high", "critical"]
        scores = []
        for sev in severities:
            r = score_prediction_confidence(
                mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
                garch_nu=8.0, data_years=5.0, drift_severity=sev,
            )
            scores.append(r["score"])
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], (
                f"Score should decrease: {severities[i]}={scores[i]} vs "
                f"{severities[i+1]}={scores[i+1]}"
            )

    def test_interval_widening_increases_with_drift(self):
        """Higher drift → wider adjusted intervals."""
        no_drift = score_prediction_confidence(
            mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
            drift_severity="none",
        )
        critical = score_prediction_confidence(
            mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
            drift_severity="critical",
        )
        no_drift_width = no_drift["adjusted_p90"] - no_drift["adjusted_p10"]
        critical_width = critical["adjusted_p90"] - critical["adjusted_p10"]
        assert critical_width > no_drift_width

    def test_no_drift_intervals_unchanged(self):
        """With no drift, adjusted intervals equal raw MC intervals."""
        result = score_prediction_confidence(
            mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
            drift_severity="none",
        )
        assert result["adjusted_p10"] == result["mc_p10"]
        assert result["adjusted_p90"] == result["mc_p90"]
        assert result["interval_widening"] == 1.0

    def test_critical_drift_lowers_grade(self):
        """Critical drift should drop grade significantly."""
        good = score_prediction_confidence(
            mc_p10_return=10.0, mc_p90_return=100.0, mc_median_return=50.0,
            garch_nu=15.0, data_years=5.0, drift_severity="none",
        )
        bad = score_prediction_confidence(
            mc_p10_return=10.0, mc_p90_return=100.0, mc_median_return=50.0,
            garch_nu=15.0, data_years=5.0, drift_severity="critical",
        )
        grade_order = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
        assert grade_order[good["grade"]] > grade_order[bad["grade"]]


class TestGARCHImpact:
    """GARCH parameters affect tail quality score."""

    def test_high_nu_better_confidence(self):
        """Higher nu (thinner tails) → higher confidence."""
        thin = score_prediction_confidence(
            mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
            garch_nu=20.0,
        )
        fat = score_prediction_confidence(
            mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
            garch_nu=4.0,
        )
        assert thin["components"]["tail_quality"] > fat["components"]["tail_quality"]

    def test_no_garch_neutral(self):
        """Without GARCH, tail quality defaults to neutral."""
        result = score_prediction_confidence(
            mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
        )
        assert result["components"]["tail_quality"] == 0.5

    def test_high_persistence_penalizes(self):
        """Very high persistence (>0.98) penalizes tail quality."""
        normal = score_prediction_confidence(
            mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
            garch_nu=10.0, garch_persistence=0.90,
        )
        sticky = score_prediction_confidence(
            mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
            garch_nu=10.0, garch_persistence=0.99,
        )
        assert normal["components"]["tail_quality"] > sticky["components"]["tail_quality"]


class TestDataSufficiency:
    """Data sufficiency component tests."""

    def test_5yr_data_full_score(self):
        result = score_prediction_confidence(
            mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
            data_years=5.0,
        )
        assert result["components"]["data_sufficiency"] == 1.0

    def test_1yr_data_low_score(self):
        result = score_prediction_confidence(
            mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
            data_years=1.0,
        )
        assert result["components"]["data_sufficiency"] == 0.2

    def test_more_data_higher_score(self):
        short = score_prediction_confidence(
            mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
            data_years=2.0,
        )
        long = score_prediction_confidence(
            mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
            data_years=5.0,
        )
        assert long["components"]["data_sufficiency"] > short["components"]["data_sufficiency"]


class TestBetaStability:
    """Beta stability component tests."""

    def test_normal_beta_high_score(self):
        result = score_prediction_confidence(
            mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
            beta=1.0,
        )
        assert result["components"]["beta_stability"] == 0.9

    def test_extreme_beta_low_score(self):
        result = score_prediction_confidence(
            mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
            beta=3.0,
        )
        assert result["components"]["beta_stability"] == 0.5


class TestMCSpread:
    """MC spread quality tests."""

    def test_narrow_spread_higher_confidence(self):
        narrow = score_prediction_confidence(
            mc_p10_return=30.0, mc_p90_return=70.0, mc_median_return=50.0,
        )
        wide = score_prediction_confidence(
            mc_p10_return=-50.0, mc_p90_return=300.0, mc_median_return=50.0,
        )
        assert narrow["components"]["mc_spread"] > wide["components"]["mc_spread"]

    def test_zero_median_handled(self):
        """Doesn't crash when median return is 0."""
        result = score_prediction_confidence(
            mc_p10_return=-20.0, mc_p90_return=20.0, mc_median_return=0.0,
        )
        assert 0.0 <= result["components"]["mc_spread"] <= 1.0


class TestEdgeCases:
    """Edge cases and robustness."""

    def test_none_drift_severity(self):
        """None drift_severity treated as 'none'."""
        result = score_prediction_confidence(
            mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
            drift_severity=None,
        )
        assert result["drift_severity"] == "none"
        assert result["interval_widening"] == 1.0

    def test_unknown_drift_severity(self):
        """Unknown severity falls back to moderate penalty."""
        result = score_prediction_confidence(
            mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
            drift_severity="unknown_value",
        )
        assert result["grade"] in ("A", "B", "C", "D", "F")  # doesn't crash

    def test_negative_median(self):
        """Works with negative median return (bearish stock)."""
        result = score_prediction_confidence(
            mc_p10_return=-50.0, mc_p90_return=10.0, mc_median_return=-20.0,
        )
        assert result["adjusted_p10"] <= result["mc_median"]
        assert result["adjusted_p90"] >= result["mc_median"]

    def test_extreme_garch_nu(self):
        """Very low nu (fat tails) doesn't crash."""
        result = score_prediction_confidence(
            mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
            garch_nu=2.5,
        )
        assert 0.0 <= result["components"]["tail_quality"] <= 1.0

    def test_interpretation_includes_drift_warning(self):
        """High/critical drift adds warning to interpretation."""
        result = score_prediction_confidence(
            mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
            drift_severity="critical",
        )
        assert "critical" in result["interpretation"]


class TestIntegrationWithStockAnalyzer:
    """Verify the scorer integrates correctly with stock_analyzer types."""

    def test_typical_stock_parameters(self):
        """Simulate a typical NVDA-like stock with critical drift."""
        result = score_prediction_confidence(
            mc_p10_return=-56.1,
            mc_p90_return=300.0,
            mc_median_return=76.3,
            garch_nu=8.0,
            garch_persistence=0.95,
            data_years=4.5,
            drift_severity="critical",
            beta=2.335,
        )
        # Should be low confidence due to critical drift + extreme beta
        assert result["grade"] in ("C", "D", "F")
        assert result["interval_widening"] == 1.60
        # Adjusted intervals wider than raw
        assert result["adjusted_p10"] < result["mc_p10"]
        assert result["adjusted_p90"] > result["mc_p90"]

    def test_stable_stock_no_drift(self):
        """Simulate a stable BRK-B-like stock with no drift."""
        result = score_prediction_confidence(
            mc_p10_return=-4.5,
            mc_p90_return=136.2,
            mc_median_return=49.7,
            garch_nu=8.0,
            garch_persistence=0.92,
            data_years=5.0,
            drift_severity="none",
            beta=0.7,
        )
        # Should be high confidence
        assert result["grade"] in ("A", "B")
        assert result["interval_widening"] == 1.0
