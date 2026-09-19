"""THE ALWAYS-ON LAB — one supervisor, ten loops, whenever the PC is on.

    python -m scripts.always_on_lab --dry-run    # print the plan; touch nothing
    python -m scripts.always_on_lab              # the loop, until STOP
    python -m scripts.always_on_lab --ticks 1    # one tick, then exit
    python -m scripts.always_on_lab --schtasks   # print the registration, run nothing
    python -m scripts.always_on_lab --acceptance # the three-date acceptance receipt

Source: Murat, 2026-09-13 — "do a learning lab for it to continuously learn ...
live whenever pc is on, fetching live data for news the LLM and the engine is
gathering data and learning, decision vs reality, upcoming dates and
possibilities, linkedin theory, business pivot to ai, motivation, holders, the
business, the future anything."

Spec: `docs/research_notes/2026-09-13/spec_always_on_lab.md`.

WHAT THIS IS
============
ARBITRATION AND CADENCE. It is NOT a rewrite of `daily_pass.py`,
`night_factory.py`, `monday_night.py`, `night_l2_typed_events.py` or any of the
E1-E5/L1-L4/M1-M5 modules — every one of those already exists, is tested, and
has its own receipt discipline. This supervisor decides WHEN each existing
driver gets to run, makes sure two of them never fight over the GPU or the
model server, and writes ONE status file a human or the desktop board can read
without opening eight receipt folders.

A supervisor that re-implements `refuse_if_the_machine_may_sleep()` or the
STOP-file convention instead of IMPORTING them is a second copy of a rule that
will drift from the first. Every guard here is imported:

* `scripts.night_factory.refuse_if_the_machine_may_sleep` — the power plan;
* `backend.services.llama_server.status` — and, since 2026-09-18,
  `start()` when nothing is listening; NEVER `stop()`;
* `backend.services.ledger_retrieval.visible_at` — the hindsight gate;
* `scripts.news_pull.pull_all` / `scripts.night_l2_typed_events.L2_typed_events`
  — the loops' actual work.

FIVE THINGS IT REFUSES, BY NAME
===============================
* `ALREADY_RUNNING: pid <n>` — a live supervisor holds the lock (spec 1.2);
* `POWER_PLAN_ALLOWS_SLEEP` — the GPU loops pause, the news pull does not (1.3);
* `CLOUD_READER_NOT_IMPLEMENTED` — `AEGIS_L2_READER=cloud` with no reader
  registered; never a silent fallback to local called a cloud run (3.2);
* `DAILY_SPEND_CAP_REACHED` — checked BEFORE a cloud call, not after (5);
* `NIGHT_FACTORY_ALREADY_RUNNING` / `DAILY_PASS_RUNNING` /
  `MONDAY_NIGHT_RUNNING` / `NIGHT_LAUNCHER_RUNNING` — the idle queue and the
  dispatch loops yield to the scheduled owners (4); a dispatch NEVER kills;
* `ALREADY_RAN_TODAY` / `NOT_DUE` / `WEEKEND_NOT_DUE` / `DRIVER_BOX_EXCEEDED`
  — the two time-of-day drivers the lab owns since chunk 17.

THE LAB OWNS ITS CLOCK (chunk 17, 2026-09-19)
=============================================
Both Windows scheduled tasks that used to own a time of day failed twice in one
week — `0x80070520` (no logon session) on 09-19 and `0x80070420` (an instance is
already running) for four days before it — and nothing but a `schtasks /Query`
would have shown it. The lab is the only process that is genuinely live
whenever the PC is on, so it dispatches `scripts.daily_pass` at 06:30 local and
`scripts.run_night_launcher --scheduled` at 16:00 local on weekdays, each at
most once per LOCAL DATE, each gated on the driver's own RECEIPT and on a
record written BEFORE the call. The scheduled tasks stay registered as a
fallback: whichever fires first writes the receipt and the other stands down.

AND IT RECORDS WHY IT DIED
==========================
Three lab deaths between 2026-09-18 05:41 and 2026-09-19 03:15 left nothing
behind but the next instance's "overwrote a stale lock". The lock now carries
`exit_reason`/`exit_utc`, written on every path that unwinds (STOP file, ticks
exhausted, a signal, an exception, `atexit`), and the NEXT instance carries the
previous one's reason forward — `not_recorded (killed or crashed)` when there
was none, which is the honest answer for `TerminateProcess` and for a
bugcheck.

A refusal is a finding: it is recorded in `lab_status.json` and the process
exits 0. The exit code is non-zero only for a refusal about the INVOCATION
(a second instance), which is a fact about the command rather than the day.

NO ORDER PATH, NO LLM AUTHORITY OVER CAPITAL
============================================
Nothing here places an order, arms a lane, sizes a position or touches a paper
book's frozen `Strategy`. The nightly refit produces candidates for a FUTURE
book; it never reaches backward into one already accruing forward evidence.
`test_always_on_lab.py` walks this module's AST (docstrings removed) and fails
if an order or broker symbol appears in executable source.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import socket
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from backend import config as _config

logger = logging.getLogger("always_on_lab")

ROOT = Path(__file__).resolve().parent.parent

#: The declared loop list. The supervisor walks THIS, in this order, not the
#: list of things that worked — the `daily_pass.STEPS` discipline, which exists
#: because a check that reads the record of what ran cannot see what never got
#: called (`signal_reachability.py`'s founding lesson).
LOOPS: tuple[tuple[str, str], ...] = (
    # The two time-of-day drivers come FIRST in the walk (chunk 17): they own
    # their day, and every loop below them yields to a driver that is running.
    ("daily_pass_dispatch", "the daily pass at its local time, on the lab's own clock"),
    ("night_launcher_dispatch", "the IIF-1 night launcher at its local time, weekdays"),
    ("news_pull", "every registered source into the corpus, with first_seen_utc"),
    ("l2_typing", "type new corpus rows into the frozen event vocabulary"),
    ("decision_vs_reality", "what we said vs what happened, across every mechanism"),
    ("catalyst_calendar", "earnings plus FOMC/CPI/NFP, every entry with its provenance"),
    ("nn_lab", "E1 refit, E4 ADWIN gate, E5 stopping rules, on tonight's table"),
    ("idle_gpu_queue", "the next registered job, only when nothing needs the model"),
    ("thematic_streams", "Murat's themes as typed hypothesis streams"),
    ("status", "lab_status.json, every tick, whether or not anything happened"),
)

#: The five statuses are deliberately `daily_pass.STATUSES` so one reader learns
#: one vocabulary, plus the two a long-running driver needs that a one-shot pass
#: does not.
STATUSES = ("ok", "nothing_to_do", "refused", "error", "skipped",
            "paused", "timeout")

PERIODS: dict = dict(_config.LAB_LOOP_PERIODS_MINUTES)
TIMEOUTS: dict = dict(_config.LAB_LOOP_TIMEOUT_S)
HEARTBEAT_MINUTES = _config.LAB_HEARTBEAT_MINUTES
POWER_RECHECK_MINUTES = _config.LAB_POWER_RECHECK_MINUTES
IDLE_MINUTES = _config.LAB_IDLE_MINUTES
MODEL_LOOPS = frozenset(_config.LAB_MODEL_LOOPS)
TASK_NAME = "AegisAlwaysOnLab"

assert set(PERIODS) == {name for name, _ in LOOPS}, \
    "every declared loop needs a period in config.LAB_LOOP_PERIODS_MINUTES"
assert set(TIMEOUTS) == {name for name, _ in LOOPS}, \
    "every declared loop needs a wall-clock box in config.LAB_LOOP_TIMEOUT_S"


# ===========================================================================
# PATHS AND CLOCKS
# ===========================================================================


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _trunc(exc: BaseException, n: int = 400) -> str:
    return f"{type(exc).__name__}: {exc}"[:n]


def run_date() -> str:
    """The date this supervisor's receipts belong to.

    `NIGHT_RUN_DATE` is honoured so the lab files into the same night folder as
    every other job of the day. Unset it is TODAY — never a literal, which is
    the defect `night_factory.py` carried for five days in September.
    """
    return os.getenv("NIGHT_RUN_DATE") or datetime.now().strftime("%Y-%m-%d")


def data_dir() -> Path:
    """`backend/data/optimus` — the SHARED path, not a per-user temp directory.

    Shared on purpose: `ONLOGON` fires per logon, and two Windows sessions must
    be able to see each other's lock or the single-instance rule is not one.
    """
    return Path(_config.DATA_DIR) / "optimus"


def out_dir() -> Path:
    """Today's night folder, created at write time by the job registry."""
    from scripts import night_factory_jobs as J
    return J._out()


def lock_path() -> Path:
    return data_dir() / "always_on_lab_lock.json"


def status_path() -> Path:
    return data_dir() / "lab_status.json"


def stop_path() -> Path:
    return out_dir() / "STOP"


def model_server_hold_path() -> Path:
    """The operator's hold on the lab's starter (`LAB_MODEL_SERVER_HOLD_NAME`)."""
    return data_dir() / str(_config.LAB_MODEL_SERVER_HOLD_NAME)


def _write_atomic(path: Path, payload: dict) -> None:
    """`os.replace` over a sibling temp file — never a bare `write_text`.

    The same pattern `llama_server.py` and `night_launcher.py` already use for
    their own state files: a crash mid-write leaves the PREVIOUS status intact
    rather than a truncated JSON nobody can parse.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str),
                   encoding="utf-8")
    os.replace(tmp, path)


# ===========================================================================
# THE SEAMS
#
# One module-level callable per external thing a loop does, so a test can
# replace it BY NAME. A loop body cannot be monkeypatched; these can.
# ===========================================================================


def power_refusal() -> str | None:
    """The power-plan guard, IMPORTED. A second copy would drift from the first."""
    from scripts.night_factory import refuse_if_the_machine_may_sleep
    return refuse_if_the_machine_may_sleep()


def model_status() -> dict:
    """`llama_server.status()` — the probe, never `stop()`.

    Probed before EVERY model-touching tick, not once at startup, because the
    desktop app can start or stop the server at any point in a multi-day
    supervisor run. Since 2026-09-18 a NOT-LISTENING answer is also the trigger
    for `ensure_model_server()`: see `LAB_STARTS_MODEL_SERVER` in config.
    """
    from backend.services import llama_server
    return llama_server.status()


def start_model_server() -> dict:
    """`llama_server.start(bind=False)` — the lab as a STARTER (2026-09-18).

    `bind=False` is the whole of the design. `start(bind=True)` puts the server
    in a Windows job object whose last handle is held by THIS process, so the
    OS kills the server the moment the supervisor exits — and this supervisor is
    restarted by the Startup folder on every logon. A server that dies with its
    starter is not the "live whenever the PC is on" the lab exists for.

    The ownership note `llama_server.start` writes carries `owner_pid =
    os.getpid()`, which is this supervisor's PID: the existing scheme, unchanged,
    so `stop_if_owned()` in a desktop app still correctly declines to kill a
    server the lab started.
    """
    from backend.services import llama_server
    return llama_server.start(bind=False,
                              wait_s=float(_config.LAB_MODEL_SERVER_START_WAIT_S))


def pid_alive(pid: int) -> bool:
    from backend.services import llama_server
    return llama_server.pid_alive(int(pid))


def pid_names_lab(pid: int) -> bool:
    """Does PID `pid`'s command line still name this supervisor?

    PID reuse is real on a long-uptime Windows box: liveness alone would report
    a stale lock as live the moment the OS handed that number to another
    program. CANNOT DETERMINE (the probe did not run) is treated as TRUE — the
    conservative direction is to refuse to start a second supervisor, not to
    start one on a maybe.
    """
    if sys.platform != "win32":
        return True
    from backend.services import quiet_subprocess as qsp
    try:
        r = qsp.run(["powershell", "-NoProfile", "-Command",
                     f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}')"
                     ".CommandLine"],
                    capture_output=True, text=True, timeout=30)
    except Exception:                                              # noqa: BLE001
        return True
    out = (r.stdout or "").strip()
    if not out:
        return True
    return "always_on_lab" in out


def pull_news(**kw) -> dict:
    from scripts import news_pull
    return news_pull.pull_all(**kw)


def news_sources() -> list:
    from backend.services import news_registry
    return list(news_registry.pullable())


def type_rows(**kw) -> dict:
    from scripts import night_l2_typed_events
    return night_l2_typed_events.L2_typed_events(**kw)


#: The scheduled drivers that own their own windows and their own receipts.
#: The supervisor's overlapping loops YIELD to a running one rather than
#: launching a second concurrent copy of the same underlying job.
SCHEDULED_DRIVERS: dict = {
    "daily_pass": "scripts.daily_pass",
    "night_factory": "scripts.night_factory",
    "monday_night": "scripts.monday_night",
    # 2026-09-19: the lab dispatches this one itself, so it must also be able
    # to SEE one it did not dispatch -- a scheduled task that still fires, or a
    # human at a terminal. A dispatcher that cannot see its own job running is
    # a dispatcher that launches a second copy of it.
    "night_launcher": "scripts.run_night_launcher",
}

#: How long a process scan is trusted before it is taken again. A PowerShell
#: CIM query per loop per tick would cost more than the loops it guards.
DRIVER_SCAN_TTL_S = 60.0
_DRIVER_SCAN: dict = {"utc": None, "value": None}


def scan_processes() -> list[tuple[int, str]]:
    """(pid, command line) for every python process on this machine.

    ONE query, shared by every arbitration check in a tick. Returns [] when the
    probe itself could not run — and the callers treat that as CANNOT DETERMINE
    rather than as "nothing is running", because a scan that failed and a
    machine that is idle are different facts.
    """
    if sys.platform != "win32":
        return []
    from backend.services import quiet_subprocess as qsp
    try:
        r = qsp.run(["powershell", "-NoProfile", "-Command",
                     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                     "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }"],
                    capture_output=True, text=True, timeout=45)
    except Exception:                                              # noqa: BLE001
        return []
    out: list[tuple[int, str]] = []
    for line in (r.stdout or "").splitlines():
        pid, _, cmd = line.partition("\t")
        if pid.strip().isdigit():
            out.append((int(pid), cmd))
    return out


def running_drivers(*, now: datetime | None = None) -> dict:
    """Which scheduled drivers are running RIGHT NOW, by PID.

    Detected from the process table, never from a guessed wall-clock window: a
    `daily_pass` running late is still running, whatever time it is. The scan
    is cached for `DRIVER_SCAN_TTL_S` because it costs a PowerShell launch.
    """
    now = now or datetime.now(timezone.utc)
    prev = _as_dt(_DRIVER_SCAN.get("utc"))
    if prev is not None and (now - prev).total_seconds() < DRIVER_SCAN_TTL_S:
        return dict(_DRIVER_SCAN["value"] or {})
    rows = scan_processes()
    me = os.getpid()
    found: dict = {"scanned": len(rows), "scan_ran": bool(rows)}
    for name, needle in SCHEDULED_DRIVERS.items():
        found[name] = sorted(pid for pid, cmd in rows
                             if needle in (cmd or "") and pid != me)
    _DRIVER_SCAN["utc"] = now.isoformat(timespec="seconds")
    _DRIVER_SCAN["value"] = found
    return dict(found)


def yields_to(*names: str, now: datetime | None = None) -> dict | None:
    """A refusal row when one of `names` is running, else None.

    `NIGHT_FACTORY_ALREADY_RUNNING` / `DAILY_PASS_RUNNING` /
    `MONDAY_NIGHT_RUNNING`, by name, in the receipt — a reader never has to
    know an enum's numbering to learn why a tick did nothing.
    """
    drivers = running_drivers(now=now)
    for name in names:
        pids = drivers.get(name) or []
        if pids:
            return {"status": "skipped",
                    "reason": f"{name.upper()}_RUNNING" if name != "night_factory"
                              else "NIGHT_FACTORY_ALREADY_RUNNING",
                    "detail": (f"{name} is running as pid(s) {pids}; this loop "
                               f"yields rather than launching a second copy of "
                               f"the same underlying job"),
                    "yielded_to": name, "pids": pids}
    return None


def dispatch_job(job: str, minutes: int) -> dict:
    """One idle-queue job, through `night_factory`'s OWN dispatcher.

    Called rather than re-implemented: a second way to run the same job is two
    ways that drift, and `night_factory.run_job` is the one that time-boxes by
    AWAKE seconds and kills the process tree by PID.
    """
    from scripts import night_factory
    # 2026-09-14 02:20: a literal run 1 rewrote a committed receipt the first
    # night this ran. The factory's own rule picks the next free number and
    # resumes a crashed stub under its own.
    run, resume = night_factory.resolve_run(job, 1)
    return night_factory.run_job(job, run, minutes, [], resume=resume)


# ===========================================================================
# THE LAB OWNS ITS CLOCK (chunk 17)
#
# Two time-of-day drivers that a Windows scheduled task used to own and twice
# failed to start: 0x80070520 (no logon session, both tasks, 2026-09-19) and
# 0x80070420 (an instance is already running, four days, the week before).
# The lab is the only thing that is live whenever the PC is on, so it fires
# them itself -- and the scheduled tasks stay registered as a fallback,
# because whichever runs first writes the receipt and the other stands down.
# ===========================================================================


#: One row per driver the lab dispatches on its own clock. Declared as DATA so
#: the two loops are one implementation with two configurations: a second
#: hand-written dispatch loop is a second place to forget the receipt gate.
DRIVERS: dict = {
    "daily_pass": {
        "loop": "daily_pass_dispatch",
        "module": "scripts.daily_pass",
        "args": (),
        "local_time": str(_config.LAB_DAILY_PASS_LOCAL_TIME),
        "weekdays_only": False,
        "task": "AegisDailyPass",
    },
    "night_launcher": {
        "loop": "night_launcher_dispatch",
        "module": "scripts.run_night_launcher",
        # --scheduled, ALWAYS. The launcher's own arming, timing and
        # acceptance rules are what make a night legitimate; the lab dispatches
        # it, it never bypasses it. Without the flag the receipt counts for
        # nothing toward acceptance.
        "args": ("--scheduled",),
        "local_time": str(_config.LAB_NIGHT_LAUNCHER_LOCAL_TIME),
        "weekdays_only": bool(_config.LAB_NIGHT_LAUNCHER_WEEKDAYS_ONLY),
        "task": "AegisIIF1NightLauncher",
    },
}

assert {d["loop"] for d in DRIVERS.values()} <= {name for name, _ in LOOPS}, \
    "every dispatched driver needs its own declared loop"
assert set(DRIVERS) <= set(SCHEDULED_DRIVERS), \
    "a driver the lab dispatches must also be one it can SEE running"
assert set(DRIVERS) == set(_config.LAB_DRIVER_BOX_S), \
    "every dispatched driver needs a box in config.LAB_DRIVER_BOX_S"


def empty_stdin_path() -> Path:
    """The zero-length REGULAR file every scheduled driver reads stdin from.

    Not `NUL`. On Windows `_isatty()` returns true for any character device, so
    `< NUL` redirects and changes nothing observable -- which disqualified the
    launcher's first two genuine firings in August because
    `observe_invocation` marked them `contradicted`. A disk file is not a
    character device.
    """
    return data_dir() / "empty_stdin.txt"


def driver_log_path(name: str, today: str) -> Path:
    """Where a dispatched driver's stdout and stderr go. A convenience, never
    the evidence: the evidence is the driver's own receipt."""
    return data_dir() / f"lab_dispatch_{name}_{today}.log"


def driver_receipt(name: str, today: str) -> dict:
    """Has `name` already produced its receipt for the local date `today`?

    The already-ran gate is keyed HERE, on the artefact on disk, and not on
    this supervisor's memory: the scheduled task may still be registered, a
    human may have run the driver by hand, and a restarted lab must not
    re-dispatch a pass that already happened. `_receipt_today`'s lesson
    (2026-09-14), applied to the two drivers it did not cover.

    `iif1_launches/` is resolved through `data_dir()` rather than through
    `night_launcher.LAUNCH_RECEIPTS_DIR` because that constant binds
    `DATA_DIR` at import; the two are the same directory and a test pins that
    they stay the same.
    """
    if name == "daily_pass":
        folder = data_dir() / f"night_factory_{today}"
        pattern = f"daily_pass_{today}*.json"
    else:
        folder = data_dir() / "iif1_launches"
        pattern = f"{today}*.json"
    try:
        found = sorted(p for p in folder.glob(pattern) if p.is_file())
    except OSError as exc:
        return {"exists": False, "why": f"CANNOT_READ: {_trunc(exc)}"}
    if not found:
        return {"exists": False, "path": None, "verdict": None}
    latest = found[-1]
    verdict = None
    try:
        doc = json.loads(latest.read_text(encoding="utf-8"))
        verdict = doc.get("verdict") or doc.get("headline")
    except (OSError, ValueError):
        verdict = "UNREADABLE_RECEIPT"
    return {"exists": True, "path": str(latest), "n": len(found),
            "verdict": (str(verdict)[:200] if verdict else None)}


def local_now() -> datetime:
    """The MACHINE's wall clock — the one a 06:30 means. A seam, so a test can
    put the lab at any hour of any weekday without touching the UTC clock the
    rest of the supervisor reasons in."""
    return datetime.now()


def due_at_local_time(hhmm: str, now: datetime) -> bool:
    """Is `now` (local) at or after `hhmm` on its own date?

    No upper bound, on purpose. A window would turn a machine that was off at
    06:30 and on at 09:00 into a silent skip, which is the failure this whole
    change exists to remove. Being late is handled by the driver: the launcher
    refuses `PAST_LATEST_SAFE_LAUNCH` by name, and the daily pass is worth
    running at any hour of its own date.
    """
    try:
        hh, mm = (int(x) for x in str(hhmm).split(":"))
    except ValueError:
        return False
    return (now.hour, now.minute) >= (hh, mm)


def launch_driver(module: str, args: tuple[str, ...] = (), *,
                  log: Path, stdin: Path) -> dict:
    """Start one driver as a DETACHED child of THIS interpreter. One seam.

    Four properties, each of them paid for somewhere in this repository:

    * `sys.executable`, never a bare `python`: the lab runs from the venv and a
      child that resolved to a different interpreter would import a different
      repository;
    * DETACHED, in its own process group: the dispatching loop runs under a
      wall-clock box on a daemon thread, and a child tied to this console would
      die with a Ctrl-Break the supervisor never sent;
    * stdin from the empty regular file (see `empty_stdin_path`);
    * stdout and stderr appended to a dated log, with no pipe anywhere --
      `cmd | tail` reports tail's exit code, and the exit code is the guard.

    The child is NOT waited on. Its completion signal is its receipt.
    """
    import subprocess
    argv = [sys.executable, "-m", module, *args]
    log.parent.mkdir(parents=True, exist_ok=True)
    if not stdin.exists():
        stdin.parent.mkdir(parents=True, exist_ok=True)
        stdin.write_bytes(b"")
    flags = 0
    if sys.platform == "win32":
        flags = (getattr(subprocess, "DETACHED_PROCESS", 0)
                 | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    fin = stdin.open("rb")
    fout = log.open("ab")
    try:
        proc = subprocess.Popen(argv, cwd=str(ROOT), stdin=fin, stdout=fout,
                                stderr=subprocess.STDOUT, creationflags=flags,
                                close_fds=True)
    finally:
        fin.close()
        fout.close()
    return {"pid": int(proc.pid), "argv": argv, "log": str(log),
            "started_utc": _now()}


def _driver_outcome(rec: dict, receipt: dict, name: str,
                    now: datetime) -> dict:
    """What became of a dispatch this lab already made on this date.

    Read from the RECEIPT, never from the child's exit code — the lab does not
    wait on it, and the pass's own rule is that the exit code is a fact about
    the invocation while the receipt is the fact about the day.
    """
    box = float(_config.LAB_DRIVER_BOX_S[name])
    started = _as_dt(rec.get("at_utc"))
    elapsed = None if started is None else (now - started).total_seconds()
    if receipt.get("exists"):
        verdict = str(receipt.get("verdict") or "")
        result = "refused" if "REFUSED" in verdict.upper() else "ok"
        return {"status": "ok", "reason": "DISPATCHED_THIS_DATE",
                "result": result, "driver_verdict": receipt.get("verdict"),
                "receipt_path": receipt.get("path"),
                "elapsed_s": (None if elapsed is None else round(elapsed, 1)),
                "detail": (f"this lab dispatched {name} at {rec.get('at_utc')} "
                           f"(pid {rec.get('pid')}) and its receipt is on disk")}
    if elapsed is not None and elapsed > box:
        return {"status": "timeout", "reason": "DRIVER_BOX_EXCEEDED",
                "result": "timeout", "elapsed_s": round(elapsed, 1),
                "box_s": box,
                "detail": (f"{name} was dispatched {elapsed / 3600:.1f} h ago "
                           f"(pid {rec.get('pid')}) and no receipt for this "
                           f"date has landed; the box is {box:.0f}s. Nothing "
                           f"is killed here — a driver past its box is a "
                           f"finding, and killing is by PID and attended.")}
    return {"status": "nothing_to_do", "reason": "DISPATCHED_THIS_DATE",
            "result": "running", "elapsed_s": (None if elapsed is None
                                               else round(elapsed, 1)),
            "box_s": box,
            "detail": (f"{name} was dispatched at {rec.get('at_utc')} "
                       f"(pid {rec.get('pid')}); no receipt yet, still inside "
                       f"its box")}


def dispatch_driver(state: LabState, name: str, *,
                    now: datetime | None = None,
                    now_local: datetime | None = None) -> dict:
    """One time-of-day driver, at most once per LOCAL date. Six gates, by name.

    In order, and the order is the design:

    1. this lab already dispatched it today -> read the receipt, never re-fire;
    2. a receipt already exists (the scheduled task fired, or a human ran it)
       -> `ALREADY_RAN_TODAY`;
    3. the weekday pre-filter, for the launcher only -> `WEEKEND_NOT_DUE`;
    4. the local clock -> `NOT_DUE`;
    5. a live sibling driver -> yields BY NAME. It does not kill: the only
       thing in this repository licensed to kill a stale driver is that
       driver's own startup, by PID, and this one is not it;
    6. dispatch — and the record is written BEFORE the call, because this runs
       on a daemon thread that a wall-clock box may abandon, and a record
       written after the return was never written at all (the idle queue paid
       for that on 2026-09-14 by dispatching its first job twice).
    """
    spec = DRIVERS[name]
    now = now or datetime.now(timezone.utc)
    local = now_local or local_now()
    today = local.strftime("%Y-%m-%d")
    row = state.loops[spec["loop"]]
    base = {"n": 0, "driver": name, "date": today,
            "local_time": spec["local_time"],
            "local_now": local.strftime("%Y-%m-%d %H:%M"),
            "weekdays_only": spec["weekdays_only"],
            "fallback_task": spec["task"]}

    rec = dict(row.get("dispatched") or {})
    receipt = driver_receipt(name, today)

    if rec.get("date") == today:
        out = _driver_outcome(rec, receipt, name, now)
        rec["result"] = out["result"]
        row["dispatched"] = rec
        return {**base, **out, "dispatched": rec}

    if receipt.get("exists"):
        return {**base, "status": "nothing_to_do", "reason": "ALREADY_RAN_TODAY",
                "result": "ok", "receipt_path": receipt.get("path"),
                "driver_verdict": receipt.get("verdict"),
                "detail": (f"{receipt.get('n')} receipt(s) for {today} are "
                           f"already on disk (the scheduled task "
                           f"{spec['task']} fired, or a human ran it); the lab "
                           f"stands down rather than running a second one")}

    if spec["weekdays_only"] and local.weekday() >= 5:
        return {**base, "status": "skipped", "reason": "WEEKEND_NOT_DUE",
                "detail": (f"{today} is a {local.strftime('%A')}; the weekday "
                           f"rule is a coarse pre-filter and NOT the calendar "
                           f"— the launcher reads XNYS and refuses holidays "
                           f"itself")}

    if not due_at_local_time(spec["local_time"], local):
        return {**base, "status": "nothing_to_do", "reason": "NOT_DUE",
                "detail": (f"local {local.strftime('%H:%M')} is before "
                           f"{spec['local_time']}")}

    yielded = yields_to(name, now=now)
    if yielded:
        return {**base, **yielded}

    log = driver_log_path(name, today)
    rec = {"date": today, "driver": name, "at_utc": _now(), "pid": None,
           "result": "dispatching", "log": str(log)}
    row["dispatched"] = rec
    try:
        out = launch_driver(spec["module"], tuple(spec["args"]),
                            log=log, stdin=empty_stdin_path())
    except Exception as exc:                                       # noqa: BLE001
        logger.exception("the lab could not dispatch %s", name)
        rec["result"] = "spawn_failed"
        rec["detail"] = _trunc(exc)
        row["dispatched"] = rec
        return {**base, "status": "error", "reason": "SPAWN_FAILED",
                "result": "spawn_failed", "detail": _trunc(exc),
                "dispatched": rec}

    rec.update(pid=out["pid"], argv=out["argv"], result="running")
    row["dispatched"] = rec
    # The cached process scan predates this child, and the loops below this one
    # in the walk yield to a running driver. Invalidating it costs one
    # PowerShell launch and buys an arbitration that is true this tick.
    _DRIVER_SCAN["utc"] = None
    logger.warning("DISPATCHED %s as pid %s (local %s, box %.0fs) -> %s",
                   name, out["pid"], local.strftime("%H:%M"),
                   float(_config.LAB_DRIVER_BOX_S[name]), log)
    return {**base, "status": "ok", "n": 1, "result": "running",
            "pid": out["pid"], "argv": out["argv"], "log": str(log),
            "dispatched": rec,
            "headline": (f"the lab dispatched {name} at local "
                         f"{local.strftime('%H:%M')} as pid {out['pid']}; its "
                         f"receipt, not its exit code, is the outcome")}


def loop_daily_pass_dispatch(state: LabState) -> dict:
    """`scripts.daily_pass`, at `LAB_DAILY_PASS_LOCAL_TIME`, once per date."""
    return dispatch_driver(state, "daily_pass")


def loop_night_launcher_dispatch(state: LabState) -> dict:
    """`scripts.run_night_launcher --scheduled`, weekdays, once per date."""
    return dispatch_driver(state, "night_launcher")


# ===========================================================================
# THE SINGLE-INSTANCE LOCK
# ===========================================================================


class AlreadyRunning(RuntimeError):
    """A live supervisor holds the lock. A refusal, not a crash."""


def read_lock() -> dict:
    p = lock_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


#: What the previous instance's lock says when it left no reason at all. A
#: killed process runs no handler -- `TerminateProcess` unwinds nothing, and a
#: bugcheck less than that -- so the ABSENCE of a reason is itself the finding,
#: and it is written down by the next instance rather than left as a gap
#: somebody has to notice ("a promise kept only on the tidy path is not the
#: promise", 2026-09-10).
EXIT_NOT_RECORDED = "not_recorded (killed or crashed)"

#: Every reason the supervisor can record for its own death, by name. The
#: generic one is diagnostic precisely because every KNOWN path sets its own
#: before `atexit` would fire.
EXIT_REASONS = ("STOP_file", "ticks_exhausted", "SystemExit", "KeyboardInterrupt",
                "exception", "process_exit_unclassified")


def record_exit(reason: str, *, lock: dict | None = None) -> dict | None:
    """Write `exit_reason`/`exit_utc` into the lock — if this process holds it.

    THE MEASURED GAP. Between 2026-09-18 05:41 and 2026-09-19 03:15 the lab
    died and restarted three times and the only evidence of any of it is the
    NEXT instance's line "overwrote a stale lock: pid N is not alive". Nothing
    said why. A supervisor that cannot say why it stopped cannot tell a clean
    shutdown from a GPU bugcheck, and the two want opposite responses.

    Never raises: this runs on the way out, and an exception here would replace
    a recorded death with an unrecorded one.
    """
    try:
        rec = dict(lock if lock is not None else read_lock())
        if int(rec.get("pid") or 0) != os.getpid():
            return None
        rec["exit_reason"] = str(reason)[:300]
        rec["exit_utc"] = _now()
        _write_atomic(lock_path(), rec)
        return rec
    except Exception:                                              # noqa: BLE001
        return None


def lock_holder() -> dict:
    """Who holds the lock, and whether that claim survives inspection.

    Three states, never two: HELD (a live PID whose command line still names
    this supervisor), STALE (the PID is gone, or a different program now holds
    that number), and FREE (no lock file, or a lock a previous instance
    released). A released or stale lock carries `previous_exit_reason`: what
    the last instance said on its way out, or `EXIT_NOT_RECORDED`.
    """
    rec = read_lock()
    pid = int(rec.get("pid") or 0)
    if not pid:
        return {"state": "free", "lock": rec,
                "previous_exit_reason": (rec.get("exit_reason")
                                         or (EXIT_NOT_RECORDED if rec else None)),
                "previous_exit_utc": rec.get("exit_utc")}
    prev = {"previous_exit_reason": rec.get("exit_reason") or EXIT_NOT_RECORDED,
            "previous_exit_utc": rec.get("exit_utc")}
    if not pid_alive(pid):
        return {"state": "stale", "lock": rec, "why": f"pid {pid} is not alive",
                **prev}
    if not pid_names_lab(pid):
        return {"state": "stale", "lock": rec,
                "why": (f"pid {pid} is alive but its command line does not name "
                        f"always_on_lab (PID reuse)"),
                **prev}
    # A HELD lock's own `exit_reason` would be a claim about a live process, so
    # what travels is the one IT carried forward about the instance before it.
    return {"state": "held", "lock": rec, "pid": pid,
            "previous_exit_reason": rec.get("previous_exit_reason"),
            "previous_exit_utc": rec.get("previous_exit_utc")}


def acquire_lock() -> dict:
    """Take the lock, or raise `AlreadyRunning`. Written BEFORE the first tick."""
    holder = lock_holder()
    if holder["state"] == "held":
        raise AlreadyRunning(f"ALREADY_RUNNING: pid {holder['pid']} "
                             f"(started {holder['lock'].get('started_utc')})")
    rec = {"pid": os.getpid(), "started_utc": _now(),
           "hostname": socket.gethostname(), "started_by": "always_on_lab",
           "overwrote": (holder.get("lock") or None) if holder["state"] == "stale" else None,
           "overwrote_why": holder.get("why"),
           # Carried forward on purpose: the instance that can SAY why the last
           # one died is the one that comes after it, and a killed instance
           # necessarily says nothing itself.
           "previous_exit_reason": holder.get("previous_exit_reason"),
           "previous_exit_utc": holder.get("previous_exit_utc")}
    _write_atomic(lock_path(), rec)
    if holder["state"] == "stale":
        logger.warning("overwrote a stale lock: %s (previous exit: %s)",
                       holder.get("why"), holder.get("previous_exit_reason"))
    return rec


def release_lock(reason: str | None = None) -> None:
    """Give the lock up, KEEPING the record so the next instance can read it.

    The file used to be unlinked. It is now rewritten with `pid: None` — which
    `lock_holder` reads as FREE exactly as an absent file does — because the
    exit reason written on the way out is worth nothing if the act of leaving
    deletes it.
    """
    try:
        rec = read_lock()
        if int(rec.get("pid") or 0) != os.getpid():
            return
        # An already-recorded reason WINS: it was written by a more specific
        # path (a signal handler) that knows something this one does not.
        rec["exit_reason"] = str(rec.get("exit_reason") or reason
                                 or "process_exit_unclassified")[:300]
        rec["exit_utc"] = rec.get("exit_utc") or _now()
        rec["released_utc"] = _now()
        rec["pid"] = None
        _write_atomic(lock_path(), rec)
    except OSError:
        pass


# ===========================================================================
# THE LOOP BOXES — a stuck loop must not become a silent supervisor
# ===========================================================================


class LoopTimeout(RuntimeError):
    """One loop outlived its wall-clock box. The supervisor's heartbeat did not."""


def call_boxed(fn: Callable[[], dict], timeout_s: float, what: str) -> dict:
    """Run `fn()` under a hard wall-clock bound, on a DAEMON thread.

    The hung thread is NOT killed — Python cannot — which is why it is a daemon:
    it cannot hold the process open at exit, and the supervisor's own 5-minute
    heartbeat keeps advancing while that ONE loop's `last_tick_utc` stops. That
    divergence is exactly the detectable signal; a supervisor that awaited a
    stuck loop unboundedly would go silent instead, and silence is never
    success.

    Shape borrowed verbatim from `news_pull.call_with_timeout`, which was
    written on 2026-09-13 after Alpaca held a TLS handshake for two hours.
    """
    box: dict = {}

    def _run() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:                               # noqa: BLE001
            box["error"] = exc

    t = threading.Thread(target=_run, daemon=True, name=f"lab:{what}")
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        raise LoopTimeout(f"{what}: no return in {timeout_s:.0f}s (thread abandoned)")
    if "error" in box:
        raise box["error"]                                         # type: ignore[misc]
    return box.get("value") or {}


# ===========================================================================
# LOOP STATE
# ===========================================================================


class LabState:
    """Per-loop last-successful-tick times, carried across restarts.

    A loop due every 15 minutes that the supervisor was away from for six hours
    runs ONCE at the next wake-up, not twenty-four times to "catch up": catching
    up burns the budget on stale data for no benefit. That falls out of storing
    the last SUCCESSFUL tick rather than a schedule of missed firings.
    """

    def __init__(self, loops: dict | None = None, started_utc: str | None = None):
        self.loops: dict = {name: dict((loops or {}).get(name) or {})
                            for name, _ in LOOPS}
        for name, what in LOOPS:
            self.loops[name].setdefault("last_tick_utc", None)
            self.loops[name].setdefault("status", "not_yet_run")
            self.loops[name]["what"] = what
        self.started_utc = started_utc or _now()
        self.power_refusal: str | None = None
        self.power_checked_utc: str | None = None
        self.last_model_call_utc: str | None = None
        self.ticks = 0
        self.stopped_by: str | None = None
        #: WITHIN one process, never a second PID file: the supervisor is
        #: single-threaded for anything that touches the model server.
        self.model_lock = threading.Lock()
        #: A loop still running past its box is not re-issued while wedged.
        self.inflight: set[str] = set()
        #: `{"date": "<YYYY-MM-DD>", "n": int}` — how many times the lab has
        #: started the model server on that date. Carried across a restart
        #: because the lab restarts itself from the Startup folder, and a cap
        #: that a restart resets is not a cap.
        self.model_server_starts: dict = {"date": None, "n": 0}

    @classmethod
    def load(cls) -> "LabState":
        p = status_path()
        if not p.exists():
            return cls()
        try:
            prev = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        st = cls(loops=prev.get("loops") or {})
        st.last_model_call_utc = prev.get("last_model_call_utc")
        st.model_server_starts = {
            "date": (prev.get("model_server_starts") or {}).get("date"),
            "n": int((prev.get("model_server_starts") or {}).get("n") or 0)}
        return st

    def starts_today(self, today: str) -> int:
        """Model-server starts booked on `today`. A new date starts at zero."""
        rec = self.model_server_starts or {}
        return int(rec.get("n") or 0) if rec.get("date") == today else 0

    def note_model_server_start(self, today: str) -> int:
        n = self.starts_today(today) + 1
        self.model_server_starts = {"date": today, "n": n}
        return n

    def due(self, loop: str, now: datetime) -> bool:
        last = self.loops[loop].get("last_tick_utc")
        if not last:
            return True
        prev = _as_dt(last)
        if prev is None:
            return True
        return (now - prev) >= timedelta(minutes=PERIODS[loop])

    def idle_minutes(self, now: datetime) -> float | None:
        """Minutes since the last model-touching call, or None if there has
        never been one in this status file's history."""
        prev = _as_dt(self.last_model_call_utc)
        if prev is None:
            return None
        return (now - prev).total_seconds() / 60.0

    def note_model_call(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        self.last_model_call_utc = now.isoformat(timespec="seconds")


def _as_dt(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


# ===========================================================================
# THE MODEL SERVER — the lab is a STARTER, and never a stopper (2026-09-18)
# ===========================================================================


#: Every reason `ensure_model_server` can decline, by name. Declared so a reader
#: of `lab_status.json` meets a closed vocabulary rather than free prose, and so
#: a test can assert on the NAME instead of on a sentence.
MODEL_SERVER_REFUSALS = (
    "LAB_STARTS_MODEL_SERVER_DISABLED",
    "OPERATOR_HOLD",
    "ALREADY_LISTENING",
    "FOREIGN_SERVER_UP",
    "POWER_PLAN_ALLOWS_SLEEP",
    "MODEL_SERVER_START_CAP_REACHED",
    "STATUS_PROBE_FAILED",
    "START_FAILED",
)


def ensure_model_server(state: "LabState", *, now: datetime | None = None,
                        server: dict | None = None) -> dict:
    """Start the model server when nothing is listening. Five gates, by name.

    THE MEASURED DEFECT. On 2026-09-18 at 06:57 the PC rebooted for Windows
    Update. The lab came back from the Startup folder and then spent the whole
    day reporting `PENDING_MODEL` (typing), `MODEL_IN_USE` (the NN lab) and a
    stalled idle queue, because the only starters were the desktop app and a
    human and neither was there. "Live whenever the PC is on" cannot have a
    human in its critical path.

    What is NOT relaxed:

    * the lab never STOPS a server — not one it started, not a foreign one;
    * a FOREIGN server (one Aegis did not start) is still not ours to touch: it
      may be several GB into somebody else's job;
    * the power-plan refusal still pauses the GPU half;
    * the cap. `LAB_MODEL_SERVER_MAX_STARTS_PER_DAY` starts a day and then
      REFUSES BY NAME. A server that keeps dying is a finding; a supervisor that
      restarts it every five minutes for a week is a log nobody reads.

    The count is incremented BEFORE the call, deliberately — the same lesson the
    idle queue paid for on 2026-09-14: this runs inside a boxed loop whose thread
    can be abandoned, and a counter written after the return is a counter that
    was never written.
    """
    now = now or datetime.now(timezone.utc)
    today = run_date()
    starts = state.starts_today(today)
    base = {"attempted": False, "started": False, "starts_today": starts,
            "cap": int(_config.LAB_MODEL_SERVER_MAX_STARTS_PER_DAY)}

    if not bool(getattr(_config, "LAB_STARTS_MODEL_SERVER", False)):
        return {**base, "reason": "LAB_STARTS_MODEL_SERVER_DISABLED",
                "detail": ("config.LAB_STARTS_MODEL_SERVER is off; the desktop "
                           "app and a human are the only starters")}
    hold = model_server_hold_path()
    if hold.exists():
        return {**base, "reason": "OPERATOR_HOLD",
                "detail": (f"{hold} exists: an operator is holding the server "
                           f"down (a suite run, a memory recipe); the lab "
                           f"starts nothing until it is deleted")}
    if server is None:
        try:
            server = model_status()
        except Exception as exc:                                   # noqa: BLE001
            return {**base, "reason": "STATUS_PROBE_FAILED", "detail": _trunc(exc)}
    if server.get("foreign"):
        return {**base, "reason": "FOREIGN_SERVER_UP",
                "detail": (f"pid {server.get('pid')} is serving the model and "
                           f"Aegis did not start it; not ours to touch")}
    if server.get("listening"):
        return {**base, "reason": "ALREADY_LISTENING",
                "detail": f"pid {server.get('pid')} is already listening"}
    if state.power_refusal:
        return {**base, "reason": "POWER_PLAN_ALLOWS_SLEEP",
                "detail": str(state.power_refusal)[:200]}
    if starts >= int(_config.LAB_MODEL_SERVER_MAX_STARTS_PER_DAY):
        return {**base, "reason": "MODEL_SERVER_START_CAP_REACHED",
                "detail": (f"the lab has already started the model server "
                           f"{starts} time(s) on {today}; a server that keeps "
                           f"dying is a finding, not a retry loop")}

    with state.model_lock:
        starts = state.note_model_server_start(today)
        try:
            out = start_model_server()
        except Exception as exc:                                   # noqa: BLE001
            logger.exception("the lab could not start the model server")
            return {**base, "attempted": True, "starts_today": starts,
                    "reason": "START_FAILED", "detail": _trunc(exc)}
    if not out.get("ok"):
        return {**base, "attempted": True, "starts_today": starts,
                "reason": "START_FAILED",
                "detail": str(out.get("reason") or out.get("action"))[:300]}
    logger.warning("MODEL SERVER STARTED by the lab (pid %s, action %s, "
                   "start %d of %d today)", out.get("pid"), out.get("action"),
                   starts, int(_config.LAB_MODEL_SERVER_MAX_STARTS_PER_DAY))
    return {**base, "attempted": True, "started": True, "starts_today": starts,
            "reason": None, "action": out.get("action"),
            "server_pid": out.get("pid"), "ready": bool(out.get("ready")),
            "detail": "MODEL SERVER STARTED by the lab"}


# ===========================================================================
# THE LOOPS
#
# Each returns a dict with at least `status`. A loop that did its work and
# found nothing returns `nothing_to_do` with an explicit count — never an
# omitted key, which is what a reader cannot tell from a crash.
# ===========================================================================


#: `200 req/min free tier` -> (200, "min"). Prose the registry writes for a
#: human, read for the one number in it that a cadence check can use.
_RATE_PER_MIN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:req|call|request)s?\s*(?:/|per)\s*"
    r"(s|sec|second|min|minute|h|hour|day)", re.I)


def parsed_rate_limit(source) -> dict:
    """The registry's PROSE rate limit, as calls-per-day when it parses.

    `rate_limit` is a sentence written for a human ("200 req/min free tier",
    "none observed", "unknown"). Where a number and a unit are in it, this
    returns the implied daily budget; where they are not, it returns
    CANNOT DETERMINE — which is NOT a skip. A refusal needs evidence just as a
    positive does, and skipping every source whose limit is unparseable prose
    would silently stop fourteen of eighteen sources.
    """
    text = str(getattr(source, "rate_limit", "") or "")
    m = _RATE_PER_MIN.search(text)
    if not m:
        return {"parsed": False, "per_day": None, "text": text[:120],
                "why": "no `<n> per <unit>` in the registry's prose"}
    n = float(m.group(1))
    per = {"s": 86400, "sec": 86400, "second": 86400,
           "min": 1440, "minute": 1440, "h": 24, "hour": 24,
           "day": 1}[m.group(2).lower()]
    return {"parsed": True, "per_day": n * per, "text": text[:120]}


def cadence_admits(source, period_minutes: int) -> dict:
    """May this source be pulled every `period_minutes`? Two checks, both derived.

    1. PACING: the source's own `min_interval_s` times its per-pull call count
       is the floor on how long ONE pull takes. A pull that cannot finish
       before the next one is due would have the supervisor's own cadence
       breaching the registry's declared spacing.
    2. BUDGET: where the prose rate limit parses to a daily budget, the cadence
       demands `1440/period` pulls a day at that many calls each.

    A skipped source is marked `rate_limit_would_be_breached_at_this_cadence`
    BY NAME rather than quietly pulled less often than declared — a cadence
    table with an unstated exception is not a cadence table.
    """
    calls = max(1, len(getattr(source, "queries", ()) or ()))
    floor_s = float(getattr(source, "min_interval_s", 0) or 0) * calls
    pulls_per_day = 1440.0 / max(1, period_minutes)
    rate = parsed_rate_limit(source)
    row = {"source": getattr(source, "id", "?"), "calls_per_pull": calls,
           "min_interval_s": getattr(source, "min_interval_s", None),
           "pull_floor_s": round(floor_s, 1),
           "pulls_per_day_at_this_cadence": round(pulls_per_day, 1),
           "calls_per_day_at_this_cadence": round(pulls_per_day * calls, 1),
           "declared_budget_per_day": rate["per_day"],
           "budget_parsed": rate["parsed"], "rate_limit_text": rate["text"]}
    if floor_s > period_minutes * 60:
        return {**row, "admitted": False,
                "why": "rate_limit_would_be_breached_at_this_cadence",
                "detail": (f"one pull needs at least {floor_s:.0f}s of declared "
                           f"spacing and the cadence is {period_minutes * 60}s")}
    if rate["parsed"] and pulls_per_day * calls > rate["per_day"]:
        return {**row, "admitted": False,
                "why": "rate_limit_would_be_breached_at_this_cadence",
                "detail": (f"{pulls_per_day * calls:.0f} calls/day at this cadence "
                           f"against a declared {rate['per_day']:.0f}/day")}
    return {**row, "admitted": True,
            "why": (None if rate["parsed"]
                    else "budget CANNOT DETERMINE from the registry's prose; "
                         "admitted, and said so")}


def loop_news_pull(state: LabState) -> dict:
    """Every registered source that the 15-minute cadence admits.

    Calls `news_pull.pull_all` — the corpus writer with its own per-source
    cursor, its own `first_seen_utc` stamp and its own two-zero-runs-is-RED
    rule. This wrapper adds exactly two things: the cadence admission above,
    and yielding to a `daily_pass` that is already pulling.
    """
    yielded = yields_to("daily_pass")
    if yielded:
        return {**yielded, "n": 0, "rows_new": 0, "sources_red": []}

    try:
        sources = news_sources()
    except Exception as exc:                                       # noqa: BLE001
        return {"status": "refused", "n": 0, "rows_new": 0, "sources_red": [],
                "reason": "REGISTRY_UNREADABLE", "detail": _trunc(exc)}

    period = PERIODS["news_pull"]
    admission = [cadence_admits(s, period) for s in sources]
    admitted = [r["source"] for r in admission if r["admitted"]]
    skipped = [{"source": r["source"], "why": r["why"], "detail": r.get("detail")}
               for r in admission if not r["admitted"]]
    if not admitted:
        return {"status": "refused", "n": 0, "rows_new": 0, "sources_red": [],
                "reason": "EVERY_SOURCE_RATE_LIMITED_AT_THIS_CADENCE",
                "sources_skipped": skipped, "cadence_minutes": period}

    # 2026-09-14 02:20: a source keeps the CLI's 600 s budget by default, and
    # 26 sources at 600 s cannot fit a 900 s loop box -- the loop timed out on
    # every tick of the first night. The lab's pull is the 15-minute
    # increment, so each source gets LAB_NEWS_SOURCE_BUDGET_S.
    from scripts import news_pull as _np
    summary = pull_news(source_ids=admitted,
                        ctx=_np.RunContext(budget_s=float(_config.LAB_NEWS_SOURCE_BUDGET_S)))
    rows = int(summary.get("rows_new") or 0)
    red = list(summary.get("red") or [])
    refused = list(summary.get("refused") or [])
    return {
        "status": ("ok" if rows else ("refused" if refused and not red
                                      else "nothing_to_do")),
        "n": rows, "rows_new": rows,
        "sources_pulled": len(admitted),
        "sources_red": red,
        "sources_refused": refused,
        "sources_skipped": skipped,
        "cadence_minutes": period,
        "resolution_rate": summary.get("resolution_rate"),
        "receipt_path": summary.get("receipt_path"),
        "headline": summary.get("headline"),
    }


def _overlap_block() -> dict:
    """The two-READER agreement set, or a named CANNOT DETERMINE.

    Reported on every typing tick rather than computed once at the end, because
    the day a second reader starts running is the day someone will want to mix
    its rows into E1's table — and the kappa that licenses that has to already
    exist, not be commissioned afterwards.
    """
    from backend.services import lab_reader
    try:
        return lab_reader.overlap_report()
    except Exception as exc:                                       # noqa: BLE001
        return {"status": "CANNOT DETERMINE", "why": _trunc(exc),
                "target_rows": lab_reader.overlap_rows()}


def loop_l2_typing(state: LabState) -> dict:
    """Type the rows the last pull added, bounded so one tick cannot eat the day.

    Three things this loop does NOT do, each of them named because doing any of
    them would be a plausible mistake:

    * it never starts the model server. It probes `llama_server.status()` before
      every model-touching tick — not once at startup, because the desktop app
      can start or stop the server at any point in a multi-day run — and USES a
      foreign-owned server read-only when one is up;
    * it never adds a second resume mechanism. `typed_events/_cursor.json` is
      the only one, and the supervisor's single-instance lock plus the in-process
      model lock are what stop two typing calls from racing it;
    * it never falls back from a refused cloud reader to local. The refusal is
      recorded by name and the tick ends.
    """
    from backend.services import lab_budget, lab_reader

    max_rows = int(_config.LAB_L2_MAX_ROWS_PER_TICK)
    choice = lab_reader.resolve(rows_this_tick=max_rows)
    if not choice.get("ok"):
        return {"status": "refused", "n": 0, "rows_typed_this_tick": 0,
                "reason": choice["refusal"], "detail": choice["detail"],
                "reader": choice["reader"],
                "spend_today_usd": choice.get("spend_today_usd"),
                "spend_cap_usd": choice.get("spend_cap_usd")}

    backend = choice["backend"]
    server = {}
    if backend == "local":
        try:
            server = model_status()
        except Exception as exc:                                   # noqa: BLE001
            return {"status": "error", "n": 0, "rows_typed_this_tick": 0,
                    "reader": "local", "detail": _trunc(exc)}
        started: dict = {}
        if not server.get("listening"):
            # 2026-09-18: this used to return PENDING_MODEL and stop. After the
            # 06:57 unclean reboot (Kernel-Power 41) nothing else started the server and
            # the loop said PENDING_MODEL for a whole day. It now asks
            # `ensure_model_server` first — which refuses BY NAME for a foreign
            # server, a sleep-permitting power plan or the daily cap.
            started = ensure_model_server(state, server=server)
            if started.get("started"):
                try:
                    server = model_status()
                except Exception as exc:                           # noqa: BLE001
                    return {"status": "error", "n": 0, "rows_typed_this_tick": 0,
                            "reader": "local", "detail": _trunc(exc),
                            "model_server_start": started}
        if not server.get("ready"):
            # `L2_typed_events` writes PENDING_MODEL with the input list frozen
            # and hashed; this loop returns to the scheduler rather than raising.
            return {"status": "PENDING_MODEL", "n": 0, "rows_typed_this_tick": 0,
                    "reader": "local",
                    "llama_server_up": bool(server.get("listening")),
                    "model_server_start": started or None,
                    "detail": (started.get("detail") if started.get("started")
                               else ("the model server is not ready; "
                                     + str(started.get("detail")
                                           or server.get("detail") or ""))[:300]),
                    "backlog_remaining": None}
        if server.get("foreign"):
            # A server that was already running when Aegis started is not ours to
            # stop. It IS ours to read from.
            server = {**server, "used_read_only": True}

    with state.model_lock:
        try:
            out = type_rows(backend=backend, max_rows=max_rows)
        except Exception as exc:                                   # noqa: BLE001
            return {"status": "error", "n": 0, "rows_typed_this_tick": 0,
                    "reader": choice["reader"], "detail": _trunc(exc)}

    corpus = out.get("corpus") or {}
    typed = int(out.get("rows_typed") or (out.get("counts") or {}).get("typed") or 0)
    # 2026-09-13 23:30: the mark used to land BEFORE the call, on every tick,
    # rows or not -- so a 15-minute typing cadence reset the idle clock for
    # ever and the 20-minute idle-GPU queue could never fire while the lab
    # ran. The model was touched only if a row was read.
    rows_read = int(out.get("rows_read") or (out.get("results") or {}).get("rows_read") or 0)
    if typed or rows_read:
        state.note_model_call()
    waiting = corpus.get("rows_waiting")
    status = str(out.get("status") or "")
    if status.startswith("PENDING_MODEL"):
        row_status = "PENDING_MODEL"
    elif status == "done" or (waiting == 0 and not typed):
        row_status = "nothing_to_do"
    else:
        row_status = "ok" if typed else "nothing_to_do"

    spend = lab_budget.spend_today()
    cost_source = "not_metered"
    if choice["metered"] and typed:
        usage = out.get("usage") or {}
        reported = float(usage.get("cost_usd") or 0.0)
        # THE RECEIPT LIES ABOUT ZERO, MEASURED. The 2026-09-13 17:18 DeepSeek
        # run typed 6,007 rows and printed `llm_spend_usd: 0.00` while the call
        # ledger said $2.04, because the field reads the local-cost path. So a
        # metered tick that reports 0.00 is booked at the ESTIMATE instead --
        # and SAYS which of the two it used, because a silently substituted
        # number is the failure the substitution exists to prevent, wearing the
        # other hat.
        actual = reported or lab_reader.estimate_usd(choice["reader"], typed)
        cost_source = "receipt" if reported else "estimate_substituted"
        spend = lab_budget.record(actual, backend=choice["reader"],
                                  rows=typed,
                                  what=f"L2 typing tick ({cost_source})")
    elif typed:
        cost_source = "local_unmetered"
        lab_budget.record(0.0, backend="local", rows=typed, what="L2 typing tick")

    return {
        "status": row_status,
        "n": typed,
        "rows_typed_this_tick": typed,
        "backlog_remaining": waiting,
        "rows_on_disk": corpus.get("rows_on_disk"),
        "reader": choice["reader"],
        "backend": backend,
        "metered": choice["metered"],
        "estimated_usd": choice["estimated_usd"],
        "cost_source": cost_source,
        "spend_today_usd": spend["spend_today_usd"],
        "spend_cap_usd": spend["cap_usd"],
        "reader_overlap": _overlap_block(),
        "llama_server_up": bool(server.get("listening")),
        "llama_server_foreign": bool(server.get("foreign")),
        "headline": out.get("headline"),
    }


def loop_decision_vs_reality(state: LabState) -> dict:
    """What we said vs what happened, across every mechanism, once an hour.

    Re-grades nothing: it rolls up what each mechanism's own grader already
    wrote, through `ledger_retrieval.visible_at`'s hindsight gate. A window with
    zero resolutions writes the receipt anyway, with every mechanism at
    `n_resolved: 0` — invariant 15, which is the rule that costs a session the
    most when skipped.
    """
    from backend.services import lab_decision_vs_reality as DVR
    payload = DVR.report()
    path = DVR.write_report(payload, day=run_date(), out=out_dir())
    n = int(payload.get("n_resolved") or 0)
    worst = payload.get("worst_miss") or {}
    return {
        "status": "ok" if n else "nothing_to_do",
        "n": n,
        "n_resolved": n,
        "pool_size": payload.get("pool_size"),
        "mechanisms_reported": len(payload.get("by_mechanism") or []),
        "mechanisms_with_resolutions": sum(
            1 for r in (payload.get("by_mechanism") or []) if r.get("n_resolved")),
        "undeclared_mechanisms": payload.get("undeclared_mechanisms"),
        "worst_miss_id": worst.get("record_id"),
        "worst_miss_brier": worst.get("brier"),
        "receipt_path": str(path),
        "headline": payload.get("headline"),
    }


def calendar_tickers() -> list[str]:
    """The names the per-ticker half of the calendar covers.

    The PM book's own positions, through the same loader `routers/pm.py`'s
    `/catalysts` already uses — a second answer to "which names do we hold"
    would be one answer too many. An unreadable book is CANNOT DETERMINE, not
    an empty list: the macro half still ships, and the receipt says the ticker
    half did not.
    """
    from backend.services import pm_engine
    book = pm_engine.load_book(strict=False)
    return [p.ticker for p in getattr(book, "positions", [])]


def loop_catalyst_calendar(state: LabState) -> dict:
    """Upcoming dates, every entry with its provenance and every gap named.

    Two halves. The per-ticker half is `pm_catalysts.calendar()`, CALLED, not
    rebuilt. The macro half is new: CPI and NFP from FRED's scheduled release
    dates, FOMC from a hand-seeded table. Every entry carries
    `engine_probability: null` with `AWAITING_L2`, because X3 is not wired and
    a fabricated probability attached to a real date is the one failure this
    loop could cause that nobody would notice for months.
    """
    from backend.services import macro_calendar

    tickers: list[str] = []
    ticker_refusal: str | None = None
    try:
        tickers = calendar_tickers()
    except Exception as exc:                                       # noqa: BLE001
        ticker_refusal = f"TICKERS_CANNOT_DETERMINE: {_trunc(exc)}"

    macro = macro_calendar.macro_block()
    per_ticker: dict = {}
    if tickers:
        try:
            from backend.services import pm_catalysts
            per_ticker = pm_catalysts.calendar(tickers)
        except Exception as exc:                                   # noqa: BLE001
            ticker_refusal = f"EARNINGS_HALF_FAILED: {_trunc(exc)}"

    payload = {
        "receipt": "lab_catalyst_calendar",
        "licence": "PRODUCT_EXPERIMENT", "stage": "raw", "llm_spend_usd": 0.0,
        "utc": _now(), "date": run_date(),
        "tickers": tickers, "ticker_refusal": ticker_refusal,
        "per_ticker": per_ticker, **macro,
    }
    path = out_dir() / f"lab_catalyst_calendar_{run_date()}.json"
    _write_atomic(path, payload)

    n_macro = len(macro.get("macro") or [])
    n_ticker = int((per_ticker.get("events_found") or 0))
    refusals = list(macro.get("refusals") or [])
    if ticker_refusal:
        refusals.append({"kind": "per_ticker", "refusal": ticker_refusal})
    return {
        "status": ("ok" if (n_macro or n_ticker)
                   else ("refused" if refusals else "nothing_to_do")),
        "n": n_macro + n_ticker,
        "macro_events": n_macro,
        "ticker_events": n_ticker,
        "tickers_checked": len(tickers),
        "macro_legs": macro.get("legs"),
        "fomc_table": (macro.get("fomc_table") or {}).get("status"),
        "refusals": [r.get("refusal") for r in refusals],
        "receipt_path": str(path),
        "headline": (f"{n_macro} macro date(s) and {n_ticker} ticker event(s) "
                     f"over {len(tickers)} name(s); "
                     f"{len(refusals)} named refusal(s); every "
                     f"engine_probability null (AWAITING_L2)"),
    }


def loop_nn_lab(state: LabState) -> dict:
    """The nightly refit sequence, once a night, only when the GPU is free.

    The idle condition is the same one the idle-GPU queue uses — this loop is
    not more entitled to the model than the typing loop is, and the in-process
    model lock serialises them whichever wins the tick.
    """
    from backend.services import lab_nn

    now = datetime.now(timezone.utc)
    idle = state.idle_minutes(now)
    if idle is not None and idle < IDLE_MINUTES:
        return {"status": "skipped", "n": 0,
                "reason": "MODEL_IN_USE",
                "detail": (f"a model-touching call finished {idle:.0f} min ago; "
                           f"{IDLE_MINUTES} min of quiet are required"),
                "idle_minutes": round(idle, 1)}

    yielded = yields_to("night_factory", "monday_night", now=now)
    if yielded:
        return {**yielded, "n": 0}

    # 2026-09-18: the lab is a starter. The refit itself does not call the model
    # server, so this is NOT a precondition for the sequence -- it is the one
    # once-a-night moment at which a box that rebooted with nothing listening
    # gets a server back. The row records the attempt either way, and the
    # sequence runs whatever the answer was.
    started = ensure_model_server(state, now=now)

    with state.model_lock:
        state.note_model_call(now)
        payload = lab_nn.run_nn_lab()
    path = lab_nn.write_receipt(payload, day=run_date(), out=out_dir())

    return {
        "status": "ok" if payload["n_heads"] else ("refused" if payload["refusals"]
                                                   else "nothing_to_do"),
        "model_server_start": started,
        "n": payload["n_heads"],
        "held_out_month": payload["held_out_month"],
        "heads": payload["n_heads"],
        "beat_last_night": payload["n_beat_last_night"],
        "undecided": payload["n_undecided"],
        "event_source": payload["event_source"],
        "refusals": payload["refusals"],
        "receipt_path": str(path),
        "headline": payload["headline"],
    }


def _receipt_today(job: str, today: str) -> bool:
    """Does the night folder for `today` already hold a receipt for `job`?"""
    folder = data_dir() / f"night_factory_{today}"
    try:
        return any(folder.glob(f"{job}_run[0-9][0-9].json"))
    except OSError:
        return False


def loop_idle_gpu_queue(state: LabState) -> dict:
    """The next registered job, ONLY when nothing else needs the model.

    This loop exists to fill the GAPS the scheduled evening run does not cover —
    daytime idle periods, a night `night_factory` was never launched. It is not
    a second scheduler for the same jobs, and it is the one loop that can
    actively collide with existing scheduled work, which is why it was built
    last and why every condition below is a refusal rather than a preference.

    Four gates, in this order:
      1. the model must have been quiet for `IDLE_MINUTES`;
      2. no FOREIGN server may be up — a server we did not start is the desktop
         app's or a human's, and taking the GPU out from under it is exactly
         the "not ours to stop" rule wearing a different hat;
      3. `night_factory` / `monday_night` / `daily_pass` must not be running;
      4. the job must not already have run today.
    """
    now = datetime.now(timezone.utc)
    row = state.loops["idle_gpu_queue"]
    dispatched: dict = dict(row.get("dispatched_on") or {})
    today = run_date()
    queue = [(j, m) for j, m in _config.LAB_IDLE_QUEUE]
    # 2026-09-14 05:05: "already ran today" is a fact about the NIGHT FOLDER,
    # not about this supervisor instance -- a restarted lab re-dispatched jobs a
    # factory had already read that day, and would have loaded Qwen3-30B beside
    # a 12 GB server. A receipt for the job under today's folder counts.
    remaining = [j for j, _ in queue
                 if dispatched.get(j) != today and not _receipt_today(j, today)]

    idle = state.idle_minutes(now)
    if idle is not None and idle < IDLE_MINUTES:
        return {"status": "skipped", "n": 0, "reason": "GPU_BUSY",
                "detail": (f"a model-touching call finished {idle:.0f} min ago; "
                           f"{IDLE_MINUTES} min of quiet are required"),
                "idle_minutes": round(idle, 1), "queue_remaining": remaining,
                "dispatched_on": dispatched}

    try:
        server = model_status()
    except Exception as exc:                                       # noqa: BLE001
        return {"status": "error", "n": 0, "detail": _trunc(exc),
                "queue_remaining": remaining, "dispatched_on": dispatched}
    if server.get("listening") and server.get("foreign"):
        return {"status": "skipped", "n": 0, "reason": "FOREIGN_SERVER_UP",
                "detail": (f"pid {server.get('pid')} is serving the model and "
                           f"Aegis did not start it; it may be mid-job and is "
                           f"not ours to interrupt"),
                "queue_remaining": remaining, "dispatched_on": dispatched}

    # 2026-09-18: half this queue reads through the model server, and after the
    # 06:57 unclean reboot (Kernel-Power 41) nothing was listening for the whole day. The
    # start is attempted; the dispatch is NOT gated on it, because the other
    # half of the queue does not need a model and blocking those on a server
    # that will not come up would trade one stall for another.
    started = ensure_model_server(state, now=now, server=server)

    yielded = yields_to("night_factory", "monday_night", "daily_pass", now=now)
    if yielded:
        return {**yielded, "n": 0, "queue_remaining": remaining,
                "dispatched_on": dispatched}

    if not remaining:
        return {"status": "nothing_to_do", "n": 0,
                "reason": "EVERY_QUEUED_JOB_ALREADY_RAN_TODAY",
                "queue_remaining": [], "dispatched_on": dispatched,
                "queue": [j for j, _ in queue]}

    job = remaining[0]
    minutes = dict(queue)[job]
    # 2026-09-14 05:00: record the dispatch BEFORE the call. The loop's own
    # 60 s box abandons this thread long before a real job returns, so a
    # record written after the return was never written, the next tick saw
    # the same job as still due, and the queue re-dispatched its first job
    # instead of advancing -- the first night ran X_anon_gap twice and never
    # reached E1.
    dispatched[job] = today
    row["dispatched_on"] = dispatched
    row["running_job"] = job
    with state.model_lock:
        state.note_model_call(now)
        try:
            payload = dispatch_job(job, minutes)
        except Exception as exc:                                   # noqa: BLE001
            logger.exception("idle queue job %s raised", job)
            dispatched[job] = today
            row["dispatched_on"] = dispatched
            return {"status": "error", "n": 0, "job": job,
                    "detail": _trunc(exc), "dispatched_on": dispatched,
                    "queue_remaining": [j for j in remaining if j != job]}

    # Marked dispatched whatever the verdict: a job that FAILED tonight has had
    # its turn, and re-dispatching it every five minutes would starve the rest
    # of the queue on one broken job.
    dispatched[job] = today
    row["dispatched_on"] = dispatched
    return {
        "status": "ok", "n": 1, "job": job, "box_minutes": minutes,
        "model_server_start": started,
        "verdict": payload.get("verdict"),
        "job_headline": str(payload.get("headline"))[:200],
        "dispatched_on": dispatched,
        "queue": [j for j, _ in queue],
        "queue_remaining": [j for j in remaining if j != job],
        "headline": (f"dispatched {job} (<= {minutes} min) into an idle GPU; "
                     f"{len(remaining) - 1} job(s) left in tonight's queue"),
    }


def loop_thematic_streams(state: LabState) -> dict:
    """Murat's four themes, each its own `mechanism_id`, each on its own cadence.

    Registration is idempotent and happens every tick; only the streams whose
    own cadence has elapsed do any work. A placeholder reports `n_fired: 0` with
    the reason rather than disappearing from the payload — a stream nobody
    remembers is waiting is a stream that gets invented from nothing later, with
    no history.
    """
    from backend.services import lab_themes

    tickers: list[str] = []
    try:
        tickers = calendar_tickers()
    except Exception as exc:                                       # noqa: BLE001
        logger.warning("thematic streams: no ticker list (%s)", _trunc(exc))

    out = lab_themes.run_due(tickers)
    path = out_dir() / f"lab_theme_streams_{run_date()}.json"
    _write_atomic(path, out)
    obs = sum(r["n_observations"] for r in out["streams"])
    fired = sum(r["n_fired"] for r in out["streams"])
    return {
        "status": "ok" if (obs or fired) else "nothing_to_do",
        "n": obs + fired,
        "observations": obs,
        "forecasts": fired,
        "tickers_checked": len(tickers),
        "streams": {r["mechanism_id"]: r["readiness"] for r in out["streams"]},
        "blocked": {r["mechanism_id"]: r.get("blocked_by")
                    for r in out["streams"] if r.get("blocked_by")},
        "receipt_path": str(path),
        "headline": out["headline"],
    }


def loop_status(state: LabState) -> dict:
    """The heartbeat's own loop. Writing the file is the tick's last act, so
    this one only records that the writer was reached."""
    return {"status": "ok", "note": "lab_status.json written at the end of the tick"}


HANDLERS: dict[str, Callable[[LabState], dict]] = {
    "daily_pass_dispatch": loop_daily_pass_dispatch,
    "night_launcher_dispatch": loop_night_launcher_dispatch,
    "news_pull": loop_news_pull,
    "l2_typing": loop_l2_typing,
    "decision_vs_reality": loop_decision_vs_reality,
    "catalyst_calendar": loop_catalyst_calendar,
    "nn_lab": loop_nn_lab,
    "idle_gpu_queue": loop_idle_gpu_queue,
    "thematic_streams": loop_thematic_streams,
    "status": loop_status,
}
assert set(HANDLERS) == {name for name, _ in LOOPS}, \
    "every declared loop needs a handler"


# ===========================================================================
# THE SUPERVISOR
# ===========================================================================


def check_power(state: LabState, now: datetime) -> None:
    """Re-check the power plan on a cadence, never only at boot.

    A refusal does NOT kill the process. It pauses the GPU-touching loops and
    says so; the next recheck can un-pause them without a human restarting a
    scheduled task. `night_factory` checks once because its longest run is
    hours; this supervisor runs for days.
    """
    if state.power_checked_utc:
        prev = _as_dt(state.power_checked_utc)
        if prev is not None and (now - prev) < timedelta(minutes=POWER_RECHECK_MINUTES):
            return
    try:
        state.power_refusal = power_refusal()
    except Exception as exc:                                       # noqa: BLE001
        state.power_refusal = None
        logger.warning("power check raised (%s); CANNOT DETERMINE, continuing",
                       _trunc(exc))
    state.power_checked_utc = now.isoformat(timespec="seconds")


def tick(state: LabState, *, now: datetime | None = None) -> dict:
    """One heartbeat: every DUE loop, in declared order, each under its box."""
    now = now or datetime.now(timezone.utc)
    state.ticks += 1
    check_power(state, now)
    ran: list[str] = []

    for name, _what in LOOPS:
        row = state.loops[name]
        if not state.due(name, now):
            row["due"] = False
            continue
        row["due"] = True
        if name in state.inflight:
            row["status"] = "timeout"
            row["detail"] = ("a previous call to this loop has not returned; "
                             "not re-issued")
            continue
        if state.power_refusal and name in MODEL_LOOPS:
            row["status"] = "paused"
            row["detail"] = f"POWER_PLAN_ALLOWS_SLEEP: {str(state.power_refusal)[:200]}"
            row["paused_since_utc"] = row.get("paused_since_utc") or now.isoformat(
                timespec="seconds")
            continue
        row.pop("paused_since_utc", None)
        state.inflight.add(name)
        t0 = time.time()
        try:
            out = call_boxed(lambda n=name: HANDLERS[n](state), TIMEOUTS[name], name)
            state.inflight.discard(name)
        except LoopTimeout as exc:
            # Left in `inflight` ON PURPOSE: the thread is abandoned, not dead,
            # and re-issuing the same loop against the same resource is how one
            # stuck call becomes a pile of them.
            row["status"] = "timeout"
            row["detail"] = f"timeout_after_{TIMEOUTS[name]:.0f}s"
            row["error"] = str(exc)[:300]
            continue
        except Exception as exc:                                   # noqa: BLE001
            state.inflight.discard(name)
            logger.exception("lab loop %s raised", name)
            row["status"] = "error"
            row["detail"] = _trunc(exc)
            continue
        row.update({k: v for k, v in out.items() if k != "what"})
        row["seconds"] = round(time.time() - t0, 2)
        row["last_tick_utc"] = now.isoformat(timespec="seconds")
        ran.append(name)

    payload = status_payload(state, now)
    _write_atomic(status_path(), payload)
    try:
        write_learned_line(payload)
    except OSError as exc:
        logger.warning("could not write the LEARNED line (%s)", _trunc(exc))
    payload["loops_run_this_tick"] = ran
    return payload


def _theme_status() -> dict:
    from backend.services import lab_themes
    try:
        return lab_themes.status()
    except Exception as exc:                                       # noqa: BLE001
        return {"status": "CANNOT DETERMINE", "why": _trunc(exc)}


def driver_block(state: LabState) -> dict:
    """The two time-of-day drivers, their configured local time, and what the
    lab's last dispatch of each came to.

    Present for BOTH drivers on every tick, with `last_result: null` before the
    first dispatch of the date — the invariant the rest of this file keeps: a
    loop that did nothing says so with a reason, and never by an omitted key.
    """
    out: dict = {}
    for name, spec in DRIVERS.items():
        row = state.loops.get(spec["loop"]) or {}
        rec = dict(row.get("dispatched") or {})
        out[name] = {
            "local_time": spec["local_time"],
            "weekdays_only": spec["weekdays_only"],
            "module": spec["module"],
            "args": list(spec["args"]),
            "box_s": float(_config.LAB_DRIVER_BOX_S[name]),
            "fallback_scheduled_task": spec["task"],
            "last_status": row.get("status"),
            "last_reason": row.get("reason"),
            "last_result": rec.get("result"),
            "last_dispatch": rec or None,
            "last_tick_utc": row.get("last_tick_utc"),
        }
    return out


def status_payload(state: LabState, now: datetime | None = None) -> dict:
    """`lab_status.json` — every loop's block present every tick, always."""
    now = now or datetime.now(timezone.utc)
    try:
        model = model_status()
    except Exception as exc:                                       # noqa: BLE001
        model = {"error": _trunc(exc)}
    from backend.services import lab_budget
    spend = lab_budget.spend_today()
    lock = read_lock()
    return {
        "receipt": "always_on_lab",
        "licence": "PRODUCT_EXPERIMENT",
        "utc": now.isoformat(timespec="seconds"),
        "date": run_date(),
        "running": state.stopped_by is None,
        "stopped_by": state.stopped_by,
        "pid": os.getpid(),
        "started_utc": state.started_utc,
        "ticks": state.ticks,
        "heartbeat_minutes": HEARTBEAT_MINUTES,
        "power_plan": (f"REFUSED, may sleep since {state.power_checked_utc}"
                       if state.power_refusal else "ok (or CANNOT DETERMINE)"),
        "power_refusal": (str(state.power_refusal)[:400] if state.power_refusal else None),
        "power_checked_utc": state.power_checked_utc,
        "periods_minutes": PERIODS,
        "loops": state.loops,
        "last_model_call_utc": state.last_model_call_utc,
        "idle_minutes": state.idle_minutes(now),
        "model_server_starts": dict(state.model_server_starts),
        "model_server_starts_today": state.starts_today(run_date()),
        "model_server_start_cap_per_day": int(
            _config.LAB_MODEL_SERVER_MAX_STARTS_PER_DAY),
        "lab_starts_model_server": bool(_config.LAB_STARTS_MODEL_SERVER),
        "model_server_hold": model_server_hold_path().exists(),
        "llama_server": {"up": bool(model.get("listening")),
                         "ready": bool(model.get("ready")),
                         "owned_by_us": bool(model.get("started_by_aegis")),
                         "foreign_owner_pid": (model.get("pid")
                                               if model.get("foreign") else None),
                         "detail": model.get("detail")},
        "spend_today_usd": spend["spend_today_usd"],
        "spend_cap_usd": spend["cap_usd"],
        "spend_cap_reached": spend["cap_reached"],
        "thematic_streams": _theme_status(),
        # Chunk 17. Both dispatch loops, named, with their last result — so a
        # reader learns "the 06:30 pass ran" or "it has not fired and here is
        # why" from the same file that carries everything else, rather than
        # from a scheduled task's Last Result nobody queries.
        "drivers": driver_block(state),
        "single_instance_lock": lock,
        # The PREVIOUS instance's last words, carried forward by `acquire_lock`.
        # `EXIT_NOT_RECORDED` is the honest answer for a killed or crashed one.
        "previous_exit_reason": lock.get("previous_exit_reason"),
        "previous_exit_utc": lock.get("previous_exit_utc"),
        "stop_file": str(stop_path()),
        "read_me_first": (
            "One block per DECLARED loop, every tick, whether or not it ran — a "
            "loop that found nothing says `nothing_to_do` with a count, never an "
            "omitted key. `last_tick_utc` advances only on a SUCCESSFUL tick, so "
            "a loop whose stamp stops moving while `utc` keeps moving is stuck, "
            "which is the signal this file exists to make visible. Nothing here "
            "places an order. The lab DOES start the model server when nothing "
            "is listening (2026-09-18, after an unclean reboot left every "
            "model loop PENDING_MODEL for a day) — capped per date, never for a "
            "foreign server, and it still stops nothing."),
    }


def _on_signal(signum, _frame):
    """Record the reason, then leave by the tidy path.

    `SystemExit` unwinds `run_forever`'s `finally`, so the lock is released
    with a reason instead of left looking like a crash. This is the "signal-
    safe path" half of the exit-reason rule; the other half is `atexit`, and
    NEITHER of them covers `TerminateProcess` or a bugcheck — which is exactly
    why the next instance writes `EXIT_NOT_RECORDED` rather than assuming.
    """
    import signal as _signal
    name = next((n for n in ("SIGTERM", "SIGINT", "SIGBREAK")
                 if getattr(_signal, n, None) == signum), str(signum))
    record_exit(f"signal:{name}")
    raise SystemExit(128 + int(signum))


def install_exit_hooks():
    """`atexit` + the signals a supervisor is actually asked to stop with.

    Returns what to call to put the previous handlers back: a test (or a caller
    that is not the process's main loop) must not leave this process with the
    lab's SIGINT handler installed.
    """
    import atexit
    import signal as _signal

    atexit.register(record_exit, "process_exit_unclassified")
    previous: list = []
    for nm in ("SIGTERM", "SIGINT", "SIGBREAK"):
        sig = getattr(_signal, nm, None)
        if sig is None:
            continue
        try:
            previous.append((sig, _signal.signal(sig, _on_signal)))
        except (ValueError, OSError, RuntimeError):     # not the main thread
            continue

    def _restore() -> None:
        for sig, handler in previous:
            try:
                _signal.signal(sig, handler)
            except (ValueError, OSError, RuntimeError, TypeError):
                pass
        try:
            atexit.unregister(record_exit)
        except Exception:                                          # noqa: BLE001
            pass

    return _restore


def run_forever(*, max_ticks: int | None = None,
                sleeper: Callable[[float], None] | None = None,
                clock: Callable[[], datetime] | None = None) -> dict:
    """The loop. Holds the lock, ends on STOP, never on a sub-loop's failure.

    It also records WHY it ended, into the lock, before releasing it. Three lab
    deaths in 30 hours left nothing behind but the next instance's "overwrote a
    stale lock" line; a reason that is only ever written on the tidy path is
    still worth having, because it turns every OTHER death into a named
    absence.
    """
    clock = clock or (lambda: datetime.now(timezone.utc))
    sleeper = sleeper or time.sleep
    rec = acquire_lock()
    restore = install_exit_hooks()
    state = LabState.load()
    state.started_utc = rec["started_utc"]
    payload: dict = {}
    reason = "process_exit_unclassified"
    try:
        while True:
            if stop_path().exists():
                state.stopped_by = "STOP_file"
                reason = "STOP_file"
                payload = status_payload(state, clock())
                _write_atomic(status_path(), payload)
                break
            payload = tick(state, now=clock())
            if max_ticks is not None and state.ticks >= max_ticks:
                reason = "ticks_exhausted"
                break
            sleeper(HEARTBEAT_MINUTES * 60)
    except KeyboardInterrupt:
        reason = "KeyboardInterrupt"
        raise
    except SystemExit:
        reason = "SystemExit"
        raise
    except BaseException as exc:                                   # noqa: BLE001
        reason = f"exception:{type(exc).__name__}"
        raise
    finally:
        release_lock(reason)
        restore()
    return payload


# ===========================================================================
# PRINTERS
# ===========================================================================


def plan() -> dict:
    """What a real run WOULD do. Reads the clock and the lock; calls no loop,
    touches no network and no model."""
    holder = lock_holder()
    return {
        "dry_run": True,
        "date": run_date(),
        "heartbeat_minutes": HEARTBEAT_MINUTES,
        "status_file_would_be": str(status_path()),
        "lock_file": str(lock_path()),
        "lock_state": holder["state"],
        "stop_file": str(stop_path()),
        "power_recheck_minutes": POWER_RECHECK_MINUTES,
        "idle_minutes": IDLE_MINUTES,
        "spend_cap_usd": _config.LAB_DAILY_SPEND_CAP_USD,
        "l2_reader": os.getenv("AEGIS_L2_READER", "local"),
        "loops": [{"loop": n, "what": w, "period_minutes": PERIODS[n],
                   "timeout_s": TIMEOUTS[n],
                   "touches_model": n in MODEL_LOOPS} for n, w in LOOPS],
        "drivers": {n: {"local_time": s["local_time"],
                        "weekdays_only": s["weekdays_only"],
                        "argv": [sys.executable, "-m", s["module"], *s["args"]],
                        "box_s": float(_config.LAB_DRIVER_BOX_S[n]),
                        "fallback_scheduled_task": s["task"]}
                    for n, s in DRIVERS.items()},
        "previous_exit_reason": holder.get("previous_exit_reason"),
        "note": ("--dry-run calls no loop: it makes no network request, probes "
                 "no model server, and writes nothing. It prints the cadence "
                 "table and the process model, which is what a reader deciding "
                 "whether to register the task needs."),
    }


def print_plan(p: dict) -> None:
    print("=" * 74)
    print(f"ALWAYS-ON LAB — dry run — {p['date']}")
    print("=" * 74)
    print(f"  heartbeat        every {p['heartbeat_minutes']} min")
    print(f"  lock             {p['lock_state']}  {p['lock_file']}")
    print(f"  STOP file        {p['stop_file']}")
    print(f"  power recheck    every {p['power_recheck_minutes']} min")
    print(f"  idle threshold   {p['idle_minutes']} min with no model call")
    print(f"  spend cap        ${p['spend_cap_usd']:.2f}/UTC day")
    print(f"  L2 reader        {p['l2_reader']}")
    print()
    print(f"  {'loop':22s} {'period':>10s} {'box':>8s}  model  what")
    for row in p["loops"]:
        print(f"  {row['loop']:22s} {row['period_minutes']:6d} min "
              f"{row['timeout_s']:7d}s  "
              f"{'GPU' if row['touches_model'] else '   ':5s}  {row['what'][:44]}")
    print()
    print(f"  {'driver':22s} {'local':>10s} {'box':>8s}  days     fallback task")
    for name, row in p["drivers"].items():
        print(f"  {name:22s} {row['local_time']:>10s} "
              f"{row['box_s']:7.0f}s  "
              f"{'Mon-Fri' if row['weekdays_only'] else 'daily  '}"
              f"  {row['fallback_scheduled_task']}")
    print(f"\n  previous exit reason -> {p['previous_exit_reason']}")
    print(f"\n  status file -> {p['status_file_would_be']}")
    print(f"\n  {p['note']}")


def _print_schtasks() -> int:
    """Print the registration. Deliberately does not run it.

    ONLOGON, not ONSTART and not a fixed daily time: it is the literal
    translation of "live whenever pc is on". The task fires once per
    interactive logon and the supervisor loops until STOP, rather than firing
    once and exiting the way `daily_pass` and `run_night_launcher` do.

    /RL LIMITED: nothing here needs admin rights, and an elevated unattended
    loop is a bigger blast radius for the same job.
    """
    root = os.getcwd()
    empty = f"{root}\\backend\\data\\optimus\\empty_stdin.txt"
    log = f"{root}\\backend\\data\\optimus\\always_on_lab.log"
    py = sys.executable
    print("=" * 74)
    print("REGISTER THE ALWAYS-ON LAB — printed, not run; registering it is a decision")
    print("=" * 74)
    print(f"""
  * ONLOGON, not ONSTART: the lab needs an interactive session (the desktop app
    owns the model server, and a session-0 service cannot see it).

  * /RL LIMITED. Nothing this loop does needs admin rights.

  * ONE instance. A second logon's supervisor reads the shared lock at
    {lock_path()} and refuses with ALREADY_RUNNING.

  * The stdin redirect comes from a REGULAR FILE, not from NUL: on Windows
    `_isatty()` returns true for any character device, so `< NUL` redirects and
    changes nothing observable (paid for on 2026-08-18).

  * No pipe. `cmd | tail` reports tail's exit code, and the exit code is the
    guard.
""")
    # 2026-09-13, measured: `schtasks` caps /TR at 261 characters (this line is
    # longer) and refuses ONLOGON for a non-elevated user ("Access is denied").
    # What registered without elevation was a two-line wrapper .cmd and a
    # windowless .vbs in the user's Startup folder -- the same effect, printed
    # first because it is the one that works. The schtasks form stays below for
    # an elevated shell.
    wrapper = os.path.join(root, "backend", "data", "optimus", "always_on_lab.cmd")
    print("  # 1. the wrapper (schtasks /TR is capped at 261 chars):")
    print(f"  #    {wrapper}  containing:")
    print("  #      @echo off")
    print(f"  #      cd /d {root}")
    print(f"  #      {py} -m scripts.always_on_lab < {empty} >> {log} 2>&1")
    print("  # 2. windowless at logon WITHOUT elevation (the Startup folder):")
    startup = os.path.join("%APPDATA%", "Microsoft", "Windows", "Start Menu", "Programs", "Startup", f"{TASK_NAME}.vbs")
    print(f"  #    {startup}  containing:")
    print('  #      Set sh = CreateObject("WScript.Shell")')
    print(f'  #      sh.Run """{wrapper}""", 0, False')
    print("  # 3. or, from an ELEVATED shell only (ONLOGON is denied otherwise):")
    print(f'  schtasks /Create /TN "{TASK_NAME}" /SC ONLOGON /RL LIMITED /TR "{wrapper}"')
    print("\n  Already registered? Change it in place rather than re-registering:\n")
    print(f'  schtasks /Change /TN "{TASK_NAME}" /TR "{wrapper}"')
    print(f"""
  THE OTHER TWO TASKS ARE NOW FALLBACKS, NOT THE CLOCK (chunk 17, 2026-09-19).
  {DRIVERS['daily_pass']['task']} and {DRIVERS['night_launcher']['task']}
  both failed this week with 0x80070520 (no logon session) and, the week
  before, with 0x80070420 for four days. The lab now dispatches
  `{DRIVERS['daily_pass']['module']}` at {DRIVERS['daily_pass']['local_time']} local and
  `{DRIVERS['night_launcher']['module']} {' '.join(DRIVERS['night_launcher']['args'])}`
  at {DRIVERS['night_launcher']['local_time']} local on weekdays, from inside a process that is
  already running unattended. Leave both tasks registered for now: whichever
  fires first writes the receipt, and the other one's already-ran gate reads
  that receipt and stands down. Deleting them is an attended decision.
""")
    print(f"""
  To stop it: create {stop_path()} and wait one heartbeat
  ({HEARTBEAT_MINUTES} min). Never `taskkill /F /IM python.exe` — on
  2026-09-06 that killed two other agents' jobs, a test suite and 1,676
  already-billed extractions. Kill by the PID in
  {lock_path()}, or do not kill.

  The log redirect is a convenience, NOT the evidence. The evidence is
  {status_path()} and the per-loop receipts in the night folder.
""")
    return 0


#: The six acceptance criteria, declared so the report walks THEM rather than
#: whatever happened to be checkable. Each is (id, what it asserts).
ACCEPTANCE_CRITERIA: tuple[tuple[str, str], ...] = (
    ("news_pull_never_gapped",
     "`news_pull`'s last_tick_utc never gapped by more than 2x its declared "
     "period on any of the three dates"),
    ("decision_vs_reality_per_date",
     "at least one full decision_vs_reality receipt per date, even at "
     "n_resolved 0 everywhere"),
    ("catalyst_calendar_refreshed",
     "the catalyst calendar refreshed at least once per date with the macro "
     "block populated, or FRED_KEY_ABSENT named"),
    ("no_double_write_collisions",
     "zero collisions with night_factory/daily_pass recorded as anything other "
     "than a clean skip"),
    ("spend_cap_never_breached",
     "the daily dollar cap never breached"),
    ("learned_line_present",
     "LEARNED_<date>.md carries the supervisor's line for all three dates"),
)


def learned_line(payload: dict) -> str:
    """The ONE line the lab contributes to the day's brain file.

    Written whether or not anything interesting happened — the "a session that
    ships thirty changes and moves none of them says RESULT IMPROVEMENT: NONE"
    discipline, on a daily cadence instead of a session one.
    """
    loops = payload.get("loops") or {}
    news = loops.get("news_pull") or {}
    l2 = loops.get("l2_typing") or {}
    nn = loops.get("nn_lab") or {}
    idle = loops.get("idle_gpu_queue") or {}
    themes = payload.get("thematic_streams") or {}
    red = news.get("sources_red") or []
    return (
        f"Always-on lab, {payload.get('date')}: news pulled from "
        f"{news.get('sources_pulled', 0)} source(s) ({len(red)} red); L2 typed "
        f"{l2.get('rows_typed_this_tick', 0)} row(s) (backlog "
        f"{l2.get('backlog_remaining')}, reader={l2.get('reader', 'local')}); NN lab "
        f"{nn.get('heads', 0)} head(s), {nn.get('beat_last_night', 0)} beat last "
        f"night on held-out {nn.get('held_out_month')}; idle-GPU queue ran "
        f"{idle.get('job') or 'nothing'}; thematic streams: "
        f"{', '.join(f'{k}={v}' for k, v in sorted(themes.items()))}; spend "
        f"${payload.get('spend_today_usd', 0.0):.2f}/"
        f"${payload.get('spend_cap_usd', 0.0):.2f} cap.")


def write_learned_line(payload: dict) -> Path:
    """Append the line to `brain/LEARNED_<date>.md`, creating the file."""
    p = data_dir() / "brain" / f"LEARNED_{payload.get('date')}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    line = f"> {learned_line(payload)}\n"
    prior = p.read_text(encoding="utf-8") if p.exists() else ""
    if line not in prior:
        with p.open("a", encoding="utf-8") as fh:
            fh.write(line)
    return p


def acceptance_report(*, dates: list[str] | None = None,
                      status: dict | None = None) -> dict:
    """Is the lab ACCEPTED? Three dates of real coverage, not three task runs.

    `ONLOGON` can fire and die repeatedly in a bad state and still produce three
    "runs"; the bar is three DATES on which the machine was actually on. This
    report reads what is on disk and REFUSES to conclude from what is absent:
    a date with no receipts is `no_evidence`, never a failure and never a pass.
    """
    payload = status if status is not None else _read_status()
    today = date.fromisoformat(run_date())
    want = dates or [(today - timedelta(days=i)).isoformat()
                     for i in range(_config.LAB_ACCEPTANCE_DATES - 1, -1, -1)]

    per_date = []
    for day in want:
        folder = data_dir() / f"night_factory_{day}"
        dvr = folder / f"decision_vs_reality_{day}.json"
        cal = folder / f"lab_catalyst_calendar_{day}.json"
        learned = data_dir() / "brain" / f"LEARNED_{day}.md"
        row = {
            "date": day,
            "night_folder_exists": folder.is_dir(),
            "decision_vs_reality": dvr.exists(),
            "catalyst_calendar": cal.exists(),
            "learned_line": (learned.exists()
                             and "Always-on lab" in learned.read_text(
                                 encoding="utf-8", errors="replace")),
        }
        row["evidence"] = any(v for k, v in row.items() if k != "date")
        per_date.append(row)

    dated = [r for r in per_date if r["evidence"]]
    spend = _spend_block()
    checks = {
        "news_pull_never_gapped": "CANNOT DETERMINE (no per-tick history file yet)",
        "decision_vs_reality_per_date": all(r["decision_vs_reality"] for r in per_date)
        if dated else "no_evidence",
        "catalyst_calendar_refreshed": all(r["catalyst_calendar"] for r in per_date)
        if dated else "no_evidence",
        "no_double_write_collisions": "CANNOT DETERMINE (collisions are recorded "
                                      "per tick, not per date)",
        "spend_cap_never_breached": not spend["cap_reached"],
        "learned_line_present": all(r["learned_line"] for r in per_date)
        if dated else "no_evidence",
    }
    accepted = (len(dated) >= _config.LAB_ACCEPTANCE_DATES
                and all(v is True for v in checks.values()))
    return {
        "receipt": "always_on_lab_acceptance",
        "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "utc": _now(), "date": run_date(),
        "dates_required": _config.LAB_ACCEPTANCE_DATES,
        "min_hours_per_date": _config.LAB_ACCEPTANCE_MIN_HOURS,
        "dates_examined": want,
        "dates_with_evidence": [r["date"] for r in dated],
        "per_date": per_date,
        "criteria": {k: v for k, v in ACCEPTANCE_CRITERIA},
        "checks": checks,
        "spend": spend,
        "accepted": accepted,
        "status": ("ACCEPTED" if accepted else
                   ("BUILT_UNACCEPTED" if len(dated) < _config.LAB_ACCEPTANCE_DATES
                    else "BUILT_NOT_YET_PASSING")),
        "headline": (
            f"{len(dated)} of {_config.LAB_ACCEPTANCE_DATES} date(s) carry "
            f"evidence; " + ("ACCEPTED" if accepted else
                             "NOT accepted — acceptance needs real wall-clock "
                             "days, not agent time")),
        "read_me_first": (
            "Three DATES on which the machine was actually on, not three task "
            "runs: ONLOGON can fire and die repeatedly in a bad state and still "
            "produce three runs. A date with no receipts is `no_evidence` — "
            "neither a pass nor a failure. Until every check is True the honest "
            "status is 'built, unaccepted', and a fabricated acceptance receipt "
            "would be worse than none."),
    }


def _read_status() -> dict:
    p = status_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _spend_block() -> dict:
    from backend.services import lab_budget
    return lab_budget.spend_today()


def write_acceptance(report: dict | None = None) -> Path:
    report = report if report is not None else acceptance_report()
    day = report.get("date") or run_date()
    p = out_dir() / f"always_on_lab_acceptance_{day}.json"
    _write_atomic(p, report)
    return p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="always_on_lab",
                                 description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="print the cadence table and the process model; run nothing")
    ap.add_argument("--schtasks", action="store_true",
                    help="print the ONLOGON registration; runs nothing")
    ap.add_argument("--ticks", type=int, default=None,
                    help="run this many heartbeats and exit (default: until STOP)")
    ap.add_argument("--acceptance", action="store_true",
                    help="write the acceptance receipt and exit")
    a = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:                                          # noqa: BLE001
            pass

    if a.schtasks:
        return _print_schtasks()
    if a.dry_run:
        print_plan(plan())
        return 0
    if a.acceptance:
        report = acceptance_report()
        path = write_acceptance(report)
        print(json.dumps({**report, "path": str(path)}, indent=1, default=str))
        return 0
    try:
        payload = run_forever(max_ticks=a.ticks)
    except AlreadyRunning as exc:
        print(f"REFUSED: {exc}")
        return 2
    print(json.dumps({k: payload.get(k) for k in
                      ("utc", "ticks", "running", "stopped_by",
                       "spend_today_usd", "power_plan")}, indent=1, default=str))
    return 0


__all__ = ["ACCEPTANCE_CRITERIA", "DRIVERS", "EXIT_NOT_RECORDED",
           "EXIT_REASONS", "HANDLERS", "LOOPS", "MODEL_SERVER_REFUSALS",
           "PERIODS",
           "SCHEDULED_DRIVERS", "STATUSES", "TIMEOUTS", "AlreadyRunning",
           "LabState", "LoopTimeout", "acceptance_report", "acquire_lock",
           "cadence_admits", "calendar_tickers", "call_boxed", "check_power",
           "data_dir", "dispatch_driver", "dispatch_job", "driver_block",
           "driver_log_path", "driver_receipt", "due_at_local_time",
           "empty_stdin_path", "ensure_model_server", "install_exit_hooks",
           "launch_driver", "learned_line", "local_now",
           "lock_holder", "model_server_hold_path", "record_exit",
           "lock_path", "main", "model_status", "news_sources", "out_dir",
           "parsed_rate_limit", "pid_alive", "pid_names_lab", "plan",
           "power_refusal", "print_plan", "pull_news", "read_lock",
           "release_lock", "run_date", "run_forever", "running_drivers",
           "scan_processes", "start_model_server", "status_path",
           "status_payload", "stop_path",
           "tick", "type_rows", "write_acceptance", "write_learned_line",
           "yields_to"]


if __name__ == "__main__":
    raise SystemExit(main())
