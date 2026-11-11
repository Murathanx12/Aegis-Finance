"""CH-05 R2: the DeepSeek callers that now reserve against the monthly envelope.

Fake transports and isolated envelopes only: no socket, no key, $0. Each caller
is checked twice -- a refusal sends NOTHING and surfaces as that caller's stop
signal (never an empty success), and an admitted call reserves and settles one
envelope row.
"""
from __future__ import annotations

import io
import json
from types import SimpleNamespace as NS

import pytest

from backend.services import provider_budget as PB


@pytest.fixture
def host(monkeypatch, tmp_path):
    """The PC: envelope required, a FIXED envelope path under tmp (absent until
    `envelope()` writes it, so an absent one refuses)."""
    p = tmp_path / "envelope.json"
    monkeypatch.setenv("AEGIS_DEEPSEEK_BUDGET_PATH", str(p))
    monkeypatch.setattr(PB, "host_envelope_required", lambda: True)
    return p


def envelope(p, cap=1):
    p.write_text(json.dumps({"schema": PB.SCHEMA, "session_id": "test-only",
        "cap_units": PB._units(cap), "opening_units": 0, "opening_evidence": "fixture",
        "calls": {}, "daily": {}, "blocked": None}), encoding="utf-8")


def calls(p):
    return json.loads(p.read_text(encoding="utf-8"))["calls"] if p.exists() else {}


def sdk_reply(text="{}", model="deepseek-flash"):
    return NS(id="fixture", model=model,
              choices=[NS(message=NS(content=text), finish_reason="stop")],
              usage=NS(prompt_tokens=20, completion_tokens=10, prompt_cache_hit_tokens=0))


class Client:
    """An OpenAI-SDK-shaped client that records every request."""
    base_url = "https://api.deepseek.com/v1/"

    def __init__(self, result=None):
        self.result = result or sdk_reply()
        self.requests: list[dict] = []
        self.options: list[dict] = []
        self.chat = NS(completions=NS(create=self.create))

    def with_options(self, **kw):
        self.options.append(kw)
        return self

    def create(self, **kw):
        self.requests.append(kw)
        return self.result


def json_reply(text="OK"):
    return {"model": "deepseek-flash",
            "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 3}}


# ── provider_budget: the request shapes it admits, and the two helpers ──────

def test_json_mode_is_admitted_and_other_response_formats_are_not(host):
    envelope(host)
    body = {"model": "deepseek-chat", "max_tokens": 50, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]}
    resp, acct = PB.attempt(body, base_url="https://api.deepseek.com", purpose="fixture",
                            send=lambda: sdk_reply())
    assert acct["billing_status"] == "SETTLED_PEAK_ESTIMATE" and len(calls(host)) == 1
    bad = {**body, "response_format": {"type": "json_schema", "json_schema": {}}}
    with pytest.raises(PB.BudgetRefused) as e:
        PB.attempt(bad, base_url="https://api.deepseek.com", purpose="fixture",
                   send=lambda: pytest.fail("wire"))
    assert e.value.no_wire and len(calls(host)) == 1


def test_guarded_create_on_the_cloud_is_the_plain_sdk_call(monkeypatch, host):
    monkeypatch.setattr(PB, "host_envelope_required", lambda: False)
    c = Client()
    body = {"model": "deepseek-chat", "messages": []}
    resp, acct = PB.guarded_create(c, body, purpose="x",
                                   send=lambda t: t.chat.completions.create(**body))
    assert acct is None and len(c.requests) == 1 and c.options == [] and not host.exists()


def test_guarded_create_on_the_host_reserves_without_sdk_retries(host):
    envelope(host)
    c = Client()
    body = {"model": "deepseek-chat", "max_tokens": 50,
            "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]}
    resp, acct = PB.guarded_create(c, body, purpose="fixture",
                                   send=lambda t: t.chat.completions.create(**body))
    assert c.options == [{"max_retries": 0}] and len(c.requests) == 1
    assert acct["reservation_id"] in calls(host)


def test_guarded_send_refusal_sends_nothing(host):
    with pytest.raises(PB.BudgetRefused) as e:          # fixed envelope absent
        PB.guarded_send({"model": "deepseek-chat", "max_tokens": 5,
                         "messages": [{"role": "system", "content": "s"},
                                      {"role": "user", "content": "u"}]},
                        purpose="fixture", send=lambda: pytest.fail("wire"))
    assert e.value.no_wire


# ── llm_swarm.default_llm_call (the IIF-1 path) ─────────────────────────────

@pytest.fixture
def no_governor(monkeypatch):
    from backend.services import research_budget
    monkeypatch.setattr(research_budget, "require", lambda *a, **k: None)


def test_swarm_refusal_is_a_campaign_stop_not_a_retry(host, no_governor):
    from backend.services import llm_swarm, research_budget
    c = Client()
    with pytest.raises(research_budget.ResearchBudgetExhausted, match="DEEPSEEK BUDGET|envelope"):
        llm_swarm.default_llm_call("system json", "user", client=c, max_retries=3)
    assert c.requests == []


def test_swarm_call_reserves_and_carries_its_accounting(host, no_governor):
    from backend.services import llm_swarm
    envelope(host)
    c = Client(sdk_reply('{"forecasts": []}'))
    reply = llm_swarm.default_llm_call("system json", "user", client=c, max_retries=0)
    assert reply.budget_accounting["reservation_id"] in calls(host)
    assert c.requests[0]["response_format"] == {"type": "json_object"}


# ── model_provider.complete ─────────────────────────────────────────────────

class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_model_provider_refusal_is_its_own_provider_refusal(monkeypatch, host):
    import urllib.request

    from backend.services import model_provider as MP
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-only")
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("wire"))
    with pytest.raises(MP.BudgetRefusal) as e:
        MP.complete("deepseek", "hello", purpose="fixture")
    assert isinstance(e.value, MP.ProviderRefusal) and "DEEPSEEK BUDGET" in str(e.value)


def test_model_provider_admitted_call_settles(monkeypatch, host):
    import urllib.request

    from backend.services import model_provider as MP
    envelope(host)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-only")
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: _Resp(json.dumps(json_reply("ready")).encode()))
    rep = MP.complete("deepseek", "hello", purpose="fixture", max_tokens=16)
    assert rep.text == "ready" and rep.budget_accounting["reservation_id"] in calls(host)


# ── llm_research.ask ────────────────────────────────────────────────────────

def test_research_refusal_is_budget_exhausted_and_ledgers_nothing(monkeypatch, host, tmp_path):
    import requests

    from backend.services import llm_research as LR
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-only")
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("wire"))
    ledger = tmp_path / "ledger.jsonl"
    with pytest.raises(LR.BudgetExhausted, match="DEEPSEEK BUDGET|envelope"):
        LR.ask("q", purpose="fixture", ledger_path=ledger)
    assert not ledger.exists()


def test_research_admitted_call_ledgers_the_envelope_charge(monkeypatch, host, tmp_path):
    import requests

    from backend.services import llm_research as LR
    envelope(host)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-only")
    monkeypatch.setattr(requests, "post", lambda *a, **k: NS(
        raise_for_status=lambda: None, json=lambda: json_reply("an answer")))
    ledger = tmp_path / "ledger.jsonl"
    out = LR.ask("q", purpose="fixture", max_tokens=50, ledger_path=ledger)
    row = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    acct = row["meta"]["shared_budget"]
    assert out["text"] == "an answer" and acct["reservation_id"] in calls(host)
    assert row["cost_usd"] == acct["budget_charge_usd"]


# ── why_moved, leakage_probe, book_factory, stack_health ────────────────────

def test_why_moved_refusal_degrades_the_lens_with_the_envelope_line(monkeypatch, host):
    import openai

    from backend.services import why_moved as WM
    c = Client()
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: c)
    with pytest.raises(PB.BudgetRefused):
        WM.default_llm_call("system", "user", api_key="fixture-only")
    assert c.requests == []


def test_leakage_probe_refusal_is_a_campaign_stop(host, no_governor):
    from backend.services import leakage_probe as LP
    from backend.services.research_budget import ResearchBudgetExhausted
    c = Client()
    with pytest.raises(ResearchBudgetExhausted):
        LP.call_llm("system json", "user", client=c, max_retries=2)
    assert c.requests == []


def test_book_factory_refusal_is_a_stop_marker_not_a_failed_book(monkeypatch, host):
    from backend.services import llm_analyzer as LA
    from scripts import book_factory as BF
    c = Client()
    monkeypatch.setattr(LA, "_DEEPSEEK_API_KEY", "fixture-only")
    monkeypatch.setattr(LA, "_get_openai_client", lambda: c)
    monkeypatch.setattr(LA, "_acquire_call_budget", lambda: True)
    out = BF.deepseek_call("system", "user", max_tokens=100)
    assert out["budget_refused"] and "DEEPSEEK BUDGET" in out["error"] and c.requests == []


def test_stack_health_deep_probe_refusal_is_a_red_row(monkeypatch, host):
    import urllib.request

    from backend.services import system_health as SH
    from scripts import stack_health
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-only")
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("wire"))
    row = stack_health.deep_deepseek()
    assert row["verdict"] == "REFUSED" and "DEEPSEEK BUDGET" in row["detail"]
    assert SH.exit_code([row]) == 2
