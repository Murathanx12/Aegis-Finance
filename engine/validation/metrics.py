"""
Evaluation Metrics for Crash Prediction
=========================================

Brier score, Brier Skill Score, AUC, calibration analysis,
conformal prediction, lead-time accuracy, false alarm rate.
Used by walk-forward backtest and research paper.

Includes advanced metrics from V7 evaluation/metrics.py.

Usage:
    from engine.validation.metrics import compute_metrics, brier_skill_score
    from engine.validation.metrics import ConformalPredictor, lead_time_accuracy
"""

import numpy as np
import pandas as pd
from typing import Optional
from sklearn.metrics import brier_score_loss, roc_auc_score


def compute_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    base_rate: float = None,
) -> dict:
    """Compute all crash prediction metrics.

    Args:
        y_true: Binary actual outcomes (0/1)
        y_pred: Predicted probabilities [0, 1]
        base_rate: Climatological base rate (for BSS). If None, uses y_true.mean()

    Returns:
        Dict with brier, bss, auc, calibration metrics
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    mask = ~(np.isnan(y_true) | np.isnan(y_pred))
    y_true = y_true[mask]
    y_pred = y_pred[mask]

    if len(y_true) < 5:
        return {"error": "Too few samples"}

    # Brier score (lower is better, 0 = perfect)
    brier = float(brier_score_loss(y_true, y_pred))

    # Brier Skill Score (positive = better than climatology)
    if base_rate is None:
        base_rate = float(y_true.mean())
    brier_clim = base_rate * (1 - base_rate)
    bss = 1 - brier / brier_clim if brier_clim > 0 else 0.0

    # AUC (0.5 = random, 1.0 = perfect)
    try:
        auc = float(roc_auc_score(y_true, y_pred))
    except ValueError:
        auc = 0.5

    # Prediction spread
    spread = prediction_spread_check(y_pred)

    # Calibration: split into bins and check predicted vs observed
    cal = _calibration_curve(y_true, y_pred, n_bins=5)

    return {
        "brier": brier,
        "bss": float(bss),
        "auc": auc,
        "base_rate": float(base_rate),
        "n_samples": len(y_true),
        "n_positive": int(y_true.sum()),
        "pred_std": spread["std"],
        "pred_range": (spread["min"], spread["max"]),
        "is_underdispersed": spread["is_underdispersed"],
        "calibration": cal,
    }


def brier_skill_score(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    base_rate: float = None,
    baseline: str = "climatology",
    vix_series: Optional[pd.Series] = None,
    spread_series: Optional[pd.Series] = None,
) -> float:
    """Compute Brier Skill Score relative to a baseline.

    BSS = 1 - (BS_model / BS_baseline)
    Positive BSS means the model beats the baseline.

    Args:
        baseline: One of "climatology", "vix25", "yield_curve".
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    bs_model = float(brier_score_loss(y_true, y_pred))

    if baseline == "climatology":
        if base_rate is None:
            base_rate = float(y_true.mean())
        brier_clim = base_rate * (1 - base_rate)
        if brier_clim == 0:
            return 0.0
        return float(1 - bs_model / brier_clim)
    elif baseline == "vix25":
        if vix_series is None:
            raise ValueError("vix_series required for 'vix25' baseline")
        vix_arr = np.asarray(vix_series, dtype=float)
        baseline_pred = (vix_arr > 25).astype(float)
        bs_baseline = float(np.mean((baseline_pred - y_true) ** 2))
    elif baseline == "yield_curve":
        if spread_series is None:
            raise ValueError("spread_series required for 'yield_curve' baseline")
        spread_arr = np.asarray(spread_series, dtype=float)
        baseline_pred = (spread_arr < 0).astype(float)
        bs_baseline = float(np.mean((baseline_pred - y_true) ** 2))
    else:
        raise ValueError(f"Unknown baseline: {baseline}")

    if bs_baseline == 0:
        return 0.0
    return float(1.0 - bs_model / bs_baseline)


def reliability_diagram(
    y_pred: np.ndarray,
    y_true: np.ndarray,
    n_bins: int = 10,
) -> dict:
    """Compute reliability diagram data and Expected Calibration Error (ECE)."""
    y_pred = np.asarray(y_pred, dtype=float)
    y_true = np.asarray(y_true, dtype=float)

    bin_edges = np.linspace(0, 1, n_bins + 1)
    bin_centers = np.zeros(n_bins)
    bin_frequencies = np.zeros(n_bins)
    bin_counts = np.zeros(n_bins, dtype=int)

    total = len(y_pred)
    ece = 0.0

    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        if i == n_bins - 1:
            mask = (y_pred >= lo) & (y_pred <= hi)
        else:
            mask = (y_pred >= lo) & (y_pred < hi)

        count = mask.sum()
        bin_counts[i] = count
        bin_centers[i] = (lo + hi) / 2

        if count > 0:
            bin_frequencies[i] = y_true[mask].mean()
            ece += abs(bin_frequencies[i] - bin_centers[i]) * count / total

    return {
        "bin_centers": bin_centers.tolist(),
        "bin_frequencies": bin_frequencies.tolist(),
        "bin_counts": bin_counts.tolist(),
        "calibration_error": float(ece),
    }


def prediction_spread_check(y_pred: np.ndarray) -> dict:
    """Check prediction spread for underdispersion.

    Underdispersed predictions (std < 5%) indicate the model has collapsed
    to predicting near the base rate for everything.
    """
    y_pred = np.asarray(y_pred, dtype=float)
    std = float(y_pred.std()) if len(y_pred) > 0 else 0.0
    return {
        "mean": float(y_pred.mean()) if len(y_pred) > 0 else 0.0,
        "std": std,
        "min": float(y_pred.min()) if len(y_pred) > 0 else 0.0,
        "max": float(y_pred.max()) if len(y_pred) > 0 else 0.0,
        "is_underdispersed": std < 0.05,
    }


# ═════════════════════════════════════════════════════════════════════
# ADVANCED VALIDATION METRICS (from V7)
# ═════════════════════════════════════════════════════════════════════


def lead_time_accuracy(
    bt: pd.DataFrame,
    crash_periods: pd.DataFrame,
    prob_col: str = "ml_crash_12m",
    prob_threshold: float = 0.40,
) -> dict:
    """Measure how many days before each crash the model raised an alert.

    Target: > 30 days average lead time.
    """
    if bt.empty or crash_periods.empty or prob_col not in bt.columns:
        return {"mean_lead_days": 0, "median_lead_days": 0, "per_crash": [],
                "n_crashes": 0, "n_detected": 0}

    bt_sorted = bt.sort_values("date").copy()
    lead_times = []
    per_crash = []

    for _, crash in crash_periods.iterrows():
        crash_start = pd.Timestamp(crash["start"])
        lookback_start = crash_start - pd.Timedelta(days=365)

        mask = (bt_sorted["date"] >= lookback_start) & (bt_sorted["date"] < crash_start)
        window = bt_sorted[mask]

        if window.empty:
            per_crash.append({"crash_start": str(crash_start.date()),
                              "detected": False, "lead_days": 0})
            continue

        alerts = window[window[prob_col] >= prob_threshold]
        if not alerts.empty:
            first_alert = alerts["date"].iloc[0]
            lead_days = (crash_start - pd.Timestamp(first_alert)).days
            lead_times.append(lead_days)
            per_crash.append({
                "crash_start": str(crash_start.date()),
                "detected": True,
                "lead_days": lead_days,
                "first_alert_prob": float(alerts[prob_col].iloc[0]),
            })
        else:
            per_crash.append({"crash_start": str(crash_start.date()),
                              "detected": False, "lead_days": 0})

    return {
        "mean_lead_days": float(np.mean(lead_times)) if lead_times else 0,
        "median_lead_days": float(np.median(lead_times)) if lead_times else 0,
        "per_crash": per_crash,
        "n_crashes": len(crash_periods),
        "n_detected": len(lead_times),
    }


def false_alarm_rate(
    bt: pd.DataFrame,
    prob_col: str = "ml_crash_12m",
    actual_col: str = "actual_crash_12m",
    alarm_threshold: float = 0.60,
    horizon_days: int = 63,
) -> dict:
    """Fraction of high-probability alerts where no crash occurred.

    Target: < 30%.
    """
    if bt.empty or prob_col not in bt.columns:
        return {"rate": 0.0, "n_alarms": 0, "n_false_alarms": 0}

    bt_sorted = bt.sort_values("date").copy()
    alarms = bt_sorted[bt_sorted[prob_col] >= alarm_threshold]

    if alarms.empty:
        return {"rate": 0.0, "n_alarms": 0, "n_false_alarms": 0}

    episodes = []
    prev_date = None
    for _, row in alarms.iterrows():
        dt = pd.Timestamp(row["date"])
        if prev_date is None or (dt - prev_date).days > horizon_days:
            episodes.append(dt)
        prev_date = dt

    n_false = 0
    for ep_start in episodes:
        ep_end = ep_start + pd.Timedelta(days=horizon_days)
        future = bt_sorted[
            (bt_sorted["date"] >= ep_start) & (bt_sorted["date"] <= ep_end)
        ]
        if future.empty or not future[actual_col].any():
            n_false += 1

    n_episodes = len(episodes)
    rate = n_false / n_episodes if n_episodes > 0 else 0.0

    return {"rate": float(rate), "n_alarms": n_episodes, "n_false_alarms": n_false}


def missed_crash_rate(
    bt: pd.DataFrame,
    crash_periods: pd.DataFrame,
    prob_col: str = "ml_crash_12m",
    safe_threshold: float = 0.30,
    lead_days: int = 21,
) -> dict:
    """Fraction of crashes where model said 'safe' beforehand.

    Target: < 20%.
    """
    if bt.empty or crash_periods.empty or prob_col not in bt.columns:
        return {"rate": 0.0, "n_crashes": 0, "n_missed": 0}

    bt_sorted = bt.sort_values("date").copy()
    n_missed = 0
    n_evaluated = 0

    for _, crash in crash_periods.iterrows():
        crash_start = pd.Timestamp(crash["start"])
        check_date = crash_start - pd.Timedelta(days=lead_days)

        before = bt_sorted[bt_sorted["date"] <= check_date]
        if before.empty:
            continue

        prob = float(before.iloc[-1][prob_col])
        n_evaluated += 1
        if prob < safe_threshold:
            n_missed += 1

    rate = n_missed / n_evaluated if n_evaluated > 0 else 0.0
    return {"rate": float(rate), "n_crashes": n_evaluated, "n_missed": n_missed}


def regime_conditional_bss(
    y_pred: np.ndarray,
    y_true: np.ndarray,
    regimes: np.ndarray,
) -> dict:
    """Compute BSS stratified by regime label."""
    y_pred = np.asarray(y_pred, dtype=float)
    y_true = np.asarray(y_true, dtype=float)
    regimes = np.asarray(regimes)

    result = {"overall_bss": brier_skill_score(y_pred, y_true)}

    for regime in np.unique(regimes):
        mask = regimes == regime
        n = int(mask.sum())
        if n < 10 or len(np.unique(y_true[mask])) < 2:
            result[f"bss_{regime}"] = float("nan")
            result[f"n_{regime}"] = n
            continue
        result[f"bss_{regime}"] = brier_skill_score(y_pred[mask], y_true[mask])
        result[f"n_{regime}"] = n

    return result


class ConformalPredictor:
    """Split conformal prediction for coverage-guaranteed crash intervals.

    Given calibration residuals, produces prediction intervals with
    finite-sample coverage guarantees (Vovk et al., 2005).

    Usage:
        cp = ConformalPredictor(target_coverage=0.90)
        cp.calibrate(cal_predictions, cal_true_labels)
        interval = cp.predict_interval(new_prediction)
    """

    def __init__(self, target_coverage: float = 0.90):
        self.target_coverage = target_coverage
        self._quantile = None
        self._calibrated = False

    def calibrate(self, cal_pred: np.ndarray, cal_true: np.ndarray) -> None:
        cal_pred = np.asarray(cal_pred, dtype=float)
        cal_true = np.asarray(cal_true, dtype=float)
        n = len(cal_pred)
        if n < 10:
            self._quantile = 0.5
            self._calibrated = True
            return

        scores = np.abs(cal_pred - cal_true)
        q_level = np.ceil((n + 1) * self.target_coverage) / n
        q_level = min(q_level, 1.0)
        self._quantile = float(np.quantile(scores, q_level))
        self._calibrated = True

    def predict_interval(self, point_pred: float) -> dict:
        if not self._calibrated:
            raise RuntimeError("Must call calibrate() before predict_interval()")

        lower = max(0.0, point_pred - self._quantile)
        upper = min(1.0, point_pred + self._quantile)

        return {
            "lower": float(lower),
            "upper": float(upper),
            "point": float(point_pred),
            "coverage": self.target_coverage,
        }

    def predict_intervals_batch(self, predictions: np.ndarray) -> list:
        return [self.predict_interval(float(p)) for p in np.asarray(predictions)]


def _calibration_curve(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    n_bins: int = 5,
) -> list[dict]:
    """Compute calibration curve (reliability diagram data)."""
    bins = np.linspace(0, 1, n_bins + 1)
    result = []

    for i in range(n_bins):
        mask = (y_pred >= bins[i]) & (y_pred < bins[i + 1])
        if i == n_bins - 1:
            mask = (y_pred >= bins[i]) & (y_pred <= bins[i + 1])

        count = int(mask.sum())
        if count == 0:
            continue

        result.append(
            {
                "bin": f"{bins[i]:.2f}-{bins[i+1]:.2f}",
                "predicted_mean": float(y_pred[mask].mean()),
                "observed_mean": float(y_true[mask].mean()),
                "count": count,
            }
        )

    return result
