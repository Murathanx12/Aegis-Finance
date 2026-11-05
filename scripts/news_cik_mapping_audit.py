"""Read saved SEC EX99 inputs and print sanitized candidate JSON; no writes/calls.

PRODUCT_EXPERIMENT. Example (all paths explicitly supplied, no live defaults)::

    python -B -m scripts.news_cik_mapping_audit --corpus EX99.jsonl \
        --master company_tickers.json --master-meta company_tickers.meta.json \
        --proxy universe_2026-11-01.parquet --proxy-receipt RECEIPT.json \
        --as-of 2026-11-05T06:00:00Z

Legacy metadata does not bind bytes: its date is unverified and cannot backdate
availability before this audit's observation. No mtime fallback. Historical use
requires --provenance-manifest plus --provenance-manifest-sha256, an independently
verified digest supplied by the caller (not calculated here as a trust decision).
Manifest schema: {"schema_version": 1, "snapshots": {"master" or "proxy":
{"data_sha256": "...", "metadata_sha256": "...", "known_at_utc": "..."}}}.
For a proxy copy whose path differs from the receipt, that proxy entry must also
name source_path matching the receipt. Both hashes must match, so replacement
bytes or a different receipt cannot inherit that manifest's availability.
Only market/symbol/exchange are read from parquet; no amounts or article bodies
are emitted. Exit 0 = completed audit (possibly empty), 1 = rejected corpus rows,
2 = invalid/unreadable input. Saved source bytes are hashed to bind provenance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath

from backend.services.news_cik_mapping import CandidateMapper, MappingError, Snapshot, canonical_utc


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _receipt_clock(value):
    if isinstance(value, str) and re.fullmatch(r"[0-9]{8}T[0-9]{6}Z", value):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).isoformat()
    return value


def _observation_clock() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path_key(value: str, base: Path) -> str:
    # Compare saved Windows paths even when running this offline audit elsewhere.
    windows = PureWindowsPath(value)
    if windows.is_absolute():
        return windows.as_posix().casefold()
    path = Path(value)
    return os.path.normcase(str((path if path.is_absolute() else base / path).resolve()))


def _manifest_entries(path: Path | None, expected_hash: str | None, actual_hash: str | None) -> dict:
    if path is None and expected_hash is None:
        return {}
    if (path is None or not isinstance(expected_hash, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)):
        raise MappingError("INVALID_PROVENANCE_MANIFEST_OPTIONS")
    if expected_hash != actual_hash:
        raise MappingError("PROVENANCE_MANIFEST_HASH_MISMATCH")
    manifest = _read_json(path)
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != 1
            or not isinstance(manifest.get("snapshots"), dict)
            or not manifest["snapshots"]
            or not all(isinstance(entry, dict) for entry in manifest["snapshots"].values())
            or not set(manifest["snapshots"]) <= {"master", "proxy"}):
        raise MappingError("INVALID_PROVENANCE_MANIFEST")
    return manifest["snapshots"]


def _bound_snapshot(data_hash: str, metadata_hash: str, declared_at, observed_at: str,
                    entry: dict | None) -> tuple[Snapshot, dict]:
    if declared_at is not None:
        canonical_utc(declared_at)
    if entry is not None:
        if not isinstance(entry, dict):
            raise MappingError("INVALID_PROVENANCE_MANIFEST")
        if entry.get("data_sha256") != data_hash or entry.get("metadata_sha256") != metadata_hash:
            raise MappingError("PROVENANCE_CONTENT_MISMATCH")
        known = entry.get("known_at_utc")
        canonical_utc(known)
        basis = "PINNED_CONTENT_PROVENANCE"
    else:
        # A legacy date may conservatively delay availability, never backdate it.
        known = max((s for s in (observed_at, declared_at) if s is not None), key=canonical_utc)
        basis = "CURRENT_OBSERVATION_NO_VERIFIED_VINTAGE"
    return Snapshot(data_hash, known), {
        "clock_basis": basis, "declared_at_utc": declared_at,
        "declared_clock_binding": "UNVERIFIED_LEGACY_METADATA",
    }


def audit_files(*, corpus_paths: list[Path], master_path: Path, master_meta_path: Path,
                proxy_path: Path, proxy_receipt_path: Path, as_of_utc: str,
                provenance_manifest_path: Path | None = None,
                provenance_manifest_sha256: str | None = None) -> dict:
    # pandas is optional for the pure in-memory module, required for saved parquet.
    import pandas as pd

    paths = [*corpus_paths, master_path, master_meta_path, proxy_path, proxy_receipt_path]
    if provenance_manifest_path is not None:
        paths.append(provenance_manifest_path)
    before = [_fingerprint(p) for p in paths]
    n = len(corpus_paths)
    master_hash, meta_hash, proxy_hash, receipt_hash = before[n:n + 4]
    entries = _manifest_entries(provenance_manifest_path, provenance_manifest_sha256,
                                before[-1] if provenance_manifest_path is not None else None)
    master = _read_json(master_path)
    meta = _read_json(master_meta_path)
    receipt = _read_json(proxy_receipt_path)
    if not isinstance(master, dict) or not all(isinstance(v, dict) for v in master.values()):
        raise MappingError("INVALID_SEC_MASTER_SHAPE")
    if not isinstance(meta, dict) or not isinstance(receipt, dict):
        raise MappingError("INVALID_SNAPSHOT_METADATA")
    proxy = pd.read_parquet(proxy_path, columns=["market", "symbol", "exchange"])
    proxy = proxy.astype(object).where(pd.notna(proxy), None)
    if meta.get("n_entries") != len(master) or receipt.get("rows_after") != len(proxy):
        raise MappingError("SNAPSHOT_ROW_COUNT_MISMATCH")
    observed_at = _observation_clock()
    master_snapshot, master_clock = _bound_snapshot(
        master_hash, meta_hash, meta.get("fetched_at_utc"), observed_at, entries.get("master"))
    proxy_snapshot, proxy_clock = _bound_snapshot(
        proxy_hash, receipt_hash, _receipt_clock(receipt.get("written_utc")), observed_at, entries.get("proxy"))
    if "path" in receipt:
        named_path = receipt["path"]
        if not isinstance(named_path, str) or not named_path:
            raise MappingError("INVALID_PROXY_RECEIPT_PATH")
        base = proxy_receipt_path.resolve().parent
        if _path_key(named_path, base) != _path_key(str(proxy_path.resolve()), base):
            # Relocation is allowed only through caller-pinned byte provenance,
            # including the original association claimed by this exact receipt.
            origin = entries.get("proxy", {}).get("source_path")
            if not isinstance(origin, str) or _path_key(origin, base) != _path_key(named_path, base):
                raise MappingError("PROXY_RECEIPT_PATH_CONTRADICTION")
    mapper = CandidateMapper(
        master.values(), proxy.to_dict("records"),
        master_snapshot=master_snapshot, proxy_snapshot=proxy_snapshot,
    )

    def corpus_rows():
        for path in corpus_paths:
            with path.open(encoding="utf-8-sig") as stream:
                for line in stream:
                    if line.strip():
                        yield json.loads(line)

    result = mapper.audit(corpus_rows(), as_of_utc=as_of_utc)
    if before != [_fingerprint(p) for p in paths]:
        raise MappingError("INPUT_CHANGED_DURING_AUDIT")
    # No local paths or source JSON are copied into the public-safe result.
    result["input_sha256"] = {
        "corpus": before[:n], "master": master_hash, "master_meta": meta_hash,
        "proxy": proxy_hash, "proxy_receipt": receipt_hash,
    }
    if provenance_manifest_path is not None:
        result["input_sha256"]["provenance_manifest"] = before[-1]
    result["observed_at_utc"] = observed_at
    result["master_snapshot"].update(master_clock)
    result["proxy_snapshot"].update(proxy_clock)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", action="append", required=True, type=Path)
    parser.add_argument("--master", required=True, type=Path)
    parser.add_argument("--master-meta", required=True, type=Path)
    parser.add_argument("--proxy", required=True, type=Path)
    parser.add_argument("--proxy-receipt", required=True, type=Path)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--provenance-manifest", type=Path)
    parser.add_argument("--provenance-manifest-sha256")
    args = parser.parse_args(argv)
    try:
        result = audit_files(corpus_paths=args.corpus, master_path=args.master,
                             master_meta_path=args.master_meta, proxy_path=args.proxy,
                             proxy_receipt_path=args.proxy_receipt, as_of_utc=args.as_of,
                             provenance_manifest_path=args.provenance_manifest,
                             provenance_manifest_sha256=args.provenance_manifest_sha256)
    except MappingError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError, KeyError, ImportError):
        print(json.dumps({"error": "UNREADABLE_OR_INVALID_SAVED_INPUT"}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["counts"]["rejected_rows"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
