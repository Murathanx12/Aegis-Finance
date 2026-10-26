"""Bounded offline C05 identity diagnostic; no native writes or data discovery.

Only ticker and the declared raw observation DATE are decoded. The narrow
typed projection follows raw_ibes_worker.py's str/date/null roundtrip semantics;
the acquisition worker is pinned as provenance, never imported or executed.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import time
from typing import Any, BinaryIO


PRIVATE_ROOT = Path.home() / "aegis-recovery-evidence"
ROLES = {"job", "root_plan", "run", "readback", "raw_pins", "codec",
         "actual_schema", "typed_schema"}
LINK_COLUMNS = ["ticker", "permno", "ncusip", "sdate", "edate", "score"]
PROJECTED_LINK_COLUMNS = ["ticker", "permno", "sdate", "edate", "score"]
CATEGORIES = ("no_link", "one_unique_permno", "multiple_permnos",
              "overlap_one_permno", "unqualified_link", "missing_key_or_date",
              "malformed_key_or_date")
CLAIM = "DATED_IDENTITY_DIAGNOSTIC_ONLY_NO_PIT_READINESS_OR_C05_COMPLETION"


class Refusal(Exception):
    """Only programmer-owned constant gates may cross the output boundary."""


def require(ok: bool, gate: str) -> None:
    if not ok:
        raise Refusal(gate)


@dataclass(frozen=True)
class Limits:
    input_bytes: int = 24 * 1024**2
    input_rows: int = 40000
    line_bytes: int = 64 * 1024
    metadata_bytes: int = 1024**2
    link_bytes: int = 1024**2
    link_rows: int = 25000
    parquet_footer_bytes: int = 128 * 1024
    parquet_uncompressed_bytes: int = 16 * 1024**2
    arrow_batch_bytes: int = 2 * 1024**2
    batch_rows: int = 512
    links_per_key: int = 512
    key_bytes: int = 128
    score_buckets: int = 64
    wall_seconds: int = 90


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def is_hash(value: Any) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def count(value: Any, cap: int) -> bool:
    return type(value) is int and 0 <= value <= cap


def identity(path: Path) -> tuple[int, int, int, int, int]:
    s = path.stat()
    require(path.is_file(), "SOURCE_NOT_FILE")
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns


def same_file(path: Path, before: tuple) -> None:
    require(identity(path) == before, "SOURCE_MUTATED")


def bounded_hash(path: Path, cap: int) -> tuple[str, tuple]:
    before = identity(path)
    require(before[2] <= cap, "SOURCE_BYTE_LIMIT")
    h, seen = hashlib.sha256(), 0
    with path.open("rb") as stream:
        while chunk := stream.read(min(1024**2, cap - seen + 1)):
            seen += len(chunk)
            require(seen <= cap, "SOURCE_BYTE_LIMIT")
            h.update(chunk)
    same_file(path, before)
    require(seen == before[2], "SOURCE_MUTATED")
    return h.hexdigest(), before


def no_duplicates(pairs: list) -> dict:
    result = {}
    for k, v in pairs:
        require(k not in result, "DUPLICATE_JSON_KEY")
        result[k] = v
    return result


def parse_json(raw: bytes | str) -> Any:
    try:
        return json.loads(raw, object_pairs_hook=no_duplicates,
                          parse_constant=lambda _: (_ for _ in ()).throw(Refusal("INVALID_JSON")))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise Refusal("INVALID_JSON") from None


def pinned_json(ref: dict, cap: int) -> tuple[dict, tuple]:
    require(type(ref) is dict and set(ref) == {"path", "sha256"}
            and type(ref["path"]) is str and is_hash(ref["sha256"]), "SOURCE_REFERENCE_INVALID")
    path = Path(ref["path"]).resolve(strict=True)
    observed, before = bounded_hash(path, cap)
    require(observed == ref["sha256"], "SOURCE_HASH_DRIFT")
    with path.open("rb") as stream:
        raw = stream.read(cap + 1)
    require(len(raw) <= cap and sha(raw) == observed, "SOURCE_MUTATED")
    same_file(path, before)
    obj = parse_json(raw)
    require(type(obj) is dict, "METADATA_OBJECT_REQUIRED")
    return obj, before


def calendar_date(value: Any) -> date | None:
    if type(value) is date:
        return value
    if type(value) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
        return None
    try:
        result = date.fromisoformat(value)
        return result if result.isoformat() == value else None
    except ValueError:
        return None


def key_ok(value: Any, limits: Limits) -> bool:
    # No trimming, case folding, symbol substitution or lossy key coercion.
    if type(value) is not str or not value or value != value.strip():
        return False
    try:
        key_bytes = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        return False
    return (key_bytes <= limits.key_bytes
            and all(ord(c) >= 32 and ord(c) != 127 for c in value))


def link_timestamp_ns_date(value: Any) -> date | None:
    """Only exact midnight int64 storage from a naive link timestamp[ns]."""
    day_ns = 86_400_000_000_000
    if (type(value) is not int or not -(2**63) <= value < 2**63
            or value % day_ns != 0):
        return None
    # The int64 nanosecond range lies inside Python's date range. Integer
    # division is exact here, including before the epoch; no datetime rounding.
    return date(1970, 1, 1) + timedelta(days=value // day_ns)


def query_hash(job: dict) -> str:
    query = ("SELECT * FROM " + job["table"] + " WHERE " + job["date_column"]
             + " >= %s AND " + job["date_column"] + " < %s")
    return sha(query.encode())


def validate_binding(binding: dict, limits: Limits) -> dict:
    """Validate metadata only. Does not open the typed partition or link file."""
    require(type(binding) is dict and binding.get("schema") == "C05_identity_binding/1",
            "BINDING_SCHEMA")
    refs = binding.get("sources")
    require(type(refs) is dict and set(refs) == ROLES, "EVIDENCE_MISSING")
    docs, stamps = {}, {}
    for role, ref in refs.items():
        if role in {"codec", "typed_schema"}:
            require(type(ref) is dict and set(ref) == {"path", "sha256"}
                    and type(ref["path"]) is str and is_hash(ref["sha256"]), "SOURCE_REFERENCE_INVALID")
            observed, before = bounded_hash(Path(ref["path"]), limits.metadata_bytes)
            require(observed == ref["sha256"], "SOURCE_HASH_DRIFT")
            stamps[role] = before
        else:
            docs[role], stamps[role] = pinned_json(ref, limits.metadata_bytes)
    job, root, run, back, pins, actual = (docs[k] for k in
                                        ("job", "root_plan", "run", "readback", "raw_pins", "actual_schema"))
    jobpath = Path(refs["job"]["path"]).resolve(strict=True)
    packet = jobpath.parent.parent
    require(jobpath == packet / "plans" / "job01.json", "EXACT_JOB01_REQUIRED")
    for role, filename in {"root_plan": "PLAN.json", "run": "RUN_RECEIPT.json",
                           "readback": "READBACK_JOB01.json", "raw_pins": "ACTUAL_RESULT_PINS.json",
                           "codec": "raw_ibes_worker.py"}.items():
        require(Path(refs[role]["path"]).resolve(strict=True) == packet / filename,
                "EVIDENCE_PATH_BINDING")
    require(job.get("schema") == "C05_exact_raw_IBES_month/1"
            and job.get("table") == "ibes.statsum_epsus" and job.get("date_column") == "statpers"
            and job.get("from_inclusive") == "2025-01-01" and job.get("until_exclusive") == "2025-02-01"
            and job.get("all_source_identifiers") is True and job.get("preserve_all_rows_and_fields") is True,
            "EXACT_JANUARY_US_SUMMARY_SCOPE")
    require(root.get("schema") == "C05_exact_four_raw_IBES_plan/1"
            and run.get("schema") == "C05_raw_IBES_jan2025_receipt/1"
            and run.get("status") == "COMPLETED_RAW_FOUR_TABLE_PARTITIONS"
            and run.get("plan_sha256") == refs["root_plan"]["sha256"]
            and run.get("worker_sha256") == refs["codec"]["sha256"]
            and run.get("connection_closed") is True and run.get("cleanup_gates") == [], "RAW_RUN_BINDING")
    require(pins.get("status") == "FROZEN_ACTUAL_FOUR_COMPLETE_NO_FURTHER_QUERIES"
            and pins.get("frozen_sourcepins_still_equal") is True, "RAW_FREEZE_UNQUALIFIED")
    for role in ("run", "readback"):
        require(pins["files"].get(Path(refs[role]["path"]).name) == refs[role]["sha256"],
                "INDEPENDENT_RECEIPT_PIN_DRIFT")
    require(len(root["jobs"]) == 4 and root["jobs"][0]["sha256"] == refs["job"]["sha256"]
            and Path(root["jobs"][0]["path"]).resolve(strict=True) == jobpath, "ROOT_JOB_BINDING")
    for role, prefix in (("typed_schema", "typed_schema_witness"), ("actual_schema", "actual_schema")):
        source = job if role == "typed_schema" else root
        require(Path(source[prefix + "_path"]).resolve(strict=True)
                == Path(refs[role]["path"]).resolve(strict=True)
                and source[prefix + "_sha256"] == refs[role]["sha256"], "SCHEMA_WITNESS_BINDING")
    columns, oids = job["expected_columns"], job["expected_source_type_oids"]
    require(type(columns) is list and 2 <= len(columns) <= 64
            and all(type(c) is str for c in columns) and len(set(columns)) == len(columns)
            and type(oids) is dict and set(oids) == set(columns)
            and all(type(v) is int for v in oids.values())
            and oids.get("ticker") == 1043 and oids.get("statpers") == 1082, "DECLARED_DATE_OR_KEY_SCHEMA")
    require([r["column_name"] for r in actual["tables"][job["table"]]] == columns
            and next(r for r in actual["tables"][job["table"]] if r["column_name"] == "statpers")["udt_name"] == "date",
            "ACTUAL_SCHEMA_DRIFT")
    require(len(run["jobs"]) == 4, "RAW_JOB_COUNT")
    record = run["jobs"][0]
    require(record.get("table") == job["table"] and record.get("status") == "COMPLETE"
            and record.get("job_plan_sha256") == refs["job"]["sha256"]
            and record.get("query_template_sha256") == query_hash(job), "RAW_ARTIFACT_BINDING")
    artifact = record["artifact"]
    partition = binding["partition"]
    require(type(partition) is dict and set(partition) == {"path", "sha256", "bytes", "rows"}, "PARTITION_BINDING")
    path = Path(partition["path"]).resolve(strict=True)  # stat/resolve only, no open
    require(path == packet / "artifacts" / "partition01.typed.jsonl"
            and Path(artifact["path"]).resolve(strict=True) == path
            and Path(job["output_root"]).resolve(strict=True) == path.parent, "EXACT_PARTITION01_REQUIRED")
    require(is_hash(partition["sha256"]) and count(partition["bytes"], limits.input_bytes)
            and count(partition["rows"], limits.input_rows) and partition["rows"] > 0, "PARTITION_LIMIT")
    require(back.get("status") == "COMPLETE" and back.get("table") == job["table"]
            and back.get("predicate_column") == job["date_column"]
            and back.get("column_count") == len(columns), "INDEPENDENT_READBACK_SCOPE")
    for flag in ("actual_column_order_OIDs_and_date_predicate_match", "all_cell_type_roundtrips_equal",
                 "all_source_rows_fields_and_clock_values_retained"):
        require(back.get(flag) is True, "INDEPENDENT_READBACK_UNQUALIFIED")
    for name in ("bytes", "rows"):
        require(type(artifact.get(name)) is int and type(back.get(name)) is int,
                "INDEPENDENT_ARTIFACT_COUNT_TYPE")
    for name in ("sha256", "bytes", "rows"):
        require(artifact.get(name) == back.get(name) == partition[name], "INDEPENDENT_ARTIFACT_DRIFT")
    for flag in ("source_date_predicate_validated", "typed_roundtrip_equal", "all_columns_and_original_order_retained"):
        require(artifact.get(flag) is True, "RAW_ARTIFACT_UNQUALIFIED")
    link = binding["link"]
    require(type(link) is dict and set(link) == {"path", "sha256", "bytes", "rows", "columns"}
            and is_hash(link["sha256"]) and count(link["bytes"], limits.link_bytes)
            and count(link["rows"], limits.link_rows) and link["rows"] > 0
            and link["columns"] == LINK_COLUMNS, "LINK_REFERENCE_OR_LIMIT")
    return {"job": job, "stamps": stamps, "partition_path": path}


_SPACE = " \t\r\n"
_STRING = re.compile(r'"(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"')
_ATOM = re.compile(r"(?:null|true|false|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)")


def skip_space(text: str, pos: int) -> int:
    while pos < len(text) and text[pos] in _SPACE:
        pos += 1
    return pos


def skip_value(text: str, pos: int, depth: int = 0) -> int:
    """Validate JSON syntax without materializing excluded source cell values."""
    require(depth <= 12 and pos < len(text), "ROW_JSON_DEPTH_OR_SYNTAX")
    ch = text[pos]
    if ch in '[{':
        end, pos = (']' if ch == '[' else '}'), skip_space(text, pos + 1)
        if pos < len(text) and text[pos] == end:
            return pos + 1
        while True:
            if ch == '{':
                match = _STRING.match(text, pos)
                require(match is not None, "ROW_JSON_SYNTAX")
                pos = skip_space(text, match.end())
                require(pos < len(text) and text[pos] == ':', "ROW_JSON_SYNTAX")
                pos = skip_space(text, pos + 1)
            pos = skip_space(text, skip_value(text, pos, depth + 1))
            require(pos < len(text), "ROW_JSON_SYNTAX")
            if text[pos] == end:
                return pos + 1
            require(text[pos] == ',', "ROW_JSON_SYNTAX")
            pos = skip_space(text, pos + 1)
    match = (_STRING if ch == '"' else _ATOM).match(text, pos)
    require(match is not None, "ROW_JSON_SYNTAX")
    return match.end()


def project_row(raw: bytes, width: int, indexes: set[int]) -> dict[int, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        raise Refusal("ROW_UTF8") from None
    pos = skip_space(text, 0)
    require(pos < len(text) and text[pos] == '[', "ROW_ARRAY_REQUIRED")
    pos, seen, result = skip_space(text, pos + 1), 0, {}
    while pos < len(text) and text[pos] != ']':
        start = pos
        pos = skip_space(text, skip_value(text, pos))
        if seen in indexes:
            result[seen] = parse_json(text[start:pos])
        seen += 1
        require(seen <= width and pos < len(text), "ROW_WIDTH")
        if text[pos] == ']':
            break
        require(text[pos] == ',', "ROW_JSON_SYNTAX")
        pos = skip_space(text, pos + 1)
        require(pos < len(text) and text[pos] != ']', "ROW_JSON_SYNTAX")
    require(pos < len(text) and text[pos] == ']' and seen == width
            and skip_space(text, pos + 1) == len(text), "ROW_WIDTH_OR_TRAILING_JSON")
    return result


def typed_projection(cell: Any, kind: str, limits: Limits) -> tuple[str, Any]:
    if cell == ["null"]:
        return "missing", None
    if type(cell) is not list or len(cell) != 2 or cell[0] != kind:
        return "malformed", None
    value = cell[1]
    if kind == "str" and key_ok(value, limits):
        return "valid", value
    if kind == "date" and type(value) is str:
        parsed = calendar_date(value)
        if parsed is not None:
            return "valid", parsed
    return "malformed", None


def numeric(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def score_bucket(value: Any) -> str:
    if value is None:
        return "null"
    if not numeric(value):
        return "invalid"
    return str(int(value)) if value == int(value) else format(value, ".17g")


@dataclass(frozen=True)
class Link:
    start: date | None
    end: date | None
    permno: int | None
    score: str


def load_links(path: Path, spec: dict, limits: Limits, check: Any) -> tuple[dict, dict]:
    """Preflight all column chunks before decompression; use bounded Arrow batches."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        raise Refusal("PYARROW_REQUIRED") from None
    with path.open("rb") as stream:
        require(stream.read(4) == b"PAR1" and spec["bytes"] >= 12, "PARQUET_MAGIC")
        stream.seek(-8, 2)
        footer = stream.read(8)
        require(len(footer) == 8 and footer[4:] == b"PAR1", "PARQUET_MAGIC")
        footer_bytes = struct.unpack("<I", footer[:4])[0]
        require(footer_bytes <= limits.parquet_footer_bytes and footer_bytes <= spec["bytes"] - 12,
                "PARQUET_FOOTER_LIMIT")
        stream.seek(0)
        with pq.ParquetFile(stream, memory_map=False, pre_buffer=False,
                            thrift_string_size_limit=limits.parquet_footer_bytes,
                            thrift_container_size_limit=10000) as pf:
            md, schema = pf.metadata, pf.schema_arrow
            require(schema.names == spec["columns"] and md.num_rows == spec["rows"]
                    and md.num_rows <= limits.link_rows and md.num_row_groups <= limits.link_rows,
                    "PARQUET_SCHEMA_OR_ROWS")
            for field in schema:
                require(pa.types.is_string(field.type) or pa.types.is_large_string(field.type)
                        or pa.types.is_integer(field.type) or pa.types.is_floating(field.type)
                        or pa.types.is_date(field.type)
                        or (field.name in ("sdate", "edate") and pa.types.is_timestamp(field.type)
                            and field.type.unit == "ns" and field.type.tz is None),
                        "PARQUET_PRIMITIVE_SCHEMA")
            timestamp_dates = [name for name in ("sdate", "edate")
                               if pa.types.is_timestamp(schema.field(name).type)]
            uncompressed = 0
            for i in range(md.num_row_groups):
                group = md.row_group(i)
                require(group.num_columns == len(LINK_COLUMNS), "PARQUET_SCHEMA_OR_ROWS")
                for j in range(group.num_columns):
                    size = group.column(j).total_uncompressed_size
                    require(size >= 0, "PARQUET_UNCOMPRESSED_LIMIT")
                    uncompressed += size
                    require(uncompressed <= limits.parquet_uncompressed_bytes, "PARQUET_UNCOMPRESSED_LIMIT")
            index, buckets = defaultdict(list), Counter()
            seen = unknown_keys = bad = 0
            for batch in pf.iter_batches(batch_size=limits.batch_rows, columns=PROJECTED_LINK_COLUMNS,
                                         use_threads=False):
                check()
                require(batch.num_rows <= limits.batch_rows and batch.nbytes <= limits.arrow_batch_bytes,
                        "ARROW_BATCH_LIMIT")
                # Inspect ns storage before to_pylist: datetime conversion can
                # round/truncate sub-microsecond values (or produce NaT).
                for name in timestamp_dates:
                    i = batch.schema.get_field_index(name)
                    batch = batch.set_column(i, batch.schema.field(i).with_type(pa.int64()),
                                             batch.column(i).cast(pa.int64()))
                for row in batch.to_pylist():
                    seen += 1
                    require(seen <= limits.link_rows, "LINK_ROW_LIMIT")
                    bucket = score_bucket(row["score"])
                    buckets[bucket] += 1
                    require(len(buckets) <= limits.score_buckets, "SCORE_BUCKET_LIMIT")
                    if not key_ok(row["ticker"], limits):
                        unknown_keys += 1
                        bad += 1
                        continue
                    start, end = (link_timestamp_ns_date(row[name]) if name in timestamp_dates
                                  else calendar_date(row[name]) for name in ("sdate", "edate"))
                    permno = row["permno"]
                    valid_id = numeric(permno) and permno == int(permno) and 0 < permno < 2**53
                    if start is None or end is None or start > end:
                        start = end = None  # uncertain interval blocks this key, never open-ended
                    qualified = start is not None and valid_id and bucket not in ("null", "invalid")
                    bad += not qualified
                    index[row["ticker"]].append(Link(start, end, int(permno) if valid_id else None, bucket))
                    require(len(index[row["ticker"]]) <= limits.links_per_key, "LINKS_PER_KEY_LIMIT")
            require(seen == spec["rows"], "LINK_INCOMPLETE_STREAM")
    return index, {"rows": seen, "unqualified_rows": bad, "unassignable_key_rows": unknown_keys,
                   "source_score_buckets": dict(sorted(buckets.items())),
                   "advertised_uncompressed_bytes": uncompressed}


def classify(links: list[Link], observation: date, unknown_keys: bool) -> tuple[str, int, int, list[str]]:
    active = [r for r in links if r.start is not None and r.start <= observation <= r.end]
    ids = {r.permno for r in active if r.permno is not None}
    scores = [r.score for r in active]
    if unknown_keys or any(r.start is None for r in links) or any(
            r.permno is None or r.score in ("null", "invalid") for r in active):
        return "unqualified_link", len(active), len(ids), scores
    if not active:
        return "no_link", 0, 0, scores
    if len(ids) > 1:
        return "multiple_permnos", len(active), len(ids), scores
    if len(active) > 1:
        return "overlap_one_permno", len(active), 1, scores
    return "one_unique_permno", 1, 1, scores


def run_diagnostic(binding: dict, limits: Limits = Limits()) -> dict:
    """Return aggregates only, after complete EOF and all post-read hash checks."""
    started = time.monotonic()

    def check() -> None:
        require(time.monotonic() - started <= limits.wall_seconds, "WALL_LIMIT")

    for v in asdict(limits).values():
        require(type(v) is int and v > 0, "INVALID_LIMIT")
    validated = validate_binding(binding, limits)
    check()
    job, path = validated["job"], validated["partition_path"]
    linkpath = Path(binding["link"]["path"]).resolve(strict=True)
    linkhash, linkstamp = bounded_hash(linkpath, limits.link_bytes)
    require(linkhash == binding["link"]["sha256"] and linkstamp[2] == binding["link"]["bytes"],
            "LINK_HASH_OR_BYTES_DRIFT")
    index, linkstats = load_links(linkpath, binding["link"], limits, check)
    check()
    before = identity(path)
    require(before[2] == binding["partition"]["bytes"], "INPUT_BYTES_DRIFT")
    h, byte_count, rows = hashlib.sha256(), 0, 0
    categories = Counter({k: 0 for k in CATEGORIES})
    cells = {k: Counter({s: 0 for s in ("valid", "missing", "malformed")}) for k in ("ticker", "statpers")}
    matched_scores, active_rows, multirow_same_id, multi_ids = Counter(), 0, 0, 0

    def line(stream: BinaryIO) -> bytes:
        nonlocal byte_count
        check()
        raw = stream.readline(min(limits.line_bytes, limits.input_bytes - byte_count) + 1)
        require(len(raw) <= limits.line_bytes and byte_count + len(raw) <= limits.input_bytes, "INPUT_BYTE_OR_LINE_LIMIT")
        require(not raw or raw.endswith(b"\n"), "INCOMPLETE_LINE")
        byte_count += len(raw)
        h.update(raw)
        return raw

    columns = job["expected_columns"]
    ti, di = columns.index("ticker"), columns.index("statpers")
    lower, upper = calendar_date(job["from_inclusive"]), calendar_date(job["until_exclusive"])
    with path.open("rb") as stream:
        header = parse_json(line(stream))
        expected = {"schema": "C05_exact_typed_rows_jsonl/1", "columns": columns,
                    "source_type_oids": job["expected_source_type_oids"],
                    "job_plan_sha256": binding["sources"]["job"]["sha256"],
                    "query_template_sha256": query_hash(job), "rows_expected": binding["partition"]["rows"],
                    "all_source_fields_rows_and_duplicate_versions_preserved": True}
        require(type(header) is dict and canonical(header) == canonical(expected)
                and type(header.get("rows_expected")) is int, "TYPED_HEADER_DRIFT")
        while raw := line(stream):
            rows += 1
            require(rows <= limits.input_rows and rows <= binding["partition"]["rows"], "INPUT_ROW_LIMIT")
            projected = project_row(raw, len(columns), {ti, di})
            ts, ticker = typed_projection(projected[ti], "str", limits)
            ds, observation = typed_projection(projected[di], "date", limits)
            cells["ticker"][ts] += 1
            cells["statpers"][ds] += 1
            if ds == "valid":
                require(lower <= observation < upper, "OBSERVATION_DATE_OUTSIDE_DECLARED_RANGE")
            if "malformed" in (ts, ds):
                category = "malformed_key_or_date"
            elif "missing" in (ts, ds):
                category = "missing_key_or_date"
            else:
                category, n, distinct, scores = classify(index.get(ticker, []), observation,
                                                        bool(linkstats["unassignable_key_rows"]))
                active_rows += n
                multirow_same_id += n > 1 and distinct == 1
                multi_ids += distinct > 1
                matched_scores.update(scores)
            categories[category] += 1
    require(rows == binding["partition"]["rows"] and byte_count == binding["partition"]["bytes"]
            and h.hexdigest() == binding["partition"]["sha256"], "INPUT_HASH_OR_COUNT_DRIFT")
    same_file(path, before)
    # A second full byte hash catches changed already-read bytes and replacement.
    final_hash, final_stamp = bounded_hash(path, limits.input_bytes)
    require(final_hash == h.hexdigest() and final_stamp == before, "INPUT_POSTREAD_DRIFT")
    linkafter, afterstamp = bounded_hash(linkpath, limits.link_bytes)
    require(linkafter == linkhash and afterstamp == linkstamp, "LINK_POSTREAD_DRIFT")
    for role, ref in binding["sources"].items():
        observed, stamp = bounded_hash(Path(ref["path"]), limits.metadata_bytes)
        require(observed == ref["sha256"] and stamp == validated["stamps"][role], "EVIDENCE_POSTREAD_DRIFT")
    check()
    require(sum(categories.values()) == rows, "DENOMINATOR_MISMATCH")
    return {"schema": "C05_identity_diagnostic/1", "status": "COMPLETE_BOUNDED_DIAGNOSTIC",
            "at": datetime.now(timezone.utc).isoformat(), "claims": CLAIM,
            "rows": rows, "bytes": byte_count, "categories": dict(categories),
            "projected_cell_states": {k: dict(v) for k, v in cells.items()},
            "all_input_rows_including_duplicates_retained_in_denominator": True,
            "decoded_columns": ["ticker", "statpers"], "source_observation_type": "DATE",
            "observation_date_is_not_public_availability_or_timezone": True,
            "active_link_row_matches": active_rows,
            "observations_multiple_link_rows_one_permno": multirow_same_id,
            "observations_multiple_permnos": multi_ids,
            "active_link_score_buckets_row_weighted": dict(sorted(matched_scores.items())),
            "link_source": linkstats, "link_sha256_before": linkhash, "link_sha256_after": linkafter,
            "partition_sha256": h.hexdigest(), "evidence_sha256": {k: r["sha256"] for k, r in binding["sources"].items()},
            "limits": asdict(limits), "no_raw_identity_values_exported": True}


def private_output(path: Path) -> Path:
    resolved = path.resolve()
    require(resolved.is_relative_to(PRIVATE_ROOT.resolve()) and resolved != PRIVATE_ROOT.resolve(),
            "PRIVATE_OUTPUT_REQUIRED")
    # Do not follow a junction/symlink into an existing output directory.
    require(not path.exists() and not path.is_symlink(), "OUTPUT_ALREADY_EXISTS")
    resolved.mkdir(exist_ok=False)  # parent must already exist; no native paths created
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", required=True, type=Path)
    parser.add_argument("--binding-sha256", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--consume-one-partition", required=True, action="store_true")
    args = parser.parse_args(argv)
    output = None
    try:
        output = private_output(args.output_dir)
        binding, _ = pinned_json({"path": str(args.binding), "sha256": args.binding_sha256}, Limits().metadata_bytes)
        result = run_diagnostic(binding)
        # Revalidate the operation binding itself before persisting any counts.
        pinned_json({"path": str(args.binding), "sha256": args.binding_sha256}, Limits().metadata_bytes)
        result["binding_sha256"] = args.binding_sha256
        name, status = "RESULT.json", 0
    except Exception as error:
        result = {"schema": "C05_identity_refusal/1", "status": "REFUSED", "claims": CLAIM,
                  "gate": str(error) if type(error) is Refusal else "SOURCE_OR_RUNTIME_FAILURE"}
        name, status = "REFUSED.json", 2
    if output is not None:
        with (output / name).open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
    print(json.dumps({"status": result["status"], "gate": result.get("gate")}))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
