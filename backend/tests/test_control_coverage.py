"""N-F — `GET /api/control/coverage`. Every number derived from disk."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.routers import control


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    from backend import config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path, raising=False)
    return tmp_path / "optimus" / "news_corpus"


def _write(corpus, source, day, rows):
    d = corpus / source
    d.mkdir(parents=True, exist_ok=True)
    with (d / f"{day}.jsonl").open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _row(first_seen: datetime, source="google_news_rss_en_hk"):
    return {"source": source, "first_seen_utc": first_seen.isoformat(timespec="seconds"),
            "published_utc": "", "tz_source": "RFC 822", "url": "u", "title": "t",
            "body": "", "lang": "en", "tickers": [], "entity_tags": [],
            "raw_id": f"id-{first_seen.isoformat()}", "pit_grade": "index_state"}


def test_an_empty_corpus_reports_never_pulled_not_a_dash(corpus):
    out = control.coverage()
    assert out["available"] is True
    assert out["corpus_exists"] is False
    assert out["totals"]["rows_total"] == 0
    assert "google_news_rss_en_hk" in out["totals"]["never_pulled"]
    hk = next(s for s in out["sources"] if s["id"] == "google_news_rss_en_hk")
    assert hk["status"] == "NEVER_PULLED", "distinct from NO_ROWS and from RED"


def test_rows_today_and_the_seven_day_trend(corpus):
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    old = (now.date() - timedelta(days=3)).isoformat()
    _write(corpus, "google_news_rss_en_hk", today, [_row(now), _row(now - timedelta(minutes=5))])
    _write(corpus, "google_news_rss_en_hk", old, [_row(now - timedelta(days=3))])

    out = control.coverage()
    hk = next(s for s in out["sources"] if s["id"] == "google_news_rss_en_hk")
    assert hk["rows_total"] == 3
    assert hk["rows_today"] == 2
    assert len(hk["trend_7d"]) == control.COVERAGE_TREND_DAYS
    assert hk["trend_7d"][-1] == 2 and hk["trend_7d"][-4] == 1
    assert hk["status"] == "OK"
    assert hk["last_row_age_hours"] is not None and hk["last_row_age_hours"] < 1


def test_asia_first_is_a_number(corpus):
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    _write(corpus, "google_news_rss_en_hk", today, [_row(now)])
    _write(corpus, "google_news_rss_ja_jp", today, [_row(now, "google_news_rss_ja_jp")])
    _write(corpus, "google_news_rss_en_us", today, [_row(now, "google_news_rss_en_us")])

    out = control.coverage()
    assert out["asia_first"]["rows_total"] == 2, "the US row is not Asia"
    assert set(out["asia_first"]["regions"]) >= {"HK", "JP"}
    assert "floor, not a ceiling" in out["asia_first"]["note"]


def test_two_zero_runs_in_the_cursor_show_as_red(corpus):
    cur = corpus / "_cursors"
    cur.mkdir(parents=True, exist_ok=True)
    (cur / "nikkei_asia_rss.json").write_text(
        json.dumps({"source": "nikkei_asia_rss", "consecutive_zero_runs": 2, "runs": 4,
                    "last_run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}),
        encoding="utf-8")
    out = control.coverage()
    nik = next(s for s in out["sources"] if s["id"] == "nikkei_asia_rss")
    assert nik["status"] == "RED"
    assert "nikkei_asia_rss" in out["totals"]["red"]
    assert any("consecutive zero-row runs" in f for f in nik["flags"])


def test_a_stale_source_is_flagged_even_without_a_zero_run(corpus):
    """A feed that 500s every time never records a zero-row RUN."""
    old = datetime.now(timezone.utc) - timedelta(hours=control.COVERAGE_STALE_HOURS + 10)
    _write(corpus, "google_news_rss_en_sg", old.date().isoformat(),
           [_row(old, "google_news_rss_en_sg")])
    out = control.coverage()
    sg = next(s for s in out["sources"] if s["id"] == "google_news_rss_en_sg")
    assert sg["status"] == "STALE"


def test_a_refused_source_shows_its_named_refusal(corpus):
    rec = corpus / "_receipts"
    rec.mkdir(parents=True, exist_ok=True)
    (rec / "20260911T000000Z_alpaca_benzinga_news.json").write_text(
        json.dumps({"source": "alpaca_benzinga_news", "status": "REFUSED",
                    "failures": ["REFUSED: no credential resolved (looked for APCA_API_KEY_ID)"]}),
        encoding="utf-8")
    (corpus / "_cursors").mkdir(parents=True, exist_ok=True)
    (corpus / "_cursors" / "alpaca_benzinga_news.json").write_text(
        json.dumps({"consecutive_zero_runs": 0, "runs": 1}), encoding="utf-8")
    out = control.coverage()
    al = next(s for s in out["sources"] if s["id"] == "alpaca_benzinga_news")
    assert al["status"] == "REFUSED"
    assert "APCA_API_KEY_ID" in al["flags"][0]


def test_index_state_sources_are_marked_as_never_labelling(corpus):
    out = control.coverage()
    for s in out["sources"]:
        if s["pit_grade"] == "index_state":
            assert s["label_source"] is False
    assert "invariant 20" in out["rules"]["label_rule"]
    assert set(out["totals"]["label_sources"]) == {
        s["id"] for s in out["sources"] if s["label_source"]}


def test_regions_aggregate_and_name_their_problems(corpus):
    now = datetime.now(timezone.utc)
    _write(corpus, "google_news_rss_en_hk", now.date().isoformat(), [_row(now)])
    out = control.coverage()
    hk = next(r for r in out["regions"] if r["region"] == "HK")
    assert hk["rows_total"] == 1
    assert hk["sources"] >= 2, "HK carries the Google News leg and the deferred HKEX row"
    assert isinstance(hk["never_pulled"], list)


def test_the_endpoint_is_registered_on_the_router():
    paths = {r.path for r in control.router.routes}
    assert "/api/control/coverage" in paths


def test_an_unreadable_registry_degrades_to_a_report(corpus, monkeypatch):
    from backend.services import news_registry
    monkeypatch.setattr(news_registry, "load",
                        lambda *a, **k: (_ for _ in ()).throw(news_registry.RegistryError("boom")))
    out = control.coverage()
    assert out["available"] is False
    assert "boom" in out["error"]
    assert out["sources"] == []
