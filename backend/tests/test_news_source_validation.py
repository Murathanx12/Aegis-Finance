from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json

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


def current_control():
    """Synthetic exact-bound control; no real source qualification claim."""
    now = datetime.now(timezone.utc)
    item = WD.Item("control", "article", "sec", "https://sec.gov/control", "MU guidance",
                   "Micron management predicts MU revenue will rise in the coming weeks.",
                   (now - timedelta(hours=2)).isoformat(),
                   published_utc=(now - timedelta(hours=3)).isoformat(), tickers_named=["MU"])
    raw = {"topic": "MU guidance", "summary": "Management predicts a revenue increase.",
           "event_type": "guidance", "novelty": "new_fact", "forward_claims": [
               {"subject": "MU", "direction": "up", "horizon": "weeks", "who": "management",
                "speaker": "Micron management", "modality": "prediction", "witness": item.text}]}
    prompt, flagged = WD._item_prompt(item)
    capture = {"cache_key": WD.current_cache_key(item),
               "extraction_identity": WD.current_extraction_identity(),
               "source_sha256": NV.content_sha256(item.title + "\n" + item.text),
               "source_item_sha256": NV.content_sha256(vars(item)),
               "user_prompt": prompt, "raw_reply": json.dumps(raw),
               "extract_model": "offline-control", "injection_lines_removed": flagged,
               "started_utc": (now - timedelta(hours=1)).isoformat(),
               "cached_utc": (now - timedelta(minutes=30)).isoformat(),
               "row": WD.type_current_row(raw, item)}
    review = {"schema": "current_news_semantic_review/1", "decision": "FULL_ROW_ACCEPTED",
              "independent": True, "reviewer": "offline control reviewer",
              "capture_sha256": NV.current_binding(capture), "reviewed_utc": now.isoformat(),
              "claim_indices": [0], "checks": ["full_row", "speaker_modality_horizon",
                  "quantities_units_baselines", "reporting_date_only_no_inferred_operative_date"]}
    return item, capture, review, (now + timedelta(seconds=1)).isoformat()


def test_current_requires_independent_full_row_review_not_exact_spans():
    item, capture, review, cutoff = current_control()
    with pytest.raises(NV.SourceValidationError, match="independent_full_row"):
        NV.admit_current(item, capture, semantic_review=None, cutoff_utc=cutoff)
    result = NV.admit_current(item, capture, semantic_review=review, cutoff_utc=cutoff)
    assert result["semantic_grounding_validated"] and not result["eligible_for_existing_shadow_v0"]
    review["claim_indices"] = []
    with pytest.raises(NV.SourceValidationError, match="claim_review_incomplete"):
        NV.admit_current(item, capture, semantic_review=review, cutoff_utc=cutoff)


@pytest.mark.parametrize("field", ["raw_reply", "row", "extract_model", "user_prompt",
                                  "source_sha256", "extraction_identity", "cached_utc"])
def test_current_review_binds_every_capture_field(field):
    item, capture, review, cutoff = current_control()
    capture[field] = deepcopy(capture[field])
    if field == "row":
        capture[field]["summary"] = "A different assertion"
    elif field == "extraction_identity":
        capture[field]["version"] = "legacy"
    elif field == "cached_utc":
        capture[field] = datetime.fromisoformat(cutoff).isoformat()
    else:
        capture[field] += "changed"
    with pytest.raises(NV.SourceValidationError):
        NV.admit_current(item, capture, semantic_review=review, cutoff_utc=cutoff)


@pytest.mark.parametrize("field", ["first_seen_utc", "published_utc"])
@pytest.mark.parametrize("bad_time", ["future", "naive"])
def test_current_source_chronology_refuses_future_and_naive(field, bad_time):
    item, capture, review, cutoff = current_control()
    setattr(item, field, ((datetime.fromisoformat(cutoff) + timedelta(days=1)).isoformat()
                          if bad_time == "future" else cutoff[:19]))
    with pytest.raises(NV.SourceValidationError):
        NV.admit_current(item, capture, semantic_review=review, cutoff_utc=cutoff)


def test_detached_semantics_cannot_be_admitted_by_span_only_receipt():
    item, capture, review, cutoff = current_control()
    review["checks"] = ["exact_spans"]
    with pytest.raises(NV.SourceValidationError, match="semantic_review_incomplete"):
        NV.admit_current(item, capture, semantic_review=review, cutoff_utc=cutoff)


@pytest.mark.parametrize("field,value", [
    ("checks", {"full_row": False, "speaker_modality_horizon": False,
                "quantities_units_baselines": False,
                "reporting_date_only_no_inferred_operative_date": False}),
    ("checks", [{"full_row": False}]), ("checks", False),
    ("checks", ["full_row"] * 4), ("claim_indices", [False]),
    ("claim_indices", [0.0]), ("claim_indices", {0: True}), ("claim_indices", [[0]])])
def test_current_malformed_receipt_refuses_with_original_capture(field, value):
    item, capture, review, cutoff = current_control()
    original = deepcopy(capture)
    review[field] = value
    meter = WD.Meter(0, llm=lambda *a, **kw: pytest.fail("cache hit must not call"))
    result = WD.extract_current_item(item, meter, cache={WD.current_cache_key(item): capture},
        cutoff_utc=cutoff, stage_cap=0, semantic_review=review)
    assert result["status"] == "REFUSED" and result["rows"] == []
    assert result["capture"] == original and meter.calls == 0
