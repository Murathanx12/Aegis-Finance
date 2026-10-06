"""Keep the PC's scheduled work alive across sleep, boot and a passed `--until`.

    python -m scripts.task_keeper reader      # relaunch the reader supervisor if none is alive
    python -m scripts.task_keeper catchup     # run any daily Aegis task whose trigger was missed
    python -m scripts.task_keeper sim         # start the US-session sim, or write why not
    python -m scripts.task_keeper catalog     # data catalog receipt + archive closed big ledger months
    python -m scripts.task_keeper status      # print every decision, change nothing
    python -m scripts.task_keeper register    # print (never run) the task registrations

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

3. THE SIM HAD NO OWNER (2026-10-06): no session ran 09-29 -> 10-06. `sim`
   starts one inside the US/Eastern start window, in trading mode only when
   the PC-PAPER mandate is OK and the worst case passes, else in `observe`
   with the refusal named; every firing writes one row to `sim/owner.jsonl`.

Every reader/catch-up decision is one JSON line in `task_keeper/keeper.jsonl`;
no LLM and no order. The sim owner reads the broker (one GET) before a start.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

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
                 "AegisAnalystPanelDaily", "AegisHypLabNightly", "AegisContestRehearsal",
                 "AegisDataCatalog")
CATCHUP_MAX_AGE_H = 20.0
CATCHUP_GRACE_MIN = 15.0

TASK_READER = "AegisReaderSupervisor"
#: Daily data catalog + closed-ledger archival (chunk C10, 2026-10-06).
TASK_CATALOG = "AegisDataCatalog"
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


# ================================================================ sim owner
#
# WHY (chunk C2, 2026-10-06). No sim session ran from 2026-09-29 to 10-06
# while the US session opened five times. The 2026-10-02 handoff said
# "AegisIIF1NightLauncher starts a sim session if a safe window remains"; it
# does not -- it launches the IIF1 investigator night (`backend.services.
# iif1_run`) and nothing else. Every session in `sim/sessions.jsonl` was
# started by a person (the button or Telegram `/sim start`), at irregular
# times, and `system_health.p_sim_session` already said so in its own words:
# "no scheduler starts one". `sim` is that scheduler: idempotent, fired every
# 30 min plus logon/unlock/wake, and on every firing it writes ONE receipt row
# to `sim/owner.jsonl` saying what it did or exactly why not.

SIM_DIR = OPT / "sim"
SIM_OWNER_STOP = SIM_DIR / "OWNER_STOP"
SIM_OWNER_LOG = SIM_DIR / "owner.jsonl"
TASK_SIM = "AegisSimOwner"
#: A session the owner stopped on purpose (button / Telegram) is not restarted
#: the same US/Eastern day; this is the `end_reason` `sim_run` writes for it.
OPERATOR_STOP_REASONS = ("stop requested", "signal", "KeyboardInterrupt")


def _et(now_utc: datetime) -> datetime:
    from zoneinfo import ZoneInfo                                  # noqa: PLC0415
    return now_utc.astimezone(ZoneInfo("America/New_York"))


def is_session_day(d) -> bool:
    """XNYS trading day (exchange_calendars; weekdays when it is absent)."""
    from backend.services import system_health as SH               # noqa: PLC0415
    days, _ = SH._sessions(d, d)
    return bool(days)


def sim_window(now_utc: datetime, *, session_day: bool,
               allowed_hours: tuple = (6, 8, 10, 12)) -> dict:
    """PURE. Is a start due now, and for how long? All times US/Eastern."""
    from datetime import time as dtime                             # noqa: PLC0415
    et = _et(now_utc)
    first = dtime(*_config.SIM_OWNER_FIRST_START_ET)
    last = dtime(*_config.SIM_OWNER_LAST_START_ET)
    base = {"now_et": et.isoformat(timespec="minutes"), "et_date": et.date().isoformat(),
            "session_day": bool(session_day),
            "window_et": f"{first:%H:%M}-{last:%H:%M}"}
    if not session_day:
        return {**base, "in_window": False,
                "why": f"{et.date()} is not an XNYS session day"}
    if et.time() < first:
        return {**base, "in_window": False,
                "why": f"before the first start ({first:%H:%M} ET); now {et:%H:%M} ET"}
    if et.time() > last:
        return {**base, "in_window": False,
                "why": f"after the last start ({last:%H:%M} ET); now {et:%H:%M} ET"}
    close = et.replace(hour=16, minute=0, second=0, microsecond=0)
    target = close + timedelta(minutes=int(_config.SIM_OWNER_END_AFTER_CLOSE_MIN))
    need_h = (target - et).total_seconds() / 3600.0
    fit = [h for h in allowed_hours if h >= need_h]
    hours = min(fit) if fit else max(allowed_hours)
    return {**base, "in_window": True, "hours": hours,
            "ends_et": (et + timedelta(hours=hours)).isoformat(timespec="minutes"),
            "why": f"inside the start window; {hours} h reaches {target:%H:%M} ET"}


def sim_owner_gate(*, now_utc: datetime, session_day: bool, sim: dict,
                   stop_exists: bool, disk_ok: tuple[bool, str] = (True, "")) -> dict:
    """PURE. What the owner does BEFORE the mandate is read:
    `paused` / `stopped_by_operator` / `alive` / `outside_window` / `refused` / `start`."""
    if stop_exists:
        return {"action": "paused", "verdict": "STOPPED_BY_OPERATOR",
                "why": f"{SIM_OWNER_STOP.name} exists (the owner's pause); delete it to resume"}
    state = str(sim.get("state") or "IDLE")
    s = sim.get("session") or {}
    if state in ("RUNNING", "STOPPING"):
        return {"action": "alive", "session": s.get("id"), "mode": s.get("mode"),
                "pid": s.get("pid"), "why": f"session {s.get('id')} is {state}"}
    win = sim_window(now_utc, session_day=session_day)
    if not win["in_window"]:
        return {"action": "outside_window", "window": win, "why": win["why"]}
    ended = s.get("ended")
    if state == "STOPPED" and str(s.get("end_reason")) in OPERATOR_STOP_REASONS and ended:
        try:
            ended_et = _et(datetime.fromisoformat(str(ended)))
        except ValueError:
            ended_et = None
        if ended_et is not None and ended_et.date().isoformat() == win["et_date"]:
            return {"action": "stopped_by_operator", "verdict": "STOPPED_BY_OPERATOR",
                    "session": s.get("id"), "window": win,
                    "why": (f"session {s.get('id')} was stopped on purpose today "
                            f"({s.get('end_reason')}, {ended}); not restarted until the "
                            f"next session day")}
    ok, why = disk_ok
    if not ok:
        return {"action": "refused", "window": win, "why": f"REFUSED_DISK: {why}"}
    return {"action": "start", "window": win, "hours": win["hours"],
            "why": win["why"]}


def sim_owner_mode(mandate: dict | None) -> tuple[str, str | None]:
    """PURE. (mode, trade_refused). Trading only on an OK mandate whose worst
    case PASSES; anything else starts `observe` and names why."""
    if not isinstance(mandate, dict) or not mandate.get("status"):
        return "observe", "MANDATE CANNOT DETERMINE: no mandate block was computed"
    gate = (mandate.get("worst_case_gate") or {})
    if gate.get("verdict") != "PASS":
        return "observe", ("WORST CASE " + str(gate.get("verdict") or "UNKNOWN") + ": "
                           + str(gate.get("line") or "no worst-case gate on the mandate"))
    if mandate.get("status") != "OK":
        kinds = [str(d).split(":", 1)[0] for d in mandate.get("disagreements") or []]
        return "observe", f"MANDATE {mandate.get('status')}: {', '.join(kinds) or '?'}"
    return str(_config.SIM_OWNER_MODE), None


def _disk_ok() -> tuple[bool, str]:
    try:
        from backend.services import disk_guard as DG              # noqa: PLC0415
        DG.require_free(_config.DISK_FREE_DEAD_GB + 1, "sim owner",
                        path=_config.OPTIMUS_LEDGER_DIR)
        return True, ""
    except Exception as exc:                                       # noqa: BLE001
        return False, f"{type(exc).__name__}: {str(exc)[:200]}"


def _broker_read() -> dict:
    """One live broker read of PC-PAPER, persisted where the mandate reads it."""
    try:
        from backend.services import pc_broker as PB                # noqa: PLC0415
        snap = PB.snapshot(tag="sim_owner")
        return {"ok": True, "equity": snap.get("equity"), "t": snap.get("t")}
    except Exception as exc:                                       # noqa: BLE001
        return {"ok": False, "why": f"{type(exc).__name__}: {str(exc)[:200]}"}


def _mandate() -> dict | None:
    from backend.services import decision_contract as DC           # noqa: PLC0415
    m = DC.account_mandate(None)
    return {k: m.get(k) for k in ("status", "capital_usd", "capital_source",
                                  "broker_equity_usd", "broker_equity_as_of",
                                  "disagreements", "worst_case_gate", "line")}


def ensure_sim(*, now_utc: datetime | None = None,
               status: Callable[[], dict] | None = None,
               start: Callable[..., dict] | None = None,
               session_day: Callable[[Any], bool] = is_session_day,
               broker_read: Callable[[], dict] = _broker_read,
               mandate: Callable[[], dict | None] = _mandate,
               disk: Callable[[], tuple[bool, str]] = _disk_ok,
               stop_path: Path | None = None, log_path: Path | None = None,
               dry_run: bool = False) -> dict:
    """The scheduled sim owner. One receipt row per firing, whatever happens."""
    import uuid                                                    # noqa: PLC0415
    from backend.services import sim_session as SS                 # noqa: PLC0415
    now_utc = now_utc or _now()
    run_id = uuid.uuid4().hex[:12]
    row: dict = {"job": "sim", "run_id": run_id}
    try:
        sim = (status or SS.status)()
        et_day = _et(now_utc).date()
        d = sim_owner_gate(now_utc=now_utc, session_day=session_day(et_day), sim=sim,
                           stop_exists=Path(stop_path or SIM_OWNER_STOP).exists(),
                           disk_ok=disk())
        row.update(d)
        if d["action"] == "start":
            row["broker_read"] = broker_read()
            m = mandate()
            row["mandate"] = m
            mode, trade_refused = sim_owner_mode(m)
            row.update(mode=mode, trade_refused=trade_refused)
            if dry_run:
                row["action"] = "would_start"
            else:
                try:
                    sess = (start or SS.start)(hours=d["hours"], mode=mode)
                    row.update(action="started", session=sess.get("id"),
                               pid=sess.get("pid"), planned_end=sess.get("planned_end"))
                except Exception as exc:                           # noqa: BLE001
                    row.update(action="refused",
                               why=f"sim_session.start refused: {type(exc).__name__}: "
                                   f"{str(exc)[:240]}")
    except Exception as exc:                                       # noqa: BLE001
        row.update(action="refused", why=f"owner raised {type(exc).__name__}: {str(exc)[:240]}")
    return log(row, log_path or SIM_OWNER_LOG)


# ================================================================ catalog
#
# WHY (chunk C10, 2026-10-06). "We pull the same data again" and "the long-term
# archival design for very large monthly ledgers is unresolved". Once a day:
# archive every CLOSED `<ledger>_<YYYY-MM>.jsonl` over the size floor to Parquet
# outside git with a committed manifest (`ledger_archive`), THEN walk the data
# roots into a catalog receipt (`data_catalog`) so the new manifest is in it.
# A failed step is a REFUSED row with its reason; neither step deletes data.
# TODO(orchestrator): once C3/C7 land their daily_pass edits, consider a
# `data_catalog` step there too, so the morning report can print catalog age.

def run_catalog(*, archive: Callable[[], dict] | None = None,
                catalog: Callable[[], dict] | None = None,
                log_path: Path | None = None) -> dict:
    row: dict = {"job": "catalog"}
    try:
        if archive is None:
            from backend.services import ledger_archive as LA      # noqa: PLC0415
            archive = LA.archive_closed
        a = archive()
        row["archive"] = {"status": a.get("status"),
                          "months": [{k: m.get(k) for k in ("path", "action", "manifest", "why")}
                                     for m in a.get("months", [])]}
    except Exception as exc:                                       # noqa: BLE001
        row["archive"] = {"status": "REFUSED", "why": f"{type(exc).__name__}: {str(exc)[:300]}"}
    try:
        if catalog is None:
            from backend.services import data_catalog as DC        # noqa: PLC0415
            catalog = DC.run
        row["catalog"] = catalog()
    except Exception as exc:                                       # noqa: BLE001
        row["catalog"] = {"status": "REFUSED", "why": f"{type(exc).__name__}: {str(exc)[:300]}"}
    bad = (row["archive"].get("status") != "OK"
           or row["catalog"].get("status") == "REFUSED")
    row["action"] = "refused" if bad else "ok"
    return log(row, log_path)


# ================================================================ register

def registration_ps() -> str:
    """PowerShell that (re)registers the three tasks. Printed by `register`.

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
        "# the sim owner: same triggers, every 30 minutes (it decides by the US/Eastern clock)",
        "$daily = New-ScheduledTaskTrigger -Daily -At 07:00",
        "$rep = New-ScheduledTaskTrigger -Once -At 07:10 -RepetitionInterval (New-TimeSpan -Minutes 30)",
        f"$a = New-ScheduledTaskAction -Execute '{pyw}' -Argument \"-m scripts.task_keeper sim\" "
        f"-WorkingDirectory '{REPO}'",
        "Register-ScheduledTask -TaskName '" + TASK_SIM + "' -Action $a -Settings $S -Force "
        "-Trigger @((New-ScheduledTaskTrigger -AtLogOn -User \"$env:USERDOMAIN\\$env:USERNAME\"), "
        "$unlock, $wake, $daily, $rep)",
        "# the data catalog + ledger archival: once a day; `catchup` starts it if the PC slept",
        "$SC = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries "
        "-DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)",
        f"$a = New-ScheduledTaskAction -Execute '{pyw}' -Argument \"-m scripts.task_keeper catalog\" "
        f"-WorkingDirectory '{REPO}'",
        "Register-ScheduledTask -TaskName '" + TASK_CATALOG + "' -Action $a -Settings $SC -Force "
        "-Trigger @(New-ScheduledTaskTrigger -Daily -At 05:30)",
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
    ap.add_argument("job", choices=("reader", "catchup", "sim", "status", "register", "catalog"))
    a = ap.parse_args(argv)
    if a.job == "register":
        print(registration_ps())
        return 0
    if a.job == "status":
        print(json.dumps({"reader": ensure_reader(dry_run=True),
                          "catchup": catch_up(dry_run=True),
                          "sim": ensure_sim(dry_run=True)}, indent=1, default=str))
        return 0
    if a.job == "catalog":
        out = run_catalog()
        print(json.dumps(out, default=str))
        return 2 if out.get("action") == "refused" else 0
    if a.job == "sim":
        out = ensure_sim()
        print(json.dumps(out, default=str))
        return 2 if out.get("action") == "refused" else 0
    out = ensure_reader() if a.job == "reader" else catch_up()
    print(json.dumps(out, default=str))
    return 0 if out.get("action") not in ("launch_failed", "cannot_determine") else 2


if __name__ == "__main__":
    raise SystemExit(main())
