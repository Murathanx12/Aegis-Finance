"""
THE 2026-07-26 RE-BOOK DEFECT — regression tests.

`_get_portfolio_notional` used to return the static inception_value, so every
cadence/config/decision rebalance re-booked the lane at $100k − costs: NAV
teleported toward inception at every rebalance boundary and compounding was
severed. Caught live: on 2026-07-09 (SPY +0.85%) the aggressive lane "fell"
−2.79% the day after its weekly rebalance — its +2.0% NAV was erased by the
re-book; on 2026-07-16 the same lane "gained" +1.26% (pulled UP to $100k from
below). These tests pin the correct behavior: a rebalance re-books the lane at
the CURRENT MARKED VALUE of its open book, so a rebalance is value-neutral
except for transaction costs.
"""

import sqlite3
from datetime import date

from backend.services.portfolio_intelligence.nav import CASH_TICKER
from backend.services.portfolio_intelligence.reference_engine import (
    _apply_rebalance_positions,
    _get_portfolio_notional,
)


def _make_db(tmp_path):
    db_path = tmp_path / "notional_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE paper_portfolios (
            id TEXT PRIMARY KEY,
            inception_date TEXT NOT NULL,
            inception_value REAL NOT NULL DEFAULT 100000.0,
            config_version TEXT
        );
        CREATE TABLE paper_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            shares REAL NOT NULL,
            cost_basis REAL DEFAULT 100.0,
            opened_at TEXT NOT NULL,
            closed_at TEXT
        );
    """)
    conn.commit()
    return db_path, conn


def _seed(conn, lane_id="testlane", inception=100_000.0):
    today = date.today().isoformat()
    conn.execute(
        "INSERT INTO paper_portfolios (id, inception_date, inception_value) "
        "VALUES (?, ?, ?)", (lane_id, today, inception),
    )
    conn.commit()


class TestGetPortfolioNotional:
    def test_open_book_marked_at_live_prices(self, tmp_path):
        """The notional is the CURRENT marked value, not inception."""
        _, conn = _make_db(tmp_path)
        _seed(conn)
        today = date.today().isoformat()
        # 1000 shares @ $100 cost = $100k booked
        conn.execute(
            "INSERT INTO paper_positions (portfolio_id, ticker, shares, "
            "cost_basis, opened_at) VALUES (?, ?, ?, ?, ?)",
            ("testlane", "AAA", 1000.0, 100.0, today),
        )
        conn.commit()
        # price moved +10% → the lane is worth $110k, and a rebalance must
        # re-book at $110k, never at the $100k inception
        assert _get_portfolio_notional(conn, "testlane", {"AAA": 110.0}) == 110_000.0
        conn.close()

    def test_cost_basis_fallback_when_price_missing(self, tmp_path):
        _, conn = _make_db(tmp_path)
        _seed(conn)
        today = date.today().isoformat()
        conn.execute(
            "INSERT INTO paper_positions (portfolio_id, ticker, shares, "
            "cost_basis, opened_at) VALUES (?, ?, ?, ?, ?)",
            ("testlane", "AAA", 500.0, 80.0, today),
        )
        conn.commit()
        assert _get_portfolio_notional(conn, "testlane", {}) == 40_000.0
        assert _get_portfolio_notional(conn, "testlane") == 40_000.0
        conn.close()

    def test_cash_positions_counted_at_par(self, tmp_path):
        _, conn = _make_db(tmp_path)
        _seed(conn)
        today = date.today().isoformat()
        conn.execute(
            "INSERT INTO paper_positions (portfolio_id, ticker, shares, "
            "cost_basis, opened_at) VALUES (?, ?, ?, ?, ?)",
            ("testlane", "AAA", 100.0, 100.0, today),
        )
        conn.execute(
            "INSERT INTO paper_positions (portfolio_id, ticker, shares, "
            "cost_basis, opened_at) VALUES (?, ?, ?, ?, ?)",
            ("testlane", CASH_TICKER, 5_000.0, 1.0, today),
        )
        conn.commit()
        assert _get_portfolio_notional(conn, "testlane", {"AAA": 120.0}) == 17_000.0
        conn.close()

    def test_closed_positions_excluded(self, tmp_path):
        _, conn = _make_db(tmp_path)
        _seed(conn)
        today = date.today().isoformat()
        conn.execute(
            "INSERT INTO paper_positions (portfolio_id, ticker, shares, "
            "cost_basis, opened_at, closed_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("testlane", "OLD", 999.0, 100.0, today, today),
        )
        conn.execute(
            "INSERT INTO paper_positions (portfolio_id, ticker, shares, "
            "cost_basis, opened_at) VALUES (?, ?, ?, ?, ?)",
            ("testlane", "AAA", 100.0, 100.0, today),
        )
        conn.commit()
        assert _get_portfolio_notional(conn, "testlane", {"AAA": 100.0}) == 10_000.0
        conn.close()

    def test_inception_fallback_before_first_build(self, tmp_path):
        """No open positions yet (first build) → inception_value, unchanged."""
        _, conn = _make_db(tmp_path)
        _seed(conn, inception=100_000.0)
        assert _get_portfolio_notional(conn, "testlane") == 100_000.0
        conn.close()

    def test_unknown_lane_defaults(self, tmp_path):
        _, conn = _make_db(tmp_path)
        assert _get_portfolio_notional(conn, "ghost") == 100_000.0
        conn.close()


class TestNoTeleportOnRebalance:
    """End-to-end: a rebalance is value-neutral except costs — the exact
    invariant the re-book defect violated."""

    def test_gains_survive_a_rebalance(self, tmp_path):
        _, conn = _make_db(tmp_path)
        _seed(conn)
        today = date.today().isoformat()
        conn.execute(
            "INSERT INTO paper_positions (portfolio_id, ticker, shares, "
            "cost_basis, opened_at) VALUES (?, ?, ?, ?, ?)",
            ("testlane", "AAA", 1000.0, 100.0, today),
        )
        conn.commit()

        prices = {"AAA": 110.0, "BBB": 55.0}          # book now worth $110k
        notional = _get_portfolio_notional(conn, "testlane", prices)
        assert notional == 110_000.0

        total_cost = 66.0                              # arbitrary cost figure
        _apply_rebalance_positions(
            conn, "testlane", {"AAA": 0.5, "BBB": 0.5}, prices,
            notional, total_cost, today,
        )
        rows = conn.execute(
            "SELECT ticker, shares FROM paper_positions "
            "WHERE portfolio_id = ? AND closed_at IS NULL", ("testlane",),
        ).fetchall()
        book_value = sum(r["shares"] * prices[r["ticker"]] for r in rows)
        # value-neutral except costs — NOT teleported back to $100k
        assert abs(book_value - (110_000.0 - total_cost)) < 1e-6
        conn.close()

    def test_losses_survive_a_rebalance(self, tmp_path):
        """The mirror failure: a lane BELOW inception must not be pulled UP
        to $100k (the 2026-07-16 aggressive '+1.26% jump')."""
        _, conn = _make_db(tmp_path)
        _seed(conn)
        today = date.today().isoformat()
        conn.execute(
            "INSERT INTO paper_positions (portfolio_id, ticker, shares, "
            "cost_basis, opened_at) VALUES (?, ?, ?, ?, ?)",
            ("testlane", "AAA", 1000.0, 100.0, today),
        )
        conn.commit()

        prices = {"AAA": 92.0}                         # book now worth $92k
        notional = _get_portfolio_notional(conn, "testlane", prices)
        assert notional == 92_000.0

        _apply_rebalance_positions(
            conn, "testlane", {"AAA": 1.0}, prices, notional, 0.0, today,
        )
        rows = conn.execute(
            "SELECT ticker, shares FROM paper_positions "
            "WHERE portfolio_id = ? AND closed_at IS NULL", ("testlane",),
        ).fetchall()
        book_value = sum(r["shares"] * prices[r["ticker"]] for r in rows)
        assert abs(book_value - 92_000.0) < 1e-6
        conn.close()
