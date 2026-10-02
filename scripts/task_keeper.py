"""Keep the PC's scheduled work alive across sleep, boot and a passed `--until`.

    python -m scripts.task_keeper reader      # relaunch the reader supervisor if none is alive
    python -m scripts.task_keeper catchup     # run any daily Aegis task whose trigger was missed
    python -m scripts.task_keeper status      # print both decisions, change nothing
    python -m scripts.task_keeper register    # print (never run) the two task registrations

WHY (automation audit, 2026-10-02)
==================================
1. THE READER HAD NO SCHEDULED TASK. `night_reader_supervisor --until 12:00`
   stops itself at its own end time, and nothing relaunched it: 57.5 hours with
   no reader tick (2026-09-30 10:48 -> 10-02 20:17 local) while the PC was awake.
   `reader` is idempotent: it exits when a supervisor is alive (matched on the
   COMMAND LINE, never the image name), honours the owner's pause file
   `dowjones/SUPERVISOR_STOP`, and otherwise launches
   `dowjones/supervisor_run.cmd <HH:MM> <dated log>` with a ROLLING end time
   (`READER_ROLL_H` ahead), detached, and records the PID it started.
2. FOUR DAILY TASKS SKIPPED 10-02 because the PC slept over their trigger and
   battery conditions blocked the catch-up. The tasks now carry
   StartWhenAvailable + WakeToRun; `catchup` is the belt to those braces: for
   each task in `CATCHUP_TASKS` it computes the most recent scheduled
   occurrence from the task's own trigger, and if the task has not run since
   (and the occurrence is less than `CATCHUP_MAX_AGE_H` old and more than
   `CATCHUP_GRACE_MIN` old, so Windows' own catch-up gets the first chance) it
   starts the task by NAME -- so the task's own action, STOP files and
   single-instance rules apply exactly as on a scheduled firing.
   The fleet-manager OPEN/PRECLOSE passes are deliberately NOT caught up here:
   a live-order pass started at the wrong time of day is not a catch-up.

Every decision is one JSON line in `task_keeper/keeper.jsonl`; no LLM, no
network, no order.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config  # noqa: E402

OPT = Path(_config.OPTIMUS_LEDGER_DIR)
DJ = OPT / "dowjones"
SUPERVISOR_CMD = DJ / "supervisor_run.cmd"
SUPERVISOR_STOP = DJ / "SUPERVISOR_STOP"
KEEPER_DIR = OPT / "task_keeper"
KEEPER_LOG = KEEPER_DIR / "keeper.jsonl"

#: The supervisor's end time is this far ahead of each launch: the keeper fires
#: at least every two hours, so a supervisor never outlives its relaunch path.
READER_ROLL_H = 23.0

#: Daily jobs the catch-up may start late. NOT the fleet-manager passes (live
#: orders at the wrong time are not a catch-up) and not the IIF1 launcher (it
#: computes its own safe-launch window and refuses outside it).
CATCHUP_TASKS = ("AegisDailyPass", "AegisFleetDailyCheck", "AegisNNLabNightly",
                 "AegisAnalystPanelDaily", "AegisHypLabNightly", "AegisContestRehearsal")
CATCHUP_MAX_AGE_H = 20.0
CATCHUP_GRACE_MIN = 15.0

TASK_READER = "AegisReaderSupervisor"
TASK_CATCHUP = "AegisCatchUp"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def log(row: dict, path: Path | None = None) -> dict:
    p = Path(path or KEEPER_LOG)
    p.parent.mkdir(parents=True, exist_ok=True)
    row = {"utc": _now().isoformat(timespec="seconds"), **row}
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    return row


# ============================================================ process table

def scan_python() -> Optional[list[dict]]:
    """Every python process as {pid, cmdline}; None when the scan itself failed
    (CANNOT DETERMINE is not "nothing is running")."""
    if sys.platform != "win32":
        return None
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
             "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }"],
            capture_output=True, text=True, timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:                                              # noqa: BLE001
        return None
    if r.returncode != 0:
        return None
    out = []
    for line in (r.stdout or "").splitlines():
        pid, _, cmd = line.partition("\t")
        if pid.strip().isdigit():
            out.append({"pid": int(pid), "cmdline": cmd})
    return out


def supervisor_rows(rows: list[dict]) -> list[dict]:
    """PURE. The rows that are a RUNNING supervisor loop (not a `--probe` or a
    `--repair-once` one-shot, which exit by themselves)."""
    out = []
    for r in rows or []:
        c = str(r.get("cmdline") or "")
        if "scripts.night_reader_supervisor" not in c:
            continue
        if "--probe" in c or "--repair-once" in c:
            continue
        out.append(r)
    return out


# ================================================================== reader

def rolling_until(now_local: datetime, roll_h: float = READER_ROLL_H) -> str:
    """PURE. The `--until HH:MM` that ends `roll_h` hours after `now_local`."""
    return (now_local + timedelta(hours=roll_h)).strftime("%H:%M")


def reader_decision(*, rows: Optional[list[dict]], stop_exists: bool) -> dict:
    """PURE. What `reader` should do: `paused` / `alive` / `cannot_determine` / `launch`."""
    if stop_exists:
        return {"action": "paused",
                "why": f"{SUPERVISOR_STOP.name} exists (the owner's pause); delete it to resume"}
    if rows is None:
        return {"action": "cannot_determine",
                "why": "the process scan failed; launching blind could start a second supervisor"}
    sup = supervisor_rows(rows)
    if sup:
        return {"action": "alive", "pids": [r["pid"] for r in sup],
                "why": f"{len(sup)} supervisor process(es) alive (launcher + interpreter count as 2)"}
    return {"action": "launch", "why": "no supervisor process alive"}


def launch_supervisor(until: str, log_path: Path) -> int:
    """Start `supervisor_run.cmd <until> <log>` detached; return its PID."""
    flags = (getattr(subprocess, "DETACHED_PROCESS", 0)
             | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
             | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    p = subprocess.Popen(["cmd.exe", "/c", str(SUPERVISOR_CMD), until, str(log_path)],
                         cwd=str(REPO), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, creationflags=flags, close_fds=True)
    return int(p.pid)


def ensure_reader(*, scan: Callable[[], Optional[list[dict]]] = scan_python,
                  launch: Callable[[str, Path], int] = launch_supervisor,
                  stop_path: Path | None = None, now_local: datetime | None = None,
                  log_path: Path | None = None, dry_run: bool = False) -> dict:
    now_local = now_local or datetime.now()
    stop = Path(stop_path or SUPERVISOR_STOP)
    d = reader_decision(rows=scan(), stop_exists=stop.exists())
    d["job"] = "reader"
    if d["action"] == "launch" and not dry_run:
        until = rolling_until(now_local)
        sup_log = DJ / f"supervisor_{now_local:%Y-%m-%d_%H%M}.log"
        try:
            d["launched_pid"] = launch(until, sup_log)
            d.update(until=until, supervisor_log=str(sup_log))
        except Exception as exc:                                   # noqa: BLE001
            d["action"] = "launch_failed"
            d["why"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    return log(d, log_path)


# ================================================================= catch-up

def last_due(trigger: dict, now_local: datetime) -> Optional[datetime]:
    """PURE. The most recent scheduled occurrence <= `now_local` of a daily or
    weekly trigger: {"start": ISO StartBoundary, "days_interval": int|None,
    "days_of_week": bitmask|None (Sun=1 .. Sat=64)}. None for anything else."""
    try:
        st = datetime.fromisoformat(str(trigger["start"]))
    except (KeyError, ValueError, TypeError):
        return None
    st = st.replace(tzinfo=None)              # the boundary is local wall-clock time
    if st > now_local:
        return None
    mask = trigger.get("days_of_week")
    interval = trigger.get("days_interval")
    for back in range(0, 15):
        day = (now_local - timedelta(days=back)).date()
        cand = datetime.combine(day, st.time())
        if cand > now_local or cand < st:
            continue
        if mask:
            bit = 1 << ((cand.weekday() + 1) % 7)          # Mon=0 -> 2, Sun=6 -> 1
            if not int(mask) & bit:
                continue
            return cand
        if interval:
            if (cand.date() - st.date()).days % int(interval) == 0:
                return cand
            continue
        return None
    return None


def catchup_decision(task: dict, now_local: datetime, *,
                     max_age_h: float = CATCHUP_MAX_AGE_H,
                     grace_min: float = CATCHUP_GRACE_MIN) -> dict:
    """PURE. task = {"name", "state", "last_run": ISO local or None, "triggers": [...]}."""
    name = task.get("name")
    if str(task.get("state")) in ("Running", "Disabled"):
        return {"task": name, "action": "skip", "why": f"state {task.get('state')}"}
    dues = [d for d in (last_due(t, now_local) for t in task.get("triggers") or []) if d]
    if not dues:
        return {"task": name, "action": "skip", "why": "no daily/weekly occurrence due"}
    due = max(dues)
    try:
        lr = datetime.fromisoformat(str(task.get("last_run"))).replace(tzinfo=None)
    except (ValueError, TypeError):
        lr = None
    age_h = (now_local - due).total_seconds() / 3600.0
    if lr is not None and lr >= due - timedelta(minutes=1):
        return {"task": name, "action": "ok", "due": due.isoformat(), "last_run": lr.isoformat()}
    if age_h * 60 < grace_min:
        return {"task": name, "action": "wait", "due": due.isoformat(),
                "why": f"due {age_h * 60:.0f} min ago; Windows' own catch-up goes first"}
    if age_h > max_age_h:
        return {"task": name, "action": "too_old", "due": due.isoformat(),
                "why": f"missed occurrence is {age_h:.1f} h old (> {max_age_h:g} h); the next one will run"}
    return {"task": name, "action": "start", "due": due.isoformat(),
            "last_run": lr.isoformat() if lr else None,
            "why": f"missed the {due:%Y-%m-%d %H:%M} occurrence ({age_h:.1f} h ago)"}


_TASKS_PS = r"""
$names = @(__NAMES__)
$out = foreach ($n in $names) {
  $t = Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue
  if (-not $t) { continue }
  $i = $t | Get-ScheduledTaskInfo
  [pscustomobject]@{ name = $n; state = "$($t.State)";
    last_run = $(if ($i.LastRunTime -and $i.LastRunTime.Year -gt 2000) { $i.LastRunTime.ToString('s') } else { $null });
    triggers = @($t.Triggers | ForEach-Object { [pscustomobject]@{ start = $_.StartBoundary;
      days_interval = $_.DaysInterval; days_of_week = $_.DaysOfWeek } }) }
}
$out | ConvertTo-Json -Depth 5 -Compress
"""


def read_tasks(names: tuple[str, ...] = CATCHUP_TASKS) -> Optional[list[dict]]:
    if sys.platform != "win32":
        return None
    ps = _TASKS_PS.replace("__NAMES__", ",".join(f"'{n}'" for n in names))
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True,
                           text=True, timeout=90,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        js = json.loads(r.stdout or "null")
    except Exception:                                              # noqa: BLE001
        return None
    if js is None:
        return []
    return js if isinstance(js, list) else [js]


def start_task(name: str) -> int:
    r = subprocess.run(["schtasks", "/Run", "/TN", name], capture_output=True, text=True,
                       timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return int(r.returncode)


def catch_up(*, tasks: Callable[[], Optional[list[dict]]] = read_tasks,
             start: Callable[[str], int] = start_task, now_local: datetime | None = None,
             log_path: Path | None = None, dry_run: bool = False) -> dict:
    now_local = now_local or datetime.now()
    ts = tasks()
    if ts is None:
        return log({"job": "catchup", "action": "cannot_determine",
                    "why": "could not read the task scheduler"}, log_path)
    rows = []
    for t in ts:
        d = catchup_decision(t, now_local)
        if d["action"] == "start" and not dry_run:
            d["rc"] = start(str(t.get("name")))
            d["action"] = "started" if d["rc"] == 0 else "start_failed"
        rows.append(d)
    reports: list = []
    if not dry_run:
        # a finished sim session always gets its learning report (or a FAILED row)
        try:
            from scripts import daily_learning_report as DLR       # noqa: PLC0415
            reports = [{k: r.get(k) for k in ("session", "day", "status", "error")}
                       for r in DLR.ensure_session_reports()]
        except Exception as exc:                                   # noqa: BLE001
            reports = [{"status": "FAILED", "error": f"{type(exc).__name__}: {str(exc)[:200]}"}]
    return log({"job": "catchup", "decisions": rows,
                "started": [r["task"] for r in rows if r["action"] == "started"],
                "learning_reports": reports}, log_path)


# ================================================================ register

def registration_ps() -> str:
    """PowerShell that (re)registers the two tasks. Printed by `register`.

    The logon and unlock triggers are scoped to THIS user: an unscoped unlock
    trigger (any user) needs elevation and fails with 0x80070005 (measured
    2026-10-02)."""
    pyw = REPO / ".venv" / "Scripts" / "pythonw.exe"
    return "\n".join([
        "$S = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -AllowStartIfOnBatteries "
        "-DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)",
        "$unlock = New-CimInstance -CimClass (Get-CimClass -Namespace Root/Microsoft/Windows/TaskScheduler "
        "-ClassName MSFT_TaskSessionStateChangeTrigger) -Property @{StateChange=8; "
        "UserId=\"$env:USERDOMAIN\\$env:USERNAME\"} -ClientOnly",
        "$wake = New-CimInstance -CimClass (Get-CimClass -Namespace Root/Microsoft/Windows/TaskScheduler "
        "-ClassName MSFT_TaskEventTrigger) -Property @{Enabled=$true; Subscription='<QueryList><Query Id=\"0\" "
        "Path=\"System\"><Select Path=\"System\">*[System[Provider[@Name=''Microsoft-Windows-Power-Troubleshooter'']"
        " and EventID=1]]</Select></Query></QueryList>'} -ClientOnly",
        "foreach ($j in @(@('" + TASK_READER + "','reader'),@('" + TASK_CATCHUP + "','catchup'))) {",
        "  $daily = New-ScheduledTaskTrigger -Daily -At 07:00",
        "  $rep = New-ScheduledTaskTrigger -Once -At 07:05 -RepetitionInterval (New-TimeSpan -Hours 2)",
        f"  $a = New-ScheduledTaskAction -Execute '{pyw}' -Argument \"-m scripts.task_keeper $($j[1])\" "
        f"-WorkingDirectory '{REPO}'",
        "  Register-ScheduledTask -TaskName $j[0] -Action $a -Settings $S -Force "
        "-Trigger @((New-ScheduledTaskTrigger -AtLogOn -User \"$env:USERDOMAIN\\$env:USERNAME\"), "
        "$unlock, $wake, $daily, $rep)",
        "}",
    ])


def _ensure_streams() -> None:
    if sys.stdout is None or sys.stderr is None:
        KEEPER_DIR.mkdir(parents=True, exist_ok=True)
        fh = open(KEEPER_DIR / "keeper_stdout.log", "a", encoding="utf-8")  # noqa: SIM115
        sys.stdout = sys.stdout or fh
        sys.stderr = sys.stderr or fh


def main(argv: list[str] | None = None) -> int:
    _ensure_streams()
    ap = argparse.ArgumentParser(prog="task_keeper")
    ap.add_argument("job", choices=("reader", "catchup", "status", "register"))
    a = ap.parse_args(argv)
    if a.job == "register":
        print(registration_ps())
        return 0
    if a.job == "status":
        print(json.dumps({"reader": ensure_reader(dry_run=True),
                          "catchup": catch_up(dry_run=True)}, indent=1, default=str))
        return 0
    out = ensure_reader() if a.job == "reader" else catch_up()
    print(json.dumps(out, default=str))
    return 0 if out.get("action") not in ("launch_failed", "cannot_determine") else 2


if __name__ == "__main__":
    raise SystemExit(main())
