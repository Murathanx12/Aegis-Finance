"""
Aegis Finance — Market Regime Detection
==========================================

Classifies each trading day into Bull/Neutral/Bear/Volatile using:
  1. Rule-based: rolling returns + volatility with leading indicator overlays
  2. HMM-based: 3-state Gaussian HMM for probabilistic regime assignment

The HMM outputs (state_means, state_vols, regime_probs) feed directly
into the Monte Carlo engine's drift/vol blending, activating the
hmm_drift_blend and hmm_vol_blend parameters.

Usage:
    from backend.services.regime_detector import detect_regimes, fit_hmm_for_mc
"""

import logging

import numpy as np
import pandas as pd

from backend.config import config

logger = logging.getLogger(__name__)


def detect_regimes(data: pd.DataFrame, window: int = 252) -> tuple[pd.Series, str]:
    """Classify each day into Bull/Neutral/Bear/Volatile.

    Args:
        data: DataFrame with 'SP500' column (and optionally 'VIX', 'Risk_Score')
        window: Rolling window size (default 252 = 1 year)

    Returns:
        regimes: pd.Series of regime labels
        current: Current regime string
    """
    thresholds = config["risk"]["regimes"]
    returns = data["SP500"].pct_change()
    log_returns = np.log(1 + returns).replace([np.inf, -np.inf], np.nan)
    regimes = pd.Series(index=data.index, dtype=str, data="")

    has_vix = "VIX" in data.columns
    has_vix3m = "VIX3M" in data.columns
    has_risk = "Risk_Score" in data.columns

    # Short-window drawdown thresholds
    short_bear_1m = thresholds.get("short_bear_1m", -0.05)
    short_bear_3m = thresholds.get("short_bear_3m", -0.08)

    # VIX term structure thresholds (backwardation = stress signal)
    backwardation_thresh = thresholds.get("vix_backwardation_threshold", 1.05)
    severe_backwardation = thresholds.get("vix_severe_backwardation", 1.15)
    deep_contango = thresholds.get("vix_deep_contango", 0.80)

    for i in range(window, len(returns)):
        date_window = returns.index[max(0, i - window):i]
        w = log_returns.loc[date_window].dropna()
        if len(w) < 60:
            continue

        ann_ret = w.mean() * 252
        ann_vol = w.std() * np.sqrt(252)

        neutral_threshold = thresholds.get("neutral_return_threshold", 0.00)
        bear_threshold = thresholds.get("bear_return_threshold", -0.10)

        if ann_vol > thresholds["high_vol_threshold"]:
            base_regime = "Volatile"
        elif ann_ret > thresholds["bull_return_threshold"]:
            base_regime = "Bull"
        elif ann_ret > neutral_threshold:
            base_regime = "Neutral"
        elif ann_ret > bear_threshold:
            base_regime = "Bear"
        else:
            base_regime = "Volatile"

        # Leading indicator overlay
        vix_now = (
            float(data["VIX"].iloc[i])
            if has_vix and pd.notna(data["VIX"].iloc[i])
            else None
        )
        risk_now = (
            float(data["Risk_Score"].iloc[i])
            if has_risk and pd.notna(data["Risk_Score"].iloc[i])
            else None
        )

        # Short-window drawdown override: Bull cannot persist during sharp drops
        if base_regime == "Bull":
            # Check 21-day (1-month) return
            if i >= 21:
                ret_21d = float(data["SP500"].iloc[i] / data["SP500"].iloc[i - 21] - 1)
            else:
                ret_21d = 0.0
            # Check 63-day (3-month) return
            if i >= 63:
                ret_63d = float(data["SP500"].iloc[i] / data["SP500"].iloc[i - 63] - 1)
            else:
                ret_63d = 0.0

            if ret_21d < short_bear_1m or ret_63d < short_bear_3m:
                # Sharp drawdown → at least Neutral, maybe Bear
                if ret_21d < short_bear_1m * 2 or ret_63d < short_bear_3m * 2:
                    base_regime = "Bear"
                else:
                    base_regime = "Neutral"

        # VIX term structure signal: backwardation = near-term fear spike
        # VIX/VIX3M > 1.05 = mild backwardation, > 1.15 = severe stress
        vix_ratio = None
        if (has_vix and has_vix3m
                and vix_now is not None
                and pd.notna(data["VIX3M"].iloc[i])):
            vix3m_now = float(data["VIX3M"].iloc[i])
            if vix3m_now > 1.0:  # sanity check
                vix_ratio = vix_now / vix3m_now

        # Bull → Volatile if ANY stress signal flashing (was: required 2)
        if base_regime == "Bull":
            stress_signals = 0
            if vix_now is not None and vix_now > thresholds["vix_stress_threshold"]:
                stress_signals += 1
            if risk_now is not None and risk_now > thresholds["risk_stress_threshold"]:
                stress_signals += 1
            # VIX backwardation is a real-time stress signal from options market
            if vix_ratio is not None and vix_ratio > backwardation_thresh:
                stress_signals += 1
            if stress_signals >= 1:
                base_regime = "Volatile"

        # Severe backwardation: override Bull/Neutral → Volatile
        # This is a strong real-time signal — options market is pricing
        # near-term tail risk significantly above longer-term vol
        if vix_ratio is not None and vix_ratio > severe_backwardation:
            if base_regime in ("Bull", "Neutral"):
                base_regime = "Volatile"

        # Bear → Neutral if stress very low (recovery)
        elif base_regime == "Bear":
            calm_conditions = (
                vix_now is not None and vix_now < thresholds["vix_calm_threshold"]
                and risk_now is not None
                and risk_now < thresholds["risk_calm_threshold"]
            )
            # Also require VIX term structure is NOT in backwardation for recovery
            if vix_ratio is not None:
                calm_conditions = calm_conditions and vix_ratio < backwardation_thresh
            if calm_conditions and ann_vol < 0.20:
                base_regime = "Neutral"

        regimes.iloc[i] = base_regime

    current = regimes.iloc[-1] if regimes.iloc[-1] else "Unknown"
    logger.info("Current regime: %s", current)
    return regimes, current


def get_vix_term_structure_state(data: pd.DataFrame) -> dict:
    """Compute current VIX term structure state from market data.

    Uses VIX/VIX3M ratio to classify term structure:
      - severe_backwardation: VIX >> VIX3M (crisis-level near-term fear)
      - backwardation: VIX > VIX3M (stress, near-term fear elevated)
      - normal_contango: VIX < VIX3M (calm, normal markets)
      - deep_contango: VIX << VIX3M (complacency, potential vol spike ahead)

    Returns:
        Dict with ratio, structure classification, and signal score.
    """
    thresholds = config["risk"]["regimes"]
    backwardation_thresh = thresholds.get("vix_backwardation_threshold", 1.05)
    severe_thresh = thresholds.get("vix_severe_backwardation", 1.15)
    deep_contango_thresh = thresholds.get("vix_deep_contango", 0.80)

    if "VIX" not in data.columns or "VIX3M" not in data.columns:
        return {"available": False, "ratio": None, "structure": "unknown", "signal": 0.0}

    vix = data["VIX"].dropna()
    vix3m = data["VIX3M"].dropna()
    if len(vix) == 0 or len(vix3m) == 0:
        return {"available": False, "ratio": None, "structure": "unknown", "signal": 0.0}

    vix_now = float(vix.iloc[-1])
    vix3m_now = float(vix3m.iloc[-1])

    if vix3m_now <= 1.0:  # invalid data
        return {"available": False, "ratio": None, "structure": "unknown", "signal": 0.0}

    ratio = vix_now / vix3m_now

    # Classify term structure
    if ratio > severe_thresh:
        structure = "severe_backwardation"
        signal = -0.5  # strong bearish
    elif ratio > backwardation_thresh:
        structure = "backwardation"
        signal = -0.3  # moderately bearish
    elif ratio < deep_contango_thresh:
        structure = "deep_contango"
        signal = -0.1  # mild concern (complacency)
    else:
        structure = "normal_contango"
        signal = 0.1  # normal/slightly positive

    return {
        "available": True,
        "ratio": round(ratio, 3),
        "vix": round(vix_now, 2),
        "vix3m": round(vix3m_now, 2),
        "structure": structure,
        "signal": signal,
        "interpretation": _term_structure_interpretation(structure, vix_now, vix3m_now, ratio),
    }


def _term_structure_interpretation(structure: str, vix: float, vix3m: float, ratio: float) -> str:
    """Human-readable interpretation of VIX term structure state."""
    if structure == "severe_backwardation":
        return (
            f"Severe backwardation: VIX ({vix:.1f}) >> VIX3M ({vix3m:.1f}), "
            f"ratio {ratio:.2f}. Options market pricing acute near-term stress."
        )
    elif structure == "backwardation":
        return (
            f"Backwardation: VIX ({vix:.1f}) > VIX3M ({vix3m:.1f}), "
            f"ratio {ratio:.2f}. Near-term fear elevated above longer-term expectations."
        )
    elif structure == "deep_contango":
        return (
            f"Deep contango: VIX ({vix:.1f}) << VIX3M ({vix3m:.1f}), "
            f"ratio {ratio:.2f}. Unusual complacency — potential vol spike risk."
        )
    return (
        f"Normal contango: VIX ({vix:.1f}) < VIX3M ({vix3m:.1f}), "
        f"ratio {ratio:.2f}. Calm, well-functioning vol term structure."
    )


# ══════════════════════════════════════════════════════════════════════════════
# HMM REGIME FITTING — outputs MC-ready arrays
# ══════════════════════════════════════════════════════════════════════════════


def fit_hmm_for_mc(
    data: pd.DataFrame,
) -> dict:
    """Fit 3-state HMM and return arrays ready for simulate_paths().

    This bridges the gap between backend/models/hmm.py (fitting) and
    backend/services/monte_carlo.py (consumption). The MC engine accepts
    hmm_state_means, hmm_state_vols, and hmm_regime_probs — this function
    produces exactly those.

    Args:
        data: DataFrame with 'SP500' column (and optionally 'VIX')

    Returns:
        Dict with keys: state_means, state_vols, regime_probs, current_regime,
        success. All arrays are annualized and in return/vol space.
        Returns fallback values if HMM fitting fails.
    """
    try:
        from backend.models.hmm import fit_hmm_regimes
    except ImportError:
        logger.warning("HMM model not available")
        return _hmm_fallback()

    hmm_cfg = config["simulation"].get("hmm", {})
    try:
        hmm_result = fit_hmm_regimes(
            data,
            n_states=hmm_cfg.get("n_states", 3),
            n_fits=hmm_cfg.get("n_fits", 10),
        )
    except (ValueError, np.linalg.LinAlgError, KeyError) as e:
        logger.warning("HMM fitting failed: %s", e)
        return _hmm_fallback()

    if not hmm_result.success:
        return _hmm_fallback()

    # state_means from HMM are annualized log returns (feature 0 = smoothed ret * 252)
    # state_vols are annualized realized vol (feature 1 = rolling std * sqrt(252))
    # regime_probs are ordered [Bull, Bear, Crisis] — see hmm.py label ordering
    logger.info(
        "HMM fit: regime=%s, probs=[%.2f, %.2f, %.2f], "
        "means=[%.3f, %.3f, %.3f], vols=[%.3f, %.3f, %.3f]",
        hmm_result.current_regime,
        *hmm_result.regime_probs,
        *hmm_result.state_means,
        *hmm_result.state_vols,
    )

    return {
        "state_means": hmm_result.state_means,
        "state_vols": hmm_result.state_vols,
        "regime_probs": hmm_result.regime_probs,
        "current_regime": hmm_result.current_regime,
        "transition_matrix": hmm_result.transition_matrix,
        "success": True,
    }


def _hmm_fallback() -> dict:
    """Return neutral fallback when HMM is unavailable."""
    return {
        "state_means": None,
        "state_vols": None,
        "regime_probs": None,
        "current_regime": None,
        "transition_matrix": None,
        "success": False,
    }
