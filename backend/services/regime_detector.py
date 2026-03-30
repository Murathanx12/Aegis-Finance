"""
Aegis Finance — Market Regime Detection
==========================================

Classifies each trading day into Bull/Neutral/Bear/Volatile using
rolling returns + volatility with leading indicator overlays
(VIX, risk score) for early transition detection.

Usage:
    from backend.services.regime_detector import detect_regimes
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
    has_risk = "Risk_Score" in data.columns

    # Short-window drawdown thresholds
    short_bear_1m = thresholds.get("short_bear_1m", -0.05)
    short_bear_3m = thresholds.get("short_bear_3m", -0.08)

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

        # Bull → Volatile if ANY stress signal flashing (was: required 2)
        if base_regime == "Bull":
            stress_signals = 0
            if vix_now is not None and vix_now > thresholds["vix_stress_threshold"]:
                stress_signals += 1
            if risk_now is not None and risk_now > thresholds["risk_stress_threshold"]:
                stress_signals += 1
            if stress_signals >= 1:
                base_regime = "Volatile"

        # Bear → Neutral if stress very low (recovery)
        elif base_regime == "Bear":
            if (vix_now is not None and vix_now < thresholds["vix_calm_threshold"]
                    and risk_now is not None
                    and risk_now < thresholds["risk_calm_threshold"]):
                if ann_vol < 0.20:
                    base_regime = "Neutral"

        regimes.iloc[i] = base_regime

    current = regimes.iloc[-1] if regimes.iloc[-1] else "Unknown"
    logger.info("Current regime: %s", current)
    return regimes, current
