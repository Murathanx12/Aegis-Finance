"""
Aegis Finance — Earnings Intelligence
========================================

Extracts earnings-related signals for individual stocks:
  - Next earnings date and countdown
  - Historical earnings surprise track record
  - Revenue/EPS growth trajectory
  - Estimate revision momentum (analysts raising/lowering estimates)

Earnings events are the single largest source of stock-level volatility.
Institutional desks track every metric here; retail tools rarely surface this.

Data source: yfinance (Ticker.earnings, calendar, analysis)

Usage:
    from backend.services.earnings_intelligence import get_earnings_summary
"""

import logging
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

from backend.config import config

logger = logging.getLogger(__name__)


def get_earnings_summary(ticker: str) -> dict:
    """Comprehensive earnings intelligence for a single stock.

    Returns:
        Dict with earnings dates, surprise history, growth metrics, and signal
    """
    try:
        import yfinance as yf
    except ImportError:
        return {"error": "yfinance not installed"}

    try:
        stock = yf.Ticker(ticker)
        result = {"ticker": ticker}

        # 1. Earnings calendar — next earnings date
        try:
            calendar = stock.calendar
            if calendar is not None:
                if isinstance(calendar, dict):
                    earnings_date = calendar.get("Earnings Date")
                    if isinstance(earnings_date, list) and len(earnings_date) > 0:
                        next_date = earnings_date[0]
                        if hasattr(next_date, 'strftime'):
                            result["next_earnings_date"] = next_date.strftime("%Y-%m-%d")
                            days_until = (next_date - datetime.now()).days
                            result["days_until_earnings"] = max(0, days_until)
                            if 0 <= days_until <= 14:
                                result["earnings_imminent"] = True
                    elif isinstance(earnings_date, (datetime, pd.Timestamp)):
                        result["next_earnings_date"] = earnings_date.strftime("%Y-%m-%d")
                        days_until = (earnings_date - datetime.now()).days
                        result["days_until_earnings"] = max(0, days_until)
                        if 0 <= days_until <= 14:
                            result["earnings_imminent"] = True

                    # Revenue/EPS estimates
                    if "Revenue Estimate" in calendar:
                        result["revenue_estimate"] = calendar["Revenue Estimate"]
                    if "EPS Estimate" in calendar:
                        result["eps_estimate"] = calendar["EPS Estimate"]
        except Exception as e:
            logger.debug("Calendar fetch failed for %s: %s", ticker, e)

        # 2. Earnings history — surprise track record
        try:
            earnings_hist = stock.earnings_history
            if earnings_hist is not None and not earnings_hist.empty:
                # Recent surprises
                recent = earnings_hist.tail(8)  # Last 2 years of quarterly earnings
                surprises = []
                beat_count = 0
                miss_count = 0

                for _, row in recent.iterrows():
                    eps_actual = row.get("epsActual")
                    eps_estimate = row.get("epsEstimate")
                    if eps_actual is not None and eps_estimate is not None and eps_estimate != 0:
                        surprise_pct = (eps_actual - eps_estimate) / abs(eps_estimate) * 100
                        beat = eps_actual > eps_estimate
                        if beat:
                            beat_count += 1
                        else:
                            miss_count += 1
                        surprises.append({
                            "quarter": str(row.get("quarter", "")),
                            "eps_actual": round(float(eps_actual), 3),
                            "eps_estimate": round(float(eps_estimate), 3),
                            "surprise_pct": round(float(surprise_pct), 1),
                            "beat": beat,
                        })

                if surprises:
                    result["earnings_surprises"] = surprises
                    result["beat_rate"] = round(beat_count / (beat_count + miss_count) * 100, 0)
                    result["avg_surprise_pct"] = round(
                        float(np.mean([s["surprise_pct"] for s in surprises])), 1
                    )
                    # Trend: are surprises getting better or worse?
                    if len(surprises) >= 4:
                        first_half = np.mean([s["surprise_pct"] for s in surprises[:len(surprises)//2]])
                        second_half = np.mean([s["surprise_pct"] for s in surprises[len(surprises)//2:]])
                        result["surprise_trend"] = (
                            "improving" if second_half > first_half + 2
                            else "declining" if second_half < first_half - 2
                            else "stable"
                        )
        except Exception as e:
            logger.debug("Earnings history failed for %s: %s", ticker, e)

        # 3. Revenue & earnings growth
        try:
            financials = stock.quarterly_financials
            if financials is not None and not financials.empty:
                if "Total Revenue" in financials.index:
                    rev = financials.loc["Total Revenue"].dropna().sort_index()
                    if len(rev) >= 4:
                        # YoY revenue growth (latest quarter vs same quarter last year)
                        yoy_growth = (float(rev.iloc[-1]) / float(rev.iloc[-4]) - 1) * 100
                        result["revenue_yoy_growth"] = round(yoy_growth, 1)
                        # QoQ growth
                        qoq_growth = (float(rev.iloc[-1]) / float(rev.iloc[-2]) - 1) * 100
                        result["revenue_qoq_growth"] = round(qoq_growth, 1)

                if "Net Income" in financials.index:
                    ni = financials.loc["Net Income"].dropna().sort_index()
                    if len(ni) >= 4:
                        current = float(ni.iloc[-1])
                        prev = float(ni.iloc[-4])
                        if prev > 0:
                            earnings_growth = (current / prev - 1) * 100
                            result["earnings_yoy_growth"] = round(earnings_growth, 1)
                        elif prev < 0 and current > 0:
                            result["earnings_yoy_growth"] = None
                            result["earnings_turnaround"] = True
        except Exception as e:
            logger.debug("Financials failed for %s: %s", ticker, e)

        # 4. Analyst estimates & revision momentum
        try:
            analysis = stock.analyst_price_targets
            if analysis is not None:
                if isinstance(analysis, dict):
                    result["analyst_targets"] = {
                        "current": analysis.get("current"),
                        "low": analysis.get("low"),
                        "high": analysis.get("high"),
                        "mean": analysis.get("mean"),
                        "median": analysis.get("median"),
                    }
                elif isinstance(analysis, pd.DataFrame) and not analysis.empty:
                    result["analyst_targets"] = {
                        "current": _safe_float(analysis, "current"),
                        "low": _safe_float(analysis, "low"),
                        "high": _safe_float(analysis, "high"),
                        "mean": _safe_float(analysis, "mean"),
                        "median": _safe_float(analysis, "median"),
                    }
        except Exception as e:
            logger.debug("Analyst targets failed for %s: %s", ticker, e)

        # 5. Recommendations trend
        try:
            recs = stock.recommendations
            if recs is not None and not recs.empty:
                recent_recs = recs.tail(10)
                if not recent_recs.empty:
                    # Count recommendation types
                    grade_counts = {}
                    for _, row in recent_recs.iterrows():
                        grade = row.get("To Grade", row.get("toGrade", ""))
                        if grade:
                            grade_lower = str(grade).lower()
                            if any(w in grade_lower for w in ["buy", "overweight", "outperform"]):
                                grade_counts["buy"] = grade_counts.get("buy", 0) + 1
                            elif any(w in grade_lower for w in ["sell", "underweight", "underperform"]):
                                grade_counts["sell"] = grade_counts.get("sell", 0) + 1
                            else:
                                grade_counts["hold"] = grade_counts.get("hold", 0) + 1

                    result["recent_recommendations"] = grade_counts
        except Exception as e:
            logger.debug("Recommendations failed for %s: %s", ticker, e)

        # 6. Key financial ratios
        try:
            info = stock.info
            result["fundamentals"] = {}
            for key in ["trailingPE", "forwardPE", "trailingEps", "forwardEps",
                        "priceToBook", "priceToSalesTrailing12Months",
                        "returnOnEquity", "debtToEquity", "freeCashflow",
                        "profitMargins", "revenueGrowth", "earningsGrowth",
                        "dividendYield", "payoutRatio"]:
                val = info.get(key)
                if val is not None:
                    result["fundamentals"][key] = (
                        round(float(val), 3) if isinstance(val, (int, float)) else val
                    )
        except Exception as e:
            logger.debug("Info failed for %s: %s", ticker, e)

        # Generate composite signal
        result["signal"] = _generate_earnings_signal(result)

        return result

    except Exception as e:
        logger.warning("Earnings analysis failed for %s: %s", ticker, e)
        return {"error": str(e), "ticker": ticker}


def _safe_float(df, col):
    """Safely extract a float from a DataFrame column."""
    try:
        if col in df.columns:
            val = df[col].iloc[0]
            return round(float(val), 2) if pd.notna(val) else None
        return None
    except Exception:
        return None


def _generate_earnings_signal(data: dict) -> dict:
    """Generate a composite earnings signal."""
    score = 0.0
    reasons = []
    n_signals = 0

    # Beat rate
    beat_rate = data.get("beat_rate")
    if beat_rate is not None:
        n_signals += 1
        if beat_rate >= 87.5:  # 7/8 or better
            score += 0.25
            reasons.append(f"Strong earnings beat rate ({beat_rate:.0f}%)")
        elif beat_rate >= 62.5:  # 5/8 or better
            score += 0.1
        elif beat_rate <= 37.5:  # 3/8 or worse
            score -= 0.2
            reasons.append(f"Poor earnings track record ({beat_rate:.0f}% beat rate)")

    # Average surprise magnitude
    avg_surprise = data.get("avg_surprise_pct")
    if avg_surprise is not None:
        n_signals += 1
        if avg_surprise > 10:
            score += 0.2
            reasons.append(f"Large avg earnings surprise (+{avg_surprise:.0f}%)")
        elif avg_surprise > 3:
            score += 0.1
        elif avg_surprise < -5:
            score -= 0.2
            reasons.append(f"Negative avg earnings surprise ({avg_surprise:.0f}%)")

    # Surprise trend
    trend = data.get("surprise_trend")
    if trend == "improving":
        n_signals += 1
        score += 0.15
        reasons.append("Earnings surprises improving trend")
    elif trend == "declining":
        n_signals += 1
        score -= 0.15
        reasons.append("Earnings surprises declining trend")

    # Revenue growth
    rev_growth = data.get("revenue_yoy_growth")
    if rev_growth is not None:
        n_signals += 1
        if rev_growth > 20:
            score += 0.2
            reasons.append(f"Strong revenue growth (+{rev_growth:.0f}% YoY)")
        elif rev_growth > 5:
            score += 0.1
        elif rev_growth < -5:
            score -= 0.15
            reasons.append(f"Revenue declining ({rev_growth:.0f}% YoY)")

    # Earnings growth
    earnings_growth = data.get("earnings_yoy_growth")
    if earnings_growth is not None:
        n_signals += 1
        if earnings_growth > 25:
            score += 0.2
        elif earnings_growth > 10:
            score += 0.1
        elif earnings_growth < -10:
            score -= 0.15

    # Earnings imminence — flag but don't trade on it
    if data.get("earnings_imminent"):
        reasons.insert(0, f"Earnings in {data.get('days_until_earnings', '?')} days")

    score = float(np.clip(score, -1.0, 1.0))

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
