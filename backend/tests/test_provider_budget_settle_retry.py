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


# -- review 3 (S65) on #97: the reviewer's three probes, now asserting the fix --
# Invariant every test below checks: the spend a reader sees is never below the
# cost of a reply that was paid for.

BODY = {"model": "deepseek-chat", "max_tokens": 100,
        "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]}
ENV = "deepseek_local.json"


def _seen_held(month_dir):
    """What every reader sees: preflight and snapshot agree."""
    a = PB._held(PB.preflight_snapshot())
    b = PB._units(PB.snapshot()["held_usd"])
    assert a == b
    return a


def _cost_units(resp):
    u = resp.usage
    return PB._units((u.prompt_tokens * PB.PRICE["in"]
                      + u.completion_tokens * PB.PRICE["out"]) / 1e6)


def test_probe1_lock_timeout_at_settle_keeps_the_paid_reply(month_dir, monkeypatch):
    real = PB._lock
    n = {"k": 0}

    def lk(p):
        n["k"] += 1
        if n["k"] >= 2:                                   # reserve ok, settle times out
            raise DG.FileLockTimeout("held by another process")
        return real(p)
    monkeypatch.setattr(PB, "_lock", lk)
    sent, resp = [], _resp()
    out, acc = PB.attempt(BODY, base_url="https://api.deepseek.com", purpose="p",
                          send=lambda: sent.append(1) or resp)
    assert out is resp and sent == [1]                    # paid, and KEPT
    assert acc["billing_status"] == PB.DEFERRED_STATUS
    assert acc["settle_error"] == "FileLockTimeout"
    rec = _env(month_dir)["calls"][acc["reservation_id"]]
    assert rec["status"] == "RESERVED_UNKNOWN"            # full reservation still held on disk
    assert rec["held_units"] >= _cost_units(resp)
    monkeypatch.setattr(PB, "_lock", real)
    assert _seen_held(month_dir) >= _cost_units(resp)
    _reserve()                                            # the next reserve reconciles
    rec = _env(month_dir)["calls"][acc["reservation_id"]]
    assert rec["status"] == "SETTLED_PEAK_ESTIMATE" and rec["held_units"] == _cost_units(resp)
    assert not PB.sidecar_path(month_dir / ENV).exists()


def test_load_failure_at_settle_keeps_the_paid_reply(month_dir, monkeypatch):
    real = PB._load
    n = {"k": 0}

    def ld(p):
        n["k"] += 1
        if n["k"] >= 2:
            raise PB.BudgetRefused("shared envelope absent/unreadable")
        return real(p)
    monkeypatch.setattr(PB, "_load", ld)
    resp = _resp()
    out, acc = PB.attempt(BODY, base_url="https://api.deepseek.com", purpose="p",
                          send=lambda: resp)
    assert out is resp and acc["billing_status"] == PB.DEFERRED_STATUS
    assert PB._units(acc["budget_charge_usd"]) >= _cost_units(resp)
    monkeypatch.setattr(PB, "_load", real)
    assert _seen_held(month_dir) >= _cost_units(resp)


def test_probe2_status_and_preflight_see_a_block_pending_in_the_sidecar(month_dir, monkeypatch):
    t = _reserve()
    _busy_envelope(monkeypatch, times=None)
    PB.settle(t, _resp(model="deepseek-mystery"))         # block deferred to the sidecar
    monkeypatch.setattr(DG, "atomic_write_json", REAL_WRITE)
    line = PB.status_line()
    assert line.startswith("DEEPSEEK BUDGET REFUSED (BLOCKED)"), line
    assert "1 deferred settlement(s) pending in the sidecar" in line
    assert PB.preflight_snapshot()["blocked"] == "unknown returned model"
    from scripts import world_digest as WD
    assert WD._shared_budget_refusal() == "SHARED_ENVELOPE_BLOCKED"
    assert PB.main(["status"]) == 2
    # no reader wrote anything
    assert _env(month_dir).get("blocked") is None
    assert PB.sidecar_path(month_dir / ENV).exists()


def test_readers_see_a_settled_cost_above_its_reservation(month_dir, monkeypatch):
    """O4: cost > reservation (itself a block) while the write is busy."""
    t = _reserve()
    reserved = _env(month_dir)["calls"][t["id"]]["held_units"]
    big = _resp(out=5000)                                 # far above max_tokens=100
    assert _cost_units(big) > reserved
    _busy_envelope(monkeypatch, times=None)
    PB.settle(t, big)
    monkeypatch.setattr(DG, "atomic_write_json", REAL_WRITE)
    assert _seen_held(month_dir) >= _cost_units(big)
    assert PB.preflight_snapshot()["blocked"] == "provider usage exceeded request reservation bound"


def test_probe3_partial_sidecar_line_does_not_eat_the_next_block(month_dir, monkeypatch):
    t = _reserve()
    sp = PB.sidecar_path(month_dir / ENV)
    sp.write_text('{"reservation_id": "zz", "sta', encoding="utf-8")    # crash mid-line
    _busy_envelope(monkeypatch, times=None)
    PB.settle(t, _resp(model="deepseek-mystery"))
    monkeypatch.setattr(DG, "atomic_write_json", REAL_WRITE)
    with pytest.raises(PB.BudgetRefused, match="BLOCKED"):
        _reserve()
    s = _env(month_dir)
    assert s["blocked"] == "unknown returned model"
    assert [o.get("unparsed", "")[:16] for o in s["sidecar_orphans"]] == ['{"reservation_id']


def test_unwritable_sidecar_still_blocks_this_process(month_dir, monkeypatch):
    """O2: envelope AND sidecar unwritable: the reply is kept, the block is
    latched in-process and persisted by this process's next reserve."""
    t = _reserve()
    _busy_envelope(monkeypatch, times=None)

    def no_sidecar(p, row):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(PB, "_append_sidecar", no_sidecar)
    acc = PB.settle(t, _resp(model="deepseek-mystery"))
    assert acc["billing_status"] == "SETTLEMENT_FAILED_RESERVATION_RETAINED"
    monkeypatch.setattr(DG, "atomic_write_json", REAL_WRITE)
    assert PB.status_line().startswith("DEEPSEEK BUDGET REFUSED (BLOCKED)")
    with pytest.raises(PB.BudgetRefused, match="BLOCKED"):
        _reserve()
    assert _env(month_dir)["blocked"] == "unknown returned model"


def test_orphan_lines_are_not_re_appended_while_the_sidecar_cannot_be_cleared(
        month_dir, monkeypatch):
    """O3."""
    _reserve()
    sp = PB.sidecar_path(month_dir / ENV)
    sp.write_text(json.dumps({"reservation_id": "not-here", "status": "BILLING_UNKNOWN"})
                  + "\n", encoding="utf-8")
    monkeypatch.setattr(PB, "_consume_sidecar", lambda p, raw: None)   # never cleared
    _reserve()
    _reserve()
    _reserve()
    assert len(_env(month_dir)["sidecar_orphans"]) == 1


def test_reconcile_recomputes_cost_from_tokens_not_held_units(month_dir):
    """O5: a parseable line claiming held_units 0 cannot release the reservation."""
    t = _reserve()
    reserved = _env(month_dir)["calls"][t["id"]]["held_units"]
    sp = PB.sidecar_path(month_dir / ENV)
    row = {"reservation_id": t["id"], "status": "SETTLED_PEAK_ESTIMATE", "held_units": 0,
           "served_model": "deepseek-flash", "settled_utc": "2026-01-01T00:00:00+00:00"}
    sp.write_text(json.dumps(row) + "\n", encoding="utf-8")
    _reserve()
    rec = _env(month_dir)["calls"][t["id"]]
    assert rec["status"] == "BILLING_UNKNOWN" and rec["held_units"] == reserved   # no tokens
    t2 = _reserve()
    sp.write_text(json.dumps({**row, "reservation_id": t2["id"], "ti": 20, "to": 10,
                              "cached": 0}) + "\n", encoding="utf-8")
    _reserve()
    assert _env(month_dir)["calls"][t2["id"]]["held_units"] == _cost_units(_resp())


def test_stale_unreconciled_sidecar_is_a_degraded_status_line(month_dir, monkeypatch):
    from datetime import datetime, timedelta, timezone
    t = _reserve()
    _busy_envelope(monkeypatch, times=None)
    PB.settle(t, _resp())
    monkeypatch.setattr(DG, "atomic_write_json", REAL_WRITE)
    line = PB.status_line()
    assert line.startswith("DEEPSEEK BUDGET OK") and "pending in the sidecar" in line
    lim = float(C.DEEPSEEK_SIDECAR_STALE_HOURS)
    later = datetime.now(timezone.utc) + timedelta(hours=lim + 1)
    monkeypatch.setattr(PB, "_utcnow", lambda: later)
    line = PB.status_line()
    assert line.startswith("DEEPSEEK BUDGET DEGRADED (SIDECAR_STALE)"), line
    assert PB.main(["reconcile"]) == 0
    assert PB.status_line().startswith("DEEPSEEK BUDGET OK")
    assert not PB.sidecar_path(month_dir / ENV).exists()
