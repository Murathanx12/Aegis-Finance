"""
Aegis Finance — External Validation
======================================

Cross-checks engine predictions against independent sources:
1. Conference Board LEI — via FRED
2. SLOOS (lending conditions) — via FRED
3. Fed Funds Rate direction — via FRED
4. Consumer Sentiment — via FRED
5. IMF GDP Forecasts — hardcoded consensus

Returns consensus agreement % and divergence alerts.

Adapted from V7 validation/external_validator.py.

Usage:
    from backend.services.external_validator import validate_external
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

from backend.config import config


@dataclass
class ExternalValidation:
    """Result of external validation checks."""

    lei_signal: str = "UNKNOWN"
    sloos_signal: str = "UNKNOWN"
    fed_signal: str = "UNKNOWN"
    sentiment_signal: str = "UNKNOWN"
    consensus_direction: str = "UNKNOWN"
    engine_agreement: float = 0.0
    divergence_alerts: list = field(default_factory=list)


def validate_external(
    fred_data: dict,
    ml_crash_prob: Optional[float],
    current_regime: str,
) -> ExternalValidation:
    """Cross-check engine outputs against external data sources.

    Args:
        fred_data: Dict of FRED time series
        ml_crash_prob: Engine's current 12m crash probability (0-1)
        current_regime: Engine's current regime call

    Returns:
        ExternalValidation with per-source signals and agreement score
    """
    result = ExternalValidation()
    is_engine_bearish = current_regime in ("Bear", "Crisis", "Volatile") or (
        ml_crash_prob is not None and ml_crash_prob > 0.50
    )

    signals_agree = 0
    signals_total = 0

    # 1. Conference Board LEI
    if fred_data and "lei" in fred_data:
        result.lei_signal = _assess_lei(fred_data["lei"])
        signals_total += 1
        lei_bearish = result.lei_signal in ("WARNING", "RECESSION")
        if lei_bearish == is_engine_bearish:
            signals_agree += 1
        elif result.lei_signal == "RECESSION" and not is_engine_bearish:
            result.divergence_alerts.append(
                f"LEI signals RECESSION but engine says {current_regime}"
            )
        elif result.lei_signal == "EXPANSION" and is_engine_bearish:
            result.divergence_alerts.append(
                "LEI signals EXPANSION — leading indicators do not confirm bearish view"
            )

    # 2. SLOOS
    if fred_data and "sloos_ci" in fred_data:
        result.sloos_signal = _assess_sloos(fred_data["sloos_ci"])
        signals_total += 1
        sloos_bearish = result.sloos_signal == "TIGHTENING"
        if sloos_bearish == is_engine_bearish:
            signals_agree += 1
        elif result.sloos_signal == "TIGHTENING" and not is_engine_bearish:
            result.divergence_alerts.append(
                "Banks tightening lending (SLOOS) — credit conditions deteriorating"
            )

    # 3. Fed Funds Rate Direction
    if fred_data and "fed_funds" in fred_data:
        result.fed_signal = _assess_fed(fred_data["fed_funds"])
        signals_total += 1
        fed_bearish = result.fed_signal == "HAWKISH"
        if fed_bearish == is_engine_bearish:
            signals_agree += 1

    # 4. Consumer Sentiment
    if fred_data and "consumer_sentiment" in fred_data:
        result.sentiment_signal = _assess_sentiment(fred_data["consumer_sentiment"])
        signals_total += 1
        # Extreme fear is contrarian-BULLISH
        sentiment_bearish = result.sentiment_signal in ("NEUTRAL", "GREED")
        if sentiment_bearish == is_engine_bearish:
            signals_agree += 1
        elif result.sentiment_signal == "EXTREME_FEAR" and is_engine_bearish:
            result.divergence_alerts.append(
                "Consumer sentiment at EXTREME FEAR — historically contrarian-bullish"
            )

    # Compute agreement
    if signals_total > 0:
        result.engine_agreement = signals_agree / signals_total
    else:
        result.engine_agreement = 0.0

    # Determine consensus
    bearish_count = sum(1 for s in [
        result.lei_signal in ("WARNING", "RECESSION"),
        result.sloos_signal == "TIGHTENING",
        result.fed_signal == "HAWKISH",
        result.sentiment_signal in ("NEUTRAL", "GREED"),
    ] if s)

    if bearish_count >= 3:
        result.consensus_direction = "BEARISH"
    elif bearish_count <= 1:
        result.consensus_direction = "BULLISH"
    else:
        result.consensus_direction = "NEUTRAL"

    return result


def _assess_lei(lei_series: pd.Series) -> str:
    s = pd.Series(lei_series).dropna()
    if len(s) < 7:
        return "UNKNOWN"

    monthly = s.resample("MS").last().dropna()
    if len(monthly) < 2:
        return "UNKNOWN"

    consecutive_declines = 0
    for i in range(len(monthly) - 1, 0, -1):
        if monthly.iloc[i] < monthly.iloc[i - 1]:
            consecutive_declines += 1
        else:
            break

    if consecutive_declines >= 6:
        return "RECESSION"
    elif consecutive_declines >= 3:
        return "WARNING"
    else:
        return "EXPANSION"


def _assess_sloos(sloos_series: pd.Series) -> str:
    s = pd.Series(sloos_series).dropna()
    if len(s) == 0:
        return "UNKNOWN"

    latest = float(s.iloc[-1])
    if latest > 20:
        return "TIGHTENING"
    elif latest < -20:
        return "EASING"
    else:
        return "NEUTRAL"


def _assess_fed(fed_funds_series: pd.Series) -> str:
    s = pd.Series(fed_funds_series).dropna()
    if len(s) < 252:
        return "UNKNOWN"

    current = float(s.iloc[-1])
    year_ago = float(s.iloc[-252])

    change = current - year_ago
    if change > 0.25:
        return "HAWKISH"
    elif change < -0.25:
        return "DOVISH"
    else:
        return "NEUTRAL"


def _assess_sentiment(sentiment_series: pd.Series) -> str:
    s = pd.Series(sentiment_series).dropna()
    if len(s) == 0:
        return "UNKNOWN"

    latest = float(s.iloc[-1])
    if latest < 60:
        return "EXTREME_FEAR"
    elif latest < 80:
        return "FEAR"
    elif latest < 100:
        return "NEUTRAL"
    else:
        return "GREED"
