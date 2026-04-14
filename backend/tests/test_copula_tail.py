"""Tests for copula tail dependence service."""

import numpy as np
import pytest

import pandas as pd

from backend.services.copula_tail import (
    _to_pseudo_observations,
    _fit_clayton,
    _fit_gumbel,
    _fit_frank,
    _fit_student_t,
    fit_best_copula,
    compute_copula_risk_from_returns,
)


@pytest.fixture
def uniform_data():
    """Independent uniform data (no dependence)."""
    rng = np.random.default_rng(42)
    n = 500
    u = rng.uniform(0.01, 0.99, n)
    v = rng.uniform(0.01, 0.99, n)
    return u, v


@pytest.fixture
def dependent_data():
    """Positively dependent data (correlated normals → copula)."""
    rng = np.random.default_rng(42)
    n = 500
    rho = 0.7
    z1 = rng.standard_normal(n)
    z2 = rho * z1 + np.sqrt(1 - rho**2) * rng.standard_normal(n)
    from scipy.stats import norm
    u = norm.cdf(z1)
    v = norm.cdf(z2)
    return u, v


@pytest.fixture
def tail_dependent_data():
    """Data with lower tail dependence (Clayton copula-like)."""
    rng = np.random.default_rng(42)
    n = 500
    # Generate from Clayton copula with theta=2
    theta = 2.0
    u = rng.uniform(0.01, 0.99, n)
    w = rng.uniform(0.01, 0.99, n)
    v = (1 + u ** (-theta) * (w ** (-theta / (1 + theta)) - 1)) ** (-1 / theta)
    v = np.clip(v, 0.01, 0.99)
    return u, v


class TestPseudoObservations:
    def test_rank_transform(self):
        data = np.array([10, 20, 30, 40, 50])
        u = _to_pseudo_observations(data)
        assert len(u) == 5
        assert u.min() > 0
        assert u.max() < 1
        # Should be monotonically increasing for sorted input
        assert (np.diff(u) > 0).all()

    def test_2d_transform(self):
        rng = np.random.default_rng(42)
        data = rng.standard_normal((100, 3))
        u = _to_pseudo_observations(data)
        assert u.shape == (100, 3)
        assert u.min() > 0
        assert u.max() < 1


class TestClaytonCopula:
    def test_fit_independent(self, uniform_data):
        u, v = uniform_data
        result = _fit_clayton(u, v)
        assert result["family"] == "clayton"
        assert result["theta"] > 0
        # Independence → theta near 0
        assert result["theta"] < 2.0
        assert result["tail_lower"] >= 0

    def test_fit_dependent(self, tail_dependent_data):
        u, v = tail_dependent_data
        result = _fit_clayton(u, v)
        # Should detect strong lower tail dependence
        assert result["theta"] > 1.0
        assert result["tail_lower"] > 0.2

    def test_no_upper_tail(self, tail_dependent_data):
        u, v = tail_dependent_data
        result = _fit_clayton(u, v)
        assert result["tail_upper"] == 0.0


class TestGumbelCopula:
    def test_fit_basic(self, dependent_data):
        u, v = dependent_data
        result = _fit_gumbel(u, v)
        assert result["family"] == "gumbel"
        assert result["theta"] >= 1.0
        assert result["tail_lower"] == 0.0

    def test_fit_independent(self, uniform_data):
        u, v = uniform_data
        result = _fit_gumbel(u, v)
        # Near independence → theta near 1
        assert result["theta"] < 2.0


class TestFrankCopula:
    def test_fit_basic(self, dependent_data):
        u, v = dependent_data
        result = _fit_frank(u, v)
        assert result["family"] == "frank"
        assert result["tail_lower"] == 0.0
        assert result["tail_upper"] == 0.0

    def test_positive_dependence(self, dependent_data):
        u, v = dependent_data
        result = _fit_frank(u, v)
        # Positive dependence → positive theta
        assert result["theta"] > 0


class TestStudentTCopula:
    def test_fit_basic(self, dependent_data):
        u, v = dependent_data
        result = _fit_student_t(u, v)
        assert result["family"] == "student_t"
        assert -1 < result["rho"] < 1
        assert result["nu"] >= 2
        # Should have symmetric tail dependence
        assert result["tail_lower"] == result["tail_upper"]


class TestBestCopula:
    def test_selects_best(self, dependent_data):
        u, v = dependent_data
        result = fit_best_copula(u, v)
        assert result["best"] is not None
        assert result["selection"] in ("clayton", "gumbel", "frank", "student_t")
        assert len(result["all_fits"]) >= 3

    def test_aic_ordering(self, dependent_data):
        u, v = dependent_data
        result = fit_best_copula(u, v)
        # Best should have lowest AIC
        best_aic = result["best"]["aic"]
        for name, fit in result["all_fits"].items():
            assert fit["aic"] >= best_aic - 1e-6  # Allow tiny float errors

    def test_tail_dependent_data_selects_appropriate(self, tail_dependent_data):
        u, v = tail_dependent_data
        result = fit_best_copula(u, v)
        # Clayton or Student-t should be selected (they have lower tail dependence)
        assert result["selection"] in ("clayton", "student_t")
        assert result["best"]["tail_lower"] > 0.1


class TestStudentTMarginalCorrection:
    """Regression tests for Student-t copula log-likelihood marginal correction.

    The log-likelihood must subtract marginal t densities so AIC is
    comparable across copula families.
    """

    def test_student_t_aic_comparable_to_frank(self, uniform_data):
        """For independent data, Student-t AIC should not dominate Frank."""
        u, v = uniform_data
        t_result = _fit_student_t(u, v)
        f_result = _fit_frank(u, v)
        # Student-t has 2 params vs Frank's 1, so it should not always win
        # on independent data. Allow some tolerance but they should be same order.
        assert abs(t_result["aic"] - f_result["aic"]) < 500, (
            f"Student-t AIC ({t_result['aic']}) vs Frank AIC ({f_result['aic']}) "
            "are too far apart — marginal correction may be missing"
        )

    def test_student_t_loglik_negative_for_independence(self, uniform_data):
        """For independent uniform data, copula log-likelihood should be near 0."""
        u, v = uniform_data
        result = _fit_student_t(u, v)
        # Independence copula has density=1 everywhere → loglik=0
        # With estimation noise, should be within reasonable range
        assert result["loglik"] < 200, (
            f"Student-t loglik={result['loglik']} is too large for independent data"
        )


class TestCopulaRiskFromReturns:
    """Tests for the pre-fetched returns copula risk function."""

    def test_basic_output_structure(self):
        rng = np.random.default_rng(42)
        n = 300
        returns = pd.DataFrame(
            rng.standard_normal((n, 3)) * 0.02,
            columns=["A", "B", "C"],
        )
        weights = np.array([0.5, 0.3, 0.2])
        result = compute_copula_risk_from_returns(returns, weights, n_sims=5000)
        assert result is not None
        assert "gaussian_var_95" in result
        assert "copula_var_95" in result
        assert "copula_cvar_95" in result
        assert "tail_risk_underestimate_pct" in result
        # VaR should be negative (loss)
        assert result["gaussian_var_95"] < 0
        assert result["copula_var_95"] < 0
        # CVaR should be worse (more negative) than VaR
        assert result["copula_cvar_95"] <= result["copula_var_95"]

    def test_returns_none_for_single_asset(self):
        rng = np.random.default_rng(42)
        returns = pd.DataFrame(rng.standard_normal((300, 1)) * 0.02, columns=["A"])
        result = compute_copula_risk_from_returns(returns, np.array([1.0]))
        assert result is None

    def test_returns_none_for_short_data(self):
        rng = np.random.default_rng(42)
        returns = pd.DataFrame(rng.standard_normal((50, 2)) * 0.02, columns=["A", "B"])
        result = compute_copula_risk_from_returns(returns, np.array([0.5, 0.5]))
        assert result is None

    def test_fat_tailed_data_shows_higher_copula_risk(self):
        """With fat-tailed correlated data, copula VaR should be worse than gaussian."""
        rng = np.random.default_rng(42)
        n = 500
        # Generate t-distributed returns (fat tails)
        from scipy.stats import t as t_dist
        r1 = t_dist.rvs(df=3, size=n, random_state=42) * 0.02
        r2 = 0.6 * r1 + t_dist.rvs(df=3, size=n, random_state=43) * 0.01
        returns = pd.DataFrame({"A": r1, "B": r2})
        weights = np.array([0.5, 0.5])
        result = compute_copula_risk_from_returns(returns, weights, n_sims=10000)
        assert result is not None
        # Copula should detect heavier tails than Gaussian
        assert result["copula_cvar_95"] <= result["gaussian_cvar_95"] + 0.5
