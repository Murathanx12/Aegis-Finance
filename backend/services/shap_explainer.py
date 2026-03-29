"""
Aegis Finance — SHAP Explainability Service
==============================================

Wraps SHAP TreeExplainer for LightGBM crash model.
Provides feature importance and counterfactual analysis.

Usage:
    from backend.services.shap_explainer import explain_prediction, run_counterfactual
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def explain_prediction(
    predictor,
    features: pd.DataFrame,
    horizon: str = "3m",
    top_n: int = 10,
) -> dict:
    """Compute SHAP explanation for a crash prediction.

    Args:
        predictor: Trained CrashPredictor instance
        features: Feature DataFrame (single row or multiple)
        horizon: Prediction horizon ("3m", "6m", "12m")
        top_n: Number of top features to return

    Returns:
        Dict with crash_prob, top_features, base_value
    """
    prob = float(predictor.predict_proba(features, horizon)[-1])

    # Get SHAP values
    shap_values = predictor.get_shap_values(features, horizon)

    top_features = []
    for feat_name, shap_val in shap_values[:top_n]:
        feat_val = None
        if isinstance(features, pd.DataFrame) and feat_name in features.columns:
            feat_val = float(features[feat_name].iloc[-1])

        top_features.append({
            "feature": feat_name,
            "shap_value": float(shap_val),
            "feature_value": feat_val,
        })

    return {
        "crash_prob": prob,
        "horizon": horizon,
        "top_features": top_features,
    }


def run_counterfactual(
    predictor,
    base_features: pd.DataFrame,
    scenarios: list[dict],
    horizon: str = "3m",
) -> dict:
    """What-if analysis: how does crash probability change under scenarios?

    Args:
        predictor: Trained CrashPredictor
        base_features: Current feature values
        scenarios: List of {"label": str, "overrides": {feature: value}}
        horizon: Prediction horizon

    Returns:
        Dict with base_prob and scenario results
    """
    base_prob = float(predictor.predict_proba(base_features, horizon)[-1])

    results = []
    for scenario in scenarios:
        modified = base_features.copy()
        for col, val in scenario.get("overrides", {}).items():
            if col in modified.columns:
                modified[col] = val

        scenario_prob = float(predictor.predict_proba(modified, horizon)[-1])
        results.append({
            "label": scenario["label"],
            "crash_prob": scenario_prob,
            "delta": scenario_prob - base_prob,
        })

    return {
        "base_prob": base_prob,
        "horizon": horizon,
        "scenarios": results,
    }


# Default counterfactual scenarios for the API
DEFAULT_SCENARIOS = [
    {"label": "VIX Spike to 40", "overrides": {"vix": 40, "vix_zscore": 3.0}},
    {"label": "Yield Curve Inversion", "overrides": {"term_spread": -0.5, "yield_curve_inverted": 1}},
    {"label": "Credit Stress", "overrides": {"credit_spread_proxy": 0.08}},
    {"label": "Market Crash (-20%)", "overrides": {"mom_3m": -0.20, "max_drawdown_3m": 0.20}},
    {"label": "Bull Market", "overrides": {"mom_3m": 0.10, "vix": 12, "vix_zscore": -1.5}},
]
