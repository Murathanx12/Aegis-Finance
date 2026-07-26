"""NAV rows must carry the LANE'S OWN config_version (prod finding (b),
2026-07-24): mark_lane_to_market used to stamp the GLOBAL reference-yaml hash
on every lane's paper_nav rows, so book/ATR/SMQ segments claimed the wrong
identity."""

from datetime import date
from unittest.mock import patch

from backend.db import get_connection, init_db
from backend.services.portfolio_intelligence.reference_engine import (
    mark_lane_to_market,
)


def _seed_lane(db_path, lane_id, config_version):
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO paper_portfolios (id, inception_date, inception_value, "
            "config_version) VALUES (?, ?, ?, ?)",
            (lane_id, date.today().isoformat(), 100_000.0, config_version),
        )
        conn.execute(
            "INSERT INTO paper_positions (portfolio_id, ticker, shares, "
            "cost_basis, opened_at) VALUES (?, ?, ?, ?, ?)",
            (lane_id, "AAA", 1000.0, 100.0, date.today().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def _nav_stamp(db_path, lane_id):
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT config_version FROM paper_nav WHERE portfolio_id = ? "
            "ORDER BY date DESC LIMIT 1", (lane_id,),
        ).fetchone()
        return row["config_version"] if row else None
    finally:
        conn.close()


class TestNavStampsLaneOwnVersion:
    def test_non_reference_lane_keeps_its_own_hash(self, tmp_path):
        db = tmp_path / "stamp.db"
        _seed_lane(db, "some-attended-lane", "lanehash1234")
        nav = mark_lane_to_market(
            "some-attended-lane", prices={"AAA": 105.0}, db_path=db,
        )
        assert nav == 105_000.0
        assert _nav_stamp(db, "some-attended-lane") == "lanehash1234"

    def test_empty_version_falls_back_to_global_hash(self, tmp_path):
        """config_version is NOT NULL in the real schema; an empty string is
        the only degenerate case — defensively stamp the global hash."""
        db = tmp_path / "stamp2.db"
        _seed_lane(db, "legacy-lane", "")
        with patch(
            "backend.db.get_config_hash", return_value="globalhash99",
        ):
            mark_lane_to_market("legacy-lane", prices={"AAA": 100.0}, db_path=db)
        assert _nav_stamp(db, "legacy-lane") == "globalhash99"
