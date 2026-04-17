"""Tests for the Dividend Intelligence service."""

import numpy as np
import pandas as pd
import pytest

from backend.services.dividend_intelligence import (
    get_dividend_intelligence,
    get_dividend_summary,
    _compute_trailing_yield,
    _trailing_annual_dividend,
    _compute_growth_rates,
    _annual_dividends,
    _consecutive_growth_years,
    _classify_dividend_status,
    _detect_frequency,
    _compute_payout_ratios,
    _compute_safety_score,
    _compute_ddm,
    _compute_income_projection,
    _format_history,
    _years_of_data,
    _safe_round,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_dividends(amounts: list, start: str = "2015-01-15", freq: str = "QS") -> pd.Series:
    """Create a dividend Series with quarterly dates."""
    dates = pd.date_range(start=start, periods=len(amounts), freq=freq)
    return pd.Series(amounts, index=dates)


def _make_annual_growing(years: int = 10, start_amount: float = 1.0, growth: float = 0.05):
    """Create quarterly dividends that grow 'growth' per year for 'years' years."""
    amounts = []
    dates = []
    base_year = 2010
    for y in range(years):
        annual = start_amount * (1 + growth) ** y
        quarterly = annual / 4
        for m in [3, 6, 9, 12]:
            dates.append(f"{base_year + y}-{m:02d}-15")
            amounts.append(quarterly)
    return pd.Series(amounts, index=pd.to_datetime(dates))


# ── _safe_round ──────────────────────────────────────────────────────────────


class TestSafeRound:
    def test_normal_value(self):
        assert _safe_round(3.14159, 2) == 3.14

    def test_none(self):
        assert _safe_round(None) is None

    def test_nan(self):
        assert _safe_round(float("nan")) is None

    def test_inf(self):
        assert _safe_round(float("inf")) is None

    def test_zero(self):
        assert _safe_round(0.0, 4) == 0.0


# ── _trailing_annual_dividend ────────────────────────────────────────────────


class TestTrailingAnnualDividend:
    def test_normal_quarterly(self):
        # Explicit dates: trailing 12m from last date captures last 4 payments
        dates = pd.to_datetime([
            "2023-02-15", "2023-05-15", "2023-08-15", "2023-11-15",
            "2024-02-15", "2024-05-15", "2024-08-15", "2024-11-15",
        ])
        divs = pd.Series([0.25, 0.25, 0.25, 0.25, 0.30, 0.30, 0.30, 0.30], index=dates)
        annual = _trailing_annual_dividend(divs)
        # Last date is 2024-11-15, cutoff is 2023-11-15 (inclusive >=)
        # Captures: 2023-11-15 (0.25) + 4x 2024 (0.30 each) = 1.45
        assert annual == pytest.approx(1.45, abs=0.01)

    def test_empty(self):
        assert _trailing_annual_dividend(pd.Series(dtype=float)) is None

    def test_single_payment(self):
        divs = pd.Series([1.50], index=pd.to_datetime(["2024-06-15"]))
        result = _trailing_annual_dividend(divs)
        assert result == pytest.approx(1.50)


# ── _compute_trailing_yield ──────────────────────────────────────────────────


class TestTrailingYield:
    def test_normal(self):
        # 8 quarterly payments of $0.50, trailing 12m captures 5 (boundary inclusive)
        dates = pd.to_datetime([
            "2023-02-15", "2023-05-15", "2023-08-15", "2023-11-15",
            "2024-02-15", "2024-05-15", "2024-08-15", "2024-11-15",
        ])
        divs = pd.Series([0.50] * 8, index=dates)
        yield_pct = _compute_trailing_yield(divs, 100.0)
        # 5 payments * $0.50 = $2.50 / $100 = 2.5%
        assert yield_pct == pytest.approx(2.5, abs=0.1)

    def test_zero_price(self):
        divs = _make_dividends([0.50] * 4)
        assert _compute_trailing_yield(divs, 0) is None

    def test_negative_price(self):
        divs = _make_dividends([0.50] * 4)
        assert _compute_trailing_yield(divs, -10) is None


# ── _annual_dividends ────────────────────────────────────────────────────────


class TestAnnualDividends:
    def test_aggregation(self):
        # 2 years of quarterly dividends
        dates = pd.to_datetime([
            "2023-03-15", "2023-06-15", "2023-09-15", "2023-12-15",
            "2024-03-15", "2024-06-15", "2024-09-15", "2024-12-15",
        ])
        divs = pd.Series([0.25] * 8, index=dates)
        annual = _annual_dividends(divs)
        assert len(annual) == 2
        assert annual.iloc[0] == pytest.approx(1.0)

    def test_empty(self):
        result = _annual_dividends(pd.Series(dtype=float))
        assert len(result) == 0


# ── _compute_growth_rates ────────────────────────────────────────────────────


class TestGrowthRates:
    def test_steady_growth(self):
        divs = _make_annual_growing(years=12, growth=0.08)
        rates = _compute_growth_rates(divs)
        assert "cagr_5y" in rates
        assert "cagr_10y" in rates
        # 8% growth should come back approximately
        assert rates["cagr_5y"] == pytest.approx(8.0, abs=1.5)

    def test_insufficient_data(self):
        divs = _make_dividends([0.50])
        rates = _compute_growth_rates(divs)
        assert rates == {}

    def test_zero_start(self):
        """If a year had zero dividends, CAGR can't be computed for that span."""
        dates = pd.to_datetime(["2020-03-01", "2021-03-01", "2022-03-01", "2023-03-01"])
        divs = pd.Series([0.0, 1.0, 1.1, 1.2], index=dates)
        rates = _compute_growth_rates(divs)
        # 1Y growth from 1.1 to 1.2 should work
        if "cagr_1y" in rates:
            assert rates["cagr_1y"] > 0


# ── _consecutive_growth_years ────────────────────────────────────────────────


class TestConsecutiveGrowth:
    def test_steady_growth(self):
        annual = pd.Series([1.0, 1.05, 1.10, 1.15, 1.20])
        assert _consecutive_growth_years(annual) == 4

    def test_recent_cut(self):
        annual = pd.Series([1.0, 1.05, 1.10, 0.90, 1.00])
        assert _consecutive_growth_years(annual) == 1

    def test_flat(self):
        annual = pd.Series([1.0, 1.0, 1.0])
        assert _consecutive_growth_years(annual) == 0

    def test_single_year(self):
        annual = pd.Series([1.0])
        assert _consecutive_growth_years(annual) == 0

    def test_empty(self):
        assert _consecutive_growth_years(pd.Series(dtype=float)) == 0

    def test_long_streak(self):
        annual = pd.Series([1.0 * (1.05 ** i) for i in range(30)])
        assert _consecutive_growth_years(annual) == 29


# ── _classify_dividend_status ────────────────────────────────────────────────


class TestClassification:
    def test_aristocrat(self):
        assert _classify_dividend_status(25) == "Dividend Aristocrat"
        assert _classify_dividend_status(30) == "Dividend Aristocrat"

    def test_contender(self):
        assert _classify_dividend_status(10) == "Dividend Contender"
        assert _classify_dividend_status(15) == "Dividend Contender"

    def test_challenger(self):
        assert _classify_dividend_status(5) == "Dividend Challenger"
        assert _classify_dividend_status(7) == "Dividend Challenger"

    def test_grower(self):
        assert _classify_dividend_status(1) == "Dividend Grower"
        assert _classify_dividend_status(3) == "Dividend Grower"

    def test_no_growth(self):
        assert _classify_dividend_status(0) == "No Consecutive Growth"


# ── _detect_frequency ────────────────────────────────────────────────────────


class TestDetectFrequency:
    def test_quarterly(self):
        dates = pd.date_range("2023-01-15", periods=8, freq="QS")
        divs = pd.Series([0.5] * 8, index=dates)
        assert _detect_frequency(divs) == "quarterly"

    def test_monthly(self):
        dates = pd.date_range("2023-01-15", periods=12, freq="MS")
        divs = pd.Series([0.1] * 12, index=dates)
        assert _detect_frequency(divs) == "monthly"

    def test_annual(self):
        dates = pd.date_range("2020-06-15", periods=4, freq="YS")
        divs = pd.Series([2.0] * 4, index=dates)
        assert _detect_frequency(divs) == "annual"

    def test_semi_annual(self):
        dates = pd.date_range("2022-01-15", periods=6, freq="6MS")
        divs = pd.Series([1.0] * 6, index=dates)
        assert _detect_frequency(divs) == "semi-annual"

    def test_too_few(self):
        divs = _make_dividends([0.5, 0.5])
        assert _detect_frequency(divs) == "unknown"


# ── _compute_payout_ratios ───────────────────────────────────────────────────


class TestPayoutRatios:
    def test_normal(self):
        info = {
            "payoutRatio": 0.45,
            "trailingEps": 5.0,
            "dividendRate": 2.0,
            "freeCashflow": 1e9,
            "sharesOutstanding": 1e8,
        }
        result = _compute_payout_ratios(info)
        assert result["earnings_payout_pct"] == pytest.approx(45.0)
        assert result["eps_payout_pct"] == pytest.approx(40.0)
        assert "fcf_payout_pct" in result

    def test_empty_info(self):
        result = _compute_payout_ratios({})
        assert result == {}

    def test_negative_eps(self):
        info = {"trailingEps": -2.0, "dividendRate": 1.0}
        result = _compute_payout_ratios(info)
        # Should not produce eps_payout_pct with negative EPS
        assert "eps_payout_pct" not in result


# ── _compute_safety_score ────────────────────────────────────────────────────


class TestSafetyScore:
    def test_very_safe(self):
        info = {"debtToEquity": 20}  # 0.2 ratio
        payout = {"earnings_payout_pct": 30, "fcf_payout_pct": 35}
        growth = {"cagr_5y": 8.0}
        result = _compute_safety_score(info, payout, growth, consecutive_years=20)
        assert result["score"] >= 75
        assert result["grade"] in ("Very Safe", "Safe")

    def test_very_unsafe(self):
        info = {"debtToEquity": 300}
        payout = {"earnings_payout_pct": 120, "fcf_payout_pct": 150}
        growth = {}
        result = _compute_safety_score(info, payout, growth, consecutive_years=0)
        assert result["score"] is not None
        assert result["score"] < 30

    def test_no_data(self):
        result = _compute_safety_score({}, {}, {}, 0)
        # Should have earnings_stability at minimum
        assert result["score"] is not None

    def test_components_present(self):
        info = {"debtToEquity": 50}
        payout = {"earnings_payout_pct": 50}
        result = _compute_safety_score(info, payout, {}, 10)
        assert "components" in result
        assert "payout_ratio" in result["components"]
        assert "debt_equity" in result["components"]


# ── _compute_ddm ─────────────────────────────────────────────────────────────


class TestDDM:
    def test_normal(self):
        divs = _make_dividends([0.50] * 8)  # $2/yr
        growth = {"cagr_5y": 5.0}
        result = _compute_ddm(divs, 100.0, growth)
        assert result["intrinsic_value"] is not None
        assert result["intrinsic_value"] > 0
        assert result["upside_pct"] is not None
        assert result["growth_rate_used"] == pytest.approx(5.0)

    def test_no_growth_data(self):
        divs = _make_dividends([0.50] * 8)
        result = _compute_ddm(divs, 100.0, {})
        # Should use terminal growth as fallback
        assert result["intrinsic_value"] is not None

    def test_zero_dividend(self):
        divs = pd.Series(dtype=float)
        result = _compute_ddm(divs, 100.0, {"cagr_5y": 5.0})
        assert result["intrinsic_value"] is None

    def test_growth_capped_below_discount(self):
        """Growth rate can't exceed discount rate in Gordon model."""
        divs = _make_dividends([0.50] * 8)
        growth = {"cagr_5y": 15.0}  # Higher than discount rate
        result = _compute_ddm(divs, 100.0, growth)
        # Should still produce a valid value (growth gets capped)
        assert result["intrinsic_value"] is not None
        assert result["growth_rate_used"] < 10.0  # Below discount rate


# ── _compute_income_projection ───────────────────────────────────────────────


class TestIncomeProjection:
    def test_normal(self):
        result = _compute_income_projection(3.0, 50.0, 10000)
        assert result["annual_income"] == pytest.approx(300.0)
        assert result["monthly_income"] == pytest.approx(25.0)
        assert result["shares"] == pytest.approx(200.0)

    def test_no_yield(self):
        result = _compute_income_projection(None, 50.0, 10000)
        assert result["annual_income"] is None

    def test_zero_yield(self):
        result = _compute_income_projection(0, 50.0, 10000)
        assert result["annual_income"] is None


# ── _format_history ──────────────────────────────────────────────────────────


class TestFormatHistory:
    def test_normal(self):
        divs = _make_dividends([0.25, 0.30, 0.35])
        hist = _format_history(divs, tail=10)
        assert len(hist) == 3
        assert "date" in hist[0]
        assert "amount" in hist[0]
        assert hist[-1]["amount"] == 0.35

    def test_tail_limit(self):
        divs = _make_dividends([0.25] * 30)
        hist = _format_history(divs, tail=5)
        assert len(hist) == 5


# ── _years_of_data ───────────────────────────────────────────────────────────


class TestYearsOfData:
    def test_normal(self):
        divs = _make_dividends([0.25] * 20)  # ~5 years quarterly
        years = _years_of_data(divs)
        assert years is not None
        assert years > 3.5

    def test_empty(self):
        assert _years_of_data(pd.Series(dtype=float)) is None


# ── Integration: get_dividend_intelligence (mock-free, uses yfinance) ────────


class TestGetDividendIntelligence:
    @pytest.mark.slow
    def test_jnj_has_dividends(self):
        """JNJ is a well-known dividend aristocrat."""
        result = get_dividend_intelligence("JNJ")
        assert result is not None
        assert result["pays_dividend"] is True
        assert result["trailing_yield"] is not None
        assert result["trailing_yield"] > 0
        assert result["consecutive_growth_years"] >= 5
        assert result["safety"]["score"] is not None
        assert result["classification"] in (
            "Dividend Aristocrat",
            "Dividend Contender",
            "Dividend Challenger",
            "Dividend Grower",
        )

    @pytest.mark.slow
    def test_non_payer(self):
        """AMZN historically doesn't pay dividends (may change)."""
        result = get_dividend_intelligence("AMZN")
        # AMZN might start paying in future; if so, should still return valid data
        assert result is not None
        if not result.get("pays_dividend"):
            assert "message" in result

    @pytest.mark.slow
    def test_summary_compact(self):
        """Summary should be a compact subset."""
        result = get_dividend_summary("JNJ")
        if result is not None:
            assert "trailing_yield" in result
            assert "safety_score" in result
            assert "classification" in result
            # Should NOT have full history
            assert "history" not in result

    def test_invalid_ticker(self):
        """Invalid ticker should return None gracefully."""
        result = get_dividend_intelligence("ZZZZZZ_FAKE")
        # Should either return None or pays_dividend=False
        assert result is None or result.get("pays_dividend") is False
