"""Protected-first, metadata-only lexer before original decision projection.

The lexer decodes JSON keys and selected metadata strings/flags only. Other
strings and analytical primitive tokens remain opaque until full recursive
metadata admission. It intentionally need not parse malformed analytical
numbers in a protected row. No population-by-path fallback is permitted.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time

VERSION = "beta_v1_decision_projection/2"
META = re.compile(r"population|evidence|writer|specialist|investigator|mechanism|source|\bby\b|arm|lane|role|policy|strategy|trial|experiment|sandbox|replay|iif|sealed|holdout|gold|protect|quarantin|resolution_state|config|metadata", re.I)
PROTECTED = re.compile(r"sandbox|replay|iif|trial|experiment|gold|sealed|holdout|investigator[:_ -]?[abcd](?:_|:|\b)|quarantin|protected", re.I)
IDENTITY = {"decision_id", "state", "utc", "asof", "ledger_version", "formation_utc", "decided_utc"}
FLAGS = re.compile(r"quarantin|protect|sealed|holdout|gold|trial|experiment|sandbox|replay|iif|investigator", re.I)
FAMILY = re.compile(r"^(?:by|writer|specialist|source|arm|lane|role|strategy)(?:_(?:id|name|family|arm|tag))?$", re.I)
ROW_METADATA_KEYS = ("by", "evidence_population", "ledger_version", "formation_utc", "decided_utc")
DETAIL_KEYS = ("er_horizon", "horizon_sessions", "benchmark", "benchmark_symbol", "grading_rule", "er_by_component",
    "excess_return", "expiry_utc", "formation_utc", "label_start_at", "label_end_at", "entry_utc", "exit_utc",
    "target_calendar", "window_contract", "task", "score_units", "costs_charged", "cost_rate_bps",
    "model_version", "prompt_version", "policy_version", "source_versions", "score_persisted_utc", "score_available_utc")
NUMERICAL_DETAIL_KEYS = frozenset(("er_horizon", "horizon_sessions", "er_by_component", "excess_return", "cost_rate_bps"))


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _reference(table, value):
    digest = hashlib.sha256(canonical_bytes(value)).hexdigest()
    if digest in table and table[digest] != value:
        raise ProjectionRefusal("content-addressed projection table collision")
    table[digest] = value
    return digest


def expand_projected_row(result, compact_row):
    """Recover the exact v1 selected row; validate every content-addressed reference.

    Other original metadata is deliberately not copied. Its immutable lookup is
    the result's source SHA256 plus this row's exact raw-byte SHA256, and its
    recursive admission tags are independently pinned by admission_metadata_sha256.
    """
    if result.get("schema") != VERSION:
        raise ProjectionRefusal("unsupported compact projection schema")
    def resolve(kind, key):
        digest = compact_row[key]
        value = result["reference_tables"][kind][digest]
        if hashlib.sha256(canonical_bytes(value)).hexdigest() != digest:
            raise ProjectionRefusal("projection reference integrity mismatch")
        return value
    metadata = resolve("row_metadata", "metadata_ref")
    detail_metadata = resolve("detail_metadata", "detail_metadata_ref")
    qualified = resolve("qualification", "qualification_ref")
    expanded = {**{k: compact_row[k] for k in ("decision_id", "state", "utc", "asof", "full_row_sha256")},
        **{k: metadata.get(k) for k in ROW_METADATA_KEYS},
        "detail": {k: (compact_row["detail"].get(k) if k in NUMERICAL_DETAIL_KEYS else detail_metadata.get(k))
                   for k in DETAIL_KEYS},
        "h21_qualification": json.loads(canonical_bytes(qualified)),
        "metadata_admission": result["metadata_admission_contract"]}
    return json.loads(canonical_bytes(expanded))


def _compact_row(row, tags, tables):
    return {**{k: row[k] for k in ("decision_id", "state", "utc", "asof", "full_row_sha256")},
        "metadata_ref": _reference(tables["row_metadata"], {k: row[k] for k in ROW_METADATA_KEYS if row[k] is not None}),
        "detail_metadata_ref": _reference(tables["detail_metadata"],
            {k: v for k, v in row["detail"].items() if k not in NUMERICAL_DETAIL_KEYS and v is not None}),
        "qualification_ref": _reference(tables["qualification"], row["h21_qualification"]),
        "detail": {k: v for k, v in row["detail"].items() if k in NUMERICAL_DETAIL_KEYS and v is not None},
        "admission_metadata_sha256": hashlib.sha256(canonical_bytes(tags)).hexdigest()}


class ProjectionRefusal(ValueError):
    pass


class MetadataLexer:
    def __init__(self, line: bytes):
        self.text = line.decode("utf-8")
        self.i, self.tags = 0, []

    def _space(self):
        while self.i < len(self.text) and self.text[self.i].isspace():
            self.i += 1

    def _string(self, decode: bool):
        if self.i >= len(self.text) or self.text[self.i] != '"':
            raise ProjectionRefusal("object key/string delimiter missing")
        start = self.i
        self.i += 1
        while self.i < len(self.text):
            char = self.text[self.i]
            if char == "\\":
                self.i += 2
            elif char == '"':
                self.i += 1
                if decode:
                    return json.loads(self.text[start:self.i])
                return None
            else:
                self.i += 1
        raise ProjectionRefusal("unterminated JSON string")

    def _value(self, path: str, active: bool, direct: bool, depth: int):
        if depth > 64:
            raise ProjectionRefusal("metadata nesting limit exceeded")
        self._space()
        if self.i >= len(self.text):
            raise ProjectionRefusal("incomplete JSON value")
        char = self.text[self.i]
        if char in "{[" and active:
            self.tags.append((path, "object" if char == "{" else "array", None))
        if char == "{":
            self.i += 1
            keys = set()
            self._space()
            if self.i < len(self.text) and self.text[self.i] == "}":
                self.i += 1
                return
            while True:
                self._space()
                key = self._string(True)
                if key in keys:
                    raise ProjectionRefusal("duplicate JSON object key")
                keys.add(key)
                self._space()
                if self.i >= len(self.text) or self.text[self.i] != ":":
                    raise ProjectionRefusal("missing JSON colon")
                self.i += 1
                child = path+"."+key if path else key
                declared = bool(META.search(key) or FAMILY.match(key)) or (not path and key in IDENTITY)
                self._value(child, active or declared, declared, depth+1)
                self._space()
                if self.i >= len(self.text):
                    raise ProjectionRefusal("incomplete JSON object")
                delimiter = self.text[self.i]
                self.i += 1
                if delimiter == "}":
                    break
                if delimiter != ",":
                    raise ProjectionRefusal("invalid JSON object delimiter")
            return
        if char == "[":
            self.i += 1
            self._space()
            if self.i < len(self.text) and self.text[self.i] == "]":
                self.i += 1
                return
            n = 0
            while True:
                self._value(path+"["+str(n)+"]", active, False, depth+1)
                n += 1
                self._space()
                if self.i >= len(self.text):
                    raise ProjectionRefusal("incomplete JSON array")
                delimiter = self.text[self.i]
                self.i += 1
                if delimiter == "]":
                    return
                if delimiter != ",":
                    raise ProjectionRefusal("invalid JSON array delimiter")
        if char == '"':
            value = self._string(active)
            if active:
                self.tags.append((path, "string", value))
            return
        start = self.i
        while self.i < len(self.text) and self.text[self.i] not in ",]} \t\r\n":
            self.i += 1
        if start == self.i:
            raise ProjectionRefusal("missing JSON primitive")
        token = self.text[start:self.i]
        # Do not convert numeric/analytical tokens. Direct metadata primitives
        # are flags or ambiguous metadata, never a numeric outcome read.
        if active and token in ("true", "false", "null"):
            self.tags.append((path, "literal", token))
        elif active:
            self.tags.append((path, "ambiguous", None))

    def scan(self):
        self._space()
        if self.i >= len(self.text) or self.text[self.i] != "{":
            raise ProjectionRefusal("decision row must be a JSON object")
        self._value("", False, False, 0)
        self._space()
        if self.i != len(self.text):
            raise ProjectionRefusal("trailing/noncomplete JSON line")
        return self.tags


def admit_metadata(tags):
    top = {p: (kind, value) for p, kind, value in tags if "." not in p and "[" not in p}
    if top.get("evidence_population") != ("string", "campaign_forward"):
        return False, "explicit_campaign_forward_population_missing_or_mismatch"
    if top.get("decision_id", (None, None))[0] != "string" or not top["decision_id"][1]:
        return False, "stable_decision_id_missing"
    if top.get("state", (None, None))[0] != "string" or not top["state"][1]:
        return False, "lifecycle_state_missing_or_ambiguous"
    for path, kind, value in tags:
        key = path.rsplit(".", 1)[-1].split("[", 1)[0]
        if kind == "ambiguous":
            return False, "ambiguous_declared_metadata"
        if "population" in path.lower() and (kind != "string" or value != "campaign_forward"):
            return False, "recursive_population_mismatch"
        if FLAGS.search(key) and not ((kind == "literal" and value in ("false", "null")) or
                                      (kind == "string" and value == "")):
            return False, "recursive_protected_flag"
        if FAMILY.match(key) and kind != "string":
            return False, "ambiguous_declared_identity_metadata"
        if FAMILY.match(key) and kind == "literal":
            return False, "ambiguous_declared_identity_metadata"
        if kind == "string" and PROTECTED.search(value):
            return False, "recursive_protected_metadata"
    return True, "explicit_original_campaign_metadata_admitted"


def _parse_admitted(line):
    def refuse_constant(value):
        raise ProjectionRefusal("nonfinite admitted analytical JSON token")
    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ProjectionRefusal("nonfinite admitted analytical number")
        return parsed
    return json.loads(line, parse_constant=refuse_constant, parse_float=finite_float)


def _clock(value):
    if not isinstance(value, str) or "T" not in value:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp.astimezone(timezone.utc) if stamp.tzinfo is not None else None


def _recorded(value):
    """Recorded version leaves are non-placeholder strings, never truthy blobs."""
    return (isinstance(value, str) and bool(value.strip()) and
            not re.search(r"unknown|unrecorded|unavailable|missing|not[ _-]?recorded|cannot determine|^none$|^null$|^n/?a$", value.strip(), re.I))


def _versions(value, depth=0):
    if depth > 32 or not isinstance(value, dict) or not value:
        return False
    return all(_recorded(k) and (_versions(v, depth+1) if isinstance(v, dict) else _recorded(v))
               for k, v in value.items())


def _finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _alias(values, parser, name, reasons):
    """Every declared alias must be valid and agree; no truthiness precedence."""
    declared = [parser(v) for present, v in values if present]
    if not declared or any(v is None for v in declared):
        reasons.append(name+" missing/invalid declared metadata")
        return None
    if any(v != declared[0] for v in declared[1:]):
        reasons.append(name+" contradictory declared aliases")
        return None
    return declared[0]


def qualification(row, cutoff):
    from backend.services import decision_ledger as DL
    detail = row.get("detail")
    if not isinstance(detail, dict):
        raise ProjectionRefusal("invalid admitted detail shape: object required")
    reasons = []
    formation = _alias([(k in obj, obj.get(k)) for obj, k in
        ((detail, "formation_utc"), (row, "formation_utc"), (row, "decided_utc"))], _clock, "formation", reasons)
    start = _alias([(k in detail, detail.get(k)) for k in ("label_start_at", "entry_utc")], _clock, "target start", reasons)
    end = _alias([(k in detail, detail.get(k)) for k in ("label_end_at", "exit_utc")], _clock, "target end", reasons)
    score = _alias([(k in obj, obj.get(k)) for obj, k in
        ((row, "utc"), (row, "score_persisted_utc"), (detail, "score_persisted_utc"),
         (detail, "score_available_utc"))], _clock, "score availability", reasons)
    expiry = _clock(detail.get("expiry_utc"))
    cut = _clock(cutoff)
    if cut is None:
        raise ProjectionRefusal("explicit UTC fit cutoff required")
    h = _alias([(k in detail, detail.get(k)) for k in ("er_horizon", "horizon_sessions")],
               lambda v: v if type(v) is int else None, "horizon", reasons)
    if row.get("state") != "SCORED":
        reasons.append("lifecycle not SCORED")
    if type(h) is not int or h != 21:
        reasons.append("exact H21 target unavailable; no alias")
    if None in (formation, start, end, score):
        reasons.append("exact formation/actual target-close/score-persisted clock missing; date-only is not PIT")
    elif not formation <= start < end <= score <= cut:
        reasons.append("formation/target/score unavailable by cutoff or chronology invalid")
    if formation is not None:
        if row.get("asof") != formation.date().isoformat() or formation > cut:
            reasons.append("formation/asof contract mismatch or future formation")
    if expiry is None or (end is not None and score is not None and not end <= expiry <= score):
        reasons.append("declared exact expiry unavailable or inconsistent with target/score")
    benchmark = _alias([(k in detail, detail.get(k)) for k in ("benchmark", "benchmark_symbol")],
                       lambda v: v if _recorded(v) else None, "benchmark", reasons)
    if not benchmark:
        reasons.append("declared benchmark unknown")
    if detail.get("target_calendar") != "XNYS" or detail.get("window_contract") != "session_close_to_close":
        reasons.append("actual exchange target contract unqualified")
    elif start is not None and end is not None:
        import exchange_calendars as xcals
        calendar = xcals.get_calendar("XNYS")
        try:
            if (calendar.session_close(start.date().isoformat()).to_pydatetime() != start or
                calendar.session_close(end.date().isoformat()).to_pydatetime() != end or
                len(calendar.sessions_in_range(start.date().isoformat(), end.date().isoformat()))-1 != 21):
                reasons.append("actual XNYS label duration/close mismatch")
        except (ValueError, KeyError):
            reasons.append("actual target date outside supported exchange sessions")
    if detail.get("task") != "expected_excess_return" or detail.get("score_units") != "decimal_price_excess_return":
        reasons.append("original task/score units unknown")
    if detail.get("grading_rule") != DL.SCORING_RULE:
        reasons.append("approved original grading rule unavailable")
    if row.get("by") != "decision_grader":
        reasons.append("approved original grader identity unavailable")
    excess = detail.get("excess_return")
    components = detail.get("er_by_component")
    if (not _finite(excess)
            or not isinstance(components, dict) or not components):
        reasons.append("finite original excess/component grades unavailable")
    elif any(not isinstance(v, dict) or not _finite(v.get("x")) for v in components.values()):
        reasons.append("finite component return input unavailable")
    if not _recorded(detail.get("model_version")) or not _versions(detail.get("source_versions")):
        reasons.append("original model/source versions unknown")
    if detail.get("costs_charged") is not False or type(detail.get("cost_rate_bps")) not in (int, float) or detail.get("cost_rate_bps") != 0:
        reasons.append("original price-excess grade cost provenance unavailable or inconsistent")
    return {"eligible_h21_training": not reasons, "reasons": reasons,
            "fit_cutoff": cutoff, "clock_status": "EXACT" if None not in (formation, start, end, score) else "UNKNOWN_OR_DATE_ONLY"}


def project_line(line: bytes, *, cutoff: str):
    tags = MetadataLexer(line).scan()
    okay, reason = admit_metadata(tags)
    if not okay:
        return None, tags, reason
    return _project_admitted(line, tags, reason, cutoff=cutoff), tags, reason


def _project_admitted(line, tags, reason, *, cutoff):
    row = _parse_admitted(line)
    detail = row.get("detail")
    if not isinstance(detail, dict):
        raise ProjectionRefusal("invalid admitted detail shape: object required")
    projected = {k: row.get(k) for k in ("decision_id", "state", "utc", "asof", "by", "evidence_population", "ledger_version", "formation_utc", "decided_utc")}
    projected.update(full_row_sha256=hashlib.sha256(line).hexdigest(),
                     detail={k: detail.get(k) for k in DETAIL_KEYS},
                     h21_qualification=qualification(row, cutoff), metadata_admission=reason)
    return projected


def _hash(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            value.update(chunk)
    return value.hexdigest()


def project_file(path, *, expected_sha256: str, cutoff: str):
    from backend.services import beta_v1_replay as limits
    budget = limits.RunBudget(max_seconds=30, max_rss_bytes=256*1024*1024, max_records=10000,
                             max_output_bytes=4*1024*1024)
    path = Path(path)
    budget.check("before decision source read")
    if path.stat().st_size > 2*1024*1024 or _hash(path) != expected_sha256:
        raise ProjectionRefusal("source file size/hash qualification mismatch")
    counts, families, populations = Counter(), Counter(), Counter()
    grouped = defaultdict(dict)
    with path.open("rb") as handle:
        n = 0
        while True:
            line = handle.readline(256*1024+1)
            if not line:
                break
            n += 1
            budget.check("decision metadata stream", records=n)
            counts["all_rows"] += 1
            if len(line) > 256*1024 or not line.endswith(b"\n"):
                raise ProjectionRefusal("line size/newline completeness limit")
            try:
                tags = MetadataLexer(line).scan()
                okay, reason = admit_metadata(tags)
            except (ProjectionRefusal, UnicodeError, json.JSONDecodeError) as exc:
                counts["excluded:malformed_or_ambiguous_metadata"] += 1
                populations["UNKNOWN_MALFORMED_METADATA"] += 1
                families["UNKNOWN_MALFORMED_METADATA"] += 1
                continue
            for p, kind, value in tags:
                if kind == "string" and "population" in p.lower():
                    populations[value] += 1
                elif "population" in p.lower():
                    populations["UNKNOWN_INVALID_TYPE:"+kind] += 1
                if kind == "string" and FAMILY.match(p.rsplit(".", 1)[-1].split("[", 1)[0]):
                    families[value.split(":", 1)[0]] += 1
                elif FAMILY.match(p.rsplit(".", 1)[-1].split("[", 1)[0]):
                    families["UNKNOWN_INVALID_TYPE:"+kind] += 1
            if not any("population" in p.lower() for p, _, _ in tags):
                populations["UNKNOWN_MISSING"] += 1
            if not any(kind == "string" and FAMILY.match(p.rsplit(".", 1)[-1].split("[", 1)[0]) for p, kind, _ in tags):
                families["UNKNOWN_MISSING_OR_CONTAINER"] += 1
            counts[reason] += 1
            top = {p: (kind, value) for p, kind, value in tags if "." not in p and "[" not in p}
            if (top.get("decision_id", (None, None))[0] == "string" and top["decision_id"][1] and
                    top.get("state", (None, None))[0] == "string" and top["state"][1]):
                key = (top["decision_id"][1], top["state"][1])
                raw_hash = hashlib.sha256(line).hexdigest()
                if raw_hash in grouped[key]:
                    counts["identical_raw_duplicate_idempotent"] += 1
                grouped[key][raw_hash] = (line, tags, okay, reason)
    if _hash(path) != expected_sha256:
        raise ProjectionRefusal("source changed during protected-first stream")
    rows, tables, eligible = [], {k: {} for k in ("row_metadata", "detail_metadata", "qualification")}, 0
    for key, versions in sorted(grouped.items(), key=lambda item: str(item[0])):
        if len(versions) != 1:
            counts["conflicting_identity_lifecycle_quarantined"] += len(versions)
            continue
        line, tags, okay, reason = next(iter(versions.values()))
        if not okay:
            continue
        budget.check("unique admitted analytical parse")
        try:
            projected = _project_admitted(line, tags, reason, cutoff=cutoff)
            rows.append(_compact_row(projected, tags, tables))
            eligible += projected["h21_qualification"]["eligible_h21_training"]
        except (ProjectionRefusal, ValueError, TypeError) as exc:
            counts["excluded:invalid_admitted_analytical_payload"] += 1
            if isinstance(exc, ProjectionRefusal) and "detail shape" in str(exc):
                counts["excluded:invalid_admitted_detail_shape"] += 1
    if _hash(path) != expected_sha256:
        raise ProjectionRefusal("source changed during admitted projection")
    result = {"schema": VERSION, "source_sha256_before_after": expected_sha256, "fit_cutoff": cutoff,
        "counts": dict(counts), "all_metadata_family_counts": dict(families), "all_population_counts": dict(populations),
        "metadata_counter_unit": "declared metadata occurrences, not unique row membership",
        "rows_private": rows, "eligible_h21_training_rows": eligible,
        "reference_tables": tables, "metadata_admission_contract": "explicit_original_campaign_metadata_admitted",
        "compact_row_contract": "content-addressed references; omitted selected fields reconstruct as null via declared key lists",
        "row_metadata_keys": ROW_METADATA_KEYS, "detail_keys": DETAIL_KEYS,
        "numerical_detail_keys": sorted(NUMERICAL_DETAIL_KEYS),
        "original_metadata_lookup": {"source_sha256": expected_sha256, "row_key": "full_row_sha256",
            "row_hash_contract": "SHA256 exact original JSONL row bytes including newline",
            "admission_metadata_hash_contract": "SHA256 canonical JSON recursive metadata-lexer tags; values not copied; re-lex only matching pinned original bytes"},
        "claims": "original projection only; no population path guess, calendar-day horizon approximation or activation"}
    result["artifact_hash"] = hashlib.sha256(canonical_bytes(result)).hexdigest()
    budget.check("decision projection output", output_bytes=limits.json_bytes(result))
    return result
