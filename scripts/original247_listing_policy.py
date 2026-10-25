"""Pinned offline calendar policy for exact frozen instruments; no listing certification."""
import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path


POLICY_PATH = Path(__file__).resolve().parents[1] / "docs/beta_v2/original247_listing_policy.json"
MANIFEST_SHA256 = "7e5003eb267eb05acf461aec5c5ac6877b1da3f1d2d322d8c9c13ee48c21e696"
IDENTITIES_SHA256 = "d6c336ad9fe2e1f799c9fd038ea07c0121166726c78167cb19beb8f33f1b2331"
BOOK_IDS_SHA256 = "a4aaa677a205d7cf05975a3cdab24cda624051c7995ed533dae38f70164e2ef8"
SCOPE = "FROZEN_INSTRUMENT_CALENDAR_ONLY"
SCHEMA = "original247_listing_policy/1"


class PolicyError(ValueError):
    """Explicit WAIT reason; never fall back to a suffix, stale policy or provider."""


def canonical_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _require(condition, reason):
    if not condition:
        raise PolicyError(reason)


def _object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _constant(_value):
    raise PolicyError("NONFINITE_JSON_VALUE")


def _keys(value, keys, reason):
    _require(isinstance(value, dict) and set(value) == set(keys.split()), reason)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _day(value):
    _require(isinstance(value, str), "INVALID_POLICY_DATE")
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise PolicyError("INVALID_POLICY_DATE") from exc
    _require(result.isoformat() == value, "INVALID_POLICY_DATE")
    return result


def _retrieved(value):
    _require(_text(value), "INVALID_RETRIEVAL_INTERVAL")
    stamp = datetime.fromisoformat(value.replace(" UTC", "+00:00").replace("Z", "+00:00"))
    _require(stamp.tzinfo is not None and stamp.utcoffset() is not None, "INVALID_RETRIEVAL_INTERVAL")
    return stamp.astimezone(timezone.utc)


def _load_policy(*, session, observed_at, path=None, expected_sha256=None,
                calendar_loader=None, exact_symbols=None):
    """Validate exact bytes, complete public evidence and finite calendar-policy scope.

    Optional path/pin/calendar injection is for isolated fixtures and reviewed
    callers. The production default never discovers another manifest or fetches.
    """
    target = POLICY_PATH if path is None else Path(path)
    pin = MANIFEST_SHA256 if expected_sha256 is None else expected_sha256
    try:
        raw = target.read_bytes()
    except OSError as exc:
        raise PolicyError("POLICY_FILE_UNAVAILABLE") from exc
    _require(len(raw) <= 256 * 1024 and _hash(pin) and sha256(raw) == pin, "POLICY_PIN_MISMATCH")
    try:
        policy = json.loads(raw.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant)
        _require(canonical_bytes(policy) == raw, "NONCANONICAL_POLICY_JSON")
    except RecursionError as exc:
        # The byte ceiling does not bound nesting. Refuse decoder/normalizer
        # depth exhaustion here; unrelated implementation recursion stays loud.
        raise PolicyError("POLICY_JSON_NESTING_LIMIT") from exc
    except (UnicodeError, ValueError, TypeError) as exc:
        if isinstance(exc, PolicyError):
            raise
        raise PolicyError("INVALID_POLICY_JSON") from exc
    _keys(policy, "schema policy_id scope claims cohort validity source_receipts sources instruments", "POLICY_SCHEMA")
    _require(policy["schema"] == SCHEMA and policy["scope"] == SCOPE and
             policy["policy_id"] == "original247_calendar_policy/1", "POLICY_SCOPE")
    _require(policy["claims"] == {"current_listing_status": False, "freeze_date_membership": False,
                                 "pit_signal": False, "vendor_delivery": False} and
             all(type(v) is bool for v in policy["claims"].values()), "POLICY_CLAIMS")
    cohort = policy["cohort"]
    _keys(cohort, "asof book_count book_ids_sha256 identity_count identities_sha256", "COHORT_SCHEMA")
    _require(cohort == {"asof": "2026-10-14", "book_count": 247, "book_ids_sha256": BOOK_IDS_SHA256,
                        "identity_count": 76, "identities_sha256": IDENTITIES_SHA256} and
             type(cohort["book_count"]) is int and type(cohort["identity_count"]) is int, "FROZEN_COHORT_BINDING")
    rows = policy["instruments"]
    _require(isinstance(rows, dict) and len(rows) == 76 and
             sha256(canonical_bytes(sorted(rows))) == IDENTITIES_SHA256, "FROZEN_IDENTITY_BINDING")
    if exact_symbols is not None:
        _require(set(exact_symbols) == set(rows), "FROZEN_IDENTITY_SET_MISMATCH")

    validity = policy["validity"]
    _keys(validity, "grade_session_from grade_session_through observation_date_from observation_date_through rationale", "VALIDITY_SCHEMA")
    start, end = _day(validity["grade_session_from"]), _day(validity["grade_session_through"])
    obs_start, obs_end = _day(validity["observation_date_from"]), _day(validity["observation_date_through"])
    _require(start == date(2026, 10, 15) and end == date(2027, 4, 19) and
             obs_start == date(2026, 10, 25) and obs_end == date(2027, 4, 20) and
             _text(validity["rationale"]), "INVALID_POLICY_VALIDITY")
    _require(type(session) is date and isinstance(observed_at, datetime) and
             observed_at.tzinfo is not None and observed_at.utcoffset() is not None, "POLICY_CLOCK_REQUIRED")
    today = observed_at.astimezone(timezone.utc).date()
    _require(start <= session <= end and obs_start <= today <= obs_end and session <= today, "POLICY_OUTSIDE_VALIDITY")

    receipts = policy["source_receipts"]
    _require(isinstance(receipts, list) and bool(receipts), "SOURCE_RECEIPTS_REQUIRED")
    for receipt in receipts:
        _keys(receipt, "name sha256 kind", "SOURCE_RECEIPT_SCHEMA")
        _require(_text(receipt["name"]) and _hash(receipt["sha256"]) and
                 receipt["kind"] == "STRUCTURAL_OFFLINE_HASH_RECEIPT", "INVALID_SOURCE_RECEIPT")
    _require(len(receipts) == 4 and {r["name"] for r in receipts} == {
        "C10_LISTING_WITNESS_INVENTORY.json", "PUBLIC_LISTING_WITNESSES.json",
        "PUBLIC_LISTING_WITNESSES_FOLLOWUP.json", "C10_MAPPING_REVIEW_PACKET.md"}, "SOURCE_RECEIPT_SET")
    sources = policy["sources"]
    _require(isinstance(sources, dict) and bool(sources), "PUBLIC_SOURCES_REQUIRED")
    for source in sources.values():
        _keys(source, "url kind excerpt excerpt_sha256 embedded_date retrieval_interval representation receipt_sha256", "WITNESS_SCHEMA")
        _require(source["kind"] in {"PUBLIC_BODY", "INHERITED_REVIEW"} and
                 _text(source["excerpt"]) and _hash(source["excerpt_sha256"]) and
                 sha256(source["excerpt"].encode("utf-8")) == source["excerpt_sha256"] and
                 (source["receipt_sha256"] is None or _hash(source["receipt_sha256"])) and
                 (source["embedded_date"] is None or _text(source["embedded_date"])) and
                 _text(source["representation"]) and isinstance(source["retrieval_interval"], list), "INVALID_WITNESS_RECEIPT")
        _require((_text(source["url"]) and source["url"].startswith("https://"))
                 if source["kind"] == "PUBLIC_BODY" else source["url"] is None, "WITNESS_URL_REQUIRED")
        if source["kind"] == "PUBLIC_BODY":
            interval = source["retrieval_interval"]
            _require(len(interval) == 2 and _retrieved(interval[0]) <= _retrieved(interval[1]),
                     "INVALID_RETRIEVAL_INTERVAL")
        else:
            _require(not source["retrieval_interval"] and _hash(source["receipt_sha256"]), "INHERITED_RECEIPT_REQUIRED")

    mapping = {}
    for symbol, row in rows.items():
        _keys(row, "native_symbol official_symbol issuer security_class class_uncertainty actual_exchange_mic mic_basis calendar_key calendar_semantics decision unresolved_reason crosswalk embedded_date uncertainty source_ids matches", "INSTRUMENT_SCHEMA")
        _require(row["native_symbol"] == symbol and all(_text(row[k]) for k in
                 ("official_symbol", "issuer", "security_class", "mic_basis", "calendar_semantics", "crosswalk")), "INSTRUMENT_IDENTITY")
        _require(row["decision"] in {"CALENDAR_ALLOWED", "UNRESOLVED"} and
                 isinstance(row["class_uncertainty"], str) and isinstance(row["uncertainty"], list) and
                 bool(row["uncertainty"]) and all(_text(x) for x in row["uncertainty"]) and
                 (row["embedded_date"] is None or _text(row["embedded_date"])) and
                 (row["actual_exchange_mic"] is None or re.fullmatch(r"[A-Z0-9]{4}", row["actual_exchange_mic"])), "INSTRUMENT_SCOPE")
        ids, matches = row["source_ids"], row["matches"]
        _require(isinstance(ids, list) and bool(ids) and len(set(ids)) == len(ids) and
                 all(s in sources for s in ids) and isinstance(matches, list) and bool(matches), "INSTRUMENT_WITNESSES")
        matched = set()
        for match in matches:
            _keys(match, "source_id text", "BODY_MATCH_SCHEMA")
            _require(match["source_id"] in ids and _text(match["text"]) and
                     match["text"] in sources[match["source_id"]]["excerpt"], "BODY_MATCH_REQUIRED")
            matched.add(match["source_id"])
        _require(matched == set(ids), "BODY_SOURCE_COVERAGE")
        if row["decision"] == "UNRESOLVED":
            _require(row["calendar_key"] is None and _text(row["unresolved_reason"]), "UNRESOLVED_DISPOSITION")
        else:
            _require(row["unresolved_reason"] is None and row["calendar_key"] in
                     {"XNYS", "XSTO", "XETR", "XOSL", "XTAI", "XKRX", "XTKS", "XASX"}, "CALENDAR_KEY_REQUIRED")
            mapping[symbol] = row["calendar_key"]
    try:
        if calendar_loader is None:
            import exchange_calendars as xc
            available = set(xc.get_calendar_names())
            _require(set(mapping.values()) <= available, "CALENDAR_UNAVAILABLE")
        else:
            for key in sorted(set(mapping.values())):
                _require(calendar_loader(key) is not None, "CALENDAR_UNAVAILABLE")
    except Exception as exc:
        if isinstance(exc, PolicyError):
            raise
        raise PolicyError("CALENDAR_UNAVAILABLE") from exc
    receipt = {"status": "VALID", "policy_id": policy["policy_id"], "scope": SCOPE,
               "manifest_sha256": pin, "identities_sha256": IDENTITIES_SHA256,
               "n_identities": 76, "n_allowed": len(mapping), "validity": validity,
               "source_receipts": receipts}
    return {"mapping": mapping, "receipt": receipt, "instruments": rows, "sources": sources}


def load_policy(**kwargs):
    """Normalize malformed input to an explicit policy refusal for consumers."""
    try:
        return _load_policy(**kwargs)
    except PolicyError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        raise PolicyError("MALFORMED_POLICY") from exc
