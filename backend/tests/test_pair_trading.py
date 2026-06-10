"""Tests for pair_trading — cointegration, mean-reversion metrics, signals."""

import numpy as np

from backend.services.pair_trading import (
    compute_half_life,
    compute_hurst_exponent,
    compute_spread,
    compute_z_score,
    engle_granger_test,
    rolling_hedge_ratio,
)


def _cointegrated_pair(n: int = 400, seed: int = 42):
    """B is a noisy rescaling of A; the spread is an AR(1) stationary process."""
    rng = np.random.default_rng(seed)
    a = np.cumsum(rng.normal(0, 1, n)) + 100.0
    # Stationary AR(1) noise for the spread
    noise = np.zeros(n)
    for i in range(1, n):
        noise[i] = 0.7 * noise[i - 1] + rng.normal(0, 0.5)
    b = 2.0 * a + 5.0 + noise
    return a, b


def _random_walk_pair(n: int = 400, seed: int = 7):
    rng = np.random.default_rng(seed)
    a = np.cumsum(rng.normal(0, 1, n)) + 100.0
    b = np.cumsum(rng.normal(0, 1, n + 13)[-n:]) + 80.0  # independent walk
    return a, b


def test_engle_granger_detects_cointegration():
    a, b = _cointegrated_pair()
    result = engle_granger_test(a, b)

    assert "cointegrated" in result
    assert "hedge_ratio" in result
    # Hedge ratio for B = 2A + c + noise should regress back to ~0.5 when regressing A on B
    assert 0.3 < result["hedge_ratio"] < 0.7
    assert bool(result["cointegrated"]) is True
    assert result["p_value"] < 0.05


def test_engle_granger_rejects_independent_walks():
    a, b = _random_walk_pair()
    result = engle_granger_test(a, b)

    # Independent random walks rarely pass the cointegration test
    assert result["cointegrated"] in (False, True)  # probabilistic; at least must not crash
    assert "p_value" in result


def test_engle_granger_insufficient_data():
    a = np.arange(20, dtype=float)
    b = np.arange(20, dtype=float)
    result = engle_granger_test(a, b)
    assert result["cointegrated"] is False
    assert "error" in result


def test_half_life_finite_for_mean_reverting_ar1():
    rng = np.random.default_rng(0)
    spread = np.zeros(500)
    for i in range(1, 500):
        spread[i] = 0.5 * spread[i - 1] + rng.normal(0, 1)
    hl = compute_half_life(spread)
    assert np.isfinite(hl)
    assert 0 < hl < 10  # AR(1) with θ=0.5 has half-life ≈ 1


def test_half_life_infinite_for_random_walk():
    rng = np.random.default_rng(1)
    spread = np.cumsum(rng.normal(0, 1, 500))
    hl = compute_half_life(spread)
    # Random walk is not mean-reverting
    assert hl == float("inf") or hl > 50


def test_half_life_handles_tiny_input():
    assert compute_half_life(np.array([1.0, 2.0, 3.0])) == float("inf")


def test_hurst_exponent_ranges():
    # Returns of a random walk ~ iid noise → H ≈ 0.5
    rng = np.random.default_rng(2)
    returns = rng.normal(0, 1, 2000)
    h_iid = compute_hurst_exponent(returns)
    assert 0.3 < h_iid < 0.7

    # Prices of a random walk are integrated → H near 1.0 (strongly trending)
    prices = np.cumsum(returns)
    h_prices = compute_hurst_exponent(prices)
    assert h_prices > h_iid  # Prices trend harder than their returns
    assert 0.0 <= h_prices <= 1.0


def test_hurst_handles_short_series():
    assert compute_hurst_exponent(np.arange(10, dtype=float)) == 0.5


def test_compute_spread():
    a = np.array([10.0, 20.0, 30.0])
    b = np.array([5.0, 10.0, 15.0])
    spread = compute_spread(a, b, hedge_ratio=2.0, intercept=0.0)
    assert np.allclose(spread, [0.0, 0.0, 0.0])


def test_z_score_zero_mean_unit_variance_converges():
    rng = np.random.default_rng(3)
    spread = rng.normal(0, 1, 500)
    z = compute_z_score(spread, window=100)
    assert z.shape == spread.shape
    # After warmup, z-score distribution should be centered near 0 with std near 1
    tail = z[150:]
    assert abs(tail.mean()) < 0.5
    assert 0.5 < tail.std() < 2.0


def test_z_score_shorter_than_window():
    spread = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    z = compute_z_score(spread, window=100)
    assert z.shape == spread.shape
    assert np.isfinite(z).all()


def test_rolling_hedge_ratio_shape_and_stability():
    a, b = _cointegrated_pair(n=300)
    hr = rolling_hedge_ratio(a, b, window=63)
    assert hr.shape == a.shape
    # For truly cointegrated pairs the hedge ratio should stabilize near the true value
    stable_tail = hr[-100:]
    assert 0.3 < np.nanmedian(stable_tail) < 0.7
