"""Pure metadata eligibility for an exact transcript version; no intake or I/O.

``eligible`` covers this temporal/provenance check only, not H19 admission,
rights, issuer/security linkage, price availability or research validity.
Provenance references are caller-supplied evidence, not authenticated here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import re


@dataclass(frozen=True)
class SourceVersion:
    source_id: str
    record_id: str
    version_id: str
    content_sha256: str
    evidence_ref: str


@dataclass(frozen=True)
class Clock:
    at: str | None = None
    source_field: str | None = None
    evidence_ref: str | None = None
    source_version: SourceVersion | None = None
    basis: str | None = None


@dataclass(frozen=True)
class TranscriptMetadata:
    version: SourceVersion
    creation: Clock = Clock()
    event: Clock = Clock()
    publication: Clock = Clock()
    observed: Clock = Clock()
    revision: Clock = Clock()
    supersedes_version_id: str | None = None


@dataclass(frozen=True)
class Eligibility:
    status: str
    reasons: tuple[str, ...]
    historical_eligible: bool
    usable_from: str | None
    decision_at: str
    metadata: TranscriptMetadata
    normalized_clocks: tuple[tuple[str, str | None], ...]
    scope: str = 'transcript_version_temporal_provenance_only'

    def to_dict(self) -> dict:
        result = asdict(self)
        result['normalized_clocks'] = dict(self.normalized_clocks)
        return result


_BASES = {
    'creation': {'source_metadata', 'archival_receipt'},
    'event': {'source_metadata', 'archival_receipt'},
    'publication': {'source_metadata', 'archival_receipt'},
    'observed': {'collector_observation', 'archival_receipt', 'acquisition'},
    'revision': {'source_metadata', 'archival_receipt'},
}


def _instant(value: str) -> datetime:
    if not isinstance(value, str) or 'T' not in value:
        raise ValueError('Timestamp requires a time and explicit timezone')
    instant = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError('Timestamp requires a timezone')
    return instant.astimezone(timezone.utc)


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 2048


def validate_availability(record: TranscriptMetadata, *, decision_at: str) -> Eligibility:
    """Retain unknowns and validate supplied evidence without inventing clocks.

    Exact-version publication plus non-acquisition observation by the decision
    clock can pass historical eligibility. A valid local acquisition/observation
    alone bounds prospective use; it never backdates historical availability.
    Future or inconsistent version evidence returns unknown with refusal reasons.
    This function does not select the latest version or modify earlier results.
    """
    if not isinstance(record, TranscriptMetadata):
        raise TypeError('Expected TranscriptMetadata, without text or extra fields')
    reasons: list[str] = []
    errors: list[str] = []
    clocks: dict[str, datetime | None] = {}
    try:
        decision = _instant(decision_at)
    except (ValueError, TypeError, OverflowError):
        decision = None
        errors.append('invalid_decision_clock')
    version = record.version
    if not isinstance(version, SourceVersion) or not all(_nonempty(getattr(version, key))
            for key in ('source_id', 'record_id', 'version_id', 'evidence_ref')):
        errors.append('missing_source_version_provenance')
    if not isinstance(version, SourceVersion) or not isinstance(version.content_sha256, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', version.content_sha256):
        errors.append('invalid_source_content_digest')
    if record.supersedes_version_id is not None:
        if not _nonempty(record.supersedes_version_id):
            errors.append('invalid_supersedes_version')
        elif isinstance(version, SourceVersion) and record.supersedes_version_id == version.version_id:
            errors.append('self_superseding_version')
    for name, bases in _BASES.items():
        clock = getattr(record, name)
        clocks[name] = None
        if not isinstance(clock, Clock):
            errors.append(name + '_invalid_clock_metadata')
            continue
        if clock.at is None:
            reasons.append(name + '_unknown')
            continue
        try:
            clocks[name] = _instant(clock.at)
        except (ValueError, TypeError, OverflowError):
            errors.append(name + '_invalid_or_ambiguous_clock')
            continue
        if not _nonempty(clock.source_field) or not _nonempty(clock.evidence_ref):
            errors.append(name + '_missing_provenance')
        if not isinstance(version, SourceVersion) or clock.source_version != version:
            errors.append(name + '_source_version_mismatch')
        if not isinstance(clock.basis, str) or clock.basis not in bases:
            errors.append(name + '_invalid_evidence_basis')
        if name == 'publication' and clock.basis == 'acquisition':
            errors.append('acquisition_cannot_establish_publication')
        if decision is not None and clocks[name] > decision:
            if name == 'event':
                reasons.append('event_after_decision_not_an_availability_clock')
            else:
                errors.append(name + '_after_decision')
    # A particular version cannot be public or observed before it exists.
    for origin in ('creation', 'revision'):
        for later in ('publication', 'observed'):
            if clocks[origin] is not None and clocks[later] is not None and clocks[origin] > clocks[later]:
                errors.append(origin + '_after_' + later)
    if clocks['creation'] is not None and clocks['revision'] is not None and clocks['revision'] < clocks['creation']:
        errors.append('revision_before_creation')

    status, usable = 'unknown', None
    if not errors:
        observed, publication = clocks['observed'], clocks['publication']
        if observed is not None:
            if record.observed.basis == 'acquisition':
                reasons.append('acquisition_not_historical_availability')
            if publication is not None and record.observed.basis != 'acquisition':
                status = 'eligible'
                usable = max(publication, observed).isoformat()
                reasons.append('version_public_and_observed_by_decision')
            else:
                status = 'prospective-only'
                usable = max(t for t in (publication, observed) if t is not None).isoformat()
                reasons.append('use_only_from_bound_observation_no_historical_claim')
        else:
            reasons.append('no_version_bound_observation')
    return Eligibility(status, tuple(errors + reasons), status == 'eligible', usable,
        decision_at, record, tuple((name, at.isoformat() if at is not None else None)
                                  for name, at in clocks.items()))
