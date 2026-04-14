"""
Aegis Finance — Cox Proportional Hazards Crash Model
======================================================

Models crash timing as a survival analysis problem: for each date,
how many days until the next >=20% drawdown?

Advantages over standard classification:
  - Naturally handles censored observations (no crash within horizon)
  - Produces time-varying hazard rates (3m, 6m, 12m from single model)
  - Semi-parametric: learns feature effects without assuming hazard distribution
  - Regularized (penalizer=0.1) for sparse crash events

Ported from market-prediction-engine with Aegis config integration.

Usage:
    from backend.services.survival_model import CrashSurvivalModel
"""

import logging

import numpy as np
import pandas as pd

from backend.config import config

logger = logging.getLogger(__name__)

HORIZON_DAYS = {"3m": 63, "6m": 126, "12m": 252}

# Features proven effective for crash prediction (domain-motivated, low-correlation)
COX_FEATURES = [
    "vix_zscore",
    "term_spread",
    "credit_spread_proxy",
    "mom_12m",
    "vol_ratio_1m_12m",
    "mom_6m",
    "sma_200d_dev",
    "dist_52w_high",
    "vol_1m",
]

try:
    from lifelines import CoxPHFitter
    from sklearn.preprocessing import StandardScaler
    _HAS_LIFELINES = True
except ImportError:
    _HAS_LIFELINES = False


def _build_survival_targets(
    data: pd.DataFrame,
    max_horizon: int = 252,
    threshold: float = -0.20,
) -> pd.DataFrame:
    """Build survival analysis targets from price data.

    For each date t, look forward up to max_horizon days.
    Find the first day where drawdown from t exceeds threshold.

    Returns DataFrame with columns 'duration' and 'event'.
    """
    prices = data["SP500"].values.astype(float)
    n = len(prices)
    durations = np.full(n, max_horizon, dtype=float)
    events = np.zeros(n, dtype=float)

    for i in range(n - 1):
        end = min(n, i + max_horizon + 1)
        window = prices[i:end]
        if len(window) <= 1:
            continue
        peak = np.maximum.accumulate(window)
        mask = peak > 0
        if not mask.any():
            continue
        dd = np.where(mask, (window - peak) / peak, 0.0)
        crash_indices = np.where(dd <= threshold)[0]
        if len(crash_indices) > 0:
            first_crash = crash_indices[0]
            if first_crash > 0:
                durations[i] = float(first_crash)
                events[i] = 1.0

    return pd.DataFrame({"duration": durations, "event": events}, index=data.index)


class CrashSurvivalModel:
    """Cox PH crash prediction model.

    Produces crash probabilities at multiple horizons from a single
    fitted model: P(crash within t) = 1 - S(t).
    """

    def __init__(self, penalizer: float = 0.1):
        self.penalizer = penalizer
        self.is_trained = False
        self._model = None
        self._scaler = None
        self._fill_values = None
        self._available_features: list[str] = []
        self._base_rate = config.get("ml", {}).get("crash_base_rate_fallback", 0.12)

    def train(
        self,
        features: pd.DataFrame,
        data: pd.DataFrame,
        train_end_idx: int,
        min_train_samples: int = 1260,
    ) -> dict:
        """Train the Cox PH model."""
        if not _HAS_LIFELINES:
            logger.warning("[COX] lifelines not installed — using fallback")
            return {"success": False, "reason": "lifelines not installed"}

        if data is None or "SP500" not in data.columns:
            return {"success": False, "reason": "data with SP500 column required"}

        if train_end_idx < min_train_samples:
            return {"success": False, "reason": f"Need {min_train_samples} samples, have {train_end_idx}"}

        # Build survival targets
        crash_thresh = -config.get("risk", {}).get("crash_threshold", 0.20)
        target_data_end = min(train_end_idx + 252, len(data))
        surv = _build_survival_targets(data.iloc[:target_data_end], max_horizon=252, threshold=crash_thresh)

        # Select available features
        self._available_features = [f for f in COX_FEATURES if f in features.columns]
        if len(self._available_features) < 3:
            return {"success": False, "reason": f"Only {len(self._available_features)} features available"}

        # Purge gap to prevent label leakage
        purge_gap = config.get("ml", {}).get("purge_gaps", {}).get("12m", 265)
        train_end = train_end_idx - 252
        if train_end < min_train_samples:
            train_end = int(train_end_idx * 0.7)

        X_train = features[self._available_features].iloc[:train_end]
        surv_train = surv.iloc[:train_end]

        # Clean data
        valid = ~(X_train.isna().any(axis=1) | surv_train.isna().any(axis=1))
        valid = valid & (surv_train["duration"] > 0)
        X_train = X_train[valid]
        surv_train = surv_train[valid]

        if len(X_train) < 100 or surv_train["event"].sum() < 3:
            return {"success": False, "reason": f"Insufficient: {len(X_train)} rows, {surv_train['event'].sum():.0f} events"}

        self._fill_values = X_train.median()
        self._scaler = StandardScaler()
        X_scaled = pd.DataFrame(
            self._scaler.fit_transform(X_train),
            columns=self._available_features,
            index=X_train.index,
        )

        train_df = pd.concat([X_scaled, surv_train], axis=1)

        try:
            self._model = CoxPHFitter(penalizer=self.penalizer)
            self._model.fit(train_df, duration_col="duration", event_col="event", show_progress=False)
        except Exception as e:
            logger.warning("[COX] fit failed: %s", e)
            return {"success": False, "reason": str(e)}

        self.is_trained = True
        return {
            "success": True,
            "n_train": len(X_train),
            "n_events": int(surv_train["event"].sum()),
        }

    def predict_proba(self, features: pd.DataFrame, horizon: str = "12m") -> np.ndarray:
        """Predict crash probability at the given horizon."""
        if not self.is_trained:
            return np.full(len(features), self._base_rate)

        horizon_days = HORIZON_DAYS.get(horizon, 252)
        X = features.reindex(columns=self._available_features).fillna(self._fill_values)
        X_scaled = pd.DataFrame(
            self._scaler.transform(X),
            columns=self._available_features,
            index=X.index,
        )

        try:
            surv_func = self._model.predict_survival_function(X_scaled)
            times = surv_func.index.values.astype(float)
            if horizon_days <= times[0]:
                s_t = surv_func.iloc[0].values
            elif horizon_days >= times[-1]:
                s_t = surv_func.iloc[-1].values
            else:
                right = np.searchsorted(times, horizon_days)
                left = right - 1
                t_lo, t_hi = times[left], times[right]
                frac = (horizon_days - t_lo) / (t_hi - t_lo) if t_hi != t_lo else 0.0
                s_t = surv_func.iloc[left].values * (1 - frac) + surv_func.iloc[right].values * frac
            return np.clip(1.0 - s_t, 0.02, 0.98)
        except Exception:
            return np.full(len(X), self._base_rate)

    def get_top_features(self, n: int = 5) -> list[tuple]:
        """Return top features by absolute Cox coefficient magnitude."""
        if not self.is_trained or self._model is None:
            return []
        coefs = self._model.params_
        sorted_feats = coefs.abs().sort_values(ascending=False)
        return [(name, float(coefs[name])) for name in sorted_feats.index[:n]]
