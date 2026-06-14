"""
Tests for the point-in-time (as-of) data store — schema v7.

Covers: migration, snapshot insert/no-op/revision, and the LEAK-FREE read
contract (observed_at <= decision_ts). The anti-leak property is the whole
point of this layer, so it gets the most coverage.
"""

import sqlite3

import pytest

from backend.db import (
    CURRENT_SCHEMA_VERSION,
    _SCHEMA_V1,
    get_connection,
    get_latest_observable,
    get_revisions,
    get_series_observable,
    init_db,
    snapshot,
)


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test_pit.db"
    init_db(path)
    return path


@pytest.fixture
def conn(db_path):
    c = get_connection(db_path)
    yield c
    c.close()


# ── Migration ────────────────────────────────────────────────────────────────


class TestMigration:
    def test_table_created_at_v7(self, conn):
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "pit_observations" in tables

    def test_schema_version_is_current(self, conn):
        assert CURRENT_SCHEMA_VERSION >= 7
        v = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0]
        assert v == CURRENT_SCHEMA_VERSION

    def test_init_db_idempotent(self, db_path):
        # Re-running must not error or duplicate.
        init_db(db_path)
        init_db(db_path)
        c = get_connection(db_path)
        try:
            n = c.execute(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type='table' AND name='pit_observations'"
            ).fetchone()[0]
            assert n == 1
        finally:
            c.close()

    def test_migrates_from_v6(self, tmp_path):
        # Simulate a pre-v7 db: base schema + version stamped at 6, no PIT table.
        path = tmp_path / "old.db"
        raw = sqlite3.connect(str(path))
        raw.executescript(_SCHEMA_V1)
        raw.execute("INSERT INTO _schema_version (version) VALUES (6)")
        raw.commit()
        raw.close()
        # init_db should run only the <7 migration and create the table.
        init_db(path)
        c = get_connection(path)
        try:
            assert c.execute(
                "SELECT name FROM sqlite_master WHERE name='pit_observations'"
            ).fetchone() is not None
            assert (
                c.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0]
                == CURRENT_SCHEMA_VERSION
            )
        finally:
            c.close()


# ── snapshot() ───────────────────────────────────────────────────────────────


class TestSnapshot:
    def test_insert_returns_id_and_revision_zero(self, conn):
        rid = snapshot(conn, "fred:CPI", "2026-01-01", 100.0, source="fred")
        assert rid is not None
        revs = get_revisions(conn, "fred:CPI", "2026-01-01")
        assert len(revs) == 1
        assert revs[0]["revision"] == 0
        assert revs[0]["value"] == 100.0
        assert revs[0]["source"] == "fred"

    def test_unchanged_value_is_noop(self, conn):
        snapshot(conn, "fred:CPI", "2026-01-01", 100.0, source="fred")
        again = snapshot(conn, "fred:CPI", "2026-01-01", 100.0, source="fred")
        assert again is None
        assert len(get_revisions(conn, "fred:CPI", "2026-01-01")) == 1

    def test_changed_value_increments_revision(self, conn):
        snapshot(conn, "fred:CPI", "2026-01-01", 100.0, source="fred",
                 observed_at="2026-01-05T00:00:00+00:00")
        rid = snapshot(conn, "fred:CPI", "2026-01-01", 101.5, source="fred",
                       observed_at="2026-01-10T00:00:00+00:00")
        assert rid is not None
        revs = get_revisions(conn, "fred:CPI", "2026-01-01")
        assert [r["revision"] for r in revs] == [0, 1]
        assert [r["value"] for r in revs] == [100.0, 101.5]

    def test_payload_round_trips(self, conn):
        snapshot(conn, "13f:BRK", "2026-03-31", source="edgar",
                 payload={"AAPL": 0.42, "KO": 0.10})
        latest = get_latest_observable(conn, "13f:BRK")
        assert latest["payload"] == {"AAPL": 0.42, "KO": 0.10}
        assert latest["value"] is None

    def test_unchanged_payload_is_noop(self, conn):
        snapshot(conn, "13f:BRK", "2026-03-31", source="edgar", payload={"AAPL": 0.42})
        again = snapshot(conn, "13f:BRK", "2026-03-31", source="edgar",
                         payload={"AAPL": 0.42})
        assert again is None


# ── Leak-free reads (the core contract) ──────────────────────────────────────


class TestLeakFreeReads:
    def test_latest_observable_respects_observed_at(self, conn):
        # Value refers to Jan 1 but we only recorded it on Jan 5.
        snapshot(conn, "fred:X", "2026-01-01", 1.0, source="fred",
                 observed_at="2026-01-05T00:00:00+00:00")
        # As of Jan 4 we did NOT know it yet.
        assert get_latest_observable(conn, "fred:X", "2026-01-04T00:00:00+00:00") is None
        # As of Jan 6 we did.
        seen = get_latest_observable(conn, "fred:X", "2026-01-06T00:00:00+00:00")
        assert seen is not None and seen["value"] == 1.0

    def test_series_uses_revision_known_at_cutoff(self, conn):
        # Original print, then a later revision of the same reference month.
        snapshot(conn, "fred:X", "2026-01-01", 1.0, source="fred",
                 observed_at="2026-01-05T00:00:00+00:00")
        snapshot(conn, "fred:X", "2026-01-01", 1.1, source="fred",
                 observed_at="2026-01-10T00:00:00+00:00")
        snapshot(conn, "fred:X", "2026-02-01", 2.0, source="fred",
                 observed_at="2026-02-05T00:00:00+00:00")

        # As of Jan 7: only the ORIGINAL Jan-01 print is knowable (1.0), Feb not yet.
        early = get_series_observable(conn, "fred:X", "2026-01-07T00:00:00+00:00")
        assert [(r["as_of"], r["value"]) for r in early] == [("2026-01-01", 1.0)]

        # As of Jan 31: the REVISED Jan-01 value (1.1) is now what we'd have seen.
        mid = get_series_observable(conn, "fred:X", "2026-01-31T00:00:00+00:00")
        assert [(r["as_of"], r["value"]) for r in mid] == [("2026-01-01", 1.1)]

        # As of Feb 6: both reference dates, Jan at its revised value.
        full = get_series_observable(conn, "fred:X", "2026-02-06T00:00:00+00:00")
        assert [(r["as_of"], r["value"]) for r in full] == [
            ("2026-01-01", 1.1),
            ("2026-02-01", 2.0),
        ]

    def test_latest_observable_picks_greatest_as_of(self, conn):
        snapshot(conn, "fred:X", "2026-01-01", 1.0, source="fred",
                 observed_at="2026-01-05T00:00:00+00:00")
        snapshot(conn, "fred:X", "2026-02-01", 2.0, source="fred",
                 observed_at="2026-02-05T00:00:00+00:00")
        latest = get_latest_observable(conn, "fred:X", "2026-03-01T00:00:00+00:00")
        assert latest["as_of"] == "2026-02-01" and latest["value"] == 2.0

    def test_missing_key_returns_none_and_empty(self, conn):
        assert get_latest_observable(conn, "nope") is None
        assert get_series_observable(conn, "nope") == []
        assert get_revisions(conn, "nope", "2026-01-01") == []
