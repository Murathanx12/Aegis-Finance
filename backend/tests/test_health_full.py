"""
/api/health/full — the one-call session status endpoint (V2 observability).

Covers: ring buffer capture + cap, source-health counters + rates,
endpoint aggregation shape, and per-lane since-inception delta math.
"""

import logging

import pytest
from fastapi.testclient import TestClient

from backend import observability as obs
from backend.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_observability():
    obs.reset_for_tests()
    yield
    obs.reset_for_tests()


class TestRingBuffer:
    def test_warning_is_captured_info_is_not(self):
        obs.install_log_buffer()
        log = logging.getLogger("aegis.test.ring")
        log.warning("ring-buffer-test-warning")
        log.info("ring-buffer-test-info")
        messages = [r["message"] for r in obs.recent_warnings()]
        assert "ring-buffer-test-warning" in messages
        assert "ring-buffer-test-info" not in messages

    def test_buffer_capped_at_50(self):
        obs.install_log_buffer()
        log = logging.getLogger("aegis.test.cap")
        for i in range(60):
            log.warning("w%d", i)
        records = obs.recent_warnings()
        assert len(records) == 50
        assert records[-1]["message"] == "w59"  # newest kept
        assert records[0]["message"] == "w10"   # oldest dropped

    def test_install_is_idempotent(self):
        obs.install_log_buffer()
        obs.install_log_buffer()
        root = logging.getLogger()
        n = sum(isinstance(h, obs.RingBufferHandler) for h in root.handlers)
        assert n == 1


class TestSourceHealth:
    def test_yfinance_success_rate(self):
        obs.record_yfinance_batch(fetched=9, requested=10)
        obs.record_yfinance_batch(fetched=10, requested=10)
        s = obs.source_health()["yfinance"]
        assert s["batches"] == 2
        assert s["success_rate"] == pytest.approx(0.95)
        assert s["last_batch"] == {"fetched": 10, "requested": 10}

    def test_fred_series_names(self):
        obs.record_fred_fetch(loaded=["nfci", "cpi"], failed=["gpr_world"])
        s = obs.source_health()["fred"]
        assert s["series_loaded"] == ["cpi", "nfci"]
        assert s["series_failed"] == ["gpr_world"]
        assert s["n_loaded"] == 2 and s["n_failed"] == 1

    def test_empty_state_has_no_rate(self):
        s = obs.source_health()
        assert s["yfinance"]["success_rate"] is None
        assert s["fred"]["n_loaded"] == 0


class TestHealthFullEndpoint:
    def test_shape(self):
        response = client.get("/api/health/full")
        assert response.status_code == 200
        body = response.json()
        for key in ("status", "deploy", "scheduler", "track_record",
                    "data_sources", "recent_warnings"):
            assert key in body, f"missing key: {key}"
        for key in ("commit", "version", "started_at", "uptime_seconds"):
            assert key in body["deploy"]
        assert "nav" in body["scheduler"], "scheduler block must carry freshness"
        assert isinstance(body["recent_warnings"], list)

    def test_lane_delta_math(self, tmp_path, monkeypatch):
        from backend import db as db_module

        fresh_db = tmp_path / "h.db"
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
            db_module.insert_nav(conn, "balanced", "2026-06-10", 100618.85,
                                 "cfg", "2026-06-10T20:30:00")
        finally:
            conn.close()

        body = client.get("/api/health/full").json()
        tr = body["track_record"]
        assert tr["inception_date"] == "2026-06-08"
        assert tr["age_days"] >= 2
        balanced = tr["lanes"]["balanced"]
        assert balanced["nav"] == pytest.approx(100618.85)
        assert balanced["since_inception_pct"] == pytest.approx(0.619, abs=0.001)
        # Lane with no NAV rows yet is present with explicit nulls.
        assert tr["lanes"]["conservative"]["nav"] is None

    def test_warnings_flow_through(self):
        obs.install_log_buffer()
        logging.getLogger("aegis.test.flow").warning("endpoint-flow-check")
        body = client.get("/api/health/full").json()
        assert any("endpoint-flow-check" in r["message"]
                   for r in body["recent_warnings"])


class TestGprRemoval:
    def test_gpr_world_absent_from_config(self):
        from backend.config import config
        assert "gpr_world" not in config["data"]["fred_series"], (
            "GPRH does not exist on FRED — entry must stay removed "
            "(see config.py note); re-adding a proxy is an evolution-loop item"
        )
