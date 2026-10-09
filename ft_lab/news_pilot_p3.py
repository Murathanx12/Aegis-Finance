"""Offline p3 candidate: source-derived constrained evidence for local Qwen7B.

No inference entry point. PRODUCT_EXPERIMENT; candidate must be reviewed and
version-frozen before an owned local-model run. No gold labels are read here.
"""
from __future__ import annotations

import json
import re

from ft_lab.news_pilot import canonical, digest
from ft_lab.news_pilot_qwen7b import EVENTS, SCHEMA

VERSION = "qwen7b_article_facts/p3_window_enum_v2"
TRANSFORM_VERSION = "source_windows_overlap_half/v1"
MAX_CHUNKS = 64
MAX_SCHEMA_BYTES = 16_384
MAX_SPAN = 180
MAX_SOURCE = 1600


def source_chunks(excerpt: str) -> list[str]:
    """Overlapping exact word-boundary windows preserve financial punctuation."""
    from backend.services.world_digest import sanitize_text

    if not excerpt or len(excerpt) > MAX_SOURCE:
        raise ValueError("source empty or oversized")
    cleaned, flagged = sanitize_text(excerpt)
    if flagged or cleaned != excerpt:
        raise ValueError("injection marker or source sanitization required")
    words = list(re.finditer(r"\S+", excerpt))
    if any(len(w.group()) > MAX_SPAN for w in words):
        raise ValueError("unsplittable source token exceeds evidence bound")
    pieces: list[str] = []
    start = 0
    while start < len(words):
        end = start
        while end + 1 < len(words) and words[end + 1].end() - words[start].start() <= MAX_SPAN:
            end += 1
        pieces.append(excerpt[words[start].start():words[end].end()])
        if end == len(words) - 1:
            break
        # Step about half a window, so ordinary amount/date phrases crossing
        # one edge remain intact in the next candidate.
        midpoint = words[start].start() + (words[end].end() - words[start].start()) // 2
        next_start = start + 1
        while next_start < end and words[next_start].start() < midpoint:
            next_start += 1
        start = next_start
    pieces = list(dict.fromkeys(pieces))
    if not pieces or len(pieces) > MAX_CHUNKS or any(len(p) > MAX_SPAN or p not in excerpt for p in pieces):
        raise ValueError("source clause enumeration not bounded/source-bound")
    return pieces


def response_format(excerpt: str) -> dict:
    chunks = source_chunks(excerpt)
    schema = {
        "type": "object", "additionalProperties": False,
        "required": ["entity", "event_type", "event_date", "date_precision",
                     "numbers", "evidence_spans", "abstain"],
        "properties": {
            "entity": {"type": ["string", "null"]},
            "event_type": {"type": "string", "enum": list(EVENTS)},
            "event_date": {"type": ["string", "null"]},
            "date_precision": {"type": "string", "enum": ["day", "month", "quarter", "year", "unknown"]},
            "numbers": {"type": "array", "items": {"type": "string"}, "maxItems": 12},
            "evidence_spans": {"type": "array", "items": {"type": "string", "enum": chunks},
                               "minItems": 0, "maxItems": 5},
            "abstain": {"type": "boolean"},
        },
    }
    wire = {"type": "json_object", "schema": schema}
    if len(json.dumps(wire, ensure_ascii=False).encode("utf-8")) > MAX_SCHEMA_BYTES:
        raise ValueError("source schema exceeds wire size bound")
    return wire


def validate_reply(text: str, excerpt: str, wire: dict) -> dict:
    """Check observed output against the requested enum, even if grammar is ignored."""
    from ft_lab.news_pilot_qwen7b import PilotValidationError, parse_reply
    parsed = parse_reply(text, excerpt)
    allowed = set(wire["schema"]["properties"]["evidence_spans"]["items"]["enum"])
    if any(span not in allowed for span in parsed["evidence_spans"]):
        raise PilotValidationError("evidence_not_in_enum")
    if not parsed["abstain"] and not parsed["evidence_spans"]:
        raise PilotValidationError("missing_evidence")
    return parsed


def constraint_receipt(excerpt: str) -> dict:
    wire = response_format(excerpt)
    return {"prompt_version": VERSION, "transform_version": TRANSFORM_VERSION,
            "schema": SCHEMA, "source_sha256": digest(excerpt.encode("utf-8")),
            "response_format_sha256": digest(canonical(wire)),
            "candidate_count": len(wire["schema"]["properties"]["evidence_spans"]["items"]["enum"]),
            "wire_bytes": len(json.dumps(wire, ensure_ascii=False).encode("utf-8"))}


def variant_hash(documents: list[dict]) -> str:
    """Reservation binding for the exact selected development source set."""
    if not documents or any(d.get("split") != "dev" for d in documents):
        raise ValueError("p3 reservation only accepts development excerpts")
    formats = {}
    for d in documents:
        if digest(d["excerpt"].encode("utf-8")) != d.get("content_sha256") or d["id"] in formats:
            raise ValueError("duplicate or changed p3 source")
        formats[d["id"]] = digest(canonical(response_format(d["excerpt"])))
    return digest(canonical({"version": VERSION, "formats": formats}))


def run_p3(manifest: dict, **kwargs) -> dict:
    """Reuse the reviewed owner/PID/RAM/checkpoint lifecycle with explicit p3 binding."""
    from ft_lab.news_pilot_qwen7b import run
    return run(manifest, variant={"prompt_version": VERSION,
                                  "response_format": response_format,
                                  "validate_reply": validate_reply}, **kwargs)


def complete_p3(doc: dict, *, model_complete=None):
    """A single local wire request; caller owns lifecycle, RAM guard and checkpoint."""
    from backend.services import model_provider
    from ft_lab.news_pilot_qwen7b import SYSTEM

    excerpt = doc["excerpt"]
    if digest(excerpt.encode("utf-8")) != doc.get("content_sha256"):
        raise ValueError("source hash drift")
    wire = response_format(excerpt)
    reply = (model_complete or model_provider.complete)(
        "local", "<SOURCE>\n" + excerpt + "\n</SOURCE>", system=SYSTEM,
        model="local", max_tokens=500, temperature=0, timeout=90,
        purpose="news_pilot_qwen7b_p3", response_format=wire)
    # Return raw reply unchanged. The existing runner must retain raw text and
    # invoke parse_reply afterward, including on INVALID_OUTPUT.
    return reply
