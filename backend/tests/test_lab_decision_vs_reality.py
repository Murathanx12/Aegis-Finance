"""DECISION VS REALITY (chunk 14, loop 3) — synthetic ledgers, no real files.

Four behaviours are pinned, and the first is the one that would be silently
wrong if it were re-implemented instead of imported:

* **the hindsight gate is `ledger_retrieval.visible_at`, actually called.** A
  spy asserts the real predicate ran, so a future edit that inlines a
  similar-looking four-clause check fails this test rather than drifting from
  M3 in a direction nobody notices for a month.
* **the worst miss carries its thesis AND its counter-thesis**, verbatim. A
  gallery of misses without the counter-thesis is a gallery of survivors with
  the sign flipped.
* **every declared mechanism has a row at n_resolved 0.** A group that vanishes
  is a group nobody notices is missing.
* **a mechanism writing records nobody declared is reported, not absorbed.**

Dates are derived from `datetime.now(timezone.utc)` inside each test.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from backend.services import lab_decision_vs_reality as DVR


def _record(*, pid: str, mech: str, p: float, outcome: int,
            resolved: datetime, made: datetime, observable: str = "ret_5d_gt_0",
            thesis: str = "", counter: str = "", regime: str | None = None) -> dict:
    return {
        "prediction_id": pid, "mechanism_id": mech, "ticker": "TEST",
        "observable": observable, "probability": p, "outcome": outcome,
        "made_at": made.isoformat(timespec="seconds"),
        "resolves_after": (made + timedelta(days=1)).isoformat(timespec="seconds"),
        "resolution_date": (resolved - timedelta(days=1)).date().isoformat(),
        "resolved_at": resolved.isoformat(timespec="seconds"),
        "thesis": thesis, "counter_thesis": counter,
        "resolution_detail": ({"regime": regime} if regime else {}),
    }


def test_it_admits_only_hindsight_safe_rows_through_the_imported_predicate():
    """Resolved BEFORE the cut-off is admitted; graded AFTER it is not.

    The spy is the point: it asserts `ledger_retrieval.visible_at` was the
    function that made the decision, not a lookalike written here.
    """
    now = datetime.now(timezone.utc)
    early = _record(pid="in", mech="paper_book_v1", p=0.7, outcome=1,
                    resolved=now - timedelta(hours=2), made=now - timedelta(days=9))
    late = _record(pid="out", mech="paper_book_v1", p=0.7, outcome=1,
                   resolved=now + timedelta(days=3), made=now - timedelta(days=9))

    from backend.services import ledger_retrieval
    calls: list[str] = []

    def spy(record, t):
        calls.append(record.get("prediction_id"))
        return ledger_retrieval.visible_at(record, t)

    payload = DVR.report(as_of=now, rows=[early, late], visible=spy)
    assert calls == ["in", "out"], "the real predicate was not consulted per record"
    assert payload["n_resolved"] == 1
    assert payload["dropped"]["not_visible_at_as_of"] == 1
    book = [r for r in payload["by_mechanism"]
            if r["mechanism_id"] == "paper_book_v1"][0]
    assert book["n_resolved"] == 1


def test_a_record_resolved_outside_the_window_is_dropped_with_a_reason():
    now = datetime.now(timezone.utc)
    old = _record(pid="old", mech="paper_book_v1", p=0.6, outcome=1,
                  resolved=now - timedelta(days=4), made=now - timedelta(days=20))
    payload = DVR.report(as_of=now, rows=[old])
    assert payload["n_resolved"] == 0
    assert payload["dropped"]["outside_window"] == 1


def test_worst_miss_ties_to_thesis_and_counter_thesis():
    now = datetime.now(timezone.utc)
    rows = [
        _record(pid="mild", mech="paper_book_v1", p=0.55, outcome=1,
                resolved=now - timedelta(hours=1), made=now - timedelta(days=9)),
        _record(pid="howler", mech="paper_book_v1", p=0.93, outcome=0,
                resolved=now - timedelta(hours=1), made=now - timedelta(days=9),
                thesis="the guide raise is already in the tape",
                counter="the raise was pre-announced and the move is spent"),
    ]
    payload = DVR.report(as_of=now, rows=rows)
    miss = payload["worst_miss"]
    assert miss["record_id"] == "howler"
    assert miss["thesis"] == "the guide raise is already in the tape"
    assert miss["counter_thesis"] == "the raise was pre-announced and the move is spent"
    assert miss["predicted"] == 0.93 and miss["outcome"] == 0
    assert round(miss["brier"], 4) == round(0.93 ** 2, 4)


def test_every_declared_mechanism_gets_a_row_even_with_nothing_resolved():
    now = datetime.now(timezone.utc)
    payload = DVR.report(as_of=now, rows=[])
    got = {r["mechanism_id"] for r in payload["by_mechanism"]}
    assert got == {m for m, _s, _w in DVR.DECLARED_MECHANISMS}
    for r in payload["by_mechanism"]:
        assert r["n_resolved"] == 0
        assert "status" in r and r["brier"] is None
    x3 = [r for r in payload["by_mechanism"]
          if r["mechanism_id"] == "x3_scenario_forecast_v1"][0]
    assert x3["status"] == "not_wired_yet", (
        "X3's contract exists and is not wired; a row that said `ok` at n=0 "
        "would read as a mechanism that ran and found nothing")


def test_an_undeclared_mechanism_is_reported_not_absorbed():
    now = datetime.now(timezone.utc)
    rows = [_record(pid="x", mech="some_new_thing_v1", p=0.5, outcome=1,
                    resolved=now - timedelta(hours=1), made=now - timedelta(days=9))]
    payload = DVR.report(as_of=now, rows=rows)
    assert payload["undeclared_mechanisms"] == ["some_new_thing_v1"]
    row = [r for r in payload["by_mechanism"]
           if r["mechanism_id"] == "some_new_thing_v1"][0]
    assert row["declared_status"] == "UNDECLARED"


def test_a_small_sample_prints_the_brier_and_draws_no_verdict():
    now = datetime.now(timezone.utc)
    rows = [_record(pid=f"r{i}", mech="paper_book_v1", p=0.8, outcome=1,
                    resolved=now - timedelta(hours=1), made=now - timedelta(days=9))
            for i in range(3)]
    payload = DVR.report(as_of=now, rows=rows)
    row = [r for r in payload["by_mechanism"]
           if r["mechanism_id"] == "paper_book_v1"][0]
    assert row["n_resolved"] == 3
    assert row["brier"] is not None
    assert row["status"] == "insufficient_n"
    assert str(DVR.MIN_N_FOR_A_VERDICT) in row["insufficient_n_note"]


def test_it_groups_by_event_type_and_by_regime():
    now = datetime.now(timezone.utc)
    rows = [
        _record(pid="a", mech="paper_book_v1", p=0.6, outcome=1,
                resolved=now - timedelta(hours=1), made=now - timedelta(days=9),
                observable="earnings_beat", regime="risk_on"),
        _record(pid="b", mech="paper_book_v1", p=0.6, outcome=0,
                resolved=now - timedelta(hours=1), made=now - timedelta(days=9),
                observable="guidance_cut", regime="risk_off"),
    ]
    payload = DVR.report(as_of=now, rows=rows)
    assert set(payload["by_event_type"]) == {"earnings_beat", "guidance_cut"}
    assert set(payload["by_regime"]) == {"risk_on", "risk_off"}
    assert payload["by_event_type"]["earnings_beat"]["n_resolved"] == 1


def test_the_receipt_is_written_atomically_into_the_night_folder(tmp_path):
    now = datetime.now(timezone.utc)
    payload = DVR.report(as_of=now, rows=[])
    day = now.date().isoformat()
    p = DVR.write_report(payload, day=day, out=tmp_path)
    assert p.name == f"decision_vs_reality_{day}.json"
    assert not p.with_suffix(".json.tmp").exists()
    back = json.loads(p.read_text(encoding="utf-8"))
    assert back["receipt"] == "decision_vs_reality"
    assert back["licence"] == "PRODUCT_EXPERIMENT"
    assert back["llm_spend_usd"] == 0.0


def test_the_base_rate_control_is_computed_and_the_delta_named():
    """`beats_base_rate` is the only verdict this roll-up draws, and it is a
    comparison, never a level."""
    now = datetime.now(timezone.utc)
    rows = [_record(pid=f"r{i}", mech="paper_book_v1", p=0.9, outcome=i % 2,
                    resolved=now - timedelta(hours=1),
                    made=now - timedelta(days=9 + i)) for i in range(12)]
    payload = DVR.report(as_of=now, rows=rows)
    row = [r for r in payload["by_mechanism"]
           if r["mechanism_id"] == "paper_book_v1"][0]
    assert row["base_rate_brier"] is not None
    assert row["brier_vs_base_rate"] is not None
    assert row["beats_base_rate"] is (row["brier_vs_base_rate"] < 0)
