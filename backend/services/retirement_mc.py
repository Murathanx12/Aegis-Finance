"""
Aegis Finance — Monte Carlo Retirement Simulator
===================================================

Portfolio Visualizer's most popular feature: simulate retirement outcomes
with contributions, withdrawals, and real market uncertainty.

Unlike the deterministic savings_calculator.py (which assumes fixed returns),
this uses Monte Carlo simulation with:
  - Historical return distributions (fat tails, volatility clustering)
  - Configurable withdrawal rates (4% rule, dynamic withdrawal)
  - Inflation adjustment
  - Social Security / pension income offsets
  - Probability of ruin (running out of money before death)

Key output: "What is the probability I run out of money before age 90?"
This is the single most important retirement planning question.

Usage:
    from backend.services.retirement_mc import (
        simulate_retirement, compute_safe_withdrawal_rate,
    )
"""

import logging

import numpy as np


logger = logging.getLogger(__name__)


# Asset class return assumptions (annual, geometric)
_ASSET_RETURNS = {
    "conservative": {"mu": 0.050, "sigma": 0.08},  # 60/40 bonds/stocks
    "moderate":     {"mu": 0.065, "sigma": 0.12},  # 40/60 bonds/stocks
    "aggressive":   {"mu": 0.080, "sigma": 0.17},  # 20/80 bonds/stocks
    "all_equity":   {"mu": 0.090, "sigma": 0.20},  # 100% stocks
}


def simulate_retirement(
    current_savings: float,
    monthly_contribution: float = 0,
    monthly_withdrawal: float = 0,
    current_age: int = 30,
    retirement_age: int = 65,
    end_age: int = 95,
    risk_level: str = "moderate",
    inflation_rate: float = 0.025,
    social_security_monthly: float = 0,
    social_security_start_age: int = 67,
    n_sims: int = 5000,
    seed: int = 42,
) -> dict:
    """Monte Carlo retirement simulation with contributions and withdrawals.

    Phases:
    1. Accumulation (current_age → retirement_age): monthly contributions, no withdrawals
    2. Distribution (retirement_age → end_age): monthly withdrawals, no contributions

    Args:
        current_savings: Current portfolio value ($)
        monthly_contribution: Monthly contribution during accumulation ($)
        monthly_withdrawal: Monthly withdrawal during distribution ($, in today's dollars)
        current_age: Current age
        retirement_age: Age to stop contributing and start withdrawing
        end_age: End of simulation (planning horizon)
        risk_level: "conservative", "moderate", "aggressive", "all_equity"
        inflation_rate: Annual inflation rate
        social_security_monthly: Monthly Social Security / pension income (today's $)
        social_security_start_age: Age when SS/pension starts
        n_sims: Number of Monte Carlo paths
        seed: Random seed for reproducibility

    Returns:
        Dict with simulation results, success probability, and yearly projections.
    """
    rng = np.random.default_rng(seed)

    params = _ASSET_RETURNS.get(risk_level, _ASSET_RETURNS["moderate"])
    annual_mu = params["mu"]
    annual_sigma = params["sigma"]

    # Daily parameters
    # annual_mu is the TARGET geometric return. To achieve this after compounding
    # with volatility, we need a higher arithmetic drift to offset the volatility
    # drag (Jensen's inequality): E[geometric] ≈ E[arithmetic] - σ²/2.
    # So: arithmetic_mu = geometric_mu + σ²/2
    annual_arith_mu = annual_mu + 0.5 * annual_sigma ** 2
    daily_mu = annual_arith_mu / 252
    daily_sigma = annual_sigma / np.sqrt(252)
    monthly_inflation = inflation_rate / 12

    total_years = end_age - current_age
    total_months = total_years * 12
    accum_months = max(retirement_age - current_age, 0) * 12

    # Simulate monthly returns (21 trading days per month, aggregated)
    # Use Student-t for fat tails, normalized so Var(noise) = sigma^2
    # Raw standard_t(df) has variance df/(df-2), so we scale by sqrt((df-2)/df)
    df_t = 8
    t_scale = np.sqrt((df_t - 2) / df_t)  # ≈ 0.866, corrects variance to 1.0
    monthly_returns = np.zeros((total_months, n_sims))
    for m in range(total_months):
        # 21 daily returns → 1 monthly return (compound)
        daily = daily_mu + daily_sigma * t_scale * rng.standard_t(df=df_t, size=(21, n_sims))
        monthly_returns[m, :] = np.exp(np.sum(np.log(1 + daily), axis=0)) - 1

    # Simulate portfolio paths
    balances = np.zeros((total_months + 1, n_sims))
    balances[0, :] = current_savings

    for m in range(total_months):
        age_months = current_age * 12 + m
        age_years = age_months / 12

        # Investment return
        balances[m + 1, :] = balances[m, :] * (1 + monthly_returns[m, :])

        # Inflation-adjusted contribution/withdrawal
        inflation_factor = (1 + monthly_inflation) ** m

        if m < accum_months:
            # Accumulation phase: add contributions
            balances[m + 1, :] += monthly_contribution * inflation_factor
        else:
            # Distribution phase: subtract withdrawals
            net_withdrawal = monthly_withdrawal * inflation_factor

            # Social Security offset
            if age_years >= social_security_start_age and social_security_monthly > 0:
                ss_adjusted = social_security_monthly * inflation_factor
                net_withdrawal = max(0, net_withdrawal - ss_adjusted)

            balances[m + 1, :] = np.maximum(0, balances[m + 1, :] - net_withdrawal)

    # Compute outcomes
    final_balances = balances[-1, :]
    retirement_balances = balances[accum_months, :] if accum_months < total_months else final_balances

    # Ruin probability: fraction of paths that hit $0
    ruin_mask = np.any(balances[accum_months:, :] <= 0, axis=0)
    ruin_probability = float(np.mean(ruin_mask))

    # Year-by-year percentile paths
    yearly_indices = list(range(0, total_months + 1, 12))
    yearly_data = []
    for idx in yearly_indices:
        age = current_age + idx // 12
        vals = balances[idx, :]
        yearly_data.append({
            "age": age,
            "year": idx // 12,
            "phase": "accumulation" if idx < accum_months else "distribution",
            "median": round(float(np.median(vals))),
            "p10": round(float(np.percentile(vals, 10))),
            "p25": round(float(np.percentile(vals, 25))),
            "p75": round(float(np.percentile(vals, 75))),
            "p90": round(float(np.percentile(vals, 90))),
            "mean": round(float(np.mean(vals))),
            "pct_depleted": round(float(np.mean(vals <= 0)) * 100, 1),
        })

    # Success metrics
    success_rate = (1 - ruin_probability) * 100

    return {
        "parameters": {
            "current_savings": current_savings,
            "monthly_contribution": monthly_contribution,
            "monthly_withdrawal": monthly_withdrawal,
            "current_age": current_age,
            "retirement_age": retirement_age,
            "end_age": end_age,
            "risk_level": risk_level,
            "expected_return": round(annual_mu * 100, 1),
            "expected_volatility": round(annual_sigma * 100, 1),
            "inflation_rate": round(inflation_rate * 100, 1),
            "social_security_monthly": social_security_monthly,
            "n_sims": n_sims,
        },
        "at_retirement": {
            "age": retirement_age,
            "median": round(float(np.median(retirement_balances))),
            "p10": round(float(np.percentile(retirement_balances, 10))),
            "p90": round(float(np.percentile(retirement_balances, 90))),
        },
        "at_end": {
            "age": end_age,
            "median": round(float(np.median(final_balances))),
            "p10": round(float(np.percentile(final_balances, 10))),
            "p90": round(float(np.percentile(final_balances, 90))),
            "mean": round(float(np.mean(final_balances))),
        },
        "success_rate": round(success_rate, 1),
        "ruin_probability": round(ruin_probability * 100, 1),
        "yearly_projections": yearly_data,
        "interpretation": _interpret_retirement(success_rate, ruin_probability, retirement_balances, monthly_withdrawal),
    }


def compute_safe_withdrawal_rate(
    savings: float,
    retirement_years: int = 30,
    risk_level: str = "moderate",
    target_success_rate: float = 95.0,
    n_sims: int = 3000,
    seed: int = 42,
) -> dict:
    """Find the maximum safe monthly withdrawal that maintains target success rate.

    Binary search over withdrawal amounts to find the highest withdrawal
    that keeps ruin probability below (100 - target_success_rate)%.

    The classic "4% rule" (Bengen 1994) suggests 4% initial withdrawal rate.
    This function computes the actual safe rate for current market conditions.

    Args:
        savings: Portfolio value at retirement
        retirement_years: Expected years in retirement
        risk_level: Investment allocation
        target_success_rate: Minimum acceptable success rate (%)
        n_sims: Number of simulations
        seed: Random seed

    Returns:
        Dict with safe withdrawal rate and comparison to 4% rule.
    """
    params = _ASSET_RETURNS.get(risk_level, _ASSET_RETURNS["moderate"])
    # Apply same arithmetic drift correction as simulate_retirement
    annual_arith_mu = params["mu"] + 0.5 * params["sigma"] ** 2
    daily_mu = annual_arith_mu / 252
    daily_sigma = params["sigma"] / np.sqrt(252)

    total_months = retirement_years * 12
    max_ruin_rate = (100 - target_success_rate) / 100

    df_t = 8
    t_scale = np.sqrt((df_t - 2) / df_t)

    def _ruin_rate(monthly_wd: float) -> float:
        """Compute ruin probability for a given withdrawal."""
        # Fresh RNG per call so binary search is deterministic (same seed → same paths)
        inner_rng = np.random.default_rng(seed)
        monthly_returns = np.zeros((total_months, n_sims))
        for m in range(total_months):
            daily = daily_mu + daily_sigma * t_scale * inner_rng.standard_t(df=df_t, size=(21, n_sims))
            monthly_returns[m, :] = np.exp(np.sum(np.log(1 + daily), axis=0)) - 1

        balances = np.zeros((total_months + 1, n_sims))
        balances[0, :] = savings
        monthly_inflation = 0.025 / 12
        for m in range(total_months):
            inflation = (1 + monthly_inflation) ** m
            balances[m + 1, :] = np.maximum(0, balances[m, :] * (1 + monthly_returns[m, :]) - monthly_wd * inflation)

        return float(np.mean(np.any(balances <= 0, axis=0)))

    # Binary search for max safe withdrawal
    lo, hi = 0, savings / total_months * 3  # Upper bound: 3x simple division
    for _ in range(15):  # ~15 iterations for good precision
        mid = (lo + hi) / 2
        rr = _ruin_rate(mid)
        if rr <= max_ruin_rate:
            lo = mid
        else:
            hi = mid

    safe_monthly = lo
    safe_annual = safe_monthly * 12
    safe_rate = safe_annual / savings * 100 if savings > 0 else 0

    # Compare to 4% rule
    four_pct_monthly = savings * 0.04 / 12

    return {
        "safe_monthly_withdrawal": round(safe_monthly, 0),
        "safe_annual_withdrawal": round(safe_annual, 0),
        "safe_withdrawal_rate_pct": round(safe_rate, 2),
        "four_pct_rule_monthly": round(four_pct_monthly, 0),
        "four_pct_rule_annual": round(savings * 0.04, 0),
        "vs_four_pct": round(safe_rate - 4.0, 2),
        "target_success_rate": target_success_rate,
        "retirement_years": retirement_years,
        "risk_level": risk_level,
        "interpretation": (
            f"Safe withdrawal rate: {safe_rate:.1f}% "
            f"({'above' if safe_rate > 4 else 'below'} the classic 4% rule). "
            f"This means you can safely withdraw ${safe_monthly:,.0f}/month "
            f"(${safe_annual:,.0f}/year) with {target_success_rate:.0f}% confidence "
            f"of not running out of money over {retirement_years} years."
        ),
    }


def _interpret_retirement(
    success_rate: float,
    ruin_probability: float,
    retirement_balances: np.ndarray,
    monthly_withdrawal: float,
) -> str:
    """Human-readable retirement simulation interpretation."""
    parts = []

    if success_rate >= 95:
        parts.append(f"Excellent: {success_rate:.0f}% success rate. Your plan is well-funded.")
    elif success_rate >= 85:
        parts.append(f"Good: {success_rate:.0f}% success rate. Consider building a small buffer.")
    elif success_rate >= 70:
        parts.append(f"Caution: {success_rate:.0f}% success rate. Consider reducing withdrawals or working longer.")
    else:
        parts.append(f"Warning: Only {success_rate:.0f}% success rate. Significant risk of running out of money.")

    median_at_ret = float(np.median(retirement_balances))
    if monthly_withdrawal > 0 and median_at_ret > 0:
        years_of_withdrawals = median_at_ret / (monthly_withdrawal * 12)
        parts.append(
            f"Median portfolio at retirement: ${median_at_ret:,.0f} "
            f"(~{years_of_withdrawals:.0f} years of withdrawals at current rate)."
        )

    return " ".join(parts)
