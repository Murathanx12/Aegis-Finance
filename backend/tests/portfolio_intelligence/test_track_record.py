"""
GET /api/pi/track-record — the canonical live forward track record (P0 #2).

Asserts: real NAV rows round-trip per lane with config_version, benchmark
overlays normalize to exactly the notional at inception, the 60/40 blend is
between SPY and AGG cumulative paths, and freshness/intraday flags surface.
"""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def _seed(tmp_path, monkeypatch, nav_rows_by_lane):
    from backend import db as db_module

    fresh_db = tmp_path / "tr.db"
    monkeypatch.setattr(db_module, "DB_PATH", fresh_db)
    db_module.init_db(fresh_db)
    conn = db_module.get_connection(fresh_db)
    try:
        for lane in ("conservative", "balanced", "aggressive"):
            conn.execute(
                "INSERT INTO paper_portfolios "
                "(id, inception_date, inception_value, config_version) "
                "VALUES (?, '2026-06-08', 100000.0, 'cfg')",
                (lane,),
            )
        conn.commit()
        for lane, rows in nav_rows_by_lane.items():
            for d, nav, cfg in rows:
                db_module.insert_nav(conn, lane, d, nav, cfg, d + "T21:00:00")
    finally:
        conn.close()


def _benchmark_prices():
    idx = pd.date_range("2026-06-01", "2026-06-10", freq="B")
    spy = pd.Series(np.linspace(600.0, 612.0, len(idx)), index=idx)
    agg = pd.Series(np.linspace(98.0, 98.5, len(idx)), index=idx)
    return spy, agg


class TestTrackRecord:
    def test_lanes_and_benchmarks(self, tmp_path, monkeypatch):
        _seed(tmp_path, monkeypatch, {
            "balanced": [
                ("2026-06-08", 100000.0, "cfgA"),
                ("2026-06-09", 100618.85, "cfgA"),
                ("2026-06-10", 100070.91, "cfgB"),  # segment boundary
            ],
        })
        spy, agg = _benchmark_prices()

        def fake_fetch(ticker, start, end, name=None):
            return spy if ticker == "SPY" else agg

        with patch("backend.cache.cache_get", return_value=None), \
             patch("backend.cache.cache_set"), \
             patch("backend.services.data_fetcher.fetch_safe",
                   side_effect=fake_fetch):
            response = client.get("/api/pi/track-record")

        assert response.status_code == 200, response.text
        body = response.json()

        assert body["inception_date"] == "2026-06-08"
        assert body["age_days"] >= 2

        balanced = body["lanes"]["balanced"]
        assert [(p["date"], p["value"]) for p in balanced] == [
            ("2026-06-08", 100000.0),
            ("2026-06-09", 100618.85),
            ("2026-06-10", 100070.91),
        ]
        assert [p["config_version"] for p in balanced] == ["cfgA", "cfgA", "cfgB"]
        assert body["lanes"]["conservative"] == []  # no rows yet → empty, explicit

        # Benchmarks normalized: first point ON/after inception == notional.
        for name in ("SPY", "AGG", "60_40"):
            series = body["benchmarks"][name]
            assert series[0]["date"] == "2026-06-08"
            assert series[0]["value"] == pytest.approx(100000.0)

        # 60/40 final value sits between SPY and AGG cumulative paths.
        last = {n: body["benchmarks"][n][-1]["value"] for n in ("SPY", "AGG", "60_40")}
        lo, hi = sorted((last["SPY"], last["AGG"]))
        assert lo <= last["60_40"] <= hi

        # SPY normalization math: 612/spy(06-08) — verify against fixture.
        spy_0608 = float(spy[pd.Timestamp("2026-06-08")])
        expected_last = round(612.0 / spy_0608 * 100000.0, 2)
        assert last["SPY"] == pytest.approx(expected_last)

    def test_freshness_and_note_fields_present(self, tmp_path, monkeypatch):
        _seed(tmp_path, monkeypatch, {})
        # Disk cache outlives cache_clear() — force a miss so the patched
        # (down) fetch path is actually exercised.
        with patch("backend.cache.cache_get", return_value=None), \
             patch("backend.services.data_fetcher.fetch_safe",
                   return_value=None):  # benchmark fetch down → empty overlays
            body = client.get("/api/pi/track-record").json()
        assert "all_fresh" in body and body["all_fresh"] is False  # no rows
        assert body["benchmarks"] == {}
        assert "60/40" in body["benchmark_note"] or "60%" in body["benchmark_note"]
