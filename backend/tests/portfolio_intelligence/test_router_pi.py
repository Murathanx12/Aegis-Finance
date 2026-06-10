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


class TestReferenceStateColdInit:
    """Phase 5b regression: state endpoint must not 500 on a fresh DB.

    Original bug: run_reference_check wrote to rebalance_events (FK to
    paper_portfolios.id) before initialize_lane was ever called.
    """

    def test_cold_call_returns_200(self, tmp_path, monkeypatch):
        # Point DB at a fresh tmp file. We can't easily inject db_path through
        # the FastAPI route (run_reference_check has db_path=None default), so
        # we patch the DB_PATH module-level constant for this test.
        from backend import db as db_module
        from backend.services.portfolio_intelligence import reference_engine

        fresh_db = tmp_path / "fresh.db"
        monkeypatch.setattr(db_module, "DB_PATH", fresh_db)

        # init_db on the fresh path
        db_module.init_db(fresh_db)

        # Sanity: parent row should NOT exist yet
        conn = db_module.get_connection(fresh_db)
        try:
            row = conn.execute(
                "SELECT id FROM paper_portfolios WHERE id = 'conservative'"
            ).fetchone()
        finally:
            conn.close()
        assert row is None, "fixture: parent row should not exist before test"

        # Now call reference engine — should auto-initialize
        snapshot = reference_engine.run_reference_check("conservative")
        assert snapshot.portfolio_id == "conservative"

        # Parent row must exist now
        conn = db_module.get_connection(fresh_db)
        try:
            row = conn.execute(
                "SELECT id FROM paper_portfolios WHERE id = 'conservative'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None


class TestHistoryEndpointShape:
    """Phase 5b regression: history must return wrapper shape, not raw list."""

    def test_period_param_accepted(self):
        # Should not 422 — period is the documented param
        response = client.get("/api/pi/reference/conservative/history?period=1Y")
        assert response.status_code == 200, response.text

    def test_invalid_period_rejected(self):
        response = client.get("/api/pi/reference/conservative/history?period=BOGUS")
        assert response.status_code == 422

    def test_response_shape(self):
        response = client.get("/api/pi/reference/conservative/history?period=1Y")
        assert response.status_code == 200
        body = response.json()
        for f in ("portfolio_id", "period", "equity_curve", "rebalance_log", "has_rebalance_events"):
            assert f in body, f"missing field: {f}"
        assert body["portfolio_id"] == "conservative"
        assert body["period"] == "1Y"
        assert isinstance(body["equity_curve"], list)
        assert isinstance(body["rebalance_log"], list)
        assert isinstance(body["has_rebalance_events"], bool)


class TestExplainEndpointShape:
    """Phase 5b regression: explain must return consistent shape, not {message} when empty."""

    def test_response_shape(self):
        response = client.get("/api/pi/reference/conservative/explain")
        assert response.status_code == 200
        body = response.json()
        for f in ("portfolio_id", "explanation", "last_rebalance_date", "has_rebalance_events"):
            assert f in body, f"missing field: {f}"
        assert body["portfolio_id"] == "conservative"
        assert isinstance(body["explanation"], str) and len(body["explanation"]) > 0


class TestHistoryNavWiring:
    """V2 P0 #1: equity curve must come from paper_nav, not synthetic seeding.

    The old stub seeded inception_value at each rebalance date — a fake flat
    line indistinguishable from real data. Now: real NAV rows with per-point
    config_version, and an explicit has_nav_data=false empty state.
    """

    def _seed(self, tmp_path, monkeypatch, nav_rows):
        from backend import db as db_module
        from backend.config import paper_portfolios
        from backend.services.portfolio_intelligence.reference_engine import initialize_lane
        from backend.services.portfolio_intelligence.rules import _get_sleeve_tickers

        fresh_db = tmp_path / "nav.db"
        monkeypatch.setattr(db_module, "DB_PATH", fresh_db)
        db_module.init_db(fresh_db)

        sleeves = _get_sleeve_tickers(paper_portfolios["universe"])
        prices = {t: 100.0 for t in
                  sleeves["equity"] + sleeves["bond"] + sleeves["alternative"]}
        initialize_lane("balanced", db_path=fresh_db, prices=prices)

        conn = db_module.get_connection(fresh_db)
        try:
            for d, nav in nav_rows:
                db_module.insert_nav(conn, "balanced", d, nav, "cfgv1", d + "T21:00:00")
        finally:
            conn.close()

    def test_curve_returns_real_nav_rows(self, tmp_path, monkeypatch):
        self._seed(tmp_path, monkeypatch,
                   [("2026-06-08", 100_000.0), ("2026-06-09", 100_750.5)])
        response = client.get("/api/pi/reference/balanced/history?period=ALL")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["has_nav_data"] is True
        assert [(p["date"], p["value"]) for p in body["equity_curve"]] == [
            ("2026-06-08", 100_000.0), ("2026-06-09", 100_750.5),
        ]
        assert all(p["config_version"] == "cfgv1" for p in body["equity_curve"])
        assert body["inception_value"] == 100_000.0
        assert body["inception_date"] is not None

    def test_empty_lane_is_explicit_no_data(self, tmp_path, monkeypatch):
        self._seed(tmp_path, monkeypatch, [])
        response = client.get("/api/pi/reference/balanced/history?period=ALL")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["equity_curve"] == [], "no synthetic points allowed"
        assert body["has_nav_data"] is False

    def test_period_filter_excludes_old_rows(self, tmp_path, monkeypatch):
        from datetime import date, timedelta

        recent = (date.today() - timedelta(days=2)).isoformat()
        self._seed(tmp_path, monkeypatch,
                   [("2020-01-01", 90_000.0), (recent, 101_000.0)])
        response = client.get("/api/pi/reference/balanced/history?period=1M")
        assert response.status_code == 200, response.text
        body = response.json()
        assert [p["date"] for p in body["equity_curve"]] == [recent]
        assert isinstance(body["has_rebalance_events"], bool)
        # last_rebalance_date is Optional[str] — may be None or string

    def test_unknown_lane_404(self):
        response = client.get("/api/pi/reference/bogus/explain")
        assert response.status_code == 404


class TestCompareEndpointShape:
    """Phase 5b regression: compare must return {lanes, benchmarks, period, start_date, end_date}."""

    @patch("backend.services.portfolio_intelligence.replay.ReplayEngine.run")
    @patch("backend.routers.portfolio_intelligence._compute_benchmark_metrics")
    def test_response_shape(self, mock_bench, mock_engine_run):
        # Stub the heavy operations
        mock_result = MagicMock()
        mock_result.metrics = MetricPack(
            total_return=0.5, annualized_return=0.1, annualized_volatility=0.15,
            sharpe_ratio=0.6, max_drawdown=-0.2,
        )
        mock_engine_run.return_value = mock_result

        mock_bench.return_value = MetricPack(
            total_return=0.4, annualized_return=0.08, annualized_volatility=0.18,
            sharpe_ratio=0.5, max_drawdown=-0.25,
        )

        response = client.get("/api/pi/compare?ids=conservative,balanced&period=1Y")
        assert response.status_code == 200
        body = response.json()
        for f in ("lanes", "benchmarks", "period", "start_date", "end_date"):
            assert f in body, f"missing field: {f}"
        assert "conservative" in body["lanes"]
        assert "balanced" in body["lanes"]
        assert "SPY" in body["benchmarks"]
        assert "AGG" in body["benchmarks"]
        assert "60-40" in body["benchmarks"]
        assert body["period"] == "1Y"

    def test_invalid_period_rejected(self):
        response = client.get("/api/pi/compare?period=BOGUS")
        assert response.status_code == 422
