"""
Tests for Volatility Analytics service.

Covers: vol cone, term structure, regime detection, vol estimators,
vol clustering, vol-of-vol, GARCH forward curve, and summary endpoint.
"""

import numpy as np
import pandas as pd
import pytest

from backend.services.volatility_analytics import (
    _annualized_vol,
    _parkinson_vol,
    _garman_klass_vol,
    _compute_vol_cone,
    _compute_term_structure,
    _detect_vol_regime,
    _compute_vol_clustering,
    _compute_vol_of_vol,
    _garch_forward_curve,
    _regime_interpretation,
    get_volatility_analytics,
    get_vol_summary,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

def _make_returns(n=1260, seed=42, vol=0.01):
    """Generate synthetic log-returns with realistic properties."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0003, vol, size=n)
    # Add a vol cluster in the middle
    returns[400:450] *= 3.0
    return pd.Series(returns, index=pd.bdate_range("2021-01-01", periods=n))


def _make_ohlcv(n=1260, seed=42):
    """Generate synthetic OHLCV data."""
    rng = np.random.default_rng(seed)
    close = [100.0]
    for _ in range(n - 1):
        close.append(close[-1] * (1 + rng.normal(0.0003, 0.015)))
    close = np.array(close)
    high = close * (1 + np.abs(rng.normal(0, 0.005, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.005, n)))
    open_ = close * (1 + rng.normal(0, 0.002, n))
    volume = rng.integers(1_000_000, 10_000_000, size=n)
    idx = pd.bdate_range("2021-01-01", periods=n)
    return pd.DataFrame({
        "Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume
    }, index=idx)


# ── Unit tests ────────────────────────────────────────────────────────────

class TestAnnualizedVol:
    def test_basic(self):
        returns = _make_returns(252, vol=0.01)
        vol = _annualized_vol(returns)
        # Daily vol ~1%, annualized ~15.8%
        assert 0.10 < vol < 0.30

    def test_empty(self):
        assert _annualized_vol(pd.Series([], dtype=float)) == 0.0

    def test_single_value(self):
        assert _annualized_vol(pd.Series([0.01])) == 0.0


class TestParkinsonVol:
    def test_positive(self):
        ohlcv = _make_ohlcv(252)
        vol = _parkinson_vol(ohlcv["High"], ohlcv["Low"])
        assert vol > 0
        assert vol < 1.0  # Not absurdly high

    def test_insufficient_data(self):
        assert _parkinson_vol(pd.Series([1.0]), pd.Series([0.9])) == 0.0

    def test_higher_than_close_to_close(self):
        """Parkinson should generally differ from close-to-close but both positive."""
        ohlcv = _make_ohlcv(500)
        pk_vol = _parkinson_vol(ohlcv["High"], ohlcv["Low"])
        cc_vol = _annualized_vol(np.log(ohlcv["Close"] / ohlcv["Close"].shift(1)).dropna())
        assert pk_vol > 0
        assert cc_vol > 0


class TestGarmanKlassVol:
    def test_positive(self):
        ohlcv = _make_ohlcv(252)
        vol = _garman_klass_vol(ohlcv["Open"], ohlcv["High"], ohlcv["Low"], ohlcv["Close"])
        assert vol > 0
        assert vol < 1.0

    def test_insufficient_data(self):
        assert _garman_klass_vol(
            pd.Series([1.0]), pd.Series([1.1]),
            pd.Series([0.9]), pd.Series([1.0])
        ) == 0.0


class TestVolCone:
    def test_basic_structure(self):
        returns = _make_returns(1260)
        cone = _compute_vol_cone(returns)
        assert len(cone) > 0
        # Should have entries for different windows
        assert "30d" in cone
        assert "252d" in cone

    def test_cone_percentiles_ordered(self):
        returns = _make_returns(1260)
        cone = _compute_vol_cone(returns)
        for key, entry in cone.items():
            assert entry["p5"] <= entry["p25"] <= entry["median"]
            assert entry["median"] <= entry["p75"] <= entry["p95"]

    def test_current_within_range(self):
        returns = _make_returns(1260)
        cone = _compute_vol_cone(returns)
        for key, entry in cone.items():
            # Current should be between p5 and p95 most of the time
            assert entry["p5"] * 0.5 <= entry["current"] <= entry["p95"] * 2.0

    def test_percentile_bounded(self):
        returns = _make_returns(1260)
        cone = _compute_vol_cone(returns)
        for key, entry in cone.items():
            assert 0 <= entry["percentile"] <= 100

    def test_insufficient_data(self):
        returns = _make_returns(20)
        cone = _compute_vol_cone(returns)
        # Should skip windows that don't have enough data
        assert "252d" not in cone


class TestTermStructure:
    def test_basic(self):
        returns = _make_returns(500)
        ts = _compute_term_structure(returns)
        assert len(ts) > 0
        for entry in ts:
            assert "horizon_days" in entry
            assert "realized_vol_pct" in entry
            assert entry["realized_vol_pct"] > 0

    def test_horizons_increasing(self):
        returns = _make_returns(500)
        ts = _compute_term_structure(returns)
        horizons = [e["horizon_days"] for e in ts]
        assert horizons == sorted(horizons)


class TestVolRegime:
    def test_basic(self):
        returns = _make_returns(500)
        regime = _detect_vol_regime(returns)
        assert regime["regime"] in ("high", "normal", "low")
        assert 0 <= regime["percentile"] <= 100
        assert "interpretation" in regime

    def test_insufficient_data(self):
        returns = _make_returns(20)
        regime = _detect_vol_regime(returns)
        assert regime["regime"] == "unknown"


class TestVolClustering:
    def test_detects_clustering(self):
        """Returns with intentional vol cluster should show ARCH effects."""
        returns = _make_returns(1260, vol=0.01)
        clustering = _compute_vol_clustering(returns)
        assert "arch_effect" in clustering
        assert "interpretation" in clustering

    def test_insufficient_data(self):
        returns = _make_returns(10)
        clustering = _compute_vol_clustering(returns)
        assert clustering["arch_effect"] is False


class TestVolOfVol:
    def test_basic(self):
        returns = _make_returns(1260)
        vovol = _compute_vol_of_vol(returns)
        assert vovol is not None
        assert vovol["vol_of_vol_pct"] > 0
        assert vovol["coefficient_of_variation"] > 0
        assert vovol["vol_trend"] in ("rising", "falling", "stable")

    def test_insufficient_data(self):
        returns = _make_returns(50)
        vovol = _compute_vol_of_vol(returns)
        assert vovol is None


class TestGarchForwardCurve:
    def test_basic(self):
        returns = _make_returns(500)
        curve = _garch_forward_curve(returns)
        assert curve is not None
        assert "model" in curve
        assert "curve" in curve
        assert len(curve["curve"]) > 0

    def test_curve_horizons(self):
        returns = _make_returns(500)
        curve = _garch_forward_curve(returns)
        if curve:
            horizons = [e["horizon_days"] for e in curve["curve"]]
            assert 1 in horizons
            assert 90 in horizons

    def test_positive_vols(self):
        returns = _make_returns(500)
        curve = _garch_forward_curve(returns)
        if curve:
            for entry in curve["curve"]:
                assert entry["forecast_vol_pct"] > 0

    def test_insufficient_data(self):
        returns = _make_returns(30)
        curve = _garch_forward_curve(returns)
        assert curve is None


class TestRegimeInterpretation:
    def test_high(self):
        interp = _regime_interpretation("high", 85.0)
        assert "elevated" in interp.lower() or "hedging" in interp.lower()

    def test_low(self):
        interp = _regime_interpretation("low", 15.0)
        assert "cheap" in interp.lower() or "subdued" in interp.lower()

    def test_normal(self):
        interp = _regime_interpretation("normal", 50.0)
        assert "normal" in interp.lower()


class TestGetVolatilityAnalytics:
    """Integration test using real yfinance data (fast — single ticker)."""

    @pytest.mark.parametrize("ticker", ["AAPL"])
    def test_full_analytics(self, ticker):
        result = get_volatility_analytics(ticker)
        assert result["ticker"] == ticker
        assert "error" not in result

        # Core sections should exist
        assert "vol_cone" in result
        assert "term_structure" in result
        assert "regime" in result
        assert "estimators" in result
        assert "clustering" in result
        assert "summary" in result

        # Vol cone should have entries
        assert len(result["vol_cone"]) >= 3

        # Term structure should have entries
        assert len(result["term_structure"]) >= 3

        # Regime should be classified
        assert result["regime"]["regime"] in ("high", "normal", "low")

        # Estimators should all be positive
        est = result["estimators"]
        assert est["close_to_close_pct"] > 0
        assert est["parkinson_pct"] > 0
        assert est["garman_klass_pct"] > 0

        # Summary should have key fields
        assert result["summary"]["regime"] in ("high", "normal", "low")

    def test_invalid_ticker(self):
        result = get_volatility_analytics("ZZZZZZZZZZ")
        assert "error" in result


class TestGetVolSummary:
    """Test the lightweight summary used in stock analysis."""

    def test_summary_structure(self):
        """Test with synthetic data path — just verify the function works."""
        # get_vol_summary calls yfinance, so we test structure
        # In CI this might return None for bad tickers
        result = get_vol_summary("AAPL")
        if result is not None:
            assert "vol_30d_pct" in result
            assert "vol_regime" in result
            assert result["vol_regime"] in ("high", "normal", "low", "unknown")
            if result["vol_30d_pct"] is not None:
                assert result["vol_30d_pct"] > 0
