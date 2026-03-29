"""
Walk-Forward Backtest (Simplified — 2 Models)
================================================

Expanding-window walk-forward test with zero data leakage.
Uses LightGBM + Logistic Regression only (dropped LSTM/TCN/XGB/Cox).

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
"""

import sys
import logging
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
from engine.validation.metrics import compute_metrics

logger = logging.getLogger(__name__)


def run_backtest(
    data: pd.DataFrame,
    fred_data: dict = None,
    step_months: int = 6,
    min_train_years: int = 8,
) -> pd.DataFrame:
    """Run walk-forward backtest on crash prediction models.

    Args:
        data: Market DataFrame with SP500, VIX, etc.
        fred_data: Optional FRED time series dict
        step_months: Months between prediction points
        min_train_years: Minimum years of data before first prediction

    Returns:
        DataFrame with per-prediction results, metrics in .attrs
    """
    logger.info("Running walk-forward backtest (2000 -> present)...")

    risk_cfg = config["risk"]
    threshold = -risk_cfg["crash_threshold"]

    # Build features and targets for full history
    logger.info("Building feature matrix...")
    features = build_feature_matrix(data, fred_data=fred_data)
    logger.info("Built %d features", len(features.columns))

    crash_targets = build_target_crash_multi(data, threshold=threshold)

    # Prediction dates: every step_months from backtest_start
    backtest_start = pd.Timestamp(config["data"]["backtest_start"])
    min_start = data.index[0] + pd.DateOffset(years=min_train_years)
    effective_start = max(backtest_start, min_start)

    # Need at least 12 months forward for evaluation
    last_valid = data.index[-1] - pd.DateOffset(months=13)

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

    # Compute aggregate metrics
    metrics = {}
    for horizon in ["3m", "6m", "12m"]:
        pred_col = f"pred_{horizon}"
        actual_col = f"actual_{horizon}"

        if pred_col not in results_df.columns:
            continue

        valid = results_df[[pred_col, actual_col]].dropna()
        if len(valid) < 5:
            continue

        m = compute_metrics(
            valid[actual_col].values,
            valid[pred_col].values,
        )
        metrics[horizon] = m
        logger.info(
            "  %s: Brier=%.4f, BSS=%.3f, AUC=%.3f, n=%d",
            horizon,
            m["brier"],
            m["bss"],
            m["auc"],
            m["n_samples"],
        )

    results_df.attrs["metrics"] = metrics
    results_df.attrs["n_predictions"] = len(results_df)

    return results_df


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    from backend.services.data_fetcher import DataFetcher

    logger.info("Fetching data for walk-forward backtest...")
    fetcher = DataFetcher()
    data, _ = fetcher.fetch_market_data()
    fred_data = fetcher.fetch_fred_data()

    results = run_backtest(data, fred_data=fred_data)

    if len(results) > 0:
        metrics = results.attrs.get("metrics", {})
        print("\n" + "=" * 60)
        print("WALK-FORWARD BACKTEST RESULTS")
        print("=" * 60)
        for horizon, m in metrics.items():
            print(
                f"  {horizon}: Brier={m['brier']:.4f}, "
                f"BSS={m['bss']:.3f}, AUC={m['auc']:.3f}, "
                f"n={m['n_samples']}"
            )
        print(f"\nTotal predictions: {len(results)}")

        # Save results
        output_path = Path("engine/validation/backtest_results.csv")
        results.to_csv(output_path, index=False)
        logger.info("Results saved to %s", output_path)
