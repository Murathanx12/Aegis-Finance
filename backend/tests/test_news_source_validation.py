from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib

import pytest

from backend.services import news_source_validation as NV, world_digest as WD


def fixture():
    now = datetime.now(timezone.utc)
    item = WD.Item("source-1", "article", "sec", "https://example.com/article", "CACC announcement",
                   "Credit Acceptance announced today that it has entered or will enter into consent judgments.",
                   (now - timedelta(hours=1)).isoformat(), tickers_named=["CACC"])
    row = WD.type_row({"tickers": ["CACC"], "event_type": "other", "summary": "Mixed settlement timing"}, item)
    row["extract_model"] = "stored_model"
    cache = {"cache_key": WD.cache_key(item), "cached_utc": now.isoformat(), "row": row}
    return item, cache, now.isoformat()


def test_legacy_model_row_is_bound_only_never_semantically_promoted():
    item, cache, cutoff = fixture()
    result = NV.validate_cached(item, cache, cutoff_utc=cutoff)
    assert result["status"] == "BOUND_ONLY" and result["source_identity_validated"]
    assert not result["semantic_grounding_validated"]
    assert result["operative_event_date"] is None and result["estimated_event_dates"] == []


@pytest.mark.parametrize("field", ["text", "title", "url"])
def test_changed_source_invalidates_cache_binding(field):
    item, cache, cutoff = fixture()
    setattr(item, field, getattr(item, field) + " changed")
    with pytest.raises(NV.SourceValidationError, match="cache_source_or_prompt_drift"):
        NV.validate_cached(item, cache, cutoff_utc=cutoff)


@pytest.mark.parametrize("field", ["first_seen_utc", "published_utc", "cached_utc"])
def test_future_inputs_fail_loud(field):
    item, cache, cutoff = fixture()
    future = (datetime.fromisoformat(cutoff) + timedelta(seconds=1)).isoformat()
    if field == "cached_utc":
        cache[field] = future
    else:
        setattr(item, field, future)
    with pytest.raises(NV.SourceValidationError):
        NV.validate_cached(item, cache, cutoff_utc=cutoff)


def test_typed_row_cannot_change_source_identity_or_add_an_action_day():
    item, cache, cutoff = fixture()
    cache["row"]["first_seen_utc"] = cutoff
    with pytest.raises(NV.SourceValidationError, match="metadata_drift"):
        NV.validate_cached(item, cache, cutoff_utc=cutoff)
    _, cache, _ = fixture()
    # Use the original matching source metadata for the operative-date check.
    cache["cache_key"] = WD.cache_key(item)
    cache["row"] = WD.type_row(cache["row"], item)
    cache["cached_utc"] = cutoff
    cache["row"]["event_date"] = cutoff[:10]
    with pytest.raises(NV.SourceValidationError, match="operative_or_estimated"):
        NV.validate_cached(item, cache, cutoff_utc=cutoff)


def test_mixed_cacc_reporting_phrase_does_not_license_settlement_date():
    item, _, cutoff = fixture()
    source = item.text
    facts = {"entity": "Credit Acceptance", "event_type": "litigation_settlement",
             "event_date": cutoff[:10], "date_precision": "day", "numbers": [],
             "evidence_spans": [source], "abstain": False}
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    with pytest.raises(NV.SourceValidationError, match="unsupported_operative_event_day"):
        NV.validate_article_facts(facts, source, source_sha256=source_hash)
    facts.update(event_date=None, date_precision="unknown")
    accepted = NV.validate_article_facts(facts, source, source_sha256=source_hash)
    assert accepted["event_date"] is None and not accepted["semantic_grounding_validated"]
    with pytest.raises(NV.SourceValidationError, match="source_drift"):
        NV.validate_article_facts(facts, source + "changed", source_sha256=source_hash)


def test_evidence_contract_cannot_relabel_an_unbound_date_as_reporting():
    item, cache, cutoff = fixture()
    source = item.title + "\n" + item.text
    cache["evidence_contract"] = {"source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                                  "dates": [{"role": "reporting", "status": "source_reported", "date": cutoff[:10]}]}
    with pytest.raises(NV.SourceValidationError, match="normalization_contract_missing"):
        NV.validate_cached(item, cache, cutoff_utc=cutoff)
