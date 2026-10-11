import hashlib
import json

import pytest

from backend.services import beta_v1_context as context
from backend.services import beta_v1_policy as policy


def _bytes(value):
    return json.dumps(value, sort_keys=True).encode()


def _case():
    body = "Reported guidance changed."
    source = {"text": body, "url": "https://publisher.example/one", "published_utc": "2025-01-02T12:00:00Z",
              "first_seen_utc": "2025-01-02T13:00:00Z"}
    raw = _bytes(source)
    case = {"schema": "beta_factual_news_context/1", "source_hash": hashlib.sha256(raw).hexdigest(),
        "body_hash": hashlib.sha256(body.encode()).hexdigest(), "source_url": source["url"],
        "published_at": source["published_utc"], "source_first_seen_at": source["first_seen_utc"],
        "interpreted_at": "2025-01-02T14:00:00Z", "new_return_forecasts": [],
        "numeric_allocation_authority": False, "historical_replay_backdate_allowed": False,
        "claims": [{"kind": "GUIDANCE_REVISION", "role": "DESCRIPTIVE_REPORTED_FACT_ONLY",
                    "statement": "The source reports a guidance change.", "source_span_start": 0,
                    "source_span_end": len(body), "source_span_sha256": hashlib.sha256(body.encode()).hexdigest()}]}
    case_raw = _bytes(case)
    review = {"verdict": "PASS_DESCRIPTIVE_ONLY", "case_sha256": hashlib.sha256(case_raw).hexdigest(),
        "source_sha256": hashlib.sha256(raw).hexdigest(), "reviewed_claim_indices": [0],
        "reviewed_at": "2025-01-02T15:00:00Z", "available_at": "2025-01-02T15:00:00Z"}
    return case_raw, review, raw


def test_news_requires_whole_review_and_actual_availability():
    case, review, raw = _case()
    with pytest.raises(ValueError, match="unavailable"):
        context.admit_news(case, review, raw, asof="2025-01-02T14:30:00Z")
    with pytest.raises(ValueError, match="complete"):
        context.admit_news(case, {**review, "reviewed_claim_indices": []}, raw, asof="2025-01-02T16:00:00Z")
    accepted = context.admit_news(case, review, raw, asof="2025-01-02T16:00:00Z")
    assert accepted["numeric_return_authority"] is False
    assert accepted["source_first_seen_at"] != accepted["published_at"]


def test_witness_mutation_and_return_authority_refused():
    case, review, raw = _case()
    with pytest.raises(ValueError, match="complete"):
        context.admit_news(case, review, raw.replace(b"changed", b"growing"), asof="2025-01-02T16:00:00Z")
    changed = json.loads(case)
    changed["new_return_forecasts"] = [{"probability": .8}]
    changed_raw = _bytes(changed)
    review["case_sha256"] = hashlib.sha256(changed_raw).hexdigest()
    with pytest.raises(ValueError, match="authority"):
        context.admit_news(changed_raw, review, raw, asof="2025-01-02T16:00:00Z")


def test_analyst_context_refuses_future_duplicate_and_bad_numeric_features():
    features = {"schema": "beta_v1_current_descriptive_features/1", "asof_utc": "2025-01-02T15:00:00Z",
        "source_pins": {k:"a"*64 for k in ("projection","asset_metadata","prices","revision_flow","current_feature_builder")},
        "event_window": "bound original descriptor", "records": [{"ticker": "AAA", "revision_flow": {"net_raises": 2}}]}
    with pytest.raises(ValueError, match="unavailable"):
        context.analyst_context(_bytes(features), asof="2025-01-02T14:00:00Z", tickers=["AAA"])
    features["records"].append(features["records"][0].copy())
    with pytest.raises(ValueError, match="duplicate"):
        context.analyst_context(_bytes(features), qualification=_qualification(features), asof="2025-01-02T16:00:00Z", tickers=["AAA"])
    features["records"] = [{"ticker": "AAA", "revision_flow": {"net_raises": 2}, "fixed_revision_flow_score": float("nan")}]
    with pytest.raises(ValueError, match="invalid"):
        context.analyst_context(_bytes(features), qualification=_qualification(features), asof="2025-01-02T16:00:00Z", tickers=["AAA"])


def _qualification(features):
    return {"schema":"beta_v1_feature_qualification/1", "status":"PIT_FEATURE_BYTES_QUALIFIED",
        "whole_feature_sha256":hashlib.sha256(_bytes(features)).hexdigest(),
        "input_and_source_hashes":features["source_pins"], "source_job_sha256":features["source_pins"]["current_feature_builder"],
        "qualification_source_sha256":"b"*64, "source_ref":"fixture-only external projection qualification",
        "qualification_reason":"fixture witness, not real data", "feature_asof":features["asof_utc"],
        "first_seen_cutoff":features["asof_utc"], "qualified_at":"2025-01-02T15:30:00Z",
        "event_window":{"start_inclusive":"2024-10-04T00:00:00Z", "end_exclusive":"2025-01-02T00:00:00Z"},
        "bound_original_window_descriptor":features["event_window"]}


def test_analyst_whole_bytes_pins_and_window_require_external_qualification():
    features={"schema":"beta_v1_current_descriptive_features/1", "asof_utc":"2025-01-02T15:00:00Z",
        "source_pins":{k:"a"*64 for k in ("projection","asset_metadata","prices","revision_flow","current_feature_builder")},
        "event_window":"bound original descriptor", "records":[{"ticker":"AAA","revision_flow":{"net_raises":2}}]}
    q=_qualification(features)
    accepted=context.analyst_context(_bytes(features), qualification=q, asof="2025-01-02T16:00:00Z", tickers=["AAA"])
    assert accepted["records"][0]["revision_flow"]==features["records"][0]["revision_flow"]
    assert accepted["available_at"]=="2025-01-02T15:30:00+00:00"
    with pytest.raises(ValueError,match="qualification"):
        context.analyst_context(_bytes(features), asof="2025-01-02T16:00:00Z", tickers=["AAA"])
    for key,value in (("whole_feature_sha256","c"*64),("source_job_sha256","UNRECORDED"),
                      ("input_and_source_hashes",{"projection":"NOT_A_HASH"})):
        with pytest.raises(ValueError,match="qualification"):
            context.analyst_context(_bytes(features), qualification={**q,key:value}, asof="2025-01-02T16:00:00Z", tickers=["AAA"])
    for key,value in (("event_window",{"start_inclusive":"2024-10-04T00:00:00Z","end_exclusive":"2026-01-01T00:00:00Z"}),
                      ("first_seen_cutoff","2025-01-03T00:00:00Z"),("qualified_at","2025-01-03T00:00:00Z")):
        with pytest.raises(ValueError,match="PIT"):
            context.analyst_context(_bytes(features), qualification={**q,key:value}, asof="2025-01-02T16:00:00Z", tickers=["AAA"])


def test_real_planner_consumes_context_bound_forecast_without_forcing_holdings():
    news = context.admit_news(*_case(), asof="2025-01-02T16:00:00Z")
    definitions = {"numerical": {"source_family": "numerical", "model_version": "FIXTURE",
                                "prompt_version": "none", "correlation_group": "numerical"}}
    vintage = policy.fit([], qualifications={}, definitions=definitions, cutoff="2025-01-02T16:00:00Z",
                         task="expected_excess_return", horizon=21, objective_version="CONTEXT_FIXTURE_ONLY")
    numeric = policy.forecast(vintage, [], qualifications={}, asof="2025-01-02T16:00:00Z")
    with_news = context.attach(numeric, news=[news], analyst=None)
    without_news = context.attach(numeric, news=[news], analyst=None, variant="without_news_context")
    assert with_news["forecasts"] == without_news["forecasts"] == numeric["forecasts"]
    assert with_news["artifact_hash"] != without_news["artifact_hash"]
    plans = [policy.paper_plan_preview(view, instruments={}, equity=1, issuer_cap=.1, cash_floor=.7,
                                      max_names=10, round_trip_cost=.005) for view in (with_news, without_news)]
    assert plans[0]["forecast_artifact_hash"] == with_news["artifact_hash"]
    assert plans[1]["forecast_artifact_hash"] == without_news["artifact_hash"]
    assert all(plan["cash_weight"] == 1 for plan in plans)
