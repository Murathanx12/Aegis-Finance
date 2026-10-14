"""One reviewed, private ASML issuer interpretation through the bounded owner.

This module neither discovers a provider nor writes a forecast or native cache.
The CLI owner supplies an already authorized bounded DeepSeek transport.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import math
from pathlib import Path
import time

from backend.services import beta_v1_news_runtime as R
from backend.services import news_source_validation as NV
from backend.services import world_digest as WD
from backend.services.issuer_ir_current_case import build_item


ACQUISITION_SHA256 = "d2da519d62c71929bce31df9db5f039d57c2d481d6b1ecb2755e44c4dd51827e"
ITEM_SHA256 = "db53f7f319e5b1e7e314e2a09b961b72e0f9ea40a4c02957c513de73fba2ae33"
CACHE_KEY = "a0430296645ef639017d63a51775d02beb5576522974a9dd8c9332f9231ccd87"
SOURCE_SHA256 = "18d7248819cfad3c02f6a20b64f25f9ca7cae0d11b313684e25a9c622deafdfb"
PROMPT_SHA256 = "6b86096c408364fa5498f81dacb068eb923f20706122a969d5b0bc43d4bf9291"
SYSTEM_SHA256 = "fa6df1221b9327bd47e768068f9eba4c7dba425304641bc104bf47b831e91972"
MODEL = "deepseek-flash"
PURPOSE = "world_digest_extract_current"
MAX_TOKENS = 900
STAGE_CAP_USD = 0.003


def authorize(grant: dict, *, now: str, review: dict, actual_sources: dict) -> None:
    """Fresh external ROOT grant for one named ASML operation, not Beta authority."""
    clock = R.utc(now)
    R.quiet_admission(clock)
    nonce = grant.get("nonce")
    if (not isinstance(nonce, str) or len(nonce) != 32
            or any(c not in "0123456789abcdef" for c in nonce)):
        raise R.RuntimeRefused("ASML_ROOT_NONCE_UNAVAILABLE")
    if (grant.get("schema") != "asml_current_actual_root_grant/1"
            or grant.get("owner") != "ROOT"
            or grant.get("stage") != "asml-current"
            or grant.get("provider") != "deepseek"
            or grant.get("development_capture_only") is not True
            or grant.get("prospective_accrual") is not False
            or grant.get("model_calls") != 1
            or grant.get("acquisition_sha256") != ACQUISITION_SHA256
            or grant.get("item_sha256") != ITEM_SHA256
            or grant.get("prompt_sha256") != PROMPT_SHA256
            or not isinstance(grant.get("bundle_sha256"), str)
            or len(grant["bundle_sha256"]) != 64
            or grant.get("bundle_sha256") != review.get("bundle_sha256")
            or grant.get("source_pin_hash_domain") != "FILE_BYTES_SHA256"
            or grant.get("source_pins") != actual_sources
            or grant.get("source_review_sha256") != R.digest(review)
            or grant.get("limits") != {"wall_seconds": 30, "rss_bytes": R.RSS_LIMIT,
                                      "output_bytes": R.MAX_OUTPUT}
            or review.get("independent") is not True
            or review.get("verdict") != "PASS_BOUNDED_ASML_CURRENT_CAPTURE_SOURCE"
            or review.get("source_pin_hash_domain") != "FILE_BYTES_SHA256"
            or review.get("source_pins") != actual_sources
            or review.get("acquisition_sha256") != ACQUISITION_SHA256
            or review.get("prompt_sha256") != PROMPT_SHA256
            or R.utc(review.get("available_at")) > clock
            or not R.utc(grant.get("issued_at")) <= clock <= R.utc(grant.get("issued_at")) + timedelta(seconds=600)):
        raise R.RuntimeRefused("ASML_EXACT_CAPTURE_AUTHORITY_UNAVAILABLE")


def preflight(acquisition_path: Path, *, check=lambda: None):
    """Rebuild the original held item and pin every model-visible byte."""
    check()
    raw = R.read_bound(acquisition_path, expected_sha256=ACQUISITION_SHA256,
                       check=check, maximum=65536)
    if len(raw) == 0:
        raise R.RuntimeRefused("ASML_ACQUISITION_UNAVAILABLE")
    item = build_item(acquisition_path)
    prompt, removed = WD._item_prompt(item)
    if (NV.content_sha256(vars(item)) != ITEM_SHA256
            or WD.current_cache_key(item) != CACHE_KEY
            or NV.content_sha256(item.title + "\n" + item.text) != SOURCE_SHA256
            or hashlib.sha256(prompt.encode()).hexdigest() != PROMPT_SHA256
            or hashlib.sha256(WD.CURRENT_EXTRACT_SYSTEM.encode()).hexdigest() != SYSTEM_SHA256
            or removed != 0 or len(prompt) != 3733):
        raise R.RuntimeRefused("ASML_MODEL_INPUT_DRIFT")
    check()
    return item


def validate_bundle(bundle: dict, grant: dict) -> Path:
    if (set(bundle) != {"schema", "acquisition_path", "acquisition_sha256"}
            or bundle.get("schema") != "asml_current_capture_bundle/1"
            or bundle.get("acquisition_sha256") != ACQUISITION_SHA256
            or bundle.get("acquisition_sha256") != grant.get("acquisition_sha256")):
        raise R.RuntimeRefused("ASML_BUNDLE_UNAVAILABLE")
    path = Path(bundle["acquisition_path"])
    if path.name != "acquisition.json" or path.is_symlink() or not path.is_file():
        raise R.RuntimeRefused("ASML_ACQUISITION_PATH_UNAVAILABLE")
    return path


def private_native_return(result: dict) -> dict:
    """Keep the complete JSON return, redacting only credential-bearing keys."""
    blocked = {"authorization", "proxy_authorization", "api_key", "apikey",
               "secret", "password", "cookie", "set_cookie", "access_token"}
    def scrub(value):
        if isinstance(value, dict):
            return {k: "[REDACTED]" if k.lower().replace("-", "_") in blocked
                    else scrub(v) for k, v in value.items()}
        if isinstance(value, list):
            return [scrub(v) for v in value]
        return value
    safe = scrub(result)
    raw = R.encode(safe)
    if len(raw) > R.RESPONSE_BYTES * 2:
        raise R.RuntimeRefused("ASML_NATIVE_RETURN_SIZE_UNAVAILABLE")
    return {"schema": "asml_private_native_return/1", "result": safe,
            "captured_utc": datetime.now(timezone.utc).isoformat(),
            "cost_observation": "RETURNED_RESULT_NOT_AN_INVOICE"}


def capture(acquisition_path: Path, *, transport, persist_native, check=lambda: None) -> dict:
    """One transport invocation; durably retain its result before any post-check."""
    item = preflight(acquisition_path, check=check)
    native = []
    native_receipt = []

    def llm(system, user, *, purpose, max_tokens):
        check()
        if native or purpose != PURPOSE or max_tokens != MAX_TOKENS:
            raise R.RuntimeRefused("ASML_EXACT_ONE_REQUEST_UNAVAILABLE")
        if (hashlib.sha256(system.encode()).hexdigest() != SYSTEM_SHA256
                or hashlib.sha256(user.encode()).hexdigest() != PROMPT_SHA256):
            raise R.RuntimeRefused("ASML_MODEL_INPUT_DRIFT")
        native.append({"status": "STARTED_NO_RETURNED_USAGE"})
        result = transport(system, user, timeout_s=30, purpose=purpose,
                           max_tokens=max_tokens)
        if not isinstance(result, dict):
            raise R.RuntimeRefused("ASML_NATIVE_RESULT_UNAVAILABLE")
        native[0] = result
        native_receipt.append(persist_native(private_native_return(result)))
        check()
        if result.get("served_model") != MODEL:
            raise R.RuntimeRefused("ASML_NATIVE_MODEL_UNAVAILABLE")
        return result

    meter = WD.Meter(STAGE_CAP_USD, llm=llm)
    source_cutoff = datetime.now(timezone.utc).isoformat()
    result = WD.extract_current_item(
        item, meter, cache={}, cutoff_utc=source_cutoff,
        stage_cap=STAGE_CAP_USD, semantic_review=None,
        contract_version=WD.CURRENT_EXTRACT_VERSION)
    completed = datetime.now(timezone.utc).isoformat()
    wait_started = time.monotonic()
    while R.utc(completed) <= R.utc(source_cutoff) and time.monotonic() - wait_started < 0.01:
        time.sleep(0.001)
        completed = datetime.now(timezone.utc).isoformat()
    # Re-run only the pure cache-hit admission at a real post-call cutoff.
    # A reviewer can later supply a full-row semantic review to this capture;
    # there is no second provider request or native cache write here.
    postcall = WD.extract_current_item(
        item, meter, cache={CACHE_KEY: result["capture"]}, cutoff_utc=completed,
        stage_cap=STAGE_CAP_USD, semantic_review=None,
        contract_version=WD.CURRENT_EXTRACT_VERSION)
    check()
    if len(native) != 1 or len(native_receipt) != 1:
        raise R.RuntimeRefused("ASML_EXACT_ONE_REQUEST_UNAVAILABLE")
    actual = native[0]
    cost = actual.get("cost_usd")
    evidence = actual.get("evidence") or {}
    spend_status = ("MEASURED_LISTED_WITHIN_RESERVE" if type(cost) in (int, float)
                    and math.isfinite(cost) and 0 <= cost <= STAGE_CAP_USD
                    and actual.get("cost_status") == "LISTED"
                    and evidence.get("usage_status") == "MEASURED"
                    and evidence.get("cost_status") == "LISTED"
                    and evidence.get("served_model") == MODEL
                    and evidence.get("durably_persisted") is True
                    else "UNKNOWN_OR_OVER_CAP")
    if (result.get("cache_hit") is not False or result.get("status") != "REFUSED"
            or result.get("capture", {}).get("cache_key") != CACHE_KEY
            or postcall.get("cache_hit") is not True
            or postcall.get("status") != "REFUSED"
            or postcall.get("capture") != result.get("capture")
            or meter.calls != 1):
        raise R.RuntimeRefused("ASML_EXPERIMENTAL_CAPTURE_UNAVAILABLE")
    # The pre-call clock establishes source availability. Only the separately
    # observed post-call clock may be used for later cache-hit admission.
    if R.utc(completed) <= R.utc(source_cutoff):
        raise R.RuntimeRefused("ASML_CAPTURE_CLOCK_UNAVAILABLE")
    return {"status": "PRIVATE_CAPTURE_FOR_INDEPENDENT_SEMANTIC_REVIEW",
            "case": postcall, "native_result": actual, "meter": meter.summary(),
            "native_return_sha256": native_receipt[0],
            "source_eligibility_cutoff_utc": source_cutoff,
            "extraction_completed_utc": completed,
            "later_semantic_review_cutoff_utc": None,
            "actual_spend_status": spend_status,
            "forecast_authority": False, "corpus_write": False}
