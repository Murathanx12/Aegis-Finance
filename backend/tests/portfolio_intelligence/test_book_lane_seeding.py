"""
Tests for seed_book_lane (P1 #6, Chunk 1b) — the controlled write-path.

Offline: live prices are injected. Covers correct MV-weight seeding, $100k
normalization, idempotency, and the fail-loud-BEFORE-write garbage gate.
"""

import json
from datetime import date

import pytest

from backend.db import (
    count_cumulative_trials,
    get_book_config_hash,
    get_connection,
    init_db,
    insert_nav,
)
from backend.services.portfolio_intelligence import reference_engine as re_
from backend.services.portfolio_intelligence.experiment_registry import (
    effective_independent_trials,
)


# Arbitrary positive prices for the 12-name confirmed book.
_PRICES = {
    "SOC": 12.0, "DKNG": 40.0, "NTLA": 9.0, "AARD": 3.0, "BHVN": 25.0,
    "HUBS": 500.0, "KYTX": 6.0, "PRCH": 2.0, "QUBT": 15.0, "AMSC": 30.0,
    "ABSI": 4.0, "SLDP": 1.5,
}


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "book_seed.db"
    init_db(path)
    return path


def _portfolio_row(db_path, lane_id):
    c = get_connection(db_path)
    try:
        return c.execute(
            "SELECT id, inception_value, config_version, inception_date "
            "FROM paper_portfolios WHERE id = ?", (lane_id,)
        ).fetchone()
    finally:
        c.close()


def _positions(db_path, lane_id):
    c = get_connection(db_path)
    try:
        return c.execute(
            "SELECT ticker, shares, cost_basis FROM paper_positions "
            "WHERE portfolio_id = ?", (lane_id,)
        ).fetchall()
    finally:
        c.close()


class TestSeedBookLane:
    def test_seeds_mirror_at_100k_mv_weights(self, db_path):
        res = re_.seed_book_lane("mirror", db_path=db_path, prices=_PRICES)
        assert res["seeded"] is True
        assert res["n_positions"] == 12
        assert sum(res["weights"].values()) == pytest.approx(1.0)

        row = _portfolio_row(db_path, "mirror")
        assert row is not None
        assert row["inception_value"] == 100000.0
        assert row["config_version"] == get_book_config_hash()

        # shares_i = weight_i * 100k / price_i ; value_i = shares_i * price_i
        positions = {p["ticker"]: p for p in _positions(db_path, "mirror")}
        assert len(positions) == 12
        total_value = sum(p["shares"] * p["cost_basis"] for p in positions.values())
        assert total_value == pytest.approx(100000.0)
        # SOC weight = (700*12) / total_MV ; check its dollar value matches
        total_mv = sum(_PRICES[t] * s for t, s in {
            "SOC": 700, "DKNG": 150, "NTLA": 250, "AARD": 1000, "BHVN": 300,
            "HUBS": 10, "KYTX": 250, "PRCH": 200, "QUBT": 200, "AMSC": 50,
            "ABSI": 600, "SLDP": 600,
        }.items())
        soc_dollar = positions["SOC"]["shares"] * positions["SOC"]["cost_basis"]
        assert soc_dollar == pytest.approx(100000.0 * (700 * 12.0) / total_mv)

    def test_idempotent_no_double_seed(self, db_path):
        first = re_.seed_book_lane("mirror", db_path=db_path, prices=_PRICES)
        second = re_.seed_book_lane("mirror", db_path=db_path, prices=_PRICES)
        assert first["seeded"] is True
        assert second["seeded"] is False
        assert len(_positions(db_path, "mirror")) == 12  # not 24

    def test_mirror_and_conviction_seed_identically(self, db_path):
        m = re_.seed_book_lane("mirror", db_path=db_path, prices=_PRICES)
        c = re_.seed_book_lane("conviction", db_path=db_path, prices=_PRICES)
        assert m["weights"] == c["weights"]  # same book, same seed
        assert _portfolio_row(db_path, "conviction") is not None

    def test_fail_loud_before_any_write(self, db_path):
        bad = dict(_PRICES)
        del bad["SLDP"]  # one unpriceable name
        with pytest.raises(ValueError):
            re_.seed_book_lane("mirror", db_path=db_path, prices=bad)
        # The gate runs before any INSERT — no partial row may exist.
        assert _portfolio_row(db_path, "mirror") is None
        assert _positions(db_path, "mirror") == []

    def test_unknown_lane_raises(self, db_path):
        with pytest.raises(ValueError):
            re_.seed_book_lane("not_a_lane", db_path=db_path, prices=_PRICES)


def _nav_rows(db_path, lane_id):
    c = get_connection(db_path)
    try:
        return c.execute(
            "SELECT date, nav FROM paper_nav WHERE portfolio_id = ?", (lane_id,)
        ).fetchall()
    finally:
        c.close()


class TestBookLaneMTM:
    def test_unseeded_book_lanes_skipped(self, db_path):
        # Fresh DB, nothing seeded → MTM must NOT auto-create book lanes.
        out = re_.mark_all_book_lanes(db_path=db_path)
        assert out == {"mirror": None, "conviction": None}
        assert _portfolio_row(db_path, "mirror") is None  # not auto-created

    def test_mtm_at_seed_prices_is_100k(self, db_path):
        re_.seed_book_lane("mirror", db_path=db_path, prices=_PRICES)
        nav = re_.mark_lane_to_market("mirror", prices=_PRICES, db_path=db_path)
        assert nav == pytest.approx(100000.0)  # marked at seed prices → notional
        assert len(_nav_rows(db_path, "mirror")) == 1

    def test_one_bad_ticker_degrades_to_cost_basis(self, db_path):
        re_.seed_book_lane("mirror", db_path=db_path, prices=_PRICES)
        partial = dict(_PRICES)
        del partial["SLDP"]  # one un-fetchable name
        nav = re_.mark_lane_to_market("mirror", prices=partial, db_path=db_path)
        # SLDP falls back to its cost_basis (== seed price) → NAV still ~100k,
        # NOT a flat-line, NOT a crash.
        assert nav is not None
        assert nav == pytest.approx(100000.0, rel=1e-6)

    def test_total_price_failure_persists_no_row(self, db_path):
        re_.seed_book_lane("mirror", db_path=db_path, prices=_PRICES)
        nav = re_.mark_lane_to_market("mirror", prices={}, db_path=db_path)
        assert nav is None  # every price failed → refuse to write a flat line
        assert _nav_rows(db_path, "mirror") == []

    def test_mark_all_book_lanes_after_seed(self, db_path, monkeypatch):
        re_.seed_book_lane("mirror", db_path=db_path, prices=_PRICES)
        re_.seed_book_lane("conviction", db_path=db_path, prices=_PRICES)
        # Inject prices so MTM is deterministic + offline (no network attempt).
        monkeypatch.setattr(re_, "_get_current_prices", lambda tickers: dict(_PRICES))
        out = re_.mark_all_book_lanes(db_path=db_path)
        assert set(out.keys()) == {"mirror", "conviction"}
        assert out["mirror"] == pytest.approx(100000.0)
        assert out["conviction"] == pytest.approx(100000.0)


class TestTrialRegistration:
    def test_seeding_registers_both_trials(self, db_path):
        c = get_connection(db_path)
        try:
            base = count_cumulative_trials(c)
        finally:
            c.close()
        re_.seed_book_lane("mirror", db_path=db_path, prices=_PRICES)
        re_.seed_book_lane("conviction", db_path=db_path, prices=_PRICES)
        c = get_connection(db_path)
        try:
            # +2 (one per lane) — in prod 3→5; on a fresh db base→base+2.
            assert count_cumulative_trials(c) == base + 2
            rows = {
                r["lane_id"]: r for r in c.execute(
                    "SELECT lane_id, config_version, verdict, notes FROM "
                    "rule_experiments WHERE lane_id IN ('mirror','conviction')"
                ).fetchall()
            }
        finally:
            c.close()
        assert set(rows) == {"mirror", "conviction"}
        assert rows["mirror"]["config_version"] == get_book_config_hash()
        assert json.loads(rows["mirror"]["notes"])["purpose"] == "portfolio-mirror"
        assert json.loads(rows["conviction"]["notes"])["purpose"] == "conviction"

    def test_reseed_does_not_double_register(self, db_path):
        re_.seed_book_lane("mirror", db_path=db_path, prices=_PRICES)
        c = get_connection(db_path)
        try:
            after_first = count_cumulative_trials(c)
        finally:
            c.close()
        re_.seed_book_lane("mirror", db_path=db_path, prices=_PRICES)  # idempotent
        c = get_connection(db_path)
        try:
            assert count_cumulative_trials(c) == after_first  # no second trial
        finally:
            c.close()


class TestEffectiveNCountsBookLanes:
    def _inject_correlated_nav(self, db_path):
        # Two non-flat, highly-correlated NAV streams (mirror ≈ conviction) over
        # 35 common dates → the participation ratio should see ~1 independent pair.
        conn = get_connection(db_path)
        try:
            h = get_book_config_hash()
            mirror_nav = 100000.0
            conv_nav = 100000.0
            for i in range(35):
                r = 0.004 * (((i % 5) - 2) / 2.0)   # varies -0.004..+0.006
                mirror_nav *= (1 + r)
                conv_nav *= (1 + r + (0.0003 if i % 2 else -0.0002))  # near-identical
                d = f"2026-05-{i + 1:02d}" if i < 31 else f"2026-06-{i - 30:02d}"
                insert_nav(conn, "mirror", d, mirror_nav, h, d)
                insert_nav(conn, "conviction", d, conv_nav, h, d)
        finally:
            conn.close()

    def test_book_lanes_in_neff_and_counted_as_pair(self, db_path):
        # Seed registers the lanes; inject correlated NAV so N_eff can compute.
        re_.seed_book_lane("mirror", db_path=db_path, prices=_PRICES)
        re_.seed_book_lane("conviction", db_path=db_path, prices=_PRICES)
        self._inject_correlated_nav(db_path)

        info = effective_independent_trials(db_path=db_path)
        assert "mirror" in info["lanes"] and "conviction" in info["lanes"]
        # Raw cumulative count (the gate floor) counts both as 2 separate trials…
        c = get_connection(db_path)
        try:
            assert count_cumulative_trials(c) >= 2
        finally:
            c.close()
        # …but N_eff treats the correlated pair as ~1 independent stream.
        if info["status"] == "ok":
            assert info["n_eff"] is not None and info["n_eff"] < 1.6


class TestSeedAllAndFreshness:
    def test_seed_all_book_lanes(self, db_path, monkeypatch):
        monkeypatch.setattr(re_, "_get_current_prices", lambda t: dict(_PRICES))
        out = re_.seed_all_book_lanes(db_path=db_path)
        assert out["seeded"]["mirror"]["seeded"] is True
        assert out["seeded"]["conviction"]["seeded"] is True
        assert out["mtm"]["mirror"] == pytest.approx(100000.0)
        assert out["mtm"]["conviction"] == pytest.approx(100000.0)

    def test_nav_freshness_excludes_unseeded_then_includes_seeded(
        self, tmp_path, monkeypatch
    ):
        from backend import db as db_module
        from backend.services.portfolio_intelligence import scheduler as sched

        dbp = tmp_path / "fresh.db"
        init_db(dbp)
        monkeypatch.setattr(db_module, "DB_PATH", dbp)  # nav_freshness reads default

        # Unseeded: book lanes must NOT appear (must not drag all_fresh false).
        fr0 = sched.nav_freshness()
        assert "mirror" not in fr0["lanes"]
        assert "conviction" not in fr0["lanes"]

        # Seed + a fresh NAV row dated today (>= expected trading day).
        re_.seed_book_lane("mirror", db_path=dbp, prices=_PRICES)
        re_.seed_book_lane("conviction", db_path=dbp, prices=_PRICES)
        today = date.today().isoformat()
        h = get_book_config_hash()
        c = get_connection(dbp)
        try:
            insert_nav(c, "mirror", today, 100000.0, h, today)
            insert_nav(c, "conviction", today, 100000.0, h, today)
        finally:
            c.close()

        fr1 = sched.nav_freshness()
        assert fr1["lanes"]["mirror"]["fresh"] is True
        assert fr1["lanes"]["conviction"]["fresh"] is True
