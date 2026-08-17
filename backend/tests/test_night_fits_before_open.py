"""A night that cannot FINISH before the open is as contaminated as a stale one.

THE FIRST DEFECT, FOUND 2026-08-15 BY MULTIPLYING TWO KNOWN NUMBERS
===================================================================
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

THE SECOND AND THIRD DEFECTS, FOUND 2026-08-15 IN REVIEW — IN THIS FILE
=======================================================================
The guard above was right about the wrong world, twice, and **this test file
was the reason neither showed**:

* every timestamp below used to be **Saturday 2026-08-15**, asserting a 13:30Z
  opening bell on a day the exchange is shut. The guard built its bell by
  replacing the clock with 13:30 UTC and adding a calendar day if that had
  passed, so on the Saturday it was reviewed it returned a **Sunday** open —
  and the test asserting `next_open_utc` starts with "2026-08-16" **pinned the
  bug**. The bell now comes from an XNYS calendar (`market_sessions`), and
  every date here is a real session, checkable against a published calendar.
* the projection divided the night by the FULL arm count while its docstring
  said it stayed "deliberately pessimistic" because "a cell ends when its
  SLOWEST arm ends". Dividing by five IS the optimistic bound. See
  `test_concurrency_may_only_claim_the_DECLARED_efficiency`.

Both are the same shape as the CI failure earlier the same day: **the check and
its test agreed with each other about a world neither had looked at.**
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.services import investigator_night as N

#: Monday 2026-08-17 — a real EDT session, opening 13:30 UTC.
SESSION = (2026, 8, 17)
#: Thursday 2026-01-15 — a real EST session, opening **14:30** UTC.
WINTER_SESSION = (2026, 1, 15)


def _at(h, m=0, day=SESSION):
    return datetime(*day, h, m, tzinfo=timezone.utc)


#: Captured BEFORE any test can monkeypatch the name, so a test that pins the
#: clock still exercises the real guard rather than its own stub.
_real_guard = N.assert_night_fits_before_open


def _guard_minutes(*, k=40, n_arms=5, call_seconds=None):
    """The projection the guard ACTUALLY decides on.

    These tests used to compute their boundaries from
    `projected_night_minutes(k, n_arms)` with its module defaults, which was the
    same number the guard used — until 2026-08-17, when the guard began deriving
    `calls_per_cell` from completed nights' receipts (4.8 declared, 7.085
    measured on Night 1) and deciding on the SERIAL branch always.

    A test that recomputes the boundary from a different basis than the guard
    pins a coincidence. This helper is the single source, so a future
    measurement moves the tests and the guard together instead of turning six
    tests red on a correct change.
    """
    return N.projected_night_minutes(
        k=k, n_arms=n_arms, call_seconds=call_seconds, arm_concurrency=1,
        calls_per_cell=N.derive_calls_per_cell()["value"])


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
    # 1417, not 960. 960 was 40 x 5 x the DECLARED 4.8 calls/cell; 1417 is the
    # number Night 1 actually made (40 x 5 x 7.085), which the guard now derives
    # from that night's own receipt. The literal is kept rather than computed
    # because this is the one place the measured total should be readable.
    assert rep["n_calls_projected"] == 1417
    assert rep["calls_per_cell_basis"] == "MEASURED_MAX_OVER_COMPLETED_NIGHTS"
    assert rep["next_open_utc"].startswith("2026-08-17T13:30")
    assert rep["calendar"] == "XNYS"


def test_the_boundary_is_the_open_not_a_round_number():
    """Just inside passes; just outside refuses. No fudge either way."""
    mins = _guard_minutes()
    open_utc = _at(13, 30)
    just_ok = open_utc - timedelta(minutes=mins + 1)
    just_late = open_utc - timedelta(minutes=mins - 1)
    assert N.assert_night_fits_before_open(k=40, n_arms=5, now=just_ok)
    with pytest.raises(N.NightWouldSpanTheOpen):
        N.assert_night_fits_before_open(k=40, n_arms=5, now=just_late)


def test_after_the_open_the_deadline_rolls_to_the_NEXT_SESSION():
    """A 14:00 UTC start is not 'negative headroom today' — it is a night for
    the next session, and it is refused for being 23 hours early.

    This test used to assert the next open was **2026-08-16**, which is a
    Sunday, and that the night had "plenty of room". It was pinning the
    arithmetic, not the market. The real answer is Tuesday the 18th, and the
    correct verdict is a REFUSAL: a night begun during Monday's session and
    graded against Tuesday's open carries a snapshot a full day old. The old
    guard called that the safest configuration available, because it measured
    headroom and nothing else.
    """
    with pytest.raises(N.NightWouldSpanTheOpen) as e:
        N.assert_night_fits_before_open(k=40, n_arms=5, now=_at(14, 0))
    assert "not a pre-open window" in str(e.value)
    rep = N.assert_night_fits_before_open(k=40, n_arms=5, now=_at(14, 0),
                                          max_lead_hours=1e6)
    assert rep["next_session"] == "2026-08-18"
    assert rep["minutes_of_headroom"] > 60


def test_the_usable_window_is_a_window_at_both_ends():
    """Too late is contamination; too early is a stale snapshot. Both refuse,
    and the receipt names which."""
    open_utc = _at(13, 30)
    mins = _guard_minutes()
    latest = open_utc - timedelta(minutes=mins + 1)
    earliest = open_utc - timedelta(hours=N.MAX_PREOPEN_LEAD_HOURS) \
        + timedelta(minutes=1)
    assert N.assert_night_fits_before_open(k=40, n_arms=5, now=latest)
    assert N.assert_night_fits_before_open(k=40, n_arms=5, now=earliest)
    with pytest.raises(N.NightWouldSpanTheOpen, match="pre-open window"):
        N.assert_night_fits_before_open(
            k=40, n_arms=5, now=earliest - timedelta(minutes=2))


def test_a_slower_vendor_shrinks_the_window():
    """p90 latency is 15.6s, and the window moves with the measurement.

    Stated as the PROPERTY rather than as two clock times. The earlier version
    asserted that 09:00 fits at p90 and 09:30 does not, which was correct
    arithmetic in a world of 4.8 calls per cell and became wrong when the guard
    started deriving 7.085 from Night 1's receipt — at p90 the night is now 6.1h,
    so neither time fits. Pinning "the latest safe start moves EARLIER when the
    vendor is slower" survives any future measurement, and it is the claim the
    test's own name makes.
    """
    open_utc = _at(13, 30)
    mean_mins = _guard_minutes()
    slow_mins = _guard_minutes(call_seconds=15.6)
    assert slow_mins > mean_mins, "a slower vendor must lengthen the night"

    # Latest start that fits, at each latency. Slower vendor => earlier deadline.
    latest_mean = open_utc - timedelta(minutes=mean_mins + 1)
    latest_slow = open_utc - timedelta(minutes=slow_mins + 1)
    assert latest_slow < latest_mean

    ok = N.assert_night_fits_before_open(k=40, n_arms=5, now=latest_slow,
                                         call_seconds=15.6)
    assert 0 < ok["minutes_of_headroom"] < 5
    # One minute past its own deadline, the slow night refuses.
    with pytest.raises(N.NightWouldSpanTheOpen):
        N.assert_night_fits_before_open(
            k=40, n_arms=5, now=open_utc - timedelta(minutes=slow_mins - 1),
            call_seconds=15.6)


# ── the calendar, which the guard used to invent ────────────────────────────

def test_a_SATURDAY_night_is_refused_as_not_a_pre_open_window():
    """The live case on the day this was found. The old guard did not merely
    allow it — it allowed it against a Sunday bell it had made up."""
    with pytest.raises(N.NightWouldSpanTheOpen) as e:
        N.assert_night_fits_before_open(k=40, n_arms=5,
                                        now=_at(9, 0, (2026, 8, 15)))
    assert "not a pre-open window" in str(e.value)
    assert "2026-08-17" in str(e.value)      # the real next session
    assert "not a session" in str(e.value)


def test_a_SUNDAY_night_is_refused_and_names_MONDAY():
    """2026-08-16 — the date the paid night was ordered for."""
    with pytest.raises(N.NightWouldSpanTheOpen) as e:
        N.assert_night_fits_before_open(k=40, n_arms=5,
                                        now=_at(11, 0, (2026, 8, 16)))
    assert "not a pre-open window" in str(e.value)
    assert "2026-08-17" in str(e.value)


def test_the_calendar_fix_alone_would_have_made_a_WEEKEND_look_EXCELLENT():
    """Why the lead-time clause exists, stated as the arithmetic it prevents.

    With the bell read correctly but no lead limit, a Sunday 11:00Z night has
    26 hours of headroom — more than any weekday — so the *fixed* guard would
    have ranked the worst night of the week as the safest.
    """
    sunday = _at(11, 0, (2026, 8, 16))
    rep = N.assert_night_fits_before_open(k=40, n_arms=5, now=sunday,
                                          max_lead_hours=1e6)
    assert rep["minutes_of_headroom"] > 1000
    with pytest.raises(N.NightWouldSpanTheOpen):
        N.assert_night_fits_before_open(k=40, n_arms=5, now=sunday)


def test_a_WINTER_night_is_measured_against_a_1430_bell_not_1330():
    """09:30 New York is 13:30 UTC only under EDT. The constants were
    permanently 13:30, which was an hour PESSIMISTIC — the safe direction, and
    therefore the kind of error that survives for years."""
    rep = N.assert_night_fits_before_open(k=40, n_arms=5,
                                          now=_at(9, 0, WINTER_SESSION))
    assert "T14:30" in rep["next_open_utc"]
    # The hour is not cosmetic: there is a start that fits against a 14:30 bell
    # and refuses against a 13:30 one, on identical inputs. Computed from the
    # guard's own projection rather than written as a clock time, because the
    # literal 11:20 encoded a 2.32h night and stopped being the boundary the
    # moment the projection was measured.
    mins = _guard_minutes()
    fits_in_winter = _at(14, 30, WINTER_SESSION) - timedelta(minutes=mins + 2)
    assert N.assert_night_fits_before_open(k=40, n_arms=5, now=fits_in_winter)
    # The same offset before a SUMMER bell is one hour too late.
    too_late_in_summer = _at(13, 30) - timedelta(minutes=mins - 30)
    with pytest.raises(N.NightWouldSpanTheOpen):
        N.assert_night_fits_before_open(k=40, n_arms=5,
                                        now=too_late_in_summer)
    with pytest.raises(N.NightWouldSpanTheOpen):
        N.assert_night_fits_before_open(k=40, n_arms=5, now=_at(11, 20))


def test_a_HOLIDAY_is_refused_rather_than_traded_through():
    """Presidents' Day 2026-02-16. The old arithmetic would have projected
    against a 13:30Z bell that does not ring."""
    with pytest.raises(N.NightWouldSpanTheOpen) as e:
        N.assert_night_fits_before_open(k=40, n_arms=5,
                                        now=_at(9, 0, (2026, 2, 16)))
    assert "not a pre-open window" in str(e.value)
    assert "2026-02-17" in str(e.value)


def test_the_FRIDAY_BEFORE_a_long_weekend_still_runs_normally():
    """The lead clause must refuse weekends without refusing the last session
    before one — Friday 2026-02-13 is an ordinary pre-open window."""
    rep = N.assert_night_fits_before_open(k=40, n_arms=5,
                                          now=_at(9, 0, (2026, 2, 13)))
    assert rep["next_session"] == "2026-02-13"
    assert rep["hours_until_open"] < 6


# ── the divisor ─────────────────────────────────────────────────────────────

def test_concurrency_may_only_claim_the_DECLARED_efficiency():
    """The projection said 28 minutes. It had never met a real latency.

    Dividing a mean-of-five by five is the OPTIMISTIC bound, and the docstring
    that sat above it claimed pessimism on the grounds that a cell ends with
    its slowest arm. Both bounds are computed now and the slower one is taken.
    """
    serial = N.projected_night_minutes(k=40, n_arms=5)
    conc = N.projected_night_minutes(k=40, n_arms=5, arm_concurrency=5)
    speedup = serial / conc
    assert speedup <= N.DECLARED_CONCURRENCY_EFFICIENCY + 1e-9, (
        f"the projection claims a {speedup:.2f}x speedup against a DECLARED "
        f"{N.DECLARED_CONCURRENCY_EFFICIENCY}x — the rehearsal that produced "
        f"'peak 5 in flight' ran against a STUB, and a stub with no latency "
        f"cannot measure a latency speedup")
    assert 65 < conc < 75, conc          # ~70 minutes, not ~28


def test_the_projection_never_divides_by_more_than_the_arms_it_has():
    """A flattering projection would let a night start too late, which is the
    exact failure the guard exists to prevent."""
    a = N.projected_night_minutes(k=40, n_arms=5, arm_concurrency=50)
    b = N.projected_night_minutes(k=40, n_arms=5, arm_concurrency=5)
    assert a == b


def test_the_MAX_OF_ARMS_floor_binds_once_the_efficiency_is_raised():
    """A cell cannot beat its own slowest arm however efficient concurrency is.

    This is the property that makes a future measurement safe to adopt: raising
    the declared efficiency moves the projection only until one arm's serial
    chain takes over.
    """
    floor = N.MEASURED_MAX_ARM_CALLS * N.MEASURED_CALL_SECONDS * N.P90_OVER_MEAN
    generous = N.projected_night_minutes(k=40, n_arms=5, arm_concurrency=5,
                                         efficiency=50.0)
    assert generous == pytest.approx(40 * floor / 60.0)
    assert generous > 50.0, "the floor collapsed to something implausible"


def test_the_declared_efficiency_is_on_the_REGISTERED_surface(monkeypatch):
    """It decides whether a night may run, so drift in it is a refusal."""
    from backend.services import iif1_prereg as P
    rt = P.runtime_surface()
    assert rt["DECLARED_CONCURRENCY_EFFICIENCY"] == \
        N.DECLARED_CONCURRENCY_EFFICIENCY
    assert rt["MAX_PREOPEN_LEAD_HOURS"] == N.MAX_PREOPEN_LEAD_HOURS


def test_the_latest_safe_start_moved_LATER_when_the_divisor_was_fixed():
    """Stated as a time, because that is what the night is actually planned by.

    Serial: 13:30 minus 2.32h = about 11:10Z. Concurrent at the declared 2x:
    about 12:20Z. The deleted version said about 13:02Z — half an hour of
    window that did not exist.
    """
    open_utc = _at(13, 30)
    serial = open_utc - timedelta(
        minutes=N.projected_night_minutes(k=40, n_arms=5))
    conc = open_utc - timedelta(
        minutes=N.projected_night_minutes(k=40, n_arms=5, arm_concurrency=5))
    assert serial.strftime("%H:%M") == "11:10"
    assert conc.strftime("%H:%M") == "12:20"


# ── wiring ──────────────────────────────────────────────────────────────────

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


def test_a_module_constant_used_as_a_DEFAULT_ARGUMENT_is_frozen_at_import():
    """The trap that hid a dead guard for a day, pinned so it cannot return.

    `def f(call_seconds=MEASURED_CALL_SECONDS)` binds the value when the
    function is DEFINED. Setting `N.MEASURED_CALL_SECONDS` afterwards changes
    the module attribute and nothing the function reads — a constant that looks
    live and is frozen at import. Every constant here decides whether a paid
    night may run, so all of them are read at call time.
    """
    import backend.services.investigator_night as _N
    real = _N.MEASURED_CALL_SECONDS
    try:
        _N.MEASURED_CALL_SECONDS = 3600.0
        assert _N.projected_night_minutes(k=40, n_arms=5) > 10_000, (
            "the projection ignored a patched MEASURED_CALL_SECONDS — the "
            "constant is bound as a default argument again, and the guard "
            "that depends on it is untestable and unconfigurable")
    finally:
        _N.MEASURED_CALL_SECONDS = real


def test_the_guard_ACTUALLY_FIRES_on_a_production_night(monkeypatch):
    """Not source inspection — the real call path, refusing before it spends.

    The test above reads `run_night`'s source, which cannot tell you the line
    executes. This one drives the production branch with a latency constant
    large enough that no start time could fit and asserts the refusal arrives
    before any trigger selection or vendor call.

    IT PASSED FOR A YEAR OF ITS LIFE WITHOUT THE GUARD EVER FIRING. The
    monkeypatch below did nothing (see the test above), so the projection used
    the real 8.7s constant — and the old guard refused anyway, but only while
    the suite happened to run inside the 2.3 hours before the fabricated daily
    open. On 2026-08-15 it ran seven minutes before 13:30 UTC and was green;
    forty-six minutes later, on a commit that added 246 lines to one markdown
    file, it was red. `now` is pinned now so the clock cannot decide.
    """
    spent = []
    monkeypatch.setattr(N, "MEASURED_CALL_SECONDS", 3600.0)
    # A real pre-open session moment, so the LEAD clause passes and the test is
    # about the timing clause it names. Without this, the test passes on a
    # weekend for the wrong reason and fails on a Monday for the right one.
    monkeypatch.setattr(
        N, "assert_night_fits_before_open",
        lambda **kw: _real_guard(**{**kw, "now": _at(9, 0)}))
    monkeypatch.setattr(N, "make_llm_call",
                        lambda **kw: spent.append(1), raising=False)
    monkeypatch.setattr(N.TR, "select_triggers",
                        lambda *a, **k: spent.append("selected"))
    # The registered-rule check runs FIRST on a production night, and it reads
    # the `Aegis module` sibling. That ordering is correct — an unregistered
    # invocation must be refused before anything else is considered — but it
    # means this test asserted the timing guard's exception only on a machine
    # that happens to have the sibling checked out. In CI it raised
    # FrozenPreregMissing instead and turned the build red. Supplying the
    # runtime's own surface keeps the trial-integrity check real (a mismatched
    # k/arms/max_usd would still refuse) while letting the test reach the guard
    # it is actually about.
    from backend.services import iif1_prereg as P
    monkeypatch.setattr(P, "verify_or_refuse", P.runtime_surface)

    with pytest.raises(N.NightWouldSpanTheOpen) as e:
        N.run_night({f"T{i}": {} for i in range(3)},
                    k=40, arms=N.ARMS, max_usd=12.0,
                    llm_call=None, tool_runner=None,
                    dry_run=False, sandbox=False)

    assert spent == [], (
        "the night selected triggers or called the vendor before the timing "
        "guard refused — the guard must sit with the other pre-spend refusals")
    msg = str(e.value)
    assert "open" in msg and ("after the" in msg or "pre-open window" in msg)


def test_a_sandbox_rehearsal_is_NOT_blocked_by_the_open(monkeypatch):
    """A rehearsal spends nothing and reads no live data, so the market clock
    is irrelevant to it. Blocking rehearsals would make the one free way to
    exercise this machinery unavailable for most of the day — and after the
    calendar fix, unavailable for the whole of every weekend, which is when
    this one was written."""
    monkeypatch.setattr(N, "MEASURED_CALL_SECONDS", 3600.0)
    from backend.tests.test_investigator_night import (_feats, good_llm,
                                                       no_tools)
    res = N.run_night({f"T{i}": _feats(float(i)) for i in range(3)},
                      k=3, llm_call=good_llm, tool_runner=no_tools,
                      dry_run=True, sandbox=True)
    assert res.status in ("ok", "VOID")
    assert res.timing == {}          # not computed, and not silently faked


def test_the_receipt_records_the_headroom_the_night_actually_had():
    res = N.NightResult(night="2026-08-17")
    assert res.timing == {}
    res.timing = N.assert_night_fits_before_open(k=40, n_arms=5, now=_at(9, 0))
    d = res.as_dict()
    assert "timing" in d and d["timing"]["n_calls_projected"] == 1417
    # Value-free: a projection and a clock, no trial statistics.
    for leak in ("posterior", "probability", "brier", "contrast"):
        assert leak not in str(d["timing"])


def test_the_measured_efficiency_is_recorded_so_the_declared_one_can_die():
    """The declared 2.0 exists to be replaced by a measurement, and the night
    that replaces it has to record one.

    THE STUB MUST TAKE MEASURABLE TIME. The first version of this test used the
    instant stub, so every arm started and finished inside one tick of a
    Windows clock (~15 ms), the cell's wall time came out as exactly 0.0, and
    `measured_efficiency` correctly returned None because it will not divide by
    zero. It passed alone and failed under load — a flaky test asserting a
    timing property of a thing with no timing.

    A stub with no latency cannot test a latency measurement, which is the same
    sentence as the reason `DECLARED_CONCURRENCY_EFFICIENCY` exists at all.
    """
    import time

    from backend.tests.test_investigator_night import (_feats, good_llm,
                                                       no_tools)

    def slow(**kw):
        time.sleep(0.01)
        return good_llm(**kw)

    res = N.run_night({f"T{i}": _feats(float(i)) for i in range(4)},
                      k=3, llm_call=slow, tool_runner=no_tools,
                      dry_run=True, sandbox=True, arm_concurrency=5)
    m = N.measured_concurrency_efficiency(res)
    assert m["n_cells_measured"] >= 1
    assert m["declared_efficiency"] == N.DECLARED_CONCURRENCY_EFFICIENCY
    assert m["measured_efficiency"] is not None, (
        "the night recorded no measured efficiency, so nothing could ever "
        "replace the declared placeholder")
    assert m["mean_cell_wall_seconds"] > 0.0


def test_every_GUARD_constant_is_live_not_frozen_at_import():
    """The census, turned into a check.

    105 module constants are used as default arguments across
    `backend/services`, and most are harmless — a lookback window or a seed
    read once is fine. The dangerous subclass is narrow and precise:

      * a constant a GUARD reads to decide whether to refuse, and
      * a constant whose entire purpose is to be REPLACED by a measurement.

    `DECLARED_CONCURRENCY_EFFICIENCY` is both. It exists to be replaced after
    the first concurrent night measures the real speedup, and frozen at import
    that replacement would have required a source edit and silently done
    nothing anywhere else.
    """
    import backend.services.investigator_night as _N

    probes = {
        "MEASURED_CALL_SECONDS": (
            3600.0, lambda: _N.projected_night_minutes(k=40, n_arms=5)),
        "MEASURED_CALLS_PER_CELL": (
            999.0, lambda: _N.projected_night_minutes(k=40, n_arms=5)),
        "DECLARED_CONCURRENCY_EFFICIENCY": (
            5.0, lambda: _N.projected_night_minutes(k=40, n_arms=5,
                                                    arm_concurrency=5)),
        "MEASURED_MAX_ARM_CALLS": (
            500, lambda: _N.projected_night_minutes(k=40, n_arms=5,
                                                    arm_concurrency=5)),
    }
    for name, (patched, call) in probes.items():
        real = getattr(_N, name)
        before = call()
        try:
            setattr(_N, name, patched)
            after = call()
        finally:
            setattr(_N, name, real)
        assert after != before, (
            f"{name} is bound as a default argument again — patching the "
            f"module attribute changed nothing the function reads, so the "
            f"guard that depends on it cannot be exercised or reconfigured")


def test_the_FRESHNESS_guard_constant_is_live_too():
    import backend.services.investigator_night as _N
    stale = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    assert _N.assert_decision_time_fresh(stale) > 0     # 30 < 45, allowed
    real = _N.MAX_DECISION_LAG_MINUTES
    try:
        _N.MAX_DECISION_LAG_MINUTES = 5
        with pytest.raises(_N.DecisionTimeStale):
            _N.assert_decision_time_fresh(stale)
    finally:
        _N.MAX_DECISION_LAG_MINUTES = real
