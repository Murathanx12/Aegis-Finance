"""
Aegis Finance — Crash Timeline Estimator
==========================================

Monthly granularity crash probability over the next N months.
Uses Monte Carlo simulation to track when drawdowns first exceed
the crash threshold (20%) in each path.

Output:
  - Monthly crash probabilities
  - Cumulative crash probability curve
  - Peak risk month identification
  - Contributing risk factors with severity

Ported from market-engine-v5 with Aegis MC integration.

Usage:
    from backend.services.crash_timeline import estimate_crash_timeline
"""

import logging
from datetime import datetime, timedelta

import numpy as np

from backend.config import config, get_institutional_return

logger = logging.getLogger(__name__)


def estimate_crash_timeline(
    current_level: float,
    regime: str = "Neutral",
    risk_score: float = 0.0,
    vix: float = 20.0,
    yield_curve: float = 0.5,
    crash_prob_3m: float = None,
    months_ahead: int = 60,
) -> dict:
    """Estimate monthly crash probability over the next N months.

    A 'crash' is defined as >=20% drawdown from peak.

    Args:
        current_level: Current S&P 500 price level.
        regime: Current market regime (Bull/Bear/Volatile/Neutral).
        risk_score: Composite risk score [-4, +4].
        vix: Current VIX level.
        yield_curve: 10Y-3M yield spread.
        crash_prob_3m: ML crash probability for next 3 months (if available).
        months_ahead: Number of months to forecast (default 60 = 5 years).

    Returns:
        Dictionary with monthly probabilities, peak risk month, and factors.
    """
    from backend.services.monte_carlo import simulate_paths

    n_sims = 5000
    forecast_days = months_ahead * 21  # ~21 trading days per month

    inst_return = get_institutional_return()
    crash_threshold = config.get("risk", {}).get("crash_threshold", 0.20)

    # Use ML crash prob to modulate jump rate if available
    crash_freq = config["simulation"]["jump_diffusion"]["annual_rate"]
    if crash_prob_3m is not None:
        # Scale jump rate by how elevated crash probability is vs base rate.
        # crash_prob_3m is in decimal (0-1 scale), base_rate is also decimal.
        base_rate = config.get("crash_base_rate_pct", 12.0) / 100.0
        # Guard: if caller passes percentage (>1), convert to decimal
        prob = crash_prob_3m if crash_prob_3m <= 1.0 else crash_prob_3m / 100.0
        crash_freq *= max(0.5, min(3.0, prob / base_rate))

    # Build a neutral scenario dict for the simulation
    scenario = config.get("scenarios", {}).get("base", {
        "drift_adj": 0.0,
        "vol_mult": 1.0,
        "crash_mult": 1.0,
        "label": "Base",
    })

    paths = simulate_paths(
        start_price=current_level,
        historical_mu=inst_return,
        historical_sigma=vix / 100.0 if vix > 0 else 0.16,
        days=forecast_days,
        n_sims=n_sims,
        crash_freq=crash_freq,
        risk_score=risk_score,
        scenario=scenario,
        seed=42,
    )

    # Track when crashes first occur in each path
    monthly_crash_counts = np.zeros(months_ahead)
    crash_already_happened = np.zeros(n_sims, dtype=bool)

    for m in range(months_ahead):
        day_idx = min((m + 1) * 21, paths.shape[0] - 1)
        window = paths[:day_idx + 1]

        peaks = np.maximum.accumulate(window, axis=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            drawdowns = np.where(peaks > 0, (window - peaks) / peaks, 0.0)

        crashed_by_now = np.any(drawdowns <= -crash_threshold, axis=0)
        new_crashes = crashed_by_now & ~crash_already_happened
        monthly_crash_counts[m] = np.sum(new_crashes)
        crash_already_happened = crashed_by_now

    # Convert to probabilities
    monthly_probs = monthly_crash_counts / n_sims * 100
    cumulative_probs = np.minimum(np.cumsum(monthly_crash_counts) / n_sims * 100, 100.0)

    start = datetime.now()
    monthly_data = []
    for m in range(months_ahead):
        month_date = start + timedelta(days=30 * (m + 1))
        monthly_data.append({
            "month": m + 1,
            "date": month_date.strftime("%Y-%m"),
            "probability": round(float(monthly_probs[m]), 2),
            "cumulative": round(float(cumulative_probs[m]), 1),
        })

    peak_month = int(np.argmax(monthly_probs)) + 1
    peak_prob = float(monthly_probs[peak_month - 1])

    factors = _identify_risk_factors(risk_score, vix, yield_curve, regime, crash_prob_3m)

    return {
        "months_ahead": months_ahead,
        "total_simulations": n_sims,
        "crash_threshold_pct": round(crash_threshold * 100, 1),
        "monthly_probabilities": monthly_data,
        "peak_risk_month": peak_month,
        "peak_risk_probability": round(peak_prob, 2),
        "total_crash_probability_1y": round(float(cumulative_probs[min(11, months_ahead - 1)]), 1),
        "total_crash_probability_5y": round(float(cumulative_probs[-1]), 1),
        "contributing_factors": factors,
        "regime": regime,
        "risk_score": round(risk_score, 2),
    }


def _identify_risk_factors(
    risk_score: float,
    vix: float,
    yield_curve: float,
    regime: str,
    crash_prob: float = None,
) -> list[dict]:
    """Identify and rank current risk factors."""
    factors = []
    _vix_t = config.get("signal_thresholds_vix", {"low": 15, "moderate": 20, "elevated": 25, "high": 30})

    if vix > _vix_t["high"]:
        factors.append({"factor": "Extreme VIX", "severity": "HIGH",
                        "detail": f"VIX at {vix:.1f} — extreme market fear"})
    elif vix > _vix_t["elevated"]:
        factors.append({"factor": "Elevated VIX", "severity": "MEDIUM",
                        "detail": f"VIX at {vix:.1f} — above-average fear"})
    elif vix < _vix_t["low"]:
        factors.append({"factor": "Low VIX", "severity": "LOW",
                        "detail": f"VIX at {vix:.1f} — complacency risk"})

    if yield_curve is not None:
        if yield_curve < -0.5:
            factors.append({"factor": "Deeply Inverted Yield Curve", "severity": "HIGH",
                            "detail": f"10Y-3M spread at {yield_curve:+.2f}% — strong recession signal"})
        elif yield_curve < 0:
            factors.append({"factor": "Inverted Yield Curve", "severity": "MEDIUM",
                            "detail": f"10Y-3M spread at {yield_curve:+.2f}%"})

    if risk_score > 2.0:
        factors.append({"factor": "Elevated Macro Risk", "severity": "HIGH",
                        "detail": f"Composite risk score {risk_score:.1f} (threshold: 2.0)"})
    elif risk_score > 1.0:
        factors.append({"factor": "Above-Average Macro Risk", "severity": "MEDIUM",
                        "detail": f"Composite risk score {risk_score:.1f}"})

    if regime in ("Bear", "Volatile"):
        factors.append({"factor": f"{regime} Market Regime", "severity": "MEDIUM",
                        "detail": f"HMM-detected {regime.lower()} regime"})

    if crash_prob is not None and crash_prob > 0.25:
        factors.append({"factor": "ML Crash Warning", "severity": "HIGH",
                        "detail": f"3M crash probability {crash_prob:.0%}"})

    # Sort by severity
    severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    factors.sort(key=lambda f: severity_order.get(f["severity"], 3))

    return factors
