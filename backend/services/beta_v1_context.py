"""Reviewed factual context consumed by the NEW inactive Beta forecast/plan.

Context changes provenance and explanations. It never manufactures a numeric
return, changes a frozen target, promotes a refused WD extraction, or trades.
"""
from __future__ import annotations

import hashlib
import json
import math
import re

import pandas as pd

from backend.services import beta_v1_policy as policy

VERSION = "beta_v1_context/1"
FACT_KINDS = frozenset({"OWNERSHIP_ASSET_TRANSFER", "OPERATING_CONTRACT_CHANGE",
                       "GUIDANCE_REVISION", "PRELIMINARY_OPERATING_OUTLOOK"})


def _clock(value):
    clock = pd.Timestamp(value)
    if pd.isna(clock) or clock.tzinfo is None:
        raise ValueError("exact timezone-aware context clock required")
    return clock.tz_convert("UTC")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _seal(value):
    return {**value, "artifact_hash": policy.digest(value)}


def _verify_context(value):
    if (value.get("schema") != VERSION or value.get("artifact_hash") !=
            policy.digest({k:v for k,v in value.items() if k != "artifact_hash"})):
        raise ValueError("invalid context schema/hash")


def admit_news(case_bytes: bytes, review: dict, source_bytes: bytes, *, asof: str) -> dict:
    """Bind the independently reviewed WHOLE factual case to untouched source."""
    if len(case_bytes) > 65536 or len(source_bytes) > 262144:
        raise ValueError("context byte cap")
    case = json.loads(case_bytes)
    source = json.loads(source_bytes)
    claims = case.get("claims")
    if (case.get("schema") != "beta_factual_news_context/1"
            or not isinstance(claims, list) or not 1 <= len(claims) <= 32
            or review.get("verdict") != "PASS_DESCRIPTIVE_ONLY"
            or review.get("case_sha256") != _sha(case_bytes)
            or review.get("source_sha256") != _sha(source_bytes)
            or review.get("reviewed_claim_indices") != list(range(len(claims)))
            or any(type(i) is not int for i in review.get("reviewed_claim_indices", []))):
        raise ValueError("complete independent factual-case review required")
    body = source.get("text")
    if (not isinstance(body, str) or case.get("source_hash") != _sha(source_bytes)
            or case.get("body_hash") != _sha(body.encode())
            or case.get("source_url") != source.get("url")
            or case.get("new_return_forecasts") != []
            or case.get("numeric_allocation_authority") is not False
            or case.get("historical_replay_backdate_allowed") is not False):
        raise ValueError("source/role/return authority mismatch")
    published = _clock(source.get("published_utc"))
    first_seen = _clock(source.get("first_seen_utc"))
    interpreted = _clock(case.get("interpreted_at"))
    reviewed = _clock(review.get("reviewed_at"))
    available = _clock(review.get("available_at"))
    if (case.get("published_at") != source.get("published_utc")
            or case.get("source_first_seen_at") != source.get("first_seen_utc")
            or not published <= first_seen <= interpreted <= reviewed <= available <= _clock(asof)):
        raise ValueError("source/interpretation/review unavailable by decision")
    for claim in claims:
        start, end = claim.get("source_span_start"), claim.get("source_span_end")
        if (claim.get("kind") not in FACT_KINDS or claim.get("role") != "DESCRIPTIVE_REPORTED_FACT_ONLY"
                or not isinstance(claim.get("statement"), str) or not claim["statement"].strip()
                or type(start) is not int or type(end) is not int or not 0 <= start < end <= len(body)
                or claim.get("source_span_sha256") != _sha(body[start:end].encode())):
            raise ValueError("unsupported or unbound factual claim")
    return _seal({"schema": VERSION, "role": "FACTUAL_CONTEXT_ONLY", "available_at": available.isoformat(),
        "source_hash": _sha(source_bytes), "case_hash": _sha(case_bytes), "review_hash": policy.digest(review),
        "source_url": case["source_url"], "published_at": published.isoformat(),
        "source_first_seen_at": first_seen.isoformat(), "claims": claims,
        "linked_entities": case.get("linked_entities", []), "numeric_return_authority": False,
        "old_contracts": "UNTOUCHED; this separate descriptive case does not admit old refused WD outputs"})


def analyst_context(feature_bytes: bytes, *, qualification: dict | None = None, asof: str, tickers: list[str]) -> dict:
    """Keep measured PIT revision features as context, with no return conversion."""
    if len(feature_bytes) > 16*1024*1024 or len(tickers) > 10000:
        raise ValueError("analyst context cap")
    features = json.loads(feature_bytes)
    observed = _clock(features.get("asof_utc"))
    if observed > _clock(asof) or features.get("schema") != "beta_v1_current_descriptive_features/1":
        raise ValueError("PIT feature snapshot unavailable")
    pins = features.get("source_pins")
    q = qualification
    required = {"projection", "asset_metadata", "prices", "revision_flow", "current_feature_builder"}
    def valid_hash(value):
        return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None
    if (not isinstance(pins, dict) or not required <= set(pins)
            or not all(valid_hash(pins[k]) for k in required)
            or not isinstance(q, dict) or q.get("schema") != "beta_v1_feature_qualification/1"
            or q.get("status") != "PIT_FEATURE_BYTES_QUALIFIED"
            or q.get("whole_feature_sha256") != _sha(feature_bytes)
            or q.get("input_and_source_hashes") != pins
            or not valid_hash(q.get("source_job_sha256"))
            or q.get("source_job_sha256") != pins["current_feature_builder"]
            or not valid_hash(q.get("qualification_source_sha256"))
            or not q.get("source_ref") or not q.get("qualification_reason")):
        raise ValueError("missing or mismatched whole-feature PIT qualification witness")
    q_available = _clock(q.get("qualified_at"))
    window = q.get("event_window")
    expected_end = observed.normalize()
    expected_start = expected_end - pd.Timedelta(days=90)
    if (not isinstance(window, dict) or _clock(q.get("feature_asof")) != observed
            or _clock(q.get("first_seen_cutoff")) != observed
            or _clock(window.get("start_inclusive")) != expected_start
            or _clock(window.get("end_exclusive")) != expected_end
            or not observed <= q_available <= _clock(asof)
            or features.get("event_window") != q.get("bound_original_window_descriptor")):
        raise ValueError("future/reversed/mismatched PIT event window or availability")
    admitted, seen = [], set()
    selected = set(tickers)
    for row in features.get("records", []):
        if row.get("ticker") not in selected or not isinstance(row.get("revision_flow"), dict):
            continue
        if row["ticker"] in seen:
            raise ValueError("ambiguous duplicate analyst context")
        seen.add(row["ticker"])
        for value in [*row["revision_flow"].values(), row.get("fixed_revision_flow_score"), row.get("net_raises_score")]:
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                raise ValueError("invalid analyst feature; no zero substitution")
        admitted.append({"ticker": row["ticker"], "revision_flow": row["revision_flow"],
            "fixed_revision_flow_score": row.get("fixed_revision_flow_score"),
            "net_raises_score": row.get("net_raises_score"), "role": "PIT_DESCRIPTIVE_NOT_EXPECTED_RETURN"})
    return _seal({"schema": VERSION, "role": "ANALYST_CONTEXT_ONLY", "available_at": q_available.isoformat(),
        "feature_asof": observed.isoformat(), "qualification_hash": policy.digest(q),
        "source_hash": _sha(feature_bytes), "projection_hash": features["source_pins"]["projection"],
        "event_window": window, "first_seen_cutoff": q["first_seen_cutoff"],
        "records": sorted(admitted, key=lambda r:r["ticker"]),
        "numeric_return_authority": False})


def attach(forecast: dict, *, news: list[dict], analyst: dict | None, variant: str = "with_context") -> dict:
    """The real planner consumes this sealed forecast and its context hash.

    Ablation changes consumed context and hashes. Numeric predictions remain
    unchanged because no calibrated return effect has been established.
    """
    policy.verify_artifact(forecast)
    if forecast.get("context_contract"):
        raise ValueError("context requires original numeric forecast, not reattachment")
    if variant not in ("with_context", "without_news_context", "without_analyst_context"):
        raise ValueError("unknown context ablation")
    if any(c.get("role") != "FACTUAL_CONTEXT_ONLY" for c in news) or (
            analyst is not None and analyst.get("role") != "ANALYST_CONTEXT_ONLY"):
        raise ValueError("wrong context role")
    for context in [*news, *([analyst] if analyst is not None else [])]:
        _verify_context(context)
        if (context.get("schema") != VERSION or context.get("numeric_return_authority") is not False
                or _clock(context.get("available_at")) > _clock(forecast["asof"])):
            raise ValueError("future or numeric-authority context rejected")
    consumed = {"news": [] if variant == "without_news_context" else news,
                "analyst": None if variant == "without_analyst_context" else analyst}
    result = {k:v for k,v in forecast.items() if k != "artifact_hash"}
    result.update(context_contract=VERSION, numeric_forecast_artifact_hash=forecast["artifact_hash"],
        consumed_context=consumed, consumed_context_hash=policy.digest(consumed), context_variant=variant,
        context_effect="DESCRIPTIVE_PROVENANCE_ONLY; numeric return and allocation weights unchanged")
    return _seal(result)
