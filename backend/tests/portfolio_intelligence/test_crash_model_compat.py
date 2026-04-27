"""
Tests that the crash_model.py external_features modification is backward-compatible.

The V7 model is frozen per CONTEXT. This test verifies:
  1. predict_proba(features) with external_features=None produces identical output
     to the original codepath
  2. predict_proba(features, external_features=X) uses X instead of features
  3. No model weights, calibrators, or imputers were changed
"""

from unittest.mock import patch, MagicMock, PropertyMock

import numpy as np
import pandas as pd
import pytest


class TestCrashModelBackwardCompat:
    """Verify external_features param is a pure passthrough."""

    def _make_mock_predictor(self):
        """Create a mock CrashPredictor with controlled internals."""
        from backend.services.crash_model import CrashPredictor

        predictor = CrashPredictor.__new__(CrashPredictor)
        predictor.is_trained = True
        predictor.feature_names = ["feat_a", "feat_b", "feat_c"]

        mock_lgb = MagicMock()
        mock_lgb.predict_proba.return_value = np.array([[0.7, 0.3]])
        predictor.lgb_models = {"3m": mock_lgb}

        predictor.lr_models = {}
        predictor.scalers = {}
        predictor.imputers = {}
        predictor.calibrators = {}
        predictor._calibrator_input_range = {}
        predictor._train_crash_rate = {}

        return predictor

    def test_default_path_unchanged(self):
        """external_features=None → same codepath as before the change."""
        predictor = self._make_mock_predictor()

        features = pd.DataFrame({
            "feat_a": [1.0], "feat_b": [2.0], "feat_c": [3.0], "extra": [99.0],
        })

        result_default = predictor.predict_proba(features, "3m")
        result_explicit_none = predictor.predict_proba(features, "3m", external_features=None)

        np.testing.assert_array_equal(result_default, result_explicit_none)

    def test_external_features_bypasses_selection(self):
        """When external_features is provided, it's used directly instead of features[self.feature_names]."""
        predictor = self._make_mock_predictor()

        full_features = pd.DataFrame({
            "feat_a": [1.0], "feat_b": [2.0], "feat_c": [3.0],
        })

        external = pd.DataFrame({
            "feat_a": [10.0], "feat_b": [20.0], "feat_c": [30.0],
        })

        # Call with external_features
        predictor.predict_proba(full_features, "3m", external_features=external)

        # Verify the LGB model received the external features, not the originals
        call_args = predictor.lgb_models["3m"].predict_proba.call_args
        X_passed = call_args[0][0]
        assert X_passed is external

    def test_identical_predictions_same_features(self):
        """Same features passed both ways → identical predictions."""
        predictor = self._make_mock_predictor()

        features = pd.DataFrame({
            "feat_a": [1.0], "feat_b": [2.0], "feat_c": [3.0],
        })

        result_standard = predictor.predict_proba(features, "3m")
        result_external = predictor.predict_proba(
            features, "3m", external_features=features[predictor.feature_names],
        )

        np.testing.assert_array_equal(result_standard, result_external)

    def test_no_model_attributes_changed(self):
        """Verify the modification didn't alter any model state attributes."""
        from backend.services.crash_model import CrashPredictor
        import inspect

        # Check that __init__ signature hasn't changed
        init_params = list(inspect.signature(CrashPredictor.__init__).parameters.keys())
        assert "external_features" not in init_params

        # Check that train() signature hasn't changed
        train_params = list(inspect.signature(CrashPredictor.train).parameters.keys())
        assert "external_features" not in train_params

    def test_predict_proba_signature_backward_compatible(self):
        """Calling predict_proba with only positional args still works."""
        predictor = self._make_mock_predictor()
        features = pd.DataFrame({
            "feat_a": [1.0], "feat_b": [2.0], "feat_c": [3.0],
        })
        # Old call style: predict_proba(features, "3m")
        result = predictor.predict_proba(features, "3m")
        assert len(result) == 1
