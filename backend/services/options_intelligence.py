"""
Aegis Finance — Options-Implied Intelligence
===============================================

Extracts forward-looking market signals from options data:
  - Implied Volatility (IV) surface & skew
  - Put/Call ratio (volume and open interest)
  - VIX term structure (contango/backwardation)
  - IV rank and percentile (relative to 1-year history)

Options data is the only truly forward-looking market signal — it reflects
what traders are PAYING for protection vs upside. Bloomberg Terminal's edge
over retail tools comes largely from options intelligence.

Data source: yfinance options chains (free, no API key needed)

Usage:
    from backend.services.options_intelligence import (
        get_options_summary,
        get_vix_term_structure,
        get_iv_signal,
    )
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from backend.config import config

logger = logging.getLogger(__name__)


def get_options_summary(ticker: str) -> dict:
    """Compute options-derived intelligence for a single ticker.

    Fetches the nearest two expiration chains and computes:
    - Implied volatility skew (put IV vs call IV)
    - Put/call ratio (volume-weighted)
    - At-the-money IV
    - IV rank vs recent history

    Args:
        ticker: Stock ticker symbol

    Returns:
        Dict with options intelligence metrics
    """
    try:
        import yfinance as yf
    except ImportError:
        return {"error": "yfinance not installed"}

    try:
        stock = yf.Ticker(ticker)
        expirations = stock.options

        if not expirations or len(expirations) == 0:
            return {"error": f"No options data for {ticker}", "ticker": ticker}

        # Get nearest expiration (short-term) and ~30-60 day expiration
        today = datetime.now()
        exp_dates = [datetime.strptime(e, "%Y-%m-%d") for e in expirations]
        # Filter out expired
        future_exps = [(e, s) for e, s in zip(exp_dates, expirations) if e > today]

        if len(future_exps) < 1:
            return {"error": "No future expirations available", "ticker": ticker}

        # Pick nearest and ~30-day
        nearest_exp_str = future_exps[0][1]
        mid_exp_str = None
        for exp_date, exp_str in future_exps:
            days_to_exp = (exp_date - today).days
            if 25 <= days_to_exp <= 60:
                mid_exp_str = exp_str
                break

        if mid_exp_str is None and len(future_exps) > 1:
            mid_exp_str = future_exps[min(1, len(future_exps) - 1)][1]

        # Get current price
        info = stock.info
        current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        if current_price <= 0:
            hist = stock.history(period="1d")
            if not hist.empty:
                current_price = float(hist["Close"].iloc[-1])

        if current_price <= 0:
            return {"error": "Could not determine current price", "ticker": ticker}

        # Fetch chains
        chain_near = stock.option_chain(nearest_exp_str)
        chain_mid = stock.option_chain(mid_exp_str) if mid_exp_str else None

        # Compute metrics from nearest chain
        calls = chain_near.calls
        puts = chain_near.puts

        result = _analyze_chain(
            calls, puts, current_price, nearest_exp_str, ticker
        )

        # Add mid-term chain if available
        if chain_mid is not None:
            mid_result = _analyze_chain(
                chain_mid.calls, chain_mid.puts, current_price, mid_exp_str, ticker
            )
            result["mid_term"] = {
                "expiration": mid_exp_str,
                "atm_iv_call": mid_result.get("atm_iv_call"),
                "atm_iv_put": mid_result.get("atm_iv_put"),
                "put_call_volume_ratio": mid_result.get("put_call_volume_ratio"),
                "iv_skew": mid_result.get("iv_skew"),
            }

            # IV term structure: compare near vs mid
            near_atm = result.get("atm_iv_call")
            mid_atm = mid_result.get("atm_iv_call")
            if near_atm and mid_atm and mid_atm > 0:
                result["iv_term_structure"] = {
                    "near_iv": near_atm,
                    "mid_iv": mid_atm,
                    "slope": round(mid_atm - near_atm, 4),
                    "contango": mid_atm > near_atm,
                    "interpretation": (
                        "Normal (contango) — market expects stable vol"
                        if mid_atm > near_atm
                        else "Inverted (backwardation) — near-term fear elevated"
                    ),
                }

        # Compute IV rank using historical volatility as proxy
        try:
            hist_data = stock.history(period="1y")
            if len(hist_data) > 20:
                daily_rets = hist_data["Close"].pct_change().dropna()
                realized_vol = float(daily_rets.std() * np.sqrt(252))
                # Rolling 20-day realized vol over the year
                rolling_vol = daily_rets.rolling(20).std() * np.sqrt(252)
                rolling_vol = rolling_vol.dropna()

                if len(rolling_vol) > 0 and result.get("atm_iv_call"):
                    atm_iv = result["atm_iv_call"]
                    vol_min = float(rolling_vol.min())
                    vol_max = float(rolling_vol.max())
                    if vol_max > vol_min:
                        iv_rank = (atm_iv - vol_min) / (vol_max - vol_min)
                        iv_percentile = float(
                            (rolling_vol < atm_iv).mean()
                        )
                        result["iv_rank"] = round(float(np.clip(iv_rank, 0, 1)) * 100, 1)
                        result["iv_percentile"] = round(iv_percentile * 100, 1)
                        result["realized_vol_1y"] = round(realized_vol * 100, 1)
                        result["iv_vs_rv"] = round(
                            (atm_iv / max(realized_vol, 0.001) - 1) * 100, 1
                        )
        except Exception as e:
            logger.warning("IV rank calculation failed for %s: %s", ticker, e)

        # Generate signal
        result["signal"] = _generate_options_signal(result)

        return result

    except Exception as e:
        logger.warning("Options analysis failed for %s: %s", ticker, e)
        return {"error": str(e), "ticker": ticker}


def _analyze_chain(
    calls: pd.DataFrame,
    puts: pd.DataFrame,
    current_price: float,
    expiration: str,
    ticker: str,
) -> dict:
    """Analyze a single options chain (calls + puts) for one expiration."""
    result = {"ticker": ticker, "expiration": expiration, "current_price": round(current_price, 2)}

    # Filter valid data
    calls = calls[calls["impliedVolatility"] > 0].copy()
    puts = puts[puts["impliedVolatility"] > 0].copy()

    if calls.empty and puts.empty:
        result["error"] = "No valid IV data in chain"
        return result

    # ATM options: strikes within 3% of current price
    atm_range = current_price * 0.03
    atm_calls = calls[abs(calls["strike"] - current_price) <= atm_range]
    atm_puts = puts[abs(puts["strike"] - current_price) <= atm_range]

    # ATM Implied Volatility
    if not atm_calls.empty:
        result["atm_iv_call"] = round(float(atm_calls["impliedVolatility"].mean()), 4)
    if not atm_puts.empty:
        result["atm_iv_put"] = round(float(atm_puts["impliedVolatility"].mean()), 4)

    # IV Skew: OTM put IV vs OTM call IV
    # Higher skew = more demand for downside protection = bearish
    otm_puts = puts[puts["strike"] < current_price * 0.95]
    otm_calls = calls[calls["strike"] > current_price * 1.05]

    if not otm_puts.empty and not otm_calls.empty:
        put_iv = float(otm_puts["impliedVolatility"].mean())
        call_iv = float(otm_calls["impliedVolatility"].mean())
        if call_iv > 0:
            skew = put_iv / call_iv
            result["iv_skew"] = round(skew, 3)
            result["iv_skew_interpretation"] = (
                "Strong demand for downside protection (bearish)"
                if skew > 1.3
                else "Elevated put demand"
                if skew > 1.1
                else "Balanced"
                if skew > 0.9
                else "Call-heavy (bullish speculation)"
            )

    # Put/Call Ratio (volume)
    total_call_vol = int(calls["volume"].fillna(0).sum())
    total_put_vol = int(puts["volume"].fillna(0).sum())
    if total_call_vol > 0:
        pc_vol_ratio = total_put_vol / total_call_vol
        result["put_call_volume_ratio"] = round(pc_vol_ratio, 3)
        result["total_call_volume"] = total_call_vol
        result["total_put_volume"] = total_put_vol

    # Put/Call Ratio (open interest)
    total_call_oi = int(calls["openInterest"].fillna(0).sum())
    total_put_oi = int(puts["openInterest"].fillna(0).sum())
    if total_call_oi > 0:
        pc_oi_ratio = total_put_oi / total_call_oi
        result["put_call_oi_ratio"] = round(pc_oi_ratio, 3)
        result["total_call_oi"] = total_call_oi
        result["total_put_oi"] = total_put_oi

    # Max pain: strike with maximum combined open interest value
    if not calls.empty and not puts.empty:
        try:
            all_strikes = sorted(
                set(calls["strike"].tolist() + puts["strike"].tolist())
            )
            max_pain_strike = None
            min_total_intrinsic = float("inf")

            for strike in all_strikes:
                # Total intrinsic value at this strike for all options
                call_intrinsic = calls.apply(
                    lambda r: max(0, strike - r["strike"]) * r.get("openInterest", 0),
                    axis=1,
                ).sum()
                put_intrinsic = puts.apply(
                    lambda r: max(0, r["strike"] - strike) * r.get("openInterest", 0),
                    axis=1,
                ).sum()
                total = call_intrinsic + put_intrinsic
                if total < min_total_intrinsic:
                    min_total_intrinsic = total
                    max_pain_strike = strike

            if max_pain_strike is not None:
                result["max_pain"] = round(float(max_pain_strike), 2)
                result["max_pain_distance_pct"] = round(
                    (max_pain_strike / current_price - 1) * 100, 2
                )
        except Exception:
            pass

    return result


def _generate_options_signal(data: dict) -> dict:
    """Generate a composite signal from options data.

    Returns a score from -1 (very bearish) to +1 (very bullish) with reasoning.
    """
    score = 0.0
    reasons = []
    n_signals = 0

    # IV Skew signal
    skew = data.get("iv_skew")
    if skew is not None:
        n_signals += 1
        if skew > 1.4:
            score -= 0.3
            reasons.append(f"Heavy put skew ({skew:.2f}) — institutional hedging")
        elif skew > 1.2:
            score -= 0.15
            reasons.append(f"Elevated put skew ({skew:.2f})")
        elif skew < 0.8:
            score += 0.2
            reasons.append(f"Call-heavy skew ({skew:.2f}) — bullish speculation")
        else:
            reasons.append(f"Normal IV skew ({skew:.2f})")

    # Put/Call ratio signal
    pcr = data.get("put_call_volume_ratio")
    if pcr is not None:
        n_signals += 1
        if pcr > 1.5:
            # Extreme put buying can be contrarian bullish
            score += 0.15
            reasons.append(f"Extreme P/C ratio ({pcr:.2f}) — contrarian bullish")
        elif pcr > 1.0:
            score -= 0.15
            reasons.append(f"Elevated P/C ratio ({pcr:.2f}) — bearish sentiment")
        elif pcr < 0.5:
            score -= 0.1  # Extreme call buying = complacency
            reasons.append(f"Low P/C ratio ({pcr:.2f}) — complacency risk")
        else:
            score += 0.05
            reasons.append(f"Balanced P/C ratio ({pcr:.2f})")

    # IV rank signal
    iv_rank = data.get("iv_rank")
    if iv_rank is not None:
        n_signals += 1
        if iv_rank > 80:
            score -= 0.2
            reasons.append(f"IV rank high ({iv_rank:.0f}%) — elevated fear")
        elif iv_rank > 60:
            score -= 0.1
        elif iv_rank < 20:
            score += 0.15
            reasons.append(f"IV rank low ({iv_rank:.0f}%) — complacency/calm")
        elif iv_rank < 40:
            score += 0.05

    # IV vs realized vol signal
    iv_vs_rv = data.get("iv_vs_rv")
    if iv_vs_rv is not None:
        n_signals += 1
        if iv_vs_rv > 30:
            score -= 0.15
            reasons.append(f"IV premium +{iv_vs_rv:.0f}% over realized — expensive protection")
        elif iv_vs_rv < -15:
            score += 0.1
            reasons.append(f"IV discount {iv_vs_rv:.0f}% vs realized — cheap protection")

    # IV term structure signal
    ts = data.get("iv_term_structure")
    if ts is not None:
        n_signals += 1
        if not ts["contango"]:
            score -= 0.2
            reasons.append("IV term structure inverted — near-term fear")
        else:
            score += 0.05

    # Max pain gravity
    max_pain_dist = data.get("max_pain_distance_pct")
    if max_pain_dist is not None:
        n_signals += 1
        if abs(max_pain_dist) > 5:
            if max_pain_dist > 0:
                score += 0.1
                reasons.append(f"Max pain {max_pain_dist:+.1f}% above — potential magnet up")
            else:
                score -= 0.1
                reasons.append(f"Max pain {max_pain_dist:+.1f}% below — potential magnet down")

    score = float(np.clip(score, -1.0, 1.0))

    # Determine sentiment
    if score > 0.2:
        sentiment = "bullish"
    elif score > 0.05:
        sentiment = "slightly_bullish"
    elif score < -0.2:
        sentiment = "bearish"
    elif score < -0.05:
        sentiment = "slightly_bearish"
    else:
        sentiment = "neutral"

    return {
        "score": round(score, 3),
        "sentiment": sentiment,
        "confidence": min(n_signals * 15, 100),
        "n_signals": n_signals,
        "reasons": reasons[:4],
    }


def get_vix_term_structure() -> dict:
    """Fetch VIX term structure (VIX vs VIX3M vs VIX6M).

    Contango (VIX < VIX3M < VIX6M) = normal, calm markets
    Backwardation (VIX > VIX3M) = near-term fear, often precedes volatility events

    Returns:
        Dict with VIX levels, term structure shape, and signal
    """
    try:
        import yfinance as yf

        # Fetch VIX indices
        tickers_to_fetch = {
            "VIX": "^VIX",
            "VIX3M": "^VIX3M",
            "VIX9D": "^VIX9D",
        }

        values = {}
        for name, ticker in tickers_to_fetch.items():
            try:
                data = yf.download(ticker, period="5d", progress=False)
                if not data.empty:
                    close = data["Close"]
                    if isinstance(close, pd.DataFrame):
                        close = close.iloc[:, 0]
                    values[name] = float(close.iloc[-1])
            except Exception:
                pass

        if "VIX" not in values:
            return {"error": "Could not fetch VIX data"}

        result = {"values": values}

        # Term structure analysis
        vix = values["VIX"]
        vix3m = values.get("VIX3M")

        if vix3m is not None:
            ratio = vix / vix3m
            result["vix_vix3m_ratio"] = round(ratio, 3)
            result["contango"] = ratio < 1.0
            result["backwardation"] = ratio > 1.0

            if ratio > 1.1:
                result["structure"] = "strong_backwardation"
                result["signal"] = "bearish"
                result["interpretation"] = (
                    f"VIX ({vix:.1f}) >> VIX3M ({vix3m:.1f}) — "
                    "severe near-term stress, historically precedes selloffs"
                )
            elif ratio > 1.0:
                result["structure"] = "mild_backwardation"
                result["signal"] = "slightly_bearish"
                result["interpretation"] = (
                    f"VIX ({vix:.1f}) > VIX3M ({vix3m:.1f}) — "
                    "elevated near-term concern"
                )
            elif ratio > 0.85:
                result["structure"] = "normal_contango"
                result["signal"] = "neutral"
                result["interpretation"] = (
                    f"Normal term structure: VIX ({vix:.1f}) < VIX3M ({vix3m:.1f})"
                )
            else:
                result["structure"] = "steep_contango"
                result["signal"] = "bullish"
                result["interpretation"] = (
                    f"Steep contango: VIX ({vix:.1f}) << VIX3M ({vix3m:.1f}) — "
                    "extreme complacency or strong trend"
                )

        # VIX level assessment
        if vix > 35:
            result["vix_level"] = "extreme_fear"
        elif vix > 25:
            result["vix_level"] = "elevated"
        elif vix > 18:
            result["vix_level"] = "normal"
        elif vix > 12:
            result["vix_level"] = "calm"
        else:
            result["vix_level"] = "extreme_calm"

        # VIX 9-day vs 30-day (ultra-short-term stress)
        vix9d = values.get("VIX9D")
        if vix9d is not None:
            result["vix9d_vix_ratio"] = round(vix9d / vix, 3)
            if vix9d / vix > 1.1:
                result["ultra_short_term"] = "spike — event-driven fear"

        return result

    except Exception as e:
        logger.warning("VIX term structure failed: %s", e)
        return {"error": str(e)}


def get_iv_signal(ticker: str) -> dict:
    """Quick IV-based signal for use in the signal engine.

    Returns a simplified score that can be integrated into the composite signal.
    """
    summary = get_options_summary(ticker)
    if "error" in summary and "signal" not in summary:
        return {"score": 0.0, "available": False}

    signal = summary.get("signal", {})
    return {
        "score": signal.get("score", 0.0),
        "sentiment": signal.get("sentiment", "neutral"),
        "iv_skew": summary.get("iv_skew"),
        "put_call_ratio": summary.get("put_call_volume_ratio"),
        "iv_rank": summary.get("iv_rank"),
        "available": True,
    }
