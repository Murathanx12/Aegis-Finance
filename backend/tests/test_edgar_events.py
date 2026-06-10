"""Tests for SEC EDGAR event classification.

Network calls (CIK lookup, submissions fetch) are mocked so tests run
under -m "not slow" and stay deterministic offline.
"""

from __future__ import annotations

from unittest.mock import patch


from backend.services import edgar_events as ee


def test_classify_items_earnings():
    types, mat = ee.classify_items(["2.02", "9.01"])
    assert "earnings" in types
    # Item 9.01 (financial statements) should also be present
    assert "financial_statements" in types
    # Earnings is high materiality
    assert mat >= 0.85


def test_classify_items_high_materiality_bankruptcy():
    types, mat = ee.classify_items(["1.03"])
    assert "bankruptcy" in types
    assert mat >= 0.9


def test_classify_items_unknown():
    types, mat = ee.classify_items(["99.99"])
    assert types == []
    assert mat == 0.0


def test_parse_item_codes_strings():
    assert ee.parse_item_codes("5.02 — Officer departure, 9.01 Exhibits") == ["5.02", "9.01"]
    assert ee.parse_item_codes(None) == []
    assert ee.parse_item_codes(["2.02 Results of Ops", "9.01 Exhibits"]) == ["2.02", "9.01"]


def test_parse_item_codes_dedup():
    assert ee.parse_item_codes("5.02, 5.02") == ["5.02"]


def test_high_materiality_items_set():
    # Sanity: bankruptcy + management change + delisting + earnings must
    # be in the high-materiality set
    assert "1.03" in ee.HIGH_MATERIALITY_ITEMS
    assert "5.02" in ee.HIGH_MATERIALITY_ITEMS
    assert "3.01" in ee.HIGH_MATERIALITY_ITEMS
    assert "2.02" in ee.HIGH_MATERIALITY_ITEMS


def test_event_summary_empty():
    out = ee.event_summary([])
    assert out["count"] == 0


def test_event_summary_aggregates():
    events = [
        ee.EdgarEvent(
            ticker="AAPL", cik=320193, accession="0000-1",
            form="8-K", filed="2026-04-01",
            items=["2.02"], event_types=["earnings"], materiality=0.85,
            primary_doc_url="", is_8k=True,
        ),
        ee.EdgarEvent(
            ticker="AAPL", cik=320193, accession="0000-2",
            form="8-K", filed="2026-04-02",
            items=["1.03"], event_types=["bankruptcy"], materiality=0.95,
            primary_doc_url="", is_8k=True,
        ),
        ee.EdgarEvent(
            ticker="MSFT", cik=789019, accession="0000-3",
            form="8-K", filed="2026-04-03",
            items=["8.01"], event_types=["other_event"], materiality=0.40,
            primary_doc_url="", is_8k=True,
        ),
    ]
    s = ee.event_summary(events)
    assert s["count"] == 3
    assert s["high_materiality_count"] == 2  # earnings + bankruptcy
    assert s["by_ticker"]["AAPL"] == 2


def test_doc_url_format():
    url = ee._doc_url(320193, "0000320193-25-000001", "primary.htm")
    assert "Archives/edgar/data/320193/" in url
    assert "0000320193250000010" not in url  # not malformed


def test_lookup_cik_uses_cache_after_refresh():
    """Mock the CIK lookup payload and verify lookup returns the right CIK."""
    fake_payload = {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp."},
    }

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return fake_payload

    # Reset cache so we go through the refresh path
    ee._CIK_CACHE.clear()
    ee._CIK_CACHE_TS = None

    with patch.object(ee.requests, "get", return_value=FakeResp()):
        assert ee.lookup_cik("aapl") == 320193
        assert ee.lookup_cik("MSFT") == 789019
        assert ee.lookup_cik("NOTLISTED") is None


def test_fetch_events_for_ticker_filters_by_days(monkeypatch):
    """Mock submissions API and verify the days_back cutoff is enforced."""
    from datetime import datetime, timedelta, timezone

    today = datetime.now(timezone.utc).date()
    fake_sub = {
        "filings": {
            "recent": {
                "form": ["8-K", "8-K", "10-Q"],
                "accessionNumber": ["a-1", "a-2", "a-3"],
                "filingDate": [
                    today.isoformat(),
                    (today - timedelta(days=200)).isoformat(),
                    today.isoformat(),
                ],
                "items": ["2.02 Results", "5.02 Officer", ""],
                "primaryDocument": ["doc1.htm", "doc2.htm", "doc3.htm"],
            }
        }
    }

    monkeypatch.setattr(ee, "lookup_cik", lambda t: 320193)
    monkeypatch.setattr(ee, "_fetch_submissions", lambda cik: fake_sub)

    events = ee.fetch_events_for_ticker("AAPL", days_back=30)
    # Recent earnings 8-K should be included; 200-day-old 8-K excluded;
    # 10-Q excluded by only_8k=True
    assert len(events) == 1
    assert events[0].items == ["2.02"]
    assert "earnings" in events[0].event_types


def test_fetch_events_high_materiality_filter(monkeypatch):
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).date()
    fake_sub = {
        "filings": {
            "recent": {
                "form": ["8-K", "8-K"],
                "accessionNumber": ["a-1", "a-2"],
                "filingDate": [today.isoformat(), today.isoformat()],
                "items": ["8.01 Other Events", "1.03 Bankruptcy"],
                "primaryDocument": ["d1.htm", "d2.htm"],
            }
        }
    }
    monkeypatch.setattr(ee, "lookup_cik", lambda t: 320193)
    monkeypatch.setattr(ee, "_fetch_submissions", lambda cik: fake_sub)

    events = ee.fetch_events_for_ticker(
        "AAPL", days_back=30, high_materiality_only=True
    )
    assert len(events) == 1
    assert events[0].items == ["1.03"]
