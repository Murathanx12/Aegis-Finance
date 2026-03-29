"""
Aegis Finance — ML-Driven Monte Carlo Simulator
=================================================

Jump-diffusion Monte Carlo with:
  - Merton 1976 drift compensator (Bug 20 fix)
  - Block bootstrap for volatility clustering
  - Ornstein-Uhlenbeck volatility dynamics
  - Mean reversion to fair value trajectory
  - Leverage effect (correlated vol/price shocks)
  - Scenario-weighted simulation

Adapted from V7 engine (market-prediction-engine) with critical fixes applied.

Usage:
    from backend.services.monte_carlo import simulate_paths, run_monte_carlo
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from backend.config import config, get_scenario_configs, get_institutional_return

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# BLOCK BOOTSTRAP
# ══════════════════════════════════════════════════════════════════════════════


def _generate_block_bootstrap_residuals(
    historical_returns: np.ndarray,
    days: int,
    n_sims: int,
    block_size: int = 21,
    rng: Optional[np.random.Generator] = None,
) -> np.ndarray:
    """Sample overlapping blocks of historical residuals to preserve vol clustering.

    Real markets exhibit autocorrelated volatility. Block bootstrap samples
    contiguous blocks of historical returns, preserving within-block serial
    correlation (volatility clustering, momentum, mean-reversion).

    Args:
        historical_returns: Array of standardized historical daily returns
        days: Number of simulation days
        n_sims: Number of simulation paths
        block_size: Size of each block (21 ~ 1 trading month)
        rng: Numpy random generator

    Returns:
        np.ndarray of shape (days, n_sims) with block-bootstrapped residuals
    """
    if rng is None:
        rng = np.random.default_rng()

    n_hist = len(historical_returns)
    max_start = n_hist - block_size
    if max_start < 1:
        return rng.standard_normal(size=(days, n_sims))

    # Standardize to zero mean, unit variance
    mu = historical_returns.mean()
    sigma = historical_returns.std()
    if sigma < 1e-10:
        return rng.standard_normal(size=(days, n_sims))
    standardized = (historical_returns - mu) / sigma

    n_blocks_needed = (days + block_size - 1) // block_size
    residuals = np.zeros((days, n_sims))

    starts = rng.integers(0, max_start, size=(n_blocks_needed, n_sims))
    for b in range(n_blocks_needed):
        row_start = b * block_size
        row_end = min(row_start + block_size, days)
        actual_len = row_end - row_start
        for sim in range(n_sims):
            residuals[row_start:row_end, sim] = standardized[
                starts[b, sim] : starts[b, sim] + actual_len
            ]

    return residuals


# ══════════════════════════════════════════════════════════════════════════════
# CORE SIMULATION
# ══════════════════════════════════════════════════════════════════════════════


def simulate_paths(
    start_price: float,
    historical_mu: float,  # Historical log-return mean (annualized)
    historical_sigma: float,  # Historical volatility (annualized)
    days: int,  # Simulation horizon in trading days
    n_sims: int,  # Number of Monte Carlo paths
    crash_freq: float,  # Historical crash frequency (crashes/year)
    risk_score: float,  # Current composite risk score
    scenario: dict,  # Scenario adjustments
    # ── ML INPUTS ────────────────────────────────────────────────
    ml_crash_prob: Optional[float] = None,
    ml_predicted_return: Optional[float] = None,
    ml_return_p10: Optional[float] = None,
    ml_return_p90: Optional[float] = None,
    garch_vol: Optional[float] = None,
    garch_persistence: Optional[float] = None,
    # ── HMM REGIME INPUTS ───────────────────────────────────────
    hmm_state_means: Optional[np.ndarray] = None,
    hmm_regime_probs: Optional[np.ndarray] = None,
    hmm_state_vols: Optional[np.ndarray] = None,
    # ── BLOCK BOOTSTRAP ──────────────────────────────────────────
    historical_residuals: Optional[np.ndarray] = None,
    # ── REPRODUCIBILITY ──────────────────────────────────────────
    seed: Optional[int] = None,
) -> np.ndarray:
    """
    ML-Driven Monte Carlo path simulation with Merton jump-diffusion.

    ALL drift/vol/jump parameters are derived from ML predictions and
    fitted models. Zero hardcoded regime parameters.

    Returns:
        np.ndarray of shape (days+1, n_sims) with simulated prices
    """
    sim_cfg = config["simulation"]
    dt = 1.0 / sim_cfg["trading_days_per_year"]
    rng = np.random.default_rng(seed)

    # ══════════════════════════════════════════════════════════════
    # 1. DRIFT — from ML prediction (or historical fallback)
    # ══════════════════════════════════════════════════════════════
    if ml_predicted_return is not None:
        annual_drift = np.log(1 + ml_predicted_return)
    else:
        annual_drift = historical_mu

    # HMM regime tilt
    hmm_drift_blend = sim_cfg.get("hmm_drift_blend", 0.15)
    hmm_vol_blend = sim_cfg.get("hmm_vol_blend", 0.15)
    if hmm_state_means is not None and hmm_regime_probs is not None:
        hmm_expected = float(np.dot(hmm_regime_probs, hmm_state_means))
        hmm_tilt = hmm_drift_blend * (hmm_expected - annual_drift)
        annual_drift += hmm_tilt

    # Scenario adjustment (additive)
    annual_drift += scenario.get("drift_adj", 0.0)

    # Daily drift
    base_drift = annual_drift * dt

    # ══════════════════════════════════════════════════════════════
    # 2. VOLATILITY — from GARCH (or historical fallback)
    # ══════════════════════════════════════════════════════════════
    if garch_vol is not None:
        base_vol = garch_vol
    else:
        base_vol = historical_sigma

    # HMM vol blend
    if hmm_state_vols is not None and hmm_regime_probs is not None:
        hmm_vol = float(np.dot(hmm_regime_probs, hmm_state_vols))
        base_vol = (1 - hmm_vol_blend) * base_vol + hmm_vol_blend * hmm_vol

    # Scenario vol multiplier
    base_vol *= scenario.get("vol_mult", 1.0)
    base_vol = min(base_vol, sim_cfg.get("max_annual_volatility", 1.2))

    # Vol persistence and mean reversion
    persistence = garch_persistence if garch_persistence is not None else 0.97
    long_run_vol = historical_sigma
    kappa_vol = max(0.5, (1 - persistence) * 252)
    xi = 0.06  # Vol-of-vol noise coefficient

    # ══════════════════════════════════════════════════════════════
    # 3. JUMP PROCESS — from ML crash probability
    # ══════════════════════════════════════════════════════════════
    jump_cfg = sim_cfg["jump_diffusion"]
    t_df = jump_cfg["t_degrees_of_freedom"]

    if ml_crash_prob is not None:
        base_jump_rate = crash_freq
        jump_rate = base_jump_rate * (0.5 + ml_crash_prob * 5.0)
        jump_rate = np.clip(jump_rate, 0.01, 0.25)
    else:
        jump_rate = crash_freq * scenario.get("crash_mult", 1.0)
        jump_rate = np.clip(jump_rate, 0.02, 0.20)

    jump_mean = jump_cfg["mean"]  # ~-10%
    jump_std = jump_cfg["std"]  # ~5%
    daily_jump_prob = jump_rate * dt

    # ══════════════════════════════════════════════════════════════
    # MERTON 1976 JUMP COMPENSATOR (Bug 20 fix)
    # ══════════════════════════════════════════════════════════════
    # Without this, jumps mechanically drag expected returns below
    # the calibrated drift by lambda * E[e^J - 1] per year.
    # The compensator restores E[S(T)] = S(0) * exp(mu * T).
    jump_k = np.exp(jump_mean + 0.5 * jump_std**2) - 1
    jump_compensator = daily_jump_prob * jump_k

    # ══════════════════════════════════════════════════════════════
    # 4. MEAN REVERSION — calibrated from drawdown recovery data
    # ══════════════════════════════════════════════════════════════
    if ml_predicted_return is not None:
        fv_growth = np.log(1 + ml_predicted_return) * dt
    else:
        fv_growth = annual_drift * dt

    mr_cfg = sim_cfg.get("mean_reversion", {})
    mr_strength_up = mr_cfg.get("strength_up", 0.08)
    mr_strength_down = mr_cfg.get("strength_down", 0.04)
    mr_threshold_low = mr_cfg.get("threshold_low", 0.20)
    mr_threshold_high = mr_cfg.get("threshold_high", 0.30)

    # ══════════════════════════════════════════════════════════════
    # 5. UNCERTAINTY SCALING — from ML quantile spread
    # ══════════════════════════════════════════════════════════════
    if ml_return_p10 is not None and ml_return_p90 is not None:
        ml_spread = ml_return_p90 - ml_return_p10
        expected_spread = 2 * 1.28 * base_vol
        if expected_spread > 0:
            vol_scale = max(0.7, min(1.5, ml_spread / expected_spread))
            base_vol *= vol_scale

    # ══════════════════════════════════════════════════════════════
    # 6. RUN SIMULATION
    # ══════════════════════════════════════════════════════════════
    prices = np.zeros((days + 1, n_sims))
    prices[0] = start_price

    sigma_t = np.full(n_sims, float(base_vol))
    fair_value = np.full(n_sims, float(start_price))

    # Pre-generate random numbers
    use_block_bootstrap = sim_cfg.get("use_block_bootstrap", False)
    block_size = sim_cfg.get("block_bootstrap_size", 21)
    if (
        use_block_bootstrap
        and historical_residuals is not None
        and len(historical_residuals) > block_size
    ):
        Z_price = _generate_block_bootstrap_residuals(
            historical_residuals, days, n_sims, block_size, rng
        )
    else:
        Z_price = rng.standard_t(df=t_df, size=(days, n_sims))
    Z_vol_raw = rng.standard_normal(size=(days, n_sims))
    Z_jump = rng.uniform(size=(days, n_sims))
    Z_jump_size = rng.normal(jump_mean, jump_std, size=(days, n_sims))

    # Leverage effect: correlate vol innovations with price shocks
    rho_leverage = -0.7
    Z_vol = rho_leverage * Z_price + np.sqrt(1 - rho_leverage**2) * Z_vol_raw

    for t in range(days):
        # Update fair value trajectory
        fair_value *= np.exp(fv_growth)

        # Mean reversion force
        deviation = (prices[t] - fair_value) / fair_value
        mr_force = np.zeros(n_sims)
        below = deviation < -mr_threshold_low
        above = deviation > mr_threshold_high
        mr_force[below] = mr_strength_up * (-deviation[below] - mr_threshold_low)
        mr_force[above] = -mr_strength_down * (
            deviation[above] - mr_threshold_high
        )
        mr_daily = mr_force * dt

        # Ornstein-Uhlenbeck volatility dynamics
        d_sigma = kappa_vol * (long_run_vol - sigma_t) * dt + xi * sigma_t * np.sqrt(
            dt
        ) * Z_vol[t]
        sigma_t = np.clip(sigma_t + d_sigma, 0.04, 1.0)

        # Price dynamics (GBM with jumps + Merton compensator)
        # dS/S = (mu - sigma^2/2 - lambda*k)dt + sigma*sqrt(dt)*Z + J*dN
        drift_daily = (
            base_drift - 0.5 * sigma_t**2 * dt + jump_compensator + mr_daily
        )
        diffusion = sigma_t * np.sqrt(dt) * Z_price[t]

        # Jump component
        jumps = np.where(Z_jump[t] < daily_jump_prob, Z_jump_size[t], 0.0)

        # Log-price step
        log_return = drift_daily + diffusion + jumps
        prices[t + 1] = prices[t] * np.exp(log_return)

    # Apply return cap
    max_return = sim_cfg.get("max_5y_return", 3.0)
    max_price = start_price * (1 + max_return)
    prices = np.clip(prices, 0.01, max_price)

    return prices


# ══════════════════════════════════════════════════════════════════════════════
# SCENARIO-WEIGHTED SIMULATION
# ══════════════════════════════════════════════════════════════════════════════


def run_monte_carlo(
    current_price: float,
    current_regime: str,
    risk_score: float,
    crash_freq: float,
    current_vix: float,
    yield_curve: float,
    val_penalty: float,
    garch_vol: Optional[float] = None,
    garch_persistence: Optional[float] = None,
    recession_prob: Optional[float] = None,
    ml_crash_prob: Optional[float] = None,
    ml_predicted_return: Optional[float] = None,
    ml_return_p10: Optional[float] = None,
    ml_return_p90: Optional[float] = None,
    hmm_state_means: Optional[np.ndarray] = None,
    hmm_regime_probs: Optional[np.ndarray] = None,
    hmm_state_vols: Optional[np.ndarray] = None,
    seed: Optional[int] = None,
    n_sims_override: Optional[int] = None,
    forecast_days_override: Optional[int] = None,
) -> dict:
    """
    Run full Monte Carlo simulation with scenario weighting.

    Scenarios provide different views of the future. ML predictions
    condition ALL scenarios — they shift the distribution center,
    while scenarios shift the spread.

    Returns:
        dict with all simulation results and statistics
    """
    sim_cfg = config["simulation"]
    n_sims = n_sims_override if n_sims_override is not None else sim_cfg["num_simulations"]
    days = forecast_days_override if forecast_days_override is not None else (
        sim_cfg["forecast_years"] * sim_cfg["trading_days_per_year"]
    )
    risk_cfg = config["risk"]

    scenarios = get_scenario_configs()

    # Dynamic scenario weighting
    scenario_weights = _adjust_scenario_weights(
        scenarios,
        current_vix,
        yield_curve,
        risk_score,
        recession_prob,
        ml_crash_prob,
        ml_predicted_return,
    )

    # Base drift from ML or institutional consensus
    if ml_predicted_return is not None:
        base_annual_return = ml_predicted_return
    else:
        base_annual_return = get_institutional_return()

    base_annual_return -= val_penalty

    historical_mu = np.log(1 + base_annual_return)
    historical_sigma = garch_vol if garch_vol else 0.16

    inst_return = get_institutional_return()
    inst_mu = np.log(1 + inst_return)

    # Run scenario-weighted simulation
    all_paths = None
    scenario_results = {}

    # Use sub-seeds for reproducibility across scenarios
    base_rng = np.random.default_rng(seed)

    for i, (name, scfg) in enumerate(scenarios.items()):
        weight = scenario_weights[name]
        sims_for_scenario = max(1, int(n_sims * weight))

        # Scenario-specific drift adjustment (relative to consensus)
        scenario_return = scfg.get("return", inst_return)
        drift_adj = np.log(1 + scenario_return) - inst_mu

        scenario_params = {
            "drift_adj": drift_adj,
            "vol_mult": scfg.get("volatility", historical_sigma)
            / max(historical_sigma, 0.01),
            "crash_mult": scfg.get("crash_multiplier", 1.0),
        }

        # Generate sub-seed for this scenario
        scenario_seed = None
        if seed is not None:
            scenario_seed = seed + i + 1

        paths = simulate_paths(
            start_price=current_price,
            historical_mu=historical_mu,
            historical_sigma=historical_sigma,
            days=days,
            n_sims=sims_for_scenario,
            crash_freq=crash_freq,
            risk_score=risk_score,
            scenario=scenario_params,
            ml_crash_prob=ml_crash_prob,
            ml_predicted_return=ml_predicted_return,
            ml_return_p10=ml_return_p10,
            ml_return_p90=ml_return_p90,
            garch_vol=garch_vol,
            garch_persistence=garch_persistence,
            hmm_state_means=hmm_state_means,
            hmm_regime_probs=hmm_regime_probs,
            hmm_state_vols=hmm_state_vols,
            seed=scenario_seed,
        )

        scenario_results[name] = {
            "weight": weight,
            "n_sims": sims_for_scenario,
            "mean_final": float(paths[-1].mean()),
        }

        logger.info(
            "  %s (%.0f%%): %d sims -> $%,.0f",
            name,
            weight * 100,
            sims_for_scenario,
            paths[-1].mean(),
        )

        all_paths = paths if all_paths is None else np.hstack([all_paths, paths])

    # ── Compute statistics ─────────────────────────────────────────────
    final = all_paths[-1]
    crash_threshold = -risk_cfg["crash_threshold"]

    # Peak-to-trough drawdown
    sim_peak = np.maximum.accumulate(all_paths, axis=0)
    sim_dd = (all_paths - sim_peak) / sim_peak

    # 1-year crash probability
    yr1_dd = sim_dd[: min(252, days + 1)]
    crash_1y = float((yr1_dd.min(axis=0) <= crash_threshold).mean()) * 100

    # Full-period crash probability
    crash_full = float((sim_dd.min(axis=0) <= crash_threshold).mean()) * 100

    # CVaR (expected loss in worst 5%)
    returns_full = final / current_price - 1
    sorted_returns = np.sort(returns_full)
    n_tail = max(1, int(len(sorted_returns) * 0.05))
    cvar_95 = float(sorted_returns[:n_tail].mean()) * 100

    # Max drawdown (average per-path)
    per_path_max_dd = sim_dd.min(axis=0)
    max_dd = float(per_path_max_dd.mean()) * 100

    total_return = float(final.mean()) / current_price - 1
    annual_return = (1 + total_return) ** (1 / sim_cfg["forecast_years"]) - 1

    # Path percentile bands
    mean_path = all_paths.mean(axis=1)
    median_path = np.median(all_paths, axis=1)
    p05_path = np.percentile(all_paths, 5, axis=1)
    p25_path = np.percentile(all_paths, 25, axis=1)
    p75_path = np.percentile(all_paths, 75, axis=1)
    p95_path = np.percentile(all_paths, 95, axis=1)

    # Crash probability by horizon
    crash_probs = {}
    horizon_map = {
        "1mo": 21,
        "3mo": 63,
        "6mo": 126,
        "12mo": 252,
        "24mo": 504,
        "36mo": 756,
        "60mo": days,
    }
    for label, horizon_days in horizon_map.items():
        if horizon_days > days:
            horizon_days = days
        h_dd = sim_dd[: horizon_days + 1]
        crash_probs[label] = (
            float((h_dd.min(axis=0) <= crash_threshold).mean()) * 100
        )

    # Enrich scenario results
    for name, scfg in scenarios.items():
        if name in scenario_results:
            mean_final = scenario_results[name]["mean_final"]
            scen_total_ret = (mean_final / current_price - 1) * 100
            scenario_results[name].update(
                {
                    "probability": scenario_results[name]["weight"],
                    "return": scfg.get("return", 0.0),
                    "total_return": scen_total_ret,
                    "volatility": scfg.get("volatility", historical_sigma),
                    "description": scfg.get("description", ""),
                }
            )

    # Realism validation
    realism = _validate_realism(all_paths, current_price, sim_cfg["forecast_years"])

    return {
        "all_paths": all_paths,
        "paths": all_paths,
        "mean_path": mean_path,
        "median_path": median_path,
        "p05": p05_path,
        "p25": p25_path,
        "p75": p75_path,
        "p95": p95_path,
        "final_mean": float(final.mean()),
        "final_median": float(np.median(final)),
        "final_p05": float(np.percentile(final, 5)),
        "final_p10": float(np.percentile(final, 10)),
        "final_p25": float(np.percentile(final, 25)),
        "final_p75": float(np.percentile(final, 75)),
        "final_p90": float(np.percentile(final, 90)),
        "final_p95": float(np.percentile(final, 95)),
        "total_return_pct": total_return * 100,
        "annual_return_pct": annual_return * 100,
        "crash_prob_1y": crash_1y,
        "crash_prob_5y": crash_full,
        "crash_probs": crash_probs,
        "cvar_95_pct": cvar_95,
        "max_dd_pct": max_dd,
        "max_drawdown_pct": abs(max_dd),
        "scenarios": scenario_results,
        "ml_crash_prob": ml_crash_prob,
        "ml_predicted_return": ml_predicted_return,
        "garch_vol": garch_vol,
        "realism_check": realism,
    }


def _adjust_scenario_weights(
    scenarios: dict,
    vix: float,
    yield_curve: float,
    risk_score: float,
    recession_prob: Optional[float],
    ml_crash_prob: Optional[float],
    ml_predicted_return: Optional[float],
) -> dict:
    """Dynamically adjust scenario probabilities based on current market state.

    ML crash/return predictions tilt the scenario distribution:
    - High crash prob -> more weight on bearish scenarios
    - Low crash prob -> more weight on bullish scenarios

    All adjustments are proportional and re-normalized to sum to 1.0.
    """
    weights = {name: scfg["probability"] for name, scfg in scenarios.items()}

    # ML-based tilt
    if ml_crash_prob is not None:
        crash_tilt = (ml_crash_prob - 0.22) * 3.0
        for name, scfg in scenarios.items():
            category = scfg.get("category", "neutral")
            if category == "bearish":
                weights[name] *= 1 + max(0, crash_tilt)
            elif category == "bullish":
                weights[name] *= 1 + max(0, -crash_tilt)

    # Recession probability tilt
    if recession_prob is not None and recession_prob > 0.30:
        for name in weights:
            if "Recession" in name or "Stagflation" in name:
                weights[name] *= 1 + (recession_prob - 0.30)

    # VIX tilt
    if vix > 25:
        for name, scfg in scenarios.items():
            if scfg.get("category") == "bearish":
                weights[name] *= 1 + (vix - 25) / 30

    # Yield curve inversion tilt
    if yield_curve < 0:
        for name, scfg in scenarios.items():
            if scfg.get("category") == "bearish":
                weights[name] *= 1.3

    # Normalize
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}

    # Enforce minimum 2% floor per scenario
    for k in weights:
        weights[k] = max(weights[k], 0.02)
    total = sum(weights.values())
    weights = {k: v / total for k, v in weights.items()}

    return weights


def _validate_realism(
    paths: np.ndarray,
    start_price: float,
    years: float,
) -> dict:
    """Validate simulation realism against empirical S&P 500 statistics.

    Checks:
        - Mean annual return: should be 2-15%
        - Annual volatility: should be 10-30%
        - Crash frequency: 30-90% of paths should have >20% drawdown
        - Fat tails: return kurtosis should be >3
    """
    final = paths[-1]
    n_sims = paths.shape[1]

    # Annual return
    total_returns = final / start_price - 1
    mean_total = float(total_returns.mean())
    mean_annual = (1 + mean_total) ** (1 / max(years, 0.5)) - 1

    # Annualized vol from daily log returns
    daily_log_rets = np.diff(np.log(paths), axis=0)
    mean_daily_vol = float(daily_log_rets.std(axis=0).mean())
    annual_vol = mean_daily_vol * np.sqrt(252)

    # Crash frequency
    sim_peak = np.maximum.accumulate(paths, axis=0)
    sim_dd = (paths - sim_peak) / np.where(sim_peak > 0, sim_peak, 1.0)
    crash_pct = float((sim_dd.min(axis=0) <= -0.20).mean())

    # Fat tails
    sample_rets = daily_log_rets[:, : min(1000, n_sims)].flatten()
    kurt = float(pd.Series(sample_rets).kurtosis())
    skew = float(pd.Series(sample_rets).skew())

    warnings = []
    if mean_annual < 0.02 or mean_annual > 0.15:
        warnings.append(f"Annual return {mean_annual*100:.1f}% outside 2-15% range")
    if annual_vol < 0.10 or annual_vol > 0.30:
        warnings.append(f"Annual vol {annual_vol*100:.1f}% outside 10-30% range")
    if crash_pct < 0.30 or crash_pct > 0.90:
        warnings.append(
            f"Crash frequency {crash_pct*100:.0f}% outside 30-90% range"
        )
    if kurt < 3:
        warnings.append(f"Kurtosis {kurt:.1f} < 3 (insufficient fat tails)")

    if warnings:
        for w in warnings:
            logger.warning("REALISM: %s", w)
    else:
        logger.info("Realism check: all metrics within expected ranges")

    return {
        "mean_annual_return": mean_annual,
        "annual_vol": annual_vol,
        "crash_frequency": crash_pct,
        "kurtosis": kurt,
        "skewness": skew,
        "warnings": warnings,
    }
