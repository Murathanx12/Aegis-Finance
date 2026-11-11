"""Suspend ONE named PID (a job this builder started) while machine available RAM is low.

    python -m scripts.night.ram_guard <pid> [--low 2.5] [--high 4.0]

Suspends when available < low GB, resumes when > high GB, exits when the PID is gone.
Never touches any other process. Logs every transition to stdout.
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime

import psutil


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pid", type=int)
    ap.add_argument("--low", type=float, default=2.5)
    ap.add_argument("--high", type=float, default=4.0)
    a = ap.parse_args(argv)
    p = psutil.Process(a.pid)
    print(f"{datetime.now():%H:%M:%S} guarding pid {a.pid}: {' '.join(p.cmdline())[:120]}", flush=True)
    suspended = False
    peak = 0.0
    while p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
        avail = psutil.virtual_memory().available / 1e9
        try:
            peak = max(peak, p.memory_info().rss / 1e9)
        except psutil.Error:
            break
        if not suspended and avail < a.low:
            p.suspend()
            suspended = True
            print(f"{datetime.now():%H:%M:%S} SUSPEND avail {avail:.2f} GB rss {peak:.2f}", flush=True)
        elif suspended and avail > a.high:
            p.resume()
            suspended = False
            print(f"{datetime.now():%H:%M:%S} RESUME avail {avail:.2f} GB", flush=True)
        time.sleep(5)
    print(f"{datetime.now():%H:%M:%S} pid {a.pid} gone; peak rss {peak:.2f} GB", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
