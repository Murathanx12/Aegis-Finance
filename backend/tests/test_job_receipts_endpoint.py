"""A receipt nobody can read is barely better than the log line it replaced.

The 2026-08-15 session added dated receipts to `pi_ledger_resolve` and
`pi_ownership_collect` so a run leaves evidence independent of logs. Checking
the first fired run showed that was only half a fix: the receipts were written
to the persistent volume and **nothing exposed them**. The 16:30 ET resolver run
left the ledger unchanged — the expected result when nothing is due, and
therefore indistinguishable from a job that never fired — and the container had
since restarted, taking the log lines with it.

So the read path is part of the fix, and these pin it.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient


def _client(monkeypatch, tmp_path):
    from backend import config as _config
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_DIR", tmp_path)
    from backend.routers import optimus_ledger
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(optimus_ledger.router)
    return TestClient(app)


def test_a_quiet_run_is_visible_as_a_run(monkeypatch, tmp_path):
    d = tmp_path / "resolver_receipts"
    d.mkdir(parents=True)
    (d / "2026-08-14T203000Z.json").write_text(json.dumps({
        "job": "pi_ledger_resolve", "population": "live_forward",
        "ran_at": "2026-08-14T20:30:00+00:00", "status": "ok",
        "due": 0, "newly_resolved": 0, "nothing_was_due": True}),
        encoding="utf-8")

    body = _client(monkeypatch, tmp_path).get(
        "/api/optimus/job_receipts").json()

    r = body["pi_ledger_resolve"]
    assert r["exists"] is True
    assert r["n_receipts"] == 1
    assert r["receipts"][0]["nothing_was_due"] is True
    assert r["receipts"][0]["ran_at"].startswith("2026-08-14T20:30")


def test_no_receipt_directory_says_no_run_has_written_one(monkeypatch,
                                                          tmp_path):
    body = _client(monkeypatch, tmp_path).get(
        "/api/optimus/job_receipts").json()

    r = body["pi_ledger_resolve"]
    # An absent directory and an empty one are different facts, and the one
    # that matters here is "no run has ever written a receipt".
    assert r["exists"] is False
    assert r["n_receipts"] == 0
    assert "no run has written one yet" in r["note"]


def test_receipts_are_newest_first_and_bounded(monkeypatch, tmp_path):
    d = tmp_path / "resolver_receipts"
    d.mkdir(parents=True)
    for day in range(1, 8):
        (d / f"2026-08-0{day}T203000Z.json").write_text(
            json.dumps({"job": "pi_ledger_resolve", "day": day}),
            encoding="utf-8")

    body = _client(monkeypatch, tmp_path).get(
        "/api/optimus/job_receipts?limit=3").json()

    r = body["pi_ledger_resolve"]
    assert r["n_receipts"] == 7          # the true total, not the page size
    assert [x["day"] for x in r["receipts"]] == [7, 6, 5]


def test_a_refusal_is_readable(monkeypatch, tmp_path):
    d = tmp_path / "resolver_receipts"
    d.mkdir(parents=True)
    (d / "2026-08-16T203000Z.json").write_text(json.dumps({
        "job": "pi_ledger_resolve", "status": "REFUSED",
        "reason": "live_forward population UNESTABLISHED"}), encoding="utf-8")

    body = _client(monkeypatch, tmp_path).get(
        "/api/optimus/job_receipts").json()

    got = body["pi_ledger_resolve"]["receipts"][0]
    assert got["status"] == "REFUSED"
    assert "UNESTABLISHED" in got["reason"]


def test_an_unreadable_receipt_is_reported_not_swallowed(monkeypatch,
                                                         tmp_path):
    d = tmp_path / "resolver_receipts"
    d.mkdir(parents=True)
    (d / "2026-08-14T203000Z.json").write_text("{ truncated", encoding="utf-8")

    body = _client(monkeypatch, tmp_path).get(
        "/api/optimus/job_receipts").json()

    got = body["pi_ledger_resolve"]["receipts"][0]
    # Skipping it would shrink the count silently, which is how a corrupt
    # receipt becomes a run that looks like it never happened.
    assert got["unreadable"] is True
    assert body["pi_ledger_resolve"]["n_receipts"] == 1


def test_both_jobs_are_reported_side_by_side(monkeypatch, tmp_path):
    body = _client(monkeypatch, tmp_path).get(
        "/api/optimus/job_receipts").json()
    assert set(body) >= {"pi_ledger_resolve", "pi_ownership_collect"}
