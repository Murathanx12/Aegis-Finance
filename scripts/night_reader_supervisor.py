"""Keeps the reader working through the night with nobody watching
(2026-09-28, Murat: "make sure it works autonomous ... run the services we built
and in the morning we can analyze").

Every TICK: is the reader alive? If not, and the queue is not finished:

1. CLASSIFY why it exited, from the tail of its log (`gateway_repair.
   classify_exit`): READER_CRASH, a DEPENDENCY fault (GATEWAY_DOWN,
   GATEWAY_STUCK, CHROME_DOWN), NOT_MURATCLAW, a POLICY_STOP, or QUEUE_DONE.
2. PROBE the dependency (gateway port, the dedicated Chrome's port, the
   gateway's status of the dedicated profile). While it is down the reader is
   NOT relaunched -- last night it was relaunched 20 times in 100 minutes
   against a jammed gateway (handoff 2026-09-28 §5 R1, R2).
3. REPAIR it (`gateway_repair.repair`: launch the dedicated Chrome; `browser
   stop`; an orphaned chrome-devtools-mcp by PID; `gateway start`; `gateway
   restart`; wait for the port; one attach), at most
   `OPENCLAW_REPAIRS_PER_HOUR` per hour with exponential backoff. Every step is
   a receipt line.
4. Relaunch the reader only when the probe is healthy, with its own
   exponential backoff (a crash loop is not a night's work either).
   NOT_MURATCLAW and POLICY_STOP end the night: the first is never
   auto-repaired (it could mean attaching to the wrong browser), the second is
   a refusal the reader was right to make.

Every HOUR: claims -> three-source table -> source scorecard. At the end time:
stop the reader BY PID, run the three once more, exit. It never touches the
browser itself (only the repair module launches the DEDICATED Chrome), never
kills by image name, and stops on its own STOP file, a missing HANDOFF_PC, or a
disk below the floor. It never creates HANDOFF_PC.

    python -m scripts.night_reader_supervisor --until 08:00
    python -m scripts.night_reader_supervisor --until 08:00 --no-pool   # the old 3-worker queue

THE POOL (2026-09-28 21:45 HKT, Murat: "can openclaw read more, can it launch
another chrome tabs to read too, this one by one is very slow"): by default
(`config.READER_POOL_ENABLED`) the supervisor launches `scripts.reader_pool`
-- several tabs, paced per host, section fronts, stock pages, their news, media
and the social hosts -- instead of the rolling three-worker queue. CORRECTED
2026-09-29: the pool CAN run out of work (every name read inside its freshness
window, fronts not yet due); that morning it sat empty for 100+ minutes while
this supervisor called it STALLED and restarted it ~20 times. The pool now
refills itself (the browse lane: fronts revisited when a host's list runs low)
and names its state (READING / REFILLING / QUEUE_EMPTY / WAITING_FOR_CAP);
QUEUE_EMPTY and WAITING_FOR_CAP are healthy here, never a stall. Everything
else (classify, probe, repair, backoff, stop by PID) is unchanged. `reader_status.json` carries
the pool's own status (tab count and why, per-host pages an hour against the
caps, cooling hosts) and the hourly digest refreshes
`dowjones/reading_report_<day>.md`.
    python -m scripts.night_reader_supervisor --probe          # one probe, printed
    python -m scripts.night_reader_supervisor --repair-once    # probe + repair if faulted
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import gateway_repair as GR  # noqa: E402

from backend import config as _config  # noqa: E402

# the ledger root from config (not rebuilt from `__file__`): the same folder the
# reader and the throttle write to, in a source run and in a frozen build alike
DATA = Path(_config.OPTIMUS_LEDGER_DIR)
DJ = DATA / "dowjones"
LOG = DJ / "night_reader_supervisor.jsonl"
STOP = DJ / "SUPERVISOR_STOP"
HANDOFF = DATA / "HANDOFF_PC"
THROTTLE = DATA / "news_corpus" / "dowjones" / "_throttle.log"
#: 2026-09-28: one tick a minute (the STATUS file is refreshed every tick); a
#: `tick` line goes to the log every LOG_TICK_EVERY ticks.
TICK_S = 60
LOG_TICK_EVERY = 5
STATUS = DJ / "reader_status.json"
POOL_STATUS = DJ / "reader_pool_status.json"
POOL_CMD = DJ / "reader_pool_run.cmd"
PAGE_LOG = DJ / "page_log.jsonl"
#: a run that ended on the DAILY cap is retried this long after its launch
#: (the cap is a rolling 24 h window), not ended for the night
CAPS_RETRY_S = 1800.0
#: the next check when every name has been read today (a new UTC day re-opens them)
ALL_READ_RETRY_S = 1800.0
HOURLY_S = 3600
MAX_RESTARTS = 20
READER_BACKOFF_S = 60.0          # the reader's own relaunch backoff, doubling
READER_BACKOFF_MAX_S = 1800.0
#: READER_CANNOT_OPEN_TABS (2026-09-28): the reader ran and could not open a
#: single tab. Relaunching it every tick burns nothing useful, so these
#: relaunches have their own budget: at most OPEN_FAULT_PER_HOUR in any rolling
#: hour, the n-th waiting OPEN_FAULT_BACKOFF_S * 2**(n-1) after the previous one.
OPEN_FAULT = "READER_CANNOT_OPEN_TABS"
OPEN_FAULT_PER_HOUR = 3
OPEN_FAULT_BACKOFF_S = 300.0
DISK_FLOOR_GB = 20.0
PY = str(REPO / ".venv" / "Scripts" / "python.exe")


def log(**row: object) -> None:
    row = {"t": datetime.now().astimezone().isoformat(timespec="seconds"), **row}
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


#: the command lines that are OUR readers: the queue workers and the pool
READER_CMDLINE = "'scripts[.](dowjones_pull|reader_pool)'"


def pool_cmd_text(*, until: str, profile: str = "muratclaw", py: str | None = None,
                  day: str | None = None) -> str:
    """PURE. The launcher for the pool: same python, stdin and log shape as the
    queue launcher, so `queue_logs` and `classify_exit` read it the same way."""
    day = day or datetime.now().strftime("%Y-%m-%d")
    log = f"backend\\data\\optimus\\dowjones\\reader_pool_{day}.log"
    return ("@echo off\n"
            f"cd /d {REPO}\n"
            f"{py or PY} -m scripts.reader_pool --handoff --profile {profile} --until {until} "
            f"< backend\\data\\optimus\\empty_stdin.txt >> {log} 2>> {log}.err\n")


def pool_status(path: Path | None = None) -> dict | None:
    """The pool's own status file (tabs, hosts, caps, cooling), or None."""
    try:
        return json.loads((path or POOL_STATUS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def reader_pids() -> list[int]:
    """PIDs of OUR reader processes, matched on the command line (never on the
    image name). No psutil in this venv, so Windows is asked directly."""
    q = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object "
         "{ $_.CommandLine -match " + READER_CMDLINE + " } | ForEach-Object { $_.ProcessId }")
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


def queue_logs(queue_cmd: Path) -> list[Path]:
    """The files the queue command appends to (`>> path` / `2>> path`)."""
    try:
        txt = queue_cmd.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out = []
    for m in re.finditer(r"2?>>\s*(\S+)", txt):
        p = Path(m.group(1))
        out.append(p if p.is_absolute() else REPO / p)
    return out


def log_tail(paths: list[Path], n_bytes: int = 6000) -> str:
    parts = []
    for p in paths:
        try:
            with p.open("rb") as f:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - n_bytes))
                parts.append(f.read().decode("utf-8", "replace"))
        except OSError:
            continue
    return "\n".join(parts)


def reader_backoff_s(n: int) -> float:
    """PURE. The wait before the n-th reader relaunch (n >= 1)."""
    return min(READER_BACKOFF_MAX_S, READER_BACKOFF_S * (2 ** max(0, n - 1)))


def open_fault_budget() -> GR.RepairBudget:
    """The relaunch budget for READER_CANNOT_OPEN_TABS (same rolling-hour and
    doubling rules as the repair budget, its own numbers)."""
    return GR.RepairBudget(per_hour=OPEN_FAULT_PER_HOUR, backoff_s=OPEN_FAULT_BACKOFF_S)


def caps_reached(kind: str, evidence: str) -> bool:
    """PURE. The run ended on the daily page cap (a POLICY_STOP that is a wait,
    not a verdict)."""
    return kind == "POLICY_STOP" and "REFUSED_THROTTLE_DAY" in (evidence or "")


def page_counts(now: datetime, path: Path | None = None, max_lines: int = 4000) -> dict:
    """From the tail of `page_log.jsonl`: OK pages in the last 10 and 60 minutes,
    every class per host in the last 60, the last non-OK page, and the last url
    per worker."""
    p = path or PAGE_LOG
    out: dict = {"ok_10m": 0, "ok_60m": 0, "attempts_10m": 0, "classes_60m": {},
                 "last_not_ok": None, "current_url_by_worker": {}}
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]
    except OSError:
        return out
    now_utc = now.astimezone() if now.tzinfo else now.astimezone()
    for ln in lines:
        try:
            r = json.loads(ln)
            t = datetime.fromisoformat(r["t"])
        except (ValueError, KeyError, TypeError):
            continue
        age = (now_utc - t).total_seconds()
        cls, host = r.get("class") or "?", r.get("host") or "-"
        if age <= 600:
            out["attempts_10m"] = out.get("attempts_10m", 0) + 1
        if age <= 3600:
            row = out["classes_60m"].setdefault(host, {})
            row[cls] = row.get(cls, 0) + 1
            if cls == "OK":
                out["ok_60m"] += 1
                if age <= 600:
                    out["ok_10m"] += 1
        if cls != "OK":
            out["last_not_ok"] = {"t": r.get("t"), "class": cls, "url": r.get("url")}
        out["current_url_by_worker"][r.get("worker") or "-"] = r.get("url")
    return out


def write_status(state: str, *, next_action: str, last_error: str | None = None,
                 extra: dict | None = None, path: Path | None = None,
                 now: datetime | None = None) -> dict:
    """`reader_status.json`: one small object, rewritten every tick (Telegram's
    `report` can read it)."""
    now = now or datetime.now().astimezone()
    pc = page_counts(now)
    row = {"t": now.isoformat(timespec="seconds"), "state": state,
           "current_url_by_worker": pc["current_url_by_worker"],
           "pages_ok_10m": pc["ok_10m"], "pages_ok_60m": pc["ok_60m"],
           "classes_60m": pc["classes_60m"], "last_not_ok_page": pc["last_not_ok"],
           "last_error": (last_error or "")[:300] or None, "next_action": next_action,
           **(extra or {})}
    try:
        GR_atomic_json(path or STATUS, row)
    except OSError:
        pass
    return row


def GR_atomic_json(path: Path, obj: dict) -> None:
    from backend.services import disk_guard as DG
    DG.atomic_write_json(path, obj)


def rolling_queue(template_cmd: Path, *, day: str | None = None,
                  names: list[str] | None = None) -> dict:
    """Build the next queue from the candidate set (oldest newest-read first) and
    a launcher for it modelled on `template_cmd` (same python, stdin and log
    files; only the queue file changes). Returns `{cmd, queue, n_names,
    n_unread_today}`."""
    from scripts import dowjones_pull as DP
    day = day or DP._today()
    names = DP.rolling_names() if names is None else names
    last = DP.last_read_days(names)
    q = DJ / f"QUEUE_rolling_{day}.txt"
    text = DP.build_rolling_queue_text(names, last, day=day)
    old = q.read_text(encoding="utf-8") if q.exists() else None
    if old != text:
        GR_atomic_text(q, text)
        dd = DP.queue_done_dir(q)            # a rebuilt queue is a new queue
        if dd.exists():
            for f in dd.glob("*.done"):
                f.unlink()
    tpl = template_cmd.read_text(encoding="utf-8", errors="replace")
    cmd_text = re.sub(r"--queue\s+\S+", "--queue " + str(q).replace("\\", "\\\\"), tpl)
    cmd = DJ / "queue_run_rolling.cmd"
    GR_atomic_text(cmd, cmd_text)
    unread = sum(1 for n in names if (last.get(n) or "") < day)
    return {"cmd": cmd, "queue": q, "n_names": len(names), "n_unread_today": unread}


def GR_atomic_text(path: Path, text: str) -> None:
    from backend.services import disk_guard as DG
    DG.atomic_write_text(path, text)


def _exhausted(q: Path) -> bool:
    from scripts import dowjones_pull as DP
    try:
        return DP.queue_exhausted(q)
    except OSError:
        return False


def queue_of(cmd: Path) -> Path | None:
    try:
        m = re.search(r"--queue\s+(\S+)", cmd.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    if not m:
        return None
    q = Path(m.group(1))
    return q if q.is_absolute() else REPO / q


def decide(*, kind: str, probe: dict, restarts: int, since_launch_s: float | None,
           budget_ok: bool, open_fault_ok: bool = True) -> str:
    """PURE. What the supervisor does this tick when the reader is NOT alive:

    * "stop"      -- NOT_MURATCLAW / POLICY_STOP / QUEUE_DONE, or out of restarts;
    * "repair"    -- the dependency is down and the repair budget allows;
    * "wait_dep"  -- the dependency is down and the budget does not allow yet
                     (the reader is NOT relaunched while it is down);
    * "wait"      -- the reader's own backoff has not elapsed;
    * "wait_open_fault" -- the last exit was READER_CANNOT_OPEN_TABS and its
                     own budget (<= 3 per hour, doubling from 5 min) says not yet;
    * "relaunch"  -- healthy dependency, backoff elapsed."""
    if kind in ("NOT_MURATCLAW", "POLICY_STOP", "QUEUE_DONE"):
        return "stop"
    if not probe.get("healthy"):
        return "repair" if budget_ok else "wait_dep"
    if restarts >= MAX_RESTARTS:
        return "stop"
    if kind == OPEN_FAULT and not open_fault_ok:
        return "wait_open_fault"
    if since_launch_s is not None and restarts > 0 \
            and since_launch_s < reader_backoff_s(restarts):
        return "wait"
    return "relaunch"


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
    step("reading_report", ["backend.services.reader_report"], 300)


def end_time(hhmm: str) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    now = datetime.now()
    end = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return end if end > now else end + timedelta(days=1)


def repair_once(budget: GR.RepairBudget | None = None, *, deps: GR.Deps | None = None) -> dict:
    """Probe; if faulted and the budget allows, repair. One receipt line each."""
    pr = GR.probe(deps)
    log(event="probe", **pr)
    if pr["healthy"]:
        return {"probe": pr, "repair": None}
    b = budget or GR.RepairBudget()
    ok, wait = b.allow(time.monotonic())
    if not ok:
        log(event="repair_deferred", fault=pr.get("fault"), wait_s=round(wait, 1))
        return {"probe": pr, "repair": None, "deferred_s": round(wait, 1)}
    b.spend(time.monotonic())
    res = GR.repair(pr.get("fault") or "GATEWAY_DOWN", deps=deps, log=log)
    log(event="repair", fault=res["fault"], healthy=res["healthy"],
        cleared_by=res["cleared_by"], seconds=res.get("seconds"),
        steps=[s["step"] for s in res["steps"]])
    return {"probe": pr, "repair": res}


# ── the reader's REAL state, and what a stall triggers (2026-09-29) ──────────
#
# 00:59-02:15 HKT the status file said "reading" for 75 minutes while every page
# came back BLANK: `state` was set from "is a reader process alive", never from
# pages. A hung tab in the dedicated Chrome made every Playwright attach time
# out (the gateway's own log, 343 lines), the gateway probe stayed green, and
# nothing looked at pages OK. So the state is now DERIVED from pages OK and the
# workers, and a stall is a named fault with an escalating, bounded remedy.

READING, WAITING_FOR_CAP, REPAIRING, STALLED, DOWN, STARTING = (
    "READING", "WAITING_FOR_CAP", "REPAIRING", "STALLED", "DOWN", "STARTING")
#: 2026-09-29: the pool's own queue states (reader_scheduler.Q_*)
QUEUE_EMPTY, REFILLING = "QUEUE_EMPTY", "REFILLING"
#: a pool status older than this is not trusted for its queue state
POOL_STATUS_FRESH_S = 180.0
STALL_LADDER_FILE = DJ / "stall_ladder.json"
#: 2026-09-29: the Chrome recycle's refusal, backoff and hourly count, kept
#: across supervisor restarts (see `recycle_gate`)
RECYCLE_STATE_FILE = DJ / "chrome_recycle_state.json"
POOL_STOP = DJ / "READER_POOL_STOP"
#: the stall ladder: 1 close hung tabs (+ repair a faulted gateway), 2 restart
#: the pool, 3 recycle the dedicated Chrome and restart the pool
STALL_LADDER = ("close_hung_tabs", "restart_pool", "recycle_chrome")


def stall_s() -> float:
    return float(getattr(_config, "READER_STALL_S", 600.0))


def stall_step_s() -> float:
    return float(getattr(_config, "READER_STALL_STEP_S", 300.0))


def last_ok_age_s(now: datetime, path: Path | None = None, max_lines: int = 4000
                  ) -> float | None:
    """Seconds since the newest OK page in `page_log.jsonl`, or None."""
    p = path or PAGE_LOG
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]
    except OSError:
        return None
    for ln in reversed(lines):
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if r.get("class") == "OK":
            try:
                return max(0.0, (now.astimezone() - datetime.fromisoformat(r["t"])
                                 ).total_seconds())
            except (KeyError, ValueError, TypeError):
                return None
    return None


def derive_state(*, alive: bool, repairing: bool, ok_10m: int, last_ok_age: float | None,
                 since_launch_s: float | None, next_slot_in_s: float | None,
                 attempts_10m: int, stall_after_s: float | None = None,
                 pool_state: str | None = None) -> str:
    """PURE. The reader's state from what it DID, not from whether a process
    exists:

    * REPAIRING        -- the supervisor is repairing a dependency now;
    * DOWN             -- no reader process;
    * READING          -- at least one page OK in the last 10 minutes;
    * WAITING_FOR_CAP  -- alive, nothing attempted in 10 min, and the next
                          reserved open is more than a minute ahead (a cap);
    * QUEUE_EMPTY      -- alive, nothing attempted in 10 min, and the POOL says
                          its list is empty with caps free (2026-09-29): it is
                          waiting for its next front revisit, not stalled;
    * REFILLING        -- the pool says a front is due and is being queued;
    * STARTING         -- alive, launched less than the stall window ago;
    * STALLED          -- alive, no page OK for the stall window while there
                          was work to do (a fault the supervisor acts on).
    `pool_state` is the pool's own `queue_state` (None: not in pool mode, or
    its status file is stale)."""
    s = stall_s() if stall_after_s is None else stall_after_s
    if repairing:
        return REPAIRING
    if not alive:
        return DOWN
    if ok_10m > 0:
        return READING
    if attempts_10m == 0 and pool_state in (QUEUE_EMPTY, WAITING_FOR_CAP):
        return pool_state
    if attempts_10m == 0 and next_slot_in_s is not None and next_slot_in_s > 60:
        return WAITING_FOR_CAP
    fresh = since_launch_s is not None and since_launch_s < s
    ok_recent = last_ok_age is not None and last_ok_age < s
    if fresh or ok_recent:
        if pool_state == REFILLING:
            return REFILLING
        return STARTING if fresh else READING
    return STALLED


def pool_state_of(pst: dict | None, now: datetime | None = None) -> str | None:
    """The pool's `queue_state` from its status file, or None when there is no
    status or it is older than POOL_STATUS_FRESH_S (a dead writer's last word
    is not the pool's state)."""
    if not pst or not pst.get("queue_state"):
        return None
    try:
        t = datetime.fromisoformat(str(pst.get("t")))
        now = now or datetime.now().astimezone()
        if (now.astimezone() - t).total_seconds() > POOL_STATUS_FRESH_S:
            return None
    except (TypeError, ValueError):
        return None
    return str(pst["queue_state"])


def next_action_for(state: str, pst: dict | None = None) -> str:
    """PURE. The words beside a state (never "keep reading" beside a stall)."""
    nxt = (pst or {}).get("next_front_due_s")
    if state == READING:
        return "keep reading"
    if state == QUEUE_EMPTY:
        return ("queue empty, caps free: revisit the fronts in "
                f"{nxt:.0f} s" if isinstance(nxt, (int, float)) else
                "queue empty, caps free: revisit the fronts when due")
    if state == REFILLING:
        return "refilling the list from the section fronts"
    if state == WAITING_FOR_CAP:
        return "wait for the hourly / daily cap window (or a cooling host)"
    if state == STARTING:
        return "starting: first pages"
    return "see the stall ladder"


def load_ladder(path: Path | None = None, now: float | None = None) -> dict:
    """The stall ladder as the last supervisor left it (level, last action
    time), if written in the last hour; else level 0."""
    try:
        d = json.loads((path or STALL_LADDER_FILE).read_text(encoding="utf-8"))
        if (now or time.time()) - float(d.get("saved", 0)) <= 3600:
            return {"level": int(d.get("level", 0)), "last_act": float(d.get("last_act", 0.0))}
    except (OSError, ValueError, TypeError):
        pass
    return {"level": 0, "last_act": 0.0}


def save_ladder(level: int, last_act: float, path: Path | None = None) -> None:
    try:
        GR_atomic_json(path or STALL_LADDER_FILE, {"level": int(level),
                                                   "last_act": float(last_act),
                                                   "saved": time.time()})
    except OSError:
        pass


# ── the Chrome recycle is decided before anything is stopped (2026-09-29) ────
#
# Measured in night_reader_supervisor.jsonl, 11:12-12:00 HKT: four supervisors
# (each restarted by a STOP file about every 15 minutes) each found a recycle
# due on their first memory check, 5-6 minutes in (MEMORY_PRESSURE twice, AGE
# twice), because the hourly recycle budget and the last refusal lived only in
# the process. Each STOPPED the pool first; the recycle was then refused
# (OWNER_MAY_BE_USING twice, the instance not proven once) and the pool was
# relaunched for nothing. Now: the refusal is checked first, with no side
# effect; a refusal leaves the pool reading and is not asked again until its
# backoff (persisted) runs out; the recycle count per hour is persisted too.

def load_recycle_state(path: Path | None = None) -> dict:
    try:
        d = json.loads((path or RECYCLE_STATE_FILE).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_recycle_state(st: dict, path: Path | None = None) -> None:
    try:
        GR_atomic_json(path or RECYCLE_STATE_FILE, st)
    except OSError:
        pass


#: tab ids the reader opened, remembered across pool and supervisor restarts
READER_TABS_KEEP = 2000


def remember_reader_tabs(pst: dict | None, state: dict) -> dict:
    """Merge every tab id the pool status names as the reader's (open,
    opened this run, orphaned) into `state["reader_tab_ids"]` (oldest dropped
    past READER_TABS_KEEP). A tab the reader opened stays the reader's after
    the process that opened it is gone: at 12:19 HKT on 2026-09-29 two of the
    pool's own search tabs, left open by its stop, refused the recycle as
    somebody else's."""
    st = dict(state or {})
    p = pst or {}
    ids = [*(st.get("reader_tab_ids") or []), *(p.get("reader_tab_ids") or []),
           *(p.get("open_tab_ids") or []), *(p.get("orphaned_tabs") or [])]
    st["reader_tab_ids"] = list(dict.fromkeys(str(t) for t in ids if t))[-READER_TABS_KEEP:]
    return st


def refused_backoff_s(n: int) -> float:
    """The wait after the n-th consecutive refusal (n >= 1): doubling, capped."""
    base = float(getattr(_config, "READER_CHROME_REFUSED_BACKOFF_S", 900.0))
    cap = float(getattr(_config, "READER_CHROME_REFUSED_BACKOFF_MAX_S", 7200.0))
    return min(cap, base * (2 ** max(0, int(n) - 1)))


def _refusal_kind(refused: str | None) -> str:
    return str(refused or "").split(":", 1)[0].strip() or "UNKNOWN"


def recycle_gate(why: str, *, now: float, preflight, state: dict,
                 per_hour: int | None = None) -> dict:
    """Decide a due recycle WITHOUT stopping anything. Returns
    `{"go": bool, "reason": ..., "wait_s": ..., "log": row-or-None, "state": new}`:

    * inside a refusal backoff -> go False, silently (no re-ask each tick);
    * the hourly recycle count reached -> go False, silently;
    * `preflight()` refuses -> go False; the refusal is recorded with a
      doubling backoff and logged only when it is new (a new kind of refusal);
    * otherwise go True (the caller stops the pool, then recycles).

    `preflight` is a zero-argument call returning `GR.recycle_preflight`'s
    dict. `state` is `load_recycle_state()`; the caller saves `out["state"]`."""
    st = dict(state or {})
    ph = int(per_hour if per_hour is not None
             else getattr(_config, "READER_CHROME_RECYCLES_PER_HOUR", 2))
    stamps = [float(t) for t in (st.get("recycled_at") or []) if now - float(t) < 3600.0]
    st["recycled_at"] = stamps
    retry = float(st.get("retry_after") or 0.0)
    if retry > now:
        return {"go": False, "reason": "refusal_backoff", "wait_s": round(retry - now),
                "log": None, "state": st}
    if len(stamps) >= ph:
        return {"go": False, "reason": "hourly_budget",
                "wait_s": round(stamps[0] + 3600.0 - now), "log": None, "state": st}
    pre = preflight() or {}
    if not pre.get("ok"):
        n = int(st.get("n_refused") or 0) + 1
        kind = _refusal_kind(pre.get("refused"))
        new_episode = kind != st.get("refused_kind")
        wait = refused_backoff_s(n)
        st.update(n_refused=n, refused_kind=kind, refused=str(pre.get("refused"))[:300],
                  refused_at=now, retry_after=now + wait, refused_why=why,
                  active_foreign=pre.get("active_foreign") or [])
        return {"go": False, "reason": "refused", "wait_s": round(wait),
                "log": ({"event": "chrome_recycle_refused", "why": why,
                         "refused": st["refused"], "active_foreign": st["active_foreign"],
                         "n_refused": n, "retry_in_s": round(wait),
                         "pool": "kept reading (not stopped)"} if new_episode else None),
                "state": st}
    log_row = None
    if st.get("n_refused"):
        log_row = {"event": "chrome_recycle_refusal_cleared", "was": st.get("refused"),
                   "n_refused": st.get("n_refused")}
    for k in ("n_refused", "refused_kind", "refused", "refused_at", "retry_after",
              "refused_why", "active_foreign"):
        st.pop(k, None)
    return {"go": True, "reason": "ok", "wait_s": 0, "log": log_row, "state": st}


def record_recycle_result(state: dict, rec: dict, *, why: str, now: float) -> dict:
    """After a recycle ran (the pool was stopped): count it for the hourly
    budget; a late refusal (the pages changed between the preflight and the
    recycle) starts a backoff like any other."""
    st = dict(state or {})
    st["recycled_at"] = [float(t) for t in (st.get("recycled_at") or [])
                         if now - float(t) < 3600.0] + [now]
    if rec.get("ok"):
        st["last_ok_at"] = now
    elif rec.get("refused"):
        n = int(st.get("n_refused") or 0) + 1
        st.update(n_refused=n, refused_kind=_refusal_kind(rec.get("refused")),
                  refused=str(rec.get("refused"))[:300], refused_at=now,
                  retry_after=now + refused_backoff_s(n), refused_why=why,
                  active_foreign=rec.get("active_foreign") or [])
    return st


def attempts_10m(pc: dict) -> int:
    """Pages of ANY class in the last 10 minutes is not in `page_counts`; the
    60-minute classes are, so this counts the recent tail directly."""
    return int(pc.get("attempts_10m") or 0)


def stall_action(level: int) -> str | None:
    """PURE. The ladder step for the n-th action of one stall episode (0-based);
    past the last step the ladder starts again at `restart_pool`."""
    if level < len(STALL_LADDER):
        return STALL_LADDER[level]
    return STALL_LADDER[1 + (level - len(STALL_LADDER)) % (len(STALL_LADDER) - 1)]


def stop_pool_gracefully(*, wait_s: float = 180.0, pids_fn=None, kill_fn=None,
                         sleep_fn=time.sleep, clock=time.monotonic,
                         status_fn=None, close_fn=None) -> dict:
    """Ask the pool to stop (its own STOP file: its threads finish the page in
    hand and it closes its tabs), wait up to `wait_s`, then end it BY PID. The
    tabs it named as open are closed afterwards either way. Removes the STOP
    file. Never kills by image name."""
    pids_fn = pids_fn or reader_pids
    kill_fn = kill_fn or kill_pid
    status_fn = status_fn or pool_status
    out: dict = {"stopped_gracefully": False, "killed": [], "closed_tabs": []}
    st = status_fn() or {}
    tabs = list(st.get("open_tab_ids") or [])
    try:
        POOL_STOP.write_text("stop for a repair or a recycle\n", encoding="utf-8")
    except OSError:
        pass
    t0 = clock()
    while pids_fn() and clock() - t0 < wait_s:
        sleep_fn(3.0)
    left = pids_fn()
    out["stopped_gracefully"] = not left
    for pid in left:
        if kill_fn(pid):
            out["killed"].append(pid)
    try:
        POOL_STOP.unlink()
    except OSError:
        pass
    st2 = status_fn() or {}
    tabs = list(dict.fromkeys(tabs + list(st2.get("open_tab_ids") or [])))
    if tabs:
        close = close_fn or _close_listed_tabs
        out["closed_tabs"] = close(tabs)
    out["seconds"] = round(clock() - t0, 1)
    return out


def _close_listed_tabs(ids: list[str]) -> list[str]:
    """Close the listed tabs on the PROVEN dedicated Chrome (those still there)."""
    try:
        GR._prove_dedicated()
        present = {str(t.get("id")) for t in GR._page_targets()}
    except Exception:  # noqa: BLE001 -- nothing proven, nothing closed
        return []
    done = []
    for t in ids:
        if t in present:
            try:
                if GR._close_target(t):
                    done.append(t)
            except Exception:  # noqa: BLE001
                pass
    return done


def chrome_age_s(now: datetime | None = None) -> float | None:
    """Seconds since the proven dedicated Chrome's browser process started."""
    try:
        from backend.services import muratclaw_instance as MI
        created = MI.prove().get("created")
        t = datetime.fromisoformat(str(created))
    except Exception:  # noqa: BLE001
        return None
    now = now or datetime.now().astimezone()
    return max(0.0, (now - t.astimezone()).total_seconds())


def free_ram_gb() -> float | None:
    try:
        return GR._free_gb()
    except Exception:  # noqa: BLE001
        return None


def write_machine_record(row: dict) -> None:
    """This machine's numbers (memory, tabs, Chrome size) go under local_pc/,
    which git ignores; never into docs/."""
    p = DATA / "local_pc" / "reader_machine.jsonl"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"t": datetime.now().astimezone().isoformat(timespec="seconds"),
                                **row}, default=str) + "\n")
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--until", default="08:00", help="local HH:MM")
    ap.add_argument("--queue-cmd", default=str(DJ / "queue_run.cmd"))
    ap.add_argument("--claims-since", default="2026-07-01")
    ap.add_argument("--no-rolling", dest="rolling", action="store_false",
                    help="run --queue-cmd as given instead of the self-built rolling queue")
    ap.add_argument("--pool", dest="pool", action="store_true",
                    default=bool(getattr(_config, "READER_POOL_ENABLED", False)),
                    help="launch the multi-tab reader pool (default from config)")
    ap.add_argument("--no-pool", dest="pool", action="store_false")
    ap.add_argument("--probe", action="store_true", help="print one dependency probe and exit")
    ap.add_argument("--repair-once", action="store_true",
                    help="probe, repair if faulted (bounded), print, exit")
    a = ap.parse_args(argv)
    if a.probe:
        print(json.dumps(GR.probe(), indent=1, default=str))
        return 0
    if a.repair_once:
        out = repair_once()
        print(json.dumps(out, indent=1, default=str))
        return 0 if (out["probe"]["healthy"] or (out["repair"] or {}).get("healthy")) else 2
    end = end_time(a.until)
    log(event="start", pid=os.getpid(), until=end.isoformat(timespec="minutes"))
    budget = GR.RepairBudget()
    open_budget = open_fault_budget()
    restarts, finished, last_launch, last_hourly, last_loads = 0, False, 0.0, time.time(), loads()
    template = Path(a.queue_cmd)
    # 2026-09-28: the supervisor builds its OWN queue (never idle): the plan over
    # the candidate set, oldest-read names first, rebuilt when it is exhausted
    if a.pool:
        a.rolling = False
        GR_atomic_text(POOL_CMD, pool_cmd_text(until=a.until))
        log(event="pool_mode", cmd=str(POOL_CMD))
    rq = rolling_queue(template) if a.rolling else None
    queue_cmd = POOL_CMD if a.pool else (rq["cmd"] if rq else template)
    if rq:
        log(event="rolling_queue", queue=str(rq["queue"]), n_names=rq["n_names"],
            n_unread_today=rq["n_unread_today"])
    logs = queue_logs(queue_cmd)
    why = "end time"
    ticks, state, next_action, last_err = 0, STARTING, "launch the reader", None
    idle_until = 0.0
    # 2026-09-29: the stall ladder and the scheduled Chrome recycle
    _lad = load_ladder()
    stall_level, last_stall_act, detail = _lad["level"], _lad["last_act"], ""
    #: review 2026-09-29 F2: stall restarts / recycles are bounded per hour
    stall_budget = GR.RepairBudget(
        per_hour=int(getattr(_config, "READER_STALL_RESTARTS_PER_HOUR", 3)),
        backoff_s=float(getattr(_config, "READER_STALL_RESTART_BACKOFF_S", 300.0)))
    stall_restarts = 0

    def relaunch_now(why_: str) -> None:
        nonlocal last_launch
        last_launch = time.time()
        log(event="relaunch", why=why_, launcher_pid=launch(queue_cmd),
            queue_cmd=str(queue_cmd))

    def _own_tabs() -> list[str]:
        """The pool's open tabs plus every tab the reader is known to have
        opened (persisted), so a tab it left behind is never 'foreign'."""
        st_ = remember_reader_tabs(pool_status(), load_recycle_state())
        save_recycle_state(st_)
        return list(st_["reader_tab_ids"])

    def recycle_and_relaunch(why_: str) -> dict:
        """Decide first (no side effect), THEN stop the pool and recycle.
        Returns `{"skipped": True, ...}` without touching the pool when the
        recycle would be refused, is in its backoff, or is over its hour."""
        tabs = _own_tabs()
        gate = recycle_gate(
            why_, now=time.time(), state=load_recycle_state(),
            preflight=lambda: GR.recycle_preflight(tabs, own_again=_own_tabs,
                                                   settle_s=20.0))
        save_recycle_state(gate["state"])
        if gate["log"]:
            log(**gate["log"])
        if not gate["go"]:
            return {"skipped": True, "reason": gate["reason"], "wait_s": gate["wait_s"]}
        tabs = _own_tabs() or tabs
        write_status(REPAIRING, next_action="recycle the dedicated Chrome: " + why_,
                     last_error=last_err)
        stopped_ = stop_pool_gracefully()
        log(event="pool_stopped", why=why_, **stopped_)
        # re-read after the stop: the pool's final status names every tab it
        # opened, including one it opened while stopping
        tabs = list(dict.fromkeys([*tabs, *_own_tabs()]))
        rec = GR.recycle_dedicated_chrome(tabs, why=why_)
        log(event="chrome_recycle", **rec)
        save_recycle_state(record_recycle_result(load_recycle_state(), rec, why=why_,
                                                 now=time.time()))
        pr_ = GR.probe()
        if not pr_["healthy"]:
            res_ = GR.repair(pr_.get("fault") or "PROFILE_DETACHED", log=log)
            log(event="repair", fault=res_["fault"], healthy=res_["healthy"],
                cleared_by=res_["cleared_by"], steps=[x["step"] for x in res_["steps"]])
        relaunch_now(f"after chrome recycle: {why_}")
        return rec
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
        if ticks % LOG_TICK_EVERY == 0:
            log(event="tick", reader_procs=len(pids), page_loads_total=n,
                new_loads=n - last_loads, free_gb=round(free, 1), restarts=restarts)
            last_loads = n
        ticks += 1
        if pids:
            now_dt = datetime.now().astimezone()
            pc = page_counts(now_dt)
            pst = pool_status() if a.pool else None
            ok_age = last_ok_age_s(now_dt)
            state = derive_state(
                alive=True, repairing=False, ok_10m=pc["ok_10m"], last_ok_age=ok_age,
                since_launch_s=(time.time() - last_launch) if last_launch else None,
                next_slot_in_s=(pst or {}).get("next_slot_in_s"),
                attempts_10m=pc["attempts_10m"], pool_state=pool_state_of(pst, now_dt))
            next_action = next_action_for(state, pst)
            if pc["ok_10m"] > 0 and stall_level:
                # the ladder resets only after an OK page (review F2), never
                # because a restart made the next ten minutes read STARTING
                stall_level = 0
                save_ladder(0, last_stall_act)
            if state in (READING, QUEUE_EMPTY, REFILLING, WAITING_FOR_CAP) and last_err:
                log(event="error_cleared", state=state, was=last_err)
                last_err = None
            act = stall_action(stall_level) if state == STALLED else None
            if act in ("restart_pool", "recycle_chrome") and \
                    time.time() - last_stall_act >= stall_step_s():
                ok_s, wait_s = stall_budget.allow(time.monotonic())
                if not ok_s:
                    if ticks % LOG_TICK_EVERY == 0:
                        log(event="stall_restart_deferred", level=stall_level, action=act,
                            wait_s=round(wait_s, 1))
                    next_action = f"stalled: {act} deferred {wait_s:.0f} s (hourly budget)"
                    act = None
            if state == STALLED and act and time.time() - last_stall_act >= stall_step_s():
                if act in ("restart_pool", "recycle_chrome"):
                    stall_budget.spend(time.monotonic())
                    stall_restarts += 1
                stall_level += 1
                last_stall_act = time.time()
                save_ladder(stall_level, last_stall_act)
                last_err = (f"STALLED: no page OK for {ok_age or 0:.0f} s with the reader "
                            f"alive ({pc['attempts_10m']} attempts in 10 min)")
                log(event="stall", level=stall_level, action=act, last_ok_age_s=ok_age,
                    attempts_10m=pc["attempts_10m"], stall_restarts=stall_restarts)
                write_status(REPAIRING, next_action=act, last_error=last_err)
                if act == "close_hung_tabs":
                    log(event="stall_close_hung_tabs", **GR.close_hung_tabs(log=log))
                    pr = GR.probe()
                    ok_b, _w = budget.allow(time.monotonic())
                    if not pr["healthy"] and ok_b:
                        budget.spend(time.monotonic())
                        res = GR.repair(pr.get("fault") or "GATEWAY_DOWN", log=log)
                        log(event="repair", fault=res["fault"], healthy=res["healthy"],
                            cleared_by=res["cleared_by"],
                            steps=[x["step"] for x in res["steps"]])
                elif act == "restart_pool":
                    log(event="pool_stopped", why="stall", **stop_pool_gracefully())
                    relaunch_now("stall: restart the pool")
                else:
                    rec_s = recycle_and_relaunch("stall: " + last_err)
                    if rec_s.get("skipped"):
                        # the recycle would be refused / is backing off: the
                        # stalled pool is still restarted (the ladder's step 2)
                        act = "restart_pool"
                        log(event="pool_stopped",
                            why=f"stall (recycle skipped: {rec_s.get('reason')})",
                            **stop_pool_gracefully())
                        relaunch_now("stall: restart the pool")
                state, next_action = REPAIRING, act
            elif a.pool and ticks % LOG_TICK_EVERY == 1:
                save_recycle_state(remember_reader_tabs(pst, load_recycle_state()))
                stale = GR.close_stale_tabs(keep_ids=list((pst or {}).get("open_tab_ids") or []))
                if stale.get("closed"):
                    log(event="stale_tabs_closed", closed=stale["closed"])
                age = chrome_age_s()
                try:
                    mem = GR._chrome_memory()
                except Exception:  # noqa: BLE001
                    mem = {}
                ram = free_ram_gb()
                try:
                    total = GR._total_gb()
                except Exception:  # noqa: BLE001 -- unknown: the share test is skipped
                    total = None
                why_r = GR.chrome_recycle_due(age_s=age, mem_gb=mem.get("total_gb"),
                                              free_gb=ram, total_gb=total)
                rec_r = recycle_and_relaunch(why_r) if why_r else None
                write_machine_record({"free_ram_gb": ram, "total_ram_gb": total, "chrome": mem,
                                      "chrome_age_s": age, "state": state,
                                      "tabs": (pst or {}).get("tabs"),
                                      "recycle_due": why_r,
                                      "recycle": (None if rec_r is None else
                                                  {k: rec_r.get(k) for k in
                                                   ("skipped", "reason", "wait_s", "ok",
                                                    "refused")})})
                if rec_r is not None and not rec_r.get("skipped"):
                    state, next_action = STARTING, "recycled the dedicated Chrome: " + why_r
        if free < DISK_FLOOR_GB:
            why = f"disk {free:.1f} GB under the {DISK_FLOOR_GB} GB floor"
            break
        if not pids and not finished and time.time() < idle_until:
            pass                                   # idle by rule; the status says why
        elif not pids and not finished:
            cls = GR.classify_exit(log_tail(logs)) if last_launch else {"kind": "NOT_STARTED",
                                                                        "evidence": ""}
            qf = queue_of(queue_cmd)
            if a.rolling and last_launch and (cls["kind"] == "QUEUE_DONE" or
                                              (qf is not None and qf.exists() and
                                               _exhausted(qf))):
                rq = rolling_queue(template)
                queue_cmd, logs = rq["cmd"], queue_logs(rq["cmd"])
                log(event="rolling_queue", queue=str(rq["queue"]), n_names=rq["n_names"],
                    n_unread_today=rq["n_unread_today"])
                if rq["n_unread_today"] == 0:
                    idle_until = time.time() + ALL_READ_RETRY_S
                    state, detail, next_action = (WAITING_FOR_CAP, "idle_all_read_today",
                                          f"rebuild the queue in {ALL_READ_RETRY_S/60:.0f} min")
                    write_status(state, next_action=next_action, last_error=last_err)
                    time.sleep(TICK_S)
                    continue
                cls = {"kind": "NOT_STARTED", "evidence": "rolling queue rebuilt"}
            if caps_reached(cls["kind"], cls["evidence"]):
                idle_until = last_launch + CAPS_RETRY_S
                state, detail, next_action = (WAITING_FOR_CAP, "idle_daily_cap",
                                      f"retry at {datetime.fromtimestamp(idle_until):%H:%M}")
                last_err = cls["evidence"]
                log(event="reader_down", exit_kind=cls["kind"], evidence=cls["evidence"],
                    action="wait_caps")
                write_status(state, next_action=next_action, last_error=last_err)
                time.sleep(TICK_S)
                continue
            pr = GR.probe()
            ok_budget, wait = budget.allow(time.monotonic())
            ok_open, open_wait = open_budget.allow(time.monotonic())
            act = decide(kind=cls["kind"], probe=pr, restarts=restarts,
                         since_launch_s=(time.time() - last_launch) if last_launch else None,
                         budget_ok=ok_budget, open_fault_ok=ok_open)
            log(event="reader_down", exit_kind=cls["kind"], evidence=cls["evidence"],
                probe_fault=pr.get("fault"), healthy=pr.get("healthy"), action=act,
                repair_wait_s=round(wait, 1),
                open_fault_wait_s=round(open_wait, 1) if cls["kind"] == OPEN_FAULT else None)
            if cls["kind"] not in ("NOT_STARTED",):
                last_err = f"{cls['kind']}: {cls['evidence']}"[:300]
            detail = {"stop": "stopped", "repair": "repairing", "wait_dep": "dependency_down",
                      "wait": "backoff", "wait_open_fault": "backoff_open_fault",
                      "relaunch": "relaunching"}.get(act, act)
            state = {"repair": REPAIRING, "relaunch": STARTING}.get(act, DOWN)
            next_action = act
            if act == "stop":
                finished = True
                log(event="stopped_relaunching", exit_kind=cls["kind"], restarts=restarts)
            elif act == "repair":
                budget.spend(time.monotonic())
                res = GR.repair(pr.get("fault") or "GATEWAY_DOWN", log=log)
                log(event="repair", fault=res["fault"], healthy=res["healthy"],
                    cleared_by=res["cleared_by"], seconds=res.get("seconds"),
                    steps=[s["step"] for s in res["steps"]])
            elif act == "relaunch":
                if cls["kind"] == OPEN_FAULT:
                    open_budget.spend(time.monotonic())
                restarts += 1
                last_launch = time.time()
                log(event="relaunch", n=restarts, launcher_pid=launch(queue_cmd),
                    queue_cmd=str(queue_cmd))
        if time.time() - last_hourly >= HOURLY_S:
            last_hourly = time.time()
            digest(a.claims_since)
        write_status(state, next_action=next_action, last_error=last_err,
                     extra={"restarts": restarts, "free_disk_gb": round(free, 1),
                            "free_ram_gb": free_ram_gb(), "detail": detail if not pids else "",
                            "stall_level": stall_level, "stall_restarts": stall_restarts,
                            "mode": "pool" if a.pool else "queue",
                            "queue": str(queue_of(queue_cmd) or ""),
                            **({"pool": pool_status()} if a.pool else {})})
        time.sleep(TICK_S)
    # 2026-09-29: the pool is asked to stop by its own STOP file first (it
    # finishes the page in hand, closes its tabs, saves its carried links);
    # only a pool still alive after the wait is ended BY PID. A hard kill left
    # its tabs open in the dedicated Chrome, where the next recycle counted
    # them as somebody else's.
    stopped = []
    if reader_pids():
        st_ = stop_pool_gracefully(wait_s=180.0)
        stopped = st_.get("killed") or []
        log(event="pool_stopped", why="supervisor stopping: " + why, **st_)
    log(event="stopping", why=why, reader_pids_stopped=stopped)
    write_status("stopped", next_action="none: " + why, last_error=last_err)
    digest(a.claims_since)
    log(event="end", why=why, restarts=restarts, page_loads_total=loads())
    return 0


if __name__ == "__main__":
    sys.exit(main())
