"""ONE frozen execution policy, and the reasons it is one rule rather than three.

THE RULE
========
    fill session = the first trading session STRICTLY AFTER the calendar date
                   of `public_at` (New York), at that session's OPEN.

That is the whole policy. It does not branch on time of day, and that is
deliberate:

* **During market hours.** A filing accepted at 10:04 is theoretically tradable
  at 10:05, but a paper account that claims an intraday fill claims a fill price
  nobody has to honour and a reaction time no human process had. Next open is
  the conservative reading, and consistency across lanes matters more here than
  squeezing a session.
* **After the close.** Handled by the same rule with no special case. This is
  the case that produced a real defect elsewhere: a 13G accepted at 21:55 UTC is
  16:55 ET — after the close — and a policy that treated the FILING DATE as
  tradable would have helped itself to most of a session it never had.
* **Weekend / holiday.** Also the same rule, because sessions are taken from the
  price index rather than from a calendar we would have to maintain. A session
  is a day the market actually printed; a holiday simply is not in the index.

NO RETROACTIVE FILLS
====================
`first_executable_session` is a pure function of `public_at` and the session
list. Nothing may fill before the lane was seeded — enforced by the engine, and
stated here because this is where someone would be tempted to add "just backfill
the last month to make the NAV interesting".

WHAT THIS FILE DOES NOT DO
==========================
It does not decide size, eligibility or exit. One frozen policy per concern, so
a change to sizing cannot silently change timing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
except Exception:                                              # pragma: no cover
    NY = timezone(timedelta(hours=-5))

POLICY_ID = "next_session_open_after_public_at@v1"


class NotExecutable(ValueError):
    """No session exists after this timestamp in the panel we have."""


@dataclass(frozen=True)
class ExecutionPolicy:
    """Named so a receipt can state which policy produced its fills."""

    policy_id: str = POLICY_ID
    price_point: str = "open"
    same_session_fills: bool = False
    retroactive_fills: bool = False


def to_ny_date(ts: "str | datetime") -> date:
    """The New York calendar date of an instant.

    New York because every boundary that matters is one: the close, an 8-K
    accepted at 16:05, a filing stamped in UTC. A naive string is read as UTC,
    then converted — reading it as local time would move the boundary by five
    hours in the direction that leaks.
    """
    if isinstance(ts, datetime):
        d = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    else:
        s = str(ts).replace("Z", "+00:00")
        try:
            d = datetime.fromisoformat(s)
        except ValueError:
            return date.fromisoformat(str(ts)[:10])
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(NY).date()


def first_executable_session(public_at: "str | datetime",
                             sessions: "list[date]") -> date:
    """The session a signal disclosed at `public_at` may first be filled in.

    `sessions` must be sorted ascending and is the list of days the market
    actually printed — normally the index of the benchmark's price history.
    """
    d = to_ny_date(public_at)
    for s in sessions:
        if s > d:
            return s
    raise NotExecutable(
        f"no trading session after {d} is present in the price panel — the "
        f"signal cannot be filled yet, and inventing a fill date would be the "
        f"whole failure this policy exists to prevent")
