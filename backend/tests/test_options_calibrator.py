"""
Tests for options-implied Monte Carlo calibrator.

Validates:
  1. Null/missing data → neutral calibration (no effect on MC)
  2. IV blending (GARCH + ATM IV weighted average)
  3. Jump frequency from P/C ratio and IV rank
  4. Jump magnitude from IV skew
  5. Vol mean-reversion from term structure
  6. Confidence scoring
  7. apply_calibration_to_mc_params() scaling by confidence
  8. Edge cases (extreme values, partial data)
"""

import pytest
import numpy as np

from backend.services.options_calibrator import (
    calibrate_mc_from_options,
    apply_calibration_to_mc_params,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

_FULL_OPTIONS_DATA = {
    "ticker": "SPY",
    "current_price": 500.0,
    "atm_iv_call": 0.22,
    "atm_iv_put": 0.24,
    "iv_skew": 1.3,
    "put_call_volume_ratio": 1.2,
    "put_call_oi_ratio": 1.1,
    "iv_rank": 60.0,
    "total_call_volume": 50000,
    "total_put_volume": 60000,
    "iv_term_structure": {
        "near_iv": 0.22,
        "mid_iv": 0.24,
        "slope": 0.02,
        "contango": True,
    },
}

_BEARISH_OPTIONS_DATA = {
    "ticker": "SPY",
    "current_price": 450.0,
    "atm_iv_call": 0.35,
    "atm_iv_put": 0.40,
    "iv_skew": 1.8,
    "put_call_volume_ratio": 2.5,
    "iv_rank": 90.0,
    "total_call_volume": 20000,
    "total_put_volume": 50000,
    "iv_term_structure": {
        "near_iv": 0.35,
        "mid_iv": 0.28,
        "slope": -0.07,
        "contango": False,
    },
}

_BULLISH_OPTIONS_DATA = {
    "ticker": "AAPL",
    "current_price": 200.0,
    "atm_iv_call": 0.18,
    "atm_iv_put": 0.19,
    "iv_skew": 0.95,
    "put_call_volume_ratio": 0.6,
    "iv_rank": 15.0,
    "total_call_volume": 80000,
    "total_put_volume": 48000,
    "iv_term_structure": {
        "near_iv": 0.18,
        "mid_iv": 0.22,
        "slope": 0.04,
        "contango": True,
    },
}


# ── Test: Null/missing data ──────────────────────────────────────────────────

class TestNullCalibration:
    def test_none_data(self):
        result = calibrate_mc_from_options(None, garch_vol=0.20)
        assert result["confidence"] == 0.0
        assert result["jump_freq_mult"] == 1.0
        assert result["jump_mag_adj"] == 0.0
        assert result["vol_kappa_mult"] == 1.0

    def test_empty_dict(self):
        result = calibrate_mc_from_options({}, garch_vol=0.20)
        assert result["confidence"] == 0.0

    def test_error_in_data(self):
        result = calibrate_mc_from_options({"error": "No options"}, garch_vol=0.20)
        assert result["confidence"] == 0.0
        assert result["implied_vol"] is None


# ── Test: IV Blending ────────────────────────────────────────────────────────

class TestIVBlending:
    def test_blends_garch_and_iv(self):
        result = calibrate_mc_from_options(_FULL_OPTIONS_DATA, garch_vol=0.20)
        # ATM IV is 0.22, GARCH is 0.20, blend weight 0.35
        # expected: 0.65 * 0.20 + 0.35 * 0.22 = 0.207
        assert result["implied_vol"] is not None
        assert abs(result["implied_vol"] - 0.207) < 0.01

    def test_iv_only_when_no_garch(self):
        result = calibrate_mc_from_options(_FULL_OPTIONS_DATA, garch_vol=None)
        assert result["implied_vol"] == 0.22

    def test_garch_only_when_no_iv(self):
        data = {"ticker": "XYZ", "current_price": 100}
        result = calibrate_mc_from_options(data, garch_vol=0.25)
        assert result["implied_vol"] == 0.25

    def test_bearish_higher_vol(self):
        result = calibrate_mc_from_options(_BEARISH_OPTIONS_DATA, garch_vol=0.25)
        # Bearish IV (0.35) should pull the blend up
        assert result["implied_vol"] > 0.25


# ── Test: Jump Frequency ─────────────────────────────────────────────────────

class TestJumpFrequency:
    def test_neutral_pc_ratio(self):
        """P/C ratio near neutral → multiplier close to 1.0."""
        data = {**_FULL_OPTIONS_DATA, "put_call_volume_ratio": 0.95}
        result = calibrate_mc_from_options(data, garch_vol=0.20)
        assert 0.9 <= result["jump_freq_mult"] <= 1.2

    def test_high_pc_increases_freq(self):
        """High P/C ratio → more put buying → higher jump frequency."""
        result = calibrate_mc_from_options(_BEARISH_OPTIONS_DATA, garch_vol=0.25)
        assert result["jump_freq_mult"] > 1.2

    def test_low_pc_decreases_freq(self):
        """Low P/C ratio → bullish → lower jump frequency."""
        result = calibrate_mc_from_options(_BULLISH_OPTIONS_DATA, garch_vol=0.18)
        assert result["jump_freq_mult"] < 1.0

    def test_high_iv_rank_increases_freq(self):
        """High IV rank → elevated fear → higher jump frequency."""
        data = {**_FULL_OPTIONS_DATA, "iv_rank": 95.0, "put_call_volume_ratio": 1.0}
        result = calibrate_mc_from_options(data, garch_vol=0.20)
        assert result["jump_freq_mult"] > 1.0

    def test_freq_bounded(self):
        """Jump frequency multiplier stays in [0.5, 2.5]."""
        extreme = {**_BEARISH_OPTIONS_DATA, "put_call_volume_ratio": 5.0, "iv_rank": 100.0}
        result = calibrate_mc_from_options(extreme, garch_vol=0.30)
        assert 0.5 <= result["jump_freq_mult"] <= 2.5


# ── Test: Jump Magnitude ─────────────────────────────────────────────────────

class TestJumpMagnitude:
    def test_steep_skew_increases_magnitude(self):
        """Steep IV skew → market pricing larger crashes → more negative jump adj."""
        result = calibrate_mc_from_options(_BEARISH_OPTIONS_DATA, garch_vol=0.25)
        assert result["jump_mag_adj"] < 0

    def test_flat_skew_no_adjustment(self):
        """Normal skew → no meaningful adjustment."""
        data = {**_FULL_OPTIONS_DATA, "iv_skew": 1.1}
        result = calibrate_mc_from_options(data, garch_vol=0.20)
        assert abs(result["jump_mag_adj"]) < 0.005

    def test_inverted_skew_positive_adj(self):
        """Very flat/inverted skew → slight positive adjustment."""
        data = {**_FULL_OPTIONS_DATA, "iv_skew": 0.85}
        result = calibrate_mc_from_options(data, garch_vol=0.20)
        assert result["jump_mag_adj"] >= 0

    def test_magnitude_bounded(self):
        """Jump magnitude adjustment stays in [-0.06, 0.02]."""
        extreme = {**_BEARISH_OPTIONS_DATA, "iv_skew": 3.0}
        result = calibrate_mc_from_options(extreme, garch_vol=0.30)
        assert -0.06 <= result["jump_mag_adj"] <= 0.02


# ── Test: Vol Mean-Reversion ─────────────────────────────────────────────────

class TestVolKappa:
    def test_backwardation_faster_reversion(self):
        """Backwardation (near IV > far IV) → faster vol mean-reversion."""
        result = calibrate_mc_from_options(_BEARISH_OPTIONS_DATA, garch_vol=0.25)
        assert result["vol_kappa_mult"] > 1.0

    def test_contango_normal_reversion(self):
        """Normal contango → kappa multiplier near 1.0."""
        result = calibrate_mc_from_options(_FULL_OPTIONS_DATA, garch_vol=0.20)
        assert 0.7 <= result["vol_kappa_mult"] <= 1.1

    def test_kappa_bounded(self):
        """Vol kappa multiplier stays in [0.5, 2.0]."""
        extreme = {**_BEARISH_OPTIONS_DATA}
        extreme["iv_term_structure"]["slope"] = -0.20
        result = calibrate_mc_from_options(extreme, garch_vol=0.30)
        assert 0.5 <= result["vol_kappa_mult"] <= 2.0

    def test_vix_backwardation(self):
        """VIX > VIX3M (backwardation) → faster reversion."""
        data = {**_FULL_OPTIONS_DATA, "vix_term_structure": {
            "vix_vix3m_ratio": 1.2, "contango": False,
        }}
        result = calibrate_mc_from_options(data, garch_vol=0.20)
        assert result["vol_kappa_mult"] > 1.0


# ── Test: Confidence Scoring ─────────────────────────────────────────────────

class TestConfidence:
    def test_full_data_high_confidence(self):
        """Full options data → high confidence."""
        result = calibrate_mc_from_options(_FULL_OPTIONS_DATA, garch_vol=0.20)
        assert result["confidence"] > 0.7

    def test_partial_data_lower_confidence(self):
        """Partial data → lower confidence."""
        data = {"ticker": "XYZ", "current_price": 100, "atm_iv_call": 0.25}
        result = calibrate_mc_from_options(data, garch_vol=0.20)
        assert 0 < result["confidence"] < 0.5

    def test_no_volume_reduces_confidence(self):
        """No volume data → reduced confidence."""
        data = {**_FULL_OPTIONS_DATA}
        del data["total_call_volume"]
        del data["total_put_volume"]
        result = calibrate_mc_from_options(data, garch_vol=0.20)
        assert result["confidence"] < calibrate_mc_from_options(
            _FULL_OPTIONS_DATA, garch_vol=0.20
        )["confidence"]


# ── Test: apply_calibration_to_mc_params ─────────────────────────────────────

class TestApplyCalibration:
    def test_scales_by_confidence(self):
        """Adjustments are scaled by confidence level."""
        cal_high = {
            "implied_vol": 0.30,
            "jump_freq_mult": 2.0,
            "jump_mag_adj": -0.03,
            "vol_kappa_mult": 1.5,
            "confidence": 1.0,
        }
        cal_low = {**cal_high, "confidence": 0.5}

        applied_high = apply_calibration_to_mc_params(cal_high, garch_vol=0.20, base_crash_freq=0.07)
        applied_low = apply_calibration_to_mc_params(cal_low, garch_vol=0.20, base_crash_freq=0.07)

        # Higher confidence → larger crash freq adjustment
        assert applied_high["crash_freq"] > applied_low["crash_freq"]

    def test_zero_confidence_no_change(self):
        """Zero confidence → parameters unchanged."""
        cal = {
            "implied_vol": 0.40,
            "jump_freq_mult": 3.0,
            "jump_mag_adj": -0.05,
            "vol_kappa_mult": 2.0,
            "confidence": 0.0,
        }
        applied = apply_calibration_to_mc_params(cal, garch_vol=0.20, base_crash_freq=0.07)
        assert applied["crash_freq"] == 0.07
        assert applied["jump_mean"] == -0.10

    def test_crash_freq_bounded(self):
        """Applied crash frequency stays in [0.02, 0.25]."""
        cal = {
            "implied_vol": 0.30,
            "jump_freq_mult": 2.5,
            "jump_mag_adj": 0.0,
            "vol_kappa_mult": 1.0,
            "confidence": 1.0,
        }
        applied = apply_calibration_to_mc_params(cal, garch_vol=0.20, base_crash_freq=0.20)
        assert 0.02 <= applied["crash_freq"] <= 0.25

    def test_vol_override(self):
        """Implied vol is passed through directly."""
        cal = {
            "implied_vol": 0.28,
            "jump_freq_mult": 1.0,
            "jump_mag_adj": 0.0,
            "vol_kappa_mult": 1.0,
            "confidence": 0.8,
        }
        applied = apply_calibration_to_mc_params(cal, garch_vol=0.20, base_crash_freq=0.07)
        assert applied["garch_vol"] == 0.28


# ── Test: Integration scenarios ──────────────────────────────────────────────

class TestIntegrationScenarios:
    def test_bearish_market_conditions(self):
        """Bearish options data should increase risk parameters."""
        cal = calibrate_mc_from_options(_BEARISH_OPTIONS_DATA, garch_vol=0.25)
        applied = apply_calibration_to_mc_params(cal, garch_vol=0.25, base_crash_freq=0.07)

        # Should increase crash frequency and vol
        assert applied["crash_freq"] > 0.07
        assert applied["garch_vol"] > 0.25
        # Jump mean should be more negative
        assert applied["jump_mean"] < -0.10

    def test_bullish_market_conditions(self):
        """Bullish options data should decrease risk parameters."""
        cal = calibrate_mc_from_options(_BULLISH_OPTIONS_DATA, garch_vol=0.18)
        applied = apply_calibration_to_mc_params(cal, garch_vol=0.18, base_crash_freq=0.07)

        # Should decrease crash frequency
        assert applied["crash_freq"] < 0.07

    def test_neutral_market_minimal_effect(self):
        """Neutral options → parameters stay close to defaults."""
        neutral = {
            "ticker": "SPY",
            "current_price": 500,
            "atm_iv_call": 0.20,
            "iv_skew": 1.1,
            "put_call_volume_ratio": 0.95,
            "iv_rank": 50.0,
            "total_call_volume": 40000,
            "total_put_volume": 38000,
            "iv_term_structure": {"near_iv": 0.20, "mid_iv": 0.21, "slope": 0.01, "contango": True},
        }
        cal = calibrate_mc_from_options(neutral, garch_vol=0.20)
        applied = apply_calibration_to_mc_params(cal, garch_vol=0.20, base_crash_freq=0.07)

        assert abs(applied["crash_freq"] - 0.07) < 0.02
        assert abs(applied["jump_mean"] + 0.10) < 0.005
