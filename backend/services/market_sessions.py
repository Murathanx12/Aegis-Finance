"""The next US equity session, from an exchange calendar rather than arithmetic.

THE DEFECT THIS EXISTS TO REMOVE (found 2026-08-15, in review)
==============================================================
`assert_night_fits_before_open` computed the next opening bell like this::

    open_today = now.replace(hour=13, minute=30, second=0, microsecond=0)
    if open_today <= now:
        open_today += timedelta(days=1)

Two independent errors, both of which authorise a night that should be refused:

1. **No calendar.** Today is Saturday 2026-08-15. That code says the next
   opening bell is **Sunday 2026-08-16 at 13:30 UTC**. There is no Sunday
   session. The same arithmetic invents a session on every weekend day, every
   NYSE holiday and the whole of a long weekend.
2. **No DST.** 09:30 America/New_York is 13:30 UTC only while New York is on
   EDT. From the first Sunday in November it is **14:30 UTC**, and the
   constants were permanently `13, 30`. The guard would have been an hour
   pessimistic in winter — which is the safe direction, and therefore the kind
   of error that survives for years without anyone noticing it is there.

Both are the house failure mode stated exactly: **correct arithmetic against
the wrong world.** Neither is visible from the guard's own tests, because the
tests supplied the same fabricated calendar the guard used. (Every timestamp in
`test_night_fits_before_open.py` was on Saturday 2026-08-15, asserting a 13:30Z
open on a day the exchange is shut.)

WHY A LIBRARY AND NOT A HOLIDAY TABLE
=====================================
`backend/config.py` already carries a hand-written `US_MARKET_HOLIDAYS` set. It
is correct — and it runs out at the end of 2027, at which point it does not
fail, it silently starts calling 2028-01-01 a trading day. A hand table is a
promise to keep editing a file forever, and the failure mode of forgetting is a
guard that quietly stops guarding. `exchange_calendars` maintains XNYS sessions
(weekends, holidays, ad-hoc closures, the 1885-onward history and the DST
transitions) as a package that can be upgraded.

`test_market_sessions.py` cross-checks the hand table against the library and
goes red when the table stops covering the year ahead, so the expiry is a build
failure instead of a wrong answer.

WHAT IS DELIBERATELY NOT MODELLED
=================================
**Early closes.** The day after Thanksgiving and Christmas Eve close at 13:00
ET. They open at 09:30 ET like any other session, and this module is only ever
asked when the bell RINGS. An early close cannot make a pre-open night late, so
modelling it here would be machinery with no consequence.

REFUSAL, NOT FALLBACK
=====================
If the calendar cannot be loaded this module raises. The repo's usual rule is
`try/except ImportError` with a fallback, and it is the wrong rule here: the
fallback available is exactly the weekday arithmetic being deleted, and a paid
night certified against a fabricated Sunday session is worse than a night that
does not run. Same reasoning as `verify_or_refuse` ignoring
`AEGIS_IIF1_PREREG_ABSENT_OK` — a context that cannot read the real rule must
not certify anything against it.
"""

from __future__ import annotations

import datetime as _dt
from functools import lru_cache

#: The calendar is built once and cached; construction parses decades of
#: sessions and costs about a second.
_CALENDAR = "XNYS"
_START = "1990-01-01"
_END = "2035-12-31"


class SessionCalendarUnavailable(RuntimeError):
    """The exchange calendar could not be consulted, so nothing is asserted."""


@lru_cache(maxsize=1)
def _xnys():
    try:
        import exchange_calendars as xc
    except ImportError as exc:                                   # pragma: no cover
        raise SessionCalendarUnavailable(
            "exchange_calendars is not installed, so the next opening bell "
            "cannot be determined. This is a refusal and not a fallback: the "
            "only fallback available is the weekday arithmetic that invented a "
            "Sunday session, and a night certified against a session that does "
            "not exist is worse than a night that does not run. "
            "pip install exchange_calendars") from exc
    return xc.get_calendar(_CALENDAR, start=_START, end=_END)


def _ts(when):
    """Normalise to a tz-aware pandas Timestamp in UTC."""
    import pandas as pd

    if when is None:
        when = _dt.datetime.now(_dt.timezone.utc)
    t = pd.Timestamp(when)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def next_session_open(now=None) -> _dt.datetime:
    """The next real opening bell strictly after `now`, as tz-aware UTC.

    During a session this returns the NEXT session's open, not the one already
    rung — which is the behaviour the night guard wants: a run that starts
    after the bell is a run for tomorrow's session.
    """
    t = _ts(now)
    cal = _xnys()
    if not (cal.first_minute <= t <= cal.last_minute):
        raise SessionCalendarUnavailable(
            f"{t.isoformat()} is outside the loaded {_CALENDAR} calendar "
            f"({_START}..{_END}); widen it rather than guessing")
    return cal.next_open(t).to_pydatetime()


def is_session(day) -> bool:
    """True iff `day` is a real trading session for XNYS."""
    import pandas as pd

    d = pd.Timestamp(day)
    if d.tzinfo is not None:
        d = d.tz_convert("UTC")
    return bool(_xnys().is_session(d.normalize().tz_localize(None)))


def sessions_in_year(year: int) -> list[_dt.date]:
    """Every session date in a calendar year — used to audit hand tables."""
    cal = _xnys()
    idx = cal.sessions_in_range(f"{year}-01-01", f"{year}-12-31")
    return [d.date() for d in idx]


def non_sessions_in_year(year: int, *, weekdays_only: bool = True
                         ) -> list[_dt.date]:
    """Weekdays in `year` on which the exchange did NOT trade (holidays)."""
    sessions = set(sessions_in_year(year))
    out, d = [], _dt.date(year, 1, 1)
    while d.year == year:
        if d not in sessions and (not weekdays_only or d.weekday() < 5):
            out.append(d)
        d += _dt.timedelta(days=1)
    return out
