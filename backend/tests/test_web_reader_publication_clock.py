"""Publication instants from article text, with no browser or network calls."""

from backend.services import web_reader as WR


def test_yahoo_viewer_offset_precedes_issuer_date_only_dateline():
    article = ("ASML Netherlands BV\n"
               "Wed, 14 October 2026 at 1:00 pm GMT+8 9 min read\n"
               "VELDHOVEN, the Netherlands, October 14, 2026 - Today, ASML published results.")
    assert WR.parse_published(article) == "2026-10-14T05:00:00+00:00"


def test_yahoo_offsets_cross_utc_date_and_keep_minute_precision():
    assert WR.parse_published("Wed, 14 October 2026 at 12:15 am GMT+08:30") == (
        "2026-10-13T15:45:00+00:00")
    assert WR.parse_published("Wed, 14 October 2026 at 11:59 pm GMT-04:00") == (
        "2026-10-15T03:59:00+00:00")


def test_yahoo_invalid_or_conflicting_headers_fail_closed():
    dateline = "\nOctober 14, 2026"
    for header in ("Wed, 14 October 2026 at 1:00 pm GMT+25",
                   "Wed, 14 October 2026 at 1:00 pm GMT+8:60",
                   "Wed, 14 October 2026 at 13:00 pm GMT+8",
                   "Tue, 14 October 2026 at 1:00 pm GMT+8"):
        assert WR.parse_published(header + dateline) is None
    assert WR.parse_published(
        "Wed, 14 October 2026 at 1:00 pm GMT+8\n"
        "Wed, 14 October 2026 at 2:00 pm GMT+8" + dateline) is None


def test_dow_jones_eastern_daylight_and_standard_time():
    assert WR.parse_published("Published Oct 14, 2026, 1:00 p.m. ET") == (
        "2026-10-14T17:00:00+00:00")
    assert WR.parse_published("Published Jan 14, 2026, 1:00 p.m. ET") == (
        "2026-01-14T18:00:00+00:00")


def test_date_only_and_eastern_dst_transition_clocks_have_no_instant():
    assert WR.parse_published("October 14, 2026") is None
    assert WR.parse_published("Published Nov 1, 2026, 1:30 a.m. ET") is None
    assert WR.parse_published("Published Mar 8, 2026, 2:30 a.m. ET") is None


def test_date_only_age_bound_rejects_only_definitely_old_calendar_dates():
    from datetime import datetime, timezone

    cutoff = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
    assert not WR.definitely_old_date_only("Oct. 9, 2026", cutoff, 4)
    assert WR.definitely_old_date_only("Oct. 8, 2026", cutoff, 4)
    assert not WR.definitely_old_date_only("10/9/26", cutoff, 4)
    assert WR.definitely_old_date_only("10/8/26", cutoff, 4)
    assert not WR.definitely_old_date_only(
        "Company discussed October 8, 2026 results", cutoff, 4,
        article_header=True)


# Fixed historical regression inputs, not dates relative to the test clock.
# Reconstructed from the owner's excerpt; not a copied or rewritten corpus row.
DJ_HEAD = ("Democrats Romp, Flip Congress and Attempt to Flip the Script\n"
           "Subtitle referring to Jan. 6, 2021\nDamian Paletta\n")


def test_dj_historical_subtitle_before_explicit_publication_dateline():
    text = DJ_HEAD + "Nov. 4, 2026 1:32 am ET\nArticle body."
    assert WR.parse_published(text) == "2026-11-04T06:32:00+00:00"
    assert WR.parse_published(text.replace("Jan. 6, 2021", "Jan. 6, 2031")) == (
        "2026-11-04T06:32:00+00:00")


def test_dj_actual_archive_stays_old_and_writes_no_forecast(tmp_path):
    from backend.services import dowjones_claims as DC
    from backend.services import news_registry as NR

    article = {"url": "https://www.wsj.com/a", "text": DJ_HEAD,
               "first_seen_utc": "2026-11-04T12:00:00+00:00",
               "published_utc": WR.parse_published(DJ_HEAD + "Jan. 6, 2021 1:32 am ET"),
               "column": "wsj_other"}
    assert article["published_utc"] == "2021-01-06T06:32:00+00:00"
    assert NR.is_archive(article)
    result = DC.write_forecasts(article, [], ledger_path=tmp_path / "p.jsonl",
                                claims_path=tmp_path / "c.jsonl",
                                local_path=tmp_path / "local.jsonl")
    assert result["status"] == "ARCHIVE_NO_FORECAST"
    assert not (tmp_path / "p.jsonl").exists()


def test_dj_ambiguous_missing_and_malformed_dates_stay_unknown():
    for suffix in (
        "", "Nov. 4, 2026", "Nov. 4, 2026 1:32 am",
        "On Nov. 4, 2026 1:32 am ET the event occurred.",
        "Updated Nov. 4, 2026 1:32 am ET",
        "Nov. 4, 2026 1:32 am ET\nNov. 3, 2026 1:32 am ET",
        "Jan. 6, 2021\nNov. 4, 2026 1:32 am ET",
        "Nov. 4, 2026 1:32 am ET\nUpdated Nov. 4, 2026 2:32 am ET",
        "Nov. 4, 2026 13:32 am ET", "Nov. 31, 2026 1:32 am ET",
        "Nov. 4, 2026 1:32 am ET trailing text",
        "Nov. 4, 2026 1:32 am ET\nJan. 6, 2021 99:99 xm ET",
        "Nov. 4, 2026 1:32 am ET\nUpdated Jan. 6, 2021 1:32 am PT",
    ):
        assert WR.parse_published(DJ_HEAD + suffix) is None, suffix


def test_old_update_only_is_archive_bound_end_to_end(tmp_path, monkeypatch):
    from backend.services import dowjones_claims as DC
    from backend.services import news_registry as NR

    monkeypatch.setattr(DC, "local_claims_path", lambda day: (_ for _ in ()).throw(
        AssertionError("test must not use configured runtime storage")))

    seen = "2026-11-04T12:00:00+00:00"
    monkeypatch.setattr(DC, "now_iso", lambda: seen)
    claim = {"ticker": "MU", "direction": "up", "horizon_days_stated": 63,
             "magnitude_bucket": "unstated", "quote": "q", "paraphrase": "p"}
    for line in ("Updated Jan. 6, 2021 1:32 am ET",
                 "Updated Jan.6 2021 1:32 am ET"):
        class Driver:
            def read_text(self, tab, profile_name=None):
                return {"url": "https://www.wsj.com/a", "title": "A story - WSJ",
                        "text": DJ_HEAD + line + "\n" + "Article body. " * 25}

        reader = WR.Reader(profile="user", tab="t99", driver=Driver(), lock=False,
                           blank_after_read=False, scroll_steps=(0, 0),
                           throttle=WR.Throttle(tmp_path / "t.log"))
        article = reader.finish_article("https://www.wsj.com/a", store=False)
        assert article["first_seen_utc"] == seen
        assert article["published_utc"] == "2021-01-06T06:32:00+00:00"
        assert NR.is_archive(article)
        ledger = tmp_path / "p.jsonl"
        result = DC.write_forecasts(article, [claim], ledger_path=ledger,
                                    claims_path=tmp_path / "c.jsonl",
                                    local_path=tmp_path / "local.jsonl")
        assert result["status"] == "ARCHIVE_NO_FORECAST"
        assert result["n_rows_written"] == 0
        assert not ledger.exists()


def test_recent_update_only_is_not_positive_publication_proof():
    seen = "2026-11-04T12:00:00+00:00"
    assert WR.parse_published(DJ_HEAD + "Updated Nov. 4, 2026 1:32 am ET",
                              first_seen_utc=seen) is None
    assert WR.parse_published(DJ_HEAD + "Updated Oct. 10, 2026 1:32 am ET",
                              first_seen_utc=seen) is None
    assert WR.parse_published(DJ_HEAD + "Updated Jan. 6, 2021 1:32 am ET") is None
    assert WR.parse_published(DJ_HEAD + "Updated Jan. 6, 2021 1:32 am ET",
                              first_seen_utc="unknown") is None


def test_malformed_old_candidate_blocks_new_dateline_even_with_seen():
    text = DJ_HEAD + "Updated Jan. 6, 2021 99:99 xm ET\nNov. 4, 2026 1:32 am ET"
    assert WR.parse_published(text, first_seen_utc="2026-11-04T12:00:00+00:00") is None


def test_digest_body_and_header_use_ingest_clock_for_archive_bound(tmp_path, monkeypatch):
    import json

    from backend import config as C
    from backend.services import digest_inbox as DI
    from backend.services import dowjones_claims as DC
    from backend.services import news_registry as NR

    seen = "2026-11-04T12:00:00+00:00"
    old_update = "Updated Jan. 6, 2021 1:32 am ET"
    body = DJ_HEAD + old_update + "\n" + "Article body. " * 25
    header = f"https://www.wsj.com/b | {old_update} | WSJ"
    assert DI.parse_header(header).get("date") is None  # no ingest clock yet
    assert DI.parse_header(header, ingest_utc=seen)["date"] == "2021-01-06T06:32:00+00:00"
    assert DI.to_article({}, body, ingest_utc=seen)["published_utc"] == (
        "2021-01-06T06:32:00+00:00")
    assert DI.to_article({}, DJ_HEAD + "Updated Nov. 4, 2026 1:32 am ET",
                         ingest_utc=seen)["published_utc"] is None
    assert DI.to_article({}, DJ_HEAD + "Updated Jan. 6, 2021 99:99 xm ET\n"
                         "Nov. 4, 2026 1:32 am ET", ingest_utc=seen)["published_utc"] is None
    assert DI.parse_header(header.replace(old_update, "Updated Nov. 4, 2026 1:32 am ET"),
                           ingest_utc=seen).get("date") is None

    monkeypatch.setattr(C, "OPTIMUS_LEDGER_DIR", tmp_path / "ledger")
    inbox = tmp_path / "inbox"
    DI.ensure_inbox(inbox)
    pasted = (DI.DIGEST_HEADER + "=== https://www.wsj.com/a | WSJ\n" + body
              + "\n=== " + header + "\n" + DJ_HEAD + "Different body. " * 25)
    (inbox / "DIGEST.md").write_text(pasted, encoding="utf-8")
    root = tmp_path / "articles"
    receipt = DI.ingest(inbox, now_utc=seen, root=root)
    assert receipt["n_new"] == 2
    assert {row["pit_grade"] for row in receipt["entries"]} == {"archive"}
    articles = [json.loads(p.read_text(encoding="utf-8")) for p in root.glob("*/*/*.json")]
    assert len(articles) == 2
    assert {a["first_seen_utc"] for a in articles} == {seen}
    assert {a["published_utc"] for a in articles} == {"2021-01-06T06:32:00+00:00"}
    assert all(NR.is_archive(a) for a in articles)
    claim = {"ticker": "MU", "direction": "up", "horizon_days_stated": 63,
             "magnitude_bucket": "unstated", "quote": "q", "paraphrase": "p"}
    forecast_path = tmp_path / "forecast.jsonl"
    for article in articles:
        result = DC.write_forecasts(article, [claim], ledger_path=forecast_path,
                                    claims_path=tmp_path / "claims.jsonl",
                                    local_path=tmp_path / "local.jsonl")
        assert result["status"] == "ARCHIVE_NO_FORECAST"
        assert result["n_rows_written"] == 0
    assert not forecast_path.exists()


def test_dj_parse_has_no_clock_or_storage_side_effects(tmp_path, monkeypatch):
    import json
    from datetime import datetime

    class NoClock(datetime):
        @classmethod
        def now(cls, *args, **kwargs):
            raise AssertionError("publication must not use the current clock")

    monkeypatch.setattr(WR, "datetime", NoClock)
    monkeypatch.setattr(WR, "store_article", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("parsing must not store or rewrite articles")))
    saved = {"text": DJ_HEAD + "Nov. 4, 2026 1:32 am ET",
             "published_utc": None, "first_seen_utc": "2040-01-01T00:00:00+00:00"}
    corpus = tmp_path / "saved.jsonl"
    corpus.write_text(json.dumps(saved) + "\n", encoding="utf-8")
    before = corpus.read_bytes()
    assert WR.parse_published(saved["text"]) == "2026-11-04T06:32:00+00:00"
    assert WR.parse_published(DJ_HEAD) is None
    assert saved["published_utc"] is None
    assert corpus.read_bytes() == before
