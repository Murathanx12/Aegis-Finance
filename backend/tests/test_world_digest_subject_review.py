"""Astra E1 regression packet: synthetic fixtures; no provider/security authority."""
from copy import deepcopy
import hashlib
import json
import os

import pytest

from backend.services import news_source_validation as NV, world_digest as WD
from backend.tests.test_world_digest_subjects import forbidden, item, reply, sec_item


@pytest.fixture(autouse=True)
def no_models(monkeypatch):
    from backend.services import llm_analyzer
    monkeypatch.setattr(llm_analyzer, "call_named", forbidden)
    monkeypatch.setattr(WD._cfg, "WORLD_DIGEST_LOCAL_EXTRACT", False)


@pytest.mark.parametrize("title", [
    "Apple reports Qualcomm results", "Qualcomm announces Apple quarterly results",
    "Qualcomm reports its partner Apple earnings", "Apple cuts Qualcomm estimates",
    "Apple reports its partner quarterly results", "Apple announces results for its customer",
])
def test_reporter_or_partner_titles_do_not_identify_an_own_event(title):
    row = WD.type_row(reply(["QCOM", "AAPL"]), item(title=title))
    assert row["tickers"] == []
    assert row["tickers_unverified"] == ["AAPL", "QCOM"]


@pytest.mark.parametrize("ticker,cik,name", [("WU", "320193", "Western Union"),
    ("AAPL", "1418121", "Apple Hospitality REIT, Inc.")])
def test_sec_string_agreement_is_not_owner_to_security_proof(ticker, cik, name):
    source = sec_item(ticker, cik, name,
        text=f"Exhibit 99.1\n{'Apple' if ticker == 'AAPL' else name} Reports Quarterly Results\n"
             f"November 4, 2026 - (NASDAQ: {ticker}); issuer also mentions NYSE: APLE.")
    row = WD.type_row(reply([ticker]), source)
    assert row["tickers"] == [] and row["tickers_unverified"] == [ticker]


@pytest.mark.parametrize("changes", [
    {}, {"first_seen_utc": "", "published_utc": None},
    {"url": "https://example.test/not-sec"},
])
def test_sec_generic_issuer_title_cannot_bypass_primary_qualification(changes):
    source = sec_item(title="Western Union reports quarterly results", **changes)
    row = WD.type_row(reply(["WU"]), source)
    assert row["tickers"] == [] and row["tickers_unverified"] == ["WU"]


@pytest.mark.parametrize("ticker,cik,name", [("WU", "1365135", "Western Union"),
                                          ("KVYO", "1835830", "Klaviyo")])
def test_genuine_sec_identification_remains_candidate_without_dated_security_edge(ticker, cik, name):
    source = sec_item(ticker, cik, name)
    row = WD.type_row(reply([ticker]), source)
    assert row["tickers"] == [] and row["tickers_unverified"] == [ticker]
    assert row["security_authorization"] == "UNAVAILABLE"
    assert row["published_utc"] == source.published_utc
    assert row["first_seen_utc"] == source.first_seen_utc


BAD_FIELDS = [True, 1, "AAPL", {}, [None], [{}], [True], ["A" * 9], ["AAAAA"] * 50000]


@pytest.mark.parametrize("bad", BAD_FIELDS, ids=["bool", "int", "string", "object", "null-item",
                                               "object-item", "bool-item", "long-item", "oversized"])
def test_legacy_invalid_unverified_field_abstains_without_coercion(bad):
    raw = dict(reply([]), tickers_unverified=bad)
    assert WD.type_row(raw, item()) is None


@pytest.mark.parametrize("bad", BAD_FIELDS, ids=["bool", "int", "string", "object", "null-item",
                                               "object-item", "bool-item", "long-item", "oversized"])
def test_strict_invalid_unverified_field_has_named_whole_row_refusal(bad):
    raw = dict(reply([]), tickers_unverified=bad)
    with pytest.raises(NV.SourceValidationError, match="ticker"):
        WD.type_current_row(raw, item())


def test_bounds_are_checked_before_element_iteration():
    class NoIteration(list):
        def __iter__(self):
            pytest.fail("oversized/subclass payload must be rejected before iteration")
    with pytest.raises(NV.SourceValidationError, match="ticker"):
        WD.type_current_row(dict(reply([]), tickers_unverified=NoIteration(["AAAAA"] * 50000)), item())


def test_malformed_strict_cached_reply_returns_refused_without_model_or_mutation():
    from backend.tests.test_news_source_validation import current_control
    source, capture, review, cutoff = current_control()
    raw = json.loads(capture["raw_reply"])
    raw["tickers_unverified"] = True
    capture["raw_reply"] = json.dumps(raw)
    before = deepcopy(capture)
    meter = WD.Meter(0, llm=forbidden)
    result = WD.extract_current_item(source, meter, cache={WD.current_cache_key(source): capture},
                                     cutoff_utc=cutoff, stage_cap=0, semantic_review=review)
    assert result["status"] == "REFUSED" and result["rows"] == []
    assert "ticker" in result["reason"]
    assert result["capture"] == before and meter.calls == 0


def test_malformed_legacy_cache_does_not_trigger_model_retry(tmp_path):
    source = item()
    meter = WD.Meter(0, llm=forbidden)
    old = dict(reply([]), tickers_unverified=True)
    cached = {WD.cache_key(source): {"row": old}}
    before = deepcopy(cached)
    result = WD.extract_items([source], meter, cache=cached, stage_cap=0, workers=1,
                              cache_file=tmp_path / "never.jsonl", local_runner=forbidden)
    assert result["rows"] == [] and result["cache_refused"] == 1
    assert meter.calls == 0 and cached == before
    assert not (tmp_path / "never.jsonl").exists()


def test_same_stat_catalog_replacement_binds_actual_bytes_and_both_keys(tmp_path, monkeypatch):
    path = tmp_path / "data/news_entities/issuers.csv"
    path.parent.mkdir(parents=True)
    first = b"symbol,primary_name,aliases,country,is_adr\nQCOM,Qualcomm Incorporated,,US,\n"
    second = first.replace(b"Qualcomm", b"Fakecomm")
    path.write_bytes(first)
    monkeypatch.setattr(WD._cfg, "BACKEND_DIR", tmp_path)
    source = item(title="Qualcomm reports quarterly results")
    a, ac = WD.cache_key(source), WD.current_cache_key(source)
    assert WD.type_row(reply(["QCOM"]), source)["tickers"] == ["QCOM"]
    stat = path.stat()
    path.write_bytes(second)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert path.stat().st_size == stat.st_size and path.stat().st_mtime_ns == stat.st_mtime_ns
    assert WD._subject_catalog()[1] == hashlib.sha256(second).hexdigest()
    assert WD.cache_key(source) != a and WD.current_cache_key(source) != ac
    assert WD.type_row(reply(["QCOM"]), source)["tickers"] == []


def test_strict_headline_preserves_model_abstention_over_upstream_tag():
    raw = reply([])
    source = item(kind="headline", title="Qualcomm reports quarterly results", tickers_named=["QCOM"])
    before = deepcopy(raw)
    row = WD.type_current_row(raw, source)
    assert row["tickers"] == [] and raw == before
    assert row["security_authorization"] == "UNAVAILABLE"


def test_subject_candidate_does_not_authorize_current_security_assignment():
    source = item()
    assert WD.type_row(reply(["QCOM"]), source)["tickers"] == ["QCOM"]
    with pytest.raises(NV.SourceValidationError, match="security_authorization"):
        WD.type_current_row(reply(["QCOM"]), source)
