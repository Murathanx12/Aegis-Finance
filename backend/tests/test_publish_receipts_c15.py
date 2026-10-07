"""C15 (2026-10-07): the public pages' receipts are published into a TRACKED folder, and the
deny-by-default sanitiser runs on EVERY published file (C19 review F12: a tracked folder in a
public repo is a second publication channel that bypasses the routers).

Fixtures are the C19 poisoned receipts (fake account number, dollar equity, a user-home path,
PIDs, ports, credential env-var names, a broker host, owner-personal books) plus a poisoned
Opportunity Explorer receipt. Every published byte is grepped; the routers then serve the
published copy from a checkout with NO live receipts (the Railway case). Offline; dates
derive from `now` (protocol item 5).
"""
from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import config as _config
from backend.routers import arena_v1 as RA
from backend.routers import legibility_v1 as RL
from backend.routers import opportunities as RO
from backend.services import legibility as L
from backend.services import legibility_sanitise as S
from backend.services import opportunities as OPP
from backend.services import publish_receipts as PR
from backend.tests.test_legibility_routers import (HOME, NOW, _dna, _health, _roi, _theory, _w,
                                                   assert_clean)


def _opps(base: Path) -> Path:
    run = NOW.strftime("%Y%m%dT%H%M%SZ")
    row = {"ticker": "VKTX", "company_name": "Viking", "list_id": "roi_v3", "rank": 1, "lane": "CORE",
           "price": {"value": 29.28, "date": NOW.date().isoformat(), "source": f"bars via {HOME}"},
           "analyst": {"median": 95.0, "n": 19, "equity": 123456.78},
           "why_picked": [{"reason": "shortlist source: Murat", "service": "s"}],
           "news": [{"title": f"note PA9SECRET0001 at {HOME}", "url": "https://paper-api.alpaca.markets/v2/x",
                     "published_utc": NOW.isoformat(), "source": "dow jones reader"}] * 6,
           "insiders": {"n_buys": 1, "recent": [{"owner": "A", "side": "BUY", "url": "https://sec.gov/x"}] * 5},
           "analyst_reputation": {"label": "REPUTATION_WEIGHT: NOT_PERSISTENT_OOS", "sum_of_weights": 3.0},
           "links": {"yahoo": "https://finance.yahoo.com/quote/VKTX"},
           "missing_because": {"insiders": "pid 4242 read 127.0.0.1:18789"}}
    blob = {"schema": OPP.SCHEMA, "generated_utc": NOW.isoformat(), "asof": NOW.date().isoformat(),
            "run_id": run, "builder": "scripts/opportunities_build.py", "licence": "PRODUCT_EXPERIMENT",
            "legend": {"move_score": "magnitude"}, "inputs": {"books": f"{HOME}"},
            "lists": [{"list_id": "roi_v3", "title": "ROI", "coverage": {"price": 1}, "rows": [row] * 3},
                      {"list_id": "murat_core_satellite_2026-09-27", "title": "owner", "rows": [row]}]}
    return _w(base / "opportunities" / f"opportunities_{NOW.date().isoformat()}_{run}.json", blob)


@pytest.fixture
def world(tmp_path, monkeypatch):
    live = tmp_path / "live" / "optimus"
    live.mkdir(parents=True)
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_DIR", live)
    L._CACHE.clear()
    OPP._CACHE.clear()
    PR._CACHE.clear()
    gen = NOW - timedelta(hours=3)
    _roi(live, gen, dna_name=_dna(live, gen))
    _health(live, gen)
    _theory(live)
    _opps(live)
    return tmp_path, live


def _client() -> TestClient:
    app = FastAPI()
    for r in (RA.router, RL.router, RO.router):
        app.include_router(r)
    return TestClient(app, raise_server_exceptions=False)


def test_every_published_file_passed_the_sanitiser_and_the_manifest_hashes_it(world):
    tmp, live = world
    out = PR.publish()
    assert out["written"] and out["status"] == "OK", out
    pub = PR.public_dir()
    assert pub == live.parent / "public_receipts"
    man = json.loads((pub / "MANIFEST.json").read_text(encoding="utf-8"))
    assert set(man["published"]) >= {"arena", "theory_lab_sticky", "theory_lab_basket", "system_health",
                                      "opportunities"}
    assert man["missing"] == ["arena_stories", "forecast_lab"]
    for name in man["published"]:
        e = man["kinds"][name]
        b = (pub / name / "latest.json").read_bytes()
        assert hashlib.sha256(b).hexdigest() == e["sha256"] and len(b) == e["bytes"]
        blob = json.loads(b)
        assert_clean(blob)                                            # the C19 deny patterns
        assert PR.leak_scan(blob) == []
        spec = S.SPEC[PR.KIND_BY_NAME[name].spec]
        assert S.sanitise(blob, spec) == blob, f"{name} is not a fixed point of the sanitiser"
        assert e["sources"] and all(s["sha256"] for s in e["sources"]), name
    raw = (pub / "opportunities" / "latest.json").read_text(encoding="utf-8")
    assert "murat_core" not in raw and "Murat" not in raw and "https://" not in raw and "analyst_reputation" not in raw
    opp = json.loads(raw)
    assert opp["n_lists_dropped_owner_personal"] == 1
    r0 = opp["lists"][0]["rows"][0]
    assert len(r0["news"]) == PR.OPP_CAPS["news"] and len(r0["insiders"]["recent"]) == PR.OPP_RECENT_CAP
    assert "equity" not in r0["analyst"]
    # the manifest itself names only repo-relative paths
    assert PR.leak_scan(man) == []


def test_the_sanitiser_is_not_optional_a_bypassed_scrub_is_refused(world, monkeypatch):
    monkeypatch.setattr(S, "scrub_str", lambda s: s)                  # simulate a sanitiser regression
    out = PR.publish()
    refused = {n for n, e in out["kinds"].items() if e["status"] == "REFUSED"}
    assert {"arena", "system_health", "opportunities"} <= refused
    assert all("leak scan" in out["kinds"][n]["why"] for n in refused)
    assert not (PR.public_dir() / "arena" / "latest.json").exists()


def test_over_budget_refuses_and_writes_nothing(world):
    out = PR.publish(max_bytes=10_000)
    assert out["status"] == "REFUSED" and not out["written"] and "budget" in out["why"]
    assert not PR.public_dir().exists()


def test_routers_serve_the_published_copy_where_no_live_receipt_exists(world, monkeypatch):
    tmp, live = world
    PR.publish(out_dir=tmp / "rail" / "public_receipts")
    rail = tmp / "rail" / "optimus"                                   # a fresh checkout: no receipts
    rail.mkdir(parents=True)
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_DIR", rail)
    L._CACHE.clear()
    OPP._CACHE.clear()
    c = _client()
    for path in ("/api/arena/v1/latest", "/api/legibility/v1/theory-lab?board=sticky",
                 "/api/legibility/v1/theory-lab?board=basket", "/api/legibility/v1/system-health"):
        r = c.get(path)
        assert r.status_code == 200, (path, r.text[:200])
        body = r.json()
        assert body["served_from"].startswith("public_receipts/"), path
        assert body["published_utc"]
        assert_clean(body)
        ages = [x["age_hours"] for x in body["receipts"] if x.get("age_hours") is not None]
        assert ages and all(x["status"] in ("FRESH", "STALE", "UNKNOWN", "MISSING") for x in body["receipts"])
    assert c.get("/api/legibility/v1/forecast-lab").status_code == 404   # nothing published, nothing invented
    r = c.get("/api/opportunities/latest")
    assert r.status_code == 200 and "public_receipts" in r.json()["served_from"]
    row = r.json()["list"]["rows"][0]
    assert row["links"]["yahoo"].endswith("/quote/VKTX")             # rebuilt from the ticker at serve time


def test_live_receipts_win_when_they_are_complete(world):
    tmp, live = world
    PR.publish()
    r = _client().get("/api/arena/v1/latest")
    assert r.status_code == 200 and r.json().get("served_from") is None


def test_published_copy_ages_into_stale_from_its_own_stamp(world, monkeypatch):
    tmp, live = world
    PR.publish(out_dir=tmp / "rail" / "public_receipts")
    rail = tmp / "rail" / "optimus"
    rail.mkdir(parents=True)
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_DIR", rail)
    later = NOW + timedelta(days=5)
    out = PR.refresh(PR.load_published("system_health"), "system_health", now=later)
    assert out["status"] == "STALE" and out["receipts"][0]["status"] == "STALE"


def test_publish_has_a_caller_in_the_daily_catalog_job():
    from scripts import task_keeper as K
    import inspect
    src = inspect.getsource(K.main)
    assert "run_publish_receipts" in src and "run_opportunities" in src


# ───────────────────── the caller: the AegisDataCatalog firing (C15 item 6) ─────────────

class _R:
    def __init__(self, rc: int, out: str = "", err: str = ""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def test_run_opportunities_refuses_a_silent_exit_and_logs_one_row(tmp_path):
    from scripts import task_keeper as K
    lp = tmp_path / "opp.jsonl"
    ok = K.run_opportunities(runner=lambda *a, **k: _R(0, "roi_v3 n=65\nwrote backend/x.json (2.0 MB)"), log_path=lp)
    assert ok["action"] == "ok" and ok["line"].startswith("wrote ")
    silent = K.run_opportunities(runner=lambda *a, **k: _R(0, "roi_v3 n=65"), log_path=lp)
    assert silent["action"] == "refused" and "nothing written" in silent["why"]
    bad = K.run_opportunities(runner=lambda *a, **k: _R(1, "", "Traceback\nMemoryError"), log_path=lp)
    assert bad["action"] == "refused" and "MemoryError" in bad["why"]
    assert len(lp.read_text(encoding="utf-8").splitlines()) == 3


def test_run_publish_receipts_maps_status_to_action(tmp_path):
    from scripts import task_keeper as K
    lp = tmp_path / "pub.jsonl"
    for st, act in (("OK", "ok"), ("DEGRADED", "degraded"), ("REFUSED", "refused")):
        assert K.run_publish_receipts(job=lambda st=st: {"status": st, "total_bytes": 1}, log_path=lp)["action"] == act
    def boom():
        raise OSError("disk full")
    assert K.run_publish_receipts(job=boom, log_path=lp)["action"] == "refused"


def test_catalog_health_row_is_degraded_by_a_refused_step_of_the_same_firing(tmp_path):
    from datetime import datetime, timezone
    from backend.services import task_receipts as TR
    now = datetime.now(timezone.utc)
    od = tmp_path / "optimus"
    _w(od / "data_catalog" / f"catalog_{now:%Y%m%dT%H%M%SZ}.json",
       {"status": "OK", "utc": now.isoformat(), "summary": {"n": 3}})
    _w(od / "task_keeper" / "opportunities.jsonl", [{"utc": now.isoformat(), "job": "opportunities",
                                                     "action": "refused", "why": "exited 1: MemoryError"}])
    _w(od / "task_keeper" / "publish_receipts.jsonl", [{"utc": now.isoformat(), "action": "ok"}])

    class Ctx:
        optimus_dir = od
    rd = TR.r_catalog(Ctx(), None)
    assert rd.status == "DEGRADED" and "opportunities_build refused" in rd.reason
    assert "publish_receipts: ok" in rd.detail
