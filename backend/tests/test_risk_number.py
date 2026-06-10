"""Tests for portfolio risk number (1-100)."""

import numpy as np
import pandas as pd

from backend.services.risk_number import compute_risk_number


def _make_returns(n_days=252, n_assets=5, seed=42):
    """Generate synthetic daily return data."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-01", periods=n_days)
    tickers = [f"STOCK{i}" for i in range(n_assets)]
    data = rng.normal(0.0003, 0.015, (n_days, n_assets))
    returns = pd.DataFrame(data, index=dates, columns=tickers)
    weights = {t: 1.0 / n_assets for t in tickers}
    return returns, weights


class TestRiskNumber:
    def test_basic_output_structure(self):
        returns, weights = _make_returns()
        result = compute_risk_number(returns, weights)
        assert "risk_number" in result
        assert "level" in result
        assert "description" in result
        assert "components" in result
        assert 1 <= result["risk_number"] <= 99

    def test_components_present(self):
        returns, weights = _make_returns()
        result = compute_risk_number(returns, weights)
        for key in ["volatility", "max_drawdown", "cvar_95", "concentration", "beta"]:
            assert key in result["components"]
            comp = result["components"][key]
            assert "value" in comp
            assert "score" in comp

    def test_low_vol_portfolio_gets_low_score(self):
        """Near-zero vol portfolio should have low risk number."""
        rng = np.random.default_rng(42)
        dates = pd.bdate_range("2024-01-01", periods=252)
        returns = pd.DataFrame(
            rng.normal(0.0001, 0.001, (252, 3)),
            index=dates,
            columns=["A", "B", "C"],
        )
        weights = {"A": 0.33, "B": 0.34, "C": 0.33}
        result = compute_risk_number(returns, weights)
        assert result["risk_number"] <= 30

    def test_high_vol_portfolio_gets_high_score(self):
        """Very volatile portfolio should have high risk number."""
        rng = np.random.default_rng(42)
        dates = pd.bdate_range("2024-01-01", periods=252)
        returns = pd.DataFrame(
            rng.normal(0.0, 0.05, (252, 2)),
            index=dates,
            columns=["X", "Y"],
        )
        weights = {"X": 0.5, "Y": 0.5}
        result = compute_risk_number(returns, weights)
        assert result["risk_number"] >= 60

    def test_concentrated_portfolio_penalized(self):
        """Single-stock portfolio should have higher risk number."""
        returns, _ = _make_returns()
        # Diversified
        equal_weights = {f"STOCK{i}": 0.2 for i in range(5)}
        result_div = compute_risk_number(returns, equal_weights)
        # Concentrated
        conc_weights = {"STOCK0": 1.0}
        result_conc = compute_risk_number(returns, conc_weights)
        assert result_conc["risk_number"] >= result_div["risk_number"]

    def test_with_benchmark(self):
        returns, weights = _make_returns()
        bench = returns.mean(axis=1)  # simple benchmark
        result = compute_risk_number(returns, weights, benchmark_returns=bench)
        assert "beta" in result["components"]
        assert result["components"]["beta"]["value"] is not None

    def test_insufficient_data(self):
        dates = pd.bdate_range("2024-01-01", periods=10)
        returns = pd.DataFrame({"A": np.zeros(10)}, index=dates)
        result = compute_risk_number(returns, {"A": 1.0})
        assert result["risk_number"] == 50  # fallback

    def test_no_valid_tickers(self):
        returns, _ = _make_returns()
        result = compute_risk_number(returns, {"INVALID": 1.0})
        assert result["risk_number"] == 50  # fallback

    def test_level_categories(self):
        """Ensure levels map correctly to score ranges."""
        returns, weights = _make_returns()
        result = compute_risk_number(returns, weights)
        rn = result["risk_number"]
        level = result["level"]
        if rn <= 20:
            assert level == "very_low"
        elif rn <= 40:
            assert level == "low"
        elif rn <= 60:
            assert level == "moderate"
        elif rn <= 80:
            assert level == "high"
        else:
            assert level == "very_high"

    def test_weights_renormalized(self):
        """Non-normalized weights should still work."""
        returns, _ = _make_returns()
        weights = {"STOCK0": 2.0, "STOCK1": 3.0}  # sums to 5, not 1
        result = compute_risk_number(returns, weights)
        assert 1 <= result["risk_number"] <= 99
