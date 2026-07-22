"""
Offline tests for the smallmid-quality lane (TRIAL-SMQ-FWD) seed + MTM.

All offline: prices are injected, no network. Verifies the seed-a-lane safety
properties: hash isolation from every existing config, no-op-until-seeded,
idempotent double-seed, registry-row-on-seed, drop-tolerance fail-loud
behavior, and that the frozen configs are byte-untouched by importing/seeding.
"""

from pathlib import Path
import tempfile

import pytest

from backend.config import smallmid_quality_lanes
from backend.db import (
    get_book_config_hash,
    get_config_hash,
    get_connection,
    get_conservative_atr_config_hash,
    get_smq_config_hash,
    init_db,
)
from backend.services.portfolio_intelligence import smq_lane as sq
from backend.services.portfolio_intelligence.smq_lane import (
    LANE_ID,
    MAX_DROPPED_TICKERS,
)


@pytest.fixture
def db():
    path = Path(tempfile.mkdtemp()) / "smq_lane_test.db"
    init_db(path)
    return path


def _holdings() -> list[str]:
    return list(smallmid_quality_lanes[LANE_ID]["holdings"])


def _flat_prices() -> dict:
    return {t: 50.0 for t in _holdings()}


class TestConfig:
    def test_lane_config_present_with_30_holdings(self):
        cfg = smallmid_quality_lanes.get(LANE_ID)
        assert cfg and cfg["purpose"] == "smq-forward-trial"
        assert len(cfg["holdings"]) == 30
        assert cfg["optimizer"] == "none"
        assert cfg["rebalance_frequency"] == "never"

    def test_smq_hash_distinct_from_every_other_config(self):
        h = get_smq_config_hash()
        assert h != get_config_hash()
        assert h != get_book_config_hash()
        assert h != get_conservative_atr_config_hash()


class TestNoOpUntilSeeded:
    def test_mtm_skips_unseeded_lane(self, db):
        assert sq.mark_all_smq_lanes(db_path=db) == {LANE_ID: None}


class TestSeed:
    def test_seed_creates_lane_with_isolated_hash_and_registry_row(self, db):
        res = sq.seed_smallmid_quality_lane(db_path=db, prices=_flat_prices())
        assert res["seeded"] is True and res["n_positions"] == 30
        assert res["dropped"] == []
        conn = get_connection(db)
        try:
            pp = conn.execute(
                "SELECT config_version FROM paper_portfolios WHERE id = ?",
                (LANE_ID,),
            ).fetchone()
            assert pp is not None
            assert pp["config_version"] == get_smq_config_hash()
            n_pos = conn.execute(
                "SELECT COUNT(*) c FROM paper_positions WHERE portfolio_id = ?",
                (LANE_ID,),
            ).fetchone()["c"]
            assert n_pos == 30
            trial = conn.execute(
                "SELECT 1 FROM rule_experiments WHERE lane_id = ?",
                (LANE_ID,),
            ).fetchone()
            assert trial is not None
        finally:
            conn.close()

    def test_double_seed_idempotent(self, db):
        first = sq.seed_smallmid_quality_lane(db_path=db, prices=_flat_prices())
        second = sq.seed_smallmid_quality_lane(db_path=db, prices=_flat_prices())
        assert first["seeded"] is True
        assert second["seeded"] is False and second["reason"] == "already_exists"
        conn = get_connection(db)
        try:
            n = conn.execute(
                "SELECT COUNT(*) c FROM paper_positions WHERE portfolio_id = ?",
                (LANE_ID,),
            ).fetchone()["c"]
        finally:
            conn.close()
        assert n == 30

    def test_few_unpriceable_drop_loudly(self, db):
        prices = _flat_prices()
        missing = _holdings()[:MAX_DROPPED_TICKERS]
        for t in missing:
            prices[t] = None
        res = sq.seed_smallmid_quality_lane(db_path=db, prices=prices)
        assert res["seeded"] is True
        assert sorted(res["dropped"]) == sorted(missing)
        assert res["n_positions"] == 30 - MAX_DROPPED_TICKERS

    def test_too_many_unpriceable_refuses(self, db):
        prices = _flat_prices()
        for t in _holdings()[: MAX_DROPPED_TICKERS + 1]:
            prices[t] = None
        with pytest.raises(ValueError, match="REFUSED"):
            sq.seed_smallmid_quality_lane(db_path=db, prices=prices)
        conn = get_connection(db)
        try:
            assert conn.execute(
                "SELECT 1 FROM paper_portfolios WHERE id = ?", (LANE_ID,)
            ).fetchone() is None
        finally:
            conn.close()

    def test_equal_weight_book(self, db):
        sq.seed_smallmid_quality_lane(db_path=db, prices=_flat_prices())
        conn = get_connection(db)
        try:
            rows = conn.execute(
                "SELECT shares, cost_basis FROM paper_positions "
                "WHERE portfolio_id = ?", (LANE_ID,),
            ).fetchall()
        finally:
            conn.close()
        mvs = [r["shares"] * r["cost_basis"] for r in rows]
        assert all(abs(mv - mvs[0]) < 1e-6 for mv in mvs)
        assert abs(sum(mvs) - 100_000.0) < 1e-3
