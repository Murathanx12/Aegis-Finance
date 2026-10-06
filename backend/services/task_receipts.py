"""Every scheduled task judged by the RECEIPT it must advance (chunk C8, 2026-10-07).

WHY
===
Until tonight the `task:*` health rows read `schtasks`' "Last Result", which is
the exit code of `cmd.exe` or `pythonw.exe`, not of the job. Seventeen rows said
UNKNOWN every night. Behind them, the nn_lab nightly wrote six non-OK receipts in
a row (2026-10-02 -> 10-06) and nothing turned red. A task the scheduler fires
is not a task that produces, so each task is now judged ONLY by what it wrote.

`TASK_RECEIPT` maps every task name to a reader. The reader returns the newest
receipt's own stamp (never an mtime: CLAUDE.md protocol item 7), its status
(OK / REFUSED / DEGRADED / STOPPED), a reason, and a SUBSTANCE string: the
receipt with its stamps and run ids removed. `judge()` turns that into one
state:

* ``ALIVE_PROGRESSING``   -- a fresh receipt whose substance moved
* ``ALIVE_IDLE_EXPECTED`` -- fresh enough, inside a DECLARED idle window (no XNYS
                             session today, not yet due, the producer's own
                             out-of-window flag); the window is named
* ``DEGRADED``            -- fresh, but something is wrong (errored steps, no
                             scheduled task to write the next one, retired task)
* ``STALE``               -- older than its declared cadence, OR the same
                             substance for too long ("same output for X h")
* ``REFUSED``             -- the newest receipt is a refusal, and it says why
* ``DEAD``                -- nothing is scheduled AND the receipt is old
* ``UNKNOWN``             -- only when the receipt cannot be read on this
                             machine at all, and it says why

The coarse `verdict` kept on every row (ALIVE / STALE / REFUSED / DEAD /
UNKNOWN / STOPPED_BY_OPERATOR) is what existing consumers compare against; the
fine `state` above rides beside it. Cadences live in
`config.HEALTH_TASK_CADENCE_H`; the same-substance rule is
`config.HEALTH_PROGRESS_SAME_HASH_PROBES`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from backend import config as _config

#: fine state -> coarse verdict (what `counts`, `exit_code`, the daily pass and
#: the Telegram brief already understand)
COARSE = {"ALIVE_PROGRESSING": "ALIVE", "ALIVE_IDLE_EXPECTED": "ALIVE",
          "DEGRADED": "STALE", "STALE": "STALE", "REFUSED": "REFUSED", "DEAD": "DEAD",
          "UNKNOWN": "UNKNOWN", "STOPPED_BY_OPERATOR": "STOPPED_BY_OPERATOR"}
STATES = tuple(COARSE)

#: schtasks' "Last Result" for a task that has never run (SCHED_S_TASK_HAS_NOT_RUN)
NEVER_RAN_RC = "267011"

#: keys whose values are clocks or ids, removed before the substance hash
_VOLATILE = re.compile(r"(utc|stamp|run_id|_at$|^at$|time|started|finished|written|^now|"
                       r"elapsed|runtime|wall|seconds|^pid$|^t$|age|^id$|lock|free_ram|free_gb)",
                       re.I)


# ═══════════════════════════════════════════════════════════════ reading

@dataclass
class Reading:
    stamp: Optional[datetime] = None
    status: str = "OK"               # OK / REFUSED / DEGRADED / STOPPED
    reason: str = ""
    substance: Optional[str] = None  # None = the hash rule is off (see `hash_off`)
    proof: str = ""
    detail: str = ""
    idle_reason: Optional[str] = None
    unknown_reason: Optional[str] = None
    delegated: Optional[str] = None  # a coarse verdict another probe already judged


@dataclass(frozen=True)
class TaskSpec:
    reader: Callable[[Any, Optional[dict]], Reading]
    receipt: str                     # where the receipt lives, for the row and the docs
    session_only: bool = False       # produces only for XNYS sessions
    hash_off: str = ""               # why the same-substance rule does not apply
    retired: bool = False
    #: judged only when the scheduler actually holds the task (a command the repo
    #: PRINTS for the owner, or a job a Startup script owns instead)
    registered_only: bool = False


def parse_stamp(v: Any) -> Optional[datetime]:
    """ISO, a date, or the compact `20261006T163002Z` the receipts use."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    s = str(v).strip()
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z?", s)
    if m:
        return datetime(*map(int, m.groups()), tzinfo=timezone.utc)
    try:
        if len(s) == 10:
            d = date.fromisoformat(s)
            return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def substance(obj: Any) -> str:
    """The receipt with every clock and id removed, as canonical JSON."""
    def strip(o):
        if isinstance(o, dict):
            return {k: strip(v) for k, v in sorted(o.items()) if not _VOLATILE.search(str(k))}
        if isinstance(o, list):
            return [strip(x) for x in o]
        return o
    return json.dumps(strip(obj), sort_keys=True, default=str)


def _read(p: Path) -> Any:
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def _newest(folder: Path, pattern: str) -> tuple[Optional[Path], Any]:
    """The newest receipt by NAME (the producer's stamp), never by mtime."""
    try:
        files = sorted(Path(folder).glob(pattern))
    except OSError:
        return None, None
    for p in reversed(files):
        d = _read(p)
        if d is not None:
            return p, d
    return (files[-1] if files else None), None


def _last_row(p: Path, pred: Callable[[dict], bool] = lambda r: True,
              nbytes: int = 262144) -> Optional[dict]:
    from backend.services import system_health as SH                # noqa: PLC0415
    for line in reversed(SH._tail_lines(Path(p), nbytes)):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict) and pred(r):
            return r
    return None


def _none(where: str) -> Reading:
    """No receipt at all."""
    return Reading(stamp=None, detail=f"no receipt at {where}", proof=where)


# ═══════════════════════════════════════════════════════════════ readers

def r_daily_pass(ctx, task) -> Reading:
    from backend.services import system_health as SH                # noqa: PLC0415
    day, d = SH._newest_daily_pass(ctx, back=8)
    if not d:
        return _none("night_factory_<d>/daily_pass_<d>.json")
    steps = [s for s in d.get("steps") or [] if isinstance(s, dict)]
    stamps = [t for t in (parse_stamp(s.get("utc")) for s in steps) if t]
    t = max(stamps) if stamps else parse_stamp(d.get("finished_utc") or d.get("started_utc"))
    errs = [s.get("step") for s in steps if s.get("status") in ("error", "timeout")]
    return Reading(stamp=t, status="DEGRADED" if errs else "OK",
                   reason=f"errored steps: {errs}" if errs else "",
                   substance=substance(steps), proof=f"daily_pass_{day}.json steps[*].utc",
                   detail=f"daily_pass {day}: {str(d.get('headline') or '')[:120]}")


def _delegate(fn_name: str, label: str):
    def reader(ctx, task) -> Reading:
        from backend.services import system_health as SH            # noqa: PLC0415
        r = getattr(SH, fn_name)(ctx)
        return Reading(stamp=SH._ts(r.evidence_utc), delegated=r.verdict,
                       substance=None, proof=r.proof or label,
                       detail=f"{label}: {r.detail}",
                       reason=r.detail if r.verdict != "ALIVE" else "")
    return reader


def r_nn_lab(ctx, task) -> Reading:
    from nn_lab import health as NH                                  # noqa: PLC0415
    rd = ctx.path("nn_lab_receipts", ctx.optimus_dir / "nn_lab" / "receipts")
    c = NH.health_contract(receipt_dir=rd, now=ctx.now)
    proof = f"nn_lab.health_contract(): {c.get('receipt') or 'no receipt'}"
    if c.get("receipt") is None:
        return _none("nn_lab/receipts/nightly_*.json")
    age = c.get("age_hours")
    t = ctx.now - timedelta(hours=float(age)) if age is not None else None
    st = c.get("status")
    if st == "REFUSED":
        # a refusal is judged fresh/old like any receipt; the contract's line names it
        return Reading(stamp=t or ctx.now, status="REFUSED", reason=c.get("line", ""),
                       substance=None, proof=proof, detail=c.get("line", ""))
    return Reading(stamp=t, status="OK", substance=f"{c.get('receipt')}|{c.get('receipt_status')}",
                   proof=proof, detail=c.get("line", ""))


def r_sim_owner(ctx, task) -> Reading:
    p = ctx.optimus_dir / "sim" / "owner.jsonl"
    row = _last_row(p)
    if row is None:
        return _none("sim/owner.jsonl")
    a = str(row.get("action"))
    status = {"refused": "REFUSED", "paused": "STOPPED", "stopped_by_operator": "STOPPED"}.get(a, "OK")
    return Reading(stamp=parse_stamp(row.get("utc")), status=status, reason=str(row.get("why") or ""),
                   proof="sim/owner.jsonl[-1].utc",
                   detail=f"owner {a}: {str(row.get('why') or '')[:140]}")


def r_catalog(ctx, task) -> Reading:
    p, d = _newest(ctx.optimus_dir / "data_catalog", "catalog_*.json")
    if not isinstance(d, dict):
        return _none("data_catalog/catalog_*.json")
    bad = str(d.get("status") or "").upper() == "REFUSED"
    return Reading(stamp=parse_stamp(d.get("utc") or d.get("run_id")),
                   status="REFUSED" if bad else "OK", reason=str(d.get("why") or ""),
                   substance=substance(d.get("summary")), proof=f"data_catalog/{p.name} utc",
                   detail=f"catalog {p.name}: {str(d.get('summary'))[:120]}")


def r_rehearsal(ctx, task) -> Reading:
    row = _last_row(ctx.optimus_dir / "contest" / "rehearsal" / "runs.jsonl")
    if row is None:
        return _none("contest/rehearsal/runs.jsonl")
    t = parse_stamp(row.get("finished_utc") or row.get("started_utc"))
    sheet = row.get("sheet")
    err = row.get("error")
    return Reading(stamp=t, status="DEGRADED" if err else "OK", reason=str(err or ""),
                   substance=substance({"sheet": sheet, "grade": row.get("grade"), "day": row.get("day")}),
                   proof="contest/rehearsal/runs.jsonl[-1]",
                   detail=f"rehearsal {row.get('day')}: sheet "
                          + (str((sheet or {}).get('sheet_code')) if isinstance(sheet, dict) else str(sheet)[:100]))


def _contest_live_first_day() -> Optional[date]:
    try:
        from scripts import contest_calendar as cc                    # noqa: PLC0415
        return cc.CONTEST_START - timedelta(days=3)
    except Exception:                                                 # noqa: BLE001
        return None


def r_contest_desk(ctx, task) -> Reading:
    live = ctx.optimus_dir / "contest" / "live"
    run = _last_row(live / "runs.jsonl")
    rp, ref = _newest(live / "refusals", "live_gate_*.json")
    t_run = parse_stamp((run or {}).get("finished_utc") or (run or {}).get("started_utc"))
    t_ref = parse_stamp((ref or {}).get("written_utc")) if isinstance(ref, dict) else None
    if t_ref and (t_run is None or t_ref >= t_run):
        why = " | ".join(ref.get("reasons") or []) or "gate refused"
        return Reading(stamp=t_ref, status="REFUSED", reason=why, substance=None,
                       proof=f"contest/live/refusals/{rp.name}", detail=f"live gate REFUSED: {why[:160]}")
    if t_run:
        return Reading(stamp=t_run, status="OK", substance=substance(run),
                       proof="contest/live/runs.jsonl[-1]", detail=f"live desk {run.get('day')}")
    rd = _none("contest/live/runs.jsonl or contest/live/refusals/")
    first = _contest_live_first_day()
    never = task is not None and str(task.get("Last Result", "")).strip() == NEVER_RAN_RC
    today = ctx.now.date()
    if first and today < first:
        rd.idle_reason = f"not yet due: the live desk's first sheet day is {first}"
    elif never:
        rd.idle_reason = (f"the scheduler says it has never run (0x41303); next run "
                          f"{task.get('Next Run Time')}")
    return rd


def r_hyp_lab(ctx, task) -> Reading:
    p, d = _newest(ctx.optimus_dir / "hyp_lab" / "receipts", "nightly_*.json")
    if not isinstance(d, dict):
        return _none("hyp_lab/receipts/nightly_*.json")
    st = str(d.get("status") or "MISSING_STATUS")
    status = "OK" if st == "OK" else "REFUSED"
    return Reading(stamp=parse_stamp(d.get("started_utc")), status=status,
                   reason=str(d.get("reason") or d.get("why_exited") or st),
                   substance=substance({k: d.get(k) for k in ("declared", "results", "generation")}),
                   proof=f"hyp_lab/receipts/{p.name} started_utc",
                   detail=f"hyp_lab nightly {st}; declared {d.get('declared')}")


def r_world_digest(ctx, task) -> Reading:
    p, d = _newest(ctx.optimus_dir / "digest", "world_digest_*.json")
    if not isinstance(d, dict):
        return _none("digest/world_digest_*.json")
    return Reading(stamp=parse_stamp(d.get("stamp")), substance=substance({k: d.get(k) for k in ("n_items", "counts", "themes")}),
                   proof=f"digest/{p.name} stamp", detail=f"digest {p.name}: {d.get('n_items')} items")


def r_alerts(ctx, task) -> Reading:
    p, d = _newest(ctx.optimus_dir / "alerts" / "receipts", "alert_pass_*.json")
    if not isinstance(d, dict):
        return _none("alerts/receipts/alert_pass_*.json")
    refused = d.get("refused") or d.get("status") == "REFUSED"
    return Reading(stamp=parse_stamp(d.get("created_utc")), status="REFUSED" if refused else "OK",
                   reason=str(d.get("refused") or ""),
                   proof=f"alerts/receipts/{p.name} created_utc",
                   detail=f"alert pass {d.get('mode')}: {d.get('n_events')} event(s)")


def r_straddle(ctx, task) -> Reading:
    p, d = _newest(ctx.optimus_dir / "straddle_forward" / "runs", "pass_*.json")
    if not isinstance(d, dict):
        return _none("straddle_forward/runs/pass_*.json")
    w = d.get("window") or {}
    idle = None if w.get("in_window") else f"outside its declared window {w.get('window_et')} ET ({w.get('reason')})"
    return Reading(stamp=parse_stamp(d.get("now_utc") or d.get("stamp")),
                   substance=substance({"state": d.get("state"), "summary": d.get("summary"), "grade": d.get("grade")}),
                   idle_reason=idle, proof=f"straddle_forward/runs/{p.name} now_utc",
                   detail=f"straddle pass: {str(d.get('state'))[:120]}")


def _fleet_pass(which: str):
    def reader(ctx, task) -> Reading:
        folder = ctx.optimus_dir / "paper_accounts" / "fleet_manager" / "runs"
        try:
            files = sorted(folder.glob("run_*.json"))
        except OSError:
            files = []
        for p in reversed(files):
            d = _read(p)
            if isinstance(d, dict) and str(d.get("pass")) == which:
                st = str(d.get("status") or "OK")
                return Reading(stamp=parse_stamp(d.get("finished_utc") or d.get("started_utc")),
                               status="REFUSED" if st.startswith("REFUSED") else "OK",
                               reason=str(d.get("why") or d.get("refused") or ""),
                               substance=substance(d.get("accounts")),
                               proof=f"fleet_manager/runs/{p.name} finished_utc",
                               detail=f"fleet manager {which} pass {p.name}")
        return _none(f"paper_accounts/fleet_manager/runs/run_*.json with pass={which}")
    return reader


def r_fleet_daily(ctx, task) -> Reading:
    p, d = _newest(ctx.optimus_dir / "paper_accounts" / "fleet_daily", "fleet_*.json")
    if not isinstance(d, dict):
        return _none("paper_accounts/fleet_daily/fleet_*.json")
    retired = set(getattr(_config, "PAPER_ACCOUNTS_RETIRED_UNREADABLE", ()) or ())
    accts = [a for a in d.get("accounts") or [] if isinstance(a, dict)]
    bad = [a.get("role") for a in accts if a.get("status") != "ok" and a.get("role") not in retired]
    excused = [f"{a.get('role')} {a.get('status')}" for a in accts
               if a.get("status") != "ok" and a.get("role") in retired]
    return Reading(stamp=parse_stamp(d.get("stamp_utc")), status="DEGRADED" if bad else "OK",
                   reason=f"accounts not ok: {bad}" if bad else "",
                   substance=substance(d.get("accounts")), proof=f"fleet_daily/{p.name} stamp_utc",
                   detail=f"fleet daily check: {d.get('n_flags')} flag(s)"
                          + (f"; retired, excused by config: {excused}" if excused else ""))


def r_reader(ctx, task) -> Reading:
    dj = ctx.optimus_dir / "dowjones"
    row = _last_row(dj / "night_reader_supervisor.jsonl", lambda r: r.get("event") == "tick")
    if (dj / "SUPERVISOR_STOP").exists():
        return Reading(stamp=parse_stamp((row or {}).get("t")), status="STOPPED",
                       reason="dowjones/SUPERVISOR_STOP exists (the owner's pause)",
                       proof="dowjones/SUPERVISOR_STOP", detail="reader paused by the owner")
    if row is None:
        return _none("dowjones/night_reader_supervisor.jsonl (event tick)")
    return Reading(stamp=parse_stamp(row.get("t")), substance=str(row.get("page_loads_total")),
                   proof="night_reader_supervisor.jsonl[tick].t + page_loads_total",
                   detail=f"supervisor tick: {row.get('page_loads_total')} page loads total, "
                          f"{row.get('new_loads')} new")


def r_catchup(ctx, task) -> Reading:
    row = _last_row(ctx.optimus_dir / "task_keeper" / "keeper.jsonl", lambda r: r.get("job") == "catchup")
    if row is None:
        return _none("task_keeper/keeper.jsonl (job catchup)")
    bad = row.get("action") == "cannot_determine"
    return Reading(stamp=parse_stamp(row.get("utc")), status="DEGRADED" if bad else "OK",
                   reason=str(row.get("why") or ""), proof="task_keeper/keeper.jsonl[catchup].utc",
                   detail=f"catch-up: started {row.get('started') or 'nothing'}")


def _terminal_repo(ctx) -> Path:
    return Path(ctx.paths.get("terminal_repo")
                or os.getenv("AAT_REPO") or (ctx.repo.parent / "aegis-alpha-terminal"))


def r_analyst_panel(ctx, task) -> Reading:
    root = _terminal_repo(ctx)
    folder = root / "state" / "research" / "analyst_panel"
    if not folder.exists():
        return Reading(unknown_reason=("the panel's receipts live in the terminal repo "
                                       "(state/research/analyst_panel/<date>.jsonl), which is not "
                                       "present beside this repo on this machine"),
                       proof="aegis-alpha-terminal/state/research/analyst_panel")
    try:
        files = sorted(folder.glob("20??-??-??.jsonl"))
    except OSError:
        files = []
    if not files:
        return _none("aegis-alpha-terminal/state/research/analyst_panel/<date>.jsonl")
    p = files[-1]
    row = _last_row(p)
    t = parse_stamp((row or {}).get("captured_utc")) or parse_stamp(p.stem)
    n = sum(1 for _ in open(p, encoding="utf-8", errors="replace"))
    return Reading(stamp=t, substance=f"{p.name}|{n}", proof=f"analyst_panel/{p.name}[-1].captured_utc",
                   detail=f"analyst panel {p.stem}: {n} rows")


def r_analyst_pull(ctx, task) -> Reading:
    p, d = _newest(ctx.optimus_dir / "analyst", "analyst_pull_*.json")
    k = _last_row(ctx.optimus_dir / "task_keeper" / "analyst.jsonl")
    t_pull = parse_stamp((d or {}).get("written_utc")) if isinstance(d, dict) else None
    t_k = parse_stamp((k or {}).get("utc"))
    if k and str(k.get("action")) == "refused" and t_k and (t_pull is None or t_k > t_pull):
        return Reading(stamp=t_k, status="REFUSED", reason=str(k.get("why")),
                       proof="task_keeper/analyst.jsonl[-1]", detail=f"analyst pull REFUSED: {k.get('why')}")
    if not isinstance(d, dict):
        return _none("analyst/analyst_pull_<day>.json")
    ok = (d.get("n_snapshots") or 0) > 0
    return Reading(stamp=t_pull, status="OK" if ok else "DEGRADED",
                   reason="" if ok else "the pull wrote zero snapshots",
                   substance=f"{p.name}|{d.get('n_snapshots')}|{d.get('n_revision_rows')}",
                   proof=f"analyst/{p.name} written_utc",
                   detail=f"analyst pull {d.get('day')}: {d.get('n_snapshots')} snapshots of "
                          f"{d.get('n_requested')}, {d.get('n_failed')} failed")


def r_brain(ctx, task) -> Reading:
    k = _last_row(ctx.optimus_dir / "task_keeper" / "brain.jsonl")
    if k is None:
        return _none("task_keeper/brain.jsonl")
    a = str(k.get("action"))
    status = {"ok": "OK", "refused": "REFUSED", "failed": "DEGRADED"}.get(a, "DEGRADED")
    return Reading(stamp=parse_stamp(k.get("utc")), status=status, reason=str(k.get("why") or ""),
                   substance=None, proof="task_keeper/brain.jsonl[-1]",
                   detail=f"brain refresh {a}: {str(k.get('summary') or k.get('why') or '')[:140]}")


def r_no_receipt(why: str):
    def reader(ctx, task) -> Reading:
        return Reading(unknown_reason=why)
    return reader


def r_retired(ctx, task) -> Reading:
    return Reading(detail="retired one-shot")


TASK_RECEIPT: dict[str, TaskSpec] = {
    "AegisDailyPass": TaskSpec(r_daily_pass, "night_factory_<d>/daily_pass_<d>.json"),
    "AegisIIF1NightLauncher": TaskSpec(_delegate("p_iif1_night", "iif1_night"), "iif1_nights/<weekday>.json",
                                       hash_off="judged by the iif1_night probe (weekday-aware)"),
    "AegisNNLabNightly": TaskSpec(r_nn_lab, "nn_lab.health_contract() over nn_lab/receipts/nightly_*.json"),
    "AegisSimOwner": TaskSpec(r_sim_owner, "sim/owner.jsonl",
                              hash_off="the owner's row is legitimately constant while one session runs; "
                                       "the session itself is the sim_session row"),
    "AegisDataCatalog": TaskSpec(r_catalog, "data_catalog/catalog_*.json"),
    "AegisContestRehearsal": TaskSpec(r_rehearsal, "contest/rehearsal/runs.jsonl"),
    "AegisContestDesk": TaskSpec(r_contest_desk, "contest/live/runs.jsonl | contest/live/refusals/live_gate_*.json",
                                 session_only=True),
    "AegisHypLabNightly": TaskSpec(r_hyp_lab, "hyp_lab/receipts/nightly_*.json"),
    "AegisWorldDigest": TaskSpec(r_world_digest, "digest/world_digest_*.json"),
    "AegisAlerts": TaskSpec(r_alerts, "alerts/receipts/alert_pass_*.json",
                            hash_off="a quiet market legitimately repeats the same pass"),
    "AegisStraddleForward": TaskSpec(r_straddle, "straddle_forward/runs/pass_*.json"),
    "AegisFleetManagerOpen": TaskSpec(_fleet_pass("open"), "paper_accounts/fleet_manager/runs/run_* (pass open)",
                                      session_only=True),
    "AegisFleetManagerPreclose": TaskSpec(_fleet_pass("preclose"),
                                          "paper_accounts/fleet_manager/runs/run_* (pass preclose)",
                                          session_only=True),
    "AegisFleetDailyCheck": TaskSpec(r_fleet_daily, "paper_accounts/fleet_daily/fleet_*.json"),
    "AegisReaderSupervisor": TaskSpec(r_reader, "dowjones/night_reader_supervisor.jsonl (tick)"),
    "AegisCatchUp": TaskSpec(r_catchup, "task_keeper/keeper.jsonl (job catchup)",
                             hash_off="an all-'ok' catch-up row is the healthy steady state"),
    "AegisTelegramAgent": TaskSpec(_delegate("p_telegram_agent", "telegram_agent"),
                                   "telegram/heartbeat.json + agent pid",
                                   hash_off="judged by the telegram_agent probe (pid + heartbeat)"),
    "AegisAnalystPanelDaily": TaskSpec(r_analyst_panel, "aegis-alpha-terminal state/research/analyst_panel/<date>.jsonl",
                                       session_only=True),
    "AegisAnalystPull": TaskSpec(r_analyst_pull, "analyst/analyst_pull_<day>.json | task_keeper/analyst.jsonl"),
    "AegisBrainRefresh": TaskSpec(r_brain, "task_keeper/brain.jsonl",
                                  hash_off="the brain page's own stamp is the optimus_brain row"),
    "AegisWRDSPullNight": TaskSpec(r_retired, "none (retired one-shot, 2026-08-21)", retired=True),
    "AegisAlwaysOnLab": TaskSpec(_delegate("p_always_on_lab", "always_on_lab"),
                                 "lab_status.json (judged by the always_on_lab probe)",
                                 hash_off="judged by the always_on_lab probe (pid + OFF marker)",
                                 registered_only=True),
    "AegisNightPreOpen": TaskSpec(r_no_receipt(
        "scripts.night_cache_sentinel --before prints and writes NO receipt; night_schedule_plan "
        "only prints this registration. Give the sentinel a receipt before registering it."),
        "none: night_cache_sentinel writes no receipt", registered_only=True),
}


# ═══════════════════════════════════════════════════════════════ judging

def _non_session_days(after: date, upto: date) -> int:
    from backend.services import system_health as SH                # noqa: PLC0415
    if upto <= after:
        return 0
    sess, _ = SH._sessions(after + timedelta(days=1), upto)
    return (upto - after).days - len(sess)


def allowed_age_s(name: str, spec: TaskSpec, stamp: Optional[datetime], now: datetime) -> float:
    from backend.services import system_health as SH                # noqa: PLC0415
    cad_h = float(_config.HEALTH_TASK_CADENCE_H.get(name, 24.0))
    allowed = cad_h * 3600 * (1 + SH.GRACE)
    if spec.session_only and stamp is not None:
        allowed += 86400 * _non_session_days(SH._et(stamp).date(), SH._et(now).date())
    return allowed


def _progress(ctx, name: str, sub: Optional[str]) -> tuple[int, Optional[datetime]]:
    """Record the substance hash; return (consecutive probes with it, first seen)."""
    prog = ctx.new_state.setdefault("progress", dict(ctx.prev_state.get("progress") or {}))
    if sub is None:
        prog.pop(name, None)
        return 0, None
    h = hashlib.sha256(sub.encode("utf-8")).hexdigest()[:16]
    prev = prog.get(name) or {}
    from backend.services import system_health as SH                # noqa: PLC0415
    if prev.get("hash") == h:
        rec = {"hash": h, "first_seen_utc": prev.get("first_seen_utc") or SH._iso(ctx.now),
               "n_same": int(prev.get("n_same") or 1) + 1}
    else:
        rec = {"hash": h, "first_seen_utc": SH._iso(ctx.now), "n_same": 1}
    prog[name] = rec
    return rec["n_same"], parse_stamp(rec["first_seen_utc"])


def _today_idle(spec: TaskSpec, now: datetime) -> Optional[str]:
    if not spec.session_only:
        return None
    from backend.services import system_health as SH                # noqa: PLC0415
    et = SH._et(now)
    sess, _ = SH._sessions(et.date(), et.date())
    return None if sess else f"no XNYS session on {et.date()} (declared idle: session-only task)"


@dataclass
class Judgement:
    state: str
    detail: str
    stamp: Optional[datetime] = None
    proof: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def verdict(self) -> str:
        return COARSE[self.state]


def judge(ctx, name: str, task: Optional[dict], spec: Optional[TaskSpec] = None) -> Judgement:
    """One task -> one state. `task` is the schtasks row (None = not registered)."""
    from backend.services import system_health as SH                # noqa: PLC0415
    spec = spec or TASK_RECEIPT.get(name)
    if spec is None:
        return Judgement("UNKNOWN", f"no receipt is declared for {name}: add it to "
                                    f"task_receipts.TASK_RECEIPT")
    if spec.retired:
        return Judgement("DEGRADED", f"retired task still registered ({spec.receipt}); delete it: "
                                     f"schtasks /Delete /TN {name} /F", proof="task_receipts.TASK_RECEIPT retired")
    if task is not None and str(task.get("Scheduled Task State")) == "Disabled":
        return Judgement("STOPPED_BY_OPERATOR", "the scheduled task is Disabled", proof="schtasks state")
    try:
        rd = spec.reader(ctx, task)
    except Exception as exc:                                          # noqa: BLE001
        return Judgement("UNKNOWN", f"receipt reader raised {type(exc).__name__}: {str(exc)[:160]}")
    t, now = rd.stamp, ctx.now
    age = SH._age(t, now)
    proof = rd.proof or spec.receipt
    unreg = task is None
    owner = "" if not unreg else "; NO scheduled task by this name -- nothing writes the next receipt"
    if rd.unknown_reason:
        return Judgement("UNKNOWN", rd.unknown_reason, proof=proof)
    if rd.status == "STOPPED":
        return Judgement("STOPPED_BY_OPERATOR", rd.reason or rd.detail, t, proof)
    allowed = allowed_age_s(name, spec, t, now)
    age_txt = f"newest receipt {SH._fmt_age(age)} old (allowed {SH._fmt_age(allowed)})"
    if rd.delegated is not None:
        v = rd.delegated
        state = {"ALIVE": "ALIVE_PROGRESSING", "STALE": "STALE", "DEAD": "DEAD", "REFUSED": "REFUSED",
                 "UNKNOWN": "UNKNOWN", "STOPPED_BY_OPERATOR": "STOPPED_BY_OPERATOR"}.get(v, "UNKNOWN")
        if state == "ALIVE_PROGRESSING" and unreg:
            state = "DEGRADED"
        if state == "UNKNOWN":
            # the task IS declared and scheduled; the delegate found nothing it wrote
            state = "DEAD" if unreg else "STALE"
            return Judgement(state, f"scheduled, but no derivable receipt -- {rd.detail}" + owner, t, proof)
        return Judgement(state, rd.detail + owner, t, proof)
    if t is None:
        if rd.idle_reason:
            return Judgement("ALIVE_IDLE_EXPECTED", f"no receipt yet; {rd.idle_reason}" + owner, None, proof)
        if unreg:
            return Judgement("DEAD", f"{rd.detail}{owner}", None, proof)
        return Judgement("STALE", f"{rd.detail}: the task is scheduled but has never written its receipt "
                                  f"(Last Run {task.get('Last Run Time')})", None, proof)
    if age is not None and age > allowed:
        if rd.status == "REFUSED":
            return Judgement("STALE", f"newest receipt is an OLD refusal ({rd.reason[:120]}); {age_txt}"
                             + owner, t, proof)
        return Judgement("DEAD" if unreg else "STALE", f"{age_txt}; {rd.detail}{owner}", t, proof)
    if rd.status == "REFUSED":
        return Judgement("REFUSED", f"{rd.reason[:220]} ({SH._fmt_age(age)} ago)" + owner, t, proof)
    n_same, first = _progress(ctx, name, rd.substance)
    idle = rd.idle_reason or _today_idle(spec, now)
    if (rd.substance is not None and n_same >= int(_config.HEALTH_PROGRESS_SAME_HASH_PROBES)
            and first is not None and (now - first).total_seconds() > allowed and not idle):
        return Judgement("STALE", f"same output for {SH._fmt_age((now - first).total_seconds())} across "
                                  f"{n_same} probes (allowed {SH._fmt_age(allowed)}), though the stamp "
                                  f"moved; {rd.detail}" + owner, t, proof,
                         extra={"same_hash_probes": n_same})
    if unreg:
        return Judgement("DEGRADED", f"receipt fresh ({SH._fmt_age(age)}) but{owner[1:]}; {rd.detail}", t, proof)
    if rd.status == "DEGRADED":
        return Judgement("DEGRADED", f"{rd.reason[:160]}; {rd.detail} ({SH._fmt_age(age)} ago)", t, proof)
    if idle:
        return Judgement("ALIVE_IDLE_EXPECTED", f"{idle}; {rd.detail} ({SH._fmt_age(age)} ago)", t, proof)
    hash_note = f" [hash rule off: {spec.hash_off}]" if rd.substance is None and spec.hash_off else ""
    return Judgement("ALIVE_PROGRESSING", f"{rd.detail} ({SH._fmt_age(age)} ago){hash_note}", t, proof)
