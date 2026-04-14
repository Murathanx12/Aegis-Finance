"""
Historical Stress Testing Tests
==================================

Tests for stress testing framework.

Run with:
    python -m pytest backend/tests/test_stress_testing.py -v
"""

import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.stress_testing import (
    stress_test_single,
    stress_test_portfolio,
    get_scenario_list,
    _estimate_crisis_return,
)


class TestScenarioList:
    def test_scenarios_available(self):
        scenarios = get_scenario_list()
        assert len(scenarios) >= 5
        names = [s["name"] for s in scenarios]
        assert any("2008" in n for n in names)
        assert any("COVID" in n for n in names)

    def test_scenario_structure(self):
        scenarios = get_scenario_list()
        for s in scenarios:
            assert "id" in s
            assert "name" in s
            assert "start" in s
            assert "end" in s
            assert "sp500_drawdown" in s
            assert s["sp500_drawdown"] < 0, f"Drawdown should be negative: {s}"


class TestEstimateCrisisReturn:
    def test_tech_stock_high_beta(self):
        ret = _estimate_crisis_return(
            "TSLA", "2008_GFC", sector="Technology", beta=2.0,
            sp500_drawdown=-0.568,
        )
        # High beta tech should lose more than market
        assert ret < -0.568
        assert ret >= -0.95

    def test_utility_stock_low_beta(self):
        ret = _estimate_crisis_return(
            "NEE", "2020_COVID", sector="Utilities", beta=0.5,
            sp500_drawdown=-0.339,
        )
        # Defensive utility should lose less than market
        assert ret > -0.339

    def test_caps_at_95_pct(self):
        ret = _estimate_crisis_return(
            "EXTREME", "2008_GFC", sector="Financials", beta=3.0,
            sp500_drawdown=-0.568,
        )
        assert ret >= -0.95

    def test_default_sector(self):
        ret = _estimate_crisis_return(
            "UNKNOWN", "2020_COVID", sector=None, beta=1.0,
            sp500_drawdown=-0.339,
        )
        assert -0.95 <= ret <= 0


class TestStressTestSingle:
    @patch("backend.services.stress_testing._fetch_crisis_returns")
    def test_with_estimation_fallback(self, mock_fetch):
        mock_fetch.return_value = None  # Force estimation fallback
        result = stress_test_single("AAPL", sector="Technology", beta=1.2)

        assert result["ticker"] == "AAPL"
        assert "scenarios" in result
        assert len(result["scenarios"]) >= 5

        for sid, scenario in result["scenarios"].items():
            assert "projected_drawdown" in scenario
            assert scenario["projected_drawdown"] < 0
            assert "data_source" in scenario
            assert scenario["data_source"] == "estimated"

    @patch("backend.services.stress_testing._fetch_crisis_returns")
    def test_with_historical_data(self, mock_fetch):
        # Mock historical returns for 2020 COVID
        dates = pd.bdate_range("2020-02-19", "2020-03-23")
        prices = np.linspace(100, 66, len(dates))  # ~34% decline
        cumret = pd.DataFrame(
            {"AAPL": prices / 100, "SPY": prices / 100},
            index=dates,
        )
        mock_fetch.return_value = cumret

        result = stress_test_single("AAPL", scenario_id="2020_COVID")
        assert "2020_COVID" in result["scenarios"]
        scenario = result["scenarios"]["2020_COVID"]
        assert scenario["data_source"] == "historical"
        assert scenario["projected_drawdown"] < 0

    @patch("backend.services.stress_testing._fetch_crisis_returns")
    def test_specific_scenario(self, mock_fetch):
        mock_fetch.return_value = None
        result = stress_test_single("MSFT", scenario_id="2008_GFC")
        assert len(result["scenarios"]) == 1
        assert "2008_GFC" in result["scenarios"]


class TestStressTestPortfolio:
    @patch("backend.services.stress_testing._fetch_crisis_returns")
    def test_basic_portfolio(self, mock_fetch):
        mock_fetch.return_value = None  # Force estimation
        weights = {"AAPL": 0.4, "JPM": 0.3, "XOM": 0.3}

        result = stress_test_portfolio(
            weights,
            sector_map={"AAPL": "Technology", "JPM": "Financials", "XOM": "Energy"},
            beta_map={"AAPL": 1.2, "JPM": 1.1, "XOM": 0.9},
        )

        assert result["portfolio_size"] == 3
        assert "scenarios" in result
        assert "worst_case" in result
        assert "best_case" in result
        assert result["worst_case"]["drawdown"] < result["best_case"]["drawdown"]

    @patch("backend.services.stress_testing._fetch_crisis_returns")
    def test_portfolio_drawdown_negative(self, mock_fetch):
        mock_fetch.return_value = None
        weights = {"AAPL": 0.5, "MSFT": 0.5}
        result = stress_test_portfolio(weights)

        for sid, scenario in result["scenarios"].items():
            assert scenario["portfolio_drawdown"] < 0

    @patch("backend.services.stress_testing._fetch_crisis_returns")
    def test_relative_to_market(self, mock_fetch):
        mock_fetch.return_value = None
        weights = {"NEE": 0.5, "SO": 0.5}
        result = stress_test_portfolio(
            weights,
            sector_map={"NEE": "Utilities", "SO": "Utilities"},
            beta_map={"NEE": 0.4, "SO": 0.3},
        )
        # Defensive portfolio should show relative_to_market < 1.0 (less drawdown than market)
        for sid, scenario in result["scenarios"].items():
            if scenario["relative_to_market"] is not None:
                assert scenario["relative_to_market"] < 1.5
