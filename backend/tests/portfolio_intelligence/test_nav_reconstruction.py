"""Tests for the 2026-07-26 re-book defect reconstruction.

Synthetic lane reproducing the observed prod pattern: honest daily marks,
then a cadence rebalance that re-booked at $100k and teleported the chain.
The reconstruction must splice the chain back together, rescale the open
book, archive originals, and be idempotent.
"""

import sqlite3
from datetime import date

import pytest

from backend.db import get_connection, init_db
from backend.services.portfolio_intelligence.nav_reconstruction import (
    ARCHIVE_TABLE,
    reconstruct_nav_history,
)


def _mk_lane(db, lane_id="testlane"):
    init_db(db)
    conn = get_connection(db)
    conn.execute(
        "INSERT INTO paper_portfolios (id, inception_date, inception_value, "
        "config_version) VALUES (?, ?, ?, ?)",
        (lane_id, "2026-06-08", 100_000.0, "hashx"),
    )
    conn.commit()
    return conn


def _nav(conn, lane_id, d, v):
    conn.execute(
        "INSERT OR REPLACE INTO paper_nav (portfolio_id, date, nav, "
        "config_version, computed_at) VALUES (?, ?, ?, ?, ?)",
        (lane_id, d, v, "hashx", d + "T16:30:00"),
    )


def _event(conn, lane_id, ts, reason):
    conn.execute(
        "INSERT INTO rebalance_events (portfolio_id, triggered_at, "
        "trigger_reason, pre_weights, post_weights, explanation) "
        "VALUES (?, ?, ?, '{}', '{}', 'test')",
        (lane_id, ts, reason),
    )


def _navs(conn, lane_id):
    return {r["date"]: r["nav"] for r in conn.execute(
        "SELECT date, nav FROM paper_nav WHERE portfolio_id = ? ORDER BY date",
        (lane_id,)).fetchall()}


class TestReconstruction:
    def test_case_a_teleport_spliced(self, tmp_path):
        """The aggressive-lane pattern: +2% NAV erased by a 16:30 re-book.
        Booked: 100k, 102k(rebalance day, pre-book row), 100.5k(post-book).
        True:   100k, 102k, 102k*100.5/100 = 102,510."""
        db = tmp_path / "r.db"
        conn = _mk_lane(db)
        _nav(conn, "testlane", "2026-07-07", 102_000.0)
        _nav(conn, "testlane", "2026-07-08", 102_017.0)   # pre-book mark
        _event(conn, "testlane", "2026-07-08T16:30:01", "weekly_aggressive")
        _nav(conn, "testlane", "2026-07-09", 100_500.0)   # post-book (teleported)
        # open book as re-booked at ~100k
        conn.execute(
            "INSERT INTO paper_positions (portfolio_id, ticker, shares, "
            "cost_basis, opened_at) VALUES (?, ?, ?, ?, ?)",
            ("testlane", "AAA", 1000.0, 100.0, "2026-07-08"),
        )
        conn.commit()
        conn.close()

        res = reconstruct_nav_history(db_path=db)
        assert res["status"] == "reconstructed"
        k = 102_017.0 / 100_000.0
        conn = get_connection(db)
        navs = _navs(conn, "testlane")
        assert navs["2026-07-07"] == 102_000.0            # pre-boundary untouched
        assert navs["2026-07-08"] == 102_017.0            # pre-book row untouched
        assert navs["2026-07-09"] == pytest.approx(100_500.0 * k)
        shares = conn.execute(
            "SELECT shares FROM paper_positions WHERE portfolio_id='testlane' "
            "AND closed_at IS NULL").fetchone()["shares"]
        assert shares == pytest.approx(1000.0 * k)        # open book rescaled
        conn.close()

    def test_case_b_boot_config_event(self, tmp_path):
        """Config-change at boot: same-day row is already post-book (~100k);
        the factor comes from the prior row."""
        db = tmp_path / "r2.db"
        conn = _mk_lane(db)
        _nav(conn, "testlane", "2026-06-09", 100_619.0)
        _event(conn, "testlane", "2026-06-10T08:00:00", "config_change a->b")
        _nav(conn, "testlane", "2026-06-10", 99_972.0)    # post-book (within band)
        conn.commit()
        conn.close()

        res = reconstruct_nav_history(db_path=db)
        k = 100_619.0 / 100_000.0
        conn = get_connection(db)
        navs = _navs(conn, "testlane")
        assert navs["2026-06-09"] == 100_619.0
        assert navs["2026-06-10"] == pytest.approx(99_972.0 * k)
        conn.close()
        assert res["plan"]["testlane"]["n_boundaries"] == 1

    def test_initialization_and_postfix_events_ignored(self, tmp_path):
        db = tmp_path / "r3.db"
        conn = _mk_lane(db)
        _event(conn, "testlane", "2026-06-08T10:00:00", "initialization")
        _nav(conn, "testlane", "2026-06-09", 101_000.0)
        # fixed-era event (after FIX_CUTOFF) must not be treated as a boundary
        _event(conn, "testlane", "2026-08-10T16:30:00", "monthly")
        _nav(conn, "testlane", "2026-08-11", 103_000.0)
        conn.commit()
        conn.close()

        res = reconstruct_nav_history(db_path=db)
        assert res["plan"]["testlane"]["n_boundaries"] == 0
        conn = get_connection(db)
        navs = _navs(conn, "testlane")
        assert navs["2026-06-09"] == 101_000.0
        assert navs["2026-08-11"] == 103_000.0
        conn.close()

    def test_cumulative_boundaries_compound(self, tmp_path):
        db = tmp_path / "r4.db"
        conn = _mk_lane(db)
        _nav(conn, "testlane", "2026-06-16", 102_000.0)   # pre-book #1
        _event(conn, "testlane", "2026-06-16T16:30:01", "weekly_aggressive")
        _nav(conn, "testlane", "2026-06-17", 99_000.0)
        _nav(conn, "testlane", "2026-06-23", 98_000.0)    # pre-book #2
        _event(conn, "testlane", "2026-06-23T16:30:01", "weekly_aggressive")
        _nav(conn, "testlane", "2026-06-24", 101_000.0)
        conn.commit()
        conn.close()

        reconstruct_nav_history(db_path=db)
        k1, k2 = 1.02, 0.98
        conn = get_connection(db)
        navs = _navs(conn, "testlane")
        assert navs["2026-06-17"] == pytest.approx(99_000.0 * k1)
        assert navs["2026-06-23"] == pytest.approx(98_000.0 * k1)
        assert navs["2026-06-24"] == pytest.approx(101_000.0 * k1 * k2)
        conn.close()

    def test_idempotent_and_archived(self, tmp_path):
        db = tmp_path / "r5.db"
        conn = _mk_lane(db)
        _nav(conn, "testlane", "2026-07-08", 102_000.0)
        _event(conn, "testlane", "2026-07-08T16:30:01", "monthly")
        _nav(conn, "testlane", "2026-07-09", 100_000.0)
        conn.commit()
        conn.close()

        r1 = reconstruct_nav_history(db_path=db)
        assert r1["status"] == "reconstructed"
        conn = get_connection(db)
        after_first = _navs(conn, "testlane")
        archived = {r["date"]: r["nav"] for r in conn.execute(
            f"SELECT date, nav FROM {ARCHIVE_TABLE} "
            "WHERE portfolio_id='testlane'").fetchall()}
        conn.close()
        assert archived["2026-07-09"] == 100_000.0        # original preserved

        r2 = reconstruct_nav_history(db_path=db)          # second run: no-op
        assert r2["status"] == "already_ran"
        conn = get_connection(db)
        assert _navs(conn, "testlane") == after_first
        conn.close()

    def test_dry_run_writes_nothing(self, tmp_path):
        db = tmp_path / "r6.db"
        conn = _mk_lane(db)
        _nav(conn, "testlane", "2026-07-08", 102_000.0)
        _event(conn, "testlane", "2026-07-08T16:30:01", "monthly")
        _nav(conn, "testlane", "2026-07-09", 100_000.0)
        conn.commit()
        conn.close()

        res = reconstruct_nav_history(db_path=db, dry_run=True)
        assert res["status"] == "dry_run"
        assert res["plan"]["testlane"]["n_boundaries"] == 1
        conn = get_connection(db)
        assert _navs(conn, "testlane")["2026-07-09"] == 100_000.0
        # a later real run still executes
        conn.close()
        assert reconstruct_nav_history(db_path=db)["status"] == "reconstructed"
