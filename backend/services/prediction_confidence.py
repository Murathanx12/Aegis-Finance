"""
Aegis Finance — Prediction Confidence Scorer
==============================================

Quantifies prediction uncertainty for stock analysis by combining:
  1. Drift severity — how much the feature distribution has shifted
  2. MC simulation spread — width of P10-P90 range relative to median
  3. GARCH fit quality — tail thickness (nu) and vol persistence
  4. Data sufficiency — years of price history available

Outputs a confidence grade (A-F), a numeric score (0-1), and
drift-adjusted prediction intervals that widen under uncertainty.

Usage:
    from backend.services.prediction_confidence import score_prediction_confidence

    conf = score_prediction_confidence(
        mc_p10_return=-10.0, mc_p90_return=120.0, mc_median_return=50.0,
        garch_nu=8.0, garch_persistence=0.97,
        data_years=4.5, drift_severity="critical",
    )
    # conf = {"grade": "C", "score": 0.52, "adjusted_p10": ..., ...}
"""

import logging
from typing import Optional

import numpy as np

from backend.config import config

logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────────

_DRIFT_CFG = config["ml"]["drift"]

# Drift severity → confidence penalty (0 = no penalty, 1 = total distrust)
_DRIFT_PENALTY: dict[str, float] = {
    "none": 0.0,
    "low": 0.05,
    "moderate": 0.20,
    "high": 0.40,
    "critical": 0.60,
}

# Grade boundaries: score >= threshold → grade
_GRADE_THRESHOLDS = [
    (0.80, "A"),
    (0.65, "B"),
    (0.50, "C"),
    (0.35, "D"),
    (0.0, "F"),
]

# Interval widening factor per drift severity
# When drift is critical, P10/P90 widen by this multiplier beyond median
_INTERVAL_WIDENING: dict[str, float] = {
    "none": 1.0,
    "low": 1.05,
    "moderate": 1.15,
    "high": 1.35,
    "critical": 1.60,
}


def score_prediction_confidence(
    mc_p10_return: float,
    mc_p90_return: float,
    mc_median_return: float,
    garch_nu: Optional[float] = None,
    garch_persistence: Optional[float] = None,
    data_years: float = 5.0,
    drift_severity: Optional[str] = None,
    beta: float = 1.0,
) -> dict:
    """Score prediction confidence and compute drift-adjusted intervals.

    Args:
        mc_p10_return: Monte Carlo 10th percentile 5Y return (%)
        mc_p90_return: Monte Carlo 90th percentile 5Y return (%)
        mc_median_return: Monte Carlo median 5Y return (%)
        garch_nu: Student-t degrees of freedom from GARCH (lower = fatter tails)
        garch_persistence: GARCH alpha+gamma+beta (closer to 1 = more persistent vol)
        data_years: Years of price history used for estimation
        drift_severity: Drift detector severity level (none/low/moderate/high/critical)
        beta: Stock beta (high beta = wider natural uncertainty)

    Returns:
        dict with grade, score, adjusted intervals, and component breakdown
    """
    if drift_severity is None:
        drift_severity = "none"

    components = {}

    # ── Component 1: Drift penalty (0-1, higher = worse) ─────────────────
    drift_penalty = _DRIFT_PENALTY.get(drift_severity, 0.3)
    drift_score = 1.0 - drift_penalty
    components["drift"] = round(drift_score, 3)

    # ── Component 2: MC spread quality (0-1) ─────────────────────────────
    # Narrow, well-separated intervals → high confidence
    # Extremely wide or asymmetric → lower confidence
    spread = mc_p90_return - mc_p10_return
    if spread > 0 and mc_median_return != 0:
        # Coefficient of variation of the spread: normalize by absolute median
        cv = spread / max(abs(mc_median_return), 10.0)  # floor at 10% to avoid div issues
        # CV of ~1-2 is typical for 5Y stock MC; >4 is very uncertain
        spread_score = float(np.clip(1.0 - (cv - 1.0) / 5.0, 0.1, 1.0))
    else:
        spread_score = 0.5  # degenerate case
    components["mc_spread"] = round(spread_score, 3)

    # ── Component 3: GARCH tail quality (0-1) ────────────────────────────
    # Higher nu = thinner tails = more predictable
    # nu=4 (very fat) → 0.3, nu=8 → 0.6, nu=30+ → 0.9
    if garch_nu is not None and garch_nu > 2:
        tail_score = float(np.clip((garch_nu - 3) / 25.0, 0.1, 0.95))
    else:
        tail_score = 0.5  # no GARCH → neutral assumption

    # High persistence means vol clusters → harder to predict
    if garch_persistence is not None:
        # persistence > 0.98 → penalize; < 0.90 → slight boost
        persistence_penalty = float(np.clip((garch_persistence - 0.90) / 0.10, 0.0, 0.5))
        tail_score = tail_score * (1.0 - persistence_penalty * 0.3)

    components["tail_quality"] = round(tail_score, 3)

    # ── Component 4: Data sufficiency (0-1) ──────────────────────────────
    # 5+ years → full score; 1 year → low; <1 year → very low
    data_score = float(np.clip(data_years / 5.0, 0.2, 1.0))
    components["data_sufficiency"] = round(data_score, 3)

    # ── Component 5: Beta stability (0-1) ────────────────────────────────
    # Extreme betas are harder to predict (very high or very low)
    if 0.5 <= beta <= 1.5:
        beta_score = 0.9
    elif 0.3 <= beta <= 2.5:
        beta_score = 0.7
    else:
        beta_score = 0.5
    components["beta_stability"] = round(beta_score, 3)

    # ── Weighted composite score ─────────────────────────────────────────
    weights = {
        "drift": 0.35,          # drift is the dominant uncertainty source
        "mc_spread": 0.20,
        "tail_quality": 0.15,
        "data_sufficiency": 0.15,
        "beta_stability": 0.15,
    }
    composite = sum(components[k] * weights[k] for k in weights)
    composite = float(np.clip(composite, 0.0, 1.0))

    # ── Grade assignment ─────────────────────────────────────────────────
    grade = "F"
    for threshold, g in _GRADE_THRESHOLDS:
        if composite >= threshold:
            grade = g
            break

    # ── Drift-adjusted prediction intervals ──────────────────────────────
    widening = _INTERVAL_WIDENING.get(drift_severity, 1.0)
    median = mc_median_return

    # Widen symmetrically around median
    adj_p10 = median - (median - mc_p10_return) * widening
    adj_p90 = median + (mc_p90_return - median) * widening

    # ── Interpretation ───────────────────────────────────────────────────
    if grade in ("A", "B"):
        interpretation = "High confidence — predictions are well-calibrated"
    elif grade == "C":
        interpretation = "Moderate confidence — consider wider outcome range"
    elif grade == "D":
        interpretation = "Low confidence — significant uncertainty in predictions"
    else:
        interpretation = "Very low confidence — treat predictions as directional only"

    if drift_severity in ("high", "critical"):
        interpretation += f" (feature drift is {drift_severity})"

    return {
        "grade": grade,
        "score": round(composite, 3),
        "components": components,
        "drift_severity": drift_severity,
        "interpretation": interpretation,
        # Original MC intervals
        "mc_p10": round(mc_p10_return, 2),
        "mc_p90": round(mc_p90_return, 2),
        "mc_median": round(mc_median_return, 2),
        # Drift-adjusted intervals (wider under uncertainty)
        "adjusted_p10": round(adj_p10, 2),
        "adjusted_p90": round(adj_p90, 2),
        "interval_widening": round(widening, 2),
    }
