"""R10 — arms concurrent within a cell, against a KNOWN-RESPONSE transport.

WHY A KNOWN-RESPONSE HARNESS COMES FIRST
========================================
Concurrency bugs do not announce themselves. They produce a night that finishes,
a receipt that says `ok`, and numbers that are wrong by an amount nobody can
reconstruct afterwards. So every property the amendment depends on is asserted
against a transport whose replies are fixed and whose timing is controlled,
before a single real vendor call is made concurrently.

THE HAZARD THAT MOTIVATED THE GOVERNOR, STATED PRECISELY
========================================================
`_spend_since` reads the telemetry ledger, and a row lands there only AFTER its
call has been served. In series that is complete information. With five arms in
flight, all five can read the ledger before any of them writes to it, all five
see the same `$11.99`, all five pass `usd + reserve > max_usd`, and all five
transmit. **The hard ceiling would become soft by the concurrency factor** — and
every individual check would have been correct.

WHAT IS DELIBERATELY NOT CLAIMED
================================
That concurrency is faster. It is, and the receipt records it, but speed is not
why R10 was approved: cell-major ordering exists so the five arms see the same
world, and concurrency makes them more simultaneous. That is a claim about
`arm_start_skew_ms`, which is measured here rather than asserted.
"""

from __future__ import annotations

import threading
import time

import pytest

from backend.services import investigator_night as N
from backend.tests.test_investigator_night import _feats, good_llm, no_tools


# ── the governor: the ceiling under concurrency ─────────────────────────────

def _gov(max_usd=12.0, spent=0.0, calls=0, monkeypatch=None):
    monkeypatch.setattr(N, "_spend_since", lambda *a, **k: (spent, calls))
    return N.SpendGovernor(since_iso="2026-08-16T00:00:00+00:00",
                           max_usd=max_usd, max_calls=3000)


def test_five_concurrent_reservations_cannot_all_pass_one_slot(monkeypatch):
    """The exact failure: the ledger says $11.99 to every arm at once.

    Room for exactly one worst-case call. Five threads ask together. Without an
    in-flight term all five would be told yes, because all five read the same
    ledger before any of them wrote to it.
    """
    room = N.WORST_CASE_CALL_USD * 1.5
    gov = _gov(max_usd=room, spent=0.0, monkeypatch=monkeypatch)

    granted, refused = [], []
    barrier = threading.Barrier(5)

    def ask():
        barrier.wait()               # force the reads to collide
        try:
            gov.reserve()
            granted.append(1)
        except N.NightlyBudgetExhausted:
            refused.append(1)

    threads = [threading.Thread(target=ask) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(granted) == 1, (
        f"{len(granted)} concurrent calls were authorised against room for "
        f"one — the nightly ceiling is soft by the concurrency factor")
    assert len(refused) == 4


def test_a_released_reservation_frees_the_slot_again(monkeypatch):
    gov = _gov(max_usd=N.WORST_CASE_CALL_USD * 1.5, monkeypatch=monkeypatch)
    gov.reserve()
    with pytest.raises(N.NightlyBudgetExhausted):
        gov.reserve()
    gov.release()
    gov.reserve()                    # the slot came back


def test_a_reservation_is_released_even_when_the_call_RAISES(monkeypatch):
    """A leak on failure would ratchet the night shut one error at a time, and
    it would report a budget refusal for money that was never spent."""
    monkeypatch.setattr(N, "_spend_since", lambda *a, **k: (0.0, 0))

    def boom(**kw):
        raise RuntimeError("vendor said no")

    call = N.make_llm_call(since_iso="2026-08-16T00:00:00+00:00",
                           max_usd=12.0, transport=boom,
                           telemetry_path=None)
    for _ in range(6):
        with pytest.raises(RuntimeError):
            call(system="s", user="u")
    assert call.governor._in_flight_usd == pytest.approx(0.0)
    assert call.governor._in_flight_calls == 0


def test_the_call_ceiling_also_counts_what_is_in_flight(monkeypatch):
    gov = _gov(max_usd=1000.0, calls=2, monkeypatch=monkeypatch)
    gov.max_calls = 4
    gov.reserve(), gov.reserve()          # 2 served + 2 in flight == 4
    with pytest.raises(N.NightlyBudgetExhausted, match="in flight"):
        gov.reserve()


# ── the night: arms concurrent, cells sequential ────────────────────────────

def _slow_llm(delay=0.05):
    """A known-response transport that takes measurable time."""
    def call(**kw):
        time.sleep(delay)
        return good_llm(**kw)
    return call


def _night(**kw):
    base = dict(k=3, llm_call=good_llm, tool_runner=no_tools,
                dry_run=True, sandbox=True)
    base.update(kw)
    return N.run_night({f"T{i}": _feats(float(i)) for i in range(4)}, **base)


def test_concurrent_and_serial_nights_produce_the_SAME_cells():
    """Concurrency must change the timing and nothing else."""
    a = _night(arm_concurrency=1)
    b = _night(arm_concurrency=5)
    assert a.tickers == b.tickers
    for arm in N.ARMS:
        assert ([r["ticker"] for r in a.per_arm[arm]["rows"]]
                == [r["ticker"] for r in b.per_arm[arm]["rows"]])


def test_the_arms_of_a_cell_are_MORE_simultaneous_when_concurrent():
    """The claim the amendment rests on, measured rather than assumed."""
    serial = _night(arm_concurrency=1, llm_call=_slow_llm(0.02))
    conc = _night(arm_concurrency=5, llm_call=_slow_llm(0.02))
    assert serial.arm_start_skew_ms and conc.arm_start_skew_ms
    assert max(conc.arm_start_skew_ms) < max(serial.arm_start_skew_ms), (
        "arms did not start closer together under concurrency, which is the "
        "entire scientific argument for the change")


def test_every_arm_gets_its_OWN_chain_cursor():
    """A shared cursor would file telemetry under whichever arm wrote last —
    silently, and in a way that looks like clean data."""
    res = _night(arm_concurrency=5)
    seen = set()
    for arm in N.ARMS:
        for r in res.per_arm[arm]["rows"]:
            seen.add((r["arm"], r["ticker"]))
    # One (arm, cell) pair per row, none lost to a stomped cursor.
    assert len(seen) == sum(len(res.per_arm[a]["rows"]) for a in N.ARMS)


def test_a_cell_is_dropped_for_EVERY_arm_or_for_none(monkeypatch):
    """Symmetric drop. The arms must never differ by WHICH cell cut them off."""
    calls = {"n": 0}
    lock = threading.Lock()

    def flaky(**kw):
        with lock:
            calls["n"] += 1
            n = calls["n"]
        if n > 7:                     # dies part-way through a cell
            raise N.NightlyBudgetExhausted("ceiling")
        return good_llm(**kw)

    res = _night(arm_concurrency=5, llm_call=flaky)
    lengths = {len(res.per_arm[a]["rows"]) for a in N.ARMS}
    assert len(lengths) == 1, (
        f"arms hold different numbers of cells {lengths} — a partially "
        f"recorded cell is exactly the ragged edge the pairing guard refuses")


def test_the_receipt_records_the_execution_mode_it_actually_ran():
    assert _night(arm_concurrency=5).execution_mode == N.EXECUTION_MODE
    assert _night(arm_concurrency=1).execution_mode.endswith("arms_sequential")


def test_the_receipt_carries_the_skew_and_stays_value_free():
    import json
    res = _night(arm_concurrency=5)
    d = res.as_dict()
    assert d["arm_start_skew_ms"] and d["arm_concurrency"] == 5
    blob = json.dumps(d, default=str)
    for leak in ("posterior", "probability", "brier", "contrast"):
        assert leak not in blob


# ── the registered surface ──────────────────────────────────────────────────

def test_an_unregistered_concurrency_cannot_accrue(monkeypatch):
    """A number that changes how simultaneous the arms are is the primary
    contrast, so an unregistered value is a different experiment."""
    from backend.services import iif1_prereg as P
    monkeypatch.setattr(P, "verify_or_refuse", P.runtime_surface)
    with pytest.raises(N.SandboxRequired, match="MAX_ARM_CONCURRENCY"):
        N.assert_production_invocation(
            k=N.TR.TRIGGERS_PER_NIGHT, arms=N.ARMS, max_usd=N.NIGHTLY_MAX_USD,
            llm_call=None, tool_runner=None, arm_concurrency=3)


def test_the_registered_value_is_accepted(monkeypatch):
    from backend.services import iif1_prereg as P
    monkeypatch.setattr(P, "verify_or_refuse", P.runtime_surface)
    assert N.assert_production_invocation(
        k=N.TR.TRIGGERS_PER_NIGHT, arms=N.ARMS, max_usd=N.NIGHTLY_MAX_USD,
        llm_call=None, tool_runner=None,
        arm_concurrency=N.MAX_ARM_CONCURRENCY)


def test_the_execution_mode_is_on_the_FROZEN_surface_not_just_the_runtime():
    """`MAX_TOKENS` earned its place there by being able to bias the primary
    contrast while appearing in no registered document. This is the same."""
    from backend.services import iif1_prereg as P
    rt = P.runtime_surface()
    assert rt["EXECUTION_MODE"] == N.EXECUTION_MODE
    assert rt["MAX_ARM_CONCURRENCY"] == N.MAX_ARM_CONCURRENCY


# ── the timing guard, under the new mode ────────────────────────────────────

def test_concurrency_shrinks_the_projected_night_and_the_guard_knows():
    """This test used to assert the ratio was exactly 5.0.

    It was pinning the bug. Dividing the night by the full arm count is the
    OPTIMISTIC bound — a cell ends when its slowest arm ends, and the slow arms
    are systematically the tool-bearing ones. The projection may now claim only
    the DECLARED efficiency, which no real night has yet measured; the rehearsal
    that produced "peak 5 in flight, skew 1.0 ms" ran against a stub, and a stub
    with no latency cannot measure a latency speedup. See
    `test_night_fits_before_open.py::test_concurrency_may_only_claim_the_DECLARED_efficiency`.
    """
    serial = N.projected_night_minutes(k=40, n_arms=5)
    conc = N.projected_night_minutes(k=40, n_arms=5, arm_concurrency=5)
    assert serial / conc == pytest.approx(N.DECLARED_CONCURRENCY_EFFICIENCY)
    assert 65 < conc < 75, conc          # ~70 minutes, from 2.3 hours


def test_the_projection_never_divides_by_more_than_the_arms_it_has():
    """A flattering projection would let a night start too late, which is the
    exact failure the guard exists to prevent."""
    a = N.projected_night_minutes(k=40, n_arms=5, arm_concurrency=50)
    b = N.projected_night_minutes(k=40, n_arms=5, arm_concurrency=5)
    assert a == b
