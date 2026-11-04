"""Read-only accounting of two explicit archived contest proxy snapshots.

No provider imports, discovery, membership certification, or issuer inference.
See docs/CONTEST_UNIVERSE_DIFF.md for the bounded input contract.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path, PureWindowsPath
import re
import sys

import pyarrow as pa
import pyarrow.parquet as pq

MAX_ROWS = 50_000
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_PROJECTED_BYTES = 16 * 1024 * 1024
MAX_RECEIPT_BYTES = 64 * 1024
COLUMNS = ("market", "symbol", "membership", "screened_on")
MEMBERSHIP = "UNCONFIRMED_MEMBERSHIP"


class SnapshotRefused(ValueError):
    """An input failed validation; messages are fixed codes, never raw data."""


class SanitizedParser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps({"status": "REFUSED", "reason": "INVALID_ARGUMENTS"}))
        raise SystemExit(2)


def require(condition, code):
    if not condition:
        raise SnapshotRefused(code)


def digest(path):
    h = sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(64 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def iso_day(value):
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value),
            "INVALID_DATE")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise SnapshotRefused("INVALID_DATE") from None


def no_duplicate_fields(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_RECEIPT_FIELD")
        result[key] = value
    return result


def load_snapshot(parquet_path, receipt_path):
    parquet_path, receipt_path = Path(parquet_path), Path(receipt_path)
    for path in (parquet_path, receipt_path):
        require(not str(path).startswith(("\\\\", "//"))
                and ":" not in str(path)[2:]
                and not str(path.resolve()).startswith(("\\\\", "//")), "LOCAL_INPUT_REQUIRED")
    require(parquet_path.is_file() and receipt_path.is_file(), "INPUT_NOT_FILE")
    require(parquet_path.stat().st_size <= MAX_FILE_BYTES
            and receipt_path.stat().st_size <= MAX_RECEIPT_BYTES, "INPUT_LIMIT")
    before = (digest(parquet_path), digest(receipt_path))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"),
                         object_pairs_hook=no_duplicate_fields)
    require(isinstance(receipt, dict), "INVALID_RECEIPT")
    match = re.fullmatch(r"universe_(\d{4}-\d{2}-\d{2})\.parquet", parquet_path.name)
    require(match is not None, "INVALID_ARCHIVE_NAME")
    archive_day = iso_day(match[1])
    require(isinstance(receipt.get("path"), str)
            and PureWindowsPath(receipt["path"]).name == parquet_path.name,
            "RECEIPT_PATH_MISMATCH")
    stamp = receipt.get("written_utc")
    require(isinstance(stamp, str) and re.fullmatch(r"\d{8}T\d{6}Z", stamp),
            "INVALID_RECEIPT_CLOCK")
    try:
        written = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ")
    except ValueError:
        raise SnapshotRefused("INVALID_RECEIPT_CLOCK") from None
    require(written.date() == archive_day, "RECEIPT_DATE_MISMATCH")
    require(isinstance(receipt.get("membership"), str)
            and receipt["membership"].startswith(MEMBERSHIP), "INVALID_MEMBERSHIP")
    count = receipt.get("rows_after")
    require(type(count) is int and 0 <= count <= MAX_ROWS, "INVALID_ROW_COUNT")
    by_market = receipt.get("by_market")
    require(isinstance(by_market, dict) and isinstance(by_market.get("n"), dict),
            "INVALID_MARKET_COUNTS")
    expected = by_market["n"]
    require(all(isinstance(k, str) and type(v) is int and v >= 0
                for k, v in expected.items()), "INVALID_MARKET_COUNTS")
    # Zero-count markets mean absent coverage, never observed membership.
    expected = {k: v for k, v in expected.items() if v}
    require(sum(expected.values()) == count, "RECEIPT_COUNT_MISMATCH")
    keys = defaultdict(set)
    screened = Counter()
    with pq.ParquetFile(parquet_path, memory_map=False, pre_buffer=False) as source:
        schema = source.schema_arrow
        require(len(schema.names) == len(set(schema.names)), "INVALID_SCHEMA")
        require(all(c in schema.names and pa.types.is_string(schema.field(c).type)
                    for c in COLUMNS), "INVALID_SCHEMA")
        require(source.metadata.num_rows == count, "ROW_COUNT_MISMATCH")
        # Parquet leaf indexes differ from Arrow field indexes if an unrelated
        # nested column precedes these four fields.
        indexes = [i for i in range(len(source.schema))
                   if source.schema.column(i).path in COLUMNS]
        require(len(indexes) == len(COLUMNS), "INVALID_SCHEMA")
        projected = sum(source.metadata.row_group(g).column(i).total_uncompressed_size
                        for g in range(source.metadata.num_row_groups) for i in indexes)
        require(0 <= projected <= MAX_PROJECTED_BYTES, "PROJECTED_INPUT_LIMIT")
        seen = 0
        for batch in source.iter_batches(batch_size=512, columns=list(COLUMNS),
                                         use_threads=False):
            for row in batch.to_pylist():
                market, symbol = row["market"], row["symbol"]
                require(isinstance(market, str) and re.fullmatch(r"[A-Z]{2,8}", market),
                        "INVALID_MARKET")
                require(all(isinstance(v, str) and v.strip() and len(v) <= limit
                            and not any(ord(c) < 32 or ord(c) == 127 for c in v)
                            for v, limit in ((market, 32), (symbol, 128))), "INVALID_KEY")
                require(symbol not in keys[market], "DUPLICATE_KEY")
                require(row["membership"] == MEMBERSHIP, "INVALID_MEMBERSHIP")
                day = iso_day(row["screened_on"])
                require(day <= written.date(), "SCREENING_AFTER_RECEIPT")
                keys[market].add(symbol)  # Exact strings: no trim/case/issuer normalization.
                screened[day.isoformat()] += 1
                seen += 1
        require(seen == count, "ROW_COUNT_MISMATCH")
    require({k: len(v) for k, v in keys.items()} == expected, "MARKET_COUNT_MISMATCH")
    require(before == (digest(parquet_path), digest(receipt_path)), "INPUT_CHANGED")
    return keys, {
        "archive_date": archive_day.isoformat(), "receipt_written_utc": stamp,
        "parquet_sha256": before[0], "receipt_sha256": before[1], "rows": count,
        "membership_census": {MEMBERSHIP: count} if count else {},
        "screened_on_census": dict(sorted(screened.items())),
    }


def compare(old_parquet, old_receipt, new_parquet, new_receipt):
    old, old_meta = load_snapshot(old_parquet, old_receipt)
    new, new_meta = load_snapshot(new_parquet, new_receipt)
    require(old_meta["receipt_written_utc"] < new_meta["receipt_written_utc"],
            "NONINCREASING_RECEIPT_CLOCKS")
    markets = []
    for market in sorted(old.keys() | new.keys()):
        o, n = old.get(market, set()), new.get(market, set())
        common = len(o & n)
        coverage = "BOTH_PRESENT" if o and n else (
            "MISSING_NEW_MARKET" if o else "MISSING_OLD_MARKET")
        markets.append({
            "market": market, "coverage": coverage, "old": len(o), "new": len(n),
            "persisted": common, "old_only": len(o) - common, "new_only": len(n) - common,
            "observed_key_exits": len(o) - common if o and n else None,
            "observed_key_entries": len(n) - common if o and n else None,
            "old_persistence_pct": round(100 * common / len(o), 4) if o and n else None,
        })
    return {
        "status": "DESCRIPTIVE_ONLY", "unit": "exact (market,symbol)",
        "membership": MEMBERSHIP, "first_seen": "UNKNOWN", "pit_availability": "UNKNOWN",
        "caveat": "Archived proxy coverage only. Keys do not establish issuer identity; "
                  "renames, listing changes, screening and provider coverage cannot be separated.",
        "old_count": old_meta["rows"], "new_count": new_meta["rows"],
        **{k: sum(m[k] for m in markets) for k in ("persisted", "old_only", "new_only")},
        "by_market": markets, "inputs": {"old": old_meta, "new": new_meta},
    }


def main(argv=None):
    parser = SanitizedParser(description=__doc__)
    for side in ("old", "new"):
        parser.add_argument(f"--{side}-parquet", required=True, type=Path)
        parser.add_argument(f"--{side}-receipt", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = compare(args.old_parquet, args.old_receipt, args.new_parquet, args.new_receipt)
    except SnapshotRefused as exc:
        result = {"status": "REFUSED", "reason": str(exc)}
    except (OSError, ValueError, TypeError, KeyError, pa.ArrowException):
        result = {"status": "REFUSED", "reason": "UNREADABLE_INPUT"}
    print(json.dumps(result, sort_keys=True, ensure_ascii=True, allow_nan=False))
    return 2 if result["status"] == "REFUSED" else 0


if __name__ == "__main__":
    sys.exit(main())
