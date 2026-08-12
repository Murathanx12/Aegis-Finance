"""F-017 builder absorbs: contradiction warnings + probability-of-target."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.portfolio_engine import PortfolioEngine


# MARKED SLOW 2026-08-12. These call build_portfolio, which fetches live prices
# through yfinance. They were never offline tests — they only looked like it
# because the fast suite's network guard could not see curl_cffi (yfinance's
# transport), so the fetches went through unnoticed. Closing that hole
# (conftest.py + test_network_guard.py) exposed seven such tests across three
# files, and also cut the fast suite from ~20 min to ~2 min, which is how much
# of its runtime was network I/O that was never supposed to be there.
#
# `slow` is the honest classification, not a workaround: these are integration
# tests and the house rule is explicit — a network call in a unit test is a bug,
# so mark it slow or mock it. Mocking is the better end state (the assertions
# are about warning TEXT, not about prices), but that is a rewrite of the
# fixtures rather than a reclassification, and inventing price fixtures at 2am
# to keep a green tick is how tests stop testing anything.
@pytest.mark.slow
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
