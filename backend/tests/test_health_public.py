"""The public health / providers / scheduler endpoints carry no internal detail.

`/api/health/full` used to print LLM spend, the last 50 WARNING lines, provider
failure reasons and absolute paths to anyone. These tests pin the split (S70,
2026-11-15): a coarse PUBLIC view for everyone, the FULL payload only for the
desktop control plane or an `X-Health-Token` holder, `/api/health` minimal, and
every consumer's field still present in the public view.
"""

from __future__ import annotations

import json
import logging
import re

import pytest
from fastapi.testclient import TestClient

from backend import observability as obs
from backend.main import app
from backend.services import health_public as hp

TOKEN = "test-health-token"
H = {"X-Health-Token": TOKEN}

#: Key names that must carry NO text in a public payload (null is allowed: the
#: subsystem rows keep the key so the frontend's types still hold).
BANNED_KEYS = {"reason", "error", "detail", "proof", "where", "probe", "message",
               "path", "root", "dir", "traceback", "exception", "cost_usd", "usd",
               "balance", "spend", "spent", "daily_budget", "calls_today",
               "recent_warnings", "llm", "fmp_budget", "credential_env", "credentials"}
BANNED_KEY_PATTERN = re.compile(
    r"(^|_)(usd|spend|spent|balance|traceback|exception|warnings?|secret|password|api_key)($|_)", re.I)


@pytest.fixture(autouse=True)
def _clean_observability():
    obs.reset_for_tests()
    yield
    obs.reset_for_tests()


@pytest.fixture
def client():
    return TestClient(app)


def walk(node, path=""):
    """Yield (path, key, value) for every dict entry, and (path, None, str) for
    every list string."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield path, k, v
            yield from walk(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, str):
                yield path, None, v
            yield from walk(v, f"{path}[{i}]")


def assert_public_clean(payload):
    """The recursive scan: no unsafe SHAPE in any string, no banned KEY with text."""
    for where, key, value in walk(payload):
        if isinstance(value, str):
            assert not hp.UNSAFE_SHAPES.search(value), (where, key, value)
        if key is not None:
            assert not BANNED_KEY_PATTERN.search(str(key)), (where, key)
            if key in BANNED_KEYS:
                assert value is None, f"banned key {key!r} carries a value at {where}: {value!r}"
    blob = json.dumps(payload)
    assert "Traceback" not in blob
    assert not re.search(r"[A-Za-z]:\\\\", blob)


# ---------------------------------------------------------------- public view

class TestPublicHealthFull:
    def test_public_by_default_and_clean(self, client):
        r = client.get("/api/health/full")
        assert r.status_code == 200
        body = r.json()
        assert body["view"] == "public"
        assert_public_clean(body)
        for gone in ("llm", "fmp_budget", "recent_warnings", "data_sources", "event_intel",
                     "overlay", "lppls", "paper_broker_targets"):
            assert gone not in body, gone

    def test_a_logged_path_and_traceback_never_reach_the_public_view(self, client):
        obs.install_log_buffer()
        logging.getLogger("aegis.test.leak").warning(
            "boom C:\\Users\\mrthn\\secret\\x.json Traceback /app/backend/data/y.jsonl $12.50")
        public = client.get("/api/health/full")
        assert "secret" not in public.text and "mrthn" not in public.text
        assert "recent_warnings" not in public.json()
        # ...but the token holder still has the log lines
        full = client.get("/api/health/detail", headers=H).json()
        assert any("boom" in w["message"] for w in full["recent_warnings"])

    def test_coarse_codes_replace_sentences(self, client, monkeypatch):
        from backend.services import accrual_canary as ac
        monkeypatch.setattr(ac, "health", lambda **k: {
            "status": "DEGRADED", "forecast_accrual": {
                "status": "DEGRADED", "reason": "0 new rows in /app/backend/data/x.jsonl"},
            "openclaw": {"status": "IDLE"}})
        pub = client.get("/api/health/full").json()
        assert "forecast_accrual" in pub["degraded_reasons"]
        assert all(" " not in c for c in pub["degraded_reasons"])
        full = client.get("/api/health/detail", headers=H).json()
        assert any("0 new rows" in r for r in full["degraded_reasons"])

    def test_projection_is_a_whitelist(self):
        """A key nobody added to the projection never appears, whatever it holds."""
        poisoned = {
            "status": "ok", "brand_new_block": {"secret": "C:\\Users\\x"},
            "deploy": {"commit": "abc", "version": "0.2.0", "started_at": "t",
                       "uptime_seconds": 5, "cache_status": "ready",
                       "process_rss_mb": 9.0, "env": "AEGIS_API_KEY"},
            "scheduler": {"running": True, "n_jobs": 12, "jobstore": "SQLAlchemyJobStore",
                          "error": "Traceback (most recent call last)", "reason": "x",
                          "next_runs": {"a": "t"}, "job_ids": ["a"],
                          "nav": {"all_fresh": True, "error": "/app/x.db",
                                  "expected_nav_date": "2026-01-02",
                                  "lanes": {"balanced": {"last_nav_date": "2026-01-02",
                                                         "fresh": True, "path": "/app/x"}}},
                          "jobs": {"status": "ok", "missing": [], "unexpected": [],
                                   "reason": "C:\\x"}},
            "track_record": {"inception_date": "2026-01-01", "age_days": 3,
                             "error": "/app/db", "lanes": {"balanced": {
                                 "last_date": "d", "nav": 1.0, "since_inception_pct": 0.1,
                                 "private": 1}}},
            "prediction_ledger": {"status": "ok", "problems": ["/app/a.jsonl"],
                                  "persistence": {"data_dir": "/app/data"}},
            "forecast_populations": {"status": "ok", "populations": {
                "live_forward": {"status": "ok", "days_quiet": 0, "path": "/app/a.jsonl",
                                 "reason": "r"}}},
            "fred_health": {"status": "ok", "critical_series": ["a"], "fetch_passes": 2,
                            "by_status": {"OK": ["a"]}, "last_no_fetch_reason": "FRED_API_KEY",
                            "series": {"a": {"last_value": 1}}},
            "llm": {"usd_today": 3.2}, "recent_warnings": [{"message": "x"}],
            "subsystems": {"generated_utc": "t", "source": "pc_request", "counts": {},
                           "exit_code": 0, "error": "Traceback", "rows": [
                               {"name": "n", "verdict": "ALIVE", "state": "ALIVE_PROGRESSING",
                                "detail": "C:\\Users\\x", "proof": "/app/a", "where": "/app",
                                "probe": "p", "alarm": {"light": "GREEN", "status": "HEALTHY",
                                                        "healthy": True, "reason": "/app/x"}}],
                           "alarm": {"schema": "health_alarm/1", "light": "GREEN",
                                     "reason": "/app/x"}},
        }
        pub = hp.public_health_full(poisoned, ["nav_not_fresh"])
        assert_public_clean(pub)
        blob = json.dumps(pub)
        for needle in ("brand_new_block", "jobstore", "SQLAlchemy", "Traceback", "/app",
                       "C:\\\\", "usd_today", "FRED_API_KEY", "private", "problems"):
            assert needle not in blob, needle
        assert pub["subsystems"]["rows"][0]["state"] == "ALIVE_PROGRESSING"  # words survive

    def test_withhold_unsafe_shapes(self):
        for bad in ("C:\\Users\\a\\b", "see /app/backend/x", "backend/data/x.jsonl",
                    "Traceback (most recent call last)", "cost $4.20", "spent 3 USD",
                    "FMP_API_KEY missing", "AEGIS_HEALTH_TOKEN"):
            assert hp.withhold_unsafe(bad) == hp.WITHHELD, bad
        for ok in ("ALIVE_PROGRESSING", "STOPPED_BY_OPERATOR", "2026-11-15T10:00:00+00:00",
                   "forecast_population:live_forward", "STRICT_FAILURE_VIEW/1", "nav_not_fresh"):
            assert hp.withhold_unsafe(ok) == ok, ok


# ------------------------------------------------------------- /api/health

class TestMinimalHealth:
    def test_health_answers_200_without_auth_with_a_minimal_body(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert set(body) == {"status", "version", "cache_ready", "cache_status", "git_head"}
        assert body["status"] == "ok"
        assert_public_clean(body)

    def test_cache_error_text_is_for_the_token_or_control_plane_only(self, client, monkeypatch):
        import backend.main as m
        monkeypatch.setattr(m, "cache_status",
                            lambda: {"status": "failed", "error": "C:\\x\\boom"})
        assert "cache_error" not in client.get("/api/health").json()
        # a control-plane (desktop loopback) request keeps the error text
        monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
        local = TestClient(app, base_url="http://127.0.0.1")
        assert "cache_error" in local.get("/api/health").json()


# ------------------------------------------------------- the access rule

class TestFullViewAccess:
    def test_detail_is_404_while_the_token_is_unset(self, client, monkeypatch):
        monkeypatch.delenv("AEGIS_HEALTH_TOKEN", raising=False)
        monkeypatch.delenv("AEGIS_CONTROL_ENABLED", raising=False)
        assert client.get("/api/health/detail").status_code == 404
        assert client.get("/api/health/detail", headers=H).status_code == 404

    def test_detail_needs_the_right_token(self, client):
        assert client.get("/api/health/detail").status_code == 403
        assert client.get("/api/health/detail",
                          headers={"X-Health-Token": "nope"}).status_code == 403
        r = client.get("/api/health/detail", headers=H)
        assert r.status_code == 200 and r.json()["view"] == "full"

    def test_a_token_makes_full_also_serve_the_full_view(self, client):
        assert client.get("/api/health/full", headers=H).json()["view"] == "full"
        assert client.get("/api/health/full",
                          headers={"X-Health-Token": "nope"}).json()["view"] == "public"

    def test_token_compare_is_constant_time(self):
        import inspect
        assert "compare_digest" in inspect.getsource(hp.token_state)

    def test_desktop_control_plane_gets_the_full_view_remote_does_not(self, monkeypatch):
        monkeypatch.delenv("AEGIS_HEALTH_TOKEN", raising=False)
        monkeypatch.setenv("AEGIS_CONTROL_ENABLED", "1")
        local = TestClient(app, base_url="http://127.0.0.1")
        assert local.get("/api/health/full").json()["view"] == "full"
        assert local.get("/api/health/detail").status_code == 200
        remote = TestClient(app)          # Host "testserver" is not loopback
        assert remote.get("/api/health/full").json()["view"] == "public"
        assert remote.get("/api/health/detail").status_code == 403

    def test_control_plane_off_means_no_full_view_without_a_token(self, monkeypatch):
        monkeypatch.delenv("AEGIS_HEALTH_TOKEN", raising=False)
        monkeypatch.delenv("AEGIS_CONTROL_ENABLED", raising=False)
        local = TestClient(app, base_url="http://127.0.0.1")
        assert local.get("/api/health/full").json()["view"] == "public"


# ------------------------------------------------- providers and scheduler

class TestProvidersAndScheduler:
    def test_providers_public_has_no_failure_reason(self, client):
        body = client.get("/api/providers").json()
        assert body["view"] == "public"
        assert_public_clean(body)
        for p in body["providers"]:
            assert set(p) == {"name", "available", "capabilities"}
        assert "priority" in body

    def test_providers_full_view_keeps_the_reason(self, client):
        body = client.get("/api/providers", headers=H).json()
        assert body["view"] == "full"
        assert all("reason" in p for p in body["providers"])

    def test_scheduler_canary_keeps_its_status_code_and_drops_internals(self, client):
        r = client.get("/health/scheduler")
        assert r.status_code in (200, 503)
        body = r.json()
        assert_public_clean(body)
        for gone in ("jobstore", "job_ids", "next_runs", "reason", "error"):
            assert gone not in body
        full = client.get("/health/scheduler", headers=H)
        assert full.status_code == r.status_code
        assert "jobstore" in full.json()


# ------------------------------------------------------ the consumers

class TestConsumersStillSatisfied:
    """Each consumer's fields, read from the PUBLIC body."""

    def pub(self, client):
        return client.get("/api/health/full").json()

    def test_prod_monitor_fields(self, client):
        b = self.pub(client)
        # .github/workflows/prod-monitor.yml
        assert isinstance(b["status"], str)
        assert "all_fresh" in b["scheduler"]["nav"]
        assert isinstance(b["prediction_ledger"]["status"], str)
        assert isinstance(b["degraded_reasons"], list)

    def test_session_state_fields(self, client):          # scripts/session_state.py
        b = self.pub(client)
        assert "commit" in b["deploy"]
        assert "status" in b["scheduler"]["jobs"]
        assert "all_fresh" in b["scheduler"]["nav"]

    def test_control_paper_snapshot_fields(self, client):  # routers/control.py
        tr = self.pub(client)["track_record"]
        assert {"lanes", "inception_date", "age_days"} <= set(tr)

    def test_system_health_probes_read_the_public_body(self, client):
        from backend.services import system_health as SH
        body = self.pub(client)

        class Ctx:
            railway_url = "https://example.invalid"
            now = SH._utcnow()
            http_json = staticmethod(lambda url, t: (body, 0.1, None))

        r = SH.p_railway_backend(Ctx())
        assert r.verdict in ("ALIVE", "STALE"), r      # not UNKNOWN: no field went missing
        f = SH.p_fred_macro_inputs(Ctx())
        assert "lacks" not in (f.detail or ""), f

    def test_frontend_fields_exist(self, client):        # dev / brain / health pages
        b = self.pub(client)
        assert {"commit", "uptime_seconds", "cache_status"} <= set(b["deploy"])
        assert "running" in b["scheduler"] and "n_jobs" in b["scheduler"]
        assert b["subsystems"]["alarm"]["schema"] == "health_alarm/1"
        assert "generated_utc" in b["subsystems"]
        for key in ("llm", "recent_warnings", "event_intel"):
            assert key not in b    # the dev page reads these as OPTIONAL (`h?.llm ?`)

    def test_deep_consumers_declare_that_they_need_the_token(self):
        """monday_gate_check reads deep fields; it must go to /detail and refuse
        (CANNOT DETERMINE) on a public body rather than read missing fields."""
        src = open("scripts/monday_gate_check.py", encoding="utf-8").read()
        assert "/api/health/detail" in src and "X-Health-Token" in src
        assert 'health.get("view") == "public"' in src
