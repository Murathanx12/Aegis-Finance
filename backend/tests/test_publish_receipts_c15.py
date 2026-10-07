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
from backend.tests.test_legibility_routers import (HOME, NOW, _beliefs, _dna, _health, _roi, _theory, _w,
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
    _beliefs(live, gen)
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
                                      "opportunities", "brain", "forecast_lab"}
    # forecast_lab now finds a receipt too: the brain fixture's digest/world_state_<stamp>.json is the
    # SAME file forecast_lab's "regime rows" ingredient reads (both pages share it in production).
    assert man["missing"] == ["arena_stories"]
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
                 "/api/legibility/v1/theory-lab?board=basket", "/api/legibility/v1/system-health",
                 "/api/legibility/v1/brain", "/api/legibility/v1/forecast-lab"):
        r = c.get(path)
        assert r.status_code == 200, (path, r.text[:200])
        body = r.json()
        assert body["served_from"].startswith("public_receipts/"), path
        assert body["published_utc"]
        assert_clean(body)
        ages = [x["age_hours"] for x in body["receipts"] if x.get("age_hours") is not None]
        assert ages and all(x["status"] in ("FRESH", "STALE", "UNKNOWN", "MISSING") for x in body["receipts"])
    r = c.get("/api/opportunities/latest")
    assert r.status_code == 200 and "public_receipts" in r.json()["served_from"]
    row = r.json()["list"]["rows"][0]
    assert row["links"]["yahoo"].endswith("/quote/VKTX")             # rebuilt from the ticker at serve time


def _volume_deployment(tmp, monkeypatch):
    """Railway's layout: the data dir is a mounted volume, the image carries the published
    copies at backend/data/public_receipts (committed to git), and the volume holds none."""
    image_data = tmp / "image" / "data"
    volume = tmp / "volume"
    (volume / "optimus").mkdir(parents=True)
    monkeypatch.setattr(_config, "DATA_DIR", volume)
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_DIR", volume / "optimus")
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_LEGACY_DIR", image_data / "optimus")
    L._CACHE.clear()
    OPP._CACHE.clear()
    PR._CACHE.clear()
    return image_data / "public_receipts", volume / "public_receipts"


def test_a_volume_deployment_serves_the_copies_baked_into_the_image(world, monkeypatch):
    """2026-10-07, live: /arena, /forecast-lab, /theory-lab and /health answered "no receipt
    written yet" because serving read only <volume>/public_receipts, while the published copies
    ship in the image. The earlier test above models a checkout whose data dir IS the image's;
    this one models the deployment that actually broke."""
    tmp, live = world
    baked = tmp / "image" / "data" / "public_receipts"
    PR.publish(out_dir=baked)
    baked_dir, volume_dir = _volume_deployment(tmp, monkeypatch)
    assert baked_dir == baked and not volume_dir.exists()
    assert PR.read_dirs() == [volume_dir, baked] and PR.serving_dir() == baked
    c = _client()
    for path in ("/api/arena/v1/latest", "/api/legibility/v1/theory-lab?board=sticky",
                 "/api/legibility/v1/system-health", "/api/legibility/v1/forecast-lab"):
        r = c.get(path)
        assert r.status_code == 200, (path, r.text[:200])
        assert r.json()["served_from"].startswith("public_receipts/"), path
        assert r.json()["published_utc"]
    assert "public_receipts" in c.get("/api/opportunities/latest").json()["served_from"]


def test_the_newer_published_copy_serves_whichever_folder_holds_it(world, monkeypatch):
    tmp, live = world
    baked = tmp / "image" / "data" / "public_receipts"
    volume_copy = tmp / "volume" / "public_receipts"
    PR.publish(out_dir=baked, now=NOW - timedelta(days=1))
    PR.publish(out_dir=volume_copy, now=NOW)
    _volume_deployment(tmp, monkeypatch)
    assert PR.serving_dir() == volume_copy                      # the volume's copy is newer
    man = json.loads((baked / "MANIFEST.json").read_text(encoding="utf-8"))
    man["published_utc"] = (NOW + timedelta(hours=1)).isoformat(timespec="seconds")
    (baked / "MANIFEST.json").write_text(json.dumps(man), encoding="utf-8")   # a redeploy ships a newer one
    assert PR.serving_dir() == baked


def test_without_a_volume_serving_never_reaches_outside_the_data_dir(world, monkeypatch):
    """Locally and in this suite the data dir is the image's: a test that points the ledger
    dir at tmp must never be served the real committed copies."""
    tmp, live = world
    monkeypatch.setattr(_config, "DATA_DIR", Path(_config.BACKEND_DIR) / "data")
    assert PR.read_dirs() == [PR.public_dir()]
    assert PR.serving_dir() == live.parent / "public_receipts"


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
    assert "run_publish_receipts" in src and "run_opportunities" in src and "run_publish_commit" in src
    assert src.index("run_publish_commit()") > src.index("run_publish_receipts()")  # commit is LAST


# ───────────────────── the caller: the AegisDataCatalog firing (C15 item 6) ─────────────

class _R:
    def __init__(self, rc: int, out: str = "", err: str = ""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def test_run_opportunities_refuses_a_silent_exit_and_logs_one_row(tmp_path):
    from scripts import task_keeper as K
    lp = tmp_path / "opp.jsonl"
    mem = {"free_gb": lambda: 8.0}
    ok = K.run_opportunities(runner=lambda *a, **k: _R(0, "roi_v3 n=65\nwrote backend/x.json (2.0 MB)"), log_path=lp,
                             **mem)
    assert ok["action"] == "ok" and ok["line"].startswith("wrote ")
    silent = K.run_opportunities(runner=lambda *a, **k: _R(0, "roi_v3 n=65"), log_path=lp, **mem)
    assert silent["action"] == "refused" and "nothing written" in silent["why"]
    bad = K.run_opportunities(runner=lambda *a, **k: _R(1, "", "Traceback\nMemoryError"), log_path=lp, **mem)
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


def test_run_opportunities_refuses_below_the_memory_floor_and_never_starts(tmp_path):
    """Review C15 M5: the 09:00 firing shares its window with the sim owner."""
    from scripts import task_keeper as K
    started = []
    out = K.run_opportunities(runner=lambda *a, **k: started.append(1), log_path=tmp_path / "o.jsonl",
                              free_gb=lambda: 2.5)
    assert out["action"] == "refused" and "2.5 GB free < 4.0 GB" in out["why"] and not started
    unk = K.run_opportunities(runner=lambda *a, **k: started.append(1), log_path=tmp_path / "o.jsonl",
                              free_gb=lambda: None)
    assert unk["action"] == "refused" and "could not be read" in unk["why"] and not started


# ───────────────────── review C15 M1: precedence by AGE, rows re-aged ─────────────────────

def _pl(*stamps, missing: int = 0) -> dict:
    recs = [{"kind": "k", "status": "FRESH", "stamp_utc": t.isoformat()} for t in stamps]
    recs += [{"kind": "k", "status": "MISSING", "stamp_utc": None}] * missing
    return {"receipts": recs}


def test_the_newer_copy_wins_by_its_own_stamps_and_ties_go_to_completeness():
    old, new = NOW - timedelta(days=3), NOW - timedelta(hours=1)
    assert PR.prefer_published(_pl(old, old), _pl(new, new)) is True       # same count, pub newer
    assert PR.prefer_published(_pl(new, new), _pl(old, old, old)) is False  # live newer wins
    assert PR.prefer_published(_pl(new, missing=1), _pl(new, new)) is True  # tie -> more complete
    assert PR.prefer_published(_pl(new, new), _pl(new, new)) is False       # full tie -> live
    assert PR.prefer_published(None, _pl(old)) is True and PR.prefer_published(_pl(old), None) is False


def test_a_published_arena_rows_are_re_aged_from_serve_time(world):
    tmp, live = world
    PR.publish()
    pub = PR.load_published("arena")
    rows = [r for r in pub["books"] if r.get("mark_status") == "LIVE"]
    assert rows, "fixture has a LIVE row"
    later = NOW + timedelta(days=6)
    out = PR.refresh(pub, "arena", now=later)
    by = {r["account"]: r for r in out["books"]}
    for r in rows:
        got = by[r["account"]]
        assert got["mark_status"] == "STALE" and got["mark_age_days"] >= (r["mark_age_days"] or 0) + 6
    assert out["numbers"]["mark_status_counts"].get("LIVE", 0) == 0


def test_published_health_rows_carry_age_now_from_their_own_evidence(world):
    PR.publish()
    later = NOW + timedelta(days=2)
    out = PR.refresh(PR.load_published("system_health"), "system_health", now=later)
    ages = [r["age_s_now"] for g in out["groups"] for r in g["rows"] if r.get("age_s_now") is not None]
    assert ages and min(ages) > 2 * 86400 - 60


# ───────────────────── review C15 M2: the owner's identity on EVERY kind ──────────────────

def test_owner_identity_is_scrubbed_on_every_kind_and_is_in_the_leak_scan(world, monkeypatch):
    tmp, live = world
    hp = next((live / "health").glob("health_*.json"))
    rec = json.loads(hp.read_text(encoding="utf-8"))
    rec["rows"][0]["detail"] = "MURAT asked; see github.com/murathanx12 and Murathan's notes"
    hp.write_text(json.dumps(rec), encoding="utf-8")
    L._CACHE.clear()
    assert PR.leak_scan({"x": "by Murathanx12"}) == ["$.x: owner identity"]
    assert PR.leak_scan({"x": "murat_book"}) == ["$.x: owner identity"]
    out = PR.publish()
    assert out["kinds"]["system_health"]["status"] == "OK"
    raw = (PR.public_dir() / "system_health" / "latest.json").read_text(encoding="utf-8")
    assert "the owner asked" in raw and not PR.owner_pattern().search(raw)
    monkeypatch.setattr(PR, "_owner_scrub", lambda v: v)                    # a scrub regression
    again = PR.publish()
    assert again["kinds"]["system_health"]["status"] == "REFUSED"
    assert "owner identity" in again["kinds"]["system_health"]["why"]


# ───────────────────── review C15 H1: commit ONLY the folder, on main, then push ────────────

import subprocess  # noqa: E402


def _g(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (args, r.stderr)
    return r.stdout.strip()


@pytest.fixture
def gitrepo(tmp_path):
    """A throwaway repo + bare remote (never the real repository). Local config isolates it
    from the machine's hooks and signing settings."""
    remote = tmp_path / "remote.git"
    _g(tmp_path, "init", "--bare", "-b", "main", str(remote))
    repo = tmp_path / "repo"
    repo.mkdir()
    _g(repo, "init", "-b", "main")
    hooks = tmp_path / "nohooks"
    hooks.mkdir()
    for k, v in (("user.name", "fixture"), ("user.email", "fixture@example.invalid"),
                 ("commit.gpgsign", "false"), ("core.hooksPath", str(hooks)), ("core.autocrlf", "false")):
        _g(repo, "config", k, v)
    (repo / "code.py").write_text("x = 1\n", encoding="utf-8")
    _g(repo, "add", "code.py")
    _g(repo, "commit", "-m", "init")
    _g(repo, "remote", "add", "origin", str(remote))
    _g(repo, "push", "-q", "origin", "main")
    folder = repo / "backend" / "data" / "public_receipts"
    return repo, folder, remote


def _publish_into(folder: Path, payload: str = "1") -> None:
    (folder / "arena").mkdir(parents=True, exist_ok=True)
    b = json.dumps({"x": payload}).encode()
    (folder / "arena" / "latest.json").write_bytes(b)
    (folder / "MANIFEST.json").write_text(json.dumps({
        "status": "OK", "published_utc": NOW.isoformat(),
        "kinds": {"arena": {"status": "OK", "sha256": hashlib.sha256(b).hexdigest()}}}), encoding="utf-8")


def _commit(repo, folder, tmp_path, **kw):
    return PR.commit_public_receipts(repo=repo, folder=folder, log_path=tmp_path / "commit.jsonl", **kw)


def test_commit_refuses_off_main_and_changes_nothing(gitrepo, tmp_path):
    repo, folder, _ = gitrepo
    _publish_into(folder)
    _g(repo, "checkout", "-q", "-b", "wip/x")
    out = _commit(repo, folder, tmp_path)
    assert out["status"] == "REFUSED" and "not 'main'" in out["reasons"][0]
    assert _g(repo, "diff", "--cached", "--name-only") == ""                  # nothing staged
    row = json.loads((tmp_path / "commit.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert row["status"] == "REFUSED" and row["branch"] == "wip/x"


def test_commit_refuses_with_staged_changes_outside_the_folder(gitrepo, tmp_path):
    repo, folder, _ = gitrepo
    _publish_into(folder)
    (repo / "code.py").write_text("x = 2\n", encoding="utf-8")
    _g(repo, "add", "code.py")
    out = _commit(repo, folder, tmp_path)
    assert out["status"] == "REFUSED" and "outside backend/data/public_receipts/" in out["reasons"][0]
    assert _g(repo, "diff", "--cached", "--name-only") == "code.py"           # the owner's stage untouched


def test_commit_refuses_a_manifest_that_does_not_hash(gitrepo, tmp_path):
    repo, folder, _ = gitrepo
    _publish_into(folder)
    (folder / "arena" / "latest.json").write_text('{"x": "tampered"}', encoding="utf-8")
    out = _commit(repo, folder, tmp_path)
    assert out["status"] == "REFUSED" and "does not hash" in " ".join(out["reasons"])


def test_commit_publishes_only_the_folder_then_refuses_an_empty_diff(gitrepo, tmp_path):
    repo, folder, remote = gitrepo
    _publish_into(folder)
    (repo / "code.py").write_text("x = 3\n", encoding="utf-8")              # unstaged code change
    out = _commit(repo, folder, tmp_path)
    assert out["status"] == "COMMITTED" and out["pushed"] is True, out
    assert out["message"] == f"public receipts {NOW.isoformat()} (data-only, sanitised; no code)"
    files = _g(repo, "show", "--name-only", "--format=", "HEAD").splitlines()
    assert files and all(f.startswith("backend/data/public_receipts/") for f in files)
    assert _g(remote, "log", "-1", "--format=%s", "main") == out["message"]
    assert "code.py" in _g(repo, "status", "--porcelain")                    # never committed
    again = _commit(repo, folder, tmp_path)
    assert again["status"] == "REFUSED" and "staged diff" in again["reasons"][0]


def test_commit_never_pushes_unpushed_code_on_main(gitrepo, tmp_path):
    repo, folder, remote = gitrepo
    (repo / "code.py").write_text("x = 4\n", encoding="utf-8")
    _g(repo, "commit", "-qam", "somebody's local code commit")
    _publish_into(folder)
    out = _commit(repo, folder, tmp_path)
    assert out["status"] == "COMMITTED" and out["pushed"] is False and "never pushes code" in out["push_refused"]
    assert _g(remote, "log", "-1", "--format=%s", "main") == "init"
