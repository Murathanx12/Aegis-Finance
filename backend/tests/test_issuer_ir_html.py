"""Small synthetic fixture; authentic page is smoke-tested from private archive."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import pytest

from backend.services import news_registry
from backend.services.issuer_ir_html import IssuerPageRefused, parse_asml_release
from backend.services.issuer_ir_current_case import build_item
from backend.services import issuer_ir_current_case as current_case
from backend.services.issuer_ir_probability_v0 import ProbabilityRefused, preview
from scripts import news_pull


FIXTURE = Path(__file__).parent / "fixtures" / "news" / "asml_ir_synthetic.html"
SOURCE = "asml_ir_q3_2026"
EXPECTED_SHA = sha256(FIXTURE.read_bytes()).hexdigest()


class OfflineContext(news_pull.RunContext):
    def __init__(self, payload: bytes):
        super().__init__()
        self.payload = payload
        self.urls = []

    def http_get_issuer_exact(self, url: str) -> bytes:
        self.urls.append(url)
        return self.payload


def test_synthetic_fixture_parses_exact_registered_issuer_shape():
    raw = FIXTURE.read_bytes()
    source = news_registry.get(SOURCE)
    assert sha256(raw).hexdigest() == EXPECTED_SHA
    assert source.method == "html" and source.parser == "asml_issuer_html"
    assert source.manual_only and SOURCE not in [s.id for s in news_registry.pullable()]
    assert source.pit_grade == "first_seen_only" and not source.label_source
    item = parse_asml_release(raw, source.endpoint_or_feed)
    assert item["raw_sha256"] == EXPECTED_SHA
    assert item["published"] == datetime(2026, 10, 14, 5, 0, 31, tzinfo=timezone.utc)
    assert item["tickers"] == ["ASML"]
    assert "Q4 2026 total net sales" in item["body"]
    assert "ASML Holding" in item["body"]


def test_canonical_or_page_type_drift_refuses_instead_of_zero_rows():
    source = news_registry.get(SOURCE)
    raw = FIXTURE.read_bytes()
    for changed in (raw.replace(source.endpoint_or_feed.encode(), b"https://investor.asml.com/other", 1),
                    raw.replace(b'press_release_page', b'index_page', 1),
                    b'<html><body>no release</body></html>'):
        with pytest.raises(IssuerPageRefused):
            parse_asml_release(changed, source.endpoint_or_feed)
    with pytest.raises(IssuerPageRefused):
        parse_asml_release(raw, "https://www.sec.gov/Archives/not-an-issuer-release")


def test_offline_fetch_and_row_preserve_provenance_without_past_first_seen():
    raw = FIXTURE.read_bytes()
    source = news_registry.get(SOURCE)
    ctx = OfflineContext(raw)
    result = news_pull.fetch_asml_issuer_html(source, ctx)
    assert not result.refused and len(result.items) == 1
    assert ctx.urls == [source.endpoint_or_feed]
    held = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
    row = news_pull._row(source, result.items[0], held, tbl=None)
    assert row["first_seen_utc"] == "2026-10-14T12:00:00+00:00"
    assert row["published_utc"] == "2026-10-14T05:00:31+00:00"
    assert row["raw_sha256"] == EXPECTED_SHA
    assert row["source"] == SOURCE and row["tickers"] == ["ASML"]
    assert row["entity_tags"] == ["issuer:ASML"]


def test_missing_issuer_content_is_a_named_refusal():
    source = news_registry.get(SOURCE)
    result = news_pull.fetch_asml_issuer_html(source, OfflineContext(b'<html>empty</html>'))
    assert result.items == []
    assert result.refused.startswith("ASML_ISSUER_PAGE_REFUSED:")


def test_exact_origin_final_url_and_one_mib_read_bound(monkeypatch):
    source = news_registry.get(SOURCE)
    calls = []

    class Response:
        status = 200
        headers = {"Content-Type": "text/html; charset=UTF-8"}

        def __init__(self, final_url, payload):
            self.final_url, self.payload = final_url, payload

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def geturl(self):
            return self.final_url

        def read(self, n):
            calls.append(n)
            return self.payload[:n]

    class Opener:
        def __init__(self, response):
            self.response = response

        def open(self, *_args, **_kwargs):
            return self.response

    monkeypatch.setattr(news_pull.urllib.request, "build_opener", lambda *_: Opener(
        Response(source.endpoint_or_feed, FIXTURE.read_bytes())))
    assert news_pull._issuer_http_get_exact(source.endpoint_or_feed) == FIXTURE.read_bytes()
    assert calls == [1024 * 1024 + 1]
    with pytest.raises(IssuerPageRefused, match="issuer_request_origin_refused"):
        news_pull._issuer_http_get_exact("https://evil.example/release")
    monkeypatch.setattr(news_pull.urllib.request, "build_opener", lambda *_: Opener(
        Response("https://evil.example/release", FIXTURE.read_bytes())))
    with pytest.raises(IssuerPageRefused, match="issuer_final_url_drift"):
        news_pull._issuer_http_get_exact(source.endpoint_or_feed)
    monkeypatch.setattr(news_pull.urllib.request, "build_opener", lambda *_: Opener(
        Response(source.endpoint_or_feed, b"x" * (1024 * 1024 + 1))))
    with pytest.raises(IssuerPageRefused, match="issuer_page_over_one_mib"):
        news_pull._issuer_http_get_exact(source.endpoint_or_feed)
    assert max(calls) == 1024 * 1024 + 1


def test_redirect_handler_refuses_without_following():
    with pytest.raises(IssuerPageRefused, match="issuer_redirect_refused"):
        news_pull._IssuerNoRedirect().redirect_request(
            None, None, 302, "Moved", {}, "https://investor.asml.com/other")


def test_first_held_time_requires_pinned_receipt_not_forged_json(tmp_path, monkeypatch):
    source = news_registry.get(SOURCE)
    raw_path = tmp_path / "raw.html"
    raw_path.write_bytes(FIXTURE.read_bytes())
    acquisition = tmp_path / "acquisition.json"
    receipt = {
        "status": "CAPTURED_CANDIDATE_NOT_ADMITTED",
        "source_url": source.endpoint_or_feed, "final_url": source.endpoint_or_feed,
        "raw_sha256": EXPECTED_SHA, "raw_path": str(raw_path),
        "first_seen_utc": "2026-10-14T11:23:52.141587+00:00",
        "extraction_completed_utc": "2026-10-14T11:23:52.145587+00:00",
        "publication_metadata": [{"key": "sc:publication_date", "content": "2026-10-14T05:00:31Z"}],
    }
    receipt_bytes = json.dumps(receipt).encode()
    acquisition.write_bytes(receipt_bytes)
    monkeypatch.setattr(current_case, "RAW_SHA256", EXPECTED_SHA)
    monkeypatch.setattr(current_case, "RECEIPT_SHA256", sha256(receipt_bytes).hexdigest())
    item = build_item(acquisition)
    assert item.source == SOURCE and item.tickers_named == ["ASML"]
    assert item.first_seen_utc == receipt["first_seen_utc"]
    assert item.published_utc == "2026-10-14T05:00:31+00:00"
    assert item.text.startswith("ASML Holding presents a synthetic example")
    assert len(item.text) > 400
    receipt["first_seen_utc"] = "2026-10-14T04:00:00Z"
    acquisition.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(IssuerPageRefused, match="authentic_acquisition_receipt_drift"):
        build_item(acquisition)


def test_frozen_probability_preview_is_bounded_and_not_a_forecast_write():
    row = {"source": SOURCE, "event_type": "earnings", "tickers": ["ASML"],
           "tickers_unverified": [], "sentiment": 0.2,
           "forward_claims": [{"direction": "up", "subject": "sales"}]}
    assert preview(row)["p_symbol_beats_benchmark"] == 0.55
    assert preview(row)["status"] == "PREVIEW_ONLY_NO_FORECAST_AUTHORITY"
    row["sentiment"] = -0.2
    assert preview(row)["p_symbol_beats_benchmark"] == 0.45
    row["sentiment"] = 0
    assert preview(row)["p_symbol_beats_benchmark"] == 0.50
    row["tickers"] = ["ASML.AS"]
    with pytest.raises(ProbabilityRefused):
        preview(row)
