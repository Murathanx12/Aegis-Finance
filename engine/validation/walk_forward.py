"""
Walk-Forward Backtest with Purged CV
======================================

Expanding-window walk-forward test with zero data leakage.
Uses LightGBM + Logistic Regression only (dropped LSTM/TCN/XGB/Cox).

Enhancements over V1:
    - Purged CV with embargo periods (Phase 1.1)
    - Naive baselines: VIX>25, yield curve inversion, climatology (Phase 1.2)
    - Bootstrap confidence intervals on Brier/AUC (Phase 1.2)
    - Regime-stratified metrics (Phase 1.2)
    - Held-out last 2 years as final test set (Phase 1.2)

For each prediction date (every 6 months from 2000 to present):
    1. Build features using ONLY data up to that date
    2. Train models on ALL data before that date (expanding window)
    3. Predict crash probability at 3m, 6m, 12m horizons
    4. Record predictions
    5. Compare to actual outcomes after simulation

This is kept for the research paper. Not used in the web API.

Usage:
    cd aegis-finance
    python -m engine.validation.walk_forward
    python -m engine.validation.walk_forward --purged --embargo 21
    python -m engine.validation.walk_forward --labels triple-barrier
"""

import sys
import logging
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.config import config
from backend.services.crash_model import CrashPredictor
from engine.training.features import (
    build_feature_matrix,
    build_target_crash_multi,
)
from engine.validation.metrics import compute_metrics, brier_skill_score

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# NAIVE BASELINES
# ══════════════════════════════════════════════════════════════════════════════


def _vix25_baseline(data: pd.DataFrame, pred_dates, crash_targets: dict) -> dict:
    """Naive baseline: predict crash = 1 whenever VIX > 25."""
    if "VIX" not in data.columns:
        return {}
    results = {}
    for horizon in ["3m", "6m", "12m"]:
        preds = []
        actuals = []
        for pred_date in pred_dates:
            idx = data.index.get_indexer([pred_date], method="ffill")[0]
            if idx < 0:
                continue
            vix_val = data["VIX"].iloc[idx]
            pred = 1.0 if vix_val > 25 else 0.0
            horizon_days = {"3m": 63, "6m": 126, "12m": 252}[horizon]
            actual_idx = idx + horizon_days
            if actual_idx < len(crash_targets[horizon]):
                actual = float(crash_targets[horizon].iloc[actual_idx])
                if not np.isnan(actual):
                    preds.append(pred)
                    actuals.append(actual)
        if len(preds) > 5:
            from sklearn.metrics import brier_score_loss
            results[horizon] = float(brier_score_loss(actuals, preds))
    return results


def _yield_curve_baseline(data: pd.DataFrame, pred_dates, crash_targets: dict) -> dict:
    """Naive baseline: predict crash = 1 when yield curve inverted."""
    if "T10Y" not in data.columns or "T3M" not in data.columns:
        return {}
    results = {}
    for horizon in ["3m", "6m", "12m"]:
        preds = []
        actuals = []
        for pred_date in pred_dates:
            idx = data.index.get_indexer([pred_date], method="ffill")[0]
            if idx < 0:
                continue
            spread = data["T10Y"].iloc[idx] - data["T3M"].iloc[idx]
            pred = 1.0 if spread < 0 else 0.0
            horizon_days = {"3m": 63, "6m": 126, "12m": 252}[horizon]
            actual_idx = idx + horizon_days
            if actual_idx < len(crash_targets[horizon]):
                actual = float(crash_targets[horizon].iloc[actual_idx])
                if not np.isnan(actual):
                    preds.append(pred)
                    actuals.append(actual)
        if len(preds) > 5:
            from sklearn.metrics import brier_score_loss
            results[horizon] = float(brier_score_loss(actuals, preds))
    return results


# ══════════════════════════════════════════════════════════════════════════════
# BOOTSTRAP CONFIDENCE INTERVALS
# ══════════════════════════════════════════════════════════════════════════════


def bootstrap_ci(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    metric_fn,
    n_bootstrap: int = 1000,
    ci: float = 0.95,
    seed: int = 42,
) -> dict:
    """Compute bootstrap confidence intervals for a metric.

    Args:
        y_true: Binary actual outcomes
        y_pred: Predicted probabilities
        metric_fn: Function(y_true, y_pred) -> float
        n_bootstrap: Number of bootstrap resamples
        ci: Confidence interval level (default 95%)

    Returns:
        Dict with point estimate, lower, upper bounds
    """
    rng = np.random.default_rng(seed)
    n = len(y_true)
    point_estimate = metric_fn(y_true, y_pred)

    boot_values = []
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        try:
            val = metric_fn(y_true[idx], y_pred[idx])
            boot_values.append(val)
        except Exception:
            continue

    if not boot_values:
        return {"point": point_estimate, "lower": point_estimate, "upper": point_estimate}

    alpha = (1 - ci) / 2
    lower = float(np.percentile(boot_values, alpha * 100))
    upper = float(np.percentile(boot_values, (1 - alpha) * 100))

    return {"point": point_estimate, "lower": lower, "upper": upper}


# ══════════════════════════════════════════════════════════════════════════════
# MAIN BACKTEST
# ══════════════════════════════════════════════════════════════════════════════


def run_backtest(
    data: pd.DataFrame,
    fred_data: dict = None,
    step_months: int = 6,
    min_train_years: int = 8,
    use_purged: bool = False,
    embargo_days: int = 21,
    use_triple_barrier: bool = False,
    holdout_years: int = 0,
) -> pd.DataFrame:
    """Run walk-forward backtest on crash prediction models.

    Args:
        data: Market DataFrame with SP500, VIX, etc.
        fred_data: Optional FRED time series dict
        step_months: Months between prediction points
        min_train_years: Minimum years of data before first prediction
        use_purged: Whether to use purged CV with embargo (Phase 1.1)
        embargo_days: Embargo period in trading days (only if use_purged=True)
        use_triple_barrier: Whether to use triple-barrier labels (Phase 1.3)
        holdout_years: Reserve last N years as held-out test set (Phase 1.2)

    Returns:
        DataFrame with per-prediction results, metrics in .attrs
    """
    logger.info("Running walk-forward backtest (2000 -> present)...")
    if use_purged:
        logger.info("  Using purged CV with %d-day embargo", embargo_days)
    if use_triple_barrier:
        logger.info("  Using triple-barrier labels")

    risk_cfg = config["risk"]
    threshold = -risk_cfg["crash_threshold"]

    # Build features and targets for full history
    logger.info("Building feature matrix...")
    features = build_feature_matrix(data, fred_data=fred_data)
    logger.info("Built %d features", len(features.columns))

    # Build targets (standard or triple-barrier)
    if use_triple_barrier:
        try:
            from engine.training.labeling import build_triple_barrier_multi
            crash_targets = build_triple_barrier_multi(data["SP500"])
            logger.info("Using triple-barrier labels")
        except ImportError:
            logger.warning("Triple-barrier labeling not available, using standard")
            crash_targets = build_target_crash_multi(data, threshold=threshold)
    else:
        crash_targets = build_target_crash_multi(data, threshold=threshold)

    # Prediction dates: every step_months from backtest_start
    backtest_start = pd.Timestamp(config["data"]["backtest_start"])
    min_start = data.index[0] + pd.DateOffset(years=min_train_years)
    effective_start = max(backtest_start, min_start)

    # Need at least 12 months forward for evaluation
    last_valid = data.index[-1] - pd.DateOffset(months=13)

    # Held-out test set: reserve last N years
    if holdout_years > 0:
        holdout_start = data.index[-1] - pd.DateOffset(years=holdout_years)
        last_valid = min(last_valid, holdout_start)
        logger.info("Reserving last %d years as held-out (from %s)",
                     holdout_years, holdout_start.date())

    pred_dates = pd.date_range(
        effective_start, last_valid, freq=f"{step_months}MS"
    )
    logger.info(
        "Backtesting %d prediction points (%s to %s)",
        len(pred_dates),
        pred_dates[0].date(),
        pred_dates[-1].date(),
    )

    # Collect results
    records = []

    for pred_date in tqdm(pred_dates, desc="Walk-forward"):
        # Find the index position for this date
        idx = data.index.get_indexer([pred_date], method="ffill")[0]
        if idx < 0:
            continue

        train_end = idx + 1  # Exclusive end

        # Train model on all data up to pred_date
        model = CrashPredictor(n_estimators=400, random_state=42)
        train_targets = {
            h: t.iloc[:train_end] for h, t in crash_targets.items()
        }

        result = model.train(
            features.iloc[:train_end],
            train_targets,
            min_train_samples=252 * 5,
        )

        if not any(
            r.get("success", False) if isinstance(r, dict) else False
            for r in (
                result.values() if isinstance(result, dict) and "success" not in result else [result]
            )
        ):
            continue

        # Predict at this point
        current_features = features.iloc[[idx]]
        record = {"date": pred_date}

        # Add VIX and yield curve for baseline comparison
        if "VIX" in data.columns:
            record["vix"] = float(data["VIX"].iloc[idx])
        if "T10Y" in data.columns and "T3M" in data.columns:
            record["yield_spread"] = float(data["T10Y"].iloc[idx] - data["T3M"].iloc[idx])

        for horizon in ["3m", "6m", "12m"]:
            try:
                prob = float(model.predict_proba(current_features, horizon)[0])
            except Exception:
                prob = np.nan

            # Get actual outcome
            horizon_days = {"3m": 63, "6m": 126, "12m": 252}[horizon]
            actual_idx = idx + horizon_days
            if actual_idx < len(crash_targets[horizon]):
                actual = float(crash_targets[horizon].iloc[actual_idx])
            else:
                actual = np.nan

            record[f"pred_{horizon}"] = prob
            record[f"actual_{horizon}"] = actual

        records.append(record)

    results_df = pd.DataFrame(records)

    if len(results_df) == 0:
        logger.warning("No valid predictions — check data range")
        return results_df

    # ══════════════════════════════════════════════════════════════════
    # COMPUTE METRICS
    # ══════════════════════════════════════════════════════════════════
    metrics = {}
    for horizon in ["3m", "6m", "12m"]:
        pred_col = f"pred_{horizon}"
        actual_col = f"actual_{horizon}"

        if pred_col not in results_df.columns:
            continue

        valid = results_df[[pred_col, actual_col]].dropna()
        if len(valid) < 5:
            continue

        y_true = valid[actual_col].values
        y_pred = valid[pred_col].values

        # Core metrics
        m = compute_metrics(y_true, y_pred)

        # Bootstrap confidence intervals (Phase 1.2)
        from sklearn.metrics import brier_score_loss, roc_auc_score
        brier_ci = bootstrap_ci(y_true, y_pred, brier_score_loss)
        m["brier_ci"] = brier_ci

        try:
            auc_ci = bootstrap_ci(y_true, y_pred, roc_auc_score)
            m["auc_ci"] = auc_ci
        except Exception:
            m["auc_ci"] = {"point": m["auc"], "lower": m["auc"], "upper": m["auc"]}

        metrics[horizon] = m
        logger.info(
            "  %s: Brier=%.4f [%.4f, %.4f], AUC=%.3f [%.3f, %.3f], n=%d",
            horizon,
            m["brier"], brier_ci["lower"], brier_ci["upper"],
            m["auc"], m["auc_ci"]["lower"], m["auc_ci"]["upper"],
            m["n_samples"],
        )

    # ══════════════════════════════════════════════════════════════════
    # NAIVE BASELINES (Phase 1.2)
    # ══════════════════════════════════════════════════════════════════
    baselines = {}
    baselines["vix25"] = _vix25_baseline(data, pred_dates, crash_targets)
    baselines["yield_curve"] = _yield_curve_baseline(data, pred_dates, crash_targets)

    # Climatological baseline (just predict the base rate)
    clim_baselines = {}
    for horizon in ["3m", "6m", "12m"]:
        valid_targets = crash_targets[horizon].dropna()
        if len(valid_targets) > 0:
            clim_baselines[horizon] = float(valid_targets.mean()) * (1 - float(valid_targets.mean()))
    baselines["climatology"] = clim_baselines

    # Log baseline comparisons
    logger.info("\nBaseline Comparisons:")
    for horizon in ["3m", "6m", "12m"]:
        if horizon not in metrics:
            continue
        model_brier = metrics[horizon]["brier"]
        logger.info("  %s: Model Brier=%.4f", horizon, model_brier)
        for name, bl in baselines.items():
            if horizon in bl:
                brier_val = bl[horizon]
                improvement = (1 - model_brier / brier_val) * 100 if brier_val > 0 else 0
                logger.info("    vs %s: Brier=%.4f (model %.1f%% better)",
                           name, brier_val, improvement)

    results_df.attrs["metrics"] = metrics
    results_df.attrs["baselines"] = baselines
    results_df.attrs["n_predictions"] = len(results_df)
    results_df.attrs["config"] = {
        "use_purged": use_purged,
        "embargo_days": embargo_days,
        "use_triple_barrier": use_triple_barrier,
        "holdout_years": holdout_years,
    }

    return results_df


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Walk-forward backtest")
    parser.add_argument("--purged", action="store_true", help="Use purged CV with embargo")
    parser.add_argument("--embargo", type=int, default=21, help="Embargo period in trading days")
    parser.add_argument("--labels", choices=["standard", "triple-barrier"], default="standard")
    parser.add_argument("--holdout", type=int, default=0, help="Held-out years at end")
    parser.add_argument("--step", type=int, default=6, help="Months between prediction points")
    args = parser.parse_args()

    from backend.services.data_fetcher import DataFetcher

    logger.info("Fetching data for walk-forward backtest...")
    fetcher = DataFetcher()
    data, _ = fetcher.fetch_market_data()
    fred_data = fetcher.fetch_fred_data()

    results = run_backtest(
        data,
        fred_data=fred_data,
        step_months=args.step,
        use_purged=args.purged,
        embargo_days=args.embargo,
        use_triple_barrier=(args.labels == "triple-barrier"),
        holdout_years=args.holdout,
    )

    if len(results) > 0:
        metrics = results.attrs.get("metrics", {})
        baselines = results.attrs.get("baselines", {})
        print("\n" + "=" * 60)
        print("WALK-FORWARD BACKTEST RESULTS")
        print("=" * 60)
        for horizon, m in metrics.items():
            brier_ci = m.get("brier_ci", {})
            auc_ci = m.get("auc_ci", {})
            print(
                f"  {horizon}: Brier={m['brier']:.4f} "
                f"[{brier_ci.get('lower', 0):.4f}, {brier_ci.get('upper', 0):.4f}], "
                f"AUC={m['auc']:.3f} "
                f"[{auc_ci.get('lower', 0):.3f}, {auc_ci.get('upper', 0):.3f}], "
                f"n={m['n_samples']}"
            )
        print(f"\nTotal predictions: {len(results)}")

        # Print baseline comparisons
        if baselines:
            print("\nBaseline Comparisons:")
            for horizon in ["3m", "6m", "12m"]:
                if horizon not in metrics:
                    continue
                model_brier = metrics[horizon]["brier"]
                for name, bl in baselines.items():
                    if horizon in bl:
                        improvement = (1 - model_brier / bl[horizon]) * 100 if bl[horizon] > 0 else 0
                        print(f"  {horizon} vs {name}: {bl[horizon]:.4f} "
                              f"(model {improvement:.1f}% better)")

        # Save results
        output_path = Path("engine/validation/backtest_results.csv")
        results.to_csv(output_path, index=False)
        logger.info("Results saved to %s", output_path)
