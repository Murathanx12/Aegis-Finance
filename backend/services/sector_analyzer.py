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
    hmm_state_means: Optional[np.ndarray] = None,
    hmm_regime_probs: Optional[np.ndarray] = None,
    hmm_state_vols: Optional[np.ndarray] = None,
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

    # Load factor model parameters from config
    _sm = config.get("sector_model", {})
    min_hist = _sm.get("min_history_days", 504)
    beta_long = _sm.get("beta_lookback_long", 504)
    beta_short = _sm.get("beta_lookback_short", 252)
    beta_lo, beta_hi = _sm.get("beta_clip", (0.3, 2.5))
    mom_6m_w = _sm.get("momentum_6m_weight", 0.4)
    mom_12m_w = _sm.get("momentum_12m_weight", 0.2)
    mr_coeff = _sm.get("mean_reversion_coeff", -0.15)
    mr_lookback = _sm.get("mean_reversion_lookback", 1260)
    vol_long = _sm.get("vol_lookback_long", 504)
    vol_short = _sm.get("vol_lookback_short", 63)
    vol_ratio_thresh = _sm.get("vol_ratio_threshold", 1.3)
    vol_adj_coeff = _sm.get("vol_adj_coeff", -0.02)
    sigma_cap = _sm.get("sigma_cap", 0.80)
    sigma_default = _sm.get("sigma_default", 0.20)
    ret_lo, ret_hi = _sm.get("expected_return_clip", (-0.30, 0.50))

    for name, series in sector_data.items():
        series = series.dropna()
        if len(series) < min_hist:
            continue

        returns = series.pct_change().dropna()
        current = float(series.iloc[-1])

        # Factor 1: Beta (rolling window)
        common_idx = returns.index.intersection(sp_returns.index)
        if len(common_idx) > beta_long:
            sr = sp_returns.reindex(common_idx).iloc[-beta_long:]
            sec_r = returns.reindex(common_idx).iloc[-beta_long:]
            var = sr.var()
            beta = float(sec_r.cov(sr) / var) if var > 0 else 1.0
            beta = float(np.clip(beta, beta_lo, beta_hi))
        elif len(common_idx) > beta_short:
            sr = sp_returns.reindex(common_idx).iloc[-beta_short:]
            sec_r = returns.reindex(common_idx).iloc[-beta_short:]
            var = sr.var()
            beta = float(sec_r.cov(sr) / var) if var > 0 else 1.0
            beta = float(np.clip(beta, beta_lo, beta_hi))
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

        momentum_alpha = mom_6m_w * rel_strength_6m + mom_12m_w * rel_strength_12m

        # Factor 3: Mean reversion (excess over market)
        if len(series) > mr_lookback:
            annualized_5y = (current / float(series.iloc[-mr_lookback])) ** (1 / 5) - 1
            market_5y = (float(sp_price.iloc[-1]) / float(sp_price.iloc[-mr_lookback])) ** (1 / 5) - 1
            mr_factor = mr_coeff * (annualized_5y - market_5y)
        else:
            mr_factor = 0.0

        # Factor 4: Sector volatility
        sigma = float(returns.iloc[-vol_long:].std() * np.sqrt(252)) if len(returns) > vol_long else sigma_default
        sigma = min(sigma, sigma_cap)

        vol_short_d = float(returns.iloc[-vol_short:].std() * np.sqrt(252)) if len(returns) > vol_short else sigma
        vol_ratio = vol_short_d / max(sigma, 0.01)
        vol_adj = vol_adj_coeff * max(0, vol_ratio - vol_ratio_thresh)

        # Combine: CAPM + factors
        capm_return = rf + beta * (market_annual_return - rf)
        expected_annual = float(np.clip(capm_return + momentum_alpha + mr_factor + vol_adj, ret_lo, ret_hi))

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
    sim_cfg = config["simulation"]
    n_sims = sim_cfg["num_simulations"]
    crash_freq = sim_cfg["jump_diffusion"]["annual_rate"]
    base_scenario = {"drift_adj": 0, "vol_mult": 1.0, "crash_mult": 1.0}

    # Fit GARCH per sector for sector-specific vol dynamics, tail thickness,
    # and standardized residuals.  Fall back to SP500 GARCH when the sector
    # series is too short or the fit fails.
    sp_garch_persistence = None
    sp_garch_nu = None
    sp_hist_residuals = None
    try:
        from backend.models.garch import fit_garch, get_standardized_residuals
        sp_garch_result = fit_garch(sp_returns)
        if sp_garch_result.success:
            sp_garch_nu = sp_garch_result.nu
            sp_garch_persistence = (
                sp_garch_result.alpha
                + sp_garch_result.gamma * np.sqrt(2 / np.pi)
                + sp_garch_result.beta
            )
            std_resid = get_standardized_residuals(sp_garch_result, sp_returns)
            if std_resid is not None and len(std_resid) > 50:
                sp_hist_residuals = std_resid
    except (ImportError, ValueError, np.linalg.LinAlgError) as e:
        logger.debug("SP500 GARCH fit skipped: %s", e)
    if sp_hist_residuals is None and len(sp_returns) > 50:
        sp_hist_residuals = sp_returns.values

    # Pre-fit GARCH for each sector on its own returns
    sector_garch = {}  # name → (current_vol, persistence, nu, residuals)
    for name, f in sector_factors.items():
        sec_current_vol = None
        sec_persistence = sp_garch_persistence
        sec_nu = sp_garch_nu
        sec_residuals = sp_hist_residuals
        try:
            from backend.models.garch import fit_garch as _fit_garch, get_standardized_residuals as _get_resid
            sec_returns = sector_data[name].pct_change().dropna()
            if len(sec_returns) >= 500:
                sec_garch = _fit_garch(sec_returns)
                if sec_garch.success:
                    sec_current_vol = sec_garch.current_vol
                    sec_persistence = (
                        sec_garch.alpha
                        + sec_garch.gamma * np.sqrt(2 / np.pi)
                        + sec_garch.beta
                    )
                    sec_nu = sec_garch.nu
                    sec_std = _get_resid(sec_garch, sec_returns)
                    if sec_std is not None and len(sec_std) > 50:
                        sec_residuals = sec_std
                    logger.debug(
                        "Sector %s GARCH: vol=%.3f, persistence=%.3f, nu=%.1f",
                        name, sec_current_vol, sec_persistence, sec_nu,
                    )
        except (ImportError, ValueError, np.linalg.LinAlgError) as e:
            logger.debug("Sector %s GARCH fit skipped: %s", name, e)
        sector_garch[name] = (sec_current_vol, sec_persistence, sec_nu, sec_residuals)

    for name, f in sector_factors.items():
        expected_annual = f["expected_annual"]
        sigma = f["sigma"]
        current = f["current_price"]
        expected_total = (1 + expected_annual) ** years - 1

        # Beta-adjust crash frequency: high-beta sectors crash more often
        beta_adj_crash_freq = float(np.clip(crash_freq * f["beta"], 0.02, 0.25))

        # Use sector-specific GARCH parameters (falls back to SP500)
        sec_current_vol, sec_persistence, sec_nu, sec_residuals = sector_garch.get(
            name, (None, sp_garch_persistence, sp_garch_nu, sp_hist_residuals)
        )

        # Ito correction: convert arithmetic return to log drift for simulate_paths.
        # simulate_paths uses log_return = drift*dt + sigma*dW, so the drift must be
        # log drift = ln(1+r) - 0.5*sigma^2 to produce correct E[S(T)].
        # Use GARCH current_vol when available (matches what simulate_paths uses
        # as base_vol); fall back to historical sigma.
        ito_sigma = sec_current_vol if sec_current_vol is not None else sigma
        sector_mu = float(np.log(1 + expected_annual) - 0.5 * ito_sigma**2)
        paths = simulate_paths(
            current, sector_mu, sigma, forecast_days, n_sims,
            beta_adj_crash_freq, 0.0, base_scenario,
            ml_crash_prob=ml_crash_prob,
            ml_predicted_return=expected_annual,
            garch_vol=ito_sigma,
            garch_persistence=sec_persistence,
            garch_nu=sec_nu,
            historical_residuals=sec_residuals,
            hmm_state_means=hmm_state_means,
            hmm_regime_probs=hmm_regime_probs,
            hmm_state_vols=hmm_state_vols,
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
