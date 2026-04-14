"""
Fama-French 5-Factor Model Tests
===================================

Tests for factor decomposition service.

Run with:
    python -m pytest backend/tests/test_factor_model.py -v
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.factor_model import (
    decompose_stock,
    decompose_portfolio,
    _interpret_style,
    get_factor_data,
)


# ── Mock data generators ──────────────────────────────────────────


def _make_mock_factor_data(n_days: int = 500) -> pd.DataFrame:
    """Create realistic mock Fama-French factor data."""
    rng = np.random.default_rng(42)
    dates = pd.bdate_range(end="2026-03-31", periods=n_days)
    return pd.DataFrame({
        "Mkt-RF": rng.normal(0.0004, 0.01, n_days),
        "SMB": rng.normal(0.0001, 0.005, n_days),
        "HML": rng.normal(0.0001, 0.004, n_days),
        "RMW": rng.normal(0.0001, 0.003, n_days),
        "CMA": rng.normal(0.0001, 0.003, n_days),
        "RF": np.full(n_days, 0.0002),
    }, index=dates)


def _make_mock_price_series(
    n_days: int = 500,
    beta: float = 1.0,
    alpha_daily: float = 0.0,
) -> pd.Series:
    """Create a mock price series with known factor exposures."""
    rng = np.random.default_rng(42)
    dates = pd.bdate_range(end="2026-03-31", periods=n_days)
    returns = alpha_daily + beta * rng.normal(0.0004, 0.01, n_days) + rng.normal(0, 0.005, n_days)
    prices = 100.0 * np.cumprod(1 + returns)
    return pd.Series(prices, index=dates, name="Close")


# ── Style interpretation ──────────────────────────────────────────


class TestInterpretStyle:
    def test_aggressive_growth(self):
        style = _interpret_style({"Mkt-RF": 1.5, "SMB": 0.3, "HML": -0.4, "RMW": -0.2, "CMA": -0.3})
        assert style["market"] == "aggressive"
        assert style["value"] == "growth"
        assert style["size"] == "small-cap tilt"

    def test_defensive_value(self):
        style = _interpret_style({"Mkt-RF": 0.6, "SMB": -0.3, "HML": 0.5, "RMW": 0.3, "CMA": 0.2})
        assert style["market"] == "defensive"
        assert style["value"] == "value"
        assert style["size"] == "large-cap tilt"

    def test_neutral(self):
        style = _interpret_style({"Mkt-RF": 1.0, "SMB": 0.0, "HML": 0.0, "RMW": 0.0, "CMA": 0.0})
        assert style["market"] == "neutral"
        assert style["value"] == "blend"
        assert style["size"] == "neutral"


# ── Factor decomposition ─────────────────────────────────────────


class TestDecomposeStock:
    @patch("backend.services.factor_model.get_factor_data")
    def test_basic_decomposition(self, mock_factors):
        mock_factors.return_value = _make_mock_factor_data(400)
        prices = _make_mock_price_series(400, beta=1.2)

        result = decompose_stock("TEST", price_series=prices, lookback_days=350)

        assert result is not None
        assert result["ticker"] == "TEST"
        assert "r_squared" in result
        assert 0 <= result["r_squared"] <= 1.0
        assert "alpha_annual" in result
        assert "factors" in result
        assert len(result["factors"]) == 5
        for f in ["Mkt-RF", "SMB", "HML", "RMW", "CMA"]:
            assert f in result["factors"]
            assert "loading" in result["factors"][f]
            assert "t_stat" in result["factors"][f]
            assert "p_value" in result["factors"][f]

    @patch("backend.services.factor_model.get_factor_data")
    def test_high_beta_stock(self, mock_factors):
        mock_factors.return_value = _make_mock_factor_data(400)
        prices = _make_mock_price_series(400, beta=1.8)

        result = decompose_stock("HIGHBETA", price_series=prices, lookback_days=350)

        assert result is not None
        # Market beta should be positive and elevated
        assert result["factors"]["Mkt-RF"]["loading"] > 0.5

    @patch("backend.services.factor_model.get_factor_data")
    def test_insufficient_data(self, mock_factors):
        mock_factors.return_value = _make_mock_factor_data(50)
        prices = _make_mock_price_series(50)

        result = decompose_stock("SHORT", price_series=prices, lookback_days=200)
        # Should return None with insufficient overlapping data
        assert result is None

    @patch("backend.services.factor_model.get_factor_data")
    def test_style_present(self, mock_factors):
        mock_factors.return_value = _make_mock_factor_data(400)
        prices = _make_mock_price_series(400, beta=1.0)

        result = decompose_stock("STYLE", price_series=prices, lookback_days=350)
        assert result is not None
        assert "style" in result
        assert "market" in result["style"]
        assert "value" in result["style"]

    def test_no_factor_data(self):
        with patch("backend.services.factor_model.get_factor_data", return_value=None):
            result = decompose_stock("TEST", price_series=_make_mock_price_series(300))
            assert result is None

    @patch("backend.services.factor_model.get_factor_data")
    def test_residual_vol_present(self, mock_factors):
        mock_factors.return_value = _make_mock_factor_data(400)
        prices = _make_mock_price_series(400)

        result = decompose_stock("VOL", price_series=prices, lookback_days=350)
        assert result is not None
        assert "residual_vol" in result
        assert result["residual_vol"] >= 0


# ── Portfolio decomposition ───────────────────────────────────────


class TestDecomposePortfolio:
    @patch("backend.services.factor_model.decompose_stock")
    def test_basic_portfolio(self, mock_decompose):
        mock_decompose.return_value = {
            "ticker": "MOCK",
            "observations": 300,
            "r_squared": 0.85,
            "adjusted_r_squared": 0.84,
            "alpha_daily": 0.0002,
            "alpha_annual": 0.05,
            "alpha_significant": True,
            "factors": {
                "Mkt-RF": {"loading": 1.1, "t_stat": 15.0, "p_value": 0.001, "significant": True},
                "SMB": {"loading": -0.1, "t_stat": -1.5, "p_value": 0.13, "significant": False},
                "HML": {"loading": 0.3, "t_stat": 3.0, "p_value": 0.003, "significant": True},
                "RMW": {"loading": 0.2, "t_stat": 2.5, "p_value": 0.01, "significant": True},
                "CMA": {"loading": 0.1, "t_stat": 1.2, "p_value": 0.22, "significant": False},
            },
            "style": {"market": "neutral", "value": "value", "size": "neutral", "profitability": "quality", "investment": "neutral"},
            "residual_vol": 0.15,
        }

        weights = {"AAPL": 0.5, "MSFT": 0.3, "GOOGL": 0.2}
        result = decompose_portfolio(weights)

        assert result is not None
        assert "portfolio_alpha_annual" in result
        assert "portfolio_factors" in result
        assert "portfolio_style" in result
        assert result["stocks_analyzed"] == 3

    @patch("backend.services.factor_model.decompose_stock")
    def test_all_fail(self, mock_decompose):
        mock_decompose.return_value = None
        result = decompose_portfolio({"AAPL": 0.5, "MSFT": 0.5})
        assert result is None


# ── Factor data fetch ─────────────────────────────────────────────


class TestGetFactorData:
    @patch("backend.services.factor_model.get_factor_data")
    def test_returns_dataframe_or_none(self, mock_get):
        mock_get.return_value = _make_mock_factor_data(200)
        df = get_factor_data(lookback_days=100)
        if df is not None:
            assert isinstance(df, pd.DataFrame)
            assert "Mkt-RF" in df.columns
            assert "RF" in df.columns
