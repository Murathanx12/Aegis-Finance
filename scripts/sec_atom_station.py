"""Offline bounded SEC current-Atom metadata station; standard library only.

No application imports, discovery, resolver, security, exhibit or downstream path.
Caller pins an explicit snapshot manifest. Hashes prove consistency, not origin.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
from urllib.parse import urlsplit

ADAPTER = "sec-current-atom-station/2"
SOURCE = "sec_edgar_8k_current_atom"
MAX_IO = 1_048_576
MAX_OUTPUT = 1_048_576
MAX_LINE = 32_768
MAX_SECONDS = 30
MAX_STATE = 262_144
UTC = r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|\+00:00)"
ACCESSION = r"[0-9]{10}-[0-9]{2}-[0-9]{6}"


class StationRefused(ValueError):
    """Fixed safe diagnostics; never untrusted strings or source bytes."""


def fail(code: str) -> None:
    raise StationRefused(code)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def seal(value: dict) -> dict:
    return dict(value, integrity_sha256=digest(canonical(value)))


def unseal(value: dict) -> dict:
    body = {k: v for k, v in value.items() if k != "integrity_sha256"}
    if value.get("integrity_sha256") != digest(canonical(body)):
        fail("STATE_INTEGRITY")
    return body


def unique(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            fail("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def parse(data: bytes) -> dict:
    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=unique,
            parse_constant=lambda _: fail("INVALID_JSON"),
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, StationRefused):
            raise
        fail("INVALID_JSON")
    if type(value) is not dict:
        fail("INVALID_JSON")
    return value


def keys(value: dict, expected: str) -> None:
    if type(value) is not dict or set(value) != set(expected.split()):
        fail("INVALID_FIELDS")


def sha(value: object) -> str:
    if type(value) is not str or not re.fullmatch(r"[a-f0-9]{64}", value):
        fail("INVALID_SHA256")
    return value


def utc(value: object) -> datetime:
    if type(value) is not str or not re.fullmatch(UTC, value):
        fail("INVALID_CLOCK")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail("INVALID_CLOCK")


def safe_path(path: Path, *, directory: bool = False, external: bool = False) -> None:
    if (
        not isinstance(path, Path)
        or not path.is_absolute()
        or ".." in path.parts
        or str(path).startswith("\\\\")
    ):
        fail("INVALID_PATH")
    try:
        for part in (path, *path.parents):
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                fail("REDIRECT_PATH")
            if external and (part / ".git").exists():
                fail("OUTPUT_IN_REPOSITORY")
        info = path.stat()
        if directory and not stat.S_ISDIR(info.st_mode):
            fail("INVALID_DIRECTORY")
        if not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
            fail("INVALID_FILE")
    except OSError:
        fail("PATH_UNAVAILABLE")


class Budget:
    def __init__(self) -> None:
        self.started = time.monotonic()
        self.input_bytes = 0

    def check(self) -> None:
        if time.monotonic() - self.started > MAX_SECONDS:
            fail("TIME_LIMIT")

    def charge(self, count: int) -> None:
        self.check()
        self.input_bytes += count
        if self.input_bytes > MAX_IO:
            fail("INPUT_IO_LIMIT")

    def read(self, path: Path, cap: int) -> bytes:
        safe_path(path)
        before = path.stat()
        if before.st_size > cap:
            fail("BYTE_LIMIT")
        if before.st_size > MAX_IO - self.input_bytes:
            fail("INPUT_IO_LIMIT")
        try:
            with path.open("rb", buffering=0) as stream:
                opened = os.fstat(stream.fileno())
                if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                    fail("PATH_CHANGED")
                data = stream.read(before.st_size)
                self.charge(len(data))
            safe_path(path)
            after = path.stat()
            if len(data) != before.st_size or (after.st_dev, after.st_ino, after.st_size) != (
                before.st_dev,
                before.st_ino,
                before.st_size,
            ):
                fail("FILE_CHANGED")
            return data
        except OSError:
            fail("READ_FAILED")


def snapshot(path: Path, budget: Budget, prefix_bytes: int = 0, prior_size: int = 0) -> dict:
    """Stream hash/count without interpreting or retaining source bodies."""
    safe_path(path)
    before = path.stat()
    whole, prefix, prior = hashlib.sha256(), hashlib.sha256(), hashlib.sha256()
    count = total = prefix_rows = 0
    prefix_last = b""
    last = b""
    try:
        with path.open("rb", buffering=0) as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                fail("PATH_CHANGED")
            while total < before.st_size:
                remaining = MAX_IO - budget.input_bytes
                if remaining <= 0:
                    fail("INPUT_IO_LIMIT")
                block = stream.read(min(65536, remaining, before.st_size - total))
                budget.charge(len(block))
                if not block:
                    fail("SOURCE_CHANGED")
                whole.update(block)
                piece = block[: max(0, prefix_bytes - total)]
                prefix.update(piece)
                prefix_rows += piece.count(b"\n")
                if piece:
                    prefix_last = piece[-1:]
                prior.update(block[: max(0, prior_size - total)])
                total += len(block)
                count += block.count(b"\n")
                last = block[-1:]
    except OSError:
        fail("READ_FAILED")
    safe_path(path)
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
    ):
        fail("SOURCE_CHANGED")
    if total and last != b"\n":
        fail("PARTIAL_TRAILING_LINE")
    return dict(
        sha256=whole.hexdigest(),
        bytes=total,
        rows=count,
        prefix_sha256=prefix.hexdigest(),
        prefix_rows=prefix_rows,
        prefix_boundary=prefix_bytes == 0 or prefix_last == b"\n",
        prior_sha256=prior.hexdigest(),
    )


def cik(raw: object) -> str:
    if type(raw) is not str or not re.fullmatch(r"[0-9]{1,10}", raw) or int(raw) == 0:
        fail("INVALID_CIK")
    return raw.zfill(10)


def project(row: dict, observed: datetime) -> dict:
    """Only validated source metadata leaves this function; body is never read."""
    if row.get("source") != SOURCE:
        fail("WRONG_SOURCE")
    accession = row.get("raw_id")
    if type(accession) is not str or not re.fullmatch(ACCESSION, accession):
        fail("INVALID_ACCESSION")
    title = row.get("title")
    if type(title) is not str or len(title) > 240:
        fail("INVALID_FILER_TITLE")
    match = re.fullmatch(
        r"(8-K(?:/A)?) - ([A-Za-z0-9][A-Za-z0-9 &.,\'()/+\-]{0,159}) \(([0-9]{1,10})\) \(Filer\)",
        title,
    )
    if not match:
        fail("UNSUPPORTED_FORM_OR_TITLE")
    form, label, raw_cik = match.groups()
    issuer = cik(raw_cik)
    url = row.get("url")
    if type(url) is not str or len(url) > 300:
        fail("INVALID_SEC_URL")
    try:
        parsed = urlsplit(url)
    except ValueError:
        fail("INVALID_SEC_URL")
    if (
        parsed.scheme != "https"
        or parsed.netloc not in {"sec.gov", "www.sec.gov"}
        or parsed.query
        or parsed.fragment
    ):
        fail("INVALID_SEC_URL")
    path = re.fullmatch(
        r"/Archives/edgar/data/([0-9]{1,10})/([0-9]{18})/(" + ACCESSION + r"-index\.html?)",
        parsed.path,
    )
    if not path:
        fail("NOT_FILING_INDEX")
    url_cik, compact, filename = path.groups()
    if cik(url_cik) != issuer:
        fail("CONFLICTING_CIK")
    if compact != accession.replace("-", "") or not filename.startswith(accession + "-index."):
        fail("ACCESSION_URL_MISMATCH")
    tags, tickers = row.get("entity_tags", []), row.get("tickers", [])
    if type(tags) is not list or len(tags) > 32 or type(tickers) is not list or len(tickers) > 32:
        fail("TAG_LIMIT")
    raw_ciks, items = [], set()
    for tag in tags:
        if type(tag) is not str or len(tag) > 100:
            fail("INVALID_TAG")
        if tag.startswith("cik:"):
            raw = tag[4:]
            if cik(raw) != issuer:
                fail("CONFLICTING_CIK")
            raw_ciks.append(raw)
        elif tag.startswith("8-K:"):
            if not re.fullmatch(r"8-K:[1-9]\.[0-9]{2}", tag):
                fail("INVALID_ITEM_CODE")
            items.add(tag[4:])
    hints = []
    for symbol in tickers:
        if type(symbol) is not str or not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,11}", symbol):
            fail("INVALID_HINT")
        hints.append(symbol)
    published_raw, seen_raw = row.get("published_utc"), row.get("first_seen_utc")
    published, seen = utc(published_raw), utc(seen_raw)
    if published > observed or seen > observed:
        fail("FUTURE_CLOCK")
    if published > seen:
        fail("PUBLICATION_AFTER_FIRST_SEEN")
    filing_id = digest(canonical([issuer, accession]))
    document_id = digest(canonical([issuer, accession, filename]))
    return dict(
        record_kind="FILING_INDEX_METADATA",
        filing_id=filing_id,
        document_id=document_id,
        issuer_cik=issuer,
        raw_cik_evidence=dict(
            title_filer=raw_cik, filing_index_path=url_cik, cik_tags=sorted(set(raw_ciks))
        ),
        issuer_label=label,
        accession=accession,
        raw_accession=accession,
        form=form,
        document_filename=filename,
        filing_link=url,
        reported_item_codes=sorted(items),
        published_raw=published_raw,
        published_utc=published.isoformat(),
        published_basis="ATOM_UPDATED_AS_PUBLISHED",
        first_seen_raw=seen_raw,
        first_seen_utc=seen.isoformat(),
        clock_validity="VALID_SAVED_CLAIMS",
        acceptance_utc="UNKNOWN",
        filing_date="UNKNOWN",
        event_date="UNKNOWN",
        amends_filing_id="UNKNOWN",
        security_identity="UNKNOWN",
        issuer_resolution="UNRESOLVED",
        ticker_hints=sorted(set(hints)),
        hint_authority="HEURISTIC_DISCOVERY_HINT",
        rights="SAVED_REGISTRY_DECLARATION / METADATA_ONLY / EXTERNAL_TERMS_UNVERIFIED",
        authority="FILING_DISCOVERY_ONLY",
        exhibit_acquisition_complete=False,
    )


def clock_evidence(row: dict | None, observed: datetime) -> dict:
    result = {}
    for name in ("published_utc", "first_seen_utc"):
        raw = row.get(name) if row else None
        safe_raw = raw if type(raw) is str and re.fullmatch(UTC, raw) else "UNKNOWN"
        parsed, validity = "UNKNOWN", "INVALID_OR_MISSING"
        try:
            value = utc(raw)
            parsed = value.isoformat()
            validity = "FUTURE" if value > observed else "VALID_SAVED_CLAIM"
        except StationRefused:
            pass
        result[name] = dict(
            raw=safe_raw,
            parsed_utc=parsed,
            validity=validity,
            raw_value_sha256=digest(canonical(raw)),
        )
    return result


@contextmanager
def locked(output: Path):
    path = output / "station.lock"
    if os.path.lexists(path):
        safe_path(path)
    with path.open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fail("STATION_BUSY")
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def write_stage(path: Path, data: bytes) -> None:
    # Only deterministic station-owned temporary names, under an OS lock.
    if os.path.lexists(path):
        safe_path(path)
        path.unlink()
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def commit_cursor(output: Path, cursor: dict, fault=None) -> None:
    data = canonical(seal(cursor)) + b"\n"
    if len(data) > MAX_STATE:
        fail("STATE_LIMIT")
    temporary = output / ".cursor.pending"
    write_stage(temporary, data)
    if fault:
        fault("after_cursor_stage")
    target = output / "cursor.json"
    if os.path.lexists(target):
        safe_path(target)
    if fault:
        fault("before_cursor_replace")
    os.replace(temporary, target)


def validate_before_cursor(
    *, source: Path, manifest_path: Path, manifest_data: bytes, manifest: dict, budget: Budget
) -> None:
    """Identical bounded commit-time evidence gate for cold and recovered passes."""
    final = snapshot(source, budget)
    if final["sha256"] != manifest["sha256"] or final["bytes"] != manifest["bytes"]:
        fail("SOURCE_CHANGED_BEFORE_CURSOR")
    if budget.read(manifest_path, 4096) != manifest_data:
        fail("MANIFEST_CHANGED_BEFORE_CURSOR")
    budget.check()


def validate_cursor(cursor: dict) -> None:
    keys(
        cursor,
        "adapter source_identity relative_path physical_lines byte_offset prefix_sha256 snapshot_sha256 snapshot_bytes versions accessions last_bundle_sha256 last_request_id",
    )
    for field in ("source_identity", "prefix_sha256"):
        sha(cursor[field])
    for field in ("snapshot_sha256", "last_bundle_sha256", "last_request_id"):
        if cursor[field] is not None:
            sha(cursor[field])
    for field in ("physical_lines", "byte_offset", "snapshot_bytes"):
        if type(cursor[field]) is not int or cursor[field] < 0:
            fail("INVALID_CURSOR")
    if type(cursor["versions"]) is not dict or type(cursor["accessions"]) is not dict:
        fail("INVALID_CURSOR")
    if len(cursor["versions"]) > 4096 or len(cursor["accessions"]) > 4096:
        fail("STATE_LIMIT")
    for document, versions in cursor["versions"].items():
        sha(document)
        if type(versions) is not list or not versions or len(versions) > 4096:
            fail("INVALID_CURSOR")
        for version in versions:
            sha(version)
    for accession, filers in cursor["accessions"].items():
        if (
            not re.fullmatch(ACCESSION, accession)
            or type(filers) is not list
            or not filers
            or len(filers) > 100
        ):
            fail("INVALID_CURSOR")
        for filer in filers:
            if cik(filer) != filer:
                fail("INVALID_CURSOR")


def run_pass(
    *,
    source_root: Path,
    manifest_path: Path,
    manifest_sha256: str,
    output_dir: Path,
    start_line: int = 0,
    line_limit: int = 100,
    _fault=None,
) -> dict:
    """One pinned file/pass; start_line is the expected committed physical count.

    Identical requests return the original committed bundle. Cursor is independent
    of collector state. _fault is solely an in-process crash-test boundary hook.
    """
    try:
        return _run(
            source_root, manifest_path, manifest_sha256, output_dir, start_line, line_limit, _fault
        )
    except StationRefused:
        raise
    except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError):
        fail("INVALID_STATION_INPUT")


def _run(
    root: Path,
    manifest_path: Path,
    manifest_sha256: str,
    output: Path,
    start_line: int,
    limit: int,
    fault,
) -> dict:
    budget = Budget()
    observed = datetime.now(timezone.utc)
    if (
        type(start_line) is not int
        or start_line < 0
        or type(limit) is not int
        or not 1 <= limit <= 100
    ):
        fail("INVALID_PASS_BOUND")
    safe_path(root, directory=True)
    safe_path(output, directory=True, external=True)
    if root == output or root in output.parents or output in root.parents:
        fail("OUTPUT_OVERLAPS_SOURCE")
    manifest_data = budget.read(manifest_path, 4096)
    if digest(manifest_data) != sha(manifest_sha256):
        fail("MANIFEST_PIN_MISMATCH")
    manifest = parse(manifest_data)
    keys(manifest, "schema adapter source relative_path sha256 bytes observed_at_utc")
    if (
        manifest["schema"] != "sec-atom-snapshot/1"
        or manifest["adapter"] != ADAPTER
        or manifest["source"] != SOURCE
    ):
        fail("MANIFEST_SCHEMA")
    relative = manifest["relative_path"]
    if type(relative) is not str or not re.fullmatch(
        SOURCE + r"/[0-9]{4}-[0-9]{2}-[0-9]{2}\.jsonl", relative
    ):
        fail("INVALID_SOURCE_PATH")
    try:
        datetime.strptime(relative.split("/")[1], "%Y-%m-%d.jsonl")
    except ValueError:
        fail("INVALID_SOURCE_PATH")
    snapshot_observed = utc(manifest["observed_at_utc"])
    if snapshot_observed > observed:
        fail("FUTURE_MANIFEST")
    sha(manifest["sha256"])
    if type(manifest["bytes"]) is not int or not 0 <= manifest["bytes"] <= MAX_IO // 2:
        fail("SNAPSHOT_SIZE_LIMIT")
    source = root / relative
    source_identity = digest(canonical([str(root), relative, SOURCE]))
    request_id = digest(canonical([ADAPTER, manifest_sha256, source_identity, start_line, limit]))
    bundle_dir = output / ("pass-" + request_id)
    bundle_path = bundle_dir / "bundle.json"
    cursor_path = output / "cursor.json"
    with locked(output):
        cursor = None
        cursor_hash = None
        if os.path.lexists(cursor_path):
            raw_cursor = budget.read(cursor_path, MAX_STATE)
            cursor_hash = digest(raw_cursor)
            cursor = unseal(parse(raw_cursor))
            validate_cursor(cursor)
            if cursor["adapter"] != ADAPTER or cursor["source_identity"] != source_identity:
                fail("CURSOR_BINDING_OR_PARSER_DRIFT")
        # Replaying/recovering a published transaction never reconstructs its bytes.
        if os.path.lexists(bundle_path):
            bundle_bytes = budget.read(bundle_path, MAX_OUTPUT)
            bundle = unseal(parse(bundle_bytes))
            if bundle["request_id"] != request_id or bundle["manifest_sha256"] != manifest_sha256:
                fail("BUNDLE_BINDING")
            check = snapshot(source, budget, bundle["cursor_after"]["byte_offset"])
            if check["sha256"] != manifest["sha256"] or check["bytes"] != manifest["bytes"]:
                fail("SOURCE_PIN_MISMATCH")
            after = dict(bundle["cursor_after"], last_bundle_sha256=digest(bundle_bytes))
            validate_cursor(after)
            if (
                after["byte_offset"] > check["bytes"]
                or after["prefix_sha256"] != check["prefix_sha256"]
                or not check["prefix_boundary"]
                or after["physical_lines"] != check["prefix_rows"]
            ):
                fail("RECOVERY_BOUNDARY_MISMATCH")
            if cursor == after:
                return dict(execution="COMMITTED_PASS_REPLAY", receipt=bundle["receipt"])
            if cursor_hash != bundle["cursor_before_sha256"]:
                fail("RECOVERY_CURSOR_CONFLICT")
            if fault:
                fault("before_cursor")
            validate_before_cursor(
                source=source,
                manifest_path=manifest_path,
                manifest_data=manifest_data,
                manifest=manifest,
                budget=budget,
            )
            commit_cursor(output, after, fault)
            return dict(execution="RECOVERED_COMMIT", receipt=bundle["receipt"])
        if cursor is None:
            cursor = dict(
                adapter=ADAPTER,
                source_identity=source_identity,
                relative_path=relative,
                physical_lines=0,
                byte_offset=0,
                prefix_sha256=digest(b""),
                snapshot_sha256=None,
                snapshot_bytes=0,
                versions={},
                accessions={},
                last_bundle_sha256=None,
                last_request_id=None,
            )
        if cursor["physical_lines"] != start_line:
            fail("CURSOR_POSITION_MISMATCH")
        if cursor["last_bundle_sha256"] is not None:
            # Verify the immediately preceding commit anchor without unbounded scans.
            anchor = output / ("pass-" + cursor["last_request_id"]) / "bundle.json"
            anchor_bytes = budget.read(anchor, MAX_OUTPUT)
            if digest(anchor_bytes) != cursor["last_bundle_sha256"]:
                fail("PREVIOUS_BUNDLE_TAMPER")
            anchor_body = unseal(parse(anchor_bytes))
            expected_cursor = dict(
                anchor_body["cursor_after"], last_bundle_sha256=digest(anchor_bytes)
            )
            if cursor != expected_cursor:
                fail("CURSOR_ANCHOR_MISMATCH")
        first = snapshot(source, budget, cursor["byte_offset"], cursor["snapshot_bytes"])
        if cursor["snapshot_sha256"] is not None and (
            first["bytes"] < cursor["snapshot_bytes"]
            or first["prior_sha256"] != cursor["snapshot_sha256"]
        ):
            fail("SNAPSHOT_REWRITE_OR_TRUNCATION")
        if first["sha256"] != manifest["sha256"] or first["bytes"] != manifest["bytes"]:
            fail("SOURCE_PIN_MISMATCH")
        if (
            cursor["byte_offset"] > first["bytes"]
            or first["prefix_sha256"] != cursor["prefix_sha256"]
        ):
            fail("PREFIX_REWRITE_OR_TRUNCATION")
        if start_line != first["prefix_rows"] or not first["prefix_boundary"]:
            fail("CURSOR_POSITION_MISMATCH")
        records, occurrences, quarantines = [], [], []
        counts = Counter(
            attempted=0,
            projected_new=0,
            exact_replays=0,
            quarantined=0,
            explicitly_excluded=0,
            changed_versions=0,
        )
        reasons = Counter()
        versions = {k: list(v) for k, v in cursor["versions"].items()}
        accessions = {k: list(v) for k, v in cursor["accessions"].items()}
        offset = cursor["byte_offset"]
        safe_path(source)
        with source.open("rb", buffering=0) as stream:
            stream.seek(offset)
            for index in range(limit):
                budget.check()
                remaining = MAX_IO - budget.input_bytes
                if remaining <= 0:
                    fail("INPUT_IO_LIMIT")
                raw = stream.readline(min(MAX_LINE + 1, remaining))
                budget.charge(len(raw))
                if not raw:
                    break
                if len(raw) > MAX_LINE:
                    fail("LINE_BYTE_LIMIT")
                if not raw.endswith(b"\n"):
                    fail("PARTIAL_TRAILING_LINE")
                pointer = dict(
                    source=SOURCE,
                    relative_path=relative,
                    physical_line=start_line + index + 1,
                    byte_start=offset,
                    byte_end=offset + len(raw),
                    line_sha256=digest(raw),
                    snapshot_sha256=manifest["sha256"],
                    manifest_sha256=manifest_sha256,
                    adapter=ADAPTER,
                )
                occurrence_id = digest(
                    canonical([SOURCE, relative, start_line + index + 1, offset, digest(raw)])
                )
                counts["attempted"] += 1
                row = None
                try:
                    row = parse(raw)
                    metadata = project(row, observed)
                    if (
                        utc(row["published_utc"]) > snapshot_observed
                        or utc(row["first_seen_utc"]) > snapshot_observed
                    ):
                        fail("ROW_CLOCK_AFTER_SNAPSHOT_OBSERVATION")
                except StationRefused as exc:
                    reason = str(exc)
                    reasons[reason] += 1
                    counts["quarantined"] += 1
                    quarantines.append(
                        dict(
                            pointer=pointer,
                            occurrence_id=occurrence_id,
                            reason=reason,
                            clock_evidence=clock_evidence(row, observed),
                            authority="NONE",
                        )
                    )
                else:
                    document = metadata["document_id"]
                    version = digest(canonical([document, digest(raw), ADAPTER]))
                    prior = versions.setdefault(document, [])
                    if version in prior:
                        counts["exact_replays"] += 1
                    else:
                        counts["projected_new"] += 1
                        counts["changed_versions"] += bool(prior)
                        prior.append(version)
                        filers = accessions.setdefault(metadata["accession"], [])
                        if metadata["issuer_cik"] not in filers:
                            filers.append(metadata["issuer_cik"])
                        records.append(
                            dict(
                                metadata,
                                metadata_version_id=version,
                                first_occurrence_id=occurrence_id,
                                cross_observation_ambiguity=len(filers) > 1,
                                observed_ciks_for_accession=sorted(filers),
                                pointer=pointer,
                                projection_observed_at_utc=observed.isoformat(),
                            )
                        )
                    occurrences.append(
                        dict(
                            occurrence_id=occurrence_id,
                            metadata_version_id=version,
                            pointer=pointer,
                        )
                    )
                offset += len(raw)
        for record in records:
            known_filers = sorted(accessions[record["accession"]])
            record["observed_ciks_for_accession"] = known_filers
            record["cross_observation_ambiguity"] = len(known_filers) > 1
        second = snapshot(source, budget, offset)
        if (second["sha256"], second["bytes"]) != (first["sha256"], first["bytes"]):
            fail("SOURCE_CHANGED_DURING_PASS")
        budget.check()
        if counts["attempted"] == 0 and offset < first["bytes"]:
            fail("ZERO_PROGRESS_WITH_PENDING_WORK")
        after = dict(
            adapter=ADAPTER,
            source_identity=source_identity,
            relative_path=relative,
            physical_lines=start_line + counts["attempted"],
            byte_offset=offset,
            prefix_sha256=second["prefix_sha256"],
            snapshot_sha256=manifest["sha256"],
            snapshot_bytes=first["bytes"],
            versions=versions,
            accessions=accessions,
            last_request_id=request_id,
            last_bundle_sha256=None,
        )
        receipt = dict(
            schema=ADAPTER,
            request_id=request_id,
            status=(
                "NO_PENDING_ROWS"
                if counts["attempted"] == 0
                else "QUARANTINED_ONLY"
                if counts["quarantined"] == counts["attempted"]
                else "EXACT_REPLAYS_ONLY"
                if counts["exact_replays"] == counts["attempted"]
                else "BOUNDED_METADATA_PASS"
            ),
            scope="FIRST_100_PHYSICAL_LINES"
            if start_line == 0 and limit == 100
            else "BOUNDED_PHYSICAL_LINES",
            coverage="PARTIAL",
            observed_at_utc=observed.isoformat(),
            manifest_observed_at_utc=manifest["observed_at_utc"],
            snapshot_sha256=manifest["sha256"],
            manifest_sha256=manifest_sha256,
            counts=dict(counts),
            reason_counts=dict(reasons),
            cross_observation_ambiguities=[
                dict(accession=a, observed_ciks=sorted(filers))
                for a, filers in sorted(accessions.items())
                if len(filers) > 1
            ],
            remaining_bytes=first["bytes"] - offset,
            remaining_physical_rows=first["rows"] - after["physical_lines"],
            cursor_before_sha256=cursor_hash,
            cursor_after_line=after["physical_lines"],
            cursor_after_byte=offset,
            cursor_after_prefix_sha256=second["prefix_sha256"],
            total_input_io_bytes=budget.input_bytes + first["bytes"] + len(manifest_data),
            elapsed_before_commit_seconds=time.monotonic() - budget.started,
            security_identity="UNKNOWN",
            issuer_authority="NONE",
            held_authority="NONE",
            cause_authority="NONE",
            forecast="NONE",
            owner_authority="NONE",
            delivery="NOT_ATTEMPTED",
            exhibit_acquisition_complete=False,
            historical_PIT_completeness="UNVERIFIED",
        )
        assert (
            counts["attempted"]
            == counts["projected_new"]
            + counts["exact_replays"]
            + counts["quarantined"]
            + counts["explicitly_excluded"]
        )
        bundle = dict(
            request_id=request_id,
            manifest_sha256=manifest_sha256,
            cursor_before_sha256=cursor_hash,
            cursor_after=after,
            records=records,
            occurrences=occurrences,
            quarantines=quarantines,
            receipt=receipt,
        )
        data = canonical(seal(bundle)) + b"\n"
        reserved_cursor = dict(after, last_bundle_sha256="0" * 64)
        if receipt["total_input_io_bytes"] > MAX_IO:
            fail("INPUT_IO_LIMIT")
        if (
            len(data) + len(canonical(seal(reserved_cursor))) > MAX_OUTPUT
            or len(canonical(seal(reserved_cursor))) > MAX_STATE
        ):
            fail("OUTPUT_OR_STATE_LIMIT")
        if fault:
            fault("before_bundle")
        stage = output / (".pass-" + request_id + ".pending")
        if os.path.lexists(stage):
            safe_path(stage, directory=True, external=True)
            children = list(stage.iterdir())
            if any(p.name != "bundle.json" for p in children) or len(children) > 1:
                fail("UNEXPECTED_STAGING_CONTENT")
            if children:
                safe_path(children[0])
                children[0].unlink()
            stage.rmdir()
        stage.mkdir()
        write_stage(stage / "bundle.json", data)
        if fault:
            fault("after_stage")
        # Nonempty transaction directories cannot be overwritten by rename.
        if os.path.lexists(bundle_dir):
            fail("BUNDLE_ALREADY_EXISTS")
        budget.check()
        os.rename(stage, bundle_dir)
        if fault:
            fault("after_bundle")
        # Anchor lives only in cursor to avoid a circular bundle hash dependency.
        after = dict(after, last_bundle_sha256=digest(data))
        if fault:
            fault("before_cursor")
        validate_before_cursor(
            source=source,
            manifest_path=manifest_path,
            manifest_data=manifest_data,
            manifest=manifest,
            budget=budget,
        )
        commit_cursor(output, after, fault)
        if fault:
            fault("after_cursor")
        return dict(execution="COMMITTED", receipt=receipt)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--start-line", type=int, default=0)
    parser.add_argument("--line-limit", type=int, default=100)
    args = parser.parse_args(argv)
    try:
        result = run_pass(
            source_root=args.source_root,
            manifest_path=args.manifest,
            manifest_sha256=args.manifest_sha256,
            output_dir=args.output_dir,
            start_line=args.start_line,
            line_limit=args.line_limit,
        )
    except StationRefused as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 1 if result["receipt"]["counts"]["quarantined"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
