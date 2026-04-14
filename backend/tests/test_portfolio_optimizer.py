"""Tests for advanced portfolio optimizer."""

import numpy as np
import pandas as pd
import pytest

from backend.services.portfolio_optimizer import (
    optimize_max_diversification,
    _equal_weight_fallback,
)


@pytest.fixture
def mock_returns(monkeypatch):
    """Mock _fetch_returns to avoid network calls."""
    rng = np.random.default_rng(42)
    T = 504
    tickers = ["AAPL", "MSFT", "GOOGL", "JPM", "XOM"]

    # Create realistic correlated returns
    corr = np.array([
        [1.0, 0.7, 0.6, 0.3, 0.1],
        [0.7, 1.0, 0.65, 0.25, 0.15],
        [0.6, 0.65, 1.0, 0.2, 0.1],
        [0.3, 0.25, 0.2, 1.0, 0.4],
        [0.1, 0.15, 0.1, 0.4, 1.0],
    ])
    L = np.linalg.cholesky(corr)
    Z = rng.standard_normal((T, 5))
    vols = np.array([0.25, 0.22, 0.28, 0.20, 0.24]) / np.sqrt(252)
    mus = np.array([0.12, 0.10, 0.14, 0.08, 0.06]) / 252

    returns_data = (Z @ L.T) * vols + mus
    df = pd.DataFrame(returns_data, columns=tickers)

    def mock_fetch(tickers_arg, lookback_days=504):
        available = [t for t in tickers_arg if t in df.columns]
        return df[available] if available else None

    import backend.services.portfolio_optimizer as po
    monkeypatch.setattr(po, "_fetch_returns", mock_fetch)
    return df


class TestEqualWeight:
    def test_basic(self):
        result = _equal_weight_fallback(["AAPL", "MSFT", "GOOGL"])
        assert result["method"] == "equal_weight"
        assert len(result["weights"]) == 3
        assert abs(sum(result["weights"].values()) - 1.0) < 0.01


class TestMaxDiversification:
    def test_basic(self, mock_returns):
        result = optimize_max_diversification(["AAPL", "MSFT", "GOOGL", "JPM", "XOM"])
        assert result is not None
        assert result["method"] == "max_diversification"
        assert len(result["weights"]) >= 2
        # Weights should sum to ~1
        assert abs(sum(result["weights"].values()) - 1.0) < 0.02
        # Diversification ratio should be > 1
        assert result["metrics"]["diversification_ratio"] > 1.0

    def test_two_assets(self, mock_returns):
        result = optimize_max_diversification(["AAPL", "XOM"])
        assert result is not None
        # Low correlation pair should get more equal weights
        assert len(result["weights"]) == 2

    def test_insufficient_tickers(self, mock_returns):
        result = optimize_max_diversification(["UNKNOWN_TICKER"])
        assert result is None


class TestMeanCVaR:
    def test_basic(self, mock_returns):
        from backend.services.portfolio_optimizer import optimize_mean_cvar
        result = optimize_mean_cvar(["AAPL", "MSFT", "GOOGL", "JPM", "XOM"])
        assert result is not None
        assert result["method"] == "mean_cvar"
        assert len(result["weights"]) >= 1
        assert abs(sum(result["weights"].values()) - 1.0) < 0.05


class TestRiskParity:
    def test_basic(self, mock_returns):
        from backend.services.portfolio_optimizer import optimize_risk_parity
        result = optimize_risk_parity(["AAPL", "MSFT", "GOOGL", "JPM", "XOM"])
        assert result is not None
        assert result["method"] == "risk_parity"
        # Risk parity should give more balanced weights than mean-var
        weights = list(result["weights"].values())
        assert max(weights) < 0.5  # No single asset > 50%


class TestHRP:
    def test_basic(self, mock_returns):
        from backend.services.portfolio_optimizer import optimize_hrp
        result = optimize_hrp(["AAPL", "MSFT", "GOOGL", "JPM", "XOM"])
        assert result is not None
        assert result["method"] == "hrp"
        assert len(result["weights"]) >= 2


class TestLiquidityAdjustedPositionSizing:
    """Tests for adjust_weights_for_liquidity()."""

    def test_no_adjustment_for_liquid_stocks(self):
        from backend.services.portfolio_optimizer import adjust_weights_for_liquidity
        weights = {"AAPL": 0.4, "MSFT": 0.3, "GOOGL": 0.3}
        liq_scores = {
            "AAPL": {"composite": 90, "tier": "highly_liquid", "avg_dollar_volume_mm": 5000},
            "MSFT": {"composite": 85, "tier": "highly_liquid", "avg_dollar_volume_mm": 4000},
            "GOOGL": {"composite": 80, "tier": "highly_liquid", "avg_dollar_volume_mm": 3000},
        }
        result = adjust_weights_for_liquidity(weights, liq_scores)
        assert not result["liquidity_adjusted"]
        assert abs(sum(result["weights"].values()) - 1.0) < 0.02

    def test_penalizes_illiquid_stock(self):
        from backend.services.portfolio_optimizer import adjust_weights_for_liquidity
        weights = {"AAPL": 0.5, "MSFT": 0.3, "ILLIQ": 0.2}
        liq_scores = {
            "AAPL": {"composite": 90, "tier": "highly_liquid", "avg_dollar_volume_mm": 5000},
            "MSFT": {"composite": 85, "tier": "highly_liquid", "avg_dollar_volume_mm": 4000},
            "ILLIQ": {"composite": 20, "tier": "illiquid", "avg_dollar_volume_mm": 5.0},
        }
        result = adjust_weights_for_liquidity(weights, liq_scores)
        assert result["liquidity_adjusted"]
        assert result["n_penalized"] == 1
        # Illiquid stock should have lower weight
        assert result["weights"]["ILLIQ"] < 0.2
        # Weights should still sum to ~1
        assert abs(sum(result["weights"].values()) - 1.0) < 0.02

    def test_removes_very_illiquid_stock(self):
        from backend.services.portfolio_optimizer import adjust_weights_for_liquidity
        weights = {"AAPL": 0.5, "MSFT": 0.3, "MICRO": 0.2}
        liq_scores = {
            "AAPL": {"composite": 90, "tier": "highly_liquid", "avg_dollar_volume_mm": 5000},
            "MSFT": {"composite": 85, "tier": "highly_liquid", "avg_dollar_volume_mm": 4000},
            "MICRO": {"composite": 10, "tier": "highly_illiquid", "avg_dollar_volume_mm": 0.3},
        }
        result = adjust_weights_for_liquidity(weights, liq_scores)
        assert result["n_removed"] == 1
        assert "MICRO" not in result["weights"]
        assert abs(sum(result["weights"].values()) - 1.0) < 0.02

    def test_preserves_weights_when_no_liq_data(self):
        from backend.services.portfolio_optimizer import adjust_weights_for_liquidity
        weights = {"AAPL": 0.5, "MSFT": 0.5}
        result = adjust_weights_for_liquidity(weights, {})
        assert not result["liquidity_adjusted"]
        assert result["weights"] == weights

    def test_redistribution_is_proportional(self):
        from backend.services.portfolio_optimizer import adjust_weights_for_liquidity
        weights = {"A": 0.4, "B": 0.2, "C": 0.4}
        liq_scores = {
            "A": {"composite": 90, "tier": "highly_liquid", "avg_dollar_volume_mm": 5000},
            "B": {"composite": 15, "tier": "illiquid", "avg_dollar_volume_mm": 2.0},
            "C": {"composite": 85, "tier": "highly_liquid", "avg_dollar_volume_mm": 3000},
        }
        result = adjust_weights_for_liquidity(weights, liq_scores)
        # A and C should get the freed weight proportionally (50/50 since they were equal)
        assert result["weights"]["A"] > 0.4
        assert result["weights"]["C"] > 0.4
        assert result["freed_weight_pct"] > 0

    def test_all_liquid_no_change(self):
        from backend.services.portfolio_optimizer import adjust_weights_for_liquidity
        weights = {"AAPL": 0.5, "MSFT": 0.5}
        liq_scores = {
            "AAPL": {"composite": 95, "tier": "highly_liquid", "avg_dollar_volume_mm": 10000},
            "MSFT": {"composite": 92, "tier": "highly_liquid", "avg_dollar_volume_mm": 8000},
        }
        result = adjust_weights_for_liquidity(weights, liq_scores)
        assert not result["liquidity_adjusted"]
        assert abs(result["weights"]["AAPL"] - 0.5) < 0.01
        assert abs(result["weights"]["MSFT"] - 0.5) < 0.01
