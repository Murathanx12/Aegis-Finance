"""Tests for the MPC-style convex optimizer."""

from __future__ import annotations

import numpy as np
import pandas as pd

from backend.services.mpc_optimizer import (
    optimize_single_period,
    optimize_multi_period,
    _psd_wrap,
)


def _three_asset_inputs(seed: int = 42):
    rng = np.random.default_rng(seed)
    tickers = ["A", "B", "C"]
    mu = pd.Series([0.12, 0.08, 0.04], index=tickers)
    # Craft a covariance where A is high-vol, C is low-vol, correlations ~0.3
    vols = np.array([0.28, 0.18, 0.10])
    corr = np.array([[1.0, 0.3, 0.2], [0.3, 1.0, 0.3], [0.2, 0.3, 1.0]])
    Sigma = np.outer(vols, vols) * corr
    Sigma = pd.DataFrame(Sigma, index=tickers, columns=tickers)
    return mu, Sigma


class TestSinglePeriod:
    def test_sum_to_one_and_bounds(self):
        mu, Sigma = _three_asset_inputs()
        result = optimize_single_period(mu, Sigma, gamma=3.0, max_weight=0.7)
        assert result["status"] in {"optimal", "optimal_inaccurate"}
        w = np.array(list(result["weights"].values()))
        assert abs(w.sum() - 1.0) < 1e-4
        assert (w >= -1e-6).all()
        assert (w <= 0.7 + 1e-6).all()

    def test_higher_gamma_reduces_risk(self):
        mu, Sigma = _three_asset_inputs()
        low = optimize_single_period(mu, Sigma, gamma=0.5)
        high = optimize_single_period(mu, Sigma, gamma=10.0)
        # Risk-averse solution must have lower variance
        assert high["metrics"]["volatility"] <= low["metrics"]["volatility"] + 1e-4

    def test_transaction_cost_reduces_turnover(self):
        mu, Sigma = _three_asset_inputs()
        current = {"A": 0.10, "B": 0.30, "C": 0.60}
        free = optimize_single_period(mu, Sigma, current_weights=current, transaction_cost_bps=0)
        pricey = optimize_single_period(
            mu, Sigma, current_weights=current, transaction_cost_bps=500
        )
        # 5% round-trip cost — any rational optimizer trades less
        assert pricey["metrics"]["turnover"] <= free["metrics"]["turnover"] + 1e-6

    def test_tracking_error_constraint_pulls_toward_benchmark(self):
        mu, Sigma = _three_asset_inputs()
        benchmark = {"A": 0.33, "B": 0.33, "C": 0.34}
        loose = optimize_single_period(
            mu, Sigma, benchmark_weights=benchmark, tracking_error_limit=0.20
        )
        tight = optimize_single_period(
            mu, Sigma, benchmark_weights=benchmark, tracking_error_limit=0.02
        )
        # Tight TE must produce weights closer to benchmark
        te_loose = loose["tracking_error"]["annualised"]
        te_tight = tight["tracking_error"]["annualised"]
        assert te_tight <= te_loose + 1e-4
        assert te_tight <= 0.021  # respects the limit (with tiny tolerance)

    def test_sector_cap_respected(self):
        mu, Sigma = _three_asset_inputs()
        sector_map = {"A": "Tech", "B": "Tech", "C": "Utilities"}
        # max_weight high enough to make Utilities feasible alongside Tech cap
        result = optimize_single_period(
            mu,
            Sigma,
            sector_map=sector_map,
            sector_caps={"Tech": 0.40},
            max_weight=0.8,
            gamma=0.5,  # would normally load up Tech
        )
        assert result["status"] in {"optimal", "optimal_inaccurate"}
        exp = result["sector_exposures"]
        assert exp["Tech"] <= 0.40 + 1e-4

    def test_trades_sum_to_zero(self):
        mu, Sigma = _three_asset_inputs()
        current = {"A": 0.10, "B": 0.30, "C": 0.60}
        result = optimize_single_period(mu, Sigma, current_weights=current)
        trade_sum = sum(result["trades"].values())
        assert abs(trade_sum) < 1e-4  # redistribution sums to zero


class TestMultiPeriod:
    def test_rolls_horizon_steps(self):
        mu, Sigma = _three_asset_inputs()
        result = optimize_multi_period(mu, Sigma, horizon=3, return_decay=0.2)
        assert result["horizon"] == 3
        assert len(result["steps"]) == 3
        assert all("weights" in s for s in result["steps"])
        assert result["cumulative"]["turnover"] >= 0

    def test_return_decay_reduces_churn(self):
        mu, Sigma = _three_asset_inputs()
        no_decay = optimize_multi_period(mu, Sigma, horizon=4, return_decay=0.0)
        decay = optimize_multi_period(mu, Sigma, horizon=4, return_decay=0.5)
        # With heavy decay, later-period forecasts are weaker, so we'd expect
        # less aggressive rebalancing late in the horizon. Cumulative turnover
        # shouldn't be dramatically higher than the no-decay case.
        assert decay["cumulative"]["turnover"] <= no_decay["cumulative"]["turnover"] * 1.1


class TestPsdWrap:
    def test_psd_wrap_makes_symmetric_psd(self):
        rng = np.random.default_rng(42)
        A = rng.normal(size=(4, 4))
        S = _psd_wrap(A @ A.T)
        # symmetric
        assert np.allclose(S, S.T)
        # all eigenvalues ≥ 0
        assert np.linalg.eigvalsh(S).min() >= -1e-9

    def test_psd_wrap_handles_non_psd_input(self):
        A = np.array([[1.0, 2.0], [2.0, 1.0]])  # eigenvalues 3, -1 → not PSD
        S = _psd_wrap(A)
        assert np.linalg.eigvalsh(S).min() >= 0
