"""FAULT INJECTION for the night pipeline as a SEQUENCE (Order 20 §7 / B3).

The dress rehearsal proved the RESOLUTION sequence hands its stages the right
shapes; nothing had injected faults into the NIGHT sequence and asserted the
one property that matters: **a fault mid-night halts the night — it never
produces a partial night that reads as data.** Budget exhaustion and cell
divergence were already covered; the two faults added here are the ones the
adjudication named:

  * NETWORK DEATH — a raw ConnectionError from the transport, mid-sequence,
    which is not one of the typed refusals the runner already knows;
  * A CORRUPTED FEED — NaN and garbage in the feature snapshot, which must
    be excluded at selection with a counted reason, never forecast on.

Everything runs sandboxed and offline; the evidence ledger is monkeypatched
and asserted untouched in every case.
"""

from __future__ import annotations

import math

import pytest

from backend.services import investigator_night as N
from backend.tests.test_investigator_night import _feats, good_llm, no_tools


def _guard_ledger(monkeypatch):
    appended = []
    monkeypatch.setattr("backend.services.belief_state.append",
                        lambda recs, path=None: appended.extend(recs))
    monkeypatch.setattr(N, "_spend_since", lambda s, **_: (0.01, 5))
    return appended


# ── network death mid-sequence ─────────────────────────────────────────────
def test_a_connection_death_mid_night_never_yields_a_partial_ok(monkeypatch):
    """The LLM transport dies after six successful calls — the shape of a
    network drop, not a budget stop. Whatever the runner does with it
    (typed halt or propagated exception), the two forbidden outcomes are a
    status of 'ok' and a ledger append."""
    appended = _guard_ledger(monkeypatch)
    calls = {"n": 0}

    def dying_llm(**kw):
        calls["n"] += 1
        if calls["n"] > 6:
            raise ConnectionError("simulated network death mid-night")
        return good_llm(**kw)

    try:
        res = N.run_night({f"T{i}": _feats(float(i)) for i in range(4)},
                          k=4, llm_call=dying_llm, tool_runner=no_tools,
                          dry_run=True, sandbox=True)
    except ConnectionError:
        res = None          # propagating is an acceptable halt
    if res is not None:
        assert res.status != "ok", (
            "a night whose transport died mid-sequence reported ok — a "
            "partial night in the ledger looks exactly like a complete one")
        assert res.void_reason or res.status in ("void", "budget_stopped",
                                                 "failed", "error")
    assert appended == [], "a dying night appended to the evidence ledger"


def test_a_connection_death_on_the_first_call_is_equally_clean(monkeypatch):
    appended = _guard_ledger(monkeypatch)

    def dead_llm(**kw):
        raise ConnectionError("network unreachable")

    try:
        res = N.run_night({f"T{i}": _feats(float(i)) for i in range(3)},
                          k=3, llm_call=dead_llm, tool_runner=no_tools,
                          dry_run=True, sandbox=True)
    except ConnectionError:
        res = None
    if res is not None:
        assert res.status != "ok"
    assert appended == []


# ── corrupted feed ─────────────────────────────────────────────────────────
def test_nan_zscores_are_missing_and_amendment_1_refuses_boolean_only_names():
    """AMENDMENT 1 (2026-08-19, Murat-approved, attended): the pre-amendment
    rule let a name with both z-scores unmeasured stay eligible at score 0
    on its booleans alone — the registered loophole cycle G found. Now a
    name needs >=1 measured CONTINUOUS component; the refusal discloses
    which components were missing."""
    bad = _feats(float("nan"))
    bad["volume_z_20d"] = float("nan")
    c = N.TR.score_candidate("CORRUPT", bad)
    assert not c.eligible
    assert "no continuous trigger component" in c.reason
    assert "abs_resid_return_z_1d" in c.reason
    assert "volume_z_20d" in c.reason

    # ONE measured continuous component keeps a name eligible — the
    # amendment tightens the boolean-only case, not ordinary missingness.
    one = _feats(2.5)
    one["volume_z_20d"] = float("nan")
    c1 = N.TR.score_candidate("HALFMEASURED", one)
    assert c1.eligible
    assert "missing: volume_z_20d" in c1.reason

    # And the limiting case stays a refusal: nothing measured is not calm.
    nothing = {"price": 100.0, "dollar_volume_20d": 1e9}
    c2 = N.TR.score_candidate("UNMEASURED", nothing)
    assert not c2.eligible
    assert "no trigger features" in c2.reason


def test_amendment_1_disclosure_is_carried_on_the_night_receipt():
    """Cycle G's second finding: run_night stripped `selected` rows, so the
    per-name missing-components disclosure never reached the receipt. It
    must now be carried, with the amendment stamped beside the weights."""
    feats = {f"T{i}": _feats(1.0 + i) for i in range(4)}
    res = N.run_night(feats, k=3, llm_call=good_llm, tool_runner=no_tools,
                      dry_run=True, sandbox=True)
    tr = res.trigger_report
    assert "selected" in tr and len(tr["selected"]) == 3
    assert all("reason" in row for row in tr["selected"])
    assert "amendment-1" in tr["amendment"]


def test_a_wholly_corrupted_feed_voids_the_night(monkeypatch):
    """Every name NaN — the shape of a dead upstream feed. The night must be
    void with a reason, not 'ok' over an empty or garbage selection."""
    appended = _guard_ledger(monkeypatch)
    bad = {}
    for i in range(4):
        f = _feats(float("nan"))
        f["volume_z_20d"] = float("nan")
        f["price"] = float("nan")
        bad[f"T{i}"] = f
    res = N.run_night(bad, k=4, llm_call=good_llm, tool_runner=no_tools,
                      dry_run=True, sandbox=True)
    assert res.status == "void"
    assert res.void_reason
    assert appended == []


def test_garbage_typed_features_do_not_reach_an_arm(monkeypatch):
    """Strings where floats belong — the classic upstream schema drift.
    Selection must either exclude the name or the runner must halt; a night
    that forecasts on 'N/A' has laundered a type error into a probability."""
    appended = _guard_ledger(monkeypatch)
    bad = {"abs_resid_return_z_1d": "N/A", "volume_z_20d": "err",
           "earnings_within_5d": False, "filing_within_2d": False,
           "price": "None", "dollar_volume_20d": 1e9}
    try:
        res = N.run_night({"GOOD": _feats(3.0), "TYPED": bad},
                          k=2, llm_call=good_llm, tool_runner=no_tools,
                          dry_run=True, sandbox=True)
    except (TypeError, ValueError):
        appended_ok = appended == []
        assert appended_ok
        return          # a loud halt is an acceptable outcome
    assert "TYPED" not in res.tickers, \
        "a string-typed name was selected as a trigger"
    assert appended == []
