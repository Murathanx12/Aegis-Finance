"""A FAKE night job that exists only to test the factory's time box.

The queue's jobs run for hours and cost real compute, so the time box was never
exercised by anything cheap -- and on 2026-09-11 `N3_frozen_embedding_head` ran
11h16m (about 2.9h of it awake; the machine was in Modern Standby for the rest)
under a declared `<= 60 min` box and the factory never wrote a TIMEOUT receipt.
This module is the cheap exercise: it sleeps for as long as it is told, writes a
heartbeat file while it sleeps, and writes a receipt only if it reaches the end.

`scripts.night_factory._job_module` routes to this module for, and only for,
job ids beginning with `SMOKE_`. No real queue may contain such a name -- the
test `test_night_factory_timebox.py::test_no_smoke_job_is_in_a_real_queue`
fails if one ever does.

    python -m scripts.night_smoke_job SMOKE_sleeper --out r.json --sleep-s 30
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

#: prefix the factory dispatches here; never a real job
SMOKE_PREFIX = "SMOKE_"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("--out", required=True)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--sleep-s", type=float, default=1.0)
    ap.add_argument("--heartbeat", help="file this process rewrites every 0.1s while it sleeps")
    ap.add_argument("--exit-code", type=int, default=0)
    # accepted and ignored so the factory can pass its usual flags
    ap.add_argument("--hours", type=float, default=0.0)
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args(argv)

    if not a.job.startswith(SMOKE_PREFIX):
        print(f"REFUSED: {a.job!r} is not a {SMOKE_PREFIX}* job", flush=True)
        return 2

    print(f"[smoke] {a.job} pid {os.getpid()} sleeping {a.sleep_s}s", flush=True)
    beat = Path(a.heartbeat) if a.heartbeat else None
    end = time.time() + a.sleep_s
    n = 0
    while time.time() < end:
        if beat is not None:
            n += 1
            beat.write_text(f"{n} {time.time():.3f}", encoding="utf-8")
        time.sleep(0.1)

    Path(a.out).write_text(json.dumps({
        "job": a.job,
        "run": a.run,
        "verdict": "SMOKE",
        "headline": f"slept {a.sleep_s}s and reached the end (pid {os.getpid()}, {n} beats)",
        "slept_s": a.sleep_s,
        "pid": os.getpid(),
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, indent=1), encoding="utf-8")
    print("[smoke] receipt written", flush=True)
    return a.exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
