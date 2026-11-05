"""Pinned, read-only E2 receipt to a local owner review candidate.

All source clocks and identity assertions remain caller supplied. This module
does not discover files, authenticate a held book, or deliver an alert.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any

from backend.services import provisional_event_review as e2


class ViewRefused(ValueError):
    """Sanitized refusal; never includes paths, bytes, or article content."""


@dataclass(frozen=True)
class SourcePin:
    source_key: str
    source_sha256: str
    absolute_local_path: Path


@dataclass(frozen=True)
class StationPin:
    station_key: str
    map_path: Path
    map_sha256: str
    label: str


def _refuse(code: str) -> None:
    raise ViewRefused(code)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash(value: Any) -> str:
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value):
        _refuse("INVALID_PIN")
    return value


def _key(value: Any) -> str:
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:._-]{0,127}", value):
        _refuse("INVALID_PIN")
    return value


def _read_pinned(path: Path, expected_sha: str, cap: int) -> bytes:
    """Read an explicit regular file once, rejecting reparse components."""
    _hash(expected_sha)
    if not isinstance(path, Path) or not path.is_absolute() or path.drive.startswith("\\\\"):
        _refuse("INVALID_PATH")
    try:
        for part in (path, *path.parents):
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or (getattr(info, "st_file_attributes", 0) & 0x400):
                _refuse("REDIRECT_PATH")
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            _refuse("INVALID_FILE")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                _refuse("PATH_CHANGED")
            data = stream.read(cap + 1)
            if len(data) > cap:
                _refuse("BYTE_CAP")
            if stream.read(1):
                _refuse("BYTE_CAP")
        after = path.lstat()
        if (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino):
            _refuse("PATH_CHANGED")
        if _digest(data) != expected_sha:
            _refuse("PIN_MISMATCH")
        return data
    except (OSError, ValueError) as exc:
        if isinstance(exc, ViewRefused):
            raise
        _refuse("FILE_UNAVAILABLE")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            _refuse("DUPLICATE_JSON_KEY")
        out[key] = value
    return out


def _parse_receipt(data: bytes) -> dict[str, Any]:
    try:
        result = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object,
                            parse_constant=lambda _: _refuse("INVALID_JSON"))
        if type(result) is not dict:
            _refuse("INVALID_JSON")
        body = {key: value for key, value in result.items() if key != "receipt_id"}
        if result.get("receipt_id") != _digest(e2._canonical(body)):
            _refuse("RECEIPT_INTEGRITY")
        if (result.get("schema") != "provisional-event-review/1"
                or result.get("status") != "PROVISIONAL_REVIEW"
                or result.get("component_only") is not True
                or result.get("natural_warning") is not False
                or result.get("provenance_authority") != "CALLER_SUPPLIED_NOT_INDEPENDENTLY_VERIFIED"
                or result.get("authority") != {"forecast_writes": 0, "portfolio_action": "NONE",
                                               "delivery": "NOT_ATTEMPTED", "provider_calls": 0}
                or result.get("uncertainty") != {"probability": "UNKNOWN", "direction": "UNKNOWN",
                                                 "magnitude": "UNKNOWN", "expectations": "UNKNOWN",
                                                 "event_outcome": "UNKNOWN"}):
            _refuse("RECEIPT_INTEGRITY")
        cutoff = e2._clock(result["source_cutoff_utc"])
        if e2._clock(result["review_time_utc"]) < cutoff:
            _refuse("RECEIPT_INTEGRITY")
        e2._validate_receipt_schema(result, cutoff)
        if len(result["groups"]) != 1:
            _refuse("EVENT_GROUP_COUNT")
        return result
    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError, OverflowError, RecursionError,
            e2.ReviewRefused, ValueError):
        _refuse("RECEIPT_INTEGRITY")


def build_owner_decision_view(*, receipt_path: Path, receipt_sha256: str,
                              source_pins: list[SourcePin] | tuple[SourcePin, ...],
                              station: StationPin | None = None) -> dict[str, Any]:
    """Verify explicit pins and return one sanitized, deterministic display object."""
    receipt = _parse_receipt(_read_pinned(receipt_path, receipt_sha256, e2.MAX_RECEIPT_BYTES))
    group = receipt["groups"][0]
    sources = group["sources"]
    edge_tokens: set[tuple[Any, ...]] = set()
    issuer_by_indirect_symbol: dict[str, str] = {}
    issuer_by_source: dict[tuple[str, str], str] = {}
    for edge in group["edges"]:
        token = tuple(edge[name] for name in ("source_id", "source_sha256", "issuer_id",
                                               "symbol", "relation", "basis", "known_at_utc",
                                               "evidence_sha256"))
        if token in edge_tokens:
            _refuse("DUPLICATE_EDGE")
        edge_tokens.add(token)
        if edge["relation"] == "INDIRECT_CANDIDATE":
            old = issuer_by_indirect_symbol.setdefault(edge["symbol"], edge["issuer_id"])
            if old != edge["issuer_id"]:
                _refuse("AMBIGUOUS_ISSUER")
        elif edge["relation"] == "ISSUER_CANDIDATE":
            identity = (edge["source_id"], edge["source_sha256"])
            old = issuer_by_source.setdefault(identity, edge["issuer_id"])
            if old != edge["issuer_id"]:
                _refuse("AMBIGUOUS_ISSUER")
    if (type(source_pins) not in (list, tuple) or len(source_pins) != len(sources)
            or len(source_pins) > e2.MAX_SELECTED_SOURCES):
        _refuse("SOURCE_PIN_COUNT")
    selected: dict[tuple[str, str], dict[str, Any]] = {}
    keys: set[str] = set()
    selected_ids: set[str] = set()
    selected_hashes: set[str] = set()
    for source in sources:
        identity = (source["source_id"], source["source_sha256"])
        if (identity in selected or source["source_id"] in selected_ids
                or source["source_sha256"] in selected_hashes):
            _refuse("SOURCE_ID_COLLISION")
        selected[identity] = source
        selected_ids.add(source["source_id"])
        selected_hashes.add(source["source_sha256"])
    total = 0
    matched: set[tuple[str, str]] = set()
    for pin in source_pins:
        if type(pin) is not SourcePin:
            _refuse("INVALID_PIN")
        key, sha = _key(pin.source_key), _hash(pin.source_sha256)
        identity = (e2._stable_id("source", key), sha)
        if key in keys or identity not in selected or identity in matched:
            _refuse("SOURCE_BINDING")
        keys.add(key)
        matched.add(identity)
        data = _read_pinned(pin.absolute_local_path, sha,
                            min(e2.MAX_SOURCE_BYTES, e2.MAX_TOTAL_SOURCE_BYTES - total))
        if not data:
            _refuse("MISSING_SOURCE_BYTES")
        total += len(data)
        if total > e2.MAX_TOTAL_SOURCE_BYTES:
            _refuse("SOURCE_TOTAL_CAP")
    if matched != set(selected):
        _refuse("SOURCE_BINDING")
    # The E2 schema validator checks every edge against a selected source and
    # enforces edge known_at <= cutoff, but does not reject repeated source IDs.
    if station is None:
        station_view = {"status": "UNKNOWN"}
    else:
        if (type(station) is not StationPin or not _key(station.station_key)
                or type(station.label) is not str or not 1 <= len(station.label) <= 120
                or any(ord(ch) < 32 or ord(ch) == 127 for ch in station.label)):
            _refuse("INVALID_STATION")
        _read_pinned(station.map_path, station.map_sha256, e2.MAX_SOURCE_BYTES)
        station_view = {"status": "CALLER_LABELED_HYPOTHESIS", "station_key": station.station_key,
                        "label": station.label, "map_sha256": station.map_sha256}
    source_view = [{key: source[key] for key in ("source_id", "version_id", "source_sha256",
                                                 "published_utc", "first_seen_utc",
                                                 "version_seen_utc", "proof_known_at_utc")}
                   for source in sources]
    identity_body = {"event_id": group["event_id"], "receipt_id": receipt["receipt_id"],
                     "source_cutoff_utc": receipt["source_cutoff_utc"],
                     "source_sha256": sorted(source["source_sha256"] for source in sources)}
    return {"schema": "owner-decision-view/1", "status": "CANDIDATE_FOR_OWNER_REVIEW",
            "view_id": _digest(e2._canonical(identity_body)), "event_id": group["event_id"],
            "event_key": group["event_key"], "receipt_id": receipt["receipt_id"],
            "provenance_authority": receipt["provenance_authority"],
            "source_cutoff_utc": receipt["source_cutoff_utc"],
            "review_time_utc": receipt["review_time_utc"], "sources": source_view,
            "decision": group["decision"], "reason_codes": group["reason_codes"],
            "caller_supplied_indirect_symbol_matches": group["caller_supplied_indirect_symbol_matches"],
            "relation_status": "CALLER_SUPPLIED_INDIRECT_HYPOTHESIS" if group["decision"] == "REVIEW_EXPOSURE"
                               else "ISSUER_OR_EXPOSURE_UNRESOLVED",
            "coverage": receipt["coverage"],
            "holdings": {"status": receipt["holdings"]["status"],
                         "authority": receipt["holdings"]["authority"]},
            "upstream_digest": receipt["upstream_digest"], "uncertainty": receipt["uncertainty"],
            "contradiction": group["contradiction"], "falsifier": group["falsifier"],
            "station": station_view, "owner_decision": "UNOBSERVED",
            "delivery": "NOT_ATTEMPTED", "natural_warning": False,
            "forecast_status": "UNKNOWN", "portfolio_action": "NONE"}
