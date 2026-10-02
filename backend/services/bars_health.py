"""One loud line for the age of the bar panels: DEGRADED when a closed session is missing.

WHY (2026-10-02)
================
`scripts.pull_bars_refresh` failed with HTTP 400 on every attempt from
2026-09-29 22:30 UTC to 2026-10-02 (one Yahoo-spelled ticker, `BRK-B`, in the
forecast-only side panel). Each receipt said `refused` correctly, and nobody
read them for three days: the forecast grader, the leaderboard, the straddle
log, alert grading and nn_lab all read bars frozen at 2026-09-28 while their
own rows said "ok" or "nothing to do". `bars_age()` had always computed the
sessions_old number; nothing put it at the TOP of anything a human reads.

THE RULE: on any day, if the gated panels (`pull_bars_refresh.GATED_PANELS`)
are missing one or more CLOSED XNYS sessions, the state is DEGRADED and the
line says how many and since when. An unreadable panel is DEGRADED too
(missing evidence is never fresh). This is stricter than
`config.BARS_MAX_AGE_SESSIONS`, which gates ACTING (u_plan); this gates
whether a reader is told.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional


def check(now_utc: Optional[datetime] = None, *,
          age_fn: Optional[Callable[..., dict]] = None) -> dict:
    """`{"state": "OK"|"DEGRADED", "line": str, "sessions_old": int|None, ...}`.

    `age_fn(now_utc=..., max_age_sessions=0)` is the seam (tests inject one);
    production uses `scripts.pull_bars_refresh.bars_age`, which reads the
    parquet's own `date` column, never its mtime. A raising age read is
    DEGRADED, naming the exception -- never OK by default.
    """
    try:
        if age_fn is None:
            from scripts.pull_bars_refresh import bars_age as age_fn   # noqa: PLC0415
        age = age_fn(now_utc=now_utc, max_age_sessions=0)
    except Exception as exc:                                       # noqa: BLE001
        return {"state": "DEGRADED", "sessions_old": None, "newest": None,
                "line": (f"DEGRADED bars: CANNOT DETERMINE the panel age "
                         f"({type(exc).__name__}: {str(exc)[:160]})")}
    n = age.get("sessions_old")
    newest = age.get("newest")
    last = age.get("last_closed_session")
    if n is None:
        return {"state": "DEGRADED", "sessions_old": None, "newest": newest,
                "last_closed_session": last,
                "line": (f"DEGRADED bars: panel age UNKNOWN (a gated panel is absent or "
                         f"has no readable date); last closed session {last}")}
    if int(n) >= 1:
        return {"state": "DEGRADED", "sessions_old": int(n), "newest": newest,
                "last_closed_session": last,
                "line": (f"DEGRADED bars: newest bar {newest} is {n} closed session(s) "
                         f"behind {last} -- every grader, ranker and alert grade reading "
                         f"these panels is stale; see prices_2025_26/bars_refresh/ receipts")}
    return {"state": "OK", "sessions_old": 0, "newest": newest,
            "last_closed_session": last,
            "line": f"bars OK: newest {newest} = last closed session {last}"}
