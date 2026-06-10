"""Tests for SEC EDGAR fundamentals service."""

from backend.services.fundamentals import (
    get_fundamentals,
    _compute_metrics,
    _compute_piotroski,
    _safe_float,
    EDGAR_AVAILABLE,
)


class TestSafeFloat:
    def test_valid_float(self):
        assert _safe_float(42.5) == 42.5

    def test_string_number(self):
        assert _safe_float("123.45") == 123.45

    def test_none(self):
        assert _safe_float(None) is None

    def test_nan(self):
        assert _safe_float(float("nan")) is None

    def test_inf(self):
        assert _safe_float(float("inf")) is None


class TestComputeMetrics:
    def test_profitability_metrics(self):
        income = {"revenue": 1000000, "net_income": 200000, "operating_income": 300000, "gross_profit": 600000}
        balance = {"total_assets": 5000000, "stockholders_equity": 2000000}
        cashflow = {"operating_cash_flow": 250000, "capital_expenditures": 50000}

        metrics = _compute_metrics(income, balance, cashflow)
        assert metrics["net_margin"] == 20.0
        assert metrics["operating_margin"] == 30.0
        assert metrics["gross_margin"] == 60.0
        assert metrics["return_on_assets"] == 4.0
        assert metrics["return_on_equity"] == 10.0

    def test_leverage_metrics(self):
        income = {"revenue": 1000000, "net_income": 100000}
        balance = {
            "stockholders_equity": 500000,
            "total_debt": 200000,
            "short_term_debt": 50000,
            "current_assets": 300000,
            "current_liabilities": 150000,
            "total_assets": 1000000,
        }
        cashflow = {}

        metrics = _compute_metrics(income, balance, cashflow)
        assert metrics["debt_to_equity"] == 0.5  # 250k / 500k
        assert metrics["current_ratio"] == 2.0   # 300k / 150k

    def test_fcf_metrics(self):
        income = {"revenue": 1000000}
        balance = {}
        cashflow = {"operating_cash_flow": 200000, "capital_expenditures": 50000}

        metrics = _compute_metrics(income, balance, cashflow)
        assert metrics["free_cash_flow"] == 150000
        assert metrics["fcf_margin"] == 15.0

    def test_empty_inputs(self):
        metrics = _compute_metrics({}, {}, {})
        assert metrics == {}


class TestPiotroski:
    def test_strong_company(self):
        income = {"revenue": 1000000, "net_income": 200000, "gross_profit": 600000}
        balance = {
            "total_assets": 2000000,
            "stockholders_equity": 1500000,
            "total_debt": 100000,
            "short_term_debt": 50000,
            "current_assets": 500000,
            "current_liabilities": 200000,
        }
        cashflow = {"operating_cash_flow": 300000}

        result = _compute_piotroski(income, balance, cashflow)
        assert result["score"] >= 5  # Strong fundamentals
        assert result["strength"] in ("strong", "moderate")

    def test_weak_company(self):
        income = {"revenue": 100000, "net_income": -50000, "gross_profit": -10000}
        balance = {
            "total_assets": 500000,
            "stockholders_equity": 100000,
            "total_debt": 400000,
            "current_assets": 50000,
            "current_liabilities": 200000,
        }
        cashflow = {"operating_cash_flow": -30000}

        result = _compute_piotroski(income, balance, cashflow)
        assert result["score"] <= 3
        assert result["strength"] == "weak"

    def test_empty_data(self):
        result = _compute_piotroski({}, {}, {})
        assert result["score"] == 0
        assert result["strength"] == "weak"

    def test_max_score_is_7(self):
        """Implementation covers 7 binary checks (not full 9-criteria Piotroski)."""
        result = _compute_piotroski(
            {"revenue": 1e6, "net_income": 2e5, "gross_profit": 5e5},
            {"total_assets": 1e6, "stockholders_equity": 8e5, "total_debt": 0,
             "short_term_debt": 0, "current_assets": 5e5, "current_liabilities": 1e5},
            {"operating_cash_flow": 3e5},
        )
        assert result["max_score"] == 7
        assert 0 <= result["score"] <= 7

    def test_perfect_score_achievable(self):
        """All 7 checks should pass for an ideal company."""
        result = _compute_piotroski(
            {"revenue": 1e6, "net_income": 2e5, "gross_profit": 5e5},
            {"total_assets": 1e6, "stockholders_equity": 8e5, "total_debt": 0,
             "short_term_debt": 0, "current_assets": 5e5, "current_liabilities": 1e5},
            {"operating_cash_flow": 3e5},
        )
        assert result["score"] == 7
        assert result["strength"] == "strong"


class TestGetFundamentals:
    def test_returns_none_when_edgar_unavailable(self):
        """If edgartools isn't available, should return None gracefully."""
        if not EDGAR_AVAILABLE:
            result = get_fundamentals("AAPL")
            assert result is None
