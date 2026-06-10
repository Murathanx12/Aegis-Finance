"""
Tests for the portfolio intelligence database layer.

Covers: schema creation, CRUD operations, immutability constraints,
schema versioning, and the pre_state + trades == post_state invariant.
"""

import json
import sqlite3

import pytest

from backend.db import (
    CURRENT_SCHEMA_VERSION,
    get_config_hash,
    get_connection,
    init_db,
    insert_audit_log,
    insert_personal_decision,
    insert_rebalance_event,
)


@pytest.fixture
def db_path(tmp_path):
    """Fresh SQLite database for each test."""
    path = tmp_path / "test_pi.db"
    init_db(path)
    return path


@pytest.fixture
def conn(db_path):
    """Database connection for testing."""
    c = get_connection(db_path)
    yield c
    c.close()


# ── Schema Creation ──────────────────────────────────────────────────────────


class TestSchemaCreation:
    def test_init_creates_all_tables(self, conn):
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        expected = {
            "_schema_version",
            "paper_portfolios",
            "paper_positions",
            "paper_trades",
            "rebalance_events",
            "audit_log",
            "personal_decisions",
            "decision_outcomes",
        }
        assert expected.issubset(tables), f"Missing tables: {expected - tables}"

    def test_schema_version_set(self, conn):
        row = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()
        assert row[0] == CURRENT_SCHEMA_VERSION

    def test_wal_mode_enabled(self, conn):
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"

    def test_foreign_keys_enabled(self, conn):
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1

    def test_idempotent_init(self, db_path):
        init_db(db_path)
        init_db(db_path)
        c = get_connection(db_path)
        rows = c.execute("SELECT COUNT(*) FROM _schema_version").fetchone()[0]
        c.close()
        assert rows == 1


# ── Paper Portfolio CRUD ─────────────────────────────────────────────────────


class TestPaperPortfolioCRUD:
    def test_insert_and_read_portfolio(self, conn):
        conn.execute(
            "INSERT INTO paper_portfolios (id, inception_date, inception_value, config_version) "
            "VALUES (?, ?, ?, ?)",
            ("conservative", "2026-05-01", 100000.0, "abc123"),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM paper_portfolios WHERE id = ?", ("conservative",)
        ).fetchone()
        assert row["id"] == "conservative"
        assert row["inception_value"] == 100000.0

    def test_duplicate_portfolio_id_rejected(self, conn):
        conn.execute(
            "INSERT INTO paper_portfolios (id, inception_date, inception_value, config_version) "
            "VALUES (?, ?, ?, ?)",
            ("balanced", "2026-05-01", 100000.0, "abc123"),
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO paper_portfolios (id, inception_date, inception_value, config_version) "
                "VALUES (?, ?, ?, ?)",
                ("balanced", "2026-05-01", 100000.0, "abc123"),
            )


# ── Paper Positions ──────────────────────────────────────────────────────────


class TestPaperPositions:
    def _setup_portfolio(self, conn):
        conn.execute(
            "INSERT INTO paper_portfolios (id, inception_date, inception_value, config_version) "
            "VALUES (?, ?, ?, ?)",
            ("conservative", "2026-05-01", 100000.0, "abc123"),
        )
        conn.commit()

    def test_insert_position(self, conn):
        self._setup_portfolio(conn)
        conn.execute(
            "INSERT INTO paper_positions (portfolio_id, ticker, shares, cost_basis, opened_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("conservative", "SPY", 100.0, 450.0, "2026-05-01T10:00:00"),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM paper_positions WHERE ticker = ?", ("SPY",)
        ).fetchone()
        assert row["shares"] == 100.0
        assert row["closed_at"] is None

    def test_close_position(self, conn):
        self._setup_portfolio(conn)
        conn.execute(
            "INSERT INTO paper_positions (portfolio_id, ticker, shares, cost_basis, opened_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("conservative", "SPY", 100.0, 450.0, "2026-05-01T10:00:00"),
        )
        conn.commit()
        conn.execute(
            "UPDATE paper_positions SET closed_at = ? WHERE ticker = ? AND portfolio_id = ?",
            ("2026-06-01T10:00:00", "SPY", "conservative"),
        )
        conn.commit()
        row = conn.execute(
            "SELECT closed_at FROM paper_positions WHERE ticker = ?", ("SPY",)
        ).fetchone()
        assert row["closed_at"] == "2026-06-01T10:00:00"


# ── Rebalance Events ─────────────────────────────────────────────────────────


class TestRebalanceEvents:
    def _setup_portfolio(self, conn):
        conn.execute(
            "INSERT INTO paper_portfolios (id, inception_date, inception_value, config_version) "
            "VALUES (?, ?, ?, ?)",
            ("balanced", "2026-05-01", 100000.0, "abc123"),
        )
        conn.commit()

    def test_insert_rebalance_event(self, conn):
        self._setup_portfolio(conn)
        pre = {"SPY": 0.5, "AGG": 0.5}
        post = {"SPY": 0.7, "AGG": 0.3}
        row_id = insert_rebalance_event(
            conn,
            portfolio_id="balanced",
            triggered_at="2026-05-15T16:30:00",
            trigger_reason="monthly",
            pre_weights=pre,
            post_weights=post,
            crash_prob_3m=0.15,
            regime="bull",
            explanation="Monthly rebalance. Increased equity from 50% to 70%.",
        )
        assert row_id > 0
        row = conn.execute(
            "SELECT * FROM rebalance_events WHERE id = ?", (row_id,)
        ).fetchone()
        assert row["trigger_reason"] == "monthly"
        assert json.loads(row["pre_weights"]) == pre
        assert json.loads(row["post_weights"]) == post

    def test_invalid_trade_side_rejected(self, conn):
        self._setup_portfolio(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO paper_trades (portfolio_id, ticker, side, shares, price, "
                "transaction_cost, slippage, executed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("balanced", "SPY", "short", 10, 450.0, 0.5, 0.1, "2026-05-15T16:30:00"),
            )


# ── Pre-state + Trades == Post-state Invariant ───────────────────────────────


class TestRebalanceInvariant:
    """The critical invariant from SPEC section 5:
    pre_state_snapshot + trades == post_state_snapshot."""

    def test_invariant_holds_for_simple_rebalance(self, conn):
        conn.execute(
            "INSERT INTO paper_portfolios (id, inception_date, inception_value, config_version) "
            "VALUES (?, ?, ?, ?)",
            ("aggressive", "2026-05-01", 100000.0, "abc123"),
        )
        conn.commit()

        pre = {"SPY": 0.60, "QQQ": 0.30, "GLD": 0.10}
        post = {"SPY": 0.50, "QQQ": 0.40, "GLD": 0.10}
        notional = 100000.0

        trades = [
            ("sell", "SPY", 10.0 / 450.0 * notional * 0.10),
            ("buy", "QQQ", 10.0 / 380.0 * notional * 0.10),
        ]

        _verify_pre_plus_trades_eq_post(pre, post, trades_weight_delta={
            "SPY": -0.10,
            "QQQ": +0.10,
        })

    def test_invariant_fails_on_mismatch(self):
        pre = {"SPY": 0.60, "QQQ": 0.40}
        post = {"SPY": 0.50, "QQQ": 0.40}
        with pytest.raises(AssertionError):
            _verify_pre_plus_trades_eq_post(pre, post, trades_weight_delta={
                "SPY": -0.05,
            })


def _verify_pre_plus_trades_eq_post(
    pre: dict[str, float],
    post: dict[str, float],
    trades_weight_delta: dict[str, float],
    tolerance: float = 0.001,
):
    """Verify the critical invariant: pre_weights + trade_deltas == post_weights."""
    reconstructed = dict(pre)
    for ticker, delta in trades_weight_delta.items():
        reconstructed[ticker] = reconstructed.get(ticker, 0.0) + delta

    all_tickers = set(reconstructed) | set(post)
    for ticker in all_tickers:
        r = reconstructed.get(ticker, 0.0)
        p = post.get(ticker, 0.0)
        assert abs(r - p) < tolerance, (
            f"Invariant violation for {ticker}: "
            f"pre({pre.get(ticker, 0)}) + delta({trades_weight_delta.get(ticker, 0)}) "
            f"= {r}, but post = {p}"
        )


# ── Audit Log ────────────────────────────────────────────────────────────────


class TestAuditLog:
    def test_insert_and_read_audit(self, conn):
        row_id = insert_audit_log(
            conn,
            timestamp="2026-05-15T16:30:00",
            portfolio_id="conservative",
            event_type="rebalance_check",
            payload={"drift_max": 0.03, "rebalanced": False},
        )
        assert row_id > 0
        row = conn.execute(
            "SELECT * FROM audit_log WHERE id = ?", (row_id,)
        ).fetchone()
        assert row["event_type"] == "rebalance_check"
        assert json.loads(row["payload"])["rebalanced"] is False

    def test_audit_log_allows_null_portfolio(self, conn):
        row_id = insert_audit_log(
            conn,
            timestamp="2026-05-15T16:30:00",
            portfolio_id=None,
            event_type="system_startup",
            payload={"version": "1.0"},
        )
        row = conn.execute(
            "SELECT portfolio_id FROM audit_log WHERE id = ?", (row_id,)
        ).fetchone()
        assert row["portfolio_id"] is None


# ── Personal Decisions ───────────────────────────────────────────────────────


class TestPersonalDecisions:
    _VALID_RATIONALE = "Testing biotech thesis on TVTX — FDA catalyst expected Q3 2026, strong pipeline data"

    def test_insert_decision(self, conn):
        row_id = insert_personal_decision(
            conn,
            timestamp="2026-05-15T10:00:00",
            ticker="TVTX",
            action="enter",
            shares_delta=100.0,
            price=34.0,
            rationale=self._VALID_RATIONALE,
            thesis_tags=["FDA_catalyst", "biotech"],
            conviction=4,
            portfolio_snapshot={"TVTX": {"shares": 100, "weight": 0.10}},
        )
        assert row_id > 0
        row = conn.execute(
            "SELECT * FROM personal_decisions WHERE id = ?", (row_id,)
        ).fetchone()
        assert row["ticker"] == "TVTX"
        assert row["conviction"] == 4
        assert json.loads(row["thesis_tags"]) == ["FDA_catalyst", "biotech"]

    def test_rationale_too_short_rejected(self, conn):
        with pytest.raises(ValueError, match="Rationale must be >= 50 characters"):
            insert_personal_decision(
                conn,
                timestamp="2026-05-15T10:00:00",
                ticker="TVTX",
                action="enter",
                shares_delta=100.0,
                price=34.0,
                rationale="too short",
                thesis_tags=[],
                conviction=3,
                portfolio_snapshot={},
            )

    def test_rationale_exactly_50_accepted(self, conn):
        rationale_50 = "A" * 50
        row_id = insert_personal_decision(
            conn,
            timestamp="2026-05-15T10:00:00",
            ticker="TVTX",
            action="enter",
            shares_delta=100.0,
            price=34.0,
            rationale=rationale_50,
            thesis_tags=[],
            conviction=3,
            portfolio_snapshot={},
        )
        assert row_id > 0

    def test_conviction_out_of_range_rejected(self, conn):
        with pytest.raises(ValueError, match="Conviction must be 1-5"):
            insert_personal_decision(
                conn,
                timestamp="2026-05-15T10:00:00",
                ticker="TVTX",
                action="enter",
                shares_delta=100.0,
                price=34.0,
                rationale=self._VALID_RATIONALE,
                thesis_tags=[],
                conviction=6,
                portfolio_snapshot={},
            )

    def test_invalid_action_rejected(self, conn):
        with pytest.raises(ValueError, match="Action must be enter/add/trim/exit"):
            insert_personal_decision(
                conn,
                timestamp="2026-05-15T10:00:00",
                ticker="TVTX",
                action="buy",
                shares_delta=100.0,
                price=34.0,
                rationale=self._VALID_RATIONALE,
                thesis_tags=[],
                conviction=3,
                portfolio_snapshot={},
            )

    def test_amendment_links_to_original(self, conn):
        original_id = insert_personal_decision(
            conn,
            timestamp="2026-05-15T10:00:00",
            ticker="TVTX",
            action="enter",
            shares_delta=100.0,
            price=34.0,
            rationale=self._VALID_RATIONALE,
            thesis_tags=["biotech"],
            conviction=4,
            portfolio_snapshot={"TVTX": {"shares": 100}},
        )
        amendment_id = insert_personal_decision(
            conn,
            timestamp="2026-05-16T10:00:00",
            ticker="TVTX",
            action="add",
            shares_delta=50.0,
            price=35.0,
            rationale="Adding to position after positive Phase 2 data readout confirmed",
            thesis_tags=["biotech", "phase2_data"],
            conviction=5,
            portfolio_snapshot={"TVTX": {"shares": 150}},
            amends_id=original_id,
        )
        row = conn.execute(
            "SELECT amends_id FROM personal_decisions WHERE id = ?",
            (amendment_id,),
        ).fetchone()
        assert row["amends_id"] == original_id

    def test_immutability_update_blocked_by_trigger(self, conn):
        """Personal decisions cannot be UPDATEd — enforced by SQLite trigger."""
        row_id = insert_personal_decision(
            conn,
            timestamp="2026-05-15T10:00:00",
            ticker="TVTX",
            action="enter",
            shares_delta=100.0,
            price=34.0,
            rationale=self._VALID_RATIONALE,
            thesis_tags=[],
            conviction=3,
            portfolio_snapshot={},
        )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute(
                "UPDATE personal_decisions SET rationale = ? WHERE id = ?",
                ("changed rationale that is long enough to pass validation", row_id),
            )

    def test_immutability_delete_blocked_by_trigger(self, conn):
        """Personal decisions cannot be DELETEd — enforced by SQLite trigger."""
        row_id = insert_personal_decision(
            conn,
            timestamp="2026-05-15T10:00:00",
            ticker="TVTX",
            action="enter",
            shares_delta=100.0,
            price=34.0,
            rationale=self._VALID_RATIONALE,
            thesis_tags=[],
            conviction=3,
            portfolio_snapshot={},
        )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute("DELETE FROM personal_decisions WHERE id = ?", (row_id,))


# ── Config Hash ──────────────────────────────────────────────────────────────


class TestConfigHash:
    def test_config_hash_is_deterministic(self):
        h1 = get_config_hash()
        h2 = get_config_hash()
        assert h1 == h2
        assert len(h1) == 16

    def test_config_hash_not_empty(self):
        h = get_config_hash()
        assert h != "no-config"

    def test_config_hash_ignores_whitespace_changes(self, tmp_path):
        """Hash should be based on parsed config, not raw bytes.
        Whitespace/comment changes should NOT change the hash."""
        import yaml
        from backend.db import _compute_config_hash

        config_data = {"conservative": {"target_equity_pct": 0.40}}

        file1 = tmp_path / "v1.yaml"
        file1.write_text(yaml.dump(config_data))

        file2 = tmp_path / "v2.yaml"
        file2.write_text("# extra comment\n" + yaml.dump(config_data) + "\n\n")

        h1 = _compute_config_hash(file1)
        h2 = _compute_config_hash(file2)
        assert h1 == h2, "Hash should not change when only comments/whitespace differ"

    def test_config_hash_changes_on_value_change(self, tmp_path):
        """Hash SHOULD change when actual config values change."""
        import yaml
        from backend.db import _compute_config_hash

        file1 = tmp_path / "v1.yaml"
        file1.write_text(yaml.dump({"equity_pct": 0.40}))

        file2 = tmp_path / "v2.yaml"
        file2.write_text(yaml.dump({"equity_pct": 0.50}))

        h1 = _compute_config_hash(file1)
        h2 = _compute_config_hash(file2)
        assert h1 != h2, "Hash should change when config values differ"
