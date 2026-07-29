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
from pathlib import Path
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

# Pinned daily vintage (baked into the image, NOT under AEGIS_DATA_DIR — the
# persistence volume must not shadow it). French rewrites factor history across
# vintages (92.8% of HML months changed across one 18-month step, measured on
# the research pin), so served attribution is anchored to this frozen file and
# only the post-vintage tail may come from a live fetch — disclosed, never
# silently re-derived on a floating vintage.
_PINNED_CSV = Path(__file__).parent.parent / "data" / "ff_daily_pinned.csv.gz"
_PINNED_VINTAGE = _PINNED_CSV.with_name("ff_daily_pinned_VINTAGE.json")

_FF5_COLS = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"]


def _load_pinned() -> tuple[Optional[pd.DataFrame], dict]:
    """Load the pinned daily FF vintage behind its sha256 gate.

    Returns (df, meta). A hash mismatch REFUSES the file (an unpinned live
    fetch with disclosed provenance beats a silently tampered pin).
    Cached without TTL — the pin is immutable for the life of the process.
    """
    cached = _FACTOR_CACHE.get("ff_pinned")
    if cached is not None:
        return cached

    df: Optional[pd.DataFrame] = None
    meta: dict = {"status": "absent"}
    try:
        if _PINNED_CSV.exists() and _PINNED_VINTAGE.exists():
            import hashlib
            import json

            recorded = json.loads(_PINNED_VINTAGE.read_text(encoding="utf-8"))
            actual = hashlib.sha256(_PINNED_CSV.read_bytes()).hexdigest()
            if actual != recorded.get("sha256"):
                logger.error(
                    "Pinned FF vintage FAILED its hash gate (%s… != recorded %s…) — "
                    "refusing the file; attribution falls back to live_unpinned",
                    actual[:12], str(recorded.get("sha256"))[:12],
                )
                meta = {"status": "hash_mismatch"}
            else:
                df = pd.read_csv(_PINNED_CSV, index_col="Date", parse_dates=True)
                meta = {
                    "status": "ok",
                    "vintage_date": recorded.get("download_date"),
                    "sha256": recorded.get("sha256"),
                    "ff5_end": recorded.get("ff5_end"),
                    "mom_end": recorded.get("mom_end"),
                }
        else:
            logger.warning(
                "Pinned FF vintage not found at %s — factor attribution runs "
                "live_unpinned (vintage floats across French rewrites)", _PINNED_CSV,
            )
    except Exception as e:
        logger.error("Pinned FF vintage unreadable (%s) — live_unpinned fallback", e)
        meta = {"status": "unreadable", "error": str(e)}

    _FACTOR_CACHE["ff_pinned"] = (df, meta)
    return df, meta


def _fetch_ff5_live() -> Optional[pd.DataFrame]:
    """Live FF5 daily fetch (pandas_datareader, ~5y rolling window)."""
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

        # Ensure datetime index — pandas_datareader returns a PeriodIndex,
        # and pd.to_datetime(PeriodIndex) raises on pandas >= 2.x
        if isinstance(df.index, pd.PeriodIndex):
            df.index = df.index.to_timestamp()
        else:
            df.index = pd.to_datetime(df.index)
        return df.sort_index()
    except Exception as e:
        logger.warning("Live Fama-French fetch failed: %s", e)
        return None


def factor_provenance() -> dict:
    """Disclosed provenance of the factor data currently being served."""
    return {
        "ff5": _FACTOR_CACHE.get("ff5_provenance", {"mode": "not_loaded"}),
        "mom": _FACTOR_CACHE.get("mom_provenance", {"mode": "not_loaded"}),
    }


def get_factor_data(lookback_days: Optional[int] = None) -> Optional[pd.DataFrame]:
    """Fama-French 5-factor daily returns: pinned vintage + disclosed live tail.

    Returns DataFrame with columns: Mkt-RF, SMB, HML, RMW, CMA, RF
    Values are daily returns in decimal form (e.g., 0.01 = 1%).
    Provenance of the served frame is available via factor_provenance().
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

    pinned, pin_meta = _load_pinned()
    live = _fetch_ff5_live()

    if pinned is not None:
        base = pinned[_FF5_COLS].dropna()
        if live is not None:
            tail = live[live.index > base.index[-1]]
            df = pd.concat([base, tail]) if len(tail) else base
            mode = "pinned+live_append"
        else:
            df = base
            mode = "pinned_only"
        prov = {
            "mode": mode,
            "vintage_date": pin_meta.get("vintage_date"),
            "sha256_prefix": str(pin_meta.get("sha256"))[:12],
            "pinned_through": pin_meta.get("ff5_end"),
            "extended_through": str(df.index[-1].date()),
        }
    elif live is not None:
        df = live
        prov = {"mode": "live_unpinned", "pin_status": pin_meta.get("status")}
    else:
        _FACTOR_CACHE["ff5_provenance"] = {
            "mode": "unavailable", "pin_status": pin_meta.get("status"),
        }
        logger.warning("Fama-French data unavailable (no pin, live fetch failed)")
        return None

    _FACTOR_CACHE[cache_key] = df
    _FACTOR_CACHE_TS[cache_key] = now
    _FACTOR_CACHE["ff5_provenance"] = prov

    logger.info("Loaded %d days of Fama-French 5-factor data (%s)", len(df), prov["mode"])

    if lookback_days and len(df) > lookback_days:
        return df.iloc[-lookback_days:]
    return df


def _fetch_french_daily_csv(url: str, col_name: str) -> Optional[pd.DataFrame]:
    """Download a Kenneth French daily-factor zip and parse it robustly:
    keep only rows that start with an 8-digit date, drop the -99.99/-999
    missing markers, convert percent -> decimal. Immune to preamble/footer
    format drift that breaks pandas_datareader."""
    import io
    import re
    import zipfile

    import requests

    r = requests.get(url, timeout=60)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        text = zf.read(zf.namelist()[0]).decode("utf-8", errors="replace")

    dates, vals = [], []
    row_re = re.compile(r"^\s*(\d{8})\s*,\s*(-?\d+(?:\.\d+)?)")
    for line in text.splitlines():
        m = row_re.match(line)
        if not m:
            continue
        v = float(m.group(2))
        if v <= -99.0:  # French library missing-data markers
            continue
        dates.append(m.group(1))
        vals.append(v / 100.0)
    if not dates:
        return None
    df = pd.DataFrame({col_name: vals},
                      index=pd.to_datetime(dates, format="%Y%m%d"))
    return df.sort_index()


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
        "factor_data_provenance": _FACTOR_CACHE.get("ff5_provenance", {"mode": "not_loaded"}),
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


def _fetch_mom_live() -> Optional[pd.DataFrame]:
    """Live daily momentum fetch.

    pandas_datareader's famafrench parser breaks on the current momentum CSV
    (its preamble line "Missing data are indicated by -99.99..." lands in the
    date column -> DateParseError locally, str/float compare in prod). Caught
    live 2026-07-19: FF6 silently degraded to FF5 everywhere. Fetch + parse
    the file directly.
    """
    try:
        df = _fetch_french_daily_csv(
            "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
            "F-F_Momentum_Factor_daily_CSV.zip",
            col_name="Mom",
        )
        if df is None:
            raise ValueError("momentum CSV parse yielded no rows")
        return df
    except Exception as e:
        logger.warning("Live Momentum factor fetch failed: %s", e)
        return None


def get_momentum_factor(lookback_days: Optional[int] = None) -> Optional[pd.DataFrame]:
    """Carhart Momentum (UMD) daily returns: pinned vintage + disclosed live tail.

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

    pinned, pin_meta = _load_pinned()
    live = _fetch_mom_live()

    if pinned is not None and "Mom" in pinned.columns:
        base = pinned[["Mom"]].dropna()
        if live is not None:
            tail = live[live.index > base.index[-1]]
            df = pd.concat([base, tail]) if len(tail) else base
            mode = "pinned+live_append"
        else:
            df = base
            mode = "pinned_only"
        prov = {
            "mode": mode,
            "vintage_date": pin_meta.get("vintage_date"),
            "sha256_prefix": str(pin_meta.get("sha256"))[:12],
            "pinned_through": pin_meta.get("mom_end"),
            "extended_through": str(df.index[-1].date()),
        }
    elif live is not None:
        df = live
        prov = {"mode": "live_unpinned", "pin_status": pin_meta.get("status")}
    else:
        _FACTOR_CACHE["mom_provenance"] = {
            "mode": "unavailable", "pin_status": pin_meta.get("status"),
        }
        logger.warning("Momentum factor unavailable (no pin, live fetch failed)")
        return None

    _FACTOR_CACHE[cache_key] = df
    _FACTOR_CACHE_TS[cache_key] = now
    _FACTOR_CACHE["mom_provenance"] = prov

    logger.info("Loaded %d days of Momentum factor data (%s)", len(df), prov["mode"])

    if lookback_days and len(df) > lookback_days:
        return df.iloc[-lookback_days:]
    return df


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

    # Factor-lens additions (F-018): historical premium earned by each factor
    # over THIS regression window, and contribution = loading x premium —
    # "this factor earned you X%/yr". Premiums are realized averages, not
    # forecasts; the frontend states this.
    for name in factor_names:
        premium_annual = float(combined[name].mean() * 252)
        fd = factor_details[name]
        fd["premium_annual"] = round(premium_annual, 4)
        fd["contribution_annual"] = round(
            float(factor_loadings[name]) * premium_annual, 4)

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
        "rolling": _rolling_loadings(combined, factor_names),
        "residuals": residuals,  # For PCA analysis
        "factor_data_provenance": factor_provenance(),
    }


def _rolling_loadings(combined: pd.DataFrame, factor_names: list[str],
                      window: int = 252, step: int = 21) -> Optional[dict]:
    """Rolling-window OLS loadings (monthly steps, 1y window) — the
    presentation gap F-018 identified: static loadings hide regime shifts.
    Returns None when the sample supports fewer than 4 windows."""
    n = len(combined)
    if n < window + 3 * step:
        return None
    y_all = (combined["stock_ret"] - combined["RF"]).values
    X_all = combined[factor_names].values
    dates, series = [], {f: [] for f in factor_names}
    for end in range(window, n + 1, step):
        Xw = np.column_stack([np.ones(window), X_all[end - window:end]])
        try:
            b, _, _, _ = np.linalg.lstsq(Xw, y_all[end - window:end], rcond=None)
        except np.linalg.LinAlgError:
            continue
        dates.append(str(combined.index[end - 1].date()))
        for i, f in enumerate(factor_names):
            series[f].append(round(float(b[i + 1]), 3))
    if len(dates) < 4:
        return None
    return {"dates": dates, "window_days": window, **series}


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

    portfolio_r2 = 0.0
    for ticker, data in stock_results.items():
        w = data["weight"] / total_weight if total_weight > 0 else 0
        decomp = data["decomposition"]
        portfolio_alpha += w * decomp["alpha_annual"]
        portfolio_r2 += w * decomp.get("r_squared", 0.0)
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
        "portfolio_r_squared": round(portfolio_r2, 4),
        "portfolio_factors": {
            f: round(v, 4) for f, v in portfolio_loadings.items()
        },
        "portfolio_style": style,
        "risk_attribution": risk_attribution,
        "stocks_analyzed": len(stock_results),
        "stocks_failed": len(weights) - len(stock_results),
        "stock_details": stock_results,
    }
