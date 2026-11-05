"""Offline, one-file Google News RSS station projection; no collector cursor.

Each invocation reads at most one dated JSONL source and writes only to an
explicit external evidence directory. A pass receipt is committed before its
separate projection cursor. The output has source pointers and clocks, no text.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
from uuid import uuid4

SOURCE = "google_news_rss_en_gb"
ADAPTER = "google-news-rss-metadata/1"
MAX_ROWS = 512
MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_ROW_BYTES = 256 * 1024
MAX_SECONDS = 30
EMPTY_SHA = hashlib.sha256(b"").hexdigest()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(data: object) -> bytes:
    return (json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            + "\n").encode("ascii")


def _clock(value: object, *, required: bool) -> str | None:
    if value is None or value == "":
        if required:
            raise ValueError("MISSING_FIRST_SEEN")
        return None
    if not isinstance(value, str):
        raise ValueError("MALFORMED_CLOCK")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("MALFORMED_CLOCK") from exc
    if parsed.tzinfo is None:
        raise ValueError("NAIVE_CLOCK")
    return parsed.astimezone(timezone.utc).isoformat()


def _atomic_json(path: Path, body: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp-" + uuid4().hex)
    try:
        with temp.open("xb") as stream:
            stream.write(_json(body))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _is_within(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _has_reparse(path: Path) -> bool:
    for component in (*reversed(path.parents), path):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(info.st_mode)
                or bool(getattr(info, "st_file_attributes", 0)
                        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
                or getattr(component, "is_junction", lambda: False)()):
            return True
    return False


def _load_cursor(path: Path, source_id: str, file_key: str) -> dict:
    if not path.exists():
        return {"schema": ADAPTER, "source_id": source_id, "source_file_key": file_key,
                "byte_offset": 0,
                "line_number": 0, "prefix_sha256": EMPTY_SHA, "last_pass_id": None}
    if path.stat().st_size > 4096:
        raise ValueError("CURSOR_INVALID")
    try:
        cursor = json.loads(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise ValueError("CURSOR_INVALID") from exc
    if (not isinstance(cursor, dict)
            or set(cursor) != {"schema", "source_id", "source_file_key", "byte_offset", "line_number",
                                   "prefix_sha256", "last_pass_id"}
            or cursor["schema"] != ADAPTER or cursor["source_id"] != source_id
            or cursor["source_file_key"] != file_key
            or type(cursor["byte_offset"]) is not int or cursor["byte_offset"] < 0
            or type(cursor["line_number"]) is not int or cursor["line_number"] < 0
            or not isinstance(cursor["prefix_sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", cursor["prefix_sha256"])
            or (cursor["last_pass_id"] is not None
                and (not isinstance(cursor["last_pass_id"], str)
                     or not re.fullmatch(r"[0-9a-f]{64}", cursor["last_pass_id"])))):
        raise ValueError("CURSOR_INVALID")
    return cursor


def _projection(raw: bytes, row: dict, *, source_id: str, file_key: str, line: int,
                start: int, end: int, projected_at: str) -> dict:
    if not isinstance(row, dict) or row.get("source") != SOURCE:
        raise ValueError("SOURCE_SCHEMA")
    first = _clock(row.get("first_seen_utc"), required=True)
    published = _clock(row.get("published_utc"), required=False)
    if published and published > first:
        raise ValueError("PUBLISHED_AFTER_FIRST_SEEN")
    if first > projected_at:
        raise ValueError("FUTURE_FIRST_SEEN")
    digest = _sha(raw)  # exact bytes, including the line terminator
    identity = _sha(f"{file_key}\0{start}\0{digest}".encode("utf-8"))
    return {"schema": ADAPTER, "observation_id": identity, "source": SOURCE,
            "source_class": "HEADLINE", "rights": "METADATA_POINTER_ONLY",
            "availability": "HINDSIGHT_PROJECTED",
            "source_id": source_id, "source_file_key": file_key,
            "line_number": line, "byte_start": start,
            "byte_end": end, "raw_row_sha256": digest,
            "event_at": None, "event_clock_status": "UNKNOWN",
            "published_at": published, "first_seen_at": first,
            "projected_at": projected_at, "issuer_edges": [], "causal_edges": [],
            "held_edges": [], "forecast_authority": "NONE", "owner_delivery": "NOT_ATTEMPTED"}


def project_file(source_file: Path, evidence_dir: Path, *, max_rows: int = MAX_ROWS,
                 max_source_bytes: int = MAX_SOURCE_BYTES,
                 max_row_bytes: int = MAX_ROW_BYTES,
                 now: datetime | None = None) -> dict:
    """Project one file. Return the same bounded summary written in the pass receipt."""
    if (not source_file.is_absolute() or not evidence_dir.is_absolute()
            or source_file.parent.name != SOURCE
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}\.jsonl", source_file.name)
            or _has_reparse(source_file) or not source_file.is_file()
            or max_rows < 1 or max_rows > MAX_ROWS
            or max_source_bytes < 1 or max_source_bytes > MAX_SOURCE_BYTES
            or max_row_bytes < 1 or max_row_bytes > MAX_ROW_BYTES):
        raise ValueError("INVALID_SOURCE_SCOPE")
    source_root = source_file.parents[2].resolve(strict=True)
    output = evidence_dir.resolve(strict=False)
    if _is_within(output, source_root) or _is_within(output, source_file.parent):
        raise ValueError("ACTIVE_LEDGER_OUTPUT_REFUSED")
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        raise ValueError("NAIVE_PROJECTION_CLOCK")
    projected_at = stamp.astimezone(timezone.utc).isoformat()
    source_id = SOURCE + "/" + source_file.name
    file_key = _sha((str(source_root) + "\0" + source_id).encode("utf-8"))[:24]
    cursor_path = output / "station_cursors" / f"{file_key}.json"
    cursor = _load_cursor(cursor_path, source_id, file_key)
    before = cursor["byte_offset"]
    initial_stat = source_file.stat()
    size = initial_stat.st_size
    started = time.monotonic()

    def refused(reason: str, *, blocked_row_sha256: str | None = None,
                attempted_rows: int = 0) -> dict:
        receipt = {"schema": ADAPTER, "coverage": "BLOCKED", "reason": reason,
                   "source_id": source_id, "source_file_key": file_key,
                   "source_path": str(source_file), "source_file_sha256": None,
                   "file_bytes_at_pass": size, "cursor_before": before,
                   "cursor_after": before, "line_before": cursor["line_number"],
                   "line_after": cursor["line_number"], "attempted_rows": attempted_rows,
                   "projected_rows": 0, "blocked_row_sha256": blocked_row_sha256,
                   "denominator": {"scope": "ONE_SOURCE_FILE", "exact": False,
                                   "eligible_rows": None,
                                   "rows_lower_bound": cursor["line_number"],
                                   "unread_bytes_at_snapshot": max(0, size - before)},
                   "projection_lag_seconds": None, "projected_at": projected_at,
                   "claims": "SOURCE_METADATA_ONLY;NO_ISSUER_CAUSAL_HELD_FORECAST_OWNER",
                   "projections": []}
        path = output / "station_passes" / ("blocked_" + uuid4().hex + ".json")
        _atomic_json(path, receipt)
        return {key: value for key, value in receipt.items() if key != "projections"} | {"receipt_path": str(path)}

    if size > max_source_bytes:
        return refused("SOURCE_FILE_CAP")
    if size < before:
        return refused("SOURCE_TRUNCATED")
    prefix = hashlib.sha256()
    with source_file.open("rb") as stream:
        left = before
        while left:
            chunk = stream.read(min(left, 65536))
            if not chunk:
                return refused("SOURCE_TRUNCATED")
            prefix.update(chunk)
            left -= len(chunk)
        if prefix.hexdigest() != cursor["prefix_sha256"]:
            return refused("SOURCE_PREFIX_REWRITTEN")
        projections = []
        chunk_hash = hashlib.sha256()
        while stream.tell() < size and len(projections) < max_rows:
            if time.monotonic() - started >= MAX_SECONDS:
                if not projections:
                    return refused("TIME_CAP")
                break
            start = stream.tell()
            raw = stream.readline(size - start)
            if not raw.endswith(b"\n"):
                return refused("INCOMPLETE_TAIL", blocked_row_sha256=_sha(raw),
                               attempted_rows=len(projections) + 1)
            if len(raw) > max_row_bytes:
                return refused("OVERSIZED_ROW", blocked_row_sha256=_sha(raw),
                               attempted_rows=len(projections) + 1)
            try:
                row = json.loads(raw)
                projection = _projection(raw, row, source_id=source_id, file_key=file_key,
                                         line=cursor["line_number"] + len(projections) + 1,
                                         start=start, end=stream.tell(),
                                         projected_at=projected_at)
            except (ValueError, UnicodeError) as exc:
                reason = str(exc) if isinstance(exc, ValueError) and str(exc) in {
                    "SOURCE_SCHEMA", "MISSING_FIRST_SEEN", "MALFORMED_CLOCK",
                    "NAIVE_CLOCK", "PUBLISHED_AFTER_FIRST_SEEN", "FUTURE_FIRST_SEEN"} else "MALFORMED_ROW"
                return refused(reason, blocked_row_sha256=_sha(raw),
                               attempted_rows=len(projections) + 1)
            projections.append(projection)
            prefix.update(raw)
            chunk_hash.update(raw)
        after = stream.tell()
    final_stat = source_file.stat()
    if (final_stat.st_size != size or final_stat.st_mtime_ns != initial_stat.st_mtime_ns
            or final_stat.st_ino != initial_stat.st_ino):
        return refused("SOURCE_CHANGED_DURING_PASS", attempted_rows=len(projections))
    at_eof = after == size
    lag = [int((stamp.astimezone(timezone.utc) -
                datetime.fromisoformat(p["first_seen_at"])).total_seconds())
           for p in projections]
    pass_id = _sha(f"{file_key}\0{before}\0{after}\0{chunk_hash.hexdigest()}".encode())
    receipt = {"schema": ADAPTER, "pass_id": pass_id, "coverage": "PARTIAL",
               "reason": "SOURCE_FILE_AT_SNAPSHOT_EOF" if at_eof else "PASS_CAP",
               "source_id": source_id, "source_file_key": file_key,
               "source_path": str(source_file),
               "source_file_sha256": prefix.hexdigest() if at_eof else None,
               "file_bytes_at_pass": size, "cursor_before": before, "cursor_after": after,
               "line_before": cursor["line_number"],
               "line_after": cursor["line_number"] + len(projections),
               "attempted_rows": len(projections), "projected_rows": len(projections),
               "blocked_row_sha256": None,
               "denominator": {"scope": "ONE_SOURCE_FILE", "exact": at_eof,
                               "eligible_rows": cursor["line_number"] + len(projections) if at_eof else None,
                               "rows_lower_bound": cursor["line_number"] + len(projections),
                               "unread_bytes_at_snapshot": size - after},
               "projection_lag_seconds": {"min": min(lag), "max": max(lag)} if lag else None,
               "projected_at": projected_at,
               "claims": "SOURCE_METADATA_ONLY;NO_ISSUER_CAUSAL_HELD_FORECAST_OWNER",
               "previous_pass_id": cursor["last_pass_id"], "projections": projections}
    path = output / "station_passes" / f"{pass_id}.json"
    if path.exists():
        old = json.loads(path.read_bytes())
        if (old.get("pass_id") != pass_id or old.get("cursor_before") != before
                or old.get("cursor_after") != after
                or [(p["byte_start"], p["raw_row_sha256"]) for p in old["projections"]]
                != [(p["byte_start"], p["raw_row_sha256"]) for p in projections]):
            return refused("PASS_REPLAY_CONFLICT")
        receipt = old
    else:
        _atomic_json(path, receipt)
    if after != before:
        _atomic_json(cursor_path, {"schema": ADAPTER, "source_id": source_id,
                                   "source_file_key": file_key,
                                   "byte_offset": after, "line_number": receipt["line_after"],
                                   "prefix_sha256": prefix.hexdigest(), "last_pass_id": pass_id})
    return {key: value for key, value in receipt.items() if key != "projections"} | {"receipt_path": str(path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source-file", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--max-rows", type=int, default=MAX_ROWS)
    args = parser.parse_args(argv)
    result = project_file(args.source_file, args.evidence_dir, max_rows=args.max_rows)
    print(_json(result).decode("ascii").rstrip())
    return 2 if result["coverage"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
