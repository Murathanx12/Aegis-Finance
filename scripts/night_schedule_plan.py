"""Derive the daily pre-open and post-close start times from the real calendar.

    python -m scripts.night_schedule_plan --k 40 --arms 5 --days 7
    python -m scripts.night_schedule_plan --k 40 --arms 5 --schtasks

IT PLANS. IT DOES NOT LAUNCH, AND IT WILL NOT BE ARMED TODAY.
=============================================================
This prints times and, on request, the `schtasks` command that WOULD register
them. It never starts a night, never registers a task, and imports nothing the
night does not already import.

That separation is the point rather than caution for its own sake:

* **A paid night is not a daily job.** It has a declared population named in a
  receipt before the run, one attempt, and a multiplicity budget that attaches
  to the CALENDAR — so a cron that fires one every day spends error rate on
  trials nobody reserved and produces receipts against no hypothesis. What
  belongs on a timer is the FREE work: data pulls, campaign resolution, the
  morning brief. A paid night belongs on a timer only once a campaign has
  declared how many of them it is buying and against what.
* **Automating tonight's run is the one thing not to do today.** The standing
  rule for a paid one-shot is attended, one attempt, refusal is a finding.

WHY THE TIME IS DERIVED AND NOT WRITTEN DOWN
============================================
09:30 New York is 13:30 UTC only under EDT. From 2026-11-01 the same wall-clock
schedule silently starts an hour later relative to the bell, and the failure is
invisible: the run finishes fine, and the tool arms simply read an hour of live
session while being graded from a pre-open stamp. So every time below comes from
`exchange_calendars` via the same accessor the guard uses, and every proposed
start is then handed to `assert_night_fits_preopen` AT arm_concurrency=1 and
must PASS. A schedule that has not been through the guard it will face is a
guess with a clock attached.

`arm_concurrency=1` deliberately, and not because the runner is serial: the
guard's verdict depends on a number the CALLER supplies, so a plan validated on
the pessimistic branch does not depend on that number being right.

THE TARGET, DECLARED
====================
`TARGET_LATENCY_MULTIPLE` — start early enough that the run still finishes
before the bell if every call takes this multiple of its measured mean. 1.9 is
the value Order 11 chose for the 17:00 start (139-min projection, 131 minutes of
headroom). Later would be fresher and thinner; earlier costs information for no
safety gain, because the binding constraint is the bell, not the clock.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

from backend.services import investigator_night as N
from backend.services import market_sessions as MS

#: Tolerate this multiple of the measured mean call latency and still land
#: before the bell. Declared, not tuned to produce a convenient hour.
TARGET_LATENCY_MULTIPLE = 1.9

#: Post-close runs wait this long after the bell for the tape to settle.
POST_CLOSE_DELAY_MINUTES = 30


def _next_close(after):
    """Session close from the same calendar the guard reads.

    Reaches into `market_sessions._xnys` because the public module has
    `next_session_open` and no `next_session_close`. Adding one is a source edit
    to a module the night imports, which is not something to do hours before the
    run it guards — it is the first thing to tidy afterwards.
    """
    import pandas as pd
    cal = MS._xnys()
    t = pd.Timestamp(after).tz_convert("UTC") if pd.Timestamp(after).tzinfo \
        else pd.Timestamp(after).tz_localize("UTC")
    return cal.next_close(t).to_pydatetime()


def plan_one(open_utc, *, k: int, arms: int) -> dict:
    # Serial, deliberately, and matching what the guard below will decide on: a
    # start time that survives the pessimistic branch does not depend on an
    # input the planner cannot verify. Measured against Night 1, every
    # concurrency branch UNDER-projects the real wall clock.
    minutes = N.projected_night_minutes(
        k=k, n_arms=arms, arm_concurrency=1,
        calls_per_cell=N.derive_calls_per_cell()["value"])
    start = open_utc - timedelta(minutes=minutes * TARGET_LATENCY_MULTIPLE)
    row = {"session": open_utc.date().isoformat(),
           "open_utc": open_utc, "projected_minutes": round(minutes, 1),
           "pre_open_start_utc": start}
    # The plan is only a plan until the guard it will face accepts it.
    #
    # ONLY the guard's own exception is caught. The first version used a bare
    # `except Exception`, misspelled the guard's name, and printed REFUSED six
    # times — an AttributeError wearing a domain verdict, which reads as "the
    # calendar says no" and is the most persuasive possible way to be wrong. A
    # catch-all around the thing whose refusal you are reporting cannot tell a
    # refusal from a typo.
    try:
        # No concurrency argument: the guard decides on the SERIAL branch
        # always, and derives the runner's concurrency for the record. Passing a
        # number here is how the planner and the runner came to disagree
        # five-fold on Night 1 with nothing positioned to notice.
        rep = N.assert_night_fits_before_open(k=k, n_arms=arms, now=start)
        row["guard"] = "PASS"
        row["headroom_minutes"] = rep["minutes_of_headroom"]
        row["lead_hours"] = rep["hours_until_open"]
    except N.NightWouldSpanTheOpen as e:
        row["guard"] = "REFUSED"
        row["why"] = str(e).split(". ")[0]
    row["post_close_start_utc"] = (_next_close(open_utc)
                                   + timedelta(minutes=POST_CLOSE_DELAY_MINUTES))
    return row


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=40, help="names per arm")
    ap.add_argument("--arms", type=int, default=5)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--schtasks", action="store_true",
                    help="print the Windows command that WOULD register it")
    a = ap.parse_args()

    now = datetime.now(timezone.utc)
    local_offset = datetime.now().astimezone().utcoffset() or timedelta(0)

    def loc(t):
        return (t + local_offset).strftime("%a %H:%M")

    print("=" * 76)
    print("NIGHT SCHEDULE — derived from XNYS, validated by the guard at conc=1")
    print("=" * 76)
    print(f"  now {now.strftime('%Y-%m-%d %H:%M')}Z / local "
          f"{(now + local_offset).strftime('%H:%M')}  "
          f"(UTC{local_offset.total_seconds() / 3600:+.0f})")
    print(f"  k={a.k} names x {a.arms} arms, {N.MEASURED_CALL_SECONDS}s mean "
          f"call, target {TARGET_LATENCY_MULTIPLE}x latency tolerance\n")
    print(f"  {'session':<12} {'open':>7} {'pre-open start':>22} "
          f"{'headroom':>9}  {'post-close start':>20}")

    rows, cursor = [], now
    for _ in range(a.days):
        op = MS.next_session_open(cursor)
        r = plan_one(op, k=a.k, arms=a.arms)
        rows.append(r)
        pre, post = r["pre_open_start_utc"], r["post_close_start_utc"]
        head = (f"{r['headroom_minutes']:.0f}m" if r["guard"] == "PASS"
                else "REFUSED")
        print(f"  {r['session']:<12} {op.strftime('%H:%M')}Z "
              f"{pre.strftime('%H:%M')}Z / {loc(pre):>12}  {head:>9}  "
              f"{post.strftime('%H:%M')}Z / {loc(post):>12}")
        cursor = op + timedelta(minutes=1)

    bad = [r for r in rows if r["guard"] != "PASS"]
    if bad:
        print(f"\n  {len(bad)} planned start(s) the guard REFUSES — those days "
              f"do not get a night:")
        for r in bad:
            print(f"    {r['session']}  {r.get('why', '')[:90]}")

    print("\n" + "-" * 76)
    print("WHAT IS SAFE TO PUT ON A TIMER TODAY, AND WHAT IS NOT")
    print("-" * 76)
    print("  SAFE (free, idempotent, no error-rate spent):")
    print("    * campaign resolution and receipt writing")
    print("    * the morning brief and data pulls")
    print("    * `night_cache_sentinel --before` as a pre-run canary")
    print("  NOT SAFE without a declared campaign:")
    print("    * the paid night. One attempt, a population named in a receipt")
    print("      before the run, and a multiplicity budget that attaches to the")
    print("      calendar — a daily cron spends error rate on trials nobody")
    print("      reserved, and produces receipts against no hypothesis.")

    if a.schtasks:
        first = next((r for r in rows if r["guard"] == "PASS"), None)
        if first is None:
            print("\n  no passing start to register")
            return 1
        t = (first["pre_open_start_utc"] + local_offset).strftime("%H:%M")
        print("\n" + "-" * 76)
        print("THE COMMAND — NOT RUN. Registering it is a decision, not a step.")
        print("-" * 76)
        print("  Two properties before anyone pastes it: the daily time is")
        print("  WALL-CLOCK and the bell is not, so it drifts an hour at the")
        print("  DST change and must be re-derived from this script each time;")
        print("  and the task must re-run the guard at launch, because a plan")
        print("  made yesterday is not a permission granted today.\n")
        print(f'  schtasks /Create /TN "AegisNightPreOpen" /SC DAILY /ST {t} '
              f'/TR "cmd /c cd /d {sys.path[0] or "."} && '
              f'python -m scripts.night_cache_sentinel --before"')
        print("\n  Note what that /TR runs: the SENTINEL, not a night. Wiring a")
        print("  paid run to a timer is a separate decision and not this one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
