"""TEACHER-LIBRARY-1 — the canonical event ledger.

The tests that matter here are almost all about REFUSAL and about time. A
teacher ledger that quietly admits a filing before it was public, or that scores
a broken feed as a quiet week, produces research that looks clean and is wrong —
and neither failure raises anything on its own.

Offline and deterministic.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from backend.services.teacher_library import adapters as A
from backend.services.teacher_library import events as E
from backend.services.teacher_library import ledger as L
from backend.services.teacher_library.events import TeacherEvent


def _ev(**kw) -> TeacherEvent:
    base = dict(source="test", source_event_id="1", actor_id="cik:1",
                actor_type=E.ACTOR_CORPORATE_INSIDER, action_type="BUY",
                ticker_at_event="AAA", public_at="2026-08-10T00:00:00+00:00")
    base.update(kw)
    return TeacherEvent(**base)


@pytest.fixture
def path(tmp_path):
    return tmp_path / "events.jsonl"


# ── the taxonomy refuses free text ─────────────────────────────────────────

def test_a_politician_cannot_be_filed_as_a_corporate_insider():
    """CORPORATE_INSIDER is a statutory category — officers, directors and
    >10% holders under Section 16. Using it for a congressional trader would
    put a legal claim into the database as a category label."""
    ok = _ev(actor_type=E.ACTOR_POLITICIAN)
    assert ok.actor_type == "POLITICIAN"
    with pytest.raises(E.TeacherEventInvalid, match="not in the taxonomy"):
        _ev(actor_type="insider_trader")


def test_an_unknown_action_type_is_refused():
    with pytest.raises(E.TeacherEventInvalid):
        _ev(action_type="YOLO")


def test_the_required_identity_fields_are_required():
    for missing in ("source", "source_event_id", "actor_id"):
        with pytest.raises(E.TeacherEventInvalid, match="deduplicated"):
            _ev(**{missing: ""})


# ── time: the invariants that make the ledger honest ───────────────────────

def test_a_usable_event_without_public_at_is_refused():
    """`public_at` is the only timestamp a copy strategy may enter on. A usable
    row without one cannot be used and must not pretend it can."""
    with pytest.raises(E.TeacherEventInvalid, match="only timestamp"):
        _ev(public_at=None)


def test_a_failure_row_may_omit_public_at():
    """Recording that a source failed is not an actionable event, so it is not
    held to the actionable-event contract — but it still gets written."""
    e = _ev(public_at=None, status=E.UNAVAILABLE, reason="sec_403")
    assert not e.usable


def test_a_transaction_after_its_disclosure_is_impossible_and_refused():
    """Information cannot become public before the act it describes. This shape
    is a date-parse error wearing a plausible mask, and admitting it would
    produce a NEGATIVE disclosure lag that later reads as prescience."""
    with pytest.raises(E.TeacherEventInvalid, match="cannot become public"):
        _ev(transaction_at="2026-08-20T00:00:00+00:00",
            public_at="2026-08-10T00:00:00+00:00")


def test_disclosure_lag_is_measured_from_the_two_stored_timestamps():
    e = _ev(transaction_at="2026-08-01", public_at="2026-08-11")
    assert e.disclosure_lag_days() == pytest.approx(10.0)


def test_disclosure_lag_is_none_when_the_source_reports_no_trade_date():
    """13F gives a quarter-end holding and a filing date, never a trade date.
    Inventing one would manufacture a lag that was never measured."""
    assert _ev(transaction_at=None).disclosure_lag_days() is None


def test_inverted_amount_ranges_are_refused():
    with pytest.raises(E.TeacherEventInvalid, match="amount_low"):
        _ev(amount_low=100_000.0, amount_high=1_000.0)


# ── identity is deterministic across processes ─────────────────────────────

def test_the_event_id_is_sha256_and_stable():
    """Python salts string hashing per process, so `hash()` here would give the
    same filing a different identity on every run and deduplication would
    silently stop working."""
    a, b = _ev(), _ev()
    assert a.event_id() == b.event_id()
    assert len(a.event_id()) == 64
    int(a.event_id(), 16)
    assert _ev(shares=10.0).event_id() != _ev(shares=11.0).event_id()


def test_two_actors_with_the_same_name_are_not_the_same_actor():
    """"SMITH JOHN" is not an identifier. Keying on it silently merges two
    people's histories into one actor's track record."""
    a = _ev(actor_id="cik:111", actor_name="SMITH JOHN")
    b = _ev(actor_id="cik:222", actor_name="SMITH JOHN")
    assert a.event_id() != b.event_id()


def test_the_same_ticker_at_two_issuers_is_not_the_same_security():
    a = _ev(security_id="cik:111:AAA")
    b = _ev(security_id="cik:222:AAA")
    assert a.event_id() != b.event_id()


# ── the ledger: append-only, deduplicated ──────────────────────────────────

def test_appending_the_same_event_twice_writes_it_once(path):
    r1 = L.append([_ev()], path=path)
    r2 = L.append([_ev()], path=path)
    assert r1["written"] == 1 and r2["written"] == 0 and r2["duplicates"] == 1
    assert len(L.all_events(path)) == 1


def test_a_rerun_over_the_same_window_is_a_no_op(path):
    evs = [_ev(source_event_id=str(i)) for i in range(5)]
    L.append(evs, path=path)
    again = L.append(evs, path=path)
    assert again["written"] == 0 and again["duplicates"] == 5


def test_an_unreadable_line_is_reported_not_silently_dropped(path, caplog):
    L.append([_ev()], path=path)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    with caplog.at_level("ERROR"):
        rows = L.all_events(path)
    assert len(rows) == 1
    assert "LOWER BOUNDS" in caplog.text


# ── point in time: the whole reason this exists ────────────────────────────

def test_a_read_cannot_see_a_filing_that_was_not_public_yet(path):
    L.append([_ev(source_event_id="early", public_at="2026-08-01"),
              _ev(source_event_id="late", public_at="2026-08-20")], path=path)
    visible = L.events_asof("2026-08-10", path=path)
    assert [e.source_event_id for e in visible] == ["early"]


def test_the_filter_is_on_public_at_and_never_on_transaction_at(path):
    """The trade happened long before the cutoff; the disclosure did not. A
    ledger filtering on transaction_at would hand a backtest a position nobody
    could have held."""
    L.append([_ev(source_event_id="x", transaction_at="2026-07-01",
                  public_at="2026-08-20")], path=path)
    assert L.events_asof("2026-08-10", path=path) == []
    assert len(L.events_asof("2026-08-21", path=path)) == 1


def test_non_usable_rows_are_excluded_from_a_research_read_by_default(path):
    L.append([_ev(source_event_id="ok"),
              _ev(source_event_id="bad", status=E.UNAVAILABLE,
                  public_at="2026-08-01")], path=path)
    ids = [e.source_event_id for e in L.events_asof("2026-08-30", path=path)]
    assert ids == ["ok"]
    assert len(L.events_asof("2026-08-30", path=path, usable_only=False)) == 2


def test_a_late_filing_is_still_usable_because_it_really_was_disclosed(path):
    """LATE_FILING is a quality flag about the actor, not a reason to discard
    the event — the lateness is itself a measurable behaviour."""
    L.append([_ev(source_event_id="l", status=E.LATE_FILING)], path=path)
    assert len(L.events_asof("2026-08-30", path=path)) == 1


def test_filters_narrow_without_widening_the_time_window(path):
    L.append([_ev(source_event_id="a", ticker_at_event="AAA"),
              _ev(source_event_id="b", ticker_at_event="BBB",
                  actor_type=E.ACTOR_POLITICIAN, public_at="2026-08-20")],
             path=path)
    got = L.events_asof("2026-08-30", path=path, tickers=["bbb"])
    assert [e.source_event_id for e in got] == ["b"]
    got = L.events_asof("2026-08-10", path=path, tickers=["bbb"])
    assert got == []


# ── amendments ─────────────────────────────────────────────────────────────

def test_an_amendment_supersedes_its_parent_once_it_is_public(path):
    original = _ev(source_event_id="orig", shares=100.0, public_at="2026-08-01")
    L.append([original], path=path)
    fixed = _ev(source_event_id="orig-a", shares=250.0, public_at="2026-08-15",
                is_amendment=True, amends_event_id=original.event_id())
    L.append([fixed], path=path)

    # before the correction: the world saw the original
    before = L.events_asof("2026-08-10", path=path)
    assert [e.shares for e in before] == [100.0]

    # after: the amendment, and the parent does not double-count
    after = L.events_asof("2026-08-20", path=path)
    assert [e.shares for e in after] == [250.0]


def test_an_amendment_does_not_rewrite_the_original_row(path):
    original = _ev(source_event_id="orig", shares=100.0, public_at="2026-08-01")
    L.append([original], path=path)
    L.append([_ev(source_event_id="orig-a", shares=250.0,
                  public_at="2026-08-15", is_amendment=True,
                  amends_event_id=original.event_id())], path=path)
    raw = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    assert len(raw) == 2
    assert raw[0]["shares"] == 100.0, "the ledger rewrote history in place"


# ── coverage counts failures as failures ───────────────────────────────────

def test_coverage_counts_unavailable_rows_so_broken_never_reads_as_quiet(path):
    L.append([_ev(source_event_id="a"),
              _ev(source_event_id="b", status=E.UNAVAILABLE,
                  public_at=None, reason="sec_403")], path=path)
    cov = L.coverage(path)
    assert cov["n_events"] == 2
    assert cov["by_status"][E.UNAVAILABLE] == 1
    assert "FAILING" in cov["note"]


# ── the Form 4 adapter, end to end ─────────────────────────────────────────

def _payload(**kw):
    base = {"ticker": "AAPL", "status": "OK_DATA", "buys": [
        {"name": "DOE JANE", "cik": "12345", "shares": 1000.0,
         "value": 50_000.0, "date": "2026-08-01", "filing_date": "2026-08-03"}]}
    base.update(kw)
    return base


def test_form4_public_at_is_the_filing_date_not_the_transaction_date():
    """Section 16 allows two business days between the trade and the filing.
    The gap is real, routinely non-zero, and is the quantity the copyability
    question turns on."""
    ev = A.Form4Adapter().to_events(_payload())[0]
    assert ev.public_at.startswith("2026-08-03")
    assert ev.transaction_at.startswith("2026-08-01")
    assert ev.disclosure_lag_days() == pytest.approx(2.0)


def test_form4_records_identity_quality_rather_than_assuming_it():
    with_cik = A.Form4Adapter().to_events(_payload())[0]
    assert with_cik.identity_quality == "cik"
    p = _payload()
    p["buys"][0]["cik"] = ""
    no_cik = A.Form4Adapter().to_events(p)[0]
    assert no_cik.identity_quality == "name_only"
    assert no_cik.actor_id.startswith("name:")


def test_an_unavailable_source_produces_a_status_row_not_silence():
    """Emitting nothing on failure is how a broken feed becomes a quiet week."""
    evs = A.Form4Adapter().to_events(
        {"ticker": "AAPL", "status": "UNAVAILABLE", "reason": "cik_map_unavailable"})
    assert len(evs) == 1
    assert evs[0].status == E.UNAVAILABLE
    assert evs[0].reason == "cik_map_unavailable"
    assert not evs[0].usable


def test_an_empty_source_and_an_unavailable_source_differ_in_the_ledger(path):
    ad = A.Form4Adapter()
    L.append(ad.to_events({"ticker": "A", "status": "OK_EMPTY",
                           "reason": "no_open_market_purchases"}), path=path)
    L.append(ad.to_events({"ticker": "B", "status": "UNAVAILABLE",
                           "reason": "submissions_fetch_failed"}), path=path)
    cov = L.coverage(path)
    assert cov["by_status"][E.OK_EMPTY] == 1
    assert cov["by_status"][E.UNAVAILABLE] == 1


def test_a_partial_source_flags_its_own_lower_bound():
    ev = A.Form4Adapter().to_events(_payload(partial=True))[0]
    assert "source_partial_lower_bound" in ev.data_quality_flags


def test_a_transaction_with_no_filing_date_is_a_parse_error_not_a_signal():
    p = _payload()
    p["buys"][0]["filing_date"] = ""
    ev = A.Form4Adapter().to_events(p)[0]
    assert ev.status == E.PARSE_ERROR
    assert not ev.usable


def test_ingest_wires_source_to_ledger_and_reports_what_it_wrote(path):
    ad = A.Form4Adapter(fetch=lambda t, **kw: _payload(ticker=t))
    res = A.ingest(ad, ["AAPL", "MSFT"], path=path)
    assert res["subjects"] == 2 and res["written"] == 2
    assert res["usable_events"] == 2
    assert res["status_by_subject"] == {"AAPL": "OK_DATA", "MSFT": "OK_DATA"}
    assert L.append([], path=path)["written"] == 0

    got = L.events_asof("2026-08-30", path=path)
    assert {e.ticker_at_event for e in got} == {"AAPL", "MSFT"}
    assert all(e.actor_type == E.ACTOR_CORPORATE_INSIDER for e in got)
    assert L.events_asof("2026-08-02", path=path) == []   # before disclosure


def test_a_raising_fetch_becomes_an_unavailable_row_rather_than_a_crash(path):
    def boom(t, **kw):
        raise RuntimeError("SEC 403")
    res = A.ingest(A.Form4Adapter(fetch=boom), ["AAPL"], path=path)
    assert res["usable_events"] == 0
    rows = L.all_events(path)
    assert rows[0].status == E.UNAVAILABLE
    assert "fetch_raised" in rows[0].reason


def test_the_provenance_hash_is_deterministic():
    a = A.Form4Adapter().to_events(_payload())[0]
    b = A.Form4Adapter().to_events(_payload())[0]
    assert a.raw_sha256 == b.raw_sha256 and len(a.raw_sha256) == 64
