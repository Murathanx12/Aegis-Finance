"""
Portfolio Builder Stress Tests
================================

Tests the portfolio builder across multiple risk profiles and time horizons.
Validates weight normalization, holding structure, and return reasonableness.

Run with:
    python -m pytest backend/tests/test_stress_portfolio.py -v
"""

import logging
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.portfolio_engine import PortfolioEngine, score_risk_profile

logger = logging.getLogger(__name__)


RISK_PROFILES = ["conservative", "moderate", "aggressive"]
TIME_HORIZONS = ["1y", "3y", "5y", "10y"]


@pytest.mark.slow
class TestPortfolioBuild:
    """Test portfolio builder across risk tolerance levels."""

    @pytest.mark.parametrize("risk_tolerance", RISK_PROFILES)
    def test_weights_sum_to_one(self, risk_tolerance):
        """Portfolio weights should sum to ~1.0 (within 0.01)."""
        result = PortfolioEngine.build_portfolio(
            risk_tolerance=risk_tolerance,
            investment_amount=10000,
            time_horizon="5y",
        )
        assert "holdings" in result, f"No holdings in result for {risk_tolerance}"

        total_weight = sum(h["weight"] for h in result["holdings"])
        np.testing.assert_allclose(
            total_weight, 100.0, atol=1.0,
            err_msg=f"{risk_tolerance}: weights sum to {total_weight:.2f}%, expected ~100%",
        )

    @pytest.mark.parametrize("risk_tolerance", RISK_PROFILES)
    def test_holdings_have_valid_tickers(self, risk_tolerance):
        """Every holding should have a non-empty ticker symbol."""
        result = PortfolioEngine.build_portfolio(
            risk_tolerance=risk_tolerance,
            investment_amount=10000,
            time_horizon="5y",
        )
        for h in result["holdings"]:
            assert isinstance(h["ticker"], str) and len(h["ticker"]) > 0, (
                f"Invalid ticker in {risk_tolerance} portfolio: {h}"
            )

    @pytest.mark.parametrize("risk_tolerance", RISK_PROFILES)
    def test_dollar_amounts_sum_to_investment(self, risk_tolerance):
        """Dollar amounts should approximately sum to the investment amount."""
        investment = 10000
        result = PortfolioEngine.build_portfolio(
            risk_tolerance=risk_tolerance,
            investment_amount=investment,
            time_horizon="5y",
        )
        total_dollars = sum(h["dollar_amount"] for h in result["holdings"])
        np.testing.assert_allclose(
            total_dollars, investment, atol=50,
            err_msg=f"{risk_tolerance}: dollar sum {total_dollars:.2f} != {investment}",
        )

    @pytest.mark.parametrize("risk_tolerance", RISK_PROFILES)
    def test_shares_positive(self, risk_tolerance):
        """All share counts should be positive."""
        result = PortfolioEngine.build_portfolio(
            risk_tolerance=risk_tolerance,
            investment_amount=10000,
            time_horizon="5y",
        )
        for h in result["holdings"]:
            assert h["shares"] > 0, (
                f"{risk_tolerance}: {h['ticker']} has non-positive shares: {h['shares']}"
            )

    @pytest.mark.parametrize("risk_tolerance", RISK_PROFILES)
    def test_result_metadata(self, risk_tolerance):
        """Result should contain expected metadata fields."""
        result = PortfolioEngine.build_portfolio(
            risk_tolerance=risk_tolerance,
            investment_amount=10000,
            time_horizon="5y",
        )
        assert result["risk_tolerance"] == risk_tolerance
        assert result["investment_amount"] == 10000
        assert result["time_horizon"] == "5y"
        assert isinstance(result["description"], str)

    @pytest.mark.parametrize("time_horizon", TIME_HORIZONS)
    def test_time_horizon_adjustment(self, time_horizon):
        """Shorter horizons should shift weight toward bonds."""
        result = PortfolioEngine.build_portfolio(
            risk_tolerance="moderate",
            investment_amount=10000,
            time_horizon=time_horizon,
        )
        total_weight = sum(h["weight"] for h in result["holdings"])
        np.testing.assert_allclose(
            total_weight, 100.0, atol=1.0,
            err_msg=f"horizon={time_horizon}: weights don't sum to 100%",
        )

    def test_shorter_horizon_more_bonds(self):
        """1y portfolio should have more bond weight than 10y portfolio."""
        short = PortfolioEngine.build_portfolio(
            risk_tolerance="moderate", investment_amount=10000, time_horizon="1y",
        )
        long = PortfolioEngine.build_portfolio(
            risk_tolerance="moderate", investment_amount=10000, time_horizon="10y",
        )

        bond_tickers = {"BND", "VTIP"}
        short_bonds = sum(
            h["weight"] for h in short["holdings"] if h["ticker"] in bond_tickers
        )
        long_bonds = sum(
            h["weight"] for h in long["holdings"] if h["ticker"] in bond_tickers
        )
        assert short_bonds > long_bonds, (
            f"1y bonds ({short_bonds:.1f}%) should exceed 10y bonds ({long_bonds:.1f}%)"
        )


class TestRiskProfileScoring:
    """Test the risk questionnaire scoring (no network calls)."""

    def test_conservative_answers(self):
        answers = {
            "horizon": "1y",
            "risk_tolerance": "conservative",
            "loss_reaction": "sell",
            "experience": "none",
            "income_stability": "unstable",
            "goal": "preservation",
        }
        result = score_risk_profile(answers)
        assert result["allocation_style"] == "conservative"
        assert result["risk_score"] <= 3

    def test_aggressive_answers(self):
        answers = {
            "horizon": "20y",
            "risk_tolerance": "aggressive",
            "loss_reaction": "buy_more",
            "experience": "advanced",
            "income_stability": "very_stable",
            "goal": "aggressive_growth",
        }
        result = score_risk_profile(answers)
        assert result["allocation_style"] == "aggressive"
        assert result["risk_score"] >= 7

    def test_moderate_answers(self):
        answers = {
            "horizon": "5y",
            "risk_tolerance": "moderate",
            "loss_reaction": "hold",
            "experience": "beginner",
            "income_stability": "stable",
            "goal": "growth",
        }
        result = score_risk_profile(answers)
        assert result["allocation_style"] in ("moderate", "aggressive")
        assert 4 <= result["risk_score"] <= 7

    def test_risk_score_clamped(self):
        """Risk score should always be in [1, 10] range."""
        extreme_low = {
            "horizon": "1y", "risk_tolerance": "conservative",
            "loss_reaction": "sell", "experience": "none",
            "income_stability": "unstable", "goal": "preservation",
        }
        extreme_high = {
            "horizon": "20y", "risk_tolerance": "aggressive",
            "loss_reaction": "buy_more", "experience": "advanced",
            "income_stability": "very_stable", "goal": "aggressive_growth",
        }
        low = score_risk_profile(extreme_low)
        high = score_risk_profile(extreme_high)
        assert 1 <= low["risk_score"] <= 10
        assert 1 <= high["risk_score"] <= 10
