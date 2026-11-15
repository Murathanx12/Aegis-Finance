"""Usage receipt: privacy, monitor exclusion, flag gating, caps, token guard."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from backend.config import config
from backend.middleware import add_timing_middleware
from backend.routers import usage as usage_router
from backend.services import usage_receipt as ur

SITE = "https://site.example"
HUMAN_UA = "Mozilla/5.0 (X11; Linux x86_64) Chrome/120 Safari/537"
TOKEN = "t0ken-for-tests"


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2030, 1, 15, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv(ur.ENV_FLAG, "1")
    monkeypatch.setenv(ur.ENV_TOKEN, TOKEN)
    monkeypatch.delenv(ur.ENV_DIR, raising=False)


def build_app(clock) -> FastAPI:
    """Built AFTER the flag is set/unset, as at startup."""
    app = FastAPI()
    app.state.cors_origins = [SITE]
    app.add_middleware(CORSMiddleware, allow_origins=[SITE], allow_methods=["*"], allow_headers=["*"])
    add_timing_middleware(app)
    usage_router.register(app)

    @app.get("/api/stock/{ticker}")
    def stock(ticker: str):
        return {"t": ticker}

    @app.get("/api/health/full")
    def health():
        return {"ok": True}

    @app.get("/api/market")
    def market():
        return {"ok": True}

    ur.reset_recorder_for_tests(ur.UsageRecorder(clock=clock))
    return app


@pytest.fixture
def client(env, clock):
    yield TestClient(build_app(clock))
    ur.reset_recorder_for_tests(None)


def summary(c):
    return c.get("/api/usage/summary", headers={"x-usage-token": TOKEN})


def test_flag_off_route_absent_and_middleware_inert(monkeypatch, clock):
    monkeypatch.delenv(ur.ENV_FLAG, raising=False)
    monkeypatch.setenv(ur.ENV_TOKEN, TOKEN)
    app = build_app(clock)
    c = TestClient(app)
    c.get("/api/market", headers={"user-agent": HUMAN_UA})
    assert c.get("/api/usage/summary", headers={"x-usage-token": TOKEN}).status_code == 404
    for method in ("get", "post", "put", "delete", "options"):
        assert getattr(c, method)("/api/usage/pageview").status_code == 404, method
    assert not any("/api/usage" in p for p in c.get("/openapi.json").json()["paths"])
    rec = ur.get_recorder()
    assert rec._today.human_requests == 0 and rec._today.requests == {}


def test_flag_on_route_present_in_openapi(client):
    assert "/api/usage/summary" in client.get("/openapi.json").json()["paths"]


def test_monitor_only_traffic_has_zero_humans(client):
    for _ in range(5):
        client.get("/api/health/full", headers={"user-agent": "curl/8.4.0"})
    client.get("/api/market", headers={"user-agent": "curl/8.4.0"})
    t = summary(client).json()["today"]
    assert t["distinct_visitors_upper_bound"] == 0
    assert t["human_requests"] == 0
    assert t["monitor_requests"] == 6
    assert t["routes"] == {}


def test_bots_counted_apart_and_health_by_human_ua_is_monitor(client):
    client.get("/api/market", headers={"user-agent": "Googlebot/2.1"})
    client.get("/api/health/full", headers={"user-agent": HUMAN_UA})
    t = summary(client).json()["today"]
    assert t["bot_requests"] == 1 and t["monitor_requests"] == 1 and t["human_requests"] == 0


def test_same_visitor_twice_is_one_and_templating(client, monkeypatch):
    monkeypatch.setitem(config["usage_receipt"], "ticker_min_visitors", 1)
    monkeypatch.setitem(config["usage_receipt"], "ticker_min_requests", 1)
    h = {"user-agent": HUMAN_UA, "x-real-ip": "203.0.113.9"}
    client.get("/api/stock/NVDA", headers=h)
    client.get("/api/stock/AMD", headers=h)
    client.get("/api/stock/nvda", headers=h)
    t = summary(client).json()["today"]
    assert t["distinct_visitors_upper_bound"] == 1
    assert list(t["routes"]) == ["/api/stock/{ticker}"]
    assert t["routes"]["/api/stock/{ticker}"] == {"2xx": 3}
    assert t["tickers_top"][0] == {"ticker": "NVDA", "requests": 2}
    assert {"ticker": "AMD", "requests": 1} in t["tickers_top"]


def test_ticker_table_suppressed_below_thresholds(client):
    h = {"user-agent": HUMAN_UA, "x-real-ip": "203.0.113.9"}
    for _ in range(6):
        client.get("/api/stock/ZZXQ", headers=h)
    t = summary(client).json()["today"]
    assert t["tickers_top"] == [] and t["tickers_suppressed_rows"] == 1  # one visitor only
    for i in range(5):
        client.get("/api/stock/ZZXQ", headers={"user-agent": HUMAN_UA, "x-real-ip": f"198.51.100.{i}"})
    client.get("/api/stock/AMD", headers=h)
    t = summary(client).json()["today"]
    assert t["tickers_top"] == [{"ticker": "ZZXQ", "requests": 11}]
    assert t["tickers_suppressed_rows"] == 1  # AMD has 1 request


def test_user_agent_rotation_is_one_visitor(client):
    for i in range(30):
        client.get("/api/market", headers={"user-agent": f"Mozilla/5.0 Rot{i}", "x-real-ip": "203.0.113.5"})
    assert summary(client).json()["today"]["distinct_visitors_upper_bound"] == 1


def test_beacon_limit_keyed_on_ip_not_ua(client, monkeypatch):
    monkeypatch.setitem(config["usage_receipt"], "beacon_per_visitor_per_min", 2)
    codes = [client.post("/api/usage/pageview", json={"path": "/"},
                         headers={"origin": SITE, "user-agent": f"Mozilla/5.0 R{i}",
                                  "x-real-ip": "203.0.113.5"}).status_code for i in range(4)]
    assert codes == [204, 204, 429, 429]


def test_address_shape_reports_counts_not_values(client):
    client.get("/api/market", headers={"user-agent": HUMAN_UA, "x-real-ip": "203.0.113.5",
                                       "x-forwarded-for": "6.6.6.6, 7.7.7.7"})
    client.get("/api/market", headers={"user-agent": HUMAN_UA})
    body = summary(client)
    shape = body.json()["today"]["address_header_shape"]
    assert shape["used_x-real-ip"] == 1 and shape["used_peer"] == 1
    assert shape["xff_entries_2"] == 1 and shape["xff_entries_0"] == 1
    for v in ("203.0.113.5", "6.6.6.6", "7.7.7.7"):
        assert v not in body.text


def test_exclusion_list_moves_server_side_callers_out_of_humans(client, monkeypatch):
    monkeypatch.setitem(config["usage_receipt"], "exclude_ua_substrings", ["node-frontend"])
    monkeypatch.setitem(config["usage_receipt"], "exclude_ip_prefixes", ["192.0.2."])
    client.get("/api/market", headers={"user-agent": "node-frontend/1", "x-real-ip": "203.0.113.5"})
    client.get("/api/market", headers={"user-agent": HUMAN_UA, "x-real-ip": "192.0.2.44"})
    t = summary(client).json()["today"]
    assert t["excluded_requests"] == 2 and t["human_requests"] == 0
    assert "frontend host" in summary(client).json()["note"]


def test_flush_interval_checked_before_directory_stat(clock, tmp_path, monkeypatch):
    monkeypatch.setenv(ur.ENV_DIR, str(tmp_path))
    rec = ur.UsageRecorder(clock=clock, monotonic=lambda: 1000.0)
    kw = dict(route="/r", path_params={}, status=200, ip="1.1.1.1", user_agent=HUMAN_UA, raw_path="/r")
    rec.record_request(**kw)  # first flush due
    calls = []
    real = ur.UsageRecorder._receipt_dir
    monkeypatch.setattr(ur.UsageRecorder, "_receipt_dir", staticmethod(lambda: calls.append(1) or real()))
    for _ in range(20):
        rec.record_request(**kw)
    assert calls == []


def test_lock_not_held_during_file_write(clock, tmp_path, monkeypatch):
    monkeypatch.setenv(ur.ENV_DIR, str(tmp_path))
    rec = ur.UsageRecorder(clock=clock)
    held = []
    real = ur.UsageRecorder._write_receipt

    def spy(self, *a, **k):
        held.append(self._lock.locked())
        return real(self, *a, **k)

    monkeypatch.setattr(ur.UsageRecorder, "_write_receipt", spy)
    rec.record_request(route="/r", path_params={}, status=200, ip="1.1.1.1", user_agent=HUMAN_UA, raw_path="/r")
    assert held == [False]


def test_different_ip_is_different_visitor_and_status_class(client):
    client.get("/api/market", headers={"user-agent": HUMAN_UA, "x-real-ip": "198.51.100.1"})
    client.get("/api/market", headers={"user-agent": HUMAN_UA, "x-real-ip": "198.51.100.2"})
    client.get("/api/nope", headers={"user-agent": HUMAN_UA, "x-real-ip": "198.51.100.2"})
    t = summary(client).json()["today"]
    assert t["distinct_visitors_upper_bound"] == 2
    assert t["routes"]["unmatched"] == {"4xx": 1}


def test_x_real_ip_else_peer_never_xff():
    assert ur.client_ip({"x-real-ip": "203.0.113.9", "x-forwarded-for": "6.6.6.6, 7.7.7.7"}, "10.0.0.1") == "203.0.113.9"
    assert ur.client_ip({"x-forwarded-for": "6.6.6.6, 7.7.7.7"}, "10.0.0.1") == "10.0.0.1"
    assert ur.client_ip({}, "10.0.0.1") == "10.0.0.1"


def test_day_rollover_rotates_key_and_hashes_not_linkable(clock):
    rec = ur.UsageRecorder(clock=clock)
    kw = dict(route="/r", path_params={}, status=200, ip="203.0.113.9", user_agent=HUMAN_UA, raw_path="/r")
    rec.record_request(**kw)
    key1, hashes1 = rec._today.key, set(rec._today.visitors)
    assert len(hashes1) == 1
    clock.now += timedelta(days=1)
    rec.record_request(**kw)
    assert rec._today.key != key1
    assert not (hashes1 & rec._today.visitors)
    yesterday = rec.summary()["previous_days_this_process"][0]
    assert yesterday["distinct_visitors_upper_bound"] == 1
    # a new recorder (restart) derives unrelated hashes too
    rec2 = ur.UsageRecorder(clock=clock)
    rec2.record_request(**kw)
    assert not (rec2._today.visitors & rec._today.visitors)


def test_no_identifier_in_summary_receipt_or_logs(client, tmp_path, monkeypatch, caplog):
    monkeypatch.setenv(ur.ENV_DIR, str(tmp_path))
    ip, ua = "203.0.113.77", "Mozilla/5.0 UniqueMarker/9.9 Chrome/120"
    with caplog.at_level(logging.DEBUG):
        client.get("/api/stock/NVDA", headers={"user-agent": ua, "x-real-ip": ip})
        client.post("/api/usage/pageview", json={"path": "/stock/NVDA"},
                    headers={"origin": SITE, "user-agent": ua, "x-real-ip": ip})
        body = summary(client).text
        path = ur.get_recorder().flush()
    rec = ur.get_recorder()
    hexes = [h.hex() for h in rec._today.visitors]
    key = rec._today.key.hex()
    assert len(hexes) == 1
    blob = body + path.read_text() + caplog.text + "\n".join(r.getMessage() for r in caplog.records)
    for secret in (ip, "UniqueMarker", key, *hexes):
        assert secret not in blob
    assert json.loads(path.read_text())["totals"]["distinct_visitors_upper_bound"] == 1


def test_beacon_allow_list_and_origin(client):
    ok = {"origin": SITE, "user-agent": HUMAN_UA}
    assert client.post("/api/usage/pageview", json={"path": "/stock/AAPL"}, headers=ok).status_code == 204
    for bad in ("/../etc/passwd", "/stock/NVDA?x=1", "/a/b/c/d", "https://x.com/", "/Stock", "/%2e", "", "/a b"):
        r = client.post("/api/usage/pageview", json={"path": bad}, headers=ok)
        assert r.status_code == 422, bad
    assert client.post("/api/usage/pageview", json={"path": "/", "extra": 1}, headers=ok).status_code == 422
    assert client.post("/api/usage/pageview", content=b"x" * 1000, headers=ok).status_code == 413
    assert client.post("/api/usage/pageview", json={"path": "/"},
                       headers={"origin": "https://evil.example", "user-agent": HUMAN_UA}).status_code == 403
    assert client.post("/api/usage/pageview", json={"path": "/"},
                       headers={"user-agent": HUMAN_UA}).status_code == 403
    t = summary(client).json()["today"]
    assert t["pageviews"] == {"/stock/{ticker}": 1}
    assert t["distinct_visitors_upper_bound"] == 1


def test_beacon_rate_limited(client, monkeypatch):
    monkeypatch.setitem(config["usage_receipt"], "beacon_per_visitor_per_min", 3)
    ok = {"origin": SITE, "user-agent": HUMAN_UA}
    codes = [client.post("/api/usage/pageview", json={"path": "/"}, headers=ok).status_code for _ in range(5)]
    assert codes == [204, 204, 204, 429, 429]


def test_visitor_cap(clock, monkeypatch):
    monkeypatch.setitem(config["usage_receipt"], "visitor_cap", 3)
    rec = ur.UsageRecorder(clock=clock)
    for i in range(10):
        rec.record_request(route="/r", path_params={}, status=200, ip=f"198.51.100.{i}",
                           user_agent=HUMAN_UA, raw_path="/r")
    t = rec.summary()["today"]
    assert t["distinct_visitors_upper_bound"] == ">=3" and t["distinct_visitors_capped"] is True
    assert t["human_requests"] == 10


def test_summary_requires_token(client, monkeypatch):
    assert client.get("/api/usage/summary").status_code == 403
    assert client.get("/api/usage/summary", headers={"x-usage-token": "wrong"}).status_code == 403
    monkeypatch.delenv(ur.ENV_TOKEN)
    assert client.get("/api/usage/summary", headers={"x-usage-token": ""}).status_code == 503
    assert client.get("/api/usage/summary", headers={"x-usage-token": TOKEN}).status_code == 503


def test_summary_states_since_process_start(client):
    s = summary(client).json()
    assert s["since_process_start"].endswith("Z") and s["persisted_to_disk"] is False


def test_receipt_file_written_only_with_dir_and_merges_segments(clock, tmp_path, monkeypatch):
    monkeypatch.delenv(ur.ENV_DIR, raising=False)
    rec = ur.UsageRecorder(clock=clock)
    rec.record_request(route="/r", path_params={}, status=200, ip="1.1.1.1", user_agent=HUMAN_UA, raw_path="/r")
    assert rec.flush() is None
    monkeypatch.setenv(ur.ENV_DIR, str(tmp_path))
    p = rec.flush()
    assert p.name == "usage_2030-01-15.json"
    rec2 = ur.UsageRecorder(clock=clock)  # a restart on the same day
    rec2.record_request(route="/r", path_params={}, status=200, ip="1.1.1.1", user_agent=HUMAN_UA, raw_path="/r")
    rec2.flush()
    doc = json.loads(p.read_text())
    assert len(doc["segments"]) == 2 and doc["totals"]["human_requests"] == 2


def test_main_without_flag_has_no_usage_route(monkeypatch):
    monkeypatch.delenv(ur.ENV_FLAG, raising=False)
    from backend.main import app
    assert "/api/usage/summary" not in app.openapi()["paths"]  # flag off in the suite
