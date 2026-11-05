"""Offline, descriptive news/issuer audit. Never imports the digest or reader.

Inputs are the dated news_registry JSONL schema, archived contest parquet,
and optionally the existing edgar_8k/company_tickers.json SEC master and a safe
JSON array of held symbols (e.g. ["US:WU", "QCOM"]). stdout is sanitized JSON.
No source text, titles, URLs, private identity, or broker access is emitted.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit


MEMBERSHIP = "UNCONFIRMED_MEMBERSHIP"
ARCHIVE_DATE = "2026-11-01"
SYMBOL = re.compile(r"[A-Z0-9^][A-Z0-9.&^=\-]{0,23}\Z")
SOURCE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
MARKETS = {"CN", "EU", "HK", "ID", "IN", "JP", "KR", "TW", "US"}
SUFFIXES = {"inc", "incorporated", "corp", "corporation", "co", "company", "ltd",
            "limited", "plc", "holdings", "holding", "group", "sa", "ag"}
GENERIC = {"international", "national", "technology", "technologies", "financial",
           "energy", "global", "digital", "services", "industries", "resources"}


class Refused(Exception):
    """Only constant reason codes, never input-derived exception messages."""


@dataclass(frozen=True)
class Limits:
    rows: int = 10000
    seconds: float = 30.0
    files: int = 64
    line_bytes: int = 262144
    news_bytes: int = 32 * 1024 * 1024
    output_bytes: int = 16 * 1024 * 1024
    candidates: int = 32


class Budget:
    def __init__(self, limits: Limits):
        self.limits = limits
        self.deadline = time.monotonic() + limits.seconds

    def check(self):
        if time.monotonic() > self.deadline:
            raise Refused("TIME_LIMIT")


def clock(value):
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return t.astimezone(timezone.utc).isoformat() if t.tzinfo else None
    except ValueError:
        return None


def tokens(text):
    return tuple(re.findall(r"[^\W_]+", text.casefold()))


def bounded_json(path, max_bytes, budget):
    with path.open("rb") as fh:
        raw = fh.read(max_bytes + 1)
    budget.check()
    if len(raw) > max_bytes:
        raise Refused("METADATA_SIZE_LIMIT")
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


class Universe:
    def __init__(self, records):
        self.by_key = {}
        self.by_symbol = defaultdict(set)
        self.name_index = defaultdict(list)
        for row in records:
            market, symbol, name = row["market"], row["symbol"], row["name"]
            if (market not in MARKETS or not isinstance(symbol, str)
                    or not SYMBOL.fullmatch(symbol) or not isinstance(name, str)
                    or not name or len(name) > 512 or row["membership"] != MEMBERSHIP):
                raise Refused("UNIVERSE_SCHEMA")
            key = f"{market}:{symbol}"
            if key in self.by_key:
                raise Refused("DUPLICATE_UNIVERSE_KEY")
            self.by_key[key] = row
            self.by_symbol[symbol].add(key)
            full = tokens(name)
            core = full
            while core and core[-1] in SUFFIXES:
                core = core[:-1]
            for phrase in {full, core}:
                # Short/common single words require review; preserve the full
                # legal name as a possible witness (Apple Inc, for example).
                if (not phrase or (len(phrase) == 1 and
                                   (len(phrase[0]) < 8 or phrase[0] in GENERIC))):
                    continue
                self.name_index[phrase[0]].append((phrase, key))

    def title_keys(self, title, budget):
        words = tokens(title)
        found = set()
        for i, word in enumerate(words):
            for j, (phrase, key) in enumerate(self.name_index.get(word, ())):
                if j % 256 == 0:
                    budget.check()
                if words[i:i + len(phrase)] == phrase:
                    found.add(key)
        return found


def load_universe(path, budget, *, expected_rows=17261):
    # Parquet only; no pandas/config/service imports or implicit refresh.
    import pyarrow.parquet as pq

    if path.stat().st_size > 16 * 1024 * 1024:
        raise Refused("UNIVERSE_SIZE_LIMIT")
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
            budget.check()
    parquet = pq.ParquetFile(path)
    meta = parquet.metadata
    if meta.num_rows != expected_rows or meta.num_rows > 20000:
        raise Refused("UNIVERSE_ROW_COUNT")
    if sum(meta.row_group(i).total_byte_size for i in range(meta.num_row_groups)) > 64 * 1024 * 1024:
        raise Refused("UNIVERSE_EXPANDED_SIZE_LIMIT")
    required = ["market", "symbol", "name", "membership", "screened_on"]
    if not set(required) <= set(parquet.schema_arrow.names):
        raise Refused("UNIVERSE_SCHEMA")
    records = []
    for batch in parquet.iter_batches(batch_size=1024, columns=required):
        budget.check()
        for row in batch.to_pylist():
            screened = row.get("screened_on")
            if not isinstance(screened, str) or date.fromisoformat(screened) > date.fromisoformat(ARCHIVE_DATE):
                raise Refused("UNIVERSE_VINTAGE")
            records.append(row)
    universe = Universe(records)
    return universe, {"archive_date": ARCHIVE_DATE, "rows": len(records),
                      "sha256": digest.hexdigest(), "membership": MEMBERSHIP,
                      "membership_confirmed": False}


def load_sec_cache(path, budget):
    if path is None:
        return {}, {"provided": False}
    data, sha = bounded_json(path, 4 * 1024 * 1024, budget)
    if not isinstance(data, dict) or len(data) > 20000:
        raise Refused("SEC_CACHE_SCHEMA")
    # Prefer edgar_8k's complete SEC master; retain every share class. Also
    # support official/'s existing, potentially lossy single-symbol cache.
    cache_clock = None
    if set(data) == {"t", "map"}:
        cache_clock = clock(data["t"])
        mapping = data["map"]
        if not cache_clock or not isinstance(mapping, dict) or len(mapping) > 20000:
            raise Refused("SEC_CACHE_SCHEMA")
        pairs = list(mapping.items())
        basis = "SINGLE_SYMBOL_CACHE_INCOMPLETE_SHARE_CLASS_COVERAGE"
    else:
        pairs = []
        for row in data.values():
            if not isinstance(row, dict) or not {"cik_str", "ticker", "title"} <= row.keys():
                raise Refused("SEC_CACHE_SCHEMA")
            pairs.append((str(row["cik_str"]), row["ticker"]))
        basis = "SEC_MASTER_SNAPSHOT_NOT_ALIAS_HISTORY"
    out = defaultdict(set)
    for cik, symbol in pairs:
        if (not re.fullmatch(r"[0-9]{1,10}", cik) or int(cik) == 0
                or not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol)):
            raise Refused("SEC_CACHE_SCHEMA")
        normalized = str(int(cik))
        out[normalized].add(symbol)
    return dict(out), {"provided": True, "sha256": sha, "cache_utc": cache_clock,
                      "basis": basis, "point_in_time_certified": False}


def load_held(path, budget):
    if path is None:
        return None
    data, _ = bounded_json(path, 65536, budget)
    if not isinstance(data, list) or len(data) > 256:
        raise Refused("HELD_SAFE_LIST_SCHEMA")
    for entry in data:
        if not isinstance(entry, str):
            raise Refused("HELD_SAFE_LIST_SCHEMA")
        parts = entry.split(":")
        if (len(parts) not in (1, 2) or not SYMBOL.fullmatch(parts[-1])
                or (len(parts) == 2 and parts[0] not in MARKETS)):
            raise Refused("HELD_SAFE_LIST_SCHEMA")
    return set(data)


def sec_identity(row, source):
    """Tags are untrusted until they agree with an HTTPS SEC archive URL.

    The accession's first ten digits can be a filing agent, NOT issuer CIK.
    """
    if source not in {"sec_edgar_8k_ex99_body", "sec_edgar_8k_current_atom"}:
        return None
    tags = row.get("entity_tags", [])
    cik_tags = [t for t in tags if t.startswith("cik:")]
    acc_tags = [t for t in tags if t.startswith("accession:")]
    if (len(cik_tags) != 1 or len(acc_tags) != 1
            or not re.fullmatch(r"cik:[0-9]{1,10}", cik_tags[0])
            or not re.fullmatch(r"accession:[0-9]{10}-[0-9]{2}-[0-9]{6}", acc_tags[0])):
        return {"verified": False}
    ciks = {str(int(cik_tags[0][4:]))}
    accs = {acc_tags[0][10:]}
    url = urlsplit(row.get("url", ""))
    match = re.fullmatch(r"/Archives/edgar/data/([0-9]{1,10})/([0-9]{18})/[^/]+", url.path)
    if (url.scheme != "https" or url.hostname not in {"www.sec.gov", "sec.gov"}
            or url.username or url.password or url.port not in (None, 443) or not match):
        return {"verified": False}
    cik, compact = str(int(match[1])), match[2]
    accession = f"{compact[:10]}-{compact[10:12]}-{compact[12:]}"
    if ciks != {cik} or accs != {accession}:
        return {"verified": False}
    return {"verified": True, "cik": cik, "accession": accession,
            "document_id_sha256": hashlib.sha256(url.path.encode()).hexdigest()}


def audit_row(row, *, source, universe, sec_cache, held, budget):
    if (not isinstance(row, dict) or row.get("source") != source
            or not isinstance(row.get("title"), str) or len(row["title"]) > 4096
            or not isinstance(row.get("url", ""), str)
            or not isinstance(row.get("tickers", []), list)
            or not isinstance(row.get("entity_tags", []), list)
            or any(not isinstance(t, str) for t in row.get("entity_tags", []))):
        raise Refused("NEWS_SCHEMA")
    tags = row.get("tickers", [])
    if len(tags) > budget.limits.candidates or any(not isinstance(t, str) or not SYMBOL.fullmatch(t) for t in tags):
        raise Refused("TICKER_SCHEMA_OR_LIMIT")
    first, published = clock(row.get("first_seen_utc")), clock(row.get("published_utc"))
    clocks = []
    if first is None:
        clocks.append("FIRST_SEEN_UNKNOWN")
    if published is None:
        clocks.append("PUBLICATION_UNKNOWN")
    if first and published and published > first:
        clocks.append("PUBLICATION_AFTER_FIRST_SEEN")
    title = row["title"]
    title_keys = universe.title_keys(title, budget)
    # Existing tickers_named (if present) is deliberately NOT issuer evidence:
    # full-page text can contain sidebar stocks. Bodies are never inspected.
    symbols = set(tags)
    symbols.update(t for t in re.findall(r"(?<![\w.&^-])\$?([A-Z][A-Z0-9.&^-]{0,23})(?![\w.&^-])", title)
                   if t in universe.by_symbol)
    candidates = set(title_keys)
    for symbol in symbols:
        candidates.update(universe.by_symbol.get(symbol, {f"UNKNOWN:{symbol}"}))
    sec = sec_identity(row, source)
    sec_keys = set()
    sec_symbols = set()
    if sec and sec["verified"]:
        sec_symbols = sec_cache.get(sec["cik"], set())
        sec_keys = {f"US:{symbol}" for symbol in sec_symbols}
        candidates.update(sec_keys)
    if len(candidates) > budget.limits.candidates:
        raise Refused("CANDIDATE_LIMIT")
    url_path = urlsplit(row.get("url", "")).path.lower()
    recurring = bool(re.search(r"\banalyst\s+estimates\b", title, re.I)
                     or "analystestimates" in url_path or "analyst-estimates" in url_path)
    event_status = ("NO_EVENT_RECURRING_ESTIMATES" if recurring else
                    "FILING_EVENT_CANDIDATE" if sec and sec["verified"] else "EVENT_UNASSESSED")
    results = []
    for key in sorted(candidates):
        budget.check()
        market, symbol = key.split(":", 1)
        evidence, reason = "REVIEW_REQUIRED", "SYMBOL_ONLY_OR_UNVERIFIED_TAG"
        if key not in universe.by_key:
            evidence, reason = "REJECTED", "NOT_IN_ARCHIVED_PROXY_UNIVERSE"
        elif recurring:
            reason = "RECURRING_REFERENCE_NOT_EVENT"
        elif sec is not None:
            if key in sec_keys and len(sec_symbols) == 1:
                evidence, reason = "DIRECT", "SEC_URL_TAG_CIK_CACHE_AGREE"
            else:
                reason = "SEC_IDENTITY_UNRESOLVED_OR_CONFLICT"
        elif key in title_keys and len(title_keys) == 1 and len(universe.by_symbol[symbol]) == 1:
            evidence, reason = "DIRECT", "UNIQUE_TITLE_ISSUER_NAME_WITNESS"
        elif key in title_keys:
            reason = "MULTIPLE_ISSUERS_OR_MARKETS_IN_TITLE"
        elif symbol in tags:
            reason = "TAG_WITHOUT_TITLE_ISSUER_WITNESS"
        if (symbol == "SNOW" and key not in title_keys
                and re.search(r"\bsnow\b", title, re.I)
                and re.search(r"\b(weather|winter|storm|snowfall|forecast|blizzard)\b", title, re.I)):
            evidence, reason = "REJECTED", "WEATHER_SNOW_NOT_SNOWFLAKE"
        if evidence == "DIRECT" and (not first or "PUBLICATION_AFTER_FIRST_SEEN" in clocks):
            evidence, reason = "REVIEW_REQUIRED", "SOURCE_CLOCK_REVIEW"
        held_status = None if held is None else (key in held or symbol in held)
        results.append({"market": market, "symbol": symbol, "evidence_class": evidence,
                        "evidence_scope": "ISSUER_IDENTIFICATION_ONLY",
                        "security_event_relation": "REVIEW_REQUIRED",
                        "reason": reason, "tagged_in_source": symbol in tags,
                        "title_issuer_witness": key in title_keys,
                        "held_safe_list_match": held_status,
                        "held_match_basis": "SYMBOL_ONLY_MARKET_UNRESOLVED" if held and symbol in held
                        else "MARKET_SYMBOL" if held_status else None,
                        "membership": MEMBERSHIP if key in universe.by_key else None})
    return {"first_seen_utc": first, "published_utc": published, "clock_issues": clocks,
            "publication_basis": "CORPUS_SEC_ACCEPTED_REPORTED" if sec and sec["verified"]
            else "CORPUS_PUBLISHED_REPORTED", "event_status": event_status,
            "sec_identity": sec, "candidates": results}


def audit(corpus_root, day, universe, universe_meta, *, sec_cache=None, sec_meta=None,
          held=None, held_as_of=None, sources=(), limits=Limits(), budget=None):
    budget = budget or Budget(limits)
    paths = []
    # A bounded one-level inventory, not a recursive walk of the licensed store.
    with os.scandir(corpus_root) as entries:
        for n, entry in enumerate(entries, 1):
            budget.check()
            if n > 256:
                raise Refused("SOURCE_DIRECTORY_LIMIT")
            if SOURCE.fullmatch(entry.name) and entry.is_dir() and (not sources or entry.name in sources):
                path = Path(entry.path) / f"{day}.jsonl"
                if path.is_file():
                    if path.is_symlink() or entry.is_symlink():
                        raise Refused("SYMLINK_INPUT")
                    paths.append(path)
                    if len(paths) > limits.files:
                        raise Refused("FILE_LIMIT")
    if not paths or (sources and set(sources) != {p.parent.name for p in paths}):
        raise Refused("DATED_INPUT_MISSING")
    rows, files, groups = [], [], {}
    total_bytes = output_bytes = 0
    counts = Counter()
    for path in sorted(paths):
        budget.check()
        with path.open("rb") as fh:
            size = path.stat().st_size
            total_bytes += size
            if total_bytes > limits.news_bytes:
                raise Refused("NEWS_BYTE_LIMIT")
            digest = hashlib.sha256()
            remaining, line_no = size, 0
            while remaining:
                budget.check()
                raw = fh.readline(min(remaining, limits.line_bytes + 1))
                if not raw or not raw.endswith(b"\n"):
                    raise Refused("INCOMPLETE_OR_OVERSIZE_LINE")
                if len(raw) > limits.line_bytes:
                    raise Refused("LINE_SIZE_LIMIT")
                remaining -= len(raw)
                digest.update(raw)
                line_no += 1
                if len(rows) >= limits.rows:
                    raise Refused("ROW_LIMIT")
                row_hash = hashlib.sha256(raw).hexdigest()
                result = audit_row(json.loads(raw), source=path.parent.name, universe=universe,
                                   sec_cache=sec_cache or {}, held=held, budget=budget)
                result.update(source_file=f"{path.parent.name}/{day}.jsonl", source_line=line_no,
                              row_sha256=row_hash)
                cache_clock = (sec_meta or {}).get("cache_utc")
                result["mapping_known_at_first_seen"] = (
                    None if not cache_clock or not result["first_seen_utc"]
                    else cache_clock <= result["first_seen_utc"])
                sec = result["sec_identity"]
                group_key = f"SEC:{sec['cik']}:{sec['accession']}" if sec and sec["verified"] else f"ROW:{row_hash}"
                result["event_candidate_group"] = group_key
                group = groups.setdefault(group_key, {"group_key": group_key, "source_rows": 0,
                                                      "candidate_keys": set(), "document_ids": set()})
                group["source_rows"] += 1
                group["document_ids"].add(sec["document_id_sha256"] if sec and sec["verified"] else row_hash)
                for c in result["candidates"]:
                    counts[c["evidence_class"]] += 1
                    group["candidate_keys"].add(f"{c['market']}:{c['symbol']}")
                output_bytes += len(json.dumps(result))
                if output_bytes > limits.output_bytes:
                    raise Refused("OUTPUT_SIZE_LIMIT")
                rows.append(result)
            files.append({"source_file": f"{path.parent.name}/{day}.jsonl", "snapshot_bytes": size,
                          "snapshot_sha256": digest.hexdigest(), "rows": line_no})
    if not rows:
        raise Refused("EMPTY_DATED_INPUT")
    for group in groups.values():
        group["candidate_keys"] = sorted(group["candidate_keys"])
        group["document_ids"] = sorted(group["document_ids"])
        group["documents"] = len(group["document_ids"])
    held_coverage = []
    for entry in sorted(held or ()):
        keys = sorted({entry} & universe.by_key.keys() if ":" in entry
                      else universe.by_symbol.get(entry, ()))
        held_coverage.append({"safe_list_entry": entry, "proxy_keys": keys,
                              "status": "IN_PROXY" if keys else "OUTSIDE_PROXY_PRESERVED"})
    budget.check()
    return {"schema": "news_universe_audit_v1", "status": "AUDIT_COMPLETE",
            "audited_at_utc": datetime.now(timezone.utc).isoformat(),
            "scope": "LOCAL_DESCRIPTIVE_MAPPING_ONLY", "selected_date": day,
            "digest_ran": False, "decision_ran": False, "spend_units": 0,
            "universe": universe_meta, "sec_cache": sec_meta or {"provided": False},
            "held_safe_list_provided": held is not None,
            "held_as_of_utc": held_as_of, "held_coverage": held_coverage,
            "ownership_now": "UNKNOWN", "point_in_time_replay": False,
            "input_snapshot": "BOUNDED_FILE_PREFIX_NOT_ATOMIC_CORPUS_SNAPSHOT",
            "files": files, "rows": rows, "event_candidate_groups": list(groups.values()),
            "summary": {"rows": len(rows), "groups": len(groups),
                        "documents": sum(g["documents"] for g in groups.values()),
                        "evidence_counts": dict(counts)},
            "limits": vars(limits)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--date", required=True, help="Explicit local corpus date; never auto-selects 'latest'")
    parser.add_argument("--universe", type=Path, required=True, help="Archived 2026-11-01 parquet")
    parser.add_argument("--sec-tickers", type=Path, help="Local edgar_8k SEC master (preferred) or official cache")
    parser.add_argument("--held-safe-list", type=Path)
    parser.add_argument("--held-as-of", help="Optional supplied safe-list snapshot clock, with timezone")
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--max-rows", type=int, default=10000)
    parser.add_argument("--max-seconds", type=float, default=30)
    args = parser.parse_args(argv)
    try:
        if (date.fromisoformat(args.date).isoformat() != args.date
                or not 1 <= args.max_rows <= 10000 or not 0 < args.max_seconds <= 30
                or any(not SOURCE.fullmatch(s) for s in args.source)
                or args.universe.name != "universe_2026-11-01.parquet"
                or (args.held_as_of is not None and (not clock(args.held_as_of) or args.held_safe_list is None))):
            raise Refused("ARGUMENT_BOUNDS")
        limits = Limits(rows=args.max_rows, seconds=args.max_seconds)
        budget = Budget(limits)
        universe, meta = load_universe(args.universe, budget)
        sec_cache, sec_meta = load_sec_cache(args.sec_tickers, budget)
        held = load_held(args.held_safe_list, budget)
        result = audit(args.corpus_root, args.date, universe, meta, sec_cache=sec_cache,
                       sec_meta=sec_meta, held=held, sources=args.source,
                       held_as_of=clock(args.held_as_of),
                       limits=limits, budget=budget)
        encoded = json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
        if len(encoded) > limits.output_bytes:
            raise Refused("OUTPUT_SIZE_LIMIT")
        budget.check()
    except Refused as exc:
        result = {"status": "REFUSED", "reason": str(exc), "digest_ran": False,
                  "decision_ran": False, "spend_units": 0}
    except (OSError, ValueError, TypeError, KeyError, ImportError, OverflowError, RecursionError):
        result = {"status": "REFUSED", "reason": "INPUT_OR_DEPENDENCY_ERROR",
                  "digest_ran": False, "decision_ran": False, "spend_units": 0}
    if result["status"] != "AUDIT_COMPLETE":
        encoded = json.dumps(result, separators=(",", ":"))
    print(encoded)
    return 0 if result["status"] == "AUDIT_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
