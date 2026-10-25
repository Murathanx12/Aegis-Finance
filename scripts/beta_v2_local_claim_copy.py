"""Audit one supplied copied local-claim line; never locate native records."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import ntpath
import os
from pathlib import Path, PureWindowsPath
import re
import stat
import sys

PRIVATE_ROOT = Path("C:/Users/mrthn/aegis-recovery-evidence/beta-v2-owner-20261025")
OBJECT_CAP = 64 * 1024
ROW_CAP = 256 * 1024
SCHEMA = "copied_local_claim_input/1"


class ClaimCopyRefused(ValueError):
    """Only constant controlled codes; no external input in diagnostics."""


def require(condition, code):
    if not condition:
        raise ClaimCopyRefused(code)


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
            and all(ord(c) >= 32 for c in value) and not any(c in value for c in "?#")
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
        raise ClaimCopyRefused("invalid_clock") from None


def fields(value, names):
    require(type(value) is dict and set(value) == set(names.split()), "invalid_schema")
    return value


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def constant(_):
    raise ClaimCopyRefused("nonfinite_json")


def document(raw, cap):
    require(type(raw) is bytes and 0 < len(raw) <= cap, "input_size")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
        require(type(value) is dict, "json_root_object_required")
        pending = [(value, 0)]
        while pending:
            item, depth = pending.pop()
            require(depth <= 64, "json_depth")
            if type(item) is dict:
                for key in item:
                    key.encode("utf-8")
                pending.extend((v, depth + 1) for v in item.values())
            elif type(item) is list:
                pending.extend((v, depth + 1) for v in item)
            elif type(item) is str:
                item.encode("utf-8")  # Reject escaped lone surrogates, too.
            elif type(item) is float:
                require(math.isfinite(item), "nonfinite_json")
        return value
    except ClaimCopyRefused:
        raise
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        raise ClaimCopyRefused("invalid_json") from None


def parse_pointer(value, source_id):
    p = fields(value, "path offset length row_sha256 article_sha declared_prefix_sha256 prefix_end")
    locator(p["path"])
    integer(p["offset"])
    integer(p["length"], 1)
    require(p["length"] <= ROW_CAP and p["offset"] + p["length"] <= 2**63 - 1,
            "pointer_length")
    digest(p["row_sha256"])
    require(digest(p["article_sha"], 20) == source_id, "pointer_body_mismatch")
    if p["declared_prefix_sha256"] is None:
        require(p["prefix_end"] is None, "invalid_prefix_reference")
    else:
        digest(p["declared_prefix_sha256"])
        integer(p["prefix_end"], 1)
        require(p["prefix_end"] >= p["offset"] + p["length"], "invalid_prefix_reference")
    return p


def parse_manifest(raw, manifest_sha256):
    require(type(raw) is bytes and 0 < len(raw) <= OBJECT_CAP, "input_size")
    require(sha(raw) == digest(manifest_sha256), "manifest_hash_mismatch")
    m = fields(document(raw, OBJECT_CAP), "schema trace body_binding claim_copy claim_pointer")
    require(m["schema"] == SCHEMA, "invalid_schema")
    binding = fields(m["body_binding"],
                     "source_id item_id text_sha256 generation_id reader_source_sha256 pool_pid")
    digest(binding["source_id"], 20)
    for key in ("item_id", "text_sha256", "generation_id", "reader_source_sha256"):
        digest(binding[key])
    integer(binding["pool_pid"], 1)
    for key, cap in (("trace", OBJECT_CAP), ("claim_copy", ROW_CAP)):
        if key == "claim_copy" and m[key] is None:
            continue
        desc = fields(m[key], "copy_path sha256 bytes")
        locator(desc["copy_path"])
        digest(desc["sha256"])
        require(integer(desc["bytes"], 1) <= cap, "input_size")
    require((m["claim_pointer"] is None) == (m["claim_copy"] is None), "incomplete_row_locator")
    if m["claim_pointer"] is not None:
        p = parse_pointer(m["claim_pointer"], binding["source_id"])
        require(p["length"] == m["claim_copy"]["bytes"]
                and p["row_sha256"] == m["claim_copy"]["sha256"], "pointer_copy_pin_mismatch")
        require(ntpath.normcase(ntpath.normpath(p["path"])) !=
                ntpath.normcase(ntpath.normpath(m["claim_copy"]["copy_path"])), "copy_native_alias")
    return m


def validate_trace(raw, m):
    desc = m["trace"]
    require(type(raw) is bytes and len(raw) == desc["bytes"] and sha(raw) == desc["sha256"],
            "trace_pin_mismatch")
    t = document(raw, OBJECT_CAP)
    require(t.get("schema") == "one_body_trace/1"
            and t.get("status") == "COPIED_BODY_FILE_CONSISTENT"
            and t.get("qualification") == "FILE_CONSISTENCY_NOT_NATIVE_AUTHENTICITY_QUALITY_OR_FULLTEXT",
            "trace_unqualified")
    for name, value in m["body_binding"].items():
        if name == "text_sha256":
            continue  # c91 TRACE stores this under copy, never requires it at top level.
        require(type(t.get(name)) is type(value) and t[name] == value, "trace_binding_mismatch")
    c = t.get("copy")
    require(type(c) is dict and c.get("page_kind") == "article" and c.get("duplicate") is False
            and c.get("full_file_hash_status") == "VERIFIED_COPY_BYTES", "trace_copy_unqualified")
    digest(c.get("sha256"))
    require(digest(c.get("text_sha256")) == m["body_binding"]["text_sha256"], "trace_binding_mismatch")
    integer(c.get("bytes"), 1)
    integer(c.get("text_chars"), 1)
    require(t.get("actual_consumed_ids", "MISSING") is None
            and t.get("downstream") == dict.fromkeys(("typed", "event", "forecast", "position"), "UNKNOWN"),
            "trace_downstream_unqualified")
    # This first adapter accepts the existing body-only TRACE, not a later upgraded chain.
    require(t.get("body_to_claim") == {"status": "ROW_LOCATOR_REQUIRED", "edge": "UNKNOWN", "pointer": None},
            "trace_stage_unqualified")
    meta = fields(t.get("metadata"), "declared_published_utc declared_first_seen_utc storage_completion_utc")
    require(meta["storage_completion_utc"] is None, "trace_stage_unqualified")
    clock(meta["declared_first_seen_utc"])
    clock(meta["declared_published_utc"], nullable=True)
    witness = t.get("witness")
    require(type(witness) is dict
            and witness.get("binding") == "SUPPLIED_FROZEN_STATUS_CONSISTENCY_ONLY", "trace_witness_unqualified")
    clock(witness.get("observed_utc"))
    return t


def validate_row(raw, m, t):
    desc = m["claim_copy"]
    require(type(raw) is bytes and 0 < len(raw) <= ROW_CAP, "input_size")
    require(len(raw) == desc["bytes"] and sha(raw) == desc["sha256"], "row_pin_mismatch")
    require(raw.endswith(b"\n"), "complete_jsonl_line_required")
    content = raw[:-2] if raw.endswith(b"\r\n") else raw[:-1]
    require(b"\r" not in content and b"\n" not in content, "one_jsonl_line_required")
    r = fields(document(content, ROW_CAP),
               "source_id article_sha url first_seen_utc published_utc pit_grade ticker direction horizon_days_stated magnitude_bucket quote paraphrase")
    require(digest(r["article_sha"], 20) == m["body_binding"]["source_id"], "row_body_mismatch")
    require(type(r["source_id"]) is str and 0 < len(r["source_id"]) <= 128, "invalid_column_label")
    require(r["url"] is None or (type(r["url"]) is str and len(r["url"]) <= 8192), "invalid_row_field")
    require(type(r["ticker"]) is str and re.fullmatch(r"[A-Z]{1,5}(\.[A-Z])?", r["ticker"]) is not None,
            "invalid_row_field")
    require(type(r["direction"]) is str and r["direction"] in ("up", "down", "none"), "invalid_row_field")
    require(type(r["magnitude_bucket"]) is str
            and r["magnitude_bucket"] in ("small", "medium", "large", "unstated"), "invalid_row_field")
    require(type(r["pit_grade"]) is str and r["pit_grade"] in ("first_seen_only", "archive"), "invalid_row_field")
    horizon = r["horizon_days_stated"]
    require(type(horizon) is int and horizon in (5, 21, 63, 126, 252), "invalid_row_field")
    for key, cap in (("quote", 300), ("paraphrase", 200)):
        require(type(r[key]) is str and bool(r[key].strip()) and len(r[key]) <= cap, "invalid_row_field")
    require(clock(r["first_seen_utc"]) == clock(t["metadata"]["declared_first_seen_utc"])
            and clock(r["published_utc"], nullable=True) ==
            clock(t["metadata"]["declared_published_utc"], nullable=True), "metadata_clock_mismatch")
    return r


def verify_local_claim_copy(trace_raw, row_manifest_raw, row_raw=None, *, manifest_sha256):
    """Pure validation of supplied bytes. No input/native/claim paths are followed."""
    m = parse_manifest(row_manifest_raw, manifest_sha256)
    t = validate_trace(trace_raw, m)
    p = m["claim_pointer"]
    if p is None:
        require(row_raw is None, "unexpected_row_bytes")
    else:
        validate_row(row_raw, m, t)
    return {
        "schema": "copied_local_claim_audit/1",
        "status": "LOCAL_CLAIM_COPY_BODY_ID_MATCH_ONLY" if p else "ROW_LOCATOR_REQUIRED",
        "manifest_sha256": manifest_sha256,
        "trace": {"sha256": sha(trace_raw), "bytes": len(trace_raw)},
        "body_binding": dict(m["body_binding"]),
        "metadata": {**t["metadata"], "witness_observed_utc": clock(t["witness"]["observed_utc"])},
        "claim_copy": None if p is None else {**m["claim_copy"], "row_hash_status": "VERIFIED_COPY_BYTES"},
        "native_pointer": None if p is None else {
            **p, "status": "DECLARED_NOT_READ", "row_hash_status": "DECLARED_NOT_READ",
            "prefix_hash_status": "DECLARED_UPSTREAM_REFERENCE" if p["declared_prefix_sha256"] else "NOT_SUPPLIED",
            "bytes_read": 0,
        },
        "body_to_claim_edge": "COPY_BODY_ID_MATCH_ONLY" if p else "UNKNOWN",
        "column_binding": "UNKNOWN", "semantic_grounding": "UNKNOWN",
        "actual_consumed_ids": None,
        "downstream": dict.fromkeys(("typed", "event", "forecast", "position", "delivery"), "UNKNOWN"),
        "qualification": "COORDINATOR_SUPPLIED_COPY_CONSISTENCY_NOT_NATIVE_AUTHENTICITY_OR_CONSUMPTION",
    }


def read_once(path, cap):
    try:
        with path.open("rb") as handle:
            before = os.fstat(handle.fileno())
            require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= cap, "input_size")
            require(before.st_nlink == 1, "hardlinked_input_refused")
            raw = handle.read(cap + 1)
            after = os.fstat(handle.fileno())
        def identity(s):
            return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns
        require(identity(before) == identity(after) and len(raw) == before.st_size, "changed_input")
        return raw, identity(after)
    except OSError:
        raise ClaimCopyRefused("input_unavailable") from None


def lexical_private(value):
    """Pure fixed-E allowlist; reject external/UNC descriptors before resolution."""
    locator(value)
    base = ntpath.normcase(ntpath.normpath(str(PRIVATE_ROOT)))
    try:
        inside = ntpath.commonpath((base, ntpath.normcase(ntpath.normpath(value)))) == base
    except ValueError:
        inside = False
    require(inside, "outside_private_root")
    return value


def private_input(value, root):
    p = Path(lexical_private(value)).resolve(strict=True)
    require(p.is_relative_to(root) and p.is_file(), "outside_private_root")
    return p


def audit_to_private(manifest_path, manifest_sha256, output_dir):
    """Exactly two or three bounded copied inputs, reread, then exclusive E output."""
    # Pure preflight, before resolve/open/mkdir; no injectable root authority.
    digest(manifest_sha256)
    locator(manifest_path)
    locator(output_dir)
    require(os.name == "nt" and PRIVATE_ROOT.is_absolute(), "unsupported_private_root_platform")
    for name in (manifest_path, output_dir):
        lexical_private(name)
    try:
        root = PRIVATE_ROOT.resolve(strict=True)
        require(root.is_dir(), "private_root_required")
        output = Path(output_dir).resolve(strict=False)
        require(output != root and output.is_relative_to(root), "outside_private_root")
        mp = private_input(manifest_path, root)
        first = [read_once(mp, OBJECT_CAP)]
        m = parse_manifest(first[0][0], manifest_sha256)
        paths = [mp, private_input(m["trace"]["copy_path"], root)]
        caps = [OBJECT_CAP, OBJECT_CAP]
        if m["claim_copy"] is not None:
            paths.append(private_input(m["claim_copy"]["copy_path"], root))
            caps.append(ROW_CAP)
        require(len(set(paths)) == len(paths), "input_path_alias")
        first.extend(read_once(p, cap) for p, cap in zip(paths[1:], caps[1:]))
        identities = [row[1][:2] for row in first]
        require(len(set(identities)) == len(identities), "input_file_alias")
        report = verify_local_claim_copy(first[1][0], first[0][0], first[2][0] if len(first) == 3 else None,
                                         manifest_sha256=manifest_sha256)
        for p, cap, previous in zip(paths, caps, first):
            require(read_once(p, cap) == previous, "changed_input")
        report["io"] = {"distinct_inputs": len(paths), "input_bytes": sum(len(v[0]) for v in first),
                        "integrity_reread_bytes": sum(len(v[0]) for v in first),
                        "body_native_prefix_downstream_bytes_read": 0}
        raw = (json.dumps(report, ensure_ascii=True, allow_nan=False, indent=2) + "\n").encode("utf-8")
        output.mkdir()  # CreateNew directory; existing runs are immutable.
        with (output / "CLAIM_COPY_AUDIT.json").open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        return {"status": report["status"], "report_sha256": sha(raw)}
    except ClaimCopyRefused:
        raise
    except (OSError, ValueError, RecursionError, OverflowError):
        raise ClaimCopyRefused("private_io_refused") from None


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ClaimCopyRefused("invalid_arguments")


def main(argv=None):
    try:
        p = Parser(description=__doc__)
        p.add_argument("--manifest", required=True)
        p.add_argument("--manifest-sha256", required=True)
        p.add_argument("--output-dir", required=True)
        args = p.parse_args(argv)
        print(json.dumps(audit_to_private(args.manifest, args.manifest_sha256, args.output_dir), sort_keys=True))
        return 0
    except ClaimCopyRefused as exc:
        print(json.dumps({"status": "REFUSED", "code": str(exc)}))
        return 2
    except Exception:
        print(json.dumps({"status": "REFUSED", "code": "internal_error"}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
