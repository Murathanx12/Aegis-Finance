"""Frozen copied-body consistency audit; no claim reads or native certification."""
from __future__ import annotations

import argparse
import hashlib
import json
import ntpath
import os
from pathlib import Path, PureWindowsPath
import re
import stat
import sys
from datetime import datetime, timezone

BODY_CAP = 16 * 1024**2
OBJECT_CAP = 1024**2
PRIVATE_ROOT = Path("C:/Users/mrthn/aegis-recovery-evidence/beta-v2-owner-20261025")
SCHEMA = "one_body_trace_input/1"


class TraceRefused(ValueError):
    """Controlled refusal code; external values never enter exception messages."""


def require(condition, code):
    if not condition:
        raise TraceRefused(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value, length=64):
    require(type(value) is str and re.fullmatch(r"[0-9a-f]{%d}" % length, value) is not None,
            "invalid_digest")
    return value


def integer(value, minimum=0):
    require(type(value) is int and minimum <= value <= 2**63 - 1, "invalid_integer")
    return value


def locator(value):
    require(type(value) is str and 0 < len(value) <= 2048
            and all(ord(c) >= 32 for c in value)
            and (Path(value).is_absolute() or PureWindowsPath(value).is_absolute()),
            "invalid_locator")
    return value


def clock(value, nullable=False):
    if value is None and nullable:
        return None
    require(type(value) is str and 0 < len(value) <= 64, "invalid_clock")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(parsed.tzinfo is not None and parsed.utcoffset() is not None, "invalid_clock")
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError):
        raise TraceRefused("invalid_clock") from None


def fields(value, expected):
    require(type(value) is dict and set(value) == set(expected.split()), "invalid_schema")
    return value


def pairs(values):
    result = {}
    for key, value in values:
        require(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def constant(_):
    raise TraceRefused("nonfinite_json")


def document(raw, cap):
    require(type(raw) is bytes and 0 < len(raw) <= cap, "input_size")
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
        require(type(result) is dict, "json_root_object_required")
        pending = [(result, 0)]
        while pending:
            value, depth = pending.pop()
            require(depth <= 64, "json_depth")
            if type(value) is dict:
                pending.extend((v, depth + 1) for v in value.values())
            elif type(value) is list:
                pending.extend((v, depth + 1) for v in value)
            elif type(value) is float:
                require(value not in (float("inf"), float("-inf")) and value == value, "nonfinite_json")
        return result
    except TraceRefused:
        raise
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        raise TraceRefused("invalid_json") from None


def pointer(value, source_id):
    if value is None:
        return None
    fields(value, "path offset length row_sha256 article_sha declared_prefix_sha256 prefix_end")
    locator(value["path"])
    integer(value["offset"])
    integer(value["length"], 1)
    require(value["length"] <= 256 * 1024, "pointer_length")
    digest(value["row_sha256"])
    digest(value["article_sha"], 20)
    require(value["article_sha"] == source_id, "pointer_body_mismatch")
    if value["declared_prefix_sha256"] is None:
        require(value["prefix_end"] is None, "invalid_prefix_reference")
    else:
        digest(value["declared_prefix_sha256"])
        integer(value["prefix_end"], 1)
        require(value["prefix_end"] >= value["offset"] + value["length"], "invalid_prefix_reference")
    return {**value, "status": "DECLARED_NOT_READ", "row_hash_status": "DECLARED_NOT_READ",
            "prefix_hash_status": "DECLARED_UPSTREAM_REFERENCE" if value["declared_prefix_sha256"] else "NOT_SUPPLIED",
            "bytes_read": 0}


def parse_manifest(raw, expected_sha256):
    require(type(raw) is bytes and 0 < len(raw) <= OBJECT_CAP, "input_size")
    require(sha(raw) == digest(expected_sha256), "manifest_hash_mismatch")
    m = fields(document(raw, OBJECT_CAP),
               "schema body status generation_id reader_source_sha256 pool_pid item_id source_id text_sha256 text_chars published_utc first_seen_utc witness_observed_utc claim_pointer")
    require(m["schema"] == SCHEMA, "invalid_schema")
    for name in ("generation_id", "reader_source_sha256", "item_id", "text_sha256"):
        digest(m[name])
    digest(m["source_id"], 20)
    integer(m["pool_pid"], 1)
    integer(m["text_chars"], 1)
    for name, names, cap in (("body", "copy_path native_path sha256 bytes", BODY_CAP),
                              ("status", "path sha256 bytes", OBJECT_CAP)):
        row = fields(m[name], names)
        digest(row["sha256"])
        integer(row["bytes"], 1)
        require(row["bytes"] <= cap, "input_size")
    locator(m["body"]["copy_path"])
    locator(m["body"]["native_path"])
    locator(m["status"]["path"])
    require(ntpath.normcase(ntpath.normpath(m["body"]["copy_path"])) !=
            ntpath.normcase(ntpath.normpath(m["body"]["native_path"])), "copy_native_alias")
    clock(m["published_utc"], nullable=True)
    clock(m["first_seen_utc"])
    clock(m["witness_observed_utc"])
    pointer(m["claim_pointer"], m["source_id"])
    return m


def validate_bundle(manifest_raw, body_raw, status_raw, *, manifest_sha256):
    """Pure bytes-in/projection-out. No paths are opened, resolved or followed."""
    m = parse_manifest(manifest_raw, manifest_sha256)
    for raw, row, cap in ((body_raw, m["body"], BODY_CAP), (status_raw, m["status"], OBJECT_CAP)):
        require(type(raw) is bytes and 0 < len(raw) <= cap, "input_size")
        require(len(raw) == row["bytes"] and sha(raw) == row["sha256"], "input_pin_mismatch")
    body = document(body_raw, BODY_CAP)
    status = document(status_raw, OBJECT_CAP)
    require({"sha", "text", "page_kind", "first_seen_utc", "published_utc", "chars"} <= body.keys(),
            "body_fields_required")
    require(body.get("page_kind") == "article", "article_required")
    require(body.get("sha") == m["source_id"], "body_source_mismatch")
    text = body.get("text")
    require(type(text) is str and bool(text.strip()), "body_text_required")
    try:
        text_hash = sha(text.encode("utf-8"))
    except UnicodeError:
        raise TraceRefused("invalid_text_utf8") from None
    require(text_hash == m["text_sha256"] and len(text) == m["text_chars"], "text_pin_mismatch")
    # Exact pure identity expression from pinned dowjones_claims.text_sha;
    # this normalized 20-char ID is distinct from the full raw-text SHA256.
    normalized_id = sha(re.sub(r"\s+", " ", text).strip().encode("utf-8"))[:20]
    require(normalized_id == m["source_id"], "source_text_mismatch")
    if "chars" in body:
        require(type(body["chars"]) is int and body["chars"] == len(text), "text_count_mismatch")
    require(clock(body.get("published_utc"), nullable=True) == clock(m["published_utc"], nullable=True)
            and clock(body.get("first_seen_utc")) == clock(m["first_seen_utc"]), "metadata_clock_mismatch")
    generation = status.get("generation")
    lineage = status.get("carry_lineage")
    require(type(generation) is dict and type(lineage) is dict, "generation_required")
    require(generation.get("schema") == "reader_pool_generation/1" and generation.get("status") == "NATIVE_SELF",
            "generation_unqualified")
    require(generation.get("generation_id") == m["generation_id"]
            and generation.get("reader_source_sha256") == m["reader_source_sha256"]
            and type(generation.get("pid")) is int and generation["pid"] == m["pool_pid"]
            and type(status.get("pid")) is int and status["pid"] == m["pool_pid"], "generation_mismatch")
    require(lineage.get("schema") == "native_pool_carry_lineage/2"
            and lineage.get("generation") == generation, "lineage_generation_mismatch")
    require(lineage.get("body_history_truncated") is False, "truncated_witness_history")
    evidence = lineage.get("body_evidence")
    require(type(evidence) is list and all(type(row) is dict for row in evidence), "invalid_witness_array")
    require(type(lineage.get("body_evidence_total")) is int and lineage["body_evidence_total"] == len(evidence),
            "witness_count_mismatch")
    matches = [row for row in evidence if row.get("item_id") == m["item_id"] or row.get("source_id") == m["source_id"]]
    require(len(matches) == 1, "ambiguous_or_missing_witness")
    witness = matches[0]
    require(witness.get("status") == "ACTUAL_BODY_FILE_READ_BACK"
            and witness.get("item_id") == m["item_id"] and witness.get("source_id") == m["source_id"]
            and witness.get("file_sha256") == m["body"]["sha256"]
            and witness.get("body_sha256") == m["text_sha256"]
            and type(witness.get("body_chars")) is int and witness["body_chars"] == len(text)
            and witness.get("path") == m["body"]["native_path"], "witness_mismatch")
    require(witness.get("duplicate") is False, "nonduplicate_required")
    require(clock(status.get("t")) == clock(m["witness_observed_utc"]), "observation_clock_mismatch")
    claim = pointer(m["claim_pointer"], m["source_id"])
    return {
        "schema": "one_body_trace/1", "status": "COPIED_BODY_FILE_CONSISTENT",
        "manifest_sha256": manifest_sha256, "generation_id": m["generation_id"],
        "reader_source_sha256": m["reader_source_sha256"], "pool_pid": m["pool_pid"],
        "item_id": m["item_id"], "source_id": m["source_id"],
        "copy": {"path": m["body"]["copy_path"], "sha256": sha(body_raw), "bytes": len(body_raw),
                 "full_file_hash_status": "VERIFIED_COPY_BYTES", "text_sha256": text_hash,
                 "text_chars": len(text), "page_kind": "article", "duplicate": False},
        "native": {"path": m["body"]["native_path"], "status": "DECLARED_NOT_READ", "bytes_read": 0},
        "witness": {"path": m["status"]["path"], "sha256": sha(status_raw), "bytes": len(status_raw),
                    "observed_utc": clock(status["t"]), "carry_observed_utc": clock(lineage.get("observed_utc")),
                    "binding": "SUPPLIED_FROZEN_STATUS_CONSISTENCY_ONLY"},
        "metadata": {"declared_published_utc": clock(m["published_utc"], nullable=True),
                     "declared_first_seen_utc": clock(m["first_seen_utc"]), "storage_completion_utc": None},
        "body_to_claim": {"status": "DECLARED_NOT_READ" if claim else "ROW_LOCATOR_REQUIRED",
                          "edge": "UNKNOWN", "pointer": claim},
        "actual_consumed_ids": None,
        "downstream": {"typed": "UNKNOWN", "event": "UNKNOWN", "forecast": "UNKNOWN", "position": "UNKNOWN"},
        "qualification": "FILE_CONSISTENCY_NOT_NATIVE_AUTHENTICITY_QUALITY_OR_FULLTEXT",
    }


def private_path(value, root):
    try:
        path = Path(value).resolve(strict=True)
        require(path.is_relative_to(root), "outside_private_root")
        require(path.is_file(), "regular_file_required")
        return path
    except OSError:
        raise TraceRefused("input_unavailable") from None


def read_once(path, cap):
    try:
        with path.open("rb") as handle:
            before = os.fstat(handle.fileno())
            require(stat.S_ISREG(before.st_mode), "regular_file_required")
            require(0 < before.st_size <= cap, "input_size")
            raw = handle.read(cap + 1)
            after = os.fstat(handle.fileno())
        def identity(s):
            return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(identity(before) == identity(after) and len(raw) == before.st_size, "changed_input")
        return raw, identity(after)
    except OSError:
        raise TraceRefused("input_unavailable") from None


def audit_to_private(manifest_path, manifest_sha256, output_dir, *, private_root=PRIVATE_ROOT):
    """Read exactly manifest/copy/status, re-read all three, then CreateNew output."""
    try:
        locator(str(private_root))
        locator(manifest_path)
        locator(output_dir)
        root = Path(private_root).resolve(strict=True)
        require(root.is_relative_to(PRIVATE_ROOT.resolve(strict=True)), "outside_private_root")
        require(root.is_dir(), "private_root_required")
        output = Path(output_dir).resolve(strict=False)
        require(output != root and output.is_relative_to(root), "outside_private_root")
        manifest_path = private_path(manifest_path, root)
        first = [read_once(manifest_path, OBJECT_CAP)]
        m = parse_manifest(first[0][0], manifest_sha256)
        body_path = private_path(m["body"]["copy_path"], root)
        status_path = private_path(m["status"]["path"], root)
        paths = (manifest_path, body_path, status_path)
        require(len(set(paths)) == 3, "input_path_alias")
        first.extend((read_once(body_path, BODY_CAP), read_once(status_path, OBJECT_CAP)))
        report = validate_bundle(*(row[0] for row in first), manifest_sha256=manifest_sha256)
        for path, cap, original in zip(paths, (OBJECT_CAP, BODY_CAP, OBJECT_CAP), first):
            current = read_once(path, cap)
            require(current == original, "changed_input")
        report["io"] = {"distinct_inputs": 3, "input_bytes": sum(len(row[0]) for row in first),
                        "integrity_reread_bytes": sum(len(row[0]) for row in first),
                        "claim_native_or_downstream_bytes_read": 0}
        raw = (json.dumps(report, ensure_ascii=True, allow_nan=False, indent=2) + "\n").encode("utf-8")
        output.mkdir()  # Exclusive new directory; never reopen a previous run.
        with (output / "TRACE.json").open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        return {"status": report["status"], "report_sha256": sha(raw)}
    except TraceRefused:
        raise
    except (OSError, ValueError, RecursionError):
        raise TraceRefused("private_io_refused") from None


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise TraceRefused("invalid_arguments")


def main(argv=None):
    try:
        parser = Parser(description=__doc__)
        parser.add_argument("--manifest", required=True)
        parser.add_argument("--manifest-sha256", required=True)
        parser.add_argument("--output-dir", required=True)
        args = parser.parse_args(argv)
        result = audit_to_private(args.manifest, args.manifest_sha256, args.output_dir)
        print(json.dumps(result, sort_keys=True))
        return 0
    except TraceRefused as exc:
        print(json.dumps({"status": "REFUSED", "code": str(exc)}))
        return 2
    except Exception:
        print(json.dumps({"status": "REFUSED", "code": "internal_error"}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
