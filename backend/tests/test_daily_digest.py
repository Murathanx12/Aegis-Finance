"""Daily digest — the corpus of "what happened vs what we thought".

The failure this subsystem must never exhibit is its own subject matter: a
digest that silently records nothing, or crashes and leaves the day blank.
So the tests pin (1) build never raises against any disk state, (2) absent
vs empty sources are DIFFERENT facts, (3) the corpus dedupes a re-run day,
and (4) the job is declared in the scheduler's expected set — the NIGHT-13
canary covers registration drift from there.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.services import daily_digest as dd

DAY = "2026-08-21"

ALLOWED = {"ok", "ok_empty", "unavailable"}


@pytest.fixture()
def roots(tmp_path):
    ledger = tmp_path / "ledger"
    arena = tmp_path / "arena"
    ledger.mkdir()
    arena.mkdir()
    return ledger, arena


# ── build ───────────────────────────────────────────────────────────────────

def test_build_never_raises_on_bare_disk(roots):
    ledger, arena = roots
    digest = dd.build_digest(DAY, ledger_dir=ledger, arena_root=arena)
    assert digest["day"] == DAY
    assert set(digest["sections"]) == set(dd.SECTIONS)
    for name, section in digest["sections"].items():
        assert section.get("status") in ALLOWED, (name, section)


def test_arena_section_records_the_router_trail(roots):
    """The digest carries what RELIABILITY_ROUTER_v1 would recommend today.
    On a bare arena that is an honest ABSTAIN — the trail starts truthful."""
    ledger, arena = roots
    digest = dd.build_digest(DAY, ledger_dir=ledger, arena_root=arena)
    tr = digest["sections"]["arena"].get("trust_router")
    assert tr is not None, digest["sections"]["arena"]
    assert tr["router_version"] == "RELIABILITY_ROUTER_v1"
    assert tr["verdict"] == "ABSTAIN"
    assert tr["weights"] is None  # never weights without a RECOMMENDED verdict


def test_absent_directory_is_unavailable_not_empty(roots):
    """No resolver_receipts dir means the resolver has never left evidence —
    that is a different fact from 'the directory is there and empty'."""
    ledger, arena = roots
    digest = dd.build_digest(DAY, ledger_dir=ledger, arena_root=arena)
    assert digest["sections"]["ledger"]["status"] == "unavailable"

    (ledger / "resolver_receipts").mkdir()
    digest2 = dd.build_digest(DAY, ledger_dir=ledger, arena_root=arena)
    assert digest2["sections"]["ledger"]["status"] == "ok_empty"


def test_resolver_receipt_is_read_and_dated(roots):
    ledger, arena = roots
    d = ledger / "resolver_receipts"
    d.mkdir()
    (d / "2026-08-21T203000Z.json").write_text(json.dumps({
        "ran_at": f"{DAY}T20:30:00+00:00", "status": "ok",
        "due": 3, "newly_resolved": 3, "pending": 0, "overdue": 0,
        "nothing_was_due": False,
    }), encoding="utf-8")
    section = dd.build_digest(DAY, ledger_dir=ledger,
                              arena_root=arena)["sections"]["ledger"]
    assert section["status"] == "ok"
    assert section["ran_today"] is True
    assert section["latest_receipt"]["newly_resolved"] == 3


def test_iif_launch_record_surfaces_outcome(roots):
    ledger, arena = roots
    d = ledger / "iif1_launches"
    d.mkdir()
    (d / f"{DAY}.json").write_text(json.dumps({
        "outcome": "LAUNCHED", "launched_at": f"{DAY}T17:00:41+08:00",
    }), encoding="utf-8")
    section = dd.build_digest(DAY, ledger_dir=ledger,
                              arena_root=arena)["sections"]["iif"]
    assert section["status"] == "ok"
    assert section["outcome"] == "LAUNCHED"


def test_iif_no_record_yet_is_empty_not_unavailable(roots):
    ledger, arena = roots
    (ledger / "iif1_launches").mkdir()
    section = dd.build_digest(DAY, ledger_dir=ledger,
                              arena_root=arena)["sections"]["iif"]
    assert section["status"] == "ok_empty"


def test_collections_reads_latest_receipt(roots):
    ledger, arena = roots
    d = ledger / "teacher_library" / "collection_receipts"
    d.mkdir(parents=True)
    (d / "2026-08-20.json").write_text(json.dumps({
        "written": 412, "source_status": "OK"}), encoding="utf-8")
    section = dd.build_digest(DAY, ledger_dir=ledger,
                              arena_root=arena)["sections"]["collections"]
    assert section["status"] == "ok"
    assert section["written"] == 412
    assert section["latest_day"] == "2026-08-20"


# ── persistence ─────────────────────────────────────────────────────────────

def test_write_creates_json_md_and_one_corpus_line(roots):
    ledger, arena = roots
    digest = dd.build_digest(DAY, ledger_dir=ledger, arena_root=arena)
    paths = dd.write_digest(digest, ledger_dir=ledger)
    assert paths["corpus_appended"] is True
    d = dd.digests_dir(ledger)
    assert (d / f"{DAY}.json").exists()
    assert (d / f"{DAY}.md").exists()
    lines = dd.corpus_path(ledger).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["day"] == DAY


def test_rerunning_a_day_refreshes_files_but_never_double_counts(roots):
    """The corpus is the training substrate — a manual re-run of a day must
    not become two rows of evidence for one day."""
    ledger, arena = roots
    for _ in range(2):
        res = dd.run_daily_digest(DAY, ledger_dir=ledger, arena_root=arena)
    assert res["corpus_appended"] is False
    lines = dd.corpus_path(ledger).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_a_new_day_appends(roots):
    ledger, arena = roots
    dd.run_daily_digest("2026-08-21", ledger_dir=ledger, arena_root=arena)
    dd.run_daily_digest("2026-08-22", ledger_dir=ledger, arena_root=arena)
    lines = dd.corpus_path(ledger).read_text(encoding="utf-8").splitlines()
    assert [json.loads(l)["day"] for l in lines] == ["2026-08-21",
                                                     "2026-08-22"]


def test_corrupt_corpus_line_does_not_kill_the_job(roots):
    ledger, arena = roots
    dd.digests_dir(ledger).mkdir(parents=True)
    dd.corpus_path(ledger).write_text("{not json\n", encoding="utf-8")
    res = dd.run_daily_digest(DAY, ledger_dir=ledger, arena_root=arena)
    assert res["status"] == "ok"
    assert res["corpus_appended"] is True


def test_run_summary_carries_the_counts(roots):
    ledger, arena = roots
    res = dd.run_daily_digest(DAY, ledger_dir=ledger, arena_root=arena)
    assert res["day"] == DAY
    assert isinstance(res["n_ok"], int)
    assert isinstance(res["unavailable"], list)


# ── wiring ──────────────────────────────────────────────────────────────────

def test_job_is_declared_in_the_scheduler_expected_set():
    from backend.services.portfolio_intelligence import scheduler as sched
    assert "pi_daily_digest" in sched.EXPECTED_JOB_IDS


def test_endpoint_404_before_any_digest_then_serves_it(roots, monkeypatch):
    ledger, arena = roots
    from backend import config as _config
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_DIR", ledger)

    from backend.main import app
    client = TestClient(app)
    assert client.get("/api/optimus/digest").status_code == 404

    dd.run_daily_digest(DAY, ledger_dir=ledger, arena_root=arena)
    body = client.get("/api/optimus/digest").json()
    assert body["day"] == DAY
    assert body["population"] == "documentation"
    assert client.get(f"/api/optimus/digest?day={DAY}").json()["day"] == DAY
    assert client.get("/api/optimus/digest?day=1999-01-01").status_code == 404
