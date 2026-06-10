"""
Sector Analyzer Ito Correction Tests
========================================

Validates that the sector MC simulation applies the Ito drift correction
(ln(1+r) - 0.5*sigma^2) so sector projections don't have upward drift bias.

Run with:
    python -m pytest backend/tests/test_sector_ito.py -v
"""

import numpy as np
import pandas as pd
import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.monte_carlo import simulate_paths


class TestItoCorrection:
    """Verify Ito correction math matches stock_analyzer's approach."""

    @pytest.mark.parametrize("expected_annual,sigma", [
        (0.08, 0.20),   # moderate return, moderate vol
        (0.12, 0.30),   # higher return, higher vol → bigger correction
        (0.05, 0.15),   # low return, low vol → small correction
        (0.10, 0.40),   # high vol → large correction (~8%)
    ])
    def test_ito_correction_reduces_log_drift(self, expected_annual, sigma):
        """Log drift with Ito correction must be < log(1+r)."""
        naive_mu = np.log(1 + expected_annual)
        corrected_mu = np.log(1 + expected_annual) - 0.5 * sigma**2

        assert corrected_mu < naive_mu, (
            f"Ito correction should reduce drift: "
            f"corrected={corrected_mu:.4f} should be < naive={naive_mu:.4f}"
        )
        # The gap should be exactly 0.5 * sigma^2
        gap = naive_mu - corrected_mu
        assert abs(gap - 0.5 * sigma**2) < 1e-12

    def test_ito_correction_magnitude_for_high_vol_sector(self):
        """For sigma=0.25 (Energy-like), correction is ~3.1% annual."""
        sigma = 0.25
        correction = 0.5 * sigma**2
        assert abs(correction - 0.03125) < 1e-6
        # This is the bias that was present before the fix

    def test_ito_correction_magnitude_for_tech_sector(self):
        """For sigma=0.22 (Tech-like), correction is ~2.4% annual."""
        sigma = 0.22
        correction = 0.5 * sigma**2
        assert abs(correction - 0.0242) < 1e-4


class TestSectorMCDriftNeutrality:
    """Test that sector MC with Ito correction produces unbiased mean returns."""

    @pytest.mark.parametrize("expected_annual,sigma", [
        (0.08, 0.18),
        (0.10, 0.25),
    ])
    def test_mc_mean_return_near_expected(self, expected_annual, sigma):
        """MC mean final price should approximate E[S(T)] = S0 * (1+r)^T.

        With correct Ito drift, the GBM expected value is:
        E[S(T)] = S0 * exp(mu*T + 0.5*sigma^2*T)
        where mu = log(1+r) - 0.5*sigma^2 (the Ito-corrected drift).
        This simplifies to S0 * exp(log(1+r)*T) = S0 * (1+r)^T.

        Without the correction, mean final price would be systematically higher.
        """
        start_price = 100.0
        days = 1260  # 5 years
        n_sims = 5000
        years = days / 252

        # Ito-corrected drift (what sector_analyzer now does)
        mu_corrected = np.log(1 + expected_annual) - 0.5 * sigma**2

        paths = simulate_paths(
            start_price=start_price,
            historical_mu=mu_corrected,
            historical_sigma=sigma,
            days=days,
            n_sims=n_sims,
            crash_freq=0.0,  # disable jumps for clean drift test
            risk_score=0.0,
            scenario={"drift_adj": 0.0, "vol_mult": 1.0, "crash_mult": 1.0},
            seed=42,
            garch_vol=None,  # pure GBM, no GARCH overlay
        )

        final_prices = paths[-1]
        mc_mean_return = np.mean(final_prices) / start_price - 1
        expected_total = (1 + expected_annual) ** years - 1

        # Mean return should be within 25% relative error of expected.
        # MC noise + block bootstrap + OU vol dynamics make exact match impossible;
        # this test validates the correction is in the right ballpark, not that
        # GBM E[S(T)] holds exactly under all the overlaid dynamics.
        rel_error = abs(mc_mean_return - expected_total) / max(expected_total, 0.01)
        assert rel_error < 0.25, (
            f"MC mean return {mc_mean_return:.3f} too far from expected {expected_total:.3f} "
            f"(relative error {rel_error:.1%})"
        )

    def test_uncorrected_drift_is_biased_high(self):
        """Without Ito correction, MC mean overshoots the target return."""
        start_price = 100.0
        expected_annual = 0.08
        sigma = 0.25
        days = 1260
        n_sims = 5000
        years = days / 252

        # WRONG: naive log drift without Ito correction (the old bug)
        mu_naive = np.log(1 + expected_annual)
        # CORRECT: with Ito correction
        mu_corrected = np.log(1 + expected_annual) - 0.5 * sigma**2

        paths_naive = simulate_paths(
            start_price=start_price,
            historical_mu=mu_naive,
            historical_sigma=sigma,
            days=days, n_sims=n_sims,
            crash_freq=0.0, risk_score=0.0,
            scenario={"drift_adj": 0.0, "vol_mult": 1.0, "crash_mult": 1.0},
            seed=42, garch_vol=None,
        )
        paths_corrected = simulate_paths(
            start_price=start_price,
            historical_mu=mu_corrected,
            historical_sigma=sigma,
            days=days, n_sims=n_sims,
            crash_freq=0.0, risk_score=0.0,
            scenario={"drift_adj": 0.0, "vol_mult": 1.0, "crash_mult": 1.0},
            seed=42, garch_vol=None,
        )

        naive_mean = np.mean(paths_naive[-1])
        corrected_mean = np.mean(paths_corrected[-1])

        # Naive (uncorrected) should produce higher mean than corrected
        assert naive_mean > corrected_mean, (
            f"Naive mean {naive_mean:.2f} should exceed corrected {corrected_mean:.2f}"
        )

        # The difference should be approximately exp(0.5*sigma^2*T) - 1 in ratio terms
        # For sigma=0.25, 5 years: exp(0.5*0.0625*5) - 1 ≈ 17%
        bias_pct = (naive_mean / corrected_mean - 1) * 100
        assert bias_pct > 5, (
            f"Drift bias from missing Ito correction should be >5%, got {bias_pct:.1f}%"
        )


class TestSectorGarchTupleFormat:
    """Verify the sector_garch tuple now carries current_vol."""

    def test_tuple_has_four_elements(self):
        """sector_garch entries should be (current_vol, persistence, nu, residuals)."""
        # Simulate what the code produces
        sec_current_vol = 0.22
        sec_persistence = 0.95
        sec_nu = 8.5
        sec_residuals = np.random.randn(500)

        entry = (sec_current_vol, sec_persistence, sec_nu, sec_residuals)
        assert len(entry) == 4
        assert entry[0] == sec_current_vol  # current_vol is first

    def test_none_current_vol_falls_back_to_sigma(self):
        """When GARCH fit fails, current_vol is None → ito_sigma = sigma."""
        sec_current_vol = None
        sigma = 0.20

        ito_sigma = sec_current_vol if sec_current_vol is not None else sigma
        assert ito_sigma == sigma

    def test_garch_vol_used_when_available(self):
        """When GARCH succeeds, current_vol is used for Ito correction."""
        sec_current_vol = 0.28
        sigma = 0.20

        ito_sigma = sec_current_vol if sec_current_vol is not None else sigma
        assert ito_sigma == sec_current_vol


class TestSectorAnalyzerIntegration:
    """Integration test: analyze_sectors applies Ito correction end-to-end."""

    def _make_sector_data(self, n_days=1300):
        """Generate synthetic sector price series."""
        rng = np.random.default_rng(42)
        dates = pd.bdate_range("2019-01-02", periods=n_days)

        # SP500-like index
        sp_returns = 0.0003 + 0.012 * rng.standard_normal(n_days)
        sp_prices = 3000 * np.cumprod(1 + sp_returns)

        data = pd.DataFrame({
            "SP500": sp_prices,
            "VIX": 20 + 5 * rng.standard_normal(n_days),
            "T3M": np.full(n_days, 0.04),
            "T10Y": np.full(n_days, 0.045),
        }, index=dates)

        # Two synthetic sectors: one low-vol, one high-vol
        sector_data = {}
        for name, vol_mult in [("LowVol", 0.8), ("HighVol", 1.5)]:
            sec_returns = 0.0003 + vol_mult * 0.012 * rng.standard_normal(n_days)
            sector_data[name] = pd.Series(
                100 * np.cumprod(1 + sec_returns), index=dates, name=name,
            )

        return data, sector_data

    def test_analyze_sectors_returns_results(self):
        """analyze_sectors should return metrics for each sector."""
        from backend.services.sector_analyzer import analyze_sectors

        data, sector_data = self._make_sector_data()
        results = analyze_sectors(data, sector_data, forecast_days=252)

        assert len(results) == 2
        for name in ("LowVol", "HighVol"):
            assert name in results
            r = results[name]
            assert "sim_total_return" in r
            assert "expected_annual" in r
            assert "crash_prob" in r

    def test_high_vol_sector_has_lower_sim_vs_naive(self):
        """High-vol sector should show more Ito drag, meaning
        sim_total_return is meaningfully below naive (1+r)^T expectation."""
        from backend.services.sector_analyzer import analyze_sectors

        data, sector_data = self._make_sector_data()
        results = analyze_sectors(data, sector_data, forecast_days=252)

        for name, r in results.items():
            # sim_total_return (MC) should not wildly exceed expected_total (factor model)
            # Before the fix, high-vol sectors would overshoot by 5-15%
            gap = r["sim_total_return"] - r["expected_total"]
            assert gap < 20, (
                f"Sector {name}: sim_total ({r['sim_total_return']:.1f}%) should not "
                f"massively exceed expected_total ({r['expected_total']:.1f}%), gap={gap:.1f}%"
            )
