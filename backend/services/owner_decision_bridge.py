"""Read-only, explicit saved-corpus locator bridge for a selected E2 event.

Container hashes prove current bytes; row clocks and issuer claims are not
independently authenticated point-in-time evidence. No owner send lives here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

from backend.services import owner_decision_view as view
from backend.services import provisional_event_review as e2
from scripts import world_digest_provisional as hook


@dataclass(frozen=True)
class RowLocator:
    source_key: str
    source_sha256: str
    relative_corpus_path: str
    container_sha256: str
    line_number: int | None


def _refuse(code: str) -> None:
    raise view.ViewRefused(code)


def _container(root: Path, locator: RowLocator) -> tuple[Path, str, str]:
    rel = locator.relative_corpus_path
    if type(rel) is not str or "\\" in rel or not rel or rel.startswith("/"):
        _refuse("INVALID_CORPUS_PATH")
    parts = rel.split("/")
    if any(not part or part in (".", "..") or ":" in part for part in parts):
        _refuse("INVALID_CORPUS_PATH")
    if len(parts) == 2 and parts[0] in hook.SOURCES:
        kind = "JSONL"
        match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\.jsonl", parts[1])
        if type(locator.line_number) is not int or not 1 <= locator.line_number <= hook.MAX_LINES:
            _refuse("INVALID_LINE_NUMBER")
    elif (len(parts) == 4 and parts[:2] in (["dowjones", "marketwatch"], ["dowjones", "wsj"])
          and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.json", parts[3])):
        kind = "PAGE"
        match = re.fullmatch(r"\d{4}-\d{2}-\d{2}", parts[2])
        if locator.line_number is not None:
            _refuse("INVALID_LINE_NUMBER")
    else:
        _refuse("INVALID_CORPUS_PATH")
    if not match:
        _refuse("INVALID_CORPUS_PATH")
    day = match[1] if kind == "JSONL" else parts[2]
    try:
        if date.fromisoformat(day).isoformat() != day:
            _refuse("INVALID_CORPUS_DAY")
    except ValueError:
        _refuse("INVALID_CORPUS_DAY")
    return root.joinpath(*parts), kind, day


def _lines(data: bytes) -> list[bytes]:
    chunks = data.split(b"\n")
    if chunks[-1] == b"":
        chunks.pop()
    rows = [part + (b"\n" if index < len(chunks) - 1 or data.endswith(b"\n") else b"")
            for index, part in enumerate(chunks)]
    if len(rows) > hook.MAX_LINES:
        _refuse("LINE_CAP")
    return rows


def _sec_accession(url: str) -> None:
    """Require the exact SEC path form that the hook groups by CIK/accession."""
    try:
        parsed = urlsplit(url)
        valid = (parsed.scheme == "https" and parsed.hostname in {"sec.gov", "www.sec.gov"}
                 and not parsed.username and not parsed.password and parsed.port in (None, 443)
                 and re.fullmatch(r"/Archives/edgar/data/[0-9]{1,10}/[0-9]{18}/[^/]+",
                                  parsed.path, re.IGNORECASE))
    except ValueError:
        valid = False
    if not valid:
        _refuse("INVALID_SEC_ACCESSION")


def _verify_row(raw: bytes, payload: bytes, source: dict[str, Any], locator: RowLocator,
                kind: str, day: str, path: Path, event_key: str) -> None:
    if (not payload or len(payload) > e2.MAX_SOURCE_BYTES
            or view._digest(raw) != source["proof_witness_sha256"]
            or view._digest(payload) != source["source_sha256"]):
        _refuse("ROW_HASH_MISMATCH")
    try:
        row = json.loads(payload.decode("utf-8"), object_pairs_hook=view._unique_object,
                         parse_constant=lambda _: _refuse("INVALID_ROW_JSON"))
        if type(row) is not dict or str(row.get("page_kind") or "").startswith("stock"):
            _refuse("INVALID_ROW")
        first = hook._utc(row.get("first_seen_utc"))
        published_raw = row.get("published_utc")
        published = hook._utc(published_raw) if published_raw else None
        if first is None or (published_raw and published is None) or (published and published > first):
            _refuse("INVALID_ROW_CLOCK")
        if first.date().isoformat() != day:
            _refuse("CORPUS_DAY_MISMATCH")
        title = str(row.get("title") or "")
        body = str(row.get("body") or row.get("text") or "")
        if len(title) < 12 or (kind == "PAGE" and len(body) < 400):
            _refuse("INELIGIBLE_ROW")
        url = str(row.get("url") or "")
        identity = hook.WD.norm_url(url) or str(row.get("raw_id") or "")
        if not identity:
            _refuse("MISSING_SOURCE_IDENTITY")
        expected_key = "source:" + view._digest(identity.encode("utf-8"))[:40]
        if expected_key != locator.source_key or source["source_id"] != e2._stable_id("source", expected_key):
            _refuse("SOURCE_IDENTITY_MISMATCH")
        source_dir = path.parent.name if kind == "JSONL" else ""
        derived_kind = ("FILING" if source_dir.startswith("sec_edgar_") else
                        "HEADLINE" if source_dir == "google_news_rss_en_gb" else
                        "REFERENCE_PAGE" if "analyst estimates" in title.casefold() else
                        "ARTICLE" if len(body) >= 400 else "REFERENCE_PAGE")
        if derived_kind != source["kind"]:
            _refuse("SOURCE_KIND_MISMATCH")
        if derived_kind == "FILING":
            _sec_accession(url)
        if hook._event_key(identity, filing=derived_kind == "FILING", raw_url=url) != event_key:
            _refuse("EVENT_IDENTITY_MISMATCH")
        first_iso = e2._iso(first)
        if (source["first_seen_utc"] != first_iso or source["version_seen_utc"] != first_iso
                or source["proof_known_at_utc"] != first_iso
                or source["published_utc"] != (e2._iso(published) if published else None)):
            _refuse("ROW_CLOCK_MISMATCH")
    except (UnicodeError, json.JSONDecodeError, TypeError, OverflowError, RecursionError, ValueError) as exc:
        if isinstance(exc, view.ViewRefused):
            raise
        _refuse("INVALID_ROW")


def build_selected_event_view(*, receipt_path: Path, receipt_sha256: str,
                              selected_event_id: str, corpus_root: Path,
                              locators: list[RowLocator] | tuple[RowLocator, ...],
                              station: view.StationPin | None = None) -> dict[str, Any]:
    """Return an E3 review view for exactly one pinned E2 group; never write."""
    view._hash(selected_event_id)
    if (not isinstance(corpus_root, Path) or not corpus_root.is_absolute()
            or corpus_root.name != "news_corpus" or corpus_root.drive.startswith("\\\\")):
        _refuse("INVALID_CORPUS_ROOT")
    receipt = view._parse_receipt(view._read_pinned(receipt_path, receipt_sha256,
                                                    e2.MAX_RECEIPT_BYTES), require_one_group=False)
    groups = receipt["groups"]
    if sum(len(group["sources"]) for group in groups) > hook.MAX_SOURCES:
        _refuse("SOURCE_COUNT_CAP")
    event_ids: set[str] = set()
    event_keys: set[str] = set()
    source_ids: set[str] = set()
    chosen = None
    for group in groups:
        if group["event_id"] in event_ids or group["event_key"] in event_keys:
            _refuse("DUPLICATE_EVENT")
        event_ids.add(group["event_id"])
        event_keys.add(group["event_key"])
        view._validate_group_edges(group)
        for source in group["sources"]:
            if source["source_id"] in source_ids:
                _refuse("DUPLICATE_SOURCE_ID")
            source_ids.add(source["source_id"])
        if group["event_id"] == selected_event_id:
            chosen = group
    if chosen is None:
        _refuse("EVENT_NOT_FOUND")
    sources = chosen["sources"]
    if (type(locators) not in (list, tuple) or len(locators) != len(sources)
            or not 1 <= len(locators) <= hook.MAX_SOURCES):
        _refuse("LOCATOR_COUNT")
    selected = {(source["source_id"], source["source_sha256"]): source for source in sources}
    if len(selected) != len(sources):
        _refuse("DUPLICATE_SELECTED_SOURCE")
    matched: set[tuple[str, str]] = set()
    containers: dict[str, tuple[str, bytes, str, str]] = {}
    total_bytes = 0
    total_lines = 0
    for locator in locators:
        if type(locator) is not RowLocator:
            _refuse("INVALID_LOCATOR")
        key, sha, container_sha = (view._key(locator.source_key), view._hash(locator.source_sha256),
                                   view._hash(locator.container_sha256))
        identity = (e2._stable_id("source", key), sha)
        if identity not in selected or identity in matched:
            _refuse("LOCATOR_BINDING")
        matched.add(identity)
        path, kind, day = _container(corpus_root, locator)
        cached = containers.get(locator.relative_corpus_path)
        if cached is None:
            if len(containers) >= hook.MAX_FILES:
                _refuse("FILE_CAP")
            data = view._read_pinned(path, container_sha,
                                     min(hook.MAX_FILE_BYTES, hook.MAX_SCAN_BYTES - total_bytes))
            total_bytes += len(data)
            if total_bytes > hook.MAX_SCAN_BYTES:
                _refuse("CONTAINER_TOTAL_CAP")
            row_count = len(_lines(data)) if kind == "JSONL" else 1
            total_lines += row_count
            if total_lines > hook.MAX_LINES:
                _refuse("LINE_CAP")
            containers[locator.relative_corpus_path] = (container_sha, data, kind, day)
        else:
            if cached[0] != container_sha or cached[2:] != (kind, day):
                _refuse("CONTAINER_PIN_CONFLICT")
            data = cached[1]
        raw = (_lines(data)[locator.line_number - 1]
               if kind == "JSONL" and locator.line_number <= len(_lines(data)) else
               data if kind == "PAGE" else None)
        if raw is None:
            _refuse("LINE_NOT_FOUND")
        payload = raw.rstrip(b"\r\n") if kind == "JSONL" else raw
        _verify_row(raw, payload, selected[identity], locator, kind, day, path,
                    chosen["event_key"])
    if matched != set(selected):
        _refuse("LOCATOR_BINDING")
    return view._render_view(receipt, chosen, view._station_view(station))
