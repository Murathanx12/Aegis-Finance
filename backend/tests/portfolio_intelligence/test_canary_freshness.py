"""
V2 P0 #3 — canary upgrade: liveness → freshness.

Acceptance:
  - last_mtm is NOT stamped when every lane fails to mark (a green liveness
    canary over zero persisted rows was the failure mode to kill),
  - last_mtm IS stamped when at least one lane marks,
  - expected-nav-date logic handles pre/post-close, weekends, NYSE holidays,
  - scheduler_health exposes per-lane paper_nav freshness,
  - total price failure does NOT persist a flat all-cost-basis NAV row.
"""

import asyncio
from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import backend.services.portfolio_intelligence.scheduler as sched
from backend.config import paper_portfolios
from backend.services.portfolio_intelligence.rules import _get_sleeve_tickers

ET = ZoneInfo("US/Eastern")


def _universe_prices(value: float) -> dict:
    sleeves = _get_sleeve_tickers(paper_portfolios["universe"])
    tickers = sleeves["equity"] + sleeves["bond"] + sleeves["alternative"]
    return {t: value for t in tickers}


class TestLastMtmStamping:
    def setup_method(self):
        self._saved = sched._last_mtm_timestamp
        sched._last_mtm_timestamp = None

    def teardown_method(self):
        sched._last_mtm_timestamp = self._saved

    def test_not_stamped_when_all_lanes_fail(self):
        with patch(
            "backend.services.portfolio_intelligence.reference_engine.mark_all_lanes",
            return_value={"conservative": None, "balanced": None, "aggressive": None},
        ):
            asyncio.run(sched._hourly_mtm())
        assert sched._last_mtm_timestamp is None, (
            "last_mtm stamped over zero persisted rows — canary is lying"
        )

    def test_stamped_when_any_lane_succeeds(self):
        with patch(
            "backend.services.portfolio_intelligence.reference_engine.mark_all_lanes",
            return_value={"conservative": 100_000.0, "balanced": None, "aggressive": None},
        ):
            asyncio.run(sched._hourly_mtm())
        assert sched._last_mtm_timestamp is not None


class TestExpectedNavDate:
    def test_weekday_premarket_expects_prior_session(self):
        now = datetime(2026, 6, 10, 9, 0, tzinfo=ET)  # Wed before close
        assert sched._expected_nav_date(now) == "2026-06-09"

    def test_weekday_postclose_expects_today(self):
        now = datetime(2026, 6, 10, 18, 0, tzinfo=ET)
        assert sched._expected_nav_date(now) == "2026-06-10"

    def test_weekend_expects_friday(self):
        now = datetime(2026, 6, 13, 12, 0, tzinfo=ET)  # Saturday
        assert sched._expected_nav_date(now) == "2026-06-12"

    def test_monday_premarket_skips_holiday_friday(self):
        # Fri 2026-06-19 is Juneteenth (NYSE closed) → Thu 18th is expected.
        now = datetime(2026, 6, 22, 9, 0, tzinfo=ET)  # Monday pre-market
        assert sched._expected_nav_date(now) == "2026-06-18"

    def test_holiday_itself_skips_back_to_prior_friday(self):
        # Mon 2026-09-07 is Labor Day; even post-close no row is due for it.
        now = datetime(2026, 9, 7, 18, 0, tzinfo=ET)
        assert sched._expected_nav_date(now) == "2026-09-04"


class TestNavFreshness:
    def _seed_lanes(self, db_path):
        from backend import db as db_module

        db_module.init_db(db_path)
        conn = db_module.get_connection(db_path)
        try:
            for lane in ("conservative", "balanced", "aggressive"):
                conn.execute(
                    "INSERT INTO paper_portfolios "
                    "(id, inception_date, inception_value, config_version) "
                    "VALUES (?, '2026-06-08', 100000.0, 'cfg')",
                    (lane,),
                )
            conn.commit()
        finally:
            conn.close()

    def test_per_lane_freshness_flags(self, tmp_path, monkeypatch):
        from backend import db as db_module

        fresh_db = tmp_path / "fresh.db"
        monkeypatch.setattr(db_module, "DB_PATH", fresh_db)
        self._seed_lanes(fresh_db)

        expected = sched._expected_nav_date()
        conn = db_module.get_connection(fresh_db)
        try:
            db_module.insert_nav(
                conn, "conservative", expected, 100_000.0, "cfg",
                expected + "T21:00:00",
            )
            db_module.insert_nav(
                conn, "balanced", "2020-01-01", 100_000.0, "cfg",
                "2020-01-01T21:00:00",
            )
            # aggressive: no rows at all
        finally:
            conn.close()

        out = sched.nav_freshness()
        assert out["expected_nav_date"] == expected
        assert out["lanes"]["conservative"]["fresh"] is True
        assert out["lanes"]["balanced"]["fresh"] is False
        assert out["lanes"]["aggressive"]["fresh"] is False
        assert out["lanes"]["aggressive"]["last_nav_date"] is None
        assert out["all_fresh"] is False

    def test_health_payload_includes_nav_block(self, tmp_path, monkeypatch):
        from backend import db as db_module

        fresh_db = tmp_path / "fresh.db"
        monkeypatch.setattr(db_module, "DB_PATH", fresh_db)
        self._seed_lanes(fresh_db)

        out = sched.scheduler_health()
        assert "nav" in out, "freshness block missing from canary payload"
        assert "all_fresh" in out["nav"]
        assert set(out["nav"]["lanes"]) == {"conservative", "balanced", "aggressive"}


class TestNoLivePricesGuard:
    def test_total_price_failure_does_not_persist_nav(self, tmp_path):
        from backend.db import get_connection, get_nav_series, init_db
        from backend.services.portfolio_intelligence.reference_engine import (
            initialize_lane,
            mark_lane_to_market,
        )

        db = tmp_path / "pi.db"
        init_db(db)
        initialize_lane("balanced", db_path=db, prices=_universe_prices(100.0))

        nav = mark_lane_to_market(
            "balanced", prices={}, as_of_date=date(2026, 6, 9), db_path=db,
        )
        assert nav is None

        conn = get_connection(db)
        try:
            assert get_nav_series(conn, "balanced") == [], (
                "flat all-cost-basis NAV row persisted on total price failure"
            )
        finally:
            conn.close()
