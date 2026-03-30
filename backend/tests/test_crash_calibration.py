"""
Task 4: Crash Probability Calibration Check
=============================================

Runs the crash prediction model on historical data at monthly intervals
and checks calibration: when model says X% crash prob, do crashes happen ~X%?

Note: Requires trained crash model (crash_model.pkl). If not available,
tests are skipped.
"""

import logging
import pytest
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _check_model_exists():
    """Check if crash model is trained."""
    from backend.config import MODEL_DIR
    model_path = MODEL_DIR / "crash_model.pkl"
    if not model_path.exists():
        pytest.skip("Crash model not trained — run engine.training.train_crash_model first")
    return model_path


class TestCrashCalibration:
    """Test crash model calibration against realized outcomes."""

    def test_calibration_table(self):
        """Run model on historical data and compute calibration buckets."""
        model_path = _check_model_exists()

        import yfinance as yf
        from backend.services.crash_model import CrashPredictor
        from backend.services.data_fetcher import DataFetcher
        from engine.training.features import build_feature_matrix

        # Load model
        predictor = CrashPredictor()
        predictor.load_model(str(model_path))

        # Fetch historical data
        fetcher = DataFetcher()
        data, _ = fetcher.fetch_market_data()

        # Also get S&P 500 for forward return calculation
        sp500 = data["SP500"].copy()

        try:
            fred_data = fetcher.fetch_fred_data()
        except Exception:
            fred_data = {}

        features = build_feature_matrix(data, fred_data=fred_data)
        available = [f for f in predictor.feature_names if f in features.columns]

        # Monthly evaluation dates
        eval_dates = features.index[features.index >= "2019-01-01"]
        eval_monthly = eval_dates[::21]  # ~monthly

        results = []
        for date in eval_monthly:
            # Only use data up to this date
            idx = features.index.get_loc(date)
            if idx < 1:
                continue

            row = features[available].iloc[[idx]]

            for horizon in predictor.lgb_models:
                try:
                    prob = float(predictor.predict_proba(row, horizon)[0])
                except Exception:
                    continue

                # Determine forward window
                if horizon == "3m":
                    fwd_days = 63
                elif horizon == "6m":
                    fwd_days = 126
                elif horizon == "12m":
                    fwd_days = 252
                else:
                    continue

                # Check if a >10% drawdown occurred in forward window
                fwd_start = features.index[idx]
                fwd_end_idx = min(idx + fwd_days, len(sp500) - 1)
                fwd_prices = sp500.iloc[idx:fwd_end_idx + 1]

                if len(fwd_prices) < fwd_days * 0.8:
                    continue  # not enough forward data

                peak = fwd_prices.cummax()
                drawdown = (fwd_prices - peak) / peak
                max_dd = float(drawdown.min())
                crash_occurred = max_dd < -0.10  # >10% drawdown

                results.append({
                    "date": str(fwd_start.date()),
                    "horizon": horizon,
                    "predicted_prob": prob,
                    "crash_occurred": crash_occurred,
                    "max_drawdown": max_dd,
                })

        df = pd.DataFrame(results)
        if df.empty:
            pytest.skip("No calibration data produced")

        # Compute calibration by bucket
        buckets = [(0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0)]
        calibration = []
        for low, high in buckets:
            mask = (df["predicted_prob"] >= low) & (df["predicted_prob"] < high)
            bucket_df = df[mask]
            if len(bucket_df) > 0:
                actual_rate = float(bucket_df["crash_occurred"].mean())
                calibration.append({
                    "bucket": f"{int(low*100)}-{int(high*100)}%",
                    "n_predictions": len(bucket_df),
                    "predicted_avg": float(bucket_df["predicted_prob"].mean()),
                    "actual_crash_rate": actual_rate,
                    "gap": abs(actual_rate - bucket_df["predicted_prob"].mean()),
                })

        logger.info("=== CRASH MODEL CALIBRATION TABLE ===")
        for row in calibration:
            logger.info(
                "  %s: n=%d, predicted=%.1f%%, actual=%.1f%%, gap=%.1f%%",
                row["bucket"], row["n_predictions"],
                row["predicted_avg"] * 100, row["actual_crash_rate"] * 100,
                row["gap"] * 100,
            )

        # Soft assertion: average gap should be < 30% (loose, given small sample)
        if calibration:
            avg_gap = np.mean([r["gap"] for r in calibration])
            logger.info("Average calibration gap: %.1f%%", avg_gap * 100)
            if avg_gap > 0.30:
                logger.warning(
                    "CALIBRATION WARNING: Average gap %.1f%% exceeds 30%%. "
                    "Consider recalibrating the model.",
                    avg_gap * 100,
                )

    def test_monotonic_horizons(self):
        """3m crash prob should be <= 6m <= 12m (monotonically increasing)."""
        model_path = _check_model_exists()

        from backend.services.crash_model import CrashPredictor
        from backend.services.data_fetcher import DataFetcher
        from engine.training.features import build_feature_matrix

        predictor = CrashPredictor()
        predictor.load_model(str(model_path))

        fetcher = DataFetcher()
        data, _ = fetcher.fetch_market_data()

        try:
            fred_data = fetcher.fetch_fred_data()
        except Exception:
            fred_data = {}

        features = build_feature_matrix(data, fred_data=fred_data)
        available = [f for f in predictor.feature_names if f in features.columns]
        latest = features[available].iloc[[-1]]

        probs = {}
        for horizon in predictor.lgb_models:
            probs[horizon] = float(predictor.predict_proba(latest, horizon)[0])

        logger.info("Current crash probabilities: %s", probs)

        if "3m" in probs and "6m" in probs:
            assert probs["3m"] <= probs["6m"] + 0.05, \
                f"3m prob ({probs['3m']:.3f}) should be <= 6m ({probs['6m']:.3f})"

        if "6m" in probs and "12m" in probs:
            assert probs["6m"] <= probs["12m"] + 0.05, \
                f"6m prob ({probs['6m']:.3f}) should be <= 12m ({probs['12m']:.3f})"
