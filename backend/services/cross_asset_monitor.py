"""
Aegis Finance — Cross-Asset Macro Regime Monitor
===================================================

Bloomberg MAC3-style cross-asset intelligence:
  - Growth × Inflation quadrant (Goldilocks / Reflation / Stagflation / Deflation)
  - Risk-On / Risk-Off composite score (0–100)
  - Cross-asset momentum table (equities, bonds, commodities, currencies, crypto)
  - Rolling correlation matrix between major asset classes
  - Intermarket divergence detection
  - Asset class trend regime (trending/mean-reverting/choppy)

The growth/inflation regime is derived from market-based proxies:
  - Growth: Copper/Gold ratio, HYG/LQD spread, small-cap/large-cap ratio (IWM/SPY)
  - Inflation: TIPS/IEF ratio (breakeven proxy), gold momentum, oil momentum

The Risk-On/Risk-Off score aggregates cross-asset signals:
  - Equity momentum (SPY, QQQ, EEM)
  - Credit spreads (HYG vs LQD)
  - Safe haven flows (gold, USD, treasuries)
  - Volatility regime (VIX level + term structure)
  - Carry appetite (EM vs DM, high-yield vs IG)

References:
  - QuantCube "Beyond the Quadrant" RORO framework
  - Bridgewater All-Weather macro regime classification
  - Bloomberg MAC3 multi-asset risk models

Data source: yfinance (free, no API key required)

Usage:
    from backend.services.cross_asset_monitor import (
        compute_macro_regime,
        compute_cross_asset_dashboard,
    )
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from backend.config import config

logger = logging.getLogger(__name__)


# ── Asset Universe ──────────────────────────────────────────────────────────

CROSS_ASSET_CONFIG = config.get("cross_asset", {})

_DEFAULT_ASSETS = {
    # Equities
    "SPY": {"name": "S&P 500", "class": "equity", "subclass": "us_large"},
    "QQQ": {"name": "NASDAQ 100", "class": "equity", "subclass": "us_tech"},
    "IWM": {"name": "Russell 2000", "class": "equity", "subclass": "us_small"},
    "EFA": {"name": "EAFE (Developed ex-US)", "class": "equity", "subclass": "intl_dm"},
    "EEM": {"name": "Emerging Markets", "class": "equity", "subclass": "intl_em"},
    # Fixed Income
    "TLT": {"name": "20+ Year Treasury", "class": "fixed_income", "subclass": "us_lt"},
    "IEF": {"name": "7-10 Year Treasury", "class": "fixed_income", "subclass": "us_it"},
    "HYG": {"name": "High Yield Corp", "class": "fixed_income", "subclass": "us_hy"},
    "LQD": {"name": "IG Corporate", "class": "fixed_income", "subclass": "us_ig"},
    "TIP": {"name": "TIPS (Inflation-Protected)", "class": "fixed_income", "subclass": "us_tips"},
    # Commodities
    "GLD": {"name": "Gold", "class": "commodity", "subclass": "precious"},
    "USO": {"name": "Crude Oil", "class": "commodity", "subclass": "energy"},
    "DBC": {"name": "Commodities Basket", "class": "commodity", "subclass": "broad"},
    # Currencies
    "UUP": {"name": "US Dollar (Bull)", "class": "currency", "subclass": "usd"},
    # Crypto
    "BTC-USD": {"name": "Bitcoin", "class": "crypto", "subclass": "btc"},
}

ASSET_TICKERS = CROSS_ASSET_CONFIG.get("tickers", _DEFAULT_ASSETS)

# Windows for momentum/trend calculations
MOMENTUM_WINDOWS = CROSS_ASSET_CONFIG.get(
    "momentum_windows", {"1w": 5, "1m": 21, "3m": 63, "6m": 126, "1y": 252}
)
CORRELATION_WINDOW = CROSS_ASSET_CONFIG.get("correlation_window", 63)
LOOKBACK_YEARS = CROSS_ASSET_CONFIG.get("lookback_years", 3)


# ── Data Fetching ───────────────────────────────────────────────────────────


def _fetch_cross_asset_prices(
    period: str = "3y",
) -> Optional[pd.DataFrame]:
    """Fetch daily closes for all cross-asset universe tickers."""
    try:
        import yfinance as yf
        from backend.services.data_fetcher import _yf_lock

        tickers = list(ASSET_TICKERS.keys())
        with _yf_lock:
            raw = yf.download(tickers, period=period, auto_adjust=True, progress=False)

        if raw.empty:
            logger.warning("Cross-asset download returned empty")
            return None

        # Handle MultiIndex columns from yfinance
        if isinstance(raw.columns, pd.MultiIndex):
            prices = raw["Close"] if "Close" in raw.columns.get_level_values(0) else raw.iloc[:, :len(tickers)]
        else:
            prices = raw

        # Ensure we have a DataFrame
        if isinstance(prices, pd.Series):
            prices = prices.to_frame()

        prices = prices.ffill().dropna(how="all")
        return prices

    except Exception as e:
        logger.error("Cross-asset price fetch failed: %s", e)
        return None


# ── Growth × Inflation Regime ──────────────────────────────────────────────


def _compute_growth_score(prices: pd.DataFrame, window: int = 63) -> pd.Series:
    """
    Market-based growth proxy from 3 signals:
      1. Copper/Gold ratio momentum (Dr. Copper = global industrial demand)
      2. HYG/LQD ratio momentum (credit appetite = growth confidence)
      3. IWM/SPY ratio momentum (small-cap outperformance = cyclical strength)

    Returns a z-scored growth indicator.
    """
    components = []

    # 1. Credit appetite: HYG/LQD
    if "HYG" in prices.columns and "LQD" in prices.columns:
        credit_ratio = prices["HYG"] / prices["LQD"]
        credit_mom = credit_ratio.pct_change(window)
        components.append(credit_mom)

    # 2. Small-cap vs large-cap cyclical proxy: IWM/SPY
    if "IWM" in prices.columns and "SPY" in prices.columns:
        size_ratio = prices["IWM"] / prices["SPY"]
        size_mom = size_ratio.pct_change(window)
        components.append(size_mom)

    # 3. EM vs DM (risk appetite / global growth): EEM/EFA
    if "EEM" in prices.columns and "EFA" in prices.columns:
        em_ratio = prices["EEM"] / prices["EFA"]
        em_mom = em_ratio.pct_change(window)
        components.append(em_mom)

    if not components:
        return pd.Series(dtype=float)

    # Average the z-scored components
    combined = pd.concat(components, axis=1)
    zscores = combined.apply(lambda s: (s - s.rolling(252).mean()) / s.rolling(252).std())
    growth = zscores.mean(axis=1)
    return growth


def _compute_inflation_score(prices: pd.DataFrame, window: int = 63) -> pd.Series:
    """
    Market-based inflation proxy from 3 signals:
      1. TIP/IEF ratio momentum (breakeven inflation proxy)
      2. Gold momentum (inflation hedge demand)
      3. Oil (USO) momentum (input cost pressure)

    Returns a z-scored inflation indicator.
    """
    components = []

    # 1. Breakeven inflation proxy: TIP/IEF
    if "TIP" in prices.columns and "IEF" in prices.columns:
        breakeven = prices["TIP"] / prices["IEF"]
        be_mom = breakeven.pct_change(window)
        components.append(be_mom)

    # 2. Gold momentum
    if "GLD" in prices.columns:
        gold_mom = prices["GLD"].pct_change(window)
        components.append(gold_mom)

    # 3. Oil momentum
    if "USO" in prices.columns:
        oil_mom = prices["USO"].pct_change(window)
        components.append(oil_mom)

    if not components:
        return pd.Series(dtype=float)

    combined = pd.concat(components, axis=1)
    zscores = combined.apply(lambda s: (s - s.rolling(252).mean()) / s.rolling(252).std())
    inflation = zscores.mean(axis=1)
    return inflation


def _classify_quadrant(growth: float, inflation: float) -> dict:
    """
    Classify into the 4 macro quadrants based on growth × inflation signs.

    Quadrant layout:
        Growth ↑, Inflation ↓ → Goldilocks (best for risk assets)
        Growth ↑, Inflation ↑ → Reflation (commodities, cyclicals)
        Growth ↓, Inflation ↑ → Stagflation (worst for portfolios)
        Growth ↓, Inflation ↓ → Deflation/Risk-Off (bonds rally)
    """
    if growth > 0 and inflation <= 0:
        return {
            "quadrant": "Goldilocks",
            "description": "Growth accelerating, inflation cooling — best environment for risk assets",
            "favored_assets": ["equities", "high_yield", "growth_stocks"],
            "avoid_assets": ["gold", "commodities", "defensive"],
        }
    elif growth > 0 and inflation > 0:
        return {
            "quadrant": "Reflation",
            "description": "Growth and inflation both rising — commodities and cyclicals outperform",
            "favored_assets": ["commodities", "value_stocks", "em_equities", "tips"],
            "avoid_assets": ["long_duration_bonds", "growth_stocks"],
        }
    elif growth <= 0 and inflation > 0:
        return {
            "quadrant": "Stagflation",
            "description": "Growth slowing while inflation persists — worst for traditional portfolios",
            "favored_assets": ["gold", "tips", "cash", "defensive_equities"],
            "avoid_assets": ["equities", "high_yield", "em_equities"],
        }
    else:  # growth <= 0, inflation <= 0
        return {
            "quadrant": "Deflation",
            "description": "Growth and inflation both falling — treasuries rally, risk-off",
            "favored_assets": ["long_duration_bonds", "usd", "quality_stocks"],
            "avoid_assets": ["commodities", "em_equities", "high_yield"],
        }


# ── Risk-On / Risk-Off Score ───────────────────────────────────────────────


def _compute_roro_score(prices: pd.DataFrame, window: int = 21) -> dict:
    """
    Risk-On/Risk-Off composite score (0-100).

    Aggregates 6 cross-asset signals:
      1. Equity momentum (SPY 1m return z-score)
      2. Credit appetite (HYG/LQD ratio change)
      3. Safe haven demand (inverse gold momentum)
      4. USD strength (inverse = risk-on)
      5. VIX regime (low VIX = risk-on) — via equity vol proxy
      6. EM appetite (EEM momentum)

    Score > 65 = Risk-On, < 35 = Risk-Off, 35-65 = Neutral
    """
    signals = {}
    raw_scores = []

    # 1. Equity momentum
    if "SPY" in prices.columns:
        spy_ret = prices["SPY"].pct_change(window).iloc[-1]
        spy_z = _trailing_zscore(prices["SPY"].pct_change(window), 252)
        signals["equity_momentum"] = {
            "value": round(float(spy_ret) * 100, 2),
            "z_score": round(float(spy_z), 2),
            "signal": "risk_on" if spy_z > 0 else "risk_off",
        }
        raw_scores.append(float(spy_z))

    # 2. Credit appetite
    if "HYG" in prices.columns and "LQD" in prices.columns:
        credit_ratio = prices["HYG"] / prices["LQD"]
        credit_change = credit_ratio.pct_change(window).iloc[-1]
        credit_z = _trailing_zscore(credit_ratio.pct_change(window), 252)
        signals["credit_appetite"] = {
            "value": round(float(credit_change) * 100, 2),
            "z_score": round(float(credit_z), 2),
            "signal": "risk_on" if credit_z > 0 else "risk_off",
        }
        raw_scores.append(float(credit_z))

    # 3. Safe haven demand (inverse: gold up = risk-off)
    if "GLD" in prices.columns:
        gold_ret = prices["GLD"].pct_change(window).iloc[-1]
        gold_z = _trailing_zscore(prices["GLD"].pct_change(window), 252)
        signals["safe_haven"] = {
            "value": round(float(gold_ret) * 100, 2),
            "z_score": round(float(-gold_z), 2),  # inverted
            "signal": "risk_off" if gold_z > 0 else "risk_on",
        }
        raw_scores.append(float(-gold_z))

    # 4. USD strength (inverse: strong USD = risk-off)
    if "UUP" in prices.columns:
        usd_ret = prices["UUP"].pct_change(window).iloc[-1]
        usd_z = _trailing_zscore(prices["UUP"].pct_change(window), 252)
        signals["usd_strength"] = {
            "value": round(float(usd_ret) * 100, 2),
            "z_score": round(float(-usd_z), 2),  # inverted
            "signal": "risk_off" if usd_z > 0 else "risk_on",
        }
        raw_scores.append(float(-usd_z))

    # 5. Volatility proxy (equity vol — high = risk-off)
    if "SPY" in prices.columns:
        spy_vol = prices["SPY"].pct_change().rolling(21).std() * np.sqrt(252)
        vol_z = _trailing_zscore(spy_vol, 252)
        signals["volatility"] = {
            "value": round(float(spy_vol.iloc[-1]) * 100, 1),
            "z_score": round(float(-vol_z), 2),  # inverted
            "signal": "risk_off" if vol_z > 0.5 else "risk_on",
        }
        raw_scores.append(float(-vol_z))

    # 6. EM appetite
    if "EEM" in prices.columns:
        eem_ret = prices["EEM"].pct_change(window).iloc[-1]
        eem_z = _trailing_zscore(prices["EEM"].pct_change(window), 252)
        signals["em_appetite"] = {
            "value": round(float(eem_ret) * 100, 2),
            "z_score": round(float(eem_z), 2),
            "signal": "risk_on" if eem_z > 0 else "risk_off",
        }
        raw_scores.append(float(eem_z))

    # Composite: average z-score mapped to 0-100
    if raw_scores:
        avg_z = np.mean(raw_scores)
        # Map z-score to 0-100 using sigmoid-like transform
        # z=0 → 50, z=2 → ~88, z=-2 → ~12
        from scipy.stats import norm
        composite = float(norm.cdf(avg_z) * 100)
    else:
        composite = 50.0
        avg_z = 0.0

    # Classify regime
    if composite >= 65:
        regime = "Risk-On"
        interpretation = "Cross-asset signals favor risk appetite — equities, credit, EM preferred"
    elif composite <= 35:
        regime = "Risk-Off"
        interpretation = "Cross-asset signals show defensive positioning — bonds, gold, USD preferred"
    else:
        regime = "Neutral"
        interpretation = "Mixed cross-asset signals — no clear risk appetite direction"

    return {
        "score": round(composite, 1),
        "z_score": round(float(avg_z), 3),
        "regime": regime,
        "interpretation": interpretation,
        "signals": signals,
        "n_signals": len(signals),
    }


def _trailing_zscore(series: pd.Series, window: int = 252) -> float:
    """Compute z-score of the latest value vs trailing window."""
    clean = series.dropna()
    if len(clean) < window:
        window = max(len(clean) - 1, 1)
    trailing = clean.iloc[-window:]
    mean = trailing.mean()
    std = trailing.std()
    if std == 0 or np.isnan(std):
        return 0.0
    return float((clean.iloc[-1] - mean) / std)


# ── Cross-Asset Momentum Table ─────────────────────────────────────────────


def _compute_momentum_table(prices: pd.DataFrame) -> list[dict]:
    """
    Multi-timeframe momentum for each asset.
    Returns sorted by 3m momentum (strongest first).
    """
    results = []

    for ticker, meta in ASSET_TICKERS.items():
        if ticker not in prices.columns:
            continue

        series = prices[ticker].dropna()
        if len(series) < 30:
            continue

        entry = {
            "ticker": ticker,
            "name": meta["name"],
            "asset_class": meta["class"],
            "subclass": meta["subclass"],
            "price": round(float(series.iloc[-1]), 2),
        }

        # Compute returns for each window
        for label, days in MOMENTUM_WINDOWS.items():
            if len(series) >= days + 1:
                ret = float((series.iloc[-1] / series.iloc[-days - 1]) - 1) * 100
                entry[f"return_{label}"] = round(ret, 2)
            else:
                entry[f"return_{label}"] = None

        # Trend strength: SMA ratio (price / SMA200)
        if len(series) >= 200:
            sma200 = series.rolling(200).mean().iloc[-1]
            entry["sma200_ratio"] = round(float(series.iloc[-1] / sma200), 4)
            entry["above_sma200"] = bool(series.iloc[-1] > sma200)
        else:
            entry["sma200_ratio"] = None
            entry["above_sma200"] = None

        # Volatility (annualized 30d)
        if len(series) >= 30:
            vol = float(series.pct_change().tail(30).std() * np.sqrt(252) * 100)
            entry["vol_30d_ann_pct"] = round(vol, 1)
        else:
            entry["vol_30d_ann_pct"] = None

        results.append(entry)

    # Sort by 3m return (strongest momentum first)
    results.sort(key=lambda x: x.get("return_3m") or -999, reverse=True)
    return results


# ── Correlation Matrix ──────────────────────────────────────────────────────


def _compute_correlation_matrix(
    prices: pd.DataFrame, window: int = 63
) -> dict:
    """
    Rolling correlation matrix between major asset class representatives.
    Also flags notable divergences from historical norms.
    """
    # Use one representative per asset class
    reps = {
        "Equities": "SPY",
        "Bonds": "TLT",
        "Gold": "GLD",
        "Oil": "USO",
        "USD": "UUP",
        "High Yield": "HYG",
        "EM Equity": "EEM",
        "Bitcoin": "BTC-USD",
    }

    available_reps = {k: v for k, v in reps.items() if v in prices.columns}
    if len(available_reps) < 3:
        return {"available": False, "reason": "insufficient_data"}

    rep_tickers = list(available_reps.values())
    rep_names = list(available_reps.keys())

    returns = prices[rep_tickers].pct_change().dropna()
    if len(returns) < window:
        return {"available": False, "reason": "insufficient_history"}

    # Current rolling correlation
    recent = returns.tail(window)
    current_corr = recent.corr()

    # Long-term correlation (for divergence detection)
    long_corr = returns.corr()

    # Build matrix output with readable names
    matrix = {}
    for i, name_i in enumerate(rep_names):
        row = {}
        for j, name_j in enumerate(rep_names):
            ti, tj = rep_tickers[i], rep_tickers[j]
            val = float(current_corr.loc[ti, tj])
            row[name_j] = round(val, 3)
        matrix[name_i] = row

    # Find notable divergences (current vs long-term)
    divergences = []
    for i in range(len(rep_tickers)):
        for j in range(i + 1, len(rep_tickers)):
            ti, tj = rep_tickers[i], rep_tickers[j]
            curr = float(current_corr.loc[ti, tj])
            hist = float(long_corr.loc[ti, tj])
            diff = curr - hist
            if abs(diff) > 0.25:  # Significant divergence threshold
                divergences.append({
                    "pair": f"{rep_names[i]} / {rep_names[j]}",
                    "current_corr": round(curr, 3),
                    "historical_corr": round(hist, 3),
                    "divergence": round(diff, 3),
                    "interpretation": (
                        f"{'Unusually correlated' if diff > 0 else 'Unusually decorrelated'} "
                        f"vs history ({round(abs(diff), 2)} deviation)"
                    ),
                })

    # Sort divergences by magnitude
    divergences.sort(key=lambda x: abs(x["divergence"]), reverse=True)

    # Key relationships
    key_pairs = {}
    pair_keys = [
        ("Equities", "Bonds", "stock_bond"),
        ("Equities", "Gold", "stock_gold"),
        ("Equities", "USD", "stock_dollar"),
        ("Gold", "USD", "gold_dollar"),
        ("Equities", "High Yield", "stock_credit"),
    ]
    for name_a, name_b, key in pair_keys:
        if name_a in available_reps and name_b in available_reps:
            ta, tb = available_reps[name_a], available_reps[name_b]
            key_pairs[key] = {
                "correlation": round(float(current_corr.loc[ta, tb]), 3),
                "historical": round(float(long_corr.loc[ta, tb]), 3),
            }

    return {
        "available": True,
        "window_days": window,
        "matrix": matrix,
        "key_relationships": key_pairs,
        "divergences": divergences[:5],  # Top 5
        "n_assets": len(available_reps),
    }


# ── Intermarket Divergences ────────────────────────────────────────────────


def _detect_intermarket_divergences(prices: pd.DataFrame) -> list[dict]:
    """
    Detect notable intermarket divergences that may signal regime shifts.
    These are historically reliable cross-asset warning signals.
    """
    alerts = []

    # 1. Stock-Bond correlation flip (normally negative in risk-off)
    if "SPY" in prices.columns and "TLT" in prices.columns:
        returns = prices[["SPY", "TLT"]].pct_change().dropna()
        if len(returns) >= 63:
            recent_corr = returns.tail(21).corr().iloc[0, 1]
            normal_corr = returns.tail(252).corr().iloc[0, 1]
            if recent_corr > 0.3 and normal_corr < 0:
                alerts.append({
                    "type": "stock_bond_positive_corr",
                    "severity": "high",
                    "message": (
                        f"Stocks and bonds moving together (corr={recent_corr:.2f}) — "
                        "historically signals inflation fears or liquidity crisis"
                    ),
                    "current_corr": round(float(recent_corr), 3),
                })

    # 2. Gold/USD divergence (normally inversely correlated)
    if "GLD" in prices.columns and "UUP" in prices.columns:
        gold_1m = float(prices["GLD"].pct_change(21).iloc[-1])
        usd_1m = float(prices["UUP"].pct_change(21).iloc[-1])
        if gold_1m > 0.03 and usd_1m > 0.02:
            alerts.append({
                "type": "gold_usd_both_rising",
                "severity": "medium",
                "message": (
                    "Gold and USD both rising — rare combo signaling "
                    "extreme uncertainty or geopolitical stress"
                ),
                "gold_1m_pct": round(gold_1m * 100, 1),
                "usd_1m_pct": round(usd_1m * 100, 1),
            })

    # 3. Credit-equity divergence (HYG falling while SPY rising)
    if "HYG" in prices.columns and "SPY" in prices.columns:
        hyg_1m = float(prices["HYG"].pct_change(21).iloc[-1])
        spy_1m = float(prices["SPY"].pct_change(21).iloc[-1])
        if spy_1m > 0.02 and hyg_1m < -0.01:
            alerts.append({
                "type": "credit_equity_divergence",
                "severity": "high",
                "message": (
                    "Equities rising but high-yield credit declining — "
                    "credit market not confirming equity rally (bearish divergence)"
                ),
                "spy_1m_pct": round(spy_1m * 100, 1),
                "hyg_1m_pct": round(hyg_1m * 100, 1),
            })

    # 4. Small-cap underperformance (risk appetite weakening)
    if "IWM" in prices.columns and "SPY" in prices.columns:
        iwm_3m = float(prices["IWM"].pct_change(63).iloc[-1])
        spy_3m = float(prices["SPY"].pct_change(63).iloc[-1])
        spread = iwm_3m - spy_3m
        if spread < -0.08:
            alerts.append({
                "type": "small_cap_underperformance",
                "severity": "medium",
                "message": (
                    f"Small-caps lagging large-caps by {abs(spread)*100:.1f}% over 3 months — "
                    "risk appetite narrowing, late-cycle signal"
                ),
                "iwm_3m_pct": round(iwm_3m * 100, 1),
                "spy_3m_pct": round(spy_3m * 100, 1),
            })

    # 5. EM underperformance (global growth concern)
    if "EEM" in prices.columns and "SPY" in prices.columns:
        eem_3m = float(prices["EEM"].pct_change(63).iloc[-1])
        spy_3m = float(prices["SPY"].pct_change(63).iloc[-1])
        if eem_3m < -0.05 and spy_3m > 0.02:
            alerts.append({
                "type": "em_dm_divergence",
                "severity": "medium",
                "message": (
                    "EM equities falling while US rises — "
                    "global growth divergence or USD tightening"
                ),
                "eem_3m_pct": round(eem_3m * 100, 1),
                "spy_3m_pct": round(spy_3m * 100, 1),
            })

    return alerts


# ── Breadth & Trend Score ───────────────────────────────────────────────────


def _compute_asset_class_breadth(prices: pd.DataFrame) -> dict:
    """
    Cross-asset breadth: what fraction of asset classes are in uptrends.
    Uses SMA50 > SMA200 golden cross as trend definition.
    """
    uptrend_count = 0
    total = 0
    class_trends = {}

    for ticker, meta in ASSET_TICKERS.items():
        if ticker not in prices.columns:
            continue
        series = prices[ticker].dropna()
        if len(series) < 200:
            continue

        sma50 = series.rolling(50).mean().iloc[-1]
        sma200 = series.rolling(200).mean().iloc[-1]
        in_uptrend = bool(sma50 > sma200)

        asset_class = meta["class"]
        if asset_class not in class_trends:
            class_trends[asset_class] = {"uptrend": 0, "total": 0, "tickers": []}

        class_trends[asset_class]["total"] += 1
        class_trends[asset_class]["tickers"].append({
            "ticker": ticker,
            "uptrend": in_uptrend,
        })
        if in_uptrend:
            class_trends[asset_class]["uptrend"] += 1
            uptrend_count += 1
        total += 1

    breadth = uptrend_count / total if total > 0 else 0.5

    return {
        "breadth_score": round(breadth, 3),
        "uptrend_count": uptrend_count,
        "total_assets": total,
        "interpretation": (
            "Broad uptrend" if breadth > 0.7
            else "Narrow leadership" if breadth < 0.3
            else "Mixed trends"
        ),
        "by_class": {
            k: {
                "uptrend_pct": round(v["uptrend"] / v["total"] * 100, 0) if v["total"] > 0 else 0,
                "detail": v["tickers"],
            }
            for k, v in class_trends.items()
        },
    }


# ── Public API ──────────────────────────────────────────────────────────────


def compute_macro_regime(prices: Optional[pd.DataFrame] = None) -> dict:
    """
    Compute the current macro regime (growth × inflation quadrant).

    Returns:
        dict with quadrant, growth_score, inflation_score, and regime details
    """
    if prices is None:
        prices = _fetch_cross_asset_prices()
    if prices is None or prices.empty:
        return {"error": "Failed to fetch cross-asset data"}

    growth_series = _compute_growth_score(prices)
    inflation_series = _compute_inflation_score(prices)

    if growth_series.empty or inflation_series.empty:
        return {"error": "Insufficient data for regime classification"}

    growth_current = float(growth_series.dropna().iloc[-1])
    inflation_current = float(inflation_series.dropna().iloc[-1])

    quadrant = _classify_quadrant(growth_current, inflation_current)

    # Compute regime momentum (is the regime shifting?)
    if len(growth_series.dropna()) > 21 and len(inflation_series.dropna()) > 21:
        growth_prev = float(growth_series.dropna().iloc[-22])
        inflation_prev = float(inflation_series.dropna().iloc[-22])
        prev_quadrant = _classify_quadrant(growth_prev, inflation_prev)["quadrant"]
        regime_stable = quadrant["quadrant"] == prev_quadrant
    else:
        prev_quadrant = None
        regime_stable = None

    return {
        "quadrant": quadrant["quadrant"],
        "description": quadrant["description"],
        "favored_assets": quadrant["favored_assets"],
        "avoid_assets": quadrant["avoid_assets"],
        "growth_score": round(growth_current, 3),
        "inflation_score": round(inflation_current, 3),
        "regime_stable": regime_stable,
        "previous_quadrant": prev_quadrant,
        "growth_interpretation": (
            "accelerating" if growth_current > 0.5
            else "expanding" if growth_current > 0
            else "slowing" if growth_current > -0.5
            else "contracting"
        ),
        "inflation_interpretation": (
            "surging" if inflation_current > 0.5
            else "rising" if inflation_current > 0
            else "cooling" if inflation_current > -0.5
            else "falling"
        ),
    }


def compute_cross_asset_dashboard(prices: Optional[pd.DataFrame] = None) -> dict:
    """
    Full cross-asset intelligence dashboard.

    Returns:
        dict with macro_regime, risk_on_off, momentum_table, correlations,
        divergences, and breadth analysis
    """
    if prices is None:
        prices = _fetch_cross_asset_prices()
    if prices is None or prices.empty:
        return {"error": "Failed to fetch cross-asset data"}

    # All computations share the same price data
    macro_regime = compute_macro_regime(prices)
    roro = _compute_roro_score(prices)
    momentum = _compute_momentum_table(prices)
    correlations = _compute_correlation_matrix(prices, CORRELATION_WINDOW)
    divergences = _detect_intermarket_divergences(prices)
    breadth = _compute_asset_class_breadth(prices)

    # Summary: one-line "macro weather"
    quadrant = macro_regime.get("quadrant", "Unknown")
    roro_regime = roro.get("regime", "Neutral")
    roro_score = roro.get("score", 50)

    weather = _macro_weather(quadrant, roro_regime, roro_score, divergences)

    return {
        "macro_regime": macro_regime,
        "risk_on_off": roro,
        "momentum_table": momentum,
        "correlations": correlations,
        "intermarket_divergences": divergences,
        "breadth": breadth,
        "macro_weather": weather,
        "n_assets_tracked": len(momentum),
        "asset_classes": ["equity", "fixed_income", "commodity", "currency", "crypto"],
    }


def _macro_weather(
    quadrant: str, roro_regime: str, roro_score: float, divergences: list
) -> dict:
    """Generate a one-line macro weather summary."""
    n_alerts = len([d for d in divergences if d.get("severity") == "high"])

    if quadrant == "Goldilocks" and roro_regime == "Risk-On":
        condition = "Clear skies"
        summary = "Macro environment strongly supports risk assets — growth up, inflation down, risk appetite broad"
    elif quadrant == "Reflation" and roro_regime == "Risk-On":
        condition = "Warm with rising prices"
        summary = "Reflationary boom — cyclicals and commodities outperform, watch for overheating"
    elif quadrant == "Stagflation":
        condition = "Storm warning"
        summary = "Stagflation risk — growth slowing amid persistent inflation, defensive positioning advised"
    elif quadrant == "Deflation":
        condition = "Cold front"
        summary = "Deflationary pressures — flight to quality, long-duration bonds and USD benefit"
    elif roro_regime == "Risk-Off":
        condition = "Overcast"
        summary = f"Risk-off environment (score: {roro_score:.0f}/100) — cross-asset signals favor safety"
    else:
        condition = "Partly cloudy"
        summary = f"Mixed signals — {quadrant} regime with {roro_regime.lower()} risk appetite"

    if n_alerts > 0:
        summary += f" | {n_alerts} high-severity intermarket divergence{'s' if n_alerts > 1 else ''} detected"

    return {
        "condition": condition,
        "summary": summary,
        "quadrant": quadrant,
        "risk_regime": roro_regime,
        "roro_score": round(roro_score, 1),
        "n_divergence_alerts": n_alerts,
    }
