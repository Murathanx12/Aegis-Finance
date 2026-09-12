"""D5 — the Monday-night device protocol.

MURAT, roadmap §10b: *"I will leave the PC open on Monday nights to let it test
on the device."* This is the thing that runs on those nights.

WHAT IT IS
==========
A loop that runs the `30m` cadence pass every thirty minutes across the US
session and writes ONE RECEIPT PER PASS — **including a pass with nothing to
do**, because a silent pass and a dead scheduler are the same observation
(invariant 15) and the only way to tell them apart afterwards is a file that
says "nothing to do" with a timestamp on it.

THE TWO CLOCKS, COMPUTED AND NOT ASSUMED
========================================
The machine runs on Asia/Hong_Kong (UTC+8); the market runs on
America/New_York. The declared window is **21:30 to 04:00 HKT**, which is
09:30 to 16:00 ET — the US cash session — and the mapping is recomputed per
run rather than hard-coded, because it moves twice a year with US DST and a
fixture that hard-codes a calendar moment fails the day after that moment
passes. Every receipt prints BOTH clocks.

FIVE REFUSALS, EACH FOR A FAILURE THAT HAPPENED
===============================================
1. **The power plan.** 2026-09-11: the machine entered Modern Standby at 23:58
   and left at 08:09, handing eight hours to a suspended CPU. The check is
   `night_factory.refuse_if_the_machine_may_sleep` — the SAME function the
   factory uses, not a second copy that can drift from it.
2. **The GPU line.** 2026-09-12 10:53 HKT: bugcheck 0x116 VIDEO_TDR_ERROR
   while an unattended job held 5.3 GB of 8 GB. Printed and put in the session
   receipt so the next crash does not need an archaeologist.
3. **No broker, ever.** This module imports no broker SDK and reaches no order
   path, and `test_monday_night.py` reads the AST to prove it rather than
   grepping for a word that also appears in this docstring.
4. **A STOP file.** `<receipt dir>/STOP` ends the loop between passes, cleanly,
   with a final receipt. A night that can only be ended by killing a process
   is a night that ends by killing the wrong process — 2026-09-06, one
   `taskkill /IM python.exe` took two other agents' jobs, a test suite and
   1,676 already-billed extractions.
5. **Its own PID, written down first.** Rule 6: kill by a PID you wrote down
   when you started the process, or do not kill.

    python -m scripts.monday_night --dry-run --passes 2 --interval-s 1
    python -m scripts.monday_night
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import date, datetime, time as dtime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger("monday_night")

HKT = ZoneInfo("Asia/Hong_Kong")
ET = ZoneInfo("America/New_York")

#: The declared window, in the clock Murat's PC runs on.
WINDOW_START_HKT = dtime(21, 30)
WINDOW_END_HKT = dtime(4, 0)            # the next morning

PASS_INTERVAL_S = 30 * 60
CADENCE = "30m"
STOP_FILENAME = "STOP"


def receipt_dir() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / "monday_night"


def stop_file() -> Path:
    return receipt_dir() / STOP_FILENAME


def window_in_et(day: date) -> dict:
    """The HKT window expressed in ET, recomputed for `day`.

    Not hard-coded: US DST moves this by an hour twice a year, and a constant
    that was right in March is wrong in November. `day` is the HKT calendar
    day the window OPENS on.
    """
    from datetime import timedelta

    start_hkt = datetime.combine(day, WINDOW_START_HKT, tzinfo=HKT)
    end_hkt = datetime.combine(day + timedelta(days=1), WINDOW_END_HKT,
                               tzinfo=HKT)
    return {
        "start_hkt": start_hkt.isoformat(), "end_hkt": end_hkt.isoformat(),
        "start_et": start_hkt.astimezone(ET).isoformat(),
        "end_et": end_hkt.astimezone(ET).isoformat(),
        "start_utc": start_hkt.astimezone(timezone.utc).isoformat(),
        "end_utc": end_hkt.astimezone(timezone.utc).isoformat(),
        "note": ("the window is declared in HKT because that is the clock the "
                 "machine runs on; the ET column is recomputed per run because "
                 "US DST moves it twice a year"),
    }


def inside_window(now: datetime) -> bool:
    """Is `now` (any tz) inside 21:30-04:00 HKT?"""
    t = now.astimezone(HKT).time()
    return t >= WINDOW_START_HKT or t < WINDOW_END_HKT


# --------------------------------------------------------------------------
# the passes


def one_pass(*, dry_run: bool, now: datetime, index: int) -> dict:
    """Run the cadence pass once and return the receipt payload.

    A `dry_run` pass does everything except mark: it resolves the window, the
    clock and the book list, and records `nothing_to_do` with the reason. That
    is what makes the two-pass rehearsal a rehearsal of THIS code rather than
    of a branch nobody runs at night.
    """
    payload: dict = {
        "pass_index": int(index), "dry_run": bool(dry_run),
        "ran_at_utc": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "ran_at_hkt": now.astimezone(HKT).isoformat(timespec="seconds"),
        "ran_at_et": now.astimezone(ET).isoformat(timespec="seconds"),
        "inside_declared_window": inside_window(now),
        "cadence": CADENCE, "pid": os.getpid(),
    }
    if dry_run:
        payload["nothing_to_do"] = True
        payload["reason"] = ("--dry-run: the clock, the window and this "
                             "receipt are exercised; no book was marked and "
                             "nothing was decided")
        return payload
    try:
        from backend.services import book_cadence as BC
        result = BC.run_pass(CADENCE, today=now.astimezone(ET).date())
        payload["n_marked"] = result.get("n_marked")
        payload["n_refused"] = result.get("n_refused")
        payload["nothing_to_do"] = bool(result.get("nothing_to_do"))
        payload["refused"] = result.get("refused")
        payload["receipt_path"] = result.get("path")
        payload["granularity"] = "daily_close"
        payload["intraday_bars_available"] = False
        payload["granularity_note"] = (
            "minute bars do not exist on this machine, so a 30m book is marked "
            "from the daily close. A 30-minute book graded from daily closes is "
            "not a 30-minute book's result.")
    except Exception as exc:                                   # noqa: BLE001
        payload["failed"] = f"{type(exc).__name__}: {exc}"[:400]
        payload["nothing_to_do"] = False
    return payload


def _write(payload: dict, *, write: bool) -> dict:
    if not write:
        return payload
    d = receipt_dir()
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S%fZ")
    # The PASS INDEX is in the name as well as the timestamp. Two passes thirty
    # minutes apart can never collide, but two passes in a one-second rehearsal
    # did: the first run of this loop's own test wrote pass 0 and pass 1 to the
    # same microsecond-stamped file and the second silently replaced the first.
    # A receipt that can overwrite another receipt is not a receipt.
    p = d / f"pass_{stamp}_{int(payload.get('pass_index', 0)):04d}.json"
    p.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    payload["path"] = str(p)
    return payload


def run(*, passes: int | None = None, interval_s: float = PASS_INTERVAL_S,
        dry_run: bool = False, write_receipts: bool = True,
        now_fn=None, sleeper=time.sleep, allow_outside_window: bool = False
        ) -> dict:
    """The loop. Returns the SESSION receipt; each pass writes its own too."""
    from scripts import night_factory as NF

    now_fn = now_fn or (lambda: datetime.now(timezone.utc))
    t0 = now_fn()
    session: dict = {
        "job": "monday_night", "lane": "D", "item": "D5",
        "pid": os.getpid(),
        "started_utc": t0.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "started_hkt": t0.astimezone(HKT).isoformat(timespec="seconds"),
        "window": window_in_et(t0.astimezone(HKT).date()),
        "interval_s": float(interval_s), "cadence": CADENCE,
        "dry_run": bool(dry_run),
        "stop_file": str(stop_file()),
        "passes": [], "stopped_by": None,
        "pid_note": ("this PID is written down BEFORE any work, because rule 6 "
                     "says kill by a PID you wrote down or do not kill. Never "
                     "`taskkill /F /IM python.exe`: on 2026-09-06 one such "
                     "call killed two other agents' jobs, a running suite and "
                     "1,676 already-billed extractions."),
    }

    refusal = NF.refuse_if_the_machine_may_sleep()
    session["power_plan"] = refusal or "OK (or CANNOT DETERMINE — see stdout)"
    if refusal:
        session["refused"] = refusal
        session["stopped_by"] = "power_plan"
        session["n_passes"] = 0
        session["finished_utc"] = datetime.now(timezone.utc).isoformat(
            timespec="seconds")
        print(refusal, flush=True)
        return _write_session(session, write_receipts)

    session["gpu"] = NF.gpu_line()
    print(session["gpu"], flush=True)
    print(f"monday_night pid {os.getpid()} | window "
          f"{session['window']['start_hkt']} .. {session['window']['end_hkt']} "
          f"HKT ({session['window']['start_et']} .. "
          f"{session['window']['end_et']} ET) | STOP file: {stop_file()}",
          flush=True)

    i = 0
    while True:
        if passes is not None and i >= int(passes):
            session["stopped_by"] = "pass_count"
            break
        if stop_file().is_file():
            session["stopped_by"] = "stop_file"
            print(f"STOP file present at {stop_file()} — ending cleanly",
                  flush=True)
            break
        now = now_fn()
        if not (allow_outside_window or dry_run) and not inside_window(now):
            session["stopped_by"] = "window_closed"
            break
        p = _write(one_pass(dry_run=dry_run, now=now, index=i),
                   write=write_receipts)
        session["passes"].append(p)
        print(f"pass {i}: {'nothing to do' if p.get('nothing_to_do') else ''}"
              f" marked={p.get('n_marked')} refused={p.get('n_refused')}"
              f" -> {p.get('path')}", flush=True)
        i += 1
        if passes is not None and i >= int(passes):
            session["stopped_by"] = "pass_count"
            break
        sleeper(float(interval_s))

    session["n_passes"] = len(session["passes"])
    session["finished_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return _write_session(session, write_receipts)


def _write_session(session: dict, write: bool) -> dict:
    if not write:
        return session
    d = receipt_dir()
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    p = d / f"session_{stamp}.json"
    p.write_text(json.dumps(session, indent=2, default=str), encoding="utf-8")
    session["session_path"] = str(p)
    return session


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--passes", type=int, default=None,
                    help="stop after N passes (default: until the window closes)")
    ap.add_argument("--interval-s", type=float, default=PASS_INTERVAL_S)
    ap.add_argument("--dry-run", action="store_true",
                    help="exercise the clock, the window and the receipts; "
                         "mark nothing")
    ap.add_argument("--allow-outside-window", action="store_true",
                    help="run even when the HKT clock is outside 21:30-04:00")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    s = run(passes=a.passes, interval_s=a.interval_s, dry_run=a.dry_run,
            allow_outside_window=a.allow_outside_window)
    print(json.dumps({k: v for k, v in s.items() if k != "passes"}, indent=2,
                     default=str))
    return 1 if s.get("refused") else 0


if __name__ == "__main__":                                   # pragma: no cover
    sys.exit(main())
