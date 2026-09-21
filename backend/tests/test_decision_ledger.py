"""The decision ledger, pinned (chunk 18).

The property nothing in either repo had: **did anyone SEE this before the
window closed?** A decision that was written and never read looks, from the
outside, exactly like a day on which the engine found nothing — and those two
call for opposite work.

Four things are tested and each cost a rule to learn:

1. **Append-only and idempotent per `(decision_id, state)`.** Two surfaces
   retrieving the same row on the same day is the normal case; a ledger that
   counted it twice would report engagement it did not have.
2. **The order is enforced BY NAME.** `FILLED` before `DECIDED` is a refusal
   that says why, not a silent append.
3. **The enforcement can go green.** `SCORED` is reachable from `DECIDED` alone,
   because nothing in this repo can ever write `FILLED` and a gate that cannot
   go green is a broken gate, not a strict one.
4. **`ORDER_SUBMITTED`/`FILLED` cannot be written here at all.** They belong to
   the execution artery, and a research process that could stamp them could make
   a paper fill look like a real one in the only file that records the
   difference.

Every write goes to `tmp_path`; the grader is handed a fake price frame and
never touches the network.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from backend.services import decision_ledger as DL


@pytest.fixture()
def ledger(tmp_path):
    return tmp_path / "ledger.jsonl"


def test_the_states_and_their_ranks_agree_with_the_contract():
    from backend.services import decision_contract as DC
    assert DL.STATES == DC.DECISION_STATES
    assert set(DL.RANK) == set(DL.STATES)
    assert DL.RANK["REFUSED"] == DL.RANK["ORDER_SUBMITTED"], (
        "REFUSED and ORDER_SUBMITTED are alternatives at one point in the "
        "lifecycle, not successive steps")


def test_a_row_is_appended_and_read_back(ledger):
    row = DL.record("abc123", "DECIDED", by="morning", asof="2026-09-19",
                    path=ledger)
    assert row["state"] == "DECIDED"
    assert row["by"] == "morning"
    assert row["evidence_population"]
    assert row["ledger_version"]
    lines = ledger.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["decision_id"] == "abc123"


def test_the_same_state_twice_is_idempotent_and_says_so(ledger):
    DL.record("abc", "DECIDED", by="morning", path=ledger)
    again = DL.record("abc", "DECIDED", by="daily_pass", path=ledger)
    assert again["duplicate"] is True
    assert again["by"] == "morning", "the FIRST writer is the one on record"
    assert len(ledger.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_the_file_is_append_only(ledger):
    DL.record("abc", "DECIDED", by="morning", path=ledger)
    DL.record("abc", "DELIVERED", by="copilot", path=ledger)
    DL.record("def", "DECIDED", by="morning", path=ledger)
    assert DL.states_of("abc", path=ledger) == ["DECIDED", "DELIVERED"]
    assert len(DL.read(ledger)) == 3


def test_a_filled_before_decided_refuses_by_name(ledger):
    with pytest.raises(DL.DecisionLedgerError) as exc:
        DL.record("never-seen", "FILLED", by="x", path=ledger,
                  allow_execution_states=True)
    assert "before DECIDED" in str(exc.value)
    assert not ledger.exists(), "a refused row must not create the file"


def test_the_lifecycle_only_moves_forward(ledger):
    """A state whose rank is BEHIND what the row already reached is refused.

    Note the order of the two rules: a repeat of a state already on the row is
    the IDEMPOTENCE path (two surfaces delivering the same row is normal), and
    only a genuinely new state that walks the lifecycle backwards is a refusal.
    """
    DL.record("abc", "DECIDED", by="morning", path=ledger)
    DL.record("abc", "SCORED", by="decision_grader", path=ledger)
    with pytest.raises(DL.DecisionLedgerError) as exc:
        DL.record("abc", "DELIVERED", by="desktop_ask", path=ledger)
    assert "cannot follow" in str(exc.value)
    assert "SCORED" in str(exc.value)
    # and a repeat of what is already there is a duplicate, not a refusal
    assert DL.record("abc", "SCORED", by="anybody", path=ledger)["duplicate"]


def test_scored_is_reachable_from_decided_alone(ledger):
    """The gate that would otherwise never go green in this repo."""
    DL.record("abc", "DECIDED", by="morning", path=ledger)
    row = DL.record("abc", "SCORED", by="decision_grader", path=ledger)
    assert row["state"] == "SCORED"
    assert "duplicate" not in row


def test_refused_and_order_submitted_are_mutually_exclusive(ledger):
    DL.record("abc", "DECIDED", by="morning", path=ledger)
    DL.record("abc", "REFUSED", by="engine", path=ledger)
    with pytest.raises(DL.DecisionLedgerError) as exc:
        DL.record("abc", "ORDER_SUBMITTED", by="artery", path=ledger,
                  allow_execution_states=True)
    assert "alternative" in str(exc.value)


def test_this_repo_cannot_write_the_execution_arterys_states(ledger):
    DL.record("abc", "DECIDED", by="morning", path=ledger)
    for state in sorted(DL.EXECUTION_ARTERY_STATES):
        with pytest.raises(DL.DecisionLedgerError) as exc:
            DL.record("abc", state, by="anybody", path=ledger)
        assert "EXECUTION artery" in str(exc.value)


def test_an_undeclared_state_is_refused_with_the_closed_set_named(ledger):
    with pytest.raises(DL.DecisionLedgerError) as exc:
        DL.record("abc", "PROBABLY_FINE", by="x", path=ledger)
    assert "not a declared decision state" in str(exc.value)
    assert "DECIDED" in str(exc.value)


def test_an_empty_decision_id_is_refused(ledger):
    with pytest.raises(DL.DecisionLedgerError):
        DL.record("", "DECIDED", by="x", path=ledger)


def test_record_many_keeps_going_past_one_refusal(ledger):
    DL.record("good", "DECIDED", by="morning", path=ledger)
    out = DL.record_many(["good", "unknown"], "DELIVERED", by="copilot",
                         path=ledger)
    assert out["written"] == 1
    assert len(out["refused"]) == 1
    assert out["refused"][0]["decision_id"] == "unknown"
    out2 = DL.record_many(["good"], "DELIVERED", by="copilot", path=ledger)
    assert out2["duplicate"] == 1


def test_summary_counts_states_for_one_contract_day(ledger):
    DL.record("a", "DECIDED", by="morning", asof="2026-09-19", path=ledger)
    DL.record("b", "DECIDED", by="morning", asof="2026-09-19", path=ledger)
    DL.record("a", "DELIVERED", by="copilot", asof="2026-09-19", path=ledger)
    DL.record("c", "DECIDED", by="morning", asof="2026-09-18", path=ledger)
    s = DL.summary("2026-09-19", path=ledger)
    assert s["n_decisions"] == 2
    assert s["count_by_state"]["DECIDED"] == 2
    assert s["count_by_state"]["DELIVERED"] == 1
    assert s["count_by_state"]["FILLED"] == 0
    assert s["states_declared"] == list(DL.STATES)
    assert "execution repo" in s["note"]
    every = DL.summary(path=ledger)
    assert every["n_rows"] == 4


def test_an_unparseable_line_does_not_hide_the_good_rows(ledger):
    DL.record("a", "DECIDED", by="morning", path=ledger)
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write("{not json at all\n")
    assert len(DL.read(ledger)) == 1


# ── the grader ─────────────────────────────────────────────────────────────

def _frame(rows):
    pd = pytest.importorskip("pandas")
    idx = pd.to_datetime([d for d, _ in rows])
    return pd.DataFrame({"AAA": [v for _, v in rows]}, index=idx)


def test_nothing_is_scored_before_its_own_expiry(ledger):
    row = {"decision_id": "a", "ticker": "AAA", "asof": "2026-09-19",
           "direction": "BUY", "source": "investment_committee",
           "expiry_utc": "2027-03-20T00:00:00+00:00"}

    def boom(*a, **k):                     # the fetch must never be called
        raise AssertionError("a row that is not due must not cost a fetch")

    out = DL.score_due(today=date(2026, 9, 20), contracts=[row],
                       price_fetch=boom, path=ledger)
    assert out["status"] == "nothing_to_do"
    assert out["due"] == 0


def test_a_due_row_is_scored_on_close_to_close(ledger):
    DL.record("a", "DECIDED", by="morning", asof="2026-09-19", path=ledger)
    row = {"decision_id": "a", "ticker": "AAA", "asof": "2026-09-19",
           "direction": "BUY", "source": "investment_committee",
           "expiry_utc": "2026-09-25T00:00:00+00:00",
           "artifact_sha256": "deadbeef"}
    frame = _frame([("2026-09-19", 100.0), ("2026-09-25", 110.0)])
    out = DL.score_due(today=date(2026, 9, 26), contracts=[row],
                       price_fetch=lambda *a, **k: frame, path=ledger)
    assert out["status"] == "ok"
    assert out["newly_scored"] == 1
    assert out["scored"][0]["realised_return"] == pytest.approx(0.10)
    assert "SCORED" in DL.states_of("a", path=ledger)


def test_the_grader_writes_the_benchmark_beside_the_raw_return(ledger):
    """Chunk 23a, §16.5 item 37: the external figure beside the internal one.

    A raw close-to-close return is mostly the market. A panel built on raw
    returns measures beta and calls it a mechanism, so the grader records the
    benchmark's own return over the SAME window and the difference — and when
    the benchmark cannot be priced both fields are present and null with the
    reason, never a zero, which would read as 'the market did nothing'.
    """
    pd = pytest.importorskip("pandas")
    DL.record("a", "DECIDED", by="morning", asof="2026-09-19", path=ledger)
    row = {"decision_id": "a", "ticker": "AAA", "asof": "2026-09-19",
           "direction": "BUY", "source": "investment_committee",
           "expiry_utc": "2026-09-25T00:00:00+00:00"}
    idx = pd.to_datetime(["2026-09-19", "2026-09-25"])
    frame = pd.DataFrame({"AAA": [100.0, 110.0], "SPY": [400.0, 412.0]},
                         index=idx)
    asked: list = []

    def fetch(tickers, start, end):
        asked.append(list(tickers))
        return frame

    out = DL.score_due(today=date(2026, 9, 26), contracts=[row],
                       price_fetch=fetch, path=ledger)
    assert "SPY" in asked[0], (
        "the benchmark is REQUESTED with the names; a benchmark nobody asked "
        "for could never be in the frame and the field would be null for ever")
    got = out["scored"][0]
    assert got["realised_return"] == pytest.approx(0.10)
    assert got["benchmark_return"] == pytest.approx(0.03)
    assert got["excess_return"] == pytest.approx(0.07)
    assert got["benchmark_symbol"] == "SPY"


def test_a_missing_benchmark_is_null_with_a_reason_never_a_zero(ledger):
    DL.record("a", "DECIDED", by="morning", asof="2026-09-19", path=ledger)
    row = {"decision_id": "a", "ticker": "AAA", "asof": "2026-09-19",
           "direction": "BUY", "source": "investment_committee",
           "expiry_utc": "2026-09-25T00:00:00+00:00"}
    frame = _frame([("2026-09-19", 100.0), ("2026-09-25", 110.0)])
    out = DL.score_due(today=date(2026, 9, 26), contracts=[row],
                       price_fetch=lambda *a, **k: frame, path=ledger)
    got = out["scored"][0]
    assert got["realised_return"] == pytest.approx(0.10)
    assert got["benchmark_return"] is None
    assert got["excess_return"] is None
    assert "CANNOT DETERMINE" in got["benchmark_basis"]


def test_a_probe_row_is_graded_like_any_other_and_carries_its_hypothesis(
        ledger):
    """Chunk 23a. A virtual row that is never graded taught nothing."""
    DL.record("p5", "DECIDED", by="morning", asof="2026-09-19", path=ledger)
    row = {"decision_id": "p5", "ticker": "AAA", "asof": "2026-09-19",
           "direction": "PROBE", "source": "investment_committee",
           "expiry_utc": "2026-09-25T00:00:00+00:00",
           "hypothesis_id": "abc123def456", "horizon_sessions": 5,
           "virtual": True, "selection_probability": 1.0}
    frame = _frame([("2026-09-19", 100.0), ("2026-09-25", 110.0)])
    out = DL.score_due(today=date(2026, 9, 26), contracts=[row],
                       price_fetch=lambda *a, **k: frame, path=ledger)
    assert out["newly_scored"] == 1
    got = out["scored"][0]
    assert got["direction"] == "PROBE"
    assert got["hypothesis_id"] == "abc123def456"
    assert got["horizon_sessions"] == 5
    assert got["selection_probability"] == 1.0


def test_an_unpriceable_row_stays_open_and_is_named(ledger):
    DL.record("a", "DECIDED", by="morning", asof="2026-09-19", path=ledger)
    row = {"decision_id": "a", "ticker": "AAA", "asof": "2026-09-19",
           "direction": "BUY", "source": "investment_committee",
           "expiry_utc": "2026-09-25T00:00:00+00:00"}
    frame = _frame([("2026-09-19", 100.0)])      # one close: no return exists
    out = DL.score_due(today=date(2026, 9, 26), contracts=[row],
                       price_fetch=lambda *a, **k: frame, path=ledger)
    assert out["newly_scored"] == 0
    assert out["unpriceable"]
    assert "CANNOT DETERMINE" in out["unpriceable"][0]["reason"]
    assert "SCORED" not in DL.states_of("a", path=ledger)


def test_a_failed_fetch_refuses_rather_than_grading_at_zero(ledger):
    row = {"decision_id": "a", "ticker": "AAA", "asof": "2026-09-19",
           "direction": "BUY", "source": "investment_committee",
           "expiry_utc": "2026-09-25T00:00:00+00:00"}

    def boom(*a, **k):
        raise OSError("network is unreachable (test)")

    out = DL.score_due(today=date(2026, 9, 26), contracts=[row],
                       price_fetch=boom, path=ledger)
    assert out["status"] == "refused"
    assert out["newly_scored"] == 0
    assert "stay open" in out["reason"]


def test_the_open_row_scan_picks_up_probe_rows_from_the_contract_files(
        ledger, tmp_path):
    """PROBE joined BUY and WATCH in the grader's own scan (chunk 23a)."""
    folder = tmp_path / "decisions"
    folder.mkdir()
    (folder / "2026-09-21.json").write_text(json.dumps({"rows": [
        {"decision_id": "b", "direction": "BUY", "ticker": "AAA"},
        {"decision_id": "p", "direction": "PROBE", "ticker": "BBB"},
        {"decision_id": "r", "direction": "REFUSED", "ticker": "CCC"},
    ]}), encoding="utf-8")
    got = DL._open_contract_rows(day=date(2026, 9, 22), out_dir=folder,
                                 path=ledger)
    assert {r["decision_id"] for r in got} == {"b", "p"}, (
        "a REFUSED row is not graded and a PROBE row is: the second is a "
        "virtual position with an expiry, and grading it is the whole point")


def test_a_row_with_no_expiry_is_unpriceable_not_graded(ledger):
    row = {"decision_id": "a", "ticker": "AAA", "asof": "2026-09-19",
           "direction": "BUY", "source": "investment_committee",
           "expiry_utc": None,
           "expiry_basis": "CANNOT DETERMINE: the row carries no falsifier"}
    out = DL.score_due(today=date(2027, 1, 1), contracts=[row],
                       price_fetch=lambda *a, **k: None, path=ledger)
    assert out["newly_scored"] == 0
    assert "CANNOT DETERMINE" in out["unpriceable"][0]["reason"]
