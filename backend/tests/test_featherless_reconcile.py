"""CH-04b follow-up (S66): an error reply is not an unknown model, and a block has an exit.

2026-11-12: one 2xx reply without a `model` field blocked the Featherless
envelope as "unknown returned model"; nothing could clear it. Pinned here:

  * each reply class gets its status, its money treatment and its block
    behaviour (no response / HTTP error / error body / different model /
    missing model / missing usage);
  * the missing-model RATE rule: one malformed reply never blocks, a run of them does;
  * the http status and the error class reach the envelope row;
  * the attended reconcile clears a block only with evidence and only when the
    envelope holds at least the provider-observed spend; it refuses, red, otherwise;
    dead-pid stale reservations are settled at FULL reservation, live ones left alone;
    `--dry-run` writes nothing;
  * the balance reader sends the key only to the official host, never returns it.

Offline: stubbed HTTP (`opener`), tmp envelopes, injected clocks and pid checks.
"""
from __future__ import annotations

import io
import json
from datetime import timedelta
from types import SimpleNamespace

import pytest

from backend import config as C
from backend.services import provider_budget as PB

MODEL = "Qwen/Qwen3-30B-A3B-Instruct-2507"


@pytest.fixture
def envelope(tmp_path, monkeypatch):
    p = tmp_path / "featherless_local.json"
    monkeypatch.setenv("AEGIS_FEATHERLESS_BUDGET_PATH", str(p))
    monkeypatch.setattr(C, "FEATHERLESS_MONTHLY_CAP_USD", 25.0)
    monkeypatch.setattr(C, "FEATHERLESS_LIFETIME_CAP_USD", 75.0)
    return p


def _body(model=MODEL, max_tokens=600):
    return {"model": model, "max_tokens": max_tokens, "temperature": 0.2,
            "messages": [{"role": "system", "content": "sys"}, {"role": "user", "content": "user"}]}


def _resp(model=MODEL, ti=1500, to=200, cost=None):
    usage = {"prompt_tokens": ti, "completion_tokens": to}
    if cost is not None:
        usage["cost"] = cost
    return SimpleNamespace(model=model, usage=SimpleNamespace(**usage),
                           choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))])


def _never():
    pytest.fail("nothing may be sent when the envelope refuses")


def _rows(p):
    return json.loads(p.read_text())["calls"]


def _only_row(p):
    rows = _rows(p)
    assert len(rows) == 1
    return next(iter(rows.values()))


def _raise(exc):
    def send():
        raise exc
    return send


# ── item 1/2: the reply classes ──────────────────────────────────────────────

def test_a_reply_object_built_from_an_error_body_is_not_billed_and_does_not_block(envelope):
    """What the openai SDK hands back for a 2xx error body: model/usage/choices None,
    the error in the extras. Featherless bills successful requests only."""
    from openai.types.chat import ChatCompletion
    reply = ChatCompletion.construct(**{"error": {"message": "model busy", "type": "overloaded"}})
    _, acct = PB.featherless_attempt(_body(), purpose="t", send=lambda: reply)
    assert acct["billing_status"] == "UNBILLED_HTTP_REFUSAL" and acct["reply_class"] == "NOT_BILLED_ERROR"
    assert acct["budget_charge_usd"] == 0
    r = _only_row(envelope)
    assert r["held_units"] == 0 and r["http_status"] == 200
    assert r["error_class"] == "payload_error:overloaded" and "error" in r["reply_keys"]
    assert "model busy" not in envelope.read_text()                 # a class, never the message text
    assert PB.featherless_status_line().startswith("FEATHERLESS BUDGET OK")


def test_a_dict_error_body_is_not_billed(envelope):
    _, acct = PB.featherless_attempt(_body(), purpose="t", send=lambda: {"error": {"code": 503}})
    assert acct["reply_class"] == "NOT_BILLED_ERROR" and acct["budget_charge_usd"] == 0
    assert _only_row(envelope)["error_class"] == "payload_error:503"


def test_no_response_keeps_the_full_reservation_without_a_block_and_names_the_exception(envelope):
    class APITimeoutError(Exception):
        pass
    with pytest.raises(APITimeoutError) as ei:
        PB.featherless_attempt(_body(), purpose="t", send=_raise(APITimeoutError()))
    acct = ei.value.shared_budget_accounting
    assert acct["billing_status"] == "BILLING_UNKNOWN" and acct["reply_class"] == "NO_RESPONSE"
    r = _only_row(envelope)
    assert r["held_units"] == r["reserved_units"] > 0
    assert r["http_status"] is None and r["error_class"] == "APITimeoutError"
    assert not json.loads(envelope.read_text())["blocked"]


def test_an_http_error_status_is_released_to_zero_and_recorded(envelope):
    class RateLimitError(Exception):
        status_code = 429
    with pytest.raises(RateLimitError) as ei:
        PB.featherless_attempt(_body(), purpose="t", send=_raise(RateLimitError()))
    acct = ei.value.shared_budget_accounting
    assert acct["billing_status"] == "UNBILLED_HTTP_REFUSAL" and acct["reply_class"] == "HTTP_ERROR"
    r = _only_row(envelope)
    assert r["held_units"] == 0 and r["http_status"] == 429 and r["error_class"] == "RateLimitError"
    assert not json.loads(envelope.read_text())["blocked"]


def test_a_status_carried_on_the_exception_response_is_read_too(envelope):
    class APIStatusError(Exception):
        response = SimpleNamespace(status_code=503)
    with pytest.raises(APIStatusError):
        PB.featherless_attempt(_body(), purpose="t", send=_raise(APIStatusError()))
    assert _only_row(envelope)["http_status"] == 503


def test_a_different_returned_model_still_blocks_and_records_who_set_it(envelope):
    _, acct = PB.featherless_attempt(_body(), purpose="digest", send=lambda: _resp(model="other/model"))
    assert acct["billing_status"] == "BILLING_UNKNOWN" and acct["reply_class"] == "SERVED_MODEL_MISMATCH"
    s = json.loads(envelope.read_text())
    assert s["blocked"] == "unknown returned model"
    rid = next(iter(s["calls"]))
    assert s["blocked_by"]["reservation_id"] == rid and s["blocked_by"]["purpose"] == "digest"
    assert s["calls"][rid]["held_units"] == s["calls"][rid]["reserved_units"]
    with pytest.raises(PB.BudgetRefused, match="BLOCKED"):
        PB.featherless_attempt(_body(), purpose="t", send=_never)


def test_usage_without_a_model_holds_the_reservation_but_one_does_not_block(envelope):
    reply = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=100, completion_tokens=10),
                            choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))])
    _, acct = PB.featherless_attempt(_body(), purpose="t", send=lambda: reply)
    assert acct["billing_status"] == "BILLING_UNKNOWN" and acct["reply_class"] == "SERVED_MODEL_MISSING"
    r = _only_row(envelope)
    assert r["held_units"] == r["reserved_units"] and r["http_status"] == 200
    assert not json.loads(envelope.read_text())["blocked"]
    PB.featherless_attempt(_body(), purpose="t", send=lambda: _resp(ti=500, to=100))  # the next caller is admitted


def test_right_model_unreadable_usage_holds_without_a_block(envelope):
    _, acct = PB.featherless_attempt(_body(), purpose="t", send=lambda: SimpleNamespace(model=MODEL, usage=None))
    assert acct["billing_status"] == "BILLING_UNKNOWN" and acct["reply_class"] == "USAGE_MISSING"
    assert not json.loads(envelope.read_text())["blocked"]


def test_a_success_settles_and_records_200(envelope):
    _, acct = PB.featherless_attempt(_body(), purpose="t", send=lambda: _resp(ti=500, to=100))
    assert acct["billing_status"] == "SETTLED" and acct["reply_class"] == "OK"
    r = _only_row(envelope)
    assert r["http_status"] == 200 and r["reply_class"] == "OK" and r["served_model"] == MODEL


def test_new_rows_stay_readable_by_the_old_status_contract(envelope):
    """An older release clone sharing the file accepts only four statuses."""
    PB.featherless_attempt(_body(), purpose="t", send=lambda: {"error": {"code": 503}})
    PB.featherless_attempt(_body(), purpose="t", send=lambda: SimpleNamespace(usage=None))
    with pytest.raises(OSError):
        PB.featherless_attempt(_body(), purpose="t", send=_raise(OSError()))
    assert {r["status"] for r in _rows(envelope).values()} <= {
        "RESERVED_UNKNOWN", "BILLING_UNKNOWN", "SETTLED", "UNBILLED_HTTP_REFUSAL"}


# ── the missing-model rate rule ──────────────────────────────────────────────

def test_missing_model_blocks_only_past_the_configured_share_of_the_window(envelope, monkeypatch):
    monkeypatch.setattr(C, "FEATHERLESS_MISSING_MODEL_WINDOW", 10)
    monkeypatch.setattr(C, "FEATHERLESS_MISSING_MODEL_MAX_SHARE", 0.20)      # block at > 2 of 10
    missing = lambda: SimpleNamespace(usage=SimpleNamespace(prompt_tokens=5, completion_tokens=5))  # noqa: E731
    for _ in range(2):
        PB.featherless_attempt(_body(), purpose="t", send=missing)
    assert not json.loads(envelope.read_text())["blocked"]                    # 2 of 10: admitted
    PB.featherless_attempt(_body(), purpose="t", send=missing)                # 3 of 10: over the share
    s = json.loads(envelope.read_text())
    assert s["blocked"].startswith("served model missing on 3 of the last 3 calls")
    assert s["blocked_by"]["reply_class"] == "SERVED_MODEL_MISSING"
    with pytest.raises(PB.BudgetRefused, match="BLOCKED"):
        PB.featherless_attempt(_body(), purpose="t", send=_never)


def test_old_missing_replies_age_out_of_the_window(envelope, monkeypatch):
    monkeypatch.setattr(C, "FEATHERLESS_MISSING_MODEL_WINDOW", 4)
    monkeypatch.setattr(C, "FEATHERLESS_MISSING_MODEL_MAX_SHARE", 0.25)      # block at > 1 of 4
    missing = lambda: SimpleNamespace(usage=SimpleNamespace(prompt_tokens=5, completion_tokens=5))  # noqa: E731
    PB.featherless_attempt(_body(), purpose="t", send=missing)
    for _ in range(4):
        PB.featherless_attempt(_body(), purpose="t", send=lambda: _resp(ti=500, to=100))
    PB.featherless_attempt(_body(), purpose="t", send=missing)                # 1 of the last 4
    assert not json.loads(envelope.read_text())["blocked"]


# ── the attended reconcile ───────────────────────────────────────────────────

def _blocked_envelope(p, *, held_usd, now, extra_rows=None):
    s = PB._fl_fresh()
    s["blocked"] = "unknown returned model"
    t = (now - timedelta(hours=3)).isoformat()
    s["calls"]["paid"] = {"held_units": PB._units(held_usd), "reserved_units": PB._units(held_usd),
                          "status": "SETTLED", "started_utc": t, "settled_utc": t, "purpose": "t", "pid": 1}
    s["calls"].update(extra_rows or {})
    p.write_text(json.dumps(s))
    return s


def _reader(balance):
    return lambda: {"balance_usd": balance, "read_utc": "stub", "source": "GET /v1/credits/balance"}


def _no_reader():
    pytest.fail("an operator-entered balance must not call the endpoint")


def test_reconcile_clears_a_block_with_evidence_when_the_envelope_is_conservative(envelope):
    now = PB._utcnow()
    _blocked_envelope(envelope, held_usd=0.16, now=now)
    res = PB.featherless_reconcile(opening_balance_usd=74.50, balance_reader=_reader(74.40),
                                   pid_alive=lambda pid: False, now=now, who="tester")
    assert res["rc"] == 0 and res["decision"] == "CLEAR_BLOCK"
    s = json.loads(envelope.read_text())
    assert s["blocked"] is None and s["opening_balance_usd"] == 74.50
    ev = s["history"][-1]
    assert ev["action"] == "unblock" and ev["who"] == "tester" and ev["previous_block"] == "unknown returned model"
    assert ev["observed_balance_usd"] == 74.40 and ev["observed_spend_usd"] == pytest.approx(0.10)
    assert ev["held_usd"] == pytest.approx(0.16) and ev["why"]
    assert s["balance_observations"][-1]["decision"] == "CLEAR_BLOCK"
    PB.featherless_attempt(_body(), purpose="t", send=lambda: _resp(ti=500, to=100))  # admitted again


def test_reconcile_refuses_when_observed_spend_exceeds_what_is_held(envelope):
    now = PB._utcnow()
    _blocked_envelope(envelope, held_usd=0.05, now=now)
    res = PB.featherless_reconcile(opening_balance_usd=74.50, balance_reader=_reader(74.30),
                                   pid_alive=lambda pid: False, now=now)
    assert res["rc"] == 2 and res["decision"] == "REFUSED"
    assert res["held_usd"] == pytest.approx(0.05) and res["observed_spend_usd"] == pytest.approx(0.20)
    assert any("0.050000 < observed provider spend $0.200000" in ln for ln in res["lines"])
    s = json.loads(envelope.read_text())
    assert s["blocked"] == "unknown returned model" and not s.get("history")
    assert s["balance_observations"][-1]["decision"] == "REFUSED"            # the observation is kept


def test_reconcile_settles_stale_dead_pid_rows_at_full_reservation_and_leaves_live_ones(envelope):
    now = PB._utcnow()
    old = (now - timedelta(hours=4)).isoformat()
    young = (now - timedelta(minutes=2)).isoformat()
    rows = {
        "deadold": {"held_units": PB._units(0.0011), "reserved_units": PB._units(0.0011),
                    "status": "RESERVED_UNKNOWN", "started_utc": old, "pid": 111},
        "liveold": {"held_units": PB._units(0.0011), "reserved_units": PB._units(0.0011),
                    "status": "RESERVED_UNKNOWN", "started_utc": old, "pid": 222},
        "deadyoung": {"held_units": PB._units(0.0011), "reserved_units": PB._units(0.0011),
                      "status": "RESERVED_UNKNOWN", "started_utc": young, "pid": 333},
    }
    _blocked_envelope(envelope, held_usd=0.10, now=now, extra_rows=rows)
    res = PB.featherless_reconcile(opening_balance_usd=74.50, balance_reader=_reader(74.45),
                                   pid_alive=lambda pid: pid == 222, now=now, who="t")
    assert res["rc"] == 0 and res["settled"] == 1 and res["left_alone"] == 2
    calls = json.loads(envelope.read_text())["calls"]
    assert calls["deadold"]["status"] == "BILLING_UNKNOWN"
    assert calls["deadold"]["reply_class"] == "ABANDONED_DEAD_PID"
    assert calls["deadold"]["held_units"] == PB._units(0.0011)              # FULL reservation, never less
    assert calls["liveold"]["status"] == "RESERVED_UNKNOWN"
    assert calls["deadyoung"]["status"] == "RESERVED_UNKNOWN"


def test_dry_run_reads_the_balance_and_writes_nothing(envelope):
    now = PB._utcnow()
    rows = {"deadold": {"held_units": 5, "reserved_units": 5, "status": "RESERVED_UNKNOWN",
                        "started_utc": (now - timedelta(hours=4)).isoformat(), "pid": 9}}
    _blocked_envelope(envelope, held_usd=0.16, now=now, extra_rows=rows)
    before = envelope.read_bytes()
    files_before = sorted(x.name for x in envelope.parent.iterdir())
    asked = []
    res = PB.featherless_reconcile(dry_run=True, opening_balance_usd=74.50,
                                   balance_reader=lambda: asked.append(1) or _reader(74.40)(),
                                   pid_alive=lambda pid: False, now=now)
    assert asked == [1] and res["rc"] == 0 and res["decision"] == "CLEAR_BLOCK" and res["dry_run"]
    assert envelope.read_bytes() == before
    assert sorted(x.name for x in envelope.parent.iterdir()) == files_before


def test_the_stored_opening_balance_is_the_baseline_and_is_never_rewritten(envelope):
    now = PB._utcnow()
    _blocked_envelope(envelope, held_usd=0.16, now=now)
    assert PB.featherless_reconcile(opening_balance_usd=74.50, balance_reader=_reader(74.40),
                                    pid_alive=lambda pid: False, now=now)["rc"] == 0
    # the next one needs no --opening-balance ...
    res = PB.featherless_reconcile(balance_reader=_reader(74.39), pid_alive=lambda pid: False, now=now)
    assert res["rc"] == 0 and res["decision"] == "NO_BLOCK"
    assert len(json.loads(envelope.read_text())["balance_observations"]) == 2
    # ... and a different one is refused
    res = PB.featherless_reconcile(opening_balance_usd=80.0, balance_reader=_reader(74.39),
                                   pid_alive=lambda pid: False, now=now)
    assert res["rc"] == 2 and "differs" in res["reason"]


@pytest.mark.parametrize("kw,why", [
    ({}, "no opening balance"),
    ({"opening_balance_usd": 74.0}, "ABOVE the opening"),
    ({"opening_balance_usd": 74.5, "observed_balance_usd": 74.4}, "needs --evidence"),
])
def test_reconcile_refusals_are_red_and_change_nothing(envelope, kw, why):
    now = PB._utcnow()
    _blocked_envelope(envelope, held_usd=0.16, now=now)
    before = envelope.read_bytes()
    reader = _no_reader if "observed_balance_usd" in kw else _reader(74.40)
    res = PB.featherless_reconcile(balance_reader=reader, pid_alive=lambda pid: False, now=now, **kw)
    assert res["rc"] == 2 and why in res["reason"]
    assert envelope.read_bytes() == before


def test_an_operator_read_balance_with_evidence_can_clear_and_is_recorded(envelope):
    now = PB._utcnow()
    _blocked_envelope(envelope, held_usd=0.16, now=now)
    res = PB.featherless_reconcile(opening_balance_usd=74.5, observed_balance_usd=74.42,
                                   evidence="dashboard read by the owner", balance_reader=_no_reader,
                                   pid_alive=lambda pid: False, now=now, who="t")
    assert res["rc"] == 0
    ev = json.loads(envelope.read_text())["history"][-1]
    assert ev["balance_source"] == "operator" and "dashboard read by the owner" in ev["why"]


def test_an_unreadable_balance_refuses_red(envelope):
    now = PB._utcnow()
    _blocked_envelope(envelope, held_usd=0.16, now=now)

    def broken():
        raise PB.FeatherlessBalanceUnavailable("stub outage")
    res = PB.featherless_reconcile(opening_balance_usd=74.5, balance_reader=broken, now=now,
                                   pid_alive=lambda pid: False)
    assert res["rc"] == 2 and "balance unavailable" in res["reason"]


# ── the balance reader (stubbed HTTP) ────────────────────────────────────────

class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_the_balance_reader_parses_usd_and_never_returns_the_key():
    seen = {}

    def opener(req, timeout):
        seen.update(url=req.full_url, auth=req.get_header("Authorization"), timeout=timeout)
        return _Resp(json.dumps({"balance": "74.41", "currency": "USD"}).encode())
    out = PB.featherless_read_balance(opener=opener, api_key="fl-test-not-a-real-key")
    assert out["balance_usd"] == pytest.approx(74.41)
    assert seen["url"].startswith("https://api.featherless.ai/") and seen["auth"].startswith("Bearer ")
    assert "fl-test-not-a-real-key" not in json.dumps(out)


def test_the_balance_reader_refuses_a_foreign_host_a_missing_key_and_an_unknown_shape(monkeypatch):
    def never(req, timeout):
        pytest.fail("the key must not be sent")
    with pytest.raises(PB.FeatherlessBalanceUnavailable, match="official"):
        PB.featherless_read_balance(opener=never, url="https://evil.example/credits", api_key="k")
    monkeypatch.delenv(C.FEATHERLESS_KEY_ENV, raising=False)
    with pytest.raises(PB.FeatherlessBalanceUnavailable, match="not set"):
        PB.featherless_read_balance(opener=never)
    with pytest.raises(PB.FeatherlessBalanceUnavailable, match="fields"):
        PB.featherless_read_balance(opener=lambda r, timeout: _Resp(b'{"plan": "x"}'), api_key="k")


# ── the CLI ──────────────────────────────────────────────────────────────────

def test_cli_status_prints_counts_block_and_who_set_it(envelope, capsys):
    PB.featherless_attempt(_body(), purpose="digest", send=lambda: _resp(model="other/model"))
    assert PB.main(["status", "--provider", "featherless"]) == 2
    out = capsys.readouterr().out
    assert "FEATHERLESS BUDGET REFUSED (BLOCKED)" in out
    assert "by reply class: {'SERVED_MODEL_MISMATCH': 1}" in out
    assert "blocked: unknown returned model" in out and "blocked by: {'reservation_id'" in out


def test_cli_reconcile_dry_run_writes_nothing(envelope, monkeypatch, capsys):
    now = PB._utcnow()
    _blocked_envelope(envelope, held_usd=0.16, now=now)
    before = envelope.read_bytes()
    monkeypatch.setattr(PB, "featherless_read_balance", _reader(74.40))
    rc = PB.main(["reconcile", "--provider", "featherless", "--dry-run", "--opening-balance", "74.5"])
    assert rc == 0 and envelope.read_bytes() == before
    assert "[dry-run] would clear the block" in capsys.readouterr().out


def test_cli_deepseek_reconcile_refuses_featherless_flags(capsys):
    assert PB.main(["reconcile", "--dry-run"]) == 2
    assert "belong to `reconcile --provider featherless`" in capsys.readouterr().out
