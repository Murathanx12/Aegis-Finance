"""CH-04b follow-up (S66): an error reply is not an unknown model, and a block has an exit.

2026-11-12: one 2xx reply without a `model` field blocked the Featherless
envelope as "unknown returned model"; nothing could clear it. Pinned here
(revised after the PR #131 adversarial review):

  * each reply class gets its status, its money treatment and its block
    behaviour; money is released to $0 ONLY on an OBSERVED 4xx/5xx that is not
    a timeout/gateway status; an empty 2xx keeps its full reservation;
  * the REAL http status is read from the client's raw response, never assumed;
    the error excerpt is short, redacted, and never quotes the prompt;
  * the missing-model rule: more than N in the window OR more than M in a row;
  * the attended reconcile clears only a model-identity block (or an exact
    `--clear-reason` with evidence), only when held >= observed spend; a refused
    run writes ONLY a history row; the opening is stored only on success;
    `rebaseline` (top-up / typo) records old/new/who/why and never clears;
    an operator-read balance needs a terminal; a concurrent reservation waits on
    the file lock and is not lost;
  * the balance reader takes only a named USD field, refuses bare numbers,
    unknown shapes and implausible values, and never follows a redirect.

Offline: stubbed HTTP (`opener`), tmp envelopes, injected clocks and pid checks.
"""
from __future__ import annotations

import io
import json
import threading
import time
from datetime import timedelta
from types import SimpleNamespace

import pytest

from backend import config as C
from backend.services import llm_analyzer as LA
from backend.services import provider_budget as PB

MODEL = "Qwen/Qwen3-30B-A3B-Instruct-2507"


@pytest.fixture
def envelope(tmp_path, monkeypatch):
    p = tmp_path / "featherless_local.json"
    monkeypatch.setenv("AEGIS_FEATHERLESS_BUDGET_PATH", str(p))
    monkeypatch.setattr(C, "FEATHERLESS_MONTHLY_CAP_USD", 25.0)
    monkeypatch.setattr(C, "FEATHERLESS_LIFETIME_CAP_USD", 75.0)
    return p


def _body(model=MODEL, max_tokens=600, user="user"):
    return {"model": model, "max_tokens": max_tokens, "temperature": 0.2,
            "messages": [{"role": "system", "content": "sys"}, {"role": "user", "content": user}]}


def _resp(model=MODEL, ti=500, to=100, cost=None):
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


def _state(p):
    return json.loads(p.read_text())


def _raise(exc):
    def send():
        raise exc
    return send


def _status_error(code, body=None, name="APIStatusError"):
    return type(name, (Exception,), {"status_code": code, "body": body})()


# ── reply classes ────────────────────────────────────────────────────────────

def test_an_error_body_on_a_2xx_is_empty_2xx_held_in_full_not_released(envelope):
    """What the openai SDK hands back for a 2xx error body: model/usage/choices None,
    the error in the extras. We cannot prove it was not billed: hold, do not block."""
    from openai.types.chat import ChatCompletion
    reply = ChatCompletion.construct(**{"error": {"message": "model busy", "type": "overloaded"}})
    _, acct = PB.featherless_attempt(_body(), purpose="t", send=lambda: PB.FeatherlessReply(reply, 200))
    assert acct["billing_status"] == "BILLING_UNKNOWN" and acct["reply_class"] == "EMPTY_2XX"
    r = _only_row(envelope)
    assert r["held_units"] == r["reserved_units"] > 0 and r["http_status"] == 200
    assert "error" in r["reply_keys"]
    assert r["error_excerpt"] == "type=overloaded; msg=model busy"            # tonight's reply would be on file
    assert not _state(envelope)["blocked"]


def test_a_message_only_reply_is_not_released(envelope):
    _, acct = PB.featherless_attempt(_body(), purpose="t", send=lambda: {"message": "nope"})
    assert acct["reply_class"] == "EMPTY_2XX" and acct["budget_charge_usd"] > 0


def test_a_bare_reply_records_the_status_as_unknown_never_200(envelope):
    PB.featherless_attempt(_body(), purpose="t", send=lambda: _resp())
    r = _only_row(envelope)
    assert r["status"] == "SETTLED" and r["reply_class"] == "OK" and r["http_status"] is None


def test_call_named_reads_the_real_status_from_the_raw_response(envelope, monkeypatch):
    class Raw:
        status_code = 201

        def parse(self):
            return _resp()
    comp = SimpleNamespace(create=lambda **kw: pytest.fail("the raw path must be used"),
                           with_raw_response=SimpleNamespace(create=lambda **kw: Raw()))
    monkeypatch.setattr(LA, "_get_featherless_client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=comp)))
    res = LA.call_named("featherless", "s", "u", purpose="t", max_tokens=600)
    assert res["ok"] and res["billing_status"] == "SETTLED"
    assert _only_row(envelope)["http_status"] == 201


def test_no_response_keeps_the_full_reservation_without_a_block_and_names_the_exception(envelope):
    class APITimeoutError(Exception):
        pass
    with pytest.raises(APITimeoutError) as ei:
        PB.featherless_attempt(_body(), purpose="t", send=_raise(APITimeoutError("Request timed out.")))
    acct = ei.value.shared_budget_accounting
    assert acct["billing_status"] == "BILLING_UNKNOWN" and acct["reply_class"] == "NO_RESPONSE"
    r = _only_row(envelope)
    assert r["held_units"] == r["reserved_units"] > 0
    assert r["http_status"] is None and r["error_class"] == "APITimeoutError"
    assert r["error_excerpt"].startswith("APITimeoutError")
    assert not _state(envelope)["blocked"]


@pytest.mark.parametrize("code", [400, 403, 429, 500, 503])
def test_an_observed_http_error_is_released_to_zero(envelope, code):
    with pytest.raises(Exception) as ei:
        PB.featherless_attempt(_body(), purpose="t",
                               send=_raise(_status_error(code, {"error": {"type": "x", "message": "m"}})))
    acct = ei.value.shared_budget_accounting
    assert acct["billing_status"] == "UNBILLED_HTTP_REFUSAL" and acct["reply_class"] == "HTTP_ERROR"
    r = _only_row(envelope)
    assert r["held_units"] == 0 and r["http_status"] == code
    assert r["error_excerpt"] == "APIStatusError; type=x; msg=m"


@pytest.mark.parametrize("code", [408, 499, 502, 504, 524])
def test_a_timeout_or_gateway_status_keeps_the_full_reservation(envelope, code):
    with pytest.raises(Exception) as ei:
        PB.featherless_attempt(_body(), purpose="t", send=_raise(_status_error(code)))
    acct = ei.value.shared_budget_accounting
    assert acct["billing_status"] == "BILLING_UNKNOWN" and acct["reply_class"] == "HTTP_AMBIGUOUS"
    r = _only_row(envelope)
    assert r["held_units"] == r["reserved_units"] > 0 and r["http_status"] == code


def test_the_excerpt_redacts_keys_and_never_quotes_the_prompt(envelope):
    secret = "fl_" + "A" * 40
    prompt = "Type this confidential headline about the merger please"
    err = _status_error(400, {"error": {"message": f"bad key {secret}"}})
    with pytest.raises(Exception):
        PB.featherless_attempt(_body(user=prompt), purpose="t", send=_raise(err))
    err2 = _status_error(400, {"error": {"message": f"echo: {prompt}"}})
    with pytest.raises(Exception):
        PB.featherless_attempt(_body(user=prompt), purpose="t", send=_raise(err2))
    text = envelope.read_text()
    assert secret not in text and "<redacted>" in text
    assert "confidential headline" not in text and "<dropped: quotes the prompt>" in text


def test_a_status_carried_on_the_exception_response_is_read_too(envelope):
    class E(Exception):
        response = SimpleNamespace(status_code=503)
    with pytest.raises(E):
        PB.featherless_attempt(_body(), purpose="t", send=_raise(E()))
    assert _only_row(envelope)["http_status"] == 503


def test_a_different_returned_model_still_blocks_and_records_who_set_it(envelope):
    _, acct = PB.featherless_attempt(_body(), purpose="digest", send=lambda: _resp(model="other/model"))
    assert acct["billing_status"] == "BILLING_UNKNOWN" and acct["reply_class"] == "SERVED_MODEL_MISMATCH"
    s = _state(envelope)
    assert s["blocked"] == "unknown returned model"
    rid = next(iter(s["calls"]))
    assert s["blocked_by"]["reservation_id"] == rid and s["blocked_by"]["purpose"] == "digest"
    with pytest.raises(PB.BudgetRefused, match="BLOCKED"):
        PB.featherless_attempt(_body(), purpose="t", send=_never)


def test_usage_without_a_model_holds_the_reservation_but_one_does_not_block(envelope):
    reply = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=100, completion_tokens=10),
                            choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))])
    _, acct = PB.featherless_attempt(_body(), purpose="t", send=lambda: reply)
    assert acct["billing_status"] == "BILLING_UNKNOWN" and acct["reply_class"] == "SERVED_MODEL_MISSING"
    r = _only_row(envelope)
    assert r["held_units"] == r["reserved_units"]
    assert not _state(envelope)["blocked"]
    PB.featherless_attempt(_body(), purpose="t", send=lambda: _resp())  # the next caller is admitted


def test_right_model_unreadable_usage_holds_without_a_block(envelope):
    _, acct = PB.featherless_attempt(_body(), purpose="t", send=lambda: SimpleNamespace(model=MODEL, usage=None))
    assert acct["billing_status"] == "BILLING_UNKNOWN" and acct["reply_class"] == "USAGE_MISSING"
    assert not _state(envelope)["blocked"]


def test_new_rows_stay_readable_by_the_old_status_contract(envelope):
    """An older release clone sharing the file accepts only four statuses."""
    PB.featherless_attempt(_body(), purpose="t", send=lambda: {"error": {"code": 503}})
    with pytest.raises(Exception):
        PB.featherless_attempt(_body(), purpose="t", send=_raise(_status_error(504)))
    with pytest.raises(OSError):
        PB.featherless_attempt(_body(), purpose="t", send=_raise(OSError()))
    assert {r["status"] for r in _rows(envelope).values()} <= {
        "RESERVED_UNKNOWN", "BILLING_UNKNOWN", "SETTLED", "UNBILLED_HTTP_REFUSAL"}


# ── the missing-model rule ───────────────────────────────────────────────────

def _missing():
    return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=5, completion_tokens=5))


def test_missing_model_blocks_past_n_in_the_window(envelope, monkeypatch):
    monkeypatch.setattr(C, "FEATHERLESS_MISSING_MODEL_WINDOW", 50)
    monkeypatch.setattr(C, "FEATHERLESS_MISSING_MODEL_MAX_IN_WINDOW", 2)
    monkeypatch.setattr(C, "FEATHERLESS_MISSING_MODEL_MAX_CONSECUTIVE", 10)
    for i in range(2):
        PB.featherless_attempt(_body(), purpose="t", send=_missing)
        PB.featherless_attempt(_body(), purpose="t", send=lambda: _resp())
    assert not _state(envelope)["blocked"]                                # 2 of 4: admitted
    PB.featherless_attempt(_body(), purpose="t", send=lambda: {"message": "x"})   # EMPTY_2XX counts too
    s = _state(envelope)
    assert s["blocked"].startswith("served model missing or empty on 3 of the last 5 calls")
    with pytest.raises(PB.BudgetRefused, match="BLOCKED"):
        PB.featherless_attempt(_body(), purpose="t", send=_never)


def test_missing_model_blocks_past_m_consecutive(envelope, monkeypatch):
    monkeypatch.setattr(C, "FEATHERLESS_MISSING_MODEL_MAX_IN_WINDOW", 40)
    monkeypatch.setattr(C, "FEATHERLESS_MISSING_MODEL_MAX_CONSECUTIVE", 3)
    for _ in range(3):
        PB.featherless_attempt(_body(), purpose="t", send=_missing)
    assert not _state(envelope)["blocked"]
    PB.featherless_attempt(_body(), purpose="t", send=_missing)
    assert _state(envelope)["blocked"] == "served model missing or empty on 4 consecutive calls (limit 3)"


def test_the_shipped_rule_blocks_one_in_five(envelope):
    """The review's case: one missing in five ran 400 calls unblocked. Now it stops."""
    blocked_at = None
    for i in range(100):
        send = _missing if i % 5 == 0 else (lambda: _resp())
        PB.featherless_attempt(_body(), purpose="t", send=send)
        if _state(envelope)["blocked"]:
            blocked_at = i + 1
            break
    assert blocked_at is not None and blocked_at <= 5 * (C.FEATHERLESS_MISSING_MODEL_MAX_IN_WINDOW + 1)


# ── status ───────────────────────────────────────────────────────────────────

def test_status_is_red_when_blocked_and_degraded_when_the_unbilled_share_is_high(envelope, capsys, monkeypatch):
    for _ in range(3):
        PB.featherless_attempt(_body(), purpose="t", send=lambda: _resp())
    assert PB.main(["status", "--provider", "featherless"]) == 0
    for _ in range(2):
        with pytest.raises(Exception):
            PB.featherless_attempt(_body(), purpose="t", send=_raise(_status_error(503)))
    capsys.readouterr()
    assert PB.main(["status", "--provider", "featherless"]) == 1                 # 2 of 5 > 20%
    assert "FEATHERLESS BUDGET DEGRADED: 2 of the last 5 calls" in capsys.readouterr().out
    PB.featherless_attempt(_body(), purpose="digest", send=lambda: _resp(model="other/model"))
    assert PB.main(["status", "--provider", "featherless"]) == 2
    out = capsys.readouterr().out
    assert "blocked: unknown returned model" in out and "blocked by: {'reservation_id'" in out
    assert "'SERVED_MODEL_MISMATCH': 1" in out


# ── the attended reconcile ───────────────────────────────────────────────────

def _blocked_envelope(p, *, held_usd, now, extra_rows=None, block="unknown returned model", **top):
    s = PB._fl_fresh()
    s["blocked"] = block
    t = (now - timedelta(hours=3)).isoformat()
    s["calls"]["paid"] = {"held_units": PB._units(held_usd), "reserved_units": PB._units(held_usd),
                          "status": "SETTLED", "started_utc": t, "settled_utc": t, "purpose": "t", "pid": 1}
    s["calls"].update(extra_rows or {})
    s.update(top)
    p.write_text(json.dumps(s))
    return s


def _reader(balance):
    return lambda: {"balance_usd": balance, "read_utc": "stub", "source": "GET /credits/balance"}


def _no_reader():
    pytest.fail("an operator-entered balance must not call the endpoint")


def _without_history(p):
    s = _state(p)
    return {k: v for k, v in s.items() if k != "history"}, s.get("history") or []


def test_reconcile_clears_a_model_block_with_evidence_when_the_envelope_is_conservative(envelope):
    now = PB._utcnow()
    _blocked_envelope(envelope, held_usd=0.16, now=now)
    res = PB.featherless_reconcile(opening_balance_usd=74.50, balance_reader=_reader(74.40),
                                   pid_alive=lambda pid: False, now=now, who="tester")
    assert res["rc"] == 0 and res["decision"] == "CLEAR_BLOCK"
    s = _state(envelope)
    assert s["blocked"] is None and s["opening_balance_usd"] == 74.50 and s["baseline_held_units"] == 0
    ev = s["history"][-1]
    assert ev["action"] == "unblock" and ev["who"] == "tester" and ev["previous_block"] == "unknown returned model"
    assert ev["observed_balance_usd"] == 74.40 and ev["observed_spend_usd"] == pytest.approx(0.10)
    assert ev["held_usd"] == pytest.approx(0.16) and ev["why"] and ev["manual"] is False
    assert s["balance_observations"][-1]["decision"] == "CLEAR_BLOCK"
    PB.featherless_attempt(_body(), purpose="t", send=lambda: _resp())       # admitted again


def test_a_refused_run_writes_only_a_history_row(envelope):
    now = PB._utcnow()
    rows = {"deadold": {"held_units": 5, "reserved_units": 5, "status": "RESERVED_UNKNOWN",
                        "started_utc": (now - timedelta(hours=4)).isoformat(), "pid": 9}}
    _blocked_envelope(envelope, held_usd=0.05, now=now, extra_rows=rows)
    before, _ = _without_history(envelope)
    res = PB.featherless_reconcile(opening_balance_usd=74.50, balance_reader=_reader(74.30),
                                   pid_alive=lambda pid: False, now=now, who="t")
    assert res["rc"] == 2 and res["decision"] == "REFUSED"
    assert res["held_usd"] == pytest.approx(0.05) and res["observed_spend_usd"] == pytest.approx(0.20)
    after, hist = _without_history(envelope)
    assert after == before                                 # no settlement, no observation, no opening
    assert "opening_balance_usd" not in after and after["calls"]["deadold"]["status"] == "RESERVED_UNKNOWN"
    assert len(hist) == 1 and hist[0]["action"] == "reconcile_refused" and "< observed provider spend" in hist[0]["reason"]


def test_a_mistyped_opening_on_a_refused_run_is_not_stored_and_the_retry_works(envelope):
    now = PB._utcnow()
    _blocked_envelope(envelope, held_usd=0.16, now=now)
    res = PB.featherless_reconcile(opening_balance_usd=745.0, balance_reader=_reader(74.40),
                                   pid_alive=lambda pid: False, now=now)
    assert res["rc"] == 2 and "opening_balance_usd" not in _state(envelope)
    res = PB.featherless_reconcile(opening_balance_usd=74.50, balance_reader=_reader(74.40),
                                   pid_alive=lambda pid: False, now=now)
    assert res["rc"] == 0 and res["decision"] == "CLEAR_BLOCK"


def test_reconcile_settles_stale_dead_pid_rows_at_full_reservation_and_leaves_live_ones(envelope):
    now = PB._utcnow()
    old = (now - timedelta(hours=4)).isoformat()
    young = (now - timedelta(minutes=2)).isoformat()
    unit = PB._units(0.0011)
    rows = {k: {"held_units": unit, "reserved_units": unit, "status": "RESERVED_UNKNOWN",
                "started_utc": ts, "pid": pid}
            for k, ts, pid in (("deadold", old, 111), ("liveold", old, 222), ("deadyoung", young, 333))}
    _blocked_envelope(envelope, held_usd=0.10, now=now, extra_rows=rows)
    res = PB.featherless_reconcile(opening_balance_usd=74.50, balance_reader=_reader(74.45),
                                   pid_alive=lambda pid: pid == 222, now=now, who="t")
    assert res["rc"] == 0 and res["settled"] == 1 and res["left_alone"] == 2
    calls = _rows(envelope)
    assert calls["deadold"]["status"] == "BILLING_UNKNOWN"
    assert calls["deadold"]["reply_class"] == "ABANDONED_DEAD_PID"
    assert calls["deadold"]["held_units"] == unit                         # FULL reservation, never less
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
    # a refused dry run writes nothing either
    res = PB.featherless_reconcile(dry_run=True, opening_balance_usd=74.50, balance_reader=_reader(70.0),
                                   pid_alive=lambda pid: False, now=now)
    assert res["rc"] == 2
    assert envelope.read_bytes() == before
    assert sorted(x.name for x in envelope.parent.iterdir()) == files_before


def test_a_non_model_block_needs_the_exact_reason_and_evidence(envelope):
    now = PB._utcnow()
    bound = "provider usage exceeded request reservation bound"
    _blocked_envelope(envelope, held_usd=0.16, now=now, block=bound)
    kw = dict(opening_balance_usd=74.50, balance_reader=_reader(74.40), pid_alive=lambda pid: False, now=now)
    res = PB.featherless_reconcile(**kw)
    assert res["rc"] == 2 and "not a model-identity block" in res["reason"]
    res = PB.featherless_reconcile(clear_reason="provider usage exceeded", evidence="x", **kw)
    assert res["rc"] == 2 and "does not match the block exactly" in res["reason"]
    res = PB.featherless_reconcile(clear_reason=bound, **kw)
    assert res["rc"] == 2                                                      # no evidence
    assert _state(envelope)["blocked"] == bound and "opening_balance_usd" not in _state(envelope)
    res = PB.featherless_reconcile(clear_reason=bound, evidence="statement checked: one long reply", **kw)
    assert res["rc"] == 0 and _state(envelope)["blocked"] is None
    assert _state(envelope)["history"][-1]["clear_reason"] == bound


def test_an_operator_read_balance_needs_a_terminal_and_evidence_and_is_marked_manual(envelope):
    now = PB._utcnow()
    _blocked_envelope(envelope, held_usd=0.16, now=now)
    kw = dict(opening_balance_usd=74.5, observed_balance_usd=74.42, balance_reader=_no_reader,
              pid_alive=lambda pid: False, now=now, who="t")
    res = PB.featherless_reconcile(evidence="dashboard", interactive=False, **kw)
    assert res["rc"] == 2 and res["reason"].startswith("NOT_A_TERMINAL")
    res = PB.featherless_reconcile(evidence=None, interactive=True, **kw)
    assert res["rc"] == 2 and "needs --evidence" in res["reason"]
    res = PB.featherless_reconcile(evidence="dashboard read by the owner", interactive=True, **kw)
    assert res["rc"] == 0
    ev = _state(envelope)["history"][-1]
    assert ev["manual"] is True and ev["balance_source"] == "operator" and "dashboard read by the owner" in ev["why"]


def test_an_unreadable_balance_refuses_red(envelope):
    now = PB._utcnow()
    _blocked_envelope(envelope, held_usd=0.16, now=now)

    def broken():
        raise PB.FeatherlessBalanceUnavailable("stub outage")
    res = PB.featherless_reconcile(opening_balance_usd=74.5, balance_reader=broken, now=now,
                                   pid_alive=lambda pid: False)
    assert res["rc"] == 2 and "balance unavailable" in res["reason"]
    assert _state(envelope)["blocked"] == "unknown returned model"


def test_a_stored_opening_is_the_baseline_and_a_different_one_is_refused(envelope):
    now = PB._utcnow()
    _blocked_envelope(envelope, held_usd=0.16, now=now)
    assert PB.featherless_reconcile(opening_balance_usd=74.50, balance_reader=_reader(74.40),
                                    pid_alive=lambda pid: False, now=now)["rc"] == 0
    res = PB.featherless_reconcile(balance_reader=_reader(74.39), pid_alive=lambda pid: False, now=now)
    assert res["rc"] == 0 and res["decision"] == "NO_BLOCK"
    res = PB.featherless_reconcile(opening_balance_usd=80.0, balance_reader=_reader(74.39),
                                   pid_alive=lambda pid: False, now=now)
    assert res["rc"] == 2 and "rebaseline" in res["reason"]


# ── rebaseline ───────────────────────────────────────────────────────────────

def test_rebaseline_after_a_top_up_records_evidence_and_never_clears(envelope):
    now = PB._utcnow()
    _blocked_envelope(envelope, held_usd=0.16, now=now, opening_balance_usd=74.50, baseline_held_units=0)
    # a top-up: observed above the opening is refused
    res = PB.featherless_reconcile(balance_reader=_reader(99.90), pid_alive=lambda pid: False, now=now)
    assert res["rc"] == 2 and "ABOVE the opening" in res["reason"]
    assert PB.featherless_rebaseline(opening_balance_usd=99.90, evidence=None)["rc"] == 2
    res = PB.featherless_rebaseline(opening_balance_usd=99.90, evidence="topped up $25, receipt 1234", who="t")
    assert res["rc"] == 0
    s = _state(envelope)
    assert s["blocked"] == "unknown returned model"                         # never clears by itself
    ev = s["history"][-1]
    assert (ev["action"], ev["old_opening_usd"], ev["new_opening_usd"], ev["as_of"]) == (
        "rebaseline", 74.50, 99.90, "now")
    assert ev["new_baseline_held_usd"] == pytest.approx(0.16) and ev["who"] == "t" and "receipt" in ev["why"]
    # after the rebaseline: no spend since -> clears; spend since must be held since
    assert PB.featherless_reconcile(balance_reader=_reader(99.90), pid_alive=lambda pid: False,
                                    now=now)["decision"] == "CLEAR_BLOCK"
    res = PB.featherless_reconcile(balance_reader=_reader(99.80), pid_alive=lambda pid: False, now=now)
    assert res["rc"] == 2 and res["held_usd"] == pytest.approx(0.0)        # 0.10 spent, nothing held since
    PB.featherless_attempt(_body(max_tokens=300000), purpose="t", send=lambda: _resp(ti=500, to=230000))
    res = PB.featherless_reconcile(balance_reader=_reader(99.80), pid_alive=lambda pid: False, now=now)
    assert res["rc"] == 0


def test_rebaseline_at_creation_fixes_a_typo(envelope):
    now = PB._utcnow()
    _blocked_envelope(envelope, held_usd=0.16, now=now, opening_balance_usd=74.45, baseline_held_units=0)
    res = PB.featherless_rebaseline(opening_balance_usd=74.50, evidence="typo: the 11-11 reading was 74.50",
                                    at_creation=True)
    assert res["rc"] == 0
    s = _state(envelope)
    assert s["opening_balance_usd"] == 74.50 and s["baseline_held_units"] == 0
    assert s["history"][-1]["as_of"] == "creation"


# ── a reservation racing the reconcile ───────────────────────────────────────

def test_a_reservation_during_reconcile_waits_on_the_lock_and_is_not_lost(envelope):
    now = PB._utcnow()
    rows = {"deadold": {"held_units": 5, "reserved_units": 5, "status": "RESERVED_UNKNOWN",
                        "started_utc": (now - timedelta(hours=4)).isoformat(), "pid": 9}}
    _blocked_envelope(envelope, held_usd=0.16, now=now, extra_rows=rows)
    seen = {}

    def other_caller():
        try:
            seen["acct"] = PB.featherless_attempt(_body(), purpose="racer", send=lambda: _resp())[1]
        except Exception as exc:                                              # noqa: BLE001
            seen["exc"] = exc

    t = threading.Thread(target=other_caller)

    def alive(pid):                         # called INSIDE the reconcile's lock
        if not t.is_alive() and "started" not in seen:
            seen["started"] = True
            t.start()
            time.sleep(0.4)
            seen["waiting_while_locked"] = t.is_alive()
        return False
    res = PB.featherless_reconcile(opening_balance_usd=74.50, balance_reader=_reader(74.40),
                                   pid_alive=alive, now=now, who="t")
    t.join(timeout=10)
    assert res["rc"] == 0 and seen["waiting_while_locked"] is True
    assert "exc" not in seen and seen["acct"]["billing_status"] == "SETTLED"   # admitted after the unblock
    s = _state(envelope)
    assert s["blocked"] is None and s["history"][-1]["action"] == "unblock"     # the reconcile's write survived
    assert s["calls"]["deadold"]["status"] == "BILLING_UNKNOWN"
    assert any(r.get("purpose") == "racer" for r in s["calls"].values())        # and so did the racer's row


# ── the balance reader (stubbed HTTP) ────────────────────────────────────────

class _Resp(io.BytesIO):
    def __init__(self, data, url="https://api.featherless.ai/credits/balance"):
        super().__init__(data)
        self._url = url

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_the_balance_reader_takes_a_named_usd_field_and_never_returns_the_key():
    seen = {}

    def opener(req, timeout):
        seen.update(url=req.full_url, auth=req.get_header("Authorization"))
        return _Resp(json.dumps({"balance": "74.41", "currency": "USD"}).encode())
    out = PB.featherless_read_balance(opener=opener, api_key="fl-test-not-a-real-key")
    assert out["balance_usd"] == pytest.approx(74.41) and out["field"] == "balance"
    assert seen["url"].startswith("https://api.featherless.ai/") and seen["auth"].startswith("Bearer ")
    assert "fl-test-not-a-real-key" not in json.dumps(out)
    out = PB.featherless_read_balance(opener=lambda r, timeout: _Resp(b'{"data": {"balance_usd": 12.5}}'),
                                      api_key="k")
    assert out["balance_usd"] == 12.5 and out["field"] == "data.balance_usd"


@pytest.mark.parametrize("payload,match", [
    (b"74.41", "not a JSON object"),
    (b'{"plan": "x", "credits": 74}', "no accepted USD balance field"),
    (b'{"balance": 7441}', "outside 0..150"),
    (b'{"balance": 74.4, "currency": "EUR"}', "not USD"),
    (b'{"balance": true}', "not a number"),
])
def test_the_balance_reader_refuses_bare_numbers_unknown_shapes_and_implausible_values(payload, match):
    with pytest.raises(PB.FeatherlessBalanceUnavailable, match=match):
        PB.featherless_read_balance(opener=lambda r, timeout: _Resp(payload), api_key="k")


def test_the_balance_reader_refuses_a_foreign_host_a_missing_key_and_a_redirected_reply(monkeypatch):
    def never(req, timeout):
        pytest.fail("the key must not be sent")
    with pytest.raises(PB.FeatherlessBalanceUnavailable, match="official"):
        PB.featherless_read_balance(opener=never, url="https://evil.example/credits", api_key="k")
    monkeypatch.delenv(C.FEATHERLESS_KEY_ENV, raising=False)
    with pytest.raises(PB.FeatherlessBalanceUnavailable, match="not set"):
        PB.featherless_read_balance(opener=never)
    with pytest.raises(PB.FeatherlessBalanceUnavailable, match="another host"):
        PB.featherless_read_balance(
            opener=lambda r, timeout: _Resp(b'{"balance": 1}', url="https://evil.example/x"), api_key="k")


def test_the_default_opener_never_follows_a_redirect():
    import urllib.request
    opener = PB._fl_no_redirect_opener()
    handlers = opener.__self__.handlers
    redirect = [h for h in handlers if isinstance(h, urllib.request.HTTPRedirectHandler)]
    assert redirect and all(h.redirect_request(None, None, 302, "Found", {}, "https://evil.example/") is None
                            for h in redirect)


# ── the CLI ──────────────────────────────────────────────────────────────────

def test_cli_reconcile_dry_run_writes_nothing(envelope, monkeypatch, capsys):
    now = PB._utcnow()
    _blocked_envelope(envelope, held_usd=0.16, now=now)
    before = envelope.read_bytes()
    monkeypatch.setattr(PB, "featherless_read_balance", _reader(74.40))
    rc = PB.main(["reconcile", "--provider", "featherless", "--dry-run", "--opening-balance", "74.5"])
    assert rc == 0 and envelope.read_bytes() == before
    assert "[dry-run] would clear the block" in capsys.readouterr().out


def test_cli_manual_balance_without_a_terminal_is_refused(envelope, monkeypatch, capsys):
    now = PB._utcnow()
    _blocked_envelope(envelope, held_usd=0.16, now=now)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    rc = PB.main(["reconcile", "--provider", "featherless", "--opening-balance", "74.5",
                  "--observed-balance", "74.4", "--evidence", "x"])
    assert rc == 2 and "NOT_A_TERMINAL" in capsys.readouterr().out
    assert _state(envelope)["blocked"] == "unknown returned model"


def test_cli_rebaseline_refuses_without_evidence(envelope, capsys):
    now = PB._utcnow()
    _blocked_envelope(envelope, held_usd=0.16, now=now)
    assert PB.main(["rebaseline", "--provider", "featherless", "--opening-balance", "80"]) == 2
    assert "--evidence TEXT is required" in capsys.readouterr().out


def test_cli_deepseek_reconcile_refuses_featherless_flags(capsys):
    assert PB.main(["reconcile", "--dry-run"]) == 2
    assert "belong to `reconcile --provider featherless`" in capsys.readouterr().out
