"""
Router-Level Tests for Aegis Finance API
==========================================

Tests the HTTP layer: status codes, input validation, query parameter parsing,
cache key logic, response structure, and input sanitization.

Uses FastAPI TestClient with mocked service backends so tests are fast
and don't require network or FRED keys.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


# ══════════════════════════════════════════════════════════════════════════════
# ROOT & HEALTH
# ══════════════════════════════════════════════════════════════════════════════


class TestRootAndHealth:
    def test_root_returns_200(self, client):
        r = client.get("/")
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "Aegis Finance API"
        assert "endpoints" in body

    def test_root_contains_version(self, client):
        body = client.get("/").json()
        assert "version" in body
        assert body["version"] == "0.2.0"

    def test_root_contains_docs_link(self, client):
        body = client.get("/").json()
        assert body["docs"] == "/docs"

    def test_health_returns_200(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "cache_ready" in body

    def test_health_has_version(self, client):
        body = client.get("/api/health").json()
        assert body["version"] == "0.2.0"

    def test_nonexistent_route_returns_404(self, client):
        r = client.get("/api/nonexistent")
        assert r.status_code == 404

    def test_nonexistent_deep_path_404(self, client):
        r = client.get("/api/foo/bar/baz")
        assert r.status_code == 404

    def test_post_to_get_endpoint_405(self, client):
        """POST to a GET-only endpoint should return 405 Method Not Allowed."""
        r = client.post("/api/health")
        assert r.status_code == 405

    def test_get_to_post_endpoint_405(self, client):
        """GET to a POST-only endpoint should return 405."""
        r = client.get("/api/savings/project")
        assert r.status_code == 405

    def test_get_to_portfolio_build_405(self, client):
        r = client.get("/api/portfolio/build")
        assert r.status_code == 405


# ══════════════════════════════════════════════════════════════════════════════
# CRASH ROUTER — input validation & ticker sanitization
# ══════════════════════════════════════════════════════════════════════════════


class TestCrashRouter:
    def test_prediction_invalid_horizon_rejected(self, client):
        """Horizon must be 3m, 6m, or 12m."""
        r = client.get("/api/crash/prediction?horizon=99z")
        assert r.status_code == 422

    def test_prediction_empty_horizon_rejected(self, client):
        r = client.get("/api/crash/prediction?horizon=")
        assert r.status_code == 422

    def test_prediction_1m_horizon_rejected(self, client):
        """1m is not a valid horizon."""
        r = client.get("/api/crash/prediction?horizon=1m")
        assert r.status_code == 422

    def test_prediction_valid_horizons_accepted(self, client):
        """Valid horizons should not trigger 422."""
        for h in ["3m", "6m", "12m"]:
            r = client.get(f"/api/crash/prediction?horizon={h}")
            assert r.status_code != 422

    def test_prediction_default_horizon_accepted(self, client):
        """Default horizon (no param) should work."""
        r = client.get("/api/crash/prediction")
        assert r.status_code != 422

    def test_prediction_explain_flag(self, client):
        """explain=true should not trigger 422."""
        r = client.get("/api/crash/prediction?explain=true")
        assert r.status_code != 422

    def test_ticker_crash_invalid_ticker_rejected(self, client):
        """Tickers with special chars should be rejected."""
        r = client.get("/api/crash/DROP TABLE")
        assert r.status_code == 422

    def test_ticker_crash_too_long_rejected(self, client):
        r = client.get("/api/crash/ABCDEFGHIJK")
        assert r.status_code == 422

    def test_ticker_crash_lowercase_uppercased(self, client):
        """Lowercase tickers are uppercased before regex check, so they pass."""
        r = client.get("/api/crash/aapl")
        assert r.status_code != 422

    def test_ticker_crash_dot_ticker_accepted(self, client):
        """BRK.B format should be accepted."""
        r = client.get("/api/crash/BRK.B")
        assert r.status_code != 422

    def test_ticker_crash_hyphen_accepted(self, client):
        """BRK-B format should be accepted."""
        r = client.get("/api/crash/BRK-B")
        assert r.status_code != 422

    def test_ticker_crash_numeric_accepted(self, client):
        """Numeric-containing tickers should pass."""
        r = client.get("/api/crash/3M")
        assert r.status_code != 422


# ══════════════════════════════════════════════════════════════════════════════
# STOCK ROUTER — all sub-endpoints share ticker validation
# ══════════════════════════════════════════════════════════════════════════════


class TestStockRouterTickerValidation:
    """All stock sub-endpoints must reject invalid tickers with 422."""

    @pytest.mark.parametrize("path_suffix", [
        "",            # /{ticker}
        "/signal",     # /{ticker}/signal
        "/shap",       # /{ticker}/shap
        "/sentiment",  # /{ticker}/sentiment
    ])
    def test_invalid_ticker_rejected_all_endpoints(self, client, path_suffix):
        r = client.get(f"/api/stock/!!!BAD{path_suffix}")
        assert r.status_code == 422, f"Invalid ticker accepted on /api/stock/!!!BAD{path_suffix}"

    @pytest.mark.parametrize("path_suffix", [
        "",
        "/signal",
        "/shap",
        "/sentiment",
    ])
    def test_too_long_ticker_rejected_all_endpoints(self, client, path_suffix):
        r = client.get(f"/api/stock/ABCDEFGHIJK{path_suffix}")
        assert r.status_code == 422

    @pytest.mark.parametrize("path_suffix", [
        "",
        "/signal",
        "/shap",
        "/sentiment",
    ])
    def test_sql_injection_rejected_all_endpoints(self, client, path_suffix):
        r = client.get(f"/api/stock/'; DROP TABLE--{path_suffix}")
        assert r.status_code in (404, 422)

    @pytest.mark.parametrize("ticker", ["AAPL", "BRK.B", "T", "X", "NVDA"])
    def test_valid_tickers_pass_main_endpoint(self, client, ticker):
        r = client.get(f"/api/stock/{ticker}")
        assert r.status_code != 422, f"Valid ticker {ticker} wrongly rejected"

    def test_lowercase_uppercased(self, client):
        r = client.get("/api/stock/aapl")
        assert r.status_code != 422


# ══════════════════════════════════════════════════════════════════════════════
# SIMULATION ROUTER — query parameter bounds
# ══════════════════════════════════════════════════════════════════════════════


class TestSimulationRouter:
    def test_sp500_nsims_below_minimum_rejected(self, client):
        r = client.get("/api/simulation/sp500?n_sims=500")
        assert r.status_code == 422

    def test_sp500_nsims_above_maximum_rejected(self, client):
        r = client.get("/api/simulation/sp500?n_sims=100000")
        assert r.status_code == 422

    def test_sp500_nsims_zero_rejected(self, client):
        r = client.get("/api/simulation/sp500?n_sims=0")
        assert r.status_code == 422

    def test_sp500_nsims_negative_rejected(self, client):
        r = client.get("/api/simulation/sp500?n_sims=-1000")
        assert r.status_code == 422

    def test_sp500_nsims_non_integer_rejected(self, client):
        r = client.get("/api/simulation/sp500?n_sims=abc")
        assert r.status_code == 422

    def test_sp500_years_below_minimum_rejected(self, client):
        r = client.get("/api/simulation/sp500?years=0")
        assert r.status_code == 422

    def test_sp500_years_above_maximum_rejected(self, client):
        r = client.get("/api/simulation/sp500?years=20")
        assert r.status_code == 422

    def test_sp500_years_negative_rejected(self, client):
        r = client.get("/api/simulation/sp500?years=-3")
        assert r.status_code == 422

    def test_sp500_valid_params_not_422(self, client):
        r = client.get("/api/simulation/sp500?n_sims=1000&years=5")
        assert r.status_code != 422

    def test_sp500_boundary_min_params(self, client):
        """Exact minimum values should be accepted."""
        r = client.get("/api/simulation/sp500?n_sims=1000&years=1")
        assert r.status_code != 422

    def test_sp500_boundary_max_params(self, client):
        """Exact maximum values should be accepted."""
        r = client.get("/api/simulation/sp500?n_sims=50000&years=10")
        assert r.status_code != 422

    def test_sp500_default_params_accepted(self, client):
        """No params should use defaults and not 422."""
        r = client.get("/api/simulation/sp500")
        assert r.status_code != 422

    def test_scenarios_endpoint_exists(self, client):
        """Scenarios endpoint should not 404."""
        r = client.get("/api/simulation/scenarios")
        assert r.status_code != 404


# ══════════════════════════════════════════════════════════════════════════════
# NEWS ROUTER — ticker validation
# ══════════════════════════════════════════════════════════════════════════════


class TestNewsRouter:
    def test_invalid_ticker_rejected(self, client):
        r = client.get("/api/news/!!!BAD!!!")
        assert r.status_code == 422
        assert "Invalid ticker" in r.json()["detail"]

    def test_valid_ticker_not_422(self, client):
        r = client.get("/api/news/AAPL")
        assert r.status_code != 422

    def test_ticker_with_dot_accepted(self, client):
        r = client.get("/api/news/BRK.B")
        assert r.status_code != 422

    def test_market_news_endpoint_exists(self, client):
        r = client.get("/api/news/market")
        assert r.status_code != 404

    def test_empty_ticker_404(self, client):
        """Trailing slash without ticker resolves to /api/news/ which is 404."""
        r = client.get("/api/news/")
        # Either 404 (no match) or 307 redirect — should not be 200
        assert r.status_code in (307, 404)


# ══════════════════════════════════════════════════════════════════════════════
# SAVINGS ROUTER — Pydantic model validation
# ══════════════════════════════════════════════════════════════════════════════


class TestSavingsRouter:
    def test_default_request_returns_200(self, client):
        r = client.post("/api/savings/project", json={})
        assert r.status_code == 200

    def test_negative_contribution_rejected(self, client):
        r = client.post("/api/savings/project", json={"monthly_contribution": -100})
        assert r.status_code == 422

    def test_invalid_risk_level_rejected(self, client):
        r = client.post("/api/savings/project", json={"risk_level": "yolo"})
        assert r.status_code == 422

    def test_target_age_less_than_current_returns_error(self, client):
        r = client.post("/api/savings/project", json={
            "current_age": 65,
            "target_age": 25,
        })
        assert r.status_code == 200
        body = r.json()
        assert "error" in body

    def test_valid_request_returns_projection(self, client):
        r = client.post("/api/savings/project", json={
            "monthly_contribution": 1000,
            "current_savings": 50000,
            "current_age": 30,
            "target_age": 65,
            "risk_level": "aggressive",
        })
        assert r.status_code == 200
        body = r.json()
        assert "error" not in body or body.get("error") is None

    def test_extreme_inflation_rejected(self, client):
        r = client.post("/api/savings/project", json={"inflation_rate": 0.50})
        assert r.status_code == 422

    def test_all_risk_levels_accepted(self, client):
        for level in ["conservative", "moderate", "aggressive"]:
            r = client.post("/api/savings/project", json={"risk_level": level})
            assert r.status_code == 200

    def test_zero_contribution_accepted(self, client):
        """Zero monthly contribution is valid (lump sum only)."""
        r = client.post("/api/savings/project", json={"monthly_contribution": 0})
        assert r.status_code == 200

    def test_zero_savings_accepted(self, client):
        """Starting from zero savings is valid."""
        r = client.post("/api/savings/project", json={"current_savings": 0})
        assert r.status_code == 200

    def test_boundary_age_min_accepted(self, client):
        """Age 1 is the minimum allowed."""
        r = client.post("/api/savings/project", json={"current_age": 1, "target_age": 65})
        assert r.status_code == 200

    def test_boundary_age_max_accepted(self, client):
        """Age 100 current, 120 target are the maximums."""
        r = client.post("/api/savings/project", json={"current_age": 100, "target_age": 120})
        assert r.status_code == 200

    def test_age_zero_rejected(self, client):
        r = client.post("/api/savings/project", json={"current_age": 0})
        assert r.status_code == 422

    def test_target_age_over_120_rejected(self, client):
        r = client.post("/api/savings/project", json={"target_age": 121})
        assert r.status_code == 422

    def test_negative_inflation_rejected(self, client):
        r = client.post("/api/savings/project", json={"inflation_rate": -0.01})
        assert r.status_code == 422

    def test_zero_inflation_accepted(self, client):
        r = client.post("/api/savings/project", json={"inflation_rate": 0.0})
        assert r.status_code == 200

    def test_max_contribution_boundary(self, client):
        r = client.post("/api/savings/project", json={"monthly_contribution": 1_000_000})
        assert r.status_code == 200

    def test_over_max_contribution_rejected(self, client):
        r = client.post("/api/savings/project", json={"monthly_contribution": 1_000_001})
        assert r.status_code == 422

    def test_no_json_body_rejected(self, client):
        """POST without JSON body should fail."""
        r = client.post("/api/savings/project", content=b"not json",
                        headers={"Content-Type": "application/json"})
        assert r.status_code == 422

    def test_non_json_content_type_rejected(self, client):
        r = client.post("/api/savings/project", content=b"hello",
                        headers={"Content-Type": "text/plain"})
        assert r.status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# PORTFOLIO ROUTER — Pydantic validation
# ══════════════════════════════════════════════════════════════════════════════


class TestPortfolioRouter:
    def test_build_invalid_risk_tolerance_rejected(self, client):
        r = client.post("/api/portfolio/build", json={
            "risk_tolerance": "extreme",
        })
        assert r.status_code == 422

    def test_build_invalid_method_rejected(self, client):
        r = client.post("/api/portfolio/build", json={
            "method": "random",
        })
        assert r.status_code == 422

    def test_build_invalid_time_horizon_rejected(self, client):
        r = client.post("/api/portfolio/build", json={
            "time_horizon": "100y",
        })
        assert r.status_code == 422

    def test_build_invalid_goal_rejected(self, client):
        r = client.post("/api/portfolio/build", json={
            "goal": "gambling",
        })
        assert r.status_code == 422

    def test_build_zero_amount_rejected(self, client):
        r = client.post("/api/portfolio/build", json={
            "investment_amount": 0,
        })
        assert r.status_code == 422

    def test_build_negative_amount_rejected(self, client):
        r = client.post("/api/portfolio/build", json={
            "investment_amount": -10000,
        })
        assert r.status_code == 422

    def test_build_valid_combinations_accepted(self, client):
        """All valid risk/method/goal combos should pass validation."""
        for risk in ["conservative", "moderate", "aggressive"]:
            r = client.post("/api/portfolio/build", json={
                "risk_tolerance": risk,
                "method": "template",
                "goal": "growth",
            })
            assert r.status_code != 422, f"Failed for risk={risk}"

    def test_build_all_methods_accepted(self, client):
        for method in ["template", "black-litterman", "hrp"]:
            r = client.post("/api/portfolio/build", json={"method": method})
            assert r.status_code != 422, f"Method {method} rejected"

    def test_build_all_goals_accepted(self, client):
        for goal in ["preservation", "income", "growth", "aggressive_growth", "retirement"]:
            r = client.post("/api/portfolio/build", json={"goal": goal})
            assert r.status_code != 422, f"Goal {goal} rejected"

    def test_build_all_horizons_accepted(self, client):
        for horizon in ["1y", "3y", "5y", "10y"]:
            r = client.post("/api/portfolio/build", json={"time_horizon": horizon})
            assert r.status_code != 422, f"Horizon {horizon} rejected"

    def test_analyze_empty_holdings_rejected(self, client):
        r = client.post("/api/portfolio/analyze", json={"holdings": []})
        assert r.status_code == 422

    def test_analyze_invalid_ticker_in_holding_rejected(self, client):
        r = client.post("/api/portfolio/analyze", json={
            "holdings": [{"ticker": "!!!bad", "shares": 10, "current_price": 100}]
        })
        assert r.status_code == 422

    def test_analyze_negative_shares_rejected(self, client):
        r = client.post("/api/portfolio/analyze", json={
            "holdings": [{"ticker": "AAPL", "shares": -5, "current_price": 100}]
        })
        assert r.status_code == 422

    def test_analyze_zero_shares_rejected(self, client):
        r = client.post("/api/portfolio/analyze", json={
            "holdings": [{"ticker": "AAPL", "shares": 0, "current_price": 100}]
        })
        assert r.status_code == 422

    def test_analyze_zero_price_rejected(self, client):
        r = client.post("/api/portfolio/analyze", json={
            "holdings": [{"ticker": "AAPL", "shares": 10, "current_price": 0}]
        })
        assert r.status_code == 422

    def test_analyze_negative_price_rejected(self, client):
        r = client.post("/api/portfolio/analyze", json={
            "holdings": [{"ticker": "AAPL", "shares": 10, "current_price": -50}]
        })
        assert r.status_code == 422

    def test_analyze_missing_ticker_rejected(self, client):
        r = client.post("/api/portfolio/analyze", json={
            "holdings": [{"shares": 10, "current_price": 100}]
        })
        assert r.status_code == 422

    def test_analyze_multiple_holdings_accepted(self, client):
        """Multiple valid holdings should pass validation."""
        r = client.post("/api/portfolio/analyze", json={
            "holdings": [
                {"ticker": "AAPL", "shares": 10, "current_price": 150},
                {"ticker": "MSFT", "shares": 5, "current_price": 400},
                {"ticker": "NVDA", "shares": 20, "current_price": 190},
            ]
        })
        assert r.status_code != 422

    def test_analyze_ticker_dot_in_holding_accepted(self, client):
        r = client.post("/api/portfolio/analyze", json={
            "holdings": [{"ticker": "BRK.B", "shares": 2, "current_price": 400}]
        })
        assert r.status_code != 422

    def test_project_invalid_years_rejected(self, client):
        r = client.post("/api/portfolio/project", json={
            "holdings": [{"ticker": "AAPL", "shares": 10, "current_price": 150}],
            "years": 50,
        })
        assert r.status_code == 422

    def test_project_zero_years_rejected(self, client):
        r = client.post("/api/portfolio/project", json={
            "holdings": [{"ticker": "AAPL", "shares": 10, "current_price": 150}],
            "years": 0,
        })
        assert r.status_code == 422

    def test_project_negative_monthly_rejected(self, client):
        r = client.post("/api/portfolio/project", json={
            "holdings": [{"ticker": "AAPL", "shares": 10, "current_price": 150}],
            "monthly_add": -500,
        })
        assert r.status_code == 422

    def test_project_boundary_max_years(self, client):
        """30 years is the max."""
        r = client.post("/api/portfolio/project", json={
            "holdings": [{"ticker": "AAPL", "shares": 10, "current_price": 150}],
            "years": 30,
        })
        assert r.status_code != 422

    def test_project_over_max_years_rejected(self, client):
        r = client.post("/api/portfolio/project", json={
            "holdings": [{"ticker": "AAPL", "shares": 10, "current_price": 150}],
            "years": 31,
        })
        assert r.status_code == 422

    def test_questionnaire_invalid_risk_rejected(self, client):
        r = client.post("/api/portfolio/questionnaire", json={
            "risk_tolerance": "extreme",
        })
        assert r.status_code == 422

    def test_questionnaire_invalid_experience_rejected(self, client):
        r = client.post("/api/portfolio/questionnaire", json={
            "experience": "expert",
        })
        assert r.status_code == 422

    def test_questionnaire_invalid_loss_reaction_rejected(self, client):
        r = client.post("/api/portfolio/questionnaire", json={
            "loss_reaction": "panic",
        })
        assert r.status_code == 422

    def test_questionnaire_invalid_income_stability_rejected(self, client):
        r = client.post("/api/portfolio/questionnaire", json={
            "income_stability": "chaotic",
        })
        assert r.status_code == 422

    def test_questionnaire_valid_defaults_accepted(self, client):
        r = client.post("/api/portfolio/questionnaire", json={})
        assert r.status_code != 422

    def test_build_no_json_body_rejected(self, client):
        r = client.post("/api/portfolio/build", content=b"not json",
                        headers={"Content-Type": "application/json"})
        assert r.status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# BACKTEST ROUTER — date validation
# ══════════════════════════════════════════════════════════════════════════════


class TestBacktestRouter:
    def test_invalid_start_date_format_rejected(self, client):
        r = client.get("/api/backtest/signal?start=not-a-date")
        assert r.status_code == 422
        assert "start date" in r.json()["detail"].lower()

    def test_invalid_end_date_format_rejected(self, client):
        r = client.get("/api/backtest/signal?end=not-a-date")
        assert r.status_code == 422
        assert "end date" in r.json()["detail"].lower()

    def test_start_after_end_rejected(self, client):
        r = client.get("/api/backtest/signal?start=2025-01-01&end=2020-01-01")
        assert r.status_code == 422
        assert "before" in r.json()["detail"].lower()

    def test_start_equals_end_rejected(self, client):
        r = client.get("/api/backtest/signal?start=2023-01-01&end=2023-01-01")
        assert r.status_code == 422

    def test_valid_date_range_not_422(self, client):
        r = client.get("/api/backtest/signal?start=2022-01-01&end=2023-01-01")
        assert r.status_code != 422

    def test_default_dates_not_422(self, client):
        """Default dates should pass validation."""
        r = client.get("/api/backtest/signal")
        assert r.status_code != 422

    def test_partial_date_rejected(self, client):
        r = client.get("/api/backtest/signal?start=2023-01")
        assert r.status_code == 422

    def test_date_with_time_rejected(self, client):
        r = client.get("/api/backtest/signal?start=2023-01-01T00:00:00")
        assert r.status_code == 422

    def test_sql_injection_in_date_rejected(self, client):
        r = client.get("/api/backtest/signal?start='; DROP TABLE--")
        assert r.status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# CROSS-CUTTING: response structure
# ══════════════════════════════════════════════════════════════════════════════


class TestSavingsResponseStructure:
    """Test that savings endpoint returns well-structured response."""

    def test_response_has_required_keys(self, client):
        r = client.post("/api/savings/project", json={
            "monthly_contribution": 500,
            "current_savings": 10000,
            "current_age": 30,
            "target_age": 65,
            "risk_level": "moderate",
        })
        assert r.status_code == 200
        body = r.json()
        assert "projections" in body
        assert "summary" in body
        assert "target" in body

    def test_response_projections_are_list(self, client):
        r = client.post("/api/savings/project", json={
            "current_age": 30, "target_age": 35,
        })
        body = r.json()
        assert isinstance(body.get("projections"), list)
        assert len(body["projections"]) > 0

    def test_response_summary_has_final_nominal(self, client):
        r = client.post("/api/savings/project", json={
            "current_age": 30, "target_age": 65,
        })
        body = r.json()
        summary = body.get("summary", {})
        assert "final_nominal" in summary
        assert summary["final_nominal"] > 0

    def test_target_met_field_exists(self, client):
        r = client.post("/api/savings/project", json={
            "monthly_contribution": 5000,
            "current_savings": 100000,
            "current_age": 30,
            "target_age": 65,
            "target_amount": 1_000_000,
        })
        body = r.json()
        target = body.get("target", {})
        assert "met" in target
        assert isinstance(target["met"], bool)


class TestHealthResponseStructure:
    def test_health_has_all_required_keys(self, client):
        body = client.get("/api/health").json()
        assert "status" in body
        assert "version" in body
        assert "cache_ready" in body


# ══════════════════════════════════════════════════════════════════════════════
# TICKER SANITIZATION — parametrized exhaustive tests
# ══════════════════════════════════════════════════════════════════════════════


class TestCrashRouterTickerPatterns:
    """Exhaustive ticker format tests against the _TICKER_RE pattern."""

    @pytest.mark.parametrize("ticker", [
        "AAPL", "MSFT", "BRK.B", "SPY", "T", "X", "NVDA", "3M",
    ])
    def test_valid_tickers_accepted(self, client, ticker):
        r = client.get(f"/api/crash/{ticker}")
        assert r.status_code != 422, f"Ticker {ticker} wrongly rejected"

    @pytest.mark.parametrize("ticker", [
        "'; DROP TABLE--",
        "<script>alert(1)</script>",
        "AAPL MSFT",  # space
        "",  # empty (caught by path, not regex)
        "A" * 11,  # 11 chars, over limit
        "../etc/passwd",
    ])
    def test_malicious_tickers_rejected(self, client, ticker):
        r = client.get(f"/api/crash/{ticker}")
        assert r.status_code in (404, 422), f"Ticker {ticker!r} wrongly accepted"


class TestNewsRouterTickerPatterns:
    """Exhaustive ticker format tests for news endpoint."""

    @pytest.mark.parametrize("ticker", [
        "'; DROP TABLE--",
        "<script>alert(1)</script>",
        "A" * 20,  # too long
        "../../../etc/passwd",
        "AAPL;rm -rf /",
    ])
    def test_malicious_tickers_rejected(self, client, ticker):
        r = client.get(f"/api/news/{ticker}")
        assert r.status_code in (404, 422), f"Ticker {ticker!r} wrongly accepted"


# ══════════════════════════════════════════════════════════════════════════════
# CONFIG INTEGRATION — verify config values are used
# ══════════════════════════════════════════════════════════════════════════════


class TestConfigIntegration:
    """Verify that config values exist and are used by routers."""

    def test_backtest_ttl_in_config(self):
        from backend.config import config
        assert "ttl_backtest" in config["cache"]
        assert config["cache"]["ttl_backtest"] == 86400

    def test_all_cache_ttls_positive(self):
        from backend.config import config
        for key, val in config["cache"].items():
            if key.startswith("ttl_"):
                assert isinstance(val, (int, float)), f"{key} is not numeric"
                assert val >= 0, f"{key} is negative"

    def test_signal_weights_sum_to_one(self):
        from backend.config import config
        weights = config["signal_weights"]
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.01, f"Signal weights sum to {total}, expected 1.0"

    def test_signal_weights_has_macro_risk(self):
        from backend.config import config
        assert "macro_risk" in config["signal_weights"]
        assert config["signal_weights"]["macro_risk"] > 0
