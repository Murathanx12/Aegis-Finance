"""Chunk 20 T1 — the stealthy fetcher adapter, the registry option, EDGAR's Ex-99 body.

Offline throughout. The adapter's real entry point (`StealthyFetcher.fetch`)
drives a browser, so every test here injects a callable instead — the same seam
`hiring_pull._fetch` and `RunContext.http_get` already have. Nothing in this
file needs the `[fetchers]` extra, a browser binary, or a socket.

What is pinned, and each is a way this could run green and be wrong:

  1. the adapter is BOXED — a fetcher that never returns is abandoned at the
     wall clock, not waited on (the Yahoo five-minute socket and the Alpaca
     two-hour handshake are the two receipts for why);
  2. an import failure REFUSES BY NAME, and the two import failures are
     different names: the library absent vs the `[fetchers]` extra absent;
  3. ONE retry is the maximum, and a call whose deadline is spent does not
     start a second attempt;
  4. a refusal never carries a status code (that would read as a page);
  5. the registry accepts `fetcher: scrapling`, defaults to `plain` when the
     field is absent, and REFUSES an unrecognised value rather than falling
     back — a typo that fell through to the default would silently keep the
     door the editor was trying to change;
  6. a fake fetcher drives the whole registry path and the rows it writes carry
     `fetcher` in the row, not only in the receipt;
  7. EDGAR's exhibit types are read from the HTML-ESCAPED SGML header, because
     `index.json`'s `type` is a GIF ICON NAME — both facts came from the
     2026-09-19 probe and either one silently returns "no Exhibit 99, ever".
"""

from __future__ import annotations

import json
import sys
import textwrap
import time

import pytest

from backend.services import fetch_scrapling as FS
from backend.services import news_registry as reg
from scripts import news_pull as np_


# --------------------------------------------------------------------------
# a stand-in for Scrapling's Response


class FakePage:
    def __init__(self, status=200, html="<html><body>hello world</body></html>",
                 url="https://example.invalid/final", text=None, encoding="utf-8"):
        self.status = status
        self.html_content = html
        self.url = url
        self.encoding = encoding
        self._text = text

    def get_all_text(self):
        if self._text is None:
            raise RuntimeError("no text extractor here")
        return self._text


def _ok_fetcher(page=None, calls=None):
    def fetch(url, **kw):
        if calls is not None:
            calls.append((url, kw))
        return page or FakePage()
    return fetch


# --------------------------------------------------------------------------
# the adapter


def test_a_successful_fetch_returns_the_flat_contract():
    calls: list = []
    res = FS.fetch("https://example.invalid/p", budget_s=5.0,
                   fetcher=_ok_fetcher(FakePage(text="hello world"), calls))
    assert res["refused"] == ""
    assert res["status"] == 200
    assert res["fetcher"] == FS.FETCHER_NAME
    assert res["final_url"] == "https://example.invalid/final"
    assert "hello world" in res["html"]
    assert res["text"] == "hello world"
    assert res["attempts"] == 1
    assert isinstance(res["elapsed_s"], float)
    # Scrapling's own timeout is a HINT in milliseconds; it is passed, and it
    # is not what ends the call.
    assert calls[0][1]["timeout"] > 100


def test_text_falls_back_when_the_extractor_raises():
    """An adapter that raises while reading a SUCCESSFUL reply reports failure
    for pages it actually got."""
    res = FS.fetch("https://example.invalid/p", budget_s=5.0,
                   fetcher=_ok_fetcher(FakePage()))
    assert res["refused"] == ""
    assert res["status"] == 200
    assert res["text"] == ""


def test_an_empty_url_refuses_by_name():
    res = FS.fetch("", budget_s=5.0, fetcher=_ok_fetcher())
    assert res["refused"] == "SCRAPLING_NO_URL"
    assert res["status"] is None


def test_the_wall_clock_box_abandons_a_fetcher_that_never_returns():
    def wedged(url, **kw):
        time.sleep(30)
        return FakePage()

    t0 = time.monotonic()
    res = FS.fetch("https://example.invalid/p", budget_s=1.0, fetcher=wedged)
    spent = time.monotonic() - t0
    assert res["refused"] == "SCRAPLING_TIMEOUT"
    assert res["status"] is None, "a refusal must never carry a plausible status"
    assert spent < 10, f"the box did not bind: {spent:.1f}s"


def test_one_retry_is_the_maximum():
    calls: list = []

    def boom(url, **kw):
        calls.append(url)
        raise RuntimeError("blocked")

    res = FS.fetch("https://example.invalid/p", budget_s=30.0, fetcher=boom)
    assert res["refused"] == "SCRAPLING_FETCH_FAILED"
    assert len(calls) == FS.MAX_ATTEMPTS == 2
    assert res["attempts"] == 2
    assert "one retry is the maximum" in res["detail"]


def test_the_retry_is_not_attempted_without_budget_for_it():
    calls: list = []

    def slow_boom(url, **kw):
        calls.append(url)
        time.sleep(0.4)
        raise RuntimeError("blocked")

    res = FS.fetch("https://example.invalid/p",
                   budget_s=FS.MIN_RETRY_BUDGET_S * 0.1, fetcher=slow_boom)
    assert res["refused"] == "SCRAPLING_FETCH_FAILED"
    assert len(calls) == 1


def test_a_second_attempt_can_succeed():
    seen: list = []

    def flaky(url, **kw):
        seen.append(url)
        if len(seen) == 1:
            raise RuntimeError("blocked once")
        return FakePage(text="second time")

    res = FS.fetch("https://example.invalid/p", budget_s=30.0, fetcher=flaky)
    assert res["refused"] == ""
    assert res["attempts"] == 2
    assert res["text"] == "second time"


def test_a_403_is_a_status_and_not_a_refusal():
    """The adapter reports what the site said. Turning a 403 into a refusal
    would hide the one signal that says the stealth layer did not work."""
    res = FS.fetch("https://example.invalid/p", budget_s=5.0,
                   fetcher=_ok_fetcher(FakePage(status=403, html="denied")))
    assert res["refused"] == ""
    assert res["status"] == 403


def test_cp1252_bytes_are_decoded_rather_than_replaced():
    """EDGAR exhibits are frequently cp1252 with no charset. `errors=replace`
    on UTF-8 mangles exactly the characters a quotation lands on."""
    body = b"the Company\x92s operations"          # 0x92 = cp1252 right quote
    assert body.decode("utf-8", "replace") != "the Company’s operations"
    assert FS._decode(body) == "the Company’s operations"


# --------------------------------------------------------------------------
# the two import refusals


def test_the_library_being_absent_refuses_by_name(monkeypatch):
    monkeypatch.setitem(sys.modules, "scrapling", None)
    fn, refusal, detail = FS.resolve_fetcher()
    assert fn is None
    assert refusal == "SCRAPLING_NOT_INSTALLED"
    res = FS.fetch("https://example.invalid/p")
    assert res["refused"] == "SCRAPLING_NOT_INSTALLED"
    assert res["status"] is None


def test_the_fetchers_extra_being_absent_is_its_own_name(monkeypatch):
    pytest.importorskip("scrapling")
    monkeypatch.setitem(sys.modules, "scrapling.fetchers", None)
    fn, refusal, detail = FS.resolve_fetcher()
    assert fn is None
    assert refusal == "SCRAPLING_FETCHERS_NOT_INSTALLED"
    assert "scrapling[fetchers]" in detail


def test_every_refusal_this_adapter_can_return_is_declared():
    """A caller matches on these strings; one that is not declared is a string
    nobody can be asked to handle."""
    assert set(FS.REFUSALS) == {
        "SCRAPLING_NOT_INSTALLED", "SCRAPLING_FETCHERS_NOT_INSTALLED",
        "SCRAPLING_NO_URL", "SCRAPLING_TIMEOUT", "SCRAPLING_FETCH_FAILED"}
    d = FS.declaration()
    assert d["fetcher"] == "scrapling"
    assert d["max_attempts"] == 2
    assert "availability" in d


# --------------------------------------------------------------------------
# the registry option


_ROW = """
    version: "t"
    licence: PRODUCT_EXPERIMENT
    sources:
      - id: t_stealth
        provider: T
        region: US
        language: en
        tier: 2
        licence: free
        method: rss
        parser: rss2
        fetcher: scrapling
        endpoint_or_feed: "https://example.invalid/feed"
        auth: none
        rate_limit: none
        min_interval_s: 0.0
        pit_grade: index_state
        stamp_field: pubDate
        stamp_tz: RFC822
        ticker_tags: false
        body_available: false
        label_source: false
        implemented: true
        implemented_note: ""
        notes: ok
    """


def _write(tmp_path, body: str):
    p = tmp_path / "news_sources.yaml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_a_row_may_name_the_scrapling_fetcher(tmp_path):
    src = reg.load(_write(tmp_path, _ROW))[0]
    assert src.fetcher == "scrapling"


def test_a_row_without_the_field_means_plain(tmp_path):
    src = reg.load(_write(tmp_path, _ROW.replace("        fetcher: scrapling\n", "")))[0]
    assert src.fetcher == reg.DEFAULT_FETCHER == "plain"


def test_an_unrecognised_fetcher_refuses_the_file(tmp_path):
    p = _write(tmp_path, _ROW.replace("fetcher: scrapling", "fetcher: scrapeling"))
    with pytest.raises(reg.RegistryError, match="fetcher"):
        reg.load(p)


def test_the_shipped_registry_still_loads_and_every_row_names_a_known_door():
    for s in reg.load():
        assert s.fetcher in reg.VALID_FETCHERS, f"{s.id}: {s.fetcher}"


# --------------------------------------------------------------------------
# a fake fetcher drives the registry path


@pytest.fixture
def stealth_registry(tmp_path, monkeypatch):
    """A one-row registry whose source declares `fetcher: scrapling`."""
    data = tmp_path / "backend" / "data"
    data.mkdir(parents=True)
    (data / "news_sources.yaml").write_text(textwrap.dedent(_ROW), encoding="utf-8")
    monkeypatch.setattr(reg._config, "BACKEND_DIR", tmp_path / "backend", raising=False)
    monkeypatch.setattr(np_._config, "DATA_DIR", tmp_path, raising=False)
    reg.load(refresh=True)
    return tmp_path / "optimus" / "news_corpus"


class StealthCtx(np_.RunContext):
    """A context whose STEALTHY door returns a canned adapter result."""

    def __init__(self, result: dict, **kw):
        super().__init__(**kw)
        self.result = result
        self.plain_calls: list[str] = []
        self.stealth_calls: list[str] = []

    def http_get(self, url: str, headers: dict | None = None) -> bytes:
        self.plain_calls.append(url)
        raise AssertionError("a scrapling row must not reach the plain door")

    def scrapling_fetch(self, url: str, *, budget_s: float) -> dict:
        self.stealth_calls.append(url)
        return dict(self.result)


_FEED = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Acme Corp raises guidance</title><link>https://example.invalid/a</link>
<guid>a-1</guid><pubDate>Thu, 11 Sep 2026 09:00:00 GMT</pubDate>
<description>Acme Corp said today</description></item>
</channel></rss>"""


def test_a_scrapling_row_is_pulled_through_the_adapter(stealth_registry):
    ctx = StealthCtx({"fetcher": "scrapling", "status": 200,
                      "html": _FEED.decode(), "text": "", "final_url": "",
                      "refused": "", "detail": "", "elapsed_s": 0.1,
                      "attempts": 1}, paced=False)
    rec = np_.pull_source("t_stealth", ctx)
    assert rec["status"] == "OK", rec["failures"]
    assert rec["new"] == 1
    assert rec["fetcher"] == "scrapling"
    assert ctx.stealth_calls == ["https://example.invalid/feed"]
    assert ctx.plain_calls == []
    day = next(iter((stealth_registry / "t_stealth").glob("*.jsonl")))
    row = json.loads(day.read_text(encoding="utf-8").splitlines()[0])
    assert set(row) == set(np_.ROW_KEYS), "the row schema drifted"
    assert row["fetcher"] == "scrapling", "the door belongs in the ROW, not only the receipt"


def test_an_adapter_refusal_becomes_a_named_failure_not_a_crash(stealth_registry):
    ctx = StealthCtx({"fetcher": "scrapling", "status": None, "html": "",
                      "text": "", "final_url": "",
                      "refused": "SCRAPLING_FETCHERS_NOT_INSTALLED",
                      "detail": "no extra", "elapsed_s": 0.0, "attempts": 0},
                     paced=False)
    rec = np_.pull_source("t_stealth", ctx)
    assert rec["new"] == 0
    assert any("SCRAPLING_FETCHERS_NOT_INSTALLED" in f for f in rec["failures"])


def test_a_403_through_the_stealth_door_is_a_named_failure(stealth_registry):
    ctx = StealthCtx({"fetcher": "scrapling", "status": 403, "html": "denied",
                      "text": "", "final_url": "", "refused": "", "detail": "",
                      "elapsed_s": 0.0, "attempts": 1}, paced=False)
    rec = np_.pull_source("t_stealth", ctx)
    assert rec["new"] == 0
    assert any("HTTP 403" in f for f in rec["failures"])


# --------------------------------------------------------------------------
# SEC 8-K Exhibit 99, the body the feed row does not have


#: The 2026-09-19 probe's real shape, trimmed: the SGML header arrives
#: HTML-ESCAPED inside an HTML page.
_INDEX_HEADERS = b"""<html><body><pre>
&lt;DOCUMENT&gt;
&lt;TYPE&gt;8-K
&lt;SEQUENCE&gt;1
&lt;FILENAME&gt;cacc-20260917.htm
&lt;DESCRIPTION&gt;8-K
&lt;/DOCUMENT&gt;
&lt;DOCUMENT&gt;
&lt;TYPE&gt;EX-10.1
&lt;SEQUENCE&gt;2
&lt;FILENAME&gt;cacc_8k20260917cj.htm
&lt;DESCRIPTION&gt;EX-10.1
&lt;/DOCUMENT&gt;
&lt;DOCUMENT&gt;
&lt;TYPE&gt;EX-99.1
&lt;SEQUENCE&gt;3
&lt;FILENAME&gt;cacc_8k20260917pr.htm
&lt;DESCRIPTION&gt;EX-99.1
&lt;/DOCUMENT&gt;
</pre></body></html>"""

_EX99_BODY = (b"<html><body><p>Exhibit 99.1</p><p>ACME REACHES RESOLUTION</p>"
              b"<p>Southfield, Michigan \x96 September 17, 2026</p></body></html>")

_EDGAR_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
 <entry>
  <title>8-K - CREDIT ACCEPTANCE CORP (0000885550) (Filer)</title>
  <link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/885550/000088555026000192/0000885550-26-000192-index.htm"/>
  <summary type="html">&lt;b&gt;Filed:&lt;/b&gt; 2026-09-18 &lt;b&gt;AccNo:&lt;/b&gt; 0000885550-26-000192 &lt;b&gt;Item 7.01:&lt;/b&gt; Regulation FD</summary>
  <updated>2026-09-18T16:31:00-04:00</updated>
 </entry>
 <entry>
  <title>8-K - BORING CO (0000111111) (Filer)</title>
  <link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/111111/000011111126000001/0000111111-26-000001-index.htm"/>
  <summary type="html">&lt;b&gt;Filed:&lt;/b&gt; 2026-09-18 &lt;b&gt;AccNo:&lt;/b&gt; 0000111111-26-000001 &lt;b&gt;Item 5.02:&lt;/b&gt; Departure of Directors</summary>
  <updated>2026-09-18T16:32:00-04:00</updated>
 </entry>
</feed>""".encode()


def test_the_exhibit_types_are_read_from_the_escaped_sgml_header():
    docs = np_.parse_filing_documents(_INDEX_HEADERS)
    assert [d["type"] for d in docs] == ["8-K", "EX-10.1", "EX-99.1"]
    ex = np_.exhibit_99_documents(docs)
    assert len(ex) == 1
    assert ex[0]["filename"] == "cacc_8k20260917pr.htm"


def test_a_filing_with_no_exhibit_99_is_an_answer_not_a_parse_failure():
    docs = np_.parse_filing_documents(
        _INDEX_HEADERS.replace(b"EX-99.1", b"EX-10.2"))
    assert docs, "the header still parsed"
    assert np_.exhibit_99_documents(docs) == []


def test_the_ex99_fetch_costs_exactly_two_calls_per_qualifying_filing(tmp_path,
                                                                     monkeypatch):
    monkeypatch.setattr(np_._config, "DATA_DIR", tmp_path, raising=False)
    routes = {
        "action=getcurrent": _EDGAR_FEED,
        "index-headers.html": _INDEX_HEADERS,
        "cacc_8k20260917pr.htm": _EX99_BODY,
    }
    seen: list[str] = []

    class Ctx(np_.RunContext):
        def http_get(self, url, headers=None):
            seen.append(url)
            for frag, payload in routes.items():
                if frag in url:
                    return payload
            raise np_.FetchError(f"no stub for {url}")

    rec = np_.pull_source("sec_edgar_8k_ex99_body", Ctx(paced=False))
    assert rec["status"] == "OK", rec["failures"]
    assert rec["new"] == 1, "only the Item 7.01 filing qualifies"
    # one feed call + two per qualifying filing. The second entry names Item
    # 5.02 only and must never be opened.
    assert len(seen) == 1 + np_.EX99_REQUESTS_PER_FILING
    assert not any("000011111126000001" in u for u in seen)

    day = next(iter((tmp_path / "optimus" / "news_corpus"
                     / "sec_edgar_8k_ex99_body").glob("*.jsonl")))
    row = json.loads(day.read_text(encoding="utf-8").splitlines()[0])
    assert "ACME REACHES RESOLUTION" in row["body"]
    assert "– September 17, 2026" in row["body"], "cp1252 en dash survived"
    assert row["raw_id"] == "0000885550-26-000192:cacc_8k20260917pr.htm", \
        "the raw_id must not collide with the FEED source's accession"
    assert "exhibit:EX-99.1" in row["entity_tags"]
    assert row["fetcher"] == "plain", "SEC gets the plain door on purpose"


def test_the_shipped_ex99_row_uses_the_plain_door_and_may_label():
    """SEC requires a descriptive contact User-Agent; spoofing a browser
    fingerprint at a fair-access government endpoint buys nothing."""
    s = reg.get("sec_edgar_8k_ex99_body")
    assert s.fetcher == "plain"
    assert s.parser == "edgar_ex99"
    assert s.pit_grade == "native_stamp" and s.label_source is True
    assert s.body_available is True
    assert "getcurrent" in s.endpoint_or_feed
