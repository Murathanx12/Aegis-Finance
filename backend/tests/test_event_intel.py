"""
EVENT-INTEL tests (offline)
===========================

Exercises the 2026-07-29B acceptance spec: direction taxonomy, extraction
tiers as parse fidelity, canary-gated empty-vs-unavailable disclosure, the
no-advice playbook (enforced by construction + scrubber), measured-only
context cards, and the router.

Run with:
    python -m pytest backend/tests/test_event_intel.py -v
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services import event_intel as ei
from backend import observability as obs


@pytest.fixture(autouse=True)
def _fresh_obs():
    obs.reset_for_tests()
    yield
    obs.reset_for_tests()


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    """Default: deterministic path (individual tests re-enable the LLM mock)."""
    monkeypatch.setattr(ei, "_classify_llm", lambda ticker, titles: None)


@pytest.fixture(autouse=True)
def _canary_healthy(monkeypatch):
    """Default: feeds are considered healthy (tests override to exercise)."""
    monkeypatch.setattr(ei, "_canary_ok", lambda feed: True)


# ── Keyword classification (deterministic fallback) ───────────────


def test_keywords_positive():
    etype, direction, basis, tier = ei._classify_keywords(
        "Acme beats estimates and raises guidance")
    assert direction == "positive"
    assert basis == "IMPLIED"
    assert tier == "LOW"


def test_keywords_negative():
    etype, direction, basis, tier = ei._classify_keywords(
        "Acme misses on revenue, announces layoffs")
    assert direction == "negative"
    assert basis == "IMPLIED"


def test_keywords_unknown_is_said_not_guessed():
    etype, direction, basis, tier = ei._classify_keywords(
        "Acme to present at industry conference")
    assert direction == "unknown"
    assert basis == "UNKNOWN"


def test_keywords_event_types():
    assert ei._classify_keywords("Acme Q3 earnings preview")[0] == "earnings"
    assert ei._classify_keywords("FDA approves Acme device")[0] == "regulatory"
    assert ei._classify_keywords("Acme to acquire Widget Corp")[0] == "ma"
    assert ei._classify_keywords("Acme CFO resigns")[0] == "management_change"


# ── Event assembly: enums only, honest degradation ────────────────


def test_make_event_rejects_invalid_direction():
    ev = ei._make_event(
        scope="AAPL", event_type="earnings", direction="to_the_moon",
        basis="EXPLICIT", feed="test", title="x", timestamp=None)
    assert ev["direction"] == "unknown"
    assert ev["direction_basis"] == "UNKNOWN"
    assert ev["extraction"]["tier"] == "FAILED"


def test_make_event_default_context_is_no_measured_base_rate():
    ev = ei._make_event(
        scope="AAPL", event_type="other", direction="unknown",
        basis="UNKNOWN", feed="test", title="x", timestamp=None)
    assert ev["context"]["base_rate"]["status"] == "none_measured"


def test_direction_is_relative_to_scope():
    ev = ei._make_event(
        scope="NVDA", event_type="earnings", direction="positive",
        basis="EXPLICIT", feed="test", title="x", timestamp=None)
    assert ev["direction_relative_to"] == "NVDA"


# ── News block ────────────────────────────────────────────────────


def _fake_news(*_a, **_k):
    return [
        {"title": "Acme beats estimates", "publisher": "P", "link": "https://x",
         "published": None, "type": "STORY"},
        {"title": "Acme to host investor day", "publisher": "P", "link": "https://y",
         "published": None, "type": "STORY"},
    ]


def test_news_block_keyword_fallback(monkeypatch):
    import backend.services.news_intelligence as ni
    monkeypatch.setattr(ni, "fetch_stock_news", _fake_news)
    block = ei._news_block("ACME")
    assert block["status"] == "ok"
    assert len(block["events"]) == 2
    assert block["events"][0]["direction"] == "positive"
    assert block["events"][0]["extraction"]["method"] == "keyword"
    assert block["events"][1]["direction"] == "unknown"


def test_news_block_empty_with_healthy_canary_is_quiet_not_unavailable(monkeypatch):
    import backend.services.news_intelligence as ni
    monkeypatch.setattr(ni, "fetch_stock_news", lambda *a, **k: [])
    block = ei._news_block("ACME")
    assert block["status"] == "ok"
    assert block["events"] == []


def test_news_block_empty_with_dead_canary_is_disclosed(monkeypatch):
    import backend.services.news_intelligence as ni
    monkeypatch.setattr(ni, "fetch_stock_news", lambda *a, **k: [])
    monkeypatch.setattr(ei, "_canary_ok", lambda feed: False)
    block = ei._news_block("ACME")
    assert block["status"] == "unavailable"
    assert "canary" in block["error"]


def test_news_block_llm_labels_applied(monkeypatch):
    import backend.services.news_intelligence as ni
    monkeypatch.setattr(ni, "fetch_stock_news", _fake_news)
    monkeypatch.setattr(ei, "_classify_llm", lambda t, titles: [
        {"i": 0, "event_type": "earnings", "direction": "positive",
         "basis": "EXPLICIT"},
    ])
    block = ei._news_block("ACME")
    ev0 = block["events"][0]
    assert ev0["extraction"] == {"tier": "MEDIUM", "method": "llm"}
    assert ev0["direction_basis"] == "EXPLICIT"
    # headline 1 had no LLM label -> keyword fallback, not dropped
    assert block["events"][1]["extraction"]["method"] == "keyword"


def test_llm_parse_garbage_returns_none(monkeypatch):
    from backend.services import llm_analyzer
    monkeypatch.setattr(ei, "_llm_disabled", lambda: False)
    monkeypatch.setattr(llm_analyzer, "is_available", lambda: True)
    monkeypatch.setattr(llm_analyzer, "_call_llm",
                        lambda *a, **k: "sorry, cannot help with that")
    assert ei.__dict__["_classify_llm"]("ACME", ["headline"]) is None


def test_llm_kill_switch(monkeypatch):
    monkeypatch.setenv("AEGIS_DISABLE_EVENT_LLM", "1")
    assert ei.__dict__["_classify_llm"]("ACME", ["headline"]) is None


# ── EDGAR block ───────────────────────────────────────────────────


def _fake_filing(items, event_types, materiality=0.9):
    from backend.services.edgar_events import EdgarEvent
    return EdgarEvent(
        ticker="ACME", cik=1, accession="a", form="8-K", filed="2026-07-20",
        items=items, event_types=event_types, materiality=materiality,
        primary_doc_url="https://sec.gov/x", is_8k=True)


def test_edgar_bankruptcy_item_is_explicit_negative(monkeypatch):
    import backend.services.edgar_events as ee
    monkeypatch.setattr(ee, "fetch_events_for_ticker",
                        lambda *a, **k: [_fake_filing(["1.03"], ["bankruptcy"])])
    block = ei._edgar_block("ACME")
    ev = block["events"][0]
    assert ev["direction"] == "negative"
    assert ev["direction_basis"] == "EXPLICIT"
    assert ev["extraction"]["tier"] == "HIGH"
    # filing-conditioned cohorts are selection-contaminated -> no drift stat
    assert ev["context"]["base_rate"]["status"] == "none_measured"
    assert "selection" in ev["context"]["note"]


def test_edgar_directionless_item_is_unknown(monkeypatch):
    import backend.services.edgar_events as ee
    monkeypatch.setattr(ee, "fetch_events_for_ticker",
                        lambda *a, **k: [_fake_filing(["8.01"], ["other"])])
    block = ei._edgar_block("ACME")
    assert block["events"][0]["direction"] == "unknown"
    assert block["events"][0]["direction_basis"] == "UNKNOWN"


def test_edgar_empty_with_dead_canary_disclosed(monkeypatch):
    import backend.services.edgar_events as ee
    monkeypatch.setattr(ee, "fetch_events_for_ticker", lambda *a, **k: [])
    monkeypatch.setattr(ei, "_canary_ok", lambda feed: False)
    assert ei._edgar_block("ACME")["status"] == "unavailable"


# ── Earnings block ────────────────────────────────────────────────


def test_earnings_beat_is_explicit_with_measured_base_rate(monkeypatch):
    import backend.services.earnings_intelligence as eint
    monkeypatch.setattr(eint, "get_earnings_summary", lambda t: {
        "ticker": t,
        "earnings_surprises": [
            {"quarter": "2026Q2", "eps_actual": 2.1, "eps_estimate": 2.0,
             "surprise_pct": 5.0, "beat": True},
            {"quarter": "2026Q1", "beat": False},
        ],
        "beat_rate": 0.5,
        "next_earnings_date": "2026-08-05",
        "days_until_earnings": 7,
    })
    block = ei._earnings_block("ACME")
    assert block["status"] == "ok"
    result = [e for e in block["events"] if "Reported" in e["title"]][0]
    assert result["direction"] == "positive"
    assert result["direction_basis"] == "EXPLICIT"
    br = result["context"]["base_rate"]
    assert br["status"] == "measured"
    assert br["n"] == 2  # the N-count ships with the stat

    scheduled = [e for e in block["events"] if "scheduled" in e["title"]][0]
    assert scheduled["direction"] == "neutral"
    assert scheduled["direction_basis"] == "NEUTRAL"


def test_earnings_error_with_dead_canary_disclosed(monkeypatch):
    import backend.services.earnings_intelligence as eint
    monkeypatch.setattr(eint, "get_earnings_summary",
                        lambda t: {"error": "boom", "ticker": t})
    monkeypatch.setattr(ei, "_canary_ok", lambda feed: False)
    assert ei._earnings_block("ACME")["status"] == "unavailable"


# ── Aggregation, playbook, observability ──────────────────────────


def test_get_ticker_events_aggregates_and_discloses(monkeypatch):
    monkeypatch.setattr(ei, "_news_block", lambda t: {
        "status": "ok", "events": [ei._make_event(
            scope=t, event_type="other", direction="unknown", basis="UNKNOWN",
            feed="yfinance_news", title="Acme in the news", timestamp="2026-07-28")]})
    monkeypatch.setattr(ei, "_edgar_block",
                        lambda t: {"status": "unavailable", "error": "canary"})
    monkeypatch.setattr(ei, "_earnings_block", lambda t: {"status": "ok", "events": []})
    out = ei.get_ticker_events("ACME")
    assert len(out["events"]) == 1
    assert out["unavailable_feeds"] == ["edgar_8k"]
    assert out["feeds"]["edgar_8k"]["status"] == "unavailable"
    # observability recorded the pass
    stats = obs.event_intel_stats()
    assert stats["events_extracted"] == 1
    assert stats["feed_calls"]["edgar_8k"]["unavailable"] == 1
    assert stats["feed_calls"]["yfinance_news"]["ok"] == 1


def test_advice_shaped_titles_are_scrubbed(monkeypatch):
    monkeypatch.setattr(ei, "_news_block", lambda t: {
        "status": "ok", "events": [ei._make_event(
            scope=t, event_type="other", direction="unknown", basis="UNKNOWN",
            feed="yfinance_news",
            title="Analysts: you should buy Acme before earnings",
            timestamp="2026-07-28")]})
    monkeypatch.setattr(ei, "_edgar_block", lambda t: {"status": "ok", "events": []})
    monkeypatch.setattr(ei, "_earnings_block", lambda t: {"status": "ok", "events": []})
    out = ei.get_ticker_events("ACME")
    assert "buy" not in out["events"][0]["title"].lower()


def test_no_advice_language_in_module_templates():
    # The playbook's forbidden list must not appear in anything WE render.
    assert not ei._FORBIDDEN_RE.search(
        ei.get_ticker_events.__doc__ or "")
    sample = ei._make_event(
        scope="X", event_type="other", direction="unknown", basis="UNKNOWN",
        feed="test", title="t", timestamp=None)
    disclaimer_probe = ei.get_ticker_events  # disclaimer text lives in the fn
    # Build a real (empty-feed) response to check the served disclaimer:
    with patch.object(ei, "_news_block", lambda t: {"status": "ok", "events": []}), \
         patch.object(ei, "_edgar_block", lambda t: {"status": "ok", "events": []}), \
         patch.object(ei, "_earnings_block", lambda t: {"status": "ok", "events": []}):
        out = ei.get_ticker_events("X")
    assert not ei._FORBIDDEN_RE.search(out["disclaimer"])
    assert sample["context"]["base_rate"]["status"] == "none_measured"
    _ = disclaimer_probe


# ── Router ────────────────────────────────────────────────────────


def test_router_ticker_endpoint():
    from backend.main import app
    client = TestClient(app)
    fake = {"ticker": "AAPL", "events": [], "feeds": {}, "unavailable_feeds": [],
            "generated_at": "t", "disclaimer": "d"}
    with patch("backend.services.event_intel.get_ticker_events",
               return_value=fake):
        resp = client.get("/api/event-intel/AAPL__nocache_test")
        assert resp.status_code == 422  # invalid ticker regex
        resp = client.get("/api/event-intel/AAPL")
    assert resp.status_code == 200
    assert "events" in resp.json()


def test_router_stats_endpoint():
    from backend.main import app
    client = TestClient(app)
    resp = client.get("/api/event-intel/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert "events_extracted" in body
    assert "feed_calls" in body


# ── Daily brief integration ───────────────────────────────────────


def test_brief_events_block_never_raises(monkeypatch):
    from backend.services import daily_brief as db

    def boom(_tickers):
        raise RuntimeError("nope")
    monkeypatch.setattr(ei, "get_events_for_brief", boom)
    block = db._events_block(["AAPL"])
    assert block["status"] == "unavailable"
    assert block["events"] == []


def test_brief_template_mentions_events(monkeypatch):
    from backend.services import daily_brief as db
    events = {
        "status": "ok",
        "events": [{"scope": "AAPL", "event_type": "earnings",
                    "direction": "positive", "direction_basis": "EXPLICIT",
                    "title": "Reported EPS beat estimates", "timestamp": "2026-07-28",
                    "tier": "HIGH", "url": None}],
        "n_events": 1, "n_directed": 1, "unavailable": {"MSFT": ["edgar_8k"]},
    }
    summary = db._template_summary([], {}, [], events)
    assert "1 structured events" in summary["impact_on_holdings"]
    assert "edgar_8k" in summary["impact_on_holdings"]


def test_geopolitical_block_reads_producer_keys(monkeypatch):
    """Regression: .score/.label silently served None for weeks."""
    from backend.services import daily_brief as db
    fake_news = {
        "gdelt": {"conflict_score": 0.4, "raw_data": {"conflict": [1, 2]}},
        "event_score": {"event_score": 0.7, "interpretation": "elevated"},
    }
    monkeypatch.setattr(db, "cache_peek", lambda *a, **k: (fake_news, 10.0))
    geo = db._geopolitical_block()
    assert geo["event_score"] == 0.7
    assert geo["event_label"] == "elevated"
    assert geo["conflict_score"] == 0.4
