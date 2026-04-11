"""
Tests for external_validator service — contract, signals, edge cases.

Covers:
1. validate_external() contract: return type, attribute access, argument combos
2. _assess_lei(): monthly decline counting, RECESSION/WARNING/EXPANSION thresholds
3. _assess_sloos(): tightening/easing/neutral boundaries
4. _assess_fed(): hawkish/dovish/neutral from YoY rate change
5. _assess_sentiment(): extreme_fear/fear/neutral/greed boundaries
6. Consensus logic: bearish_count thresholds from config
7. Edge cases: NaN-heavy data, empty series, None inputs, extreme values
"""

import pytest
import pandas as pd
import numpy as np


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_fred_data():
    """Minimal FRED data dict with all 4 indicator series (300 business days)."""
    idx = pd.date_range("2023-01-01", periods=300, freq="B")
    return {
        "lei": pd.Series(np.linspace(100, 98, len(idx)), index=idx),
        "sloos_ci": pd.Series(np.full(len(idx), 10.0), index=idx),
        "fed_funds": pd.Series(np.full(len(idx), 5.0), index=idx),
        "consumer_sentiment": pd.Series(np.full(len(idx), 85.0), index=idx),
    }


@pytest.fixture
def monthly_idx():
    """12-month index for LEI tests."""
    return pd.date_range("2022-01-01", periods=12, freq="MS")


# ── 1. Contract Tests ────────────────────────────────────────────────────────

class TestExternalValidatorContract:
    """Verify function signature and return type match router usage."""

    def test_returns_dataclass_not_dict(self, mock_fred_data):
        from backend.services.external_validator import validate_external, ExternalValidation
        result = validate_external(mock_fred_data, 0.3, "Bull")
        assert isinstance(result, ExternalValidation)

    def test_consensus_direction_is_attribute(self, mock_fred_data):
        from backend.services.external_validator import validate_external
        result = validate_external(mock_fred_data, 0.3, "Bull")
        assert hasattr(result, "consensus_direction")
        assert result.consensus_direction in ("BULLISH", "BEARISH", "NEUTRAL", "UNKNOWN")

    def test_all_fields_present(self, mock_fred_data):
        from backend.services.external_validator import validate_external
        result = validate_external(mock_fred_data, 0.3, "Bull")
        assert hasattr(result, "lei_signal")
        assert hasattr(result, "sloos_signal")
        assert hasattr(result, "fed_signal")
        assert hasattr(result, "sentiment_signal")
        assert hasattr(result, "engine_agreement")
        assert hasattr(result, "divergence_alerts")

    def test_accepts_none_crash_prob(self, mock_fred_data):
        from backend.services.external_validator import validate_external
        result = validate_external(mock_fred_data, None, "Bull")
        assert result.consensus_direction in ("BULLISH", "BEARISH", "NEUTRAL", "UNKNOWN")

    def test_accepts_empty_fred_data(self):
        from backend.services.external_validator import validate_external
        result = validate_external({}, 0.5, "Bear")
        assert result.consensus_direction in ("BULLISH", "NEUTRAL", "BEARISH")
        assert result.engine_agreement == 0.0

    def test_accepts_none_fred_data(self):
        from backend.services.external_validator import validate_external
        result = validate_external(None, 0.5, "Bear")
        assert result.engine_agreement == 0.0

    def test_engine_agreement_range(self, mock_fred_data):
        from backend.services.external_validator import validate_external
        result = validate_external(mock_fred_data, 0.3, "Bull")
        assert 0.0 <= result.engine_agreement <= 1.0

    def test_divergence_alerts_is_list(self, mock_fred_data):
        from backend.services.external_validator import validate_external
        result = validate_external(mock_fred_data, 0.3, "Bull")
        assert isinstance(result.divergence_alerts, list)


# ── 2. LEI Signal Tests ─────────────────────────────────────────────────────

class TestAssessLEI:
    """Test _assess_lei with various decline patterns."""

    def test_expansion_rising_lei(self, monthly_idx):
        from backend.services.external_validator import _assess_lei
        lei = pd.Series(np.linspace(95, 105, len(monthly_idx)), index=monthly_idx)
        assert _assess_lei(lei) == "EXPANSION"

    def test_warning_3_month_decline(self, monthly_idx):
        from backend.services.external_validator import _assess_lei
        # Flat then 4 consecutive declines → WARNING (>= 3)
        vals = [100] * 8 + [99, 98, 97, 96]
        lei = pd.Series(vals, index=monthly_idx)
        assert _assess_lei(lei) == "WARNING"

    def test_recession_6_month_decline(self, monthly_idx):
        from backend.services.external_validator import _assess_lei
        vals = [100] * 5 + [99, 98, 97, 96, 95, 94, 93]
        lei = pd.Series(vals, index=pd.date_range("2022-01-01", periods=12, freq="MS"))
        assert _assess_lei(lei) == "RECESSION"

    def test_unknown_too_few_points(self):
        from backend.services.external_validator import _assess_lei
        idx = pd.date_range("2023-01-01", periods=3, freq="B")
        lei = pd.Series([100, 99, 98], index=idx)
        assert _assess_lei(lei) == "UNKNOWN"

    def test_unknown_empty_series(self):
        from backend.services.external_validator import _assess_lei
        assert _assess_lei(pd.Series(dtype=float)) == "UNKNOWN"

    def test_nan_heavy_lei(self, monthly_idx):
        from backend.services.external_validator import _assess_lei
        vals = [np.nan] * 6 + [100, 99, 98, 97, 96, 95]
        lei = pd.Series(vals, index=monthly_idx)
        result = _assess_lei(lei)
        assert result in ("EXPANSION", "WARNING", "RECESSION", "UNKNOWN")


# ── 3. SLOOS Signal Tests ───────────────────────────────────────────────────

class TestAssessSLOOS:
    """Test _assess_sloos threshold boundaries."""

    def test_tightening_above_threshold(self):
        from backend.services.external_validator import _assess_sloos
        idx = pd.date_range("2023-01-01", periods=10, freq="B")
        s = pd.Series(np.full(10, 30.0), index=idx)
        assert _assess_sloos(s) == "TIGHTENING"

    def test_easing_below_threshold(self):
        from backend.services.external_validator import _assess_sloos
        idx = pd.date_range("2023-01-01", periods=10, freq="B")
        s = pd.Series(np.full(10, -30.0), index=idx)
        assert _assess_sloos(s) == "EASING"

    def test_neutral_in_band(self):
        from backend.services.external_validator import _assess_sloos
        idx = pd.date_range("2023-01-01", periods=10, freq="B")
        s = pd.Series(np.full(10, 0.0), index=idx)
        assert _assess_sloos(s) == "NEUTRAL"

    def test_boundary_at_exactly_20(self):
        from backend.services.external_validator import _assess_sloos
        idx = pd.date_range("2023-01-01", periods=10, freq="B")
        # Exactly 20 → NOT > 20, so NEUTRAL
        s = pd.Series(np.full(10, 20.0), index=idx)
        assert _assess_sloos(s) == "NEUTRAL"

    def test_boundary_at_exactly_minus_20(self):
        from backend.services.external_validator import _assess_sloos
        idx = pd.date_range("2023-01-01", periods=10, freq="B")
        # Exactly -20 → NOT < -20, so NEUTRAL
        s = pd.Series(np.full(10, -20.0), index=idx)
        assert _assess_sloos(s) == "NEUTRAL"

    def test_unknown_empty(self):
        from backend.services.external_validator import _assess_sloos
        assert _assess_sloos(pd.Series(dtype=float)) == "UNKNOWN"

    def test_extreme_tightening(self):
        from backend.services.external_validator import _assess_sloos
        idx = pd.date_range("2023-01-01", periods=5, freq="B")
        s = pd.Series(np.full(5, 80.0), index=idx)
        assert _assess_sloos(s) == "TIGHTENING"


# ── 4. Fed Funds Signal Tests ───────────────────────────────────────────────

class TestAssessFed:
    """Test _assess_fed YoY rate change classification."""

    def test_hawkish_rate_hike(self):
        from backend.services.external_validator import _assess_fed
        idx = pd.date_range("2022-01-01", periods=300, freq="B")
        # Start at 3.0, end at 5.5 → change = +2.5 > 0.25 → HAWKISH
        s = pd.Series(np.linspace(3.0, 5.5, 300), index=idx)
        assert _assess_fed(s) == "HAWKISH"

    def test_dovish_rate_cut(self):
        from backend.services.external_validator import _assess_fed
        idx = pd.date_range("2022-01-01", periods=300, freq="B")
        s = pd.Series(np.linspace(5.0, 3.5, 300), index=idx)
        assert _assess_fed(s) == "DOVISH"

    def test_neutral_flat_rate(self):
        from backend.services.external_validator import _assess_fed
        idx = pd.date_range("2022-01-01", periods=300, freq="B")
        s = pd.Series(np.full(300, 5.0), index=idx)
        assert _assess_fed(s) == "NEUTRAL"

    def test_unknown_too_short(self):
        from backend.services.external_validator import _assess_fed
        idx = pd.date_range("2023-01-01", periods=100, freq="B")
        s = pd.Series(np.full(100, 5.0), index=idx)
        assert _assess_fed(s) == "UNKNOWN"

    def test_unknown_empty(self):
        from backend.services.external_validator import _assess_fed
        assert _assess_fed(pd.Series(dtype=float)) == "UNKNOWN"

    def test_boundary_exactly_025(self):
        """Change of exactly 0.25 → NOT > 0.25, should be NEUTRAL."""
        from backend.services.external_validator import _assess_fed
        idx = pd.date_range("2022-01-01", periods=252, freq="B")
        vals = np.full(252, 5.0)
        vals[-1] = 5.25  # exactly +0.25 from 5.0
        s = pd.Series(vals, index=idx)
        assert _assess_fed(s) == "NEUTRAL"


# ── 5. Sentiment Signal Tests ───────────────────────────────────────────────

class TestAssessSentiment:
    """Test _assess_sentiment threshold boundaries from config."""

    def test_extreme_fear(self):
        from backend.services.external_validator import _assess_sentiment
        idx = pd.date_range("2023-01-01", periods=5, freq="B")
        s = pd.Series(np.full(5, 50.0), index=idx)
        assert _assess_sentiment(s) == "EXTREME_FEAR"

    def test_fear(self):
        from backend.services.external_validator import _assess_sentiment
        idx = pd.date_range("2023-01-01", periods=5, freq="B")
        s = pd.Series(np.full(5, 70.0), index=idx)
        assert _assess_sentiment(s) == "FEAR"

    def test_neutral(self):
        from backend.services.external_validator import _assess_sentiment
        idx = pd.date_range("2023-01-01", periods=5, freq="B")
        s = pd.Series(np.full(5, 90.0), index=idx)
        assert _assess_sentiment(s) == "NEUTRAL"

    def test_greed(self):
        from backend.services.external_validator import _assess_sentiment
        idx = pd.date_range("2023-01-01", periods=5, freq="B")
        s = pd.Series(np.full(5, 110.0), index=idx)
        assert _assess_sentiment(s) == "GREED"

    def test_boundary_exactly_60(self):
        """60 → NOT < 60, should be FEAR (not EXTREME_FEAR)."""
        from backend.services.external_validator import _assess_sentiment
        idx = pd.date_range("2023-01-01", periods=5, freq="B")
        s = pd.Series(np.full(5, 60.0), index=idx)
        assert _assess_sentiment(s) == "FEAR"

    def test_boundary_exactly_80(self):
        """80 → NOT < 80, should be NEUTRAL (not FEAR)."""
        from backend.services.external_validator import _assess_sentiment
        idx = pd.date_range("2023-01-01", periods=5, freq="B")
        s = pd.Series(np.full(5, 80.0), index=idx)
        assert _assess_sentiment(s) == "NEUTRAL"

    def test_boundary_exactly_100(self):
        """100 → NOT < 100, should be GREED."""
        from backend.services.external_validator import _assess_sentiment
        idx = pd.date_range("2023-01-01", periods=5, freq="B")
        s = pd.Series(np.full(5, 100.0), index=idx)
        assert _assess_sentiment(s) == "GREED"

    def test_unknown_empty(self):
        from backend.services.external_validator import _assess_sentiment
        assert _assess_sentiment(pd.Series(dtype=float)) == "UNKNOWN"


# ── 6. Consensus / Integration Tests ────────────────────────────────────────

class TestConsensusLogic:
    """Test bearish_count → consensus mapping and divergence alerts."""

    def test_bearish_consensus_all_indicators_bearish(self, mock_fred_data):
        from backend.services.external_validator import validate_external
        idx = mock_fred_data["lei"].index
        # LEI declining → WARNING/RECESSION
        mock_fred_data["lei"] = pd.Series(np.linspace(100, 90, len(idx)), index=idx)
        # SLOOS tightening
        mock_fred_data["sloos_ci"] = pd.Series(np.full(len(idx), 30.0), index=idx)
        # Fed hawkish
        mock_fred_data["fed_funds"] = pd.Series(np.linspace(3.0, 5.5, len(idx)), index=idx)
        # Sentiment neutral (bearish in this model)
        mock_fred_data["consumer_sentiment"] = pd.Series(np.full(len(idx), 95.0), index=idx)

        result = validate_external(mock_fred_data, 0.7, "Bear")
        assert result.consensus_direction == "BEARISH"

    def test_bullish_consensus_all_indicators_bullish(self, mock_fred_data):
        from backend.services.external_validator import validate_external
        idx = mock_fred_data["lei"].index
        # LEI rising → EXPANSION
        mock_fred_data["lei"] = pd.Series(np.linspace(95, 105, len(idx)), index=idx)
        # SLOOS easing
        mock_fred_data["sloos_ci"] = pd.Series(np.full(len(idx), -30.0), index=idx)
        # Fed dovish
        mock_fred_data["fed_funds"] = pd.Series(np.linspace(5.0, 3.5, len(idx)), index=idx)
        # Extreme fear → contrarian bullish (not counted as bearish)
        mock_fred_data["consumer_sentiment"] = pd.Series(np.full(len(idx), 55.0), index=idx)

        result = validate_external(mock_fred_data, 0.1, "Bull")
        assert result.consensus_direction == "BULLISH"

    def test_neutral_consensus_mixed_signals(self, mock_fred_data):
        from backend.services.external_validator import validate_external
        idx = mock_fred_data["lei"].index
        # LEI declining → WARNING (bearish)
        mock_fred_data["lei"] = pd.Series(np.linspace(100, 90, len(idx)), index=idx)
        # SLOOS neutral (not bearish)
        mock_fred_data["sloos_ci"] = pd.Series(np.full(len(idx), 0.0), index=idx)
        # Fed hawkish (bearish) — need clear hike
        mock_fred_data["fed_funds"] = pd.Series(np.linspace(3.0, 5.5, len(idx)), index=idx)
        # Extreme fear (not bearish)
        mock_fred_data["consumer_sentiment"] = pd.Series(np.full(len(idx), 55.0), index=idx)

        result = validate_external(mock_fred_data, 0.3, "Bull")
        # 2 bearish signals (LEI + Fed) → NEUTRAL
        assert result.consensus_direction == "NEUTRAL"

    def test_divergence_lei_recession_vs_bull(self, mock_fred_data):
        """LEI signals RECESSION but engine says Bull → divergence alert."""
        from backend.services.external_validator import validate_external
        monthly_idx = pd.date_range("2022-01-01", periods=12, freq="MS")
        lei_vals = np.linspace(100, 88, 12)
        mock_fred_data["lei"] = pd.Series(lei_vals, index=monthly_idx)

        result = validate_external(mock_fred_data, 0.1, "Bull")
        assert any("RECESSION" in alert for alert in result.divergence_alerts)

    def test_divergence_extreme_fear_contrarian(self, mock_fred_data):
        """EXTREME_FEAR sentiment + engine bearish → contrarian alert."""
        from backend.services.external_validator import validate_external
        idx = mock_fred_data["lei"].index
        mock_fred_data["consumer_sentiment"] = pd.Series(np.full(len(idx), 50.0), index=idx)

        result = validate_external(mock_fred_data, 0.7, "Bear")
        assert any("EXTREME FEAR" in alert for alert in result.divergence_alerts)

    def test_engine_agreement_full_match(self, mock_fred_data):
        """All 4 signals agree with engine → agreement = 1.0."""
        from backend.services.external_validator import validate_external
        idx = mock_fred_data["lei"].index
        # All bullish signals + Bull engine
        mock_fred_data["lei"] = pd.Series(np.linspace(95, 105, len(idx)), index=idx)
        mock_fred_data["sloos_ci"] = pd.Series(np.full(len(idx), -30.0), index=idx)
        mock_fred_data["fed_funds"] = pd.Series(np.linspace(5.0, 3.5, len(idx)), index=idx)
        mock_fred_data["consumer_sentiment"] = pd.Series(np.full(len(idx), 55.0), index=idx)

        result = validate_external(mock_fred_data, 0.1, "Bull")
        assert result.engine_agreement == 1.0


# ── 7. Edge Cases ───────────────────────────────────────────────────────────

class TestEdgeCases:
    """Extreme / unusual inputs that shouldn't crash."""

    def test_nan_only_series(self):
        from backend.services.external_validator import validate_external
        idx = pd.date_range("2023-01-01", periods=100, freq="B")
        fred = {
            "lei": pd.Series(np.full(100, np.nan), index=idx),
            "sloos_ci": pd.Series(np.full(100, np.nan), index=idx),
            "fed_funds": pd.Series(np.full(100, np.nan), index=idx),
            "consumer_sentiment": pd.Series(np.full(100, np.nan), index=idx),
        }
        result = validate_external(fred, 0.3, "Bull")
        # All signals should be UNKNOWN (no valid data)
        assert result.lei_signal == "UNKNOWN"
        assert result.sloos_signal == "UNKNOWN"
        assert result.fed_signal == "UNKNOWN"
        assert result.sentiment_signal == "UNKNOWN"

    def test_crash_prob_zero(self, mock_fred_data):
        from backend.services.external_validator import validate_external
        result = validate_external(mock_fred_data, 0.0, "Bull")
        assert result.consensus_direction in ("BULLISH", "BEARISH", "NEUTRAL")

    def test_crash_prob_one(self, mock_fred_data):
        from backend.services.external_validator import validate_external
        result = validate_external(mock_fred_data, 1.0, "Crisis")
        assert result.consensus_direction in ("BULLISH", "BEARISH", "NEUTRAL")

    def test_unknown_regime_string(self, mock_fred_data):
        from backend.services.external_validator import validate_external
        result = validate_external(mock_fred_data, 0.3, "SomethingWeird")
        assert result.consensus_direction in ("BULLISH", "BEARISH", "NEUTRAL")

    def test_partial_fred_data_only_lei(self):
        from backend.services.external_validator import validate_external
        idx = pd.date_range("2023-01-01", periods=300, freq="B")
        fred = {"lei": pd.Series(np.linspace(100, 98, 300), index=idx)}
        result = validate_external(fred, 0.3, "Bull")
        assert result.lei_signal != "UNKNOWN"
        assert result.sloos_signal == "UNKNOWN"
        assert result.fed_signal == "UNKNOWN"
        assert result.sentiment_signal == "UNKNOWN"

    def test_extreme_sentiment_value(self):
        from backend.services.external_validator import _assess_sentiment
        idx = pd.date_range("2023-01-01", periods=5, freq="B")
        s = pd.Series(np.full(5, 200.0), index=idx)
        assert _assess_sentiment(s) == "GREED"

    def test_negative_sentiment_value(self):
        from backend.services.external_validator import _assess_sentiment
        idx = pd.date_range("2023-01-01", periods=5, freq="B")
        s = pd.Series(np.full(5, -10.0), index=idx)
        assert _assess_sentiment(s) == "EXTREME_FEAR"

    def test_extreme_sloos_value(self):
        from backend.services.external_validator import _assess_sloos
        idx = pd.date_range("2023-01-01", periods=5, freq="B")
        s = pd.Series(np.full(5, 100.0), index=idx)
        assert _assess_sloos(s) == "TIGHTENING"

    def test_negative_extreme_sloos_value(self):
        from backend.services.external_validator import _assess_sloos
        idx = pd.date_range("2023-01-01", periods=5, freq="B")
        s = pd.Series(np.full(5, -100.0), index=idx)
        assert _assess_sloos(s) == "EASING"


# ── 8. Config Integration Tests ─────────────────────────────────────────────

class TestConfigIntegration:
    """Verify thresholds are read from config, not hardcoded."""

    def test_config_has_external_validator_section(self):
        from backend.config import config
        assert "external_validator" in config

    def test_config_has_all_required_keys(self):
        from backend.config import config
        ev = config["external_validator"]
        required = [
            "lei_warning_months", "lei_recession_months",
            "sloos_tightening_threshold", "sloos_easing_threshold",
            "fed_hawkish_bps", "fed_dovish_bps", "fed_lookback_days",
            "sentiment_extreme_fear", "sentiment_fear", "sentiment_greed",
            "bearish_consensus_min", "bullish_consensus_max",
            "crash_prob_bearish",
        ]
        for key in required:
            assert key in ev, f"Missing config key: external_validator.{key}"

    def test_thresholds_are_sane(self):
        from backend.config import config
        ev = config["external_validator"]
        assert ev["lei_warning_months"] < ev["lei_recession_months"]
        assert ev["sloos_easing_threshold"] < 0 < ev["sloos_tightening_threshold"]
        assert ev["fed_dovish_bps"] < 0 < ev["fed_hawkish_bps"]
        assert ev["sentiment_extreme_fear"] < ev["sentiment_fear"] < ev["sentiment_greed"]
        assert ev["bullish_consensus_max"] < ev["bearish_consensus_min"]
        assert 0 < ev["crash_prob_bearish"] <= 1.0
