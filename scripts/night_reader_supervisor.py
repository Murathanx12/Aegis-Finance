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
    out: dict = {"ok_10m": 0, "ok_60m": 0, "classes_60m": {}, "last_not_ok": None,
                 "current_url_by_worker": {}}
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--until", default="08:00", help="local HH:MM")
    ap.add_argument("--queue-cmd", default=str(DJ / "queue_run.cmd"))
    ap.add_argument("--claims-since", default="2026-07-01")
    ap.add_argument("--no-rolling", dest="rolling", action="store_false",
                    help="run --queue-cmd as given instead of the self-built rolling queue")
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
    rq = rolling_queue(template) if a.rolling else None
    queue_cmd = rq["cmd"] if rq else template
    if rq:
        log(event="rolling_queue", queue=str(rq["queue"]), n_names=rq["n_names"],
            n_unread_today=rq["n_unread_today"])
    logs = queue_logs(queue_cmd)
    why = "end time"
    ticks, state, next_action, last_err = 0, "starting", "launch the reader", None
    idle_until = 0.0
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
            state, next_action = "reading", "keep reading"
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
                    state, next_action = ("idle_all_read_today",
                                          f"rebuild the queue in {ALL_READ_RETRY_S/60:.0f} min")
                    write_status(state, next_action=next_action, last_error=last_err)
                    time.sleep(TICK_S)
                    continue
                cls = {"kind": "NOT_STARTED", "evidence": "rolling queue rebuilt"}
            if caps_reached(cls["kind"], cls["evidence"]):
                idle_until = last_launch + CAPS_RETRY_S
                state, next_action = ("idle_daily_cap",
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
            state = {"stop": "stopped", "repair": "repairing", "wait_dep": "dependency_down",
                     "wait": "backoff", "wait_open_fault": "backoff_open_fault",
                     "relaunch": "relaunching"}.get(act, act)
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
                     extra={"restarts": restarts, "free_gb": round(free, 1),
                            "queue": str(queue_of(queue_cmd) or "")})
        time.sleep(TICK_S)
    stopped = []
    for pid in reader_pids():                      # by PID, matched on the command line
        if kill_pid(pid):                          # each is one of OUR reader processes
            stopped.append(pid)
    log(event="stopping", why=why, reader_pids_stopped=stopped)
    write_status("stopped", next_action="none: " + why, last_error=last_err)
    digest(a.claims_since)
    log(event="end", why=why, restarts=restarts, page_loads_total=loads())
    return 0


if __name__ == "__main__":
    sys.exit(main())
