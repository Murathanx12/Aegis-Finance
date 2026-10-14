"""Build one provenance-bound current Item from the earlier private ASML capture.

Pure preparation: no network, model, corpus, forecast, cache, or ledger writes.
The caller may submit this Item to world_digest's opt-in CURRENT extractor only
after a prospective contract and independent route review are in place.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from backend.services import news_registry, world_digest
from backend.services.issuer_ir_html import IssuerPageRefused, parse_asml_release


SOURCE_ID = "asml_ir_q3_2026"
RAW_SHA256 = "8e8c8a50e784d0af9b75ab747dc7892f6f2ba98554b5d2043f17530c8562753f"
RECEIPT_SHA256 = "d2da519d62c71929bce31df9db5f039d57c2d481d6b1ecb2755e44c4dd51827e"


def _utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise IssuerPageRefused("capture_time_invalid") from exc
    if parsed.tzinfo is None:
        raise IssuerPageRefused("capture_time_naive")
    return parsed.astimezone(timezone.utc)


def build_item(acquisition_path: Path) -> world_digest.Item:
    acquisition_path = Path(acquisition_path)
    receipt_bytes = acquisition_path.read_bytes()
    if hashlib.sha256(receipt_bytes).hexdigest() != RECEIPT_SHA256:
        raise IssuerPageRefused("authentic_acquisition_receipt_drift")
    receipt = json.loads(receipt_bytes.decode("utf-8"))
    source = news_registry.get(SOURCE_ID)
    if (receipt.get("status") != "CAPTURED_CANDIDATE_NOT_ADMITTED"
            or receipt.get("source_url") != source.endpoint_or_feed
            or receipt.get("final_url") != source.endpoint_or_feed
            or receipt.get("raw_sha256") != RAW_SHA256):
        raise IssuerPageRefused("capture_registry_or_hash_drift")
    raw_path = Path(receipt.get("raw_path") or "")
    if raw_path.parent.resolve() != acquisition_path.parent.resolve():
        raise IssuerPageRefused("capture_raw_path_outside_archive")
    raw = raw_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != RAW_SHA256:
        raise IssuerPageRefused("capture_raw_bytes_drift")
    page = parse_asml_release(raw, source.endpoint_or_feed)
    published = page["published"].astimezone(timezone.utc)
    first_seen = _utc(receipt.get("first_seen_utc"))
    extraction_done = _utc(receipt.get("extraction_completed_utc"))
    if not published <= first_seen <= extraction_done <= datetime.now(timezone.utc):
        raise IssuerPageRefused("capture_information_time_invalid")
    metadata = receipt.get("publication_metadata") or []
    if not any(m.get("key") == "sc:publication_date"
               and _utc(m.get("content")) == published for m in metadata):
        raise IssuerPageRefused("capture_publication_metadata_drift")
    # This parser isolates the issuer article; the broader archived page text
    # remains available for audit but does not enter the model prompt.
    return world_digest.Item(
        item_id=hashlib.sha256(page["url"].encode()).hexdigest(),
        kind="article", source=SOURCE_ID, url=page["url"],
        title=page["title"], text=page["body"],
        first_seen_utc=first_seen.isoformat(), published_utc=published.isoformat(),
        tickers_named=["ASML"],
    )
