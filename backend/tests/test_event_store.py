"""The event store must remember yesterday without backdating it.

Three properties carry the weight:

* **acceptance time is ours** — a feed stamp from three days ago must never
  decide what a decision "knew", or lookahead arrives through the timestamp
  rather than through the data;
* **novelty is UNKNOWN on an empty store** — reporting every event as NEW on
  day one is not a measurement, and a learner that believes its first day was
  extraordinary has been misled by its own baseline;
* **a dead feed is visible** — the house failure mode is code that runs green
  and stores nothing.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.services import event_store as ES


def _ev(title="Nvidia beats", scope="NVDA", url="http://x/1",
        feed="yfinance_news", ts="2026-08-20T10:00:00+00:00"):
    return {
        "scope": scope,
        "event_type": "earnings",
        "direction": "positive",
        "direction_basis": "STATED",
        "source": {"feed": feed, "url": url, "publisher": "wire"},
        "timestamp": ts,
        "title": title,
        "extraction": {"tier": "HIGH", "method": "deterministic"},
        "context": {},
    }


UTC = timezone.utc


# ------------------------------------------------------------ content hash


def test_same_headline_from_two_feeds_collides():
    """Otherwise re-syndication reads as independent evidence."""
    a = _ev(feed="yfinance_news")
    b = _ev(feed="edgar_8k")
    assert ES.content_hash(a) == ES.content_hash(b)


def test_different_headlines_do_not_collide():
    assert ES.content_hash(_ev(title="A", url="u1")) != \
        ES.content_hash(_ev(title="B", url="u2"))


def test_hash_ignores_case_and_padding():
    assert ES.content_hash(_ev(title="  Nvidia Beats ")) == \
        ES.content_hash(_ev(title="nvidia beats"))


# ----------------------------------------------------------------- novelty


def test_novelty_is_UNKNOWN_on_an_empty_store(tmp_path):
    n = ES.novelty_of(_ev(), root=tmp_path)
    assert n["novelty"] == "UNKNOWN", (
        "an empty baseline reported a novelty verdict — day one would look "
        "extraordinary to anything learning from this")


def test_second_sighting_is_a_REPEAT(tmp_path):
    now = datetime(2026, 8, 23, 12, tzinfo=UTC)
    rec = ES.make_record(_ev(), accepted_at=now, root=tmp_path)
    ES.append([rec], root=tmp_path)
    n = ES.novelty_of(_ev(), root=tmp_path, today=now.date())
    assert n["novelty"] == "REPEAT"


def test_a_genuinely_different_event_is_NEW(tmp_path):
    now = datetime(2026, 8, 23, 12, tzinfo=UTC)
    ES.append([ES.make_record(_ev(), accepted_at=now, root=tmp_path)],
              root=tmp_path)
    n = ES.novelty_of(_ev(title="Recall announced", url="http://x/2"),
                      root=tmp_path, today=now.date())
    assert n["novelty"] == "NEW"


def test_novelty_window_forgets_old_events(tmp_path):
    old = datetime(2026, 1, 1, 12, tzinfo=UTC)
    ES.append([ES.make_record(_ev(), accepted_at=old, root=tmp_path)],
              root=tmp_path, day="2026-01-01")
    # Far outside the 30-day window: the baseline is empty again.
    n = ES.novelty_of(_ev(), root=tmp_path, today=old.date()
                      + timedelta(days=200))
    assert n["novelty"] == "UNKNOWN"


# ------------------------------------------------- acceptance vs source time


def test_accepted_at_is_stamped_never_taken_from_the_payload(tmp_path):
    """The core anti-lookahead property."""
    now = datetime(2026, 8, 23, 12, tzinfo=UTC)
    rec = ES.make_record(_ev(ts="2026-08-20T10:00:00+00:00"),
                         accepted_at=now, root=tmp_path)
    assert rec["accepted_at"].startswith("2026-08-23")
    assert rec["source_timestamp"] == "2026-08-20T10:00:00+00:00"
    assert rec["accepted_at"] != rec["source_timestamp"]


def test_availability_uses_the_acceptance_clock_not_the_source_clock(tmp_path):
    """An item stamped BEFORE a decision, but accepted AFTER it, is not
    available to that decision. This is the whole point."""
    decision = "2026-08-23T09:00:00+00:00"
    accepted_after = datetime(2026, 8, 23, 17, tzinfo=UTC)
    rec = ES.make_record(_ev(ts="2026-08-20T10:00:00+00:00"),
                         accepted_at=accepted_after, root=tmp_path)
    ES.append([rec], root=tmp_path)

    got = ES.available_to_decision(decision, root=tmp_path)
    assert got == [], (
        "an event accepted AFTER the decision leaked into it because its "
        "SOURCE timestamp predated the decision — that is lookahead")


def test_availability_includes_events_accepted_before(tmp_path):
    decision = "2026-08-23T17:00:00+00:00"
    rec = ES.make_record(_ev(), accepted_at=datetime(2026, 8, 23, 9,
                                                     tzinfo=UTC),
                         root=tmp_path)
    ES.append([rec], root=tmp_path)
    assert len(ES.available_to_decision(decision, root=tmp_path)) == 1


def test_availability_is_strict_at_the_boundary(tmp_path):
    """Same instant is not 'before'."""
    t = datetime(2026, 8, 23, 17, tzinfo=UTC)
    ES.append([ES.make_record(_ev(), accepted_at=t, root=tmp_path)],
              root=tmp_path)
    assert ES.available_to_decision(t.isoformat(), root=tmp_path) == []


def test_availability_filters_by_entity(tmp_path):
    t = datetime(2026, 8, 23, 9, tzinfo=UTC)
    ES.append([
        ES.make_record(_ev(scope="NVDA"), tickers=["NVDA"], accepted_at=t,
                       root=tmp_path),
        ES.make_record(_ev(scope="AMD", title="AMD news", url="http://y/1"),
                       tickers=["AMD"], accepted_at=t, root=tmp_path),
    ], root=tmp_path)
    got = ES.available_to_decision("2026-08-23T17:00:00+00:00",
                                   root=tmp_path, entity="AMD")
    assert [r["entities"] for r in got] == [["AMD"]]


# ------------------------------------------------------------- refusals


def test_untraceable_event_is_refused(tmp_path):
    bad = _ev(title="", url=None)
    with pytest.raises(ES.EventRejected):
        ES.make_record(bad, root=tmp_path)


def test_append_is_append_only(tmp_path):
    t = datetime(2026, 8, 23, 9, tzinfo=UTC)
    ES.append([ES.make_record(_ev(), accepted_at=t, root=tmp_path)],
              root=tmp_path)
    ES.append([ES.make_record(_ev(title="second", url="http://x/2"),
                              accepted_at=t, root=tmp_path)], root=tmp_path)
    assert len(ES._read_day("2026-08-23", tmp_path)) == 2


def test_corrupt_line_does_not_blind_the_whole_day(tmp_path):
    t = datetime(2026, 8, 23, 9, tzinfo=UTC)
    ES.append([ES.make_record(_ev(), accepted_at=t, root=tmp_path)],
              root=tmp_path)
    p = ES._day_path("2026-08-23", tmp_path)
    p.write_text(p.read_text(encoding="utf-8") + "{not json\n", encoding="utf-8")
    assert len(ES._read_day("2026-08-23", tmp_path)) == 1


# ---------------------------------------------------------------- ingestion


def test_ingestion_failure_is_visible_not_an_empty_day(tmp_path, monkeypatch):
    """The house failure mode: green run, nothing stored, nobody told."""
    def boom(ticker):
        raise RuntimeError("feed down")

    monkeypatch.setattr("backend.services.event_intel.get_ticker_events", boom)
    out = ES.ingest_for_tickers(["NVDA"], root=tmp_path)
    assert out["status"] == "partial"
    assert "NVDA" in out["failures"]
    assert out["n_events"] == 0


def test_the_same_story_about_two_companies_is_two_events(tmp_path,
                                                          monkeypatch):
    """`scope` is in the content hash on purpose.

    One wire story naming two companies is two pieces of company-specific
    evidence, not one duplicated. Collapsing them would lose the AMD read of an
    NVDA headline, which is exactly the read-through the graph work wants.
    """
    def same(ticker):
        return {"events": [_ev(scope=ticker)], "unavailable_feeds": []}

    monkeypatch.setattr("backend.services.event_intel.get_ticker_events", same)
    out = ES.ingest_for_tickers(["NVDA", "AMD"], root=tmp_path,
                                accepted_at=datetime(2026, 8, 23, 9,
                                                     tzinfo=UTC))
    assert out["n_events"] == 2
    assert out["n_repeat"] == 0, out
    # First lands on an empty baseline (UNKNOWN); the second can see it.
    assert out["n_unknown_novelty"] == 1 and out["n_new"] == 1, out


def test_one_companys_story_from_two_feeds_dedups_within_a_pass(tmp_path,
                                                                monkeypatch):
    """Re-syndication of the SAME company's story must read as a repeat."""
    def duplicated(ticker):
        return {"events": [_ev(feed="yfinance_news"),
                           _ev(feed="edgar_8k")],
                "unavailable_feeds": []}

    monkeypatch.setattr("backend.services.event_intel.get_ticker_events",
                        duplicated)
    out = ES.ingest_for_tickers(["NVDA"], root=tmp_path,
                                accepted_at=datetime(2026, 8, 23, 9,
                                                     tzinfo=UTC))
    assert out["n_events"] == 2
    assert out["n_repeat"] == 1, out


def test_novelty_survives_across_days_not_just_within_a_pass(tmp_path,
                                                             monkeypatch):
    """The whole reason the store exists: yesterday must still count."""
    def one(ticker):
        return {"events": [_ev()], "unavailable_feeds": []}

    monkeypatch.setattr("backend.services.event_intel.get_ticker_events", one)
    ES.ingest_for_tickers(["NVDA"], root=tmp_path,
                          accepted_at=datetime(2026, 8, 22, 9, tzinfo=UTC))
    out = ES.ingest_for_tickers(["NVDA"], root=tmp_path,
                                accepted_at=datetime(2026, 8, 23, 9,
                                                     tzinfo=UTC))
    assert out["n_repeat"] == 1, (
        "the same headline re-read the next day counted as fresh evidence")


# ------------------------------------------------------------------- health


def test_health_reports_ABSENT_before_anything_is_ingested(tmp_path):
    assert ES.health(root=tmp_path / "nope")["status"] == "ABSENT"


def test_health_ok_after_a_recent_day(tmp_path):
    t = datetime(2026, 8, 23, 9, tzinfo=UTC)
    ES.append([ES.make_record(_ev(), accepted_at=t, root=tmp_path)],
              root=tmp_path)
    h = ES.health(root=tmp_path, today=t.date())
    assert h["status"] == "ok" and h["n_events_window"] == 1


def test_health_degrades_when_the_store_goes_quiet(tmp_path):
    t = datetime(2026, 8, 1, 9, tzinfo=UTC)
    ES.append([ES.make_record(_ev(), accepted_at=t, root=tmp_path)],
              root=tmp_path)
    h = ES.health(root=tmp_path, today=t.date() + timedelta(days=20))
    assert h["status"] == "DEGRADED" and h["days_quiet"] == 20
