"""CH-04b: Featherless as a capped SECOND provider for named bulk purposes.

Owner, 2026-11-11: "we have 75$ usd in featherless api use it". What is pinned:

  * selection is by PURPOSE through config (`LLM_PURPOSE_PROVIDER`), empty by
    default, so nothing changes until a flag is set;
  * every Featherless call is reserved against its OWN envelope
    (`provider_budget.featherless_attempt`): a monthly cap, a lifetime ceiling,
    an unpriced model and a foreign host are refused BEFORE anything is sent;
  * a refusal is red: `BUDGET_REFUSED` on `call_named`, rc 2 on the CLI, and
    `featherless:BUDGET_REFUSED` on the digest Meter (the script exits 2);
  * a Featherless miss in the digest falls back to the metered DeepSeek call
    (which its own envelope still gates) and the row says so;
  * the language pin and the non-Latin refusal apply on this path too.

Offline: every client and every model is a fake; the conftest blocks sockets.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend import config as C
from backend.services import llm_analyzer as LA
from backend.services import provider_budget as PB
from backend.services import world_digest as WD
from backend.tests.test_world_digest import GOOD, _item, _ok

MODEL = "Qwen/Qwen3-30B-A3B-Instruct-2507"
BASE = "https://api.featherless.ai/v1"


@pytest.fixture
def envelope(tmp_path, monkeypatch):
    p = tmp_path / "featherless_local.json"
    monkeypatch.setenv("AEGIS_FEATHERLESS_BUDGET_PATH", str(p))
    monkeypatch.setattr(C, "FEATHERLESS_MONTHLY_CAP_USD", 25.0)
    monkeypatch.setattr(C, "FEATHERLESS_LIFETIME_CAP_USD", 75.0)
    return p


def _body(model=MODEL, max_tokens=600, **extra):
    return {"model": model, "max_tokens": max_tokens, "temperature": 0.2,
            "messages": [{"role": "system", "content": "sys"}, {"role": "user", "content": "user"}],
            **extra}


def _resp(model=MODEL, ti=1500, to=200, cost=None, text='{"ok": true}'):
    usage = {"prompt_tokens": ti, "completion_tokens": to}
    if cost is not None:
        usage["cost"] = cost
    return SimpleNamespace(model=model, usage=SimpleNamespace(**usage),
                           choices=[SimpleNamespace(message=SimpleNamespace(content=text),
                                                    finish_reason="stop")])


def _never():
    pytest.fail("nothing may be sent when the envelope refuses")


# ── the declaration ──────────────────────────────────────────────────────────

def test_deepseek_stays_primary_and_featherless_is_the_only_declared_secondary():
    assert LA.PRIMARY_PROVIDER == "deepseek"
    assert set(LA.SECONDARY_PROVIDERS) == {"featherless"}
    assert LA.SOLE_PROVISIONED_PROVIDER == LA.PRIMARY_PROVIDER     # deprecated alias, same meaning


def test_no_purpose_is_routed_anywhere_by_default(monkeypatch):
    import os
    if os.getenv("AEGIS_LLM_PURPOSE_PROVIDER"):
        pytest.skip("a route is set in this environment on purpose")
    assert C.LLM_PURPOSE_PROVIDER == {}
    assert LA.provider_for("world_digest_extract") == "deepseek"
    assert WD.extract_provider() == "deepseek"


def test_a_purpose_route_selects_featherless_and_a_typo_is_red(monkeypatch):
    monkeypatch.setattr(C, "LLM_PURPOSE_PROVIDER", {"world_digest_extract": "featherless"})
    assert LA.provider_for("world_digest_extract") == "featherless"
    assert LA.provider_for("something_else") == "deepseek"
    monkeypatch.setattr(C, "LLM_PURPOSE_PROVIDER", {"world_digest_extract": "featherles"})
    with pytest.raises(ValueError, match="featherles"):
        LA.provider_for("world_digest_extract")


def test_every_featherless_default_model_is_priced():
    assert C.FEATHERLESS_DEFAULT_MODEL in C.FEATHERLESS_MODELS
    assert C.FEATHERLESS_MONTHLY_CAP_USD <= C.FEATHERLESS_LIFETIME_CAP_USD <= C.FEATHERLESS_HARD_CAP_USD
    # ONE rate table (X7): the envelope and telemetry price from the same rows
    for m in C.FEATHERLESS_MODELS:
        row = C.LLM_PRICE_PER_MTOK[m]
        assert PB._fl_price(m) == (row["in"], row["out"])
        assert row["cached_in"] == row["in"]                      # never priced as cached


def test_a_deepseek_model_is_not_sendable_to_featherless(envelope):
    # priced in the table, but not a Featherless model: refused before dispatch
    with pytest.raises(PB.BudgetRefused, match="UNPRICED"):
        PB.featherless_quote("s", "u", 10, "deepseek-flash")


# ── the envelope ─────────────────────────────────────────────────────────────

def test_a_call_settles_at_the_higher_of_our_price_and_the_providers_cost(envelope):
    resp, acct = PB.featherless_attempt(_body(), purpose="t", send=lambda: _resp(ti=500, cost=0.0003))
    assert acct["billing_status"] == "SETTLED"
    ours = (500 * 0.125 + 200 * 0.45) / 1e6
    assert ours < 0.0003
    assert acct["cost_usd"] == pytest.approx(0.0003, abs=1e-9)    # the provider's figure was higher
    assert acct["provider_cost_usd"] == 0.0003
    s = json.loads(envelope.read_text())
    assert s["schema"] == PB.FEATHERLESS_SCHEMA and len(s["calls"]) == 1
    assert PB.featherless_status_line().startswith("FEATHERLESS BUDGET OK")


def test_the_monthly_cap_refuses_before_dispatch(envelope, monkeypatch):
    monkeypatch.setattr(C, "FEATHERLESS_MONTHLY_CAP_USD", 0.0001)
    with pytest.raises(PB.BudgetRefused, match="EXHAUSTED_MONTH") as ei:
        PB.featherless_attempt(_body(), purpose="t", send=_never)
    assert ei.value.no_wire is True


def test_the_lifetime_ceiling_binds_across_months(envelope, monkeypatch):
    monkeypatch.setattr(C, "FEATHERLESS_LIFETIME_CAP_USD", 30.0)
    old = {"held_units": PB._units(29.9999), "status": "SETTLED", "started_utc": "2026-01-15T00:00:00+00:00"}
    envelope.write_text(json.dumps({**PB._fl_fresh(), "calls": {"old": old}}))
    # this month is empty, so only the lifetime ceiling can refuse
    with pytest.raises(PB.BudgetRefused, match="EXHAUSTED_LIFETIME"):
        PB.featherless_attempt(_body(), purpose="t", send=_never)
    assert PB.featherless_status_line().startswith("FEATHERLESS BUDGET OK")   # room > 0, a call needs more
    assert PB.main(["status", "--provider", "featherless"]) == 0


def test_status_is_red_when_the_month_is_spent(envelope, monkeypatch, capsys):
    monkeypatch.setattr(C, "FEATHERLESS_MONTHLY_CAP_USD", 1.0)
    now = datetime.now(timezone.utc).isoformat()
    envelope.write_text(json.dumps({**PB._fl_fresh(), "calls": {
        "a": {"held_units": PB._units(1.0), "status": "SETTLED", "started_utc": now}}}))
    assert PB.main(["status", "--provider", "featherless"]) == 2
    assert "FEATHERLESS BUDGET REFUSED (EXHAUSTED_MONTH)" in capsys.readouterr().out


@pytest.mark.parametrize("model", ["Qwen/Some-Unpriced-Model", "deepseek-chat"])
def test_an_unpriced_model_is_refused_before_dispatch(envelope, model):
    with pytest.raises(PB.BudgetRefused, match="UNPRICED") as ei:
        PB.featherless_attempt(_body(model=model), purpose="t", send=_never)
    assert ei.value.no_wire is True and not envelope.exists()


def test_a_foreign_host_and_unsupported_options_are_refused(envelope):
    with pytest.raises(PB.BudgetRefused, match="official"):
        PB.featherless_attempt(_body(), purpose="t", send=_never, base_url="https://evil.example/v1")
    with pytest.raises(PB.BudgetRefused, match="unsupported"):
        PB.featherless_attempt(_body(tools=[{}]), purpose="t", send=_never)
    with pytest.raises(PB.BudgetRefused, match="unsupported"):
        PB.featherless_attempt(_body(response_format={"type": "json_schema"}), purpose="t", send=_never)
    # JSON mode is admitted
    PB.featherless_attempt(_body(response_format={"type": "json_object"}), purpose="t",
                           send=lambda: _resp())


def test_a_different_returned_model_blocks_the_envelope(envelope):
    _, acct = PB.featherless_attempt(_body(), purpose="t", send=lambda: _resp(model="other/model"))
    assert acct["billing_status"] == "BILLING_UNKNOWN"          # full reservation kept
    with pytest.raises(PB.BudgetRefused, match="BLOCKED"):
        PB.featherless_attempt(_body(), purpose="t", send=_never)


def test_usage_above_the_reservation_bound_blocks_the_envelope(envelope):
    _, acct = PB.featherless_attempt(_body(max_tokens=10), purpose="t", send=lambda: _resp(to=5000))
    assert acct["billing_status"] == "SETTLED"                   # the true cost is recorded ...
    assert PB.featherless_status_line().startswith("FEATHERLESS BUDGET REFUSED (BLOCKED)")  # ... and blocks


def test_an_http_error_response_is_unbilled_and_a_timeout_keeps_the_reservation(envelope):
    class Gated(Exception):
        status_code = 403

    with pytest.raises(Gated) as ei:
        PB.featherless_attempt(_body(), purpose="t", send=lambda: (_ for _ in ()).throw(Gated()))
    assert ei.value.shared_budget_accounting["billing_status"] == "UNBILLED_HTTP_REFUSAL"
    assert ei.value.shared_budget_accounting["budget_charge_usd"] == 0
    with pytest.raises(TimeoutError) as ei2:
        PB.featherless_attempt(_body(), purpose="t", send=lambda: (_ for _ in ()).throw(TimeoutError()))
    acct = ei2.value.shared_budget_accounting
    assert acct["billing_status"] == "BILLING_UNKNOWN" and acct["budget_charge_usd"] > 0
    s = json.loads(envelope.read_text())
    assert sorted(r["status"] for r in s["calls"].values()) == ["BILLING_UNKNOWN", "UNBILLED_HTTP_REFUSAL"]


def test_the_featherless_envelope_never_touches_the_deepseek_one(envelope, tmp_path, monkeypatch):
    ds = tmp_path / "deepseek_local.json"
    monkeypatch.setenv("AEGIS_DEEPSEEK_BUDGET_PATH", str(ds))
    PB.featherless_attempt(_body(), purpose="t", send=lambda: _resp())
    assert not ds.exists() and envelope.exists()


# ── call_named("featherless") ────────────────────────────────────────────────

class _FakeClient:
    def __init__(self, reply):
        self.reply, self.sent = reply, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.sent.append(kw)
        return self.reply


@pytest.fixture
def fake_client(monkeypatch, envelope):
    def install(reply):
        client = _FakeClient(reply)
        monkeypatch.setattr(LA, "_get_featherless_client", lambda: client)
        return client
    return install


def test_call_named_featherless_is_guarded_pinned_and_priced(fake_client):
    client = fake_client(_resp(text=json.dumps({"topic": "x"})))
    res = LA.call_named("featherless", "Type this.", "item", purpose="world_digest_extract_featherless",
                        max_tokens=600, json_object=True)
    assert res["ok"] and res["status"] == "OK" and res["billing_status"] == "SETTLED"
    assert res["served_model"] == MODEL and res["cost_usd"] > 0
    sent = client.sent[0]
    assert sent["model"] == MODEL and sent["response_format"] == {"type": "json_object"}
    assert sent["messages"][0]["content"].endswith(LA._LANGUAGE_PIN)            # the pin travels


def test_call_named_featherless_refuses_a_non_latin_reply(fake_client):
    fake_client(_resp(text="这是一个中文回复，没有任何英文内容。" * 3))
    res = LA.call_named("featherless", "s", "u", purpose="t", max_tokens=100)
    assert res["ok"] is False and res["status"] == "LANGUAGE_REFUSED" and res["text"] is None


def test_call_named_featherless_budget_refusal_sends_nothing(fake_client, monkeypatch):
    client = fake_client(_resp())
    monkeypatch.setattr(C, "FEATHERLESS_MONTHLY_CAP_USD", 0.0001)
    res = LA.call_named("featherless", "s", "u", purpose="t", max_tokens=600)
    assert res["status"] == "BUDGET_REFUSED" and "FEATHERLESS BUDGET REFUSED" in res["error"]
    assert client.sent == []


def test_call_named_featherless_unpriced_override_sends_nothing(fake_client):
    client = fake_client(_resp())
    res = LA.call_named("featherless", "s", "u", purpose="t", max_tokens=600,
                        model_override="someone/unpriced-model")
    assert res["status"] == "BUDGET_REFUSED" and "UNPRICED" in res["error"] and client.sent == []


def test_call_named_featherless_without_a_key_is_not_configured(monkeypatch):
    monkeypatch.setattr(LA, "_get_featherless_client", lambda: None)
    res = LA.call_named("featherless", "s", "u", purpose="t")
    assert res["status"] == "NOT_CONFIGURED" and "FEATHERLESS_API_KEY" in res["error"]


def test_json_mode_is_scoped_to_featherless():
    res = LA.call_named("deepseek", "s", "u", purpose="t", json_object=True)
    assert res["status"] == "INVALID_JSON_SCOPE"


def test_provider_status_lists_featherless_as_a_named_secondary(monkeypatch):
    monkeypatch.setenv("FEATHERLESS_API_KEY", "fl-test-not-a-real-key")
    st = LA.provider_status()
    assert st["primary"] == "deepseek" and st["secondary"] == ["featherless"]
    assert st["named"]["featherless"]["state"] == "configured"
    assert st["roles"]["featherless"] == "bulk_secondary"


# ── the digest's stage-1 typing ──────────────────────────────────────────────

def _fl_ok(text):
    return {"ok": True, "text": text, "status": "OK", "served_model": MODEL, "budget_charge_usd": 0.0003}


def test_flag_off_the_digest_never_calls_featherless(tmp_path):
    m = WD.Meter(1.0, llm=lambda *a, **k: _ok(json.dumps(GOOD)),
                 featherless_llm=lambda *a, **k: pytest.fail("featherless must stay off by default"))
    ex = WD.extract_items([_item()], m, cache={}, stage_cap=1.0, workers=1, cache_file=tmp_path / "c.jsonl")
    assert ex["extract_provider"] == "deepseek"
    assert "featherless_calls" not in m.summary()                  # the receipt is unchanged
    assert "extract_fallback_from" not in ex["rows"][0]


def test_routed_typing_uses_featherless_and_spends_outside_the_deepseek_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(WD._cfg, "LLM_PURPOSE_PROVIDER", {"world_digest_extract": "featherless"})
    m = WD.Meter(1.0, llm=lambda *a, **k: pytest.fail("DeepSeek must not be called"),
                 featherless_llm=lambda *a, **k: _fl_ok(json.dumps(GOOD)))
    ex = WD.extract_items([_item()], m, cache={}, stage_cap=1.0, workers=1, cache_file=tmp_path / "c.jsonl")
    assert ex["extract_provider"] == "featherless" and ex["featherless_typed_calls"] == 1
    assert ex["rows"][0]["extract_model"] == f"featherless:{MODEL}"
    assert m.spent == 0 and m.calls == 0                            # the DeepSeek run budget is untouched
    assert m.summary()["featherless_spent_usd"] == pytest.approx(0.0003)


@pytest.mark.parametrize("reply,why", [
    ({"ok": False, "status": "BUDGET_REFUSED", "text": None}, "featherless:BUDGET_REFUSED"),
    ({"ok": False, "status": "LANGUAGE_REFUSED", "text": None}, "featherless:LANGUAGE_REFUSED"),
    (_fl_ok("not json"), "featherless:NOT_TYPED"),
])
def test_a_featherless_miss_falls_back_to_deepseek_and_the_row_says_so(tmp_path, monkeypatch, reply, why):
    monkeypatch.setattr(WD._cfg, "LLM_PURPOSE_PROVIDER", {"world_digest_extract": "featherless"})
    paid = []
    m = WD.Meter(1.0, llm=lambda *a, **k: paid.append(1) or _ok(json.dumps(GOOD)),
                 featherless_llm=lambda *a, **k: reply)
    ex = WD.extract_items([_item()], m, cache={}, stage_cap=1.0, workers=1, cache_file=tmp_path / "c.jsonl")
    assert paid == [1] and ex["featherless_fallback_calls"] == 1
    row = ex["rows"][0]
    assert row["extract_model"].startswith("deepseek:") and row["extract_fallback_from"] == why
    if reply["status"] == "BUDGET_REFUSED":
        # the counter `scripts/world_digest` turns into DEGRADED_MODEL_BUDGET, rc 2
        assert m.statuses["featherless:BUDGET_REFUSED"] == 1


def test_the_fallback_is_itself_gated_by_the_deepseek_run_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(WD._cfg, "LLM_PURPOSE_PROVIDER", {"world_digest_extract": "featherless"})
    m = WD.Meter(0.0, llm=lambda *a, **k: pytest.fail("no DeepSeek room: no call"),
                 featherless_llm=lambda *a, **k: {"ok": False, "status": "BUDGET_REFUSED", "text": None})
    ex = WD.extract_items([_item()], m, cache={}, stage_cap=1.0, workers=1, cache_file=tmp_path / "c.jsonl")
    assert ex["budget_skipped"] == 1 and ex["rows"] == []


def test_the_default_featherless_path_is_call_named_with_json_mode(monkeypatch):
    seen = {}

    def fake_call_named(provider, system, user, **kw):
        seen.update(provider=provider, **kw)
        return {"ok": False, "status": "BUDGET_REFUSED", "text": None}
    monkeypatch.setattr(LA, "call_named", fake_call_named)
    text, status = WD.Meter(1.0).call_featherless("s", "u", purpose="p", max_tokens=600)
    assert text is None and status == "BUDGET_REFUSED"
    assert seen["provider"] == "featherless" and seen["json_object"] is True


def test_an_unknown_route_for_the_digest_is_red(monkeypatch):
    monkeypatch.setattr(WD._cfg, "LLM_PURPOSE_PROVIDER", {"world_digest_extract": "openai"})
    with pytest.raises(ValueError, match="LLM_PURPOSE_PROVIDER"):
        WD.extract_provider()
