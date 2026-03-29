"""
Monte Carlo Validation Script
================================

Validates that the two critical bug fixes are working:
  FIX 1: Variance drag (no double-counting of Ito correction)
  FIX 2: Jump compensator sign (Merton 1976)

Also validates scenario probability weighting.

Usage:
    cd aegis-finance
    python -m engine.validation.validate_fixes
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np


def test_variance_drag():
    """Test 1: Median terminal log-return should equal mu_geometric * T.

    With the variance drag bug, the simulation would produce:
        median(log(S_T/S_0)) ≈ (mu_geo - 0.5*sigma^2) * T  (too low)
    After fix:
        median(log(S_T/S_0)) ≈ mu_geo * T  (correct)
    """
    from backend.services.monte_carlo import simulate_paths

    mu_geo = 0.08  # 8% geometric annual return
    sigma = 0.18   # 18% annual volatility
    T = 5           # 5 years
    days = T * 252
    n_sims = 10000
    S0 = 100.0

    # Run with NO jumps, NO mean reversion, NO ML inputs
    paths = simulate_paths(
        start_price=S0,
        historical_mu=mu_geo,
        historical_sigma=sigma,
        days=days,
        n_sims=n_sims,
        crash_freq=0.0,       # No jumps
        risk_score=0.0,
        scenario={"drift_adj": 0.0, "vol_mult": 1.0, "crash_mult": 0.0},
        seed=42,
    )

    final = paths[-1]
    log_returns = np.log(final / S0)
    median_log_return = np.median(log_returns)
    expected_log_return = mu_geo * T  # = 0.40

    tolerance = 0.01 * T  # 1% per year = 5% total
    error = abs(median_log_return - expected_log_return)

    passed = error < tolerance
    print(f"TEST 1 — Variance Drag Fix:")
    print(f"  Expected median log-return: {expected_log_return:.4f}")
    print(f"  Actual median log-return:   {median_log_return:.4f}")
    print(f"  Error: {error:.4f} (tolerance: {tolerance:.4f})")
    print(f"  {'PASS' if passed else 'FAIL'}")
    print()
    return passed


def test_jump_compensator():
    """Test 2: Ensemble average terminal price should equal S0 * exp(mu * T).

    With jump compensator sign error, jumps mechanically depress returns.
    After fix: E[S_T] ≈ S0 * exp(mu_arithmetic * T) regardless of jump params.
    """
    from backend.services.monte_carlo import simulate_paths

    mu_geo = 0.08
    sigma = 0.18
    T = 5
    days = T * 252
    n_sims = 10000
    S0 = 100.0

    # Convert geometric to arithmetic for expected price calculation
    mu_arith = mu_geo + 0.5 * sigma ** 2

    # Run WITH jumps
    paths = simulate_paths(
        start_price=S0,
        historical_mu=mu_geo,
        historical_sigma=sigma,
        days=days,
        n_sims=20000,  # More sims for stable mean estimate
        crash_freq=0.07,      # 7% annual jump rate
        risk_score=0.0,
        scenario={"drift_adj": 0.0, "vol_mult": 1.0, "crash_mult": 1.0},
        seed=42,
    )

    final = paths[-1]
    mean_final = final.mean()
    expected_final = S0 * np.exp(mu_arith * T)

    # 5% tolerance — OU vol dynamics, leverage effect, and return cap
    # intentionally shift the distribution; we just verify the compensator
    # is directionally correct (mean > no-compensator baseline)
    tolerance = 0.05
    relative_error = abs(mean_final - expected_final) / expected_final

    passed = relative_error < tolerance
    print(f"TEST 2 — Jump Compensator Fix:")
    print(f"  Expected mean final price: ${expected_final:.2f}")
    print(f"  Actual mean final price:   ${mean_final:.2f}")
    print(f"  Relative error: {relative_error:.4f} (tolerance: {tolerance:.4f})")
    print(f"  {'PASS' if passed else 'FAIL'}")
    print()
    return passed


def test_scenario_weights():
    """Test 3: Probability-weighted scenario return should be +3% to +7%."""
    from backend.config import get_scenario_configs

    scenarios = get_scenario_configs()

    weighted_return = 0.0
    total_prob = 0.0
    print("TEST 3 — Scenario Weights:")
    for name, scfg in scenarios.items():
        prob = scfg["probability"]
        ret = scfg.get("return", 0.0)
        weighted_return += prob * ret
        total_prob += prob
        print(f"  {name:25s}: prob={prob:.2f}, return={ret*100:+.1f}%")

    print(f"\n  Total probability: {total_prob:.4f}")
    print(f"  Probability-weighted return: {weighted_return*100:.2f}%")

    passed = 0.03 <= weighted_return <= 0.07
    print(f"  In range [+3%, +7%]: {'PASS' if passed else 'FAIL'}")
    print()
    return passed


def test_no_negative_major_tickers():
    """Test 4: Basic sanity — MC with positive drift should produce positive expected returns."""
    from backend.services.monte_carlo import simulate_paths

    mu_geo = 0.06  # Conservative 6% drift
    sigma = 0.20
    T = 5
    days = T * 252
    n_sims = 5000
    S0 = 100.0

    paths = simulate_paths(
        start_price=S0,
        historical_mu=mu_geo,
        historical_sigma=sigma,
        days=days,
        n_sims=n_sims,
        crash_freq=0.05,
        risk_score=0.0,
        scenario={"drift_adj": 0.0, "vol_mult": 1.0, "crash_mult": 1.0},
        seed=123,
    )

    final = paths[-1]
    median_return = (np.median(final) / S0 - 1) * 100
    mean_return = (final.mean() / S0 - 1) * 100

    passed = median_return > 0 and mean_return > 0
    print(f"TEST 4 — Positive Returns Sanity:")
    print(f"  Median 5Y return: {median_return:+.1f}%")
    print(f"  Mean 5Y return:   {mean_return:+.1f}%")
    print(f"  Both positive: {'PASS' if passed else 'FAIL'}")
    print()
    return passed


if __name__ == "__main__":
    print("=" * 60)
    print("AEGIS FINANCE — Monte Carlo Validation Suite")
    print("=" * 60)
    print()

    results = {
        "Variance Drag Fix": test_variance_drag(),
        "Jump Compensator Fix": test_jump_compensator(),
        "Scenario Weights": test_scenario_weights(),
        "Positive Returns": test_no_negative_major_tickers(),
    }

    print("=" * 60)
    print("SUMMARY:")
    all_passed = True
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {name:30s}: {status}")
        if not passed:
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED — review output above")
        sys.exit(1)
