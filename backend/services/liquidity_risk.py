"""
Aegis Finance — Liquidity Risk Analytics
==========================================

Institutional-grade liquidity metrics that Bloomberg PORT / MSCI Barra provide:

1. Amihud Illiquidity Ratio: |return| / dollar_volume — measures price impact
   per unit of trading volume. Higher = less liquid = more slippage risk.
   (Amihud 2002, "Illiquidity and stock returns")

2. Roll Spread Estimator: Implicit bid-ask spread from serial covariance of
   returns. No tick data needed. (Roll 1984, "A simple implicit measure")

3. Kyle's Lambda: Price impact coefficient from volume-return regression.
   Measures how much price moves per unit of net order flow.
   (Kyle 1985, "Continuous auctions and insider trading")

4. Turnover Ratio: Volume / shares outstanding — measures trading activity
   relative to float. Low turnover = illiquid.

5. Liquidity-adjusted VaR (LVaR): Standard VaR + liquidity cost adjustment.
   Critical for realistic risk estimation on less liquid stocks.

6. Liquidity Score: Composite 0-100 score combining all metrics.

Usage:
    from backend.services.liquidity_risk import (
        compute_liquidity_metrics, compute_liquidity_score,
        compute_lvar, analyze_liquidity_universe
    )
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from backend.config import config

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────

_LIQ_CFG = config.get("liquidity_risk", {})
_LOOKBACK = _LIQ_CFG.get("lookback_days", 252)
_MIN_OBS = _LIQ_CFG.get("min_observations", 60)
_AMIHUD_WINDOW = _LIQ_CFG.get("amihud_window", 21)  # Rolling window for Amihud
_ROLL_WINDOW = _LIQ_CFG.get("roll_window", 21)       # Rolling window for Roll spread


def compute_amihud_illiquidity(
    returns: pd.Series,
    volume: pd.Series,
    price: pd.Series,
    window: int = _AMIHUD_WINDOW,
) -> pd.Series:
    """Compute Amihud (2002) illiquidity ratio: |return| / dollar_volume.

    Higher values indicate less liquid stocks (more price impact per dollar traded).
    Returns are in units of 1/$ (scaled by 1e6 for readability).

    Args:
        returns: Daily returns series
        volume: Daily volume (shares)
        price: Daily close price
        window: Rolling window for averaging

    Returns:
        Rolling average Amihud illiquidity ratio (×10⁶)
    """
    dollar_volume = volume * price
    # Avoid division by zero
    dollar_volume = dollar_volume.replace(0, np.nan)

    daily_illiq = returns.abs() / dollar_volume
    # Scale by 1e6 for readability (standard convention)
    daily_illiq = daily_illiq * 1e6

    return daily_illiq.rolling(window, min_periods=max(5, window // 4)).mean()


def compute_roll_spread(returns: pd.Series, window: int = _ROLL_WINDOW) -> pd.Series:
    """Estimate bid-ask spread from return serial covariance (Roll 1984).

    Spread = 2 * sqrt(-cov(r_t, r_{t-1})) when cov < 0.
    When cov >= 0, spread is set to 0 (no bid-ask bounce detected).

    Returns spread as a fraction (e.g., 0.002 = 0.2% = 20bps).
    """
    def _roll_estimate(r):
        if len(r) < 5:
            return np.nan
        cov = np.cov(r[1:], r[:-1])[0, 1]
        if cov < 0:
            return 2 * np.sqrt(-cov)
        return 0.0

    return returns.rolling(window, min_periods=max(5, window // 4)).apply(
        _roll_estimate, raw=True
    )


def compute_kyle_lambda(
    returns: pd.Series,
    volume: pd.Series,
    window: int = 63,
) -> pd.Series:
    """Estimate Kyle's Lambda — price impact per unit of signed volume.

    Uses OLS: |r_t| = alpha + lambda * sqrt(volume_t) + epsilon
    Lambda measures how much price moves per unit of net order flow.

    Returns lambda coefficient (higher = more price impact = less liquid).
    """
    def _kyle_estimate(idx):
        if len(idx) < 10:
            return np.nan
        r = returns.iloc[idx].values
        v = volume.iloc[idx].values
        sqrt_v = np.sqrt(v.astype(float) + 1)  # +1 to avoid sqrt(0)
        abs_r = np.abs(r)

        # Simple OLS: abs_r = a + lambda * sqrt_v
        X = np.column_stack([np.ones(len(sqrt_v)), sqrt_v])
        try:
            beta, _, _, _ = np.linalg.lstsq(X, abs_r, rcond=None)
            return max(beta[1], 0.0)  # Lambda should be non-negative
        except np.linalg.LinAlgError:
            return np.nan

    results = pd.Series(np.nan, index=returns.index)
    for i in range(window, len(returns)):
        indices = list(range(i - window, i))
        results.iloc[i] = _kyle_estimate(indices)

    return results


def compute_turnover_ratio(
    volume: pd.Series,
    shares_outstanding: float,
    window: int = 21,
) -> pd.Series:
    """Compute average daily turnover ratio: volume / shares_outstanding.

    Higher turnover = more liquid. Expressed as percentage.
    """
    if shares_outstanding <= 0:
        return pd.Series(np.nan, index=volume.index)

    daily_turnover = volume / shares_outstanding * 100  # as percentage
    return daily_turnover.rolling(window, min_periods=max(5, window // 4)).mean()


def compute_lvar(
    returns: pd.Series,
    amihud_illiq: float,
    confidence: float = 0.95,
    holding_period: int = 1,
) -> dict:
    """Compute Liquidity-adjusted Value at Risk.

    LVaR = VaR + Liquidity Cost Adjustment
    where LC = 0.5 * spread + k * sigma_spread

    This is more realistic than standard VaR for less liquid stocks where
    exit costs during stress can be substantial.
    """
    clean = returns.dropna()
    if len(clean) < 30:
        return {"var_95": None, "lvar_95": None, "liquidity_cost_bps": None}

    # Standard VaR (historical)
    var_pct = float(np.percentile(clean, (1 - confidence) * 100))

    # Multi-day adjustment (square root of time)
    var_pct *= np.sqrt(holding_period)

    # Liquidity cost: proportional to Amihud illiquidity
    # Higher Amihud → higher spread → higher exit cost
    # Empirical: ~2-5bps for mega-cap, 20-50bps for small-cap
    liq_cost = min(amihud_illiq * 5.0, 0.05)  # Cap at 5% (500bps)
    liq_cost = max(liq_cost, 0.0001)  # Floor at 1bp

    lvar = var_pct - liq_cost  # More negative = worse

    return {
        "var_95": round(float(var_pct) * 100, 2),  # as percentage
        "lvar_95": round(float(lvar) * 100, 2),
        "liquidity_cost_bps": round(float(liq_cost) * 10000, 1),
    }


def compute_liquidity_metrics(
    ticker: str,
    lookback_days: int = _LOOKBACK,
) -> Optional[dict]:
    """Compute comprehensive liquidity metrics for a stock.

    Args:
        ticker: Stock ticker symbol
        lookback_days: Number of trading days to analyze

    Returns:
        Dictionary with all liquidity metrics, or None if insufficient data.
    """
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        hist = tk.history(period="2y")

        if hist.empty or len(hist) < _MIN_OBS:
            logger.warning("%s: insufficient history for liquidity analysis (%d days)",
                           ticker, len(hist) if not hist.empty else 0)
            return None

        # Trim to lookback
        if len(hist) > lookback_days:
            hist = hist.iloc[-lookback_days:]

        close = hist["Close"]
        volume = hist["Volume"]
        returns = close.pct_change().dropna()

        # Get shares outstanding for turnover
        info = tk.info or {}
        shares_out = info.get("sharesOutstanding", 0) or 0

    except Exception as e:
        logger.warning("Failed to fetch %s for liquidity analysis: %s", ticker, e)
        return None

    # Compute metrics — align volume and close to returns index to prevent misalignment
    amihud = compute_amihud_illiquidity(returns, volume.loc[returns.index], close.loc[returns.index])
    roll_spread = compute_roll_spread(returns)

    # Current values (latest non-NaN)
    current_amihud = float(amihud.dropna().iloc[-1]) if len(amihud.dropna()) > 0 else None
    current_roll = float(roll_spread.dropna().iloc[-1]) if len(roll_spread.dropna()) > 0 else None

    # Turnover
    turnover = None
    if shares_out > 0:
        turn_series = compute_turnover_ratio(volume, shares_out)
        turnover = float(turn_series.dropna().iloc[-1]) if len(turn_series.dropna()) > 0 else None

    # Average daily dollar volume (millions)
    avg_dollar_vol = float((volume * close).tail(21).mean()) / 1e6

    # LVaR
    lvar_result = compute_lvar(returns, current_amihud or 0.0)

    # Liquidity score (0-100, higher = more liquid)
    score = compute_liquidity_score(
        amihud_illiq=current_amihud,
        roll_spread=current_roll,
        avg_dollar_volume_mm=avg_dollar_vol,
        turnover_pct=turnover,
    )

    # Amihud trend (is liquidity improving or deteriorating?)
    amihud_clean = amihud.dropna()
    if len(amihud_clean) >= 63:
        recent_amihud = float(amihud_clean.tail(21).mean())
        older_amihud = float(amihud_clean.iloc[-63:-21].mean())
        if older_amihud > 0:
            amihud_trend = (recent_amihud / older_amihud - 1) * 100
        else:
            amihud_trend = 0.0
    else:
        amihud_trend = 0.0

    return {
        "ticker": ticker,
        "lookback_days": len(hist),
        "metrics": {
            "amihud_illiquidity": round(current_amihud, 4) if current_amihud else None,
            "roll_spread_bps": round(current_roll * 10000, 1) if current_roll else None,
            "avg_dollar_volume_mm": round(avg_dollar_vol, 1),
            "daily_turnover_pct": round(turnover, 3) if turnover else None,
            "shares_outstanding_mm": round(shares_out / 1e6, 1) if shares_out else None,
        },
        "risk": {
            **lvar_result,
            "amihud_trend_pct": round(amihud_trend, 1),
            "liquidity_deteriorating": amihud_trend > 20,
        },
        "score": score,
        "interpretation": _interpret_liquidity(score, current_amihud, avg_dollar_vol),
    }


def compute_liquidity_score(
    amihud_illiq: Optional[float],
    roll_spread: Optional[float],
    avg_dollar_volume_mm: float = 0.0,
    turnover_pct: Optional[float] = None,
) -> dict:
    """Composite liquidity score (0-100).

    Scoring methodology:
    - Dollar volume: 40% weight (most objective measure)
    - Amihud illiquidity: 30% weight (price impact)
    - Roll spread: 20% weight (bid-ask estimation)
    - Turnover: 10% weight (trading activity)
    """
    scores = {}

    # Dollar volume score (log scale)
    # <$1M/day = 0, $10M = 50, $100M = 75, $1B+ = 100
    if avg_dollar_volume_mm > 0:
        dv_score = min(100, max(0, 25 * np.log10(avg_dollar_volume_mm + 1) + 25))
    else:
        dv_score = 0
    scores["dollar_volume"] = {"score": round(dv_score, 0), "weight": 0.40}

    # Amihud score (inverted — lower illiquidity = higher score)
    # Mega-cap: ~0.01, Mid-cap: ~0.1, Small-cap: ~1.0, Micro: ~10+
    if amihud_illiq is not None and amihud_illiq >= 0:
        amihud_score = max(0, 100 - 20 * np.log10(amihud_illiq * 100 + 1))
    else:
        amihud_score = 50  # neutral if unknown
    scores["amihud"] = {"score": round(amihud_score, 0), "weight": 0.30}

    # Roll spread score (lower spread = higher score)
    # <5bps = 100, 10bps = 80, 50bps = 40, 100bps+ = 0
    if roll_spread is not None:
        spread_bps = roll_spread * 10000
        spread_score = max(0, min(100, 100 - spread_bps))
    else:
        spread_score = 50
    scores["roll_spread"] = {"score": round(spread_score, 0), "weight": 0.20}

    # Turnover score
    if turnover_pct is not None and turnover_pct > 0:
        turn_score = min(100, turnover_pct * 200)  # 0.5% daily = 100
    else:
        turn_score = 50
    scores["turnover"] = {"score": round(turn_score, 0), "weight": 0.10}

    # Weighted composite
    composite = sum(s["score"] * s["weight"] for s in scores.values())

    # Classification
    if composite >= 80:
        tier = "highly_liquid"
    elif composite >= 60:
        tier = "liquid"
    elif composite >= 40:
        tier = "moderately_liquid"
    elif composite >= 20:
        tier = "illiquid"
    else:
        tier = "highly_illiquid"

    return {
        "composite": round(composite, 0),
        "tier": tier,
        "components": scores,
    }


def _interpret_liquidity(
    score: dict,
    amihud: Optional[float],
    avg_dv: float,
) -> str:
    """Human-readable liquidity interpretation."""
    tier = score.get("tier", "unknown")
    composite = score.get("composite", 0)

    tier_descriptions = {
        "highly_liquid": "Institutional-grade liquidity. Minimal slippage expected even for large orders.",
        "liquid": "Good liquidity. Standard position sizes can be executed efficiently.",
        "moderately_liquid": "Adequate liquidity. Larger orders may experience noticeable slippage.",
        "illiquid": "Poor liquidity. Significant price impact expected. Use limit orders.",
        "highly_illiquid": "Very illiquid. High execution risk. Consider this stock's liquidity before sizing positions.",
    }

    base = tier_descriptions.get(tier, "Liquidity assessment unavailable.")

    if avg_dv < 1.0:
        base += " Average daily volume under $1M — position sizing is critical."
    elif avg_dv > 500:
        base += f" Avg daily volume ${avg_dv:.0f}M supports institutional-size trades."

    return base


def analyze_liquidity_universe(
    tickers: Optional[list[str]] = None,
    top_n: int = 20,
) -> dict:
    """Analyze liquidity across a universe of stocks.

    Returns ranked list and aggregate statistics.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if tickers is None:
        universe = config.get("stock_universe", {})
        tickers = universe.get("default_watchlist", [])

    results = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(compute_liquidity_metrics, t): t
            for t in tickers[:top_n]
        }
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                result = future.result()
                if result:
                    results[ticker] = result
            except Exception as e:
                logger.warning("Liquidity analysis failed for %s: %s", ticker, e)

    if not results:
        return {"stocks": [], "summary": {}}

    # Rank by liquidity score
    ranked = sorted(
        results.items(),
        key=lambda x: x[1]["score"]["composite"],
        reverse=True,
    )

    # Summary stats
    scores = [r["score"]["composite"] for _, r in ranked]
    tiers = {}
    for _, r in ranked:
        tier = r["score"]["tier"]
        tiers[tier] = tiers.get(tier, 0) + 1

    return {
        "stocks": [
            {
                "ticker": t,
                "score": r["score"]["composite"],
                "tier": r["score"]["tier"],
                "avg_dollar_volume_mm": r["metrics"]["avg_dollar_volume_mm"],
                "amihud": r["metrics"]["amihud_illiquidity"],
                "lvar_95": r["risk"]["lvar_95"],
            }
            for t, r in ranked
        ],
        "summary": {
            "mean_score": round(float(np.mean(scores)), 1),
            "median_score": round(float(np.median(scores)), 1),
            "tier_distribution": tiers,
            "stocks_analyzed": len(results),
        },
    }
