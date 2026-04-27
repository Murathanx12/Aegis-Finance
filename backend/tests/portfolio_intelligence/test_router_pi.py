"""
Tests for the portfolio intelligence router.

Uses FastAPI TestClient with mocked analyzer to avoid network calls.
"""

from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.schemas.portfolio_intelligence import (
    MetricPack,
    RiskFlag,
    SnapshotResponse,
)


client = TestClient(app)

_MOCK_SNAPSHOT = SnapshotResponse(
    portfolio_id="real",
    date="2026-04-26",
    weights={"AAPL": 0.5, "MSFT": 0.5},
    metrics=MetricPack(
        total_return=0.15,
        annualized_return=0.07,
        annualized_volatility=0.12,
        sharpe_ratio=0.58,
        max_drawdown=-0.08,
    ),
    flags=[
        RiskFlag(
            flag_type="single_name",
            severity="warning",
            message="AAPL is 50% of portfolio",
        ),
    ],
)


class TestAnalyzeEndpoint:
    @patch("backend.routers.portfolio_intelligence.analyze_portfolio")
    def test_valid_request(self, mock_analyze):
        mock_analyze.return_value = _MOCK_SNAPSHOT
        response = client.post("/api/pi/real-portfolio/analyze", json={
            "holdings": [
                {"ticker": "AAPL", "shares": 10.0},
                {"ticker": "MSFT", "shares": 20.0},
            ],
        })
        assert response.status_code == 200
        data = response.json()
        assert data["portfolio_id"] == "real"
        assert "metrics" in data
        assert "flags" in data

    def test_empty_holdings_rejected(self):
        response = client.post("/api/pi/real-portfolio/analyze", json={
            "holdings": [],
        })
        assert response.status_code == 422

    def test_invalid_ticker_rejected(self):
        response = client.post("/api/pi/real-portfolio/analyze", json={
            "holdings": [{"ticker": "THIS_IS_WAY_TOO_LONG_TICKER", "shares": 10.0}],
        })
        assert response.status_code == 422

    def test_zero_shares_rejected(self):
        response = client.post("/api/pi/real-portfolio/analyze", json={
            "holdings": [{"ticker": "AAPL", "shares": 0}],
        })
        assert response.status_code == 422

    def test_negative_shares_rejected(self):
        response = client.post("/api/pi/real-portfolio/analyze", json={
            "holdings": [{"ticker": "AAPL", "shares": -10.0}],
        })
        assert response.status_code == 422

    @patch("backend.routers.portfolio_intelligence.analyze_portfolio")
    def test_response_shape(self, mock_analyze):
        mock_analyze.return_value = _MOCK_SNAPSHOT
        response = client.post("/api/pi/real-portfolio/analyze", json={
            "holdings": [{"ticker": "AAPL", "shares": 10.0}],
        })
        data = response.json()
        metrics = data["metrics"]
        assert "total_return" in metrics
        assert "annualized_return" in metrics
        assert "annualized_volatility" in metrics
        assert "max_drawdown" in metrics
        assert "sector_exposure" in metrics
        assert "factor_exposure" in metrics

    @patch("backend.routers.portfolio_intelligence.analyze_portfolio")
    def test_flags_in_response(self, mock_analyze):
        mock_analyze.return_value = _MOCK_SNAPSHOT
        response = client.post("/api/pi/real-portfolio/analyze", json={
            "holdings": [{"ticker": "AAPL", "shares": 10.0}],
        })
        data = response.json()
        assert len(data["flags"]) == 1
        assert data["flags"][0]["flag_type"] == "single_name"

    def test_missing_body_rejected(self):
        response = client.post("/api/pi/real-portfolio/analyze")
        assert response.status_code == 422

    @patch("backend.routers.portfolio_intelligence.analyze_portfolio")
    def test_ticker_uppercased(self, mock_analyze):
        mock_analyze.return_value = _MOCK_SNAPSHOT
        response = client.post("/api/pi/real-portfolio/analyze", json={
            "holdings": [{"ticker": "aapl", "shares": 10.0}],
        })
        assert response.status_code == 200

    @patch("backend.routers.portfolio_intelligence.analyze_portfolio")
    def test_server_error_returns_500(self, mock_analyze):
        mock_analyze.side_effect = RuntimeError("boom")
        response = client.post("/api/pi/real-portfolio/analyze", json={
            "holdings": [{"ticker": "AAPL", "shares": 10.0}],
        })
        assert response.status_code == 500
