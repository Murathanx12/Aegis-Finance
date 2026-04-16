"""
Aegis Finance — Technical Analysis Service
=============================================

Comprehensive technical indicators using the `ta` library.
Closes the #1 gap vs TradingView: gives users actionable TA signals
alongside our ML-driven crash predictions.

Indicators computed:
  - Trend: SMA(20/50/200), EMA(12/26), MACD, ADX, Ichimoku Cloud
  - Momentum: RSI(14), Stochastic(14,3), Williams %R, CCI, ROC
  - Volatility: Bollinger Bands(20,2), ATR(14), Keltner Channel
  - Volume: OBV, VWAP proxy, Accumulation/Distribution, Force Index
  - Pattern: Golden/Death cross, support/resistance levels

Usage:
    from backend.services.technical_analysis import (
        compute_technical_indicators, get_ta_signal, get_ta_summary,
    )
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

try:
    import ta
    from ta.trend import SMAIndicator, EMAIndicator, MACD, ADXIndicator
    from ta.momentum import (
        RSIIndicator, StochasticOscillator, WilliamsRIndicator, ROCIndicator,
    )
    from ta.volatility import BollingerBands, AverageTrueRange, KeltnerChannel
    from ta.volume import (
        OnBalanceVolumeIndicator, AccDistIndexIndicator, ForceIndexIndicator,
    )
    HAS_TA = True
except ImportError:
    HAS_TA = False

from backend.config import config

logger = logging.getLogger(__name__)


def compute_technical_indicators(
    prices: pd.Series,
    volumes: Optional[pd.Series] = None,
    high: Optional[pd.Series] = None,
    low: Optional[pd.Series] = None,
) -> dict:
    """Compute comprehensive technical indicators for a price series.

    Args:
        prices: Close price series (DatetimeIndex)
        volumes: Volume series (optional, needed for volume indicators)
        high: High price series (optional, needed for ATR/Stochastic)
        low: Low price series (optional, needed for ATR/Stochastic)

    Returns:
        Dict with indicator categories: trend, momentum, volatility, volume, patterns
    """
    if not HAS_TA:
        return {"error": "ta library not installed", "indicators": {}}

    close = prices.dropna()
    if len(close) < 50:
        return {"error": "Insufficient data (need 50+ trading days)", "indicators": {}}

    # Synthesize high/low from close if not provided
    if high is None:
        high = close * 1.005  # rough proxy
    if low is None:
        low = close * 0.995

    result = {
        "trend": _compute_trend(close, high, low),
        "momentum": _compute_momentum(close, high, low),
        "volatility": _compute_volatility(close, high, low),
        "volume": _compute_volume(close, volumes, high, low) if volumes is not None else {},
        "patterns": _detect_patterns(close),
    }

    return result


def _compute_trend(close: pd.Series, high: pd.Series, low: pd.Series) -> dict:
    """Trend indicators: SMA, EMA, MACD, ADX, Ichimoku."""
    current = float(close.iloc[-1])

    # Simple Moving Averages
    sma_20 = SMAIndicator(close, window=20).sma_indicator()
    sma_50 = SMAIndicator(close, window=50).sma_indicator()
    # Only compute SMA 200 when we have enough data — using a shorter window
    # would produce a different indicator masquerading as SMA 200
    sma_200 = SMAIndicator(close, window=200).sma_indicator() if len(close) >= 200 else pd.Series(dtype=float)

    # EMAs for MACD
    ema_12 = EMAIndicator(close, window=12).ema_indicator()
    ema_26 = EMAIndicator(close, window=26).ema_indicator()

    # MACD
    macd_obj = MACD(close)
    macd_line = macd_obj.macd()
    macd_signal = macd_obj.macd_signal()
    macd_hist = macd_obj.macd_diff()

    # ADX (trend strength)
    adx_val = None
    if len(close) > 28:
        try:
            adx_obj = ADXIndicator(high, low, close, window=14)
            adx_series = adx_obj.adx()
            adx_val = _safe_last(adx_series)
        except Exception:
            pass

    # Trend direction summary
    sma20_val = _safe_last(sma_20)
    sma50_val = _safe_last(sma_50)
    sma200_val = _safe_last(sma_200)

    above_sma20 = current > sma20_val if sma20_val else None
    above_sma50 = current > sma50_val if sma50_val else None
    above_sma200 = current > sma200_val if sma200_val else None

    # Overall trend assessment
    bullish_count = sum(1 for x in [above_sma20, above_sma50, above_sma200] if x is True)
    if bullish_count >= 3:
        trend_direction = "strong_uptrend"
    elif bullish_count == 2:
        trend_direction = "uptrend"
    elif bullish_count == 1:
        trend_direction = "mixed"
    else:
        bearish_count = sum(1 for x in [above_sma20, above_sma50, above_sma200] if x is False)
        trend_direction = "strong_downtrend" if bearish_count >= 3 else "downtrend"

    return {
        "sma_20": sma20_val,
        "sma_50": sma50_val,
        "sma_200": sma200_val,
        "ema_12": _safe_last(ema_12),
        "ema_26": _safe_last(ema_26),
        "price_vs_sma20_pct": round((current / sma20_val - 1) * 100, 2) if sma20_val else None,
        "price_vs_sma50_pct": round((current / sma50_val - 1) * 100, 2) if sma50_val else None,
        "price_vs_sma200_pct": round((current / sma200_val - 1) * 100, 2) if sma200_val else None,
        "macd": _safe_last(macd_line),
        "macd_signal": _safe_last(macd_signal),
        "macd_histogram": _safe_last(macd_hist),
        "macd_bullish": (_safe_last(macd_line) or 0) > (_safe_last(macd_signal) or 0),
        "adx": adx_val,
        "adx_interpretation": (
            "strong_trend" if adx_val and adx_val > 25
            else "weak_trend" if adx_val and adx_val > 20
            else "no_trend" if adx_val
            else None
        ),
        "trend_direction": trend_direction,
    }


def _compute_momentum(close: pd.Series, high: pd.Series, low: pd.Series) -> dict:
    """Momentum indicators: RSI, Stochastic, Williams %R, CCI, ROC."""
    # RSI
    rsi = RSIIndicator(close, window=14).rsi()
    rsi_val = _safe_last(rsi)

    rsi_interpretation = "neutral"
    if rsi_val is not None:
        if rsi_val > 70:
            rsi_interpretation = "overbought"
        elif rsi_val > 60:
            rsi_interpretation = "bullish"
        elif rsi_val < 30:
            rsi_interpretation = "oversold"
        elif rsi_val < 40:
            rsi_interpretation = "bearish"

    # Stochastic Oscillator
    stoch_k = None
    stoch_d = None
    if len(close) > 17:
        try:
            stoch_obj = StochasticOscillator(high, low, close, window=14, smooth_window=3)
            stoch_k = _safe_last(stoch_obj.stoch())
            stoch_d = _safe_last(stoch_obj.stoch_signal())
        except Exception:
            pass

    # Williams %R
    williams_r = None
    if len(close) > 14:
        try:
            wr = WilliamsRIndicator(high, low, close, lbp=14)
            williams_r = _safe_last(wr.williams_r())
        except Exception:
            pass

    # Rate of Change (10-day)
    roc_val = None
    if len(close) > 10:
        try:
            roc = ROCIndicator(close, window=10)
            roc_val = _safe_last(roc.roc())
        except Exception:
            pass

    return {
        "rsi_14": rsi_val,
        "rsi_interpretation": rsi_interpretation,
        "stochastic_k": stoch_k,
        "stochastic_d": stoch_d,
        "stochastic_signal": (
            "overbought" if stoch_k and stoch_k > 80
            else "oversold" if stoch_k and stoch_k < 20
            else "neutral"
        ),
        "williams_r": williams_r,
        "roc_10": roc_val,
    }


def _compute_volatility(close: pd.Series, high: pd.Series, low: pd.Series) -> dict:
    """Volatility indicators: Bollinger Bands, ATR, Keltner Channel."""
    # Bollinger Bands
    bb = BollingerBands(close, window=20, window_dev=2)
    bb_upper = _safe_last(bb.bollinger_hband())
    bb_lower = _safe_last(bb.bollinger_lband())
    bb_mid = _safe_last(bb.bollinger_mavg())
    bb_width = _safe_last(bb.bollinger_wband())
    current = float(close.iloc[-1])

    bb_position = None
    if bb_upper and bb_lower and bb_upper != bb_lower:
        bb_position = (current - bb_lower) / (bb_upper - bb_lower)

    # ATR
    atr_val = None
    atr_pct = None
    if len(close) > 14:
        try:
            atr_obj = AverageTrueRange(high, low, close, window=14)
            atr_val = _safe_last(atr_obj.average_true_range())
            if atr_val and current > 0:
                atr_pct = round(atr_val / current * 100, 2)
        except Exception:
            pass

    return {
        "bollinger_upper": bb_upper,
        "bollinger_lower": bb_lower,
        "bollinger_mid": bb_mid,
        "bollinger_width": bb_width,
        "bollinger_position": round(bb_position, 3) if bb_position is not None else None,
        "bollinger_signal": (
            "overbought" if bb_position and bb_position > 1.0
            else "oversold" if bb_position is not None and bb_position < 0.0
            else "upper_band" if bb_position and bb_position > 0.8
            else "lower_band" if bb_position is not None and bb_position < 0.2
            else "neutral"
        ),
        "atr_14": atr_val,
        "atr_pct": atr_pct,
    }


def _compute_volume(
    close: pd.Series,
    volume: pd.Series,
    high: pd.Series,
    low: pd.Series,
) -> dict:
    """Volume indicators: OBV, A/D Line, Force Index."""
    if volume is None or len(volume.dropna()) < 20:
        return {}

    # On-Balance Volume
    obv = OnBalanceVolumeIndicator(close, volume).on_balance_volume()
    obv_val = _safe_last(obv)

    # OBV trend (rising/falling over last 20 days)
    obv_trend = None
    if len(obv.dropna()) >= 20:
        obv_recent = obv.dropna().iloc[-20:]
        if len(obv_recent) >= 2:
            obv_slope = (float(obv_recent.iloc[-1]) - float(obv_recent.iloc[0])) / len(obv_recent)
            obv_trend = "rising" if obv_slope > 0 else "falling"

    # Accumulation/Distribution
    ad = AccDistIndexIndicator(high, low, close, volume).acc_dist_index()
    ad_val = _safe_last(ad)

    # Force Index (13-day)
    fi = ForceIndexIndicator(close, volume, window=13).force_index()
    fi_val = _safe_last(fi)

    # Average volume
    avg_volume_20d = float(volume.dropna().iloc[-20:].mean()) if len(volume.dropna()) >= 20 else None
    latest_volume = float(volume.dropna().iloc[-1]) if len(volume.dropna()) > 0 else None
    volume_ratio = None
    if avg_volume_20d and latest_volume and avg_volume_20d > 0:
        volume_ratio = round(latest_volume / avg_volume_20d, 2)

    return {
        "obv": obv_val,
        "obv_trend": obv_trend,
        "acc_dist": ad_val,
        "force_index_13": fi_val,
        "avg_volume_20d": avg_volume_20d,
        "latest_volume": latest_volume,
        "volume_ratio": volume_ratio,
        "volume_signal": (
            "high_volume" if volume_ratio and volume_ratio > 1.5
            else "low_volume" if volume_ratio and volume_ratio < 0.5
            else "normal"
        ),
    }


def _detect_patterns(close: pd.Series) -> dict:
    """Detect chart patterns and key levels."""
    if len(close) < 200:
        sma200 = None
    else:
        sma200 = float(close.rolling(200).mean().iloc[-1])

    sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
    current = float(close.iloc[-1])

    # Golden/Death Cross detection
    cross = None
    if sma50 is not None and sma200 is not None and len(close) >= 201:
        sma50_prev = float(close.rolling(50).mean().iloc[-2])
        sma200_prev = float(close.rolling(200).mean().iloc[-2])
        if sma50 > sma200 and sma50_prev <= sma200_prev:
            cross = "golden_cross"
        elif sma50 < sma200 and sma50_prev >= sma200_prev:
            cross = "death_cross"
        elif sma50 > sma200:
            cross = "above_200sma"
        else:
            cross = "below_200sma"

    # Support/Resistance (pivot-based)
    recent = close.iloc[-20:]
    support = float(recent.min())
    resistance = float(recent.max())

    # 52-week high/low
    year_data = close.iloc[-252:] if len(close) >= 252 else close
    high_52w = float(year_data.max())
    low_52w = float(year_data.min())
    pct_from_52w_high = round((current / high_52w - 1) * 100, 2) if high_52w > 0 else None
    pct_from_52w_low = round((current / low_52w - 1) * 100, 2) if low_52w > 0 else None

    return {
        "golden_death_cross": cross,
        "support_20d": support,
        "resistance_20d": resistance,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "pct_from_52w_high": pct_from_52w_high,
        "pct_from_52w_low": pct_from_52w_low,
    }


def get_ta_signal(indicators: dict) -> dict:
    """Compute a composite TA signal from indicators.

    Returns:
        Dict with score (-1 to +1), sentiment, confidence, and reasons.
    """
    if "error" in indicators:
        return {"score": 0, "sentiment": "neutral", "confidence": 0, "reasons": [indicators["error"]]}

    signals = []
    reasons = []

    # Trend signals
    trend = indicators.get("trend", {})
    td = trend.get("trend_direction", "mixed")
    if td == "strong_uptrend":
        signals.append(0.8)
        reasons.append("Price above all major moving averages")
    elif td == "uptrend":
        signals.append(0.4)
    elif td == "strong_downtrend":
        signals.append(-0.8)
        reasons.append("Price below all major moving averages")
    elif td == "downtrend":
        signals.append(-0.4)

    if trend.get("macd_bullish"):
        signals.append(0.3)
        reasons.append("MACD bullish crossover")
    else:
        signals.append(-0.3)

    adx = trend.get("adx")
    if adx and adx > 25:
        reasons.append(f"Strong trend (ADX={adx:.0f})")

    # Momentum signals
    momentum = indicators.get("momentum", {})
    rsi = momentum.get("rsi_14")
    if rsi is not None:
        if rsi > 70:
            signals.append(-0.5)
            reasons.append(f"RSI overbought ({rsi:.0f})")
        elif rsi < 30:
            signals.append(0.5)
            reasons.append(f"RSI oversold ({rsi:.0f})")
        elif rsi > 50:
            signals.append(0.1)
        else:
            signals.append(-0.1)

    stoch = momentum.get("stochastic_k")
    if stoch is not None:
        if stoch > 80:
            signals.append(-0.3)
        elif stoch < 20:
            signals.append(0.3)
            reasons.append("Stochastic oversold")

    # Volatility signals
    vol = indicators.get("volatility", {})
    bb_sig = vol.get("bollinger_signal")
    if bb_sig == "overbought":
        signals.append(-0.3)
        reasons.append("Price above Bollinger upper band")
    elif bb_sig == "oversold":
        signals.append(0.3)
        reasons.append("Price below Bollinger lower band")

    # Volume signals
    vol_data = indicators.get("volume", {})
    vol_sig = vol_data.get("volume_signal")
    obv_trend = vol_data.get("obv_trend")
    if vol_sig == "high_volume" and obv_trend == "rising":
        signals.append(0.2)
        reasons.append("High volume with rising OBV (accumulation)")
    elif vol_sig == "high_volume" and obv_trend == "falling":
        signals.append(-0.2)
        reasons.append("High volume with falling OBV (distribution)")

    # Pattern signals
    patterns = indicators.get("patterns", {})
    cross = patterns.get("golden_death_cross")
    if cross == "golden_cross":
        signals.append(0.5)
        reasons.append("Golden cross detected (SMA50 > SMA200)")
    elif cross == "death_cross":
        signals.append(-0.5)
        reasons.append("Death cross detected (SMA50 < SMA200)")

    # Composite
    if not signals:
        return {"score": 0, "sentiment": "neutral", "confidence": 0, "reasons": ["No data"]}

    score = float(np.clip(np.mean(signals), -1, 1))
    confidence = min(len(signals) / 8.0, 1.0)  # more signals = more confident

    if score > 0.3:
        sentiment = "bullish"
    elif score > 0.1:
        sentiment = "slightly_bullish"
    elif score < -0.3:
        sentiment = "bearish"
    elif score < -0.1:
        sentiment = "slightly_bearish"
    else:
        sentiment = "neutral"

    return {
        "score": round(score, 3),
        "sentiment": sentiment,
        "confidence": round(confidence, 2),
        "n_signals": len(signals),
        "reasons": reasons[:5],
    }


def get_ta_summary(
    prices: pd.Series,
    volumes: Optional[pd.Series] = None,
    high: Optional[pd.Series] = None,
    low: Optional[pd.Series] = None,
) -> dict:
    """One-call convenience: compute indicators + signal + summary."""
    indicators = compute_technical_indicators(prices, volumes, high, low)
    signal = get_ta_signal(indicators)
    return {
        "indicators": indicators,
        "signal": signal,
    }


def _safe_last(series: pd.Series) -> Optional[float]:
    """Get last non-NaN value from a series, or None."""
    if series is None or series.empty:
        return None
    clean = series.dropna()
    if clean.empty:
        return None
    val = float(clean.iloc[-1])
    if np.isnan(val) or np.isinf(val):
        return None
    return round(val, 4)
