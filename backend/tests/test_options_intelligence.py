"""
Tests for Options Intelligence Service
==========================================

Tests the options-derived signal computation, IV skew analysis,
put/call ratio interpretation, and VIX term structure analysis.
"""

import pandas as pd


class TestOptionsSignalGeneration:
    """Test the signal generation logic from options data."""

    def test_bearish_signal_from_high_skew_and_pcr(self):
        """High IV skew + high put/call ratio → bearish."""
        from backend.services.options_intelligence import _generate_options_signal

        data = {
            "iv_skew": 1.5,
            "put_call_volume_ratio": 1.2,
            "iv_rank": 85,
            "iv_vs_rv": 35,
            "iv_term_structure": {"contango": False, "slope": -0.05},
        }
        signal = _generate_options_signal(data)
        assert signal["score"] < -0.2
        assert signal["sentiment"] in ("bearish", "slightly_bearish")
        assert signal["n_signals"] >= 4

    def test_bullish_signal_from_low_iv_and_call_skew(self):
        """Low IV rank + call-heavy skew → bullish."""
        from backend.services.options_intelligence import _generate_options_signal

        data = {
            "iv_skew": 0.75,
            "put_call_volume_ratio": 0.6,
            "iv_rank": 15,
            "iv_vs_rv": -20,
            "iv_term_structure": {"contango": True, "slope": 0.03},
        }
        signal = _generate_options_signal(data)
        assert signal["score"] > 0.1
        assert signal["sentiment"] in ("bullish", "slightly_bullish")

    def test_neutral_signal_from_balanced_data(self):
        """Balanced options data → neutral signal."""
        from backend.services.options_intelligence import _generate_options_signal

        data = {
            "iv_skew": 1.0,
            "put_call_volume_ratio": 0.8,
            "iv_rank": 50,
            "iv_vs_rv": 5,
            "iv_term_structure": {"contango": True, "slope": 0.01},
        }
        signal = _generate_options_signal(data)
        assert -0.3 < signal["score"] < 0.3
        assert signal["n_signals"] >= 4

    def test_extreme_pcr_is_contrarian_bullish(self):
        """Extreme put/call ratio (>1.5) triggers contrarian bullish signal."""
        from backend.services.options_intelligence import _generate_options_signal

        data = {"put_call_volume_ratio": 1.8}
        signal = _generate_options_signal(data)
        # The PCR component should be positive (contrarian)
        assert signal["score"] > 0

    def test_signal_score_bounds(self):
        """Signal score always in [-1, 1]."""
        from backend.services.options_intelligence import _generate_options_signal

        # Maximally bearish
        data = {
            "iv_skew": 2.0,
            "put_call_volume_ratio": 1.3,
            "iv_rank": 99,
            "iv_vs_rv": 100,
            "iv_term_structure": {"contango": False},
            "max_pain_distance_pct": -10,
        }
        signal = _generate_options_signal(data)
        assert -1.0 <= signal["score"] <= 1.0

        # Maximally bullish
        data2 = {
            "iv_skew": 0.5,
            "put_call_volume_ratio": 1.6,
            "iv_rank": 5,
            "iv_vs_rv": -30,
            "iv_term_structure": {"contango": True},
            "max_pain_distance_pct": 10,
        }
        signal2 = _generate_options_signal(data2)
        assert -1.0 <= signal2["score"] <= 1.0

    def test_empty_data_returns_zero_signal(self):
        """No options data → zero score."""
        from backend.services.options_intelligence import _generate_options_signal

        signal = _generate_options_signal({})
        assert signal["score"] == 0.0
        assert signal["n_signals"] == 0
        assert signal["sentiment"] == "neutral"

    def test_confidence_scales_with_signal_count(self):
        """Confidence increases with more available signals."""
        from backend.services.options_intelligence import _generate_options_signal

        one_signal = _generate_options_signal({"iv_skew": 1.3})
        many_signals = _generate_options_signal({
            "iv_skew": 1.3,
            "put_call_volume_ratio": 1.1,
            "iv_rank": 70,
            "iv_vs_rv": 20,
            "iv_term_structure": {"contango": True},
            "max_pain_distance_pct": -3,
        })
        assert many_signals["confidence"] > one_signal["confidence"]


class TestChainAnalysis:
    """Test chain analysis helper."""

    def test_analyze_chain_handles_empty_data(self):
        """Empty options chain returns error."""
        from backend.services.options_intelligence import _analyze_chain

        empty_calls = pd.DataFrame(columns=["strike", "impliedVolatility", "volume", "openInterest"])
        empty_puts = pd.DataFrame(columns=["strike", "impliedVolatility", "volume", "openInterest"])
        result = _analyze_chain(empty_calls, empty_puts, 100.0, "2026-05-01", "TEST")
        assert "error" in result

    def test_analyze_chain_computes_atm_iv(self):
        """Chain analysis extracts ATM implied vol."""
        from backend.services.options_intelligence import _analyze_chain

        calls = pd.DataFrame({
            "strike": [95, 100, 105, 110],
            "impliedVolatility": [0.35, 0.30, 0.28, 0.25],
            "volume": [100, 500, 300, 50],
            "openInterest": [1000, 5000, 3000, 500],
        })
        puts = pd.DataFrame({
            "strike": [90, 95, 100, 105],
            "impliedVolatility": [0.40, 0.35, 0.32, 0.29],
            "volume": [50, 200, 400, 100],
            "openInterest": [500, 2000, 4000, 1000],
        })
        result = _analyze_chain(calls, puts, 100.0, "2026-05-01", "TEST")
        assert "atm_iv_call" in result
        assert "atm_iv_put" in result
        assert result["atm_iv_call"] > 0
        assert result["atm_iv_put"] > 0

    def test_analyze_chain_computes_pcr(self):
        """Chain analysis computes put/call volume ratio."""
        from backend.services.options_intelligence import _analyze_chain

        calls = pd.DataFrame({
            "strike": [100], "impliedVolatility": [0.3],
            "volume": [1000], "openInterest": [5000],
        })
        puts = pd.DataFrame({
            "strike": [100], "impliedVolatility": [0.35],
            "volume": [500], "openInterest": [3000],
        })
        result = _analyze_chain(calls, puts, 100.0, "2026-05-01", "TEST")
        assert result["put_call_volume_ratio"] == 0.5
        assert result["put_call_oi_ratio"] == 0.6
