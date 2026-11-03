"""Inactive saved SEC lineage candidate: injected bytes in, artifacts out.

No forecast is generated. Unkeyed hashes prove byte/context identity, not truth,
source authenticity, snapshot ownership, freshness now, or delivery.
"""
from __future__ import annotations

import hashlib
import json

from backend.services.owner_event_warning import build_saved_warning_bytes
from backend.services.saved_sec_forecast_input import (
    MAX_BYTES,
    _utc,
    build_saved_sec_input,
)

SCHEMA = "saved-sec-event-path/1"


def _digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def build_saved_sec_event_path(*, event_bytes: bytes, snapshot_bytes: bytes,
                               ticker: str, cutoff_utc: str,
                               decision_utc: str) -> dict:
    """Connect one PIT evidence unit to a provisional, zero-allocation decision.

    cutoff <= decision; snapshot t <= decision (not necessarily <= cutoff).
    Exact daily row copies count once under the adapter's bounded JSONL contract.
    Returns explicit refusal if either upstream builder refuses. No IO, clocks,
    model invocation, transport, persistence or allocation authority is supplied.
    """
    result = {
        "schema": SCHEMA, "status": "REFUSED", "active": False,
        "runtime_authority": "NONE", "new_allocation_usd": "0",
        "forecast_status": "NO_CALIBRATED_EVENT_FORECAST", "forecast_id": None,
        "event_id": None, "evidence_packet_sha256": None,
        "forecast_input_id": None, "decision_id": None,
    }
    try:
        cutoff, decision = _utc(cutoff_utc), _utc(decision_utc)
    except (ValueError, TypeError, OverflowError):
        return {**result, "reason": "CLOCK_INVALID"}
    if cutoff > decision:
        return {**result, "reason": "CUTOFF_AFTER_DECISION"}
    if type(snapshot_bytes) is not bytes or not 0 < len(snapshot_bytes) <= MAX_BYTES:
        return {**result, "reason": "SNAPSHOT_BYTES_INVALID_OR_TOO_LARGE"}
    packet = build_saved_sec_input(event_bytes, ticker=ticker, cutoff_utc=cutoff_utc)
    if packet["status"] != "EVIDENCE_ONLY":
        return {**result, "reason": packet["reason"], "refusal_stage": "EVIDENCE"}
    evidence = packet["evidence"]
    selected = evidence["source_row_utf8"].encode("utf-8")
    try:
        artifact = build_saved_warning_bytes(
            source_bytes=selected, snapshot_bytes=snapshot_bytes,
            ticker=ticker, now=decision,
            source_row_sha256=evidence["row_sha256"],
        )
    except RecursionError:
        return {**result, "reason": "SAVED_INPUT_INVALID", "refusal_stage": "DECISION"}
    if artifact["status"] != "PROVISIONAL":
        return {**result, "reason": artifact["reason"], "refusal_stage": "DECISION"}
    packet_hash = packet["packet_sha256"]
    event_id = artifact["event_key"]
    input_id = "saved-sec-input:" + packet_hash
    binding = {
        "schema": SCHEMA, "event_id": event_id,
        "forecast_input_id": input_id, "evidence_packet_sha256": packet_hash,
        "snapshot_sha256": hashlib.sha256(snapshot_bytes).hexdigest(),
        "decision_utc": decision.isoformat(), "decision_artifact": artifact,
    }
    return {
        **result, **binding, "status": "PROVISIONAL", "reason": "SAVED_EVIDENCE_ONLY",
        "evidence_unit_count": 1, "evidence_packet": packet,
        "decision_id": "saved-sec-decision:" + _digest(binding),
    }
