"""Synthetic refusal controls; real sources are retained privately, not fixtures."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest

from backend.services import news_source_validation as NV, world_digest as WD


def control():
    now = datetime.now(timezone.utc)
    item = WD.Item("context", "article", "issuer", "https://example.com/release",
                   "Issuer release", "Issued on: 2026/10/08. Revenue was USD 12 million in September 2026. "
                   "Conference 2026-10-15 14:00:00 Asia/Taipei. Issuer management predicts "
                   "revenue will rise in the next weeks.",
                   (now - timedelta(hours=2)).isoformat())
    facts = {"entity": "Issuer", "event_date": None, "date_precision": "unknown",
             "abstain": False, "evidence_spans": [item.text], "numbers": ["12"]}
    annotation = {"facts": facts, "dates": [{"role": "scheduled_event",
                  "value": "2026-10-15 14:00:00", "precision": "second",
                  "timezone": "Asia/Taipei", "witness": "Conference 2026-10-15 14:00:00 Asia/Taipei."}],
                  "source_predictions": [], "aegis_hypotheses": ["Does revenue convert into cash?"]}
    capture = {"schema": "current_news_context_capture/2", "cache_key": WD.context_cache_key(item),
               "extraction_identity": WD.context_extraction_identity(),
               "source_sha256": NV.content_sha256(item.title + "\n" + item.text),
               "source_item_sha256": NV.content_sha256(vars(item)),
               "started_utc": (now - timedelta(hours=1)).isoformat(),
               "completed_utc": (now - timedelta(minutes=30)).isoformat(),
               "producer": {"kind": "DETERMINISTIC_ANNOTATION", "actor": "annotator"},
               "annotation": annotation}
    review = {"schema": "current_news_context_review/2", "decision": "CONTEXT_ACCEPTED",
              "independent": True, "reviewer": "independent control reviewer",
              "capture_sha256": NV.current_binding(capture), "producer_kind": "DETERMINISTIC_ANNOTATION",
              "reviewed_utc": now.isoformat(), "checks": ["full_row", "producer_origin", "date_roles",
              "quantities_units_baselines", "source_predictions_separate_from_aegis_hypotheses"]}
    return item, capture, review, (now + timedelta(seconds=1)).isoformat()


def reviewed(capture, review):
    review["capture_sha256"] = NV.current_binding(capture)
    review["producer_kind"] = capture["producer"]["kind"]


def admit(item, capture, review, cutoff, **kwargs):
    return NV.admit_context(item, capture, semantic_review=review, cutoff_utc=cutoff, **kwargs)


def test_reviewed_deterministic_context_has_no_numerical_or_native_authority():
    item, capture, review, cutoff = control()
    result = admit(item, capture, review, cutoff)
    assert result["status"] == "SOURCE_GROUNDED_CONTEXT_ONLY"
    assert result["producer_kind"] == "DETERMINISTIC_ANNOTATION"
    assert not any(result[k] for k in ("native_call_evidence_bound", "forecast_authority",
                                      "eligible_for_existing_shadow_v0", "ranking_authority", "sizing_authority"))
    assert result["operative_event_date"] is None


def test_opt_in_caller_never_initiates_paid_call_and_never_returns_native_rows():
    item, capture, review, cutoff = control()
    meter = WD.Meter(0, llm=lambda *a, **k: pytest.fail("context must not call model"))
    pending = WD.extract_current_item(item, meter, cache={}, cutoff_utc=cutoff, stage_cap=0,
                                      contract_version=WD.CURRENT_CONTEXT_VERSION)
    assert pending["status"] == "REFUSED" and meter.calls == 0
    result = WD.extract_current_item(item, meter, cache={}, cutoff_utc=cutoff, stage_cap=0,
                                    contract_version=WD.CURRENT_CONTEXT_VERSION,
                                    context_capture=capture, semantic_review=review)
    assert result["rows"] == [] and result["context_rows"] == [capture["annotation"]]
    assert meter.calls == 0


@pytest.mark.parametrize("bad", ["raw_reply", "user_prompt", "served_model"])
def test_deterministic_capture_cannot_look_like_wire_evidence(bad):
    item, capture, review, cutoff = control()
    capture[bad] = "handwritten"
    reviewed(capture, review)
    with pytest.raises(NV.SourceValidationError, match="capture_shape"):
        admit(item, capture, review, cutoff)


def test_computed_template_and_forged_native_label_are_not_call_proof():
    item, capture, review, cutoff = control()
    capture["producer"] = {"kind": "NATIVE_INFERENCE", "actor": "annotator", "call_id": "invented",
                           "provider": "hosted", "served_model": "claimed", "receipt_sha256": "template"}
    reviewed(capture, review)
    with pytest.raises(NV.SourceValidationError, match="returned_evidence"):
        admit(item, capture, review, cutoff)


@pytest.mark.parametrize("path,value,reason", [
    ("source_sha256", "wrong", "source_or_identity"),
    ("cache_key", "wrong", "source_or_identity"),
    ("completed_utc", "2099-01-01T00:00:00+00:00", "clock"),
])
def test_source_and_clock_drift_fail_even_after_fresh_review(path, value, reason):
    item, capture, review, cutoff = control()
    capture[path] = value; reviewed(capture, review)
    with pytest.raises(NV.SourceValidationError, match=reason):
        admit(item, capture, review, cutoff)


def test_unsupported_quantity_and_detached_quantity_fail():
    item, capture, review, cutoff = control()
    capture["annotation"]["facts"]["numbers"] = ["999"]
    reviewed(capture, review)
    with pytest.raises(NV.SourceValidationError, match="unsupported_evidence"):
        admit(item, capture, review, cutoff)
    capture["annotation"]["facts"]["numbers"] = ["12"]
    capture["annotation"]["facts"]["evidence_spans"] = ["Issuer"]
    reviewed(capture, review)
    with pytest.raises(NV.SourceValidationError, match="quantity_without_fact_witness"):
        admit(item, capture, review, cutoff)


@pytest.mark.parametrize("entity", [42, ["Issuer"], {"name": "Issuer"}])
def test_malformed_factual_entity_returns_typed_refusal(entity):
    item, capture, review, cutoff = control()
    capture["annotation"]["facts"]["entity"] = entity
    reviewed(capture, review)
    result = WD.extract_current_item(item, WD.Meter(0), cache={}, cutoff_utc=cutoff,
                                    stage_cap=0, contract_version=WD.CURRENT_CONTEXT_VERSION,
                                    context_capture=capture, semantic_review=review)
    assert result["status"] == "REFUSED"
    assert result["reason"] == "context_invalid_factual_entity"
    assert result["rows"] == result["context_rows"] == []
    assert result["capture"] is capture


@pytest.mark.parametrize("change,reason", [
    ({"role": "operative"}, "date_role"),
    ({"value": "2026-10-16 14:00:00"}, "date_witness"),
    ({"timezone": "UTC"}, "date_witness"),
    ({"timezone": None}, "timezone_missing"),
])
def test_schedule_role_precision_and_timezone_not_inferred(change, reason):
    item, capture, review, cutoff = control()
    capture["annotation"]["dates"][0].update(change); reviewed(capture, review)
    with pytest.raises(NV.SourceValidationError, match=reason):
        admit(item, capture, review, cutoff)


def test_publication_date_is_retained_without_inventing_UTC_hour():
    item, capture, review, cutoff = control()
    capture["annotation"]["dates"] = [{"role": "publication", "value": "2026/10/08",
        "precision": "day", "timezone": None, "witness": "Issued on: 2026/10/08."},
        {"role": "reporting_period", "value": "September 2026", "precision": "month",
         "timezone": None, "witness": "Revenue was USD 12 million in September 2026."}]
    reviewed(capture, review)
    assert admit(item, capture, review, cutoff)["operative_event_date"] is None
    assert item.published_utc is None


@pytest.mark.parametrize("field,value", [("checks", [{}]), ("checks", False),
                                       ("reviewer", "annotator"), ("reviewed_utc", "2099-01-01T00:00:00+00:00")])
def test_malformed_or_nonindependent_context_review_fails(field, value):
    item, capture, review, cutoff = control()
    review[field] = value
    with pytest.raises(NV.SourceValidationError):
        admit(item, capture, review, cutoff)


def test_publication_day_cannot_be_taken_from_future_schedule():
    item, capture, review, cutoff = control()
    capture["annotation"]["dates"] = [{"role": "publication", "value": "2099-01-01",
        "precision": "day", "timezone": None, "witness": "2099-01-01"}]
    # Future date is present in a synthetic source, but is not usable publication metadata.
    item.text += " 2099-01-01"
    capture["cache_key"] = WD.context_cache_key(item)
    capture["source_sha256"] = NV.content_sha256(item.title + "\n" + item.text)
    capture["source_item_sha256"] = NV.content_sha256(vars(item))
    reviewed(capture, review)
    with pytest.raises(NV.SourceValidationError, match="future_publication"):
        admit(item, capture, review, cutoff)


def test_aegis_question_cannot_be_reclassified_as_source_prediction():
    item, capture, review, cutoff = control()
    capture["annotation"]["source_predictions"] = [{"subject": "cash", "direction": "up",
        "horizon": "weeks", "who": "management", "speaker": "Issuer management",
        "modality": "prediction", "witness": item.text}]
    reviewed(capture, review)
    with pytest.raises(NV.SourceValidationError, match="detached_claim"):
        admit(item, capture, review, cutoff)


def test_replay_requires_same_source_and_current_independent_review():
    item, capture, review, cutoff = control()
    with pytest.raises(NV.SourceValidationError, match="independent_review"):
        admit(item, capture, None, cutoff)
    capture["annotation"]["aegis_hypotheses"].append("Changed research question")
    with pytest.raises(NV.SourceValidationError, match="independent_review"):
        admit(item, capture, review, cutoff)


def test_legacy_schema6_identity_and_shadow_contract_are_unchanged():
    assert WD.current_extraction_identity() == {
        "version": "source_current_v6_summary_country_priority",
        "system_sha256": "fa6df1221b9327bd47e768068f9eba4c7dba425304641bc104bf47b831e91972"}
    assert WD.shadow_contract()["contract_hash"] == "f3b149ea42311760"
    item, capture, review, cutoff = control()
    meter = WD.Meter(0, llm=lambda *a, **kw: pytest.fail("no model call"))
    with pytest.raises(WD.BudgetExceeded):
        WD.extract_current_item(item, meter, cache={WD.context_cache_key(item): capture},
                                cutoff_utc=cutoff, stage_cap=0)


def native_control():
    item, capture, review, cutoff = control()
    reply = json.dumps(capture["annotation"])
    prompt, _ = WD._item_prompt(item)
    evidence = {"call_id": "SYNTHETIC_CONTROL_CALL", "provider": "synthetic", "served_model": "control",
        "system_sha256": NV.content_sha256(WD.CURRENT_CONTEXT_SYSTEM),
        "user_prompt_sha256": NV.content_sha256(prompt), "raw_reply": reply,
        "started_utc": capture["started_utc"], "completed_utc": capture["completed_utc"],
        "telemetry": {"call_id": "SYNTHETIC_CONTROL_CALL", "provider": "synthetic",
                      "served_model": "control", "status": "OK", "response_sha256": NV.content_sha256(reply)}}
    capture["producer"] = {"kind": "NATIVE_INFERENCE", "actor": "synthetic producer",
                           "call_id": evidence["call_id"], "provider": evidence["provider"],
                           "served_model": evidence["served_model"], "receipt_sha256": NV.content_sha256(evidence)}
    reviewed(capture, review)
    return item, capture, review, cutoff, evidence


def test_bound_native_synthetic_control_is_context_only_not_real_call_qualification():
    item, capture, review, cutoff, evidence = native_control()
    result = admit(item, capture, review, cutoff, native_evidence=evidence)
    assert result["native_call_evidence_bound"] and not result["forecast_authority"]


@pytest.mark.parametrize("field,value,reason", [
    ("call_id", "other", "call_identity"),
    ("user_prompt_sha256", "recomputed other template", "actual_prompt"),
    ("system_sha256", "other", "actual_prompt"),
    ("raw_reply", "{}", "returned_reply"),
    ("started_utc", "2099-01-01T00:00:00+00:00", "call_clock"),
    ("telemetry", {}, "telemetry"),
])
def test_native_returned_proof_mismatch_fails(field, value, reason):
    item, capture, review, cutoff, evidence = native_control()
    evidence[field] = value
    capture["producer"]["receipt_sha256"] = NV.content_sha256(evidence)
    reviewed(capture, review)
    with pytest.raises(NV.SourceValidationError, match=reason):
        admit(item, capture, review, cutoff, native_evidence=evidence)
