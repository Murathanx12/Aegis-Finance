"""F-017 builder absorbs: contradiction warnings + probability-of-target."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.portfolio_engine import PortfolioEngine


class TestContradictionWarnings:
    def test_short_horizon_aggressive_flags(self):
        r = PortfolioEngine.build_portfolio(
            risk_tolerance="aggressive", investment_amount=10_000,
            time_horizon="1y", method="template")
        assert r["warnings"], "1y + aggressive must produce warnings"
        joined = " ".join(r["warnings"]).lower()
        assert "opposite directions" in joined
        assert "tilted toward bonds" in joined  # glide-path disclosed

    def test_max_growth_3y_flags(self):
        r = PortfolioEngine.build_portfolio(
            risk_tolerance="max_growth", investment_amount=10_000,
            time_horizon="3y", method="template")
        assert r["warnings"]

    def test_consistent_inputs_clean(self):
        r = PortfolioEngine.build_portfolio(
            risk_tolerance="moderate", investment_amount=10_000,
            time_horizon="10y", method="template")
        assert r["warnings"] == []

    def test_no_advice_language_in_warnings(self):
        r = PortfolioEngine.build_portfolio(
            risk_tolerance="aggressive", investment_amount=10_000,
            time_horizon="1y", method="template")
        for w in r["warnings"]:
            low = w.lower()
            assert "you should" not in low and "we recommend" not in low


class TestProjectRequestTarget:
    def test_request_model_accepts_target(self):
        from backend.routers.portfolio import ProjectRequest
        req = ProjectRequest(
            holdings=[{"ticker": "SPY", "shares": 10, "current_price": 500.0}],
            years=5, monthly_add=100, target_amount=50_000)
        assert req.target_amount == 50_000

    def test_target_optional(self):
        from backend.routers.portfolio import ProjectRequest
        req = ProjectRequest(
            holdings=[{"ticker": "SPY", "shares": 10, "current_price": 500.0}])
        assert req.target_amount is None
