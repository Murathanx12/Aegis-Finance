"""Conservative source binding for stored news interpretations; no inference.

Legacy digest caches contain typed paraphrases without model evidence spans.
Binding one to its source is not a semantic validation pass. Such rows may be
inspected as context, but never acquire an operative event date or authority.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime


class SourceValidationError(ValueError):
    pass


def content_sha256(value) -> str:
    """Canonical content pin; strings retain their exact bytes, not a repr."""
    text = value if isinstance(value, str) else json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode()).hexdigest()


def check_current_times(item, *, cutoff_utc: str) -> None:
    cutoff = _time(cutoff_utc)
    if _time(item.first_seen_utc) > cutoff:
        raise SourceValidationError("source_not_known_at_cutoff")
    if item.published_utc and _time(item.published_utc) > cutoff:
        raise SourceValidationError("future_publication")


def current_binding(capture: dict) -> str:
    """Review binds the entire capture, including raw/typed/model/prompt/time."""
    return content_sha256(capture)


def admit_current(item, capture: dict, *, semantic_review: dict | None,
                  cutoff_utc: str) -> dict:
    """CURRENT independent case admission, never a corpus quality certificate.

    Caller supplies an actual independent review receipt, not model testimony.
    Checks bind that decision to every retained field. Exact-span membership is
    a necessary syntax check only; the review must adjudicate full semantics,
    speaker/modality/horizon and quantities/units/comparison baselines.
    """
    from backend.services import world_digest as WD
    check_current_times(item, cutoff_utc=cutoff_utc)
    if not isinstance(capture, dict):
        raise SourceValidationError("current_capture_missing")
    cutoff = _time(cutoff_utc)
    started, completed = _time(capture.get("started_utc")), _time(capture.get("cached_utc"))
    if not _time(item.first_seen_utc) <= started <= completed <= cutoff:
        raise SourceValidationError("current_interpretation_time_invalid")
    if item.published_utc and _time(item.published_utc) > started:
        raise SourceValidationError("current_publication_after_extraction")
    prompt, flagged = WD._item_prompt(item)
    if (capture.get("cache_key") != WD.current_cache_key(item)
            or capture.get("extraction_identity") != WD.current_extraction_identity()
            or capture.get("source_sha256") != content_sha256(item.title + "\n" + item.text)
            or capture.get("source_item_sha256") != content_sha256(vars(item))
            or capture.get("user_prompt") != prompt
            or capture.get("injection_lines_removed") != flagged):
        raise SourceValidationError("current_source_or_prompt_drift")
    if not isinstance(capture.get("extract_model"), str) or not capture["extract_model"].strip():
        raise SourceValidationError("current_served_model_missing")
    if not isinstance(capture.get("raw_reply"), str):
        raise SourceValidationError("current_raw_reply_missing")
    typed = WD.type_current_row(WD.parse_current_reply(capture["raw_reply"]), item)
    if capture.get("typing_refusal") or typed != capture.get("row"):
        raise SourceValidationError("current_raw_or_typed_drift")
    review = semantic_review
    if (not isinstance(review, dict) or review.get("schema") != "current_news_semantic_review/1"
            or review.get("decision") != "FULL_ROW_ACCEPTED"
            or review.get("independent") is not True
            or not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip()
            or review.get("capture_sha256") != current_binding(capture)):
        raise SourceValidationError("current_independent_full_row_review_missing_or_drift")
    reviewed = _time(review.get("reviewed_utc"))
    if not completed <= reviewed <= cutoff:
        raise SourceValidationError("current_review_time_invalid")
    required = {"full_row", "speaker_modality_horizon", "quantities_units_baselines",
                "reporting_date_only_no_inferred_operative_date"}
    checks = review.get("checks")
    if (not isinstance(checks, list) or len(checks) != len(required)
            or any(not isinstance(name, str) for name in checks) or set(checks) != required):
        raise SourceValidationError("current_semantic_review_incomplete")
    indices = review.get("claim_indices")
    if (not isinstance(indices, list) or any(type(index) is not int for index in indices)
            or indices != list(range(len(typed["forward_claims"])))):
        raise SourceValidationError("current_claim_review_incomplete")
    return {"status": "CURRENT_CASE_SEMANTICALLY_ADMITTED_EXPERIMENTAL_ONLY",
            "capture_sha256": current_binding(capture),
            "review_sha256": content_sha256(review), "semantic_grounding_validated": True,
            "operative_event_date": None, "eligible_for_existing_shadow_v0": False}


def _time(value: str) -> datetime:
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise SourceValidationError("missing_or_invalid_information_time") from exc
    if stamp.tzinfo is None:
        raise SourceValidationError("information_time_requires_timezone")
    return stamp


def validate_cached(item, cached: dict, *, cutoff_utc: str) -> dict:
    """Check actual cache identity and source timestamps, without a paid call.

No legacy paraphrase is promoted to SOURCE_GROUNDED. An optional evidence
contract must bind exact source spans; operative/estimated dates are refused
because the legacy extractor never supplied a role-specific date contract.
"""
    from backend.services import world_digest as WD
    cutoff = _time(cutoff_utc)
    if _time(item.first_seen_utc) > cutoff:
        raise SourceValidationError("source_not_known_at_cutoff")
    if item.published_utc and _time(item.published_utc) > cutoff:
        raise SourceValidationError("future_publication")
    if _time(cached.get("cached_utc")) > cutoff:
        raise SourceValidationError("interpretation_not_known_at_cutoff")
    if cached.get("cache_key") != WD.cache_key(item):
        raise SourceValidationError("cache_source_or_prompt_drift")
    raw = cached.get("row")
    if not isinstance(raw, dict) or raw.get("item_id") != item.item_id:
        raise SourceValidationError("cache_item_identity_mismatch")
    typed = WD.type_row(raw, item)
    if typed is None or any(raw.get(k) != v for k, v in typed.items()):
        raise SourceValidationError("cached_type_or_source_metadata_drift")
    source = item.title + "\n" + item.text
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    contract = cached.get("evidence_contract")
    if contract:
        if contract.get("source_sha256") != source_hash:
            raise SourceValidationError("evidence_source_drift")
        for span in contract.get("evidence_spans", []):
            if not isinstance(span, str) or not span or span not in source:
                raise SourceValidationError("unsupported_evidence_span")
        for fact in contract.get("dates", []):
            if fact.get("role") != "reporting" or fact.get("status") != "source_reported":
                raise SourceValidationError("unsupported_operative_or_estimated_event_day")
            # Even reporting dates need an explicit source-bound normalization
            # contract; a date-shaped string is not that contract.
            raise SourceValidationError("reporting_date_normalization_contract_missing")
    if raw.get("event_date") is not None or raw.get("estimated_dates"):
        raise SourceValidationError("unsupported_operative_or_estimated_event_day")
    return {"item_id": item.item_id, "cache_key": cached["cache_key"],
            "source_sha256": source_hash, "source_url": item.url,
            "first_seen_utc": item.first_seen_utc, "published_utc": item.published_utc,
            "cached_utc": cached["cached_utc"], "extract_model": raw.get("extract_model"),
            "status": "BOUND_ONLY", "source_identity_validated": True,
            "semantic_grounding_validated": False, "operative_event_date": None,
            "estimated_event_dates": [], "reason": "legacy typed cache lacks raw reply and role-specific evidence contract"}


def validate_article_facts(reply: dict, source: str, *, source_sha256: str) -> dict:
    """Validate exact spans without guessing which day a settlement occurred.

This bounded contract deliberately supports only unknown action dates. A
reporting/publication stamp is metadata, and cannot fill the operative field.
"""
    if hashlib.sha256(source.encode()).hexdigest() != source_sha256:
        raise SourceValidationError("evidence_source_drift")
    spans = reply.get("evidence_spans")
    if not isinstance(spans, list) or (not reply.get("abstain") and not spans):
        raise SourceValidationError("missing_evidence")
    for span in spans + list(reply.get("numbers") or []):
        if not isinstance(span, str) or not span or span not in source:
            raise SourceValidationError("unsupported_evidence_span")
    if reply.get("entity") and reply["entity"] not in source:
        raise SourceValidationError("unsupported_entity")
    if reply.get("event_date") is not None or reply.get("date_precision") != "unknown":
        raise SourceValidationError("unsupported_operative_event_day")
    return {"status": "SOURCE_SPANS_VALIDATED_ACTION_DATE_UNKNOWN",
            "source_sha256": source_sha256, "event_date": None,
            "semantic_grounding_validated": False,
            "reason": "exact spans only; no full held-out semantic quality pass"}


def _context_dates(dates, source: str, *, cutoff_utc: str) -> None:
    """Witnessed date roles are context, never inferred operative authority."""
    if not isinstance(dates, list):
        raise SourceValidationError("context_invalid_dates")
    for fact in dates:
        if (not isinstance(fact, dict)
                or set(fact) != {"role", "value", "precision", "timezone", "witness"}
                or not isinstance(fact["role"], str) or not isinstance(fact["precision"], str)
                or fact["role"] not in {"publication", "reporting_period", "scheduled_event"}
                or fact["precision"] not in {"day", "month", "quarter", "year", "minute", "second",
                                             "minute_timezone_unresolved"}):
            raise SourceValidationError("context_unsupported_date_role_or_precision")
        value, witness, zone = fact["value"], fact["witness"], fact["timezone"]
        if (not isinstance(value, str) or not value or not isinstance(witness, str)
                or witness not in source or value not in witness
                or (zone is not None and (not isinstance(zone, str) or not zone or zone not in witness))):
            raise SourceValidationError("context_detached_date_witness")
        if fact["precision"] == "minute_timezone_unresolved" and zone is not None:
            raise SourceValidationError("context_invented_date_timezone")
        if fact["role"] == "scheduled_event" and fact["precision"] in {"minute", "second"} and not zone:
            raise SourceValidationError("context_scheduled_timezone_missing")
        if fact["role"] == "scheduled_event" and zone is not None:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
            try:
                ZoneInfo(zone)
                if fact["precision"] in {"minute", "second"}:
                    fmt = "%Y-%m-%d %H:%M" + (":%S" if fact["precision"] == "second" else "")
                    datetime.strptime(value, fmt)
            except (ValueError, ZoneInfoNotFoundError):
                raise SourceValidationError("context_invalid_scheduled_date_or_timezone")
        if fact["role"] == "publication":
            # Never use acquisition time to invent a publication hour/zone.
            formats = ("%Y/%m/%d", "%Y-%m-%d", "%B %d, %Y",
                       "%A, %B %d, %Y - %I:%M%p")
            day = None
            for fmt in formats:
                try:
                    day = datetime.strptime(value, fmt).date()
                    break
                except ValueError:
                    continue
            if day is None or day > _time(cutoff_utc).date():
                raise SourceValidationError("context_invalid_or_future_publication_date")


def _context_native_evidence(item, capture: dict, evidence: dict | None) -> None:
    """Bind retained returned-call metadata; no receipt is manufactured here.

    This is not authentication of arbitrary caller-provided dictionaries. The
    independent producer-origin review must inspect actual transport/telemetry
    provenance. Missing call IDs in today's producer remain a refusal.
    """
    from backend.services import world_digest as WD
    producer = capture["producer"]
    if not isinstance(evidence, dict) or producer.get("receipt_sha256") != content_sha256(evidence):
        raise SourceValidationError("context_native_returned_evidence_missing_or_drift")
    for field in ("call_id", "provider", "served_model"):
        if (not isinstance(evidence.get(field), str) or not evidence[field].strip()
                or producer.get(field) != evidence[field]):
            raise SourceValidationError("context_native_call_identity_missing_or_drift")
    prompt, _ = WD._item_prompt(item)
    if (evidence.get("system_sha256") != content_sha256(WD.CURRENT_CONTEXT_SYSTEM)
            or evidence.get("user_prompt_sha256") != content_sha256(prompt)):
        raise SourceValidationError("context_native_actual_prompt_drift")
    if (evidence.get("started_utc") != capture["started_utc"]
            or evidence.get("completed_utc") != capture["completed_utc"]):
        raise SourceValidationError("context_native_call_clock_drift")
    reply = evidence.get("raw_reply")
    if not isinstance(reply, str) or WD.parse_current_reply(reply) != capture["annotation"]:
        raise SourceValidationError("context_native_returned_reply_drift")
    telemetry = evidence.get("telemetry")
    if (not isinstance(telemetry, dict) or telemetry.get("status") != "OK"
            or any(telemetry.get(k) != evidence[k] for k in ("call_id", "provider", "served_model"))
            or telemetry.get("response_sha256") != content_sha256(reply)):
        raise SourceValidationError("context_native_telemetry_missing_or_drift")


def admit_context(item, capture: dict | None, *, semantic_review: dict | None,
                  cutoff_utc: str, native_evidence: dict | None = None) -> dict:
    """Versioned source-grounded context admission, with no economic authority."""
    from backend.services import world_digest as WD
    check_current_times(item, cutoff_utc=cutoff_utc)
    fields = {"schema", "cache_key", "extraction_identity", "source_sha256",
              "source_item_sha256", "started_utc", "completed_utc", "producer", "annotation"}
    if (not isinstance(capture, dict) or set(capture) != fields
            or capture.get("schema") != "current_news_context_capture/2"):
        raise SourceValidationError("context_capture_shape_or_version")
    if (capture["cache_key"] != WD.context_cache_key(item)
            or capture["extraction_identity"] != WD.context_extraction_identity()
            or capture["source_sha256"] != content_sha256(item.title + "\n" + item.text)
            or capture["source_item_sha256"] != content_sha256(vars(item))):
        raise SourceValidationError("context_source_or_identity_drift")
    started, completed, cutoff = map(_time, (capture["started_utc"], capture["completed_utc"], cutoff_utc))
    if not _time(item.first_seen_utc) <= started <= completed <= cutoff:
        raise SourceValidationError("context_capture_clock_invalid")
    if item.published_utc and _time(item.published_utc) > started:
        raise SourceValidationError("context_publication_after_extraction")
    annotation = capture["annotation"]
    if (not isinstance(annotation, dict)
            or set(annotation) != {"facts", "dates", "source_predictions", "aegis_hypotheses"}
            or not isinstance(annotation["facts"], dict)
            or not isinstance(annotation["source_predictions"], list)
            or not isinstance(annotation["aegis_hypotheses"], list)
            or any(not isinstance(q, str) or not q.strip() for q in annotation["aegis_hypotheses"])):
        raise SourceValidationError("context_annotation_shape")
    source = item.title + "\n" + item.text
    facts = annotation["facts"]
    if (set(facts) != {"entity", "event_date", "date_precision", "evidence_spans", "numbers", "abstain"}
            or type(facts["abstain"]) is not bool
            or not isinstance(facts.get("evidence_spans"), list)
            or not isinstance(facts.get("numbers", []), list)):
        raise SourceValidationError("context_invalid_factual_collections")
    if facts["entity"] is not None and not isinstance(facts["entity"], str):
        raise SourceValidationError("context_invalid_factual_entity")
    validate_article_facts(annotation["facts"], source, source_sha256=capture["source_sha256"])
    if any(not any(number in span for span in annotation["facts"]["evidence_spans"])
           for number in annotation["facts"].get("numbers", [])):
        raise SourceValidationError("context_quantity_without_fact_witness")
    _context_dates(annotation["dates"], source, cutoff_utc=cutoff_utc)
    WD.type_current_row({"event_type": "other", "novelty": "new_fact",
                         "forward_claims": annotation["source_predictions"]}, item)
    producer = capture["producer"]
    if not isinstance(producer, dict) or not isinstance(producer.get("actor"), str) or not producer["actor"].strip():
        raise SourceValidationError("context_producer_missing")
    kind = producer.get("kind")
    if kind == "DETERMINISTIC_ANNOTATION":
        if set(producer) != {"kind", "actor"} or native_evidence is not None:
            raise SourceValidationError("context_deterministic_native_misattribution")
    elif kind == "NATIVE_INFERENCE":
        if set(producer) != {"kind", "actor", "call_id", "provider", "served_model", "receipt_sha256"}:
            raise SourceValidationError("context_native_producer_shape")
        _context_native_evidence(item, capture, native_evidence)
    else:
        raise SourceValidationError("context_unknown_producer_kind")
    review = semantic_review
    required = {"full_row", "producer_origin", "date_roles", "quantities_units_baselines",
                "source_predictions_separate_from_aegis_hypotheses"}
    if (not isinstance(review, dict) or review.get("schema") != "current_news_context_review/2"
            or review.get("decision") != "CONTEXT_ACCEPTED" or review.get("independent") is not True
            or not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip()
            or review["reviewer"] == producer["actor"]
            or review.get("capture_sha256") != current_binding(capture)
            or review.get("producer_kind") != kind):
        raise SourceValidationError("context_independent_review_missing_or_drift")
    checks = review.get("checks")
    if (not isinstance(checks, list) or len(checks) != len(required)
            or any(not isinstance(check, str) for check in checks) or set(checks) != required):
        raise SourceValidationError("context_review_incomplete")
    if not completed <= _time(review.get("reviewed_utc")) <= cutoff:
        raise SourceValidationError("context_review_clock_invalid")
    return {"status": "SOURCE_GROUNDED_CONTEXT_ONLY", "capture_sha256": current_binding(capture),
            "review_sha256": content_sha256(review), "producer_kind": kind,
            "native_call_evidence_bound": kind == "NATIVE_INFERENCE",
            "semantic_grounding_validated": True, "operative_event_date": None,
            "eligible_for_existing_shadow_v0": False, "forecast_authority": False,
            "ranking_authority": False, "sizing_authority": False}
