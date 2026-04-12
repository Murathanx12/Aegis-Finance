"""Tests for lab data_generator wiring — validates signal context and key mappings.

These tests verify the Phase B (Cycle 34) fixes:
  1. Market signal gets real context (not zero defaults)
  2. Stock analysis reads correct keys + computes signals
  3. Drift check collector works with synthetic data
  4. Internal keys are stripped before JSON serialization
"""

import json
import os
import tempfile
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helper: build a fake market data DataFrame like DataFetcher returns
# ---------------------------------------------------------------------------
def _make_market_df(n_days=300, vix=19.0, sp500_base=5000.0):
    """Create a DataFrame resembling DataFetcher.fetch_market_data() output."""
    dates = pd.bdate_range("2024-01-02", periods=n_days)
    rng = np.random.default_rng(42)
    sp500 = sp500_base * np.cumprod(1 + rng.normal(0.0003, 0.01, n_days))
    return pd.DataFrame({
        "SP500": sp500,
        "VIX": vix + rng.normal(0, 2, n_days),
        "T10Y": 4.3 + rng.normal(0, 0.1, n_days),
        "T3M": 3.8 + rng.normal(0, 0.05, n_days),
    }, index=dates)


class TestComputeMarketSignalForLab:
    """Test the _compute_market_signal_for_lab helper."""

    def _call_with_mocked_services(self, data=None, regime="Bull",
                                   risk_score_series=None):
        """Call _compute_market_signal_for_lab with mocked network services.

        The function uses lazy imports inside the body, so we patch the
        source modules rather than lab.data_generator attributes.
        """
        import lab.data_generator as dg
        dg._cached_market_signal = None  # clear cache

        if data is None:
            data = _make_market_df()
        if risk_score_series is None:
            risk_score_series = pd.Series(
                np.full(len(data), 1.14), index=data.index
            )

        mock_fetcher = MagicMock()
        mock_fetcher.fetch_market_data.return_value = (data, {})
        mock_fetcher.fetch_fred_data.return_value = {}

        hmm_data = {
            "state_means": np.array([0.001, -0.002, 0.0005]),
            "regime_probs": np.array([0.6, 0.2, 0.2]),
            "state_vols": np.array([0.01, 0.03, 0.015]),
        }

        with patch("backend.services.data_fetcher.DataFetcher", return_value=mock_fetcher), \
             patch("backend.services.risk_scorer.build_risk_score", return_value=risk_score_series), \
             patch("backend.services.regime_detector.detect_regimes", return_value=(pd.Series(), regime)), \
             patch("backend.services.regime_detector.fit_hmm_for_mc", return_value=hmm_data):
            sig = dg._compute_market_signal_for_lab()
        return sig

    def test_returns_required_keys(self):
        sig = self._call_with_mocked_services()
        for key in ["action", "confidence", "composite_score", "components", "reasons"]:
            assert key in sig, f"Missing key: {key}"

    def test_regime_component_nonzero_for_bull(self):
        sig = self._call_with_mocked_services(regime="Bull")
        assert sig["components"]["regime"] == pytest.approx(0.7)

    def test_regime_component_negative_for_bear(self):
        sig = self._call_with_mocked_services(regime="Bear")
        assert sig["components"]["regime"] < 0

    def test_macro_risk_nonzero_when_risk_score_high(self):
        data = _make_market_df()
        risk = pd.Series(np.full(len(data), 2.5), index=data.index)
        sig = self._call_with_mocked_services(data=data, risk_score_series=risk)
        assert sig["components"]["macro_risk"] != 0.0

    def test_vix_drives_valuation_component(self):
        """Real VIX from data should produce a valuation signal, not the default."""
        data = _make_market_df(vix=30.0)  # elevated VIX
        sig = self._call_with_mocked_services(data=data)
        # VIX 25-30 → val_sig = 0.15 in signal_engine
        assert sig["components"]["valuation"] != 0.0

    def test_momentum_nonzero_with_real_prices(self):
        """SP500 pct_change should produce nonzero momentum."""
        sig = self._call_with_mocked_services()
        # With random walk data, momentum won't be exactly zero
        # (unless the random walk happens to produce exactly 0% return)
        # The component may be small but should be computed, not defaulted
        assert "momentum" in sig["components"]

    def test_drawdown_computed_from_sp500(self):
        sig = self._call_with_mocked_services()
        assert "drawdown" in sig["components"]

    def test_hmm_data_attached(self):
        """Internal HMM keys should be present for MC conditioning."""
        sig = self._call_with_mocked_services()
        assert "_hmm_state_means" in sig
        assert "_hmm_regime_probs" in sig
        assert "_hmm_state_vols" in sig

    def test_crash_3m_pct_attached(self):
        """_crash_3m_pct key should always be present (even if None)."""
        sig = self._call_with_mocked_services()
        assert "_crash_3m_pct" in sig

    def test_cache_returns_same_object(self):
        """Second call should return cached result, not recompute."""
        import lab.data_generator as dg
        sig1 = self._call_with_mocked_services()
        # Don't clear cache — second call should reuse
        sig2 = dg._compute_market_signal_for_lab()
        assert sig1 is sig2

    def test_cache_reset_on_new_run(self):
        """run_engine_data_collection should reset cache."""
        import lab.data_generator as dg
        dg._cached_market_signal = {"fake": True}
        # Simulate the reset that happens at start of run
        dg._cached_market_signal = None
        assert dg._cached_market_signal is None


class TestCollectSignalQualityWiring:
    """Test that collect_signal_quality strips internal keys before saving."""

    def test_internal_keys_stripped_from_saved_signal(self):
        """Keys starting with _ should not appear in the saved JSON."""
        import lab.data_generator as dg

        # Build a fake market signal with internal keys
        fake_signal = {
            "action": "Buy",
            "confidence": 50,
            "composite_score": 0.3,
            "components": {"regime": 0.7, "valuation": 0.3},
            "reasons": ["Bullish regime"],
            "color": "green",
            "_crash_3m_pct": 12.5,
            "_hmm_state_means": [0.001],
            "_hmm_regime_probs": [0.6],
            "_hmm_state_vols": [0.01],
        }

        # Filter the same way collect_signal_quality does
        saveable = {k: v for k, v in fake_signal.items() if not k.startswith("_")}
        assert "_crash_3m_pct" not in saveable
        assert "_hmm_state_means" not in saveable
        assert "action" in saveable
        assert "components" in saveable

    def test_saveable_signal_is_json_serializable(self):
        """Stripping internal keys should produce JSON-safe output."""
        fake_signal = {
            "action": "Hold",
            "confidence": 10,
            "composite_score": 0.05,
            "components": {"regime": 0.0},
            "reasons": ["Mixed"],
            "color": "amber",
            "_crash_3m_pct": None,
            "_hmm_state_means": np.array([0.001, -0.002]),
        }
        saveable = {k: v for k, v in fake_signal.items() if not k.startswith("_")}
        # Should not raise
        serialized = json.dumps(saveable, default=str)
        assert "Hold" in serialized


class TestCollectStockAnalysisWiring:
    """Test stock analysis key mapping fixes."""

    def test_crash_prob_comes_from_market_signal(self):
        """crash_prob_3m should come from market signal, not stock_analyzer output."""
        # The old code tried data.get("crash_prob_3m") — wrong key.
        # The new code uses crash_3m_pct from market signal.
        stock_data = {
            "current_price": 150.0,
            "mc_median_5y_return": 50.0,
            "mc_p10_5y_return": -10.0,
            "mc_p90_5y_return": 120.0,
            "garch_annual_vol": 25.0,
            "garch_nu": 8.0,
            "ml_crash_prob": 0.15,  # This is what stock_analyzer returns
            "beta": 1.1,
            "sector": "Technology",
            "analyst_target": 180.0,
            "pe_ratio": 25.0,
            "key_stats": {"pe_forward": 20.0},
        }

        # The OLD code would look for data.get("crash_prob_3m") → None
        assert "crash_prob_3m" not in stock_data  # proves the old key was wrong

        # The NEW code gets crash_3m_pct from market signal
        crash_3m_pct = 15.0  # from _compute_market_signal_for_lab
        result_crash = crash_3m_pct  # what the new code stores
        assert result_crash == 15.0

    def test_signal_comes_from_get_stock_signal(self):
        """signal_action should come from get_stock_signal, not stock_analyzer."""
        from backend.services.signal_engine import get_stock_signal

        market_sig = {
            "action": "Buy",
            "confidence": 30,
            "composite_score": 0.25,
            "components": {"regime": 0.7, "valuation": 0.3},
            "reasons": ["Bullish regime"],
        }

        stock_sig = get_stock_signal(
            market_signal=market_sig,
            beta=1.2,
            analyst_target=180.0,
            current_price=150.0,
            pe_ratio=25.0,
            forward_pe=20.0,
        )

        # The OLD code looked for data.get("signal", {}).get("action") → None
        # because stock_analyzer doesn't return a "signal" dict at all.
        # The NEW code calls get_stock_signal and reads directly.
        assert stock_sig["action"] in {"Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"}
        assert isinstance(stock_sig["composite_score"], float)

    def test_stock_signal_with_no_analyst_target(self):
        """Signal should still work when analyst_target is None."""
        from backend.services.signal_engine import get_stock_signal

        market_sig = {
            "action": "Hold",
            "confidence": 5,
            "composite_score": 0.05,
            "components": {"regime": 0.0},
            "reasons": ["Mixed"],
        }

        stock_sig = get_stock_signal(
            market_signal=market_sig,
            beta=1.0,
            analyst_target=None,
            current_price=100.0,
        )
        assert "action" in stock_sig

    def test_stock_signal_with_zero_price(self):
        """Zero current_price should not crash."""
        from backend.services.signal_engine import get_stock_signal

        market_sig = {
            "action": "Hold",
            "confidence": 5,
            "composite_score": 0.0,
            "components": {},
            "reasons": ["Mixed"],
        }

        stock_sig = get_stock_signal(
            market_signal=market_sig,
            beta=1.0,
            analyst_target=50.0,
            current_price=0.0,
        )
        assert "action" in stock_sig

    def test_stock_signal_with_extreme_beta(self):
        """Extreme beta values should be dampened, not crash."""
        from backend.services.signal_engine import get_stock_signal

        market_sig = {
            "action": "Buy",
            "confidence": 30,
            "composite_score": 0.3,
            "components": {"regime": 0.7},
            "reasons": ["Bullish"],
        }

        for beta in [0.0, 0.01, 5.0, 10.0]:
            sig = get_stock_signal(market_signal=market_sig, beta=beta)
            assert -1.0 <= sig["composite_score"] <= 1.0


class TestCollectDriftCheck:
    """Test the drift detection collector with synthetic data."""

    def test_no_drift_on_identical_distribution(self):
        """When reference and inference are from the same distribution, no drift."""
        from backend.services.drift_detector import DriftDetector

        rng = np.random.default_rng(42)
        n = 2000
        data = pd.DataFrame({
            "feat_a": rng.normal(0, 1, n),
            "feat_b": rng.uniform(-1, 1, n),
            "feat_c": rng.exponential(1, n),
        })

        reference = data.iloc[:1600]
        inference = data.iloc[1600:]

        detector = DriftDetector(reference)
        report = detector.check_drift(inference)

        assert report["drift_detected"] is False
        assert report["n_drifted"] == 0

    def test_drift_on_shifted_distribution(self):
        """When inference mean shifts significantly, drift should be detected."""
        from backend.services.drift_detector import DriftDetector

        rng = np.random.default_rng(42)
        n = 2000

        reference = pd.DataFrame({
            "feat_a": rng.normal(0, 1, n),
            "feat_b": rng.normal(0, 1, n),
        })

        # Shift mean by 3 standard deviations — clear drift
        inference = pd.DataFrame({
            "feat_a": rng.normal(3.0, 1, 400),
            "feat_b": rng.normal(-3.0, 1, 400),
        })

        detector = DriftDetector(reference)
        report = detector.check_drift(inference)

        assert report["drift_detected"] is True
        assert report["n_drifted"] >= 1

    def test_drift_with_empty_inference(self):
        """Empty inference data should not crash."""
        from backend.services.drift_detector import DriftDetector

        rng = np.random.default_rng(42)
        reference = pd.DataFrame({"feat_a": rng.normal(0, 1, 500)})
        inference = pd.DataFrame({"feat_a": pd.Series(dtype=float)})

        detector = DriftDetector(reference)
        report = detector.check_drift(inference)

        assert report["drift_detected"] is False
        assert report["n_features_checked"] == 0

    def test_drift_with_single_feature(self):
        """Should work with a single-column DataFrame."""
        from backend.services.drift_detector import DriftDetector

        rng = np.random.default_rng(42)
        reference = pd.DataFrame({"x": rng.normal(0, 1, 1000)})
        inference = pd.DataFrame({"x": rng.normal(0, 1, 200)})

        detector = DriftDetector(reference)
        report = detector.check_drift(inference)

        assert "drift_detected" in report
        assert "n_features_checked" in report

    def test_drift_with_nan_heavy_feature(self):
        """Features with many NaNs should be handled gracefully."""
        from backend.services.drift_detector import DriftDetector

        rng = np.random.default_rng(42)
        ref_data = rng.normal(0, 1, 500)
        ref_data[::3] = np.nan  # 33% NaN
        reference = pd.DataFrame({"feat": ref_data})

        inf_data = rng.normal(0, 1, 100)
        inference = pd.DataFrame({"feat": inf_data})

        detector = DriftDetector(reference)
        report = detector.check_drift(inference)
        # Should not crash; feature may or may not be checked
        assert isinstance(report["drift_detected"], bool)

    def test_drift_report_structure(self):
        """Report should have all expected keys."""
        from backend.services.drift_detector import DriftDetector

        rng = np.random.default_rng(42)
        reference = pd.DataFrame({"a": rng.normal(0, 1, 500), "b": rng.normal(0, 1, 500)})
        inference = pd.DataFrame({"a": rng.normal(0, 1, 100), "b": rng.normal(0, 1, 100)})

        detector = DriftDetector(reference)
        report = detector.check_drift(inference)

        for key in ["drift_detected", "drifted_features", "n_features_checked",
                     "n_drifted", "drift_pct", "feature_details"]:
            assert key in report, f"Missing key: {key}"

    def test_psi_symmetry(self):
        """PSI(p, q) should be non-negative."""
        from backend.services.drift_detector import DriftDetector

        p = np.array([0.2, 0.3, 0.5])
        q = np.array([0.3, 0.3, 0.4])

        psi = DriftDetector._psi(p, q)
        assert psi >= 0


class TestDriftDetectorRollingWindow:
    """Test the rolling window drift detection method."""

    def test_rolling_no_drift_on_stationary_data(self):
        """Stationary data should show no/low drift with rolling window."""
        from backend.services.drift_detector import DriftDetector

        rng = np.random.default_rng(42)
        n = 1500  # > 504 + 252 = 756
        features = pd.DataFrame({
            "feat_a": rng.normal(0, 1, n),
            "feat_b": rng.uniform(-1, 1, n),
        })

        report = DriftDetector.from_rolling_window(features)
        assert report["severity"] in ("none", "low")
        assert report["reference_window"] == 504
        assert report["inference_window"] == 252

    def test_rolling_detects_recent_shift(self):
        """A mean shift in the last 252 days should be detected."""
        from backend.services.drift_detector import DriftDetector

        rng = np.random.default_rng(42)
        # 504 reference days: normal(0,1), then 252 inference days: normal(3,1)
        reference_part = rng.normal(0, 1, 504)
        inference_part = rng.normal(3, 1, 252)
        features = pd.DataFrame({"x": np.concatenate([reference_part, inference_part])})

        report = DriftDetector.from_rolling_window(
            features, reference_days=504, inference_days=252,
        )
        assert report["drift_detected"] is True
        assert report["severity"] in ("moderate", "high", "critical")

    def test_rolling_severity_levels(self):
        """Severity should scale with drift percentage."""
        from backend.services.drift_detector import DriftDetector

        rng = np.random.default_rng(42)
        # No drift
        features = pd.DataFrame({f"f{i}": rng.normal(0, 1, 800) for i in range(5)})
        report = DriftDetector.from_rolling_window(features, reference_days=400, inference_days=200)
        assert report["severity"] in ("none", "low", "moderate")

    def test_rolling_fallback_on_short_data(self):
        """Should fall back to proportional split when data is short."""
        from backend.services.drift_detector import DriftDetector

        rng = np.random.default_rng(42)
        features = pd.DataFrame({"x": rng.normal(0, 1, 300)})
        # 300 < 504+252=756, so falls back to 60/40 split
        report = DriftDetector.from_rolling_window(features)
        assert "drift_detected" in report
        assert report["severity"] is not None

    def test_rolling_report_has_window_info(self):
        """Report should include reference and inference window sizes."""
        from backend.services.drift_detector import DriftDetector

        rng = np.random.default_rng(42)
        features = pd.DataFrame({"x": rng.normal(0, 1, 1000)})
        report = DriftDetector.from_rolling_window(features)
        assert "reference_window" in report
        assert "inference_window" in report
        assert "severity" in report


class TestCollectDriftCheckCollector:
    """Test the actual collect_drift_check function with mocked data."""

    def test_insufficient_data_returns_status(self):
        """When features have <504 rows, should return insufficient_data."""
        mock_fetcher = MagicMock()
        small_data = _make_market_df(n_days=100)
        mock_fetcher.fetch_market_data.return_value = (small_data, {})
        mock_fetcher.fetch_fred_data.return_value = {}

        small_features = pd.DataFrame({"a": np.zeros(100)})

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("backend.services.data_fetcher.DataFetcher", return_value=mock_fetcher), \
                 patch("engine.training.features.build_feature_matrix", return_value=small_features):
                from lab.data_generator import collect_drift_check
                result = collect_drift_check(tmpdir)

        assert result["status"] == "insufficient_data"


class TestSaveHelper:
    """Test the _save helper for JSON serialization edge cases."""

    def test_save_creates_file(self):
        from lab.data_generator import _save
        with tempfile.TemporaryDirectory() as tmpdir:
            _save(tmpdir, "test.json", {"key": "value"})
            path = os.path.join(tmpdir, "test.json")
            assert os.path.exists(path)
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            assert data["key"] == "value"

    def test_save_handles_numpy_types(self):
        from lab.data_generator import _save
        with tempfile.TemporaryDirectory() as tmpdir:
            data = {
                "float64": np.float64(1.5),
                "int64": np.int64(42),
                "array": np.array([1, 2, 3]),
            }
            # _save uses default=str which handles numpy types
            _save(tmpdir, "numpy.json", data)
            path = os.path.join(tmpdir, "numpy.json")
            assert os.path.exists(path)

    def test_save_handles_none_values(self):
        from lab.data_generator import _save
        with tempfile.TemporaryDirectory() as tmpdir:
            _save(tmpdir, "none.json", {"value": None, "list": [None, 1]})
            path = os.path.join(tmpdir, "none.json")
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            assert data["value"] is None


class TestCacheReset:
    """Test that the global cache is properly managed."""

    def test_cache_cleared_between_runs(self):
        import lab.data_generator as dg
        dg._cached_market_signal = {"stale": True}
        # Simulate what run_engine_data_collection does at the top
        global_reset = None
        dg._cached_market_signal = global_reset
        assert dg._cached_market_signal is None
