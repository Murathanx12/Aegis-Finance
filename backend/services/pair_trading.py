"""
Aegis Finance — Pair Trading & Cointegration Scanner
=======================================================

Statistical arbitrage pair detection using cointegration analysis.
This is a core quant feature found in Bloomberg PORT and institutional
trading desks but rarely in retail platforms.

Methodology:
1. Engle-Granger two-step cointegration test (ADF on spread residuals)
2. Johansen trace test for multivariate cointegration
3. Ornstein-Uhlenbeck half-life estimation (mean-reversion speed)
4. Rolling OLS hedge ratio with Kalman-style exponential weighting
5. Z-score of spread with configurable entry/exit thresholds
6. Hurst exponent for mean-reversion confirmation (H < 0.5)

Signals:
  - z_score > +entry_z  → Short the spread (sell A, buy B)
  - z_score < -entry_z  → Long the spread (buy A, sell B)
  - |z_score| < exit_z  → Close position (mean reversion complete)

References:
  - Engle & Granger (1987), "Co-integration and Error Correction"
  - Johansen (1991), "Estimation and Hypothesis Testing of Cointegration"
  - Vidyamurthy (2004), "Pairs Trading: Quantitative Methods and Analysis"
  - Avellaneda & Lee (2010), "Statistical Arbitrage in the US Equities Market"
  - Gatev, Goetzmann & Rouwenhorst (2006), "Pairs Trading: Performance of a Relative Value Arbitrage Rule"

Usage:
    from backend.services.pair_trading import (
        analyze_pair, scan_pairs, get_pair_signal,
        compute_half_life, compute_hurst_exponent
    )
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

from backend.config import config

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────

_PAIR_CFG = config.get("pair_trading", {})
_LOOKBACK = _PAIR_CFG.get("lookback_days", 504)
_MIN_OBS = _PAIR_CFG.get("min_observations", 126)
_COINT_PVALUE = _PAIR_CFG.get("cointegration_pvalue", 0.05)
_ENTRY_Z = _PAIR_CFG.get("entry_z", 2.0)
_EXIT_Z = _PAIR_CFG.get("exit_z", 0.5)
_STOP_Z = _PAIR_CFG.get("stop_z", 4.0)
_MAX_HALF_LIFE = _PAIR_CFG.get("max_half_life_days", 126)
_MIN_HALF_LIFE = _PAIR_CFG.get("min_half_life_days", 5)
_Z_WINDOW = _PAIR_CFG.get("z_score_window", 63)
_HEDGE_WINDOW = _PAIR_CFG.get("hedge_ratio_window", 63)
_SCAN_WORKERS = _PAIR_CFG.get("scan_workers", 6)
_TOP_PAIRS = _PAIR_CFG.get("top_pairs", 20)


# ══════════════════════════════════════════════════════════════════════════════
# COINTEGRATION TESTS
# ══════════════════════════════════════════════════════════════════════════════


def _adf_test(series: np.ndarray) -> dict:
    """Augmented Dickey-Fuller test for stationarity."""
    try:
        from statsmodels.tsa.stattools import adfuller
        result = adfuller(series, maxlag=None, autolag="AIC")
        return {
            "adf_statistic": float(result[0]),
            "p_value": float(result[1]),
            "lags_used": int(result[2]),
            "n_obs": int(result[3]),
            "critical_values": {k: float(v) for k, v in result[4].items()},
            "is_stationary": result[1] < _COINT_PVALUE,
        }
    except Exception as e:
        logger.warning("ADF test failed: %s", e)
        return {"adf_statistic": None, "p_value": 1.0, "is_stationary": False}


def engle_granger_test(
    y: np.ndarray, x: np.ndarray
) -> dict:
    """Engle-Granger two-step cointegration test.

    Step 1: Regress y on x to get residuals (spread)
    Step 2: ADF test on residuals — if stationary, pair is cointegrated
    """
    n = len(y)
    if n < _MIN_OBS:
        return {
            "cointegrated": False,
            "p_value": 1.0,
            "error": f"Insufficient data: {n} < {_MIN_OBS}",
        }

    # OLS regression: y = alpha + beta * x + epsilon
    x_with_const = np.column_stack([np.ones(n), x])
    try:
        beta, _, _, _ = np.linalg.lstsq(x_with_const, y, rcond=None)
    except np.linalg.LinAlgError:
        return {"cointegrated": False, "p_value": 1.0, "error": "OLS failed"}

    alpha, hedge_ratio = float(beta[0]), float(beta[1])
    residuals = y - (alpha + hedge_ratio * x)

    # ADF test on residuals
    adf = _adf_test(residuals)

    return {
        "cointegrated": adf["is_stationary"],
        "p_value": adf["p_value"],
        "adf_statistic": adf["adf_statistic"],
        "critical_values": adf.get("critical_values", {}),
        "hedge_ratio": hedge_ratio,
        "intercept": alpha,
        "residual_std": float(np.std(residuals)),
    }


def johansen_test(prices_a: np.ndarray, prices_b: np.ndarray) -> dict:
    """Johansen trace test for cointegration rank.

    Returns the number of cointegrating relationships (0, 1, or 2).
    """
    try:
        from statsmodels.tsa.vector_ar.vecm import coint_johansen

        data = np.column_stack([prices_a, prices_b])
        # det_order=0: constant in cointegrating relation
        # k_ar_diff=1: VAR lag order
        result = coint_johansen(data, det_order=0, k_ar_diff=1)

        trace_stats = result.lr1.tolist()
        crit_90 = result.cvt[:, 0].tolist()
        crit_95 = result.cvt[:, 1].tolist()
        crit_99 = result.cvt[:, 2].tolist()

        # Count how many cointegrating vectors at 5% significance
        n_coint = sum(
            1 for ts, cv in zip(trace_stats, crit_95) if ts > cv
        )

        return {
            "n_cointegrating_vectors": n_coint,
            "trace_statistics": trace_stats,
            "critical_values_95": crit_95,
            "critical_values_99": crit_99,
            "cointegrated": n_coint >= 1,
            "eigenvectors": result.evec.tolist(),
        }
    except Exception as e:
        logger.warning("Johansen test failed: %s", e)
        return {
            "n_cointegrating_vectors": 0,
            "cointegrated": False,
            "error": str(e),
        }


# ══════════════════════════════════════════════════════════════════════════════
# MEAN-REVERSION METRICS
# ══════════════════════════════════════════════════════════════════════════════


def compute_half_life(spread: np.ndarray) -> float:
    """Ornstein-Uhlenbeck half-life of mean reversion.

    Fits: Δspread_t = θ * (spread_{t-1} - μ) + ε
    Half-life = -ln(2) / ln(1 + θ) ≈ -ln(2) / θ

    Returns half-life in trading days. Lower = faster mean reversion.
    """
    if len(spread) < 20:
        return float("inf")

    spread_lag = spread[:-1]
    spread_diff = np.diff(spread)

    # Remove any NaN/inf
    mask = np.isfinite(spread_lag) & np.isfinite(spread_diff)
    if mask.sum() < 20:
        return float("inf")

    spread_lag = spread_lag[mask]
    spread_diff = spread_diff[mask]

    # OLS: Δspread = alpha + theta * spread_lag
    x = np.column_stack([np.ones(len(spread_lag)), spread_lag])
    try:
        beta, _, _, _ = np.linalg.lstsq(x, spread_diff, rcond=None)
    except np.linalg.LinAlgError:
        return float("inf")

    theta = beta[1]
    if theta >= 0:
        # Not mean-reverting (random walk or momentum)
        return float("inf")

    half_life = -np.log(2) / theta
    return float(half_life)


def compute_hurst_exponent(series: np.ndarray, max_lag: int = 100) -> float:
    """Hurst exponent via rescaled range (R/S) analysis.

    H < 0.5: Mean-reverting (good for pairs trading)
    H = 0.5: Random walk (no edge)
    H > 0.5: Trending (bad for pairs trading)
    """
    n = len(series)
    if n < 40:
        return 0.5  # Default to random walk

    max_lag = min(max_lag, n // 4)
    lags = range(10, max_lag + 1)
    rs_values = []

    for lag in lags:
        rs_list = []
        for start in range(0, n - lag, lag):
            chunk = series[start: start + lag]
            mean_chunk = np.mean(chunk)
            deviations = np.cumsum(chunk - mean_chunk)
            r = np.max(deviations) - np.min(deviations)
            s = np.std(chunk, ddof=1)
            if s > 1e-10:
                rs_list.append(r / s)
        if rs_list:
            rs_values.append((np.log(lag), np.log(np.mean(rs_list))))

    if len(rs_values) < 3:
        return 0.5

    log_lags, log_rs = zip(*rs_values)
    log_lags = np.array(log_lags)
    log_rs = np.array(log_rs)

    # Linear regression: log(R/S) = H * log(lag) + c
    slope, _, _, _, _ = stats.linregress(log_lags, log_rs)
    return float(np.clip(slope, 0.0, 1.0))


def compute_spread(
    prices_a: np.ndarray,
    prices_b: np.ndarray,
    hedge_ratio: float,
    intercept: float = 0.0,
) -> np.ndarray:
    """Compute the cointegration spread: spread = A - hedge_ratio * B - intercept."""
    return prices_a - hedge_ratio * prices_b - intercept


def compute_z_score(
    spread: np.ndarray, window: int = _Z_WINDOW
) -> np.ndarray:
    """Rolling z-score of the spread."""
    if len(spread) < window:
        window = max(len(spread) // 2, 10)

    s = pd.Series(spread)
    rolling_mean = s.rolling(window=window).mean()
    rolling_std = s.rolling(window=window).std()
    z = (s - rolling_mean) / rolling_std.replace(0, np.nan)
    return z.fillna(0.0).values


def rolling_hedge_ratio(
    prices_a: np.ndarray,
    prices_b: np.ndarray,
    window: int = _HEDGE_WINDOW,
) -> np.ndarray:
    """Rolling OLS hedge ratio (exponentially weighted)."""
    n = len(prices_a)
    ratios = np.full(n, np.nan)

    for i in range(window, n):
        y = prices_a[i - window: i]
        x = prices_b[i - window: i]
        x_with_const = np.column_stack([np.ones(window), x])
        try:
            beta, _, _, _ = np.linalg.lstsq(x_with_const, y, rcond=None)
            ratios[i] = beta[1]
        except np.linalg.LinAlgError:
            if i > window:
                ratios[i] = ratios[i - 1]

    # Forward-fill initial NaNs
    first_valid = window
    if first_valid < n:
        ratios[:first_valid] = ratios[first_valid]

    return ratios


# ══════════════════════════════════════════════════════════════════════════════
# PAIR ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════


def _get_signal(z_score: float) -> dict:
    """Determine trading signal from current z-score."""
    if z_score > _STOP_Z:
        return {"action": "stop_loss", "direction": "short_spread", "strength": "extreme"}
    elif z_score > _ENTRY_Z:
        return {"action": "short_spread", "direction": "sell_A_buy_B", "strength": "strong" if z_score > 3.0 else "moderate"}
    elif z_score < -_STOP_Z:
        return {"action": "stop_loss", "direction": "long_spread", "strength": "extreme"}
    elif z_score < -_ENTRY_Z:
        return {"action": "long_spread", "direction": "buy_A_sell_B", "strength": "strong" if z_score < -3.0 else "moderate"}
    elif abs(z_score) < _EXIT_Z:
        return {"action": "close", "direction": "neutral", "strength": "converged"}
    else:
        return {"action": "hold", "direction": "neutral", "strength": "waiting"}


def analyze_pair(
    prices_a: np.ndarray,
    prices_b: np.ndarray,
    ticker_a: str = "A",
    ticker_b: str = "B",
) -> dict:
    """Full cointegration analysis for a pair of price series.

    Returns hedge ratio, cointegration test results, half-life,
    Hurst exponent, current z-score, and trading signal.
    """
    n = min(len(prices_a), len(prices_b))
    if n < _MIN_OBS:
        return {
            "pair": f"{ticker_a}/{ticker_b}",
            "error": f"Insufficient data: {n} < {_MIN_OBS}",
            "cointegrated": False,
        }

    # Align lengths
    prices_a = prices_a[-n:]
    prices_b = prices_b[-n:]

    # ── Cointegration Tests ──
    eg_result = engle_granger_test(prices_a, prices_b)
    joh_result = johansen_test(prices_a, prices_b)

    hedge_ratio = eg_result.get("hedge_ratio", 1.0)
    intercept = eg_result.get("intercept", 0.0)

    # ── Spread & Z-Score ──
    spread = compute_spread(prices_a, prices_b, hedge_ratio, intercept)
    z_scores = compute_z_score(spread)
    current_z = float(z_scores[-1]) if len(z_scores) > 0 else 0.0

    # ── Mean-Reversion Metrics ──
    half_life = compute_half_life(spread)
    hurst = compute_hurst_exponent(spread)

    # ── Correlation ──
    returns_a = np.diff(np.log(np.maximum(prices_a, 1e-8)))
    returns_b = np.diff(np.log(np.maximum(prices_b, 1e-8)))
    min_ret = min(len(returns_a), len(returns_b))
    if min_ret > 10:
        correlation = float(np.corrcoef(returns_a[-min_ret:], returns_b[-min_ret:])[0, 1])
    else:
        correlation = 0.0

    # ── Rolling hedge ratio (last value) ──
    rolling_hr = rolling_hedge_ratio(prices_a, prices_b)
    hr_stability = float(np.std(rolling_hr[~np.isnan(rolling_hr)])) if np.any(~np.isnan(rolling_hr)) else 0.0

    # ── Signal ──
    signal = _get_signal(current_z)

    # ── Composite score (higher = better pair) ──
    # Factors: cointegration p-value (lower better), half-life (moderate better),
    # Hurst (lower better), hedge ratio stability
    score = _compute_pair_score(
        eg_pvalue=eg_result.get("p_value", 1.0),
        joh_coint=joh_result.get("cointegrated", False),
        half_life=half_life,
        hurst=hurst,
        hr_stability=hr_stability,
        correlation=correlation,
    )

    # ── Recent spread history for charting ──
    chart_len = min(252, len(spread))
    spread_history = spread[-chart_len:].tolist()
    z_history = z_scores[-chart_len:].tolist()

    return {
        "pair": f"{ticker_a}/{ticker_b}",
        "ticker_a": ticker_a,
        "ticker_b": ticker_b,
        "cointegration": {
            "engle_granger": {
                "cointegrated": eg_result.get("cointegrated", False),
                "p_value": eg_result.get("p_value", 1.0),
                "adf_statistic": eg_result.get("adf_statistic"),
                "critical_values": eg_result.get("critical_values", {}),
            },
            "johansen": {
                "cointegrated": joh_result.get("cointegrated", False),
                "n_vectors": joh_result.get("n_cointegrating_vectors", 0),
                "trace_statistics": joh_result.get("trace_statistics", []),
            },
            "is_cointegrated": eg_result.get("cointegrated", False) or joh_result.get("cointegrated", False),
        },
        "hedge_ratio": hedge_ratio,
        "intercept": intercept,
        "hedge_ratio_stability": hr_stability,
        "spread_std": eg_result.get("residual_std", 0.0),
        "half_life_days": half_life if np.isfinite(half_life) else None,
        "hurst_exponent": hurst,
        "mean_reverting": hurst < 0.5 and np.isfinite(half_life) and half_life < _MAX_HALF_LIFE,
        "correlation": correlation,
        "current_z_score": current_z,
        "signal": signal,
        "pair_quality_score": score,
        "spread_history": spread_history,
        "z_score_history": z_history,
        "thresholds": {
            "entry_z": _ENTRY_Z,
            "exit_z": _EXIT_Z,
            "stop_z": _STOP_Z,
        },
        "n_observations": n,
    }


def _compute_pair_score(
    eg_pvalue: float,
    joh_coint: bool,
    half_life: float,
    hurst: float,
    hr_stability: float,
    correlation: float,
) -> float:
    """Composite pair quality score (0-100). Higher = better pair for trading."""
    score = 0.0

    # Cointegration p-value (0-30 points)
    if eg_pvalue < 0.01:
        score += 30
    elif eg_pvalue < 0.05:
        score += 20
    elif eg_pvalue < 0.10:
        score += 10

    # Johansen confirmation bonus (0-10 points)
    if joh_coint:
        score += 10

    # Half-life quality (0-25 points) — ideal: 10-60 days
    if np.isfinite(half_life):
        if _MIN_HALF_LIFE <= half_life <= 60:
            score += 25
        elif half_life <= _MAX_HALF_LIFE:
            score += 15
        elif half_life <= 252:
            score += 5

    # Hurst exponent (0-20 points) — lower is more mean-reverting
    if hurst < 0.35:
        score += 20
    elif hurst < 0.45:
        score += 15
    elif hurst < 0.50:
        score += 10

    # Hedge ratio stability (0-10 points) — lower std is more stable
    if hr_stability < 0.1:
        score += 10
    elif hr_stability < 0.3:
        score += 5

    # Correlation bonus (0-5 points) — higher correlation helps
    if correlation > 0.7:
        score += 5
    elif correlation > 0.5:
        score += 3

    return float(min(score, 100))


# ══════════════════════════════════════════════════════════════════════════════
# PAIR SCANNER (UNIVERSE-WIDE)
# ══════════════════════════════════════════════════════════════════════════════


def scan_pairs(
    tickers: list[str],
    lookback_days: int = _LOOKBACK,
    top_n: int = _TOP_PAIRS,
    sector_filter: Optional[str] = None,
) -> dict:
    """Scan a universe of tickers for cointegrated pairs.

    Uses a two-pass approach:
    1. Fast correlation pre-filter (skip uncorrelated pairs)
    2. Full cointegration test on promising pairs

    Returns top N pairs ranked by pair_quality_score.
    """
    import yfinance as yf
    from concurrent.futures import ThreadPoolExecutor

    # Get sector mapping
    sector_stocks = config.get("stock_universe", {}).get("sector_stocks", {})
    ticker_sector = {}
    for sector, stocks in sector_stocks.items():
        for t in stocks:
            ticker_sector[t] = sector

    # Filter by sector if requested
    if sector_filter:
        tickers = [t for t in tickers if ticker_sector.get(t) == sector_filter]

    if len(tickers) < 2:
        return {"pairs": [], "error": "Need at least 2 tickers"}

    # ── Fetch prices ──
    logger.info("Pair scanner: fetching %d tickers", len(tickers))
    try:
        from backend.services.data_fetcher import _yf_lock, _safe_download_single
        end = pd.Timestamp.now()
        start = end - pd.Timedelta(days=int(lookback_days * 1.5))

        # Download all at once
        with _yf_lock:
            data = yf.download(
                tickers, start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"), progress=False, auto_adjust=True,
            )

        if data.empty:
            return {"pairs": [], "error": "No price data returned"}

        # Extract close prices
        if isinstance(data.columns, pd.MultiIndex):
            prices_df = data["Close"]
        else:
            prices_df = data[["Close"]]
            prices_df.columns = tickers[:1]

        # Drop tickers with too few observations
        prices_df = prices_df.dropna(axis=1, thresh=_MIN_OBS)
        valid_tickers = list(prices_df.columns)
    except Exception as e:
        logger.error("Pair scanner price fetch failed: %s", e)
        return {"pairs": [], "error": str(e)}

    if len(valid_tickers) < 2:
        return {"pairs": [], "error": "Insufficient valid tickers after filtering"}

    # ── Pass 1: Correlation pre-filter ──
    returns_df = prices_df.pct_change().dropna()
    corr_matrix = returns_df.corr()

    # Generate candidate pairs (correlation > 0.3)
    candidates = []
    for i in range(len(valid_tickers)):
        for j in range(i + 1, len(valid_tickers)):
            t_a, t_b = valid_tickers[i], valid_tickers[j]
            corr = corr_matrix.loc[t_a, t_b]
            if abs(corr) > 0.3:  # Pre-filter threshold
                candidates.append((t_a, t_b, corr))

    logger.info("Pair scanner: %d candidates from %d possible pairs",
                len(candidates), len(valid_tickers) * (len(valid_tickers) - 1) // 2)

    # ── Pass 2: Cointegration tests ──
    results = []

    def _test_pair(pair_info):
        t_a, t_b, corr = pair_info
        try:
            pa = prices_df[t_a].dropna().values
            pb = prices_df[t_b].dropna().values
            n = min(len(pa), len(pb))
            pa = pa[-n:]
            pb = pb[-n:]
            analysis = analyze_pair(pa, pb, t_a, t_b)
            # Add sector info
            analysis["sector_a"] = ticker_sector.get(t_a, "Unknown")
            analysis["sector_b"] = ticker_sector.get(t_b, "Unknown")
            analysis["same_sector"] = analysis["sector_a"] == analysis["sector_b"]
            return analysis
        except Exception as e:
            logger.debug("Pair %s/%s failed: %s", t_a, t_b, e)
            return None

    with ThreadPoolExecutor(max_workers=_SCAN_WORKERS) as pool:
        pair_results = list(pool.map(_test_pair, candidates))

    for r in pair_results:
        if r is not None and "error" not in r:
            results.append(r)

    # Sort by quality score
    results.sort(key=lambda x: x.get("pair_quality_score", 0), reverse=True)

    # Trim chart data for scanner results (save bandwidth)
    for r in results:
        r.pop("spread_history", None)
        r.pop("z_score_history", None)

    top_results = results[:top_n]

    # Summary stats
    n_cointegrated = sum(1 for r in results if r.get("cointegration", {}).get("is_cointegrated", False))
    n_mean_reverting = sum(1 for r in results if r.get("mean_reverting", False))

    return {
        "pairs": top_results,
        "summary": {
            "tickers_scanned": len(valid_tickers),
            "total_candidates": len(candidates),
            "pairs_tested": len(results),
            "cointegrated_pairs": n_cointegrated,
            "mean_reverting_pairs": n_mean_reverting,
            "top_score": top_results[0]["pair_quality_score"] if top_results else 0,
        },
    }


def get_pair_signal(ticker_a: str, ticker_b: str, lookback_days: int = _LOOKBACK) -> dict:
    """Quick signal check for a specific pair. Returns current z-score and action."""
    import yfinance as yf
    from backend.services.data_fetcher import _yf_lock

    end = pd.Timestamp.now()
    start = end - pd.Timedelta(days=int(lookback_days * 1.5))

    try:
        with _yf_lock:
            data = yf.download(
                [ticker_a, ticker_b],
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                progress=False, auto_adjust=True,
            )
        if data.empty:
            return {"error": "No data"}

        if isinstance(data.columns, pd.MultiIndex):
            pa = data["Close"][ticker_a].dropna().values
            pb = data["Close"][ticker_b].dropna().values
        else:
            return {"error": "Single ticker returned"}

        return analyze_pair(pa, pb, ticker_a, ticker_b)
    except Exception as e:
        return {"error": str(e)}
