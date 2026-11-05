"""Bounded, offline provisional exposure review over caller-supplied evidence.

No collector, issuer inference, portfolio action, provider, or delivery lives here.
Input clocks and witness hashes are caller attestations, not a verified PIT manifest.
The only I/O seam is ``write_receipt`` to an existing, caller-chosen directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any


MAX_INPUT_SOURCES = 512
MAX_SOURCE_BYTES = 262_144
MAX_TOTAL_SOURCE_BYTES = 4_194_304
MAX_EDGES = 512
MAX_HOLDINGS = 256
MAX_SELECTED_SOURCES = 128
MAX_RECEIPT_BYTES = 1_048_576

_CLOCK = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9:._-]{0,127}\Z")
_SYMBOL = re.compile(r"(?:US|EU|HK|CN|ID|IN|JP|KR|TW):[A-Z0-9][A-Z0-9.&^=-]{0,31}\Z")
_CIK = re.compile(r"cik:0*([1-9][0-9]{0,9})\Z")
_ISSUER_HASH = re.compile(r"issuer:[0-9a-f]{64}\Z")


class ReviewRefused(ValueError):
    """A sanitized, fail-closed input or receipt refusal."""


class _BuiltReceipt(dict):
    """A builder result sealed to its original bytes for the write boundary."""

    __slots__ = ("_sealed_bytes",)

    def __init__(self, value: dict[str, Any]):
        super().__init__(value)
        self._sealed_bytes = _canonical(value)


@dataclass(frozen=True)
class SourceProof:
    source_sha256: str
    known_at_utc: str
    witness_sha256: str


@dataclass(frozen=True)
class SourceItem:
    source_key: str
    event_key: str
    payload: bytes
    first_seen_utc: str
    version_seen_utc: str
    published_utc: str | None
    provenance: SourceProof
    kind: str = "ARTICLE"


@dataclass(frozen=True)
class IssuerEdge:
    source_key: str
    source_sha256: str
    issuer_id: str
    symbol: str | None
    relation: str
    basis: str
    known_at_utc: str
    evidence_sha256: str


@dataclass(frozen=True)
class HoldingsSnapshot:
    as_of_utc: str
    known_at_utc: str
    symbols: tuple[str, ...]
    evidence_sha256: str
    complete: bool


def _refuse(code: str) -> None:
    raise ReviewRefused(code)


def _clock(value: str) -> datetime:
    if not isinstance(value, str) or not _CLOCK.fullmatch(value):
        _refuse("INVALID_UTC_CLOCK")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _refuse("INVALID_UTC_CLOCK")
    if parsed.utcoffset().total_seconds() != 0:
        _refuse("INVALID_UTC_CLOCK")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash(value: str) -> str:
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        _refuse("INVALID_PROVENANCE_HASH")
    return value


def _key(value: str) -> str:
    if not isinstance(value, str) or not _KEY.fullmatch(value):
        _refuse("INVALID_OPAQUE_KEY")
    return value


def _symbol(value: str) -> str:
    if not isinstance(value, str) or not _SYMBOL.fullmatch(value):
        _refuse("INVALID_SYMBOL")
    return value


def _issuer(value: str) -> str:
    if not isinstance(value, str) or len(value) > 128:
        _refuse("INVALID_ISSUER_ID")
    cik = _CIK.fullmatch(value)
    if cik:
        return f"cik:{int(cik.group(1))}"
    if _ISSUER_HASH.fullmatch(value):
        return value
    _refuse("INVALID_ISSUER_ID")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _stable_id(namespace: str, value: str) -> str:
    return _sha(f"{namespace}\0{value}".encode("ascii"))


def _id(namespace: str, value: str, registry: dict[tuple[str, str], str]) -> str:
    identifier = _stable_id(namespace, value)
    previous = registry.setdefault((namespace, identifier), value)
    if previous != value:
        _refuse("ID_COLLISION")
    return identifier


def _bounded_sequence(value: Any, cap: int) -> list[Any]:
    if not isinstance(value, (list, tuple)):
        _refuse("INVALID_BOUNDED_INPUT")
    if len(value) > cap:
        _refuse("INPUT_CAP")
    return list(value)


def _source(raw: SourceItem, review: datetime) -> dict[str, Any]:
    if not isinstance(raw, SourceItem):
        _refuse("INVALID_SOURCE")
    source_key, event_key = _key(raw.source_key), _key(raw.event_key)
    if raw.kind not in ("ARTICLE", "FILING", "REFERENCE_PAGE"):
        _refuse("INVALID_SOURCE_KIND")
    if not isinstance(raw.payload, bytes) or not raw.payload:
        _refuse("MISSING_SOURCE_BYTES")
    if len(raw.payload) > MAX_SOURCE_BYTES:
        _refuse("SOURCE_BYTE_CAP")
    if not isinstance(raw.provenance, SourceProof):
        _refuse("MISSING_SOURCE_PROVENANCE")
    sha = _hash(raw.provenance.source_sha256)
    _hash(raw.provenance.witness_sha256)
    if _sha(raw.payload) != sha:
        _refuse("SOURCE_HASH_MISMATCH")
    first, version, known = (_clock(raw.first_seen_utc), _clock(raw.version_seen_utc),
                             _clock(raw.provenance.known_at_utc))
    published = _clock(raw.published_utc) if raw.published_utc is not None else None
    if first > version or version > known or known > review or (published is not None and published > version):
        _refuse("INVALID_SOURCE_TIMELINE")
    return {"source_key": source_key, "event_key": event_key, "source_sha256": sha,
            "first": first, "version": version, "known": known,
            "published": published, "witness_sha256": raw.provenance.witness_sha256,
            "kind": raw.kind}


def _edge(raw: IssuerEdge, supplied: dict[tuple[str, str], datetime],
          review: datetime) -> dict[str, Any]:
    if not isinstance(raw, IssuerEdge):
        _refuse("INVALID_EDGE")
    key, sha = _key(raw.source_key), _hash(raw.source_sha256)
    if (key, sha) not in supplied:
        _refuse("MISSING_EDGE_SOURCE")
    issuer = _issuer(raw.issuer_id)
    _hash(raw.evidence_sha256)
    known = _clock(raw.known_at_utc)
    if known < supplied[(key, sha)] or known > review:
        _refuse("INVALID_EDGE_TIMELINE")
    if (not isinstance(raw.relation, str) or len(raw.relation) > 32
            or not isinstance(raw.basis, str) or len(raw.basis) > 32):
        _refuse("INVALID_EDGE_QUALIFICATION")
    allowed = {"DIRECT_ISSUER": {"FULL_ISSUER_SUBJECT"},
               "INDIRECT_CANDIDATE": {"REVIEWED_MECHANISM"},
               "DISCOVERY_CONTEXT": {"QUEUE_CONTEXT", "TICKER_ONLY"},
               "ISSUER_CANDIDATE": {"SEC_CIK"}}
    if raw.relation == "DIRECT_ISSUER" and raw.basis not in allowed["DIRECT_ISSUER"]:
        _refuse("UNQUALIFIED_DIRECT_EDGE")
    if raw.relation not in allowed or raw.basis not in allowed[raw.relation]:
        _refuse("INVALID_EDGE_QUALIFICATION")
    if raw.relation == "ISSUER_CANDIDATE":
        # A CIK names an issuer, not a dated listing or held security. Even an
        # asserted ticker alongside it must not become a held-symbol join.
        if raw.symbol is not None:
            _refuse("UNQUALIFIED_ISSUER_CANDIDATE")
        if not _CIK.fullmatch(raw.issuer_id):
            _refuse("INVALID_EDGE_QUALIFICATION")
        symbol = None
    else:
        symbol = _symbol(raw.symbol)
    return {"source_key": key, "source_sha256": sha, "issuer_id": issuer,
            "symbol": symbol, "relation": raw.relation, "basis": raw.basis,
            "known": known, "evidence_sha256": raw.evidence_sha256}


def _holdings(raw: HoldingsSnapshot | None, review: datetime,
              cutoff: datetime) -> tuple[dict[str, Any], set[str] | None]:
    if raw is None:
        return {"status": "UNKNOWN", "as_of_utc": None, "known_at_utc": None,
                "evidence_sha256": None, "symbol_count": None}, None
    if not isinstance(raw, HoldingsSnapshot):
        _refuse("INVALID_HOLDINGS")
    if type(raw.complete) is not bool:
        _refuse("INVALID_COMPLETENESS")
    symbols = _bounded_sequence(raw.symbols, MAX_HOLDINGS)
    normalized = {_symbol(symbol) for symbol in symbols}
    if len(normalized) != len(symbols):
        _refuse("DUPLICATE_HELD_SYMBOL")
    evidence = _hash(raw.evidence_sha256)
    as_of, known = _clock(raw.as_of_utc), _clock(raw.known_at_utc)
    if as_of > known or known > review:
        _refuse("INVALID_HOLDINGS_TIMELINE")
    status = "HOLDINGS_AFTER_CUTOFF" if known > cutoff else ("COMPLETE" if raw.complete else "PARTIAL")
    return {"status": status, "as_of_utc": _iso(as_of), "known_at_utc": _iso(known),
            "evidence_sha256": evidence, "symbol_count": len(normalized)}, (
                normalized if known <= cutoff else None)


def _reason_codes(positive: bool, reference: bool, issuer_only: bool,
                  held_status: str, coverage_partial: bool) -> list[str]:
    if reference:
        return ["REFERENCE_ONLY"]
    if positive:
        return ["QUALIFIED_HELD_EDGE_FOR_REVIEW"]
    unresolved = []
    if issuer_only:
        unresolved.append("ISSUER_SECURITY_UNRESOLVED")
    if held_status == "UNKNOWN":
        unresolved.append("HOLDINGS_UNKNOWN")
    elif held_status == "HOLDINGS_AFTER_CUTOFF":
        unresolved.append("HOLDINGS_AFTER_CUTOFF")
    elif held_status == "PARTIAL":
        unresolved.append("PARTIAL_HOLDINGS_UNKNOWN")
    if coverage_partial:
        unresolved.append("PARTIAL_INPUT_COVERAGE_UNKNOWN")
    return unresolved or ["NO_QUALIFIED_HELD_EDGE"]


def build_review(*, sources: list[SourceItem] | tuple[SourceItem, ...],
                 issuer_edges: list[IssuerEdge] | tuple[IssuerEdge, ...],
                 holdings: HoldingsSnapshot | None, review_time_utc: str,
                 source_cutoff_utc: str, input_complete: bool,
                 max_sources: int = 64, upstream_state: str = "UNKNOWN",
                 upstream_exit_code: int | None = None) -> dict[str, Any]:
    """Return sanitized JSON-ready review; no I/O, model, or issuer discovery."""
    review, cutoff = _clock(review_time_utc), _clock(source_cutoff_utc)
    if review < cutoff:
        _refuse("REVIEW_BEFORE_CUTOFF")
    if type(input_complete) is not bool:
        _refuse("INVALID_COMPLETENESS")
    if type(max_sources) is not int or not 1 <= max_sources <= MAX_SELECTED_SOURCES:
        _refuse("INPUT_CAP")
    if upstream_state == "UNKNOWN" and upstream_exit_code is None:
        pass
    elif upstream_state == "BUDGET_REFUSED" and type(upstream_exit_code) is int and upstream_exit_code > 0:
        pass
    else:
        _refuse("INVALID_UPSTREAM_STATUS")
    inputs = _bounded_sequence(sources, MAX_INPUT_SOURCES)
    if not inputs:
        _refuse("MISSING_SOURCE")
    edges_in = _bounded_sequence(issuer_edges, MAX_EDGES)
    total_bytes = 0
    parsed = []
    for item in inputs:
        parsed_item = _source(item, review)
        total_bytes += len(item.payload)
        if total_bytes > MAX_TOTAL_SOURCE_BYTES:
            _refuse("SOURCE_BYTE_CAP")
        parsed.append(parsed_item)
    supplied: dict[tuple[str, str], datetime] = {}
    for item in parsed:
        identity = (item["source_key"], item["source_sha256"])
        current = supplied.get(identity)
        if current is None or item["known"] < current:
            supplied[identity] = item["known"]
    edges = [_edge(raw, supplied, review) for raw in edges_in]
    held_meta, held = _holdings(holdings, review, cutoff)

    eligible = [item for item in parsed if item["known"] <= cutoff]
    future_sources = len(parsed) - len(eligible)
    future_edges = sum(edge["known"] > cutoff for edge in edges)
    # Eligibility precedes all semantic collision checks: future knowledge cannot
    # rewrite or poison an earlier review.
    identities: dict[str, str] = {}
    versions: dict[tuple[str, str], dict[str, Any]] = {}
    at_clock: dict[tuple[str, datetime], str] = {}
    duplicate_versions = 0
    for item in eligible:
        key = item["source_key"]
        prior_event = identities.setdefault(key, item["event_key"])
        if prior_event != item["event_key"]:
            _refuse("SOURCE_EVENT_COLLISION")
        clock_key = (key, item["version"])
        prior_sha = at_clock.setdefault(clock_key, item["source_sha256"])
        if prior_sha != item["source_sha256"]:
            _refuse("SOURCE_VERSION_CLOCK_COLLISION")
        identity = (key, item["source_sha256"])
        prior = versions.get(identity)
        if prior is None:
            versions[identity] = item
        else:
            if any(item[field] != prior[field] for field in ("event_key", "first", "published", "kind")):
                _refuse("SOURCE_VERSION_METADATA_COLLISION")
            duplicate_versions += 1
            if (item["known"], item["witness_sha256"]) < (prior["known"], prior["witness_sha256"]):
                versions[identity] = item

    by_key: dict[str, list[dict[str, Any]]] = {}
    for item in versions.values():
        by_key.setdefault(item["source_key"], []).append(item)
    chosen = []
    for key, available in by_key.items():
        available.sort(key=lambda item: (item["version"], item["known"], item["source_sha256"]))
        latest = available[-1]
        chosen.append((latest, sorted(item["source_sha256"] for item in available[:-1])))
    chosen.sort(key=lambda pair: (pair[0]["known"], pair[0]["source_key"]))
    omitted = max(0, len(chosen) - max_sources)
    chosen = chosen[:max_sources]
    registry: dict[tuple[str, str], str] = {}
    selected: dict[tuple[str, str], tuple[str, str]] = {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item, superseded in chosen:
        source_id = _id("source", item["source_key"], registry)
        event_id = _id("event", item["event_key"], registry)
        selected[(item["source_key"], item["source_sha256"])] = (item["event_key"], source_id)
        grouped.setdefault(item["event_key"], []).append({
            "source_id": source_id, "version_id": _sha(f"version\0{source_id}\0{item['source_sha256']}".encode()),
            "source_sha256": item["source_sha256"], "kind": item["kind"],
            "first_seen_utc": _iso(item["first"]), "version_seen_utc": _iso(item["version"]),
            "published_utc": _iso(item["published"]) if item["published"] else None,
            "proof_known_at_utc": _iso(item["known"]),
            "proof_witness_sha256": item["witness_sha256"],
            "superseded_version_hashes": superseded})

    joined: dict[str, list[dict[str, Any]]] = {key: [] for key in grouped}
    seen_edges = set()
    direct_issuers: dict[str, str] = {}
    edges_not_joined = 0
    for edge in edges:
        identity = (edge["source_key"], edge["source_sha256"])
        if edge["known"] > cutoff:
            continue
        if identity not in selected:
            edges_not_joined += 1
            continue
        event_key, source_id = selected[identity]
        token = (identity, edge["issuer_id"], edge["symbol"], edge["relation"],
                 edge["basis"], edge["known"], edge["evidence_sha256"])
        if token in seen_edges:
            continue
        seen_edges.add(token)
        if edge["relation"] == "DIRECT_ISSUER":
            previous = direct_issuers.setdefault(edge["symbol"], edge["issuer_id"])
            if previous != edge["issuer_id"]:
                _refuse("SYMBOL_ISSUER_COLLISION")
        match = ("UNKNOWN" if edge["relation"] == "ISSUER_CANDIDATE" or held is None
                 or (held_meta["status"] == "PARTIAL" and edge["symbol"] not in held)
                 else edge["symbol"] in held)
        joined[event_key].append({"source_id": source_id, "source_sha256": edge["source_sha256"],
                                  "issuer_id": edge["issuer_id"], "symbol": edge["symbol"],
                                  "relation": edge["relation"], "basis": edge["basis"],
                                  "known_at_utc": _iso(edge["known"]),
                                  "evidence_sha256": edge["evidence_sha256"],
                                  "held_snapshot_match": match})

    coverage_partial = not input_complete or omitted > 0
    coverage = {"status": "PARTIAL" if coverage_partial else "COMPLETE",
                "caller_input_complete": input_complete, "input_source_rows": len(inputs),
                "future_source_versions_excluded": future_sources,
                "future_edges_excluded": future_edges, "duplicate_versions": duplicate_versions,
                "sources_omitted_by_cap": omitted, "edges_not_joined": edges_not_joined}

    groups = []
    for event_key in sorted(grouped):
        sources_out = sorted(grouped[event_key], key=lambda item: item["source_id"])
        edges_out = sorted(joined[event_key], key=lambda item: (
            item["source_id"], item["symbol"] or "", item["issuer_id"], item["relation"],
            item["basis"], item["known_at_utc"], item["evidence_sha256"]))
        reference = all(source["kind"] == "REFERENCE_PAGE" for source in sources_out)
        direct = sorted({edge["symbol"] for edge in edges_out if edge["relation"] == "DIRECT_ISSUER"
                         and edge["held_snapshot_match"] is True and not reference})
        indirect = sorted({edge["symbol"] for edge in edges_out if edge["relation"] == "INDIRECT_CANDIDATE"
                           and edge["held_snapshot_match"] is True and not reference})
        positive = bool(direct or indirect)
        issuer_only = any(edge["relation"] == "ISSUER_CANDIDATE" for edge in edges_out)
        groups.append({"event_id": _id("event", event_key, registry), "event_key": event_key,
                       "sources": sources_out, "edges": edges_out,
                       "qualified_direct_held": direct,
                       "provisional_indirect_held_candidates": indirect,
                       "decision": "REVIEW_EXPOSURE" if positive else "NO_CHANGE_WITH_REASON",
                       "reason_codes": _reason_codes(positive, reference, issuer_only,
                                                      held_meta["status"], coverage_partial),
                       "contradiction": {"status": "UNKNOWN",
                                         "check": "Issuer or event subject differs from caller-qualified edge"},
                       "falsifier": {"status": "UNKNOWN",
                                     "check": "Underlying event, issuer link, or held snapshot fails independent review"}})
    positive = any(group["decision"] == "REVIEW_EXPOSURE" for group in groups)
    root_issuer_only = any(any(edge["relation"] == "ISSUER_CANDIDATE" for edge in group["edges"])
                           for group in groups)
    root_reasons = (_reason_codes(positive, False, root_issuer_only,
                                  held_meta["status"], coverage_partial)
                    if groups else ["NO_SOURCES_AT_CUTOFF"])
    body = {"schema": "provisional-event-review/1", "status": "PROVISIONAL_REVIEW",
            "component_only": True, "natural_warning": False,
            "provenance_authority": "CALLER_SUPPLIED_NOT_INDEPENDENTLY_VERIFIED",
            "review_time_utc": _iso(review), "source_cutoff_utc": _iso(cutoff),
            "upstream_digest": {"state": upstream_state, "exit_code": upstream_exit_code,
                                "parse_status": "UNKNOWN"},
            "authority": {"forecast_writes": 0, "portfolio_action": "NONE",
                          "delivery": "NOT_ATTEMPTED", "provider_calls": 0},
            "coverage": coverage, "holdings": held_meta, "groups": groups,
            "uncertainty": {"probability": "UNKNOWN", "direction": "UNKNOWN",
                            "magnitude": "UNKNOWN", "expectations": "UNKNOWN",
                            "event_outcome": "UNKNOWN"},
            "decision": "REVIEW_EXPOSURE" if positive else "NO_CHANGE_WITH_REASON",
            "reason_codes": root_reasons}
    receipt_id = _sha(_canonical(body))
    result = {**body, "receipt_id": receipt_id}
    if len(_canonical(result)) > MAX_RECEIPT_BYTES:
        _refuse("RECEIPT_BYTE_CAP")
    return _BuiltReceipt(result)


def _only_fields(value: Any, names: str) -> None:
    if not isinstance(value, dict) or set(value) != set(names.split()):
        _refuse("RECEIPT_INTEGRITY")


def _safe_reason_codes(value: Any) -> None:
    allowed = {"REFERENCE_ONLY", "QUALIFIED_HELD_EDGE_FOR_REVIEW",
               "ISSUER_SECURITY_UNRESOLVED", "HOLDINGS_UNKNOWN",
               "HOLDINGS_AFTER_CUTOFF", "PARTIAL_HOLDINGS_UNKNOWN",
               "PARTIAL_INPUT_COVERAGE_UNKNOWN", "NO_QUALIFIED_HELD_EDGE",
               "NO_SOURCES_AT_CUTOFF"}
    if not isinstance(value, list) or not value or len(value) > 4 or any(
            not isinstance(code, str) or code not in allowed for code in value):
        _refuse("RECEIPT_INTEGRITY")


def _validate_receipt_schema(receipt: dict[str, Any], cutoff: datetime) -> None:
    """Allow only builder fields and fixed non-action states at every level."""
    _only_fields(receipt, "schema status component_only natural_warning provenance_authority "
                 "review_time_utc source_cutoff_utc upstream_digest authority coverage "
                 "holdings groups uncertainty decision reason_codes receipt_id")
    upstream = receipt["upstream_digest"]
    _only_fields(upstream, "state exit_code parse_status")
    if upstream["parse_status"] != "UNKNOWN" or not (
            (upstream["state"] == "UNKNOWN" and upstream["exit_code"] is None)
            or (upstream["state"] == "BUDGET_REFUSED"
                and type(upstream["exit_code"]) is int and upstream["exit_code"] > 0)):
        _refuse("RECEIPT_INTEGRITY")
    _only_fields(receipt["authority"], "forecast_writes portfolio_action delivery provider_calls")
    _only_fields(receipt["uncertainty"], "probability direction magnitude expectations event_outcome")
    coverage = receipt["coverage"]
    _only_fields(coverage, "status caller_input_complete input_source_rows future_source_versions_excluded "
                 "future_edges_excluded duplicate_versions sources_omitted_by_cap edges_not_joined")
    if (type(coverage["caller_input_complete"]) is not bool
            or type(coverage["input_source_rows"]) is not int
            or not 1 <= coverage["input_source_rows"] <= MAX_INPUT_SOURCES
            or any(type(coverage[name]) is not int or coverage[name] < 0 for name in (
                "future_source_versions_excluded", "future_edges_excluded", "duplicate_versions",
                "sources_omitted_by_cap", "edges_not_joined"))
            or coverage["status"] != ("PARTIAL" if not coverage["caller_input_complete"]
                                      or coverage["sources_omitted_by_cap"] else "COMPLETE")):
        _refuse("RECEIPT_INTEGRITY")
    held = receipt["holdings"]
    _only_fields(held, "status as_of_utc known_at_utc evidence_sha256 symbol_count")
    if held["status"] == "UNKNOWN":
        if any(held[name] is not None for name in (
                "as_of_utc", "known_at_utc", "evidence_sha256", "symbol_count")):
            _refuse("RECEIPT_INTEGRITY")
    elif held["status"] in ("COMPLETE", "PARTIAL", "HOLDINGS_AFTER_CUTOFF"):
        if (type(held["symbol_count"]) is not int or not 0 <= held["symbol_count"] <= MAX_HOLDINGS
                or _clock(held["as_of_utc"]) > _clock(held["known_at_utc"])):
            _refuse("RECEIPT_INTEGRITY")
        _hash(held["evidence_sha256"])
        if (held["status"] == "HOLDINGS_AFTER_CUTOFF") != (_clock(held["known_at_utc"]) > cutoff):
            _refuse("RECEIPT_INTEGRITY")
    else:
        _refuse("RECEIPT_INTEGRITY")
    groups = receipt["groups"]
    if not isinstance(groups, list) or len(groups) > MAX_SELECTED_SOURCES:
        _refuse("RECEIPT_INTEGRITY")
    total_sources = 0
    root_issuer_only = False
    for group in groups:
        _only_fields(group, "event_id event_key sources edges qualified_direct_held "
                     "provisional_indirect_held_candidates decision reason_codes contradiction falsifier")
        event_key = _key(group["event_key"])
        if group["event_id"] != _stable_id("event", event_key):
            _refuse("RECEIPT_INTEGRITY")
        _safe_reason_codes(group["reason_codes"])
        for field, check in (("contradiction", "Issuer or event subject differs from caller-qualified edge"),
                             ("falsifier", "Underlying event, issuer link, or held snapshot fails independent review")):
            _only_fields(group[field], "status check")
            if group[field] != {"status": "UNKNOWN", "check": check}:
                _refuse("RECEIPT_INTEGRITY")
        sources = group["sources"]
        edges = group["edges"]
        if (not isinstance(sources, list) or not 1 <= len(sources) <= MAX_SELECTED_SOURCES
                or not isinstance(edges, list) or len(edges) > MAX_EDGES):
            _refuse("RECEIPT_INTEGRITY")
        total_sources += len(sources)
        if total_sources > MAX_SELECTED_SOURCES:
            _refuse("RECEIPT_INTEGRITY")
        selected = {}
        for source in sources:
            _only_fields(source, "source_id version_id source_sha256 kind first_seen_utc "
                         "version_seen_utc published_utc proof_known_at_utc proof_witness_sha256 "
                         "superseded_version_hashes")
            sid, sha = _hash(source["source_id"]), _hash(source["source_sha256"])
            if (source["version_id"] != _sha(f"version\0{sid}\0{sha}".encode())
                    or source["kind"] not in ("ARTICLE", "FILING", "REFERENCE_PAGE")):
                _refuse("RECEIPT_INTEGRITY")
            first, version, known = (_clock(source["first_seen_utc"]),
                                     _clock(source["version_seen_utc"]),
                                     _clock(source["proof_known_at_utc"]))
            if first > version or version > known or known > cutoff:
                _refuse("RECEIPT_INTEGRITY")
            if source["published_utc"] is not None and _clock(source["published_utc"]) > version:
                _refuse("RECEIPT_INTEGRITY")
            _hash(source["proof_witness_sha256"])
            old = source["superseded_version_hashes"]
            if not isinstance(old, list) or len(old) > MAX_INPUT_SOURCES:
                _refuse("RECEIPT_INTEGRITY")
            for old_sha in old:
                _hash(old_sha)
            selected[(sid, sha)] = known
        reference = all(source["kind"] == "REFERENCE_PAGE" for source in sources)
        direct, indirect = set(), set()
        issuer_only = False
        for edge in edges:
            _only_fields(edge, "source_id source_sha256 issuer_id symbol relation basis known_at_utc "
                         "evidence_sha256 held_snapshot_match")
            identity = (_hash(edge["source_id"]), _hash(edge["source_sha256"]))
            if identity not in selected or not selected[identity] <= _clock(edge["known_at_utc"]) <= cutoff:
                _refuse("RECEIPT_INTEGRITY")
            _issuer(edge["issuer_id"])
            _hash(edge["evidence_sha256"])
            relation, basis = edge["relation"], edge["basis"]
            allowed = {"DIRECT_ISSUER": "FULL_ISSUER_SUBJECT",
                       "INDIRECT_CANDIDATE": "REVIEWED_MECHANISM",
                       "ISSUER_CANDIDATE": "SEC_CIK"}
            if relation == "ISSUER_CANDIDATE":
                issuer_only = True
                root_issuer_only = True
                if (basis != "SEC_CIK" or not _CIK.fullmatch(edge["issuer_id"])
                        or edge["symbol"] is not None or edge["held_snapshot_match"] != "UNKNOWN"):
                    _refuse("RECEIPT_INTEGRITY")
            else:
                _symbol(edge["symbol"])
                if relation == "DISCOVERY_CONTEXT":
                    if basis not in ("QUEUE_CONTEXT", "TICKER_ONLY"):
                        _refuse("RECEIPT_INTEGRITY")
                elif allowed.get(relation) != basis:
                    _refuse("RECEIPT_INTEGRITY")
                if edge["held_snapshot_match"] not in (True, False, "UNKNOWN"):
                    _refuse("RECEIPT_INTEGRITY")
                if held["status"] in ("UNKNOWN", "HOLDINGS_AFTER_CUTOFF") and edge["held_snapshot_match"] != "UNKNOWN":
                    _refuse("RECEIPT_INTEGRITY")
                if edge["held_snapshot_match"] is True and not reference:
                    if relation == "DIRECT_ISSUER":
                        direct.add(edge["symbol"])
                    elif relation == "INDIRECT_CANDIDATE":
                        indirect.add(edge["symbol"])
        if (group["qualified_direct_held"] != sorted(direct)
                or group["provisional_indirect_held_candidates"] != sorted(indirect)
                or group["decision"] != ("REVIEW_EXPOSURE" if direct or indirect else "NO_CHANGE_WITH_REASON")
                or group["reason_codes"] != _reason_codes(bool(direct or indirect), reference,
                                                           issuer_only, held["status"],
                                                           coverage["status"] == "PARTIAL")):
            _refuse("RECEIPT_INTEGRITY")
    _safe_reason_codes(receipt["reason_codes"])
    positive = any(group["decision"] == "REVIEW_EXPOSURE" for group in groups)
    expected_reasons = (_reason_codes(positive, False, root_issuer_only, held["status"],
                                      coverage["status"] == "PARTIAL")
                        if groups else ["NO_SOURCES_AT_CUTOFF"])
    if (receipt["decision"] != ("REVIEW_EXPOSURE" if positive else "NO_CHANGE_WITH_REASON")
            or receipt["reason_codes"] != expected_reasons):
        _refuse("RECEIPT_INTEGRITY")


def write_receipt(receipt: _BuiltReceipt, *, directory: Path) -> Path:
    """Persist an unmodified builder result; preserve any partial I/O failure."""
    if type(receipt) is not _BuiltReceipt:
        _refuse("RECEIPT_INTEGRITY")
    # A caller-computed SHA proves only byte consistency. Persist exactly the
    # unmodified builder result; reject added claims at any nesting depth.
    try:
        serialized = _canonical(receipt)
    except (TypeError, ValueError, OverflowError):
        _refuse("RECEIPT_INTEGRITY")
    if serialized != receipt._sealed_bytes:
        _refuse("RECEIPT_INTEGRITY")
    if len(serialized) + 1 > MAX_RECEIPT_BYTES:
        _refuse("RECEIPT_BYTE_CAP")
    body = {key: value for key, value in receipt.items() if key != "receipt_id"}
    try:
        valid = (receipt.get("receipt_id") == _sha(_canonical(body))
                 and receipt.get("schema") == "provisional-event-review/1"
                 and receipt.get("status") == "PROVISIONAL_REVIEW"
                 and receipt.get("component_only") is True
                 and receipt.get("natural_warning") is False
                 and receipt.get("provenance_authority") == "CALLER_SUPPLIED_NOT_INDEPENDENTLY_VERIFIED"
                 and receipt.get("decision") in ("REVIEW_EXPOSURE", "NO_CHANGE_WITH_REASON")
                 and receipt.get("uncertainty") == {"probability": "UNKNOWN", "direction": "UNKNOWN",
                                                   "magnitude": "UNKNOWN", "expectations": "UNKNOWN",
                                                   "event_outcome": "UNKNOWN"}
                 and receipt.get("authority") == {"forecast_writes": 0, "portfolio_action": "NONE",
                                                   "delivery": "NOT_ATTEMPTED", "provider_calls": 0})
    except (TypeError, ValueError, OverflowError):
        valid = False
    if not valid:
        _refuse("RECEIPT_INTEGRITY")
    review = _clock(receipt.get("review_time_utc"))
    cutoff = _clock(receipt.get("source_cutoff_utc"))
    if review < cutoff:
        _refuse("RECEIPT_INTEGRITY")
    try:
        _validate_receipt_schema(receipt, cutoff)
    except (ReviewRefused, TypeError, ValueError, KeyError, OverflowError):
        _refuse("RECEIPT_INTEGRITY")
    data = serialized + b"\n"
    if (not isinstance(directory, Path) or not directory.is_absolute()
            or directory.drive.startswith("\\\\") or not directory.is_dir()
            or directory.is_symlink()):
        _refuse("RECEIPT_DIRECTORY")
    stamp = review.strftime("%Y%m%dT%H%M%S%fZ")
    path = directory / f"provisional_review_{stamp}_{receipt['receipt_id']}.json"
    try:
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        _refuse("RECEIPT_EXISTS")
    except OSError:
        _refuse("RECEIPT_IO_INCOMPLETE")
    return path
