"""KNOWN-ANSWER tests for the opening bell. The guard was right about a world.

WHY THIS FILE EXISTS, AND WHY IT IS ALL KNOWN ANSWERS
=====================================================
`assert_night_fits_before_open` computed the next opening bell as "today at
13:30 UTC, plus one calendar day if that has passed". On Saturday 2026-08-15 —
the day it was reviewed — that returns **Sunday 2026-08-16 13:30Z**, a session
that does not exist. From the first Sunday in November it is an hour early,
because 09:30 America/New_York is 13:30 UTC only under EDT.

The guard's own test file could not have caught either one: every timestamp in
`test_night_fits_before_open.py` was on **Saturday 2026-08-15**, asserting a
13:30Z open on a day the exchange is shut. The tests supplied the same
fabricated calendar the code used, so the two agreed perfectly and were both
wrong. That is the CI lesson from earlier the same day in a different costume —
**two green signals can measure different worlds** — and the answer is the same
one: pin the real world explicitly, by known answer, not by re-running the
implementation's arithmetic inside the assertion.

Every date below is checkable against a published NYSE calendar without running
any of this code.
"""

from __future__ import annotations

import datetime as dt

import pytest

from backend.services import market_sessions as MS


def _utc(y, m, d, hh=0, mm=0):
    return dt.datetime(y, m, d, hh, mm, tzinfo=dt.timezone.utc)


# ── weekends: the defect, stated as the calendar sees it ────────────────────

def test_SATURDAY_2026_08_15_opens_on_MONDAY_the_17th():
    """The exact case that was live when this was found.

    The old arithmetic answered Sunday 2026-08-16 13:30Z.
    """
    nxt = MS.next_session_open(_utc(2026, 8, 15, 14, 18))
    assert nxt == _utc(2026, 8, 17, 13, 30)
    assert nxt.date().strftime("%A") == "Monday"


def test_SUNDAY_2026_08_16_opens_on_MONDAY_not_on_SUNDAY():
    """The date the paid night was ordered for."""
    assert MS.next_session_open(_utc(2026, 8, 16, 11, 0)) == \
        _utc(2026, 8, 17, 13, 30)


def test_immediately_after_the_FRIDAY_close_the_next_bell_is_MONDAY():
    assert MS.next_session_open(_utc(2026, 8, 14, 20, 5)) == \
        _utc(2026, 8, 17, 13, 30)


def test_saturday_and_sunday_are_not_sessions():
    assert not MS.is_session(dt.date(2026, 8, 15))
    assert not MS.is_session(dt.date(2026, 8, 16))
    assert MS.is_session(dt.date(2026, 8, 17))


# ── DST: 13:30 is not a constant ────────────────────────────────────────────

def test_a_normal_EDT_day_opens_at_1330_UTC():
    assert MS.next_session_open(_utc(2026, 8, 17, 6, 0)) == \
        _utc(2026, 8, 17, 13, 30)


def test_a_normal_EST_day_opens_at_1430_UTC_not_1330():
    """The second half of the defect: the constants were permanently 13:30."""
    assert MS.next_session_open(_utc(2026, 1, 15, 6, 0)) == \
        _utc(2026, 1, 15, 14, 30)
    assert MS.next_session_open(_utc(2026, 12, 8, 6, 0)) == \
        _utc(2026, 12, 8, 14, 30)


def test_the_first_session_after_the_autumn_DST_switch_moves_by_an_hour():
    """2026-11-01 is the US fallback. Friday before is EDT, Monday after EST."""
    fri = MS.next_session_open(_utc(2026, 10, 30, 6, 0))
    mon = MS.next_session_open(_utc(2026, 11, 2, 6, 0))
    assert fri == _utc(2026, 10, 30, 13, 30)
    assert mon == _utc(2026, 11, 2, 14, 30)
    assert (mon.hour - fri.hour) == 1


# ── holidays ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("holiday,next_session", [
    ("2026-01-01", "2026-01-02"),      # New Year's Day
    ("2026-02-16", "2026-02-17"),      # Presidents' Day
    ("2026-04-03", "2026-04-06"),      # Good Friday -> the following Monday
    ("2026-05-25", "2026-05-26"),      # Memorial Day
    ("2026-07-03", "2026-07-06"),      # July 4 observed on a Friday
    ("2026-11-26", "2026-11-27"),      # Thanksgiving
    ("2026-12-25", "2026-12-28"),      # Christmas on a Friday
])
def test_a_holiday_is_skipped_to_the_next_real_session(holiday, next_session):
    d = dt.date.fromisoformat(holiday)
    assert not MS.is_session(d)
    nxt = MS.next_session_open(_utc(d.year, d.month, d.day, 6, 0))
    assert nxt.date().isoformat() == next_session


def test_a_LONG_WEEKEND_is_three_days_not_one():
    """Friday evening before Presidents' Day: the next bell is Tuesday."""
    assert MS.next_session_open(_utc(2026, 2, 13, 22, 0)).date() == \
        dt.date(2026, 2, 17)


def test_columbus_day_and_veterans_day_ARE_sessions():
    """Federal holidays that the NYSE trades through — the reason
    `pandas.tseries.holiday.USFederalHolidayCalendar` is the wrong table."""
    assert MS.is_session(dt.date(2026, 10, 12))     # Columbus Day
    assert MS.is_session(dt.date(2026, 11, 11))     # Veterans Day


# ── during a session, the next bell is TOMORROW's ───────────────────────────

def test_during_the_session_the_next_bell_is_the_following_session():
    """A run that starts after the bell is a run for the NEXT session, and the
    guard's headroom must be measured against that one."""
    assert MS.next_session_open(_utc(2026, 8, 17, 15, 0)) == \
        _utc(2026, 8, 18, 13, 30)


def test_one_second_before_the_bell_still_returns_TODAYS_bell():
    assert MS.next_session_open(_utc(2026, 8, 17, 13, 29)) == \
        _utc(2026, 8, 17, 13, 30)


# ── the hand-written table in config.py, audited rather than trusted ────────

def test_the_hand_written_holiday_table_agrees_with_the_calendar():
    """`config.US_MARKET_HOLIDAYS` drives NAV freshness. It is correct today
    and it is a promise to keep editing a file forever."""
    from backend.config import US_MARKET_HOLIDAYS

    for year in (2026, 2027):
        real = {d.isoformat() for d in MS.non_sessions_in_year(year)}
        listed = {d for d in US_MARKET_HOLIDAYS if d.startswith(str(year))}
        assert listed == real, (
            f"config.US_MARKET_HOLIDAYS disagrees with XNYS for {year}: "
            f"missing {sorted(real - listed)}, extra {sorted(listed - real)}")


def test_the_hand_written_table_still_covers_the_year_AHEAD():
    """Goes red when the table expires, instead of silently calling
    2028-01-01 a trading day. That is the whole point of writing it down."""
    from backend.config import US_MARKET_HOLIDAYS

    horizon = dt.date.today().year + 1
    assert any(d.startswith(str(horizon)) for d in US_MARKET_HOLIDAYS), (
        f"US_MARKET_HOLIDAYS has no {horizon} entries — NAV freshness will "
        f"start treating {horizon} holidays as sessions. Extend it, or move "
        f"the scheduler onto backend.services.market_sessions.")


# ── refusal, not fallback ───────────────────────────────────────────────────

def test_a_date_outside_the_loaded_calendar_REFUSES(monkeypatch):
    """Silently extrapolating past the calendar's end is how the old
    arithmetic behaved. Out of range is a refusal."""
    with pytest.raises(MS.SessionCalendarUnavailable):
        MS.next_session_open(_utc(2099, 1, 4, 6, 0))


def test_a_missing_calendar_library_REFUSES_rather_than_guessing(monkeypatch):
    import builtins

    MS._xnys.cache_clear()
    real_import = builtins.__import__

    def no_xcals(name, *a, **k):
        if name == "exchange_calendars":
            raise ImportError("simulated absence")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_xcals)
    try:
        with pytest.raises(MS.SessionCalendarUnavailable, match="refusal"):
            MS.next_session_open(_utc(2026, 8, 17, 6, 0))
    finally:
        MS._xnys.cache_clear()


# ── the resolver on a non-session day ───────────────────────────────────────

def test_a_SUNDAY_resolution_cannot_invent_a_bar():
    """The order for 2026-08-16 says: do not fabricate a market outcome if the
    resolver lacks the required observation. 2026-08-16 is a Sunday.

    Verified rather than assumed. `resolve_one` counts BARS, not calendar days
    (`len(s) < horizon_days + 1`), so a non-session day contributes nothing to
    a window and cannot close one. A record with its bars grades against
    Friday's close, which is correct — Friday's close IS the last observation
    on or before Sunday. A record short of bars stays pending.
    """
    import pandas as pd

    from backend.services import belief_state as B

    rec = {"prediction_id": "t1", "ticker": "SPY", "made_at": "2026-08-07",
           "resolves_after": "2026-08-16", "horizon_days": 5,
           "probability": 0.6, "observable": "return_sign", "outcome": None,
           "benchmark": "SPY"}
    # All that can exist when the resolver runs on Sunday 2026-08-16.
    idx = pd.to_datetime(["2026-08-07", "2026-08-10", "2026-08-11",
                          "2026-08-12", "2026-08-13", "2026-08-14"])
    px = pd.DataFrame({"SPY": [100, 101, 102, 101, 103, 104]}, index=idx)

    got = B.resolve_one(dict(rec), px, today=dt.date(2026, 8, 16))
    assert got["outcome"] == 1
    d = got["resolution_detail"]
    assert d["n_bars"] == 6
    assert d["realised_return"] == pytest.approx(104 / 100 - 1), (
        "the outcome was not Friday's close — something supplied a price for "
        "a day the exchange was shut")

    # One more bar than exists: Sunday does not provide it.
    short = B.resolve_one(dict(rec, horizon_days=6, prediction_id="t2"), px,
                          today=dt.date(2026, 8, 16))
    assert short is None, (
        "a record whose window needs a bar that does not exist was graded — "
        "the window must be counted in bars, never in calendar days")
