"""Inactive, pure adapter for injected saved SEC JSONL bytes.

Hashes bind bytes, not source authenticity or truth. The caller must independently
qualify the saved capture. No clock, filesystem, model, transport or ledger access.
Evidence text is untrusted source content, never instructions or a forecast.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
import re
from urllib.parse import urlsplit

SCHEMA = "saved-sec-forecast-input/1"
MAX_BYTES = 1024 * 1024
MAX_ROWS = 64


class _Refused(ValueError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _utc(value: str) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", value
    ):
        raise ValueError("explicit UTC timestamp required")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.utcoffset() != timedelta(0):
        raise ValueError("UTC required")
    return result


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(_):
    raise ValueError("nonfinite JSON")


def _evidence(row: dict, raw: bytes, ticker: str) -> tuple[dict, datetime, datetime]:
    if row.get("source") != "sec_edgar_8k_ex99_body" or row.get("tickers") != [ticker]:
        raise _Refused("UNSUPPORTED_SOURCE_OR_TICKER_BINDING")
    title = row.get("title")
    title_match = re.fullmatch(
        r"8-K - .+ \((\d{10})\) \(Filer\).+EX-99(?:\.1)?", title
    ) if isinstance(title, str) else None
    raw_id = row.get("raw_id")
    identity = re.fullmatch(
        r"(\d{10}-\d{2}-\d{6}):([A-Za-z0-9_-]+\.html?)", raw_id
    ) if isinstance(raw_id, str) else None
    url = row.get("url")
    if not isinstance(url, str) or not identity or not title_match:
        raise _Refused("SEC_IDENTITY_INVALID")
    accession, filename = identity.groups()
    cik = title_match[1]
    expected_url = (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
        f"{accession.replace('-', '')}/{filename}"
    )
    parsed = urlsplit(url)
    # Accession prefix is the login CIK (possibly an agent), not the issuer.
    # Keep title issuer == URL subject and the full accession/filename binding.
    # https://www.sec.gov/submit-filings/filer-support-resources/how-do-i-guides/understand-select-set-default-login-cik
    if url != expected_url or parsed.hostname != "www.sec.gov":
        raise _Refused("SEC_IDENTITY_INVALID")
    body = row.get("body")
    if not isinstance(body, str) or not body.strip():
        raise _Refused("BODY_MISSING")
    try:
        published = _utc(row.get("published_utc"))
        seen = _utc(row.get("first_seen_utc"))
    except ValueError:
        raise _Refused("SOURCE_CLOCK_INVALID") from None
    if published > seen:
        raise _Refused("SOURCE_CLOCK_ORDER_INVALID")
    evidence = {
        "accession": accession, "raw_id": raw_id, "url": url,
        "source": row["source"], "ticker": ticker, "title": title,
        "body": body, "published_utc": row["published_utc"],
        "first_seen_utc": row["first_seen_utc"], "row_sha256": _sha(raw),
        "source_row_utf8": raw.decode("utf-8"),
    }
    return evidence, published, seen


def build_saved_sec_input(event_bytes: bytes, *, ticker: str, cutoff_utc: str) -> dict:
    """Build one document's packet or explicit refusal from bounded JSONL bytes.

    Both publication and first-seen must be <= cutoff. Exact duplicate lines
    collapse; distinct eligible bytes for one raw_id conflict, and multiple
    eligible documents are ambiguous. Hashes include exact line terminators.
    No current freshness, semantic admission, event forecast or trading authority
    is conferred. A cutoff is a caller assertion, not a trusted observation clock.
    """
    try:
        if not isinstance(ticker, str) or not re.fullmatch(r"[A-Z]{1,5}(?:[.-][A-Z])?", ticker):
            raise _Refused("TICKER_INVALID")
        try:
            cutoff = _utc(cutoff_utc)
        except ValueError:
            raise _Refused("CUTOFF_INVALID") from None
        if type(event_bytes) is not bytes or not 0 < len(event_bytes) <= MAX_BYTES:
            raise _Refused("INPUT_BYTES_INVALID_OR_TOO_LARGE")
        lines = event_bytes.splitlines(keepends=True)
        if len(lines) > MAX_ROWS:
            raise _Refused("TOO_MANY_ROWS")
        eligible = {}
        matching = False
        for raw in lines:
            if not raw.strip():
                continue
            try:
                row = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                                 parse_constant=_constant)
                if not isinstance(row, dict):
                    raise ValueError("object required")
                tickers = row.get("tickers")
                if (not isinstance(tickers, list)
                        or any(not isinstance(t, str) for t in tickers)):
                    raise ValueError("ticker list required")
            except (ValueError, RecursionError):
                raise _Refused("ROW_JSON_INVALID") from None
            if ticker not in tickers:
                continue
            matching = True
            evidence, published, seen = _evidence(row, raw, ticker)
            if published > cutoff or seen > cutoff:
                continue
            key = evidence["raw_id"]
            if key in eligible and eligible[key]["row_sha256"] != evidence["row_sha256"]:
                raise _Refused("CONFLICTING_EVENT_BYTES")
            eligible[key] = evidence
        if not eligible:
            raise _Refused("NOT_AVAILABLE_AT_CUTOFF" if matching else "NO_MATCHING_EVENT")
        if len(eligible) != 1:
            raise _Refused("AMBIGUOUS_EVENT")
        packet = {
            "schema": SCHEMA, "status": "EVIDENCE_ONLY", "ticker": ticker,
            "cutoff_utc": cutoff.isoformat(), "evidence": next(iter(eligible.values())),
            "qualification": "Injected saved bytes only; authenticity and semantics unverified.",
            "forecast_status": "NOT_GENERATED", "runtime_authority": "NONE",
        }
        return {**packet, "packet_sha256": _sha(_canonical(packet))}
    except _Refused as exc:
        return {"schema": SCHEMA, "status": "REFUSED", "reason": str(exc)}
    except (ValueError, TypeError, OverflowError, RecursionError):
        return {"schema": SCHEMA, "status": "REFUSED", "reason": "ROW_INVALID"}


def verify_saved_sec_input(packet: dict, event_bytes: bytes, *, ticker: str,
                           cutoff_utc: str) -> bool:
    """Rebuild against injected bytes; mutations or changed context invalidate.

    This is integrity comparison, not authentication: anyone can recompute an
    unkeyed hash. Retain the original packet/hash independently for later checks.
    Refusal artifacts are never verified as qualified evidence.
    """
    rebuilt = build_saved_sec_input(event_bytes, ticker=ticker, cutoff_utc=cutoff_utc)
    return rebuilt.get("status") == "EVIDENCE_ONLY" and packet == rebuilt
