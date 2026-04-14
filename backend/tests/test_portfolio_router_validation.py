"""Tests for portfolio router input validation."""

import pytest
from pydantic import ValidationError

from backend.routers.portfolio import RiskContribRequest


class TestRiskContribValidation:
    """Regression tests for tickers/weights validation."""

    def test_valid_request(self):
        req = RiskContribRequest(tickers=["AAPL", "MSFT"], weights=[0.6, 0.4])
        assert len(req.tickers) == len(req.weights)

    def test_mismatched_lengths_rejected(self):
        """Regression: mismatched tickers and weights must be rejected."""
        with pytest.raises(ValidationError, match="must match"):
            RiskContribRequest(tickers=["AAPL", "MSFT", "GOOGL"], weights=[0.5, 0.5])

    def test_negative_weights_rejected(self):
        """Regression: negative weights must be rejected."""
        with pytest.raises(ValidationError, match="non-negative"):
            RiskContribRequest(tickers=["AAPL", "MSFT"], weights=[0.6, -0.4])

    def test_zero_weights_accepted(self):
        """Zero weights are valid (means exclude from portfolio)."""
        req = RiskContribRequest(tickers=["AAPL", "MSFT"], weights=[1.0, 0.0])
        assert req.weights == [1.0, 0.0]
