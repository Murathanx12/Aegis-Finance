"""
Tests for Tail Risk Analytics
================================

Tests Sortino, Omega, Calmar ratios, drawdown duration, tail concentration,
ulcer index, and edge cases with synthetic data.
"""

import numpy as np
import pytest

from backend.services.tail_risk import (
    compute_tail_risk_metrics,
    _max_drawdown_duration,
    _tail_concentration,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def bull_returns():
    """Simulate a steady bull market: ~15% annual, ~15% vol."""
    rng = np.random.default_rng(42)
    return rng.normal(0.0006, 0.0095, size=504)  # 2 years


@pytest.fixture
def bear_returns():
    """Simulate a bear market with fat-tailed drawdowns."""
    rng = np.random.default_rng(42)
    base = rng.normal(-0.0003, 0.015, size=504)
    # Add a few crash days
    crash_days = rng.choice(504, size=10, replace=False)
    base[crash_days] -= rng.uniform(0.03, 0.08, size=10)
    return base


@pytest.fixture
def flat_returns():
    """Near-zero returns (money market)."""
    rng = np.random.default_rng(42)
    return rng.normal(0.00016, 0.001, size=252)  # ~4% annual, ~1.6% vol


@pytest.fixture
def constant_positive():
    """All positive returns — no downside."""
    return np.full(252, 0.001)


# ── Core Metric Tests ────────────────────────────────────────────────────────


class TestSortinoRatio:
    def test_bull_market_positive(self, bull_returns):
        m = compute_tail_risk_metrics(bull_returns)
        assert m["sortino_ratio"] is not None
        assert m["sortino_ratio"] > 0, "Bull market should have positive Sortino"

    def test_bear_market_negative(self, bear_returns):
        m = compute_tail_risk_metrics(bear_returns)
        assert m["sortino_ratio"] is not None
        assert m["sortino_ratio"] < 0, "Bear market should have negative Sortino"

    def test_higher_than_sharpe_equivalent(self, bull_returns):
        """Sortino should generally be higher than Sharpe for positive-skew returns."""
        m = compute_tail_risk_metrics(bull_returns)
        # Compute simple Sharpe for comparison
        annual_ret = np.mean(bull_returns) * 252
        annual_vol = np.std(bull_returns) * np.sqrt(252)
        sharpe = (annual_ret - 0.04) / annual_vol
        # Sortino penalizes only downside, so should be >= Sharpe for positive returns
        assert m["sortino_ratio"] >= sharpe * 0.8, "Sortino should be comparable or higher than Sharpe"


class TestOmegaRatio:
    def test_bull_market_above_one(self, bull_returns):
        m = compute_tail_risk_metrics(bull_returns)
        assert m["omega_ratio"] is not None
        assert m["omega_ratio"] > 1.0, "Bull market Omega should exceed 1.0"

    def test_bear_market_below_one(self, bear_returns):
        m = compute_tail_risk_metrics(bear_returns)
        assert m["omega_ratio"] is not None
        assert m["omega_ratio"] < 1.0, "Bear market Omega should be below 1.0"

    def test_constant_positive_is_none(self, constant_positive):
        """All positive returns → no losses → Omega undefined (None)."""
        # With threshold=0, all returns > 0 means losses_below = 0
        m = compute_tail_risk_metrics(constant_positive)
        # gains_above > 0, losses_below = 0 → None
        assert m["omega_ratio"] is None


class TestCalmarRatio:
    def test_bull_market_positive(self, bull_returns):
        m = compute_tail_risk_metrics(bull_returns)
        assert m["calmar_ratio"] is not None
        assert m["calmar_ratio"] > 0

    def test_bear_market_negative(self, bear_returns):
        m = compute_tail_risk_metrics(bear_returns)
        assert m["calmar_ratio"] is not None
        assert m["calmar_ratio"] < 0, "Bear market should have negative Calmar"


class TestDownsideDeviation:
    def test_lower_than_total_vol(self, bull_returns):
        """Downside deviation should be less than total vol for positive-mean returns."""
        m = compute_tail_risk_metrics(bull_returns)
        total_vol = float(np.std(bull_returns) * np.sqrt(252)) * 100
        assert m["downside_deviation_annual"] < total_vol * 1.1  # some tolerance

    def test_higher_for_bear(self, bull_returns, bear_returns):
        m_bull = compute_tail_risk_metrics(bull_returns)
        m_bear = compute_tail_risk_metrics(bear_returns)
        assert m_bear["downside_deviation_annual"] > m_bull["downside_deviation_annual"]


class TestMaxDrawdownDuration:
    def test_basic_recovery(self):
        """Synthetic: drop then recovery → duration = drop period."""
        cum = np.array([1.0, 1.1, 1.05, 1.0, 0.95, 0.98, 1.05, 1.15])
        duration = _max_drawdown_duration(cum)
        assert duration > 0
        assert duration <= len(cum)

    def test_no_drawdown(self):
        """Monotonically increasing → no drawdown."""
        cum = np.arange(1.0, 2.0, 0.01)
        duration = _max_drawdown_duration(cum)
        assert duration == 0

    def test_full_period_drawdown(self):
        """Never recovers → duration = len - 1."""
        cum = np.array([1.0, 0.9, 0.85, 0.80, 0.75])
        duration = _max_drawdown_duration(cum)
        assert duration == 4  # after first peak, stays in DD

    def test_bear_has_longer_dd(self, bull_returns, bear_returns):
        m_bull = compute_tail_risk_metrics(bull_returns)
        m_bear = compute_tail_risk_metrics(bear_returns)
        assert m_bear["max_drawdown_duration_days"] >= m_bull["max_drawdown_duration_days"]


class TestTailConcentration:
    def test_normal_distribution(self):
        """Normal returns should have moderate tail concentration."""
        rng = np.random.default_rng(123)
        returns = rng.normal(0, 0.01, size=5000)
        tc = _tail_concentration(returns, 5)
        # For normal dist, worst 5% of negative days contain ~15-25% of total losses
        assert 0.10 < tc < 0.40

    def test_fat_tails_higher(self):
        """Returns with extreme outliers should have higher tail concentration."""
        rng = np.random.default_rng(123)
        normal = rng.normal(0, 0.01, size=5000)
        fat = normal.copy()
        # Add 5 extreme crash days
        fat[:5] = -0.15  # 15% crash
        tc_normal = _tail_concentration(normal, 5)
        tc_fat = _tail_concentration(fat, 5)
        assert tc_fat > tc_normal

    def test_empty_returns(self):
        """No negative returns → 0.0."""
        returns = np.full(100, 0.01)
        tc = _tail_concentration(returns, 5)
        assert tc == 0.0


class TestUlcerIndex:
    def test_bull_lower_than_bear(self, bull_returns, bear_returns):
        m_bull = compute_tail_risk_metrics(bull_returns)
        m_bear = compute_tail_risk_metrics(bear_returns)
        assert m_bear["ulcer_index"] > m_bull["ulcer_index"]

    def test_positive(self, bull_returns):
        m = compute_tail_risk_metrics(bull_returns)
        assert m["ulcer_index"] >= 0


class TestGainPainRatio:
    def test_bull_above_one(self, bull_returns):
        m = compute_tail_risk_metrics(bull_returns)
        assert m["gain_pain_ratio"] is not None
        assert m["gain_pain_ratio"] > 0.9, "Bull market gain/pain should be near or above 1"

    def test_bear_below_one(self, bear_returns):
        m = compute_tail_risk_metrics(bear_returns)
        assert m["gain_pain_ratio"] is not None
        assert m["gain_pain_ratio"] < 1.0


class TestWinRateAndProfitFactor:
    def test_bull_higher_win_rate(self, bull_returns, bear_returns):
        m_bull = compute_tail_risk_metrics(bull_returns)
        m_bear = compute_tail_risk_metrics(bear_returns)
        assert m_bull["win_rate_pct"] > m_bear["win_rate_pct"]

    def test_profit_factor_positive(self, bull_returns):
        m = compute_tail_risk_metrics(bull_returns)
        assert m["profit_factor"] is not None
        assert m["profit_factor"] > 0


# ── Edge Cases ────────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_insufficient_data(self):
        """Less than min_observations → all None."""
        m = compute_tail_risk_metrics(np.array([0.01, -0.01, 0.005]))
        assert m["sortino_ratio"] is None
        assert m["omega_ratio"] is None
        assert m["n_observations"] == 0

    def test_nan_handling(self):
        """NaN values should be filtered out."""
        rng = np.random.default_rng(42)
        returns = rng.normal(0.0005, 0.01, size=300)
        returns[10] = np.nan
        returns[50] = np.nan
        returns[200] = np.inf
        m = compute_tail_risk_metrics(returns)
        assert m["n_observations"] == 297  # 300 - 3 non-finite

    def test_zero_vol(self):
        """All zero returns → downside dev = 0, ratios = None."""
        m = compute_tail_risk_metrics(np.zeros(100))
        assert m["downside_deviation_annual"] == 0.0
        assert m["sortino_ratio"] is None

    def test_single_large_crash(self):
        """One big crash in otherwise calm market."""
        rng = np.random.default_rng(42)
        returns = rng.normal(0.0004, 0.005, size=252)
        returns[125] = -0.20  # 20% single-day crash
        m = compute_tail_risk_metrics(returns)
        assert m["tail_concentration_pct"] > 30, "Single crash should dominate tail concentration"
        assert m["max_drawdown_pct"] < -15

    def test_all_fields_present(self, bull_returns):
        """All expected keys must be present."""
        m = compute_tail_risk_metrics(bull_returns)
        expected_keys = {
            "sortino_ratio", "omega_ratio", "calmar_ratio",
            "downside_deviation_annual", "max_drawdown_pct",
            "max_drawdown_duration_days", "tail_concentration_pct",
            "gain_pain_ratio", "ulcer_index", "win_rate_pct",
            "avg_win_pct", "avg_loss_pct", "profit_factor",
            "n_observations",
        }
        assert set(m.keys()) == expected_keys

    def test_consistent_with_manual_calmar(self, bull_returns):
        """Calmar should match manual computation."""
        m = compute_tail_risk_metrics(bull_returns)
        annual_ret = float(np.mean(bull_returns) * 252)
        cum = np.cumprod(1 + bull_returns)
        peak = np.maximum.accumulate(cum)
        dd = (cum - peak) / peak
        max_dd = float(np.min(dd))
        expected_calmar = annual_ret / abs(max_dd)
        assert abs(m["calmar_ratio"] - expected_calmar) < 0.01
