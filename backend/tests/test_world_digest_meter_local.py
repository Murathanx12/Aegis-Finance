"""CH-05 R5: the digest Meter debits in-flight reservations under its lock (a
runtime fix ported to main), and stage-1 typing can go to the on-box model
behind a flag that is OFF by default. Offline: every model is a fake."""
from __future__ import annotations

import json
import threading

import pytest

from backend.services import world_digest as WD
from backend.tests.test_world_digest import GOOD, _item, _ok


# ── the in-flight reservation (ported from the runtime) ──────────────────────

def test_an_in_flight_reservation_holds_headroom_for_concurrent_callers():
    started, release = threading.Event(), threading.Event()

    def slow(system, user, **kw):
        started.set()
        release.wait(5)
        return _ok("{}", cost=0.001)
    m = WD.Meter(0.005, llm=slow)
    t = threading.Thread(target=lambda: m.call("s", "u", purpose="t", max_tokens=10, stage="x",
                                               reserve_usd=0.003))
    t.start()
    assert started.wait(5)
    # main checked-then-called: this second call passed the gate on the same headroom
    with pytest.raises(WD.BudgetExceeded):
        m.call("s", "u", purpose="t", max_tokens=10, stage="x", reserve_usd=0.003)
    release.set()
    t.join(5)
    assert m.spent == pytest.approx(0.001)              # settled to the real cost
    assert m.by_stage["x"] == pytest.approx(0.001)


def test_a_dispatch_that_raises_keeps_its_reservation():
    def boom(system, user, **kw):
        raise ConnectionError("transport died after send")
    m = WD.Meter(1.0, llm=boom)
    with pytest.raises(ConnectionError):
        m.call("s", "u", purpose="t", max_tokens=10, stage="x", reserve_usd=0.004)
    assert m.spent == pytest.approx(0.004) and m.failed == 1 and m.unpriced == 1


@pytest.mark.parametrize("bad", [float("nan"), -0.1, float("inf")])
def test_an_invalid_reservation_is_refused_before_any_call(bad):
    m = WD.Meter(1.0, llm=lambda *a, **k: pytest.fail("no call"))
    with pytest.raises(WD.BudgetExceeded, match="invalid"):
        m.call("s", "u", purpose="t", max_tokens=10, stage="x", reserve_usd=bad)


# ── stage-1 typing on the local model (flag, default OFF) ─────────────────────

def _local_ok(text):
    return {"ok": True, "text": text, "status": "OK", "served_model": "qwen2.5-7b-q4"}


def test_default_provider_never_touches_the_local_model(tmp_path):
    m = WD.Meter(1.0, llm=lambda *a, **k: _ok(json.dumps(GOOD)),
                 local_llm=lambda *a, **k: pytest.fail("local must stay off by default"))
    ex = WD.extract_items([_item()], m, cache={}, stage_cap=1.0, workers=1,
                          cache_file=tmp_path / "c.jsonl")
    assert ex["extract_provider"] == "deepseek" and ex["extracted"] == 1
    assert ex["rows"][0]["extract_model"].startswith("deepseek:")


def test_local_typing_replaces_the_paid_call_and_costs_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(WD._cfg, "WORLD_DIGEST_EXTRACT_PROVIDER", "local")
    m = WD.Meter(1.0, llm=lambda *a, **k: pytest.fail("DeepSeek must not be called"),
                 local_llm=lambda *a, **k: _local_ok(json.dumps(GOOD)))
    ex = WD.extract_items([_item()], m, cache={}, stage_cap=1.0, workers=1,
                          cache_file=tmp_path / "c.jsonl")
    assert ex["extract_provider"] == "local" and ex["extracted"] == 1
    assert ex["rows"][0]["extract_model"] == "local:qwen2.5-7b-q4"
    assert m.spent == 0 and m.calls == 0 and m.local_calls == 1
    # cached: the next run re-types nothing on either provider
    again = WD.extract_items([_item()], WD.Meter(1.0, llm=lambda *a, **k: pytest.fail("cached"),
                                                 local_llm=lambda *a, **k: pytest.fail("cached")),
                             cache=WD.read_cache(tmp_path / "c.jsonl"), stage_cap=1.0, workers=1,
                             cache_file=tmp_path / "c.jsonl")
    assert again["cache_hits"] == 1


@pytest.mark.parametrize("local_reply", [
    {"ok": False, "status": "LOCAL_UNAVAILABLE", "text": None},   # server not up
    _local_ok("not json at all"),                                  # answered, did not type
])
def test_a_local_miss_falls_back_to_deepseek_for_that_item(tmp_path, monkeypatch, local_reply):
    monkeypatch.setattr(WD._cfg, "WORLD_DIGEST_EXTRACT_PROVIDER", "local")
    paid = []
    m = WD.Meter(1.0, llm=lambda *a, **k: paid.append(1) or _ok(json.dumps(GOOD)),
                 local_llm=lambda *a, **k: local_reply)
    ex = WD.extract_items([_item()], m, cache={}, stage_cap=1.0, workers=1,
                          cache_file=tmp_path / "c.jsonl")
    assert paid == [1] and ex["extracted"] == 1 and ex["local_fallback_calls"] == 1
    assert ex["rows"][0]["extract_model"].startswith("deepseek:")


def test_a_headline_batch_the_local_model_mostly_fails_is_retyped_by_deepseek(tmp_path, monkeypatch):
    monkeypatch.setattr(WD._cfg, "WORLD_DIGEST_EXTRACT_PROVIDER", "local")
    hs = [_item(item_id=f"h{k}", kind="headline", url=f"https://x.test/{k}", title=f"headline {k}",
                text="") for k in range(5)]
    one_row = json.dumps({"rows": [{"i": 0, "topic": "Fed holds", "event_type": "central_bank"}]})
    all_rows = json.dumps({"rows": [{"i": k, "topic": f"t{k}", "event_type": "other"} for k in range(5)]})
    paid = []
    m = WD.Meter(1.0, llm=lambda *a, **k: paid.append(1) or _ok(all_rows),
                 local_llm=lambda *a, **k: _local_ok(one_row))
    ex = WD.extract_items(hs, m, cache={}, stage_cap=1.0, workers=1, cache_file=tmp_path / "c.jsonl")
    assert paid == [1] and ex["extracted"] == 5                      # 1/5 < 80% -> DeepSeek
    m2 = WD.Meter(1.0, llm=lambda *a, **k: pytest.fail("80% typed locally is accepted"),
                  local_llm=lambda *a, **k: _local_ok(all_rows))
    ex2 = WD.extract_items(hs, m2, cache={}, stage_cap=1.0, workers=1, cache_file=tmp_path / "d.jsonl")
    assert ex2["extracted"] == 5 and ex2["local_typed_calls"] == 1


def test_an_unknown_provider_is_refused(monkeypatch):
    monkeypatch.setattr(WD._cfg, "WORLD_DIGEST_EXTRACT_PROVIDER", "nvidia")
    with pytest.raises(ValueError, match="WORLD_DIGEST_EXTRACT_PROVIDER"):
        WD.extract_items([_item()], WD.Meter(1.0), cache={}, stage_cap=1.0, workers=1)


def test_the_default_local_path_is_llm_analyzer_local(monkeypatch):
    from backend.services import llm_analyzer as LA
    seen = {}

    def fake_call_named(provider, system, user, **kw):
        seen.update(provider=provider, **kw)
        return {"ok": False, "status": "LOCAL_UNAVAILABLE", "text": None}
    monkeypatch.setattr(LA, "call_named", fake_call_named)
    assert WD.Meter(1.0).call_local("s", "u", purpose="world_digest_extract_local", max_tokens=600) is None
    assert seen["provider"] == "local" and seen["ensure_reason"] == "world_digest_extract_local"
