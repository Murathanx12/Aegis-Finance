"""
Aegis Finance — Quantile Return Predictor
===========================================

Multi-horizon return predictor using LightGBM quantile regression.
Outputs 10th/50th/90th percentile return distributions.

Adapted from V7 ml/return_model.py.

Usage:
    from backend.services.return_model import ReturnPredictor

    predictor = ReturnPredictor()
    result = predictor.train(features, targets)
    quantiles = predictor.predict_quantiles(latest_features)
"""

import numpy as np
import pandas as pd
from typing import Optional

from backend.config import config as _cfg

try:
    import lightgbm as lgb
    _HAS_LIGHTGBM = True
except ImportError:
    _HAS_LIGHTGBM = False


if _HAS_LIGHTGBM:

    class ReturnPredictor:
        """Multi-horizon return predictor with quantile regression.

        For each horizon, trains three models:
        - Median (50th percentile) — point estimate
        - Lower (10th percentile) — downside bound
        - Upper (90th percentile) — upside bound
        """

        def __init__(self, n_estimators: int = 600, random_state: int = 42):
            self.n_estimators = n_estimators
            self.random_state = random_state
            self.models = {}
            self.quantile_models = {}
            self.feature_names = None
            self.feature_importances_ = None
            self.is_trained = False
            self.train_stats = {}
            self._naive_mae = {}

        def train(
            self,
            features: pd.DataFrame,
            targets: dict | pd.Series,
            train_end_idx: Optional[int] = None,
            min_train_samples: int = 1260,
        ) -> dict:
            if isinstance(targets, pd.Series):
                targets = {"12m": targets}

            if train_end_idx is not None:
                X = features.iloc[:train_end_idx].copy()
                target_slices = {h: t.iloc[:train_end_idx].copy() for h, t in targets.items()}
            else:
                X = features.copy()
                target_slices = {h: t.copy() for h, t in targets.items()}

            primary_target = target_slices.get("12m", list(target_slices.values())[0])
            valid = primary_target.notna() & X.notna().any(axis=1)
            X_clean = X[valid]
            if len(X_clean) < min_train_samples:
                return {"success": False, "reason": f"Only {len(X_clean)} samples"}

            self.feature_names = list(X_clean.columns)

            results = {}
            combined_importances = np.zeros(len(self.feature_names))

            for horizon, target in target_slices.items():
                y = target.iloc[:train_end_idx] if train_end_idx is not None else target.copy()
                valid_h = y.notna() & X.notna().any(axis=1)
                X_h = X[valid_h]
                y_h = y[valid_h]

                if len(X_h) < min_train_samples:
                    continue

                self.train_stats[horizon] = {
                    "mean": float(y_h.mean()),
                    "std": float(y_h.std()),
                    "min": float(y_h.min()),
                    "max": float(y_h.max()),
                    "p10": float(y_h.quantile(0.10)),
                    "p90": float(y_h.quantile(0.90)),
                }

                r = self._train_single(X_h, y_h, horizon)
                results[horizon] = r

                if r["success"] and horizon in self.models:
                    imp = self.models[horizon].feature_importances_
                    if imp.sum() > 0:
                        combined_importances += imp / imp.sum()

            if not self.models:
                return {"success": False, "reason": "No horizon trained successfully"}

            self.feature_importances_ = dict(zip(self.feature_names, combined_importances))
            self.is_trained = True

            return results.get("12m", list(results.values())[0])

        def _train_single(self, X: pd.DataFrame, y: pd.Series, horizon: str) -> dict:
            n_samples = len(X)

            decay = _cfg.get("ml", {}).get("temporal_weight_decay", 0.0005)
            temporal_weights = np.exp(-decay * (n_samples - np.arange(n_samples)))

            purge_cfg = _cfg.get("ml", {}).get("purge_gaps", {"3m": 70, "6m": 140, "12m": 265})
            gap_days = purge_cfg.get(horizon, purge_cfg.get("12m", 265))
            val_size = max(504, n_samples // 5)
            split_idx = n_samples - val_size - gap_days

            if split_idx < min(1260, n_samples // 2):
                split_idx = int(n_samples * 0.8)
                gap_days = 0

            train_X = X.iloc[:split_idx]
            train_y = y.iloc[:split_idx]
            train_w = temporal_weights[:split_idx]
            val_X = X.iloc[split_idx + gap_days:]
            val_y = y.iloc[split_idx + gap_days:]

            if len(val_y) < 50:
                split_idx = int(n_samples * 0.8)
                train_X = X.iloc[:split_idx]
                train_y = y.iloc[:split_idx]
                train_w = temporal_weights[:split_idx]
                val_X = X.iloc[split_idx:]
                val_y = y.iloc[split_idx:]

            base_params = {
                "n_estimators": self.n_estimators,
                "max_depth": 6,
                "num_leaves": 30,
                "learning_rate": 0.008,
                "min_child_samples": 40,
                "subsample": 0.75,
                "colsample_bytree": 0.60,
                "reg_alpha": 0.1,
                "reg_lambda": 1.0,
                "min_gain_to_split": 0.003,
                "random_state": self.random_state,
                "verbose": -1,
                "n_jobs": -1,
            }

            median_params = {**base_params, "objective": "regression", "metric": "mae"}
            model = lgb.LGBMRegressor(**median_params)
            model.fit(
                train_X, train_y,
                sample_weight=train_w,
                eval_set=[(val_X, val_y)],
                callbacks=[
                    lgb.early_stopping(stopping_rounds=80, verbose=False),
                    lgb.log_evaluation(period=0),
                ],
            )
            self.models[horizon] = model

            for alpha in [0.10, 0.90]:
                q_params = {**base_params,
                            "objective": "quantile",
                            "alpha": alpha,
                            "metric": "quantile"}
                q_model = lgb.LGBMRegressor(**q_params)
                q_model.fit(
                    train_X, train_y,
                    sample_weight=train_w,
                    eval_set=[(val_X, val_y)],
                    callbacks=[
                        lgb.early_stopping(stopping_rounds=80, verbose=False),
                        lgb.log_evaluation(period=0),
                    ],
                )
                self.quantile_models[(horizon, alpha)] = q_model

            val_pred = model.predict(val_X)
            val_mae = float(np.abs(val_y.values - val_pred).mean())

            val_corr = 0.0
            if len(val_y) > 5:
                c = np.corrcoef(val_y.values, val_pred)[0, 1]
                val_corr = float(c if not np.isnan(c) else 0)

            naive_pred = train_y.mean()
            naive_mae = float(np.abs(val_y.values - naive_pred).mean())
            skill = 1 - val_mae / naive_mae if naive_mae > 0 else 0
            self._naive_mae[horizon] = naive_mae

            coverage = 0.0
            if (horizon, 0.10) in self.quantile_models and (horizon, 0.90) in self.quantile_models:
                p10 = self.quantile_models[(horizon, 0.10)].predict(val_X)
                p90 = self.quantile_models[(horizon, 0.90)].predict(val_X)
                coverage = float(((val_y.values >= p10) & (val_y.values <= p90)).mean())

            return {
                "success": True,
                "horizon": horizon,
                "n_train": len(train_X),
                "n_val": len(val_X),
                "val_mae": val_mae,
                "val_corr": val_corr,
                "naive_mae": naive_mae,
                "skill_score": float(skill),
                "quantile_coverage": coverage,
            }

        def predict(self, features: pd.DataFrame, horizon: str = "12m") -> np.ndarray:
            if not self.is_trained:
                raise RuntimeError("Model not trained")
            if horizon not in self.models:
                horizon = list(self.models.keys())[0]

            X = features[self.feature_names] if isinstance(features, pd.DataFrame) else features
            preds = self.models[horizon].predict(X)

            stats = self.train_stats.get(horizon, {"min": -0.60, "max": 1.50})
            lo = max(stats.get("min", -0.60) * 1.2, -0.80)
            hi = min(stats.get("max", 1.50) * 1.2, 2.00)
            return np.clip(preds, lo, hi)

        def predict_quantiles(self, features: pd.DataFrame, horizon: str = "12m") -> dict:
            if not self.is_trained:
                raise RuntimeError("Model not trained")
            if horizon not in self.models:
                horizon = list(self.models.keys())[0]

            X = features[self.feature_names] if isinstance(features, pd.DataFrame) else features
            result = {"median": self.models[horizon].predict(X)}

            for alpha in [0.10, 0.90]:
                key = "p10" if alpha == 0.10 else "p90"
                if (horizon, alpha) in self.quantile_models:
                    result[key] = self.quantile_models[(horizon, alpha)].predict(X)
                else:
                    stats = self.train_stats.get(horizon, {"std": 0.15})
                    z = -1.28 if alpha == 0.10 else 1.28
                    result[key] = result["median"] + z * stats["std"]

            return result

        def get_top_features(self, n: int = 15) -> list:
            if self.feature_importances_ is None:
                return []
            return sorted(
                self.feature_importances_.items(),
                key=lambda x: x[1], reverse=True,
            )[:n]

else:

    class ReturnPredictor:
        """Fallback when LightGBM is not installed."""

        def __init__(self, n_estimators: int = 100, random_state: int = 42):
            self.is_trained = False
            self.feature_names = None
            self.feature_importances_ = None

        def train(self, features, targets, **kwargs):
            self.is_trained = True
            self.feature_names = list(features.columns) if hasattr(features, "columns") else None
            return {"success": True, "val_mae": 0.0, "skill_score": 0.0}

        def predict(self, features, horizon="12m"):
            return np.zeros(len(features))

        def predict_quantiles(self, features, horizon="12m"):
            n = len(features)
            return {"median": np.zeros(n), "p10": np.full(n, -0.10), "p90": np.full(n, 0.10)}

        def get_top_features(self, n=15):
            return []
