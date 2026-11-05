"""Offline SEC EX99 issuer candidates; PRODUCT_EXPERIMENT, descriptive only.

No body interpretation, event typing, routing, or listing certification. A CIK
is an issuer identifier. Even a single current-master symbol plus a proxy match
does not witness the exact security discussed by an exhibit. Tags are discovery
context and are deliberately ignored. Snapshot availability is not alias validity.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping
from urllib.parse import urlsplit


SOURCE = "sec_edgar_8k_ex99_body"
MEMBERSHIP = "UNCONFIRMED_MEMBERSHIP"
_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)")
_CIK = re.compile(r"[0-9]{1,10}")
_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9.-]{0,31}")
_FILE = r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,254}"
_RAW = re.compile(rf"([0-9]{{10}}-[0-9]{{2}}-[0-9]{{6}}):({_FILE})")
_ARCHIVE = re.compile(rf"/Archives/edgar/data/([0-9]{{1,10}})/([0-9]{{18}})/({_FILE})")
_TITLE = re.compile(r"\(([0-9]{1,10})\)\s*\(Filer\)", re.IGNORECASE)


class MappingError(ValueError):
    """Fixed diagnostic codes only: never echo an untrusted row or body."""


def canonical_utc(value: object) -> datetime:
    """Accept explicit UTC ISO timestamps only (Z/+00:00, <=6 decimals)."""
    if not isinstance(value, str) or not _UTC.fullmatch(value):
        raise MappingError("INVALID_CANONICAL_UTC")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise MappingError("INVALID_CANONICAL_UTC") from None


def normalize_cik(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise MappingError("INVALID_CIK")
    value = str(value)
    if not _CIK.fullmatch(value) or int(value) == 0:
        raise MappingError("INVALID_CIK")
    return str(int(value))


def _symbol(value: object) -> str:
    if not isinstance(value, str) or not _SYMBOL.fullmatch(value):
        raise MappingError("INVALID_SYMBOL")
    return value


@dataclass(frozen=True)
class Snapshot:
    """Hash binds saved bytes; known_at is supplied evidence, never file mtime.

    None means availability UNKNOWN. No candidates are derived from a snapshot
    whose availability is unknown or later than the cutoff.
    """

    sha256: str
    known_at_utc: str | None

    def __post_init__(self):
        if not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise MappingError("INVALID_SNAPSHOT_SHA256")
        if self.known_at_utc is not None:
            canonical_utc(self.known_at_utc)

    def status(self, cutoff: datetime) -> str:
        if self.known_at_utc is None:
            return "UNKNOWN_AVAILABILITY"
        return ("AVAILABLE_AT_CUTOFF" if canonical_utc(self.known_at_utc) <= cutoff
                else "AFTER_CUTOFF")

    def describe(self, cutoff: datetime) -> dict:
        return {"sha256": self.sha256, "known_at_utc": self.known_at_utc,
                "availability": self.status(cutoff)}


def parse_document(row: Mapping) -> dict:
    """Reconcile URL/title CIK; accession comes ONLY from raw_id, not its CIK prefix."""
    if row.get("source") != SOURCE:
        raise MappingError("NOT_SEC_EX99_SOURCE")
    raw = row.get("raw_id")
    match = _RAW.fullmatch(raw) if isinstance(raw, str) else None
    if not match:
        raise MappingError("INVALID_RAW_ID")
    accession, filename = match.groups()
    url_cik = None
    url = row.get("url")
    if url:
        try:
            parts = urlsplit(url)
            archive = _ARCHIVE.fullmatch(parts.path)
            valid = (parts.scheme == "https" and parts.netloc in {"www.sec.gov", "sec.gov"}
                     and not parts.query and not parts.fragment and archive)
        except (ValueError, TypeError, AttributeError):
            valid = False
        if not valid:
            raise MappingError("INVALID_SEC_ARCHIVE_URL")
        url_cik, url_accession, url_filename = archive.groups()
        url_cik = normalize_cik(url_cik)
        if url_accession != accession.replace("-", "") or url_filename != filename:
            raise MappingError("URL_RAW_ID_CONFLICT")
    title = row.get("title", "")
    if not isinstance(title, str):
        raise MappingError("INVALID_TITLE")
    title_ciks = {normalize_cik(cik) for cik in _TITLE.findall(title)}
    if len(title_ciks) > 1:
        raise MappingError("AMBIGUOUS_TITLE_CIK")
    title_cik = next(iter(title_ciks), None)
    if url_cik and title_cik and url_cik != title_cik:
        raise MappingError("URL_TITLE_CIK_CONFLICT")
    cik = url_cik or title_cik
    if not cik:
        raise MappingError("NO_ISSUER_CIK_WITNESS")
    return {
        "issuer_cik": cik, "accession": accession, "filename": filename,
        "document_id": f"{cik}:{accession}:{filename}",
        "cik_witnesses": [name for name, value in
                          (("SEC_ARCHIVE_URL", url_cik), ("FILING_TITLE", title_cik)) if value],
    }


class CandidateMapper:
    """Invert the saved master and join exact US proxy symbols without aliases.

    No dot/dash substitution, ADR conversion, name guessing, or first-writer
    collision resolution. All master symbols and all matching listing keys survive.
    """

    def __init__(self, master_rows: Iterable[Mapping], proxy_rows: Iterable[Mapping],
                 *, master_snapshot: Snapshot, proxy_snapshot: Snapshot):
        self.master_snapshot = master_snapshot
        self.proxy_snapshot = proxy_snapshot
        self._symbols: dict[str, set[str]] = defaultdict(set)
        self._listings: dict[str, set[tuple[str, str | None, str]]] = defaultdict(set)
        for row in master_rows:
            self._symbols[normalize_cik(row.get("cik_str"))].add(_symbol(row.get("ticker")))
        if not self._symbols:
            raise MappingError("EMPTY_SEC_MASTER")
        count = 0
        for row in proxy_rows:
            count += 1
            market, symbol, exchange = row.get("market"), row.get("symbol"), row.get("exchange")
            if not isinstance(market, str) or not re.fullmatch(r"[A-Z]{2}", market):
                raise MappingError("INVALID_PROXY_MARKET")
            # Non-US symbol syntaxes are outside this SEC-symbol join's scope.
            if market != "US":
                continue
            symbol = _symbol(symbol)
            if exchange is not None and (not isinstance(exchange, str)
                    or not re.fullmatch(r"[A-Za-z0-9._-]{1,32}", exchange)):
                raise MappingError("INVALID_PROXY_EXCHANGE")
            # SEC tickers denote US-symbol candidates, never a same-string local listing.
            self._listings[symbol].add((market, exchange, symbol))
        if not count:
            raise MappingError("EMPTY_PROXY")

    def candidates(self, cik: str, cutoff: datetime) -> list[dict]:
        if self.master_snapshot.status(cutoff) != "AVAILABLE_AT_CUTOFF":
            return []
        result = []
        for symbol in sorted(self._symbols.get(cik, ())):
            keys = (self._listings.get(symbol, ())
                    if self.proxy_snapshot.status(cutoff) == "AVAILABLE_AT_CUTOFF" else ())
            listings = [{"market": market, "exchange": exchange, "symbol": symbol,
                         "membership": MEMBERSHIP, "listing_validity": "UNKNOWN"}
                        for market, exchange, symbol in sorted(keys, key=lambda k: (k[0], k[1] or "", k[2]))]
            result.append({"symbol": symbol, "listing_candidates": listings,
                           "identity_level": "ISSUER_CANDIDATE_ONLY"})
        return result

    def audit(self, rows: Iterable[Mapping], *, as_of_utc: str) -> dict:
        """Filter each document before parsing, deduplication, mapping or grouping.

        Duplicate document observations count once; the earliest eligible metadata
        wins. Later siblings/duplicates cannot enrich an earlier document. Filings
        and issuer groups are descriptive containers, never economic-event counts.
        """
        cutoff = canonical_utc(as_of_utc)
        documents: dict[str, dict] = {}
        rejected = []
        total = excluded = eligible = 0
        for index, row in enumerate(rows):
            total += 1
            if not isinstance(row, Mapping):
                rejected.append({"row_index": index, "reason": "INVALID_CORPUS_ROW"})
                continue
            try:
                seen = canonical_utc(row.get("first_seen_utc"))
                if seen > cutoff:
                    excluded += 1
                    continue
                doc = parse_document(row)
            except MappingError as exc:
                rejected.append({"row_index": index, "reason": str(exc)})
                continue
            eligible += 1
            doc["first_seen_utc"] = seen.isoformat()
            # This hashes allowlisted metadata, NOT the licensed body or whole input.
            doc["metadata_sha256"] = hashlib.sha256(
                json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            old = documents.get(doc["document_id"])
            if old is None or (seen, doc["metadata_sha256"]) < (
                    canonical_utc(old["first_seen_utc"]), old["metadata_sha256"]):
                documents[doc["document_id"]] = doc
        filings: dict[tuple[str, str], list[str]] = defaultdict(list)
        issuers: dict[str, list[tuple[str, str]]] = defaultdict(list)
        ordered = sorted(documents.values(), key=lambda d: d["document_id"])
        for doc in ordered:
            cik = doc["issuer_cik"]
            doc["candidates"] = self.candidates(cik, cutoff)
            doc["mapping_status"] = (
                "CANDIDATES" if doc["candidates"] else
                "CIK_NOT_IN_SAVED_MASTER" if self.master_snapshot.status(cutoff) == "AVAILABLE_AT_CUTOFF"
                else "MASTER_UNAVAILABLE_AT_CUTOFF")
            doc["listing_identity"] = "UNCONFIRMED_REQUIRES_LISTING_WITNESS"
            filings[(cik, doc["accession"])].append(doc["document_id"])
        for key in sorted(filings):
            issuers[key[0]].append(key)
        return {
            "schema_version": 1, "licence": "PRODUCT_EXPERIMENT",
            "as_of_utc": cutoff.isoformat(), "availability_clock": "first_seen_utc",
            "membership": MEMBERSHIP,
            "master_snapshot": {**self.master_snapshot.describe(cutoff),
                                "scope": "CURRENT_REGISTRANTS_NOT_DATED_ALIAS_HISTORY"},
            "proxy_snapshot": {**self.proxy_snapshot.describe(cutoff),
                               "scope": "CONTEST_PROXY_NOT_OFFICIAL_MEMBERSHIP"},
            "counts": {"input_rows": total, "excluded_after_cutoff": excluded,
                       "rejected_rows": len(rejected), "eligible_rows": eligible,
                       "duplicate_rows": eligible - len(ordered), "documents": len(ordered),
                       "filings": len(filings), "issuer_groups": len(issuers)},
            "documents": ordered,
            "filings": [{"issuer_cik": cik, "accession": accession, "document_ids": ids}
                        for (cik, accession), ids in sorted(filings.items())],
            "issuer_groups": [{"issuer_cik": cik, "document_count": sum(len(filings[k]) for k in keys),
                               "filing_count": len(keys), "candidates": self.candidates(cik, cutoff)}
                              for cik, keys in sorted(issuers.items())],
            "rejected": rejected,
            "limitations": [
                "Issuer candidates do not certify exact listings, historical aliases or validity.",
                "No listing witness admission or security routing is implemented.",
                "No event typing, ADR conversion, fund constituents or exposure inference.",
                "Snapshot known-at gates availability; it does not establish historical identity.",
                "Source published timestamps and discovery ticker tags are not used.",
            ],
        }
