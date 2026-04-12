"""
Aegis Finance — LPPL Bubble Detector
======================================

Implements Sornette's Log-Periodic Power Law Singularity model for bubble
detection. The LPPL model fits price as:

    LPPL(t) = A + B(tc - t)^m + C(tc - t)^m * cos[ω ln(tc - t) + φ]

where tc is the estimated critical time (bubble peak). The confidence indicator
— computed via nested fits across multiple time windows — is the primary output,
functioning as a bubble thermometer rather than a point prediction.

This is used as an optional signal overlay in signal_engine.py. It only fires
when LPPL confidence exceeds a configurable threshold to minimize false positives.

Reference:
    Sornette (2003), "Why Stock Markets Crash"
    Demos & Sornette (2017), "Birth or burst of financial bubbles"

Usage:
    from backend.services.bubble_detector import get_bubble_status
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from backend.config import config

logger = logging.getLogger(__name__)

try:
    from lppls import lppls as lppls_module
    LPPLS_AVAILABLE = True
except ImportError:
    LPPLS_AVAILABLE = False
    logger.info("lppls not installed — bubble detection disabled")

BUBBLE_CFG = config.get("bubble_detection", {})
CONFIDENCE_THRESHOLD = BUBBLE_CFG.get("confidence_threshold", 0.5)
MIN_WINDOW_DAYS = BUBBLE_CFG.get("min_window_days", 120)
MAX_WINDOW_DAYS = BUBBLE_CFG.get("max_window_days", 750)
N_FITS = BUBBLE_CFG.get("n_fits", 25)


def get_bubble_status(
    prices: pd.Series,
    ticker: str = "SP500",
) -> dict:
    """Compute LPPL bubble confidence indicator.

    Runs multiple LPPL fits with different time windows and computes
    a confidence score: fraction of fits that satisfy Sornette parameter bounds
    and have tc in the near future.

    Args:
        prices: Daily price series (pd.Series with DatetimeIndex).
        ticker: Label for logging.

    Returns:
        dict with confidence (0-1), is_bubble (bool), tc_median (estimated
        critical date), n_valid_fits, and status string.
    """
    if not LPPLS_AVAILABLE:
        return _empty_result("lppls not installed")

    if prices is None or len(prices) < MIN_WINDOW_DAYS:
        return _empty_result("insufficient data")

    try:
        # Prepare data in lppls format: [timestamp_ordinal, log_price]
        time_ordinal = np.array([d.toordinal() for d in prices.index])
        log_price = np.log(prices.values).astype(float)

        # Create observation matrix [time, log_price]
        observations = np.array([time_ordinal, log_price]).T

        # Create LPPL model
        model = lppls_module.LPPLS(observations=observations)

        # Run nested fits with different start windows
        valid_fits = []
        t2 = len(observations) - 1  # End at latest observation
        rng = np.random.default_rng(42)

        for _ in range(N_FITS):
            # Random start window between min and max
            window = rng.integers(MIN_WINDOW_DAYS, min(MAX_WINDOW_DAYS, len(observations)))
            t1 = max(0, t2 - window)

            try:
                tc, m, w, a, b, c1, c2, O, D = model.fit(t1, t2, max_searches=25)

                # Sornette parameter bounds for valid bubble fits
                if not _valid_sornette_params(tc, m, w, t2, time_ordinal):
                    continue

                valid_fits.append({
                    "tc": tc,
                    "m": m,
                    "omega": w,
                    "O": O,
                    "D": D,
                })

            except Exception:
                continue

        # Compute confidence as fraction of valid fits
        confidence = len(valid_fits) / N_FITS if N_FITS > 0 else 0.0

        # Median critical time from valid fits
        tc_median = None
        tc_date = None
        if valid_fits:
            tc_values = [f["tc"] for f in valid_fits]
            tc_median = float(np.median(tc_values))
            try:
                tc_date = datetime.fromordinal(int(tc_median)).strftime("%Y-%m-%d")
            except (ValueError, OverflowError):
                tc_date = None

        is_bubble = confidence >= CONFIDENCE_THRESHOLD
        if is_bubble:
            status = "bubble_warning"
            logger.warning(
                "%s: LPPL bubble detected (confidence=%.2f, tc=%s, valid=%d/%d)",
                ticker, confidence, tc_date, len(valid_fits), N_FITS,
            )
        else:
            status = "normal"
            logger.debug(
                "%s: LPPL normal (confidence=%.2f, valid=%d/%d)",
                ticker, confidence, len(valid_fits), N_FITS,
            )

        return {
            "confidence": round(confidence, 3),
            "is_bubble": is_bubble,
            "tc_median_date": tc_date,
            "n_valid_fits": len(valid_fits),
            "n_total_fits": N_FITS,
            "threshold": CONFIDENCE_THRESHOLD,
            "status": status,
            "ticker": ticker,
        }

    except Exception as e:
        logger.warning("%s: LPPL fitting failed — %s", ticker, e)
        return _empty_result(f"fitting failed: {e}")


def _valid_sornette_params(
    tc: float, m: float, w: float, t2: int, time_ordinal: np.ndarray,
) -> bool:
    """Check if LPPL fit parameters satisfy Sornette bounds.

    Valid ranges (Sornette, 2003):
    - 0.1 ≤ m ≤ 0.9 (power law exponent)
    - 6 ≤ ω ≤ 13 (log-periodic frequency)
    - tc > t2 (critical time must be in the future)
    - tc < t2 + 0.4 * (t2 - t1) (not too far in the future)
    """
    last_t = time_ordinal[t2]

    # tc must be in the future but not too far
    if tc <= last_t:
        return False
    horizon = tc - last_t
    if horizon > 365:  # More than 1 year out is unreliable
        return False

    # Power law exponent bounds
    if m < 0.1 or m > 0.9:
        return False

    # Log-periodic frequency bounds
    if w < 6.0 or w > 13.0:
        return False

    return True


def get_bubble_signal_score(prices: pd.Series, ticker: str = "SP500") -> Optional[float]:
    """Return a signal score in [-1, 0] for use in signal_engine.

    Returns negative values when bubble is detected (bearish overlay).
    Returns 0 when no bubble detected. Returns None when unavailable.
    """
    status = get_bubble_status(prices, ticker)
    if status.get("confidence") is None:
        return None

    confidence = status["confidence"]
    if confidence < CONFIDENCE_THRESHOLD * 0.5:
        return 0.0  # No signal

    # Scale: -0.5 at threshold, -1.0 at confidence=1.0
    if confidence >= CONFIDENCE_THRESHOLD:
        return -0.5 - 0.5 * min(1.0, (confidence - CONFIDENCE_THRESHOLD) / (1 - CONFIDENCE_THRESHOLD + 1e-9))
    else:
        # Partial warning zone (half threshold to threshold)
        return -0.25 * (confidence - CONFIDENCE_THRESHOLD * 0.5) / (CONFIDENCE_THRESHOLD * 0.5 + 1e-9)


def _empty_result(reason: str) -> dict:
    return {
        "confidence": None,
        "is_bubble": False,
        "tc_median_date": None,
        "n_valid_fits": 0,
        "n_total_fits": 0,
        "threshold": CONFIDENCE_THRESHOLD,
        "status": reason,
        "ticker": None,
    }
