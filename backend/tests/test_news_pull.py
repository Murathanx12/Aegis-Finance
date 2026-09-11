"""N-A — the corpus writer: schema, dedupe, cursor, the RED rule, every parser.

Offline throughout. `RunContext` exists precisely so that every external effect
(HTTP, yfinance, the Alpaca credential) is a method a test can replace, so no
test here needs a socket, a key or a clock.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.services import news_registry as registry
from scripts import news_pull as np_

FIXTURES = Path(__file__).parent / "fixtures" / "news"


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    """Point the CORPUS at tmp_path. The registry and name tables stay real."""
    monkeypatch.setattr(np_._config, "DATA_DIR", tmp_path, raising=False)
    return tmp_path / "optimus" / "news_corpus"


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class StubCtx(np_.RunContext):
    """A context whose HTTP door returns a canned payload."""

    def __init__(self, payload: bytes | dict[str, bytes] = b"", **kw):
        super().__init__(**kw)
        self.payload = payload
        self.urls: list[str] = []
        self.headers: list[dict] = []

    def http_get(self, url: str, headers: dict | None = None) -> bytes:
        self.urls.append(url)
        self.headers.append(headers or {})
        if isinstance(self.payload, dict):
            for key, val in self.payload.items():
                if key in url:
                    return val
            raise np_.FetchError(f"no stub for {url}")
        return self.payload


# --------------------------------------------------------------- the parsers


def test_rss2_parser():
    items = np_.parse_rss2(fixture_bytes("google_news_rss_en_hk.xml"))
    assert len(items) == 3
    assert items[0]["title"].startswith("Empty seats")
    assert items[0]["published"].isoformat().startswith("2026-09-11T09:00:00")
    assert items[0]["raw_id"], "RSS 2.0 dedupe key is the guid, falling back to the link"


def test_rss1_rdf_parser_finds_what_a_naive_parser_misses():
    """The 09-11 probe's own first attempt returned ZERO items here."""
    raw = fixture_bytes("nikkei_asia_rss.xml")
    import xml.etree.ElementTree as ET
    naive = list(ET.fromstring(raw).iter("item"))
    assert naive == [], "if this ever finds items the fixture stopped being RDF"
    items = np_.parse_rss1_rdf(raw)
    assert len(items) == 3
    assert items[0]["published"] is not None, "dc:date must parse"
    assert "asia.nikkei.com" in items[0]["url"]


def test_atom_parser():
    items = np_.parse_atom_generic(fixture_bytes("reddit_algotrading.atom"))
    assert len(items) == 2
    assert items[0]["raw_id"] == "t3_1abcxyz"
    assert "momentum" in items[0]["title"].lower()


def test_edgar_parser_tags_item_202_and_carries_the_cik():
    items = np_.parse_edgar_atom(fixture_bytes("sec_edgar_getcurrent.atom"))
    assert len(items) == 3
    by_title = {i["title"]: i for i in items}
    kroger = next(v for k, v in by_title.items() if "KROGER" in k)
    exelixis = next(v for k, v in by_title.items() if "EXELIXIS" in k)
    assert "8-K:2.02" in kroger["entity_tags"], "the earnings print must be tagged"
    assert "8-K:2.02" not in exelixis["entity_tags"], "an 8.01 must NOT be tagged 2.02"
    assert "cik:0000056873" in kroger["entity_tags"]
    assert kroger["raw_id"] == "0001104659-26-106890", "the accession number is the dedupe key"
    assert kroger["published"] is not None


def test_gdelt_parser_reads_the_seendate_format():
    items = np_.parse_gdelt_doc(fixture_bytes("gdelt_doc.json"))
    assert len(items) == 3
    assert items[0]["published"].isoformat().startswith("2026-06-19T03:30:00")
    assert items[0]["lang"] == "korean"
    assert any(t.startswith("domain:") for t in items[0]["entity_tags"])


def test_gdelt_non_json_is_a_named_failure_not_a_crash():
    with pytest.raises(np_.FetchError, match="non-JSON"):
        np_.parse_gdelt_doc(b"<html>Please limit requests</html>")


# ------------------------------------------------------------------ the rows


def test_row_schema_is_exactly_the_roadmap_row(corpus):
    ctx = StubCtx(fixture_bytes("google_news_rss_en_hk.xml"), paced=False)
    rec = np_.pull_source("google_news_rss_en_hk", ctx)
    assert rec["new"] == 3
    day_files = sorted((corpus / "google_news_rss_en_hk").glob("*.jsonl"))
    assert len(day_files) == 1
    rows = [json.loads(x) for x in day_files[0].read_text(encoding="utf-8").splitlines()]
    for row in rows:
        assert set(row) == set(np_.ROW_KEYS), "the row schema drifted"
        assert row["source"] == "google_news_rss_en_hk"
        assert row["pit_grade"] == "index_state"
        assert isinstance(row["tickers"], list)
        assert isinstance(row["entity_tags"], list)


def test_first_seen_utc_is_written_by_us_not_parsed(corpus):
    """It is OUR stamp. For a first_seen_only source it is the only PIT anchor."""
    ctx = StubCtx(fixture_bytes("google_news_rss_en_hk.xml"), paced=False)
    before = np_._now()
    np_.pull_source("google_news_rss_en_hk", ctx)
    after = np_._now()
    row = json.loads(
        next((corpus / "google_news_rss_en_hk").glob("*.jsonl")).read_text(encoding="utf-8").splitlines()[0]
    )
    seen = np_._parse_iso(row["first_seen_utc"])
    assert before.replace(microsecond=0) <= seen <= after
    # ...and it is NOT the provider's pubDate.
    assert row["published_utc"] != row["first_seen_utc"]


def test_entity_resolution_runs_and_is_counted(corpus):
    ctx = StubCtx(fixture_bytes("google_news_rss_en_hk.xml"), paced=False)
    rec = np_.pull_source("google_news_rss_en_hk", ctx)
    assert rec["resolved"] + rec["unresolved"] == rec["new"]
    assert rec["resolution_rate"] is not None
    rows = [json.loads(x) for x in
            next((corpus / "google_news_rss_en_hk").glob("*.jsonl")).read_text(encoding="utf-8").splitlines()]
    alibaba = [r for r in rows if "9988.HK" in r["title"]]
    assert alibaba and alibaba[0]["tickers"] == ["BABA"], "the local HK code must map to its ADR leg"


def test_unresolved_rows_are_kept_and_counted(corpus):
    ctx = StubCtx(fixture_bytes("google_news_rss_en_hk.xml"), paced=False)
    rec = np_.pull_source("google_news_rss_en_hk", ctx)
    assert rec["unresolved"] >= 1, "the NPR/BBC headlines name no issuer"
    rows = next((corpus / "google_news_rss_en_hk").glob("*.jsonl")).read_text(encoding="utf-8").splitlines()
    assert any(json.loads(r)["tickers"] == [] for r in rows), "an unresolved row is KEPT, not dropped"


# -------------------------------------------------------- dedupe and cursors


def test_dedupe_across_two_runs(corpus):
    payload = fixture_bytes("google_news_rss_en_hk.xml")
    first = np_.pull_source("google_news_rss_en_hk", StubCtx(payload, paced=False))
    second = np_.pull_source("google_news_rss_en_hk", StubCtx(payload, paced=False))
    assert first["new"] == 3 and first["dupes"] == 0
    assert second["new"] == 0 and second["dupes"] == 3
    rows = next((corpus / "google_news_rss_en_hk").glob("*.jsonl")).read_text(encoding="utf-8").splitlines()
    assert len(rows) == 3, "the second run must not have appended duplicates"


def test_the_cursor_is_written_and_counts_runs(corpus):
    payload = fixture_bytes("google_news_rss_en_hk.xml")
    np_.pull_source("google_news_rss_en_hk", StubCtx(payload, paced=False))
    np_.pull_source("google_news_rss_en_hk", StubCtx(payload, paced=False, resume=True))
    cur = json.loads((corpus / "_cursors" / "google_news_rss_en_hk.json").read_text(encoding="utf-8"))
    assert cur["runs"] == 2
    assert cur["rows_written_total"] == 3
    assert cur["last_run_utc"]


def test_resume_feeds_the_cursor_back_to_the_fetcher(corpus):
    """Alpaca's incremental `created_at` — the fix for the 83.6% stall."""
    cur_dir = corpus / "_cursors"
    cur_dir.mkdir(parents=True, exist_ok=True)
    (cur_dir / "alpaca_benzinga_news.json").write_text(
        json.dumps({"source": "alpaca_benzinga_news", "next_cursor": "2026-09-01T00:00:00Z",
                    "runs": 4, "consecutive_zero_runs": 0}), encoding="utf-8")

    class Cred(StubCtx):
        def alpaca_credential(self):
            return "k", "s", "stub"

    ctx = Cred(fixture_bytes("alpaca_news.json"), paced=False, resume=True)
    rec = np_.pull_source("alpaca_benzinga_news", ctx)
    assert rec["new"] == 2
    assert "start=2026-09-01" in ctx.urls[0].replace("%3A", ":").replace("+", "")
    cur = json.loads((cur_dir / "alpaca_benzinga_news.json").read_text(encoding="utf-8"))
    assert cur["next_cursor"] == "2026-09-11T12:45:22Z", "the cursor advances to the newest created_at"


# ------------------------------------------------------------- the RED rule


def test_zero_rows_twice_is_red(corpus):
    empty = b'<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'
    first = np_.pull_source("google_news_rss_en_gb", StubCtx(empty, paced=False))
    assert first["status"] == "OK", "one quiet run is ordinary"
    assert first["consecutive_zero_runs"] == 1
    second = np_.pull_source("google_news_rss_en_gb", StubCtx(empty, paced=False, resume=True))
    assert second["status"] == "RED"
    assert second["consecutive_zero_runs"] == 2
    assert any("RED" in f for f in second["failures"])


def test_a_good_run_resets_the_zero_counter(corpus):
    empty = b'<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'
    np_.pull_source("google_news_rss_en_gb", StubCtx(empty, paced=False))
    good = np_.pull_source("google_news_rss_en_gb",
                           StubCtx(fixture_bytes("google_news_rss_en_hk.xml"), paced=False, resume=True))
    assert good["consecutive_zero_runs"] == 0
    assert good["status"] == "OK"


# ---------------------------------------------------------------- refusals


def test_an_unregistered_source_is_refused_before_any_effect(corpus):
    with pytest.raises(registry.UnknownSource, match="REFUSED"):
        np_.pull_source("bloomberg_terminal", StubCtx(b"", paced=False))
    assert not corpus.exists(), "a refusal must not create a corpus directory"


def test_alpaca_without_a_key_refuses_by_name_and_does_not_crash(corpus):
    class NoCred(StubCtx):
        def alpaca_credential(self):
            return None, None, "no terminal repo .env found"

    rec = np_.pull_source("alpaca_benzinga_news", NoCred(b"", paced=False))
    assert rec["status"] == "REFUSED"
    msg = rec["failures"][0]
    assert "APCA_API_KEY_ID" in msg and "APCA_API_SECRET_KEY" in msg, "the refusal names the KEYS"
    assert "AAT_HACK" in msg, "and names the terminal-repo fallback it also tried"
    # A refusal is not a zero-row run: it already names its own cause.
    assert rec["consecutive_zero_runs"] == 0


def test_a_refusal_never_prints_a_key_value(corpus):
    class Cred(StubCtx):
        def alpaca_credential(self):
            return "SUPERSECRETKEYID", "SUPERSECRETVALUE", "terminal repo .env, HACK3 (data endpoint only)"

    rec = np_.pull_source("alpaca_benzinga_news", Cred(fixture_bytes("alpaca_news.json"), paced=False))
    blob = json.dumps(rec)
    assert "SUPERSECRET" not in blob, "a receipt must carry the credential SOURCE, never a value"
    assert "HACK3" in blob


def test_an_unimplemented_source_says_why(corpus):
    rec = np_.pull_source("akshare_stock_news_em", StubCtx(b"", paced=False))
    assert rec["status"] == "NOT_IMPLEMENTED"
    assert "akshare is NOT INSTALLED" in rec["failures"][0]


def test_wikipedia_is_refused_as_a_sensor_not_a_news_source(corpus):
    rec = np_.pull_source("wikipedia_pageviews", StubCtx(b"", paced=False))
    assert rec["status"] == "NOT_IMPLEMENTED"
    assert "COVERAGE SENSOR" in rec["failures"][0]


# ------------------------------------------------------------ other fetchers


def test_yfinance_news_fetcher(corpus):
    items = json.loads(fixture_bytes("yfinance_ticker_news.json"))

    class YF(StubCtx):
        def yf_news(self, symbol):
            return items

    ctx = YF(b"", paced=False, max_rows=2)
    ctx._universe = ["NVDA"]
    rec = np_.pull_source("yfinance_ticker_news", ctx)
    assert rec["new"] == 2
    row = json.loads(
        next((corpus / "yfinance_ticker_news").glob("*.jsonl")).read_text(encoding="utf-8").splitlines()[0]
    )
    assert row["tickers"] == ["NVDA"], "the provider's own tag wins over the resolver"
    assert row["raw_id"].startswith("https://finance.yahoo.com")
    assert row["body"], "the ~130-char blurb is the body"


def test_yfinance_without_a_universe_refuses(corpus):
    ctx = StubCtx(b"", paced=False)
    ctx._universe = []
    rec = np_.pull_source("yfinance_ticker_news", ctx)
    assert rec["status"] == "REFUSED"
    assert "no universe file" in rec["failures"][0]


def test_edgar_paging_stops_on_an_empty_page(corpus):
    empty = b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
    ctx = StubCtx({"start=": empty, "getcurrent": fixture_bytes("sec_edgar_getcurrent.atom")},
                  paced=False, max_rows=400)
    rec = np_.pull_source("sec_edgar_8k_current_atom", ctx)
    assert rec["new"] == 3
    assert rec["calls"] == 2, "page 2 came back empty and paging stopped"


def test_gdelt_is_paced_from_the_registry_not_from_the_docs():
    """20 s, the MEASURED cadence. The documented 5 s 429'd 3 of 5 probes."""
    src = registry.get("gdelt_doc_v2")
    ctx = np_.RunContext(paced=True)
    assert ctx.pace(src) >= 15
    assert np_.RunContext(paced=False).pace(src) == 0.0


def test_the_theme_queries_are_built_from_the_real_basket_shape():
    """`themes: {<name>: {members: [{ticker, ...}]}}` — NOT a bare symbol list.

    A first pass here read `body["symbols"]`, produced zero theme queries, and
    looked exactly like a working sweep: GDELT ran its six region queries and
    nobody would have noticed the five theme queries were missing.
    """
    q = np_.RunContext().theme_queries()
    assert len(q) >= 5, "the theme sweep silently produced nothing"
    assert any("NVDA" in x for x in q)
    assert all(x.startswith("(") and " OR " in x for x in q)


def test_gdelt_429_records_the_missing_ngrams_fallback(corpus):
    class Limited(StubCtx):
        def http_get(self, url, headers=None):
            raise np_.FetchError("HTTP 429 https://api.gdeltproject.org/api/v2/doc/doc")

    rec = np_.pull_source("gdelt_doc_v2", Limited(b"", paced=False))
    assert rec["received"] == 0
    assert any("NGrams 3.0 bulk fallback is NOT implemented" in f for f in rec["failures"])


# ---------------------------------------------------------------- receipts


def test_every_run_writes_a_receipt(corpus):
    rec = np_.pull_source("google_news_rss_en_hk",
                          StubCtx(fixture_bytes("google_news_rss_en_hk.xml"), paced=False))
    receipts = sorted((corpus / "_receipts").glob("*_google_news_rss_en_hk.json"))
    assert receipts, "no receipt written"
    payload = json.loads(receipts[-1].read_text(encoding="utf-8"))
    for key in ("requested", "received", "new", "dupes", "failures",
                "consecutive_zero_runs", "resolution_rate", "pit_grade", "label_source"):
        assert key in payload, f"receipt lost {key}"
    assert payload["llm_spend_usd"] == 0.0
    assert rec["receipt_path"].endswith(".json")


def test_pull_all_writes_a_summary_and_names_its_red_sources(corpus):
    ctx = StubCtx(fixture_bytes("google_news_rss_en_hk.xml"), paced=False)
    out = np_.pull_all(["google_news_rss_en_hk", "google_news_rss_en_sg"], ctx=ctx)
    assert out["sources"] == 2
    assert out["rows_new"] == 6, "each source dedupes against its OWN directory, so both keep 3"
    assert "red" in out and "refused" in out
    assert out["name_table"]["issuer_rows"] >= 3000
    assert Path(out["receipt_path"]).exists()


def test_the_cli_lists_the_registry(capsys):
    assert np_.main(["--list"]) == 0
    printed = capsys.readouterr().out
    assert "gdelt_doc_v2" in printed
    assert "label=False" in printed and "label=True" in printed


def test_the_cli_refuses_an_unknown_source(capsys):
    assert np_.main(["--source", "not_a_source"]) == 2
    assert "REFUSED" in capsys.readouterr().out
