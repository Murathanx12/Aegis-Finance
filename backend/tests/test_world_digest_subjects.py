"""Subject admission controls; all source text is synthetic, no licensed bodies.

The QCOM layout reproduces raw 71306938456cdf61ec9f's distinction between
PSNL discovery provenance, AAPL mentions and the Qualcomm article subject.
"""
from copy import deepcopy
import json

import pytest

from backend.services import news_source_validation as NV, world_digest as WD


def item(**changes):
    values = dict(item_id="qcom", kind="article", source="marketwatch",
        url="https://www.marketwatch.com/story/synthetic-qcom",
        title="Qualcomm's stock falls as twin forces pressure sales",
        text="QCOM -5.3%\nAAPL +0.2%\nQualcomm reports lower handset sales. "
             "Apple is mentioned as a customer using its own modems.",
        first_seen_utc="2026-11-04T22:41:00+00:00",
        published_utc="2026-11-04T22:03:00+00:00", tickers_named=["AAPL"])
    values.update(changes)
    return WD.Item(**values)


def reply(tickers):
    return dict(event_type="earnings", novelty="new_fact", tickers=tickers,
                topic="Quarterly results", summary="Quarterly sales changed.", forward_claims=[])


def forbidden(*args, **kwargs):
    pytest.fail("subject/cache checks must not call a provider, local model or broker")


@pytest.fixture(autouse=True)
def no_models(monkeypatch):
    from backend import config
    from backend.services import llm_analyzer
    monkeypatch.setattr(llm_analyzer, "call_named", forbidden)
    monkeypatch.setattr(config, "WORLD_DIGEST_LOCAL_EXTRACT", False)


def test_qcom_mentions_never_become_subjects_and_clocks_are_preserved():
    source = item()
    raw = reply(["QCOM", "AAPL", "PSNL", "ZZZZ"])
    before = deepcopy(raw)
    row = WD.type_row(raw, source)
    assert row["tickers"] == ["QCOM"]
    assert row["tickers_unverified"] == ["AAPL", "PSNL", "ZZZZ"]
    assert row["first_seen_utc"] == source.first_seen_utc
    assert row["published_utc"] == source.published_utc
    assert raw == before and source.tickers_named == ["AAPL"]


@pytest.mark.parametrize("title,ticker", [
    ("Micron (MU) beats on memory prices", "MU"),
    ("Qualcomm reports quarterly results", "QCOM"),
    ("Apple's shares fall after earnings", "AAPL"),
    ("Microsoft revenue rises", "MSFT"),
    ("Alphabet (GOOGL) reports results", "GOOGL"),
    ("Novo Nordisk raises guidance", "NVO"),
])
def test_unambiguous_issuer_title_positives(title, ticker):
    row = WD.type_row(reply([ticker]), item(title=title, tickers_named=[]))
    assert row["tickers"] == [ticker]
    assert row["tickers_unverified"] == []


@pytest.mark.parametrize("title,tickers,kind", [
    ("Qualcomm supplier cuts forecasts", ["QCOM"], "article"),
    ("Apple and Qualcomm report results", ["AAPL", "QCOM"], "article"),
    ("Alphabet reports results", ["GOOG", "GOOGL"], "article"),
    ("Snow expected in the mountains", ["SNOW"], "headline"),
    ("Apple harvest falls after storms", ["AAPL"], "headline"),
    ("QCOM | Qualcomm Analyst Estimates", ["QCOM"], "stock_page"),
    ("Qualcomm reports results", ["QCOM"], "social"),
    ("The semiconductor outlook", ["AAPL"], "article"),
    ("Apple reports on Qualcomm results", ["AAPL"], "article"),
])
def test_ambiguous_or_non_event_sources_abstain(title, tickers, kind):
    row = WD.type_row(reply(tickers), item(title=title, kind=kind, tickers_named=tickers))
    assert row["tickers"] == []
    assert set(row["tickers_unverified"]) == set(tickers)


def test_headline_model_abstention_is_not_overridden_by_upstream_tags():
    row = WD.type_row(reply([]), item(kind="headline", tickers_named=["PSNL", "QCOM"]))
    assert row["tickers"] == [] and row["tickers_unverified"] == []


def test_strict_current_contract_refuses_whole_reply_without_repair():
    raw = reply(["QCOM", "AAPL"])
    before = deepcopy(raw)
    with pytest.raises(NV.SourceValidationError, match="subject"):
        WD.type_current_row(raw, item())
    assert raw == before


def test_cached_model_row_is_requalified_without_calls_or_cache_mutation(tmp_path):
    source = item()
    old = dict(WD.type_row(reply([]), source), tickers=["AAPL", "QCOM"],
               tickers_unverified=["ZZZZ"], extract_model="offline-cached")
    cached = {WD.cache_key(source): {"row": old}}
    before = deepcopy(cached)
    meter = WD.Meter(0, llm=forbidden)
    result = WD.extract_items([source], meter, cache=cached, stage_cap=0,
                              workers=1, cache_file=tmp_path / "never-written.jsonl",
                              local_runner=forbidden)
    row, = result["rows"]
    assert row["tickers"] == ["QCOM"]
    assert row["tickers_unverified"] == ["AAPL", "ZZZZ"]
    assert row["extract_model"] == "offline-cached"
    assert result["cache_hits"] == 1 and meter.calls == 0
    assert cached == before and not (tmp_path / "never-written.jsonl").exists()


def test_old_disk_cache_cannot_restore_aapl_or_invent_source_clocks(tmp_path):
    source = item()
    old = dict(reply(["AAPL"]), first_seen_utc="invented", published_utc="invented",
               extract_model="offline-cached")
    path = tmp_path / "cache.jsonl"
    path.write_text(json.dumps({"cache_key": WD.cache_key(source), "row": old}) + "\n")
    result = WD.extract_items([source], WD.Meter(0, llm=forbidden),
        cache=WD.read_cache(path), stage_cap=0, workers=1, local_runner=forbidden)
    row, = result["rows"]
    assert row["tickers"] == [] and row["tickers_unverified"] == ["AAPL"]
    assert row["first_seen_utc"] == source.first_seen_utc
    assert row["published_utc"] == source.published_utc


def test_subject_contract_versions_both_extraction_identities(monkeypatch):
    source = item()
    old, current = WD.cache_key(source), WD.current_cache_key(source)
    monkeypatch.setattr(WD, "SUBJECT_ADMISSION_VERSION", "changed-subject-contract")
    assert WD.cache_key(source) != old
    assert WD.current_cache_key(source) != current


def sec_item(ticker="WU", cik="1365135", name="Western Union", **changes):
    defaults = dict(source="sec_edgar_8k_ex99_body",
        url=f"https://www.sec.gov/Archives/edgar/data/{cik}/000119312526447234/ex99.htm",
        title=f"8-K - {name} ({int(cik):010d}) (Filer) - EX-99.1",
        text=f"Exhibit 99.1\n{name} Reports Third Quarter Results\n"
             f"November 4, 2026 - {name} (NYSE: {ticker}) today reported revenue.",
        tickers_named=[], first_seen_utc="2026-11-05T00:15:28+00:00",
        published_utc="2026-11-04T21:08:36+00:00")
    defaults.update(changes)
    return item(**defaults)


@pytest.mark.parametrize("ticker,cik,name", [("WU", "1365135", "Western Union"),
                                            ("KVYO", "1835830", "Klaviyo")])
def test_dated_sec_header_is_candidate_only_without_owner_security_edge(ticker, cik, name):
    source = sec_item(ticker, cik, name)
    row = WD.type_row(reply([ticker]), source)
    assert row["tickers"] == [] and row["tickers_unverified"] == [ticker]
    assert row["security_authorization"] == "UNAVAILABLE"
    assert row["published_utc"] == source.published_utc
    # Filing-agent accession 1193125 is deliberately different from issuer CIK.
    assert "0001193125" in source.url


@pytest.mark.parametrize("changes", [
    {"url": "https://www.sec.gov/Archives/edgar/data/1193125/acc/ex99.htm"},
    {"url": "https://www.sec.gov.evil.test/Archives/edgar/data/1365135/acc/ex99.htm"},
    {"published_utc": None},
    {"published_utc": "2026-11-06T00:00:00+00:00"},
    {"first_seen_utc": "2026-11-05T00:15:28"},
    {"text": "Exhibit 99.1\nQualcomm reports results.\nMentioned securities: NYSE: WU"},
])
def test_unqualified_sec_or_counterparty_witness_abstains(changes):
    row = WD.type_row(reply(["WU"]), sec_item(**changes))
    assert row["tickers"] == [] and row["tickers_unverified"] == ["WU"]


def test_primary_issuer_title_cannot_replace_missing_owner_security_evidence():
    source = item(title="Apple reports quarterly results", source="issuer_release",
                  url="https://www.apple.com/newsroom/synthetic-results", tickers_named=["QCOM"])
    row = WD.type_row(reply(["AAPL", "QCOM"]), source)
    assert row["tickers"] == [] and row["tickers_unverified"] == ["AAPL", "QCOM"]


@pytest.mark.parametrize("kind", ["article", "headline"])
def test_fresh_extraction_and_written_cache_share_subject_gate(kind, tmp_path):
    source = item(kind=kind)
    raw = reply(["QCOM", "AAPL", "PSNL"])
    payload = {"rows": [dict(raw, i=0)]} if kind == "headline" else raw

    class FixtureMeter:
        def call(self, *args, **kwargs):
            return json.dumps(payload)  # fixture reply; no model/backend invoked

        def last_model(self):
            return "offline-fixture"

    path = tmp_path / "cache.jsonl"
    result = WD.extract_items([source], FixtureMeter(), cache={}, stage_cap=0,
                              workers=1, cache_file=path, local_runner=forbidden)
    row, = result["rows"]
    assert row["tickers"] == ["QCOM"]
    assert row["tickers_unverified"] == ["AAPL", "PSNL"]
    persisted = WD.read_cache(path)[WD.cache_key(source)]["row"]
    assert persisted == row
    assert persisted["first_seen_utc"] == source.first_seen_utc


def test_primary_exchange_witness_is_not_a_dated_security_edge():
    source = sec_item("GOOGL", "1652044", "Alphabet",
        text="Exhibit 99.1\nAlphabet Reports Quarterly Results\n"
             "November 4, 2026 - Alphabet (NASDAQ: GOOGL) reported results.")
    row = WD.type_row(reply(["GOOGL", "GOOG"]), source)
    assert row["tickers"] == [] and row["tickers_unverified"] == ["GOOG", "GOOGL"]


def test_missing_name_catalog_abstains_instead_of_using_page_mentions(monkeypatch):
    monkeypatch.setattr(WD, "_subject_catalog", lambda: ({}, "UNAVAILABLE"))
    row = WD.type_row(reply(["QCOM", "AAPL"]), item())
    assert row["tickers"] == [] and row["tickers_unverified"] == ["AAPL", "QCOM"]


def test_primary_results_heading_still_needs_owner_security_edge():
    source = sec_item("KVYO", "1835830", "Klaviyo",
        text="Exhibit 99.1\nKlaviyo Delivers Solid Q3 with Enterprise Growth\n"
             "November 4, 2026 - Klaviyo (NYSE: KVYO) announced quarterly results.")
    row = WD.type_row(reply(["KVYO"]), source)
    assert row["tickers"] == [] and row["tickers_unverified"] == ["KVYO"]


def test_collect_full_page_keeps_mentions_separate_from_discovery_tags(tmp_path):
    from datetime import datetime, timedelta
    source = item(text=item().text * 8)
    folder = tmp_path / "news_corpus" / "dowjones" / "marketwatch" / "2026-11-04"
    folder.mkdir(parents=True)
    record = dict(url=source.url, title=source.title, text=source.text,
                  first_seen_utc=source.first_seen_utc, published_utc=source.published_utc,
                  publisher="marketwatch", tickers_named=["AAPL"], tickers=["PSNL"],
                  page_kind="article")
    (folder / "synthetic.json").write_text(json.dumps(record), encoding="utf-8")
    until = datetime.fromisoformat(source.first_seen_utc)
    collected, = WD.collect(until - timedelta(hours=1), until, root=tmp_path)["items"]
    assert collected.tickers_named == ["AAPL"]
    assert WD.type_row(reply(["QCOM", "AAPL", "PSNL"]), collected)["tickers"] == ["QCOM"]
