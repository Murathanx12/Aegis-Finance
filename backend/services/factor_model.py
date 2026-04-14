"""
Aegis Finance — Fama-French 5-Factor Model Decomposition
==========================================================

Decomposes stock and portfolio returns into systematic factor exposures:
  - Mkt-RF: Market excess return (CAPM beta)
  - SMB: Small minus Big (size factor)
  - HML: High minus Low (value factor)
  - RMW: Robust minus Weak (profitability factor)
  - CMA: Conservative minus Aggressive (investment factor)
  - Alpha: Unexplained excess return (manager skill or mispricing)

Data source: Kenneth French Data Library (free, academic standard).

Usage:
    from backend.services.factor_model import (
        get_factor_data, decompose_stock, decompose_portfolio
    )
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

from backend.config import config

logger = logging.getLogger(__name__)

# Kenneth French data library — standard academic source
_FACTOR_CACHE: dict = {}
_FACTOR_CACHE_TS: dict[str, float] = {}  # per-key timestamps
_CACHE_TTL = 86400  # 24 hours


def get_factor_data(lookback_days: Optional[int] = None) -> Optional[pd.DataFrame]:
    """Download Fama-French 5-factor daily returns from Kenneth French Data Library.

    Returns DataFrame with columns: Mkt-RF, SMB, HML, RMW, CMA, RF
    Values are daily returns in decimal form (e.g., 0.01 = 1%).
    """
    import time

    global _FACTOR_CACHE, _FACTOR_CACHE_TS

    now = time.time()
    cache_key = "ff5_daily"
    if cache_key in _FACTOR_CACHE and (now - _FACTOR_CACHE_TS.get(cache_key, 0)) < _CACHE_TTL:
        df = _FACTOR_CACHE[cache_key]
        if lookback_days and len(df) > lookback_days:
            return df.iloc[-lookback_days:]
        return df

    try:
        import pandas_datareader.data as web
        ff5 = web.DataReader(
            "F-F_Research_Data_5_Factors_2x3_daily",
            "famafrench",
        )
        # ff5 is a dict of DataFrames; [0] is the main table
        df = ff5[0]

        # Convert from percentage to decimal
        df = df / 100.0

        # Ensure datetime index
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()

        _FACTOR_CACHE[cache_key] = df
        _FACTOR_CACHE_TS[cache_key] = now

        logger.info("Loaded %d days of Fama-French 5-factor data", len(df))

        if lookback_days and len(df) > lookback_days:
            return df.iloc[-lookback_days:]
        return df

    except Exception as e:
        logger.warning("Failed to load Fama-French data: %s", e)
        return None


def decompose_stock(
    ticker: str,
    price_series: Optional[pd.Series] = None,
    lookback_days: Optional[int] = None,
) -> Optional[dict]:
    """Decompose a stock's returns into Fama-French 5-factor exposures.

    Args:
        ticker: Stock ticker symbol
        price_series: Optional pre-fetched price series. If None, fetches via yfinance.
        lookback_days: Number of trading days to analyze (default from config)

    Returns:
        Dictionary with factor loadings, alpha, R², and statistical significance,
        or None if insufficient data.
    """
    cfg = config.get("factor_model", {})
    if lookback_days is None:
        lookback_days = cfg.get("lookback_days", 756)
    min_obs = cfg.get("min_observations", 126)
    sig_level = cfg.get("significance_level", 0.05)

    # Get stock returns
    if price_series is None:
        try:
            import yfinance as yf
            tk = yf.Ticker(ticker)
            hist = tk.history(period="5y")
            if hist.empty or len(hist) < min_obs:
                return None
            price_series = hist["Close"]
        except Exception as e:
            logger.warning("Failed to fetch %s for factor decomposition: %s", ticker, e)
            return None

    stock_returns = price_series.pct_change().dropna()
    if len(stock_returns) < min_obs:
        return None

    # Get factor data
    factors = get_factor_data(lookback_days=lookback_days + 30)  # buffer for alignment
    if factors is None or factors.empty:
        return None

    # Align dates
    stock_returns.index = pd.to_datetime(stock_returns.index).tz_localize(None)
    factors.index = pd.to_datetime(factors.index).tz_localize(None)

    # Merge on date
    combined = pd.DataFrame({"stock_ret": stock_returns}).join(factors, how="inner")
    combined = combined.dropna()

    if len(combined) < min_obs:
        logger.warning("%s: only %d overlapping observations (need %d)",
                       ticker, len(combined), min_obs)
        return None

    # Trim to lookback
    if len(combined) > lookback_days:
        combined = combined.iloc[-lookback_days:]

    # Excess returns = stock return - risk-free rate
    y = combined["stock_ret"] - combined["RF"]
    factor_names = ["Mkt-RF", "SMB", "HML", "RMW", "CMA"]
    X = combined[factor_names].values
    X_with_const = np.column_stack([np.ones(len(X)), X])

    # OLS regression
    try:
        betas, residuals, rank, sv = np.linalg.lstsq(X_with_const, y.values, rcond=None)
    except np.linalg.LinAlgError:
        logger.warning("%s: factor regression failed (singular matrix)", ticker)
        return None

    alpha = betas[0]
    factor_loadings = dict(zip(factor_names, betas[1:]))

    # Predicted values and R²
    y_pred = X_with_const @ betas
    ss_res = np.sum((y.values - y_pred) ** 2)
    ss_tot = np.sum((y.values - y.values.mean()) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    # Standard errors and t-statistics
    n = len(y)
    k = X_with_const.shape[1]
    if n > k:
        mse = ss_res / (n - k)
        try:
            cov_matrix = mse * np.linalg.inv(X_with_const.T @ X_with_const)
            se = np.sqrt(np.diag(cov_matrix))
            t_stats = betas / se
            p_values = [2 * (1 - stats.t.cdf(abs(t), df=n - k)) for t in t_stats]
        except np.linalg.LinAlgError:
            se = np.full(k, np.nan)
            t_stats = np.full(k, np.nan)
            p_values = [np.nan] * k
    else:
        se = np.full(k, np.nan)
        t_stats = np.full(k, np.nan)
        p_values = [np.nan] * k

    # Build result
    factor_details = {}
    for i, name in enumerate(factor_names):
        idx = i + 1  # skip intercept
        p_val = p_values[idx] if idx < len(p_values) else np.nan
        factor_details[name] = {
            "loading": round(float(factor_loadings[name]), 4),
            "t_stat": round(float(t_stats[idx]), 2) if not np.isnan(t_stats[idx]) else None,
            "p_value": round(float(p_val), 4) if not np.isnan(p_val) else None,
            "significant": bool(p_val < sig_level) if not np.isnan(p_val) else False,
        }

    # Annualize alpha (252 trading days)
    alpha_annual = float(alpha) * 252

    # Interpret factor exposures
    style = _interpret_style(factor_loadings)

    return {
        "ticker": ticker,
        "observations": len(combined),
        "r_squared": round(float(r_squared), 4),
        "adjusted_r_squared": round(float(1 - (1 - r_squared) * (n - 1) / (n - k - 1)), 4) if n > k + 1 else None,
        "alpha_daily": round(float(alpha), 6),
        "alpha_annual": round(alpha_annual, 4),
        "alpha_significant": bool(p_values[0] < sig_level) if not np.isnan(p_values[0]) else False,
        "factors": factor_details,
        "style": style,
        "residual_vol": round(float(np.sqrt(mse) * np.sqrt(252)), 4) if n > k else None,
    }


def _interpret_style(loadings: dict) -> dict:
    """Interpret factor loadings into human-readable style labels."""
    style = {}

    beta = loadings.get("Mkt-RF", 1.0)
    if beta > 1.2:
        style["market"] = "aggressive"
    elif beta < 0.8:
        style["market"] = "defensive"
    else:
        style["market"] = "neutral"

    smb = loadings.get("SMB", 0.0)
    if smb > 0.2:
        style["size"] = "small-cap tilt"
    elif smb < -0.2:
        style["size"] = "large-cap tilt"
    else:
        style["size"] = "neutral"

    hml = loadings.get("HML", 0.0)
    if hml > 0.2:
        style["value"] = "value"
    elif hml < -0.2:
        style["value"] = "growth"
    else:
        style["value"] = "blend"

    rmw = loadings.get("RMW", 0.0)
    if rmw > 0.15:
        style["profitability"] = "quality"
    elif rmw < -0.15:
        style["profitability"] = "speculative"
    else:
        style["profitability"] = "neutral"

    cma = loadings.get("CMA", 0.0)
    if cma > 0.15:
        style["investment"] = "conservative"
    elif cma < -0.15:
        style["investment"] = "aggressive"
    else:
        style["investment"] = "neutral"

    return style


def get_momentum_factor(lookback_days: Optional[int] = None) -> Optional[pd.DataFrame]:
    """Download Carhart Momentum (UMD) factor from Kenneth French Data Library.

    UMD = Up Minus Down = returns of past winners minus past losers.
    Adding this to FF5 creates the FF5+Momentum (FF6) model.
    """
    import time

    global _FACTOR_CACHE, _FACTOR_CACHE_TS

    now = time.time()
    cache_key = "mom_daily"
    if cache_key in _FACTOR_CACHE and (now - _FACTOR_CACHE_TS.get(cache_key, 0)) < _CACHE_TTL:
        df = _FACTOR_CACHE[cache_key]
        if lookback_days and len(df) > lookback_days:
            return df.iloc[-lookback_days:]
        return df

    try:
        import pandas_datareader.data as web
        mom = web.DataReader(
            "F-F_Momentum_Factor_daily",
            "famafrench",
        )
        df = mom[0] / 100.0  # Convert percentage to decimal
        df.columns = ["Mom"]
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()

        _FACTOR_CACHE[cache_key] = df
        _FACTOR_CACHE_TS[cache_key] = now

        logger.info("Loaded %d days of Momentum factor data", len(df))

        if lookback_days and len(df) > lookback_days:
            return df.iloc[-lookback_days:]
        return df

    except Exception as e:
        logger.warning("Failed to load Momentum factor: %s", e)
        return None


def decompose_stock_ff6(
    ticker: str,
    price_series: Optional[pd.Series] = None,
    lookback_days: Optional[int] = None,
) -> Optional[dict]:
    """Decompose returns using FF5 + Momentum (6-factor model).

    Same as decompose_stock but adds the Carhart UMD momentum factor.
    """
    cfg = config.get("factor_model", {})
    if lookback_days is None:
        lookback_days = cfg.get("lookback_days", 756)
    min_obs = cfg.get("min_observations", 126)
    sig_level = cfg.get("significance_level", 0.05)

    # Get stock returns
    if price_series is None:
        try:
            import yfinance as yf
            tk = yf.Ticker(ticker)
            hist = tk.history(period="5y")
            if hist.empty or len(hist) < min_obs:
                return None
            price_series = hist["Close"]
        except Exception as e:
            logger.warning("Failed to fetch %s: %s", ticker, e)
            return None

    stock_returns = price_series.pct_change().dropna()
    if len(stock_returns) < min_obs:
        return None

    # Get FF5 + Momentum data
    factors = get_factor_data(lookback_days=lookback_days + 30)
    mom = get_momentum_factor(lookback_days=lookback_days + 30)

    if factors is None or factors.empty:
        return None

    # Merge momentum if available
    if mom is not None and not mom.empty:
        factors = factors.join(mom, how="inner")
        factor_names = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"]
    else:
        factor_names = ["Mkt-RF", "SMB", "HML", "RMW", "CMA"]

    # Align dates
    stock_returns.index = pd.to_datetime(stock_returns.index).tz_localize(None)
    factors.index = pd.to_datetime(factors.index).tz_localize(None)

    combined = pd.DataFrame({"stock_ret": stock_returns}).join(factors, how="inner").dropna()

    if len(combined) < min_obs:
        return None

    if len(combined) > lookback_days:
        combined = combined.iloc[-lookback_days:]

    # Excess returns
    y = combined["stock_ret"] - combined["RF"]
    X = combined[factor_names].values
    X_with_const = np.column_stack([np.ones(len(X)), X])

    # OLS regression
    try:
        betas, _, _, _ = np.linalg.lstsq(X_with_const, y.values, rcond=None)
    except np.linalg.LinAlgError:
        return None

    alpha = betas[0]
    factor_loadings = dict(zip(factor_names, betas[1:]))

    # R² and residuals
    y_pred = X_with_const @ betas
    residuals = y.values - y_pred
    ss_res = np.sum(residuals ** 2)
    ss_tot = np.sum((y.values - y.values.mean()) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    # Standard errors
    n = len(y)
    k = X_with_const.shape[1]
    if n > k:
        mse = ss_res / (n - k)
        try:
            cov_matrix = mse * np.linalg.inv(X_with_const.T @ X_with_const)
            se = np.sqrt(np.diag(cov_matrix))
            t_stats = betas / se
            p_values = [2 * (1 - stats.t.cdf(abs(t), df=n - k)) for t in t_stats]
        except np.linalg.LinAlgError:
            t_stats = np.full(k, np.nan)
            p_values = [np.nan] * k
    else:
        t_stats = np.full(k, np.nan)
        p_values = [np.nan] * k

    # Build result
    factor_details = {}
    for i, name in enumerate(factor_names):
        idx = i + 1
        p_val = p_values[idx] if idx < len(p_values) else np.nan
        factor_details[name] = {
            "loading": round(float(factor_loadings[name]), 4),
            "t_stat": round(float(t_stats[idx]), 2) if not np.isnan(t_stats[idx]) else None,
            "p_value": round(float(p_val), 4) if not np.isnan(p_val) else None,
            "significant": bool(p_val < sig_level) if not np.isnan(p_val) else False,
        }

    alpha_annual = float(alpha) * 252
    style = _interpret_style(factor_loadings)

    # Add momentum style interpretation
    mom_loading = factor_loadings.get("Mom", 0.0)
    if mom_loading > 0.15:
        style["momentum"] = "winner"
    elif mom_loading < -0.15:
        style["momentum"] = "loser/reversal"
    else:
        style["momentum"] = "neutral"

    return {
        "ticker": ticker,
        "model": "FF5+Mom" if "Mom" in factor_names else "FF5",
        "observations": len(combined),
        "r_squared": round(float(r_squared), 4),
        "adjusted_r_squared": round(float(1 - (1 - r_squared) * (n - 1) / (n - k - 1)), 4) if n > k + 1 else None,
        "alpha_daily": round(float(alpha), 6),
        "alpha_annual": round(alpha_annual, 4),
        "alpha_significant": bool(p_values[0] < sig_level) if not np.isnan(p_values[0]) else False,
        "factors": factor_details,
        "style": style,
        "residual_vol": round(float(np.sqrt(mse) * np.sqrt(252)), 4) if n > k else None,
        "residuals": residuals,  # For PCA analysis
    }


def pca_residual_factors(
    tickers: list[str],
    lookback_days: Optional[int] = None,
    n_components: int = 3,
) -> Optional[dict]:
    """Axioma-style hybrid approach: PCA on FF5+Mom residuals.

    After running FF6 regression on each stock, the residuals contain
    systematic risk not captured by the standard factors. PCA extracts
    the dominant patterns (hidden factors like sector rotation, crowding,
    liquidity, etc.).

    Args:
        tickers: List of stock tickers
        lookback_days: Analysis window
        n_components: Number of PCA components to extract

    Returns:
        Dict with PCA factors, explained variance, and factor correlations.
    """
    from sklearn.decomposition import PCA

    cfg = config.get("factor_model", {})
    if lookback_days is None:
        lookback_days = cfg.get("lookback_days", 756)

    # Collect residuals from FF6 decomposition
    residual_matrix = {}
    for ticker in tickers:
        result = decompose_stock_ff6(ticker, lookback_days=lookback_days)
        if result is not None and result.get("residuals") is not None:
            residual_matrix[ticker] = result["residuals"]

    if len(residual_matrix) < n_components + 1:
        logger.warning("Not enough tickers with valid residuals for PCA (%d/%d)",
                       len(residual_matrix), n_components + 1)
        return None

    # Align residuals into a matrix
    min_len = min(len(r) for r in residual_matrix.values())
    aligned = np.column_stack([r[-min_len:] for r in residual_matrix.values()])
    ticker_order = list(residual_matrix.keys())

    # Standardize
    mean = aligned.mean(axis=0)
    std = aligned.std(axis=0)
    std[std == 0] = 1e-10
    standardized = (aligned - mean) / std

    # PCA
    n_comp = min(n_components, aligned.shape[1] - 1, aligned.shape[0] - 1)
    pca = PCA(n_components=n_comp)
    pca.fit(standardized)

    # Interpret components
    components = []
    for i in range(n_comp):
        loadings = dict(zip(ticker_order, [round(float(x), 4) for x in pca.components_[i]]))
        # Find top positive and negative loadings
        sorted_loadings = sorted(loadings.items(), key=lambda x: abs(x[1]), reverse=True)

        components.append({
            "component": i + 1,
            "explained_variance_pct": round(float(pca.explained_variance_ratio_[i]) * 100, 2),
            "top_loadings": {t: v for t, v in sorted_loadings[:5]},
            "interpretation": _interpret_pca_component(sorted_loadings),
        })

    return {
        "n_tickers": len(residual_matrix),
        "n_observations": min_len,
        "n_components": n_comp,
        "total_variance_explained_pct": round(float(sum(pca.explained_variance_ratio_)) * 100, 2),
        "components": components,
        "interpretation": (
            f"PCA extracted {n_comp} hidden factors from FF6 residuals across {len(residual_matrix)} stocks. "
            f"These explain {sum(pca.explained_variance_ratio_)*100:.1f}% of residual variance "
            f"(risk not captured by standard FF5+Momentum factors)."
        ),
    }


def _interpret_pca_component(sorted_loadings: list) -> str:
    """Interpret a PCA component from its loadings."""
    if not sorted_loadings:
        return "Unknown factor"

    top_pos = [(t, v) for t, v in sorted_loadings if v > 0.2][:3]
    top_neg = [(t, v) for t, v in sorted_loadings if v < -0.2][:3]

    if top_pos and top_neg:
        pos_str = ", ".join(t for t, _ in top_pos)
        neg_str = ", ".join(t for t, _ in top_neg)
        return f"Long {pos_str} / Short {neg_str} — possible sector rotation or style factor"
    elif top_pos:
        pos_str = ", ".join(t for t, _ in top_pos)
        return f"Driven by {pos_str} — possible idiosyncratic or thematic factor"
    else:
        return "Diffuse factor — affects many stocks weakly"


def decompose_portfolio(
    weights: dict[str, float],
    lookback_days: Optional[int] = None,
) -> Optional[dict]:
    """Decompose a portfolio's returns into factor exposures.

    Args:
        weights: Dictionary of {ticker: weight} (weights should sum to ~1.0)
        lookback_days: Number of trading days to analyze

    Returns:
        Portfolio-level factor decomposition with individual stock contributions.
    """
    cfg = config.get("factor_model", {})
    if lookback_days is None:
        lookback_days = cfg.get("lookback_days", 756)

    stock_results = {}
    for ticker, weight in weights.items():
        result = decompose_stock(ticker, lookback_days=lookback_days)
        if result is not None:
            stock_results[ticker] = {"weight": weight, "decomposition": result}

    if not stock_results:
        return None

    # Weighted portfolio factor loadings
    factor_names = ["Mkt-RF", "SMB", "HML", "RMW", "CMA"]
    portfolio_loadings = {f: 0.0 for f in factor_names}
    portfolio_alpha = 0.0
    total_weight = sum(v["weight"] for v in stock_results.values())

    for ticker, data in stock_results.items():
        w = data["weight"] / total_weight if total_weight > 0 else 0
        decomp = data["decomposition"]
        portfolio_alpha += w * decomp["alpha_annual"]
        for f in factor_names:
            portfolio_loadings[f] += w * decomp["factors"][f]["loading"]

    # Portfolio style interpretation
    style = _interpret_style(portfolio_loadings)

    # Risk attribution: what fraction of portfolio risk comes from each factor
    risk_attribution = {}
    total_loading_sq = sum(v ** 2 for v in portfolio_loadings.values())
    if total_loading_sq > 0:
        for f in factor_names:
            risk_attribution[f] = round(
                portfolio_loadings[f] ** 2 / total_loading_sq, 4
            )

    return {
        "portfolio_alpha_annual": round(portfolio_alpha, 4),
        "portfolio_factors": {
            f: round(v, 4) for f, v in portfolio_loadings.items()
        },
        "portfolio_style": style,
        "risk_attribution": risk_attribution,
        "stocks_analyzed": len(stock_results),
        "stocks_failed": len(weights) - len(stock_results),
        "stock_details": stock_results,
    }
