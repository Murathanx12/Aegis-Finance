"""A night that cannot FINISH before the open is as contaminated as a stale one.

THE DEFECT, FOUND 2026-08-15 BY MULTIPLYING TWO KNOWN NUMBERS
=============================================================
The order specified a pre-open night at ~11:50 UTC. The night is

    40 cells x 5 arms x ~4.8 calls = ~960 SERIAL vendor calls

and Night 1's own ledger already recorded the latency of 224 real calls:
median 6.6s, **mean 8.7s**, p90 15.6s. That is **2.3 hours**.

An 11:50 UTC start finishes around 14:10 UTC. The US session opens at 13:30
UTC. **The ordered start time could never have finished pre-open** — and nobody
had noticed, because the call count lived in a config file and the latency lived
in a telemetry ledger, and no one had multiplied them.

WHY IT NEEDS A GUARD AND NOT A NOTE
===================================
The failure does not look like a failure. The night completes, the receipt says
`ok`, and the contamination is visible only to someone who compares the last
cell's timestamp against the opening bell. Worse than a void: a void mints
nothing, while this would ACCRUE — spending one of the forty nights on a night
whose tool-bearing arms read live intraday data their forecasts are not graded
against. That is hindsight handed specifically to the treatment arms of the
primary contrast, which is the exact structure that voided Night 1.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.services import investigator_night as N


def _at(h, m=0):
    return datetime(2026, 8, 15, h, m, tzinfo=timezone.utc)


def test_the_full_night_is_about_two_and_a_quarter_hours():
    """The number nobody had computed."""
    mins = N.projected_night_minutes(k=40, n_arms=5)
    assert 2.0 < mins / 60.0 < 2.6, mins
    assert int(40 * 5 * N.MEASURED_CALLS_PER_CELL) == 960


def test_the_ORDERED_start_time_would_have_spanned_the_open():
    """11:50 UTC — the time the order actually specified."""
    with pytest.raises(N.NightWouldSpanTheOpen) as e:
        N.assert_night_fits_before_open(k=40, n_arms=5, now=_at(11, 50))
    assert "after the 13:30Z open" in str(e.value)
    # And it says what to do instead, rather than only refusing.
    assert "latest safe start is about" in str(e.value)


def test_a_start_with_room_is_allowed_and_reports_its_headroom():
    rep = N.assert_night_fits_before_open(k=40, n_arms=5, now=_at(9, 0))
    assert rep["minutes_of_headroom"] > 0
    assert rep["n_calls_projected"] == 960
    assert "13:30" in rep["next_open_utc"]


def test_the_boundary_is_the_open_not_a_round_number():
    """Just inside passes; just outside refuses. No fudge either way."""
    mins = N.projected_night_minutes(k=40, n_arms=5)
    open_utc = _at(13, 30)
    just_ok = open_utc - timedelta(minutes=mins + 1)
    just_late = open_utc - timedelta(minutes=mins - 1)
    assert N.assert_night_fits_before_open(k=40, n_arms=5, now=just_ok)
    with pytest.raises(N.NightWouldSpanTheOpen):
        N.assert_night_fits_before_open(k=40, n_arms=5, now=just_late)


def test_after_the_open_the_deadline_rolls_to_TOMORROW_not_to_zero():
    """A 14:00 UTC start is not 'negative headroom today' — it is a night for
    tomorrow's session, and it has plenty of room."""
    rep = N.assert_night_fits_before_open(k=40, n_arms=5, now=_at(14, 0))
    assert rep["next_open_utc"].startswith("2026-08-16")
    assert rep["minutes_of_headroom"] > 60


def test_a_slower_vendor_shrinks_the_window():
    """p90 latency is 15.6s, and the window moves with the measurement.

    Worth stating the arithmetic, because the first version of this test got it
    wrong: at p90 the night is 4.2h, so a 09:00 start still lands at 13:10 with
    twenty minutes to spare. It is 09:30 that stops fitting. The guard is
    tighter than intuition in one direction and looser in the other, which is
    the argument for computing it rather than eyeballing it.
    """
    ok = N.assert_night_fits_before_open(k=40, n_arms=5, now=_at(9, 0),
                                         call_seconds=15.6)
    assert 0 < ok["minutes_of_headroom"] < 30
    with pytest.raises(N.NightWouldSpanTheOpen):
        N.assert_night_fits_before_open(k=40, n_arms=5, now=_at(9, 30),
                                        call_seconds=15.6)


def test_the_guard_runs_on_the_production_path_before_any_paid_call(monkeypatch):
    """Wiring, not intent — the check must sit with the other pre-spend guards."""
    import inspect
    src = inspect.getsource(N.run_night)
    assert "assert_night_fits_before_open" in src
    i_guard = src.index("assert_night_fits_before_open")
    i_select = src.index("TR.select_triggers")
    assert i_guard < i_select, (
        "the timing guard must fire before the night starts selecting and "
        "spending, like every other refusal here")


def test_the_guard_ACTUALLY_FIRES_on_a_production_night(monkeypatch):
    """Not source inspection — the real call path, refusing before it spends.

    The test above reads `run_night`'s source, which cannot tell you the line
    executes. This one drives the production branch with a latency constant
    large enough that no start time could fit, so it does not depend on when
    the suite happens to run, and asserts the refusal arrives before any
    trigger selection or vendor call.
    """
    spent = []
    monkeypatch.setattr(N, "MEASURED_CALL_SECONDS", 3600.0)
    monkeypatch.setattr(N, "make_llm_call",
                        lambda **kw: spent.append(1), raising=False)
    monkeypatch.setattr(N.TR, "select_triggers",
                        lambda *a, **k: spent.append("selected"))

    with pytest.raises(N.NightWouldSpanTheOpen) as e:
        N.run_night({f"T{i}": {} for i in range(3)},
                    k=40, arms=N.ARMS, max_usd=12.0,
                    llm_call=None, tool_runner=None,
                    dry_run=False, sandbox=False)

    assert spent == [], (
        "the night selected triggers or called the vendor before the timing "
        "guard refused — the guard must sit with the other pre-spend refusals")
    assert "after the" in str(e.value) and "open" in str(e.value)


def test_a_sandbox_rehearsal_is_NOT_blocked_by_the_open(monkeypatch):
    """A rehearsal spends nothing and reads no live data, so the market clock
    is irrelevant to it. Blocking rehearsals would make the one free way to
    exercise this machinery unavailable for most of the day."""
    monkeypatch.setattr(N, "MEASURED_CALL_SECONDS", 3600.0)
    from backend.tests.test_investigator_night import (_feats, good_llm,
                                                       no_tools)
    res = N.run_night({f"T{i}": _feats(float(i)) for i in range(3)},
                      k=3, llm_call=good_llm, tool_runner=no_tools,
                      dry_run=True, sandbox=True)
    assert res.status in ("ok", "VOID")
    assert res.timing == {}          # not computed, and not silently faked


def test_the_receipt_records_the_headroom_the_night_actually_had():
    res = N.NightResult(night="2026-08-15")
    assert res.timing == {}
    res.timing = N.assert_night_fits_before_open(k=40, n_arms=5, now=_at(9, 0))
    d = res.as_dict()
    assert "timing" in d and d["timing"]["n_calls_projected"] == 960
    # Value-free: a projection and a clock, no trial statistics.
    for leak in ("posterior", "probability", "brier", "contrast"):
        assert leak not in str(d["timing"])
