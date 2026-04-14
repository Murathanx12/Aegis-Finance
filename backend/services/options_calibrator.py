"""
Aegis Finance — Options-Implied Monte Carlo Calibrator
========================================================

Bridges options intelligence → Monte Carlo simulation by extracting
forward-looking parameters from options market data.

Options are the only truly forward-looking signal in markets. GARCH
extrapolates past volatility; options reflect what traders are *paying*
for future risk. This calibrator blends both to produce more
market-consistent MC parameters.

Outputs (all optional — MC degrades gracefully without them):
  - implied_vol: ATM IV blended with GARCH vol
  - jump_freq_mult: Crash frequency multiplier from P/C ratio + IV rank
  - jump_mag_adj: Jump magnitude adjustment from IV skew steepness
  - vol_kappa_adj: Vol mean-reversion speed from VIX term structure

Usage:
    from backend.services.options_calibrator import calibrate_mc_from_options

    cal = calibrate_mc_from_options(options_data, garch_vol=0.25)
    # Pass cal["implied_vol"] as garch_vol override into simulate_paths
    # Pass cal["jump_freq_mult"] as crash frequency multiplier
"""

import logging
from typing import Optional

import numpy as np

from backend.config import config

logger = logging.getLogger(__name__)

# Config section for options calibration parameters
_OPT_CAL_CFG = config.get("options_calibration", {})

# Default blending weight: how much to trust IV vs GARCH
# 0.0 = pure GARCH (backward-looking), 1.0 = pure IV (forward-looking)
_IV_BLEND_WEIGHT = _OPT_CAL_CFG.get("iv_blend_weight", 0.35)

# IV skew thresholds for jump magnitude adjustment
_SKEW_NEUTRAL = _OPT_CAL_CFG.get("skew_neutral", 1.1)  # Normal skew level
_SKEW_ELEVATED = _OPT_CAL_CFG.get("skew_elevated", 1.4)  # High fear

# P/C ratio thresholds
_PC_NEUTRAL = _OPT_CAL_CFG.get("pc_ratio_neutral", 0.9)
_PC_ELEVATED = _OPT_CAL_CFG.get("pc_ratio_elevated", 1.5)

# IV rank thresholds for jump frequency
_IVRANK_LOW = _OPT_CAL_CFG.get("iv_rank_low", 25.0)
_IVRANK_HIGH = _OPT_CAL_CFG.get("iv_rank_high", 75.0)

# IV skew floor: below this = flat/inverted skew (complacent about tails)
_SKEW_FLOOR = _OPT_CAL_CFG.get("skew_floor", 0.9)


def calibrate_mc_from_options(
    options_data: dict,
    garch_vol: Optional[float] = None,
    ticker: str = "SPY",
) -> dict:
    """Extract MC calibration parameters from options intelligence output.

    This function takes the output of get_options_summary() and returns
    parameters that can be passed to simulate_paths() to incorporate
    forward-looking market information.

    Args:
        options_data: Output from options_intelligence.get_options_summary()
        garch_vol: Current GARCH-estimated annualized volatility (for blending)
        ticker: Ticker symbol (for logging)

    Returns:
        Dict with calibration parameters:
            - implied_vol: Blended vol estimate (GARCH + IV)
            - jump_freq_mult: Multiplier for base crash frequency [0.5, 2.5]
            - jump_mag_adj: Additive adjustment to jump mean (negative = larger crashes)
            - vol_kappa_mult: Multiplier for vol mean-reversion speed
            - confidence: How much to trust these calibrations (0-1)
            - components: Breakdown of what drove each adjustment
    """
    if not options_data or "error" in options_data:
        return _null_calibration("No options data available")

    components = {}

    # ══════════════════════════════════════════════════════════════════
    # 1. IMPLIED VOLATILITY — blend ATM IV with GARCH
    # ══════════════════════════════════════════════════════════════════
    atm_iv = options_data.get("atm_iv_call")
    implied_vol = None

    if atm_iv is not None and atm_iv > 0.01:
        if garch_vol is not None and garch_vol > 0.01:
            # Weighted blend: IV is forward-looking but noisy (bid-ask, liquidity)
            # GARCH is backward-looking but stable
            implied_vol = (1 - _IV_BLEND_WEIGHT) * garch_vol + _IV_BLEND_WEIGHT * atm_iv
            components["vol_blend"] = {
                "garch_vol": round(garch_vol, 4),
                "atm_iv": round(atm_iv, 4),
                "blend_weight": _IV_BLEND_WEIGHT,
                "result": round(implied_vol, 4),
            }
        else:
            implied_vol = atm_iv
            components["vol_blend"] = {
                "source": "iv_only",
                "atm_iv": round(atm_iv, 4),
            }
    elif garch_vol is not None:
        implied_vol = garch_vol
        components["vol_blend"] = {"source": "garch_only"}

    # ══════════════════════════════════════════════════════════════════
    # 2. JUMP FREQUENCY — from P/C ratio + IV rank
    # ══════════════════════════════════════════════════════════════════
    # High P/C ratio = traders buying puts = expecting crashes
    # High IV rank = vol is elevated relative to history = risk pricing up
    pc_ratio = options_data.get("put_call_volume_ratio") or options_data.get(
        "put_call_oi_ratio"
    )
    iv_rank = options_data.get("iv_rank")

    jump_freq_mult = 1.0
    pc_contribution = 0.0
    ivr_contribution = 0.0

    if pc_ratio is not None:
        # Map P/C ratio to a multiplier contribution
        # PC < 0.9 → bullish (fewer puts), reduce jump freq
        # PC > 1.5 → bearish (heavy put buying), increase jump freq
        if pc_ratio < _PC_NEUTRAL:
            pc_contribution = -0.2 * (_PC_NEUTRAL - pc_ratio) / _PC_NEUTRAL
        elif pc_ratio > _PC_ELEVATED:
            pc_contribution = 0.3 * min(2.0, (pc_ratio - _PC_ELEVATED) / _PC_ELEVATED)
        else:
            pc_contribution = 0.2 * (pc_ratio - _PC_NEUTRAL) / (_PC_ELEVATED - _PC_NEUTRAL)

    if iv_rank is not None:
        # Map IV rank (0-100) to frequency contribution
        # Low IV rank → market complacent → reduce jump freq
        # High IV rank → market scared → increase jump freq
        if iv_rank < _IVRANK_LOW:
            ivr_contribution = -0.15
        elif iv_rank > _IVRANK_HIGH:
            ivr_contribution = 0.15 * min(2.0, (iv_rank - _IVRANK_HIGH) / (100 - _IVRANK_HIGH))
        else:
            ivr_contribution = 0.0

    jump_freq_mult = float(np.clip(1.0 + pc_contribution + ivr_contribution, 0.5, 2.5))
    components["jump_freq"] = {
        "pc_ratio": pc_ratio,
        "iv_rank": iv_rank,
        "pc_contribution": round(pc_contribution, 4),
        "ivr_contribution": round(ivr_contribution, 4),
        "multiplier": round(jump_freq_mult, 4),
    }

    # ══════════════════════════════════════════════════════════════════
    # 3. JUMP MAGNITUDE — from IV skew
    # ══════════════════════════════════════════════════════════════════
    # Steep skew = expensive OTM puts = market pricing larger crashes
    # Normal skew ~1.1 (puts always slightly more expensive)
    iv_skew = options_data.get("iv_skew")
    jump_mag_adj = 0.0

    if iv_skew is not None:
        if iv_skew > _SKEW_ELEVATED:
            # Very steep skew: market pricing extreme tail events
            # Adjust jump mean more negative (larger crashes)
            jump_mag_adj = -0.02 * min(3.0, (iv_skew - _SKEW_ELEVATED) / 0.3)
        elif iv_skew > _SKEW_NEUTRAL:
            # Moderately elevated skew
            jump_mag_adj = -0.01 * (iv_skew - _SKEW_NEUTRAL) / (_SKEW_ELEVATED - _SKEW_NEUTRAL)
        elif iv_skew < _SKEW_FLOOR:
            # Flat/inverted skew (rare) — market unusually complacent about tails
            jump_mag_adj = 0.01

    jump_mag_adj = float(np.clip(jump_mag_adj, -0.06, 0.02))
    components["jump_magnitude"] = {
        "iv_skew": iv_skew,
        "adjustment": round(jump_mag_adj, 4),
    }

    # ══════════════════════════════════════════════════════════════════
    # 4. VOL MEAN-REVERSION — from term structure
    # ══════════════════════════════════════════════════════════════════
    # Contango (normal): near IV < far IV → market expects vol to stay/rise slowly
    #   → normal mean-reversion speed (kappa multiplier = 1.0)
    # Backwardation: near IV > far IV → market expects vol spike to decay
    #   → faster mean-reversion (kappa multiplier > 1.0, vol decays faster)
    vol_kappa_mult = 1.0
    iv_term = options_data.get("iv_term_structure")

    if iv_term is not None:
        slope = iv_term.get("slope", 0)  # mid_iv - near_iv
        if slope < -0.03:
            # Backwardation: near-term vol elevated → will revert faster
            vol_kappa_mult = 1.0 + min(0.5, abs(slope) * 5)
        elif slope > 0.05:
            # Strong contango: vol expected to stay low → slower reversion
            vol_kappa_mult = max(0.7, 1.0 - slope * 2)

    # Also check VIX term structure if available (for market-level)
    vix_data = options_data.get("vix_term_structure")
    if vix_data is not None:
        vix_ratio = vix_data.get("vix_vix3m_ratio", 1.0)
        if vix_ratio > 1.1:
            # VIX > VIX3M: backwardation, near-term stress → faster reversion
            vol_kappa_mult = max(vol_kappa_mult, 1.0 + (vix_ratio - 1.0) * 2)
        elif vix_ratio < 0.85:
            # Deep contango: complacency → slower reversion
            vol_kappa_mult = min(vol_kappa_mult, 0.75)

    vol_kappa_mult = float(np.clip(vol_kappa_mult, 0.5, 2.0))
    components["vol_kappa"] = {
        "iv_term_slope": iv_term.get("slope") if iv_term else None,
        "vix_ratio": vix_data.get("vix_vix3m_ratio") if vix_data else None,
        "multiplier": round(vol_kappa_mult, 4),
    }

    # ══════════════════════════════════════════════════════════════════
    # 5. CONFIDENCE — how reliable are these calibrations?
    # ══════════════════════════════════════════════════════════════════
    # Higher confidence when we have more data points and they agree
    confidence = _compute_confidence(options_data)

    logger.info(
        "%s options calibration: implied_vol=%.3f, jump_freq_mult=%.2f, "
        "jump_mag_adj=%.3f, vol_kappa_mult=%.2f, confidence=%.2f",
        ticker,
        implied_vol or 0,
        jump_freq_mult,
        jump_mag_adj,
        vol_kappa_mult,
        confidence,
    )

    return {
        "implied_vol": implied_vol,
        "jump_freq_mult": jump_freq_mult,
        "jump_mag_adj": jump_mag_adj,
        "vol_kappa_mult": vol_kappa_mult,
        "confidence": confidence,
        "components": components,
    }


def _compute_confidence(options_data: dict) -> float:
    """Estimate confidence in options calibration (0-1).

    Higher when:
    - We have both ATM IV and IV rank (anchored relative to history)
    - Sufficient volume (liquid options = reliable prices)
    - IV skew is computable (need OTM data)
    """
    score = 0.0
    max_score = 0.0

    # ATM IV available
    max_score += 0.3
    if options_data.get("atm_iv_call") is not None:
        score += 0.3

    # IV rank (need historical context)
    max_score += 0.2
    if options_data.get("iv_rank") is not None:
        score += 0.2

    # Volume (liquidity)
    max_score += 0.2
    total_vol = (options_data.get("total_call_volume", 0) +
                 options_data.get("total_put_volume", 0))
    if total_vol > 10000:
        score += 0.2
    elif total_vol > 1000:
        score += 0.1

    # IV skew
    max_score += 0.15
    if options_data.get("iv_skew") is not None:
        score += 0.15

    # Term structure
    max_score += 0.15
    if options_data.get("iv_term_structure") is not None:
        score += 0.15

    return round(score / max_score, 3) if max_score > 0 else 0.0


def _null_calibration(reason: str) -> dict:
    """Return neutral calibration when options data is unavailable."""
    return {
        "implied_vol": None,
        "jump_freq_mult": 1.0,
        "jump_mag_adj": 0.0,
        "vol_kappa_mult": 1.0,
        "confidence": 0.0,
        "components": {"reason": reason},
    }


def apply_calibration_to_mc_params(
    calibration: dict,
    garch_vol: Optional[float] = None,
    base_crash_freq: float = 0.07,
    jump_mean: float = -0.10,
) -> dict:
    """Apply options calibration to MC parameters for simulate_paths().

    This is a convenience function that translates calibration output
    into the actual parameter overrides for simulate_paths().

    Args:
        calibration: Output from calibrate_mc_from_options()
        garch_vol: Base GARCH vol (used if implied_vol is None)
        base_crash_freq: Base annual crash frequency
        jump_mean: Base jump mean (e.g., -0.10)

    Returns:
        Dict with MC parameter overrides:
            - garch_vol: Blended vol (or original if no IV)
            - crash_freq: Adjusted crash frequency
            - jump_mean: Adjusted jump mean
            - garch_persistence: Adjusted (via vol_kappa_mult)
    """
    confidence = calibration.get("confidence", 0.0)

    # Scale adjustments by confidence — uncertain calibrations have less effect
    scale = confidence

    # Vol override
    effective_vol = calibration.get("implied_vol") or garch_vol

    # Crash frequency
    freq_mult = 1.0 + (calibration.get("jump_freq_mult", 1.0) - 1.0) * scale
    effective_crash_freq = float(np.clip(base_crash_freq * freq_mult, 0.02, 0.25))

    # Jump magnitude
    mag_adj = calibration.get("jump_mag_adj", 0.0) * scale
    effective_jump_mean = jump_mean + mag_adj

    # Vol mean-reversion (affects GARCH persistence)
    # Higher kappa_mult → faster reversion → lower persistence
    kappa_mult = calibration.get("vol_kappa_mult", 1.0)
    # Don't override persistence directly — just return the kappa multiplier
    # for the caller to apply

    return {
        "garch_vol": effective_vol,
        "crash_freq": effective_crash_freq,
        "jump_mean": effective_jump_mean,
        "vol_kappa_mult": kappa_mult,
        "confidence": confidence,
        "adjustments_applied": scale > 0.01,
    }
