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
BANNED_KEYS = {"reason", "error", "detail", "proof", "where", "message",
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
            assert not hp._unsafe(value), (where, key, value)
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
                    "FMP_API_KEY missing", "AEGIS_HEALTH_TOKEN", "ALPACA_SECRET_KEY", "APCA_API_KEY_ID",
                    "NVIDIA_NIM_API_KEY", "sk-abcdefghijklmnop1234", "12.34 dollars",
                    "db.internal.example:5432", "10.0.0.5", "KeyError: 'x'",
                    "/workspace/a/b", "~/.openclaw/openclaw.json", "bill held at $20",
                    "A" * 60):
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

    def test_detail_404s_the_same_whether_or_not_a_token_is_set(self, client):
        """Do not reveal whether a token is configured: missing and wrong are 404."""
        a = client.get("/api/health/detail")
        b = client.get("/api/health/detail", headers={"X-Health-Token": "nope"})
        assert a.status_code == b.status_code == 404
        assert a.json() == b.json() == {"detail": "Not Found"}
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
        assert remote.get("/api/health/detail").status_code == 404

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


# ------------------------------------------- handler-level poison (reviewer)

POISONS = [
    "POISON C:\\Users\\mrthn\\x.json", "POISON /app/backend/data/x.jsonl", "POISON /workspace/a/b",
    "POISON Traceback (most recent call last)", "POISON sk-abcdefghijklmnop1234",
    "POISON 12.34 dollars", "POISON db.internal.example:5432", "POISON KeyError: 'x'",
    "POISON ALPACA_SECRET_KEY", "POISON APCA_API_KEY_ID", "POISON NVIDIA_NIM_API_KEY",
    "POISON bill held at $20", "POISON " + "A" * 60, "POISON ~/.openclaw/openclaw.json",
]


class _Poisoner:
    def __init__(self):
        self.i = 0

    def next(self):
        self.i += 1
        return POISONS[self.i % len(POISONS)]

    def __call__(self, v, depth=0):
        if isinstance(v, str):
            return self.next()
        if isinstance(v, dict):
            out = {k: self(x, depth + 1) for k, x in v.items()}
            if v and all(isinstance(x, dict) for x in v.values()):
                out[self.next()] = self(next(iter(v.values())), depth + 1)   # a poisoned MAP KEY (row)
            else:
                out[self.next()] = self.next()                    # a poisoned MAP KEY
            if depth < 4:
                out["extra"] = {self.next(): {self.next(): self.next()}}   # nested extras
            return out
        if isinstance(v, (list, tuple)):
            return [self(x, depth + 1) for x in v] + [self.next()]
        return v


@pytest.fixture
def poisoned(monkeypatch):
    """Every collector the health handlers call returns its real output with every
    string, every map key and every nested dict replaced/extended by poison."""
    import importlib
    P = _Poisoner()
    targets = [
        ("backend.services.portfolio_intelligence.scheduler", "scheduler_health"),
        ("backend.services.portfolio_intelligence.scheduler", "overlay_status"),
        ("backend.services.portfolio_intelligence.scheduler", "lppls_status"),
        ("backend.services.llm_analyzer", "llm_usage"),
        ("backend.services.fmp_budget", "snapshot"),
        ("backend.observability", "event_intel_stats"),
        ("backend.observability", "source_health"),
        ("backend.observability", "recent_warnings"),
        ("backend.services.belief_state", "ledger_health"),
        ("backend.services.event_store", "health"),
        ("backend.services.portfolio_intelligence.paper_broker_targets", "health"),
        ("backend.services.portfolio_intelligence.execution_ledger", "health"),
        ("backend.services.options_pit_store", "health"),
        ("backend.services.arena.information_bus", "health"),
        ("backend.services.arena.selector_identity", "health"),
        ("backend.services.forecast_populations", "registry_health"),
        ("backend.services.investment_committee", "ic_health"),
        ("backend.services.fred_health", "health"),
        ("backend.services.accrual_canary", "health"),
        ("backend.services.system_health", "api_block"),
    ]
    for mod, name in targets:
        m = importlib.import_module(mod)
        orig = getattr(m, name)

        def make(orig):
            return lambda *a, **k: P(orig(*a, **k))
        monkeypatch.setattr(m, name, make(orig))
    from backend.services.providers import registry
    from types import SimpleNamespace as NS
    monkeypatch.setattr(registry, "health", lambda: [
        NS(name=P.next(), available=True, reason=P.next(), capabilities=[P.next(), "equity_history"])
        for _ in range(3)])
    monkeypatch.setattr(registry, "_priority", P({"equity_history": ["yfinance"]}))
    import backend.main as m
    monkeypatch.setattr(m, "cache_status", lambda: {"status": P.next(), "error": P.next()})
    monkeypatch.setattr(m, "git_head", lambda: P.next())
    return P


@pytest.mark.parametrize("path", ["/api/health", "/api/health/full", "/api/providers",
                                  "/health/scheduler"])
def test_handler_level_poison_never_reaches_a_public_response(client, poisoned, path):
    r = client.get(path)
    assert r.status_code in (200, 503), r.text[:200]
    assert "POISON" not in r.text, [ln for ln in r.text.split('"') if "POISON" in ln][:3]
    for needle in ("Traceback", "sk-abc", "KeyError", "ALPACA", "APCA_", "NVIDIA_NIM",
                   "/workspace", "/app/", "dollars", "5432", "openclaw.json"):
        assert needle not in r.text, needle
    assert_public_clean(r.json())


def test_poison_in_map_keys_is_dropped_and_counted(client, poisoned):
    body = client.get("/api/health/full").json()
    assert body["withheld_keys"] > 0


def test_health_cache_status_is_a_fixed_word_and_git_head_a_hash(client, poisoned):
    body = client.get("/api/health").json()
    assert body["cache_status"] == "other" and body["git_head"] is None


def test_scalar_only_pick_drops_containers_under_scalar_keys():
    full = {"status": "ok", "scheduler": {"running": True, "last_mtm": {"x": "C:\\a"},
                                           "jobs": {"status": {"a": 1}, "missing": [{"k": 1}, "ok_id"]}},
            "deploy": {"commit": {"a": 1}, "version": "0.2.0"},
            "subsystems": {"counts": {"ALIVE": 3, "bad key with spaces": 1, "nested": {"a": 1}},
                           "rows": [{"name": "n", "alarm": {"light": "RED", "evidence_calendar": {"a": 1},
                                                            "light_counts": {"RED": 1, "C:\\x": 2}}}]}}
    pub = hp.public_health_full(full, ["fine_code", "has spaces here"])
    assert pub["scheduler"]["last_mtm"] is None
    assert pub["scheduler"]["jobs"]["status"] is None
    assert pub["scheduler"]["jobs"]["missing"] == ["ok_id"]
    assert "commit" not in pub["deploy"]
    assert pub["subsystems"]["counts"] == {"ALIVE": 3}
    assert pub["degraded_reasons"] == ["fine_code"]
    assert pub["subsystems"]["rows"][0]["alarm"]["light_counts"] == {"RED": 1}
    assert "evidence_calendar" not in pub["subsystems"]["rows"][0]["alarm"]
    assert pub["withheld_keys"] >= 5


# ------------------------------------------------ legibility system-health

class TestLegibilitySystemHealth:
    def test_public_projection_nulls_text_and_keeps_words(self):
        row = {"name": "x", "probe": "p", "where": "/app/x", "verdict": "DEAD", "state": "DEAD",
               "detail": "bill held at $20 C:\\a", "proof": "backend/data/x.jsonl",
               "evidence": "~/.openclaw/a.json",
               "evidence_utc": "2026-01-01T00:00:00+00:00", "age_s_at_probe": 5, "age_s_now": 9,
               "same_output": False, "missing_because": "Traceback", "alarm": {"light": "RED", "reason": "x"}}
        payload = {"schema": "legibility/2", "page": "system_health", "status": "STALE",
                   "served_from": "public_receipts/system_health/latest.json", "exit_code": 1,
                   "counts": {"DEAD": 1, "ALIVE": 2}, "health_line": "C:\\x", "read_me_first": "see /app/x",
                   "receipts": [{"kind": "system_health", "file": "optimus/health/h.json", "line": "x /app",
                                 "stamp_utc": "t", "age_hours": 1.0, "stale_after_hours": 26.0,
                                 "status": "STALE"}],
                   "groups": [{"verdict": "DEAD", "n": 1, "states": {"DEAD": 1}, "rows": [row]}],
                   "process_census": [row], "same_output_rows": [],
                   "task_owners": [{"task": "T", "receipt": "night_factory_<d>/a.json", "state": "DEAD",
                                    "verdict": "DEAD", "detail": "/app/x", "cadence_h": 24.0,
                                    "hash_rule_off": "because /app", "alarm": {"light": "RED"}}]}
        pub = hp.public_system_health(payload)
        assert_public_clean(pub)
        r = pub["groups"][0]["rows"][0]
        assert (r["detail"], r["proof"], r["where"], r["evidence"], r["missing_because"]) == (None,) * 5
        assert r["verdict"] == "DEAD" and r["alarm"] == {"light": "RED"}
        assert pub["receipts"][0]["file"] is None and pub["receipts"][0]["status"] == "STALE"
        assert pub["task_owners"][0]["receipt"] is None
        assert pub["health_line"].startswith("health rc 1")
        assert pub["read_me_first"] is None

    def test_route_serves_the_projection_publicly_and_the_receipt_to_the_token(self, client):
        pub = client.get("/api/legibility/v1/system-health")
        if pub.status_code == 404:
            pytest.skip("no system_health receipt in this checkout")
        body = pub.json()
        assert body["view"] == "public"
        assert_public_clean(body)
        for g in body["groups"]:
            for r in g["rows"]:
                assert r["detail"] is None and r["proof"] is None and r["where"] is None
        full = client.get("/api/legibility/v1/system-health", headers=H).json()
        assert full.get("view") != "public"
