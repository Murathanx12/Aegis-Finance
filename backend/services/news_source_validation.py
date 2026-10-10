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
