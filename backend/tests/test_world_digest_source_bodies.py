import json
from datetime import datetime, timedelta, timezone

from backend.services import world_digest as WD


def _collect(tmp_path, source, body):
    now = datetime(2026, 10, 14, 16, 30, tzinfo=timezone.utc)
    folder = tmp_path / "news_corpus" / source
    folder.mkdir(parents=True)
    row = {"source": source, "first_seen_utc": now.isoformat(),
           "published_utc": now.isoformat(), "url": "https://example.test/release",
           "title": "A substantive company earnings release", "body": body,
           "tickers": ["WINA"]}
    (folder / "2026-10-14.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    return WD.collect(now - timedelta(minutes=1), now, root=tmp_path)


def test_registered_full_body_reaches_article_interpretation(tmp_path):
    body = "Reported sales increased. " * 100 + "Material contrary evidence at the end."
    result = _collect(tmp_path, "sec_edgar_8k_ex99_body", body)
    item, = result["items"]
    assert item.kind == "article"
    assert item.text == body
    assert result["counts"]["article"] == 1
    assert item.tickers_named == ["WINA"]


def test_headline_feed_cannot_promote_a_long_description(tmp_path):
    item, = _collect(tmp_path, "google_news_rss_en_us", "description " * 100)["items"]
    assert item.kind == "headline"
    assert len(item.text) == 300


def test_short_registered_body_remains_a_headline(tmp_path):
    item, = _collect(tmp_path, "sec_edgar_8k_ex99_body", "Short summary.")["items"]
    assert item.kind == "headline"


def test_unknown_source_cannot_promote_a_long_description(tmp_path):
    item, = _collect(tmp_path, "unregistered_source", "description " * 100)["items"]
    assert item.kind == "headline"
