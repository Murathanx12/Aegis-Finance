"""The verifier must work on the receipt it will actually meet.

WHY THIS EXISTS
===============
`scripts/verify_ownership_collector.py` had been exercised against exactly one
state: no receipt at all. That is the state it is in right now and the least
interesting one. The first production run of `pi_ownership_collect` happens
once; if the verifier mis-reads that receipt, the failure lands at the only
moment it matters and the day cannot be replayed.

So the paths tested here are the ones the verifier will meet at 10:00 UTC:

  * a healthy run — every one of the twelve required fields present;
  * the T9 SHAPE — documents attempted, ZERO fetched. This project shipped a
    collector that passed twelve offline tests while 403-ing on 100% of its
    production requests, and a receipt reporting only "attempted" cannot
    express it at all;
  * a quiet run that wrote nothing, which is either a genuinely empty day or a
    dead fetch path and looks identical on every dashboard;
  * BUYS ONLY, the shape the pre-2026-08 parser produced, which would have made
    the Teacher Library a collection of successful-looking stories;
  * a receipt that is present but unreadable.

Exit codes matter: 0 healthy, 1 something is wrong, 2 no run yet. `2` is not a
failure — it is the absence of evidence, and the two must not collapse.
"""

from __future__ import annotations

import json

import pytest

from scripts import verify_ownership_collector as V


def _receipt(**over):
    r = {
        "job": "pi_ownership_collect", "day": "2026-08-14",
        "ran_at": "2026-08-15T10:00:12+00:00", "source_status": "OK_DATA",
        "reason": "", "n_index_rows": 1098, "n_unique_accessions": 512,
        "n_attempted": 512, "n_documents_fetched": 510, "coverage": 1.0,
        "n_parse_errors": 4, "failure_classes": {"document_not_retrievable": 4},
        "events_by_action": {"SELL": 516, "BUY": 92, "OTHER": 975},
        "n_buys": 92, "n_sells": 516, "n_mechanical": 975,
        "n_distinct_actors": 482, "n_distinct_tickers": 294,
        "fetch_seconds": 631.2, "total_seconds": 640.8,
        "written": 1583, "duplicates": 0, "usable_events": 1583,
    }
    r.update(over)
    return r


def _wire(monkeypatch, receipts, health_ok=True):
    def fake_fetch(base, path, timeout=60):
        if "health" in path:
            if not health_ok:
                raise RuntimeError("edge down")
            return {"status": "ok", "deploy": {"commit": "abc12345" * 5}}
        return {"pi_ownership_collect": {
            "dir": "/data/optimus/teacher_library/collection_receipts",
            "exists": bool(receipts), "n_receipts": len(receipts),
            "receipts": receipts,
            "note": "no receipt directory — no run has written one yet"}}
    monkeypatch.setattr(V, "fetch", fake_fetch)


def test_no_run_yet_is_reported_as_absence_of_evidence(monkeypatch, capsys):
    _wire(monkeypatch, [])
    rc = V.main([])
    out = capsys.readouterr().out
    assert rc == 2                       # not 1 — this is not a failure
    assert "NO PRODUCTION RUN HAS WRITTEN A RECEIPT YET" in out
    assert "absence of evidence" in out


def test_a_healthy_run_reports_every_one_of_the_twelve(monkeypatch, capsys):
    _wire(monkeypatch, [_receipt()])
    rc = V.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "MISSING FROM RECEIPT" not in out
    for probe in ("index rows", "unique accessions", "documents fetched",
                  "coverage", "parse errors", "BUY", "SELL",
                  "mechanical / other", "distinct actors", "distinct tickers",
                  "fetch seconds", "events written", "duplicates skipped"):
        assert probe in out, probe
    assert "reached EDGAR from production" in out


def test_the_T9_SHAPE_is_named_when_nothing_was_fetched(monkeypatch, capsys):
    """Attempted 512, fetched 0. The exact failure that once passed 12 tests."""
    _wire(monkeypatch, [_receipt(n_documents_fetched=0, written=0,
                                 n_parse_errors=512,
                                 failure_classes={"document_not_retrievable":
                                                  512})])
    rc = V.main([])
    out = capsys.readouterr().out
    assert rc == 1
    assert "T9 SHAPE" in out
    assert "ZERO were fetched" in out
    assert "Railway egress" in out


def test_a_missing_field_is_flagged_rather_than_printed_as_None(monkeypatch,
                                                                capsys):
    r = _receipt()
    del r["n_distinct_actors"]
    _wire(monkeypatch, [r])
    V.main([])
    out = capsys.readouterr().out
    assert "MISSING FROM RECEIPT" in out


def test_a_run_that_wrote_nothing_is_not_called_quiet(monkeypatch, capsys):
    _wire(monkeypatch, [_receipt(written=0, n_buys=0, n_sells=0,
                                 n_mechanical=0)])
    rc = V.main([])
    out = capsys.readouterr().out
    assert rc == 1
    assert "wrote NOTHING" in out
    # Assert on the VERDICT text, not on the token `failure_classes` — that
    # token is printed in the field table above regardless of the verdict, so
    # matching it would pass for a reason unrelated to the behaviour.
    verdict = out.split("── verdict ──", 1)[1]
    assert "genuinely quiet day" in verdict
    assert "dead" in verdict and "fetch path" in verdict


def test_buys_only_is_flagged_because_that_was_the_old_parsers_shape(
        monkeypatch, capsys):
    _wire(monkeypatch, [_receipt(n_sells=0, n_mechanical=0, written=92,
                                 events_by_action={"BUY": 92})])
    rc = V.main([])
    out = capsys.readouterr().out
    assert rc == 1
    assert "BUYS ONLY" in out
    assert "successful-looking buy stories" in out


def test_index_not_yet_published_is_not_treated_as_a_failure(monkeypatch,
                                                             capsys):
    _wire(monkeypatch, [_receipt(source_status="NOT_YET_PUBLISHED",
                                 n_attempted=0, n_documents_fetched=0,
                                 written=0, n_buys=0, n_sells=0,
                                 n_mechanical=0)])
    rc = V.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "not a failure" in out


def test_an_unreadable_receipt_is_reported_not_skipped(monkeypatch, capsys):
    _wire(monkeypatch, [{"file": "2026-08-14.json", "unreadable": True,
                         "error": "JSONDecodeError: truncated"}])
    rc = V.main([])
    out = capsys.readouterr().out
    assert rc == 1
    assert "RECEIPT UNREADABLE" in out


def test_idempotency_is_reported_as_UNMEASURED_on_a_first_run(monkeypatch,
                                                              capsys):
    """It is answerable on the SECOND run, by whether duplicates absorb the
    overlap. Printing a field nobody measured would be worse than saying so."""
    _wire(monkeypatch, [_receipt()])
    V.main([])
    assert "idempotency: UNMEASURED" in capsys.readouterr().out


def test_two_runs_let_idempotency_be_reported(monkeypatch, capsys):
    _wire(monkeypatch, [_receipt(day="2026-08-15"),
                        _receipt(day="2026-08-14", written=0,
                                 duplicates=1583)])
    V.main([])
    out = capsys.readouterr().out
    assert "previous run (2026-08-14) wrote 0 with 1583 duplicates" in out


def test_an_unreachable_health_endpoint_does_not_stop_the_verification(
        monkeypatch, capsys):
    """The receipt is the evidence; health is context. Losing the context must
    not lose the reading."""
    _wire(monkeypatch, [_receipt()], health_ok=False)
    rc = V.main([])
    out = capsys.readouterr().out
    assert "UNREACHABLE" in out
    assert rc == 0
    assert "reached EDGAR from production" in out


def test_the_receipt_json_shape_matches_what_the_collector_actually_writes():
    """Pins the verifier's expectations against the producer's key set.

    A verifier written against imagined keys is the 2026-08-15 daily-index
    lesson repeating: a fixture that agrees with the parser and not with the
    source proves only that they agree.
    """
    from backend.tests.test_ownership_receipt_completeness import REQUIRED
    written = set(_receipt())
    assert set(REQUIRED) <= written, sorted(set(REQUIRED) - written)
    assert json.dumps(_receipt())      # and it must serialise
