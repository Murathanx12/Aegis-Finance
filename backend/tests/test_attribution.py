"""Tests for Brinson-Fachler attribution and risk contributions."""

import numpy as np
import pytest

from backend.services.attribution import (
    brinson_fachler_attribution,
    _group_by_sector,
)


class TestBrinsonFachler:
    """Test Brinson-Fachler performance attribution."""

    def test_basic_attribution(self):
        """Simple 2-sector example with known values."""
        portfolio_w = {"AAPL": 0.4, "XOM": 0.3, "JPM": 0.3}
        benchmark_w = {"AAPL": 0.33, "XOM": 0.33, "JPM": 0.34}
        portfolio_r = {"AAPL": 0.10, "XOM": -0.05, "JPM": 0.03}
        benchmark_r = {"AAPL": 0.08, "XOM": -0.03, "JPM": 0.02}
        sector_map = {"AAPL": "Tech", "XOM": "Energy", "JPM": "Financials"}

        result = brinson_fachler_attribution(
            portfolio_w, benchmark_w, portfolio_r, benchmark_r, sector_map
        )

        assert "attribution" in result
        assert "sector_detail" in result
        assert result["n_sectors"] == 3

        # Active return = portfolio return - benchmark return
        port_ret = 0.4 * 0.10 + 0.3 * (-0.05) + 0.3 * 0.03
        bench_ret = 0.33 * 0.08 + 0.33 * (-0.03) + 0.34 * 0.02
        expected_active = port_ret - bench_ret
        assert abs(result["active_return"] - expected_active * 100) < 0.1

        # Attribution components should approximately sum to active return
        attr = result["attribution"]
        total_attr = attr["allocation"] + attr["selection"] + attr["interaction"]
        assert abs(total_attr - result["active_return"]) < 0.5

    def test_identical_portfolios(self):
        """Same portfolio and benchmark → zero active return."""
        weights = {"AAPL": 0.5, "MSFT": 0.5}
        returns = {"AAPL": 0.05, "MSFT": 0.03}

        result = brinson_fachler_attribution(
            weights, weights, returns, returns
        )

        assert abs(result["active_return"]) < 0.01
        assert abs(result["attribution"]["allocation"]) < 0.01
        assert abs(result["attribution"]["selection"]) < 0.01

    def test_allocation_effect_positive(self):
        """Overweighting an outperforming sector should produce positive allocation."""
        # Portfolio overweights Tech (80% vs 50%), Tech outperforms
        portfolio_w = {"AAPL": 0.8, "XOM": 0.2}
        benchmark_w = {"AAPL": 0.5, "XOM": 0.5}
        # Both portfolios hold same stocks with same returns
        # but portfolio overweights the better one
        returns = {"AAPL": 0.10, "XOM": -0.05}
        sector_map = {"AAPL": "Tech", "XOM": "Energy"}

        result = brinson_fachler_attribution(
            portfolio_w, benchmark_w, returns, returns, sector_map
        )

        # Overweighting Tech (which outperformed) → positive allocation
        assert result["attribution"]["allocation"] > 0

    def test_selection_effect(self):
        """Better stock picking within sectors."""
        portfolio_w = {"AAPL": 0.5, "XOM": 0.5}
        benchmark_w = {"AAPL": 0.5, "XOM": 0.5}
        # Same weights, but portfolio stocks did better
        portfolio_r = {"AAPL": 0.12, "XOM": 0.05}
        benchmark_r = {"AAPL": 0.08, "XOM": 0.01}
        sector_map = {"AAPL": "Tech", "XOM": "Energy"}

        result = brinson_fachler_attribution(
            portfolio_w, benchmark_w, portfolio_r, benchmark_r, sector_map
        )

        # Same allocation, better selection → selection effect positive
        assert result["attribution"]["selection"] > 0
        assert abs(result["attribution"]["allocation"]) < 0.5  # ~0 allocation effect

    def test_empty_portfolio(self):
        """Edge case: empty portfolio."""
        result = brinson_fachler_attribution({}, {"AAPL": 1.0}, {}, {"AAPL": 0.05})
        assert result["total_portfolio_return"] == 0.0

    def test_has_interpretation(self):
        """Result should include human-readable interpretation."""
        portfolio_w = {"AAPL": 0.6, "XOM": 0.4}
        benchmark_w = {"AAPL": 0.5, "XOM": 0.5}
        returns = {"AAPL": 0.10, "XOM": -0.05}

        result = brinson_fachler_attribution(
            portfolio_w, benchmark_w, returns, returns
        )

        assert "interpretation" in result
        assert len(result["interpretation"]) > 20


class TestGroupBySector:
    def test_basic_grouping(self):
        weights = {"AAPL": 0.3, "MSFT": 0.2, "XOM": 0.5}
        returns = {"AAPL": 0.10, "MSFT": 0.08, "XOM": -0.05}
        sector_map = {"AAPL": "Tech", "MSFT": "Tech", "XOM": "Energy"}

        result = _group_by_sector(weights, returns, sector_map)

        assert "Tech" in result
        assert "Energy" in result
        assert abs(result["Tech"]["weight"] - 0.5) < 0.01
        assert abs(result["Energy"]["weight"] - 0.5) < 0.01
        # Tech return = (0.3*0.10 + 0.2*0.08) / 0.5 = 0.092
        assert abs(result["Tech"]["return"] - 0.092) < 0.001

    def test_unknown_sector(self):
        """Tickers not in sector_map go to 'Other'."""
        weights = {"ABC": 1.0}
        returns = {"ABC": 0.05}
        sector_map = {}

        result = _group_by_sector(weights, returns, sector_map)
        assert "Other" in result
