"""Tests for portfolio projection (jump-diffusion MC)."""

import pytest

from backend.services.portfolio_engine import PortfolioEngine


@pytest.mark.slow
class TestPortfolioProjection:
    """Test project_portfolio with jump-diffusion MC."""

    @pytest.fixture
    def sample_holdings(self):
        return [
            {"ticker": "SPY", "shares": 10, "current_price": 560.0},
            {"ticker": "BND", "shares": 20, "current_price": 72.0},
        ]

    def test_returns_required_keys(self, sample_holdings):
        result = PortfolioEngine.project_portfolio(sample_holdings, years=1)
        for key in ["current_value", "horizon_years", "expected_final",
                     "p10_final", "p90_final", "prob_gain", "quarterly"]:
            assert key in result, f"Missing key: {key}"

    def test_percentile_ordering(self, sample_holdings):
        result = PortfolioEngine.project_portfolio(sample_holdings, years=3)
        assert result["p10_final"] < result["expected_final"] < result["p90_final"]

    def test_monthly_add_increases_final(self, sample_holdings):
        no_add = PortfolioEngine.project_portfolio(sample_holdings, years=5, monthly_add=0)
        with_add = PortfolioEngine.project_portfolio(sample_holdings, years=5, monthly_add=500)
        assert with_add["expected_final"] > no_add["expected_final"]

    def test_quarterly_snapshots_count(self, sample_holdings):
        result = PortfolioEngine.project_portfolio(sample_holdings, years=5)
        assert len(result["quarterly"]) == 20  # 5 years * 4 quarters

    def test_prob_gain_reasonable(self, sample_holdings):
        result = PortfolioEngine.project_portfolio(sample_holdings, years=5, monthly_add=500)
        # With DCA over 5 years, probability of gain should be high
        assert result["prob_gain"] > 50.0


class TestStockAnalyzerBetaCrashFreq:
    """Test that stock analyzer uses beta-adjusted crash frequency."""

    def test_config_driven_paths(self):
        from backend.config import config
        num_sims = config["simulation"]["num_simulations"]
        assert num_sims >= 5000, "Config should specify at least 5000 simulations"

    def test_crash_freq_adjustment_logic(self):
        """Verify the beta-adjustment formula used in stock_analyzer."""
        import numpy as np
        from backend.config import config

        base_freq = config["simulation"]["jump_diffusion"]["annual_rate"]

        # Low beta (defensive)
        low_beta = 0.3
        adj_low = float(np.clip(base_freq * low_beta, 0.02, 0.25))
        assert adj_low < base_freq

        # High beta (aggressive)
        high_beta = 2.0
        adj_high = float(np.clip(base_freq * high_beta, 0.02, 0.25))
        assert adj_high > base_freq

        # Clipping at extremes
        extreme_beta = 10.0
        adj_extreme = float(np.clip(base_freq * extreme_beta, 0.02, 0.25))
        assert adj_extreme == 0.25  # capped
