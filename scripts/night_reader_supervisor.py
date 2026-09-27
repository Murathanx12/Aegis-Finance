"""Keeps the Dow Jones reader working through the night with nobody watching
(2026-09-28, Murat: "make sure it works autonomous ... run the services we built
and in the morning we can analyze").

Every TICK: is the reader alive? if not, and the queue is not finished, start
it again (bounded). Every HOUR: claims -> three-source table -> source
scorecard, so the morning has graded output whatever time the reader stopped.
At the end time: stop the reader BY PID, run the three once more, exit.

It never touches the browser itself, never kills by image name, and stops on
its own STOP file, a missing HANDOFF_PC, or a disk below the floor.

    python -m scripts.night_reader_supervisor --until 08:00
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "backend" / "data" / "optimus"
DJ = DATA / "dowjones"
LOG = DJ / "night_reader_supervisor.jsonl"
STOP = DJ / "SUPERVISOR_STOP"
HANDOFF = DATA / "HANDOFF_PC"
THROTTLE = DATA / "news_corpus" / "dowjones" / "_throttle.log"
TICK_S = 300
HOURLY_S = 3600
MAX_RESTARTS = 20
QUICK_EXIT_S = 180          # a launch that ends this fast had nothing left to read
DISK_FLOOR_GB = 20.0
PY = str(REPO / ".venv" / "Scripts" / "python.exe")


def log(**row: object) -> None:
    row = {"t": datetime.now().astimezone().isoformat(timespec="seconds"), **row}
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def reader_pids() -> list[int]:
    """PIDs of OUR reader processes, matched on the command line (never on the
    image name). No psutil in this venv, so Windows is asked directly."""
    q = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object "
         "{ $_.CommandLine -match 'scripts[.]dowjones_pull' } | ForEach-Object { $_.ProcessId }")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", q], capture_output=True,
                           text=True, timeout=60, stdin=subprocess.DEVNULL,
                           creationflags=0x08000000)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [int(x) for x in (r.stdout or "").split() if x.strip().isdigit()]


def kill_pid(pid: int) -> bool:
    r = subprocess.run(["taskkill", "/PID", str(int(pid)), "/F"], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, creationflags=0x08000000)
    return r.returncode == 0


def loads() -> int:
    try:
        return sum(1 for _ in THROTTLE.open(encoding="utf-8", errors="replace"))
    except OSError:
        return -1


def launch(queue_cmd: Path) -> int:
    p = subprocess.Popen(["cmd.exe", "/c", str(queue_cmd)], cwd=str(REPO),
                         creationflags=0x08000000 | 0x00000200,   # no window, new group
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    return p.pid


def step(name: str, args: list[str], timeout: int) -> dict:
    t0 = time.time()
    try:
        r = subprocess.run([PY, "-m", *args], cwd=str(REPO), capture_output=True, text=True,
                           timeout=timeout, stdin=subprocess.DEVNULL,
                           creationflags=0x08000000)
        row = {"step": name, "rc": r.returncode, "seconds": round(time.time() - t0, 1),
               "tail": (r.stdout or "")[-400:], "err": (r.stderr or "")[-300:]}
    except subprocess.TimeoutExpired:
        row = {"step": name, "rc": "TIMEOUT", "seconds": timeout}
    log(**row)
    return row


def digest(claims_since: str) -> None:
    step("claims", ["scripts.dowjones_pull", "--claims", "--claims-since", claims_since], 1800)
    step("three_source", ["scripts.three_source_compare"], 300)
    step("scorecard", ["scripts.source_scorecard"], 1800)


def end_time(hhmm: str) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    now = datetime.now()
    end = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return end if end > now else end + timedelta(days=1)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--until", default="08:00", help="local HH:MM")
    ap.add_argument("--queue-cmd", default=str(DJ / "queue_run.cmd"))
    ap.add_argument("--claims-since", default="2026-07-01")
    a = ap.parse_args(argv)
    end = end_time(a.until)
    log(event="start", pid=os.getpid(), until=end.isoformat(timespec="minutes"))
    restarts, finished, last_launch, last_hourly, last_loads = 0, False, 0.0, time.time(), loads()
    why = "end time"
    while datetime.now() < end:
        if STOP.exists():
            why = "STOP file"
            break
        if not HANDOFF.exists():
            why = "HANDOFF_PC absent"
            break
        free = shutil.disk_usage(str(DATA)).free / 1e9
        pids = reader_pids()
        n = loads()
        log(event="tick", reader_procs=len(pids), page_loads_total=n,
            new_loads=n - last_loads, free_gb=round(free, 1), restarts=restarts)
        last_loads = n
        if free < DISK_FLOOR_GB:
            why = f"disk {free:.1f} GB under the {DISK_FLOOR_GB} GB floor"
            break
        if not pids and not finished:
            if last_launch and time.time() - last_launch < QUICK_EXIT_S:
                finished = True
                log(event="queue_finished", how="the last launch ended quickly")
            elif restarts >= MAX_RESTARTS:
                finished = True
                log(event="gave_up", restarts=restarts)
            else:
                restarts += 1
                last_launch = time.time()
                log(event="relaunch", n=restarts, launcher_pid=launch(Path(a.queue_cmd)))
        if time.time() - last_hourly >= HOURLY_S:
            last_hourly = time.time()
            digest(a.claims_since)
        time.sleep(TICK_S)
    stopped = []
    for pid in reader_pids():                      # by PID, matched on the command line
        if kill_pid(pid):                          # each is one of OUR reader processes
            stopped.append(pid)
    log(event="stopping", why=why, reader_pids_stopped=stopped)
    digest(a.claims_since)
    log(event="end", why=why, restarts=restarts, page_loads_total=loads())
    return 0


if __name__ == "__main__":
    sys.exit(main())
