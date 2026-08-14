"""Order 1 (D1/D2): torn ledger lines get an address, and receipts are UTF-8.

Two failure shapes are pinned here, and both are shapes this repo has already
suffered rather than hypotheticals:

  D2  Concurrent appends tore two rows in `llm_calls.jsonl` on 2026-08-12.
      `read_calls` already counted them and downgraded every total to a lower
      bound — into a log line. Nothing that gets READ said so, so the ledger
      reported healthy for two days while missing spend.

  D1  Night 1's receipt says `spend_usd: 0.0` against a measured $0.066464.
      The correction must be APPENDED. A receipt that can be edited into
      correctness cannot be used to prove what was believed at the time.
"""

from __future__ import annotations

import json

import pytest

from backend.services import investigator_night as N
from backend.services import llm_telemetry as T


def _write(path, rows):
    path.write_text("".join(
        (r if isinstance(r, str) else json.dumps(r)) + "\n" for r in rows),
        encoding="utf-8")


def _call_row(cid):
    return {"call_id": cid, "ts": "2026-08-14T10:00:00+00:00",
            "provider": "deepseek", "model": "deepseek-v4-flash",
            "purpose": "T", "cost_usd": 0.001, "row_type": "call",
            "schema_version": "1.0.0"}


# ── D2: the count becomes an address ────────────────────────────────────────

def test_scan_finds_torn_lines_with_their_line_numbers(tmp_path):
    p = tmp_path / "llm_calls.jsonl"
    # The exact two fragments the real ledger carries: an orphan TAIL whose head
    # was lost to an interleaved write.
    _write(p, [_call_row("a"), '"1.0.0"}', _call_row("b"), '"}'])

    scan = T.scan_integrity(p)

    assert scan["n_unreadable"] == 2
    assert [b["line_no"] for b in scan["unreadable"]] == [2, 4]
    assert scan["n_lines"] == 4


def test_clean_ledger_reports_zero_rather_than_staying_silent(tmp_path):
    p = tmp_path / "llm_calls.jsonl"
    _write(p, [_call_row("a"), _call_row("b")])

    assert T.scan_integrity(p)["n_unreadable"] == 0


def test_health_is_degraded_and_says_totals_are_lower_bounds(tmp_path):
    p = tmp_path / "llm_calls.jsonl"
    _write(p, [_call_row("a"), '"1.0.0"}'])

    h = T.ledger_health(p, today=__import__("datetime").date(2026, 8, 14))

    # Loud above zero. A ledger that has lost rows is not "ok" — that is the
    # whole defect: the damage existed and the health surface said fine.
    assert h["status"] == "DEGRADED"
    assert h["n_unreadable_lines"] == 1
    assert h["totals_are_lower_bounds"] is True
    assert any("LOWER BOUND" in s for s in h["problems"])
    assert 2 in h["unreadable_line_numbers"]


def test_quarantine_copies_and_never_removes(tmp_path):
    p = tmp_path / "llm_calls.jsonl"
    _write(p, [_call_row("a"), '"1.0.0"}'])
    before = p.read_bytes()

    res = T.quarantine_unreadable(p)

    # The source ledger is append-only and must be BYTE-identical afterwards:
    # rewriting it to drop the bad line would destroy the only evidence that
    # anything was lost, and manufacture a clean parse.
    assert p.read_bytes() == before
    assert res["n_written"] == 1
    q = json.loads((tmp_path / "llm_calls.jsonl.quarantine.jsonl")
                   .read_text(encoding="utf-8").strip())
    assert q["line_no"] == 2
    assert q["raw"] == '"1.0.0"}'
    assert q["detected_at"]


def test_quarantine_is_idempotent(tmp_path):
    p = tmp_path / "llm_calls.jsonl"
    _write(p, [_call_row("a"), '"1.0.0"}'])

    T.quarantine_unreadable(p)
    second = T.quarantine_unreadable(p)

    # A health check may call this on a schedule; it must not grow a sidecar
    # by one duplicate row per invocation forever.
    assert second["n_written"] == 0
    lines = (tmp_path / "llm_calls.jsonl.quarantine.jsonl").read_text(
        encoding="utf-8").strip().splitlines()
    assert len(lines) == 1


def test_scan_does_not_reach_into_the_real_ledger_from_a_test():
    # `_resolve_path(None)` returns None under pytest. An integrity check that
    # ignored that would report on the developer's own 43,000-row ledger from
    # inside a unit test, and its result would depend on the machine.
    assert T.scan_integrity()["exists"] is False


# ── D1: the correction is appended, not applied ─────────────────────────────

def test_amendment_appends_and_leaves_the_original_claim_visible(tmp_path,
                                                                 monkeypatch):
    monkeypatch.setattr(N, "RECEIPTS_DIR", tmp_path)
    (tmp_path / "2026-08-14.json").write_text(
        json.dumps({"night": "2026-08-14", "status": "void", "spend_usd": 0.0}),
        encoding="utf-8")

    N.amend_receipt("2026-08-14", {"kind": "cost_correction",
                                   "as_written": 0.0, "measured": 0.066464})
    out = N.read_receipt("2026-08-14")

    assert out["spend_usd"] == 0.0          # untouched, deliberately
    assert len(out["amendments"]) == 1
    assert out["amendments"][0]["measured"] == 0.066464
    assert out["amendments"][0]["amended_at"]
    assert out["amendments"][0]["seq"] == 1


def test_amendments_accumulate_in_order(tmp_path, monkeypatch):
    monkeypatch.setattr(N, "RECEIPTS_DIR", tmp_path)
    (tmp_path / "n.json").write_text(json.dumps({"night": "n"}),
                                     encoding="utf-8")

    N.amend_receipt("n", {"kind": "first"})
    N.amend_receipt("n", {"kind": "second"})

    seqs = [a["seq"] for a in N.read_receipt("n")["amendments"]]
    assert seqs == [1, 2]
    assert [a["kind"] for a in N.read_receipt("n")["amendments"]] == ["first",
                                                                     "second"]


# ── the encoding pin, on BOTH sides ─────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "information guard: 5 consecutive cells produced no gradeable forecast — "
    "stopping rather than paying",          # em dash: the exact Night 1 string
    "café — naïve — ±0.05 — 日本",
])
def test_receipt_round_trips_non_ascii_byte_for_byte(tmp_path, monkeypatch,
                                                     text):
    monkeypatch.setattr(N, "RECEIPTS_DIR", tmp_path)
    (tmp_path / "n.json").write_text(
        json.dumps({"night": "n", "void_reason": text}, ensure_ascii=False),
        encoding="utf-8")

    N.amend_receipt("n", {"kind": "noop"})

    # The mojibake was a READ-side cp1252 default, not a corrupt file, so a
    # write-only pin would have left the bug exactly where it was. Both ends
    # are asserted, through a rewrite.
    assert N.read_receipt("n")["void_reason"] == text
    raw = (tmp_path / "n.json").read_bytes()
    assert "—".encode("utf-8") in raw or "\\u2014" in raw.decode("utf-8")


def test_receipt_reader_refuses_the_platform_default(tmp_path, monkeypatch):
    monkeypatch.setattr(N, "RECEIPTS_DIR", tmp_path)
    body = {"night": "n", "void_reason": "stopped — barren"}
    (tmp_path / "n.json").write_text(json.dumps(body, ensure_ascii=False),
                                     encoding="utf-8")

    # Decoding the same bytes as cp1252 is what produced the mojibake in the
    # first place; this asserts the two readings genuinely differ, so the test
    # above is testing something rather than passing on an ASCII payload.
    mojibake = (tmp_path / "n.json").read_bytes().decode("cp1252")
    assert json.loads(mojibake)["void_reason"] != body["void_reason"]
    assert N.read_receipt("n")["void_reason"] == body["void_reason"]


# ── `since` means since, not "that morning" ─────────────────────────────────

def test_a_timestamp_cutoff_is_honoured_to_the_second(tmp_path):
    p = tmp_path / "llm_calls.jsonl"
    early = dict(_call_row("early"), ts="2026-08-15T09:00:00+00:00")
    late = dict(_call_row("late"), ts="2026-08-15T21:00:00+00:00")
    _write(p, [early, late])

    # `_as_date` truncated this cutoff to 2026-08-15 and swept in BOTH rows, so
    # a night starting at 20:30 was charged for everything since midnight. A
    # rehearsal that made no vendor call reported spending $0.115184 — which is
    # how this was found — and the same arithmetic feeds the funding rule.
    s = T.spend(since="2026-08-15T20:00:00+00:00", path=p)

    assert s["n_calls"] == 1
    assert s["total_cost_usd"] == pytest.approx(0.001)


def test_a_date_only_cutoff_still_means_the_whole_day(tmp_path):
    p = tmp_path / "llm_calls.jsonl"
    _write(p, [dict(_call_row("early"), ts="2026-08-15T09:00:00+00:00"),
               dict(_call_row("late"), ts="2026-08-15T21:00:00+00:00")])

    # A caller who passed a DAY meant a day. Reading "2026-08-15" as midnight
    # would be the same truncation bug pointing the other way, and it is what
    # `research_budget`'s daily caps depend on.
    assert T.spend(since="2026-08-15", path=p)["n_calls"] == 2
    assert T.spend(since=__import__("datetime").date(2026, 8, 15),
                   path=p)["n_calls"] == 2


def test_the_measurement_can_be_scoped_to_one_trial(tmp_path):
    p = tmp_path / "llm_calls.jsonl"
    _write(p, [dict(_call_row("a"), purpose="INTERNET-INVESTIGATOR-FWD-1"),
               dict(_call_row("b"), purpose="IIF1-DIAGNOSTIC")])

    # The ceiling stays broad on purpose; the FUNDING number does not. A
    # diagnostic run the same evening must not decide whether 40 nights are
    # affordable.
    assert T.spend(path=p)["n_calls"] == 2
    assert T.spend(path=p, purpose="INTERNET-INVESTIGATOR-FWD-1")["n_calls"] == 1
