"""
Feature & Target Builders for ML Pipeline
===========================================

Builds 80+ backward-looking ML features from market data and optional
FRED macro time series. Features span these categories:

    1. Price momentum & returns (multiple horizons)
    2. Volatility (realized, ratios, higher moments)
    3. Trend & technical (SMA, EMA, RSI, MACD, Bollinger)
    4. Fixed income & macro (yields, spreads, VIX dynamics)
    5. Tail risk (drawdowns, downside measures, CVaR)
    6. Cross-asset (gold/equity, bond/equity, breadth)
    7. Interaction features (vol*mom, vix*spread, etc.)
    8. FRED macro time series (if provided)

ALL features are strictly backward-looking — no future data leakage.

Adapted from V7 engine (market-prediction-engine).

Usage:
    from engine.training.features import build_feature_matrix, build_target_crash_multi
"""

from typing import Dict

import numpy as np
import pandas as pd


# ══════════════════════════════════════════════════════════════════════════════
# MAIN FEATURE BUILDER
# ══════════════════════════════════════════════════════════════════════════════


def build_feature_matrix(
    data: pd.DataFrame, fred_data: dict = None
) -> pd.DataFrame:
    """Build 80+ backward-looking features from market data and optional FRED macro.

    Args:
        data: DataFrame with columns SP500, VIX, T10Y, T3M, Gold, NASDAQ,
              Russell, HYG, LQD, etc. (missing columns handled gracefully)
        fred_data: Optional dict of FRED time series

    Returns:
        DataFrame aligned with data.index, all features backward-looking
    """
    df = pd.DataFrame(index=data.index)
    sp = data["SP500"]

    # ══════════════════════════════════════════════════════════════════
    # 1. CORE RETURNS
    # ══════════════════════════════════════════════════════════════════
    df["daily_ret"] = sp.pct_change()
    df["log_ret"] = np.log(1 + df["daily_ret"]).replace(
        [np.inf, -np.inf], np.nan
    )

    # ══════════════════════════════════════════════════════════════════
    # 2. PRICE MOMENTUM (multiple horizons)
    # ══════════════════════════════════════════════════════════════════
    for days, name in [
        (5, "1w"), (10, "2w"), (21, "1m"), (42, "2m"),
        (63, "3m"), (126, "6m"), (252, "12m"),
    ]:
        df[f"mom_{name}"] = sp.pct_change(days)

    # Distance from 52-week high and low
    high_252 = sp.rolling(252).max()
    low_252 = sp.rolling(252).min()
    df["dist_52w_high"] = (sp - high_252) / high_252
    df["dist_52w_low"] = (sp - low_252) / low_252
    df["drawdown_from_peak"] = df["dist_52w_high"]

    # ══════════════════════════════════════════════════════════════════
    # 3. VOLATILITY (realized, ratios, higher moments)
    # ══════════════════════════════════════════════════════════════════
    log_ret = df["log_ret"]
    for days, name in [
        (5, "1w"), (10, "2w"), (21, "1m"), (63, "3m"),
        (126, "6m"), (252, "12m"),
    ]:
        df[f"vol_{name}"] = log_ret.rolling(days).std()

    df["vol_ratio_1m_3m"] = df["vol_1m"] / df["vol_3m"].replace(0, np.nan)
    df["vol_ratio_1m_12m"] = df["vol_1m"] / df["vol_12m"].replace(0, np.nan)
    df["vol_ratio_1w_1m"] = df["vol_1w"] / df["vol_1m"].replace(0, np.nan)
    df["vol_of_vol"] = df["vol_1m"].rolling(63).std()

    df["realized_skew"] = log_ret.rolling(63).skew()
    df["realized_kurt"] = log_ret.rolling(63).apply(
        lambda x: pd.Series(x).kurtosis(), raw=False
    )

    df["max_daily_loss_21d"] = log_ret.rolling(21).min()
    df["max_daily_loss_63d"] = log_ret.rolling(63).min()

    vol_12m_mean = df["vol_1m"].rolling(252).mean()
    vol_12m_std = df["vol_1m"].rolling(252).std()
    df["vol_zscore"] = (df["vol_1m"] - vol_12m_mean) / vol_12m_std.replace(
        0, np.nan
    )

    # ══════════════════════════════════════════════════════════════════
    # 4. TREND & TECHNICAL INDICATORS
    # ══════════════════════════════════════════════════════════════════
    for days, name in [(50, "50d"), (100, "100d"), (200, "200d")]:
        sma = sp.rolling(days).mean()
        df[f"sma_{name}_dev"] = (sp - sma) / sma

    sma_50 = sp.rolling(50).mean()
    sma_200 = sp.rolling(200).mean()
    df["golden_cross"] = (sma_50 > sma_200).astype(float)

    ema_12 = sp.ewm(span=12, adjust=False).mean()
    ema_26 = sp.ewm(span=26, adjust=False).mean()
    macd_line = ema_12 - ema_26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    df["macd_signal"] = (macd_line - macd_signal) / sp

    delta = sp.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi_14d"] = 100 - (100 / (1 + rs))
    df["rsi_14d_norm"] = df["rsi_14d"] / 100

    bb_mid = sp.rolling(20).mean()
    bb_std = sp.rolling(20).std()
    df["bollinger_pos"] = (sp - bb_mid) / (2 * bb_std).replace(0, np.nan)

    df["trend_strength_3m"] = df["mom_3m"] / df["vol_3m"].replace(0, np.nan)
    df["trend_strength_12m"] = df["mom_12m"] / df["vol_12m"].replace(0, np.nan)

    # ══════════════════════════════════════════════════════════════════
    # 5. FIXED INCOME & VIX DYNAMICS
    # ══════════════════════════════════════════════════════════════════
    if "VIX" in data.columns:
        vix = data["VIX"].ffill()
        df["vix"] = vix
        df["vix_change_1m"] = vix.pct_change(21)
        df["vix_change_3m"] = vix.pct_change(63)
        vix_mean = vix.rolling(252).mean()
        vix_std = vix.rolling(252).std()
        df["vix_zscore"] = (vix - vix_mean) / vix_std.replace(0, np.nan)
        realized_vol_annual = df["vol_1m"] * np.sqrt(252) * 100
        df["vix_term_structure"] = (vix - realized_vol_annual) / vix.replace(
            0, np.nan
        )

    if "T10Y" in data.columns:
        df["yield_10y"] = data["T10Y"]
        df["yield_10y_change_1m"] = data["T10Y"].diff(21)
        df["yield_10y_change_3m"] = data["T10Y"].diff(63)

    if "T3M" in data.columns:
        df["yield_3m"] = data["T3M"]

    if "T10Y" in data.columns and "T3M" in data.columns:
        spread = data["T10Y"] - data["T3M"]
        df["term_spread"] = spread
        df["term_spread_change_1m"] = spread.diff(21)
        df["term_spread_change_3m"] = spread.diff(63)
        df["yield_curve_inverted"] = (spread < 0).astype(float)

    if "T30Y" in data.columns and "T10Y" in data.columns:
        df["long_short_spread"] = data["T30Y"] - data["T10Y"]

    if "VIX" in data.columns and "VIX3M" in data.columns:
        vix3m = data["VIX3M"].ffill()
        df["vix_term_structure_ratio"] = data["VIX"].ffill() / vix3m.replace(
            0, np.nan
        )
        df["vix_backwardation"] = (
            df["vix_term_structure_ratio"] > 1.0
        ).astype(float)

    if "SKEW" in data.columns:
        skew_data = data["SKEW"].ffill()
        df["skew_index"] = skew_data
        skew_mean = skew_data.rolling(252).mean()
        skew_std = skew_data.rolling(252).std()
        df["skew_zscore"] = (skew_data - skew_mean) / skew_std.replace(
            0, np.nan
        )
        df["skew_elevated"] = (skew_data > 145).astype(float)

    if "HYG" in data.columns and "LQD" in data.columns:
        credit_ratio = data["HYG"] / data["LQD"].replace(0, np.nan)
        df["credit_spread_proxy"] = credit_ratio.pct_change(21)
        df["credit_spread_level"] = credit_ratio

    # ══════════════════════════════════════════════════════════════════
    # 6. TAIL RISK FEATURES
    # ══════════════════════════════════════════════════════════════════
    for days, name in [(63, "3m"), (252, "12m")]:
        rolling_max = sp.rolling(days).max()
        dd = (sp - rolling_max) / rolling_max
        df[f"max_drawdown_{name}"] = dd.rolling(days).min()

    neg_ret = log_ret.clip(upper=0)
    df["lower_partial_moment"] = neg_ret.rolling(63).apply(
        lambda x: np.sqrt((x**2).mean()), raw=True
    )
    df["cvar_5pct_63d"] = log_ret.rolling(63).apply(
        lambda x: x[x <= np.percentile(x, 5)].mean() if len(x) > 5 else np.nan,
        raw=True,
    )
    df["neg_day_ratio_21d"] = (log_ret < 0).rolling(21).mean()
    df["neg_day_ratio_63d"] = (log_ret < 0).rolling(63).mean()

    is_down = (log_ret < 0).astype(float)
    not_down = (is_down == 0).astype(float)
    group = not_down.cumsum()
    df["down_streak"] = is_down.groupby(group).cumsum()

    # ══════════════════════════════════════════════════════════════════
    # 7. CROSS-ASSET FEATURES
    # ══════════════════════════════════════════════════════════════════
    sp_ret = df["daily_ret"]

    if "Gold" in data.columns:
        gold_ret = data["Gold"].pct_change()
        df["gold_equity_ratio"] = data["Gold"] / sp
        df["gold_equity_ratio_change_3m"] = df["gold_equity_ratio"].pct_change(63)
        df["gold_equity_corr_63d"] = sp_ret.rolling(63).corr(gold_ret)

    if "NASDAQ" in data.columns:
        nasdaq_ret = data["NASDAQ"].pct_change()
        df["sp_nasdaq_ratio"] = sp / data["NASDAQ"].replace(0, np.nan)
        df["sp_nasdaq_corr_63d"] = sp_ret.rolling(63).corr(nasdaq_ret)

    if "Russell" in data.columns:
        df["small_large_ratio"] = data["Russell"] / sp
        df["small_large_change_3m"] = df["small_large_ratio"].pct_change(63)

    sector_cols = [c for c in data.columns if c.startswith("Sector_")]
    if len(sector_cols) >= 3:
        sector_returns = data[sector_cols].pct_change()
        df["sector_dispersion"] = sector_returns.std(axis=1)
        df["sector_dispersion_63d"] = df["sector_dispersion"].rolling(63).mean()

    if "T10Y" in data.columns:
        yield_change = data["T10Y"].diff()
        df["bond_equity_corr_63d"] = sp_ret.rolling(63).corr(yield_change)

    # ══════════════════════════════════════════════════════════════════
    # 8. INTERACTION FEATURES
    # ══════════════════════════════════════════════════════════════════
    df["vol_x_mom_3m"] = df["vol_1m"] * df["mom_3m"]
    df["vol_x_mom_12m"] = df["vol_1m"] * df["mom_12m"]

    if "vix" in df.columns and "term_spread" in df.columns:
        df["vix_x_spread"] = df["vix"] * df["term_spread"]

    df["vol_x_drawdown"] = df["vol_1m"] * df["drawdown_from_peak"]

    if "rsi_14d_norm" in df.columns:
        df["mom_x_rsi"] = df["mom_3m"] * df["rsi_14d_norm"]

    df["vol_ratio_x_trend"] = df["vol_ratio_1m_3m"] * df["sma_50d_dev"]

    if "vix" in df.columns:
        df["drawdown_x_vix"] = df["drawdown_from_peak"] * df["vix"]
        df["vix_x_mom"] = df["vix"] * df["mom_1m"]

    if "term_spread" in df.columns:
        df["spread_x_vol"] = df["term_spread"] * df["vol_1m"]

    if "vix_term_structure_ratio" in df.columns:
        df["vix_ts_x_mom"] = df["vix_term_structure_ratio"] * df["mom_1m"]

    if "skew_zscore" in df.columns:
        df["skew_x_drawdown"] = df["skew_zscore"] * df["drawdown_from_peak"]

    # ══════════════════════════════════════════════════════════════════
    # 9. FRED MACRO FEATURES (time-varying, if provided)
    # ══════════════════════════════════════════════════════════════════
    if fred_data:
        fred_cols: Dict[str, pd.Series] = {}
        for k, series in fred_data.items():
            try:
                s = pd.Series(series).astype(float)
                s.index = pd.to_datetime(s.index)
                s = s.reindex(df.index).ffill()
                col = f"fred_{k}"
                fred_cols[col] = s
                fred_cols[f"{col}_chg_3m"] = s.pct_change(63)
                fred_cols[f"{col}_chg_12m"] = s.pct_change(252)
                col_mean = s.rolling(252).mean()
                col_std = s.rolling(252).std()
                fred_cols[f"{col}_zscore"] = (s - col_mean) / col_std.replace(
                    0, np.nan
                )
            except Exception:
                continue
        if fred_cols:
            df = pd.concat(
                [df, pd.DataFrame(fred_cols, index=df.index)], axis=1
            )

    # FRED interaction features
    interaction_cols: Dict[str, pd.Series] = {}
    if "fred_hy_oas" in df.columns:
        interaction_cols["hy_oas_x_vol"] = df["fred_hy_oas"] * df["vol_1m"]
    if "fred_gpr_world" in df.columns:
        interaction_cols["gpr_x_mom"] = df["fred_gpr_world"] * df["mom_1m"]
    if interaction_cols:
        df = pd.concat(
            [df, pd.DataFrame(interaction_cols, index=df.index)], axis=1
        )

    # ══════════════════════════════════════════════════════════════════
    # 10. FINAL CLEANUP
    # ══════════════════════════════════════════════════════════════════
    df = df.replace([np.inf, -np.inf], np.nan).ffill().fillna(0)
    return df


# ══════════════════════════════════════════════════════════════════════════════
# TARGET BUILDERS
# ══════════════════════════════════════════════════════════════════════════════


def _forward_return(series: pd.Series, days: int) -> pd.Series:
    return series.shift(-days) / series - 1.0


def build_target_return(
    data: pd.DataFrame, horizon_days: int = 252
) -> pd.Series:
    """Return series over horizon_days forward."""
    return _forward_return(data["SP500"], horizon_days)


def build_target_return_multi(data: pd.DataFrame) -> Dict[str, pd.Series]:
    return {
        "3m": build_target_return(data, horizon_days=63),
        "6m": build_target_return(data, horizon_days=126),
        "12m": build_target_return(data, horizon_days=252),
    }


def _forward_max_drawdown(prices: pd.Series, days: int) -> pd.Series:
    """Compute forward-looking maximum drawdown over next days."""
    vals = prices.values.astype(float)
    n = len(vals)
    out = np.full(n, np.nan)

    for i in range(n - 1):
        end = min(n, i + days + 1)
        window = vals[i:end]
        if len(window) <= 1:
            continue
        peak = np.maximum.accumulate(window)
        mask = peak > 0
        dd_min = 0.0
        if mask.any():
            dd = np.where(mask, (window - peak) / peak, 0.0)
            dd_min = dd.min()
        out[i] = dd_min

    return pd.Series(out, index=prices.index)


def build_target_crash(
    data: pd.DataFrame, threshold: float = -0.2, horizon_days: int = 252
) -> pd.Series:
    """Boolean: does a crash (drawdown <= threshold) occur within horizon?"""
    mdd = _forward_max_drawdown(data["SP500"], horizon_days)
    return mdd <= threshold


def build_target_crash_multi(
    data: pd.DataFrame, threshold: float = -0.2
) -> Dict[str, pd.Series]:
    return {
        "3m": build_target_crash(data, threshold=threshold, horizon_days=63),
        "6m": build_target_crash(data, threshold=threshold, horizon_days=126),
        "12m": build_target_crash(data, threshold=threshold, horizon_days=252),
    }
