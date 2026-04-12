"""
Aegis Finance — Crash Prediction Model
=========================================

Multi-horizon crash probability estimator using:
  - LightGBM (primary — best single-model Brier score)
  - Logistic Regression (secondary — better generalization with sparse crashes)

Simplified from V7's 5-model ensemble. Isotonic calibration maps raw scores
to monotonically increasing probabilities.

Usage:
    from backend.services.crash_model import CrashPredictor

    predictor = CrashPredictor()
    predictor.load_model("backend/models/crash_model.pkl")
    probs = predictor.predict_proba(features, horizon="3m")
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from backend.config import config

logger = logging.getLogger(__name__)

try:
    import lightgbm as lgb
    from sklearn.isotonic import IsotonicRegression
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.impute import SimpleImputer
    from sklearn.metrics import brier_score_loss, roc_auc_score
    import joblib

    _HAS_ML = True
except ImportError:
    _HAS_ML = False


class CrashPredictor:
    """Multi-horizon LightGBM + Logistic crash probability estimator.

    Two models:
      - LightGBM: captures nonlinear interactions, best Brier score
      - Logistic Regression: linear baseline, better calibration on sparse data

    Final prediction: weighted blend (70% LightGBM, 30% Logistic).
    """

    def __init__(
        self,
        n_estimators: int = 800,
        random_state: int = 42,
        lgb_weight: float = 0.70,
    ):
        self.n_estimators = n_estimators
        self.random_state = random_state
        self.lgb_weight = lgb_weight

        self.lgb_models: dict = {}  # {horizon: lgb model}
        self.lr_models: dict = {}  # {horizon: logistic model}
        self.calibrators: dict = {}  # {horizon: IsotonicRegression}
        self.scalers: dict = {}  # {horizon: StandardScaler}
        self.imputers: dict = {}  # {horizon: SimpleImputer (median)}
        self.feature_names: Optional[list[str]] = None
        self.is_trained: bool = False
        self._train_crash_rate: dict = {}
        self._calibrator_input_range: dict = {}  # {horizon: (min, max)} of fitted blended scores

    def train(
        self,
        features: pd.DataFrame,
        targets: dict,
        train_end_idx: Optional[int] = None,
        min_train_samples: int = 1260,
    ) -> dict:
        """Train crash predictors for each horizon.

        Args:
            features: Feature matrix (backward-looking only)
            targets: Dict of {horizon: binary_series} e.g. {"3m": ..., "6m": ..., "12m": ...}
            train_end_idx: Temporal cutoff (expanding window)
            min_train_samples: Minimum observations needed

        Returns:
            Dict with training metrics
        """
        if not _HAS_ML:
            return {"success": False, "reason": "lightgbm/sklearn not installed"}

        if train_end_idx is not None:
            X = features.iloc[:train_end_idx].copy()
            target_slices = {
                h: t.iloc[:train_end_idx].copy() for h, t in targets.items()
            }
        else:
            X = features.copy()
            target_slices = {h: t.copy() for h, t in targets.items()}

        self.feature_names = list(X.columns)

        results = {}
        for horizon, target in target_slices.items():
            r = self._train_horizon(X, target, horizon, min_train_samples)
            results[horizon] = r

        if not self.lgb_models:
            return {"success": False, "reason": "No horizon trained successfully"}

        self.is_trained = True
        return results

    def _train_horizon(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        horizon: str,
        min_train_samples: int,
    ) -> dict:
        """Train both LightGBM and Logistic models for one horizon."""
        valid = y.notna() & X.notna().any(axis=1)
        X_h = X[valid]
        y_h = y[valid].astype(int)

        if len(X_h) < min_train_samples or y_h.nunique() < 2:
            return {"success": False, "reason": f"Insufficient data: {len(X_h)} samples"}

        self._train_crash_rate[horizon] = float(y_h.mean())

        # Purged train/val split
        gap_days = {"3m": 70, "6m": 140, "12m": 265}.get(horizon, 265)
        val_size = max(504, len(X_h) // 5)
        split_idx = len(X_h) - val_size - gap_days

        if split_idx < min(1260, len(X_h) // 2):
            split_idx = len(X_h) - val_size
            gap_days = 0

        train_X = X_h.iloc[:split_idx]
        train_y = y_h.iloc[:split_idx]
        val_X = X_h.iloc[split_idx + gap_days:]
        val_y = y_h.iloc[split_idx + gap_days:]

        if len(val_y) < 50 or val_y.nunique() < 2:
            split_idx = int(len(X_h) * 0.8)
            train_X = X_h.iloc[:split_idx]
            train_y = y_h.iloc[:split_idx]
            val_X = X_h.iloc[split_idx:]
            val_y = y_h.iloc[split_idx:]

        if train_y.nunique() < 2:
            return {"success": False, "reason": "Single class in training set"}

        # Sample weights: uniqueness-based if enabled, else temporal decay
        use_uniqueness = config["ml"].get("sample_uniqueness", False)
        if use_uniqueness:
            try:
                from engine.training.sample_uniqueness import (
                    compute_sample_weights,
                    compute_horizon_end_dates,
                )
                horizon_days_map = {"3m": 63, "6m": 126, "12m": 252}
                h_days = horizon_days_map.get(horizon, 63)
                obs_dates = train_X.index
                price_dates = X_h.index
                end_dates = compute_horizon_end_dates(obs_dates, h_days, price_dates)
                temporal_weights = compute_sample_weights(
                    obs_dates, end_dates, price_dates, temporal_decay=True
                )
                logger.info("  %s: Using uniqueness-weighted samples", horizon)
            except Exception as e:
                logger.warning("  %s: Uniqueness weighting failed (%s), using temporal", horizon, e)
                temporal_weights = np.linspace(0.5, 1.5, len(train_X))
        else:
            temporal_weights = np.linspace(0.5, 1.5, len(train_X))

        # ── LightGBM ──────────────────────────────────────────────────
        pos_rate = float(train_y.mean())
        scale_pos = min((1 - pos_rate) / max(pos_rate, 0.01), 10.0)

        lgb_params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "n_estimators": self.n_estimators,
            "max_depth": 7,
            "num_leaves": 40,
            "learning_rate": 0.008,
            "min_child_samples": 30,
            "subsample": 0.75,
            "colsample_bytree": 0.65,
            "reg_alpha": 0.05,
            "reg_lambda": 0.5,
            "min_gain_to_split": 0.002,
            "scale_pos_weight": scale_pos,
            "random_state": self.random_state,
            "verbose": -1,
            "n_jobs": -1,
        }

        lgb_model = lgb.LGBMClassifier(**lgb_params)

        # Handle single-class validation set
        eval_X, eval_y = val_X, val_y
        if val_y.nunique() < 2:
            eval_split = max(50, int(len(train_X) * 0.1))
            eval_X = train_X.iloc[-eval_split:]
            eval_y = train_y.iloc[-eval_split:]

        lgb_model.fit(
            train_X,
            train_y,
            sample_weight=temporal_weights,
            eval_set=[(eval_X, eval_y)],
            callbacks=[
                lgb.early_stopping(stopping_rounds=100, verbose=False),
                lgb.log_evaluation(period=0),
            ],
        )
        self.lgb_models[horizon] = lgb_model

        # ── Logistic Regression ─────────────────────────────────────
        imputer = SimpleImputer(strategy="median")
        train_X_imputed = imputer.fit_transform(train_X)
        val_X_imputed = imputer.transform(val_X)
        scaler = StandardScaler()
        train_X_scaled = scaler.fit_transform(train_X_imputed)
        val_X_scaled = scaler.transform(val_X_imputed)

        lr_model = LogisticRegression(
            penalty="l2",
            C=0.1,
            class_weight="balanced",
            max_iter=2000,
            random_state=self.random_state,
        )
        lr_model.fit(train_X_scaled, train_y, sample_weight=temporal_weights)
        self.lr_models[horizon] = lr_model
        self.scalers[horizon] = scaler
        self.imputers[horizon] = imputer

        # ── Isotonic calibration on first half of val, metrics on second ──
        lgb_raw = lgb_model.predict_proba(val_X)[:, 1]
        lr_raw = lr_model.predict_proba(val_X_scaled)[:, 1]
        blended_raw = self.lgb_weight * lgb_raw + (1 - self.lgb_weight) * lr_raw

        # Split validation into calibration (first 60%) and test (last 40%)
        cal_split = max(20, int(len(val_X) * 0.6))
        cal_raw, test_raw = blended_raw[:cal_split], blended_raw[cal_split:]
        cal_y_fit, test_y = val_y.values[:cal_split], val_y.values[cal_split:]

        cal_cfg = config["ml"].get("calibration", {})
        calibrator = IsotonicRegression(
            y_min=cal_cfg.get("isotonic_y_min", 0.01),
            y_max=cal_cfg.get("isotonic_y_max", 0.99),
            out_of_bounds="clip",
        )
        calibrator.fit(cal_raw, cal_y_fit)
        self.calibrators[horizon] = calibrator
        self._calibrator_input_range[horizon] = (
            float(np.min(cal_raw)),
            float(np.max(cal_raw)),
        )

        # ── Metrics on held-out test portion ────────────────────────
        if len(test_raw) >= 10:
            cal_probs = calibrator.predict(test_raw)
            val_brier = brier_score_loss(test_y, cal_probs)
        else:
            # Fallback: evaluate on full val if test portion too small
            cal_probs = calibrator.predict(blended_raw)
            val_brier = brier_score_loss(val_y, cal_probs)

        try:
            eval_y = test_y if len(test_raw) >= 10 else val_y
            val_auc = roc_auc_score(eval_y, cal_probs)
        except ValueError:
            val_auc = 0.5

        logger.info(
            "  %s: Brier=%.4f, AUC=%.3f, crash_rate=%.1f%%, range=[%.2f, %.2f]",
            horizon,
            val_brier,
            val_auc,
            pos_rate * 100,
            cal_probs.min(),
            cal_probs.max(),
        )

        return {
            "success": True,
            "horizon": horizon,
            "n_train": len(train_X),
            "n_val": len(val_X),
            "pos_rate": pos_rate,
            "val_brier": float(val_brier),
            "val_auc": float(val_auc),
            "pred_range": (float(cal_probs.min()), float(cal_probs.max())),
            "pred_std": float(cal_probs.std()),
        }

    def _blend_scores(
        self, features: pd.DataFrame, horizon: str
    ) -> tuple[np.ndarray, str]:
        """Compute blended LGB+LR scores for a given horizon.

        Returns (blended_scores, resolved_horizon) where resolved_horizon
        is the actual horizon used (may differ if requested horizon was missing).
        """
        X = features[self.feature_names] if isinstance(features, pd.DataFrame) else features

        if horizon not in self.lgb_models:
            horizon = list(self.lgb_models.keys())[0]

        lgb_raw = self.lgb_models[horizon].predict_proba(X)[:, 1]

        if horizon in self.lr_models and horizon in self.scalers:
            try:
                X_imputed = self.imputers[horizon].transform(
                    X if isinstance(X, pd.DataFrame) else X
                ) if horizon in self.imputers else (
                    X.fillna(X.median()) if isinstance(X, pd.DataFrame) else X
                )
                X_scaled = self.scalers[horizon].transform(X_imputed)
                lr_raw = self.lr_models[horizon].predict_proba(X_scaled)[:, 1]
                blended = self.lgb_weight * lgb_raw + (1 - self.lgb_weight) * lr_raw
            except (AttributeError, ValueError) as e:
                logger.warning("LR predict_proba failed for %s (%s), using LGB only", horizon, e)
                blended = lgb_raw
        else:
            blended = lgb_raw

        return blended, horizon

    def predict_proba(
        self, features: pd.DataFrame, horizon: str = "3m"
    ) -> np.ndarray:
        """Predict calibrated crash probability.

        Pipeline: features -> LightGBM + Logistic blend -> isotonic calibration
        """
        if not self.is_trained:
            raise RuntimeError("Model not trained — call train() or load_model() first")

        cal_cfg = config["ml"].get("calibration", {})
        prob_floor = cal_cfg.get("prob_floor", 0.001)
        prob_ceil = cal_cfg.get("prob_ceil", 0.999)
        floor_warn_pct = cal_cfg.get("floor_warn_pct", 0.50)
        use_base_rate_fallback = cal_cfg.get("fallback_to_base_rate", True)
        isotonic_y_min = cal_cfg.get("isotonic_y_min", 0.01)

        blended, horizon = self._blend_scores(features, horizon)

        if horizon in self.calibrators:
            # Check for out-of-distribution blended scores
            cal_range = self._calibrator_input_range.get(horizon)
            if cal_range is not None:
                oob_low = int(np.sum(blended < cal_range[0]))
                oob_high = int(np.sum(blended > cal_range[1]))
                if oob_low + oob_high > 0:
                    logger.info(
                        "Crash model %s: %d/%d blended scores outside calibrator "
                        "training range [%.3f, %.3f] (low=%d, high=%d)",
                        horizon, oob_low + oob_high, len(blended),
                        cal_range[0], cal_range[1], oob_low, oob_high,
                    )
            calibrated = self.calibrators[horizon].predict(blended)
        else:
            calibrated = blended

        clipped = np.clip(calibrated, prob_floor, prob_ceil)

        # Detect degenerate calibrator output: when most predictions are
        # pinned at or near the calibrator floor (isotonic_y_min), the model
        # is likely out-of-distribution (e.g. from feature drift). The check
        # uses isotonic_y_min (not prob_floor) because IsotonicRegression
        # clips output to [y_min, y_max] before our np.clip, so predictions
        # pile up at y_min rather than prob_floor.
        degenerate_threshold = max(prob_floor, isotonic_y_min) + 1e-6
        n_at_floor = int(np.sum(calibrated <= degenerate_threshold))
        n_total = len(calibrated)
        if n_total > 0 and n_at_floor / n_total > floor_warn_pct:
            base_rate = self._train_crash_rate.get(horizon)
            logger.warning(
                "Crash model %s: %.0f%% of predictions pinned at/below %.4f "
                "(isotonic_y_min=%.4f). Calibrator likely out-of-distribution.",
                horizon,
                n_at_floor / n_total * 100,
                degenerate_threshold,
                isotonic_y_min,
            )
            if use_base_rate_fallback and base_rate is not None:
                logger.warning(
                    "Falling back to training base rate %.2f%% for %s",
                    base_rate * 100,
                    horizon,
                )
                clipped = np.full_like(clipped, base_rate)

        return clipped

    def predict_all_horizons(self, features: pd.DataFrame) -> dict:
        """Predict crash probability at all trained horizons.

        Enforces monotonicity: P(crash, 3m) ≤ P(crash, 6m) ≤ P(crash, 12m).
        Longer horizons must have equal or higher crash probability.
        """
        raw = {
            horizon: self.predict_proba(features, horizon)
            for horizon in self.lgb_models
        }

        # Enforce monotonicity across horizons
        ordered = ["3m", "6m", "12m"]
        available = [h for h in ordered if h in raw]
        if len(available) >= 2:
            for i in range(1, len(available)):
                prev, curr = available[i - 1], available[i]
                # Longer horizon must be >= shorter horizon
                raw[curr] = np.maximum(raw[curr], raw[prev])

        return raw

    def diagnostics(self, features: pd.DataFrame) -> dict:
        """Run diagnostic checks on crash model predictions.

        Returns dict with per-horizon health info: whether predictions are
        degenerate, calibrator out-of-bounds stats, and base rate fallback status.
        Checks raw calibrator output (before fallback) to detect floor-pinning.
        """
        cal_cfg = config["ml"].get("calibration", {})
        prob_floor = cal_cfg.get("prob_floor", 0.001)
        isotonic_y_min = cal_cfg.get("isotonic_y_min", 0.01)
        floor_warn_pct = cal_cfg.get("floor_warn_pct", 0.50)
        fallback_enabled = cal_cfg.get("fallback_to_base_rate", True)
        degenerate_threshold = max(prob_floor, isotonic_y_min) + 1e-6

        result = {}
        for horizon in self.lgb_models:
            # Get raw calibrator output (bypass fallback) to detect floor-pinning
            raw_probs = self._raw_calibrated(features, horizon)
            clipped = np.clip(raw_probs, prob_floor, 1.0)
            n_at_floor = int(np.sum(clipped <= degenerate_threshold))
            n_total = len(clipped)
            floor_pct = n_at_floor / n_total if n_total > 0 else 0
            is_degenerate = floor_pct > floor_warn_pct

            base_rate = self._train_crash_rate.get(horizon)
            cal_range = self._calibrator_input_range.get(horizon)
            actually_falling_back = (
                is_degenerate and fallback_enabled and base_rate is not None
            )

            # Final predictions (with fallback applied)
            final_probs = self.predict_proba(features, horizon)

            result[horizon] = {
                "n_predictions": n_total,
                "n_at_floor": n_at_floor,
                "floor_pct": round(floor_pct * 100, 1),
                "degenerate": is_degenerate,
                "using_base_rate_fallback": actually_falling_back,
                "base_rate": round(base_rate * 100, 2) if base_rate else None,
                "calibrator_range": cal_range,
                "pred_mean": round(float(np.mean(final_probs)) * 100, 2),
                "pred_std": round(float(np.std(final_probs)) * 100, 4),
            }
        return result

    def _raw_calibrated(self, features: pd.DataFrame, horizon: str) -> np.ndarray:
        """Get raw calibrator output without floor/fallback logic."""
        blended, horizon = self._blend_scores(features, horizon)
        if horizon in self.calibrators:
            return self.calibrators[horizon].predict(blended)
        return blended

    def get_shap_values(
        self, features: pd.DataFrame, horizon: str = "3m"
    ) -> list[tuple[str, float]]:
        """Compute SHAP values for the LightGBM model.

        Returns list of (feature_name, shap_value) sorted by absolute importance.
        """
        try:
            import shap
        except ImportError:
            return []

        if horizon not in self.lgb_models:
            if not self.lgb_models:
                return []
            horizon = list(self.lgb_models.keys())[0]

        X = features[self.feature_names] if isinstance(features, pd.DataFrame) else features
        explainer = shap.TreeExplainer(self.lgb_models[horizon])
        shap_values = explainer.shap_values(X)

        if isinstance(shap_values, list):
            sv = shap_values[1]
        else:
            sv = shap_values

        row = sv[-1] if len(sv.shape) > 1 else sv
        contributions = list(zip(self.feature_names, row))
        return sorted(contributions, key=lambda x: abs(x[1]), reverse=True)

    def get_top_features(self, n: int = 15) -> list[tuple[str, float]]:
        """Return top N features by LightGBM importance (averaged across horizons)."""
        if not self.lgb_models:
            return []
        combined = np.zeros(len(self.feature_names))
        for model in self.lgb_models.values():
            imp = model.feature_importances_
            if imp.sum() > 0:
                combined += imp / imp.sum()
        importance = dict(zip(self.feature_names, combined))
        return sorted(importance.items(), key=lambda x: x[1], reverse=True)[:n]

    def save_model(self, path: str) -> None:
        """Serialize all models to disk."""
        if not _HAS_ML:
            raise RuntimeError("joblib not available")
        state = {
            "lgb_models": self.lgb_models,
            "lr_models": self.lr_models,
            "calibrators": self.calibrators,
            "scalers": self.scalers,
            "imputers": self.imputers,
            "feature_names": self.feature_names,
            "train_crash_rate": self._train_crash_rate,
            "calibrator_input_range": self._calibrator_input_range,
            "lgb_weight": self.lgb_weight,
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(state, path)
        logger.info("Model saved to %s", path)

    def load_model(self, path: str) -> None:
        """Load serialized models from disk."""
        if not _HAS_ML:
            raise RuntimeError("joblib not available")
        state = joblib.load(path)
        self.lgb_models = state["lgb_models"]
        self.lr_models = state.get("lr_models", {})
        self.calibrators = state["calibrators"]
        self.scalers = state.get("scalers", state.get("scaler", {}))
        self.imputers = state.get("imputers", {})
        self.feature_names = state["feature_names"]
        self._train_crash_rate = state.get("train_crash_rate", {})
        self._calibrator_input_range = state.get("calibrator_input_range", {})
        self.lgb_weight = state.get("lgb_weight", 0.70)
        self.is_trained = True

        # Patch LogisticRegression models for sklearn version compatibility.
        # Models trained with sklearn>=1.6 drop the `multi_class` attribute,
        # but sklearn<1.6 predict_proba requires it.
        for horizon, lr_model in self.lr_models.items():
            if isinstance(lr_model, LogisticRegression) and not hasattr(lr_model, "multi_class"):
                lr_model.multi_class = "auto"

        logger.info(
            "Model loaded from %s (horizons: %s)",
            path,
            list(self.lgb_models.keys()),
        )
