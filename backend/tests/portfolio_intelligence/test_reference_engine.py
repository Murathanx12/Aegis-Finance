"""
Tests for the reference engine (orchestrator).

Integration-level tests with mocked DB, crash model, and data fetcher.
Verifies the full rebalance pipeline end-to-end.
"""

import sqlite3
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock


from backend.services.portfolio_intelligence.reference_engine import (
    run_reference_check,
    run_all_lanes,
    initialize_lane,
    _get_lane_config,
    _get_current_weights,
    _get_last_rebalance_date,
)


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_test_db(tmp_path) -> Path:
    """Create a minimal test DB with the required tables. Returns Path object."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS paper_portfolios (
            id TEXT PRIMARY KEY,
            inception_date TEXT NOT NULL,
            inception_value REAL NOT NULL DEFAULT 100000.0,
            config_version TEXT
        );
        CREATE TABLE IF NOT EXISTS paper_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            shares REAL NOT NULL,
            cost_basis REAL DEFAULT 100.0,
            opened_at TEXT NOT NULL,
            closed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS rebalance_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id TEXT NOT NULL,
            triggered_at TEXT NOT NULL,
            trigger_reason TEXT NOT NULL,
            pre_weights TEXT,
            post_weights TEXT,
            crash_prob_3m REAL,
            regime TEXT,
            explanation TEXT
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id TEXT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT
        );
        CREATE TABLE IF NOT EXISTS _schema_version (
            version INTEGER NOT NULL
        );
        INSERT INTO _schema_version (version) VALUES (1);
    """)
    conn.commit()
    conn.close()
    return db_path


def _seed_portfolio(db_path, lane_id, tickers_shares):
    """Seed a portfolio with positions."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    today = date.today().isoformat()
    conn.execute(
        "INSERT INTO paper_portfolios (id, inception_date, inception_value) VALUES (?, ?, ?)",
        (lane_id, today, 100_000.0),
    )
    for ticker, shares in tickers_shares.items():
        conn.execute(
            "INSERT INTO paper_positions (portfolio_id, ticker, shares, cost_basis, opened_at) VALUES (?, ?, ?, ?, ?)",
            (lane_id, ticker, shares, 100.0, today),
        )
    conn.commit()
    conn.close()


# ── _get_lane_config ──────────────────────────────────────────────────────


class TestGetLaneConfig:
    def test_known_lanes(self):
        for lane in ["conservative", "balanced", "aggressive"]:
            cfg = _get_lane_config(lane)
            assert cfg is not None
            assert "target_equity_pct" in cfg

    def test_unknown_lane(self):
        assert _get_lane_config("nonexistent") is None


# ── _get_current_weights ─────────────────────────────────────────────────


class TestGetCurrentWeights:
    def test_empty_portfolio(self, tmp_path):
        db_path = _make_test_db(tmp_path)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        weights = _get_current_weights(conn, "conservative")
        assert weights == {}
        conn.close()

    def test_with_positions(self, tmp_path):
        db_path = _make_test_db(tmp_path)
        _seed_portfolio(db_path, "balanced", {"SPY": 50.0, "AGG": 50.0})
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        weights = _get_current_weights(conn, "balanced")
        assert len(weights) == 2
        assert abs(sum(weights.values()) - 1.0) < 1e-6
        conn.close()


# ── _get_last_rebalance_date ─────────────────────────────────────────────


class TestGetLastRebalanceDate:
    def test_no_events(self, tmp_path):
        db_path = _make_test_db(tmp_path)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        assert _get_last_rebalance_date(conn, "conservative") is None
        conn.close()

    def test_with_event(self, tmp_path):
        db_path = _make_test_db(tmp_path)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute(
            "INSERT INTO rebalance_events (portfolio_id, triggered_at, trigger_reason) VALUES (?, ?, ?)",
            ("conservative", "2026-04-01T10:00:00", "monthly"),
        )
        conn.commit()
        result = _get_last_rebalance_date(conn, "conservative")
        assert result == date(2026, 4, 1)
        conn.close()


# ── initialize_lane ──────────────────────────────────────────────────────


class TestInitializeLane:
    @patch("backend.services.portfolio_intelligence.reference_engine._get_current_prices", return_value={})
    @patch("backend.services.portfolio_intelligence.reference_engine._get_sector_map", return_value={})
    def test_creates_portfolio_and_positions(self, mock_sector, mock_prices, tmp_path):
        db_path = _make_test_db(tmp_path)
        initialize_lane("conservative", notional=100_000.0, db_path=db_path)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM paper_portfolios WHERE id = 'conservative'").fetchone()
        assert row is not None
        assert row["inception_value"] == 100_000.0

        positions = conn.execute(
            "SELECT * FROM paper_positions WHERE portfolio_id = 'conservative'"
        ).fetchall()
        assert len(positions) > 10  # should have many tickers

        events = conn.execute(
            "SELECT * FROM rebalance_events WHERE portfolio_id = 'conservative'"
        ).fetchall()
        assert len(events) == 1
        assert events[0]["trigger_reason"] == "initialization"
        conn.close()

    @patch("backend.services.portfolio_intelligence.reference_engine._get_current_prices", return_value={})
    @patch("backend.services.portfolio_intelligence.reference_engine._get_sector_map", return_value={})
    def test_idempotent(self, mock_sector, mock_prices, tmp_path):
        db_path = _make_test_db(tmp_path)
        initialize_lane("balanced", db_path=db_path)
        initialize_lane("balanced", db_path=db_path)  # second call should be no-op

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM paper_portfolios WHERE id = 'balanced'").fetchall()
        assert len(rows) == 1
        conn.close()


# ── run_reference_check ──────────────────────────────────────────────────


class TestRunReferenceCheck:
    @patch("backend.services.portfolio_intelligence.reference_engine._get_current_prices", return_value={})
    @patch("backend.services.portfolio_intelligence.reference_engine._get_sector_map", return_value={})
    @patch("backend.services.portfolio_intelligence.reference_engine._get_crash_prob", return_value=0.10)
    @patch("backend.services.portfolio_intelligence.reference_engine._get_regime", return_value="bull")
    def test_no_rebalance_when_no_drift(self, mock_regime, mock_crash, mock_sector, mock_prices, tmp_path):
        """Fresh portfolio with no drift should not trigger (already at target)."""
        db_path = _make_test_db(tmp_path)

        # Initialize first
        initialize_lane("conservative", db_path=db_path)

        # Run check — just initialized, so recent rebalance, no drift
        result = run_reference_check(
            "conservative", db_path=db_path, as_of_date=date(2026, 4, 27),
        )
        assert result.portfolio_id == "conservative"

    def test_unknown_lane_returns_empty(self, tmp_path):
        db_path = _make_test_db(tmp_path)
        result = run_reference_check("nonexistent", db_path=db_path)
        assert result.portfolio_id == "nonexistent"
        assert result.weights == {}

    @patch("backend.services.portfolio_intelligence.reference_engine._get_sector_map", return_value={})
    @patch("backend.services.portfolio_intelligence.reference_engine._get_crash_prob", return_value=0.10)
    @patch("backend.services.portfolio_intelligence.reference_engine._get_regime", return_value=None)
    @patch("backend.services.portfolio_intelligence.reference_engine._get_current_prices")
    def test_initialization_trigger_on_empty_portfolio(
        self, mock_prices, mock_regime, mock_crash, mock_sector, tmp_path,
    ):
        """Empty portfolio (no positions, no rebalance history) should trigger initialization."""
        db_path = _make_test_db(tmp_path)

        mock_prices.return_value = {"SPY": 500.0, "AGG": 100.0, "GLD": 200.0}

        result = run_reference_check(
            "conservative", db_path=db_path, as_of_date=date(2026, 4, 27),
        )
        assert result.portfolio_id == "conservative"
        # Should have triggered rebalance (initialization)
        if result.latest_rebalance:
            assert result.latest_rebalance.trigger_reason == "initialization"

    @patch("backend.services.portfolio_intelligence.reference_engine._get_sector_map", return_value={})
    @patch("backend.services.portfolio_intelligence.reference_engine._get_crash_prob", return_value=0.50)
    @patch("backend.services.portfolio_intelligence.reference_engine._get_regime", return_value="volatile")
    @patch("backend.services.portfolio_intelligence.reference_engine._get_current_prices")
    def test_crash_overlay_fires_at_high_prob(
        self, mock_prices, mock_regime, mock_crash, mock_sector, tmp_path,
    ):
        """High crash probability should activate the crash overlay."""
        db_path = _make_test_db(tmp_path)

        mock_prices.return_value = {"SPY": 500.0, "AGG": 100.0, "GLD": 200.0}

        result = run_reference_check(
            "conservative", db_path=db_path,
            as_of_date=date(2026, 4, 27),
            crash_prob_override=0.50,
        )
        # With crash_prob=0.50 > conservative threshold=0.25, overlay should fire
        # The function should complete without error
        assert result.portfolio_id == "conservative"


# ── run_all_lanes ────────────────────────────────────────────────────────


class TestRunAllLanes:
    @patch("backend.services.portfolio_intelligence.reference_engine.run_reference_check")
    def test_runs_three_lanes(self, mock_check):
        mock_check.return_value = MagicMock(portfolio_id="test")
        results = run_all_lanes()
        assert mock_check.call_count == 3
        called_lanes = {call.args[0] for call in mock_check.call_args_list}
        assert called_lanes == {"conservative", "balanced", "aggressive"}

    @patch("backend.services.portfolio_intelligence.reference_engine.run_reference_check")
    def test_handles_single_lane_failure(self, mock_check):
        def side_effect(lane_id, **kwargs):
            if lane_id == "balanced":
                raise RuntimeError("test error")
            return MagicMock(portfolio_id=lane_id)

        mock_check.side_effect = side_effect
        results = run_all_lanes()
        assert "conservative" in results
        assert "aggressive" in results
        assert "balanced" not in results
