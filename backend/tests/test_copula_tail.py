"""Tests for copula tail dependence service."""

import numpy as np
import pytest

from backend.services.copula_tail import (
    _to_pseudo_observations,
    _fit_clayton,
    _fit_gumbel,
    _fit_frank,
    _fit_student_t,
    fit_best_copula,
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
