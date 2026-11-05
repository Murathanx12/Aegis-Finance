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
    symbol: str
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
    if not isinstance(value, str):
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
    issuer, symbol = _issuer(raw.issuer_id), _symbol(raw.symbol)
    _hash(raw.evidence_sha256)
    known = _clock(raw.known_at_utc)
    if known < supplied[(key, sha)] or known > review:
        _refuse("INVALID_EDGE_TIMELINE")
    allowed = {"DIRECT_ISSUER": {"FULL_ISSUER_SUBJECT", "SEC_CIK"},
               "INDIRECT_CANDIDATE": {"REVIEWED_MECHANISM"},
               "DISCOVERY_CONTEXT": {"QUEUE_CONTEXT", "TICKER_ONLY"}}
    if raw.relation == "DIRECT_ISSUER" and raw.basis not in allowed["DIRECT_ISSUER"]:
        _refuse("UNQUALIFIED_DIRECT_EDGE")
    if raw.relation not in allowed or raw.basis not in allowed[raw.relation]:
        _refuse("INVALID_EDGE_QUALIFICATION")
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
        match = "UNKNOWN" if held is None or (held_meta["status"] == "PARTIAL" and edge["symbol"] not in held) else edge["symbol"] in held
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

    def reasons(positive: bool, reference: bool = False) -> list[str]:
        if reference:
            return ["REFERENCE_ONLY"]
        if positive:
            return ["QUALIFIED_HELD_EDGE_FOR_REVIEW"]
        if held_meta["status"] == "UNKNOWN":
            return ["HOLDINGS_UNKNOWN"]
        if held_meta["status"] == "HOLDINGS_AFTER_CUTOFF":
            return ["HOLDINGS_AFTER_CUTOFF"]
        if held_meta["status"] == "PARTIAL":
            return ["PARTIAL_HOLDINGS_UNKNOWN"]
        if coverage_partial:
            return ["PARTIAL_INPUT_COVERAGE_UNKNOWN"]
        return ["NO_QUALIFIED_HELD_EDGE"]

    groups = []
    for event_key in sorted(grouped):
        sources_out = sorted(grouped[event_key], key=lambda item: item["source_id"])
        edges_out = sorted(joined[event_key], key=lambda item: (
            item["source_id"], item["symbol"], item["issuer_id"], item["relation"],
            item["basis"], item["known_at_utc"], item["evidence_sha256"]))
        reference = all(source["kind"] == "REFERENCE_PAGE" for source in sources_out)
        direct = sorted({edge["symbol"] for edge in edges_out if edge["relation"] == "DIRECT_ISSUER"
                         and edge["held_snapshot_match"] is True and not reference})
        indirect = sorted({edge["symbol"] for edge in edges_out if edge["relation"] == "INDIRECT_CANDIDATE"
                           and edge["held_snapshot_match"] is True and not reference})
        positive = bool(direct or indirect)
        groups.append({"event_id": _id("event", event_key, registry), "event_key": event_key,
                       "sources": sources_out, "edges": edges_out,
                       "qualified_direct_held": direct,
                       "provisional_indirect_held_candidates": indirect,
                       "decision": "REVIEW_EXPOSURE" if positive else "NO_CHANGE_WITH_REASON",
                       "reason_codes": reasons(positive, reference),
                       "contradiction": {"status": "UNKNOWN",
                                         "check": "Issuer or event subject differs from caller-qualified edge"},
                       "falsifier": {"status": "UNKNOWN",
                                     "check": "Underlying event, issuer link, or held snapshot fails independent review"}})
    positive = any(group["decision"] == "REVIEW_EXPOSURE" for group in groups)
    root_reasons = reasons(positive) if groups else ["NO_SOURCES_AT_CUTOFF"]
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
    return result


def write_receipt(receipt: dict[str, Any], *, directory: Path) -> Path:
    """Create one dated receipt exclusively; preserve any partial I/O failure."""
    if not isinstance(receipt, dict):
        _refuse("RECEIPT_INTEGRITY")
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
    data = _canonical(receipt) + b"\n"
    if len(data) > MAX_RECEIPT_BYTES:
        _refuse("RECEIPT_BYTE_CAP")
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
