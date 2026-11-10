"""A paid DeepSeek reply is never discarded because the envelope file was busy.

2026-11-10 16:33:40Z, `world_digest_synth`: DeepSeek answered in 10.3 s, then
`settle()`'s `os.replace` of `deepseek_local.json` raised `PermissionError
[WinError 5]` (another handle held the target), `settle` re-raised, and the paid
reply was thrown away -- the night's biggest theme got 0 implications. These
pin: the settle write is retried with backoff under the lock; if it still cannot
write, the reply is KEPT and the settlement goes to a sidecar that the next
`reserve()` reconciles; spend is never under-counted. Offline; tmp envelopes.
"""
import json
from types import SimpleNamespace as NS

import pytest

from backend import config as C
from backend.services import disk_guard as DG
from backend.services import provider_budget as PB

REAL_WRITE = DG.atomic_write_json


@pytest.fixture
def month_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("AEGIS_DEEPSEEK_BUDGET_PATH", raising=False)
    monkeypatch.setattr(PB, "_default_dir", lambda: tmp_path)
    monkeypatch.setattr(C, "DEEPSEEK_MONTHLY_CAP_USD", 15.0)
    monkeypatch.setattr(PB, "_sleep", lambda s: None)
    return tmp_path


def _reserve(**kw):
    return PB.reserve("system", "user", 100, model="deepseek-chat",
                      base_url="https://api.deepseek.com", purpose="fixture", **kw)


def _resp(out=10, model="deepseek-flash"):
    return NS(model=model, usage=NS(prompt_tokens=20, completion_tokens=out,
                                    prompt_cache_hit_tokens=0))


def _busy_envelope(monkeypatch, times):
    """`atomic_write_json` on the envelope raises WinError 5 `times` times."""
    real = DG.atomic_write_json
    state = {"left": times, "calls": 0}

    def fake(path, obj, **kw):
        if str(path).endswith("deepseek_local.json"):
            state["calls"] += 1
            if state["left"] is None or state["left"] > 0:
                if state["left"] is not None:
                    state["left"] -= 1
                raise PermissionError(13, "[WinError 5] Access is denied", str(path))
        return real(path, obj, **kw)
    monkeypatch.setattr(DG, "atomic_write_json", fake)
    return state


def _env(d):
    return json.loads((d / "deepseek_local.json").read_text(encoding="utf-8"))


def test_settle_retries_a_busy_envelope_and_settles(month_dir, monkeypatch):
    t = _reserve()
    st = _busy_envelope(monkeypatch, times=2)
    acc = PB.settle(t, _resp())
    assert acc["billing_status"] == "SETTLED_PEAK_ESTIMATE" and st["calls"] == 3
    assert _env(month_dir)["calls"][t["id"]]["status"] == "SETTLED_PEAK_ESTIMATE"
    assert not PB.sidecar_path(month_dir / "deepseek_local.json").exists()


def test_settle_that_cannot_write_keeps_the_reply_and_defers_to_a_sidecar(month_dir, monkeypatch):
    t = _reserve()
    reserved = _env(month_dir)["calls"][t["id"]]["held_units"]
    _busy_envelope(monkeypatch, times=None)                  # never writable
    acc = PB.settle(t, _resp())                              # does NOT raise
    assert acc["billing_status"] == PB.DEFERRED_STATUS
    assert acc["cost_usd"] is not None and acc["cost_usd"] > 0
    # the envelope still HOLDS the full reservation: spend is over-, never under-counted
    rec = _env(month_dir)["calls"][t["id"]]
    assert rec["status"] == "RESERVED_UNKNOWN" and rec["held_units"] == reserved
    assert rec["held_units"] >= PB._units(acc["cost_usd"])
    side = PB.sidecar_path(month_dir / "deepseek_local.json")
    lines = [json.loads(x) for x in side.read_text(encoding="utf-8").splitlines()]
    assert [x["reservation_id"] for x in lines] == [t["id"]]


def test_next_reserve_reconciles_the_sidecar(month_dir, monkeypatch):
    t = _reserve()
    _busy_envelope(monkeypatch, times=None)
    acc = PB.settle(t, _resp())
    monkeypatch.undo()                                       # the envelope is free again
    monkeypatch.setattr(PB, "_default_dir", lambda: month_dir)
    monkeypatch.setattr(C, "DEEPSEEK_MONTHLY_CAP_USD", 15.0)
    t2 = _reserve()
    s = _env(month_dir)
    rec = s["calls"][t["id"]]
    assert rec["status"] == "SETTLED_PEAK_ESTIMATE" and rec["reconciled_from_sidecar"] is True
    assert rec["held_units"] == PB._units(acc["cost_usd"])
    assert t2["id"] in s["calls"]
    assert not PB.sidecar_path(month_dir / "deepseek_local.json").exists()


def test_a_deferred_block_still_blocks_after_reconciliation(month_dir, monkeypatch):
    t = _reserve()
    _busy_envelope(monkeypatch, times=None)
    PB.settle(t, _resp(model="deepseek-mystery"))           # unknown served model -> block
    monkeypatch.undo()
    monkeypatch.setattr(PB, "_default_dir", lambda: month_dir)
    monkeypatch.setattr(C, "DEEPSEEK_MONTHLY_CAP_USD", 15.0)
    with pytest.raises(PB.BudgetRefused, match="BLOCKED"):
        _reserve()
    assert _env(month_dir)["blocked"] == "unknown returned model"


def test_attempt_returns_the_paid_reply_when_the_envelope_stays_busy(month_dir, monkeypatch):
    body = {"model": "deepseek-chat", "max_tokens": 100,
            "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]}
    PB.reserve("x", "y", 10, model="deepseek-chat", base_url="https://api.deepseek.com",
               purpose="create-envelope")
    _busy_envelope(monkeypatch, times=None)
    resp = _resp()
    # reserve's own write is also refused while busy: nothing is dispatched, nothing paid
    with pytest.raises(PermissionError):
        PB.attempt(body, base_url="https://api.deepseek.com", purpose="p", send=lambda: resp)
    sent = []
    real = REAL_WRITE
    calls = {"n": 0}

    def busy_after_reserve(path, obj, **kw):
        if str(path).endswith("deepseek_local.json"):
            calls["n"] += 1
            if calls["n"] > 1:                               # reserve ok, settle busy
                raise PermissionError(13, "[WinError 5] Access is denied", str(path))
        return real(path, obj, **kw)
    monkeypatch.setattr(DG, "atomic_write_json", busy_after_reserve)
    out, acc = PB.attempt(body, base_url="https://api.deepseek.com", purpose="p",
                          send=lambda: sent.append(1) or resp)
    assert out is resp and sent == [1] and acc["billing_status"] == PB.DEFERRED_STATUS
