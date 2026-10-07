"""Keep the PC's scheduled work alive across sleep, boot and a passed `--until`.

    python -m scripts.task_keeper reader      # relaunch the reader supervisor if none is alive
    python -m scripts.task_keeper catchup     # run any daily Aegis task whose trigger was missed
    python -m scripts.task_keeper sim         # start the US-session sim, or write why not
    python -m scripts.task_keeper catalog     # data catalog receipt + report unsealed closed ledger months
                                              # (then the snowball shadow grade, C18)
    python -m scripts.task_keeper snowball    # C18: snowball follow-through shadow rows + grades
    python -m scripts.task_keeper opportunities  # C15: rebuild the Opportunity Explorer receipt
    python -m scripts.task_keeper publish     # C15: sanitised public copies -> backend/data/public_receipts/
    python -m scripts.task_keeper publish_commit  # C15 H1: commit ONLY that folder on main + push
    python -m scripts.task_keeper assets      # bump the public-assets pin, test, commit + push (weekly)
    python -m scripts.task_keeper analyst     # weekly analyst-target pull (refuses in US hours)
    python -m scripts.task_keeper brain       # refresh the Optimus brain (tools/refresh_aegis.py)
    python -m scripts.task_keeper public_flow # C16 sensors: USAspending daily, LDA weekly, crypto daily
    python -m scripts.task_keeper register-owners [--apply]   # C8: AegisAnalystPull + AegisBrainRefresh
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
                 "AegisDataCatalog",
                 # C8 (2026-10-07): the two owners for jobs that had none
                 "AegisBrainRefresh", "AegisAnalystPull",
                 # C16 (2026-10-07): the public-flow sensors' daily owner
                 "AegisPublicFlow")
CATCHUP_MAX_AGE_H = 20.0
CATCHUP_GRACE_MIN = 15.0

TASK_READER = "AegisReaderSupervisor"
#: Daily data catalog + closed-ledger archival (chunk C10, 2026-10-06).
TASK_CATALOG = "AegisDataCatalog"
#: Weekly public-assets refresh (2026-10-07 chunk): Saturday, after the Friday close's daily
#: pass and the same-day catalog firing. `config.PUBLIC_ASSETS_REFRESH_WEEKDAY`/`_HHMM`.
TASK_ASSETS = "AegisPublicAssetsWeekly"
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


def sim_owner_mode(mandate: dict | None,
                   broker_read: dict | None = None) -> tuple[str, str | None]:
    """PURE. (mode, trade_refused). Trading only when ALL hold:
    * the live broker read just made succeeded (review C2 F5: a failed live
      read must not trade on a file up to four days old);
    * the read is from the PC-PAPER account (`account_verified`);
    * the mandate is OK;
    * the worst-case gate's TRADING verdict passes (PASS, or PASS with
      EXPLOIT capped / off -- u_plan enforces the cap every cycle).
    Anything else starts `observe` and names why."""
    if broker_read is not None and not broker_read.get("ok"):
        return "observe", ("LIVE BROKER READ FAILED: " + str(broker_read.get("why") or "?")
                           + " -- a persisted read is not enough to trade on")
    if not isinstance(mandate, dict) or not mandate.get("status"):
        return "observe", "MANDATE CANNOT DETERMINE: no mandate block was computed"
    gate = (mandate.get("worst_case_gate") or {})
    tv = str(gate.get("trading_verdict") or gate.get("verdict") or "UNKNOWN")
    if not tv.startswith("PASS"):
        return "observe", ("WORST CASE " + tv + ": "
                           + str(gate.get("line") or "no worst-case gate on the mandate"))
    if mandate.get("status") != "OK":
        kinds = [str(d).split(":", 1)[0] for d in mandate.get("disagreements") or []]
        return "observe", f"MANDATE {mandate.get('status')}: {', '.join(kinds) or '?'}"
    if mandate.get("account_verified") is False:
        return "observe", ("ACCOUNT UNVERIFIED: the broker read carries no account number "
                           "matching config.PC_PAPER_ACCOUNT_NUMBER")
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
        return {"ok": True, "equity": snap.get("equity"), "t": snap.get("t"),
                "account_number": snap.get("account_number")}
    except Exception as exc:                                       # noqa: BLE001
        return {"ok": False, "why": f"{type(exc).__name__}: {str(exc)[:200]}"}


def _mandate() -> dict | None:
    from backend.services import decision_contract as DC           # noqa: PLC0415
    m = DC.account_mandate(None)
    return {k: m.get(k) for k in ("status", "capital_usd", "capital_source",
                                  "broker_equity_usd", "broker_equity_as_of",
                                  "account_number", "account_verified",
                                  "disagreements", "worst_case_gate", "line")}


def ensure_sim(*, now_utc: datetime | None = None,
               status: Callable[[], dict] | None = None,
               start: Callable[..., dict] | None = None,
               session_day: Callable[[Any], bool] = is_session_day,
               broker_read: Callable[[], dict] = _broker_read,
               mandate: Callable[[], dict | None] = _mandate,
               disk: Callable[[], tuple[bool, str]] = _disk_ok,
               stop_path: Path | None = None, log_path: Path | None = None,
               stop_running: Callable[..., dict] | None = None,
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
        if d["action"] == "paused" and str(sim.get("state")) in ("RUNNING", "STOPPING")                 and not dry_run:
            # review C2 F3: the owner's pause also stops a RUNNING session, at its
            # next unit boundary (sim_session.request_stop), never mid-unit
            try:
                row["stop_requested"] = (stop_running or SS.request_stop)(reason="OWNER_STOP")
            except Exception as exc:                               # noqa: BLE001
                row["stop_requested"] = {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}
        if d["action"] == "start":
            row["broker_read"] = broker_read()
            m = mandate()
            row["mandate"] = m
            mode, trade_refused = sim_owner_mode(m, row["broker_read"])
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
# WHY (chunk C10, 2026-10-06; scan-only since review F4, 10-07). "We pull the
# same data again" and "the long-term archival design for very large monthly
# ledgers is unresolved". Once a day, UNATTENDED and READ-ONLY for ledgers:
# report every CLOSED `<ledger>_<YYYY-MM>.jsonl` over the size floor that is
# not sealed, with the reason and the command (`ledger_archive.scan_report`);
# sealing is an attended `--apply` plus a commit, never cron. Then walk the data
# roots into a catalog receipt (`data_catalog`). A failed step is a REFUSED row
# with its reason; unsealed months are ATTENTION, not a failure of the job.
# TODO(orchestrator): once C3/C7 land their daily_pass edits, consider a
# `data_catalog` step there too, so the morning report can print catalog age.

def run_catalog(*, archive: Callable[[], dict] | None = None,
                catalog: Callable[[], dict] | None = None,
                log_path: Path | None = None) -> dict:
    row: dict = {"job": "catalog"}
    try:
        if archive is None:
            from backend.services import ledger_archive as LA      # noqa: PLC0415
            archive = LA.scan_report
        a = archive()
        row["archive"] = {"status": a.get("status"), "apply": a.get("apply", False),
                          "headline": a.get("headline"),
                          "months": [{k: m.get(k) for k in ("path", "sealed", "why", "command")}
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
    bad = (row["archive"].get("status") == "REFUSED"
           or row["catalog"].get("status") == "REFUSED")
    row["action"] = ("refused" if bad else
                     "attention" if row["archive"].get("status") == "ATTENTION" else "ok")
    return log(row, log_path)


# ================================================================ regret
# C11 (2026-10-06): the regret ledger prices the decision stories' frozen
# alternatives once their 5/21/63-session horizons mature. A failed step is a
# REFUSED row with its reason. It reads bars and frozen rows; it never orders.
# Scheduled by `scripts/daily_pass.py` step `regret` (C11 review F4); this job is
# the attended / catch-up entry for the same grader.

def run_regret(*, grade: Callable[[], dict] | None = None,
               log_path: Path | None = None) -> dict:
    row: dict = {"job": "regret"}
    try:
        if grade is None:
            from backend.services import regret_ledger as RL        # noqa: PLC0415
            grade = RL.grade_due
        g = grade()
        row["regret"] = {k: g.get(k) for k in ("status", "run_id", "path", "line",
                                                 "n_decisions_frozen", "pending_not_matured")}
        bad = g.get("status") == "REFUSED"
    except Exception as exc:                                       # noqa: BLE001
        row["regret"] = {"status": "REFUSED", "why": f"{type(exc).__name__}: {str(exc)[:300]}"}
        bad = True
    row["action"] = "refused" if bad else "ok"
    return log(row, log_path)


# ================================================================ snowball (C18)
# The snowball FOLLOW-THROUGH shadow series (`services/snowball_shadow`): append
# a row per new t0 event, grade every row whose 63-session window closed. Its
# own grader, because `belief_state.resolve_one` reads only prices. Runs daily
# after `catalog` (same scheduled task, AegisDataCatalog, caught up by `catchup`),
# so it needed no new task registration. Nothing trades; no LLM; no network.

def run_snowball(*, job: Callable[[], dict] | None = None,
                 log_path: Path | None = None) -> dict:
    row: dict = {"job": "snowball"}
    try:
        if job is None:
            from backend.services import snowball_shadow as SS       # noqa: PLC0415
            job = SS.run
        g = job()
        row["snowball"] = {k: g.get(k) for k in ("status", "path", "rows_total", "rows_new",
                                                   "rows_graded_now", "forward_new", "first_seen_basis")}
        bad = g.get("status") != "ok"
    except Exception as exc:                                       # noqa: BLE001
        row["snowball"] = {"status": "REFUSED", "why": f"{type(exc).__name__}: {str(exc)[:300]}"}
        bad = True
    row["action"] = "refused" if bad else "ok"
    return log(row, log_path)


# ================================================================ opportunities + publish (C15)
#
# WHY (chunk C15, 2026-10-07). Two follow-ups owed by reviews:
#  * C4 F6: `scripts.opportunities_build` had NO scheduled caller -- the
#    funnel_night10.json pattern rebuilt (a static file, an age check, nobody
#    running the remedy). It now runs daily inside the AegisDataCatalog firing,
#    which is registered AFTER the daily pass (bars refresh 06:30 + analyst
#    snapshot) and the analyst panel (05:30), as a CHILD process (a crash or a
#    memory spike cannot take the keeper down), with a time limit.
#  * C19 F12: the public pages 404 on Railway because their receipts are not in
#    git. `publish_receipts` runs LAST in the same firing and writes sanitised
#    copies into the TRACKED `backend/data/public_receipts/`; the daily commit of
#    that folder is what makes the pages public.
# Each step writes ONE row to its own series (`task_keeper/opportunities.jsonl`,
# `task_keeper/publish_receipts.jsonl`), which `task_receipts.r_catalog` folds
# into the AegisDataCatalog health row. A failed step is a REFUSED row with its
# reason; it never changes the catalog's own exit code.

OPPORTUNITIES_LOG = KEEPER_DIR / "opportunities.jsonl"
PUBLISH_LOG = KEEPER_DIR / "publish_receipts.jsonl"
OPPORTUNITIES_TIMEOUT_S = 45 * 60


#: review C15 M5: the Explorer build loads bars while the sim owner fires every 30 min; below
#: this much free RAM the build is REFUSED (logged), never started -- otherwise the OOM killer
#: chooses between it and the sim.
OPPORTUNITIES_MIN_FREE_GB = 4.0


def _free_gb() -> Optional[float]:
    """Available physical RAM (GlobalMemoryStatusEx, the reading `bridges_on_crsp._mem_gb`
    uses; psutil is not installed here). None = cannot read -- never a made-up number."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes                                              # noqa: PLC0415

        class _MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = _MS()
        m.dwLength = ctypes.sizeof(_MS)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            return None
        return round(m.ullAvailPhys / 1e9, 2)
    except Exception:                                              # noqa: BLE001
        return None


def run_opportunities(*, runner: Callable[..., Any] | None = None,
                      log_path: Path | None = None,
                      free_gb: Callable[[], Optional[float]] | None = None) -> dict:
    row: dict = {"job": "opportunities"}
    cmd = [_child_python(), "-m", "scripts.opportunities_build"]
    gb = (free_gb or _free_gb)()
    row["free_gb"] = gb
    row["min_free_gb"] = OPPORTUNITIES_MIN_FREE_GB
    if gb is None:
        row.update(action="refused", why="free memory could not be read; the build was not started")
        return log(row, log_path or OPPORTUNITIES_LOG)
    if gb < OPPORTUNITIES_MIN_FREE_GB:
        row.update(action="refused", why=(f"{gb:.1f} GB free < {OPPORTUNITIES_MIN_FREE_GB:.1f} GB floor; the "
                                          f"build was not started (the sim owner shares this window)"))
        return log(row, log_path or OPPORTUNITIES_LOG)
    try:
        runner = runner or subprocess.run
        r = runner(cmd, cwd=str(REPO), capture_output=True, text=True, timeout=OPPORTUNITIES_TIMEOUT_S,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        tail = [ln for ln in (r.stdout or "").splitlines() if ln.strip()][-1:]
        row["rc"] = r.returncode
        row["line"] = tail[0][:300] if tail else None
        if r.returncode != 0:
            row["action"] = "refused"
            row["why"] = (f"opportunities_build exited {r.returncode}: "
                          f"{((r.stderr or '').strip().splitlines() or ['no stderr'])[-1][:300]}")
        elif not (tail and tail[0].startswith("wrote ")):
            row["action"] = "refused"
            row["why"] = "opportunities_build exited 0 but printed no `wrote <receipt>` line (nothing written)"
        else:
            row["action"] = "ok"
    except subprocess.TimeoutExpired:
        row.update(action="refused", why=f"opportunities_build ran past {OPPORTUNITIES_TIMEOUT_S // 60} min")
    except Exception as exc:                                       # noqa: BLE001
        row.update(action="refused", why=f"{type(exc).__name__}: {str(exc)[:300]}")
    return log(row, log_path or OPPORTUNITIES_LOG)


RESULTS_LOG = KEEPER_DIR / "results_voice.jsonl"


def run_results_voice(*, job: Callable[[], dict] | None = None,
                      log_path: Path | None = None) -> dict:
    """The results-first statement (`backend.services.results_voice`, 2026-10-07) over
    the newest roi + book_dna pair. `scripts/daily_pass.py` step `paper_accounts` runs
    it right after it writes those receipts; the catalog firing runs it again BEFORE
    the public receipts so /arena carries it. A failure is a SKIP row, never a raise."""
    row: dict = {"job": "results_voice"}
    try:
        if job is None:
            from backend.services import results_voice as RV          # noqa: PLC0415
            job = RV.safe_run
        out = job()
        row.update(status=out.get("status"), run_id=out.get("run_id"), md=out.get("md"),
                   line=out.get("line"))
        row["action"] = "ok" if out.get("status") == "ok" else "skip"
    except Exception as exc:                                       # noqa: BLE001
        row.update(action="skip", line=f"SKIP results_voice: {type(exc).__name__}: {str(exc)[:300]}")
    return log(row, log_path or RESULTS_LOG)


def run_publish_receipts(*, job: Callable[[], dict] | None = None,
                         log_path: Path | None = None) -> dict:
    row: dict = {"job": "publish_receipts"}
    try:
        if job is None:
            from backend.services import publish_receipts as PR     # noqa: PLC0415
            job = PR.publish
        out = job()
        row.update(status=out.get("status"), why=out.get("why"), written=out.get("written"),
                   total_bytes=out.get("total_bytes"), max_bytes=out.get("max_bytes"),
                   published=out.get("published"), refused=out.get("refused"), missing=out.get("missing"))
        row["action"] = {"OK": "ok", "DEGRADED": "degraded"}.get(str(out.get("status")), "refused")
    except Exception as exc:                                       # noqa: BLE001
        row.update(action="refused", why=f"{type(exc).__name__}: {str(exc)[:300]}")
    return log(row, log_path or PUBLISH_LOG)


PUBLISH_COMMIT_LOG = KEEPER_DIR / "publish_commit.jsonl"


def run_publish_commit(*, job: Callable[[], dict] | None = None,
                       log_path: Path | None = None) -> dict:
    """Review C15 H1: the step that actually PUBLISHES -- commit ONLY public_receipts/ on
    `main` and push. Its own receipt row (COMMITTED / REFUSED with reasons) is written by
    `publish_receipts.commit_public_receipts`; this wrapper maps it to an action."""
    try:
        if job is None:
            from backend.services import publish_receipts as PR     # noqa: PLC0415
            out = PR.commit_public_receipts(log_path=log_path or PUBLISH_COMMIT_LOG)
        else:
            out = job()
    except Exception as exc:                                       # noqa: BLE001
        out = log({"job": "publish_commit", "status": "REFUSED",
                   "reasons": [f"{type(exc).__name__}: {str(exc)[:300]}"]}, log_path or PUBLISH_COMMIT_LOG)
    out["action"] = "ok" if out.get("status") == "COMMITTED" and out.get("pushed") is not False else "refused"
    return out


# ================================================================ assets (2026-10-07 chunk)
#
# WHY. The owner wants the public pictures to refresh "maybe live, maybe once a week, based
# on the winners" without a human remembering to run three commands. `render_public_assets
# --bump-pin` already does step 1 (pick the newest receipt pair, re-render, write its own
# refresh receipt, REFUSE loud on an older/identical pin, a missing LIVE featured account or a
# text-budget failure); this job is steps 2-3: gate the bump on `test_public_assets.py` (a
# bump that renders but fails its own pinning test is never committed), then commit ONLY the
# generator, the rendered assets, the motion page, the README and the refresh receipt on
# `main` and push -- the SAME H1 guards as `publish_commit` (via `publish_receipts.commit_
# paths`, the generalised form of its one-folder pattern). A failure at ANY step is a SKIP
# line in `assets.jsonl`, never a raised exception and never a partial commit.

ASSETS_LOG = KEEPER_DIR / "assets.jsonl"
#: Committed on every successful bump, beside the run's own refresh receipt (added at call
#: time: `backend/data/optimus/paper_accounts/public_assets_refresh_<run_id>.json`).
# README.md is included although the chunk's own wording names only the generator, the
# assets and the motion page: `render_public_assets.update_readme_results_block` rewrites its
# results-panel block on every bump, and leaving it out would leave README.md permanently
# dirty (and SKIP every following week's job on an already-dirty index).
ASSETS_COMMIT_PATHS = ("scripts/render_public_assets.py", "docs/assets", "docs/design/aegis_front_page.html",
                      "README.md")


def run_assets(*, bump: Callable[..., int] | None = None,
               pytest_runner: Callable[..., Any] | None = None,
               commit: Callable[..., dict] | None = None, log_path: Path | None = None) -> dict:
    row: dict = {"job": "assets"}
    try:
        from scripts import render_public_assets as RPA                # noqa: PLC0415
    except Exception as exc:                                           # noqa: BLE001
        row.update(action="skip", why=f"could not import render_public_assets: "
                                      f"{type(exc).__name__}: {str(exc)[:300]}")
        return log(row, log_path or ASSETS_LOG)
    old_id = RPA.RESULTS_RUN_ID
    try:
        rc = (bump or RPA.bump_pin)()
    except Exception as exc:                                           # noqa: BLE001
        row.update(action="skip", why=f"bump_pin raised {type(exc).__name__}: {str(exc)[:300]}")
        return log(row, log_path or ASSETS_LOG)
    new_id = RPA.RESULTS_RUN_ID
    row.update(bump_rc=rc, old_run_id=old_id, new_run_id=new_id)
    if rc == 2:
        row.update(action="skip", why="bump_pin refused (the newest receipt pair is not newer than the "
                                      "pinned one, a featured family has no LIVE strategy account, or a "
                                      "text budget failed); nothing rendered, nothing to commit")
        return log(row, log_path or ASSETS_LOG)
    if rc != 0:
        row.update(action="skip", why=f"bump_pin exited {rc}")
        return log(row, log_path or ASSETS_LOG)
    try:
        runner = pytest_runner or subprocess.run
        r = runner([_child_python(), "-m", "pytest", "backend/tests/test_public_assets.py", "-q"],
                  cwd=str(REPO), capture_output=True, text=True, timeout=180,
                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        rc_test = int(getattr(r, "returncode", 1))
        row["pytest_rc"] = rc_test
        if rc_test != 0:
            tail = [ln for ln in str(getattr(r, "stdout", "") or "").splitlines() if ln.strip()][-8:]
            row.update(action="skip", why=f"test_public_assets.py failed (rc {rc_test}); the bump stands "
                                          f"but is NOT committed: {tail}")
            return log(row, log_path or ASSETS_LOG)
    except Exception as exc:                                           # noqa: BLE001
        row.update(action="skip", why=f"pytest raised {type(exc).__name__}: {str(exc)[:300]}")
        return log(row, log_path or ASSETS_LOG)
    receipt_rel = (RPA.PAPER_DIR / f"public_assets_refresh_{new_id}.json").resolve().relative_to(
        RPA.REPO.resolve()).as_posix()
    try:
        commit = commit or (lambda **kw: __import__(
            "backend.services.publish_receipts", fromlist=["commit_paths"]).commit_paths(**kw))
        out = commit(paths=(*ASSETS_COMMIT_PATHS, receipt_rel),
                     message=f"public assets refresh {new_id} (bumped pin {old_id} -> {new_id}; "
                             f"data + generator only)",
                     log_path=KEEPER_DIR / "assets_commit.jsonl")
    except Exception as exc:                                           # noqa: BLE001
        row.update(action="skip", why=f"commit raised {type(exc).__name__}: {str(exc)[:300]}")
        return log(row, log_path or ASSETS_LOG)
    row["commit"] = {k: out.get(k) for k in ("status", "commit", "pushed", "push_refused", "reasons", "n_files")}
    row["action"] = "ok" if out.get("status") == "COMMITTED" and out.get("pushed") is not False else "skip"
    if row["action"] == "skip":
        row["why"] = out.get("reasons") or out.get("push_refused") or "commit did not complete"
    voice = RPA.PAPER_DIR / f"results_voice_{new_id}.md"
    if voice.is_file():
        row["results_voice"] = voice.resolve().relative_to(RPA.REPO.resolve()).as_posix()
    return log(row, log_path or ASSETS_LOG)


# ================================================================ owners (C8)
#
# WHY (chunk C8, 2026-10-07). Two jobs had NO scheduled caller:
#  * the analyst-target pull (`scripts.pull_analyst_targets`, ~60-80 min) last
#    ran 2026-09-29 by hand; ROT5_DIR refuses its inputs past 14 days;
#  * `tools/refresh_aegis.py` in the sibling Optimus repo -- the brain page was
#    23 days old and every session's `brain_query` read a September corpus.
# Each firing writes ONE row to its own receipt series (`task_keeper/
# analyst.jsonl`, `task_keeper/brain.jsonl`), which `task_receipts` reads.
# A step that cannot run is a REFUSED row with its reason, never a silent exit.

TASK_ANALYST = "AegisAnalystPull"
TASK_BRAIN = "AegisBrainRefresh"
ANALYST_LOG = KEEPER_DIR / "analyst.jsonl"
BRAIN_LOG = KEEPER_DIR / "brain.jsonl"


def _child_python() -> str:
    """A console python for a child (pythonw has no stdout to hand down)."""
    p = REPO / ".venv" / "Scripts" / "python.exe"
    return str(p) if p.exists() else sys.executable


def analyst_gate(now_utc: datetime) -> dict:
    """Refuse while the US regular session is open: an 80-minute vendor crawl
    competes with the live loops for the same rate limit."""
    from backend.services import system_health as SH               # noqa: PLC0415
    if SH.in_session_hours(now_utc):
        return {"action": "refused",
                "why": (f"US session is open ({SH._et(now_utc):%Y-%m-%d %H:%M} ET); the weekly "
                        f"pull runs outside regular hours")}
    return {"action": "run"}


def run_analyst_pull(*, now_utc: datetime | None = None,
                     runner: Callable[..., Any] | None = None,
                     log_path: Path | None = None) -> dict:
    now_utc = now_utc or _now()
    row: dict = {"job": "analyst", **analyst_gate(now_utc)}
    if row["action"] == "run":
        KEEPER_DIR.mkdir(parents=True, exist_ok=True)
        out = KEEPER_DIR / f"analyst_pull_{now_utc:%Y%m%dT%H%M%SZ}.log"
        argv = [_child_python(), "-m", "scripts.pull_analyst_targets", "--universe", "bars"]
        try:
            with open(out, "w", encoding="utf-8") as fh:
                r = (runner or subprocess.run)(
                    argv, cwd=str(REPO), stdout=fh, stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    timeout=float(_config.ANALYST_PULL_TIMEOUT_MIN) * 60,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            rc = int(getattr(r, "returncode", 1))
            row.update(action="ok" if rc == 0 else "failed", rc=rc, log=out.name,
                       why="" if rc == 0 else f"pull_analyst_targets exited {rc}; see {out.name}")
        except subprocess.TimeoutExpired:
            row.update(action="failed",
                       why=f"timed out after {_config.ANALYST_PULL_TIMEOUT_MIN} min")
        except Exception as exc:                                   # noqa: BLE001
            row.update(action="refused",
                       why=f"could not start: {type(exc).__name__}: {str(exc)[:200]}")
    return log(row, log_path or ANALYST_LOG)


# ================================================================ public flow (C16)
#
# WHY (chunk C16, 2026-10-07). Three SENSORS with provenance + latency, never a
# trade signal on their own: USAspending contract transactions for the crosswalk
# recipients (DAILY, a 14-day incremental window; rows dedupe on the
# transaction id) plus the agency x month obligation snapshot; Senate LDA
# lobbying filings (WEEKLY: filings are quarterly; due when the newest LDA
# receipt -- dated by its OWN stamp, never mtime -- is LDA_EVERY_DAYS old); the
# crypto risk-appetite snapshot (daily). Each step that cannot run is a REFUSED
# entry with its reason; zero new USAspending rows on a weekday is DEGRADED.

TASK_PUBLIC_FLOW = "AegisPublicFlow"
PUBLIC_FLOW_LOG = KEEPER_DIR / "public_flow.jsonl"


def lda_due(now_utc: datetime, last: Optional[dict]) -> bool:
    """PURE. LDA runs when no receipt exists or the newest is LDA_EVERY_DAYS old."""
    if not last:
        return True
    try:
        t = datetime.fromisoformat(str(last.get("written_utc")))
    except (TypeError, ValueError):
        return True
    return (now_utc - t).total_seconds() >= float(_config.LDA_EVERY_DAYS) * 86400


def run_public_flow(*, now_utc: datetime | None = None, steps: dict | None = None,
                    log_path: Path | None = None) -> dict:
    now_utc = now_utc or _now()
    row: dict = {"job": "public_flow"}
    if steps is None:
        from backend.services import crypto_market as CM            # noqa: PLC0415
        from backend.services import lobbying_lda as LDA             # noqa: PLC0415
        from backend.services import public_flow_common as PF        # noqa: PLC0415
        from backend.services import usaspending_awards as USA       # noqa: PLC0415
        steps = {"usaspending": lambda: USA.pull(),
                 "usaspending_agency_months": lambda: USA.pull_agency_months(),
                 "lda": (lambda: LDA.pull()) if lda_due(now_utc, PF.last_receipt(LDA.SOURCE)) else None,
                 "crypto": lambda: CM.risk_sensor_snapshot()}
    statuses = []
    for name, fn in steps.items():
        if fn is None:
            row[name] = {"status": "NOT_DUE", "why": f"last receipt younger than {_config.LDA_EVERY_DAYS} days"}
            continue
        try:
            r = fn()
            row[name] = {k: r.get(k) for k in ("status", "rows_added", "rows_read", "receipt",
                                                 "refusals") if k in r}
        except Exception as exc:                                   # noqa: BLE001
            row[name] = {"status": "REFUSED", "why": f"{type(exc).__name__}: {str(exc)[:300]}"}
        statuses.append(row[name].get("status"))
    row["action"] = ("refused" if statuses and all(s == "REFUSED" for s in statuses) else
                     "degraded" if any(s in ("REFUSED", "DEGRADED") for s in statuses) else "ok")
    return log(row, log_path or PUBLIC_FLOW_LOG)


# ================================================================ research lane (Q12, 2026-10-07)
#
# WEEKLY, ADDITIVE: research-intake cards gain literature evidence through the
# academic lane (`backend/services/research_instruments.py`,
# `scripts/research_lane.py --due`), never more than
# `QUERY_PLANNER_ACADEMIC_QUERIES_DAY` queries/day, $0, keyless. This is its
# OWN owner, same shape as `analyst`/`public_flow` above -- `daily_pass.py` is
# not touched.

TASK_RESEARCH = "AegisResearchLane"
RESEARCH_LANE_LOG = KEEPER_DIR / "research_lane.jsonl"


def research_lane_due(now_utc: datetime, last_utc: Optional[str]) -> bool:
    """PURE. No prior probe, or the newest one is RESEARCH_LANE_EVERY_DAYS old."""
    if not last_utc:
        return True
    try:
        t = datetime.fromisoformat(str(last_utc))
    except (TypeError, ValueError):
        return True
    t = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    return (now_utc - t).total_seconds() >= float(_config.RESEARCH_LANE_EVERY_DAYS) * 86400


def run_research_lane(*, now_utc: datetime | None = None, runner: Callable[..., Any] | None = None,
                      log_path: Path | None = None, last_utc: str | None = "unset") -> dict:
    now_utc = now_utc or _now()
    from backend.services import research_instruments as RI       # noqa: PLC0415
    last = RI.last_probe_utc() if last_utc == "unset" else last_utc
    row: dict = {"job": "research_lane"}
    if not research_lane_due(now_utc, last):
        row.update(action="not_due", why=f"last probe {last} < "
                                         f"{_config.RESEARCH_LANE_EVERY_DAYS:g} days ago")
        return log(row, log_path or RESEARCH_LANE_LOG)
    KEEPER_DIR.mkdir(parents=True, exist_ok=True)
    out = KEEPER_DIR / f"research_lane_{now_utc:%Y%m%dT%H%M%SZ}.log"
    argv = [_child_python(), "-m", "scripts.research_lane", "--due"]
    try:
        with open(out, "w", encoding="utf-8") as fh:
            r = (runner or subprocess.run)(
                argv, cwd=str(REPO), stdout=fh, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, timeout=float(_config.RESEARCH_LANE_TIMEOUT_MIN) * 60,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        rc = int(getattr(r, "returncode", 1))
        row.update(action="ok" if rc == 0 else "failed", rc=rc, log=out.name,
                   why="" if rc == 0 else f"research_lane exited {rc}; see {out.name}")
    except subprocess.TimeoutExpired:
        row.update(action="failed", why=f"timed out after {_config.RESEARCH_LANE_TIMEOUT_MIN} min")
    except Exception as exc:                                       # noqa: BLE001
        row.update(action="refused", why=f"could not start: {type(exc).__name__}: {str(exc)[:200]}")
    return log(row, log_path or RESEARCH_LANE_LOG)


def optimus_root() -> Path:
    return Path(os.getenv("OPTIMUS_ROOT", str(REPO.parent / "optimus")))


def run_brain_refresh(*, root: Path | None = None, runner: Callable[..., Any] | None = None,
                      log_path: Path | None = None) -> dict:
    root = Path(root or optimus_root())
    tool = root / "tools" / "refresh_aegis.py"
    py = root / ".venv" / "Scripts" / "python.exe"
    row: dict = {"job": "brain"}
    if not tool.exists():
        row.update(action="refused", why=("tools/refresh_aegis.py not found in the Optimus repo "
                                          "(OPTIMUS_ROOT or ../optimus)"))
        return log(row, log_path or BRAIN_LOG)
    if not py.exists():
        row.update(action="refused", why=("the Optimus repo has no .venv python; its ingest "
                                          "needs that environment"))
        return log(row, log_path or BRAIN_LOG)
    try:
        r = (runner or subprocess.run)(
            [str(py), str(tool)], cwd=str(root), capture_output=True, text=True,
            encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
            timeout=float(_config.BRAIN_REFRESH_TIMEOUT_MIN) * 60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        rc = int(getattr(r, "returncode", 1))
        lines = [ln for ln in str(getattr(r, "stdout", "") or "").splitlines() if ln.strip()]
        fails = [ln for ln in lines if ln.startswith("[FAIL]")]
        row.update(action="ok" if rc == 0 else "failed", rc=rc,
                   n_ok=sum(1 for ln in lines if ln.startswith("[ok]")), n_fail=len(fails),
                   summary=(lines[-1] if lines else "no output")[:200],
                   why="" if rc == 0 else ("; ".join(fails)[:400] or f"exit {rc}"))
    except subprocess.TimeoutExpired:
        row.update(action="failed", why=f"timed out after {_config.BRAIN_REFRESH_TIMEOUT_MIN} min")
    except Exception as exc:                                       # noqa: BLE001
        row.update(action="refused", why=f"could not start: {type(exc).__name__}: {str(exc)[:200]}")
    return log(row, log_path or BRAIN_LOG)


def owner_registration_ps() -> str:
    """PowerShell registering the two C8 owners. Printed by `register-owners`,
    run by `register-owners --apply`. Times are this PC's local (HKT) clock."""
    pyw = REPO / ".venv" / "Scripts" / "pythonw.exe"
    return "\n".join([
        "$S = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries "
        "-DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 3)",
        "# weekly analyst-target pull: Sunday 10:00 HKT (Saturday night ET; no session)",
        f"$a = New-ScheduledTaskAction -Execute '{pyw}' -Argument '-m scripts.task_keeper analyst' "
        f"-WorkingDirectory '{REPO}'",
        "Register-ScheduledTask -TaskName '" + TASK_ANALYST + "' -Action $a -Settings $S -Force "
        "-Trigger @(New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 10:00)",
        "# daily Optimus brain refresh: 05:45 HKT",
        f"$a = New-ScheduledTaskAction -Execute '{pyw}' -Argument '-m scripts.task_keeper brain' "
        f"-WorkingDirectory '{REPO}'",
        "Register-ScheduledTask -TaskName '" + TASK_BRAIN + "' -Action $a -Settings $S -Force "
        "-Trigger @(New-ScheduledTaskTrigger -Daily -At 05:45)",
        "# C16 public-flow sensors: 06:15 HKT daily (US evening; LDA weekly inside the job)",
        f"$a = New-ScheduledTaskAction -Execute '{pyw}' -Argument '-m scripts.task_keeper public_flow' "
        f"-WorkingDirectory '{REPO}'",
        "Register-ScheduledTask -TaskName '" + TASK_PUBLIC_FLOW + "' -Action $a -Settings $S -Force "
        "-Trigger @(New-ScheduledTaskTrigger -Daily -At 06:15)",
        "# Q12 academic lane: weekly, Sunday 11:00 HKT ($0, keyless; the job itself re-checks "
        "RESEARCH_LANE_EVERY_DAYS and is a no-op most weeks)",
        f"$a = New-ScheduledTaskAction -Execute '{pyw}' -Argument '-m scripts.task_keeper research' "
        f"-WorkingDirectory '{REPO}'",
        "Register-ScheduledTask -TaskName '" + TASK_RESEARCH + "' -Action $a -Settings $S -Force "
        "-Trigger @(New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 11:00)",
    ])


def register_owners(apply: bool = False) -> int:
    ps = owner_registration_ps()
    print(ps)
    if not apply:
        return 0
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True,
                       text=True, timeout=120,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    print(r.stdout[-2000:], r.stderr[-2000:])
    return int(r.returncode)


# ================================================================ register

_PS_WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _assets_day_name() -> str:
    """`config.PUBLIC_ASSETS_REFRESH_WEEKDAY` (Mon=0..Sun=6) as the PowerShell day name."""
    return _PS_WEEKDAY_NAMES[int(getattr(_config, "PUBLIC_ASSETS_REFRESH_WEEKDAY", 5)) % 7]


def _assets_hhmm_colon() -> str:
    """`config.PUBLIC_ASSETS_REFRESH_HHMM` ("0900") as "09:00"."""
    hhmm = str(getattr(_config, "PUBLIC_ASSETS_REFRESH_HHMM", "0900")).zfill(4)
    return f"{hhmm[:2]}:{hhmm[2:]}"


def registration_ps() -> str:
    """PowerShell that (re)registers the tasks (reader, catch-up, sim owner, catalog, and the
    weekly public-assets refresh). Printed by `register`.

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
        "# the data catalog + ledger archival, then (C15) the Opportunity Explorer rebuild and the",
        "# sanitised public receipts: once a day AFTER the daily pass (06:30, bars + analyst",
        "# snapshot); `catchup` starts it if the PC slept",
        "$SC = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries "
        "-DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)",
        f"$a = New-ScheduledTaskAction -Execute '{pyw}' -Argument \"-m scripts.task_keeper catalog\" "
        f"-WorkingDirectory '{REPO}'",
        "Register-ScheduledTask -TaskName '" + TASK_CATALOG + "' -Action $a -Settings $SC -Force "
        "-Trigger @(New-ScheduledTaskTrigger -Daily -At 09:00)",
        "# the public-assets refresh: weekly, AFTER the daily catalog path on the same day "
        f"(config.PUBLIC_ASSETS_REFRESH_WEEKDAY/_HHMM = {_assets_day_name()} "
        f"{_assets_hhmm_colon()} HKT)",
        f"$a = New-ScheduledTaskAction -Execute '{pyw}' -Argument \"-m scripts.task_keeper assets\" "
        f"-WorkingDirectory '{REPO}'",
        "Register-ScheduledTask -TaskName '" + TASK_ASSETS + "' -Action $a -Settings $SC -Force "
        f"-Trigger @(New-ScheduledTaskTrigger -Weekly -DaysOfWeek {_assets_day_name()} "
        f"-At {_assets_hhmm_colon()})",
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
    ap.add_argument("job", choices=("reader", "catchup", "sim", "status", "register", "catalog",
                                   "regret", "snowball", "opportunities", "publish", "publish_commit",
                                   "analyst", "brain", "register-owners", "public_flow", "research",
                                   "results", "assets"))
    ap.add_argument("--apply", action="store_true",
                    help="register-owners: run the registration, not only print it")
    a = ap.parse_args(argv)
    if a.job == "register-owners":
        return register_owners(apply=a.apply)
    if a.job == "public_flow":
        out = run_public_flow()
        print(json.dumps(out, default=str))
        return 2 if out.get("action") == "refused" else 0
    if a.job == "research":
        out = run_research_lane()
        print(json.dumps(out, default=str))
        return 0 if out.get("action") in ("ok", "not_due") else 2
    if a.job in ("analyst", "brain"):
        out = run_analyst_pull() if a.job == "analyst" else run_brain_refresh()
        print(json.dumps(out, default=str))
        return 0 if out.get("action") == "ok" else 2
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
        # C18: the daily snowball grade rides the catalog's daily firing; its own
        # keeper row; it never changes the catalog's exit code.
        print(json.dumps(run_snowball(), default=str))
        # C15: the Opportunity Explorer rebuild, then the public receipts LAST (they copy what
        # the steps before them wrote). Own keeper rows; never the catalog's exit code.
        print(json.dumps(run_opportunities(), default=str))
        # 2026-10-07: the results voice BEFORE the public receipts, so /arena carries it
        print(json.dumps(run_results_voice(), default=str))
        print(json.dumps(run_publish_receipts(), default=str))
        # C15 H1: LAST, the step that makes the pages public (it refuses off `main`)
        print(json.dumps(run_publish_commit(), default=str))
        return 2 if out.get("action") == "refused" else 0
    if a.job in ("opportunities", "publish", "publish_commit", "assets"):
        out = {"opportunities": run_opportunities, "publish": run_publish_receipts,
               "publish_commit": run_publish_commit, "assets": run_assets}[a.job]()
        print(json.dumps(out, default=str))
        return 2 if out.get("action") in ("refused", "skip") else 0
    if a.job == "results":
        out = run_results_voice()
        print(json.dumps(out, default=str))
        return 0 if out.get("action") == "ok" else 2
    if a.job == "snowball":
        out = run_snowball()
        print(json.dumps(out, default=str))
        return 2 if out.get("action") == "refused" else 0
    if a.job == "regret":
        out = run_regret()
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
