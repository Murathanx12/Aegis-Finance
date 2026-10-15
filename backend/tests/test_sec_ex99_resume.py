"""Restart and archive-transaction regressions for the rolling SEC feed."""
from datetime import timedelta

import pytest

from scripts import news_pull as n

SOURCE = "sec_edgar_8k_ex99_body"


def entry(acc):
    return {"url": f"https://www.sec.gov/Archives/edgar/data/1/{acc}/{acc}-index.htm",
            "title": acc, "entity_tags": ["8-K:2.02"]}


def index(*names):
    return "".join(f"<DOCUMENT>\n<TYPE>EX-99.1\n<FILENAME>{name}\n</DOCUMENT>" for name in names).encode()


class Context(n.RunContext):
    def __init__(self, payload, **kw):
        super().__init__(resume=True, paced=False, **kw)
        self.payload = payload
        self.urls = []

    def http_get_via(self, src, url, headers=None):
        self.urls.append(url)
        value = self.payload.get(url.rsplit("/", 1)[-1], b"feed")
        if isinstance(value, Exception):
            raise value
        return value


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    monkeypatch.setattr(n._config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(n.entities, "tables", lambda: None)
    monkeypatch.setattr(n.entities, "resolve", lambda *a, **k: type("R", (), {"tickers": (), "how": {}})())
    return tmp_path


def test_partial_filing_survives_feed_shift_and_does_not_refetch_accepted_body(corpus, monkeypatch):
    monkeypatch.setattr(n, "parse_edgar_atom", lambda raw: [entry("a")])
    first = n.pull_source(SOURCE, Context({"a-index-headers.html": index("one.htm", "two.htm"),
                                         "one.htm": b"<p>first</p>", "two.htm": n.FetchError("503")}))
    assert first["new"] == 1
    assert first["sec_progress"]["pending_filings"] == 1
    assert "a" not in n._read_cursor(SOURCE)["sec_completed"]
    monkeypatch.setattr(n, "parse_edgar_atom", lambda raw: [entry("b")])
    ctx = Context({"a-index-headers.html": index("one.htm", "two.htm"), "two.htm": b"<p>second</p>",
                   "b-index-headers.html": index("b.htm"), "b.htm": b"<p>new filing</p>"})
    second = n.pull_source(SOURCE, ctx)
    assert second["new"] == 2
    assert not any(url.endswith("/one.htm") for url in ctx.urls)
    assert set(n._read_cursor(SOURCE)["sec_completed"]) == {"a", "b"}
    assert second["sec_progress"]["pending_filings"] == 0


def test_duplicate_before_cursor_commit_advances_and_restart_skips_index(corpus, monkeypatch):
    monkeypatch.setattr(n, "parse_edgar_atom", lambda raw: [entry("a")])
    ctx = Context({"a-index-headers.html": index("one.htm"), "one.htm": b"body"})
    n.pull_source(SOURCE, ctx)
    n.cursor_path(SOURCE).unlink()  # crash between durable archive and cursor replacement
    rec = n.pull_source(SOURCE, ctx)
    assert rec["new"] == 0
    assert rec["sec_progress"]["completed_filings"] == 1
    again = Context({})
    n.pull_source(SOURCE, again)
    assert len(again.urls) == 1  # feed only, no repeated prefix requests


def test_archive_older_than_dedupe_window_is_verified_not_reacquired(corpus, monkeypatch):
    monkeypatch.setattr(n, "parse_edgar_atom", lambda raw: [entry("a")])
    n.pull_source(SOURCE, Context({"a-index-headers.html": index("one.htm"), "one.htm": b"body"}))
    day = next(n.source_dir(SOURCE).glob("*.jsonl"))
    day.rename(day.with_name((n._now().date() - timedelta(days=30)).isoformat() + ".jsonl"))
    ctx = Context({})
    n.pull_source(SOURCE, ctx)
    assert len(ctx.urls) == 1


def test_failed_archive_write_never_commits_completion(corpus, monkeypatch):
    monkeypatch.setattr(n, "parse_edgar_atom", lambda raw: [entry("a")])
    monkeypatch.setattr(n.os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError, match="disk"):
        n.pull_source(SOURCE, Context({"a-index-headers.html": index("one.htm"), "one.htm": b"body"}))
    assert not n.cursor_path(SOURCE).exists()  # even pending checkpoint failed fsync


def test_row_cap_cannot_complete_unwritten_second_exhibit(corpus, monkeypatch):
    monkeypatch.setattr(n, "parse_edgar_atom", lambda raw: [entry("a")])
    rec = n.pull_source(SOURCE, Context({"a-index-headers.html": index("one.htm", "two.htm"),
                                        "one.htm": b"one", "two.htm": b"two"}, max_rows=1))
    assert rec["new"] == 1
    assert rec["sec_progress"]["pending_filings"] == 1
    assert n._read_cursor(SOURCE)["sec_completed"] == {}


def test_empty_index_is_not_completed_work(corpus, monkeypatch):
    monkeypatch.setattr(n, "parse_edgar_atom", lambda raw: [entry("a")])
    rec = n.pull_source(SOURCE, Context({"a-index-headers.html": b"<html>no index</html>"}))
    assert rec["sec_progress"]["pending_filings"] == 1
    assert any("empty filing document index" in f for f in rec["failures"])


def test_feed_failure_and_nonresume_caller_preserve_unfinished_work(corpus, monkeypatch):
    monkeypatch.setattr(n, "parse_edgar_atom", lambda raw: [entry("a")])
    n.pull_source(SOURCE, Context({"a-index-headers.html": index("one.htm"),
                                  "one.htm": n.FetchError("503")}))
    pending = n._read_cursor(SOURCE)["sec_pending"]
    ctx = Context({})
    ctx.resume = False
    ctx.http_get_via = lambda *a, **k: (_ for _ in ()).throw(n.FetchError("feed unavailable"))
    n.pull_source(SOURCE, ctx)
    assert n._read_cursor(SOURCE)["sec_pending"] == pending
    monkeypatch.setattr(n, "parse_edgar_atom", lambda raw: [])
    resumed = Context({"a-index-headers.html": index("one.htm"), "one.htm": b"saved after restart"})
    resumed.resume = False
    assert n.pull_source(SOURCE, resumed)["new"] == 1


def test_crash_after_archive_before_cursor_and_shifted_feed_keeps_other_exhibit(corpus, monkeypatch):
    monkeypatch.setattr(n, "parse_edgar_atom", lambda raw: [entry("a")])
    original = n._write_cursor
    calls = []
    def crash_second_write(source, cur):
        calls.append(cur)
        if len(calls) == 2:
            raise OSError("crash before completion commit")
        original(source, cur)
    monkeypatch.setattr(n, "_write_cursor", crash_second_write)
    with pytest.raises(OSError, match="crash"):
        n.pull_source(SOURCE, Context({"a-index-headers.html": index("one.htm", "two.htm"),
                                      "one.htm": b"one", "two.htm": n.FetchError("503")}))
    monkeypatch.setattr(n, "_write_cursor", original)
    monkeypatch.setattr(n, "parse_edgar_atom", lambda raw: [])
    rec = n.pull_source(SOURCE, Context({"a-index-headers.html": index("one.htm", "two.htm"), "two.htm": b"two"}))
    assert rec["new"] == 1
    assert rec["sec_progress"]["completed_filings"] == 1


def test_nonempty_truncated_index_cannot_commit_empty_completion(corpus, monkeypatch):
    monkeypatch.setattr(n, "parse_edgar_atom", lambda raw: [entry("a")])
    truncated = b"<DOCUMENT>\n<TYPE>8-K\n<FILENAME>main.htm\n</DOCUMENT>"
    n.pull_source(SOURCE, Context({"a-index-headers.html": truncated}))
    assert n._read_cursor(SOURCE)["sec_pending"] == [entry("a")]
    assert n._read_cursor(SOURCE)["sec_completed"] == {}


def test_live_feed_with_completed_archive_is_not_dead_but_empty_feed_still_is(corpus, monkeypatch):
    monkeypatch.setattr(n, "parse_edgar_atom", lambda raw: [entry("a")])
    n.pull_source(SOURCE, Context({"a-index-headers.html": index("one.htm"), "one.htm": b"one"}))
    cursor = n._read_cursor(SOURCE)
    cursor["consecutive_zero_runs"] = 1
    n._write_cursor(SOURCE, cursor)
    rec = n.pull_source(SOURCE, Context({}))
    assert rec["received"] == 0
    assert rec["consecutive_zero_runs"] == 0
    assert rec["sec_progress"]["feed_entries"] == 1
    monkeypatch.setattr(n, "parse_edgar_atom", lambda raw: [])
    n.pull_source(SOURCE, Context({}))
    rec = n.pull_source(SOURCE, Context({}))
    assert rec["status"] == "RED"
    assert rec["sec_progress"]["feed_entries"] == 0
