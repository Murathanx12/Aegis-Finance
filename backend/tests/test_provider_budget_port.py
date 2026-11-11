"""Host budget port: fake transports and isolated envelopes only."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from types import SimpleNamespace as NS

import pytest

from backend.services import provider_budget as PB
from backend.services import llm_analyzer as LA
from backend.services import llm_telemetry as LT


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    p = tmp_path / "envelope.json"
    monkeypatch.setenv("AEGIS_DEEPSEEK_BUDGET_PATH", str(p))
    monkeypatch.setenv(LT.LLM_TELEMETRY_PATH_ENV, str(tmp_path / "calls.jsonl"))
    monkeypatch.delenv("AEGIS_DEEPSEEK_HOST_ENVELOPE", raising=False)
    monkeypatch.setattr(LA, "_spend_state", {"date": None, "count": 0, "breaker_until": 0,
                                          "breaker_reason": None, "cap_logged": False})
    return p


def envelope(p, cap=1):
    # Synthetic contract, never initialize/reset the host's actual envelope.
    p.write_text(json.dumps({"schema": PB.SCHEMA, "session_id": "test-only",
        "cap_units": PB._units(cap), "opening_units": 0, "opening_evidence": "fixture",
        "calls": {}, "daily": {}, "blocked": None}), encoding="utf-8")


def reply(model="deepseek-flash", usage=True):
    return NS(id="fake-vendor-response", model=model,
              choices=[NS(message=NS(content="A fixture answer."))],
              usage=NS(prompt_tokens=20, completion_tokens=10, prompt_cache_hit_tokens=0) if usage else None)


class Client:
    base_url = "https://api.deepseek.com/v1/"

    def __init__(self, result=None):
        self.result = result or reply()
        self.options = []
        self.requests = []
        self.chat = NS(completions=NS(create=self.create))

    def with_options(self, **kw):
        self.options.append(kw)
        return self

    def create(self, **kw):
        self.requests.append(kw)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def configure(monkeypatch, client, required=True):
    monkeypatch.setattr(PB, "host_envelope_required", lambda: required)
    monkeypatch.setattr(LA, "_get_openai_client", lambda: client)
    monkeypatch.setattr(LA, "_DEEPSEEK_API_KEY", "fixture-only")
    monkeypatch.setattr(LA, "_get_provider", lambda: "deepseek")


def call(**kw):
    return LA.call_named("deepseek", "system", "user", purpose="port-test", max_tokens=100, **kw)


def reserve(**kw):
    return PB.reserve("system", "user", 100, model="deepseek-chat",
                      base_url="https://api.deepseek.com", purpose="fixture", **kw)


@pytest.mark.parametrize("platform,flag,expected", [
    ("win32", None, True), ("win32", "0", True), ("linux", None, False),
    ("linux", "0", False), ("linux", "1", True)])
def test_host_scope_cannot_disable_windows(monkeypatch, isolated, platform, flag, expected):
    monkeypatch.setattr(PB.sys, "platform", platform)
    if flag is not None:
        monkeypatch.setenv("AEGIS_DEEPSEEK_HOST_ENVELOPE", flag)
    assert PB.host_envelope_required() is expected


@pytest.mark.parametrize("batch", [False, True])
def test_missing_pc_envelope_never_dispatches(monkeypatch, isolated, batch):
    c = Client()
    configure(monkeypatch, c)
    result = call(production_budget=not batch)
    assert result["status"] == "BUDGET_REFUSED"
    assert result["budget_charge_usd"] == 0 and result["cost_usd"] is None
    assert not c.requests and not isolated.exists()
    assert not (isolated.parent / "calls.jsonl").exists()


def test_cloud_without_pc_envelope_keeps_caps_and_telemetry(monkeypatch, isolated):
    c = Client()
    def no_clone(**kw):
        pytest.fail("cloud dispatch must preserve the original SDK client")
    c.with_options = no_clone
    configure(monkeypatch, c, required=False)
    monkeypatch.setattr(LA, "_DAILY_CAP", 1)
    assert call()["ok"]
    assert call()["status"] == "BUDGET_REFUSED"
    assert call(production_budget=False)["ok"]  # existing attended batch semantics
    LA._spend_state["breaker_until"] = LA.time.time() + 60
    assert call(production_budget=False)["status"] == "BUDGET_REFUSED"
    assert len(c.requests) == 2 and not isolated.exists()
    assert c.options == []
    assert len(LT.read_calls(isolated.parent / "calls.jsonl")) == 2


def test_primary_cloud_path_without_envelope(monkeypatch, isolated):
    c = Client()
    def no_clone(**kw):
        pytest.fail("cloud dispatch must preserve the original SDK client")
    c.with_options = no_clone
    configure(monkeypatch, c, required=False)
    assert LA._call_llm("system", "user") == "A fixture answer."
    assert len(c.requests) == 1 and not isolated.exists()


def test_primary_pc_path_reserves(monkeypatch, isolated):
    envelope(isolated)
    c = Client()
    configure(monkeypatch, c)
    assert LA._call_llm("system", "user") == "A fixture answer."
    assert len(PB.snapshot()["calls"]) == 1


@pytest.mark.parametrize("result,status", [(TimeoutError("fake timeout"), "ERROR"),
    (reply(usage=False), "OK"), (reply(model="unpriced-model"), "OK")])
def test_unknown_billing_never_releases_or_fabricates_zero(monkeypatch, isolated, result, status):
    envelope(isolated)
    c = Client(result)
    configure(monkeypatch, c)
    out = call()
    assert out["status"] == status and out["cost_usd"] is None
    assert out["budget_charge_usd"] > 0 and len(c.requests) == 1
    held = next(iter(PB.snapshot()["calls"].values()))
    assert held["status"] == "BILLING_UNKNOWN"
    assert held["held_units"] == held["reserved_units"]
    row = LT.read_calls(isolated.parent / "calls.jsonl")[0]
    assert row["cost_usd"] is None
    if getattr(result, "model", None) == "unpriced-model":
        assert call()["status"] == "BUDGET_REFUSED" and len(c.requests) == 1


def test_success_uses_dated_peak_estimate(monkeypatch, isolated):
    envelope(isolated)
    c = Client()
    configure(monkeypatch, c)
    out = call()
    assert out["ok"] and out["cost_usd"] == pytest.approx(.000018)
    assert out["price_as_of"] == "2026-11-03"
    assert out["cost_basis"] == "PEAK_LIST_ESTIMATE_NOT_BILLED"
    with pytest.raises(PB.BudgetRefused):
        PB.settle({"path": str(isolated), "id": out["reservation_id"]}, reply())


def test_atomic_concurrent_reservations_and_daily_cap(isolated):
    envelope(isolated)
    def one(_):
        try:
            return reserve(production_cap=3)
        except PB.BudgetRefused:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        tickets = list(pool.map(one, range(12)))
    assert sum(t is not None for t in tickets) == 3
    snap = PB.snapshot()
    assert len(snap["calls"]) == 3
    assert snap["daily"][datetime.now(timezone.utc).date().isoformat()] == 3


def test_exhaustion_and_opening_debit(isolated):
    envelope(isolated, cap=.0005)
    data=json.loads(isolated.read_text())
    data["opening_units"]=PB._units(.0004)
    isolated.write_text(json.dumps(data))
    with pytest.raises(PB.BudgetRefused):
        reserve()
    assert not PB.snapshot()["calls"]


def test_usage_bound_breach_blocks(isolated):
    envelope(isolated)
    ticket=reserve()
    r=reply()
    r.usage.completion_tokens=101
    PB.settle(ticket,r)
    with pytest.raises(PB.BudgetRefused):
        reserve()


@pytest.mark.parametrize("fault", ["corrupt", "schema", "write", "lock"])
def test_predispatch_failure_is_no_wire(monkeypatch, isolated, fault):
    envelope(isolated)
    c=Client()
    configure(monkeypatch,c)
    if fault == "corrupt":
        isolated.write_text("{")
    elif fault == "schema":
        isolated.write_text('{}')
    else:
        def fail(*a, **kw):
            raise OSError("fixture storage failure")
        monkeypatch.setattr(PB.DG, "atomic_write_json" if fault == "write" else "file_lock", fail)
    assert call()["status"] == "BUDGET_REFUSED"
    assert not c.requests


def test_settlement_write_failure_retains_reservation(monkeypatch, isolated):
    envelope(isolated)
    c=Client()
    configure(monkeypatch,c)
    original=c.create
    def send(**kw):
        response=original(**kw)
        def fail(*a, **k):
            raise OSError("fixture settlement failure")
        monkeypatch.setattr(PB.DG,"atomic_write_json",fail)
        return response
    c.chat.completions.create=send
    out=call()
    # review 3 (S65): the provider ANSWERED, so the paid reply is kept; the
    # settlement waits in the sidecar and the envelope on disk keeps the full
    # reservation. Every reader applies the sidecar in memory.
    assert out["ok"] and out["billing_status"] == PB.DEFERRED_STATUS
    on_disk = json.loads(isolated.read_text(encoding="utf-8"))
    rec = next(iter(on_disk["calls"].values()))
    assert rec["status"] == "RESERVED_UNKNOWN" and rec["held_units"] >= PB._units(out["cost_usd"])
    assert PB.snapshot()["held_usd"] >= out["cost_usd"]


def test_evidence_path_preserves_timeout_and_host_binding(monkeypatch, isolated):
    envelope(isolated)
    c=Client()
    configure(monkeypatch,c)
    out=call(model_override="deepseek-flash", no_retry=True, non_thinking=True,
             evidence_mode=True, request_timeout_s=12)
    assert out["ok"]
    assert out["evidence"]["budget_scope"] == "shared_host_envelope"
    assert out["evidence"]["shared_budget"]["reservation_id"] == out["reservation_id"]
    assert c.options == [{"max_retries": 0, "timeout": 12.0}, {"max_retries": 0}]
    assert out["evidence"]["telemetry"]["cost_usd"] == out["cost_usd"]


def test_unsupported_billable_options_are_refused(isolated):
    envelope(isolated)
    with pytest.raises(PB.BudgetRefused) as e:
        PB.attempt({"model":"deepseek-flash", "messages":[], "max_tokens":100, "tools":[{}]},
                   base_url="https://api.deepseek.com", purpose="fixture", send=lambda: pytest.fail("wire"))
    assert e.value.no_wire

@pytest.mark.parametrize("fault", ["transport", "identity", "usage", "reply"])
def test_evidence_failure_keeps_host_accounting_metadata(monkeypatch, isolated, fault):
    envelope(isolated)
    result = reply()
    if fault == "transport":
        result = TimeoutError("fake timeout")
    elif fault == "identity":
        result.id = None
    elif fault == "usage":
        result.usage = None
    else:
        result.choices[0].message.content = ""
    c = Client(result)
    configure(monkeypatch, c)
    out = call(model_override="deepseek-flash", no_retry=True, non_thinking=True,
               evidence_mode=True, request_timeout_s=12)
    assert not out["ok"] and len(c.requests) == 1
    row = LT.read_calls(isolated.parent / "calls.jsonl")[0]
    assert row["meta"]["budget_scope"] == "shared_host_envelope"
    assert row["meta"]["shared_budget"]["reservation_id"] == out["reservation_id"]
    if fault in {"transport", "usage"}:
        assert out["cost_usd"] is None and row["cost_usd"] is None
    assert len(PB.snapshot()["calls"]) == 1


def test_primary_missing_pc_envelope_never_dispatches(monkeypatch, isolated):
    c = Client()
    configure(monkeypatch, c)
    assert LA._call_llm("system", "user") is None
    assert not c.requests and not isolated.exists()
    assert LT.read_calls(isolated.parent / "calls.jsonl") == []
