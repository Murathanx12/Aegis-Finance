"""Synthetic control of the one-call ASML binding; no source or provider IO."""
from datetime import datetime, timezone
import hashlib
import json

import pytest
from types import SimpleNamespace
import sys

from backend.services import asml_current_adapter as A
from backend.services import beta_v1_news_runtime as R
from backend.services import world_digest as WD


def _item():
    return WD.Item(item_id="synthetic", kind="article", source="wsj_news",
        url="https://www.wsj.com/synthetic", title="Synthetic fixture",
        text="A company reported synthetic earnings.",
        first_seen_utc="2026-10-13T10:00:00+00:00",
        published_utc="2026-10-13T09:00:00+00:00", tickers_named=[])


def _bind(monkeypatch):
    item = _item()
    monkeypatch.setattr(A, "preflight", lambda *a, **k: item)
    monkeypatch.setattr(A, "CACHE_KEY", WD.current_cache_key(item))
    monkeypatch.setattr(A, "SYSTEM_SHA256", hashlib.sha256(WD.CURRENT_EXTRACT_SYSTEM.encode()).hexdigest())
    monkeypatch.setattr(A, "PROMPT_SHA256", hashlib.sha256(WD._item_prompt(item)[0].encode()).hexdigest())
    return item


def test_one_returned_native_request_is_privately_captured(monkeypatch, tmp_path):
    _bind(monkeypatch)
    calls = []
    saved = []
    def transport(system, user, **kwargs):
        calls.append(kwargs)
        return {"ok": True, "status": "OK", "served_model": "deepseek-flash",
                "text": json.dumps({"event_type": "earnings", "novelty": "new_fact",
                                    "summary": "Synthetic earnings were reported.",
                                    "topic": "Synthetic result", "forward_claims": []}),
                "cost_usd": 0.001, "cost_status": "LISTED", "tokens_in": 50,
                "tokens_out": 20, "evidence": {"usage_status": "MEASURED",
                    "cost_status": "LISTED", "served_model": "deepseek-flash",
                    "durably_persisted": True}}
    result = A.capture(tmp_path / "unused", transport=transport,
        persist_native=lambda row: saved.append(row) or R.digest(row))
    assert len(calls) == 1 and calls[0] == {"timeout_s": 30,
        "purpose": "world_digest_extract_current", "max_tokens": 900}
    assert result["status"] == "PRIVATE_CAPTURE_FOR_INDEPENDENT_SEMANTIC_REVIEW"
    assert result["case"]["status"] == "REFUSED" and result["case"]["rows"] == []
    assert result["actual_spend_status"] == "MEASURED_LISTED_WITHIN_RESERVE"
    assert len(saved) == 1 and saved[0]["result"]["text"] == result["native_result"]["text"]
    assert (R.utc(result["source_eligibility_cutoff_utc"])
            < R.utc(result["extraction_completed_utc"]))
    assert result["native_return_sha256"] == R.digest(saved[0])
    assert result["forecast_authority"] is False and result["corpus_write"] is False


@pytest.mark.parametrize("served,cost", [("deepseek-chat", 0.001), ("deepseek-flash", None)])
def test_model_drift_refuses_and_unknown_cost_stays_unknown(monkeypatch, tmp_path, served, cost):
    _bind(monkeypatch)
    saved = []
    def transport(*args, **kwargs):
        return {"ok": True, "status": "OK", "served_model": served,
                "text": '{}', "cost_usd": cost, "tokens_in": 0, "tokens_out": 0}
    if served != "deepseek-flash":
        with pytest.raises(R.RuntimeRefused, match="MODEL"):
            A.capture(tmp_path / "unused", transport=transport,
                persist_native=lambda row: saved.append(row) or R.digest(row))
        assert len(saved) == 1 and saved[0]["result"]["served_model"] == served
        assert saved[0]["result"]["cost_usd"] == cost
    else:
        result = A.capture(tmp_path / "unused", transport=transport,
            persist_native=lambda row: saved.append(row) or R.digest(row))
        assert result["actual_spend_status"] == "UNKNOWN_OR_OVER_CAP"


def test_post_return_stop_refusal_preserves_native_evidence(monkeypatch, tmp_path):
    _bind(monkeypatch)
    returned = []
    saved = []
    def check():
        if returned and saved:
            raise R.RuntimeRefused("STOP_PRESENT")
    def transport(*args, **kwargs):
        returned.append(1)
        return {"ok": False, "status": "ERROR", "served_model": "deepseek-flash",
                "cost_usd": 0.002, "tokens_in": 100, "tokens_out": 30,
                "text": None, "cost_status": "LISTED"}
    with pytest.raises(R.RuntimeRefused, match="STOP_PRESENT"):
        A.capture(tmp_path / "unused", transport=transport, check=check,
            persist_native=lambda row: saved.append(row) or R.digest(row))
    assert len(returned) == len(saved) == 1
    assert saved[0]["result"]["cost_usd"] == 0.002


def test_private_native_return_redacts_credentials_but_preserves_usage():
    row = A.private_native_return({"text": "full returned content", "tokens_in": 17,
        "cost_usd": 0.001, "evidence": {"api_key": "synthetic-secret", "usage_status": "MEASURED"}})
    assert row["result"]["evidence"]["api_key"] == "[REDACTED]"
    assert row["result"]["text"] == "full returned content"
    assert row["result"]["tokens_in"] == 17


def test_transport_hook_retains_return_before_post_return_owner_refusal(monkeypatch):
    from backend import services
    returned = []
    checks = []
    class Client:
        _client = SimpleNamespace(_transport_for_url=lambda url: None)
        def with_options(self, **kwargs):
            return self
    client = Client()
    namespace = {"_get_openai_client": lambda: client}
    exec("def call_named(*args, **kwargs):\n return {'served_model':'deepseek-flash','cost_usd':0.002,'tokens_in':20,'tokens_out':10}", namespace)
    fake = SimpleNamespace(call_named=namespace["call_named"], _get_openai_client=lambda: client)
    monkeypatch.setitem(sys.modules, "backend.services.llm_analyzer", fake)
    monkeypatch.setattr(services, "llm_analyzer", fake, raising=False)
    pins = {k: "a" * 64 for k in R.SDK_FILES}
    monkeypatch.setattr(R, "sdk_source_pins", lambda **kwargs: pins)
    def owner_check():
        checks.append(1)
        if returned:
            raise R.RuntimeRefused("STOP_PRESENT")
    transport = R.deepseek_transport(authorized=True, sdk_pins=pins,
        owner_check=owner_check, on_native_return=lambda result: returned.append(result.copy()))
    with pytest.raises(R.RuntimeRefused, match="STOP_PRESENT"):
        transport("system", "user", timeout_s=30, purpose="fixture", max_tokens=900)
    assert len(returned) == 1 and returned[0]["cost_usd"] == 0.002
    assert len(checks) == 1


def test_outer_refusal_reports_actual_returned_usage_without_reinterpreting(tmp_path):
    from scripts import beta_v1_news_capture as CLI
    native = A.private_native_return({"served_model": "deepseek-chat", "tokens_in": 120,
        "tokens_out": 25, "cost_usd": 0.002, "cost_status": "LISTED",
        "evidence": {"usage_status": "MEASURED"}, "text": "raw synthetic result"})
    path = R.publish(tmp_path, "native_return.json", native)
    got = CLI.returned_refusal_evidence(tmp_path)
    assert got["native_return_file_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert got["tokens_in"] == 120 and got["tokens_out"] == 25
    assert got["cost_usd"] == 0.002 and got["provider_spend_status"] == "RETURNED_NATIVE_EVIDENCE_RETAINED"
    assert CLI.returned_refusal_evidence(tmp_path / "empty") == {}


def test_external_review_and_fresh_root_grant_required():
    now = datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc).isoformat()
    pins = {"synthetic": "a" * 64}
    review = {"independent": True, "verdict": "PASS_BOUNDED_ASML_CURRENT_CAPTURE_SOURCE",
              "source_pin_hash_domain": "FILE_BYTES_SHA256", "source_pins": pins,
              "acquisition_sha256": A.ACQUISITION_SHA256,
              "prompt_sha256": A.PROMPT_SHA256, "bundle_sha256": "b" * 64,
              "available_at": now}
    grant = {"schema": "asml_current_actual_root_grant/1", "owner": "ROOT",
        "stage": "asml-current", "provider": "deepseek", "development_capture_only": True,
        "prospective_accrual": False, "model_calls": 1,
        "acquisition_sha256": A.ACQUISITION_SHA256, "item_sha256": A.ITEM_SHA256,
        "prompt_sha256": A.PROMPT_SHA256, "bundle_sha256": "b" * 64,
        "nonce": "1" * 32, "issued_at": now, "source_pin_hash_domain": "FILE_BYTES_SHA256",
        "source_pins": pins, "source_review_sha256": R.digest(review),
        "limits": {"wall_seconds": 30, "rss_bytes": R.RSS_LIMIT,
                   "output_bytes": R.MAX_OUTPUT}}
    A.authorize(grant, now=now, review=review, actual_sources=pins)
    with pytest.raises(R.RuntimeRefused):
        A.authorize({**grant, "model_calls": 2}, now=now, review=review, actual_sources=pins)
    with pytest.raises(R.RuntimeRefused):
        A.authorize(grant, now=now, review={**review, "independent": False}, actual_sources=pins)
