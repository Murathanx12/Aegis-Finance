"""Read saved SEC EX99 inputs and print sanitized candidate JSON; no writes/calls.

PRODUCT_EXPERIMENT. Example (all paths explicitly supplied, no live defaults)::

    python -B -m scripts.news_cik_mapping_audit --corpus EX99.jsonl \
        --master company_tickers.json --master-meta company_tickers.meta.json \
        --proxy universe_2026-11-01.parquet --proxy-receipt RECEIPT.json \
        --as-of 2026-11-05T06:00:00Z

The compact proxy receipt clock is converted to canonical UTC. No mtime fallback.
Only market/symbol/exchange are read from parquet; no amounts or article bodies
are emitted. Exit 0 = completed audit (possibly empty), 1 = rejected corpus rows,
2 = invalid/unreadable input. Saved source bytes are hashed to bind provenance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from backend.services.news_cik_mapping import CandidateMapper, MappingError, Snapshot


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


def audit_files(*, corpus_paths: list[Path], master_path: Path, master_meta_path: Path,
                proxy_path: Path, proxy_receipt_path: Path, as_of_utc: str) -> dict:
    # pandas is optional for the pure in-memory module, required for saved parquet.
    import pandas as pd

    paths = [*corpus_paths, master_path, master_meta_path, proxy_path, proxy_receipt_path]
    before = [_fingerprint(p) for p in paths]
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
    mapper = CandidateMapper(
        master.values(), proxy.to_dict("records"),
        master_snapshot=Snapshot(before[len(corpus_paths)], meta.get("fetched_at_utc")),
        proxy_snapshot=Snapshot(before[-2], _receipt_clock(receipt.get("written_utc"))),
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
        "corpus": before[:len(corpus_paths)], "master": before[len(corpus_paths)],
        "master_meta": before[-3], "proxy": before[-2], "proxy_receipt": before[-1],
    }
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", action="append", required=True, type=Path)
    parser.add_argument("--master", required=True, type=Path)
    parser.add_argument("--master-meta", required=True, type=Path)
    parser.add_argument("--proxy", required=True, type=Path)
    parser.add_argument("--proxy-receipt", required=True, type=Path)
    parser.add_argument("--as-of", required=True)
    args = parser.parse_args(argv)
    try:
        result = audit_files(corpus_paths=args.corpus, master_path=args.master,
                             master_meta_path=args.master_meta, proxy_path=args.proxy,
                             proxy_receipt_path=args.proxy_receipt, as_of_utc=args.as_of)
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
