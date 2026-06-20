"""
Cycle 035: Crash Model Floor & Diagnostics Tests
==================================================

Tests that the crash model:
1. Uses configurable probability floor (not hardcoded 0.02)
2. Detects degenerate calibrator output (floor-pinned predictions)
3. Falls back to training base rate when calibrator is out-of-distribution
4. Reports diagnostics accurately
5. Persists calibrator input range through save/load
6. Handles edge cases: empty data, NaN, extreme values, missing base rate
"""

import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

logger = logging.getLogger(__name__)

try:
    import lightgbm  # noqa: F401
    from sklearn.isotonic import IsotonicRegression
    from backend.services.crash_model import CrashPredictor

    _HAS_ML = True
except ImportError:
    _HAS_ML = False

pytestmark = pytest.mark.skipif(not _HAS_ML, reason="lightgbm/sklearn not installed")


# ═══════════════════════════════════════════════════════════════════════════════
# FIXTURES & HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _make_synthetic_data(n_samples=2000, crash_rate=0.12, n_features=20, seed=42):
    """Generate synthetic features + binary crash target for testing."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2010-01-01", periods=n_samples)

    X = pd.DataFrame(
        rng.standard_normal((n_samples, n_features)),
        index=dates,
        columns=[f"feat_{i}" for i in range(n_features)],
    )
    # Make crash labels correlated with first 3 features
    signal = X["feat_0"] + 0.5 * X["feat_1"] - 0.3 * X["feat_2"]
    threshold = np.quantile(signal, 1 - crash_rate)
    y = (signal > threshold).astype(int)

    return X, pd.Series(y, index=dates, name="crash_3m")


def _make_degenerate_calibrator():
    """Create a calibrator that always outputs near-zero."""
    cal = IsotonicRegression(y_min=0.001, y_max=0.99, out_of_bounds="clip")
    cal.fit([0.0, 1.0], [0.0, 0.0])
    return cal


def _make_ceiling_calibrator():
    """Create a calibrator that always outputs near-one."""
    cal = IsotonicRegression(y_min=0.001, y_max=0.99, out_of_bounds="clip")
    cal.fit([0.0, 1.0], [1.0, 1.0])
    return cal


def _make_healthy_calibrator():
    """Create a calibrator that maps scores to varied, realistic probabilities.

    Outputs span [0.02, 0.50] — well above the isotonic floor — so the
    degenerate detector does NOT trigger.
    """
    cal = IsotonicRegression(y_min=0.01, y_max=0.99, out_of_bounds="clip")
    cal.fit(
        [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        [0.02, 0.05, 0.10, 0.20, 0.35, 0.50],
    )
    return cal


@pytest.fixture
def trained_predictor():
    """Train a fresh CrashPredictor on synthetic data."""
    X, y = _make_synthetic_data()
    predictor = CrashPredictor(n_estimators=50, random_state=42)
    targets = {"3m": y}
    result = predictor.train(X, targets, min_train_samples=200)
    assert any(
        r.get("success", False) if isinstance(r, dict) else False
        for r in (result.values() if isinstance(result, dict) and "success" not in result else [result])
    ), f"Training failed: {result}"
    return predictor, X


@pytest.fixture
def multi_horizon_predictor():
    """Train a CrashPredictor with 3m and 6m horizons."""
    X, y_3m = _make_synthetic_data(crash_rate=0.10, seed=42)
    _, y_6m = _make_synthetic_data(crash_rate=0.18, seed=99)
    predictor = CrashPredictor(n_estimators=50, random_state=42)
    targets = {"3m": y_3m, "6m": y_6m}
    result = predictor.train(X, targets, min_train_samples=200)
    return predictor, X


# ═══════════════════════════════════════════════════════════════════════════════
# 1. CONFIGURABLE FLOOR
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfigurableFloor:
    """Test that probability floor comes from config, not hardcoded."""

    def test_floor_from_config(self, trained_predictor):
        predictor, X = trained_predictor
        latest = X.iloc[[-1]]
        probs = predictor.predict_proba(latest, "3m")
        assert probs[0] >= 0.001

    def test_custom_floor_via_config(self, trained_predictor):
        predictor, X = trained_predictor
        latest = X.iloc[[-1]]
        custom_cfg = {
            "prob_floor": 0.05,
            "prob_ceil": 0.90,
            "floor_warn_pct": 0.50,
            "fallback_to_base_rate": False,
        }
        with patch.dict("backend.services.crash_model.config", {
            "ml": {"calibration": custom_cfg},
        }):
            probs = predictor.predict_proba(latest, "3m")
            assert probs[0] >= 0.05, f"Floor not applied: got {probs[0]}"
            assert probs[0] <= 0.90, f"Ceiling not applied: got {probs[0]}"

    def test_ceil_clamps_high_predictions(self, trained_predictor):
        """Ceiling should cap predictions above prob_ceil."""
        predictor, X = trained_predictor
        predictor.calibrators["3m"] = _make_ceiling_calibrator()
        latest = X.iloc[[-1]]

        with patch.dict("backend.services.crash_model.config", {
            "ml": {"calibration": {
                "prob_floor": 0.001,
                "prob_ceil": 0.80,
                "floor_warn_pct": 0.50,
                "fallback_to_base_rate": False,
            }},
        }):
            probs = predictor.predict_proba(latest, "3m")
            assert probs[0] <= 0.80, f"Ceiling not applied: got {probs[0]}"

    def test_old_hardcoded_floor_gone(self):
        """Verify the hardcoded 0.02 clip is no longer in predict_proba."""
        import inspect
        source = inspect.getsource(CrashPredictor.predict_proba)
        assert "0.02" not in source, "Hardcoded 0.02 floor still present in predict_proba"

    def test_config_defaults_when_calibration_section_missing(self, trained_predictor):
        """If config has no calibration section, sane defaults are used."""
        predictor, X = trained_predictor
        latest = X.iloc[[-1]]
        with patch.dict("backend.services.crash_model.config", {"ml": {}}):
            probs = predictor.predict_proba(latest, "3m")
            assert 0.001 <= probs[0] <= 0.999


# ═══════════════════════════════════════════════════════════════════════════════
# 2. DEGENERATE DETECTION + FALLBACK
# ═══════════════════════════════════════════════════════════════════════════════

class TestDegenerateDetection:
    """Test detection and fallback when calibrator output is degenerate."""

    def test_base_rate_fallback_on_degenerate(self, trained_predictor):
        predictor, X = trained_predictor
        predictor.calibrators["3m"] = _make_degenerate_calibrator()
        latest = X.iloc[[-1]]
        base_rate = predictor._train_crash_rate.get("3m", 0.12)

        probs = predictor.predict_proba(latest, "3m")
        assert abs(probs[0] - base_rate) < 0.01, (
            f"Expected base rate fallback ~{base_rate:.3f}, got {probs[0]:.3f}"
        )

    def test_no_fallback_when_disabled(self, trained_predictor):
        predictor, X = trained_predictor
        predictor.calibrators["3m"] = _make_degenerate_calibrator()
        latest = X.iloc[[-1]]

        with patch.dict("backend.services.crash_model.config", {
            "ml": {"calibration": {
                "prob_floor": 0.001,
                "prob_ceil": 0.999,
                "floor_warn_pct": 0.50,
                "fallback_to_base_rate": False,
            }},
        }):
            probs = predictor.predict_proba(latest, "3m")
            assert probs[0] <= 0.002, f"Expected floor value, got {probs[0]:.3f}"

    def test_no_fallback_when_base_rate_missing(self, trained_predictor, caplog):
        """When base rate is not stored, fallback should be skipped gracefully."""
        predictor, X = trained_predictor
        predictor.calibrators["3m"] = _make_degenerate_calibrator()
        predictor._train_crash_rate = {}  # Clear base rate
        latest = X.iloc[[-1]]

        with caplog.at_level(logging.WARNING):
            probs = predictor.predict_proba(latest, "3m")

        # Should stay at floor since no base rate to fall back to
        assert probs[0] <= 0.002, f"Expected floor, got {probs[0]}"
        assert any("pinned at" in r.message for r in caplog.records)

    def test_warning_logged_on_degenerate(self, trained_predictor, caplog):
        predictor, X = trained_predictor
        predictor.calibrators["3m"] = _make_degenerate_calibrator()
        latest = X.iloc[[-1]]

        with caplog.at_level(logging.WARNING):
            predictor.predict_proba(latest, "3m")

        assert any("pinned at" in r.message for r in caplog.records), (
            "Expected 'pinned at' warning in logs"
        )

    def test_no_warning_when_predictions_healthy(self, trained_predictor, caplog):
        """A healthy calibrator producing varied outputs should not trigger the warning."""
        predictor, X = trained_predictor
        predictor.calibrators["3m"] = _make_healthy_calibrator()
        batch = X.iloc[-50:]

        with caplog.at_level(logging.WARNING):
            predictor.predict_proba(batch, "3m")

        floor_warnings = [r for r in caplog.records if "pinned at" in r.message]
        assert len(floor_warnings) == 0, "Healthy model should not trigger floor warning"

    def test_fallback_applies_uniformly_to_batch(self, trained_predictor):
        """When fallback triggers on batch, all rows get base rate."""
        predictor, X = trained_predictor
        predictor.calibrators["3m"] = _make_degenerate_calibrator()
        batch = X.iloc[-10:]
        base_rate = predictor._train_crash_rate.get("3m", 0.12)

        probs = predictor.predict_proba(batch, "3m")
        assert len(probs) == 10
        for i, p in enumerate(probs):
            assert abs(p - base_rate) < 0.01, (
                f"Row {i}: expected base rate ~{base_rate:.3f}, got {p:.3f}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. DIAGNOSTICS
# ═══════════════════════════════════════════════════════════════════════════════

class TestDiagnostics:
    """Test the diagnostics() method."""

    def test_diagnostics_returns_all_horizons(self, trained_predictor):
        predictor, X = trained_predictor
        latest = X.iloc[[-1]]
        diag = predictor.diagnostics(latest)

        assert "3m" in diag
        for key in ["n_predictions", "floor_pct", "degenerate", "base_rate",
                     "calibrator_range", "pred_mean", "pred_std",
                     "using_base_rate_fallback"]:
            assert key in diag["3m"], f"Missing key: {key}"

    def test_diagnostics_healthy_model(self, trained_predictor):
        predictor, X = trained_predictor
        predictor.calibrators["3m"] = _make_healthy_calibrator()
        batch = X.iloc[-50:]
        diag = predictor.diagnostics(batch)

        assert not diag["3m"]["degenerate"]
        assert not diag["3m"]["using_base_rate_fallback"]
        assert diag["3m"]["floor_pct"] < 50.0

    def test_diagnostics_degenerate_model(self, trained_predictor):
        predictor, X = trained_predictor
        predictor.calibrators["3m"] = _make_degenerate_calibrator()
        latest = X.iloc[[-1]]
        diag = predictor.diagnostics(latest)

        assert diag["3m"]["degenerate"], "Degenerate model not detected"
        assert diag["3m"]["using_base_rate_fallback"]
        assert diag["3m"]["floor_pct"] == 100.0

    def test_diagnostics_multi_horizon(self, multi_horizon_predictor):
        predictor, X = multi_horizon_predictor
        latest = X.iloc[[-1]]
        diag = predictor.diagnostics(latest)

        for h in predictor.lgb_models:
            assert h in diag, f"Missing horizon {h} in diagnostics"
            assert isinstance(diag[h]["n_predictions"], int)

    def test_diagnostics_missing_calibrator_range(self, trained_predictor):
        """Model trained before calibrator_input_range was added."""
        predictor, X = trained_predictor
        predictor._calibrator_input_range = {}
        latest = X.iloc[[-1]]
        diag = predictor.diagnostics(latest)

        assert diag["3m"]["calibrator_range"] is None

    def test_diagnostics_with_batch(self, trained_predictor):
        """Diagnostics work correctly on multi-row input."""
        predictor, X = trained_predictor
        batch = X.iloc[-5:]
        diag = predictor.diagnostics(batch)
        assert diag["3m"]["n_predictions"] == 5

    def test_diagnostics_fallback_false_when_config_disabled(self, trained_predictor):
        """using_base_rate_fallback should be False when config disables fallback."""
        predictor, X = trained_predictor
        predictor.calibrators["3m"] = _make_degenerate_calibrator()
        latest = X.iloc[[-1]]

        with patch.dict("backend.services.crash_model.config", {
            "ml": {"calibration": {
                "prob_floor": 0.001,
                "prob_ceil": 0.999,
                "floor_warn_pct": 0.50,
                "fallback_to_base_rate": False,
            }},
        }):
            diag = predictor.diagnostics(latest)
            assert diag["3m"]["degenerate"], "Should detect as degenerate"
            assert not diag["3m"]["using_base_rate_fallback"], (
                "Fallback should be False when config disables it"
            )

    def test_diagnostics_fallback_false_when_base_rate_missing(self, trained_predictor):
        """using_base_rate_fallback should be False when base rate was not stored."""
        predictor, X = trained_predictor
        predictor.calibrators["3m"] = _make_degenerate_calibrator()
        predictor._train_crash_rate = {}
        latest = X.iloc[[-1]]

        diag = predictor.diagnostics(latest)
        assert diag["3m"]["degenerate"]
        assert not diag["3m"]["using_base_rate_fallback"], (
            "Fallback should be False when base rate is missing"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 4. CALIBRATOR RANGE PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════════════

class TestCalibratorRangePersistence:
    """Test that calibrator input range survives save/load."""

    def test_save_load_preserves_range(self, trained_predictor):
        predictor, X = trained_predictor

        assert predictor._calibrator_input_range.get("3m") is not None
        cal_range = predictor._calibrator_input_range["3m"]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test_model.pkl")
            predictor.save_model(path)

            loaded = CrashPredictor()
            loaded.load_model(path)

            assert loaded._calibrator_input_range.get("3m") is not None
            assert loaded._calibrator_input_range["3m"] == cal_range

    def test_load_old_model_without_range(self, trained_predictor):
        """Models saved before this change should load without error."""
        predictor, X = trained_predictor

        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test_model.pkl")
            predictor.save_model(path)

            import joblib
            state = joblib.load(path)
            del state["calibrator_input_range"]
            joblib.dump(state, path)

            loaded = CrashPredictor()
            loaded.load_model(path)
            assert loaded._calibrator_input_range == {}

            latest = X.iloc[[-1]]
            probs = loaded.predict_proba(latest, "3m")
            assert 0 < probs[0] < 1


# ═══════════════════════════════════════════════════════════════════════════════
# 5. PROVENANCE SIDECAR (BACKLOG M3 — the 67-vs-30 guard)
# ═══════════════════════════════════════════════════════════════════════════════

class TestProvenanceSidecar:
    """save_model writes crash_model.meta.json; load_model fails loud on a
    feature-hash mismatch (the exact failure mode that left the overlay broken)."""

    def test_sidecar_written_with_feature_contract(self, trained_predictor):
        import json
        from backend.services.crash_model import _feature_hash, _meta_path

        predictor, _ = trained_predictor
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test_model.pkl")
            predictor.save_model(path)

            meta_path = _meta_path(path)
            assert meta_path.exists(), "sidecar not written"
            meta = json.loads(meta_path.read_text())
            assert meta["n_features"] == len(predictor.feature_names)
            assert meta["feature_hash"] == _feature_hash(predictor.feature_names)
            assert "sklearn_version" in meta and "model_sha256" in meta

    def test_feature_hash_mismatch_fails_loud(self, trained_predictor):
        """A .pkl whose feature_names disagree with the sidecar must NOT load as
        trained — this is what stops a 67-vs-30 model from silently shipping."""
        import joblib

        predictor, _ = trained_predictor
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test_model.pkl")
            predictor.save_model(path)  # writes matching sidecar

            # Corrupt the contract: drop a feature name in the .pkl only.
            state = joblib.load(path)
            state["feature_names"] = state["feature_names"][:-1]
            joblib.dump(state, path)

            loaded = CrashPredictor()
            with pytest.raises(ValueError, match="feature-hash mismatch"):
                loaded.load_model(path)
            assert loaded.is_trained is False

    def test_sidecar_deletion_refuses_to_train(self, trained_predictor):
        """F3 CLOSED: the sidecar-deletion bypass is gone. Delete the sidecar and
        tamper the feature contract — load must now REFUSE (no unverified model
        marks itself trained), not fall through the legacy path."""
        import joblib
        from backend.services.crash_model import _meta_path

        predictor, _ = trained_predictor
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test_model.pkl")
            predictor.save_model(path)
            _meta_path(path).unlink()              # remove provenance
            state = joblib.load(path)
            state["feature_names"] = state["feature_names"][:-1]  # tamper
            joblib.dump(state, path)

            loaded = CrashPredictor()
            with pytest.raises(ValueError, match="no provenance sidecar"):
                loaded.load_model(path)
            assert loaded.is_trained is False      # the bypass is closed

    def test_missing_sidecar_refuses_to_train(self, trained_predictor):
        """F3: a missing sidecar (even on an untampered model) refuses to load —
        provenance is now a hard precondition. Re-saving (which writes a sidecar)
        restores loadability."""
        from backend.services.crash_model import _meta_path

        predictor, X = trained_predictor
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test_model.pkl")
            predictor.save_model(path)
            _meta_path(path).unlink()              # simulate a pre-sidecar model

            loaded = CrashPredictor()
            with pytest.raises(ValueError, match="no provenance sidecar"):
                loaded.load_model(path)
            assert loaded.is_trained is False

            # Re-saving regenerates the sidecar -> loads again.
            predictor.save_model(path)
            recovered = CrashPredictor()
            recovered.load_model(path)
            assert recovered.is_trained is True
            assert 0 < recovered.predict_proba(X.iloc[[-1]], "3m")[0] < 1

    def test_unreadable_sidecar_refuses_to_train(self, trained_predictor):
        """A corrupt/unreadable sidecar is treated like a missing one — refuse."""
        from backend.services.crash_model import _meta_path

        predictor, _ = trained_predictor
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test_model.pkl")
            predictor.save_model(path)
            _meta_path(path).write_text("{ not valid json ]")

            loaded = CrashPredictor()
            with pytest.raises(ValueError, match="sidecar"):
                loaded.load_model(path)
            assert loaded.is_trained is False

    def test_range_is_tuple_of_floats(self, trained_predictor):
        """Calibrator range should be (min_float, max_float)."""
        predictor, _ = trained_predictor
        cal_range = predictor._calibrator_input_range["3m"]
        assert isinstance(cal_range, tuple)
        assert len(cal_range) == 2
        assert isinstance(cal_range[0], float)
        assert isinstance(cal_range[1], float)
        assert cal_range[0] <= cal_range[1]


# ═══════════════════════════════════════════════════════════════════════════════
# 5. EDGE CASES: predict_proba
# ═══════════════════════════════════════════════════════════════════════════════

class TestPredictProbaEdgeCases:
    """Edge cases for predict_proba."""

    def test_untrained_model_raises(self):
        """Calling predict_proba on untrained model raises RuntimeError."""
        predictor = CrashPredictor()
        X = pd.DataFrame({"feat_0": [1.0]})
        with pytest.raises(RuntimeError, match="not trained"):
            predictor.predict_proba(X, "3m")

    def test_unknown_horizon_falls_back(self, trained_predictor):
        """Requesting an untrained horizon falls back to the first available."""
        predictor, X = trained_predictor
        latest = X.iloc[[-1]]
        probs = predictor.predict_proba(latest, "99m")
        assert len(probs) == 1
        assert 0 < probs[0] < 1

    def test_single_row_prediction(self, trained_predictor):
        predictor, X = trained_predictor
        single = X.iloc[[-1]]
        probs = predictor.predict_proba(single, "3m")
        assert probs.shape == (1,)

    def test_nan_features_handled(self, trained_predictor):
        """NaN features should not crash — LightGBM handles NaN natively."""
        predictor, X = trained_predictor
        nan_row = X.iloc[[-1]].copy()
        nan_row.iloc[0, :5] = np.nan  # First 5 features NaN
        probs = predictor.predict_proba(nan_row, "3m")
        assert len(probs) == 1
        assert np.isfinite(probs[0])

    def test_all_nan_features_handled(self, trained_predictor):
        """Completely NaN row should still produce a finite prediction."""
        predictor, X = trained_predictor
        nan_row = X.iloc[[-1]].copy()
        nan_row.iloc[0, :] = np.nan
        probs = predictor.predict_proba(nan_row, "3m")
        assert len(probs) == 1
        assert np.isfinite(probs[0])

    def test_extreme_feature_values(self, trained_predictor):
        """Extreme features should produce clipped but finite predictions."""
        predictor, X = trained_predictor
        extreme = X.iloc[[-1]].copy()
        extreme.iloc[0, 0] = 1e6
        extreme.iloc[0, 1] = -1e6
        probs = predictor.predict_proba(extreme, "3m")
        assert np.isfinite(probs[0])
        assert 0.001 <= probs[0] <= 0.999

    def test_prediction_without_calibrator(self, trained_predictor):
        """When calibrator is missing, raw blend is used."""
        predictor, X = trained_predictor
        predictor.calibrators = {}  # Remove all calibrators
        latest = X.iloc[[-1]]
        probs = predictor.predict_proba(latest, "3m")
        assert 0 < probs[0] < 1

    def test_prediction_without_lr_model(self, trained_predictor):
        """When LR model is missing, LGB-only scores are used."""
        predictor, X = trained_predictor
        predictor.lr_models = {}
        predictor.scalers = {}
        latest = X.iloc[[-1]]
        probs = predictor.predict_proba(latest, "3m")
        assert len(probs) == 1
        assert np.isfinite(probs[0])


# ═══════════════════════════════════════════════════════════════════════════════
# 6. EDGE CASES: _blend_scores
# ═══════════════════════════════════════════════════════════════════════════════

class TestBlendScores:
    """Test the extracted _blend_scores method."""

    def test_blend_returns_tuple(self, trained_predictor):
        predictor, X = trained_predictor
        result = predictor._blend_scores(X.iloc[[-1]], "3m")
        assert isinstance(result, tuple)
        assert len(result) == 2
        scores, horizon = result
        assert isinstance(scores, np.ndarray)
        assert isinstance(horizon, str)

    def test_blend_resolves_unknown_horizon(self, trained_predictor):
        predictor, X = trained_predictor
        scores, resolved = predictor._blend_scores(X.iloc[[-1]], "99m")
        assert resolved in predictor.lgb_models

    def test_blend_scores_in_0_1_range(self, trained_predictor):
        """Blended scores should be valid probabilities."""
        predictor, X = trained_predictor
        scores, _ = predictor._blend_scores(X.iloc[-10:], "3m")
        assert np.all(scores >= 0)
        assert np.all(scores <= 1)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. EDGE CASES: predict_all_horizons
# ═══════════════════════════════════════════════════════════════════════════════

class TestPredictAllHorizons:
    """Test predict_all_horizons including degenerate scenarios."""

    def test_monotonicity_with_degenerate_3m(self, multi_horizon_predictor):
        """Monotonicity should hold even when 3m calibrator is degenerate."""
        predictor, X = multi_horizon_predictor
        predictor.calibrators["3m"] = _make_degenerate_calibrator()
        latest = X.iloc[[-1]]

        probs = predictor.predict_all_horizons(latest)
        if "3m" in probs and "6m" in probs:
            assert probs["3m"][0] <= probs["6m"][0] + 1e-9, (
                f"Monotonicity violated: 3m={probs['3m'][0]:.4f} > 6m={probs['6m'][0]:.4f}"
            )

    def test_all_horizons_returns_dict(self, trained_predictor):
        predictor, X = trained_predictor
        latest = X.iloc[[-1]]
        result = predictor.predict_all_horizons(latest)
        assert isinstance(result, dict)
        assert "3m" in result


# ═══════════════════════════════════════════════════════════════════════════════
# 8. OOB LOGGING
# ═══════════════════════════════════════════════════════════════════════════════

class TestOOBLogging:
    """Test out-of-bounds blended score detection."""

    def test_oob_logged_when_scores_outside_range(self, trained_predictor, caplog):
        """When blended scores exceed calibrator training range, info is logged."""
        predictor, X = trained_predictor
        # Set a very narrow calibrator range so scores fall outside
        predictor._calibrator_input_range["3m"] = (0.49, 0.51)
        latest = X.iloc[[-1]]

        with caplog.at_level(logging.INFO):
            predictor.predict_proba(latest, "3m")

        oob_logs = [r for r in caplog.records if "outside calibrator" in r.message]
        assert len(oob_logs) > 0, "Expected OOB log when scores exceed range"

    def test_no_oob_logged_when_range_missing(self, trained_predictor, caplog):
        """No OOB check when calibrator range is not stored."""
        predictor, X = trained_predictor
        predictor._calibrator_input_range = {}
        latest = X.iloc[[-1]]

        with caplog.at_level(logging.INFO):
            predictor.predict_proba(latest, "3m")

        oob_logs = [r for r in caplog.records if "outside calibrator" in r.message]
        assert len(oob_logs) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 9. ISOTONIC CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsotonicConfig:
    """Test that IsotonicRegression bounds come from config."""

    def test_isotonic_bounds_from_config(self):
        from backend.config import config
        cal_cfg = config["ml"]["calibration"]
        assert "isotonic_y_min" in cal_cfg
        assert "isotonic_y_max" in cal_cfg
        assert 0 < cal_cfg["isotonic_y_min"] < cal_cfg["isotonic_y_max"] < 1

    def test_training_uses_config_isotonic_bounds(self):
        """Training should create calibrator with config-specified bounds."""
        X, y = _make_synthetic_data(n_samples=2000, crash_rate=0.12)

        with patch.dict("backend.services.crash_model.config", {
            "ml": {
                "calibration": {
                    "isotonic_y_min": 0.02,
                    "isotonic_y_max": 0.95,
                    "prob_floor": 0.001,
                    "prob_ceil": 0.999,
                    "floor_warn_pct": 0.50,
                    "fallback_to_base_rate": True,
                },
            },
        }):
            predictor = CrashPredictor(n_estimators=50, random_state=42)
            predictor.train(X, {"3m": y}, min_train_samples=200)

            cal = predictor.calibrators.get("3m")
            assert cal is not None
            assert cal.y_min == 0.02
            assert cal.y_max == 0.95


# ═══════════════════════════════════════════════════════════════════════════════
# 10. ROUTER DIAGNOSTICS ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════════

class TestDiagnosticsRouter:
    """Test the /api/crash/diagnostics endpoint."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        return TestClient(app, raise_server_exceptions=False)

    def test_diagnostics_endpoint_exists(self, client):
        """Endpoint should respond (not 404/405)."""
        r = client.get("/api/crash/diagnostics")
        assert r.status_code != 404, "Diagnostics endpoint not found"
        assert r.status_code != 405, "Diagnostics endpoint wrong method"

    def test_diagnostics_returns_json(self, client):
        """Endpoint should return valid JSON with status key."""
        r = client.get("/api/crash/diagnostics")
        if r.status_code == 200:
            data = r.json()
            assert "status" in data
            assert data["status"] in ("healthy", "degraded", "model_not_trained")

    def test_diagnostics_model_not_trained(self, client):
        """When model file is missing, status should be model_not_trained."""
        from unittest.mock import patch as mock_patch
        from pathlib import Path

        with mock_patch.object(Path, "exists", return_value=False):
            r = client.get("/api/crash/diagnostics")
            if r.status_code == 200:
                assert r.json()["status"] == "model_not_trained"
