"""Long simulations with a START button, a STOP button, and no lost work.

MURAT, 2026-09-22
=================
    "this week I will just run the continious sims so on the exe the run
     simulation should work the simulations can very from 6-8-10-12 hours
     there can be just a start and stop button to make it more convinent but
     it should stop at a safe time save everything and maybe continue not
     terminate or leave it on the middle."

Three requirements, and the third is the one with teeth:

1. one button to start, one to stop;
2. a declared length -- 6, 8, 10 or 12 hours;
3. **a stop is a SAFE stop.** Never mid-unit, never a lost checkpoint, and the
   next run CONTINUES rather than starting over.

WHY THIS IS NOT `night_run_until`
=================================
`night_run_until` is a CLOCK: it ends at a wall-clock time and kills its
children by PID at T-5. That is right for an unattended night with a hard
deadline, and wrong for a session a human starts and stops from a button:
killing a tree mid-job loses whatever that job had not yet written, which is
exactly the 2026-09-10 failure where `night_g3_evolve_v2` died 3.1 hours into a
5-hour box and its receipt said `exited with no receipt`.

So this runs a CYCLE LOOP instead. Work is cut into units small enough that
finishing the current one is always cheap, and every boundary between units is a
safe stopping point where state is on disk. Stopping means "finish this unit,
checkpoint, exit" -- not "die now".

THE STATE MACHINE, AND WHAT EACH STATE PROMISES
===============================================
    IDLE       nothing running; a previous session may be RESUMABLE
    RUNNING    the loop owns the work; heartbeat is fresh
    STOPPING   a stop was requested; the current unit is finishing
    STOPPED    clean exit at a unit boundary; every cycle's work is on disk
               and `resume_from` names where the next run continues
    COMPLETED  the requested duration elapsed and the loop stopped itself
    UNCLEAN    the process vanished without writing a stop receipt (crash,
               power loss, force-kill). The checkpoint is still good -- that is
               the point of checkpointing -- but the last cycle is UNKNOWN and
               the receipt says so rather than pretending it finished.

`UNCLEAN` exists because "the process is gone" and "the work finished" are
different facts, and a status that cannot tell them apart teaches its reader to
assume the happy one. A heartbeat older than `STALE_AFTER_S` with no stop
receipt IS the unclean case, and `status()` derives it rather than trusting a
field somebody remembered to set.

WHAT A CYCLE IS
===============
One pass of: reconcile the broker -> refresh the ranking -> plan the book ->
grade whatever reality has resolved -> run one queued research unit. Each is
idempotent, each writes its own receipt, and the cycle number is the resume
point. A 6-hour session is not one 6-hour job; it is N cycles, and N is how many
fit.

WHAT IT REFUSES
===============
* **A second session.** One simulation owns the machine's GPU and the broker
  lease. `start()` refuses while another is RUNNING rather than racing it.
* **A duration outside the declared set.** 6/8/10/12 hours, because an
  arbitrary number is how a "quick test" becomes an unattended 40-hour run.
  `SMOKE_MINUTES` is the one exception and it is named, not a loophole.
* **Resuming into a different configuration.** A resume whose parameters moved
  is a different experiment wearing the first one's session id.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from backend import config as _cfg

STATE_DIR = _cfg.OPTIMUS_LEDGER_DIR / "sim"
SESSION_PATH = STATE_DIR / "session.json"
STOP_FLAG = STATE_DIR / "STOP_REQUESTED"
HISTORY_PATH = STATE_DIR / "sessions.jsonl"

#: The durations the button offers. An arbitrary duration is how a "quick test"
#: becomes an unattended 40-hour run nobody meant to start.
ALLOWED_HOURS = (6, 8, 10, 12)
#: The named exception, for rehearsals. Minutes, not hours, and it is written
#: into the receipt so a smoke run can never be read as a real session.
SMOKE_MINUTES = (5, 15, 30, 60)

#: A heartbeat older than this, with no stop receipt, means the process is gone.
STALE_AFTER_S = 300
#: How long a stop waits for the current unit to finish before escalating.
#: Generous on purpose: the whole point is not to interrupt a unit.
STOP_GRACE_S = 900


class SimRefused(RuntimeError):
    """The simulation cannot start or stop safely."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("sim_session: unreadable %s (%s)", path, exc)
        return None


def _atomic_write(path: Path, payload: dict) -> None:
    """tmp + os.replace. A kill mid-write leaves the PREVIOUS good file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, path)


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        import psutil
        return psutil.pid_exists(int(pid))
    except ImportError:
        pass
    if os.name == "nt":
        r = subprocess.run(["tasklist", "/FI", f"PID eq {int(pid)}"],
                           capture_output=True, text=True)
        return str(pid) in r.stdout
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


# ──────────────────────────────── status ────────────────────────────────────

def status() -> dict:
    """What is running, how far in, and whether the last session ended cleanly.

    DERIVES the unclean case from the heartbeat rather than reading a field: a
    crashed process cannot set its own "I crashed" flag, so a status that waits
    to be told will report RUNNING forever.
    """
    s = _read(SESSION_PATH)
    if not s:
        return {"state": "IDLE", "session": None, "resumable": False,
                "allowed_hours": list(ALLOWED_HOURS),
                "smoke_minutes": list(SMOKE_MINUTES)}

    state = s.get("state", "IDLE")
    alive = pid_alive(s.get("pid"))
    hb = s.get("heartbeat")
    age = None
    if hb:
        try:
            age = (datetime.now(timezone.utc)
                   - datetime.fromisoformat(hb)).total_seconds()
        except ValueError:
            age = None

    if state in ("RUNNING", "STOPPING") and not alive:
        state = "UNCLEAN"
        s["unclean_reason"] = (
            f"pid {s.get('pid')} is gone and no stop receipt was written. The "
            f"checkpoint at cycle {s.get('cycle', 0)} is still good; what the "
            f"cycle after it did is UNKNOWN.")
    elif state == "RUNNING" and age is not None and age > STALE_AFTER_S:
        state = "UNCLEAN"
        s["unclean_reason"] = (
            f"heartbeat is {age:.0f}s old (> {STALE_AFTER_S}s) while the process "
            f"still exists: it is wedged, not working.")

    planned_end = s.get("planned_end")
    remaining = None
    if planned_end and state in ("RUNNING", "STOPPING"):
        try:
            remaining = max(0.0, (datetime.fromisoformat(planned_end)
                                  - datetime.now(timezone.utc)).total_seconds())
        except ValueError:
            remaining = None

    return {
        "state": state,
        "session": s,
        "pid_alive": alive,
        "heartbeat_age_s": round(age, 1) if age is not None else None,
        "remaining_s": round(remaining) if remaining is not None else None,
        "cycle": s.get("cycle", 0),
        "resumable": state in ("STOPPED", "UNCLEAN", "COMPLETED")
                     and bool(s.get("checkpoint")),
        "stop_requested": STOP_FLAG.exists(),
        "allowed_hours": list(ALLOWED_HOURS),
        "smoke_minutes": list(SMOKE_MINUTES),
    }


# ───────────────────────────── start and stop ───────────────────────────────

def start(*, hours: float | None = None, minutes: float | None = None,
          resume: bool = False, mode: str = "observe",
          launcher: Any = None) -> dict:
    """Begin a session. Refuses while one is RUNNING; resumes from a checkpoint.

    `launcher` is a seam for tests: a callable taking the session dict and
    returning a pid. Production spawns `scripts.sim_run` detached, which is the
    only way a button-started job survives the request that started it.
    """
    cur = status()
    if cur["state"] in ("RUNNING", "STOPPING"):
        raise SimRefused(
            f"a simulation is already {cur['state']} (session "
            f"{cur['session'].get('id')}, cycle {cur.get('cycle')}). One session "
            f"owns the GPU and the broker lease; stop it before starting another.")

    if minutes is not None:
        if minutes not in SMOKE_MINUTES:
            raise SimRefused(f"smoke runs are {SMOKE_MINUTES} minutes, not {minutes}")
        duration_s = float(minutes) * 60
        kind = "smoke"
    else:
        h = hours if hours is not None else ALLOWED_HOURS[0]
        if h not in ALLOWED_HOURS:
            raise SimRefused(
                f"duration must be one of {ALLOWED_HOURS} hours, not {h}. An "
                f"arbitrary duration is how a quick test becomes an unattended "
                f"40-hour run.")
        duration_s = float(h) * 3600
        kind = "session"

    prior = cur["session"] if resume else None
    if resume:
        if not cur["resumable"]:
            raise SimRefused(
                f"nothing to resume: last state {cur['state']}, "
                f"checkpoint {'present' if (cur['session'] or {}).get('checkpoint') else 'ABSENT'}")
        if prior.get("mode") != mode:
            raise SimRefused(
                f"refusing to resume into a different configuration: the session "
                f"being resumed ran mode={prior.get('mode')!r}, this asks for "
                f"{mode!r}. That is a different experiment wearing its id.")

    STOP_FLAG.unlink(missing_ok=True)
    now = datetime.now(timezone.utc)
    session = {
        "id": (prior or {}).get("id") if resume else uuid.uuid4().hex[:12],
        "kind": kind,
        "mode": mode,
        "state": "RUNNING",
        "started": _now(),
        "planned_end": (now + timedelta(seconds=duration_s)).isoformat(timespec="seconds"),
        "duration_s": duration_s,
        "requested_hours": hours,
        "requested_minutes": minutes,
        "resumed_from": (prior or {}).get("checkpoint") if resume else None,
        "resume_count": ((prior or {}).get("resume_count", 0) + 1) if resume else 0,
        "cycle": (prior or {}).get("cycle", 0) if resume else 0,
        "checkpoint": (prior or {}).get("checkpoint") if resume else None,
        "cycles": [],
        "heartbeat": _now(),
        "pid": None,
        "read_me_first": (
            "A STOP finishes the current cycle, checkpoints, and exits. It never "
            "interrupts a unit of work. `state` UNCLEAN means the process "
            "vanished without a stop receipt -- the checkpoint is still good, "
            "the cycle after it is unknown."),
    }
    _atomic_write(SESSION_PATH, session)

    pid = (launcher or _spawn)(session)
    session["pid"] = pid
    _atomic_write(SESSION_PATH, session)
    logger.info("sim_session: started %s (%s) pid %s", session["id"], kind, pid)
    return session


def _spawn(session: dict) -> int:
    """Detached, so the session outlives the HTTP request that started it."""
    repo = Path(__file__).resolve().parents[2]
    log = STATE_DIR / f"sim_{session['id']}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    fh = log.open("a", encoding="utf-8")
    kwargs: dict[str, Any] = {}
    if os.name == "nt":
        kwargs["creationflags"] = (subprocess.CREATE_NEW_PROCESS_GROUP
                                   | getattr(subprocess, "DETACHED_PROCESS", 0))
    else:
        kwargs["start_new_session"] = True
    p = subprocess.Popen(
        [sys.executable, "-m", "scripts.sim_run", "--session", session["id"]],
        cwd=str(repo), stdout=fh, stderr=subprocess.STDOUT, text=True,
        env={**os.environ, "AEGIS_IGNORE_DOTENV": "0", "PYTHONIOENCODING": "utf-8"},
        **kwargs)
    return p.pid


def request_stop(*, reason: str = "button") -> dict:
    """Ask for a SAFE stop. Returns immediately; the loop stops at a boundary."""
    cur = status()
    if cur["state"] not in ("RUNNING", "STOPPING"):
        return {"ok": False, "state": cur["state"],
                "detail": f"nothing to stop: state is {cur['state']}"}
    STOP_FLAG.write_text(json.dumps({"requested": _now(), "reason": reason}),
                         encoding="utf-8")
    s = _read(SESSION_PATH) or {}
    s["state"] = "STOPPING"
    s["stop_requested"] = _now()
    s["stop_reason"] = reason
    _atomic_write(SESSION_PATH, s)
    return {"ok": True, "state": "STOPPING", "cycle": s.get("cycle"),
            "detail": (f"the current cycle will finish, checkpoint and exit. "
                       f"Grace is {STOP_GRACE_S}s; nothing is killed mid-unit.")}


# ────────────────────── what the runner calls, per cycle ────────────────────

def stop_requested() -> bool:
    return STOP_FLAG.exists()


def should_continue(session: dict) -> tuple[bool, str]:
    """The ONLY place the loop asks whether to run another cycle."""
    if stop_requested():
        return False, "stop requested"
    try:
        if datetime.now(timezone.utc) >= datetime.fromisoformat(session["planned_end"]):
            return False, "requested duration elapsed"
    except (KeyError, ValueError):
        return False, "session has no readable planned_end"
    return True, "within the session"


def heartbeat(cycle: int | None = None, note: str | None = None) -> None:
    s = _read(SESSION_PATH)
    if not s:
        return
    s["heartbeat"] = _now()
    if cycle is not None:
        s["cycle"] = cycle
    if note:
        s["note"] = note
    _atomic_write(SESSION_PATH, s)


def record_cycle(cycle: int, payload: dict) -> None:
    """Checkpoint at a UNIT BOUNDARY. This is the resume point."""
    s = _read(SESSION_PATH)
    if not s:
        return
    s["cycle"] = cycle
    s["heartbeat"] = _now()
    s["checkpoint"] = {"cycle": cycle, "at": _now(), **payload}
    s.setdefault("cycles", []).append({"cycle": cycle, "at": _now(),
                                       **{k: v for k, v in payload.items()
                                          if k in ("units", "elapsed_s", "errors")}})
    s["cycles"] = s["cycles"][-200:]
    _atomic_write(SESSION_PATH, s)


def finish(state: str, why: str, extra: dict | None = None) -> dict:
    """Write the stop receipt. Every exit path, once."""
    s = _read(SESSION_PATH) or {}
    s["state"] = state
    s["ended"] = _now()
    s["end_reason"] = why
    if extra:
        s.update(extra)
    _atomic_write(SESSION_PATH, s)
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({k: v for k, v in s.items() if k != "cycles"},
                            default=str) + "\n")
    STOP_FLAG.unlink(missing_ok=True)
    logger.info("sim_session: %s -- %s", state, why)
    return s


def history(limit: int = 20) -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    rows = [json.loads(l) for l in
            HISTORY_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    return rows[-limit:]
