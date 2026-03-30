"""
Aegis Finance — Sector Analysis (Factor-Based)
=================================================

Multi-factor model for 11 S&P 500 sectors:
  E[R] = rf + beta*(market_return - rf) + momentum + mean_reversion + vol_adj

Each factor is computed from the sector's own price history.
Returns are normalized so cap-weighted average matches index return.

Usage:
    from backend.services.sector_analyzer import analyze_sectors
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from backend.config import config, get_institutional_return
from backend.services.monte_carlo import simulate_paths

logger = logging.getLogger(__name__)

# Approximate S&P 500 sector cap weights
_SECTOR_WEIGHTS = {
    "Technology": 0.32,
    "Healthcare": 0.12,
    "Financials": 0.13,
    "Consumer Disc.": 0.10,
    "Industrials": 0.09,
    "Communications": 0.09,
    "Consumer Staples": 0.06,
    "Energy": 0.03,
    "Utilities": 0.02,
    "Real Estate": 0.02,
    "Materials": 0.02,
}


def analyze_sectors(
    data: pd.DataFrame,
    sector_data: dict[str, pd.Series],
    forecast_days: int,
    ml_predicted_return: Optional[float] = None,
    ml_crash_prob: Optional[float] = None,
    garch_vol: Optional[float] = None,
) -> dict:
    """Sector-level projections with factor-based differentiation.

    Args:
        data: Market DataFrame with SP500, T3M, etc.
        sector_data: Dict of {sector_name: price_series}
        forecast_days: Trading days to project
        ml_predicted_return: Annual market return estimate
        ml_crash_prob: Crash probability for MC
        garch_vol: GARCH volatility estimate

    Returns:
        Dict of {sector_name: metrics_dict}
    """
    # Risk-free rate
    if "T3M" in data.columns:
        rf = float(data["T3M"].dropna().iloc[-1])
        rf = max(0.0, min(rf, 0.10))
    else:
        rf = config.get("risk_free_rate", 0.04)

    sp_returns = data["SP500"].pct_change().dropna()
    sp_price = data["SP500"]

    market_annual_return = ml_predicted_return if ml_predicted_return is not None else get_institutional_return()

    results = {}
    sector_factors = {}

    for name, series in sector_data.items():
        series = series.dropna()
        if len(series) < 504:
            continue

        returns = series.pct_change().dropna()
        current = float(series.iloc[-1])

        # Factor 1: Beta (rolling 2-year)
        common_idx = returns.index.intersection(sp_returns.index)
        if len(common_idx) > 504:
            sr = sp_returns.reindex(common_idx).iloc[-504:]
            sec_r = returns.reindex(common_idx).iloc[-504:]
            var = sr.var()
            beta = float(sec_r.cov(sr) / var) if var > 0 else 1.0
            beta = np.clip(beta, 0.3, 2.5)
        elif len(common_idx) > 252:
            sr = sp_returns.reindex(common_idx).iloc[-252:]
            sec_r = returns.reindex(common_idx).iloc[-252:]
            var = sr.var()
            beta = float(sec_r.cov(sr) / var) if var > 0 else 1.0
            beta = np.clip(beta, 0.3, 2.5)
        else:
            beta = 1.0

        # Factor 2: Momentum (relative to market)
        if len(series) > 252 and len(sp_price) > 252:
            sector_mom_6m = float(series.pct_change(126).iloc[-1])
            sector_mom_12m = float(series.pct_change(252).iloc[-1])
            market_mom_6m = float(sp_price.pct_change(126).iloc[-1])
            market_mom_12m = float(sp_price.pct_change(252).iloc[-1])
            rel_strength_6m = sector_mom_6m - market_mom_6m
            rel_strength_12m = sector_mom_12m - market_mom_12m
        else:
            rel_strength_6m = 0.0
            rel_strength_12m = 0.0

        momentum_alpha = 0.4 * rel_strength_6m + 0.2 * rel_strength_12m

        # Factor 3: Mean reversion (5-year excess)
        if len(series) > 1260:
            annualized_5y = (current / float(series.iloc[-1260])) ** (1 / 5) - 1
            market_5y = (float(sp_price.iloc[-1]) / float(sp_price.iloc[-1260])) ** (1 / 5) - 1
            mr_factor = -0.15 * (annualized_5y - market_5y)
        else:
            mr_factor = 0.0

        # Factor 4: Sector volatility
        sigma = float(returns.iloc[-504:].std() * np.sqrt(252)) if len(returns) > 504 else 0.20
        sigma = min(sigma, 0.80)

        vol_63d = float(returns.iloc[-63:].std() * np.sqrt(252)) if len(returns) > 63 else sigma
        vol_ratio = vol_63d / max(sigma, 0.01)
        vol_adj = -0.02 * max(0, vol_ratio - 1.3)

        # Combine: CAPM + factors
        capm_return = rf + beta * (market_annual_return - rf)
        expected_annual = np.clip(capm_return + momentum_alpha + mr_factor + vol_adj, -0.30, 0.50)

        sector_factors[name] = {
            "expected_annual": expected_annual,
            "sigma": sigma,
            "beta": float(beta),
            "rel_strength_6m": rel_strength_6m,
            "rel_strength_12m": rel_strength_12m,
            "momentum_alpha": momentum_alpha,
            "mr_factor": mr_factor,
            "vol_adj": vol_adj,
            "current_price": current,
        }

    # Normalize so cap-weighted average matches index return
    if sector_factors:
        default_w = 1.0 / max(len(sector_factors), 1)
        total_w = sum(_SECTOR_WEIGHTS.get(s, default_w) for s in sector_factors)
        if total_w > 0:
            weighted_avg = sum(
                _SECTOR_WEIGHTS.get(s, default_w) * f["expected_annual"]
                for s, f in sector_factors.items()
            ) / total_w
            gap = weighted_avg - market_annual_return
            if not np.isnan(gap):
                for f in sector_factors.values():
                    f["expected_annual"] -= gap

    # Run Monte Carlo per sector
    years = forecast_days / 252
    n_sims = 2000
    base_scenario = {"drift_adj": 0, "vol_mult": 1.0, "crash_mult": 1.0}

    for name, f in sector_factors.items():
        expected_annual = f["expected_annual"]
        sigma = f["sigma"]
        current = f["current_price"]
        expected_total = (1 + expected_annual) ** years - 1

        sector_mu = np.log(1 + expected_annual)
        paths = simulate_paths(
            current, sector_mu, sigma, forecast_days, n_sims,
            1.0 / 9.0, 0.0, base_scenario,
            ml_crash_prob=ml_crash_prob,
            ml_predicted_return=expected_annual,
            garch_vol=sigma,
        )

        final = paths[-1]

        # Cap MC returns to match expected_annual cap (50% annual → ~660% 5Y max)
        max_mc_total = (1 + 0.50) ** years - 1
        max_mc_price = current * (1 + max_mc_total)
        final = np.minimum(final, max_mc_price)

        sim_total_return = float(final.mean()) / current - 1

        sim_peak = np.maximum.accumulate(paths, axis=0)
        sim_dd = (paths - sim_peak) / sim_peak
        crash_prob = float((sim_dd.min(axis=0) <= -0.20).mean())

        results[name] = {
            "expected_total": expected_total * 100,
            "sim_total_return": sim_total_return * 100,
            "expected_annual": expected_annual * 100,
            "beta": f["beta"],
            "sigma": sigma * 100,
            "momentum_6m": f["rel_strength_6m"] * 100,
            "momentum_12m": f["rel_strength_12m"] * 100,
            "momentum_alpha": f["momentum_alpha"] * 100,
            "mean_reversion": f["mr_factor"] * 100,
            "vol_adj": f["vol_adj"] * 100,
            "crash_prob": crash_prob * 100,
            "sim_p10": float(np.percentile(final, 10)),
            "sim_p90": float(np.percentile(final, 90)),
            "current_price": current,
        }

    logger.info("Analyzed %d sectors", len(results))
    return results
