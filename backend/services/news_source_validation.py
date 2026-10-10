"""Conservative source binding for stored news interpretations; no inference.

Legacy digest caches contain typed paraphrases without model evidence spans.
Binding one to its source is not a semantic validation pass. Such rows may be
inspected as context, but never acquire an operative event date or authority.
"""
from __future__ import annotations

import hashlib
from datetime import datetime


class SourceValidationError(ValueError):
    pass


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
