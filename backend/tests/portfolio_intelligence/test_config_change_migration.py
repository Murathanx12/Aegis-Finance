"""
Config v1→v2 boundary mechanics (Step #2).

  - apply_config_change_rebalances fires EXACTLY ONE explicit boundary
    rebalance per existing lane whose stored config_version differs, stamps
    the event with the new hash, and updates the lane row — idempotent on
    the next boot.
  - New lanes (balanced-ew-control) are initialized + registered as trials
    (the cumulative count the DSR guard deflates against).
  - Rebalances now REALLY trade: old positions closed, target book opened —
    and NAV is continuous across the switch (± transaction costs).
  - Schema v3→v4 adds rebalance_events.config_version.
"""

from unittest.mock import patch

import pytest

from backend.config import paper_portfolios
from backend.db import get_config_hash, get_connection, init_db
from backend.services.portfolio_intelligence import reference_engine as engine
from backend.services.portfolio_intelligence.rules import (
    REFERENCE_LANES,
    _get_sleeve_tickers,
)

OLD_HASH = "0ld0ld0ld0ld0ld0"
PRE_EXISTING = ("conservative", "balanced", "aggressive")


def _universe_prices(value: float = 100.0) -> dict:
    sleeves = _get_sleeve_tickers(paper_portfolios["universe"])
    tickers = sleeves["equity"] + sleeves["bond"] + sleeves["alternative"]
    return {t: value for t in tickers}


@pytest.fixture()
def seeded_db(tmp_path, monkeypatch):
    """Three lanes initialized under a fake OLD config hash."""
    db = tmp_path / "mig.db"
    init_db(db)
    prices = _universe_prices()
    for lane in PRE_EXISTING:
        engine.initialize_lane(lane, db_path=db, prices=prices)
    conn = get_connection(db)
    try:
        conn.execute("UPDATE paper_portfolios SET config_version = ?", (OLD_HASH,))
        conn.commit()
    finally:
        conn.close()
    # Keep the migration offline + deterministic.
    monkeypatch.setattr(engine, "_get_current_prices", lambda tickers: _universe_prices())
    monkeypatch.setattr(engine, "_get_crash_prob", lambda: None)
    return db


class TestBoundaryMigration:
    def test_fires_once_per_lane_and_is_idempotent(self, seeded_db):
        out = engine.apply_config_change_rebalances(db_path=seeded_db)
        for lane in PRE_EXISTING:
            assert out[lane] == "rebalanced", out
        assert out["balanced-ew-control"] == "initialized"

        current = get_config_hash()
        conn = get_connection(seeded_db)
        try:
            for lane in PRE_EXISTING:
                events = conn.execute(
                    "SELECT trigger_reason, config_version FROM rebalance_events "
                    "WHERE portfolio_id = ? ORDER BY id",
                    (lane,),
                ).fetchall()
                reasons = [e["trigger_reason"] for e in events]
                boundary = [r for r in reasons if r.startswith("config_change")]
                assert len(boundary) == 1, f"{lane}: {reasons}"
                assert OLD_HASH[:8] in boundary[0] and current[:8] in boundary[0]
                assert events[-1]["config_version"] == current

                row = conn.execute(
                    "SELECT config_version FROM paper_portfolios WHERE id = ?",
                    (lane,),
                ).fetchone()
                assert row["config_version"] == current
        finally:
            conn.close()

        # Second boot: nothing fires.
        out2 = engine.apply_config_change_rebalances(db_path=seeded_db)
        assert all(v == "current" for v in out2.values()), out2
        conn = get_connection(seeded_db)
        try:
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM rebalance_events "
                "WHERE trigger_reason LIKE 'config_change%'"
            ).fetchone()["n"]
            n_trials = conn.execute(
                "SELECT COUNT(*) AS n FROM rule_experiments"
            ).fetchone()["n"]
        finally:
            conn.close()
        assert n == len(PRE_EXISTING)
        assert n_trials == 1, "control lane registered exactly once"

    def test_rebalance_actually_trades_the_book(self, seeded_db):
        engine.apply_config_change_rebalances(db_path=seeded_db)
        conn = get_connection(seeded_db)
        try:
            closed = conn.execute(
                "SELECT COUNT(*) AS n FROM paper_positions "
                "WHERE portfolio_id = 'balanced' AND closed_at IS NOT NULL"
            ).fetchone()["n"]
            open_rows = conn.execute(
                "SELECT ticker, shares, cost_basis, opened_at FROM paper_positions "
                "WHERE portfolio_id = 'balanced' AND closed_at IS NULL"
            ).fetchall()
            event = conn.execute(
                "SELECT post_weights FROM rebalance_events "
                "WHERE portfolio_id = 'balanced' "
                "AND trigger_reason LIKE 'config_change%'"
            ).fetchone()
        finally:
            conn.close()

        assert closed > 0, "old book was never closed — event is paper-only"
        assert open_rows, "no new book opened"

        import json
        post = json.loads(event["post_weights"])
        book_value = sum(r["shares"] * r["cost_basis"] for r in open_rows)
        for r in open_rows:
            booked_w = (r["shares"] * r["cost_basis"]) / book_value
            assert booked_w == pytest.approx(post[r["ticker"]], abs=1e-4), (
                f"{r['ticker']}: booked {booked_w:.5f} != target "
                f"{post[r['ticker']]:.5f}"
            )

    def test_nav_continuous_across_switch(self, seeded_db):
        prices = _universe_prices()
        nav_before = engine.mark_lane_to_market(
            "balanced", prices=prices, db_path=seeded_db,
        )
        engine.apply_config_change_rebalances(db_path=seeded_db)
        nav_after = engine.mark_lane_to_market(
            "balanced", prices=prices, db_path=seeded_db,
        )
        # Same prices → NAV moves only by transaction costs (a few bps).
        assert nav_after == pytest.approx(nav_before, rel=0.005), (
            f"NAV jumped across the boundary: {nav_before} -> {nav_after}"
        )
        assert nav_after <= nav_before + 1e-6, "rebalance cannot CREATE value"

    def test_control_lane_registered_with_hypothesis(self, seeded_db):
        engine.apply_config_change_rebalances(db_path=seeded_db)
        conn = get_connection(seeded_db)
        try:
            row = conn.execute(
                "SELECT lane_id, param, verdict, notes, cumulative_trials "
                "FROM rule_experiments WHERE lane_id = 'balanced-ew-control'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None, "lane is not a registered trial — guardrail violated"
        assert row["param"] == "lane:balanced-ew-control"
        assert "HRP adds value over equal-weight" in row["notes"]
        assert "optimizer-variant" in row["notes"]
        assert row["cumulative_trials"] >= 1


class TestSchemaV4:
    def test_fresh_db_has_event_config_version(self, tmp_path):
        db = tmp_path / "v4.db"
        init_db(db)
        conn = get_connection(db)
        try:
            cols = [r["name"] for r in conn.execute(
                "PRAGMA table_info(rebalance_events)"
            ).fetchall()]
        finally:
            conn.close()
        assert "config_version" in cols

    def test_v3_db_migrates_to_v4(self, tmp_path):
        import sqlite3
        from backend.db import _SCHEMA_V1

        db = tmp_path / "old.db"
        raw = sqlite3.connect(str(db))
        raw.executescript(_SCHEMA_V1)
        raw.execute("INSERT INTO _schema_version (version) VALUES (3)")
        raw.commit()
        raw.close()

        init_db(db)  # runs 3→4
        conn = get_connection(db)
        try:
            cols = [r["name"] for r in conn.execute(
                "PRAGMA table_info(rebalance_events)"
            ).fetchall()]
        finally:
            conn.close()
        assert "config_version" in cols, "v3→v4 migration did not add the column"


def test_reference_lanes_includes_control():
    assert "balanced-ew-control" in REFERENCE_LANES
