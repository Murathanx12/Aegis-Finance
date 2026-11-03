"""Real telemetry files with fake vendor responses; no network or credentials."""
import hashlib
import json
from types import SimpleNamespace as NS

import pytest

from backend.services import llm_analyzer as LA
from backend.services import llm_telemetry as LT
from backend.services import provider_budget as PB


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.options = []
        self.requests = []
        self.chat = NS(completions=NS(create=self.create))

    def with_options(self, **options):
        self.options.append(options)
        return self

    def create(self, **request):
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def response(text='{"fact":"public source witness"}', *, vendor_id="vendor-returned-id", model="deepseek-flash"):
    return NS(id=vendor_id, model=model, choices=[NS(message=NS(content=text))],
              usage=NS(prompt_tokens=20, completion_tokens=10, prompt_cache_hit_tokens=0))


@pytest.fixture
def setup(monkeypatch, tmp_path):
    # These existing receipts exercise the cloud contract; PC coverage is separate.
    monkeypatch.setattr(PB, "host_envelope_required", lambda: False)
    client = FakeClient(response())
    monkeypatch.setattr(LA, "_DEEPSEEK_API_KEY", "fixture-only-not-a-key")
    monkeypatch.setattr(LA, "_get_openai_client", lambda: client)
    monkeypatch.setattr(LA, "_spend_state", {"date": None, "count": 0, "breaker_until": 0,
                                          "breaker_reason": None, "cap_logged": False})
    monkeypatch.setenv(LT.LLM_TELEMETRY_PATH_ENV, str(tmp_path / "calls.jsonl"))
    return client, tmp_path


def call(**overrides):
    options = dict(purpose="hosted_context_fixture", max_tokens=100, model_override="deepseek-flash",
                   no_retry=True, non_thinking=True, production_budget=True,
                   evidence_mode=True, request_timeout_s=12)
    options.update(overrides)
    return LA.call_named("deepseek", "source system", "source user", **options)


def test_actual_returned_identity_wire_hashes_and_durable_row_are_bound(setup):
    client, root = setup
    result = call(validate=lambda text: json.loads(text).get("fact") is not None)
    assert result["ok"] and len(client.requests) == 1
    assert client.options == [{"max_retries": 0, "timeout": 12.0}]
    evidence = result["evidence"]
    assert evidence["provider_response_id"] == "vendor-returned-id"
    assert evidence["telemetry_call_id"] != evidence["provider_response_id"]
    assert evidence["served_model"] == result["served_model"] == "deepseek-flash"
    assert evidence["budget_scope"] == "process_local"
    assert LA._spend_state["count"] == 1
    persisted = json.loads(next(root.glob("calls_*.jsonl")).read_text(encoding="utf-8"))
    assert persisted == evidence["telemetry"]
    assert persisted["call_id"] == evidence["telemetry_call_id"]
    for role, field in (("system", "wire_system_sha256"), ("user", "user_prompt_sha256")):
        wire = next(m["content"] for m in client.requests[0]["messages"] if m["role"] == role)
        assert evidence[field] == hashlib.sha256(wire.encode()).hexdigest()
        assert persisted["meta"][field] == evidence[field]
    assert evidence["response_sha256"] == hashlib.sha256(result["text"].encode()).hexdigest()
    assert evidence["durably_persisted"] is True
    assert persisted["schema_version"] == LT.SCHEMA_VERSION
    assert "source system" not in json.dumps(persisted)


def test_actual_wire_reply_and_complete_request_hash_survive_normalization(setup):
    client, _ = setup
    client.response = response('  {"fact":"public source witness"}\n')
    result = call()
    evidence = result["evidence"]
    assert evidence["wire_response_sha256"] == hashlib.sha256(client.response.choices[0].message.content.encode()).hexdigest()
    assert evidence["wire_response_sha256"] != evidence["response_sha256"]
    assert evidence["response_normalization"] == "strip"
    request = json.dumps(client.requests[0], sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    assert evidence["sdk_arguments_sha256"] == hashlib.sha256(request.encode()).hexdigest()
    assert "wire_request_sha256" not in evidence and evidence["prepared_http_body_bound"] is False
    assert evidence["sdk_max_retries"] == 0 and evidence["request_timeout_s"] == 12


@pytest.mark.parametrize("overrides", [
    {"request_timeout_s": None}, {"request_timeout_s": float("nan")},
    {"request_timeout_s": 61}, {"request_timeout_s": True}, {"no_retry": False},
    {"non_thinking": False}, {"production_budget": False}, {"max_tokens": 901},
    {"max_tokens": True}, {"model_override": None},
])
def test_invalid_scope_refuses_before_budget_or_transport(setup, overrides):
    client, _ = setup
    assert call(**overrides)["status"] == "INVALID_EVIDENCE_SCOPE"
    assert not client.requests and not client.options and LA._spend_state["count"] == 0


@pytest.mark.parametrize("field,value", [("id", None), ("id", ""), ("model", None), ("model", 17)])
def test_missing_vendor_identity_never_becomes_generated_proof(setup, field, value):
    client, _ = setup
    setattr(client.response, field, value)
    result = call()
    assert result["status"] == "REFUSED_EVIDENCE_IDENTITY" and result["text"] is None
    assert "evidence" not in result and len(client.requests) == 1


@pytest.mark.parametrize("mode", ["write_failure", "fsync_failure", "suppressed", "missing_row"])
def test_failed_or_absent_telemetry_refuses_result(setup, monkeypatch, mode):
    client, _ = setup
    if mode == "suppressed":
        monkeypatch.delenv(LT.LLM_TELEMETRY_PATH_ENV)
    elif mode == "missing_row":
        monkeypatch.setattr(LT, "record_call_evidence", lambda **kw: None)
    else:
        def fail(*args, **kwargs):
            raise OSError("fixture-private-detail")
        monkeypatch.setattr(LT if mode == "write_failure" else LT.os,
                            "append" if mode == "write_failure" else "fsync", fail)
    result = call()
    assert result["status"] == "REFUSED_EVIDENCE_WRITE" and result["text"] is None
    assert "evidence" not in result and "fixture-private-detail" not in result["error"]
    assert len(client.requests) == 1


def test_schema_failure_still_records_spend_but_returns_no_admitted_evidence(setup):
    _, root = setup
    result = call(validate=lambda text: False)
    assert result["status"] == "REFUSED_EVIDENCE_REPLY" and result["text"] is None
    row = json.loads(next(root.glob("calls_*.jsonl")).read_text())
    assert row["schema_valid"] is False and row["meta"]["status"] == "REFUSED_REPLY"
    assert "evidence" not in result


def test_timeout_is_one_attempt_and_has_no_evidence(setup):
    client, root = setup
    client.response = TimeoutError("fixture-private-detail")
    result = call()
    assert result["status"] == "ERROR" and not result["ok"] and "evidence" not in result
    assert len(client.requests) == 1 and "fixture-private-detail" not in result["error"]
    assert "fixture-private-detail" not in next(root.glob("calls_*.jsonl")).read_text()


def test_daily_budget_still_refuses_before_request(setup, monkeypatch):
    client, _ = setup
    monkeypatch.setattr(LA, "_acquire_call_budget", lambda: False)
    assert call()["status"] == "BUDGET_REFUSED"
    assert not client.requests


def test_default_cloud_contract_has_no_timeout_clone_or_evidence_and_telemetry_stays_best_effort(setup, monkeypatch):
    client, _ = setup
    recorded = []
    monkeypatch.setattr(LT, "record_call", lambda **kw: recorded.append(kw))
    result = LA.call_named("deepseek", "source system", "source user", purpose="default_fixture")
    assert result["ok"] and "evidence" not in result and client.options == []
    assert len(recorded) == 1 and "meta" not in recorded[0]
    assert set(result) == {"provider", "model", "text", "ok", "status", "latency_s", "cost_usd",
                           "cost_status", "tokens_in", "tokens_out", "cached_tokens", "error",
                           "served_model", "n_429"}


def test_default_telemetry_swallows_write_error_but_evidence_does_not(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("fixture failure")
    monkeypatch.setattr(LT, "append", fail)
    assert LT.record_call(provider="deepseek", model="deepseek-flash", purpose="fixture") is None
    with pytest.raises(OSError):
        LT.record_call_evidence(provider="deepseek", model="deepseek-flash", purpose="fixture")


@pytest.mark.parametrize("status", [401, 402])
def test_evidence_billing_error_sanitizes_result_ledger_logs_and_breaker(setup, caplog, status):
    client, root = setup
    error = RuntimeError("FIXTURE_AUTHORIZATION_SECRET")
    error.status_code = status
    client.response = error
    result = call()
    assert result["status"] == "ERROR" and result["cost_usd"] is None
    for text in (json.dumps(result), next(root.glob("calls_*.jsonl")).read_text(),
                 caplog.text, str(LA.llm_usage()["breaker_reason"])):
        assert "FIXTURE_AUTHORIZATION_SECRET" not in text
    assert LA._spend_state["breaker_until"] > LA.time.time()
    assert call()["status"] == "BUDGET_REFUSED" and len(client.requests) == 1
    row = json.loads(next(root.glob("calls_*.jsonl")).read_text())
    assert row["cost_usd"] is None and row["meta"]["cost_status"] == "UNKNOWN"


@pytest.mark.parametrize("usage", [None, {}, {"prompt_tokens": 20},
    {"prompt_tokens": 20, "completion_tokens": "10", "prompt_cache_hit_tokens": 0},
    {"prompt_tokens": True, "completion_tokens": 10, "prompt_cache_hit_tokens": 0},
    {"prompt_tokens": 20, "completion_tokens": -1, "prompt_cache_hit_tokens": 0},
    {"prompt_tokens": 20, "completion_tokens": 10, "prompt_cache_hit_tokens": 21},
    {"prompt_tokens": 20, "completion_tokens": 10},
    {"prompt_tokens": 0, "completion_tokens": 0, "prompt_cache_hit_tokens": 0},
    {"prompt_tokens": 20, "completion_tokens": 0, "prompt_cache_hit_tokens": 0},
    {"prompt_tokens": 0, "completion_tokens": 10, "prompt_cache_hit_tokens": 0},
])
def test_unknown_usage_refuses_and_persists_unknown_attempted_cost(setup, usage):
    client, root = setup
    client.response.usage = usage
    result = call()
    assert result["status"] == "REFUSED_EVIDENCE_USAGE" and result["text"] is None
    assert result["cost_usd"] is None and result["cost_status"] == "UNKNOWN"
    assert "evidence" not in result and len(client.requests) == 1
    row = json.loads(next(root.glob("calls_*.jsonl")).read_text())
    assert row["cost_usd"] is None and row["meta"]["usage_status"] == "UNKNOWN"
    assert row["meta"]["status"] == "REFUSED_USAGE"


def test_unpriced_actual_served_model_stays_unknown_not_requested_rate(setup):
    client, root = setup
    client.response.model = "fixture-unpriced-model"
    result = call()
    assert result["ok"] and result["cost_usd"] is None and result["cost_status"] == "UNPRICED"
    row = json.loads(next(root.glob("calls_*.jsonl")).read_text())
    assert row["model"] == "fixture-unpriced-model" and row["cost_usd"] is None


def test_fully_cached_positive_input_and_positive_output_remain_measured(setup):
    client, root = setup
    client.response.usage = NS(prompt_tokens=20, completion_tokens=10, prompt_cache_hit_tokens=20)
    result = call()
    assert result["ok"] and result["tokens_in"] == 0 and result["cached_tokens"] == 20
    assert result["tokens_out"] == 10 and result["cost_usd"] > 0
    row = json.loads(next(root.glob("calls_*.jsonl")).read_text())
    assert row["cost_usd"] > 0 and row["meta"]["usage_status"] == "MEASURED"


def test_default_missing_usage_semantics_remain_compatible(setup):
    client, _ = setup
    client.response.usage = None
    result = LA.call_named("deepseek", "system", "user", purpose="default")
    assert result["ok"] and result["cost_usd"] == 0.0 and "evidence" not in result
