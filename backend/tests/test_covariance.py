"""Tests for denoised covariance matrix estimation."""

import numpy as np
import pandas as pd
import pytest

from backend.services.covariance import (
    marchenko_pastur_bound,
    denoise_covariance,
    estimate_covariance,
    covariance_diagnostics,
)


@pytest.fixture
def random_returns():
    """Generate synthetic returns with known structure: signal + noise."""
    rng = np.random.default_rng(42)
    T = 504  # 2 years
    N = 20   # 20 assets

    # Create factor structure: 3 factors + noise
    factors = rng.standard_normal((T, 3))
    loadings = rng.standard_normal((3, N)) * 0.3
    noise = rng.standard_normal((T, N)) * 0.01

    returns_data = factors @ loadings + noise
    columns = [f"Asset_{i}" for i in range(N)]
    return pd.DataFrame(returns_data, columns=columns)


@pytest.fixture
def small_returns():
    """Small dataset where T < N to test fallback."""
    rng = np.random.default_rng(42)
    T = 30
    N = 50
    data = rng.standard_normal((T, N)) * 0.01
    columns = [f"Asset_{i}" for i in range(N)]
    return pd.DataFrame(data, columns=columns)


class TestMarchenkoPasturBound:
    def test_basic_bound(self):
        bound = marchenko_pastur_bound(T=252, N=20)
        # For q = 252/20 = 12.6, bound ≈ var * (1 + 1/sqrt(12.6))^2
        assert bound > 1.0
        assert bound < 5.0

    def test_more_assets_higher_bound(self):
        """More assets relative to time → more noise → higher bound."""
        bound_few = marchenko_pastur_bound(T=252, N=10)
        bound_many = marchenko_pastur_bound(T=252, N=100)
        assert bound_many > bound_few

    def test_more_data_lower_bound(self):
        """More observations → less noise → lower bound."""
        bound_short = marchenko_pastur_bound(T=100, N=20)
        bound_long = marchenko_pastur_bound(T=1000, N=20)
        assert bound_long < bound_short


class TestDenoiseCovariance:
    def test_output_shape(self, random_returns):
        cov = denoise_covariance(random_returns, detone=False)
        assert cov.shape == (20, 20)
        assert list(cov.columns) == list(random_returns.columns)

    def test_symmetric(self, random_returns):
        cov = denoise_covariance(random_returns, detone=False)
        np.testing.assert_allclose(cov.values, cov.values.T, atol=1e-10)

    def test_positive_semidefinite(self, random_returns):
        cov = denoise_covariance(random_returns, detone=False)
        eigenvalues = np.linalg.eigvalsh(cov.values)
        assert (eigenvalues >= -1e-8).all()

    def test_lower_condition_number(self, random_returns):
        """Denoised matrix should have lower condition number than raw."""
        cov_raw = random_returns.cov()
        cov_dn = denoise_covariance(random_returns, detone=False)

        evals_raw = np.linalg.eigvalsh(cov_raw.values)
        evals_dn = np.linalg.eigvalsh(cov_dn.values)

        cond_raw = evals_raw[-1] / max(evals_raw[0], 1e-10)
        evals_dn_pos = evals_dn[evals_dn > 0]
        cond_dn = evals_dn_pos[-1] / max(evals_dn_pos[0], 1e-10)

        assert cond_dn <= cond_raw * 1.01  # Allow tiny float error

    def test_detone_removes_market(self, random_returns):
        """Detoned matrix should have smaller first eigenvalue."""
        cov_no_detone = denoise_covariance(random_returns, detone=False)
        cov_detoned = denoise_covariance(random_returns, detone=True)

        eval_no = np.sort(np.linalg.eigvalsh(cov_no_detone.values))[-1]
        eval_dt = np.sort(np.linalg.eigvalsh(cov_detoned.values))[-1]
        assert eval_dt < eval_no

    def test_fallback_when_T_less_than_N(self, small_returns):
        """Should fall back to Ledoit-Wolf when T < N."""
        cov = denoise_covariance(small_returns)
        assert cov.shape == (50, 50)
        # Should still be valid
        assert not np.isnan(cov.values).any()


class TestEstimateCovariance:
    def test_denoised_method(self, random_returns):
        cov = estimate_covariance(random_returns, method="denoised")
        assert cov.shape == (20, 20)

    def test_ledoit_wolf_method(self, random_returns):
        cov = estimate_covariance(random_returns, method="ledoit_wolf")
        assert cov.shape == (20, 20)

    def test_empirical_method(self, random_returns):
        cov = estimate_covariance(random_returns, method="empirical")
        assert cov.shape == (20, 20)
        # Empirical should match pandas .cov()
        np.testing.assert_allclose(cov.values, random_returns.cov().values, atol=1e-10)


class TestDiagnostics:
    def test_diagnostics_output(self, random_returns):
        diag = covariance_diagnostics(random_returns)
        assert "dimensions" in diag
        assert "marchenko_pastur_bound" in diag
        assert "signal_eigenvalues" in diag
        assert "condition_number" in diag
        assert diag["dimensions"]["T"] == 504
        assert diag["dimensions"]["N"] == 20
        assert diag["signal_eigenvalues"] > 0
        assert diag["condition_number"]["improvement"] >= 1.0

    def test_diagnostics_mp_bound_uses_fitted_variance(self, random_returns):
        """Regression: diagnostics MP bound must use fitted noise variance,
        not default var=1.0, to be consistent with denoise_covariance."""
        diag = covariance_diagnostics(random_returns)
        T, N = random_returns.shape
        q = T / N
        # The MP bound in diagnostics should NOT equal the default var=1.0 bound
        default_bound = marchenko_pastur_bound(T, N, var=1.0)
        # The diagnostics bound should use the fitted variance
        actual_bound = diag["marchenko_pastur_bound"]
        # They should differ (fitted variance != 1.0 for our synthetic data)
        # Our synthetic data has noise variance << 1.0 (factors are large, noise is small)
        assert actual_bound != pytest.approx(default_bound, rel=0.01)

    def test_diagnostics_uses_correlation_eigenvalues(self, random_returns):
        """Regression (cycle 72): diagnostics must analyze eigenvalues of the
        correlation matrix, not the covariance matrix. Marchenko-Pastur theory
        applies to standardized (correlation) matrices with trace=N.

        Using covariance eigenvalues produces wrong signal/noise classification
        because the eigenvalue scale depends on asset volatilities."""
        diag = covariance_diagnostics(random_returns)
        T, N = random_returns.shape

        # Our synthetic data has 3 factors. The diagnostics should find at least
        # 2 signal eigenvalues using correlation eigenvalues. With covariance
        # eigenvalues, only 1 is found because the scale is wrong.
        assert diag["signal_eigenvalues"] >= 2, (
            f"Only {diag['signal_eigenvalues']} signal eigenvalue(s) found — "
            f"the synthetic data has 3 factors, so the diagnostics is likely "
            f"analyzing covariance eigenvalues instead of correlation eigenvalues"
        )

        # The top eigenvalues should sum to approximately N (=20) for a
        # correlation matrix, not to the trace of the covariance matrix.
        top_5 = diag["top_5_eigenvalues"]["raw"]
        assert top_5[0] > 3.0, (
            f"Largest eigenvalue {top_5[0]} is too small — suggests covariance "
            f"eigenvalues (scale ~0.01-3.5) instead of correlation eigenvalues "
            f"(scale ~4-10)"
        )
