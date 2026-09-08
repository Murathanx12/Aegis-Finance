"""The free-inference backends declare what they are, and the declaration is pinned.

`test_llm_provider_declaration.py` exists because `llm_analyzer._get_provider`
reads `if _ANTHROPIC_API_KEY: return "claude"` first and has returned `deepseek`
for its whole life. The fix was not to rewrite the branch; it was to DECLARE the
resolved provider and fail the suite if the declaration ever stops matching.

This is that test for the free backends, plus the two things a free provider adds:

* **cost 0.0 is not "no cost"** -- a free call still emits a token count, still
  goes through `llm_telemetry`, and still produces a spend LINE reading $0.00.
  A backend with no line and a backend with a zero line look the same in a
  summary and mean opposite things.
* **the language contract reaches the raw-HTTP path**. The existing contract
  test walks the AST for `chat.completions.create` -- the OpenAI SDK -- so
  `model_provider`, which speaks urllib, was never in its enumeration and
  carried a private `_LANGUAGE_PIN` with no reply guard at all. The last test
  here is the raw-HTTP arm of that same enumeration.

NO NETWORK. Every wire call is monkeypatched; the fast suite blocks sockets.
"""

from __future__ import annotations

import ast
import io
from pathlib import Path

import pytest

from backend.config import LLM_PRICE_PER_MTOK
from backend.services import free_inference as fi
from backend.services import llm_language as _lang
from backend.services import model_provider as mp

SERVICES = Path(__file__).resolve().parents[1] / "services"


def _reply(text: str = "ok", *, tin: int = 10, tout: int = 5) -> mp.Reply:
    return mp.Reply(provider="stub", model="stub", text=text, latency_s=0.01,
                    prompt_tokens=tin, completion_tokens=tout)


@pytest.fixture(autouse=True)
def _isolate_counters(monkeypatch):
    """Per-test counters. A shared dict makes one test's refusal another's."""
    monkeypatch.setattr(fi, "_USAGE", {})
    monkeypatch.setattr(_lang, "REFUSALS", {})


# ── the declaration ─────────────────────────────────────────────────────────
def test_every_declared_backend_names_a_real_transport():
    for name, row in fi.BACKENDS.items():
        assert row.transport in mp.PROVIDERS, (
            f"{name} names transport {row.transport!r} which is not a row in "
            "model_provider.PROVIDERS -- a backend pointing at nothing")


def test_every_declared_model_is_in_the_ONE_price_table():
    """An unpriced model records cost_usd=None and makes every total a LOWER
    BOUND. That is the failure `price_call` warns about; here it is prevented."""
    for name, row in fi.BACKENDS.items():
        for m in row.models:
            assert m in LLM_PRICE_PER_MTOK, (
                f"{name} declares {m!r} with no row in "
                f"config.LLM_PRICE_PER_MTOK. One price table, no exceptions.")


def test_a_free_backend_prices_every_model_at_exactly_zero():
    for name, row in fi.BACKENDS.items():
        if not row.is_free:
            continue
        for m in row.models:
            assert fi.is_free_model(m), (
                f"{name} is declared free but {m!r} does not price at zero. "
                "Freeness is DERIVED from the price table so the two facts "
                "cannot disagree.")


def test_the_paid_backend_is_not_priced_at_zero():
    """The mirror of the test above. If DeepSeek ever priced at zero, every
    guard here would pass and the balance would still drain."""
    paid = fi.BACKENDS[fi.PAID_BACKEND]
    assert not paid.is_free
    assert not any(fi.is_free_model(m) for m in paid.models)


def test_the_default_backend_is_free_and_is_never_the_paid_one():
    """Murat has ~$9 left and is preserving it. A new caller that reaches for
    the paid provider by default is how that becomes $0 with no decision."""
    assert fi.DEFAULT_BACKEND != fi.PAID_BACKEND
    assert fi.BACKENDS[fi.DEFAULT_BACKEND].is_free
    assert fi.resolve(None).name == fi.DEFAULT_BACKEND


def test_a_keyless_backend_reports_key_present_as_None_not_False():
    """`unprobed`, not `absent`. A local server has no credential to be missing,
    so a config read carries NO information about it -- reporting False would be
    the ANTHROPIC_API_KEY mistake with the sign flipped."""
    row = fi.capability_declaration()["backends"]["local_gguf"]
    assert row["needs_key"] is False
    assert row["key_present"] is None
    # A probe date says "somebody saw it answer that day" and NOT "it is up".
    # Only a probe can say the second thing, and the note must send the reader
    # to the thing that starts it rather than implying it is already running.
    assert "llama-start" in row["note"]


def test_the_declaration_carries_the_language_contract_it_actually_uses():
    d = fi.capability_declaration()
    assert d["language_pin"] == _lang.LANGUAGE_PIN
    assert d["non_latin_bar"] == _lang.NON_LATIN_BAR
    assert d["price_table"] == "backend.config.LLM_PRICE_PER_MTOK"


def test_models_that_did_not_serve_are_recorded_not_deleted():
    """"We tried it and it 404s" is a fact a future session otherwise re-buys."""
    nim = fi.BACKENDS["nvidia_nim"]
    assert nim.not_served, "the 404/timeout list must survive in the table"
    assert not (set(nim.models) & set(nim.not_served)), (
        "a model cannot be both served and not served")


# ── refusals ────────────────────────────────────────────────────────────────
def test_an_unknown_backend_is_a_refusal_and_not_a_fallback():
    with pytest.raises(mp.ProviderRefusal) as e:
        fi.complete("groq", "hi")
    assert "groq" in str(e.value) and "REFUSAL" in str(e.value)


def test_an_undeclared_model_is_refused_before_the_wire(monkeypatch):
    called = []
    monkeypatch.setattr(fi, "_wire", lambda *a, **k: called.append(1))
    with pytest.raises(mp.ProviderRefusal) as e:
        fi.complete("nvidia_nim", "hi", model="meta/llama-3.3-70b-instruct")
    assert not called, "an undeclared model must not reach the network"
    assert "LLM_PRICE_PER_MTOK" in str(e.value)


# ── accounting ──────────────────────────────────────────────────────────────
def test_a_free_call_costs_zero_and_still_emits_a_token_count(monkeypatch):
    monkeypatch.setattr(fi, "_wire",
                        lambda *a, **k: _reply("A stock split.", tin=91, tout=75))
    rep = fi.complete("nvidia_nim", "what is a stock split?", record=False)
    assert rep.cost_usd == 0.0
    assert (rep.tokens_in, rep.tokens_out, rep.tokens_total) == (91, 75, 166)
    assert rep.cost_class == "free"


def test_usage_emits_a_dollar_line_for_a_backend_that_spent_nothing():
    u = fi.usage()
    assert set(u) == set(fi.BACKENDS), "every declared backend gets a line"
    assert u["deepseek"]["calls"] == 0
    assert u["deepseek"]["cost_usd_str"] == "$0.00", (
        "an absent line and a $0.00 line read identically in a summary and "
        "mean opposite things")


def test_the_counterfactual_is_priced_from_the_same_table():
    """The point of the lane in one number, and not at a made-up rate."""
    p = LLM_PRICE_PER_MTOK["deepseek-chat"]
    got = fi.counterfactual_deepseek(1_000_000, 1_000_000)
    assert got == pytest.approx(p["in"] + p["out"])
    assert got > 0, "if the counterfactual is zero the lane has no point"


def test_a_free_call_is_recorded_in_telemetry_like_a_paid_one(monkeypatch):
    seen = {}
    monkeypatch.setattr(fi, "_wire", lambda *a, **k: _reply("fine", tin=7, tout=3))
    monkeypatch.setattr(fi._tel, "record_call", lambda **kw: seen.update(kw))
    fi.complete("nvidia_nim", "hi", purpose="unit")
    assert seen["provider"] == "nvidia_nim" and seen["tokens_in"] == 7
    assert seen["meta"]["free"] is True and seen["meta"]["cost_class"] == "free"


# ── the language contract ───────────────────────────────────────────────────
def test_a_non_latin_reply_is_REFUSED_counted_and_still_accounted(monkeypatch):
    """Refused, not repaired and not retried -- and the tokens it burned are
    recorded anyway, because a refusal rate needs a denominator."""
    seen = {}
    monkeypatch.setattr(mp, "_key", lambda name: "stub-key")
    monkeypatch.setattr(fi._tel, "record_call", lambda **kw: seen.update(kw))

    def _chinese(*a, **k):
        # Go through the REAL model_provider guard so this test exercises the
        # central path rather than a re-implementation of it.
        return mp.complete(*a, **k)

    monkeypatch.setattr(fi, "_wire", _chinese)
    monkeypatch.setattr(mp.urllib.request, "urlopen", _fake_urlopen(
        "股票拆分是一种公司行为"))

    with pytest.raises(mp.LanguageRefused) as e:
        fi.complete("nvidia_nim", "what is a stock split?", purpose="unit")
    assert "DISCARDED" in str(e.value)
    assert _lang.refusals().get("nvidia_nim") == 1, (
        "the refusal must be counted under the BACKEND name, not the transport")
    assert seen["error"] == "LANGUAGE_REFUSED" and seen["tokens_out"] == 5
    assert fi.usage()["nvidia_nim"]["tokens_out"] == 5


def test_an_english_reply_through_the_same_path_is_not_refused(monkeypatch):
    """The guard must not be a blanket refusal; the negative control."""
    monkeypatch.setattr(mp, "_key", lambda name: "stub-key")
    monkeypatch.setattr(mp.urllib.request, "urlopen",
                        _fake_urlopen("A stock split is a corporate action."))
    rep = fi.complete("nvidia_nim", "what is a stock split?", record=False)
    assert rep.text.startswith("A stock split")
    assert _lang.refusals() == {}


def _fake_urlopen(text: str):
    """A minimal OpenAI-compatible response, so the REAL parse path is used."""
    import json as _json

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return _json.dumps({
                "choices": [{"message": {"content": text},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }).encode()

    return lambda req, timeout=None: _Resp()


def test_model_provider_no_longer_defines_its_own_language_pin():
    """It carried `_LANGUAGE_PIN = " Respond in English."` -- one word different
    from the contract, and a second definition of the one thing that exists
    BECAUSE the same text was written twice."""
    assert mp._LANGUAGE_PIN is _lang.LANGUAGE_PIN


def _raw_http_completion_sites() -> set[str]:
    """Modules under services/ that POST to a `/chat/completions` URL directly.

    The blind spot in `test_llm_language_contract.py`: its detector looks for
    `chat.completions.create`, the OpenAI SDK call. A module that builds the URL
    itself and hands it to urllib is just as much a direct wire path and was in
    no enumeration at all.
    """
    found = set()
    for p in SERVICES.rglob("*.py"):
        try:
            tree = ast.parse(io.open(p, encoding="utf-8").read())
        except Exception:                                       # noqa: BLE001
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and node.value.endswith("/chat/completions"):
                found.add(p.stem)
    return found


@pytest.mark.parametrize("mod", sorted(_raw_http_completion_sites()))
def test_every_raw_http_call_site_pins_AND_guards(mod):
    src = io.open(SERVICES / f"{mod}.py", encoding="utf-8").read()
    assert ("_lang.pin(" in src or "_lang.pin_messages(" in src), (
        f"{mod} builds a /chat/completions request without the central pin")
    assert ("_lang.refuse(" in src or "_lang.guard(" in src), (
        f"{mod} pins the request and trusts whatever came back. That is the "
        "polite half of the contract; wire the reply through llm_language.")


def test_the_raw_http_detector_actually_finds_something():
    """A detector that matches nothing passes forever. Name the case it must
    catch -- `detectability_gate` was green for two days by finding nobody."""
    assert "model_provider" in _raw_http_completion_sites()
